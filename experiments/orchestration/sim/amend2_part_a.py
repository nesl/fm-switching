#!/usr/bin/env python3
"""StudyB-baselines amendment 2, Part A re-run: every runnable arm on ONE representative cell.

CPU only. Nothing here runs a model, and nothing here is a sweep: it replays the StudySIM1d
Part A cell (balanced mix, F = 4, deadline 5 s, seed 0) once per arm and records the action
counts by class, the episodic cloud fraction and the recall timely accuracy, so the BEFORE and
AFTER of the amendment-2 fixes can be compared arm by arm.

Run it with `--out <path>` BEFORE applying the fixes and again afterwards; `--diff a b` prints
the comparison and flags any arm that changed outside the pre-declared expected set.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
for p in (ROOT / "experiments/dashcam", ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/orchestration/baselines/smoke",
          ROOT / "experiments/orchestration/baselines/reconstructed",
          ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import run as R                        # noqa: E402
import workload as W                   # noqa: E402
from sim1d_validate import AUDIT_CELL, Traced   # noqa: E402

# Pre-registered in research/EXPERIMENTS.md (StudyB-baselines amendment 2) BEFORE this ran: the
# arms the eight accepted fixes are expected to change, including the two shared-harness-state
# effects (the evidence inventory of item 4 and the action ordering of item 8).
EXPECTED_CHANGE = {
    "videostorm/maxmin": "item 1 (lag as the configuration's own hold shift)",
    "videostorm/maxsum": "item 1",
    "B9-noHost": "item 1 via component (ii); item 4 via the evidence inventory",
    "covstream": "item 2 (stream action follows DEFAULTS); item 4 via the evidence inventory",
    "simplestream": "item 2",
    "streamscout": "item 2; item 3 (committed device confidence); item 4 via the inventory",
    "thinking-qwenvl-atdm": "item 4 (the inventory lists the representations that exist)",
    "kvflow": "item 5 (OFFLOAD_TO_HOST -> KEEP_GPU_WARM in scope); item 8 (action ordering)",
    "preble": "item 5",
    "rh8-demand-aware-causal": "items 5 and 6; item 8 (action ordering)",
    "rh8-demand-aware-ORACLE": "items 5 and 6; item 8 (action ordering)",
    "B10-blocking-aware-admission": "item 7 (B10 is redefined as StudySLICE1's P2)",
    "B11-naive-slicing": "item 8 (B11 is redefined as StudySLICE1's P3) and the ordering fix",
}

FIELDS = ("challenge_mAP", "episodic_cloud_fraction", "recall_timely_accuracy",
          "stream_actions", "recall_actions", "session_actions", "slice_materializations",
          "engine_slice_steps", "engine_steps", "engine_gpu_busy_s", "episodic_submitted",
          "episodic_completed", "recall_n", "gpu_s")


def run_all(cell: Dict[str, Any] = AUDIT_CELL) -> Dict[str, Any]:
    tr = W.build_trace(cell["mix"], cell["fleet"], cell["deadline_s"], cell["seed"])
    rows: List[Dict[str, Any]] = []
    for label, pol in R._arms():
        tp = Traced(pol, keep=0)
        try:
            res = R.run_cell(tr, tp, seed=cell["seed"])
        except Exception as e:                                        # noqa: BLE001
            rows.append(dict(arm=label, failed=f"{type(e).__name__}: {e}"))
            print("  %-32s FAILED %s" % (label, e), flush=True)
            continue
        sa = dict(tp.stream_actions)
        tot = sum(sa.values())
        row = dict(
            arm=label,
            challenge_mAP=round(res["challenge_mAP"], 6),
            episodic_cloud_fraction=(round(sa.get("cloud", 0) / tot, 6) if tot else None),
            recall_timely_accuracy=res["recall"]["timely_accuracy"],
            stream_actions=sa, recall_actions=dict(tp.recall_actions),
            session_actions=dict(tp.session_actions),
            slice_materializations=tp.slice_requests,
            engine_slice_steps=res["engine"]["slice_steps"],
            engine_steps=res["engine"]["steps"],
            engine_gpu_busy_s=res["engine"]["gpu_busy_s"],
            episodic_submitted=res["episodic"]["submitted"],
            episodic_completed=res["episodic"]["completed"],
            recall_n=res["recall"]["n"], gpu_s=res["gpu_s"],
            decisions=res["decisions"], epochs=tp.epochs)
        rows.append(row)
        print("  %-32s mAP %.4f  cloud %s  timely %s" % (
            label, row["challenge_mAP"], row["episodic_cloud_fraction"],
            row["recall_timely_accuracy"]), flush=True)
    return dict(cell=dict(cell, trace_digest=tr.digest, length_s=tr.length_s,
                          question_set=W.QUESTION_SET),
                n_arms=len(rows), arms=rows)


def diff(a_path: str, b_path: str) -> Dict[str, Any]:
    A = {r["arm"]: r for r in json.loads(Path(a_path).read_text())["arms"]}
    B = {r["arm"]: r for r in json.loads(Path(b_path).read_text())["arms"]}
    out = []
    for arm in sorted(set(A) | set(B)):
        a, b = A.get(arm, {}), B.get(arm, {})
        changed = sorted(f for f in FIELDS if a.get(f) != b.get(f))
        out.append(dict(arm=arm, changed=changed, expected=EXPECTED_CHANGE.get(arm),
                        unintended=bool(changed) and arm not in EXPECTED_CHANGE,
                        before={f: a.get(f) for f in FIELDS},
                        after={f: b.get(f) for f in FIELDS}))
    unint = [r["arm"] for r in out if r["unintended"]]
    return dict(n_arms=len(out), n_changed=sum(1 for r in out if r["changed"]),
                n_unintended=len(unint), unintended_arms=unint, arms=out,
                expected_change_set=EXPECTED_CHANGE)


# ---------------------------------------------------------------- mechanical explanations
EXPLAIN_ARMS = ("confidence-cascade", "r3-streaming", "streamscout", "thinking-qwenvl-atdm",
                "videostorm/maxmin", "videostorm/maxsum", "B9-noHost",
                "B10-blocking-aware-admission", "B11-naive-slicing", "hybrid-llm")


def _recall_facts(obs, qid):
    q = next((x for x in obs.recall if x.query_id == qid), None)
    if q is None:
        return {}
    return dict(query_id=qid, now_s=obs.now_s, arrival_s=q.arrival_s, deadline_s=q.deadline_s,
                readiness=q.readiness, readiness_tokens=q.readiness_tokens,
                device_answer_confidence=q.device_answer_confidence,
                evidence=[(e.representation, e.tier, e.tokens) for e in q.evidence],
                n_distinct_representations=len({e.representation for e in q.evidence}))


def explain(cell=AUDIT_CELL, keep: int = 3) -> Dict[str, Any]:
    """For each named arm, the inputs and the rule behind its first few recall decisions, so the
    arithmetic of a changed decision can be checked by hand."""
    tr = W.build_trace(cell["mix"], cell["fleet"], cell["deadline_s"], cell["seed"])
    arms = dict(R._arms())
    out = {}
    for label in EXPLAIN_ARMS:
        if label not in arms:
            continue
        pol = arms[label]
        traces: List[Dict[str, Any]] = []

        class _Spy:
            def __init__(self, pol):
                self.pol = pol
                self.name = pol.name

            def __getattr__(self, k):
                return getattr(self.pol, k)

            def reset(self, seed: int = 0):
                self.pol.reset(seed)

            def __call__(self, obs):
                act = self.pol(obs)
                for ra in act.recall:
                    if len(traces) >= keep:
                        break
                    traces.append(dict(_recall_facts(obs, ra.query_id),
                                       action=ra.decision, defer_s=ra.defer_s,
                                       representation=ra.representation,
                                       notes={k: v for k, v in (act.notes or {}).items()
                                              if k != "d_star_s_reported_not_used"}))
                return act

        res = R.run_cell(tr, _Spy(pol), seed=cell["seed"])
        out[label] = dict(first_recall_decisions=traces,
                          recall=res["recall"], decisions=res["decisions"],
                          challenge_mAP=round(res["challenge_mAP"], 6),
                          engine=res["engine"],
                          reads_device_answer=bool(getattr(pol, "reads_device_answer", False)),
                          host_offload_intent=getattr(pol, "host_offload_intent", "demote"))
        print("  explained", label, flush=True)
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--diff", nargs=2)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--question-set", default="EVAL", choices=("EVAL", "ALL"),
                    help="EVAL is the amendment-2 default; ALL restores the pre-amendment "
                         "question set so the before / after table can be read on it")
    a = ap.parse_args()
    W.set_question_set(a.question_set)
    if a.explain:
        d = explain()
        if a.out:
            Path(a.out).write_text(json.dumps(d, indent=1, default=str))
            print("wrote", a.out)
        return 0
    if a.diff:
        d = diff(*a.diff)
        print(json.dumps({k: v for k, v in d.items() if k != "arms"}, indent=1))
        if a.out:
            Path(a.out).write_text(json.dumps(d, indent=1))
            print("wrote", a.out)
        return 0
    res = run_all()
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1))
        print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
