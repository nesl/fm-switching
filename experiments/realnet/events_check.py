#!/usr/bin/env python3
"""Validate StudyREAL-NET wire events against the REPO's OWN schema, not a copy of it.

StudyREAL-NET support module.

WHY THIS EXISTS. `live2/fleet/events.py` is the authoritative field list and it already
refuses a missing or unknown field (`make()` raises on both). `live2/schema.py` is the
coordinator's copy and `events.check_against_schema()` RAISES on any difference between the
two. If this harness kept its own third copy, a drift would show up as a silent behaviour
change in a cell rather than as an import-time failure.

So: this module IMPORTS the repo's events.py when it can reach it, and every event this
harness puts on the wire is built through the repo's own `make()`. Where the repo is not on
the path (an Orin holding only a slice, no checkout), `OFFLINE_FIELDS` mirrors it and
`check_drift()` reports that the check was skipped -- it never silently substitutes.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_EV = None
_WHY = "not attempted"


def _candidate_paths():
    env = os.environ.get("LIVE2_DIR")
    if env:
        yield Path(env) / "fleet" / "events.py"
    here = Path(__file__).resolve().parent
    # This package lives at experiments/realnet/, deliberately OUTSIDE
    # experiments/orchestration/ and experiments/lib/: those two trees are the run-path
    # identity used for same-code pairing, so adding a directory to either would change it.
    yield here.parent / "orchestration" / "live2" / "fleet" / "events.py"
    yield here.parent / "live2" / "fleet" / "events.py"
    yield here / "live2" / "fleet" / "events.py"


def load_repo_events():
    """Import live2/fleet/events.py if reachable. Returns the module or None."""
    global _EV, _WHY
    if _EV is not None:
        return _EV
    for p in _candidate_paths():
        if not p.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location("live2_fleet_events", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _EV = mod
            _WHY = "loaded %s" % p
            return _EV
        except Exception as e:
            _WHY = "failed to load %s: %s" % (p, e)
    if _WHY == "not attempted":
        _WHY = "live2/fleet/events.py not found on any candidate path"
    return None


def why() -> str:
    return _WHY


# Mirror of live2/fleet/events.py FIELDS, used ONLY where the repo is unreachable.
# Kept verbatim from the module read on 2026-11-25.
OFFLINE_FIELDS: Dict[str, tuple] = {
    "device_register": ("device_id", "type", "uplink_mbps", "rtt_ms", "start_t"),
    "session_start": ("device_id", "session_id", "t"),
    "session_end": ("device_id", "session_id", "t"),
    "monitor_offer": ("device_id", "opportunity_id", "instant_id", "t_capture", "deadline_s",
                      "frame_bytes", "device_score"),
    "monitor_frame": ("device_id", "opportunity_id", "instant_id", "t_capture", "t_arrive",
                      "deadline_s", "frame_ref", "frame_bytes", "episode_id", "episode_index",
                      "frame_refs", "episode_frames", "device_score"),
    "history_preload": ("device_id", "session_id", "frame_refs", "est_tokens", "t"),
    "history_append": ("device_id", "session_id", "batch_id", "t_arrive", "frame_refs",
                       "est_tokens"),
    "recall_question": ("device_id", "opportunity_id", "session_id", "question_id", "t_ask",
                        "t_arrive", "deadline_s", "question", "options", "category"),
    "pull_request": ("device_id", "instant_id", "t_sent"),
    "cloud_answer": ("device_id", "opportunity_id", "t_done", "payload"),
}
OFFLINE_OPTIONAL: Dict[str, tuple] = {
    "recall_question": ("category",),
    "monitor_frame": ("episode_id", "episode_index", "frame_refs", "episode_frames",
                      "device_score"),
    "monitor_offer": ("device_score",),
}
OFFLINE_TYPES = ("dashcam", "robot", "assistive")


def check_drift() -> Dict[str, Any]:
    """Compare OFFLINE_FIELDS with the repo's own FIELDS. Reports rather than raising."""
    ev = load_repo_events()
    if ev is None:
        return dict(checked=False, reason=why())
    diffs = []
    for k in sorted(set(OFFLINE_FIELDS) | set(getattr(ev, "FIELDS", {}))):
        a = tuple(OFFLINE_FIELDS.get(k, ()))
        b = tuple(getattr(ev, "FIELDS", {}).get(k, ()))
        if a != b:
            diffs.append(dict(kind=k, ours=a, repo=b))
    opt_diffs = []
    for k in sorted(set(OFFLINE_OPTIONAL) | set(getattr(ev, "OPTIONAL_FIELDS", {}))):
        a = tuple(OFFLINE_OPTIONAL.get(k, ()))
        b = tuple(getattr(ev, "OPTIONAL_FIELDS", {}).get(k, ()))
        if a != b:
            opt_diffs.append(dict(kind=k, ours=a, repo=b))
    return dict(checked=True, reason=why(), field_diffs=diffs,
                optional_diffs=opt_diffs, ok=not diffs and not opt_diffs)


def make(kind: str, **kw: Any) -> Dict[str, Any]:
    """Build one wire event through the repo's `make()` when reachable, else the mirror."""
    ev = load_repo_events()
    if ev is not None:
        return ev.make(kind, **kw)
    want = OFFLINE_FIELDS.get(kind)
    if want is None:
        raise KeyError("unknown event kind %r" % kind)
    opt = OFFLINE_OPTIONAL.get(kind, ())
    missing = [f for f in want if f not in kw and f not in opt]
    extra = [f for f in kw if f not in want]
    if missing or extra:
        raise ValueError("%s: missing=%s extra=%s" % (kind, missing, extra))
    if kind == "device_register" and kw["type"] not in OFFLINE_TYPES:
        raise ValueError("device type %r not in %s" % (kw["type"], OFFLINE_TYPES))
    return dict(kind=kind, **kw)


def check_slice_builds_events(records, answers_by_opp, device_id) -> Tuple[bool, str]:
    """Every record in a slice must build a schema-valid wire event. Returns (ok, why)."""
    for r in records:
        k = r.get("kind")
        try:
            if k == "device_register":
                make("device_register", device_id=device_id, type=r["type"],
                     uplink_mbps=r.get("uplink_mbps"), rtt_ms=r.get("rtt_ms"),
                     start_t=r.get("start_t"))
            elif k in ("session_start", "session_end"):
                make(k, device_id=device_id, session_id=r["session_id"], t=float(r["t"]))
            elif k == "history_preload":
                make("history_preload", device_id=device_id, session_id=r["session_id"],
                     frame_refs=r.get("frame_refs") or [],
                     est_tokens=int(r.get("cum_tokens") or r.get("est_tokens") or 0),
                     t=float(r["t"]))
            elif k == "history_batch":
                make("history_append", device_id=device_id, session_id=r["session_id"],
                     batch_id=r["batch_id"], t_arrive=float(r["t"]),
                     frame_refs=r.get("frame_refs") or [],
                     est_tokens=int(r.get("cum_tokens") or r.get("est_tokens") or 0))
            elif k == "monitor_opportunity":
                opp = str(r["opportunity_id"])
                prof = answers_by_opp.get(opp) or {}
                kw = dict(device_id=device_id, opportunity_id=opp,
                          instant_id=r.get("instant_id") or opp,
                          t_capture=float(r["t"]), t_arrive=float(r["t"]),
                          deadline_s=float(r["deadline_s"]),
                          frame_ref=r.get("frame_ref"),
                          frame_bytes=int(r.get("frame_bytes") or 0))
                if prof.get("device_score") is not None:
                    kw["device_score"] = float(prof["device_score"])
                make("monitor_frame", **kw)
            elif k == "recall_question":
                opp = str(r["opportunity_id"])
                kw = dict(device_id=device_id, opportunity_id=opp,
                          session_id=r.get("session_id"),
                          question_id=r.get("question_id") or opp,
                          t_ask=float(r["t"]), t_arrive=float(r["t"]),
                          deadline_s=float(r["deadline_s"]),
                          question=r.get("question"), options=r.get("options") or [])
                if r.get("category") is not None:
                    kw["category"] = r["category"]
                make("recall_question", **kw)
            else:
                return False, "unknown record kind %r" % k
        except Exception as e:
            return False, "%s on %r: %s" % (type(e).__name__, k, e)
    return True, "ok"
