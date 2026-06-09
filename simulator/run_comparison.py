"""
Step 5: Run all policies × all scenarios, save comparison.

Use --include-ppo to add the trained RL policy.
"""

import argparse
import json
from pathlib import Path
from itertools import product

from orchestrator_sim import (run_episode,
                                 read_workload_csv, read_network_csv)
from policies import all_policies

ROOT = Path(__file__).parent
WORKLOADS = ["steady", "variable", "burst"]
NETWORKS  = ["stable", "degrading", "intermittent", "urban", "realistic",
             "markov_campus", "markov_urban", "markov_indoor"]
MEMORY_CAP_MB = 13_000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--include-ppo", action="store_true")
    p.add_argument("--include-ssm", action="store_true",
                   help="Add SSM+MPC and SSM+RL policies")
    p.add_argument("--ppo-path", default=str(ROOT / "trained_ppo.pt"))
    p.add_argument("--ssm-mpc-path", default=str(ROOT / "trained_ssm_predictor.pt"))
    p.add_argument("--ssm-rl-path", default=str(ROOT / "trained_ssm_rl.pt"))
    p.add_argument("--output", default=str(ROOT / "results" / "comparison.json"))
    args = p.parse_args()

    policies_list = list(all_policies())
    if args.include_ppo:
        from rl_policy import PPOPolicy
        if not Path(args.ppo_path).exists():
            print(f"!! PPO weights not found at {args.ppo_path}; skipping PPO.")
        else:
            policies_list.append(PPOPolicy(args.ppo_path))
            print(f"Loaded PPO from {args.ppo_path}")
    if args.include_ssm:
        from ssm_mpc_policy import SSMMPCPolicy
        from ssm_rl_policy import SSMRLPolicy
        if Path(args.ssm_mpc_path).exists():
            policies_list.append(SSMMPCPolicy(args.ssm_mpc_path))
            print(f"Loaded SSM+MPC from {args.ssm_mpc_path}")
        else:
            print(f"!! SSM+MPC predictor not found at {args.ssm_mpc_path}; skipping.")
        if Path(args.ssm_rl_path).exists():
            policies_list.append(SSMRLPolicy(args.ssm_rl_path))
            print(f"Loaded SSM+RL from {args.ssm_rl_path}")
        else:
            print(f"!! SSM+RL weights not found at {args.ssm_rl_path}; skipping.")

    rows = []
    n_total = len(WORKLOADS) * len(NETWORKS) * len(policies_list)
    print(f"Running {n_total} (policy × scenario) combinations...")

    for wl_name, net_name in product(WORKLOADS, NETWORKS):
        wl_path = ROOT / "traces" / "workload" / f"trace_{wl_name}.csv"
        net_path = ROOT / "traces" / "network" / f"net_{net_name}.csv"
        wl = read_workload_csv(wl_path)
        nt = read_network_csv(net_path)

        for policy in policies_list:
            try:
                m = run_episode(wl, nt, policy,
                                memory_cap_mb=MEMORY_CAP_MB,
                                start_quant="fp16",
                                start_location="edge",
                                start_mode="full",
                                lookahead=50)
            except Exception as e:
                print(f"  FAIL {policy.name} on {wl_name}/{net_name}: {e}")
                continue
            row = {
                "policy": policy.name,
                "workload": wl_name,
                "network": net_name,
                "n_cycles": m.n_cycles,
                "total_time_s": round(m.total_time_s, 2),
                "mean_cycle_latency_s": round(m.mean_cycle_latency_s, 3),
                "total_planning_gap_s": round(m.total_planning_gap_s, 2),
                "num_migrations": m.num_migrations,
                "peak_memory_mb": round(m.peak_memory_mb, 1),
                "oom_events": m.oom_events,
                "mean_quality": round(m.mean_quality, 3),
                "peak_memory_mb_overlap": m.peak_memory_mb_overlap,
                "overlap_total_s": m.overlap_total_s,
                "n_overlap_windows": m.n_overlap_windows,
                "n_lh_aborts": m.n_lh_aborts,
                "peak_memory_mb_continuous": m.peak_memory_mb_continuous,
                "mean_memory_mb_continuous": m.mean_memory_mb_continuous,
                "mean_compute_tokens_per_cycle": m.mean_compute_tokens_per_cycle,
                "mean_compute_seconds_per_cycle": m.mean_compute_seconds_per_cycle,
                "wasted_compute_tokens": m.wasted_compute_tokens,
                "cloud_failure_events": m.cloud_failure_events,
                "successful_fallbacks": m.successful_fallbacks,
                "unrecoverable_cycles": m.unrecoverable_cycles,
            }
            rows.append(row)
            print(f"  {policy.name:<18} {wl_name:>8}/{net_name:<13} "
                  f"latency={row['mean_cycle_latency_s']:6.2f}s "
                  f"gap={row['total_planning_gap_s']:6.1f}s "
                  f"migs={row['num_migrations']:>2}  "
                  f"mem_peak={row['peak_memory_mb']:>5.0f}MB "
                  f"q={row['mean_quality']:.2f}"
                  + (f"  OOM:{row['oom_events']}" if row['oom_events'] else ""))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nSaved to {out}")

    # Print a per-scenario summary table grouped by network
    print("\n" + "=" * 100)
    print("SUMMARY (mean_cycle_latency_s, lower is better)")
    print("=" * 100)
    header = f"{'Policy':<20} " + " ".join(f"{wl[:3]+'/'+net[:5]:>14}"
                                            for wl in WORKLOADS for net in NETWORKS)
    print(header)
    for policy_name in [p.name for p in policies_list]:
        cells = []
        for wl in WORKLOADS:
            for net in NETWORKS:
                hit = next((r for r in rows if r["policy"] == policy_name
                            and r["workload"] == wl and r["network"] == net), None)
                if hit:
                    cells.append(f"{hit['mean_cycle_latency_s']:>14.2f}")
                else:
                    cells.append(f"{'-':>14}")
        print(f"{policy_name:<20} " + " ".join(cells))


if __name__ == "__main__":
    main()
