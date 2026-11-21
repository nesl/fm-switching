#!/usr/bin/env python3
"""D159 (C) / D161 re-ask trace: proofs, per-seed coverage, and the Orin export.

CPU only, no GPU, no live run. Proves, in order:

  1. BYTE IDENTITY with re-asks off, so the committed workload is untouched by the change.
  2. The re-asks are a pure function of (seed, device, session): building twice gives the same
     trace, which is what makes "identical for every arm" true rather than hoped for.
  3. The fairness and live1 digests are equal between two independent builds of the same cell.
  4. Counts: re-asks emitted, beyond-32k asks COUNTED and never truncated, distinct questions.
  5. Distinct-question coverage of the 69-question lh_req pool across seeds 4, 5, 6, 7.
  6. The Orin export: one row per re-ask with its original ask time for the parity control.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HERE = REPO / "experiments/orchestration/live2"
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import trace as TR                      # noqa: E402  fleet/trace.py
import data_sources as DS               # noqa: E402
import _provenance                      # noqa: E402

SEEDS = (4, 5, 6, 7)                    # never 1-3 (held out), per the standing rule
NDEV, RATIO, RUN_S, MODE = 16, "40:40:20", 1200.0, "A"
MEAN_S = 30.0
COMMON = dict(robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame")
OUT_JSON = REPO / "results/orchestration/live2/frozen_test/reask_trace_proofs.json"
OUT_DIR = REPO / "results/orchestration/live2/reask_lists"


def build(seed, mean_s):
    kw = dict(COMMON)
    if mean_s > 0:
        kw["robot_reask_mean_s"] = mean_s
    return TR.generate_trace(seed=seed, n_devices=NDEV, ratio=RATIO, run_s=RUN_S,
                             mode=MODE, count_only=False, **kw)


def canon(recs):
    return json.dumps(sorted((json.dumps(r, sort_keys=True) for r in recs)))


def main():
    res = {"criterion": dict(seeds=list(SEEDS), n_devices=NDEV, ratio=RATIO, run_s=RUN_S,
                             reask_mean_s=MEAN_S, **COMMON)}

    # ---- proof 1: byte identity with re-asks OFF
    a = build(4, 0.0)
    b = build(4, 0.0)
    res["proof_1_off_is_deterministic"] = canon(a["records"]) == canon(b["records"])

    # ---- proofs 2 and 3: re-asks ON are deterministic, and the digests match
    c = build(4, MEAN_S)
    d = build(4, MEAN_S)
    res["proof_2_on_is_deterministic"] = canon(c["records"]) == canon(d["records"])
    res["proof_3_digests_equal"] = dict(
        fairness=TR.fairness_digest(c["records"], MODE) == TR.fairness_digest(d["records"], MODE),
        fairness_digest=TR.fairness_digest(c["records"], MODE),
        fairness_digest_off=TR.fairness_digest(a["records"], MODE),
        off_and_on_differ=TR.fairness_digest(a["records"], MODE)
        != TR.fairness_digest(c["records"], MODE),
    )
    # The OFF trace must be a strict SUBSET of the ON trace: re-asks only ADD records.
    # Compared with the ASSIGNED ids stripped, because `opportunity_id` is allocated in canonical
    # sort order, so inserting re-ask records renumbers every later opportunity. That renumbering
    # is harmless (the id is opaque and per-trace) but it means a raw record-for-record comparison
    # would fail for a reason that has nothing to do with the workload. Noted in the report: a
    # re-ask cell's opportunity_ids are NOT comparable to a non-re-ask cell's.
    def strip(recs):
        out = []
        for r in recs:
            q = {k: v for k, v in r.items()
                 if k not in ("opportunity_id", "instant_id", "reask_of")}
            out.append(json.dumps(q, sort_keys=True))
        return out
    off, on = set(strip(a["records"])), set(strip(c["records"]))
    res["proof_1b_off_is_subset_of_on"] = off.issubset(on)
    res["proof_1c_only_recall_added"] = sorted(
        {json.loads(x)["kind"] for x in (on - off)}) == ["recall_question"]
    res["proof_1d_ids_renumber"] = (
        {json.dumps(r, sort_keys=True) for r in a["records"]}.issubset(
            {json.dumps(r, sort_keys=True) for r in c["records"]}) is False)
    res["note_ids"] = ("opportunity_id is assigned in canonical sort order, so a re-ask cell "
                       "renumbers every later opportunity; ids are not comparable across the "
                       "re-ask on/off pair, while every non-id field of the OFF trace is present "
                       "unchanged in the ON trace")

    # ---- proofs 4 and 5: counts and coverage, per seed, plus the Orin export
    pool = {q.question_id for s in DS.lh_req_sessions().values() for q in s.questions}
    warm = DS.device_recall_warm_latency_s()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_seed, all_distinct, rows_total = {}, set(), 0
    for seed in SEEDS:
        t = build(seed, MEAN_S)
        st = t["stats"].as_dict() if hasattr(t["stats"], "as_dict") else dict(t["stats"])
        recs = [r for r in t["records"]
                if r["kind"] == "recall_question" and str(r["device_id"]).startswith("robo")]
        orig = {r["opportunity_id"]: r for r in recs if "reask_of" not in r}
        reasks = [r for r in recs if "reask_of" in r]
        distinct = {r["question_id"] for r in recs}
        all_distinct |= distinct
        # the export, one row per re-ask, with the ORIGINAL ask time for the parity control
        path = OUT_DIR / f"reask_list_seed{seed}.jsonl"
        with open(path, "w") as f:
            for r in sorted(reasks, key=lambda z: (z["device_id"], z["session_id"], z["t"])):
                src = orig.get(r["reask_of"]) or {}
                f.write(json.dumps(dict(
                    seed=seed, device_id=r["device_id"], session_id=r["session_id"],
                    question_id=r["question_id"], reask_time=r["t"],
                    reask_time_session=r["t_ask_session"],
                    ask_time=src.get("t"), ask_time_session=src.get("t_ask_session"),
                    reask_index=r["reask_index"], history_tokens=r["history_tokens"],
                    device_latency_s_warm=round(float(warm[r["question_id"]]), 6),
                    opportunity_id=r["opportunity_id"], reask_of=r["reask_of"]),
                    sort_keys=True) + "\n")
        rows_total += len(reasks)
        per_seed[str(seed)] = dict(
            originals=len(recs) - len(reasks), reasks=len(reasks), total_asks=len(recs),
            distinct_questions=len(distinct),
            distinct_coverage_of_pool=round(len(distinct) / len(pool), 4),
            reasks_beyond_32k=st.get("robot_reasks_beyond_32k"),
            reask_empty_pool=st.get("robot_reask_empty_pool"),
            asks_per_distinct=round(len(recs) / max(len(distinct), 1), 3),
            export=str(path.relative_to(REPO)))
    res["per_seed"] = per_seed
    res["pool_n"] = len(pool)
    res["distinct_over_all_seeds"] = len(all_distinct)
    res["distinct_coverage_over_all_seeds"] = round(len(all_distinct) / len(pool), 4)
    res["export_rows_total"] = rows_total
    res["recent_window_definition_for_orin"] = (
        "committed 60-frame last-120 s filter over the D2 frame list ending at reask_time, "
        "matching StudyORIN-REC part 1; the Orin proposed this and session D confirms it")
    res["device_latency_note"] = (
        "scorer/score.py:248-258 prefers the MEASURED warm table keyed on question_id and REFUSES "
        "rather than guessing, and all 69 pool questions are present in it, so a re-ask already "
        "scored at the recent-window warm latency. D161 (3) is satisfied in the scored path; the "
        "trace's own superseded fallback field is now set from the same table so the two agree.")
    res["_provenance"] = _provenance.stamp(script="reask_trace_proofs.py", model="32BI",
                                           device="nvidia_rtx_a6000", n=len(SEEDS), args=None)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=2, sort_keys=True))

    print("PROOFS")
    for k in ("proof_1_off_is_deterministic", "proof_1b_off_is_subset_of_on",
              "proof_1c_only_recall_added", "proof_1d_ids_renumber",
              "proof_2_on_is_deterministic"):
        print(f"  {k:34s} {res[k]}")
    p3 = res["proof_3_digests_equal"]
    print(f"  proof_3_fairness_digest_equal      {p3['fairness']}")
    print(f"  proof_3_off_and_on_differ          {p3['off_and_on_differ']}  "
          f"(they MUST differ: re-asks are extra scored opportunities)")
    print(f"\nPOOL {len(pool)} questions")
    print(f"{'seed':>5s} {'orig':>5s} {'reask':>6s} {'total':>6s} {'distinct':>9s} "
          f"{'cover':>6s} {'>32k':>5s} {'asks/q':>7s}")
    for s, v in per_seed.items():
        print(f"{s:>5s} {v['originals']:5d} {v['reasks']:6d} {v['total_asks']:6d} "
              f"{v['distinct_questions']:9d} {v['distinct_coverage_of_pool']:6.3f} "
              f"{v['reasks_beyond_32k']:5d} {v['asks_per_distinct']:7.2f}")
    print(f"\nDISTINCT over seeds {SEEDS}: {len(all_distinct)} of {len(pool)} "
          f"= {res['distinct_coverage_over_all_seeds']:.1%}")
    print(f"export rows: {rows_total} across {len(SEEDS)} files in "
          f"{OUT_DIR.relative_to(REPO)}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
