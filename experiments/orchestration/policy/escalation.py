"""Spec v3.1 addendum A1-A3 (D51-D53): ONE escalation basis for every request type.

    Ghat(r) = E[ u_cloud(r) - u_device(r) | observable features of r ]

computed from DEV lookup tables, NOT learned. No request type is routed to the cloud by a rule:
`ghat` is the only thing that decides, and the same Ghat enters the cloud's DeltaJ_H (A1), so
device-side triggering and cloud admission use one formula. `tests/test_escalation.py` asserts
this behaviourally for all three types.

THE FOUR FEATURES, and where each one's table comes from:

  evidence coverage   does the request reference time beyond the device's own window? COMMITTED:
                      in-window the device answers from its D2 history (StudyE7 Job A, 4B-D2),
                      out-of-window it answers from one frame (StudyF4 Part A, Jetson Orin N=1).
                      The gap between those two committed tables IS the value of the cloud
                      holding more evidence; nothing is invented for it.
  task-type posterior keyword and temporal-reference rules (A3), non-learned. The per-type base
                      gain is the committed DEV accuracy pair for that type.
  device uncertainty  the controller's own self-normalized signal (spec 7.7). NO committed DEV
                      table maps uncertainty to gain, so the multiplier is IDENTITY and is marked
                      PLACEHOLDER. Addendum A4 names the measurement that fills it: StudyCTRL1b's
                      predictability-ceiling arm. The slot is `GhatTables.uncertainty_multiplier`
                      and filling it changes no other code.
  timeliness          deadline against the delivered delay predicted on this device's link; a
                      cloud answer that cannot arrive in time has Ghat exactly zero.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .profiles import MissingEvidence, Profiles
from .utility import u_sh_cloud, u_sh_device

HISTORY_TYPES = ("counting_objects_events", "location_trace", "sequential_action",
                 "temporal_ordering_recognition", "time_duration", "visual_detail_recall")

PAST_REFERENCE = re.compile(
    r"\b(earlier|before|previous|previously|ago|last|first|then|after|when i|did i|had i|"
    r"minutes?|seconds?|hours?|yesterday|past)\b", re.I)
PRESENT_REFERENCE = re.compile(r"\b(now|current|currently|right now|this|ahead|in front)\b", re.I)
COUNT_WORDS = re.compile(r"\b(how many|count|number of)\b", re.I)
WHERE_WORDS = re.compile(r"\b(where|location|which (room|street|lane))\b", re.I)
ORDER_WORDS = re.compile(r"\b(order|sequence|first|then|after|before that)\b", re.I)
DURATION_WORDS = re.compile(r"\b(how long|duration|for how many)\b", re.I)
DETAIL_WORDS = re.compile(r"\b(what colour|what color|what kind|describe|what was)\b", re.I)


COMPLETE = "complete"
QUESTION_FIRST = "question_first"


@dataclass
class EscalationRequest:
    """A request of ANY type, as the escalation basis sees it (addendum A2).

    QUERIES ARE SENT COMPLETE BY DEFAULT: the question plus any payload the cloud lacks, which
    for SS is the current frame(s) and for RC is ONLY the history frames the cloud does not
    already hold. The cloud runs admission on arrival and DISCARDS a declined query; the device's
    answer stands. QUESTION-FIRST is an exception path, taken only when an RC query's unsent
    history exceeds a size threshold AND the device's uplink already carries higher-value
    traffic; then the question goes alone, the cloud decides, and on admission it pulls the
    missing frames.

    `payload_bytes` and `frames` describe what the cloud LACKS, whichever path is used; the path
    decides WHEN they travel, not whether they exist."""
    device: str
    task: str                                  # "SH" | "SS" | "RC"
    t: float
    text: Optional[str] = None
    temporal_reference_s: Optional[float] = None
    device_window_s: Optional[float] = None
    uncertainty: Optional[float] = None
    deadline: Optional[float] = None
    qtype: Optional[str] = None
    predicted_delivered_delay_s: Optional[float] = None
    payload_bytes: int = 0
    frames: int = 0
    question_bytes: int = 512
    unsent_history_bytes: int = 0
    path: Optional[str] = None
    payload_delivered: bool = False


@dataclass
class GhatTables:
    """Every table Ghat reads, so a caller can see and replace each one."""
    pf: Profiles
    uncertainty_multiplier: Callable[[Optional[float]], float] = None
    provenance: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.uncertainty_multiplier is None:
            self.uncertainty_multiplier = _identity_multiplier
        self.provenance = dict(
            evidence_coverage="COMMITTED: 4B-D2 (StudyE7 Job A) in window against "
                              "device-N1-orin (StudyF4 Part A) out of window",
            type_posterior="NON-LEARNED RULES (addendum A3): keyword and temporal-reference "
                           "rules; the device model labelling the question is a fallback only",
            per_type_base_gain="DEV: StudyPROF1-dev RC tables and omega_RC",
            sh_base_gain="DEV: StudyPROF1-dev u_SH curves and omega_SH",
            uncertainty_multiplier=("PLACEHOLDER, IDENTITY: no committed DEV table maps the "
                                    "controller's self-normalized signal to a gain. Addendum A4 "
                                    "names StudyCTRL1b's predictability-ceiling arm as the "
                                    "measurement that fills it."),
            timeliness="COMMITTED link constants: RTT 0.044 s and the 13.6 Mbit/s uplink "
                       "ASSUMPTION, plus the committed TTFT tables")


def _identity_multiplier(u: Optional[float]) -> float:
    return 1.0


def type_posterior(req: EscalationRequest) -> Dict[str, float]:
    """Addendum A3: P(type | observable) from non-learned rules.

    A request whose type is already known is a point mass. Otherwise the keyword and
    temporal-reference rules vote, and the mass is spread over the types they match; with no
    match the posterior is uniform over the committed question types, which is the honest reading
    of 'the rules are too coarse here'."""
    if req.qtype:
        return {req.qtype: 1.0}
    text = req.text or ""
    votes: Dict[str, float] = {}
    if COUNT_WORDS.search(text):
        votes["counting_objects_events"] = votes.get("counting_objects_events", 0.0) + 1.0
    if WHERE_WORDS.search(text):
        votes["location_trace"] = votes.get("location_trace", 0.0) + 1.0
    if ORDER_WORDS.search(text):
        votes["temporal_ordering_recognition"] = votes.get(
            "temporal_ordering_recognition", 0.0) + 1.0
        votes["sequential_action"] = votes.get("sequential_action", 0.0) + 1.0
    if DURATION_WORDS.search(text):
        votes["time_duration"] = votes.get("time_duration", 0.0) + 1.0
    if DETAIL_WORDS.search(text):
        votes["visual_detail_recall"] = votes.get("visual_detail_recall", 0.0) + 1.0
    if PAST_REFERENCE.search(text) and not votes:
        for k in HISTORY_TYPES:
            votes[k] = votes.get(k, 0.0) + 1.0
    if not votes:
        return {}
    s = sum(votes.values())
    return {k: v / s for k, v in sorted(votes.items())}


def evidence_coverage(req: EscalationRequest) -> Dict[str, Any]:
    """Does the request reference evidence the device still holds?

    Returns the coverage flag and which committed device table applies. Unknown reference and
    unknown window mean UNKNOWN, and unknown is treated as covered, which is the conservative
    direction: it credits the cloud with less, not more."""
    ref, win = req.temporal_reference_s, req.device_window_s
    if ref is None or win is None:
        txt = req.text or ""
        if PAST_REFERENCE.search(txt) and not PRESENT_REFERENCE.search(txt):
            return dict(covered=False, basis="past temporal reference in the text, no explicit "
                                             "offset", device_table="device-N1-orin")
        return dict(covered=True, basis="no temporal reference resolvable; treated as covered, "
                                        "which understates the cloud's gain",
                    device_table="4B-D2")
    covered = bool(ref <= win)
    return dict(covered=covered, reference_s=ref, window_s=win,
                basis="explicit temporal reference against the device's window",
                device_table=("4B-D2" if covered else "device-N1-orin"))


def _device_accuracy(pf: Profiles, qtype: str, table: str) -> float:
    if table == "4B-D2":
        return pf.rc_accuracy(qtype, "D2", "device")
    return pf.rc_accuracy(qtype, "N1", "device")


def ghat(req: EscalationRequest, tables: GhatTables, link=None,
         predicted_delay_s: Optional[float] = None,
         flags=None) -> Dict[str, Any]:
    """Addendum A1. Returns Ghat and EVERY term that produced it.

    This is the only function that decides whether a request is worth the cloud, for every task
    type. It never branches on the type to grant or deny escalation: the type only selects which
    committed table supplies the base gain."""
    pf = tables.pf
    mult = float(tables.uncertainty_multiplier(req.uncertainty))
    delay = (predicted_delay_s if predicted_delay_s is not None
             else req.predicted_delivered_delay_s)
    terms: Dict[str, Any] = dict(task=req.task, uncertainty_multiplier=mult,
                                 predicted_delivered_delay_s=delay)

    if req.deadline is not None and delay is not None and delay > req.deadline:
        terms.update(timeliness="MISSED: the predicted delivered delay exceeds the deadline, so "
                                "the cloud answer cannot serve this opportunity")
        return dict(ghat=0.0, terms=terms, posterior={}, coverage=None)

    if req.task == "SH":
        if delay is None:
            raise ValueError("an SH request needs a predicted delivered delay to score Ghat")
        u_c, in_range = u_sh_cloud(pf, delay, 1, allow_m_gt_1=bool(flags and flags.merging))
        u_d = u_sh_device(pf)
        g = pf.omega("SH") * (u_c - u_d) * mult
        terms.update(u_cloud=u_c, u_device=u_d, omega=pf.omega("SH"),
                     within_measured_delay=in_range,
                     table="StudyPROF1-dev u_SH, DEV")
        return dict(ghat=float(g), terms=terms, posterior={"SH": 1.0}, coverage=None)

    post = type_posterior(req)
    cov = evidence_coverage(req)
    if not post:
        raise MissingEvidence(
            "the task-type posterior is empty for this request: the addendum's keyword and "
            "temporal-reference rules matched nothing and no qtype was supplied, so Ghat cannot "
            "be computed from committed tables. Addendum A3's fallback (the device model "
            "labelling the question) is not implemented because no committed DEV measurement of "
            "its labelling accuracy exists.")
    total = 0.0
    per_type = {}
    for qtype, p in post.items():
        try:
            rep = pf.representation_for(qtype)
            acc_c = pf.rc_accuracy(qtype, rep, "cloud")
            acc_d = _device_accuracy(pf, qtype, cov["device_table"])
        except MissingEvidence:
            raise
        omega = pf.omega("RC" if req.task == "RC" else req.task)
        g = omega * (acc_c - acc_d) * mult
        per_type[qtype] = dict(p=p, acc_cloud=acc_c, acc_device=acc_d, rep=rep, ghat=g)
        total += p * g
    terms.update(per_type=per_type, omega=pf.omega("RC" if req.task == "RC" else req.task),
                 table="StudyPROF1-dev RC tables, DEV",
                 device_table=cov["device_table"])
    return dict(ghat=float(total), terms=terms, posterior=post, coverage=cov)


def choose_path(req: EscalationRequest, higher_value_in_flight: bool,
                history_bytes_threshold: int) -> Dict[str, Any]:
    """Addendum A2 as revised: COMPLETE by default, QUESTION-FIRST only as an exception.

    Both exception conditions must hold, and only an RC query can take the exception, because it
    is the only request whose payload can be large enough for the question to be worth separating
    from it."""
    if req.task != "RC":
        return dict(path=COMPLETE,
                    reason="not an RC query, so the question-first exception cannot apply")
    big = req.unsent_history_bytes > history_bytes_threshold
    if big and higher_value_in_flight:
        return dict(path=QUESTION_FIRST, unsent_history_bytes=req.unsent_history_bytes,
                    threshold=history_bytes_threshold,
                    reason="unsent history exceeds the threshold AND the uplink already carries "
                           "higher-value traffic")
    return dict(path=COMPLETE, unsent_history_bytes=req.unsent_history_bytes,
                threshold=history_bytes_threshold,
                reason=("unsent history is under the threshold" if not big else
                        "no higher-value traffic is in flight on this uplink"))


# ---------------------------------------------------------------- SH trigger families (A2)
class TriggerFamily:
    """Addendum A2 leaves the SH trigger family OPEN (Q11), to be decided from StudyCTRL1b. The
    three candidates are interchangeable objects with one method, so the measured winner is
    dropped in without touching the policy."""

    name = "abstract"

    def should_escalate(self, req: EscalationRequest, tables: GhatTables, **kw) -> Dict[str, Any]:
        raise NotImplementedError


@dataclass
class DeviceFilter(TriggerFamily):
    """The device computes Ghat locally and escalates when it clears a DEV-fitted threshold."""
    threshold: float = 0.0
    name: str = "device_filter"

    def should_escalate(self, req, tables, predicted_delay_s=None, flags=None, **kw):
        g = ghat(req, tables, predicted_delay_s=predicted_delay_s, flags=flags)
        return dict(escalate=bool(g["ghat"] > self.threshold), ghat=g["ghat"], basis=self.name,
                    terms=g["terms"])


@dataclass
class CloudTrickle(TriggerFamily):
    """The cloud samples every stream at a low background cadence and opens an episode on its own
    score. The device does not filter at all."""
    cadence_s: float = 4.0
    score_threshold: float = 0.0
    name: str = "cloud_trickle"

    def should_escalate(self, req, tables, cloud_score=None, **kw):
        if cloud_score is None:
            return dict(escalate=False, basis=self.name,
                        reason="no background sample has been read yet at this instant")
        return dict(escalate=bool(cloud_score > self.score_threshold), basis=self.name,
                    cloud_score=cloud_score, cadence_s=self.cadence_s)


@dataclass
class ContextModulatedTrickle(CloudTrickle):
    """Arm (e) of StudyCTRL1b: the background cadence halves while a cheap context signal is
    above its training-fold threshold."""
    context_threshold: float = 0.0
    name: str = "context_modulated_trickle"

    def cadence_for(self, context_value: Optional[float]) -> float:
        if context_value is None:
            return self.cadence_s
        return self.cadence_s / 2.0 if context_value > self.context_threshold else self.cadence_s

    def should_escalate(self, req, tables, cloud_score=None, context_value=None, **kw):
        out = CloudTrickle.should_escalate(self, req, tables, cloud_score=cloud_score)
        out.update(basis=self.name, effective_cadence_s=self.cadence_for(context_value),
                   context_value=context_value)
        return out


FAMILIES = {f.name: f for f in (DeviceFilter(), CloudTrickle(), ContextModulatedTrickle())}
