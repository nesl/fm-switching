"""Spec 5.4 and 7.3: job-level continuation value and feasibility, from a FEASIBLE CONTINUATION
SCHEDULE and never from tokens processed (D45).

The continuation schedule is pi_0's own plan beyond the horizon, at reduced resolution: the
remaining pieces of the job are placed in deadline order into the slots pi_0 would give them,
given the calendar and the expected arrival rate, and P(finish by the deadline) is read off that
placement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .completion_error import p_finish_by
from .engine import EngineModel, Request
from .state import Job

FEASIBLE = "FEASIBLE"
PRIORITY = "FEASIBLE_ONLY_WITH_PRIORITY"
INFEASIBLE = "INFEASIBLE"


@dataclass
class RemainingWork:
    """Addendum A6.1: E[w_r | defer for gap g] = w_left + P_loss(g) x [P_host x w_reload +
    (1 - P_host) x w_rebuild], in ENGINE SECONDS so it composes with the step model."""
    w_left_s: float
    p_loss: float
    p_host: float
    w_reload_s: float
    w_rebuild_s: float
    extra_s: float
    total_s: float
    beyond_horizon_unmeasured: bool = False
    basis: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


def restore_costs_s(prefix_tokens: int, pf) -> Tuple[float, float]:
    """w_reload and w_rebuild from the COMMITTED profiles (StudyRH5 host reload and cold
    re-prefill rates). A6.1 also names the M1 step model; M1 does not exist, so only the
    committed per-token rates are used and nothing is estimated."""
    if prefix_tokens <= 0:
        return 0.0, 0.0
    return (prefix_tokens * pf.seconds_per_token("reload", prefix_tokens),
            prefix_tokens * pf.seconds_per_token("rebuild", prefix_tokens))


def expected_remaining_work(job: Job, engine: EngineModel, pf, p_loss: float, p_host: float,
                            prefix_tokens: Optional[int] = None,
                            beyond_horizon_unmeasured: bool = False) -> RemainingWork:
    """A6.1, used by the continuation value (5.4), the feasibility class (7.3) and piece sizing
    (7.4), so all three price the same risk."""
    if not 0.0 <= p_loss <= 1.0:
        raise ValueError("P_loss must be a probability, got %r" % p_loss)
    if not 0.0 <= p_host <= 1.0:
        raise ValueError("P_host must be a probability, got %r" % p_host)
    w_left = 0.0
    for i in range(job.pieces_left()):
        pr = engine.predict(Request(kind="rc_piece", device=job.device,
                                    tokens=job.tokens_per_piece, job_id=job.job_id,
                                    piece_index=job.pieces_done + i), concurrent=0)
        w_left += pr.gpu_s
    built = (prefix_tokens if prefix_tokens is not None
             else job.pieces_done * job.tokens_per_piece)
    w_reload, w_rebuild = restore_costs_s(built, pf)
    extra = p_loss * (p_host * w_reload + (1.0 - p_host) * w_rebuild)
    return RemainingWork(
        w_left_s=w_left, p_loss=float(p_loss), p_host=float(p_host), w_reload_s=w_reload,
        w_rebuild_s=w_rebuild, extra_s=extra, total_s=w_left + extra,
        beyond_horizon_unmeasured=bool(beyond_horizon_unmeasured),
        basis="A6.1 with committed StudyRH5 reload and rebuild rates",
        detail=dict(built_prefix_tokens=built, pieces_left=job.pieces_left()))


@dataclass
class Schedule:
    finish_at: Optional[float]
    pieces_placed: int
    busy_s: float
    basis: str
    in_sample: bool
    # D122 v1.1 F4: the cursor after placing EVERY remaining piece, set whether or not the
    # placement met the deadline. `finish_at` keeps its meaning (None on overrun), so nothing
    # that reads it changes; this is the predicted completion the error model needs.
    finish_estimate: Optional[float] = None


def continuation_schedule(job: Job, t: float, engine: EngineModel, competing_s: float,
                          priority: bool, resolution_s: float = 0.25,
                          extra_work_s: float = 0.0,
                          full_estimate: bool = False) -> Schedule:
    """Place the job's remaining pieces into the time pi_0 leaves for them.

    `competing_s` is the engine-seconds of other work pi_0 would serve before this job's pieces
    (expected, from the calendar and the arrival rates). With priority, only work whose own loss
    exceeds the job's value stays ahead of it, which the caller expresses by passing a smaller
    `competing_s`.

    `extra_work_s` is addendum A6.1's expected restore work under deferral, charged BEFORE the
    remaining pieces because that is when a lost prefix must be rebuilt."""
    if competing_s < 0:
        raise ValueError("competing engine time cannot be negative")
    cursor = t + (0.0 if priority else competing_s) + max(extra_work_s, 0.0)
    overran_at = None
    placed = 0
    busy = 0.0
    in_sample = True
    for i in range(job.pieces_left()):
        req = Request(kind="rc_piece", device=job.device, tokens=job.tokens_per_piece,
                      job_id=job.job_id, piece_index=job.pieces_done + i)
        pr = engine.predict(req, concurrent=0)
        in_sample = in_sample and pr.in_sample
        cursor += max(pr.service_s, resolution_s)
        busy += pr.gpu_s
        placed += 1
        if cursor > job.deadline and overran_at is None:
            overran_at = placed
            if not full_estimate:
                return Schedule(finish_at=None, pieces_placed=placed, busy_s=busy,
                                basis="pi_0 placement overran the deadline",
                                in_sample=in_sample, finish_estimate=cursor)
    if overran_at is not None:
        # D122 v1.1 F4: with `full_estimate` the loop runs to the end so the predicted completion
        # is known even on an overrun. `finish_at` still reports None, so every existing reader
        # sees exactly what it saw before.
        return Schedule(finish_at=None, pieces_placed=overran_at, busy_s=busy,
                        basis="pi_0 placement overran the deadline", in_sample=in_sample,
                        finish_estimate=cursor)
    return Schedule(finish_at=cursor, pieces_placed=placed, busy_s=busy,
                    basis="pi_0 placement at %.2f s resolution" % resolution_s,
                    in_sample=in_sample, finish_estimate=cursor)


def p_finish(job: Job, t: float, engine: EngineModel, competing_s: float, priority: bool,
             resolution_s: float = 0.25, extra_work_s: float = 0.0,
             rel_sigma: Optional[float] = None) -> float:
    """Spec 5.4's Phat_r. The expected-value rollout gives a schedule, not a distribution, so the
    probability is the indicator of the schedule meeting the deadline, SOFTENED only by the
    device's reachability (spec 7.5). Sampled scenarios (flag off) would replace this with a
    frequency over draws; that is recorded as ambiguity A4."""
    if rel_sigma is None:
        s = continuation_schedule(job, t, engine, competing_s, priority, resolution_s,
                                  extra_work_s)
        return 1.0 if s.finish_at is not None else 0.0
    # D122 v1.1 F4 (spec Phat): the indicator becomes P(predicted finish <= D_r) under the cost
    # model's MEASURED completion-time error. `full_estimate` makes the predicted completion
    # available even when the placement overran, which the indicator path never needed.
    s = continuation_schedule(job, t, engine, competing_s, priority, resolution_s, extra_work_s,
                              full_estimate=True)
    est = s.finish_estimate
    if est is None:
        return 1.0 if s.finish_at is not None else 0.0
    return p_finish_by(float(job.deadline) - float(t), max(float(est) - float(t), 0.0),
                       float(rel_sigma))


def classify(job: Job, t: float, engine: EngineModel, competing_s: float, threshold: float,
             competing_s_with_priority: float = 0.0, resolution_s: float = 0.25,
             extra_work_s: float = 0.0, rel_sigma: Optional[float] = None) -> str:
    """A6.1: the feasibility class uses the EXPECTED remaining work, so a job whose prefix is at
    risk can be infeasible at a deadline it would have met if the prefix were safe."""
    base = p_finish(job, t, engine, competing_s, False, resolution_s, extra_work_s, rel_sigma)
    if base >= threshold:
        return FEASIBLE
    prio = p_finish(job, t, engine, competing_s_with_priority, True, resolution_s, extra_work_s,
                    rel_sigma)
    return PRIORITY if prio >= threshold else INFEASIBLE


def continuation_value(job: Job, t: float, engine: EngineModel, competing_s: float,
                       priority: bool, omega_rc: float, acc_cloud: float, acc_device: float,
                       z: float, d_p_success: float = 0.0,
                       p_reachable: float = 1.0, resolution_s: float = 0.25,
                       extra_work_s: float = 0.0,
                       rel_sigma: Optional[float] = None) -> float:
    """Spec 5.4. Zero for an answered job and for an infeasible one; the state value of a
    partially rebuilt history is NOT counted here (spec 5.3 values each item exactly once)."""
    if job.answered or job.pieces_left() == 0:
        return 0.0
    p = (p_finish(job, t, engine, competing_s, priority, resolution_s, extra_work_s, rel_sigma)
         * float(p_reachable))
    return omega_rc * (acc_cloud - acc_device) * p + z * d_p_success


def bounded_waiting_breach(job: Job, t: float, engine: EngineModel, competing_s: float,
                           threshold: float, interval_s: float,
                           resolution_s: float = 0.25) -> bool:
    """Spec 7.3: a job that is feasible with priority NOW but would be infeasible within the next
    scheduling interval is promoted to the priority class."""
    now = classify(job, t, engine, competing_s, threshold, 0.0, resolution_s)
    if now == INFEASIBLE:
        return False
    later = classify(job, t + interval_s, engine, competing_s, threshold, 0.0, resolution_s)
    return bool(later == INFEASIBLE and now != INFEASIBLE)
