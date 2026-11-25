#!/usr/bin/env python3
"""One device: replay a trace slice over a REAL socket, fall back to the profiled answer.

StudyREAL-NET, component 2. Runs on a Jetson Orin (orin-1/2 are Python 3.8.10) and, with a
different slice, on flash for the emulated fleet. Stdlib only: no torch, no CUDA, no vLLM.

WHAT IS REAL HERE AND WHAT IS PROFILED
  REAL      the frame bytes on the wire, the send schedule, the transport, the arrival time,
            the deadline comparison, and which branch the application takes
  PROFILED  the DEVICE's own answer, read from `device_answers.jsonl` (StudyORIN1's dense
            per-instant set). D177: within a device type the accuracy gap is a positive
            constant that never changes a policy decision, so replaying it is the correct
            treatment of a profiled input, not a weakened experiment.

THE FALLBACK (D165 B replacement semantics). For each opportunity the agent waits until
`deadline_s` past capture. If the cloud answer has arrived, it is used. If not, the device's
own profiled answer replaces it. Both outcomes are logged with the time that decided them.

NO SYNTHETIC IDS. D96 (1): `opportunity_id` is assigned by the trace generator and echoed
unchanged. This agent reads ids out of its slice and never builds one.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import queue as _queue
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events_check as EC  # noqa: E402
import wire as W  # noqa: E402

# Kinds in a trace slice, and the wire event each becomes.
#   monitor_opportunity -> monitor_frame   (mode A: pushed with the bytes)
#   history_batch       -> history_append
# The others keep their name.
PASSTHROUGH = ("device_register", "session_start", "session_end", "history_preload",
               "recall_question")


class Profile:
    """The device's own profiled answers for this slice. D201: a missing score is an error."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.by_opp: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            raise FileNotFoundError(
                "%s holds no device_answers.jsonl; the device cannot answer for itself and a "
                "neutral substitute is exactly the defect D201 fixed" % self.path.parent)
        with open(self.path) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                a = json.loads(ln)
                opp = a.get("opportunity_id")
                if not opp:
                    continue
                if a.get("kind") == "monitor" and a.get("device_score") is None:
                    raise ValueError(
                        "profiled answer for %r carries no device_score (D201)" % opp)
                self.by_opp[str(opp)] = a

    def answer(self, opportunity_id: str) -> Dict[str, Any]:
        """The device's own answer. RAISES if absent -- never returns a neutral value."""
        a = self.by_opp.get(str(opportunity_id))
        if a is None:
            raise KeyError(
                "no profiled answer for opportunity %r in %s; the device cannot fall back, and "
                "substituting one would reintroduce the D201 defect" % (opportunity_id, self.path))
        return a


class FrameStore:
    """Real JPEG bytes from local disk, with a synthetic mode for tests.

    `--synthetic-frames` generates deterministic bytes of the EXACT length the trace records,
    so the wire carries the right number of bytes without the 140 MB frame store. Every run
    records which mode it used; a measured cell must use real frames.
    """

    def __init__(self, root: Optional[Path], synthetic: bool = False) -> None:
        self.root = Path(root) if root else None
        self.synthetic = bool(synthetic)
        self.n_real = 0
        self.n_synthetic = 0
        self._miss: List[str] = []

    def get(self, frame_ref: str, nbytes: int) -> bytes:
        if not self.synthetic and self.root is not None:
            p = self.root / frame_ref.replace("|", "__")
            if p.exists():
                self.n_real += 1
                return p.read_bytes()
            if len(self._miss) < 5:
                self._miss.append(frame_ref)
        self.n_synthetic += 1
        # Deterministic in the ref, so two runs send identical bytes.
        rnd = random.Random(frame_ref)
        return bytes(rnd.getrandbits(8) for _ in range(min(int(nbytes), 1 << 20)))

    def stats(self) -> Dict[str, Any]:
        return dict(n_real=self.n_real, n_synthetic=self.n_synthetic,
                    synthetic_mode=self.synthetic, missing_sample=list(self._miss))


class UplinkSender:
    """ONE uplink per device, drained FIFO by a thread, with the queueing delay RECORDED.

    WHY THIS EXISTS. `live2/fleet/links.py` defines the semantics this harness has to
    reproduce:

      "ONE UPLINK PER DEVICE, SHARED SERIALLY. Monitoring frames and history batches contend
       for it FIFO in the order they are offered: a transfer starts at
       max(offer_time, uplink_free_at) and THE QUEUEING DELAY IT SUFFERED IS RECORDED, NEVER
       HIDDEN INSIDE THE TRANSFER TIME."

    Calling a blocking `sendall` from the replay loop violates both halves of that. It stalls
    the replay (so the offered load stops matching the trace: at the Irish 5G p10 profile,
    0.90 Mbit/s, one 66,595 B frame serialises in 0.592 s against a 0.5 s dashcam cadence) and
    it folds the queueing delay into the next frame's send time, losing the one quantity a
    real-fleet run measures better than arithmetic.

    So the replay loop OFFERS and never blocks; this thread drains. Per transfer it records
    t_offer / t_start / t_done / queue_s, the same fields as `links.UplinkTransfer`.
    """

    def __init__(self, wire: "W.Wire", clock, max_queue: int = 0) -> None:
        self.wire = wire
        self.clock = clock                       # callable -> run-relative seconds
        self.q: "_queue.Queue" = _queue.Queue(maxsize=max_queue)  # 0 = unbounded
        self.log: List[Dict[str, Any]] = []
        self.err: Optional[str] = None
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self.free_at = 0.0                       # when the uplink next becomes idle
        self.n_sent = 0

    def start(self) -> None:
        self._th = threading.Thread(target=self._drain, name="uplink")
        self._th.daemon = True
        self._th.start()

    def offer(self, kind: str, ref: str, msg: Dict[str, Any],
              blob: Optional[bytes] = None) -> float:
        """Hand a transfer to the uplink. Returns t_offer. NEVER BLOCKS on the link."""
        t_offer = self.clock()
        self.q.put((kind, ref, msg, blob, t_offer))
        return t_offer

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.q.get(timeout=0.05)
            except _queue.Empty:
                continue
            if item is None:
                break
            kind, ref, msg, blob, t_offer = item
            try:
                # FIFO: a transfer starts when the uplink is free, not when it was offered.
                t_start = max(t_offer, self.free_at, self.clock())
                nbytes = len(blob) if blob else 0
                self.wire.send(msg, blob=blob)
                t_done = self.clock()
                self.free_at = t_done
                self.n_sent += 1
                self.log.append(dict(kind=kind, ref=ref, bytes=nbytes,
                                     t_offer=round(t_offer, 6),
                                     t_start=round(t_start, 6),
                                     t_done=round(t_done, 6),
                                     queue_s=round(max(0.0, t_start - t_offer), 6),
                                     occupancy_s=round(max(0.0, t_done - t_start), 6)))
            except Exception as e:
                self.err = "%s: %s" % (type(e).__name__, e)
                self._stop.set()
                return
            finally:
                self.q.task_done()

    def drain_and_stop(self, timeout: float = 30.0) -> None:
        """Wait for every offered transfer to leave, then stop the thread."""
        end = time.monotonic() + timeout
        while not self.q.empty() and self.err is None and time.monotonic() < end:
            time.sleep(0.02)
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=5.0)

    def stats(self) -> Dict[str, Any]:
        q = sorted(t["queue_s"] for t in self.log)
        occ = sum(t["occupancy_s"] for t in self.log)
        if not q:
            return dict(n=0, busy_s=0.0, queue_p50=None, queue_p99=None, queue_max=None,
                        pending=self.q.qsize(), error=self.err)

        def pc(p):
            return q[min(len(q) - 1, int(round(p * (len(q) - 1))))]

        return dict(n=len(q), busy_s=round(occ, 6),
                    queue_p50=round(pc(0.50), 6), queue_p99=round(pc(0.99), 6),
                    queue_max=round(q[-1], 6),
                    pending=self.q.qsize(), error=self.err)


class DeviceAgent:
    """Replays one slice against a StudyREAL-NET server."""

    def __init__(self, slice_dir: Path, host: str, port: int,
                 frames_root: Optional[Path] = None, synthetic_frames: bool = False,
                 speed: float = 1.0, drain_s: float = 30.0) -> None:
        self.dir = Path(slice_dir)
        self.meta = json.loads((self.dir / "slice_meta.json").read_text())
        self.device_id = str(self.meta["device_id"])
        self.type = self.meta.get("type")
        self.records = []
        with open(self.dir / "trace.jsonl") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    self.records.append(json.loads(ln))
        self.profile = Profile(self.dir / "device_answers.jsonl")
        self.frames = FrameStore(frames_root, synthetic_frames)
        self.host, self.port = host, int(port)
        self.speed = float(speed)            # >1 runs the schedule faster, for tests
        self.drain_s = float(drain_s)
        self.wire: Optional[W.Wire] = None
        self.t0 = 0.0
        self.answers: Dict[str, Dict[str, Any]] = {}
        self.log: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._rx: Optional[threading.Thread] = None
        self.uplink: Optional[UplinkSender] = None
        self.n_pull = 0
        self.err: Optional[str] = None

    # ---- clock
    def now(self) -> float:
        """Run-relative seconds."""
        return (time.monotonic() - self.t0) * self.speed

    def sleep_until(self, t: float) -> None:
        while not self._stop.is_set():
            d = (t - self.now()) / self.speed
            if d <= 0:
                return
            time.sleep(min(d, 0.05))

    # ---- receive loop
    def _recv_loop(self) -> None:
        try:
            while not self._stop.is_set():
                msg, _blob = self.wire.recv()
                k = msg.get("kind")
                if k == "cloud_answer":
                    opp = str(msg.get("opportunity_id"))
                    msg["_t_recv"] = self.now()
                    self.answers[opp] = msg
                elif k == "pull_request":
                    self.n_pull += 1
                elif k == "run_start":
                    pass
        except (EOFError, OSError):
            pass
        except Exception as e:
            self.err = "recv: %s: %s" % (type(e).__name__, e)

    # ---- the run
    def run(self) -> Dict[str, Any]:
        self.wire = W.connect(self.host, self.port)
        reg = [r for r in self.records if r["kind"] == "device_register"]
        if not reg:
            raise ValueError("slice %s has no device_register record" % self.dir)
        r0 = reg[0]
        # Register and WAIT for the barrier: the server starts t=0 only once every expected
        # device has registered, so no device runs ahead of the fleet.
        self.wire.send(dict(kind="device_register", device_id=self.device_id,
                            type=r0["type"], uplink_mbps=r0.get("uplink_mbps"),
                            rtt_ms=r0.get("rtt_ms"), start_t=r0.get("start_t"),
                            n_records=len(self.records)))
        msg, _ = self.wire.recv()
        if msg.get("kind") != "run_start":
            raise W.WireError("expected run_start, got %r" % msg.get("kind"))
        self.t0 = time.monotonic()
        self._rx = threading.Thread(target=self._recv_loop, name="rx")
        self._rx.daemon = True
        self._rx.start()
        self.uplink = UplinkSender(self.wire, self.now)
        self.uplink.start()

        deadlines: List[Dict[str, Any]] = []
        for rec in sorted(self.records, key=lambda r: float(r.get("t") or 0.0)):
            if self._stop.is_set():
                break
            k = rec["kind"]
            t = float(rec.get("t") or 0.0)
            if k == "device_register":
                continue
            self.sleep_until(t)
            self._resolve_due(deadlines)
            if k == "monitor_opportunity":
                self._send_monitor(rec, deadlines)
            elif k == "history_batch":
                self._send_history(rec)
            elif k == "recall_question":
                self._send_recall(rec, deadlines)
            elif k in PASSTHROUGH:
                self._send_passthrough(rec)

        # DRAIN, in the order the semantics require:
        #   1. every offered transfer must actually leave the uplink;
        #   2. then wait out the longest outstanding deadline;
        #   3. then resolve what is left.
        # The horizon is taken over the LAST SCHEDULED RECORD as well as the pending
        # deadlines, so an empty deadline list cannot collapse the drain to "now" (F7).
        self.uplink.drain_and_stop(timeout=max(30.0, self.drain_s))
        last_t = max([float(r.get("t") or 0.0) for r in self.records] or [0.0])
        horizon = max([d["t_deadline"] for d in deadlines] + [last_t, self.now()])
        self.sleep_until(horizon + 0.05)
        self._resolve_due(deadlines, force=True)
        try:
            self.wire.send(dict(kind="device_done", device_id=self.device_id))
        except OSError:
            pass
        self._stop.set()
        time.sleep(0.05)
        st = self.wire.stats()
        self.wire.close()
        return self._summary(st)

    # ---- senders
    #
    # EVERY outbound event is built through `events_check.make()`, which is the REPO's own
    # `fleet/events.make()` when the repo is reachable. Forwarding a raw trace record instead
    # ships the generator's bookkeeping onto the wire: a real `session_start` record carries
    # duration_s, join_offset_s, joined_part_way and source_session, none of which the schema
    # defines. The server's rebuild happened to discard them, so it worked by luck -- but
    # `live2/bridge.py` calls `SC.parse(event)` on every event and is stricter than that, and
    # the extra fields inflate every line on the wire.
    def _send_passthrough(self, rec: Dict[str, Any]) -> None:
        k = rec["kind"]
        if k == "device_register":
            ev = EC.make("device_register", device_id=self.device_id, type=rec["type"],
                         uplink_mbps=rec.get("uplink_mbps"), rtt_ms=rec.get("rtt_ms"),
                         start_t=rec.get("start_t"))
        elif k in ("session_start", "session_end"):
            ev = EC.make(k, device_id=self.device_id, session_id=rec["session_id"],
                         t=float(rec["t"]))
        elif k == "history_preload":
            # D101: NO UPLINK TIME. The frames were on cloud-side disk before the clock
            # started, so a preload neither occupies the uplink nor queues behind anything.
            ev = EC.make("history_preload", device_id=self.device_id,
                         session_id=rec["session_id"],
                         frame_refs=rec.get("frame_refs") or [],
                         est_tokens=int(rec.get("cum_tokens")
                                        or rec.get("est_tokens") or 0),
                         t=float(rec["t"]))
        else:
            raise ValueError("passthrough does not handle %r" % k)
        self.wire.send(ev)

    def _send_monitor(self, rec: Dict[str, Any], deadlines: List[Dict[str, Any]]) -> None:
        opp = str(rec["opportunity_id"])
        nb = int(rec.get("frame_bytes") or 0)
        blob = self.frames.get(str(rec.get("frame_ref") or opp), nb)
        prof = self.profile.by_opp.get(opp) or {}
        ev = dict(device_id=self.device_id, opportunity_id=opp,
                  instant_id=rec.get("instant_id") or opp,
                  t_capture=float(rec["t"]), t_arrive=float(rec["t"]),
                  deadline_s=float(rec["deadline_s"]),
                  frame_ref=rec.get("frame_ref"), frame_bytes=nb)
        if prof.get("device_score") is not None:
            ev["device_score"] = float(prof["device_score"])
        for f in ("episode_id", "episode_index", "frame_refs", "episode_frames"):
            if rec.get(f) is not None:
                ev[f] = rec[f]
        # OFFERED to the uplink, not written inline: the replay loop must not block on the
        # link (see UplinkSender).
        t_send = self.uplink.offer("monitor_frame", opp, EC.make("monitor_frame", **ev),
                                   blob=blob)
        deadlines.append(dict(opportunity_id=opp, kind="monitor",
                              t_capture=float(rec["t"]), t_send=t_send,
                              t_deadline=float(rec["t"]) + float(rec["deadline_s"]),
                              bytes=len(blob)))

    def _send_history(self, rec: Dict[str, Any]) -> None:
        nb = int(rec.get("frame_bytes") or 0)
        refs = rec.get("frame_refs") or []
        blob = b""
        if nb:
            blob = self.frames.get(str(refs[0]) if refs else str(rec.get("batch_id")), nb)
        ev = EC.make("history_append", device_id=self.device_id,
                     session_id=rec["session_id"], batch_id=rec["batch_id"],
                     t_arrive=float(rec["t"]), frame_refs=refs,
                     est_tokens=int(rec.get("cum_tokens") or rec.get("est_tokens") or 0))
        # D75: history batches contend for the SAME single uplink as monitoring frames.
        self.uplink.offer("history_append", str(rec["batch_id"]), ev, blob=blob or None)

    def _send_recall(self, rec: Dict[str, Any], deadlines: List[Dict[str, Any]]) -> None:
        opp = str(rec["opportunity_id"])
        ev = dict(device_id=self.device_id, opportunity_id=opp,
                  session_id=rec.get("session_id"),
                  question_id=rec.get("question_id") or opp,
                  t_ask=float(rec["t"]), t_arrive=float(rec["t"]),
                  deadline_s=float(rec["deadline_s"]),
                  question=rec.get("question"), options=rec.get("options") or [])
        if rec.get("category") is not None:
            ev["category"] = rec["category"]
        t_send = self.uplink.offer("recall_question", opp, EC.make("recall_question", **ev))
        deadlines.append(dict(opportunity_id=opp, kind="recall",
                              t_capture=float(rec["t"]), t_send=t_send,
                              t_deadline=float(rec["t"]) + float(rec["deadline_s"]),
                              bytes=0))

    # ---- the deadline decision
    def _resolve_due(self, deadlines: List[Dict[str, Any]], force: bool = False) -> None:
        """For every opportunity whose deadline has passed, record cloud-or-device."""
        now = self.now()
        keep = []
        for d in deadlines:
            if not force and now < d["t_deadline"]:
                keep.append(d)
                continue
            opp = d["opportunity_id"]
            ans = self.answers.get(opp)
            used_cloud = ans is not None and float(ans.get("t_done", 1e18)) <= d["t_deadline"]
            row = dict(opportunity_id=opp, kind=d["kind"], device_id=self.device_id,
                       t_capture=d["t_capture"], t_send=d["t_send"],
                       t_deadline=d["t_deadline"], bytes=d["bytes"],
                       cloud_arrived=ans is not None,
                       t_cloud_done=(float(ans["t_done"]) if ans else None),
                       t_cloud_recv=(ans.get("_t_recv") if ans else None),
                       source="cloud" if used_cloud else "device",
                       deadline_met=bool(used_cloud))
            if not used_cloud:
                # D165 B: the device's own profiled answer REPLACES the cloud answer.
                try:
                    p = self.profile.answer(opp)
                    row["device_score"] = p.get("device_score")
                    row["device_letter"] = p.get("device_letter") or p.get("letter")
                except KeyError as e:
                    row["fallback_error"] = str(e)
            self.log.append(row)
        deadlines[:] = keep

    def _summary(self, wire_stats: Dict[str, Any]) -> Dict[str, Any]:
        n = len(self.log)
        cloud = sum(1 for r in self.log if r["source"] == "cloud")
        errs = [r for r in self.log if r.get("fallback_error")]
        return dict(device_id=self.device_id, type=self.type,
                    n_records=len(self.records), n_resolved=n,
                    n_cloud=cloud, n_device=n - cloud,
                    cloud_frac=(round(cloud / n, 4) if n else None),
                    n_pull_requests=self.n_pull,
                    n_fallback_errors=len(errs),
                    wire=wire_stats, frames=self.frames.stats(),
                    # D75 / links.py: the queueing delay the single uplink imposed, recorded
                    # SEPARATELY and never folded into the transfer time.
                    uplink=(self.uplink.stats() if self.uplink else None),
                    send_error=(self.uplink.err if self.uplink else None),
                    recv_error=self.err)

    def write_log(self, out_dir: Path) -> None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / ("device_log_%s.jsonl" % self.device_id), "w") as fh:
            for r in self.log:
                fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
        if self.uplink is not None:
            with open(out_dir / ("uplink_%s.jsonl" % self.device_id), "w") as fh:
                for r in self.uplink.log:
                    fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


def selftest(slice_dir: Path) -> int:
    """Validate a slice without a server: schema, ids, answer coverage. No network."""
    import events_check as EC
    d = Path(slice_dir)
    meta = json.loads((d / "slice_meta.json").read_text())
    recs = [json.loads(l) for l in open(d / "trace.jsonl") if l.strip()]
    prof = Profile(d / "device_answers.jsonl")
    checks = []

    checks.append(("slice_meta has device_id", bool(meta.get("device_id"))))
    checks.append(("has device_register",
                   any(r["kind"] == "device_register" for r in recs)))
    checks.append(("record count matches meta", len(recs) == meta.get("n_records")))

    opps = [str(r["opportunity_id"]) for r in recs if r.get("opportunity_id")]
    checks.append(("opportunity ids unique", len(opps) == len(set(opps))))
    covered = sum(1 for o in opps if o in prof.by_opp)
    checks.append(("every opportunity has a profiled answer", covered == len(opps)))

    single = all(str(r["device_id"]) == str(meta["device_id"])
                 for r in recs if r.get("device_id"))
    checks.append(("every record belongs to this device", single))

    monitors = [r for r in recs if r["kind"] == "monitor_opportunity"]
    checks.append(("monitors carry frame_bytes",
                   all(int(r.get("frame_bytes") or 0) > 0 for r in monitors)))
    ok_ev, why = EC.check_slice_builds_events(recs, prof.by_opp, str(meta["device_id"]))
    checks.append(("every record builds a valid wire event" + ("" if ok_ev else ": " + why),
                   ok_ev))

    print("selftest %s (%s, %d records)" % (meta["device_id"], meta.get("type"), len(recs)))
    bad = 0
    for name, ok in checks:
        print("  %-55s %s" % (name, "PASS" if ok else "FAIL"))
        if not ok:
            bad += 1
    print("  %d/%d checks pass" % (len(checks) - bad, len(checks)))
    return 1 if bad else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Replay one device slice over a real socket")
    ap.add_argument("--slice", required=True, help="a per-device slice directory")
    ap.add_argument("--server", default=None, help="host:port of the fleet server")
    ap.add_argument("--frames-root", default=None, help="local JPEG store")
    ap.add_argument("--synthetic-frames", action="store_true",
                    help="generate bytes of the recorded length instead of reading JPEGs")
    ap.add_argument("--speed", type=float, default=1.0, help="schedule speed-up for tests")
    ap.add_argument("--out", default=None, help="write the per-opportunity log here")
    ap.add_argument("--selftest", action="store_true", help="validate the slice, no network")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest(Path(a.slice))
    if not a.server:
        print("--server is required unless --selftest", file=sys.stderr)
        return 2
    host, _, port = a.server.rpartition(":")
    ag = DeviceAgent(Path(a.slice), host, int(port),
                     Path(a.frames_root) if a.frames_root else None,
                     a.synthetic_frames, a.speed)
    summ = ag.run()
    if a.out:
        ag.write_log(Path(a.out))
    print(json.dumps(summ, indent=2, sort_keys=True))
    return 0 if not summ.get("n_fallback_errors") and not summ.get("recv_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
