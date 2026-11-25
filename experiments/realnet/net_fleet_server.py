#!/usr/bin/env python3
"""The network front end: real sockets in, the live2 Coordinator Protocol out.

StudyREAL-NET, component 3. Runs on the H100. CPU only -- the GPU is touched only by whatever
coordinator this drives.

WHAT THIS IS. The real-network counterpart of `live2/fleet/emulator.py::FleetEmulator`. It owns
the ONE run clock and calls the coordinator through exactly the Protocol the emulator uses
(`live2/fleet/emulator.py:76-78`):

    on_event(event, t) -> Sequence[reply]
    tick(t)            -> Sequence[reply]

so `live2/bridge.py`, `live2/coordinator.py` and every `arms_*.py` stay BYTE-IDENTICAL. The
bridge already holds no clock of its own ("every call carries the emulator's `t`... it
therefore cannot drift from the fleet") and already enforces D99 (1) one-decision-per-period
on the caller's clock, so honouring the Protocol inherits both.

THE BUG THIS IS WRITTEN TO AVOID. `FleetEmulator.run()` carries a long comment about a defect
they hit and fixed: ticks were caught up in a BURST BEFORE the sleep, so the coordinator was
not driven at all while the loop waited for the next action. A request that finished inside a
wait was not collected until the next action popped, and its `cloud_answer` arrived carrying a
`t_done` already in the past. That notice delay WAS the pilot's lateness -- p50 18.4 ms, p99
289.0 ms on `answer_delivered`, while every other event kind sat at p99 0.28 ms.

The fix, which this server implements from the start rather than discovering again:
  1. TICK WHILE WAITING. The select loop never blocks longer than the next tick is due.
  2. A reply handled during a wait may schedule something EARLIER than the item in hand, so
     the pending item goes back and the loop re-decides what is next.
  3. `Lateness` is tracked and `MAX_P99_LATENESS_MS` gates the cell.

NO CLOCK SYNC NEEDED. The server stamps `t_arrive` on receipt, on ITS clock, which is the run
clock. A device's own clock reaches only its local send log. A cross-host offset therefore
cannot enter the coordinator's view -- which is why chrony/PTP is not a prerequisite.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events_check as EC  # noqa: E402
import wire as W  # noqa: E402

DEFAULT_TICK_S = 0.010
MAX_P99_LATENESS_MS = 50.0          # same gate as fleet/emulator.py
DEFAULT_PORT = 47900


class Lateness:
    """How late the loop was in delivering each scheduled action. Same role as the emulator's."""

    def __init__(self) -> None:
        self.v: List[float] = []
        self.by_what: Dict[str, List[float]] = {}

    def add(self, dt: float, what: str = "?") -> None:
        self.v.append(dt)
        self.by_what.setdefault(what, []).append(dt)

    @staticmethod
    def _q(v: List[float], p: float) -> Optional[float]:
        if not v:
            return None
        s = sorted(v)
        k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
        return s[k]

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = dict(
            n=len(self.v),
            p50_ms=(round(self._q(self.v, 0.50) * 1e3, 3) if self.v else None),
            p99_ms=(round(self._q(self.v, 0.99) * 1e3, 3) if self.v else None),
            max_ms=(round(max(self.v) * 1e3, 3) if self.v else None),
        )
        out["by_kind"] = {
            k: dict(n=len(v), p99_ms=round(self._q(v, 0.99) * 1e3, 3))
            for k, v in sorted(self.by_what.items())
        }
        p99 = out["p99_ms"]
        out["gate_max_p99_ms"] = MAX_P99_LATENESS_MS
        out["gate_pass"] = (p99 is None) or (p99 <= MAX_P99_LATENESS_MS)
        return out


class DeviceConn:
    """One connected device."""

    def __init__(self, sock: socket.socket, addr) -> None:
        self.wire = W.Wire(sock)
        self.addr = addr
        self.device_id: Optional[str] = None
        self.type: Optional[str] = None
        self.registered = False
        self.done = False
        self.n_events = 0
        self.n_replies = 0

    def fileno(self) -> int:
        return self.wire.sock.fileno()


class NetFleetServer:
    """Terminates device connections and drives a coordinator through the live2 Protocol."""

    def __init__(self, coordinator, expect_devices: int, run_s: float,
                 port: int = DEFAULT_PORT, tick_s: float = DEFAULT_TICK_S,
                 drain_s: float = 5.0, barrier_timeout_s: float = 120.0) -> None:
        self.coord = coordinator
        self.expect = int(expect_devices)
        self.run_s = float(run_s)
        self.tick_s = float(tick_s)
        self.drain_s = float(drain_s)
        self.barrier_timeout_s = float(barrier_timeout_s)
        self.port = int(port)
        self.lateness = Lateness()
        self.conns: List[DeviceConn] = []
        self.by_device: Dict[str, DeviceConn] = {}
        self.roster: List[Dict[str, Any]] = []
        self.t0 = 0.0
        self.t0_unix = 0.0
        self.next_tick = 0.0
        self.n_events = 0
        self.n_ticks = 0
        self.n_replies = 0
        self.n_unroutable = 0
        self.short_run = False
        # F6: arrivals are STREAMED, not buffered. At 16 devices x 1200 s the buffered form
        # was ~30k dicts (20-40 MB) and grew with run length; a 10x longer run would be
        # 300-400 MB. `events_seen` keeps only counts now.
        self.events_by_kind: Dict[str, int] = {}
        self.n_arrivals = 0
        self.errors: List[str] = []
        self._lsock: Optional[socket.socket] = None
        self._arrivals_fh = None
        self._out_dir: Optional[Path] = None

    # ---- clock
    def now(self) -> float:
        return time.monotonic() - self.t0

    # ---- phase 1: registration barrier
    def accept_until_quorum(self) -> None:
        """Hold t=0 until every expected device has registered (or we time out)."""
        self._lsock = W.listener(self.port)
        deadline = time.monotonic() + self.barrier_timeout_s
        while len(self.by_device) < self.expect:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "barrier: %d/%d devices registered in %.0f s (have %s)"
                    % (len(self.by_device), self.expect, self.barrier_timeout_s,
                       sorted(self.by_device)))
            rl, _, _ = select.select([self._lsock] + [c for c in self.conns
                                                      if not c.registered], [], [], 0.25)
            for r in rl:
                if r is self._lsock:
                    s, addr = self._lsock.accept()
                    s.settimeout(None)
                    self.conns.append(DeviceConn(s, addr))
                    continue
                try:
                    msg, _blob = r.wire.recv()
                except (EOFError, OSError, W.WireError) as e:
                    self.errors.append("pre-register close from %s: %s" % (r.addr, e))
                    self._drop(r)
                    continue
                if msg.get("kind") != "device_register":
                    self.errors.append("expected device_register, got %r" % msg.get("kind"))
                    continue
                d = str(msg["device_id"])
                r.device_id, r.type, r.registered = d, msg.get("type"), True
                self.by_device[d] = r
                self.roster.append(dict(device_id=d, type=msg.get("type"),
                                        addr=str(r.addr),
                                        n_records=msg.get("n_records"),
                                        uplink_mbps=msg.get("uplink_mbps"),
                                        rtt_ms=msg.get("rtt_ms"),
                                        start_t=msg.get("start_t")))

    def _write_arrival(self, row: Dict[str, Any]) -> None:
        self.n_arrivals += 1
        if self._arrivals_fh is not None:
            self._arrivals_fh.write(json.dumps(row, sort_keys=True,
                                               separators=(",", ":")) + "\n")

    def _drop(self, c: DeviceConn) -> None:
        try:
            c.wire.close()
        except Exception:
            pass
        if c in self.conns:
            self.conns.remove(c)
        if c.device_id and self.by_device.get(c.device_id) is c:
            del self.by_device[c.device_id]

    # ---- phase 2: release the barrier and run
    def check_run_s(self, trace_run_s: Optional[float],
                    allow_short: bool = False) -> None:
        """F5: a --run-s below the trace's own run_s silently truncates the cell.

        The frozen trace declares `run_s = 1200.0`. Passing a smaller value drops every
        record after it and produces a partial cell that looks complete. That is how the
        60 s development runs worked, which is exactly why it needs a guard rather than a
        convention.
        """
        if trace_run_s is None:
            return
        if abs(float(trace_run_s) - self.run_s) < 1e-6:
            return
        msg = ("--run-s %.3f disagrees with the trace's run_s %.3f; a short run silently "
               "truncates the cell" % (self.run_s, float(trace_run_s)))
        if not allow_short:
            raise ValueError(msg + " (pass allow_short=True / --allow-short-run to accept)")
        self.errors.append("SHORT RUN ACCEPTED: " + msg)
        self.short_run = True

    def run(self, out_dir: Optional[Path] = None) -> Dict[str, Any]:
        if out_dir is not None:
            self._out_dir = Path(out_dir)
            self._out_dir.mkdir(parents=True, exist_ok=True)
            self._arrivals_fh = open(self._out_dir / "arrivals.jsonl", "w")
        self.accept_until_quorum()
        # Feed every device_register to the coordinator at t=0, then release the fleet.
        self.t0 = time.monotonic()
        self.t0_unix = time.time()
        self.next_tick = 0.0
        for row in self.roster:
            ev = EC.make("device_register", device_id=row["device_id"], type=row["type"],
                         uplink_mbps=row.get("uplink_mbps"), rtt_ms=row.get("rtt_ms"),
                         start_t=row.get("start_t"))
            self._to_coord(ev, 0.0)
        for d, c in sorted(self.by_device.items()):
            try:
                c.wire.send(dict(kind="run_start", device_id=d, t0_unix=self.t0_unix))
            except OSError as e:
                self.errors.append("run_start to %s failed: %s" % (d, e))

        horizon = self.run_s + self.drain_s
        while True:
            t = self.now()
            if t > horizon:
                break
            if self.by_device and all(c.done for c in self.by_device.values()):
                break
            # (1) TICK WHILE WAITING: never block past the next due tick.
            #
            # The wait is bounded by the time remaining until the next tick, NOT by a fixed
            # cap, so select() can never sleep past a due tick. (An earlier version used
            # min(timeout, 0.05); that is wrong in principle even though measurement showed it
            # was not the source of the jitter below.)
            #
            # MEASURED ON A MAC, 2026-11-25, 3 devices x 60 s of trace at 20x. Two runs:
            # tick lateness p50 1.6-1.9 ms, p99 5.1-11.6 ms, max 36-92 ms. The max is not this
            # loop: profiling put a whole run's socket reads at 0.415 s over 2,704 messages
            # (0.15 ms each) and all coordinator work at 0.052 s, i.e. under half a second of
            # work across the run.
            #
            # A CONTROL -- a bare 10 ms time.sleep() loop with no sockets and no coordinator on
            # the same host -- measured p99 17.8 ms / max 52.5 ms on a loaded run and p99
            # 5.8 ms / max 6.3 ms on a quiet one. The control's own spread across runs is as
            # large as the server's, which is the point: this host's scheduler tail is not
            # stable enough to attribute a tens-of-ms tick max to the harness OR to clear the
            # harness of it. The profiling above is the load-bearing evidence; the control only
            # shows the host can produce the same tail with no I/O at all.
            #
            # This matters for where the gate is trusted: on the H100 (128 cores, load ~4.5)
            # the scheduler tail should be far smaller, so MAX_P99_LATENESS_MS must be judged
            # there, not here. A Mac run is a functional test, never a timing measurement.
            due = self.t0 + self.next_tick
            timeout = max(0.0, due - time.monotonic())
            socks = [c for c in self.conns if not c.done]
            rl: List[Any] = []
            if socks:
                rl, _, _ = select.select(socks, [], [], timeout)
            elif timeout > 0:
                time.sleep(timeout)
            # Issue every tick now due, BEFORE handling reads, so a completion that landed
            # during the wait is collected within one tick_s.
            while self.next_tick <= self.now():
                issued = self.next_tick
                self.lateness.add(max(0.0, self.now() - issued), "tick")
                self.n_ticks += 1
                for reply in (self.coord.tick(issued) or ()):
                    self._route(reply, issued)
                self.next_tick = round(self.next_tick + self.tick_s, 9)
            for c in rl:
                self._read_one(c)
        return self._finish(out_dir)

    def _read_one(self, c: DeviceConn) -> None:
        try:
            msg, blob = c.wire.recv()
        except (EOFError, OSError, W.WireError) as e:
            if not c.done:
                self.errors.append("read from %s: %s" % (c.device_id, e))
            c.done = True
            return
        kind = msg.get("kind")
        if kind == "device_done":
            c.done = True
            return
        # (2) t_arrive IS STAMPED HERE, on the run clock. This is what removes the need for
        # cross-host clock sync: the device's own clock never reaches the coordinator.
        t = self.now()
        self._write_arrival(dict(device_id=c.device_id, kind=kind,
                                 opportunity_id=msg.get("opportunity_id"),
                                 t_arrive=round(t, 6),
                                 t_capture=msg.get("t_capture"),
                                 bytes=(len(blob) if blob else 0)))
        ev = self._to_wire_event(msg, t, blob)
        if ev is None:
            return
        c.n_events += 1
        self._to_coord(ev, t)

    def _to_wire_event(self, msg: Dict[str, Any], t: float,
                       blob: Optional[bytes]) -> Optional[Dict[str, Any]]:
        """Build the schema-valid event, stamping arrival. Returns None on a bad message."""
        k = msg.get("kind")
        try:
            if k == "monitor_frame":
                kw = dict(device_id=msg["device_id"], opportunity_id=msg["opportunity_id"],
                          instant_id=msg.get("instant_id") or msg["opportunity_id"],
                          t_capture=float(msg["t_capture"]), t_arrive=t,
                          deadline_s=float(msg["deadline_s"]),
                          frame_ref=msg.get("frame_ref"),
                          frame_bytes=int(msg.get("frame_bytes") or (len(blob) if blob else 0)))
                for f in ("episode_id", "episode_index", "frame_refs", "episode_frames",
                          "device_score"):
                    if msg.get(f) is not None:
                        kw[f] = msg[f]
                return EC.make("monitor_frame", **kw)
            if k == "recall_question":
                kw = dict(device_id=msg["device_id"], opportunity_id=msg["opportunity_id"],
                          session_id=msg.get("session_id"),
                          question_id=msg.get("question_id") or msg["opportunity_id"],
                          t_ask=float(msg["t_ask"]), t_arrive=t,
                          deadline_s=float(msg["deadline_s"]),
                          question=msg.get("question"), options=msg.get("options") or [])
                if msg.get("category") is not None:
                    kw["category"] = msg["category"]
                return EC.make("recall_question", **kw)
            if k == "history_append":
                return EC.make("history_append", device_id=msg["device_id"],
                               session_id=msg["session_id"], batch_id=msg["batch_id"],
                               t_arrive=t, frame_refs=msg.get("frame_refs") or [],
                               est_tokens=int(msg.get("est_tokens") or 0))
            if k == "history_preload":
                return EC.make("history_preload", device_id=msg["device_id"],
                               session_id=msg["session_id"],
                               frame_refs=msg.get("frame_refs") or [],
                               est_tokens=int(msg.get("est_tokens")
                                              or msg.get("cum_tokens") or 0),
                               t=float(msg.get("t") or t))
            if k in ("session_start", "session_end"):
                return EC.make(k, device_id=msg["device_id"],
                               session_id=msg["session_id"], t=float(msg.get("t") or t))
        except Exception as e:
            self.errors.append("malformed %r from %r: %s: %s"
                               % (k, msg.get("device_id"), type(e).__name__, e))
            return None
        self.errors.append("unroutable inbound kind %r" % k)
        return None

    def _to_coord(self, ev: Dict[str, Any], t: float) -> None:
        self.n_events += 1
        self.events_by_kind[ev["kind"]] = self.events_by_kind.get(ev["kind"], 0) + 1
        for reply in (self.coord.on_event(ev, t) or ()):
            self._route(reply, t)

    def _route(self, reply: Dict[str, Any], t: float) -> None:
        """Send a coordinator reply back to the owning device socket."""
        d = str(reply.get("device_id"))
        c = self.by_device.get(d)
        if c is None or c.done:
            self.n_unroutable += 1
            return
        try:
            c.wire.send(reply)
            c.n_replies += 1
            self.n_replies += 1
        except OSError as e:
            self.errors.append("reply to %s failed: %s" % (d, e))
            c.done = True

    def _finish(self, out_dir: Optional[Path]) -> Dict[str, Any]:
        if self._arrivals_fh is not None:
            try:
                self._arrivals_fh.flush()
                self._arrivals_fh.close()
            except Exception:
                pass
            self._arrivals_fh = None
        for c in list(self.conns):
            try:
                c.wire.close()
            except Exception:
                pass
        if self._lsock is not None:
            try:
                self._lsock.close()
            except Exception:
                pass
        close = getattr(self.coord, "close", None)
        if callable(close):
            try:
                close()
            except Exception as e:
                self.errors.append("coordinator close: %s" % e)

        lat = self.lateness.stats()
        kind = getattr(self.coord, "kind", None)
        summary = dict(
            server="net_fleet_server",
            # A stub run is NOT a measurement. The scorer refuses one, and this field is what
            # it reads, so it is set from the coordinator itself rather than asserted here.
            server_kind=kind or "unknown",
            is_measurement=(kind not in ("stub", None)),
            n_devices=len(self.roster),
            roster=self.roster,
            run_s=self.run_s, tick_s=self.tick_s,
            t0_unix=self.t0_unix,
            n_events=self.n_events, n_ticks=self.n_ticks, n_replies=self.n_replies,
            n_unroutable_replies=self.n_unroutable,
            events_by_kind=dict(sorted(self.events_by_kind.items())),
            n_arrivals=self.n_arrivals,
            short_run=self.short_run,
            lateness=lat,
            n_errors=len(self.errors), errors=self.errors[:50],
            per_device={c.device_id: dict(n_events=c.n_events, n_replies=c.n_replies,
                                          wire=c.wire.stats())
                        for c in self.conns if c.device_id},
        )
        bridge_describe = getattr(self.coord, "describe", None)
        if callable(bridge_describe):
            try:
                summary["coordinator"] = bridge_describe()
            except Exception:
                pass
        if out_dir:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "server_meta.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
        return summary


def load_live2_emulator():
    """Import live2/fleet/emulator.py for its StubCoordinator, reimplementing nothing.

    The module must be REGISTERED IN sys.modules BEFORE exec_module. `emulator.py` decorates
    `Lateness` with @dataclass, and dataclasses resolves `cls.__module__` through
    `sys.modules[...]`; executing an unregistered module makes that lookup return None and
    raises `AttributeError: 'NoneType' object has no attribute '__dict__'`. Registering first
    is the documented way to load a module by path.
    """
    here = Path(__file__).resolve().parent
    live2 = Path(os.environ.get(
        "LIVE2_DIR", here.parent / "orchestration" / "live2"))
    for p in (str(live2), str(live2 / "fleet")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import importlib
    import importlib.util
    name = "live2_fleet_emulator"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, live2 / "fleet" / "emulator.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules[name]
        raise
    return mod


def build_stub(capacity_per_s: float = 8.0, service_s: float = 0.25):
    """live2's own StubCoordinator, imported not reimplemented."""
    mod = load_live2_emulator()
    return mod.StubCoordinator(capacity_per_s=capacity_per_s, service_s=service_s)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="StudyREAL-NET network front end")
    ap.add_argument("--expect-devices", type=int, required=True)
    ap.add_argument("--run-s", type=float, required=True)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--tick-s", type=float, default=DEFAULT_TICK_S)
    ap.add_argument("--drain-s", type=float, default=5.0)
    ap.add_argument("--barrier-timeout-s", type=float, default=120.0)
    ap.add_argument("--mode", default="A", choices=("A", "B"),
                    help="A = frames pushed with the bytes. B (pull) is NOT IMPLEMENTED: "
                         "no monitor_offer is ever sent, so the coordinator could never "
                         "issue a pull_request and the run would silently carry no frames")
    ap.add_argument("--trace-run-s", type=float, default=None,
                    help="the trace's own run_s; --run-s must match it (F5)")
    ap.add_argument("--allow-short-run", action="store_true",
                    help="accept a --run-s shorter than the trace, producing a PARTIAL cell")
    ap.add_argument("--coordinator", default="stub", choices=("stub",),
                    help="stub only for now; the real bridge lands at integration step 4")
    ap.add_argument("--stub-capacity", type=float, default=8.0)
    ap.add_argument("--stub-service-s", type=float, default=0.25)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if a.mode == "B":
        print("--mode B (pull) is not implemented: this server never sends monitor_offer, so "
              "no pull_request can be answered and the cell would carry no frames. Refusing "
              "rather than running an empty cell.", file=sys.stderr)
        return 2
    coord = build_stub(a.stub_capacity, a.stub_service_s)
    srv = NetFleetServer(coord, a.expect_devices, a.run_s, a.port, a.tick_s,
                         a.drain_s, a.barrier_timeout_s)
    try:
        srv.check_run_s(a.trace_run_s, a.allow_short_run)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    summ = srv.run(Path(a.out) if a.out else None)
    print(json.dumps(summ, indent=2, sort_keys=True, default=str))
    ok = summ["lateness"]["gate_pass"] and summ["n_errors"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
