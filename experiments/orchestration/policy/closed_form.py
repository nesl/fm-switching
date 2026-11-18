#!/usr/bin/env python3
"""Spec v4 section 6.5: the closed-form channel approximation, for SH admission ONLY.

StudyLIVE2-perf Option B, built as schedule insurance on the user's decision of 2026-11-18 and
**OFF BY DEFAULT**. It is enabled nowhere: `Coordinator.sh_cost` defaults to "rollout", which
takes exactly the path this file did not exist for. Acceptance is the user's call after the H100
pilot. The pre-registration, written and committed before this file, is
`reports/study_live2_perf.md` section "Option B" (B.1 to B.6), and it is the authority on every
term here.

WHY A CLOSED FORM IS POSSIBLE. The frozen engine model in the rollout is a SINGLE SERIAL SERVER
in EDF order (`rollout.py` 203-219: `start = max(free_at, due_at)`, `finish = start + service_s`,
`free_at = finish`). Inserting one request therefore shifts every later request in the queue by
exactly its service time. That is arithmetic, not simulation, which is what makes this an
approximation of the ROLLOUT rather than a second model of the engine.

WHAT IS APPROXIMATED AND WHAT IS NOT. Every TIMING comes from the frozen
`Eng1Engine.predict().service_s` / `.gpu_s`; every VALUE comes from the committed utility
functions, called exactly as the rollout calls them. What is dropped is listed in B.4 and
repeated at `_NOT_PRICED` below, and all of it is omitted COST, which is the mechanism behind the
pre-registered over-admission prediction.

NOTHING HERE IS A MEASUREMENT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .continuation import continuation_value
from .state import Fleet, PendingItem
from .utility import u_sh_cloud, u_sh_device

SH_COST_MODES = ("rollout", "closed_form", "shadow")

_NOT_PRICED = (
    "cascade effects beyond the first-order shift (work pushed out of the horizon, and the "
    "change in `busy` that follows)",
    "the KV pool and the A6.2 prefix-risk term",
    "cadence-calendar instants not served by a queued or in-flight call",
    "the terminal state-value sum, whose omission is EXACT rather than an approximation: an "
    "episode call builds no history, so no device belief changes and the term cancels "
    "identically in a.total - b.total",
)


class ClosedFormNotApplicable(ValueError):
    """Raised rather than guessing when the candidate is not a lone SH call.

    Piece release and recall jobs keep the full rollout (the user's scope for Option B), so a
    caller that reaches this has mis-routed and must not silently get an approximation.
    """


@dataclass
class _Served:
    """One queued request, with the delivery the serial server gives it."""
    item: PendingItem
    start: float
    finish: float
    delivered: float
    starts_in_horizon: bool
    gpu_s: float = 0.0


def load_factor(ro, fleet: Fleet, cand: PendingItem) -> Dict[str, Any]:
    """B.3: the frozen step model at the current occupancy over itself at zero occupancy.

    ONE definition, NO fitted parameter, so no HOLDOUT is touched and no cross-fitting is
    needed. No term is dropped and no clamp is applied: the frozen model's fitted
    `per_decode_req_ms` is negative, so this can come out BELOW 1 on a decode-heavy engine, and
    choosing otherwise would substitute our judgement for the frozen model's. An LF below 1
    deflates the imposed delay, which ADDS to the predicted over-admission.
    """
    step = ro.engine.step
    tok = max(int(cand.tokens), 0)
    img = max(int(getattr(cand, "frames", 0) or 0), 0)
    r_d = len(fleet.in_flight)
    r_p = sum(1 for p in fleet.pending if p.item_id != cand.item_id)
    ctx = sum(max(int(p.tokens), 0) for p in fleet.in_flight)
    loaded = float(step.step_ms(tok, img, r_d, r_p, ctx))
    solo = float(step.step_ms(tok, img, 0, 0, 0))
    lf = (loaded / solo) if solo > 0 else 1.0
    return dict(lf=float(lf), loaded_ms=loaded, solo_ms=solo, decode_reqs=r_d,
                prefill_reqs=r_p, cached_ctx_tokens=ctx,
                note="frozen StepModel.step_ms ratio; no fitted parameter, no clamp")


def _serial(ro, fleet: Fleet, queue: Sequence[PendingItem], free0: float,
            t0: float, end: float, concurrent: int) -> List[_Served]:
    """The rollout's own serial-EDF arithmetic, as `run` performs it."""
    out: List[_Served] = []
    free = free0
    for p in queue:
        start = max(free, p.due_at)
        if start > end:
            out.append(_Served(p, start, start, start, False))
            continue
        pr = ro.engine.predict(ro._request(p), concurrent=concurrent, load_pct=ro.load_pct)
        finish = start + pr.service_s
        free = finish
        dev = fleet.devices.get(p.device)
        down = dev.link.down_s() if dev else 0.0
        out.append(_Served(p, start, finish, finish + down, True, float(pr.gpu_s)))
    return out


def _free_after_in_flight(ro, fleet: Fleet, t0: float) -> Tuple[float, float]:
    """`(free_at, busy)` from the in-flight set, exactly as `run` accumulates them."""
    free, busy = t0, 0.0
    for p in fleet.in_flight:
        pr = ro.engine.predict(ro._request(p),
                               concurrent=max(len(fleet.in_flight) - 1, 0),
                               load_pct=ro.load_pct)
        free = max(free, t0 + pr.service_s)
        busy += float(pr.gpu_s)
    return free, busy


def _sh_credit(ro, capture: float, delivered: Optional[float], l_sh: float,
               cad: float, u_dev: float, w: float) -> float:
    """The committed per-instant D98 credit: `w * (u_cloud - u_device)`, or 0 if it is late."""
    if delivered is None or delivered > capture + l_sh + 1e-12:
        return 0.0
    u, _inrange = u_sh_cloud(ro.pf, max(float(delivered) - float(capture), 0.0), 1, cad,
                             allow_m_gt_1=ro.flags.merging)
    return float(w) * (float(u) - float(u_dev))


def sh_admit_delta_j(ro, fleet: Fleet, items: Sequence[PendingItem],
                     jobs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """`DeltaJ_cf = G - L + DeltaCV - mu*B + DeltaZ` for admitting ONE SH call (B.2)."""
    cands = [p for p in items if p.kind == "episode_call"]
    if len(cands) != 1 or len(items) != 1:
        raise ClosedFormNotApplicable(
            "the closed form prices exactly one SH (episode_call) candidate; got %r. Piece "
            "release and recall jobs keep the full rollout."
            % ([p.kind for p in items],))
    cand = cands[0]
    params, pf = ro.params, ro.pf
    t0 = float(fleet.t)
    end = t0 + float(params.H)
    cad = float(params.T_k["SH"])
    l_sh = float(params.L_k["SH"])
    w = float(params.omega["SH"])
    u_dev = u_sh_device(pf)
    mu = float(params.mu)

    free0, busy_in_flight = _free_after_in_flight(ro, fleet, t0)
    concurrent = len(fleet.in_flight)
    before = _serial(ro, fleet, ro._edf(list(fleet.pending)), free0, t0, end, concurrent)
    after_q = ro._edf(list(fleet.pending) + [cand])
    k = next(i for i, p in enumerate(after_q) if p.item_id == cand.item_id)

    pr_c = ro.engine.predict(ro._request(cand), concurrent=concurrent, load_pct=ro.load_pct)
    lf = load_factor(ro, fleet, cand)
    shift = float(lf["lf"]) * float(pr_c.service_s)

    # the candidate's own delivery: the serial server at its EDF position
    free_at_k = free0 if k == 0 else before[k - 1].finish
    start_c = max(free_at_k, float(cand.due_at))
    dev_c = fleet.devices.get(cand.device)
    down_c = dev_c.link.down_s() if dev_c else 0.0
    delivered_c = start_c + float(pr_c.service_s) + down_c
    in_horizon_c = start_c <= end

    # G: the candidate's own instant. D98 credits an instant at ITS OWN deadline even when that
    # lies past t0 + H, and the rollout's tail pass simulates a call that cannot start inside
    # the horizon for exactly that reason, so the delivery is used whether or not it starts in H.
    g = _sh_credit(ro, float(cand.due_at), delivered_c, l_sh, cad, u_dev, w)

    # L: the first-order loss to every queued SH call at or after position k
    shifted: List[Tuple[_Served, float]] = []
    loss = 0.0
    for idx, s in enumerate(before):
        if idx < k or not s.starts_in_horizon:
            continue
        shifted.append((s, s.delivered + shift))
        if s.item.kind != "episode_call":
            continue
        c_j = float(s.item.due_at)
        loss += (_sh_credit(ro, c_j, s.delivered, l_sh, cad, u_dev, w)
                 - _sh_credit(ro, c_j, s.delivered + shift, l_sh, cad, u_dev, w))

    # DeltaCV: the continuation value, RETAINED, for every job whose pieces are delayed
    d_cv = 0.0
    cv_rows: List[Dict[str, Any]] = []
    delayed_jobs = sorted({s.item.job_id for s, _ in shifted if s.item.job_id})
    all_jobs = dict(fleet.jobs)
    if jobs:
        all_jobs.update(jobs)
    for jid in delayed_jobs:
        job = all_jobs.get(jid)
        if job is None:
            continue
        dev = fleet.devices.get(job.device)
        if dev is None:
            continue
        kw = dict(omega_rc=pf.omega("RC"),
                  acc_cloud=pf.rc_accuracy(job.qtype, job.rep, "cloud"),
                  acc_device=pf.rc_accuracy(job.qtype, "D2", "device"),
                  z=dev.z_of("RC"), p_reachable=dev.link.p_reachable_within_hs,
                  resolution_s=params.continuation_resolution_s)
        safe = continuation_value(job, t0, ro.engine, 0.0, False, extra_work_s=0.0, **kw)
        late = continuation_value(job, t0, ro.engine, 0.0, False, extra_work_s=shift, **kw)
        d_cv += float(late - safe)
        cv_rows.append(dict(job_id=jid, safe=float(safe), delayed=float(late),
                            delta=float(late - safe)))

    # B: the backlog term, charged only OUTSIDE CHANNEL 1, with the ROLLOUT'S OWN STRUCTURE.
    #
    # SECOND ERRATUM TO THE PRE-REGISTRATION (B.2), found by shadow mode and recorded rather
    # than quietly changed. B.2 wrote the term as `-mu * gpu_c` whenever the candidate had to
    # queue. That is not the rollout's backlog term and it is not the spec's: the rollout charges
    # `-mu * max(busy - H, 0)` (`rollout.py::_terminal`), leftover work AT THE HORIZON, so an
    # admit whose work still fits inside H costs nothing in backlog. Charging the candidate's
    # whole GPU time instead put a spurious `-mu * gpu_c` on EVERY queued candidate: on an
    # 8 + 8 60 s fixture with mu estimated it was a near-constant -0.055 on 949 of 952
    # candidates, which alone accounted for the entire difference from the rollout (the
    # rollout's own `d_terminal` was 0 and its `d_u_hat` matched this file's `own_gain` exactly).
    # "Applied only outside channel 1" restricts WHICH work counts toward the backlog, it does
    # not replace the `max(busy - H, 0)` structure. So:
    #
    #     B = max(busy_before + gpu_outside_channel_1 - H, 0) - max(busy_before - H, 0)
    #
    # ERRATUM TO THE PRE-REGISTRATION (B.2), recorded rather than quietly changed. B.2 wrote the
    # condition as `start_c > due_at_c`. That is wrong, and the first shadow run showed it: an
    # instant CAPTURED BEFORE the decision instant has `start_c = t0 > due_at_c` on a completely
    # IDLE engine, so the condition fired with nothing whatever ahead of the candidate. It
    # conflates "waiting for its own capture to be reached" with "queued behind other work",
    # which is the thing channel 1 is about. The condition used is the amount of WORK AHEAD of
    # the candidate at the moment it could first run:
    #
    #     work_ahead_s = max(0, free_at_k - max(t0, due_at_c))
    #
    # which is 0 on an idle engine whatever the capture time, and positive exactly when
    # in-flight or earlier-queued work holds channel 1 past the point the candidate could start.
    work_ahead_s = max(0.0, free_at_k - max(t0, float(cand.due_at)))
    queued = work_ahead_s > 1e-9
    busy_before = busy_in_flight + sum(s.gpu_s for s in before if s.starts_in_horizon)
    gpu_outside = float(pr_c.gpu_s) if queued else 0.0
    h = float(params.H)
    b = max(busy_before + gpu_outside - h, 0.0) - max(busy_before - h, 0.0)

    # DeltaZ: the deficit term, over the devices whose instant outcomes change
    d_z = _delta_z(ro, fleet, cand, before, k, shift, t0, end, cad, l_sh, u_dev,
                   delivered_c, in_horizon_c)

    total = g - loss + d_cv - mu * b + d_z
    return dict(
        delta_j=float(total), basis="closed_form_6_5",
        terms=dict(own_gain=float(g), imposed_loss=float(loss), delta_cv=float(d_cv),
                   backlog_outside_channel_1=float(b), mu=mu, mu_term=float(-mu * b),
                   busy_before_s=float(busy_before), gpu_outside_channel_1=float(gpu_outside),
                   delta_z=float(d_z), shift_s=float(shift),
                   service_s=float(pr_c.service_s), gpu_s=float(pr_c.gpu_s),
                   queued_behind_channel_1=bool(queued), work_ahead_s=float(work_ahead_s),
                   delivered_c=float(delivered_c), start_c=float(start_c),
                   edf_position=int(k), n_queue=len(before),
                   n_shifted=len(shifted), n_jobs_delayed=len(cv_rows)),
        load_factor=lf, continuation_rows=cv_rows,
        in_sample=bool(pr_c.in_sample), not_priced=list(_NOT_PRICED),
        is_measurement=False)


def _delta_z(ro, fleet: Fleet, cand: PendingItem, before: Sequence[_Served], k: int,
             shift: float, t0: float, end: float, cad: float, l_sh: float, u_dev: float,
             delivered_c: float, in_horizon_c: bool) -> float:
    """`rollout._z_term`'s expression, over the devices whose outcomes can change."""
    q_sh = float(ro.params.q_k["SH"])
    dev_meets = bool(u_dev >= q_sh)
    touched = {cand.device}
    for idx, s in enumerate(before):
        if idx >= k and s.starts_in_horizon and s.item.kind == "episode_call":
            touched.add(s.item.device)
    total = 0.0
    for did in sorted(touched):
        dev = fleet.devices.get(did)
        if dev is None:
            continue
        instants = []
        o = t0
        while o < end - 1e-12:
            instants.append(o)
            o += cad
        for p in list(fleet.pending) + list(fleet.in_flight):
            if p.kind == "episode_call" and p.device == did:
                instants.append(float(p.due_at))
        inst_before = sorted({round(x, 9) for x in instants})
        inst_after = sorted({round(x, 9) for x in instants + ([float(cand.due_at)]
                                                              if did == cand.device else [])})
        served: Dict[float, float] = {}
        served_after: Dict[float, float] = {}
        for idx, s in enumerate(before):
            if s.item.kind != "episode_call" or s.item.device != did:
                continue
            if not s.starts_in_horizon:
                continue
            cj = round(float(s.item.due_at), 9)
            served[cj] = s.delivered
            served_after[cj] = s.delivered + (shift if idx >= k else 0.0)
        if did == cand.device and in_horizon_c:
            served_after[round(float(cand.due_at), 9)] = delivered_c

        def frac(insts, table):
            if not insts:
                return None
            ok = 0
            for c in insts:
                d = table.get(c)
                cloud = d is not None and d <= c + l_sh + 1e-12
                if cloud or dev_meets:
                    ok += 1
            return ok / len(insts)

        fb, fa = frac(inst_before, served), frac(inst_after, served_after)
        if fb is None or fa is None:
            continue
        total += float(dev.z_of("SH")) * (fa - fb)
    return float(total)
