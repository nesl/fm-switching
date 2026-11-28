#!/usr/bin/env python3
"""Paper F3 (double column): latency CDFs per type with the deadline as a vertical line. NO DATA version.
Reason (checked in reports/figdata/F3.csv.gz, F3.schema.json, 2026-11-27):
  (1) device-only has NO rows in F3.csv.gz (arms present: COVEX stand-ins, development rungs and the baselines only);
  (2) the table has no delivered-answer latency field. It carries standing_latency_s and cloud_latency_s (two answer
      paths per request, each NaN for about a quarter to a third of requests; heavy tails to 700 s) and the composite
      stamps stamp_queue_prefill_s and stamp_decode_s. Which answer an arm actually delivered, and when, is not
      recorded, so a per-request answer-latency distribution (and its position against the deadline) cannot be formed
      without choosing a rule (e.g. min of the two paths) that the data do not support.
Draws the axes, labels and legend empty with a centred NO DATA tag. usage: python3 -I f3_latency_cdf.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402
import figcommon as fc   # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

STEM = "F3_latency_cdf"
NEED = "delivered-answer latency field and device-only rows in F3"


def main():
    types = ["Robot", "Single-shot", "Dashcam"]

    def build(fig, mode):
        ps.no_data(fig, NEED)
        w = (0.97 - 0.07 - 2 * 0.03) / 3
        for i, t in enumerate(types):
            ax = fig.add_axes([0.07 + i * (w + 0.03), 0.3, w, 0.62])
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ps.style_axes(ax)
            ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
            ax.spines["left"].set_color(fc.INK); ax.spines["bottom"].set_color(fc.INK)
            ax.set_xlabel(f"{t}: answer latency (s)", fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)
            ax.set_xticks([]); 
            if i == 0:
                ax.set_ylabel("Fraction of requests", fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)
                ax.set_yticks([0, 0.5, 1.0]); ax.set_yticklabels(["0", "0.5", "1"])
            else:
                ax.set_yticks([0, 0.5, 1.0]); ax.set_yticklabels([])
        hs = [Line2D([], [], color=fc.CLASS_COLOR["covex"], lw=1.5, label=ps.legend_label(ps.COVEX_RUNG3)),
              Line2D([], [], color=fc.CLASS_COLOR["device"], lw=1.5, label="On-device only"),
              Line2D([], [], color=fc.CLASS_COLOR["stateful"], lw=1.5, label="Three strongest baselines"),
              Line2D([], [], color=fc.INK, lw=0.8, ls="--", label="Deadline")]
        fig.legend(handles=hs, loc="lower center", ncol=4, frameon=False, fontsize=ps.FS_TEXT,
                   bbox_to_anchor=(0.5, -0.005), handlelength=1.6, columnspacing=1.5)

    body = ("Latency CDFs per question type with the deadline marked, for COVEX, the on-device model and the three "
            "strongest baselines. Not drawn: the committed latency table has no delivered-answer latency field and no "
            "on-device rows.")
    ps.save_figure(build, STEM, ps.DOUBLE_IN, 2.3, [], [], body, extra="NO DATA YET: " + NEED)
    fc.set_no_data_status(STEM)
    fc.finish(STEM)
    print("F3 NO DATA written")


if __name__ == "__main__":
    main()
