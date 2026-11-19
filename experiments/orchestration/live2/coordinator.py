#!/usr/bin/env python3
"""The live round-1 COORDINATOR: one process in front of one OpenAI-compatible server. CPU only.

StudyLIVE2-coord. It consumes fleet events, keeps per-device state, calls the active arm once per
100 ms DECISION PERIOD over that period's batched events (D99), submits through the existing `HttpBackend`, and emits `cloud_answer`.
It is a pure HTTP client of the server (request-harness pattern) and scrapes `/metrics`; nothing
in this process opens an engine.

THINGS THIS LOOP DOES FOR EVERY ARM, IDENTICALLY

* `interface.scrub` on every observation and `interface.validate_action` on every action, both
  inside `interface.Policy.__call__`, plus `interface.check_fairness` before the run. An arm
  declaring `reads_future` is REFUSED.
* DEFER(defer_s) is HONOURED (amendment 2, D90): a deferred opportunity is withheld until
  `defer_s` has elapsed and is then re-decided. Arms that never emit DEFER are unaffected.
* D84 cache isolation: every request carries this device's cache salt and one multimodal uuid
  per (device, frame).
* D87: an arm whose published mechanism waits for the device's own answer is charged StudyD8's
  0.567 s rule, so its opportunities are not actionable before then and its DEVICE outcomes are
  delivered then. None of the eight round-1 arms declares it; the charge is implemented so that
  an arm which does is charged automatically.
* Capacities (D56, D76) and targets (D71, D82) are INPUTS, passed to every arm identically.

MONITORING IS CAPACITY-BASED (D62): every decision instant is a candidate; an instant the arm
does not take simply stands as the device's own answer.

UPLOAD MODES (D69): A pushes every frame; B pulls, and the pull message plus the upload count
toward delivered delay. Robot history batches are pushed in both modes.

NOTHING A RUN AGAINST THE CPU STUB PRODUCES IS A MEASUREMENT.
"""
import resource
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/baselines/reconstructed"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import costs as C                                                       # noqa: E402
from interface import Budget, check_fairness                            # noqa: E402

import bodies as B                                                      # noqa: E402
import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import schema as SC                                                     # noqa: E402
import scores as S2                                                     # noqa: E402
from backend import (Live2Backend, Live2Submission, cached_tokens_of,    # noqa: E402
                     output_tokens_of, prompt_tokens_of)

DEVICE_ANSWER_CHARGE_S = C.DEV_LAT_S         # StudyD8's 0.567 s RULE (D87, amendment 2 item 3)
# D99 (1): ONE DECISION PERIOD FOR EVERY ARM, 100 ms, with the events of each period batched.
# It replaces the 50 ms event grid AND the per-arm H tick: H is now the rollout horizon only
# (spec 6.1, 9 as amended). Every arm therefore decides at the same rate, which is what makes
# the decision rate stop being an arm property, and it is recorded in the run header.
DECISION_PERIOD_S = 0.1
DEFAULT_TICK_S = DECISION_PERIOD_S           # kept as the old name; same value for every arm
HEADER_TEXT = "D2 history"                   # the committed D2 header text, 31 tokens (StudyRH4)


@dataclass
class Logs:
    out_dir: Path
    decision: Any = None
    request: Any = None
    residency: Any = None

    def open(self) -> "Logs":
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.decision = SC.JsonlWriter(self.out_dir / "decision.jsonl")
        self.request = SC.JsonlWriter(self.out_dir / "request.jsonl")
        self.residency = SC.JsonlWriter(self.out_dir / "residency.jsonl")
        return self

    def close(self) -> None:
        for w in (self.decision, self.request, self.residency):
            if w is not None:
                w.close()


class Live2Coordinator:
    def __init__(self, arm, backend: Optional[Live2Backend], events: List[Dict[str, Any]],
                 *, gpu_kv_tokens: int, host_tier_gib: float, host_tier_tokens: int,
                 upload_mode: str = "A", window_s: float = 180.0, drain_s: float = 20.0,
                 tick_s: Optional[float] = None, decision_period_s: Optional[float] = None,
                 seed: int = 0, speed: float = 1.0,
                 logs: Optional[Logs] = None, run_tag: str = "live2",
                 frames_root: Optional[Path] = None, dry_run: bool = False,
                 targets: Optional[Dict[str, Any]] = None, on_pull=None,
                 gpu_budget_s: Optional[float] = None,
                 max_wall_s: Optional[float] = None,
                 frame_cache: Any = None, defer_images: bool = False) -> None:
        self.arm = arm
        self.be = backend
        self.events = sorted(events, key=lambda e: (_sched(e), e.get("kind", "")))
        self.upload_mode = upload_mode
        self.window_s = float(window_s)
        self.drain_s = float(drain_s)
        self.seed = int(seed)
        self.speed = float(speed)
        self.logs = logs
        self.run_tag = run_tag
        self.frames_root = Path(frames_root) if frames_root else None
        # StudyLIVE2-harness: with a frame cache the loop never reads a frame or base64-encodes
        # one; `defer_images` leaves the image payloads to the backend's own thread. Both are
        # OFF by default, so an unconfigured run behaves exactly as the pilot's did.
        self.frame_cache = frame_cache
        self.defer_images = bool(defer_images)
        self.dry_run = bool(dry_run)
        # mode B (D69): the fleet answers a pull. Without a live fleet process the caller may
        # supply a responder that returns the monitor_frame the pull would produce, with the pull
        # message and the upload both charged to the delivered delay.
        self.on_pull = on_pull
        self.injected: List[Dict[str, Any]] = []
        self.h_s = getattr(arm, "h_s", None) if getattr(arm, "uses_h", False) else None
        # D99 (1): the decision period is the SAME for every arm and is NOT the arm's H. The
        # period is the grid: each period's events are ingested and then ONE decision is taken
        # over the batch. `tick_s` survives as the old name for the same number so existing
        # callers keep working; it can no longer differ from the period.
        period = decision_period_s if decision_period_s is not None else tick_s
        self.decision_period_s = float(period if period is not None else DECISION_PERIOD_S)
        self.tick_s = self.decision_period_s
        self.event_grid_s = self.decision_period_s
        self.st = CS.CoordState(gpu_kv_tokens=int(gpu_kv_tokens),
                                host_tier_gib=float(host_tier_gib),
                                host_tier_tokens=int(host_tier_tokens),
                                upload_mode=upload_mode,
                                targets=dict(targets or CS.TARGETS))
        # D102: the GPU budget is an explicit INPUT, equal by default to one GPU's time over
        # the run (window length x 1 GPU-second per second), identical for every arm and
        # recorded in the header. It is the PHYSICAL CAPACITY, so it never binds artificially
        # (D58: round 1 has no fixed budget; "budget %" is only a test variable). B8, B9 and
        # edf-service-time admit by a utility-per-GPU-second ratio against a remaining budget
        # and need a finite one, which is why it exists at all. It replaces the harness constant
        # (StudyLIVE2-coord open issue 8).
        self.gpu_budget_s = float(gpu_budget_s if gpu_budget_s is not None
                                  else self.window_s * 1.0)
        self.st.budget = Budget(gpu_seconds=self.gpu_budget_s)
        self.n_dec = 0
        self.n_req = 0
        self.futures: List[Tuple[Any, Live2Submission]] = []
        self.answers: List[Dict[str, Any]] = []
        self.pulls: List[Dict[str, Any]] = []
        self.cloud_answers: List[Dict[str, Any]] = []
        # StudyLIVE2-harness addendum: answers the I/O layer forwarded at stream end, by request
        self.forwarded: Dict[str, Dict[str, Any]] = {}
        self.n_forward_mismatch = 0
        # what a slow decision costs: epoch start -> the request going on the wire (addendum (a))
        self.submit_delays_ms: List[float] = []
        self._epoch_wall0: Optional[float] = None
        self.n_recall_first_token = 0
        self.n_recall_letter_differs = 0
        self.recall_letter_diffs: List[Dict[str, Any]] = []
        self.n_monitor_score_differs = 0
        self.decision_latencies_ms: List[float] = []
        # D115: per decision (t, wall_ms, cpu_ms, candidates)
        self.decision_times: List[Tuple[float, float, float, int]] = []
        self._priority_latest: Dict[str, int] = {}          # vllm-priority, by item key
        self.errors: List[str] = []
        self.counts: Dict[str, int] = defaultdict(int)
        self.builds: Dict[str, Dict[str, Any]] = {}
        self.reads_device = bool(getattr(arm, "reads_device_answer", False))
        # A cell whose decision loop cannot keep up with its own tick would otherwise run for
        # many times its window and report nothing. The guard stops it and the result SAYS SO,
        # with the virtual time it reached, which is the number that matters.
        self.max_wall_s = float(max_wall_s) if max_wall_s else None
        self.wall_guard_hit = False
        self.t_reached = 0.0
        self.epoch_overruns = 0
        self.max_epoch_lag_s = 0.0

    # ---------------------------------------------------------------- the loop
    def run(self) -> Dict[str, Any]:
        fair = check_fairness(self.arm)
        if fair.get("rule5_reads_future"):
            raise RuntimeError("fairness rule 5: an arm that reads the future is refused in a "
                               "live run (%s)" % self.arm.name)
        self.arm.reset(self.seed)
        ei = 0
        wall0 = time.time()
        cpu0 = _cpu_s()
        t = 0.0
        end = self.window_s + self.drain_s
        while t < end:
            if not self.dry_run:
                target = wall0 + t / self.speed
                lag = time.time() - target
                if lag > 0.5 * self.tick_s / self.speed:
                    self.epoch_overruns += 1
                    self.max_epoch_lag_s = max(self.max_epoch_lag_s, lag * self.speed)
                elif lag < 0:
                    time.sleep(-lag)
            self._collect(t)
            epoch = "tick"
            while ei < len(self.events) and _sched(self.events[ei]) <= t + 1e-9:
                epoch = self._ingest(self.events[ei], t) or epoch
                ei += 1
            while self.injected and _sched(self.injected[0]) <= t + 1e-9:
                epoch = self._ingest(self.injected.pop(0), t) or epoch
            self.st.now = t
            if not self.dry_run and self.be is not None:
                self.st.metrics = self.be.metrics()
            # D99 (1): exactly ONE decision per period, over that period's batched events.
            # The old rule (one decision per arm tick PLUS one on every event) made the
            # policy arm's decision rate a function of the event rate: at 64 devices an event
            # landed in nearly every 50 ms step, so an H = 1 s arm was in fact invoked about 20
            # times a virtual second (StudyLIVE2-coord open issue 10a).
            if t <= self.window_s:
                self._epoch(t, epoch)
            self._expire(t)
            self.t_reached = t
            t = round(t + self.event_grid_s, 9)
            if self.max_wall_s is not None and time.time() - wall0 > self.max_wall_s:
                self.wall_guard_hit = True
                break
        if self.dry_run:
            for _ in range(10_000):
                if not self.futures:
                    break
                self.st.now = round(self.st.now + self.tick_s, 9)
                self._collect(self.st.now)
        else:
            deadline = time.time() + 60.0
            while self.futures and time.time() < deadline:
                self._collect(self.window_s + self.drain_s)
                time.sleep(0.01)
        return self._result(cpu0, time.time() - wall0)

    def _epoch(self, t: float, epoch: str) -> None:
        # D100: the hook is refreshed once per decision period, immediately before the
        # observation, so the instant deadline and the built-prefix size the arm reads describe
        # the same state the observation does. It is O(devices + sessions) per period.
        self._roster(t)
        obs = self.st.observation(t, epoch if epoch in _EPOCHS else "tick")
        k0 = self._candidates_counter()
        t0 = time.perf_counter()
        c0 = time.thread_time()
        self._epoch_wall0 = t0
        try:
            act = self.arm(obs)                  # scrub + validate_action + apply_defaults
            # D115: the DECIDING THREAD's CPU time over the same call (time.thread_time, so the
            # I/O loop's thread in the same process is not counted), read INSIDE the wall interval
            # so cpu <= wall by construction; and the candidates priced: the delta of the arm's own
            # scoring counter where it keeps one (policy-core's rollout scorings), else the number
            # of pending items the arm ordered (EDF family, which prices nothing).
            cpu_ms = (time.thread_time() - c0) * 1000.0
            dt_ms = (time.perf_counter() - t0) * 1000.0
            k1 = self._candidates_counter()
            cand = (k1 - k0) if (k0 is not None and k1 is not None) else \
                (len(getattr(obs, "streams", ()) or ()) + len(getattr(obs, "recall", ()) or ()))
            self.decision_latencies_ms.append(dt_ms)
            self.decision_times.append((round(t, 4), round(dt_ms, 4), round(cpu_ms, 4), int(cand)))
            self._enact(act, t, dt_ms)
        finally:
            # a submission made OUTSIDE an epoch (a chained recall released by a completion in
            # `_settle`) is stamped at the instant it is made, not charged this epoch's delay
            self._epoch_wall0 = None

    def _priority_for(self, kind, device_id, session_id, opportunity_id) -> Dict[str, Any]:
        """vllm-priority: the priority the arm set for this item, if any (monitor by stream, recall
        by question, build by session); {} for every other arm, so nothing else changes."""
        if not self._priority_latest:
            return {}
        key = ("mon:" + str(device_id) if kind == "monitor" else
               "rc:" + str(opportunity_id) if kind == "recall" else "session:" + str(session_id))
        v = self._priority_latest.get(key)
        return {} if v is None else {"priority_ms": int(v)}

    def _candidates_counter(self) -> Optional[int]:
        """D115: the arm's own count of candidates priced so far, read only (never written)."""
        co = getattr(self.arm, "co", None)
        v = getattr(co, "scoring_calls", None) if co is not None else None
        return int(v) if isinstance(v, (int, float)) else None

    def decision_time_summary(self) -> Dict[str, Any]:
        """D115: decision wall and CPU time, their ratio (contention indicator) and candidates."""
        rows = self.decision_times
        wall = [r[1] for r in rows]
        cpu = [r[2] for r in rows]
        ratio = [r[1] / r[2] for r in rows if r[2] > 0]
        cand = [r[3] for r in rows]
        return dict(n=len(rows), cpu_clock="time.thread_time() of the deciding thread",
                    wall_ms=_pct(wall), cpu_ms=_pct(cpu), wall_over_cpu=_pct(ratio),
                    candidates=_pct(cand),
                    candidates_source=("arm scoring counter delta"
                                       if self._candidates_counter() is not None
                                       else "pending items ordered"))

    def write_decision_times(self, path: Path) -> None:
        import gzip
        import json
        with gzip.open(path, "wt") as f:
            for t, w, c, k in self.decision_times:
                f.write(json.dumps(dict(t=t, wall_ms=w, cpu_ms=c, candidates=k)) + "\n")

    # ---------------------------------------------------------------- fleet events
    def _ingest(self, ev: Dict[str, Any], t: float) -> Optional[str]:
        k = ev["kind"]
        if k == "device_register":
            self.st.register(ev, CK.cache_salt(self.run_tag, ev["device_id"]))
            self._roster()
            return "stream_arrival"
        if k == "session_start":
            self.st.session_start(ev)
            return None
        if k == "session_end":
            self.st.session_end(ev)
            self._log_residency(t, ev["session_id"])
            return None
        if k == "history_preload":
            self.st.history_preload(ev)
            return None
        if k == "history_append":
            self.st.history_append(ev)
            return None
        if k == "monitor_offer":
            o = self.st.monitor_offer(ev)
            self._device_answer(o)
            return "stream_arrival"
        if k == "monitor_frame":
            o = self.st.monitor_frame(ev)
            self._device_answer(o)
            return "stream_arrival"
        if k == "recall_question":
            self.st.recall_question(ev)
            self._roster()
            return "recall_arrival"
        raise KeyError(f"the coordinator has no handler for event kind {k!r}")

    def _device_answer(self, o) -> None:
        """The device answers every opportunity locally and immediately (spec v4 section 1.2),
        so the application-visible stream carries the device's own answer from the capture
        instant; a cloud answer that arrives in time is appended on top of it and upgrades it.
        The SCORES here are placeholders: task value is scored offline from the recordings
        (D85, D87), never in this process."""
        d = self.st.devices.get(o.device_id)
        if d is None or o.kind != "monitor":
            return
        if any(abs(t - o.t_event) < 1e-9 for t, _v in d.delivered):
            return
        d.delivered.append((o.t_event, 0.0))

    def _roster(self, now: Optional[float] = None) -> None:
        """The arm-side hook (D100): CAUSAL FACTS KNOWN AT ARRIVAL, never the future, and never
        through the scrubbed `Observation`.

        Two D100 facts are added to the device roster:

        * `sh_instant`, per device: the opportunity_id, capture time and ABSOLUTE DEADLINE
          c_i + L_SH of the monitoring instant that device's stream currently stands for. It is
          chosen by exactly the rule `CoordState.observation` uses (the first visible, undecided,
          un-deferred, not-yet-late instant in arrival order), so an arm ordering by this
          deadline is ordering the instant the coordinator will actually act on. It replaces the
          "next call due after the last answer the application received" workaround, under which
          every stream tied on `now + L` and pi_0's tie-break by item_id starved every device but
          the first (StudyLIVE2-coord open issue 9).
        * `built_tokens_by_session`: how much of each history the cloud has ALREADY BUILT
          (partial readiness), so a later reconstruction piece is costed as a piece on a warm
          prefix instead of a cold rebuild (open issue 3b).

        Registry arms (FCFS, B8, B9) declare no `live2_roster` and so receive nothing: they are
        unchanged by D100.
        """
        if not hasattr(self.arm, "live2_roster"):
            return
        now = self.st.now if now is None else float(now)
        mon, _rec = self.st.visible(now)
        first: Dict[str, Any] = {}
        for o in mon:
            first.setdefault(o.device_id, o)
        self.arm.live2_roster(dict(
            devices={d.device_id: dict(type=d.type, uplink_mbps=d.uplink_mbps,
                                       rtt_ms=d.rtt_ms) for d in self.st.devices.values()},
            session_device={s.session_id: s.device_id for s in self.st.sessions.values()},
            frame_bytes={d.device_id: d.frame_bytes for d in self.st.devices.values()
                         if d.frame_bytes},
            sh_instant={did: dict(opportunity_id=o.opp_id, t_capture=round(o.t_event, 6),
                                  deadline_abs=round(o.deadline_abs(), 6))
                        for did, o in first.items()},
            built_tokens_by_session={sid: int(s.built_tokens)
                                     for sid, s in self.st.sessions.items()
                                     if s.built_tokens > 0},
        ))

    # ---------------------------------------------------------------- enactment
    def _enact(self, act, t: float, dt_ms: float) -> None:
        # vllm-priority: the arm's per-item priorities (Action.notes["priority_ms"]); kept by key so a
        # submission released outside an epoch (a chained recall) still carries its item's priority
        pri = ((getattr(act, "notes", None) or {}).get("priority_ms")) or {}
        if pri:
            self._priority_latest.update(pri)
        preds = getattr(self.arm, "last_predictions", {}) or {}
        mix = self.st.traffic_mix()
        for sa in act.streams:
            d = self.st.devices.get(sa.stream_id)
            if d is None:
                continue
            d.on_cloud = sa.mode == "cloud"
            if sa.mode == "cloud":
                d.cadence_s = float(sa.cadence_s or d.cadence_s)
                d.frame_count = int(sa.frame_count or d.frame_count)
                self._serve_monitor(sa.stream_id, t, dt_ms, preds, mix)
        warmed: Dict[str, str] = {}
        for xa in act.sessions:
            s = self.st.sessions.get(xa.session_id)
            if s is None:
                continue
            self.counts["session_" + xa.action] += 1
            if xa.action == "EVICT":
                # D56: demote to cold. The frames stay on disk; nothing is deleted.
                s.belief = {"gpu": 0.0, "host": 0.0, "cold": 1.0}
                s.built_tokens = 0
            elif xa.action == "OFFLOAD_TO_HOST":
                s.desired_tier = "host"
            elif xa.action == "KEEP_GPU_WARM":
                s.desired_tier = "gpu"
            elif xa.action == "MATERIALIZE":
                rid = self._advance_build(s, xa.target_tokens, xa.slice_tokens, t, dt_ms,
                                          preds, mix)
                if rid:
                    warmed[s.session_id] = rid
        for ra in act.recall:
            o = self.st.opps.get(ra.query_id)
            if o is None or o.state not in ("arrived", "offered"):
                continue
            self.counts["recall_" + ra.decision] += 1
            if ra.decision == "DEFER":
                o.defer_until = t + max(float(ra.defer_s or 0.0), 0.0)
                o.n_defers += 1
                self._log_decision(t, "defer", [o.opp_id], defer_s=float(ra.defer_s or 0.0),
                                   latency_ms=dt_ms, preds=preds, mix=mix)
                continue
            if ra.decision in ("DEVICE", "REJECT"):
                o.state = "declined"
                o.served_at = (o.t_event + DEVICE_ANSWER_CHARGE_S if self.reads_device
                               else t)
                self.answers.append(dict(opportunity_id=o.opp_id, kind="recall",
                                         device_id=o.device_id, decision=ra.decision,
                                         delivered_s=o.served_at,
                                         deadline_s=o.deadline_abs(), served_by="device",
                                         on_time=None))
                self._log_decision(t, "decline", [o.opp_id], latency_ms=dt_ms, preds=preds,
                                   mix=mix)
                continue
            s = self.st.sessions.get(o.session_id)
            if s is None:
                continue
            if s.session_id in warmed:
                self.builds[warmed[s.session_id]]["answers"] = o.opp_id
                o.state = "in_flight"
                continue
            if s.built_tokens < s.est_tokens and s.believed_tier() != "gpu":
                # no build was asked for: the answer carries the whole history in one request,
                # which is what an arm that never materializes expresses (monolithic).
                self._submit_recall(o, s, t, dt_ms, preds, mix, whole=True)
            else:
                self._submit_recall(o, s, t, dt_ms, preds, mix, whole=False)

    def _serve_monitor(self, device_id: str, t: float, dt_ms: float, preds, mix) -> None:
        cands = [self.st.opps[i] for i in self.st.order
                 if self.st.opps[i].kind == "monitor"
                 and self.st.opps[i].device_id == device_id
                 and self.st.opps[i].state in ("arrived", "offered")
                 and self.st.opps[i].defer_until <= t + 1e-9
                 and self.st.opps[i].deadline_abs() >= t - 1e-9]
        if not cands:
            return
        o = min(cands, key=lambda x: x.deadline_abs())
        if self.reads_device and t + 1e-9 < o.t_event + DEVICE_ANSWER_CHARGE_S:
            return
        if o.state == "offered":
            if self.upload_mode != "B":
                return
            if o.pulled_at is None:
                o.pulled_at = t
                self.pulls.append(SC.make("pull_request", device_id=device_id,
                                          instant_id=o.instant_id or o.opp_id, t_sent=t))
                self._log_decision(t, "pull", [o.opp_id], latency_ms=dt_ms, preds=preds, mix=mix)
                if self.on_pull is not None:
                    ev = self.on_pull(o, t)
                    if ev is not None:
                        import bisect
                        keys = [_sched(x) for x in self.injected]
                        self.injected.insert(bisect.bisect_right(keys, _sched(ev)), ev)
            return
        cost = C.episodic_gpu_s("32BI", self.st.devices[device_id].frame_count)
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            return
        self.st.budget.spend(cost)
        o.state = "in_flight"
        did = self._log_decision(t, "release_monitor", [o.opp_id], latency_ms=dt_ms,
                                 preds=preds, mix=mix, key="mon:" + device_id)
        frames = [dict(frame_ref=o.frame_ref, path=self._path(o.frame_ref))]
        self._submit(kind="monitor", device_id=device_id, session_id=None,
                     opportunity_id=o.opp_id, decision_id=did, frames=frames,
                     est_tokens=378, question=B.SH_QUERY, options=(),
                     max_tokens=B.SH_GEN["max_tokens"], t=t, mix=mix)

    def _advance_build(self, s, target_tokens: Optional[int], slice_tokens: Optional[int],
                       t: float, dt_ms: float, preds, mix) -> Optional[str]:
        """One MATERIALIZE advances a session's build by ONE piece (or the remainder).

        LIVE SEMANTICS, stated because it differs from StudyLIVE1's adapter, which issued a whole
        chain on one MATERIALIZE: here each piece is a separate decision and a separate request,
        so an arm CAN hold or re-order the next piece. The same rule applies to every arm, so no
        arm gains or loses by it. `slice_tokens = None` builds the remainder in one request,
        which is the monolithic option every pre-amendment baseline can express.
        """
        target = min(int(target_tokens or s.est_tokens), max(int(s.est_tokens), 1))
        if s.built_tokens >= target:
            return None
        left = target - s.built_tokens
        piece = left if slice_tokens is None else min(int(slice_tokens), left)
        n_new = max(1, int(round(piece / float(CS.D2_TOK_PER_IMG))))
        already = len(s.sent_bytes_for)
        new_refs = s.frames[already:already + n_new]
        if not new_refs:
            return None
        cost = C.recall_gpu_s(max(piece, 1), "COLD")
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            return None
        self.st.budget.spend(cost)
        kind = "piece" if slice_tokens is not None else "whole"
        did = self._log_decision(t, "release_piece" if kind == "piece" else "release_whole",
                                 [], piece_tokens=int(piece), latency_ms=dt_ms, preds=preds,
                                 mix=mix, key="rc:" + s.session_id, session_id=s.session_id)
        frames = ([dict(frame_ref=r, path=None) for r in s.frames[:already]]
                  + [dict(frame_ref=r, path=self._path(r)) for r in new_refs])
        rid = self._submit(kind=kind, device_id=s.device_id, session_id=s.session_id,
                           opportunity_id=None, decision_id=did, frames=frames,
                           est_tokens=int(s.built_tokens + piece), question=None, options=(),
                           max_tokens=1, t=t, mix=mix)
        self.builds[rid] = dict(session_id=s.session_id, piece_tokens=int(piece),
                                refs=list(new_refs), answers=None)
        return rid

    def _submit_recall(self, o, s, t: float, dt_ms: float, preds, mix, whole: bool) -> None:
        tokens = max(int(s.est_tokens), 1)
        cost = C.recall_gpu_s(tokens, s.readiness())
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            o.state = "declined"
            self.answers.append(dict(opportunity_id=o.opp_id, kind="recall",
                                     device_id=o.device_id, decision="DEVICE-on-refusal",
                                     delivered_s=t, deadline_s=o.deadline_abs(),
                                     served_by="device", on_time=None))
            return
        self.st.budget.spend(cost)
        o.state = "in_flight"
        did = self._log_decision(t, "release_recall", [o.opp_id], latency_ms=dt_ms, preds=preds,
                                 mix=mix, key="rc:" + (o.session_id or ""),
                                 session_id=o.session_id)
        sent = len(s.sent_bytes_for)
        if whole:
            frames = [dict(frame_ref=r, path=self._path(r)) for r in s.frames]
        else:
            frames = ([dict(frame_ref=r, path=None) for r in s.frames[:sent]]
                      + [dict(frame_ref=r, path=self._path(r)) for r in s.frames[sent:]])
        self._submit(kind="recall", device_id=o.device_id, session_id=o.session_id,
                     opportunity_id=o.opp_id, decision_id=did, frames=frames,
                     est_tokens=tokens, question=o.question, options=o.options,
                     max_tokens=B.RECALL_GEN["max_tokens"], t=t, mix=mix)

    def _path(self, frame_ref: Optional[str]) -> Optional[Path]:
        if frame_ref is None:
            return None
        if self.frame_cache is not None:
            return self.frame_cache.path_of(frame_ref)
        p = Path(frame_ref)
        if not p.is_absolute() and self.frames_root is not None:
            p = self.frames_root / frame_ref
        return p if p.exists() else None

    # ---------------------------------------------------------------- requests
    def _submit(self, *, kind: str, device_id: str, session_id: Optional[str],
                opportunity_id: Optional[str], decision_id: Optional[str],
                frames: List[Dict[str, Any]], est_tokens: int, question: Optional[str],
                options, max_tokens: int, t: float, mix: Dict[str, int]) -> str:
        self.n_req += 1
        rid = f"r{self.n_req}"
        d = self.st.devices[device_id]
        # THE TRUE SUBMISSION STAMP (StudyLIVE2-harness addendum (a), from flash's branch). A
        # decision that takes 100 ms puts its requests on the wire 100 ms after the epoch it
        # belongs to; stamping them with the epoch's nominal instant would understate every time
        # derived from them by that delay. The delay is recorded per request and IS what a slow
        # decision costs: later submissions, not held answers. A dry run has no wall clock and
        # keeps the nominal instant, so its logs stay deterministic. Unlike the branch, the
        # delay is charged only inside an epoch (`_epoch_wall0` is cleared when it ends).
        delay_s = 0.0
        if not self.dry_run and self._epoch_wall0 is not None:
            delay_s = max(0.0, time.perf_counter() - self._epoch_wall0)
            self.submit_delays_ms.append(delay_s * 1000.0)
        t = t + delay_s
        body = B.build_body(kind=kind, device_id=device_id, session_id=session_id,
                            run_tag=self.run_tag, salt=d.salt, header=HEADER_TEXT,
                            frames=frames, question=question, options=options,
                            max_tokens=max_tokens, est_tokens=est_tokens,
                            defer_images=self.defer_images)
        sub = Live2Submission(request_id=rid, decision_id=decision_id, kind=kind,
                              device_id=device_id, session_id=session_id,
                              opportunity_id=opportunity_id, body=body,
                              est_tokens=int(est_tokens), sent_s=t, cache_salt=d.salt,
                              mm_uuids=list(body["_live2"]["mm_uuids"]), traffic_mix=dict(mix),
                              meta=dict(nominal_t=t - delay_s, decision_delay_s=delay_s,
                                        **self._priority_for(kind, device_id, session_id, opportunity_id)))
        self.st.in_flight[kind] += 1
        self.counts["submitted_" + kind] += 1
        if session_id is not None:
            s = self.st.sessions[session_id]
            for f in frames:
                if f.get("path") is not None:
                    s.sent_bytes_for.add(f["frame_ref"])
        if self.dry_run:
            self.futures.append((_DryFuture(sub, self._dry_service_s(sub), t,
                                            lambda: self.st.now), sub))
        else:
            self.futures.append((self.be.submit_live2(sub), sub))
        return rid

    def _dry_service_s(self, sub: Live2Submission) -> float:
        """The deterministic stand-in used by `--dry-run`, which sends no HTTP at all.

        It is the committed cost curve (`baselines/costs.py`), so the loop advances without a
        server and WITHOUT a wall clock. A dry run is a determinism and legality test, never a
        measurement and never a latency result.
        """
        if sub.kind == "monitor":
            return float(C.episodic_cloud_latency_s("32BI", 1, 25))
        return float(C.recall_ttft_s(max(sub.est_tokens, 1), "COLD"))

    def _collect(self, t: float) -> None:
        still = []
        for fut, sub in self.futures:
            if not fut.done():
                still.append((fut, sub))
                continue
            r = fut.result()
            self.st.in_flight[sub.kind] = max(self.st.in_flight[sub.kind] - 1, 0)
            if r.get("error"):
                self.errors.append(r["error"])
            usage = r.get("usage") or {}
            ct = cached_tokens_of(usage)
            pt = prompt_tokens_of(usage)
            path, frac = SC.cache_path_of(ct, pt)
            done_s = sub.sent_s + (r["total_s"] * self.speed if r.get("total_s") else 0.0)
            first_s = (sub.sent_s + r["ttft_s"] * self.speed) if r.get("ttft_s") else None
            if self.logs is not None:
                self.logs.request.write(SC.RequestRecord(
                    request_id=sub.request_id, decision_id=sub.decision_id,
                    device_id=sub.device_id, t_submit=round(sub.sent_s, 6),
                    t_first_token=(round(first_s, 6) if first_s is not None else None),
                    t_done=round(done_s, 6), prompt_tokens=pt, cached_tokens=ct,
                    cache_path=path, cached_fraction=frac,
                    output_tokens=output_tokens_of(usage), http_status=r.get("http_status"),
                    cache_salt=sub.cache_salt, session_id=sub.session_id,
                    opportunity_id=sub.opportunity_id, mm_uuids=list(sub.mm_uuids),
                    traffic_mix=dict(sub.traffic_mix)))
            self.st.ewma("episodic" if sub.kind == "monitor" else "recall", r.get("ttft_s"))
            if hasattr(self.arm, "live2_completed"):
                # An arm that keeps its own model of what the engine is running must be told
                # when a request finishes, or its model never empties.
                self.arm.live2_completed(dict(
                    kind=sub.kind, device_id=sub.device_id, session_id=sub.session_id,
                    opportunity_id=sub.opportunity_id, decision_id=sub.decision_id,
                    t_submit=sub.sent_s, t_first_token=first_s, t_done=done_s,
                    cache_path=path, request_id=sub.request_id,
                    prompt_tokens=(pt if pt is not None else sub.est_tokens),
                    cached_tokens=ct))
            self._settle(sub, first_s, done_s, path, t, ct, self._score_of(sub, r))
            self.counts["completed_" + sub.kind] += 1
        self.futures[:] = still

    def _score_of(self, sub: Live2Submission, r: Dict[str, Any]) -> Dict[str, Any]:
        """The committed extraction on this answer (live2/scores.py), or {} for a build piece.

        A dry run sends no HTTP and so carries no logprobs and no text; the score is then None,
        which the scorer reads as UNKNOWN and refuses AP on, rather than a fabricated number.
        """
        if sub.kind == "monitor":
            return S2.sh_score(S2.first_token_logprobs(r.get("chunks") or ()))
        if sub.kind == "recall":
            return S2.recall_letter(r.get("text") or "")
        return {}

    def _settle(self, sub: Live2Submission, first_s, done_s: float, path, t: float,
                cached_tokens=None, scored: Optional[Dict[str, Any]] = None) -> None:
        if sub.kind in ("piece", "whole") and sub.request_id in self.builds:
            b = self.builds.pop(sub.request_id)
            s = self.st.sessions.get(b["session_id"])
            if s is not None:
                s.built_tokens += b["piece_tokens"]
                # A PARTIALLY built history is not warm: the believed tier becomes GPU only when
                # the whole history is built. The interface's READINESS has no partial value
                # (COLD | HOST-WARM | GPU-WARM), so an incomplete rebuild stays COLD, which is
                # what keeps a chaining arm issuing the next piece. The already-built prefix is
                # still reused on the wire as uuid references, so the request is cheap even
                # while the readiness the arm sees says COLD; that gap is a limitation of the
                # committed action space and is reported.
                if s.built_tokens >= s.est_tokens:
                    s.belief = {"gpu": 1.0, "host": 0.0, "cold": 0.0}
                # the engine's OWN report, not the coordinator's belief (spec 7.6)
                self._log_residency(t, s.session_id, telemetry=cached_tokens)
            if b.get("answers"):
                o = self.st.opps.get(b["answers"])
                if o is not None and s is not None:
                    o.state = "arrived"
                    if s.built_tokens >= s.est_tokens:
                        self._submit_recall(o, s, t, 0.0, {}, self.st.traffic_mix(),
                                            whole=False)
                    # otherwise the chain is unfinished: the question becomes visible again and
                    # the arm decides about the NEXT piece, which is the point of per-piece
                    # release (one unit at a time, spec 7.2 step 3).
            return
        o = self.st.opps.get(sub.opportunity_id) if sub.opportunity_id else None
        if o is None:
            return
        delivered = first_s if first_s is not None else done_s
        o.served_at = delivered
        o.cache_path = path
        ontime = delivered <= o.deadline_abs() + 1e-9
        ev = self._cloud_answer(sub, o, delivered, path, scored)
        o.state = "answered" if ontime else "late"
        if o.kind == "monitor":
            self.st.devices[o.device_id].delivered.append((delivered, 0.0))
        self.answers.append(dict(opportunity_id=o.opp_id, kind=o.kind, device_id=o.device_id,
                                 decision="CLOUD", delivered_s=delivered,
                                 deadline_s=o.deadline_abs(),
                                 served_by="cloud" if ontime else "device",
                                 on_time=bool(ontime), cache_path=path,
                                 request_id=sub.request_id))
        # the coordinator's one output to the fleet: the cloud answer, delivered at t_done. The
        # DEVICE's own answer never passes through here (CONTRACT.md). When the I/O layer has
        # already forwarded it (StudyLIVE2-harness addendum), it is still recorded here, and the
        # bridge does not send it a second time; the two must be the same event.
        early = self.forwarded.get(sub.request_id)
        if early is not None and _comparable(early) != _comparable(ev):
            self.n_forward_mismatch += 1
        self.cloud_answers.append(ev)

    def _cloud_answer(self, sub: Live2Submission, o, delivered: float, path,
                      scored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ontime = delivered <= o.deadline_abs() + 1e-9
        return SC.make(
            "cloud_answer", device_id=o.device_id, opportunity_id=o.opp_id,
            t_done=round(delivered, 6),
            payload=dict(request_id=sub.request_id, kind=o.kind, cache_path=path,
                         on_time=bool(ontime),
                         cloud_score=(scored or {}).get("cloud_score"),
                         cloud_letter=(scored or {}).get("cloud_letter"),
                         p_yes=(scored or {}).get("p_yes")))

    def answer_on_completion(self, r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """StudyLIVE2-harness addendum: the cloud_answer for a finished response, built the
        moment its stream ends, on the I/O thread, without waiting for a tick or an epoch.

        It reads only the submission, the response and the opportunity's deadline (fixed when
        the opportunity was created), and builds the event with the same `_cloud_answer` the
        decision thread uses, so the event is identical to the one `_settle` will record (any
        difference is counted in `n_forward_mismatch`). It changes no coordinator state except
        `forwarded`; the arm still learns of the completion in `_collect`, at its next epoch.
        Build pieces carry no answer and return None.
        """
        sub = r.get("sub")
        if sub is None or sub.kind in ("piece", "whole") or not sub.opportunity_id:
            return None
        o = self.st.opps.get(sub.opportunity_id)
        if o is None:
            return None
        usage = r.get("usage") or {}
        path, _frac = SC.cache_path_of(cached_tokens_of(usage), prompt_tokens_of(usage))
        done_s = sub.sent_s + (r["total_s"] * self.speed if r.get("total_s") else 0.0)
        first_s = (sub.sent_s + r["ttft_s"] * self.speed) if r.get("ttft_s") else None
        delivered = first_s if first_s is not None else done_s
        ev = self._cloud_answer(sub, o, delivered, path, self._score_of(sub, r))
        early = self.forwarded.get(sub.request_id)
        if early is not None:
            # Already sent at its first content token (ruling Option 1): compare what the fleet
            # received with what the full response gives, and count the differences.
            pe, pf = early.get("payload") or {}, ev.get("payload") or {}
            if sub.kind == "recall":
                self.n_recall_first_token += 1
                if pe.get("cloud_letter") != pf.get("cloud_letter"):
                    self.n_recall_letter_differs += 1
                    self.recall_letter_diffs.append(dict(
                        request_id=sub.request_id, first_token=pe.get("cloud_letter"),
                        full_text=pf.get("cloud_letter")))
            elif pe.get("cloud_score") != pf.get("cloud_score"):
                self.n_monitor_score_differs += 1
            return None
        self.forwarded[sub.request_id] = ev
        return ev

    def answer_on_first(self, r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """StudyLIVE2-harness addendum, ruling Option 1: the cloud_answer at the FIRST CONTENT
        TOKEN. t_done is the existing first-token time (unchanged), the monitor score comes from
        the first token's logprobs and the recall letter from the text so far (the first token).
        `cache_path` is not known until the usage block at stream end, so the payload carries
        None; the scorer takes cache_path from request.jsonl. Returns None for build pieces."""
        sub = r.get("sub")
        if sub is None or sub.kind in ("piece", "whole") or not sub.opportunity_id:
            return None
        o = self.st.opps.get(sub.opportunity_id)
        if o is None or r.get("ttft_s") is None:
            return None
        delivered = sub.sent_s + r["ttft_s"] * self.speed
        ev = self._cloud_answer(sub, o, delivered, None, self._score_of(sub, r))
        self.forwarded[sub.request_id] = ev
        return ev

    def _expire(self, t: float) -> None:
        for oid in self.st.order:
            o = self.st.opps[oid]
            if o.state in ("arrived", "offered") and o.deadline_abs() < t - 1e-9:
                o.state = "late"
                self.answers.append(dict(opportunity_id=o.opp_id, kind=o.kind,
                                         device_id=o.device_id, decision="NOT-TAKEN",
                                         delivered_s=None, deadline_s=o.deadline_abs(),
                                         served_by="device", on_time=False))

    # ---------------------------------------------------------------- logging
    def _log_decision(self, t: float, kind: str, opp_ids: List[str], *, piece_tokens=None,
                      defer_s=None, latency_ms: float = 0.0, preds=None, mix=None,
                      key: Optional[str] = None, session_id: Optional[str] = None) -> str:
        self.n_dec += 1
        did = f"d{self.n_dec}"
        preds = preds or {}
        pr = (preds.get("by_target") or {}).get(key) if key else None
        rec = SC.DecisionRecord(
            t=round(t, 6), arm=self.arm.name,
            arm_version=getattr(self.arm, "arm_version", "unversioned"), decision_id=did,
            kind=kind, opportunity_ids=list(opp_ids), piece_tokens=piece_tokens,
            predicted=(pr if pr else SC.asdict(SC.Predicted())),
            cost_model_id=preds.get("cost_model_id"), mu=preds.get("mu"), H=preds.get("H"),
            belief=(preds.get("belief") or SC.asdict(SC.Belief())),
            decision_latency_ms=round(float(latency_ms), 4),
            traffic_mix=dict(mix or {}), defer_s=defer_s,
            note=(f"session={session_id}" if session_id else None))
        if self.logs is not None:
            self.logs.decision.write(rec)
        return did

    def _log_residency(self, t: float, session_id: str, telemetry=None) -> None:
        s = self.st.sessions.get(session_id)
        if s is None or self.logs is None:
            return
        self.logs.residency.write(SC.ResidencyRecord(
            t=round(t, 6), session_id=session_id, believed_tier=s.believed_tier(),
            telemetry_cached_tokens=telemetry, device_id=s.device_id,
            believed_dist=dict(s.belief)))

    # ---------------------------------------------------------------- result
    def _result(self, cpu0: float, wall_s: float) -> Dict[str, Any]:
        lat = sorted(self.decision_latencies_ms)
        def q(p):
            return round(lat[min(int(p * len(lat)), len(lat) - 1)], 4) if lat else None
        mon = [a for a in self.answers if a["kind"] == "monitor"]
        rec = [a for a in self.answers if a["kind"] == "recall"]
        return dict(
            arm=self.arm.name, arm_version=getattr(self.arm, "arm_version", "unversioned"),
            is_measurement=False,
            tick_s=self.tick_s, decision_period_s=self.decision_period_s, h_s=self.h_s,
            upload_mode=self.upload_mode,
            window_s=self.window_s, n_devices=len(self.st.devices),
            n_sessions=len(self.st.sessions), n_opportunities=len(self.st.opps),
            n_requests=self.n_req, n_decisions=self.n_dec,
            counts=dict(sorted(self.counts.items())),
            n_monitor_answers=len(mon), n_recall_answers=len(rec),
            n_on_time=sum(1 for a in self.answers if a.get("on_time")),
            submit_delay_ms=_pct(self.submit_delays_ms),
            decision_time=self.decision_time_summary(),
            n_pulls=len(self.pulls), n_cloud_answers=len(self.cloud_answers),
            decision_latency_ms=dict(p50=q(0.5), p99=q(0.99),
                                     max=(round(lat[-1], 4) if lat else None), n=len(lat)),
            cpu_s=round(_cpu_s() - cpu0, 3), wall_s=round(wall_s, 3),
            cpu_percent=(round(100.0 * (_cpu_s() - cpu0) / wall_s, 1) if wall_s > 0 else None),
            request_rate_per_s=(round(self.n_req / wall_s, 2) if wall_s > 0 else None),
            budget_gpu_s=round(self.st.budget.gpu_seconds, 2),
            budget_spent_gpu_s=round(self.st.budget.spent_gpu_seconds, 2),
            epoch_overruns=self.epoch_overruns,
            max_epoch_lag_s=round(self.max_epoch_lag_s, 4),
            wall_guard_hit=self.wall_guard_hit, wall_guard_s=self.max_wall_s,
            virtual_t_reached_s=round(self.t_reached, 3),
            n_errors=len(self.errors), first_errors=self.errors[:3],
            mu_time_average=(self.arm.mu_time_average()
                             if hasattr(self.arm, "mu_time_average") else None),
            arm_stats=getattr(self.arm, "stats", None),
        )


_EPOCHS = ("stream_arrival", "stream_departure", "recall_arrival", "request_completion",
           "connectivity_change", "tick")


def _pct(xs) -> Dict[str, Any]:
    v = sorted(xs)
    if not v:
        return dict(n=0)
    def g(p):
        return round(v[min(int(p * len(v)), len(v) - 1)], 4)
    return dict(n=len(v), p50=g(0.5), p90=g(0.9), p99=g(0.99), max=round(v[-1], 4))


def _comparable(ev: Dict[str, Any]) -> Dict[str, Any]:
    """A cloud_answer without the two fields Option 1 lets differ: cache_path (unknown at the
    first token) and the recall letter (counted separately)."""
    p = dict(ev.get("payload") or {})
    p.pop("cache_path", None)
    p.pop("cloud_letter", None)
    return dict(ev, payload=p)


def _sched(ev: Dict[str, Any]) -> float:
    for k in ("t_arrive", "t_capture", "start_t", "t", "t_ask"):
        if ev.get(k) is not None:
            return float(ev[k])
    return 0.0


def _cpu_s() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


class _DryFuture:
    """A completed-at-a-virtual-time stand-in for a thread-pool future (`--dry-run`)."""

    def __init__(self, sub: Live2Submission, service_s: float, t: float, clock) -> None:
        self.sub = sub
        self.service_s = float(service_s)
        self.t = float(t)
        self.clock = clock

    def done(self) -> bool:
        return self.clock() >= self.t + self.service_s - 1e-9

    def result(self) -> Dict[str, Any]:
        return dict(request_id=self.sub.request_id, kind=self.sub.kind, sent_s=self.sub.sent_s,
                    ttft_s=self.service_s, total_s=self.service_s, http_status=None,
                    error=None, usage={}, sub=self.sub, dry_run=True)
