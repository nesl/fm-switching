"""
Temporal encoder (GRU-based stand-in for Mamba/S4).

Takes a window of recent telemetry [batch, window, 6] -> latent state [batch, latent_dim].
"""

import torch
import torch.nn as nn


TELEMETRY_DIM = 6   # rtt, connected, context, mem_util, vlm_lat, cycle_norm
WINDOW_SIZE = 10
LATENT_DIM = 16
HIDDEN_DIM = 32


class TemporalEncoder(nn.Module):
    def __init__(self, input_dim=TELEMETRY_DIM, hidden_dim=HIDDEN_DIM,
                 latent_dim=LATENT_DIM):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, batch_first=True)
        self.projection = nn.Linear(hidden_dim, latent_dim)

    def forward(self, window):
        # window: (batch, T, input_dim)
        _, h_n = self.gru(window)            # h_n: (1, batch, hidden_dim)
        return self.projection(h_n.squeeze(0))   # (batch, latent_dim)


def state_to_features(state):
    """SimState -> 6-dim feature vector (matches user spec)."""
    return [
        min(state.network_rtt_ms, 1000.0) / 1000.0,
        1.0 if state.network_connected else 0.0,
        min(state.accumulated_tokens, 3000.0) / 3000.0,
        min(state.memory_used_mb, state.memory_cap_mb) / max(state.memory_cap_mb, 1.0),
        min(state.current_vlm_latency_s, 20.0) / 20.0,
        min(state.cycle, 100) / 100.0,
    ]


def pad_window(history, window_size=WINDOW_SIZE):
    """Pad with zeros at the front if history is shorter than window_size."""
    if len(history) >= window_size:
        return history[-window_size:]
    pad = [[0.0] * TELEMETRY_DIM] * (window_size - len(history))
    return pad + history
