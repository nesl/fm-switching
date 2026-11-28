#!/usr/bin/env python3
"""Paper F11 (double column): workload composition (dashcam-heavy, robot-heavy 3:11:2, re-ask rq10 / rq30 / rq60,
mixed robot workload).

NO DATA YET. reports/figdata/F11.csv has zero rows; READINESS.md lists only rq30 and the standard 40:40:20 mix
(the 3:11:2 device ratio is the committed standard workload, not a composition sweep). Axes, labels and legend are
drawn empty. OFFLINE, no cell is read.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D
import paperstyle as ps
import fig5_11_common as fc

STEM = "F11_composition"
CONDS = ["dashcam-heavy", "robot-heavy\n3:11:2", "re-ask\nrq10", "re-ask\nrq30", "re-ask\nrq60", "mixed robot\nworkload"]
NEED = ("composition cells: dashcam-heavy mix, robot-heavy 3:11:2 mix, re-ask rq10 and rq60 (rq30 exists only\n"
        "in the standard 40:40:20 grid), mixed robot workload; F11.csv has 0 rows")


def build(fig, mode):
    ax = fig.add_axes([0.075, 0.25, 0.905, 0.64])
    ax.set_xlim(-0.6, len(CONDS) - 0.4)
    ax.set_ylim(0, 1)
    ax.set_xticks(range(len(CONDS)))
    ax.set_xticklabels(CONDS, fontsize=ps.FS_TEXT)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0", "0.5", "1"])
    ps.style_axes(ax, xgrid=False)
    ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
    ax.set_ylabel("Correct by deadline", fontsize=ps.FS_AXLABEL)
    ax.set_xlabel("Workload composition", fontsize=ps.FS_AXLABEL, labelpad=2)
    h = [Line2D([], [], marker="o", color=ps.COLORS["covex"], lw=0, ms=4, label="COVEX (old: rung 3)"),
         Line2D([], [], marker="o", color=ps.COLORS["stateful"], lw=0, ms=4, label="Stateful baselines"),
         Line2D([], [], marker="o", color=ps.COLORS["stateless"], lw=0, ms=4, label="Stateless baselines")]
    ax.legend(handles=h, loc="upper right", ncol=3, frameon=False, fontsize=ps.FS_TEXT, handletextpad=0.2,
              columnspacing=1.0)
    fig.text(0.53, 0.55, "NO DATA YET: " + NEED, ha="center", va="center", fontsize=ps.FS_TEXT, color=ps.COLORS["tag"],
             bbox=dict(facecolor="white", edgecolor="none", pad=2))


rows = [{"status": "NO DATA", "arm": None, "seed": None, "run_dir": None, "run_commit": None, "pipeline_sha": None,
         "note": "F11.csv has 0 rows; needed cells: " + NEED.replace("\n", " ")}]
body = ("Correct-by-deadline under workload composition: dashcam-heavy, robot-heavy 3:11:2, re-ask rq10, rq30 and rq60, "
        "and a mixed robot workload. Empty: none of the composition cells exist yet.")
cap = fc.finish(STEM, build, ps.DOUBLE_IN, 2.2, ["OLD"], rows, body, extra="NO DATA, rung 3 stand-in for COVEX")
print(cap)
