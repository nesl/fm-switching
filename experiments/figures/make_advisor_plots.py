#!/usr/bin/env python3
"""
Advisor plots for FM-switching project, 2026-09-30.
CPU-only. Reads committed result files; writes PDF + PNG to figures/advisor_2026_09_30/.
"""

import json, math, warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FixedLocator, FuncFormatter
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

REPO     = Path(__file__).resolve().parents[2]
OUT_DIR  = REPO / "figures" / "advisor_2026_09_30"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── color palette (colorblind-safe, IBM palette) ──────────────────────────────
C = dict(
    blue="#648FFF",
    violet="#785EF0",
    red="#DC267F",
    orange="#FE6100",
    yellow="#FFB000",
    grey="#999999",
    light_grey="#CCCCCC",
    dark="#222222",
    pos="#648FFF",   # "positive / highlight"
    neg="#DC267F",   # "negative / contrast"
    cap="#FE6100",   # cap-hit
    ctrl="#785EF0",  # control
)

SLIDE_SIZE = (10, 6)
DPI = 300
FONT_LABEL  = 14
FONT_TICK   = 12
FONT_ANNOT  = 12

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.labelsize": FONT_LABEL,
    "xtick.labelsize": FONT_TICK,
    "ytick.labelsize": FONT_TICK,
    "figure.dpi": DPI,
})


def save(fig, stem):
    pdf = OUT_DIR / f"{stem}.pdf"
    png = OUT_DIR / f"{stem}.png"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {pdf.name} + {png.name}")
    return pdf, png


def wilson_ci(k, n, z=1.96):
    """Wilson score 95% CI."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


# ─────────────────────────────────────────────────────────────────────────────
# PLOT A — Workload screening table
# Source: reports (values hardcoded with citations below)
# Fifth column: selection rationale (Fix 2)
# ─────────────────────────────────────────────────────────────────────────────
def plot_A():
    """Workload screening matrix: 4 datasets × 5 criteria (4 ticks + rationale)."""
    rows = [
        # (dataset, platform_sourced, multi_query_session, published_thinking_gain, released, rationale)
        ("S-EMBER",       1, 1, 0, 1,
         "released session workload\nwith grounded evidence intervals"),
        ("ERQA",          1, 0, 1, 1,
         "published Qwen3-VL Instruct/Thinking\nnumbers for our exact models"),
        ("SiGNgapore2D",  1, 0, 0, 1,
         "paper's documented failure modes are\nreasoning, not perception; real robot deployment\n(arXiv:2506.02556)"),
        ("COCO counting", 0, 0, 0, 1,
         "rejected — scale-insensitive\nVLM failure mode (Study C)"),
    ]

    col_labels = [
        "Platform-sourced\nimagery",
        "Multi-query\nsession",
        "Published\nthinking gain",
        "Released /\navailable",
        "Selection rationale",
    ]
    n_rows   = len(rows)
    n_tick_cols = 4

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.axis("off")

    MARKERS = {1: ("✓", C["blue"]), 0: ("✗", C["red"]), 0.5: ("◑", C["yellow"])}

    # Layout: tick columns at x=0..3, rationale column at x=5 (wider gap)
    tick_xs = [0, 1, 2, 3]
    rationale_x = 5.2

    ax.set_xlim(-2.2, rationale_x + 3.5)
    ax.set_ylim(-0.8, n_rows + 0.3)

    for ri, row in enumerate(rows):
        row_y = n_rows - 1 - ri
        dataset, p, m, t, r, rationale = row
        values = [p, m, t, r]

        # Dataset label
        weight = "bold" if ri < 3 else "normal"
        color  = C["dark"] if ri < 3 else C["grey"]
        ax.text(-2.0, row_y, dataset, ha="left", va="center",
                fontsize=FONT_LABEL, fontweight=weight, color=color)

        for ci, v in enumerate(values):
            sym, col = MARKERS[v]
            ax.text(tick_xs[ci], row_y, sym, ha="center", va="center",
                    fontsize=26, color=col)

        # Rationale text
        rat_color = C["grey"] if ri == 3 else C["dark"]
        ax.text(rationale_x, row_y, rationale, ha="left", va="center",
                fontsize=10, color=rat_color, style="italic" if ri == 3 else "normal")

    # Column headers
    for ci, x in enumerate(tick_xs):
        ax.text(x, n_rows - 0.1, col_labels[ci], ha="center", va="bottom",
                fontsize=11, fontweight="bold")
    ax.text(rationale_x, n_rows - 0.1, col_labels[4], ha="left", va="bottom",
            fontsize=11, fontweight="bold")

    # Vertical separator before rationale column
    ax.axvline(x=rationale_x - 0.4, ymin=0.05, ymax=0.95,
               color=C["light_grey"], linewidth=1, linestyle="-")

    # Horizontal separator above COCO
    ax.axhline(y=0.5, color=C["grey"], linewidth=1, linestyle="--",
               xmin=0.0, xmax=0.95)
    ax.text(-2.0, 0.0, "rejected baseline", ha="left", va="center",
            fontsize=9, color=C["grey"], style="italic")

    # Legend
    legend_elements = [
        mpatches.Patch(color=C["blue"], label="✓  Yes"),
        mpatches.Patch(color=C["red"],  label="✗  No"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=FONT_ANNOT,
              frameon=False, bbox_to_anchor=(1.0, -0.12))

    fig.tight_layout()
    save(fig, "A_workload_screening")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT B — S-EMBER evidence-distance distribution
# Source: results/sember/study_h2/study_h2_evidence_distance.json (overall histogram)
#         results/sember/study_h/data/sember_grounding.jsonl (per-category)
# Counting_objects_events excluded.
# ─────────────────────────────────────────────────────────────────────────────
def plot_B():
    h2 = json.load(open(REPO / "results/sember/study_h2/study_h2_evidence_distance.json"))

    # Overall histogram bins (from committed JSON)
    bins_data = h2["histogram_nearest"]  # list of {lo, hi, count, pct}
    # Parse per-category distances from raw grounding jsonl
    cat_distances = defaultdict(list)
    EXCLUDE_CAT = "counting_objects_events"
    with open(REPO / "results/sember/study_h/data/sember_grounding.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            cat = rec.get("question_category", "")
            if cat == EXCLUDE_CAT:
                continue
            qt  = float(rec["question_time"])
            aet = float(rec["answer_end_time"])
            dist = qt - aet
            if dist < 0:
                continue  # exclude the 10 artifact records
            cat_distances[cat].append(dist)

    # Bins: [0,1), [1,5), [5,15), [15,30), [30,60), [60,120), [120,300), [300+)
    bin_edges = [0, 1, 5, 15, 30, 60, 120, 300, 10000]
    bin_labels = ["[0,1)", "[1,5)", "[5,15)", "[15,30)", "[30,60)", "[60,120)", "[120,300)", "300+"]
    n_bins = len(bin_labels)

    def assign_bins(dists):
        counts = np.zeros(n_bins)
        for d in dists:
            for bi in range(n_bins):
                if bin_edges[bi] <= d < bin_edges[bi + 1]:
                    counts[bi] += 1
                    break
        return counts

    # Overall (excluding counting)
    all_dists = [d for dists in cat_distances.values() for d in dists]
    overall_counts = assign_bins(all_dists)
    overall_n = len(all_dists)

    # overall from JSON (for cross-check — includes counting)
    json_overall_n = sum(b["count"] for b in bins_data)

    # Compute median and p90 of all_dists
    sorted_all = sorted(all_dists)
    n_all = len(sorted_all)
    median_val = sorted_all[n_all // 2]
    p90_val    = sorted_all[int(0.9 * n_all)]

    CAT_COLORS = {
        "location_trace":               C["blue"],
        "visual_detail_recall":         C["violet"],
        "sequential_action":            C["orange"],
        "time_duration":                C["yellow"],
        "temporal_ordering_recognition": C["red"],
        "object_comparison":            "#44AA99",
        "spatial_aware_reasoning":      "#DDCC77",
    }
    CAT_LABELS = {
        "location_trace":               "Location trace",
        "visual_detail_recall":         "Visual detail recall",
        "sequential_action":            "Sequential action",
        "time_duration":                "Time duration",
        "temporal_ordering_recognition": "Temporal ordering",
        "object_comparison":            "Object comparison",
        "spatial_aware_reasoning":      "Spatial aware",
    }

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)

    # Plot overall as grey bars
    bar_w = 0.6
    xs = np.arange(n_bins)
    fracs = overall_counts / overall_n
    ax.bar(xs, fracs, width=bar_w, color=C["light_grey"], zorder=1, label=f"Overall (n={overall_n:,})")

    # Overlay per-category as step lines
    for cat, dists in sorted(cat_distances.items(), key=lambda x: -len(x[1])):
        cat_counts = assign_bins(dists)
        cat_fracs  = cat_counts / len(dists) if dists else cat_counts
        ax.step(xs, cat_fracs,
                where="mid", color=CAT_COLORS.get(cat, C["grey"]),
                linewidth=1.5, label=CAT_LABELS.get(cat, cat))

    # Mark median and p90
    def dist_to_bin(d):
        for bi in range(n_bins):
            if bin_edges[bi] <= d < bin_edges[bi + 1]:
                return bi
        return n_bins - 1

    median_bin = dist_to_bin(median_val)
    p90_bin    = dist_to_bin(p90_val)
    ax.axvline(median_bin, color=C["dark"], linewidth=1.5, linestyle="--",
               label=f"Median ({median_val:.0f}s)")
    ax.axvline(p90_bin, color=C["dark"], linewidth=1.5, linestyle=":",
               label=f"p90 ({p90_val:.0f}s)")

    ax.set_xticks(xs)
    ax.set_xticklabels(bin_labels, rotation=30, ha="right", fontsize=FONT_TICK)
    ax.set_xlabel("Nearest evidence distance (s)", fontsize=FONT_LABEL)
    ax.set_ylabel("Fraction of questions", fontsize=FONT_LABEL)
    ax.text(0.98, 0.97,
            f"n={overall_n:,} (counting_objects_events excluded)\n"
            f"Median = {median_val:.0f}s  |  p90 = {p90_val:.0f}s\n"
            "(median 21s in committed report includes counting)",
            transform=ax.transAxes, ha="right", va="top", fontsize=9, color=C["grey"])
    ax.legend(fontsize=9, frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.82))
    fig.tight_layout()
    save(fig, "B_sember_evidence_distance")

    return {
        "overall_n": overall_n,
        "json_overall_n": json_overall_n,
        "median_s": median_val,
        "p90_s": p90_val,
        "per_cat_n": {cat: len(dists) for cat, dists in cat_distances.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLOT C — S-EMBER 4B vs 8B per-category accuracy (SPARSE arm, n=459 each)
# Source: results/sember/study_i3/study_i3_results.json, B_by_category
# ─────────────────────────────────────────────────────────────────────────────
def plot_C():
    i3 = json.load(open(REPO / "results/sember/study_i3/study_i3_results.json"))
    bc = i3["B_by_category"]
    cats = [k for k in bc.keys() if not k.startswith("_")]

    CAT_SHORT = {
        "time_duration":                 "Time\nduration",
        "visual_detail_recall":          "Visual\ndetail",
        "sequential_action":             "Sequential\naction",
        "location_trace":                "Location\ntrace",
        "spatial_aware_reasoning":       "Spatial\naware",
        "object_comparison":             "Object\ncomparison",
        "temporal_ordering_recognition": "Temporal\nordering",
    }

    # Sort cats by 4B accuracy descending
    cats_sorted = sorted(cats, key=lambda c: bc[c]["qwen3vl4b"]["SPARSE"]["acc"], reverse=True)

    n_cats = len(cats_sorted)
    xs     = np.arange(n_cats)
    w      = 0.32

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)

    for i, (model_key, label, color, offset) in enumerate([
        ("qwen3vl4b", "4B Thinking", C["blue"],   -w/2),
        ("qwen3vl8b", "8B Thinking", C["orange"],  w/2),
    ]):
        accs   = []
        ci_los = []
        ci_his = []
        ns     = []
        for cat in cats_sorted:
            d = bc[cat][model_key]["SPARSE"]
            accs.append(d["acc"])
            ci_los.append(d["ci_lo"])
            ci_his.append(d["ci_hi"])
            ns.append(d["n"])

        accs   = np.array(accs)
        ci_los = np.array(ci_los)
        ci_his = np.array(ci_his)

        bars = ax.bar(xs + offset, accs, width=w, color=color, label=label, zorder=2)
        ax.errorbar(xs + offset, accs,
                    yerr=[accs - ci_los, ci_his - accs],
                    fmt="none", color="black", capsize=3, linewidth=1, zorder=3)
        for xi, (bar, n) in enumerate(zip(bars, ns)):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + (ci_his[xi] - accs[xi]) + 0.01,
                    f"n={n}", ha="center", va="bottom", fontsize=8, color=C["dark"])

    # 20% random baseline
    ax.axhline(0.2, color=C["grey"], linewidth=1.5, linestyle="--", label="20% random baseline", zorder=1)

    ax.set_xticks(xs)
    ax.set_xticklabels([CAT_SHORT.get(c, c) for c in cats_sorted], fontsize=FONT_TICK)
    ax.set_ylabel("Accuracy — SPARSE arm\n(16 frames uniform, greedy decode)", fontsize=FONT_LABEL)
    ax.set_ylim(0, 0.65)
    ax.legend(fontsize=FONT_ANNOT, frameon=False, loc="upper right")
    ax.text(0.98, 0.02,
            "Models: Qwen3-VL-4B-Instruct and 8B-Instruct\nArm: SPARSE = 16 frames uniform over [0, question_time]",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color=C["grey"],
            style="italic")
    fig.tight_layout()
    save(fig, "C_sember_4b_vs_8b")

    return {cat: {m: bc[cat][m]["SPARSE"]["acc"] for m in ["qwen3vl4b","qwen3vl8b"]}
            for cat in cats_sorted}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT D — ERQA paired outcome matrix (2×2 McNemar)
# Source: results/erqa/study_k/study_k_results.json, gate_overall + arm_accuracies
# Aggregation: majority vote across 3 THINKING seeds (as in study analysis)
# ─────────────────────────────────────────────────────────────────────────────
def plot_D():
    # Fix 5: compute all four cells directly from trials using majority vote.
    trials = [json.loads(l) for l in open(REPO / "results/erqa/study_k/study_k_trials.jsonl")]
    instruct_bool = {t["question_id"]: (t["correct"] == "True" or t["correct"] is True)
                     for t in trials if t["arm"] == "INSTRUCT"}
    think_by_q = defaultdict(list)
    for t in trials:
        if t["arm"] == "THINKING":
            think_by_q[t["question_id"]].append(t["correct"] == "True" or t["correct"] is True)
    think_majority = {qid: (sum(v) > len(v) / 2) for qid, v in think_by_q.items()}

    a = b = c = d = 0
    for qid in instruct_bool:
        ic = instruct_bool[qid]
        tc = think_majority.get(qid, False)
        if ic and tc:      a += 1
        elif not ic and tc: b += 1
        elif ic and not tc: c += 1
        else:              d += 1
    n = a + b + c + d

    # Cross-check b and c against committed gate_overall
    k_res = json.load(open(REPO / "results/erqa/study_k/study_k_results.json"))
    assert b == k_res["gate_overall"]["b"], f"b mismatch: {b} != {k_res['gate_overall']['b']}"
    assert c == k_res["gate_overall"]["c"], f"c mismatch: {c} != {k_res['gate_overall']['c']}"
    p = k_res["gate_overall"]["pval"]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.axis("off")

    cells = [
        [a, b],
        [c, d],
    ]
    assert cells[0][0] == a and cells[1][1] == d
    assert cells[0][1] == b, "top-right must be THINKING-correct / INSTRUCT-wrong"
    assert cells[1][0] == c, "bottom-left must be THINKING-wrong / INSTRUCT-correct"

    col_labels = ["INSTRUCT\ncorrect", "INSTRUCT\nwrong"]
    row_labels = ["THINKING\ncorrect", "THINKING\nwrong"]

    # Draw grid
    CELL_W, CELL_H = 1.8, 1.2
    x0, y0 = 0.5, 0.5

    for ri in range(2):
        for ci in range(2):
            x = x0 + ci * CELL_W
            y = y0 + (1 - ri) * CELL_H
            is_discordant = (ri == 0 and ci == 1) or (ri == 1 and ci == 0)
            facecolor = "#E8F4FD" if not is_discordant else "#FDE8F4"
            rect = mpatches.FancyBboxPatch(
                (x, y), CELL_W, CELL_H,
                boxstyle="round,pad=0.05",
                facecolor=facecolor,
                edgecolor=C["dark"], linewidth=1.5,
            )
            ax.add_patch(rect)
            count = cells[ri][ci]
            ax.text(x + CELL_W / 2, y + CELL_H * 0.6, str(count),
                    ha="center", va="center", fontsize=28, fontweight="bold",
                    color=C["dark"])
            label = ""
            if ri == 0 and ci == 1:
                label = f"b = {count}\n(THINKING wins)"
            elif ri == 1 and ci == 0:
                label = f"c = {count}\n(INSTRUCT wins)"
            if label:
                ax.text(x + CELL_W / 2, y + CELL_H * 0.22, label,
                        ha="center", va="center", fontsize=10, color=C["dark"])

    # Row / column headers
    for ci, lbl in enumerate(col_labels):
        ax.text(x0 + ci * CELL_W + CELL_W / 2, y0 + 2 * CELL_H + 0.15, lbl,
                ha="center", va="bottom", fontsize=FONT_LABEL, fontweight="bold")
    for ri, lbl in enumerate(row_labels):
        ax.text(x0 - 0.15, y0 + (1 - ri) * CELL_H + CELL_H / 2, lbl,
                ha="right", va="center", fontsize=FONT_LABEL, fontweight="bold")

    ax.text(x0 + CELL_W, y0 - 0.35,
            f"McNemar p = {p:.4f}  (b={b}, c={c}, n={n}, majority vote across 3 THINKING seeds)",
            ha="center", va="top", fontsize=FONT_ANNOT, color=C["dark"])

    ax.set_xlim(-0.2, x0 + 2 * CELL_W + 0.2)
    ax.set_ylim(y0 - 0.7, y0 + 2 * CELL_H + 0.5)
    fig.tight_layout()
    save(fig, "D_erqa_mcnemar")

    return {"a": a, "b": b, "c": c, "d": d, "n": n, "pval": p}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT E — ERQA think-tokens vs correctness, within category
# Source: results/erqa/study_k/study_k_trials.jsonl (THINKING arm, 3 seeds)
# Computed WITHIN category only (not pooled).
# ─────────────────────────────────────────────────────────────────────────────
def plot_E():
    trials = [json.loads(l) for l in open(REPO / "results/erqa/study_k/study_k_trials.jsonl")]
    thinking = [t for t in trials if t["arm"] == "THINKING"]

    cat_data = defaultdict(lambda: {"tokens": [], "correct": []})
    for t in thinking:
        cat = t["category"]
        cat_data[cat]["tokens"].append(int(t["n_think_tokens"]))
        cat_data[cat]["correct"].append(int(t["correct"] == "True" or t["correct"] is True))

    HIGHLIGHT_CATS = {"Spatial Reasoning", "Task Reasoning"}
    cats = sorted(cat_data.keys())
    n_cats = len(cats)

    fig, axes = plt.subplots(2, 4, figsize=(14, 7), sharey=False)
    axes = axes.flatten()

    # Load pre-computed within-category correlations from results
    k_results = json.load(open(REPO / "results/erqa/study_k/study_k_results.json"))
    corr_lookup = {}
    for key, val in k_results["think_vs_correct_corr"].items():
        if key.startswith("cat:"):
            cat = key[4:]
            corr_lookup[cat] = val

    for ax_i, (cat, ax) in enumerate(zip(cats, axes)):
        tokens  = np.array(cat_data[cat]["tokens"])
        correct = np.array(cat_data[cat]["correct"])
        n_pts   = len(tokens)

        # Quartile bins within this category
        q_cuts = np.percentile(tokens, [0, 25, 50, 75, 100])
        bin_labels_q = []
        bin_accs = []
        bin_ns   = []
        bin_ci_lo = []
        bin_ci_hi = []

        for qi in range(4):
            if qi < 3:
                mask = (tokens >= q_cuts[qi]) & (tokens < q_cuts[qi + 1])
            else:
                mask = tokens >= q_cuts[qi]
            subset = correct[mask]
            n_sub  = len(subset)
            acc    = subset.mean() if n_sub > 0 else 0.0
            lo, hi = wilson_ci(subset.sum(), n_sub)
            bin_labels_q.append(f"Q{qi+1}\n≤{q_cuts[qi+1]:.0f}t")
            bin_accs.append(acc)
            bin_ns.append(n_sub)
            bin_ci_lo.append(lo)
            bin_ci_hi.append(hi)

        xs = np.arange(4)
        highlight = cat in HIGHLIGHT_CATS
        color = C["blue"] if not highlight else C["orange"]

        bars = ax.bar(xs, bin_accs, color=color, alpha=0.85, width=0.6)
        ax.errorbar(xs, bin_accs,
                    yerr=[np.array(bin_accs) - np.array(bin_ci_lo),
                          np.array(bin_ci_hi) - np.array(bin_accs)],
                    fmt="none", color="black", capsize=3, linewidth=1)
        for xi, (acc, n) in enumerate(zip(bin_accs, bin_ns)):
            ax.text(xi, acc + 0.03, f"n={n}", ha="center", fontsize=7)

        ax.set_xticks(xs)
        ax.set_xticklabels([f"Q{i+1}" for i in range(4)], fontsize=9)
        ax.set_ylim(0, 0.85)
        ax.set_title(cat, fontsize=10, fontweight="bold" if highlight else "normal")

        if cat in corr_lookup:
            r = corr_lookup[cat]["r"]
            pv = corr_lookup[cat]["pval"]
            n_r = corr_lookup[cat]["n"]
            pv_str = f"p={pv:.3f}" if pv >= 0.001 else "p<0.001"
            ax.text(0.97, 0.97, f"r={r:.2f}, {pv_str}\n(n={n_r})",
                    transform=ax.transAxes, ha="right", va="top", fontsize=8, color=C["dark"])

        if ax_i % 4 == 0:
            ax.set_ylabel("Accuracy", fontsize=FONT_TICK)

    # Hide last unused axis if any
    for ax in axes[n_cats:]:
        ax.axis("off")

    fig.suptitle("Within-category: think-token quartile vs accuracy (THINKING arm only; NOT pooled across categories)",
                 fontsize=10, style="italic", y=1.01)
    fig.tight_layout()
    save(fig, "E_erqa_think_vs_correct")

    return {cat: {
        "n": len(cat_data[cat]["tokens"]),
        "r": corr_lookup.get(cat, {}).get("r"),
        "pval": corr_lookup.get(cat, {}).get("pval"),
    } for cat in cats}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT F — SiGNgapore2D truncation rate by complexity
# Source: reports/study_j_signs.md §1 (aggregate bins, reproduced here)
# 162 THINKING signs at 2048-token budget.
# ─────────────────────────────────────────────────────────────────────────────
def plot_F():
    # Reconstruct n_gt per sign from /tmp/sign-understanding/gt/gt_annotation.json
    # (matched against committed results/signs/study_j/study_j_trials.jsonl).
    # n_gt = len(text_labels) + len(symbol_labels) - len(mixed)  (matching StudyJ definition)
    GT_PATH = Path("/tmp/sign-understanding/gt/gt_annotation.json")
    J_PATH  = REPO / "results/signs/study_j/study_j_trials.jsonl"

    if GT_PATH.exists():
        gt = json.load(open(GT_PATH))
        sign_ngt = {}
        for entry in gt:
            img_path = entry["imagePath"]
            stem = img_path[:-4]
            for ann in entry["annotation"]:
                crop_name = f"{stem}_{ann['objectID']}.jpg"
                tl = ann.get("text labels") or {}
                sl = ann.get("symbol labels") or {}
                ml = ann.get("mixed") or {}
                if not isinstance(tl, dict): tl = {}
                if not isinstance(sl, dict): sl = {}
                if not isinstance(ml, dict): ml = {}
                sign_ngt[crop_name] = len(tl) + len(sl) - len(ml)

        j_trials = [json.loads(l) for l in open(J_PATH)]
        thinking = [t for t in j_trials if t["arm"] == "THINKING"]

        bin_counts = {"low": [0,0], "mid": [0,0], "high": [0,0], "other": [0,0]}
        for t in thinking:
            crop = t["crop_name"]
            if crop not in sign_ngt:
                continue
            n = sign_ngt[crop]
            trunc = str(t.get("truncated", "False")).lower() == "true"
            if n <= 0:   key = "other"
            elif n <= 2: key = "low"
            elif n <= 5: key = "mid"
            else:        key = "high"
            bin_counts[key][0] += 1          # total
            bin_counts[key][1] += int(trunc) # truncated
        note = "Reconstructed from GT annotation + committed trials"
    else:
        # Fallback to report aggregates (n_gt not in trials; GT file not available)
        bin_counts = {
            "low":   [39, 21],
            "mid":   [61, 55],
            "high":  [45, 44],
            "other": [17, 12],  # note: report's 12 sums to 132 (inconsistency with 130 overall)
        }
        note = "Transcribed from reports/study_j_signs.md §1 (GT file unavailable)"

    bins = [
        ("low\n(1–2 items)",  bin_counts["low"][0],   bin_counts["low"][1]),
        ("mid\n(3–5 items)",  bin_counts["mid"][0],   bin_counts["mid"][1]),
        ("high\n(6+ items)",  bin_counts["high"][0],  bin_counts["high"][1]),
        ("other\n(≤0 items)", bin_counts["other"][0], bin_counts["other"][1]),
    ]
    labels = [b[0] for b in bins]
    ns     = [b[1] for b in bins]
    ks     = [b[2] for b in bins]
    rates  = [k / n for k, n in zip(ks, ns)]
    ci_lo  = [wilson_ci(k, n)[0] for k, n in zip(ks, ns)]
    ci_hi  = [wilson_ci(k, n)[1] for k, n in zip(ks, ns)]

    xs = np.arange(len(bins))
    COLORS = [C["blue"], C["violet"], C["red"], C["grey"]]

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)
    bars = ax.bar(xs, rates, width=0.5, color=COLORS, zorder=2)
    ax.errorbar(xs, rates,
                yerr=[np.array(rates) - np.array(ci_lo),
                      np.array(ci_hi) - np.array(rates)],
                fmt="none", color="black", capsize=5, linewidth=1.5, zorder=3)

    for xi, (rate, n, k) in enumerate(zip(rates, ns, ks)):
        ax.text(xi, rate + (ci_hi[xi] - rate) + 0.015,
                f"n={n}\n({k}/{n})", ha="center", va="bottom", fontsize=FONT_ANNOT)

    # Overall 80.2% line
    ax.axhline(0.802, color=C["orange"], linewidth=1.5, linestyle="--", zorder=1,
               label="Overall 80.2% (130/162)")

    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=FONT_TICK)
    ax.set_xlabel("Complexity bin (n GT items)", fontsize=FONT_LABEL)
    ax.set_ylabel("Truncation rate at 2048-token budget", fontsize=FONT_LABEL)
    ax.set_ylim(0, 1.15)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.legend(fontsize=FONT_ANNOT, frameon=False)
    ax.text(0.98, 0.01, note, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color=C["grey"], style="italic")
    fig.tight_layout()
    save(fig, "F_signs_truncation_by_complexity")

    return {b[0]: {"n": b[1], "k": b[2], "rate": b[2]/b[1]} for b in bins}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT G — SiGNgapore2D survival curve (regenerated from study_j2 trials)
# Source: results/signs/study_j2/study_j2_trials.jsonl
# ─────────────────────────────────────────────────────────────────────────────
def plot_G():
    j2_trials = [json.loads(l) for l in
                 open(REPO / "results/signs/study_j2/study_j2_trials.jsonl")]

    # All trials use max_new_tokens=24576 (single budget). Survival at budget B =
    # fraction NOT terminated (think_tokens >= B, i.e., truncated or think exhausted).
    # We compute: at budget B, would this sign have been truncated?
    # A sign is truncated at B iff its actual n_think_tokens >= B (i.e., it hadn't
    # closed </think> by B).  If the sign DID close (think_closed=True), it terminated
    # at n_think_tokens < 24576; survival at B = (n_think_tokens > B).

    def not_terminated_at(trial, budget):
        closed = str(trial["think_closed"]).lower() == "true"
        toks   = int(trial["n_think_tokens"])
        if not closed:
            return True   # never terminated within 24576
        return toks > budget

    budgets = [1024, 2048, 4096, 8192, 16384, 24576]

    def bin_of(trial):
        n = int(trial["n_gt"])
        if n <= 0:   return "other (≤0)"
        if n <= 2:   return "low (1–2)"
        if n <= 5:   return "mid (3–5)"
        return "high (6+)"

    bins = ["low (1–2)", "mid (3–5)", "high (6+)", "other (≤0)"]
    BIN_COLORS = {
        "low (1–2)":   C["blue"],
        "mid (3–5)":   C["violet"],
        "high (6+)":   C["red"],
        "other (≤0)":  C["grey"],
    }
    overall_n = len(j2_trials)

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)

    # Overall
    overall_surv = [sum(not_terminated_at(t, B) for t in j2_trials) / overall_n for B in budgets]
    ax.plot(range(len(budgets)), overall_surv, color=C["dark"], linewidth=2.5,
            marker="o", label=f"Overall (n={overall_n})", zorder=5)
    for i, (sv, B) in enumerate(zip(overall_surv, budgets)):
        ax.annotate(f"{sv:.0%}", (i, sv), textcoords="offset points",
                    xytext=(5, 5), fontsize=9, color=C["dark"])

    # Per-bin
    for b_label in bins:
        subset = [t for t in j2_trials if bin_of(t) == b_label]
        if not subset:
            continue
        surv = [sum(not_terminated_at(t, B) for t in subset) / len(subset) for B in budgets]
        ax.plot(range(len(budgets)), surv,
                color=BIN_COLORS[b_label], linewidth=1.5, marker="s",
                linestyle="--", label=f"{b_label} (n={len(subset)})")

    # Shade flat region (16384 → 24576)
    flat_lo = len(budgets) - 2
    flat_hi = len(budgets) - 1
    ax.axvspan(flat_lo, flat_hi, alpha=0.1, color=C["yellow"],
               label="Asymptote region (budget ≥16K)")

    # Annotate 20% asymptote
    ax.axhline(0.20, color=C["orange"], linewidth=1, linestyle=":", zorder=1)
    ax.text(flat_hi - 0.05, 0.22, "20% asymptote", ha="right", fontsize=FONT_ANNOT,
            color=C["orange"])

    ax.set_xticks(range(len(budgets)))
    ax.set_xticklabels([f"{b//1000}K" for b in budgets], fontsize=FONT_TICK)
    ax.set_xlabel("Token budget (max_new_tokens)", fontsize=FONT_LABEL)
    ax.set_ylabel("Fraction NOT terminated", fontsize=FONT_LABEL)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.legend(fontsize=FONT_ANNOT, frameon=False, loc="upper right")
    fig.tight_layout()
    save(fig, "G_signs_survival_curve")

    return {B: {
        "overall": sum(not_terminated_at(t, B) for t in j2_trials) / overall_n,
    } for B in budgets}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT H — Per-sign failure rate across seeds (KEY PLOT)
# Source: results/signs/study_j4/study_j4_trials.jsonl
# 14 signs × 5 seeds; corrected pooled rate 13-16% as horizontal band.
# ─────────────────────────────────────────────────────────────────────────────
def plot_H():
    j4_trials = [json.loads(l) for l in
                 open(REPO / "results/signs/study_j4/study_j4_trials.jsonl")]

    by_crop = defaultdict(lambda: {"fails": 0, "total": 0, "role": "?"})
    for t in j4_trials:
        crop = t["crop_name"]
        by_crop[crop]["total"] += 1
        by_crop[crop]["fails"] += int(str(t["truncated"]).lower() == "true")
        by_crop[crop]["role"]   = t.get("role", "?")

    # Sort descending by fail rate, then by name
    entries = sorted(by_crop.items(), key=lambda x: (-x[1]["fails"], x[0]))
    signs   = [e[0] for e in entries]
    rates   = [e[1]["fails"] / e[1]["total"] for e in entries]
    roles   = [e[1]["role"] for e in entries]
    ns      = [e[1]["total"] for e in entries]
    fails   = [e[1]["fails"] for e in entries]

    # Short labels
    short_labels = [s.replace("_frame", "").replace(".jpg", "").replace("_0", "")[:16] for s in signs]

    ROLE_COLOR = {"cap_hit": C["cap"], "control": C["ctrl"]}
    colors = [ROLE_COLOR.get(r, C["grey"]) for r in roles]

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)
    xs = np.arange(len(signs))

    # Shade 0% and 100% as "input-determined would look like this"
    ax.axhspan(0, 0.08, color=C["grey"], alpha=0.12, zorder=0)
    ax.axhspan(0.92, 1.0, color=C["grey"], alpha=0.12, zorder=0)
    ax.text(len(signs) - 0.3, 0.04, "input-determined\n(always-safe zone)", ha="right",
            fontsize=9, color=C["grey"], style="italic")
    ax.text(len(signs) - 0.3, 0.96, "input-determined\n(always-fail zone)", ha="right",
            fontsize=9, color=C["grey"], style="italic", va="top")

    bars = ax.bar(xs, rates, width=0.6, color=colors, zorder=2)

    # Corrected pooled rate band: 13–16%
    ax.axhspan(0.13, 0.16, color=C["yellow"], alpha=0.35, zorder=1)
    ax.axhline(0.161, color=C["yellow"], linewidth=1.5, linestyle="--", zorder=2)
    ax.text(len(signs) - 0.4, 0.165,
            "corrected per-attempt rate\n(selection-adjusted): 13–16%",
            ha="right", va="bottom", fontsize=9, color="#8B6914",
            style="italic")

    # Annotate raw pooled rate
    total_fails = sum(fails)
    total_n     = sum(ns)
    ax.text(0.01, 0.97,
            f"Raw pooled: {total_fails}/{total_n} = {total_fails/total_n:.1%}  "
            f"(inflated — 8 cap-hit draws on seed=42 determined by selection criterion)\n"
            f"Corrected: 10/62 = 16.1% unbiased draws; 4/30 = 13.3% controls only",
            transform=ax.transAxes, ha="left", va="top", fontsize=9,
            color=C["dark"],
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C["light_grey"], alpha=0.9))

    # Annotate each bar
    for xi, (rate, n, k) in enumerate(zip(rates, ns, fails)):
        ax.text(xi, rate + 0.02, f"{k}/{n}", ha="center", fontsize=9, color=C["dark"])

    # Legend for roles
    legend_patches = [
        mpatches.Patch(color=C["cap"],  label="Former cap-hit (StudyJ2)"),
        mpatches.Patch(color=C["ctrl"], label="Control (completed StudyJ2)"),
        mpatches.Patch(color=C["yellow"], alpha=0.5,
                       label="Corrected per-attempt rate 13–16%"),
    ]
    ax.legend(handles=legend_patches, fontsize=FONT_ANNOT, frameon=False,
              loc="upper right", bbox_to_anchor=(1.0, 0.70))

    ax.set_xticks(xs)
    ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=FONT_TICK - 2)
    ax.set_ylabel("Failure rate (truncations / 5 seeds)", fontsize=FONT_LABEL)
    ax.set_ylim(0, 1.10)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_xlabel("Sign (sorted by failure rate)", fontsize=FONT_LABEL)
    fig.tight_layout()
    save(fig, "H_signs_per_sign_failure_rate")

    return {s: {"role": r, "rate": rate, "k": k, "n": n}
            for s, r, rate, k, n in zip(signs, roles, rates, fails, ns)}


# ─────────────────────────────────────────────────────────────────────────────
# PLOT I — Thinking gain by benchmark (published Qwen3-VL numbers)
# Source: Qwen3-VL Technical Report arXiv 2511.21631 Table 4 (hardcoded)
# NOT our measurements.
# ─────────────────────────────────────────────────────────────────────────────
def plot_I():
    # arXiv 2511.21631 Table 4, 4B model: Instruct → Thinking gain
    # (benchmark, instruct_score, thinking_score, group)
    # Fix 3: three groups replacing the incorrect symbolic/spatial binary split:
    #   multi_image_knowledge: MUIRBench (multi-image reasoning), MMMU, MMMU-Pro (knowledge/symbolic)
    #   grounding_spatial:     RefSpatialBench, VSI-Bench, SUNRGBD, RoboSpatialHome, EmbSpatialBench
    #   mixed_unclassified:    ERQA (second-largest gain; not cleanly spatial or symbolic),
    #                          MVBench (video understanding, mixed)
    data = [
        # benchmark                  instruct  thinking  group
        ("MUIRBench",               63.8,     75.0,     "multi_image_knowledge"),
        ("ERQA",                    41.3,     47.3,     "mixed_unclassified"),
        ("MMMU-Pro",                53.2,     57.0,     "multi_image_knowledge"),
        ("MMMU",                    67.4,     70.8,     "multi_image_knowledge"),
        ("EmbSpatialBench",         79.6,     80.7,     "grounding_spatial"),
        ("MVBench",                 68.9,     69.3,     "mixed_unclassified"),
        ("RoboSpatialHome",         61.7,     63.2,     "grounding_spatial"),
        ("RefSpatialBench",         46.6,     45.3,     "grounding_spatial"),
        ("VSI-Bench",               59.3,     55.2,     "grounding_spatial"),
        ("SUNRGBD",                 34.7,     28.0,     "grounding_spatial"),
    ]
    # Sort by gain descending
    data = sorted(data, key=lambda x: x[2] - x[1], reverse=True)

    benchmarks = [d[0] for d in data]
    gains      = [d[2] - d[1] for d in data]
    categories = [d[3] for d in data]

    CAT_COLOR = {
        "multi_image_knowledge": C["blue"],
        "grounding_spatial":     C["orange"],
        "mixed_unclassified":    C["grey"],
    }
    colors = [CAT_COLOR[c] for c in categories]

    fig, ax = plt.subplots(figsize=SLIDE_SIZE)
    xs = np.arange(len(data))
    bars = ax.barh(xs, gains, color=colors, height=0.6, zorder=2)

    ax.axvline(0, color=C["dark"], linewidth=1, zorder=3)

    for xi, (gain, bm, cat) in enumerate(zip(gains, benchmarks, categories)):
        ha = "left" if gain >= 0 else "right"
        offset = 0.15 if gain >= 0 else -0.15
        ax.text(gain + offset, xi, f"{gain:+.1f}pp", va="center", ha=ha,
                fontsize=FONT_ANNOT, color=C["dark"])

    # Highlight ERQA
    erqa_i = benchmarks.index("ERQA")
    ax.get_children()  # force draw
    ax.annotate("← our benchmark", xy=(gains[erqa_i], erqa_i),
                xytext=(gains[erqa_i] + 0.5, erqa_i - 0.5),
                fontsize=10, color=C["dark"],
                arrowprops=dict(arrowstyle="-", color=C["dark"]))

    ax.set_yticks(xs)
    ax.set_yticklabels(benchmarks, fontsize=FONT_TICK)
    ax.set_xlabel("4B Thinking − 4B Instruct (published pp)", fontsize=FONT_LABEL)
    ax.invert_yaxis()

    legend_patches = [
        mpatches.Patch(color=C["blue"],   label="Multi-image / knowledge reasoning"),
        mpatches.Patch(color=C["orange"], label="Grounding / 3D spatial"),
        mpatches.Patch(color=C["grey"],   label="Mixed / unclassified (ERQA, MVBench)"),
    ]
    ax.legend(handles=legend_patches, fontsize=FONT_ANNOT, frameon=False, loc="lower right")

    # Note about ERQA classification
    ax.text(0.01, 0.01,
            "ERQA = 2nd-largest gain (+6.0pp) but does not fit cleanly\n"
            "into multi-image/knowledge or spatial — classified as mixed.",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8.5,
            color=C["grey"], style="italic")

    ax.text(0.98, 0.01,
            "Source: Qwen3-VL Technical Report, arXiv:2511.21631, Table 4\nNOT our measurements.",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=9, style="italic", color=C["grey"])

    fig.tight_layout()
    save(fig, "I_thinking_gain_published")

    return {b: g for b, g in zip(benchmarks, gains)}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Advisor plots — CPU only, no GPU ===")
    import subprocess
    gpu_proc = subprocess.run(["pgrep", "-f", "study_j5_prompt_power"], capture_output=True)
    if gpu_proc.returncode == 0:
        print(f"  [OK] StudyJ5 is still running (pid {gpu_proc.stdout.decode().strip()}); "
              "we read only committed files and do not touch it.")

    results = {}

    print("\n[A] Workload screening table")
    plot_A()

    print("\n[B] S-EMBER evidence-distance distribution")
    results["B"] = plot_B()

    print("\n[C] S-EMBER 4B vs 8B per-category accuracy")
    results["C"] = plot_C()

    print("\n[D] ERQA paired outcome matrix")
    results["D"] = plot_D()

    print("\n[E] ERQA think-tokens vs correctness, within category")
    results["E"] = plot_E()

    print("\n[F] SiGNgapore2D truncation rate by complexity")
    results["F"] = plot_F()

    print("\n[G] SiGNgapore2D survival curve")
    results["G"] = plot_G()

    print("\n[H] Per-sign failure rate across seeds")
    results["H"] = plot_H()

    print("\n[I] Thinking gain by benchmark (published)")
    results["I"] = plot_I()

    # Dump sanity numbers for manifest
    sanity_path = REPO / "figures" / "advisor_2026_09_30" / "_sanity_numbers.json"
    with open(sanity_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSanity numbers dumped to {sanity_path.name}")
    print("=== Done ===")
