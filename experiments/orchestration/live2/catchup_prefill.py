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
PACED MODE (`live2_catchup_prefill_paced`, arm `-la-er-cup`, requires the switch above): a session
is asked only while (1) its device's predicted next question is inside the warm horizon (the JIT
test: now >= last_q + gap - `_horizon_s(gap)`, prediction known), (2) it still has ask credit,
ceil(backlog / chunk_tokens) per window, the number of ordinary chunk-edge asks that much material
is worth, spent by catch-up asks AND ordinary asks, (3) the hybrid core's C5 cap is at its ceiling,
(4) the core's C2 epoch record shows no dashcam row and no single-shot row at risk this epoch.
Order: deficit weight (`_pd_w_of`, the rung-3 feed's `weight_device`) descending, then the gap order.
BUSY-X MODE (`live2_catchup_prefill_busyx`, arm `-la-er-cupx`, requires the paced mode): in addition
to the same-device piece/whole test, no catch-up ask while ANY deadline-bearing single-shot
(`qtype == "assistance"`) or dashcam (`qtype == "alert"`) request, of any device, is in flight, nor
while a piece/whole of ANY device with an open catch-up window is in flight. Same rows, same fields.

READ SITES: `arms_v5rules2.V5Rules2Arm.decide` (`observe`, `candidates`, `account`); the decision it
changes is the MATERIALIZE list `act.sessions`, enacted at `coordinator._enact` (MATERIALIZE branch)
-> `_advance_build` -> `release_piece`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import book_belief_uncached as BB

SWITCH = "live2_catchup_prefill"
PACED_SWITCH = "live2_catchup_prefill_paced"
BUSYX_SWITCH = "live2_catchup_prefill_busyx"
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


def arm_paced(arm: Any) -> bool:
    """Is the PACED mode on for THIS INSTANCE? Default False; instance dict only, strict bool, and
    it requires the catch-up switch itself."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if PACED_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(PACED_SWITCH, False)):
                raise CatchupSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "it requires an arm-scoped INSTANCE attribute" % (PACED_SWITCH, klass.__name__))
    v = own.get(PACED_SWITCH, False)
    if not isinstance(v, bool):
        raise CatchupSwitchError("%s must be a bool, got %r" % (PACED_SWITCH, type(v).__name__))
    if v and not arm_enables(arm):
        raise CatchupSwitchError("%s requires %s" % (PACED_SWITCH, SWITCH))
    return v


def arm_busyx(arm: Any) -> bool:
    """Is the WIDENED BUSY CHECK on for THIS INSTANCE? Default False; instance dict only, strict
    bool, and it requires the paced mode."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if BUSYX_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(BUSYX_SWITCH, False)):
                raise CatchupSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "it requires an arm-scoped INSTANCE attribute" % (BUSYX_SWITCH, klass.__name__))
    v = own.get(BUSYX_SWITCH, False)
    if not isinstance(v, bool):
        raise CatchupSwitchError("%s must be a bool, got %r" % (BUSYX_SWITCH, type(v).__name__))
    if v and not arm_paced(arm):
        raise CatchupSwitchError("%s requires %s" % (BUSYX_SWITCH, PACED_SWITCH))
    return v


def _core(arm: Any) -> Any:
    """The object that owns the C5 cap and the C2 epoch record (the hybrid core of `_base`)."""
    o = getattr(arm, "_base", None)
    for _ in range(8):
        if o is None:
            return None
        if "cap_ceiling" in getattr(o, "__dict__", {}):
            return o
        o = getattr(o, "_base", None) or getattr(o, "_inner", None)
    return None


class State:
    def __init__(self) -> None:
        self.credit: Dict[str, int] = {}                 # paced: asks left in the window
        self.seen: Dict[str, float] = {}                 # device -> back_online_at already latched
        self.win: Dict[str, Tuple[int, int, str]] = {}   # session -> (est0, backlog_tokens, device)
        self.supp: Dict[str, set] = {}
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
                if arm_paced(arm):
                    cu.credit[sid] = -(-int(lk.backlog_tokens) // int(arm.chunk_tokens))
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
    paced = arm_paced(arm)
    busyx = arm_busyx(arm) if paced else False
    if busyx:
        ss_fl = any(str(r.qtype) == "assistance" and bool(r.has_deadline) for r in rows)
        dash_fl = any(str(r.qtype) == "alert" and bool(r.has_deadline) for r in rows)
        win_dev = {w[2] for w in cu.win.values()}
        cu_fl = {str(r.device_id) for r in rows if str(r.kind) in ("piece", "whole")
                 and str(r.device_id) in win_dev}
    blocked = None
    if paced:
        core = _core(arm)
        now = float(obs.now_s)
        if core is None:
            arm.stats["catchup_paced_core_missing"] += 1
            blocked = "core"
        elif int(core.cap) < int(core.cap_ceiling):
            blocked = "c5"
        else:
            ep = core.c2_epoch
            if ep is None or ep[0] != now:
                arm.stats["catchup_paced_c2_epoch_stale"] += 1
            elif ep[1] > 0 or ep[2] > 0:
                blocked = "c2"
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
            if paced:
                cu.credit[sid] = cu.credit.get(sid, 0) - 1
            continue
        if paced:
            if blocked is not None:
                arm.stats["catchup_paced_suppressed_" + blocked] += 1
                cu.supp.setdefault(blocked, set()).add(sid)
                continue
            last, gap = arm._last_q_t.get(did), arm._gap_ewma.get(did)
            if last is None or gap is None:
                arm.stats["catchup_paced_skip_no_prediction"] += 1
                continue
            if float(obs.now_s) < last + gap - arm._horizon_s(gap):
                arm.stats["catchup_paced_skip_beyond_horizon"] += 1
                continue
            if cu.credit.get(sid, 0) <= 0:
                arm.stats["catchup_paced_skip_no_credit"] += 1
                continue
        if did in busy:
            arm.stats["catchup_epochs_paced_one_in_flight"] += 1
            continue
        if busyx:
            if ss_fl:
                arm.stats["catchup_paced_skip_busy_ss"] += 1
                continue
            if dash_fl:
                arm.stats["catchup_paced_skip_busy_dash"] += 1
                continue
            if cu_fl:
                arm.stats["catchup_paced_skip_busy_cu_global"] += 1
                continue
        if b > 0 and BB.booked_uncached(b, int((pb.get(sid) or {}).get("cached", 0)),
                                        1)[2]:
            arm.stats["catchup_epochs_prefix_not_resident"] += 1
            continue
        out.append(sid)
    arm.stats["catchup_candidates"] += len(out)
    return out


def order(arm: Any, sids: List[str], now_s: float = 0.0) -> List[str]:
    """Earliest predicted next question first (the arm's own `_last_q_t + _gap_ewma`), unknown
    last, session id last. `roster.session_device` maps the session to its device."""
    sdev = (arm._roster or {}).get("session_device") or {}

    def key(sid: str):
        did = sdev.get(sid)
        last, gap = arm._last_q_t.get(did), arm._gap_ewma.get(did)
        nxt = (last + gap) if (last is not None and gap is not None) else float("inf")
        return (nxt, sid)
    if arm_paced(arm):
        wf = arm._cup_w_of

        def pkey(sid: str):
            return (-float(wf(sdev.get(sid))),) + key(sid)
        return sorted(sids, key=pkey)
    return sorted(sids, key=key)


def account(arm: Any, plan: Any, extra: List[str], now_s: float) -> None:
    cu: State = arm._cu_state
    legal = set(plan.legal)
    for sid in extra:
        if sid in legal:
            arm.stats["catchup_emitted"] += 1
            if arm_paced(arm):
                cu.credit[sid] = cu.credit.get(sid, 0) - 1
            if len(cu.log) < LOG_CAP:
                cu.log.append(dict(t=round(float(now_s), 4), ev="ask", sid=sid))
        else:
            arm.stats["catchup_not_emitted"] += 1
