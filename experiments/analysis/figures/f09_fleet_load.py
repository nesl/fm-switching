#!/usr/bin/env python3
"""Paper F9 (single column): load vs fleet size (n devices) with the capacity line.

Data: reports/figdata/F9.csv (fleet-sweep cells, per arm per seed) plus the standard n16 cells from F1.csv, and the
DEV arm covex-v6-fair-final-cand-tl scored by the committed scorer (figdata.cell_core) on its committed cells
(n16 std composition and n20 3:11:2, seed 4). Panel (a) pooled correct-in-time fraction, panel (b) dashcam
per-episode on-time alert attainment; mean over the seeds that exist at each n.
Composition audit: F9.csv labels every cell 40:40:20, but cells whose run name carries the token c3-11-2 are the
3:11:2 device composition (pooled_n 520 at n20 against 634 without the token). They are drawn as a separate dashed
series, never mixed into the standard series. Capacity column (capacity_largest_fleet_all_D178) is blank in F9.csv, so
no capacity line is drawn and the figure says so. OFFLINE, CPU only. Omitted: base, rules (development rungs).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from matplotlib.lines import Line2D
import paperstyle as ps
import fig5_11_common as fc

STEM = "F09_fleet_load"
SKIP = {"base", "rules", "covex-v6-state-final", "hybrid-F-lhreq", "v5-rules"}
DEVARM = "covex-v6-fair-final-cand-tl"
DEV_STD = "covex-v6-fair-final-cand-tl_n16_s4_1200s_h27_3t_L3_epg_rq30_qp"
DEV_312 = "covex-v6-fair-final-cand-tl_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp"
MARK = {"covex-v6-fair-final": "o", DEVARM: "D", "llf": "s", "simplestream": "^", "eco-llm": "v", "mooncake": "P",
        "device-only": "X"}


def val(r):
    return (float(r["pooled_correct"]) / float(r["pooled_n"]), float(r["dash_attain_per_episode"] or 0.0))


rows_by = defaultdict(lambda: defaultdict(list))   # (arm, comp) -> n -> [(seed, row)]
used = []
for r in fc.load_csv("F9"):
    if r["arm"] in SKIP or not r["pooled_n"]:
        continue
    comp = "3:11:2" if "c3-11-2" in r["run_dir"] else "std"
    rows_by[(r["arm"], comp)][int(r["cond_n_devices"])].append(r)
for r in fc.load_csv("F1"):
    if r["arm"] in SKIP or r["seed"] not in ("4", "5", "6", "7") or not r["pooled_n"]:
        continue
    rows_by[(r["arm"], "std")][16].append(r)
series = {}
for (arm, comp), byn in rows_by.items():
    pts = {n: np.mean([val(r) for r in rs], axis=0) for n, rs in byn.items()}
    series[(arm, comp)] = {"pts": pts, "seeds": {n: sorted({r["seed"] for r in rs}) for n, rs in byn.items()}}
    for n, rs in byn.items():
        for r in rs:
            used.append({"status": ps.arm_status(arm, r["status"]), "figdata_status": r["status"], "arm": arm,
                         "composition": comp, "n_devices": n, "seed": r["seed"], "run_dir": r["run_dir"],
                         "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"]})
for rd, comp, n in ((DEV_STD, "std", 16), (DEV_312, "3:11:2", 20)):
    m = fc.score_cell(rd)
    series[(DEVARM, comp)] = {"pts": {n: np.array([m["pooled_correct"] / m["pooled_n"], m["dash_attain_per_episode"]])},
                              "seeds": {n: ["4"]}}
    used.append({"status": "DEV", "figdata_status": "scored-from-committed-cell", "arm": DEVARM, "composition": comp,
                 "n_devices": n, "seed": "4", "run_dir": m["run_dir"], "run_commit": m["run_commit"],
                 "pipeline_sha": m["pipeline_sha"]})
statuses = [u["status"] for u in used]
cap_vals = [r["capacity_largest_fleet_all_D178"] for r in fc.load_csv("F9") if r["capacity_largest_fleet_all_D178"]]
assert not cap_vals, "capacity values now exist: add the capacity line"


def build(fig, mode):
    axA = fig.add_axes([0.185, 0.605, 0.795, 0.355])
    axB = fig.add_axes([0.185, 0.235, 0.795, 0.335], sharex=axA)
    order = ["device-only", "simplestream", "eco-llm", "llf", "mooncake", "covex-v6-fair-final", DEVARM]
    for (arm, comp), s in sorted(series.items(), key=lambda kv: (order.index(kv[0][0]) if kv[0][0] in order else 9, kv[0][1])):
        if arm not in MARK:
            continue
        ns = sorted(s["pts"])
        for ax, k in ((axA, 0), (axB, 1)):
            ys = [s["pts"][n][k] for n in ns]
            ls = "--" if comp == "3:11:2" else "-"
            c = fc.color(arm)
            ax.plot(ns, ys, color=c, lw=0.9, ls=ls, marker=MARK[arm], ms=3.2, mfc=("white" if comp == "3:11:2" else c),
                    mec=c, mew=0.7, zorder=3 if arm in (ps.COVEX_RUNG3, DEVARM, "covex-v6-fair-final") else 2)
    for ax in (axA, axB):
        ps.style_axes(ax)
        ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
        ax.set_xlim(6.5, 34)
    axA.set_ylim(0.15, 0.7)
    axB.set_ylim(-0.03, 1.0)
    axA.set_xticks([8, 12, 16, 20, 24, 32])
    axA.tick_params(labelbottom=False)
    axB.set_xlabel("Fleet size (devices)", fontsize=ps.FS_AXLABEL, labelpad=2)
    axA.set_ylabel("Pooled correct\nin time", fontsize=ps.FS_AXLABEL)
    axB.set_ylabel("Dashcam\nattainment", fontsize=ps.FS_AXLABEL)
    axA.text(0.99, 0.04, "capacity line: not measured (fleet sweep pending)", transform=axA.transAxes, ha="right",
             va="bottom", fontsize=ps.FS_TEXT, color=ps.COLORS["tag"])
    h = []
    for arm in order:
        if (arm, "std") in series or (arm, "3:11:2") in series:
            h.append(Line2D([], [], color=fc.color(arm), marker=MARK[arm], ms=3.2, lw=0.9, label=fc.name(arm, mode)))
    h.append(Line2D([], [], color=ps.COLORS["ink"], lw=0.9, label="std. composition"))
    h.append(Line2D([], [], color=ps.COLORS["ink"], lw=0.9, ls="--", label="3:11:2 composition"))
    fig.legend(handles=h, loc="lower center", ncol=3, frameon=False, fontsize=ps.FS_TEXT, handlelength=1.3,
               handletextpad=0.3, columnspacing=0.7, bbox_to_anchor=(0.5, -0.01))


body = ("Pooled correct-in-time fraction (top) and dashcam per-episode alert attainment (bottom) against fleet "
        "size. Solid: standard composition, dashed with open markers: 3:11:2 composition (separate series, not "
        "comparable in level). Means over the seeds present at each size (mostly seed 4 only). The capacity line "
        "(largest fleet meeting all three targets) is absent: no fleet sweep has produced capacity values yet.")
cap = fc.finish(STEM, build, ps.SINGLE_IN, 3.9, statuses, used, body,
                extra="rung 3 stand-in and COVEX dev seed 4, no capacity values")
j = ps.OUTDIR / f"{STEM}.rows.json"
d = json.loads(j.read_text())
d["series"] = [{"arm": a, "composition": c, "points": {str(n): [round(float(x), 4) for x in v] for n, v in s["pts"].items()},
                "seeds": {str(n): sd for n, sd in s["seeds"].items()}} for (a, c), s in series.items()]
d["capacity_line"] = "MISSING: capacity_largest_fleet_all_D178 is blank for every F9.csv row"
d["omitted_arms"] = sorted(SKIP)
j.write_text(json.dumps(d, indent=1))
print(cap)
for (a, c), s in sorted(series.items()): print(a, c, {n: [round(float(x), 3) for x in v] for n, v in sorted(s["pts"].items())})
