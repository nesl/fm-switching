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


def should_touch(*, belief: Dict[str, float], prefix_tokens: int,
                 costs: Any, budget_ok: Any = None) -> Dict[str, Any]:
    """The whole decision for one session, as data so a proof can read it."""
    allowed, reason = mixed_touch_guard(belief)
    tier, mass = predicted_tier(belief)
    price = touch_price_gpu_s(prefix_tokens, belief, costs)
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
