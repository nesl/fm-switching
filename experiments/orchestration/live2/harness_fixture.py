#!/usr/bin/env python3
"""A flash-local frame store with the COMMITTED byte sizes. CPU only, a fixture.

StudyLIVE2-harness, step 1. The pilot's lateness is suspected to come from the size of the
request bodies, so reproducing it on flash needs bodies of the RIGHT SIZE. Flash holds none of
the frames (`StudyLIVE2-pre` section 2: the stores live on the frame host), but the per-frame
byte counts ARE committed, in
`results/orchestration/live2/pre/manifests/{nexar_q90,sember_d2_q88}_manifest.jsonl.gz`.

So this module writes, for each frame_ref the trace needs, a file of EXACTLY the committed byte
length, filled with deterministic pseudo-random bytes behind a JPEG SOI marker. The resulting
base64 payload has the same length as the real one, which is the only property the harness
measurement depends on.

THESE ARE NOT FRAMES. No image content is implied, nothing is decoded, no score computed from
them would mean anything, and no run against this store is a measurement. The store is written
under the scratch directory the caller names, never into `results/` and never into the real
`~/data/live2/jpeg` stores.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = ROOT / "results/orchestration/live2/pre/manifests"
NAMES = ("nexar_q90", "sember_d2_q88")


def manifest_bytes(names: Iterable[str] = NAMES) -> Dict[str, int]:
    """frame_ref -> committed JPEG byte count, from the Part-1 manifests."""
    out: Dict[str, int] = {}
    for name in names:
        p = MANIFESTS / f"{name}_manifest.jsonl.gz"
        if not p.exists():
            raise SystemExit(f"MISSING: {p}; the committed Part-1 manifest is the only source "
                             f"of the per-frame byte counts")
        for ln in gzip.open(p, "rt"):
            r = json.loads(ln)
            out[r["frame_ref"]] = int(r["bytes"])
    return out


def write_plain_manifest(path: Path, sizes: Dict[str, int]) -> Path:
    """The flat `frame_ref / bytes` manifest `fleet/trace.py --frame-manifest` reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for ref, nb in sizes.items():
            fh.write(json.dumps(dict(frame_ref=ref, bytes=nb)) + "\n")
    return path


def _filler(ref: str, nb: int) -> bytes:
    """Deterministic bytes of exactly `nb` length, so a store is reproducible from the ref."""
    head = b"\xff\xd8\xff\xe0"
    if nb <= len(head):
        return head[:nb]
    need = nb - len(head)
    chunks: List[bytes] = []
    got = 0
    seed = ref.encode()
    i = 0
    while got < need:
        blk = hashlib.sha256(seed + b"|%d" % i).digest()
        chunks.append(blk)
        got += len(blk)
        i += 1
    return head + b"".join(chunks)[:need]


def build_store(out: Path, refs: Optional[Iterable[str]] = None,
                sizes: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Write a file per frame_ref under `out`, each exactly its committed length."""
    out = Path(out)
    sizes = sizes if sizes is not None else manifest_bytes()
    want = list(refs) if refs is not None else list(sizes)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    total = 0
    missing: List[str] = []
    for ref in want:
        nb = sizes.get(ref)
        if nb is None:
            missing.append(ref)
            continue
        p = out / ref
        if p.exists() and p.stat().st_size == nb:
            n += 1
            total += nb
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_filler(ref, nb))
        n += 1
        total += nb
    return dict(store=str(out), n_frames=n, total_bytes=total, n_missing=len(missing),
                missing_sample=missing[:5],
                note="FIXTURE: committed byte LENGTHS only, no image content, not a measurement")


def refs_in_trace(trace_dir: Path) -> List[str]:
    """Every frame_ref a generated trace will put on the wire, in first-seen order."""
    seen: Dict[str, None] = {}
    for ln in open(Path(trace_dir) / "trace.jsonl"):
        r = json.loads(ln)
        if r.get("frame_ref"):
            seen.setdefault(r["frame_ref"], None)
        for ref in (r.get("frame_refs") or ()):
            seen.setdefault(ref, None)
    return list(seen)
