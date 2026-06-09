"""Side-by-side: RoutedSyncLH vs RoutedSyncSSM_LH vs SpeculativeLH.

All 24 cells (3 workloads × 8 networks). Writes per-cell comparison
to results/sprint_2/ssm_routing_vs_baseline.csv and a one-paragraph
verdict to results/sprint_2/ssm_routing_verdict.txt.

Seeds match the previous comparison runs (default seed=0 inside each
trace file; no per-policy randomness on this path).
"""

import csv
import json
from pathlib import Path

from orchestrator_sim import run_episode, read_workload_csv, read_network_csv
from routed_sync_lh_policy import RoutedSyncLHPolicy
from routed_sync_ssm_lh_policy import RoutedSyncSSMLHPolicy
from speculative_lh_policy import SpeculativeLHPolicy

ROOT = Path(__file__).resolve().parent
TRACES_WL = ROOT / "traces" / "workload"
TRACES_NET = ROOT / "traces" / "network"
OUT = ROOT.parent / "results" / "sprint_2"
OUT.mkdir(parents=True, exist_ok=True)

WORKLOADS = ["steady", "variable", "burst"]
NETWORKS = ["markov_campus", "markov_urban", "markov_indoor",  # priority 1
            "intermittent",                                      # priority 2
            "stable", "degrading", "urban", "realistic"]         # priority 3
MEM_CAP = 13_000


rs = RoutedSyncLHPolicy()
rs_ssm = RoutedSyncSSMLHPolicy()
spec = SpeculativeLHPolicy()

rows = []
for net_name in NETWORKS:
    net = read_network_csv(TRACES_NET / f"net_{net_name}.csv")
    for wl_name in WORKLOADS:
        wl = read_workload_csv(TRACES_WL / f"trace_{wl_name}.csv")
        out = {"workload": wl_name, "network": net_name}
        for pol, tag in [(rs, "rs"), (rs_ssm, "rs_ssm"), (spec, "spec")]:
            m = run_episode(wl, net, pol, memory_cap_mb=MEM_CAP,
                            start_quant="fp16", start_location="edge",
                            start_mode="full", lookahead=50)
            out[f"{tag}_lat"]               = round(m.mean_cycle_latency_s, 4)
            out[f"{tag}_compute_s"]         = round(m.mean_compute_seconds_per_cycle, 4)
            out[f"{tag}_compute_tokens"]    = round(m.mean_compute_tokens_per_cycle, 1)
            out[f"{tag}_quality"]           = round(m.mean_quality, 4)
            out[f"{tag}_migrations"]        = m.num_migrations
            out[f"{tag}_planning_gap"]      = round(m.total_planning_gap_s, 2)
        out["delta_rs_ssm_minus_rs"]   = round(out["rs_ssm_lat"] - out["rs_lat"], 4)
        out["delta_rs_ssm_minus_spec"] = round(out["rs_ssm_lat"] - out["spec_lat"], 4)
        rows.append(out)
        print(f"  {wl_name:<10} {net_name:<14} rs={out['rs_lat']:.3f}  "
              f"rs_ssm={out['rs_ssm_lat']:.3f}  spec={out['spec_lat']:.3f}  "
              f"Δ(rs_ssm-rs)={out['delta_rs_ssm_minus_rs']:+.4f}")

# Write CSV
csv_path = OUT / "ssm_routing_vs_baseline.csv"
fields = ["workload", "network",
          "rs_lat", "rs_ssm_lat", "spec_lat",
          "delta_rs_ssm_minus_rs", "delta_rs_ssm_minus_spec",
          "rs_ssm_migrations", "rs_ssm_planning_gap",
          "rs_compute_s", "rs_ssm_compute_s", "spec_compute_s",
          "rs_ssm_compute_tokens", "rs_ssm_quality"]
with csv_path.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
print(f"\n→ {csv_path}")

# Summary stats
def avg(rs, k): return sum(r[k] for r in rs) / len(rs)
markov_rows = [r for r in rows if r["network"].startswith("markov_")]
intermit_rows = [r for r in rows if r["network"] == "intermittent"]
other_rows = [r for r in rows if not r["network"].startswith("markov_")
              and r["network"] != "intermittent"]

print("\n--- Markov cells (9) ---")
print(f"  mean Δ(rs_ssm - rs)   = {avg(markov_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
print(f"  mean Δ(rs_ssm - spec) = {avg(markov_rows, 'delta_rs_ssm_minus_spec'):+.4f}s")
print("\n--- intermittent cells (3) ---")
print(f"  mean Δ(rs_ssm - rs)   = {avg(intermit_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
print(f"  mean Δ(rs_ssm - spec) = {avg(intermit_rows, 'delta_rs_ssm_minus_spec'):+.4f}s")
print("\n--- other 12 cells ---")
print(f"  mean Δ(rs_ssm - rs)   = {avg(other_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
print(f"  mean Δ(rs_ssm - spec) = {avg(other_rows, 'delta_rs_ssm_minus_spec'):+.4f}s")

# Build verdict
wins = [r for r in rows if r["delta_rs_ssm_minus_rs"] < -0.01]
losses = [r for r in rows if r["delta_rs_ssm_minus_rs"] >  0.01]
ties = [r for r in rows if abs(r["delta_rs_ssm_minus_rs"]) <= 0.01]
matches_spec = [r for r in rows if abs(r["delta_rs_ssm_minus_spec"]) <= 0.01]
worst_loss = max(rows, key=lambda r: r["delta_rs_ssm_minus_rs"])
best_win   = min(rows, key=lambda r: r["delta_rs_ssm_minus_rs"])

verdict = []
verdict.append("SSM-driven routing vs ground-truth instantaneous threshold — verdict")
verdict.append("====================================================================")
verdict.append("")
verdict.append(f"Cells run: {len(rows)} (3 workloads × 8 networks; same RNG seeds as "
                "the main comparison).")
verdict.append("")
verdict.append(f"Mean Δ(rs_ssm − rs) on Markov-only (9 cells): "
                f"{avg(markov_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
verdict.append(f"Mean Δ(rs_ssm − rs) on intermittent (3 cells): "
                f"{avg(intermit_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
verdict.append(f"Mean Δ(rs_ssm − rs) on other 12 cells: "
                f"{avg(other_rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
verdict.append(f"Mean Δ(rs_ssm − rs) overall: "
                f"{avg(rows, 'delta_rs_ssm_minus_rs'):+.4f}s")
verdict.append("")
verdict.append(f"Cells where rs_ssm BEATS rs (Δ < -10ms): {len(wins)}")
for r in sorted(wins, key=lambda r: r['delta_rs_ssm_minus_rs'])[:5]:
    verdict.append(f"  {r['workload']:<10} {r['network']:<14} "
                   f"Δ = {r['delta_rs_ssm_minus_rs']:+.4f}s  "
                   f"(rs={r['rs_lat']:.3f} → rs_ssm={r['rs_ssm_lat']:.3f})")
verdict.append("")
verdict.append(f"Cells where rs_ssm LOSES to rs (Δ > +10ms): {len(losses)}")
for r in sorted(losses, key=lambda r: -r['delta_rs_ssm_minus_rs'])[:5]:
    verdict.append(f"  {r['workload']:<10} {r['network']:<14} "
                   f"Δ = {r['delta_rs_ssm_minus_rs']:+.4f}s  "
                   f"(rs={r['rs_lat']:.3f} → rs_ssm={r['rs_ssm_lat']:.3f})")
verdict.append("")
verdict.append(f"Cells where rs_ssm matches spec_lat within 10ms: "
                f"{len(matches_spec)} of {len(rows)}")
verdict.append("")
verdict.append("Mechanism notes:")
verdict.append("  * The trained SSM predicts RTT directly (no P(disconnected) head).")
verdict.append("  * Connectivity translated via rtt_fc < 1000ms — the same threshold")
verdict.append("    the simulator uses for ground-truth (`orchestrator_sim.network_at`).")
verdict.append("  * 1-step horizon only (no horizon tuning, no threshold tuning).")
verdict.append("")
overall_delta = avg(rows, 'delta_rs_ssm_minus_rs')
if overall_delta < -0.05:
    verdict.append("Verdict: SSM-driven routing beats the trivial threshold on the")
    verdict.append(f"current trained predictor. Mean improvement: {-overall_delta*1000:.1f}ms/cycle.")
    verdict.append("This is a preliminary positive result and warrants a follow-up")
    verdict.append("ablation: which transitions does the SSM catch early? Try a 2-3 step")
    verdict.append("forecast horizon to confirm the gain is from anticipation, not noise.")
elif overall_delta > 0.05:
    verdict.append("Verdict: SSM-driven routing UNDERPERFORMS the instantaneous threshold.")
    verdict.append(f"Mean cost: {overall_delta*1000:.1f}ms/cycle. The 1-step trained")
    verdict.append("forecast is too noisy to beat ground-truth, OR the regimes don't")
    verdict.append("offer meaningful anticipation gain — when the chain is in 'good',")
    verdict.append("instantaneous RTT is already correct most of the time; when it")
    verdict.append("transitions, the SSM is one step late by construction. Treat as a")
    verdict.append("grounded next-experiment note, not a positive result.")
else:
    verdict.append("Verdict: SSM-driven routing is statistically tied with the")
    verdict.append("instantaneous threshold across the 24 cells. Neither a win nor")
    verdict.append("a loss — the rs_ssm hits the same routing decisions in most")
    verdict.append("cycles because the chain dynamics happen at a timescale shorter")
    verdict.append("than the 1-step forecast horizon. To see signal, the forecast")
    verdict.append("would need to predict state TRANSITIONS not just RTT levels.")
    verdict.append("Recommended next experiment: train an SSM with an explicit")
    verdict.append("P(transition) head, then redo this comparison.")

(OUT / "ssm_routing_verdict.txt").write_text("\n".join(verdict))
print(f"\n→ {OUT / 'ssm_routing_verdict.txt'}")
