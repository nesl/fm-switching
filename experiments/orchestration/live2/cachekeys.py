#!/usr/bin/env python3
"""D84: devices never share cache entries. CPU only.

Two mechanisms, both verified present in vLLM 0.31.0 (see reports/study_live2_coord.md section
"vLLM 0.31.0 cache-isolation evidence"):

  1. a PER-DEVICE CACHE SALT on every request. vLLM's ChatCompletionRequest carries
     `cache_salt` (vllm/entrypoints/openai/chat_completion/protocol.py:456-467); it enters the
     first block's hash extra keys (vllm/v1/core/kv_cache_utils.py:636-640) and block hashes
     chain through `parent_block_hash` (vllm/v1/core/kv_cache_utils.py:684-713), so a different
     salt makes the WHOLE prefix chain a different key.
  2. a MULTIMODAL UUID PER (device, frame). A chat content part may carry `uuid`
     (vllm/entrypoints/chat_utils.py:1711, 1726-1733); it reaches the engine as
     `multi_modal_uuids` (vllm/entrypoints/chat_utils.py:1078-1079) and REPLACES the computed
     mm hash (vllm/multimodal/processing/inputs.py:90-105), which is both the prefix-cache mm
     extra key (vllm/v1/core/kv_cache_utils.py:552) and the processor/encoder cache key.

The uuid namespace follows the committed StudyRH7 / SLICE1 / ENG1c convention
(experiments/cost/study_rh7_eager_lazy.py:72-78, 90, 121):

    "<run_tag>|<device_id>|<session_id>|<frame_ref>"

so it is STABLE for a re-send of the same frame by the same device (within-device reuse is
unaffected, which D84 requires) and never equal across devices.
"""
import hashlib
from typing import Optional

SALT_LEN = 43                      # 43 base64 characters, the length vLLM's own field doc gives


def run_tag(seed: int, arm: str, label: str = "live2") -> str:
    """One tag per run, so two runs of the same arm never share engine-side cache entries."""
    h = hashlib.sha256(f"{label}|{arm}|{seed}".encode()).hexdigest()[:12]
    return f"{label}{h}"


def cache_salt(run_tag_: str, device_id: str) -> str:
    """Per-device salt. Deterministic in (run tag, device), so a replay reproduces it."""
    raw = hashlib.sha256(f"{run_tag_}|{device_id}".encode()).digest()
    import base64
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")[:SALT_LEN]


def mm_uuid(run_tag_: str, device_id: str, session_id: Optional[str], frame_ref: str) -> str:
    return f"{run_tag_}|{device_id}|{session_id or '-'}|{frame_ref}"


def check_isolation(salts_by_device, uuids_by_device_frame):
    """Assert D84 on a finished run's recorded request bodies.

    `salts_by_device`: {device_id: set of salts seen}
    `uuids_by_device_frame`: {(device_id, frame_ref): set of uuids seen}
    Returns a dict for the report; raises on a violation.
    """
    bad = {d: sorted(s) for d, s in salts_by_device.items() if len(s) != 1}
    if bad:
        raise AssertionError(f"D84: a device used more than one cache salt: {bad}")
    seen = {}
    for dev, salts in salts_by_device.items():
        s = next(iter(salts))
        if s in seen:
            raise AssertionError(f"D84: devices {seen[s]!r} and {dev!r} share a cache salt")
        seen[s] = dev
    multi = {k: sorted(v) for k, v in uuids_by_device_frame.items() if len(v) != 1}
    if multi:
        raise AssertionError(f"D84: a (device, frame) used more than one mm uuid: {multi}")
    by_uuid = {}
    for (dev, frame), uu in uuids_by_device_frame.items():
        u = next(iter(uu))
        if u in by_uuid and by_uuid[u][0] != dev:
            raise AssertionError(f"D84: mm uuid {u!r} shared by devices "
                                 f"{by_uuid[u][0]!r} and {dev!r}")
        by_uuid[u] = (dev, frame)
    return dict(n_devices=len(salts_by_device), n_distinct_salts=len(seen),
                n_device_frames=len(uuids_by_device_frame), n_distinct_uuids=len(by_uuid))
