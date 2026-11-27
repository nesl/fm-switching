#!/usr/bin/env python3
"""CATCH-UP PREFILL of the reconnect backlog (switch `live2_catchup_prefill`, arm `-la-er-cu`).

DEV BUILD, DEFAULT OFF on every arm. Design: research/study_sync_redesign_from_b2.md, line (b).

MECHANISM. After a link outage the device uploads its held frames in a burst; each arrives as a
`history_append` and raises the session's `est_tokens`. Rung 3's warm-ahead (`arms_v5rules2`) asks
for ONE slice per chunk of new material (an edge on cumulative tokens, D160 (1)), so a burst of
about 8,000 tokens leaves most of itself unbuilt, and the first question after the drain carries the
tail as uncached prefill inside its own 3 s deadline. With the switch on, a session that has just
come back online is also asked for a slice EVERY epoch (a level test, only inside the catch-up
window) until the backlog has arrived and its tail is below the arm's own chunk size.

NO NEW CONSTANT. The window opens at the arm's first read of a new `DeviceLink.back_online_at`, with
`est0` = the session's est_tokens at that read; it closes when est - est0 >= the link's own
`backlog_tokens` (the backlog has arrived) AND est - built < `chunk_tokens` (the arm's existing
steady-state tail). The slice size is the arm's own `slice_tokens` (1,024). Pacing: one catch-up
piece in flight per device (read from `obs.cloud.in_flight_work`, the W register), and every piece
still goes through the coordinator's `can_spend`, `_share_ok`, the arm's guard (sheds warming first)
and the state leg's HOLD_BACK. A session whose built prefix layer P believes mostly evicted is
skipped (the 0b `prefix_mostly_uncached` test): that rebuild is the state leg's decision, not a
catch-up. Ordering: the catch-up asks are appended AFTER the ordinary warm-ahead asks, sorted by the
arm's own predicted next-question time (`_last_q_t + _gap_ewma`), unknown last, session id last.
NOT IMPLEMENTED: a deficit-weight ordering (the deficit weight already scales the harm term the
state leg prices each catch-up piece with).

READ SITES: `arms_v5rules2.V5Rules2Arm.decide` (`observe`, `candidates`, `account`); the decision it
changes is the MATERIALIZE list `act.sessions`, enacted at `coordinator._enact` (MATERIALIZE branch)
-> `_advance_build` -> `release_piece`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import book_belief_uncached as BB

SWITCH = "live2_catchup_prefill"
LOG_CAP = 4000


class CatchupSwitchError(RuntimeError):
    """The switch was a truthy CLASS attribute or a non-bool."""


def arm_enables(arm: Any) -> bool:
    """Is catch-up prefill on for THIS INSTANCE? Default False; instance dict only."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(SWITCH, False)):
                raise CatchupSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "it requires an arm-scoped INSTANCE attribute" % (SWITCH, klass.__name__))
    v = own.get(SWITCH, False)
    if not isinstance(v, bool):
        raise CatchupSwitchError("%s must be a bool, got %r" % (SWITCH, type(v).__name__))
    return v


class State:
    def __init__(self) -> None:
        self.seen: Dict[str, float] = {}                 # device -> back_online_at already latched
        self.win: Dict[str, Tuple[int, int, str]] = {}   # session -> (est0, backlog_tokens, device)
        self.log: List[Dict[str, Any]] = []


def observe(arm: Any, obs: Any, roster: Dict[str, Any]) -> None:
    """Open the catch-up window at the FIRST read of a new back_online_at. Runs every epoch, before
    the guard test, so a shed epoch cannot delay the baseline `est0`."""
    cu: State = arm._cu_state
    est = roster.get("est_tokens_by_session") or {}
    sdev = roster.get("session_device") or {}
    devs = roster.get("devices") or {}
    for lk in (getattr(obs, "device_links", None) or ()):
        if not lk.connected or lk.back_online_at is None:
            continue
        if cu.seen.get(lk.device_id) == lk.back_online_at:
            continue
        cu.seen[lk.device_id] = lk.back_online_at
        arm.stats["catchup_reconnects_seen"] += 1
        if int(lk.backlog_tokens) <= 0:
            continue
        for sid, did in sdev.items():
            if did == lk.device_id and str((devs.get(did) or {}).get("type")) == "robot":
                cu.win[sid] = (int(est.get(sid, 0)), int(lk.backlog_tokens), str(did))
                arm.stats["catchup_windows_opened"] += 1
                if len(cu.log) < LOG_CAP:
                    cu.log.append(dict(t=round(float(obs.now_s), 4), ev="open", sid=sid,
                                       est0=int(est.get(sid, 0)), backlog=int(lk.backlog_tokens)))


def candidates(arm: Any, obs: Any, roster: Dict[str, Any], ordinary: set) -> List[str]:
    """Sessions in a catch-up window that need another slice now (not already an ordinary ask)."""
    cu: State = arm._cu_state
    est = roster.get("est_tokens_by_session") or {}
    built = roster.get("built_tokens_by_session") or {}
    pb = roster.get("pb_cached_by_session") or {}
    live = set(obs.live_sessions or ())
    rows = getattr(getattr(obs, "cloud", None), "in_flight_work", None) or ()
    busy = {str(r.device_id) for r in rows if str(r.kind) in ("piece", "whole")}
    out: List[str] = []
    for sid, (est0, backlog, did) in sorted(cu.win.items()):
        e = int(est.get(sid, 0))
        b = int(built.get(sid, 0) or 0)
        tail = e - b
        if sid not in live:
            del cu.win[sid]
            arm.stats["catchup_windows_closed_session_gone"] += 1
            continue
        if e - est0 >= backlog and tail < int(arm.chunk_tokens):
            del cu.win[sid]
            arm.stats["catchup_windows_closed_done"] += 1
            if len(cu.log) < LOG_CAP:
                cu.log.append(dict(t=round(float(obs.now_s), 4), ev="close", sid=sid, est=e,
                                   built=b))
            continue
        if tail <= 0:
            continue
        if sid in ordinary:
            arm.stats["catchup_epochs_ordinary_ask_already"] += 1
            continue
        if did in busy:
            arm.stats["catchup_epochs_paced_one_in_flight"] += 1
            continue
        if b > 0 and BB.booked_uncached(b, int((pb.get(sid) or {}).get("cached", 0)),
                                        1)[2]:
            arm.stats["catchup_epochs_prefix_not_resident"] += 1
            continue
        out.append(sid)
    arm.stats["catchup_candidates"] += len(out)
    return out


def order(arm: Any, sids: List[str]) -> List[str]:
    """Earliest predicted next question first (the arm's own `_last_q_t + _gap_ewma`), unknown
    last, session id last. `roster.session_device` maps the session to its device."""
    sdev = (arm._roster or {}).get("session_device") or {}

    def key(sid: str):
        did = sdev.get(sid)
        last, gap = arm._last_q_t.get(did), arm._gap_ewma.get(did)
        nxt = (last + gap) if (last is not None and gap is not None) else float("inf")
        return (nxt, sid)
    return sorted(sids, key=key)


def account(arm: Any, plan: Any, extra: List[str], now_s: float) -> None:
    cu: State = arm._cu_state
    legal = set(plan.legal)
    for sid in extra:
        if sid in legal:
            arm.stats["catchup_emitted"] += 1
            if len(cu.log) < LOG_CAP:
                cu.log.append(dict(t=round(float(now_s), 4), ev="ask", sid=sid))
        else:
            arm.stats["catchup_not_emitted"] += 1
