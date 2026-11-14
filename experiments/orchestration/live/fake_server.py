#!/usr/bin/env python3
"""A fake OpenAI-compatible server, so every ported arm can be tested with NO GPU. CPU only.

StudyLIVE1-port, part 4. It speaks the three endpoints the live orchestrator uses:

  POST /v1/chat/completions   streamed or not; the first token is emitted after a delay drawn
                              from the committed distributions (`ttft_model.py`), served through
                              ONE FIFO queue so that queueing is produced here rather than being
                              baked into the draw.
  GET  /v1/models             the model id, so a client can check it is talking to the right one
  GET  /metrics               vLLM's Prometheus names for what the orchestrator reads: running,
                              waiting and GPU KV usage, computed from this stub's own state

**NOTHING THIS SERVER PRODUCES IS A MEASUREMENT.** It is a test fixture: it checks that an arm's
actions are legal, that the loop enacts them, and that a decision trace can be produced.

Run it standalone with `python3 fake_server.py --port 8077`, or use `serve()` as a context
manager from a test.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ttft_model as TM          # noqa: E402

MODEL = "fake-32BI"
KV_TOKENS = 62944                # StudyRH3 / RH4 / RH5 / E10b, the image server's KV


class _State:
    def __init__(self, seed: int = 0) -> None:
        self.lock = threading.Lock()
        self.free = threading.Semaphore(1)       # ONE server: the FIFO queue
        self.rng = random.Random(seed)
        self.running = 0
        self.waiting = 0
        self.kv_tokens = 0
        self.served = 0
        self.by_kind: Dict[str, int] = {}


STATE = _State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):               # quiet
        return

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):                                             # noqa: N802
        if self.path.startswith("/v1/models"):
            return self._json(200, dict(object="list", data=[dict(id=MODEL, object="model")]))
        if self.path.startswith("/metrics"):
            with STATE.lock:
                txt = (f'vllm:num_requests_running{{model_name="{MODEL}"}} {STATE.running}\n'
                       f'vllm:num_requests_waiting{{model_name="{MODEL}"}} {STATE.waiting}\n'
                       f'vllm:gpu_cache_usage_perc{{model_name="{MODEL}"}} '
                       f'{min(STATE.kv_tokens / KV_TOKENS, 1.0):.6f}\n')
            raw = txt.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return self._json(404, dict(error="not found"))

    def do_POST(self):                                            # noqa: N802
        if not self.path.startswith("/v1/chat/completions"):
            return self._json(404, dict(error="not found"))
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        kind = str(body.get("fm_kind") or "episodic")       # our own hint field
        tokens = int(body.get("fm_tokens") or 0)
        stream = bool(body.get("stream"))
        retain = bool(body.get("fm_retain"))                # a session build keeps its KV
        scale = float(body.get("fm_time_scale") or 1.0)     # the test fixture's time compression
        with STATE.lock:
            STATE.waiting += 1
        STATE.free.acquire()                                 # the single server
        with STATE.lock:
            STATE.waiting -= 1
            STATE.running += 1
            STATE.kv_tokens += tokens
            service = TM.sample(kind, STATE.rng, tokens) * scale
        try:
            time.sleep(service)
            if stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for i, piece in enumerate(("A", "")):
                    chunk = dict(id="fake", object="chat.completion.chunk", model=MODEL,
                                 choices=[dict(index=0, delta=dict(content=piece),
                                               finish_reason=None if i == 0 else "stop")])
                    self._chunk(("data: " + json.dumps(chunk) + "\n\n").encode())
                self._chunk(b"data: [DONE]\n\n")
                self._chunk(b"")
            else:
                self._json(200, dict(id="fake", object="chat.completion", model=MODEL,
                                     choices=[dict(index=0, finish_reason="stop",
                                                   message=dict(role="assistant",
                                                                content="A"))],
                                     usage=dict(prompt_tokens=tokens, completion_tokens=1,
                                                total_tokens=tokens + 1)))
        finally:
            with STATE.lock:
                STATE.running -= 1
                if not retain:
                    STATE.kv_tokens = max(STATE.kv_tokens - tokens, 0)
                STATE.served += 1
                STATE.by_kind[kind] = STATE.by_kind.get(kind, 0) + 1
            STATE.free.release()

    def _chunk(self, raw: bytes) -> None:
        self.wfile.write(b"%x\r\n" % len(raw) + raw + b"\r\n")
        self.wfile.flush()


@contextlib.contextmanager
def serve(port: int = 0, seed: int = 0):
    """Start the stub on `port` (0 = any free port) and yield its base URL."""
    global STATE
    STATE = _State(seed)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8077)
    a = ap.parse_args()
    with serve(a.port) as url:
        print("fake OpenAI-compatible server on", url, flush=True)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
