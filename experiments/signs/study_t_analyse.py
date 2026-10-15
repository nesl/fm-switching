#!/usr/bin/env python3
"""StudyT analysis (pre-registered in reports/study_t_signs_32b.md).

Usage:
  python experiments/signs/study_t_analyse.py [--procs logs/<run>_gpu_procs.csv ...]
Reads trials + offline scores (study_t_score.py) + scorer_validation.json; prints markdown
tables and writes results/signs/study_t/study_t_results_h100nvl.json.

Committed comparators (A6000, transformers 5.12.x, same 40-sign manifest):
  termination @8192: 4B-T 28/40 (70.0%), 8B-T 36/40 (90.0%)   — reports/study_p_retry_vs_scale.md §2
  accuracy (non-term = 0): 4B-T 11/40, 8B-T 12/40, 8B-I 12/40 — reports/study_p_retry_vs_scale.md §3
  4B completer think-token medians: low 505 / mid 5,416 / high 4,897 / all 3,339 — reports/study_j2_survival.md §3
  4B survival (not terminated by B, single 24,576 run, seed 42) — reports/study_j2_survival.md §2
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp  # noqa: E402

TRIALS = "results/signs/study_t/study_t_trials_h100nvl.jsonl"
SCORES = "results/signs/study_t/study_t_scores_h100nvl.jsonl"
VALID = "results/signs/study_t/scorer_validation.json"
OUT = "results/signs/study_t/study_t_results_h100nvl.json"
J2_TRIALS = "results/signs/study_j2/study_j2_trials.jsonl"
P_TRIALS = "results/signs/study_p/study_p_trials.jsonl"

BINS = ("low", "mid", "high", "other")
SURV_B = (1024, 2048, 4096, 8192, 16384, 24576)
PRIOR_TERM_8192 = {"4B-T (StudyP A)": (28, 40), "8B-T (StudyP C)": (36, 40)}
PRIOR_ACC = {"4B-T (StudyP A)": (11, 40), "8B-T (StudyP C)": (12, 40), "8B-I (StudyP D)": (12, 40)}
PRIOR_MEDIANS_4B = {"low": 505, "mid": 5416, "high": 4897, "all": 3339}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def bin_of(n_gt):
    return "low" if 1 <= n_gt <= 2 else "mid" if 3 <= n_gt <= 5 else "high" if n_gt >= 6 else "other"


def pct(v, q):
    return float(np.percentile(v, q)) if len(v) else float("nan")


def ci_str(k, n):
    lo, hi = wilson(k, n)
    return f"{100*k/n:.1f}% [{100*lo:.1f}, {100*hi:.1f}]" if n else "—"


def contaminated_ids(trials, procs_paths):
    """Trials whose [start,end] window overlaps a procs-log row on the same GPU from a foreign PID."""
    from datetime import datetime
    if not procs_paths:
        return set(), "no procs log given — contention NOT checked"
    own = {t.get("_pid") for t in trials}
    foreign = []  # (time, pid)
    for p in procs_paths:
        with open(p) as f:
            for row in csv.reader(f):
                if len(row) < 4 or row[0].startswith("timestamp"):
                    continue
                ts, uuid, pid = row[0].strip(), row[1].strip(), row[2].strip()
                try:
                    pid = int(pid)
                    tt = datetime.strptime(ts, "%Y/%m/%d %H:%M:%S.%f")
                except ValueError:
                    continue
                foreign.append((tt, uuid.replace("GPU-", ""), pid))
    bad = set()
    for t in trials:
        g = (t.get("_gpu_uuid") or "").replace("GPU-", "")
        s, e = datetime.fromisoformat(t["start_wall"]), datetime.fromisoformat(t["end_wall"])
        for tt, uuid, pid in foreign:
            if uuid == g and pid not in own and s <= tt <= e:
                bad.add((t["arm"], t["budget"], t["sign_id"]))
                break
    return bad, f"checked against {len(foreign)} proc-log rows from {procs_paths}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default=TRIALS)
    ap.add_argument("--scores", default=SCORES)
    ap.add_argument("--procs", nargs="*", default=[])
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.trials) if l.strip()]
    key = lambda t: (t["arm"], t["budget"], t["sign_id"])  # noqa: E731
    T = {key(t): t for t in rows}
    signs = sorted({t["sign_id"] for t in rows})
    sbin = {t["sign_id"]: t["bin"] for t in rows}
    out = {"n_trials": len(rows)}
    validated = False
    if Path(VALID).exists():
        v = json.load(open(VALID))
        validated = bool(v.get("passed"))
        out["scorer_validation"] = {k: v[k] for k in ("matched_denominator", "correct", "accuracy", "passed")}
    flag = "" if validated else " **UNVALIDATED SCORER**"

    t8 = [t for t in rows if t["arm"] == "T32" and t["budget"] == 8192]
    i8 = [t for t in rows if t["arm"] == "I32" and t["budget"] == 8192]

    # 1. termination @8192
    print("## 1. Termination at max_new_tokens=8192 (same 40-sign J2 manifest)\n")
    print("| model | terminated | n | rate [95% Wilson] | source |")
    print("|---|---|---|---|---|")
    for lab, (k, n) in PRIOR_TERM_8192.items():
        print(f"| {lab} | {k} | {n} | {ci_str(k, n)} | committed, A6000 |")
    k32 = sum(t["think_closed"] is True for t in t8)
    print(f"| **32B-T (this run)** | {k32} | {len(t8)} | {ci_str(k32, len(t8)) if t8 else '—'} | h100nvl |")
    ki = sum(not t["budget_hit"] for t in i8)
    print(f"| 32B-I (EOS before budget) | {ki} | {len(i8)} | {ci_str(ki, len(i8)) if i8 else '—'} | h100nvl |")
    out["termination_8192"] = dict(T32=[k32, len(t8)], I32_eos=[ki, len(i8)],
                                   T32_wilson=wilson(k32, len(t8)) if t8 else None,
                                   budget_hits_T32=sum(t["budget_hit"] for t in t8),
                                   priors=PRIOR_TERM_8192)
    # paired by sign vs committed StudyP per-sign trials (same manifest, same seed 42, same budget)
    if t8 and Path(P_TRIALS).exists():
        from scipy.stats import binomtest
        p_rows = [json.loads(l) for l in open(P_TRIALS)]
        mine = {t["sign_id"]: t["think_closed"] is True for t in t8}
        out["termination_8192"]["paired_vs_studyP"] = {}
        print("\nPaired by sign (McNemar exact):")
        for lab, arm in (("4B-T", "A"), ("8B-T", "C")):
            prior = {t["sign_id"]: t["think_closed"] is True for t in p_rows
                     if t["arm"] == arm and t.get("pass_index", 1) == 1}
            both = sorted(set(mine) & set(prior))
            b = sum(mine[s] and not prior[s] for s in both)   # 32B closed, prior open
            c = sum(prior[s] and not mine[s] for s in both)   # prior closed, 32B open
            p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
            out["termination_8192"]["paired_vs_studyP"][lab] = dict(n=len(both), b_32B_only=b, c_prior_only=c,
                                                                     mcnemar_p=round(p, 4))
            print(f"- 32B-T vs {lab}: n={len(both)}, 32B-only terminated b={b}, {lab}-only c={c}, McNemar p={p:.4f}")

    # 2. accuracy
    scores = {}
    if Path(args.scores).exists():
        for l in open(args.scores):
            s = json.loads(l)
            scores[(s["arm"], s["budget"], s["sign_id"])] = s
    print(f"\n## 2. Accuracy at 8192 (non-terminating = 0){flag}\n")
    print("| arm | correct | n | acc [95% Wilson] | parse_failed (eligible) | not eligible (non-term / budget) |")
    print("|---|---|---|---|---|---|")
    for lab, (k, n) in PRIOR_ACC.items():
        print(f"| {lab} | {k} | {n} | {ci_str(k, n)} | — | — | ")
    out["accuracy_8192"] = {}
    for arm, ts in (("T32", t8), ("I32", i8)):
        sc = [scores.get(key(t)) for t in ts]
        if not ts or any(s is None for s in sc):
            print(f"| {arm} | not scored yet | {len(ts)} | — | — | — |")
            continue
        k = sum(s["correct"] for s in sc)
        pf = sum(s["eligible"] and s["parse_status"] != "ok" for s in sc)
        ne = sum(not s["eligible"] for s in sc)
        print(f"| {arm}{flag} | {k} | {len(ts)} | {ci_str(k, len(ts))} | {pf} | {ne} |")
        out["accuracy_8192"][arm] = dict(correct=k, n=len(ts), wilson=wilson(k, len(ts)), parse_failed=pf,
                                         not_eligible=ne, scorer_validated=validated)
    if "T32" in out["accuracy_8192"] and "I32" in out["accuracy_8192"]:
        tc = {t["sign_id"]: scores[key(t)]["correct"] for t in t8}
        ic = {t["sign_id"]: scores[key(t)]["correct"] for t in i8}
        both = sorted(set(tc) & set(ic))
        b = sum(tc[s] and not ic[s] for s in both)
        c = sum(ic[s] and not tc[s] for s in both)
        out["accuracy_8192"]["T32_vs_I32_discordance"] = dict(n=len(both), b_T_right_I_wrong=b, c_I_right_T_wrong=c)
        print(f"\nT32 vs I32 paired discordance (n={len(both)}): b (T✓ I✗) = {b}, c (I✓ T✗) = {c}")

    # 3. think tokens among completers
    print("\n## 3. Think tokens among completers (T32 @8192) vs 4B (J2, completers within 24,576)\n")
    print("| bin | 32B completers | 32B median | 32B IQR | 32B p90 | 32B max | 4B median |")
    print("|---|---|---|---|---|---|---|")
    out["think_tokens_completers"] = {}
    for b in BINS + ("all",):
        tk = [t["n_think_tokens"] for t in t8 if t["think_closed"] and (b == "all" or t["bin"] == b)]
        nb = sum(1 for t in t8 if b == "all" or t["bin"] == b)
        r = dict(n_completers=len(tk), n=nb, median=pct(tk, 50), q1=pct(tk, 25), q3=pct(tk, 75),
                 p90=pct(tk, 90), max=max(tk) if tk else None, prior_4B_median=PRIOR_MEDIANS_4B.get(b))
        out["think_tokens_completers"][b] = r
        print(f"| {b} | {len(tk)}/{nb} | {r['median']:.0f} | {r['q1']:.0f}–{r['q3']:.0f} | {r['p90']:.0f} | "
              f"{r['max']} | {PRIOR_MEDIANS_4B.get(b, '—')} |")
    print("\nCensoring note: 32B completers are censored at 8192; 4B completers at 24,576 (J2) — "
          "medians are not like-for-like for slow completers.")

    # 4. per-bin termination @8192
    print("\n## 4. Per-bin termination at 8192\n")
    j2 = [json.loads(l) for l in open(J2_TRIALS)] if Path(J2_TRIALS).exists() else []
    print("| bin | 32B-T terminated | 4B-T terminated by 8192 (J2 read-off) |")
    print("|---|---|---|")
    out["per_bin_termination_8192"] = {}
    for b in BINS:
        tb = [t for t in t8 if t["bin"] == b]
        k = sum(t["think_closed"] is True for t in tb)
        jb = [t for t in j2 if bin_of(t["n_gt"]) == b]
        kj = sum(t["think_closed"] and t["n_think_tokens"] < 8192 for t in jb)
        out["per_bin_termination_8192"][b] = dict(T32=[k, len(tb)], J2_4B=[kj, len(jb)])
        print(f"| {b} | {k}/{len(tb)} | {kj}/{len(jb)} |")

    # 5. survival curve (core read-off + ladder rungs)
    print("\n## 5. Survival: fraction NOT terminated by budget B\n")
    print("4B: J2 single 24,576 run, read off at B (think_closed and n_think < B). "
          "32B: B ≤ 8192 read off the 8192 run; B = 16384 / 24576 from the ladder re-runs "
          "(leftover-time extension; a sign is terminated by B if closed in the 8192 run with n_think < B, "
          "or closed in a ladder rung ≤ B with n_think < B).\n")
    t_by = {}
    for t in rows:
        if t["arm"] == "T32":
            t_by.setdefault(t["sign_id"], {})[t["budget"]] = t
    surv = {}
    print("| B | 32B-T not terminated | 4B-T not terminated (J2) | 32B status |")
    print("|---|---|---|---|")
    for B in SURV_B:
        n_obs = 0
        nt = 0
        unobs = 0  # not closed at 8192 and rung B not run yet: must NOT be dropped silently (survivor bias)
        complete = True
        for s in signs:
            runs = t_by.get(s, {})
            if 8192 not in runs:
                complete = False
                continue
            term = any(r["think_closed"] and r["n_think_tokens"] < B for bb, r in runs.items() if bb <= max(B, 8192))
            if not term and B > 8192 and B not in runs:
                # not closed at 8192 and rung B not run (yet) -> unobserved
                complete = False
                unobs += 1
                continue
            n_obs += 1
            nt += (not term)
        kj = sum(not (t["think_closed"] and t["n_think_tokens"] < B) for t in j2)
        surv[B] = dict(T32_not_terminated=nt, T32_n=n_obs, T32_unobserved_nonterminated=unobs,
                       J2_4B_not_terminated=kj, J2_n=len(j2), complete=complete)
        if unobs:
            cell = (f"{nt}/{n_obs} observed + {unobs} not closed at 8192 with rung {B} NOT RUN "
                    f"(range {nt}–{nt + unobs} of {n_obs + unobs})")
        else:
            cell = f"{nt}/{n_obs} ({100*nt/n_obs:.1f}%)" if n_obs else "—"
        print(f"| {B} | {cell} | {kj}/{len(j2)} ({100*kj/len(j2):.1f}%) | "
              f"{'complete' if complete else 'PARTIAL'} |" if j2 else f"| {B} | — | — | — |")
    out["survival"] = surv
    pm = [t for t in rows if t.get("prefix_match") is not None]
    out["ladder_prefix_match"] = dict(n=len(pm), matched=sum(t["prefix_match"] for t in pm))
    if pm:
        print(f"\nLadder determinism check: {out['ladder_prefix_match']['matched']}/{len(pm)} re-runs reproduced "
              f"the previous rung's tokens as a prefix.")

    # 6. latency
    bad, how = contaminated_ids(rows, args.procs)
    out["contention"] = dict(method=how, contaminated=sorted(map(list, bad)))
    print(f"\n## 6. Latency (contended trials excluded: {len(bad)}; {how})\n")
    print("| arm | budget | n | median s | p90 s | median decode tok/s |")
    print("|---|---|---|---|---|---|")
    out["latency"] = {}
    for arm in ("I32", "T32"):
        for B in (8192,) + tuple(sorted({t['budget'] for t in rows if t['budget'] != 8192})):
            ts = [t for t in rows if t["arm"] == arm and t["budget"] == B and key(t) not in bad]
            if not ts:
                continue
            v = [t["latency_ms"] / 1000 for t in ts]
            tps = [t["decode_tok_s"] for t in ts]
            out["latency"][f"{arm}@{B}"] = dict(n=len(ts), median_s=pct(v, 50), p90_s=pct(v, 90),
                                                 decode_tok_s_median=pct(tps, 50))
            print(f"| {arm} | {B} | {len(ts)} | {pct(v,50):.1f} | {pct(v,90):.1f} | {pct(tps,50):.1f} |")

    # 7. one-line trend
    if t8:
        lo, hi = wilson(k32, len(t8))
        trend = (f"Termination at 8192: 4B 70% → 8B 90% → 32B {100*k32/len(t8):.1f}% "
                 f"[{100*lo:.1f}, {100*hi:.1f}] (n={len(t8)}).")
        out["trend_line"] = trend
        print(f"\n## 7. Trend\n\n{trend}")

    peak = {a: max((t["peak_reserved_gb"] for t in rows if t["arm"] == a), default=None) for a in ("I32", "T32")}
    out["peak_reserved_gb"] = peak
    print(f"\nPeak reserved VRAM per arm: {peak}")
    out["_provenance"] = stamp(script="study_t_analyse.py", model="qwen3vl-32b", device="h100nvl",
                               n=len(signs), seed=42, args=args)
    Path(args.out).write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
