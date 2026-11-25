#!/usr/bin/env python3
"""StudyROBOT-IDLE-SURVIVAL (official; CPU only, read-only on cells, NO images).

Does a robot history survive idle time on the cloud KV cache? For every VALID L3_epg_rq30 cell at
1x and at kv0.5r (seeds 4 to 7), each robot request whose PREVIOUS request in the same session had
at least 2000 prompt tokens is classified by how much of its history was still cached:

    gap      = t_submit - previous_request.t_done                (idle seconds)
    survival = cached_tokens / min(previous prompt_tokens, this prompt_tokens)
    COLD     survival < 0.2 ;  WARM survival >= 0.8

Reported per ARM and per MEMORY LEVEL, 1x and kv0.5r kept strictly separate and never pooled
(D240). Per gap bucket: n, P(cold), P(warm), median previous prompt tokens, and median first-token
time (t_first_token - t_submit) for cold and for warm. Robot QUESTION requests (opportunity_id not
null) are reported separately: P(cold) and P(first token within 3 s).

INVALID cells (header source_agreement.verdict starts with INVALID) are never used; cells with no
source_agreement key are marked "agreement ABSENT" and kept. A _rerun cell supersedes its plain.
"""
from __future__ import annotations
import glob, gzip, json, os, re, statistics, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

CELL_RE = re.compile(
    r"^(?P<arm>.+)_n16_s(?P<seed>[4-7])_1200s_h27_3t(?P<kv>_kv0\.5r)?_L3_epg_rq30(?P<rerun>_rerun)?$")
PREV_MIN_TOKENS = 2000
COLD, WARM = 0.2, 0.8
BUCKETS = [(0, 1), (1, 3), (3, 10), (10, 30), (30, 60), (60, 120), (120, 1e18)]
BUCKET_LABELS = ["0-1", "1-3", "3-10", "10-30", "30-60", "60-120", "120+"]
ROB_DEADLINE_S = 3.0


def source_agreement(d):
    hp = os.path.join(d, "header.json")
    if not os.path.exists(hp):
        return "ABSENT"
    try:
        sa = json.load(open(hp)).get("source_agreement")
    except Exception:
        return "ABSENT"
    if sa is None:
        return "ABSENT"
    if isinstance(sa, dict):
        v = sa.get("verdict")
        return v if (isinstance(v, str) and v) else "ABSENT"
    return sa if isinstance(sa, str) else str(sa)


def valid_cells():
    """(arm, seed, mem) -> {dir, agreement, is_rerun, supersedes}; prefer scorable _rerun, drop
    INVALID. Only cells with a request log are kept."""
    groups = {}
    for d in sorted(set(glob.glob(str(RUNS / "*_rq30")) + glob.glob(str(RUNS / "*_rq30_rerun")))):
        name = os.path.basename(d)
        m = CELL_RE.match(name)
        if not m:
            continue
        agree = source_agreement(d)
        has_req = (os.path.exists(os.path.join(d, "request.jsonl.gz"))
                   or os.path.exists(os.path.join(d, "request.jsonl")))
        groups.setdefault((m["arm"], int(m["seed"]), "kv0.5r" if m["kv"] else "1x"), []).append(
            {"dir": d, "name": name, "agreement": agree,
             "invalid": agree.upper().startswith("INVALID"),
             "is_rerun": bool(m["rerun"]), "has_req": has_req})
    out = {}
    for key, cands in groups.items():
        elig = [c for c in cands if not c["invalid"] and c["has_req"]]
        if not elig:
            continue
        win = sorted(elig, key=lambda c: c["is_rerun"], reverse=True)[0]
        others = [c for c in cands if c["name"] != win["name"]]
        out[key] = {"dir": win["dir"], "agreement": win["agreement"], "is_rerun": win["is_rerun"],
                    "supersedes": others[0]["name"] if (win["is_rerun"] and others) else ""}
    return out


def read_requests(d):
    for cand, op in ((os.path.join(d, "request.jsonl.gz"), gzip.open),
                     (os.path.join(d, "request.jsonl"), open)):
        if os.path.exists(cand):
            with op(cand, "rt") as f:
                return [json.loads(l) for l in f if l.strip()]
    return []


def bucket_of(gap):
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= gap < hi:
            return i
    return None


def analyse_cell(d):
    """Return list of robot-request records (gap, survival, cold, warm, ttft, prev_tokens, is_q)."""
    reqs = read_requests(d)
    by_sess = {}
    for r in reqs:
        by_sess.setdefault(r.get("session_id"), []).append(r)
    recs = []
    for sid, rs in by_sess.items():
        rs.sort(key=lambda r: r["t_submit"])
        for i in range(1, len(rs)):
            r, prev = rs[i], rs[i - 1]
            if not str(r.get("device_id", "")).startswith("robo"):
                continue
            ppt = prev.get("prompt_tokens")
            if ppt is None or ppt < PREV_MIN_TOKENS:
                continue
            ppt_cur = r.get("prompt_tokens")
            if not ppt_cur:
                continue
            denom = min(ppt, ppt_cur)
            if denom <= 0:
                continue
            surv = (r.get("cached_tokens") or 0) / denom
            gap = r["t_submit"] - prev["t_done"]
            if gap < 0:
                gap = 0.0
            ttft = (r.get("t_first_token") or r.get("t_done")) - r["t_submit"]
            recs.append({"gap": gap, "survival": surv, "cold": surv < COLD, "warm": surv >= WARM,
                         "ttft": ttft, "prev_tokens": ppt,
                         "is_question": r.get("opportunity_id") is not None})
    return recs


def med(xs):
    return round(statistics.median(xs), 6) if xs else None


def summarise(recs):
    """Per gap bucket: n, P(cold), P(warm), median prev tokens, median ttft cold / warm."""
    out = {}
    for i, lab in enumerate(BUCKET_LABELS):
        b = [r for r in recs if bucket_of(r["gap"]) == i]
        n = len(b)
        cold = [r for r in b if r["cold"]]
        warm = [r for r in b if r["warm"]]
        out[lab] = {
            "n": n,
            "p_cold": round(len(cold) / n, 6) if n else None,
            "p_warm": round(len(warm) / n, 6) if n else None,
            "median_prev_tokens": med([r["prev_tokens"] for r in b]),
            "median_ttft_cold_s": med([r["ttft"] for r in cold]),
            "median_ttft_warm_s": med([r["ttft"] for r in warm]),
        }
    return out


def question_summary(recs):
    q = [r for r in recs if r["is_question"]]
    n = len(q)
    return {
        "n": n,
        "p_cold": round(sum(1 for r in q if r["cold"]) / n, 6) if n else None,
        "p_first_token_within_3s": round(sum(1 for r in q if r["ttft"] <= ROB_DEADLINE_S) / n, 6)
        if n else None,
    }


def main():
    cells = valid_cells()
    # aggregate per (arm, mem) pooling the arm's own seeds 4-7 (seeds pool within a memory level;
    # the two MEMORY levels never pool, D240).
    per_arm_mem = {}
    cell_index = []
    for (arm, seed, mem), info in sorted(cells.items()):
        recs = analyse_cell(info["dir"])
        per_arm_mem.setdefault((arm, mem), []).extend(recs)
        cell_index.append({"arm": arm, "seed": seed, "memory": mem,
                           "agreement": info["agreement"], "is_rerun": info["is_rerun"],
                           "supersedes": info["supersedes"], "n_robot_reqs": len(recs)})
    result = {"1x": {}, "kv0.5r": {}}
    for (arm, mem), recs in sorted(per_arm_mem.items()):
        result[mem][arm] = {
            "n_total": len(recs),
            "by_gap_bucket": summarise(recs),
            "questions_only": question_summary(recs),
        }
    out = {
        "_what": "StudyROBOT-IDLE-SURVIVAL: robot history KV survival vs idle gap, per arm and "
                 "memory level (D240: 1x and kv0.5r reported separately, never pooled).",
        "definitions": {
            "prev_min_prompt_tokens": PREV_MIN_TOKENS, "cold_below": COLD, "warm_at_or_above": WARM,
            "survival": "cached_tokens / min(prev prompt_tokens, this prompt_tokens)",
            "gap_s": "t_submit - previous_request.t_done (same session_id)",
            "first_token_s": "t_first_token - t_submit", "robot_deadline_s": ROB_DEADLINE_S,
            "buckets_s": BUCKET_LABELS},
        "cells_used": cell_index,
        "results": result,
    }
    out["_provenance"] = stamp(script="robot_idle_survival.py", model="qwen3vl32b",
                               device="jetson_orin", n=sum(len(v) for v in per_arm_mem.values()))
    outdir = REPO / "results/orchestration/live2/robot_idle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "robot_idle_survival.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "robot_idle_survival.json")
    print("cells used:", len(cell_index),
          "| 1x arms:", len(result["1x"]), "| kv0.5r arms:", len(result["kv0.5r"]))
    return out


if __name__ == "__main__":
    main()
