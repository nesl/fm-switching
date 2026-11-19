"""Spec 7 and 8: the main loop.

One event at a time: update estimates and beliefs, score admission, re-classify jobs, re-solve
the tier assignment, then release pending work one unit at a time while DeltaJ_H stays positive.
Nothing is forced: approaching deadlines enter through continuation value and deficits, and
feasibility rules bound waiting (spec 7.2 step 4, 7.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .continuation import (FEASIBLE, INFEASIBLE, PRIORITY, bounded_waiting_breach, classify,
                           expected_remaining_work, restore_costs_s)
from .kvpool import prefix_id_for
from .escalation import (COMPLETE, QUESTION_FIRST, ContextModulatedTrickle, DeviceFilter,
                         EscalationRequest, GhatTables, TriggerFamily, choose_path, ghat)
from .engine import EngineModel
from .flags import Flags
from .profiles import MissingEvidence, Profiles
from .readiness import state_actions, state_value, tier_assignment
from . import closed_form as CF
from .rollout import Rollout, delta_j
from .state import Episode, Fleet, Job, PendingItem
from .utility import t_ready_s


@dataclass
class Decision:
    t: float
    kind: str
    target: str
    delta_j: Optional[float]
    taken: bool
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Coordinator:
    pf: Profiles
    params: Any
    flags: Flags
    engine: EngineModel
    rollout: Rollout = None
    # StudyPOL5 Part 3: see Rollout.residency_belief. None keeps the pre-POL5 path.
    residency_belief: Any = None
    decisions: List[Decision] = field(default_factory=list)
    scoring_calls: int = 0
    # StudyLIVE2-perf Option B (spec 6.5), OFF BY DEFAULT and enabled nowhere. "rollout" is the
    # path every committed run takes; "closed_form" prices SH admission by the closed form;
    # "shadow" computes both, decides with the rollout, and logs the pair.
    sh_cost: str = "rollout"
    sh_shadow: List[Dict[str, Any]] = field(default_factory=list)
    sh_closed_form_calls: int = 0
    tables: GhatTables = None
    sh_trigger: TriggerFamily = None
    ghat_calls: int = 0
    prefix_loss_events: List[Dict[str, Any]] = field(default_factory=list)
    # D99 (4): how often the release-loop evaluation cap actually BOUND, and how many item
    # evaluations it skipped. Both are reported; an unset cap leaves them at zero.
    cap_bound_passes: int = 0
    cap_skipped_items: int = 0

    def __post_init__(self) -> None:
        if self.rollout is None:
            self.rollout = Rollout(self.pf, self.params, self.flags, self.engine,
                                   residency_belief=self.residency_belief)
        elif self.residency_belief is not None and self.rollout.residency_belief is None:
            self.rollout.residency_belief = self.residency_belief
        if self.tables is None:
            self.tables = GhatTables(pf=self.pf)
        if self.sh_trigger is None:
            self.sh_trigger = DeviceFilter(threshold=0.0)
        if self.params.decision_latency_s is None:
            from .m4 import load_decision_latency_s
            m = load_decision_latency_s(self.params.H)
            self.decision_latency = m
            if m["available"]:
                self.params.decision_latency_s = m["seconds"]
        else:
            self.decision_latency = dict(available=True, seconds=self.params.decision_latency_s,
                                         basis="supplied by the caller")
        if self.params.omega.get("SS") is None:
            self._ss_blocked = ("omega_SS is not calibrated and no committed SS accuracy exists; "
                                "an SS opportunity raises rather than being scored")

    # ---------------------------------------------------------------- spec 8, one event
    def on_event(self, fleet: Fleet, event: Dict[str, Any]) -> List[Decision]:
        out: List[Decision] = []
        self._update_jobs(fleet, out)
        if event.get("kind") == "escalation":
            out += self._admission(fleet, event)
        if event.get("kind") in ("telemetry", "timer", "state"):
            out += self._state(fleet)
        out += self._release_loop(fleet)
        self._update_mu(fleet)
        self.decisions += out
        return out

    # ------------------------------------------------- addendum A1, A2: one escalation basis
    def ghat_of(self, fleet: Fleet, req: EscalationRequest) -> Dict[str, Any]:
        """The ONLY thing that decides whether a request is worth the cloud, for every type."""
        dev = fleet.device(req.device)
        delay = req.predicted_delivered_delay_s
        if delay is None:
            delay = self.predicted_delivered_delay_s(fleet, req, path=req.path)
        self.ghat_calls += 1
        return ghat(req, self.tables, link=dev.link, predicted_delay_s=delay, flags=self.flags)

    def predicted_delivered_delay_s(self, fleet: Fleet, req: EscalationRequest,
                                    path: Optional[str] = None, detail: bool = False):
        """Spec 4's delivered delay FOR THE PATH ACTUALLY USED, from committed constants only.

        COMPLETE path:        up(question + the payload the cloud lacks) + compute + down.
        QUESTION-FIRST path:  up(question) + the coordinator's decision latency (M4) + one
                              CONTROL ROUND TRIP for the pull + up(payload) + compute + down.

        The question-first path refuses to quote a delay when the decision latency is UNMEASURED,
        rather than quoting one that silently omits it."""
        dev = fleet.device(req.device)
        path = path or req.path or COMPLETE
        if req.task == "SH":
            compute = self.pf.episodic_ttft_s("32BI", max(req.frames, 1), 25)
        else:
            b = dev.history.get("RICH")
            tier = b.most_likely() if b is not None else "STORED"
            compute = t_ready_s(self.pf, "RICH", tier, b.size_tokens if b else 11_000,
                                b.staleness_s if b else 0.0, 0, dev.link)["total"]
        up_payload = dev.link.up_s(req.payload_bytes) if req.payload_bytes else 0.0
        up_question = dev.link.up_s(req.question_bytes) if req.question_bytes else 0.0
        terms = dict(path=path, up_question_s=up_question, up_payload_s=up_payload,
                     compute_s=compute, down_s=dev.link.down_s())
        if path == QUESTION_FIRST:
            if self.params.decision_latency_s is None:
                raise MissingEvidence(
                    "the question-first path charges the coordinator's decision latency and it "
                    "is UNMEASURED here: run M4 (policy/run_pol2.py) or supply "
                    "Params.decision_latency_s. Quoting a delivered delay without it would "
                    "understate exactly the term this path adds.")
            control_rtt = dev.link.rtt_s
            dec = float(self.params.decision_latency_s)
            terms.update(control_round_trip_s=control_rtt, decision_latency_s=dec,
                         decision_latency_basis=self.decision_latency.get("basis"))
            total = (up_question + dec + control_rtt + up_payload + compute
                     + dev.link.down_s())
        else:
            total = up_question + up_payload + compute + dev.link.down_s()
        terms["total_s"] = float(total)
        return (float(total), terms) if detail else float(total)

    def higher_value_in_flight(self, fleet: Fleet, device_id: str,
                               ghat_value: float) -> Dict[str, Any]:
        """Is this device's uplink already carrying traffic worth more than this query?

        Episode calls are the case the revised A2 names. An item counts as higher value when its
        own recorded Ghat exceeds this query's; an episode call with no recorded Ghat counts as
        higher value only if the query's own Ghat is not positive, which is the conservative
        reading."""
        rival = []
        for it in list(fleet.in_flight) + list(fleet.pending):
            if it.device != device_id:
                continue
            other = it.meta.get("ghat")
            if other is not None and float(other) > float(ghat_value):
                rival.append(dict(item_id=it.item_id, kind=it.kind, ghat=float(other)))
            elif other is None and it.kind == "episode_call" and ghat_value <= 0:
                rival.append(dict(item_id=it.item_id, kind=it.kind, ghat=None))
        return dict(any=bool(rival), items=rival[:8], n=len(rival))

    def _admit_score(self, fleet: Fleet, req, items, jobs) -> Dict[str, Any]:
        """StudyLIVE2-perf Option B, OFF BY DEFAULT. The narrow hook for spec 6.5.

        With `sh_cost = "rollout"`, which is the default and the only mode any committed run
        uses, this is the call it replaced, argument for argument, so the default path is
        untouched. "closed_form" prices an SH admission by `closed_form.sh_admit_delta_j`.
        "shadow" computes BOTH and DECIDES WITH THE ROLLOUT, logging the pair for the divergence
        study, so it cannot change a decision.

        Piece release and recall jobs never reach the closed form: only `task == "SH"` is
        routed, this hook sits only in `escalate` and not in `_admission`, and
        `sh_admit_delta_j` itself refuses anything but one lone episode call.
        """
        mode = getattr(self, "sh_cost", "rollout")
        if mode not in CF.SH_COST_MODES:
            raise ValueError("sh_cost must be one of %s, got %r" % (CF.SH_COST_MODES, mode))
        action = dict(kind="admit", items=items, jobs=jobs)
        if mode == "rollout" or getattr(req, "task", None) != "SH":
            return delta_j(self.rollout, fleet, action)
        if mode == "closed_form":
            self.sh_closed_form_calls += 1
            return CF.sh_admit_delta_j(self.rollout, fleet, items, jobs)
        roll = delta_j(self.rollout, fleet, action)
        cf = CF.sh_admit_delta_j(self.rollout, fleet, items, jobs)
        self.sh_shadow.append(dict(
            t=float(fleet.t), device=str(req.device),
            delta_j_rollout=float(roll["delta_j"]), delta_j_closed_form=float(cf["delta_j"]),
            admit_rollout=bool(roll["delta_j"] > 0),
            admit_closed_form=bool(cf["delta_j"] > 0),
            n_devices=len(fleet.devices),
            backlog_queued_tokens=sum(max(int(p.tokens), 0) for p in fleet.pending),
            backlog_running_requests=len(fleet.in_flight),
            backlog_queued_requests=len(fleet.pending),
            load_factor=float(cf["load_factor"]["lf"]), terms=cf["terms"]))
        return roll

    def escalate(self, fleet: Fleet, req: EscalationRequest) -> List[Decision]:
        """Addendum A2 as revised: a QUERY IS SENT COMPLETE BY DEFAULT, question plus whatever
        payload the cloud lacks, and the cloud runs admission on arrival and DISCARDS it if
        declined. QUESTION-FIRST is an exception path, taken only when an RC query's unsent
        history exceeds the size threshold AND the uplink already carries higher-value traffic;
        then the payload is pulled on admission. SH instants come through the pluggable trigger
        family. Every path scores the same Ghat and then the same DeltaJ_H, and nothing here
        branches on the task type to grant or deny escalation.

        ORDERING, because the two quantities are mutually dependent: Ghat is computed first on
        the COMPLETE path (the default), that value decides whether the exception applies, and if
        the path switches the Ghat is RECOMPUTED on the path actually used, so the timeliness
        term and the deadline check always describe the real path."""
        if req.task != "SH":
            req.path = req.path or COMPLETE
            g = self.ghat_of(fleet, req)
            rival = self.higher_value_in_flight(fleet, req.device, g["ghat"])
            pick = choose_path(req, rival["any"], self.params.question_first_history_bytes)
            if pick["path"] != req.path:
                req.path = pick["path"]
                g = self.ghat_of(fleet, req)
            req.__dict__["_path_choice"] = dict(pick, higher_value_in_flight=rival)
        else:
            g = self.ghat_of(fleet, req)
        if req.task == "SH":
            filt = self.sh_trigger.should_escalate(
                req, self.tables, predicted_delay_s=req.predicted_delivered_delay_s
                or self.predicted_delivered_delay_s(fleet, req), flags=self.flags,
                cloud_score=req.__dict__.get("cloud_score"),
                context_value=req.__dict__.get("context_value"))
            if not filt.get("escalate", False):
                return [Decision(fleet.t, "escalation", req.device, g["ghat"], False,
                                 "the device's local filter (%s) did not escalate this instant"
                                 % self.sh_trigger.name,
                                 detail=dict(basis="ghat", trigger=filt, ghat=g["ghat"]))]
        if req.task != "SH" and req.deadline is not None:
            delay, dterms = self.predicted_delivered_delay_s(fleet, req, path=req.path,
                                                             detail=True)
            if delay > req.deadline:
                return [Decision(
                    fleet.t, "escalation", req.device, g["ghat"], False,
                    "declined and DISCARDED on the %s path: the delivered delay for the path "
                    "actually used is %.4f s against a deadline of %.4f s, so the cloud answer "
                    "cannot serve this query and the device's answer stands"
                    % (req.path, delay, req.deadline),
                    detail=dict(basis="ghat", ghat=g["ghat"], path=req.path,
                                delivered_delay_terms=dterms,
                                path_choice=req.__dict__.get("_path_choice"),
                                deadline=req.deadline))]
        items = self._plan(fleet, dict(kind="escalation", task=req.task, device=req.device,
                                       qtype=req.qtype, payload_bytes=req.payload_bytes,
                                       deadline=req.deadline, capture_at=req.capture_at),
                           ghat=g["ghat"])
        jobs = dict(getattr(self, "_planned_jobs", {}))
        self._planned_jobs = {}
        path_detail = req.__dict__.get("_path_choice")
        if not items:
            return [Decision(fleet.t, "escalation", req.device, g["ghat"], False,
                             "no feasible plan for this request",
                             detail=dict(basis="ghat", ghat=g["ghat"], terms=g["terms"],
                                         path=req.path, path_choice=path_detail))]
        # D125 v1.2: for RC the per-piece short-horizon score is replaced by a JOB PLAN chosen
        # over the job's lifetime. The plan's units carry their planned release time, so the
        # pending set and the calendar see reservations rather than items to re-score each
        # period. SH is untouched and still dispatches on the 100 ms horizon.
        if self.flags.planner_rc and req.task != "SH":
            pl = self._plan_rc(fleet, req, items, jobs, g)
            if pl is not None:
                return pl
        res = self._admit_score(fleet, req, items, jobs)
        self.scoring_calls += 1
        take = res["delta_j"] > 0
        if take:
            fleet.jobs.update(jobs)
            if req.path == QUESTION_FIRST:
                self.pull_payload(fleet, req, items)
            else:
                req.payload_delivered = True
                for it in items:
                    it.meta["payload_arrived_with_request"] = True
            fleet.pending += items
            if req.task == "SH":
                dev = fleet.device(req.device)
                ep = Episode(device=dev.device_id, task="SH", cadence_s=self.params.T_k["SH"],
                             opened_at=fleet.t, max_calls=self.params.E_k["SH"])
                ep.calls_issued.append(fleet.t)
                dev.episodes.append(ep)
        if not take:
            self._discard(fleet, items, jobs)
        return [Decision(fleet.t, "escalation", req.device, res["delta_j"], take,
                         ("admitted on the %s path: Ghat %.4f and DeltaJ_H %.4f"
                          % (req.path or "SH", g["ghat"], res["delta_j"]))
                         if take else
                         ("declined and DISCARDED on the %s path: Ghat %.4f but DeltaJ_H %.4f "
                          "against the decline reference; the device's answer stands"
                          % (req.path or "SH", g["ghat"], res["delta_j"])),
                         detail=dict(basis="ghat", ghat=g["ghat"], terms=g["terms"],
                                     posterior=g["posterior"], coverage=g["coverage"],
                                     delta_j_terms=res["terms"], n_items=len(items),
                                     path=req.path, path_choice=path_detail))]

    def _discard(self, fleet: Fleet, items: Sequence[PendingItem],
                 jobs: Dict[str, Job]) -> None:
        """A declined query leaves NOTHING behind: no pending item, no job, no in-flight work.

        The plan is built speculatively to be scored, so this is what makes 'the cloud discards
        declined queries and the device's answer stands' true of the state and not only of the
        prose."""
        ids = {it.item_id for it in items}
        fleet.pending = [p for p in fleet.pending if p.item_id not in ids]
        fleet.in_flight = [p for p in fleet.in_flight if p.item_id not in ids]
        for jid in jobs:
            fleet.jobs.pop(jid, None)

    def pull_payload(self, fleet: Fleet, req: EscalationRequest,
                     items: Sequence[PendingItem]) -> None:
        """Addendum A2 as revised: this is the QUESTION-FIRST path only. The cloud pulls the
        missing frames after admitting the question; the control round trip and the decision
        latency it costs are already charged in the delivered delay. On the complete path the
        payload arrived with the request and this is never called."""
        req.payload_delivered = True
        for it in items:
            if it.kind == "episode_call":
                it.frames = max(it.frames, 1)
                it.payload_bytes = req.payload_bytes
            else:
                it.meta["payload_pulled_at"] = fleet.t

    # ---------------------------------------------------------------- 7.1 admission
    def _admission(self, fleet: Fleet, event: Dict[str, Any]) -> List[Decision]:
        items = self._plan(fleet, event)
        if not items:
            return [Decision(fleet.t, "admission", event.get("device", "?"), None, False,
                             "no feasible plan")]
        jobs = dict(getattr(self, "_planned_jobs", {}))
        self._planned_jobs = {}
        res = delta_j(self.rollout, fleet, dict(kind="admit", items=items, jobs=jobs))
        self.scoring_calls += 1
        take = res["delta_j"] > 0
        if not take:
            self._discard(fleet, items, jobs)
        if take:
            fleet.jobs.update(jobs)
            fleet.pending += items
            if event.get("task") == "SH":
                dev = fleet.device(event["device"])
                ep = Episode(device=dev.device_id, task="SH",
                             cadence_s=self.params.T_k["SH"], opened_at=fleet.t,
                             max_calls=self.params.E_k["SH"])
                ep.calls_issued.append(fleet.t)
                if self.flags.phase_assignment:
                    ep.phase = self._phase(fleet, ep)
                dev.episodes.append(ep)
        return [Decision(fleet.t, "admission", event.get("device", "?"), res["delta_j"], take,
                         "admitted" if take else "declined against the decline reference",
                         detail=dict(terms=res["terms"], in_sample=res["in_sample"],
                                     n_items=len(items)))]

    def _plan(self, fleet: Fleet, event: Dict[str, Any],
              ghat: Optional[float] = None) -> List[PendingItem]:
        """Spec 7.1: the escalation's BEST plan. For RC that is the best option over
        {device, SUMMARY if enabled, RICH} given believed tiers, staleness and feasibility."""
        did = event["device"]
        dev = fleet.device(did)
        if event.get("task") == "SH":
            # D98 / D100: when the caller supplies the instant's own capture time, the call
            # carries c_i as its `due_at` and c_i + L_SH as its deadline, so spec 5.1's
            # per-instant rule credits the instant this call actually serves and pi_0 orders it
            # by its own deadline. Omitted, both fall back to the pre-D98 behaviour
            # (`due_at = fleet.t`, no deadline), so no existing caller moves.
            cap = event.get("capture_at")
            due = float(cap) if cap is not None else fleet.t
            dl = event.get("deadline") if cap is not None else None
            return [PendingItem(item_id="%s:call:%.3f" % (did, due), kind="episode_call",
                                device=did, due_at=due,
                                deadline=(float(dl) if dl is not None else None), frames=1,
                                payload_bytes=event.get("payload_bytes", 0),
                                meta=dict(ghat=ghat) if ghat is not None else {})]
        if event.get("task") == "SS":
            raise MissingEvidence(getattr(self, "_ss_blocked", "SS is not supported"))
        qtype = event["qtype"]
        reps = ["RICH"] + (["SUMMARY"] if self.flags.summaries else [])
        best: Optional[Tuple[float, List[PendingItem], str]] = None
        for rep in reps:
            if rep not in dev.history:
                continue
            b = dev.history[rep]
            size = self.params.piece_sizes_tokens[-1]
            n_pieces = max(1, -(-b.size_tokens // size))
            job = Job(job_id="%s:%s:%.3f" % (did, rep, fleet.t), device=did, qtype=qtype,
                      rep=rep,
                      deadline=(event.get("deadline")
                                if event.get("deadline") is not None
                                else fleet.t + self.params.L_k["RC"]),
                      admitted_at=fleet.t,
                      pieces_total=n_pieces, tokens_per_piece=size)
            sizing = self.choose_piece_size(fleet, job)
            size = int(sizing["chosen"]["size_tokens"])
            n_pieces = int(sizing["chosen"]["n_pieces"])
            job.tokens_per_piece, job.pieces_total = size, n_pieces
            # D122 v1.1 F3: the competing engine-seconds pi_0 would serve first, from the
            # rollout's own state. 0.0 with the flag off, which is the previous behaviour.
            cls = classify(job, fleet.t, self.engine,
                           competing_s=self.rollout.competing_gpu_s(fleet, job, fleet.t),
                           threshold=self.params.feasibility_threshold,
                           resolution_s=self.params.continuation_resolution_s,
                           rel_sigma=self.rollout.rel_sigma_for(job))
            if cls == INFEASIBLE:
                continue
            try:
                acc = self.pf.rc_accuracy(qtype, rep, "cloud")
            except MissingEvidence:
                continue
            items = [PendingItem(item_id="%s:p%d" % (job.job_id, i), kind="rc_piece", device=did,
                                 due_at=fleet.t, deadline=job.deadline,
                                 tokens=job.tokens_per_piece, job_id=job.job_id,
                                 readiness=_readiness(b.most_likely()),
                                 meta=dict(ghat=ghat) if ghat is not None else {})
                     for i in range(n_pieces)]
            if best is None or acc > best[0]:
                best = (acc, items, job.job_id)
                self._planned_jobs = {job.job_id: job}
        if best is None:
            self._planned_jobs = {}
            return []
        return list(best[1])

    # ---------------------------------------------------------------- D125 v1.2
    def _plan_rc(self, fleet: Fleet, req, items, jobs, g) -> Optional[List[Decision]]:
        """Choose and reserve a job plan for one recall question (design note 2.2 to 2.4).

        Returns the decisions, or None to fall back to the v1.1 path when the question carries no
        job for the planner to plan (then nothing has been changed).
        """
        from . import planner_rc as PL
        if not jobs:
            return None
        jid, job = sorted(jobs.items())[0]
        dev = fleet.device(req.device)
        b = dev.history.get(job.rep)
        if b is None:
            return None
        built = int(getattr(self, "_built_tokens_by_job", {}).get(jid, 0))
        kappa = getattr(self.params, "kappa", None)
        kappa = None if kappa is None else float(kappa)
        plans = PL.enumerate_plans(
            engine=self.engine, device=req.device, qtype=job.qtype, rep=job.rep,
            size_tokens=int(b.size_tokens), readiness=_readiness(b.most_likely()),
            deadline_abs=float(job.deadline), t=float(fleet.t),
            piece_sizes=tuple(self.params.piece_sizes_tokens),
            allow_latest=bool(self.flags.plan_latest), kappa=kappa, built_tokens=built)
        if not plans:
            return None
        out = PL.choose(self.rollout, fleet, plans, float(job.deadline),
                        decision_period_s=float(getattr(self.params, "decision_period_s", 0.1)))
        self.scoring_calls += len(out["plans"]) + 1
        chosen = out["chosen"]
        self.last_plan = dict(
            job_id=jid, admitted=bool(out["admitted"]), horizon_s=out["horizon_s"],
            chosen=(chosen.label() if chosen is not None else None),
            delta_j=(chosen.delta_j if chosen is not None else None),
            considered={p.label(): (None if p.delta_j is None else round(p.delta_j, 9))
                        for p in out["plans"]},
            kappa=("derived" if kappa is None else kappa), kappa_provisional=False)
        if chosen is None:
            self._discard(fleet, items, jobs)
            return [Decision(fleet.t, "plan", req.device, None, False,
                             out["note"], detail=dict(plan=self.last_plan))]
        # Reserve: the plan's own units replace the per-piece items, carrying planned times.
        self._discard(fleet, items, jobs)
        fleet.jobs[jid] = chosen.job
        fleet.pending += list(chosen.units)
        req.payload_delivered = True
        for it in chosen.units:
            it.meta["payload_arrived_with_request"] = True
        return [Decision(fleet.t, "plan", req.device, chosen.delta_j, True,
                         out["note"], detail=dict(plan=self.last_plan))]

    def _phase(self, fleet: Fleet, ep: Episode) -> float:
        """Spec 7.8: a phase that clusters this episode's follow-ups with others of the same
        cadence. Conditional; the capture-time shift it costs is charged in the rollout because
        the call's due_at moves."""
        peers = [e for d in fleet.devices.values() for e in d.episodes
                 if abs(e.cadence_s - ep.cadence_s) < 1e-9 and e.phase is not None]
        if not peers:
            return 0.0
        return float(sorted(p.phase for p in peers)[0])

    # ---------------------------------------------------------------- 7.3
    def _update_jobs(self, fleet: Fleet, out: List[Decision]) -> None:
        for jid, job in fleet.jobs.items():
            if job.answered:
                continue
            # D122 v1.1 F3. `classify` compares `competing_s` against
            # `competing_s_with_priority`, which stays 0.0 as the existing convention for "only
            # work whose own loss exceeds the job's value stays ahead". With a real competing_s
            # PRIORITY becomes reachable, which is what makes A3 live.
            comp = self.rollout.competing_gpu_s(fleet, job, fleet.t)
            job.feasibility = classify(job, fleet.t, self.engine, competing_s=comp,
                                       threshold=self.params.feasibility_threshold,
                                       resolution_s=self.params.continuation_resolution_s,
                                       rel_sigma=self.rollout.rel_sigma_for(job))
            if job.feasibility == FEASIBLE and bounded_waiting_breach(
                    job, fleet.t, self.engine, comp, self.params.feasibility_threshold,
                    self.params.H, self.params.continuation_resolution_s):
                job.feasibility = PRIORITY
                out.append(Decision(fleet.t, "feasibility", jid, None, True,
                                    "promoted to the priority class by the bounded-waiting check "
                                    "(spec 7.3)"))
            if job.feasibility == INFEASIBLE:
                keep = [p for p in fleet.pending if p.job_id != jid]
                dropped = len(fleet.pending) - len(keep)
                fleet.pending = keep
                if dropped:
                    out.append(Decision(fleet.t, "feasibility", jid, None, True,
                                        "INFEASIBLE: stopped spending GPU time on the answer "
                                        "(spec 7.3); %d pieces dropped, the device's answer is "
                                        "used" % dropped))

    # ---------------------------------------------------------------- 6.2, 6.3
    def _state(self, fleet: Fleet) -> List[Decision]:
        out: List[Decision] = []
        cands = []
        for did, dev in fleet.devices.items():
            if dev.qtype is None or dev.demand is None:
                continue
            for rep, b in dev.history.items():
                r = state_value(self.pf, dev, rep, dev.demand, self.params.H_s, dev.qtype,
                                dev.link, self.params.L_k["RC"], self.pf.omega("RC"),
                                in_episode=bool(dev.episodes))
                cands.append(dict(r, device=did, tokens=b.size_tokens))
        if not cands:
            return out
        try:
            host_pool = self.rollout._build_host(fleet)
            alloc = tier_assignment(cands, self.params.gpu_kv_capacity_tokens,
                                    self.params.host_kv_capacity_tokens,
                                    calibration=getattr(self.params, "tier_calibration", None),
                                    host_occupied_tokens=(host_pool.occupancy()
                                                          if host_pool is not None else 0))
        except ValueError as e:
            return [Decision(fleet.t, "tier_assignment", "-", None, False, str(e))]
        # D99 (4): the STATE pass is a full-DeltaJ path too -- one evaluation per state action
        # the tier assignment proposes, which is O(devices) per decision period -- so the cap
        # has to cover it. With the cap on the release loop and SH admission only, K = 1 at 128
        # devices still missed the p99 target, and this pass is why. The candidates are taken in
        # the tier assignment's own order (highest nu_tier first), so the cap keeps the
        # promotions worth the most, and the rest are reconsidered next period.
        budget = getattr(self.params, "release_eval_cap_k", None)
        budget = int(budget) if budget else None
        for c in alloc["gpu"]:
            if budget is not None and budget <= 0:
                self.cap_bound_passes += 1
                self.cap_skipped_items += 1
                continue
            dev = fleet.device(c["device"])
            acts = state_actions(dev, c["rep"], self.flags, target="GPU")
            for a in acts:
                if budget is not None:
                    if budget <= 0:
                        self.cap_skipped_items += 1
                        continue
                    budget -= 1
                item = PendingItem(item_id="%s:%s:%s:%.3f" % (a.device, a.rep, a.kind, fleet.t),
                                   kind="state_action", device=a.device, due_at=fleet.t,
                                   tokens=a.tokens,
                                   readiness=_readiness(dev.history[a.rep].most_likely()),
                                   meta=dict(action=a.kind, target=a.target_tier))
                res = delta_j(self.rollout, fleet, dict(kind="state", items=[item]))
                self.scoring_calls += 1
                take = res["delta_j"] > 0
                if take:
                    fleet.pending.append(item)
                out.append(Decision(fleet.t, "state_action", item.item_id, res["delta_j"], take,
                                    "scored against no change (spec 6.2)",
                                    detail=dict(nu_tier=alloc["nu_tier"], action=a.kind)))
        return out

    # ---------------------------------------------------------------- A6.5 piece sizing (7.4)
    def choose_piece_size(self, fleet: Fleet, job: Job,
                          candidates: Optional[Sequence[int]] = None) -> Dict[str, Any]:
        """Spec 7.4 with addendum A6.5: candidate sizes are scored with the DEFERRAL RISK
        included, so exposure between pieces is part of the size choice.

        Larger pieces mean fewer gaps, and a gap is when the prefix is unreferenced and can be
        freed. The score is the expected total engine work: the pieces themselves plus the
        expected restore work over the gaps the size implies."""
        cands = list(candidates or self.params.piece_sizes_tokens)
        total_tokens = max(job.pieces_total * job.tokens_per_piece, 1)
        if self.params.allow_whole_job_piece:
            cands = cands + [total_tokens]
        rows = []
        store = self.rollout._build_store(fleet)
        pool = store.gpu if store is not None else None
        for size in sorted(set(int(c) for c in cands if c > 0)):
            n_pieces = max(1, -(-total_tokens // size))
            gaps = max(n_pieces - 1, 0)
            probe = Job(job_id=job.job_id, device=job.device, qtype=job.qtype, rep=job.rep,
                        deadline=job.deadline, admitted_at=job.admitted_at,
                        pieces_total=n_pieces, pieces_done=0, tokens_per_piece=size)
            if pool is None:
                p_loss = 0.0
            else:
                pred = pool.predict_loss(prefix_id_for(job.job_id), size, fleet.t)
                p_loss = pred["p_loss"]
            src = (self.residency_belief if self.residency_belief is not None else self.params)
            ph = src.p_host_for(store.host if store is not None else None,
                                        int(round(p_loss * size)),
                                        prefix_id=prefix_id_for(job.job_id), t=fleet.t)
            rw = expected_remaining_work(probe, self.engine, self.pf, p_loss=p_loss,
                                         p_host=float(ph["p_host"]), prefix_tokens=size)
            exposure = gaps * rw.extra_s
            rows.append(dict(size_tokens=size, n_pieces=n_pieces, gaps=gaps,
                             work_s=rw.w_left_s, p_loss=p_loss, p_host=ph["p_host"],
                             p_host_basis=ph["basis"], expected_restore_s=exposure,
                             expected_total_s=rw.w_left_s + exposure))
        rows.sort(key=lambda r: (r["expected_total_s"], r["size_tokens"]))
        return dict(chosen=rows[0], candidates=rows,
                    rule="minimize expected total engine work including the deferral exposure "
                         "each size implies (A6.5)")

    # ---------------------------------------------------------------- A6.4 verify on resume
    def verify_prefix_before_release(self, fleet: Fleet, item: PendingItem,
                                     telemetry=None) -> Dict[str, Any]:
        """A6.4: before releasing a job's next piece, check the prefix's believed residency; on
        observed or likely loss, RE-PLAN with the true remaining work and record the event."""
        if not item.job_id:
            return dict(checked=False, reason="not a job piece")
        job = fleet.jobs.get(item.job_id)
        if job is None:
            return dict(checked=False, reason="no such job")
        store = self.rollout._build_store(fleet)
        pool = store.gpu if store is not None else None
        pid = prefix_id_for(job.job_id)
        built = job.pieces_done * job.tokens_per_piece
        observed_loss = False
        if telemetry is not None:
            observed_loss = bool(getattr(telemetry, "evictions", 0) > 0
                                 and getattr(telemetry, "local_hits", 0) == 0
                                 and getattr(telemetry, "external_hits", 0) == 0)
        p_loss = 0.0
        competing = sum(max(q.tokens, 0) for q in fleet.pending
                        if q.item_id != item.item_id and q.job_id != job.job_id)
        demand = max(item.tokens, 0) + competing
        if pool is not None and built > 0:
            p_loss = pool.predict_loss(pid, demand, fleet.t)["p_loss"]
        likely = p_loss >= float(self.params.prefix_loss_replan_threshold)
        out = dict(checked=True, job_id=job.job_id, built_prefix_tokens=built,
                   p_loss=p_loss, observed_loss=observed_loss, likely_loss=likely,
                   demand_tokens=demand, competing_tokens=competing, replanned=False)
        if built > 0 and (observed_loss or likely):
            w_reload, w_rebuild = restore_costs_s(built, self.pf)
            src = (self.residency_belief if self.residency_belief is not None else self.params)
            ph = src.p_host_for(store.host if store is not None else None,
                                        int(round(max(p_loss, 1.0 if observed_loss else 0.0)
                                                  * built)),
                                        prefix_id=pid, t=fleet.t)
            p_host = float(ph["p_host"])
            restore_s = (w_reload if (observed_loss and p_host >= 0.5)
                         else (p_host * w_reload + (1.0 - p_host) * w_rebuild))
            restore = PendingItem(
                item_id="%s:restore:%.3f" % (job.job_id, fleet.t), kind="rc_piece",
                device=job.device, due_at=fleet.t, deadline=job.deadline, tokens=built,
                job_id=job.job_id, readiness=("HOST-WARM" if p_host >= 0.5 else "COLD"),
                meta=dict(a6_restore=True, restore_work_s=restore_s,
                          reason=("observed loss" if observed_loss else
                                  "believed likely loss, P_loss %.3f" % p_loss)))
            fleet.pending.insert(0, restore)
            job.pieces_total += 1
            job.feasibility = classify(
                job, fleet.t, self.engine, competing_s=0.0,
                threshold=self.params.feasibility_threshold,
                resolution_s=self.params.continuation_resolution_s,
                extra_work_s=restore_s)
            ev = dict(t=fleet.t, job_id=job.job_id, built_prefix_tokens=built, p_loss=p_loss,
                      p_host=ph, observed_loss=observed_loss, restore_work_s=restore_s,
                      restore_item=restore.item_id, new_pieces_total=job.pieces_total,
                      feasibility_after=job.feasibility,
                      requested_continuation_vs_observed_loss=(
                          "requested to continue from the built prefix; telemetry OBSERVED the "
                          "loss" if observed_loss else
                          "requested to continue; the pool predicts it will be gone"))
            self.prefix_loss_events.append(ev)
            out.update(replanned=True, event=ev)
        return out

    # ---------------------------------------------------------------- 7.2 release loop
    def _release_loop(self, fleet: Fleet, max_releases: int = 32) -> List[Decision]:
        out: List[Decision] = []
        # D99 (4): with `release_eval_cap_k` set, AT MOST K pending items get a full DeltaJ
        # evaluation in this whole call, i.e. in this decision period, SHARED ACROSS THE PASSES
        # of the loop; the rest wait for the next period, still in pi_0 order. Capping per PASS
        # instead would leave the per-period cost unbounded, because the loop makes up to
        # `max_releases` passes. None (the default) is UNLIMITED, which is the behaviour every
        # committed result was produced under.
        budget = getattr(self.params, "release_eval_cap_k", None)
        budget = int(budget) if budget else None
        for _ in range(max_releases):
            if budget is not None and budget <= 0:
                break
            best = None
            due = [p for p in fleet.pending if p.due_at <= fleet.t + 1e-12]
            if budget is not None:
                if len(due) > budget:
                    self.cap_bound_passes += 1
                    self.cap_skipped_items += len(due) - budget
                due = self.rollout._edf(due)[:budget]
                budget -= len(due)
            for p in due:
                res = delta_j(self.rollout, fleet,
                              dict(kind="dispatch" if p.kind == "episode_call" else "release",
                                   item_id=p.item_id))
                self.scoring_calls += 1
                if best is None or res["delta_j"] > best[1]["delta_j"]:
                    best = (p, res)
            if best is not None and best[0].job_id:
                chk = self.verify_prefix_before_release(fleet, best[0])
                if chk.get("replanned"):
                    out.append(Decision(fleet.t, "prefix_loss", best[0].item_id, None, True,
                                        "A6.4: before releasing this piece the prefix was found "
                                        "lost or likely lost, so restore work was inserted and "
                                        "the job re-planned; the release is re-scored",
                                        detail=chk))
                    continue
            if best is None or best[1]["delta_j"] <= 0:
                if best is not None:
                    out.append(Decision(fleet.t, "release", best[0].item_id,
                                        best[1]["delta_j"], False,
                                        "held: no pending item has positive DeltaJ_H (spec 7.2 "
                                        "step 3); merging is %s"
                                        % ("on" if self.flags.merging else "off")))
                break
            p, res = best
            fleet.pending = [q for q in fleet.pending if q.item_id != p.item_id]
            fleet.in_flight.append(p)
            out.append(Decision(fleet.t, "release", p.item_id, res["delta_j"], True,
                                "released, one unit at a time (spec 7.2 step 3)",
                                detail=dict(terms=res["terms"], in_sample=res["in_sample"])))
        return out

    # ---------------------------------------------------------------- 7.9 hold and merge
    def hold_or_merge(self, fleet: Fleet, due: PendingItem,
                      next_due_at: float) -> Dict[str, Any]:
        res = delta_j(self.rollout, fleet, dict(kind="dispatch", item_id=due.item_id))
        self.scoring_calls += 1
        if res["delta_j"] > 0:
            return dict(action="dispatch", delta_j=res["delta_j"])
        if not self.flags.merging:
            return dict(action="hold_then_device_outcome", delta_j=res["delta_j"],
                        note="merging is OFF (spec 7.9 enabling condition not met), so the held "
                             "call's own opportunity is a device-only outcome")
        return dict(action="merge_into_next", delta_j=res["delta_j"], merged_at=next_due_at,
                    frames=min(self.params.W_k["SH"], due.frames + 1),
                    note="the earlier opportunity is a device-only outcome and the merged answer "
                         "serves the later one, with utility from M3 (spec 7.9)")

    # ---------------------------------------------------------------- 7.5 outages
    def on_outage(self, fleet: Fleet, device_id: str, p_reconnect: float) -> List[Decision]:
        dev = fleet.device(device_id)
        dev.link.reachable = False
        dev.link.p_reachable_within_hs = float(p_reconnect)
        paused = [p for p in fleet.pending if p.device == device_id]
        fleet.pending = [p for p in fleet.pending if p.device != device_id]
        dev.__dict__.setdefault("_paused", []).extend(paused)
        return [Decision(fleet.t, "outage", device_id, None, True,
                         "device unreachable: %d pending items paused, state value discounted by "
                         "P(reachable within H_s) = %.3f (spec 7.5)" % (len(paused), p_reconnect))]

    def on_reconnect(self, fleet: Fleet, device_id: str) -> List[Decision]:
        dev = fleet.device(device_id)
        dev.link.reachable = True
        dev.link.p_reachable_within_hs = 1.0
        back = dev.__dict__.pop("_paused", [])
        fleet.pending += back
        return [Decision(fleet.t, "reconnect", device_id, None, True,
                         "backlog of %d items returned to the coordinator (spec 7.5)"
                         % len(back))]

    # ---------------------------------------------------------------- 3.3, 7.6
    def update_deficit(self, fleet: Fleet, device_id: str, task: str,
                       success_hat: float) -> float:
        return fleet.device(device_id).bump_z(task, self.params.p_k[task], success_hat)

    # ---------------------------------------------------------------- mu and the price
    def _update_mu(self, fleet: Fleet) -> None:
        """Spec 8 says 'update mu' and gives no rule; ambiguity A3 records the choice: an EWMA of
        the realized marginal utility per GPU-second of the last released item, floored at 0."""
        est = str(getattr(self.params, "mu_estimator", "none"))
        if est == "none":
            self.mu_note = (
                "mu is held at its PLACEHOLDER 0 because Params.mu_estimator is 'none'. Spec 8 "
                "says only 'update mu' and spec 9 does not list mu, so the SPEC DOES NOT "
                "DETERMINE AN ESTIMATOR. The options and their consequences are written out in "
                "reports/study_pol3_update.md; selecting one is an explicit choice, not a "
                "default. With mu at 0 the terminal backlog channel of spec 5.3 is SILENT, so "
                "A6's expected restore work reaches a decision only through the feasibility "
                "class and the memory decision (ambiguity A26)")
            return
        if est == "scarcity":
            # D129: a SCARCITY price. The EWMA priced BEST USE, not scarcity: session 2's F-A9
            # measured mu p50 rising 1.445, 2.178, 9.835 at 4, 8 and 16 devices while in-flight
            # occupancy FELL 1.090, 1.054, 0.332, so refusing work raised the price of work and
            # the loop reinforced itself. This prices the engine at what it is actually short of:
            # near zero with spare capacity, rising with real predicted backlog.
            #
            #     mu = mu_scale * min(1, busy_ahead / H)
            #
            # `busy_ahead` is the predicted remaining service of what is already in flight, which
            # is the same engine model the rollout uses, so no new estimator enters.
            ahead = 0.0
            for p_ in fleet.in_flight:
                try:
                    pr_ = self.engine.predict(self.rollout._request(p_),
                                              concurrent=max(len(fleet.in_flight) - 1, 0))
                    ahead += float(pr_.service_s)
                except Exception:
                    continue
            h = max(float(self.params.H), 1e-9)
            scale = float(getattr(self.params, "mu_scale", 1.0) or 1.0)
            self.params.mu = scale * min(1.0, ahead / h)
            return
        if est != "ewma_marginal_utility":
            raise ValueError("unknown mu estimator %r; 'none' (default, mu stays at the "
                             "PLACEHOLDER 0) and 'ewma_marginal_utility' (ambiguity A3) are the "
                             "only ones implemented" % est)
        if not fleet.in_flight:
            return
        a = self.params.mu_ewma_alpha
        last = fleet.in_flight[-1]
        pr = self.engine.predict(self.rollout._request(last), concurrent=len(fleet.in_flight) - 1)
        if pr.gpu_s <= 0:
            return
        realized = max(getattr(self, "_last_delta_j", 0.0), 0.0) / pr.gpu_s
        self.params.mu = (1 - a) * float(self.params.mu) + a * realized

    def upgrade_device_answer(self, cloud: Dict[str, Any], device: Dict[str, Any],
                             margin: float = 0.0) -> Dict[str, Any]:
        """D57: the cloud upgrades the device's answer ONLY on the common calibrated probability
        scale. Both raw scores are mapped by their tier's DEV-fitted monotone map first, and the
        call RAISES when no calibration exists between the two tiers, rather than comparing two
        scales that StudyCTRL1b measured to be different."""
        from .calibration import upgrade_decision
        return upgrade_decision(getattr(self.params, "tier_calibration", None), cloud, device,
                                margin=margin)

    def price(self, fleet: Fleet, typical_first_call_gpu_s: float) -> float:
        """Spec 7.7's pi(t) = mu x (GPU-seconds of a typical first call). Broadcast only when the
        conditional price flag is on."""
        if not self.flags.escalation_price:
            return 0.0
        return float(self.params.mu) * float(typical_first_call_gpu_s)


def _readiness(tier: str) -> str:
    return {"GPU": "GPU-WARM", "HOST": "HOST-WARM", "STORED": "COLD"}[tier]
