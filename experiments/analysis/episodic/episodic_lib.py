#!/usr/bin/env python3
"""D192 shared library: cell selection, committed-score readers, SS2 join, cost.

Offline, read-only, CPU only. Seeds 4 to 7. Full-memory final-workload cells
(<arm>_n16_s<seed>_1200s_h27_3t_L3_epg_rq30), preferring the _rerun directory when it exists and
carries a cell.json. The committed scorer's output is READ from cell.json; nothing is reimplemented.
No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RUNS = os.path.join(REPO, "results/orchestration/live2/frozen_test/runs")
SS2 = os.path.join(REPO, "results/casestudy/study_ss2")
SEEDS = [4, 5, 6, 7]
GPU_S_PER_UNCACHED_TOK = 0.000182431  # D174

# D192 arm list. Each display arm maps to the raw cell-arm for its full-memory final cells.
ARMS = [
    ("base", "hybrid-F-lhreq-noc3"),
    ("rules", "v5-rules-2"),
    ("state-uo", "covex-v6-state-uo"),
    ("state-uo-c5attr", "covex-v6-state-uo-c5attr"),
    ("state-shares", "covex-v6-state-shares"),
    ("state-shares-r1", "covex-v6-state-shares-r1"),
    ("state-shares-r2", "covex-v6-state-shares-r2"),
    ("fair-c5attr", "covex-v6-fair-c5attr"),
    ("fair-c5attr-gain0", "covex-v6-fair-c5attr-gain0"),
    ("edf", "edf"),
    ("llf", "llf"),
    ("b7-edf-feasibility", "b7-edf-feasibility"),
    ("always-cloud-fcfs", "always-cloud-fcfs"),
    ("mooncake", "mooncake"),
    ("attentionstore-prefetch", "attentionstore-prefetch"),
    ("lmcache", "lmcache"),
    ("kvflow-prefetch", "kvflow-prefetch"),
    ("simplestream", "simplestream"),
    ("streamscout", "streamscout"),
    ("querystream-proactive", "querystream-proactive"),
    ("eco-llm", "eco-llm"),
    # confidence-cascade removed: SUPERSEDED under D205 (delivered_scores constant 0.0 reader).
    ("warm-all-lru", "warm-all-lru"),
    ("fair-c5attr-rr", "covex-v6-fair-c5attr-rr"),  # D208: joins rung 3
]


def cell_dir(raw_arm, seed):
    """Full-memory final cell for (raw_arm, seed), preferring a valid _rerun directory.

    Returns (path, used_rerun) or (None, False) if no scorable cell exists.
    """
    base = f"{raw_arm}_n16_s{seed}_1200s_h27_3t_L3_epg_rq30"
    rerun = os.path.join(RUNS, base + "_rerun")
    plain = os.path.join(RUNS, base)
    if os.path.isdir(rerun) and os.path.exists(os.path.join(rerun, "cell.json")):
        return rerun, True
    if os.path.isdir(plain) and os.path.exists(os.path.join(plain, "cell.json")):
        return plain, False
    return None, False


def read_jsonl_gz(path):
    for cand, op in ((path + ".gz", gzip.open), (path, open)):
        if os.path.exists(cand):
            with op(cand, "rt") as fh:
                return [json.loads(l) for l in fh if l.strip()]
    return []


def load_cell(path):
    return json.load(open(os.path.join(path, "cell.json")))


# ---------------------------------------------------------------- Step 3: robot (committed scorer)
def robot_correct_in_time(cell):
    """Committed scorer headline: correct answers delivered by the 3 s deadline (cloud if on time,
    else device), read from cell.json robot_headline. Returns (correct_count, n, fraction)."""
    rh = (((cell.get("score") or {}).get("score") or {}).get("robot_headline") or {})
    acc = rh.get("correct_answers_delivered_by_deadline")
    n = rh.get("n_by_deadline")
    if acc is None or n is None:
        return None, None, None
    return int(round(acc * n)), int(n), acc


# ---------------------------------------------------------------- Step 4: single-shot (SS2 join)
_SS2_CACHE = {}


def ss2_correctness():
    """Per-qid correctness for both tiers across both SS2 datasets.

    Returns dict qid -> {"device": bool, "cloud": bool}. Correctness is the committed SS2 score:
    exact_match for realworldqa (mcq), point_accuracy for refspatial (pointing).
    """
    if _SS2_CACHE:
        return _SS2_CACHE
    corr = {}
    for ds in ("realworldqa", "refspatial"):
        for tier, fn in (("device", f"{ds}_device.json"), ("cloud", f"{ds}_cloud32b.json")):
            d = json.load(open(os.path.join(SS2, fn)))
            for r in d.get("rows") or []:
                sc = r.get("score") or {}
                v = sc.get("exact_match", sc.get("point_accuracy"))
                if v is None:
                    continue
                corr.setdefault(r["qid"], {})[tier] = (float(v) >= 0.5)
    _SS2_CACHE.update(corr)
    return _SS2_CACHE


def refused_ids(reqs):
    """D226 (3): request ids that are refusals, by score.py::refused_request_ids -- http_status
    != 200, or no http_status with no prompt_tokens and no output_tokens. The single canonical
    refusal definition used across canon, dsmap and ss_correct_in_time."""
    out = set()
    for r in reqs or []:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    out.add(r.get("request_id"))
            except (TypeError, ValueError):
                out.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            out.add(r.get("request_id"))
    return out


def refused_and_present(path):
    """(refused_ids, present_ids) for a cell. A cloud answer is a VERIFIED delivery only when its
    request id is present in the request log and not refused (D226 (3)); an absent-row or refused
    request is unverifiable and must fall back to the device answer."""
    reqs = read_jsonl_gz(os.path.join(path, "request.jsonl")) \
        or read_jsonl_gz(os.path.join(path, "requests.jsonl")) or []
    return refused_ids(reqs), {r.get("request_id") for r in reqs}


def ss_correct_in_time(path):
    """Per single-shot opportunity: correct if cloud delivered within 2 s and cloud is correct,
    else device correctness. Returns (correct_count, n, fraction, cloud_ontime_frac, n_missing_qid).
    """
    corr = ss2_correctness()
    outs = read_jsonl_gz(os.path.join(path, "outcomes.jsonl"))
    rows = [o for o in outs if str(o.get("device_id", "")).startswith("asst")]
    n = len(rows)
    if not n:
        return None, 0, None, None, 0
    # D226 (3): a cloud answer counts as on-time only if its request is VERIFIED delivered (present
    # in the request log and not a refusal). An absent-row or refused request is unverifiable, so
    # on-time falls back to the device answer.
    refused, present = refused_and_present(path)
    k = 0
    cloud_on = 0
    missing = 0
    for o in rows:
        qid = o.get("question_id")
        c = corr.get(qid)
        if c is None:
            missing += 1
            continue
        rid = (o.get("cloud_payload") or {}).get("request_id")
        verified = rid is not None and rid in present and rid not in refused
        on_time = (bool((o.get("cloud_payload") or {}).get("on_time"))
                   or bool(o.get("within_L"))) and verified
        if on_time:
            cloud_on += 1
            ok = c.get("cloud")
        else:
            ok = c.get("device")
        if ok:
            k += 1
    denom = n - missing
    return k, denom, (k / denom if denom else None), (cloud_on / n if n else None), missing


# ---------------------------------------------------------------- Step e: cost (uncached tokens)
def cell_cost(path):
    """Total uncached tokens and GPU seconds over the cell's cloud requests.

    uncached = prompt_tokens - cached_tokens per request; cached_tokens ABSENT is recorded, not
    treated as 0 (those requests are excluded from the uncached sum and counted). Returns dict.
    """
    reqs = read_jsonl_gz(os.path.join(path, "request.jsonl"))
    if not reqs:
        reqs = read_jsonl_gz(os.path.join(path, "requests.jsonl"))
    unc = 0
    n_req = 0
    n_cached_absent = 0
    for r in reqs:
        pt = r.get("prompt_tokens")
        ct = r.get("cached_tokens")
        if pt is None:
            continue
        n_req += 1
        if ct is None:
            n_cached_absent += 1
            continue
        unc += max(0, int(pt) - int(ct))
    return {"uncached_tokens": unc, "gpu_s": round(unc * GPU_S_PER_UNCACHED_TOK, 6),
            "n_cloud_requests": n_req, "n_cached_absent": n_cached_absent}
