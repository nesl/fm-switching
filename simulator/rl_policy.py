"""
PPO-trained orchestrator policy.

Wraps the simulator into a Gym-like environment, trains a tiny PPO agent on
randomized workloads, exposes the trained policy as PPOPolicy for use in
run_comparison.

CLI:
    python rl_policy.py --train --episodes 2000 --save trained_ppo.pt
    python rl_policy.py --eval --load trained_ppo.pt
"""

import argparse
import csv
import json
import random
from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from cost_model import (FP16, INT4, CLOUD,
                        QUALITY, EFFECTIVE_TOKENS, TOKENS_PER_CYCLE_FULL,
                        llm_latency_ms, migration_cost_s, memory_used_mb)
from orchestrator_sim import (
    STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE,
    SET_WINDOW_3, SET_STATELESS,
    network_at, effective_tokens, read_workload_csv, read_network_csv,
)
from policies import Policy

ROOT = Path(__file__).parent
NETWORK_DIR = ROOT / "traces" / "network"
NETWORK_NAMES = ["stable", "degrading", "intermittent", "urban", "realistic"]


# ── Gym-like env ────────────────────────────────────────────────────────

class OrchestratorEnv:
    """Step-by-step environment over the simulator's per-cycle logic.

    Action set (5 discrete):
        0: STAY
        1: MIGRATE_TO_CLOUD
        2: MIGRATE_TO_EDGE
        3: SET_WINDOW_3
        4: SET_STATELESS
    """
    ACTIONS = [STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE, SET_WINDOW_3, SET_STATELESS]
    OBS_DIM = 8
    ACT_DIM = 5

    def __init__(self, workload, network, memory_cap_mb=13_000,
                 start_quant="fp16", start_loc="edge", start_mode="full"):
        self.workload = workload
        self.network = network
        self.memory_cap_mb = memory_cap_mb
        self.start_quant = start_quant
        self.start_loc = start_loc
        self.start_mode = start_mode
        self.reset()

    def reset(self):
        self.cycle = 0
        self.time_s = 0.0
        self.accumulated = 161
        self.last_migration_time = -1e9
        self.location = self.start_loc
        self.quant = self.start_quant
        self.mode = self.start_mode
        return self._obs()

    def _obs(self):
        ctx = effective_tokens(self.mode, self.accumulated)
        mem = memory_used_mb(self.quant, self.location, ctx)
        rtt, connected = network_at(self.network, self.time_s)
        wl_lat = (self.workload[self.cycle]["vlm_latency_s"]
                  if self.cycle < len(self.workload) else 9.2)
        return np.array([
            min(self.accumulated, 3000) / 3000.0,
            min(mem, self.memory_cap_mb) / self.memory_cap_mb,
            min(rtt, 1000) / 1000.0,
            1.0 if connected else 0.0,
            1.0 if self.location == "cloud" else 0.0,
            1.0 if self.quant == "fp16" else 0.0,
            min(self.time_s - self.last_migration_time, 30) / 30.0,
            min(wl_lat, 20) / 20.0,
        ], dtype=np.float32)

    def step(self, action_idx):
        action = self.ACTIONS[int(action_idx)]
        if self.cycle >= len(self.workload):
            return self._obs(), 0.0, True, {}
        wl = self.workload[self.cycle]
        rtt, connected = network_at(self.network, self.time_s)

        ctx = effective_tokens(self.mode, self.accumulated)
        gap = 0.0
        migrated = False
        if action == MIGRATE_TO_CLOUD and self.location == "edge" and connected:
            gap = migration_cost_s("to_cloud", self.quant, ctx, rtt)
            self.location = "cloud"
            self.last_migration_time = self.time_s
            migrated = True
        elif action == MIGRATE_TO_EDGE and self.location == "cloud":
            gap = migration_cost_s("to_edge", self.quant, ctx, rtt, warm_cache=True)
            self.location = "edge"
            self.last_migration_time = self.time_s
            migrated = True
        elif action == SET_WINDOW_3:
            self.mode = "window-3"
        elif action == SET_STATELESS:
            self.mode = "stateless"
        # STAY

        ctx = effective_tokens(self.mode, self.accumulated)
        mem = memory_used_mb(self.quant, self.location, ctx)
        if mem > self.memory_cap_mb:
            # Forced fallback: drop to stateless, big penalty
            self.mode = "stateless"
            ctx = effective_tokens(self.mode, self.accumulated)
            mem = memory_used_mb(self.quant, self.location, ctx)

        llm_ms = llm_latency_ms(self.quant, self.location, ctx, gen_tokens=10,
                                 network_rtt_ms=rtt if self.location == "cloud" else 0)
        cycle_total_s = wl["vlm_latency_s"] + (llm_ms / 1000.0) + gap
        quality = QUALITY[self.mode]

        latency_pen   = -cycle_total_s / 20.0
        gap_pen       = -gap / 10.0
        quality_bonus = quality * 0.5
        mig_pen       = -0.3 if migrated else 0.0
        reward = latency_pen + gap_pen + quality_bonus + mig_pen

        self.time_s += cycle_total_s
        self.accumulated += TOKENS_PER_CYCLE_FULL
        self.cycle += 1
        done = self.cycle >= len(self.workload)

        return self._obs(), reward, done, {
            "cycle_latency": cycle_total_s, "gap": gap,
            "quality": quality, "migrated": migrated,
            "memory_mb": mem, "context_tokens": ctx,
            "config": f"{self.location}_{self.quant}/{self.mode}",
        }


# ── PPO ────────────────────────────────────────────────────────────────

class ActorCritic(nn.Module):
    def __init__(self, obs_dim=8, act_dim=5, hidden=64):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
        )
        self.actor = nn.Linear(hidden, act_dim)
        self.critic = nn.Linear(hidden, 1)

    def forward(self, x):
        h = self.body(x)
        return self.actor(h), self.critic(h).squeeze(-1)


class PPOAgent:
    def __init__(self, obs_dim=8, act_dim=5, hidden=64, lr=3e-4,
                 gamma=0.99, lam=0.95, clip_eps=0.2,
                 epochs_per_update=4, batch_size=64,
                 entropy_coef=0.01, vf_coef=0.5, device="cpu"):
        self.device = torch.device(device)
        self.net = ActorCritic(obs_dim, act_dim, hidden).to(self.device)
        self.opt = optim.Adam(self.net.parameters(), lr=lr)
        self.gamma = gamma
        self.lam = lam
        self.clip = clip_eps
        self.epochs = epochs_per_update
        self.batch = batch_size
        self.ent_coef = entropy_coef
        self.vf_coef = vf_coef

    @torch.no_grad()
    def select_action(self, obs, deterministic=False):
        x = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        logits, _ = self.net(x)
        if deterministic:
            return int(logits.argmax(-1).item())
        probs = torch.softmax(logits, dim=-1)
        return int(torch.multinomial(probs, 1).item())

    def _eval(self, obs_t, act_t):
        logits, val = self.net(obs_t)
        log_probs = torch.log_softmax(logits, dim=-1)
        return log_probs.gather(-1, act_t.unsqueeze(-1)).squeeze(-1), val, logits

    def update(self, traj):
        """traj: list of (obs, act, reward, done) tuples (one episode or
        accumulated batch)."""
        obs = np.array([t[0] for t in traj], dtype=np.float32)
        acts = np.array([t[1] for t in traj], dtype=np.int64)
        rews = np.array([t[2] for t in traj], dtype=np.float32)
        dones = np.array([t[3] for t in traj], dtype=np.float32)

        with torch.no_grad():
            obs_t = torch.as_tensor(obs, device=self.device)
            _, vals = self.net(obs_t)
            vals_np = vals.cpu().numpy()

        # GAE-lambda
        adv = np.zeros_like(rews, dtype=np.float32)
        gae = 0.0
        for t in reversed(range(len(rews))):
            next_v = 0.0 if t == len(rews) - 1 else vals_np[t + 1]
            delta = rews[t] + self.gamma * next_v * (1 - dones[t]) - vals_np[t]
            gae = delta + self.gamma * self.lam * (1 - dones[t]) * gae
            adv[t] = gae
        ret = adv + vals_np
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)

        obs_t = torch.as_tensor(obs, device=self.device)
        act_t = torch.as_tensor(acts, device=self.device)
        adv_t = torch.as_tensor(adv, device=self.device)
        ret_t = torch.as_tensor(ret, device=self.device)

        with torch.no_grad():
            old_logp, _, _ = self._eval(obs_t, act_t)

        idx = np.arange(len(obs))
        for _ in range(self.epochs):
            np.random.shuffle(idx)
            for s in range(0, len(idx), self.batch):
                mb = idx[s:s + self.batch]
                mb_t = torch.as_tensor(mb, device=self.device, dtype=torch.long)
                logp, val, logits = self._eval(obs_t[mb_t], act_t[mb_t])
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
        self.net.load_state_dict(torch.load(path, map_location=self.device))


# ── Training ───────────────────────────────────────────────────────────

def random_workload(n_cycles=100, rng=None):
    if rng is None:
        rng = random.Random()
    return [{"cycle": i, "vlm_latency_s": 7 + rng.random() * 8.0}
            for i in range(n_cycles)]


def load_all_networks():
    return {n: read_network_csv(NETWORK_DIR / f"net_{n}.csv") for n in NETWORK_NAMES}


def evaluate(agent, networks, n_eval=5, n_cycles=100):
    """Average reward over n_eval random rollouts (deterministic)."""
    rng = random.Random(7777)
    total = 0.0
    for _ in range(n_eval):
        wl = random_workload(n_cycles, rng)
        net = networks[rng.choice(NETWORK_NAMES)]
        env = OrchestratorEnv(wl, net)
        obs = env.reset()
        ep_r = 0.0
        for _ in range(n_cycles):
            a = agent.select_action(obs, deterministic=True)
            obs, r, done, _ = env.step(a)
            ep_r += r
            if done:
                break
        total += ep_r
    return total / n_eval


def train_ppo(num_episodes=2000, max_cycles=100, save_path=None,
              update_every=4, log_every=100, seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    rng = random.Random(seed)

    networks = load_all_networks()
    agent = PPOAgent()
    log_rows = []
    pending = []
    best_eval = -1e9

    for ep in range(num_episodes):
        wl = random_workload(max_cycles, rng)
        net = networks[rng.choice(NETWORK_NAMES)]
        env = OrchestratorEnv(wl, net)
        obs = env.reset()
        ep_reward = 0.0
        for _ in range(max_cycles):
            a = agent.select_action(obs)
            next_obs, r, done, _ = env.step(a)
            pending.append((obs, a, r, float(done)))
            obs = next_obs
            ep_reward += r
            if done:
                break

        if (ep + 1) % update_every == 0:
            agent.update(pending)
            pending = []

        if ep % log_every == 0 or ep == num_episodes - 1:
            ev = evaluate(agent, networks, n_eval=5, n_cycles=max_cycles)
            log_rows.append({"episode": ep, "train_reward": round(ep_reward, 3),
                             "eval_reward": round(ev, 3)})
            print(f"  ep {ep:>4} train_r={ep_reward:7.2f} eval_r={ev:7.2f}")
            # Save best
            if save_path and ev > best_eval:
                best_eval = ev
                agent.save(save_path)
                # Also dump training log incrementally
                Path(save_path).with_suffix(".log.json").write_text(json.dumps(log_rows, indent=2))

    if save_path:
        agent.save(save_path)
        Path(save_path).with_suffix(".log.json").write_text(json.dumps(log_rows, indent=2))
    return agent, log_rows


# ── Wrapped policy for use in run_comparison ───────────────────────────

class PPOPolicy(Policy):
    name = "PPO"

    def __init__(self, model_path):
        self.agent = PPOAgent()
        self.agent.load(model_path)

    def decide(self, sim_state):
        obs = np.array([
            min(sim_state.accumulated_tokens, 3000) / 3000.0,
            min(sim_state.memory_used_mb, sim_state.memory_cap_mb) / sim_state.memory_cap_mb,
            min(sim_state.network_rtt_ms, 1000) / 1000.0,
            1.0 if sim_state.network_connected else 0.0,
            1.0 if sim_state.llm_location == "cloud" else 0.0,
            1.0 if sim_state.quantization == "fp16" else 0.0,
            min(sim_state.time_since_last_migration_s, 30) / 30.0,
            min(sim_state.current_vlm_latency_s, 20) / 20.0,
        ], dtype=np.float32)
        idx = self.agent.select_action(obs, deterministic=True)
        return OrchestratorEnv.ACTIONS[idx]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--eval", action="store_true")
    p.add_argument("--episodes", type=int, default=2000)
    p.add_argument("--max-cycles", type=int, default=100)
    p.add_argument("--save", default=str(ROOT / "trained_ppo.pt"))
    p.add_argument("--load", default=None)
    args = p.parse_args()

    if args.train:
        print(f"Training PPO for {args.episodes} episodes...")
        agent, log = train_ppo(num_episodes=args.episodes, max_cycles=args.max_cycles,
                                save_path=args.save)
        print(f"Saved to {args.save}")
    if args.eval:
        path = args.load or args.save
        agent = PPOAgent()
        agent.load(path)
        ev = evaluate(agent, load_all_networks(), n_eval=10, n_cycles=args.max_cycles)
        print(f"Eval reward (det, 10 episodes): {ev:.3f}")


if __name__ == "__main__":
    main()
