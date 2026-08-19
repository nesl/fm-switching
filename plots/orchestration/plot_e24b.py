"""
E24b phase diagram plots.

Generates:
  figures/orchestration/e24b_phase_diagram_vs_fidelity.pdf
    capacity × mobility, one panel per regime_mix
    cell = joint improvement over fidelity_only (the stronger decomposed baseline)

  figures/orchestration/e24b_phase_diagram_vs_cv.pdf
    same layout but vs cache_value

  figures/orchestration/e24b_slo_summary.pdf
    mean SLO by policy per regime_mix (averaged over all dims)
"""

import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

REPO = Path(__file__).parent.parent.parent
OUT_DIR = REPO / "results" / "orchestration" / "e24b_coupling"
FIG_DIR = REPO / "figures" / "orchestration"
FIG_DIR.mkdir(parents=True, exist_ok=True)

CAPACITY_PCTS  = [10, 25, 50, 75, 100]
MOBILITY_LEVELS = ["static", "predictable", "moderate", "high"]
REGIME_MIXES   = ["mostly_compressible", "mixed", "mostly_dense"]
TAUS           = [0.80, 0.90, 0.95]
DRIFT_RATES    = [0, 20]


def load_all_cells():
    """Load all cell.json files; average over tau and drift."""
    # Structure: cells[(cap, mob, regime)] → {policy: [slo_fractions by seed]}
    from collections import defaultdict
    data = defaultdict(lambda: defaultdict(list))  # (cap,mob,regime) → policy → [slo]

    for cell_dir in OUT_DIR.iterdir():
        cell_file = cell_dir / "cell.json"
        if not cell_file.exists():
            continue
        with open(cell_file) as f:
            cell = json.load(f)
        cfg = cell["config"]
        key = (cfg["capacity_pct"], cfg["mobility_level"], cfg["regime_mix"])
        for pname, pr in cell["policies"].items():
            m = pr.get("mean_slo")
            if m is not None:
                data[key][pname].append(m)

    # Average over tau and drift per (cap, mob, regime)
    result = {}
    for key, pols in data.items():
        result[key] = {p: np.mean(vals) for p, vals in pols.items()}
    return result


def make_heatmap(data, comparator: str, title_suffix: str, out_path: Path):
    """
    3-panel heatmap: capacity (y) × mobility (x), one panel per regime_mix.
    Cell value = joint SLO - comparator SLO (signed, in percentage points).
    """
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), constrained_layout=True)
    fig.suptitle(f"E24b: joint improvement over {comparator} (pp)\n"
                 f"(averaged over tau ∈ {{0.80,0.90,0.95}} × drift ∈ {{0,20}})",
                 fontsize=11)

    vmax = 20  # pp
    vmin = -vmax
    cmap = plt.cm.RdBu_r
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)

    for ax, regime in zip(axes, REGIME_MIXES):
        grid = np.zeros((len(CAPACITY_PCTS), len(MOBILITY_LEVELS)))
        for i, cap in enumerate(CAPACITY_PCTS):
            for j, mob in enumerate(MOBILITY_LEVELS):
                key = (cap, mob, regime)
                if key in data:
                    joint = data[key].get("joint", None)
                    comp = data[key].get(comparator, None)
                    if joint is not None and comp is not None:
                        grid[i, j] = (joint - comp) * 100  # pp

        im = ax.imshow(grid, cmap=cmap, norm=norm, aspect="auto",
                       origin="lower")

        # Annotate cells
        for i in range(len(CAPACITY_PCTS)):
            for j in range(len(MOBILITY_LEVELS)):
                val = grid[i, j]
                color = "white" if abs(val) > 8 else "black"
                ax.text(j, i, f"{val:+.1f}", ha="center", va="center",
                        fontsize=8, color=color, fontweight="bold")

        ax.set_xticks(range(len(MOBILITY_LEVELS)))
        ax.set_xticklabels(MOBILITY_LEVELS, rotation=30, ha="right", fontsize=9)
        ax.set_yticks(range(len(CAPACITY_PCTS)))
        ax.set_yticklabels([f"{c}%" for c in CAPACITY_PCTS], fontsize=9)
        ax.set_xlabel("Mobility level", fontsize=9)
        ax.set_ylabel("Capacity (% of cheapest-sufficient ref.)", fontsize=9)
        ax.set_title(regime.replace("_", " "), fontsize=10)

        plt.colorbar(im, ax=ax, label="pp improvement")

    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def make_summary_bar(data, out_path: Path):
    """Mean SLO by policy × regime_mix."""
    policies = ["reactive", "replication", "placement_only", "fidelity_only",
                "cache_value", "joint", "oracle", "libra_style", "handover_sched"]
    colors = {
        "reactive": "#d62728", "replication": "#e377c2",
        "placement_only": "#ff7f0e", "fidelity_only": "#1f77b4",
        "cache_value": "#bcbd22", "joint": "#2ca02c", "oracle": "#9467bd",
        "libra_style": "#8c564b", "handover_sched": "#7f7f7f",
    }

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    fig.suptitle("E24b: Mean SLO fraction by policy\n"
                 "(averaged over cap × mobility × tau × drift)", fontsize=11)

    for ax, regime in zip(axes, REGIME_MIXES):
        # Aggregate over all (cap, mob) for this regime
        pol_means = {p: [] for p in policies}
        for key, pols in data.items():
            if key[2] == regime:
                for p in policies:
                    v = pols.get(p)
                    if v is not None:
                        pol_means[p].append(v)

        names = []
        vals = []
        for p in policies:
            m = pol_means[p]
            if m:
                names.append(p.replace("_", "\n"))
                vals.append(np.mean(m))

        bars = ax.bar(range(len(names)), vals,
                      color=[colors.get(p.replace("\n", "_"), "#aaaaaa") for p in names])
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=7)
        ax.set_ylim(0, 1)
        ax.set_ylabel("Mean SLO fraction", fontsize=9)
        ax.set_title(regime.replace("_", " "), fontsize=10)
        ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8)

        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=7)

    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def main():
    print("Loading cells...")
    data = load_all_cells()
    print(f"Loaded {len(data)} (cap, mob, regime) combinations")

    make_heatmap(data, "fidelity_only",
                 "fidelity_only",
                 FIG_DIR / "e24b_phase_diagram_vs_fidelity.pdf")

    make_heatmap(data, "cache_value",
                 "cache_value",
                 FIG_DIR / "e24b_phase_diagram_vs_cv.pdf")

    make_summary_bar(data, FIG_DIR / "e24b_slo_summary.pdf")

    # Print per-band SLO for tau=0.90, drift=0 (core result)
    print("\nPer-L-band SLO: tau=0.90, drift=0, cap=50%, moderate, mixed")
    target = OUT_DIR / "50pct_moderate_mixed_tau90_drift0"
    if (target / "cell.json").exists():
        with open(target / "cell.json") as f:
            cell = json.load(f)
        for pname, pr in cell["policies"].items():
            seeds = pr.get("seeds", [])
            bands = {}
            for seed in seeds:
                if "slo_by_band" in seed:
                    for b, v in seed["slo_by_band"].items():
                        bands.setdefault(b, []).append(v)
            band_str = " | ".join(f"{b}:{np.mean(v):.3f}" for b, v in bands.items())
            print(f"  {pname:20s}: {band_str}")


if __name__ == "__main__":
    main()
