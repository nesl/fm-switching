"""
RQ3 ablation policies: placement-only, rep-only, joint-inertia, baselines.

  ContinuousCopy        — continuous dual-tier sync (RoutedSyncLHPolicy alias)
  InertiaBlindAdaptive  — CostAwareGreedy, full context locked, linear migration cost
  PlaceOnly             — placement-aware with measured inertia migration cost, no rep change
  RepOnly               — MPC over {stateless, window-3, window-10, summary-80, full}, edge-only
  JointInertia          — MPC over placement × rep, expected-cost migration under disconnect risk

JointInertia cost-model notes (PART A fixes):
  - Migration to cloud: expected cost = (1-p_disc)*success_cost + p_disc*fallback_cost,
    where p_disc is estimated from current RTT via Bayesian soft-classification over
    the Markov state-conditional lognormal RTT distributions in markov_network.py.
  - Migration success cost includes RTT (network transfer of context).
  - Cloud serving cost includes RTT at every horizon step (prevents spurious migration
    when context is small and edge compute is already cheaper than cloud+RTT).
  - connected = rtt < DISCONNECTED_RTT_MS (5000), not 1000.
"""

import math as _math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cost_model import (FP16, QUALITY as _QUALITY_DEFAULT, EFFECTIVE_TOKENS,
                         TOKENS_PER_CYCLE_FULL, SUMMARIZATION_COST_S,
                         llm_latency_ms, migration_cost_s, memory_used_mb,
                         inertia_ms, cloud_compute_ms as _cloud_ms)
from orchestrator_sim import (
    STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE,
    SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT, SET_STATELESS,
    SET_SUMMARY_80, SET_SUMMARY_200,
)
from policies import Policy
from routed_sync_lh_policy import RoutedSyncLHPolicy

# RTT value used by markov_network.py for the disconnected state
_DISCONNECTED_RTT_MS = 5000.0

# ── P(disconnect) estimator ─────────────────────────────────────────────────
# Uses Bayesian soft-classification over Markov (good, degraded) states,
# with lognormal likelihoods from markov_network.py (_lognormal_params).

_GOOD_MU    = _math.log(3.0)
_GOOD_SIGMA = (_math.log(250.0) - _math.log(3.0)) / 2.326   # ≈ 1.901
_DEG_MU     = _math.log(100.0)
_DEG_SIGMA  = (_math.log(1000.0) - _math.log(100.0)) / 2.326  # ≈ 0.990

# P(disconnect in next step | state): mean over campus and urban profiles.
# campus: good→disc=0.005, degraded→disc=0.02
# urban:  good→disc=0.05,  degraded→disc=0.10
_P_DISC_GOOD = 0.028      # (0.005 + 0.05) / 2
_P_DISC_DEG  = 0.060      # (0.02  + 0.10) / 2
_PRIOR_GOOD  = 0.65       # rough average of campus/urban steady-states
_PRIOR_DEG   = 0.35

_SWITCHOVER_S = 0.001     # 1 ms switchover overhead (mirrors GRU-v2 policy)


def _p_disc(rtt_ms: float, connected: bool) -> float:
    """Soft Bayesian P(disconnect in next second) from observed RTT.

    Mirrors the expected-cost marginalization in routed_sync_gru_v2_lh_policy.py,
    but uses the Markov lognormal models in place of the GRU forecast.
    """
    if not connected or rtt_ms >= _DISCONNECTED_RTT_MS:
        return 1.0
    x = max(1.0, rtt_ms)
    def _lpdf(mu, sigma):
        z = (_math.log(x) - mu) / sigma
        return _math.exp(-0.5 * z * z) / (x * sigma)
    lik_g = _lpdf(_GOOD_MU, _GOOD_SIGMA)
    lik_d = _lpdf(_DEG_MU,  _DEG_SIGMA)
    post_g = lik_g * _PRIOR_GOOD
    post_d = lik_d * _PRIOR_DEG
    Z = post_g + post_d + 1e-12
    return (post_g / Z) * _P_DISC_GOOD + (post_d / Z) * _P_DISC_DEG


# ── 1. ContinuousCopy ───────────────────────────────────────────────────────
ContinuousCopy = RoutedSyncLHPolicy


# ── 2. InertiaBlindAdaptive ─────────────────────────────────────────────────
class InertiaBlindAdaptive(Policy):
    """CostAwareGreedy: full context, linear migration cost — blind to measured inertia curves.

    Uses a flat token-linear model for migration cost (the naive estimate before
    profiling).  Contrast with PlaceOnly which uses the measured inertia_ms curves.

    Linear model:
      to_cloud: CLOUD rate × ctx + RTT  (overestimates server cost ~2.7× at deep ctx)
      to_edge:  FP16 rate × ctx         (matches measured edge within 1-15%)
    The server overestimation makes this policy less eager to migrate at deep context
    than PlaceOnly, which sees the cheap measured A6000 re-prefill.
    """
    name = "InertiaBlindAdaptive"
    AMORTIZE = 20

    def _cycle_cost_s(self, loc, quant, ctx, rtt_ms):
        return llm_latency_ms(quant, loc, ctx, gen_tokens=10,
                               network_rtt_ms=rtt_ms if loc == "cloud" else 0) / 1000.0

    def _mig_cost_linear(self, direction, quant, ctx_tokens, rtt_ms):
        """Flat token-linear migration cost — ignores measured inertia curve."""
        if direction == "to_cloud":
            from cost_model import CLOUD
            return (CLOUD["llm_prefill_ms_per_token"] * ctx_tokens + rtt_ms) / 1000.0
        params = FP16 if quant == "fp16" else FP16
        return params["llm_prefill_ms_per_token"] * ctx_tokens / 1000.0

    def decide(self, state):
        ctx = state.context_tokens
        rtt = state.network_rtt_ms
        if not state.network_connected and state.llm_location == "cloud":
            return MIGRATE_TO_EDGE
        stay_cost = self._cycle_cost_s(state.llm_location, state.quantization, ctx, rtt)
        candidates = [(STAY, stay_cost)]
        if state.llm_location != "cloud" and state.network_connected:
            mig = self._mig_cost_linear("to_cloud", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("cloud", state.quantization, ctx, rtt)
            candidates.append((MIGRATE_TO_CLOUD, cyc + mig / self.AMORTIZE))
        if state.llm_location != "edge":
            mig = self._mig_cost_linear("to_edge", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("edge", state.quantization, ctx, rtt)
            candidates.append((MIGRATE_TO_EDGE, cyc + mig / self.AMORTIZE))
        action, _ = min(candidates, key=lambda x: x[1])
        return action


# ── 3. PlaceOnly ────────────────────────────────────────────────────────────
class PlaceOnly(Policy):
    """Placement-aware with measured inertia cost; never changes representation."""
    name = "PlaceOnly"
    AMORTIZE = 20

    def _cycle_cost_s(self, loc, quant, ctx, rtt_ms):
        return llm_latency_ms(quant, loc, ctx, gen_tokens=10,
                               network_rtt_ms=rtt_ms if loc == "cloud" else 0) / 1000.0

    def _mig_cost(self, direction, quant, ctx_tokens, rtt_ms):
        if direction == "to_cloud":
            return inertia_ms("server", ctx_tokens) / 1000.0 + rtt_ms / 1000.0
        return inertia_ms("edge", ctx_tokens) / 1000.0

    def decide(self, state):
        ctx = state.context_tokens
        rtt = state.network_rtt_ms
        if not state.network_connected and state.llm_location == "cloud":
            return MIGRATE_TO_EDGE
        stay_cost = self._cycle_cost_s(state.llm_location, state.quantization, ctx, rtt)
        candidates = [(STAY, stay_cost)]
        if state.llm_location != "cloud" and state.network_connected:
            mig = self._mig_cost("to_cloud", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("cloud", state.quantization, ctx, rtt)
            candidates.append((MIGRATE_TO_CLOUD, cyc + mig / self.AMORTIZE))
        if state.llm_location != "edge":
            mig = self._mig_cost("to_edge", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("edge", state.quantization, ctx, rtt)
            candidates.append((MIGRATE_TO_EDGE, cyc + mig / self.AMORTIZE))
        action, _ = min(candidates, key=lambda x: x[1])
        return action


# ── 4. RepOnly ──────────────────────────────────────────────────────────────
_REP_ACTIONS = [
    STAY, SET_STATELESS, SET_WINDOW_3, SET_WINDOW_10, SET_SUMMARY_80, SET_FULL_CONTEXT,
]
_REP_MODE_MAP = {
    SET_STATELESS:    "stateless",
    SET_WINDOW_3:     "window-3",
    SET_WINDOW_10:    "window-10",
    SET_FULL_CONTEXT: "full",
    SET_SUMMARY_80:   "summary-80",
}


class RepOnly(Policy):
    """MPC over representation space; placement permanently locked to edge."""
    name = "RepOnly"
    HORIZON = 10
    QUALITY_WEIGHT_S = 5.0

    def __init__(self, quality=None):
        self._q = quality if quality is not None else _QUALITY_DEFAULT

    def _llm_s(self, mode, accum):
        ctx = accum if mode == "full" else EFFECTIVE_TOKENS.get(mode, 0)
        return llm_latency_ms("fp16", "edge", ctx, gen_tokens=10, network_rtt_ms=0) / 1000.0

    def _evaluate(self, state, h0_action):
        mode = state.context_mode
        accum = state.accumulated_tokens
        cap = state.memory_cap_mb
        cost = 0.0
        wl = state.workload_lookahead_vlm_s
        for h in range(self.HORIZON):
            vlm = wl[h] if h < len(wl) else state.current_vlm_latency_s
            a = h0_action if h == 0 else STAY
            if a in _REP_MODE_MAP:
                new_mode = _REP_MODE_MAP[a]
                if new_mode != mode:
                    new_ctx = accum if new_mode == "full" else EFFECTIVE_TOKENS.get(new_mode, 0)
                    cost += inertia_ms("edge", new_ctx) / 1000.0
                    if new_mode == "summary-80":
                        cost += SUMMARIZATION_COST_S
                mode = new_mode
            ctx = accum if mode == "full" else EFFECTIVE_TOKENS.get(mode, 0)
            if memory_used_mb("fp16", "edge", ctx) > cap:
                cost += 50.0
            cost += vlm + self._llm_s(mode, accum) + self.QUALITY_WEIGHT_S * (1.0 - self._q.get(mode, 0.3))
            accum += TOKENS_PER_CYCLE_FULL
        return cost

    def decide(self, state):
        if state.llm_location != "edge":
            return MIGRATE_TO_EDGE
        best_action, best_cost = STAY, float("inf")
        for a in _REP_ACTIONS:
            c = self._evaluate(state, a)
            if c < best_cost:
                best_cost, best_action = c, a
        return best_action


# ── 5. JointInertia ─────────────────────────────────────────────────────────
_JOINT_REP_ACTIONS = [
    STAY, SET_STATELESS, SET_WINDOW_3, SET_WINDOW_10, SET_SUMMARY_80, SET_FULL_CONTEXT,
]


class JointInertia(Policy):
    """MPC over placement × representation with expected-cost migration.

    Warm-server / warm-edge model (default):
      - Cloud server is modeled as permanently warm (model resident on A6000).
        Edge→cloud migration cost = inertia_ms("server", ctx) + RTT.
      - Edge LLM stays resident during cloud serving.
        Cloud→edge fallback cost = inertia_ms("edge", ctx) — no 47 s reload.
      - This makes cloud migration viable when the cloud's speed advantage
        (0.154 ms/tok vs 1.37 ms/tok on Jetson) exceeds the disconnect risk
        (p_disc × edge_reprefill_s per step).

    Cloud serving risk: orchestrator checks max(1, ceil(cloud_compute_s))
    seconds of connectivity.  p_fail = 1 - (1 - p_disc)^t_win per step.
    """
    name = "JointInertia"
    HORIZON = 10
    QUALITY_WEIGHT_S = 5.0

    def __init__(self, quality=None):
        self._q = quality if quality is not None else _QUALITY_DEFAULT

    def _cloud_serve_s(self, ctx, rtt_ms):
        return (_cloud_ms(ctx, gen_tokens=10) + rtt_ms) / 1000.0

    def _edge_serve_s(self, quant, ctx):
        return llm_latency_ms(quant, "edge", ctx, gen_tokens=10, network_rtt_ms=0) / 1000.0

    def _migration_gap_s(self, direction, quant, ctx_tokens, rtt_ms):
        """Deterministic migration gap (warm-server / warm-edge model).

        Cloud server is warm (model resident): to_cloud = A6000 re-prefill + RTT.
        Edge model stays resident during cloud serving: to_edge = Jetson re-prefill.
        No weight reloads. Consistent with cost_model.migration_cost_s defaults.
        """
        if direction == "to_cloud":
            return inertia_ms("server", ctx_tokens) / 1000.0 + rtt_ms / 1000.0
        return inertia_ms("edge", ctx_tokens) / 1000.0

    def _evaluate(self, state, h0_action):
        loc = state.llm_location
        quant = state.quantization
        mode = state.context_mode
        accum = state.accumulated_tokens
        cap = state.memory_cap_mb
        cost = 0.0
        wl = state.workload_lookahead_vlm_s
        nt = state.network_lookahead_rtt_ms
        # Estimate disconnect probability once from h=0 state for the whole horizon.
        rtt0 = state.network_rtt_ms
        conn0 = state.network_connected
        p0 = _p_disc(rtt0, conn0)

        for h in range(self.HORIZON):
            vlm = wl[h] if h < len(wl) else state.current_vlm_latency_s
            rtt = nt[h] if h < len(nt) else rtt0
            connected = rtt < _DISCONNECTED_RTT_MS
            a = h0_action if h == 0 else STAY
            gap = 0.0

            if a == MIGRATE_TO_CLOUD and loc == "edge" and connected:
                ctx_tokens = accum if mode == "full" else EFFECTIVE_TOKENS.get(mode, 0)
                gap = self._migration_gap_s("to_cloud", quant, ctx_tokens, rtt)
                loc = "cloud"
            elif a == MIGRATE_TO_EDGE and loc == "cloud":
                ctx_tokens = accum if mode == "full" else EFFECTIVE_TOKENS.get(mode, 0)
                gap = self._migration_gap_s("to_edge", quant, ctx_tokens, rtt)
                loc = "edge"
            elif a in _REP_MODE_MAP:
                new_mode = _REP_MODE_MAP[a]
                if new_mode != mode:
                    new_ctx = accum if new_mode == "full" else EFFECTIVE_TOKENS.get(new_mode, 0)
                    tier = "edge" if loc == "edge" else "server"
                    gap += inertia_ms(tier, new_ctx) / 1000.0
                    if new_mode == "summary-80":
                        gap += SUMMARIZATION_COST_S
                mode = new_mode

            ctx = accum if mode == "full" else EFFECTIVE_TOKENS.get(mode, 0)
            if memory_used_mb(quant, loc, ctx) > cap:
                cost += 50.0

            # Cloud serving: expected cost includes full return-to-edge cost on failure.
            # JointInertia has NO warm edge replica (unlike RoutedSyncLH), so cloud
            # failure forces a 47s warm reload.  Scale p_disc to the actual cloud
            # serving window (t_serve_s) to get per-step failure probability.
            if loc == "cloud":
                cloud_compute_s = _cloud_ms(ctx, gen_tokens=10) / 1000.0
                # Orchestrator checks max(1, ceil(cloud_compute_s)) seconds of
                # connectivity — use that same window to get the correct p_fail.
                t_win = max(1.0, _math.ceil(cloud_compute_s))
                p_per_s = _p_disc(rtt, connected)
                p_fail = 1.0 - (1.0 - p_per_s) ** t_win
                edge_s = self._edge_serve_s(quant, ctx)
                # Warm-edge: on cloud failure, edge model is still resident.
                # Cost = Jetson re-prefill only (no 47s reload).
                mig_back_s = inertia_ms("edge", ctx) / 1000.0
                success_s  = cloud_compute_s + rtt / 1000.0
                fallback_s = cloud_compute_s * 0.5 + edge_s + mig_back_s
                llm_s = (1.0 - p_fail) * success_s + p_fail * fallback_s
            else:
                llm_s = self._edge_serve_s(quant, ctx)

            quality = self._q.get(mode, 0.3)
            cost += vlm + llm_s + gap + self.QUALITY_WEIGHT_S * (1.0 - quality)
            accum += TOKENS_PER_CYCLE_FULL
        return cost

    def decide(self, state):
        h0_options = list(_JOINT_REP_ACTIONS)
        if state.llm_location == "edge" and state.network_connected:
            h0_options.append(MIGRATE_TO_CLOUD)
        if state.llm_location == "cloud":
            h0_options.append(MIGRATE_TO_EDGE)
        best_action, best_cost = STAY, float("inf")
        for a in h0_options:
            c = self._evaluate(state, a)
            if c < best_cost:
                best_cost, best_action = c, a
        return best_action
