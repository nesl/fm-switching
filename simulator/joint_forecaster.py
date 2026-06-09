"""
JointForecaster — adds a P(disconnect within next 1s) head to the existing
GRU-based temporal encoder + horizon-10 RTT/ctx/mem predictor.

Architecture identical to `SSMPredictor` except for the extra head:
  encoder         : nn.GRU(6, 32) → Linear(32, 16)              (TemporalEncoder)
  rtt/ctx/mem head: Linear(16, 32) → ReLU → Linear(32, 3*10)    (matches SSMPredictor)
  disconnect head : Linear(16, 1)  → sigmoid                    (NEW)

Naming note: the codebase calls this stack "SSM" throughout, but the
encoder is actually a 1-layer GRU (see ssm_encoder.py docstring). Keeping
"Joint" in the class name to disambiguate from the existing SSMPredictor.
"""

import torch
import torch.nn as nn

from ssm_encoder import (TemporalEncoder, TELEMETRY_DIM,
                          WINDOW_SIZE, LATENT_DIM, HIDDEN_DIM)


PREDICT_DIM = 3   # rtt, context_norm, mem_util (matches SSMPredictor)
HORIZON = 10


class JointForecaster(nn.Module):
    def __init__(self, input_dim=TELEMETRY_DIM, hidden_dim=HIDDEN_DIM,
                 latent_dim=LATENT_DIM, predict_dim=PREDICT_DIM,
                 horizon=HORIZON):
        super().__init__()
        self.encoder = TemporalEncoder(input_dim, hidden_dim, latent_dim)
        self.regress_head = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, predict_dim * horizon),
        )
        self.disc_head = nn.Linear(latent_dim, 1)
        self.horizon = horizon
        self.predict_dim = predict_dim

    def forward(self, window):
        latent = self.encoder(window)                              # (B, 16)
        rtt_etc = self.regress_head(latent).view(-1, self.horizon,
                                                   self.predict_dim)
        disc_logit = self.disc_head(latent).squeeze(-1)            # (B,)
        return rtt_etc, disc_logit

    def predict_rtt_and_disc(self, window):
        """Returns (rtt_predictions [B,H,3], disc_probs [B])."""
        rtt_etc, disc_logit = self.forward(window)
        return rtt_etc, torch.sigmoid(disc_logit)

    # ── Routing-policy facing helpers ────────────────────────────────
    # These accept a numpy/list 1-window history (already padded) and
    # return a single-cell numeric forecast — convenient for the
    # routing policy which calls them once per cycle.
    def forecast_rtt(self, history_window, horizon_index=0):
        """Predicted RTT (ms) at the requested 1-step-ahead index.
        history_window: list/array shape (WINDOW_SIZE, TELEMETRY_DIM)."""
        import numpy as _np
        x = torch.as_tensor(_np.asarray(history_window),
                             dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            rtt_etc, _ = self.forward(x)
        # Training stored rtt normalized by /1000 (capped at 1.0). Denormalize
        # and clip to the simulator's RTT range.
        rtt_norm = float(rtt_etc[0, horizon_index, 0].item())
        return float(_np.clip(rtt_norm * 1000.0, 5.0, 5000.0))

    def forecast_disconnect_probability(self, history_window, window_s=1.0):
        """P(disconnect within `window_s` seconds). The trained head
        is calibrated for the 1-second window per Step 2 of the work
        item; the `window_s` argument is here for future extension."""
        if abs(window_s - 1.0) > 1e-6:
            # Out-of-spec window requested — caller should know.
            pass
        import numpy as _np
        x = torch.as_tensor(_np.asarray(history_window),
                             dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            _, disc_logit = self.forward(x)
        return float(torch.sigmoid(disc_logit).item())
