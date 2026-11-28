#!/usr/bin/env python3
"""Paper Figure 13: correct answers per GPU-second, GPU busy fraction, tokens/s per arm. OFFLINE, committed data.

Reads reports/figdata/F13.csv. Cells: the standard grid (1x memory, 16 devices, robot deadline 3.0 s, rq30, mix 40:40:20),
i.e. run_dir name <arm>_n16_s<4-7>_1200s_h27_3t_L3_epg_rq30 with an optional _rerun / _ms_rerun suffix; outage, rep2,
preD249, c3-11-2 mix and other variants are excluded. Per arm: mean over seeds with min and max. GPU busy fraction =
gpu_busy_s_measured / 1200 s (the per-run GPU budget_gpu_s, one GPU). Tokens/s = uncached_tokens_per_gpu_s (D174 uncached
tokens charged per measured GPU-second). usage: python3 -I f13_gpu_efficiency.py
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

STD = re.compile(r"^.+_n16_s([4-7])_1200s_h27_3t_L3_epg_rq30(_rerun|_ms_rerun)?$")
BUDGET_S = 1200.0
ARMS = [P.COVEX_RUNG3, "lmcache", "mooncake", "kvflow-prefetch", "attentionstore-prefetch", "warm-all-lru",
        "streamscout", "simplestream", "llf", "edf", "b7-edf-feasibility", "eco-llm", "querystream-proactive",
        "always-cloud-fcfs"]
METRICS = [("correct_per_gpu_s", "correct\nper GPU-s", 1.0),
           ("busy_frac", "GPU busy\nfraction", 1.0),
           ("uncached_tokens_per_gpu_s", "uncached tok.\nper GPU-s (k)", 1e-3)]


def ylab(a, mode):
    if a == P.COVEX_RUNG3:
        return (r"\textbf{" + P.legend_label(a) + "}") if mode == "pgf" else P.legend_label(a)
    return P.tex_name(a) if mode == "pgf" else P.display(a)


def main():
    rows = list(csv.DictReader(open(P.REPO / "reports/figdata/F13.csv")))
    pick = {}
    for r in rows:
        t = r["run_dir"].split("/")[-1]
        m = STD.match(t)
        if not m or r["cond_memory"] != "1x" or r["cond_n_devices"] != "16" or r["cond_deadline_s"] != "3.0":
            continue
        if r["cond_extras"] or r["correct_per_gpu_s"] in ("", None):
            continue
        key = (r["arm"], r["seed"])
        # prefer the rerun cell when both exist
        if key not in pick or m.group(2):
            pick[key] = r
    per = defaultdict(list)
    used = []
    for (arm, seed), r in sorted(pick.items()):
        if arm not in ARMS:
            continue
        v = {"correct_per_gpu_s": float(r["correct_per_gpu_s"]),
             "busy_frac": float(r["gpu_busy_s_measured"]) / BUDGET_S,
             "uncached_tokens_per_gpu_s": float(r["uncached_tokens_per_gpu_s"])}
        per[arm].append(v)
        used.append((arm, seed, r))
    arms = [a for a in ARMS if per.get(a)]
    missing = [a for a in ARMS if not per.get(a)]
    statuses = [P.arm_status(a, next(r["status"] for (x, s, r) in used if x == a)) for a in arms]
    # order: COVEX first, then by correct_per_gpu_s descending
    arms = [arms[0]] + sorted(arms[1:], key=lambda a: -np.mean([v["correct_per_gpu_s"] for v in per[a]]))

    def build(fig, mode):
        gs = fig.add_gridspec(1, 3, left=0.36, right=0.955, top=0.94, bottom=0.2, wspace=0.3)
        y = np.arange(len(arms))[::-1]
        for j, (k, lab, sc) in enumerate(METRICS):
            ax = fig.add_subplot(gs[0, j])
            P.style_axes(ax, xgrid=False)
            ax.xaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
            for yi, a in zip(y, arms):
                vals = np.array([v[k] for v in per[a]]) * sc
                col = P.COLORS[P.arm_class(a)] if P.arm_class(a) in P.COLORS else P.COLORS["stateless"]
                ax.barh(yi, vals.mean(), 0.7, color=col, lw=0)
                ax.plot([vals.min(), vals.max()], [yi, yi], color=P.COLORS["ink"], lw=0.7)
                ax.plot(vals, [yi] * len(vals), "|", color=P.COLORS["ink"], ms=3, mew=0.5)
            ax.set_yticks(y)
            if j == 0:
                ax.set_yticklabels([ylab(a, mode) for a in arms], fontsize=P.FS_TEXT)
            else:
                ax.set_yticklabels([])
            ax.set_xlabel(lab, fontsize=P.FS_AXLABEL)
            ax.set_ylim(-0.6, len(arms) - 0.4)
            ax.tick_params(axis="x", labelsize=P.FS_TEXT)
            if k == "busy_frac":
                ax.set_xlim(0, 1.0)
            else:
                ax.set_xlim(0, None)
            if j == 1:
                ax.set_xticks([0, 0.5, 1.0])
            if j == 2:
                ax.set_xticks([0, 3, 6])

    caption = ("Efficiency of the cloud GPU on the standard grid (16 devices, 1x memory, 3 s robot deadline, seeds 4 to 7): "
               "correct answers (robot plus single-shot) per measured GPU-second, GPU busy fraction of the 1200 s "
               "per-run budget, and D174 uncached tokens charged per GPU-second. Bars are the mean over the seeds "
               "present for the arm; marks show each seed. Arms with no committed GPU metrics (LMCache, Warm-all LRU) are not drawn. Blue is COVEX, dark grey stateful baselines, light grey "
               "stateless baselines.")
    extra = ("COVEX is the rung 3 covex-v6-fair-final stand-in (OLD); the DEV candidates covex-v6-fair-final-cand-tl "
             "and -sync are not in F13.csv; arms with blank GPU fields in every standard F13 row (not plotted): "
             + (", ".join(missing) or "none") + "; seeds missing per arm: "
             + "; ".join(f"{a} has {len(per[a])}/4" for a in arms if len(per[a]) < 4))
    rows_json = [{"status": P.arm_status(a, r["status"]), "arm": a, "seed": int(s), "run_dir": r["run_dir"],
                  "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"], "figdata_status": r["status"],
                  "correct_per_gpu_s": r["correct_per_gpu_s"], "gpu_busy_s_measured": r["gpu_busy_s_measured"],
                  "uncached_tokens_per_gpu_s": r["uncached_tokens_per_gpu_s"]} for a, s, r in used]
    P.save_figure(build, "F13_gpu_efficiency", P.SINGLE_IN, 3.6, statuses, rows_json, caption, extra)
    cap = P.OUTDIR / "F13_gpu_efficiency.caption.txt"
    print(cap.read_text())
    print({a: len(per[a]) for a in arms}, missing)
    P.compile_preview("F13_gpu_efficiency", caption.replace("%", r"\%"))


if __name__ == "__main__":
    main()
