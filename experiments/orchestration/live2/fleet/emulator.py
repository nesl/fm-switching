#!/usr/bin/env python3
"""The real-time fleet emulator: replays one trace against one coordinator, in wall-clock time.

StudyLIVE2-fleet, part 4. CPU only on flash. A run against the stub coordinator in this module
is NOT a measurement of anything; it exercises the harness. Only a run against the real
coordinator on the H100, with a FINAL calibration map, produces numbers.

WHAT IT DOES

One process holds the whole emulated fleet. Every device action in the trace is an entry in a
time-ordered queue, released against the wall clock: at run-clock time `t` the loop sleeps until
`t0 + t` and then fires. The delay between when an action was due and when it fired is its
LATENESS, logged for every action; the run is marked INVALID if p99 lateness exceeds
`MAX_P99_LATENESS_MS` (50 ms). That is a validity check ON THE HARNESS, not a result threshold:
an invalid run says the emulator could not keep time at that fleet size on that host, which is
exactly what the D77 pilot is supposed to find out.

LINKS (D75, uniform in round 1, per-device here so later rounds need no change)

  upload       bytes * 8 / uplink + RTT / 2, and the serialisation part OCCUPIES the uplink
  pull message RTT / 2, no payload
  delivery     RTT / 2 + payload bytes / downlink

ONE UPLINK PER DEVICE, SHARED SERIALLY. Monitoring frames, history batches and question texts
contend FIFO for the same uplink (`links.UplinkQueue`), so a 30-s history batch delays the frames
offered behind it. The queueing delay is recorded per transfer and summarised per device; it is
never folded into the transfer time, because the point of reporting it is that it is a cost the
device pays for uploading history.

UPLOAD MODES (D69)

  A  push:  the device uploads every decision-instant frame; the coordinator serves what it can.
  B  pull:  the device sends a `monitor_offer`; the coordinator replies `pull_request` for the
            instants it wants; the frame upload then starts at offer_arrival + RTT/2, so mode B
            pays one extra RTT before the bytes move.

FAIRNESS (D69, D79, D96 (2)). The emulator never changes the opportunity stream. Its sent-stream
digest is the CANONICAL fairness digest: `trace.fairness_digest` over the events it actually
presented, covering device_register, session_start, session_end, history_preload (D101),
history_append, recall_question, and monitor_offer in PULL mode or monitor_frame in PUSH mode. A pulled frame is
not digested, because which frames exist depends on the arm's pulls. The digest must equal the
trace's digest FOR THIS MODE; a mismatch is a stop condition and `run()` raises.

THE COORDINATOR INTERFACE. Any object with

    on_event(event: dict, t: float) -> Sequence[dict]      # pull_request / cloud_answer
    tick(t: float) -> Sequence[dict]                       # same, called every tick_s
    close() -> None                                        # optional

Replies carry their own run-clock time (`t_sent` for a pull, `t_done` for an answer); the
emulator adds the link time and nothing else. `StubCoordinator` below is the flash stand-in.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import resource
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import data_sources as DS
import events as EV
import links as LK
import trace as TR

MAX_P99_LATENESS_MS = 50.0
DEFAULT_TICK_S = 0.010
QUESTION_TEXT_B = 1200          # a question plus its options, as a request body


class Coordinator(Protocol):
    def on_event(self, event: Dict[str, Any], t: float) -> Sequence[Dict[str, Any]]: ...
    def tick(self, t: float) -> Sequence[Dict[str, Any]]: ...


# ---------------------------------------------------------------- stub coordinator
class StubCoordinator:
    """A deterministic stand-in for the real coordinator. NOT a model and NOT a measurement.

    It serves the first `capacity_per_s` requests that arrive in each whole second and declines
    the rest, with a fixed service time. It exists so the emulator, the digests, the uplink
    bookkeeping and the scorer can be tested on flash without the H100. Every run header it
    produces carries `server_kind = "stub"` and `is_measurement = False`, and the scorer refuses
    to treat a stub run as a measurement.
    """

    kind = "stub"

    def __init__(self, capacity_per_s: float = 8.0, service_s: float = 0.25,
                 pull_all: bool = True, answer_correct: bool = True,
                 cache_path_cycle: Sequence[str] = ("WARM", "COLD"),
                 stub_scores: bool = True) -> None:
        # D86 / D105: a cloud answer with no score makes the scorer refuse AP, so the stub
        # carries one. It is a DETERMINISTIC FUNCTION OF THE OPPORTUNITY ID, never a model
        # output, and every payload it produces is tagged `stub=True`; no stub score may enter a
        # measured result.
        self.stub_scores = bool(stub_scores)
        self.capacity_per_s = float(capacity_per_s)
        self.service_s = float(service_s)
        self.pull_all = pull_all
        self.answer_correct = answer_correct
        self.cache_path_cycle = tuple(cache_path_cycle)
        self.served_in_second: Dict[int, int] = {}
        self.requests: List[Dict[str, Any]] = []
        self._n = 0

    def _admit(self, t: float) -> bool:
        s = int(t)
        n = self.served_in_second.get(s, 0)
        if n >= self.capacity_per_s:
            return False
        self.served_in_second[s] = n + 1
        return True

    def on_event(self, event: Dict[str, Any], t: float) -> Sequence[Dict[str, Any]]:
        k = event["kind"]
        if k == "monitor_offer":
            if not self.pull_all:
                return ()
            return (EV.make("pull_request", device_id=event["device_id"],
                            instant_id=event["instant_id"], t_sent=t),)
        # D96 (1): the id is echoed unchanged; the stub never builds one.
        if k not in ("monitor_frame", "recall_question"):
            return ()
        opp = EV.opportunity_id_of(event)
        if not self._admit(t):
            return ()
        self._n += 1
        path = self.cache_path_cycle[self._n % len(self.cache_path_cycle)]
        t_done = t + self.service_s
        self.requests.append(dict(request_id=f"stub-{self._n:06d}",
                                  device_id=event["device_id"], opportunity_id=opp,
                                  t_submit=t, t_done=t_done, cache_path=path,
                                  cached_tokens=(1 if path == "WARM" else 0),
                                  prompt_tokens=378, cache_salt=event["device_id"]))
        kind = "monitor" if k == "monitor_frame" else "recall"
        payload = dict(kind=kind, cache_path=path, stub=True,
                       cloud_score=(self._stub_score(opp) if self.stub_scores
                                    and kind == "monitor" else None),
                       cloud_letter=(self._stub_letter(event) if self.stub_scores
                                     and kind == "recall" else None))
        return (EV.make("cloud_answer", device_id=event["device_id"], opportunity_id=opp,
                        t_done=t_done, payload=payload),)

    def _stub_score(self, opp: str) -> float:
        """A reproducible log p_yes in [-14, 0), the range live2/calib.py's grid covers."""
        h = int(hashlib.sha256(opp.encode()).hexdigest()[:8], 16)
        return -14.0 + 14.0 * (h / 0xFFFFFFFF)

    def _stub_letter(self, event: Dict[str, Any]) -> str:
        opts = event.get("options") or ()
        gold = event.get("gold_letter") or "A"
        if self.answer_correct or not opts:
            return str(gold)
        return "ABCDE"[(("ABCDE".index(str(gold)[0]) if str(gold)[0] in "ABCDE" else 0) + 1) % 5]

    def tick(self, t: float) -> Sequence[Dict[str, Any]]:
        return ()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- the emulator
@dataclass
class Lateness:
    samples: List[float] = field(default_factory=list)
    # StudyLIVE2-harness: optional per-action detail, so a late action can be attributed to its
    # own due instant and kind. Off unless `detail` is a list; the statistics are unaffected.
    detail: Optional[List[Any]] = None

    def add(self, v: float, due: Optional[float] = None, what: Optional[str] = None) -> None:
        self.samples.append(v)
        if self.detail is not None:
            self.detail.append((round(float(due or 0.0), 6), what, round(1000 * v, 4)))

    def stats(self) -> Dict[str, Any]:
        s = sorted(self.samples)
        if not s:
            return dict(n=0)
        def q(p: float) -> float:
            return s[min(len(s) - 1, int(p * len(s)))]
        return dict(n=len(s), p50_ms=round(1000 * q(0.50), 4),
                    p90_ms=round(1000 * q(0.90), 4), p99_ms=round(1000 * q(0.99), 4),
                    max_ms=round(1000 * s[-1], 4), mean_ms=round(1000 * sum(s) / len(s), 4))


@dataclass
class Outcome:
    opportunity_id: str
    device_id: str
    kind: str
    t_opportunity: float
    deadline_s: float
    play_id: Optional[str] = None
    session_id: Optional[str] = None
    question_id: Optional[str] = None
    clip: Optional[str] = None
    t_local: Optional[float] = None
    presented: bool = True
    pulled: Optional[bool] = None
    t_frame_arrive: Optional[float] = None
    uplink_queue_s: Optional[float] = None
    t_cloud_done: Optional[float] = None
    t_delivered: Optional[float] = None
    within_L: bool = False
    cloud_payload: Optional[Any] = None

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        for k in ("t_opportunity", "t_frame_arrive", "uplink_queue_s", "t_cloud_done",
                  "t_delivered"):
            if d[k] is not None:
                d[k] = round(float(d[k]), 6)
        return d


def _cumulative_tokens(rec: Dict[str, Any]) -> int:
    """The session's CUMULATIVE history tokens after this record, which is what goes on the wire.

    THE ONE SEMANTICS (CONTRACT.md "history size"). The trace carries both quantities on every
    history record: `est_tokens` is that batch's own increment and `cum_tokens` is the session's
    running total, which resets at `session_start` (D83) and includes the `history_preload`
    (D101). The wire and the coordinator's belief use the CUMULATIVE one. A record without
    `cum_tokens` is refused rather than silently read as an increment, because that silent
    reading is the defect this function exists to close.
    """
    if "cum_tokens" not in rec:
        raise KeyError(
            "history record %r carries no `cum_tokens`: the wire's `est_tokens` is the "
            "session's CUMULATIVE history tokens (CONTRACT.md), and reading a per-batch "
            "increment as a total is the 2026-11-18 defect. Regenerate the trace with a "
            "`fleet/trace.py` that emits `cum_tokens`."
            % ({k: rec.get(k) for k in ("kind", "device_id", "session_id", "batch_id")},))
    return int(rec["cum_tokens"])


class FleetEmulator:
    def __init__(self, trace_dir: Path, coordinator: Coordinator, mode: str,
                 link_by_device: Optional[Dict[str, LK.LinkSpec]] = None,
                 tick_s: float = DEFAULT_TICK_S, realtime: bool = True,
                 drain_s: float = 5.0, link_events: bool = False,
                 link_sync_hold: bool = False) -> None:
        # link_events switch, DEFAULT OFF: with it off `_plan` adds nothing and `run` never sees a
        # `connectivity` action, so the heap, the wire and every digest are what they were.
        self.link_events = bool(link_events)
        self.n_link_events = 0
        # link_sync switch, DEFAULT OFF, needs link_events. On, the device's buffered backlog is
        # HELD at the device after the reconnect (live frames upload first) and goes up only when
        # the coordinator sends `sync_pull`. An arm that does not declare sync control never runs
        # with this on, so a baseline's backlog auto-releases exactly as before (FIFO by capture
        # time, the committed D242 behaviour).
        self.link_sync_hold = bool(link_sync_hold)
        if self.link_sync_hold and not self.link_events:
            raise ValueError("link_sync_hold requires link_events")
        self.held: Dict[str, List[Dict[str, Any]]] = {}
        self._held_ids: Dict[str, Dict[str, Any]] = {}
        self._held_by_sess: Dict[str, List[Dict[str, Any]]] = {}
        self._released: set = set()
        self._latest_cum: Dict[str, int] = {}
        self._gap_from: Dict[str, int] = {}
        self.link_log: List[Dict[str, Any]] = []
        self.dir = Path(trace_dir)
        self.records = [json.loads(l) for l in open(self.dir / "trace.jsonl")]
        self.meta = json.loads((self.dir / "trace_meta.json").read_text())
        # D201: THE DEVICE'S OWN PER-INSTANT DASHCAM SCORE, ON THE WIRE.
        #
        # `fleet/trace.py` already writes one row per monitor instant into
        # `device_answers.jsonl`, carrying `device_score` straight out of StudyORIN1's dense
        # per-instant set (`data_sources.orin_dense_scores`), and the generator RAISES if the
        # committed set does not cover an instant. That table was never read at run time, so the
        # coordinator filled the application-visible stream with a literal 0.0 and the two arms
        # whose published method reads the device's score trajectory decided on a constant.
        # The table is loaded here, once, and the score travels on the monitor event.
        #
        # IT IS CAUSAL. The row is keyed on the opportunity, i.e. on ONE capture instant, and it
        # is attached to that instant's own event. No row for a later instant is ever read.
        #
        # A MISSING TABLE RAISES, and does not degrade to None. A device score that is absent is
        # exactly the failure this fixes, and a neutral value here would hide it again.
        ap = self.dir / "device_answers.jsonl"
        if not ap.exists():
            raise FileNotFoundError(
                "%s holds no device_answers.jsonl; the DEVICE's own per-instant dashcam score "
                "cannot be put on the wire, and an arm whose published method reads it would "
                "decide on nothing (D201)" % self.dir)
        self._device_score: Dict[str, float] = {}
        for _ln in open(ap):
            _a = json.loads(_ln)
            if _a.get("kind") != "monitor":
                continue
            _v = _a.get("device_score")
            if _v is None:
                raise ValueError(
                    "device_answers.jsonl row for %r carries no device_score (D201)"
                    % _a.get("opportunity_id"))
            self._device_score[str(_a["opportunity_id"])] = float(_v)
        if mode not in TR.MODES:
            raise ValueError(f"mode {mode!r} not in {TR.MODES}")
        self.mode = mode
        self.coord = coordinator
        self.tick_s = tick_s
        self.realtime = realtime
        self.drain_s = drain_s
        self.run_s = float(self.meta["run_s"])
        self.links: Dict[str, LK.LinkSpec] = dict(link_by_device or {})
        self.queues: Dict[str, LK.UplinkQueue] = {}
        self.lateness = Lateness()
        self.outcomes: Dict[str, Outcome] = {}
        self.presented: List[Dict[str, Any]] = []
        self.wire_sent = 0
        self.wire_received = 0
        self.n_preload = 0
        self._seq = 0
        self._heap: List[Tuple[float, int, str, Dict[str, Any]]] = []

    # -- links ------------------------------------------------------------
    def link(self, device_id: str) -> LK.LinkSpec:
        if device_id not in self.links:
            self.links[device_id] = LK.LinkSpec()
        return self.links[device_id]

    def queue(self, device_id: str) -> LK.UplinkQueue:
        if device_id not in self.queues:
            self.queues[device_id] = LK.UplinkQueue(self.link(device_id))
        return self.queues[device_id]

    # -- scheduling -------------------------------------------------------
    def _push(self, t: float, what: str, payload: Dict[str, Any]) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (float(t), self._seq, what, payload))

    def _load_held_marks(self) -> None:
        o = self.meta.get("outage")
        if not o:
            return
        for rid, per in (o.get("deferred_per_robot") or {}).items():
            marks = per.get("deferred")
            if per.get("frames", 0) and marks is None:
                raise ValueError("link_sync_hold: the trace meta carries no deferred-batch "
                                 "marks for %s; regenerate the trace with link marks on" % rid)
            for m in sorted(marks or (), key=lambda m: (m["t_captured"], m["cum_tokens"])):
                self._held_ids[m["batch_id"]] = dict(m, device_id=rid)
                self._held_by_sess.setdefault(m["session_id"], []).append(self._held_ids[m["batch_id"]])
                self._gap_from[m["session_id"]] = min(
                    self._gap_from.get(m["session_id"], 1 << 60),
                    int(m["cum_tokens"]) - int(m["own_tokens"]))

    def _plan(self) -> None:
        if self.link_sync_hold:
            self._load_held_marks()
        for r in self.records:
            k = r["kind"]
            if k == "device_register":
                self._push(0.0, "register", r)
            elif k in ("session_start", "session_end"):
                self._push(r["t"], k, r)
            elif k == "history_preload":
                self._push(r["t"], "history_preload", r)
            elif k == "history_batch":
                if self.link_sync_hold and r["batch_id"] in self._held_ids:
                    self._push(r["t"], "history_held", r)
                else:
                    self._push(r["t"], "history_batch", r)
            elif k == "monitor_opportunity":
                self._push(r["t"], "monitor_opportunity", r)
            elif k == "recall_question":
                self._push(r["t"], "recall_question", r)
            else:
                raise ValueError(f"unknown trace record kind {k!r}")
        if self.link_events:
            self._plan_link_events()

    def _plan_link_events(self) -> None:
        """link_events (A1): one `connectivity` event per victim at outage start and at its end.

        Read from the trace's own outage meta, pushed AFTER every trace action so the sequence
        numbers of all other actions are unchanged. No outage in the meta means no events.
        Start carries nothing about the future (no end, backlog 0); end carries the victim's
        deferred history frames and their D2 tokens (D242 buffered semantics only).
        """
        EV.check_link_against_schema()
        o = self.meta.get("outage")
        if not o:
            return
        if o.get("semantics", "buffered") != "buffered":
            raise ValueError("link_events is built on the device-buffered semantics; the "
                             "superseded 'true' (lost) semantics is refused")
        t0, t1 = float(o["t_start"]), float(o["t_end"])
        per = o.get("deferred_per_robot") or {}
        for rid in o["robots"]:
            fr = int(per.get(rid, {}).get("frames", 0))
            self._push(t0, "connectivity", dict(
                device_id=rid, t=t0, connected=False, offline_since=t0, back_online_at=None,
                backlog_frames=0, backlog_tokens=0))
            self._push(t1, "connectivity", dict(
                device_id=rid, t=t1, connected=True, offline_since=t0, back_online_at=t1,
                backlog_frames=fr, backlog_tokens=fr * DS.D2_TOK_PER_IMG))

    # -- wire -------------------------------------------------------------
    def _to_coord(self, ev: Dict[str, Any], t: float) -> None:
        self.wire_sent += 1
        for reply in (self.coord.on_event(ev, t) or ()):
            self._handle_reply(reply, t)

    def _handle_reply(self, reply: Dict[str, Any], t: float) -> None:
        self.wire_received += 1
        k = reply["kind"]
        if k == "pull_request":
            t_arrive = float(reply["t_sent"]) + LK.pull_s(self.link(reply["device_id"]).rtt_ms)
            self._push(t_arrive, "pull_arrived", reply)
        elif k == "sync_pull":
            if not self.link_sync_hold:
                raise ValueError("a sync_pull arrived at an emulator with link_sync_hold off")
            t_arrive = float(reply["t_sent"]) + LK.pull_s(self.link(reply["device_id"]).rtt_ms)
            self._push(t_arrive, "sync_pull_arrived", reply)
        elif k == "cloud_answer":
            spec = self.link(reply["device_id"])
            t_del = float(reply["t_done"]) + LK.deliver_s(
                int(self.meta.get("answer_payload_bytes", TR.ANSWER_PAYLOAD_B)),
                spec.rtt_ms, spec.downlink_mbps)
            self._push(t_del, "answer_delivered", reply)
        else:
            raise ValueError(f"coordinator sent an unknown event kind {k!r}")

    def _on_sync_pull(self, pull: Dict[str, Any], t: float) -> None:
        """Release the device's held backlog OLDEST-FIRST through its own uplink queue.

        `n_frames` 0 means all; otherwise whole records are released until at least that many
        frames are covered. A pull for a device with nothing held is counted and does nothing.
        """
        rid = pull["device_id"]
        q = self.held.get(rid, [])
        want = int(pull.get("n_frames", 0))
        got = 0
        n_rec = 0
        while q and (want <= 0 or got < want):
            rec = q.pop(0)
            m = self._held_ids[rec["batch_id"]]
            tr = self._upload(rec, "history_batch", rec["batch_id"], int(rec["frame_bytes"]), t)
            self._push(tr.t_arrive, "history_arrived", dict(rec=rec, t_arrive=tr.t_arrive,
                                                            released=True))
            got += int(m["frames"])
            n_rec += 1
            self.link_log.append(dict(t=t, ev="release", device_id=rid, batch_id=rec["batch_id"],
                                      t_offer=t, t_arrive=tr.t_arrive, queue_s=tr.queue_s,
                                      frames=m["frames"]))
        self.link_log.append(dict(t=t, ev="pull_arrived", device_id=rid, requested=want,
                                  released_records=n_rec, released_frames=got,
                                  still_held=sum(self._held_ids[x["batch_id"]]["frames"]
                                                 for x in q)))

    def _history_arrived_held(self, r: Dict[str, Any], payload: Dict[str, Any], t: float) -> None:
        """link_sync: forward a history record with the CLOUD'S BELIEF, not the capture total.

        `cum_tokens` counts every frame the device captured. While part of the history is still
        held at the device the cloud has not received it, so the believed total is the latest
        capture total seen among ARRIVED records minus the tokens of the records still held. On
        a record with nothing held it is exactly `cum_tokens`, which is the committed value.
        """
        sid = r["session_id"]
        m = self._held_ids.get(r["batch_id"])
        released = bool(payload.get("released"))
        if released:
            self._released.add(r["batch_id"])
            self.link_log.append(dict(t=t, ev="arrived", device_id=r["device_id"],
                                      batch_id=r["batch_id"], frames=m["frames"],
                                      t_arrive=payload["t_arrive"]))
            self._to_coord(EV.make_link_kind(
                "sync_release", device_id=r["device_id"], session_id=sid, t=float(t),
                from_tokens=int(self._gap_from[sid]), n_frames=int(m["frames"]),
                n_tokens=int(m["frames"]) * DS.D2_TOK_PER_IMG), t)
        self._latest_cum[sid] = max(self._latest_cum.get(sid, 0), _cumulative_tokens(r))
        lc = self._latest_cum[sid]
        believed = lc - sum(int(x["own_tokens"]) for x in self._held_by_sess.get(sid, ())
                            if x["batch_id"] not in self._released and int(x["cum_tokens"]) <= lc)
        self._to_coord(EV.make("history_append", device_id=r["device_id"],
                               session_id=sid, batch_id=r["batch_id"],
                               t_arrive=payload["t_arrive"], frame_refs=r["frame_refs"],
                               est_tokens=believed), t)

    def _upload(self, r: Dict[str, Any], kind: str, ref: str, nbytes: int,
                t_offer: float) -> LK.UplinkTransfer:
        return self.queue(r["device_id"]).send(kind, ref, nbytes, t_offer)

    def device_score_of(self, opportunity_id: str) -> float:
        """The DEVICE's committed score for this instant (D201). RAISES if it is not there.

        There is no fallback on purpose. Every monitor opportunity in a generated trace has a
        row, because `fleet/trace.py` refuses to emit an instant the committed StudyORIN1 set
        does not cover, so an absence here is a plumbing fault and not a data gap.
        """
        v = self._device_score.get(str(opportunity_id))
        if v is None:
            raise KeyError(
                "no committed DEVICE score for monitor opportunity %r; the trace's answer "
                "table does not cover it (D201)" % opportunity_id)
        return float(v)

    # -- handlers ---------------------------------------------------------
    def _on_monitor_opportunity(self, r: Dict[str, Any], t: float) -> None:
        opp = r["opportunity_id"]
        self.outcomes[opp] = Outcome(opportunity_id=opp, device_id=r["device_id"],
                                     kind="monitor", t_opportunity=r["t"],
                                     deadline_s=r["deadline_s"], play_id=r["play_id"],
                                     clip=r["clip"], t_local=r["t_local"])
        self.presented.append(r)
        if self.mode == "A":
            tr = self._upload(r, "monitor_frame", opp, int(r["frame_bytes"]), t)
            self.outcomes[opp].pulled = None
            self.outcomes[opp].uplink_queue_s = tr.queue_s
            self.outcomes[opp].t_frame_arrive = tr.t_arrive
            self._push(tr.t_arrive, "frame_arrived", dict(rec=r, t_arrive=tr.t_arrive))
        else:
            ev = EV.make("monitor_offer", device_id=r["device_id"], opportunity_id=opp,
                         instant_id=opp, t_capture=r["t"], deadline_s=r["deadline_s"],
                         frame_bytes=int(r["frame_bytes"]),
                         device_score=self.device_score_of(opp))
            self.outcomes[opp].pulled = False
            self._push(t + LK.pull_s(self.link(r["device_id"]).rtt_ms), "offer_arrived",
                       dict(rec=r, ev=ev))

    def _on_pull_arrived(self, reply: Dict[str, Any], t: float) -> None:
        opp = reply["instant_id"]
        o = self.outcomes.get(opp)
        if o is None:
            raise KeyError(f"pull_request for an unknown instant {opp!r}")
        rec = self._rec_by_opp[opp]
        o.pulled = True
        tr = self._upload(rec, "monitor_frame", opp, int(rec["frame_bytes"]), t)
        o.uplink_queue_s = tr.queue_s
        o.t_frame_arrive = tr.t_arrive
        self._push(tr.t_arrive, "frame_arrived", dict(rec=rec, t_arrive=tr.t_arrive))

    def _on_recall_question(self, r: Dict[str, Any], t: float) -> None:
        opp = r["opportunity_id"]
        self.outcomes[opp] = Outcome(opportunity_id=opp, device_id=r["device_id"],
                                     kind="recall", t_opportunity=r["t"],
                                     deadline_s=r["deadline_s"], session_id=r["session_id"],
                                     question_id=r["question_id"])
        self.presented.append(r)
        # D242 item A: THE OFFER TIME, and it is `t` for every question but one the trace put
        # inside a correlated outage window. `t_offer` is present only on those (fleet/trace.py,
        # the outage block) and carries the reconnect instant. THIS IS THE READ THAT MAKES THE
        # DEFERRAL CAUSAL: the value goes straight into links.UplinkQueue.send, which decides
        # when the question reaches the coordinator, so the question arrives after the reconnect
        # and past its own deadline and the committed standing-answer rule leaves the DEVICE's
        # answer standing. The record's `t`, its `deadline_s` and the Outcome row above are
        # untouched, so the deadline is still measured from the ASK, and `self.presented` holds
        # the record unchanged so the fairness digest is unaffected.
        t_offer = float(r.get("t_offer", t))
        tr = self._upload(r, "recall_question", opp, QUESTION_TEXT_B, t_offer)
        self.outcomes[opp].uplink_queue_s = tr.queue_s
        self._push(tr.t_arrive, "question_arrived", dict(rec=r, t_arrive=tr.t_arrive))

    # -- main loop --------------------------------------------------------
    def run(self, out_dir: Path) -> Dict[str, Any]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._rec_by_opp = {r["opportunity_id"]: r for r in self.records
                            if r["kind"] in ("monitor_opportunity", "recall_question")}
        self._plan()
        horizon = self.run_s + self.drain_s
        cpu0 = time.process_time()
        ru0 = resource.getrusage(resource.RUSAGE_SELF)
        t0 = time.monotonic()
        # D230 (10), user 2026-11-24: the UNIX time of run t = 0, so run-relative logs (decision, request,
        # outcomes) align with the host counters (host_counters_d211.log, host_load.jsonl), which use unix t.
        # Read at the same instant as the monotonic origin; recorded only, never read by any decision.
        self.t0_unix = time.time()
        next_tick = 0.0
        while self._heap:
            t, _seq, what, payload = heapq.heappop(self._heap)
            if t > horizon:
                break
            if self.realtime:
                # REAL-TIME TICKING (StudyLIVE2-harness). The ticks used to be caught up in a
                # burst BEFORE the sleep, so the coordinator was not driven at all while the
                # loop waited for the next action. A request that finished inside a wait was
                # therefore not collected until the next action popped, and its `cloud_answer`
                # arrived carrying a `t_done` already in the past, which the emulator then
                # scheduled behind its own clock. That notice delay WAS the pilot's lateness:
                # in the flash reproduction every late action was an `answer_delivered`
                # (p50 18.4 ms, p99 289.0 ms) while every other kind sat at p99 0.28 ms.
                # Ticking on the wall clock while waiting collects a completion within one
                # `tick_s`. A reply handled during the wait can schedule an action EARLIER than
                # the one in hand, so the popped action goes back on the heap and the loop
                # re-pops, keeping strict time order.
                due = t0 + t
                requeued = False
                while True:
                    now = time.monotonic()
                    if now >= due:
                        break
                    elapsed = now - t0
                    if next_tick <= elapsed:
                        for reply in (self.coord.tick(next_tick) or ()):
                            self._handle_reply(reply, next_tick)
                        next_tick += self.tick_s
                        if self._heap and self._heap[0][0] < t:
                            heapq.heappush(self._heap, (t, _seq, what, payload))
                            requeued = True
                            break
                        continue
                    time.sleep(max(0.0, min(due, t0 + next_tick) - now))
                if requeued:
                    continue
                now = time.monotonic()
                self.lateness.add(max(0.0, now - due), t, what)
            # Every tick up to this action's instant has been issued before the action is
            # delivered, exactly as before. In a real-time run the wait above has already
            # issued almost all of them; in a non-real-time run this IS the tick loop and its
            # behaviour is unchanged, which is what keeps the existing suites identical.
            while next_tick <= t:
                for reply in (self.coord.tick(next_tick) or ()):
                    self._handle_reply(reply, next_tick)
                next_tick += self.tick_s
            if what == "register":
                self.presented.append(payload)
                self._to_coord(EV.make("device_register", device_id=payload["device_id"],
                                       type=payload["type"],
                                       uplink_mbps=self.link(payload["device_id"]).uplink_mbps,
                                       rtt_ms=self.link(payload["device_id"]).rtt_ms,
                                       start_t=payload["start_t"]), t)
            elif what in ("session_start", "session_end"):
                self.presented.append(payload)
                self._to_coord(EV.make(what, device_id=payload["device_id"],
                                       session_id=payload["session_id"], t=payload["t"]), t)
            elif what == "history_preload":
                # D101: NO UPLINK TIME. The frames were on cloud-side disk before the clock
                # started, so the preload neither occupies the device's uplink nor queues
                # behind anything; it is handed to the coordinator at its own run-clock time.
                self.presented.append(payload)
                self.n_preload += 1
                # `est_tokens` on the wire is the session's CUMULATIVE history tokens after
                # this event (CONTRACT.md "history size"). For a preload the two are equal, the
                # preload being the session's first holding, but `cum_tokens` is forwarded
                # anyway so there is ONE rule at both producers.
                self._to_coord(EV.make("history_preload", device_id=payload["device_id"],
                                       session_id=payload["session_id"],
                                       frame_refs=payload["frame_refs"],
                                       est_tokens=_cumulative_tokens(payload),
                                       t=float(payload["t"])), t)
            elif what == "history_batch":
                self.presented.append(payload)
                tr = self._upload(payload, "history_batch", payload["batch_id"],
                                  int(payload["frame_bytes"]), t)
                self._push(tr.t_arrive, "history_arrived", dict(rec=payload,
                                                                t_arrive=tr.t_arrive))
            elif what == "history_arrived":
                r = payload["rec"]
                if self.link_sync_hold:
                    self._history_arrived_held(r, payload, t)
                    continue
                # THE FIX (2026-11-18). This forwarded the PER-BATCH increment
                # (`r["est_tokens"]`, which `trace.py:391` sets to that batch's `tok`) and threw
                # away the cumulative total the trace carries beside it (`cum_tokens`, the
                # session's running `tokens_sent`). The coordinator then had no way to know the
                # history's size: on the seed-10 12-device trace the per-batch increments of
                # robo002's second session peak at 1,381 tokens while the session really holds
                # 17,581, a 12.7x understatement, and every session in that trace is understated
                # by 2.0x to 12.7x. `cum_tokens` already resets per session (D83,
                # `trace.py:343`) and already includes the D101 preload
                # (`trace.py:352`), so it is exactly the quantity the belief needs.
                self._to_coord(EV.make("history_append", device_id=r["device_id"],
                                       session_id=r["session_id"], batch_id=r["batch_id"],
                                       t_arrive=payload["t_arrive"],
                                       frame_refs=r["frame_refs"],
                                       est_tokens=_cumulative_tokens(r)), t)
            elif what == "monitor_opportunity":
                self._on_monitor_opportunity(payload, t)
            elif what == "offer_arrived":
                self._to_coord(payload["ev"], t)
            elif what == "pull_arrived":
                self._on_pull_arrived(payload, t)
            elif what == "frame_arrived":
                r = payload["rec"]
                # D153: the four EPISODE fields are forwarded exactly as the trace generator
                # wrote them, and ONLY if it wrote them. The emulator derives none of them: the
                # episode context must not depend on anything that happens at run time, or
                # proof (b) stops holding by construction.
                ep = {k: r[k] for k in ("episode_id", "episode_index", "frame_refs",
                                        "episode_frames") if k in r}
                self._to_coord(EV.make("monitor_frame", device_id=r["device_id"],
                                       opportunity_id=r["opportunity_id"],
                                       instant_id=r["opportunity_id"], t_capture=r["t"],
                                       t_arrive=payload["t_arrive"],
                                       deadline_s=r["deadline_s"], frame_ref=r["frame_ref"],
                                       frame_bytes=int(r["frame_bytes"]),
                                       device_score=self.device_score_of(
                                           r["opportunity_id"]), **ep), t)
            elif what == "recall_question":
                self._on_recall_question(payload, t)
            elif what == "question_arrived":
                r = payload["rec"]
                self._to_coord(EV.make("recall_question", device_id=r["device_id"],
                                       opportunity_id=r["opportunity_id"],
                                       session_id=r["session_id"],
                                       question_id=r["question_id"], t_ask=r["t"],
                                       t_arrive=payload["t_arrive"],
                                       deadline_s=r["deadline_s"], question=r["question"],
                                       # The S-EMBER question category. The trace emits it on
                                       # every recall record and it was DROPPED here, so the
                                       # coordinator never saw it and `RecallQuery.category` was
                                       # filled with the literal "recall" instead. That is why
                                       # the policy pinned a single question type.
                                       category=r.get("category"),
                                       options=r["options"]), t)
            elif what == "answer_delivered":
                opp = self._resolve_opportunity(payload)
                o = self.outcomes[opp]
                o.t_cloud_done = float(payload["t_done"])
                o.t_delivered = t
                o.cloud_payload = payload["payload"]
                o.within_L = (t - o.t_opportunity) <= o.deadline_s + 1e-9
            elif what == "history_held":
                self.presented.append(payload)
                m = self._held_ids[payload["batch_id"]]
                self.held.setdefault(m["device_id"], []).append(payload)
                self.link_log.append(dict(t=t, ev="held", device_id=m["device_id"],
                                          batch_id=payload["batch_id"], frames=m["frames"],
                                          tokens=m["frames"] * DS.D2_TOK_PER_IMG))
            elif what == "sync_pull_arrived":
                self._on_sync_pull(payload, t)
            elif what == "connectivity":
                self.n_link_events += 1
                self.wire_sent += 1
                for reply in (self.coord.on_event(EV.make_link(**payload), t) or ()):
                    self._handle_reply(reply, t)
            else:
                raise ValueError(f"unknown scheduled action {what!r}")
        wall = time.monotonic() - t0
        cpu = time.process_time() - cpu0
        ru1 = resource.getrusage(resource.RUSAGE_SELF)
        if hasattr(self.coord, "close"):
            self.coord.close()

        sent_digest = self._sent_digest()
        trace_digest = self.meta[f"fairness_digest_{self.mode}"]
        lat = self.lateness.stats()
        invalid = bool(self.realtime and lat.get("n") and
                       lat["p99_ms"] > MAX_P99_LATENESS_MS)
        up = {d: q.stats() for d, q in self.queues.items()}
        qp99 = sorted(s["queue_p99"] for s in up.values() if s.get("queue_p99") is not None)
        meta = dict(
            trace_dir=str(self.dir), out_dir=str(out_dir), mode=self.mode,
            t0_unix=round(float(getattr(self, "t0_unix", 0.0)), 6),
            run_s=self.run_s, tick_s=self.tick_s, realtime=self.realtime,
            n_devices=self.meta["n_devices"], ratio=self.meta["ratio"],
            seed=self.meta["seed"],
            server_kind=getattr(self.coord, "kind", type(self.coord).__name__),
            is_measurement=False if getattr(self.coord, "kind", "") == "stub" else None,
            wall_s=round(wall, 6), cpu_s=round(cpu, 6),
            cpu_fraction=(round(cpu / wall, 4) if wall > 0 else None),
            maxrss_kb=ru1.ru_maxrss, voluntary_ctx=ru1.ru_nvcsw - ru0.ru_nvcsw,
            lateness=lat, lateness_limit_p99_ms=MAX_P99_LATENESS_MS,
            run_valid=(not invalid),
            validity_note=("HARNESS VALIDITY, not a result threshold: p99 scheduling lateness "
                           "above 50 ms means the emulator could not keep run-clock time on "
                           "this host at this fleet size."),
            fairness_digest=sent_digest, trace_fairness_digest=trace_digest,
            fairness_digest_definition=self.meta.get("fairness_digest_definition"),
            digests_equal=(sent_digest == trace_digest),
            n_history_preload=self.n_preload,
            history_preload_uplink_bytes_charged=0,
            history_preload_note=("D101: a history_preload charges NO uplink time and occupies "
                                  "no uplink slot, so it never queues ahead of a frame; the "
                                  "frames were on cloud-side disk before the run clock started."),
            n_opportunities=len(self.outcomes),
            n_served=sum(1 for o in self.outcomes.values() if o.t_delivered is not None),
            n_within_L=sum(1 for o in self.outcomes.values() if o.within_L),
            wire_events_to_coordinator=self.wire_sent,
            **({} if not self.link_events else dict(link_events=True,
                                                    n_link_events=self.n_link_events)),
            wire_events_from_coordinator=self.wire_received,
            uplink_queue_p99_s_median=(qp99[len(qp99) // 2] if qp99 else None),
            uplink=up,
            caveats=[DS.AP_CAVEAT, DS.DEVICE_ANSWER_CAVEAT, DS.SEMBER_JPEG_CAVEAT,
                     DS.CACHE_PATH_CAVEAT])
        with open(out_dir / "outcomes.jsonl", "w") as fh:
            for opp in sorted(self.outcomes):
                fh.write(json.dumps(self.outcomes[opp].as_dict(), sort_keys=True,
                                    separators=(",", ":")) + "\n")
        if getattr(self.coord, "requests", None) is not None:
            with open(out_dir / "requests.jsonl", "w") as fh:
                for r in self.coord.requests:
                    fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
        (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        if self.link_events:
            (out_dir / "link_events.json").write_text(json.dumps(
                dict(outage=self.meta.get("outage") and {
                         k: self.meta["outage"].get(k) for k in
                         ("robots", "t_start", "t_end", "placement", "deferred_per_robot")},
                     link_log=self.link_log, n_link_events=self.n_link_events), default=str) + "\n")
        if sent_digest != trace_digest:
            raise RuntimeError(
                "FAIRNESS DIGEST != TRACE DIGEST for this mode; the emulator did not present "
                "the trace's event stream, which breaks D69 fairness and is a STOP condition "
                f"(D96 (2)):\n"
                f"  sent  {sent_digest}\n  trace {trace_digest}")
        return meta

    def _resolve_opportunity(self, answer: Dict[str, Any]) -> str:
        """Resolve a `cloud_answer` to its opportunity. GUARD, no longer the mechanism.

        Since D96 (1) the trace generator ASSIGNS every `opportunity_id` and both sides echo it
        unchanged, so the exact match below is the normal path and the rest should never fire.
        The fallback and the ambiguity check are kept as a safety net: if a coordinator ever
        sends a bare instant or question id, it is resolved against `device_id`, and if that pair
        matches more than one opportunity the run STOPS rather than crediting the wrong one.
        """
        opp = str(answer["opportunity_id"])
        if opp in self.outcomes:
            return opp
        dev = answer["device_id"]
        cand = [k for k, o in self.outcomes.items()
                if o.device_id == dev and o.kind == "recall"
                and (o.question_id == opp or k.endswith("|" + opp))]
        if len(cand) == 1:
            return cand[0]
        if not cand:
            raise KeyError(f"cloud_answer for an unknown opportunity {opp!r} on device {dev!r}")
        raise RuntimeError(
            f"AMBIGUOUS opportunity id {opp!r} on device {dev!r}: it matches {len(cand)} "
            f"opportunities, so the coordinator's bare question_id convention cannot be resolved "
            f"in this run. This is the D84 session-repeat case; the two sides must agree on the "
            f"session-qualified form. STOP.")

    def _sent_digest(self) -> str:
        """D96 (2): the canonical digest, over what this run actually presented, for this mode."""
        return TR.fairness_digest(self.presented, self.mode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="A", choices=list(TR.MODES))
    ap.add_argument("--stub-capacity", type=float, default=8.0)
    ap.add_argument("--stub-service-s", type=float, default=0.25)
    ap.add_argument("--tick-s", type=float, default=DEFAULT_TICK_S)
    ap.add_argument("--no-realtime", action="store_true",
                    help="run as fast as possible; lateness is then not measured and the run "
                         "is not a timing check")
    a = ap.parse_args(argv)
    em = FleetEmulator(Path(a.trace), StubCoordinator(a.stub_capacity, a.stub_service_s),
                       a.mode, tick_s=a.tick_s, realtime=not a.no_realtime)
    meta = em.run(Path(a.out))
    print(json.dumps({k: v for k, v in meta.items() if k != "uplink"},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
