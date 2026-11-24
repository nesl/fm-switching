#!/usr/bin/env python3
"""A streaming fake server with REALISTIC latencies, for harness work only. CPU only.

StudyLIVE2-harness, step 1. The committed StudyLIVE1 stub
(`experiments/orchestration/live/fake_server.py`) is kept unchanged and is not used here: it
samples its own service time, answers without `logprobs`, and - the point of this module - it
does not have to READ a large request body, which is the work StudyLIVE2-pilot's lateness is
suspected to come from. Reproducing the pilot on flash needs a server that

  * reads a real multi-megabyte base64 body off the socket,
  * takes the time the COMMITTED COST CURVES say the real server takes
    (`baselines/costs.py::episodic_cloud_latency_s` and `recall_ttft_s`, the same two functions
    `coordinator._dry_service_s` already uses, so the stand-in is not invented here),
  * streams its answer with first-token timing and `logprobs`, as the real server does under
    the fix2 bodies,
  * serves one request at a time per "engine" with a configurable concurrency, so a queue can
    form exactly as it does on the H100.

THIS IS A FIXTURE AND NOT A MEASUREMENT. Every run against it carries `server_kind = "fake"` and
the scorer already refuses to treat such a run as a measurement. The answer token is fixed, so
no number it returns is a model output.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parents[0] / "baselines"),
           str(HERE.parents[2] / "experiments/orchestration/baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import costs as C                                                       # noqa: E402

DEFAULT_CONCURRENCY = 4
DEFAULT_LOAD_PCT = 25


class _State:
    def __init__(self, concurrency: int, load_pct: int, scale: float) -> None:
        self.free = threading.Semaphore(concurrency)
        self.load_pct = int(load_pct)
        self.scale = float(scale)
        self.lock = threading.Lock()
        self.served = 0
        self.by_kind: Dict[str, int] = {}
        self.bytes_in = 0
        self.max_concurrent = 0
        self.running = 0
        # Test-only (H100 2026-11-24): seconds between the first content chunk and the end of the
        # stream, so a harness proof can hold an ANSWERED request open past finish (the r10175
        # case). 0 = the committed behaviour (both chunks back to back).
        self.tail_s = 0.0
        self.read_s = 0.0


STATE: Optional[_State] = None


def service_s(kind: str, tokens: int, n_images: int) -> float:
    """The committed curve for this request kind. Not a measurement, a stand-in."""
    st = STATE
    load = st.load_pct if st else DEFAULT_LOAD_PCT
    if kind == "episodic":
        n = 1 if n_images <= 1 else (3 if n_images <= 3 else 9)
        return float(C.episodic_cloud_latency_s("32BI", n, load, jpeg=True))
    return float(C.recall_ttft_s(max(int(tokens), 1), "COLD"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):                                                 # noqa: N802
        if self.path.startswith("/metrics"):
            body = b"# fake stream server\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):                                                # noqa: N802
        st = STATE
        if not self.path.startswith("/v1/chat/completions"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length") or 0)
        t_read = time.perf_counter()
        raw = self.rfile.read(n) if n else b"{}"
        read_s = time.perf_counter() - t_read
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        kind = str(body.get("fm_kind") or "episodic")
        tokens = int(body.get("fm_tokens") or 0)
        content = ((body.get("messages") or [{}])[0].get("content") or [])
        n_images = sum(1 for p in content if isinstance(p, dict)
                       and p.get("type") == "image_url")
        wants_lp = bool(body.get("logprobs"))
        with st.lock:
            st.bytes_in += len(raw)
            st.read_s += read_s
        st.free.acquire()
        with st.lock:
            st.running += 1
            st.max_concurrent = max(st.max_concurrent, st.running)
        try:
            time.sleep(service_s(kind, tokens, n_images) * st.scale)
            letter = "Yes" if wants_lp else "B"
            lp = {"content": [{"token": letter, "logprob": -0.2,
                               "top_logprobs": [{"token": "Yes", "logprob": -0.2},
                                                {"token": "No", "logprob": -1.8}]}]}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i, piece in enumerate((letter, "")):
                ch = dict(id="fakestream", object="chat.completion.chunk", model="32BI",
                          choices=[dict(index=0, delta=dict(content=piece),
                                        logprobs=(lp if (i == 0 and wants_lp) else None),
                                        finish_reason=None if i == 0 else "stop")],
                          usage=(dict(prompt_tokens=max(tokens, 1), completion_tokens=1,
                                      total_tokens=max(tokens, 1) + 1,
                                      prompt_tokens_details=dict(cached_tokens=0))
                                 if i else None))
                self._chunk(("data: " + json.dumps(ch) + "\n\n").encode())
                if i == 0 and st.tail_s > 0:
                    time.sleep(st.tail_s)
            self._chunk(b"data: [DONE]\n\n")
            self._chunk(b"")
        finally:
            with st.lock:
                st.running -= 1
                st.served += 1
                st.by_kind[kind] = st.by_kind.get(kind, 0) + 1
            st.free.release()

    def _chunk(self, payload: bytes) -> None:
        # a client that has gone away mid-stream is normal at teardown and is not an error of
        # the fixture's; the run's own error count is what matters
        try:
            self.wfile.write(b"%x\r\n" % len(payload) + payload + b"\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class serve:
    """`with serve(0, ...) as url:` - the same shape as the committed stub's `serve`."""

    def __init__(self, port: int = 0, concurrency: int = DEFAULT_CONCURRENCY,
                 load_pct: int = DEFAULT_LOAD_PCT, scale: float = 1.0,
                 tail_s: float = 0.0) -> None:
        self.tail_s = float(tail_s)
        self.port = int(port)
        self.concurrency = int(concurrency)
        self.load_pct = int(load_pct)
        self.scale = float(scale)
        self.srv: Any = None
        self.thread: Any = None

    def __enter__(self) -> str:
        global STATE
        STATE = _State(self.concurrency, self.load_pct, self.scale)
        STATE.tail_s = self.tail_s
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.srv.daemon_threads = True
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        return "http://127.0.0.1:%d" % self.srv.server_address[1]

    def __exit__(self, *a) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    @staticmethod
    def stats() -> Dict[str, Any]:
        st = STATE
        if st is None:
            return {}
        with st.lock:
            return dict(served=st.served, by_kind=dict(st.by_kind), bytes_in=st.bytes_in,
                        max_concurrent=st.max_concurrent,
                        body_read_s_total=round(st.read_s, 4))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    ap.add_argument("--load-pct", type=int, default=DEFAULT_LOAD_PCT)
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args(argv)
    with serve(a.port, a.concurrency, a.load_pct, a.scale) as url:
        print(f"fake streaming server on {url} (FIXTURE, not a measurement)", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
