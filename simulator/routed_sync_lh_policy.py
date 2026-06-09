"""
RoutedSyncLH (Variant B) — per request, route to the lower-latency tier;
the other tier stays warm and KV-current via redundant-compute sync on
new tokens. Routing is instantaneous (no forecast): compare
edge_compute_ms vs cloud_compute_ms + rtt_ms; tie-break to edge.

Cost accounting:
  Serving tier compute  : edge_compute_ms OR cloud_compute_ms
  Network (cloud serve) : rtt_ms                                (RTT only)
  Replica sync compute  : tier-correct prefill rate × new_tokens
                          (per user sign-off Q4: edge replica pays edge
                          prefill rate; cloud replica pays 0.154 ms/tok)
  Memory                : continuous dual-tier
  No migrations, no wasted compute under normal operation.
"""

from cost_model import (edge_compute_ms, cloud_compute_ms,
                         replica_compute_ms, replica_memory_mb)
from orchestrator_sim import STAY
from policies import Policy


class RoutedSyncLHPolicy(Policy):
    name = "RoutedSyncLH"

    def __init__(self):
        self.reset()

    def reset(self):
        self.routed_to_cloud_count = 0

    def decide(self, state):
        return STAY

    def compute_cycle_overrides(self, *, sim_state, state_loc, state_quant,
                                  ctx_tokens, gen_tokens, rtt_ms, connected,
                                  new_tokens_per_turn, mem_edge_mb,
                                  trajectory, cloud_ok, cloud_mean_rtt,
                                  cloud_elapsed_s, **_):
        edge_ms = edge_compute_ms(state_quant, ctx_tokens, gen_tokens)
        cloud_compute_only = cloud_compute_ms(ctx_tokens, gen_tokens)

        # Routing rule unchanged: decide on START-OF-CYCLE state only.
        cloud_ms_at_decision = cloud_compute_only + rtt_ms
        route_cloud = connected and (cloud_ms_at_decision < edge_ms)
        cloud_failed = False
        successful_fallback = False
        if route_cloud:
            self.routed_to_cloud_count += 1
            if cloud_ok:
                # Cloud completed successfully across the trajectory window
                llm_ms = cloud_compute_only + cloud_mean_rtt
                served_compute_ms = cloud_compute_only
                replica_ms = replica_compute_ms("edge", new_tokens_per_turn,
                                                  quant=state_quant)
            else:
                # Mid-cycle cloud failure → warm edge replica saves the cycle.
                # Cost = elapsed cloud time + edge_serve + 1ms switchover.
                cloud_failed = True
                successful_fallback = True
                llm_ms = (cloud_elapsed_s * 1000.0) + edge_ms + 1.0
                served_compute_ms = (cloud_elapsed_s * 1000.0) + edge_ms
                replica_ms = 0.0  # replica is now serving; no separate sync
        else:
            llm_ms = edge_ms
            served_compute_ms = edge_ms
            replica_ms = replica_compute_ms("cloud", new_tokens_per_turn)

        served_tokens = (ctx_tokens + gen_tokens)
        cycle_tokens = served_tokens + max(0, new_tokens_per_turn)
        cycle_seconds = (served_compute_ms + replica_ms) / 1000.0

        cloud_mem = replica_memory_mb("cloud", ctx_tokens, quant=state_quant)
        total_mem = mem_edge_mb + cloud_mem

        return {
            "llm_latency_ms": llm_ms,
            "compute_tokens": cycle_tokens,
            "compute_seconds": cycle_seconds,
            "memory_total_mb": total_mem,
            "wasted_compute_tokens": 0,
            "cloud_failed_mid_cycle": cloud_failed,
            "successful_fallback": successful_fallback,
        }
