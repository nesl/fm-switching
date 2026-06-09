"""
SpeculativeLH (Variant A) — per request, BOTH tiers process the request in
parallel. User-facing latency = min(edge, cloud). No cancellation: the loser
pays its full compute. Both KV caches grow identically by construction
(both tiers process identical inputs every turn).

Cost accounting (per user sign-off, Track 1 LH-variants work item):
  C_edge_serve         : edge_compute_ms(quant, ctx, gen)
  C_cloud_serve        : cloud_compute_ms(ctx, gen)        (no RTT)
  C_network_per_request: rtt_ms                            (RTT only;
                         bandwidth_mbps is intentionally unused)
  Memory               : continuous dual-tier (both warm, both KV-current)
  Wasted compute       : loser's compute (both tiers can lose under
                         normal operation; cloud loses whenever
                         edge_time ≤ cloud_time + RTT, edge loses
                         the rest of the time)

Failure mode: if `connected=False`, the cloud branch never returns. User-
facing latency = edge_time. Cloud's compute is still charged (it was queued
before the disconnection was observed); whether it counts as wasted depends
on whether we know about the disconnection in advance — for the conservative
model, we count it as wasted only if edge wins, else cloud wins by default.
"""

from cost_model import (edge_compute_ms, cloud_compute_ms,
                         replica_memory_mb, memory_used_mb)
from orchestrator_sim import STAY
from policies import Policy


class SpeculativeLHPolicy(Policy):
    name = "SpeculativeLH"

    def __init__(self):
        self.reset()

    def reset(self):
        pass

    def decide(self, state):
        # No migration actions; the override hook does all the work.
        return STAY

    def compute_cycle_overrides(self, *, sim_state, state_loc, state_quant,
                                  ctx_tokens, gen_tokens, rtt_ms, connected,
                                  new_tokens_per_turn, mem_edge_mb,
                                  trajectory, cloud_ok, cloud_mean_rtt,
                                  cloud_elapsed_s, **_):
        edge_ms = edge_compute_ms(state_quant, ctx_tokens, gen_tokens)
        cloud_compute_only = cloud_compute_ms(ctx_tokens, gen_tokens)

        # If the within-cycle trajectory has cloud succeeding, race edge vs
        # cloud using the trajectory-averaged RTT. If it fails mid-cycle,
        # edge still completes — Speculative serves edge's response.
        if cloud_ok:
            cloud_ms = cloud_compute_only + cloud_mean_rtt
            llm_ms = min(edge_ms, cloud_ms)
            cloud_failed = False
        else:
            llm_ms = edge_ms
            cloud_failed = True

        # Compute charged to both tiers regardless of who wins: full prefill
        # + decode tokens at both rates. (No cancellation; if cloud failed
        # mid-cycle, the wasted-token count is still one tier's worth because
        # the compute that ran is still charged.)
        cycle_tokens = 2 * (ctx_tokens + gen_tokens)
        cycle_seconds = (edge_ms + cloud_compute_only) / 1000.0
        wasted = ctx_tokens + gen_tokens

        cloud_mem = replica_memory_mb("cloud", ctx_tokens, quant=state_quant)
        total_mem = mem_edge_mb + cloud_mem

        return {
            "llm_latency_ms": llm_ms,
            "compute_tokens": cycle_tokens,
            "compute_seconds": cycle_seconds,
            "memory_total_mb": total_mem,
            "wasted_compute_tokens": wasted,
            "cloud_failed_mid_cycle": cloud_failed,
            "successful_fallback": False,  # Spec doesn't fall back — edge ran in parallel
        }
