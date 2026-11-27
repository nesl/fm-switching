#!/usr/bin/env python3
"""HybridArm (D138, P1): b7-edf-feasibility plus switchable components, each default OFF.

With every switch off, `decide` RETURNS b7's own decision unchanged (it calls the committed
`B7EDFFeasibility.decide`), so the base is byte-identical to b7-edf-feasibility by construction; the
proof is a decision-log diff on dry runs (tests/test_hybrid.py). b7 has NO in-flight limit: it marks
every stream for the cloud each period and admits / defers / rejects each recall by feasibility.

Components (flash code read-only: costs.py curves, b7's feasibility rule, the RC quality tables):
  C1 ordering        index = value x urgency / remaining work; urgency = 1 / max(slack, 0.1 s), slack against the
                     item's own deadline less its predicted work; work from the committed cost curve; value from
                     the committed RC tables (cloud minus device accuracy, trace-weighted) for a recall and the
                     committed SH cloud gain for a dashcam instant.
  C2 protect-fill    at risk = a recall whose slack < k_r, or a dashcam whose running on-time fraction (trailing
                     60 s) < 0.25 + m_d; at-risk work first, and (when a cap applies) one reserved slot for
                     at-risk recall; the rest in C1 order (or deadline order if C1 is off).
  C3 degradation     an at-risk recall that is infeasible as a full-history recall but feasible as RECENT is sent
                     as RECENT (the representation field is live since e924005) instead of deferred / rejected.
  C4 retention       INERT until memory pressure exists (placeholder that emits no session action).
  C5 AIMD in-flight  cap starts at 8, halves (floor 4) when the episodic latency estimate exceeds 0.8 x the
                     dashcam deadline, +1 per 5 s otherwise (ceiling 8); only the top `cap - in_flight` items are
                     released; the rest stay local (dashcam) or deferred (recall).
  C6 chooser         flash's policy/chooser.py (70be641), per robot question: candidates send (full D2) / hold /
                     decline, the C2/C3 choice as default, each simulated to the question's deadline on a
                     policy-core mirror whose own decisions are never executed (arms_covex_v2's evaluator pattern).
                     Off = the code path never runs (no mirror is built), so off is identical by construction.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for p in (LIVE2, LIVE2 / "fleet", REPO / "experiments/orchestration",
          REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import costs as C
import la_arrival_admission as LA                                        # noqa: E402
# `hybrid` is imported BOTH as a package (the live harness puts live2/ on sys.path but NOT
# live2/hybrid/) and as a flat module directory (flash's proofs put live2/hybrid/ on sys.path).
# A bare `import value_reader` works only in the second case, and it killed every live run on the
# H100 at "import hybrid", llf included, because run_live2_real imports hybrid to register the
# hybrid-* arms whatever arm is being run. Both forms are tried so the module works however it is
# imported, and the harness's own path setup is now part of what I test before pushing.
try:
    from . import value_reader as VR                                          # noqa: E402
except ImportError:                                                           # noqa: BLE001
    import value_reader as VR                                                 # noqa: E402
from interface import Action, Observation, RecallAction, StreamAction       # noqa: E402
from policy.profiles import MissingEvidence                                  # noqa: E402

DASH_DEADLINE_S = 1.0


def _chooser_module():
    """flash's committed policy/chooser.py (70be641), loaded read-only by path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("policy_chooser", REPO / "experiments/orchestration/policy/chooser.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("policy_chooser", m)
    spec.loader.exec_module(m)
    return m
RECENT_TOKENS = 467          # live2's committed RECENT_WINDOW_TOKENS (cstate), the representation the coordinator charges


LH_REQ_PATH = REPO / "results/orchestration/live2/lh_req/lh_req_definition.json"
WORKLOADS = ("mixed", "lh_req")


def _lh_req_mix() -> Counter:
    """The LH-REQ category mix, read from the COMMITTED definition file (`lh_req_question_ids` and
    `per_category`, 1acbe36). D142 item 2 wants the workload's OWN trace-weighted table, and the
    weights are that file's per-category counts over the 97 questions.

    This file is the ONE source of truth for the question set: the 97 are NOT re-derived here, and no
    question filter is written here. The trace option that selects them is owned elsewhere."""
    d = json.loads(LH_REQ_PATH.read_text())
    return Counter({k: int(v) for k, v in (d.get("per_category") or {}).items()})


def _quality_values(workload: str = "mixed") -> Dict[str, float]:
    """Committed values, read-only: recall = 32B-D2 minus 4B-D2 accuracy, weighted by the workload's own
    category mix; dashcam = the committed cloud SH gain (figM1 / CTRL1b, +0.090 challenge mAP).

    The accuracy TABLE is the same committed table for both workloads; only the WEIGHTS differ, which is
    what "the workload's own trace-weighted table" means. LH-REQ uses all eight S-EMBER categories, all
    present in the committed table, so no entry is missing and no value is invented."""
    if workload not in WORKLOADS:
        raise ValueError("workload must be one of %r" % (WORKLOADS,))
    prof = json.loads((REPO / "results/orchestration/prof1/profiles_dev.json").read_text())["RC"]["tables"]
    cl, dv = prof["32B-D2"]["by_category"], prof["4B-D2"]["by_category"]
    if workload == "lh_req":
        mix = _lh_req_mix()
    else:
        try:
            import data_sources as DS
            mix = Counter(q.category for s in DS.eval_sessions().values() for q in s.questions)
        except Exception:                                                     # noqa: BLE001
            mix = Counter({k: 1 for k in cl})
    num = sum(mix[c] * (float(cl[c]["accuracy"]) - float(dv[c]["accuracy"])) for c in cl if c in dv and mix[c])
    den = sum(mix[c] for c in cl if c in dv and mix[c]) or 1
    return dict(recall=max(num / den, 1e-3), dashcam=0.090)


SS_QUALITY_PATH = REPO / "results/orchestration/prof1/ss_quality.json"


def _ss_table() -> Dict[str, Any]:
    """D142 item 3: the single-shot quality table is a DECLARED INPUT, read here, never a constant in this
    module. Replacing the placeholder with the measured 32B values is then a DATA UPDATE that leaves this
    frozen policy byte-identical; a table written into policy code would make every swap a new labelled
    version with all cells redone under D79. The SS question TYPES come from the same file, so even the set
    of categories that count as single-shot is data rather than policy code."""
    if not SS_QUALITY_PATH.exists():
        return {}
    return json.loads(SS_QUALITY_PATH.read_text())


def _ss_values(tbl: Dict[str, Any]) -> Dict[str, float]:
    """C1's value for an SS request: cloud accuracy minus device accuracy, per dataset. Under the PLACEHOLDER
    rule those are EQUAL (the placeholder sets cloud = measured device accuracy), so the gain is 0 and C1
    values an SS request at the floor. That is the conservative reading and it is FLAGGED, not hidden: with
    no measured cloud answer there is no evidence the cloud beats the device, and inventing a gain here would
    put a made-up number into the ordering index of a frozen policy."""
    out: Dict[str, float] = {}
    for qt, e in (tbl.get("question_type_to_representation") or {}).items():
        cloud, dev = e.get("cloud_accuracy"), e.get("_device_accuracy")
        out[qt] = max(float(cloud) - float(dev), 1e-3) if (cloud is not None and dev is not None) else 1e-3
    return out


# D170: the engine's context limit is a DEPLOYMENT CONSTRAINT, identical for every arm. A request
# whose predicted prompt exceeds it cannot be answered at all, so sending one spends the engine and
# still misses. Our policy treats it as INFEASIBLE in its feasibility check and leaves the question
# to the device.
#
# WHY A SWITCH, DEFAULT OFF, AND NOT A CHANGE TO THE BASE. "Already behaves correctly" and "has
# the rule" are different claims and D170 asks for them separately. Measured on the committed
# cells: 18 recall questions exceed the limit, all at seed 7 (34,051 to 52,861 tokens), and every
# arm of ours sent NONE of them. They are declined on TIME, not on the limit: `est <= slack` with
# est = recall_ttft_s(history, readiness) cannot predict a 34k-token COLD history inside a 3 s
# deadline. That is b7's behaviour inherited through the base, and it is not the rule.
#
# THE CASE THE RULE EXISTS FOR IS ONE WARMING CREATES. A 40k-token history already built WARM has
# a SMALL predicted est, passes `est <= slack`, is sent, and is refused by the engine. Rung 1 and
# above warm ahead, so the reachable path appears exactly where the rule is missing. The one arm
# that did send over-limit requests, always-cloud-fcfs at seed 7, got back no prompt_tokens, no
# http_status and the 'X' no-letter sentinel, with one of the two recorded as delivered ON TIME
# 17 ms after submission.
# D223 (2): the limit is no longer a constant here. It is the SERVER'S CONFIGURED max-model-len,
# read once at run start from the server's own argv (D56: capacities are inputs), and every read
# below is a CALL made at decision time. The module attribute is kept as a live read through
# PEP 562 `__getattr__`, because `d170_rule_proofs.py:50` does `LIMIT = HA.CONTEXT_LIMIT_TOKENS`
# and that proof must keep testing the limit the run is actually enforcing, not a stale copy of it.
import context_limit as CL                                                   # noqa: E402


def __getattr__(name):
    if name == "CONTEXT_LIMIT_TOKENS":
        return CL.limit_tokens()
    raise AttributeError(name)


class HybridArm:
    """Built on the committed b7 live2 wrapper; see the module docstring."""

    SWITCHES = ("c1", "c2", "c3", "c4", "c5", "c6")
    # D170's switch as a CLASS-LEVEL DEFAULT, read-only, with every instance setting its own in
    # __init__. The instance value is what ablates; this default exists because the recall loop is
    # BORROWED by objects that never ran HybridArm.__init__ (the counterfactual's mirror of the
    # base is one), and on those `self.over_limit_infeasible` raised AttributeError inside a
    # generic except, which silently changed plan_state's candidate scoring: covex-v6-state's dry
    # log moved 15,734 to 15,954 rows and covex-v6-state-off, which has plan_state off, did not.
    # This is the mirror image of the earlier flags-as-class-attributes bug: there a class
    # attribute with no instance value broke the negative control, here a missing class default
    # broke a borrowed method.
    over_limit_infeasible = False

    def __init__(self, name: str = "hybrid-base", c1=False, c2=False, c3=False, c4=False, c5=False, c6=False,
                 k_r: float = 1.0, m_d: float = 0.05, defs: str = "v1", reserve: Optional[bool] = None,
                 throttle_floor: int = 2, c3_always: bool = False, workload: str = "mixed",
                 k_r_frac: Optional[float] = None, quality_fit: str = "trace_mix",
                 c6_robot_only: bool = False, c6_mirror_all_periods: bool = False,
                 c3_value_reader: bool = False, value_transform: str = "none",
                 over_limit_infeasible: bool = False) -> None:
        from arms_published import B7EdfFeasibilityArm
        self._b7 = B7EdfFeasibilityArm()
        self.name = name
        # D170. DEFAULT OFF so no committed arm's decisions move; enabled by the ladder arms that
        # have no cells yet, and proved to change nothing on the committed ones.
        self.over_limit_infeasible = bool(over_limit_infeasible)
        self.sw = dict(c1=bool(c1), c2=bool(c2), c3=bool(c3), c4=bool(c4), c5=bool(c5), c6=bool(c6))
        self.k_r, self.m_d = float(k_r), float(m_d)
        # D143 ruling B: k_r scales with each device type's OWN deadline, k_r = 0.3 x deadline, so a
        # robot gets 1.5 s and a single-shot request 0.6 s. The SAME rule expressed as a fraction;
        # no new tuned number is introduced.
        #
        # Why it was needed. The flat 1.5 s was chosen against a 5 s robot deadline. Against a 2 s
        # SS deadline the at-risk test, laxity < k_r + work, fires once slack falls below about
        # 1.84 to 2.06 s depending on prompt size, which is 92 to 100 percent of an SS request's
        # whole life: the flag switched on after roughly 0.1 s of queueing while measured cloud TTFT
        # p50 was 0.3225 s against that 2 s deadline. A threshold whose window spans almost the
        # entire lifetime of a device type is not a risk detector for that type, it is a constant,
        # and it drove the dashcam throttle: at 12 devices 55 of 118 SS requests were flagged while
        # only about 2 of the at-risk entities were robots, holding 1,516 dashcam submissions.
        #
        # ROBOTS ARE UNCHANGED, exactly. 0.3 x 5.0 is 1.5 in float64 with no representation error
        # (both are 3/2), so every robot comparison is bit-identical to the flat 1.5 s and the whole
        # effect of this ruling is confined to single-shot. That is what makes byte-identity with SS
        # absent the right proof for it.
        #
        # None keeps the committed flat scalar, so every run before this parameter existed is
        # unchanged.
        self.k_r_frac = None if k_r_frac is None else float(k_r_frac)
        # D144 ruling 4: C6 robot-only, as D143 ruling C already stated the design to be. It is a
        # SEPARATE ARM (hybrid-F6r), not a change to hybrid-F6, because the gate is not
        # decision-preserving: at 20 devices it deletes one single-shot deviation
        # (c6_dev_send_to_hold), so D108 / D121 byte-identity cannot hold and D79 applies.
        #
        # It gates BOTH consumers of the switch: the per-period policy-core mirror in _c6_prepare,
        # which is where the cost is (measured 94 percent of C6 calls were on single-shot requests,
        # and the SS-only periods paid p50 42.6 to 133.5 ms against a 100 ms decision period), and
        # the per-request _c6_one. Gating only the second would keep the whole cost.
        # D149 / D152 (2), DEFAULT OFF: replace C3's feasibility-triggered RECENT fallback with
        # the value reader. `value_transform` is the D149 (4) acceptance control: flattening or
        # inverting the table MUST change decisions, and it runs through the same code path as the
        # real table so the control cannot differ from the thing it controls.
        self.c3_value_reader = bool(c3_value_reader)
        self.value_transform = str(value_transform)
        self._value_table = None
        self.c6_robot_only = bool(c6_robot_only)
        # MEASURED, not anticipated: gating the mirror as well is NOT robot-side neutral. The mirror
        # is a policy-core instance advanced once per period (_c6_prepare's own docstring: "advance
        # the policy-core mirror to this period"), so it carries state across periods. Skip the
        # single-shot-only periods and the mirror arrives at the next robot period having never seen
        # them, which changed 2 robot decisions and 82 dashcam decisions at 16 devices seed 0.
        #
        # So there are two robot-only arms, and the difference between them is the whole question:
        #   c6_mirror_all_periods False (hybrid-F6r)  cheap, robot decisions may differ from F6
        #   c6_mirror_all_periods True  (hybrid-F6rm) robot decisions identical to F6, no saving,
        #                                             because the mirror IS the cost
        self.c6_mirror_all_periods = bool(c6_mirror_all_periods)
        # D140 definition fixes. "v1" = the definitions screened first (labelled "old at-risk / old cap"):
        #   robot at risk when slack < k_r or laxity < 0; C5's cap holds every kind; reserved slot = C2.
        # "v2": robot at risk when LAXITY < k_r, laxity = deadline - now - predicted remaining work (committed
        #   cost curve, including a cold rebuild of the believed un-built history); C5's cap holds DASHCAM traffic
        #   only (robot recall / rebuild work is never held by it); the reserved slot is its own switch.
        if defs not in ("v1", "v2"):
            raise ValueError("defs must be v1 or v2")
        self.defs = defs
        self.reserve = (bool(c2) if reserve is None else bool(reserve)) if defs == "v1" else bool(reserve)
        # D141 (user ruling): in v2 the CONSUMER of C2's robot at-risk flag is a DASHCAM THROTTLE: while any robot
        # question has laxity < k_r (pending, or released while at risk and not yet completed / expired), no NEW
        # dashcam frame is submitted beyond `throttle_floor` dashcam requests in flight; an at-risk dashcam device
        # (running on-time < 0.25 + m_d) is exempt. Robots stay exempt from the cap.
        self.throttle_floor = int(throttle_floor)
        # D141 ablation "C3-always": degrade EVERY at-risk robot to RECENT, even when the rebuild is predicted
        # feasible. Not a candidate default (judged on LH-REQ later).
        self.c3_always = bool(c3_always)
        self._risk_inflight: Dict[str, float] = {}       # query id -> deadline, released while at risk
        # D140 C6 line: a robot for which the chooser picked "longer dashcam throttle" holds the throttle floor at 0
        # until it completes or its deadline passes
        self._long_throttle: Dict[str, float] = {}
        self._risk_seen: set = set()
        # D142 item 5 / the "both workloads" ruling: the robot question set is SELECTABLE, and the C1
        # value term follows it. The capability is built for both; D142 item 1 rules that live policy
        # EVALUATION uses LH-REQ only and never MIXED. Those are consistent: capability, not evaluation.
        if workload not in WORKLOADS:
            raise ValueError("workload must be one of %r" % (WORKLOADS,))
        self.workload = workload
        # D143 ruling A: the C6 mirror's cross-tier comparator must read the LH-REQ table fitted on
        # the DEV split when robots draw from LH-REQ. It is passed to the mirror at configure time,
        # never swapped afterwards: the comment in arms_policy.live2_configure records what a
        # post-configure swap did when it was measured (dashcam 0.0821 and 0 recalls served).
        if quality_fit not in ("trace_mix", "lh_req_dev"):
            raise ValueError("quality_fit %r must be 'trace_mix' or 'lh_req_dev'" % (quality_fit,))
        self.quality_fit = quality_fit
        self.values = _quality_values(workload) if any(self.sw.values()) else None
        self._ss_tbl = _ss_table() if any(self.sw.values()) else {}
        self._ss_types = frozenset((self._ss_tbl.get("question_type_to_representation") or {}))
        self._ss_values = _ss_values(self._ss_tbl)
        self._ss_placeholder = bool(self._ss_tbl.get("_placeholder"))
        self.cap, self._last_adj = 8, None
        self.cap_ceiling = self.cap
        self.c2_epoch = None
        # ---- C5 ATTRIBUTION, a CANDIDATE and DEFAULT OFF (user ruling 2026-11-22 addendum) ----
        # An INSTANCE attribute, not a class attribute and not a module global. Both of the
        # others have cost real cells here: a module global that defaulted ON once cost a whole
        # live cell, and a class attribute left ON under an `-off` arm made a negative control
        # that did not collapse (arms_v6state.py's own note). Nothing in this file turns it on;
        # only `arms_v6c5.covex-v6-state-uo-c5attr` does, and it sets it on THIS object.
        #
        # THE RULE. The AIMD cap exists to back off from ENGINE OVERLOAD. A monitor whose wait
        # overlapped a robot prefill the coordinator ITSELF released is not evidence of overload;
        # it is evidence of our own scheduling. So when every slow monitor seen since the last
        # cap adjustment is of that kind, the halving is SUPPRESSED (the cap is HELD, neither
        # halved nor stepped up, and the recovery timer is not restarted).
        self.c5_attr_self_released = False
        # (ttft_s, overlapped a self-released robot prefill) per monitor completion since the
        # last cap adjustment. Only filled while the rule is on, so an arm with it off carries
        # the same state it always did.
        self._attr_mon: list = []
        self.stats = Counter()
        self._roster: Dict[str, Any] = {}
        self._scorer = None                  # C6: a policy-core instance used ONLY as state mirror + rollout
        self._chooser = None

    # ---- delegate every live2 hook to the committed b7 wrapper (the base) --------------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_b7"], k)

    def __call__(self, obs: Observation) -> Action:
        # identical entry path to b7's (Policy.__call__ scrubs, validates, applies defaults), with our decide
        return self._b7.__class__.__call__(self, obs) if hasattr(self._b7.__class__, "__call__") else self.decide(obs)

    # The roster (each dashcam instant's own deadline, session ownership, built tokens) is what C1 / C2 read
    # for dashcam deadlines, and what the C6 mirror needs. b7 declares no live2_roster and receives nothing,
    # so storing it here cannot change the base's decisions (proved by the identity test).
    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._roster = dict(roster or {})
        if self._scorer is not None:
            self._scorer.live2_roster(dict(self._roster))

    def live2_configure(self, **kw: Any) -> None:
        self._b7.live2_configure(**kw)
        if self.sw["c6"]:
            import arms as A
            CH = _chooser_module()
            self._scorer = A.make_arm("policy-core")
            self._scorer.quality_fit = self.quality_fit
            self._scorer.live2_configure(**kw)
            self._chooser = CH.Chooser(enabled=True, delta=0.0)
        if self.c3_value_reader and self._value_table is None:
            self._value_table = VR.ValueTable(transform=self.value_transform)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._b7.live2_describe()) if hasattr(self._b7, "live2_describe") else {}
        d.update(hybrid=dict(self.sw, k_r=self.k_r, k_r_frac=self.k_r_frac, m_d=self.m_d,
                             defs=self.defs, reserve=self.reserve, workload=self.workload,
                             quality_fit=self.quality_fit,
                             throttle_floor=self.throttle_floor, c3_always=self.c3_always),
                 hybrid_name=self.name)
        return d

    # ---- the decision ------------------------------------------------------------------------------------

    # ---- D182 / addendum 12 item 3(a): the DEFICIT ORDERING hook. BEGIN contiguous block -------
    # This file is the FROZEN base shared by every arm, including every baseline, so the ordering
    # consumer is added as a HOOK WITH A NEUTRAL DEFAULT rather than as a new sort term. The
    # default returns 0.0 for every item, and prepending a CONSTANT to a sort key cannot change
    # the order of anything, so every existing arm's ordering is unchanged by construction and
    # provable on a digest. Only the rung-3 arm overrides it.
    #
    # The warning at the top of this file applies directly: do not put a made-up number into the
    # ordering index of a frozen policy. That is why this is a separate leading key rather than a
    # factor folded into `idx`, which would have changed the frozen C1 index itself.
    def _device_of(self, session_id):
        """Device id for a recall/assistance session, via the roster's own mapping.

        `RecallQuery` carries no device_id (its fields are query_id, session_id, category,
        arrival_s, deadline_s, evidence, readiness, readiness_tokens, device_answer_confidence,
        question_id), so the device has to be resolved rather than read.
        """
        return ((self._roster or {}).get("session_device", {}) or {}).get(session_id)

    def _deficit_order_key(self, device_id, kind):
        """Negative per-device deficit weight, so a LARGER w_d sorts FIRST. 0.0 when inactive."""
        return 0.0
    # ---- END D182 block ------------------------------------------------------------------------
    def decide(self, obs: Observation) -> Action:
        if not any(self.sw.values()):
            return self._b7.decide(obs)                        # THE BASE: b7 exactly
        now = obs.now_s
        in_flight = sum(int(v) for v in (obs.cloud.running_by_class or {}).values())
        roster = (self._roster or {}).get("sh_instant", {})
        epi_s = float(C.episodic_cloud_latency_s("32BI", 1, 25))
        items = []
        for s in obs.streams:                                  # dashcam instants
            inst = roster.get(s.stream_id)
            dl = float(inst["deadline_abs"]) if inst else now + DASH_DEADLINE_S
            slack = dl - now - epi_s
            recent = [t for t in s.delivered_times_s if t > now - 60.0]
            frac = len(recent) / max(60.0 / max(s.cadence_s, 1e-3), 1.0)
            risk = self.sw["c2"] and (frac < 0.25 + self.m_d)
            # D182: `device_id` carried so the ordering hook can key PER DEVICE. Without it the
            # hook receives None for every dashcam item and a per-device weight collapses to one
            # value, which would have looked like an ordering that fired and did nothing.
            # `EpisodicStream` has no device_id field; its stream_id IS the device id, which is
            # how `roster.get(s.stream_id)` already resolves this object elsewhere in this method.
            # The previous `getattr(s, "device_id", None)` returned None on EVERY call, so the
            # ordering hook saw one distinct argument value across 10,956 invocations and a
            # per-device weight collapsed to a single number. That is the exact failure this field
            # was added to prevent, and it was caught by counting the hook's distinct arguments
            # rather than by reading the code.
            items.append(dict(kind="dash", id=s.stream_id, dl=dl, slack=slack, work=epi_s, risk=risk,
                              device_id=s.stream_id,
                              value=(self.values or {}).get("dashcam", 0.09)))
        rec_dec: Dict[str, RecallAction] = {}
        pending_risk: List[Any] = []
        _ss_risk_n = 0
        c6_recall = bool(obs.recall)
        if c6_recall and self.c6_robot_only and not self.c6_mirror_all_periods:
            c6_recall = any(getattr(q, "category", None) not in self._ss_types for q in obs.recall)
        c6_live = self.sw["c6"] and self._scorer is not None and c6_recall and self._c6_prepare(obs)
        for q in sorted(obs.recall, key=lambda x: (
                self._deficit_order_key(self._device_of(getattr(x, "session_id", None)), "recall"),
                x.deadline_s)):
            est = float(C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness))
            qs = q.slack_s(now)
            slack = qs - est
            if self.defs == "v1":
                risk = self.sw["c2"] and (qs < self._k_r_for(q) or slack < 0)
            else:
                work = est + self._unbuilt_rebuild_s(q)
                laxity = qs - work
                risk = self.sw["c2"] and (laxity < self._k_r_for(q))
            est_gate = est
            if LA.arm_enables(self):                      # READ SITE of live2_la_arrival_admission
                est_gate = self._la_gate_est(q, obs, now, est, qs)
            over_limit = (self.over_limit_infeasible
                          and int(getattr(q, "readiness_tokens", 0) or 0) > CL.limit_tokens())
            if over_limit:
                # INFEASIBLE, not deferred and not retried smaller: the engine cannot answer this
                # prompt at any time, so the question is the device's and the arm is charged for
                # the send it did not make (D170, D144 (3)).
                d = RecallAction(q.query_id, "REJECT")
                self.stats["over_limit_infeasible"] += 1
                self.stats["over_limit_tokens_max"] = max(
                    int(self.stats.get("over_limit_tokens_max", 0)),
                    int(getattr(q, "readiness_tokens", 0) or 0))
            elif est_gate <= qs:
                d = RecallAction(q.query_id, "CLOUD")
            elif est_gate <= qs + self._b7.defer_s:
                d = RecallAction(q.query_id, "DEFER", defer_s=self._b7.defer_s)
            else:
                d = RecallAction(q.query_id, "REJECT")
            if LA.arm_enables(self):
                self._la_dec_final(d.decision, over_limit)
            is_ss = bool(getattr(q, "category", None) in self._ss_types)
            if is_ss:
                self.stats["ss_seen"] += 1
                if risk:
                    self.stats["ss_at_risk"] += 1
                    _ss_risk_n += 1
            # D142 item 3, C2 for single-shot. The SAME laxity test and the SAME k_r as the robot flag (no new
            # threshold), consumed by the SAME dashcam throttle, which is the one C2 consumer D141 proved moves
            # decisions (3,570) where the reserved slot was an ABSENT LINK (0 at both k_r). An SS request near
            # its 2-s deadline therefore throttles dashcam frames exactly as an at-risk robot does.
            #
            # C3 is DELIBERATELY NOT applied to an SS request. An SS request carries no history, so RECENT and
            # D2 are the SAME single image: degrading buys no quality (the declared input records them as
            # equal, not ordered) while the coordinator would charge RECENT_WINDOW_TOKENS = 467 and answer on
            # a truncated image prompt. The representation axis does not exist for this device type.
            if self.sw["c3"] and self.c3_always and risk and not is_ss \
                    and d.decision == "CLOUD" and d.representation is None:
                d = RecallAction(q.query_id, "CLOUD", representation="RECENT")
                self.stats["c3_always_recent"] += 1
            if self.sw["c3"] and not is_ss and d.decision != "CLOUD":
                est_r = float(C.recall_ttft_s(RECENT_TOKENS, "COLD"))
                if self.c3_value_reader:
                    # D149 / D152 (2): the fallback asks whether the answer would be any GOOD, not
                    # merely whether it would arrive. A representation is sent only if
                    # P(on time) x accuracy beats the device's own answer. On the committed DEV
                    # table cloud RECENT and the device are both 0.107143, so RECENT never
                    # strictly beats the device and the RECENT-only shortcut disappears, which is
                    # what D152 (2) rules and what it predicted would "fall out of the value
                    # reader" rather than need a rule of its own.
                    vr = VR.choose(("RECENT",),
                                   lambda rep, _q=qs, _e=est_r: 1.0 if _e <= _q else 0.0,
                                   self._value_table,
                                   history_tokens=getattr(q, "readiness_tokens", None))
                    self.stats["c3_value_considered"] += 1
                    if vr["send"]:
                        d = RecallAction(q.query_id, "CLOUD", representation=vr["representation"])
                        self.stats["c3_value_sent"] += 1
                    else:
                        self.stats["c3_value_withheld"] += 1
                elif est_r <= qs:
                    d = RecallAction(q.query_id, "CLOUD", representation="RECENT")
                    self.stats["c3_recent"] += 1
            if c6_live and not (self.c6_robot_only and is_ss):
                d = self._c6_one(q, d, at_risk=bool(self.defs == "v2" and risk))
            rec_dec[q.query_id] = d
            if self.defs == "v2" and self.sw["c2"] and risk:
                pending_risk.append((q.query_id, float(q.deadline_s), d.decision == "CLOUD"))
            if d.decision == "CLOUD":
                items.append(dict(kind="recall", id=q.query_id, dl=q.deadline_s, slack=slack, risk=risk,
                                  device_id=self._device_of(q.session_id),
                                  work=float(C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)),
                                  value=(self._ss_values.get(q.category, 1e-3) if is_ss
                                         else (self.values or {}).get("recall", 0.1))))
        self.c2_epoch = (float(now), sum(1 for it in items if it["kind"] == "dash" and it["risk"]), _ss_risk_n)
        # order
        def idx(it):
            return it["value"] * (1.0 / max(it["slack"], 0.1)) / max(it["work"], 1e-3)
        if self.sw["c1"]:
            items.sort(key=lambda it: (self._deficit_order_key(it.get("device_id"), it["kind"]),
                                       not it["risk"], -idx(it), it["dl"], it["id"]))
        else:
            items.sort(key=lambda it: (self._deficit_order_key(it.get("device_id"), it["kind"]),
                                       not it["risk"], it["dl"], it["id"]))
        # cap (C5); without C5 the base has none, as b7
        if self.sw["c5"]:
            self._aimd(obs)
            if self.defs == "v2":
                keep = self._cap_dashcam_only(obs, items, self._throttle_on(now, pending_risk))
            else:
                keep = None
            budget = max(self.cap - in_flight, 0)
            chosen, reserved = [], 1 if self.reserve else 0
            for it in (items if keep is None else ()):
                if len(chosen) >= budget:
                    break
                if reserved and it["kind"] != "recall" and len(chosen) >= budget - reserved \
                        and not any(x["kind"] == "recall" and x["risk"] for x in chosen):
                    if any(x["kind"] == "recall" and x["risk"] for x in items):
                        continue                           # keep the slot for at-risk recall work
                chosen.append(it)
            if keep is None:
                keep = {(it["kind"], it["id"]) for it in chosen}
        elif self.defs == "v2" and self.sw["c2"]:
            keep = self._cap_dashcam_only(obs, items, self._throttle_on(now, pending_risk), cap=None)
        else:
            keep = {(it["kind"], it["id"]) for it in items}
        order = [it for it in items if (it["kind"], it["id"]) in keep]
        streams = [StreamAction(it["id"], "cloud") for it in order if it["kind"] == "dash"]
        streams += [StreamAction(s.stream_id, "local") for s in obs.streams if ("dash", s.stream_id) not in keep]
        recall = []
        for it in order:
            if it["kind"] == "recall":
                recall.append(rec_dec[it["id"]])
        for qid, d in rec_dec.items():
            if d.decision == "CLOUD" and ("recall", qid) not in keep:
                recall.append(RecallAction(qid, "DEFER", defer_s=0.0))
            elif d.decision != "CLOUD":
                recall.append(d)
        self.stats["decisions"] += 1
        return Action(streams=streams, recall=recall, order="EDF", notes={"hybrid": self.name})

    def _la_gate_est(self, q, obs, now: float, est_iso: float, qs: float) -> float:
        """Load-aware arrival estimate (la_arrival_admission). Counts, logs and returns the estimate
        the unchanged comparator then uses in place of the isolated one."""
        roster = self._roster or {}
        u, rule = LA.uncached_for(q, roster)
        ahead = LA.queued_ahead(obs)
        est_la = LA.loadaware_est(u, ahead)
        dfr = self._b7.defer_s
        o_iso, o_la = LA.outcome(est_iso, qs, dfr), LA.outcome(est_la, qs, dfr)
        st = self.stats
        st["la_arrival_evals"] += 1
        st["la_est_isolated_milli_sum"] += int(round(est_iso * 1000.0))
        st["la_est_loadaware_milli_sum"] += int(round(est_la * 1000.0))
        st["la_queued_ahead_tokens_sum"] += int(ahead)
        st["la_rule_" + rule] += 1
        if ahead > 0:
            st["la_queued_ahead_positive"] += 1
        if est_la > est_iso:
            st["la_est_greater"] += 1
        if o_iso != o_la:
            st["la_decision_changed_vs_isolated"] += 1
            st["la_changed_%s_to_%s" % (o_iso, o_la)] += 1
            log = self.__dict__.setdefault("_la_log", [])
            if len(log) < 400:
                log.append(dict(t=round(float(now), 3), query_id=q.query_id, device=str(q.session_id),
                                iso=o_iso, la=o_la, est_iso=round(est_iso, 4), est_la=round(est_la, 4),
                                slack_s=round(qs, 4), u=int(u), queued_ahead=int(ahead), rule=rule))
        pb = (roster.get("pb_cached_by_session") or {}).get(str(q.session_id))
        ntok = max(int(q.readiness_tokens), 1)
        pc = None if pb is None else min(int(pb.get("cached", 0)), ntok)
        dec = self.__dict__.setdefault("_la_dec_rows", [])
        seq = self.__dict__.setdefault("_la_dec_seq", {})
        seq[q.query_id] = seq.get(q.query_id, 0) + 1
        dec.append(dict(t=round(float(now), 4), device_id=self._device_of(q.session_id),
                        session_id=str(q.session_id), query_id=q.query_id,
                        question_id=getattr(q, "question_id", None), eval_seq=seq[q.query_id],
                        kind=str(getattr(q, "category", None)),
                        is_single_shot=bool(getattr(q, "category", None) in self._ss_types),
                        prompt_tokens=ntok, p_cached_tokens=pc,
                        p_cached_frac=None if pc is None else round(pc / ntok, 6),
                        uncached_u=int(u), queued_ahead=int(ahead), rule=rule,
                        est_isolated_s=round(est_iso, 6), est_loadaware_s=round(est_la, 6),
                        slack_s=round(qs, 6), isolated_decision=o_iso, la_decision=o_la,
                        decision=o_la, changed=bool(o_iso != o_la), over_limit=False,
                        deadline_s=round(float(q.deadline_s), 4)))
        samp = self.__dict__.setdefault("_la_est_samples", [])
        if len(samp) < 20000:
            samp.append((round(est_la, 4), int(ahead), int(u)))
        return est_la

    def _la_dec_final(self, decision: str, over_limit: bool) -> None:
        """Logging only: the decision the gate returned (differs from the comparator outcome only
        when the over-limit rule fires). A DEFER re-appears as a later row with the same query_id
        and a higher eval_seq."""
        rows = self.__dict__.get("_la_dec_rows")
        if rows:
            rows[-1]["decision"] = str(decision)
            rows[-1]["over_limit"] = bool(over_limit)

    def _unbuilt_rebuild_s(self, q) -> float:
        """v2 laxity: the cold rebuild of the believed UN-BUILT part of the history. A COLD history's rebuild is
        already the whole of `recall_ttft_s(tokens, COLD)`; for a warm one, the tokens the cloud has not built
        (roster `built_tokens_by_session`) are charged at the committed cold curve."""
        if q.readiness == "COLD":
            return 0.0
        built = int(((self._roster or {}).get("built_tokens_by_session") or {}).get(q.session_id, q.readiness_tokens))
        unbuilt = max(int(q.readiness_tokens) - built, 0)
        return float(C.recall_ttft_s(unbuilt, "COLD")) if unbuilt > 0 else 0.0

    def _k_r_for(self, q) -> float:
        """This item's at-risk threshold. D143 ruling B: a fraction of the item's OWN deadline.

        THE DEADLINE HORIZON IS deadline_s MINUS arrival_s, not deadline_s. `RecallQuery.deadline_s`
        is an ABSOLUTE time on the run clock, as `slack_s(now) = deadline_s - now` shows; the trace
        RECORD's field of the same name is the duration L. Same name, two definitions, which is
        check 4's job. Multiplying the absolute time was measured, not reasoned about: it made
        k_r grow with the clock, flagged effectively every robot at risk, and broke byte-identity
        with the screened arm on 6,253 of 6,431 decisions. The horizon derived here is 5.0 s for a
        robot and 2.0 s for a single-shot request, from the item's own two fields, so no new
        constant and no per-type table is introduced.

        A non-positive horizon falls back to the flat scalar and is COUNTED rather than silently
        producing a threshold of zero, which would read as "never at risk".
        """
        if self.k_r_frac is None:
            return self.k_r
        horizon = float(q.deadline_s) - float(q.arrival_s)
        if not horizon > 0.0:
            self.stats["k_r_horizon_nonpositive"] += 1
            return self.k_r
        return self.k_r_frac * horizon

    def _throttle_on(self, now: float, pending_risk) -> bool:
        """C2 (v2) robot channel: is any robot question at risk now? Pending at-risk questions count; one released
        while at risk keeps the throttle on until it completes (live2_completed) or its deadline passes."""
        for qid, dl in list(self._risk_inflight.items()):
            if dl < now:
                del self._risk_inflight[qid]
        for qid, dl, released in pending_risk:
            if released:
                self._risk_inflight[qid] = dl
        for qid, dl in list(self._long_throttle.items()):
            if dl < now:
                del self._long_throttle[qid]
        on = bool(pending_risk) or bool(self._risk_inflight) or bool(self._long_throttle)
        if on:
            self.stats["c2_throttle_periods"] += 1
            for qid, _dl, _r in pending_risk:
                if qid not in self._risk_seen:
                    self._risk_seen.add(qid)
                    self.stats["c2_robots_at_risk_while_throttling"] += 1
        return on

    def live2_completed(self, info: Dict[str, Any]) -> None:
        """Only the v2 C2 throttle reads completions (a robot released at risk ends the throttle when it completes);
        b7 declares no live2_completed, so this cannot change the base's decisions (identity test)."""
        if self.c5_attr_self_released and info.get("kind") == "monitor":
            # the two keys the coordinator adds for this rule; the overlap test is ITS work,
            # because only the coordinator knows what it released and when
            _t0, _tf = info.get("t_submit"), info.get("t_first_token")
            if _t0 is not None and _tf is not None:
                self._attr_mon.append((float(_tf) - float(_t0),
                                       bool(info.get("self_released_prefill_overlap"))))
                if len(self._attr_mon) > 256:
                    del self._attr_mon[:-256]
        for store in (self._risk_inflight, self._long_throttle):
            if store:
                for k in (info.get("opportunity_id"), info.get("decision_id")):
                    if k in store:
                        del store[k]

    def _cap_dashcam_only(self, obs: Observation, items, throttle: bool = False, cap: Optional[int] = -1) -> set:
        """v2 C5: the cap counts and holds dashcam (episodic) traffic only; every robot item is kept. With the
        reserve switch on, one dashcam slot is withheld while an at-risk robot item is pending (ablation)."""
        epi = int((obs.cloud.running_by_class or {}).get("episodic", 0))
        cap_n = self.cap if cap == -1 else (10 ** 9 if cap is None else int(cap))
        budget = max(cap_n - epi, 0)
        cap_budget = budget
        if throttle:
            floor = 0 if self._long_throttle else self.throttle_floor
            budget = min(budget, max(floor - epi, 0))
        if self.reserve and any(it["kind"] == "recall" and it["risk"] for it in items):
            budget = max(budget - 1, 0)
            self.stats["c5_reserve_applied"] += 1
        keep, n_d, n_thr = set(), 0, 0
        for it in items:
            if it["kind"] == "recall":
                keep.add((it["kind"], it["id"]))
            elif n_d < budget:
                keep.add((it["kind"], it["id"]))
                n_d += 1
            elif throttle and it["risk"] and n_d < cap_budget:
                keep.add((it["kind"], it["id"]))          # an at-risk dashcam device is exempt from the throttle
                n_d += 1
                self.stats["c2_throttle_exempt_dash"] += 1
            elif throttle and n_d < cap_budget:
                n_thr += 1
        self.stats["c2_throttled_dash"] += n_thr
        self.stats["c5_dash_held"] += sum(1 for it in items if it["kind"] == "dash") - n_d
        return keep

    # ---- C6: flash's counterfactual chooser, per robot question ----------------------------------------
    def _c6_prepare(self, obs: Observation) -> bool:
        """Advance the policy-core mirror to this period (its decisions are NEVER executed; the same
        evaluator pattern as arms_covex_v2), so its fleet holds the question's job and pending pieces."""
        try:
            self._scorer.live2_roster(dict(self._roster))
            self._scorer.decide(obs)
            return True
        except MissingEvidence:
            # NOT swallowed. A missing committed quantity is a configuration error, not a transient:
            # swallowing it counted C6 out of every -lhreq cell while the arm still reported c6=True.
            raise
        except Exception as e:                                                  # noqa: BLE001
            self.stats["c6_scorer_error"] += 1
            self._c6_last_error = repr(e)[:300]
            return False

    def _c6_one(self, q, d: RecallAction, at_risk: bool = False) -> RecallAction:
        """Candidates for ONE robot question, proposed by the components: the C2/C3 choice is the default;
        the alternatives are send-now (full D2), hold (defer) and decline. Each is expressed in the mirror's
        own item ids as `Rollout.run` kwargs and simulated to the question's deadline by the chooser."""
        CH = sys.modules["policy_chooser"]
        f = self._scorer.fleet
        jid = getattr(self._scorer, "_jobs_by_q", {}).get(q.query_id)
        if jid is None:
            self.stats["c6_unmapped"] += 1
            return d
        ids = tuple(p.item_id for p in f.pending if getattr(p, "job_id", None) == jid)
        if not ids:
            self.stats["c6_no_pending"] += 1
            return d
        dl = float(q.deadline_s)
        opts = dict(send=CH.Candidate(kind="send", rollout_kwargs=dict(release_now=ids), deadline_s=dl),
                    hold=CH.Candidate(kind="hold", rollout_kwargs=dict(exclude=ids), deadline_s=dl),
                    decline=CH.Candidate(kind="decline", rollout_kwargs=dict(drop=ids), deadline_s=dl))
        is_recent = d.decision == "CLOUD" and d.representation == "RECENT"
        if at_risk or is_recent:
            # D140 C6 line: an at-risk robot adds "RECENT now" and "longer dashcam throttle".
            # RECENT now: in the rollout's own copy only, the question's job becomes a RECENT job (one piece of
            # RECENT_TOKENS, valued by the profile's RECENT accuracy via job.rep), released now; its full-history
            # pieces are dropped, so the question is counted once.
            import copy as _copy
            job = _copy.deepcopy(f.jobs[jid])
            job.rep, job.pieces_total, job.pieces_done, job.tokens_per_piece = "RECENT", 1, 0, RECENT_TOKENS
            first = next(p for p in f.pending if getattr(p, "job_id", None) == jid)
            rp = _copy.deepcopy(first)
            rp.item_id, rp.tokens, rp.readiness = "%s:RECENT-now" % jid, RECENT_TOKENS, "COLD"
            opts["recent"] = CH.Candidate(kind="recent", deadline_s=dl, rollout_kwargs=dict(
                drop=ids, extra_jobs={jid: job}, extra_pending=(rp,), release_now=(rp.item_id,)))
            self.stats["c6_offered_recent_and_throttle"] += 1
            # longer dashcam throttle: send the full rebuild now and hold every pending dashcam call in the rollout
            dash = tuple(p.item_id for p in f.pending if p.kind == "episode_call")
            opts["longer_throttle"] = CH.Candidate(kind="longer_throttle", deadline_s=dl,
                                                   rollout_kwargs=dict(release_now=ids, exclude=dash))
        mine = ("recent" if is_recent else "send" if d.decision == "CLOUD"
                else ("hold" if d.decision == "DEFER" else "decline"))
        dflt = opts[mine]
        cands = [dflt] + [c for k, c in opts.items() if k != mine]
        st = CH.ChooserState(rollout=self._scorer.rollout, fleet=f, now_s=float(f.t))
        self.stats["c6_calls"] += 1
        got = self._chooser.choose(cands, st, default=dflt)
        if got is dflt:
            return d
        self.stats["c6_dev_%s_to_%s" % (mine, got.kind)] += 1
        if got.kind == "send":
            return RecallAction(q.query_id, "CLOUD")
        if got.kind == "recent":
            return RecallAction(q.query_id, "CLOUD", representation="RECENT")
        if got.kind == "longer_throttle":
            self._long_throttle[q.query_id] = dl
            return RecallAction(q.query_id, "CLOUD")
        if got.kind == "hold":
            return RecallAction(q.query_id, "DEFER", defer_s=self._b7.defer_s)
        return RecallAction(q.query_id, "REJECT")

    def _attr_suppresses(self) -> bool:
        """The candidate attribution rule's test, run only when `c5_attr_self_released` is on.

        Suppress the halving when there IS slow-monitor evidence since the last adjustment and
        ALL of it overlapped a robot prefill this coordinator released. No slow evidence at all
        (the EWMA is high from older history) does NOT suppress: the rule only re-attributes
        lateness it can see, and inventing a suppression from an absence would make the cap
        unresponsive for a reason the data does not support.
        """
        slow = [ov for v, ov in self._attr_mon if v > 0.8 * DASH_DEADLINE_S]
        if not slow:
            self.stats["c5_attr_trip_without_slow_evidence"] += 1
            return False
        if all(slow):
            self.stats["c5_attr_slow_all_self_released"] += 1
            return True
        self.stats["c5_attr_slow_mixed"] += 1
        return False

    def _aimd(self, obs: Observation) -> None:
        lat = (obs.cloud.latency_estimate_s or {}).get("episodic")
        now = obs.now_s
        if lat is not None and lat > 0.8 * DASH_DEADLINE_S:
            if self._last_adj is None or now - self._last_adj >= 1.0:
                if self.c5_attr_self_released and self._attr_suppresses():
                    # HELD: no halving, no step up, and the recovery timer is NOT restarted, so
                    # the next genuine trip is still one second away and nothing is granted the
                    # cap that the AIMD rule would not have granted it.
                    self.stats["c5_attr_suppressed_decrease"] += 1
                    return
                self.cap = max(4, self.cap // 2)
                self._last_adj = now
                self.stats["c5_decrease"] += 1
                self._attr_mon.clear()
        elif self._last_adj is None or now - self._last_adj >= 5.0:
            if self.cap < 8:
                self.cap += 1
                self.stats["c5_increase"] += 1
            self._last_adj = now
            self._attr_mon.clear()


CONFIGS: Dict[str, Dict[str, Any]] = {
    "hybrid-base": {},
    "hybrid-c1": dict(c1=True),
    "hybrid-c1c2k1": dict(c1=True, c2=True, k_r=1.0),
    "hybrid-c1c2k2": dict(c1=True, c2=True, k_r=2.0),
    "hybrid-c1c2k1c3": dict(c1=True, c2=True, c3=True, k_r=1.0),
    "hybrid-c1c2k2c3": dict(c1=True, c2=True, c3=True, k_r=2.0),
    "hybrid-c5": dict(c5=True),
    "hybrid-c1c5": dict(c1=True, c5=True),
    "hybrid-c1c2k1c5": dict(c1=True, c2=True, c5=True, k_r=1.0),
    "hybrid-c1c2k2c5": dict(c1=True, c2=True, c5=True, k_r=2.0),
    "hybrid-all-k1": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.0),
    "hybrid-all-k2": dict(c1=True, c2=True, c3=True, c5=True, k_r=2.0),
}


# D140 (v2 definitions). The v1 names above stay as screened ("old at-risk / old cap").
CONFIGS.update({
    "hybrid2-c5": dict(c5=True, defs="v2"),
    "hybrid2-c1c5": dict(c1=True, c5=True, defs="v2"),
    "hybrid2-c1c2k05c5": dict(c1=True, c2=True, c5=True, k_r=0.5, defs="v2"),
    "hybrid2-c1c2k15c5": dict(c1=True, c2=True, c5=True, k_r=1.5, defs="v2"),
    "hybrid2-c1c2k05c3c5": dict(c1=True, c2=True, c3=True, c5=True, k_r=0.5, defs="v2"),
    "hybrid2-c1c2k15c3c5": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.5, defs="v2"),
    "hybrid2-all-k05": dict(c1=True, c2=True, c3=True, c4=True, c5=True, k_r=0.5, defs="v2"),
    "hybrid2-all-k15": dict(c1=True, c2=True, c3=True, c4=True, c5=True, k_r=1.5, defs="v2"),
    "hybrid2-c1c2k05c3c5-c3always": dict(c1=True, c2=True, c3=True, c5=True, k_r=0.5, defs="v2", c3_always=True),
    "hybrid2-c1c2k15c3c5-c3always": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.5, defs="v2", c3_always=True),
    # proof-only (Step 2b): the at-risk change isolated from the cap change
    "hybrid-c1c2k05": dict(c1=True, c2=True, k_r=0.5),
    "hybrid2-c1c2k05": dict(c1=True, c2=True, k_r=0.5, defs="v2"),
    "hybrid-c1c2k15": dict(c1=True, c2=True, k_r=1.5),
    "hybrid2-c1c2k15": dict(c1=True, c2=True, k_r=1.5, defs="v2"),
    "hybrid2-c1c2k05c5-reserve": dict(c1=True, c2=True, c5=True, k_r=0.5, defs="v2", reserve=True),
    "hybrid2-c1c2k15c5-reserve": dict(c1=True, c2=True, c5=True, k_r=1.5, defs="v2", reserve=True),
})

# ---------------------------------------------------------------------------------------------------
# D142: THE FROZEN POLICY. After the "policy-F ready" commit nothing in these two definitions changes;
# any change is a new labelled version and every policy cell is redone (D79).
#
#   hybrid-F  = C1 + C2(k_r 1.5 s, dashcam throttle floor 2, at-risk dashcam exemption)
#               + C3 (degrade to RECENT only when the full rebuild is predicted infeasible: the DEFAULT
#                 C3, NOT the c3_always ablation, which D141 showed is a different policy)
#               + C5 (dashcam-only AIMD cap); C4 inert; v2 definitions throughout.
#   hybrid-F6 = hybrid-F + C6, flash's committed chooser (70be641) with delta = 0.0.
#
# c4 is left False rather than True. D141 recorded all-on as byte-identical to C1+C2+C3+C5 because C4
# emits no session action, so the two spell the same policy; False is the one that cannot later diverge
# if C4 ever stops being inert.
#
# delta = 0.0 is RECORDED, not tuned, and no tuning happens after the freeze. It means C6 deviates only
# on a STRICT improvement in the rollout total (the comparison is `> delta`), so a tie keeps the
# component's own proposal. With no committed scale for the objective's units, any non-zero delta would
# be an invented number inside a frozen policy.
#
# D143 rulings A and B, applied here before the freeze.
#   B: k_r_frac = 0.3, so k_r = 0.3 x each type's own deadline (robot 1.5 s, SS 0.6 s). k_r stays
#      at 1.5 recorded, and 0.3 x 5.0 is exactly 1.5 in float64, so ROBOT decisions are unchanged
#      and the whole effect is on single-shot.
#   A: quality_fit = "lh_req_dev" on the "-lhreq" pair only, because the LH-REQ DEV table is the
#      right source only when robots actually draw from LH-REQ. The bare pair keeps the trace-mix
#      fit, which is correct for the MIXED workload it names.
CONFIGS.update({
    "hybrid-F": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.5, k_r_frac=0.3, defs="v2",
                     throttle_floor=2, c3_always=False, c4=False),
    "hybrid-F6": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.5, k_r_frac=0.3, defs="v2",
                      throttle_floor=2, c3_always=False, c4=False, c6=True),
})
# Both robot question sets selectable, as named arms so the workload is stated rather than inferred.
# The "-lhreq" pair is what D142 item 1 evaluates; the bare pair carries the MIXED weighting and is
# capability only.
CONFIGS.update({
    "hybrid-F-lhreq": dict(CONFIGS["hybrid-F"], workload="lh_req", quality_fit="lh_req_dev"),
    "hybrid-F6-lhreq": dict(CONFIGS["hybrid-F6"], workload="lh_req", quality_fit="lh_req_dev"),
})

# D144 ruling 4. hybrid-F6r = hybrid-F6 with C6 gated to non-single-shot recall. A NEW LABELLED ARM:
# hybrid-F6 and its cells stay exactly as they were measured, and F6r's cells run fresh (D79).
CONFIGS.update({
    "hybrid-F6r": dict(CONFIGS["hybrid-F6"], c6_robot_only=True),
})
CONFIGS.update({
    "hybrid-F6rm": dict(CONFIGS["hybrid-F6r"], c6_mirror_all_periods=True),
})
CONFIGS.update({
    "hybrid-F6r-lhreq": dict(CONFIGS["hybrid-F6r"], workload="lh_req", quality_fit="lh_req_dev"),
    "hybrid-F6rm-lhreq": dict(CONFIGS["hybrid-F6rm"], workload="lh_req", quality_fit="lh_req_dev"),
})

# C6 variants of every configuration (D138 follow-up): screening adds "<best>-c6" at 10 and 12 devices.
for _n, _k in list(CONFIGS.items()):
    CONFIGS[_n + "-c6"] = dict(_k, c6=True)


def register() -> None:
    import arms as A
    for name, kw in CONFIGS.items():
        A.ARMS[name] = (lambda n=name, k=kw: HybridArm(name=n, **k))


# D149 / D152 (2), DEFAULT OFF on hybrid-F itself: the value-reader arms. `hybrid-Fv` replaces C3's
# feasibility-triggered RECENT fallback with the reader; the `-flat` and `-invert` pair are D149
# (4)'s acceptance control, which must MOVE decisions against `hybrid-Fv` or the value table is
# decorative. All three are new labelled arms (D79), so hybrid-F's own cells are untouched.
CONFIGS.update({
    "hybrid-Fv": dict(CONFIGS["hybrid-F"], c3_value_reader=True),
    "hybrid-Fv-flat": dict(CONFIGS["hybrid-F"], c3_value_reader=True, value_transform="flat"),
    "hybrid-Fv-invert": dict(CONFIGS["hybrid-F"], c3_value_reader=True, value_transform="invert"),
})
CONFIGS.update({
    "hybrid-Fv-lhreq": dict(CONFIGS["hybrid-F-lhreq"], c3_value_reader=True),
    "hybrid-Fv-flat-lhreq": dict(CONFIGS["hybrid-F-lhreq"], c3_value_reader=True,
                                 value_transform="flat"),
    "hybrid-Fv-invert-lhreq": dict(CONFIGS["hybrid-F-lhreq"], c3_value_reader=True,
                                   value_transform="invert"),
})


# D152 (2) interim reference, requested by the H100 for the 3 s handful: hybrid-F with C3 OFF, so
# no RECENT fallback of any kind. A NEW LABELLED ARM under D79; hybrid-F's own cells are untouched.
# c3=False is the WHOLE change: k_r_frac stays 0.3, so k_r is 0.9 s at a 3 s deadline exactly as it
# is for hybrid-F, and C2's at-risk test, the dashcam throttle and C1/C4/C5 are unchanged.
CONFIGS.update({
    "hybrid-F-noc3": dict(CONFIGS["hybrid-F"], c3=False),
    "hybrid-F-lhreq-noc3": dict(CONFIGS["hybrid-F-lhreq"], c3=False),
})
