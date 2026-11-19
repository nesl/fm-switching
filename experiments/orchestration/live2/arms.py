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
    C_INFLIGHT_DEFAULT = 4

    def __init__(self, piece_tokens: Optional[int] = None,
                 c_inflight: int = C_INFLIGHT_DEFAULT) -> None:
        self.piece_tokens = int(piece_tokens) if piece_tokens else None
        self.c_inflight = int(c_inflight)
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

    def decide(self, obs: Observation) -> Action:
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
        order = Rollout._edf(None, items)
        # D114: the head PREFIX, not the single head. Taking a prefix is what charges each
        # released unit against the bound within the period: the observation cannot see this
        # period's own submissions, so the arm counts the head items it releases itself.
        released = {p.item_id for p in order[:self._release_budget(obs)]}

        streams, recall, sessions = [], [], []
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
                # MATERIALIZE advances the build by ONE piece (CONTRACT.md), so a chained
                # rebuild needs one per epoch until the history is built; the coordinator
                # no-ops once it is. Issuing it once would build a single piece and leave the
                # chain unfinished, which is what arms 5 and 6 exist to exercise.
                sessions.append(materialize(q.session_id, max(q.readiness_tokens, 1),
                                            self.piece_tokens))
        return Action(streams=streams, recall=recall, sessions=sessions, order="EDF")


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
    "edf": lambda: Pi0Edf(None),
    "edf-piece1024": lambda: Pi0Edf(1024),
    "edf-piece2048": lambda: Pi0Edf(2048),
    "utility-per-cost": UtilityPerCostArm,
    "b9": B9Arm,
}


def make_arm(name: str, **kw: Any) -> Policy:
    if name == "policy-core":
        from arms_policy import PolicyCoreArm
        return PolicyCoreArm(**kw)
    f = ARMS.get(name)
    if f is None:
        raise KeyError(f"unknown arm {name!r}; known: {sorted(list(ARMS) + ['policy-core'])}")
    return f()


ARM_NAMES = ("policy-core", "device-only", "always-cloud-fcfs", "edf", "edf-piece1024",
             "edf-piece2048", "utility-per-cost", "b9")
