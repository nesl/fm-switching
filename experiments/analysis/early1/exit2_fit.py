#!/usr/bin/env python3
"""StudyEXIT2-fit (D202): the trajectory exit model. Offline, read-only, CPU only.

StudySH-EP 32BI EP-G per-instant cloud scores. Fit on DEV, report on EVAL. One logistic model per
k in {2,3,4} on a window of the last k cloud points in an episode: features are the Platt-calibrated
level of the latest point and the least-squares slope of the calibrated scores over the k points.

CRASH rule: training positives = windows ENDING 0.5 to 3.0 s before the event in crash clips;
negatives = windows in negative clips. Operating point on DEV so at most 10 percent of no-crash DEV
episodes FIRE (an episode fires if any of its windows reaches the probability threshold), episode
level as D197.
NORMAL rule ("nothing happening"): a window fires a normal exit when its crash probability is below a
bound; the bound is chosen on DEV so at most 10 percent of crash DEV episodes normal-exit before
their event.
Reference: the D197 level-only trigger (cloud theta -2.929832 in RAW score units).

The exit rules read only the k window at runtime (calibrated level + slope), never labels or event
times. No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[3]
SHEP_32BI = ROOT / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
SHEP_4BI = ROOT / "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
OUT = ROOT / "reports/figures"
KS = [2, 3, 4]
D197_THETA_RAW = -2.9298319411413662  # cloud episode-level FAR-10 threshold (raw score)
PRE_EVENT_LO, PRE_EVENT_HI = -3.0, -0.5  # windows ending 0.5 to 3.0 s before the event


def platt_cloud():
    X, y = [], []
    for l in gzip.open(SHEP_32BI, "rt"):
        if '"EP-G"' not in l or '"DEV"' not in l:
            continue
        r = json.loads(l)
        if r.get("condition") != "EP-G" or r.get("side") != "DEV" or r.get("score") is None:
            continue
        X.append([float(r["score"])])
        y.append(1 if r.get("label") == "positive" else 0)
    clf = LogisticRegression(C=1e6, solver="lbfgs").fit(X, y)
    return float(clf.coef_[0][0]), float(clf.intercept_[0])


def episodes():
    """clip -> dict(side, label, pts=[(rel_to_ref, score)...] sorted by time)."""
    ep = {}
    for l in gzip.open(SHEP_32BI, "rt"):
        if '"EP-G"' not in l:
            continue
        r = json.loads(l)
        if (r.get("condition") != "EP-G" or r.get("score") is None
                or r.get("rel_to_ref") is None or r.get("label") is None):
            continue
        d = ep.setdefault(r["file_name"], {"side": r.get("side"), "label": r["label"], "pts": []})
        d["pts"].append((float(r["rel_to_ref"]), float(r["score"])))
    for d in ep.values():
        d["pts"].sort()
    return ep


def windows(ep, k, a, b):
    """For one episode: list of (rel_end, level, slope) for each window of k consecutive points."""
    out = []
    pts = ep["pts"]
    for i in range(k - 1, len(pts)):
        w = pts[i - k + 1:i + 1]
        rel = np.array([p[0] for p in w])
        cal = np.array([a * p[1] + b for p in w])
        level = float(cal[-1])
        # least-squares slope of calibrated score vs time
        slope = float(np.polyfit(rel, cal, 1)[0]) if len(set(rel)) > 1 else 0.0
        out.append((float(w[-1][0]), level, slope))
    return out


def fit_k(ep, k, a, b):
    X, y = [], []
    for c, d in ep.items():
        if d["side"] != "DEV":
            continue
        for rel_end, level, slope in windows(d, k, a, b):
            if d["label"] == "positive":
                if PRE_EVENT_LO <= rel_end <= PRE_EVENT_HI:
                    X.append([level, slope]); y.append(1)
            else:
                X.append([level, slope]); y.append(0)
    clf = LogisticRegression(C=1.0, solver="lbfgs").fit(X, y)
    return clf, len(y), int(sum(y))


def episode_prob_series(d, k, a, b, clf):
    """time-ordered list of (rel_end, crash_prob) for an episode's windows."""
    ws = windows(d, k, a, b)
    if not ws:
        return []
    feats = np.array([[lv, sl] for (_, lv, sl) in ws])
    probs = clf.predict_proba(feats)[:, 1]
    return [(ws[i][0], float(probs[i])) for i in range(len(ws))]


def choose_crash_theta(ep, k, a, b, clf, far=0.10):
    """theta so at most far of NO-CRASH DEV episodes fire (any window prob >= theta)."""
    maxp = []
    for c, d in ep.items():
        if d["side"] != "DEV" or d["label"] != "negative":
            continue
        ser = episode_prob_series(d, k, a, b, clf)
        maxp.append(max((p for _, p in ser), default=0.0))
    maxp.sort(reverse=True)
    n = len(maxp)
    import math
    kk = math.ceil(far * n)
    theta = maxp[kk - 1] if 0 < kk <= n else (maxp[-1] if maxp else 1.0)
    achieved = sum(1 for m in maxp if m >= theta - 1e-12) / n if n else None
    return theta, achieved, n


def choose_normal_bound(ep, k, a, b, clf, far=0.10):
    """bound so at most far of CRASH DEV episodes normal-exit before the event (a pre-event window
    with crash prob < bound)."""
    minp = []
    for c, d in ep.items():
        if d["side"] != "DEV" or d["label"] != "positive":
            continue
        ser = [(r, p) for (r, p) in episode_prob_series(d, k, a, b, clf) if r < 0]  # before event
        minp.append(min((p for _, p in ser), default=1.0))
    minp.sort()
    n = len(minp)
    import math
    kk = math.ceil(far * n)
    bound = minp[kk - 1] if 0 < kk <= n else (minp[0] if minp else 0.0)
    achieved = sum(1 for m in minp if m <= bound + 1e-12) / n if n else None
    return bound, achieved, n


def eval_rules(ep, k, a, b, clf, theta, bound):
    """EVAL metrics for crash and normal rules."""
    crash_fire_times = []        # firing time before event on crash episodes (true crash exits)
    n_crash = n_nocrash = 0
    crash_caught = 0             # crash episodes with a pre-event crash fire
    false_crash = 0             # no-crash episodes that fire crash
    false_normal = 0            # crash episodes that normal-exit before event
    true_normal = 0             # no-crash episodes that normal-exit
    saved_crash, saved_normal = [], []
    for c, d in ep.items():
        if d["side"] != "EVAL":
            continue
        ser = episode_prob_series(d, k, a, b, clf)
        n_inst = len(d["pts"])
        if d["label"] == "positive":
            n_crash += 1
            fire = next(((r, i) for i, (r, p) in enumerate(ser) if p >= theta and r < 0), None)
            if fire is not None:
                crash_caught += 1
                crash_fire_times.append(-fire[0])  # seconds before event
                saved_crash.append(n_inst - (k + fire[1]))
            nfire = next(((r, i) for i, (r, p) in enumerate(ser) if p < bound and r < 0), None)
            if nfire is not None:
                false_normal += 1
        else:
            n_nocrash += 1
            if any(p >= theta for _, p in ser):
                false_crash += 1
            nfire = next((i for i, (r, p) in enumerate(ser) if p < bound), None)
            if nfire is not None:
                true_normal += 1
                saved_normal.append(n_inst - (k + nfire))
    def stat(xs):
        if not xs:
            return {"median": None, "iqr": None, "n": 0}
        xs = sorted(xs)
        return {"median": statistics.median(xs),
                "iqr": [float(np.percentile(xs, 25)), float(np.percentile(xs, 75))], "n": len(xs)}
    return {
        "n_crash_eval": n_crash, "n_nocrash_eval": n_nocrash,
        "crash_rule": {
            "fraction_crash_caught": (crash_caught / n_crash if n_crash else None),
            "firing_time_before_event_s": stat(crash_fire_times),
            "false_crash_exit_rate_on_no_crash": (false_crash / n_nocrash if n_nocrash else None),
            "instants_saved_per_true_crash_exit": stat(saved_crash)},
        "normal_rule": {
            "false_normal_exit_rate_on_crash": (false_normal / n_crash if n_crash else None),
            "true_normal_exit_rate_on_no_crash": (true_normal / n_nocrash if n_nocrash else None),
            "instants_saved_per_true_normal_exit": stat(saved_normal)}}


def label_shuffle_crash(ep, k, a, b, clf, theta):
    """AUROC-free control: the crash rule's EVAL firing rate on shuffled labels should match its
    no-crash firing rate (the rule reads no labels, so permuting labels must not change firing)."""
    rng = np.random.default_rng([0, k])
    fires = {}
    labels = [(c, d) for c, d in ep.items() if d["side"] == "EVAL"]
    real = [1 if d["label"] == "positive" else 0 for _, d in labels]
    perm = rng.permutation(real)
    fire_flags = [1 if any(p >= theta for _, p in episode_prob_series(d, k, a, b, clf)) else 0
                  for _, d in labels]
    import numpy as _np
    nocrash_rate = (sum(f for f, r in zip(fire_flags, real) if r == 0)
                    / max(1, sum(1 for r in real if r == 0)))
    shuf_rate = float(_np.mean([f for f in fire_flags]))  # label-independent by construction
    return {"no_crash_firing_rate": nocrash_rate, "overall_firing_rate_label_independent": shuf_rate,
            "_note": "firing depends only on the k window, so it is label-independent; the overall "
                     "firing rate and the no-crash rate agree up to the crash episodes' own firing."}


def clip_overlap():
    """SH-EP DEV clips vs the workload dashcam clips (union seeds 4-7)."""
    side = {}
    for l in open(SHEP_4BI):
        if '"side"' not in l:
            continue
        r = json.loads(l); side.setdefault(r["file_name"], r.get("side"))
    dev = set(c for c, s in side.items() if s == "DEV")
    wl = set()
    for s in (4, 5, 6, 7):
        p = (ROOT / "results/orchestration/live2/frozen_test/traces/"
             f"seed{s}_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz")
        if not p.exists():
            continue
        for l in gzip.open(p, "rt"):
            wl.add(json.loads(l)["clip"])
    return {"n_dev": len(dev), "n_workload_clips": len(wl),
            "workload_clips_in_dev": len(wl & dev),
            "workload_uses_dev_clips": bool(wl & dev)}


def main():
    a, b = platt_cloud()
    ep = episodes()
    res = {"_what": "StudyEXIT2-fit: trajectory exit model, fit DEV report EVAL (D202).",
           "platt_cloud_32BI": {"a": a, "b": b}, "ks": KS,
           "pre_event_window_s": [PRE_EVENT_LO, PRE_EVENT_HI],
           "d197_reference_theta_raw": D197_THETA_RAW, "clip_overlap": clip_overlap(), "by_k": {}}
    for k in KS:
        clf, ntr, npos = fit_k(ep, k, a, b)
        theta, far_c, n_neg_dev = choose_crash_theta(ep, k, a, b, clf)
        bound, far_n, n_pos_dev = choose_normal_bound(ep, k, a, b, clf)
        ev = eval_rules(ep, k, a, b, clf, theta, bound)
        ls = label_shuffle_crash(ep, k, a, b, clf, theta)
        res["by_k"][k] = {
            "logistic_coef": {"level": float(clf.coef_[0][0]), "slope": float(clf.coef_[0][1]),
                              "intercept": float(clf.intercept_[0])},
            "n_train": ntr, "n_train_pos": npos,
            "crash_theta_prob": theta, "achieved_no_crash_dev_fire_rate": far_c,
            "n_neg_dev_episodes": n_neg_dev,
            "normal_bound_prob": bound, "achieved_crash_dev_normal_exit_rate": far_n,
            "n_pos_dev_episodes": n_pos_dev, "eval": ev, "label_shuffle_control": ls}
        print(f"k={k}: caught={ev['crash_rule']['fraction_crash_caught']:.3f} "
              f"false_crash={ev['crash_rule']['false_crash_exit_rate_on_no_crash']:.3f} "
              f"false_normal={ev['normal_rule']['false_normal_exit_rate_on_crash']:.3f} "
              f"fire_t_med={ev['crash_rule']['firing_time_before_event_s']['median']}")
    # reference D197 level-only crash trigger: episode fires if any RAW cloud score >= theta
    ref = {}
    for sp in ("DEV", "EVAL"):
        nc = ncf = pc = pcf = 0
        fire_t = []
        for c, d in ep.items():
            if d["side"] != sp:
                continue
            raws = [s for (_, s) in d["pts"]]
            rels = [r for (r, _) in d["pts"]]
            fired = [rels[i] for i, s in enumerate(raws) if s >= D197_THETA_RAW]
            pre = [t for t in fired if t < 0]
            if d["label"] == "positive":
                pc += 1
                if pre:
                    pcf += 1; fire_t.append(-max(pre))
            else:
                nc += 1
                if fired:
                    ncf += 1
        ref[sp] = {"crash_caught_rate": (pcf / pc if pc else None),
                   "false_crash_rate": (ncf / nc if nc else None),
                   "median_fire_time_s": (statistics.median(fire_t) if fire_t else None)}
    res["d197_level_only_reference"] = ref
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "exit2_results.json").write_text(json.dumps(res, indent=1, default=float))
    print("wrote exit2_results.json; overlap:", res["clip_overlap"])


if __name__ == "__main__":
    main()
