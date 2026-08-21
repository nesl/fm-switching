"""
E24c figures:
  figures/orchestration/e24c_gap_vs_best_decomposed_drift0.pdf
  figures/orchestration/e24c_gap_vs_best_decomposed_drift20.pdf
  figures/orchestration/e24c_refresh_cost.pdf
"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

ROOT = Path(__file__).parent.parent.parent
RESULT_DIR = ROOT / "results" / "orchestration" / "e24c_coupling"
FIG_DIR = ROOT / "figures" / "orchestration"
FIG_DIR.mkdir(parents=True, exist_ok=True)

DECOMP_POLICIES = [
    "fidelity_first", "fidelity_first_lifecycle",
    "placement_first", "cache_value", "libra_style", "handover_sched",
]

CAPS = [0.25, 0.50, 0.75]
MOBS = ["moderate", "high"]
REGS = ["mixed", "mostly_dense"]
TAUS = [0.90, 0.95]
DRIFTS = [0, 20]


def load_all():
    cells = {}
    for cell_dir in RESULT_DIR.iterdir():
        cj = cell_dir / "cell.json"
        if not cj.exists():
            continue
        d = json.loads(cj.read_text())
        cfg = d["config"]
        key = (cfg["cap_frac"], cfg["mobility"], cfg["regime_mix"],
               cfg["tau"], cfg["drift_rate"])
        cells[key] = d
    return cells


def get_gap(d):
    pols = d["policies"]
    joint = pols["joint"]["slo_mean"]
    bd = max(pols.get(p, {}).get("slo_mean", 0.0) for p in DECOMP_POLICIES)
    return joint - bd


def plot_gap_panels(cells, drift, fname):
    """
    2×3 grid: rows = regime (mixed, mostly_dense), cols = tau (0.90, 0.95) × L-band proxy (n/a here).
    Simplified: rows = tau, cols = capacity; x = mobility, color = gap.
    Actually: facets by tau (2 rows) and regime (2 cols) = 4 panels.
    Within each panel: x = capacity (3 levels), grouped by mobility (2 bars).
    """
    fig, axes = plt.subplots(2, 2, figsize=(9, 6))
    fig.suptitle(
        f"E24c: joint SLO − best-decomposed SLO  (drift={drift}, n=100 epochs, 15 sessions)",
        fontsize=10)

    vmin, vmax = -0.20, 0.05
    cmap = plt.cm.RdYlGn
    norm = mcolors.TwoSlopeNorm(vcenter=0, vmin=vmin, vmax=vmax)

    for row, tau in enumerate(TAUS):
        for col, reg in enumerate(REGS):
            ax = axes[row][col]
            ax.set_title(f"tau={tau}, {reg}", fontsize=8)
            ax.axhline(0, color="k", lw=0.8, ls="--")
            ax.axhline(-0.05, color="salmon", lw=0.8, ls=":")
            ax.axhline(0.05, color="steelblue", lw=0.8, ls=":")

            xs = np.arange(len(CAPS))
            width = 0.35
            for mi, mob in enumerate(MOBS):
                gaps = []
                for cap in CAPS:
                    key = (cap, mob, reg, tau, drift)
                    d = cells.get(key)
                    gaps.append(get_gap(d) if d else 0.0)
                offset = (mi - 0.5) * width
                bars = ax.bar(xs + offset, gaps, width, label=mob,
                              color=[cmap(norm(g)) for g in gaps], edgecolor="k", linewidth=0.5)

            ax.set_xticks(xs)
            ax.set_xticklabels([f"{int(c*100)}%" for c in CAPS], fontsize=7)
            ax.set_xlabel("Capacity fraction", fontsize=7)
            ax.set_ylabel("Gap (joint − best-decomp) SLO", fontsize=7)
            ax.set_ylim(vmin - 0.02, vmax + 0.02)
            ax.legend(fontsize=6, loc="lower right")
            ax.tick_params(labelsize=7)

    fig.tight_layout()
    out = FIG_DIR / fname
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=150, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


def plot_refresh_cost(cells, fname):
    """Total refresh cost by policy for discriminating cells (tau=0.95, mixed)."""
    target_keys = [
        (cap, mob, "mixed", 0.95, 0)
        for cap in CAPS for mob in MOBS
    ]

    policy_order = [
        "joint", "fidelity_first", "fidelity_first_lifecycle",
        "placement_first", "cache_value",
    ]
    labels = [
        "joint", "ff (weak)", "ff_lifecycle", "placement_first", "cache_value",
    ]

    fig, axes = plt.subplots(2, 3, figsize=(11, 6), sharey=False)
    fig.suptitle("E24c: Total refresh cost per policy (tau=0.95, mixed regime, drift=0)",
                 fontsize=10)

    for idx, key in enumerate(target_keys):
        cap, mob = key[0], key[1]
        ax = axes[idx // 3][idx % 3]
        d = cells.get(key)
        if d is None:
            ax.set_visible(False)
            continue

        pols = d["policies"]
        costs = []
        for p in policy_order:
            c = pols.get(p, {}).get("total_refresh_cost_s", 0)
            costs.append(min(c, 1e5) if c != float("inf") else 1e5)

        xs = np.arange(len(policy_order))
        bars = ax.bar(xs, costs, color=["#2196F3","#FF9800","#4CAF50","#9C27B0","#F44336"])
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=30, fontsize=7, ha="right")
        ax.set_ylabel("Total refresh cost (s)", fontsize=7)
        ax.set_title(f"cap={int(cap*100)}%, {mob}", fontsize=8)
        ax.tick_params(labelsize=7)
        # Add slo annotation
        for xi, p in enumerate(policy_order):
            slo = pols.get(p, {}).get("slo_mean", 0)
            ax.text(xi, costs[xi] + 50, f"{slo:.2f}", ha="center", va="bottom", fontsize=6)

    fig.tight_layout()
    out = FIG_DIR / fname
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=150, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


def main():
    cells = load_all()
    plot_gap_panels(cells, drift=0,  fname="e24c_gap_vs_best_decomposed_drift0.pdf")
    plot_gap_panels(cells, drift=20, fname="e24c_gap_vs_best_decomposed_drift20.pdf")
    plot_refresh_cost(cells, fname="e24c_refresh_cost.pdf")
    print("Done.")


if __name__ == "__main__":
    main()
