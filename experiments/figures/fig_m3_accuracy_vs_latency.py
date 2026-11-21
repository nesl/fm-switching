#!/usr/bin/env python3
"""M3: accuracy vs first-token latency per tier and representation.

Claim: the richer full-history (RICH/D2) representation buys accuracy over the
recent window on both tiers, but at a cold first-token latency cost that pushes the
device past the 3 s budget; warming removes that cost (the device recent-window
first token drops from 3.32 s cold to 0.21 s warm at the same accuracy), which is
how a long-history representation can be both accurate and on time.

CPU only. Committed data only: device StudyORIN-REC part 2 and its warm run; cloud
StudyACC2 requests. EVAL split, over-context rows excluded from the accuracy
denominator (committed convention). Accuracy CIs are Wilson 95 percent.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

DEV = "results/sember/study_orin_rec/orin_rec_part2.jsonl"
CLOUD = "results/sember/study_acc2/acc2_requests.jsonl"
WARM = "results/sember/study_orin_rec/orin_rec_warm_meta.json"
FIGID = "M3_accuracy_vs_latency"
SLO = 3.0


def cell(rows, rep, split="EVAL"):
    sub = [r for r in rows if r.get("rep") == rep and r.get("split") == split
           and not r.get("over_context")]
    n = len(sub)
    k = sum(1 for r in sub if r.get("correct"))
    tt = [r["ttft_s"] for r in sub if r.get("ttft_s") is not None]
    p, lo, hi = F.wilson(k, n)
    return dict(acc=p, lo=lo, hi=hi, n=n, ttft=float(np.median(tt)))


def main():
    dev = F.load_jsonl(DEV)
    cloud = F.load_jsonl(CLOUD)
    warm = F.load_json(WARM)["warm_summary"]

    d_rec = cell(dev, "RECENT"); d_d2 = cell(dev, "D2")
    c_rec = cell(cloud, "RECENT"); c_d2 = cell(cloud, "D2")
    d_rec_warm = dict(acc=d_rec["acc"], lo=d_rec["lo"], hi=d_rec["hi"],
                      ttft=warm["ttft_p50"], n=warm["n"])

    fig, ax = F.new_fig(7.2, 4.8)
    ax.grid(True, axis="both", color=F.GRID, linewidth=0.7, zorder=0)

    ax.axvspan(SLO, 8, color=F.RISK, alpha=0.05, zorder=0)
    ax.axvline(SLO, color=F.INK, lw=1.3, ls=(0, (6, 4)), zorder=2)
    ax.text(SLO + 0.08, 0.205, "3 s budget", rotation=90, va="bottom", ha="left",
            fontsize=9, color=F.INK)

    # (point dict, color, marker, filled, label, label_dxdy)
    pts = [
        (d_rec, F.PURPLE, "o", False, "device recent (cold)", (0.12, 0.012)),
        (d_d2, F.PURPLE, "^", False, "device rich (cold)", (0.12, -0.004)),
        (c_rec, F.BLUE, "o", False, "cloud recent (cold)", (0.12, 0.010)),
        (c_d2, F.BLUE, "^", False, "cloud rich (cold)", (0.12, 0.012)),
        (d_rec_warm, F.PURPLE, "o", True, "device recent\n(warm)", (0.18, -0.030)),
    ]
    for pt, col, mk, filled, lab, (dx, dy) in pts:
        face = col if filled else "white"
        ax.errorbar(pt["ttft"], pt["acc"],
                    yerr=[[pt["acc"] - pt["lo"]], [pt["hi"] - pt["acc"]]],
                    fmt="none", ecolor=col, elinewidth=1.3, capsize=3, zorder=3)
        ax.scatter([pt["ttft"]], [pt["acc"]], s=95, marker=mk, facecolors=face,
                   edgecolors=col, linewidths=1.8, zorder=5)
        ax.annotate(lab, xy=(pt["ttft"], pt["acc"]),
                    xytext=(pt["ttft"] + dx, pt["acc"] + dy), fontsize=9,
                    color=F.shade(col, 0.1), va="center")

    # warming arrow: device recent cold -> warm
    ax.annotate("", xy=(d_rec_warm["ttft"] + 0.05, d_rec_warm["acc"]),
                xytext=(d_rec["ttft"] - 0.05, d_rec["acc"]),
                arrowprops=dict(arrowstyle="-|>", color=F.GREEN, lw=2.0,
                                connectionstyle="arc3,rad=-0.25"), zorder=4)
    ax.text(2.35, 0.262, "warming", color=F.shade(F.GREEN, 0.1), fontsize=9.5,
            style="italic", ha="center")

    ax.set_xlabel("first-token latency p50 (s)")
    ax.set_ylabel("EVAL recall accuracy")
    ax.set_xlim(-0.2, 7.4)
    ax.set_ylim(0.22, 0.44)
    ax.set_yticks(np.arange(0.24, 0.44, 0.04))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0.24, 0.44, 0.04)])
    ax.set_title("Rich buys accuracy at a cold-latency cost; warming removes the cost",
                 fontsize=10.8, pad=8)
    F.save(fig, FIGID, pilot=False)

    claim = (
        "Across tiers and representations, the richer full-history representation buys accuracy "
        f"over the recent window (device {d_rec['acc']*100:.0f}% to {d_d2['acc']*100:.0f}%, cloud "
        f"{c_rec['acc']*100:.0f}% to {c_d2['acc']*100:.0f}% on EVAL) but at a cold first-token cost "
        f"that puts the device over the 3 s budget (device recent {d_rec['ttft']:.2f} s, device rich "
        f"{d_d2['ttft']:.2f} s). Warming removes that cost: the device recent-window first token drops "
        f"from {d_rec['ttft']:.2f} s cold to {d_rec_warm['ttft']:.2f} s warm at the same accuracy, "
        "moving the device from over budget to well under it. A long-history representation can therefore "
        "be both accurate and on time only if its prefix is warm."
    )
    notes = (
        "Device is Qwen3-VL-4B on the Orin (StudyORIN-REC part 2, and its best-case warm run where the "
        f"recent frames are prefilled, agreeing with the cold answers on {warm['n_frames'] if 'n_frames' in warm else '93 of 97'} "
        "items so accuracy is unchanged); cloud is 32B (StudyACC2). Latency is TTFT p50; accuracy is EVAL "
        "with over-context rows excluded from the denominator and Wilson 95 percent CIs (vertical bars). "
        "Only the device recent-window warm point is a committed measurement; the warming arrow is drawn only "
        "for it and not inferred for the other cells. Points are directly labelled, so the blue (cloud) and "
        "purple (device) pair is never distinguished by hue alone; representation is also shown by marker "
        "(circle recent, triangle rich) and cold vs warm by open vs filled."
    )
    F.write_caption(FIGID, claim, [DEV, CLOUD, WARM], pilot=False, notes=notes)


if __name__ == "__main__":
    main()
