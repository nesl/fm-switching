"""Publication-quality bar charts from simulator/results/comparison_with_rl.json."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SIM_RES = ROOT / "simulator" / "results"

src = SIM_RES / "comparison_with_rl.json"
if not src.exists():
    src = SIM_RES / "comparison.json"
rows = json.loads(src.read_text())

POLICY_ORDER = ["AlwaysEdge", "AlwaysCloud", "CostAwareGreedy",
                "ReactiveThreshold", "ProactiveMPC", "PPO", "Oracle"]
COLOR = {
    "AlwaysEdge":        "#999999",
    "AlwaysCloud":       "#999999",
    "CostAwareGreedy":   "#999999",
    "ReactiveThreshold": "#9CC9E8",
    "ProactiveMPC":      "#0F6E56",
    "PPO":               "#E24B4A",
    "Oracle":            "#1E2761",
}

for style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "default"):
    try:
        plt.style.use(style); break
    except OSError:
        continue
plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.3,
                     "axes.edgecolor": "#333", "axes.linewidth": 0.8})


# ─── Figure 1: intermittent / steady ──────────────────────────────────
inter = [r for r in rows if "intermittent" in r["network"] and "steady" in r["workload"]]
inter_by_policy = {r["policy"]: r for r in inter}
policies = [p for p in POLICY_ORDER if p in inter_by_policy]
gaps      = [inter_by_policy[p]["total_planning_gap_s"]   for p in policies]
latencies = [inter_by_policy[p]["mean_cycle_latency_s"]   for p in policies]
migs      = [inter_by_policy[p]["num_migrations"]         for p in policies]
qualities = [inter_by_policy[p]["mean_quality"]           for p in policies]
colors    = [COLOR[p] for p in policies]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

bars1 = ax1.bar(policies, gaps, color=colors, edgecolor="black", linewidth=0.6)
ax1.set_ylabel("Planning gap (s)", fontsize=12)
ax1.set_title("Planning gap on intermittent network", fontsize=14)
ax1.tick_params(axis="x", rotation=30, labelsize=11)
for label in ax1.get_xticklabels():
    label.set_horizontalalignment("right")
ymax1 = max(gaps) if max(gaps) > 0 else 1.0
ax1.set_ylim(0, ymax1 * 1.18)
for b, v in zip(bars1, gaps):
    ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + ymax1 * 0.015,
             f"{v:.1f}", ha="center", va="bottom", fontsize=10)

bars2 = ax2.bar(policies, latencies, color=colors, edgecolor="black", linewidth=0.6)
ax2.set_ylabel("Mean cycle latency (s)", fontsize=12)
ax2.set_title("Cycle latency and context quality", fontsize=14)
ax2.tick_params(axis="x", rotation=30, labelsize=11)
for label in ax2.get_xticklabels():
    label.set_horizontalalignment("right")
ymax2 = max(latencies)
ax2.set_ylim(0, ymax2 * 1.22)
for b, lat, q in zip(bars2, latencies, qualities):
    x = b.get_x() + b.get_width() / 2
    h = b.get_height()
    ax2.text(x, h + ymax2 * 0.015, f"{lat:.2f}", ha="center", va="bottom", fontsize=10)
    ax2.text(x, h + ymax2 * 0.075, f"q={q:.2f}", ha="center", va="bottom",
             fontsize=9, color="#333333", style="italic")

fig.tight_layout()
fig.savefig(SIM_RES / "policy_comparison_intermittent.png", dpi=300, bbox_inches="tight")
fig.savefig(SIM_RES / "policy_comparison_intermittent.pdf", bbox_inches="tight")
plt.close(fig)


# ─── Figure 2: top-4 policies × 3 workloads (avg over networks) ───────
TOP4 = ["ReactiveThreshold", "ProactiveMPC", "PPO", "Oracle"]
WORKLOADS = ["steady", "variable", "burst"]

means = np.zeros((len(TOP4), len(WORKLOADS)))
for i, p in enumerate(TOP4):
    for j, w in enumerate(WORKLOADS):
        vals = [r["mean_cycle_latency_s"] for r in rows
                if r["policy"] == p and r["workload"] == w]
        means[i, j] = np.mean(vals) if vals else np.nan

fig, ax = plt.subplots(figsize=(10, 5.2))
x = np.arange(len(WORKLOADS))
group_w = 0.8
bw = group_w / len(TOP4)
for i, p in enumerate(TOP4):
    offsets = x - group_w / 2 + bw / 2 + i * bw
    bars = ax.bar(offsets, means[i], bw, label=p,
                  color=COLOR[p], edgecolor="black", linewidth=0.6)
    for b, v in zip(bars, means[i]):
        ax.text(b.get_x() + b.get_width() / 2,
                b.get_height() + means.max() * 0.012,
                f"{v:.2f}", ha="center", va="bottom", fontsize=9)

ax.set_xticks(x)
ax.set_xticklabels([w.capitalize() for w in WORKLOADS], fontsize=12)
ax.tick_params(axis="x", labelrotation=30)
for label in ax.get_xticklabels():
    label.set_horizontalalignment("right")
ax.set_ylabel("Mean cycle latency (s)", fontsize=12)
ax.set_title("Cycle latency by workload (averaged over 5 networks)", fontsize=14)
ax.set_ylim(0, means.max() * 1.18)
ax.legend(fontsize=11, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18),
          frameon=False)

fig.tight_layout()
fig.savefig(SIM_RES / "policy_comparison_all_workloads.png", dpi=300, bbox_inches="tight")
fig.savefig(SIM_RES / "policy_comparison_all_workloads.pdf", bbox_inches="tight")
plt.close(fig)


# ─── Stdout summary table for the intermittent / steady scenario ──────
print(f"Source: {src.name}\n")
header = f"{'Policy':<18}| {'Latency':>7} | {'Gap':>7} | {'Migrations':>10} | {'Quality':>7}"
print(header)
print("-" * len(header))
for p in policies:
    r = inter_by_policy[p]
    print(f"{p:<18}| {r['mean_cycle_latency_s']:>7.2f} | "
          f"{r['total_planning_gap_s']:>7.1f} | "
          f"{r['num_migrations']:>10d} | "
          f"{r['mean_quality']:>7.2f}")

print(f"\nWrote:")
for f in ["policy_comparison_intermittent.png",
          "policy_comparison_intermittent.pdf",
          "policy_comparison_all_workloads.png",
          "policy_comparison_all_workloads.pdf"]:
    print(f"  simulator/results/{f}")
