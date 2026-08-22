#!/usr/bin/env python3
"""
E31: Network characterization and predictability from real traces.

Parts A–D:
  A. Dataset selection and download (run first-time only; assets already present).
  B. Derive per-second reachability and bandwidth time series.
  C. Predictability: persistence fraction + empirical Markov at H={10,30,60}s.
  D. Transfer latency under measured BW profiles (Python socket rate-limiting;
     netem requires sudo-tc which is not available in this environment).

Outputs:
  results/cost/e31_network/reachability_series.csv
  results/cost/e31_network/bandwidth_series.csv
  results/cost/e31_network/predictability_metrics.csv
  results/cost/e31_network/transfer_latency.csv
  figures/cost/e31_reachability.pdf/.png
  figures/cost/e31_predictability.pdf/.png
"""

import csv
import datetime
import json
import math
import os
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parent.parent.parent
RAW = REPO / "results/cost/e31_network/raw"
OUT = REPO / "results/cost/e31_network"
FIG = REPO / "figures/cost"
FIG.mkdir(parents=True, exist_ok=True)

HEROLAB_DIR = RAW / "herolab_rssi"
IRISH5G_DIR = RAW / "irish5g/5G-production-dataset"

# ── Part A: Dataset provenance ─────────────────────────────────────────────────
DATASET_A_NOTE = """
Dataset 1 (reachability / RSSI): herolab-uga/indoor-rssi-mobile-robot (GitHub)
  - URL: https://github.com/herolab-uga/indoor-rssi-mobile-robot
  - License: not stated (no COPYING/LICENSE file in repo)
  - 7 .datalog files; 20m×26m indoor office; single Wi-Fi AP at (9,0)
  - Columns: temp_sec, temp_nsec, robot_pos_x/y, RSSI per 5 antennae
  - Sample rate: ~5 Hz (median 206ms between measurements)
  - LIMITATION: near-100% connectivity (RSSI p5 = -64 dBm; <1% below -80 dBm).
    The small indoor space and single AP produce no meaningful association events.
    Used for RSSI distribution characterization only, not for reachability events.

Dataset 2 (throughput + reachability): uccmisl/5Gdataset — Irish 5G (GitHub)
  - URL: https://github.com/uccmisl/5Gdataset
  - License: GPL-3.0
  - 5G network, Ireland; Download/Driving subset (16 files, ~1 Hz sample rate)
  - Columns: Timestamp(sec), DL_bitrate(Mbps), State(D/I), CellID, RSRP, RSSI
  - Reachability: State D = network active; State I = idle (possible app pause,
    not guaranteed network disconnect — noted as limitation)
  - Handover events: CellID transitions within a session
  - LIMITATION: driving mobility (not pedestrian). PINGAVG not populated.
"""

# ── Part B helpers ─────────────────────────────────────────────────────────────

def parse_ts(ts: str) -> float:
    """Parse Irish 5G timestamp string to Unix float (second precision)."""
    return datetime.datetime.strptime(ts, "%Y.%m.%d_%H.%M.%S").timestamp()


def load_session(path: Path):
    """Load one Irish 5G CSV; return per-second binned DataFrame as lists."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                t = parse_ts(row["Timestamp"])
                bw = float(row["DL_bitrate"])       # Mbps
                state = 1 if row["State"] == "D" else 0
                cell = int(row["CellID"]) if row["CellID"].lstrip("-").isdigit() else -1
                rows.append((t, bw, state, cell))
            except (ValueError, KeyError):
                continue
    if not rows:
        return None, None, None, None

    times = np.array([r[0] for r in rows])
    bws   = np.array([r[1] for r in rows])
    states = np.array([r[2] for r in rows])
    cells  = np.array([r[3] for r in rows])

    # Per-second binning: integer-second boundaries
    t0, t1 = int(times[0]), int(times[-1])
    bins = np.arange(t0, t1 + 1)
    bw_binned, state_binned, cell_binned = [], [], []
    for tb in bins:
        mask = (times >= tb) & (times < tb + 1)
        if mask.any():
            bw_binned.append(float(np.mean(bws[mask])))
            state_binned.append(int(np.round(np.mean(states[mask]))))
            cell_binned.append(int(np.median(cells[mask])))
        else:
            bw_binned.append(np.nan)
            state_binned.append(0)
            cell_binned.append(-1)

    return bins, np.array(bw_binned), np.array(state_binned), np.array(cell_binned)


def load_herolab_rssi():
    """Load all herolab datasets; return clean center-antenna RSSI values."""
    all_rssi = []
    for path in sorted(HEROLAB_DIR.glob("Dataset*.datalog")):
        data = np.genfromtxt(path, skip_header=1)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        c_rssi = data[:, 19]  # C_level_a (column 19, raw center RSSI in dBm)
        # Exclude corrupted readings (positive RSSI is nonsense)
        clean = c_rssi[(c_rssi > -120) & (c_rssi < 0)]
        all_rssi.extend(clean.tolist())
    return np.array(all_rssi)


# ── Part C: Predictability ────────────────────────────────────────────────────

def persistence_accuracy(series: np.ndarray, H: int) -> float:
    """Fraction of time steps where state(t) == state(t+H)."""
    if len(series) <= H:
        return np.nan
    s0 = series[:-H]
    sH = series[H:]
    valid = ~(np.isnan(s0) | np.isnan(sH))
    if valid.sum() == 0:
        return np.nan
    return float((s0[valid] == sH[valid]).mean())


def empirical_markov(series: np.ndarray, H: int):
    """
    Estimate empirical H-step Markov transition matrix for binary state.
    Returns 2×2 matrix P where P[i,j] = P(state=j at t+H | state=i at t).
    """
    if len(series) <= H:
        return np.full((2, 2), np.nan)
    s0 = series[:-H].astype(int)
    sH = series[H:].astype(int)
    valid = (s0 >= 0) & (s0 <= 1) & (sH >= 0) & (sH <= 1)
    s0, sH = s0[valid], sH[valid]
    P = np.zeros((2, 2))
    for i in range(2):
        mask = s0 == i
        if mask.sum() > 0:
            P[i, 0] = (sH[mask] == 0).mean()
            P[i, 1] = (sH[mask] == 1).mean()
        else:
            P[i, :] = np.nan
    return P


def bw_autocorr(series: np.ndarray, H: int) -> float:
    """Pearson r between BW(t) and BW(t+H) for valid pairs."""
    if len(series) <= H:
        return np.nan
    s0 = series[:-H]
    sH = series[H:]
    valid = ~(np.isnan(s0) | np.isnan(sH))
    if valid.sum() < 2:
        return np.nan
    return float(np.corrcoef(s0[valid], sH[valid])[0, 1])


# ── Part D: Transfer latency ──────────────────────────────────────────────────

def rate_limited_send(sock, data: bytes, rate_bps: float):
    """Send data over socket at rate_bps bits/second (user-space limiting)."""
    chunk = 65536
    bytes_per_chunk = chunk
    seconds_per_chunk = bytes_per_chunk * 8 / rate_bps
    sent = 0
    while sent < len(data):
        end = min(sent + chunk, len(data))
        t0 = time.perf_counter()
        sock.sendall(data[sent:end])
        sent = end
        elapsed = time.perf_counter() - t0
        sleep = seconds_per_chunk - elapsed
        if sleep > 0:
            time.sleep(sleep)


def loopback_transfer(payload_bytes: int, rate_mbps: float, rtt_ms: float = 20.0):
    """
    Transfer payload_bytes over loopback with user-space rate limiting.
    Returns dict with actual_throughput_mbps, actual_latency_s, payload_mb.

    rate_mbps: BW cap in Mbps
    rtt_ms: one-way delay to add (simulated via pre-transfer sleep on sender)
    """
    port = 19874
    rate_bps = rate_mbps * 1e6
    payload = os.urandom(min(payload_bytes, 50 * 1024 * 1024))  # cap at 50 MB for speed
    actual_size = len(payload)

    result_container = {}

    def server():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        conn, _ = srv.accept()
        received = 0
        t0 = time.perf_counter()
        while received < actual_size:
            chunk = conn.recv(65536)
            if not chunk:
                break
            received += len(chunk)
        t1 = time.perf_counter()
        conn.close()
        srv.close()
        result_container["elapsed_s"] = t1 - t0
        result_container["received"] = received

    srv_thread = threading.Thread(target=server, daemon=True)
    srv_thread.start()
    time.sleep(0.05)  # let server bind

    try:
        cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cli.connect(("127.0.0.1", port))
        # Simulate one-way delay: sleep RTT/2 before starting (half RTT on sender)
        time.sleep(rtt_ms / 2 / 1000.0)
        rate_limited_send(cli, payload, rate_bps)
        cli.close()
    except Exception as e:
        return {"error": str(e)}

    srv_thread.join(timeout=120)
    if "elapsed_s" not in result_container:
        return {"error": "server did not complete"}

    elapsed = result_container["elapsed_s"]
    throughput_mbps = (actual_size * 8 / 1e6) / elapsed
    # If payload was capped, scale up theoretical latency
    if payload_bytes > actual_size:
        theoretical_s = payload_bytes * 8 / rate_bps + rtt_ms / 2 / 1000.0
    else:
        theoretical_s = elapsed

    return {
        "payload_bytes": payload_bytes,
        "actual_size_bytes": actual_size,
        "rate_cap_mbps": rate_mbps,
        "rtt_ms": rtt_ms,
        "actual_throughput_mbps": round(throughput_mbps, 3),
        "elapsed_s": round(elapsed, 3),
        "theoretical_s_fullsize": round(payload_bytes * 8 / rate_bps + rtt_ms / 2 / 1000.0, 3),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("E31: Network characterization")
    print("=" * 60)

    # ── B: Load Irish 5G driving sessions ───────────────────────────────────
    print("\n[B] Loading Irish 5G Download/Driving sessions...")
    driving_files = sorted((IRISH5G_DIR / "Download/Driving").glob("*.csv"))
    print(f"    Found {len(driving_files)} driving session files")

    all_reachability = []   # (t, state, cell, session_id)
    all_bw = []             # (t, bw_mbps, session_id)

    for sid, path in enumerate(driving_files):
        bins, bw, state, cell = load_session(path)
        if bins is None:
            continue
        dur = len(bins)
        # Relative time within session
        for i in range(dur):
            all_reachability.append((int(bins[i]), int(state[i]), int(cell[i]), sid))
            if state[i] == 1 and not np.isnan(bw[i]) and bw[i] > 0:
                all_bw.append((int(bins[i]), float(bw[i]) / 1000.0, sid))  # kbps → Mbps

    print(f"    Total seconds across sessions: {len(all_reachability)}")
    print(f"    Active-state (D) seconds: {len(all_bw)}")

    # Write reachability CSV
    reach_path = OUT / "reachability_series.csv"
    with open(reach_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unix_t", "state_D1_I0", "cell_id", "session_id"])
        w.writerows(all_reachability)
    print(f"    Wrote {reach_path.name}")

    # Write BW CSV
    bw_path = OUT / "bandwidth_series.csv"
    with open(bw_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unix_t", "dl_bitrate_mbps", "session_id"])
        w.writerows(all_bw)
    print(f"    Wrote {bw_path.name}")

    # Summary stats
    states_arr = np.array([r[1] for r in all_reachability])
    bw_arr = np.array([r[1] for r in all_bw])
    cells_arr = np.array([r[2] for r in all_reachability])

    frac_connected = states_arr.mean()
    print(f"\n    Fraction connected (State=D): {frac_connected:.3f}")
    print(f"    BW (connected only): p5={np.percentile(bw_arr,5):.1f} p25={np.percentile(bw_arr,25):.1f} median={np.median(bw_arr):.1f} p75={np.percentile(bw_arr,75):.1f} p95={np.percentile(bw_arr,95):.1f} Mbps")

    # Handover events: count CellID transitions per session
    handover_counts = []
    for sid in range(len(driving_files)):
        session_rows = [(r[0], r[2]) for r in all_reachability if r[3] == sid]
        if len(session_rows) < 2:
            continue
        session_rows.sort()
        prev_cell = session_rows[0][1]
        ho = 0
        for _, c in session_rows[1:]:
            if c != prev_cell and c != -1 and prev_cell != -1:
                ho += 1
            prev_cell = c
        handover_counts.append(ho)
    print(f"    Handovers per session: mean={np.mean(handover_counts):.1f} min={min(handover_counts)} max={max(handover_counts)}")

    # Herolab RSSI characterization
    herolab_rssi = load_herolab_rssi()
    print(f"\n    Herolab indoor RSSI (n={len(herolab_rssi)}): "
          f"p5={np.percentile(herolab_rssi,5):.0f} median={np.median(herolab_rssi):.0f} p95={np.percentile(herolab_rssi,95):.0f} dBm")
    print(f"    Fraction below -80 dBm: {(herolab_rssi < -80).mean():.4f}")

    # ── C: Predictability ───────────────────────────────────────────────────
    print("\n[C] Predictability analysis (H=10,30,60s)...")
    pred_rows = []

    for H in [10, 30, 60]:
        # Per-session persistence and Markov (then aggregate)
        pers_list, markov_list = [], []
        bw_autocorr_list = []

        for sid in range(len(driving_files)):
            sess_reach = sorted([r for r in all_reachability if r[3] == sid], key=lambda x: x[0])
            if len(sess_reach) <= H + 5:
                continue
            s_arr = np.array([r[1] for r in sess_reach], dtype=float)
            p = persistence_accuracy(s_arr, H)
            if not np.isnan(p):
                pers_list.append(p)
            M = empirical_markov(s_arr, H)
            if not np.any(np.isnan(M)):
                markov_list.append(M)

            # BW autocorr (connected-state only, interpolate)
            bw_sess = [(r[0], r[1]) for r in all_bw if r[2] == sid]
            if len(bw_sess) > H + 5:
                bw_sess.sort()
                bw_ts = np.array([b[1] for b in bw_sess], dtype=float)
                ac = bw_autocorr(bw_ts, H)
                if not np.isnan(ac):
                    bw_autocorr_list.append(ac)

        mean_pers = float(np.mean(pers_list)) if pers_list else np.nan
        mean_markov = np.nanmean(markov_list, axis=0) if markov_list else np.full((2,2), np.nan)
        mean_bw_ac = float(np.mean(bw_autocorr_list)) if bw_autocorr_list else np.nan

        print(f"    H={H:2d}s: persistence={mean_pers:.3f}  "
              f"P(D→D)={mean_markov[1,1]:.3f}  P(I→D)={mean_markov[0,1]:.3f}  "
              f"BW_autocorr={mean_bw_ac:.3f}")

        pred_rows.append({
            "H_s": H,
            "reachability_persistence": round(mean_pers, 4) if not np.isnan(mean_pers) else None,
            "markov_I_to_I": round(float(mean_markov[0, 0]), 4) if not np.any(np.isnan(mean_markov)) else None,
            "markov_I_to_D": round(float(mean_markov[0, 1]), 4) if not np.any(np.isnan(mean_markov)) else None,
            "markov_D_to_I": round(float(mean_markov[1, 0]), 4) if not np.any(np.isnan(mean_markov)) else None,
            "markov_D_to_D": round(float(mean_markov[1, 1]), 4) if not np.any(np.isnan(mean_markov)) else None,
            "bw_autocorr": round(mean_bw_ac, 4) if not np.isnan(mean_bw_ac) else None,
        })

    pred_path = OUT / "predictability_metrics.csv"
    with open(pred_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pred_rows[0].keys())
        w.writeheader()
        w.writerows(pred_rows)
    print(f"    Wrote {pred_path.name}")

    # ── D: Transfer latency under measured BW profiles ──────────────────────
    print("\n[D] Transfer latency (Python socket rate-limiting; netem unavailable—sudo tc not accessible)...")
    # BW profiles from measured Irish 5G driving data (D-state only)
    bw_profiles = {
        "p10_mbps": float(np.percentile(bw_arr, 10)),
        "p50_mbps": float(np.median(bw_arr)),
        "p90_mbps": float(np.percentile(bw_arr, 90)),
    }
    RTT_MS = 20.0   # [ASSUMPTION] typical 5G RTT; PINGAVG not available in this dataset

    # Context state payload sizes (KV cache: 57 KB/token)
    KV_BYTES_PER_TOKEN = 57344
    payloads = {
        "sum80_kv":   80   * KV_BYTES_PER_TOKEN,    # 4.4 MB
        "sum200_kv":  200  * KV_BYTES_PER_TOKEN,     # 10.9 MB
        "win10_kv":   400  * KV_BYTES_PER_TOKEN,     # 21.9 MB
        "full_8k_kv": 8192 * KV_BYTES_PER_TOKEN,    # 449 MB (theoretical only)
    }

    transfer_rows = []
    for payload_name, payload_bytes in payloads.items():
        for profile_name, rate_mbps in bw_profiles.items():
            row = {
                "representation": payload_name,
                "payload_bytes": payload_bytes,
                "bw_profile": profile_name,
                "rate_cap_mbps": round(rate_mbps, 2),
                "rtt_ms_assumed": RTT_MS,
            }
            # Theoretical: T = payload_bits / rate + RTT/2
            theoretical_s = payload_bytes * 8 / (rate_mbps * 1e6) + RTT_MS / 2 / 1000.0
            row["theoretical_s"] = round(theoretical_s, 3)

            # Actual socket transfer: only when payload ≤ 25 MB AND theoretical_s ≤ 120s
            theoretical_s_check = payload_bytes * 8 / (rate_mbps * 1e6)
            if payload_bytes <= 25 * 1024 * 1024 and theoretical_s_check <= 120:
                print(f"    Measuring {payload_name} @ {profile_name} ({rate_mbps:.1f} Mbps)...", end="", flush=True)
                res = loopback_transfer(payload_bytes, rate_mbps, RTT_MS)
                if "error" not in res:
                    row["measured_s"] = res["elapsed_s"]
                    row["measured_throughput_mbps"] = res["actual_throughput_mbps"]
                    print(f" {res['elapsed_s']:.2f}s ({res['actual_throughput_mbps']:.1f} Mbps)")
                else:
                    row["measured_s"] = None
                    row["measured_throughput_mbps"] = None
                    print(f" ERROR: {res['error']}")
            else:
                reason = "payload too large" if payload_bytes > 25 * 1024 * 1024 else f"theoretical_s={theoretical_s_check:.0f}s too slow"
                row["measured_s"] = None
                row["measured_throughput_mbps"] = None
                print(f"    {payload_name} @ {profile_name} ({rate_mbps:.2f} Mbps): theoretical only ({reason})")

            transfer_rows.append(row)

    transfer_path = OUT / "transfer_latency.csv"
    with open(transfer_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=transfer_rows[0].keys())
        w.writeheader()
        w.writerows(transfer_rows)
    print(f"    Wrote {transfer_path.name}")

    # ── Figures ──────────────────────────────────────────────────────────────
    print("\n[Figures] Generating...")

    # Figure 1: Reachability
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    # Panel 1: Representative session reachability time series
    ax = axes[0]
    # Pick longest session
    session_lens = {}
    for r in all_reachability:
        session_lens[r[3]] = session_lens.get(r[3], 0) + 1
    longest_sid = max(session_lens, key=session_lens.get)
    sess_data = sorted([r for r in all_reachability if r[3] == longest_sid], key=lambda x: x[0])
    t_rel = np.arange(len(sess_data))
    s_vals = np.array([r[1] for r in sess_data], dtype=float)
    ax.fill_between(t_rel, s_vals, alpha=0.6, color="#4c72b0", step="post")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Reachable (1=D, 0=I)")
    ax.set_title(f"Reachability — session {longest_sid+1}\n(Irish 5G, Driving, Download)")
    ax.set_ylim(-0.05, 1.15)
    ax.set_yticks([0, 1])

    # Panel 2: Handover counts histogram
    ax = axes[1]
    ax.hist(handover_counts, bins=range(max(handover_counts)+2), color="#dd8452", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Handovers per session")
    ax.set_ylabel("Count")
    ax.set_title("Cell handovers per session\n(16 driving sessions)")

    # Panel 3: DL_bitrate distribution
    ax = axes[2]
    ax.hist(bw_arr, bins=40, color="#55a868", edgecolor="white", linewidth=0.5)
    ax.axvline(np.percentile(bw_arr, 10), color="#d62728", linestyle="--", linewidth=1.2, label="p10")
    ax.axvline(np.median(bw_arr),          color="#9467bd", linestyle="--", linewidth=1.2, label="p50")
    ax.axvline(np.percentile(bw_arr, 90), color="#8c564b", linestyle="--", linewidth=1.2, label="p90")
    ax.set_xlabel("DL bitrate (Mbps, connected state)")
    ax.set_ylabel("Count")
    ax.set_title("Throughput distribution\n(D-state rows, all Driving sessions)")
    ax.legend(fontsize=8)

    plt.tight_layout()
    for ext in ["pdf", "png"]:
        p = FIG / f"e31_reachability.{ext}"
        plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved e31_reachability.pdf/.png")

    # Figure 2: Predictability
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    # Panel 1: Persistence + BW autocorr at H={10,30,60}
    ax = axes[0]
    H_vals = [r["H_s"] for r in pred_rows]
    pers_vals = [r["reachability_persistence"] or 0 for r in pred_rows]
    bw_ac_vals = [r["bw_autocorr"] or 0 for r in pred_rows]
    x = np.arange(len(H_vals))
    w = 0.35
    bars1 = ax.bar(x - w/2, pers_vals, w, label="Reachability persistence", color="#4c72b0")
    bars2 = ax.bar(x + w/2, bw_ac_vals, w, label="BW autocorr (Pearson r)", color="#dd8452")
    ax.set_xticks(x)
    ax.set_xticklabels([f"H={h}s" for h in H_vals])
    ax.set_ylabel("Fraction / correlation")
    ax.set_ylim(0, 1.1)
    ax.set_title("Predictability at horizons H={10,30,60}s\n(Irish 5G, 16 Driving sessions)")
    ax.legend(fontsize=9)
    ax.axhline(0.5, color="gray", linestyle=":", linewidth=0.8)

    # Panel 2: Markov transition matrix at H=60s
    ax = axes[1]
    r60 = next(r for r in pred_rows if r["H_s"] == 60)
    M60 = np.array([
        [r60["markov_I_to_I"] or 0, r60["markov_I_to_D"] or 0],
        [r60["markov_D_to_I"] or 0, r60["markov_D_to_D"] or 0],
    ])
    im = ax.imshow(M60, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["→ I (0)", "→ D (1)"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["from I (0)", "from D (1)"])
    ax.set_title("Empirical Markov matrix at H=60s\n(State I=disconnected, D=connected)")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{M60[i,j]:.2f}", ha="center", va="center",
                    color="white" if M60[i,j] > 0.6 else "black", fontsize=14)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    plt.tight_layout()
    for ext in ["pdf", "png"]:
        p = FIG / f"e31_predictability.{ext}"
        plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved e31_predictability.pdf/.png")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n[Summary]")
    print(f"  Fraction connected (State=D): {frac_connected:.3f}")
    print(f"  BW p10/p50/p90: {bw_profiles['p10_mbps']:.1f} / {bw_profiles['p50_mbps']:.1f} / {bw_profiles['p90_mbps']:.1f} Mbps")
    print(f"  Handovers/session: mean={np.mean(handover_counts):.1f}")
    for r in pred_rows:
        print(f"  H={r['H_s']:2d}s: persistence={r['reachability_persistence']}  "
              f"P(D→D)={r['markov_D_to_D']}  BW_autocorr={r['bw_autocorr']}")

    return {
        "bw_profiles": bw_profiles,
        "frac_connected": frac_connected,
        "handovers_mean": float(np.mean(handover_counts)),
        "pred_rows": pred_rows,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "experiments"))
    try:
        from _provenance import stamp
    except ImportError:
        stamp = None

    summary = main()

    if stamp:
        prov = stamp(script="e31_network.py", model="n/a", device="flash_a6000",
                     n=len(list((IRISH5G_DIR / "Download/Driving").glob("*.csv"))))
    else:
        prov = {
            "git_commit": "pre-provenance",
            "script": "e31_network.py",
            "model": "n/a",
            "device": "flash_a6000",
            "note": "no GPU; network trace analysis only",
            "timestamp": datetime.datetime.now().isoformat(),
        }

    out_json = {
        "bw_profiles_mbps": summary["bw_profiles"],
        "frac_connected": summary["frac_connected"],
        "handovers_per_session_mean": summary["handovers_mean"],
        "predictability": summary["pred_rows"],
        "_provenance": prov,
    }
    json_path = OUT / "e31_summary.json"
    with open(json_path, "w") as f:
        json.dump(out_json, f, indent=2)
    print(f"\n  Wrote e31_summary.json")
    print("Done.")
