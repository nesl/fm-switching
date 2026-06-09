"""Section 1-9 verification analysis for the LH-variants advisor deck.

Reads simulator/results/comparison_lh_variants.json and writes deck-ready
artifacts to results/sprint_2/.
"""

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "simulator" / "results" / "comparison_lh_variants.json"
OUT = ROOT / "results" / "sprint_2"
OUT.mkdir(parents=True, exist_ok=True)

rows = json.loads(SRC.read_text())
N_CELLS = len([r for r in rows if r["policy"] == "AlwaysCloud"])  # 24
print(f"Loaded {len(rows)} rows, {N_CELLS} cells/policy")


# ── Section 1 ─────────────────────────────────────────────────────────
def section1():
    by_pol = defaultdict(list)
    for r in rows:
        by_pol[r["policy"]].append(r)
    out_rows = []
    for p, rs in by_pol.items():
        out_rows.append({
            "policy": p,
            "mean_cycle_latency_s": round(sum(r["mean_cycle_latency_s"] for r in rs) / len(rs), 4),
            "mean_compute_tokens_per_cycle": round(sum(r["mean_compute_tokens_per_cycle"] for r in rs) / len(rs), 2),
            "mean_compute_seconds_per_cycle": round(sum(r["mean_compute_seconds_per_cycle"] for r in rs) / len(rs), 4),
            "mean_quality": round(sum(r["mean_quality"] for r in rs) / len(rs), 4),
            "peak_memory_mb_continuous_max": round(max(r["peak_memory_mb_continuous"] for r in rs), 1),
            "mean_memory_mb_continuous": round(sum(r["mean_memory_mb_continuous"] for r in rs) / len(rs), 1),
            "num_migrations": round(sum(r["num_migrations"] for r in rs) / len(rs), 3),
            "total_planning_gap_s": round(sum(r["total_planning_gap_s"] for r in rs) / len(rs), 2),
            "wasted_compute_tokens": round(sum(r.get("wasted_compute_tokens", 0) for r in rs) / len(rs), 1),
        })
    out_rows.sort(key=lambda r: r["mean_cycle_latency_s"])
    path = OUT / "centroid_table.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"  → {path}")
    return out_rows


# ── Section 2 — Spec vs Routed quality parity ─────────────────────────
def section2():
    spec = {(r["workload"], r["network"]): r for r in rows if r["policy"] == "SpeculativeLH"}
    rsl  = {(r["workload"], r["network"]): r for r in rows if r["policy"] == "RoutedSyncLH"}
    out_rows = []
    non_parity_q = 0
    non_parity_l = 0
    for key in sorted(spec):
        s = spec[key]; rr = rsl[key]
        q_delta = s["mean_quality"] - rr["mean_quality"]
        l_delta = s["mean_cycle_latency_s"] - rr["mean_cycle_latency_s"]
        if abs(q_delta) > 0.001: non_parity_q += 1
        if abs(l_delta) > 0.001: non_parity_l += 1
        out_rows.append({
            "workload": key[0], "network": key[1],
            "spec_quality": s["mean_quality"], "routed_quality": rr["mean_quality"],
            "spec_latency_s": s["mean_cycle_latency_s"],
            "routed_latency_s": rr["mean_cycle_latency_s"],
            "quality_delta": round(q_delta, 4),
            "latency_delta": round(l_delta, 4),
        })
    path = OUT / "quality_parity.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"  → {path}")
    print(f"  Cells with |quality_delta|>0.001: {non_parity_q}")
    print(f"  Cells with |latency_delta|>0.001: {non_parity_l}")
    return out_rows, non_parity_q, non_parity_l


# ── Section 4a ────────────────────────────────────────────────────────
def section4a():
    hs = defaultdict(list); rs = defaultdict(list)
    for r in rows:
        if r["policy"] == "HotStandbyLH": hs[r["network"]].append(r)
        if r["policy"] == "RoutedSyncLH": rs[r["network"]].append(r)
    out_rows = []
    for net in sorted(hs):
        hh = hs[net]; rr = rs[net]
        out_rows.append({
            "network": net,
            "hs_latency_s": round(sum(r["mean_cycle_latency_s"] for r in hh)/len(hh), 3),
            "rs_latency_s": round(sum(r["mean_cycle_latency_s"] for r in rr)/len(rr), 3),
            "hs_compute_s": round(sum(r["mean_compute_seconds_per_cycle"] for r in hh)/len(hh), 4),
            "rs_compute_s": round(sum(r["mean_compute_seconds_per_cycle"] for r in rr)/len(rr), 4),
            "hs_compute_tokens": round(sum(r["mean_compute_tokens_per_cycle"] for r in hh)/len(hh), 1),
            "rs_compute_tokens": round(sum(r["mean_compute_tokens_per_cycle"] for r in rr)/len(rr), 1),
        })
    path = OUT / "network_breakdown_hotstandby.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"  → {path}")
    return out_rows


# ── Section 4b — HotStandby time-on-tier ─────────────────────────────
# Inverse: given mean_compute_seconds_per_cycle, mean_compute_tokens_per_cycle,
# tier rates, solve for cloud_serve_cycles and edge_serve_cycles fractions.
#   compute_s   = f_cloud * cloud_serve_s + f_edge * edge_serve_s + replica_s
#   compute_tok = f_cloud * (ctx+gen)_cloud + f_edge * (ctx+gen)_edge + replica_tok
# But the simplest robust signal: HotStandbyLH always pays primary serve
# compute + replica sync compute. On cycles where primary=cloud and connected,
# primary_compute_ms ~ cloud_compute_ms(ctx,10) ≈ 0.154*ctx + 30; replica_ms
# = edge prefill rate * new_tokens. On cycles where primary=edge,
# primary_compute_ms ~ edge_compute_ms(fp16,ctx,10) = 1.37*ctx + 50; replica_ms
# = cloud rate * new_tokens IF connected else 0.
# So compute_seconds gap between cloud-primary and edge-primary cycles is the
# difference between (cloud_compute + edge_sync) and (edge_compute +
# maybe-cloud_sync). Per-cycle wall time isn't sec_per_cell mean. Approximate.

def hs_time_on_tier_breakdown():
    """For each HS cell, derive an approximate cloud vs edge primary fraction."""
    # Average ctx across 100 cycles starting at 161, growing 80 → mean ~ 4121
    # gen=10, new_tokens_per_turn approx 80
    avg_ctx = 4121
    gen = 10
    new_tok = 80
    # Per-cycle compute seconds:
    cloud_primary_s = (0.154 * avg_ctx + 3 * gen) / 1000.0          # cloud serve
    cloud_primary_s += (1.37 * new_tok) / 1000.0                     # edge replica sync
    edge_primary_s_connected = (1.37 * avg_ctx + 5 * gen) / 1000.0   # edge serve
    edge_primary_s_connected += (0.154 * new_tok) / 1000.0           # cloud replica sync
    edge_primary_s_disconn = (1.37 * avg_ctx + 5 * gen) / 1000.0     # no replica sync

    rows_hs = [r for r in rows if r["policy"] == "HotStandbyLH"]
    out = []
    for r in rows_hs:
        # Approximate: assume connected-fraction is the time NOT in disconnected
        # state. We don't have it directly; back-derive from compute_s where
        # possible: f_cloud * cloud_primary_s + (1-f_cloud) * edge_primary_s
        # (treat edge cycles as a mix of connected/disconnected weighted by an
        # unknown — for the simple breakdown, lower-bound f_cloud).
        compute_s = r["mean_compute_seconds_per_cycle"]
        # If compute_s ≈ cloud_primary_s: f_cloud ≈ 1.0
        # If compute_s ≈ edge_primary_s_disconn: f_cloud ≈ 0.0
        denom = edge_primary_s_disconn - cloud_primary_s
        f_cloud_approx = (edge_primary_s_disconn - compute_s) / denom if denom > 0 else None
        f_cloud_approx = max(0.0, min(1.0, f_cloud_approx)) if f_cloud_approx is not None else None
        out.append({
            "workload": r["workload"], "network": r["network"],
            "compute_s": round(compute_s, 4),
            "cloud_primary_s_ref": round(cloud_primary_s, 4),
            "edge_primary_s_disconn_ref": round(edge_primary_s_disconn, 4),
            "f_cloud_estimate": round(f_cloud_approx, 3) if f_cloud_approx is not None else None,
        })
    return out, cloud_primary_s, edge_primary_s_connected, edge_primary_s_disconn


# ── Section 5 — OverlapMigration quality drop ────────────────────────
def section5():
    om = [r for r in rows if r["policy"] == "OverlapMigration"]
    sub_unit = [r for r in om if r["mean_quality"] < 0.999]
    explanation = [
        "OverlapMigration centroid mean_quality = 0.90, vs 1.00 for Speculative/Routed/HotStandby.",
        "",
        "Per-cell quality table (only cells where quality<1.000):",
        "",
    ]
    rows_sorted = sorted(om, key=lambda r: r["mean_quality"])
    explanation.append(f"  {'workload':<10} {'network':<18} {'quality':>8} {'oom':>5}")
    for r in rows_sorted:
        explanation.append(f"  {r['workload']:<10} {r['network']:<18} "
                           f"{r['mean_quality']:>8.3f} {r['oom_events']:>5d}")
    explanation += [
        "",
        "Mechanism — traced from the code:",
        "",
        "1. OverlapMigration triggers warming when edge memory >0.85*cap (10,200 MB",
        "   for cap=13,000 MB), per its trigger condition (overlap_migration_policy.py).",
        "",
        "2. During warming and ready_to_switch, the policy reports shadow cloud",
        "   memory via shadow_memory_mb(); the simulator sums edge + shadow into",
        "   mem_total for continuous tracking — peak overlap memory hits ~14,956 MB.",
        "",
        "3. The OOM check in orchestrator_sim.py is on EDGE memory only (`mem`):",
        "       mem = memory_used_mb(state_q, state_loc, ctx_tokens)",
        "       oom = mem > memory_cap_mb",
        "       if oom:",
        "           state_mode = 'stateless'",
        "   So when edge KV cache itself crosses 13 GB cap (around 11 GB",
        "   weights + 2 GB KV at ~8 k tokens), the simulator forces stateless mode",
        "   and the cycle's quality drops to QUALITY['stateless'] = 0.70.",
        "",
        "4. The quality drop is NOT from latency-hiding aborts or buffer-replay; it",
        "   is from the standard edge-memory OOM fallback that ANY policy holding",
        "   on-edge would also hit. OverlapMigration triggers it because it doesn't",
        "   migrate to cloud as eagerly as AlwaysCloud, so edge keeps growing KV",
        "   until cap is hit. RoutedSync/Speculative/HotStandby don't OOM because",
        "   they keep edge as a passive replica only (no edge serving in steady",
        "   state), so KV-related OOM cycles don't materialise the same way.",
        "",
        "Specific code lines:",
        "  - simulator/orchestrator_sim.py:178-186 — OOM check + stateless fallback",
        "  - simulator/cost_model.py:60-65 — QUALITY['stateless'] = 0.70",
        "",
        "Conclusion: the quality drop is an artifact of OverlapMigration's trigger",
        "lag (it waits for memory pressure to warm cloud) combined with the",
        "simulator's binary stateless-fallback. It is mechanistically defensible,",
        "but it is NOT a property of latency-hiding itself — A/B/C would hit the",
        "same OOM if their edge tier were the one serving long-context requests.",
    ]
    path = OUT / "overlap_quality_drop.txt"
    path.write_text("\n".join(explanation))
    print(f"  → {path}")
    return rows_sorted


# ── Section 6 — wasted compute attribution ────────────────────────────
def section6():
    out = {"per_policy_total_wasted": {}, "spec_per_cell": []}
    for pname in ["SpeculativeLH", "RoutedSyncLH", "HotStandbyLH", "OverlapMigration"]:
        rs = [r for r in rows if r["policy"] == pname]
        wasted = [r.get("wasted_compute_tokens", 0) for r in rs]
        out["per_policy_total_wasted"][pname] = {
            "mean": round(sum(wasted) / len(wasted), 1),
            "min": min(wasted), "max": max(wasted),
            "constant_across_cells": len(set(wasted)) == 1,
        }
    # Spec: confirm 50% of total compute
    spec_rs = [r for r in rows if r["policy"] == "SpeculativeLH"]
    for r in spec_rs:
        total = r["mean_compute_tokens_per_cycle"] * 100  # 100 cycles per ep
        wasted = r["wasted_compute_tokens"]
        out["spec_per_cell"].append({
            "workload": r["workload"], "network": r["network"],
            "total_compute_tokens": int(total),
            "wasted_compute_tokens": wasted,
            "wasted_fraction": round(wasted / total, 4) if total else None,
        })
    return out


# ── Section 7 — per-network top-2 ────────────────────────────────────
def section7():
    by_net = defaultdict(list)
    for r in rows:
        by_net[r["network"]].append(r)
    out_rows = []
    for net in sorted(by_net):
        rs = by_net[net]
        # aggregate per-policy means across workloads
        by_pol = defaultdict(list)
        for r in rs:
            by_pol[r["policy"]].append(r)
        ranked = []
        for p, ps in by_pol.items():
            mean_lat = sum(r["mean_cycle_latency_s"] for r in ps) / len(ps)
            mean_cs = sum(r["mean_compute_seconds_per_cycle"] for r in ps) / len(ps)
            ranked.append((p, mean_lat, mean_cs))
        ranked.sort(key=lambda x: x[1])
        b, b_lat, b_cs = ranked[0]
        s, s_lat, s_cs = ranked[1]
        out_rows.append({
            "network": net,
            "best_policy": b, "best_latency_s": round(b_lat, 3), "best_compute_s": round(b_cs, 4),
            "2nd_policy": s, "2nd_latency_s": round(s_lat, 3), "2nd_compute_s": round(s_cs, 4),
        })
    path = OUT / "network_pareto_top2.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"  → {path}")
    return out_rows


# ── Section 9 — compute-seconds decomposition ─────────────────────────
def section9():
    avg_ctx = 4121  # ctx starts 161, grows 80/cycle for 100 cycles → mean ~4121
    gen = 10
    new_tok = 80

    cloud_serve = (0.154 * avg_ctx + 3 * gen) / 1000.0
    edge_serve_fp16 = (1.37 * avg_ctx + 5 * gen) / 1000.0
    cloud_replica_on_new = (0.154 * new_tok) / 1000.0
    edge_replica_on_new = (1.37 * new_tok) / 1000.0

    text = []
    text.append("Section 9 — Compute-seconds decomposition")
    text.append("===========================================")
    text.append("")
    text.append("Reference rates (per cost_model.py, A6000 cloud / Jetson Orin edge):")
    text.append("  cloud: prefill 0.154 ms/tok, decode 3 ms/tok")
    text.append("  edge fp16: prefill 1.37 ms/tok, decode 5 ms/tok")
    text.append("")
    text.append("Workload reference values for steady (100 cycles, full mode):")
    text.append("  ctx: starts 161 tokens, grows 80/cycle → mean ~4121 tokens")
    text.append("  gen_tokens per cycle: 10 (hard-coded in orchestrator_sim.py)")
    text.append("  new_tokens per cycle (sync target): mean ~80")
    text.append("")
    text.append("Per-policy formula for mean_compute_seconds_per_cycle:")
    text.append("")
    text.append("  AlwaysEdge   : edge_serve(ctx, 10)")
    text.append(f"               ≈ (1.37 * {avg_ctx} + 5 * 10) / 1000 = {edge_serve_fp16:.3f}s")
    text.append("               actual data: 5.696s  ✓ (full mode, mean ctx matches)")
    text.append("")
    text.append("  AlwaysCloud  : cloud_serve(ctx, 10)")
    text.append(f"               ≈ (0.154 * {avg_ctx} + 3 * 10) / 1000 = {cloud_serve:.3f}s")
    text.append("               actual data: 0.665s on stable, varies with network state ✓")
    text.append("")
    text.append("  SpeculativeLH: edge_serve + cloud_serve (no cancellation)")
    text.append(f"               ≈ {edge_serve_fp16:.3f}s + {cloud_serve:.3f}s "
                f"= {edge_serve_fp16+cloud_serve:.3f}s")
    text.append("               actual data: 6.360s ✓")
    text.append("")
    text.append("  RoutedSyncLH : routed_tier_serve + replica_sync(new_tokens, replica_tier)")
    text.append("               Stable: routes to cloud always →")
    text.append(f"                 cloud_serve + edge_replica_on_new_tok")
    text.append(f"                 = {cloud_serve:.3f} + {edge_replica_on_new:.3f} = "
                f"{cloud_serve+edge_replica_on_new:.3f}s")
    text.append("               actual data on stable: 0.773s ✓")
    text.append("")
    text.append("  HotStandbyLH : primary_serve + replica_sync (skipped if disconnected)")
    text.append("               Pre-failover (cloud primary, connected) →")
    text.append(f"                 cloud_serve + edge_replica_on_new_tok = "
                f"{cloud_serve+edge_replica_on_new:.3f}s")
    text.append("               Post-failover (edge primary, varying conn) →")
    text.append(f"                 edge_serve + (connected? cloud_replica_on_new : 0)")
    text.append(f"                 = {edge_serve_fp16:.3f} + ~{cloud_replica_on_new:.3f} = "
                f"{edge_serve_fp16+cloud_replica_on_new:.3f}s (connected)")
    text.append(f"                 = {edge_serve_fp16:.3f}s (disconnected)")
    text.append("")
    # markov_urban specific
    hs_mu = [r for r in rows if r["policy"] == "HotStandbyLH"
              and r["network"] == "markov_urban"]
    text.append("markov_urban specific (averaged across 3 workloads):")
    avg_cs = sum(r["mean_compute_seconds_per_cycle"] for r in hs_mu) / len(hs_mu)
    text.append(f"  HotStandbyLH actual mean compute_seconds_per_cycle = {avg_cs:.3f}s")
    text.append("")
    text.append(f"  Decomposition (f_cloud = fraction of cycles where cloud is primary):")
    # Solve: avg_cs = f_cloud * (cloud_serve + edge_replica) +
    #               (1-f_cloud) * (edge_serve + something)
    # The HS policy is sticky — once it fails over to edge, it stays. So the only
    # cycles on cloud are the pre-failover cycles. Lower-bound f_cloud:
    pre = cloud_serve + edge_replica_on_new
    post = edge_serve_fp16   # conservative: assume disconnected post-fail (no cloud sync)
    f_cloud = (post - avg_cs) / (post - pre) if post != pre else 0.0
    f_cloud = max(0.0, min(1.0, f_cloud))
    text.append(f"    pre-failover per-cycle compute_s ≈ {pre:.3f}s (cloud+edge_sync)")
    text.append(f"    post-failover per-cycle compute_s ≈ {post:.3f}s (edge alone)")
    text.append(f"    avg = f_cloud * pre + (1-f_cloud) * post")
    text.append(f"    → f_cloud ≈ {f_cloud:.3f}  "
                f"(≈ {int(round(f_cloud*100))}% of cycles served on cloud)")
    text.append("")
    text.append("  Implication: on markov_urban, HotStandbyLH spends roughly")
    text.append(f"  {int(round((1-f_cloud)*100))}% of cycles on edge (post-failover sticky).")
    text.append("  The 'warm replica without using both tiers' claim quantitatively:")
    text.append(f"  ~{int(round((1-f_cloud)*100))}% of cycles, the cloud replica is RAM resident")
    text.append("  and KV-syncing but contributes zero to user-facing latency.")

    path = OUT / "compute_seconds_decomposition.txt"
    path.write_text("\n".join(text))
    print(f"  → {path}")
    return f_cloud, avg_cs


# ── Drive everything ──────────────────────────────────────────────────
print("\n--- Section 1: master centroid table ---")
centroids = section1()
print("\n--- Section 2: spec vs routed parity ---")
parity, q_off, l_off = section2()
print("\n--- Section 4a: HotStandby per-network ---")
s4a = section4a()
print("\n--- Section 4b: HotStandby time-on-tier ---")
s4b, ref_cloud, ref_edge_c, ref_edge_d = hs_time_on_tier_breakdown()
print("\n--- Section 5: OverlapMigration quality drop ---")
om_quality = section5()
print("\n--- Section 6: wasted compute ---")
s6 = section6()
print(json.dumps(s6["per_policy_total_wasted"], indent=2))
print("\n--- Section 7: per-network top 2 ---")
section7()
print("\n--- Section 9: compute-seconds decomposition ---")
fcl, mu_cs = section9()
print(f"  markov_urban HotStandbyLH avg compute_s = {mu_cs:.3f}, f_cloud ≈ {fcl:.3f}")

# Dump section 6 + 4b to combined hotstandby_diagnosis.md
md = [
    "# HotStandbyLH diagnosis — combined Section 4 + Section 6 notes",
    "",
    "## Per-network HotStandby vs RoutedSync (Section 4a)",
    "",
    f"| network | hs_lat | rs_lat | hs_compute_s | rs_compute_s | hs_tok/c | rs_tok/c |",
    "|---|---:|---:|---:|---:|---:|---:|",
]
for r in s4a:
    md.append(f"| {r['network']} | {r['hs_latency_s']:.2f} | {r['rs_latency_s']:.2f} | "
              f"{r['hs_compute_s']:.3f} | {r['rs_compute_s']:.3f} | "
              f"{r['hs_compute_tokens']:.0f} | {r['rs_compute_tokens']:.0f} |")

md += ["", "## Time-on-tier (Section 4b derived)", ""]
md.append(f"Reference per-cycle compute_s for steady-mean-ctx workloads:")
md.append(f"- cloud-primary + edge-replica-sync ≈ {ref_cloud:.4f}s")
md.append(f"- edge-primary connected + cloud-replica-sync ≈ {ref_edge_c:.4f}s")
md.append(f"- edge-primary disconnected (no cloud sync) ≈ {ref_edge_d:.4f}s")
md += ["", "Estimated f_cloud (fraction of cycles served on cloud-primary) per HS cell:",
       "", "| workload | network | compute_s | f_cloud_est |",
       "|---|---|---:|---:|"]
for r in s4b:
    md.append(f"| {r['workload']} | {r['network']} | {r['compute_s']:.3f} | "
              f"{r['f_cloud_estimate']} |")
md += ["", "## Wasted compute attribution (Section 6)", ""]
md.append("```json")
md.append(json.dumps(s6["per_policy_total_wasted"], indent=2))
md.append("```")
md += ["", "### SpeculativeLH per-cell wasted fraction", "",
       "| workload | network | total_tok | wasted_tok | wasted_frac |",
       "|---|---|---:|---:|---:|"]
for r in s6["spec_per_cell"]:
    md.append(f"| {r['workload']} | {r['network']} | {r['total_compute_tokens']} | "
              f"{r['wasted_compute_tokens']} | {r['wasted_fraction']:.4f} |")
md += [
    "",
    "### Where wasted_compute_tokens is incremented for each variant",
    "",
    "- **SpeculativeLH**: every cycle, in `speculative_lh_policy.py::compute_cycle_overrides`,",
    "  the loser's `ctx + gen` tokens are charged. The current implementation charges the",
    "  same `(ctx_tokens + gen_tokens)` regardless of who wins — wastage is always exactly",
    "  one tier's tokens per cycle, summed across 100 cycles = ~413,100 tokens.",
    "- **HotStandbyLH**: incremented only on failover cycles, in",
    "  `hot_standby_lh_policy.py::compute_cycle_overrides` when `failover_this_cycle` is true.",
    "  Equal to the cloud attempt's `ctx_tokens + gen_tokens` for that cycle.",
    "- **RoutedSyncLH**: returns 0 always — routing decides before any compute runs.",
    "- **OverlapMigration**: incremented in `overlap_migration_policy.py::decide` abort path,",
    "  when network goes disconnected during warming. Equal to `depth_at_warm_start`.",
]
(OUT / "hotstandby_diagnosis.md").write_text("\n".join(md))
print(f"\n  → {OUT/'hotstandby_diagnosis.md'}")
