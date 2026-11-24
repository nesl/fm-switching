#!/usr/bin/env python3
"""The LIVE adapter: every orchestrator-level arm, unchanged, driving a real server.

StudyLIVE1-port, part 2. CPU only in this file: it opens HTTP connections and never a model.

WHAT THIS IS. One loop that holds the SAME `baselines/interface.py` contract the simulator holds:
at every decision epoch it builds an `Observation` from LIVE state, calls the policy (which
validates its own `Action` through `interface.validate_action`), and enacts that action against a
backend. The arms are imported unchanged from `experiments/orchestration/baselines/`.

WHAT IS LIVE, AND WHERE IT COMES FROM.

| observation field | live source |
|---|---|
| `streams[].delivered_scores / _times_s` | the shape of what the APPLICATION receives (a cloud answer when its request completed, the device's own score otherwise) but **NOT ITS VALUES**: this harness has no per-instant score source wired, so every value is None = UNKNOWN. Until one is wired, NO SCORE-READING ARM MAY BE RUN HERE, and the seven that read these values RAISE rather than decide. Before D205 both writers put a literal `0.0` here, which is the MAXIMUM of log P(Yes) and made every one of them escalate on every instant. |
| `streams[].cadence_s`, `frame_count`, `on_cloud` | the orchestrator's own current setting for that stream |
| `cloud.queued_by_class`, `running_by_class` | the orchestrator's in-flight bookkeeping, cross-checked against the server's `/metrics` |
| `cloud.gpu_kv_fraction` | the server's KV-usage gauge, read under whichever name the engine emits (`vllm:kv_cache_usage_perc` on vLLM 0.31.0, `vllm:gpu_cache_usage_perc` on the older build and on `fake_server.py`) and republished under the older name so no reader changes. NEVER 0.0 by default: a failed fetch or an absent key is MARKED MISSING and served the last good value at most 1 s old, else UNKNOWN AND CONSERVATIVE (1.0). D209 (2). |
| `cloud.gpu_warm_sessions`, `host_warm_sessions` | the harness's own session bookkeeping |
| `cloud.latency_estimate_s` | an EWMA of the MEASURED TTFTs of completed requests, per class |
| `recall[].readiness`, `readiness_tokens` | the same bookkeeping |
| `recall[].device_answer_confidence` | committed per-question value, supplied ONLY to an arm declaring `reads_device_answer`, and the device answer is charged (StudyB-baselines amendment 2) |
| `budget_remaining_gpu_s` | the budget the harness meters, identical for every arm |

WHAT THE ORCHESTRATOR MAY NOT KNOW. It never sees the future schedule. It is given the
CADENCE-ONLY model of StudySLICE1 Part D-b - each stream's past arrivals, its cadence and a
jitter margin - exactly as `slice_rules.next_due_s` computes it, and `interface.scrub` runs on
every epoch, so a future field cannot reach a policy even by accident.

FAIRNESS, asserted rather than documented: the per-cell arrival trace is built once and its
sha256 is asserted identical for every arm; the server configuration is E0 unless the arm IS a
configuration; the budget, the cold sessions and the warm plan are the same for every arm.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import threading
import time
import urllib.request
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (HERE, ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/orchestration/baselines/reconstructed",
          ROOT / "experiments/orchestration/sim", ROOT / "experiments/lib",
          ROOT / "experiments/dashcam"):
    sys.path.insert(0, str(p))

import costs as C                                                     # noqa: E402
import device_confidence as DC                                        # noqa: E402
import slice_rules as SR                                              # noqa: E402
from interface import (Action, Budget, CloudState, EpisodicStream,     # noqa: E402
                       EvidenceItem, NetworkState, Observation, Policy, RecallQuery,
                       check_fairness)

DEVICE_RECALL_S = C.DEV_LAT_S          # StudyD8 arm A total p50; a RULE, not a device-recall
RECENT_WINDOW_TOKENS = 467             # StudyF4 Part A median input size at N = 1
EWMA = 0.3
E0 = "E0"                              # the server configuration every arm shares


# ---------------------------------------------------------------- the backend
@dataclass
class Submission:
    key: str
    kind: str                           # episodic | cold_recall | recall_escalation | ...
    tokens: int
    session: Optional[str]
    sent_s: float
    retain: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


class HttpBackend:
    """An OpenAI-compatible endpoint, driven with the standard library only.

    On the H100 the harness may inject its own client and its own BODY BUILDERS instead; this
    class exists so the whole loop can be exercised against the CPU stub with no dependencies.
    The body a real run must send is the committed one (`study_slice1_live.build_cold` for a cold
    build, `d3_infer_vllm.body` for an episodic call); here the body is a token-count placeholder
    and `fm_tokens` tells the stub how big it is.
    """

    def __init__(self, base_url: str, workers: int = 32, time_scale: float = 1.0,
                 model: str = "fake-32BI") -> None:
        self.base_url = base_url.rstrip("/")
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.time_scale = float(time_scale)
        self.model = model

    def post(self, sub: Submission) -> Dict[str, Any]:
        body = dict(model=self.model, stream=True, max_tokens=4,
                    messages=[dict(role="user", content="x")],
                    fm_kind=sub.kind, fm_tokens=int(sub.tokens),
                    fm_retain=bool(sub.retain), fm_time_scale=self.time_scale)
        req = urllib.request.Request(self.base_url + "/v1/chat/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        ttft = None
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    if raw.strip() and ttft is None:
                        ttft = time.time() - t0
                err = None
        except Exception as e:                                        # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        return dict(key=sub.key, kind=sub.kind, session=sub.session, tokens=sub.tokens,
                    sent_s=sub.sent_s, ttft_s=ttft, total_s=time.time() - t0, error=err,
                    meta=sub.meta)

    def submit(self, sub: Submission):
        return self.pool.submit(self.post, sub)

    def start_poller(self, interval_s: float = 0.2) -> None:
        """Poll /metrics in the background, so a decision epoch never waits on HTTP.

        The pre-first-poll value is UNKNOWN AND CONSERVATIVE, not `{}` (D209 (2)). `{}` here was a
        second route to the permissive 0.0, reached by any decision taken in the first poll
        interval, and it would have survived a fix that only touched the exception path.
        """
        # `fm_metrics_degraded` is 0.0 here on purpose: it is computed from the failure counters
        # and NO FETCH HAS HAPPENED YET, so nothing has failed. A reader that wants to know it is
        # holding a placeholder reads `fm_kv_state`, which says so by name.
        self._metrics: Dict[str, Any] = {
            self.KV_CANONICAL_KEY: float(self.KV_UNKNOWN_CONSERVATIVE),
            "fm_kv_state": "unknown_conservative_before_first_poll", "fm_kv_missing": 1.0,
            "fm_metrics_degraded": 0.0}
        self._stop = threading.Event()

        def loop():
            while not self._stop.is_set():
                self._metrics = self._fetch_metrics()
                self._stop.wait(interval_s)
        threading.Thread(target=loop, daemon=True).start()

    @property
    def metrics_failures(self) -> Dict[str, Any]:
        """How many metrics fetches failed, and the last exception type.

        The counter itself is the D205 commit (`29742254`) and is KEPT AS IT WAS, including the
        two key names `n` and `last` that any existing reader uses. D209 (2) adds the fields
        beside it that the counter alone could not supply: a failed fetch no longer substitutes a
        permissive value, so a run needs to say which value it used instead.
        """
        if not hasattr(self, "_metrics_failures"):
            self._metrics_failures: Dict[str, Any] = {
                "n": 0, "last": None,
                # D209 (2): what the DECISION was handed when a fetch failed or a key was absent
                "n_served_last_good": 0,     # a cached value at most LAST_GOOD_MAX_AGE_S old
                "n_served_unknown": 0,       # no usable recent value: UNKNOWN and CONSERVATIVE
                "n_kv_key_missing": 0,       # the scrape succeeded and carried no KV-usage key
                "n_kv_key_aliased": 0,       # served from the engine's current key name
                "kv_key_seen": None,         # which spelling this engine actually emits
            }
        return self._metrics_failures

    # ---- D209 (2): the missing-value policy for /metrics
    #
    # THE DEFECT. `_fetch_metrics` returned `{}` on a failed fetch, and `{}` makes every reader's
    # `m.get("vllm:gpu_cache_usage_perc", 0.0)` read 0.0 - the MINIMUM of [0, 1] and therefore the
    # MOST PERMISSIVE value an admission gate can be handed - silently. `_observation` below and
    # `live2/cstate.py:663` both read it, and it reaches `arms_v6cf.py:306`,
    # `engine_actions.py:288` (`free = (1 - frac) * pool`) and four baselines as a gate.
    #
    # AND A SECOND, WORSE PATH TO THE SAME 0.0, found by the D209 (4) probe: THE KEY NAME IS WRONG.
    # vLLM 0.31.0+cu129 emits `vllm:kv_cache_usage_perc` (0.7215 at capture) and NO
    # `vllm:gpu_cache_usage_perc`, so on a PERFECTLY SUCCESSFUL scrape the gate still read 0.0, on
    # every cell, by an absent key rather than by an exception. Two in-repo witnesses already use
    # the current spelling - `experiments/cost/study_r5_fleet.py` and `experiments/cost/
    # study_x_vllm.py` both read `vllm:kv_cache_usage_perc` - so this is the live2/live path alone
    # carrying the pre-rename name, not an open question about which name is right. Fixing only
    # the exception path would have left the gate reading 0.0 for ever and would have looked like
    # a pass, which is why both are fixed here together. Raw scrape:
    # `results/orchestration/live2/frozen_test/engine_probe_hit26/metrics_scrape_h100.txt`.
    #
    # THE POLICY (D209 (2)). A failed fetch NEVER substitutes 0.0.
    #   1. the KV fraction is MARKED MISSING, never defaulted;
    #   2. the decision uses the LAST GOOD VALUE if it is at most LAST_GOOD_MAX_AGE_S old;
    #   3. otherwise capacity is UNKNOWN AND CONSERVATIVE: `KV_UNKNOWN_CONSERVATIVE` = 1.0, the
    #      MAXIMUM of [0, 1], which every reader of this field treats as full pressure. Checked
    #      rather than assumed at each read site: `engine_actions.hold_back` computes
    #      `free = max(1 - frac, 0) * pool`, so 1.0 gives free = 0 and the hold-back fires;
    #      `preble_adapted.py:57` and `constructed.py:416` take `max(frac, ...)`, so 1.0 is the
    #      pressure end of both. An unknown is never permissive, in either direction;
    #   4. the cell RECORDS THE COUNT, in `metrics_failures` above, split by which of 2 and 3 it
    #      got; and
    #   5. the run is FLAGGED through `metrics_health()`, whose `degraded` field is the cell flag.
    #
    # WHY A dict SUBCLASS AND NOT A NEW RETURN TYPE. Every reader reaches this through
    # `m.get(key, default)`, and several of them live in files this session does not own
    # (`live2/cstate.py`, `live2/arms_v6cf.py`, four baselines). A mapping that already carries
    # the right value for the key they ask for fixes all of them without an edit to any of them,
    # and `fm_*` fields beside it carry the marking a reader that WANTS to know can read.
    KV_KEYS = ("vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc")
    KV_CANONICAL_KEY = "vllm:gpu_cache_usage_perc"
    KV_UNKNOWN_CONSERVATIVE = 1.0
    LAST_GOOD_MAX_AGE_S = 1.0

    def metrics(self) -> Dict[str, Any]:
        # Dict[str, Any] and not Dict[str, float] since D209 (2): the mapping now carries the
        # `fm_kv_*` MARKING beside the gauges, and `fm_kv_state` is a string. Every reader asks
        # for one named numeric key and coerces it, and `AsyncLive2Backend.metrics()` already
        # returns Any-valued entries into the same `cstate.CState.metrics` field, so this is the
        # honest annotation rather than a widening.
        if hasattr(self, "_metrics"):
            return self._metrics
        return self._fetch_metrics()

    def metrics_health(self) -> Dict[str, Any]:
        """The cell flag. `degraded` is true for ANY cell in which a fetch failed or a KV key was
        absent, so no such cell can be read as clean (D209 (2) requirement 5)."""
        c = dict(self.metrics_failures)
        degraded = bool(c["n"] or c["n_kv_key_missing"] or c["n_served_last_good"]
                        or c["n_served_unknown"])
        return {"metrics_degraded": degraded, "metrics_failures": c,
                "kv_unknown_conservative_value": self.KV_UNKNOWN_CONSERVATIVE,
                "last_good_max_age_s": self.LAST_GOOD_MAX_AGE_S,
                "policy": ("D209 (2): a failed fetch or an absent KV key never substitutes 0.0; "
                           "the last good value at most %.1f s old, else UNKNOWN and CONSERVATIVE "
                           "(%.1f)" % (self.LAST_GOOD_MAX_AGE_S, self.KV_UNKNOWN_CONSERVATIVE))}

    def _kv_fraction_from(self, scraped: Dict[str, float]) -> Tuple[Optional[float], str]:
        """The KV fraction this scrape carries, under whichever name the engine uses, or None.

        None is MISSING, and it is returned rather than a number so the caller must choose a
        policy. That is the whole point: `.get(key, 0.0)` made that choice invisibly.
        """
        c = self.metrics_failures
        for i, k in enumerate(self.KV_KEYS):
            if k in scraped:
                c["kv_key_seen"] = k
                if i:
                    c["n_kv_key_aliased"] = int(c["n_kv_key_aliased"]) + 1
                return float(scraped[k]), k
        return None, ""

    def _fetch_metrics(self) -> Dict[str, Any]:
        """Scrape /metrics, and never hand a decision a permissive default (D209 (2)).

        The returned mapping always carries `KV_CANONICAL_KEY`, so every reader's
        `m.get("vllm:gpu_cache_usage_perc", 0.0)` gets a REAL, a LAST-GOOD or a CONSERVATIVE
        value, and the `fm_kv_*` fields beside it say which. The 0.0 default is now unreachable
        for that key, which is the behaviour change this method exists to make.
        """
        c = self.metrics_failures
        failed: Optional[str] = None
        scraped: Dict[str, float] = {}
        try:
            with urllib.request.urlopen(self.base_url + "/metrics", timeout=5) as r:
                txt = r.read().decode()
        except Exception as e:                                        # noqa: BLE001
            failed = type(e).__name__
            c["n"] = int(c.get("n", 0)) + 1
            c["last"] = failed
            txt = ""
        for line in txt.splitlines():
            if line.startswith("#") or " " not in line:
                continue
            name, _, val = line.rpartition(" ")
            key = name.split("{")[0]
            try:
                scraped[key] = float(val)
            except ValueError:
                pass

        out: Dict[str, Any] = dict(scraped)
        kv, seen = self._kv_fraction_from(scraped)
        now = time.time()
        if kv is not None:
            self._kv_last_good = (float(kv), now)
            out[self.KV_CANONICAL_KEY] = float(kv)
            out["fm_kv_state"] = "observed"
            out["fm_kv_source_key"] = seen
            out["fm_kv_age_s"] = 0.0
        else:
            if failed is None:
                # the scrape succeeded and carried neither spelling: still a MISSING value, and
                # the same 0.0 if it were defaulted, so it takes the same policy
                c["n_kv_key_missing"] = int(c["n_kv_key_missing"]) + 1
            last = getattr(self, "_kv_last_good", None)
            age = (now - last[1]) if last else None
            if last is not None and age is not None and age <= self.LAST_GOOD_MAX_AGE_S:
                c["n_served_last_good"] = int(c["n_served_last_good"]) + 1
                out[self.KV_CANONICAL_KEY] = float(last[0])
                out["fm_kv_state"] = "last_good"
                out["fm_kv_age_s"] = round(float(age), 4)
            else:
                c["n_served_unknown"] = int(c["n_served_unknown"]) + 1
                out[self.KV_CANONICAL_KEY] = float(self.KV_UNKNOWN_CONSERVATIVE)
                out["fm_kv_state"] = "unknown_conservative"
                out["fm_kv_age_s"] = (round(float(age), 4) if age is not None else None)
            out["fm_kv_missing"] = 1.0
            out["fm_metrics_fetch_error"] = failed
        out["fm_metrics_degraded"] = 1.0 if self.metrics_health()["metrics_degraded"] else 0.0
        return out

    def close(self) -> None:
        if hasattr(self, "_stop"):
            self._stop.set()
        self.pool.shutdown(wait=False)


# ---------------------------------------------------------------- live state
@dataclass
class StreamState:
    stream_id: str
    cadence_s: float = 0.5
    frame_count: int = 1
    on_cloud: bool = True
    suspend_until_s: float = -1.0
    # D205: `delivered` is the APPLICATION-VISIBLE stream and `delivered_device` is the DEVICE's
    # own, exactly as live2/cstate.py splits them. `device_score_unknown` counts instants that
    # arrived with no committed score; one is enough to make the device channel unusable, and
    # `_observation` then hands the arm None so that a score reader raises.
    delivered: deque = field(default_factory=lambda: deque(maxlen=40))   # (t, score or None)
    delivered_device: deque = field(default_factory=lambda: deque(maxlen=40))
    device_score_unknown: int = 0
    last_issue_s: float = -1.0


@dataclass
class SessionState:
    session_id: str
    tokens: int
    tier: str = "cold"                   # cold | host | gpu
    built: bool = False


class LiveOrchestrator:
    """One cell, one arm. Real time, real HTTP, the policy unchanged."""

    def __init__(self, policy: Policy, backend: HttpBackend, trace, *, tick_s: float = 0.25,
                 speed: float = 1.0, window_s: Optional[float] = None, drain_s: float = 30.0,
                 seed: int = 0, engine_config: str = E0,
                 device_latency_s: float = DEVICE_RECALL_S) -> None:
        self.pol = policy
        self.be = backend
        self.tr = trace
        self.tick_s = float(tick_s)
        self.speed = float(speed)
        self.window_s = float(window_s) if window_s else float(trace.length_s)
        self.drain_s = float(drain_s)
        self.seed = int(seed)
        self.engine_config = engine_config
        self.device_latency_s = float(device_latency_s)
        self.reads_device = bool(getattr(policy, "reads_device_answer", False))
        self.retain = getattr(policy, "host_offload_intent", "demote") == "retain"
        self.trace_sha = trace_digest(trace, self.window_s)
        self.log: List[Dict[str, Any]] = []
        self.counts: Dict[str, int] = defaultdict(int)
        self.errors: List[str] = []
        self.epoch_overruns = 0
        self.max_epoch_lag_s = 0.0
        self.rid = 0
        self.answer_of: Dict[str, RecallQuery] = {}
        self.chain_links: Dict[str, int] = {}
        self.chain_done: Dict[str, int] = {}
        self.answers_live: List[Dict[str, Any]] = []

    # ---- observation
    def _observation(self, now: float, epoch: str, pend: List[RecallQuery]) -> Observation:
        eps = []
        for s in self.streams.values():
            eps.append(EpisodicStream(
                stream_id=s.stream_id,
                delivered_scores=tuple(v for _t, v in s.delivered),
                delivered_times_s=tuple(round(t, 3) for t, _v in s.delivered),
                # D205: None, not a short tuple. A shortened tuple reads as "this stream has had
                # fewer instants", which is the shape that let a constant pass for a trajectory.
                device_scores=(None if s.device_score_unknown else
                               tuple(v for _t, v, _e in s.delivered_device)),
                device_times_s=(None if s.device_score_unknown else
                                tuple(round(t, 3) for t, _v, _e in s.delivered_device)),
                device_episode_ids=(None if s.device_score_unknown else
                                    tuple(e for _t, _v, e in s.delivered_device)),
                cadence_s=s.cadence_s, frame_count=s.frame_count, on_cloud=s.on_cloud,
                network=NetworkState(connected=True, uplink_bps=C.UPLINK_BPS, rtt_s=C.RTT_S)))
        m = self.be.metrics()
        gpu = tuple(sorted(k for k, v in self.sessions.items() if v.tier == "gpu"))
        host = tuple(sorted(k for k, v in self.sessions.items() if v.tier == "host"))
        cloud = CloudState(
            queued_by_class=dict(recall=len(pend), episodic=int(m.get(
                "vllm:num_requests_waiting", self.counts["inflight_episodic"]))),
            running_by_class=dict(recall=self.counts["inflight_recall"],
                                  episodic=self.counts["inflight_episodic"]),
            # D209 (2): `_fetch_metrics` guarantees this key is present and carries an observed,
            # a last-good or an UNKNOWN-AND-CONSERVATIVE value, so the 0.0 default below is now
            # unreachable and is kept only so the expression is still total if a caller hands in
            # a mapping this class did not build (a test fixture, a replayed scrape).
            gpu_kv_fraction=float(m.get("vllm:gpu_cache_usage_perc",
                                        HttpBackend.KV_UNKNOWN_CONSERVATIVE)),
            host_kv_fraction=0.0, gpu_warm_sessions=gpu, host_warm_sessions=host,
            latency_estimate_s=dict(self.lat))
        return Observation(now_s=round(now, 3), epoch=epoch, streams=tuple(eps),
                           recall=tuple(pend), cloud=cloud,
                           budget_remaining_gpu_s=self.budget.remaining_gpu_s())

    def _recall_query(self, qid: str, sid: str, cat: str, at: float, tok: int) -> RecallQuery:
        st = self.sessions[sid]
        ready = {"gpu": "GPU-WARM", "host": "HOST-WARM", "cold": "COLD"}[st.tier]
        ev = (EvidenceItem("RECENT", "device", RECENT_WINDOW_TOKENS, RECENT_WINDOW_TOKENS * 4),
              EvidenceItem("D2", "device", tok, tok * 4),
              EvidenceItem("D2", "gpu" if ready == "GPU-WARM" else "device", tok,
                           C.host_reload_bytes(tok)))
        return RecallQuery(query_id=qid, session_id=sid, category=cat, arrival_s=round(at, 3),
                           deadline_s=round(at + self.tr.deadline_s, 3), evidence=ev,
                           readiness=ready, readiness_tokens=tok,
                           device_answer_confidence=(DC.confidence(qid) if self.reads_device
                                                     else None))

    # ---- the loop
    def run(self) -> Dict[str, Any]:
        import workload as W
        check_fairness(self.pol)
        self.pol.reset(self.seed)
        self.rng = random.Random(self.seed)
        self.streams = {sp.stream_id: StreamState(sp.stream_id) for sp in self.tr.streams}
        self.sessions = {sp.session_id: SessionState(sp.session_id, sp.tokens)
                         for sp in self.tr.sessions}
        self.budget = Budget(gpu_seconds=self.window_s * 1.0)
        self.lat: Dict[str, float] = dict(episodic=C.episodic_cloud_latency_s("32BI", 1, 25),
                                          recall=0.0)
        arrivals = [(a, q, s, c) for (a, q, s, c) in _recall_arrivals(self.tr)
                    if a <= self.window_s]
        ai = 0
        pend: List[RecallQuery] = []
        answers: List[Dict[str, Any]] = []
        defer_until: Dict[str, float] = {}
        futures: List[Tuple[Any, Submission]] = []
        wall0 = time.time()
        t = 0.0
        rid = 0
        while t < self.window_s + self.drain_s:
            target = wall0 + t / self.speed
            lag = time.time() - target
            if lag > 0.5 * self.tick_s / self.speed:
                self.epoch_overruns += 1
                self.max_epoch_lag_s = max(self.max_epoch_lag_s, lag * self.speed)
            elif lag < 0:
                time.sleep(-lag)
            self._collect(futures, t)
            epoch = "tick"
            while ai < len(arrivals) and arrivals[ai][0] <= t + 1e-9:
                at, qid, sid, cat = arrivals[ai]
                ai += 1
                pend.append(self._recall_query(qid, sid, cat, at,
                                               self.sessions[sid].tokens))
                epoch = "recall_arrival"
            visible = [q for q in pend
                       if t + 1e-9 >= q.arrival_s + (self.device_latency_s
                                                     if self.reads_device else 0.0)
                       and t + 1e-9 >= defer_until.get(q.query_id, -1.0)]
            withheld = [q for q in pend if q not in visible]
            if t <= self.window_s:
                act = self.pol(self._observation(t, epoch, visible))
                pend = withheld + self._enact(act, visible, t, answers, defer_until, futures)
                if len(self.log) < 40:
                    self.log.append(_trace_row(t, act))
            self._issue_episodic(t, futures)
            t += self.tick_s
        deadline = time.time() + 60.0
        while futures and time.time() < deadline:
            self._collect(futures, self.window_s + self.drain_s)
            time.sleep(0.01)
        return self._result(answers, pend)

    # ---- enactment
    def _enact(self, act: Action, visible: List[RecallQuery], t: float,
               answers: List[Dict[str, Any]], defer_until: Dict[str, float],
               futures: List) -> List[RecallQuery]:
        for sa in act.streams:
            s = self.streams[sa.stream_id]
            self.counts["stream_" + sa.mode] += 1
            if sa.mode == "suspend":
                s.on_cloud, s.suspend_until_s = False, float(sa.suspend_until_s)
            else:
                s.on_cloud = sa.mode == "cloud"
                if sa.mode == "cloud":
                    s.cadence_s, s.frame_count = float(sa.cadence_s), int(sa.frame_count)
        warmed: Dict[str, str] = {}
        for xa in act.sessions:
            a = xa.action
            self.counts["session_" + a] += 1
            st = self.sessions.get(xa.session_id)
            if st is None:
                continue
            if a == "EVICT":
                st.tier, st.built = "cold", False
                continue
            if a == "OFFLOAD_TO_HOST":
                # a host tier EXISTS live, so nothing is remapped: `host_offload_intent` only
                # ever mattered in the simulator's no-host scope.
                st.tier = "host" if st.built else st.tier
                continue
            if a in ("KEEP_GPU_WARM", "MATERIALIZE"):
                if st.tier == "gpu" and a != "MATERIALIZE":
                    continue
                if not st.built or a == "MATERIALIZE":
                    cost = C.recall_gpu_s(st.tokens, "COLD")
                    if not self.budget.can_spend(cost):
                        self.counts["budget_refusal"] += 1
                        continue
                    self.budget.spend(cost)
                    key = self._build(st, xa.slice_tokens, t, futures)
                    warmed[st.session_id] = key
                    self.counts["materialize" + ("_sliced" if xa.slice_tokens else "")] += 1
                st.tier = "gpu"
        keep: List[RecallQuery] = []
        for ra in act.recall:
            q = next(x for x in visible if x.query_id == ra.query_id)
            self.counts["recall_" + ra.decision] += 1
            if ra.decision == "DEVICE":
                done = (q.arrival_s if self.reads_device else t) + self.device_latency_s
                answers.append(dict(query_id=q.query_id, decision="DEVICE", delivered_s=done,
                                    deadline_s=q.deadline_s, on_time=done <= q.deadline_s))
            elif ra.decision == "REJECT":
                answers.append(dict(query_id=q.query_id, decision="REJECT", delivered_s=None,
                                    deadline_s=q.deadline_s, on_time=False))
            elif ra.decision == "DEFER":
                defer_until[q.query_id] = t + max(float(ra.defer_s or 0.0), 0.0)
                keep.append(q)
            else:                                        # CLOUD
                mk = warmed.get(q.session_id)
                if mk is not None:
                    self.answer_of[mk] = q               # the build carries the answer
                    continue
                cost = C.recall_gpu_s(q.readiness_tokens, q.readiness)
                if not self.budget.can_spend(cost):
                    self.counts["budget_refusal"] += 1
                    done = t + self.device_latency_s
                    answers.append(dict(query_id=q.query_id, decision="DEVICE-on-refusal",
                                        delivered_s=done, deadline_s=q.deadline_s,
                                        on_time=done <= q.deadline_s))
                    continue
                self.budget.spend(cost)
                self._recall_request(q, t, futures)
        return keep

    def _build(self, st: SessionState, slice_tokens: Optional[int], t: float,
               futures: List) -> str:
        """MATERIALIZE: one monolithic request, or a prefix-chained sequence of links.

        LIVE DIFFERENCE from the simulator, and the point of the port: each link is a separate
        request, so a policy CAN hold or align each one. The chain is issued link by link here;
        an arm that wants per-link alignment gets it by deciding again at the next epoch.
        """
        self.rid += 1
        key = f"w{self.rid}"
        n = SR.n_slices(st.tokens, slice_tokens) if slice_tokens else 1
        per = int(st.tokens / n)
        for i in range(n):
            sub = Submission(key=f"{key}.{i}", kind="cold_recall", tokens=per,
                             session=st.session_id, sent_s=t, retain=True,
                             meta=dict(link=i, n_links=n, build=key))
            self.counts["inflight_recall"] += 1
            futures.append((self.be.submit(sub), sub))
        self.chain_links[key] = n
        st.built = True
        return key

    def _recall_request(self, q: RecallQuery, t: float, futures: List) -> None:
        self.rid += 1
        key = f"r{self.rid}"
        kind = "recall_escalation" if q.readiness == "GPU-WARM" else "cold_recall"
        sub = Submission(key=key, kind=kind, tokens=q.readiness_tokens, session=q.session_id,
                         sent_s=t, retain=True, meta=dict(qid=q.query_id))
        self.answer_of[key] = q
        self.counts["inflight_recall"] += 1
        futures.append((self.be.submit(sub), sub))

    def _issue_episodic(self, t: float, futures: List) -> None:
        for s in self.streams.values():
            if not s.on_cloud:
                # the application reads the device's own score, at the device's own cadence
                if t - s.last_issue_s >= C.DEVICE_CADENCE_S:
                    s.last_issue_s = t
                    # D205 (2a): the REAL score or RAISE, and NOTHING neutral. This harness has no
                    # per-instant score source wired (live2 gets one from the trace's own
                    # device_answers.jsonl; this adapter has no equivalent), so what is recorded
                    # is None = UNKNOWN and the instant is counted. It is NOT 0.0: that literal
                    # was the maximum of log P(Yes) and made all seven readers escalate on every
                    # instant. The raise lands on the READER, which is where it belongs, because
                    # an arm that does not read scores must still be runnable here.
                    s.device_score_unknown += 1
                    self.counts["device_score_unknown"] += 1
                    s.delivered.append((t + self.device_latency_s, None))
                continue
            if s.last_issue_s >= 0 and t - s.last_issue_s < s.cadence_s - 1e-9:
                continue
            s.last_issue_s = t
            self.rid += 1
            key = f"e{self.rid}"
            tok = 378 if s.frame_count == 1 else 1062      # StudyD7b's measured prompt sizes
            cost = C.episodic_gpu_s("32BI", s.frame_count)
            if not self.budget.can_spend(cost):
                self.counts["budget_refusal"] += 1
                continue
            self.budget.spend(cost)
            sub = Submission(key=key, kind="episodic", tokens=tok, session=None, sent_s=t,
                             meta=dict(stream=s.stream_id))
            self.counts["inflight_episodic"] += 1
            futures.append((self.be.submit(sub), sub))

    def _collect(self, futures: List, t: float) -> None:
        still = []
        for fut, sub in futures:
            if not fut.done():
                still.append((fut, sub))
                continue
            r = fut.result()
            if r["error"]:
                self.errors.append(r["error"])
            if sub.kind == "episodic":
                self.counts["inflight_episodic"] -= 1
                st = self.streams.get(sub.meta.get("stream"))
                if st is not None and r["ttft_s"] is not None:
                    # D205 (2a): the cloud's own score for this answer, or None = UNKNOWN. This
                    # harness runs no score extractor (live2 has live2/scores.sh_score; the v1
                    # backend returns no logprobs), so None it is. Never 0.0.
                    sc = (r.get("score") or {}).get("cloud_score") if isinstance(
                        r.get("score"), dict) else None
                    if sc is None:
                        st.device_score_unknown += 1
                        self.counts["cloud_score_unknown"] += 1
                    st.delivered.append((sub.sent_s + r["ttft_s"] * self.speed, sc))
                self._ewma("episodic", r["ttft_s"])
            else:
                self.counts["inflight_recall"] = max(
                    self.counts["inflight_recall"] - 1, 0)
                self._ewma("recall", r["ttft_s"])
                key = sub.key.split(".")[0]
                if sub.meta.get("n_links"):
                    self.chain_done[key] = self.chain_done.get(key, 0) + 1
                    if self.chain_done[key] < self.chain_links.get(key, 1):
                        continue
                q = self.answer_of.pop(key, None)
                if q is not None and r["ttft_s"] is not None:
                    done = sub.sent_s + r["ttft_s"] * self.speed
                    self.answers_live.append(dict(query_id=q.query_id, decision="CLOUD",
                                                  delivered_s=done, deadline_s=q.deadline_s,
                                                  on_time=done <= q.deadline_s))
            self.counts["completed_" + sub.kind] += 1
        futures[:] = still

    def _ewma(self, cls: str, v: Optional[float]) -> None:
        if v is None:
            return
        v = v * self.speed
        self.lat[cls] = v if self.lat.get(cls, 0.0) <= 0 else (EWMA * v
                                                               + (1 - EWMA) * self.lat[cls])

    # ---- bookkeeping
    def _result(self, answers: List[Dict[str, Any]], pend: List[RecallQuery]) -> Dict[str, Any]:
        all_answers = answers + self.answers_live
        n_on_time = sum(1 for a in all_answers if a["on_time"])
        return dict(
            arm=self.pol.name, trace_sha256=self.trace_sha, engine_config=self.engine_config,
            window_s=self.window_s, tick_s=self.tick_s, speed=self.speed,
            n_streams=len(self.streams), n_sessions=len(self.sessions),
            counts=dict(sorted(self.counts.items())),
            n_recall_arrivals=len(all_answers) + len(pend),
            n_answered=len(all_answers), n_on_time=n_on_time,
            n_unanswered=len(pend),
            fraction_on_time=(n_on_time / len(all_answers)) if all_answers else None,
            latency_estimate_s={k: round(v, 4) for k, v in self.lat.items()},
            budget_gpu_s=round(self.budget.gpu_seconds, 2),
            budget_spent_gpu_s=round(self.budget.spent_gpu_seconds, 2),
            epoch_overruns=self.epoch_overruns,
            max_epoch_lag_s=round(self.max_epoch_lag_s, 4),
            n_errors=len(self.errors), first_errors=self.errors[:3],
            decision_trace=self.log)


def _recall_arrivals(trace) -> List[Tuple[float, str, str, str]]:
    out = []
    for sp in trace.sessions:
        for (tt, cat, qid) in sp.questions:
            out.append((float(tt), qid, sp.session_id, cat))
    return sorted(out)


def trace_digest(trace, window_s: float) -> str:
    """The per-cell sha256 every arm must see (fairness rule 6), over the ARRIVALS themselves."""
    h = hashlib.sha256()
    h.update(repr((trace.mix, trace.fleet, trace.deadline_s, trace.seed, round(window_s, 3),
                   trace.digest)).encode())
    for a in _recall_arrivals(trace):
        if a[0] <= window_s:
            h.update(repr(a).encode())
    for sp in trace.streams:
        h.update(repr((sp.stream_id, sp.clips[:4])).encode())
    return h.hexdigest()[:32]


def _trace_row(t: float, act: Action) -> Dict[str, Any]:
    return dict(now_s=round(t, 3),
                streams=[(s.stream_id, s.mode, s.cadence_s, s.frame_count) for s in act.streams],
                recall=[(r.query_id[:12], r.decision, r.representation, r.defer_s)
                        for r in act.recall],
                sessions=[(x.session_id, x.action, x.slice_tokens) for x in act.sessions],
                order=act.order, engine_config=act.engine_config,
                notes={k: v for k, v in (act.notes or {}).items()
                       if not isinstance(v, (dict, list))})
