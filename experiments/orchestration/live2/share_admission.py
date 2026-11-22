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
    raise NotImplementedError("session A commit 2: the allocator body")


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
