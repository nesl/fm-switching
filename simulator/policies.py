"""
Step 4: Baseline + proactive orchestrator policies.

Each policy implements .decide(state) -> action_string.
"""

from copy import deepcopy

from cost_model import (FP16, INT4, CLOUD,
                        QUALITY, EFFECTIVE_TOKENS,
                        llm_latency_ms, migration_cost_s, memory_used_mb,
                        TOKENS_PER_CYCLE_FULL, KV_GROWTH_MB_PER_CYCLE)
from orchestrator_sim import (
    STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE,
    SWITCH_TO_FP16, SWITCH_TO_INT4,
    SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT, SET_STATELESS,
)


class Policy:
    name = "abstract"
    def decide(self, state):
        raise NotImplementedError


# ── 1. AlwaysEdge ──────────────────────────────────────────────────────
class AlwaysEdge(Policy):
    name = "AlwaysEdge"
    def decide(self, state):
        if state.llm_location != "edge":
            return MIGRATE_TO_EDGE
        return STAY


# ── 2. AlwaysCloud ─────────────────────────────────────────────────────
class AlwaysCloud(Policy):
    name = "AlwaysCloud"
    def decide(self, state):
        if state.network_connected and state.llm_location != "cloud":
            return MIGRATE_TO_CLOUD
        if (not state.network_connected) and state.llm_location != "edge":
            return MIGRATE_TO_EDGE
        return STAY


# ── 3. ReactiveThreshold ───────────────────────────────────────────────
class ReactiveThreshold(Policy):
    name = "ReactiveThreshold"
    HYSTERESIS_S = 30.0
    MEM_THRESH = 0.85
    CTX_THRESH = 2000

    def decide(self, state):
        if state.time_since_last_migration_s < self.HYSTERESIS_S:
            return STAY
        # On edge + memory pressure + connected → cloud
        if (state.llm_location == "edge"
                and state.memory_used_mb > self.MEM_THRESH * state.memory_cap_mb
                and state.network_connected):
            return MIGRATE_TO_CLOUD
        # On cloud + disconnected → edge
        if state.llm_location == "cloud" and not state.network_connected:
            return MIGRATE_TO_EDGE
        # Heavy context on edge → strip to stateless
        if (state.llm_location == "edge"
                and state.accumulated_tokens > self.CTX_THRESH
                and state.context_mode == "full"):
            return SET_STATELESS
        return STAY


# ── 4. CostAwareGreedy ─────────────────────────────────────────────────
class CostAwareGreedy(Policy):
    name = "CostAwareGreedy"
    MIGRATION_PENALTY_AMORTIZE_OVER = 20  # cycles to amortize migration cost

    def _cycle_cost_s(self, loc, quant, mode, ctx_tokens, rtt_ms):
        ms = llm_latency_ms(quant, loc, ctx_tokens, gen_tokens=10,
                             network_rtt_ms=rtt_ms if loc == "cloud" else 0)
        return ms / 1000.0

    def decide(self, state):
        ctx = state.context_tokens
        rtt = state.network_rtt_ms

        stay_cost = self._cycle_cost_s(state.llm_location, state.quantization,
                                        state.context_mode, ctx, rtt)
        candidates = [(STAY, stay_cost)]

        # Migrate to cloud
        if state.llm_location != "cloud" and state.network_connected:
            mig = migration_cost_s("to_cloud", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("cloud", state.quantization, state.context_mode,
                                      ctx, rtt)
            penalty = mig / self.MIGRATION_PENALTY_AMORTIZE_OVER
            candidates.append((MIGRATE_TO_CLOUD, cyc + penalty))

        # Migrate to edge
        if state.llm_location != "edge":
            mig = migration_cost_s("to_edge", state.quantization, ctx, rtt)
            cyc = self._cycle_cost_s("edge", state.quantization, state.context_mode,
                                      ctx, rtt)
            penalty = mig / self.MIGRATION_PENALTY_AMORTIZE_OVER
            candidates.append((MIGRATE_TO_EDGE, cyc + penalty))

        # If disconnected, force back to edge
        if not state.network_connected and state.llm_location == "cloud":
            return MIGRATE_TO_EDGE

        action, _ = min(candidates, key=lambda x: x[1])
        return action


# ── 5. ProactiveMPC ────────────────────────────────────────────────────
class ProactiveMPC(Policy):
    name = "ProactiveMPC"
    HORIZON = 10
    QUALITY_WEIGHT_S = 5.0  # cost-equivalent of (1.0 - quality) per cycle

    def _llm_s(self, loc, quant, ctx, rtt_ms):
        return llm_latency_ms(quant, loc, ctx, gen_tokens=10,
                               network_rtt_ms=rtt_ms if loc == "cloud" else 0) / 1000.0

    def _evaluate(self, state, action_seq):
        """Simulate action_seq[0..H-1] forward and return total cost."""
        loc = state.llm_location
        quant = state.quantization
        mode = state.context_mode
        accum = state.accumulated_tokens
        cap = state.memory_cap_mb
        cost = 0.0

        wl = state.workload_lookahead_vlm_s
        nt = state.network_lookahead_rtt_ms

        for h in range(self.HORIZON):
            if h >= len(wl):
                vlm = state.current_vlm_latency_s
            else:
                vlm = wl[h]
            rtt = nt[h] if h < len(nt) else state.network_rtt_ms
            connected = rtt < 1000  # treat anything >1s as disconnected

            a = action_seq[h] if h < len(action_seq) else STAY
            gap = 0.0
            if a == MIGRATE_TO_CLOUD and loc == "edge" and connected:
                ctx_tokens = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
                gap = migration_cost_s("to_cloud", quant, ctx_tokens, rtt)
                loc = "cloud"
            elif a == MIGRATE_TO_EDGE and loc == "cloud":
                ctx_tokens = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
                gap = migration_cost_s("to_edge", quant, ctx_tokens, rtt)
                loc = "edge"
            elif a == SET_STATELESS:
                mode = "stateless"
            elif a == SET_WINDOW_3:
                mode = "window-3"
            elif a == SET_WINDOW_10:
                mode = "window-10"
            elif a == SET_FULL_CONTEXT:
                mode = "full"

            ctx = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
            mem = memory_used_mb(quant, loc, ctx)
            if mem > cap:
                cost += 50.0  # heavy penalty for OOM in horizon

            llm_s = self._llm_s(loc, quant, ctx, rtt)
            quality = QUALITY[mode]
            cost += vlm + llm_s + gap + self.QUALITY_WEIGHT_S * (1.0 - quality)
            accum += TOKENS_PER_CYCLE_FULL
        return cost

    def decide(self, state):
        # Limit search: at most one migration in the horizon, optional mode change.
        # Build candidate first-actions; the rest of the horizon is STAY.
        h0_options = [STAY, SET_STATELESS, SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT]
        if state.llm_location == "edge" and state.network_connected:
            h0_options.append(MIGRATE_TO_CLOUD)
        if state.llm_location == "cloud":
            h0_options.append(MIGRATE_TO_EDGE)

        best_action, best_cost = STAY, float("inf")
        for a in h0_options:
            seq = [a] + [STAY] * (self.HORIZON - 1)
            c = self._evaluate(state, seq)
            if c < best_cost:
                best_cost, best_action = c, a
        return best_action


# ── 6. Oracle (lookahead = full episode) ───────────────────────────────
class Oracle(Policy):
    """Approximated oracle. We don't run full DP over the whole episode (too
    expensive); instead we use a long lookahead (50 cycles) and exhaustive
    search over single migration + mode setting. This is a reasonable upper
    bound for evaluating the gap of online policies."""
    name = "Oracle"
    HORIZON = 50
    QUALITY_WEIGHT_S = 5.0

    def __init__(self, full_workload=None, full_network=None):
        # Optional: full traces for true horizon (used by run_comparison wrapper)
        self.full_wl = full_workload
        self.full_net = full_network

    def _llm_s(self, loc, quant, ctx, rtt_ms):
        return llm_latency_ms(quant, loc, ctx, gen_tokens=10,
                               network_rtt_ms=rtt_ms if loc == "cloud" else 0) / 1000.0

    def _eval_seq(self, state, h0_action, h):
        """Apply h0_action at this cycle, then STAY for the rest. Return cost."""
        loc = state.llm_location
        quant = state.quantization
        mode = state.context_mode
        accum = state.accumulated_tokens
        cap = state.memory_cap_mb
        cost = 0.0
        wl = state.workload_lookahead_vlm_s
        nt = state.network_lookahead_rtt_ms
        actions = [h0_action] + [STAY] * (h - 1)
        for k in range(h):
            a = actions[k]
            vlm = wl[k] if k < len(wl) else state.current_vlm_latency_s
            rtt = nt[k] if k < len(nt) else state.network_rtt_ms
            connected = rtt < 1000
            gap = 0.0
            if a == MIGRATE_TO_CLOUD and loc == "edge" and connected:
                ctx_t = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
                gap = migration_cost_s("to_cloud", quant, ctx_t, rtt)
                loc = "cloud"
            elif a == MIGRATE_TO_EDGE and loc == "cloud":
                ctx_t = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
                gap = migration_cost_s("to_edge", quant, ctx_t, rtt)
                loc = "edge"
            elif a == SET_STATELESS:
                mode = "stateless"
            elif a == SET_WINDOW_3:
                mode = "window-3"
            elif a == SET_WINDOW_10:
                mode = "window-10"
            elif a == SET_FULL_CONTEXT:
                mode = "full"
            ctx = (accum if mode == "full" else EFFECTIVE_TOKENS[mode])
            mem = memory_used_mb(quant, loc, ctx)
            if mem > cap:
                cost += 50.0
            cost += vlm + self._llm_s(loc, quant, ctx, rtt) + gap \
                    + self.QUALITY_WEIGHT_S * (1.0 - QUALITY[mode])
            accum += TOKENS_PER_CYCLE_FULL
        return cost

    def decide(self, state):
        # Same shape as MPC but with longer horizon
        h0 = [STAY, SET_STATELESS, SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT]
        if state.llm_location == "edge" and state.network_connected:
            h0.append(MIGRATE_TO_CLOUD)
        if state.llm_location == "cloud":
            h0.append(MIGRATE_TO_EDGE)
        best_a, best_c = STAY, float("inf")
        for a in h0:
            c = self._eval_seq(state, a, self.HORIZON)
            if c < best_c:
                best_c, best_a = c, a
        return best_a


def all_policies():
    from overlap_migration_policy import OverlapMigrationPolicy
    from speculative_lh_policy import SpeculativeLHPolicy
    from routed_sync_lh_policy import RoutedSyncLHPolicy
    from hot_standby_lh_policy import HotStandbyLHPolicy
    return [AlwaysEdge(), AlwaysCloud(), ReactiveThreshold(),
            CostAwareGreedy(), ProactiveMPC(),
            OverlapMigrationPolicy(),
            SpeculativeLHPolicy(),
            RoutedSyncLHPolicy(),
            HotStandbyLHPolicy(),
            Oracle()]
