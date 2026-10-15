#!/usr/bin/env python3
"""Study S1 — the five pre-registered analyses for the competent-category stratum.

Design: reports/study_s0_plan.md §StudyS1 AMENDMENT (pre-registered before the run).
Condition 3 rule: Gate 1 PASSES iff net_rescue > 5pp AND the paired 95% CI excludes 0.
"""

import json
import math
import statistics as st
from collections import defaultdict

Z = 1.959964
CATS = ["spatial_distance_judgement", "robotic_trajectory_selection"]
SRC = "results/mvrobobench/study_s1/study_s1_trials.jsonl"


def wilson(k, n):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (c - h) * 100, (c + h) * 100


def paired(T, Im):
    n = len(T)
    b = sum(1 for t in T if t["correct"] and not Im[t["qid_path"]]["correct"])
    c = sum(1 for t in T if not t["correct"] and Im[t["qid_path"]]["correct"])
    net = (b - c) / n
    se = math.sqrt(b + c) / n if (b + c) else 0.0
    return b, c, net * 100, (net - Z * se) * 100, (net + Z * se) * 100


def cluster_ci(T, Im, cats):
    """Net_rescue CI clustered by category (the stratum has 2 clusters).

    With only 2 clusters a cluster-robust CI is unreliable; report the
    per-cluster nets so the reader can see the between-cluster spread
    directly rather than trusting a 2-cluster sandwich estimator.
    """
    out = {}
    for cat in cats:
        sub = [t for t in T if t["category"] == cat]
        out[cat] = paired(sub, Im)[2]
    return out


def main():
    ts = [json.loads(l) for l in open(SRC)]
    Im = {t["qid_path"]: t for t in ts if t["arm"] == "I"}
    T = [t for t in ts if t["arm"] == "T" and t["category"] in CATS]
    I = [Im[t["qid_path"]] for t in T]
    n = len(T)

    print("=" * 74)
    print("StudyS1 — Gate 1 tested on a POST-HOC stratum (competent categories)")
    print("=" * 74)

    # --- 4. VERDICT FIRST ---
    b, c, net, lo, hi = paired(T, Im)
    passes = net > 5 and lo > 0
    print(f"\n### VERDICT (Condition 3)")
    print(f"net_rescue = {net:+.2f}pp   95% CI [{lo:+.2f}, {hi:+.2f}]   n={n}")
    print(f"Rule: PASSES iff net > 5pp AND CI excludes 0.")
    print(f"  net > 5pp?        {'YES' if net > 5 else 'NO'}  ({net:+.2f}pp)")
    print(f"  CI excludes 0?    {'YES' if lo > 0 else 'NO'}  (lower bound {lo:+.2f}pp)")
    print(f"\n  >>> {'Gate 1 PASSES' if passes else 'Neither - branch is empty. STOP.'}")

    # --- 1. Accuracy per arm ---
    print(f"\n### 1. Accuracy per arm (chance baseline = 20.0%)")
    for label, arm in (("arm I (reused)", I), ("arm T", T)):
        k = sum(x["correct"] for x in arm)
        l, h = wilson(k, n)
        print(f"  {label:<16} {k}/{n} = {k/n*100:5.1f}%  95% CI [{l:.1f}, {h:.1f}]")
    kI = sum(x["correct"] for x in I); kT = sum(x["correct"] for x in T)
    print(f"  unpaired difference: {(kT-kI)/n*100:+.2f}pp "
          f"(descriptive only; the paired net above is the test)")

    # --- 2. Paired discordance ---
    print(f"\n### 2. Paired discordance")
    print(f"  b (I wrong, T correct) = {b}   ({b/n*100:.1f}%)")
    print(f"  c (I correct, T wrong) = {c}   ({c/n*100:.1f}%)")
    print(f"  discordance (b+c)      = {b+c} ({(b+c)/n*100:.1f}%)")
    print(f"  net_rescue = (b-c)/n   = {net:+.2f}pp  95% CI [{lo:+.2f}, {hi:+.2f}]")
    chi = (abs(b - c) - 1) ** 2 / (b + c) if (b + c) else 0
    print(f"  McNemar chi2 (continuity-corrected) = {chi:.3f}  (crit 3.841 at a=0.05)")
    print(f"  per-cluster nets: " +
          ", ".join(f"{k.split('_')[-1]}={v:+.1f}pp"
                    for k, v in cluster_ci(T, Im, CATS).items()))
    print(f"  (2 clusters only — per-cluster nets shown instead of a 2-cluster")
    print(f"   sandwich estimator, which would be unreliable)")

    # --- 3. Per-category, descriptive ---
    print(f"\n### 3. Per-category breakdown  [DESCRIPTIVE, NOT CONFIRMATORY]")
    print(f"  {'category':<30} {'n':>4} {'arm I':>7} {'arm T':>7} {'b':>4} {'c':>4} {'net':>8} {'95% CI':>18}")
    for cat in CATS:
        sub = [t for t in T if t["category"] == cat]
        subI = [Im[t["qid_path"]] for t in sub]
        bb, cc, nn, ll, hh = paired(sub, Im)
        print(f"  {cat:<30} {len(sub):>4} "
              f"{sum(x['correct'] for x in subI)/len(sub)*100:>6.1f}% "
              f"{sum(x['correct'] for x in sub)/len(sub)*100:>6.1f}% "
              f"{bb:>4} {cc:>4} {nn:>+7.1f}pp [{ll:+6.1f},{hh:+6.1f}]")

    # --- 5. Think tokens and latency ---
    print(f"\n### 5. Think-token distribution and latency (cost side)")
    for cat in CATS + ["POOLED"]:
        sub = T if cat == "POOLED" else [t for t in T if t["category"] == cat]
        th = [t["n_think"] for t in sub]
        la = [t["lat_ms"] / 1000 for t in sub]
        laI = [Im[t["qid_path"]]["lat_ms"] / 1000 for t in sub]
        print(f"  {cat:<30} think med={st.median(th):>6.0f} "
              f"IQR=[{st.quantiles(th,n=4)[0]:.0f},{st.quantiles(th,n=4)[2]:.0f}] "
              f"max={max(th):>5} | lat_T med={st.median(la):>5.1f}s "
              f"lat_I med={st.median(laI):>4.2f}s "
              f"ratio={st.median(la)/st.median(laI):>5.1f}x")
    total_h = sum(t["lat_ms"] for t in T) / 1000 / 3600
    print(f"  arm T total compute: {total_h:.2f}h for {n} questions")

    # --- Sanity checks ---
    print(f"\n### Sanity checks")
    print(f"  arm I trials REUSED from the completed arm I sweep in {SRC}")
    print(f"    (not re-run; {len(I)}/{n} matched by qid_path)")
    tc = sum(1 for t in T if t["think_closed"])
    bh = sum(t["budget_hit"] for t in T)
    print(f"  think_closed: {tc}/{n} ({tc/n*100:.1f}%)   "
          f"NOT closed: {n-tc} ({(n-tc)/n*100:.1f}%)")
    print(f"  budget_hit:   {bh}/{n} ({bh/n*100:.1f}%)")
    px = sum(1 for t in T if t["pred"] == "X")
    pxI = sum(1 for t in I if t["pred"] == "X")
    print(f"  parse failures (pred='X'): arm T {px}, arm I {pxI} "
          f"— reported separately, not silently scored wrong")
    trunc_right = sum(1 for t in T
                      if not t["think_closed"] and t["pred"] == t["answer"])
    print(f"  truncated traces whose emitted letter was nonetheless correct: "
          f"{trunc_right}")
    print(f"    (scored 0 under the deployment-realistic convention, as in StudyP)")
    if trunc_right:
        alt = (sum(t['correct'] for t in T) + trunc_right) / n * 100
        print(f"    arm T accuracy if these were scored correct: {alt:.1f}% "
              f"(vs {sum(t['correct'] for t in T)/n*100:.1f}% as scored)")


if __name__ == "__main__":
    main()
