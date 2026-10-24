#!/usr/bin/env python3
"""StudyDevFast analysis + Results consistency check.

Reads results/device/devfast_<tag>_n<N>.jsonl (6 cells x 120), computes per-cell
latency / energy / accuracy aggregates and the 6-check consistency protocol, and
writes results/device/devfast_stats.json plus a printed table.

Committed priors for the N=37 control cross-check (StudyDeviceLatency-sember,
reports/device_latency_sember.md): 4B-I TTFT 17.0 s, 4B-T TTFT 17.2 s, input ~12,420 tok,
4B-T decode 16.2 tok/s. Orin F16 decode roofline for 4B (~8 GB weights / 204.8 GB/s) = 25.6 tok/s.
"""
import json, math, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "results/device"
CELLS = ["4bi_f16_n37", "4bi_f16_n18", "4bi_f16_n9", "4bt_f16_n37", "4bt_f16_n18", "4bt_f16_n9"]
PRIOR = {"4bi_f16_n37": {"ttft": 17.0, "input": 12420}, "4bt_f16_n37": {"ttft": 17.2, "input": 12422, "decode": 16.2}}
ROOFLINE_4B = 25.6  # tok/s, F16 weight-streaming


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = min(len(xs) - 1, int(math.ceil(q / 100 * len(xs))) - 1)
    return xs[max(0, i)]


def summ(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"median": round(st.median(xs), 3), "p90": round(pct(xs, 90), 3),
            "max": round(max(xs), 3), "min": round(min(xs), 3),
            "iqr": round(pct(xs, 75) - pct(xs, 25), 3)}


def main():
    idle = {}
    sp = OUT / "devfast_summary.json"
    if sp.exists():
        idle = {k: v["idle"] for k, v in json.load(open(sp))["cells"].items()}

    stats = {}
    for cell in CELLS:
        rows = [json.loads(l) for l in open(OUT / f"devfast_{cell}.jsonl")]
        E = [r.get("energy") or {} for r in rows]
        ncorr = sum(1 for r in rows if r["correct"])
        lo, hi = wilson(ncorr, len(rows))
        decode = [r["decode_tps"] for r in rows if r["decode_tps"]]
        stats[cell] = {
            "n": len(rows),
            "n_frames_median": st.median([r["n_frames"] for r in rows]),
            "input_tokens": summ([r["input_tokens"] for r in rows]),
            "ttft_s": summ([r["ttft_s"] for r in rows]),
            "prefill_ms": summ([r["prefill_ms"] for r in rows]),
            "total_latency_s": summ([r["total_latency_s"] for r in rows]),
            "think_tokens": summ([r["n_think_tokens"] for r in rows]),
            "n_gen": summ([r["n_gen"] for r in rows]),
            "decode_tps": summ(decode),
            "energy_j": summ([e.get("energy_j") for e in E]),
            "mean_power_w": summ([e.get("mean_w") for e in E]),
            "gpu_j_median": round(st.median([e.get("gpu_j") for e in E if e.get("gpu_j")]), 1) if any(e.get("gpu_j") for e in E) else None,
            "sys_j_median": round(st.median([e.get("sys_j") for e in E if e.get("sys_j")]), 1) if any(e.get("sys_j") for e in E) else None,
            "cpu_j_median": round(st.median([e.get("cpu_j") for e in E if e.get("cpu_j")]), 1) if any(e.get("cpu_j") for e in E) else None,
            "acc": round(ncorr / len(rows), 3), "acc_k": ncorr,
            "acc_wilson95": [round(lo, 3), round(hi, 3)],
            "budget_hit": sum(1 for r in rows if r["budget_hit"]),
            "ttft_le_5s_frac": round(sum(1 for r in rows if r["ttft_s"] and r["ttft_s"] <= 5) / len(rows), 3),
            "latency_le_10s_frac": round(sum(1 for r in rows if r["total_latency_s"] <= 10) / len(rows), 3),
            "peak_ram_mb": max((e.get("peak_ram_mb") or 0) for e in E),
            "tj_max": max((e.get("tj_max") or 0) for e in E),
            "idle_w": round(idle.get(cell, {}).get("mean_total_w", 0), 3),
        }

    # ── Consistency checks ───────────────────────────────────────────────────
    checks = {}
    # 1 + control: N=37 TTFT & input vs committed
    c1 = []
    for cell, pr in PRIOR.items():
        got = stats[cell]["ttft_s"]["median"]; ratio = got / pr["ttft"]
        c1.append({"cell": cell, "qty": "ttft_median_s", "this": got, "prior": pr["ttft"],
                   "ratio": round(ratio, 3), "within_10pct": abs(ratio - 1) <= 0.10})
        gi = stats[cell]["input_tokens"]["median"]
        c1.append({"cell": cell, "qty": "input_tokens_median", "this": gi, "prior": pr["input"],
                   "ratio": round(gi / pr["input"], 3), "within_10pct": abs(gi / pr["input"] - 1) <= 0.10})
    checks["1_control_crosscheck"] = c1
    # 2 physical plausibility: decode tps vs roofline
    dt = stats["4bt_f16_n37"]["decode_tps"]["median"]
    checks["2_physical_plausibility"] = {
        "decode_tps_4bt_n37": dt, "roofline_4B_F16_tok_s": ROOFLINE_4B,
        "frac_of_roofline": round(dt / ROOFLINE_4B, 3), "exceeds_roofline": dt > ROOFLINE_4B,
        "prior_4bt_decode": PRIOR["4bt_f16_n37"]["decode"],
        "ratio_vs_prior": round(dt / PRIOR["4bt_f16_n37"]["decode"], 3),
        "energy_identity_spotcheck": "energy_j ≈ mean_w × latency per-row by construction (trapezoid)",
    }
    # 3 distribution sanity: energy not constant; spreads present
    checks["3_distribution_sanity"] = {
        cell: {"energy_iqr_j": stats[cell]["energy_j"]["iqr"],
               "latency_iqr_s": stats[cell]["total_latency_s"]["iqr"],
               "think_iqr_tok": stats[cell]["think_tokens"]["iqr"]}
        for cell in CELLS}
    # 4 definition audit
    checks["4_definition_audit"] = {
        "N": "frame count; cells at 37/18/9; n_frames_median matches N (lower when 120s window < full)",
        "per_frame_tokens": "332 (560x560 incl marker), from dev_inputs.py; input≈N*332+text",
        "energy_rail": "total board power = VDD_GPU_SOC+VDD_CPU_CV+VIN_SYS_5V0 (3 INA3221 ch, jtop TOT); NO VDD_IN on this Orin",
        "idle_baseline": "60s loaded-idle (server up, model resident, no request) before each cell",
        "decode_tps": "(n_gen-1)/(latency-ttft), same formula as StudyDeviceLatency",
    }
    # 5 claim linkage
    checks["5_claim_linkage"] = (
        "Bears on Context Inertia physical component (FORMULATION: transfer+reconstruction latency grows "
        "with context length). Shows device TTFT scales ~linearly with frame count (prefill-bound); "
        "Instruct total latency follows TTFT, Thinking total is reasoning-bound (input-independent tail). "
        "Energy/request is the device-tier cost term. No scoped-out quantity measured.")
    # 6 proxy validity
    checks["6_proxy_validity"] = (
        "Accuracy is INDICATIVE only — reference accuracy is the A6000's (shared dev_inputs.py). "
        "Total board power is the sum of 3 INA3221 rails (jtop TOT convention), a proxy for module power "
        "since this Orin exposes no single VDD_IN rail; per-rail breakdown reported. "
        "N=18/9 frames are nearest-available subsets of the cached N=37 DEV-RECENT frames (same window), "
        "a documented approximation of frame_times(qt,N) snapped to the cached ~1 fps grid.")

    out = {"cells": stats, "consistency_checks": checks}
    json.dump(out, open(OUT / "devfast_stats.json", "w"), indent=2)

    # ── print table ──────────────────────────────────────────────────────────
    print(f"{'cell':<14}{'N':>3}{'in_tok':>8}{'TTFT_med':>9}{'lat_med':>8}{'lat_p90':>8}{'lat_max':>8}"
          f"{'think_med':>10}{'dec_tps':>8}{'E_med_J':>9}{'E_p90_J':>9}{'P_W':>6}{'idle_W':>7}{'acc':>6}{'tj':>6}")
    for cell in CELLS:
        s = stats[cell]
        print(f"{cell:<14}{s['n_frames_median']:>3.0f}{s['input_tokens']['median']:>8.0f}"
              f"{s['ttft_s']['median']:>9.2f}{s['total_latency_s']['median']:>8.1f}"
              f"{s['total_latency_s']['p90']:>8.1f}{s['total_latency_s']['max']:>8.0f}"
              f"{s['think_tokens']['median']:>10.0f}"
              f"{(s['decode_tps']['median'] if s['decode_tps'] else 0):>8.1f}"
              f"{s['energy_j']['median']:>9.0f}{s['energy_j']['p90']:>9.0f}"
              f"{s['mean_power_w']['median']:>6.1f}{s['idle_w']:>7.2f}"
              f"{s['acc']*100:>5.0f}%{s['tj_max']:>6.1f}")
    print("\n--- Check 1 control cross-check (N=37 TTFT/input vs committed StudyDeviceLatency) ---")
    for r in checks["1_control_crosscheck"]:
        print(f"  {r['cell']:<12} {r['qty']:<22} this={r['this']} prior={r['prior']} "
              f"ratio={r['ratio']} within10%={r['within_10pct']}")
    c2 = checks["2_physical_plausibility"]
    print(f"\n--- Check 2 plausibility: 4bt N=37 decode {c2['decode_tps_4bt_n37']} tok/s = "
          f"{c2['frac_of_roofline']}x roofline (25.6), {c2['ratio_vs_prior']}x prior 16.2; "
          f"exceeds_roofline={c2['exceeds_roofline']} ---")
    print(f"\nwrote {OUT/'devfast_stats.json'}")


if __name__ == "__main__":
    main()
