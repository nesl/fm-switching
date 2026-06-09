"""
RoutedSyncGRU_v2_LH — RoutedSyncLH variant that routes based on
expected-cost marginalization over the GRU forecaster's two heads:
  (a) 1-step-ahead RTT forecast
  (b) P(disconnect in next 1-second window)

Routing rule (per Step 4 spec; no thresholds):

    cloud_ms_fc   = cloud_compute_ms(ctx, gen) + rtt_fc
    edge_ms_fc    = edge_compute_ms(quant, ctx, gen)
    fallback_ms   = cloud_ms_fc + SWITCHOVER_OVERHEAD_MS + edge_ms_fc
    E[cloud]      = (1 - p_disc) * cloud_ms_fc + p_disc * fallback_ms
    route_cloud   = (E[cloud] < edge_ms_fc)

Everything else (replica sync, memory model, wasted-compute accounting,
within-cycle fallback semantics) is identical to RoutedSyncLH so the
per-cell comparison stays clean.

Naming note: the codebase calls the temporal encoder "SSM" throughout, but
the implementation is a 1-layer GRU (see ssm_encoder.py module docstring).
This v2 policy file starts the rename — class and file say "GRU" explicitly.
The trained checkpoint lives at `trained_joint_forecaster.pt`.
"""

from pathlib import Path

import numpy as np
import torch

from cost_model import (edge_compute_ms, cloud_compute_ms,
                         replica_compute_ms, replica_memory_mb)
from orchestrator_sim import STAY
from policies import Policy
from ssm_encoder import state_to_features, pad_window, WINDOW_SIZE
from joint_forecaster import JointForecaster


SWITCHOVER_OVERHEAD_MS = 1.0


class RoutedSyncGRUv2LHPolicy(Policy):
    name = "RoutedSyncGRU_v2_LH"

    def __init__(self, model_path=None):
        if model_path is None:
            model_path = Path(__file__).parent / "trained_joint_forecaster.pt"
        self.forecaster = JointForecaster()
        self.forecaster.load_state_dict(
            torch.load(model_path, map_location="cpu", weights_only=True))
        self.forecaster.eval()
        self.reset()

    def reset(self):
        self.history = []
        self.n_routed_cloud = 0
        self.n_routed_edge = 0
        self.disc_probs = []   # diagnostic: per-cycle p_disc forecasts

    def decide(self, state):
        return STAY

    def _update_history_and_forecast(self, sim_state):
        self.history.append(state_to_features(sim_state))
        if len(self.history) > WINDOW_SIZE:
            self.history = self.history[-WINDOW_SIZE:]
        win = pad_window(self.history)
        rtt_fc = self.forecaster.forecast_rtt(win, horizon_index=0)
        p_disc = self.forecaster.forecast_disconnect_probability(win, window_s=1.0)
        self.disc_probs.append(p_disc)
        return rtt_fc, p_disc

    def compute_cycle_overrides(self, *, sim_state, state_loc, state_quant,
                                  ctx_tokens, gen_tokens, rtt_ms, connected,
                                  new_tokens_per_turn, mem_edge_mb,
                                  trajectory, cloud_ok, cloud_mean_rtt,
                                  cloud_elapsed_s, **_):
        # ── 1) Expected-cost routing decision via the two GRU heads ──
        rtt_fc, p_disc = self._update_history_and_forecast(sim_state)
        edge_ms_fc = edge_compute_ms(state_quant, ctx_tokens, gen_tokens)
        cloud_compute_only = cloud_compute_ms(ctx_tokens, gen_tokens)
        cloud_ms_fc = cloud_compute_only + rtt_fc
        fallback_ms = cloud_ms_fc + SWITCHOVER_OVERHEAD_MS + edge_ms_fc
        expected_cloud_ms = (1.0 - p_disc) * cloud_ms_fc + p_disc * fallback_ms
        route_cloud = expected_cloud_ms < edge_ms_fc
        if route_cloud:
            self.n_routed_cloud += 1
        else:
            self.n_routed_edge += 1

        # ── 2) Actual outcome uses the within-cycle trajectory ───────
        # Mirrors RoutedSyncLH: warm edge replica saves the cycle on
        # mid-cycle cloud failure.
        cloud_failed = False
        successful_fallback = False
        if route_cloud:
            if cloud_ok:
                llm_ms = cloud_compute_only + cloud_mean_rtt
                served_compute_ms = cloud_compute_only
                replica_ms = replica_compute_ms("edge", new_tokens_per_turn,
                                                  quant=state_quant)
            else:
                cloud_failed = True
                successful_fallback = True
                llm_ms = (cloud_elapsed_s * 1000.0) + edge_ms_fc + SWITCHOVER_OVERHEAD_MS
                served_compute_ms = (cloud_elapsed_s * 1000.0) + edge_ms_fc
                replica_ms = 0.0
        else:
            llm_ms = edge_ms_fc
            served_compute_ms = edge_ms_fc
            replica_ms = replica_compute_ms("cloud", new_tokens_per_turn)

        served_tokens = ctx_tokens + gen_tokens
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
