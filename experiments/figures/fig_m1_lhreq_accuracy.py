#!/usr/bin/env python3
"""M1: LH-REQ accuracy by tier x representation (EVAL 69, Wilson 95 percent CIs).

Claim: on the 69 EVAL long-history-required questions, the full-history
representation (D2) recovers large accuracy over the recent-window representation
on BOTH deployment tiers, unlike the full S-EMBER suite where the gap is small.
This motivates carrying warm full-history state rather than a recent window.

CPU only. Reads committed files only; performs no inference.

Convention (matches the committed orin_rec_part2 analysis): over-context rows are
excluded from the accuracy denominator and reported separately. For the LH-REQ
EVAL subset the only over-context rows are 3 device D2 rows; cloud has none.

Positive control (CLAUDE.md results check 7): the full-suite EVAL recompute must
reproduce the committed accuracy_by_rep_split_wilson95 counts before the figure is
drawn. The script asserts this and aborts if it drifts.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

REPO = F.REPO
LH_DEF = "results/orchestration/live2/lh_req/lh_req_definition.json"
DEV = "results/sember/study_orin_rec/orin_rec_part2.jsonl"
CLOUD = "results/sember/study_acc2/acc2_requests.jsonl"
FIGID = "M1_lhreq_accuracy_by_tier_rep"


def load():
    ids = set(x.lower() for x in F.load_json(LH_DEF)["lh_req_question_ids"])
    dev = F.load_jsonl(DEV)
    cloud = F.load_jsonl(CLOUD)
    return ids, dev, cloud


def cell(data, rep, ids, lh_only, split="EVAL"):
    sub = [r for r in data if r["rep"] == rep and r["split"] == split
           and (r["question_id"].lower() in ids if lh_only else True)]
    answered = [r for r in sub if not r.get("over_context")]
    oc = len(sub) - len(answered)
    n = len(answered)
    k = sum(1 for r in answered if r.get("correct"))
    p, lo, hi = F.wilson(k, n)
    return dict(k=k, n=n, p=p, lo=lo, hi=hi, over_context=oc)


def positive_control(dev, cloud, ids):
    """Full-suite EVAL recompute must match committed part2 analysis counts."""
    comm = F.load_json("results/sember/study_orin_rec/orin_rec_part2_analysis.json")
    want = comm["accuracy_by_rep_split_wilson95"]
    for rep in ("RECENT", "D2"):
        c = cell(dev, rep, ids, lh_only=False, split="EVAL")
        got = (c["k"], c["n"])
        exp = (want[f"{rep}_EVAL"]["k"], want[f"{rep}_EVAL"]["n"])
        assert got == exp, f"control FAIL device {rep}_EVAL: got {got} committed {exp}"
    return True


def main():
    ids, dev, cloud = load()
    assert positive_control(dev, cloud, ids), "positive control failed"

    data = {"device": dev, "cloud": cloud}
    reps = [("recent", "RECENT"), ("rich", "D2")]
    cells = {t: {rk: cell(d, rv, ids, lh_only=True) for rk, rv in reps}
             for t, d in data.items()}

    fig, ax = F.new_fig(6.8, 4.4)
    group_x = {"device": 0.0, "cloud": 1.3}
    bw = 0.46
    rep_off = {"recent": -bw / 2, "rich": bw / 2}
    xticks, xlabels = [], []
    for t in ("device", "cloud"):
        base = F.TIER[t]["color"]
        gx = group_x[t]
        xticks.append(gx)
        xlabels.append(F.TIER[t]["label"])
        for rk, _ in reps:
            c = cells[t][rk]
            x = gx + rep_off[rk]
            col = F.tint(base, F.REP_TINT[rk])
            hatch = "///" if rk == "recent" else ""
            ax.bar(x, c["p"], width=bw, color=col, hatch=hatch,
                   edgecolor="white", linewidth=1.0, zorder=3)
            ax.errorbar(x, c["p"], yerr=[[c["p"] - c["lo"]], [c["hi"] - c["p"]]],
                        fmt="none", ecolor=F.INK, elinewidth=1.4, capsize=4, zorder=4)
            ax.text(x, c["hi"] + 0.02, f"{c['p']*100:.0f}%", ha="center",
                    va="bottom", fontsize=9.5, color=F.INK)
            lab = f"{c['k']}/{c['n']}"
            if c["over_context"]:
                lab += f"\n({c['over_context']} o.c. excl.)"
            ax.text(x, 0.012, lab, ha="center", va="bottom", fontsize=8,
                    color="white", zorder=5)

    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_ylabel("accuracy on 69 EVAL LH-REQ questions")
    ax.set_ylim(0, 0.72)
    ax.set_yticks(np.arange(0, 0.71, 0.1))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 0.71, 0.1)])

    import matplotlib.patches as mpatches
    leg = [mpatches.Patch(facecolor=F.tint(F.GREY, 0.45), hatch="///",
                          edgecolor="white", label="recent window (last 120 s)"),
           mpatches.Patch(facecolor=F.GREY, edgecolor="white",
                          label="full history (D2)")]
    ax.legend(handles=leg, loc="upper left", ncol=1)
    ax.set_title("Full history recovers accuracy on long-history questions, both tiers",
                 fontsize=11.5, color=F.INK, pad=8)
    F.save(fig, FIGID, pilot=False)

    dr, dd = cells["device"]["recent"], cells["device"]["rich"]
    cr, cd = cells["cloud"]["recent"], cells["cloud"]["rich"]
    claim = (
        "On the 69 EVAL long-history-required (LH-REQ) questions, moving from the "
        "recent-window to the full-history (D2) representation raises accuracy from "
        f"{dr['p']*100:.0f}% to {dd['p']*100:.0f}% on the device 4B tier and from "
        f"{cr['p']*100:.0f}% to {cd['p']*100:.0f}% on the cloud 32B tier. The full-history "
        "gain is large on both tiers, in contrast to the full S-EMBER suite where the "
        "D2-minus-recent EVAL gap is about 1 pp on the device and about 5 pp on the cloud. "
        "Error bars are Wilson 95 percent intervals; each question is a single trial."
    )
    notes = (
        "Tiers: device is Qwen3-VL-4B-Instruct on the Jetson Orin (StudyORIN-REC part 2); "
        "cloud is the 32B instruct comparator whose accuracy is measured on the A6000 "
        "accuracy box per the project convention (StudyACC2). LH-REQ was defined on the "
        "accuracy-box selection model, where these questions show D2 45.4% vs recent 21.6% "
        "(gap 23.7 pp, 95% CI [12.4, 35.1]); that selection gap is why the subset exists and "
        "is not re-plotted here. Over-context rows are excluded from the denominator and "
        "reported in-bar: only 3 device D2 rows are over context, cloud has none. "
        "Device and cloud are separate x-groups and labelled, so the blue/purple pair is "
        "never distinguished by hue alone; recent vs full within a group differ by lightness "
        "and hatch, which survive CVD and grayscale."
    )
    F.write_caption(FIGID, claim, [LH_DEF, DEV, CLOUD,
                    "results/sember/study_orin_rec/orin_rec_part2_analysis.json"],
                    pilot=False, notes=notes)


if __name__ == "__main__":
    main()
