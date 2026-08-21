"""E29 follow-up analysis (no inference runs).

Reads per-question records from results/fidelity/e29_tier_heterogeneous/.
Outputs:
  - figures/fidelity/e29_substitution.pdf/.png
  - Prints all numbers needed to revise reports/e29_tier_heterogeneous.md
"""

import json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_DIR = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous"
FIG_DIR = ROOT / "figures" / "fidelity"
FIG_DIR.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(42)
REPS = 1000


# ── helpers ──────────────────────────────────────────────────────────────────

def bootstrap_ci(v, reps=REPS):
    v = np.asarray(v, float)
    means = [np.mean(RNG.choice(v, len(v), replace=True)) for _ in range(reps)]
    return np.percentile(means, [2.5, 97.5])


def paired_bootstrap(va, vb, reps=REPS):
    """Two-sided p-value and 95% CI for mean(vb) - mean(va)."""
    va, vb = np.asarray(va, float), np.asarray(vb, float)
    d = vb - va
    obs = np.mean(d)
    # resample differences
    boots = [np.mean(RNG.choice(d, len(d), replace=True)) for _ in range(reps)]
    boots = np.array(boots)
    ci = np.percentile(boots, [2.5, 97.5])
    # shift to null
    null = boots - np.mean(boots)
    p = np.mean(np.abs(null) >= np.abs(obs))
    p = max(p, 1 / reps)
    return obs, ci, p


def sig_stars(p):
    if p < 0.001: return "***"
    if p < 0.01: return "**"
    if p < 0.05: return "*"
    return "ns"


# ── load data ─────────────────────────────────────────────────────────────────

def load_locomo(slug):
    d = json.load(open(IN_DIR / f"locomo_{slug}_n100.json"))
    uid_key = "q_uid"
    return {r[uid_key]: r["conditions"] for r in d["records"]}


def load_egoschema(slug):
    d = json.load(open(IN_DIR / f"egoschema_{slug}_n60.json"))
    return {r["uid"]: r["conditions"] for r in d["records"]}


loc3 = load_locomo("qwen3b")
loc7 = load_locomo("qwen7b")
ego3 = load_egoschema("qwen3b")
ego7 = load_egoschema("qwen7b")

# Align by shared UIDs (all should match)
loc_uids = sorted(set(loc3) & set(loc7))
ego_uids = sorted(set(ego3) & set(ego7))
assert len(loc_uids) == 100
assert len(ego_uids) == 60


def get_paired(data3, data7, uids, cond3, cond7):
    """Return (v3, v7) aligned vectors for paired tests."""
    v3 = [data3[u][cond3]["correct"] for u in uids]
    v7 = [data7[u][cond7]["correct"] for u in uids]
    return v3, v7


# ── 1. Paired substitution tests ──────────────────────────────────────────────

print("=" * 70)
print("1. PAIRED SUBSTITUTION TESTS")
print("   contrast: 7B/cond vs 3B/full  (diff = 7B/cond - 3B/full)")
print("=" * 70)

substitution_tests = [
    ("LoCoMo", loc3, loc7, loc_uids, "7B/window-10 vs 3B/full", "full", "window-10"),
    ("LoCoMo", loc3, loc7, loc_uids, "7B/summary-200 vs 3B/full", "full", "summary-200"),
    ("LoCoMo", loc3, loc7, loc_uids, "7B/full vs 3B/full [ceiling]", "full", "full"),
    ("EgoSchema", ego3, ego7, ego_uids, "7B/window-10 vs 3B/full", "full", "window-10"),
    ("EgoSchema", ego3, ego7, ego_uids, "7B/summary-200 vs 3B/full", "full", "summary-200"),
    ("EgoSchema", ego3, ego7, ego_uids, "7B/full vs 3B/full [ceiling]", "full", "full"),
]

results_sub = {}
for workload, d3, d7, uids, label, c3, c7 in substitution_tests:
    v3, v7 = get_paired(d3, d7, uids, c3, c7)
    acc3 = np.mean(v3)
    acc7 = np.mean(v7)
    diff, ci, p = paired_bootstrap(v3, v7)
    print(f"\n  {workload} — {label}")
    print(f"    3B/full={acc3:.3f}  7B/{c7}={acc7:.3f}")
    print(f"    diff (7B-3B) = {diff:+.3f}  95% CI [{ci[0]:+.3f}, {ci[1]:+.3f}]  p={p:.3f} {sig_stars(p)}")
    # Interpret: is cheaper-fidelity-on-larger-model distinguishable from full-on-smaller?
    if "ceiling" not in label:
        if p >= 0.05:
            verdict = "NOT distinguishable from 3B/full (ns)"
        else:
            verdict = "DISTINGUISHABLE from 3B/full"
        print(f"    → {verdict}")
    results_sub[(workload, label)] = dict(acc3=acc3, acc7=acc7, diff=diff, ci=ci, p=p)


# ── 2. Absolute sufficiency table ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("2. ABSOLUTE SUFFICIENCY TABLE  (floor q ∈ {0.20, 0.30, 0.40})")
print("=" * 70)

acc_table = {
    ("locomo", "qwen3b", "blind"):       0.030,
    ("locomo", "qwen3b", "window-10"):   0.180,
    ("locomo", "qwen3b", "summary-80"):  0.090,
    ("locomo", "qwen3b", "summary-200"): 0.120,
    ("locomo", "qwen3b", "full"):        0.230,
    ("locomo", "qwen7b", "blind"):       0.080,
    ("locomo", "qwen7b", "window-10"):   0.230,
    ("locomo", "qwen7b", "summary-80"):  0.120,
    ("locomo", "qwen7b", "summary-200"): 0.120,
    ("locomo", "qwen7b", "full"):        0.400,
    ("egoschema", "qwen3b", "blind"):       0.300,
    ("egoschema", "qwen3b", "window-10"):   0.450,
    ("egoschema", "qwen3b", "summary-80"):  0.400,
    ("egoschema", "qwen3b", "summary-200"): 0.433,
    ("egoschema", "qwen3b", "full"):        0.450,
    ("egoschema", "qwen7b", "blind"):       0.200,
    ("egoschema", "qwen7b", "window-10"):   0.500,
    ("egoschema", "qwen7b", "summary-80"):  0.433,
    ("egoschema", "qwen7b", "summary-200"): 0.483,
    ("egoschema", "qwen7b", "full"):        0.567,
}

floors = [0.20, 0.30, 0.40]
conditions_order = ["blind", "window-10", "summary-80", "summary-200", "full"]
models = ["qwen3b", "qwen7b"]
workloads = ["locomo", "egoschema"]

print(f"\n{'workload':<12} {'model':<8} {'condition':<14} {'acc':<6} {'q≥0.20':>7} {'q≥0.30':>7} {'q≥0.40':>7}")
print("-" * 65)
for wl in workloads:
    for mdl in models:
        for cond in conditions_order:
            acc = acc_table[(wl, mdl, cond)]
            marks = ["✓" if acc >= q else "✗" for q in floors]
            print(f"{wl:<12} {mdl:<8} {cond:<14} {acc:<6.3f} {marks[0]:>7} {marks[1]:>7} {marks[2]:>7}")
    print()

print("\nCheapest (fidelity, tier) meeting each floor per workload:")
for wl in workloads:
    print(f"\n  {wl.upper()}:")
    for q in floors:
        passing = [(cond, mdl) for wl2, mdl, cond in acc_table if wl2 == wl and acc_table[(wl, mdl, cond)] >= q]
        # order by conditions_order then by model
        order = {c: i for i, c in enumerate(conditions_order)}
        mod_order = {"qwen3b": 0, "qwen7b": 1}
        passing_sorted = sorted(passing, key=lambda x: (order[x[0]], mod_order[x[1]]))
        if passing_sorted:
            best_cond, best_mdl = passing_sorted[0]
            best_acc = acc_table[(wl, best_mdl, best_cond)]
            print(f"    q≥{q:.2f}: cheapest = ({best_cond}, {best_mdl}) acc={best_acc:.3f}")
        else:
            print(f"    q≥{q:.2f}: NO (fidelity, tier) pair meets this floor")


# ── 3. Sufficiency disagreement interpretation ────────────────────────────────

print("\n" + "=" * 70)
print("3. SUFFICIENCY DISAGREEMENT — ABSOLUTE VALUES")
print("=" * 70)

rel_threshold = {
    "egoschema/qwen3b/window-10": 0.450 / 0.450,   # 1.000
    "egoschema/qwen7b/window-10": 0.500 / 0.567,   # 0.882
    "egoschema/qwen3b/summary-200": 0.433 / 0.450, # 0.962
    "egoschema/qwen7b/summary-200": 0.483 / 0.567, # 0.852
}
print("EgoSchema window-10: 3B acc=0.450, 3B full=0.450 → ratio=1.000 ≥ 0.90 PASS")
print("EgoSchema window-10: 7B acc=0.500, 7B full=0.567 → ratio=0.882  < 0.90 FAIL")
print("  7B window-10 absolute accuracy (0.500) > 3B window-10 (0.450)")
print("  BUT 7B fails because its bar is higher (0.567 × 0.90 = 0.510 > 0.500)")
print()
print("EgoSchema summary-200: 3B acc=0.433, 3B full=0.450 → ratio=0.962 ≥ 0.90 PASS")
print("EgoSchema summary-200: 7B acc=0.483, 7B full=0.567 → ratio=0.852  < 0.90 FAIL")
print("  7B summary-200 absolute accuracy (0.483) > 3B summary-200 (0.433)")
print("  The device tier does NOT use a representation that is insufficient at the edge;")
print("  BOTH are used — the relative criterion disagrees, not the deployment choice.")


# ── 4. Fidelity-sensitivity: window-10 vs full per model per workload ──────────

print("\n" + "=" * 70)
print("4. FIDELITY SENSITIVITY: window-10 vs full contrast per model × workload")
print("=" * 70)

sensitivity_cases = [
    ("LoCoMo", "qwen3b", loc3, loc_uids),
    ("LoCoMo", "qwen7b", loc7, loc_uids),
    ("EgoSchema", "qwen3b", ego3, ego_uids),
    ("EgoSchema", "qwen7b", ego7, ego_uids),
]

sensitivity_results = {}
for workload, model, data_ref, uids in [
    ("LoCoMo", "qwen3b", loc3, loc_uids),
    ("LoCoMo", "qwen7b", loc7, loc_uids),
    ("EgoSchema", "qwen3b", ego3, ego_uids),
    ("EgoSchema", "qwen7b", ego7, ego_uids),
]:
    v_win = [data_ref[u]["window-10"]["correct"] for u in uids]
    v_full = [data_ref[u]["full"]["correct"] for u in uids]
    acc_win = np.mean(v_win)
    acc_full = np.mean(v_full)
    diff, ci, p = paired_bootstrap(v_win, v_full)
    print(f"\n  {workload} / {model}:")
    print(f"    window-10={acc_win:.3f}  full={acc_full:.3f}")
    print(f"    diff (full - window) = {-diff:+.3f}  p={p:.3f} {sig_stars(p)}")
    sensitivity_results[(workload, model)] = dict(
        acc_win=acc_win, acc_full=acc_full, diff_full_minus_win=-diff, p=p
    )

print("\n  Side-by-side (window-vs-full gap significance):")
print("  LoCoMo  3B: p=%.3f %s  7B: p=%.3f %s" % (
    sensitivity_results[("LoCoMo","qwen3b")]["p"], sig_stars(sensitivity_results[("LoCoMo","qwen3b")]["p"]),
    sensitivity_results[("LoCoMo","qwen7b")]["p"], sig_stars(sensitivity_results[("LoCoMo","qwen7b")]["p"]),
))
print("  EgoSchema  3B: p=%.3f %s  7B: p=%.3f %s" % (
    sensitivity_results[("EgoSchema","qwen3b")]["p"], sig_stars(sensitivity_results[("EgoSchema","qwen3b")]["p"]),
    sensitivity_results[("EgoSchema","qwen7b")]["p"], sig_stars(sensitivity_results[("EgoSchema","qwen7b")]["p"]),
))


# ── 5. Figure: e29_substitution.pdf ──────────────────────────────────────────

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
fig.subplots_adjust(wspace=0.38, left=0.09, right=0.97, top=0.88, bottom=0.14)

conditions_plot = ["blind", "window-10", "summary-80", "summary-200", "full"]
cond_labels = ["blind", "win-10", "sum-80", "sum-200", "full"]
x = np.arange(len(conditions_plot))
width = 0.32

colors = {"qwen3b": "#4C72B0", "qwen7b": "#DD8452"}
label_map = {"qwen3b": "3B (device)", "qwen7b": "7B (edge/cloud)"}

for ax, wl, d3_data, d7_data, uids_wl in [
    (axes[0], "LoCoMo", loc3, loc7, loc_uids),
    (axes[1], "EgoSchema", ego3, ego7, ego_uids),
]:
    # Accuracy + bootstrap CI for each model × condition
    for i, (mdl, ddata) in enumerate([("qwen3b", d3_data), ("qwen7b", d7_data)]):
        accs, lo, hi = [], [], []
        for cond in conditions_plot:
            v = [ddata[u][cond]["correct"] for u in uids_wl]
            a = np.mean(v)
            ci_lo, ci_hi = bootstrap_ci(v)
            accs.append(a)
            lo.append(a - ci_lo)
            hi.append(ci_hi - a)
        offset = (i - 0.5) * width
        bars = ax.bar(x + offset, accs, width, color=colors[mdl], alpha=0.82,
                      label=label_map[mdl], zorder=3)
        ax.errorbar(x + offset, accs, yerr=[lo, hi], fmt="none",
                    ecolor="black", elinewidth=1.0, capsize=3, zorder=4)

    # Cross-tier comparison brackets: 7B/window-10 vs 3B/full, 7B/sum200 vs 3B/full
    comparisons = [
        ("window-10", "full", "7B win-10\nvs 3B full"),
        ("summary-200", "full", "7B sum-200\nvs 3B full"),
    ]
    y_top = 0.65 if wl == "LoCoMo" else 0.75
    for ci_idx, (c7_cond, c3_cond, bracket_label) in enumerate(comparisons):
        # positions: 7B bar at c7_cond index, 3B bar at c3_cond index
        idx7 = conditions_plot.index(c7_cond)
        idx3 = conditions_plot.index(c3_cond)
        x7 = x[idx7] + 0.5 * width
        x3 = x[idx3] - 0.5 * width
        acc7 = np.mean([d7_data[u][c7_cond]["correct"] for u in uids_wl])
        acc3 = np.mean([d3_data[u][c3_cond]["correct"] for u in uids_wl])
        v3_arr = [d3_data[u][c3_cond]["correct"] for u in uids_wl]
        v7_arr = [d7_data[u][c7_cond]["correct"] for u in uids_wl]
        _, _, p_val = paired_bootstrap(v3_arr, v7_arr)
        stars = sig_stars(p_val)
        bh = y_top + 0.06 * ci_idx
        ax.annotate("", xy=(x7, bh), xytext=(x3, bh),
                    arrowprops=dict(arrowstyle="-", color="#555", lw=1.0),
                    annotation_clip=False)
        mid = (x3 + x7) / 2
        ax.text(mid, bh + 0.012, stars, ha="center", va="bottom", fontsize=8.5, color="#333")

    ax.set_title(wl, fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, fontsize=8.5)
    ax.set_ylabel("Accuracy", fontsize=9)
    ax.set_ylim(0, y_top + 0.18)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.grid(axis="y", alpha=0.35, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

patch3 = mpatches.Patch(color=colors["qwen3b"], alpha=0.82, label="3B (device)")
patch7 = mpatches.Patch(color=colors["qwen7b"], alpha=0.82, label="7B (edge/cloud)")
fig.legend(handles=[patch3, patch7], loc="upper center", ncol=2,
           fontsize=9, frameon=False, bbox_to_anchor=(0.52, 1.01))

fig.suptitle("E29 — Q(fidelity, model): accuracy by condition and tier\n"
             "Brackets: 7B cheaper-fidelity vs 3B full (ns = not distinguishable)",
             fontsize=9.5, y=1.05)

out_pdf = FIG_DIR / "e29_substitution.pdf"
out_png = FIG_DIR / "e29_substitution.png"
fig.savefig(out_pdf, bbox_inches="tight")
fig.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"\nFigure saved → {out_pdf}")
print(f"Figure saved → {out_png}")
