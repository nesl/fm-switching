"""
SSM+MPC: replaces ProactiveMPC's network/context lookahead with predictions
from a learned temporal encoder + prediction head.

Mirrors ProactiveMPC.evaluate logic so the only difference vs the baseline
MPC is the source of future RTT/context/memory estimates.
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from cost_model import (FP16, INT4, CLOUD,
                        QUALITY, EFFECTIVE_TOKENS, TOKENS_PER_CYCLE_FULL,
                        llm_latency_ms, migration_cost_s, memory_used_mb)
from orchestrator_sim import (
    STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE,
    SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT, SET_STATELESS,
)
from policies import Policy
from ssm_encoder import (TemporalEncoder, state_to_features, pad_window,
                          TELEMETRY_DIM, WINDOW_SIZE, LATENT_DIM, HIDDEN_DIM)


PREDICT_DIM = 3   # rtt, context_norm, mem_util
HORIZON = 10


class SSMPredictor(nn.Module):
    """Encoder + small MLP that predicts (rtt, context, mem_util) for next H cycles."""
    def __init__(self, input_dim=TELEMETRY_DIM, hidden_dim=HIDDEN_DIM,
                 latent_dim=LATENT_DIM, predict_dim=PREDICT_DIM, horizon=HORIZON):
        super().__init__()
        self.encoder = TemporalEncoder(input_dim, hidden_dim, latent_dim)
        self.predictor = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, predict_dim * horizon),
        )
        self.horizon = horizon
        self.predict_dim = predict_dim

    def forward(self, window):
        latent = self.encoder(window)
        flat = self.predictor(latent)
        return flat.view(-1, self.horizon, self.predict_dim)


class SSMMPCPolicy(Policy):
    """ProactiveMPC with SSM-predicted future telemetry instead of trace lookahead."""
    name = "SSM+MPC"
    QUALITY_WEIGHT_S = 5.0

    def __init__(self, model_path):
        self.predictor = SSMPredictor()
        self.predictor.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.predictor.eval()
        self.history = []

    def reset(self):
        self.history = []

    def _llm_s(self, loc, quant, ctx, rtt_ms):
        return llm_latency_ms(quant, loc, ctx, gen_tokens=10,
                               network_rtt_ms=rtt_ms if loc == "cloud" else 0) / 1000.0

    def _ssm_predict(self, state):
        """Update history, return arrays of predicted [rtt_ms, context_tokens, mem_util]
        for each of the next HORIZON cycles."""
        self.history.append(state_to_features(state))
        if len(self.history) > WINDOW_SIZE:
            self.history = self.history[-WINDOW_SIZE:]
        window = pad_window(self.history)
        with torch.no_grad():
            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
            preds = self.predictor(x).squeeze(0).numpy()    # (H, 3)
        # Denormalize: rtt was rtt/1000 (capped at 1.0 -> 1000 ms)
        rtt = np.clip(preds[:, 0] * 1000.0, 5.0, 5000.0)
        # context_norm was ctx/3000
        ctx_pred = np.clip(preds[:, 1] * 3000.0, 0.0, None)
        # mem_util was mem/cap; we mostly use this just to gate OOM checks
        mem_util = np.clip(preds[:, 2], 0.0, 2.0)
        return rtt, ctx_pred, mem_util

    def _evaluate(self, state, action_seq, future_rtt_ms):
        """Same shape as ProactiveMPC._evaluate but uses SSM RTT instead of trace lookahead."""
        loc = state.llm_location
        quant = state.quantization
        mode = state.context_mode
        accum = state.accumulated_tokens
        cap = state.memory_cap_mb
        cost = 0.0
        # VLM lookahead: SSM doesn't predict it; assume current VLM persists.
        vlm_const = state.current_vlm_latency_s
        for h in range(HORIZON):
            rtt = float(future_rtt_ms[h]) if h < len(future_rtt_ms) else state.network_rtt_ms
            connected = rtt < 1000.0
            a = action_seq[h] if h < len(action_seq) else STAY
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
            cost += vlm_const + self._llm_s(loc, quant, ctx, rtt) + gap \
                    + self.QUALITY_WEIGHT_S * (1.0 - QUALITY[mode])
            accum += TOKENS_PER_CYCLE_FULL
        return cost

    def decide(self, state):
        future_rtt, _, _ = self._ssm_predict(state)
        h0 = [STAY, SET_STATELESS, SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT]
        if state.llm_location == "edge" and state.network_connected:
            h0.append(MIGRATE_TO_CLOUD)
        if state.llm_location == "cloud":
            h0.append(MIGRATE_TO_EDGE)
        best_a, best_c = STAY, float("inf")
        for a in h0:
            seq = [a] + [STAY] * (HORIZON - 1)
            c = self._evaluate(state, seq, future_rtt)
            if c < best_c:
                best_c, best_a = c, a
        return best_a
