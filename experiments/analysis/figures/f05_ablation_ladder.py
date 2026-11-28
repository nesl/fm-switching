#!/usr/bin/env python3
"""Paper F5 (double column): ablation ladder per type, plus the two failed alternatives.

Three panels = three request types (robot correct-by-deadline, single-shot correct-in-time, dashcam per-episode
alert attainment), all scored by the committed scorer (figdata.cell_core -> canon, pipeline 298d8315) on committed
cells, SEED 4 ONLY (the only seed with dev-ladder cells). Rows, top to bottom, cumulative:
 Block 1, n16, 1x, standard composition, no outage (F1.csv seed 4 for rungs 0-3, committed cells for the rest):
   rung 0 base, rung 1 rules, rung 2 state, rung 3 fair, rung 3 fair + rr, rung 3 (covex-v6-fair-final),
   +0b +P(er) = covex-v6-fair-final-0b-er (0b: predictive+book belief; P part: engine_resync),
   +B = -la-er (la_arrival), +P (wire tokens + host engine model) = -la-er-pwire, +qp = -cand (uplink question
   priority tag), +latch fix = -cand-tl.   No cell exists for +S2 at n16.
 Block 2, n20, 3:11:2, no outage: rung 3, +latch fix (cand-tl), counterfactual admission (-cf and the
   admission-only -cf-a, both stacked on cand-tl-sync); these are failed alternatives (marked X).
 Block 3, n20, 3:11:2, 14-robot outage (k14, d188, evidence t0 407.5 s): rung 3, +latch fix, +S2 (cand-tl-sync),
   eager catch-up (-sync-eager, failed), counterfactual admission (-sync-cf, failed).
P, 0b and B cannot be isolated one by one: no P-only or 0b-only arm exists at n20, and 0b alone only at n16 as 0b-er.
Positive control (check 7): the F1.csv rung 3 seed 4 row must equal figdata.cell_core on the committed cell.
OFFLINE, CPU only.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import paperstyle as ps
import fig5_11_common as fc

STEM = "F05_ablation_ladder"
R3, TL, SYNC = "covex-v6-fair-final", "covex-v6-fair-final-cand-tl", "covex-v6-fair-final-cand-tl-sync"
T4075 = "c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link"
N20 = "_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30"
N16 = "_n16_s4_1200s_h27_3t_L3_epg_rq30"
# (block, label, arm for status/colour, source). source = ("f1", arm_in_F1) or ("cell", run_dir)
ROWS = [
    (1, "rung 0 base", "base", ("f1", "base")),
    (1, "rung 1 rules", "rules", ("f1", "rules")),
    (1, "rung 2 state", "state-uo-c5attr", ("f1", "state-uo-c5attr")),
    (1, "rung 3 fair", "fair-c5attr", ("f1", "fair-c5attr")),
    (1, "rung 3 fair + rr", "fair-c5attr-rr", ("f1", "fair-c5attr-rr")),
    (1, "rung 3 (COVEX, old)", R3, ("f1", R3)),
    (1, "+0b, +P (resync)", "covex-v6-fair-final-0b-er", ("cell", "covex-v6-fair-final-0b-er" + N16)),
    (1, "+B", "covex-v6-fair-final-la-er", ("cell", "covex-v6-fair-final-la-er" + N16)),
    (1, "+P (wire, host model)", "covex-v6-fair-final-la-er-pwire", ("cell", "covex-v6-fair-final-la-er-pwire" + N16)),
    (1, "+question priority", "covex-v6-fair-final-cand", ("cell", "covex-v6-fair-final-cand" + N16 + "_qp")),
    (1, "+latch fix (dev)", TL, ("cell", TL + N16 + "_qp")),
    (2, "rung 3 (COVEX, old)", R3, ("cell", R3 + N20)),
    (2, "+latch fix (dev)", TL, ("cell", TL + N20 + "_qp")),
    (2, "counterfactual admission", "cf", ("cell", SYNC + "-cf" + N20 + "_qp")),
    (2, "counterfactual admission, admission only", "cf", ("cell", SYNC + "-cf-a" + N20 + "_qp")),
    (3, "rung 3 (COVEX, old)", R3, ("cell", R3 + "_n20_s4_1200s_h27_3t_" + T4075)),
    (3, "+latch fix (dev)", TL, ("cell", TL + "_n20_s4_1200s_h27_3t_" + T4075 + "_qp")),
    (3, "+S2 (dev)", SYNC, ("cell", SYNC + "_n20_s4_1200s_h27_3t_" + T4075 + "_qp")),
    (3, "eager catch-up", "eager", ("cell", SYNC + "-eager_n20_s4_1200s_h27_3t_" + T4075 + "_qp")),
    (3, "counterfactual admission", "cf", ("cell", SYNC + "-cf_n20_s4_1200s_h27_3t_" + T4075 + "_qp")),
]
FAILED = {"cf", "eager"}
BLOCKS = {1: "n16, 1x, standard mix", 2: "n20, 3:11:2 mix, no outage", 3: "n20, 3:11:2 mix, 14-robot outage"}
F1 = {(r["arm"], r["seed"]): r for r in fc.load_csv("F1")}


def metrics_from_f1(r):
    return {"robot": float(r["robot_correct"]) / float(r["robot_n"]), "ss": float(r["ss_correct"]) / float(r["ss_n"]),
            "dash": float(r["dash_attain_per_episode"] or 0.0), "n": (int(r["robot_n"]), int(r["ss_n"]))}


res, used, miss = [], [], []
for blk, lab, arm, (kind, src) in ROWS:
    if kind == "f1":
        r = F1[(src, "4")]
        m = metrics_from_f1(r)
        prov = {"run_dir": r["run_dir"], "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"],
                "figdata_status": r["status"], "source": "F1.csv"}
        stat = ps.arm_status(arm, r["status"])
    else:
        try:
            c = fc.score_cell(src)
        except Exception as e:   # missing cell: marked, not plotted
            miss.append({"label": lab, "block": blk, "run_dir": src, "error": repr(e)[:120]})
            continue
        m = {"robot": c["robot_correct"] / c["robot_n"], "ss": c["ss_correct"] / c["ss_n"],
             "dash": c["dash_attain_per_episode"], "n": (c["robot_n"], c["ss_n"])}
        prov = {"run_dir": c["run_dir"], "run_commit": c["run_commit"], "pipeline_sha": c["pipeline_sha"],
                "figdata_status": "scored-from-committed-cell", "source": "figdata.cell_core"}
        stat = ps.arm_status(arm if arm in (TL, SYNC, R3) else "other", "valid")
        if arm in ("cf", "eager"):
            stat = "OLD"
    res.append({"block": blk, "label": lab, "arm": arm, "m": m, "status": stat})
    used.append({"status": stat, "arm": arm, "label": lab, "block": blk, "seed": 4, **prov,
                 "robot": round(m["robot"], 4), "single_shot": round(m["ss"], 4), "dash": round(m["dash"], 4),
                 "n_robot_ss": m["n"]})
# positive control: F1 rung 3 seed 4 against the committed scorer on its own cell
pc = fc.score_cell(F1[(R3, "4")]["run_dir"].split("/")[-1])
r3f1 = metrics_from_f1(F1[(R3, "4")])
assert abs(pc["robot_correct"] / pc["robot_n"] - r3f1["robot"]) < 1e-9 and abs(pc["dash_attain_per_episode"] - r3f1["dash"]) < 1e-6, "positive control failed"
statuses = [u["status"] for u in used]
assert not miss, miss


def colour(r):
    if r["arm"] in FAILED or r["arm"] == "cf":
        return ps.COLORS["ink"]
    return fc.color(r["arm"]) if r["arm"] in (R3, TL, SYNC) or r["arm"] in ps.BASELINES else "#6F8FB5"


def build(fig, mode):
    # y layout: headers and rows, top to bottom
    ypos, headers, y = [], [], 0.0
    last = None
    for r in res:
        if r["block"] != last:
            y += 0.45 if last is not None else 0.0
            headers.append((y, BLOCKS[r["block"]]))
            y += 1.0
            last = r["block"]
        ypos.append(y)
        y += 1.0
    ymax = y
    W = 0.165
    xs0 = [0.385, 0.385 + W + 0.045, 0.385 + 2 * (W + 0.045)]
    keys = ("robot", "ss", "dash")
    xl = ((0.3, 0.8), (0.4, 0.7), (0, 1.0))
    xt = ([0.4, 0.6], [0.4, 0.5, 0.6], [0, 0.5, 1])
    names = ("Robot correct\nby deadline", "Single-shot\ncorrect in time", "Dashcam alert\nattainment")
    axs = []
    for i, (k, x0) in enumerate(zip(keys, xs0)):
        ax = fig.add_axes([x0, 0.13, W, 0.84])
        axs.append(ax)
        ax.set_ylim(ymax - 0.4, -0.9)
        ax.set_xlim(*xl[i])
        ax.set_xticks(xt[i])
        ps.style_axes(ax)
        ax.yaxis.grid(False)
        ax.spines["left"].set_visible(False)
        ax.set_yticks([])
        ax.set_xlabel(names[i], fontsize=ps.FS_AXLABEL, labelpad=2)
        for hy, _ in headers:
            ax.axhline(hy - 0.5, color=ps.COLORS["grid"], lw=0.5, zorder=0)
        # connect the ladder within block 1 only (cumulative rungs 3 onward)
        seq = [(yy, r) for yy, r in zip(ypos, res) if r["block"] == 1 and r["label"] not in ("rung 0 base", "rung 1 rules", "rung 2 state", "rung 3 fair", "rung 3 fair + rr")]
        ax.plot([r["m"][k] for _, r in seq], [yy for yy, _ in seq], color=ps.COLORS["covex"], lw=0.6, zorder=2)
        for yy, r in zip(ypos, res):
            c = colour(r)
            failed = r["arm"] in FAILED or r["arm"] == "cf"
            ax.scatter([r["m"][k]], [yy], s=(22 if failed else 12), marker=("X" if failed else "o"), color=c,
                       linewidths=0, zorder=3)
            ax.text(r["m"][k] + (xl[i][1] - xl[i][0]) * 0.035, yy, f"{r['m'][k]:.2f}", va="center", ha="left",
                    fontsize=ps.FS_TEXT, color=ps.COLORS["tag"])
    tr = axs[0].get_yaxis_transform()
    for hy, t in headers:
        axs[0].text(-0.03, hy, t, transform=tr, ha="right", va="center", fontsize=ps.FS_TEXT, color=ps.COLORS["tag"],
                    style="italic")
    for yy, r in zip(ypos, res):
        t = r["label"]
        if r["arm"] in (R3, TL, SYNC):
            t = (r"\textbf{" + t + "}") if mode == "pgf" else t
        axs[0].text(-0.03, yy, t, transform=tr, ha="right", va="center", fontsize=ps.FS_TEXT, color=ps.COLORS["ink"])


body = ("Per-type effect of each addition (cumulative, seed 4 only). Top block: standard 16-device mix without outage, "
        "rungs 0 to 3 then the candidate additions (0b with the engine-resync part of P, B, the rest of P, question "
        "priority, touch latch fix). Middle and bottom blocks: 20 devices, 3:11:2 mix, without and with a 14-robot "
        "outage; +S2 exists only with the outage. X marks failed alternatives: counterfactual admission and eager "
        "catch-up. P, 0b and B cannot be separated one by one in the committed cells.")
cap = fc.finish(STEM, build, ps.DOUBLE_IN, 4.6, statuses, used, body,
                extra="rung 3 stand-in and COVEX dev, seed 4 only")
j = ps.OUTDIR / f"{STEM}.rows.json"
d = json.loads(j.read_text())
d["missing_cells"] = ["+S2 at n16 and at n20 without outage (no cand-tl-sync cell)", "eager at n16 and n20 without outage",
                      "-cf-a with outage", "+0b, +B, +P(rest), +qp at n20 with outage",
                      "any seed other than 4 for the dev ladder (seeds 5-7 have only cand-tl n20 s5)",
                      "P-only and 0b-only isolated arms"]
d["positive_control"] = "F1.csv rung 3 seed 4 == figdata.cell_core on its committed cell (robot, dash): passed"
j.write_text(json.dumps(d, indent=1))
print(cap)
for r in res: print(r["block"], f"{r['label']:44s}", {k: round(v, 3) for k, v in r["m"].items() if k != "n"}, r["m"]["n"], r["status"])
