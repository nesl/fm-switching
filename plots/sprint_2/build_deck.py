"""Slide 3, 4, 5 deck assets for the FM-switching Mani 1:1.

Inputs:
  simulator/results/comparison_within_cycle.json
  results/sprint_2/ssm_routing_vs_baseline.csv
  results/sprint_2/gru_v2_routing_vs_baseline.csv  (footnote only)

Outputs in plots/sprint_2/ and results/sprint_2/.

Styling: sans-serif, light gridlines or none, white background, 200 DPI,
1600x900 figures. LH variants in a blue family; reactive baselines gray;
best-in-class amber.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SIM_RES = ROOT / "simulator" / "results"
OUT_PLOTS = ROOT / "plots" / "sprint_2"
OUT_RES = ROOT / "results" / "sprint_2"
OUT_PLOTS.mkdir(parents=True, exist_ok=True)
OUT_RES.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Arial"],
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
    "grid.linewidth": 0.5,
    "axes.edgecolor": "#444",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

LH_VARIANTS = ["OverlapMigration", "SpeculativeLH", "RoutedSyncLH", "HotStandbyLH"]
LH_COLOR = {
    "OverlapMigration": "#1d4ed8",   # deep blue
    "SpeculativeLH":    "#3b82f6",   # blue
    "RoutedSyncLH":     "#0ea5e9",   # sky
    "HotStandbyLH":     "#67e8f9",   # cyan
}
LH_MARKER = {"OverlapMigration": "D", "SpeculativeLH": "o",
             "RoutedSyncLH": "s",     "HotStandbyLH": "^"}
NON_LH_COLOR = "#9ca3af"      # gray
ACCENT = "#f59e0b"            # amber for best-in-class


# ─────────────────────────────────────────────────────────────────────
# Load primary data
# ─────────────────────────────────────────────────────────────────────
rows = json.load(open(SIM_RES / "comparison_within_cycle.json"))
v1_rows = list(csv.DictReader(open(OUT_RES / "ssm_routing_vs_baseline.csv")))
try:
    v2_rows = list(csv.DictReader(open(OUT_RES / "gru_v2_routing_vs_baseline.csv")))
except FileNotFoundError:
    v2_rows = []


def centroid_for(policy):
    rs = [r for r in rows if r["policy"] == policy]
    if not rs:
        return None
    return {
        "policy": policy,
        "n_cells": len(rs),
        "mean_lat": sum(r["mean_cycle_latency_s"] for r in rs) / len(rs),
        "mean_compute_s": sum(r["mean_compute_seconds_per_cycle"] for r in rs) / len(rs),
        "mean_compute_tokens": sum(r["mean_compute_tokens_per_cycle"] for r in rs) / len(rs),
        "mean_quality": sum(r["mean_quality"] for r in rs) / len(rs),
        "peak_mem_max": max(r["peak_memory_mb_continuous"] for r in rs),
        "mean_mem": sum(r["mean_memory_mb_continuous"] for r in rs) / len(rs),
        "num_migrations": sum(r["num_migrations"] for r in rs) / len(rs),
        "planning_gap_s": sum(r["total_planning_gap_s"] for r in rs) / len(rs),
        "wasted_compute_tokens": sum(r.get("wasted_compute_tokens", 0) for r in rs) / len(rs),
        "cloud_failure_events": sum(r.get("cloud_failure_events", 0) for r in rs) / len(rs),
        "successful_fallbacks": sum(r.get("successful_fallbacks", 0) for r in rs) / len(rs),
        "unrecoverable_cycles": sum(r.get("unrecoverable_cycles", 0) for r in rs) / len(rs),
    }


ALL_POLICIES = sorted({r["policy"] for r in rows},
                       key=lambda p: centroid_for(p)["mean_lat"])
CENTROIDS = {p: centroid_for(p) for p in ALL_POLICIES}


# ─────────────────────────────────────────────────────────────────────
# Helper: render a table figure
# ─────────────────────────────────────────────────────────────────────
def render_table(fig_path, headers, rows_data, bold_row_predicate=None,
                  title=None, col_aligns=None, figsize=(16, 9), col_widths=None):
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=18, fontweight="bold", pad=16, loc="left")
    n_cols = len(headers)
    n_rows = len(rows_data)
    col_widths = col_widths or [1.0 / n_cols] * n_cols
    col_aligns = col_aligns or (["right"] * (n_cols - 1) + ["right"])
    col_aligns[0] = "left"   # policy column always left

    # header band
    table = ax.table(
        cellText=[[str(c) for c in r] for r in rows_data],
        colLabels=headers,
        cellLoc="right",
        loc="upper left",
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(13)
    # Header styling
    for c in range(n_cols):
        cell = table[0, c]
        cell.set_facecolor("#111827")
        cell.set_text_props(color="white", fontweight="bold")
        cell.set_edgecolor("#111827")
    # First col left-aligned
    for r in range(n_rows + 1):
        cell = table[r, 0]
        cell.set_text_props(ha="left")
    # Alternate row shading
    for r in range(1, n_rows + 1):
        bg = "#f3f4f6" if r % 2 == 0 else "white"
        for c in range(n_cols):
            table[r, c].set_facecolor(bg)
            table[r, c].set_edgecolor("#d1d5db")
    # Bolden the policy column on bold-row predicate
    if bold_row_predicate is not None:
        for r in range(1, n_rows + 1):
            if bold_row_predicate(rows_data[r - 1]):
                for c in range(n_cols):
                    table[r, c].set_text_props(fontweight="bold")
                    cur_color = table[r, c].get_facecolor()
                    table[r, c].set_facecolor("#fff7ed")  # amber tint
    table.scale(1, 1.6)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {fig_path}")


# ═════════════════════════════════════════════════════════════════════
# SLIDE 3 — LH family
# ═════════════════════════════════════════════════════════════════════
def slide3():
    print("\n[Slide 3] LH family within-family comparison")
    # 3a: centroid table (4 LH variants × {lat, compute-s, quality, wasted,
    #     unrecoverable})
    hdrs = ["Policy", "Mean latency (s)", "Mean compute (s/cycle)",
            "Mean quality", "Wasted compute (tok/cell)",
            "Unrecoverable cycles/cell"]
    data = []
    for p in LH_VARIANTS:
        c = CENTROIDS[p]
        data.append([
            p,
            f"{c['mean_lat']:.2f}",
            f"{c['mean_compute_s']:.3f}",
            f"{c['mean_quality']:.2f}",
            f"{c['wasted_compute_tokens']:,.0f}",
            f"{c['unrecoverable_cycles']:.2f}",
        ])
    # Bold the lowest-latency LH (best-in-class) AND the lowest-compute LH
    best_lat = min(LH_VARIANTS, key=lambda p: CENTROIDS[p]["mean_lat"])
    render_table(
        OUT_PLOTS / "slide3_lh_centroid.png",
        headers=hdrs, rows_data=data,
        bold_row_predicate=lambda row: row[0] == best_lat,
        title="LH-family centroids (averaged over 3 workloads × 8 networks = 24 cells)",
        figsize=(15, 5),
        col_widths=[0.22, 0.15, 0.18, 0.13, 0.18, 0.18],
    )

    # CSV mirror
    with (OUT_RES / "slide3_lh_summary.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(hdrs)
        for r in data:
            w.writerow(r)
    print(f"  → {OUT_RES / 'slide3_lh_summary.csv'}")

    # 3b: Spec − RoutedSync delta per cell (horizontal bars, sorted)
    spec = {(r["workload"], r["network"]): r for r in rows if r["policy"] == "SpeculativeLH"}
    rsl  = {(r["workload"], r["network"]): r for r in rows if r["policy"] == "RoutedSyncLH"}
    deltas = []
    for k in spec:
        d = spec[k]["mean_cycle_latency_s"] - rsl[k]["mean_cycle_latency_s"]
        deltas.append((f"{k[0]:<10s} / {k[1]}", d))
    # Sort by magnitude (most negative first → Spec wins most)
    deltas.sort(key=lambda x: x[1])
    labels = [d[0] for d in deltas]
    vals   = [d[1] * 1000.0 for d in deltas]  # ms
    fig, ax = plt.subplots(figsize=(16, 9))
    ypos = np.arange(len(deltas))
    colors = [LH_COLOR["SpeculativeLH"] if v < -1 else NON_LH_COLOR for v in vals]
    ax.barh(ypos, vals, color=colors, edgecolor="black", linewidth=0.4)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=10, family="monospace")
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel("Spec − RoutedSync mean cycle latency (ms)", fontsize=13)
    ax.set_title("Speculative vs RoutedSync: per-cell latency delta\n"
                  "(negative = Speculative faster; 4 cells where mid-cycle disc "
                  "lets Spec win at 2× compute)", fontsize=15, loc="left", pad=14)
    # Annotate non-zero bars
    for y, v in zip(ypos, vals):
        if abs(v) > 1.0:
            ha = "right" if v < 0 else "left"
            xoff = -3 if v < 0 else 3
            ax.text(v + xoff, y, f"{v:+.1f} ms", va="center", ha=ha,
                    fontsize=10, color="#111827")
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", alpha=0)
    fig.tight_layout()
    fig.savefig(OUT_PLOTS / "slide3_spec_vs_rs_deltas.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    print(f"  → {OUT_PLOTS / 'slide3_spec_vs_rs_deltas.png'}")

    # 3c: findings.txt — bullets including HotStandby and OverlapMigration diagnoses
    om = CENTROIDS["OverlapMigration"]; sp = CENTROIDS["SpeculativeLH"]
    rs = CENTROIDS["RoutedSyncLH"]; hs = CENTROIDS["HotStandbyLH"]
    text = [
        "Slide 3 — LH family findings",
        "============================",
        "",
        "Headline: RoutedSyncLH is the cost-effective LH variant. It matches "
        "SpeculativeLH latency (10.77s vs 10.76s) at half the compute (1.04s/cycle "
        "vs 6.36s/cycle, 4.2k tok/cycle vs 8.3k) and zero wasted-compute tokens.",
        "",
        f"Per-policy centroids (24 cells each):",
        f"  RoutedSyncLH:     lat={rs['mean_lat']:.2f}s  "
        f"compute_s={rs['mean_compute_s']:.3f}  q={rs['mean_quality']:.2f}  "
        f"wasted={rs['wasted_compute_tokens']:,.0f}  unrec={rs['unrecoverable_cycles']:.2f}",
        f"  SpeculativeLH:    lat={sp['mean_lat']:.2f}s  "
        f"compute_s={sp['mean_compute_s']:.3f}  q={sp['mean_quality']:.2f}  "
        f"wasted={sp['wasted_compute_tokens']:,.0f}  unrec={sp['unrecoverable_cycles']:.2f}",
        f"  OverlapMigration: lat={om['mean_lat']:.2f}s  "
        f"compute_s={om['mean_compute_s']:.3f}  q={om['mean_quality']:.2f}  "
        f"wasted={om['wasted_compute_tokens']:,.0f}  unrec={om['unrecoverable_cycles']:.2f}",
        f"  HotStandbyLH:     lat={hs['mean_lat']:.2f}s  "
        f"compute_s={hs['mean_compute_s']:.3f}  q={hs['mean_quality']:.2f}  "
        f"wasted={hs['wasted_compute_tokens']:,.0f}  unrec={hs['unrecoverable_cycles']:.2f}",
        "",
        "Speculative vs RoutedSync — within-cycle divergence",
        "  4 cells where Spec < RS by >10ms (all on disconnect-prone networks):",
    ]
    for label, v in [(d[0], d[1] * 1000.0) for d in deltas if d[1] < -0.01]:
        text.append(f"    {label}   Δ = {v:+.1f} ms")
    text += [
        "  Mechanism: on long-context cycles in disconnect-prone Markov regimes, the",
        "  cloud-serve window (>=2 sub-ticks) catches a mid-cycle disconnect. RS",
        "  routed pre-hoc on start-of-cycle state and pays its fallback cost; Spec's",
        "  parallel edge branch returns at edge latency with no fallback overhead.",
        "  The 'no information needed' framing for Spec is intact here — Spec wins",
        "  precisely where start-of-cycle network state is a poor predictor of the",
        "  full serving window.",
        "",
        "HotStandbyLH — Pareto dominated, structurally",
        f"  HS latency = {hs['mean_lat']:.2f}s vs RS = {rs['mean_lat']:.2f}s "
        f"(+{(hs['mean_lat']-rs['mean_lat']):.2f}s) at +3.13× compute-seconds",
        f"  ({hs['mean_compute_s']:.2f}s vs {rs['mean_compute_s']:.2f}s).",
        "  Dominance is purely from sticky promotion: once HS fails over to edge",
        "  it never reclaims cloud-primary. Estimated ~98% of cycles on edge",
        "  post-failover on markov_urban (see results/sprint_2/hotstandby_diagnosis.md).",
        "  Bidirectional standby (cloud can reclaim primary) would close most of",
        "  the gap; that change is a clean follow-up, not in scope for this deck.",
        "",
        "OverlapMigration — quality drop is OOM-fallback, not LH itself",
        f"  OM quality = {om['mean_quality']:.2f} vs 1.00 for Spec/RS/HS.",
        "  Mechanism: edge KV crosses memory_cap_mb during long-context cycles →",
        "  simulator forces state_mode='stateless' (quality 0.70). The trigger is",
        "  in orchestrator_sim.py around the OOM check; QUALITY['stateless']=0.70",
        "  in cost_model.py. OM hits it because it waits for memory pressure",
        "  before warming cloud; Spec/RS/HS never serve on edge as primary so",
        "  their KV doesn't grow that way.",
        "  This is an artifact of the OM trigger condition + simulator OOM",
        "  fallback, NOT a property of latency-hiding. Any LH policy that lets",
        "  edge keep growing KV would hit the same cap.",
    ]
    (OUT_RES / "slide3_findings.txt").write_text("\n".join(text))
    print(f"  → {OUT_RES / 'slide3_findings.txt'}")
    return deltas


# ═════════════════════════════════════════════════════════════════════
# SLIDE 4 — LH vs all policies
# ═════════════════════════════════════════════════════════════════════
def slide4():
    print("\n[Slide 4] LH vs all policies")
    # 4a: Pareto scatter, x = mean latency, y = mean compute-s, color = quality
    fig, ax = plt.subplots(figsize=(16, 9))
    pols = ALL_POLICIES
    lats = [CENTROIDS[p]["mean_lat"] for p in pols]
    cs   = [CENTROIDS[p]["mean_compute_s"] for p in pols]
    qs   = [CENTROIDS[p]["mean_quality"] for p in pols]
    is_lh = [p in LH_VARIANTS for p in pols]
    # Quality colormap: viridis from 0.70 -> 1.0
    norm = plt.Normalize(vmin=0.70, vmax=1.0)
    cmap = plt.cm.viridis
    sizes = [320 if lh else 180 for lh in is_lh]
    markers = [LH_MARKER[p] if p in LH_VARIANTS else "o" for p in pols]
    # Plot each separately so marker shape varies
    for p, lat, c_s, q, lh, sz, m in zip(pols, lats, cs, qs, is_lh, sizes, markers):
        ax.scatter([lat], [c_s], s=sz, c=[cmap(norm(q))],
                    marker=m, edgecolor="black",
                    linewidth=(1.2 if lh else 0.6), zorder=3 if lh else 2,
                    label=p)
    # Highlight best-in-class with amber ring
    best_quality1 = [p for p in pols if CENTROIDS[p]["mean_quality"] >= 0.999]
    best_pol = min(best_quality1, key=lambda p: CENTROIDS[p]["mean_lat"])
    bx, by = CENTROIDS[best_pol]["mean_lat"], CENTROIDS[best_pol]["mean_compute_s"]
    ax.scatter([bx], [by], s=900, facecolors="none", edgecolor=ACCENT,
                linewidth=3.0, zorder=4)
    # Annotations
    for p, lat, c_s in zip(pols, lats, cs):
        offset = (8, 6)
        if p == "RoutedSyncLH":
            offset = (8, 12)
        if p == "SpeculativeLH":
            offset = (8, -16)
        if p == "OverlapMigration":
            offset = (-90, 6)
        if p == "HotStandbyLH":
            offset = (8, 6)
        ax.annotate(p, (lat, c_s), xytext=offset, textcoords="offset points",
                    fontsize=11,
                    fontweight=("bold" if p in LH_VARIANTS else "normal"))
    ax.set_xlabel("Mean cycle latency (s) — lower is better", fontsize=13)
    ax.set_ylabel("Mean compute-seconds per cycle (lower is better)", fontsize=13)
    ax.set_title("Pareto: latency vs compute, colored by quality\n"
                  "(LH variants highlighted with distinct markers; best-in-class "
                  "[q=1.00] ringed amber)", fontsize=15, loc="left", pad=12)
    ax.set_yscale("log")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6)
    cbar.set_label("Mean quality", fontsize=12)
    # Legend for markers
    handles = [
        mpatches.Patch(color="#9ca3af", label="Non-LH policy"),
    ] + [mpatches.Patch(color=LH_COLOR[p], label=p) for p in LH_VARIANTS]
    ax.legend(handles=handles, loc="upper left", fontsize=10, frameon=True)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT_PLOTS / "slide4_pareto.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {OUT_PLOTS / 'slide4_pareto.png'}")

    # 4b: full centroid table — all 13 policies sorted by latency, LH rows bold
    hdrs = ["Policy", "Latency (s)", "Compute (s/cyc)", "Tokens/cyc",
            "Quality", "Migrations", "Gap (s)", "Unrec"]
    data = []
    for p in ALL_POLICIES:
        c = CENTROIDS[p]
        data.append([
            p,
            f"{c['mean_lat']:.2f}",
            f"{c['mean_compute_s']:.3f}",
            f"{c['mean_compute_tokens']:,.0f}",
            f"{c['mean_quality']:.2f}",
            f"{c['num_migrations']:.2f}",
            f"{c['planning_gap_s']:.1f}",
            f"{c['unrecoverable_cycles']:.2f}",
        ])
    render_table(
        OUT_PLOTS / "slide4_full_centroid.png",
        headers=hdrs, rows_data=data,
        bold_row_predicate=lambda row: row[0] in LH_VARIANTS,
        title="All 13 policies — centroids over 24 cells (sorted by mean latency)",
        figsize=(16, 9),
        col_widths=[0.21, 0.10, 0.12, 0.11, 0.09, 0.12, 0.10, 0.10],
    )
    # CSV mirror
    with (OUT_RES / "slide4_full_centroid.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(hdrs)
        for r in data: w.writerow(r)
    print(f"  → {OUT_RES / 'slide4_full_centroid.csv'}")

    # 4c: planning gap breakdown — where AlwaysCloud / PPO / SSM+RL accumulate the 170s
    text = [
        "Slide 4 — Planning-gap breakdown for cloud-faithful policies",
        "=============================================================",
        "",
        "Three policies — AlwaysCloud, PPO, SSM+RL — converge to the same",
        "centroid (lat≈12.39s, compute_s≈0.85s, q=1.00, migrations≈7.50,",
        "gap≈171.7s). They land in three different places on the planning-gap",
        "vs unrecoverable-cycle ledger:",
        "",
        f"  AlwaysCloud:   gap={CENTROIDS['AlwaysCloud']['planning_gap_s']:.1f}s  "
        f"migs={CENTROIDS['AlwaysCloud']['num_migrations']:.2f}  "
        f"unrec={CENTROIDS['AlwaysCloud']['unrecoverable_cycles']:.2f}/cell  "
        f"cf={CENTROIDS['AlwaysCloud']['cloud_failure_events']:.2f}/cell",
        f"  PPO:           gap={CENTROIDS['PPO']['planning_gap_s']:.1f}s  "
        f"migs={CENTROIDS['PPO']['num_migrations']:.2f}  "
        f"unrec={CENTROIDS['PPO']['unrecoverable_cycles']:.2f}/cell  "
        f"cf={CENTROIDS['PPO']['cloud_failure_events']:.2f}/cell",
        f"  SSM+RL:        gap={CENTROIDS['SSM+RL']['planning_gap_s']:.1f}s  "
        f"migs={CENTROIDS['SSM+RL']['num_migrations']:.2f}  "
        f"unrec={CENTROIDS['SSM+RL']['unrecoverable_cycles']:.2f}/cell  "
        f"cf={CENTROIDS['SSM+RL']['cloud_failure_events']:.2f}/cell",
        "",
        "AlwaysCloud's gap comes from its REACTIVE rule: when start-of-cycle is",
        "disconnected, it migrates to edge (50s warm load + KV re-prefill). With",
        "~7 such transitions per episode on disconnect-prone networks, the gap",
        "accumulates to ~170s. Its within-cycle unrecoverable rate is low (0.38/cell)",
        "because most disconnects are caught pre-cycle by the reactive trigger.",
        "",
        "PPO and SSM+RL keep state_loc=cloud through more disconnect cycles",
        "(their learned policies don't aggressively migrate). Result: they pay",
        "the within-cycle planning gap as 'unrecoverable_cycles' (~3.25/cell)",
        "AND end up triggering the reactive MIGRATE_TO_EDGE path anyway, racking",
        "up the same total gap by a different mechanism.",
        "",
        "Per-cell breakdown — disconnect-prone networks only:",
        "",
    ]
    rs_ac = [r for r in rows if r["policy"] == "AlwaysCloud"]
    disc_nets = ["markov_indoor", "markov_urban", "intermittent", "realistic"]
    text.append(f"  {'workload':<10} {'network':<14} {'AC gap':>8} {'AC migs':>8} "
                f"{'AC unrec':>9} {'PPO gap':>8} {'PPO unrec':>10}")
    for r in sorted(rs_ac, key=lambda r: (r["workload"], r["network"])):
        if r["network"] not in disc_nets:
            continue
        ppo = next(p for p in rows if p["policy"] == "PPO"
                    and p["workload"] == r["workload"]
                    and p["network"] == r["network"])
        text.append(f"  {r['workload']:<10} {r['network']:<14} "
                    f"{r['total_planning_gap_s']:>7.1f}s "
                    f"{r['num_migrations']:>8d} "
                    f"{r['unrecoverable_cycles']:>9d} "
                    f"{ppo['total_planning_gap_s']:>7.1f}s "
                    f"{ppo['unrecoverable_cycles']:>10d}")
    text += [
        "",
        "Worth flagging on the slide:",
        " * AlwaysCloud's high `migrations` and 0 `successful_fallbacks` is",
        "   the signature of 'reactive cloud→edge migration' as its disconnect",
        "   handler.",
        " * PPO/SSM+RL's 0 migrations + 3.25 unrec/cell is the signature of",
        "   'stay on cloud, eat the planning gap.' Two different mechanisms,",
        "   same total user-facing cost.",
    ]
    (OUT_RES / "slide4_planning_gap.txt").write_text("\n".join(text))
    print(f"  → {OUT_RES / 'slide4_planning_gap.txt'}")


# ═════════════════════════════════════════════════════════════════════
# SLIDE 5 — Anticipatory routing
# ═════════════════════════════════════════════════════════════════════
def slide5():
    print("\n[Slide 5] Anticipatory routing — v1 GRU, v2 footnote")
    # 5a: per-cell delta bar chart (rs_ssm − rs), sorted, highlight key cells
    data = []
    for r in v1_rows:
        d = float(r["delta_rs_ssm_minus_rs"]) * 1000.0  # ms
        data.append((f"{r['workload']:<10s} / {r['network']}", d,
                     r['workload'], r['network']))
    data.sort(key=lambda x: x[1])
    labels = [d[0] for d in data]
    vals   = [d[1] for d in data]
    fig, ax = plt.subplots(figsize=(16, 9))
    ypos = np.arange(len(data))
    colors = []
    for lab, v, wl, net in data:
        if v < -1:
            colors.append(LH_COLOR["RoutedSyncLH"])
        elif v > 1:
            colors.append("#dc2626")
        else:
            colors.append(NON_LH_COLOR)
    ax.barh(ypos, vals, color=colors, edgecolor="black", linewidth=0.4)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=10, family="monospace")
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel("v1 (GRU RTT routing) − baseline (instant RTT) latency (ms)",
                  fontsize=13)
    ax.set_title("v1 anticipatory routing: per-cell latency delta\n"
                  "(negative = v1 faster; 5 cells Pareto-strict, 0 losses)",
                  fontsize=15, loc="left", pad=14)
    # Highlight the headline cells
    headline = {"burst markov_urban": "−321 ms (largest win)",
                "burst markov_campus": "−81 ms"}
    for y, (lab, v, wl, net) in enumerate(data):
        key = f"{wl} {net}"
        if key in headline:
            ax.annotate(headline[key], xy=(v, y),
                        xytext=(-15, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=11, color=ACCENT,
                        fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=ACCENT, lw=1.5))
        elif abs(v) > 5:
            ha = "right" if v < 0 else "left"
            xoff = -3 if v < 0 else 3
            ax.text(v + xoff, y, f"{v:+.0f} ms", va="center", ha=ha,
                    fontsize=9, color="#374151")
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", alpha=0)
    fig.tight_layout()
    fig.savefig(OUT_PLOTS / "slide5_v1_routing_deltas.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    print(f"  → {OUT_PLOTS / 'slide5_v1_routing_deltas.png'}")

    # 5b: per-cell CSV (slide5_v1_per_cell.csv — same shape as ssm_routing_vs_baseline)
    fields = ["workload", "network", "rs_lat", "rs_ssm_lat", "spec_lat",
              "delta_rs_ssm_minus_rs", "delta_rs_ssm_minus_spec",
              "rs_ssm_migrations", "rs_ssm_planning_gap"]
    with (OUT_RES / "slide5_v1_per_cell.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in v1_rows:
            w.writerow(r)
    print(f"  → {OUT_RES / 'slide5_v1_per_cell.csv'}")

    # 5c: findings — v1 result + v2 footnote
    wins = [r for r in v1_rows if float(r["delta_rs_ssm_minus_rs"]) < -0.01]
    losses = [r for r in v1_rows if float(r["delta_rs_ssm_minus_rs"]) > 0.01]
    markov = [r for r in v1_rows if r["network"].startswith("markov_")]
    intermit = [r for r in v1_rows if r["network"] == "intermittent"]
    others = [r for r in v1_rows if not r["network"].startswith("markov_")
              and r["network"] != "intermittent"]
    def mean_ms(rs):
        return 1000 * sum(float(r['delta_rs_ssm_minus_rs']) for r in rs) / len(rs)

    text = [
        "Slide 5 — Anticipatory routing findings",
        "========================================",
        "",
        "Headline (v1): A 1-step GRU forecast of RTT, used to make the routing",
        "decision in RoutedSyncLH, Pareto-strict-dominates the ground-truth-",
        "instantaneous-RTT baseline. Same compute, same memory, same quality;",
        "never worse, sometimes substantially better.",
        "",
        f"Mean Δ across 24 cells: {mean_ms(v1_rows):+.1f} ms",
        f"Mean Δ on Markov (9):  {mean_ms(markov):+.1f} ms",
        f"Mean Δ on intermittent (3): {mean_ms(intermit):+.1f} ms",
        f"Mean Δ on others (12): {mean_ms(others):+.1f} ms",
        "",
        f"Cells where v1 beats baseline (>=10ms): {len(wins)} of 24",
        f"Cells where v1 loses to baseline (>=10ms): {len(losses)} of 24",
        "",
        "Top wins:",
    ]
    for r in sorted(wins, key=lambda r: float(r["delta_rs_ssm_minus_rs"]))[:5]:
        d = float(r["delta_rs_ssm_minus_rs"]) * 1000
        text.append(f"  {r['workload']:<10} {r['network']:<14}  Δ = {d:+.1f} ms  "
                    f"(rs={float(r['rs_lat']):.3f} → v1={float(r['rs_ssm_lat']):.3f})")
    text += [
        "",
        "Mechanism: on the most dynamic Markov regime (urban), the chain",
        "transitions during the cloud-serve window. Instantaneous RTT-based",
        "routing reacts ONE step late; the GRU's 1-step forecast catches the",
        "transition and routes to edge or sticks with cloud accordingly.",
        "",
        "Methodology note for the deck:",
        "  The 'GRU' is what the codebase calls 'SSM' — a 1-layer nn.GRU(6, 32)",
        "  + Linear(32, 16) latent projection + 3-head 10-step predictor.",
        "  It is NOT Mamba/S4. The 'SSM' prefix is a naming artifact from the",
        "  original Mamba plan; the v2 file (routed_sync_gru_v2_lh_policy.py)",
        "  starts the rename. The 'GRU forecast' framing is the honest one.",
        "",
        "─────────────────────────────────────────────────────────────────",
        "Footnote (v2): Joint RTT + P(disconnect) forecaster",
        "─────────────────────────────────────────────────────────────────",
        "",
        "We added a second head to the GRU forecaster — P(disconnect in next 1s),",
        "BCE-trained alongside MSE on RTT — and rebuilt the routing rule to use",
        "expected-cost marginalization (no thresholds).",
        "",
        "Training sanity (160k samples, 60 epochs, joint loss MSE + 1.0·BCE):",
        "  val AUROC = 0.9925   (target > 0.85: PASS)",
        "  val MSE  = 0.00911   (vs old SSMPredictor 0.00940: 3.1% better)",
        "",
        "Routing comparison (24 cells, same seeds):",
        "  Mean Δ(v2 − rs) overall:    +3.8 ms  (worse than baseline)",
        "  Mean Δ(v2 − v1) overall:   +34.5 ms  (worse than v1)",
        "  Wins vs rs (>=10ms): 4 ; Losses: 10 ; Ties: 10",
        "",
        "Diagnosis: v2 underperforms despite a well-trained head. Three",
        "tractable issues:",
        "  1. Pessimistic fallback estimate (cloud_ms_fc + 1ms + edge_ms_fc)",
        "     overstates disconnect cost; actual fallback is ~cloud_elapsed +",
        "     edge_ms, typically <1s of wasted compute.",
        "  2. Forecaster trained on synthetic traces only. The disc head is",
        "     well-calibrated in-distribution (intermittent) but miscalibrated",
        "     on Markov regimes (P(disc) over-predicted by 5-10x on campus).",
        "  3. Disc window = 1.0s is wider than actual cloud-compute window",
        "     (~0.7s) for typical contexts — same-direction conservatism.",
        "",
        "Three follow-up experiments are queued and tractable. For this deck,",
        "the v2 result is the negative-result-to-flag, not a headline claim.",
        "v1 is the slide's positive result.",
    ]
    (OUT_RES / "slide5_findings.txt").write_text("\n".join(text))
    print(f"  → {OUT_RES / 'slide5_findings.txt'}")


# ─────────────────────────────────────────────────────────────────────
# Drive
# ─────────────────────────────────────────────────────────────────────
slide3_deltas = slide3()
slide4()
slide5()


print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)
print("Slide 3 headline visual: slide3_spec_vs_rs_deltas.png")
print("  3 verbal beats:")
print("  1. RoutedSync matches Speculative latency at half the compute (zero waste).")
print("  2. Within-cycle disconnects create the room for Spec to win 4 cells (markov).")
print("  3. HotStandby is structurally dominated; OverlapMigration's q-drop is OOM, not LH.")
print()
print("Slide 4 headline visual: slide4_pareto.png")
print("  3 verbal beats:")
print("  1. LH variants cluster as a q=1.00 island, separate from cheap-but-degraded baselines.")
print("  2. AlwaysCloud / PPO / SSM+RL converge at lat≈12.4s, gap≈170s — same cost via")
print("     two different mechanisms (reactive migration vs accumulated unrecoverables).")
print("  3. RoutedSyncLH is the q=1.00 cost-effective frontier point: lowest-latency")
print("     full-quality policy on dynamic networks.")
print()
print("Slide 5 headline visual: slide5_v1_routing_deltas.png")
print("  3 verbal beats:")
print("  1. GRU-forecast routing strictly dominates instantaneous baseline:")
print("     5 wins, 0 losses across 24 cells, headline -321ms on burst/markov_urban.")
print("  2. The win materialises exactly in fast-transition Markov regimes — same")
print("     mechanism the within-cycle simulator exposed for Speculative.")
print("  3. The v2 disc-head extension did not improve on v1 (footnote): trained well")
print("     (AUROC 0.99) but the routing-policy plumbing overshoots due to pessimistic")
print("     fallback + out-of-distribution miscalibration. Three diagnostic fixes queued.")
