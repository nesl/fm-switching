#!/usr/bin/env python3
"""The eight round-1 arms, as D65 corrected by D90 defines them. CPU only.

Every arm is an `interface.Policy`, so EVERY ARM SHARES ONE ACTION SPACE and every action it
returns passes `interface.validate_action` while every observation passes `interface.scrub`
(both inside `Policy.__call__`). Arm 1, the policy core, lives in `arms_policy.py`.

| # | arm | what it is | source |
|---|---|---|---|
| 1 | `policy-core` | spec v4 core only, conditional mechanisms OFF | `arms_policy.py` |
| 2 | `device-only` | sends nothing; scored offline from recordings (D87) | `baselines/naive.py::DeviceOnly` AS COMMITTED |
| 3 | `always-cloud-fcfs` | the existing port | `baselines/naive.py::AlwaysCloudFCFS` AS COMMITTED |
| 4 | `edf` | the policy library's base policy pi_0, standalone, rebuilds WHOLE | `Pi0Edf` here, ordering by `policy/rollout.py::Rollout._edf` |
| 5 | `edf-piece1024` | pi_0 with a fixed 1,024-token piece | `Pi0Edf(piece_tokens=1024)` |
| 6 | `edf-piece2048` | pi_0 with a fixed 2,048-token piece | `Pi0Edf(piece_tokens=2048)` |
| 7 | `utility-per-cost` | utility per GPU-second | `baselines/constructed.py::B8UtilityPerGPUSecond` AS COMMITTED |
| 8 | `b9` | decomposed best-of-breed | `baselines/constructed.py::B9BestOfBreed` AS COMMITTED after amendment 2 (A4b / A5b already applied), with the run loop honouring DEFER (D90). No other change. |

HOW ARM 4 DIFFERS FROM THE REGISTRY'S `edf-service-time` (`baselines/naive.py:178`), which is a
different arm and is NOT one of the eight:
  * `edf-service-time` applies an ADMISSION FILTER: a query goes to the cloud only if
    `costs.recall_ttft_s` at its current readiness fits its remaining slack, else DEVICE. pi_0
    has no admission test; it releases by deadline and nothing is declined for not fitting.
  * `edf-service-time` never materializes, so a cold history is answered by one request at COLD
    readiness; pi_0 explicitly MATERIALIZEs the history it needs, whole (arm 4) or in a fixed
    piece (arms 5, 6).
  * `edf-service-time` orders only the recall queries and leaves streams at the documented
    default; pi_0 orders ONE merged pending set (monitoring calls, rebuild pieces, recall
    answers) and releases from the head of it.

    D114 NOTE ON THE SPEC, 2026-11-18. Spec 3.5 of both POLICY_SPEC_v3 and policy_spec_v4 defines
    pi_0 as "deadline-ordered release, ONE UNIT AT A TIME". Until D114 this arm matched that text
    and `policy/rollout.py::Rollout.run`, which serves the whole deadline-ordered queue bounded
    only by the horizon, did NOT. D114 makes the ARM work-conserving too, so the arm and the
    rollout now agree with each other and BOTH differ from the spec's wording. That wording needs
    either an amendment or a recorded deviation; it is a planner decision and is NOT settled here.
    Nothing in this file changes the spec.

DEFER is honoured by the run loop for EVERY arm (amendment 2, D90), including the arms that
never emit it.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/baselines/reconstructed"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib"),
           str(ROOT / "experiments/dashcam"), str(ROOT / "experiments/orchestration")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import (Action, Observation, Policy, RecallAction,      # noqa: E402
                       StreamAction, materialize)
import naive as NAIVE                                                  # noqa: E402
import constructed as CONS                                             # noqa: E402

from policy.rollout import Rollout                                     # noqa: E402
from policy.state import PendingItem                                   # noqa: E402

ARM_VERSION = "live2-arm-1.0"


class Live2ArmMixin:
    """The declarations the live2 run loop reads off an arm. Nothing policy-related."""

    arm_version: str = ARM_VERSION
    uses_h: bool = False                 # does this arm have a planning horizon H?
    h_s: Optional[float] = None
    releases_one_per_epoch: bool = False
    sends_requests: bool = True
    # D87: an arm whose PUBLISHED mechanism waits for the device's own answer is charged
    # StudyD8's 0.567 s rule. `interface.Policy.reads_device_answer` is that declaration.
    piece_tokens: Optional[int] = None
    needs_capacities: bool = False

    def live2_configure(self, *, gpu_kv_tokens: int, host_tier_gib: float,
                        host_tier_tokens: int, targets: Dict[str, Any],
                        **kw: Any) -> None:
        self._caps = dict(gpu_kv_tokens=int(gpu_kv_tokens), host_tier_gib=float(host_tier_gib),
                          host_tier_tokens=int(host_tier_tokens))
        self._targets = dict(targets)

    def live2_describe(self) -> Dict[str, Any]:
        return dict(arm=self.name, arm_version=self.arm_version, uses_h=self.uses_h,
                    h_s=self.h_s, releases_one_per_epoch=self.releases_one_per_epoch,
                    sends_requests=self.sends_requests, piece_tokens=self.piece_tokens,
                    reads_device_answer=bool(getattr(self, "reads_device_answer", False)),
                    source=getattr(self, "live2_source", "live2/arms.py"))


# ---------------------------------------------------------------- 2, 3: the existing port
class DeviceOnlyArm(Live2ArmMixin, NAIVE.DeviceOnly):
    """Arm 2. Sends nothing. Its task value is scored offline from the recordings (D87)."""

    live2_source = "baselines/naive.py::DeviceOnly AS COMMITTED"
    sends_requests = False


class AlwaysCloudFcfsArm(Live2ArmMixin, NAIVE.AlwaysCloudFCFS):
    """Arm 3. One request per opportunity, FCFS, no admission and no state management."""

    live2_source = "baselines/naive.py::AlwaysCloudFCFS AS COMMITTED"


# ---------------------------------------------------------------- 4, 5, 6: pi_0 standalone
class Pi0Edf(Live2ArmMixin, Policy):
    """pi_0 (spec 3.5 / 7.2): EDF over the pending set and calendar, WORK-CONSERVING (D114).

    The ordering is not re-implemented: the pending items are sorted by
    `policy/rollout.py::Rollout._edf`, which is the library's own pi_0 order
    `(deadline, due_at, item_id)`. `_edf` does not touch `self`, so it is called unbound rather
    than constructing a Rollout, which would require a cost model pi_0 does not use.

    D114 (user ruling 2026-11-18) replaced "release the head of the order" with "release from the
    head while in-flight cloud requests are below `c_inflight`". The old rule released ONE unit
    per 100 ms period across monitoring and recall combined, a ceiling of 10 releases per second,
    against 10.82 dashcam instants per second offered on the seed-10 trace: the backlog was
    permanent BY CONSTRUCTION, and because EDF orders by deadline and an instant's 0.5 s deadline
    always precedes a robot question's, the questions starved behind the instants. The rollout
    already modelled pi_0's continuation as work-conserving (`Rollout.run` serves the whole queue
    bounded only by the horizon), so this removes a mismatch rather than introducing one.

    What D114 did NOT change: pi_0 still declines nothing for not fitting, an item beyond the
    bound waits and is re-decided next period, an item past its deadline falls to the device, and
    MATERIALIZE still advances by ONE piece per epoch (D104 issue 6) at unchanged piece sizes.

    `piece_tokens = None` rebuilds WHOLE (arm 4); 1,024 and 2,048 are arms 5 and 6.
    """

    case = "own"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "recall_decision", "session_action", "order")
    defaults_used = ("cadence_s", "frame_count", "representation", "engine_config")
    releases_one_per_epoch = False       # D114: work-conserving up to `c_inflight`
    restricts_action_space = None

    # D114. The smallest concurrency at which the 32B reaches 100 % GPU utilisation in StudyD7b
    # Part A (reports/study_d7_capacity.md:180, 32B-I at N = 1, 12.73 req/s, 100 %). At N = 9 the
    # same report reaches 99-100 % from concurrency 2, so 4 is Part A's figure and the
    # conservative choice, not the minimum across every N.
    # D128 (2026-11-18): edf's DEFAULT concurrency is 8. StudyD7b Part A's 4 was the smallest
    # concurrency at which the 32B reaches 100 per cent GPU utilisation at N = 1, which bounds
    # utilisation and not throughput; 8 is the baseline the comparison now uses. 4 stays
    # reachable by parameter so the earlier cells remain reproducible.
    C_INFLIGHT_DEFAULT = 8

    def __init__(self, piece_tokens: Optional[int] = None,
                 c_inflight: int = C_INFLIGHT_DEFAULT) -> None:
        self.piece_tokens = int(piece_tokens) if piece_tokens else None
        self.c_inflight = int(c_inflight)
        # D131: one piece in flight per session, strictly in prefix order. ON by default; the
        # switch exists so the dry-run delta against the old behaviour can be measured.
        self.serialise_pieces = True
        self._pieces_outstanding = set()
        self._built_at_issue = {}
        if self.c_inflight < 1:
            raise ValueError("c_inflight must be at least 1, got %r" % (c_inflight,))
        self.name = ("edf" if self.piece_tokens is None
                     else f"edf-piece{self.piece_tokens}")
        self.live2_source = ("policy/rollout.py::Rollout._edf (pi_0 ordering), "
                             "D114 work-conserving release up to c_inflight=%d, " % self.c_inflight
                             + ("whole rebuild" if self.piece_tokens is None
                                else f"fixed {self.piece_tokens}-token pieces"))

    def live2_describe(self) -> Dict[str, Any]:
        d = super().live2_describe()
        d["c_inflight"] = int(self.c_inflight)
        return d

    def _release_budget(self, obs: Observation) -> int:
        """D114: how many units may be released this period.

        In-flight means submitted and not yet completed, counted across ALL kinds.
        `obs.cloud.running_by_class` is exactly that quantity: `cstate.observation` builds it from
        `st.in_flight`, which the coordinator increments at submit and decrements at completion.
        The snapshot is taken BEFORE any of this period's submissions, so completions that land
        mid-period are not visible until the next epoch. That makes the arm slightly conservative
        and never over-admitting, which is the documented D114 choice.
        """
        in_flight = sum(int(v) for v in (obs.cloud.running_by_class or {}).values())
        return max(int(self.c_inflight) - in_flight, 0)

    def reset(self, seed: int = 0) -> None:
        pass

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """D100: the arm-side hook. pi_0 reads ONE thing from it, each SH instant's own
        deadline c_i + L_SH, which is a causal fact known at the instant's arrival."""
        self._live2_roster = roster

    def _pending_items(self, obs: Observation) -> List[PendingItem]:
        """The merged pending set: monitoring instants, then recall answers.

        Moved out of `decide` verbatim so `LlfArm` (D118) can order the SAME set by a different
        key. Byte-identical decisions for every existing arm are a committed test.
        """
        items: List[PendingItem] = []
        tgt = getattr(self, "_targets", None)
        mon_l_s = float(tgt["dashcam"]["L_s"]) if tgt else 1.0
        instants = (getattr(self, "_live2_roster", None) or {}).get("sh_instant", {})
        for s in obs.streams:
            # D100: pi_0 orders a monitoring call by the TRUE per-instant deadline
            # c_i + L_SH of the instant this stream stands for, taken from the arm-side hook.
            # It replaces the "next call due after the last answer the application received"
            # workaround (open issue 9), under which every stream tied on `now + L` and the
            # tie-break by item_id served one dashcam 240 times and the other none. The
            # fallback below applies only when no hook is supplied at all.
            inst = instants.get(s.stream_id)
            if inst is not None:
                due = float(inst["t_capture"])
                dl = float(inst["deadline_abs"])
            else:
                last = (s.delivered_times_s[-1] if s.delivered_times_s
                        else obs.now_s - s.cadence_s)
                due = last + s.cadence_s
                dl = due + mon_l_s
            items.append(PendingItem(item_id="mon:" + s.stream_id, kind="episode_call",
                                     device=s.stream_id, due_at=due,
                                     deadline=dl, frames=1))
        for q in obs.recall:
            items.append(PendingItem(item_id="rc:" + q.query_id, kind="rc_piece",
                                     device=q.session_id, due_at=q.arrival_s,
                                     deadline=q.deadline_s, tokens=q.readiness_tokens,
                                     job_id=q.query_id, readiness=q.readiness))
        return items

    def decide(self, obs: Observation) -> Action:
        items = self._pending_items(obs)
        order = Rollout._edf(None, items)
        # D114: the head PREFIX, not the single head. Taking a prefix is what charges each
        # released unit against the bound within the period: the observation cannot see this
        # period's own submissions, so the arm counts the head items it releases itself.
        released = {p.item_id for p in order[:self._release_budget(obs)]}

        streams, recall, sessions = [], [], []
        piece_issued = (set(self._pieces_outstanding)
                        if (self.serialise_pieces and self.piece_tokens is not None) else set())
        for s in obs.streams:
            on = ("mon:" + s.stream_id) in released
            streams.append(StreamAction(s.stream_id, "cloud" if on else "local"))
        for q in obs.recall:
            take = ("rc:" + q.query_id) in released
            if not take:
                # pi_0 does not decline; the item simply waits for its slot. DEFER(0) means
                # "not now, re-decide at the next epoch" and is honoured by the run loop.
                recall.append(RecallAction(q.query_id, "DEFER", defer_s=0.0))
                continue
            recall.append(RecallAction(q.query_id, "CLOUD", representation="D2"))
            if q.readiness != "GPU-WARM":
                # D131 item 1, PIECE SERIALISATION. A session's history is a PREFIX: piece k+1 may
                # only be built on piece k. At C_inflight 8 two recall queries on the SAME session
                # can be released in one epoch, each issuing its own MATERIALIZE, so one session's
                # pieces advance in parallel and the history is partitioned OUT OF ORDER. NO
                # OVERLAP still holds, so no bytes go out twice, but a prefix-structured KV cache
                # cannot accept ranges that arrive out of sequence. At most ONE piece per session
                # is in flight: the second query still gets its CLOUD action and simply does not
                # advance the build this epoch.
                # SCOPE: pieces only. An arm with `piece_tokens is None` rebuilds WHOLE, and a
                # whole rebuild is a single-element partition that cannot be out of order with
                # itself, so the defect is unreachable for it. Gating those arms too would change
                # the behaviour of edf and llf, which are the SCORED baselines and must stay
                # byte-identical. Measured: gating them moved edf from 4 to 5 robot answers and
                # dashcam 0.9508 to 0.9462 at 16 devices seed 0, which is exactly the kind of
                # silent baseline drift that must not happen.
                if (self.serialise_pieces and self.piece_tokens is not None
                        and q.session_id in piece_issued):
                    continue
                if self.piece_tokens is not None:
                    piece_issued.add(q.session_id)
                # MATERIALIZE advances the build by ONE piece (CONTRACT.md), so a chained
                # rebuild needs one per epoch until the history is built; the coordinator
                # no-ops once it is. Issuing it once would build a single piece and leave the
                # chain unfinished, which is what arms 5 and 6 exist to exercise.
                sessions.append(materialize(q.session_id, max(q.readiness_tokens, 1),
                                            self.piece_tokens))
        if self.serialise_pieces and self.piece_tokens is not None:
            built = (getattr(self, "_live2_roster", None) or {}).get("built_tokens_by_session", {})
            for sid in list(self._pieces_outstanding):
                if int(built.get(sid, 0)) != int(self._built_at_issue.get(sid, -1)):
                    self._pieces_outstanding.discard(sid)
                    self._built_at_issue.pop(sid, None)
            for sid in piece_issued:
                if sid not in self._pieces_outstanding:
                    self._pieces_outstanding.add(sid)
                    self._built_at_issue[sid] = int(built.get(sid, 0))
        return Action(streams=streams, recall=recall, sessions=sessions, order="EDF")


# ---------------------------------------------------------------- 9: D118, least laxity first
class LlfArm(Pi0Edf):
    """Arm 9 (D118, BUILT AND IN NO RUN until the user decides): least laxity first.

    Why it exists. The D114 replay showed strict EDF starves robot questions: a dashcam
    instant's deadline always sorts ahead of a question's, so the question reaches the head too
    late for a multi-second cold rebuild. A reviewer will say "use least-laxity instead, and drop
    what can no longer make it". This is that baseline, built so the answer is measured and not
    argued.

    It inherits `Pi0Edf` for the D114 release rule, the D100 roster hook and the pending set, and
    changes exactly two things:

      * the ORDER is ascending laxity, `deadline - now - S_hat(unit)`, rather than deadline;
      * a unit whose laxity has gone NEGATIVE is skipped, not released, and falls to the device
        exactly as an expired item does. Skips are counted per kind in `stats`.

    There is no admission test beyond that skip rule, and no mu, deficit or utility anywhere.

    S_HAT USES COMMITTED MEASURED CURVES ONLY. Every term comes from `baselines/costs.py`, the
    same module `edf-service-time` reads (`naive.py`, `import costs as C`). The policy's cost
    model, its engine model and its rollout are NEVER consulted (D74), and a test asserts the
    source module.
    """

    case = "own"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "recall_decision", "session_action", "order")
    defaults_used = ("cadence_s", "frame_count", "representation", "engine_config")
    restricts_action_space = None

    # The committed single-frame server TTFT: StudyD7 / D7b open-loop p50 at 25 % of peak.
    SH_INSTANT_KEY = ("32BI", 1, 25)

    def __init__(self, piece_tokens: Optional[int] = None,
                 c_inflight: int = Pi0Edf.C_INFLIGHT_DEFAULT) -> None:
        super().__init__(piece_tokens=piece_tokens, c_inflight=c_inflight)
        # Only "llf" (whole) is named in ARM_NAMES; a piece variant is reachable by parameter.
        self.name = ("llf" if self.piece_tokens is None
                     else f"llf-piece{self.piece_tokens}")
        self.live2_source = ("live2/arms.py::LlfArm (D118), laxity order over the Pi0Edf pending "
                             "set, S_hat from baselines/costs.py only, "
                             "D114 work-conserving release up to c_inflight=%d, " % self.c_inflight
                             + ("whole rebuild" if self.piece_tokens is None
                                else f"fixed {self.piece_tokens}-token pieces"))
        self.stats: Dict[str, Any] = dict(arm=self.name, c_inflight=self.c_inflight,
                                          skips_by_kind={}, skipped_total=0,
                                          s_hat_source="baselines/costs.py")

    # ---- S_hat, committed curves only
    def s_hat_s(self, p: PendingItem) -> float:
        """Estimated service time for one pending unit, from committed measurements only.

        A monitoring instant is one frame, so its service time is the committed single-frame
        TTFT. A recall whose history is already resident is its committed reload TTFT at that
        readiness. A recall whose history is COLD pays the committed cold prefill rate for the
        tokens not yet built, PLUS the answer TTFT at the warm state the history is in once that
        rebuild lands.

        The two cold terms do NOT double count: `costs.recall_ttft_s(t, "COLD")` returns
        `t / COLD_PREFILL_TOK_S` and nothing else, so the prefill is charged exactly once and the
        answer is priced warm. Charging a COLD answer term instead would count the prefill twice.

        For a piece variant the remaining work is still the whole unbuilt history, because a
        job's laxity must count ALL of its remaining work or a long rebuild never starts early.
        """
        import costs as C
        if p.kind == "episode_call":
            return float(C.CLOUD_TTFT[self.SH_INSTANT_KEY])
        tok = max(int(getattr(p, "tokens", 0) or 0), 1)
        ready = str(getattr(p, "readiness", None) or "COLD").upper()
        if ready in ("GPU-WARM", "HOST-WARM"):
            return float(C.recall_ttft_s(tok, ready))
        # COLD. `unbuilt` is the whole history: a whole MATERIALIZE is one request, so a session
        # is either un-built (COLD) or built (warm) and there is no partial state for the NAMED
        # arm. For the unnamed piece variants this ignores partial progress, because the built
        # prefix (D100) never reaches the arm: `cstate.observation` gives every recall the FULL
        # believed history and varies only the tier. Recorded in the D118 pre-registration.
        return float(C.recall_ttft_s(tok, "COLD") + C.recall_ttft_s(tok, "GPU-WARM"))

    def laxity_s(self, p: PendingItem, now: float) -> float:
        return float(p.deadline) - float(now) - self.s_hat_s(p)

    def _count_skip(self, kind: str) -> None:
        by = self.stats["skips_by_kind"]
        by[kind] = int(by.get(kind, 0)) + 1
        self.stats["skipped_total"] = int(self.stats["skipped_total"]) + 1

    def decide(self, obs: Observation) -> Action:
        items = self._pending_items(obs)
        lax = {p.item_id: self.laxity_s(p, obs.now_s) for p in items}

        # The skip rule, before any ordering: a unit that can no longer make its deadline is
        # removed and falls to the device, as an expired item does now.
        skipped = set()
        for p in items:
            if lax[p.item_id] < 0.0:
                skipped.add(p.item_id)
                self._count_skip(p.kind)
        live = [p for p in items if p.item_id not in skipped]

        # Ascending laxity. `item_id` breaks ties so the order is total and reproducible.
        order = sorted(live, key=lambda p: (lax[p.item_id], p.item_id))
        released = {p.item_id for p in order[:self._release_budget(obs)]}

        streams, recall, sessions = [], [], []
        for s in obs.streams:
            on = ("mon:" + s.stream_id) in released
            streams.append(StreamAction(s.stream_id, "cloud" if on else "local"))
        for q in obs.recall:
            key = "rc:" + q.query_id
            if key in skipped:
                # Past saving: it falls to the device rather than occupying the cloud.
                recall.append(RecallAction(q.query_id, "DEVICE"))
                continue
            if key not in released:
                # Not declined, only not now: re-decided at the next epoch, as pi_0 does.
                recall.append(RecallAction(q.query_id, "DEFER", defer_s=0.0))
                continue
            recall.append(RecallAction(q.query_id, "CLOUD", representation="D2"))
            if q.readiness != "GPU-WARM":
                sessions.append(materialize(q.session_id, max(q.readiness_tokens, 1),
                                            self.piece_tokens))
        return Action(streams=streams, recall=recall, sessions=sessions, order="LLF")


# ---------------------------------------------------------------- 10: D118, engine-native EDF
class VllmPriorityArm(Live2ArmMixin, NAIVE.AlwaysCloudFCFS):
    """Arm 10 (D118, BUILT AND IN NO RUN until the user decides): engine-native EDF.

    Why it exists. A reviewer will ask "isn't this just vLLM with priority scheduling?". This arm
    is that question made measurable: its RELEASE behaviour is identical to `always-cloud-fcfs`,
    sending every opportunity immediately with no cap and no admission test, and the ONLY
    difference is that every action carries a priority equal to its absolute deadline in integer
    milliseconds. Any arm-side ordering would confound the answer, so there is none.

    vLLM v0.31.0 serves the lower priority value first and breaks ties by arrival time
    (`vllm/config/scheduler.py`: `SchedulerPolicy = Literal["fcfs", "priority"]`). IT ALSO
    PREEMPTS: `v1/core/sched/scheduler.py` picks its victim as
    `max(self.running, key=lambda r: (r.priority, r.arrival_time))` and `_preempt_request` frees
    that request's blocks and sets `num_computed_tokens = 0` before putting it back at the front
    of the waiting queue. So a preempted cold rebuild DISCARDS its prefill and recomputes it,
    which is why engine-native priority is not automatically the stronger scheduler here.

    The priority never reaches a request body from this file. It is published in
    `Action.notes["priority_ms"]`, and the one-line backend change that copies it into the body is
    written down in the report section "H100 wiring for vllm-priority" rather than applied, since
    the backend is not ours to edit.
    """

    name = "vllm-priority"
    case = "own"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "recall_decision", "order")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action",
                     "engine_config")
    live2_source = ("baselines/naive.py::AlwaysCloudFCFS release behaviour AS COMMITTED, plus a "
                    "per-action vLLM priority equal to the absolute deadline in integer ms "
                    "(D118); requires --scheduling-policy priority")
    requires_server_mode = "priority"

    def __init__(self) -> None:
        self._server_mode: Optional[str] = None
        self._has_backend: bool = False
        self.stats: Dict[str, Any] = dict(arm=self.name, requires_server_mode="priority",
                                          server_scheduling_policy=None,
                                          server_mode_undeclared=True, priorities_emitted=0)

    def reset(self, seed: int = 0) -> None:
        pass

    def live2_configure(self, **kw: Any) -> None:
        """Reads the declared server mode. `Live2ArmMixin.live2_configure` already takes **kw, so
        a runner that knows nothing about priority scheduling passes nothing and changes."""
        super().live2_configure(**kw)
        mode = kw.get("server_scheduling_policy")
        self._server_mode = str(mode) if mode is not None else None
        self._has_backend = bool(kw.get("has_backend", False))
        self.stats["server_scheduling_policy"] = self._server_mode
        self.stats["server_mode_undeclared"] = self._server_mode is None

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._live2_roster = roster

    def live2_describe(self) -> Dict[str, Any]:
        d = super().live2_describe()
        d["requires_server_mode"] = self.requires_server_mode
        d["server_scheduling_policy"] = self._server_mode
        return d

    def _check_server_mode(self) -> None:
        """It must never silently run as plain FCFS and be reported as if the engine had ordered.

        A declared mode that is not `priority` is refused outright. A run that declares nothing is
        a dry run or a test, where no engine serves anything and FCFS is not a risk, so it
        proceeds and is STAMPED `server_mode_undeclared` in the run header. The strict check
        against a real server is the pre-send assertion in the report's H100 wiring section,
        because the backend is not ours to edit.
        """
        if self._server_mode is not None and self._server_mode != "priority":
            raise RuntimeError(
                "vllm-priority refuses to run: the run declares the server scheduling policy as "
                "%r, not 'priority'. Start the server with --scheduling-policy priority, or run "
                "an arm that does not depend on engine-side ordering. Running as FCFS would "
                "report engine-native EDF numbers that no engine ordered."
                % (self._server_mode,))
        if self._has_backend and self._server_mode is None:
            raise RuntimeError(
                "vllm-priority refuses to run: a backend is attached but no server scheduling "
                "policy was declared, so it cannot be shown that the engine is in priority mode. "
                "Pass server_scheduling_policy='priority' to live2_configure.")

    @staticmethod
    def _priority_ms(deadline_abs: float) -> int:
        """vLLM takes an int64; lower is served first. The absolute deadline in ms from run
        start IS the EDF key, so handing it to the engine is exactly 'let vLLM do EDF'."""
        return int(round(float(deadline_abs) * 1000.0))

    def decide(self, obs: Observation) -> Action:
        self._check_server_mode()
        act = super().decide(obs)

        instants = (getattr(self, "_live2_roster", None) or {}).get("sh_instant", {})
        tgt = getattr(self, "_targets", None)
        mon_l_s = float(tgt["dashcam"]["L_s"]) if tgt else 1.0
        pri: Dict[str, int] = {}
        for s in obs.streams:
            inst = instants.get(s.stream_id)
            if inst is not None:
                dl = float(inst["deadline_abs"])
            else:
                last = (s.delivered_times_s[-1] if s.delivered_times_s
                        else obs.now_s - s.cadence_s)
                dl = last + s.cadence_s + mon_l_s
            pri["mon:" + s.stream_id] = self._priority_ms(dl)
        by_session: Dict[str, int] = {}
        for q in obs.recall:
            p = self._priority_ms(q.deadline_s)
            pri["rc:" + q.query_id] = p
            # A rebuild needed by a recall carries THE RECALL'S deadline, so the engine does not
            # defer the build behind the answer that depends on it. The nearest deadline wins if
            # two questions share a session.
            if q.session_id not in by_session or p < by_session[q.session_id]:
                by_session[q.session_id] = p
        for sa in act.sessions:
            sid = getattr(sa, "session_id", None)
            if sid in by_session:
                pri["session:" + str(sid)] = by_session[sid]

        notes = dict(act.notes or {})
        notes["priority_ms"] = pri
        notes["vllm_scheduling_policy"] = self._server_mode
        notes["priority_semantics"] = "absolute deadline in ms from run start; lower served first"
        self.stats["priorities_emitted"] = int(self.stats["priorities_emitted"]) + len(pri)
        return Action(streams=act.streams, recall=act.recall, sessions=act.sessions,
                      engine_config=act.engine_config, order="ENGINE-PRIORITY", notes=notes)


# ---------------------------------------------------------------- 7, 8: the constructed arms
class UtilityPerCostArm(Live2ArmMixin, CONS.B8UtilityPerGPUSecond):
    """Arm 7."""

    live2_source = "baselines/constructed.py::B8UtilityPerGPUSecond AS COMMITTED"

    def __init__(self, *a: Any, **kw: Any) -> None:
        CONS.B8UtilityPerGPUSecond.__init__(self, *a, **kw)
        self.name = "utility-per-cost"


class B9Arm(Live2ArmMixin, CONS.B9BestOfBreed):
    """Arm 8. B9 AS COMMITTED (amendment 2's A4b / A5b already applied), plus the run loop
    honouring DEFER (D90). No other change: nothing in this subclass overrides `decide`."""

    live2_source = ("baselines/constructed.py::B9BestOfBreed AS COMMITTED (amendment 2, "
                    "A4b / A5b applied); DEFER honoured by the run loop (D90)")

    def __init__(self, *a: Any, **kw: Any) -> None:
        CONS.B9BestOfBreed.__init__(self, *a, **kw)
        self.name = "b9"


ARMS = {
    "device-only": DeviceOnlyArm,
    "always-cloud-fcfs": AlwaysCloudFcfsArm,
    "edf": lambda **kw: Pi0Edf(None, **kw),
    "edf-piece1024": lambda **kw: Pi0Edf(1024, **kw),
    "edf-piece2048": lambda **kw: Pi0Edf(2048, **kw),
    "utility-per-cost": UtilityPerCostArm,
    "b9": B9Arm,
    # D118, BUILT AND IN NO RUN until the user decides. Registering them here does not put them
    # in any run plan: `ARM_NAMES` is read only by the `--arm` CLI choices and by the three
    # all-arm tests, no sweep driver reads it (the pilot drivers list their arms explicitly), and
    # the scorer's `GPU_BASELINES` is a separate seven-tuple with a committed `len == 7` test.
    # Only the WHOLE variant of llf is named; `llf-piece<n>` is reachable by parameter.
    "llf": lambda **kw: LlfArm(None, **kw),
    "vllm-priority": VllmPriorityArm,
}


# D129 v1.3-fast release. The configuration the night's evidence selected, named so the H100
# driver can ask for it by one string instead of carrying ten keyword arguments. It is
# `policy-core` with the v1.1 defect fixes and the v1.2 two-timescale planner on, the price of
# GPU time set to ZERO, and the admission floor at 8.
#
# WHY mu = 0 and not a price. The directive's cheap diagnostic was decisive: at 8 devices mu = 0
# gives 8 of 20 robot answers and 0.9330 dashcam against the EWMA's 1 of 20 and 0.7998, better on
# BOTH axes. A graded scarcity price, verified to vary over 0.5 to 0.889 with nothing at a cap,
# still gives 0 of 20 and 0.5803 at 16 devices. Pricing predicted backlog at all is worse than
# not pricing it, which is a real negative and not an absent mechanism.
#
# THIS DOES NOT BEAT THE BASELINES EVERYWHERE and is released as the best found, per D129. At 16
# devices it delivers 14 of 35 robot answers against edf-at-8's 4 and llf's 6, and loses dashcam,
# 0.8164 against 0.9508 and 0.9633. At 8 devices it loses both. The leaderboard row says so.
V13_RELEASE = dict(cost_model="pol4", h_s=0.5, impl="fast",
                   mu_mode="none", mu_fixed=None,
                   deficit_update=True, honour_job_priority=True, realistic_competing=True,
                   planner_rc=True, plan_latest=True, replan=True,
                   admit_floor_c=8, release_floor_c=0,
                   kappa=None)


def make_arm(name: str, **kw: Any) -> Policy:
    if name in ("covex-v2", "covex-v2-fast"):
        from arms_covex_v2 import CovexV2Arm
        return CovexV2Arm(**kw)
    if name in ("covex-v13", "policy-core-v13"):
        from arms_policy import PolicyCoreArm
        cfg = dict(V13_RELEASE)
        cfg.update(kw)
        return PolicyCoreArm(**cfg)
    if name == "policy-core":
        from arms_policy import PolicyCoreArm
        return PolicyCoreArm(**kw)
    f = ARMS.get(name)
    if f is None:
        raise KeyError(f"unknown arm {name!r}; known: {sorted(list(ARMS) + ['policy-core'])}")
    # D128: parameters must reach the constructed arm, or "C_inflight = 4 stays reachable by
    # parameter" is not true. Before this, kwargs were silently DISCARDED for every non-policy
    # arm, so `make_arm("edf", c_inflight=4)` quietly returned the DEFAULT arm and any cell
    # labelled c4 was really the default. Arms that take no parameters still work.
    try:
        return f(**kw) if kw else f()
    except TypeError:
        if kw:
            raise TypeError("arm %r does not accept %s" % (name, sorted(kw)))
        raise


# The eight arms of the round-1 list (D65 as corrected by D90). D118's `llf` and
# `vllm-priority` are BUILT AND IN NO RUN, so they are registered as buildable below but are NOT
# part of this tuple's round-1 meaning; the scorer's own `GPU_BASELINES` is unchanged.
ROUND1_ARM_NAMES = ("policy-core", "device-only", "always-cloud-fcfs", "edf", "edf-piece1024",
                    "edf-piece2048", "utility-per-cost", "b9")
ARM_NAMES = ROUND1_ARM_NAMES + ("llf", "vllm-priority")

# D130: the StudyB published-system baselines, ported in `arms_published.py`. They are EXTRA
# buildable arms, not round-1 arms: `ROUND1_ARM_NAMES` and the scorer's seven-arm
# `GPU_BASELINES` are both untouched. Imported at the bottom so `arms_published` can import
# `Live2ArmMixin` from here without a cycle.
from arms_published import PUBLISHED_ARMS, UPPER_BOUND_ARMS            # noqa: E402
ARMS.update(PUBLISHED_ARMS)
ARM_NAMES = ARM_NAMES + tuple(sorted(PUBLISHED_ARMS))
# D138 user ruling. Constructible by name, deliberately NOT in ARM_NAMES: these declare
# `reads_future` and the coordinator refuses them under fairness rule 5, so they are not runnable
# and must appear neither as a `--arm` choice nor in the all-arm fairness tests. ARM_NAMES means
# "arms live2 can run"; this registry means "documented, not scored". See `arms_published.py`.
ARMS.update(UPPER_BOUND_ARMS)

# D133: the modular builder's screen conditions, one explicit name per condition so the
# existing audit harness can select them by `arm_name` without name parsing.
from arms_builder import BUILDER_ARMS                                   # noqa: E402
ARMS.update(BUILDER_ARMS)
ARM_NAMES = ARM_NAMES + tuple(sorted(BUILDER_ARMS))

# D150 / StudyV5-ENGINE: the WARM-ALL + LRU calibration arms. Registered in ARMS so `make_arm`
# resolves them without the caller importing arms_warmall first, and imported LAST for the same
# reason as the two blocks above (it imports from arms.py, so an earlier import would cycle).
# Deliberately NOT added to ARM_NAMES: these are calibration instruments, not round-1 arms, and
# `warm-all-lru` cannot yet make its own characteristic decision (see reports/study_engine_actions.md).
from arms_warmall import WARMALL_ARMS                                   # noqa: E402
ARMS.update(WARMALL_ARMS)

# D155 (5) / StudyKV-PREFETCH: the KV-cache baselines' own published proactive mechanisms, now that
# PATCH 1 makes warming ahead expressible. Imported LAST for the same reason as the blocks above.
# Deliberately NOT added to ARM_NAMES: these are new labelled arms under D79, not round-1 arms, and
# the committed no-prefetch cells must stay the comparison until they are rerun.
from arms_kvprefetch import KVPREFETCH_ARMS                             # noqa: E402
ARMS.update(KVPREFETCH_ARMS)

# StudyV5-RULES: the RULES-ONLY v5 arm, `hybrid-F-lhreq-noc3` plus warm-ahead as a rule (D150
# STATE lever 1, D152 (3), spec v5 sections 4 and 8). Imported LAST for the same reason as the
# blocks above (it imports from arms.py, so an earlier import would cycle). Deliberately NOT added
# to ARM_NAMES: it is a new labelled arm under D79, not a round-1 arm. It must never be read as
# full v5, which D154 (2) blocks until the D151 (6) gate passes and MARGIN_CF is set; `v5-rules`
# makes no counterfactual prediction and so needs neither.
from arms_v5rules import V5RULES_ARMS                                   # noqa: E402
ARMS.update(V5RULES_ARMS)

# D160: v5-rules-2 is v5-rules with its two DESIGN flaws fixed, which the user classed as design
# changes and not bugs. Warming happens in CHUNKS on a session's unwarmed tail (D160 (1), replacing
# the withdrawn D152 (3) per-frame prefill, which coupled upload to warming against D150 SYNC (1)
# and made warming cost scale with request count), and a SATURATION GUARD on live engine feedback
# sheds background warming first (D160 (2), replacing the bare W2 yield, which never fired in
# 12,001 epochs; the diagnosis is in `reports/study_v5rules2_design.md`). Imported last for the
# same cycle reason as the blocks above, and deliberately NOT in ARM_NAMES for the same reason
# `v5-rules` is not: a new labelled arm under D79, never to be read as full v5.
from arms_v5rules2 import V5RULES2_ARMS                                 # noqa: E402
ARMS.update(V5RULES2_ARMS)
