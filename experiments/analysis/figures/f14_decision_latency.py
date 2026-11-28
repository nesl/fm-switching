#!/usr/bin/env python3
"""Paper Figure 14: decision latency p50 / p99 versus fleet size. OFFLINE, committed data (reports/figdata/F14.csv).

CLOCK PLOTTED: decision_wall_ms (wall clock of one policy decision, decision_time.jsonl wall_ms), not cpu_ms. The
cpu clock differs by under 3 percent in every committed row. Live decisions in the live2 runner (basis = live), not dry.
Cells: 1x memory, robot deadline 3.0 s, run_dir <arm>_n<N>_s<seed>_1200s_h27_3t_L3_epg_rq30 (standard cells, N 8 to 16) and,
for COVEX only, <arm>_n<N>_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30 for N = 20, 24, 32 (the only committed larger fleets; mix
flag c3-11-2, hollow markers). Per (arm, N): median over the seeds present of the per-cell p50 and p99.
usage: python3 -I f14_decision_latency.py
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

STD = re.compile(r"^.+_n(\d+)_s([4-7])_1200s_h27_3t_L3_epg_rq30(_rerun|_ms_rerun)?$")
BIG = re.compile(r"^.+_n(\d+)_s([4-7])_1200s_h27_3t_c3-11-2_L3_epg_rq30$")
ARMS = [(P.COVEX_RUNG3, "o"), ("mooncake", "s"), ("llf", "^"), ("simplestream", "D"), ("eco-llm", "v")]


def main():
    rows = list(csv.DictReader(open(P.REPO / "reports/figdata/F14.csv")))
    cell = {}
    for r in rows:
        t = r["run_dir"].split("/")[-1]
        if r["cond_memory"] != "1x" or r["cond_deadline_s"] != "3.0" or r["cond_extras"] or not r["decision_wall_ms_p50"]:
            continue
        a = r["arm"]
        m = STD.match(t)
        big = False
        if not m and a == P.COVEX_RUNG3:
            m = BIG.match(t)
            big = bool(m) and int(m.group(1)) > 16
        if not m or a not in dict(ARMS):
            continue
        n = int(m.group(1))
        if n == 16 and not STD.match(t):
            continue
        key = (a, n, r["seed"])
        if key not in cell or m.re is STD and m.group(3):
            cell[key] = (r, big)
    g = defaultdict(list)
    rows_json = []
    for (a, n, s), (r, big) in sorted(cell.items()):
        g[(a, n)].append((float(r["decision_wall_ms_p50"]), float(r["decision_wall_ms_p99"]), float(r["decision_cpu_ms_p50"])))
        rows_json.append({"status": P.arm_status(a, r["status"]), "arm": a, "seed": int(s), "n_devices": n,
                          "run_dir": r["run_dir"], "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"],
                          "figdata_status": r["status"], "n_decisions": r["n_decisions"],
                          "wall_p50_ms": r["decision_wall_ms_p50"], "wall_p99_ms": r["decision_wall_ms_p99"],
                          "cpu_p50_ms": r["decision_cpu_ms_p50"], "cpu_p99_ms": r["decision_cpu_ms_p99"],
                          "mix_flag_c3-11-2": big})
    statuses = [x["status"] for x in rows_json]
    series = {}
    for a, mk in ARMS:
        ns = sorted(n for (aa, n) in g if aa == a)
        series[a] = (ns, [np.median([v[0] for v in g[(a, n)]]) for n in ns],
                     [np.median([v[1] for v in g[(a, n)]]) for n in ns], [len(g[(a, n)]) for n in ns])

    def build(fig, mode):
        ax = fig.add_axes([0.14, 0.17, 0.83, 0.68])
        P.style_axes(ax, xgrid=False)
        ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
        for a, mk in ARMS:
            ns, p50, p99, cnt = series[a]
            col = P.COLORS[P.arm_class(a)]
            if a != P.COVEX_RUNG3 and P.arm_class(a) == "stateless":
                col = "#9A9A9A"
            lab = P.legend_label(a)
            ax.plot(ns, p50, color=col, lw=1.0, marker=mk, ms=3.2, label=lab)
            ax.plot(ns, p99, color=col, lw=0.8, ls=(0, (2.5, 1.5)), marker=mk, ms=3.2, mfc="white", mew=0.7)
            if a == P.COVEX_RUNG3:
                for n, v50, v99 in zip(ns, p50, p99):
                    if n > 16:
                        ax.plot([n], [v50], marker=mk, ms=3.2, mfc="white", color=col, mew=0.7)
        ax.set_xlabel("devices in the fleet", fontsize=P.FS_AXLABEL)
        ax.set_ylabel("decision latency, wall (ms)", fontsize=P.FS_AXLABEL)
        ax.set_xticks([8, 12, 16, 20, 24, 32])
        ax.set_yticks([0, 1, 2, 3, 4, 5])
        ax.set_ylim(0, 7.4)
        from matplotlib.lines import Line2D
        h, l = ax.get_legend_handles_labels()
        h = h + [Line2D([0], [0], color="#555555", lw=1.0), Line2D([0], [0], color="#555555", lw=0.8, ls=(0, (2.5, 1.5)))]
        l = l + ["p50", "p99"]
        ax.legend(h, l, loc="upper left", fontsize=P.FS_TEXT - 0.5, frameon=False, ncol=2, handlelength=1.8,
                  columnspacing=0.9, borderaxespad=0.1, labelspacing=0.25)

    caption = ("Decision latency of the policy per decision versus fleet size, live runs, 1x memory, 3 s robot deadline. "
               "Clock plotted: wall clock (decision\\_wall\\_ms), not CPU time. Solid lines are p50, dashed lines p99; each point "
               "is the median over the available seeds of the per-run percentile. COVEX points above 16 devices (hollow) are "
               "single seed 4 runs with the 3:11:2 mix flag, the only committed larger fleets; baselines have no cells "
               "above 16 devices. Each run logs about 12,000 decisions.")
    extra = ("COVEX is the rung 3 covex-v6-fair-final stand-in (OLD); DEV candidates are not in F14.csv; "
             "dry latency at 16/24/32/48 devices is not committed")
    P.save_figure(build, "F14_decision_latency", P.SINGLE_IN, 2.6, statuses, rows_json, caption, extra)
    print({a: (series[a][0], [round(x, 2) for x in series[a][1]], series[a][3]) for a, _ in ARMS})
    P.compile_preview("F14_decision_latency", caption.replace("%", r"\%"))


if __name__ == "__main__":
    main()
