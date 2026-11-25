#!/usr/bin/env python3
"""Reconnect cost-model replay (1x ONLY; CPU, read-only, no images). A MODEL-BASED SCREEN, NOT A
MEASUREMENT: it predicts first-token time from the D162 model, it does not run the engine.

This is a NETWORK experiment (D240: kept separate from the memory experiments; 1x only). For robot
QUESTION requests in the rung-3 (covex-v6-fair-final) 1x cells, seeds 4 to 7, it places an outage of
D = 60, 120, 300 s at the question's preceding gap and predicts the first question's first-token
under three recovery policies:

  (i)   history kept, catch up at QUESTION time  -> uncached = backlog
  (ii)  history kept, catch up at RECONNECT      -> uncached = 0 (backlog already warm by question)
  (iii) history EVICTED                          -> uncached = full history + backlog

backlog = (D/2) frames * tokens_per_frame, tokens_per_frame measured from consecutive robot prompts
(expected ~90, the D2 law). D162: first_token = 0.0678 + 0.000182*uncached + 0.000154*queued_ahead,
with queued_ahead taken from the cell's measured distribution at robot submits (each question's own
measured in-flight uncached-ahead). P(first token within 3 s) is reported per policy.
"""
from __future__ import annotations
import glob, gzip, json, os, re, statistics, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

RUNG3 = "covex-v6-fair-final"
SEEDS = [4, 5, 6, 7]
OUTAGES = [60.0, 120.0, 300.0]
FRAME_STRIDE_S = 2.0                     # D2 stride; backlog = (D/2) frames per the task
D162 = lambda unc, qa: 0.0678 + 0.000182 * unc + 0.000154 * qa  # noqa: E731
DEADLINE_S = 3.0
STORE = None


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


def cell_dir(seed):
    base = f"{RUNG3}_n16_s{seed}_1200s_h27_3t_L3_epg_rq30"
    for suf in ("_rerun", ""):
        d = RUNS / (base + suf)
        if (d / "request.jsonl.gz").exists() or (d / "request.jsonl").exists():
            return str(d)
    return None


def read_requests(d):
    for cand, op in ((os.path.join(d, "request.jsonl.gz"), gzip.open),
                     (os.path.join(d, "request.jsonl"), open)):
        if os.path.exists(cand):
            with op(cand, "rt") as f:
                return [json.loads(l) for l in f if l.strip()]
    return []


def tokens_per_frame(reqs):
    """Median tok/frame from consecutive robot requests in a session, via mm_uuids length delta."""
    by_sess = {}
    for r in reqs:
        if str(r.get("device_id", "")).startswith("robo"):
            by_sess.setdefault(r.get("session_id"), []).append(r)
    ratios = []
    for rs in by_sess.values():
        rs.sort(key=lambda r: r["t_submit"])
        for i in range(1, len(rs)):
            dpt = (rs[i].get("prompt_tokens") or 0) - (rs[i - 1].get("prompt_tokens") or 0)
            dfr = len(rs[i].get("mm_uuids") or []) - len(rs[i - 1].get("mm_uuids") or [])
            if dfr > 0 and dpt > 0:
                ratios.append(dpt / dfr)
    return statistics.median(ratios) if ratios else 90.0


def queued_ahead_at(reqs, t):
    """Measured uncached tokens of requests in flight at time t (contention)."""
    tot = 0
    for r in reqs:
        if r["t_submit"] <= t < r.get("t_done", r["t_submit"]):
            tot += max(0, (r.get("prompt_tokens") or 0) - (r.get("cached_tokens") or 0))
    return tot


def main():
    per_seed = {}
    pooled_q = []            # all rung3 1x robot questions across seeds (1x only; network expt)
    tpf_by_seed = {}
    for seed in SEEDS:
        d = cell_dir(seed)
        if d is None:
            continue
        agree = source_agreement(d)
        if agree.upper().startswith("INVALID"):
            continue
        reqs = read_requests(d)
        tpf = tokens_per_frame(reqs)
        tpf_by_seed[seed] = round(tpf, 3)
        questions = [r for r in reqs if str(r.get("device_id", "")).startswith("robo")
                     and r.get("opportunity_id") is not None]
        recs = []
        for q in questions:
            hist = q.get("prompt_tokens") or 0
            qa = queued_ahead_at(reqs, q["t_submit"])
            recs.append({"hist": hist, "qa": qa})
        per_seed[seed] = {"agreement": agree, "n_questions": len(recs), "tokens_per_frame": tpf}
        pooled_q.append((seed, tpf, recs))

    def p_within(recs, tpf, D, policy):
        if not recs:
            return None
        backlog = (D / FRAME_STRIDE_S) * tpf
        ok = 0
        for r in recs:
            if policy == "i_hist_kept_catchup_question":
                unc = backlog
            elif policy == "ii_hist_kept_catchup_reconnect":
                unc = 0.0
            else:  # iii_hist_evicted
                unc = r["hist"] + backlog
            if D162(unc, r["qa"]) <= DEADLINE_S:
                ok += 1
        return round(ok / len(recs), 6)

    policies = ["i_hist_kept_catchup_question", "ii_hist_kept_catchup_reconnect", "iii_hist_evicted"]
    results = {"per_seed": {}, "pooled_1x": {}}
    allrecs = [r for _, _, recs in pooled_q for r in recs]
    tpf_pool = statistics.median(list(tpf_by_seed.values())) if tpf_by_seed else 90.0
    for seed, tpf, recs in pooled_q:
        results["per_seed"][seed] = {
            "n_questions": len(recs), "tokens_per_frame": round(tpf, 3),
            "p_within_3s": {f"D{int(D)}": {pol: p_within(recs, tpf, D, pol) for pol in policies}
                            for D in OUTAGES}}
    results["pooled_1x"] = {
        "n_questions": len(allrecs), "tokens_per_frame_median": round(tpf_pool, 3),
        "p_within_3s": {f"D{int(D)}": {pol: p_within(allrecs, tpf_pool, D, pol) for pol in policies}
                        for D in OUTAGES}}

    out = {
        "_what": "Reconnect cost-model replay for rung-3 (covex-v6-fair-final) 1x robot questions. "
                 "MODEL-BASED SCREEN, NOT A MEASUREMENT (D162 prediction, engine not run). "
                 "NETWORK experiment, 1x only (D240: separate from memory experiments).",
        "model": {"d162": "first_token = 0.0678 + 0.000182*uncached + 0.000154*queued_ahead",
                  "deadline_s": DEADLINE_S, "frame_stride_s": FRAME_STRIDE_S,
                  "backlog": "(D/2) frames * tokens_per_frame",
                  "policies": {"i": "history kept, catch up at question time (uncached=backlog)",
                               "ii": "history kept, catch up at reconnect (uncached=0)",
                               "iii": "history evicted (uncached = full history + backlog)"}},
        "tokens_per_frame_by_seed": tpf_by_seed,
        "results": results,
    }
    out["_provenance"] = stamp(script="reconnect_replay.py", model="qwen3vl32b",
                               device="jetson_orin", n=len(allrecs))
    outdir = REPO / "results/orchestration/live2/robot_idle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "reconnect_replay.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "reconnect_replay.json")
    print("tokens/frame by seed:", tpf_by_seed)
    print("pooled 1x n_questions:", len(allrecs))
    for D in OUTAGES:
        pr = results["pooled_1x"]["p_within_3s"][f"D{int(D)}"]
        print(f"  D={int(D)}s P(within3s): (i)={pr['i_hist_kept_catchup_question']} "
              f"(ii)={pr['ii_hist_kept_catchup_reconnect']} (iii)={pr['iii_hist_evicted']}")
    return out


if __name__ == "__main__":
    main()
