#!/usr/bin/env python3
"""The fleet emulator and the coordinator in SEPARATE PROCESSES. CPU only.

StudyLIVE2-harness, fix (a). One Python process cannot own both a wall clock that must be
accurate to tens of milliseconds and an HTTP client that reads multi-megabyte streamed responses:
every response byte is handled by Python bytecode holding the GIL, so the clock thread waits.
StudyLIVE2-pilot measured the consequence (emulator p99 lateness 511.6 ms at 8 devices while the
coordinator was idle at 4.7 % CPU).

THE SPLIT. The emulator keeps the clock, the trace, the uplink queues, the outcomes and the
LATENESS - which is therefore measured in a process that does no HTTP at all. The coordinator,
the arm, the body building and the HTTP move into a child process. They are joined by a UNIX
socket carrying length-prefixed JSON.

WHY THE WIRE CAN BE ASYNCHRONOUS. Every reply the coordinator sends the fleet carries its own
run-clock timestamp: a `pull_request` carries `t_sent` and a `cloud_answer` carries `t_done`
(`schema.py`), and the emulator schedules the delivery from THAT timestamp, not from the moment
the reply reached it (`emulator.py::_handle_reply`). So the parent never has to block on a reply
to place it correctly in time; it writes the event and drains whatever replies have arrived. A
reply that arrives after its own delivery instant is scheduled in the past and the emulator
charges the lateness, which is the honest accounting and is exactly what the acceptance check
measures.

WHAT DOES NOT CHANGE. The arms, the decisions, the schema, the digests and the scoring. The
child builds the coordinator the way `run_live2_cell.py` does, the parent runs the same
`FleetEmulator`, and `test_live2_harness.py` requires the fairness digest and the decision log
of a split run to equal an in-process run's on the same trace and seed.

NOTHING HERE MEASURES ANYTHING: `server_kind` travels with the run as before.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

_HDR = struct.Struct("!I")
_EOF = b""


# ---------------------------------------------------------------- framing
def send_msg(sock: socket.socket, obj: Any) -> None:
    data = json.dumps(obj).encode()
    sock.sendall(_HDR.pack(len(data)) + data)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return _EOF
        buf += chunk
    return bytes(buf)


def recv_msg(sock: socket.socket) -> Any:
    head = _recv_exact(sock, _HDR.size)
    if head is _EOF or not head:
        return None
    (n,) = _HDR.unpack(head)
    body = _recv_exact(sock, n)
    if body is _EOF or not body:
        return None
    return json.loads(body)


# ---------------------------------------------------------------- the parent's proxy
class RemoteCoordinator:
    """The coordinator process seen through the emulator's own `Coordinator` Protocol.

    `on_event` and `tick` write and return whatever has come back so far, so the clock thread
    never waits on the child. `close` drains the child's remaining replies before returning, so
    no answer is silently dropped at the end of a run.
    """

    def __init__(self, sock: socket.socket, kind: str = "fake",
                 drain_close_s: float = 30.0) -> None:
        self.sock = sock
        self.kind = kind
        self.drain_close_s = float(drain_close_s)
        self._in: "queue.Queue[Any]" = queue.Queue()
        # THE PARENT MUST NEVER BLOCK ON THE WIRE. A child that is busy taking a decision is not
        # reading its socket, so a direct `sendall` from the clock thread blocks once the socket
        # buffer fills, and the emulator is late for a reason that has nothing to do with the
        # fleet. Writes therefore go to a queue drained by a writer thread; if the child falls
        # behind, the consequence shows up where it belongs, as answers delivered late.
        self._out: "queue.Queue[Any]" = queue.Queue()
        self._alive = True
        self._stats: Dict[str, Any] = {}
        self._sent = 0
        self._recv = 0
        self._write_errors = 0
        self._max_backlog = 0
        self._reader = threading.Thread(target=self._read_loop, name="live2-proxy-rx",
                                        daemon=True)
        self._reader.start()
        self._writer = threading.Thread(target=self._write_loop, name="live2-proxy-tx",
                                        daemon=True)
        self._writer.start()

    def _read_loop(self) -> None:
        try:
            while True:
                msg = recv_msg(self.sock)
                if msg is None:
                    break
                self._in.put(msg)
        except OSError:
            pass
        finally:
            self._alive = False
            self._in.put({"op": "eof"})

    def _write_loop(self) -> None:
        while True:
            obj = self._out.get()
            if obj is None:
                return
            try:
                send_msg(self.sock, obj)
            except OSError:
                self._write_errors += 1
                return

    def _put(self, obj: Any) -> None:
        self._out.put(obj)
        n = self._out.qsize()
        if n > self._max_backlog:
            self._max_backlog = n

    def _drain(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        while True:
            try:
                msg = self._in.get_nowait()
            except queue.Empty:
                break
            op = msg.get("op")
            if op == "replies":
                out += list(msg.get("replies") or ())
                self._recv += len(msg.get("replies") or ())
            elif op == "result":
                self._stats = msg.get("result") or {}
            elif op in ("eof", "closed"):
                pass
            elif op == "error":
                raise RuntimeError(f"coordinator process failed: {msg.get('error')}")
        return out

    def on_event(self, event: Dict[str, Any], t: float) -> Sequence[Dict[str, Any]]:
        self._put({"op": "event", "event": event, "t": float(t)})
        self._sent += 1
        return self._drain()

    def tick(self, t: float) -> Sequence[Dict[str, Any]]:
        self._put({"op": "tick", "t": float(t)})
        return self._drain()

    def close(self) -> None:
        self._put({"op": "finish"})
        deadline = time.monotonic() + self.drain_close_s
        pending: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            if self._stats and self._in.empty():
                break
            try:
                msg = self._in.get(timeout=0.05)
            except queue.Empty:
                continue
            op = msg.get("op")
            if op == "replies":
                pending += list(msg.get("replies") or ())
            elif op == "result":
                self._stats = msg.get("result") or {}
            elif op in ("eof", "closed"):
                break
        self.late_replies = pending
        try:
            self.sock.close()
        except OSError:
            pass

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats, wire_events_sent=self._sent, wire_replies_received=self._recv,
                    wire_write_errors=self._write_errors,
                    wire_max_send_backlog=self._max_backlog)


# ---------------------------------------------------------------- the child
def coordinator_process(sock_path: str, cfg: Dict[str, Any]) -> None:
    """Build the coordinator exactly as `run_live2_cell.py` does, then serve the socket."""
    for p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"),
              str(REPO / "experiments/orchestration/live"),
              str(REPO / "experiments/orchestration/baselines"),
              str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(sock_path)
    try:
        _serve(sock, cfg)
    except Exception as e:                                            # noqa: BLE001
        import traceback
        try:
            send_msg(sock, {"op": "error",
                            "error": f"{type(e).__name__}: {e}",
                            "traceback": traceback.format_exc()[-4000:]})
        except OSError:
            pass
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _serve(sock: socket.socket, cfg: Dict[str, Any]) -> None:
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import framecache as FC
    import run_live2_cell as RC
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs

    rdir = Path(cfg["run_dir"])
    rdir.mkdir(parents=True, exist_ok=True)
    arm = A.make_arm(cfg["arm"], **(cfg.get("arm_kwargs") or {}))
    htok = int(cfg.get("host_tier_tokens") or RC.host_tokens(float(cfg["host_tier_gib"])))
    conf = dict(gpu_kv_tokens=int(cfg["gpu_kv_tokens"]),
                host_tier_gib=float(cfg["host_tier_gib"]), host_tier_tokens=htok,
                targets=CS.TARGETS)
    if cfg.get("calibration_knots_path"):
        conf["calibration_knots_path"] = cfg["calibration_knots_path"]
    arm.live2_configure(**conf)
    store = cfg.get("frames_root")
    cache = FC.FrameCache(Path(store), int(cfg.get("cache_cap_bytes")
                                           or FC.DEFAULT_CAP_B)) if store else None
    if cache is not None and cfg.get("warm_refs"):
        cache.warm(cfg["warm_refs"])
    be = None
    if cfg.get("server_url"):
        from asyncbackend import AsyncLive2Backend
        be = AsyncLive2Backend(cfg["server_url"], model=cfg.get("model") or "32BI",
                               strip_hints=bool(cfg.get("strip_hints", True)), cache=cache,
                               limit=int(cfg.get("http_limit") or 16384))
    logs = Logs(rdir).open()
    co = Live2Coordinator(arm, be, [], upload_mode=cfg["mode"],
                          window_s=float(cfg["run_s"]), drain_s=float(cfg.get("drain_s") or 10.0),
                          decision_period_s=float(cfg.get("decision_period_s") or 0.1),
                          gpu_kv_tokens=int(cfg["gpu_kv_tokens"]),
                          host_tier_gib=float(cfg["host_tier_gib"]), host_tier_tokens=htok,
                          seed=int(cfg.get("seed") or 0), logs=logs,
                          run_tag=cfg.get("run_tag") or CK.run_tag(int(cfg.get("seed") or 0),
                                                                   cfg["arm"]),
                          frames_root=(Path(store) if store else None), frame_cache=cache,
                          defer_images=bool(cfg.get("defer_images", True)),
                          dry_run=not bool(cfg.get("server_url")),
                          gpu_budget_s=cfg.get("gpu_budget_s"), targets=CS.TARGETS)
    br = EmulatorBridge(co)
    cpu0 = time.process_time()
    t_start = time.time()
    # 0 disables self-ticking, which is what makes a split run comparable line for line with an
    # in-process run: the child then acts only when the parent calls in, so the decision log is a
    # function of the parent's clock alone.
    self_tick_s = float(cfg.get("self_tick_s", 0.005) or 0.0)

    # THE REASON THIS PROCESS EXISTS (StudyLIVE2-harness step 1 finding). In one process the
    # coordinator is only driven when the emulator pops a heap action, never during the
    # real-time sleep between actions, so a request that FINISHES inside a sleep is not noticed
    # until the next action. Its `cloud_answer` then carries a `t_done` that is already in the
    # past, the emulator schedules the delivery behind its own clock, and the whole lateness
    # distribution is that notice delay: in the flash reproduction every late action was an
    # `answer_delivered` (p50 18.4 ms, p99 289.0 ms) while every other kind sat at p99 0.28 ms.
    # Here the child drives its OWN ticks off its own clock, so a completion is collected within
    # `self_tick_s` of happening whatever the parent is doing.
    inbox: "queue.Queue[Any]" = queue.Queue()

    def _rx() -> None:
        while True:
            m = recv_msg(sock)
            inbox.put(m)
            if m is None:
                return

    threading.Thread(target=_rx, name="live2-coord-rx", daemon=True).start()
    last_t, last_mono = 0.0, time.monotonic()
    n_self_ticks = 0

    def _now_t() -> float:
        return last_t + (time.monotonic() - last_mono)

    while True:
        if self_tick_s <= 0.0:
            msg = inbox.get()
        else:
            try:
                msg = inbox.get(timeout=self_tick_s)
            except queue.Empty:
                n_self_ticks += 1
                replies = br.tick(_now_t()) or ()
                if replies:
                    send_msg(sock, {"op": "replies", "replies": list(replies)})
                continue
        if msg is None:
            break
        op = msg.get("op")
        if op in ("event", "tick"):
            last_t, last_mono = float(msg["t"]), time.monotonic()
        if op == "event":
            replies = br.on_event(msg["event"], float(msg["t"])) or ()
        elif op == "tick":
            replies = br.tick(float(msg["t"])) or ()
        elif op == "finish":
            res = co._result(cpu0, time.time() - t_start)
            res["bridge"] = br.describe()
            res["self_ticks"] = n_self_ticks
            res["self_tick_s"] = self_tick_s
            if be is not None and hasattr(be, "metrics"):
                res["backend"] = be.metrics()
            res["cache"] = cache.stats() if cache is not None else None
            res["pid"] = os.getpid()
            res["cpu_s_child"] = round(time.process_time() - cpu0, 4)
            logs.close()
            if be is not None:
                be.close()
            (rdir / "coordinator_result.json").write_text(
                json.dumps(res, indent=1, default=str) + "\n")
            send_msg(sock, {"op": "result", "result": res})
            send_msg(sock, {"op": "closed"})
            return
        else:
            continue
        if replies:
            send_msg(sock, {"op": "replies", "replies": list(replies)})


# ---------------------------------------------------------------- starting the pair
class SplitRun:
    """`with SplitRun(cfg) as coord:` gives the parent a `RemoteCoordinator` to hand the emulator."""

    def __init__(self, cfg: Dict[str, Any], kind: str = "fake",
                 sock_path: Optional[str] = None) -> None:
        self.cfg = dict(cfg)
        self.kind = kind
        # AF_UNIX paths are capped near 108 bytes, and a scratch run directory is easily
        # longer than that, so the default socket lives in a short temp directory and the run
        # directory keeps only the result files.
        self.sock_path = sock_path or self._short_sock()
        self.proc: Any = None
        self.coord: Optional[RemoteCoordinator] = None
        self._listener: Optional[socket.socket] = None

    @staticmethod
    def _short_sock() -> str:
        import tempfile
        d = tempfile.mkdtemp(prefix="l2h", dir=tempfile.gettempdir())
        return str(Path(d) / "c.sock")

    def __enter__(self) -> RemoteCoordinator:
        if len(self.sock_path.encode()) > 100:
            raise ValueError(f"socket path too long for AF_UNIX ({len(self.sock_path)}): "
                             f"{self.sock_path}")
        Path(self.sock_path).parent.mkdir(parents=True, exist_ok=True)
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(self.sock_path)
        self._listener.listen(1)
        ctx = mp.get_context("spawn")
        self.proc = ctx.Process(target=coordinator_process, args=(self.sock_path, self.cfg),
                                name="live2-coordinator", daemon=True)
        self.proc.start()
        self._listener.settimeout(120.0)
        conn, _ = self._listener.accept()
        conn.setsockopt(socket.IPPROTO_TCP if False else socket.SOL_SOCKET, socket.SO_SNDBUF,
                        4 << 20)
        self.coord = RemoteCoordinator(conn, kind=self.kind)
        return self.coord

    def __exit__(self, *a) -> None:
        if self.coord is not None:
            self.coord.close()
        if self.proc is not None:
            self.proc.join(60.0)
            if self.proc.is_alive():
                self.proc.terminate()
                self.proc.join(10.0)
        if self._listener is not None:
            self._listener.close()
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass
