"""SSM vs MPC ablation table.

Reads comparison_track1.json and produces a per-scenario delta of
mean_cycle_latency_s between SSM+MPC and ProactiveMPC. The Track 1 spec
flagged this as the key open question: under deterministic synthetic
traces the delta was 0.00; the question is whether temporal encoding
moves the needle under Markov chains.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "results" / "comparison_track1.json"
OUT = ROOT / "results" / "ssm_ablation.json"


def main():
    rows = json.loads(SRC.read_text())
    by_scenario = {}
    for r in rows:
        if r["policy"] not in ("ProactiveMPC", "SSM+MPC"):
            continue
        key = (r["workload"], r["network"])
        by_scenario.setdefault(key, {})[r["policy"]] = r["mean_cycle_latency_s"]

    out_rows = []
    print(f"{'workload':<10} {'network':<18} {'MPC':>7} {'SSM+MPC':>9} {'Δ':>7}  {'Δ%':>7}")
    print("-" * 64)
    for (wl, net), pol_map in sorted(by_scenario.items()):
        mpc = pol_map.get("ProactiveMPC")
        ssm = pol_map.get("SSM+MPC")
        if mpc is None or ssm is None:
            continue
        delta = ssm - mpc
        pct = 100.0 * delta / mpc if mpc else 0.0
        out_rows.append({"workload": wl, "network": net,
                         "ProactiveMPC": mpc, "SSM+MPC": ssm,
                         "delta_s": round(delta, 3),
                         "delta_pct": round(pct, 2)})
        print(f"{wl:<10} {net:<18} {mpc:>7.2f} {ssm:>9.2f} {delta:>+7.3f}  {pct:>+6.2f}%")

    # Aggregate over Markov-only scenarios
    markov = [r for r in out_rows if r["network"].startswith("markov_")]
    if markov:
        mean_d = sum(r["delta_s"] for r in markov) / len(markov)
        wins = sum(1 for r in markov if r["delta_s"] < -0.01)
        ties = sum(1 for r in markov if abs(r["delta_s"]) <= 0.01)
        losses = sum(1 for r in markov if r["delta_s"] > 0.01)
        summary = {"n_markov_scenarios": len(markov),
                   "mean_delta_s": round(mean_d, 4),
                   "ssm_wins": wins, "ties": ties, "ssm_losses": losses,
                   "best_ssm_win_s": round(min(r["delta_s"] for r in markov), 3),
                   "best_ssm_win_scenario": min(markov, key=lambda r: r["delta_s"])
                                              ["workload"] + "/" +
                                              min(markov, key=lambda r: r["delta_s"])["network"]}
        print("\nMarkov-only summary:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    else:
        summary = {}

    OUT.write_text(json.dumps({"per_scenario": out_rows,
                                 "markov_summary": summary}, indent=2))
    print(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
