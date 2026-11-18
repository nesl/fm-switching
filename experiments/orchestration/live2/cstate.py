#!/usr/bin/env python3
"""The coordinator's own state, and the `interface.Observation` every arm sees. CPU only.

StudyLIVE2-coord. This module holds no policy: it is the bookkeeping the arms read and the
coordinator charges.

WHAT IS LIVE HERE, AND WHERE IT COMES FROM

| observation field | live source |
|---|---|
| `streams[]` | one stream per DASHCAM device; `delivered_scores` is what the application has received (a cloud answer when its request completed, the device's own answer otherwise) |
| `streams[].cadence_s`, `frame_count`, `on_cloud` | the coordinator's current setting for that device |
| `recall[]` | robot recall questions that have arrived, are not yet answered, and are not withheld by a DEFER |
| `recall[].readiness` | the coordinator's believed tier for that session's history |
| `recall[].readiness_tokens` | the session's history size in tokens, from the fleet's `est_tokens` |
| `cloud.queued_by_class`, `running_by_class` | the coordinator's in-flight bookkeeping, cross-checked against `/metrics` |
| `cloud.gpu_kv_fraction` | the server's `vllm:gpu_cache_usage_perc` |
| `cloud.gpu_warm_sessions`, `host_warm_sessions` | the believed tiers |
| `cloud.latency_estimate_s` | an EWMA of MEASURED TTFTs of completed requests, per class |
| `budget_remaining_gpu_s` | the harness's budget, identical for every arm |

CAPACITIES ARE INPUTS (D56, D76): `gpu_kv_tokens` and `host_tier_gib` arrive on the command line
and are passed to every arm that uses them. Nothing here hard-codes a capacity.
"""
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/baselines/reconstructed"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib"),
           str(ROOT / "experiments/dashcam")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import (CloudState, EpisodicStream, EvidenceItem, NetworkState,  # noqa: E402
                       Observation, RecallQuery)

try:
    sys.path.insert(0, str(HERE / "fleet"))
    from data_sources import D2_HEADER_TOK, D2_TOK_PER_IMG         # noqa: E402
except Exception:                                                   # noqa: BLE001
    D2_TOK_PER_IMG, D2_HEADER_TOK = 90, 31                          # StudyRH4, same values

EWMA = 0.3
RECENT_WINDOW_TOKENS = 467          # StudyF4 Part A median input size at N = 1
GIB = 1024 ** 3

# D71 as amended by D82. Passed to every arm identically and never changed per arm.
TARGETS = dict(
    dashcam=dict(L_s=1.0, p=0.25, scope="per_device", min_opportunities=200),
    robot=dict(L_s=5.0, p=0.90, scope="pooled", min_opportunities=20),
)


def host_tokens_from_gib(host_tier_gib: float, bytes_per_token: float) -> int:
    return int(host_tier_gib * GIB / max(bytes_per_token, 1e-9))


@dataclass
class DeviceRec:
    device_id: str
    type: str
    uplink_mbps: float
    rtt_ms: float
    start_t: float
    salt: str = ""
    cadence_s: float = 0.5
    frame_count: int = 1
    on_cloud: bool = True
    delivered: deque = field(default_factory=lambda: deque(maxlen=40))
    sessions: List[str] = field(default_factory=list)
    frame_bytes: int = 0


@dataclass
class SessionRec:
    session_id: str
    device_id: str
    frames: List[str] = field(default_factory=list)       # every frame_ref on cloud-side disk
    sent_bytes_for: set = field(default_factory=set)      # frames whose BYTES the engine saw
    est_tokens: int = 0
    open: bool = True
    built_tokens: int = 0
    belief: Dict[str, float] = field(default_factory=lambda: {"gpu": 0.0, "host": 0.0,
                                                              "cold": 1.0})
    desired_tier: str = "cold"
    last_telemetry_cached_tokens: Optional[int] = None

    def believed_tier(self) -> str:
        return max(self.belief, key=lambda k: self.belief[k])

    def readiness(self) -> str:
        return {"gpu": "GPU-WARM", "host": "HOST-WARM", "cold": "COLD"}[self.believed_tier()]


@dataclass
class Opportunity:
    # D96: `opp_id` IS the trace generator's opportunity_id, copied unchanged. The coordinator
    # never constructs, derives or parses one; `instant_id` and `question_id` are kept beside it
    # because they are what the device and the recordings call the same thing.
    opp_id: str
    device_id: str
    kind: str                       # monitor | recall
    t_event: float                  # t_capture for monitoring, t_ask for recall
    deadline_s: float               # the bound, measured from t_event
    t_arrive: Optional[float] = None
    session_id: Optional[str] = None
    frame_ref: Optional[str] = None
    frame_bytes: int = 0
    question: Optional[str] = None
    options: List[str] = field(default_factory=list)
    state: str = "offered"          # offered | arrived | in_flight | answered | declined | late
    defer_until: float = -1.0
    n_defers: int = 0
    instant_id: Optional[str] = None
    question_id: Optional[str] = None
    pulled_at: Optional[float] = None
    served_at: Optional[float] = None
    cache_path: Optional[str] = None

    def deadline_abs(self) -> float:
        return self.t_event + self.deadline_s

    def slack_s(self, now: float) -> float:
        return self.deadline_abs() - now


@dataclass
class CoordState:
    gpu_kv_tokens: int
    host_tier_gib: float
    host_tier_tokens: int
    upload_mode: str = "A"
    now: float = 0.0
    devices: Dict[str, DeviceRec] = field(default_factory=dict)
    sessions: Dict[str, SessionRec] = field(default_factory=dict)
    opps: Dict[str, Opportunity] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)          # arrival order of opportunities
    in_flight: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    lat: Dict[str, float] = field(default_factory=lambda: {"episodic": 0.0, "recall": 0.0})
    metrics: Dict[str, float] = field(default_factory=dict)
    budget: Any = None
    targets: Dict[str, Any] = field(default_factory=lambda: dict(TARGETS))
    counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # ---- fleet events
    def register(self, ev: Dict[str, Any], salt: str) -> DeviceRec:
        d = DeviceRec(device_id=ev["device_id"], type=ev["type"],
                      uplink_mbps=float(ev["uplink_mbps"]), rtt_ms=float(ev["rtt_ms"]),
                      start_t=float(ev["start_t"]), salt=salt)
        self.devices[d.device_id] = d
        return d

    def session_start(self, ev: Dict[str, Any]) -> SessionRec:
        s = SessionRec(session_id=ev["session_id"], device_id=ev["device_id"])
        self.sessions[s.session_id] = s
        self.devices[ev["device_id"]].sessions.append(s.session_id)
        return s

    def session_end(self, ev: Dict[str, Any]) -> None:
        s = self.sessions.get(ev["session_id"])
        if s is None:
            return
        s.open = False
        # D56: the KV may be released, the FRAMES STAY. "cold" is rebuild-from-frames, not delete.
        s.belief = {"gpu": 0.0, "host": 0.0, "cold": 1.0}
        s.built_tokens = 0

    def history_append(self, ev: Dict[str, Any]) -> SessionRec:
        s = self.sessions.get(ev["session_id"])
        if s is None:
            s = self.session_start(dict(device_id=ev["device_id"],
                                        session_id=ev["session_id"], t=ev["t_arrive"]))
        s.frames.extend(ev["frame_refs"])
        s.est_tokens = max(int(ev["est_tokens"]), s.est_tokens) if ev.get("est_tokens") \
            else len(s.frames) * D2_TOK_PER_IMG + D2_HEADER_TOK
        return s

    def monitor_offer(self, ev: Dict[str, Any]) -> Opportunity:
        o = Opportunity(opp_id=ev["opportunity_id"], device_id=ev["device_id"], kind="monitor",
                        t_event=float(ev["t_capture"]), deadline_s=float(ev["deadline_s"]),
                        frame_bytes=int(ev["frame_bytes"]), state="offered",
                        instant_id=ev["instant_id"])
        self.devices[o.device_id].frame_bytes = o.frame_bytes
        self._add(o)
        return o

    def monitor_frame(self, ev: Dict[str, Any]) -> Opportunity:
        o = self.opps.get(ev["opportunity_id"])
        if o is None:
            o = Opportunity(opp_id=ev["opportunity_id"], device_id=ev["device_id"],
                            kind="monitor", t_event=float(ev["t_capture"]),
                            deadline_s=float(ev["deadline_s"]),
                            instant_id=ev["instant_id"])
            self._add(o)
        o.t_arrive = float(ev["t_arrive"])
        o.frame_ref = ev["frame_ref"]
        o.frame_bytes = int(ev["frame_bytes"])
        self.devices[o.device_id].frame_bytes = o.frame_bytes
        if o.state in ("offered", "arrived"):
            o.state = "arrived"
        return o

    def recall_question(self, ev: Dict[str, Any]) -> Opportunity:
        o = Opportunity(opp_id=ev["opportunity_id"], device_id=ev["device_id"], kind="recall",
                        t_event=float(ev["t_ask"]), deadline_s=float(ev["deadline_s"]),
                        t_arrive=float(ev["t_arrive"]), session_id=ev["session_id"],
                        question=ev["question"], options=list(ev["options"] or []),
                        state="arrived", question_id=ev["question_id"])
        self._add(o)
        return o

    def _add(self, o: Opportunity) -> None:
        if o.opp_id in self.opps:
            raise ValueError(f"duplicate opportunity id {o.opp_id!r}")
        self.opps[o.opp_id] = o
        self.order.append(o.opp_id)

    # ---- views
    def visible(self, now: float) -> Tuple[List[Opportunity], List[Opportunity]]:
        """(monitor, recall) opportunities an arm may act on now: arrived, undecided, not
        withheld by a DEFER (amendment 2, D90), not past their deadline."""
        mon, rec = [], []
        for oid in self.order:
            o = self.opps[oid]
            if o.state not in ("arrived", "offered"):
                continue
            if o.defer_until > now + 1e-9:
                continue
            if o.deadline_abs() < now - 1e-9:
                continue
            (mon if o.kind == "monitor" else rec).append(o)
        return mon, rec

    def dashcams(self) -> List[DeviceRec]:
        return [d for d in self.devices.values() if d.type == "dashcam"]

    def session_of_device(self, device_id: str) -> Optional[SessionRec]:
        for sid in reversed(self.devices[device_id].sessions):
            s = self.sessions.get(sid)
            if s is not None and s.open:
                return s
        return None

    def ewma(self, cls: str, v: Optional[float]) -> None:
        if v is None:
            return
        self.lat[cls] = v if self.lat.get(cls, 0.0) <= 0 else EWMA * v + (1 - EWMA) * self.lat[cls]

    def traffic_mix(self) -> Dict[str, int]:
        """D63: the mix in flight at submit time."""
        return {k: int(self.in_flight.get(k, 0)) for k in ("monitor", "piece", "whole", "recall")}

    # ---- the observation every arm sees
    def observation(self, now: float, epoch: str, reads_device_answer: bool = False
                    ) -> Observation:
        mon, rec = self.visible(now)
        by_dev: Dict[str, Opportunity] = {}
        for o in mon:
            by_dev.setdefault(o.device_id, o)
        streams = []
        for d in self.dashcams():
            streams.append(EpisodicStream(
                stream_id=d.device_id,
                delivered_scores=tuple(v for _t, v in d.delivered),
                delivered_times_s=tuple(round(t, 3) for t, _v in d.delivered),
                cadence_s=d.cadence_s, frame_count=d.frame_count, on_cloud=d.on_cloud,
                network=NetworkState(connected=True, uplink_bps=d.uplink_mbps * 1e6 / 8.0,
                                     rtt_s=d.rtt_ms / 1000.0)))
        queries = []
        for o in rec:
            s = self.sessions.get(o.session_id)
            if s is None:
                continue
            tok = max(int(s.est_tokens), 1)
            ready = s.readiness()
            ev = (EvidenceItem("RECENT", "device", RECENT_WINDOW_TOKENS,
                               RECENT_WINDOW_TOKENS * 4),
                  EvidenceItem("D2", "gpu" if ready == "GPU-WARM" else
                               ("host" if ready == "HOST-WARM" else "device"), tok, tok * 4))
            queries.append(RecallQuery(
                query_id=o.opp_id, session_id=o.session_id, category="recall",
                arrival_s=round(o.t_arrive if o.t_arrive is not None else o.t_event, 3),
                deadline_s=round(o.deadline_abs(), 3), evidence=ev, readiness=ready,
                readiness_tokens=tok,
                device_answer_confidence=None))
        gpu = tuple(sorted(k for k, v in self.sessions.items() if v.believed_tier() == "gpu"))
        host = tuple(sorted(k for k, v in self.sessions.items() if v.believed_tier() == "host"))
        cloud = CloudState(
            queued_by_class=dict(recall=len(queries),
                                 episodic=int(self.metrics.get("vllm:num_requests_waiting",
                                                               self.in_flight.get("monitor", 0)))),
            running_by_class=dict(recall=int(self.in_flight.get("recall", 0)
                                             + self.in_flight.get("piece", 0)
                                             + self.in_flight.get("whole", 0)),
                                  episodic=int(self.in_flight.get("monitor", 0))),
            gpu_kv_fraction=float(self.metrics.get("vllm:gpu_cache_usage_perc", 0.0)),
            host_kv_fraction=self._host_fraction(), gpu_warm_sessions=gpu,
            host_warm_sessions=host, latency_estimate_s=dict(self.lat))
        return Observation(now_s=round(now, 3), epoch=epoch, streams=tuple(streams),
                           recall=tuple(queries), cloud=cloud,
                           budget_remaining_gpu_s=(self.budget.remaining_gpu_s()
                                                   if self.budget is not None else 0.0))

    def _host_fraction(self) -> float:
        if self.host_tier_tokens <= 0:
            return 0.0
        used = sum(s.est_tokens for s in self.sessions.values()
                   if s.believed_tier() == "host")
        return min(used / float(self.host_tier_tokens), 1.0)
