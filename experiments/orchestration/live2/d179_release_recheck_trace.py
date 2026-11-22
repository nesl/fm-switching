#!/usr/bin/env python3
"""D179 (4) mechanism verification Step 3: ONE TRACED UNIT, readable by hand.

The unit is ONE REQUEST at its release instant. For each of the three deadline types the trace
records every input, the predicted first-token time term by term, the time remaining to the
deadline, which constraint bound the decision (deadline re-check, KV/budget, or neither), and the
outcome. For the alert type it also traces the NEXT instant of the same episode, because the
load-bearing claim is about what that request carries after a skip.

Not a measurement: a dry coordinator, no engine, no server. The numbers are the model's own
predictions, which is exactly what the re-check decides on.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "hybrid"), str(HERE / "v5"),
           str(HERE / "tests"), str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bodies as B                                                      # noqa: E402
import d162_price as DP                                                 # noqa: E402
import release_recheck as RR                                            # noqa: E402
from test_release_recheck import _Fixture, L_SH, T0                     # noqa: E402

DEST = REPO / "results/orchestration/live2/frozen_test/d179_release_recheck_trace.json"


def _terms(uncached: int, queue: int) -> dict:
    return {"intercept_s": DP.INTERCEPT_S,
            "per_uncached_s": DP.PER_UNCACHED_S * uncached,
            "per_queue_s": DP.PER_QUEUE_S * queue,
            "est_first_token_s": DP.first_token_s(uncached, queue)}


def alert_unit() -> dict:
    f = _Fixture(Path(tempfile.mkdtemp()), recheck=True)
    f.episode(0, 4, t_capture=T0)
    queue = 30000
    f.co._uncached_in_flight = queue
    t_rel = T0 + 0.1
    o = f.co.st.opps["o000"]
    uncached = B.epg_prompt_tokens(4)
    before = {"t_release_s": t_rel, "opportunity": o.opp_id,
              "episode_frames": 4, "episode_refs": list(o.episode_frame_refs),
              "predicted_prompt_tokens": B.epg_prompt_tokens(4),
              "predicted_uncached_tokens": uncached,
              "uncached_queued_ahead": queue,
              "deadline_abs_s": o.deadline_abs(), "remaining_s": o.deadline_abs() - t_rel,
              "terms": _terms(uncached, queue),
              "budget_gpu_s_remaining": f.co.st.budget.gpu_seconds
                                        - f.co.st.budget.spent_gpu_seconds}
    f.serve(t_rel)
    skipped = f.co.release_infeasible_events[-1] if f.co.release_infeasible_events else None
    after = {"submissions": len(f.submissions()),
             "bound_by": ("deadline re-check (D179 (4))" if skipped else "neither"),
             "counts": {k: v for k, v in f.co.counts.items() if k.startswith("release_")},
             "opportunity_state": o.state,
             "gpu_s_charged": 0.0,
             "uncached_in_flight_after": f.co._uncached_in_flight,
             "outcome": "device answer stands (latency_miss for the cloud answer that was never "
                        "asked for; the frame is NOT lost)"}
    # THE NEXT INSTANT OF THE SAME EPISODE, which is what makes the skip cost the question only
    f.co._uncached_in_flight = 0
    f.episode(1, 5, t_capture=T0 + 2.0)
    f.serve(T0 + 2.1)
    sub = f.submissions()[-1]
    nxt = {"t_release_s": T0 + 2.1, "opportunity": "o001",
           "episode_refs": list(sub.body["_live2"]["frame_refs"]),
           "carries_the_skipped_frame": skipped["skipped_frame_ref"] in
                                        sub.body["_live2"]["frame_refs"],
           "predicted_prompt_tokens": B.epg_prompt_tokens(5),
           "predicted_uncached_tokens": f.co.epg_requests[-1]["new_tokens_charged"],
           "uncached_if_instant_0_had_been_sent": B.epg_prompt_tokens(1),
           "rise_tokens": f.co.epg_requests[-1]["new_tokens_charged"] - B.epg_prompt_tokens(1),
           "gpu_s_charged": f.co.epg_requests[-1]["gpu_s_charged"]}
    return {"type": "alert", "at_release": before, "decision": after,
            "skipped_event": skipped, "next_instant_same_episode": nxt}


def recall_unit(dev: str, dev_type: str, qtype: str, deadline_s: float, tokens: int) -> dict:
    f = _Fixture(Path(tempfile.mkdtemp()), recheck=True, dev=dev, dev_type=dev_type)
    o, s = f.recall(0, t_ask=T0, deadline_s=deadline_s, tokens=tokens)
    t_rel = T0 + 0.01
    uncached = tokens                                   # COLD: the whole history is uncached
    before = {"t_release_s": t_rel, "opportunity": o.opp_id, "session": s.session_id,
              "readiness": s.residency_readiness(),
              "predicted_prompt_tokens": tokens, "predicted_uncached_tokens": uncached,
              "uncached_queued_ahead": 0,
              "deadline_abs_s": o.deadline_abs(), "remaining_s": o.deadline_abs() - t_rel,
              "terms": _terms(uncached, 0),
              "budget_gpu_s_remaining": f.co.st.budget.gpu_seconds
                                        - f.co.st.budget.spent_gpu_seconds}
    f.co._submit_recall(o, s, t_rel, 0.0, None, {}, whole=True)
    ev = f.co.release_infeasible_events[-1] if f.co.release_infeasible_events else None
    after = {"submissions": len(f.submissions()),
             "bound_by": ("deadline re-check (D179 (4))" if ev else "neither"),
             "counts": {k: v for k, v in f.co.counts.items() if k.startswith("release_")},
             "opportunity_state": o.state, "gpu_s_charged": 0.0 if ev else None,
             "outcome": ("device answer stands" if ev else "sent to cloud")}
    return {"type": qtype, "at_release": before, "decision": after, "skipped_event": ev}


def main() -> int:
    out = {"_what": "D179 (4) Step 3: one traced unit per deadline type at its release instant",
           "_not_a_measurement": "dry coordinator, no engine; the numbers are the D162 model's "
                                 "own predictions, which is what the re-check decides on",
           "price_source": DP.SOURCE, "drift_check": DP.assert_no_drift(),
           "interface_check": RR.assert_no_interface_drift(),
           "deadline_s_used": {"alert": L_SH, "note": "taken from the opportunity, never from a "
                                                      "per-type constant"},
           "units": [alert_unit(),
                     recall_unit("robo000", "robot", "recall", 0.05, 8000),
                     recall_unit("asst000", "assistive", "assistance", 0.05, 1400),
                     # and one that is NOT bound, so the trace shows both outcomes
                     recall_unit("robo000", "robot", "recall-feasible", 30.0, 8000)]}
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(out, indent=1, default=float) + "\n")
    for u in out["units"]:
        a, d = u["at_release"], u["decision"]
        print("%-18s uncached=%-6s queue=%-6s est=%.4fs remaining=%.4fs -> %-10s bound_by=%s"
              % (u["type"], a["predicted_uncached_tokens"], a["uncached_queued_ahead"],
                 a["terms"]["est_first_token_s"], a["remaining_s"],
                 "SKIP" if d["submissions"] == 0 else "SENT", d["bound_by"]))
    nx = out["units"][0]["next_instant_same_episode"]
    print("alert next instant: carries the skipped frame=%s, uncached %s vs %s if sent (+%s)"
          % (nx["carries_the_skipped_frame"], nx["predicted_uncached_tokens"],
             nx["uncached_if_instant_0_had_been_sent"], nx["rise_tokens"]))
    print("wrote", DEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
