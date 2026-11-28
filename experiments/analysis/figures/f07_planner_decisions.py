#!/usr/bin/env python3
"""Paper F7 (single column): rung 3 state-planner decisions by kind at 1x vs 0.5x memory.

NO DATA YET. reports/figdata/F7.csv has zero rows (schema: counterfactual decisions by kind, GAP), and the committed
rung 3 decision logs (decision.jsonl.gz) record only the kinds release_monitor, release_infeasible, release_recall,
release_piece, state_action (desired_tier always gpu) and touch; KEEP, RELOAD, HOLD_BACK and SLICE are not logged
as decision kinds. The axes, labels and legend are drawn with an empty plot. OFFLINE, no cell is read.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from matplotlib.patches import Patch
import paperstyle as ps
import fig5_11_common as fc

STEM = "F07_planner_decisions"
KINDS = ["KEEP", "TOUCH", "RELOAD", "HOLD_BACK", "SLICE"]
TICKS = ["KEEP", "TOUCH", "RELOAD", "HOLD\nBACK", "SLICE"]
NEED = ("rung 3 state-planner decision counts\nby kind (KEEP, TOUCH, RELOAD, HOLD_BACK, SLICE)\n"
        "at 1x and 0.5x memory; F7.csv has 0 rows")


def build(fig, mode):
    ax = fig.add_axes([0.17, 0.27, 0.80, 0.62])
    ax.set_xlim(-0.6, len(KINDS) - 0.4)
    ax.set_ylim(0, 1)
    ax.set_xticks(range(len(KINDS)))
    lab = TICKS
    ax.set_xticklabels(lab, fontsize=ps.FS_TEXT)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0", "", ""])
    ps.style_axes(ax, xgrid=False)
    ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
    ax.set_ylabel("Decisions per run", fontsize=ps.FS_AXLABEL)
    ax.set_xlabel("Decision kind", fontsize=ps.FS_AXLABEL, labelpad=2)
    h = [Patch(facecolor=ps.COLORS["covex"], label="1x memory"),
         Patch(facecolor="white", edgecolor=ps.COLORS["covex"], hatch="////", label="0.5x memory")]
    ax.legend(handles=h, loc="upper right", frameon=False, fontsize=ps.FS_TEXT, handlelength=1.2)
    fig.text(0.57, 0.58, "NO DATA YET: " + NEED, ha="center", va="center", fontsize=ps.FS_TEXT, color=ps.COLORS["tag"],
             bbox=dict(facecolor="white", edgecolor="none", pad=2))


rows = [{"status": "NO DATA", "arm": ps.COVEX_RUNG3, "seed": None, "run_dir": None, "run_commit": None,
         "pipeline_sha": None, "note": "F7.csv has 0 rows; decision kinds KEEP/RELOAD/HOLD_BACK/SLICE are not in decision.jsonl"}]
body = ("Rung 3 state-planner decisions by kind at 1x and 0.5x memory. Empty: no per-kind decision log exists yet "
        "(F7.csv has no rows).")
cap = fc.finish(STEM, build, ps.SINGLE_IN, 2.2, ["OLD"], rows, body, extra="NO DATA, rung 3 stand-in for COVEX")
print(cap)
