#!/usr/bin/env python3
"""THE SHARED FUTURE HORIZON (one definition, two users): `cf_forfeit` (step 3, counterfactual
admission) and `catchup_value` (group C S2, value-gated catch-up prefill) both price a robot's
FUTURE and the arrivals an added piece of work delays, so the functions live here and are imported
by both. Bodies are BYTE-FOR-BYTE the ones `cf_forfeit.py` defined first (moved, not rewritten):
`cf_forfeit` re-exports them, so its replay and its digests do not move.

NO CONSTANT IS INTRODUCED. The horizon cap is `cf_cost.HORIZON_WARM_CAP_S` (D151 (4)), passed in by
the caller; the gap is the rules arm's own causal EWMA; the on-time curve and the service model are
passed in as callables.

WINDOW (D324 and the D328 addendum): `arrival_window` is the added work's current queue wait plus its
own service time, which is EXACTLY B's `est_loadaware = first_token_s(u, ahead)` (INTERCEPT_S +
PER_UNCACHED_S u + PER_QUEUE_S ahead, d162_price.py:90): the caller splits it into service
(`first_token_s(u, 0)`) and wait (`first_token_s(u, ahead) - service`), so the window is
min(est_loadaware, cap) and the wait is counted ONCE.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

FUTURE_HORIZON_VERSION = "future-horizon-1.0"


def expected_questions(horizon_cap_s: float, gap_ewma_s: Optional[float]) -> Optional[float]:
    """Expected number of questions the session gets inside the committed warm horizon:
    HORIZON_WARM_CAP_S / the rules arm's own causal EWMA gap. No new quantity: both inputs are
    committed or already kept by the arm. WHY NOT ONE QUESTION: the gain of ONE next question is
    p_on(warm) - p_on(cold) <= p_on(warm) < MARGIN_CF_ON_TIME for the 3 s robot deadline on the
    committed on-time curve (measured: 0.50 to 0.58 against a bar of 0.658), so a single-question
    future can never cross the bar by itself and the step would be inert BY CONSTRUCTION. A resident
    prefix serves every question until it is evicted, and the resident set is what promises it
    survives, so the future is the expected count over the horizon.
    """
    if gap_ewma_s is None or float(gap_ewma_s) <= 0.0:
        return None
    return float(horizon_cap_s) / float(gap_ewma_s)


def forfeited_future(*, w_r: float, u_cold: int, u_warm: int, slack_next_s: float,
                     p_on_time: Callable[[float, float], float],
                     engine_s_of: Callable[[int], float],
                     n_expected: float = 1.0) -> Dict[str, Any]:
    """The on-time probability the same robot's NEXT question gains if its state is kept resident.

    cold branch: the rejection builds nothing, so the next question finds `u_cold` uncached tokens.
    warm branch: the prefix is resident, so it finds `u_warm` (0: the same history, the question
    text only). Both branches use the same slack and the same committed curve, so only the
    uncached count differs.
    """
    p_c = float(p_on_time(float(engine_s_of(int(u_cold))), float(slack_next_s)))
    p_w = float(p_on_time(float(engine_s_of(int(u_warm))), float(slack_next_s)))
    gain = float(w_r) * float(n_expected) * max(p_w - p_c, 0.0)
    return {"p_on_cold": p_c, "p_on_warm": p_w, "future_gain": gain, "w_r": float(w_r),
            "n_expected": float(n_expected),
            "u_cold": int(u_cold), "u_warm": int(u_warm), "slack_next_s": float(slack_next_s)}


WINDOW_MODES = ("queue_service", "service")


def arrival_window(*, service_s: float, wait_s: float, cap_s: float, mode: str = "queue_service") -> float:
    """The window over which expected arrivals are priced (D324).

    'queue_service' (default): every question that arrives before the added work CLEARS is delayed
    by it, so the window is the admitted request's current queue wait plus its own service time,
    both components of B's load-aware estimate `first_token_s(u, ahead) = INTERCEPT_S +
    PER_UNCACHED_S u + PER_QUEUE_S ahead` (d162_price.py:90): service = the first two terms, wait =
    the third. 'service' (the D320 reading, kept so it stays reproducible): the service time only.
    Both are capped at the FUTURE horizon `cap_s`; with an empty queue they coincide.
    """
    if mode not in WINDOW_MODES:
        raise ValueError("window mode must be one of %r" % (WINDOW_MODES,))
    w = float(service_s) + (float(wait_s) if mode == "queue_service" else 0.0)
    return max(min(w, float(cap_s)), 0.0)


def arrival_rows(devices: Sequence[Dict[str, Any]], *, ahead_tokens: int, window_s: float,
                 est_of: Callable[[int, int], float]) -> Dict[str, Any]:
    """Harm rows for the questions EXPECTED TO ARRIVE inside `window_s`, one row per other device.

    `devices` rows: device_id, qtype ('recall' or 'assistance'; dashcam stays with C5), gap_s (the
    rules arm's own causal EWMA gap, the SAME per-device rate FUTURE uses), u_tokens (the uncached
    tokens that device's last question finds now), slack_s (that question's own deadline duration).
    `est_of(u, queued_ahead)` is B's own load-aware first-token estimator (la_arrival_admission
    `loadaware_est`, the D162 model). Each row is priced at the arrival's first token UNDER THE
    CURRENT QUEUE; the admission then adds the committed D162 queued-ahead delay to it inside
    `cf_objective.harm_warm_from_queue_delay` (same cap, same on-time function as the pending harm).
    `n_expected` = window_s / gap_s is the expected number of arrivals of that device in the window
    and is the row's multiplier; a device without a gap estimate has no rate and no row.
    """
    rows: List[Dict[str, Any]] = []
    n_by_dev: Dict[str, float] = {}
    for d in devices:
        gap = d.get("gap_s")
        if gap is None or float(gap) <= 0.0 or float(window_s) <= 0.0:
            continue
        did = str(d["device_id"])
        n = float(window_s) / float(gap)
        rows.append({"req_id": "arr:" + did, "device_id": did, "qtype": str(d["qtype"]),
                     "engine_s": float(est_of(int(d["u_tokens"]), int(ahead_tokens))),
                     "slack_s": float(d["slack_s"]), "p_device_on_time": 1.0})
        n_by_dev[did] = n
    return {"rows": rows, "n_by_dev": n_by_dev, "n_expected_total": float(sum(n_by_dev.values())),
            "window_s": float(window_s)}
