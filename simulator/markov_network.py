"""
Three-state discrete-time Markov network model.

States: good / degraded / disconnected. Per-second tick matching the existing
network trace cadence. Outputs CSV rows in the same schema as
generate_network_traces.py so the simulator's network_at() consumes them
unchanged.

Profiles: campus / urban / indoor — each with its own 3x3 transition matrix
(hand-set placeholders, to be calibrated from real WiFi traces in Track 2).

References:
- Gilbert (1960), Elliott (1963) — burst-noise channel.
- Wang & Moayeri (1995) — finite-state Markov channels.
- Sui et al., WiFiSeer, MobiSys 2016 — good-state latency anchors.
- Hasslinger & Hohlfeld (2008) — Gilbert-Elliott packet loss.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


STATES = ["good", "degraded", "disconnected"]
S_GOOD, S_DEGRADED, S_DISCONNECTED = 0, 1, 2

# State-conditional latency distributions and loss rates.
# Lognormal parameterised by (median ms, sigma) such that quantile targets match
# the spec's anchors. We solve for sigma analytically from p99 ≈ exp(mu + 2.326 sigma).
def _lognormal_params(median_ms: float, p99_ms: float) -> Tuple[float, float]:
    mu = math.log(median_ms)
    # p99: ln(p99) = mu + 2.326 sigma  ->  sigma = (ln(p99) - mu) / 2.326
    sigma = max(0.05, (math.log(p99_ms) - mu) / 2.326)
    return mu, sigma


GOOD_MU, GOOD_SIGMA = _lognormal_params(median_ms=3.0, p99_ms=250.0)
DEG_MU, DEG_SIGMA = _lognormal_params(median_ms=100.0, p99_ms=1000.0)

STATE_LOSS_RATE = {
    S_GOOD: 0.005,
    S_DEGRADED: 0.075,           # mid-point of 5–10% from spec
    S_DISCONNECTED: 1.0,
}

STATE_BANDWIDTH_MBPS = {
    S_GOOD: 100.0,
    S_DEGRADED: 25.0,
    S_DISCONNECTED: 0.0,
}

DISCONNECTED_RTT_MS = 5000.0


def sample_latency_ms(state: int, rng: random.Random) -> float:
    if state == S_DISCONNECTED:
        return DISCONNECTED_RTT_MS
    if state == S_GOOD:
        return max(1.0, math.exp(rng.gauss(GOOD_MU, GOOD_SIGMA)))
    return max(1.0, math.exp(rng.gauss(DEG_MU, DEG_SIGMA)))


# ── Transition matrices (rows = from-state, cols = to-state) ───────────
# Order: good, degraded, disconnected

CAMPUS = np.array([
    [0.96, 0.035, 0.005],
    [0.60, 0.38,  0.02],
    [0.40, 0.40,  0.20],
])

URBAN = np.array([
    [0.75, 0.20, 0.05],
    [0.35, 0.55, 0.10],
    [0.20, 0.50, 0.30],
])

# NOTE: Spec's indoor matrix produces good-majority steady-state (~63%),
# but the spec text says indoor should have a *degraded* majority. The matrix
# below adjusts good→degraded mass upward so steady-state P(degraded) > P(good).
# Spec values retained in INDOOR_SPEC for traceability.
INDOOR_SPEC = np.array([
    [0.85, 0.13, 0.02],
    [0.25, 0.65, 0.10],
    [0.30, 0.55, 0.15],
])
INDOOR = np.array([
    [0.55, 0.42, 0.03],
    [0.18, 0.72, 0.10],
    [0.30, 0.55, 0.15],
])

# HARSH: underground/rural CPS-style connectivity.
# Transition matrix (rows = from-state, cols = to-state):
#   good→{good,degraded,disc} = {0.77, 0.20, 0.03}   mean dwell good     ≈  4.3 s
#   deg→{good,degraded,disc}  = {0.20, 0.73, 0.07}   mean dwell degraded ≈  3.7 s
#   disc→{good,degraded,disc} = {0.03, 0.02, 0.95}   mean dwell disc     ≈ 20.0 s ≈ 2 cycles
# Steady-state: good≈27%, degraded≈24%, disconnected≈49%.
# Designed to force sustained multi-cycle edge spells and test whether
# super-linear edge re-prefill (inertia) becomes the dominant cost term.
HARSH = np.array([
    [0.77, 0.20, 0.03],
    [0.20, 0.73, 0.07],
    [0.03, 0.02, 0.95],
])

PROFILES: Dict[str, np.ndarray] = {
    "campus": CAMPUS,
    "urban": URBAN,
    "indoor": INDOOR,
    "harsh": HARSH,
}


def steady_state(P: np.ndarray) -> np.ndarray:
    """Left eigenvector of P with eigenvalue 1, normalised to sum 1."""
    vals, vecs = np.linalg.eig(P.T)
    idx = np.argmin(np.abs(vals - 1.0))
    v = np.real(vecs[:, idx])
    v = v / v.sum()
    return v


def mean_dwell_steps(P: np.ndarray) -> np.ndarray:
    """For a DTMC, mean dwell in state i is 1 / (1 - P[i,i])."""
    return 1.0 / (1.0 - np.diag(P))


def sample_trace(profile: str, n_seconds: int = 600, seed: int = 0,
                 start_state: int = S_GOOD) -> List[dict]:
    """Return a list of rows matching the existing network CSV schema."""
    if profile not in PROFILES:
        raise KeyError(f"unknown profile {profile}; choose from {list(PROFILES)}")
    P = PROFILES[profile]
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    state = start_state
    rows = []
    for t in range(n_seconds):
        # First sample latency / loss for this tick
        latency = sample_latency_ms(state, rng)
        loss = STATE_LOSS_RATE[state]
        # Bernoulli loss draw: lost packet at this tick → treat as disconnected
        # for this sample (but the underlying state stays whatever it is).
        connected = True
        if state == S_DISCONNECTED or np_rng.random() < loss:
            connected = False
            rtt_ms = DISCONNECTED_RTT_MS
            bw = 0.0
        else:
            rtt_ms = latency
            bw = STATE_BANDWIDTH_MBPS[state]
        rows.append({
            "time_s": float(t),
            "rtt_ms": round(float(rtt_ms), 2),
            "bandwidth_mbps": round(float(bw), 2),
            "connected": 1 if connected else 0,
            "state": STATES[state],
        })
        # Transition for next tick
        probs = P[state]
        state = int(np_rng.choice(3, p=probs))
    return rows


def write_csv(rows: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        # State column is appended *after* the columns the existing reader
        # consumes, so read_network_csv() continues to work unchanged.
        w.writerow(["time_s", "rtt_ms", "bandwidth_mbps", "connected", "state"])
        for r in rows:
            w.writerow([r["time_s"], r["rtt_ms"], r["bandwidth_mbps"],
                        r["connected"], r["state"]])


def write_default_traces(out_dir: Path, n_seconds: int = 600, seed: int = 0):
    paths = {}
    for profile in PROFILES:
        rows = sample_trace(profile, n_seconds=n_seconds, seed=seed)
        path = out_dir / f"net_markov_{profile}.csv"
        write_csv(rows, path)
        paths[profile] = path
        print(f"  Wrote {path}")
    return paths


# ── Trace summary ──────────────────────────────────────────────────────

def trace_summary(rows: List[dict]) -> dict:
    n = len(rows)
    state_counts = {s: 0 for s in STATES}
    transitions = 0
    last = None
    rtts = []
    for r in rows:
        state_counts[r["state"]] += 1
        if last is not None and r["state"] != last:
            transitions += 1
        last = r["state"]
        if r["connected"]:
            rtts.append(r["rtt_ms"])
    if rtts:
        rtts_arr = np.array(rtts)
        mean_rtt = float(rtts_arr.mean())
        p99_rtt = float(np.percentile(rtts_arr, 99))
    else:
        mean_rtt = float("inf")
        p99_rtt = float("inf")
    return {
        "n": n,
        "fraction_in_state": {s: round(state_counts[s] / n, 4) for s in STATES},
        "transitions_per_hour": round(3600.0 * transitions / n, 2),
        "mean_rtt_ms_connected": round(mean_rtt, 2),
        "p99_rtt_ms_connected": round(p99_rtt, 2),
    }


# ── CLI ────────────────────────────────────────────────────────────────

def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true",
                    help="Print steady-state / dwell / sample trace summaries")
    ap.add_argument("--write", action="store_true",
                    help="Write default 600s traces to traces/network/")
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.validate:
        for name, P in PROFILES.items():
            ss = steady_state(P)
            dwell = mean_dwell_steps(P)
            print(f"\n[{name}]")
            print("  steady-state    :", {s: round(float(v), 4) for s, v in zip(STATES, ss)})
            print("  mean dwell (s)  :", {s: round(float(d), 2) for s, d in zip(STATES, dwell)})
            rows = sample_trace(name, n_seconds=args.seconds, seed=args.seed)
            print("  trace summary   :", trace_summary(rows))

    if args.write:
        out_dir = Path(__file__).parent / "traces" / "network"
        write_default_traces(out_dir, n_seconds=args.seconds, seed=args.seed)


if __name__ == "__main__":
    _cli()
