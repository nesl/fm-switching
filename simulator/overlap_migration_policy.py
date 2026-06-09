"""
OverlapMigrationPolicy (LH Variant D) — reactive edge→cloud migration whose
switch latency is hidden behind continued edge serving (buffer-and-replay),
recovered to DIRECTION A per the surviving docstring + sprint_2_analysis §5.

Default serving tier is EDGE. As the session runs, edge KV grows. When edge
memory crosses the pressure threshold (>0.85·cap) the policy starts WARMING a
cloud replica in the background while EDGE KEEPS SERVING (it does not migrate to
cloud eagerly). Only once the cloud replica has caught up to the session depth
(buffer-and-replay) does it switch over.

State machine per session (recovered phases):
  edge_only  — normal serving on edge; edge KV grows.
  warming    — edge STILL serves; cloud replica is loading + prefilling to the
               depth at warm-start. Both residencies are held at once.
  cloud_only — switch complete (buffer-and-replay residual paid via the
               orchestrator's SWITCH_TO_CLOUD_PREWARMED action).

The quality drop (centroid q≈0.90 in the deck) is NOT a latency-hiding artifact;
it is the simulator's standard edge-OOM → `stateless` fallback. The key is that
it fires at OM's WARMING EVENT, where edge (serving, full KV) + the warming cloud
replica together exceed the memory cap — a dual-residency footprint that a single
serving tier never reaches. The orchestrator's OOM check consults that footprint
ONLY when this policy signals a warming event (see warming_oom_memory_mb and the
asymmetric check in orchestrator_sim.run_episode). The continuous-sync LH
variants (Speculative/RoutedSync/HotStandby) keep edge as a passive replica (no
edge serving), so they never present this footprint and never OOM here.

Cost-model reuse (no new cost math):
  warm-up duration : cost_model.cloud_prefill_extend_s(0, depth, rtt, gen=0)
  switch residual  : cost_model.cloud_prefill_extend_s(depth, current, rtt, gen=0)
  dual/shadow memory: cost_model.replica_memory_mb("cloud", ...)

Abort: if the link drops while warming, the cloud replica is unreachable and the
warm-up is wasted — abort back to edge_only and count it (n_aborts).
"""

from cost_model import cloud_prefill_extend_s, replica_memory_mb
from orchestrator_sim import STAY, SWITCH_TO_CLOUD_PREWARMED, MIGRATE_TO_EDGE
from policies import Policy


# Edge-memory-pressure warming trigger. Per sprint_2_analysis.py §5:
# "OverlapMigration triggers warming when edge memory >0.85*cap".
MEM_THRESH = 0.85       # fraction of memory_cap_mb that starts a warm-up
HYSTERESIS_S = 30.0     # min seconds between migrations


class OverlapMigrationPolicy(Policy):
    name = "OverlapMigration"

    def __init__(self, mem_thresh=MEM_THRESH, hysteresis_s=HYSTERESIS_S):
        self.mem_thresh = mem_thresh
        self.hysteresis_s = hysteresis_s
        self.reset()

    def reset(self):
        self.phase = "edge_only"            # edge_only | warming | cloud_only
        self.warm_started_at = None
        self.depth_at_warm_start = 0
        self.warm_rtt_ms = 0.0
        self.warmup_duration_s = 0.0
        # Read (and zeroed) by the orchestrator on SWITCH_TO_CLOUD_PREWARMED.
        self.pending_prewarmed_gap_s = 0.0
        # Overlap-window metrics (surfaced via latency_hiding_metrics)
        self.n_overlap_windows = 0
        self.n_aborts = 0
        self.overlap_total_s = 0.0
        self.peak_memory_mb_overlap = 0.0

    # ── trigger ────────────────────────────────────────────────────────
    def _trigger(self, state):
        """Start warming when edge memory crosses the pressure threshold while
        connected (and past the migration hysteresis)."""
        return (state.llm_location == "edge"
                and state.network_connected
                and state.memory_used_mb > self.mem_thresh * state.memory_cap_mb
                and state.time_since_last_migration_s >= self.hysteresis_s)

    def _abort(self):
        self.phase = "edge_only"
        self.n_aborts += 1
        self.warm_started_at = None
        self.depth_at_warm_start = 0
        self.warmup_duration_s = 0.0

    # ── decision ───────────────────────────────────────────────────────
    def decide(self, state):
        # Already switched: reactive fallback to edge if the link drops.
        if self.phase == "cloud_only":
            if not state.network_connected:
                self.phase = "edge_only"
                return MIGRATE_TO_EDGE
            return STAY

        # Normalize: if somehow on cloud, treat as cloud_only.
        if state.llm_location == "cloud":
            self.phase = "cloud_only"
            return STAY

        # Edge serving, not yet warming → maybe start a warm-up under pressure.
        if self.phase == "edge_only":
            if self._trigger(state):
                self.phase = "warming"
                self.warm_started_at = state.time_s
                self.depth_at_warm_start = state.accumulated_tokens
                self.warm_rtt_ms = state.network_rtt_ms
                self.warmup_duration_s = cloud_prefill_extend_s(
                    0, self.depth_at_warm_start, self.warm_rtt_ms, gen_tokens=0)
                self.n_overlap_windows += 1
            return STAY  # edge keeps serving (no eager migration to cloud)

        # phase == "warming": edge is STILL serving while cloud catches up.
        if not state.network_connected:
            self._abort()            # cloud unreachable → warm-up wasted
            return STAY
        ready = state.time_s >= self.warm_started_at + self.warmup_duration_s
        if ready:
            # Buffer-and-replay: replay the delta accrued during warming + 1 RTT.
            self.pending_prewarmed_gap_s = cloud_prefill_extend_s(
                self.depth_at_warm_start, state.accumulated_tokens,
                state.network_rtt_ms, gen_tokens=0)
            self.phase = "cloud_only"
            return SWITCH_TO_CLOUD_PREWARMED
        return STAY  # still warming; edge serves through the overlap

    # ── orchestrator side-hooks ────────────────────────────────────────
    def warming_oom_memory_mb(self, *, state_loc, state_quant, ctx_tokens,
                              accumulated_tokens, base_mem_mb):
        """Dual-residency footprint consulted by the orchestrator's OOM check
        AT THE WARMING EVENT ONLY. While warming, edge is still serving (full
        KV → base_mem_mb) AND a cloud replica is resident; their sum can exceed
        the memory cap even though neither tier alone does. Returns None outside
        the warming phase so the OOM check stays single-tier everywhere else."""
        if self.phase != "warming":
            return None
        cloud_replica = replica_memory_mb("cloud", ctx_tokens, quant=state_quant)
        return base_mem_mb + cloud_replica

    def shadow_memory_mb(self, *, state_loc, state_quant, ctx_tokens,
                         accumulated_tokens):
        """Extra (cloud-replica) memory held while warming — for continuous
        peak-memory tracking. Mirrors warming_oom_memory_mb's cloud term."""
        if self.phase == "warming":
            return replica_memory_mb("cloud", ctx_tokens, quant=state_quant)
        return 0.0

    def on_cycle_end(self, *, cycle, time_s, cycle_total_s, state_loc,
                     state_quant, accumulated_tokens, ctx_tokens, mem_edge_mb,
                     memory_cap_mb, rtt_ms, connected):
        """Accumulate overlap-window metrics while the cloud is warming."""
        if self.phase == "warming":
            self.overlap_total_s += cycle_total_s
            cloud_replica = replica_memory_mb("cloud", ctx_tokens,
                                              quant=state_quant)
            self.peak_memory_mb_overlap = max(
                self.peak_memory_mb_overlap, mem_edge_mb + cloud_replica)

    @property
    def latency_hiding_metrics(self):
        return {
            "peak_memory_mb_overlap": self.peak_memory_mb_overlap,
            "overlap_total_s": self.overlap_total_s,
            "n_overlap_windows": self.n_overlap_windows,
            "n_aborts": self.n_aborts,
        }
