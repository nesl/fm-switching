#!/usr/bin/env python3
"""D179 (4): DEADLINE FEASIBILITY RE-CHECKED AT THE MOMENT OF RELEASE (user ruling 2026-11-22).

b7 tests whether a request can make its deadline AT ARRIVAL. Between arrival and release the
queue ahead of it changes, and nothing re-asks the question, so a request admitted when the
engine was idle is still sent when it no longer has a chance. This module is the wire-time
re-ask: if the request can no longer make its deadline, IT IS NOT SENT, the device answer stands,
and the event is counted and logged.

SCOPE. The three DEADLINE query types of spec v6 section 2 only: alert, recall, assistance.
Background work (`piece`, `whole`, `touch`) carries no deadline and is out of scope here, which
is the same split `share_admission.BACKGROUND_KINDS` draws for the share allocator.

THE SWITCH IS AN ARM-SCOPED INSTANCE ATTRIBUTE, `live2_release_recheck`, DEFAULT FALSE.
`arm_enables` REFUSES a class-level ON (see its docstring). Both of the other shapes have cost
this project real cells: a module global that defaulted ON cost a whole live cell, and a
class-level switch turns a rung on for every instance in the same run and makes the cells
incomparable (the D172 rung-2 note on `live2_belief_apply`).

WHICH FEASIBILITY QUANTITY, AND WHY IT IS NOT A NEW ONE.

  b7's own test, at ARRIVAL, is `est <= qs` (hybrid/hybrid_arm.py:384) with
  `est = costs.recall_ttft_s(readiness_tokens, readiness)` (line 364) and `qs = q.slack_s(now)`.
  That `est` is StudyRH5 Part A's ISOLATED reload TTFT. It carries NO queue term at all, so it
  cannot express the one quantity a wire-time re-check exists to see: that the work in front of
  this request has grown since it was admitted. Re-using it at release would re-compute the same
  number against a slightly smaller slack and would therefore re-ask nothing.

  So the predictor here is the committed D162 first-token model, with its coefficients IMPORTED
  from `d162_price` and never retyped, applied to THIS request's predicted uncached tokens and to
  the uncached work already in flight ahead of it:

      est_first_token_s = DP.first_token_s(uncached, queued_uncached_ahead)
      feasible          = est_first_token_s <= (deadline_abs - t_release)

  This is the SAME COMPARATOR SHAPE as b7 (a predicted first-token time against the time
  remaining to the deadline) and the SAME model the planner's harm term and the coordinator's
  budget charge already read, which is what the one-price-source ruling of 2026-11-21 asks for.
  It is not a second feasibility notion; it is b7's notion with the term that makes release time
  different from arrival time.

THE ALERT PATH HAS NEVER HAD A FEASIBILITY GATE AT ALL, so for alerts this is the FIRST
feasibility test on that path, not a re-check of one. `hybrid/hybrid_arm.py:351` computes `slack`
for a dashcam instant and line 355 appends the item UNCONDITIONALLY; the only read of
`it["slack"]` is line 443, inside the utility-per-cost ORDERING index. `share_capacity.py` says
the same thing from the data side: not one decline counter appears in any of the four committed
base cells, so the alert feasibility share of the not-sent opportunities is ZERO.

FOR AN ALERT EPISODE THE SKIP IS THE QUESTION FOR THAT INSTANT ONLY, NEVER THE FRAME. The
coordinator's skip returns before `_mon_sent` is touched, so the frame is not recorded as sent;
the episode context is append-only EP-G, so the NEXT instant's `episode_frame_refs` still carries
it and that request's `n_new` therefore RISES by this frame. That property is load-bearing and is
asserted on the actual request body in `tests/test_release_recheck.py`.

COUNTERS. In the COORDINATOR's `counts`, not in `arm_stats`: the re-check is a coordinator action
taken at wire time, after the arm's decision, so it is not the arm's statistic. The four names
below are FROZEN - the H100's reader is already written against them.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import d162_price as DP

SWITCH_ATTR = "live2_release_recheck"

# the three DEADLINE types of spec v6 section 2
TYPES = ("alert", "recall", "assistance")
# the committed device-id prefixes (fleet/trace.py:445-447 emits dash%03d / robo%03d / asst%03d).
# Declared here so this module imports on a tree where session A's interface is not yet present,
# and CHECKED against that interface whenever it IS present - the same shape `d162_price` uses for
# its coefficients, and for the same reason: a silently drifting literal is how two "identical"
# classifications stop being identical.
PREFIX_TO_TYPE = {"dash": "alert", "robo": "recall", "asst": "assistance"}
# request kinds that carry no deadline: out of scope for this re-check (D179 (4))
BACKGROUND_KINDS = ("piece", "whole", "touch", "append")

COUNTER_TOTAL = "release_infeasible"
COUNTER_BY_TYPE = {"alert": "release_infeasible_alert",
                   "recall": "release_infeasible_recall",
                   "assistance": "release_infeasible_assistance"}
# a request this module could not classify: NOT one of the four frozen names, and diagnostic only
COUNTER_UNCLASSIFIED = "release_recheck_unclassified_device"

# what the skipped opportunity's outcome row and decision row say
DECISION = "DEVICE-on-release-infeasible"
LOG_KIND = "release_infeasible"


class ReleaseRecheckSwitchError(RuntimeError):
    """The switch was declared in a shape D179 (4) forbids."""


class InterfaceDrift(RuntimeError):
    """The local type map no longer matches session A's committed interface."""


try:                                                                        # pragma: no cover
    import share_admission as _SA
except Exception:                                                           # noqa: BLE001
    _SA = None


def _check_against_interface() -> Optional[Dict[str, Any]]:
    """Compare the local type map against `share_admission`, when that module is importable."""
    if _SA is None:
        return None
    bad = []
    if dict(getattr(_SA, "PREFIX_TO_TYPE", {})) != PREFIX_TO_TYPE:
        bad.append({"name": "PREFIX_TO_TYPE", "declared": PREFIX_TO_TYPE,
                    "interface": dict(getattr(_SA, "PREFIX_TO_TYPE", {}))})
    if tuple(getattr(_SA, "TYPES", ())) != TYPES:
        bad.append({"name": "TYPES", "declared": list(TYPES),
                    "interface": list(getattr(_SA, "TYPES", ()))})
    return {"agrees": not bad, "mismatches": bad,
            "interface": "share_admission (session A, D179 interface)"}


_DRIFT = _check_against_interface()


def assert_no_interface_drift() -> Dict[str, Any]:
    if _DRIFT is None:
        return {"checked": False, "why": "share_admission not importable from here"}
    if not _DRIFT["agrees"]:
        raise InterfaceDrift("release_recheck disagrees with session A's interface: %s"
                             % (_DRIFT["mismatches"],))
    return {"checked": True, "agrees": True}


def arm_enables(arm: Any) -> bool:
    """Is the re-check on for THIS ARM INSTANCE? Default False.

    PLAIN DICT LOOKUP ON THE INSTANCE, deliberately, and a class-level ON RAISES. `getattr` would
    read a class attribute as though the instance had declared it, which is how one switch turns a
    rung on for every arm in a run; a class default of False is harmless and is allowed through,
    because it cannot do that.
    """
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if SWITCH_ATTR not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(SWITCH_ATTR, False)):
                raise ReleaseRecheckSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "D179 (4) requires an arm-scoped INSTANCE attribute: a class-level switch "
                    "turns the rung on for every arm in the run."
                    % (SWITCH_ATTR, klass.__name__))
        return False
    return bool(own[SWITCH_ATTR])


# ---------------------------------------------------------------------------
# WHICH DEADLINE TYPES THIS ARM RE-CHECKS. D190 (5) addition, ADDITIVE AND DEFAULTING TO ALL THREE.
#
# WHY IT EXISTS. The re-check is one switch over three types, and the three types are not alike.
# Measured on the committed rung-3 s4 cell (d190_rung4_margin_diagnosis.json): of 2,290 sent-and-late
# alert instants, OTHER ALERT FRAMES are the dominant blocker for 84.1 percent and recall questions
# for 6.9 percent. So the alert path is where the loss is. The recall path is the one that COST: the
# r1 cells, which ran the re-check on all three types over the shares base, skipped 34 recall
# questions at s4 and took robot on time to 95 against rung 3's 122. Running both paths at once
# would change two things in one arm and the alert contribution could not be read out of the result.
#
# THE DEFAULT IS ALL THREE TYPES, so no arm that does not declare this attribute can move. That is
# what makes this additive rather than a change to a committed component: `covex-v6-state-shares-r1`
# and every other arm that enables the re-check keeps exactly the behaviour it was measured with,
# and the proof of that is the off-switch and positive-control digests, not this comment.
TYPES_ATTR = "live2_release_recheck_types"


def types_for(arm: Any) -> Tuple[str, ...]:
    """The deadline types this ARM INSTANCE re-checks. Default: all three.

    Read from the instance only, like the switch itself and for the same reason. An unknown type
    name RAISES rather than being ignored: a typo that silently re-checked nothing would read as
    "the mechanism did not fire", which is the failure shape this project keeps paying for.
    """
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    v = own.get(TYPES_ATTR)
    if v is None:
        return TYPES
    got = tuple(str(x) for x in v)
    bad = [x for x in got if x not in TYPES]
    if bad:
        raise ReleaseRecheckSwitchError(
            "%s names %r, which is not one of the deadline types %r"
            % (TYPES_ATTR, bad, list(TYPES)))
    if not got:
        raise ReleaseRecheckSwitchError(
            "%s is empty on %r. An arm that re-checks nothing must leave the SWITCH off, so that "
            "the off-switch identity proof is what demonstrates it, rather than an enabled "
            "mechanism with no types that looks live and does nothing."
            % (TYPES_ATTR, getattr(arm, "name", arm)))
    return got


def is_background(kind: str) -> bool:
    return str(kind) in BACKGROUND_KINDS


def type_of_request(kind: str, device_id: str) -> Optional[str]:
    """alert / recall / assistance, or None if this request is not a deadline request of ours.

    The device-id prefix is the discriminator, which is how the committed cells distinguish the
    three types (`share_capacity.py`, cross-checked there against deadline_s 1.0 / 3.0 / 2.0 in
    every committed cell). `kind` only decides whether the request is a deadline request at all.
    """
    if is_background(kind):
        return None
    if str(kind) not in ("monitor", "recall"):
        return None
    qtype = PREFIX_TO_TYPE.get(str(device_id or "")[:4])
    if str(kind) == "monitor" and qtype not in (None, "alert"):
        raise RuntimeError("a monitor request from device %r classifies as %r, not alert"
                           % (device_id, qtype))
    return qtype


def decide(*, qtype: str, uncached: int, queued_uncached_ahead: int,
           remaining_s: float) -> Dict[str, Any]:
    """Can this request still make its deadline, at the instant it would go on the wire?

    `remaining_s` is `deadline_abs - t_release`, computed by the caller from the opportunity's own
    absolute deadline, never from a per-type constant: the deadline is a property of the instant.
    """
    est = DP.first_token_s(uncached, queued_uncached_ahead)
    return {"qtype": qtype, "uncached": max(int(uncached), 0),
            "queued_uncached_ahead": max(int(queued_uncached_ahead), 0),
            "est_first_token_s": est, "remaining_s": float(remaining_s),
            # the SAME direction as b7's `est <= qs` (hybrid/hybrid_arm.py:384)
            "feasible": bool(est <= float(remaining_s))}


def note_infeasible(counts: Dict[str, int], qtype: str) -> Tuple[str, str]:
    """Increment the total and the per-type counter. Both, always, so the sum identity holds."""
    if qtype not in COUNTER_BY_TYPE:
        raise KeyError("no release_infeasible counter for query type %r" % (qtype,))
    counts[COUNTER_TOTAL] += 1
    counts[COUNTER_BY_TYPE[qtype]] += 1
    return COUNTER_TOTAL, COUNTER_BY_TYPE[qtype]


def totals_agree(counts: Dict[str, Any]) -> bool:
    """The identity the H100's reader checks: the total is the sum of the three per-type counts."""
    return int(counts.get(COUNTER_TOTAL, 0)) == sum(int(counts.get(n, 0))
                                                    for n in COUNTER_BY_TYPE.values())


def as_dict() -> Dict[str, Any]:
    return {"ruling": "D179 (4), user ruling 2026-11-22",
            "switch": {"attr": SWITCH_ATTR, "scope": "arm instance", "default": False},
            "types": list(TYPES), "prefix_to_type": dict(PREFIX_TO_TYPE),
            "background_kinds_out_of_scope": list(BACKGROUND_KINDS),
            "counters": dict({"total": COUNTER_TOTAL}, **COUNTER_BY_TYPE),
            "predictor": {"source": DP.SOURCE,
                          "form": ("first_token_s = %.8f + %.10f * uncached + %.10f * "
                                   "queued_uncached_ahead"
                                   % (DP.INTERCEPT_S, DP.PER_UNCACHED_S, DP.PER_QUEUE_S)),
                          "why_not_b7s_est": ("costs.recall_ttft_s is an ISOLATED reload TTFT "
                                              "with no queue term, so it cannot see that the "
                                              "queue ahead grew between arrival and release")},
            "interface_drift_check": _DRIFT,
            "alert_path_note": ("this is the FIRST feasibility test the alert path has ever had: "
                                "hybrid/hybrid_arm.py:351 computes slack, line 355 appends the "
                                "item unconditionally, and the only read of it['slack'] is line "
                                "443 inside the utility-per-cost ORDERING index")}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
