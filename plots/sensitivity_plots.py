"""Publication-quality line plots for the four sensitivity sweeps."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
SIM_RES = ROOT / "simulator" / "results"

for style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "default"):
    try:
        plt.style.use(style); break
    except OSError:
        continue
plt.rcParams.update({
    "axes.grid": True, "grid.alpha": 0.3,
    "axes.edgecolor": "#333", "axes.linewidth": 0.8,
    "font.size": 12,
})

POLICIES = ["ProactiveMPC", "SSM+MPC", "ReactiveThreshold",
            "OverlapMigration", "PPO", "Oracle"]
COLOR = {
    "ProactiveMPC":      "#0F6E56",   # green
    "SSM+MPC":           "#8B5CF6",   # purple
    "ReactiveThreshold": "#888888",   # gray
    "OverlapMigration":     "#F59E0B",   # amber
    "PPO":               "#E24B4A",   # red
    "Oracle":            "#1E2761",   # navy
}
MARKER = {"ProactiveMPC": "o", "SSM+MPC": "P", "ReactiveThreshold": "s",
          "OverlapMigration": "v", "PPO": "^", "Oracle": "D"}


def plot_sweep(filename, xlabel, title, xtick_formatter=None, outname=None):
    d = json.loads((SIM_RES / filename).read_text())
    param = d["param"]
    xs = d["values"]
    rows = d["rows"]

    fig, ax = plt.subplots(figsize=(7.5, 5))
    for p in POLICIES:
        ys = []
        for x in xs:
            hit = next((r for r in rows
                        if r["policy"] == p and r[param] == x), None)
            ys.append(hit["mean_cycle_latency_s"] if hit else float("nan"))
        ax.plot(xs, ys, "-" + MARKER[p],
                color=COLOR[p], linewidth=2, markersize=8,
                markeredgecolor="black", markeredgewidth=0.5,
                label=p)

    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel("Mean cycle latency (s)", fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.set_xticks(xs)
    if xtick_formatter:
        ax.set_xticklabels([xtick_formatter(x) for x in xs])
    ax.legend(loc="best", fontsize=11, frameon=True)
    fig.tight_layout()

    out = outname or filename.replace(".json", "")
    fig.savefig(SIM_RES / f"{out}.png", dpi=300, bbox_inches="tight")
    fig.savefig(SIM_RES / f"{out}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {out}.png + .pdf")


print("Generating sensitivity plots...")

plot_sweep("sensitivity_context_growth.json",
           xlabel="Context growth (tokens/cycle)",
           title="Sensitivity: context growth rate")

# Network sweep is now (profile, alpha) — render one faceted figure per profile.
def plot_network_sweep():
    d = json.loads((SIM_RES / "sensitivity_network.json").read_text())
    alphas = d["alphas"]
    profiles = d["profiles"]
    rows = d["rows"]
    fig, axes = plt.subplots(1, len(profiles),
                              figsize=(5.0 * len(profiles), 4.5), sharey=True)
    if len(profiles) == 1:
        axes = [axes]
    for ax, profile in zip(axes, profiles):
        for p in POLICIES:
            xs, ys = [], []
            for a in alphas:
                hit = next((r for r in rows if r["policy"] == p
                            and r["profile"] == profile and r["alpha"] == a), None)
                if hit:
                    xs.append(hit["observed_disconnect_fraction"])
                    ys.append(hit["mean_cycle_latency_s"])
            if xs:
                ax.plot(xs, ys, "-" + MARKER.get(p, "o"),
                        color=COLOR.get(p, "#444"), linewidth=2, markersize=8,
                        markeredgecolor="black", markeredgewidth=0.5, label=p)
        ax.set_title(f"profile = {profile}", fontsize=12)
        ax.set_xlabel("Observed disconnect fraction")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Mean cycle latency (s)")
    axes[-1].legend(loc="best", fontsize=10)
    fig.suptitle("Sensitivity: Markov network reliability (disc-mass bias α)", fontsize=13)
    fig.tight_layout()
    fig.savefig(SIM_RES / "sensitivity_network.png", dpi=300, bbox_inches="tight")
    fig.savefig(SIM_RES / "sensitivity_network.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  ✓ sensitivity_network.png + .pdf")


plot_network_sweep()

plot_sweep("sensitivity_migration_cost.json",
           xlabel="LLM warm load time (s)",
           title="Sensitivity: migration cost")

plot_sweep("sensitivity_prefill_ratio.json",
           xlabel="Edge/cloud prefill ratio",
           title="Sensitivity: edge vs cloud prefill speed",
           xtick_formatter=lambda x: f"{x}x")

print("Done.")
