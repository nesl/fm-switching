#!/usr/bin/env python3
"""D161 (3): join the Orin's measured REASK device answers over the FROZEN D87 ones.

A re-ask reuses the committed D87 device answer, which was measured at the ORIGINAL ask on a
shorter history, because the D87 table is keyed on `question_id` alone. That understates the device
and therefore overstates the benefit of escalating (`reports/study_robot_reask_design.md`). The
Orin's StudyORIN-REC REASK records the device answer AT each re-ask instant on the recent window,
so this script replaces the frozen value with the measured one.

WHAT IT PRODUCES
  results/orchestration/live2/reask_device_join/reask_device_answers_seed<N>.jsonl
      one row per re-ask, keyed on `opportunity_id`, carrying the MEASURED device answer, its
      confidence and its completion latency, ready to be patched over a cell's
      `device_answers.jsonl`.
  results/orchestration/live2/reask_device_join/reask_device_join.json
      the before/after summary, including how often the measured answer differs from the frozen
      one, which is the size of the error the PROVISIONAL label stands for.

WHICH LATENCY. `device_latency_s` is replaced by the Orin's measured `completion_s`, not its
`ttft_s`, because D155 scores a device answer by WHEN IT ARRIVES and the committed warm table is
completion-based: `ORIN_REC_WARM_COMPLETION_P50` is 0.2697 and the table's own values span 0.2503
to 0.3108. Cross-check on the first row: measured `completion_s` 0.2954 against the committed warm
reference 0.2944 for the same question, agreeing to about 1 ms.

NOTHING IS SYNTHESIZED. A re-ask with no measured row keeps its frozen answer and is counted.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HERE = REPO / "experiments/orchestration/live2"
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/baselines"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _provenance                       # noqa: E402
import data_sources as DS                # noqa: E402

SEEDS = (4, 5, 6, 7)
ORIN = REPO / "results/sember/study_orin_rec"
OUTDIR = REPO / "results/orchestration/live2/reask_device_join"
LISTS = REPO / "results/orchestration/live2/reask_lists"


def main():
    dev87 = DS.d87_device_answers() if hasattr(DS, "d87_device_answers") else None
    res = {"seeds": {}, "latency_field": "completion_s (D155 scores by arrival; the committed warm "
                                         "table is completion-based)"}
    for seed in SEEDS:
        src = ORIN / f"orin_rec_reask_seed{seed}.jsonl"
        if not src.exists():
            res["seeds"][str(seed)] = dict(status="ABSENT, not yet pushed")
            continue
        rows = [json.loads(l) for l in open(src)]
        reask = [r for r in rows if r.get("kind") == "reask"]
        parity = [r for r in rows if r.get("kind") == "parity"]
        # the frozen answer per question, from the exported list's own record of it
        lst = LISTS / f"reask_list_seed{seed}.jsonl"
        frozen = {}
        if lst.exists():
            for l in open(lst):
                r = json.loads(l)
                frozen[r["opportunity_id"]] = r
        OUTDIR.mkdir(parents=True, exist_ok=True)
        out = OUTDIR / f"reask_device_answers_seed{seed}.jsonl"
        changed = same = nogold = 0
        corr_measured = corr_frozen = 0
        errs = 0
        with open(out, "w") as f:
            for r in reask:
                if r.get("error") or r.get("prefill_error"):
                    errs += 1
                    continue
                oid = r["opportunity_id"]
                # the FROZEN answer for this question: whatever the parity row reproduces, which is
                # the part1/WARM letter the D87 table carries for the original ask
                par = next((p for p in parity if p["question_id"] == r["question_id"]), None)
                froz_letter = (par or {}).get("warm_letter") or (par or {}).get("part1_letter")
                gold = r.get("gold")
                if gold is None:
                    nogold += 1
                if froz_letter is not None:
                    if froz_letter == r["letter"]:
                        same += 1
                    else:
                        changed += 1
                    corr_frozen += 1 if (gold is not None and froz_letter == gold) else 0
                corr_measured += 1 if bool(r.get("correct")) else 0
                f.write(json.dumps(dict(
                    opportunity_id=oid, reask_of=r.get("reask_of"),
                    question_id=r["question_id"], session_id=r.get("session_id"),
                    device_answer=r["letter"], device_correct=bool(r.get("correct")),
                    gold_letter=gold,
                    device_latency_s=float(r["completion_s"]),
                    device_answer_confidence=float(r["letter_prob"]),
                    frozen_device_answer=froz_letter,
                    differs_from_frozen=(froz_letter is not None and froz_letter != r["letter"]),
                    reask_index=r.get("reask_index"),
                    measured_ttft_s=float(r["ttft_s"]),
                    committed_warm_ref_s=r.get("device_latency_s_warm_ref"),
                    source="StudyORIN-REC-REASK seed %d" % seed), sort_keys=True) + "\n")
        n = changed + same
        res["seeds"][str(seed)] = dict(
            status="joined", reask_rows=len(reask), errors=errs, written=n,
            parity_rows=len(parity),
            parity_reproduces_part1=sum(1 for p in parity if p.get("reproduces_part1")),
            parity_reproduces_warm=sum(1 for p in parity if p.get("reproduces_warm")),
            differs_from_frozen=changed, same_as_frozen=same,
            differs_pct=(round(100.0 * changed / n, 2) if n else None),
            device_correct_measured=corr_measured,
            device_correct_frozen=corr_frozen,
            accuracy_measured=(round(corr_measured / n, 4) if n else None),
            accuracy_frozen=(round(corr_frozen / n, 4) if n else None),
            export=str(out.relative_to(REPO)))
    res["_provenance"] = _provenance.stamp(script="reask_device_join.py", model="qwen3vl4b",
                                           device="jetson_orin", n=len(SEEDS), args=None)
    (OUTDIR / "reask_device_join.json").write_text(json.dumps(res, indent=2, sort_keys=True))
    print(f"{'seed':>5s} {'reasks':>7s} {'differs':>8s} {'%':>6s} {'acc_meas':>9s} {'acc_frozen':>11s} {'parity p1/warm':>15s}")
    for s, v in res["seeds"].items():
        if v.get("status") != "joined":
            print(f"{s:>5s}  {v['status']}")
            continue
        print(f"{s:>5s} {v['reask_rows']:7d} {v['differs_from_frozen']:8d} "
              f"{v['differs_pct'] or 0:6.1f} {v['accuracy_measured'] or 0:9.4f} "
              f"{v['accuracy_frozen'] or 0:11.4f} "
              f"{v['parity_reproduces_part1']}/{v['parity_reproduces_warm']:>7}")
    print(f"\nwrote {OUTDIR / 'reask_device_join.json'}")


if __name__ == "__main__":
    main()
