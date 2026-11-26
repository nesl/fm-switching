"""Layer 0b: book the uncached work a build piece is PREDICTED to cause, from the arm's own belief.

A build is booked at its piece tokens only (`coordinator._advance_build`, "a build prefills exactly
its piece"). When the session's prefix is no longer in the engine's GPU KV, the engine re-prefills
that prefix as well, and none of it was booked (study_n32_diagnosis.md: n32, 286 of 536 pieces,
2.22M tokens). This module is the ONE place the corrected number is produced; the coordinator
writes it into `_uncached_last_charged` / `_uncached_in_flight` and every consumer of the booked
quantity (budget, W register, D249 in-flight rows, release re-check queue, C5 attribution) reads
it from there.

RULE, no new constant: booked = prefix x (1 - P cached fraction) + piece, P = predictive_belief.py
(pre-send, read-only). The switch REFUSES unless `live2_predictive_belief` is ON on the same arm.
`prefix_tokens` is the number of frames the request presents ahead of its new frames times
`cstate.D2_TOK_PER_IMG`-equivalent (the coordinator passes it), NOT `built_tokens`, which counts
only the coordinator's own pieces and understates the presented prefix.

Switch `live2_book_belief_uncached`: DEFAULT OFF, INSTANCE attribute only. A truthy class
attribute raises, and a non-bool value raises.
"""
from __future__ import annotations

from typing import Any, Tuple

SWITCH = "live2_book_belief_uncached"


class BookBeliefSwitchError(RuntimeError):
    """The switch was declared on a class, or with a non-bool value."""


def arm_enables(arm: Any) -> bool:
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if SWITCH not in own:
        for klass in type(arm).__mro__:
            if SWITCH in klass.__dict__ and bool(klass.__dict__[SWITCH]):
                raise BookBeliefSwitchError(
                    "%s is ON as a CLASS attribute of %s; layer 0b requires an arm-scoped "
                    "INSTANCE attribute" % (SWITCH, klass.__name__))
        return False
    v = own[SWITCH]
    if not isinstance(v, bool):
        raise BookBeliefSwitchError("%s must be a bool, got %r (%s)" % (SWITCH, v, type(v).__name__))
    return v


def booked_uncached(prefix_tokens: int, p_cached_tokens: int, piece: int) -> Tuple[int, int, bool]:
    """(total booked uncached tokens, extra over the piece, prefix_mostly_uncached).

    booked = prefix x (1 - P cached fraction) + piece, where `p_cached_tokens` is layer P's PRE-SEND
    estimate of the prefix tokens the engine will serve from cache (GPU or host: a host reload is
    not a prefill). No scaling by any earlier fraction, no new constant."""
    p = max(int(piece), 1)
    pre = max(int(prefix_tokens), 0)
    x = max(pre - max(min(int(p_cached_tokens), pre), 0), 0)
    return p + x, x, bool(pre > 0 and x * 2 > pre)
