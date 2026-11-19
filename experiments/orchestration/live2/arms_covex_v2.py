#!/usr/bin/env python3
"""covex-v2: rollout over the strongest baseline, with a margin that bounds the downside.

THE DESIGN AND WHY IT IS SHAPED THIS WAY. Three nights of evidence say COVEX's DeltaJ machinery is
unreliable in specific, documented ways: the RC deficit reaches a decision in 1 of 14,721
counterfactual calls, the state value cancels exactly, the price was mispriced and then saturated,
and `p_finish` is a saturated indicator at `competing_s = 0`. A policy that acts on DeltaJ alone
inherits every one of those faults. A policy that EXECUTES A STRONG BASELINE and deviates only when
DeltaJ clears a margin inherits them only where the margin admits them.

The guarantee is the point:

    margin = infinity  =>  covex-v2 is BYTE-IDENTICAL to its base.

That makes "COVEX cannot do worse than the best baseline" a STRUCTURAL property rather than an
empirical hope, and it is proved before any margin is swept.

WHAT pi_0 BECOMES. Every DeltaJ in this system is a counterfactual against pi_0, and here pi_0 is
THE BASE rather than EDF. No calibration intuition from v1.x transfers.

EXPRESSIBILITY, which constrains the alternative set. `live2/coordinator.py` contains no reference
to the action `order` field, so a deviation expressed solely as a REORDERING is a no-op by
construction and would read as "deviation fired, nothing changed". Every alternative here therefore
changes a field the coordinator actually reads: `RecallAction.decision` and `StreamAction`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from interface import Action, Observation, RecallAction

INF = float("inf")


class CovexV2Arm:
    """Executes `base` and deviates only where DeltaJ clears `margin`."""

    name = "covex-v2"

    def __init__(self, base: str = "b7-edf-feasibility", margin: float = INF,
                 base_kwargs: Optional[Dict[str, Any]] = None,
                 scorer_kwargs: Optional[Dict[str, Any]] = None) -> None:
        import arms as A
        self.base_name = str(base)
        self.base = A.make_arm(self.base_name, **(base_kwargs or {}))
        self.margin = float(margin)
        self._scorer_kwargs = dict(scorer_kwargs or {})
        self._scorer = None
        # Deviations BY KIND with their realised effect, which is the scientific output even if
        # the aggregate does not win.
        self.deviations: Dict[str, int] = {}
        self.considered: Dict[str, int] = {}
        self.stats: Dict[str, Any] = dict(arm=self.name, base=self.base_name,
                                          margin=self.margin)

    # ---------------------------------------------------------------- plumbing by delegation
    def reset(self, seed: int = 0) -> None:
        self.base.reset(seed)
        if self._scorer is not None:
            self._scorer.reset(seed)
        self.deviations, self.considered = {}, {}

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        if hasattr(self.base, "live2_roster"):
            self.base.live2_roster(roster)
        if self._scorer is not None and hasattr(self._scorer, "live2_roster"):
            self._scorer.live2_roster(roster)

    def live2_configure(self, **kw: Any) -> None:
        if hasattr(self.base, "live2_configure"):
            self.base.live2_configure(**kw)
        if self.margin < INF:
            # The scorer is a policy-core arm used ONLY for its rollout and DeltaJ machinery; its
            # own decisions are never executed. It is built only when a finite margin could
            # actually admit a deviation, so the infinite-margin path cannot differ from the base
            # through a side effect of constructing it.
            import arms as A
            self._scorer = A.make_arm("policy-core", **self._scorer_kwargs)
            self._scorer.live2_configure(**kw)

    def describe(self) -> Dict[str, Any]:
        d = dict(self.stats)
        d["deviations_by_kind"] = dict(self.deviations)
        d["considered_by_kind"] = dict(self.considered)
        return d

    # ---------------------------------------------------------------- the decision
    def decide(self, obs: Observation) -> Action:
        act = self.base.decide(obs)
        if self.margin >= INF or self._scorer is None:
            # No deviation can clear an infinite margin, so the base action stands UNTOUCHED.
            # This is the byte-identity guarantee and it is a property of the comparison, not a
            # special case: the loop below would also return `act` unchanged.
            return act
        return self._maybe_deviate(obs, act)

    def _maybe_deviate(self, obs: Observation, act: Action) -> Action:
        """Consider one alternative per recall decision: the opposite of what the base chose.

        Only `RecallAction.decision` is changed, which the coordinator reads. The DeltaJ of each
        alternative is scored against the base action under the SAME rollout, so the comparison is
        `DeltaJ(alternative) - DeltaJ(base action)`.
        """
        scored = self._score_recall(obs, act)
        if not scored:
            return act
        out: List[RecallAction] = []
        changed = False
        for r in act.recall:
            gain = scored.get(r.query_id)
            kind = "recall:%s->%s" % (r.decision, "DEVICE" if r.decision == "CLOUD" else "CLOUD")
            if gain is not None:
                self.considered[kind] = self.considered.get(kind, 0) + 1
            if gain is not None and gain > self.margin:
                self.deviations[kind] = self.deviations.get(kind, 0) + 1
                alt = "DEVICE" if r.decision == "CLOUD" else "CLOUD"
                out.append(RecallAction(r.query_id, alt,
                                        representation=("D2" if alt == "CLOUD" else None)))
                changed = True
            else:
                out.append(r)
        if not changed:
            return act
        return Action(streams=act.streams, recall=out, sessions=act.sessions,
                      order=act.order, notes=dict(getattr(act, "notes", None) or {},
                                                  arm=self.name, deviated=True))

    def _score_recall(self, obs: Observation, act: Action) -> Dict[str, float]:
        """DeltaJ(alternative) - DeltaJ(base) per recall query, from the scorer's own machinery.

        Returns an empty dict when the scorer cannot produce a comparable pair, which is reported
        as "no alternative scored" rather than as a zero gain, so an unscored decision is never
        mistaken for one that scored zero.
        """
        try:
            self._scorer.live2_roster(getattr(self.base, "_live2_roster", None) or {})
        except Exception:
            pass
        try:
            self._scorer.decide(obs)
        except Exception:
            return {}
        pred = getattr(self._scorer, "last_predictions", None) or {}
        dj = pred.get("delta_j") or {}
        out: Dict[str, float] = {}
        for r in act.recall:
            v = dj.get("rc:" + str(r.query_id))
            if v is None:
                continue
            # The scorer's DeltaJ is the value of ADMITTING. A base CLOUD decision already takes
            # that value, so the gain from deviating to DEVICE is its negation.
            out[r.query_id] = (-float(v)) if r.decision == "CLOUD" else float(v)
        return out
