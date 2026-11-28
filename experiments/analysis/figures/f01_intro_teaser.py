#!/usr/bin/env python3
"""Paper Figure 1 (intro teaser), D334: additional correct answers by deadline over on-device answers alone.

OFFLINE, reads only committed files: reports/figdata/F1.csv (per-seed pooled_correct) and
reports/figdata/F1_units.csv.gz (per-question correct_by_deadline, the paired units). Styling, colours, labels,
status rules and the PGF/PNG/caption/rows writers come from paperstyle.py (shared module, D334).
Writes figures/paper/F01_intro_teaser.{pgf,pdf,png,caption.txt,rows.json}.

Quantity per system: sum over the system's seeds of pooled_correct (robot + single-shot, committed scorer rule)
minus the device-only arm's pooled_correct over the SAME seeds. Dashcam is not counted.
Ratio and CI logic are unchanged: 95% clustered bootstrap by question_id (2,000 resamples, seed 0), paired with
device-only on the same (seed, question) units.

usage: python3 -I f01_intro_teaser.py [--covex-arm covex-v6-fair-final] [--seeds 4,5,6,7]
STATUS: COVEX = rung 3 stand-in (OLD); baselines and device-only on seeds 4-7 are DEV; tag is OLD DATA.
confidence-cascade is included (post-D205 rerun cells, seeds 4-7). eco-llm uses the seeds that have a committed row.
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402
import figcommon as fc   # noqa: E402

REPO = ps.REPO
F1 = REPO / "reports/figdata/F1.csv"
UNITS = REPO / "reports/figdata/F1_units.csv.gz"
NBOOT, BSEED = 2000, 0
DEVICE = ps.DEVICE
STEM = "F01_intro_teaser"

# Class basis per baseline (ruling 2026-11-27): committed arm -> (display, class, class-defining file:line, basis).
CLASS_REFS = {
    "streamscout": ("StreamScout", "stateless",
        "experiments/orchestration/baselines/streamscout_adapted.py:46,98-110",
        "per-query representation choice; sends the history-carrying representation, keeps no cross-question state"),
    "simplestream": ("SimpleStream", "stateless",
        "experiments/orchestration/baselines/simplestream_adapted.py:38,86",
        "no history reuse; recent window per question"),
    "llf": ("LLF", "stateless", "experiments/orchestration/live2/arms.py:293", "least-laxity-first scheduling"),
    "eco-llm": ("ECO-LLM", "stateless", "experiments/orchestration/baselines/ecollm_adapted.py:46",
        "per-query edge-cloud routing"),
    "mooncake": ("Mooncake", "stateful", "experiments/orchestration/baselines/mooncake_adapted.py:32",
        "KVCache-centric placement and reuse"),
    "b7-edf-feasibility": ("EDF + feasibility", "stateless",
        "experiments/orchestration/baselines/constructed.py:163", "EDF with feasibility test per query"),
    "edf": ("EDF", "stateless", "experiments/orchestration/live2/arms.py:576", "earliest-deadline-first scheduling"),
    "kvflow-prefetch": ("KVFlow", "stateful", "experiments/orchestration/baselines/kvflow_adapted.py:34",
        "prefetch and retain KV across queries"),
    "always-cloud-fcfs": ("Always-cloud FCFS", "stateless", "experiments/orchestration/live2/arms.py:102",
        "every query to cloud, first come first served"),
    "querystream-proactive": ("QueryStream", "stateless",
        "experiments/orchestration/baselines/querystream_adapted.py:47,83",
        "proactive half only; per-session size memory for defer rule, no KV management"),
    "attentionstore-prefetch": ("AttentionStore", "stateful",
        "experiments/orchestration/baselines/attentionstore_adapted.py:28", "retains KV across rounds, prefetches"),
    "lmcache": ("LMCache", "stateful", "experiments/orchestration/baselines/lmcache_adapted.py:26",
        "KV cache offload, reuse and eviction"),
    "warm-all-lru": ("Warm-all LRU", "stateful", "experiments/orchestration/live2/arms_warmall.py:72",
        "keeps every session warm under LRU eviction"),
    "confidence-cascade": ("Confidence cascade", "stateless",
        "experiments/orchestration/baselines/cascade_adapted.py:42",
        "per-query confidence cascade routing"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_f1():
    rows = list(csv.DictReader(open(F1)))
    per = defaultdict(dict)   # arm -> seed -> pooled_correct
    for r in rows:
        if r["seed"] == "all" or r["pooled_correct"] in ("", None):
            continue
        per[r["arm"]][r["seed"]] = int(r["pooled_correct"])
    return per, rows


def load_units():
    u = defaultdict(dict)     # arm -> (seed, qid) -> correct
    for r in csv.DictReader(gzip.open(UNITS, "rt")):
        u[r["arm"]][(r["seed"], r["qid"])] = int(r["correct_by_deadline"])
    return u


def system_diff(arm, seeds_arm, units):
    """arm vs device-only on the same (seed, qid) units, over the seeds the arm has."""
    a = units[arm]; d = units[DEVICE]
    keys = [k for k in a if k[0] in seeds_arm and k in d]
    arm_c = np.array([a[k] for k in keys], float)
    dev_c = np.array([d[k] for k in keys], float)
    qids = sorted({k[1] for k in keys})
    cidx = {q: i for i, q in enumerate(qids)}
    cl = np.array([cidx[k[1]] for k in keys])
    diff = arm_c - dev_c
    csum = np.bincount(cl, weights=diff, minlength=len(qids))
    rng = np.random.default_rng(BSEED)
    draws = rng.integers(0, len(qids), size=(NBOOT, len(qids)))
    boot = csum[draws].sum(axis=1)
    return {"n_units": len(keys), "diff": float(diff.sum()),
            "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}


def paired_covex(arm, covex_arm, units):
    """COVEX minus this arm on the same (seed, question) units; question-clustered bootstrap, 2,000, seed 0."""
    a = units[covex_arm]; b = units[arm]
    keys = [k for k in b if k in a]
    d = np.array([a[k] - b[k] for k in keys], float)
    qids = sorted({k[1] for k in keys}); idx = {q: i for i, q in enumerate(qids)}
    cl = np.array([idx[k[1]] for k in keys])
    cs = np.bincount(cl, weights=d, minlength=len(qids))
    rng = np.random.default_rng(BSEED)
    dr = rng.integers(0, len(qids), size=(NBOOT, len(qids)))
    bs = cs[dr].sum(axis=1)
    return {"diff": int(d.sum()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            "n_units": len(keys), "excludes_zero": bool(np.percentile(bs, 2.5) > 0)}


def make_build(rows, covex_arm):
    from matplotlib.patches import Patch
    n = len(rows)
    base_val = max(r["diff"] for r in rows if r["class"] != "covex")
    cov = rows[0]
    ratio = cov["diff"] / base_val
    covex_label = ps.legend_label(covex_arm)

    def build(fig, mode):
        INK = fc.INK
        ax = fig.add_axes([0.385, 0.19, 0.585, 0.75])
        ys = np.arange(n)[::-1]
        for y, r in zip(ys, rows):
            ax.barh(y, r["diff"], height=0.6, color=fc.color(r["arm"]), edgecolor="none", linewidth=0)
            val = f"+{r['diff']}" if r["diff"] >= 0 else (f"$-${abs(r['diff'])}" if mode == "pgf" else f"-{abs(r['diff'])}")
            if r["class"] == "covex" and mode == "pgf":
                val = r"\textbf{" + val + "}"
            ax.text(r["diff"] + 8, y, val, va="center", ha="left", fontsize=8, color=INK,
                    fontweight="bold" if r["class"] == "covex" else "normal")
        ax.set_yticks([])
        labs = []
        for r in rows:
            lab = (r"\textbf{COVEX}" if mode == "pgf" else "COVEX") if r["class"] == "covex" else fc.label(r["arm"], mode)
            if r["arm"] != covex_arm and len(r["seeds"]) < 4:
                lab += f" ({len(r['seeds'])} seeds)"
            labs.append(lab)
        fc.right_labels(ax, ys, labs, [r["class"] == "covex" for r in rows], fs=8, x=-0.012)
        ax.axvline(0, color=INK, lw=0.6, zorder=2)
        ax.set_xlim(-45, 360)
        ax.set_ylim(-0.6, n - 0.4 + 0.5)
        ax.set_xticks([0, 100, 200, 300])
        ps.style_axes(ax)
        ax.tick_params(axis="both", labelsize=8)
        ax.tick_params(axis="x", length=2, color=INK)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(INK); ax.spines["bottom"].set_linewidth(0.6)
        ax.set_xlabel("Additional correct answers\nover the on-device model", fontsize=8.5, color=INK, labelpad=3)
        yA = n - 1 + 0.72
        ax.annotate("", xy=(cov["diff"], yA), xytext=(base_val, yA),
                    arrowprops=dict(arrowstyle="<->", color=INK, lw=0.6, shrinkA=0, shrinkB=0))
        rtxt = f"{ratio:.1f}$\\times$" if mode == "pgf" else f"{ratio:.1f}x"
        ax.text((cov["diff"] + base_val) / 2, yA + 0.12, rtxt, ha="center", va="bottom", fontsize=8,
                color=INK, fontweight="bold")
        handles = [Patch(facecolor=fc.CLASS_COLOR["covex"], edgecolor="none", label=covex_label),
                   Patch(facecolor=fc.CLASS_COLOR["stateful"], edgecolor="none", label="Stateful"),
                   Patch(facecolor=fc.CLASS_COLOR["stateless"], edgecolor="none", label="Stateless")]
        ax.legend(handles=handles, loc="lower right", ncol=1, frameon=False, fontsize=7.5, handlelength=1.0,
                  handletextpad=0.4, borderaxespad=0.3, labelcolor=INK)
    return build, ratio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covex-arm", default=ps.COVEX_RUNG3)
    ap.add_argument("--seeds", default="4,5,6,7")
    a = ap.parse_args()
    seeds = [s.strip() for s in a.seeds.split(",")]
    f1, f1rows = load_f1()
    units = load_units()
    dev_sum = sum(f1[DEVICE][s] for s in seeds)
    systems = {a.covex_arm: {"display": "COVEX", "class": "covex", "seeds": [s for s in seeds if s in f1[a.covex_arm]],
                             "class_ref": "experiments/orchestration/live2/arms_final_ladder.py (rung 3 arm)",
                             "class_basis": "COVEX (this paper's policy)"}}
    for arm, (disp, c, ref, basis) in CLASS_REFS.items():
        have = [s for s in seeds if s in f1.get(arm, {})]
        systems[arm] = {"display": disp, "class": c, "seeds": have, "class_ref": ref, "class_basis": basis}
    rows = []
    for arm, info in systems.items():
        if not info["seeds"]:
            raise SystemExit(f"no committed pooled_correct rows for {arm}")
        res = system_diff(arm, set(info["seeds"]), units)
        f1sum = sum(f1[arm][s] for s in info["seeds"]) - sum(f1[DEVICE][s] for s in info["seeds"])
        if f1sum != round(res["diff"]):
            raise SystemExit(f"F1 vs units mismatch for {arm}: F1 {f1sum} units {res['diff']}")
        rows.append({"arm": arm, "display": info["display"], "class": info["class"], "seeds": info["seeds"],
                     "class_ref": info["class_ref"], "class_basis": info["class_basis"],
                     "diff": int(round(res["diff"])), "ci95": [round(x, 2) for x in res["ci95"]],
                     "n_units": res["n_units"]})
    for r in rows:
        if r["arm"] != a.covex_arm:
            r["paired_covex_minus_this"] = paired_covex(r["arm"], a.covex_arm, units)
    rows.sort(key=lambda r: -r["diff"])
    assert rows[0]["arm"] == a.covex_arm
    base_rows = [r for r in rows if r["arm"] != a.covex_arm]
    top = max(r["diff"] for r in base_rows)
    tied_top = [r["display"] for r in base_rows if r["diff"] == top]
    n_neg = sum(1 for r in base_rows if r["diff"] < 0)
    build, ratio = make_build(rows, a.covex_arm)
    # provenance: every F1 row used (arm cells plus device-only cells on the same seeds)
    used = [r for r in f1rows if r["seed"] in seeds and r["arm"] in set(systems) | {DEVICE}
            and (r["arm"] in (DEVICE, a.covex_arm) or r["seed"] in systems[r["arm"]]["seeds"])]
    prow = [{"status": ps.arm_status(r["arm"], r["status"]), "figdata_status": r["status"], "arm": r["arm"],
             "seed": r["seed"], "run_dir": r["run_dir"], "run_commit": r["run_commit"],
             "pipeline_sha": r["pipeline_sha"], "pooled_correct": r["pooled_correct"]} for r in used]
    statuses = [p["status"] for p in prow]
    body = ("Correct, on-time answers gained over the on-device model. COVEX extracts 3$\\times$ more of the "
            "cloud's benefit than any baseline.")
    ps.save_figure(build, STEM, ps.SINGLE_IN, 2.35, statuses, prow, body, extra="rung 3 stand-in for COVEX, seeds 4-7")
    j = ps.OUTDIR / f"{STEM}.rows.json"
    d = json.loads(j.read_text())
    d.update({"covex_arm": a.covex_arm, "seeds": seeds, "device_only_pooled_correct": dev_sum, "systems": rows,
              "ratio_covex_over_highest_baseline_value": round(ratio, 2), "highest_baseline_value": top,
              "highest_baseline_value_tied_with": tied_top, "n_baselines_below_device": n_neg,
              "caption_claim_all_paired_ci_exclude_zero": all(r["paired_covex_minus_this"]["excludes_zero"] for r in base_rows),
              "F1_csv_sha256": sha(F1), "F1_units_sha256": sha(UNITS),
              "eco_llm_seeds": "4, 6, 7 (seed 5 has no canon-scorable cell)",
              "placeholder": "regenerated after the freeze on the evaluation seeds (seeds 1 to 3 for baselines still to run)"})
    j.write_text(json.dumps(d, indent=1))
    fc.finish(STEM)
    print(json.dumps({"rows": [(r["display"], r["diff"], r["ci95"], r["seeds"]) for r in rows],
                      "ratio": round(ratio, 2), "below_device": n_neg}, indent=1))


if __name__ == "__main__":
    main()
