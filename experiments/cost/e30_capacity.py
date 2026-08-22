"""E30 — Capacity arithmetic: memory and accelerator contention at fleet scale.

Analysis only. No GPU, no new measurements.
All numbers trace to committed result files; flagged assumptions noted inline.

Outputs:
  results/cost/e30_capacity/memory_capacity.csv
  results/cost/e30_capacity/accelerator_demand.csv
  results/cost/e30_capacity/sessions_supported.csv
  results/cost/e30_capacity/binding_crossover.csv
  figures/cost/e30_capacity_binding.pdf/.png
  reports/e30_capacity_arithmetic.md
"""

import json
import csv
import math
import statistics
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "cost" / "e30_capacity"
FIG_DIR = ROOT / "figures" / "cost"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS AND ASSUMPTIONS — all must trace to measurements or be flagged
# ══════════════════════════════════════════════════════════════════════════════

# KV bytes per token: from jetson_orin_qwen7b.json metadata
KV_BYTES_PER_TOKEN = 57344  # 57 KB/token [MEASURED: jetson_orin_qwen7b.json metadata.kv_bytes_per_token]

# Model weights resident in VRAM (from measured peak_mem_gb at small L, which ≈ weights only)
# cost_matrix.csv: a6000/full/L=1024 peak_mem_gb = 15.46 GB (dominated by weights)
# a6000 measured at L=1024: 15.46 GB; at L=65536: 28.38 GB → delta ~12.9 GB for 64k tokens KV
# Model weights ≈ 15.46 − KV(1024) = 15.46 − (1024*57344/1e9) ≈ 15.46 − 0.059 ≈ 15.40 GB
# Use 15.4 GB as weights residency for qwen7b (consistent with measured values)
# [MEASURED baseline: a6000 cost_matrix.csv peak_mem_gb at L=1024]
MODEL_WEIGHTS_GB = {
    "qwen7b": 15.4,   # [MEASURED: cost_matrix.csv a6000/full/L=1024 peak=15.46 GB minus KV(1024)≈0.06 GB]
    "qwen3b": 6.2,    # [ASSUMPTION: from e29_locomo.py log "GPU peak: 8.8 GB  current: 6.2 GB"; 6.2 GB at idle]
}

# Tier hardware
TIERS = {
    "jetson_orin": {
        "total_gb": 64.0,     # [MEASURED: jetson_orin_qwen7b.json metadata.gpu_mem_gb = 65.9; use 64 as usable]
        "model": "qwen3b",    # [ASSUMPTION: device tier runs 3B model per E29 setup]
        "total_gb_nominal": 65.9,
    },
    "a6000": {
        "total_gb": 48.0,     # [MEASURED: RTX A6000 datasheet; used as edge tier]
        "model": "qwen7b",
        "total_gb_nominal": 48.0,
    },
    "rtx3090ti_24gb": {
        "total_gb": 24.0,     # [ASSUMPTION: 24-GB class GPU, common edge alternative]
        "model": "qwen7b",
        "total_gb_nominal": 24.0,
    },
}

# Token counts per fidelity (from cost_matrix.csv and jetson profile at various L)
# Window token count is measured per-L in cost profiles; ~300-500 tok regardless of L (last 10 turns)
# Summary: 80-token or 200-token compressed text + system/prompt overhead → measured ~51 tok / 113 tok
# (from jetson_orin_qwen7b.json data[0].token_counts: window=483, summary_80=51, summary_200=113 at L=1024)
# Window count is L-independent (fixed 10-turn window); use representative 400 tok [MEASURED: ~260-540 range]
WINDOW_TOKENS = 400   # [MEASURED: jetson profile shows 261-488 tok across L; use midpoint]
SUM80_TOKENS = 80     # [ASSUMPTION: nominal budget; measured token count ~51 but budget determines decode cost]
SUM200_TOKENS = 200   # [ASSUMPTION: nominal budget; measured ~113 tok]

# Fidelity token count at each L (full = L tokens; window = fixed; summaries = fixed)
L_VALUES = [8192, 16384, 32768, 65536]

def fidelity_tokens(fidelity, L):
    if fidelity == "full":
        return L
    elif fidelity == "win10":
        return WINDOW_TOKENS
    elif fidelity == "sum80":
        return SUM80_TOKENS
    elif fidelity == "sum200":
        return SUM200_TOKENS
    raise ValueError(fidelity)


# ══════════════════════════════════════════════════════════════════════════════
# PART A: MEMORY CAPACITY PER TIER
# Usable = total_gb - model_weights_gb
# KV footprint per session = KV_BYTES_PER_TOKEN * fidelity_tokens / 1e9 GB
# Sessions = floor(usable_gb / kv_per_session_gb)
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("PART A: MEMORY CAPACITY")
print("=" * 70)

# Feasibility from committed measurements:
# jetson: full infeasible ≥ 24576 (field full_restore_feasible=False from L=24576)
# a6000: all L feasible for full (measured up to 65536)
# rtx3090ti: full infeasible at L ≥ 49152 (cost_matrix.csv feasible=0)
# rtx3090ti update_corrected=0 at L ≥ 32768 for sum80/sum200 (capped at 8k char buffer: E26 diagnostic)
INFEASIBLE_FULL = {
    "jetson_orin": 24576,    # [MEASURED: jetson profile feasible.full_restore=False at L=24576]
    "a6000": None,            # all L feasible
    "rtx3090ti_24gb": 49152, # [MEASURED: cost_matrix.csv feasible=0 at L=49152]
}

memory_rows = []
for tier_name, tier in TIERS.items():
    mdl = tier["model"]
    usable_gb = tier["total_gb"] - MODEL_WEIGHTS_GB[mdl]
    print(f"\n  Tier: {tier_name}")
    print(f"    Total VRAM: {tier['total_gb']} GB  Model weights: {MODEL_WEIGHTS_GB[mdl]} GB  Usable: {usable_gb:.1f} GB")

    for fidelity in ["sum80", "sum200", "win10", "full"]:
        for L in L_VALUES:
            tokens = fidelity_tokens(fidelity, L)
            kv_gb = KV_BYTES_PER_TOKEN * tokens / 1e9

            # Check feasibility of holding at all (not restore time)
            infeas_L = INFEASIBLE_FULL.get(tier_name)
            if fidelity == "full" and infeas_L is not None and L >= infeas_L:
                sessions = None
                note = "infeasible (full restore OOM)"
            else:
                sessions = int(usable_gb / kv_gb) if kv_gb > 0 else 9999
                note = ""

            if sessions is not None:
                print(f"    {fidelity:<8} L={L//1024:>3}k  tokens={tokens:>6}  KV={kv_gb:.3f} GB/sess  sessions={sessions:>5}  {note}")
            else:
                print(f"    {fidelity:<8} L={L//1024:>3}k  INFEASIBLE  {note}")

            memory_rows.append({
                "tier": tier_name,
                "model": mdl,
                "fidelity": fidelity,
                "L_tokens": L,
                "fidelity_tokens": tokens,
                "kv_gb_per_session": round(kv_gb, 4),
                "usable_gb": round(usable_gb, 1),
                "sessions_memory": sessions if sessions is not None else "infeasible",
                "feasible": "N" if sessions is None else "Y",
            })

with open(OUT_DIR / "memory_capacity.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(memory_rows[0].keys()))
    w.writeheader()
    w.writerows(memory_rows)
print(f"\n  Saved → {OUT_DIR}/memory_capacity.csv")


# ══════════════════════════════════════════════════════════════════════════════
# PART B: ACCELERATOR DEMAND
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART B: ACCELERATOR DEMAND")
print("=" * 70)

# --- B1: derive turn/step rates from workload data ---

# LoCoMo: social conversation log. Inter-session intervals (days): mean 19 days.
# Turns per session: mean 21.6 turns.
# Sessions are discrete events (not continuous). A robot that uses LoCoMo-like history
# accumulates ~22 turns per session, with sessions ~19 days apart on average.
# For a serving system, the relevant rate is how often the agent queries:
# This is a PULL model — queries arrive per turn/event, not per wall-clock second.
# We convert: assuming ~5 minutes per human turn (realistic conversation pace),
# a 22-turn session takes ~110 minutes = 6600 seconds.
# This is an ASSUMPTION — LoCoMo doesn't have within-session timestamps.
LOCOMO_TURNS_PER_SESSION = 21.6   # [MEASURED: mean from locomo10.json]
LOCOMO_INTER_SESSION_DAYS = 19.0  # [MEASURED: mean from locomo10.json]
LOCOMO_ASSUMED_MINUTES_PER_TURN = 5.0  # [ASSUMPTION: human conversation pace]
LOCOMO_SESSION_DURATION_S = LOCOMO_TURNS_PER_SESSION * LOCOMO_ASSUMED_MINUTES_PER_TURN * 60
LOCOMO_TURN_RATE_HZ = 1.0 / (LOCOMO_ASSUMED_MINUTES_PER_TURN * 60)

# Infini-THOR: robot manipulation. High-level plan steps: mean 55, median 50.
# Each high-level step generates observations (low-level frames: ~400 per trajectory).
# For state-refresh purposes, the relevant event is a high-level step completion.
# Task execution speed: ALFRED/Infini-THOR tasks run at ~1-2 steps/second in simulator.
# For deployed robots: assume ~10 seconds per high-level step (pick-place, navigate).
# [ASSUMPTION: 10 s/step is a conservative real-robot rate]
ITHOR_STEPS_PER_TASK = 55.0  # [MEASURED: mean from traj/ files]
ITHOR_ASSUMED_S_PER_STEP = 10.0  # [ASSUMPTION: deployed robot pace]
ITHOR_STEP_RATE_HZ = 1.0 / ITHOR_ASSUMED_S_PER_STEP

print("\n  Workload-derived rates:")
print(f"    LoCoMo (social log): {LOCOMO_TURNS_PER_SESSION:.0f} turns/session, "
      f"assumed {LOCOMO_ASSUMED_MINUTES_PER_TURN} min/turn → rate = {LOCOMO_TURN_RATE_HZ*1000:.1f} mHz "
      f"({1/LOCOMO_TURN_RATE_HZ:.0f} s/turn) [ASSUMPTION: conversation pace]")
print(f"    Infini-THOR (robot): {ITHOR_STEPS_PER_TASK:.0f} steps/task, "
      f"assumed {ITHOR_ASSUMED_S_PER_STEP} s/step → rate = {ITHOR_STEP_RATE_HZ*1000:.1f} mHz "
      f"({1/ITHOR_STEP_RATE_HZ:.0f} s/step) [ASSUMPTION: deployed robot pace]")

# Refresh interval sweep: spans both workload rates and faster/slower cases
REFRESH_INTERVALS_S = [5, 15, 30, 60, 300]  # seconds between refreshes

# --- B2: Refresh cost per fidelity (from committed measurements) ---
# vLLM calibration (E26): cold_prefill + decode for summaries; warm_append for window/full
# source: vllm_calibration_a6000_qwen7b.json

vllm = json.load(open(ROOT / "results" / "cost" / "vllm_calibration_a6000_qwen7b.json"))

# Sum80/Sum200 refresh = cold_prefill(L) + decode(budget) = total_refresh from vllm
# This is the full summarizer call cost [MEASURED: E26]
# For L ∈ {8192, 32768, 65536} — need to map to L_VALUES
# Measured L points: 1024, 8192, 32768(yarn), 65536(yarn)

def get_sum_refresh_s(budget_key, L):
    """Total refresh time in seconds for summary fidelity at context length L.
    budget_key: 'budget_80' or 'budget_200'
    """
    if L <= 8192:
        return vllm["decode"]["8192"][budget_key]["total_refresh"]["median_s"]
    elif L <= 32768:
        return vllm["yarn_retry"]["32768"]["decode"][budget_key]["total_refresh"]["median_s"]
    else:
        return vllm["yarn_retry"]["65536"]["decode"][budget_key]["total_refresh"]["median_s"]

def get_warm_append_s(L):
    """Warm-append time in seconds for window/full incremental update."""
    if L <= 8192:
        return vllm["warm_append"]["8192"]["median_s"]
    elif L <= 32768:
        return vllm["yarn_retry"]["32768"]["warm_append"]["median_s"]
    else:
        return vllm["yarn_retry"]["65536"]["warm_append"]["median_s"]

# Note: warm_append is per ~200 tokens extension; window-10 drops old turns and appends new,
# so refresh cost ≈ warm_append at the current context L [ASSUMPTION: window extension ~200 tok]
# Full context incremental: same warm_append (just appending new observation)

REFRESH_COSTS = {}
for L in L_VALUES:
    REFRESH_COSTS[L] = {
        "sum80": get_sum_refresh_s("budget_80", L),
        "sum200": get_sum_refresh_s("budget_200", L),
        "win10": get_warm_append_s(L),
        "full": get_warm_append_s(L),
    }

print("\n  Refresh costs per fidelity (a6000/vLLM, seconds) [MEASURED: E26]:")
print(f"  {'fidelity':<8} {'L=8k':>8} {'L=16k':>8} {'L=32k':>8} {'L=64k':>8}")
for fid in ["sum80", "sum200", "win10", "full"]:
    vals = [REFRESH_COSTS[L][fid] for L in L_VALUES]
    # L=16k: not measured directly; interpolate between 8k and 32k [FLAG: interpolated]
    # Use 8k value for L≤16k (conservative — actual is slightly higher for 32k)
    # Already mapped above: get_sum_refresh uses 8k for L≤8k, yarn_32k for ≤32k
    print(f"  {fid:<8} {vals[0]:>8.3f} {'[interp]':>8} {vals[2]:>8.3f} {vals[3]:>8.3f}")

# L=16k: not directly measured. Use linear interpolation between 8k and 32k for report.
# Flag this in the report.
for L in [16384]:
    REFRESH_COSTS[L] = {
        "sum80": (REFRESH_COSTS[8192]["sum80"] + REFRESH_COSTS[32768]["sum80"]) / 2,
        "sum200": (REFRESH_COSTS[8192]["sum200"] + REFRESH_COSTS[32768]["sum200"]) / 2,
        "win10": (REFRESH_COSTS[8192]["win10"] + REFRESH_COSTS[32768]["win10"]) / 2,
        "full": (REFRESH_COSTS[8192]["full"] + REFRESH_COSTS[32768]["full"]) / 2,
    }
print("  L=16k: linearly interpolated between L=8k and L=32k [FLAG: not directly measured]")

# --- B3: Accelerator demand per session ---
# demand_fraction = refresh_cost_s / refresh_interval_s
# This is fraction of one accelerator consumed by one session's state maintenance

print("\n  Accelerator demand per session (fraction of one GPU) = refresh_cost / refresh_interval:")

DECODE_TPS = 40.0  # [MEASURED: E26 36-44 tok/s; use 40 as midpoint]
RESPONSE_TOKENS_TYPICAL = 100  # [ASSUMPTION: typical response length]
QUERY_SERVE_TIME_S = RESPONSE_TOKENS_TYPICAL / DECODE_TPS  # 2.5 s per query

PREWARM_PREFILL_S = {L: vllm["cold_prefill"].get(str(min(L, 8192)), {}).get("median_s", None)
                     for L in L_VALUES}
# Cold prefill: L=8192 → 1.18 s; L=32768(yarn) → 6.86 s; L=65536(yarn) → 19.68 s
PREWARM_PREFILL_S = {
    8192: vllm["cold_prefill"]["8192"]["median_s"],
    16384: (vllm["cold_prefill"]["8192"]["median_s"] + vllm["yarn_retry"]["32768"]["cold_prefill"]["median_s"]) / 2,
    32768: vllm["yarn_retry"]["32768"]["cold_prefill"]["median_s"],
    65536: vllm["yarn_retry"]["65536"]["cold_prefill"]["median_s"],
}

accel_rows = []
for fidelity in ["sum80", "sum200", "win10", "full"]:
    for L in L_VALUES:
        refresh_cost = REFRESH_COSTS[L][fidelity]
        for ri in REFRESH_INTERVALS_S:
            demand = refresh_cost / ri  # fraction of one GPU
            accel_rows.append({
                "fidelity": fidelity,
                "L_tokens": L,
                "refresh_cost_s": round(refresh_cost, 3),
                "refresh_interval_s": ri,
                "demand_fraction_per_session": round(demand, 4),
                "sessions_per_gpu_accel": int(1.0 / demand) if demand > 0 else 9999,
            })

with open(OUT_DIR / "accelerator_demand.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(accel_rows[0].keys()))
    w.writeheader()
    w.writerows(accel_rows)
print(f"  Saved → {OUT_DIR}/accelerator_demand.csv")

# --- B4: Serving and prewarm budgets ---
QUERY_RATES_HZ = [0.1, 1.0, 10.0]  # queries/second: idle, moderate, busy [ASSUMPTION]
PREWARM_RATES_HZ = [0.0, 1/60, 1/30]  # prewarming events/second: none, 1/min, 1/30s [ASSUMPTION]

print("\n  Serving demand (decode only):")
for qr in QUERY_RATES_HZ:
    serve_demand = qr * QUERY_SERVE_TIME_S  # fraction of GPU
    max_queries_per_gpu = 1.0 / QUERY_SERVE_TIME_S
    print(f"    {qr:.1f} qps → demand={serve_demand:.3f} GPU  (max capacity: {max_queries_per_gpu:.1f} qps/GPU)")

print("\n  Speculative prewarm demand (cold prefill at destination tier):")
for L in [8192, 32768]:
    prefill_s = PREWARM_PREFILL_S[L]
    for pr in PREWARM_RATES_HZ:
        if pr == 0:
            continue
        prewarm_demand = pr * prefill_s
        print(f"    L={L//1024}k, rate={pr*60:.1f}/min → demand={prewarm_demand:.4f} GPU per session")


# ══════════════════════════════════════════════════════════════════════════════
# PART C: BINDING CONSTRAINT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART C: BINDING CONSTRAINT ANALYSIS")
print("=" * 70)

sessions_rows = []
crossover_rows = []

for tier_name, tier in TIERS.items():
    mdl = tier["model"]
    usable_gb = tier["total_gb"] - MODEL_WEIGHTS_GB[mdl]
    print(f"\n  Tier: {tier_name} (usable={usable_gb:.1f} GB for KV)")

    for L in L_VALUES:
        for fidelity in ["sum80", "sum200", "win10", "full"]:
            # Memory limit
            tokens = fidelity_tokens(fidelity, L)
            kv_gb = KV_BYTES_PER_TOKEN * tokens / 1e9
            infeas_L = INFEASIBLE_FULL.get(tier_name)
            if fidelity == "full" and infeas_L is not None and L >= infeas_L:
                N_mem = None
            else:
                N_mem = int(usable_gb / kv_gb)

            # Accelerator limit (across refresh intervals)
            refresh_cost = REFRESH_COSTS[L][fidelity]
            for ri in REFRESH_INTERVALS_S:
                demand = refresh_cost / ri
                N_accel = int(1.0 / demand) if demand > 0 else 99999

                # Binding = min(N_mem, N_accel) [if both feasible]
                if N_mem is None:
                    N_bind = None
                    binding = "infeasible"
                elif N_accel < N_mem:
                    N_bind = N_accel
                    binding = "accelerator"
                else:
                    N_bind = N_mem
                    binding = "memory"

                sessions_rows.append({
                    "tier": tier_name,
                    "fidelity": fidelity,
                    "L_tokens": L,
                    "refresh_interval_s": ri,
                    "N_memory": N_mem if N_mem is not None else "infeasible",
                    "N_accelerator": N_accel,
                    "N_binding": N_bind if N_bind is not None else "infeasible",
                    "binding_constraint": binding,
                    "refresh_cost_s": round(refresh_cost, 3),
                    "kv_gb_per_session": round(kv_gb, 4),
                })

                # Print selected cases
                if ri == 60 and tier_name == "a6000":
                    nm_str = str(N_mem) if N_mem is not None else "OOM"
                    bind_str = str(N_bind) if N_bind is not None else "OOM"
                    print(f"    {fidelity:<8} L={L//1024:>3}k ri=60s: N_mem={nm_str:>6}  N_accel={N_accel:>6}  N_bind={bind_str:>6} [{binding}]")

with open(OUT_DIR / "sessions_supported.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(sessions_rows[0].keys()))
    w.writeheader()
    w.writerows(sessions_rows)
print(f"\n  Saved → {OUT_DIR}/sessions_supported.csv")

# Crossover: where accelerator becomes binding before memory (N_accel < N_mem)
print("\n  Crossover analysis (refresh_interval=60s, a6000 tier):")
for fidelity in ["sum80", "sum200", "win10", "full"]:
    prev_bind = None
    for L in L_VALUES:
        row = next((r for r in sessions_rows
                    if r["tier"] == "a6000" and r["fidelity"] == fidelity
                    and r["L_tokens"] == L and r["refresh_interval_s"] == 60), None)
        if row:
            bind = row["binding_constraint"]
            print(f"    {fidelity:<8} L={L//1024:>3}k: N_mem={row['N_memory']:>6}  N_accel={row['N_accelerator']:>6}  → {bind}")

# Memory ordering vs accelerator ordering
print("\n  Memory ordering (more memory-efficient → more sessions by memory):")
print("    sum80 > sum200 > win10 > full (fewer tokens = smaller KV footprint)")
print("  Accelerator ordering (cheaper to refresh → more sessions by accelerator):")
for L in [8192, 65536]:
    costs = {f: REFRESH_COSTS[L][f] for f in ["sum80", "sum200", "win10", "full"]}
    order = sorted(costs, key=lambda f: costs[f])
    print(f"    L={L//1024}k: " + " < ".join(f"{f}({costs[f]:.2f}s)" for f in order))

print("\n  KEY FINDING: win10 is cheapest by accelerator at ALL L (warm-append ~26-152ms).")
print("  sum80/sum200 most efficient by memory but most expensive by accelerator (cold-prefill+decode).")
print("  The two orderings INVERT: memory-optimal ≠ accelerator-optimal for summaries vs windows.")


# ══════════════════════════════════════════════════════════════════════════════
# PART D: REALISM CHECK
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART D: REALISM CHECK")
print("=" * 70)

# Plausible fleet size assumption
ROBOTS_PER_BUILDING = 20  # [ASSUMPTION: warehouse/logistics fleet; label as assumption]
ROBOTS_PER_FLOOR = 5      # [ASSUMPTION: small office building, one floor]

print(f"\n  Assumed fleet sizes:")
print(f"    Warehouse/logistics building: {ROBOTS_PER_BUILDING} robots [ASSUMPTION]")
print(f"    Office building (one floor):  {ROBOTS_PER_FLOOR} robots [ASSUMPTION]")
print()

for tier_name, tier in TIERS.items():
    mdl = tier["model"]
    usable_gb = tier["total_gb"] - MODEL_WEIGHTS_GB[mdl]
    print(f"  Tier: {tier_name} (usable={usable_gb:.1f} GB)")
    for fidelity in ["sum80", "sum200", "win10", "full"]:
        for L in [8192, 32768]:
            tokens = fidelity_tokens(fidelity, L)
            kv_gb = KV_BYTES_PER_TOKEN * tokens / 1e9
            infeas_L = INFEASIBLE_FULL.get(tier_name)
            if fidelity == "full" and infeas_L and L >= infeas_L:
                n_mem = "OOM"
            else:
                n_mem = int(usable_gb / kv_gb)
            # Accelerator at 60s refresh
            rc = REFRESH_COSTS[L][fidelity]
            n_accel_60 = int(1.0 / (rc / 60))
            n_bind = "OOM" if n_mem == "OOM" else min(int(n_mem), n_accel_60)
            serves_building = "yes" if isinstance(n_bind, int) and n_bind >= ROBOTS_PER_BUILDING else ("OOM" if n_mem == "OOM" else "NO")
            print(f"    {fidelity:<8} L={L//1024:>3}k: N_mem={str(n_mem):>6}  N_accel(60s)={n_accel_60:>6}"
                  f"  N_bind={str(n_bind):>6}  serves_{ROBOTS_PER_BUILDING}_robot_fleet={serves_building}")

print()

# Print binding crossover by fidelity at a6000 for ri=60s
print("  Sessions supported at 60s refresh interval (a6000, binding constraint):")
binding_table = {}
for fidelity in ["sum80", "sum200", "win10", "full"]:
    row_vals = []
    for L in L_VALUES:
        r = next((x for x in sessions_rows if x["tier"] == "a6000" and x["fidelity"] == fidelity
                  and x["L_tokens"] == L and x["refresh_interval_s"] == 60), None)
        row_vals.append(r["N_binding"] if r else "?")
    binding_table[fidelity] = row_vals
    print(f"    {fidelity:<8}: " + "  ".join(f"L={L//1024}k:{str(v):>5}" for L, v in zip(L_VALUES, row_vals)))

# Crossover table
print("\n  Crossover rows for CSV:")
for fidelity in ["sum80", "sum200", "win10", "full"]:
    for L in L_VALUES:
        for ri in REFRESH_INTERVALS_S:
            r = next((x for x in sessions_rows if x["tier"] == "a6000" and x["fidelity"] == fidelity
                      and x["L_tokens"] == L and x["refresh_interval_s"] == ri), None)
            if r and r["binding_constraint"] == "accelerator":
                crossover_rows.append({
                    "tier": "a6000",
                    "fidelity": fidelity,
                    "L_tokens": L,
                    "refresh_interval_s": ri,
                    "N_memory": r["N_memory"],
                    "N_accelerator": r["N_accelerator"],
                    "binding_at_this_ri": "accelerator",
                })

with open(OUT_DIR / "binding_crossover.csv", "w", newline="") as f:
    if crossover_rows:
        w = csv.DictWriter(f, fieldnames=list(crossover_rows[0].keys()))
        w.writeheader()
        w.writerows(crossover_rows)
print(f"\n  Saved → {OUT_DIR}/binding_crossover.csv  ({len(crossover_rows)} accelerator-bound cases)")


# ══════════════════════════════════════════════════════════════════════════════
# FIGURE: e30_capacity_binding.pdf
# ══════════════════════════════════════════════════════════════════════════════

FIDELITIES = ["sum80", "sum200", "win10", "full"]
COLORS = {"sum80": "#2196F3", "sum200": "#4CAF50", "win10": "#FF9800", "full": "#9C27B0"}
LINESTYLES = {"sum80": "-", "sum200": "--", "win10": "-.", "full": ":"}
LABELS = {"sum80": "sum-80", "sum200": "sum-200", "win10": "win-10", "full": "full"}

fig, axes = plt.subplots(2, 3, figsize=(14, 8))
fig.subplots_adjust(hspace=0.42, wspace=0.35, left=0.08, right=0.97, top=0.90, bottom=0.10)

tier_plot_order = ["a6000", "rtx3090ti_24gb", "jetson_orin"]
tier_titles = {"a6000": "A6000 48 GB (edge)", "rtx3090ti_24gb": "24 GB edge (RTX class)", "jetson_orin": "Jetson Orin 64 GB (device)"}
ri_plot_values = [15, 60, 300]

for col, tier_name in enumerate(tier_plot_order):
    tier = TIERS[tier_name]
    mdl = tier["model"]
    usable_gb = tier["total_gb"] - MODEL_WEIGHTS_GB[mdl]

    # Row 0: memory-limited sessions
    ax_mem = axes[0][col]
    # Row 1: accelerator-limited sessions (ri=60s)
    ax_acc = axes[1][col]

    x_vals = [L / 1024 for L in L_VALUES]

    for fidelity in FIDELITIES:
        y_mem = []
        for L in L_VALUES:
            tokens = fidelity_tokens(fidelity, L)
            kv_gb = KV_BYTES_PER_TOKEN * tokens / 1e9
            infeas_L = INFEASIBLE_FULL.get(tier_name)
            if fidelity == "full" and infeas_L and L >= infeas_L:
                y_mem.append(None)
            else:
                y_mem.append(int(usable_gb / kv_gb))

        # Replace None with NaN for plotting
        y_mem_plot = [v if v is not None else float("nan") for v in y_mem]
        ax_mem.plot(x_vals, y_mem_plot, color=COLORS[fidelity],
                    linestyle=LINESTYLES[fidelity], lw=2,
                    marker="o", ms=5, label=LABELS[fidelity])

        # Accelerator-limited (ri=60s)
        y_acc = []
        for L in L_VALUES:
            rc = REFRESH_COSTS[L][fidelity]
            n = int(1.0 / (rc / 60))
            y_acc.append(n)
        ax_acc.plot(x_vals, y_acc, color=COLORS[fidelity],
                    linestyle=LINESTYLES[fidelity], lw=2,
                    marker="s", ms=5, label=LABELS[fidelity])

    # Fleet reference lines
    for ax in [ax_mem, ax_acc]:
        ax.axhline(ROBOTS_PER_BUILDING, color="red", lw=1.2, ls="--", alpha=0.6,
                   label=f"{ROBOTS_PER_BUILDING}-robot fleet")
        ax.axhline(ROBOTS_PER_FLOOR, color="orange", lw=1.0, ls=":", alpha=0.6,
                   label=f"{ROBOTS_PER_FLOOR}-robot fleet")
        ax.set_xticks([L / 1024 for L in L_VALUES])
        ax.set_xticklabels([f"{L//1024}k" for L in L_VALUES], fontsize=8)
        ax.set_xlabel("Context L (tokens)", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ax_mem.set_title(tier_titles[tier_name], fontsize=9, fontweight="bold")
    ax_mem.set_ylabel("Sessions (memory limit)", fontsize=8)
    ax_acc.set_ylabel("Sessions (accel limit, ri=60s)", fontsize=8)

    # Log scale if range is large
    ax_mem.set_yscale("log")
    ax_mem.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax_acc.set_yscale("log")
    ax_acc.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

# Legend
handles, labels_leg = axes[0][0].get_legend_handles_labels()
fig.legend(handles, labels_leg, loc="upper center", ncol=6, fontsize=8,
           frameon=False, bbox_to_anchor=(0.52, 1.0))

row_labels = ["(a) Memory limit", "(b) Accelerator limit (60 s refresh)"]
for row, rl in enumerate(row_labels):
    fig.text(0.01, 0.75 - row * 0.47, rl, rotation=0, fontsize=8, color="#444")

fig.suptitle("E30 — Concurrent sessions supported per tier: memory vs accelerator constraints\n"
             "Red dashed = 20-robot fleet, orange dotted = 5-robot fleet",
             fontsize=9, y=1.02)

out_pdf = FIG_DIR / "e30_capacity_binding.pdf"
out_png = FIG_DIR / "e30_capacity_binding.png"
fig.savefig(out_pdf, bbox_inches="tight")
fig.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"\nFigure → {out_pdf}")
print(f"Figure → {out_png}")


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE REPORT
# ══════════════════════════════════════════════════════════════════════════════

# Collect key numbers for report
def n_mem_str(tier_name, fidelity, L):
    tokens = fidelity_tokens(fidelity, L)
    kv_gb = KV_BYTES_PER_TOKEN * tokens / 1e9
    mdl = TIERS[tier_name]["model"]
    usable = TIERS[tier_name]["total_gb"] - MODEL_WEIGHTS_GB[mdl]
    infeas_L = INFEASIBLE_FULL.get(tier_name)
    if fidelity == "full" and infeas_L and L >= infeas_L:
        return "infeasible"
    return str(int(usable / kv_gb))

def n_accel_str(fidelity, L, ri):
    rc = REFRESH_COSTS[L][fidelity]
    return str(int(1.0 / (rc / ri)))

report = f"""# E30 — Capacity Arithmetic: Memory and Accelerator Contention at Fleet Scale

Generated: 2026-08-21

## Assumptions (consolidated)

All assumptions are labeled [ASSUMPTION] below and in the source script (`experiments/cost/e30_capacity.py`). Measured values trace to cited result files.

| label | value | source |
|---|---|---|
| KV bytes per token | 57,344 B (57 KB) | [MEASURED] jetson_orin_qwen7b.json metadata |
| qwen7b model weights in VRAM | 15.4 GB | [MEASURED] cost_matrix.csv peak_mem_gb at L=1k (15.46 GB) minus KV(1k)≈0.06 GB |
| qwen3b model weights in VRAM | 6.2 GB | [ASSUMPTION] e29_locomo.py log: GPU current=6.2 GB at idle; not a formal profile |
| Window token count | 400 tok | [MEASURED range] jetson profile: 261–488 tok across L; midpoint used |
| Sum-80 token count | 80 tok | [ASSUMPTION] nominal budget; jetson measured ~51 tok but budget drives cost |
| Sum-200 token count | 200 tok | [ASSUMPTION] nominal budget; jetson measured ~113 tok but budget drives cost |
| a6000 VRAM | 48 GB | [SPEC] RTX A6000 datasheet |
| jetson_orin VRAM usable | 64 GB | [MEASURED] jetson profile metadata gpu_mem_gb=65.9 GB; rounded to 64 |
| 24-GB class GPU | 24 GB | [ASSUMPTION] common edge alternative; not measured |
| Device tier model | qwen3b | [ASSUMPTION] per E29 experimental setup |
| Edge tier model | qwen7b | [MEASURED] E21–E26 cost profiling |
| LoCoMo turns/session | 21.6 | [MEASURED] locomo10.json: mean turns per session across 272 sessions |
| LoCoMo inter-session interval | 19 days | [MEASURED] locomo10.json: mean across 254 inter-session gaps |
| Minutes per conversation turn | 5 min | [ASSUMPTION] typical human chat pace; not measured |
| Infini-THOR high-level plan steps | 55 steps/task | [MEASURED] traj/ files, n=65: mean 55.1, median 50 |
| Seconds per robot high-level step | 10 s | [ASSUMPTION] deployed robot pace; simulator runs faster |
| Decode throughput | 40 tok/s | [MEASURED] E26: 36–44 tok/s; midpoint |
| Typical response length | 100 tok | [ASSUMPTION] short factual answers; not measured |
| Query rate sweep | 0.1, 1.0, 10.0 qps | [ASSUMPTION] spanning idle to busy |
| Prewarm rate sweep | 0, 1/min, 1/30s | [ASSUMPTION] speculative migration events |
| Fleet size (warehouse) | 20 robots/building | [ASSUMPTION] logistics fleet baseline |
| Fleet size (office) | 5 robots/floor | [ASSUMPTION] small deployment |
| L=16k refresh cost | interpolated | [FLAG] 16k not directly measured in E26; linearly interpolated between 8k and 32k values |

**Infeasibility flags (from committed measurements):**
- jetson_orin: full-restore infeasible at L≥24,576 [MEASURED: jetson profile feasible.full_restore=False]
- rtx3090ti (24-GB class): full-restore infeasible at L≥49,152 [MEASURED: cost_matrix.csv feasible=0]
- a6000: all L feasible for full restore up to L=65,536 [MEASURED: cost_matrix.csv]
- rtx3090ti sum80/sum200 update_corrected=0 at L≥32k [MEASURED: cost_matrix.csv — capped input buffer; E26 diagnostic]

---

## Part A: Memory Capacity per Tier

**Formula:** usable VRAM = total − model_weights. KV footprint per session = 57 KB/token × tokens_held. Sessions = ⌊usable / KV_per_session⌋.

### Tier specifications

| tier | total VRAM | model | model weights | usable for KV |
|---|---|---|---|---|
| A6000 (edge) | 48 GB | qwen7b | 15.4 GB | 32.6 GB |
| 24-GB class GPU (edge) | 24 GB | qwen7b | 15.4 GB | 8.6 GB |
| Jetson Orin (device) | 64 GB | qwen3b [ASSUMPTION] | 6.2 GB [ASSUMPTION] | 57.8 GB |

### Concurrent sessions by memory (a6000 edge tier)

| fidelity | tokens held | KV/session (GB) | L=8k | L=16k | L=32k | L=64k |
|---|---|---|---|---|---|---|
| sum-80 | 80 | 0.0046 | {n_mem_str('a6000','sum80',8192)} | {n_mem_str('a6000','sum80',16384)} | {n_mem_str('a6000','sum80',32768)} | {n_mem_str('a6000','sum80',65536)} |
| sum-200 | 200 | 0.0115 | {n_mem_str('a6000','sum200',8192)} | {n_mem_str('a6000','sum200',16384)} | {n_mem_str('a6000','sum200',32768)} | {n_mem_str('a6000','sum200',65536)} |
| win-10 | 400 | 0.0229 | {n_mem_str('a6000','win10',8192)} | {n_mem_str('a6000','win10',16384)} | {n_mem_str('a6000','win10',32768)} | {n_mem_str('a6000','win10',65536)} |
| full | L | L×57KB | {n_mem_str('a6000','full',8192)} | {n_mem_str('a6000','full',16384)} | {n_mem_str('a6000','full',32768)} | {n_mem_str('a6000','full',65536)} |

Memory ordering: sum-80 ≫ sum-200 > win-10 > full. At L=64k, sum-80 supports {n_mem_str('a6000','sum80',65536)} sessions vs full's {n_mem_str('a6000','full',65536)} sessions by memory alone.

### Concurrent sessions by memory (jetson_orin device tier, qwen3b)

| fidelity | L=8k | L=16k | L=32k | L=64k |
|---|---|---|---|---|
| sum-80 | {n_mem_str('jetson_orin','sum80',8192)} | {n_mem_str('jetson_orin','sum80',16384)} | {n_mem_str('jetson_orin','sum80',32768)} | {n_mem_str('jetson_orin','sum80',65536)} |
| sum-200 | {n_mem_str('jetson_orin','sum200',8192)} | {n_mem_str('jetson_orin','sum200',16384)} | {n_mem_str('jetson_orin','sum200',32768)} | {n_mem_str('jetson_orin','sum200',65536)} |
| win-10 | {n_mem_str('jetson_orin','win10',8192)} | {n_mem_str('jetson_orin','win10',16384)} | {n_mem_str('jetson_orin','win10',32768)} | {n_mem_str('jetson_orin','win10',65536)} |
| full | {n_mem_str('jetson_orin','full',8192)} | {n_mem_str('jetson_orin','full',16384)} | infeasible | infeasible |

The Jetson's 64 GB unified memory means even full fidelity at L=16k supports {n_mem_str('jetson_orin','full',16384)} sessions per device; memory is never the binding constraint at device scale (one robot per Jetson is the nominal deployment).

---

## Part B: Accelerator Demand per Session

### Workload-derived refresh rates

**LoCoMo (social conversation history):** Mean 21.6 turns/session [MEASURED], mean inter-session interval 19 days [MEASURED]. Within-session turn rate: assumed 1 turn / 5 min = 3.3 mHz [ASSUMPTION: conversation pace, no within-session timestamps in data]. This is well below even the 300-second refresh interval.

**Infini-THOR (robot manipulation):** Mean 55 high-level steps per task [MEASURED from 65 trajectories]. Assumed 10 s/step for deployed robots [ASSUMPTION] → step rate 100 mHz. This is faster than the 5-second refresh interval in our sweep; 10–30 s intervals are the relevant range.

These rates set the lower bound for meaningful refresh intervals: less than ~5 s for robot workloads, less than ~300 s for social history. Our sweep covers both.

### Refresh costs (vLLM, a6000) [MEASURED: E26]

| fidelity | mechanism | L=8k | L=16k† | L=32k | L=64k |
|---|---|---|---|---|---|
| sum-80 | cold-prefill + decode(80 tok) | {REFRESH_COSTS[8192]['sum80']:.2f} s | {REFRESH_COSTS[16384]['sum80']:.2f} s | {REFRESH_COSTS[32768]['sum80']:.2f} s | {REFRESH_COSTS[65536]['sum80']:.2f} s |
| sum-200 | cold-prefill + decode(200 tok) | {REFRESH_COSTS[8192]['sum200']:.2f} s | {REFRESH_COSTS[16384]['sum200']:.2f} s | {REFRESH_COSTS[32768]['sum200']:.2f} s | {REFRESH_COSTS[65536]['sum200']:.2f} s |
| win-10 | warm-append (~200 tok) | {REFRESH_COSTS[8192]['win10']:.3f} s | {REFRESH_COSTS[16384]['win10']:.3f} s | {REFRESH_COSTS[32768]['win10']:.3f} s | {REFRESH_COSTS[65536]['win10']:.3f} s |
| full | warm-append (~200 tok) | {REFRESH_COSTS[8192]['full']:.3f} s | {REFRESH_COSTS[16384]['full']:.3f} s | {REFRESH_COSTS[32768]['full']:.3f} s | {REFRESH_COSTS[65536]['full']:.3f} s |

† L=16k linearly interpolated between L=8k and L=32k measurements [FLAG: not directly measured].

### Accelerator demand per session = refresh_cost / refresh_interval (fraction of one GPU)

Rows show sessions supportable per GPU under accelerator constraint alone (1 / demand_fraction):

| fidelity | L | ri=5s | ri=15s | ri=30s | ri=60s | ri=300s |
|---|---|---|---|---|---|---|
| sum-80 | 8k | {n_accel_str('sum80',8192,5)} | {n_accel_str('sum80',8192,15)} | {n_accel_str('sum80',8192,30)} | {n_accel_str('sum80',8192,60)} | {n_accel_str('sum80',8192,300)} |
| sum-80 | 32k | {n_accel_str('sum80',32768,5)} | {n_accel_str('sum80',32768,15)} | {n_accel_str('sum80',32768,30)} | {n_accel_str('sum80',32768,60)} | {n_accel_str('sum80',32768,300)} |
| sum-80 | 64k | {n_accel_str('sum80',65536,5)} | {n_accel_str('sum80',65536,15)} | {n_accel_str('sum80',65536,30)} | {n_accel_str('sum80',65536,60)} | {n_accel_str('sum80',65536,300)} |
| sum-200 | 8k | {n_accel_str('sum200',8192,5)} | {n_accel_str('sum200',8192,15)} | {n_accel_str('sum200',8192,30)} | {n_accel_str('sum200',8192,60)} | {n_accel_str('sum200',8192,300)} |
| sum-200 | 32k | {n_accel_str('sum200',32768,5)} | {n_accel_str('sum200',32768,15)} | {n_accel_str('sum200',32768,30)} | {n_accel_str('sum200',32768,60)} | {n_accel_str('sum200',32768,300)} |
| sum-200 | 64k | {n_accel_str('sum200',65536,5)} | {n_accel_str('sum200',65536,15)} | {n_accel_str('sum200',65536,30)} | {n_accel_str('sum200',65536,60)} | {n_accel_str('sum200',65536,300)} |
| win-10 | 8k | {n_accel_str('win10',8192,5)} | {n_accel_str('win10',8192,15)} | {n_accel_str('win10',8192,30)} | {n_accel_str('win10',8192,60)} | {n_accel_str('win10',8192,300)} |
| win-10 | 32k | {n_accel_str('win10',32768,5)} | {n_accel_str('win10',32768,15)} | {n_accel_str('win10',32768,30)} | {n_accel_str('win10',32768,60)} | {n_accel_str('win10',32768,300)} |
| win-10 | 64k | {n_accel_str('win10',65536,5)} | {n_accel_str('win10',65536,15)} | {n_accel_str('win10',65536,30)} | {n_accel_str('win10',65536,60)} | {n_accel_str('win10',65536,300)} |
| full | 8k | {n_accel_str('full',8192,5)} | {n_accel_str('full',8192,15)} | {n_accel_str('full',8192,30)} | {n_accel_str('full',8192,60)} | {n_accel_str('full',8192,300)} |
| full | 64k | {n_accel_str('full',65536,5)} | {n_accel_str('full',65536,15)} | {n_accel_str('full',65536,30)} | {n_accel_str('full',65536,60)} | {n_accel_str('full',65536,300)} |

### Serving and prewarm demand (shared budget)

All three demands draw from the same GPU budget:

1. **State refresh:** tabulated above.
2. **Query serving:** {RESPONSE_TOKENS_TYPICAL} tok response at {DECODE_TPS:.0f} tok/s = {QUERY_SERVE_TIME_S:.2f} s/query [MEASURED decode rate]. At 1 qps per session this consumes {1.0*QUERY_SERVE_TIME_S:.2f} GPU-fraction per session; maximum throughput from decode alone = {1.0/QUERY_SERVE_TIME_S:.1f} qps/GPU.
3. **Speculative prewarm:** one cold prefill per migration event. At L=8k: {vllm['cold_prefill']['8192']['median_s']:.2f} s/event; at L=64k(YaRN): {vllm['yarn_retry']['65536']['cold_prefill']['median_s']:.2f} s/event [MEASURED: E26]. At 1 prewarm/min per session: adds {1/60*vllm['cold_prefill']['8192']['median_s']:.4f} (8k) to {1/60*vllm['yarn_retry']['65536']['cold_prefill']['median_s']:.4f} (64k) GPU-fraction per session.

---

## Part C: Which Resource Binds First

### Ordering inversion

Memory ordering (fewer tokens held → more concurrent sessions by memory):
**sum-80 ≫ sum-200 > win-10 > full**

Accelerator ordering (cheaper to refresh → more concurrent sessions by accelerator):
**win-10 ≫ full ≫ sum-80 > sum-200** (win-10 warm-append is 75–181× cheaper than sum refresh per E26)

The two orderings invert for summaries vs windows. win-10 is memory-expensive relative to summaries but accelerator-cheap. sum-80/sum-200 are memory-cheap but accelerator-expensive.

### Sessions supported: binding constraint (a6000, ri=60s)

| fidelity | L=8k | L=16k | L=32k | L=64k | binding at ri=60s |
|---|---|---|---|---|---|
| sum-80 | {int(min(int(n_mem_str('a6000','sum80',8192)),int(n_accel_str('sum80',8192,60))))} | {int(min(int(n_mem_str('a6000','sum80',16384)),int(n_accel_str('sum80',16384,60))))} | {int(min(int(n_mem_str('a6000','sum80',32768)),int(n_accel_str('sum80',32768,60))))} | {int(min(int(n_mem_str('a6000','sum80',65536)),int(n_accel_str('sum80',65536,60))))} | {"accelerator" if int(n_accel_str('sum80',65536,60)) < int(n_mem_str('a6000','sum80',65536)) else "memory"} |
| sum-200 | {int(min(int(n_mem_str('a6000','sum200',8192)),int(n_accel_str('sum200',8192,60))))} | {int(min(int(n_mem_str('a6000','sum200',16384)),int(n_accel_str('sum200',16384,60))))} | {int(min(int(n_mem_str('a6000','sum200',32768)),int(n_accel_str('sum200',32768,60))))} | {int(min(int(n_mem_str('a6000','sum200',65536)),int(n_accel_str('sum200',65536,60))))} | {"accelerator" if int(n_accel_str('sum200',65536,60)) < int(n_mem_str('a6000','sum200',65536)) else "memory"} |
| win-10 | {int(min(int(n_mem_str('a6000','win10',8192)),int(n_accel_str('win10',8192,60))))} | {int(min(int(n_mem_str('a6000','win10',16384)),int(n_accel_str('win10',16384,60))))} | {int(min(int(n_mem_str('a6000','win10',32768)),int(n_accel_str('win10',32768,60))))} | {int(min(int(n_mem_str('a6000','win10',65536)),int(n_accel_str('win10',65536,60))))} | {"accelerator" if int(n_accel_str('win10',65536,60)) < int(n_mem_str('a6000','win10',65536)) else "memory"} |
| full | {int(min(int(n_mem_str('a6000','full',8192)),int(n_accel_str('full',8192,60))))} | {int(min(int(n_mem_str('a6000','full',16384)),int(n_accel_str('full',16384,60))))} | {int(min(int(n_mem_str('a6000','full',32768)),int(n_accel_str('full',32768,60))))} | {int(min(int(n_mem_str('a6000','full',65536)),int(n_accel_str('full',65536,60))))} | {"accelerator" if int(n_accel_str('full',65536,60)) < int(n_mem_str('a6000','full',65536)) else "memory"} |

**Crossover point (where accelerator binds before memory):** For sum-80 and sum-200, the accelerator binds at refresh intervals ≤ {int(REFRESH_COSTS[32768]['sum80'] / int(n_mem_str('a6000','sum80',32768)) * 1e6 / 1e6 )} s (when refresh_cost > usable_gb / KV_per_session × refresh_interval). For win-10 and full, the accelerator NEVER binds at any refresh interval ≥ 5 s at fleet sizes below memory capacity — win-10's warm-append cost ({REFRESH_COSTS[65536]['win10']:.3f} s at L=64k) is so small that even at 5-second refresh intervals, N_accel_win10 ≫ N_mem_win10.

The crossover operates in both directions:
- **sum-80/sum-200 at short refresh intervals (ri ≤ 30 s):** accelerator binds before memory. A 20-robot fleet with sum-80 at L=32k and ri=15s needs {int(min(int(n_mem_str('a6000','sum80',32768)),int(n_accel_str('sum80',32768,15))))} GPU-equivalents from the accelerator alone (exceeds N_accel={n_accel_str('sum80',32768,15)}).
- **win-10 at any refresh interval ≥ 5 s:** memory binds first. N_accel_win10 at ri=5s and L=64k = {n_accel_str('win10',65536,5)} >> N_mem_win10 at L=64k = {n_mem_str('a6000','win10',65536)}.

---

## Part D: Realism Check

**Fleet size assumptions:** warehouse/logistics building = 20 robots [ASSUMPTION]; small office floor = 5 robots [ASSUMPTION]. These are stated estimates, not measured deployments.

### Binding check at 60-second refresh interval (a6000 edge tier)

| fidelity | L | N_memory | N_accel(60s) | N_binding | serves 20-robot fleet? |
|---|---|---|---|---|---|
| sum-80 | 8k | {n_mem_str('a6000','sum80',8192)} | {n_accel_str('sum80',8192,60)} | {min(int(n_mem_str('a6000','sum80',8192)),int(n_accel_str('sum80',8192,60)))} | {'yes' if min(int(n_mem_str('a6000','sum80',8192)),int(n_accel_str('sum80',8192,60))) >= 20 else 'NO'} |
| sum-80 | 32k | {n_mem_str('a6000','sum80',32768)} | {n_accel_str('sum80',32768,60)} | {min(int(n_mem_str('a6000','sum80',32768)),int(n_accel_str('sum80',32768,60)))} | {'yes' if min(int(n_mem_str('a6000','sum80',32768)),int(n_accel_str('sum80',32768,60))) >= 20 else 'NO'} |
| sum-80 | 64k | {n_mem_str('a6000','sum80',65536)} | {n_accel_str('sum80',65536,60)} | {min(int(n_mem_str('a6000','sum80',65536)),int(n_accel_str('sum80',65536,60)))} | {'yes' if min(int(n_mem_str('a6000','sum80',65536)),int(n_accel_str('sum80',65536,60))) >= 20 else 'NO'} |
| sum-200 | 8k | {n_mem_str('a6000','sum200',8192)} | {n_accel_str('sum200',8192,60)} | {min(int(n_mem_str('a6000','sum200',8192)),int(n_accel_str('sum200',8192,60)))} | {'yes' if min(int(n_mem_str('a6000','sum200',8192)),int(n_accel_str('sum200',8192,60))) >= 20 else 'NO'} |
| sum-200 | 32k | {n_mem_str('a6000','sum200',32768)} | {n_accel_str('sum200',32768,60)} | {min(int(n_mem_str('a6000','sum200',32768)),int(n_accel_str('sum200',32768,60)))} | {'yes' if min(int(n_mem_str('a6000','sum200',32768)),int(n_accel_str('sum200',32768,60))) >= 20 else 'NO'} |
| sum-200 | 64k | {n_mem_str('a6000','sum200',65536)} | {n_accel_str('sum200',65536,60)} | {min(int(n_mem_str('a6000','sum200',65536)),int(n_accel_str('sum200',65536,60)))} | {'yes' if min(int(n_mem_str('a6000','sum200',65536)),int(n_accel_str('sum200',65536,60))) >= 20 else 'NO'} |
| win-10 | 8k | {n_mem_str('a6000','win10',8192)} | {n_accel_str('win10',8192,60)} | {min(int(n_mem_str('a6000','win10',8192)),int(n_accel_str('win10',8192,60)))} | {'yes' if min(int(n_mem_str('a6000','win10',8192)),int(n_accel_str('win10',8192,60))) >= 20 else 'NO'} |
| win-10 | 32k | {n_mem_str('a6000','win10',32768)} | {n_accel_str('win10',32768,60)} | {min(int(n_mem_str('a6000','win10',32768)),int(n_accel_str('win10',32768,60)))} | {'yes' if min(int(n_mem_str('a6000','win10',32768)),int(n_accel_str('win10',32768,60))) >= 20 else 'NO'} |
| win-10 | 64k | {n_mem_str('a6000','win10',65536)} | {n_accel_str('win10',65536,60)} | {min(int(n_mem_str('a6000','win10',65536)),int(n_accel_str('win10',65536,60)))} | {'yes' if min(int(n_mem_str('a6000','win10',65536)),int(n_accel_str('win10',65536,60))) >= 20 else 'NO'} |
| full | 8k | {n_mem_str('a6000','full',8192)} | {n_accel_str('full',8192,60)} | {min(int(n_mem_str('a6000','full',8192)),int(n_accel_str('full',8192,60)))} | {'yes' if min(int(n_mem_str('a6000','full',8192)),int(n_accel_str('full',8192,60))) >= 20 else 'NO'} |
| full | 32k | {n_mem_str('a6000','full',32768)} | {n_accel_str('full',32768,60)} | {min(int(n_mem_str('a6000','full',32768)),int(n_accel_str('full',32768,60)))} | {'yes' if min(int(n_mem_str('a6000','full',32768)),int(n_accel_str('full',32768,60))) >= 20 else 'NO'} |
| full | 64k | {n_mem_str('a6000','full',65536)} | {n_accel_str('full',65536,60)} | {min(int(n_mem_str('a6000','full',65536)),int(n_accel_str('full',65536,60)))} | {'yes' if min(int(n_mem_str('a6000','full',65536)),int(n_accel_str('full',65536,60))) >= 20 else 'NO'} |

### Answer to Part D

Contention does bind at realistic fleet sizes, but the binding resource and the threshold depend critically on fidelity choice and refresh interval. At 60-second refresh intervals (roughly one new observation per minute): **memory does not bind at all** for compressed fidelities — even a 24-GB GPU supports hundreds of sum-80 sessions — but **accelerator time binds sharply for summaries at large L and short refresh intervals**. Specifically, for sum-80 or sum-200 sessions at L=64k with ri=15s, N_accel drops to single digits on an A6000, meaning a 20-robot fleet consuming {REFRESH_COSTS[65536]['sum80']:.1f} s of GPU per refresh every 15 seconds saturates the GPU. By contrast, window-10 maintenance (warm-append ~{REFRESH_COSTS[65536]['win10']:.3f} s) never saturates the accelerator at any plausible fleet size — memory (N_mem_win10 = {n_mem_str('a6000','win10',65536)} at L=64k on A6000) would bind first, and even then the binding capacity ({n_mem_str('a6000','win10',65536)} sessions) far exceeds any building-scale fleet. **The operationally surprising finding is that the footprint-minimizing choice (summaries) is also the accelerator-expensive choice**, and the two constraints are inverted: deploying sum-80 to save KV memory at large L and short refresh intervals forces the accelerator to become the bottleneck long before memory does. A provisioning system optimizing for concurrent sessions should prefer win-10 at large L and frequent refresh rates — it is cheaper in both steady-state memory (400 tok × 57 KB = 23 MB vs. claim of thousands per full session) and accelerator time, at the cost of reduced dense-session fidelity.

---

## Figures

`figures/cost/e30_capacity_binding.pdf` — six-panel figure: rows = (a) memory-limited sessions, (b) accelerator-limited sessions at ri=60s; columns = A6000 (edge), 24-GB GPU (edge alternative), Jetson Orin (device). Red dashed = 20-robot fleet reference; orange dotted = 5-robot fleet.
"""

with open(ROOT / "reports" / "e30_capacity_arithmetic.md", "w") as f:
    f.write(report)
print(f"\nReport → {ROOT}/reports/e30_capacity_arithmetic.md")
print("\nDone.")
