#!/usr/bin/env python3
"""Paper F8 (single column): 1x vs 0.5x memory per arm (D223), n16, 3.0 s robot deadline, rq30, 40:40:20 mix.

Data: reports/figdata/F1.csv (1x cells) and F8.csv (0.5x cells), same seeds per arm; plus the DEV arm
covex-v6-fair-final-cand-tl scored by the committed scorer (figdata.cell_core on the committed cells) at 1x and at
kv0.5r_h0.5, seed 4 only (those cells are not in F1/F8.csv). 0.5x cell variant per arm: kv0.5r_h0.5 if present, else
kv0.5r, else kv0.5 (marked with a dagger); plain cell preferred over _rep/_rerun twins. Panel (a) pooled correct-in-time
fraction (robot + single-shot units), panel (b) dashcam per-episode on-time alert attainment.
OFFLINE, CPU only. Excluded: development-ladder arms base, rules, covex-v6-state-final (not paper arms).
"""
import re
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from matplotlib.lines import Line2D
import paperstyle as ps
import fig5_11_common as fc

STEM = "F08_memory"
EXCLUDE = {"base", "rules", "covex-v6-state-final", "hybrid-F-lhreq", "v5-rules"}
PREF = ["kv0.5r_h0.5", "kv0.5r", "kv0.5"]
DEV = "covex-v6-fair-final-cand-tl"
DEV1X = "covex-v6-fair-final-cand-tl_n16_s4_1200s_h27_3t_L3_epg_rq30_qp"
DEV05 = "covex-v6-fair-final-cand-tl_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30_qp"


def variant(run_dir):
    m = re.search(r"_(kv0\.5(?:r_h0\.5|r|))_L", run_dir)
    return m.group(1) if m else None


def val(r):
    return (float(r["pooled_correct"]) / float(r["pooled_n"]), float(r["dash_attain_per_episode"] or 0.0))  # device-only: blank = 0 (no cloud alerts)


def collect():
    f1 = [r for r in fc.load_csv("F1") if r["seed"] in ("4", "5", "6", "7") and r["pooled_n"]]
    f8 = [r for r in fc.load_csv("F8") if r["cond_memory"] == "0.5x" and r["pooled_n"]]
    one = defaultdict(dict)
    for r in f1:
        one[r["arm"]][r["seed"]] = r
    half = defaultdict(lambda: defaultdict(dict))   # arm -> variant -> seed -> row
    for r in f8:
        v = variant(r["run_dir"])
        base = r["run_dir"].split("/")[-1]
        if re.search(r"_(rep\d|rerun)$", base):
            continue
        half[r["arm"]][v][r["seed"]] = r
    out = {}
    for arm in one:
        if arm in EXCLUDE or arm not in half:
            continue
        v = next((p for p in PREF if p in half[arm]), None)
        seeds = sorted(set(one[arm]) & set(half[arm][v]))
        if not seeds:
            continue
        out[arm] = {"variant": v, "seeds": seeds, "r1": [one[arm][s] for s in seeds], "r05": [half[arm][v][s] for s in seeds]}
    return out


data = collect()
res = []
used = []
for arm, d in data.items():
    a1 = np.mean([val(r) for r in d["r1"]], axis=0)
    a5 = np.mean([val(r) for r in d["r05"]], axis=0)
    res.append({"arm": arm, "v": d["variant"], "seeds": d["seeds"], "p1": a1[0], "p5": a5[0], "d1": a1[1], "d5": a5[1],
                "st": ps.arm_status(arm, "valid")})
    for r in d["r1"] + d["r05"]:
        used.append({"status": ps.arm_status(arm, r["status"]), "figdata_status": r["status"], "arm": arm,
                     "seed": r["seed"], "memory": r["cond_memory"], "variant": variant(r["run_dir"]),
                     "run_dir": r["run_dir"], "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"]})
# DEV arm, seed 4 only, scored on the committed cells
m1, m5 = fc.score_cell(DEV1X), fc.score_cell(DEV05)
res.append({"arm": DEV, "v": "kv0.5r_h0.5", "seeds": ["4"],
            "p1": m1["pooled_correct"] / m1["pooled_n"], "p5": m5["pooled_correct"] / m5["pooled_n"],
            "d1": m1["dash_attain_per_episode"], "d5": m5["dash_attain_per_episode"], "st": "DEV"})
for m, mem in ((m1, "1x"), (m5, "0.5x")):
    used.append({"status": "DEV", "figdata_status": "scored-from-committed-cell", "arm": DEV, "seed": "4", "memory": mem,
                 "variant": "kv0.5r_h0.5" if mem == "0.5x" else None, "run_dir": m["run_dir"], "run_commit": m["run_commit"],
                 "pipeline_sha": m["pipeline_sha"]})
res.sort(key=lambda r: r["p5"])
statuses = [u["status"] for u in used]


def build(fig, mode):
    n = len(res)
    ys = np.arange(n)
    axA = fig.add_axes([0.44, 0.235, 0.27, 0.725])
    axB = fig.add_axes([0.77, 0.235, 0.21, 0.725])
    for ax, k1, k5, lim, lab in ((axA, "p1", "p5", (0.35, 0.75), "Pooled\ncorrect in time"),
                                 (axB, "d1", "d5", (0, 0.85), "Dashcam\nattainment")):
        for y, r in zip(ys, res):
            c = fc.color(r["arm"])
            ax.plot([r[k5], r[k1]], [y, y], color=c, lw=1.0, zorder=2, solid_capstyle="butt")
            ax.scatter([r[k1]], [y], s=14, color=c, zorder=3, linewidths=0)
            ax.scatter([r[k5]], [y], s=14, facecolor="white", edgecolor=c, linewidths=0.9, zorder=3)
        ax.set_ylim(-0.7, n - 0.3)
        ax.set_xlim(*lim)
        ax.set_yticks([])
        ps.style_axes(ax)
        ax.yaxis.grid(False)
        ax.spines["left"].set_visible(False)
        ax.set_xlabel(lab, fontsize=ps.FS_AXLABEL, labelpad=2)
    axA.set_xticks([0.4, 0.5, 0.6, 0.7])
    axB.set_xticks([0, 0.4, 0.8])
    labs = []
    for r in res:
        t = fc.name(r["arm"], mode, bold=False)
        if r["arm"] in (ps.COVEX_RUNG3, DEV):
            t = (r"\textbf{" + t + "}") if mode == "pgf" else t
        if r["v"] != "kv0.5r_h0.5":
            t += r"$^\dagger$" if mode == "pgf" else "†"
        if len(r["seeds"]) == 1:
            t += " (s4)"
        labs.append(t)
    fc.right_labels(axA, ys, labs, x=-0.04)
    h = [Line2D([], [], marker="o", color=ps.COLORS["ink"], lw=0, ms=3.6, label="1x memory"),
         Line2D([], [], marker="o", mfc="white", mec=ps.COLORS["ink"], color=ps.COLORS["ink"], lw=0, ms=3.6, label="0.5x memory")]
    fig.legend(handles=h, loc="lower center", ncol=2, frameon=False, fontsize=ps.FS_TEXT, handletextpad=0.1,
               columnspacing=1.5, bbox_to_anchor=(0.6, -0.005))


ps_note = [u for u in used if u["variant"] and u["variant"] != "kv0.5r_h0.5"]
fall = sorted({r["arm"] for r in res if r["v"] != "kv0.5r_h0.5"})
body = ("Effect of halving memory (1x filled, 0.5x open), left: pooled correct-in-time fraction over robot and "
        "single-shot units, right: dashcam per-episode alert attainment. Means over seeds 4-7 where available "
        "(COVEX dev: seed 4 only). $\\dagger$: 0.5x cell uses the older "
        "tag (kv0.5 or kv0.5r), not kv0.5r\\_h0.5, because no kv0.5r\\_h0.5 cell exists for that arm. Arms without a 0.5x cell are omitted.")
cap = fc.finish(STEM, build, ps.SINGLE_IN, 3.5, statuses, used, body,
                extra="rung 3 stand-in and COVEX dev seed 4, n16, 3.0 s, seeds 4-7 baselines")
import json
j = ps.OUTDIR / f"{STEM}.rows.json"
d = json.loads(j.read_text())
d["plotted"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in res]
d["fallback_variant_arms"] = fall
d["omitted"] = sorted(EXCLUDE) + ["arms with no 0.5x cell in F8.csv: " + ", ".join(sorted(
    a for a in {r['arm'] for r in fc.load_csv('F1')} if a not in {x['arm'] for x in res} and a not in EXCLUDE))]
j.write_text(json.dumps(d, indent=1))
print(cap)
for r in res: print(r["arm"], r["v"], r["seeds"], round(r["p1"], 3), round(r["p5"], 3), round(r["d1"], 3), round(r["d5"], 3))
