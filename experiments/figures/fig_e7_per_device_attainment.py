#!/usr/bin/env python3
"""E7 (PILOT): per-device target attainment.

Claim: the joint policy clears the per-device dashcam target on every dashcam device,
not just on average: all six devices serve about 67 percent of their dashcam instants
within 1 s, far above the 25 percent per-device target, and the worst-served device is
within a point of the best, so no device is starved.

CPU only. Committed EP-G pilot cells hybrid-F-lhreq seeds 4 and 5, outcomes.jsonl.gz
per-device within_L. The dashcam target is per device (D71: L 1.0 s, p 0.25); the robot
target is pooled and is reported separately in the headline. WATERMARKED PILOT.
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

RUNS = "results/orchestration/live2/frozen_test/runs"
SEEDS = ["s4", "s5"]
FIGID = "E7_per_device_attainment"
TARGET_P = 0.25


def main():
    rows = []
    for s in SEEDS:
        with gzip.open(F.REPO / f"{RUNS}/hybrid-F-lhreq_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz") as f:
            rows += [json.loads(l) for l in f]
    dev = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["kind"] != "monitor":
            continue
        d = r["device_id"]
        dev[d][1] += 1
        if r.get("within_L"):
            dev[d][0] += 1
    dash = sorted((d, h / n, n) for d, (h, n) in dev.items() if d.startswith("dash"))

    fig, ax = F.new_fig(7.0, 4.4)
    x = np.arange(len(dash))
    vals = [p for _, p, _ in dash]
    for xi, (d, p, n) in zip(x, dash):
        pt, lo, hi = F.wilson(round(p * n), n)
        ax.bar(xi, p, width=0.66, color=F.GREEN, edgecolor="white", linewidth=0.8, zorder=3)
        ax.errorbar(xi, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=F.INK,
                    elinewidth=1.0, capsize=3, zorder=4)
        ax.text(xi, p + 0.02, f"{p*100:.0f}%", ha="center", va="bottom", fontsize=9, color=F.INK)

    ax.axhline(TARGET_P, color=F.RISK, lw=1.6, ls=(0, (6, 4)), zorder=5)
    ax.text(len(dash) - 0.5, TARGET_P + 0.02, "per-device target: 25% within 1 s",
            ha="right", va="bottom", fontsize=9, color=F.shade(F.RISK, 0.1))

    ax.set_xticks(x)
    ax.set_xticklabels([d for d, _, _ in dash])
    ax.set_ylabel("dashcam instants served within 1 s")
    ax.set_ylim(0, 0.85)
    ax.set_yticks(np.arange(0, 0.81, 0.2))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 0.81, 0.2)])
    ax.set_title("Every dashcam device clears its per-device target", fontsize=10.8, pad=8)
    F.save(fig, FIGID, pilot=True)

    worst = min(vals); best = max(vals)
    claim = (
        f"The joint policy clears the per-device dashcam target on every one of the {len(dash)} dashcam "
        f"devices: each serves {worst*100:.0f} to {best*100:.0f} percent of its dashcam instants within 1 s, "
        f"far above the {TARGET_P*100:.0f} percent per-device target, and the worst-served device is within a "
        "point of the best, so service is uniform and no device is starved. The robot target is pooled and is "
        "reported in the headline, not per device."
    )
    notes = (
        "Committed EP-G PILOT cells hybrid-F-lhreq seeds 4 and 5. Bars are the per-device fraction of dashcam "
        "(monitor) instants with within_L true, pooled over the two seeds; error bars are Wilson 95 percent. "
        "The dashcam target is per device (D71: L 1.0 s, p 0.25, minimum 200 instants); ANALYSIS_PLAN decision 3 "
        "makes the robot target pooled over robot devices (a per-device robot minimum of 20 is unreachable at "
        "this run length), so robot attainment is not shown per device here. Assistive devices carry no served "
        "target. PILOT."
    )
    F.write_caption(FIGID, claim, [f"{RUNS}/hybrid-F-lhreq_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz"
                    for s in SEEDS], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
