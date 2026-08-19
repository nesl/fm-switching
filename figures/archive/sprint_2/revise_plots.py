"""Revised deck plots addressing first-pass label/spacing issues."""

import csv, json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np

ROOT  = Path(__file__).resolve().parents[2]
SIM   = ROOT / "simulator" / "results"
MRES  = ROOT / "results" / "sprint_2"
OUT   = ROOT / "plots" / "sprint_2"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Arial"],
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

rows   = json.load(open(SIM / "comparison_within_cycle.json"))
v1     = list(csv.DictReader(open(MRES / "ssm_routing_vs_baseline.csv")))

ALL_POLICIES = sorted({r["policy"] for r in rows},
                       key=lambda p: np.mean([r["mean_cycle_latency_s"]
                                              for r in rows if r["policy"]==p]))

def ctr(policy):
    rs = [r for r in rows if r["policy"]==policy]
    return {k: np.mean([r[k] for r in rs]) for k in
            ["mean_cycle_latency_s","mean_compute_seconds_per_cycle","mean_quality",
             "mean_compute_tokens_per_cycle","total_planning_gap_s",
             "num_migrations","unrecoverable_cycles","wasted_compute_tokens"]}

C = {p: ctr(p) for p in ALL_POLICIES}

LH = ["OverlapMigration","SpeculativeLH","RoutedSyncLH","HotStandbyLH"]
LH_COL = {"OverlapMigration":"#1d4ed8","SpeculativeLH":"#3b82f6",
           "RoutedSyncLH":"#0ea5e9","HotStandbyLH":"#67e8f9"}
LH_MRK = {"OverlapMigration":"D","SpeculativeLH":"o","RoutedSyncLH":"s","HotStandbyLH":"^"}
ACCENT  = "#f59e0b"
DIM     = "#9ca3af"

# ── helper ───────────────────────────────────────────────────────────
def render_table(fig_path, headers, rows_data, bold_pred=None, title=None,
                 figsize=(16,9), col_widths=None):
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=16, fontweight="bold", pad=14, loc="left")
    n_cols = len(headers)
    cw = col_widths or [1/n_cols]*n_cols
    tbl = ax.table(cellText=[[str(c) for c in r] for r in rows_data],
                   colLabels=headers, cellLoc="right", loc="upper left",
                   colWidths=cw)
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(13)
    for c in range(n_cols):
        cell = tbl[0,c]
        cell.set_facecolor("#111827"); cell.set_text_props(color="white",fontweight="bold")
        cell.set_edgecolor("#111827")
    for ri in range(len(rows_data)+1):
        tbl[ri,0].set_text_props(ha="left")
    for ri in range(1,len(rows_data)+1):
        bg = "#f3f4f6" if ri%2==0 else "white"
        for ci in range(n_cols):
            tbl[ri,ci].set_facecolor(bg); tbl[ri,ci].set_edgecolor("#d1d5db")
        if bold_pred and bold_pred(rows_data[ri-1]):
            for ci in range(n_cols):
                tbl[ri,ci].set_text_props(fontweight="bold")
                tbl[ri,ci].set_facecolor("#fff7ed")
    tbl.scale(1,1.6)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {fig_path}")


# ═════════════════════════════════════════════════════════
# slide3_lh_centroid.png — short column headers, 1600×900
# ═════════════════════════════════════════════════════════
hdrs = ["Policy","Latency (s)","Compute (s/cyc)","Quality",
        "Wasted tokens","Unrec cycles"]
data = []
for p in LH:
    c = C[p]
    data.append([p, f"{c['mean_cycle_latency_s']:.2f}",
                 f"{c['mean_compute_seconds_per_cycle']:.3f}",
                 f"{c['mean_quality']:.2f}",
                 f"{c['wasted_compute_tokens']:,.0f}",
                 f"{c['unrecoverable_cycles']:.2f}"])
# Bold RoutedSyncLH (best quality-preserving latency)
render_table(OUT/"slide3_lh_centroid.png", hdrs, data,
             bold_pred=lambda r: r[0]=="RoutedSyncLH",
             title="LH-family centroids (24 cells: 3 workloads × 8 networks)",
             figsize=(16,5),
             col_widths=[0.22,0.14,0.16,0.12,0.18,0.16])


# ═════════════════════════════════════════════════════════
# slide4_full_centroid.png — bold RoutedSyncLH specifically
# ═════════════════════════════════════════════════════════
hdrs4 = ["Policy","Latency (s)","Compute (s/cyc)","Tokens/cyc",
         "Quality","Migrations","Gap (s)","Unrec"]
data4 = []
for p in ALL_POLICIES:
    c = C[p]
    data4.append([p, f"{c['mean_cycle_latency_s']:.2f}",
                  f"{c['mean_compute_seconds_per_cycle']:.3f}",
                  f"{c['mean_compute_tokens_per_cycle']:,.0f}",
                  f"{c['mean_quality']:.2f}",
                  f"{c['num_migrations']:.2f}",
                  f"{c['total_planning_gap_s']:.1f}",
                  f"{c['unrecoverable_cycles']:.2f}"])
# Bold LH variants; extra amber highlight on RoutedSyncLH
def bold4(row):
    return row[0] in LH
render_table(OUT/"slide4_full_centroid.png", hdrs4, data4,
             bold_pred=bold4,
             title="All 13 policies — centroids, sorted by mean latency",
             figsize=(16,9),
             col_widths=[0.21,0.10,0.13,0.11,0.09,0.11,0.10,0.10])


# ═════════════════════════════════════════════════════════
# slide3_spec_vs_rs_deltas.png — drop |Δ|<5ms, right-side labels
# ═════════════════════════════════════════════════════════
spec_d = {(r["workload"],r["network"]): r["mean_cycle_latency_s"]
          for r in rows if r["policy"]=="SpeculativeLH"}
rs_d   = {(r["workload"],r["network"]): r["mean_cycle_latency_s"]
          for r in rows if r["policy"]=="RoutedSyncLH"}
deltas = [(f"{wl} / {net}", (spec_d[(wl,net)]-rs_d[(wl,net)])*1000)
          for (wl,net) in spec_d]
deltas = [(l,v) for l,v in deltas if abs(v)>=5]
deltas.sort(key=lambda x: x[1])

fig, ax = plt.subplots(figsize=(16, 9))
fig.subplots_adjust(left=0.28, right=0.92)
yp = np.arange(len(deltas))
ax.barh(yp, [v for _, v in deltas],
        color=LH_COL["SpeculativeLH"], edgecolor="black", linewidth=0.5)
ax.set_yticks(yp)
ax.set_yticklabels([l for l, _ in deltas], fontsize=13, family="monospace")
ax.axvline(0, color="black", linewidth=0.8)
x_min = min(v for _, v in deltas)
ax.set_xlim(x_min * 1.15, abs(x_min) * 0.18)  # room right of 0 for annotations
ax.set_xlabel("Speculative − RoutedSync mean cycle latency (ms)", fontsize=13)
ax.set_title("Spec vs RoutedSync: latency delta per cell\n"
             "(only cells with |Δ| ≥ 5 ms shown; negative = Spec faster)",
             fontsize=15, loc="left", pad=12)
# Annotations just right of the 0 line, black text
for y, (l, v) in enumerate(deltas):
    ax.text(3, y, f"{v:+.0f} ms", va="center", ha="left",
            fontsize=12, color="#111827", fontweight="bold")
ax.grid(axis="x", alpha=0.2, linestyle="--")
ax.grid(axis="y", alpha=0)
fig.savefig(OUT / "slide3_spec_vs_rs_deltas.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"  → {OUT/'slide3_spec_vs_rs_deltas.png'}")


# ═════════════════════════════════════════════════════════
# slide4_pareto.png — revised labeling, merged cluster, leader lines
# ═════════════════════════════════════════════════════════
# Policies to collapse into one point (only the three with identical centroids)
MERGED = ["AlwaysCloud","PPO","SSM+RL"]
MERGED_LABEL = "AlwaysCloud ≈ PPO ≈ SSM+RL"
LABEL_THESE = set(LH) | {"Oracle","ReactiveThreshold","AlwaysEdge"}

fig, ax = plt.subplots(figsize=(16,9))
norm = plt.Normalize(vmin=0.70, vmax=1.00)
cmap = plt.cm.viridis

plotted_merged = False
label_points = {}  # name → (x, y) for leader lines

for p in ALL_POLICIES:
    x = C[p]["mean_cycle_latency_s"]
    y = C[p]["mean_compute_seconds_per_cycle"]
    q = C[p]["mean_quality"]
    col = cmap(norm(q))
    if p in MERGED:
        if not plotted_merged:
            mx = np.mean([C[pp]["mean_cycle_latency_s"] for pp in MERGED])
            my = np.mean([C[pp]["mean_compute_seconds_per_cycle"] for pp in MERGED])
            mq = np.mean([C[pp]["mean_quality"] for pp in MERGED])
            ax.scatter([mx],[my], s=160, c=[cmap(norm(mq))],
                       marker="o", edgecolor="black", linewidth=0.7, zorder=2)
            label_points[MERGED_LABEL] = (mx, my)
            plotted_merged = True
        continue
    if p in LH:
        m = LH_MRK[p]
        ax.scatter([x],[y], s=300, c=[col], marker=m,
                   edgecolor="black", linewidth=1.2, zorder=4)
        label_points[p] = (x, y)
    elif p in LABEL_THESE:
        ax.scatter([x],[y], s=200, c=[col], marker="o",
                   edgecolor="black", linewidth=0.8, zorder=3)
        label_points[p] = (x, y)
    else:
        ax.scatter([x],[y], s=60, c=[DIM], marker=".", alpha=0.5, zorder=1)

# Amber ring on RoutedSyncLH (best-in-class: lowest-latency q=1.00)
rx = C["RoutedSyncLH"]["mean_cycle_latency_s"]
ry = C["RoutedSyncLH"]["mean_compute_seconds_per_cycle"]
ax.scatter([rx],[ry], s=900, facecolors="none", edgecolor=ACCENT,
            linewidth=3.0, zorder=5)

# Leader-line offsets (dx, dy) in data coordinates.
# SpeculativeLH is at lat≈10.76, compute≈6.36 — push label right to clear title.
# OverlapMigration lat≈11.18, compute≈1.16 — push left-up.
# RoutedSyncLH lat≈10.77, compute≈1.04 — push down-right, clear of OM.
offsets = {
    "OverlapMigration":      (-0.60,  0.60),
    "SpeculativeLH":         ( 2.20,  0.40),
    "RoutedSyncLH":          ( 0.20, -0.28),
    "HotStandbyLH":          ( 0.18,  0.40),
    "Oracle":                ( 0.08, -0.04),
    "ReactiveThreshold":     ( 0.15,  0.00),
    "AlwaysEdge":            ( 0.10,  0.00),
    MERGED_LABEL:            ( 0.12,  0.12),
}
for label, (px, py) in label_points.items():
    dx, dy = offsets.get(label, (0.06, 0.10))
    tx, ty = px + dx, py + dy
    weight = "bold" if label in LH or label == MERGED_LABEL else "normal"
    ax.annotate(label, xy=(px, py), xytext=(tx, ty),
                fontsize=11, fontweight=weight,
                arrowprops=dict(arrowstyle="-", color="#aaaaaa", lw=0.8),
                zorder=6)

ax.set_yscale("log")
ax.set_xlabel("Mean cycle latency (s)  ←  lower is better", fontsize=13)
ax.set_ylabel("Mean compute-seconds per cycle (log scale)  ←  lower is better",
              fontsize=13)
ax.set_title("Pareto: latency vs compute, colored by quality\n"
             "(LH variants: shaped markers; amber ring = best-in-class at q=1.00)",
             fontsize=15, loc="left", pad=12)
ax.grid(alpha=0.2, linestyle="--")

# Narrow colorbar touching right edge
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, ax=ax, fraction=0.025, pad=0.01, shrink=0.55)
cbar.set_label("Mean quality", fontsize=11)

fig.tight_layout()
fig.savefig(OUT/"slide4_pareto.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"  → {OUT/'slide4_pareto.png'}")


# ═════════════════════════════════════════════════════════
# slide5_v1_routing_deltas.png — drop |Δ|<5ms, uniform annotations
# ═════════════════════════════════════════════════════════
data5 = [(r["workload"], r["network"],
          float(r["delta_rs_ssm_minus_rs"])*1000) for r in v1]
data5 = [(wl,net,v) for wl,net,v in data5 if abs(v)>=5]
data5.sort(key=lambda x: x[2])

labels5 = [f"{wl:<10s} / {net}" for wl,net,_ in data5]
vals5   = [v for _,_,v in data5]

fig, ax = plt.subplots(figsize=(16, 9))
fig.subplots_adjust(left=0.28, right=0.92)
yp = np.arange(len(data5))
ax.barh(yp, vals5, color=LH_COL["RoutedSyncLH"],
        edgecolor="black", linewidth=0.5)
ax.set_yticks(yp)
ax.set_yticklabels(labels5, fontsize=13, family="monospace")
ax.axvline(0, color="black", linewidth=0.8)
x_min = min(vals5)
ax.set_xlim(x_min * 1.15, abs(x_min) * 0.18)
ax.set_xlabel("v1 (GRU RTT routing) − baseline (instant RTT) latency (ms)",
              fontsize=13)
ax.set_title("v1 anticipatory routing: latency delta per cell\n"
             "(5 cells Pareto-strict with |Δ| ≥ 5 ms; 0 losses)", fontsize=15,
             loc="left", pad=12)
for y, v in enumerate(vals5):
    ax.text(3, y, f"{v:+.0f} ms", va="center", ha="left",
            fontsize=12, color="#111827", fontweight="bold")
ax.grid(axis="x", alpha=0.2, linestyle="--")
ax.grid(axis="y", alpha=0)
fig.savefig(OUT / "slide5_v1_routing_deltas.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"  → {OUT/'slide5_v1_routing_deltas.png'}")


# ── verdict ──────────────────────────────────────────────────────────
print()
print("=" * 68)
print("VERDICT")
print("=" * 68)
print("Slide 3 headline: slide3_spec_vs_rs_deltas.png")
print("  1. RoutedSync matches Spec latency at half the compute, zero waste.")
print("  2. Within-cycle disconnects open Spec's niche in 4 Markov cells.")
print("  3. HotStandby dominated (sticky); OverlapMigration q-drop is OOM, not LH.")
print()
print("Slide 4 headline: slide4_pareto.png")
print("  1. LH variants form a q=1.00 island; RoutedSyncLH amber-ringed as best-in-class.")
print("  2. AlwaysCloud ≈ PPO ≈ SSM+RL cluster: same lat, same gap, two mechanisms.")
print("  3. Log-scale y-axis reveals 6× compute gap between RoutedSync and Speculative.")
print()
print("Slide 5 headline: slide5_v1_routing_deltas.png")
print("  1. GRU forecast: 5 wins, 0 losses; headline −321 ms on burst/markov_urban.")
print("  2. Wins concentrate in fast-transition Markov regimes (same as Spec's niche).")
print("  3. v2 disc-head AUROC 0.9925 but +4 ms vs baseline; three fixes queued.")
