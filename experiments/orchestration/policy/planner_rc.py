#!/usr/bin/env python3
"""D125 v1.2: the RC JOB PLANNER, the planning half of the two-timescale design.

Why this exists (design note section 1). A recall answer arrives 1 to 5 s after the decision,
outside the 0.5 s dispatch horizon, so v1.0 and v1.1 could not value recall work: the continuation
value saturated, the deficit never saw an outcome inside H, and the schedule assumed an idle
engine. A multi-second job with a deadline is a PLANNING problem; a monitoring instant is a
DISPATCH problem. This module plans; `rollout.py` still dispatches on the 100 ms period.

WHAT IS NOT NEW HERE. The engine model, the KV and host bookkeeping, pi_0, the calendar and the
value terms are the committed ones. The only new pieces are the plan set, the long-window
evaluation, reserved units carrying their planned release time, and the re-plan hooks.

kappa IS 1.0 AND PROVISIONAL (report section V27.2). The note defines it as the q90 ratio of
measured to predicted job completion time on committed FIT/DEV data, and no such quantity exists
in committed form: `eng1_step_model.json` carries per-STEP residual bands, not
predicted-against-actual job completion pairs. No HOLDOUT was read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .engine import Request
from .state import Job, PendingItem

DECLINE = "DECLINE"
WARM = "WARM"
RELOAD = "RELOAD"
ONE_GO_NOW = "ONE-GO-NOW"
PIECES_NOW = "PIECES-NOW"
PIECES_LATEST = "PIECES-LATEST"
ABANDON = "ABANDON"

PLAN_KINDS = (DECLINE, WARM, RELOAD, ONE_GO_NOW, PIECES_NOW, PIECES_LATEST, ABANDON)


@dataclass
class Plan:
    """One candidate plan for one question. `units` carry their PLANNED release time in due_at."""
    kind: str
    piece_tokens: Optional[int] = None
    first_start_s: float = 0.0
    units: List[PendingItem] = field(default_factory=list)
    job: Optional[Job] = None
    predicted_completion_s: float = 0.0
    gpu_s: float = 0.0
    delta_j: Optional[float] = None
    note: str = ""

    def label(self) -> str:
        if self.piece_tokens:
            return "%s(%d)" % (self.kind, self.piece_tokens)
        return self.kind


def _service_s(engine, device: str, tokens: int, readiness: str, job_id: str,
               piece_index: int = 0) -> Tuple[float, float]:
    """(wall-clock service, gpu_s) for one unit, from the committed engine model."""
    pr = engine.predict(Request(kind="rc_piece", device=device, tokens=int(tokens),
                                readiness=readiness, job_id=job_id, piece_index=piece_index),
                        concurrent=0)
    return float(pr.service_s), float(pr.gpu_s)


def enumerate_plans(*, engine, device: str, qtype: str, rep: str, size_tokens: int,
                    readiness: str, deadline_abs: float, t: float,
                    piece_sizes: Sequence[int], allow_latest: bool, kappa: float,
                    built_tokens: int = 0) -> List[Plan]:
    """The candidate set of design note 2.2, limited to plans whose preconditions hold.

    Piece sizes are the measured D17 ones passed in; no new size is invented here.
    """
    out: List[Plan] = []
    jid = "%s:%s:%.3f" % (device, rep, t)

    def mk(kind: str, pieces: int, tok: int, ready: str, start: float,
           piece_tokens: Optional[int]) -> Plan:
        job = Job(job_id=jid, device=device, qtype=qtype, rep=rep, deadline=float(deadline_abs),
                  admitted_at=float(t), pieces_total=max(int(pieces), 1),
                  tokens_per_piece=int(tok))
        svc, gpu = _service_s(engine, device, tok, ready, jid)
        total = svc * max(int(pieces), 1)
        units = [PendingItem(item_id="%s:p%d" % (jid, i), kind="rc_piece", device=device,
                             due_at=float(start), deadline=float(deadline_abs),
                             tokens=int(tok), job_id=jid, readiness=ready,
                             meta=dict(planned_start=float(start), plan=kind))
                 for i in range(max(int(pieces), 1))]
        return Plan(kind=kind, piece_tokens=piece_tokens, first_start_s=float(start),
                    units=units, job=job,
                    predicted_completion_s=float(start) + total,
                    gpu_s=gpu * max(int(pieces), 1))

    unbuilt = max(int(size_tokens) - int(built_tokens), 0)
    r = str(readiness).upper()
    if r == "GPU-WARM":
        out.append(mk(WARM, 1, max(size_tokens, 1), "GPU-WARM", t, None))
    if r == "HOST-WARM":
        out.append(mk(RELOAD, 1, max(size_tokens, 1), "HOST-WARM", t, None))
    # A cold or partially built history can always be rebuilt, whole or in pieces.
    if r not in ("GPU-WARM",):
        out.append(mk(ONE_GO_NOW, 1, max(unbuilt, 1), "COLD", t, None))
        for b in piece_sizes:
            n = max(1, -(-max(unbuilt, 1) // int(b)))
            out.append(mk(PIECES_NOW, n, int(b), "COLD", t, int(b)))
            if allow_latest:
                svc, _g = _service_s(engine, device, int(b), "COLD", jid)
                work = svc * n * max(float(kappa), 1.0 if kappa <= 0 else float(kappa))
                t_ls = float(deadline_abs) - work
                if t_ls > t:
                    out.append(mk(PIECES_LATEST, n, int(b), "COLD", t_ls, int(b)))
    return out


def evaluate(rollout, fleet, plan: Plan, horizon_s: float) -> float:
    """Jhat(plan) over the long window, with the plan's units as reserved releases.

    A unit's planned time travels as its `due_at`, and the rollout already starts an item at
    `max(free_at, due_at)`, so "executed at its planned time, subject to the engine" needs no new
    mechanism. `rc_rows=True` routes the planner's own RC opportunity rows into the deficit term,
    which is required because F1 is off in v1.2 and its `_rc_opportunities` was the only route.
    """
    res = rollout.run(fleet, extra_pending=plan.units,
                      extra_jobs=({plan.job.job_id: plan.job} if plan.job is not None else None),
                      horizon_s=float(horizon_s), rc_rows=True)
    return float(res.total)


def choose(rollout, fleet, plans: Sequence[Plan], deadline_abs: float,
           decision_period_s: float = 0.1) -> Dict[str, Any]:
    """Design note 2.3: argmax DeltaJ against DECLINE, admit only if positive, ties by GPU cost.

    The window is `T_r = max(D_r, predicted completion) + one decision period`, taken over the
    whole candidate set so every plan is judged on the same window.
    """
    t0 = float(fleet.t)
    longest = max([float(deadline_abs)] + [p.predicted_completion_s for p in plans] + [t0])
    horizon_s = max(longest + float(decision_period_s) - t0, float(decision_period_s))
    reference = rollout.run(fleet, horizon_s=horizon_s, rc_rows=True)
    ref_total = float(reference.total)
    scored: List[Plan] = []
    for p in plans:
        p.delta_j = evaluate(rollout, fleet, p, horizon_s) - ref_total
        scored.append(p)
    feasible = [p for p in scored if p.delta_j is not None and p.delta_j > 0.0]
    best: Optional[Plan] = None
    if feasible:
        top = max(p.delta_j for p in feasible)
        # Ties keep the cheaper plan in GPU-seconds (design note 2.3).
        tied = [p for p in feasible if p.delta_j >= top - 1e-12]
        best = min(tied, key=lambda p: (p.gpu_s, p.label()))
    return dict(chosen=best, plans=scored, horizon_s=horizon_s, reference_total=ref_total,
                admitted=best is not None,
                note=("admitted %s at DeltaJ %.6f" % (best.label(), best.delta_j)
                      if best is not None else
                      "declined: no plan scored above zero over the long window"))


def replan_cause(*, job: Job, now: float, predicted_completion_s: float, kappa: float,
                 prefix_lost: bool, readiness_changed: bool) -> Optional[str]:
    """Design note 2.5's triggers, in its own order. None means no re-plan is due."""
    if predicted_completion_s * 1.0 + 0.0 > float(job.deadline) and kappa >= 0:
        slipped = float(predicted_completion_s) * max(float(kappa), 1.0) > float(job.deadline)
        if slipped:
            return "slipped: predicted completion with kappa exceeds the deadline"
    if prefix_lost:
        return "prefix loss found on verify-on-resume (D55)"
    if readiness_changed:
        return "the believed readiness tier changed"
    return None


def abandon_note(state_value_is_inert: bool) -> str:
    """ABANDON keeps the note's definition; its basis is PROVISIONAL pending the F2 ruling.

    Where the state value is inert, ABANDON reduces to declining the remainder, and this says so
    rather than letting it look valued.
    """
    if state_value_is_inert:
        return ("ABANDON reduces to DECLINING THE REMAINDER: its 'keep the state value of what is "
                "built' basis is inert because the terminal state value is zero whenever F2 is on "
                "(100 per cent of evaluations against 28.1 per cent with F2 off). PROVISIONAL "
                "pending the F2 ruling.")
    return ("ABANDON declines the remainder and keeps the state value of the built prefix "
            "(design note 2.5).")
