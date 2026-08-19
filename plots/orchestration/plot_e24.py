"""
E24 phase diagram — joint improvement over best non-joint baseline.

Outputs:
  figures/orchestration/e24_phase_diagram.pdf         (vs best non-joint)
  figures/orchestration/e24_phase_diagram_vs_cv.pdf   (vs cache_value specifically)
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO = Path(__file__).parent.parent.parent
_RESULT_ROOT = _REPO / "results" / "orchestration" / "e24_coupling"
_FIG_DIR = _REPO / "figures" / "orchestration"
_FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Sweep dimensions ──────────────────────────────────────────────────────────

CAPACITY_PCTS = [10, 25, 50, 75, 100]
MOBILITY_LEVELS = ["static", "predictable", "moderate", "high"]
REGIME_MIXES = ["mostly_compressible", "mixed", "mostly_dense"]
NON_JOINT = ["reactive", "replication", "placement_only", "fidelity_only", "cache_value"]

# ── Data loading ──────────────────────────────────────────────────────────────

def load_cell(cap_pct, mobility, regime_mix):
    p = _RESULT_ROOT / f"{cap_pct}pct_{mobility}_{regime_mix}" / "cell.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)

def mean_slo(cell, policy):
    m = cell["policies"].get(policy, {}).get("slo_fraction", {})
    if isinstance(m, dict):
        return m.get("mean", float("nan"))
    return float("nan")

def mean_metric(cell, policy, metric):
    m = cell["policies"].get(policy, {}).get(metric, {})
    if isinstance(m, dict):
        return m.get("mean", float("nan"))
    return float("nan")

# ── Build matrices ────────────────────────────────────────────────────────────

def build_matrix(regime_mix, comparator="best_non_joint"):
    """
    Returns:
      mat: (n_cap, n_mob) array of joint - comparator slo_fraction, in pp
      ann: (n_cap, n_mob) annotation strings
      fwh: (n_cap, n_mob) false_warm_hit_rate for joint
    """
    n_cap = len(CAPACITY_PCTS)
    n_mob = len(MOBILITY_LEVELS)
    mat = np.full((n_cap, n_mob), np.nan)
    ann = np.empty((n_cap, n_mob), dtype=object)
    fwh = np.full((n_cap, n_mob), np.nan)

    for i, cap in enumerate(CAPACITY_PCTS):
        for j, mob in enumerate(MOBILITY_LEVELS):
            cell = load_cell(cap, mob, regime_mix)
            if cell is None:
                ann[i, j] = "?"
                continue
            j_slo = mean_slo(cell, "joint")
            if comparator == "best_non_joint":
                base = max(mean_slo(cell, p) for p in NON_JOINT)
            else:
                base = mean_slo(cell, comparator)
            delta_pp = (j_slo - base) * 100
            mat[i, j] = delta_pp
            ann[i, j] = f"{delta_pp:+.1f}"
            fw = mean_metric(cell, "joint", "false_warm_hit_rate")
            fwh[i, j] = fw

    return mat, ann, fwh

# ── Plot ─────────────────────────────────────────────────────────────────────

def make_phase_diagram(out_path: Path, comparator="best_non_joint",
                       title_suffix="vs best non-joint baseline"):
    n_mix = len(REGIME_MIXES)
    fig, axes = plt.subplots(1, n_mix, figsize=(14, 4.5), constrained_layout=True)
    fig.suptitle(f"Joint SLO improvement ({title_suffix})", fontsize=11, y=1.01)

    # Diverging colormap: blue=positive (joint wins), red=negative (joint loses)
    cmap = "RdBu"
    vmax = 10.0  # pp; symmetric
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    imgs = []
    for ax, rm in zip(axes, REGIME_MIXES):
        mat, ann, fwh = build_matrix(rm, comparator)
        # y-axis: capacity (low→high bottom→top), x-axis: mobility (left→right)
        mat_plot = mat[::-1, :]  # flip so 100% at top
        ann_plot = ann[::-1, :]
        fwh_plot = fwh[::-1, :]

        im = ax.imshow(mat_plot, cmap=cmap, norm=norm, aspect="auto")
        imgs.append(im)

        # Annotate cells
        for i in range(len(CAPACITY_PCTS)):
            for j in range(len(MOBILITY_LEVELS)):
                val = mat_plot[i, j]
                fw = fwh_plot[i, j]
                text = ann_plot[i, j]
                if not np.isnan(fw) and fw > 0.10:
                    text += "*"  # mark high false_warm_hit cells
                color = "white" if abs(val) > 5 else "black"
                ax.text(j, i, text, ha="center", va="center",
                        fontsize=8, color=color, fontweight="bold")

        ax.set_xticks(range(len(MOBILITY_LEVELS)))
        ax.set_xticklabels(["static", "predict.", "moderate", "high"], fontsize=8)
        ax.set_yticks(range(len(CAPACITY_PCTS)))
        ax.set_yticklabels([f"{p}%" for p in CAPACITY_PCTS[::-1]], fontsize=8)
        ax.set_xlabel("Mobility level", fontsize=9)
        if ax is axes[0]:
            ax.set_ylabel("Capacity (% of full-replication budget)", fontsize=9)
        label = rm.replace("_", " ").title()
        ax.set_title(label, fontsize=10)

    # Colorbar
    cb = fig.colorbar(imgs[0], ax=axes.ravel().tolist(), shrink=0.8,
                      label="SLO fraction improvement (pp)")
    cb.ax.tick_params(labelsize=8)

    fig.text(0.02, -0.02,
             "* = false_warm_hit_rate > 10% for joint policy",
             fontsize=7, color="gray")

    fig.savefig(out_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ── Policy comparison table ───────────────────────────────────────────────────

def print_full_table():
    """Print all policy means by regime_mix × capacity tier."""
    all_policies = ["reactive", "replication", "placement_only",
                    "fidelity_only", "cache_value", "joint", "oracle"]
    for rm in REGIME_MIXES:
        print(f"\n── {rm} ──")
        header = f"{'cap%':<6}" + "".join(f"{p:<14}" for p in all_policies)
        print(header)
        for cap in CAPACITY_PCTS:
            row_vals = []
            for mob in MOBILITY_LEVELS:
                cell = load_cell(cap, mob, rm)
                if cell is None:
                    row_vals.append(None)
                    continue
                vals = {p: mean_slo(cell, p) for p in all_policies}
                row_vals.append(vals)
            # average over mobility
            avg = {}
            for p in all_policies:
                vs = [v[p] for v in row_vals if v is not None]
                avg[p] = sum(vs) / len(vs) if vs else float("nan")
            row = f"{cap:<6}" + "".join(f"{avg[p]:<14.3f}" for p in all_policies)
            print(row)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    make_phase_diagram(
        _FIG_DIR / "e24_phase_diagram.pdf",
        comparator="best_non_joint",
        title_suffix="vs best non-joint baseline",
    )
    make_phase_diagram(
        _FIG_DIR / "e24_phase_diagram_vs_cv.pdf",
        comparator="cache_value",
        title_suffix="vs cache_value",
    )
    print_full_table()
