#!/usr/bin/env python3
"""Paper F4 (single column): per-device distribution of improvement in on-time attainment over device-only, worst
device marked. OFFLINE, CPU only. Source: reports/figdata/F4.csv (standard grid).
LIMITATION (stated in caption): F4.csv has NO device-only rows and no on-time reference for robot or single-shot
(F2 on_time_rate for device-only is NaN there). Only dashcam has a committed device-only reference: on-time
attainment 0.0 in every seed (F1 dash_attain_per_episode, F2 on_time_rate), so dashcam improvement = attainment.
Robot and single-shot panels are therefore not drawn. One point per (device, seed); box = quartiles, bar = median.
Shown: COVEX plus the four baselines with the highest mean dashcam attainment. usage: python3 -I f4_per_device.py
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402
import figcommon as fc   # noqa: E402

STEM = "F4_per_device"
DEVICE_REF = 0.0   # device-only dashcam on-time attainment, F1/F2 (all four seeds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covex-arm", default=fc.DEFAULT_COVEX)
    ap.add_argument("--nbase", type=int, default=4)
    a = ap.parse_args()
    d = fc.load("F4.csv")
    d = d[(d.type == "dashcam-alert")]
    mean_att = d[d.arm.isin(ps.BASELINE_ARMS)].groupby("arm").attainment.mean().sort_values(ascending=False)
    order = [a.covex_arm] + list(mean_att.index[:a.nbase])
    d = d[d.arm.isin(order)].copy()
    d["improvement"] = d.attainment - DEVICE_REF
    prow = fc.prov_rows(d)
    statuses = fc.row_statuses(prow)
    n = len(order)
    ys = np.arange(n)[::-1]
    rng = np.random.default_rng(0)
    summ = {}

    def build(fig, mode):
        ax = fig.add_axes([0.375, 0.2, 0.595, 0.74])
        for y, arm in zip(ys, order):
            v = d[d.arm == arm].improvement.values
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            ax.add_patch(__import__("matplotlib").patches.Rectangle((q1, y - 0.27), q3 - q1, 0.54, fc="none",
                         ec=fc.color(arm) if arm != order[-1] or True else fc.INK, lw=0.8, zorder=2))
            ax.plot([med, med], [y - 0.27, y + 0.27], color=fc.INK, lw=1.0, zorder=3)
            jit = np.random.default_rng(1).uniform(-0.17, 0.17, len(v))
            ax.scatter(v, y + jit, s=5, color=fc.color(arm), edgecolors=fc.INK, linewidths=0.2, zorder=3, alpha=0.9)
            k = int(np.argmin(v))
            ax.scatter([v[k]], [y + jit[k]], s=26, facecolors="none", edgecolors=fc.INK, linewidths=0.8, zorder=4)
            ax.text(v[k] - 0.025, y, f"{v[k]:.2f}", ha="right", va="center", fontsize=ps.FS_TEXT - 1.5, color=fc.INK)
            summ[arm] = {"n_points": int(len(v)), "min": float(v.min()), "q1": float(q1), "median": float(med),
                         "q3": float(q3), "max": float(v.max())}
        ax.set_yticks([])
        fc.right_labels(ax, ys, [fc.label(x, mode, bold=(x == a.covex_arm)) for x in order],
                        [x == a.covex_arm for x in order], x=-0.03)
        ax.set_xlim(-0.12, 1.02); ax.set_ylim(-0.6, n - 0.4)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0]); ax.set_xticklabels(["0", ".25", ".5", ".75", "1"])
        ps.style_axes(ax)
        ax.tick_params(axis="x", length=2)
        ax.spines["left"].set_color(fc.INK); ax.spines["bottom"].set_color(fc.INK)
        ax.set_xlabel("Dashcam on-time attainment gain\nover the on-device model (per device)",
                      fontsize=ps.FS_AXLABEL, color=fc.INK, labelpad=2)

    body = ("Per-device gain in dashcam on-time attainment over the on-device model (which meets none: attainment 0 "
            "in every seed), for COVEX and the four strongest baselines. One dot per device and seed (seeds 4 to 7, "
            "standard condition); boxes show quartiles, the bar the median, and the ringed dot with its value the worst "
            "device. Robot and single-shot are not shown: the committed per-device table has no on-device reference there.")
    ps.save_figure(build, STEM, ps.SINGLE_IN, 2.2, statuses, prow, body,
                   extra="rung 3 stand-in for COVEX, baselines on dev seeds 4-7; dashcam only")
    j = ps.OUTDIR / f"{STEM}.rows.json"
    o = json.loads(j.read_text()); o["summary"] = summ; o["device_only_reference"] = DEVICE_REF
    o["device_only_reference_source"] = "F1.csv dash_attain_per_episode = 0.0 for seeds 4-7; F2.csv on_time_rate = 0.0"
    j.write_text(json.dumps(o, indent=1))
    fc.finish(STEM)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
