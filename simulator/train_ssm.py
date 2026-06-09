"""
Training entry point for the two SSM variants.

Modes:
    --mode predictor   Supervised: collect trajectories with random policy,
                       train SSMPredictor (encoder + MLP head) to forecast
                       future telemetry. MSE loss.
    --mode rl          Joint: train SSMActorCriticNet with PPO end-to-end.
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from cost_model import (FP16, INT4, CLOUD,
                        QUALITY, EFFECTIVE_TOKENS, TOKENS_PER_CYCLE_FULL,
                        llm_latency_ms, migration_cost_s, memory_used_mb)
from orchestrator_sim import network_at, effective_tokens, read_network_csv
from rl_policy import OrchestratorEnv, random_workload, NETWORK_NAMES, NETWORK_DIR
from ssm_encoder import (TemporalEncoder, state_to_features, pad_window,
                          TELEMETRY_DIM, WINDOW_SIZE, LATENT_DIM, HIDDEN_DIM)
from ssm_mpc_policy import SSMPredictor, PREDICT_DIM, HORIZON
from ssm_rl_policy import SSMPPOAgent

ROOT = Path(__file__).parent


def collect_trajectories(num_episodes, max_cycles, seed=42, action_policy="random"):
    """Run episodes with a randomized action policy. Return list of telemetry
    arrays (one per episode), each shape (T, TELEMETRY_DIM)."""
    rng = random.Random(seed)
    networks = {n: read_network_csv(NETWORK_DIR / f"net_{n}.csv") for n in NETWORK_NAMES}
    episodes = []
    for ep in range(num_episodes):
        wl = random_workload(max_cycles, rng)
        net = networks[rng.choice(NETWORK_NAMES)]
        env = OrchestratorEnv(wl, net)
        env.reset()
        traj_features = []
        # Build a SimState-like structure manually each step using env's internal vars
        for t in range(max_cycles):
            # Compose features using env's current observation state
            ctx = effective_tokens(env.mode, env.accumulated)
            mem = memory_used_mb(env.quant, env.location, ctx)
            rtt, connected = network_at(env.network, env.time_s)
            wl_lat = wl[t]["vlm_latency_s"]
            features = [
                min(rtt, 1000.0) / 1000.0,
                1.0 if connected else 0.0,
                min(env.accumulated, 3000.0) / 3000.0,
                min(mem, env.memory_cap_mb) / env.memory_cap_mb,
                min(wl_lat, 20.0) / 20.0,
                min(t, 100) / 100.0,
            ]
            traj_features.append(features)
            # Random action
            if action_policy == "random":
                a = rng.randint(0, len(env.ACTIONS) - 1)
            else:
                a = 0   # STAY-only fallback
            _, _, done, _ = env.step(a)
            if done:
                break
        episodes.append(np.array(traj_features, dtype=np.float32))
    return episodes


def make_pred_dataset(episodes, window=WINDOW_SIZE, horizon=HORIZON):
    """For each episode, slice into (window, target) pairs.
    target = next `horizon` features but only the first 3 dims (rtt, ctx, mem)."""
    X, Y = [], []
    for traj in episodes:
        T = len(traj)
        if T < window + horizon:
            continue
        for t in range(window, T - horizon):
            X.append(traj[t - window: t])
            Y.append(traj[t: t + horizon, :PREDICT_DIM])
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


def train_predictor(num_episodes=1000, max_cycles=100, epochs=50,
                    batch_size=128, lr=1e-3, save_path=None, seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    print(f"Collecting {num_episodes} random-action trajectories...")
    episodes = collect_trajectories(num_episodes, max_cycles, seed=seed)
    X, Y = make_pred_dataset(episodes)
    print(f"  Pairs: X={X.shape}, Y={Y.shape}")
    n = X.shape[0]
    n_train = int(0.9 * n)
    perm = np.random.permutation(n)
    Xtr, Ytr = X[perm[:n_train]], Y[perm[:n_train]]
    Xva, Yva = X[perm[n_train:]], Y[perm[n_train:]]

    model = SSMPredictor()
    opt = optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    log = []

    Xtr_t = torch.as_tensor(Xtr); Ytr_t = torch.as_tensor(Ytr)
    Xva_t = torch.as_tensor(Xva); Yva_t = torch.as_tensor(Yva)

    for ep in range(epochs):
        model.train()
        idx = np.random.permutation(len(Xtr))
        ep_loss = 0.0
        nb = 0
        for s in range(0, len(idx), batch_size):
            mb = idx[s:s + batch_size]
            mb_t = torch.as_tensor(mb, dtype=torch.long)
            preds = model(Xtr_t[mb_t])
            loss = loss_fn(preds, Ytr_t[mb_t])
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss += loss.item()
            nb += 1
        train_loss = ep_loss / max(nb, 1)
        model.eval()
        with torch.no_grad():
            val_preds = model(Xva_t)
            val_loss = loss_fn(val_preds, Yva_t).item()
        log.append({"epoch": ep, "train_loss": train_loss, "val_loss": val_loss})
        if ep % 5 == 0 or ep == epochs - 1:
            print(f"  ep {ep:>3}  train={train_loss:.5f}  val={val_loss:.5f}")
    if save_path:
        torch.save(model.state_dict(), save_path)
        Path(save_path).with_suffix(".log.json").write_text(json.dumps(log, indent=2))
        print(f"  Saved {save_path}")
    return model, log


# ── Joint SSM+RL training ──────────────────────────────────────────────

def train_ssm_rl(num_episodes=2000, max_cycles=100, save_path=None,
                 update_every=4, log_every=100, seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    rng = random.Random(seed)

    networks = {n: read_network_csv(NETWORK_DIR / f"net_{n}.csv") for n in NETWORK_NAMES}
    agent = SSMPPOAgent()
    log_rows = []
    pending = []
    best_eval = -1e9

    def eval_agent(n_eval=5):
        eval_rng = random.Random(7777)
        total = 0.0
        for _ in range(n_eval):
            wl = random_workload(max_cycles, eval_rng)
            net = networks[eval_rng.choice(NETWORK_NAMES)]
            env = OrchestratorEnv(wl, net)
            env.reset()
            history = []
            ep_r = 0.0
            for t in range(max_cycles):
                # Build features from env state
                ctx = effective_tokens(env.mode, env.accumulated)
                mem = memory_used_mb(env.quant, env.location, ctx)
                rtt, conn = network_at(env.network, env.time_s)
                wl_lat = wl[t]["vlm_latency_s"]
                feat = [
                    min(rtt, 1000.0)/1000.0, 1.0 if conn else 0.0,
                    min(env.accumulated, 3000.0)/3000.0,
                    min(mem, env.memory_cap_mb)/env.memory_cap_mb,
                    min(wl_lat, 20.0)/20.0, min(t, 100)/100.0,
                ]
                history.append(feat)
                if len(history) > WINDOW_SIZE:
                    history = history[-WINDOW_SIZE:]
                window = pad_window(history)
                a = agent.select_action(window, deterministic=True)
                _, r, done, _ = env.step(a)
                ep_r += r
                if done:
                    break
            total += ep_r
        return total / n_eval

    for ep in range(num_episodes):
        wl = random_workload(max_cycles, rng)
        net = networks[rng.choice(NETWORK_NAMES)]
        env = OrchestratorEnv(wl, net)
        env.reset()
        history = []
        ep_reward = 0.0
        for t in range(max_cycles):
            ctx = effective_tokens(env.mode, env.accumulated)
            mem = memory_used_mb(env.quant, env.location, ctx)
            rtt, conn = network_at(env.network, env.time_s)
            wl_lat = wl[t]["vlm_latency_s"]
            feat = [
                min(rtt, 1000.0)/1000.0, 1.0 if conn else 0.0,
                min(env.accumulated, 3000.0)/3000.0,
                min(mem, env.memory_cap_mb)/env.memory_cap_mb,
                min(wl_lat, 20.0)/20.0, min(t, 100)/100.0,
            ]
            history.append(feat)
            if len(history) > WINDOW_SIZE:
                history = history[-WINDOW_SIZE:]
            window = pad_window(history)
            a = agent.select_action(window)
            _, r, done, _ = env.step(a)
            pending.append((window, a, r, float(done)))
            ep_reward += r
            if done:
                break

        if (ep + 1) % update_every == 0:
            agent.update(pending)
            pending = []

        if ep % log_every == 0 or ep == num_episodes - 1:
            ev = eval_agent(5)
            log_rows.append({"episode": ep, "train_reward": round(ep_reward, 3),
                             "eval_reward": round(ev, 3)})
            print(f"  ep {ep:>4} train_r={ep_reward:7.2f} eval_r={ev:7.2f}")
            if save_path and ev > best_eval:
                best_eval = ev
                agent.save(save_path)
                Path(save_path).with_suffix(".log.json").write_text(json.dumps(log_rows, indent=2))

    if save_path:
        agent.save(save_path)
        Path(save_path).with_suffix(".log.json").write_text(json.dumps(log_rows, indent=2))
    return agent, log_rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["predictor", "rl"], required=True)
    p.add_argument("--episodes", type=int, default=1000)
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--max-cycles", type=int, default=100)
    p.add_argument("--save", default=None)
    args = p.parse_args()

    if args.mode == "predictor":
        save = args.save or str(ROOT / "trained_ssm_predictor.pt")
        train_predictor(num_episodes=args.episodes, max_cycles=args.max_cycles,
                        epochs=args.epochs, save_path=save)
    elif args.mode == "rl":
        save = args.save or str(ROOT / "trained_ssm_rl.pt")
        train_ssm_rl(num_episodes=args.episodes, max_cycles=args.max_cycles,
                     save_path=save)


if __name__ == "__main__":
    main()
