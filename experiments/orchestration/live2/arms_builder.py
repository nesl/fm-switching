#!/usr/bin/env python3
"""A modular dry-run policy assembled from pluggable slots, registered as live2 arms.

Each slot is an independent choice, so a one-factor-at-a-time screen can attribute any change to
one mechanism. Every mechanism REUSES committed code and cites its source:

  S1 feasible-by-deadline : costs.recall_ttft_s / costs.CLOUD_TTFT, the same curves
                            `baselines/constructed.py::B7EDFFeasibility` admits by
  S2 feasible-in-time     : B7's slack test, verbatim in shape (est <= slack, else defer band)
  S3 pieces-vs-one-go     : the mode set of `policy/planner_rc.py::enumerate_plans` (D125), with
                            piece sizes from D17 only
  S4 llf                  : the laxity key of `live2/arms.py::LlfArm` (D118), S_hat from costs.py
  S4 adaptive in-flight   : the D114 release bound of `live2/arms.py::Pi0Edf`
  S6 early decline        : B7's REJECT branch

TWO SLOTS FROM THE BRIEF ARE NOT BUILT, and the reason is structural rather than a judgement:

  S5 memory (all three alternatives) is UNEXPRESSIBLE in live2. `desired_tier` is declared once
  (cstate.py:92) and written twice (coordinator.py:423, :425) with NO READ anywhere, so
  KEEP_GPU_WARM and OFFLOAD_TO_HOST cannot change a decision; `gpu_kv_tokens` is handed to arms
  and never enforced as a cap; there is no automatic eviction; and EVICT only demotes the arm's
  own session. Retention under pressure cannot be expressed where there is no pressure.

  S3 host-to-reload is UNEXERCISABLE. Every belief write in live2 sets cold (cstate.py:181, :201,
  coordinator.py:420) or gpu (coordinator.py:711). None sets host, so readiness is always COLD or
  GPU-WARM and HOST-WARM is unreachable.

Both are recorded in results/orchestration/live2/builder/slot_precheck.json.

DEFAULT ASSEMBLY IS B7-EQUIVALENT and is proved byte-identical to `b7-edf-feasibility`. A second
assembly is proved byte-identical to `always-cloud-fcfs`, because a one-base proof can pass on a
`getattr` default coincidence alone.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_ROOT / "experiments/orchestration/baselines"),
           str(_ROOT / "experiments/orchestration/sim"), str(_ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import (Action, DEFAULTS, Observation, Policy, RecallAction,   # noqa: E402
                       StreamAction, materialize)
from arms import Live2ArmMixin                                          # noqa: E402

S1_CHOICES = ("all", "feasible", "fairshare", "lateness")
S2_CHOICES = ("all", "feasible", "value")
# D135 item 2. S7 is the EVIDENCE slot, live only since Part A made RecallAction.representation
# reach execution (coordinator.py:552 -> cstate.tokens_for_representation).
S7_CHOICES = ("full", "degrade", "always-recent")
from cstate import RECENT_WINDOW_TOKENS                                  # noqa: E402
S3_CHOICES = ("fixed", "whatif")
S4_CHOICES = ("edf", "llf", "reserve", "adaptive")
S6_CHOICES = ("none", "decline")

SH_TTFT_KEY = ("32BI", 1, 25)      # committed single-frame TTFT, StudyD7 / D7b p50 at 25 percent


class BuilderArm(Live2ArmMixin, Policy):
    """One arm whose behaviour is the composition of its slot settings."""

    case = "own"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "recall_decision", "session_action", "order")
    defaults_used = ("cadence_s", "frame_count", "representation", "engine_config")
    restricts_action_space = None

    def __init__(self, s7: str = "full",
                 s1: str = "all", s2: str = "feasible", s3: str = "fixed",
                 s4: str = "edf", s6: str = "none", *, defer_s: float = 0.5,
                 c_inflight: int = 8, reserve_frac: float = 0.25, fair_target: float = 0.25,
                 piece_tokens: Optional[int] = None, name: Optional[str] = None,
                 order_label: str = "EDF", engine_config: Optional[str] = None,
                 emit_defaults_for_recall: bool = False) -> None:
        for v, choices, slot in ((s7, S7_CHOICES, "S7"), (s1, S1_CHOICES, "S1"), (s2, S2_CHOICES, "S2"),
                                 (s3, S3_CHOICES, "S3"), (s4, S4_CHOICES, "S4"),
                                 (s6, S6_CHOICES, "S6")):
            if v not in choices:
                raise ValueError("%s=%r not in %r" % (slot, v, choices))
        self.s1, self.s2, self.s3, self.s4, self.s6 = s1, s2, s3, s4, s6
        self.s7 = s7
        self.defer_s = float(defer_s)
        self.c_inflight = int(c_inflight)
        self.reserve_frac = float(reserve_frac)
        self.fair_target = float(fair_target)
        self.piece_tokens = piece_tokens
        self.order_label = order_label
        self._engine_config = engine_config
        self._emit_defaults_for_recall = bool(emit_defaults_for_recall)
        self.name = name or ("builder-%s-%s-%s-%s-%s" % (s1, s2, s3, s4, s6))
        self.live2_source = ("live2/arms_builder.py slots S1=%s S2=%s S3=%s S4=%s S6=%s; "
                             "S5 unexpressible and S3 reload unreachable, see slot_precheck.json"
                             % (s1, s2, s3, s4, s6))
        self.stats: Dict[str, Any] = dict(
            arm=self.name, s1=s1, s2=s2, s3=s3, s4=s4, s6=s6, s7=s7,
            c_inflight=self.c_inflight,
            sh_admitted=0, sh_held=0, rc_cloud=0, rc_defer=0, rc_reject=0, rc_device=0,
            materialize=0, inflight_bound_periods=0, lateness_throttle_periods=0,
            fairshare_held=0, whatif_chose_pieces=0, whatif_chose_onego=0,
            s7_recent=0, s7_degraded=0, s7_degrade_still_infeasible=0)
        self._delivered: Dict[str, int] = {}
        self._offered: Dict[str, int] = {}

    def reset(self, seed: int = 0) -> None:
        self._delivered.clear()
        self._offered.clear()

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._roster = roster

    # ---------------------------------------------------------------- cost helpers
    @staticmethod
    def _sh_service_s() -> float:
        import costs as C
        return float(C.CLOUD_TTFT[SH_TTFT_KEY])

    @staticmethod
    def _rc_service_s(tokens: int, readiness: str) -> float:
        """S2's admission estimate, VERBATIM in form from `constructed.py::B7EDFFeasibility`.

        B7 admits by `C.recall_ttft_s(max(tokens, 1), readiness)` and nothing else, so the default
        assembly uses exactly that and is b7-equivalent BY CONSTRUCTION rather than by happening to
        agree on a cell where every query is feasible under either estimate.
        """
        import costs as C
        return float(C.recall_ttft_s(max(int(tokens), 1), readiness))

    @staticmethod
    def _rc_laxity_service_s(tokens: int, readiness: str) -> float:
        """S4 llf's S_hat, from `live2/arms.py::LlfArm` (D118): a cold recall pays the committed
        cold prefill for the unbuilt history PLUS the answer at the warm state it lands in. This
        is deliberately NOT the admission estimate above; the two serve different slots."""
        import costs as C
        tok = max(int(tokens), 1)
        if readiness in ("GPU-WARM", "HOST-WARM"):
            return float(C.recall_ttft_s(tok, readiness))
        return float(C.recall_ttft_s(tok, "COLD") + C.recall_ttft_s(tok, "GPU-WARM"))

    def _instant(self, obs: Observation, sid: str):
        inst = (getattr(self, "_roster", None) or {}).get("sh_instant", {}).get(sid)
        if inst is not None:
            return float(inst["t_capture"]), float(inst["deadline_abs"])
        tgt = getattr(self, "_targets", None)
        l_s = float(tgt["dashcam"]["L_s"]) if tgt else 1.0
        s = next((x for x in obs.streams if x.stream_id == sid), None)
        last = (s.delivered_times_s[-1] if (s and s.delivered_times_s)
                else obs.now_s - (s.cadence_s if s else 0.5))
        due = last + (s.cadence_s if s else 0.5)
        return due, due + l_s

    def _inflight(self, obs: Observation) -> int:
        return sum(int(v) for v in (obs.cloud.running_by_class or {}).values())

    # ---------------------------------------------------------------- the decision
    def decide(self, obs: Observation) -> Action:
        streams = self._dashcams(obs)
        recall, sessions = self._robots(obs)
        return Action(streams=streams, recall=recall, sessions=sessions,
                      order=self.order_label, engine_config=self._engine_config)

    def _dashcams(self, obs: Observation) -> List[StreamAction]:
        if self.s1 == "all":
            self.stats["sh_admitted"] += len(obs.streams)
            return [StreamAction(s.stream_id, "cloud") for s in obs.streams]

        svc = self._sh_service_s()
        cands = []
        for s in obs.streams:
            due, dl = self._instant(obs, s.stream_id)
            self._offered[s.stream_id] = self._offered.get(s.stream_id, 0) + 1
            slack = dl - float(obs.now_s)
            feasible = svc <= slack
            if self.s1 == "feasible" and not feasible:
                continue
            if self.s1 == "fairshare":
                seen = self._offered.get(s.stream_id, 1)
                got = self._delivered.get(s.stream_id, 0)
                if got / max(seen, 1) >= self.fair_target and not feasible:
                    self.stats["fairshare_held"] += 1
                    continue
            key = (dl - svc) if self.s4 == "llf" else dl
            cands.append((key, s.stream_id, s))

        cands.sort(key=lambda c: (c[0], c[1]))
        budget = self._release_budget(obs, n_streams=len(cands))
        on = set()
        for _k, sid, _s in cands[:budget]:
            on.add(sid)
            self._delivered[sid] = self._delivered.get(sid, 0) + 1
        self.stats["sh_admitted"] += len(on)
        self.stats["sh_held"] += len(obs.streams) - len(on)
        return [StreamAction(s.stream_id, "cloud" if s.stream_id in on else "local")
                for s in obs.streams]

    def _release_budget(self, obs: Observation, n_streams: int) -> int:
        if self.s4 == "adaptive":
            free = max(self.c_inflight - self._inflight(obs), 0)
            if free < n_streams:
                self.stats["inflight_bound_periods"] += 1
            return free
        if self.s4 == "reserve":
            free = max(self.c_inflight - self._inflight(obs), 0)
            keep = int(round(self.c_inflight * self.reserve_frac))
            return max(free - keep, 0)
        if self.s1 == "lateness":
            q = sum(int(v) for v in (obs.cloud.queued_by_class or {}).values())
            if q > self.c_inflight:
                self.stats["lateness_throttle_periods"] += 1
                return max(self.c_inflight - q, 0)
        return n_streams

    def _robots(self, obs: Observation):
        rec: List[RecallAction] = []
        sessions = []
        known = (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                 | {q.session_id for q in obs.recall})
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            if self._emit_defaults_for_recall:
                rec.append(RecallAction(q.query_id, DEFAULTS["recall_decision"]))
                continue
            if self.s7 == "always-recent":
                # the REFERENCE arm: upper bound on the timing benefit, lower bound on accuracy.
                rec.append(RecallAction(q.query_id, "CLOUD", representation="RECENT"))
                self.stats["rc_cloud"] += 1; self.stats["s7_recent"] += 1
                continue
            if self.s2 == "all":
                rec.append(RecallAction(q.query_id, "CLOUD")); self.stats["rc_cloud"] += 1
                continue
            est = self._rc_service_s(q.readiness_tokens, q.readiness)
            slack = q.slack_s(obs.now_s)
            if self.s2 == "value" and not self._value_justified(q, est, slack):
                rec.append(RecallAction(q.query_id, "DEVICE")); self.stats["rc_device"] += 1
                continue
            if est <= slack:
                rec.append(RecallAction(q.query_id, "CLOUD")); self.stats["rc_cloud"] += 1
                if self.s3 != "fixed" or self.piece_tokens is not None:
                    sa = self._execution_mode(q, est, slack, known)
                    if sa is not None:
                        sessions.append(sa); self.stats["materialize"] += 1
            elif self.s7 == "degrade" and self._at_risk(q, est, slack):
                # EVIDENCE DEGRADATION. Fires on RISK, not on NEED: see _at_risk.
                tok = max(min(int(RECENT_WINDOW_TOKENS), int(q.readiness_tokens)), 1)
                est_recent = self._rc_service_s(tok, q.readiness)
                if est_recent <= slack:
                    rec.append(RecallAction(q.query_id, "CLOUD", representation="RECENT"))
                    self.stats["rc_cloud"] += 1; self.stats["s7_degraded"] += 1
                else:
                    self.stats["s7_degrade_still_infeasible"] += 1
                    if self.s6 == "decline":
                        rec.append(RecallAction(q.query_id, "DEVICE")); self.stats["rc_device"] += 1
                    else:
                        rec.append(RecallAction(q.query_id, "REJECT")); self.stats["rc_reject"] += 1
            elif est <= slack + self.defer_s:
                rec.append(RecallAction(q.query_id, "DEFER", defer_s=self.defer_s))
                self.stats["rc_defer"] += 1
            else:
                if self.s6 == "decline":
                    rec.append(RecallAction(q.query_id, "DEVICE")); self.stats["rc_device"] += 1
                else:
                    rec.append(RecallAction(q.query_id, "REJECT")); self.stats["rc_reject"] += 1
        return rec, sessions

    @staticmethod
    def _at_risk(q, est: float, slack: float) -> bool:
        """RISK, not NEED. This is the whole design argument and it belongs in the code.

        StudyEVNEED established that NOTHING PREDICTS when history helps or hurts: coverage scores
        BELOW base rate on the hurts flow, the category rule scores exactly chance, and neither
        signal is available at decision time anyway. A mechanism that fires on "this question needs
        full history" is therefore undeployable.

        This rule never asks that question. It asks a different and directly observable one:
        the history is COLD (a full answer means a cold rebuild) and the full answer does NOT FIT
        the remaining slack, so this question is already about to be declined, rejected or
        delivered late. Given that, is a degraded answer better than none?

        Both terms are observable at decision time from the observation alone, which is exactly
        what the StudyEVNEED signals were not.
        """
        return str(q.readiness).upper() == "COLD" and est > slack

    def _value_justified(self, q, est: float, slack: float) -> bool:
        """S2 value. PRE-REGISTERED AS EXPECTED-WEAK: the DeltaJ objective this imitates is blind
        to cost and to delivery risk in the range that matters, so a gain-only test is expected to
        admit nearly everything and behave like `all`."""
        import costs as C
        gain = C.recall_gpu_s(max(int(q.readiness_tokens), 1), q.readiness)
        return gain > 0.0 and est <= slack

    def _execution_mode(self, q, est: float, slack: float, known):
        """S3. The mode set of planner_rc.enumerate_plans MINUS reload, which is unreachable."""
        if q.session_id not in known:
            return None
        tok = max(int(q.readiness_tokens), 1)
        if q.readiness == "GPU-WARM":
            return None
        if self.s3 == "whatif":
            if est <= slack * 0.5:
                self.stats["whatif_chose_onego"] += 1
                return materialize(q.session_id, tok, None)
            self.stats["whatif_chose_pieces"] += 1
            return materialize(q.session_id, tok, 2048)
        return materialize(q.session_id, tok, self.piece_tokens)


def _mk(**kw):
    return lambda: BuilderArm(**kw)


BUILDER_ARMS: Dict[str, Any] = {
    # DEFAULT, proved byte-identical to b7-edf-feasibility
    "builder-default": _mk(s1="all", s2="feasible", s3="fixed", s4="edf", s6="none",
                           name="builder-default", order_label="EDF"),
    # second proof base, byte-identical to always-cloud-fcfs
    "builder-acfcfs": _mk(s1="all", s2="all", s3="fixed", s4="edf", s6="none",
                          name="builder-acfcfs", order_label="FCFS", engine_config="default"),
    "builder-s1-feasible": _mk(s1="feasible", name="builder-s1-feasible"),
    "builder-s1-fairshare": _mk(s1="fairshare", name="builder-s1-fairshare"),
    "builder-s1-lateness": _mk(s1="lateness", name="builder-s1-lateness"),
    "builder-s2-all": _mk(s2="all", name="builder-s2-all"),
    "builder-s2-value": _mk(s2="value", name="builder-s2-value"),
    "builder-s3-whatif": _mk(s3="whatif", name="builder-s3-whatif"),
    "builder-s4-llf": _mk(s1="feasible", s4="llf", name="builder-s4-llf", order_label="LLF"),
    "builder-s4-reserve": _mk(s1="feasible", s4="reserve", name="builder-s4-reserve"),
    "builder-s4-adaptive": _mk(s1="feasible", s4="adaptive", name="builder-s4-adaptive"),
    "builder-s6-decline": _mk(s6="decline", name="builder-s6-decline"),
    # ---- D135 item 2, PREPARE ONLY. Both read the representation field Part A made live.
    "builder-s7-degrade": _mk(s7="degrade", name="builder-s7-degrade"),
    "builder-s7-always-recent": _mk(s7="always-recent", name="builder-s7-always-recent"),
}
