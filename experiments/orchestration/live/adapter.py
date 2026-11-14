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
| `streams[].delivered_scores / _times_s` | what the APPLICATION has actually received: a cloud answer when its request completed, the device's own score otherwise |
| `streams[].cadence_s`, `frame_count`, `on_cloud` | the orchestrator's own current setting for that stream |
| `cloud.queued_by_class`, `running_by_class` | the orchestrator's in-flight bookkeeping, cross-checked against the server's `/metrics` |
| `cloud.gpu_kv_fraction` | the server's `vllm:gpu_cache_usage_perc` |
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
        """Poll /metrics in the background, so a decision epoch never waits on HTTP."""
        self._metrics: Dict[str, float] = {}
        self._stop = threading.Event()

        def loop():
            while not self._stop.is_set():
                self._metrics = self._fetch_metrics()
                self._stop.wait(interval_s)
        threading.Thread(target=loop, daemon=True).start()

    def metrics(self) -> Dict[str, float]:
        if hasattr(self, "_metrics"):
            return self._metrics
        return self._fetch_metrics()

    def _fetch_metrics(self) -> Dict[str, float]:
        try:
            with urllib.request.urlopen(self.base_url + "/metrics", timeout=5) as r:
                txt = r.read().decode()
        except Exception:                                             # noqa: BLE001
            return {}
        out = {}
        for line in txt.splitlines():
            if line.startswith("#") or " " not in line:
                continue
            name, _, val = line.rpartition(" ")
            key = name.split("{")[0]
            try:
                out[key] = float(val)
            except ValueError:
                pass
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
    delivered: deque = field(default_factory=lambda: deque(maxlen=40))   # (t, score)
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
            gpu_kv_fraction=float(m.get("vllm:gpu_cache_usage_perc", 0.0)),
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
                    s.delivered.append((t + self.device_latency_s, 0.0))
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
                    st.delivered.append((sub.sent_s + r["ttft_s"] * self.speed, 0.0))
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
