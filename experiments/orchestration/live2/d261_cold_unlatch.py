#!/usr/bin/env python3
"""D261: A REJECTION IS NOT PROOF OF COLD. The switch, and the belief bookkeeping.

STATUS: DEV BUILD on user ruling 2026-11-25 item 2, in the D249 dev line. DEFAULT OFF on every
arm. The only arm that turns it on is `covex-v6-fair-final-q` (rung 3 plus D249 plus this).
Rung 3 (`covex-v6-fair-final`) is untouched: `make_rung3()` with no arguments sets nothing here.

THE DEFECT, from `results/orchestration/live2/d257_robo001/robo001_starvation_diagnosis.md`.
`robo001|s001` lost its prefix in the engine's cache at t=743.9: two consecutive build pieces
returned `cached_tokens = 0` (t=743.94 pt=6,041; t=789.94 pt=7,031). The D150 corrector in APPLY
mode demoted the belief to COLD, the belief IS what the arm reads as readiness
(`cstate.observation` -> `RecallQuery.readiness`), COLD readiness fails the 3.0 s feasibility test
in `hybrid/hybrid_arm.py`, and the arm returns REJECT. *** A REJECTION SENDS NOTHING, NOTHING SENT
RE-WARMS THE PREFIX AND NOTHING SENT PRODUCES NEW TELEMETRY, SO THE NEXT QUESTION IS REJECTED TOO.
*** The session stayed COLD for 320 s and all 12 of its remaining questions were declined. It
received no request of any kind for the remaining 276 s.

*** THE OPTION CHOSEN, OF THE TWO THE RULING NAMES: (ii) TREAT A DECLINE AS NOT PROOF OF COLD. ***
Option (i), re-evaluate on the next telemetry reading, is UNEXERCISED in the diagnosed condition
and that is a stopping condition by CLAUDE.md Rule 2, not a fix: there IS no next telemetry
reading, because the decline is what prevents one. `robo001` received NO REQUEST OF ANY KIND after
t=789.94, so a rule keyed on the next reading never runs at any of the 12 instants. The decline is
the only event at those instants, so breaking the latch requires acting on the decline.

THE RULE, in two halves.

  1. MARKED ON WRITE. A demotion to cold that comes from a telemetry zero is recorded as a cold
     mark, together with the tier the belief held before the FIRST such zero. A further zero
     REFRESHES the mark and keeps that original tier. A NON-ZERO reading clears the mark, because
     the engine has just said the prefix is there and the corrector promotes anyway.
  2. CLEARED BY THE DECLINE IT CAUSED. When a recall is REJECTED on a session carrying a cold
     mark, the mark is cleared and the belief is restored to the tier recorded at the demotion.
     The rejection has to stop being the thing that keeps the belief that produced it.

*** A SECOND ZERO DOES NOT COUNT AS CONFIRMATION, AND THE FIRST BUILD OF THIS MODULE GOT THAT
WRONG. *** It had a clause saying any later reading settled the question, so a second zero made
the mark non-provisional and no rejection could clear it. THE DIAGNOSED CASE IS TWO CONSECUTIVE
ZEROS (t=743.94 pt=6,041 and t=789.94 pt=7,031), so that clause defeated the exact case this
ruling exists to fix. It passed the unit proofs because the unit proof asserted the wrong thing,
and it was caught by the whole-cell positive control, which reported `d261_cold_marked` 1 and
`d261_cold_unlatched` 0 with the decision log unchanged: CLAUDE.md Step 2b's ABSENT LINK, not a
negative. The clause was also option (i) smuggled back in, and option (i) is the one this module
rejects. What settles a cold belief here is EVIDENCE FROM SOMETHING SENT, never a count of
readings and never a decline.

WHAT THIS IS NOT, because the ruling excludes all three.
  * NOT a RECENT fallback. No evidence item, no representation and no action kind changes here.
    The arm's own branches are untouched; only the readiness it is handed can change.
  * NOT a change to the margin, and not a change to rung 3.
  * NOT a widening to every decline. `DEVICE` is an arm CHOOSING the device answer; only `REJECT`,
    the feasibility rejection the diagnosis traced, clears a mark.

THE READ THAT MAKES IT CAUSAL, because a quantity written and never read is ABSENT by CLAUDE.md
and that failure has shipped in this codebase before (`desired_tier`, `RecallAction.representation`).
The restored belief is read back, in this order, with no new read site invented for it:
    cstate.py  `SessionRec.believed_tier`         <- the belief, argmax
    cstate.py  `SessionRec.readiness`             <- believed_tier -> "GPU-WARM"|"HOST-WARM"|"COLD"
    cstate.py  `ClusterState.observation`         <- `ready = s.readiness()`, into RecallQuery
    hybrid/hybrid_arm.py `HybridArm.decide`       <- `C.recall_ttft_s(q.readiness_tokens,
                                                      q.readiness)`, which selects CLOUD / DEFER /
                                                      REJECT
That last line is the decision. Nothing here is read only by a counter.

WHAT IT COSTS, stated rather than hidden. The restored belief is the last POSITIVELY EVIDENCED
tier, not a fresh claim of warmth; if the prefix really is gone, the request that the restored
belief lets through comes back with another zero, the corrector demotes again, the mark is
refreshed, and the next decline clears it again. So the steady state on a permanently dropped
prefix is an ALTERNATION of one send and one decline, which is bounded and self-correcting instead
of a latch, and the price is a request that may be LATE rather than declined. That price is the
whole content of the option the ruling named: a decline is never evidence, so only something sent
can settle the belief. This module makes no claim about the VALUE of those answers; `robo001`'s
cloud answers were 0 of 4 correct when served (D257 (2)).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

D261_SWITCH = "live2_d261_cold_unlatch"

# The tiers a belief may be restored to. "cold" is excluded deliberately: restoring to cold is
# the no-op that would make this module the write-only shape its docstring refuses.
RESTORABLE_TIERS = ("gpu", "host")


class D261SwitchError(RuntimeError):
    """The switch was declared as a truthy CLASS attribute, which this build forbids."""


def arm_enables(arm: Any) -> bool:
    """Is D261 on for THIS ARM INSTANCE? Default False.

    INSTANCE-DICT LOOKUP ONLY, and a truthy CLASS attribute RAISES: the same shape, and for the
    same reason, as `d249_queue_visibility.arm_enables`, `release_recheck.arm_enables` and
    `share_admission.arm_enables`. A class attribute would switch D261 on for every arm that
    inherits from the same base in one run and would make the cells incomparable.
    """
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if D261_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(D261_SWITCH, False)):
                raise D261SwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "D261 requires an arm-scoped INSTANCE attribute"
                    % (D261_SWITCH, klass.__name__))
    return bool(own.get(D261_SWITCH, False))


def note_telemetry(session: Any, cached_tokens: Optional[int], before: str, after: str,
                   now: float) -> str:
    """Half 1. Record, refresh or drop the cold mark after ONE telemetry reading.

    Called only where the D150 corrector has already APPLIED its update, so this function never
    decides a tier; it records that the cold the corrector just wrote came from a zero.

    Returns the bookkeeping outcome, for the counters: "none" (no reading, or nothing to record),
    "marked" (a zero demoted a restorable tier to cold), "refreshed" (a further zero on a session
    that already carries a mark; the ORIGINAL tier is kept), "superseded" (a NON-ZERO reading, so
    the engine says the prefix is there and the mark is dropped).
    """
    if cached_tokens is None:                      # no usage block is NO EVIDENCE (D150)
        return "none"
    had = getattr(session, "cold_provisional_from", None)
    if int(cached_tokens) > 0:
        # EVIDENCE FROM SOMETHING SENT, and it points the other way. The corrector has already
        # promoted the belief; the mark has nothing left to restore.
        if had is None:
            return "none"
        session.cold_provisional_from = None
        session.cold_provisional_s = -1.0
        return "superseded"
    if had is not None:
        # A FURTHER ZERO. It refreshes the mark and KEEPS the original pre-cold tier: `before` is
        # "cold" by now, which is not restorable, and overwriting with it would silently retire
        # the mark. This is the clause the first build got wrong; see the module docstring.
        session.cold_provisional_s = float(now)
        return "refreshed"
    if after == "cold" and before in RESTORABLE_TIERS:
        session.cold_provisional_from = before
        session.cold_provisional_s = float(now)
        return "marked"
    return "none"


def clear_on_reject(session: Any, now: float) -> Optional[Dict[str, Any]]:
    """Half 2. A REJECT on a session with a provisional cold mark clears the mark.

    The belief is restored to the tier recorded at the demotion, which is the last positively
    evidenced tier for that session. Returns the restoration for the trace and the counters, or
    None when there was no provisional mark, which is the overwhelmingly common case.
    """
    frm = getattr(session, "cold_provisional_from", None)
    if frm is None:
        return None
    if frm not in RESTORABLE_TIERS:                                            # pragma: no cover
        return None
    before = session.believed_tier()
    if before != "cold":
        # The belief moved off cold without a telemetry reading (a placement action can do it),
        # so there is nothing to unlatch. Drop the stale mark and change no belief.
        session.cold_provisional_from = None
        session.cold_provisional_s = -1.0
        return None
    marked_s = float(getattr(session, "cold_provisional_s", -1.0) or -1.0)
    session.belief = {"gpu": 0.0, "host": 0.0, "cold": 0.0}
    session.belief[frm] = 1.0
    session.cold_provisional_from = None
    session.cold_provisional_s = -1.0
    return {"session_id": getattr(session, "session_id", None), "restored_to": frm,
            "from_tier": before, "marked_s": marked_s, "cleared_s": float(now),
            "held_s": (float(now) - marked_s) if marked_s >= 0.0 else None}


def describe() -> Dict[str, Any]:
    return {"switch": D261_SWITCH,
            "option": "(ii) a decline is not proof of cold",
            "option_rejected": ("(i) re-evaluate on the next telemetry reading: UNEXERCISED in "
                                "the diagnosed condition, which has no next reading"),
            "restorable_tiers": list(RESTORABLE_TIERS),
            "clears_on": "REJECT only, not DEVICE",
            "recent_fallback": False,
            "authority": ("user ruling 2026-11-25 item 2; "
                          "results/orchestration/live2/d257_robo001/"
                          "robo001_starvation_diagnosis.md")}
