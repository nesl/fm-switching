#!/usr/bin/env python3
"""E6 (PILOT): robot deadline sweep.

Claim: the joint policy serves the most robot opportunities within deadline at every
robot deadline from 2.5 s to 5 s, and its lead over the baselines holds across the
sweep (the ranking does not change with the deadline).

CPU only. Committed deadline_sweep.json. IMPORTANT caveat carried from the file: the
decisions were made under a 5 s bound and RE-SCORED at the tighter deadlines, so no arm
knew about a shorter deadline when it chose what to send, defer or decline; an arm that
fails at 3 s here might not fail if it had planned for 3 s. SS has a fixed 2 s deadline
and does not vary in this sweep. WATERMARKED PILOT.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

SRC = "results/orchestration/live2/frozen_test/deadline_sweep.json"
FIGID = "E6_deadline_sweep"
ARMS = ["hybrid-F-lhreq", "hybrid-F6-lhreq", "eco-llm", "mooncake", "b7-edf-feasibility"]


def main():
    d = F.load_json(SRC)
    deadlines = d["deadlines"]
    a16 = d["arms_16dev"]

    fig, ax = F.new_fig(7.4, 4.6)
    for a in ARMS:
        if a not in a16:
            continue
        A = F.arm(a)
        vals = [a16[a][str(dl)]["robot_all_on_time"] for dl in deadlines]
        lo = [a16[a][str(dl)]["robot_ci95"][0] for dl in deadlines]
        hi = [a16[a][str(dl)]["robot_ci95"][1] for dl in deadlines]
        ax.fill_between(deadlines, lo, hi, color=A.color, alpha=0.12, zorder=2)
        ax.plot(deadlines, vals, color=A.color, ls=A.ls, marker=A.marker, ms=6, lw=2.0,
                zorder=4, label=A.label)

    ax.set_xlabel("robot deadline (s)")
    ax.set_ylabel("robot opportunities served within deadline")
    ax.set_xticks(deadlines)
    ax.set_ylim(0, 1.05)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
    ax.legend(loc="upper left", fontsize=8.4)
    ax.text(0.98, 0.02, "decisions made under 5 s, re-scored at tighter deadlines",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8,
            color=F.MUTED, style="italic")
    ax.set_title("Joint policy leads at every robot deadline", fontsize=10.8, pad=8)
    F.save(fig, FIGID, pilot=True)

    h = a16["hybrid-F-lhreq"]
    claim = (
        "The joint policy serves the most robot opportunities within deadline at every robot deadline from "
        f"2.5 s ({h['2.5']['robot_all_on_time']*100:.0f}%) to 5 s ({h['5.0']['robot_all_on_time']*100:.0f}%), "
        "and leads the baselines across the whole sweep. SS has a fixed 2 s deadline and does not vary here. "
        "Because decisions were made under a 5 s bound and re-scored at the tighter deadlines, the tight-deadline "
        "points are a lower bound on what an arm that planned for that deadline could achieve."
    )
    notes = (
        "Committed deadline_sweep.json, 16 devices. Lines are robot_all_on_time with the committed robot_ci95 "
        "as the shaded band. Arms shown are the four-seed-supported headline arms (hybrid-F-lhreq, hybrid-F6, "
        "eco-llm, mooncake, b7); single-seed arms (always-cloud-fcfs, edf, llf) are omitted for support. "
        "CAVEAT from the file: RE-SCORED, decisions made under 5 s, no arm knew of a shorter deadline, so an "
        "arm that fails at 3 s here might not fail if it had planned for 3 s; the ranking is stable across the "
        "sweep (D155). Arm colours and order from the shared registry. PILOT."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
