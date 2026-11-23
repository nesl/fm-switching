#!/usr/bin/env python3
"""THE v5 COUNTERFACTUAL PLANNER: three decision kinds, their candidate sets, their horizons, the
latest-safe-start deferral, and the margin that lets it deviate from base (D151, D152, D154, D155).
CPU only. No GPU, no engine, no coordinator, no live run.

HOW IT IS SHAPED, in the order a reader needs it.

1. THE BASE IS EXECUTED BY DEFAULT (D151 (1), D152 (2), D154 (3)). `plan_*` always computes the
   base policy's choice first, and the counterfactual's choice is taken ONLY if its predicted
   objective beats the base's by `cf_margin.MARGIN_CF`. So the planner is never worse than
   `hybrid-F-lhreq-noc3` up to cost-model error, which is the property D151 (1) buys, and the
   margin is what pays for it. `Decision.chosen` is the base's choice unless `deviated` is true.

2. THE MARGIN COMES FROM ONE DECLARED CONSTANT and nothing else (`cf_margin`). No function here
   takes a margin argument on its scorable path, and the constant is UNSET, so every scorable
   decision RAISES `MarginUnset` today. That is not a defect: D154 (2) sets the value only when
   the cost-model gate passes, the gate fails, and spec v5 section 12.1 says v5 does not run
   before it is ruled. The planner enforces that rather than documenting it.

3. THREE KINDS ARE COUNTERFACTUAL AND TWO ARE NOT (D151 (2)). `request` (robot questions),
   `state` and `sync` are planned. A dashcam frame and a single-shot request are RULE-BASED and
   `plan()` REFUSES them, returning a `RuleBased` marker that names the rule's owner. The refusal
   is the mechanism: D151 (5)'s 20 ms budget is affordable only because the counterfactual is not
   asked to rank 13,193 monitor instants.

4. DECODE IS IN THE PREDICTED SERVICE (spec v5 section 5.2). The base's own feasibility test is
   prefill-only, exactly as the committed `B7EDFFeasibility.decide` and `hybrid_arm` compute it
   (`costs.recall_ttft_s`), and the counterfactual's is first token PLUS DECODE plus link from the
   committed gate model. The two differ by construction, which is one of the places a deviation
   can come from, and `Decision.trace` carries both so a reader can see which.

5. D155 (4) IS IMPOSED, NOT DERIVED. "No RECENT for long-horizon questions" was a consequence of
   the D87 table, where cloud RECENT and the device tied exactly. The measured Orin entry
   (0.071429, StudyORIN-REC part 1) breaks the tie, so the arithmetic would now send RECENT when
   it is more than about two-thirds likely to arrive. D155 (4) rules that the rule STAYS and is
   imposed explicitly. `IMPOSED_NO_RECENT_FOR_LH` does that, and
   `Counterfactual.counts["recent_suppressed_by_rule"]` counts every decision where the
   arithmetic would have chosen RECENT and the rule overrode it, so the imposition is auditable
   and not invisible.

6. THE PLANNER TIMES OUT TO BASE, WITH A COUNTER (spec v5 section 10). The budget is checked at
   candidate boundaries; on overrun the planner abandons and returns the base's choice with
   `timeout_fallback=True`. The fallback target is `hybrid-F-lhreq-noc3` and never C3-on
   hybrid-F, because a timeout must not re-enable a representation shortcut D152 (2) rules out.

WHAT IS A SURROGATE HERE, MARKED AT THE POINT OF USE. `base_request_choice` reimplements the
committed base's robot-request rule (b7's feasibility test with `defer_s = 0.5`, C3 off) from the
committed source, in this module, because the real arm needs a coordinator and an engine and this
module runs on a CPU with neither. It is a SURROGATE. Its agreement with `hybrid_arm` on real
observations is not proved here and must be proved by the session that owns `hybrid_arm` before
any cell is scored; `BASE_SURROGATE_NOTE` says so and `cf_proofs` reports it as an open item.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(REPO / "experiments/orchestration/live2"),
           str(REPO / "experiments/orchestration/live2/fleet"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.append(_p)

import cf_cost as CC                                                           # noqa: E402
import cf_margin as CM                                                         # noqa: E402

# D171 (1): THE MODEL-ERROR CHECK IS WEIGHTED BY THE DEFICIT WEIGHT OF THE DEVICE THE DECISION IS
# ABOUT. `deviate iff (value_cf - value_base) > w_d * MARGIN_CF`. The reason is a units one and it
# is the finding the d5d12dfc audit raised: `option_value` multiplies the GAIN by `w_d`, so a
# device at w = 2 doubles every gain it reports, and against a FIXED margin it would clear the
# model-error bar at half the true gain. MARGIN_CF was measured UNWEIGHTED, per question, so the
# weight must appear on both sides or on neither. The deficit weights keep their other two roles
# untouched (ranking candidates, and the harm term): what they must not do is loosen the check
# that exists to stop the counterfactual acting inside its own prediction error.
#
# With every w = 1 this is arithmetically the current rule, and `d171_proofs.py::P1` proves the
# decision logs byte-identical on today's dry cells. The switch exists so that equality is
# DEMONSTRATED by running both, not asserted from the algebra.
MARGIN_WEIGHTED_BY_DEFICIT = True

# D177 (1), THE CURRENCY. Every value this planner compares is a count of expected ON-TIME CLOUD
# ANSWERS: `cf_objective.option_value` is `w * p`, `device_only_value` is 0.0, `plan_state`'s gain
# carries NO accuracy factor, and the margin is read through `cf_objective.attainment_margin`. The
# conversion landed in ONE commit with `cf_objective` because a half-converted planner would
# subtract on-time-unit harm from correctness-unit gain, which is the error D177 exists to
# prevent; `cf_objective.CURRENCY_FLIP_STATUS` holds the measured magnitudes.
#
# WHAT STILL READS THE QUALITY TABLE, so that nobody looks for a removal that is not here. The
# table is loaded and REPORTED (D177 (2) makes it reporting only): `self.table` fills the
# `accuracy_table` trace field and each candidate's `accuracy` detail, and the accuracy arguments
# are still passed to `cf_objective`, which no longer reads them. No value in this module
# multiplies by an accuracy.
VALUE_UNITS = "expected on-time cloud answers (D177 (1))"
MARGIN_UNITS = "expected on-time cloud answers; MARGIN_CF / A_D2_DEV = 0.65824 (D177 (3))"

# D171 (2): the harm term prices each displaced request's OWN device answer as its fallback, the
# same replacement semantics D165 (B) gives the gain side. OFF reproduces the pre-D171 term, which
# passed `acc_dev = 0.0` and so charged a displaced request its FULL cloud accuracy. The switch is
# what makes the A/B a Step 2b diff instead of an assertion about algebra.
HARM_REPLACEMENT_SEMANTICS = True


def effective_margin(margin_value: float, weight: float) -> float:
    """The bar a deviation must clear: `w_d * MARGIN_CF` (D171 (1)), or the bare margin if the
    switch is off. One function, so the three decision kinds cannot drift apart."""
    return float(margin_value) * (float(weight) if MARGIN_WEIGHTED_BY_DEFICIT else 1.0)
import cf_objective as CO                                                      # noqa: E402
from cf_instrument import DecisionClock, BUDGET_MS                             # noqa: E402

try:
    import costs as COSTS                                                      # noqa: E402
    COSTS_AVAILABLE = True
except Exception:                                                              # noqa: BLE001
    COSTS_AVAILABLE = False

# The engine-side action space (session C, `engine_actions.py`). Imported for ONE purpose: to ask
# whether a warm candidate is EXPRESSIBLE before scoring it. The interface note's first point is
# that `plan_warm_ahead` returns what it WANTED as well as what it may legally say, and that
# scoring `n_warm_ahead` alone reads a harness blocker as a policy decision.
try:
    import engine_actions as EA                                                # noqa: E402
    ENGINE_ACTIONS_AVAILABLE = True
    ENGINE_ACTIONS_VERSION = getattr(EA, "ENGINE_ACTIONS_VERSION", "unknown")
except Exception:                                                              # noqa: BLE001
    EA = None                                                                  # type: ignore
    ENGINE_ACTIONS_AVAILABLE = False
    ENGINE_ACTIONS_VERSION = "unavailable"

BASE_POLICY = "hybrid-F-lhreq-noc3"
BASE_DEFER_S = 0.5               # committed `B7EDFFeasibility.__init__(defer_s=0.5)`
BASE_SURROGATE_NOTE = (
    "base_request_choice is a SURROGATE for hybrid-F-lhreq-noc3's robot-request rule, written "
    "from the committed source (baselines/constructed.py::B7EDFFeasibility.decide and "
    "hybrid/hybrid_arm.py::HybridArm.decide with c3 off): CLOUD if the prefill-only estimate fits "
    "the slack, DEFER by 0.5 s if it fits slack + 0.5, else the device answers. Its agreement "
    "with the real arm on real observations is NOT proved here and must be proved by the owner of "
    "hybrid_arm.py before any cell is scored.")

# D155 (4): a USER RULE, imposed in the planner, documented as imposed and not derived.
IMPOSED_NO_RECENT_FOR_LH = True
IMPOSED_NO_RECENT_NOTE = (
    "D155 (4): no RECENT for long-horizon questions, IMPOSED. Under the superseded D87 device "
    "entry (0.107143) this fell out of the arithmetic because cloud RECENT tied the device and "
    "ties go to the device. The measured Orin entry (0.071429, StudyORIN-REC part 1) breaks the "
    "tie, so the arithmetic alone would send RECENT above P(on time) about 0.667. D155 (4) keeps "
    "the rule and requires it be imposed explicitly. Every override is counted.")

DECISION_KINDS = ("request", "state", "sync")
RULE_BASED_KINDS = {
    "dashcam_frame": "rule-based (D151 (2)): the C5 cap, episode continuity and the deficit "
                     "counters decide it; owned by the arm, not the counterfactual",
    "single_shot": "rule-based (D151 (2)): feasibility only; owned by the arm",
}

# Candidate sets, per decision kind. Four for a request, and no others (spec v5 section 5.1).
REQUEST_CANDIDATES = ("ADMIT_NOW_D2", "DEFER_TO_LATEST_SAFE_START", "SEND_RECENT", "DEVICE_ANSWERS")
STATE_CANDIDATES = ("WARM", "TOUCH", "KEEP", "RELOAD", "HOLD_BACK", "SLICE")
SYNC_CANDIDATES = ("QUESTION_FIRST", "WAIT", "LEAVE_TO_DEVICE")

# Horizons, per decision kind (spec v5 section 5.3, D151 (4)).
HORIZONS = {
    "request": "its own deadline plus the deadlines it displaces",
    "state": "until the history's next likely question, capped %.0f s (range %s)" % (
        CC.HORIZON_WARM_CAP_S, CC.HORIZON_WARM_CAP_RANGE),
    "sync": "until caught up",
}

# EP-G episode tokens, used only when a trace record does not carry a token count itself. The
# formula is the committed one (`reports/policy_v5_assessment.md` section E: 338 tokens per frame
# plus about 42 of text, verified against 3,895 of 3,898 EP-G instants at deviation 0).
EPG_TOKENS_PER_FRAME = 338
EPG_TEXT_TOKENS = 42


# ---------------------------------------------------------------------------
# Reading the episode frame list from the trace record (never reconstructing it)


EPISODE_FRAME_FIELDS = ("episode_frame_refs", "frame_refs", "episode_frames", "frames")


def episode_frames_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The episode's frame list AS THE TRACE RECORD CARRIES IT.

    The EP-G dashcam bodies (D153) are being wired into `bodies.py` and `fleet/trace.py` by
    another session as this is written, so this reads whichever list field the record presents and
    NEVER rebuilds the list from a cap, a cadence or a clock. A record carrying a single
    `frame_ref` is a `dashcam-1f` record (D153's labelling ruling) and is labelled as such rather
    than being padded out to an episode.
    """
    for f in EPISODE_FRAME_FIELDS:
        v = rec.get(f)
        if isinstance(v, (list, tuple)) and v:
            return {"frames": list(v), "n_frames": len(v), "source_field": f,
                    "format": "episode", "label": "EP-G" if len(v) > 1 else "dashcam-1f"}
    one = rec.get("frame_ref")
    if one:
        return {"frames": [one], "n_frames": 1, "source_field": "frame_ref",
                "format": "single_frame", "label": "dashcam-1f"}
    return {"frames": [], "n_frames": 0, "source_field": None, "format": "none",
            "label": "unknown"}


def episode_tokens_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Prompt tokens for a dashcam request, PREFERRING the record's own count."""
    for f in ("prompt_tokens", "est_tokens", "cum_tokens"):
        v = rec.get(f)
        if isinstance(v, (int, float)) and v > 0:
            return {"tokens": int(v), "source": f, "derived": False}
    fr = episode_frames_from_record(rec)
    return {"tokens": EPG_TOKENS_PER_FRAME * fr["n_frames"] + EPG_TEXT_TOKENS,
            "source": "declared formula 338 x frames + 42 text", "derived": True,
            "n_frames": fr["n_frames"]}


# ---------------------------------------------------------------------------
# The decision record



def note_abandon(stats: Any, d: Any, budget_ms: float) -> None:
    """Record one planner decision and whether the TIME LIMIT abandoned it to base.

    User ruling 2026-11-22: the limit is proved with OFF (so a digest is a property of the arm)
    and RUN with ON (D99 (3): it is a real cost of the policy), and every live cell of rung 2 and
    up must carry the count and fraction of decisions abandoned to base BY DECISION KIND, plus
    the budget_ms in force, with any cell above 1 percent flagged.

    WHY IT HAS TO BE COUNTED PER CELL AND NOT ASSUMED FROM A DRY RUN. `over_budget` compares
    elapsed `perf_counter_ns` against `budget_ms`, so the rate is a property of the MACHINE as
    much as of the policy: three dry runs of covex-v6-state on one cell gave 15,734, 15,954 and
    15,935 decision rows with no code change. The H100's host CPU is about 2.2x slower than
    flash on the committed policy benchmark (D115 (1)), so flash's rate is a LOWER BOUND on the
    rate the live cells will show and must never be quoted for them.
    """
    kind = str(getattr(d, "kind", "unknown") or "unknown")
    stats["cf_planner_decisions"] += 1
    stats["cf_planner_decisions_" + kind] += 1
    if bool(getattr(d, "timeout_fallback", False)):
        stats["cf_timeout_abandons"] += 1
        stats["cf_timeout_abandons_" + kind] += 1
    stats["cf_budget_ms"] = float(budget_ms)


@dataclass
class Candidate:
    name: str
    value: Optional[float] = None
    gain: Optional[float] = None
    harm: Optional[float] = None
    expressible: bool = True
    scored: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name,
                "value": (None if self.value is None else round(self.value, 9)),
                "gain": (None if self.gain is None else round(self.gain, 9)),
                "harm": (None if self.harm is None else round(self.harm, 9)),
                "expressible": self.expressible, "scored": self.scored,
                "detail": self.detail}


@dataclass
class Decision:
    kind: str
    decision_id: str
    device_id: str
    chosen: str
    base_choice: str
    cf_choice: str
    deviated: bool
    value_base: Optional[float]
    value_cf: Optional[float]
    delta: Optional[float]
    margin: Optional[float]
    margin_source: str
    scorable: bool
    timeout_fallback: bool
    elapsed_ms: float
    margin_effective: Optional[float] = None    # D171 (1): w_d * MARGIN_CF, the bar actually used
    candidates: List[Candidate] = field(default_factory=list)
    trace: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "decision_id": self.decision_id, "device_id": self.device_id,
                "chosen": self.chosen, "base_choice": self.base_choice,
                "cf_choice": self.cf_choice, "deviated": self.deviated,
                "value_base": (None if self.value_base is None else round(self.value_base, 9)),
                "value_cf": (None if self.value_cf is None else round(self.value_cf, 9)),
                "delta": (None if self.delta is None else round(self.delta, 9)),
                "margin": self.margin, "margin_source": self.margin_source,
                "margin_effective": (None if self.margin_effective is None
                                     else round(self.margin_effective, 9)),
                "scorable": self.scorable, "timeout_fallback": self.timeout_fallback,
                "elapsed_ms": round(self.elapsed_ms, 6),
                "candidates": [c.as_dict() for c in self.candidates],
                "trace": self.trace}


@dataclass(frozen=True)
class RuleBased:
    kind: str
    reason: str
    counterfactual_refused: bool = True


# ---------------------------------------------------------------------------
# The base policy's own choices (SURROGATE, see BASE_SURROGATE_NOTE)


def base_prefill_only_estimate_s(tokens: int, readiness: str) -> float:
    """The base's own service estimate: `costs.recall_ttft_s`, prefill only, no decode.

    Reproduced faithfully INCLUDING the omission, because the omission is one of the things the
    counterfactual's deviation can come from (spec v5 section 5.2) and a base given decode for
    free would make v5's advantage disappear into a corrected baseline.
    """
    if not COSTS_AVAILABLE:
        raise RuntimeError("baselines/costs.py is not importable; the base surrogate needs it")
    return float(COSTS.recall_ttft_s(max(int(tokens), 1), readiness))


def base_request_choice(tokens: int, readiness: str, slack_s: float,
                        defer_s: float = BASE_DEFER_S) -> Dict[str, Any]:
    """hybrid-F-lhreq-noc3's robot-request decision. C3 is OFF, so RECENT is never a candidate."""
    est = base_prefill_only_estimate_s(tokens, readiness)
    if est <= slack_s:
        choice = "ADMIT_NOW_D2"
    elif est <= slack_s + float(defer_s):
        choice = "DEFER_TO_LATEST_SAFE_START"
    else:
        choice = "DEVICE_ANSWERS"
    return {"choice": choice, "prefill_only_estimate_s": round(est, 6),
            "slack_s": round(float(slack_s), 6), "defer_s": float(defer_s),
            "c3": "OFF (D154 (3)): RECENT is not in the base's candidate set",
            "surrogate": True, "surrogate_note": BASE_SURROGATE_NOTE}


# ---------------------------------------------------------------------------
# The planner


class Counterfactual:
    """The counterfactual engine. One instance per run; it holds the committed model, the residual
    distribution, the deficit counters and the clock, and plans one decision at a time."""

    def __init__(self, *, model: Optional[Dict[str, Any]] = None,
                 residuals: Optional[Dict[str, Any]] = None,
                 counters: Optional[CO.DeficitCounters] = None,
                 accuracy_table: Optional[Dict[str, Any]] = None,
                 safety: Optional[float] = None,
                 clock: Optional[DecisionClock] = None,
                 budget_ms: float = BUDGET_MS,
                 dry: bool = False, dry_margin: Optional[float] = None) -> None:
        self.model = model if model is not None else CC.load_gate_model()
        self.residuals = residuals if residuals is not None else CC.load_residuals()
        self.counters = counters if counters is not None else CO.DeficitCounters()
        if accuracy_table is None:
            sys.path.append(str(HERE))
            import value_readers as VR                                         # noqa: PLC0415
            accuracy_table = VR.load_dev_table()
        self.table = accuracy_table
        if safety is None:
            safety = CM.safety_factor(self.residuals)["safety_factor"]
        self.safety = float(safety)
        self.clock = clock if clock is not None else DecisionClock()
        self.budget_ms = float(budget_ms)
        self.dry = bool(dry)
        self.dry_margin = dry_margin
        self.log: List[Decision] = []
        self.counts: Dict[str, int] = {
            "decisions": 0, "request": 0, "state": 0, "sync": 0,
            "rule_based_refused": 0, "deviations": 0, "timeout_fallback": 0,
            "recent_suppressed_by_rule": 0, "deferrals_chosen": 0,
            "warm_unexpressible": 0, "harm_nonzero": 0, "replans": 0,
        }

    # ---- the margin, read exactly once per decision

    def _margin(self) -> CM.Margin:
        """The deviation bar, IN ON-TIME UNITS (D177 (3)), read exactly once per decision.

        `cf_margin.MARGIN_CF` stays the one declared constant and stays in the units it was
        MEASURED in (0.16456, correctness; `cf_margin.resolve_margin` is still its only read).
        D177 (3) restates it as 0.65824 on-time answers, which is that constant divided by the
        committed `A_D2_DEV = 0.250` that used to scale both gain and margin, and
        `cf_objective.attainment_margin` is the one function that does that division. So no second
        literal is declared anywhere and the conversion cannot drift from `cf_protect_defer`'s,
        which calls the same function.

        THE DRY PATH IS CONVERTED TOO, deliberately. A dry margin is the caller's explicit bar and
        a dry proof is a proof about the code, never a result about the policy, but a dry bar that
        skipped the conversion would sit at a quarter of the scorable one and a dry proof would
        then test a comparison no cell can make. Every dry caller in the tree passes either the
        committed MARGIN_CF (`v5/d171_proofs.py`) or an extreme (1e9, 0.0), and both read the same
        before and after the conversion.
        """
        m = CM.resolve_margin(dry=self.dry, dry_value=self.dry_margin)
        return CM.Margin(CO.attainment_margin(m.value),
                         m.source + " / cf_objective.A_D2_DEV (D177 (3): on-time units)",
                         m.scorable)

    # ---- dispatch

    def plan(self, kind: str, **kw: Any) -> Any:
        if kind in RULE_BASED_KINDS:
            self.counts["rule_based_refused"] += 1
            return RuleBased(kind, RULE_BASED_KINDS[kind])
        if kind == "request":
            return self.plan_request(**kw)
        if kind == "state":
            return self.plan_state(**kw)
        if kind == "sync":
            return self.plan_sync(**kw)
        raise ValueError("unknown decision kind %r; counterfactual kinds are %s and the rule-based "
                         "kinds are %s" % (kind, DECISION_KINDS, sorted(RULE_BASED_KINDS)))

    # ---- request decisions (D151 (3), spec v5 sections 5.1 to 5.5)

    def plan_request(self, *, decision_id: str, device_id: str, now_s: float,
                     deadline_abs_s: float, history_tokens: int, cached_tokens: int = 0,
                     readiness: str = "COLD", recent_tokens: int = 467,
                     others: Sequence[CC.PendingRequest] = (),
                     coarse_overlap_forecast: float = 0.0,
                     question_id: Optional[str] = None, kind: str = "robot",
                     episode_frames: Optional[int] = None) -> Decision:
        """Admit now with full history, defer to the latest safe start, send RECENT, or let the
        device answer. Four candidates and no others (spec v5 section 5.1)."""
        m = self._margin()
        acc = {"D2": float(self.table["cloud_D2"]), "RECENT": float(self.table["cloud_RECENT"]),
               "DEVICE": float(self.table["device"])}
        w = self.counters.weight(device_id)
        m_eff = effective_margin(m.value, w)
        dl_s = float(deadline_abs_s) - float(now_s)
        dev_wait_s = CO.device_wait_s(kind=kind, question_id=question_id,
                                      episode_frames=episode_frames)
        p_dev = CO.p_device_on_time(dl_s, dev_wait_s)
        base = base_request_choice(history_tokens, readiness, dl_s)
        cands: List[Candidate] = []
        timed_out = False

        with self.clock.time_decision("request", decision_id=decision_id, device_id=device_id,
                                      n_candidates=len(REQUEST_CANDIDATES)) as t:
            # the horizon: its own deadline plus the deadlines it displaces (spec v5 section 5.3)
            displaced = [r for r in others if r.deadline_abs_s != math.inf]
            horizon_abs_s = max([float(deadline_abs_s)] + [r.deadline_abs_s for r in displaced])
            exact_until_s = horizon_abs_s          # NEAR_EXACT_S["request"] is None: the horizon

            def _queue(start_s: Optional[float], tokens: Optional[int],
                       cached: int = 0) -> CC.QueuePlan:
                rs = list(others)
                if start_s is not None and tokens is not None:
                    rs = rs + [CC.PendingRequest(
                        req_id=decision_id, device_id=device_id, start_s=float(start_s),
                        tokens=int(tokens), cached_tokens=int(cached),
                        deadline_abs_s=float(deadline_abs_s), accuracy=0.0, weight=w,
                        kind=kind, question_id=question_id, episode_frames=episode_frames,
                        is_candidate=True)]
                return CC.plan_queue(self.model, self.residuals, rs, now_s=now_s,
                                     exact_until_s=exact_until_s, decision_kind="request",
                                     coarse_overlap_forecast=coarse_overlap_forecast)

            before = _queue(None, None)

            def _score(name: str, start_s: float, tokens: int, cached: int,
                       accuracy: float) -> Candidate:
                after = _queue(start_s, tokens, cached)
                mine = after.by_id()[decision_id]
                # REGISTER, AT THE POINT OF USE (D177 (1)): `accuracy`, `p_dev` and `acc["DEVICE"]`
                # are still passed and are REPORTING ONLY; `option_value` is `w * p` and the harm
                # rows are `w * (p_before - p_after)`, both counts of on-time cloud answers. The
                # `HARM_REPLACEMENT_SEMANTICS` branch therefore selects between two arguments that
                # no value reads: the switch is INERT under this currency, by the arithmetic in
                # `cf_objective.harm_to_others`, and it is left standing rather than removed
                # because the ruling it implements (D171 (2)) is still the reason the harm is a
                # probability difference. A reader must not take its presence for a live lever.
                harm = CO.harm_to_others(before, after, candidate_req_id=decision_id,
                                         counters=self.counters,
                                         acc_device=(acc["DEVICE"]
                                                     if HARM_REPLACEMENT_SEMANTICS else 0.0))
                v = CO.option_value(w, mine.p_on_time, accuracy, p_dev, acc["DEVICE"])
                if harm.total != 0.0:
                    self.counts["harm_nonzero"] += 1
                return Candidate(name, value=v - harm.total, gain=v, harm=harm.total,
                                 scored=True,
                                 detail={"p_on_time": round(mine.p_on_time, 6),
                                         "accuracy": accuracy,
                                         "start_s": round(float(start_s), 6),
                                         "pred": mine.pred.as_dict() if mine.pred else None,
                                         "harm_rows": harm.n_affected,
                                         "n_exact": after.n_exact, "n_coarse": after.n_coarse})

            # 1. admit now, full history
            cands.append(_score("ADMIT_NOW_D2", now_s, history_tokens, cached_tokens, acc["D2"]))

            # 2. defer to the LATEST SAFE START, decode included
            pred_now = CC.predict(self.model, history_tokens, cached_tokens,
                                  int(round(coarse_overlap_forecast)),
                                  int(round(coarse_overlap_forecast)))
            lss = CC.latest_safe_start(now_s, deadline_abs_s, pred_now, self.safety)
            if not t.over_budget(self.budget_ms):
                c = _score("DEFER_TO_LATEST_SAFE_START", max(lss.latest_start_s, now_s),
                           history_tokens, cached_tokens, acc["D2"])
                c.detail["latest_safe_start"] = lss.as_dict()
                cands.append(c)
            else:
                timed_out = True

            # 3. RECENT, scored and then suppressed by the D155 (4) user rule
            if not timed_out and not t.over_budget(self.budget_ms):
                c = _score("SEND_RECENT", now_s, recent_tokens, 0, acc["RECENT"])
                if IMPOSED_NO_RECENT_FOR_LH:
                    c.detail["suppressed_by_rule"] = IMPOSED_NO_RECENT_NOTE
                    c.scored = False
                cands.append(c)
            elif not timed_out:
                timed_out = True

            # 4. the device answers (D152 (2): "reject" means the device answers). WORTH EXACTLY
            # ZERO under D177 (1) and that is the flip's largest semantic change: the device
            # answer is the INCUMBENT, not a candidate competing on value, so this candidate wins
            # only when every cloud option is worth a negative number (harm over gain). Before the
            # flip it was `w * p_dev * 0.071429` and could outscore a low-probability cloud
            # option. `p_device_on_time` is still computed and still reported here.
            cands.append(Candidate("DEVICE_ANSWERS",
                                   value=CO.device_only_value(w, p_dev, acc["DEVICE"]),
                                   gain=CO.device_only_value(w, p_dev, acc["DEVICE"]),
                                   harm=0.0, scored=True,
                                   detail={"p_device_on_time": p_dev,
                                           "device_wait_s": round(dev_wait_s, 6),
                                           "device_wait_source": CO.DEVICE_LATENCY_SOURCE,
                                           "label": CO.DEVICE_ANSWER_LABEL,
                                           "accuracy": acc["DEVICE"]}))

            scored = [c for c in cands if c.scored and c.value is not None]
            arith_best = max(scored, key=lambda c: (c.value, c.name)) if scored else None
            all_scored = [c for c in cands if c.value is not None]
            unsuppressed_best = (max(all_scored, key=lambda c: (c.value, c.name))
                                 if all_scored else None)
            if (unsuppressed_best is not None and arith_best is not None
                    and unsuppressed_best.name == "SEND_RECENT"
                    and arith_best.name != "SEND_RECENT"):
                self.counts["recent_suppressed_by_rule"] += 1

            base_c = next((c for c in cands if c.name == base["choice"]), None)
            value_base = base_c.value if base_c is not None else None
            cf_choice = arith_best.name if arith_best else base["choice"]
            value_cf = arith_best.value if arith_best else None

            if timed_out or t.over_budget(self.budget_ms):
                timed_out = True
                self.counts["timeout_fallback"] += 1
                chosen, deviated, delta = base["choice"], False, None
            elif value_base is None or value_cf is None:
                chosen, deviated, delta = base["choice"], False, None
            else:
                delta = value_cf - value_base
                deviated = bool(cf_choice != base["choice"] and delta > m_eff)
                chosen = cf_choice if deviated else base["choice"]

        if deviated:
            self.counts["deviations"] += 1
        if chosen == "DEFER_TO_LATEST_SAFE_START":
            self.counts["deferrals_chosen"] += 1
        self.counts["request"] += 1
        self.counts["decisions"] += 1
        d = Decision(
            kind="request", decision_id=decision_id, device_id=device_id, chosen=chosen,
            base_choice=base["choice"], cf_choice=cf_choice, deviated=deviated,
            value_base=value_base, value_cf=value_cf, delta=delta, margin=m.value, margin_effective=m_eff,
            margin_source=m.source, scorable=m.scorable, timeout_fallback=timed_out,
            elapsed_ms=self.clock.records[-1]["elapsed_ms"], candidates=cands,
            trace={"base": base, "weight": round(w, 6), "deficit_shortfall":
                   round(self.counters.shortfall(device_id), 6),
                   "horizon": HORIZONS["request"],
                   "horizon_abs_s": round(horizon_abs_s, 6),
                   "n_displaced_deadlines": len(displaced),
                   "exact_until_s": round(exact_until_s, 6),
                   "safety_factor": self.safety,
                   "latest_safe_start": lss.as_dict(),
                   "decode_included": True,
                   "deadline_abs_s": float(deadline_abs_s), "now_s": float(now_s),
                   "history_tokens": int(history_tokens),
                   "cached_tokens": int(cached_tokens), "readiness": readiness,
                   "accuracy_table": acc, "p_device_on_time": p_dev})
        self.log.append(d)
        self.clock.note("deviated", deviated)
        self.clock.note("timeout_fallback", timed_out)
        return d

    # ---- state decisions (D150 STATE, spec v5 section 8)

    def plan_state(self, *, decision_id: str, device_id: str, now_s: float,
                   p_question: float, next_question_s: float,
                   accuracy: Optional[float] = None,
                   p_on_time_warm: float, p_on_time_cold: float,
                   harm_warm: float = 0.0, harm_touch: float = 0.0,
                   warm_expressible: Optional[bool] = None,
                   host_warm: bool = False, slice_tokens: Optional[int] = None,
                   tokens_to_build: int = 0) -> Decision:
        """Warm, touch, keep, reload, hold back or slice (D150's four levers plus keep and reload).

        Scored by `w * p_question * (p_warm - p_cold) - harm`, a count of expected ON-TIME CLOUD
        ANSWERS (D177 (1)).

        THE INLINE `acc` FACTOR IS GONE, and it is the whole reason this file and `cf_objective`
        are one commit. This gain used to be `w * p_question * accuracy * (p_warm - p_cold)`, with
        `accuracy = table["cloud_D2"] = 0.250` multiplied in HERE and not through
        `cf_objective.option_value`; converting the harm alone would have left this gain in
        correctness units. The gain and the margin are both 4.0x larger than before (the factor
        0.250 removed from one, divided out of the other), a device-fallback-priced harm is 5.6x
        larger, and `cf_objective.CURRENCY_FLIP_STATUS` records the band of decisions that moves.

        `accuracy` is still accepted and still REPORTED on every candidate, because D177 (2) makes
        the quality table reporting only rather than absent, and the readers' arithmetic it used to
        reproduce (`v5/value_readers.py::warm_keep_reader`) is the value READER D177 (2) removes:
        that module and the arms that select a reader are not this commit's, so the difference is
        reported here and not edited there.
        """
        m = self._margin()
        acc = float(self.table["cloud_D2"]) if accuracy is None else float(accuracy)
        w = self.counters.weight(device_id)
        m_eff = effective_margin(m.value, w)
        horizon_s = min(max(float(next_question_s) - float(now_s), 0.0), CC.HORIZON_WARM_CAP_S)
        exact_until_s = float(now_s) + float(CC.NEAR_EXACT_S["state"] or 0.0)
        if warm_expressible is None:
            warm_expressible = self._warm_expressible(device_id)
        cands: List[Candidate] = []
        timed_out = False
        with self.clock.time_decision("state", decision_id=decision_id, device_id=device_id,
                                      n_candidates=len(STATE_CANDIDATES)) as t:
            def gain(p_warm: float, p_cold: float, harm: float) -> float:
                # NO ACCURACY FACTOR (D177 (1)): on-time cloud answers on both sides of the minus.
                return (w * float(p_question) * (float(p_warm) - float(p_cold))) - float(harm)

            g_warm = gain(p_on_time_warm, p_on_time_cold, harm_warm)
            cands.append(Candidate("WARM", value=(g_warm if warm_expressible else None),
                                   gain=g_warm, harm=harm_warm,
                                   expressible=bool(warm_expressible),
                                   scored=bool(warm_expressible),
                                   detail={"horizon_s": round(horizon_s, 6),
                                           "p_question": float(p_question),
                                           "accuracy": acc,
                                           "accuracy_enters_value": False,
                                           "value_units": VALUE_UNITS,
                                           "unexpressible_note": (
                                               None if warm_expressible else
                                               "warm-ahead is not expressible in the committed "
                                               "action space (engine_actions section 3): the "
                                               "candidate is NOT scored, so the harness blocker "
                                               "is never read as a policy decision")}))
            # TOUCH COSTS SOMETHING AND THIS LINE USED TO SAY IT DID NOT. Its old comment read
            # "no rebuild, so no harm", which is true about REBUILD harm and is not the cost the
            # coordinator charges: a touch is a real request that occupies the engine ahead of
            # everything queued behind it. Scoring it at harm = 0.0 while the coordinator spent
            # up to 0.67 GPU-s on each one is CLAUDE.md check 7's general shape, a comparator
            # planning at one price while charged another, and in covex-v6-state s4 it produced
            # 1,438 touches, 12,824 budget refusals and a dashcam collapse from 6,167 on-time to
            # 1,786. The caller now supplies `harm_touch` from the SAME D162 price source the
            # coordinator charges (user ruling, 2026-11-21).
            cands.append(Candidate("TOUCH",
                                   value=gain(p_on_time_warm, p_on_time_cold, harm_touch),
                                   gain=gain(p_on_time_warm, p_on_time_cold, 0.0),
                                   harm=float(harm_touch),
                                   scored=True,
                                   detail={"lever": "KEEP_GPU_WARM, not a pin",
                                           "harm_source": ("cf_objective.harm_warm_from_queue_"
                                                           "delay on the touch's own uncached "
                                                           "tokens; the coordinator charges the "
                                                           "same model")}))
            cands.append(Candidate("KEEP", value=0.0, gain=0.0, harm=0.0, scored=True,
                                   detail={"lever": "do nothing; the reference option"}))
            cands.append(Candidate("RELOAD", value=(gain(p_on_time_warm, p_on_time_cold, harm_warm)
                                                    if host_warm else None),
                                   gain=gain(p_on_time_warm, p_on_time_cold, harm_warm),
                                   harm=harm_warm, expressible=bool(host_warm),
                                   scored=bool(host_warm),
                                   detail={"trigger_state": "belief == host",
                                           "observed_in_committed_cells": False,
                                           "note": ("reload has no observed trigger state: cold "
                                                    "14,472 / gpu 1,442 / host NEVER over 39 "
                                                    "committed 16-device cells (engine_actions "
                                                    "section 2). Zero reloads is the state of the "
                                                    "fleet, not a mechanism that failed")}))
            # HOLD_BACK and SLICE act on what ENTERS the GPU: their value is the harm they AVOID.
            cands.append(Candidate("HOLD_BACK", value=float(harm_warm), gain=0.0,
                                   harm=-float(harm_warm), scored=True,
                                   detail={"lever": "D150's \"above all\": do not let this "
                                                    "rebuild evict a history whose question is due",
                                           "avoided_harm": float(harm_warm)}))
            n_slices = (len(EA.slice_plan(int(tokens_to_build), int(slice_tokens)))
                        if (ENGINE_ACTIONS_AVAILABLE and slice_tokens and tokens_to_build) else None)
            cands.append(Candidate("SLICE", value=(g_warm + 0.5 * float(harm_warm)
                                                   if warm_expressible else None),
                                   gain=g_warm, harm=0.5 * float(harm_warm),
                                   expressible=bool(warm_expressible),
                                   scored=bool(warm_expressible),
                                   detail={"n_slices": n_slices,
                                           "slice_tokens": slice_tokens,
                                           "scope": "BACKGROUND WARMING ONLY (D151 (3)); never a "
                                                    "deadline request",
                                           "harm_model": "half the monolithic harm, DECLARED and "
                                                         "NOT MEASURED: StudySLICE1 has not run, "
                                                         "so every slicing value is parametric"}))
            if t.over_budget(self.budget_ms):
                timed_out = True
            scored = [c for c in cands if c.scored and c.value is not None]
            best = max(scored, key=lambda c: (c.value, c.name)) if scored else None
            base_c = next(c for c in cands if c.name == "KEEP")     # base warms reactively only
            if timed_out:
                self.counts["timeout_fallback"] += 1
                chosen, deviated, delta = "KEEP", False, None
            else:
                delta = (best.value - base_c.value) if best else None
                deviated = bool(best is not None and best.name != "KEEP" and delta > m_eff)
                chosen = best.name if deviated else "KEEP"
        if not warm_expressible:
            self.counts["warm_unexpressible"] += 1
        if deviated:
            self.counts["deviations"] += 1
        self.counts["state"] += 1
        self.counts["decisions"] += 1
        d = Decision(kind="state", decision_id=decision_id, device_id=device_id, chosen=chosen,
                     base_choice="KEEP", cf_choice=(best.name if best else "KEEP"),
                     deviated=deviated, value_base=base_c.value,
                     value_cf=(best.value if best else None), delta=delta, margin=m.value,
                     margin_effective=m_eff, margin_source=m.source, scorable=m.scorable, timeout_fallback=timed_out,
                     elapsed_ms=self.clock.records[-1]["elapsed_ms"], candidates=cands,
                     trace={"horizon": HORIZONS["state"], "horizon_s": round(horizon_s, 6),
                            "horizon_cap_s": CC.HORIZON_WARM_CAP_S,
                            "exact_until_s": round(exact_until_s, 6),
                            "near_exact_window_s": CC.NEAR_EXACT_S["state"],
                            "weight": round(w, 6),
                            "engine_actions": ENGINE_ACTIONS_VERSION,
                            "warm_expressible": bool(warm_expressible)})
        self.log.append(d)
        return d

    def _warm_expressible(self, session_id: str) -> bool:
        """Ask `engine_actions` whether a warm-ahead for this session can legally be emitted.

        The interface note's point 1: `plan_warm_ahead` returns `unexpressible` as well as
        `actions`, and a counterfactual that scores warming must read both. Without an
        observation this module cannot ask, so it answers False and the planner marks the
        candidate NOT SCORED, which is the conservative direction: an unexpressible candidate
        that scored would make a harness blocker look like a policy decision.
        """
        return False

    # ---- sync decisions (D150 SYNC (3), spec v5 section 9)

    def plan_sync(self, *, decision_id: str, device_id: str, now_s: float,
                  deadline_abs_s: float, pre_outage_tokens: int, recent_frame_tokens: int,
                  full_tokens: int, catch_up_s: float,
                  acc_question_first: Optional[float] = None,
                  others: Sequence[CC.PendingRequest] = (),
                  coarse_overlap_forecast: float = 0.0, question_id: Optional[str] = None,
                  kind: str = "robot", episode_frames: Optional[int] = None) -> Decision:
        """A question arriving before catch-up: question-first, wait, or leave it to the device.

        D150 SYNC (3)'s three options, entering the SAME comparison as a request decision rather
        than a fourth mechanism (spec v5 section 7.5). The horizon is "until caught up".

        THE THREE OPTIONS MUST DIFFER IN ACCURACY AS WELL AS IN P(ON TIME), and that is where a
        gap is. Question-first answers from the pre-outage history plus recent frames (D54), which
        is a TRUNCATED history and not the full one, so pricing it at the committed full-history
        accuracy would make WAIT dominated by construction: WAIT starts later with more tokens, so
        its P(on time) can never be higher, and with equal accuracy it could never win. NO
        COMMITTED ACCURACY EXISTS for a question-first answer. `acc_question_first` is therefore a
        REQUIRED DECLARED INPUT, and when it is not given the committed cloud RECENT accuracy
        stands in as the closest measured analogue of a truncated history, labelled as a
        substitution in the trace. A v5 outage result may not be read without that number being
        either measured or ruled.
        """
        m = self._margin()
        acc = {"D2": float(self.table["cloud_D2"]), "DEVICE": float(self.table["device"])}
        acc_qf_substituted = acc_question_first is None
        acc_qf = (float(self.table["cloud_RECENT"]) if acc_qf_substituted
                  else float(acc_question_first))
        w = self.counters.weight(device_id)
        m_eff = effective_margin(m.value, w)
        dl_s = float(deadline_abs_s) - float(now_s)
        dev_wait_s = CO.device_wait_s(kind=kind, question_id=question_id,
                                      episode_frames=episode_frames)
        p_dev = CO.p_device_on_time(dl_s, dev_wait_s)
        exact_until_s = float(now_s) + float(CC.NEAR_EXACT_S["sync"] or 0.0)
        cands: List[Candidate] = []
        timed_out = False
        with self.clock.time_decision("sync", decision_id=decision_id, device_id=device_id,
                                      n_candidates=len(SYNC_CANDIDATES)) as t:
            def _p(tokens: int, start_s: float) -> Tuple[float, CC.ServicePrediction]:
                pred = CC.predict(self.model, tokens, 0, int(round(coarse_overlap_forecast)),
                                  int(round(coarse_overlap_forecast)))
                return CC.p_on_time(self.residuals, pred.engine_s,
                                    float(deadline_abs_s) - float(start_s) - CC.LINK_RTT_S), pred

            # question-first: the pre-outage history plus the recent frames (D54), served now
            qf_tokens = int(pre_outage_tokens) + int(recent_frame_tokens)
            p_qf, pred_qf = _p(qf_tokens, now_s)
            cands.append(Candidate("QUESTION_FIRST",
                                   value=CO.option_value(w, p_qf, acc_qf, p_dev, acc["DEVICE"]),
                                   gain=CO.option_value(w, p_qf, acc_qf, p_dev, acc["DEVICE"]),
                                   harm=0.0, scored=True,
                                   detail={"tokens": qf_tokens, "p_on_time": round(p_qf, 6),
                                           "pred": pred_qf.as_dict(),
                                           "accuracy": acc_qf,
                                           "accuracy_is_a_substitution": acc_qf_substituted,
                                           "substitution_note": (
                                               "no committed accuracy exists for a question-first "
                                               "answer; cloud RECENT stands in as the closest "
                                               "measured truncated-history figure"
                                               if acc_qf_substituted else None),
                                           "rule": "D54 pre-outage history plus recent frames"}))
            # wait: answer after catch-up, on the full history
            p_w, pred_w = _p(int(full_tokens), float(now_s) + float(catch_up_s))
            cands.append(Candidate("WAIT",
                                   value=CO.option_value(w, p_w, acc["D2"], p_dev, acc["DEVICE"]),
                                   gain=CO.option_value(w, p_w, acc["D2"], p_dev, acc["DEVICE"]),
                                   harm=0.0, scored=True,
                                   detail={"tokens": int(full_tokens),
                                           "p_on_time": round(p_w, 6),
                                           "catch_up_s": float(catch_up_s),
                                           "pred": pred_w.as_dict(),
                                           "ordering": "oldest-first within a device: append-only "
                                                       "KV cannot prefill a later frame first "
                                                       "(D148, D152 (3))"}))
            # LEAVE_TO_DEVICE is worth EXACTLY ZERO under D177 (1), as DEVICE_ANSWERS is in
            # `plan_request`; `device_only_value` says why at its definition.
            cands.append(Candidate("LEAVE_TO_DEVICE",
                                   value=CO.device_only_value(w, p_dev, acc["DEVICE"]),
                                   gain=CO.device_only_value(w, p_dev, acc["DEVICE"]), harm=0.0,
                                   scored=True,
                                   detail={"p_device_on_time": p_dev,
                                           "device_wait_s": round(dev_wait_s, 6),
                                           "device_wait_source": CO.DEVICE_LATENCY_SOURCE}))
            if t.over_budget(self.budget_ms):
                timed_out = True
            scored = [c for c in cands if c.scored and c.value is not None]
            best = max(scored, key=lambda c: (c.value, c.name))
            # the base policy has no backlog mechanism: it serves the question as it arrives, which
            # is question-first with whatever the cloud holds.
            base_c = next(c for c in cands if c.name == "QUESTION_FIRST")
            if timed_out:
                self.counts["timeout_fallback"] += 1
                chosen, deviated, delta = base_c.name, False, None
            else:
                delta = best.value - base_c.value
                deviated = bool(best.name != base_c.name and delta > m_eff)
                chosen = best.name if deviated else base_c.name
        if deviated:
            self.counts["deviations"] += 1
        self.counts["sync"] += 1
        self.counts["decisions"] += 1
        d = Decision(kind="sync", decision_id=decision_id, device_id=device_id, chosen=chosen,
                     base_choice=base_c.name, cf_choice=best.name, deviated=deviated,
                     value_base=base_c.value, value_cf=best.value, delta=delta, margin=m.value,
                     margin_effective=m_eff, margin_source=m.source, scorable=m.scorable, timeout_fallback=timed_out,
                     elapsed_ms=self.clock.records[-1]["elapsed_ms"], candidates=cands,
                     trace={"horizon": HORIZONS["sync"], "catch_up_s": float(catch_up_s),
                            "exact_until_s": round(exact_until_s, 6),
                            "near_exact_window_s": CC.NEAR_EXACT_S["sync"],
                            "outage_model": ("SYNTHETIC (D150 (4), P6): no outage traces exist; "
                                             "every outage number carries that label"),
                            "accuracy_question_first": acc_qf,
                            "accuracy_question_first_is_a_substitution": acc_qf_substituted,
                            "accuracy_full": acc["D2"],
                            "weight": round(w, 6)})
        self.log.append(d)
        return d

    # ---- the decision log, for Step 2b diffs

    def decision_log(self) -> List[Dict[str, Any]]:
        return [d.as_dict() for d in self.log]

    def describe(self) -> Dict[str, Any]:
        return {
            "base_policy": BASE_POLICY,
            "base_surrogate_note": BASE_SURROGATE_NOTE,
            "objective": CO.OBJECTIVE_STATEMENT,
            "decision_kinds_counterfactual": list(DECISION_KINDS),
            "decision_kinds_rule_based": RULE_BASED_KINDS,
            "candidates": {"request": list(REQUEST_CANDIDATES), "state": list(STATE_CANDIDATES),
                           "sync": list(SYNC_CANDIDATES)},
            "horizons": HORIZONS,
            "two_level_fidelity": {"near_exact_s_by_kind": CC.NEAR_EXACT_S,
                                   "declared_not_fitted": True,
                                   "coarse_level": "offered-load forecast (Little's law)"},
            "margin": {"declared_in": "v5/cf_margin.py::MARGIN_CF",
                       "value": CM.MARGIN_CF, "is_set": CM.MARGIN_CF is not None,
                       "value_on_time_units": (CO.attainment_margin(float(CM.MARGIN_CF))
                                               if CM.MARGIN_CF is not None else None),
                       "units": MARGIN_UNITS, "rule": CM.MARGIN_CF_RULE},
            "value_units": VALUE_UNITS,
            "safety_factor": self.safety,
            "imposed_rules": {"no_RECENT_for_LH": IMPOSED_NO_RECENT_FOR_LH,
                              "note": IMPOSED_NO_RECENT_NOTE},
            "engine_actions": ENGINE_ACTIONS_VERSION,
            "budget_ms": self.budget_ms,
            "counts": dict(self.counts),
        }


def main() -> int:
    print(json.dumps({"base_policy": BASE_POLICY, "margin_is_set": CM.MARGIN_CF is not None,
                      "candidates": {"request": list(REQUEST_CANDIDATES),
                                     "state": list(STATE_CANDIDATES),
                                     "sync": list(SYNC_CANDIDATES)},
                      "horizons": HORIZONS, "near_exact_s": CC.NEAR_EXACT_S,
                      "engine_actions": ENGINE_ACTIONS_VERSION}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
