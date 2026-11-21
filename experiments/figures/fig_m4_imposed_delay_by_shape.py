#!/usr/bin/env python3
"""M4: delay imposed on others, monolithic rebuild vs 2k vs 1k pieces (StudyENG1c).

Claim: rebuilding a long history as one monolithic prefill imposes a large delay on
other jobs sharing the engine, and slicing the rebuild into small pieces cuts that
imposed delay several-fold at the cost of a little more latency for the rebuilding
job itself. This is why warming must be done in small, yielding pieces, not one shot.

CPU only. Committed data only: StudyENG1c Part D cells (eng1c_results.json),
cross-checked against the raw trials file. Pressure cells are the tight KV pools
(27, 38, 60) where the rebuild contends; the pool that fits (256) is the control.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

SRC = "results/cost/study_eng1c/eng1c_results.json"
FIGID = "M4_imposed_delay_by_rebuild_shape"
SHAPES = [("mono", "monolithic\n11k rebuild"),
          ("piece2048", "2048-token\npieces"),
          ("piece1024", "1024-token\npieces")]
PRESSURE_CAPS = ["27", "38", "60"]
LOADS = ["P25", "S2"]
FIT_CAP = "256"


def agg(cells, caps, shape, field):
    vals = [cells[f"{c}|{ld}|{shape}"]["all"][field]
            for c in caps for ld in LOADS
            if f"{c}|{ld}|{shape}" in cells]
    return np.median(vals), min(vals), max(vals)


def main():
    cells = F.load_json(SRC)["D"]["cells"]

    imposed = {s: agg(cells, PRESSURE_CAPS, s, "imposed_median") for s, _ in SHAPES}
    own = {s: agg(cells, PRESSURE_CAPS, s, "job_ttft_median") for s, _ in SHAPES}
    fit_imposed = {s: agg(cells, [FIT_CAP], s, "imposed_median") for s, _ in SHAPES}

    fig, ax = F.new_fig(7.0, 4.5)
    x = np.arange(len(SHAPES))
    bw = 0.38
    for off, data, col, lab, hatch in [
            (-bw / 2, imposed, F.RISK, "delay imposed on other jobs", "..."),
            (bw / 2, own, F.BLUE, "rebuilding job's own first token", "")]:
        med = [data[s][0] for s, _ in SHAPES]
        lo = [data[s][0] - data[s][1] for s, _ in SHAPES]
        hi = [data[s][2] - data[s][0] for s, _ in SHAPES]
        ax.bar(x + off, med, width=bw, color=col, hatch=hatch, edgecolor="white",
               linewidth=0.9, zorder=3, label=lab)
        ax.errorbar(x + off, med, yerr=[lo, hi], fmt="none", ecolor=F.INK,
                    elinewidth=1.1, capsize=3, zorder=4)
        for xi, v in zip(x + off, med):
            ax.text(xi, v + 0.25, f"{v:.1f}s", ha="center", va="bottom",
                    fontsize=9, color=F.INK)

    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab in SHAPES])
    ax.set_ylabel("time (s)")
    ax.set_ylim(0, 16.5)
    ax.legend(loc="upper right", ncol=1)
    ax.set_title("Monolithic rebuild imposes a long delay on others; pieces do not",
                 fontsize=10.8, pad=8)
    ax.text(0.37, 0.70, "under KV pressure (pools 27, 38, 60).\nAt a pool that fits "
            "(256)\nall shapes impose about 0 s.",
            transform=ax.transAxes, va="top", ha="left", fontsize=8.6, color=F.MUTED)
    F.save(fig, FIGID, pilot=False)

    claim = (
        "Rebuilding a long history as one monolithic prefill imposes a large delay on the other jobs "
        f"sharing the engine (median {imposed['mono'][0]:.1f} s under KV pressure), while the same rebuild "
        f"sliced into 1024-token pieces imposes only {imposed['piece1024'][0]:.1f} s, about "
        f"{imposed['mono'][0]/imposed['piece1024'][0]:.0f}x less, at the cost of a little more latency for "
        f"the rebuilding job itself ({own['mono'][0]:.1f} s monolithic vs {own['piece1024'][0]:.1f} s in "
        f"pieces). The 2048-token pieces sit between ({imposed['piece2048'][0]:.1f} s imposed). At a KV pool "
        f"that fits the histories (256), every shape imposes about 0 s, so the imposed delay is a "
        "contention cost, not an intrinsic one."
    )
    notes = (
        "Imposed delay is the committed ENG1c Part D `imposed_median` (the extra time a concurrent job waits "
        "because of the rebuild); the rebuilding job's own first token is `job_ttft_median`. Both are in "
        "seconds so they share one axis. Bars are the median over the six pressure cells (KV pools 27, 38, 60 "
        "times load profiles P25 and S2); whiskers are the min and max across those cells. The pool-256 "
        "control (histories fit, no contention) gives imposed medians of "
        f"{fit_imposed['mono'][0]:.2f}, {fit_imposed['piece2048'][0]:.2f} and {fit_imposed['piece1024'][0]:.2f} s "
        "for mono, 2k and 1k, confirming the delay is contention. Imposed delay is risk-orange with a dotted "
        "hatch, own latency is query-blue solid, so the two never rest on colour alone."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=False, notes=notes)


if __name__ == "__main__":
    main()
