"""
RoutedSyncSSM_LH — RoutedSyncLH with the routing decision driven by the
trained SSM 1-step-ahead RTT forecast instead of ground-truth instantaneous
network state.

Everything else (replica sync, wasted-compute accounting, memory model) is
identical to RoutedSyncLHPolicy so the per-cell comparison is clean.

Connectivity derivation: the trained SSM predicts RTT directly (no separate
P(disconnected) head). We translate to a connectivity flag using the same
threshold the simulator uses for ground-truth in `orchestrator_sim.py`
(network_at + connected-check chain): rtt > 1000ms → predicted disconnected.
This is the fair-by-construction translation; we do not tune the threshold.
"""

from pathlib import Path

import numpy as np
import torch

from cost_model import (edge_compute_ms, cloud_compute_ms,
                         replica_compute_ms, replica_memory_mb)
from orchestrator_sim import STAY
from policies import Policy
from ssm_encoder import state_to_features, pad_window, WINDOW_SIZE
from ssm_mpc_policy import SSMPredictor


# Fair-by-construction threshold: matches the simulator's own ground-truth
# connectivity check (rtt < 1000 means connected).
CONNECTED_RTT_THRESHOLD_MS = 1000.0


class RoutedSyncSSMLHPolicy(Policy):
    name = "RoutedSyncSSM_LH"

    def __init__(self, model_path=None):
        if model_path is None:
            model_path = Path(__file__).parent / "trained_ssm_predictor.pt"
        self.predictor = SSMPredictor()
        self.predictor.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.predictor.eval()
        self.reset()

    def reset(self):
        self.history = []
        # Forecast-call diagnostics
        self.n_routed_cloud = 0
        self.n_routed_edge = 0
        self.n_forecast_calls = 0

    def decide(self, state):
        return STAY

    def _ssm_predict_next_rtt(self, sim_state):
        """Return the SSM's 1-step-ahead RTT prediction (ms)."""
        self.history.append(state_to_features(sim_state))
        if len(self.history) > WINDOW_SIZE:
            self.history = self.history[-WINDOW_SIZE:]
        window = pad_window(self.history)
        with torch.no_grad():
            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
            preds = self.predictor(x).squeeze(0).numpy()    # (H, 3)
        # rtt was normalised by /1000 during training; denormalise + clip
        rtt_pred = float(np.clip(preds[0, 0] * 1000.0, 5.0, 5000.0))
        self.n_forecast_calls += 1
        return rtt_pred

    def compute_cycle_overrides(self, *, sim_state, state_loc, state_quant,
                                  ctx_tokens, gen_tokens, rtt_ms, connected,
                                  new_tokens_per_turn, mem_edge_mb,
                                  trajectory, cloud_ok, cloud_mean_rtt,
                                  cloud_elapsed_s, **_):
        # 1) Forecast-driven routing decision (the only diff vs RoutedSyncLH)
        rtt_fc = self._ssm_predict_next_rtt(sim_state)
        connected_fc = rtt_fc < CONNECTED_RTT_THRESHOLD_MS
        edge_ms = edge_compute_ms(state_quant, ctx_tokens, gen_tokens)
        cloud_compute_only = cloud_compute_ms(ctx_tokens, gen_tokens)
        cloud_ms_fc = cloud_compute_only + rtt_fc
        route_cloud = connected_fc and (cloud_ms_fc < edge_ms)
        if route_cloud:
            self.n_routed_cloud += 1
        else:
            self.n_routed_edge += 1

        # 2) Actual outcome uses the within-cycle trajectory (cloud_ok).
        #    Mirrors RoutedSyncLH semantics: warm edge replica saves the
        #    cycle on mid-cycle cloud failure.
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
                llm_ms = (cloud_elapsed_s * 1000.0) + edge_ms + 1.0
                served_compute_ms = (cloud_elapsed_s * 1000.0) + edge_ms
                replica_ms = 0.0
        else:
            llm_ms = edge_ms
            served_compute_ms = edge_ms
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
