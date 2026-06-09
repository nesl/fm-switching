"""
LatencyHidingPolicy: when the reactive cloud-migration trigger fires, start
cloud warm-up while edge keeps serving. Switch over only when cloud has
caught up to the session's current depth (buffer-and-replay).

State machine per session:
  edge_only       — normal serving on edge
  warming         — edge serves; cloud is loading + prefilling to depth-at-warm-start
  ready_to_switch — cloud has finished initial prefill; we still need to replay
                    any turns that arrived during warming before switching
  cloud_only      — switch complete

Switchover criterion (buffer-and-replay):
  cloud is "ready" when wallclock ≥ warm_started_at + cloud_warmup_duration(
      depth_at_warm_start). At the next cycle boundary we run a small
  delta-prefill (cloud_prefill_extend_s) for the tokens accumulated since
  warm-start, then emit SWITCH_TO_CLOUD_PREWARMED with that residual as
  the per-switch gap.

Abort condition:
  If network becomes disconnected during `warming` or `ready_to_switch`,
  drop cloud state, return to edge_only, increment abort counter, and
  account for wasted cloud prefill (in tokens).

Memory accounting:
  During overlap (warming + ready_to_switch), both edge and cloud hold
  weights+KV. Edge memory is what the simulator already tracks. We
  estimate cloud memory as the same FP16 LLM weights + KV for the
  prefilled depth, and report peak across both tiers via the
  latency_hiding_metrics dict.

Trigger:
  Mirrors ReactiveThreshold.decide() — edge + memory > 0.85 cap +
  network_connected, with 30s hysteresis since last migration.
"""

from cost_model import (FP16, INT4, CLOUD, EFFECTIVE_TOKENS,
                          memory_used_mb, migration_cost_s,
                          cloud_prefill_extend_s)
from orchestrator_sim import (
    STAY, MIGRATE_TO_EDGE, SWITCH_TO_CLOUD_PREWARMED,
    SET_STATELESS,
)
from policies import Policy


PHASE_EDGE_ONLY       = "edge_only"
PHASE_WARMING         = "warming"
PHASE_READY_TO_SWITCH = "ready_to_switch"
PHASE_CLOUD_ONLY      = "cloud_only"


class LatencyHidingPolicy(Policy):
    name = "LatencyHiding"

    # Trigger thresholds: identical to ReactiveThreshold.
    HYSTERESIS_S = 30.0
    MEM_THRESH = 0.85
    CTX_THRESH = 2000

    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = PHASE_EDGE_ONLY
        self.warm_started_at_s = None
        self.warm_ready_at_s = None       # absolute time when initial prefill finishes
        self.depth_at_warm_start = 0       # tokens
        # Bookkeeping for metrics (reset between episodes)
        self.peak_overlap_mem = 0.0
        self.overlap_total_s = 0.0
        self.n_overlap_windows = 0
        self.n_aborts = 0
        self.wasted_prefill_tokens = 0
        # Communicated back to the simulator on SWITCH_TO_CLOUD_PREWARMED:
        self.pending_prewarmed_gap_s = 0.0

    # ── Public hook surfaced by orchestrator_sim.run_episode ──────────
    def on_cycle_end(self, *, cycle, time_s, cycle_total_s, state_loc,
                     state_quant, accumulated_tokens, ctx_tokens, mem_edge_mb,
                     memory_cap_mb, rtt_ms, connected, **_):
        # Track overlap memory only when we're actually overlapping
        if self.phase in (PHASE_WARMING, PHASE_READY_TO_SWITCH):
            cloud_ctx = self.depth_at_warm_start
            # Cloud "tier" memory: model weights + KV for prefilled depth.
            # Use FP16 LLM weights (cloud uses fp16 by spec) and the same KV
            # per-token coefficient as on edge.
            cloud_mem_est = FP16["llm_weights_mb"] + 0.236 * cloud_ctx
            total_mem = mem_edge_mb + cloud_mem_est
            if total_mem > self.peak_overlap_mem:
                self.peak_overlap_mem = total_mem
            self.overlap_total_s += cycle_total_s

    @property
    def latency_hiding_metrics(self):
        return {
            "peak_memory_mb_overlap": round(self.peak_overlap_mem, 1),
            "overlap_total_s": round(self.overlap_total_s, 2),
            "n_overlap_windows": self.n_overlap_windows,
            "n_aborts": self.n_aborts,
            "wasted_prefill_tokens": self.wasted_prefill_tokens,
        }

    # ── Core decision ─────────────────────────────────────────────────
    def decide(self, state):
        # 1. Abort path — network disconnected during overlap
        if (self.phase in (PHASE_WARMING, PHASE_READY_TO_SWITCH)
                and not state.network_connected):
            self.n_aborts += 1
            self.wasted_prefill_tokens += self.depth_at_warm_start
            self._reset_to_edge_only()
            return STAY

        # 2. Disconnected after switching to cloud → forced fallback
        if self.phase == PHASE_CLOUD_ONLY:
            if not state.network_connected and state.llm_location == "cloud":
                self._reset_to_edge_only()
                return MIGRATE_TO_EDGE
            return STAY

        # 3. State machine
        if self.phase == PHASE_EDGE_ONLY:
            if self._should_start_warming(state):
                self._begin_warming(state)
                return STAY
            # Memory-only fallback to free KV (mirrors ReactiveThreshold)
            if (state.llm_location == "edge"
                    and state.accumulated_tokens > self.CTX_THRESH
                    and state.context_mode == "full"
                    and not state.network_connected):
                return SET_STATELESS
            return STAY

        if self.phase == PHASE_WARMING:
            if state.time_s >= self.warm_ready_at_s:
                self.phase = PHASE_READY_TO_SWITCH
            return STAY

        if self.phase == PHASE_READY_TO_SWITCH:
            # Replay turns accumulated since warm-start before switching
            current_depth = (state.accumulated_tokens
                             if state.context_mode == "full"
                             else EFFECTIVE_TOKENS[state.context_mode])
            replay_gap_s = cloud_prefill_extend_s(
                from_tokens=self.depth_at_warm_start,
                to_tokens=current_depth,
                network_rtt_ms=state.network_rtt_ms,
            )
            # If the delta has grown so much that a "replay" would cost more
            # than another full warm-up, re-arm warming. Threshold: replay
            # > one full extension of equal depth — i.e. the session is
            # growing faster than we can catch up.
            if replay_gap_s > self.warm_ready_at_s - self.warm_started_at_s:
                # Bump the warm target instead of aborting; treat the new depth
                # as the prefill target.
                self.depth_at_warm_start = current_depth
                self.warm_ready_at_s = state.time_s + replay_gap_s
                self.phase = PHASE_WARMING
                return STAY
            # Commit the switch this cycle. Charge the residual gap.
            self.pending_prewarmed_gap_s = replay_gap_s
            self.phase = PHASE_CLOUD_ONLY
            self.n_overlap_windows += 1
            return SWITCH_TO_CLOUD_PREWARMED

        return STAY

    # ── Helpers ───────────────────────────────────────────────────────
    def _should_start_warming(self, state):
        if state.time_since_last_migration_s < self.HYSTERESIS_S:
            return False
        return (state.llm_location == "edge"
                and state.memory_used_mb > self.MEM_THRESH * state.memory_cap_mb
                and state.network_connected)

    def _begin_warming(self, state):
        self.phase = PHASE_WARMING
        self.warm_started_at_s = state.time_s
        depth = (state.accumulated_tokens
                 if state.context_mode == "full"
                 else EFFECTIVE_TOKENS[state.context_mode])
        self.depth_at_warm_start = depth
        # Predicted cloud warm-up duration ≈ the same cost reactive would have
        # paid as a planning gap — i.e. cloud prefill to current depth + RTT.
        warmup_s = migration_cost_s(
            "to_cloud", state.quantization, depth, state.network_rtt_ms,
        )
        self.warm_ready_at_s = state.time_s + warmup_s

    def _reset_to_edge_only(self):
        self.phase = PHASE_EDGE_ONLY
        self.warm_started_at_s = None
        self.warm_ready_at_s = None
        self.depth_at_warm_start = 0
        self.pending_prewarmed_gap_s = 0.0
