#!/usr/bin/env python3
"""Study S0 Audit 3b — AUROC power for the Gate 2 within-block static-predictor test.

Added when the Gate 2 design was extended to three static-predictor variants
(S1 text+metadata, S2 image-only, S3 combined). The pre-registered rule turns on
whether AUROC >= 0.70 is distinguishable from chance at the available block sizes,
and whether an observed near-chance AUROC can RULE OUT 0.70.

Hanley-McNeil (1982) standard error for a single AUROC.
"""

import json
import math
from pathlib import Path

Z = 1.959964


def hanley_mcneil_se(a, n_pos, n_neg):
    q1 = a / (2 - a)
    q2 = 2 * a * a / (1 + a)
    num = (a * (1 - a)
           + (n_pos - 1) * (q1 - a * a)
           + (n_neg - 1) * (q2 - a * a))
    return math.sqrt(num / (n_pos * n_neg))


def ci(a, n_pos, n_neg):
    se = hanley_mcneil_se(a, n_pos, n_neg)
    return a - Z * se, a + Z * se


def main():
    summary = json.load(open("results/erqa/study_s0/audit1_summary.json"))
    homog = summary["homogeneity"]

    blocks = {c: h["largest_block"] for c, h in homog.items()
              if h["verdict"] in ("IDEAL", "USABLE")}
    pooled_n = sum(blocks.values())
    primary_n = max(blocks.values())

    print("=== AUDIT 3b — Gate 2 AUROC POWER ===\n")
    print("Hanley-McNeil SE; alpha=0.05 two-tailed.")
    print("Rescue-rate prior from StudyK discordance: P(I wrong, T correct) = 59/400 = 0.1475\n")

    RESCUE = 59 / 400

    scopes = [("primary block (spatial_viewpoint_identification)", primary_n),
              ("pooled IDEAL+USABLE blocks", pooled_n)]

    print("--- Can an observed AUROC of 0.70 be distinguished from chance? ---")
    print(f"  {'scope':<46} {'n':>5} {'pos':>5} {'AUROC 0.70 95% CI':>22} {'>0.5?':>7}")
    for label, n in scopes:
        n_pos = round(n * RESCUE)
        n_neg = n - n_pos
        lo, hi = ci(0.70, n_pos, n_neg)
        print(f"  {label:<46} {n:>5} {n_pos:>5} "
              f"{'['+format(lo,'.3f')+', '+format(hi,'.3f')+']':>22} "
              f"{'YES' if lo > 0.5 else 'NO':>7}")

    print("\n--- Can a near-chance observation RULE OUT AUROC >= 0.70? ---")
    print("  (Gate 2 is SURVIVED only if the upper CI bound falls below 0.70)")
    print(f"  {'scope':<46} {'obs A':>6} {'95% CI upper':>13} {'rules out 0.70?':>16}")
    for label, n in scopes:
        n_pos = round(n * RESCUE)
        n_neg = n - n_pos
        for obs in (0.50, 0.55, 0.60):
            lo, hi = ci(obs, n_pos, n_neg)
            print(f"  {label:<46} {obs:>6.2f} {hi:>13.3f} "
                  f"{'YES' if hi < 0.70 else 'no':>16}")

    print("\n--- Largest observed AUROC still consistent with 'survived' ---")
    for label, n in scopes:
        n_pos = round(n * RESCUE)
        n_neg = n - n_pos
        best = None
        a = 0.50
        while a < 0.70:
            _, hi = ci(a, n_pos, n_neg)
            if hi < 0.70:
                best = a
            a += 0.005
        print(f"  {label:<46} max obs AUROC with CI upper < 0.70: "
              f"{best:.3f}" if best else f"  {label:<46} none")

    out = Path("results/erqa/study_s0/audit3b_auroc_power.json")
    json.dump({
        "rescue_rate_prior": RESCUE,
        "blocks": blocks,
        "pooled_n": pooled_n,
        "primary_block_n": primary_n,
        "auroc_070_ci": {
            label: list(ci(0.70, round(n * RESCUE), n - round(n * RESCUE)))
            for label, n in scopes},
    }, open(out, "w"), indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
