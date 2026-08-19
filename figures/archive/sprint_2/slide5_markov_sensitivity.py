"""
Slide 5 — Markov profile sensitivity, two formats:
  slide5_markov_lines.png   — line chart, one line per policy
  slide5_markov_heatmap.png — heatmap, policies × profiles

Data: simulator/results/comparison_within_cycle.json
      mean cycle latency averaged over 3 workloads (steady/variable/burst)
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "simulator" / "results" / "comparison_within_cycle.json"
OUT_DIR = ROOT / "plots" / "sprint_2"
CSV_OUT = ROOT / "results" / "sprint_2" / "slide5_markov_sensitivity.csv"
CSV_OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Data ────────────────────────────────────────────────────────────────────
data = json.loads(DATA_FILE.read_text())
markov_rows = [r for r in data if r["network"].startswith("markov_")]

sums: dict = defaultdict(list)
for r in markov_rows:
    sums[(r["policy"], r["network"])].append(r["mean_cycle_latency_s"])

POLICIES = ["SpeculativeLH", "RoutedSyncLH", "HotStandbyLH", "OverlapMigration",
            "AlwaysCloud", "ReactiveThreshold", "AlwaysEdge", "Oracle"]
NETWORKS = ["markov_campus", "markov_urban", "markov_indoor"]

# Mean per (policy, network) over workloads
means: dict = {}
for pol in POLICIES:
    for net in NETWORKS:
        vals = sums.get((pol, net), [])
        means[(pol, net)] = sum(vals) / len(vals) if vals else float("nan")

# ── CSV backup ────────────────────────────────────────────────────────────
fields = ["policy"] + NETWORKS
with CSV_OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for pol in POLICIES:
        row = {"policy": pol}
        for net in NETWORKS:
            row[net] = round(means[(pol, net)], 4)
        w.writerow(row)
print(f"→ {CSV_OUT}")

# ── Shared config ────────────────────────────────────────────────────────
X_LABELS = [
    "markov_campus\n(1.3% disc)",
    "markov_urban\n(10.7% disc)",
    "markov_indoor\n(13.1% disc)",
]

# Style map
STYLE = {
    # LH variants — solid, distinct colors
    "SpeculativeLH":    dict(color="#1f4e79", ls="-",  lw=2.2, marker="o", ms=8, zorder=5),
    "RoutedSyncLH":     dict(color="#008080", ls="-",  lw=2.5, marker="s", ms=9, zorder=6),
    "HotStandbyLH":     dict(color="#c0392b", ls="-",  lw=2.2, marker="^", ms=8, zorder=5),
    "OverlapMigration": dict(color="#27ae60", ls="-",  lw=2.2, marker="D", ms=8, zorder=5),
    # Reactive — gray dashed
    "AlwaysCloud":      dict(color="#888888", ls="--", lw=1.8, marker="o", ms=6, zorder=4),
    "ReactiveThreshold":dict(color="#aaaaaa", ls="--", lw=1.8, marker="s", ms=6, zorder=4),
    "AlwaysEdge":       dict(color="#bbbbbb", ls="--", lw=1.8, marker="^", ms=6, zorder=4),
    # Oracle — light gray dotted
    "Oracle":           dict(color="#cccccc", ls=":",  lw=1.6, marker="x", ms=7, zorder=3),
}

LABELS = {
    "SpeculativeLH":    "SpeculativeLH (LH)",
    "RoutedSyncLH":     "RoutedSyncLH (LH) ★",
    "HotStandbyLH":     "HotStandbyLH (LH)",
    "OverlapMigration": "OverlapMigration (LH)",
    "AlwaysCloud":      "AlwaysCloud",
    "ReactiveThreshold":"ReactiveThreshold",
    "AlwaysEdge":       "AlwaysEdge",
    "Oracle":           "Oracle (reference)",
}

x_pos = np.arange(3)


# ════════════════════════════════════════════════════════════════════════════
# 1. LINE CHART
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5.5), dpi=200)

for pol in POLICIES:
    ys = [means[(pol, net)] for net in NETWORKS]
    sty = STYLE[pol]
    ax.plot(x_pos, ys, label=LABELS[pol],
            color=sty["color"], linestyle=sty["ls"], linewidth=sty["lw"],
            marker=sty["marker"], markersize=sty["ms"], zorder=sty["zorder"])

# Annotate RoutedSync endpoints for clarity
rs_ys = [means[("RoutedSyncLH", net)] for net in NETWORKS]
for xi, y in zip(x_pos, rs_ys):
    ax.annotate(f"{y:.2f}s", xy=(xi, y), xytext=(0, 7),
                textcoords="offset points", ha="center", fontsize=7.5,
                color="#008080", fontweight="bold")

ax.set_xticks(x_pos)
ax.set_xticklabels(X_LABELS, fontsize=10)
ax.set_ylabel("Mean cycle latency (s)", fontsize=11)
ax.set_ylim(9.5, 18.0)
ax.yaxis.set_major_locator(ticker.MultipleLocator(1.0))
ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))
ax.grid(axis="y", which="major", lw=0.6, alpha=0.4)
ax.grid(axis="y", which="minor", lw=0.3, alpha=0.25)
ax.set_title("Mean cycle latency across Markov profiles", fontsize=13, pad=10)

# Legend outside right
legend = ax.legend(
    loc="upper left", bbox_to_anchor=(1.01, 1.0),
    fontsize=9, frameon=True, framealpha=0.9,
    edgecolor="#cccccc", title="Policy", title_fontsize=9,
)
fig.subplots_adjust(right=0.75, left=0.09, top=0.90, bottom=0.13)

line_path = OUT_DIR / "slide5_markov_lines.png"
fig.savefig(line_path, dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"→ {line_path}")


# ════════════════════════════════════════════════════════════════════════════
# 2. HEATMAP
# ════════════════════════════════════════════════════════════════════════════

# Sort rows by latency on markov_indoor (worst case), ascending
sorted_pols = sorted(POLICIES, key=lambda p: means[(p, "markov_indoor")])

mat = np.array([[means[(pol, net)] for net in NETWORKS] for pol in sorted_pols])

fig, ax = plt.subplots(figsize=(7, 5), dpi=200)

# Use a diverging-light colormap anchored at a reference latency
vmin, vmax = 9.5, 17.5
im = ax.imshow(mat, aspect="auto", cmap="YlOrRd",
               vmin=vmin, vmax=vmax, interpolation="nearest")

# Axes labels
col_labels = ["campus\n(1.3%)", "urban\n(10.7%)", "indoor\n(13.1%)"]
ax.set_xticks(range(3))
ax.set_xticklabels(col_labels, fontsize=10)
ax.set_yticks(range(len(sorted_pols)))

# Bold RoutedSyncLH row label
row_labels = []
for pol in sorted_pols:
    row_labels.append(LABELS[pol])
ax.set_yticklabels(row_labels, fontsize=9)

# Bold RoutedSyncLH tick
for i, pol in enumerate(sorted_pols):
    if pol == "RoutedSyncLH":
        ax.get_yticklabels()[i].set_fontweight("bold")
        ax.get_yticklabels()[i].set_color("#008080")

# Cell annotations
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        val = mat[i, j]
        # Choose text color for contrast
        brightness = (val - vmin) / (vmax - vmin)
        txt_color = "white" if brightness > 0.65 else "black"
        ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                fontsize=8.5, color=txt_color,
                fontweight="bold" if sorted_pols[i] == "RoutedSyncLH" else "normal")

# Colorbar
cbar = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
cbar.set_label("Mean cycle latency (s)", fontsize=9)
cbar.ax.tick_params(labelsize=8)

ax.set_title("Policy × Markov profile — mean cycle latency (s)", fontsize=12, pad=10)

# Highlight RoutedSyncLH row with a border
for i, pol in enumerate(sorted_pols):
    if pol == "RoutedSyncLH":
        for j in range(3):
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                         fill=False, edgecolor="#008080", lw=2.0))
        break

fig.subplots_adjust(left=0.25, right=0.90, top=0.90, bottom=0.12)

heatmap_path = OUT_DIR / "slide5_markov_heatmap.png"
fig.savefig(heatmap_path, dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"→ {heatmap_path}")


# ── Verdict ──────────────────────────────────────────────────────────────
print("\n─── VERDICT ─────────────────────────────────────────────────────────")
print("Line chart (slide5_markov_lines.png):")
print("  Strengths: shows trajectory clearly, OverlapMigration's inverse slope visible,")
print("  AlwaysCloud's climb stands out. Good for 'LH flat, reactive climbs' story.")
print("  Weakness: AlwaysEdge/ReactiveThreshold crossing + gray cluster is busy.")
print()
print("Heatmap (slide5_markov_heatmap.png):")
print("  Strengths: compact, numbers visible at a glance, RoutedSync teal row stands")
print("  out immediately. The dark-red AlwaysCloud/HotStandby cells create instant")
print("  alarm vs pale RoutedSync/Speculative.")
print("  Weakness: doesn't show slope/trajectory as clearly as lines.")
print()
print("Recommendation: HEATMAP for the slide — the color contrast makes the")
print("'LH stays cool while HotStandby/AlwaysCloud go dark' story self-evident")
print("without reading labels. Lines as a backup speaker note.")
