#!/usr/bin/env python3
"""ONE PRICE SOURCE for every request a covex-v6 arm issues (user ruling, 2026-11-21).

    first_token_s = 0.067798 + 0.00018243 * predicted_uncached
                             + 0.00015358 * uncached_queued_ahead

read identically by the PLANNER (as the harm a candidate does to others) and by the
COORDINATOR (as the GPU-seconds it charges the budget). Not a tuning change: it is the same
validated D162 model both sides already use to predict delivery, applied to the one quantity they
previously disagreed about.

WHAT IT REPLACES, AND WHY THE OLD CHARGE WAS NOT CONSERVATIVE BUT WRONG-SHAPED.
`costs.recall_gpu_s(tokens, tier)` is StudyRH5 Part A's ISOLATED RELOAD TTFT for a full recall. It
scales with the PREFIX, so a touch on a 21k-token warm history was charged 0.6714 GPU-s for work
the engine measured at 3 uncached tokens. covex-v6-state s4 spent about 620 GPU-s on 1,246 touches
that way, exhausted the shared budget, and refused 12,824 requests: dashcam fell to 1,786 on-time
against the base's 6,167, and the robot gain was bought with them.

THE MEASUREMENT THAT SETTLED IT, and the trap it had to get past. Measured touch TTFT p50 was
0.534 s, which sits INSIDE the 0.24 to 0.67 s charged, so on TTFT alone the charge reads as
correct. It is not: TTFT under load is SERVICE time and a budget spends GPU time. Decomposing the
1,246 measured touches through this very model shows 70 to 98 percent of that TTFT is QUEUEING
BEHIND OTHER REQUESTS, leaving 0.0683 s of GPU-attributable work at every quantile.

THE THIRD TERM IS NOT AN EXTRA; IT IS WHAT MAKES ONE SOURCE POSSIBLE. `uncached_queued_ahead`
carries the displacement a request suffers from work already in front of it. The planner's harm
term and the coordinator's charge are then the SAME arithmetic on the SAME inputs, which is the
property the ruling asks to be proved per request rather than asserted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parents[3]
GATE = REPO / "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"

# The committed D162 first-token model. Declared here so the module works without the file, and
# CHECKED against the file at import, because a silently drifting literal is how two "identical"
# prices stop being identical.
# FULL PRECISION, as the gate file holds them. The ruling quotes 0.0678 / 0.000182 / 0.000154,
# which are the same numbers rounded for reading; rounding them in the code would make the two
# sides of "one price source" differ in the ninth decimal and the drift check below says so. It
# caught exactly that on its first run.
INTERCEPT_S = 0.06779759059832724
PER_UNCACHED_S = 0.0001824312597782467
PER_QUEUE_S = 0.0001535807289338535
SOURCE = "cost_model_gate_d162.json :: model.first_token (gate commit 68a2b47)"
_DRIFT: Optional[Dict[str, Any]] = None


def _check_against_gate() -> Optional[Dict[str, Any]]:
    try:
        m = json.loads(GATE.read_text())["model"]["first_token"]
    except Exception:                                                          # noqa: BLE001
        return None
    pairs = [("intercept", INTERCEPT_S, m["intercept"]),
             ("per_uncached_token", PER_UNCACHED_S, m["per_uncached_token"]),
             ("per_queue_token", PER_QUEUE_S, m["per_queue_token"])]
    bad = [{"name": n, "declared": d, "gate": g} for n, d, g in pairs if abs(d - g) > 5e-9]
    return {"agrees": not bad, "mismatches": bad,
            "gate_values": {n: g for n, _d, g in pairs}}


_DRIFT = _check_against_gate()


class PriceDrift(RuntimeError):
    """The declared coefficients no longer match the committed gate file."""


def assert_no_drift() -> Dict[str, Any]:
    if _DRIFT is None:
        return {"checked": False, "why": "gate file not readable from here"}
    if not _DRIFT["agrees"]:
        raise PriceDrift("d162_price coefficients disagree with %s: %s"
                         % (SOURCE, _DRIFT["mismatches"]))
    return {"checked": True, "agrees": True}


def first_token_s(uncached_tokens: int, queued_uncached_ahead: int = 0) -> float:
    """The predicted first-token time, which is BOTH the price and the harm basis.

    Negative inputs are clamped at 0 rather than allowed to produce a negative price: the NNLS fit
    has no negative branch and a negative charge would refund budget.
    """
    u = max(int(uncached_tokens), 0)
    q = max(int(queued_uncached_ahead), 0)
    return INTERCEPT_S + PER_UNCACHED_S * u + PER_QUEUE_S * q


# WHICH TERMS A BUDGET CHARGE MAY CARRY, and this is the one place the ruling's formula and a GPU
# budget come apart. `first_token_s` has three terms and they are not the same kind of thing:
#
#   intercept + per_uncached * u   WORK THIS REQUEST DOES. Linear in the request, charged once.
#   per_queue * queued_ahead       LATENCY THIS REQUEST SUFFERS because OTHER requests' work is
#                                  in front of it. It is not this request's GPU time.
#
# On the PLANNER side all three belong, because the planner is pricing the delay a candidate
# IMPOSES on others and that is exactly what the third term measures. On the COORDINATOR side the
# third term charges the same GPU-seconds once per request queued behind them: with k requests of
# u tokens in flight the queue charge grows as u^2 k^2 / 2 while the real work grows linearly. A
# dry covex-v6-state cell under the full formula produced 10,612 budget refusals, 10,593 of them
# dashcam, which is the budget binding ARTIFICIALLY in D102's sense.
#
# Both modes are here and the FULL one is the default, because the ruling names the full formula.
# The split is offered, not taken.
CHARGE_MODE = "first-token"      # or "work-only": intercept + per-uncached, no queue term


def price_gpu_s(uncached_tokens: int, queued_uncached_ahead: int = 0) -> float:
    """The coordinator's budget charge. Identical arithmetic to `first_token_s` BY CONSTRUCTION in
    the default mode, so the ruling's "identically in both" holds as written."""
    if CHARGE_MODE == "work-only":
        return first_token_s(uncached_tokens, 0)
    return first_token_s(uncached_tokens, queued_uncached_ahead)


def arm_enables(arm: Any) -> bool:
    """Arm-scoped like every other v5/v6 switch, so no baseline's charge changes."""
    return bool(getattr(arm, "live2_d162_pricing", False))


def as_dict() -> Dict[str, Any]:
    return {"form": ("first_token_s = %.6f + %.8f * uncached + %.8f * queued_uncached_ahead"
                     % (INTERCEPT_S, PER_UNCACHED_S, PER_QUEUE_S)),
            "source": SOURCE, "drift_check": _DRIFT,
            "replaces": ("costs.recall_gpu_s(tokens, tier), StudyRH5 Part A isolated reload TTFT, "
                         "which scales with the PREFIX and so overcharged a warm touch 3.4x at a "
                         "7k prefix rising to 9.5x at 21k"),
            "read_by": ["coordinator budget charge (every request of a covex-v6 arm)",
                        "cf_planner candidate harm, via cf_objective.harm_warm_from_queue_delay"]}


if __name__ == "__main__":
    print(json.dumps(as_dict(), indent=1))
