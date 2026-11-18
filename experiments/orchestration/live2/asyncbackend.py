#!/usr/bin/env python3
"""The coordinator's HTTP on ONE async client, off the decision loop. CPU only.

StudyLIVE2-harness. `backend.Live2Backend` posts with `urllib` on a 64-thread pool: every
response-reading thread holds the GIL while it decodes, and the body is serialized by
`json.dumps` on that thread too. In StudyLIVE2-pilot that pipeline left the real-time fleet
emulator's clock p99 511.6 ms late at 8 devices while the coordinator itself was idle (decision
p99 0.70 ms, CPU 4.7 %).

Two committed precedents are followed here, both from StudyRH6's row:

  * "frames base64-encoded once per process before the first cell and the body assembled from
    PRE-SERIALISED IMAGE FRAGMENTS (a 300-frame D2 request is 54 MB; RH5 json-serialised it in
    the event loop)" - so this module never calls `json.dumps` on a body that carries image
    bytes. `wire_bytes` splices the already-encoded base64 in, and the fragments come from
    `framecache.FrameCache`.
  * "httpx connection limit 16,384 (RH5 1,024)" - the pool limit is a flag, defaulted high.

WHAT DOES NOT CHANGE. The bytes on the wire, the arms, the decisions, the schema, the digests
and the scoring. `test_live2_harness.py` asserts `json.loads(wire_bytes(body))` equals
`json.loads(json.dumps(strip_internal(materialized_body)))` on every body shape this harness
sends, so the fast path is a serialization change and nothing else.

NOTHING HERE MEASURES ANYTHING. Latency fields it returns are the harness's own timings, exactly
as `Live2Backend` returns them.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import Future
from typing import Any, Dict, List, Optional

import bodies as B
from backend import Live2Submission

_SEP = b","


def _frag(part: Dict[str, Any]) -> bytes:
    """One content part as JSON bytes, splicing base64 in rather than re-encoding it.

    The base64 alphabet and the `data:image/jpeg;base64,` prefix contain no character JSON has
    to escape, which is why the splice is exact; everything else goes through `json.dumps`.
    """
    if part.get("type") != "image_url":
        return json.dumps(part).encode()
    iu = part.get("image_url")
    if not isinstance(iu, dict) or "url" not in iu:
        return json.dumps(part).encode()
    url = iu["url"]
    if not isinstance(url, str) or '"' in url or "\\" in url:
        return json.dumps(part).encode()
    uuid = json.dumps(part.get("uuid"))
    return (b'{"type":"image_url","image_url":{"url":"' + url.encode()
            + b'"},"uuid":' + uuid.encode() + b'}')


def wire_bytes(body: Dict[str, Any]) -> bytes:
    """The request body as bytes, without serializing the image payloads twice."""
    rest = {k: v for k, v in body.items() if k != "messages"}
    msgs = body.get("messages") or []
    if len(msgs) != 1 or not isinstance(msgs[0], dict):
        return json.dumps(body).encode()
    msg = msgs[0]
    head = {k: v for k, v in msg.items() if k != "content"}
    out: List[bytes] = [b"{"]
    for k, v in rest.items():
        out += [json.dumps(k).encode(), b":", json.dumps(v).encode(), _SEP]
    out.append(b'"messages":[{')
    for k, v in head.items():
        out += [json.dumps(k).encode(), b":", json.dumps(v).encode(), _SEP]
    out.append(b'"content":[')
    parts = msg.get("content") or []
    for i, p in enumerate(parts):
        if i:
            out.append(_SEP)
        out.append(_frag(p))
    out.append(b"]}]}")
    return b"".join(out)


class AsyncLive2Backend:
    """One asyncio loop in one thread, one `httpx.AsyncClient`, bodies built on that loop."""

    def __init__(self, base_url: str, model: str = "32BI", strip_hints: bool = True,
                 cache: Any = None, limit: int = 16384, timeout_s: float = 600.0,
                 record_bodies: bool = True, time_scale: float = 1.0) -> None:
        import httpx
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.strip_hints = bool(strip_hints)
        self.cache = cache
        self.record_bodies = bool(record_bodies)
        self.time_scale = float(time_scale)
        self.sent: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="live2-http", daemon=True)
        self._thread.start()
        self._ready.wait(10.0)
        limits = httpx.Limits(max_connections=int(limit),
                              max_keepalive_connections=int(limit))
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), limits=limits)
        self.build_s = 0.0
        self.n_built = 0

    # ---- the loop thread
    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    # ---- the Live2Backend surface the coordinator uses
    def submit_live2(self, sub: Live2Submission) -> Future:
        return asyncio.run_coroutine_threadsafe(self._post(sub), self._loop)

    def close(self) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(self._client.aclose(), self._loop)
            fut.result(30.0)
        except Exception:                                             # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(10.0)

    def metrics(self) -> Dict[str, Any]:
        return dict(n_built=self.n_built,
                    build_ms_total=round(self.build_s * 1000.0, 3),
                    build_ms_mean=(round(self.build_s * 1000.0 / self.n_built, 4)
                                   if self.n_built else None),
                    cache=(self.cache.stats() if self.cache is not None else None))

    # ---- one request
    async def _post(self, sub: Live2Submission) -> Dict[str, Any]:
        t_build = time.perf_counter()
        body = B.materialize(sub.body, self.cache)
        wire = B.strip_internal(body, strip_hints=self.strip_hints)
        wire = dict(wire)
        wire["model"] = self.model
        data = wire_bytes(wire)
        self.build_s += time.perf_counter() - t_build
        self.n_built += 1
        if self.record_bodies:
            with self._lock:
                self.sent.append(dict(request_id=sub.request_id, kind=sub.kind,
                                      device_id=sub.device_id, session_id=sub.session_id,
                                      cache_salt=wire.get("cache_salt"),
                                      mm_uuids=list(sub.mm_uuids),
                                      wire_sha256_16=_sha16(data), bytes=len(data)))
        t0 = time.time()
        ttft = None
        usage: Dict[str, Any] = {}
        status: Optional[int] = None
        err = None
        chunks: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        try:
            async with self._client.stream(
                    "POST", self.base_url + "/v1/chat/completions", content=data,
                    headers={"Content-Type": "application/json"}) as r:
                status = r.status_code
                if status != 200:
                    err = f"HTTP {status}: {(await r.aread())[:300]!r}"
                else:
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        if ttft is None:
                            ttft = time.time() - t0
                        d = _sse(line)
                        if not d:
                            continue
                        u = d.get("usage")
                        if isinstance(u, dict):
                            usage = u
                        for ch in d.get("choices") or ():
                            delta = ch.get("delta") or ch.get("message") or {}
                            piece = (delta.get("content")
                                     or delta.get("reasoning_content") or "")
                            if piece:
                                text_parts.append(piece)
                            if ch.get("logprobs"):
                                chunks.append(dict(logprobs=ch["logprobs"]))
        except Exception as e:                                        # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        total = time.time() - t0
        return dict(request_id=sub.request_id, kind=sub.kind, sent_s=sub.sent_s,
                    ttft_s=ttft, total_s=total, http_status=status, error=err,
                    usage=usage, text="".join(text_parts), chunks=chunks, sub=sub)


def _sha16(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()[:16]


def _sse(line: str) -> Dict[str, Any]:
    s = line.strip()
    if s.startswith("data:"):
        s = s[5:].strip()
    if not s or s == "[DONE]" or not s.startswith("{"):
        return {}
    try:
        d = json.loads(s)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}
