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

# The committed device-answer confidence table, loaded once per process. It is MODULE level and
# not a CoordState attribute on purpose: CoordState is a dataclass, so an annotated class
# attribute there would silently become a dataclass FIELD and change its constructor signature.
_DEV_CONF_CACHE: Optional[Dict[str, float]] = None

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
    preloaded_tokens: int = 0     # D101: tokens the cloud already held, cold, at run start
    open: bool = True
    built_tokens: int = 0
    belief: Dict[str, float] = field(default_factory=lambda: {"gpu": 0.0, "host": 0.0,
                                                              "cold": 1.0})
    desired_tier: str = "cold"
    last_telemetry_cached_tokens: Optional[int] = None
    # D133 Part A. `desired_tier` was declared here with TWO WRITES and NO READ anywhere in live2,
    # so `KEEP_GPU_WARM` and `OFFLOAD_TO_HOST` were dispatched, counted, handled and INERT. These
    # three fields make placement observable and enactable.
    #
    # `measured_tier` is the RESIDENCY MODEL: where the KV actually is, as distinct from `belief`,
    # which is what the policy thinks. The required test has two halves and the second one is
    # "changes the measured tier", which needs a measured quantity that is not the belief.
    measured_tier: str = "cold"
    last_touch_s: float = 0.0
    placement_events: int = 0

    def believed_tier(self) -> str:
        return max(self.belief, key=lambda k: self.belief[k])

    def residency_readiness(self) -> str:
        """Readiness for COSTING: the committed belief, OVERRIDDEN only where placement moved the KV.

        D133 Part A. The first version read `measured_tier` directly, which LAGS the belief in one
        path and made recalls more expensive rather than less. `built_tokens` is increased in
        completion handling, and `_submit_recall` is also called from that same completion path,
        so a chained recall is costed BEFORE the next `observation()` has run `enact_placement`.
        There `measured_tier` is still "cold" while the belief has already promoted to GPU-WARM,
        and the recall was charged a full cold rebuild instead of a warm answer. Measured: 0 of 35
        recalls served and dashcam 0.0821 at 16 devices seed 0, against a committed 14 of 35 and
        0.8164.

        So residency OVERRIDES the belief only where a placement action actually moved the KV down
        to host. Everywhere else the committed belief-based readiness stands, which keeps the
        baseline exact while still charging offload and eviction for the first time.
        """
        if self.measured_tier == "host":
            return "HOST-WARM"
        return self.readiness()

    def tokens_for_representation(self, rep: Optional[str]) -> int:
        """How many tokens a recall actually sends for representation `rep`.

        D133 Part A second field. `RecallAction.representation` is written by arms, declared in
        `decides`, and READ NOWHERE: `_submit_recall` sends and charges `max(est_tokens, 1)`, the
        full believed history, whatever was asked for. So a RECENT-choosing arm pays full-history
        cost and earns full-history accuracy, and the two cannot be told apart.

        RECENT sends the recent window only, which is the committed `RECENT_WINDOW_TOKENS`; any
        other representation sends the whole history. The cap keeps a short history from being
        inflated by asking for RECENT.
        """
        whole = max(int(self.est_tokens), 1)
        if str(rep or "").upper() == "RECENT":
            return max(min(int(RECENT_WINDOW_TOKENS), whole), 1)
        return whole

    def set_tier(self, tier: str, now: float) -> bool:
        """Move the KV to `tier`, updating belief and the residency model together.

        Returns True if anything moved, so a caller can count real placement events rather than
        attempted ones. This is the ONE shared path: mooncake's reuse-first retention, kvflow's
        flow-aware residency, lmcache's offload, pensieve's eviction ordering and attentionstore's
        keep-warm all steer placement through it rather than through five separate mechanisms.
        """
        if tier not in ("gpu", "host", "cold"):
            raise ValueError("unknown tier %r" % (tier,))
        if self.measured_tier == tier:
            return False
        self.measured_tier = tier
        # The BELIEF is what the policy reads as readiness, and the committed semantics only
        # promote it on a COMPLETE build. Moving the belief for a partially built history would
        # tell an arm its history is HOST-WARM when it is a fragment, so the belief follows the
        # residency only once the history is whole. The residency moves either way.
        if self.built_tokens >= self.est_tokens and self.est_tokens > 0:
            self.belief = {"gpu": 0.0, "host": 0.0, "cold": 0.0}
            self.belief[tier] = 1.0
        self.last_touch_s = float(now)
        self.placement_events += 1
        return True

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

    # D133 Part A second field. `RecallAction.representation` is written by arms and read nowhere,
    # so it needs somewhere to live between the action loop and the submit path. The coordinator
    # sets this when it processes the action; `_submit_recall` reads it. See the report section
    # "H100 wiring for placement" for the exact two-line change.
    requested_representation: Optional[str] = None
    representation_defaulted: bool = False
    # The S-EMBER question category, carried from the trace. It was emitted by
    # `fleet/trace.py:421` as `category=q.category` all along and DROPPED here, which is why
    # `arms_policy` pinned a single type: the field the observation offers was documented as the
    # question category and filled with the literal "recall", so it carried no information.
    qtype: Optional[str] = None

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
        # D101: a robot joins its first session PART-WAY, and the `history_preload` that declares
        # the frames the cloud already holds can be ingested before the `session_start` that
        # marks the join (both carry t = 0, and the loop batches a period's events). A
        # session_start must therefore not wipe a cold history already declared for the same
        # session; it only re-opens it.
        prev = self.sessions.get(ev["session_id"])
        if prev is not None and prev.preloaded_tokens > 0:
            prev.open = True
            return prev
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

    def history_preload(self, ev: Dict[str, Any]) -> SessionRec:
        """D101: frames the cloud ALREADY HOLDS as cold history at run start.

        Identical to an ingested batch on the coordinator side (D56: frames on disk, no KV), so
        the first question on this session still pays a cold rebuild of the joined-into prefix.
        No uplink time is charged: the holding predates the run clock.
        """
        s = self.sessions.get(ev["session_id"])
        if s is None:
            s = self.session_start(dict(device_id=ev["device_id"],
                                        session_id=ev["session_id"], t=float(ev["t"])))
        s.frames.extend(ev["frame_refs"])
        # `est_tokens` is the session's CUMULATIVE history tokens after this event, so the
        # belief IS that value. The old `max(...)` was harmless here only because a preload is
        # the session's first holding; it is removed so one rule covers both producers.
        s.est_tokens = int(ev["est_tokens"])
        s.preloaded_tokens = int(ev["est_tokens"])
        s.belief = {"gpu": 0.0, "host": 0.0, "cold": 1.0}
        s.built_tokens = 0
        return s

    def history_append(self, ev: Dict[str, Any]) -> SessionRec:
        s = self.sessions.get(ev["session_id"])
        if s is None:
            s = self.session_start(dict(device_id=ev["device_id"],
                                        session_id=ev["session_id"], t=ev["t_arrive"]))
        s.frames.extend(ev["frame_refs"])
        # THE FIX (2026-11-18). This kept `max(batch, so_far)`, which on a stream of per-batch
        # increments leaves the belief at the LARGEST SINGLE BATCH rather than the running
        # total: 1,381 tokens for robo002's 17,581-token second session on the seed-10 trace.
        # `est_tokens` is now the session's CUMULATIVE total after this append (CONTRACT.md
        # "history size"), so the belief is that value, not a maximum and not a sum. The
        # fallback when the field is absent is unchanged and was already cumulative, being
        # derived from the frames accumulated so far.
        s.est_tokens = int(ev["est_tokens"]) if ev.get("est_tokens") \
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
                        state="arrived", question_id=ev["question_id"],
                        qtype=ev.get("category"))
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
    # D133 Part A: the placement switches. `placement_enacted` makes `desired_tier` READ and
    # enacted, which changes outcomes ONLY for arms that issue placement actions and leaves every
    # other arm byte-identical. `kv_capacity_enforced` additionally enforces `gpu_kv_tokens`,
    # which creates memory pressure for EVERY arm and would change every committed baseline at
    # once, so it is OFF by default and is decision PA-4.
    placement_enacted: bool = True
    kv_capacity_enforced: bool = False
    # D134: the SINGLE SWITCH for the question-category change, at the one boundary where the
    # value is populated. Off, every consumer downstream sees the literal "recall" exactly as
    # before; on, every consumer sees the real category. This exists because the change is NOT
    # confined to the policy: `baselines/constructed.py:96` branches on `cat in self.LONG` /
    # `cat in self.SHORT` and `baselines/naive.py:166` reads `class_share.get(q.category, ...)`,
    # so b7, b10 and the naive arms change behaviour too. Gating it per consumer would be
    # RECONSTRUCTING the before-state, which is what produced two invalid controls today; gating
    # it once here disables the whole change.
    category_enabled: bool = True

    def enact_placement(self, now: float) -> Dict[str, int]:
        """Read `desired_tier` and enact it. The one shared steering path (D133 Part A).

        Residency cannot be COMMANDED in vLLM (D44), so this STEERS: an offload request moves the
        KV down, a keep-warm request protects a session in eviction order and refreshes its touch
        time, and eviction order is what the capacity sweep consults. Nothing here pins a session
        on the GPU.
        """
        counts = {"offloaded": 0, "kept_warm": 0, "evicted": 0, "resident": 0}
        # D134 item 2 instrumentation. A PEAK and a SUSTAINED overage read identically in a table
        # and have opposite implications: a 120 per cent spike lasting one epoch means LRU evicts
        # and the history is re-materialised almost immediately, which is THRASHING and shows up
        # as cost without changing admission; a 105 per cent plateau lasting half the run means
        # histories genuinely stay cold. So the epoch count above cap and the duration of each
        # over-cap interval are recorded, not only the maximum.
        self.pressure = getattr(self, "pressure", None) or {
            "epochs": 0, "epochs_over_cap": 0, "peak_tokens": 0, "intervals": [],
            "_open": 0, "host_peak_tokens": 0, "host_epochs_over_cap": 0,
        }
        live = [x for x in self.sessions.values() if x.open and x.built_tokens > 0]
        # RESIDENCY IS NOT THE BELIEF, and this is the distinction decision PA-5 turns on. The
        # only write of `gpu` in live2 is in the coordinator's completion handling and requires a
        # COMPLETE build (`built_tokens >= est_tokens`), so a session with a partial prefix reads
        # as `cold` to the policy forever. But its prefill IS on the GPU: that is what makes the
        # next piece cheap. Measured at 10 devices, every session stayed `cold` and mooncake's 10
        # KEEP_GPU_WARM actions therefore had nothing to act on.
        #
        # So the residency model records the KV where it actually is, from the first built token,
        # independently of what the policy believes.
        for x in live:
            if x.measured_tier == "cold":
                x.measured_tier = "gpu"
                x.last_touch_s = float(now)
                counts["resident"] += 1
        # RESIDENCY IS PHYSICAL AND IS ALWAYS TRACKED. Only the STEERING below is switched, so
        # placement off against on is a clean comparison of the steering alone. Gating the
        # residency marking too would have left `measured_tier` at cold while costing read it,
        # which silently charged a warm history as a cold rebuild: measured as attentionstore
        # moving 8 of 10 to 9 of 10 for a reason that had nothing to do with placement.
        if not self.placement_enacted:
            return counts
        for x in live:
            if x.desired_tier == "host" and x.measured_tier == "gpu":
                if x.set_tier("host", now):
                    counts["offloaded"] += 1
            elif x.desired_tier == "gpu" and x.measured_tier == "gpu":
                # Steering, not commanding: refresh the touch so the capacity sweep below ranks
                # this session as recently wanted. It does NOT make it unevictable.
                x.last_touch_s = float(now)
                counts["kept_warm"] += 1
        # Residency is recorded EVERY epoch, whether or not enforcement is on, so the
        # time-above-cap series exists for the unenforced regime too and the two are comparable.
        on_gpu_all = [x for x in live if x.measured_tier == "gpu"]
        used_all = sum(int(x.built_tokens) for x in on_gpu_all)
        on_host = [x for x in live if x.measured_tier == "host"]
        host_used = sum(int(x.built_tokens) for x in on_host)
        p = self.pressure
        p["epochs"] += 1
        p["peak_tokens"] = max(p["peak_tokens"], used_all)
        p["host_peak_tokens"] = max(p["host_peak_tokens"], host_used)
        if int(self.host_tier_tokens) > 0 and host_used > int(self.host_tier_tokens):
            p["host_epochs_over_cap"] += 1
        over = int(self.gpu_kv_tokens) > 0 and used_all > int(self.gpu_kv_tokens)
        if over:
            p["epochs_over_cap"] += 1
            p["_open"] += 1
        elif p["_open"]:
            p["intervals"].append(p["_open"])
            p["_open"] = 0
        if self.kv_capacity_enforced and int(self.gpu_kv_tokens) > 0:
            on_gpu = on_gpu_all
            used = used_all
            cap = int(self.gpu_kv_tokens)
            if used > cap:
                # EVICTION ORDER, which is the third steering mechanism the cards describe.
                # Sessions asking to go to host go first; then least recently touched; a
                # keep-warm request sorts last and is therefore evicted only under real pressure.
                order = sorted(on_gpu, key=lambda x: (x.desired_tier == "gpu",
                                                      float(x.last_touch_s), x.session_id))
                for x in order:
                    if used <= cap:
                        break
                    if x.set_tier("host", now):
                        used -= int(x.built_tokens)
                        counts["evicted"] += 1
        return counts

    def _device_confidence(self, o) -> Optional[float]:
        """The committed DEVICE answer confidence for this opportunity, or None.

        User ruling 2026-11-20: the five cascade-style arms must receive what they declare. Before
        it, `observation` hard-coded this field to None, ignored its own `reads_device_answer`
        parameter, and the coordinator never passed that parameter, so an arm declaring
        `reads_device_answer` paid StudyD8's 0.567 s wait (coordinator.py, the two `reads_device`
        reads) and was handed None. See reports/study_ss2.md section 12.

        The value is the committed per-question table and nothing else
        (`baselines/device_confidence.py`: StudyE7 Job A `letter_probs` mass on the letter the 4B
        actually emitted, the harness's own DEVICE answer configuration). NOTHING IS SYNTHESIZED.

        Two failure modes are kept apart on purpose, because conflating them is the defect this
        fixes. A TABLE that cannot be loaded raises, because returning None then would reproduce
        the silent absence. A QUESTION absent from the table returns None and is counted: single
        shot questions have no committed answer probability at all (StudySS1 / StudySS2 ran greedy
        with no `logprobs`), so None is the honest value for them and every arm already handles it.
        """
        qid = getattr(o, "question_id", None)
        if qid is None:
            self.counts["device_conf_no_question_id"] = \
                self.counts.get("device_conf_no_question_id", 0) + 1
            return None
        global _DEV_CONF_CACHE
        if _DEV_CONF_CACHE is None:
            import device_confidence as DC          # on sys.path via run_live2_cell
            _DEV_CONF_CACHE = dict(DC._load_primary())
            if not _DEV_CONF_CACHE:
                raise RuntimeError(
                    "device_confidence's committed table is EMPTY; an arm declaring "
                    "reads_device_answer would be charged the device-answer wait and handed None "
                    "for every question, which is the defect this supplier exists to fix. "
                    "Check results/sember/study_e7/e7_requests_h100nvl.jsonl.")
        v = _DEV_CONF_CACHE.get(qid)
        if v is None:
            v = _DEV_CONF_CACHE.get(str(qid).lower())
        key = "device_conf_supplied" if v is not None else "device_conf_absent"
        self.counts[key] = self.counts.get(key, 0) + 1
        return v

    def observation(self, now: float, epoch: str, reads_device_answer: bool = False
                    ) -> Observation:
        # Placement is enacted BEFORE the observation is built, so an arm sees the tier its own
        # previous placement action produced (decision PA-1).
        self.enact_placement(now)
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
                query_id=o.opp_id, session_id=o.session_id,
                # `RecallQuery.category` is documented as the S-EMBER question category. It was
                # populated with the literal "recall", the OPPORTUNITY KIND, so the field was
                # correctly named, correctly documented, non-empty, and of the wrong kind.
                category=((o.qtype or "recall") if self.category_enabled else "recall"),
                arrival_s=round(o.t_arrive if o.t_arrive is not None else o.t_event, 3),
                deadline_s=round(o.deadline_abs(), 3), evidence=ev, readiness=ready,
                readiness_tokens=tok,
                device_answer_confidence=(self._device_confidence(o)
                                          if reads_device_answer else None)))
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
