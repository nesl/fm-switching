#!/usr/bin/env python3
"""The "tuned vLLM engine" baseline. OUR OWN measured configuration, not an external paper.

**THIS BASELINE IS UNDER-SPECIFIED BY THE COMMITTED RECORD, AND THAT IS REPORTED RATHER THAN
GUESSED.** The task names it as "the best engine configuration from StudyE10c / E10e (priority +
step budget + long-prefill threshold)". Three problems, each checked against the repository:

1. **StudyE10e does not exist.** There is no `reports/study_e10e*.md` and no StudyE10e row in
   `research/EXPERIMENTS.md` (only E10a, E10b, E10c, E10d). Nothing can be read from it.
2. **StudyE10c's verdict is that no engine setting helps.** It tested E0 (vLLM 0.31.0 default),
   E1 (`--scheduling-policy priority`), E2 (`--max-num-batched-tokens 2048`) and E4 (E1 + E2),
   and found them "identical to E0 in 12 / 12 comparable ladders"; the levers "cost none without
   recall". So the best MEASURED configuration is indistinguishable from the default.
3. **The long-prefill threshold was never run.** StudyE10d lists
   `--long-prefill-token-threshold` (default 0) as an "untested lever".

This module therefore exposes exactly the configurations a committed study measured, defaults to
E0, and REFUSES to invent a tuned combination. `BEST_MEASURED` is E0 with the reason attached,
and asking for `"E10e-best"` raises, so no downstream table can quietly contain a number that no
measurement supports.

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
}
# E10c dropped E3 (512) on the user's trim; recorded so the set is not mistaken for complete.
NOT_RUN = {
    "E3": "max-num-batched-tokens 512 - DROPPED by the user's trim in StudyE10c",
    "long-prefill-threshold": "--long-prefill-token-threshold - named by StudyE10d as an "
                              "UNTESTED lever (default 0); no committed measurement exists",
}
BEST_MEASURED = "E0"
BEST_MEASURED_REASON = (
    "StudyE10c found E0, E1, E2 and E4 identical in 12 / 12 comparable ladders and found the "
    "levers cost nothing without recall, so no configuration it measured beats the default. "
    "StudyE10e, which the task names as the source of a tuned configuration, DOES NOT EXIST in "
    "this repository."
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

    def __init__(self, config: str = BEST_MEASURED) -> None:
        if config not in CONFIGS:
            raise ValueError(
                f"engine configuration {config!r} has no committed measurement. "
                f"Measured: {sorted(CONFIGS)}. Not run: {NOT_RUN}. {BEST_MEASURED_REASON}")
        self.config = config

    def decide(self, obs: Observation) -> Action:
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            engine_config=self.config, order="FCFS")
