"""TOUCH, and state-based pricing for warm and reload (full v5 component 2, D150, M2, M6, D160).

WHAT WAS ALREADY THERE, AND WHY IT IS NOT THIS. `engine_actions.touch()` returns
SessionAction(sid, "KEEP_GPU_WARM"), and `coordinator._enact` turns that into `s.desired_tier =
"gpu"`, which `cstate.enact_placement` reads to sort a keep-warm session last in the COORDINATOR's
eviction order. That is belief steering: it changes what the coordinator expects to be evicted. It
sends nothing to the engine, so it cannot move vLLM's own LRU recency, which is driven by engine
access. Its docstring says as much ("this function's name is the only claim it makes").

Spec v6 section 6 and the measurement behind it mean something else: touch is "a minimal request
reusing a warm prefix", and M2 confirmed that on the 32B. A request is the only actuator (D150):
residency cannot be commanded (D44), so the single way to refresh recency is to USE the prefix.
This module adds that request.

M6'S CONSTRAINT IS A DESIGN CONSTRAINT, NOT A DETAIL. StudyENG1c measured that a touch keeps a
history host-warm only if it is served WHOLLY from GPU or WHOLLY from host; a MIXED touch loses it.
So a touch issued against a history whose prefix straddles the tiers is not merely wasted, it is
HARMFUL: it can destroy the host copy it was meant to protect. `mixed_touch_guard` refuses those,
and StudyRES1's R3 FAIL (host fraction at the capacity boundary is not predictable) is why a
near-boundary belief counts as straddling rather than as host.

PRICING BY PREDICTED CACHE STATE (D160, spec section 6): a touch's cost is what the engine will
actually do, which depends on whether the prefix survived, never on a slice size. The committed
cost curve already takes the cache state (`costs.recall_gpu_s(tokens, readiness)`), so the price
comes from there rather than from a new table invented here.
"""
from typing import Any, Dict, Optional, Tuple

# A touch carries no new frames; it re-presents the built prefix and asks for one token.
TOUCH_MAX_TOKENS = 1

# StudyRES1 R3 FAIL: the host fraction at the capacity boundary is not predictable, so a belief
# this far from certainty is treated as straddling the tiers and is NOT touched.
PURE_TIER_MIN_BELIEF = 0.95

READINESS = {"gpu": "GPU-WARM", "host": "HOST-WARM", "cold": "COLD"}


def predicted_tier(belief: Dict[str, float]) -> Tuple[str, float]:
    """The single most likely tier and its mass. Belief keys are gpu / host / cold."""
    if not belief:
        return "cold", 1.0
    k = max(belief, key=lambda x: float(belief.get(x, 0.0)))
    return k, float(belief.get(k, 0.0))


def mixed_touch_guard(belief: Dict[str, float]) -> Tuple[bool, str]:
    """M6: only a WHOLLY-GPU or WHOLLY-host history may be touched.

    Returns (allowed, reason). A mixed or near-boundary history is refused, because a mixed touch
    loses host-warmth: the action would destroy what it exists to protect.
    """
    tier, mass = predicted_tier(belief)
    if tier == "cold":
        return False, "cold: nothing to refresh, a touch would be a cold rebuild"
    if mass < PURE_TIER_MIN_BELIEF:
        return False, (f"belief {tier}={mass:.3f} below {PURE_TIER_MIN_BELIEF}: treated as "
                       "straddling the tiers (StudyRES1 R3), and a MIXED touch loses host-warmth "
                       "(M6)")
    return True, f"wholly {tier} at belief {mass:.3f}"


def touch_price_gpu_s(prefix_tokens: int, belief: Dict[str, float], costs: Any) -> float:
    """GPU-seconds a touch is expected to cost, from the PREDICTED CACHE STATE (D160).

    Not from a slice size: the same touch costs a warm TTFT if the prefix survived and a full cold
    prefill if it did not, which is the whole point of pricing by state.
    """
    tier, _ = predicted_tier(belief)
    return float(costs.recall_gpu_s(max(int(prefix_tokens), 1), READINESS[tier]))


# ---------------------------------------------------------------------------
# D172 follow-up: the touch price, MEASURED rather than proxied.
#
# `touch_price_gpu_s` above charges `recall_gpu_s(WHOLE PREFIX, tier)`, which is StudyRH5 Part A's
# ISOLATED RELOAD TTFT for a full RECALL. covex-v6-state s4 measured what a touch actually is:
# 1,246 touches, every one a WARM cache hit, prompt_tokens p50 10,001 and UNCACHED p50 3, max 15,
# output 1 token. The engine re-materialises nothing.
#
# THE OBSERVED TTFT DOES NOT SETTLE IT AND LOOKS LIKE IT DOES, which is why this is written down.
# Measured touch TTFT was p50 0.534 s, sitting neatly inside the 0.24 to 0.67 s charged, so on
# TTFT alone the charge reads as correct. It is not: TTFT under load is service time, and the
# budget spends GPU time. Decomposing the measurement through the committed D162 model
# (`first_token = 0.067798 + 0.00018243 * uncached + 0.00015358 * queue_ahead`) separates them:
#
#   observed      GPU-attributable      queue share
#   p10 0.228 s      0.0683 s              70.0 %
#   p50 0.534 s      0.0683 s              87.2 %
#   p90 1.101 s      0.0683 s              93.8 %
#   max 2.978 s      0.0683 s              97.7 %
#
# So 70 to 98 percent of what looked like agreement is QUEUEING BEHIND OTHER REQUESTS, which is
# not GPU time and must not be charged to a GPU budget. Two quantities landing in the same range
# is not agreement; it is consistency check 6's invalid proxy and check 2's plausible-rate trap.
#
# AND THE ERROR HAS THE WRONG SHAPE, not merely the wrong size. The charge SCALES WITH PREFIX
# TOKENS while a warm touch's work does not, so the overcharge grows with exactly the thing that
# should not matter: 3.6x at a 7k prefix, 5.6x at 11k, 8.1x at 17k, 9.8x at 21k. A magnitude error
# could be absorbed as conservatism; a shape error cannot, because it penalises precisely the
# large warm histories a touch exists to protect.
TOUCH_PRICE_D162 = {"intercept_s": 0.067798, "per_uncached_token_s": 0.00018243,
                    "source": ("results/orchestration/live2/frozen_test/cost_model_gate_d162.json"
                               " :: model.first_token (gate commit 68a2b47)")}
# Measured on the s4 cell: uncached per touch p50 3, max 15. The MAX is used, not the median, so
# the corrected price stays an upper bound on the work and cannot flatter the policy.
TOUCH_UNCACHED_TOKENS = 15

# D209 (2) hit 22: the mode is now ASSIGNED EXPLICITLY to the ruled charge, and the ruling it names
# is D174 (1): the budget charges UNCACHED TOKENS ONLY. The intercept is occupancy and not work
# (it adds a flat 0.0678 s per request, tracks nothing the engine does, and takes utilisation past
# 1.0 of wall on both measured cells), and the queue term is delay SUFFERED, which belongs in the
# planner's harm. So the ruled touch price is `per_uncached * 15` and nothing else.
#
# WHY NOT `d162-warm-hit`. That mode was the first correction written and it is STILL WRONG under
# D174 (1), because it carries the intercept: 0.067798 + 0.00018243 * 15 = 0.070534 s, which is
# 25.8x the ruled charge of 0.002736 s. It stays here as the record of the intermediate step and
# is no longer the mode.
#
# THE COEFFICIENT IS IMPORTED, NOT COPIED. `TOUCH_PRICE_D162` above holds the coefficients ROUNDED
# for reading (0.00018243 against the gate's 0.0001824312597782467). The coordinator charges
# `d162_price.price_gpu_s` at full precision, so a touch priced from the rounded literal here and
# charged from the full one there would differ in the ninth decimal - which is exactly the drift
# `d162_price` was given a gate check to catch. `price_for_touch` therefore delegates to that one
# price source rather than re-deriving the number.
TOUCH_PRICE_MODE = "d174-uncached-only"
TOUCH_PRICE_MODES = ("d174-uncached-only", "d162-warm-hit", "reload-proxy")


def _d162_price_module() -> Any:
    """The ONE price source, imported lazily so this module stays importable on its own.

    NOT guarded into a silent fallback. A missing `d162_price` means the ruled charge cannot be
    computed, and substituting the reload proxy for it would be the same silent-wrong-default this
    hit exists to remove, so the ImportError is allowed to travel.
    """
    import d162_price as DP                                                    # noqa: PLC0415
    return DP


def touch_price_gpu_s_d174(prefix_tokens: int, belief: Dict[str, float], costs: Any) -> float:
    """The RULED touch price (D174 (1)): per-uncached work only, from `d162_price`.

    Independent of `prefix_tokens` by construction, which is the shape correction: on a warm hit
    the prefix is not re-materialised, so the price must not scale with it. Falls back to the
    reload proxy for a tier that is NOT GPU-warm, where a touch really would pay for the prefix;
    `mixed_touch_guard` refuses those anyway, so the fallback is the conservative branch and never
    the live one.
    """
    tier, _ = predicted_tier(belief)
    if tier != "gpu":
        return float(costs.recall_gpu_s(max(int(prefix_tokens), 1), READINESS[tier]))
    return float(_d162_price_module().price_gpu_s(TOUCH_UNCACHED_TOKENS, 0, "uncached-only"))


def touch_price_gpu_s_d162(prefix_tokens: int, belief: Dict[str, float], costs: Any) -> float:
    """What a touch costs the GPU on a WARM HIT, from the committed D162 model.

    Independent of `prefix_tokens` by construction, because on a warm hit the prefix is not
    re-materialised and the only work is the handful of uncached tokens plus the request's own
    overhead. Falls back to the reload proxy for a tier that is NOT GPU-warm, where a touch really
    would pay for the prefix; `mixed_touch_guard` refuses those anyway, so the fallback is the
    conservative branch and not the live one.
    """
    tier, _ = predicted_tier(belief)
    if tier != "gpu":
        return float(costs.recall_gpu_s(max(int(prefix_tokens), 1), READINESS[tier]))
    return float(TOUCH_PRICE_D162["intercept_s"]
                 + TOUCH_PRICE_D162["per_uncached_token_s"] * TOUCH_UNCACHED_TOKENS)


def price_for_touch(prefix_tokens: int, belief: Dict[str, float], costs: Any) -> float:
    """The ONE read of the touch price, so the mode cannot be set in two places.

    An unknown mode RAISES. Before D209 (2) this function fell through to the reload proxy for
    every value it did not recognise, which is how `TOUCH_PRICE_MODE` could name a corrected price
    and deliver the uncorrected one.
    """
    if TOUCH_PRICE_MODE not in TOUCH_PRICE_MODES:
        raise ValueError("unknown TOUCH_PRICE_MODE %r; one of %s"
                         % (TOUCH_PRICE_MODE, list(TOUCH_PRICE_MODES)))
    if TOUCH_PRICE_MODE == "d174-uncached-only":
        return touch_price_gpu_s_d174(prefix_tokens, belief, costs)
    if TOUCH_PRICE_MODE == "d162-warm-hit":
        return touch_price_gpu_s_d162(prefix_tokens, belief, costs)
    return touch_price_gpu_s(prefix_tokens, belief, costs)


def should_touch(*, belief: Dict[str, float], prefix_tokens: int,
                 costs: Any, budget_ok: Any = None) -> Dict[str, Any]:
    """The whole decision for one session, as data so a proof can read it."""
    allowed, reason = mixed_touch_guard(belief)
    tier, mass = predicted_tier(belief)
    price = price_for_touch(prefix_tokens, belief, costs)
    ok = bool(allowed) and int(prefix_tokens) > 0
    if allowed and int(prefix_tokens) <= 0:
        reason = "no built prefix to re-present"
    if ok and budget_ok is not None and not budget_ok(price):
        ok, reason = False, f"budget refuses {price:.4f} GPU-s"
    return dict(touch=ok, reason=reason, predicted_tier=tier, belief_mass=mass,
                price_gpu_s=price, prefix_tokens=int(prefix_tokens))


def arm_enables(arm: Any) -> bool:
    """Only an arm that declares the capability issues touch requests (D164's shape)."""
    return bool(getattr(arm, "live2_touch_requests", False))


# ----------------------------------------------------------------- warm and reload, priced by state
def build_price_gpu_s(piece_tokens: int, prefix_tokens: int, belief: Dict[str, float],
                      costs: Any) -> Dict[str, Any]:
    """What a warm piece or a reload will actually cost the GPU, by PREDICTED CACHE STATE (D160).

    The committed charge is `recall_gpu_s(piece, "COLD")`: the new slice, always at cold rates, and
    nothing else. That prices the SLICE SIZE and ignores the larger term. The request also
    RE-PRESENTS the already-built prefix, and what the engine then does depends on whether that
    prefix survived:

      GPU-warm   the prefix is a cache hit and costs nothing to re-present
      host-warm  it is reloaded over the host tier, about 15x cheaper than rebuilding (M3)
      cold       it is re-prefilled in full, which is the dominant term and the one the committed
                 charge silently omits

    So the same action costs very different amounts in the three states, which is exactly why D160
    says to price by predicted state and not by slice size. The NEW tokens are genuinely uncached in
    every state, so they stay at cold rates; only the prefix term moves.

    Returns the parts as well as the total, so a proof can read which term carried the price
    instead of inferring it from a single number.
    """
    piece = max(int(piece_tokens), 0)
    prefix = max(int(prefix_tokens), 0)
    tier, mass = predicted_tier(belief)
    new_cost = float(costs.recall_gpu_s(piece, "COLD")) if piece > 0 else 0.0
    if prefix == 0 or tier == "gpu":
        prefix_cost = 0.0
    else:
        prefix_cost = float(costs.recall_gpu_s(prefix, READINESS[tier]))
    return dict(total_gpu_s=new_cost + prefix_cost, new_tokens_gpu_s=new_cost,
                prefix_gpu_s=prefix_cost, predicted_tier=tier, belief_mass=mass,
                piece_tokens=piece, prefix_tokens=prefix,
                committed_charge_gpu_s=new_cost)


def arm_enables_state_pricing(arm: Any) -> bool:
    """Arm-scoped like the other v5 switches, so every baseline keeps the committed charge."""
    return bool(getattr(arm, "live2_state_priced_costs", False))
