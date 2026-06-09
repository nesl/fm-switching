"""Pareto scatter: mean cycle latency vs. mean continuous compute cost.

Primary compute-axis: mean_compute_tokens_per_cycle (token-equivalents
summed across tiers).
Secondary compute-axis: mean_compute_seconds_per_cycle.

The four LH variants are highlighted; other policies are background
markers. Each point is one (policy, scenario) cell — 240 points total.
Per-policy centroids overlaid.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "simulator" / "results"
OUT = Path(__file__).parent

SRC = SIM / "comparison_lh_variants.json"
rows = json.loads(SRC.read_text())

LH_VARIANTS = ["OverlapMigration", "SpeculativeLH", "RoutedSyncLH", "HotStandbyLH"]
OTHERS = [p for p in {r["policy"] for r in rows} if p not in LH_VARIANTS]

LH_COLOR = {
    "OverlapMigration": "#F59E0B",   # amber
    "SpeculativeLH":    "#DC2626",   # red
    "RoutedSyncLH":     "#2563EB",   # blue
    "HotStandbyLH":     "#7C3AED",   # purple
}
LH_MARKER = {"OverlapMigration": "v", "SpeculativeLH": "o",
             "RoutedSyncLH": "s",     "HotStandbyLH": "D"}


def scatter_axis(rows, x_field, x_label, fname, log_x=False):
    fig, ax = plt.subplots(figsize=(10, 6.5))

    # Background: all non-LH policies in light gray
    for p in OTHERS:
        pts = [r for r in rows if r["policy"] == p]
        xs = [r[x_field] for r in pts]
        ys = [r["mean_cycle_latency_s"] for r in pts]
        ax.scatter(xs, ys, s=24, color="#cbd5e1", alpha=0.6,
                   edgecolors="none", zorder=1)
    # Centroids for non-LH policies
    for p in OTHERS:
        pts = [r for r in rows if r["policy"] == p]
        if not pts:
            continue
        xs = np.mean([r[x_field] for r in pts])
        ys = np.mean([r["mean_cycle_latency_s"] for r in pts])
        ax.scatter(xs, ys, s=110, color="#475569", edgecolors="black",
                    linewidths=0.8, marker="x", zorder=3)
        ax.annotate(p, (xs, ys), fontsize=8, color="#334155",
                     xytext=(6, 4), textcoords="offset points")

    # Foreground: LH variants in distinct colours/markers
    for p in LH_VARIANTS:
        pts = [r for r in rows if r["policy"] == p]
        if not pts:
            continue
        xs = [r[x_field] for r in pts]
        ys = [r["mean_cycle_latency_s"] for r in pts]
        ax.scatter(xs, ys, s=70, color=LH_COLOR[p], marker=LH_MARKER[p],
                    alpha=0.85, edgecolors="black", linewidths=0.6,
                    label=p, zorder=4)
        # Centroid for the LH variant
        cx, cy = np.mean(xs), np.mean(ys)
        ax.scatter([cx], [cy], s=260, color=LH_COLOR[p], marker=LH_MARKER[p],
                    edgecolors="black", linewidths=1.6, zorder=5)
        ax.annotate(f"  {p} ⌀", (cx, cy), fontsize=10, fontweight="bold",
                     color=LH_COLOR[p], xytext=(8, 0), textcoords="offset points")

    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel("Mean cycle latency (s)", fontsize=12)
    ax.set_title("Pareto: latency vs continuous compute cost\n"
                  "(each point = one policy × scenario cell; bold marker = policy centroid)",
                  fontsize=13)
    if log_x:
        ax.set_xscale("log")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=10, frameon=True)
    fig.tight_layout()
    out_png = OUT / fname
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    fig.savefig(out_png.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {out_png}")
    print(f"  ✓ {out_png.with_suffix('.pdf')}")


scatter_axis(rows, "mean_compute_tokens_per_cycle",
              "Mean compute tokens per cycle (across tiers)",
              "pareto_lh_tokens.png")
scatter_axis(rows, "mean_compute_seconds_per_cycle",
              "Mean compute seconds per cycle (across tiers)",
              "pareto_lh_seconds.png")
