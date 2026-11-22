#!/usr/bin/env python3
"""FROZEN capacity and floors for D179 share-based admission. One source, imported, never retyped.

D179 (2), D180, D181 and the user's addendum 5 of 2026-11-22. Every number here is DERIVED from
committed covex-v6-base cells (committed name hybrid-F-lhreq-noc3, seeds 4 to 7) in HEALTHY-regime
windows (D162 window rule: a 100 s window is healthy iff its observed first-token p50 <= 2.781 s;
all 12 windows are healthy in all four cells, so 4,800 healthy seconds pooled). Nothing is tuned.

CAPACITY. W_max is the queue-ahead at which a typical alert request still gets its first token by
0.8 s under the committed D162 fit:

    W_max = (0.8 - b0 - b1 * u_alert) / b2
          = (0.8 - 0.06779759 - 0.0001824313 * 374.0) / 0.0001535807 = 4323.3 uncached tokens

u_alert = 374.0 is the MEASURED median uncached tokens of an alert (EP-G dashcam) request, and it
is 374 in each of the four base cells separately, not only pooled, so it is not an artefact of
mixing seeds (n = 39,949 pooled).

FLOORS, by Little's law: floor_t = lambda_t * median uncached_t * median first-token_t, which is
the mean in-flight work a type needs in steady state.

LAMBDA COUNTS DELIVERABLE DEMAND (addendum 5, which corrects an earlier planner claim). An offered
opportunity counts toward lambda unless a FEASIBILITY check declined it; a THROTTLE decline counts,
because the throttle is the mechanism D179 replaces and sizing its replacement from its own
restriction would be circular. Measured, per type:

  alert        47,098 offered, 39,949 sent, 7,149 not sent, and the feasibility share of those is
               ZERO, confirmed two ways. CODE: the dashcam loop in hybrid/hybrid_arm.py computes
               `slack` at line 351 and then appends the item UNCONDITIONALLY at line 355; the only
               read of `it["slack"]` is line 443, inside the utility-per-cost ORDERING index, so no
               feasibility gate exists on the alert path, and the D170 32k rule reads
               RecallQuery.readiness_tokens and cannot touch a monitor. DATA: not one decline
               counter (budget_refusal, over_limit, infeasible) appears in any of the four base
               cells, and an absent Counter key is zero. So lambda_alert uses the OFFERED rate.
               0.00 percent feasibility is inside addendum 5's 2 percent bound, so alert freezes.
  recall       485 offered, 179 sent. The 63 percent gap is b7 deadline feasibility declining cold
               histories that cannot make a 3 s deadline, which is D147's explicit consequence and
               a CORRECT decision, not a throttle. So lambda_recall uses the SUBMITTED rate.
  assistance   1,429 offered, 1,428 sent. b7 declines ONE request across four cells, so offered and
               submitted agree to four significant figures and the choice does not matter.

WHAT THE THROTTLE SIDE IS NOT. The arm's own throttle counters (c5_dash_held 45,839 to 50,589 and
c2_throttled_dash 2,670 to 4,348 per cell) count ITEM-PERIODS, not opportunities, because both
loops run once per 100 ms decision period. They therefore cannot be differenced against the 7,149
not-sent OPPORTUNITIES to split C5 from C2, and no such split is claimed here. Addendum 5's check
needs only the feasibility share, which is zero.

STATED LIMITATION (addendum 5 (1)): the median uncached and median first-token factors are measured
on requests the base ACTUALLY SENT. Declined requests may be larger than those sent, so for recall
in particular the factors describe the deliverable population, not the offered one. This biases the
recall floor DOWNWARD if the declined cold histories would have been larger, which they would; the
floor is a reservation for deliverable demand, and a declined request borrows from the flexible
pool if it later becomes feasible.
"""
from __future__ import annotations

from typing import Dict

# ---- the committed D162 first-token fit (imported by d162_price; repeated here only in the
# derivation comment above, never used as a literal below)
W_MAX_TOKENS = 4323.3
U_ALERT_TOKENS = 374.0

# ---- frozen floors, in uncached tokens (addendum 5 (1), after the zero-feasibility check)
FLOORS_TOKENS: Dict[str, float] = {"alert": 1622.1, "recall": 655.8, "assistance": 242.8}
FLEXIBLE_TOKENS = W_MAX_TOKENS - sum(FLOORS_TOKENS.values())      # 1802.6, 0.417 of W_max

# ---- the factors, kept beside the result so a reader never has to re-derive them
FACTORS = {
    "alert": {"lambda_per_s": 9.8121, "lambda_basis": "offered (C5 declines are a throttle)",
              "median_uncached": 374.0, "median_first_token_s": 0.4420,
              "offered": 47098, "sent": 39949, "feasibility_declines": 0},
    "recall": {"lambda_per_s": 0.0373, "lambda_basis": "submitted (b7 declines are feasibility)",
               "median_uncached": 7717.0, "median_first_token_s": 2.2790,
               "offered": 485, "sent": 179, "feasibility_declines": 306},
    "assistance": {"lambda_per_s": 0.2975, "lambda_basis": "either; they differ by one request",
                   "median_uncached": 1372.0, "median_first_token_s": 0.5943,
                   "offered": 1429, "sent": 1428, "feasibility_declines": 1},
}
SOURCE = ("hybrid-F-lhreq-noc3 (covex-v6-base) seeds 4 to 7, _L3_epg_rq30, healthy windows only; "
          "derivation in results/orchestration/live2/frozen_test/d181_share_floors.json")

# D180 (2): no proportional scaling applies, because the floors sum to 58.3 percent of W_max and
# the cap is 75 percent. Kept as an assertion so a future edit cannot silently break the invariant.
assert sum(FLOORS_TOKENS.values()) <= 0.75 * W_MAX_TOKENS + 1e-6, "D180 (2) cap violated"
assert 1500.0 <= FLOORS_TOKENS["alert"] <= 3250.0, "D180 alert floor bound violated"


def floor_of(query_type: str) -> float:
    return float(FLOORS_TOKENS[query_type])


def as_dict() -> Dict[str, object]:
    return {"w_max_tokens": W_MAX_TOKENS, "u_alert_tokens": U_ALERT_TOKENS,
            "floors_tokens": dict(FLOORS_TOKENS), "flexible_tokens": round(FLEXIBLE_TOKENS, 1),
            "floor_fractions": {k: round(v / W_MAX_TOKENS, 4) for k, v in FLOORS_TOKENS.items()},
            "flexible_fraction": round(FLEXIBLE_TOKENS / W_MAX_TOKENS, 4),
            "factors": FACTORS, "source": SOURCE,
            "scaling_applied": False, "rulings": ["D179 (2), (3)", "D180", "D181",
                                                  "user addendum 5, 2026-11-22"]}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
