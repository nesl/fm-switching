#!/usr/bin/env python3
"""StudyDASH2 Parts 0-2 (D199 metric): power/intervals and the workload-format ceiling. Offline,
read-only, CPU only. No GPU, no inference. Seeds 4-7.

Part 1: clip/play/episode units; 5-fold CROSS-FITTED per-tier Platt calibration by clip (ALL primary,
EVAL with DEV-fitted maps beside); paired CLUSTERED bootstrap over clips (same resample indices for
every arm); minimum detectable difference (paired, 80 percent power, alpha 0.05) and CI half-width.
Part 2: cloud-every-instant ceiling (union of on-time cloud scores across valid arms), coverage,
cache-path spread (D81), challenge mAP and horizon curve for device-every-instant, cloud-every-instant
and each arm, with paired CIs and horizon shift.

Metric: Nexar challenge AP at horizons 0.5 to 3.0 s, challenge mAP = mean at 0.5/1.0/1.5 s. No alarm
timing, thresholds, matched-FAR lead, AUROC or streaming AP. No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/early1"))
sys.path.insert(0, str(ROOT / "experiments/analysis/episodic"))
import dsmap as DS  # noqa: E402  trace, durations_refs, HOR, TRACE
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402

HOR = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
CHALLENGE = [0.5, 1.0, 1.5]
NB = 2000
SEED = 0
NFOLD = 5
Z = 1.959963985 + 0.841621234  # z_0.975 + z_0.80 for 80 percent power, two-sided alpha 0.05
SHEP_4BI = ROOT / "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
SHEP_32BI = ROOT / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
OUT = ROOT / "reports/figures"
ARMS_RAW = {disp: raw for disp, raw in E.ARMS}
ARMS_RAW["fair-c5attr-rr"] = "covex-v6-fair-c5attr-rr"  # Part 0


def _ap(pos, neg):
    s = np.concatenate([pos, neg]); y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    order = np.argsort(-s, kind="mergesort"); y = y[order]
    tp = np.cumsum(y); denom = tp + np.cumsum(1.0 - y)
    prec = np.where(denom > 0, tp / denom, 0.0)
    return float(np.sum(prec * y) / y.sum()) if y.sum() else 0.0


def clip_folds(clips):
    """deterministic 5-fold by clip (sorted index mod NFOLD)."""
    return {c: i % NFOLD for i, c in enumerate(sorted(clips))}


def shep_instants(path):
    op = gzip.open if str(path).endswith(".gz") else open
    rows = []
    with op(path, "rt") as fh:
        for l in fh:
            if '"EP-G"' not in l:
                continue
            r = json.loads(l)
            if r.get("condition") != "EP-G" or r.get("score") is None or r.get("label") is None:
                continue
            rows.append((r["file_name"], float(r["score"]), 1 if r["label"] == "positive" else 0,
                         r.get("side")))
    return rows


def fit_platt(rows):
    from sklearn.linear_model import LogisticRegression
    X = [[s] for _, s, _, _ in rows]; y = [yy for _, _, yy, _ in rows]
    clf = LogisticRegression(C=1e6, solver="lbfgs").fit(X, y)
    return float(clf.coef_[0][0]), float(clf.intercept_[0])


def crossfit_maps(rows, folds):
    """per tier: a Platt map per fold, fit on SH-EP instants whose clip is NOT in that fold."""
    maps = {}
    for f in range(NFOLD):
        sub = [r for r in rows if folds.get(r[0], -1) != f]
        maps[f] = fit_platt(sub)
    # DEV-fitted map (beside)
    dev = [r for r in rows if r[3] == "DEV"]
    dev_map = fit_platt(dev)
    return maps, dev_map


def _trace(seed):
    return DS._trace(seed)


def delivered_crops(arm_raw, seed, dev_map4, dev_map32, cf4, cf32, folds, labels, fake, dur,
                    mode="crossfit", device_only=False):
    """{h: {clip: value}} crops for one seed. mode crossfit uses per-clip-fold maps (ALL); mode dev
    uses the DEV-fitted maps (EVAL beside)."""
    path, _ = E.cell_dir(arm_raw, seed)
    if path is None:
        return None
    tr = _trace(seed)
    cloud = {}
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("dash"):
            continue
        cp = o.get("cloud_payload") or {}
        cloud[o["opportunity_id"]] = (bool(cp.get("on_time")), cp.get("cloud_score"))

    def cal(tier, clip, score):
        if mode == "dev":
            a, b = (dev_map4 if tier == "dev" else dev_map32)
        else:
            a, b = (cf4 if tier == "dev" else cf32)[folds.get(clip, 0)]
        return a * score + b

    by_clip = defaultdict(list)
    for oid, (clip, pts, dscore) in tr.items():
        con, cscore = cloud.get(oid, (False, None))
        if (not device_only) and con and cscore is not None:
            v = cal("cloud", clip, float(cscore))
        else:
            v = cal("dev", clip, dscore)
        by_clip[clip].append((pts, v))
    out = {h: {} for h in HOR}
    for clip, pv in by_clip.items():
        meta = labels.get(clip) or {}
        ref = (float(meta["ref"]) if meta.get("label") == "positive" and meta.get("ref") is not None
               else (fake.get(clip) if meta.get("label") == "negative" else None))
        if ref is None:
            continue
        for h in HOR:
            near = [v for (p, v) in pv if abs(p - (ref - h)) <= 0.5 + 1e-9]
            if near:
                out[h][clip] = float(np.mean(near))
    return out


def pool_over_seeds(per_seed):
    acc = {h: defaultdict(list) for h in HOR}
    for d in per_seed:
        for h in HOR:
            for c, v in d[h].items():
                acc[h][c].append(v)
    return {h: {c: float(np.mean(vs)) for c, vs in acc[h].items()} for h in HOR}


class Boot:
    """paired clustered bootstrap over source clips, shared indices for every stream."""
    def __init__(self, pos, neg):
        self.pos = list(pos); self.neg = list(neg)
        rng = np.random.default_rng(SEED)
        self.b = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
                  for _ in range(NB)]

    def ap_series(self, stream, h):
        Pf = np.array([stream[h].get(c, np.nan) for c in self.pos])
        Nf = np.array([stream[h].get(c, np.nan) for c in self.neg])
        pin = ~np.isnan(Pf); nin = ~np.isnan(Nf)
        pt = _ap(Pf[pin], Nf[nin]) if pin.any() and nin.any() else None
        arr = np.empty(NB)
        for i, (pi, ni) in enumerate(self.b):
            ps = pi[pin[pi]]; ns = ni[nin[ni]]
            arr[i] = _ap(Pf[ps], Nf[ns]) if len(ps) and len(ns) else np.nan
        return pt, arr

    def table(self, stream):
        ap = {}; boot = {}
        for h in HOR:
            pt, arr = self.ap_series(stream, h)
            a = arr[~np.isnan(arr)]
            ap[h] = {"ap": pt, "ci": ([float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
                                      if len(a) else None)}
            boot[h] = arr
        mp = float(np.nanmean([ap[h]["ap"] for h in CHALLENGE if ap[h]["ap"] is not None]))
        bm = np.nanmean([boot[h] for h in CHALLENGE], axis=0)
        bmv = bm[~np.isnan(bm)]
        return {"ap": ap, "challenge_mAP": mp,
                "challenge_mAP_ci": ([float(np.percentile(bmv, 2.5)), float(np.percentile(bmv, 97.5))]
                                     if len(bmv) else None),
                "challenge_mAP_boot": bm}

    def paired(self, ta, tb):
        d = ta["challenge_mAP_boot"] - tb["challenge_mAP_boot"]
        dv = d[~np.isnan(d)]
        return {"diff": ta["challenge_mAP"] - tb["challenge_mAP"],
                "ci": [float(np.percentile(dv, 2.5)), float(np.percentile(dv, 97.5))],
                "sd": float(np.std(dv))}


def horizon_shift(cloud_tab, dev_tab):
    ap_d = {h: dev_tab["ap"][h]["ap"] for h in HOR}
    ap_c = {h: cloud_tab["ap"][h]["ap"] for h in HOR}
    out = {}
    for t0 in CHALLENGE:
        best = None
        for delta in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
            t = round(t0 + delta, 2)
            if t in ap_c and ap_c[t] is not None and ap_d[t0] is not None and ap_c[t] >= ap_d[t0]:
                best = delta
        out[t0] = best
    return out


def cloud_every_instant(seed, valid_arms, cf32, folds):
    """union of on-time cloud scores across valid arms per instant; coverage + D81 spread."""
    tr = _trace(seed)
    per_inst = defaultdict(list)  # oid -> list of cloud_score from arms that served it on time
    for disp in valid_arms:
        path, _ = E.cell_dir(ARMS_RAW[disp], seed)
        if path is None:
            continue
        for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
            if not str(o.get("device_id", "")).startswith("dash"):
                continue
            cp = o.get("cloud_payload") or {}
            if cp.get("on_time") and cp.get("cloud_score") is not None:
                per_inst[o["opportunity_id"]].append(float(cp["cloud_score"]))
    n_inst = len(tr)
    covered = len(per_inst)
    multi = [vs for vs in per_inst.values() if len(vs) >= 2]
    spreads = [max(vs) - min(vs) for vs in multi]
    return per_inst, {"n_instants": n_inst, "covered": covered,
                      "coverage": covered / n_inst if n_inst else None,
                      "n_multi_arm": len(multi),
                      "cache_spread_median": (float(np.median(spreads)) if spreads else None),
                      "cache_spread_p90": (float(np.percentile(spreads, 90)) if spreads else None)}


def main():
    dur, labels = DS.durations_refs()
    # Part 1a units
    units = {}
    allclips = set()
    for s in E.SEEDS:
        tr = _trace(s)
        clips = set(c for c, _, _ in tr.values())
        plays = set()
        eps = set()
        for l in gzip.open(ROOT / DS.TRACE.format(s=s), "rt"):
            r = json.loads(l); plays.add(r["play_id"]); eps.add(r["episode_id"])
        allclips |= clips
        units[s] = {"distinct_clips": len(clips), "plays": len(plays), "episodes": len(eps)}
    # seed clip overlap
    seed_clipsets = {}
    for s in E.SEEDS:
        seed_clipsets[s] = set(c for c, _, _ in _trace(s).values())
    inter = set.intersection(*seed_clipsets.values()) if seed_clipsets else set()
    units["clips_in_all_seeds"] = len(inter)
    units["union_clips"] = len(allclips)
    units["seeds_reuse_clips"] = len(inter) > 0

    folds = clip_folds(allclips)
    rows4 = shep_instants(SHEP_4BI)
    rows32 = shep_instants(SHEP_32BI)
    cf4, dev4 = crossfit_maps(rows4, folds)
    cf32, dev32 = crossfit_maps(rows32, folds)

    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    side = DS.sh_ep_side()

    # which arms exist (have a scorable cell at >=1 seed)
    arms = [d for d in ARMS_RAW if any(E.cell_dir(ARMS_RAW[d], s)[0] for s in E.SEEDS)]

    # build pooled crossfit (ALL) and dev (EVAL) streams per arm
    def build(arm, mode, device_only=False):
        ps = []
        for s in E.SEEDS:
            d = delivered_crops(ARMS_RAW[arm], s, dev4, dev32, cf4, cf32, folds, labels, fake, dur,
                                mode=mode, device_only=device_only)
            if d is not None:
                ps.append(d)
        return pool_over_seeds(ps) if ps else None

    pos_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "positive")
    neg_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "negative")
    pos_eval = [c for c in pos_all if side.get(c) == "EVAL"]
    neg_eval = [c for c in neg_all if side.get(c) == "EVAL"]
    boot_all = Boot(pos_all, neg_all)
    boot_eval = Boot(pos_eval, neg_eval)

    results = {"_what": "StudyDASH2 Parts 0-2 (D199 metric).", "horizons": HOR, "n_bootstrap": NB,
               "part1a_units": units,
               "part1b_crossfit": {"folds": NFOLD, "note": "5-fold by clip; each clip scored with a "
                                   "per-tier Platt map fit on SH-EP EP-G instants of the other folds"},
               "dev_fitted_maps": {"device": dev4, "cloud": dev32}, "arms": {}, "part2": {}}

    # device-only (sanity) and arm streams, cross-fit ALL (primary) + dev EVAL (beside)
    dev_stream_all = build("base", "crossfit", device_only=True)
    dev_tab_all = boot_all.table(dev_stream_all)
    dev_stream_eval = build("base", "dev", device_only=True)
    dev_tab_eval = boot_eval.table(dev_stream_eval)
    results["device_only"] = {"ALL_crossfit_mAP": dev_tab_all["challenge_mAP"],
                              "ALL_ci": dev_tab_all["challenge_mAP_ci"],
                              "EVAL_dev_mAP": dev_tab_eval["challenge_mAP"],
                              "EVAL_ci": dev_tab_eval["challenge_mAP_ci"]}

    arm_tabs_all = {}
    for arm in arms:
        sa = build(arm, "crossfit")
        se = build(arm, "dev")
        if sa is None:
            continue
        ta = boot_all.table(sa); te = boot_eval.table(se)
        arm_tabs_all[arm] = ta
        pr = boot_all.paired(ta, dev_tab_all)
        results["arms"][arm] = {
            "ALL_crossfit_mAP": ta["challenge_mAP"], "ALL_ci": ta["challenge_mAP_ci"],
            "EVAL_dev_mAP": te["challenge_mAP"], "EVAL_ci": te["challenge_mAP_ci"],
            "ALL_vs_device_only": {"diff": pr["diff"], "ci": pr["ci"]},
            "ap_by_horizon_ALL": {h: ta["ap"][h]["ap"] for h in HOR}}

    # Part 1d MDE: paired-diff bootstrap SD, representative = top arm vs rung3
    top = max(arm_tabs_all, key=lambda a: arm_tabs_all[a]["challenge_mAP"])
    r3 = "fair-c5attr"
    sd_pair = boot_all.paired(arm_tabs_all[top], arm_tabs_all.get(r3, dev_tab_all))["sd"]
    # CI half-width before (EVAL dev-fitted, from DSMAP-style) and after (ALL crossfit clustered)
    def halfwidth(ci):
        return (ci[1] - ci[0]) / 2 if ci else None
    results["part1d_power"] = {
        "paired_diff_bootstrap_sd": sd_pair,
        "MDE_challenge_mAP_80pct_power": Z * sd_pair,
        "ci_halfwidth_after_ALL_crossfit_example_top_arm": halfwidth(arm_tabs_all[top]["challenge_mAP_ci"]),
        "ci_halfwidth_before_EVAL_devfit_example_top_arm":
            halfwidth(results["arms"][top]["EVAL_ci"]),
        "_note": "MDE = (z_0.975 + z_0.80) x SD of the paired challenge-mAP difference, clustered by "
                 "clip. Example arm for the half-widths is the top-mAP arm."}

    # Part 2: cloud-every-instant ceiling. valid arms = those on the default EP-G episodes with cloud
    # context identical (all rq30 L3 arms share the trace). Build the union stream per seed, crops.
    valid = [a for a in arms if a != "device-only"]
    cov_meta = {}
    cloud_every = {h: defaultdict(list) for h in HOR}
    for s in E.SEEDS:
        per_inst, meta = cloud_every_instant(s, valid, cf32, folds)
        cov_meta[s] = meta
        tr = _trace(s)
        # build the cloud-every-instant crop: cloud score (median across arms) where covered, else
        # device score filled in
        byclip = defaultdict(list)
        for oid, (clip, pts, dscore) in tr.items():
            if oid in per_inst:
                cs = float(np.median(per_inst[oid]))
                v = cf32[folds.get(clip, 0)][0] * cs + cf32[folds.get(clip, 0)][1]
            else:
                v = cf4[folds.get(clip, 0)][0] * dscore + cf4[folds.get(clip, 0)][1]
            byclip[clip].append((pts, v))
        for clip, pv in byclip.items():
            meta2 = labels.get(clip) or {}
            ref = (float(meta2["ref"]) if meta2.get("label") == "positive"
                   and meta2.get("ref") is not None
                   else (fake.get(clip) if meta2.get("label") == "negative" else None))
            if ref is None:
                continue
            for h in HOR:
                near = [v for (p, v) in pv if abs(p - (ref - h)) <= 0.5 + 1e-9]
                if near:
                    cloud_every[h][clip].append(float(np.mean(near)))
    cloud_stream = {h: {c: float(np.mean(vs)) for c, vs in cloud_every[h].items()} for h in HOR}
    ce_tab = boot_all.table(cloud_stream)
    results["part2"] = {
        "coverage_per_seed": cov_meta,
        "coverage_mean": float(np.mean([cov_meta[s]["coverage"] for s in cov_meta])),
        "cache_spread_median_mean": float(np.mean([cov_meta[s]["cache_spread_median"]
                                                   for s in cov_meta if cov_meta[s]["cache_spread_median"] is not None])),
        "cloud_every_instant_mAP_ALL": ce_tab["challenge_mAP"], "ce_ci": ce_tab["challenge_mAP_ci"],
        "ce_ap_by_horizon": {h: ce_tab["ap"][h]["ap"] for h in HOR},
        "ce_vs_device_only": boot_all.paired(ce_tab, dev_tab_all),
        "horizon_shift_cloud_every_vs_device": horizon_shift(ce_tab, dev_tab_all),
        "horizon_shift_by_arm": {a: horizon_shift(arm_tabs_all[a], dev_tab_all) for a in arm_tabs_all},
        "device_ap_by_horizon": {h: dev_tab_all["ap"][h]["ap"] for h in HOR}}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dash2_results.json").write_text(json.dumps(results, indent=1, default=float))
    _plot(results)
    print("units:", units)
    print("MDE challenge mAP (80% power):", round(results["part1d_power"]["MDE_challenge_mAP_80pct_power"], 4))
    print("CI halfwidth before(EVAL dev)/after(ALL crossfit):",
          round(results["part1d_power"]["ci_halfwidth_before_EVAL_devfit_example_top_arm"], 4), "/",
          round(results["part1d_power"]["ci_halfwidth_after_ALL_crossfit_example_top_arm"], 4))
    print("cloud-every-instant coverage:", round(results["part2"]["coverage_mean"], 4),
          "ceiling mAP:", round(ce_tab["challenge_mAP"], 4),
          "device-only mAP:", round(dev_tab_all["challenge_mAP"], 4))
    print("SANITY device-every == device-only:", round(dev_tab_all["challenge_mAP"], 6))


def _plot(results):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    ax.plot(HOR, [results["part2"]["device_ap_by_horizon"][h] for h in HOR], marker="s",
            color="#000000", lw=2, label=f"device-every ({results['device_only']['ALL_crossfit_mAP']:.2f})")
    ax.plot(HOR, [results["part2"]["ce_ap_by_horizon"][h] for h in HOR], marker="o",
            color="#0072B2", lw=2.4,
            label=f"cloud-every ({results['part2']['cloud_every_instant_mAP_ALL']:.2f})")
    for a, col in (("fair-c5attr", "#D55E00"), ("simplestream", "#9A9A9A")):
        if a in results["arms"]:
            ax.plot(HOR, [results["arms"][a]["ap_by_horizon_ALL"][h] for h in HOR], marker="^",
                    color=col, lw=1.6, label=f"{a} ({results['arms'][a]['ALL_crossfit_mAP']:.2f})")
    ax.set_xlabel("seconds before event (horizon t)")
    ax.set_ylabel("challenge AP (cross-fitted, ALL 300 clips)")
    ax.set_title("StudyDASH2 Part 2: the workload-format ceiling (cloud-every-instant)")
    ax.invert_xaxis(); ax.grid(True, alpha=0.25); ax.legend(fontsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "dash2_ceiling.png", dpi=200, metadata={"Software": None}, bbox_inches="tight")
    fig.savefig(OUT / "dash2_ceiling.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
