"""Spec 3.5, 5.1-5.5: the counterfactual marginal value of an action under a COMMON continuation
policy pi_0, computed by rolling the engine forward over the horizon.

pi_0 is EDF over the pending set and the calendar: deadline-ordered release, ONE unit at a time,
using the same engine model, with episodic calls at their due times. Both sides of every
comparison use it, so DeltaJ_H is a difference of two rollouts that differ only in the first
decision.

WHAT Uhat_H IS HERE. Spec 3.2 defines a cloud action's GAIN against the device's own answer, and
spec 3.5 writes Uhat_H without fixing its origin. This implementation accumulates the GAINS of
delivered opportunities (device-only is the zero), which differs from absolute utility by a
constant that is identical in both rollouts and therefore cancels in DeltaJ_H. The choice is
recorded as ambiguity A2 and makes the device-only baseline exactly zero, which is the reading
that makes an action's sign readable on its own.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .continuation import PRIORITY, continuation_value, expected_remaining_work
from .kvpool import KVPool, prefix_id_for, survival_p_loss
from .tiers import HostPool, TieredStore, p_host_from_occupancy
from .engine import EngineModel, Request
from .profiles import MissingEvidence, Profiles
from .state import Fleet, PendingItem
from .utility import u_sh_cloud, u_sh_device


def _shallow(obj):
    """`copy.copy` without the reduce protocol. StudyLIVE2-perf.

    Every object the rollout clone copies is a plain dataclass with no `__slots__`, no
    `__copy__` and no `__reduce_ex__` of its own, so `copy.copy` ends up in
    `copy._reconstruct` via `__reduce_ex__` for each of 3.7 million calls in a 64-device cell.
    Building the same new object and copying its `__dict__` is what that machinery produces, so
    the result is identical field for field; anything without a `__dict__` falls back to
    `copy.copy` rather than being handled wrongly.
    """
    try:
        d = obj.__dict__
    except AttributeError:
        return copy.copy(obj)
    new = object.__new__(type(obj))
    new.__dict__.update(d)
    return new


def clone_for_rollout(f: Fleet) -> Fleet:
    """D99 (2): the rollout's working copy of the fleet, WITHOUT a full `copy.deepcopy`.

    `Rollout.run` mutates only `f.pending` and `f.jobs`, and `_terminal` copies each job before
    touching it; every other field is read. A `copy.deepcopy` of the fleet nevertheless walks
    every device's link, demand model, controller and episode list on EVERY rollout, which at 16
    devices was 94 % of the coordinator's whole CPU time (135 M `deepcopy` calls, 152.7 of
    162.9 s in a cProfile of one 60 s dry run). This clone gives independent containers for
    everything a rollout or the release loop can write to -- the pending and in-flight lists and
    their items, the jobs, each device and its history beliefs, the per-device deficit counters
    and demand rates, the episode LIST -- and shares only the objects nothing mutates (Link,
    Demand, the controller, each Episode).

    IT IS NOT AN APPROXIMATION. `Rollout.clone_impl = "reference"` restores `copy.deepcopy`, and
    the equivalence tests assert that the two give identical `RolloutResult`s and identical
    decision logs; `test_the_fast_clone_does_not_let_a_rollout_touch_the_callers_fleet` asserts
    the caller's fleet is unchanged after a rollout under both.
    """
    g = Fleet(t=f.t, gpu_backlog_s=f.gpu_backlog_s)
    for did, d in f.devices.items():
        nd = _shallow(d)
        nd.history = {}
        for rep, b in d.history.items():
            nb = _shallow(b)
            nb.probs = dict(b.probs)
            nd.history[rep] = nb
        nd.z = dict(d.z)
        nd.lambda_rc = dict(d.lambda_rc)
        nd.episodes = list(d.episodes)
        g.devices[did] = nd
    g.jobs = {jid: _shallow(j) for jid, j in f.jobs.items()}
    for lst, src in ((g.pending, f.pending), (g.in_flight, f.in_flight)):
        for p in src:
            np_ = _shallow(p)
            np_.meta = dict(p.meta)
            lst.append(np_)
    return g


@dataclass
class RolloutResult:
    u_hat: float
    z_term: float
    terminal: float
    total: float
    deliveries: List[Dict[str, Any]] = field(default_factory=list)
    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    engine_busy_s: float = 0.0
    residual_backlog_s: float = 0.0
    in_sample: bool = True
    kv: Dict[str, Any] = field(default_factory=dict)
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Rollout:
    pf: Profiles
    params: Any
    flags: Any
    engine: EngineModel
    load_pct: int = 25
    # StudyPOL5 Part 3: StudyRES1's measured residency model, used in place of
    # `Params.p_host_for` (which derives residency from host occupancy under
    # `tiers.EVICTION_RULE_ASSUMPTION`) when the caller supplies one. None keeps the old path,
    # so nothing frozen changes and no existing result moves.
    residency_belief: Any = None
    # D99 (2): "fast" is `clone_for_rollout`; "reference" is the unoptimized `copy.deepcopy`,
    # kept selectable so the equivalence test has something to compare against.
    clone_impl: str = "fast"
    # StudyLIVE2-perf Option 0: the terminal state-value sum is memoised within one decision
    # period. "off" is the pre-Option-0 path, byte for byte; "shadow" computes both on every
    # call and raises if they differ. The owner of the period (`arms_policy.decide`) clears it.
    sv_cache_impl: str = "on"
    sv_cache: Any = None

    def state_value_cache(self):
        from .readiness import StateValueCache
        if self.sv_cache is None or self.sv_cache.mode != self.sv_cache_impl:
            self.sv_cache = StateValueCache(mode=self.sv_cache_impl)
        return self.sv_cache

    def _clone(self, fleet: Fleet) -> Fleet:
        if self.clone_impl == "reference":
            return copy.deepcopy(fleet)
        if self.clone_impl != "fast":
            raise ValueError("clone_impl must be 'fast' or 'reference', got %r"
                             % (self.clone_impl,))
        return clone_for_rollout(fleet)

    def _p_host_for(self, host_pool: Any, evicted_tokens: int, prefix_id: Optional[str] = None,
                    t: float = 0.0) -> Dict[str, Any]:
        src = self.residency_belief if self.residency_belief is not None else self.params
        return src.p_host_for(host_pool, evicted_tokens, prefix_id=prefix_id, t=t)

    # ---------------------------------------------------------------- pi_0
    def _edf(self, items: Sequence[PendingItem]) -> List[PendingItem]:
        return sorted(items, key=lambda p: (p.deadline if p.deadline is not None else 1e18,
                                            p.due_at, p.item_id))

    def rel_sigma_for(self, job: Any) -> Optional[float]:
        """D122 v1.1 F4: the committed relative-error sigma for this job's piece size.

        None with the flag off, which keeps `p_finish` the 0/1 indicator byte-for-byte.
        """
        if not self.flags.prob_p_finish:
            return None
        from .completion_error import sigma_for_tokens
        return float(sigma_for_tokens(int(getattr(job, "tokens_per_piece", 0) or 0)))

    def competing_gpu_s(self, f: Fleet, job: Any, t: float) -> float:
        """D122 v1.1 F3: the engine-seconds pi_0 would serve BEFORE this job's pieces.

        Exactly what `continuation_schedule`'s own docstring asks for, and what every caller
        passed 0.0 for. In-flight work counts unconditionally because it is already running;
        pending work counts when its pi_0 EDF key sorts strictly ahead of this job's earliest
        remaining piece. `pr.gpu_s` is the FROZEN step model's own prediction, so no new
        estimator and no new parameter enters here.

        Returns 0.0 with the flag off, which is byte-for-byte the previous behaviour.
        """
        if not self.flags.realistic_competing:
            return 0.0
        jid = getattr(job, "job_id", None)
        mine = [p for p in f.pending if p.job_id == jid]
        if mine:
            key = min((p.deadline if p.deadline is not None else 1e18, p.due_at, p.item_id)
                      for p in mine)
        else:
            key = (float(getattr(job, "deadline", 1e18)), float(t), "")
        total = 0.0
        for p in f.in_flight:
            if p.job_id != jid:
                total += float(self._gpu_s_of(p))
        for p in f.pending:
            if p.job_id == jid:
                continue
            k = (p.deadline if p.deadline is not None else 1e18, p.due_at, p.item_id)
            if k < key:
                total += float(self._gpu_s_of(p))
        return max(total, 0.0)

    @staticmethod
    def occupancy_of(pr: Any) -> float:
        """THE single expression for how much engine one request occupies.

        D127: F3's `competing_s` and spec 3.5's backlog term must not disagree about what the
        engine is doing, so both read this one function. Today it is the step model's `gpu_s`,
        which is what spec 3.5 asks for (`policy_spec_v4.md:151`, "mu is in utility units per
        GPU-second"). If F5a rules that spec 3.5 means remaining WALL-CLOCK occupancy instead,
        the correction belongs HERE and propagates to both readers at once; `pr.service_s` is the
        wall-clock alternative.

        KNOWN DIVERGENCE, recorded for F5a rather than silently reconciled: the two readers pass
        different `concurrent` values to `engine.predict`. The horizon loop passes the live
        concurrency, while `competing_gpu_s` passes 0 so that a job's competing work does not
        depend on the order in which candidates are scored. Whether those should agree is F5a's
        question, not something to settle by inlining a third choice here.
        """
        return float(pr.gpu_s)

    def _gpu_s_of(self, p: PendingItem) -> float:
        """The step model's gpu_s for one item, memoised on the request signature.

        `engine.predict` is a pure function of the request, and the profile is loaded once and
        never mutated during a run, so this is the Option 0 pattern: the value returned is the
        value `predict` would have returned, not a recomputation of it.
        """
        memo = getattr(self, "_gpu_s_memo", None)
        if memo is None:
            memo = self._gpu_s_memo = {}
        meta = tuple(sorted((k, v) for k, v in (p.meta or {}).items()
                            if isinstance(v, (int, float, str, bool, type(None)))))
        ck = (p.kind, p.device, int(p.tokens or 0), int(p.frames or 0), p.readiness, p.job_id,
              meta)
        hit = memo.get(ck)
        if hit is None:
            hit = self.occupancy_of(self.engine.predict(self._request(p), concurrent=0))
            memo[ck] = hit
        return hit

    def _request(self, p: PendingItem) -> Request:
        return Request(kind=p.kind, device=p.device, tokens=p.tokens, frames=p.frames,
                       readiness=p.readiness, job_id=p.job_id, meta=dict(p.meta))

    # ---------------------------------------------------------------- the rollout
    def run(self, fleet: Fleet, release_now: Sequence[str] = (), exclude: Sequence[str] = (),
            extra_pending: Sequence[PendingItem] = (), drop: Sequence[str] = (),
            extra_jobs: Optional[Dict[str, Any]] = None,
            horizon_s: Optional[float] = None, rc_rows: bool = False) -> RolloutResult:
        """`extra_jobs` carries a CANDIDATE job into the rollout without registering it on the
        caller's fleet. Admission must be able to value the job it is deciding about, and a
        declined query must leave nothing behind (addendum A2 as revised), so the candidate lives
        only inside this copy."""
        f = self._clone(fleet)
        # D125 v1.2: the planner evaluates a plan over the JOB'S LIFETIME, not H. `horizon_s`
        # None keeps the dispatch horizon, so every existing caller is unchanged.
        t0, H = f.t, (float(self.params.H) if horizon_s is None else float(horizon_s))
        end = t0 + H
        for p in extra_pending:
            f.pending.append(copy.deepcopy(p))
        if extra_jobs:
            f.jobs.update(copy.deepcopy(dict(extra_jobs)))
        if drop:
            f.pending = [p for p in f.pending if p.item_id not in set(drop)]
        pend = {p.item_id: p for p in f.pending}
        forced = [pend[i] for i in release_now if i in pend]
        rest = self._edf([p for p in f.pending
                          if p.item_id not in set(release_now) and p.item_id not in set(exclude)])
        queue = forced + rest

        store = self._build_store(f)
        pool = store.gpu if store is not None else None
        free_at = t0
        busy = 0.0
        in_sample = True
        deliveries: List[Dict[str, Any]] = []
        jobs_progress: Dict[str, int] = {}
        demand_tokens = 0
        for p in f.in_flight:
            pr = self.engine.predict(self._request(p), concurrent=max(len(f.in_flight) - 1, 0),
                                     load_pct=self.load_pct)
            in_sample = in_sample and pr.in_sample
            free_at = max(free_at, t0 + pr.service_s)
            busy += self.occupancy_of(pr)
            if p.kind == "episode_call":
                # D98: an SH call ALREADY IN FLIGHT is credited at its own instant's deadline
                # (spec 6.3: "never worth zero merely because it lands after the horizon"), so
                # its predicted delivery has to be visible to the SH credit even though the call
                # was released before t0. An episode call carries no job_id, so no RC accounting
                # (`_rc_utility`, `_prefix_risk`) can see these rows.
                dv = f.devices.get(p.device)
                deliveries.append(dict(
                    item_id=p.item_id, kind=p.kind, device=p.device, capture_at=p.due_at,
                    start=t0, delivered_at=t0 + pr.service_s + (dv.link.down_s() if dv else 0.0),
                    job_id=p.job_id, tokens=int(p.tokens), in_sample=pr.in_sample,
                    in_flight_at_t0=True))

        concurrent = len(f.in_flight)
        sh_tail: List[PendingItem] = []
        for p in queue:
            start = max(free_at, p.due_at)
            if start > end:
                # D98: an SH call that cannot START inside the horizon is NOT automatically
                # device-valued any more, because its own deadline may lie past t0 + H. It is
                # simulated through to delivery in the tail pass below. Every other kind keeps
                # the old behaviour: work that cannot start inside the horizon is not simulated.
                if p.kind == "episode_call":
                    sh_tail.append(p)
                elif p.kind == "rc_piece" and self.flags.tail_cursor_on():
                    # D122 v1.1: the same branch for RECALL. Without this an rc_piece that
                    # cannot start inside H is simply dropped, so a rebuild's payoff is worth
                    # zero merely because it lands after t0 + H, which is exactly the thing D98
                    # fixed for SH.
                    sh_tail.append(p)
                continue
            pr = self.engine.predict(self._request(p), concurrent=concurrent,
                                     load_pct=self.load_pct)
            in_sample = in_sample and pr.in_sample
            finish = start + pr.service_s
            busy += self.occupancy_of(pr)
            free_at = finish
            if pool is not None:
                pid = prefix_id_for(p.job_id) if p.job_id else "transient:%s" % p.item_id
                pool.allocate(pid, max(p.tokens, 0), start, owner_job=p.job_id,
                              owner_device=p.device, store=store)
                pool.reference(pid, finish, held=False)
                demand_tokens += max(p.tokens, 0)
            dev = f.devices.get(p.device)
            down = dev.link.down_s() if dev else 0.0
            deliveries.append(dict(item_id=p.item_id, kind=p.kind, device=p.device,
                                   capture_at=p.due_at, start=start, delivered_at=finish + down,
                                   job_id=p.job_id, tokens=int(p.tokens),
                                   in_sample=pr.in_sample))
            if p.job_id:
                jobs_progress[p.job_id] = jobs_progress.get(p.job_id, 0) + 1

        n_tail_simulated = 0
        tail_progress: Dict[str, int] = {}
        if sh_tail:
            # D98 TAIL. Spec 5.1 and 6.3 as amended credit each SH instant at ITS OWN deadline,
            # so a released call has to be simulated through to delivery even when that delivery
            # lands after t0 + H. The pass continues the engine from where the horizon left it
            # and stops at the LAST deadline any credited instant can have, so it is bounded.
            # COST: at most one extra engine.predict per SH call that could not start inside H.
            # Nothing here is charged to `busy`, the KV pool, `demand_tokens` or `jobs_progress`:
            # the horizon's own accounting is byte-for-byte what it was, and only the SH credit
            # and `in_sample` see these deliveries.
            latest = max([end]
                         + [float(p.due_at) for p in f.pending if p.kind == "episode_call"]
                         + [float(p.due_at) for p in f.in_flight if p.kind == "episode_call"]
                         ) + float(self.params.L_k["SH"])
            if self.flags.tail_cursor_on():
                # D122 v1.1: the same rule, "the last deadline any credited unit can have", read
                # off the field that holds it. An rc_piece carries an ABSOLUTE deadline, so no
                # L_k is added. ONE cursor is shared with the SH tail below, because the engine
                # is serial and two cursors both starting at `free_at` would double-book it.
                latest = max([latest]
                             + [float(p.deadline) for p in f.pending if p.kind == "rc_piece"]
                             + [float(p.deadline) for p in f.in_flight if p.kind == "rc_piece"])
            tail_free = free_at
            for p in sh_tail:
                start = max(tail_free, p.due_at)
                if start > latest:
                    break
                pr = self.engine.predict(self._request(p), concurrent=concurrent,
                                         load_pct=self.load_pct)
                in_sample = in_sample and pr.in_sample
                tail_free = start + pr.service_s
                n_tail_simulated += 1
                dv = f.devices.get(p.device)
                deliveries.append(dict(
                    item_id=p.item_id, kind=p.kind, device=p.device, capture_at=p.due_at,
                    start=start, delivered_at=tail_free + (dv.link.down_s() if dv else 0.0),
                    job_id=p.job_id, tokens=int(p.tokens), in_sample=pr.in_sample,
                    beyond_horizon=True))
                # D122 v1.1: the tail's progress is kept in its OWN view. `jobs_progress` is what
                # `_terminal` and `_prefix_risk` read, and D98's isolation rule keeps the
                # horizon's accounting byte-for-byte, so only `_rc_utility` sees this.
                if p.kind == "rc_piece" and p.job_id:
                    tail_progress[p.job_id] = tail_progress.get(p.job_id, 0) + 1

        ghat_by_job = {p.job_id: p.meta["ghat"] for p in queue
                       if p.job_id and isinstance(p.meta.get("ghat"), (int, float))}
        u_hat, opps = self._opportunity_utility(f, t0, end, deliveries)
        # D122 v1.1: `_rc_utility` already credits omega_RC x u_RC for a job whose pieces are all
        # done and whose last delivery meets `job.deadline`, which IS "at the question's own
        # deadline". It never fired because `jobs_progress` counts only pieces served inside H.
        # The tail's own progress is added HERE and nowhere else, so `_terminal` and
        # `_prefix_risk` keep the horizon's accounting unchanged.
        rc_progress = jobs_progress
        if (self.flags.tail_cursor_on() or rc_rows) and tail_progress:
            rc_progress = dict(jobs_progress)
            for jid, k in tail_progress.items():
                rc_progress[jid] = rc_progress.get(jid, 0) + k
        u_hat += self._rc_utility(f, rc_progress, deliveries, ghat_by_job)
        # D125 v1.2: F1 is OFF in v1.2 and its `_rc_opportunities` was the ONLY route that put RC
        # rows into `_z_term`, so the planner routes its own. Without this the design note's
        # deficit term would read as implemented while contributing nothing.
        if self.flags.tail_zrows_on() or rc_rows:
            opps = list(opps) + self._rc_opportunities(f, rc_progress, deliveries)
        z_term = self._z_term(f, opps)
        risk = self._prefix_risk(f, store, deliveries, jobs_progress, end, demand_tokens,
                                 busy_until=free_at)
        terminal, tdetail = self._terminal(f, end, jobs_progress, busy, risk)
        residual = max(busy - H, 0.0)
        return RolloutResult(
            u_hat=u_hat, z_term=z_term, terminal=terminal, total=u_hat + z_term + terminal,
            deliveries=deliveries, opportunities=opps, engine_busy_s=busy,
            residual_backlog_s=residual, in_sample=in_sample,
            kv=(store.describe() if store is not None else dict(enabled=False)),
            detail=dict(terminal=tdetail, n_queue=len(queue), horizon_s=H,
                        released=[d["item_id"] for d in deliveries], prefix_risk=risk,
                        sh_tail_simulated=n_tail_simulated, sh_tail_pending=len(sh_tail)))

    # ---------------------------------------------------------------- A6: the KV pool
    def _build_pool(self, f: Fleet) -> Optional[KVPool]:
        """Addendum A6.2. The pool starts from what the fleet already believes it holds: each
        in-progress job's BUILT prefix, unreferenced between pieces, plus each device's history
        believed to be on the GPU."""
        if not getattr(self.params, "kv_pool_model", True):
            return None
        cap = int(getattr(self.params, "gpu_kv_capacity_tokens", 0) or 0)
        if cap <= 0:
            return None
        pool = KVPool(capacity_tokens=cap, t=f.t)
        for jid, job in f.jobs.items():
            built = job.pieces_done * job.tokens_per_piece
            if built > 0 and not job.answered:
                pool.put(prefix_id_for(jid), built, f.t, referenced=False, owner_job=jid,
                         owner_device=job.device, rep=job.rep)
        for did, dev in f.devices.items():
            for rep, b in dev.history.items():
                if b.probs.get("GPU", 0.0) > 0.5 and b.size_tokens > 0:
                    pool.put("history:%s:%s" % (did, rep), b.size_tokens, f.t,
                             referenced=False, owner_device=did, rep=rep)
        return pool

    def _build_host(self, f: Fleet) -> Optional[HostPool]:
        """D56: the host-warm tier, BOUNDED, seeded from what the fleet believes it holds there.

        A capacity of 0 means NO HOST TIER, which is StudyENG1b's E0 server: evicted blocks are
        recomputed and P_host is 0 by construction."""
        cap = int(getattr(self.params, "host_kv_capacity_tokens", 0) or 0)
        if cap <= 0:
            return None
        host = HostPool(capacity_tokens=cap,
                        eviction_rule=self.params.host_eviction_callable(),
                        rule_name=str(getattr(self.params, "host_eviction_rule", "lru")),
                        t=f.t)
        for did, dev in f.devices.items():
            for rep, b in dev.history.items():
                if b.probs.get("HOST", 0.0) > 0.5 and b.size_tokens > 0:
                    host.accept("history:%s:%s" % (did, rep), b.size_tokens, f.t,
                                owner_device=did, rep=rep)
        return host

    def _build_store(self, f: Fleet) -> Optional[TieredStore]:
        """D56's three tiers as one object: GPU pool, bounded host pool, and cold beneath both.
        Nothing is ever deleted; a prefix that leaves both warm tiers is COLD."""
        pool = self._build_pool(f)
        if pool is None:
            return None
        return TieredStore(gpu=pool, host=self._build_host(f))

    def _prefix_risk(self, f: Fleet, store: Optional[TieredStore],
                     deliveries: Sequence[Dict[str, Any]],
                     progress: Dict[str, int], end: float,
                     demand_tokens: int, busy_until: float = 0.0) -> Dict[str, Any]:
        """A6.1 and A6.2: P_loss per in-progress job, read from the pool's predicted eviction
        over the gap to that job's next piece, plus the restore work it implies.

        D56: P_host is read from the BOUNDED host tier's occupancy at the moment of the predicted
        eviction, not from a constant, so a full host tier makes deferral more expensive exactly
        as it physically is."""
        out: Dict[str, Any] = {}
        if store is None or store.gpu is None:
            return out
        pool = store.gpu
        for jid, job in f.jobs.items():
            built = (job.pieces_done + progress.get(jid, 0)) * job.tokens_per_piece
            if job.answered or built <= 0 or job.pieces_left() - progress.get(jid, 0) <= 0:
                continue
            # A6.1 scopes the risk to the DEFER branch: the prefix is exposed only from the
            # moment the last piece of THIS job stopped referencing it. A piece released inside
            # the horizon therefore shortens the exposure window, and only the competing demand
            # that lands INSIDE that window can evict the prefix.
            last = max((d["delivered_at"] for d in deliveries if d["job_id"] == jid),
                       default=f.t)
            gap = max(end - last, 0.0)
            exposed_demand = sum(int(d.get("tokens", 0)) for d in deliveries
                                 if d["job_id"] != jid and d["start"] >= last)
            pid = prefix_id_for(jid)
            pred = pool.predict_loss(pid, exposed_demand, end)
            beyond = survival_p_loss(getattr(self.params, "survival_curve", None), gap)
            p_loss = min(1.0, pred["p_loss"] + (1.0 - pred["p_loss"]) * beyond["p_loss"])
            ph = self._p_host_for(store.host, int(round(p_loss * built)), prefix_id=pid, t=end)
            # StudyENG1b section 5: the LARGER cost of deferring under pressure is not the loss
            # but the QUEUE. A resume issued while another history build is still prefilling
            # waited 6 to 10 s whether or not the prefix survived. That is not a constant here:
            # it is read off this rollout's own engine timeline, as the work pi_0 still has in
            # flight at the moment the resume would be issued.
            resume_queue = max(float(busy_until) - end, 0.0)
            rw = expected_remaining_work(
                job, self.engine, self.pf, p_loss=p_loss,
                p_host=float(ph["p_host"]), prefix_tokens=built,
                beyond_horizon_unmeasured=not beyond["available"])
            out[jid] = dict(p_loss=p_loss, gap_s=gap, exposed_demand_tokens=exposed_demand,
                            exposure_starts_at=last, in_horizon=pred, beyond_horizon=beyond,
                            p_host=ph, resume_queue_s=resume_queue,
                            extra_work_s=rw.extra_s, w_left_s=rw.w_left_s,
                            total_work_s=rw.total_s, built_prefix_tokens=built,
                            beyond_horizon_unmeasured=rw.beyond_horizon_unmeasured)
        return out

    # ---------------------------------------------------------------- SH opportunities
    def _opportunity_utility(self, f: Fleet, t0: float, end: float,
                             deliveries: Sequence[Dict[str, Any]]) -> Tuple[float, List[Dict]]:
        """Spec 5.1 and 6.3 AS AMENDED BY D98: SH VALUE IS PER INSTANT.

        Under D62 every SH decision instant i is its own opportunity, with its own capture c_i
        and its own deadline c_i + L_SH. Instant i is credited

            omega_SH * u_SH(cloud, delivered_at - c_i)   if delivered_at <= c_i + L_SH
            omega_SH * u_SH(device)                      otherwise

        AT ITS OWN DEADLINE, even when that deadline falls after t0 + H. Instants that are
        pending, in flight, or predicted to arrive inside the horizon by the cadence calendar are
        all credited the same way; the released calls whose delivery lands past the horizon are
        simulated through to delivery by the tail pass in `run`.

        THIS RETIRES the display-freshness rule, which credited only the cadence points inside
        [t0, t0 + H), each served by the newest delivery already landed by that point. With
        T_k = 0.5 s and H = 0.5 s that grid held exactly ONE point, o = t0, which no action taken
        at t0 can ever serve, so the marginal value of admitting a monitoring call was
        structurally zero whenever H <= T_k (StudyLIVE2-coord open issue 1: 0 of 240 instants
        admitted at H = 0.5 s, DeltaJ exactly 0.0 on every one), and it did not match the
        measured outcome (D71, D85).

        u_SH itself, its calibration, omega and the deficit-counter term are UNCHANGED: what
        changed is which instant a delivery is credited to, and at what time that instant is
        valued. The returned list keeps ONE ENTRY PER CREDITED INSTANT, so the deficit counters
        (`_z_term`) and the live2 joiner read it exactly as before.
        """
        cad = float(self.params.T_k["SH"])
        l_sh = float(self.params.L_k["SH"])
        u_dev = u_sh_device(self.pf)
        w = self.params.omega["SH"]
        total = 0.0
        out: List[Dict[str, Any]] = []
        calls_by_dev: Dict[str, List[Dict[str, Any]]] = {}
        for d in deliveries:
            if d["kind"] == "episode_call":
                calls_by_dev.setdefault(d["device"], []).append(d)
        for did, dev in f.devices.items():
            # The instants of this device: the cadence calendar inside the horizon (the existing
            # demand model, unchanged), plus the capture of every SH item pending or in flight,
            # whose deadline may lie outside it. `f.pending` is the same in both branches of a
            # release / defer / dispatch comparison (`exclude` filters the QUEUE, not the fleet),
            # so the instant SET cancels in DeltaJ there; for an admit it can differ by the
            # candidate's own instant, which contributes exactly zero when device-served because
            # spec 3.2's scale is a GAIN against the device answer (ambiguity A2).
            instants: List[float] = []
            o = t0
            while o < end - 1e-12:
                instants.append(o)
                o += cad
            for p in list(f.pending) + list(f.in_flight):
                if p.kind == "episode_call" and p.device == did:
                    instants.append(float(p.due_at))
            served_ids: set = set()
            for c in sorted({round(x, 9) for x in instants}):
                deadline = c + l_sh
                # D62: the call that can serve instant i is the one CAPTURED AT c_i. Nothing
                # else serves it, which is what makes the value per instant rather than per
                # display refresh.
                cand = [d for d in calls_by_dev.get(did, ())
                        if abs(float(d["capture_at"]) - c) < 1e-6
                        and d["item_id"] not in served_ids]
                served = None
                for d in sorted(cand, key=lambda x: float(x["delivered_at"])):
                    if float(d["delivered_at"]) <= deadline + 1e-12:
                        served = d
                        break
                if served is None:
                    u, inrange = u_dev, True
                    kind = "device"
                else:
                    served_ids.add(served["item_id"])
                    u, inrange = u_sh_cloud(self.pf,
                                            max(float(served["delivered_at"]) - c, 0.0),
                                            1, cad, allow_m_gt_1=self.flags.merging)
                    kind = "cloud"
                total += w * (u - u_dev)
                out.append(dict(device=did, task="SH", t=c, served_by=kind, utility=u,
                                device_utility=u_dev, within_measured_delay=inrange,
                                met_slo=bool(kind == "cloud" or u_dev >= self.params.q_k["SH"]),
                                deadline=deadline,
                                delivered_at=(float(served["delivered_at"]) if served else None),
                                beyond_horizon=bool(deadline > end + 1e-12)))
        return total, out

    # ---------------------------------------------------------------- RC inside the horizon
    def _rc_utility(self, f: Fleet, progress: Dict[str, int],
                    deliveries: Sequence[Dict[str, Any]],
                    ghat_by_job: Optional[Dict[str, float]] = None) -> float:
        """Addendum A1: when the escalation basis has already estimated this request's gain, the
        rollout uses THAT Ghat rather than recomputing a gain of its own, so device-side
        triggering and cloud admission cannot disagree."""
        total = 0.0
        for jid, job in f.jobs.items():
            done = job.pieces_done + progress.get(jid, 0)
            if done < job.pieces_total or job.answered:
                continue
            last = max((d["delivered_at"] for d in deliveries if d["job_id"] == jid),
                       default=None)
            if last is None or last > job.deadline:
                continue
            g = (ghat_by_job or {}).get(jid)
            if g is None:
                acc_c = self.pf.rc_accuracy(job.qtype, job.rep, "cloud")
                acc_d = self.pf.rc_accuracy(job.qtype, "D2", "device")
                g = self.pf.omega("RC") * (acc_c - acc_d)
            total += float(g)
        return total

    def _rc_opportunities(self, f: Fleet, progress: Dict[str, int],
                          deliveries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """D122 v1.1: one row per unanswered RC job, so the per-device deficit can be credited.

        `_opportunity_utility` emits rows with `task="SH"` ONLY, so `(device, "RC")` never reached
        `_z_term`'s aggregation and `z_of("RC")` was never read by it AT ALL, for any z. That is
        why a non-zero RC deficit could not change a decision. `met_slo` is set from whether the
        answer is predicted to arrive by the question's OWN deadline, which is the same rule D98
        applies to an SH instant.
        """
        out: List[Dict[str, Any]] = []
        for jid, job in f.jobs.items():
            if job.answered:
                continue
            done = job.pieces_done + progress.get(jid, 0)
            last = max((d["delivered_at"] for d in deliveries if d["job_id"] == jid),
                       default=None)
            met = bool(done >= job.pieces_total and last is not None
                       and last <= job.deadline)
            out.append(dict(device=job.device, task="RC", t=float(job.deadline),
                            served_by=("cloud" if met else "device"),
                            met_slo=met, deadline=float(job.deadline),
                            delivered_at=(float(last) if last is not None else None),
                            counts_question=("job", jid)))
        return out

    # ---------------------------------------------------------------- deficits
    def _z_term(self, f: Fleet, opps: Sequence[Dict[str, Any]]) -> float:
        """Spec 3.5's sum of Z(i, k) * Phat_success_H(i, k). Phat is the predicted fraction of the
        device's eligible opportunities INSIDE the horizon that meet the SLO (spec 3.4's online
        prediction, not a measurement)."""
        agg: Dict[Tuple[str, str], List[int]] = {}
        for o in opps:
            k = (o["device"], o["task"])
            agg.setdefault(k, [0, 0])
            agg[k][1] += 1
            if o["met_slo"]:
                agg[k][0] += 1
        total = 0.0
        for (did, task), (ok, n) in agg.items():
            if not n:
                continue
            total += f.devices[did].z_of(task) * (ok / n)
        return total

    # ---------------------------------------------------------------- terminal value (5.3)
    def _terminal(self, f: Fleet, end: float, progress: Dict[str, int],
                  busy: float, risk: Optional[Dict[str, Any]] = None
                  ) -> Tuple[float, Dict[str, Any]]:
        cont = 0.0
        cont_detail = []
        valued_jobs = set()
        for jid, job in f.jobs.items():
            j = _shallow(job)
            j.pieces_done = min(job.pieces_done + progress.get(jid, 0), job.pieces_total)
            if j.answered or j.pieces_left() == 0:
                continue
            dev = f.devices[j.device]
            acc_c = self.pf.rc_accuracy(j.qtype, j.rep, "cloud")
            acc_d = self.pf.rc_accuracy(j.qtype, "D2", "device")
            extra = float((risk or {}).get(jid, {}).get("extra_work_s", 0.0))
            # D122 fix A3: value a promoted job under the class it was promoted TO. `_update_jobs`
            # sets `job.feasibility = PRIORITY` by spec 7.3's bounded-waiting check, and before
            # this flag that label could not reach the value it was assigned for. NOTE, measured
            # and reported: with `competing_s = 0.0`, which is what this call passes, `priority`
            # has no effect at all, because `continuation_schedule` uses it only as
            # `cursor = t + (0.0 if priority else competing_s)`. So this is a no-op TODAY and
            # becomes live the moment competing work is modelled. It is wired anyway so the label
            # is not silently discarded.
            prio = bool(self.flags.honour_job_priority and j.feasibility == PRIORITY)
            comp = self.competing_gpu_s(f, j, end)
            v = continuation_value(j, end, self.engine, competing_s=comp, priority=prio,
                                   rel_sigma=self.rel_sigma_for(j),
                                   omega_rc=self.pf.omega("RC"), acc_cloud=acc_c,
                                   acc_device=acc_d, z=dev.z_of("RC"), d_p_success=0.0,
                                   p_reachable=dev.link.p_reachable_within_hs,
                                   resolution_s=self.params.continuation_resolution_s,
                                   extra_work_s=extra)
            cont += v
            valued_jobs.add((j.device, j.rep, jid))
            cont_detail.append(dict(job_id=jid, value=v, pieces_left=j.pieces_left(),
                                    feasibility=j.feasibility, a6_extra_work_s=extra,
                                    p_loss=(risk or {}).get(jid, {}).get("p_loss"),
                                    counts_question=("job", jid)))
        sv = 0.0
        sv_detail = []
        from .readiness import assert_single_counting, state_value
        for did, dev in f.devices.items():
            if dev.qtype is None:
                continue
            for rep, b in dev.history.items():
                dmd = getattr(dev, "demand", None)
                if dmd is None:
                    continue
                in_progress = [jid for (d2, r2, jid) in valued_jobs if d2 == did and r2 == rep]
                r = state_value(self.pf, dev, rep, dmd, self.params.H_s, dev.qtype, dev.link,
                                self.params.L_k["RC"], self.pf.omega("RC"),
                                in_episode=bool(dev.episodes),
                                exclude_job=(in_progress[0] if in_progress else None),
                                cache=self.state_value_cache())
                sv += r["value"]
                sv_detail.append(dict(r, device=did, counts_question=("future", rep)))
        assert_single_counting(cont_detail, sv_detail)
        a6_backlog = sum(float(v.get("extra_work_s", 0.0)) for v in (risk or {}).values())
        mu_term = -float(self.params.mu) * (max(busy - self.params.H, 0.0) + a6_backlog)
        return cont + sv + mu_term, dict(continuation=cont_detail, state_value=sv_detail,
                                         single_counting="A6.3 with v3 5.3: the job's own "
                                                         "question is valued by its continuation "
                                                         "value and NEVER by state value, which "
                                                         "counts FUTURE ARRIVALS only; "
                                                         "readiness.assert_single_counting "
                                                         "enforces it on every rollout",
                                         mu_term=mu_term, mu=float(self.params.mu),
                                         residual_backlog_s=max(busy - self.params.H, 0.0),
                                         a6_expected_restore_backlog_s=a6_backlog,
                                         a6_note="A6.1's expected restore work is GPU work that "
                                                 "will have to be done, so spec 5.3's third "
                                                 "terminal item prices it: residual backlog not "
                                                 "covered by a job's continuation value. With "
                                                 "mu at its PLACEHOLDER 0 this channel is "
                                                 "silent and A6 reaches decisions only through "
                                                 "feasibility and the memory decision",
                                         sign_note="mu is a PRICE, so backlog SUBTRACTS from "
                                                   "terminal value (ambiguity A19)",
                                         rule="spec 5.3: each item valued exactly once")

    def continuation_value_at_risk(self, fleet: Fleet, job_id: str) -> Dict[str, Any]:
        """A6.3: the DROP in this job's continuation value if its built prefix is lost."""
        f = copy.deepcopy(fleet)
        job = f.jobs[job_id]
        dev = f.devices[job.device]
        acc_c = self.pf.rc_accuracy(job.qtype, job.rep, "cloud")
        acc_d = self.pf.rc_accuracy(job.qtype, "D2", "device")
        built = job.pieces_done * job.tokens_per_piece
        from .continuation import restore_costs_s
        w_reload, w_rebuild = restore_costs_s(built, self.pf)
        ph = self._p_host_for(self._build_host(f), built,
                                    prefix_id=prefix_id_for(job_id), t=f.t)
        p_host = float(ph["p_host"])
        lost_extra = p_host * w_reload + (1.0 - p_host) * w_rebuild
        kw = dict(omega_rc=self.pf.omega("RC"), acc_cloud=acc_c, acc_device=acc_d,
                  z=dev.z_of("RC"), p_reachable=dev.link.p_reachable_within_hs,
                  resolution_s=self.params.continuation_resolution_s)
        comp = self.competing_gpu_s(f, job, f.t)
        rs = self.rel_sigma_for(job)
        safe = continuation_value(job, f.t, self.engine, comp, False, extra_work_s=0.0,
                                  rel_sigma=rs, **kw)
        lost = continuation_value(job, f.t, self.engine, comp, False, extra_work_s=lost_extra,
                                  rel_sigma=rs, **kw)
        return dict(value_at_risk=float(safe - lost), safe=float(safe), if_lost=float(lost),
                    restore_work_s=lost_extra, built_prefix_tokens=built, p_host=ph)

    # ---------------------------------------------------------------- 5.5 fallback
    def closed_form(self, fleet: Fleet, item: PendingItem) -> float:
        """Spec 5.5: the direct delay this release imposes on overlapping requests from the step
        model, times a load factor from step occupancy, with mu applied to work outside channel 1
        and the continuation value retained. Only usable with the fallback flag on, and the
        fallback must itself pass T0."""
        if not self.flags.closed_form_fallback:
            raise MissingEvidence("the closed-form fallback is a conditional mechanism (spec 5.5) "
                                  "and its flag is off; it has not passed T0")
        pr = self.engine.predict(self._request(item), concurrent=len(fleet.in_flight),
                                 load_pct=self.load_pct)
        load = 1.0 + len(fleet.in_flight)
        return -float(self.params.mu) * pr.gpu_s * load


def delta_j(ro: Rollout, fleet: Fleet, action: Dict[str, Any],
            rc_rows: bool = False) -> Dict[str, Any]:
    """DeltaJ_H(a) = Jhat(action) - Jhat(reference), both under pi_0 (spec 3.5).

    The four reference pairs of spec 3.5 are the only ones accepted:
      release    item_id now        vs defer it to its next candidate slot
      defer      the same pair, the other way round, which is what A6 prices
      admit      extra pending      vs decline (nothing added)
      state      a state action     vs no change
      dispatch   an episode call    vs hold to the next slot

    D131: `rc_rows` routes the RC opportunity rows into `_z_term` for the DISPATCH path too.
    Without it only the planner routed them, so `z[RC]` was computed and never reached an
    admission decision: measured at n=12, `update_deficit` fires for RC and z[RC] reaches 543.58,
    yet every B2 gain gave byte-identical outcomes because the term had no path to a decision.
    That is an ABSENT link by the Step 2 standard, not a weak one.
    """
    kind = action["kind"]
    if kind == "release":
        a = ro.run(fleet, release_now=[action["item_id"]], rc_rows=rc_rows)
        b = ro.run(fleet, exclude=[action["item_id"]], rc_rows=rc_rows)
    elif kind == "admit":
        a = ro.run(fleet, extra_pending=action["items"], extra_jobs=action.get("jobs"),
                   rc_rows=rc_rows)
        b = ro.run(fleet, rc_rows=rc_rows)
    elif kind == "defer":
        a = ro.run(fleet, exclude=[action["item_id"]], rc_rows=rc_rows)
        b = ro.run(fleet, release_now=[action["item_id"]], rc_rows=rc_rows)
    elif kind == "state":
        a = ro.run(fleet, extra_pending=action["items"], release_now=[i.item_id for i
                                                                     in action["items"]], rc_rows=rc_rows)
        b = ro.run(fleet, rc_rows=rc_rows)
    elif kind == "dispatch":
        a = ro.run(fleet, release_now=[action["item_id"]], rc_rows=rc_rows)
        b = ro.run(fleet, exclude=[action["item_id"]], rc_rows=rc_rows)
    else:
        raise ValueError("unknown action kind %r; spec 3.5 fixes the reference actions" % kind)
    return dict(delta_j=a.total - b.total, action=a.total, reference=b.total,
                in_sample=bool(a.in_sample and b.in_sample),
                terms=dict(u_hat=a.u_hat - b.u_hat, z=a.z_term - b.z_term,
                           terminal=a.terminal - b.terminal),
                engine_busy_delta_s=a.engine_busy_s - b.engine_busy_s)
