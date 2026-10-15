#!/usr/bin/env python3
"""StudyR analysis (pre-registered in reports/study_r_device_vs_cloud.md).

Usage: python experiments/erqa/study_r_analyse.py [--trials PATH] [--out PATH]
Prints markdown tables and writes a results JSON.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp  # noqa: E402

SPATIAL = {"Spatial Reasoning", "Pointing"}
N_BOOT = 10_000
BUDGET_B = 8192
PUBLISHED = {"A": 41.3, "B": 47.3}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def paired(x, y, qids, rng):
    """x, y: dict qid->bool. Returns diff (x-y) in pp, bootstrap CI, b, c, McNemar exact p."""
    q = [i for i in qids if i in x and i in y]
    a = np.array([x[i] for i in q], dtype=float)
    b_ = np.array([y[i] for i in q], dtype=float)
    d = a - b_
    n = len(q)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    boots = d[idx].mean(axis=1)
    b = int(((a == 1) & (b_ == 0)).sum())  # x right, y wrong
    c = int(((a == 0) & (b_ == 1)).sum())  # x wrong, y right
    p = binomtest(b, b + c, 0.5).pvalue if b + c > 0 else 1.0
    return dict(n=n, diff_pp=round(100 * d.mean(), 2),
                ci_pp=[round(100 * np.percentile(boots, 2.5), 2), round(100 * np.percentile(boots, 97.5), 2)],
                b=b, c=c, discordance=round((b + c) / n, 3), mcnemar_p=round(p, 4))


def pct(v, q):
    return float(np.percentile(v, q)) if len(v) else float("nan")


def rescore_D_at_8192(t, tokenizer):
    """Truncate D's raw output to 8192 tokens and re-parse exactly as B was parsed."""
    from study_r_erqa import extract_letter
    if t["n_generated"] <= BUDGET_B:
        return t["correct"]
    ids = tokenizer.encode(t["raw_output"], add_special_tokens=False)[:BUDGET_B]
    full = tokenizer.decode(ids, skip_special_tokens=True)
    if "</think>" in full:
        ans = full.split("</think>", 1)[1].strip()
    else:
        ans = full
    pred, _ = extract_letter(ans)
    return (pred == t["correct_letter"]) if pred else False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default="results/erqa/study_r/study_r_trials_h100nvl.jsonl")
    ap.add_argument("--out", default="results/erqa/study_r/study_r_results_h100nvl.json")
    ap.add_argument("--no-rescore", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.trials) if l.strip()]
    arms = {}
    for r in rows:
        arms.setdefault(r["arm"], {})[r["question_id"]] = r
    cat = {r["question_id"]: r["category"] for r in rows}
    spatial = sorted(q for q in cat if cat[q] in SPATIAL)
    overall = sorted(cat)
    rng = np.random.default_rng(0)
    out = {"n_trials": len(rows), "arms_present": {a: len(v) for a, v in arms.items()}}

    # 1. accuracy
    acc = {}
    print("## 1. Accuracy (random baseline 25%)\n")
    print("| arm | subset | n | correct | acc % | 95% Wilson CI | no_letter | last_found |")
    print("|---|---|---|---|---|---|---|---|")
    for a in [x for x in ("A", "B", "C", "D", "A_h100") if x in arms]:
        for name, qs in (("spatial", spatial), ("overall", overall)):
            ts = [arms[a][q] for q in qs if q in arms[a]]
            if not ts:
                continue
            k = sum(t["correct"] for t in ts)
            lo, hi = wilson(k, len(ts))
            nl = sum(t["parse_status"] == "no_letter" for t in ts)
            lf = sum(t["parse_status"] == "last_found" for t in ts)
            acc[(a, name)] = dict(n=len(ts), correct=k, acc=round(100 * k / len(ts), 1),
                                  ci=[round(100 * lo, 1), round(100 * hi, 1)], no_letter=nl, last_found=lf)
            print(f"| {a} | {name} | {len(ts)} | {k} | {100*k/len(ts):.1f} | "
                  f"[{100*lo:.1f}, {100*hi:.1f}] | {nl} | {lf} |")
    out["accuracy"] = {f"{a}|{s}": v for (a, s), v in acc.items()}

    # 2. decomposition
    corr = {a: {q: t["correct"] for q, t in v.items()} for a, v in arms.items()}
    terms = [("C−A size @instruct", "C", "A"), ("D−B size @thinking", "D", "B"),
             ("B−A thinking @4B", "B", "A"), ("D−C thinking @32B (PRIMARY)", "D", "C"),
             ("D−A total device→cloud", "D", "A")]
    out["decomposition"] = {}
    for name, qs in (("spatial", spatial), ("overall", overall)):
        print(f"\n## 2. Decomposition — {name}\n")
        print("| term | n | diff pp | 95% paired bootstrap CI | b (x✓y✗) | c (x✗y✓) | McNemar p |")
        print("|---|---|---|---|---|---|---|")
        for label, x, y in terms:
            if x in corr and y in corr:
                r = paired(corr[x], corr[y], qs, rng)
                if r["n"] == 0:
                    continue
                out["decomposition"][f"{name}|{label}"] = r
                print(f"| {label} | {r['n']} | {r['diff_pp']:+.1f} | [{r['ci_pp'][0]:+.1f}, {r['ci_pp'][1]:+.1f}] "
                      f"| {r['b']} | {r['c']} | {r['mcnemar_p']} |")

    # 3. verdict
    prim = out["decomposition"].get("spatial|D−C thinking @32B (PRIMARY)")
    if prim and prim["n"] == len(spatial):
        pays = prim["diff_pp"] > 5 and prim["ci_pp"][0] > 0
        out["verdict"] = "THINKING PAYS AT 32B" if pays else "THINKING DOES NOT PAY AT SCALE"
        print(f"\n## 3. Verdict: **{out['verdict']}** (D−C spatial {prim['diff_pp']:+.1f} pp, "
              f"CI [{prim['ci_pp'][0]:+.1f}, {prim['ci_pp'][1]:+.1f}])")
    else:
        out["verdict"] = "INCOMPLETE"
        print("\n## 3. Verdict: INCOMPLETE (spatial D or C not complete)")

    # 3b. budget-matched D−B (D re-scored at 8192)
    if "D" in arms and not args.no_rescore and "raw_output" in next(iter(arms["D"].values())):
        from transformers import AutoTokenizer
        from huggingface_hub import snapshot_download
        tok = AutoTokenizer.from_pretrained(snapshot_download(
            "Qwen/Qwen3-VL-32B-Thinking", revision="7edd10ffd1196091948fb245ff63e406ccb2d4d1",
            local_files_only=True))
        d8 = {q: rescore_D_at_8192(t, tok) for q, t in arms["D"].items()}
        n_over = sum(t["n_generated"] > BUDGET_B for t in arms["D"].values())
        changed = sum(d8[q] != arms["D"][q]["correct"] for q in d8)
        out["D_at_8192"] = {"n_over_8192": n_over, "n_score_changed": changed}
        for name, qs in (("spatial", spatial), ("overall", overall)):
            for label, y in (("D8192−B", "B"), ("D8192−C", "C")):
                if y in corr:
                    r = paired(d8, corr[y], qs, rng)
                    if r["n"]:
                        out["D_at_8192"][f"{name}|{label}"] = r
        print(f"\n## 3b. D re-scored at 8192: {n_over} D trials exceeded 8192 tokens; {changed} scores changed")
        for k, v in out["D_at_8192"].items():
            if isinstance(v, dict):
                print(f"- {k}: {v['diff_pp']:+.1f} pp [{v['ci_pp'][0]:+.1f}, {v['ci_pp'][1]:+.1f}] b={v['b']} c={v['c']}")

    # 4. termination / think tokens
    print("\n## 4. Thinking arms: termination and think tokens\n")
    print("| arm | subset | n | think closed % | budget hits | think tok median | IQR | p90 | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    out["thinking"] = {}
    for a in ("B", "D"):
        if a not in arms:
            continue
        for name, qs in (("spatial", spatial), ("overall", overall)):
            ts = [arms[a][q] for q in qs if q in arms[a]]
            if not ts:
                continue
            closed = [t for t in ts if t["think_closed"]]
            tk = [t["n_think_tokens"] for t in closed]
            bh = sum(bool(t["budget_hit"]) for t in ts)
            r = dict(n=len(ts), closed_pct=round(100 * len(closed) / len(ts), 1), budget_hits=bh,
                     think_median=pct(tk, 50), think_q1=pct(tk, 25), think_q3=pct(tk, 75),
                     think_p90=pct(tk, 90), think_max=max(tk) if tk else None)
            out["thinking"][f"{a}|{name}"] = r
            print(f"| {a} | {name} | {len(ts)} | {r['closed_pct']} | {bh} | {r['think_median']:.0f} | "
                  f"{r['think_q1']:.0f}–{r['think_q3']:.0f} | {r['think_p90']:.0f} | {r['think_max']} |")

    # 5. latency
    print("\n## 5. Latency\n")
    print("| arm | hardware | subset | n | median s | p90 s |")
    print("|---|---|---|---|---|---|")
    lat = {}
    for a in [x for x in ("A", "B", "C", "D", "A_h100") if x in arms]:
        for name, qs in (("spatial", spatial), ("overall", overall)):
            v = [arms[a][q]["total_latency_ms"] / 1000 for q in qs if q in arms[a]]
            if not v:
                continue
            hw = next(iter(arms[a].values())).get("_hardware", "?")
            lat[(a, name)] = dict(hardware=hw, n=len(v), median_s=round(pct(v, 50), 3), p90_s=round(pct(v, 90), 3))
            print(f"| {a} | {hw} | {name} | {len(v)} | {pct(v,50):.2f} | {pct(v,90):.2f} |")
    out["latency"] = {f"{a}|{s}": v for (a, s), v in lat.items()}
    for name in ("spatial", "overall"):
        for ref, lab in (("A_h100", "same hardware (primary)"), ("A", "cross-hardware A6000 (labelled)")):
            if ("D", name) in lat and (ref, name) in lat:
                r = lat[("D", name)]["median_s"] / lat[(ref, name)]["median_s"]
                out["latency"][f"D/{ref}|{name}"] = round(r, 1)
                print(f"- D/{ref} median ratio, {name}: {r:.1f}× — {lab}")

    # sanity: published
    print("\n## Sanity: 4B vs published (overall)")
    for a in ("A", "B"):
        if (a, "overall") in acc:
            print(f"- {a}: {acc[(a,'overall')]['acc']}% vs published {PUBLISHED[a]}% "
                  f"({acc[(a,'overall')]['acc'] - PUBLISHED[a]:+.1f} pp)")

    out["_provenance"] = stamp(script="study_r_analyse.py", model="qwen3vl", device="h100nvl",
                               n=len(spatial), seed=0, args=args)
    Path(args.out).write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
