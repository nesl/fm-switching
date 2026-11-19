#!/usr/bin/env python3
"""Arm 1: the policy CORE (D66), driving the committed policy library. CPU only.

WHAT IS ON (D66, spec v4 section 8.0 core rows): admission (8.1), the release coordinator (8.2),
recall-job continuation and feasibility (8.3), rollout-chosen piece size (8.4), residency
bookkeeping (7.6 / RES1), per-device deficit counters (8.6), per-tier calibration (3.2) and
outage handling (8.5).

WHAT IS OFF: every conditional mechanism, through `policy/flags.py`, whose every flag already
defaults OFF (D38): touch, merging, escalation price, phase assignment, summaries, predictive
upload, conditional recall rate, sampled scenarios, closed-form fallback.

MONITORING IS CAPACITY-BASED (D62): every SH decision instant is a candidate and the scheduler
serves what it has capacity for. No device-side trigger is part of the contribution, so the
trigger family is the library's `DeviceFilter(threshold=0.0)` default, which escalates every
instant and leaves the choice to admission and the release loop.

NOTHING IN `experiments/orchestration/policy/` IS MODIFIED BY THIS FILE. The library is driven
through its public entry points (`Coordinator.escalate`, `Coordinator.on_event`,
`Rollout.run`, `delta_j`).
"""
import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/baselines/reconstructed"),
           str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import (Action, Observation, Policy, RecallAction,      # noqa: E402
                       StreamAction, materialize)
from arms import Live2ArmMixin                                          # noqa: E402

from policy import calibration as CAL                                   # noqa: E402
from policy.coordinator import Coordinator                              # noqa: E402
from policy.demand import Demand                                        # noqa: E402
from policy import closed_form as CF                                    # noqa: E402
from policy.eng1_engine import ENGINE_MODELS
from policy.eng1_engine_fast import Eng1Engine   # StudyLIVE2-perf: the live path, see its docstring                # noqa: E402
from policy.escalation import EscalationRequest                         # noqa: E402
from policy.flags import Flags                                          # noqa: E402
from policy.params import Params                                        # noqa: E402
from policy.profiles import load_profiles                               # noqa: E402
from policy.kvpool import prefix_id_for                                 # noqa: E402
from policy.residency_belief import ResidencyBelief                     # noqa: E402
from cstate import D2_TOK_PER_IMG                                       # noqa: E402
from policy.rollout import Rollout, clone_for_rollout            # noqa: E402
from policy.state import Device, Fleet, HistoryBelief, Link             # noqa: E402

# D73: round-1 placeholder settings, every one reported with "not tuned".
PLACEHOLDERS = {
    "H": dict(value=None, note="swept at 0.5 and 1.0 s (D73); set from --h", tuned=False),
    "feasibility_threshold": dict(value=0.5, note="D73; report jobs given up on", tuned=False),
    "belief_conservatism": dict(value=0.5, note="params.py default (D73); report how often the "
                                                "residency belief was wrong", tuned=False),
    "H_s": dict(value=60.0, note="state horizon, D73", tuned=False),
    "monitor_answer_window_s": dict(value=1.0, note="tied to the 1.0 s dashcam deadline "
                                                    "(D71, D73)", tuned=False),
    "prefix_loss_replan_threshold": dict(value=0.5, note="params.py default (D73); report "
                                                         "firings", tuned=False),
    "mu_ewma_alpha": dict(value=0.1, note="params.py default; smoothing is our choice",
                          tuned=False),
}

MU_MODES = ("none", "ewma", "fixed", "scarcity")
QTYPE = "counting_objects_events"     # the one committed RC question type (P9)


@dataclass
class PolicyCoreArm(Live2ArmMixin, Policy):
    """The core policy as one `interface.Policy`, so it shares the arms' single action space."""

    cost_model: str = "pol4"
    h_s: Optional[float] = 1.0
    mu_mode: str = "none"
    mu_fixed: Optional[float] = None
    predict_log_max: int = 4
    # D99 (2): "fast" is the optimized path; "reference" is the unoptimized post-D98 policy,
    # selectable so the equivalence test has something to compare against. The two must produce
    # IDENTICAL decision logs, which is what the test asserts.
    impl: str = "fast"
    # StudyLIVE2-perf Option B (spec 6.5), BUILT OFF. "rollout" is the default and the only
    # value any committed run uses; the other two exist so the fallback can be measured without
    # being enabled. A config switch and nothing else: this arm's behaviour at the default is
    # byte for byte what it was.
    sh_cost: str = "rollout"
    # D99 (4): the cap on how many pending items get a full DeltaJ evaluation per decision
    # period, applied to BOTH full-DeltaJ paths (the release loop and SH admission); the rest
    # wait in pi_0 order for the next period. None is UNLIMITED. It is set on the Params
    # INSTANCE rather than declared as a field, because `policy/params.py` is one of the
    # StudyPOL4 FROZEN FILES (freeze_t0b.FROZEN_FILES, md5-checked by
    # policy/tests/test_residency_belief.py) and may not be edited; the library reads it with
    # `getattr(self.params, "release_eval_cap_k", None)`, so an unset cap is the old behaviour.
    cap_k: Optional[int] = None
    # D122 v1.1 fix B1, DEFAULT OFF. Spec 3.3's deficit counters are READ in five production
    # sites and were WRITTEN in none: `Device.bump_z` is reached only through
    # `Coordinator.update_deficit`, which has no production caller, so `z_of(task)` returned 0.0
    # for every device and task on every path (verification V1). This switch introduces the
    # update arm-side, from the REALISED on-time outcome of each opportunity, which is the only
    # thing observable online without ground truth. `w = 1` for every task here; the scaling
    # (B2) is pre-registered in the report and NOT implemented.
    deficit_update: bool = False
    # D122 v1.1 fix A3, DEFAULT OFF. Travels on `Flags` because the rollout reads it there.
    # Measured to be a NO-OP in today's build, since the rollout passes competing_s = 0.0 and
    # `continuation_schedule` uses `priority` only as `t + (0.0 if priority else competing_s)`.
    honour_job_priority: bool = False
    # D122 v1.1, both DEFAULT OFF, both travelling on `Flags` because the rollout reads them.
    rc_tail: bool = False
    write_staleness: bool = False
    realistic_competing: bool = False
    rc_tail_cursor: bool = False
    rc_tail_zrows: bool = False
    prob_p_finish: bool = False
    # D125 v1.2: the two-timescale planner. kappa is 1.0 and PROVISIONAL (no committed FIT/DEV
    # q90 ratio of measured to predicted job completion exists), and it is recorded in the header.
    planner_rc: bool = False
    plan_latest: bool = False
    replan: bool = False
    kappa: Optional[float] = None   # None derives it from committed FIT-only residuals (D129)
    mu_scale: float = 1.0           # D129: the scarcity price's scale

    name: str = "policy-core"
    case: str = "own"
    experiments: Tuple[str, ...] = ("C-mixed",)
    decides: Tuple[str, ...] = ("episodic_mode", "recall_decision", "representation",
                                "session_action", "order")
    defaults_used: Tuple[str, ...] = ("cadence_s", "frame_count", "engine_config")
    uses_h: bool = True
    needs_capacities: bool = True
    _ready: bool = False
    last_predictions: Dict[str, Any] = field(default_factory=dict)
    mu_samples: List[float] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    live2_source = "policy spec v4 core (D66) via experiments/orchestration/policy/"

    def __post_init__(self) -> None:
        if self.cost_model not in ENGINE_MODELS:
            raise ValueError(f"--cost-model must be one of {ENGINE_MODELS}, "
                             f"got {self.cost_model!r} (D74)")
        if self.mu_mode not in MU_MODES:
            raise ValueError(f"mu mode must be one of {MU_MODES}")
        if self.cap_k is not None and int(self.cap_k) <= 0:
            raise ValueError("--release-cap-k must be a positive integer or unset (unlimited)")
        if self.impl not in ("fast", "reference"):
            raise ValueError("--policy-impl must be 'fast' or 'reference', got %r" % self.impl)
        if self.mu_mode == "fixed" and self.mu_fixed is None:
            raise ValueError("mu mode 'fixed' needs --mu-fixed VALUE, whose value D88 sets to "
                             "x0.5 and x2 of the EWMA estimator's time-averaged value over the "
                             "pilot runs; no committed DEV value exists")
        self._reset_sh_audit()

    # ---------------------------------------------------------------- setup
    def live2_configure(self, *, gpu_kv_tokens: int, host_tier_gib: float,
                        host_tier_tokens: int, targets: Dict[str, Any],
                        calibration_knots_path: Any = None, **kw: Any) -> None:
        super().live2_configure(gpu_kv_tokens=gpu_kv_tokens, host_tier_gib=host_tier_gib,
                                host_tier_tokens=host_tier_tokens, targets=targets)
        if gpu_kv_tokens <= 0 or host_tier_tokens <= 0:
            raise ValueError("D56: GPU and host capacities are INPUTS and must be supplied as "
                             "positive token counts; the policy refuses to guess one")
        self.pf = load_profiles()
        p = Params()
        p.gpu_kv_capacity_tokens = int(gpu_kv_tokens)
        p.host_kv_capacity_tokens = int(host_tier_tokens)
        p.H = float(self.h_s)
        p.H_s = float(PLACEHOLDERS["H_s"]["value"])
        p.feasibility_threshold = float(PLACEHOLDERS["feasibility_threshold"]["value"])
        p.prefix_loss_replan_threshold = float(
            PLACEHOLDERS["prefix_loss_replan_threshold"]["value"])
        # D89: the class weights approved for round 1; omega_SS stays unset (no SS traffic, P2).
        p.omega = {"SH": 1.0, "RC": 0.4246, "SS": None}
        p.L_k = {"SH": float(targets["dashcam"]["L_s"]), "SS": 2.0,
                 "RC": float(targets["robot"]["L_s"])}
        p.p_k = {"SH": float(targets["dashcam"]["p"]), "SS": 0.9,
                 "RC": float(targets["robot"]["p"])}
        if self.mu_mode == "scarcity":
            # D129: near zero with spare capacity, rising with real predicted backlog.
            p.mu, p.mu_estimator = 0.0, "scarcity"
            p.mu_scale = float(self.mu_scale)
        elif self.mu_mode == "none":
            p.mu, p.mu_estimator = 0.0, "none"
        elif self.mu_mode == "fixed":
            p.mu, p.mu_estimator = float(self.mu_fixed), "none"
        else:
            p.mu, p.mu_estimator = 0.0, "ewma_marginal_utility"
        if calibration_knots_path is not None:
            p.tier_calibration = CAL.load(calibration_knots_path)
        p.kappa = (None if self.kappa is None else float(self.kappa))
        self.params = p
        # D122: a v1.1 defect fix travels on `Flags` so the rollout can read it, but it is NOT
        # one of spec 7.0's conditional mechanisms, so the D66 guard asks `conditional_any_on`.
        self.flags = Flags(honour_job_priority=bool(self.honour_job_priority),
                           rc_tail=bool(self.rc_tail),
                           write_staleness=bool(self.write_staleness),
                           realistic_competing=bool(self.realistic_competing),
                           rc_tail_cursor=bool(self.rc_tail_cursor),
                           rc_tail_zrows=bool(self.rc_tail_zrows),
                           prob_p_finish=bool(self.prob_p_finish),
                           planner_rc=bool(self.planner_rc),
                           plan_latest=bool(self.plan_latest),
                           replan=bool(self.replan))
        if self.flags.conditional_any_on():
            raise RuntimeError("D66: round 1 runs the CORE only and every conditional flag must "
                               "be off; one is on")
        self.engine = Eng1Engine.load(gpu_kv_tokens=int(gpu_kv_tokens),
                                      host_kv_tokens=int(host_tier_tokens), profiles=self.pf,
                                      engine_model=self.cost_model)
        # D66's "residency bookkeeping (RES1)": the belief comes from StudyRES1's MEASURED
        # rule (4-class tier accuracy 0.9946 on StudyENG1c) with its boundary split, instead of
        # `tiers.p_host_from_occupancy`, whose eviction order is an explicitly labelled
        # ASSUMPTION. The cap is the host capacity INPUT (D56), so a different capacity scales
        # the boundary margin rather than changing the rule.
        self.residency = ResidencyBelief(cap_gib=float(host_tier_gib),
                                         gpu_pool_tokens=int(gpu_kv_tokens))
        self.rollout = Rollout(self.pf, p, self.flags, self.engine,
                               residency_belief=self.residency)
        if self.cap_k is not None:
            p.release_eval_cap_k = int(self.cap_k)
            # D99 (4): the D63 PREDICTION LOG is two extra rollouts per logged release and is
            # pure logging, so a capped run must not spend more of the period on predictions
            # than on decisions. It is limited to K logged releases per period; at a 100 ms
            # period that is still 10 x K predicted-versus-actual samples a second.
            self.predict_log_max = min(int(self.predict_log_max), int(self.cap_k))
        self._clone_impl = "reference" if self.impl == "reference" else "fast"
        self.rollout.clone_impl = self._clone_impl
        self.co = Coordinator(self.pf, p, self.flags, self.engine, self.rollout,
                              residency_belief=self.residency)
        if self.sh_cost not in CF.SH_COST_MODES:
            raise ValueError("--sh-cost must be one of %s, got %r"
                             % (CF.SH_COST_MODES, self.sh_cost))
        self.co.sh_cost = self.sh_cost
        self.fleet = Fleet(t=0.0)
        self._roster: Dict[str, Any] = dict(devices={}, session_device={})
        self._jobs_by_q: Dict[str, str] = {}
        self._session_of_job: Dict[str, str] = {}
        self._seen: set = set()
        self._ready = True
        # D122 B1: `reset` also sets this, but `live2_configure` is the call every path makes
        # before deciding, so the tracking dict is created here too rather than relying on reset.
        if not hasattr(self, "_z_track"):
            self._z_track: Dict[str, Dict[str, Any]] = {}

    def _reset_sh_audit(self) -> None:
        """F-4 and F-5 bookkeeping, both per run."""
        # F-4: the opportunity ids this arm actually SCORED and admitted, so a monitor request
        # the coordinator serves can be checked against them.
        self._sh_scored: set = set()
        self._sh_admitted: set = set()
        # F-5: per device, the SH instant that was declined and not yet followed by an admit.
        self._sh_pending_decline: Dict[str, float] = {}
        self._sh_decline_delays_s: List[float] = []
        self._sh_declines_followed_by_admit = 0

    def reset(self, seed: int = 0) -> None:
        self.last_predictions = {}
        self.mu_samples = []
        self.stats = dict(escalations=0, admitted=0, declined=0, released=0, held=0,
                          prefix_loss_replans=0, jobs_infeasible=0,
                          sh_escalated=0, sh_admitted=0, sh_declined=0,
                          sh_cap_bound_periods=0, sh_cap_skipped=0,
                          sh_served_not_scored=0,
                          release_cap_k=self.cap_k,
                          deficit_update=bool(self.deficit_update),
                          z_updates=0, z_misses=0, z_successes=0)
        self._reset_sh_audit()
        # B1: opportunity_id -> {task, device, deadline_abs, answered_at}. Registered from the
        # OBSERVATION, not from admissions, so a declined or never-admitted opportunity still
        # resolves as a miss.
        self._z_track: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------------- D122 fix B1
    def _z_register(self, obs: Observation) -> None:
        """Record every opportunity this period SHOWS the arm, so a decline counts as a miss.

        Registering from admissions instead would make the counter blind to exactly the
        opportunities the policy chose not to serve, which are the ones a deficit exists to
        notice.
        """
        instants = (self._roster or {}).get("sh_instant", {})
        for sid, inst in instants.items():
            oid = inst.get("opportunity_id")
            if oid is None or oid in self._z_track:
                continue
            self._z_track[str(oid)] = dict(task="SH", device=sid,
                                           deadline_abs=float(inst["deadline_abs"]),
                                           answered_at=None)
        for q in obs.recall:
            oid = str(q.query_id)
            if oid in self._z_track:
                continue
            dev = (self._roster or {}).get("session_device", {}).get(q.session_id,
                                                                       q.session_id)
            self._z_track[oid] = dict(task="RC", device=dev,
                                      deadline_abs=float(q.deadline_s), answered_at=None)

    def _z_note_answer(self, opportunity_id: Any, t_first_token: Any) -> None:
        """The application sees an answer at its FIRST TOKEN (harness addendum), so that is the
        time on-time is judged against."""
        if opportunity_id is None or t_first_token is None:
            return
        rec = self._z_track.get(str(opportunity_id))
        if rec is not None and rec.get("answered_at") is None:
            rec["answered_at"] = float(t_first_token)

    def _z_resolve(self, now: float) -> None:
        """Bump each opportunity's device ONCE, when its outcome is certain.

        Certain means either an answer arrived, or the deadline has passed with nothing. The
        one-period lag this leaves is accepted by the D122 ruling.
        """
        done = []
        for oid, rec in self._z_track.items():
            ans = rec.get("answered_at")
            if ans is not None:
                success = 1.0 if float(ans) <= rec["deadline_abs"] else 0.0
            elif rec["deadline_abs"] < now:
                success = 0.0
            else:
                continue
            dev = self.fleet.devices.get(rec["device"])
            if dev is not None:
                # D126 F5c: route through the spec entry point rather than calling bump_z
                # directly, so `Coordinator.update_deficit`, which spec_map.py names for spec 3.3
                # and 7.6, is live rather than dead code. Exactly equivalent: the coordinator was
                # built with the same params object, and the `dev is not None` guard is kept
                # because `fleet.device` indexes rather than creates.
                self.co.update_deficit(self.fleet, rec["device"], rec["task"], success)
                self.stats["z_updates"] = int(self.stats.get("z_updates", 0)) + 1
                key = "z_successes" if success > 0 else "z_misses"
                self.stats[key] = int(self.stats.get(key, 0)) + 1
            done.append(oid)
        for oid in done:
            self._z_track.pop(oid, None)

    def _apply_partial_readiness(self) -> None:
        """D100 (a): cost a later reconstruction piece as A PIECE ON A WARM PREFIX.

        The arm-side hook carries how much of each history the cloud has ALREADY BUILT. Without
        it the item's readiness stayed COLD until the whole chain finished (the believed tier
        becomes `gpu` only at `built_tokens >= est_tokens`), so `Eng1Engine.predict` charged
        every later piece `cached = 0` -- a cold rebuild -- even though the already-sent frames
        travel as uuid REFERENCES and the prefix is on the GPU (StudyLIVE2-coord open issue 3b).
        The built prefix is set as `cached_tokens` on the item, which is exactly the input the
        committed cost model reads; nothing in `policy/` is changed. A prefix believed to be on
        the HOST additionally carries `external_cached_tokens`, so the host-KV reload is charged
        (StudyPOL4-engine term (a)) rather than silently treated as GPU-warm.
        """
        built = (self._roster or {}).get("built_tokens_by_session", {})
        if not built:
            return
        for p in list(self.fleet.pending) + list(self.fleet.in_flight):
            if p.kind != "rc_piece" or not p.job_id:
                continue
            sid = self._session_of_job.get(p.job_id)
            b = int(built.get(sid, 0)) if sid else 0
            if b <= 0:
                continue
            job = self.fleet.jobs.get(p.job_id)
            dev = self.fleet.devices.get(job.device) if job is not None else None
            bel = dev.history.get("RICH") if dev is not None else None
            tier = bel.most_likely() if bel is not None else "GPU"
            if tier == "HOST":
                p.readiness = "HOST-WARM"
                p.meta["external_cached_tokens"] = b
            else:
                p.readiness = "GPU-WARM"
                p.meta.pop("external_cached_tokens", None)
            p.meta["cached_tokens"] = b

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """The device roster and session ownership, which EVERY arm could know: who registered,
        of what type, over what link, and which device a session belongs to. It carries no
        future information and no per-opportunity information, and `interface.scrub` still runs
        on the observation itself."""
        self._roster = roster

    # ---------------------------------------------------------------- the decision
    def decide(self, obs: Observation) -> Action:
        if not self._ready:
            raise RuntimeError("live2_configure must run before the policy arm decides")
        # StudyLIVE2-perf Option 0: the terminal state-value memo is scoped to ONE decision
        # period. Clearing it here is what makes that true, and it bounds any key error to a
        # single period rather than a whole run.
        ro = getattr(self.co, "rollout", None)
        if ro is not None and hasattr(ro, "state_value_cache"):
            ro.state_value_cache().clear()
        self._sync(obs)
        self._prune(float(obs.now_s))
        if self.deficit_update:
            self._z_register(obs)
            self._z_resolve(float(obs.now_s))
        self._apply_partial_readiness()
        decs: List[Any] = []
        decs += self._admit_monitoring(obs)
        decs += self._admit_recall(obs)
        # The snapshot is taken HERE, after admission and before the release loop, because
        # spec 3.5's counterfactual for a release is "release now vs defer to the next candidate
        # slot" from the state the release loop actually sees.
        # D99 (2): the SAME clone the rollout uses, instead of a full deepcopy of the fleet
        # once per epoch. It gives independent pending / in-flight lists, items, jobs, devices
        # and histories, which is everything the release loop writes to between here and the
        # prediction; the prediction log is the only consumer and no decision reads it.
        before = (copy.deepcopy(self.fleet) if self._clone_impl == "reference"
                  else clone_for_rollout(self.fleet)) if self.predict_log_max > 0 else None
        decs += self.co.on_event(self.fleet, dict(kind="timer"))
        self._feed_mu_estimator(decs)
        self._update_mu_samples()
        self._collect_cap_stats()
        return self._to_action(obs, decs, before)

    # ---- fleet mirror
    def _sync(self, obs: Observation) -> None:
        f = self.fleet
        f.t = float(obs.now_s)
        for s in obs.streams:
            if s.stream_id not in f.devices:
                f.add_device(self._device(s.stream_id, s.network.uplink_bps, s.network.rtt_s))
            d = f.devices[s.stream_id]
            d.link.reachable = bool(s.network.connected)
            if not s.network.connected:
                self.co.on_outage(f, d.device_id, 0.0)
        for q in obs.recall:
            did = self._roster["session_device"].get(q.session_id, q.session_id)
            if did not in f.devices:
                f.add_device(self._device(did, 13.6e6 / 8.0, 0.044))
            d = f.devices[did]
            b = d.history.get("RICH")
            if b is None:
                b = HistoryBelief(rep="RICH", size_tokens=int(q.readiness_tokens))
                d.history["RICH"] = b
            b.size_tokens = int(q.readiness_tokens)
            b.probs = {"GPU": 0.0, "HOST": 0.0, "STORED": 0.0}
            b.probs[{"GPU-WARM": "GPU", "HOST-WARM": "HOST", "COLD": "STORED"}[q.readiness]] = 1.0
            b.normalize()
            # D122 v1.1: `staleness_s` is READ by `utility.t_ready_s`, where
            # `frames = staleness_s / d2_stride_s` turns it into catch-up frames, and it was
            # written NOWHERE in production, so every history looked perfectly fresh and no
            # catch-up work was ever charged. It is the frames the cloud has received but not
            # built, expressed in the seconds unit the consumer expects.
            if self.flags.write_staleness:
                built = int((self._roster or {}).get("built_tokens_by_session", {})
                            .get(q.session_id, 0))
                unbuilt = max(int(q.readiness_tokens) - built, 0)
                b.staleness_s = (unbuilt / float(D2_TOK_PER_IMG)) * float(self._d2_stride_s())
            d.qtype = QTYPE

    @staticmethod
    def _known_sessions(obs: Observation) -> set:
        """The sessions `interface.validate_action` accepts in a session action."""
        return (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                | {q.session_id for q in obs.recall})

    def _d2_stride_s(self) -> float:
        """The committed D2 capture stride, from the profile rather than a literal."""
        return float(self.pf.raw["durations"]["catchup_per_frame"]["d2_stride_s"])

    def _prune(self, now: float) -> None:
        """Spec 7.9 with merging OFF, and D62.

        (a) A held monitoring call still unsent when its own window has passed IS A DEVICE-ONLY
        OUTCOME (D24, spec 7.9: merging is off and its enabling condition is not met), so it
        leaves the pending set instead of competing forever. Without this the pending set grows
        without bound and the release loop's cost grows with it, which is the OPEN item spec
        section 14 names.
        (b) D62 makes SH per-instant: an admitted instant is ONE call, so its Episode is over
        once the call is dispatched. The library's episode bookkeeping (spec 7.1, from D19) is
        left untouched but closed episodes older than the state horizon are dropped, so the
        fleet the rollout deep-copies does not grow with the run length.
        """
        keep, dropped = [], 0
        for p in self.fleet.pending:
            if p.kind == "episode_call" and p.deadline is not None and p.deadline < now - 1e-9:
                dropped += 1
                continue
            keep.append(p)
        if dropped:
            self.fleet.pending = keep
            self.stats["monitor_to_device"] = self.stats.get("monitor_to_device", 0) + dropped
        # SAFETY NET for the same thing `live2_completed` does from the engine's own reports:
        # an item whose deadline has passed is no longer work the engine is doing, so it must
        # not keep the modelled engine busy. Without this the rollout sees an engine that never
        # empties, every new candidate's start falls beyond the horizon, and admission returns
        # DeltaJ = 0 for reasons that have nothing to do with the fleet.
        self.fleet.in_flight = [p for p in self.fleet.in_flight
                                if p.deadline is None or p.deadline >= now - 1e-9]
        for d in self.fleet.devices.values():
            live = []
            for ep in d.episodes:
                if ep.closed_at is None and ep.calls_issued:
                    ep.closed_at = max(ep.calls_issued)
                if ep.closed_at is None or ep.closed_at >= now - float(self.params.H_s):
                    live.append(ep)
            d.episodes = live

    def live2_sh_audit(self) -> Dict[str, Any]:
        """F-4 / F-5 as reported numbers, not inferences."""
        d = sorted(self._sh_decline_delays_s)
        def g(pp):
            return round(d[min(int(pp * len(d)), len(d) - 1)], 6) if d else None
        return dict(
            sh_scored=len(self._sh_scored), sh_admitted=len(self._sh_admitted),
            sh_served_not_scored=int(self.stats.get("sh_served_not_scored", 0)),
            sh_declines_followed_by_an_admit=self._sh_declines_followed_by_admit,
            sh_decline_delay_s=(dict(n=len(d), p50=g(0.5), p90=g(0.9), p99=g(0.99),
                                     max=round(d[-1], 6), mean=round(sum(d) / len(d), 6))
                                if d else dict(n=0)))

    def live2_completed(self, info: Dict[str, Any]) -> None:
        """The engine finished a request this arm released: the item leaves `in_flight`.

        The coordinator does not know the policy's item ids, so the match is by (kind, device)
        in release order, which is the order the engine served them in.
        """
        want = "episode_call" if info["kind"] == "monitor" else "rc_piece"
        # F-4: THE INSTANT THE POLICY SCORED IS THE INSTANT THE COORDINATOR SERVES. The arm
        # scores the instant the D100 hook names and keys it by that opportunity_id; if the
        # coordinator ever served a different one, every DeltaJ this arm computed would be about
        # an instant that was not the one answered, and no later check would notice.
        opp = info.get("opportunity_id")
        if info["kind"] == "monitor" and opp is not None:
            if opp not in self._sh_admitted:
                self.stats["sh_served_not_scored"] = (
                    self.stats.get("sh_served_not_scored", 0) + 1)
                raise AssertionError(
                    "F-4: the coordinator served SH instant %r, which this arm never scored and "
                    "admitted (scored %d, admitted %d). The arm scored the instant the D100 hook "
                    "named; serving a different one would make every DeltaJ refer to an instant "
                    "that was not answered." % (opp, len(self._sh_scored),
                                                len(self._sh_admitted)))
        # RES1 bookkeeping: a completed build restarts that history's own clock and ages every
        # other history by what was written; any other completed request is just a write.
        if self.deficit_update:
            self._z_note_answer(info.get("opportunity_id"), info.get("t_first_token"))
        tok = int(info.get("prompt_tokens") or 0)
        dev = info.get("device_id")
        if want == "rc_piece":
            sid = info.get("session_id")
            jid = next((j for j, s in self._session_of_job.items() if s == sid), None)
            for i, p in enumerate(self.fleet.in_flight):
                if p.kind == "rc_piece" and (jid is None or p.job_id == jid):
                    self.fleet.in_flight.pop(i)
                    if tok > 0:
                        self.residency.note_build(prefix_id_for(p.job_id), tok)
                    job = self.fleet.jobs.get(p.job_id)
                    if job is not None:
                        job.pieces_done = min(job.pieces_done + 1, job.pieces_total)
                        if info["kind"] == "recall":
                            job.answered = True
                    return
            return
        if tok > 0:
            self.residency.note_write(tok)
        for i, p in enumerate(self.fleet.in_flight):
            if p.kind == want and p.device == dev:
                self.fleet.in_flight.pop(i)
                return

    def _device(self, device_id: str, uplink_bps: float, rtt_s: float) -> Device:
        d = Device(device_id=device_id,
                   link=Link(bandwidth_bytes_s=max(uplink_bps / 8.0, 1.0), rtt_s=float(rtt_s)),
                   qtype=QTYPE)
        d.demand = Demand().prior_from_profiles(self.pf)
        return d

    # ---- admission
    def _admit_monitoring(self, obs: Observation) -> List[Any]:
        """D62: every instant is a candidate; admission (8.1) and the release loop (8.2) decide.

        D100: the instant and ITS OWN DEADLINE c_i + L_SH come from the arm-side hook, which
        carries the very instant the coordinator will serve for this device (the earliest-
        deadline eligible one). The old reading -- "the newest delivered time IS the newest
        instant", with the deadline reconstructed from a placeholder window -- both guessed the
        instant and could guess a different one from the one that gets served.
        """
        out: List[Any] = []
        window = float(PLACEHOLDERS["monitor_answer_window_s"]["value"])
        # The hook is authoritative WHEN PRESENT, and an empty `sh_instant` means "this device
        # has no undecided instant right now", NOT "fall back to guessing". Falling back there
        # re-escalated the instant that had just been admitted (its newest delivered time is the
        # instant now in flight), under a different seen-key, which doubled the escalation count
        # and produced one dead decline per served instant.
        roster = self._roster or {}
        has_hook = "sh_instant" in roster
        instants = roster.get("sh_instant", {})
        cands = []
        for s in obs.streams:
            if not s.network.connected:
                continue
            inst = instants.get(s.stream_id)
            if inst is not None:
                capture, deadline = float(inst["t_capture"]), float(inst["deadline_abs"])
                key = ("SH", str(inst["opportunity_id"]))
            elif has_hook:
                continue
            else:
                if not s.delivered_times_s:
                    continue
                capture = float(s.delivered_times_s[-1])
                deadline = capture + window
                key = ("SH", s.stream_id, round(capture, 4))
            if key in self._seen:
                continue
            cands.append((deadline, s.stream_id, s, capture, key))
        # D99 (4): pi_0 order is by deadline, so the cap keeps the instants that are closest to
        # missing and leaves the rest to the next period (they are still visible until their own
        # deadline, so nothing is silently dropped).
        cands.sort(key=lambda c: (c[0], c[1]))
        if self.cap_k and len(cands) > int(self.cap_k):
            self.stats["sh_cap_bound_periods"] = self.stats.get("sh_cap_bound_periods", 0) + 1
            self.stats["sh_cap_skipped"] = (self.stats.get("sh_cap_skipped", 0)
                                            + len(cands) - int(self.cap_k))
            cands = cands[:int(self.cap_k)]
        for deadline, _did, s, capture, key in cands:
            self._seen.add(key)
            opp_id = (str(instants[s.stream_id]["opportunity_id"])
                      if instants.get(s.stream_id) is not None else None)
            if opp_id is not None:
                self._sh_scored.add(opp_id)
            req = EscalationRequest(device=s.stream_id, task="SH", t=obs.now_s,
                                    deadline=deadline, capture_at=capture,
                                    frames=int(s.frame_count),
                                    payload_bytes=self._frame_bytes(s.stream_id))
            self.stats["escalations"] = self.stats.get("escalations", 0) + 1
            self.stats["sh_escalated"] = self.stats.get("sh_escalated", 0) + 1
            ds = self.co.escalate(self.fleet, req)
            out += ds
            # D98 needs the SH admission decisions readable on their own: before the per-instant
            # rule, every one of these was a decline with DeltaJ exactly 0 at H <= T_k
            # (StudyLIVE2-coord open issue 1), and that is only visible if admits and declines
            # are counted per TASK rather than pooled.
            for d in ds:
                # `Coordinator.escalate` labels its verdict "escalation"; `_admission` labels
                # the same verdict "admission". Both are the admit-or-decline decision.
                if d.kind not in ("escalation", "admission"):
                    continue
                side = "sh_admitted" if d.taken else "sh_declined"
                self.stats[side] = self.stats.get(side, 0) + 1
                if d.taken and opp_id is not None:
                    self._sh_admitted.add(opp_id)
                # F-5: a declined instant costs this device its next cloud look. The decline is
                # held until the device's NEXT admit, and the gap between the two is the delay
                # that decline imposed on that device's escalation.
                if d.taken:
                    t_dec = self._sh_pending_decline.pop(s.stream_id, None)
                    if t_dec is not None:
                        self._sh_declines_followed_by_admit += 1
                        self._sh_decline_delays_s.append(max(0.0, float(obs.now_s) - t_dec))
                else:
                    self._sh_pending_decline.setdefault(s.stream_id, float(obs.now_s))
                if d.delta_j is not None:
                    key = "sh_delta_j_admit" if d.taken else "sh_delta_j_decline"
                    self.stats.setdefault(key, []).append(float(d.delta_j))
        return out

    def _admit_recall(self, obs: Observation) -> List[Any]:
        out: List[Any] = []
        for q in obs.recall:
            if q.query_id in self._jobs_by_q or ("RC", q.query_id) in self._seen:
                continue
            self._seen.add(("RC", q.query_id))
            did = self._roster["session_device"].get(q.session_id, q.session_id)
            req = EscalationRequest(device=did, task="RC", t=obs.now_s,
                                    deadline=q.deadline_s, qtype=QTYPE,
                                    temporal_reference_s=float(self.params.H_s),
                                    device_window_s=2.0, payload_bytes=0, frames=0)
            ds = self.co.escalate(self.fleet, req)
            out += ds
            took = [d for d in ds if d.taken]
            if took:
                self.stats["admitted"] = self.stats.get("admitted", 0) + 1
                jid = self._newest_job(did)
                if jid is not None:
                    self._jobs_by_q[q.query_id] = jid
                    self._session_of_job[jid] = q.session_id
            else:
                self.stats["declined"] = self.stats.get("declined", 0) + 1
        return out

    def _newest_job(self, device_id: str) -> Optional[str]:
        cands = [j for j in self.fleet.jobs.values() if j.device == device_id and not j.answered]
        if not cands:
            return None
        return max(cands, key=lambda j: j.admitted_at).job_id

    def _frame_bytes(self, device_id: str) -> int:
        return int(self._roster.get("frame_bytes", {}).get(device_id, 0))

    # ---- translation into the shared action space
    def _to_action(self, obs: Observation, decs: List[Any], before: Any) -> Action:
        released = [d for d in decs if d.kind == "release" and d.taken]
        held = [d for d in decs if d.kind == "release" and not d.taken]
        self.stats["released"] = self.stats.get("released", 0) + len(released)
        self.stats["held"] = self.stats.get("held", 0) + len(held)
        self.stats["prefix_loss_replans"] = (self.stats.get("prefix_loss_replans", 0)
                                             + sum(1 for d in decs if d.kind == "prefix_loss"))
        by_item = {p.item_id: p for p in self.fleet.in_flight}
        stream_on, mat, cloud_q = set(), {}, set()
        preds: Dict[str, Any] = {}
        for i, d in enumerate(released):
            p = by_item.get(d.target)
            if p is None:
                continue
            if p.kind == "episode_call":
                stream_on.add(p.device)
                oid = "mon:" + p.device
            elif p.kind == "rc_piece":
                job = self.fleet.jobs.get(p.job_id)
                sid = self._session_of_job.get(p.job_id)
                if sid is None or job is None:
                    continue
                # D122 v1.1: a MATERIALIZE may only name a session the observation still knows
                # (`interface.validate_action`: gpu-warm, host-warm, or offered this period).
                # The RC tail makes a job valuable past its opportunity's visibility, so without
                # this guard the arm emits a build for a session the coordinator is no longer
                # offering and the action is rejected. The piece is simply not materialised this
                # period; it is re-decided when the session is offered again.
                if sid not in self._known_sessions(obs):
                    continue
                mat[sid] = (int(job.pieces_total * job.tokens_per_piece),
                            None if job.pieces_total <= 1 else int(job.tokens_per_piece))
                for qid, jid in self._jobs_by_q.items():
                    if jid == p.job_id:
                        cloud_q.add(qid)
                oid = "rc:" + p.job_id
            else:
                continue
            if i < self.predict_log_max and before is not None:
                preds[oid] = self._predict(before, p.item_id)
        self.last_predictions = dict(
            by_target=preds, mu=float(self.params.mu), H=float(self.params.H),
            cost_model_id=self.engine.model_name(),
            belief=self._belief_tokens(), n_released=len(released), n_held=len(held),
            delta_j={d.target: d.delta_j for d in decs if d.delta_j is not None},
            decisions=[dict(kind=d.kind, target=d.target, taken=bool(d.taken),
                            delta_j=d.delta_j, reason=d.reason[:200]) for d in decs],
        )
        streams = [StreamAction(s.stream_id, "cloud" if s.stream_id in stream_on else "local")
                   for s in obs.streams]
        recall = []
        for q in obs.recall:
            if q.query_id in cloud_q:
                recall.append(RecallAction(q.query_id, "CLOUD", representation="D2"))
            elif q.query_id in self._jobs_by_q:
                recall.append(RecallAction(q.query_id, "DEFER", defer_s=0.0))
            else:
                recall.append(RecallAction(q.query_id, "DEVICE"))
        sessions = [materialize(sid, tgt, slice_) for sid, (tgt, slice_) in sorted(mat.items())]
        return Action(streams=streams, recall=recall, sessions=sessions, order="EDF",
                      notes=dict(arm="policy-core", mu=float(self.params.mu),
                                 H=float(self.params.H), n_released=len(released)))

    def _predict(self, before: Any, item_id: str) -> Dict[str, Any]:
        """D63: the prediction that is logged beside the outcome.

        The counterfactual is the spec's own pair (release now vs defer to the next candidate
        slot, both under pi_0), so the imposed delay per other request is the DIFFERENCE of that
        request's predicted delivery between the two rollouts.
        """
        a = self.rollout.run(before, release_now=[item_id])
        b = self.rollout.run(before, exclude=[item_id])
        mine = next((d for d in a.deliveries if d["item_id"] == item_id), None)
        bt = {d["item_id"]: d["delivered_at"] for d in b.deliveries}
        imposed = {d["item_id"]: round(d["delivered_at"] - bt[d["item_id"]], 6)
                   for d in a.deliveries
                   if d["item_id"] != item_id and d["item_id"] in bt}
        return dict(ttft_s=(round(mine["start"] - before.t, 6) if mine else None),
                    completion_s=(round(mine["delivered_at"] - before.t, 6) if mine else None),
                    imposed_delay_s_by_request={k: v for k, v in imposed.items() if abs(v) > 1e-9},
                    in_sample=bool(a.in_sample and b.in_sample))

    def _belief_tokens(self) -> Dict[str, Dict[str, int]]:
        out = {"gpu_tokens_by_session": {}, "host_tokens_by_session": {},
               "cold_tokens_by_session": {}}
        for jid, sid in self._session_of_job.items():
            dev = self.fleet.jobs[jid].device if jid in self.fleet.jobs else None
            d = self.fleet.devices.get(dev) if dev else None
            b = d.history.get("RICH") if d else None
            if b is None:
                continue
            key = {"GPU": "gpu_tokens_by_session", "HOST": "host_tokens_by_session",
                   "STORED": "cold_tokens_by_session"}[b.most_likely()]
            out[key][sid] = int(b.size_tokens)
        return out

    def _feed_mu_estimator(self, decs: List[Any]) -> None:
        """`ewma_marginal_utility` reads the realized marginal utility of the LAST RELEASED
        ITEM from `Coordinator._last_delta_j`, which the library expects its CALLER to set: the
        attribute is assigned nowhere in `policy/`, and `policy/tests/test_pol3_update.py:325`
        and `:334` set it from outside before calling `_update_mu`. Left unset it is 0 through
        `getattr`, so the EWMA arm would be indistinguishable from mu = 0 and D88's two fixed
        values, which are x0.5 and x2 of its time average, would both be 0.

        `_update_mu` runs at the END of `on_event`, so the value fed here is used by the NEXT
        epoch's update: a one-epoch lag, which is what "the last released item" means anyway.
        Nothing in `policy/` is modified.
        """
        taken = [d for d in decs if d.kind == "release" and d.taken and d.delta_j is not None]
        if taken:
            self.co._last_delta_j = float(taken[-1].delta_j)

    def _collect_cap_stats(self) -> None:
        """D99 (4): the release loop's own cap counters, so "how often does it bind" is a
        reported number rather than an inference."""
        self.stats["release_cap_bound_passes"] = int(getattr(self.co, "cap_bound_passes", 0))
        self.stats["release_cap_skipped_items"] = int(getattr(self.co, "cap_skipped_items", 0))
        self.stats["scoring_calls"] = int(getattr(self.co, "scoring_calls", 0))
        ro = getattr(self.co, "rollout", None)
        if ro is not None and hasattr(ro, "state_value_cache"):
            self.stats["state_value_cache"] = ro.state_value_cache().stats()
        self.stats.update(self.live2_sh_audit())

    def _update_mu_samples(self) -> None:
        if self.params.mu_estimator == "ewma_marginal_utility":
            self.mu_samples.append(float(self.params.mu))

    # ---- reporting
    def mu_time_average(self) -> Optional[float]:
        """D88: the EWMA arm must log its time-averaged mu, because the two fixed versions are
        set to x0.5 and x2 of it over the pilot runs."""
        if not self.mu_samples:
            return None
        return sum(self.mu_samples) / len(self.mu_samples)

    def placeholder_table(self) -> List[Dict[str, Any]]:
        rows = []
        for k, v in PLACEHOLDERS.items():
            val = v["value"]
            if k == "H":
                val = float(self.h_s)
            rows.append(dict(parameter=k, value=val, tuned=False, note=v["note"]))
        for k in sorted(self.params.placeholders()):
            rows.append(dict(parameter="params." + k, value=getattr(self.params, k, None),
                             tuned=False, note="params.PROVENANCE marks this a PLACEHOLDER"))
        rows.append(dict(parameter="release_eval_cap_k", value=self.cap_k, tuned=False,
                         note="D99 (4) SETTING: how many pending items get a full DeltaJ "
                              "evaluation per decision period, in the release loop and in SH "
                              "admission. None is unlimited. Reported with how often it bound "
                              "(arm_stats.sh_cap_bound_periods, release_cap_bound_passes)."))
        return rows

    def live2_describe(self) -> Dict[str, Any]:
        d = super().live2_describe()
        d["v12"] = dict(planner_rc=bool(self.planner_rc), plan_latest=bool(self.plan_latest),
                        replan=bool(self.replan), kappa=float(self.kappa),
                        kappa_provisional=True)
        d.update(cost_model_id=self.engine.model_name() if self._ready else self.cost_model,
                 mu_mode=self.mu_mode, mu_fixed=self.mu_fixed, H=self.h_s,
                 flags=self.flags.as_dict() if self._ready else None,
                 omega={"SH": 1.0, "RC": 0.4246})
        return d
