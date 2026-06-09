"""
SSM+RL: PPO with SSM latent state as observation.

Joint-trains the encoder + actor/critic. At inference, the policy maintains
a rolling telemetry window and feeds the encoder's latent vector to the actor.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from policies import Policy
from ssm_encoder import (TemporalEncoder, state_to_features, pad_window,
                          TELEMETRY_DIM, WINDOW_SIZE, LATENT_DIM, HIDDEN_DIM)
from rl_policy import OrchestratorEnv


class SSMActorCriticNet(nn.Module):
    """Encoder + actor/critic head. Forward takes a window, returns (logits, value)."""

    def __init__(self, latent_dim=LATENT_DIM, act_dim=5, hidden=64):
        super().__init__()
        self.encoder = TemporalEncoder(TELEMETRY_DIM, HIDDEN_DIM, latent_dim)
        self.body = nn.Sequential(
            nn.Linear(latent_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
        )
        self.actor = nn.Linear(hidden, act_dim)
        self.critic = nn.Linear(hidden, 1)

    def forward(self, window):
        latent = self.encoder(window)
        h = self.body(latent)
        return self.actor(h), self.critic(h).squeeze(-1)


class SSMPPOAgent:
    """PPO over windowed observations. Mirrors PPOAgent in rl_policy.py but
    forward sees (batch, window, telemetry_dim) instead of (batch, obs_dim)."""

    def __init__(self, act_dim=5, hidden=64, lr=3e-4,
                 gamma=0.99, lam=0.95, clip_eps=0.2,
                 epochs_per_update=4, batch_size=64,
                 entropy_coef=0.01, vf_coef=0.5):
        self.net = SSMActorCriticNet(act_dim=act_dim, hidden=hidden)
        self.opt = optim.Adam(self.net.parameters(), lr=lr)
        self.gamma = gamma
        self.lam = lam
        self.clip = clip_eps
        self.epochs = epochs_per_update
        self.batch = batch_size
        self.ent_coef = entropy_coef
        self.vf_coef = vf_coef

    @torch.no_grad()
    def select_action(self, window, deterministic=False):
        x = torch.as_tensor(window, dtype=torch.float32).unsqueeze(0)
        logits, _ = self.net(x)
        if deterministic:
            return int(logits.argmax(-1).item())
        probs = torch.softmax(logits, dim=-1)
        return int(torch.multinomial(probs, 1).item())

    def _eval_logits(self, win_t, act_t):
        logits, val = self.net(win_t)
        log_probs = torch.log_softmax(logits, dim=-1)
        return log_probs.gather(-1, act_t.unsqueeze(-1)).squeeze(-1), val, logits

    def update(self, traj):
        windows = np.array([t[0] for t in traj], dtype=np.float32)  # (N, W, F)
        acts    = np.array([t[1] for t in traj], dtype=np.int64)
        rews    = np.array([t[2] for t in traj], dtype=np.float32)
        dones   = np.array([t[3] for t in traj], dtype=np.float32)

        with torch.no_grad():
            win_t = torch.as_tensor(windows)
            _, vals = self.net(win_t)
            vals_np = vals.cpu().numpy()

        adv = np.zeros_like(rews, dtype=np.float32)
        gae = 0.0
        for t in reversed(range(len(rews))):
            next_v = 0.0 if t == len(rews) - 1 else vals_np[t + 1]
            delta = rews[t] + self.gamma * next_v * (1 - dones[t]) - vals_np[t]
            gae = delta + self.gamma * self.lam * (1 - dones[t]) * gae
            adv[t] = gae
        ret = adv + vals_np
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)

        win_t = torch.as_tensor(windows)
        act_t = torch.as_tensor(acts)
        adv_t = torch.as_tensor(adv)
        ret_t = torch.as_tensor(ret)
        with torch.no_grad():
            old_logp, _, _ = self._eval_logits(win_t, act_t)

        idx = np.arange(len(windows))
        for _ in range(self.epochs):
            np.random.shuffle(idx)
            for s in range(0, len(idx), self.batch):
                mb = idx[s:s + self.batch]
                mb_t = torch.as_tensor(mb, dtype=torch.long)
                logp, val, logits = self._eval_logits(win_t[mb_t], act_t[mb_t])
                ratio = torch.exp(logp - old_logp[mb_t])
                s1 = ratio * adv_t[mb_t]
                s2 = torch.clamp(ratio, 1 - self.clip, 1 + self.clip) * adv_t[mb_t]
                policy_loss = -torch.min(s1, s2).mean()
                value_loss = ((val - ret_t[mb_t]) ** 2).mean()
                probs = torch.softmax(logits, dim=-1)
                entropy = -(probs * torch.log(probs + 1e-9)).sum(-1).mean()
                loss = policy_loss + self.vf_coef * value_loss - self.ent_coef * entropy
                self.opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), 0.5)
                self.opt.step()

    def save(self, path):
        torch.save(self.net.state_dict(), path)

    def load(self, path):
        self.net.load_state_dict(torch.load(path, map_location="cpu"))


class SSMRLPolicy(Policy):
    name = "SSM+RL"
    ACTIONS = OrchestratorEnv.ACTIONS  # same 5-action set

    def __init__(self, model_path):
        self.agent = SSMPPOAgent()
        self.agent.load(model_path)
        self.history = []

    def decide(self, state):
        self.history.append(state_to_features(state))
        if len(self.history) > WINDOW_SIZE:
            self.history = self.history[-WINDOW_SIZE:]
        window = pad_window(self.history)
        idx = self.agent.select_action(window, deterministic=True)
        return self.ACTIONS[idx]
