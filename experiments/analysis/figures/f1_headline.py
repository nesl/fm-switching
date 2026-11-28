#!/usr/bin/env python3
"""Paper F1 headline (double column): correct-by-deadline per type plus dashcam on-time attainment, COVEX vs every
baseline and device-only, standard grid (1x memory, 16 devices, robot deadline 3.0 s). OFFLINE, CPU only.
Source: reports/figdata/F1.csv (per-seed rows; seed=all rows skipped). Bars: pooled over seeds (sum correct / sum n)
for robot, single-shot, pooled(robot+single-shot); mean over seeds for dashcam per-episode on-time attainment.
Dots: individual seeds. DEV/OLD status via paperstyle.arm_status. usage: python3 -I f1_headline.py [--covex-arm ARM]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402
import figcommon as fc   # noqa: E402

STEM = "F1_headline"
PANELS = [("Robot", "robot_correct", "robot_n", "Correct by deadline"),
          ("Single-shot", "ss_correct", "ss_n", "Correct by deadline"),
          ("Pooled", "pooled_correct", "pooled_n", "Correct by deadline"),
          ("Dashcam", "dash_attain_per_episode", None, "On-time attainment")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covex-arm", default=fc.DEFAULT_COVEX)
    a = ap.parse_args()
    d = fc.load("F1.csv")
    d = d[d.seed.astype(str) != "all"]
    arms = [a.covex_arm] + ps.BASELINE_ARMS + [ps.DEVICE]
    d = d[d.arm.isin(arms)]
    stats = {}
    for arm in arms:
        g = d[d.arm == arm]
        s = {}
        for name, num, den, _ in PANELS:
            gg = g[g[num].notna()]
            if len(gg) == 0:
                s[name] = None
                continue
            if den:
                per = (gg[num] / gg[den]).tolist()
                bar = gg[num].sum() / gg[den].sum()
            else:
                per = gg[num].tolist(); bar = float(np.mean(per))
            s[name] = {"bar": float(bar), "seeds": per, "seed_ids": gg.seed.astype(str).tolist()}
        stats[arm] = s
    order = [a.covex_arm] + sorted(ps.BASELINE_ARMS, key=lambda x: -(stats[x]["Pooled"]["bar"] if stats[x]["Pooled"] else 0)) + [ps.DEVICE]
    prow = fc.prov_rows(d)
    statuses = fc.row_statuses(prow)
    n = len(order)
    ys = np.arange(n)[::-1]

    def build(fig, mode):
        left, right, bot, top = 0.215, 0.99, 0.15, 0.93
        gap = 0.012
        w = (right - left - gap * 3) / 4
        for i, (name, num, den, xl) in enumerate(PANELS):
            ax = fig.add_axes([left + i * (w + gap), bot, w, top - bot])
            for y, arm in zip(ys, order):
                s = stats[arm][name]
                if s is None:
                    ax.text(0.02, y, "n/a", fontsize=ps.FS_TEXT - 1, color=ps.COLORS["tag"], va="center")
                    continue
                ax.barh(y, s["bar"], height=0.62, color=fc.color(arm), edgecolor="none")
                ax.scatter(s["seeds"], [y] * len(s["seeds"]), s=4, color=fc.INK, edgecolors="white", linewidths=0.3, zorder=3)
                ax.text(1.04, y, f"{s['bar']:.2f}", va="center", ha="left",
                        fontsize=ps.FS_TEXT - 1, color=fc.INK,
                        fontweight="bold" if arm == a.covex_arm else "normal")
            ax.set_xlim(0, 1.25)
            ax.set_ylim(-0.6, n - 0.4)
            ax.set_xticks([0, 0.5, 1.0])
            ax.set_xticklabels(["0", "0.5", "1"])
            ax.set_yticks([])
            ps.style_axes(ax)
            ax.tick_params(axis="x", length=2)
            ax.set_xlabel(name, fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)
            if i == 0:
                fc.right_labels(ax, ys, [fc.label(x, mode, bold=(x == a.covex_arm)) for x in order],
                                [x == a.covex_arm for x in order], x=-0.03)
            ax.spines["left"].set_color(fc.INK)
        from matplotlib.patches import Patch
        hs = [Patch(facecolor=fc.CLASS_COLOR["covex"], label=ps.legend_label(a.covex_arm)),
              Patch(facecolor=fc.CLASS_COLOR["stateful"], label="Stateful baseline"),
              Patch(facecolor=fc.CLASS_COLOR["stateless"], label="Stateless baseline"),
              Patch(facecolor=fc.CLASS_COLOR["device"], label="On-device only")]
        fig.legend(handles=hs, loc="lower center", ncol=4, frameon=False, fontsize=ps.FS_TEXT, bbox_to_anchor=(0.6, -0.005),
                   handlelength=1.0, columnspacing=1.5)

    body = ("Correct-by-deadline fraction on robot, single-shot and pooled (robot plus single-shot) questions, and "
            "per-episode on-time attainment on dashcam streams, for COVEX, the baselines and the on-device model "
            "(standard condition: 1$\\times$ memory, 16 devices, 3\\,s robot deadline). Bars pool seeds 4 to 7 "
            "(dashcam: mean over seeds); dots are single seeds. Confidence cascade has no dashcam cells; "
            "ECO-LLM lacks seed 5.")
    ps.save_figure(build, STEM, ps.DOUBLE_IN, 3.5, statuses, prow, body,
                   extra="rung 3 stand-in for COVEX, baselines on dev seeds 4-7")
    import json
    j = ps.OUTDIR / f"{STEM}.rows.json"
    o = json.loads(j.read_text()); o["values"] = stats; o["order"] = order; j.write_text(json.dumps(o, indent=1))
    fc.finish(STEM)
    for arm in order:
        print(arm, {k: (round(v["bar"], 3) if v else None) for k, v in stats[arm].items()})


if __name__ == "__main__":
    main()
