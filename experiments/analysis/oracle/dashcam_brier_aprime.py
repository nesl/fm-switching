#!/usr/bin/env python3
"""Candidate A-prime (pre-registered in reports/study_dashcam_diagnosis.md): candidate A's measure with
each tier's Platt map fitted on LIVE scores, cross-fitted by clip with the committed clip_to_fold rule,
pooled across arms and seeds 4 to 7 (1x). Gates identical to candidate A (dashcam_brier.py header):
  G1: mean Brier improvement of cloud over device > 0, clip-cluster bootstrap CI lower bound > 0.
  G2: Spearman rho(per-arm realised cloud gain, DSMAP challenge mAP) > 0, CI lower bound > 0.
A failure STOPS and is reported. CPU, read-only.
"""
from __future__ import annotations
import gzip, json, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/analysis/canon"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import dashcam_episodic as DC  # noqa: E402
import oracle_lp_run as R  # noqa: E402
import episodic_lib as E  # noqa: E402
from dashcam_brier import lab, hb, fit_platt, sig, LEAD  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
NB, BSEED = 2000, 0
CAL = REPO / "results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json"
ARMS = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]


def main():
    labels = DC.nexar_labels()
    c2f = json.load(open(CAL))["clip_to_fold"]          # committed 5-fold assignment by clip
    # 1. live labelled rows (arm-independent trace; cloud = simplestream dense)
    rows = []
    for s in SEEDS:
        cloud = R.simplestream_cloud(s, "")
        for r in DC.load_trace_instants(s):
            clip = r["clip"]
            m = labels.get(clip) or {}
            if m.get("ref") is None or clip not in c2f:
                continue
            rel = float(r["t_local"]) - float(m["ref"])
            y = lab(m.get("label"), rel)
            if y is None or r.get("device_score") is None:
                continue
            cs = cloud.get(r["opportunity_id"])
            cs = float(r["device_score"]) if cs is None else float(cs)
            rows.append({"s": s, "clip": clip, "opp": r["opportunity_id"], "y": y,
                         "ds": float(r["device_score"]), "cs": cs, "lead": -rel, "hb": hb(-rel),
                         "fold": int(c2f[clip])})
    # 2. cross-fitted live Platt maps: fold k map fitted on labelled live rows of the other folds
    maps = {"device": {}, "cloud": {}}
    for k in range(5):
        tr = [r for r in rows if r["fold"] != k]
        maps["device"][k] = fit_platt([r["ds"] for r in tr], [r["y"] for r in tr])
        maps["cloud"][k] = fit_platt([r["cs"] for r in tr], [r["y"] for r in tr])
    y = np.array([r["y"] for r in rows], float)
    pd = np.array([sig(maps["device"][r["fold"]][0] * r["ds"] + maps["device"][r["fold"]][1]) for r in rows])
    pc = np.array([sig(maps["cloud"][r["fold"]][0] * r["cs"] + maps["cloud"][r["fold"]][1]) for r in rows])
    imp = (y - pd) ** 2 - (y - pc) ** 2
    clips = [r["clip"] for r in rows]
    uniq = sorted(set(clips))
    cidx = {c: i for i, c in enumerate(uniq)}
    ci = np.array([cidx[c] for c in clips])
    rng = np.random.default_rng(BSEED)
    draws = rng.integers(0, len(uniq), size=(NB, len(uniq)))
    csum = np.bincount(ci, weights=imp, minlength=len(uniq))
    ccnt = np.bincount(ci, minlength=len(uniq)).astype(float)
    g1_bs = np.array([csum[d].sum() / max(ccnt[d].sum(), 1) for d in draws])
    g1_pt = float(imp.mean())
    g1 = {"mean_brier_improvement": round(g1_pt, 6),
          "ci95": [round(float(np.percentile(g1_bs, 2.5)), 6), round(float(np.percentile(g1_bs, 97.5)), 6)],
          "device_brier": round(float(((y - pd) ** 2).mean()), 6),
          "cloud_brier": round(float(((y - pc) ** 2).mean()), 6),
          "n_labelled_instants": len(rows), "n_clips": len(uniq)}
    g1["pass"] = bool(g1_pt > 0 and g1["ci95"][0] > 0)
    # 3. per-arm realised cloud gain (on-time dashcam cloud delivery per opportunity, seeds 4 to 7)
    oppidx = {(r["s"], r["opp"]): i for i, r in enumerate(rows)}
    arm_mask = {}
    for disp, raw in ARMS:
        mask = np.zeros(len(rows), bool); got = False
        for s in SEEDS:
            oc = RUNS / f"{raw}_n16_s{s}_1200s_h27_3t_L3_epg_rq30" / "outcomes.jsonl.gz"
            if not oc.exists():
                continue
            got = True
            with gzip.open(oc, "rt") as f:
                for line in f:
                    o = json.loads(line)
                    if str(o.get("device_id", "")).startswith("dash") and (o.get("cloud_payload") or {}).get("on_time"):
                        i = oppidx.get((s, o["opportunity_id"]))
                        if i is not None:
                            mask[i] = True
        if got:
            arm_mask[disp] = mask
    dsm = json.load(open(REPO / "reports/figures/dsmap_results.json"))["arms"]
    common = [a for a in arm_mask if dsm.get(a, {}).get("splits", {}).get("ALL", {}).get("challenge_mAP") is not None]
    mAP = np.array([dsm[a]["splits"]["ALL"]["challenge_mAP"] for a in common])
    gmat = np.array([np.bincount(ci, weights=imp * arm_mask[a], minlength=len(uniq)) for a in common])
    rho_pt = float(spearmanr(gmat.sum(axis=1), mAP).correlation)
    rho_bs = []
    for d in draws:
        rho_bs.append(float(spearmanr(gmat[:, d].sum(axis=1), mAP).correlation))
    rho_bs = np.array(rho_bs)
    g2 = {"spearman_rho": round(rho_pt, 4),
          "ci95": [round(float(np.nanpercentile(rho_bs, 2.5)), 4), round(float(np.nanpercentile(rho_bs, 97.5)), 4)],
          "n_arms": len(common), "arms": common}
    g2["pass"] = bool(rho_pt > 0 and g2["ci95"][0] > 0)
    out = {"_what": "Candidate A-prime: live-fitted, clip-cross-fitted (committed clip_to_fold) Platt "
                    "maps; Brier improvement of cloud over device; gates G1 and G2 pre-registered.",
           "maps_by_fold": {t: {str(k): maps[t][k] for k in range(5)} for t in maps},
           "G1": g1, "G2": g2, "gate_pass": bool(g1["pass"] and g2["pass"])}
    out["_provenance"] = stamp(script="dashcam_brier_aprime.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/dashcam_brier_aprime.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("G1", g1["mean_brier_improvement"], g1["ci95"], "pass", g1["pass"],
          "| G2 rho", g2["spearman_rho"], g2["ci95"], "pass", g2["pass"], "| GATE", out["gate_pass"])
    return out


if __name__ == "__main__":
    main()
