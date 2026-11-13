#!/usr/bin/env python3
"""Toy tests for the StudyB-baselines amendment: B10, B11 and the two new actions.

CPU only; no model, no inference. These are behaviour tests in the same style as the paper
reconstructions' toy tests: each asserts one NAMED behaviour on a hand-built observation, so a
reviewer can see the mechanism fire rather than take the smoke replay's "it ran" on trust.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "experiments/dashcam"))

import costs as C                                              # noqa: E402
import profiles as P                                           # noqa: E402
from constructed import B10BlockingAwareAdmission, B11NaiveSlicing  # noqa: E402
from interface import (CloudState, EpisodicStream, EvidenceItem, NetworkState, Observation,  # noqa
                       RecallQuery, materialize, suspend_stream, validate_action, Action,
                       SessionAction, StreamAction)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name} {detail}".strip())
    print(("  [ok] " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))


def obs_with(readiness, tokens, deadline_s, now_s=10.0, cadence_s=0.5, frame_count=1,
             connected=True):
    st = EpisodicStream(stream_id="s1", delivered_scores=(0.1, 0.2), delivered_times_s=(9.5, 9.75),
                        cadence_s=cadence_s, frame_count=frame_count, on_cloud=False,
                        network=NetworkState(connected, C.UPLINK_BPS, C.RTT_S))
    q = RecallQuery(query_id="q1", session_id="sess", category="D2", arrival_s=now_s,
                    deadline_s=now_s + deadline_s,
                    evidence=(EvidenceItem("D2", "host", tokens, tokens * 4),),
                    readiness=readiness, readiness_tokens=tokens)
    cloud = CloudState(queued_by_class={}, running_by_class={}, gpu_kv_fraction=0.0,
                       host_kv_fraction=0.0, gpu_warm_sessions=(), host_warm_sessions=("sess",),
                       latency_estimate_s={})
    return Observation(now_s=now_s, epoch="recall_arrival", streams=(st,), recall=(q,),
                       cloud=cloud, budget_remaining_gpu_s=100.0)


def main():
    print("B10 blocking-aware admission")
    b10 = B10BlockingAwareAdmission()
    dstar = P.d_star_s("32BI_N1", 0.5)
    t_cold28 = C.recall_ttft_s(28114, "COLD")
    t_warm11 = C.recall_ttft_s(11050, "HOST-WARM")
    check("StudyE9d d* is read, not guessed", dstar is not None and 1.0 < dstar < 3.0,
          f"d* = {dstar:.3f} s for 32BI_N1 at cadence 0.5 s")
    check("a COLD 28k recall's predicted hold EXCEEDS d*", t_cold28 > dstar,
          f"T = {t_cold28:.2f} s > d* = {dstar:.2f} s")
    check("a HOST-WARM 11k recall's predicted hold is UNDER d*", t_warm11 < dstar,
          f"T = {t_warm11:.2f} s < d* = {dstar:.2f} s")

    b10.reset()
    a = b10(obs_with("COLD", 28114, deadline_s=30.0))
    check("B10 DEFERS the cold recall while it has slack", a.recall[0].decision == "DEFER",
          f"decision = {a.recall[0].decision}, defer_s = {a.recall[0].defer_s}")
    b10.reset()
    a = b10(obs_with("COLD", 28114, deadline_s=1.0))
    check("B10 ADMITS it once the deadline slack is exhausted",
          a.recall[0].decision == "CLOUD", f"decision = {a.recall[0].decision}")
    check("admitting a COLD query MATERIALIZES the session monolithically",
          any(x.action == "MATERIALIZE" and x.slice_tokens is None for x in a.sessions),
          f"sessions = {[(x.action, x.slice_tokens) for x in a.sessions]}")
    b10.reset()
    a = b10(obs_with("HOST-WARM", 11050, deadline_s=30.0))
    check("B10 ADMITS a warm recall that holds nothing past d*",
          a.recall[0].decision == "CLOUD", f"decision = {a.recall[0].decision}")
    b10.reset()
    a = b10(obs_with("COLD", 28114, deadline_s=30.0, connected=False))
    check("with no connected stream there is nothing to protect, so it admits",
          a.recall[0].decision == "CLOUD", f"decision = {a.recall[0].decision}")
    b10.reset()
    a = b10(obs_with("COLD", 28114, deadline_s=30.0))
    check("B10 orders by EDF", a.order == "EDF", f"order = {a.order}")
    check("B10 declares the monolithic restriction (fairness rule 4)",
          bool(b10.restricts_action_space) and bool(b10.restriction_reason),
          b10.restricts_action_space)

    print("B11 naive slicing")
    b11 = B11NaiveSlicing()
    b11.reset()
    a = b11(obs_with("HOST-WARM", 11050, deadline_s=5.0))
    sl = [x for x in a.sessions if x.action == "MATERIALIZE"]
    check("B11 slices every materialization", bool(sl) and all(x.slice_tokens == 2048 for x in sl),
          f"slice_tokens = {[x.slice_tokens for x in sl]}")
    check("B11 is FCFS and unaware of episodic timing", a.order == "FCFS",
          f"order = {a.order}")
    check("B11 runs the tuned engine the user chose", a.engine_config == "P1",
          f"engine_config = {a.engine_config}")
    check("B11 admits every recall to the cloud",
          all(r.decision == "CLOUD" for r in a.recall))

    print("the two new actions, validated by the interface")
    o = obs_with("COLD", 28114, deadline_s=5.0)
    try:
        validate_action(Action(sessions=[materialize("sess", 11050, 2048)]), o)
        ok = True
    except Exception as e:                                           # noqa: BLE001
        ok, err = False, str(e)
    check("MATERIALIZE with a positive slice size validates", ok)
    for bad, why in ((SessionAction("sess", "MATERIALIZE"), "no target_tokens"),
                     (SessionAction("sess", "MATERIALIZE", target_tokens=0), "zero target"),
                     (SessionAction("sess", "MATERIALIZE", target_tokens=10, slice_tokens=0),
                      "zero slice"),
                     (SessionAction("sess", "EVICT", target_tokens=10),
                      "target_tokens on a non-MATERIALIZE action")):
        try:
            validate_action(Action(sessions=[bad]), o)
            rejected = False
        except ValueError:
            rejected = True
        check(f"the interface REJECTS {why}", rejected)
    try:
        validate_action(Action(streams=[suspend_stream("s1", o.now_s + 2.0)]), o)
        ok = True
    except Exception:                                                # noqa: BLE001
        ok = False
    check("SUSPEND_UNTIL in the future validates", ok)
    for bad, why in ((StreamAction("s1", "suspend", suspend_until_s=o.now_s - 1), "a past time"),
                     (StreamAction("s1", "suspend"), "no suspend_until_s"),
                     (StreamAction("s1", "suspend", cadence_s=0.5, suspend_until_s=o.now_s + 2),
                      "a cadence on a suspended stream"),
                     (StreamAction("s1", "cloud", 0.5, 1, suspend_until_s=o.now_s + 2),
                      "suspend_until_s on a cloud stream")):
        try:
            validate_action(Action(streams=[bad]), o)
            rejected = False
        except ValueError:
            rejected = True
        check(f"the interface REJECTS {why}", rejected)

    print(f"\n{len(PASS)} / {len(PASS) + len(FAIL)} named behaviours reproduced")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
