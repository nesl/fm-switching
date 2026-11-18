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
presented, covering device_register, session_start, session_end, history_append,
recall_question, and monitor_offer in PULL mode or monitor_frame in PUSH mode. A pulled frame is
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
                 cache_path_cycle: Sequence[str] = ("WARM", "COLD")) -> None:
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
        payload = dict(kind=("monitor" if k == "monitor_frame" else "recall"),
                       cloud_score=None, cloud_letter=None, cache_path=path,
                       stub=True)
        return (EV.make("cloud_answer", device_id=event["device_id"], opportunity_id=opp,
                        t_done=t_done, payload=payload),)

    def tick(self, t: float) -> Sequence[Dict[str, Any]]:
        return ()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- the emulator
@dataclass
class Lateness:
    samples: List[float] = field(default_factory=list)

    def add(self, v: float) -> None:
        self.samples.append(v)

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


class FleetEmulator:
    def __init__(self, trace_dir: Path, coordinator: Coordinator, mode: str,
                 link_by_device: Optional[Dict[str, LK.LinkSpec]] = None,
                 tick_s: float = DEFAULT_TICK_S, realtime: bool = True,
                 drain_s: float = 5.0) -> None:
        self.dir = Path(trace_dir)
        self.records = [json.loads(l) for l in open(self.dir / "trace.jsonl")]
        self.meta = json.loads((self.dir / "trace_meta.json").read_text())
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

    def _plan(self) -> None:
        for r in self.records:
            k = r["kind"]
            if k == "device_register":
                self._push(0.0, "register", r)
            elif k in ("session_start", "session_end"):
                self._push(r["t"], k, r)
            elif k == "history_batch":
                self._push(r["t"], "history_batch", r)
            elif k == "monitor_opportunity":
                self._push(r["t"], "monitor_opportunity", r)
            elif k == "recall_question":
                self._push(r["t"], "recall_question", r)
            else:
                raise ValueError(f"unknown trace record kind {k!r}")

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
        elif k == "cloud_answer":
            spec = self.link(reply["device_id"])
            t_del = float(reply["t_done"]) + LK.deliver_s(
                int(self.meta.get("answer_payload_bytes", TR.ANSWER_PAYLOAD_B)),
                spec.rtt_ms, spec.downlink_mbps)
            self._push(t_del, "answer_delivered", reply)
        else:
            raise ValueError(f"coordinator sent an unknown event kind {k!r}")

    def _upload(self, r: Dict[str, Any], kind: str, ref: str, nbytes: int,
                t_offer: float) -> LK.UplinkTransfer:
        return self.queue(r["device_id"]).send(kind, ref, nbytes, t_offer)

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
                         frame_bytes=int(r["frame_bytes"]))
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
        tr = self._upload(r, "recall_question", opp, QUESTION_TEXT_B, t)
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
        next_tick = 0.0
        while self._heap:
            t, _seq, what, payload = heapq.heappop(self._heap)
            if t > horizon:
                break
            while next_tick <= t:
                for reply in (self.coord.tick(next_tick) or ()):
                    self._handle_reply(reply, next_tick)
                next_tick += self.tick_s
            if self.realtime:
                due = t0 + t
                now = time.monotonic()
                if now < due:
                    time.sleep(due - now)
                    now = time.monotonic()
                self.lateness.add(max(0.0, now - due))
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
            elif what == "history_batch":
                self.presented.append(payload)
                tr = self._upload(payload, "history_batch", payload["batch_id"],
                                  int(payload["frame_bytes"]), t)
                self._push(tr.t_arrive, "history_arrived", dict(rec=payload,
                                                                t_arrive=tr.t_arrive))
            elif what == "history_arrived":
                r = payload["rec"]
                self._to_coord(EV.make("history_append", device_id=r["device_id"],
                                       session_id=r["session_id"], batch_id=r["batch_id"],
                                       t_arrive=payload["t_arrive"],
                                       frame_refs=r["frame_refs"],
                                       est_tokens=int(r["est_tokens"])), t)
            elif what == "monitor_opportunity":
                self._on_monitor_opportunity(payload, t)
            elif what == "offer_arrived":
                self._to_coord(payload["ev"], t)
            elif what == "pull_arrived":
                self._on_pull_arrived(payload, t)
            elif what == "frame_arrived":
                r = payload["rec"]
                self._to_coord(EV.make("monitor_frame", device_id=r["device_id"],
                                       opportunity_id=r["opportunity_id"],
                                       instant_id=r["opportunity_id"], t_capture=r["t"],
                                       t_arrive=payload["t_arrive"],
                                       deadline_s=r["deadline_s"], frame_ref=r["frame_ref"],
                                       frame_bytes=int(r["frame_bytes"])), t)
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
                                       options=r["options"]), t)
            elif what == "answer_delivered":
                opp = self._resolve_opportunity(payload)
                o = self.outcomes[opp]
                o.t_cloud_done = float(payload["t_done"])
                o.t_delivered = t
                o.cloud_payload = payload["payload"]
                o.within_L = (t - o.t_opportunity) <= o.deadline_s + 1e-9
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
            n_opportunities=len(self.outcomes),
            n_served=sum(1 for o in self.outcomes.values() if o.t_delivered is not None),
            n_within_L=sum(1 for o in self.outcomes.values() if o.within_L),
            wire_events_to_coordinator=self.wire_sent,
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
