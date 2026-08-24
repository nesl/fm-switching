"""Generate figures for E36b (rewrite): gap_vs_fleetsize, binding_resource, utilization_split."""

import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

ROOT     = Path(__file__).resolve().parents[2]
RES      = ROOT / "results" / "orchestration" / "e36b_fleet"
FIG_DIR  = ROOT / "figures" / "orchestration"
FIG_DIR.mkdir(parents=True, exist_ok=True)

stage1 = json.loads((RES / "stage1_sweep.json").read_text())
diag   = json.loads((RES / "binding_diagnostic.json").read_text())
rows   = stage1["results"]

POLICIES = ["device_only", "always_full", "always_window", "always_summary",
            "footprint_ranked", "maintenance_aware", "oracle"]
COLORS   = {
    "device_only":      "#888888",
    "always_full":      "#1f77b4",
    "always_window":    "#ff7f0e",
    "always_summary":   "#2ca02c",
    "footprint_ranked": "#d62728",
    "maintenance_aware":"#9467bd",
    "oracle":           "#8c564b",
}
NR_LIST = [5, 10, 20, 30, 50]

# ── Figure 1: gap vs fleet size (both_met at 1000ms, cap_frac=0.50) ──────────

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=False)
budget = 1000
cf     = 0.50
metric = f"both_met_{int(budget)}ms"

for ax_idx, wl in enumerate(["locomo", "egoschema"]):
    ax = axes[ax_idx]
    for pol in POLICIES:
        ys = []
        for nr in NR_LIST:
            vals = [r[metric] for r in rows
                    if r["policy"] == pol and r["n_robots"] == nr
                    and abs(r["cap_frac"] - cf) < 0.01 and r["workload"] == wl]
            ys.append(statistics.mean(vals) if vals else float("nan"))
        ls = "--" if pol in ("device_only", "oracle") else "-"
        mk = "^" if pol == "maintenance_aware" else ("s" if pol == "footprint_ranked" else "o")
        ax.plot(NR_LIST, ys, color=COLORS[pol], linestyle=ls, marker=mk,
                label=pol.replace("_", " "), linewidth=1.8, markersize=5)

    ax.set_xlabel("Fleet size (n_robots)")
    ax.set_ylabel("both_met (frac)" if ax_idx == 0 else "")
    ax.set_title(f"{wl.capitalize()} — {int(budget)} ms budget, cap_frac={cf}")
    ax.set_xticks(NR_LIST)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.grid(True, alpha=0.3)
    if ax_idx == 1:
        ax.legend(fontsize=8, loc="lower left")

fig.suptitle("E36b: Policy comparison — fraction both latency and quality met", fontsize=11)
fig.tight_layout()
fig.savefig(FIG_DIR / "e36b_gap_vs_fleetsize.pdf", bbox_inches="tight")
plt.close(fig)
print("Saved e36b_gap_vs_fleetsize.pdf")

# ── Figure 2: binding resource by policy and fleet size ───────────────────────

drows = diag["rows"]
fig, ax = plt.subplots(figsize=(10, 4.5))
x     = np.arange(len(NR_LIST))
width = 0.12
pol_short = {
    "device_only": "dev_only", "always_full": "alw_full",
    "always_window": "alw_win", "always_summary": "alw_sum",
    "footprint_ranked": "fp_rank", "maintenance_aware": "maint", "oracle": "oracle",
}
for i, pol in enumerate(POLICIES):
    kv_fracs = []
    for nr in NR_LIST:
        dr = next((r for r in drows if r["policy"] == pol and r["n_robots"] == nr), None)
        kv_fracs.append(dr["kv_bound_frac"] if dr else 0.0)
    ax.bar(x + i * width, kv_fracs, width * 0.9,
           label=pol_short[pol], color=COLORS[pol], alpha=0.8)

ax.set_xlabel("Fleet size (n_robots)")
ax.set_ylabel("Fraction of epochs where KV memory bound admission")
ax.set_title("E36b: Binding resource (KV memory) by policy and fleet size\n"
             "(Accelerator never bound — kill condition d fires)")
ax.set_xticks(x + width * 3)
ax.set_xticklabels(NR_LIST)
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
ax.legend(fontsize=8, ncol=4)
ax.grid(True, axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(FIG_DIR / "e36b_binding_resource.pdf", bbox_inches="tight")
plt.close(fig)
print("Saved e36b_binding_resource.pdf")

# ── Figure 3: accelerator utilization split ───────────────────────────────────

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for ax_idx, nr in enumerate([10, 50]):
    ax  = axes[ax_idx]
    pols_short = [pol_short[p] for p in POLICIES]
    serve_vals = []; refr_vals = []; mat_vals = []
    for pol in POLICIES:
        dr = next((r for r in drows if r["policy"] == pol and r["n_robots"] == nr), None)
        serve_vals.append((dr["accel_serve_ms"]       / 30000) if dr else 0.0)
        refr_vals.append( (dr["accel_refresh_ms"]     / 30000) if dr else 0.0)
        mat_vals.append(  (dr["accel_materialize_ms"] / 30000) if dr else 0.0)
    xi = np.arange(len(POLICIES))
    ax.bar(xi, serve_vals, label="serve",        color="#1f77b4", alpha=0.85)
    ax.bar(xi, refr_vals,  label="refresh",      color="#ff7f0e", alpha=0.85,
           bottom=serve_vals)
    bottom2 = [s + r for s, r in zip(serve_vals, refr_vals)]
    ax.bar(xi, mat_vals,   label="materialize",  color="#2ca02c", alpha=0.85,
           bottom=bottom2)
    ax.axhline(1.0, color="red", linestyle="--", linewidth=1, label="budget limit")
    ax.set_xticks(xi)
    ax.set_xticklabels(pols_short, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Fraction of accel budget used")
    ax.set_title(f"n_robots={nr}")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.grid(True, axis="y", alpha=0.3)
    if ax_idx == 1:
        ax.legend(fontsize=9)

fig.suptitle("E36b: Accelerator utilization split (serve / refresh / materialize)\n"
             "30 000 ms/epoch budget [ASSUMPTION A4]", fontsize=11)
fig.tight_layout()
fig.savefig(FIG_DIR / "e36b_utilization_split.pdf", bbox_inches="tight")
plt.close(fig)
print("Saved e36b_utilization_split.pdf")
