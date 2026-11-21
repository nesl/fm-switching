#!/usr/bin/env python3
"""E4 (PILOT): capacity, the engine saturation knee.

Claim: the serving engine has a sharp capacity knee near 4,500 to 5,200 offered
uncached tokens per second; below it first-token latency is about 0.45 s, and an arm
whose offered load crosses it sees first-token latency jump into the tens of seconds.
The clean policies sit below the knee at 16 devices; the capacity knee is what bounds
how large a fleet one engine can serve.

CPU only. Committed saturation_knee.json (clean EP-G cells only; the cal1f, rf and
other labelled cells are excluded). The live EP-G pilot is 16 devices only, so this is
the capacity axis the pilot measures; the per-fleet-size sweep arrives with the
repeat-trace cells. WATERMARKED PILOT.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

SRC = "results/orchestration/live2/frozen_test/saturation_knee.json"
FIGID = "E4_capacity_knee"


def arm_of(cell):
    return cell.split("_n16_")[0]


def main():
    d = F.load_json(SRC)
    knee = d["knee_bounded_between_tok_per_s"]
    clean = [c for c in d["cells"] if c["cell"].endswith("_L3_epg")]

    fig, ax = F.new_fig(7.4, 4.6)
    ax.grid(True, which="both", color=F.GRID, linewidth=0.6, zorder=0)
    ax.axvspan(knee[0], knee[1], color=F.RISK, alpha=0.12, zorder=1)
    ax.text((knee[0] + knee[1]) / 2, 8, "capacity\nknee", ha="center", va="center",
            fontsize=9, color=F.shade(F.RISK, 0.1))

    seen = set()
    for c in sorted(clean, key=lambda c: c["offered_uncached_tok_per_s"]):
        A = F.arm(arm_of(c["cell"]))
        lab = A.label if A.label not in seen else None
        seen.add(A.label)
        ax.scatter([c["offered_uncached_tok_per_s"]], [c["first_token_p50_s"]],
                   s=90, marker=A.marker, facecolors=A.color, edgecolors="white",
                   linewidths=1.0, zorder=5, label=lab)

    ax.axhline(1.0, color=F.INK, lw=1.1, ls=(0, (6, 4)), zorder=3)
    ax.text(3650, 1.15, "1 s", fontsize=8.5, color=F.INK)
    ax.set_yscale("log")
    ax.set_xlabel("offered load (uncached tokens / s)")
    ax.set_ylabel("first-token latency p50 (s)")
    ax.set_xlim(3500, 5800)
    ax.legend(loc="center left", fontsize=8, ncol=1)
    ax.set_title("Engine capacity knee: latency jumps when offered load crosses it",
                 fontsize=10.6, pad=8)
    F.save(fig, FIGID, pilot=True)

    below = [c for c in clean if c["offered_uncached_tok_per_s"] < knee[0]]
    above = [c for c in clean if c["offered_uncached_tok_per_s"] >= knee[1]]
    claim = (
        f"The serving engine saturates at a sharp capacity knee between {knee[0]:.0f} and {knee[1]:.0f} "
        "offered uncached tokens per second. Clean cells below the knee hold first-token latency near "
        f"{np.median([c['first_token_p50_s'] for c in below]):.2f} s, while a cell above it jumps to "
        f"{max(c['first_token_p50_s'] for c in above):.0f} s first-token p50. At 16 devices the clean "
        "policies sit below the knee; the knee is the per-engine capacity that bounds how large a fleet one "
        "engine can serve on time."
    )
    notes = (
        "Committed saturation_knee.json. Clean EP-G cells only (_L3_epg); the cal1f, rf and other labelled "
        "cells are excluded. first_token_p50_s vs offered_uncached_tok_per_s, log y. The knee band is the "
        "committed knee_bounded_between_tok_per_s. The live EP-G pilot is 16 devices only, so capacity is "
        "expressed as offered load, not fleet size; the per-fleet-size sweep is deferred to the repeat-trace "
        "cells (the committed fleet/eligibility ladder is a trace-level eligibility count, not a live-capacity "
        "curve, so it is not used here). Marks are coloured by arm from the shared registry. PILOT."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
