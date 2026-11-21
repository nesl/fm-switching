#!/usr/bin/env python3
"""E2 (PILOT): ablation ladder.

Claim: the full joint policy serves the most SS opportunities within deadline; removing
the counterfactual term (v5-rules) drops SS sharply, while removing only C3 keeps it
close to the full policy. The intermediate mechanism rungs (chunk/JIT, guard, deficit)
have no isolated committed cell in the pilot run and are left empty and labelled.

CPU only. Committed EP-G pilot cells (seeds 4, 5), per-opportunity within_L from
outcomes.jsonl.gz. WATERMARKED PILOT. This is NOT a clean nested ladder: several rungs
are not isolated in the committed cells, and the figure shows that honestly rather than
interpolating a monotone curve.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

RUNS = "results/orchestration/live2/frozen_test/runs"
SEEDS = ["s4", "s5"]
FIGID = "E2_ablation_ladder"
# ladder rung label -> committed arm (or None = no isolated committed cell)
RUNGS = [
    ("base\n(no warming)", "warm-all-lru-off"),
    ("+ warming\n(reactive)", "warm-all-lru-reactive"),
    ("+ chunk / JIT", None),
    ("+ guard", None),
    ("+ deficit", None),
    ("- counterfactual\n(v5-rules)", "v5-rules"),
    ("joint,\nno C3", "hybrid-F-lhreq-noc3"),
    ("full joint\n(ours)", "hybrid-F-lhreq"),
]


def ss_on_time(arm):
    rows = []
    for s in SEEDS:
        p = F.REPO / f"{RUNS}/{arm}_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz"
        if not p.exists():
            continue
        with gzip.open(p) as f:
            rows += [json.loads(l) for l in f]
    sel = [r for r in rows if r["kind"] == "recall"]
    n = len(sel)
    h = sum(1 for r in sel if r.get("within_L"))
    return F.wilson(h, n) + (n,)


def main():
    fig, ax = F.new_fig(8.6, 4.6)
    x = np.arange(len(RUNGS))
    for xi, (lab, arm) in zip(x, RUNGS):
        if arm is None:
            ax.text(xi, 0.5, "no isolated\ncommitted cell", ha="center", va="center",
                    fontsize=7.8, color=F.MUTED, rotation=90, style="italic")
            ax.add_patch(__import__("matplotlib").patches.Rectangle(
                (xi - 0.42, 0), 0.84, 1.0, fill=False, edgecolor=F.LIGHT_GREY,
                linewidth=0.8, linestyle=(0, (3, 3)), zorder=1))
            continue
        p, lo, hi, n = ss_on_time(arm)
        A = F.arm(arm)
        ax.bar(xi, p, width=0.72, color=A.color, hatch=A.hatch, edgecolor="white",
               linewidth=0.8, zorder=3)
        ax.errorbar(xi, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=F.INK,
                    elinewidth=1.1, capsize=3, zorder=4)
        ax.text(xi, hi + 0.015, f"{p*100:.0f}%", ha="center", va="bottom", fontsize=9,
                color=F.INK)

    ax.set_xticks(x)
    ax.set_xticklabels([lab for lab, _ in RUNGS], fontsize=8.4)
    ax.set_ylabel("SS served within 2 s")
    ax.set_ylim(0, 1.1)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
    ax.set_title("Ablation: the counterfactual term carries most of the SS gain",
                 fontsize=10.8, pad=8)
    F.save(fig, FIGID, pilot=True)

    full = ss_on_time("hybrid-F-lhreq")[0]
    v5 = ss_on_time("v5-rules")[0]
    noc3 = ss_on_time("hybrid-F-lhreq-noc3")[0]
    base = ss_on_time("warm-all-lru-off")[0]
    claim = (
        f"The full joint policy serves {full*100:.0f}% of SS opportunities within 2 s, the best of the "
        f"committed variants. Removing the counterfactual term (v5-rules) drops SS to {v5*100:.0f}%, while "
        f"removing only C3 keeps it at {noc3*100:.0f}%, close to the full policy; the no-warming base is "
        f"{base*100:.0f}%. The intermediate mechanism rungs (chunk/JIT, guard, deficit) are not isolated as "
        "committed cells in the pilot run and are shown empty and labelled, not interpolated."
    )
    notes = (
        "EP-G PILOT cells, seeds 4 and 5 (seed 5 absent for the two warm-all-lru-off and -reactive cells, which "
        "are single-seed). SS within 2 s is the committed per-opportunity within_L on recall. Error bars are "
        "Wilson 95 percent. This is not a clean nested ladder: the committed cells isolate the base, reactive "
        "warming, the no-C3 and no-counterfactual ablations, and the full policy, but not the chunk/JIT, guard "
        "or deficit rungs, so those are left empty and labelled per the figure brief. The proactive warm-all "
        "baseline is not a ladder rung here (it collapses under load; see M5) and is omitted. Dashcam is not "
        "shown on this axis; on dashcam the full policy is 68 percent and v5-rules collapses to 11 percent, so "
        "the counterfactual term matters on both workloads. Arm colours are the shared registry; PILOT."
    )
    srcs = [f"{RUNS}/{a}_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz"
            for _, a in RUNGS if a for s in SEEDS
            if (F.REPO / f"{RUNS}/{a}_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz").exists()]
    F.write_caption(FIGID, claim, srcs, pilot=True, notes=notes)


if __name__ == "__main__":
    main()
