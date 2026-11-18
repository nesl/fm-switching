#!/usr/bin/env python3
"""A real-server run REFUSES to start with a frame it cannot send. CPU only.

StudyLIVE2-harness addendum (2). The coordinator resolves `frames_root / frame_ref` and, when
the file is absent, sends the frame as a uuid-only REFERENCE (`bodies.image_part` with
`path=None`), which is the StudyRH7 wire form for "you have already seen these bytes". For a
frame whose bytes were never uploaded that is a lie to the engine: it claims a cache entry that
does not exist. On flash it merely makes the body smaller; against a real engine it corrupts the
prefix the whole study measures.

StudyLIVE2-harness found this in the committed inputs: of the 1,278 frame references an
8-device 120 s trace asks for, 30 have no row in the Part-1 manifests, all of them S-EMBER D2
references past the point the manifests cover (the manifests reach each session's LAST QUESTION;
the trace keeps appending history to the end of the session). The H100 will extend the D2 store
to each session's end. Until then a real-server trace must not need those frames, and this module
is what makes "must not" enforceable rather than hoped for.

A fake-server run is exempt on purpose: the fake-server tests build deliberately partial stores.
The exemption is by `server_kind`, so it cannot be taken by accident on a real run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

FAKE_KINDS = ("fake", "stub", "device-only-no-server")
MAX_REPORTED = 20


class MissingFrames(SystemExit):
    """Raised before anything is run, so no partial run directory is produced."""


def trace_frame_refs(trace_dir: Path) -> List[str]:
    """Every frame_ref the trace will put on the wire, in first-seen order."""
    seen: Dict[str, None] = {}
    for ln in open(Path(trace_dir) / "trace.jsonl"):
        r = json.loads(ln)
        if r.get("frame_ref"):
            seen.setdefault(r["frame_ref"], None)
        for ref in (r.get("frame_refs") or ()):
            seen.setdefault(ref, None)
    return list(seen)


def check(trace_dir: Path, frames_root: Optional[Path],
          refs: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Report, do not raise: which of the trace's frames have no file under `frames_root`."""
    want = list(refs) if refs is not None else trace_frame_refs(trace_dir)
    root = Path(frames_root) if frames_root else None
    missing: List[str] = []
    empty: List[str] = []
    for ref in want:
        if root is None:
            missing.append(ref)
            continue
        p = Path(ref)
        if not p.is_absolute():
            p = root / ref
        if not p.exists():
            missing.append(ref)
        elif p.stat().st_size == 0:
            empty.append(ref)
    return dict(trace_dir=str(trace_dir), frames_root=(str(root) if root else None),
                n_refs=len(want), n_missing=len(missing), n_empty=len(empty),
                missing=missing[:MAX_REPORTED], empty=empty[:MAX_REPORTED],
                ok=(not missing and not empty))


def require_frames(trace_dir: Path, frames_root: Optional[Path], server_kind: str,
                   refs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """The gate. A real-server run with any unstored or empty frame does not start."""
    rep = check(trace_dir, frames_root, refs)
    rep["server_kind"] = server_kind
    rep["enforced"] = server_kind not in FAKE_KINDS
    if rep["ok"] or not rep["enforced"]:
        return rep
    head = ", ".join(rep["missing"][:5]) or ", ".join(rep["empty"][:5])
    raise MissingFrames(
        "REFUSING TO START a %s run: %d of %d frame references in %s have no stored file under "
        "%s (%d more are present but empty). A frame with no file is sent as a uuid-only "
        "reference, which tells the engine it has already seen bytes that were never uploaded. "
        "Extend the store, or generate a trace that does not need these frames. First: %s"
        % (server_kind, rep["n_missing"], rep["n_refs"], trace_dir, rep["frames_root"],
           rep["n_empty"], head))
