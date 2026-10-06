#!/usr/bin/env python3
"""Study S0 Audit 3 — power calculation.

McNemar paired power for net_rescue = P(I wrong, T correct) - P(I correct, T wrong)
(Correction 1), plus power for the Gate 2 within-block analysis identified in
Audit 1.

Discordance prior taken from StudyK on ERQA: b=59, c=49 of 400
=> p_disc = 0.270, observed net = 0.025.
"""

import json
import math
from pathlib import Path

Z_ALPHA = 1.959964  # two-tailed alpha=0.05
Z_BETA = 0.841621   # power=0.80
K = (Z_ALPHA + Z_BETA) ** 2

# StudyK ERQA discordance
B, C, N_ERQA = 59, 49, 400
P_DISC = (B + C) / N_ERQA
NET_ERQA = (B - C) / N_ERQA


def n_for_net(delta, p_disc=P_DISC):
    """n needed to detect a net paired difference `delta` at 80% power."""
    return K * p_disc / delta ** 2


def mdi_net(n, p_disc=P_DISC):
    """Minimum detectable net difference at given n."""
    return math.sqrt(K * p_disc / n)


def n_for_interaction(delta, p_disc=P_DISC):
    """n PER STRATUM to detect a difference-of-deltas (variance doubles)."""
    return K * 2 * p_disc / delta ** 2


def mdi_interaction(n_per_stratum, p_disc=P_DISC):
    return math.sqrt(K * 2 * p_disc / n_per_stratum)


def wilson_halfwidth(p, n):
    z = Z_ALPHA
    return z * math.sqrt(p * (1 - p) / n)


def main():
    summary = json.load(open("results/erqa/study_s0/audit1_summary.json"))
    by_cat = summary["by_category"]
    n_total = summary["n_total"]

    print("=== AUDIT 3 — POWER CALCULATION ===\n")
    print(f"Discordance prior (StudyK/ERQA): b={B}, c={C}, n={N_ERQA}")
    print(f"  p_discordant = {P_DISC:.3f}   observed net = {NET_ERQA*100:+.1f}pp")
    print(f"  alpha=0.05 two-tailed, power=0.80\n")

    print("--- CORRECTION 1: n required to detect net_rescue ---")
    print(f"  {'target net':>11} {'n required':>12}")
    for d in (0.05, 0.10, 0.15):
        print(f"  {d*100:>10.0f}pp {n_for_net(d):>12.0f}")

    print(f"\n--- MDI for net_rescue at available n ---")
    print(f"  {'scope':<36} {'n':>6} {'MDI':>9}")
    print(f"  {'full dataset':<36} {n_total:>6} {mdi_net(n_total)*100:>8.1f}pp")
    for cat in sorted(by_cat):
        n = by_cat[cat]
        print(f"  {cat:<36} {n:>6} {mdi_net(n)*100:>8.1f}pp")

    print(f"\n--- Interaction (between-category contrast) ---")
    print("  NOTE (Audit 1): direct/compositional is determined by category, so the")
    print("  planned interaction is a between-category comparison, not an orthogonal")
    print("  factor. n below is PER STRATUM where a stratum = a set of categories.")
    print(f"  {'target interaction':>19} {'n per stratum':>15}")
    for d in (0.05, 0.10, 0.15):
        print(f"  {d*100:>18.0f}pp {n_for_interaction(d):>15.0f}")

    typical = min(by_cat.values())
    largest = max(by_cat.values())
    print(f"\n  MDI (interaction) at smallest category n={typical}: "
          f"{mdi_interaction(typical)*100:.1f}pp")
    print(f"  MDI (interaction) at largest  category n={largest}: "
          f"{mdi_interaction(largest)*100:.1f}pp")
    half = n_total // 2
    print(f"  MDI (interaction) at half-dataset strata n={half}: "
          f"{mdi_interaction(half)*100:.1f}pp")

    print(f"\n--- GATE 2 within-block power ---")
    print("  Within a statically-identical block, any static predictor scores every")
    print("  member identically => within-block AUROC = 0.5 by construction.")
    print("  The question is whether the rescue population in the block is large")
    print("  enough to estimate. Precision on the within-block rescue rate:\n")
    homog = summary["homogeneity"]
    ranked = sorted(homog.items(), key=lambda kv: -kv[1]["largest_block"])
    print(f"  {'category':<36} {'block n':>8} {'±95% CI on rescue rate':>24}")
    for cat, h in ranked[:5]:
        nb = h["largest_block"]
        hw15 = wilson_halfwidth(0.15, nb) * 100
        print(f"  {cat:<36} {nb:>8} {'±'+format(hw15,'.1f')+'pp (if rate=15%)':>24}")

    blocks = [h["largest_block"] for h in homog.values() if h["verdict"] in ("IDEAL", "USABLE")]
    pooled = sum(blocks)
    print(f"\n  Pooled IDEAL+USABLE blocks: n={pooled} across {len(blocks)} categories")
    print(f"    ±95% CI on rescue rate (if 15%): "
          f"±{wilson_halfwidth(0.15, pooled)*100:.1f}pp")
    print(f"    MDI for net_rescue within pooled blocks: {mdi_net(pooled)*100:.1f}pp")

    out = Path("results/erqa/study_s0/audit3_power.json")
    json.dump({
        "prior": {"b": B, "c": C, "n": N_ERQA, "p_disc": P_DISC, "net": NET_ERQA},
        "n_for_net": {f"{int(d*100)}pp": n_for_net(d) for d in (0.05, 0.10, 0.15)},
        "mdi_net_full_dataset": mdi_net(n_total),
        "mdi_net_by_category": {c: mdi_net(n) for c, n in by_cat.items()},
        "n_for_interaction_per_stratum": {
            f"{int(d*100)}pp": n_for_interaction(d) for d in (0.05, 0.10, 0.15)},
        "mdi_interaction_half_dataset": mdi_interaction(half),
        "gate2_pooled_block_n": pooled,
        "gate2_pooled_mdi_net": mdi_net(pooled),
    }, open(out, "w"), indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
