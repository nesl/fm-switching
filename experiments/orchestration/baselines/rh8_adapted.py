#!/usr/bin/env python3
"""StudyRH8 demand-aware warm state, ADAPTED behind our policy interface. Our own work.

Source: `experiments/cost/study_rh8_demand_aware.py` (not `experiments/orchestration/` as the
task text says - the file lives under `experiments/cost/`; noted in the card).

**A CONFLICT WITH THE INTERFACE, REPORTED RATHER THAN PAPERED OVER.** RH8's winning arm,
MIX-DEMAND, keeps warm "exactly the high-demand devices" - `eager_set()` returns
`high_demand(D)`, which is the SAME `random.Random(0).sample(...)` draw that ASSIGNED the
synthetic demand. The 2026-11-03 audit of that report says so explicitly: "MIX-DEMAND is given
the ground-truth demand labels ... The comparison therefore contrasts a policy with oracle
knowledge of the synthetic demand assignment against one with none; it does not show that demand
can be predicted."

Our interface forbids a policy from reading labels. So RH8 cannot enter the suite unchanged, and
rather than invent a hybrid this module ships BOTH readings, each labelled:

  RH8OracleDemand   reuses RH8's rule verbatim (warm = the known high-demand set). It reads a
                    label, declares `reads_future = True`, is EXCLUDED from the causality check
                    and is an UPPER BOUND, exactly like `naive.HindsightOracle`.
  RH8CausalDemand   the deployable reading: predict demand from each session's OWN observed
                    escalation history and keep the top fraction warm. This is NOT what StudyRH8
                    measured, and no RH8 number may be attributed to it.

Both keep RH8's other parameters: HIGH_FRAC = 0.25 of sessions warm, and the eager/lazy contrast
expressed through our session actions (KEEP_GPU_WARM vs OFFLOAD_TO_HOST / EVICT).

CPU only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from interface import (Action, Observation, Policy, RecallAction, SessionAction,
                       StreamAction, materialize)

HIGH_FRAC = 0.25        # StudyRH8 HIGH_FRAC
LOW_RATE = 0.20         # StudyRH8 LOW_RATE (its low-demand escalation rate)


def _warm_actions(all_sessions: Sequence[str], warm: Set[str],
                  already_gpu: Sequence[str] = (), tokens: Optional[Dict[str, int]] = None
                  ) -> List[SessionAction]:
    """StudyRH8's EAGER set. Amendment 2026-11-12: warming a session whose state does not exist
    yet is RH8's eager WARM-UP, which its own 2026-11-03 audit records as an excluded cost, so it
    is declared as MATERIALIZE with slice_tokens = None (RH8 warmed whole histories, never
    slices). Sessions already GPU-warm are held, not rebuilt."""
    g, tk = set(already_gpu), (tokens or {})
    out: List[SessionAction] = []
    for s in all_sessions:
        if s in warm:
            out.append(SessionAction(s, "KEEP_GPU_WARM") if s in g
                       else materialize(s, max(tk.get(s, 11000), 1), slice_tokens=None))
        else:
            out.append(SessionAction(s, "OFFLOAD_TO_HOST"))
    return out


class RH8OracleDemand(Policy):
    """StudyRH8 MIX-DEMAND verbatim. UPPER BOUND: it reads the demand labels."""

    name = "rh8-demand-aware-ORACLE"
    case = "A"
    experiments = ('B-recall',)
    paper = "StudyRH8 (ours), reports/study_rh8_demand_aware_warm_state.md"
    reads_future = True
    decides = ("session_action",)
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "recall_decision",
                     "representation", "order")

    def __init__(self, high_demand_sessions: Optional[Sequence[str]] = None) -> None:
        self.high = set(high_demand_sessions or ())

    def decide(self, obs: Observation) -> Action:
        sessions = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                          | {q.session_id for q in obs.recall})
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
                      sessions=_warm_actions(
                          sessions, self.high & set(sessions),
                          already_gpu=obs.cloud.gpu_warm_sessions,
                          tokens={q.session_id: q.readiness_tokens for q in obs.recall}))


class RH8CausalDemand(Policy):
    """The deployable reading: demand ESTIMATED from each session's own observed history.

    StudyRH8 did not measure this, and it is not a reproduction of any RH8 number.
    """

    name = "rh8-demand-aware-causal"
    case = "A"
    experiments = ('B-recall',)
    paper = "StudyRH8 (ours), adapted to a causal demand estimate"
    decides = ("session_action",)
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "recall_decision",
                     "representation", "order")

    def __init__(self, high_frac: float = HIGH_FRAC, half_life_s: float = 60.0) -> None:
        self.high_frac = float(high_frac)
        self.half_life_s = float(half_life_s)
        self._count: Dict[str, float] = defaultdict(float)
        self._last_s: Dict[str, float] = {}

    def reset(self, seed: int = 0) -> None:
        self._count.clear()
        self._last_s.clear()

    def _observe(self, obs: Observation) -> None:
        """An exponentially decayed count of each session's own past recall arrivals - the only
        demand signal a scheduler could actually have."""
        for q in obs.recall:
            last = self._last_s.get(q.session_id)
            if last is not None and self.half_life_s > 0:
                decay = 0.5 ** ((obs.now_s - last) / self.half_life_s)
                self._count[q.session_id] *= decay
            self._count[q.session_id] += 1.0
            self._last_s[q.session_id] = obs.now_s

    def decide(self, obs: Observation) -> Action:
        self._observe(obs)
        sessions = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                          | {q.session_id for q in obs.recall})
        k = max(int(round(self.high_frac * len(sessions))), 0)
        ranked = sorted(sessions, key=lambda s: -self._count.get(s, 0.0))
        warm = set(ranked[:k])
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
                      sessions=_warm_actions(
                          sessions, warm, already_gpu=obs.cloud.gpu_warm_sessions,
                          tokens={q.session_id: q.readiness_tokens for q in obs.recall}))
