#!/usr/bin/env python3
"""StudyORACLE D268: conditioned FAIR expected-accuracy table (CPU, read-only, no images).

Each served query is credited the expected accuracy for its (task_type, serving_location,
serving_state). serving_state = WARM_WITH_HISTORY vs COLD_OR_WITHOUT. Estimated POOLED ACROSS ARMS
from committed data; the identical table is applied to the oracle and every policy (done in the
share driver). This file estimates the table and reports cell counts per bin + how each served
query's state is determined.

Serving-state determination:
- recall (robot cloud request): WARM_WITH_HISTORY iff cached_tokens / prompt_tokens >= 0.8, else
  COLD_OR_WITHOUT (survival < 0.8). Field: `cached_tokens`, `prompt_tokens` in
  results/.../runs/<cell>/request.jsonl.gz. Correctness: `cloud_correct` in cell.json
  score.robot_rows (gold-graded), joined by opportunity_id.
- single_shot: each question is its own session with one image and NO prior residency (a stateless
  contrast class, fleet/trace.py), so every single-shot cloud answer is COLD_OR_WITHOUT. Correctness
  from the SS2 box (episodic_lib.ss2_correctness).
- device (either type): the on-device answer, no serving state. Correctness: device_correct
  (recall) / box device (single-shot).
- dashcam: handled on the committed score_cell model in the dashcam rebuild (DEV per-tier accuracy);
  reported there. Dashcam cloud is warm-with-history by construction (EPG frames accumulate).
"""
from __future__ import annotations
import json, os, sys, glob, gzip, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
for p in ("experiments/analysis/canon", "experiments/analysis/episodic", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import episodic_lib as E  # noqa: E402
from _provenance import stamp  # noqa: E402
SEEDS = [4, 5, 6, 7]
WARM = 0.8


def req_state(cell):
    """opportunity_id -> survival (cached/prompt) for robot cloud requests of this cell."""
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
                if not str(r.get("device_id", "")).startswith("robo"):
                    continue
                pt = r.get("prompt_tokens")
                if not pt:
                    continue
                out[r.get("opportunity_id")] = (r.get("cached_tokens") or 0) / pt
        break
    return out


def main():
    # recall: pool all arms x seeds x memory; bin cloud-delivered robot answers by state
    bins = {("recall", "cloud", "WARM"): [0, 0], ("recall", "cloud", "COLD"): [0, 0],
            ("recall", "device", "NA"): [0, 0]}
    ss = E.ss2_correctness()
    seen_recall = {}        # (seed,tag,oid) de-dup device floor across arms (device is arm-indep)
    for tag in ("", "_kv0.5r"):
        for s in SEEDS:
            pat = str(RUNS / f"*_n16_s{s}_1200s_h27_3t{tag}_L3_epg_rq30")
            for cell in sorted(glob.glob(pat) + glob.glob(pat + "_rerun")):
                cj = os.path.join(cell, "cell.json")
                if not os.path.exists(cj):
                    continue
                try:
                    rows = (((json.load(open(cj)).get("score") or {}).get("score") or {}).get("robot_rows")) or []
                except Exception:
                    continue
                st = req_state(cell)
                for r in rows:
                    if not str(r.get("device_id", "")).startswith("robo"):
                        continue
                    oid = r.get("opportunity_id")
                    cl = r.get("cloud_letter")
                    if cl is not None:   # cloud delivered -> bin by serving state
                        surv = st.get(oid, 0.0)
                        state = "WARM" if surv >= WARM else "COLD"
                        b = bins[("recall", "cloud", state)]
                        b[0] += 1; b[1] += 1 if r.get("cloud_correct") else 0
    # recall device acc: pooled over all robot questions (device is arm-independent); use union
    dev_n = dev_k = 0
    for tag in ("", "_kv0.5r"):
        for s in SEEDS:
            seen = set()
            pat = str(RUNS / f"*_n16_s{s}_1200s_h27_3t{tag}_L3_epg_rq30")
            for cell in sorted(glob.glob(pat) + glob.glob(pat + "_rerun")):
                cj = os.path.join(cell, "cell.json")
                if not os.path.exists(cj):
                    continue
                try:
                    rows = (((json.load(open(cj)).get("score") or {}).get("score") or {}).get("robot_rows")) or []
                except Exception:
                    continue
                for r in rows:
                    if not str(r.get("device_id", "")).startswith("robo"):
                        continue
                    oid = r.get("opportunity_id")
                    if (s, tag, oid) in seen:
                        continue
                    seen.add((s, tag, oid))
                    dev_n += 1; dev_k += 1 if r.get("device_correct") else 0
    bins[("recall", "device", "NA")] = [dev_n, dev_k]
    # single-shot: cloud (COLD, stateless) and device, from the box
    ss_dev = [v["device"] for v in ss.values() if "device" in v]
    ss_cld = [v["cloud"] for v in ss.values() if "cloud" in v]
    table = {}
    for k, (n, kk) in bins.items():
        table["|".join(k)] = {"n": n, "k": kk, "acc": round(kk / n, 6) if n else None}
    table["single_shot|cloud|COLD"] = {"n": len(ss_cld), "k": int(sum(ss_cld)),
                                        "acc": round(sum(ss_cld) / len(ss_cld), 6)}
    table["single_shot|device|NA"] = {"n": len(ss_dev), "k": int(sum(ss_dev)),
                                       "acc": round(sum(ss_dev) / len(ss_dev), 6)}
    out = {"_what": "D268 conditioned FAIR expected-accuracy table (pooled across arms). Each served "
                    "query credited acc[(type, location, state)]; identical table applied to oracle "
                    "and every policy. serving_state WARM_WITH_HISTORY iff cached_tokens/prompt_tokens"
                    " >= 0.8 (recall), single-shot always COLD (stateless). dashcam on score_cell "
                    "model (reported in the rebuild).",
           "warm_threshold_cached_over_prompt": WARM, "table": table,
           "state_field": "cached_tokens / prompt_tokens in runs/<cell>/request.jsonl.gz; "
                          "correctness from cell.json score.robot_rows.cloud_correct / SS2 box"}
    out["_provenance"] = stamp(script="oracle_fair_table.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    (outdir / "oracle_fair_table.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_fair_table.json")
    for k, v in table.items():
        print(f"  {k:30s} n={v['n']:6d} k={v['k']:6d} acc={v['acc']}")
    return out


if __name__ == "__main__":
    main()
