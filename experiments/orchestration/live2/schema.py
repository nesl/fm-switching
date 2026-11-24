#!/usr/bin/env python3
"""Shared fleet <-> coordinator interface for live round 1 (StudyLIVE2).

Authority: research/policy_design_log.md D56, D63, D69, D81, D83, D84 and
research/policy_spec_v4.md. This module is the single definition of the wire events, of the
coordinator's three log streams, and of the run header. It is owned by the coordinator session;
experiments/orchestration/live2/fleet/events.py keeps the fleet side's own copy and compares
itself against FIELDS here.

Times are SECONDS on ONE run clock, t = 0 at run start.

FLEET -> COORDINATOR
  device_register  {device_id, type: dashcam|robot, uplink_mbps, rtt_ms, start_t}
  session_start    {device_id, session_id, t}                         robots (D83)
  session_end      {device_id, session_id, t}                         robots (D83)
  monitor_offer    {device_id, opportunity_id, instant_id, t_capture, deadline_s,
                    frame_bytes}                                            mode B only
  monitor_frame    {device_id, opportunity_id, instant_id, t_capture, t_arrive, deadline_s,
                    frame_ref, frame_bytes, episode_id, episode_index, frame_refs,
                    episode_frames}                   mode A pushed; mode B after a pull
                    the four episode fields are D153's EP-G context and are absent by default
  history_preload  {device_id, session_id, frame_refs[], est_tokens, t}      robots (D101)
  history_append   {device_id, session_id, batch_id, t_arrive, frame_refs[], est_tokens}
  recall_question  {device_id, opportunity_id, session_id, question_id, t_ask, t_arrive,
                    deadline_s, question, options[]}

D101: a robot joins its first session PART-WAY, and at t = 0 the cloud already holds that
session's earlier frames as COLD history. `history_preload` is how the fleet declares them. No
uplink time is charged for a preload (the frames are already on cloud-side disk at run start);
the coordinator stores them as cold history exactly like an ingested batch (D56: frames on
disk, NO KV), so a later question still pays the cold rebuild. It carries no `batch_id` and no
`t_arrive`, because it is not a batch that arrived during the run; `t` is the run-clock instant
at which the holding is declared, which is 0.0 for a join-point preload.

D154 (4) / D150 SYNC (1): THE UPLOAD CONTRACT IS A PROPERTY OF THE TRACE AND NOT OF THIS
SCHEMA. A `history_append` carries one upload of a session's history, whatever packages it:
under the committed `batch-30s` contract that is a 30-s window's D2 frames (D68), and under
`per-frame` it is ONE FRAME, offered at its capture time, for ALL arms. The fields, their
meanings and the D2 token accounting are IDENTICAL in both - `est_tokens` is still the
session's CUMULATIVE history tokens after this append and `batch_id` is still the upload's
unique id - which is why neither this schema, the emulator, the coordinator nor any arm needed
a change. `fleet/trace.ROBOT_UPLOAD_NOTE` and `trace_meta.robot_upload` say which contract a
trace was built under.

D96: EVERY OPPORTUNITY CARRIES AN opportunity_id, UNIQUE WITHIN THE RUN AND ASSIGNED BY THE
TRACE GENERATOR. It is echoed unchanged into cloud_answer and into every log. THE COORDINATOR
NEVER CONSTRUCTS, DERIVES OR PARSES ONE: a bare instant_id or question_id is ambiguous once D84
allows a clip or a session to be replayed on more than one device, or twice on one device.

COORDINATOR -> FLEET
  pull_request     {device_id, instant_id, t_sent}
  cloud_answer     {device_id, opportunity_id, t_done, payload}

COORDINATOR LOGS (one JSONL file per stream per run)
  decision   one scheduler decision with its predictions (D63)
  request    one HTTP request to the engine with its outcome and cache path (D81)
  residency  one residency-belief sample against telemetry (D44, D47)
"""
# No `from __future__ import annotations`: fleet/events.py loads this file with
# importlib.util.spec_from_file_location WITHOUT registering it in sys.modules, and dataclasses
# cannot resolve string annotations for an unregistered module.
import json
import os
from dataclasses import MISSING, dataclass, field, asdict, fields as dc_fields
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional

SCHEMA_VERSION = "live2-schema-1"

# D136: "assistive" is a SINGLE-SHOT type, one image plus question and NO HISTORY.
DEVICE_TYPES = ("dashcam", "robot", "assistive")
UPLOAD_MODES = ("A", "B")
TIERS = ("gpu", "host", "cold")
CACHE_PATHS = ("WARM", "COLD")
OUTCOMES = ("both_met", "latency_miss", "quality_miss")

FLEET_TO_COORD = (
    "device_register",
    "session_start",
    "session_end",
    "history_preload",
    "monitor_offer",
    "monitor_frame",
    "history_append",
    "recall_question",
)
COORD_TO_FLEET = ("pull_request", "cloud_answer")

FIELDS: Dict[str, tuple] = {
    "device_register": ("device_id", "type", "uplink_mbps", "rtt_ms", "start_t"),
    "session_start": ("device_id", "session_id", "t"),
    "session_end": ("device_id", "session_id", "t"),
    "monitor_offer": ("device_id", "opportunity_id", "instant_id", "t_capture", "deadline_s",
                      "frame_bytes", "device_score"),
    "monitor_frame": ("device_id", "opportunity_id", "instant_id", "t_capture", "t_arrive",
                      "deadline_s", "frame_ref", "frame_bytes", "episode_id", "episode_index",
                      "frame_refs", "episode_frames", "device_score"),
    "history_preload": ("device_id", "session_id", "frame_refs", "est_tokens", "t"),
    "history_append": ("device_id", "session_id", "batch_id", "t_arrive", "frame_refs",
                       "est_tokens"),
    # `category` is the S-EMBER question category from the trace generator, added so the
    # coordinator can see which kind of question it is deciding about. Without it the policy
    # pinned one category for every accuracy lookup.
    "recall_question": ("device_id", "opportunity_id", "session_id", "question_id", "t_ask",
                        "t_arrive", "deadline_s", "question", "options", "category"),
    "pull_request": ("device_id", "instant_id", "t_sent"),
    "cloud_answer": ("device_id", "opportunity_id", "t_done", "payload"),
}

EVENT_FIELDS = FIELDS


# ---------------------------------------------------------------- wire events

@dataclass
class DeviceRegister:
    device_id: str
    type: str
    uplink_mbps: float
    rtt_ms: float
    start_t: float


@dataclass
class SessionStart:
    device_id: str
    session_id: str
    t: float


@dataclass
class SessionEnd:
    device_id: str
    session_id: str
    t: float


@dataclass
class MonitorOffer:
    device_id: str
    opportunity_id: str
    instant_id: str
    t_capture: float
    deadline_s: float
    frame_bytes: int
    device_score: Optional[float] = None


@dataclass
class MonitorFrame:
    # D153: the EPISODE fields carry the append-only episode context of D148, assigned by the
    # TRACE GENERATOR and independent of any arm's decisions. `frame_refs` is the episode's
    # frames oldest first, ending with `frame_ref`; `episode_index` is the index within the
    # refresh cycle. All four are absent on a one-frame trace, which is the default.
    device_id: str
    opportunity_id: str
    instant_id: str
    t_capture: float
    t_arrive: float
    deadline_s: float
    frame_ref: str
    frame_bytes: int
    episode_id: Optional[str] = None
    episode_index: Optional[int] = None
    frame_refs: Optional[List[str]] = None
    episode_frames: Optional[int] = None
    device_score: Optional[float] = None


@dataclass
class HistoryPreload:
    """D101: frames the cloud ALREADY HOLDS as cold history at run start.

    No uplink time is charged; the coordinator stores the frames on disk as cold history
    exactly like an ingested batch (D56), with NO KV.
    """
    device_id: str
    session_id: str
    frame_refs: List[str]
    est_tokens: int
    t: float


@dataclass
class HistoryAppend:
    device_id: str
    session_id: str
    batch_id: str
    t_arrive: float
    frame_refs: List[str]
    est_tokens: int


@dataclass
class RecallQuestion:
    device_id: str
    opportunity_id: str
    session_id: str
    question_id: str
    t_ask: float
    t_arrive: float
    deadline_s: float
    question: str
    options: List[str]
    category: Optional[str] = None


@dataclass
class PullRequest:
    device_id: str
    instant_id: str
    t_sent: float


@dataclass
class CloudAnswer:
    device_id: str
    opportunity_id: str
    t_done: float
    payload: Any


EVENT_CLASSES = {
    "device_register": DeviceRegister,
    "session_start": SessionStart,
    "session_end": SessionEnd,
    "monitor_offer": MonitorOffer,
    "monitor_frame": MonitorFrame,
    "history_preload": HistoryPreload,
    "history_append": HistoryAppend,
    "recall_question": RecallQuestion,
    "pull_request": PullRequest,
    "cloud_answer": CloudAnswer,
}

for _k, _c in EVENT_CLASSES.items():
    _want = tuple(f.name for f in dc_fields(_c))
    if _want != FIELDS[_k]:
        raise RuntimeError(f"schema.py internal mismatch for {_k}: {_want} vs {FIELDS[_k]}")
del _k, _c, _want


# Fields a caller MAY omit. `category` was added to `recall_question` for D134 and every
# pre-existing caller predates it, so requiring it would break them for a field that is
# genuinely optional: an event without a category simply carries None, which is what the
# coordinator saw before the field existed.
# D153: the four EPISODE fields on `monitor_frame` are optional in exactly the same sense.
# They are present only when the trace was generated with the EP-G dashcam format; a one-frame
# trace carries none of them and the coordinator then builds the committed StudyD3 body, which
# is what every caller before D153 did.
# D201: `device_score` is the DEVICE's own committed per-instant dashcam score for this
# instant, carried from the trace's answer table (`device_answers.jsonl`, written by
# `fleet/trace.py` out of StudyORIN1's dense per-instant set). It is OPTIONAL ON THE WIRE
# only so that a synthetic event builder with no committed score can still construct an
# event; it is NOT optional at the point of use. `coordinator._device_answer` RAISES when
# the field is absent or None, because the defect this field fixes survived for as long as
# it did precisely by substituting a neutral 0.0 for a score that was never fed.
OPTIONAL_FIELDS: Dict[str, tuple] = {
    "recall_question": ("category",),
    "monitor_frame": ("episode_id", "episode_index", "frame_refs", "episode_frames",
                      "device_score"),
    "monitor_offer": ("device_score",),
}


def make(kind: str, **kw: Any) -> Dict[str, Any]:
    """Build one wire event, rejecting a missing or unknown field outright."""
    want = FIELDS.get(kind)
    if want is None:
        raise KeyError(f"unknown event kind {kind!r}")
    opt = OPTIONAL_FIELDS.get(kind, ())
    missing = [f for f in want if f not in kw and f not in opt]
    extra = [f for f in kw if f not in want]
    if missing or extra:
        raise ValueError(f"{kind}: missing={missing} extra={extra}")
    if kind == "device_register" and kw["type"] not in DEVICE_TYPES:
        raise ValueError(f"device type {kw['type']!r} not in {DEVICE_TYPES}")
    EVENT_CLASSES[kind](**kw)
    return dict(kind=kind, **kw)


def parse(rec: Mapping[str, Any]):
    """Turn a wire dict back into its dataclass, rejecting anything off-schema."""
    kind = rec.get("kind")
    cls = EVENT_CLASSES.get(kind)
    if cls is None:
        raise KeyError(f"unknown event kind {kind!r}")
    body = {k: v for k, v in rec.items() if k != "kind"}
    want = FIELDS[kind]
    opt = OPTIONAL_FIELDS.get(kind, ())
    missing = [f for f in want if f not in body and f not in opt]
    extra = [f for f in body if f not in want]
    if missing or extra:
        raise ValueError(f"{kind}: missing={missing} extra={extra}")
    return cls(**body)


def to_wire(obj) -> Dict[str, Any]:
    for kind, cls in EVENT_CLASSES.items():
        if isinstance(obj, cls):
            return dict(kind=kind, **asdict(obj))
    raise TypeError(f"{type(obj).__name__} is not a live2 wire event")


# ---------------------------------------------------------------- coordinator logs

@dataclass
class Predicted:
    ttft_s: Optional[float] = None
    completion_s: Optional[float] = None
    imposed_delay_s_by_request: Dict[str, float] = field(default_factory=dict)


@dataclass
class Belief:
    gpu_tokens_by_session: Dict[str, int] = field(default_factory=dict)
    host_tokens_by_session: Dict[str, int] = field(default_factory=dict)
    cold_tokens_by_session: Dict[str, int] = field(default_factory=dict)


DECISION_KINDS = (
    "admit",
    "decline",
    "defer",
    "release_piece",
    "release_whole",
    "release_monitor",
    "release_recall",
    "pull",
    "state_action",
    "no_action",
)


@dataclass
class DecisionRecord:
    t: float
    arm: str
    arm_version: str
    decision_id: str
    kind: str
    opportunity_ids: List[str] = field(default_factory=list)
    piece_tokens: Optional[int] = None
    predicted: Dict[str, Any] = field(default_factory=lambda: asdict(Predicted()))
    cost_model_id: Optional[str] = None
    mu: Optional[float] = None
    H: Optional[float] = None
    belief: Dict[str, Any] = field(default_factory=lambda: asdict(Belief()))
    decision_latency_ms: Optional[float] = None
    traffic_mix: Dict[str, int] = field(default_factory=dict)
    defer_s: Optional[float] = None
    # D133/D134. Both are POLICY CHOICES that change what is sent and what is charged, and
    # neither was logged, so any proof that diffs decision rows was BLIND to them: an arm that
    # emitted RECENT on all 21 of its recalls showed 0 differing rows, and a placement mechanism
    # would read as inert however often it fired. `outcomes.jsonl` already carries the
    # representation; the decision log is where move-proofs look.
    representation: Optional[str] = None
    representation_defaulted: bool = False
    desired_tier: Optional[str] = None
    note: Optional[str] = None


@dataclass
class RequestRecord:
    request_id: str
    decision_id: Optional[str]
    device_id: str
    t_submit: float
    t_first_token: Optional[float]
    t_done: Optional[float]
    prompt_tokens: Optional[int]
    cached_tokens: Optional[int]
    cache_path: Optional[str]
    cached_fraction: Optional[float]
    output_tokens: Optional[int]
    http_status: Optional[int]
    cache_salt: Optional[str]
    session_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    mm_uuids: List[str] = field(default_factory=list)
    traffic_mix: Dict[str, int] = field(default_factory=dict)
    # D226 (3): a request still unfinished when the end-of-run drain gives up. Before this field
    # such a request was dropped with NO row at all (e.g. 2,257 of 10,138 in always-cloud-fcfs kv0.5 s4; a contiguous
    # late block of request ids); now it is written, marked, with no status and no tokens.
    abandoned: bool = False
    # D226 item 4 (logging only): on a request whose client raised, the exception type and repr and
    # the wall seconds from submit to failure; on every live request, whether its connection was
    # reused from the pool (None when the transport emitted no trace event).
    exc_type: Optional[str] = None
    exc_repr: Optional[str] = None
    exc_after_s: Optional[float] = None
    conn_reused: Optional[bool] = None
    # How a row came to exist when it was not written by normal completion (None for those):
    # "abandoned" (in flight at finish, NO delivered answer); "first_token_forwarded_stream_unfinished"
    # (answer delivered at first token, stream still open at finish; real first-token fields);
    # "completed_row_reconstructed" (written by the runner from outcomes.jsonl for a delivered answer
    # that had no row, user ruling 2026-11-24; http_status_inferred is then True).
    row_source: Optional[str] = None
    http_status_inferred: bool = False


@dataclass
class ResidencyRecord:
    t: float
    session_id: str
    believed_tier: str
    telemetry_cached_tokens: Optional[int]
    device_id: Optional[str] = None
    believed_dist: Dict[str, float] = field(default_factory=dict)


def cache_path_of(cached_tokens: Optional[int], prompt_tokens: Optional[int]):
    """D81: WARM iff the engine reports any cached tokens, with the fraction alongside."""
    if cached_tokens is None:
        return None, None
    path = "WARM" if cached_tokens > 0 else "COLD"
    frac = None
    if prompt_tokens:
        frac = float(cached_tokens) / float(prompt_tokens)
    return path, frac


# ---------------------------------------------------------------- run header

@dataclass
class RunHeader:
    git_commit: str
    arm: str
    arm_version: str
    flags: Dict[str, Any]
    gpu_kv_tokens: int
    host_tier_gib: float
    host_tier_tokens: Optional[int]
    cost_model_id: str
    cost_model_hash: str
    calibration_file: str
    calibration_label: str
    # D96: the canonical FAIRNESS DIGEST, the fleet's order-independent sha256 over sorted event
    # tuples (64 hex characters). The StudyLIVE1-port digest may appear ONLY under the name
    # live1_trace_digest, and a header must never present one as the other.
    fairness_digest: str
    trace_label: str
    seed: int
    targets: Dict[str, Any]
    upload_mode: str
    mu_mode: str
    mu_value: Optional[float]
    H: Optional[float]
    tick_s: float
    # D99 (1): the ONE decision period every arm decides on (100 ms in round 1), separate from
    # H, which is the rollout horizon only. `tick_s` is the same number under its old name.
    decision_period_s: float
    # D102: the GPU budget INPUT, identical for every arm; the default is one GPU's time over
    # the run (window_s x 1.0), which is the physical capacity and so never binds artificially.
    gpu_budget_s: float
    # D103 (f): the three fields the SCORER needs to label a comparison PRIMARY rather than
    # EXPLORATORY. They must be present under exactly these names: the memory SETTING as its
    # tight / roomy label (the GiB number is `host_tier_gib` alongside), the device ratio as a
    # "dashcam:robot" string, and the upload mode (`upload_mode` carries the same value under
    # its own name). A missing one silently makes every block-1 comparison exploratory.
    memory_setting: str
    ratio: str
    mode: str
    server_url: str
    server_kind: str
    model: str = "fake-32BI"
    live1_trace_digest: Optional[str] = None
    schema_version: str = SCHEMA_VERSION
    is_measurement: bool = False
    note: Optional[str] = None
    # D73: every placeholder setting, in the run header, each marked "not tuned".
    placeholders: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------- JSONL io

def _default(o):
    if hasattr(o, "__dataclass_fields__"):
        return asdict(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def write_jsonl(path, records: Iterable[Any], append: bool = False) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(p, "a" if append else "w") as fh:
        for r in records:
            fh.write(json.dumps(as_dict(r), default=_default, sort_keys=True) + "\n")
            n += 1
    return n


def as_dict(r: Any) -> Dict[str, Any]:
    if isinstance(r, dict):
        return r
    if hasattr(r, "__dataclass_fields__"):
        for kind, cls in EVENT_CLASSES.items():
            if isinstance(r, cls):
                return dict(kind=kind, **asdict(r))
        return asdict(r)
    raise TypeError(f"cannot serialize {type(r).__name__}")


def read_jsonl(path) -> List[Dict[str, Any]]:
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def iter_jsonl(path) -> Iterator[Dict[str, Any]]:
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


class JsonlWriter:
    """Line-buffered append writer; one per log stream per run."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", buffering=1)
        self.n = 0

    def write(self, rec: Any) -> None:
        self._fh.write(json.dumps(as_dict(rec), default=_default, sort_keys=True) + "\n")
        self.n += 1

    def flush(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def write_header(path, header: RunHeader) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        json.dump(asdict(header), fh, indent=2, sort_keys=True, default=_default)
        fh.write("\n")
    return p


def read_header(path) -> RunHeader:
    with open(path) as fh:
        d = json.load(fh)
    want = {f.name for f in dc_fields(RunHeader)}
    required = {f.name for f in dc_fields(RunHeader) if f.default is MISSING
                and f.default_factory is MISSING}
    missing = sorted(r for r in required if r not in d)
    extra = sorted(k for k in d if k not in want)
    if extra:
        raise ValueError(f"run header has unknown keys: {extra}")
    if missing:
        raise ValueError(f"run header missing keys: {missing}")
    return RunHeader(**d)
