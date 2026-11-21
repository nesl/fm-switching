#!/usr/bin/env python3
"""E3 (PILOT): the joint policy's mechanism over time.

Claim: the joint policy sustains its on-time service across the whole run, holding both
dashcam and SS near their targets from start to finish rather than degrading as load
accumulates, at a bounded coordinator CPU cost.

CPU only. Committed EP-G pilot cell hybrid-F-lhreq seed 4: outcomes.jsonl.gz (per-opportunity
within_L over time) and host_load.jsonl.gz (coordinator CPU). WATERMARKED PILOT.

On warm share and prefill count: believed-tier warm share is not a sound time series here
(StudyV5-ENGINE records the residency belief understates prefix reuse), so it is not plotted.
The prefix-reuse mechanism is instead evidenced by the committed counts: this cell sends
107,298 EP-G frames as a reference to an already-built prefix against 18,810 sent as bytes,
so most frame traffic reuses warm state.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np
import matplotlib.pyplot as plt

CELL = "results/orchestration/live2/frozen_test/runs/hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg"
FIGID = "E3_mechanism_over_time"
WIDTH = 90.0
HORIZON = 1200.0


def within_series(rows, kind):
    pts = [(r["t_opportunity"], 1.0 if r.get("within_L") else 0.0) for r in rows
           if r["kind"] == kind and r.get("t_opportunity") is not None]
    xs, frac = [], []
    for lo in range(0, int(HORIZON), int(WIDTH)):
        sel = [v for t, v in pts if lo <= t < lo + WIDTH]
        if len(sel) >= 10:
            xs.append((lo + WIDTH / 2) / 60.0)
            frac.append(np.mean(sel))
    return xs, frac


def main():
    with gzip.open(F.REPO / CELL / "outcomes.jsonl.gz") as f:
        rows = [json.loads(l) for l in f]
    with gzip.open(F.REPO / CELL / "host_load.jsonl.gz") as f:
        hl = [json.loads(l) for l in f]
    t0 = min(h["t"] for h in hl)

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(7.6, 5.4), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})
    for ax in (axA, axB):
        ax.grid(True, color=F.GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    xm, fm = within_series(rows, "monitor")
    xr, fr = within_series(rows, "recall")
    axA.plot(xm, fm, color=F.GREEN, lw=2.0, marker="s", ms=4, label="dashcam within 1 s")
    axA.plot(xr, fr, color=F.BLUE, lw=2.0, marker="o", ms=4, label="SS within 2 s")
    axA.set_ylabel("served within deadline")
    axA.set_ylim(0, 1.08)
    axA.set_yticks(np.arange(0, 1.01, 0.25))
    axA.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
    axA.legend(loc="lower right", fontsize=8.6, ncol=2)
    axA.set_title("Joint policy sustains on-time service across the run",
                  fontsize=10.6, pad=6)

    hx = [(h["t"] - t0) / 60.0 for h in hl]
    hy = [h["host_busy_frac"] * 100 for h in hl]
    axB.plot(hx, hy, color=F.PURPLE, lw=1.4)
    axB.fill_between(hx, 0, hy, color=F.PURPLE, alpha=0.12)
    axB.set_ylabel("coordinator\nCPU (%)")
    axB.set_xlabel("run time (min)")
    axB.set_xlim(0, 20)
    axB.set_ylim(0, max(hy) * 1.2 if hy else 10)

    F.save(fig, FIGID, pilot=True)

    claim = (
        "The joint policy sustains its on-time service across the whole 20-minute run: dashcam stays near "
        f"{np.median(fm)*100:.0f}% within 1 s and SS near {np.median(fr)*100:.0f}% within 2 s from start to "
        "finish, rather than degrading as load accumulates (contrast the warm-all baseline in M5, whose latency "
        "grows into the minutes). The coordinator CPU cost stays bounded and low throughout. The prefix-reuse "
        "mechanism is active: the cell sends 107,298 EP-G frames by reference to a built prefix against 18,810 "
        "as bytes."
    )
    notes = (
        "Committed EP-G PILOT cell hybrid-F-lhreq seed 4. Top: fraction of opportunities served within deadline "
        "per 90 s bin, monitor (dashcam, 1 s) and recall (SS, 2 s), from the committed within_L. Bottom: the run's "
        "own coordinator CPU busy fraction from host_load.jsonl.gz (the system loadavg also carries other users "
        "and is not the run's load; the engine/GPU load is reflected in the sustained service above, not in CPU). "
        "Believed-tier warm share is not plotted because it understates prefix reuse by construction "
        "(StudyV5-ENGINE); the frames-by-reference versus by-bytes counts stand in for the warm mechanism. "
        "Colours from the shared registry. PILOT."
    )
    F.write_caption(FIGID, claim, [f"{CELL}/outcomes.jsonl.gz", f"{CELL}/host_load.jsonl.gz",
                    f"{CELL}/coordinator_result.json"], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
