#!/usr/bin/env python3
"""Paper F10 (single column): robot deadline 2.5 / 3 / 4 / 5 s (plus the 1.5 s cells that exist).

Data: reports/figdata/F10.csv (deadline-sweep cells, robot_frac = robot correct by the deadline over robot
opportunities) and the 3.0 s standard cells from F1.csv (robot_correct / robot_n), seeds 4-7 means where present.
Existing: 1.5 s (covex-v6-fair-final, simplestream), 2.5 s (base, rules, device-only, llf, mooncake), 3.0 s (all, F1).
MISSING: 4 s and 5 s for every arm (no cell in F10.csv); drawn as shaded empty columns. The committed
covex-v6-fair-final L2 / L5 preD249 cells are not in F10.csv and are not used. OFFLINE, CPU only.
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

STEM = "F10_robot_deadline"
KEEP = ["covex-v6-fair-final", "simplestream", "llf", "mooncake", "device-only", "rules", "base"]
MARK = {"covex-v6-fair-final": "o", "simplestream": "^", "llf": "s", "mooncake": "P", "device-only": "X", "rules": "h",
        "base": "d"}
XS = [1.5, 2.5, 3.0, 4.0, 5.0]
data = defaultdict(lambda: defaultdict(list))
used = []
# Seed pairing: seed-to-seed spread of robot correctness is large (device-only 0.06 to 0.37 across seeds 4-7 at
# 3.0 s), so the 3.0 s point of an arm uses ONLY the seeds that arm has in F10.csv (a 4-seed mean against a seed
# 4-5 mean at 2.5 s produced an apparent rise when the deadline tightened, an artefact of the seed set).
f10_seeds = defaultdict(set)
for r in fc.load_csv("F10"):
    f10_seeds[r["arm"]].add(r["seed"])
for r in fc.load_csv("F10"):
    if r["arm"] in KEEP and r["robot_frac"]:
        data[r["arm"]][float(r["cond_deadline_s"])].append(float(r["robot_frac"]))
        used.append({"status": ps.arm_status(r["arm"], r["status"]), "figdata_status": r["status"], "arm": r["arm"],
                     "deadline_s": r["cond_deadline_s"], "seed": r["seed"], "run_dir": r["run_dir"],
                     "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"], "robot_frac": r["robot_frac"]})
for r in fc.load_csv("F1"):
    if r["arm"] in KEEP and r["seed"] in f10_seeds[r["arm"]] and r["robot_n"]:
        data[r["arm"]][3.0].append(float(r["robot_correct"]) / float(r["robot_n"]))
        used.append({"status": ps.arm_status(r["arm"], r["status"]), "figdata_status": r["status"], "arm": r["arm"],
                     "deadline_s": "3.0", "seed": r["seed"], "run_dir": r["run_dir"], "run_commit": r["run_commit"],
                     "pipeline_sha": r["pipeline_sha"], "robot_frac": float(r["robot_correct"]) / float(r["robot_n"])})
pts = {a: {x: float(np.mean(v)) for x, v in d.items()} for a, d in data.items()}
spread = {a: {x: [round(min(v), 3), round(max(v), 3), len(v)] for x, v in d.items()} for a, d in data.items()}
statuses = [u["status"] for u in used]


def build(fig, mode):
    ax = fig.add_axes([0.15, 0.33, 0.82, 0.62])
    ax.axvspan(3.55, 5.45, color="#F2F2F2", lw=0, zorder=0)
    ax.text(4.5, 0.62, "no cells\nat 4 s and 5 s", ha="center", va="top", fontsize=ps.FS_TEXT, color=ps.COLORS["tag"])
    pos = {1.5: 0, 2.5: 1, 3.0: 2, 4.0: 3, 5.0: 4}
    for arm in KEEP:
        if arm not in pts:
            continue
        xs = sorted(pts[arm])
        x = [xs_ for xs_ in xs]
        ax.plot(x, [pts[arm][k] for k in xs], color=fc.color(arm), lw=0.9, marker=MARK[arm], ms=3.4,
                mfc=fc.color(arm), mec=fc.color(arm), zorder=3)
    ax.set_xlim(1.1, 5.45)
    ax.set_ylim(0.1, 0.65)
    ax.set_xticks(XS)
    ax.set_xticklabels(["1.5", "2.5", "3", "4", "5"])
    ps.style_axes(ax)
    ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
    ax.set_xlabel("Robot deadline (s)", fontsize=ps.FS_AXLABEL, labelpad=2)
    ax.set_ylabel("Robot correct by deadline", fontsize=ps.FS_AXLABEL)
    h = [Line2D([], [], color=fc.color(a), marker=MARK[a], ms=3.4, lw=0.9, label=fc.name(a, mode)) for a in KEEP if a in pts]
    fig.legend(handles=h, loc="lower center", ncol=3, frameon=False, fontsize=ps.FS_TEXT, handlelength=1.3,
               handletextpad=0.3, columnspacing=0.8, bbox_to_anchor=(0.55, -0.01))


body = ("Robot correct-by-deadline fraction against the robot deadline. Points exist at 1.5 s (COVEX rung 3 stand-in, "
        "SimpleStream), 2.5 s (LLF, Mooncake, on-device, development rungs) and 3 s (all arms, standard cells); "
        "4 s and 5 s have no cells yet. Each arm's 3 s point uses only the seeds that arm has at the other deadlines (seeds 4-5 at 2.5 s, one seed at 1.5 s), because robot correctness varies strongly across seeds.")
cap = fc.finish(STEM, build, ps.SINGLE_IN, 2.9, statuses, used, body,
                extra="rung 3 stand-in for COVEX, 4 s and 5 s missing")
j = ps.OUTDIR / f"{STEM}.rows.json"
d = json.loads(j.read_text())
d["points"] = {a: {str(x): round(v, 4) for x, v in p.items()} for a, p in pts.items()}
d["spread_min_max_n_cells"] = {a: {str(x): s for x, s in v.items()} for a, v in spread.items()}
d["missing_cells"] = "deadline 4.0 s and 5.0 s: no rows in F10.csv for any arm; 2.5 s missing for covex-v6-fair-final, simplestream; 1.5 s missing for llf, mooncake, device-only"
j.write_text(json.dumps(d, indent=1))
print(cap)
for a, p in pts.items(): print(a, {x: round(v, 3) for x, v in sorted(p.items())}, spread[a])
