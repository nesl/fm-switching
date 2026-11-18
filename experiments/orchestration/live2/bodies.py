#!/usr/bin/env python3
"""The request bodies the coordinator sends. CPU only: this module builds JSON, nothing else.

WIRE FORM, REUSED NOT REINVENTED. The prefix-chained append is the committed StudyRH7 /
StudySLICE1 / StudyENG1c mechanism, whose reference implementation is
`experiments/cost/study_rh7_eager_lazy.py` lines 72-108 (`frag_bytes`, `frag_ref`, `body7`) as
driven by `experiments/cost/study_slice1_live.py:106` (`build_cold`). That mechanism is:

  * every image content part carries a client `uuid`;
  * a frame whose bytes the engine has already seen is sent as a REFERENCE,
    `{"type": "image_url", "image_url": null, "uuid": <uuid>}`, which hits the engine's
    multimodal cache and the prefix cache without re-uploading the bytes;
  * a frame whose bytes are new is sent with bytes AND its uuid;
  * so appending a 30 s batch to a session is one request carrying references for the already
    sent frames and bytes for the new ones ("delta" mode), which is exactly what a history
    append and a chained rebuild piece need.

Those functions are not imported because they read a prebuilt in-memory fragment cache
(`R6._FRAG`) and the study's own session objects; the WIRE FORM here is identical and the
reference is cited above so the two can be compared by eye. `cache_salt` is added per D84,
which post-dates StudyRH7.

NOTHING HERE MEASURES ANYTHING.
"""
import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cachekeys import mm_uuid

MODEL_DEFAULT = "32BI"


def _data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def image_part(uuid: str, path: Optional[Path]) -> Dict[str, Any]:
    """Bytes plus uuid when the engine has not seen this frame, a uuid-only reference when it
    has (StudyRH7 `frag_bytes` / `frag_ref`)."""
    if path is None:
        return {"type": "image_url", "image_url": None, "uuid": uuid}
    return {"type": "image_url", "image_url": {"url": _data_url(Path(path))}, "uuid": uuid}


def build_body(*, kind: str, device_id: str, session_id: Optional[str], run_tag: str,
               salt: str, header: str, frames: Sequence[Dict[str, Any]],
               question: Optional[str] = None, options: Sequence[str] = (),
               max_tokens: int = 1, model: str = MODEL_DEFAULT, stream: bool = True,
               est_tokens: int = 0, retain: bool = True,
               time_scale: float = 1.0) -> Dict[str, Any]:
    """One chat-completions body.

    `frames` is a list of {"frame_ref": str, "path": Path or None}; `path` None means send the
    uuid-only reference because this device already sent those bytes.
    """
    content: List[Dict[str, Any]] = [{"type": "text", "text": header}]
    uuids: List[str] = []
    for f in frames:
        u = mm_uuid(run_tag, device_id, session_id, f["frame_ref"])
        uuids.append(u)
        content.append(image_part(u, f.get("path")))
    if question:
        q = question if not options else (question + "\n" + "\n".join(options))
        content.append({"type": "text", "text": q})
    body: Dict[str, Any] = dict(
        model=model, temperature=0.0, max_tokens=int(max_tokens), stream=bool(stream),
        messages=[dict(role="user", content=content)],
        cache_salt=salt,
    )
    if stream:
        body["stream_options"] = {"include_usage": True}
    # fm_* are the CPU stub's hint fields (experiments/orchestration/live/fake_server.py); a real
    # vLLM server ignores unknown top-level keys only if it is not strict, so a real run strips
    # them (see backend.Live2Backend(strip_hints=True)).
    body["fm_kind"] = _fm_kind(kind)
    body["fm_tokens"] = int(est_tokens)
    body["fm_retain"] = bool(retain)
    body["fm_time_scale"] = float(time_scale)
    body["_live2"] = dict(kind=kind, device_id=device_id, session_id=session_id,
                          mm_uuids=uuids, n_new_frames=sum(1 for f in frames
                                                           if f.get("path") is not None))
    return body


_FM = {"monitor": "episodic", "piece": "cold_recall", "whole": "cold_recall",
       "recall": "recall_escalation", "append": "recall_append", "touch": "recall_append"}


def _fm_kind(kind: str) -> str:
    return _FM.get(kind, "episodic")


def strip_internal(body: Dict[str, Any], strip_hints: bool = False) -> Dict[str, Any]:
    out = {k: v for k, v in body.items() if k != "_live2"}
    if strip_hints:
        out = {k: v for k, v in out.items() if not k.startswith("fm_")}
    return out


def body_digest(body: Dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(strip_internal(body), sort_keys=True)
                          .encode()).hexdigest()[:16]
