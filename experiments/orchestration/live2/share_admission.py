#!/usr/bin/env python3
"""D179 share-based admission: the INTERFACE. Sessions B, C and D build against this file.

STATUS AT THIS COMMIT: interface only. `allowed()` returns ADMIT with reason "disabled" unless the
switch is on, and the switch is OFF on every arm, so this file changes no decision anywhere. The
allocator body is session A's next commit; the signatures below are frozen so B and C are not
blocked on it.

THE RESOURCE (D179 (1)). W = the predicted uncached tokens of requests SUBMITTED AND NOT YET AT
FIRST TOKEN, tracked per query type. First token is OBSERVABLE ONLINE: asyncbackend fires
`on_first` at the first CONTENT token (asyncbackend.py:250-255) and the coordinator already
consumes it as `answer_on_first` (coordinator.py:1540, procsplit.py:413). So W needs no
approximation and is NOT the completion-based quantity: `_uncached_in_flight` decrements at
COMPLETION and therefore includes decode time, which is not queue-ahead work for the D162 fit.
Both are kept, separately named, because they price different things:
  _uncached_in_flight   submit -> completion, the D174 budget charge's queue input
  W (here)              submit -> FIRST TOKEN, the D179 admission resource

W MUST BE DRAINED AT TWO PLACES, NOT ONE, and this is not a detail. `on_first` is wired only when
a real backend exists (procsplit.py:430-433), so IN A DRY CELL THE FIRST-TOKEN EVENT NEVER FIRES
and a first-token-only drain would let W climb monotonically until the allocator shut for good.
That failure reads as "the floors are too tight", which is a SHARES RESULT, not a plumbing bug, so
it would have been believed. The coordinator therefore calls `on_first_token` from
`answer_on_first` AND `on_settled_without_first_token` from the settle path, which is idempotent
and covers dry cells, errors and refusals alike.

CONSEQUENCE FOR READING ANY DRY CELL (consistency check 4, definition audit): in a LIVE cell W is
submit to FIRST TOKEN; in a DRY cell it is submit to SETTLE, because that is the only event there
is. The two are the same name for different quantities, the dry one being the larger, so a dry
cell's W and hold figures MUST NOT be compared against a live cell's. A dry cell can prove the
allocator's LOGIC and its determinism; only a live cell can size W.

THE TYPES are the three query types of spec v6 section 2, classified from the device id prefix,
which is how the committed cells distinguish them (dash / robo / asst, cross-checked against
deadline_s 1.0 / 3.0 / 2.0 in every committed cell).

WHAT IS AND IS NOT A FLOOR (D179 (3), D181). Floors are per type and reserve capacity for
DELIVERABLE demand; they are frozen in `share_capacity.py` and never computed here. Background work
(warm, touch) has NO floor: it lives in the flexible pool and may borrow, but never into another
type's floor. Deadline requests may borrow any unused capacity.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import share_capacity as SCAP

TYPES = ("alert", "recall", "assistance")
# the committed device-id prefixes, cross-checked against deadline_s in every committed cell
PREFIX_TO_TYPE = {"dash": "alert", "robo": "recall", "asst": "assistance"}
DEADLINE_S = {"alert": 1.0, "recall": 3.0, "assistance": 2.0}
# ---- D230 (2) / D178 (3): THE GUARD'S EWMA LAG CHANNEL PER TYPE, AND ITS THRESHOLD.
# `d230_guard_107.json` (79eef689) measured the defect these two tables fix: the saturation
# guard had only TWO lag channels, because `coordinator._collect` folded every non-monitor
# completion into "recall". Assistance therefore had NO guard signal at all, and the alert
# channel crossed its own D178 (3) threshold of 0.8 s in 497 of 47,997 decision periods while
# reaching the as-built single 2.0 s bar in only 16. The names of the first two channels are
# NOT changed: they are the keys of `CoordState.lat` (cstate.py:311) and every committed arm
# reads them by those names. "assistance" is the THIRD channel, added additively.
GUARD_LAG_CLASS = {"alert": "episodic", "recall": "recall", "assistance": "assistance"}
# D178 (3): fire when a type's first-token lag exceeds 80 percent of ITS OWN deadline.
# DERIVED from DEADLINE_S above rather than written out, so the thresholds and the deadlines
# cannot drift apart and no threshold is a tuned number. The D178 (3) values are asserted
# below as a CHECK ON THE DERIVATION and are never the source.
GUARD_LAG_FRACTION_OF_DEADLINE = 0.8
GUARD_LAG_S_BY_CLASS = {GUARD_LAG_CLASS[t]: round(GUARD_LAG_FRACTION_OF_DEADLINE
                                                  * DEADLINE_S[t], 6) for t in TYPES}
assert GUARD_LAG_S_BY_CLASS == {"episodic": 0.8, "recall": 2.4, "assistance": 1.6}, \
    GUARD_LAG_S_BY_CLASS
# request kinds that are BACKGROUND work: no floor, flexible pool only (D179 (3))
BACKGROUND_KINDS = ("piece", "whole", "touch")


def type_of_device(device_id: str) -> Optional[str]:
    """alert / recall / assistance from the device id, or None if it is not one of ours."""
    return PREFIX_TO_TYPE.get(str(device_id or "")[:4])


def is_background(kind: str) -> bool:
    return str(kind) in BACKGROUND_KINDS


class WTracker:
    """W per type: submitted, not yet at first token. One instance per coordinator.

    Keyed on request id, and the DECREMENT MUST REMOVE THE SAME NUMBER THE INCREMENT ADDED, which
    is why the charged amount is stored rather than recomputed: the same mistake was made once in
    the budget path (coordinator.py:1144) and the comment there records it.
    """

    def __init__(self) -> None:
        self._w: Dict[str, int] = {t: 0 for t in TYPES}
        # (type, uncached, was_background). The FLAG IS STORED, not re-derived: the first
        # version subtracted from the background accumulator on EVERY first token, so a large
        # foreground request drove w_background to zero while a background request was still in
        # flight. Caught by the interface's own smoke test before anything was built on it.
        self._per_request: Dict[str, Tuple[str, int, bool]] = {}
        self._bg: Dict[str, int] = {t: 0 for t in TYPES}

    def on_submit(self, request_id: str, qtype: str, uncached: int, *, background: bool) -> None:
        if qtype not in self._w or not request_id:
            return
        u = max(int(uncached), 0)
        self._w[qtype] += u
        if background:
            self._bg[qtype] += u
        self._per_request[str(request_id)] = (qtype, u, bool(background))

    def on_first_token(self, request_id: str) -> None:
        """Called from the coordinator's `answer_on_first` hook. Idempotent: a second call for the
        same id is a no-op, because the completion path may also fire for a request whose first
        token was never observed (an error, or a refusal)."""
        got = self._per_request.pop(str(request_id), None)
        if got is None:
            return
        qtype, u, was_bg = got
        self._w[qtype] = max(self._w[qtype] - u, 0)
        if was_bg:
            self._bg[qtype] = max(self._bg[qtype] - u, 0)

    def on_settled_without_first_token(self, request_id: str) -> None:
        """A request that completed or failed without ever yielding a content token still has to
        leave W, or W leaks upward and the allocator closes for good."""
        self.on_first_token(request_id)

    def w(self, qtype: str) -> int:
        return int(self._w.get(qtype, 0))

    def w_background(self, qtype: str) -> int:
        return int(self._bg.get(qtype, 0))

    def total(self) -> int:
        return int(sum(self._w.values()))

    def as_dict(self) -> Dict[str, Any]:
        return {"w_by_type": dict(self._w), "w_background_by_type": dict(self._bg),
                "w_total": self.total(), "tracked_requests": len(self._per_request)}

    def items(self) -> Tuple[Tuple[str, str, int, bool], ...]:
        """D249 (a): the tracked set itself, as (request_id, qtype, uncached, background).

        READ-ONLY and a COPY: the tuple cannot be used to mutate `_per_request`, so publishing W
        into the observation cannot disturb the resource it reports. This is the accessor D249 (a)
        needs, and it exists so the published rows carry W's OWN uncached numbers rather than a
        second count derived somewhere else; two similar numbers under one name is how an
        in-flight total drifts, which `on_submit`'s comment records.
        """
        return tuple((rid, v[0], int(v[1]), bool(v[2])) for rid, v in list(self._per_request.items()))


def allowed(*, qtype: str, uncached: int, kind: str, tracker: WTracker,
            pending_by_type: Optional[Dict[str, int]] = None,
            weights_by_type: Optional[Dict[str, float]] = None,
            feasible: Optional[bool] = None,
            enabled: bool = False) -> Tuple[bool, str]:
    """May this request be submitted now under the share rules? (admit, reason).

    INTERFACE ONLY at this commit: with `enabled` False, which is every arm's default, it returns
    (True, "disabled") and nothing changes. Session A's next commit fills in the body: floors from
    share_capacity, the flexible pool split equally (covex-v6-state) or by deficit weight
    (covex-v6-fair and above), deadline requests borrowing any unused capacity, background work
    borrowing only outside other types' floors, the oversize-when-alone rule, and no preemption.

    `feasible` CARRIES THE b7 CONJUNCT EXPLICITLY, added after session C observed that without it
    the b7 half of D179 (3)'s oversize rule ("admitted only if b7-feasible AND nothing else of its
    type is in flight") is not observable through this interface, so it rested on a caller
    convention that nothing checked. None means "the caller has already established feasibility",
    which is the previous behaviour and keeps every existing call valid; False is an explicit
    infeasible and is refused whatever the shares say. A convention no test can reach is the same
    shape as a write-only field, which is why it is an argument now.
    """
    if not enabled:
        return True, "disabled"
    if feasible is False:
        return False, "infeasible"
    if qtype not in TYPES:
        return True, "untyped"

    u = max(int(uncached), 0)
    bg = is_background(kind)
    w = {t: tracker.w(t) for t in TYPES}
    used = sum(w.values())
    floor = SCAP.FLOORS_TOKENS
    own_floor = float(floor[qtype])
    headroom = SCAP.W_MAX_TOKENS - used

    # The share of a type = its floor plus its cut of the flexible pool. Equal cuts here; the
    # deficit-weighted variant is covex-v6-fair and above, which is why `weights_by_type` is in
    # the signature and read here rather than added later.
    wt = {t: 1.0 for t in TYPES}
    if weights_by_type:
        tot = sum(max(float(weights_by_type.get(t, 0.0)), 0.0) for t in TYPES)
        if tot > 0:
            wt = {t: max(float(weights_by_type.get(t, 0.0)), 0.0) / tot * len(TYPES)
                  for t in TYPES}
    flex_share = SCAP.FLEXIBLE_TOKENS * (wt[qtype] / sum(wt.values()))
    own_share = own_floor + flex_share

    # OVERSIZE: a single request larger than its whole share can never fit, so it would starve
    # for good under a pure share test. D179 (3) admits it only when nothing else of its type is
    # in flight, and only if feasible, which the caller has established (see `feasible` above).
    # BACKGROUND IS NOT SUBJECT TO THE OVERSIZE RULE, and getting this wrong nearly cost a false
    # report that D179's own numbers contradicted each other. D179 (3) chunks warms at 2,048 and
    # the equal-split recall share is 1,256.7, so an oversize branch that swallowed background
    # refused EVERY warm chunk, for good, in every state. That is not "the floors are too tight",
    # it is warming switched off, and the arm's whole mechanism with it. Background is tested
    # against BORROWABLE capacity below, where 2,048 fits whenever recall itself is idle.
    if u > own_share and not bg:
        if w[qtype] > 0:
            return False, "oversize_wait_for_own_type"
        # ADMITTED WITH NO HEADROOM TEST, and this is the rule as D179 (3) writes it: "admitted
        # only if b7-feasible and nothing else of its type is in flight". A headroom test here
        # (my first version) refused the MEDIAN recall question outright, because u_recall = 7,717
        # is 1.8x W_max = 4,323.3, so every recall would have been declined and the arm would have
        # served no robot traffic at all.
        #
        # THE CONSEQUENCE, WHICH IS A REAL LIMIT OF THE MECHANISM AND NOT A BUG: admitting it
        # drives W above W_max and takes capacity the alert floor reserves. Nothing can be
        # preempted (vLLM 0.31 recompute-only, and D179 (3) rules out preemption), so a floor can
        # only ever be protected PROSPECTIVELY, by refusing new work. Shares therefore stop MANY
        # recalls from piling up but cannot stop ONE median recall from overrunning the alert
        # floor for the length of its prefill, about 1.48 s under the D162 fit. Reports must show W
        # over time INCLUDING overruns rather than clipping at W_max, or the overrun is invisible
        # exactly where it matters.
        return True, ("oversize_alone_over_wmax" if u > SCAP.W_MAX_TOKENS else "oversize_alone")

    # A FLOOR IS AN ADMISSION GUARANTEE, NOT A BUDGET LINE, so it is tested BEFORE headroom and
    # admits even when W is already over W_max. The ordering matters more than it looks: with the
    # headroom test first, an alert of 374 tokens, which is less than a quarter of its own floor,
    # was REFUSED for the 1.48 s prefill of a single oversize recall, because headroom had gone
    # negative. That is the head-of-line blocking D179 exists to remove, rebuilt inside the
    # mechanism meant to remove it, and it would have shown up as shares failing their own alert
    # check. Overrunning W_max is the price of the oversize exemption; shutting out the type the
    # floor protects is not.
    if w[qtype] + u <= own_floor:
        return True, "own_floor"

    if u > headroom:
        return False, "w_max"

    # Inside its own share but above its floor: discretionary, so it needs real headroom.
    if w[qtype] + u <= own_share:
        return True, "own_share"

    # BORROWING. Capacity not inside any other type's floor is borrowable. A deadline request may
    # borrow it; background work may borrow only what is outside every floor, so a warm can never
    # push a deadline type below its floor. The quantity reserved for OTHERS is each other type's
    # floor less what that type already holds: a type already over its floor reserves nothing.
    reserved_for_others = sum(max(float(floor[t]) - w[t], 0.0) for t in TYPES if t != qtype)
    borrowable = headroom - reserved_for_others
    # Background may use its OWN type's floor: D179 (3) puts "warming and touch included" inside
    # recall's floor, so that floor exists partly for this work. "Never into another type's floor"
    # constrains BORROWING, which is what reserved_for_others already enforces. Subtracting the own
    # floor as well was the second error, and it denied a 2,048 chunk even with the engine idle.
    if u <= borrowable:
        return True, ("borrow_background" if bg else "borrow_deadline")
    return False, ("floor_denied_background" if bg else "floor_denied")


def summary(tracker: WTracker, *, enabled: bool) -> Dict[str, Any]:
    """The `arm_stats["share_admission"]` block the H100 reads. Shape fixed now so its reader can
    be written before the allocator exists."""
    return {"enabled": bool(enabled), "w_max": SCAP.W_MAX_TOKENS,
            "floors": dict(SCAP.FLOORS_TOKENS),
            "flexible": round(SCAP.FLEXIBLE_TOKENS, 1),
            "w_now_by_type": tracker.as_dict()["w_by_type"],
            "admits_by_type": {}, "deferred_by_type": {},
            "borrowed_by_type": {}, "borrow_denied_floor_by_type": {},
            "_note": "counters fill in session A commit 2; shape is frozen"}

class ShareSwitchError(RuntimeError):
    """Raised when the switch is set in a way that could turn the rung on for every arm."""


def arm_enables(arm) -> bool:
    """Read `live2_share_admission` from the ARM INSTANCE only.

    Same strictness as release_recheck.arm_enables, and for the same reason: a truthy CLASS
    attribute would switch the mechanism on for every arm that inherits it, which is how a module
    global defaulting ON once cost a whole live cell here. A class default of False is allowed
    through, because it cannot turn anything on.
    """
    inst = vars(arm).get("live2_share_admission", None)
    if inst is None:
        cls = getattr(type(arm), "live2_share_admission", False)
        if cls:
            raise ShareSwitchError(
                "live2_share_admission is set as a CLASS attribute on "
                f"{type(arm).__name__}; set it on the instance so it cannot enable every arm "
                "that inherits from it")
        return False
    return bool(inst)
