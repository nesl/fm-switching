#!/usr/bin/env python3
"""StudyORACLE D268 (corrected): conditioned FAIR expected-accuracy table (CPU, read-only, no images).

Each served query is credited the expected accuracy for its (task_type, serving_location,
serving_state). serving_state is conditioned on CONTEXT SENT, not cache state: accuracy depends on
what the model received, and a cold rebuild that sends the full history produces the same prompt as
a warm hit. Estimated POOLED ACROSS ARMS from committed data; the identical table is applied to the
oracle and every policy (done in the share driver). This file estimates the table and reports cell
counts per bin + how each served query's state is determined.

Serving-state determination (CONTEXT SENT):
- recall (robot cloud request): WITH_HISTORY iff prompt_tokens >= 2000, else WITHOUT_HISTORY. Field:
  `prompt_tokens` in results/.../runs/<cell>/request.jsonl.gz. The threshold sits in the valley of a
  bimodal distribution: a low mode below ~1500 tokens (a single robot question) and a dominant high
  mode at 8-12k (question + session history); the per-bucket histogram is reported. Correctness:
  `cloud_correct` in cell.json score.robot_rows (gold-graded), joined by opportunity_id. The
  cache-hit split (cached_tokens/prompt_tokens >= 0.8) is reported BESIDE it for reference only.
- single_shot: each question is its own session with one image and NO prior residency (a stateless
  contrast class, fleet/trace.py), so every single-shot cloud answer is WITHOUT_HISTORY. Correctness
  from the SS2 box (episodic_lib.ss2_correctness).
- device (either type): the on-device answer, no serving state. Correctness: device_correct
  (recall) / box device (single-shot).
- dashcam: handled on the committed score_cell model in the dashcam rebuild (DEV per-tier accuracy);
  reported there. Dashcam cloud is with-history by construction (EPG frames accumulate).
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
WARM = 0.8          # cache-hit reference split (cached/prompt), reported for reference only
HIST_TOK = 2000     # CONTEXT-SENT split: prompt_tokens >= HIST_TOK => WITH_HISTORY (bimodal valley)


def req_state(cell):
    """opportunity_id -> (prompt_tokens, cached/prompt) for robot cloud requests of this cell."""
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
                out[r.get("opportunity_id")] = (pt, (r.get("cached_tokens") or 0) / pt)
        break
    return out


def main():
    # recall: pool all arms x seeds x memory; bin cloud-delivered robot answers by CONTEXT SENT
    bins = {("recall", "cloud", "WITH_HISTORY"): [0, 0], ("recall", "cloud", "WITHOUT_HISTORY"): [0, 0],
            ("recall", "device", "NA"): [0, 0]}
    ref_cache = {"WARM": [0, 0], "COLD": [0, 0]}     # cache-hit split, reference only
    ptdist = collections.Counter()                    # prompt_tokens histogram (bimodality evidence)
    BK = [0, 500, 1000, 1500, 2000, 3000, 5000, 8000, 12000, 20000, 40000, 100000]
    ss = E.ss2_correctness()
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
                    if cl is not None:   # cloud delivered -> bin by CONTEXT SENT (prompt_tokens)
                        pt, surv = st.get(oid, (0, 0.0))
                        correct = 1 if r.get("cloud_correct") else 0
                        state = "WITH_HISTORY" if pt >= HIST_TOK else "WITHOUT_HISTORY"
                        b = bins[("recall", "cloud", state)]
                        b[0] += 1; b[1] += correct
                        for i in range(len(BK) - 1):
                            if BK[i] <= pt < BK[i + 1]:
                                ptdist[(BK[i], BK[i + 1])] += 1
                                break
                        rb = ref_cache["WARM" if surv >= WARM else "COLD"]
                        rb[0] += 1; rb[1] += correct
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
    ref = {}
    for k, (n, kk) in ref_cache.items():
        ref["|".join(("recall", "cloud", k))] = {"n": n, "k": kk, "acc": round(kk / n, 6) if n else None}
    phist = {f"[{a},{b})": ptdist[(a, b)] for a, b in zip(BK, BK[1:])}
    out = {"_what": "D268 corrected: conditioned FAIR expected-accuracy table (pooled across arms). "
                    "Each served query credited acc[(type, location, state)]; identical table applied "
                    "to oracle and every policy. serving_state conditioned on CONTEXT SENT: recall "
                    "WITH_HISTORY iff prompt_tokens >= 2000 (bimodal valley; low mode <1500 = single "
                    "question, high mode 8-12k = question+history), single-shot always WITHOUT_HISTORY "
                    "(stateless). dashcam on score_cell model (reported in the rebuild).",
           "context_sent_threshold_prompt_tokens": HIST_TOK, "table": table,
           "prompt_tokens_histogram_robot_cloud": phist,
           "reference_only_cache_hit_split": {"_note": "cached/prompt >= 0.8; for reference, NOT used "
                                              "in FAIR", "warm_threshold_cached_over_prompt": WARM,
                                              "bins": ref},
           "state_field": "prompt_tokens in runs/<cell>/request.jsonl.gz (context sent); correctness "
                          "from cell.json score.robot_rows.cloud_correct / SS2 box"}
    out["_provenance"] = stamp(script="oracle_fair_table.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    (outdir / "oracle_fair_table.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_fair_table.json")
    print("FAIR table (context-sent conditioning):")
    for k, v in table.items():
        print(f"  {k:32s} n={v['n']:6d} k={v['k']:6d} acc={v['acc']}")
    print("reference-only cache-hit split (NOT used in FAIR):")
    for k, v in ref.items():
        print(f"  {k:32s} n={v['n']:6d} k={v['k']:6d} acc={v['acc']}")
    print("prompt_tokens histogram (robot cloud, bimodality):")
    for k, v in phist.items():
        print(f"  {k:16s} {v:6d} {'#' * (v // 1500)}")
    return out


if __name__ == "__main__":
    main()
