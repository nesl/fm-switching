#!/usr/bin/env python3
"""Paper Figure 1 (intro teaser), D334: additional correct answers by deadline over on-device answers alone.

OFFLINE, reads only committed files: reports/figdata/F1.csv (per-seed pooled_correct, the committed canon/figdata
rows) and reports/figdata/F1_units.csv.gz (per-question correct_by_deadline, the paired units). Writes:
  figures/paper/F01_intro_teaser.pdf (TrueType fonts), .png (300 dpi), .caption.txt, .provenance.json

Quantity per system: sum over the system's seeds of pooled_correct (robot + single-shot, committed scorer rule)
minus the device-only arm's pooled_correct over the SAME seeds. Dashcam is not counted.
CI: 95% clustered bootstrap by question_id (2,000 resamples, seed 0), paired with device-only on the same
(seed, question) units.

usage: python3 -I f01_intro_teaser.py [--covex-arm covex-v6-fair-final] [--seeds 4,5,6,7]

Systems: the COVEX arm and the baselines below. confidence-cascade is excluded (not in this figure, by ruling).
eco-llm uses the seeds that have a committed row (seed 5 has none); its device-only comparison uses the same seeds.
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, subprocess, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
F1 = REPO / "reports/figdata/F1.csv"
UNITS = REPO / "reports/figdata/F1_units.csv.gz"
OUTDIR = REPO / "figures/paper"
NBOOT, BSEED = 2000, 0
DEVICE = "device-only"

# Classes (ruling 2026-11-27 ~13:06). STATEFUL: the baseline's own policy manages KV or prefix state across queries.
# STATELESS: per-query scheduling, routing or context selection, even when the context carries history.
# Each entry: committed arm -> (display name, class, class-defining file:line, stated basis).
BASELINES = {
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


def git_sha():
    return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()


def load_f1():
    rows = list(csv.DictReader(open(F1)))
    per = defaultdict(dict)   # arm -> seed -> pooled_correct
    for r in rows:
        if r["seed"] == "all" or r["pooled_correct"] in ("", None):
            continue
        per[r["arm"]][r["seed"]] = int(r["pooled_correct"])
    return per


def load_units():
    u = defaultdict(dict)     # arm -> (seed, qid) -> correct
    for r in csv.DictReader(gzip.open(UNITS, "rt")):
        u[r["arm"]][(r["seed"], r["qid"])] = int(r["correct_by_deadline"])
    return u


def system_diff(arm, seeds_arm, units, covex_key):
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


def render(out, rows, pooled_n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Patch
    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7, "hatch.linewidth": 0.8,
                         "font.family": "sans-serif",
                         "font.sans-serif": ["Linux Biolinum O", "Libertinus Sans", "DejaVu Sans"]})
    fam = None
    for cand in ("Linux Biolinum O", "Libertinus Sans", "DejaVu Sans"):
        try:
            font_manager.findfont(cand, fallback_to_default=False)
            fam = cand; break
        except Exception:
            continue
    plt.rcParams["font.sans-serif"] = [fam]
    out["font"] = fam
    C_COVEX, C_STATE, C_STATEFUL = "#285B91", "#8C8C8C", "#BDBDBD"
    INK, SEC, HATCH = "#1A1A1A", "#555555", "#6E6E6E"
    n = len(rows)
    fig = plt.figure(figsize=(3.33, 2.45))
    ax = fig.add_axes([0.355, 0.215, 0.6, 0.72])
    ys = np.arange(n)[::-1]
    for y, r in zip(ys, rows):
        if r["class"] == "covex":
            col, hatch, ec = C_COVEX, None, "none"
        elif r["class"] == "stateful":
            col, hatch, ec = C_STATEFUL, "//", HATCH
        else:
            col, hatch, ec = C_STATE, None, "none"
        ax.barh(y, r["diff"], height=0.66, color=col, edgecolor=ec, hatch=hatch, linewidth=0.0)
        lo, hi = r["ci95"]
        # error bars removed (ruling: figure shows values only; paired CIs are in the rows JSON)
        label = f"{r['diff']:+d}".replace("+-", "-")
        x_lab = r["diff"] + 8
        ax.text(x_lab, y, label, va="center", ha="left", fontsize=7, color=INK,
                fontweight="bold" if r["class"] == "covex" else "normal")
    ax.set_yticks(ys)
    ax.set_yticklabels([r["display"] for r in rows], fontsize=7, color=INK)
    for lbl, r in zip(ax.get_yticklabels(), rows):
        if r["class"] == "covex":
            lbl.set_fontweight("bold")
    ax.axvline(0, color=INK, lw=0.6, zorder=2)
    ax.set_xlim(-45, 360)
    ax.set_ylim(-0.7, n - 0.2 + 0.75)
    ax.set_xticks([0, 100, 200, 300])
    ax.tick_params(axis="both", length=0, labelsize=7, colors=INK)
    ax.tick_params(axis="x", length=2, color=INK)
    ax.xaxis.grid(True, color="#E6E6E6", lw=0.4)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK); ax.spines["bottom"].set_linewidth(0.6)
    ax.set_xlabel("Additional correct answers by deadline\nover on-device answers alone",
                  fontsize=7.5, color=INK, labelpad=2)
    # ratio arrow above the top (COVEX) bar, from the highest non-COVEX value (ties are equal values) to COVEX's
    cov = rows[0]; base = max((r for r in rows if r["class"] != "covex"), key=lambda r: r["diff"])
    yA = n - 1 + 0.78
    ax.annotate("", xy=(cov["diff"], yA), xytext=(base["diff"], yA),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=0.6, shrinkA=0, shrinkB=0))
    ratio = cov["diff"] / base["diff"]
    ax.text((cov["diff"] + base["diff"]) / 2, yA + 0.12, f"{ratio:.1f}\u00d7", ha="center", va="bottom",
            fontsize=7, color=INK, fontweight="bold")
    handles = [Patch(facecolor=C_COVEX, edgecolor="none", label="COVEX"),
               Patch(facecolor=C_STATE, edgecolor="none", label="Stateless baselines"),
               Patch(facecolor=C_STATEFUL, edgecolor=HATCH, hatch="//", linewidth=0,
                     label="Stateful baselines")]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=6.5, handlelength=1.1,
              handletextpad=0.4, borderaxespad=0.2, labelcolor=INK)
    fig.set_size_inches(3.33, 2.45)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    pdf = OUTDIR / "F01_intro_teaser.pdf"
    png = OUTDIR / "F01_intro_teaser.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=300)
    out["outputs"] = {"pdf": str(pdf.relative_to(REPO)), "png": str(png.relative_to(REPO))}
    return ratio, base, fam


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covex-arm", default="covex-v6-fair-final")
    ap.add_argument("--seeds", default="4,5,6,7")
    a = ap.parse_args()
    seeds = [s.strip() for s in a.seeds.split(",")]
    f1 = load_f1()
    units = load_units()
    # sanity: F1 pooled sums over the figure seeds (device-only sum is the floor)
    dev_sum = sum(f1[DEVICE][s] for s in seeds)
    systems = {}
    covex_seeds = [s for s in seeds if s in f1[a.covex_arm]]
    systems[a.covex_arm] = {"display": "COVEX", "class": "covex", "seeds": covex_seeds,
                            "class_ref": "experiments/orchestration/live2/arms_final_ladder.py (rung 3 arm)",
                            "class_basis": "COVEX (this paper's policy)"}
    for arm, (disp, cls, ref, basis) in BASELINES.items():
        have = [s for s in seeds if s in f1.get(arm, {})]
        if len(have) < len(seeds):
            disp = f"{disp} ({len(have)} seeds)"
        systems[arm] = {"display": disp, "class": cls, "seeds": have, "class_ref": ref, "class_basis": basis}
    rows = []
    for arm, info in systems.items():
        if not info["seeds"]:
            raise SystemExit(f"no committed pooled_correct rows for {arm}")
        res = system_diff(arm, set(info["seeds"]), units, a.covex_arm)
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
    covex = next(r for r in rows if r["arm"] == a.covex_arm)
    top_base_val = max(r["diff"] for r in rows if r["arm"] != a.covex_arm)
    tied_top = [r["display"] for r in rows if r["arm"] != a.covex_arm and r["diff"] == top_base_val]
    n_neg = sum(1 for r in rows if r["arm"] != a.covex_arm and r["diff"] < 0)
    ratio = covex["diff"] / top_base_val
    pooled_n = 0
    for r in csv.DictReader(open(F1)):
        if r["arm"] == a.covex_arm and r["seed"] in seeds and r["pooled_n"]:
            pooled_n += int(r["pooled_n"])
    out = {"figure": "F01_intro_teaser", "covex_arm": a.covex_arm, "seeds": seeds,
           "device_only_pooled_correct": dev_sum, "rows": rows, "ratio_covex_over_highest_baseline_value": round(ratio, 2),
           "highest_baseline_value": top_base_val, "highest_baseline_value_tied_with": tied_top,
           "n_baselines_below_device": n_neg,
           "covex_pooled_n": pooled_n, "device_only_sum_check": dev_sum,
           "git_sha": git_sha(), "F1_csv_sha256": sha(F1), "F1_units_sha256": sha(UNITS),
           "font": None, "placeholder": ("PLACEHOLDER: this figure is regenerated after the freeze on the evaluation "
                                         "seed set (seeds 1 to 3 for every baseline still to run)."),
           "eco_llm_seeds": "4, 6, 7 (seed 5 has no canon-scorable cell; its valid cell is not chosen by canon)",
           "confidence_cascade": "post-D205 _rerun cells, seeds 4 to 7, scored with canon.collect_units (rows added to F1.csv 2026-11-27)"}
    OUTDIR.mkdir(parents=True, exist_ok=True)
    base_rows = [r for r in rows if r["arm"] != a.covex_arm]
    out["caption_claim_all_paired_ci_exclude_zero"] = all(r["paired_covex_minus_this"]["excludes_zero"] for r in base_rows)
    out["caption_claim_text"] = ("COVEX exceeds every baseline (paired 95% CI excludes 0)"
                                 if out["caption_claim_all_paired_ci_exclude_zero"] else None)
    ratio, base, fam = render(out, rows, pooled_n)
    out["ratio_plotted"] = round(ratio, 2)
    (OUTDIR / "F01_intro_teaser.rows.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"rows": [(r["display"], r["diff"], r["ci95"], r["seeds"]) for r in rows],
                      "ratio": out["ratio_covex_over_highest_baseline_value"], "below_device": n_neg,
                      "covex_pooled_n": pooled_n}, indent=1))


if __name__ == "__main__":
    main()
