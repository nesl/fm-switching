#!/usr/bin/env python3
"""StudySLICE1's P2 and P3 release rules, mirrored for the policy suite.

StudyB-baselines amendment 2 (2026-11-13), items 7 and 8. CPU only.

Every rule and constant below is mirrored from `experiments/cost/study_slice1_live.py`, which is
the DEFINITION of P0-P4, with the line ranges cited per item. Nothing here is tuned, and no
StudySLICE1 RESULT sets any value: only the policy definition is mirrored.

| mirrored object | source, `experiments/cost/study_slice1_live.py` |
|---|---|
| `ALIGN_S = 0.005`                     | l. 73 |
| `P3_SLICE_TOKENS = 2048`              | l. 74, and l. 118 (`n` for P3_2048 / P4) |
| `LAT_FACTOR`, `SLACK_MARGIN_S`        | l. 79-80 |
| `next_due_s`                          | l. 157-162 (`next_ep_due`) |
| `wait_gap_release` (P2's hold)        | l. 164-177 (`wait_gap`) |
| `align_release` (P3's alignment)      | l. 179-186 (`align_after_due`) |
| P2's `deadline_start`                 | l. 211-213 |
| P3's per-slice alignment              | l. 214-215 |
| one cold request in the engine at a time, EDF | l. 204-205 and l. 231-232 |

WHAT THE ORCHESTRATOR MAY KNOW. StudySLICE1's live harness holds the episodic schedule in
`STATE["ep_abs"]` because it IS the generator of that schedule. A policy may not read it. The
mirror therefore predicts the next episodic call from the CADENCE-ONLY model of StudySLICE1 Part
D-b: each stream's own past deliveries, its cadence, and a jitter margin. That is strictly less
information than the live harness's own lookup, and it is the one deliberate departure from the
mirrored definition; it is declared in `cards/constructed.md`.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence, Tuple

MIRRORED_FROM = "experiments/cost/study_slice1_live.py"
ALIGN_S = 0.005                      # l. 73
P3_SLICE_TOKENS = 2048               # l. 74, l. 118
LAT_FACTOR = {None: 1.321, 2048: 1.373}      # l. 79
SLACK_MARGIN_S = 0.25                        # l. 80
JITTER_MARGIN_S = 0.125              # the cadence-only model's margin; see the docstring


def next_due_s(now_s: float, last_s: Optional[float], cadence_s: float,
               jitter_margin_s: float = JITTER_MARGIN_S) -> Optional[float]:
    """When this stream's next episodic call is due, from its cadence and its own past.

    Mirrors `next_ep_due` (l. 157-162) but computes the time instead of looking it up: the first
    multiple of the cadence after `now`, counted from the last delivery the policy has seen, less
    a jitter margin so an early call is not missed. With no history at all the next call is
    assumed imminent, which is the conservative reading for a hold rule.
    """
    if cadence_s <= 0:
        return None
    if last_s is None:
        return now_s
    k = math.floor((now_s - last_s) / cadence_s) + 1
    return last_s + k * cadence_s - jitter_margin_s


def soonest_due_s(now_s: float, streams: Iterable[Tuple[Optional[float], float]]
                  ) -> Optional[float]:
    """The earliest next episodic call over the cloud streams, as (last_delivery_s, cadence_s)."""
    due = [d for d in (next_due_s(now_s, last, cad) for last, cad in streams) if d is not None]
    return min(due) if due else None


def gap_release(now_s: float, pred_s: float, deadline_start_s: float,
                next_due: Optional[float]) -> Tuple[bool, str, float]:
    """P2's rule, one decision epoch of `wait_gap` (l. 164-177).

    Returns (release_now, reason, hold_until_s). The reasons are StudySLICE1's own: 'slack' when
    the predicted answer no longer fits the deadline, 'gap' when no episodic call is due inside
    the predicted engine time, and 'hold' otherwise, held until just after the call that blocks.
    """
    if now_s >= deadline_start_s:
        return True, "slack", now_s
    if next_due is None or next_due - now_s > pred_s:
        return True, "gap", now_s
    return False, "hold", min(next_due + ALIGN_S, deadline_start_s)


def align_release(now_s: float, pred_s: float, next_due: Optional[float]
                  ) -> Tuple[bool, str, float]:
    """P3's rule, one decision epoch of `align_after_due` (l. 179-186): no hold to a gap and no
    slack guard, only alignment behind a call that is already due inside the predicted time."""
    if next_due is None or next_due - now_s > pred_s:
        return True, "align-clear", now_s
    return False, "align", next_due + ALIGN_S


def deadline_start_s(deadline_s: float, pred_s: float, slice_tokens: Optional[int] = None
                     ) -> float:
    """P2 / P4's slack guard (l. 211-213, l. 216-218): the latest start at which the predicted
    client-visible answer time still fits the deadline."""
    return deadline_s - (pred_s * LAT_FACTOR[slice_tokens] + SLACK_MARGIN_S)


def n_slices(tokens: int, slice_tokens: int = P3_SLICE_TOKENS) -> int:
    """How many prefix-chained links a build of `tokens` becomes (l. 118-135)."""
    return max(1, int(math.ceil(tokens / float(slice_tokens))))
