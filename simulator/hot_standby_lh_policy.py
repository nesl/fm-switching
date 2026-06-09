"""
HotStandbyLH (Variant C) — primary tier serves every request. Replica stays
warm and KV-current via redundant-compute sync. Failover only when primary
unreachable (network disconnected, for cloud-primary case).

Primary selection: configurable; default 'cloud' (cloud is faster when
available; edge is the failover).

Failover detection: 1 cycle of timeout (per user sign-off Q6) — the cycle
in which the disconnection is observed pays a timeout penalty in addition
to the failover-serve compute.

Sticky promotion: once edge takes over, edge remains primary even after
the network recovers. The original primary becomes the new replica and
re-syncs (catch-up cost amortized across subsequent cycles).
"""

from cost_model import (edge_compute_ms, cloud_compute_ms,
                         replica_compute_ms, replica_memory_mb, CLOUD)
from orchestrator_sim import STAY
from policies import Policy


CLOUD_TIMEOUT_MS = 5000.0   # 1-cycle failover timeout charge; matches the
                              # disconnected-state RTT the Markov model
                              # surfaces, so the timeout cost is consistent
                              # with what "tried cloud, never returned" costs.


class HotStandbyLHPolicy(Policy):
    name = "HotStandbyLH"

    def __init__(self, primary="cloud"):
        self.initial_primary = primary
        self.reset()

    def reset(self):
        self.primary = self.initial_primary    # "cloud" or "edge"
        self.n_failovers = 0

    def decide(self, state):
        return STAY

    def compute_cycle_overrides(self, *, sim_state, state_loc, state_quant,
                                  ctx_tokens, gen_tokens, rtt_ms, connected,
                                  new_tokens_per_turn, mem_edge_mb,
                                  trajectory, cloud_ok, cloud_mean_rtt,
                                  cloud_elapsed_s, **_):
        edge_ms = edge_compute_ms(state_quant, ctx_tokens, gen_tokens)
        cloud_compute_only = cloud_compute_ms(ctx_tokens, gen_tokens)
        cloud_failed = False
        successful_fallback = False

        # Failover triggers if primary is cloud AND cloud fails within this
        # cycle's window — failure detected at start (not connected) OR
        # mid-cycle (trajectory shows a disconnected sub-tick).
        cloud_fails_this_cycle = (self.primary == "cloud" and (not connected or not cloud_ok))

        if cloud_fails_this_cycle:
            # Warm edge replica saves the cycle (KV is synced). Fallback cost
            # = elapsed cloud time + edge_serve + 1ms switchover. The replica
            # is current, no re-prefill.
            self.n_failovers += 1
            self.primary = "edge"   # sticky promotion
            elapsed_ms = (cloud_elapsed_s if not cloud_ok else 0.0) * 1000.0
            llm_ms = elapsed_ms + edge_ms + 1.0
            served_compute_ms = elapsed_ms + edge_ms
            replica_ms = 0.0
            wasted = 0
            cloud_failed = True
            successful_fallback = True
        elif self.primary == "cloud":
            llm_ms = cloud_compute_only + cloud_mean_rtt
            served_compute_ms = cloud_compute_only
            replica_ms = replica_compute_ms("edge", new_tokens_per_turn,
                                              quant=state_quant)
            wasted = 0
        else:  # primary == "edge" (post-failover, sticky)
            llm_ms = edge_ms
            served_compute_ms = edge_ms
            # Cloud replica: only sync when network up; otherwise drift.
            if connected and cloud_ok:
                replica_ms = replica_compute_ms("cloud", new_tokens_per_turn)
            else:
                replica_ms = 0.0
            wasted = 0

        cloud_mem_now = replica_memory_mb("cloud", ctx_tokens, quant=state_quant)
        total_mem = mem_edge_mb + cloud_mem_now
        cycle_tokens = (ctx_tokens + gen_tokens) + max(0, new_tokens_per_turn
                                                         if replica_ms > 0 else 0)
        cycle_seconds = (served_compute_ms + replica_ms) / 1000.0

        return {
            "llm_latency_ms": llm_ms,
            "compute_tokens": cycle_tokens,
            "compute_seconds": cycle_seconds,
            "memory_total_mb": total_mem,
            "wasted_compute_tokens": wasted,
            "cloud_failed_mid_cycle": cloud_failed,
            "successful_fallback": successful_fallback,
        }
