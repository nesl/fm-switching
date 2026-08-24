"""E36c figures: gap vs fleet size, binding resource, KV occupancy."""
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT   = Path(__file__).resolve().parents[2]
S1     = json.loads((ROOT / "results/orchestration/e36c_fleet/stage1_sweep.json").read_text())
BD     = json.loads((ROOT / "results/orchestration/e36c_fleet/binding_diagnostic.json").read_text())
FIGDIR = ROOT / "figures/orchestration"
FIGDIR.mkdir(parents=True, exist_ok=True)

ROWS = S1["results"]

COLORS = {
    "device_only":       "#999999",
    "always_full":       "#e6194b",
    "always_window":     "#f58231",
    "always_summary":    "#ffe119",
    "footprint_ranked":  "#3cb44b",
    "maintenance_aware": "#4363d8",
    "oracle":            "#911eb4",
}
LABELS = {
    "device_only":      "Device-only",
    "always_full":      "Always-full",
    "always_window":    "Always-win10",
    "always_summary":   "Always-sum200",
    "footprint_ranked": "Footprint-ranked",
    "maintenance_aware":"Maint-aware",
    "oracle":           "Oracle",
}

POLICIES = ["device_only", "always_full", "always_window", "footprint_ranked",
            "maintenance_aware", "oracle"]

def _mean(lst): return statistics.mean(lst) if lst else 0.0


# ── Fig 1: both_met vs fleet size (fixed kv=9 GiB, turn=30 s, two panels) ──

def fig_gap_vs_fleetsize():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=False)
    configs = [
        ("locomo",    300.0,  0.20, "LoCoMo · 300 ms · q≥0.20"),
        ("egoschema", 300.0,  0.20, "EgoSchema · 300 ms · q≥0.20"),
    ]
    for ax, (wl, budget, q_slo, title) in zip(axes, configs):
        key = f"both_met_{int(budget)}ms"
        for pol in POLICIES:
            means = []
            for nr in [5, 10, 20, 50]:
                vals = [r[key] for r in ROWS
                        if r["policy"] == pol and r["workload"] == wl
                        and r["q_slo"] == q_slo
                        and r["kv_cap_gib"] == 9.0 and r["turn_interval_s"] == 30.0]
                means.append(_mean(vals) * 100 if vals else None)
            xs = [5, 10, 20, 50]
            ys = means
            valid = [(x, y) for x, y in zip(xs, ys) if y is not None]
            if not valid: continue
            xv, yv = zip(*valid)
            ls = "--" if pol == "maintenance_aware" else "-"
            lw = 2.5 if pol in ("footprint_ranked", "maintenance_aware") else 1.2
            ax.plot(xv, yv, color=COLORS[pol], label=LABELS[pol], ls=ls, lw=lw, marker="o", ms=5)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Fleet size (robots)", fontsize=9)
        ax.set_ylabel("Both-met (%)", fontsize=9)
        ax.set_xticks([5, 10, 20, 50])
        ax.set_ylim(-2, 105)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        ax.grid(axis="y", alpha=0.3)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=8,
               bbox_to_anchor=(0.5, -0.04))
    fig.text(0.5, 0.97, "E36c: Both-met vs fleet size  (kv_cap=9 GiB, turn_interval=30 s)",
             ha="center", fontsize=11, weight="bold")
    fig.tight_layout(rect=[0, 0.08, 1, 0.95])
    out = FIGDIR / "e36c_gap_vs_fleetsize.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close(fig)


# ── Fig 2: binding resource fraction — matrix kv_cap × turn_interval ─────────

def fig_binding_resource():
    bd_rows = BD["rows"]
    wl, nr = "locomo", 50
    kv_caps = [4.5, 9.0, 18.0, 36.0]
    tis     = [5.0, 15.0, 30.0, 60.0]

    # We show 3 panels: always_full, footprint_ranked, maintenance_aware
    pols_show = ["always_full", "footprint_ranked", "maintenance_aware"]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))

    for ax, pol in zip(axes, pols_show):
        kv_mat    = [[0.0] * len(tis) for _ in kv_caps]
        accel_mat = [[0.0] * len(tis) for _ in kv_caps]
        for i, kv in enumerate(kv_caps):
            for j, ti in enumerate(tis):
                hits = [r for r in bd_rows if r["policy"] == pol and r["n_robots"] == nr
                        and r["kv_cap_gib"] == kv and r["turn_interval_s"] == ti]
                if hits:
                    kv_mat[i][j]    = hits[0]["kv_bound_frac"]
                    accel_mat[i][j] = hits[0]["accel_bound_frac"]

        # Stacked bar per (kv_cap, ti) cell; show as grid of bars
        xs = range(len(tis))
        for i, kv in enumerate(kv_caps):
            bar_xs = [x + i * 0.2 for x in xs]
            ax.bar(bar_xs, [kv_mat[i][j] * 100 for j in range(len(tis))],
                   width=0.18, color="#4363d8", alpha=0.85,
                   label=f"{kv} GiB" if i == 0 else None)
            ax.bar(bar_xs, [accel_mat[i][j] * 100 for j in range(len(tis))],
                   width=0.18, color="#e6194b", alpha=0.7,
                   bottom=[kv_mat[i][j] * 100 for j in range(len(tis))],
                   label="Accel" if i == 0 else None)
        ax.set_title(f"{LABELS[pol]}\n(n=50 robots, LoCoMo)", fontsize=9)
        ax.set_xticks([x + 0.3 for x in xs])
        ax.set_xticklabels([f"{int(t)}s" for t in tis], fontsize=8)
        ax.set_xlabel("Turn interval", fontsize=9)
        ax.set_ylabel("Epoch bound fraction (%)", fontsize=9)
        ax.set_ylim(0, 105)
        ax.grid(axis="y", alpha=0.3)

    # Legend: kv_cap colours grouped by position
    from matplotlib.patches import Patch
    kv_colors = ["#4363d8", "#2888cc", "#1ab5a0", "#0fd068"]
    kv_patches = [Patch(color=kv_colors[i], label=f"KV {kv_caps[i]} GiB")
                  for i in range(len(kv_caps))]
    accel_patch = Patch(color="#e6194b", alpha=0.7, label="Accel")
    fig.legend(handles=kv_patches + [accel_patch], loc="lower center", ncol=5,
               fontsize=8, bbox_to_anchor=(0.5, -0.06))
    fig.text(0.5, 0.97,
             "E36c: Binding resource — KV (blue) vs Accelerator (red)  [n=50, LoCoMo]",
             ha="center", fontsize=10, weight="bold")
    fig.tight_layout(rect=[0, 0.10, 1, 0.95])
    out = FIGDIR / "e36c_binding_resource.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close(fig)


# ── Fig 3: KV occupancy statistics ───────────────────────────────────────────

def fig_kv_occupancy():
    # For each policy: show p50 and max KV occupancy vs kv_cap_gib
    # Averaged over n_robots, turn_interval, seeds, workloads, q_slos
    pols_show = ["always_full", "footprint_ranked", "maintenance_aware", "always_window"]
    kv_caps   = [4.5, 9.0, 18.0, 36.0]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    for ax, metric, label in [
        (axes[0], "kv_occ_p50_gib", "KV occupancy p50 (GiB)"),
        (axes[1], "kv_occ_max_gib", "KV occupancy max (GiB)"),
    ]:
        for pol in pols_show:
            ys = []
            for kv_cap in kv_caps:
                vals = [r.get(metric, 0.0) for r in ROWS
                        if r["policy"] == pol and r["kv_cap_gib"] == kv_cap]
                ys.append(_mean(vals))
            ls = "--" if pol == "maintenance_aware" else "-"
            lw = 2.2 if pol in ("footprint_ranked", "maintenance_aware") else 1.2
            ax.plot(kv_caps, ys, color=COLORS[pol], label=LABELS[pol],
                    ls=ls, lw=lw, marker="s", ms=5)
        # Diagonal reference (capacity)
        ax.plot(kv_caps, kv_caps, "k:", lw=0.8, label="Cap limit")
        ax.set_xlabel("KV capacity (GiB)", fontsize=9)
        ax.set_ylabel(label, fontsize=9)
        ax.set_xticks(kv_caps)
        ax.set_xticklabels([f"{v:.1f}" for v in kv_caps], fontsize=8)
        ax.grid(alpha=0.3)
        ax.set_title(label, fontsize=9)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8,
               bbox_to_anchor=(0.5, -0.04))
    fig.text(0.5, 0.97, "E36c: KV occupancy vs capacity (averaged over all other axes)",
             ha="center", fontsize=10, weight="bold")
    fig.tight_layout(rect=[0, 0.08, 1, 0.95])
    out = FIGDIR / "e36c_kv_occupancy.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close(fig)


if __name__ == "__main__":
    print("Generating E36c figures …")
    fig_gap_vs_fleetsize()
    fig_binding_resource()
    fig_kv_occupancy()
    print("Done.")
