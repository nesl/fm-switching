#!/usr/bin/env python3
"""Dashcam oracle measure, candidate A: per-instant calibrated crash probability, Brier improvement
over device-only (CPU, committed data, read-only).

PRE-REGISTERED GATE (fixed before any number is computed; a fail STOPS and is reported, no substitute):
  G1: cloud-only beats device-only on this measure. Pass iff the mean per-instant Brier improvement of
      the cloud probability over the device probability (labelled instants, all seeds, clip-cluster
      bootstrap, 2000 resamples, seed 0) is > 0 AND its 95% CI lower bound is > 0.
  G2: arm ordering agrees with committed DSMAP challenge mAP. Spearman rho between the per-arm
      realised gain on this measure and DSMAP ALL challenge mAP, clip-cluster bootstrap CI. Pass iff
      rho > 0 AND the 95% CI lower bound is > 0.

Calibration: Platt (logistic on the raw score) per tier, 5-fold cross-fitted BY CLIP over all 300 Nexar
clips, using the committed fold rule (within each clip-label stratum, order by sha256(file_name) hex,
fold = rank mod 5; D204 / StudyCTRL1b-crossfit). For each clip the map is fitted on the other folds.
Calibration data: SH-EP EP-G per-instant scores (device = 4BI file, cloud = 32BI file). Labels: positive
= instant 0.5 to 3.0 s before the event (rel_to_ref in [-3.0, -0.5]) of a positive clip; negative = any
instant of a negative clip; other instants excluded.

Scoring: live 1x trace instants (seeds 4 to 7). The device probability uses the device score; the
cloud probability uses the simplestream dense cloud score. Each clip is scored by the map of its own
fold (never fitted on it). Labels as above, live timing relative to the nexar reference.

Value per labelled instant: imp = (y - p_dev)^2 - (y - p_cloud)^2 (Brier improvement of serving cloud
over device). Log-loss improvement reported beside. Served instants use cloud when the arm delivered
the dashcam instant on time (D165 B), device otherwise.
FAIR: expected improvement per (tier, horizon bucket), pooled across arms (the full trace population).
HINDSIGHT: the realised imp per instant. Oracle: sum of max(0, value) over labelled instants.
Shares = policy / oracle (floor is device-only = 0 by construction). Clip-cluster bootstrap CIs.
"""
from __future__ import annotations
import gzip, hashlib, json, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
SH4 = REPO / "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
SH32 = REPO / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
for p in ("experiments/analysis/oracle", "experiments/analysis/episodic", "experiments/analysis/early1",
          "experiments/analysis/canon", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import dashcam_episodic as DC  # noqa: E402
import oracle_lp_run as R  # noqa: E402
import episodic_lib as E  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
NB, BSEED = 2000, 0
LEAD = (0.5, 3.0)
G1_CRIT = "mean Brier improvement > 0 and CI lower > 0"
G2_CRIT = "Spearman rho > 0 and CI lower > 0"
HBK = [(0.5, 1.0), (1.0, 2.0), (2.0, 3.0)]


def hb(lead):
    for i, (a, b) in enumerate(HBK):
        if a <= lead < b or (i == len(HBK) - 1 and lead == b):
            return i
    return None


def lab(clip_label, rel):
    """1 positive lead instant, 0 no-crash instant, None excluded."""
    if clip_label == "negative":
        return 0
    if clip_label == "positive" and LEAD[0] <= -rel <= LEAD[1] + 1e-9:
        return 1
    return None


def folds_by_clip(labels):
    strata = collections.defaultdict(list)
    for c, m in labels.items():
        strata[m.get("label")].append(c)
    fold = {}
    for lbl, clips in strata.items():
        ordered = sorted(clips, key=lambda c: hashlib.sha256(c.encode()).hexdigest())
        for rank, c in enumerate(ordered):
            fold[c] = rank % 5
    return fold


def load_shep(path, tier, labels):
    op = gzip.open if str(path).endswith(".gz") else open
    rows = []
    with op(path, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("condition") != "EP-G" or r.get("score") is None:
                continue
            clip = r["file_name"]
            rel = r.get("rel_to_ref")
            rel = float(rel) if rel is not None else None
            cl = (labels.get(clip) or {}).get("label") or r.get("label")
            if cl == "positive" and rel is None:
                continue                      # cannot place a positive instant in the lead window
            y = lab(cl, rel if rel is not None else 0.0)
            if y is None:
                continue
            rows.append((clip, float(r["score"]), y))
    return rows


def fit_platt(X, y):
    m = LogisticRegression(C=1e6, max_iter=1000)
    m.fit(np.array(X).reshape(-1, 1), np.array(y))
    return float(m.coef_[0, 0]), float(m.intercept_[0])


def sig(z):
    return 1.0 / (1.0 + np.exp(-z))


def main():
    labels = DC.nexar_labels()
    fold = folds_by_clip({c: m for c, m in labels.items() if m.get("label") in ("positive", "negative")})
    maps = {}
    for tier, path in (("device", SH4), ("cloud", SH32)):
        rows = load_shep(path, tier, labels)
        maps[tier] = {}
        for k in range(5):
            tr = [(s, y) for c, s, y in rows if fold.get(c) != k]
            a, b = fit_platt([s for s, _ in tr], [y for _, y in tr])
            maps[tier][k] = (a, b)
        maps[tier]["n_rows"] = len(rows)
    # live scoring: one row per labelled live instant
    live = []   # (seed, clip, rel, y, p_dev, p_cld, horizon_bucket, opp_id, cloud_present)
    for s in SEEDS:
        cloud = R.simplestream_cloud(s, "")
        for r in DC.load_trace_instants(s):
            clip = r["clip"]
            m = labels.get(clip) or {}
            if clip not in fold or m.get("ref") is None:
                continue
            rel = float(r["t_local"]) - float(m["ref"])
            y = lab(m.get("label"), rel)
            if y is None:
                continue
            ds = r.get("device_score")
            if ds is None:
                continue
            cs = cloud.get(r["opportunity_id"])
            cloud_present = cs is not None
            cs = ds if cs is None else cs
            k = fold[clip]
            a, b = maps["device"][k]; p_d = float(sig(a * float(ds) + b))
            a, b = maps["cloud"][k]; p_c = float(sig(a * float(cs) + b))
            live.append((s, clip, -rel, y, p_d, p_c, hb(-rel), r["opportunity_id"], cloud_present))
    n = len(live)
    y = np.array([x[3] for x in live], float)
    pd = np.array([x[4] for x in live]); pc = np.array([x[5] for x in live])
    imp = (y - pd) ** 2 - (y - pc) ** 2
    ll = lambda p: -(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))
    lli = ll(pd) - ll(pc)
    clips = np.array([x[1] for x in live])
    uniq = sorted(set(clips))
    cidx = {c: i for i, c in enumerate(uniq)}
    ci = np.array([cidx[c] for c in clips])
    rng = np.random.default_rng(BSEED)
    # G1: mean Brier improvement, cluster bootstrap over clips
    def cluster_mean(vals, idx_by_cluster, draws):
        sums = np.bincount(ci, weights=vals, minlength=len(uniq))
        cnts = np.bincount(ci, minlength=len(uniq)).astype(float)
        bs = []
        for d in draws:
            bs.append(sums[d].sum() / max(cnts[d].sum(), 1))
        return np.array(bs)
    draws = rng.integers(0, len(uniq), size=(NB, len(uniq)))
    g1_pt = float(imp.mean())
    g1_bs = cluster_mean(imp, None, draws)
    g1 = {"mean_brier_improvement": round(g1_pt, 6), "ci95": [round(float(np.percentile(g1_bs, 2.5)), 6),
                                                              round(float(np.percentile(g1_bs, 97.5)), 6)],
          "mean_logloss_improvement": round(float(lli.mean()), 6),
          "device_brier": round(float(((y - pd) ** 2).mean()), 6), "cloud_brier": round(float(((y - pc) ** 2).mean()), 6),
          "n_labelled_instants": n, "n_pos": int(y.sum()), "n_neg": int((1 - y).sum()),
          "criterion": G1_CRIT}
    g1["pass"] = bool(g1_pt > 0 and g1["ci95"][0] > 0)
    # ----- arms: 1x served sets (dashcam on-time cloud per opportunity), seeds 4 to 7
    arm_defs = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]
    served = {}
    for disp, raw in arm_defs:
        served[disp] = {}
        for s in SEEDS:
            path = RUNS / f"{raw}_n16_s{s}_1200s_h27_3t_L3_epg_rq30" / "outcomes.jsonl.gz"
            if not path.exists():
                continue
            on = set()
            with gzip.open(path, "rt") as f:
                for line in f:
                    o = json.loads(line)
                    if str(o.get("device_id", "")).startswith("dash") and (o.get("cloud_payload") or {}).get("on_time"):
                        on.add(o["opportunity_id"])
            served[disp][s] = on
    # per-instant served indicator per arm
    oppidx = {}
    for i, x in enumerate(live):
        oppidx[(x[0], x[7])] = i
    arm_clip_gain = {}
    arm_names = []
    for disp in served:
        if not served[disp]:
            continue
        g = np.zeros(len(uniq)); e = np.zeros(len(uniq))
        mask = np.zeros(n, bool)
        for s, on in served[disp].items():
            for o in on:
                i = oppidx.get((s, o))
                if i is not None:
                    mask[i] = True
        arm_clip_gain[disp] = mask
        arm_names.append(disp)
    # DSMAP committed challenge mAP (ALL split)
    dsm = json.load(open(REPO / "reports/figures/dsmap_results.json"))["arms"]
    common = [a for a in arm_names if a in dsm and dsm[a].get("splits", {}).get("ALL", {}).get("challenge_mAP") is not None]
    mAP = np.array([dsm[a]["splits"]["ALL"]["challenge_mAP"] for a in common])
    # per-arm realised gain (HINDSIGHT) pooled: sum of imp over served labelled instants / labelled count
    def arm_hind(mask, w=None):
        v = imp * mask
        return v
    # ----- G2 Spearman with clip-cluster bootstrap
    arm_vals = {a: np.bincount(ci, weights=imp * arm_clip_gain[a], minlength=len(uniq)) for a in common}
    gmat = np.array([arm_vals[a] for a in common])
    rho_pt = float(spearmanr([gmat[i].sum() for i in range(len(common))], mAP).correlation)
    rho_bs = []
    for d in draws[:NB]:
        sums = np.array([gmat[i][d].sum() for i in range(len(common))])
        rho_bs.append(spearmanr(sums, mAP).correlation)
    rho_bs = np.array(rho_bs)
    g2 = {"spearman_rho": round(rho_pt, 4), "ci95": [round(float(np.nanpercentile(rho_bs, 2.5)), 4),
                                                    round(float(np.nanpercentile(rho_bs, 97.5)), 4)],
          "n_arms": len(common), "criterion": G2_CRIT}
    g2["pass"] = bool(rho_pt > 0 and g2["ci95"][0] > 0)
    out = {"_what": "Dashcam oracle measure candidate A (per-instant Brier improvement over device). Gate "
                    "pre-registered in this file's header.", "calibration_rows": {"device": maps["device"]["n_rows"],
                                                                                   "cloud": maps["cloud"]["n_rows"]},
           "maps_by_fold": {t: {str(k): maps[t][k] for k in range(5)} for t in ("device", "cloud")},
           "G1": g1, "G2": g2, "gate_pass": bool(g1["pass"] and g2["pass"])}
    out["_provenance"] = stamp(script="dashcam_brier.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/dashcam_brier_candidateA.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("G1", g1["mean_brier_improvement"], g1["ci95"], "pass", g1["pass"],
          "| G2 rho", g2["spearman_rho"], g2["ci95"], "pass", g2["pass"], "| GATE", out["gate_pass"])
    return out


if __name__ == "__main__":
    main()
