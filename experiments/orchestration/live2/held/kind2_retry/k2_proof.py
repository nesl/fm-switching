"""Kind-2 fix proof (prepared, not applied; user ruling 2026-11-24). CPU only, no server, no GPU.

Drives the REAL AsyncLive2Backend._post through httpx.MockTransport, so the request loop under test
is the production one, with three deterministic transport behaviours:
  normal    : 200, one SSE content chunk, [DONE]
  prebyte   : the FIRST call raises httpx.ReadError before any response (the kind-2 signature),
              later calls behave as `normal`
  midstream : 200, one SSE line, then the stream raises httpx.ReadError (an error AFTER bytes)
Usage: k2_proof.py <tree root> <mode: off|on> -> one JSON line per case.
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
L2 = root / "experiments/orchestration/live2"
for p in (L2, L2 / "fleet", root / "experiments/orchestration/baselines", root / "experiments/lib"):
    sys.path.insert(0, str(p))

import httpx                                   # noqa: E402
import asyncbackend as AB                       # noqa: E402
from backend import Live2Submission             # noqa: E402

SSE_OK = (b'data: {"choices":[{"index":0,"delta":{"content":"B"},"finish_reason":null}]}\n\n'
          b'data: {"choices":[{"index":0,"delta":{"content":""},"finish_reason":"stop"}],'
          b'"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}\n\n'
          b'data: [DONE]\n\n')


class _MidStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"choices":[{"index":0,"delta":{"content":"B"},"finish_reason":null}]}\n\n'
        raise httpx.ReadError("mid-stream")


def handler_for(case):
    calls = {"n": 0}

    def h(request):
        calls["n"] += 1
        if case == "prebyte" and calls["n"] == 1:
            raise httpx.ReadError("")
        if case == "midstream":
            return httpx.Response(200, stream=_MidStream(), headers={"Content-Type": "text/event-stream"})
        return httpx.Response(200, content=SSE_OK, headers={"Content-Type": "text/event-stream"})
    return h, calls


def sub(i):
    return Live2Submission(request_id=f"r{i}", decision_id=f"d{i}", kind="recall", device_id="robo000",
                           session_id="s0", opportunity_id=f"o{i}",
                           body={"messages": [{"role": "user", "content": [{"type": "text", "text": "q"}]}],
                                 "max_tokens": 1},
                           est_tokens=5, sent_s=0.0, cache_salt="salt")


STABLE = ("http_status", "error", "usage", "text", "exc_type", "exc_repr", "kind2_retried")
for i, case in enumerate(("normal", "prebyte", "midstream")):
    be = AB.AsyncLive2Backend("http://mock.invalid")
    h, calls = handler_for(case)
    be._client = httpx.AsyncClient(transport=httpx.MockTransport(h))
    if hasattr(be, "kind2_retry"):
        be.kind2_retry = (mode == "on")
        be._fresh_client = httpx.AsyncClient(transport=httpx.MockTransport(h))  # same scripted server
    r = be.submit_live2(sub(i)).result(20)
    out = {k: r.get(k) for k in STABLE}
    out.update(case=case, mode=mode, tree=root.name, transport_calls=calls["n"],
               n_kind2_retries=getattr(be, "n_kind2_retries", None),
               n_kind2_retry_ok=getattr(be, "n_kind2_retry_ok", None),
               kind2_first=(r.get("kind2_first") or {}).get("exc_type") if r.get("kind2_first") else None)
    be.close()
    print(json.dumps(out, sort_keys=True))
