#!/usr/bin/env python3
"""covex-v2: rollout over the strongest baseline, with a margin that bounds the downside.

THE BASE IS `eco-llm`. It leads capacity (10 of 28 against 9 and 9 for mooncake and
b7-edf-feasibility) and leads the robot pool at every size where they differ (0.878 against 0.831
at 16 devices, 0.517 against 0.454 at 32). The other two lead only on dashcam, which is `D+` for
every arm at every size in the band and so does not affect the capacity conjunct at all: choosing a
base on dashcam would optimise the half of the objective that is already satisfied. The margin is
SMALL (10 cells against 9) and at 8 devices eco-llm is not a distinct policy, sitting in a
six-member collapsed class, so the base choice only has content at 10 devices and above. A v2
result at n=4 or n=8 is NOT a statement about beating eco-llm specifically.

THE DESIGN AND WHY IT IS SHAPED THIS WAY. Three nights of evidence say COVEX's DeltaJ machinery is
unreliable in specific, documented ways: the RC deficit reaches a decision in 1 of 14,721
counterfactual calls, the state value cancels exactly, the price was mispriced and then saturated,
and `p_finish` is a saturated indicator at `competing_s = 0`. A policy that acts on DeltaJ alone
inherits every one of those faults. A policy that EXECUTES A STRONG BASELINE and deviates only when
DeltaJ clears a margin inherits them only where the margin admits them.

The guarantee is the point:

    margin = infinity  =>  covex-v2 is BYTE-IDENTICAL to its base.

This holds for ANY base, BY CONSTRUCTION, because every attribute the coordinator reads is
mirrored onto the wrapper. That is a stronger claim than the one first proved, which held for
eco-llm partly through a coincidence of defaults.

That makes "COVEX cannot do worse than the best baseline" a STRUCTURAL property rather than an
empirical hope, and it is proved before any margin is swept.

WHAT pi_0 BECOMES. Every DeltaJ in this system is a counterfactual against pi_0, and here pi_0 is
THE BASE rather than EDF. No calibration intuition from v1.x transfers.

UNEXPRESSIBLE CHANNELS, which constrain the alternative set. Two fields cannot carry a deviation:

  `order`         `live2/coordinator.py` has no reference to it at all.
  `desired_tier`  three references in all of live2: one declaration and two WRITES, no READ. So
                  `KEEP_GPU_WARM` and `OFFLOAD_TO_HOST` are dispatched, counted and handled, and
                  change nothing. **keep-warm is therefore dropped from the alternative set.**

The lesson generalises and is applied to the classification pass: check whether a field is READ,
not whether it is REFERENCED. `order` has zero references and is visibly dead; `desired_tier`
passes a reference check and fails a read check.

EXPRESSIBILITY, which constrains the alternative set. `live2/coordinator.py` contains no reference
to the action `order` field, so a deviation expressed solely as a REORDERING is a no-op by
construction and would read as "deviation fired, nothing changed". Every alternative here therefore
changes a field the coordinator actually reads: `RecallAction.decision` and `StreamAction`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from interface import Action, Observation, Policy, RecallAction

INF = float("inf")


class CovexV2Arm(Policy):
    """Executes `base` and deviates only where DeltaJ clears `margin`."""

    name = "covex-v2"

    def __init__(self, base: str = "eco-llm", margin: float = INF,
                 base_kwargs: Optional[Dict[str, Any]] = None,
                 scorer_kwargs: Optional[Dict[str, Any]] = None) -> None:
        import arms as A
        self.base_name = str(base)
        self.base = A.make_arm(self.base_name, **(base_kwargs or {}))
        self.margin = float(margin)
        # The scorer must be configured to PRODUCE RC decisions, or it emits DeltaJ only for
        # dashcam targets and every recall alternative comes back UNSCORED. Measured: with default
        # kwargs the scorer's delta_j keys were all `dashNNN:` and not one `rc:` key existed, so a
        # reachability pass over it classified nothing. These are the v1.3 release switches.
        self._scorer_kwargs = dict(scorer_kwargs) if scorer_kwargs else dict(
            mu_mode="none", admit_floor_c=8, deficit_update=True, honour_job_priority=True,
            realistic_competing=True, planner_rc=True, plan_latest=True, replan=True)
        self._scorer = None
        self._roster: Dict[str, Any] = {}
        # Deviations BY KIND with their realised effect, which is the scientific output even if
        # the aggregate does not win.
        self.deviations: Dict[str, int] = {}
        self.considered: Dict[str, int] = {}
        self.stats: Dict[str, Any] = dict(arm=self.name, base=self.base_name,
                                          margin=self.margin)
        # MIRROR the base's declared policy attributes. The coordinator reads these, so a wrapper
        # that declared different ones would diverge from the base for reasons that have nothing
        # to do with the margin and would make the byte-identity proof meaningless.
        # EVERY attribute the coordinator READS must be mirrored, or the wrapper diverges from the
        # base for reasons unrelated to the margin. `uses_h` and `h_s` are read together at
        # `coordinator.py:124`:
        #     self.h_s = getattr(arm, "h_s", None) if getattr(arm, "uses_h", False) else None
        # The wrapper originally had NEITHER, so the coordinator fell back to the default False,
        # which happens to equal eco-llm's value. The byte-identity proof therefore passed partly
        # BY COINCIDENCE of defaults. It would have broken silently the moment the base had a
        # planning horizon: `policy-core` declares `uses_h = True` with `h_s = 1.0`, so a wrapper
        # around it would have had h_s None against the base's 1.0.
        for attr in ("reads_device_answer", "multi_instance_adapted", "releases_one_per_epoch",
                     "piece_tokens", "c_inflight", "uses_h", "h_s"):
            if hasattr(self.base, attr):
                setattr(self, attr, getattr(self.base, attr))

    # ---------------------------------------------------------------- plumbing by delegation
    def reset(self, seed: int = 0) -> None:
        self.base.reset(seed)
        if self._scorer is not None:
            self._scorer.reset(seed)
        self.deviations, self.considered = {}, {}

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        # KEEP IT OURSELVES. The roster is the channel through which policy-core learns the
        # EXECUTED state (built tokens per session, each SH instant's own deadline), so the
        # evaluator must receive the real one every period.
        self._roster = dict(roster or {})
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
        # D131 option 1, THE EVALUATOR MUST FOLLOW THE EXECUTED TRAJECTORY. This previously read
        # `getattr(self.base, "_live2_roster", None) or {}`, and `arms_published.py` defines no
        # `live2_roster` at all, so the base never stored one and the scorer's REAL roster was
        # overwritten with an empty dict every period. Measured consequence: `_jobs_by_q` stayed
        # at size 0 for all 2,999 epochs, no `rc:` DeltaJ was ever emitted, and every recall
        # alternative came back UNSCORED, which is not the same as scoring zero.
        try:
            self._scorer.live2_roster(dict(self._roster))
        except Exception:
            pass
        try:
            self._scorer.decide(obs)
        except Exception:
            return {}
        pred = getattr(self._scorer, "last_predictions", None) or {}
        dj = pred.get("delta_j") or {}
        # KEY FORMAT, established by inspecting the live keys rather than assuming. The scorer
        # keys DeltaJ by the DECISION TARGET, which for RC work is the planner's item id,
        # `<device>:<rep>:<t>:p<i>` (for example `robo002:RICH:39.300:p0`), and for state actions
        # `<device>:<rep>:PROMOTE_REBUILD:<t>`. It is NOT keyed by query id, so the earlier lookup
        # of `"rc:" + query_id` matched nothing and every alternative came back UNSCORED.
        #
        # A recall query carries `session_id`, which is the device, so the RC work for a query is
        # the set of target keys under that device prefix. The value of ADMITTING is their sum.
        # AGGREGATION, corrected. Summing EVERY target key under a device concentrated hundreds
        # of per-decision values into a near-constant: four queries whose histories spanned 5,431
        # to 10,831 tokens produced 0.054041, 0.054350, 0.054351 and 0.054991, agreeing to three
        # significant figures. That is CLAUDE.md check 3, a constant where a distribution is
        # expected, and it was MY estimator rather than saturation in the policy: the underlying
        # per-decision values discriminate perfectly well, with 186 distinct admit values and 388
        # distinct dispatch values over one cell.
        #
        # So take the PLAN decision for this device, which is the decision actually being
        # considered, rather than a sum over everything the device touched. `decisions` carries
        # the kind alongside the target, which the flat `delta_j` map does not.
        decs = pred.get("decisions") or []
        by_device: Dict[str, float] = {}
        for d in decs:
            # The RC decision is logged with kind "plan", not "admit": over one cell the kinds
            # are escalation 2,647 (dashcam), release 2,878, state_action 8,174, feasibility 57,
            # and plan 10 - exactly the number of recall queries in the cell.
            if str(d.get("kind")) != "plan":
                continue
            v = d.get("delta_j")
            if v is None:
                continue
            # A PLAN target is the bare device (`robo002`), with NO colon. An earlier filter
            # required one and silently skipped every plan decision, which is a fourth way this
            # estimator produced UNSCORED where a value existed.
            key = str(d.get("target") or "")
            if not key:
                continue
            dev = key.split(":", 1)[0]
            # Keep the LARGEST-magnitude admit value for the device, which is the one that would
            # drive the decision, rather than a sum that averages distinct decisions together.
            if dev not in by_device or abs(float(v)) > abs(by_device[dev]):
                by_device[dev] = float(v)
        out: Dict[str, float] = {}
        for r in act.recall:
            sid = None
            for q in getattr(obs, "recall", ()) or ():
                if q.query_id == r.query_id:
                    # A session id is `<device>|<slot>|<clip>`, for example
                    # `robo002|s000|1813544496258929_start_0.0_end_307.914`, while a DeltaJ target
                    # is keyed by the DEVICE alone. Matching the full session id found nothing.
                    sid = str(q.session_id).split("|", 1)[0]
                    break
            if sid is None or sid not in by_device:
                continue
            v = by_device[sid]
            # The scorer's DeltaJ is the value of ADMITTING. A base CLOUD decision already takes
            # that value, so the gain from deviating to DEVICE is its negation.
            out[r.query_id] = (-float(v)) if r.decision == "CLOUD" else float(v)
        return out
