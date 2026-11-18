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
from scores import D3_SCRIPT, O_Q4_SCRIPT, R1_SCRIPT, committed_constant, load_committed

MODEL_DEFAULT = "32BI"
DEFERRED = "<pending>"          # never reaches the wire; `materialize` replaces it
_PENDING = "_fm_pending"        # the deferred part's own bookkeeping, stripped on materialize

# ---------------------------------------------------------------- the committed scored bodies
# StudyLIVE2-fix2. The SH monitoring body and the robot recall body are the bodies that produced
# the committed scores the calibration (live2/calib.py) and the scorer (live2/scorer/score.py)
# consume, so neither is retyped here: the question text and the generation parameters are read
# out of the committed scripts.
#
# SH (dashcam), StudyD3 / StudyD14b / StudyORIN1-dense:
#   question                experiments/dashcam/d3_infer_vllm.py:43-44   (QUERY)
#   generation parameters   experiments/dashcam/d3_infer_vllm.py:45      (GEN)
#   body shape              experiments/dashcam/d3_infer_vllm.py:76-93   (body)
#   N = 1 header            experiments/dashcam/d3_infer_vllm.py:72-74   (grey_header), the same
#                           string the committed D14b N = 1 manifest carries
#   reused unchanged by     experiments/dashcam/d14b_infer_vllm.py:26-35
#   device side             experiments/device/study_d15_orin_nexar.py:118-124, same question,
#                           max_tokens and logprobs settings
#
# ROBOT RECALL, StudyR1 cell K1 (32B-I x RICH):
#   question text           experiments/sember/study_o_q4.py:158-168 (build_messages), which is
#                           the text StudyR1 stores per row (study_r1_inputs.py:80)
#   generation parameters   experiments/sember/study_r1_vllm.py:58 (CELLS["K1"]) and :61 (SEED)
#
# TWO EXEMPTIONS, and only two, over the committed bodies:
#   * the image bytes and their media type: round 1 sends the stored JPEGs (D70, D91), the
#     committed studies sent PNG (SH) or a comma-joined data:video/jpeg URL (recall);
#   * the D84 cache keys: `cache_salt` and the per-image client `uuid`, which post-date both.
# `stream` is a THIRD, declared deviation on the SH body: StudyD3 and StudyD14b send
# stream=False, while live2 must time the first token, and StudyORIN1-dense / StudyD15 stream the
# same scored request. StudyR1 streams, so the recall body has no deviation here.
SH_QUERY = committed_constant(D3_SCRIPT, "QUERY")
SH_GEN = committed_constant(D3_SCRIPT, "GEN")
SH_HEADER = "The following is 1 dashcam frame."          # d3 grey_header(1); D14b N=1 manifest
RECALL_GEN = dict(committed_constant(R1_SCRIPT, "CELLS")["K1"][2],
                  seed=committed_constant(R1_SCRIPT, "SEED"))
_build_messages = load_committed(O_Q4_SCRIPT, "build_messages")

SCORED_KINDS = ("monitor", "recall")


def recall_question_text(question: str, options: Sequence[str]) -> str:
    """StudyR1's stored question text, built by StudyO's own `build_messages`.

    StudyR1 took exactly this element (`study_r1_inputs.py:80`), so no second wording exists.
    """
    msgs = _build_messages(dict(question=question, options=list(options)), [])
    return msgs[0]["content"][1]["text"]


def _data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def image_part(uuid: str, path: Optional[Path], frame_ref: Optional[str] = None,
               defer: bool = False) -> Dict[str, Any]:
    """Bytes plus uuid when the engine has not seen this frame, a uuid-only reference when it
    has (StudyRH7 `frag_bytes` / `frag_ref`).

    With `defer`, the part is returned with a PLACEHOLDER in place of the data URL and
    `materialize` fills it in later, off the decision loop (StudyLIVE2-harness). The resulting
    wire part is identical either way; only the moment the base64 is computed differs.
    """
    if path is None:
        return {"type": "image_url", "image_url": None, "uuid": uuid}
    if defer:
        return {"type": "image_url", "image_url": DEFERRED,
                "uuid": uuid, _PENDING: dict(frame_ref=frame_ref, path=str(path))}
    return {"type": "image_url", "image_url": {"url": _data_url(Path(path))}, "uuid": uuid}


def materialize(body: Dict[str, Any], cache: Any = None) -> Dict[str, Any]:
    """Turn every deferred image part into the part `image_part` would have built.

    Called off the decision loop (the backend's own worker). Mutates and returns `body`. A frame
    that cannot be resolved raises, because sending a body with a placeholder in it would put a
    literal "<pending>" where an image belongs.
    """
    for part in body.get("messages", [{}])[0].get("content", ()):
        pend = part.pop(_PENDING, None) if isinstance(part, dict) else None
        if pend is None:
            continue
        ref, path = pend.get("frame_ref"), pend.get("path")
        url = (cache.data_url(ref, Path(path)) if cache is not None
               else _data_url(Path(path)))
        if url is None:
            raise FileNotFoundError(f"frame {ref!r} at {path!r} cannot be read; a deferred image "
                                    f"part must never be sent unmaterialized")
        part["image_url"] = {"url": url}
    return body


def is_materialized(body: Dict[str, Any]) -> bool:
    return not any(isinstance(p, dict) and _PENDING in p
                   for p in body.get("messages", [{}])[0].get("content", ()))


def build_body(*, kind: str, device_id: str, session_id: Optional[str], run_tag: str,
               salt: str, header: str, frames: Sequence[Dict[str, Any]],
               question: Optional[str] = None, options: Sequence[str] = (),
               max_tokens: int = 1, model: str = MODEL_DEFAULT, stream: bool = True,
               est_tokens: int = 0, retain: bool = True,
               time_scale: float = 1.0, defer_images: bool = False) -> Dict[str, Any]:
    """One chat-completions body.

    `frames` is a list of {"frame_ref": str, "path": Path or None}; `path` None means send the
    uuid-only reference because this device already sent those bytes.
    """
    gen: Dict[str, Any] = dict(temperature=0.0, max_tokens=int(max_tokens))
    if kind == "monitor":
        # the committed SH body: its header, one frame, its question, its generation parameters
        if question not in (None, "", SH_QUERY):
            raise ValueError("the SH monitoring body carries StudyD3's committed question; a "
                             "caller may not substitute one")
        if len(frames) != 1:
            raise ValueError(f"the committed SH body is one frame per call, got {len(frames)}")
        header, question, options = SH_HEADER, SH_QUERY, ()
        gen = dict(SH_GEN)
    elif kind == "recall":
        if question:
            question, options = recall_question_text(question, options), ()
        gen = dict(RECALL_GEN)
    content: List[Dict[str, Any]] = [{"type": "text", "text": header}]
    uuids: List[str] = []
    for f in frames:
        u = mm_uuid(run_tag, device_id, session_id, f["frame_ref"])
        uuids.append(u)
        content.append(image_part(u, f.get("path"), f.get("frame_ref"), defer_images))
    if question:
        q = question if not options else (question + "\n" + "\n".join(options))
        content.append({"type": "text", "text": q})
    body: Dict[str, Any] = dict(
        model=model, stream=bool(stream),
        messages=[dict(role="user", content=content)],
        cache_salt=salt, **gen,
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
