#!/usr/bin/env python3
"""THE OBJECTIVE the v5 counterfactual maximises, with per-device deficit weighting and harm to
other devices (D151 (4), D149 (1), D152 (1) as amended by D155 (3)). CPU only.

    V = sum over devices i of  w_i * E[correct answers delivered BY THE DEADLINE]  minus harm

and for one robot question with a cloud option `o`:

    V_i(o)      = w_i * [ P(o on time) * acc(o)  +  (1 - P(o on time)) * P(dev on time) * acc(dev) ]
    V_i(DEVICE) = w_i * P(dev on time) * acc(dev)
    harm        = sum over other devices j of  w_j * ( V_j(before this option) - V_j(after) )
    objective   = V_i(o) - harm

THREE THINGS IN THAT FORMULA ARE RULINGS AND NOT ARITHMETIC, so they are named here.

1. D155 (3) AMENDS THE HEADLINE TO "BY THE DEADLINE FROM EITHER SOURCE". A device answer counts
   only if it arrives within the deadline, so the device is no longer a free incumbent worth
   `1.0 * acc(dev)`: it carries its own delivery probability. `v5/value_readers.py`'s grid still
   prices the device at `p_on_time = 1.0`, which was right under D152 (1) and is not right under
   D155 (3). That module is not this session's and the difference is reported, not edited.

   MEASURED CONSEQUENCE IN THIS BUILD, and it is a CONSTANT, which CLAUDE.md Step 2 treats as a
   stopping condition for the link it implements: the only committed device-answer latency is
   `fleet/data_sources.py::DEVICE_WAIT_RULE_S = 0.567`, labelled `proxy-0.567` by D154 (5), and
   D155 (1) rules the StudyORIN-REC part 1 latencies (TTFT 3.3 s, e2e 6.65 s) an API artifact of
   the cold re-send path that must NOT be wired. 0.567 s is inside every robot deadline under
   test (2.5 to 5 s), so `P(device on time) = 1.0` for every robot question and D155 (3)'s
   restriction on the DEVICE side cannot change any decision in this build. It is implemented, it
   is read, and it is CONSTANT. The remedy is the measured warm-path per-question latencies
   D155 (1) says are being produced; until they land, every report must say that the "by the
   deadline" amendment is live on the cloud side and inert on the device side.

2. THE DEFICIT WEIGHT STEERS ON ON-TIME WHILE THE OBJECTIVE SCORES CORRECTNESS (spec v5 section
   7.7, gap G14). D152 (1) keeps the counters on observable on-time because correctness is not
   observable at run time. This module resolves the mismatch by LOCATING it rather than smoothing
   it: `w_i` is computed from observed on-time outcomes ONLY, and the quantity it multiplies is
   expected CORRECTNESS. So the weight says WHOSE answers matter more and the accuracy table says
   WHICH ANSWER is worth more, and neither is asked to do the other's job.

   The geometry that follows matters more than the statement, and it is proved in
   `weight_is_within_device_invariant`: `w_i` is a per-device scalar, so inside ONE device's
   candidate set it multiplies every candidate equally and CANNOT change which representation is
   chosen. If a report claimed the deficit weighting changes representation decisions, it would
   be claiming something this algebra forbids: that is CLAUDE.md Rule 2's `cancelled by geometry`
   and it is why the characteristic decision of the weighting is a CROSS-DEVICE one. The
   weighting acts, and acts only, where devices compete: the harm term of a request decision,
   warm and keep selection, shedding, and backlog order.

3. "HARM TO OTHERS" IS A DIFFERENCE OF TWO SIMULATED QUEUES, not a penalty term. It is
   `cf_cost.plan_queue` run without the option and again with it, with every other device's
   delivery probability re-predicted, so displacement is counted in the same units as the gain
   and no coefficient trades them off.

WHAT THE COUNTERS ARE NOT. They are not `arms_policy.Params.deficit_update` (the v1 artefact at
`arms_policy.py:276`, DEFAULT OFF, whose `w = 1` for every task and whose scaling B2 is
pre-registered and unimplemented). That one lives in the frozen policy library, is off in every
committed cell, and steers a different objective. This is a fresh implementation for v5 and it
does not import it.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(REPO / "experiments/orchestration/live2"),
           str(REPO / "experiments/orchestration/live2/fleet")):
    if _p not in sys.path:
        sys.path.append(_p)

import cf_cost as CC                                                           # noqa: E402

# ---------------------------------------------------------------------------
# THE MEASURED DEVICE-ANSWER LATENCY (D171 (3)). The 0.567 s proxy is GONE from the decision
# path: this reads the same three measured Orin tables the coordinator's live device wait reads
# (`coordinator.py::_device_wait_s`, :764 dashcam, :780 robot, :785 single-shot), through the same
# `fleet/data_sources.py` accessors, so the counterfactual's device model and the live wait cannot
# drift apart. Per TYPE and, for dashcam, per EPISODE POSITION, because the three tables are three
# different measurements and none of them covers another's ids.
#
# WHAT THE MEASURED TABLES DO AND DO NOT MAKE VARY, which a report must not get wrong:
#   robot       0.2503 to 0.3108 s over 97 LH-REQ questions (StudyORIN-REC WARM, completion).
#               Every value is inside every robot deadline under test (2.5 to 5 s), so
#               `p_device_on_time` is still 1.0 on EVERY robot decision. It is now CONSTANT
#               BECAUSE THE DEVICE IS FAST, which is a measured fact, and no longer constant
#               because the input was a flat proxy, which was an artefact. The two look the same
#               in the output and are not the same claim.
#   single_shot 1,042 questions (StudySS2, completion, D146 (1)): realworldqa p50 0.9592 s,
#               refspatial p50 1.9947 s and max 3.4093 s against a 2.0 s deadline. HERE the term
#               varies, and 45.5 percent of refspatial questions give p_device_on_time = 0.
#   dashcam     EP-G warm APPEND first token by episode frame position, 0.2349 to 0.3169 s over
#               positions 1 to 21 (StudySH-EP, D146 (1) allows first token for a Yes/No alert).
#               Inside a 1 s dashcam deadline at every position; the EPISODE START curve is the
#               one that reaches 1.88 s.
# So the mechanism is LIVE and it is UNEXERCISED on the robot decisions the counterfactual makes
# in today's cells (CLAUDE.md Rule 2), which is a different sentence from "constant" and is the
# one that is true.
DEVICE_WAIT_FALLBACK_S = 0.567
DEVICE_WAIT_FALLBACK_NOTE = (
    "the superseded proxy-0.567 literal (D154 (5)), kept ONLY as the value counted when a lookup "
    "finds no measured entry. D171 (3) requires that counter to be 0: a non-zero fallback means "
    "the counterfactual priced a device answer on a number no one measured")


class DeviceLatency:
    """The measured per-type device-answer latency, with a fallback COUNTER rather than a silence.

    Mirrors `coordinator.py::_device_wait_s` lookup for lookup. Counts by type, and counts the
    fallback by WHY it was reached, because a missing dashcam table and a question id absent from
    the single-shot table need different remedies and only one of them is a missing measurement.
    """

    def __init__(self) -> None:
        self._robot: Optional[Dict[str, float]] = None
        self._ss: Optional[Dict[str, float]] = None
        self._dash: Optional[Dict[int, float]] = None
        self.counts: Dict[str, int] = {}

    def _bump(self, k: str) -> None:
        self.counts[k] = self.counts.get(k, 0) + 1

    def _tables(self) -> None:
        if self._robot is not None:
            return
        try:
            import data_sources as _DS                                         # noqa: PLC0415
            self._robot = {str(k): float(v) for k, v in _DS.device_recall_warm_latency_s().items()}
            self._ss = {str(k): float(v) for k, v in _DS.single_shot_total_s().items()}
            self._dash = {int(k): float(v) for k, v in _DS.dashcam_append_ttft_s().items()}
        except Exception:                                                      # noqa: BLE001
            self._robot, self._ss, self._dash = {}, {}, {}

    def wait_s(self, *, kind: str = "robot", question_id: Optional[str] = None,
               episode_frames: Optional[int] = None) -> float:
        self._tables()
        if kind in ("dashcam", "monitor"):
            tab = self._dash or {}
            if tab:
                n = int(episode_frames or 1)
                n = min(max(n, min(tab)), max(tab))
                self._bump("measured_dashcam")
                return float(tab[n])
            self._bump("fallback_no_dashcam_table")
            return DEVICE_WAIT_FALLBACK_S
        if question_id is not None:
            qid = str(question_id)
            v = (self._robot or {}).get(qid)
            if v is not None:
                self._bump("measured_robot")
                return float(v)
            v = (self._ss or {}).get(qid)
            if v is not None:
                self._bump("measured_single_shot")
                return float(v)
            self._bump("fallback_question_id_not_in_any_table")
            return DEVICE_WAIT_FALLBACK_S
        self._bump("fallback_no_question_id")
        return DEVICE_WAIT_FALLBACK_S

    def as_dict(self) -> Dict[str, Any]:
        self._tables()
        n_fb = sum(v for k, v in self.counts.items() if k.startswith("fallback"))
        return {"source": DEVICE_LATENCY_SOURCE,
                "n_robot": len(self._robot or {}), "n_single_shot": len(self._ss or {}),
                "n_dashcam_positions": len(self._dash or {}),
                "counts": dict(sorted(self.counts.items())),
                "n_fallback": n_fb, "fallback_is_zero": n_fb == 0,
                "fallback_s": DEVICE_WAIT_FALLBACK_S,
                "fallback_note": DEVICE_WAIT_FALLBACK_NOTE}


DEVICE_LATENCY_SOURCE = (
    "results/device/study_devlat/orin_device_latency_tables.json via fleet/data_sources.py "
    "(device_recall_warm_latency_s, single_shot_total_s, dashcam_append_ttft_s) - the SAME "
    "accessors coordinator.py::_device_wait_s reads")
DEVICE_ANSWER_LABEL = "measured-orin (D171 (3)); the proxy-0.567 literal is no longer on this path"

DEVLAT = DeviceLatency()

# The on-time target the deficit counters measure a shortfall against. It is the committed robot
# SLO (D133: p 0.90 within the deadline), per type, and it is DECLARED, not fitted.
ON_TIME_TARGET: Dict[str, float] = {"robot": 0.90, "dashcam": 0.90, "single_shot": 0.90}
ON_TIME_TARGET_SOURCE = "D133 robot headline: p 0.90 within the deadline, applied per type"

# The gain that turns a shortfall into a weight. DECLARED, never swept: a swept gain would be a
# tuned objective, which is the thing D151 (1)'s margin exists to prevent.
DEFICIT_GAIN = 1.0

OBJECTIVE_STATEMENT = (
    "deficit-weighted expected CORRECT answers delivered BY THE DEADLINE from either source, "
    "minus harm to other devices (D151 (4), D152 (1) as amended by D155 (3)); the same objective "
    "every reader in spec v5 section 7 maximises")


# ---------------------------------------------------------------------------
# Deficit counters: observable on-time only


@dataclass
class DeviceDeficit:
    device_id: str
    kind: str = "robot"
    served: int = 0
    on_time: int = 0

    @property
    def rate(self) -> float:
        return (self.on_time / self.served) if self.served else 1.0

    def shortfall(self, target: Optional[float] = None) -> float:
        t = ON_TIME_TARGET.get(self.kind, 0.90) if target is None else float(target)
        if not self.served:
            return 0.0
        return max(t - self.rate, 0.0)


class DeficitCounters:
    """Per-device deficit counters, updated from the REALISED on-time outcome of each opportunity.

    On-time is the only thing observable online without ground truth (`arms_policy.py:276` says
    the same of the v1 counters, and it is the one thing about them v5 keeps). Correctness is not
    observable at run time, so it never enters an update here; it enters the objective through the
    committed accuracy table instead. That split is gap G14, kept deliberately and recorded.
    """

    def __init__(self, gain: float = DEFICIT_GAIN) -> None:
        self.gain = float(gain)
        self.devices: Dict[str, DeviceDeficit] = {}
        self.n_updates = 0

    def observe(self, device_id: str, on_time: bool, kind: str = "robot") -> None:
        d = self.devices.setdefault(device_id, DeviceDeficit(device_id, kind))
        d.served += 1
        d.on_time += 1 if on_time else 0
        self.n_updates += 1

    def shortfall(self, device_id: str) -> float:
        d = self.devices.get(device_id)
        return d.shortfall() if d else 0.0

    def weight(self, device_id: str) -> float:
        """`w_i = 1 + gain * shortfall_i`, so a device meeting its target weighs exactly 1.

        The floor at 1 is deliberate: a device AHEAD of its target is not worth LESS than a
        correct answer is worth, it is simply not worth more. Letting w fall below 1 would make
        the objective trade a correct answer for a fairness statistic, which D149 (1) forbids.
        """
        return 1.0 + self.gain * self.shortfall(device_id)

    def starving(self, device_id: str, threshold: float = 0.10) -> bool:
        """Reader 5's `starving` flag (D149 (3)): a shortfall past a declared threshold."""
        return self.shortfall(device_id) >= float(threshold)

    def as_dict(self) -> Dict[str, Any]:
        return {"gain": self.gain, "n_updates": self.n_updates,
                "target": ON_TIME_TARGET, "target_source": ON_TIME_TARGET_SOURCE,
                "steers_on": "observable on-time (D152 (1))",
                "objective_scores": "correct answers delivered by the deadline (D155 (3))",
                "mismatch": "gap G14, located rather than smoothed; see module docstring",
                "devices": {k: {"served": v.served, "on_time": v.on_time,
                                "rate": round(v.rate, 6),
                                "shortfall": round(v.shortfall(), 6),
                                "weight": round(self.weight(k), 6)}
                            for k, v in sorted(self.devices.items())}}


# ---------------------------------------------------------------------------
# The device side of the objective (D155 (3))


def device_wait_s(*, kind: str = "robot", question_id: Optional[str] = None,
                  episode_frames: Optional[int] = None) -> float:
    """The MEASURED wait for this question's own device answer (D171 (3))."""
    return DEVLAT.wait_s(kind=kind, question_id=question_id, episode_frames=episode_frames)


def p_device_on_time(deadline_s: float, wait_s: Optional[float] = None, *,
                     kind: str = "robot", question_id: Optional[str] = None,
                     episode_frames: Optional[int] = None) -> float:
    """P(the DEVICE's own answer arrives within this question's deadline), D155 (3) on D171 (3).

    `wait_s` is the measured latency for THIS question unless a caller supplies one explicitly
    (the negative control does, and only the negative control should).
    """
    w = (device_wait_s(kind=kind, question_id=question_id, episode_frames=episode_frames)
         if wait_s is None else float(wait_s))
    return 1.0 if float(w) <= float(deadline_s) else 0.0


# ---------------------------------------------------------------------------
# Option values


def option_value(weight: float, p_cloud_on_time: float, acc_cloud: float,
                 p_dev_on_time: float, acc_dev: float) -> float:
    """Expected correct answers delivered by the deadline from EITHER source, weighted.

    The second term is the whole of D155 (3)'s amendment: when the cloud's answer does not arrive,
    the device's does, and it counts if and only if it is inside the deadline.
    """
    p = max(min(float(p_cloud_on_time), 1.0), 0.0)
    return float(weight) * (p * float(acc_cloud)
                            + (1.0 - p) * float(p_dev_on_time) * float(acc_dev))


def device_only_value(weight: float, p_dev_on_time: float, acc_dev: float) -> float:
    return float(weight) * float(p_dev_on_time) * float(acc_dev)


# ---------------------------------------------------------------------------
# Harm to others: a difference of two simulated queues


@dataclass(frozen=True)
class Harm:
    total: float
    rows: Tuple[Dict[str, Any], ...]
    n_affected: int

    def as_dict(self) -> Dict[str, Any]:
        return {"total": round(self.total, 9), "n_affected": self.n_affected,
                "rows": [dict(r) for r in self.rows]}


def harm_to_others(before: "CC.QueuePlan", after: "CC.QueuePlan", *, candidate_req_id: str,
                   counters: Optional[DeficitCounters] = None,
                   acc_by_req: Optional[Dict[str, float]] = None,
                   deadline_by_req: Optional[Dict[str, float]] = None,
                   acc_device: float = 0.0,
                   acc_device_by_req: Optional[Dict[str, float]] = None) -> Harm:
    """The expected correct on-time answers OTHER devices lose because this option was taken.

    Positive numbers are losses. Every row is one other request whose predicted delivery
    probability moved, with its own device's weight and its own accuracy, so the harm is in the
    same units as the gain and is never a tuned penalty.

    D171 (2), REPLACEMENT SEMANTICS ON BOTH SIDES OF THE SUBTRACTION. A displaced request does not
    lose its whole cloud answer: its own DEVICE answers instead, exactly as D165 (B) prices the
    gain side. Each row is therefore

        w_o * (p_before - p_after) * (acc_cloud_o - acc_dev_o * p_dev_on_time_o)

    which is what `option_value` returns when it is given the real `acc_dev` instead of 0.0, and
    `acc_dev = 0.0` is what it was given before. The old term valued a displaced request at its
    FULL cloud accuracy, so it OVERSTATED harm wherever the other device could have answered: the
    counterfactual was more conservative than the objective says it should be. The device's own
    delivery probability is the measured one (D171 (3)), keyed on that request's own question.
    """
    b = before.by_id()
    a = after.by_id()
    rows: List[Dict[str, Any]] = []
    total = 0.0
    for rid, rb in b.items():
        if rid == candidate_req_id:
            continue
        ra = a.get(rid)
        if ra is None:
            continue
        w = (counters.weight(rb.device_id) if counters else rb.weight)
        acc = (acc_by_req or {}).get(rid, rb.accuracy)
        dl = (deadline_by_req or {}).get(rid, rb.deadline_abs_s)
        a_dev = (acc_device_by_req or {}).get(rid, float(acc_device))
        p_dev = (p_device_on_time(max(dl - rb.start_s, 0.0), kind=rb.kind,
                                  question_id=rb.question_id,
                                  episode_frames=rb.episode_frames)
                 if dl != math.inf else 1.0)
        vb = option_value(w, rb.p_on_time, acc, p_dev, a_dev)
        va = option_value(w, ra.p_on_time, acc, p_dev, a_dev)
        if abs(vb - va) > 0.0:
            rows.append({"req_id": rid, "device_id": rb.device_id, "weight": round(w, 6),
                         "p_on_time_before": round(rb.p_on_time, 6),
                         "p_on_time_after": round(ra.p_on_time, 6),
                         "accuracy": acc, "accuracy_device": a_dev,
                         "p_device_on_time": p_dev,
                         "value_lost": round(vb - va, 9)})
            total += vb - va
    return Harm(total, tuple(rows), len(rows))


# ---------------------------------------------------------------------------
# The two properties of the weighting that a report must not get wrong


def weight_is_within_device_invariant(p_values: Sequence[float], accs: Sequence[float],
                                      weights: Sequence[float]) -> Dict[str, Any]:
    """PROOF that `w_i` cannot change which option ONE device's question takes.

    `w_i` multiplies every candidate of device i identically, so the argmax over that device's own
    candidate set is independent of `w_i`. Reported because the opposite claim is the natural
    mistake: "the objective is deficit weighted" reads as if the weighting affects every decision,
    and inside one request's candidate set it provably affects none. CLAUDE.md Rule 2 calls this
    shape `cancelled by geometry`, and a mechanism that cancels must be claimed where it does not.
    """
    rows = []
    for w in weights:
        vals = [option_value(w, p, a, 1.0, 0.0) for p, a in zip(p_values, accs)]
        rows.append({"weight": w, "argmax_index": max(range(len(vals)), key=lambda i: vals[i]),
                     "values": [round(v, 9) for v in vals]})
    argmaxes = {r["argmax_index"] for r in rows}
    return {"claim": "w_i cannot change the argmax within one device's candidate set",
            "weights_tried": list(weights), "rows": rows,
            "argmax_constant_across_weights": len(argmaxes) == 1,
            "verdict": ("CONFIRMED: cancelled by geometry within a device; the weighting's "
                        "characteristic decision is CROSS-DEVICE"
                        if len(argmaxes) == 1 else
                        "UNEXPECTED: the weight moved a within-device argmax, which the algebra "
                        "forbids; the implementation has a bug")}


def main() -> int:
    c = DeficitCounters()
    for i in range(10):
        c.observe("robo000", on_time=True)
    for i in range(10):
        c.observe("robo001", on_time=(i < 5))
    print(json.dumps({"objective": OBJECTIVE_STATEMENT,
                      "device_answer_wait_s": DEVICE_ANSWER_WAIT_S,
                      "device_answer_label": DEVICE_ANSWER_LABEL,
                      "counters": c.as_dict()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
