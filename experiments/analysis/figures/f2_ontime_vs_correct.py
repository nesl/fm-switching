#!/usr/bin/env python3
"""Paper F2 (single column): on-time rate vs correct-by-deadline, one marker per arm per type. OFFLINE, CPU only.
Source: reports/figdata/F2.csv (standard grid), mean over seeds 4-7 per arm and type. Dashcam correctness is the
per-episode attainment (F2 schema). device-only has on_time_rate NaN for robot and single-shot in F2, so it is
plotted only for dashcam (0, 0); confidence-cascade has no F2 rows. usage: python3 -I f2_ontime_vs_correct.py
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402
import figcommon as fc   # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

STEM = "F2_ontime_vs_correct"
TYPES = [("robot", "o", "Robot"), ("single-shot", "s", "Single-shot"), ("dashcam-alert", "^", "Dashcam")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covex-arm", default=fc.DEFAULT_COVEX)
    a = ap.parse_args()
    d = fc.load("F2.csv")
    arms = [a.covex_arm] + ps.BASELINE_ARMS + [ps.DEVICE]
    d = d[d.arm.isin(arms)]
    pts = []
    for arm in arms:
        for t, mk, _ in TYPES:
            g = d[(d.arm == arm) & (d.type == t)]
            if len(g) == 0 or g.on_time_rate.isna().all():
                continue
            pts.append({"arm": arm, "type": t, "marker": mk, "x": float(g.on_time_rate.mean()),
                        "y": float(g.correct_by_deadline.mean()), "n_seeds": int(len(g))})
    used = d[d.apply(lambda r: any(p["arm"] == r["arm"] and p["type"] == r["type"] for p in pts), axis=1)]
    prow = fc.prov_rows(used)
    statuses = fc.row_statuses(prow)

    def build(fig, mode):
        ax = fig.add_axes([0.15, 0.33, 0.82, 0.62])
        for p in pts:
            cv = p["arm"] == a.covex_arm
            ax.scatter(p["x"], p["y"], marker=p["marker"], s=34 if cv else 16, color=fc.color(p["arm"]),
                       edgecolors=fc.INK if cv else "white", linewidths=0.6 if cv else 0.3, zorder=4 if cv else 3)
        ax.plot([0, 1], [0, 1], color=ps.COLORS["grid"], lw=0.6, zorder=1)
        ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.03, 0.85)
        ax.set_xlabel("On-time rate", fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)
        ax.set_ylabel("Correct by deadline", fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)
        ps.style_axes(ax)
        ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
        ax.spines["left"].set_color(fc.INK); ax.spines["bottom"].set_color(fc.INK)
        th = [Line2D([], [], marker=mk, ls="", color=ps.COLORS["stateful"], markersize=4, label=lab) for _, mk, lab in TYPES]
        ch = [Line2D([], [], marker="o", ls="", color=fc.CLASS_COLOR[c], markersize=4, label=lab)
              for c, lab in [("covex", ps.legend_label(a.covex_arm)), ("stateful", "Stateful"),
                             ("stateless", "Stateless"), ("device", "On-device only")]]
        fig.legend(handles=th, loc="lower left", bbox_to_anchor=(0.02, 0.0), frameon=False, fontsize=ps.FS_TEXT,
                   ncol=1, handletextpad=0.2, labelspacing=0.3)
        fig.legend(handles=ch, loc="lower left", bbox_to_anchor=(0.36, 0.0), frameon=False, fontsize=ps.FS_TEXT,
                   ncol=1, handletextpad=0.2, labelspacing=0.3)

    body = ("On-time rate against correct-by-deadline per arm (mean over seeds 4 to 7, standard condition); one marker "
            "per arm per question type. Dashcam correctness is per-episode attainment. The on-device model has no "
            "on-time rate for robot and single-shot and appears for dashcam only; confidence cascade has no cells.")
    ps.save_figure(build, STEM, ps.SINGLE_IN, 3.0, statuses, prow, body,
                   extra="rung 3 stand-in for COVEX, baselines on dev seeds 4-7")
    j = ps.OUTDIR / f"{STEM}.rows.json"
    o = json.loads(j.read_text()); o["points"] = pts; j.write_text(json.dumps(o, indent=1))
    fc.finish(STEM)
    print(len(pts), "points")


if __name__ == "__main__":
    main()
