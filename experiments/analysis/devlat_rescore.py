#!/usr/bin/env python3
"""D258 part 2: device-latency rescore (CPU, read-only, no images).

Rescore committed cells with the MEASURED per-item Orin device latency charged to each type's
deadline, in place of the committed scoring (which charged single-shot latency but left recall
device-late uncomputed). The committed scorer is NOT changed; this re-derives from the committed
cell.json + request logs (the Orin host has no traces; a rescore is a re-derivation, not a score.py
rerun).

Measured latency per item:
- recall (deadline L_rob = 3 s, COMPLETION): device_recall_latency_s(history_tokens), history_tokens
  = the robot request's prompt_tokens (request.jsonl). Source: fleet/data_sources.py:732.
- single_shot (deadline 2 s, COMPLETION): single_shot_total_s[question_id] from
  results/device/study_devlat/orin_device_latency_tables.json (question_id is already keyed
  'realworldqa/NNNN' / 'refspatial/...').
- dashcam (deadline L_dash = 1 s, FIRST TOKEN): EP-G append ttft, max 0.3169 s over 1-21 frames, so
  every EP-G dashcam device answer is on time; device-late is 0 by bound (the committed cells are all
  _epg_). The measured append table is carried for completeness.

For each type the device answer is on time iff its measured latency <= deadline. The standing answer
by deadline = cloud if the cloud was delivered on time (committed source_by_deadline=='cloud'), else
device if the (rescored) device is on time, else no answer. device-late = rows where the device is
the chosen standing source and its measured latency exceeds the deadline.
"""
from __future__ import annotations
import json, os, sys, glob, gzip
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/orchestration/live2/fleet"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import data_sources as DS  # noqa: E402
from _provenance import stamp  # noqa: E402

LAT = json.load(open(REPO / "results/device/study_devlat/orin_device_latency_tables.json"))
SS_LAT = LAT["single_shot_total_s"]
DASH_APPEND_MAX = max(LAT["dashcam_append_ttft_s"].values())   # 0.3169 s
L_ROB, L_SS, L_DASH = 3.0, 2.0, 1.0


def req_prompt_tokens(cell):
    out = {}
    for nm, op in (("request.jsonl.gz", gzip.open), ("request.jsonl", open)):
        p = os.path.join(cell, nm)
        if not os.path.exists(p):
            continue
        with op(p, "rt") as f:
            for l in f:
                try:
                    r = json.loads(l)
                except Exception:
                    continue
                if str(r.get("device_id", "")).startswith("robo") and r.get("prompt_tokens"):
                    out[r.get("opportunity_id")] = r["prompt_tokens"]
        break
    return out


def rescore_recall(cell, rows):
    """committed vs rescored: n, cbd, cloud_correct, device_standing, device_correct, device_late."""
    pt = req_prompt_tokens(cell)
    rob = [r for r in rows if str(r.get("device_id", "")).startswith("robo")]
    n = len(rob)
    # committed
    c_cbd = sum(1 for r in rob if r.get("standing_correct_by_deadline"))
    c_dev_standing = sum(1 for r in rob if r.get("source_by_deadline") == "device")
    c_cloud_correct = sum(1 for r in rob if r.get("source_by_deadline") == "cloud" and r.get("cloud_correct"))
    dev_correct = sum(1 for r in rob if r.get("device_correct"))
    # rescored: device on time iff device_recall_latency_s(history) <= L_rob
    r_cbd = r_dev_standing = r_dev_late = 0
    for r in rob:
        lat = DS.device_recall_latency_s(pt.get(r.get("opportunity_id"), 0.0))
        dev_on_time = lat <= L_ROB + 1e-9
        src = r.get("source_by_deadline")
        if src == "cloud":                        # cloud covers; device lateness irrelevant
            r_cbd += 1 if r.get("standing_correct_by_deadline") else 0
        elif src == "device":
            if dev_on_time:
                r_dev_standing += 1
                r_cbd += 1 if r.get("device_correct") else 0
            else:
                r_dev_late += 1                   # device misses deadline -> no answer by deadline
        # src none/other -> no answer either way
    return {"n": n, "committed": {"cbd": c_cbd, "cloud_correct": c_cloud_correct,
                                  "device_standing": c_dev_standing, "device_correct": dev_correct,
                                  "device_late": None},
            "rescored": {"cbd": r_cbd, "cloud_correct": c_cloud_correct,
                         "device_standing": r_dev_standing, "device_correct": dev_correct,
                         "device_late": r_dev_late},
            "max_recall_latency_s": round(max((DS.device_recall_latency_s(v) for v in pt.values()),
                                              default=0.0), 4)}


def rescore_ss(rows):
    ar = [r for r in rows if r.get("metric") in ("exact_match", "single_shot") or "/" in str(r.get("question_id", ""))]
    n = len(ar)
    c_dev_standing = sum(1 for r in ar if r.get("source_by_deadline") == "device")
    c_dev_late = sum(1 for r in ar if r.get("source_by_deadline") == "device"
                     and r.get("device_within_deadline") is False)
    r_dev_standing = r_dev_late = 0
    for r in ar:
        lat = SS_LAT.get(r.get("question_id"), r.get("device_latency_s") or 0.0)
        on_time = lat <= L_SS + 1e-9
        if r.get("source_by_deadline") == "device":
            if on_time:
                r_dev_standing += 1
            else:
                r_dev_late += 1
    return {"n": n, "committed": {"device_standing": c_dev_standing, "device_late": c_dev_late},
            "rescored": {"device_standing": r_dev_standing, "device_late": r_dev_late},
            "n_questions_over_2s": sum(1 for r in ar if SS_LAT.get(r.get("question_id"), 0) > L_SS)}


def main():
    d250 = [("confidence-cascade", "_kv0.5r_h0.5", ""), ("covex-v6-base", "_kv0.5r_h0.5", ""),
            ("covex-v6-fair-final", "_kv0.5r_h0.5", "_preD249")]
    out = {"_what": "D258 part 2 device-latency rescore: measured per-item Orin latency charged to "
                    "each deadline (recall device_recall_latency_s 0.146-0.225s vs L=3s; single_shot "
                    "single_shot_total_s vs L=2s; dashcam EP-G append ttft max %.4fs vs L=1s). "
                    "Re-derived from committed cell.json + request.jsonl; committed scorer unchanged."
                    % DASH_APPEND_MAX,
           "deadlines_s": {"recall": L_ROB, "single_shot": L_SS, "dashcam": L_DASH},
           "dashcam_epg_append_max_ttft_s": round(DASH_APPEND_MAX, 4),
           "cells": {}}
    # D250 block first, then the 1x / kv0.5r s4-s7 grid
    targets = []
    for arm, tag, suf in d250:
        targets.append((f"{arm}_n16_s4_1200s_h27_3t{tag}_L3_epg_rq30{suf}", f"D250/{arm}{tag}"))
    for tag in ("", "_kv0.5r"):
        for s in (4, 5, 6, 7):
            for cell in sorted(glob.glob(str(RUNS / f"*_n16_s{s}_1200s_h27_3t{tag}_L3_epg_rq30"))):
                targets.append((os.path.basename(cell), f"grid/{'1x' if tag=='' else 'kv0.5r'}/s{s}"))
    for base, group in targets:
        path = RUNS / base
        if not (path / "cell.json").exists():
            continue
        try:
            sc = ((json.load(open(path / "cell.json")).get("score") or {}).get("score") or {})
        except Exception:
            continue
        rr = sc.get("robot_rows") or []
        ar = sc.get("assistive_rows") or []
        out["cells"][base] = {"group": group, "recall": rescore_recall(str(path), rr),
                              "single_shot": rescore_ss(ar)}
    out["_provenance"] = stamp(script="devlat_rescore.py", model="qwen3vl4b", device="jetson_orin")
    od = REPO / "results/device/study_devlat"
    (od / "devlat_rescore.json").write_text(json.dumps(out, indent=1, default=float))
    # summary print
    tot_rec_late = sum(c["recall"]["rescored"]["device_late"] for c in out["cells"].values())
    cbd_changed = [b for b, c in out["cells"].items()
                   if c["recall"]["committed"]["cbd"] != c["recall"]["rescored"]["cbd"]]
    print(f"wrote devlat_rescore.json | cells={len(out['cells'])} "
          f"total recall device-late={tot_rec_late} recall-cbd-changed-cells={len(cbd_changed)}")
    mx = max(c["recall"]["max_recall_latency_s"] for c in out["cells"].values())
    print(f"max recall latency across cells={mx}s (deadline {L_ROB}s); dashcam append max "
          f"{DASH_APPEND_MAX:.4f}s (deadline {L_DASH}s)")
    return out


if __name__ == "__main__":
    main()
