"""
Train the JointForecaster: 1-layer GRU encoder + RTT/ctx/mem head + disc head.

Loss = MSE(rtt_etc, target_rtt_etc) + lambda * BCEWithLogits(disc_logit, label)

Disconnect label per training sample:
  Given a window of features at times [t-W, t-1], the regression head's first
  target is at time t. We define disc_label = 1 iff `connected==0` at time t
  OR time t+1 — i.e. "any disconnect in the next 1 second window starting at
  the first prediction step." This matches the user spec in Step 2 of the
  work item.

  Connectivity is read out of feature index 1, which `state_to_features` sets
  to 1.0 when connected and 0.0 when disconnected.

Sanity at end of training:
  - AUROC of disc_head on held-out split (target > 0.85)
  - MSE of RTT head on held-out split (must not regress materially vs.
    the existing `trained_ssm_predictor.pt`)
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from joint_forecaster import JointForecaster, HORIZON, PREDICT_DIM
from ssm_encoder import WINDOW_SIZE, TELEMETRY_DIM
from ssm_mpc_policy import SSMPredictor
from train_ssm import collect_trajectories

ROOT = Path(__file__).parent


def make_joint_dataset(episodes, window=WINDOW_SIZE, horizon=HORIZON):
    """Return X (windows), Y_rtt (rtt/ctx/mem horizon), Y_disc (scalar 0/1)."""
    X, Y_rtt, Y_disc = [], [], []
    CONNECTED_IDX = 1
    for traj in episodes:
        T = len(traj)
        if T < window + horizon + 1:
            continue
        for t in range(window, T - horizon):
            X.append(traj[t - window: t])
            Y_rtt.append(traj[t: t + horizon, :PREDICT_DIM])
            # disc label: any disconnect at t OR t+1 (the next-1-second window)
            disc_t  = 1.0 - float(traj[t, CONNECTED_IDX])
            disc_t1 = 1.0 - float(traj[t + 1, CONNECTED_IDX]) if t + 1 < T else 0.0
            Y_disc.append(max(disc_t, disc_t1))
    return (np.array(X, dtype=np.float32),
            np.array(Y_rtt, dtype=np.float32),
            np.array(Y_disc, dtype=np.float32))


def auroc(scores, labels):
    """Trapezoidal AUROC. Works for tiny tensors without sklearn."""
    scores = np.asarray(scores).ravel()
    labels = np.asarray(labels).ravel().astype(np.int64)
    if labels.sum() == 0 or labels.sum() == len(labels):
        return float("nan")
    order = np.argsort(-scores)
    labels_sorted = labels[order]
    tp_cum = np.cumsum(labels_sorted)
    fp_cum = np.cumsum(1 - labels_sorted)
    tp = tp_cum / max(1, labels.sum())
    fp = fp_cum / max(1, (len(labels) - labels.sum()))
    return float(np.trapz(np.concatenate([[0], tp]),
                          np.concatenate([[0], fp])))


def train_joint(num_episodes=2000, max_cycles=100, epochs=60,
                batch_size=128, lr=1e-3, lam=1.0, save_path=None, seed=42):
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    print(f"Collecting {num_episodes} random-action trajectories…")
    episodes = collect_trajectories(num_episodes, max_cycles, seed=seed)
    X, Yr, Yd = make_joint_dataset(episodes)
    print(f"  Pairs: X={X.shape}, Y_rtt={Yr.shape}, Y_disc={Yd.shape} "
          f"(positive rate = {Yd.mean():.3f})")
    n = X.shape[0]
    n_train = int(0.9 * n)
    perm = np.random.permutation(n)
    Xtr, Ytr_r, Ytr_d = X[perm[:n_train]], Yr[perm[:n_train]], Yd[perm[:n_train]]
    Xva, Yva_r, Yva_d = X[perm[n_train:]], Yr[perm[n_train:]], Yd[perm[n_train:]]

    model = JointForecaster()
    opt = optim.Adam(model.parameters(), lr=lr)
    mse = nn.MSELoss()
    bce = nn.BCEWithLogitsLoss()
    log = []

    Xtr_t = torch.as_tensor(Xtr); Ytr_r_t = torch.as_tensor(Ytr_r)
    Ytr_d_t = torch.as_tensor(Ytr_d)
    Xva_t = torch.as_tensor(Xva); Yva_r_t = torch.as_tensor(Yva_r)
    Yva_d_t = torch.as_tensor(Yva_d)

    for ep in range(epochs):
        model.train()
        idx = np.random.permutation(len(Xtr))
        sums = {"l": 0.0, "lr": 0.0, "ld": 0.0, "n": 0}
        for s in range(0, len(idx), batch_size):
            mb = torch.as_tensor(idx[s:s + batch_size], dtype=torch.long)
            rtt_pred, disc_logit = model(Xtr_t[mb])
            l_rtt = mse(rtt_pred, Ytr_r_t[mb])
            l_disc = bce(disc_logit, Ytr_d_t[mb])
            loss = l_rtt + lam * l_disc
            opt.zero_grad(); loss.backward(); opt.step()
            sums["l"] += loss.item(); sums["lr"] += l_rtt.item()
            sums["ld"] += l_disc.item(); sums["n"] += 1
        nb = max(1, sums["n"])
        model.eval()
        with torch.no_grad():
            vr, vd_logit = model(Xva_t)
            v_mse = mse(vr, Yva_r_t).item()
            v_bce = bce(vd_logit, Yva_d_t).item()
            v_probs = torch.sigmoid(vd_logit).numpy()
            v_auroc = auroc(v_probs, Yva_d)
        row = {"epoch": ep,
               "train_loss": sums["l"] / nb,
               "train_mse": sums["lr"] / nb,
               "train_bce": sums["ld"] / nb,
               "val_mse": v_mse, "val_bce": v_bce, "val_auroc": v_auroc}
        log.append(row)
        if ep % 5 == 0 or ep == epochs - 1:
            print(f"  ep {ep:>3}  L={row['train_loss']:.4f}  "
                  f"mse_v={v_mse:.5f}  bce_v={v_bce:.4f}  auroc_v={v_auroc:.3f}")

    # ── Sanity checks ────────────────────────────────────────────────
    print("\n--- Sanity ---")
    # 1) AUROC on val
    pass_auroc = v_auroc > 0.85
    print(f"  val AUROC = {v_auroc:.4f}  "
          f"(target > 0.85: {'PASS' if pass_auroc else 'FAIL'})")
    # 2) RTT MSE comparison to existing SSMPredictor checkpoint
    old_ckpt = ROOT / "trained_ssm_predictor.pt"
    if old_ckpt.exists():
        old = SSMPredictor()
        old.load_state_dict(torch.load(old_ckpt, map_location="cpu",
                                         weights_only=True))
        old.eval()
        with torch.no_grad():
            old_pred = old(Xva_t)
            old_mse = mse(old_pred, Yva_r_t).item()
        regress = v_mse > 1.5 * old_mse  # >50% worse counts as regression
        print(f"  RTT MSE old={old_mse:.5f}  new={v_mse:.5f}  "
              f"(no >50% regression: {'PASS' if not regress else 'FAIL'})")
    else:
        regress = False
        print("  (no existing trained_ssm_predictor.pt — skipping MSE comparison)")
    print(f"  positive rate in val: {Yva_d.mean():.3f} "
          f"({int(Yva_d.sum())} of {len(Yva_d)} samples)")

    if save_path:
        torch.save(model.state_dict(), save_path)
        Path(save_path).with_suffix(".log.json").write_text(json.dumps(log, indent=2))
        print(f"\n  Saved {save_path}")
    return model, log, {"val_auroc": v_auroc, "val_mse": v_mse,
                         "pass_auroc": pass_auroc, "pass_no_regress": not regress}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=2000)
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--max-cycles", type=int, default=100)
    p.add_argument("--lam", type=float, default=1.0)
    p.add_argument("--save", default=str(ROOT / "trained_joint_forecaster.pt"))
    args = p.parse_args()
    train_joint(num_episodes=args.episodes, max_cycles=args.max_cycles,
                 epochs=args.epochs, lam=args.lam, save_path=args.save)


if __name__ == "__main__":
    main()
