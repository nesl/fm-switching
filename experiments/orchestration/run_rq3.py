"""
RQ3 ablation: placement-only vs rep-only vs joint, with compressibility sensitivity.

Grid:
  delta        : {0.0, 0.05, 0.10, 0.20}  — quality(summary/window) = quality(full) - delta
  memory_cap   : {abundant=13000, pressured=10800}
  mobility     : {campus, urban, harsh}
  policies     : {ContinuousCopy, InertiaBlindAdaptive, PlaceOnly, RepOnly, JointInertia}
  seeds        : {0,1,2,3,4}

600 runs total. SLO threshold: 15 s/cycle.

Output: results/rq3_ablation.json

PART C reports:
  1. INERTIA BINDING: per-policy per-regime, cumulative edge re-prefill seconds paid.
  2. MEASURED vs FLAT: PlaceOnly (inertia_ms) vs InertiaBlindAdaptive (linear) decision divergence.
  3. JOINT WIN ATTRIBUTION: inertia management vs cloud-speed advantage.
"""

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

_SIM = Path(__file__).resolve().parent.parent.parent / "simulator"
sys.path.insert(0, str(_SIM.parent / "experiments" / "lib"))
sys.path.insert(0, str(_SIM))

from _provenance import stamp
from cost_model import FP16, QUALITY as _BASE_QUALITY
from markov_network import sample_trace
from orchestrator_sim import run_episode
from rq3_policies import (
    ContinuousCopy, InertiaBlindAdaptive, PlaceOnly, RepOnly, JointInertia,
)

# ── Experiment axes ────────────────────────────────────────────────────────
DELTAS      = [0.0, 0.05, 0.10, 0.20]
MEMORY_CAPS = {"abundant": 13_000, "pressured": 10_800}
MOBILITY    = ["campus", "urban", "harsh"]
SEEDS       = [0, 1, 2, 3, 4]
N_CYCLES    = 60
N_SECONDS   = 720
SLO_S       = 15.0    # per-cycle latency threshold for SLO violation

_FULL_Q = _BASE_QUALITY["full"]   # 0.384 — anchor; never adjusted by delta


def _make_quality(delta: float) -> dict:
    """
    Sensitivity parameterisation: delta = quality(full) - quality(compressed).
    At delta=0 (EgoSchema anchor): compressed modes ≈ full (summary-80 even
    slightly better at 0.388; we use full_q - 0 = full_q as the sweep reference).
    At delta>0: summary and window quality degraded relative to full.
    stateless and blind are left at measured values (they're the floor).
    """
    q = dict(_BASE_QUALITY)
    for m in ("summary-80", "summary-200", "window-3", "window-10"):
        q[m] = max(0.0, _FULL_Q - delta)
    return q


def _make_workload(seed: int, n: int) -> list:
    rng = random.Random(seed + 9999)
    mu    = math.log(FP16["vlm_mean_s"])
    sigma = (math.log(FP16["vlm_max_s"]) - math.log(FP16["vlm_min_s"])) / 3.0
    return [{"cycle": i,
             "vlm_latency_s": max(FP16["vlm_min_s"],
                                   min(FP16["vlm_max_s"],
                                       math.exp(rng.gauss(mu, sigma))))}
            for i in range(n)]


def _policy_factory(name: str, quality: dict):
    if name == "ContinuousCopy":       return ContinuousCopy()
    if name == "InertiaBlindAdaptive": return InertiaBlindAdaptive()
    if name == "PlaceOnly":            return PlaceOnly()
    if name == "RepOnly":              return RepOnly(quality=quality)
    if name == "JointInertia":         return JointInertia(quality=quality)
    raise ValueError(name)


POLICY_NAMES = ["ContinuousCopy", "InertiaBlindAdaptive", "PlaceOnly",
                "RepOnly", "JointInertia"]


def _run_one(policy_name, mobility, cap, seed, quality):
    net = sample_trace(mobility, n_seconds=N_SECONDS, seed=seed)
    wl  = _make_workload(seed, N_CYCLES)
    pol = _policy_factory(policy_name, quality)
    m   = run_episode(wl, net, pol, memory_cap_mb=cap, quality_override=quality)
    slo_viols = sum(1 for c in m.cycles if c.cycle_total_s > SLO_S)
    mob_fails = m.cloud_failure_events
    return {
        "mean_latency_s":            round(m.mean_cycle_latency_s, 4),
        "std_latency_s":             round(
            math.sqrt(sum((c.cycle_total_s - m.mean_cycle_latency_s)**2
                          for c in m.cycles) / max(1, len(m.cycles))), 4),
        "mean_quality":              round(m.mean_quality, 4),
        "slo_viol_rate":             round(slo_viols / N_CYCLES, 4),
        "oom_events":                m.oom_events,
        "num_migrations":            m.num_migrations,
        "mob_failures":              mob_fails,
        "peak_mem_mb":               round(m.peak_memory_mb_continuous, 1),
        "cloud_failure_reprefill_s": round(m.cloud_failure_reprefill_s, 3),
        "mode_switch_reprefill_s":   round(m.mode_switch_reprefill_s, 3),
        "total_reprefill_s":         round(m.cloud_failure_reprefill_s + m.mode_switch_reprefill_s, 3),
    }


def main():
    total = len(DELTAS) * len(MEMORY_CAPS) * len(MOBILITY) * len(POLICY_NAMES) * len(SEEDS)
    runs  = []
    done  = 0

    for delta in DELTAS:
        quality = _make_quality(delta)
        for cap_label, cap in MEMORY_CAPS.items():
            for mobility in MOBILITY:
                for policy_name in POLICY_NAMES:
                    seed_rows = []
                    for seed in SEEDS:
                        r = _run_one(policy_name, mobility, cap, seed, quality)
                        seed_rows.append(r)
                        done += 1
                    runs.append({
                        "delta": delta,
                        "cap_label": cap_label,
                        "memory_cap_mb": cap,
                        "mobility": mobility,
                        "policy": policy_name,
                        "seeds": seed_rows,
                    })
                    if done % 60 == 0 or done == total:
                        avg_lat = sum(r["mean_latency_s"] for r in seed_rows) / len(seed_rows)
                        avg_q   = sum(r["mean_quality"]   for r in seed_rows) / len(seed_rows)
                        avg_rp  = sum(r["total_reprefill_s"] for r in seed_rows) / len(seed_rows)
                        print(f"  {done}/{total}  δ={delta} {cap_label} {mobility}"
                              f" {policy_name}  lat={avg_lat:.3f}s q={avg_q:.3f} reprefill={avg_rp:.2f}s")

    # ── Aggregate: mean±std over seeds ────────────────────────────────────
    def _agg(seed_rows, key):
        vals = [r[key] for r in seed_rows]
        mu   = sum(vals) / len(vals)
        std  = math.sqrt(sum((v - mu)**2 for v in vals) / len(vals))
        return round(mu, 4), round(std, 4)

    summary = {}
    for row in runs:
        k = f"{row['delta']}|{row['cap_label']}|{row['mobility']}|{row['policy']}"
        sr = row["seeds"]
        summary[k] = {
            "mean_latency_s":            _agg(sr, "mean_latency_s"),
            "mean_quality":              _agg(sr, "mean_quality"),
            "slo_viol_rate":             _agg(sr, "slo_viol_rate"),
            "oom_events":                _agg(sr, "oom_events"),
            "num_migrations":            _agg(sr, "num_migrations"),
            "mob_failures":              _agg(sr, "mob_failures"),
            "cloud_failure_reprefill_s": _agg(sr, "cloud_failure_reprefill_s"),
            "mode_switch_reprefill_s":   _agg(sr, "mode_switch_reprefill_s"),
            "total_reprefill_s":         _agg(sr, "total_reprefill_s"),
        }

    # ── INVARIANT CHECK: Joint <= RepOnly + 0.5s in every cell ────────────
    print("\n" + "=" * 80)
    print("INVARIANT CHECK: JointInertia mean latency <= RepOnly + 0.5s in every cell")
    print("=" * 80)
    invariant_ok = True
    NOISE = 0.5
    fails = []
    for delta in DELTAS:
        for cap_label in MEMORY_CAPS:
            for mobility in MOBILITY:
                kj = f"{delta}|{cap_label}|{mobility}|JointInertia"
                kr = f"{delta}|{cap_label}|{mobility}|RepOnly"
                if kj not in summary or kr not in summary:
                    continue
                lat_j = summary[kj]["mean_latency_s"][0]
                lat_r = summary[kr]["mean_latency_s"][0]
                diff  = lat_j - lat_r
                if diff > NOISE:
                    invariant_ok = False
                    fails.append((delta, cap_label, mobility, lat_j, lat_r, diff))
                    print(f"  FAIL  δ={delta} {cap_label} {mobility}: "
                          f"Joint={lat_j:.4f}s  RepOnly={lat_r:.4f}s  Δ=+{diff:.4f}s")

    if invariant_ok:
        print("  PASS — JointInertia is competitive with RepOnly in all cells.")
    else:
        print(f"\n  {len(fails)} cell(s) failed the invariant.")
        print("  This is a cost-model bug, NOT a finding. Stopping before phase analysis.")
        _write_and_exit(runs, summary, invariant_ok, fails)
        return

    # ── Phase structure table ─────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("REGIME TABLE  mean_latency_s (mean_quality)  [slo_viol_rate]")
    print("delta=0 is EgoSchema anchor (summary≈full); higher delta = more compressible penalty")
    print("=" * 80)

    for mobility in MOBILITY:
        for cap_label in MEMORY_CAPS:
            print(f"\n  [{mobility.upper()}  cap={cap_label}]")
            hdr = f"  {'Policy':<26}" + "".join(f"  δ={d:<5}" for d in DELTAS)
            print(hdr)
            print("  " + "-" * 74)
            for policy_name in POLICY_NAMES:
                row_s = f"  {policy_name:<26}"
                for delta in DELTAS:
                    k = f"{delta}|{cap_label}|{mobility}|{policy_name}"
                    if k in summary:
                        lat, _ = summary[k]["mean_latency_s"]
                        q, _   = summary[k]["mean_quality"]
                        row_s += f"  {lat:.3f}s q={q:.3f}"
                    else:
                        row_s += "  —"
                print(row_s)

    def lat(policy, delta, cap_label, mobility):
        k = f"{delta}|{cap_label}|{mobility}|{policy}"
        return summary.get(k, {}).get("mean_latency_s", (None, None))[0]

    def reprefill(policy, delta, cap_label, mobility):
        k = f"{delta}|{cap_label}|{mobility}|{policy}"
        return summary.get(k, {}).get("total_reprefill_s", (None, None))[0]

    def cf_reprefill(policy, delta, cap_label, mobility):
        k = f"{delta}|{cap_label}|{mobility}|{policy}"
        return summary.get(k, {}).get("cloud_failure_reprefill_s", (None, None))[0]

    def ms_reprefill(policy, delta, cap_label, mobility):
        k = f"{delta}|{cap_label}|{mobility}|{policy}"
        return summary.get(k, {}).get("mode_switch_reprefill_s", (None, None))[0]

    # ── PART C-1: DOES INERTIA BIND? ──────────────────────────────────────
    # Report cumulative edge re-prefill seconds per policy per regime.
    # "Bind" = re-prefill cost is non-trivial (> 5s across 60-cycle episode)
    # relative to VLM+LLM latency floor of ~10s/cycle × 60 = 600s.
    print("\n" + "=" * 80)
    print("PART C-1: DOES INERTIA BIND?")
    print("  Cumulative edge re-prefill seconds paid per episode (mean over seeds)")
    print("  Breakdown: cloud_failure_reprefill_s | mode_switch_reprefill_s | total")
    print("  'Binds' if total > 5s over 60 cycles (>1% of total episode time floor)")
    print("=" * 80)

    for mobility in MOBILITY:
        print(f"\n  [{mobility.upper()}]  δ=0.10  cap=pressured")
        print(f"  {'Policy':<26}  {'CF-reprefill':>12}  {'MS-reprefill':>12}  {'Total':>8}  {'Binds?':>7}")
        print("  " + "-" * 70)
        delta_show = 0.10
        cap_show = "pressured"
        for policy_name in POLICY_NAMES:
            cf = cf_reprefill(policy_name, delta_show, cap_show, mobility)
            ms = ms_reprefill(policy_name, delta_show, cap_show, mobility)
            tot = reprefill(policy_name, delta_show, cap_show, mobility)
            if cf is None:
                continue
            binds = "YES" if tot > 5.0 else "no"
            print(f"  {policy_name:<26}  {cf:>12.3f}s  {ms:>12.3f}s  {tot:>8.3f}s  {binds:>7}")

    # Also show how re-prefill scales with mobility (campus vs urban vs harsh):
    print("\n  RE-PREFILL vs MOBILITY (PlaceOnly, δ=0.10, pressured):")
    print(f"  {'Mobility':<12}  {'CF-reprefill':>12}  {'MS-reprefill':>12}  {'Total':>8}")
    print("  " + "-" * 50)
    for mob in MOBILITY:
        cf = cf_reprefill("PlaceOnly", 0.10, "pressured", mob)
        ms = ms_reprefill("PlaceOnly", 0.10, "pressured", mob)
        tot = reprefill("PlaceOnly", 0.10, "pressured", mob)
        if cf is not None:
            print(f"  {mob:<12}  {cf:>12.3f}s  {ms:>12.3f}s  {tot:>8.3f}s")

    # ── PART C-2: DOES MEASURED INERTIA DIVERGE FROM FLAT? ────────────────
    print("\n" + "=" * 80)
    print("PART C-2: DOES MEASURED INERTIA DIVERGE FROM FLAT?")
    print("  PlaceOnly (inertia_ms — measured curve) vs InertiaBlindAdaptive (linear cost)")
    print("  If measured curves matter, PlaceOnly should differ from InertiaBlind in harsh/deep ctx.")
    print("=" * 80)

    print(f"\n  {'Setting':<34}  {'PlaceOnly':>10}  {'InertBlind':>10}  {'Δlat':>8}  {'Verdict':>12}")
    print("  " + "-" * 78)
    for mob in MOBILITY:
        for cap_label in ["pressured", "abundant"]:
            for delta in [0.0, 0.10, 0.20]:
                lpo = lat("PlaceOnly", delta, cap_label, mob)
                lib = lat("InertiaBlindAdaptive", delta, cap_label, mob)
                if lpo is None or lib is None:
                    continue
                diff = lpo - lib
                if abs(diff) < 0.01:
                    verdict = "IDENTICAL"
                elif diff < -0.05:
                    verdict = "PLACE<BLIND"
                elif diff > 0.05:
                    verdict = "BLIND<PLACE"
                else:
                    verdict = "near-tie"
                setting = f"{mob}/{cap_label}/δ={delta}"
                print(f"  {setting:<34}  {lpo:>10.4f}s  {lib:>10.4f}s  {diff:>+8.4f}s  {verdict:>12}")

    # Summarize divergence count:
    n_diverge = 0
    n_total_c2 = 0
    for mob in MOBILITY:
        for cap_label in MEMORY_CAPS:
            for delta in DELTAS:
                lpo = lat("PlaceOnly", delta, cap_label, mob)
                lib = lat("InertiaBlindAdaptive", delta, cap_label, mob)
                if lpo is None or lib is None:
                    continue
                n_total_c2 += 1
                if abs(lpo - lib) > 0.05:
                    n_diverge += 1
    print(f"\n  Summary: {n_diverge}/{n_total_c2} cells diverge by >0.05s.")
    if n_diverge == 0:
        print("  FINDING: Measured inertia curve makes NO difference vs flat/linear model.")
        print("  Edge re-prefill is sub-linear enough that the linear overestimate doesn't")
        print("  change placement decisions. Inertia curve shape is irrelevant in this regime.")
    else:
        print(f"  FINDING: Measured vs flat diverges in {n_diverge} cell(s) — "
              "inertia curve shape affects decisions.")

    # ── PART C-3: WHERE DOES JOINT WIN COME FROM? ─────────────────────────
    print("\n" + "=" * 80)
    print("PART C-3: WHERE DOES JOINT WIN COME FROM?")
    print("  Isolate: inertia management (bounded re-prefill on forced returns)")
    print("          vs cloud-speed advantage (staying cloud longer)")
    print()
    print("  Proxy: compare JointInertia re-prefill vs RepOnly re-prefill.")
    print("  If Joint pays LESS re-prefill than RepOnly → inertia management.")
    print("  If Joint pays SAME re-prefill but wins on latency → cloud-speed advantage.")
    print("  If Joint and RepOnly have identical re-prefill → purely cloud-speed.")
    print("=" * 80)

    print(f"\n  {'Setting':<34}  {'Joint_lat':>9}  {'Rep_lat':>9}  {'Δlat':>7}  "
          f"{'Joint_rp':>8}  {'Rep_rp':>8}  {'Δrp':>7}  {'Attribution':>20}")
    print("  " + "-" * 110)
    for mob in MOBILITY:
        for cap_label in ["pressured", "abundant"]:
            for delta in [0.0, 0.10, 0.20]:
                lj = lat("JointInertia", delta, cap_label, mob)
                lr = lat("RepOnly",      delta, cap_label, mob)
                rj = reprefill("JointInertia", delta, cap_label, mob)
                rr = reprefill("RepOnly",      delta, cap_label, mob)
                if lj is None or lr is None:
                    continue
                lat_diff = lj - lr
                rp_diff  = rj - rr if (rj is not None and rr is not None) else None
                if lat_diff > -0.05:
                    attribution = "no win"
                elif rp_diff is not None and rp_diff < -1.0:
                    attribution = "inertia mgmt"
                elif rp_diff is not None and abs(rp_diff) < 0.5:
                    attribution = "cloud-speed"
                else:
                    attribution = "mixed"
                rj_str = f"{rj:.3f}s" if rj is not None else "—"
                rr_str = f"{rr:.3f}s" if rr is not None else "—"
                rp_str = f"{rp_diff:+.3f}s" if rp_diff is not None else "—"
                setting = f"{mob}/{cap_label}/δ={delta}"
                print(f"  {setting:<34}  {lj:>9.4f}s  {lr:>9.4f}s  {lat_diff:>+7.4f}s  "
                      f"{rj_str:>8}  {rr_str:>8}  {rp_str:>7}  {attribution:>20}")

    # ── Three decisive comparisons (original) ─────────────────────────────
    print("\n" + "=" * 80)
    print("DECISIVE COMPARISONS (pressured/harsh — stress regime)")
    print("=" * 80)

    for delta in DELTAS:
        lj = lat("JointInertia", delta, "pressured", "harsh")
        lr = lat("RepOnly",      delta, "pressured", "harsh")
        lp = lat("PlaceOnly",    delta, "pressured", "harsh")
        if lj is None or lr is None or lp is None:
            continue
        j_vs_r = "WINS" if lj < lr - 0.05 else ("TIE" if abs(lj - lr) <= 0.05 else "LOSES")
        j_vs_p = "WINS" if lj < lp - 0.05 else ("TIE" if abs(lj - lp) <= 0.05 else "LOSES")
        both   = lj < lr - 0.05 and lj < lp - 0.05
        print(f"\n  δ={delta}  pressured/harsh:")
        print(f"    Joint={lj:.4f}s  RepOnly={lr:.4f}s  PlaceOnly={lp:.4f}s")
        print(f"    Joint vs RepOnly: {j_vs_r}  |  Joint vs PlaceOnly: {j_vs_p}")
        print(f"    Joint beats BOTH: {'YES' if both else 'NO'}")

    # ── Phase boundary summary ─────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PHASE BOUNDARY (where does Joint beat both RepOnly and PlaceOnly?)")
    print("=" * 80)
    any_both = False
    for delta in DELTAS:
        for cap_label in MEMORY_CAPS:
            for mobility in MOBILITY:
                lj = lat("JointInertia", delta, cap_label, mobility)
                lr = lat("RepOnly",      delta, cap_label, mobility)
                lp = lat("PlaceOnly",    delta, cap_label, mobility)
                if lj and lr and lp and lj < lr - 0.05 and lj < lp - 0.05:
                    print(f"  JOINT WINS BOTH: δ={delta} {cap_label}/{mobility}"
                          f" — lat={lj:.4f}s vs rep={lr:.4f}s place={lp:.4f}s")
                    any_both = True
    if not any_both:
        print("  Joint never beats BOTH simultaneously across the grid.")
        print("  (This is a genuine finding, not a bug — invariant passed above.)")

    _write_and_exit(runs, summary, invariant_ok, fails)


def _write_and_exit(runs, summary, invariant_ok, fails):
    prov = stamp(script="run_rq3.py", model="smollm2", device="a6000",
                 n=sum(len(r["seeds"]) for r in runs), args=None)
    out = {
        "config": {
            "deltas": DELTAS,
            "memory_caps": MEMORY_CAPS,
            "mobility": MOBILITY,
            "seeds": SEEDS,
            "n_cycles": N_CYCLES,
            "slo_threshold_s": SLO_S,
        },
        "runs":           runs,
        "summary":        summary,
        "invariant_ok":   invariant_ok,
        "invariant_fails": [{"delta": f[0], "cap_label": f[1], "mobility": f[2],
                              "lat_joint": f[3], "lat_reponly": f[4], "diff": f[5]}
                             for f in fails],
        "_provenance":    prov,
    }
    out_path = Path(__file__).resolve().parent.parent / "results" / "rq3_ablation.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
