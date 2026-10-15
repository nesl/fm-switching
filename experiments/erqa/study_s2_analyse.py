#!/usr/bin/env python3
"""StudyS2 analysis (pre-registered in reports/study_s2_mvrobobench_32b.md).

Usage: python experiments/erqa/study_s2_analyse.py [--trials PATH] [--out PATH]
          [--procs logs/study_s2_gpu_procs.csv --pid PID --gpu-uuid UUID] [--contended-ids FILE]
Prints markdown tables and writes a results JSON.
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp  # noqa: E402
from study_r_analyse import paired, pct, wilson  # noqa: E402

CATS = ["spatial_distance_judgement", "robotic_trajectory_selection"]
ARMS = ["I", "T", "C", "D"]
LABEL = {"I": "4B-Instruct", "T": "4B-Thinking", "C": "32B-Instruct", "D": "32B-Thinking"}
S1 = {"I": 37.4, "T": 38.4, "net_rescue": 1.00, "net_rescue_ci": [-4.74, 6.74]}  # flash-only, uncommitted here
S1_N = 401  # StudyS1 n (as reported); 4B arms are CROSS-STUDY aggregates in the two-arm design (2026-10-14)


def newcombe(p1, n1, p2, n2):
    """Unpaired 95% CI (Newcombe hybrid score) for p1 - p2, proportions in [0,1]."""
    l1, u1 = wilson(round(p1 * n1), n1)
    l2, u2 = wilson(round(p2 * n2), n2)
    d = p1 - p2
    return d - ((p1 - l1) ** 2 + (u2 - p2) ** 2) ** 0.5, d + ((u1 - p1) ** 2 + (p2 - l2) ** 2) ** 0.5
MATERIAL_PP = 3.0  # |4B here − S1| above which the discrepancy is reported as a finding


def contended_from_procs(procs_csv, own_pids, uuid):
    """Time windows where a foreign PID was on our GPU (5-s sampling → ±5 s padding)."""
    wins = []
    with open(procs_csv) as f:
        for row in csv.reader(f):
            if len(row) < 4 or row[0].startswith("timestamp"):
                continue
            ts, u, p = row[0].strip(), row[1].strip(), row[2].strip()
            if u == uuid and p not in own_pids:
                try:
                    t = datetime.strptime(ts, "%Y/%m/%d %H:%M:%S.%f").timestamp()
                except ValueError:
                    continue
                wins.append((t - 5, t + 5))
    return wins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default="results/erqa/study_s2/study_s2_trials_h100nvl.jsonl")
    ap.add_argument("--out", default="results/erqa/study_s2/study_s2_results_h100nvl.json")
    ap.add_argument("--procs")
    ap.add_argument("--pid", nargs="+", default=[])
    ap.add_argument("--gpu-uuid")
    ap.add_argument("--contended-ids", help="file with one '<arm> <path>' per line")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.trials) if l.strip()]
    arms = {}
    for r in rows:
        arms.setdefault(r["arm"], {})[r["path"]] = r
    cat = {r["path"]: r["category"] for r in rows}
    rng = np.random.default_rng(0)
    out = {"n_trials": len(rows), "arms_present": {a: len(v) for a, v in arms.items()}}

    # subsets: complete-case per subset (questions answered by all four arms) for the decomposition
    allq = sorted(cat)
    subsets = {"stratum (both categories)": allq}
    for c in CATS:
        subsets[c] = [q for q in allq if cat[q] == c]
    present = [a for a in ARMS if a in arms]
    complete = {k: [q for q in v if all(q in arms[a] for a in present)] for k, v in subsets.items()}
    out["n_complete_case"] = {k: len(v) for k, v in complete.items()}
    n_opts = {len(r.get("prompt", "").split("Options:\n", 1)[-1].split("\nAnswer")[0].splitlines())
              for r in rows if r.get("prompt")}
    baseline = 100 / list(n_opts)[0] if len(n_opts) == 1 else None
    out["n_options"] = sorted(n_opts)
    print(f"Options per question: {sorted(n_opts)} → random baseline "
          f"{baseline:.0f}%\n" if baseline else f"Options per question MIXED {n_opts}\n")

    # 1. accuracy + 2x2
    acc = {}
    print("## 1. Accuracy (random baseline {:.0f}%)\n".format(baseline or float('nan')))
    print("| arm | model | subset | n | correct | acc % | 95% Wilson CI | no_letter | last_found |")
    print("|---|---|---|---|---|---|---|---|---|")
    for a in present:
        for name, qs in subsets.items():
            ts = [arms[a][q] for q in qs if q in arms[a]]
            if not ts:
                continue
            k = sum(bool(t["correct"]) for t in ts)
            lo, hi = wilson(k, len(ts))
            nl = sum(t["parse_status"] == "no_letter" for t in ts)
            lf = sum(t["parse_status"] == "last_found" for t in ts)
            acc[(a, name)] = dict(n=len(ts), correct=k, acc=round(100 * k / len(ts), 1),
                                  ci=[round(100 * lo, 1), round(100 * hi, 1)], no_letter=nl, last_found=lf)
            print(f"| {a} | {LABEL[a]} | {name} | {len(ts)} | {k} | {100*k/len(ts):.1f} | "
                  f"[{100*lo:.1f}, {100*hi:.1f}] | {nl} | {lf} |")
    out["accuracy"] = {f"{a}|{s}": v for (a, s), v in acc.items()}
    print("\n### 2x2 (stratum, acc % [Wilson CI])\n")
    print("| | Instruct | Thinking |\n|---|---|---|")
    for size, (i, t) in (("4B", ("I", "T")), ("32B", ("C", "D"))):
        cell = lambda a: (f"{S1[a]} (StudyS1, cross-study)" if a in S1 and (a, "stratum (both categories)") not in acc else
                          f"{acc[(a, 'stratum (both categories)')]['acc']} "
                          f"[{acc[(a, 'stratum (both categories)')]['ci'][0]}, "
                          f"{acc[(a, 'stratum (both categories)')]['ci'][1]}]"
                          if (a, "stratum (both categories)") in acc else "—")
        print(f"| {size} | {cell(i)} | {cell(t)} |")

    # 2. decomposition (paired, complete-case)
    corr = {a: {q: bool(t["correct"]) for q, t in v.items()} for a, v in arms.items()}
    terms = [("C−I size @instruct", "C", "I"), ("D−T size @thinking", "D", "T"),
             ("T−I thinking @4B (net_rescue 4B)", "T", "I"),
             ("D−C thinking @32B = net_rescue (PRIMARY)", "D", "C"),
             ("D−I total device→cloud", "D", "I")]
    out["decomposition"] = {}
    for name, qs in complete.items():
        print(f"\n## 2. Decomposition — {name} (complete-case n={len(qs)})\n")
        print("| term | n | diff pp | 95% paired bootstrap CI | b (x✓y✗) | c (x✗y✓) | discordance | McNemar p |")
        print("|---|---|---|---|---|---|---|---|")
        for label, x, y in terms:
            if x in corr and y in corr and qs:
                r = paired(corr[x], corr[y], qs, rng)
                out["decomposition"][f"{name}|{label}"] = r
                print(f"| {label} | {r['n']} | {r['diff_pp']:+.2f} | [{r['ci_pp'][0]:+.2f}, {r['ci_pp'][1]:+.2f}] "
                      f"| {r['b']} | {r['c']} | {r['discordance']} | {r['mcnemar_p']} |")

    # 3. verdict
    prim = out["decomposition"].get("stratum (both categories)|D−C thinking @32B = net_rescue (PRIMARY)")
    if prim:
        pays = prim["diff_pp"] > 5 and prim["ci_pp"][0] > 0
        out["verdict"] = ("THINKING PAYS AT 32B on this stratum" if pays else
                          "THINKING DOES NOT PAY AT 32B on this stratum: the StudyS1 negative is NOT "
                          "scale-specific and the four-workload negative stands at 32B")
        n_stratum = 401  # manifest: SDJ 201 + RTS 200
        if prim["n"] < n_stratum:
            out["verdict"] = f"PARTIAL (complete-case n={prim['n']} of {n_stratum}): " + out["verdict"]
        print(f"\n## 3. Verdict: **{out['verdict']}** (net_rescue D−C {prim['diff_pp']:+.2f} pp, "
              f"CI [{prim['ci_pp'][0]:+.2f}, {prim['ci_pp'][1]:+.2f}], n={prim['n']}, "
              f"b={prim['b']}, c={prim['c']})")
        print(f"   Reshuffling: {prim['b'] + prim['c']} of {prim['n']} answers changed "
              f"({100*prim['discordance']:.1f}%), net {prim['b'] - prim['c']:+d}.")
    else:
        out["verdict"] = "INCOMPLETE"
        print("\n## 3. Verdict: INCOMPLETE")

    # 4. termination / think tokens
    print("\n## 4. Thinking arms: termination and think tokens\n")
    print("| arm | subset | n | think closed % | budget hits | think tok median | IQR | p90 | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    out["thinking"] = {}
    for a in ("T", "D"):
        if a not in arms:
            continue
        for name, qs in subsets.items():
            ts = [arms[a][q] for q in qs if q in arms[a]]
            if not ts:
                continue
            closed = [t for t in ts if t["think_closed"]]
            tk = [t["n_think_tokens"] for t in closed]
            bh = sum(bool(t["budget_hit"]) for t in ts)
            r = dict(n=len(ts), closed_pct=round(100 * len(closed) / len(ts), 1), budget_hits=bh,
                     budget_hit_pct=round(100 * bh / len(ts), 1),
                     think_median=pct(tk, 50), think_q1=pct(tk, 25), think_q3=pct(tk, 75),
                     think_p90=pct(tk, 90), think_max=max(tk) if tk else None)
            out["thinking"][f"{a}|{name}"] = r
            print(f"| {a} | {name} | {len(ts)} | {r['closed_pct']} | {bh} ({r['budget_hit_pct']}%) | "
                  f"{r['think_median']:.0f} | {r['think_q1']:.0f}–{r['think_q3']:.0f} | "
                  f"{r['think_p90']:.0f} | {r['think_max']} |")

    # 5. latency (contended trials excluded)
    contended = set()
    if args.contended_ids:
        contended |= {tuple(l.split()) for l in open(args.contended_ids) if l.strip()}
    if args.procs and args.gpu_uuid:
        wins = contended_from_procs(args.procs, set(args.pid), args.gpu_uuid)
        for r in rows:
            if "wall_start" in r:
                s = datetime.fromisoformat(r["wall_start"]).timestamp()
                e = datetime.fromisoformat(r["wall_end"]).timestamp()
                if any(s <= w1 and e >= w0 for w0, w1 in wins):
                    contended.add((r["arm"], r["path"]))
    out["contended_trials"] = sorted(f"{a} {p}" for a, p in contended)
    print(f"\n## 5. Latency (excluding {len(contended)} contended trials)\n")
    print("| arm | subset | n | median s | p90 s |")
    print("|---|---|---|---|---|")
    lat = {}
    for a in present:
        for name, qs in subsets.items():
            v = [arms[a][q]["latency_ms"] / 1000 for q in qs if q in arms[a] and (a, q) not in contended
                 and not arms[a][q].get("batched")]  # batched trials carry batch wall time, not latency
            if not v:
                continue
            lat[(a, name)] = dict(n=len(v), median_s=round(pct(v, 50), 3), p90_s=round(pct(v, 90), 3))
            print(f"| {a} | {name} | {len(v)} | {pct(v,50):.2f} | {pct(v,90):.2f} |")
    out["latency"] = {f"{a}|{s}": v for (a, s), v in lat.items()}
    nb = {a: sum(bool(t.get("batched")) for t in arms[a].values()) for a in present}
    out["latency"]["batched_trials_excluded"] = nb
    if any(nb.values()):
        print(f"- batched trials excluded from latency (single-stream only): {nb}")
    for name in subsets:
        for ref in ("I", "C"):
            if ("D", name) in lat and (ref, name) in lat:
                r = lat[("D", name)]["median_s"] / lat[(ref, name)]["median_s"]
                out["latency"][f"D/{ref}|{name}"] = round(r, 1)
                print(f"- D/{ref} median ratio, {name}: {r:.1f}× (same hardware, h100nvl)")

    # 6. 4B vs StudyS1 committed values
    print("\n## 6. 4B arms vs StudyS1 (flash-only values, not re-verifiable here)\n")
    out["vs_S1"] = {}
    st = "stratum (both categories)"
    for a in ("I", "T"):
        if (a, st) in acc:
            d = acc[(a, st)]["acc"] - S1[a]
            out["vs_S1"][a] = dict(here=acc[(a, st)]["acc"], s1=S1[a], diff_pp=round(d, 1),
                                   material=abs(d) > MATERIAL_PP)
            print(f"- {a}: {acc[(a, st)]['acc']}% here vs S1 {S1[a]}% ({d:+.1f} pp)"
                  f"{'  ← MATERIAL DISCREPANCY (finding)' if abs(d) > MATERIAL_PP else ''}")
    tr = out["decomposition"].get(f"{st}|T−I thinking @4B (net_rescue 4B)")
    if tr:
        d = tr["diff_pp"] - S1["net_rescue"]
        out["vs_S1"]["net_rescue_4B"] = dict(here=tr["diff_pp"], here_ci=tr["ci_pp"], s1=S1["net_rescue"],
                                             s1_ci=S1["net_rescue_ci"], diff_pp=round(d, 2),
                                             material=abs(d) > MATERIAL_PP)
        print(f"- 4B net_rescue (T−I): {tr['diff_pp']:+.2f} pp {tr['ci_pp']} here vs S1 +1.00 [-4.74, +6.74] "
              f"({d:+.2f} pp){'  ← MATERIAL DISCREPANCY (finding)' if abs(d) > MATERIAL_PP else ''}")

    # 7. cross-study terms vs StudyS1 aggregates (two-arm design): unpaired, NOT in the verdict
    if "I" not in arms and "T" not in arms:
        print("\n## 7. CROSS-STUDY terms vs StudyS1 4B aggregates (unpaired Newcombe 95% CI; not in verdict)\n")
        print("| term | 32B acc % (n) | S1 4B acc % (n=401) | diff pp | 95% unpaired CI |")
        print("|---|---|---|---|---|")
        out["cross_study"] = {}
        for label, x, y in (("C−I size @instruct", "C", "I"), ("D−T size @thinking", "D", "T"),
                            ("D−I total device→cloud", "D", "I")):
            if (x, st) in acc:
                ax = acc[(x, st)]
                lo, hi = newcombe(ax["acc"] / 100, ax["n"], S1[y] / 100, S1_N)
                d = ax["acc"] - S1[y]
                out["cross_study"][label] = dict(acc_32b=ax["acc"], n_32b=ax["n"], acc_s1=S1[y], diff_pp=round(d, 1),
                                                 ci_pp=[round(100 * lo, 1), round(100 * hi, 1)])
                print(f"| {label} | {ax['acc']} ({ax['n']}) | {S1[y]} | {d:+.1f} | [{100*lo:+.1f}, {100*hi:+.1f}] |")
        print(f"- T−I thinking @4B (StudyS1's own value): +1.00 pp [-4.74, +6.74]")
        print("- CROSS-STUDY: different host/stack, S1 prompt and exact question set unverifiable; "
              "if the 32B n is a prefix of the fixed order it is SDJ-heavy vs S1's 401.")

    out["_provenance"] = stamp(script="study_s2_analyse.py", model="qwen3vl_4b_32b", device="h100nvl",
                               n=len(allq), seed=0, args=args)
    Path(args.out).write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
