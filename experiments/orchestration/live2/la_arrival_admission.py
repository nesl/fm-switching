#!/usr/bin/env python3
"""LOAD-AWARE ARRIVAL ADMISSION for robot and single-shot recalls (arm `covex-v6-fair-final-la`).

DEV BUILD, DEFAULT OFF on every arm. At the b7 arrival gate (`hybrid/hybrid_arm.py`, the
`est <= qs` test) the ISOLATED estimate `costs.recall_ttft_s(readiness_tokens, readiness)` is
replaced by the committed D162 first-token model with its queue term:

    first_token_s(u, queued_uncached_ahead) = d162_price.first_token_s(...)

COEFFICIENTS ARE IMPORTED from `d162_price` (`DP.first_token_s`), never written here. The queue
argument is a TOKEN COUNT priced at per_queue_token SECONDS PER TOKEN inside `DP.first_token_s`;
no `overlap_ft` count (the 247.5x trap in d249_queue_visibility.py) is touched.

  u with layer P on: tokens - P's pre-send cached tokens (roster `pb_cached_by_session`); otherwise
  u (uncached implied by the BELIEF tier, the same three lines as `coordinator._submit_recall`
  and `arms_v6cfr3._rd_u`):   COLD -> readiness_tokens;  else max(tokens - max(built, telemetry), 0)
  queued ahead:               sum of `obs.cloud.in_flight_work[].uncached_tokens`, i.e. W (submit to
                              first token), the register the D162 fit used and the release re-check
                              reads (`self._w.total()`).

The comparator is unchanged: est <= slack -> CLOUD; within the defer window -> DEFER; else REJECT.
The in-flight rows are published by `coordinator.__init__` when this switch is on (data only).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import d162_price as DP

LA_SWITCH = "live2_la_arrival_admission"


class LASwitchError(RuntimeError):
    """The switch was a truthy CLASS attribute or a non-bool."""


def arm_enables(arm: Any) -> bool:
    """Is load-aware arrival admission on for THIS INSTANCE? Default False; instance dict only.
    READ SITES: `hybrid/hybrid_arm.py` (the arrival gate) and `coordinator.__init__` (publication)."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if LA_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(LA_SWITCH, False)):
                raise LASwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "it requires an arm-scoped INSTANCE attribute" % (LA_SWITCH, klass.__name__))
    v = own.get(LA_SWITCH, False)
    if not isinstance(v, bool):
        raise LASwitchError("%s must be a bool, got %r" % (LA_SWITCH, type(v).__name__))
    return v


def uncached_for(q: Any, roster: Dict[str, Any]) -> Tuple[int, str]:
    tokens = max(int(q.readiness_tokens), 1)
    pb = ((roster or {}).get("pb_cached_by_session") or {}).get(str(q.session_id))
    if pb is not None:
        # layer P: u = prompt tokens x (1 - P cached fraction), PRE-SEND, for the whole history
        return max(tokens - min(int(pb.get("cached", 0)), tokens), 0), "pb"
    if str(q.readiness) == "COLD":
        return tokens, "cold"
    inp = ((roster or {}).get("uncached_inputs_by_session") or {}).get(str(q.session_id))
    if inp is None:
        built = int((((roster or {}).get("built_tokens_by_session")) or {}).get(q.session_id, 0) or 0)
        return max(tokens - built, 0), "fallback_built_only"
    held = max(int(inp.get("built_tokens", 0) or 0), int(inp.get("telemetry_cached_tokens", 0) or 0))
    return max(tokens - held, 0), "warm"


def queued_ahead(obs: Any) -> int:
    rows = getattr(getattr(obs, "cloud", None), "in_flight_work", ()) or ()
    return int(sum(int(r.uncached_tokens) for r in rows))


def outcome(est: float, qs: float, defer_s: float) -> str:
    if est <= qs:
        return "CLOUD"
    if est <= qs + defer_s:
        return "DEFER"
    return "REJECT"


def loadaware_est(u: int, queued: int) -> float:
    return float(DP.first_token_s(int(u), int(queued)))
