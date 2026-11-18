#!/usr/bin/env python3
"""The coordinator's HTTP client: the EXISTING HttpBackend, with the live2 body and usage.

StudyLIVE2-coord. CPU only. A pure HTTP client of an OpenAI-compatible server
(request-harness pattern); `/metrics` is scraped, and nothing in this process touches an engine.

`experiments/orchestration/live/adapter.py::HttpBackend` is reused unchanged as the base class:
it owns the thread pool, the `/metrics` poller and the stream read that times the first token.
Only `post` is overridden, because live2 sends the committed StudyRH7 wire form plus D84's
`cache_salt` instead of StudyLIVE1's token-count placeholder body.
"""
import json
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapter import HttpBackend, Submission            # noqa: E402
import bodies as B                                     # noqa: E402


@dataclass
class Live2Submission:
    request_id: str
    decision_id: Optional[str]
    kind: str
    device_id: str
    session_id: Optional[str]
    opportunity_id: Optional[str]
    body: Dict[str, Any]
    est_tokens: int
    sent_s: float
    cache_salt: str
    mm_uuids: List[str] = field(default_factory=list)
    traffic_mix: Dict[str, int] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


class Live2Backend(HttpBackend):
    """HttpBackend with the live2 body builder, usage parsing and a record of what was sent."""

    def __init__(self, base_url: str, workers: int = 64, time_scale: float = 1.0,
                 model: str = "fake-32BI", strip_hints: bool = False,
                 record_bodies: bool = True) -> None:
        super().__init__(base_url, workers=workers, time_scale=time_scale, model=model)
        self.strip_hints = bool(strip_hints)
        self.record_bodies = bool(record_bodies)
        self.sent: List[Dict[str, Any]] = []
        self._lock = Lock()

    # ---- the live2 request
    def post_live2(self, sub: Live2Submission) -> Dict[str, Any]:
        wire = B.strip_internal(sub.body, strip_hints=self.strip_hints)
        wire = dict(wire)
        wire["model"] = self.model
        data = json.dumps(wire).encode()
        if self.record_bodies:
            with self._lock:
                self.sent.append(dict(request_id=sub.request_id, kind=sub.kind,
                                      device_id=sub.device_id, session_id=sub.session_id,
                                      cache_salt=wire.get("cache_salt"),
                                      mm_uuids=list(sub.mm_uuids),
                                      digest=B.body_digest(sub.body), bytes=len(data)))
        req = urllib.request.Request(self.base_url + "/v1/chat/completions", data=data,
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        ttft = None
        usage: Dict[str, Any] = {}
        status: Optional[int] = None
        err = None
        chunks: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                status = r.status
                for raw in r:
                    if raw.strip() and ttft is None:
                        ttft = time.time() - t0
                    d = _json_from_line(raw)
                    if not d:
                        continue
                    u = d.get("usage")
                    if isinstance(u, dict):
                        usage = u
                    # the answer text and the FIRST token's top-20 are what the committed score
                    # extractors read (live2/scores.py); without them no cloud_score exists
                    for ch in d.get("choices") or ():
                        delta = ch.get("delta") or ch.get("message") or {}
                        piece = delta.get("content") or delta.get("reasoning_content") or ""
                        if piece:
                            text_parts.append(piece)
                        if ch.get("logprobs"):
                            chunks.append(dict(logprobs=ch["logprobs"]))
        except Exception as e:                                        # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            status = getattr(e, "code", None)
        total = time.time() - t0
        return dict(request_id=sub.request_id, kind=sub.kind, sent_s=sub.sent_s,
                    ttft_s=ttft, total_s=total, http_status=status, error=err,
                    usage=usage, text="".join(text_parts), chunks=chunks, sub=sub)

    def submit_live2(self, sub: Live2Submission):
        return self.pool.submit(self.post_live2, sub)

    # The base class's token-count placeholder body is never used by live2; calling it would send
    # a body with no cache_salt, which D84 forbids.
    def post(self, sub: Submission) -> Dict[str, Any]:                # noqa: D102
        raise RuntimeError("live2 must not send the StudyLIVE1 placeholder body: it carries no "
                           "cache_salt and no mm uuids, which D84 requires. Use post_live2.")


def _json_from_line(raw: bytes) -> Dict[str, Any]:
    s = raw.decode(errors="replace").strip()
    if not s:
        return {}
    if s.startswith("data:"):
        s = s[5:].strip()
    if not s or s == "[DONE]" or not s.startswith("{"):
        return {}
    try:
        d = json.loads(s)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _usage_from_line(raw: bytes) -> Dict[str, Any]:
    u = _json_from_line(raw).get("usage")
    return u if isinstance(u, dict) else {}


def cached_tokens_of(usage: Dict[str, Any]) -> Optional[int]:
    """vLLM reports reused prompt tokens under `prompt_tokens_details.cached_tokens`.

    Absent (the CPU stub never reports it) means UNKNOWN, which is None, not zero: a zero would
    be read as a confirmed cold path and D81's WARM / COLD tag would then be a fabrication.
    """
    if not usage:
        return None
    d = usage.get("prompt_tokens_details")
    if isinstance(d, dict) and d.get("cached_tokens") is not None:
        return int(d["cached_tokens"])
    if usage.get("cached_tokens") is not None:
        return int(usage["cached_tokens"])
    return None


def prompt_tokens_of(usage: Dict[str, Any]) -> Optional[int]:
    if usage and usage.get("prompt_tokens") is not None:
        return int(usage["prompt_tokens"])
    return None


def output_tokens_of(usage: Dict[str, Any]) -> Optional[int]:
    if usage and usage.get("completion_tokens") is not None:
        return int(usage["completion_tokens"])
    return None
