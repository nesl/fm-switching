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
    d = json.load(open(os.path.join(E.REPO, SH_EP)))
    blk = d["h2_earliness"][f"{condition}|{far}"]["models"]
    return {"device": blk["4BI"]["threshold"], "cloud": blk["32BI"]["threshold"],
            "achieved_far": {"device": blk["4BI"]["achieved_far"],
                             "cloud": blk["32BI"]["achieved_far"]}}


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
    missing_cost = 0

    for eid, rows in eps.items():
        rows = sorted(rows, key=lambda r: float(r["clip_pts"]))
        clip = rows[0]["clip"]
        meta = labels.get(clip) or {}
        ref = meta.get("ref")
        is_pos = (meta.get("label") == "positive")
        pts = [float(r["clip_pts"]) for r in rows]
        is_crash = bool(is_pos and ref is not None and pts[0] - 1e-9 <= ref <= pts[-1] + 1e-9
                        and pts[0] < ref)
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

        if is_crash:
            n_crash += 1
            if alert_idx is not None and alert_pts < ref:
                det += 1
                leads.append(ref - alert_pts)
        else:
            n_nocrash += 1
            if alert_idx is None:
                nocrash_correct += 1
            else:
                false_alarm += 1

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
        "missing_cost_instants": missing_cost,
    }


if __name__ == "__main__":
    thr = thresholds()
    labels = nexar_labels()
    print("thresholds:", thr)
    # smoke test on base seed 4
    p, rr = E.cell_dir("hybrid-F-lhreq-noc3", 4)
    r = score_cell(p, 4, thr, labels)
    print("base s4:", json.dumps({k: r[k] for k in
          ("n_crash", "n_nocrash", "positive_clip_nonevent_episodes_as_nocrash",
           "detection_rate", "false_alarm_rate", "fraction_episodes_correct",
           "median_lead_s", "gpu_s_per_episode", "step2_gpu_fraction_after_crossing")}, indent=1))
