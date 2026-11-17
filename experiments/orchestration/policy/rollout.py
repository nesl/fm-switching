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

from .continuation import continuation_value, expected_remaining_work
from .kvpool import KVPool, prefix_id_for, survival_p_loss
from .tiers import HostPool, TieredStore, p_host_from_occupancy
from .engine import EngineModel, Request
from .profiles import MissingEvidence, Profiles
from .state import Fleet, PendingItem
from .utility import u_sh_cloud, u_sh_device


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

    # ---------------------------------------------------------------- pi_0
    def _edf(self, items: Sequence[PendingItem]) -> List[PendingItem]:
        return sorted(items, key=lambda p: (p.deadline if p.deadline is not None else 1e18,
                                            p.due_at, p.item_id))

    def _request(self, p: PendingItem) -> Request:
        return Request(kind=p.kind, device=p.device, tokens=p.tokens, frames=p.frames,
                       readiness=p.readiness, job_id=p.job_id, meta=dict(p.meta))

    # ---------------------------------------------------------------- the rollout
    def run(self, fleet: Fleet, release_now: Sequence[str] = (), exclude: Sequence[str] = (),
            extra_pending: Sequence[PendingItem] = (), drop: Sequence[str] = (),
            extra_jobs: Optional[Dict[str, Any]] = None) -> RolloutResult:
        """`extra_jobs` carries a CANDIDATE job into the rollout without registering it on the
        caller's fleet. Admission must be able to value the job it is deciding about, and a
        declined query must leave nothing behind (addendum A2 as revised), so the candidate lives
        only inside this copy."""
        f = copy.deepcopy(fleet)
        t0, H = f.t, float(self.params.H)
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
            busy += pr.gpu_s

        concurrent = len(f.in_flight)
        for p in queue:
            start = max(free_at, p.due_at)
            if start > end:
                continue
            pr = self.engine.predict(self._request(p), concurrent=concurrent,
                                     load_pct=self.load_pct)
            in_sample = in_sample and pr.in_sample
            finish = start + pr.service_s
            busy += pr.gpu_s
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

        ghat_by_job = {p.job_id: p.meta["ghat"] for p in queue
                       if p.job_id and isinstance(p.meta.get("ghat"), (int, float))}
        u_hat, opps = self._opportunity_utility(f, t0, end, deliveries)
        u_hat += self._rc_utility(f, jobs_progress, deliveries, ghat_by_job)
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
                        released=[d["item_id"] for d in deliveries], prefix_risk=risk))

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
            ph = self.params.p_host_for(store.host, int(round(p_loss * built)), prefix_id=pid,
                                        t=end)
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
        """Spec 1.2: every decision instant on the task's cadence is an eligible opportunity,
        escalated or not. The display is sample-and-hold over cloud deliveries, so an opportunity
        is served by the NEWEST delivery already landed and its delivered delay is measured from
        that answer's CAPTURE time."""
        cad = float(self.params.T_k["SH"])
        u_dev = u_sh_device(self.pf)
        w = self.params.omega["SH"]
        total = 0.0
        out: List[Dict[str, Any]] = []
        per_dev = {}
        for d in deliveries:
            if d["kind"] == "episode_call":
                per_dev.setdefault(d["device"], []).append(d)
        for did, dev in f.devices.items():
            ds = sorted(per_dev.get(did, []), key=lambda x: x["delivered_at"])
            n = 0
            o = t0
            while o < end - 1e-12:
                served = None
                for d in ds:
                    if d["delivered_at"] <= o + 1e-12:
                        served = d
                if served is None:
                    u, inrange = u_dev, True
                    kind = "device"
                else:
                    u, inrange = u_sh_cloud(self.pf, max(o - served["capture_at"], 0.0),
                                            1, cad, allow_m_gt_1=self.flags.merging)
                    kind = "cloud"
                total += w * (u - u_dev)
                out.append(dict(device=did, task="SH", t=o, served_by=kind, utility=u,
                                device_utility=u_dev, within_measured_delay=inrange,
                                met_slo=bool(kind == "cloud" or u_dev >= self.params.q_k["SH"])))
                o += cad
                n += 1
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
            j = copy.copy(job)
            j.pieces_done = min(job.pieces_done + progress.get(jid, 0), job.pieces_total)
            if j.answered or j.pieces_left() == 0:
                continue
            dev = f.devices[j.device]
            acc_c = self.pf.rc_accuracy(j.qtype, j.rep, "cloud")
            acc_d = self.pf.rc_accuracy(j.qtype, "D2", "device")
            extra = float((risk or {}).get(jid, {}).get("extra_work_s", 0.0))
            v = continuation_value(j, end, self.engine, competing_s=0.0, priority=False,
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
                                exclude_job=(in_progress[0] if in_progress else None))
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
        ph = self.params.p_host_for(self._build_host(f), built,
                                    prefix_id=prefix_id_for(job_id), t=f.t)
        p_host = float(ph["p_host"])
        lost_extra = p_host * w_reload + (1.0 - p_host) * w_rebuild
        kw = dict(omega_rc=self.pf.omega("RC"), acc_cloud=acc_c, acc_device=acc_d,
                  z=dev.z_of("RC"), p_reachable=dev.link.p_reachable_within_hs,
                  resolution_s=self.params.continuation_resolution_s)
        safe = continuation_value(job, f.t, self.engine, 0.0, False, extra_work_s=0.0, **kw)
        lost = continuation_value(job, f.t, self.engine, 0.0, False, extra_work_s=lost_extra,
                                  **kw)
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


def delta_j(ro: Rollout, fleet: Fleet, action: Dict[str, Any]) -> Dict[str, Any]:
    """DeltaJ_H(a) = Jhat(action) - Jhat(reference), both under pi_0 (spec 3.5).

    The four reference pairs of spec 3.5 are the only ones accepted:
      release    item_id now        vs defer it to its next candidate slot
      defer      the same pair, the other way round, which is what A6 prices
      admit      extra pending      vs decline (nothing added)
      state      a state action     vs no change
      dispatch   an episode call    vs hold to the next slot
    """
    kind = action["kind"]
    if kind == "release":
        a = ro.run(fleet, release_now=[action["item_id"]])
        b = ro.run(fleet, exclude=[action["item_id"]])
    elif kind == "admit":
        a = ro.run(fleet, extra_pending=action["items"], extra_jobs=action.get("jobs"))
        b = ro.run(fleet)
    elif kind == "defer":
        a = ro.run(fleet, exclude=[action["item_id"]])
        b = ro.run(fleet, release_now=[action["item_id"]])
    elif kind == "state":
        a = ro.run(fleet, extra_pending=action["items"], release_now=[i.item_id for i
                                                                     in action["items"]])
        b = ro.run(fleet)
    elif kind == "dispatch":
        a = ro.run(fleet, release_now=[action["item_id"]])
        b = ro.run(fleet, exclude=[action["item_id"]])
    else:
        raise ValueError("unknown action kind %r; spec 3.5 fixes the reference actions" % kind)
    return dict(delta_j=a.total - b.total, action=a.total, reference=b.total,
                in_sample=bool(a.in_sample and b.in_sample),
                terms=dict(u_hat=a.u_hat - b.u_hat, z=a.z_term - b.z_term,
                           terminal=a.terminal - b.terminal),
                engine_busy_delta_s=a.engine_busy_s - b.engine_busy_s)
