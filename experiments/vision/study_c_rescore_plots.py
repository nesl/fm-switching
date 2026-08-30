#!/usr/bin/env python3
"""Plotting-only companion for study_c_rescore.py."""
import csv
import statistics
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

TRIALS_CSV = "results/vision/study_c/study_c_trials.csv"
PLOTS_DIR = "figures/vision"
LEVELS = ["L1", "L2", "L3", "L4"]
MODELS = ["qwenvl3b", "qwenvl7b"]
MODES = ["direct", "stepwise"]


def spearman(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    def rank(arr):
        si = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n and arr[si[j]] == arr[si[i]]:
                j += 1
            avg = (i + j - 1) / 2.0 + 1
            for k in range(i, j):
                ranks[si[k]] = avg
            i = j
        return ranks
    rx, ry = rank(xs), rank(ys)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


with open(TRIALS_CSV) as f:
    rows = list(csv.DictReader(f))

cells = {}
for model in MODELS:
    for mode in MODES:
        for level in LEVELS:
            ct = [r for r in rows if r["model"] == model and r["mode"] == mode and r["level"] == level]
            pars = []
            for r in ct:
                ps = r["parse_status"]
                pr = r["parsed_answer"]
                gt = int(r["n_persons_gt"])
                if ps in ("ok", "fallback_last_number") and pr not in ("", "None", "nan"):
                    try:
                        pars.append({"gt": gt, "parsed": int(float(pr))})
                    except ValueError:
                        pass
            n_tot = len(ct)
            n_p = len(pars)
            gts = [p["gt"] for p in pars]
            preds = [p["parsed"] for p in pars]
            errors = [p - g for p, g in zip(preds, gts)]
            ex = sum(1 for e in errors if e == 0)
            w1 = sum(1 for e in errors if abs(e) <= 1)
            w2 = sum(1 for e in errors if abs(e) <= 2)
            rt25 = sum(1 for p, g in zip(preds, gts) if abs(p - g) / max(g, 1) <= 0.25)
            cells[(model, mode, level)] = {
                "n_total": n_tot, "n_parseable": n_p, "n_unparseable": n_tot - n_p,
                "exact_c": ex / n_tot,
                "w1_c": w1 / n_tot,
                "w2_c": w2 / n_tot,
                "rt25_c": rt25 / n_tot,
                "mean_error": sum(errors) / n_p if n_p else float("nan"),
                "median_error": statistics.median(errors) if errors else float("nan"),
                "spearman": spearman(gts, preds),
                "gts": gts, "preds": preds, "errors": errors,
            }

level_labels = ["L1\n(1 person)", "L2\n(2–3)", "L3\n(4–7)", "L4\n(8+)"]
x = np.arange(4)
col = {"qwenvl3b": "#1565C0", "qwenvl7b": "#B71C1C"}
ls = {"direct": "-", "stepwise": "--"}
mk = {"direct": "o", "stepwise": "s"}
lcolors = {"L1": "#43A047", "L2": "#1E88E5", "L3": "#FB8C00", "L4": "#E53935"}

# ── Figure 1: accuracy under three tolerances ──────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
for ax, (metric, title) in zip(axes, [
    ("exact_c", "Exact match"),
    ("w1_c", "Within-1 (|err|≤1)"),
    ("w2_c", "Within-2 (|err|≤2)"),
]):
    for model in MODELS:
        for mode in MODES:
            vals = [cells[(model, mode, lv)][metric] for lv in LEVELS]
            label = f"{'3B' if '3b' in model else '7B'} {mode}"
            ax.plot(x, vals, color=col[model], ls=ls[mode],
                    marker=mk[mode], label=label, linewidth=2, markersize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(level_labels, fontsize=9)
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("Accuracy (conservative denominator)")
    ax.set_title(title, fontsize=11)
    ax.grid(alpha=0.3)
axes[0].legend(fontsize=8, loc="lower left")
fig.suptitle("Study C Re-scoring — Accuracy vs Difficulty under Different Tolerances", fontsize=11)
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_accuracy.pdf", bbox_inches="tight")
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_accuracy.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: study_c_rescore_accuracy")

# ── Figure 2: signed error by level ────────────────────────────────────────
fig, axes = plt.subplots(2, 4, figsize=(15, 7), sharey=True)
rng = np.random.default_rng(42)
for mi, model in enumerate(MODELS):
    for li, level in enumerate(LEVELS):
        ax = axes[mi][li]
        for mode_i, mode in enumerate(MODES):
            errs = cells[(model, mode, level)]["errors"]
            if not errs:
                continue
            jitter_center = (mode_i - 0.5) * 0.3
            jx = [jitter_center + rng.uniform(-0.08, 0.08) for _ in errs]
            ax.scatter(jx, errs, alpha=0.3, color=col[model], s=12,
                       marker=mk[mode])
            med = statistics.median(errs)
            ax.scatter([jitter_center], [med], color=col[model], s=90,
                       zorder=5, marker="D", edgecolors="k", linewidths=0.6)
        ax.axhline(0, color="k", lw=1, ls="--")
        ax.set_title(f"{'3B' if '3b' in model else '7B'} / {level}", fontsize=10)
        ax.set_xticks([-0.3, 0.3])
        ax.set_xticklabels(["dir", "step"], fontsize=8)
        ax.grid(axis="y", alpha=0.3)
axes[0][0].set_ylabel("Signed error (parsed − GT)")
axes[1][0].set_ylabel("Signed error (parsed − GT)")
fig.suptitle("Study C Re-scoring — Signed Error by Level/Model (◆ = median)", fontsize=11)
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_errors.pdf", bbox_inches="tight")
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_errors.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: study_c_rescore_errors")

# ── Figure 3: parsed vs GT scatter ─────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(11, 10))
for mi, model in enumerate(MODELS):
    for moi, mode in enumerate(MODES):
        ax = axes[mi][moi]
        for level in LEVELS:
            s = cells[(model, mode, level)]
            if s["gts"]:
                ax.scatter(s["gts"], s["preds"],
                           alpha=0.35, color=lcolors[level], s=18, label=level)
        all_gt = [g for lv in LEVELS for g in cells[(model, mode, lv)]["gts"]]
        all_pred = [p for lv in LEVELS for p in cells[(model, mode, lv)]["preds"]]
        if all_gt:
            mx = max(max(all_gt), max(all_pred), 18) + 1
            ax.plot([0, mx], [0, mx], "k--", lw=1.2, label="y=x (exact)")
            ax.plot([0, mx], [1, mx + 1], color="gray", lw=0.7, ls=":")
            ax.plot([0, mx], [-1, mx - 1], color="gray", lw=0.7, ls=":")
            ax.set_xlim(-0.5, mx)
            ax.set_ylim(-0.5, mx)
        sp = spearman(all_gt, all_pred) if all_gt else float("nan")
        ax.set_xlabel("Ground truth (persons)")
        ax.set_ylabel("Parsed answer")
        ax.set_title(f"{'3B' if '3b' in model else '7B'} / {mode}  (ρ={sp:.3f})", fontsize=11)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8, loc="upper left")
fig.suptitle("Study C Re-scoring — Parsed Answer vs Ground Truth (dotted = ±1 band)", fontsize=11)
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_scatter.pdf", bbox_inches="tight")
plt.savefig(f"{PLOTS_DIR}/study_c_rescore_scatter.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: study_c_rescore_scatter")
print("All plots complete.")
