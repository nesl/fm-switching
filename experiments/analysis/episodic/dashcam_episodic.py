#!/usr/bin/env python3
"""D192 Steps 1 and 2: episodic dashcam crash detection and early-exit headroom.

Offline, read-only, CPU only. Per task episode (the workload's 21-frame episodes, episode_id from
the committed trace, matching d185's 712), walk decision instants in clip-time order using the
STANDING answer at each instant (cloud if the cloud answer was delivered on time, else device;
D165 B), each tier with its OWN score and its OWN FAR-10 threshold on DEV (StudySH-EP EP-G folds).

Inputs, all committed:
  device score + clip_pts + episode_id   the per-seed joined table
      results/orchestration/live2/frozen_test/traces/<trace>/dashcam_instants.jsonl.gz
  cloud on-time + cloud score             each cell's outcomes.jsonl.gz, joined by opportunity_id
  uncached tokens (cost)                  each cell's request.jsonl.gz, joined by opportunity_id
  FAR-10 thresholds per tier              results/dashcam/study_sh_ep/sh_ep_results.json
                                            h2_earliness EP-G|far10 (device 4BI, cloud 32BI)
  Nexar label + event time per clip       sh_ep_manifest_meta.json / nexar_check.json (ref =
                                            time_of_event; label positive = crash)

Episode labelling (stated, because the task names two categories and the 21-frame partitioning
splits a positive clip into several episodes): a CRASH episode is one whose clip is positive AND
whose clip_pts span contains the labelled event time ref, with at least one instant strictly before
ref; every other episode (negative clip, or a positive clip's pre/post-event segment) is a NO-CRASH
episode. This matches StudySH-EP calibrating FAR on non-event frames. The count of positive-clip
non-event episodes is reported so the choice is visible.

Crossing: a standing score CROSSES when it is at or above its tier's threshold (higher score = more
"yes"). Episode alert = the first instant in clip-time order that crosses.
  Crash episode  CORRECT if the alert is raised at an instant with clip_pts < ref; lead = ref - pts.
  No-crash       CORRECT if no alert is raised; otherwise a false alarm.

No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
import episodic_lib as E  # noqa: E402

TRACE = ("results/orchestration/live2/frozen_test/traces/"
         "seed{seed}_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz")
SH_EP = "results/dashcam/study_sh_ep/sh_ep_results.json"
ALERT_DEADLINE_S = 1.0


def thresholds(condition="EP-G", far="far10"):
    """INSTANT-level FAR-10 thresholds, committed by StudySH-EP on DEV (kept beside, labelled)."""
    d = json.load(open(os.path.join(E.REPO, SH_EP)))
    blk = d["h2_earliness"][f"{condition}|{far}"]["models"]
    return {"level": "instant", "device": blk["4BI"]["threshold"],
            "cloud": blk["32BI"]["threshold"],
            "achieved_far": {"device": blk["4BI"]["achieved_far"],
                             "cloud": blk["32BI"]["achieved_far"]}}


# StudySH-EP DEV EP-G per-instant scores for both tiers (committed). side = DEV / EVAL fold.
DEV_4BI = "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
DEV_32BI = "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
_EP_THR = {}


def _load_dev_episodes(path):
    """DEV EP-G episodes (one per clip) -> {clip: {label, max_score}} over negatives/positives."""
    opener = gzip.open if path.endswith(".gz") else open
    by_clip = {}
    with opener(os.path.join(E.REPO, path), "rt") as fh:
        for l in fh:
            if '"EP-G"' not in l or '"DEV"' not in l:
                continue
            r = json.loads(l)
            if r.get("condition") != "EP-G" or r.get("side") != "DEV" or r.get("score") is None:
                continue
            c = r["file_name"]
            d = by_clip.setdefault(c, {"label": r.get("label"), "max": float(r["score"])})
            d["max"] = max(d["max"], float(r["score"]))
    return by_clip


def thresholds_episode(far=0.10):
    """EPISODE-level thresholds: on StudySH-EP DEV EP-G episodes (never EVAL), the smallest tier
    threshold such that at most 10 percent of NO-CRASH DEV episodes (negative clips; no pre-event
    instant) have ANY instant crossing when that tier alone serves every instant. An episode crosses
    when its maximum instant score is at or above the threshold.
    """
    if _EP_THR:
        return _EP_THR
    import math
    out = {"level": "episode", "far_target": far, "fold": "StudySH-EP DEV (EP-G), never EVAL",
           "per_tier": {}}
    for tier, path in (("device", DEV_4BI), ("cloud", DEV_32BI)):
        dev = _load_dev_episodes(path)
        neg = sorted((v["max"] for v in dev.values() if v["label"] == "negative"), reverse=True)
        n = len(neg)
        k = math.ceil(far * n)
        theta = neg[k - 1] if 0 < k <= n else (neg[-1] if neg else 0.0)
        achieved = sum(1 for m in neg if m >= theta - 1e-12) / n if n else None
        out[tier] = theta
        out["per_tier"][tier] = {"theta": theta, "n_neg_dev_episodes": n, "k_allowed": k,
                                 "achieved_dev_episode_far": achieved,
                                 "n_pos_dev_episodes": sum(1 for v in dev.values()
                                                           if v["label"] == "positive")}
    _EP_THR.update(out)
    return _EP_THR


def nexar_labels():
    """clip -> {ref, label}; ref = time_of_event (clip seconds), label positive = crash."""
    m = {}
    for src in ("results/dashcam/study_sh_ep/sh_ep_manifest_meta.json",
                "results/data_check/nexar_check.json",
                "results/dashcam/study_d2_nexar/pilot_sample.json"):
        p = os.path.join(E.REPO, src)
        if not os.path.exists(p):
            continue
        d = json.load(open(p))

        def walk(o):
            if isinstance(o, dict):
                fn = o.get("file_name") or o.get("clip")
                ref = o.get("ref", o.get("time_of_event"))
                lab = o.get("label")
                if fn and lab is not None and fn not in m:
                    m[fn] = {"ref": ref, "label": lab}
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(d)
    return m


_TRACE_CACHE = {}


def load_trace_instants(seed):
    if seed in _TRACE_CACHE:
        return _TRACE_CACHE[seed]
    p = os.path.join(E.REPO, TRACE.format(seed=seed))
    rows = [json.loads(l) for l in gzip.open(p, "rt")]
    _TRACE_CACHE[seed] = rows
    return rows


def _cell_cloud_and_cost(path):
    """opportunity_id -> (cloud_on_time, cloud_score, gpu_s) for dashcam instants of this cell."""
    cloud = {}
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("dash"):
            continue
        cp = o.get("cloud_payload") or {}
        cloud[o["opportunity_id"]] = {"on_time": bool(cp.get("on_time")),
                                      "cloud_score": cp.get("cloud_score"),
                                      "has_cloud_req": cp.get("request_id") is not None}
    reqs = E.read_jsonl_gz(os.path.join(path, "request.jsonl")) or \
        E.read_jsonl_gz(os.path.join(path, "requests.jsonl"))
    cost = {}
    for r in reqs:
        oid = r.get("opportunity_id")
        pt, ct = r.get("prompt_tokens"), r.get("cached_tokens")
        if oid is None or pt is None:
            continue
        unc = None if ct is None else max(0, int(pt) - int(ct))
        cost[oid] = {"uncached": unc, "gpu_s": (None if unc is None
                                                else unc * E.GPU_S_PER_UNCACHED_TOK)}
    return cloud, cost


def score_cell(path, seed, thr, labels, device_only=False):
    """One cell: per-episode crash-detection outcomes + Step 2 early-exit cost split.

    Returns a dict of aggregates plus per-episode detail is collapsed to counts.
    """
    instants = load_trace_instants(seed)
    cloud, cost = _cell_cloud_and_cost(path)
    eps = defaultdict(list)
    for r in instants:
        eps[r["episode_id"]].append(r)

    n_crash = n_nocrash = 0
    det = 0
    false_alarm = 0
    nocrash_correct = 0
    leads = []
    pos_nonevent = 0
    # Step 2 cost accounting
    gpu_total = 0.0
    gpu_after = 0.0
    req_total = 0
    req_after = 0
    gpu_after_by = {"crash": 0.0, "nocrash": 0.0}
    req_after_by = {"crash": 0, "nocrash": 0}
    gpu_after_cat = {"true_detection": 0.0, "false_alarm": 0.0,
                     "crash_crossing_not_before_event": 0.0}
    req_after_cat = {"true_detection": 0, "false_alarm": 0,
                     "crash_crossing_not_before_event": 0}
    missing_cost = 0

    for eid, rows in eps.items():
        rows = sorted(rows, key=lambda r: float(r["clip_pts"]))
        clip = rows[0]["clip"]
        meta = labels.get(clip) or {}
        ref = meta.get("ref")
        is_pos = (meta.get("label") == "positive")
        pts = [float(r["clip_pts"]) for r in rows]
        # D192 refinement: a CRASH episode CONTAINS a pre-event instant (positive clip, an instant
        # strictly before the event); every other episode is NO-CRASH (negative clips and the
        # post-event segments of positive clips). This matches the no-crash definition used to
        # calibrate the episode-level DEV thresholds.
        has_pre = bool(is_pos and ref is not None and any(p < ref for p in pts))
        is_crash = has_pre
        if is_pos and not is_crash:
            pos_nonevent += 1

        # walk to the first standing crossing
        alert_idx = None
        alert_pts = None
        for i, r in enumerate(rows):
            oid = r["opportunity_id"]
            c = cloud.get(oid) or {}
            if (not device_only) and c.get("on_time"):
                score, t = c.get("cloud_score"), "cloud"
            else:
                score, t = r.get("device_score"), "device"
            if score is not None and float(score) >= thr[t] - 1e-12:
                alert_idx = i
                alert_pts = float(r["clip_pts"])
                break

        detected = bool(is_crash and alert_idx is not None and alert_pts < ref)
        if is_crash:
            n_crash += 1
            if detected:
                det += 1
                leads.append(ref - alert_pts)
                category = "true_detection"
            elif alert_idx is not None:
                category = "crash_crossing_not_before_event"
            else:
                category = "crash_miss"
        else:
            n_nocrash += 1
            if alert_idx is None:
                nocrash_correct += 1
                category = "nocrash_clean"
            else:
                false_alarm += 1
                category = "false_alarm"

        # Step 2: cost of cloud work in this episode, and the part AFTER the first crossing
        for i, r in enumerate(rows):
            oid = r["opportunity_id"]
            cc = cloud.get(oid) or {}
            if not cc.get("has_cloud_req"):
                continue
            g = (cost.get(oid) or {}).get("gpu_s")
            if g is None:
                missing_cost += 1
                continue
            req_total += 1
            gpu_total += g
            if alert_idx is not None and i > alert_idx:
                req_after += 1
                gpu_after += g
                key = "crash" if is_crash else "nocrash"
                gpu_after_by[key] += g
                req_after_by[key] += 1
                if category in gpu_after_cat:
                    gpu_after_cat[category] += g
                    req_after_cat[category] += 1

    n_eps = n_crash + n_nocrash
    return {
        "n_episodes": n_eps, "n_crash": n_crash, "n_nocrash": n_nocrash,
        "positive_clip_nonevent_episodes_as_nocrash": pos_nonevent,
        "detection_rate": (det / n_crash if n_crash else None),
        "n_detected": det,
        "false_alarm_rate": (false_alarm / n_nocrash if n_nocrash else None),
        "n_false_alarm": false_alarm,
        "fraction_episodes_correct": ((det + nocrash_correct) / n_eps if n_eps else None),
        "median_lead_s": (round(statistics.median(leads), 4) if leads else None),
        "n_leads": len(leads),
        # cost (Step 1 per-episode means + Step 2 headroom)
        "cloud_requests_total": req_total,
        "gpu_s_total": round(gpu_total, 4),
        "cloud_requests_per_episode": (round(req_total / n_eps, 4) if n_eps else None),
        "gpu_s_per_episode": (round(gpu_total / n_eps, 6) if n_eps else None),
        "step2_gpu_s_after_crossing": round(gpu_after, 4),
        "step2_gpu_fraction_after_crossing": (round(gpu_after / gpu_total, 4) if gpu_total else None),
        "step2_requests_after_crossing": req_after,
        "step2_gpu_after_crash": round(gpu_after_by["crash"], 4),
        "step2_gpu_after_nocrash": round(gpu_after_by["nocrash"], 4),
        "step2_requests_after_crash": req_after_by["crash"],
        "step2_requests_after_nocrash": req_after_by["nocrash"],
        "step2_gpu_after_true_detection": round(gpu_after_cat["true_detection"], 4),
        "step2_gpu_after_false_alarm": round(gpu_after_cat["false_alarm"], 4),
        "step2_gpu_after_crash_crossing_not_before_event":
            round(gpu_after_cat["crash_crossing_not_before_event"], 4),
        "step2_requests_after_true_detection": req_after_cat["true_detection"],
        "step2_requests_after_false_alarm": req_after_cat["false_alarm"],
        "threshold_level": thr.get("level", "unknown"),
        "missing_cost_instants": missing_cost,
    }


if __name__ == "__main__":
    labels = nexar_labels()
    thr_e = thresholds_episode()
    thr_i = thresholds()
    print("episode-level thresholds:", json.dumps(thr_e["per_tier"], indent=1))
    print("instant-level thresholds:", {"device": thr_i["device"], "cloud": thr_i["cloud"]})
    p, rr = E.cell_dir("hybrid-F-lhreq-noc3", 4)
    for lab, thr in (("EPISODE-level", thr_e), ("instant-level", thr_i)):
        r = score_cell(p, 4, thr, labels)
        print(f"\nbase s4 ({lab}):", json.dumps({k: r[k] for k in
              ("n_crash", "n_nocrash", "detection_rate", "false_alarm_rate",
               "fraction_episodes_correct", "median_lead_s",
               "step2_gpu_after_true_detection", "step2_gpu_after_false_alarm")}, indent=1))
