"""
Sensitivity analysis: vary key parameters and measure how each policy responds.

Five sweeps:
  1. Memory cap: [6, 8, 10, 13, 16, 32, 64] GB on burst/realistic
  2. Context growth (tokens/cycle): [0, 20, 40, 80, 160, 320] on steady/realistic
  3. Network reliability (disconnection fraction): [0, 0.1, 0.2, 0.3, 0.5] on steady/13GB
  4. Migration cost (LLM warm-load s): [5, 11, 25, 50, 100] on burst/realistic
  5. Prefill ratio (edge_per_token / cloud_per_token): [1, 3, 5, 9, 15, 30] on burst/realistic

Only runs the focused policies: ProactiveMPC, ReactiveThreshold, Oracle, PPO (if avail).
"""

import argparse
import copy
import csv
import json
import random
from pathlib import Path

import cost_model
import orchestrator_sim
from orchestrator_sim import (run_episode, read_workload_csv, read_network_csv)
from policies import ProactiveMPC, ReactiveThreshold, Oracle
from overlap_migration_policy import OverlapMigrationPolicy
import markov_network as mk

ROOT = Path(__file__).parent
WORKLOAD_DIR = ROOT / "traces" / "workload"
NETWORK_DIR = ROOT / "traces" / "network"


def _focus_policies(include_ppo, ppo_path, include_ssm=True,
                     ssm_mpc_path=None):
    from speculative_lh_policy import SpeculativeLHPolicy
    from routed_sync_lh_policy import RoutedSyncLHPolicy
    from hot_standby_lh_policy import HotStandbyLHPolicy
    pol = [ProactiveMPC(), ReactiveThreshold(),
           OverlapMigrationPolicy(),
           SpeculativeLHPolicy(),
           RoutedSyncLHPolicy(),
           HotStandbyLHPolicy(),
           Oracle()]
    if include_ppo and Path(ppo_path).exists():
        from rl_policy import PPOPolicy
        pol.append(PPOPolicy(ppo_path))
    if include_ssm:
        ssm_mpc_path = ssm_mpc_path or str(ROOT / "trained_ssm_predictor.pt")
        if Path(ssm_mpc_path).exists():
            from ssm_mpc_policy import SSMMPCPolicy
            pol.append(SSMMPCPolicy(ssm_mpc_path))
    return pol


def _run_episode(policy, workload, network, memory_cap_mb=13_000):
    return run_episode(workload, network, policy,
                       memory_cap_mb=memory_cap_mb,
                       start_quant="fp16", start_location="edge",
                       start_mode="full", lookahead=50)


def _record(metrics):
    return {
        "mean_cycle_latency_s": round(metrics.mean_cycle_latency_s, 3),
        "total_planning_gap_s": round(metrics.total_planning_gap_s, 2),
        "num_migrations": metrics.num_migrations,
        "peak_memory_mb": round(metrics.peak_memory_mb, 1),
        "oom_events": metrics.oom_events,
        "mean_quality": round(metrics.mean_quality, 3),
    }


# ── Param-override helpers (monkey-patch both modules) ─────────────────

def _patch_tokens_per_cycle(value):
    cost_model.TOKENS_PER_CYCLE_FULL = value
    orchestrator_sim.TOKENS_PER_CYCLE_FULL = value


def _restore_tokens_per_cycle(orig):
    cost_model.TOKENS_PER_CYCLE_FULL = orig
    orchestrator_sim.TOKENS_PER_CYCLE_FULL = orig


def _patch_load_warm(value_s):
    cost_model.FP16["llm_load_warm_s"] = value_s
    cost_model.INT4["llm_load_warm_s"] = value_s


def _patch_cloud_prefill(edge_to_cloud_ratio):
    edge_per_tok = cost_model.FP16["llm_prefill_ms_per_token"]
    cost_model.CLOUD["llm_prefill_ms_per_token"] = edge_per_tok / edge_to_cloud_ratio


# ── Network synthesis for reliability sweep ────────────────────────────

def make_network_with_disconnect_fraction(frac, n=600, seed=0):
    """Return a network trace where `frac` of the time is disconnected."""
    rng = random.Random(seed)
    samples = []
    # Use a 60s on/off cycle scaled by frac
    on_s = max(1, int(60 * (1 - frac)))
    off_s = max(0, int(60 * frac))
    period = on_s + off_s
    for t in range(n):
        in_p = t % period if period > 0 else 0
        if in_p < on_s:
            rtt = 30 + rng.gauss(0, 3)
            samples.append({"time_s": float(t), "rtt_ms": max(5.0, rtt),
                            "bandwidth_mbps": 100.0, "connected": True})
        else:
            samples.append({"time_s": float(t), "rtt_ms": 5000.0,
                            "bandwidth_mbps": 0.0, "connected": False})
    return samples


# ── 1. Memory cap ──────────────────────────────────────────────────────

def sweep_memory(policies, out_dir):
    caps_gb = [6, 8, 10, 13, 16, 32, 64]
    workload = read_workload_csv(WORKLOAD_DIR / "trace_burst.csv")
    network = read_network_csv(NETWORK_DIR / "net_realistic.csv")
    rows = []
    for cap in caps_gb:
        for pol in policies:
            m = _run_episode(pol, workload, network, memory_cap_mb=cap * 1000)
            rec = {"memory_cap_gb": cap, "policy": pol.name, **_record(m)}
            rows.append(rec)
            print(f"  mem={cap:>3}GB  {pol.name:<18} latency={rec['mean_cycle_latency_s']:6.2f}s "
                  f"oom={rec['oom_events']}")
    out = out_dir / "sensitivity_memory.json"
    out.write_text(json.dumps({"param": "memory_cap_gb", "values": caps_gb,
                                "rows": rows}, indent=2))
    print(f"  -> {out}")


# ── 2. Context growth rate ─────────────────────────────────────────────

def sweep_context_growth(policies, out_dir):
    rates = [0, 20, 40, 80, 160, 320]
    workload = read_workload_csv(WORKLOAD_DIR / "trace_steady.csv")
    network = read_network_csv(NETWORK_DIR / "net_realistic.csv")
    orig = cost_model.TOKENS_PER_CYCLE_FULL
    rows = []
    try:
        for rate in rates:
            _patch_tokens_per_cycle(rate)
            for pol in policies:
                m = _run_episode(pol, workload, network, memory_cap_mb=13_000)
                rec = {"tokens_per_cycle": rate, "policy": pol.name, **_record(m)}
                rows.append(rec)
                print(f"  rate={rate:>3}  {pol.name:<18} latency={rec['mean_cycle_latency_s']:6.2f}s "
                      f"peak={rec['peak_memory_mb']:.0f}MB")
    finally:
        _restore_tokens_per_cycle(orig)
    out = out_dir / "sensitivity_context_growth.json"
    out.write_text(json.dumps({"param": "tokens_per_cycle", "values": rates,
                                "rows": rows}, indent=2))
    print(f"  -> {out}")


# ── 3. Network reliability ─────────────────────────────────────────────

def _markov_trace_with_disc_bias(profile, alpha, n_seconds=600, seed=0):
    """Return a Markov trace with the profile's matrix biased toward more
    disconnected mass. alpha in [0, 1]: how much each row's mass is moved to
    the disconnected column. alpha=0 leaves the matrix unchanged.
    """
    import numpy as np
    P = mk.PROFILES[profile].copy()
    # Move alpha fraction of (good, degraded) mass into disconnected for each row.
    for r in range(P.shape[0]):
        moved = alpha * (P[r, 0] + P[r, 1])
        P[r, 0] *= (1 - alpha)
        P[r, 1] *= (1 - alpha)
        P[r, 2] += moved
    # Temporarily swap in the perturbed matrix
    orig = mk.PROFILES[profile]
    mk.PROFILES[profile] = P
    try:
        rows = mk.sample_trace(profile, n_seconds=n_seconds, seed=seed)
    finally:
        mk.PROFILES[profile] = orig
    # Reshape to the dict format the simulator expects
    return [{"time_s": r["time_s"], "rtt_ms": r["rtt_ms"],
             "bandwidth_mbps": r["bandwidth_mbps"],
             "connected": bool(r["connected"])} for r in rows]


def sweep_network(policies, out_dir):
    # Per-profile baseline runs (alpha=0) + biased variants. This is the
    # disconnection-fraction sweep, now expressed as a perturbation of the
    # Markov transition matrix rather than an injected on/off cycle.
    alphas = [0.0, 0.05, 0.10, 0.20, 0.40]
    profiles = ["campus", "urban", "indoor"]
    workload = read_workload_csv(WORKLOAD_DIR / "trace_steady.csv")
    rows = []
    for profile in profiles:
        for alpha in alphas:
            net = _markov_trace_with_disc_bias(profile, alpha, n_seconds=600, seed=0)
            n_disc = sum(1 for r in net if not r["connected"])
            obs_frac = round(n_disc / len(net), 4)
            for pol in policies:
                m = _run_episode(pol, workload, net, memory_cap_mb=13_000)
                rec = {"profile": profile, "alpha": alpha,
                       "observed_disconnect_fraction": obs_frac,
                       "policy": pol.name, **_record(m),
                       "peak_memory_mb_overlap": m.peak_memory_mb_overlap,
                       "n_lh_aborts": m.n_lh_aborts}
                rows.append(rec)
                print(f"  {profile:<7} a={alpha:.2f} disc={obs_frac:>5}  "
                      f"{pol.name:<18} latency={rec['mean_cycle_latency_s']:6.2f}s "
                      f"gap={rec['total_planning_gap_s']:5.1f}s migs={rec['num_migrations']}")
    out = out_dir / "sensitivity_network.json"
    out.write_text(json.dumps({"param": "markov_disc_alpha",
                                "alphas": alphas, "profiles": profiles,
                                "rows": rows}, indent=2))
    print(f"  -> {out}")


# ── 4. Migration cost (LLM warm-load time) ─────────────────────────────

def sweep_migration_cost(policies, out_dir):
    times = [5, 11, 25, 50, 100]
    workload = read_workload_csv(WORKLOAD_DIR / "trace_burst.csv")
    network = read_network_csv(NETWORK_DIR / "net_realistic.csv")
    orig_fp16 = cost_model.FP16["llm_load_warm_s"]
    orig_int4 = cost_model.INT4["llm_load_warm_s"]
    rows = []
    try:
        for t in times:
            _patch_load_warm(t)
            for pol in policies:
                m = _run_episode(pol, workload, network, memory_cap_mb=13_000)
                rec = {"llm_load_warm_s": t, "policy": pol.name, **_record(m)}
                rows.append(rec)
                print(f"  load={t:>3}s  {pol.name:<18} latency={rec['mean_cycle_latency_s']:6.2f}s "
                      f"gap={rec['total_planning_gap_s']:.1f}s migs={rec['num_migrations']}")
    finally:
        cost_model.FP16["llm_load_warm_s"] = orig_fp16
        cost_model.INT4["llm_load_warm_s"] = orig_int4
    out = out_dir / "sensitivity_migration_cost.json"
    out.write_text(json.dumps({"param": "llm_load_warm_s", "values": times,
                                "rows": rows}, indent=2))
    print(f"  -> {out}")


# ── 5. Prefill cost ratio (edge / cloud) ───────────────────────────────

def sweep_prefill_ratio(policies, out_dir):
    ratios = [1, 3, 5, 9, 15, 30]
    workload = read_workload_csv(WORKLOAD_DIR / "trace_burst.csv")
    network = read_network_csv(NETWORK_DIR / "net_realistic.csv")
    orig_cloud = cost_model.CLOUD["llm_prefill_ms_per_token"]
    rows = []
    try:
        for r in ratios:
            _patch_cloud_prefill(r)
            for pol in policies:
                m = _run_episode(pol, workload, network, memory_cap_mb=13_000)
                rec = {"prefill_ratio": r, "policy": pol.name, **_record(m)}
                rows.append(rec)
                print(f"  ratio={r:>2}x  {pol.name:<18} latency={rec['mean_cycle_latency_s']:6.2f}s "
                      f"migs={rec['num_migrations']}")
    finally:
        cost_model.CLOUD["llm_prefill_ms_per_token"] = orig_cloud
    out = out_dir / "sensitivity_prefill_ratio.json"
    out.write_text(json.dumps({"param": "prefill_ratio", "values": ratios,
                                "rows": rows}, indent=2))
    print(f"  -> {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--include-ppo", action="store_true", default=True)
    p.add_argument("--no-ppo", dest="include_ppo", action="store_false")
    p.add_argument("--ppo-path", default=str(ROOT / "trained_ppo.pt"))
    p.add_argument("--output-dir", default=str(ROOT / "results"))
    args = p.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    policies = _focus_policies(args.include_ppo, args.ppo_path)
    print(f"Policies in sweep: {[p.name for p in policies]}")

    print("\n--- 1. Memory cap ---")
    sweep_memory(policies, out_dir)
    print("\n--- 2. Context growth ---")
    sweep_context_growth(policies, out_dir)
    print("\n--- 3. Network reliability ---")
    sweep_network(policies, out_dir)
    print("\n--- 4. Migration cost ---")
    sweep_migration_cost(policies, out_dir)
    print("\n--- 5. Prefill ratio ---")
    sweep_prefill_ratio(policies, out_dir)


if __name__ == "__main__":
    main()
