#!/usr/bin/env python3
"""The "tuned vLLM engine" baseline. OUR OWN measured configuration, not an external paper.

**DECIDED BY THE USER 2026-11-12, after StudyE10e-partial-prefill landed: the tuned engine is
StudyE10e's P1** - `--long-prefill-token-threshold 1024`, the DEFAULT step budget, FCFS.

Three committed studies bear on this, all recorded in `cards/tuned_engine.md`:

- **StudyE10c** tested E0 (default), E1 (`--scheduling-policy priority`),
  E2 (`--max-num-batched-tokens 2048`) and E4 (E1 + E2): "identical to E0 in 12 / 12 comparable
  ladders"; the levers "cost none without recall".
- **StudyE10d** located the mechanism: the unit holding episodic requests behind a cold recall is
  the LM prefill of its ~12.6k tokens, and it named `--long-prefill-token-threshold` as an
  untested lever.
- **StudyE10e** tested that lever: P1 (1024), P2 (512), P3 (1024 + priority). Its pre-registered
  verdict is **"no config removes the interference"** - all three hold C0 capacity at the 40 %
  ladder top with no loss, and all three still collapse to < 10 % under cold recall.

**Why P1 is nonetheless the right tuned configuration, and why P1 and not P2 or P3.** P1 cuts
episodic p99 by **19-25 % at C1** (2.65 -> 2.12 s) and **18-30 % at C4** (4.71 -> 3.50 s) at **no
C0 capacity cost**, and unlike its siblings it barely touches warm recall: at C4 its warm append
p50 goes 0.318 -> 0.323 s (x1.02) and its warm escalation 0.391 -> 0.396 s (x1.01), against P2's
x1.37 / x1.30 and P3's x1.53 / x2.09 (P3's priority demotes warm recall). Its cost is confined to
cold recall: TTFT p50 x1.05 at C1 and x1.11 at C4, p99 **x1.12 at C1 and x1.14 at C4** - the
"+12-21 %" the decision records.

**What this baseline is NOT.** It is not a configuration that restores capacity under recall;
StudyE10e's verdict stands and is quoted in the card. It is the best measured *tail-latency*
configuration at no capacity cost, which is what a serving reference should be.

This module exposes every configuration a committed study measured (StudyE10c's four and
StudyE10e's three), records what was not run or does not exist, and **keeps the guard**: any name
no study measured raises, so no downstream table can contain a configuration nothing supports.

CPU only.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)

# StudyE10c's engine configurations, verbatim from its report.
CONFIGS: Dict[str, Dict[str, object]] = {
    "E0": dict(desc="vLLM 0.31.0 default: chunked prefill ON, max_num_batched_tokens 8192, "
                    "policy fcfs", measured_in="StudyE10c", flags=()),
    "E1": dict(desc="--scheduling-policy priority (episodic 0, warm appends / escalations 1, "
                    "cold recall 2)", measured_in="StudyE10c",
               flags=("--scheduling-policy priority",)),
    "E2": dict(desc="--max-num-batched-tokens 2048", measured_in="StudyE10c",
               flags=("--max-num-batched-tokens 2048",)),
    "E4": dict(desc="E1 + E2", measured_in="StudyE10c",
               flags=("--scheduling-policy priority", "--max-num-batched-tokens 2048")),
    "P1": dict(desc="--long-prefill-token-threshold 1024", measured_in="StudyE10e",
               flags=("--long-prefill-token-threshold 1024",)),
    "P2": dict(desc="--long-prefill-token-threshold 512", measured_in="StudyE10e",
               flags=("--long-prefill-token-threshold 512",)),
    "P3": dict(desc="P1 + --scheduling-policy priority (episodic 0, warm 1, cold 2)",
               measured_in="StudyE10e",
               flags=("--long-prefill-token-threshold 1024", "--scheduling-policy priority")),
}
# Recorded so the measured set is not mistaken for the whole option space.
NOT_RUN = {
    "E3": "max-num-batched-tokens 512 - DROPPED by the user's trim in StudyE10c",
    "max-num-partial-prefills": "does NOT EXIST in vLLM 0.31.0 (StudyE10e s0 flag check)",
    "max-long-partial-prefills": "does NOT EXIST in vLLM 0.31.0 (StudyE10e s0 flag check)",
    "long-prefill-threshold-adaptive": "supported but deliberately NOT used by StudyE10e: its "
                                       "floor weakens the cap when few requests wait, which is "
                                       "the C1 case",
    "2048-step + 512-cap": "a documented 0.31.0 combination StudyE10e did not test; named in its "
                           "verdict as a caveat",
    "no-async-scheduling": "as above - documented, untested",
}
# The tuned engine, decided by the user 2026-11-12 on StudyE10e's evidence.
TUNED = "P1"
BEST_MEASURED = "E0"          # the best configuration under StudyE10c / E10e's CAPACITY rule
BEST_MEASURED_REASON = (
    "StudyE10c found E0, E1, E2 and E4 identical in 12 / 12 comparable ladders and found the "
    "levers cost nothing without recall. StudyE10e then tested the long-prefill threshold "
    "(P1 1024, P2 512, P3 1024 + priority) and concluded that NO config removes the "
    "interference: all three hold C0 capacity at the 40 % ladder top like P0 and all three "
    "collapse to < 10 % under cold recall, five levels below their own C0. Under recall they are "
    "also strictly WORSE than the default - cold TTFT p99 +12-13 % at C1, +14-21 % at C4, and at "
    "C4 warm recall degrades (P2 appends +37 %, P3 escalation x2.1). The best measured "
    "configuration is therefore the DEFAULT, on two studies."
)
TUNED_REASON = (
    "StudyE10e's P1 (--long-prefill-token-threshold 1024, default step budget, FCFS) is the "
    "tuned engine, decided by the user 2026-11-12. It does NOT restore capacity - StudyE10e's "
    "pre-registered verdict that no config removes the interference stands - but it cuts episodic "
    "p99 by 19-25 % at C1 and 18-30 % at C4 at no C0 capacity cost, and unlike P2 / P3 it barely "
    "touches warm recall (C4 append x1.02, escalation x1.01, against P2 x1.37 / x1.30 and P3 "
    "x1.53 / x2.09). Its cost is confined to cold recall: TTFT p99 x1.12 at C1 and x1.14 at C4."
)


class TunedEngine(Policy):
    """The engine configuration as a policy decision, with FCFS request handling.

    It decides only `engine_config`; everything else takes the documented defaults, so this
    baseline isolates the engine lever from the scheduling one.
    """

    name = "tuned-engine"
    case = "own"
    experiments = ('C-mixed',)
    paper = None
    decides = ("engine_config",)
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "recall_decision",
                     "representation", "session_action", "order")

    def __init__(self, config: str = TUNED) -> None:
        if config not in CONFIGS:
            raise ValueError(
                f"engine configuration {config!r} has no committed measurement. "
                f"Measured: {sorted(CONFIGS)}. Not run: {NOT_RUN}. "
                f"{BEST_MEASURED_REASON} {TUNED_REASON}")
        self.config = config

    def decide(self, obs: Observation) -> Action:
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            engine_config=self.config, order="FCFS")
