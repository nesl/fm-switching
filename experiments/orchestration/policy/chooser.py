"""D138 P1: the counterfactual chooser.

    choose(candidates, state) -> candidate

WHY THIS EXISTS, AND WHY IT IS NOT JUST ANOTHER HEURISTIC
---------------------------------------------------------
It is the first evaluator whose window is long enough for recall decisions to differ at all.

Measured this week: over **14,721 `delta_j` calls the RC z term differs in exactly 1**. The cause
is geometric rather than statistical. A recall answer lands **1 to 5 s** after its release, while
the dispatch horizon is **H = 0.5 s**, so the action and its reference produce the *identical* RC
outcome inside the window and every RC term cancels. The same geometry was confirmed from the
other side: the identical `z_term` is alive at 0.450000000 in the planner's long window and dead
in dispatch.

A fixed-H evaluator therefore cannot distinguish recall candidates **by construction**, however
good its utility model. Simulating each candidate **to its own deadline or completion** removes
that cancellation by construction. That is the justification for the cost this object carries, and
the cost is real: it runs one rollout per candidate, over a longer span than dispatch does.

WHAT IT DOES
------------
Given a SHORT candidate list proposed by the H100's components for one robot question (warm answer,
host reload, rebuild now, pieces, RECENT, decline) or for one retention change, it evaluates each
with the EXISTING rollout -- `Rollout.run`, unmodified -- over that candidate's own span, including
harm to others across that span, and returns the best. If none beats the proposed default by
margin `delta`, it returns the default.

Each candidate carries its own `rollout_kwargs`, which are passed to `Rollout.run` verbatim. The
chooser does not interpret what a candidate MEANS; the component proposing it does. That keeps this
object generic and keeps the semantics of "host reload" or "pieces" where they are already defined.

THE OFF SWITCH
--------------
`enabled=False` returns the proposed default and runs **zero** rollouts. It is a single switch
gating the whole change, not a reconstruction of the prior behaviour: with it off, `choose` returns
the very object it was handed, so anything downstream is byte-identical by identity rather than by
comparison. (Session 1 lost a 16-cell run to a control that was never the pre-change condition;
the rule drawn from it is to construct the control by disabling the change, not by approximating
its absence.)

DEVIATION MUST BE PROVED BEFORE ANY COMPARISON IS REPORTED
----------------------------------------------------------
A chooser that always returns the default passes every correctness test perfectly. This module
therefore counts deviations **by candidate kind** (`stats["deviations_by_kind"]`), and a report
that does not show at least one deviation has not shown the mechanism ran.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# A recall answer lands 1 to 5 s out; the dispatch horizon is 0.5 s. A candidate with no stated
# deadline is simulated at least this far, so it is never evaluated inside the window where the
# terms are known to cancel.
MIN_HORIZON_S = 5.0
# A guard so one malformed candidate cannot ask for an unbounded simulation.
MAX_HORIZON_S = 60.0


@dataclass(frozen=True)
class Candidate:
    """One option for a single decision.

    `kind` is the component's own label ("warm", "host_reload", "rebuild_now", "pieces", "recent",
    "decline", "retention"), used for reporting and never interpreted here.
    `rollout_kwargs` is passed to `Rollout.run` verbatim.
    `deadline_s` is ABSOLUTE. None means "no stated deadline": the candidate is simulated to
    `completion_s` if given, else to `MIN_HORIZON_S`.
    """
    kind: str
    rollout_kwargs: Dict[str, Any] = field(default_factory=dict)
    deadline_s: Optional[float] = None
    completion_s: Optional[float] = None
    label: str = ""


@dataclass
class ChooserState:
    """Everything the chooser needs, and nothing it should mutate."""
    rollout: Any                     # policy.rollout.Rollout
    fleet: Any                       # policy.state.Fleet
    now_s: float


@dataclass
class Chooser:
    delta: float = 0.0
    enabled: bool = True
    min_horizon_s: float = MIN_HORIZON_S
    max_horizon_s: float = MAX_HORIZON_S
    stats: Dict[str, Any] = field(default_factory=lambda: dict(
        calls=0, rollouts=0, deviations=0, defaults_kept=0,
        rollouts_per_call=[], latency_ms_per_call=[], deviations_by_kind={}))

    # ---- the horizon, which is the whole point
    def horizon_for(self, c: Candidate, now_s: float) -> float:
        """This candidate's OWN span: to its deadline, or to its completion, never a fixed H."""
        if c.deadline_s is not None:
            h = float(c.deadline_s) - float(now_s)
        elif c.completion_s is not None:
            h = float(c.completion_s) - float(now_s)
        else:
            h = self.min_horizon_s
        return max(self.min_horizon_s, min(float(h), self.max_horizon_s))

    def _score(self, c: Candidate, st: ChooserState) -> float:
        res = st.rollout.run(st.fleet, horizon_s=self.horizon_for(c, st.now_s),
                             **dict(c.rollout_kwargs))
        self.stats["rollouts"] += 1
        return float(res.total)

    def choose(self, candidates: Sequence[Candidate], state: ChooserState,
               default: Optional[Candidate] = None) -> Candidate:
        """Return the best candidate, or `default` if none beats it by `delta`.

        `default` defaults to `candidates[0]`, the component's proposal.
        """
        if not candidates:
            raise ValueError("choose() needs at least one candidate")
        dflt = default if default is not None else candidates[0]

        # THE OFF SWITCH: one branch, before any work, returning the handed-in object itself.
        if not self.enabled:
            return dflt

        t0 = time.perf_counter()
        self.stats["calls"] += 1
        before = self.stats["rollouts"]

        base = self._score(dflt, state)
        best, best_score = dflt, base
        for c in candidates:
            if c is dflt:
                continue
            s = self._score(c, state)
            if s > best_score:
                best, best_score = c, s

        chosen = best if (best is not dflt and (best_score - base) > self.delta) else dflt
        if chosen is not dflt:
            self.stats["deviations"] += 1
            k = self.stats["deviations_by_kind"]
            k[chosen.kind] = k.get(chosen.kind, 0) + 1
        else:
            self.stats["defaults_kept"] += 1

        self.stats["rollouts_per_call"].append(self.stats["rollouts"] - before)
        self.stats["latency_ms_per_call"].append((time.perf_counter() - t0) * 1000.0)
        return chosen


_DEFAULT = Chooser()


def choose(candidates: Sequence[Candidate], state: ChooserState,
           default: Optional[Candidate] = None) -> Candidate:
    """Module-level entry point with the directive's signature."""
    return _DEFAULT.choose(candidates, state, default=default)
