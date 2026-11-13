#!/usr/bin/env python3
"""The policy interface every baseline in this suite is called through.

StudyB-baselines. CPU only: nothing here runs a model or touches a GPU.

Design rules this module enforces, not merely documents:

1. **Causal observations only.** An `Observation` carries what a scheduler could know at the
   decision epoch. It is frozen, and the fields that could leak the future (labels, correctness,
   future arrivals) are simply absent. `scrub()` additionally asserts that nothing a caller
   attached privately has smuggled them in.
2. **One action space.** Every policy returns an `Action`; `validate_action` rejects a cadence,
   frame count, representation, readiness or deadline that is not in the registered domain. A
   baseline that decides only part of the space leaves the rest `None` and `apply_defaults` fills
   it from `DEFAULTS`, which is the SAME for every baseline and is documented in each card.
3. **One budget.** `Budget` is checked by the harness, not by the policy, so a baseline cannot
   quietly award itself more cloud work than our scheduler gets.

Nothing in this file encodes a preference between baselines. It is deliberately dumb: the
scheduling intelligence lives in the policy modules, and the measured cost curves live in
`costs.py`.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- domains
CADENCES_S: Tuple[float, ...] = (0.25, 0.5, 1.0)
FRAME_COUNTS: Tuple[int, ...] = (1, 3)
REPRESENTATIONS: Tuple[str, ...] = ("RECENT", "RICH", "D2")
READINESS: Tuple[str, ...] = ("COLD", "HOST-WARM", "GPU-WARM")
SESSION_ACTIONS: Tuple[str, ...] = ("KEEP_GPU_WARM", "OFFLOAD_TO_HOST", "EVICT", "MATERIALIZE")
STREAM_MODES: Tuple[str, ...] = ("local", "cloud", "suspend")
# StudyB-baselines amendment 2026-11-12. MATERIALIZE(session, target_tokens, slice_tokens) builds a
# session's cloud-side state up to `target_tokens`. `slice_tokens = None` means ONE MONOLITHIC
# PREFILL, which is the only option every pre-amendment baseline can express; that restriction is
# the PROPERTY UNDER TEST (fairness rule 4), not a defect of those baselines, and a policy that
# chains slices must declare it. The per-slice overhead is NOT a measured quantity: StudySIM1
# sweeps it and every slicing result is labelled parametric until StudySLICE1 measures it.
MATERIALIZE_MONOLITHIC = None
SLICING_IS_THE_PROPERTY_UNDER_TEST = (
    "slice_tokens = None (one monolithic prefill) is what every baseline written before the "
    "2026-11-12 amendment can express. A baseline that chains slices is exercising the property "
    "under test and must say so in its card.")
RECALL_ACTIONS: Tuple[str, ...] = ("DEVICE", "CLOUD", "DEFER", "REJECT")
EPOCH_KINDS: Tuple[str, ...] = (
    "stream_arrival", "stream_departure", "recall_arrival", "request_completion",
    "connectivity_change", "tick",
)

# Fixed, documented defaults for any part of the action space a baseline does not decide.
# Every card states which of these its baseline relies on.
DEFAULTS: Dict[str, Any] = dict(
    episodic_mode="cloud",          # overridden per baseline
    cadence_s=0.5,
    frame_count=1,
    recall_decision="CLOUD",
    representation="RECENT",
    defer_s=0.0,
    session_action="OFFLOAD_TO_HOST",   # LRU-ordered by the harness
    order="FCFS",
    engine_config="default",
)

# Field names a policy must never see. Kept as a check, not a comment.
FORBIDDEN_FIELDS = (
    "label", "labels", "y", "y_true", "ground_truth", "correct", "correctness",
    "is_positive", "time_of_event", "time_of_alert", "future", "future_arrivals",
    "arrivals_ahead", "oracle", "benefit", "utility_true", "answer",
)


# ---------------------------------------------------------------- observation
@dataclass(frozen=True)
class NetworkState:
    connected: bool
    uplink_bps: float
    rtt_s: float


@dataclass(frozen=True)
class EpisodicStream:
    """One standing video query. `delivered_scores` is what the APPLICATION has seen, i.e. the
    device's sample-and-held score stream of StudyE9b, never the compute-time stream."""
    stream_id: str
    delivered_scores: Tuple[float, ...]      # oldest -> newest, application-visible only
    delivered_times_s: Tuple[float, ...]     # grid times of those scores
    cadence_s: float
    frame_count: int
    on_cloud: bool
    network: NetworkState

    def latest_score(self) -> Optional[float]:
        return self.delivered_scores[-1] if self.delivered_scores else None


@dataclass(frozen=True)
class EvidenceItem:
    """One representation of one session's history, and where it currently lives."""
    representation: str                      # in REPRESENTATIONS
    tier: str                                # "device" | "host" | "gpu"
    tokens: int
    bytes_: int


@dataclass(frozen=True)
class RecallQuery:
    query_id: str
    session_id: str
    category: str                            # StudyE6 / S-EMBER question category
    arrival_s: float
    deadline_s: float
    evidence: Tuple[EvidenceItem, ...]       # inventory, by tier
    readiness: str                           # in READINESS, for this session on the cloud
    readiness_tokens: int
    device_answer_confidence: Optional[float] = None   # StudyD13 logprob, if the device answered

    def slack_s(self, now_s: float) -> float:
        return self.deadline_s - now_s


@dataclass(frozen=True)
class CloudState:
    queued_by_class: Dict[str, int]
    running_by_class: Dict[str, int]
    gpu_kv_fraction: float
    host_kv_fraction: float
    gpu_warm_sessions: Tuple[str, ...]
    host_warm_sessions: Tuple[str, ...]
    latency_estimate_s: Dict[str, float]     # class -> recent estimate from the measured curves


@dataclass(frozen=True)
class Observation:
    now_s: float
    epoch: str                               # in EPOCH_KINDS
    streams: Tuple[EpisodicStream, ...]
    recall: Tuple[RecallQuery, ...]
    cloud: CloudState
    budget_remaining_gpu_s: float
    # The device is always warm for its own history: a fixed design assumption, not an observation.
    device_always_warm: bool = True

    def __post_init__(self) -> None:
        if self.epoch not in EPOCH_KINDS:
            raise ValueError(f"unknown epoch {self.epoch!r}")


def scrub(obs: Observation) -> Observation:
    """Assert that no forbidden field reached the policy. Cheap, and run on every epoch in the
    smoke tests: a leak is a silent correctness bug otherwise."""
    def check(o: Any, path: str) -> None:
        if dataclasses.is_dataclass(o):
            for f in dataclasses.fields(o):
                if f.name.lower().strip("_") in FORBIDDEN_FIELDS:
                    raise AssertionError(f"forbidden field {path}.{f.name}")
                check(getattr(o, f.name), f"{path}.{f.name}")
        elif isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and k.lower().strip("_") in FORBIDDEN_FIELDS:
                    raise AssertionError(f"forbidden key {path}[{k!r}]")
                check(v, f"{path}[{k!r}]")
        elif isinstance(o, (tuple, list)):
            for i, v in enumerate(o):
                check(v, f"{path}[{i}]")
    check(obs, "obs")
    return obs


# ---------------------------------------------------------------- action
@dataclass
class StreamAction:
    stream_id: str
    mode: str                                # in STREAM_MODES
    cadence_s: Optional[float] = None
    frame_count: Optional[int] = None
    # mode == "suspend": issue no cloud call until this wall time; the application uses the
    # DEVICE's scores meanwhile (StudyE9d's SUSPEND mode, whose cost that study measured).
    suspend_until_s: Optional[float] = None


@dataclass
class RecallAction:
    query_id: str
    decision: str                            # in RECALL_ACTIONS
    representation: Optional[str] = None
    defer_s: Optional[float] = None


@dataclass
class SessionAction:
    session_id: str
    action: str                              # in SESSION_ACTIONS
    # action == "MATERIALIZE" only:
    target_tokens: Optional[int] = None      # how much of the session's history to build
    slice_tokens: Optional[int] = None       # None = one monolithic prefill (see above)


@dataclass
class Action:
    streams: List[StreamAction] = field(default_factory=list)
    recall: List[RecallAction] = field(default_factory=list)
    sessions: List[SessionAction] = field(default_factory=list)
    engine_config: Optional[str] = None
    order: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)


def materialize(session_id: str, target_tokens: int,
                slice_tokens: Optional[int] = MATERIALIZE_MONOLITHIC) -> SessionAction:
    """The explicit act of BUILDING a session's cloud-side state, as against KEEP_GPU_WARM, which
    only keeps state that already exists. A baseline whose paper prefetches or eagerly warms says
    so with this; the harness charges the build at the measured cold-prefill cost either way, so
    wiring a baseline to it changes what the baseline DECLARES, not what it is charged."""
    return SessionAction(session_id, "MATERIALIZE", target_tokens=int(target_tokens),
                         slice_tokens=slice_tokens)


def suspend_stream(stream_id: str, until_s: float) -> StreamAction:
    """SUSPEND_UNTIL(t): issue no cloud call for this stream until t; the application uses the
    device's own scores meanwhile. StudyE9d measured what that costs (its SUSPEND mode)."""
    return StreamAction(stream_id, "suspend", suspend_until_s=float(until_s))


def apply_defaults(action: Action) -> Action:
    """Fill every field the baseline left undecided from DEFAULTS. Identical for all baselines."""
    for s in action.streams:
        if s.mode == "cloud":
            if s.cadence_s is None:
                s.cadence_s = DEFAULTS["cadence_s"]
            if s.frame_count is None:
                s.frame_count = DEFAULTS["frame_count"]
    for r in action.recall:
        if r.decision == "CLOUD" and r.representation is None:
            r.representation = DEFAULTS["representation"]
        if r.decision == "DEFER" and r.defer_s is None:
            r.defer_s = DEFAULTS["defer_s"]
    if action.order is None:
        action.order = DEFAULTS["order"]
    if action.engine_config is None:
        action.engine_config = DEFAULTS["engine_config"]
    return action


def validate_action(action: Action, obs: Observation) -> Action:
    """Reject anything outside the registered domain, and anything that names an entity the
    observation did not contain (which is how a policy would smuggle in knowledge of the future)."""
    sids = {s.stream_id for s in obs.streams}
    qids = {q.query_id for q in obs.recall}
    known_sessions = (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                      | {q.session_id for q in obs.recall})
    seen = set()
    for s in action.streams:
        if s.stream_id not in sids:
            raise ValueError(f"action names unknown stream {s.stream_id!r}")
        if s.stream_id in seen:
            raise ValueError(f"two actions for stream {s.stream_id!r}")
        seen.add(s.stream_id)
        if s.mode not in STREAM_MODES:
            raise ValueError(f"bad mode {s.mode!r}")
        if s.mode == "suspend":
            if s.suspend_until_s is None or s.suspend_until_s <= obs.now_s + 1e-9:
                raise ValueError("suspend_until_s must be in the future")
            if s.cadence_s is not None or s.frame_count is not None:
                raise ValueError("a suspended stream issues no cloud call, so it has no cadence "
                                 "or frame count")
        if s.mode != "suspend" and s.suspend_until_s is not None:
            raise ValueError("suspend_until_s is only meaningful with mode 'suspend'")
        if s.mode == "cloud":
            if s.cadence_s not in CADENCES_S:
                raise ValueError(f"cadence {s.cadence_s!r} not in {CADENCES_S}")
            if s.frame_count not in FRAME_COUNTS:
                raise ValueError(f"frame count {s.frame_count!r} not in {FRAME_COUNTS}")
    seen = set()
    for r in action.recall:
        if r.query_id not in qids:
            raise ValueError(f"action names unknown query {r.query_id!r}")
        if r.query_id in seen:
            raise ValueError(f"two actions for query {r.query_id!r}")
        seen.add(r.query_id)
        if r.decision not in RECALL_ACTIONS:
            raise ValueError(f"bad recall decision {r.decision!r}")
        if r.decision == "CLOUD" and r.representation not in REPRESENTATIONS:
            raise ValueError(f"bad representation {r.representation!r}")
        if r.decision == "DEFER" and not (r.defer_s is not None and r.defer_s >= 0):
            raise ValueError("defer_s must be >= 0")
    for x in action.sessions:
        if x.action not in SESSION_ACTIONS:
            raise ValueError(f"bad session action {x.action!r}")
        if x.session_id not in known_sessions:
            raise ValueError(f"action names unknown session {x.session_id!r}")
        if x.action == "MATERIALIZE":
            if not (isinstance(x.target_tokens, int) and x.target_tokens > 0):
                raise ValueError("MATERIALIZE needs a positive target_tokens")
            if x.slice_tokens is not None and not (isinstance(x.slice_tokens, int)
                                                   and x.slice_tokens > 0):
                raise ValueError("slice_tokens must be None (monolithic) or a positive int")
        elif x.target_tokens is not None or x.slice_tokens is not None:
            raise ValueError(f"target_tokens / slice_tokens are only meaningful with "
                             f"MATERIALIZE, not {x.action!r}")
    return action


# ---------------------------------------------------------------- budget
@dataclass
class Budget:
    """The same budget every baseline and our scheduler get. Enforced by the harness."""
    gpu_seconds: float
    uplink_bytes: Optional[float] = None
    spent_gpu_seconds: float = 0.0
    spent_uplink_bytes: float = 0.0

    def remaining_gpu_s(self) -> float:
        return self.gpu_seconds - self.spent_gpu_seconds

    def can_spend(self, gpu_s: float, byte_s: float = 0.0) -> bool:
        if self.spent_gpu_seconds + gpu_s > self.gpu_seconds + 1e-9:
            return False
        if self.uplink_bytes is not None and \
                self.spent_uplink_bytes + byte_s > self.uplink_bytes + 1e-9:
            return False
        return True

    def spend(self, gpu_s: float, byte_s: float = 0.0) -> None:
        if not self.can_spend(gpu_s, byte_s):
            raise RuntimeError("budget exceeded")
        self.spent_gpu_seconds += gpu_s
        self.spent_uplink_bytes += byte_s


# ---------------------------------------------------------------- policy
class Policy:
    """Base class. `name` and `case` are used by the registry and the report.

    A baseline overrides `decide` only. It must not keep any state that a real scheduler could
    not keep (anything derived from a later epoch), and the smoke harness replays epochs in time
    order so that such state cannot be built accidentally.
    """

    name: str = "unnamed"
    case: str = "?"                 # "naive" | "A" | "B" | "C" | "D" | "constructed" | "own"
    paper: Optional[str] = None
    decides: Tuple[str, ...] = ()   # which parts of the action space this baseline decides
    defaults_used: Tuple[str, ...] = ()
    # ---- fairness declarations (addendum rules 1-6); `check_fairness` validates them
    models: Tuple[str, ...] = ("4BI", "32BI")
    experiments: Tuple[str, ...] = ()          # in EXPERIMENTS
    multi_instance_adapted: bool = False       # rule 2: the original spans many replicas
    reads_future: bool = False                 # rule 5
    restricts_action_space: Optional[str] = None   # rule 4
    restriction_reason: Optional[str] = None

    def reset(self, seed: int = 0) -> None:
        """Called once before a replay."""

    def decide(self, obs: Observation) -> Action:
        raise NotImplementedError

    # Not overridden by baselines.
    def __call__(self, obs: Observation) -> Action:
        return validate_action(apply_defaults(self.decide(scrub(obs))), obs)


# ================================================================ fairness rules (addendum)
# These are enforced here and in the smoke harness, and every card restates them.
FAIRNESS_RULES = {
    1: "Same models and evidence: the device tier is 4BI, the cloud tier is 32BI, every policy "
       "sees the same observation, and no externally trained VLM may be substituted. Enforced by "
       "`validate_action` (no model field exists in the action space) and by `check_fairness`, "
       "which rejects a policy declaring a model outside MODELS.",
    2: "Same resources: ONE H100 replica. A multi-instance algorithm must be adapted and LABELLED "
       "as such via `Policy.multi_instance_adapted = True`; the action space has no instance "
       "dimension, so a policy cannot route across replicas.",
    3: "Same state accounting: every policy pays synchronisation, upload, cache construction, "
       "GPU/host occupancy, recomputation and INITIAL WARMING. Cloud-only gets no free history. "
       "Enforced by the harness, which charges a session's first promotion to GPU-warm at the "
       "measured cold-prefill cost and charges uplink bytes per episodic cloud call.",
    4: "Same feasible actions and deadlines, unless restricting the action space IS the property "
       "being tested - in which case the policy must declare `restricts_action_space` with a "
       "reason, which the harness records. Since the 2026-11-12 amendment the action space also "
       "holds MATERIALIZE(session, target_tokens, slice_tokens) and per-stream SUSPEND_UNTIL(t). "
       "Every baseline written before the amendment can express only slice_tokens = None (one "
       "monolithic prefill), and that is recorded as the PROPERTY UNDER TEST rather than as a "
       "restriction those baselines chose.",
    5: "No future knowledge except the oracle: `scrub()` on every epoch, and any policy that "
       "reads the future must declare `reads_future = True` and is excluded from the causality "
       "check and from every deployable comparison.",
    6: "Identical demand traces, seeds, deadlines and bootstrap units across policies: the harness "
       "builds the trace once from a fixed seed and asserts the digest is identical for every "
       "policy it runs.",
}
MODELS = ("4BI", "32BI")
EXPERIMENTS = ("A-episodic", "B-recall", "C-mixed")


def check_fairness(policy: "Policy") -> Dict[str, Any]:
    """Static checks a policy must pass before the harness will run it (rules 1, 2, 4, 5)."""
    out: Dict[str, Any] = {}
    bad = [m for m in getattr(policy, "models", MODELS) if m not in MODELS]
    if bad:
        raise AssertionError(f"rule 1: policy {policy.name!r} names non-suite models {bad}")
    out["rule1_models"] = list(getattr(policy, "models", MODELS))
    out["rule2_multi_instance_adapted"] = bool(getattr(policy, "multi_instance_adapted", False))
    r = getattr(policy, "restricts_action_space", None)
    if r and not getattr(policy, "restriction_reason", None):
        raise AssertionError(f"rule 4: policy {policy.name!r} restricts the action space without "
                             f"a stated reason")
    out["rule4_restricts"] = r
    out["rule4_reason"] = getattr(policy, "restriction_reason", None)
    out["rule5_reads_future"] = bool(getattr(policy, "reads_future", False))
    exps = getattr(policy, "experiments", ())
    bad = [e for e in exps if e not in EXPERIMENTS]
    if bad:
        raise AssertionError(f"policy {policy.name!r} claims unknown experiments {bad}")
    out["experiments"] = list(exps)
    return out
