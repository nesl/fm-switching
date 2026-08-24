"""
E36b (rewrite) — Corrected fleet policy experiment.

Four defects fixed vs E36/E36b-v1:
1. Incumbent is footprint_ranked (cache-value scoring by Q/KV_bytes). Primary
   comparison: maintenance_aware vs footprint_ranked, not vs device_only.
2. Correct 7 policies: device_only, always_full, always_window, always_summary,
   footprint_ranked, maintenance_aware, oracle. reactive and budget_aware dropped.
3. Binding-resource diagnostic: per policy per (n_robots, cap_frac) cell, which
   resource (KV memory or accelerator time) limited admission.
4. Quality model: admissibility constraint Q(f, model, workload) >= q_min,
   not Bernoulli draw. Primary metric: fraction served within TTFT budget from
   admissible representation. Latency miss and quality miss reported separately.

Committed inputs:
  Q table        E29  (results/fidelity/e29_tier_heterogeneous/)
  Edge costs     E35/E26 (cost_matrix.csv, phase1_cost_profiling.md)
  Jetson 7B      E23  (jetson_orin_qwen7b.json)
  A1 ratio       E37b (a1_ratio_table.csv)
  LoCoMo stats   E33a (22 turns/session, 7275-tok win10 median)

Assumptions (no new measurements):
  A1: device TTFT = measured 3B/7B ratio (E37, L-dependent, clamped at 16384).
  A2: EgoSchema context in [1500, 2500] tokens (range, not committed median).
  A3: Edge KV usable = 9 GiB (24 GB GPU - 15 GB model).
  A4: Turn interval = 30 s → accel budget = 30 000 ms/epoch per-edge-GPU. [ASSUMPTION]
      This is the binding threshold for sum200 (5854 ms/robot) at N >= 6.
  A5: win10 amortized maintenance = 652 ms/turn (E35 §Part A).
  A6: EgoSchema modeled as independent cold queries; no per-session refresh cost.
"""

import json
import random
import statistics
from collections import defaultdict, deque
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36b_fleet"

# ── COMMITTED MEASUREMENTS ────────────────────────────────────────────────────

KV_BYTES_PER_TOK_7B   = 57_344          # E23 kv_bytes_per_token
KV_BYTES_PER_TOK_3B   = 36_864          # E37
EDGE_KV_USABLE_BYTES  = 9 * 1024**3     # A3: 9 GiB

JETSON_7B_INCR_WARM    = {1024: 579.4, 2048: 666.8, 4096: 855.4,
                           8192: 1252.5, 16384: 2162.8}
JETSON_7B_FULL_RESTORE = {1024: 4052.5, 4096: 16310.6,
                           8192: 33790.3, 16384: 75053.7}
JETSON_7B_INFEASIBLE_L = 24576

A1_INCR_WARM_RATIO    = {1024: 0.5934, 4096: 0.6406, 8192: 0.6810, 16384: 0.7046}
A1_FULL_RESTORE_RATIO = {1024: 0.4749, 4096: 0.4960, 8192: 0.5175, 16384: 0.5419}

EDGE_FULL_WARM_APPEND_MS  = 66.0    # E26/E35
EDGE_WIN10_INTRA_MS       = 59.0    # E35
EDGE_WIN10_INTER_MS       = 1031.0  # E35
EDGE_SUM200_RESTORE_MS    = 32.0    # E35
EDGE_SUM200_UPDATE_MS     = 5822.0  # E35
EDGE_COLD_PREFILL_RATE    = 5984.0  # tok/s, E21/E26

WIN10_TOKENS    = 7_275    # E33a last-10-sessions median
SUM200_TOKENS   = 160      # E35 summary token count
LOCOMO_L_MEDIAN = 20_092   # E33a

# E29 Q table; edge model = qwen7b; device model = qwen3b
Q_TABLE = {
    ("full",   "locomo",    "qwen7b"): 0.400,
    ("win10",  "locomo",    "qwen7b"): 0.230,
    ("sum200", "locomo",    "qwen7b"): 0.120,
    ("full",   "locomo",    "qwen3b"): 0.230,
    ("win10",  "locomo",    "qwen3b"): 0.180,
    ("sum200", "locomo",    "qwen3b"): 0.120,
    ("full",   "egoschema", "qwen7b"): 0.567,
    ("win10",  "egoschema", "qwen7b"): 0.500,
    ("sum200", "egoschema", "qwen7b"): 0.483,
    ("full",   "egoschema", "qwen3b"): 0.450,
    ("win10",  "egoschema", "qwen3b"): 0.450,
    ("sum200", "egoschema", "qwen3b"): 0.433,
}

LOCOMO_CTX_TOKENS = [11386, 14665, 16212, 18894, 19325,
                     20860, 21125, 21592, 22266, 22778]
LOCOMO_N_SESSIONS = [19, 19, 25, 28, 29, 29, 30, 30, 31, 32]
TURNS_PER_SESSION = 22

EGOSCHEMA_CTX_TOKENS = [1500, 1800, 2000, 2200, 2500]

WORKLOADS    = ["locomo", "egoschema"]
TTFT_BUDGETS = [300.0, 1000.0, 10000.0]
QUALITY_SLOS = [0.20, 0.30, 0.40]
POLICY_NAMES = [
    "device_only",
    "always_full", "always_window", "always_summary",
    "footprint_ranked", "maintenance_aware", "oracle",
]

FIDELITIES = ["full", "win10", "sum200"]

# A4: accelerator budget per epoch (total GPU-ms available for all admitted robots)
TURN_INTERVAL_MS = 30_000.0   # [ASSUMPTION] 30 s between turns

# Maintenance cost per turn per robot on edge (E35)
MAINT_MS = {
    "full":   EDGE_FULL_WARM_APPEND_MS,   # 66 ms (warm append = maintenance)
    "win10":  652.0,                       # E35 amortized (A5)
    "sum200": EDGE_SUM200_UPDATE_MS,       # 5822 ms (background regeneration)
}

# ── LATENCY HELPERS ───────────────────────────────────────────────────────────

def _interp(table, L):
    keys = sorted(table)
    if L <= keys[0]:
        return table[keys[0]] * L / keys[0]
    if L > keys[-1]:
        rate = keys[-1] / table[keys[-1]]
        return L / rate
    for i in range(len(keys) - 1):
        if keys[i] <= L <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            f = (L - lo) / (hi - lo)
            return (1 - f) * table[lo] + f * table[hi]


def _interp_ratio(rtable, L):
    keys = sorted(rtable)
    if L <= keys[0]:
        return rtable[keys[0]]
    if L >= keys[-1]:
        return rtable[keys[-1]]
    for i in range(len(keys) - 1):
        if keys[i] <= L <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            f = (L - lo) / (hi - lo)
            return (1 - f) * rtable[lo] + f * rtable[hi]


def device_incr_warm_ms(L):
    if L >= JETSON_7B_INFEASIBLE_L:
        return None
    v7 = _interp(JETSON_7B_INCR_WARM, L)
    return v7 * _interp_ratio(A1_INCR_WARM_RATIO, L)


def device_cold_restore_ms(L):
    if L >= JETSON_7B_INFEASIBLE_L:
        return None
    v7 = _interp(JETSON_7B_FULL_RESTORE, L)
    return v7 * _interp_ratio(A1_FULL_RESTORE_RATIO, L)


def edge_cold_restore_ms(L_tok):
    return (L_tok / EDGE_COLD_PREFILL_RATE) * 1000.0


def edge_serve_ms(fidelity, workload, context_L, is_session_start, newly_admitted):
    """TTFT for a single query served from edge with the given fidelity."""
    if workload == "egoschema":
        if fidelity == "sum200":
            return EDGE_SUM200_RESTORE_MS
        if fidelity == "win10":
            return EDGE_WIN10_INTRA_MS
        return edge_cold_restore_ms(context_L)   # full: cold per query (A6)
    # LoCoMo
    if newly_admitted:
        if fidelity == "full":
            return edge_cold_restore_ms(context_L)
        if fidelity == "win10":
            return edge_cold_restore_ms(WIN10_TOKENS)
        return EDGE_SUM200_RESTORE_MS
    if fidelity == "full":
        return EDGE_FULL_WARM_APPEND_MS
    if fidelity == "win10":
        return EDGE_WIN10_INTER_MS if is_session_start else EDGE_WIN10_INTRA_MS
    return EDGE_SUM200_RESTORE_MS


def refresh_ms(fidelity, workload):
    """Out-of-band accelerator cost for maintaining fidelity state after a turn.
    For LoCoMo: full and win10 maintenance is captured in serve_ms (warm append).
    Sum200 requires a separate update pass. EgoSchema: no refresh (A6)."""
    if workload == "egoschema":
        return 0.0
    if fidelity == "sum200":
        return EDGE_SUM200_UPDATE_MS    # background regeneration, still uses GPU
    return 0.0  # full/win10: maintenance fused into TTFT


def kv_bytes(fidelity, context_L):
    if fidelity == "full":
        return int(max(context_L, 1) * KV_BYTES_PER_TOK_7B)
    if fidelity == "win10":
        return WIN10_TOKENS * KV_BYTES_PER_TOK_7B
    return SUM200_TOKENS * KV_BYTES_PER_TOK_7B


# ── FIDELITY SELECTORS (per-robot, policy-specific) ──────────────────────────

def admissible(workload, q_min):
    return [f for f in FIDELITIES
            if Q_TABLE.get((f, workload, "qwen7b"), 0.0) >= q_min]


def _fp_ranked_fidelity(workload, q_min, context_L):
    """footprint_ranked: highest Q/KV_bytes among admissible."""
    adm = admissible(workload, q_min)
    if not adm:
        return None
    return max(adm, key=lambda f: Q_TABLE[(f, workload, "qwen7b")] / kv_bytes(f, context_L))


def _maint_aware_fidelity(workload, q_min):
    """maintenance_aware: lowest maintenance_cost/Q among admissible."""
    adm = admissible(workload, q_min)
    if not adm:
        return None
    return min(adm, key=lambda f: MAINT_MS[f] / Q_TABLE[(f, workload, "qwen7b")])


def _oracle_fidelity(workload, q_min):
    """oracle: highest Q among admissible (full future knowledge)."""
    adm = admissible(workload, q_min)
    if not adm:
        return None
    return max(adm, key=lambda f: Q_TABLE[(f, workload, "qwen7b")])


# ── STAGE 0 ───────────────────────────────────────────────────────────────────

def _locomo_lat_fail(budget_ms):
    fails = total = 0
    for ctx, n_sess in zip(LOCOMO_CTX_TOKENS, LOCOMO_N_SESSIONS):
        tps = ctx / n_sess
        tpt = tps / TURNS_PER_SESSION
        for s in range(n_sess):
            for t in range(TURNS_PER_SESSION):
                L  = s * tps + t * tpt
                ms = device_incr_warm_ms(L)
                total += 1
                if ms is None or ms > budget_ms:
                    fails += 1
    return fails / total


def _ego_lat_fail(budget_ms):
    fails = sum(1 for L in EGOSCHEMA_CTX_TOKENS
                if (lambda v: v is None or v > budget_ms)(device_cold_restore_ms(L)))
    return fails / len(EGOSCHEMA_CTX_TOKENS)


def run_stage0():
    print("=" * 70)
    print("STAGE 0 — Headroom Gate (measured A1, admissibility model)")
    print("=" * 70)
    cells = []
    n_nd  = 0
    hdr   = (f"{'workload':12s} {'budget':>7s} {'q_slo':>5s} | "
             f"{'Q_dev':>5s} {'adm?':>6s} | {'lat_fail':>8s} | {'disc?':>5s}")
    print(hdr)
    print("-" * len(hdr))
    for wl in WORKLOADS:
        Q_dev = Q_TABLE[("full", wl, "qwen3b")]
        lat_fn = _locomo_lat_fail if wl == "locomo" else _ego_lat_fail
        for budget in TTFT_BUDGETS:
            lat = lat_fn(budget)
            for q_slo in QUALITY_SLOS:
                q_ok = Q_dev >= q_slo
                disc = (not q_ok) or (lat > 0.05)
                if not disc:
                    n_nd += 1
                print(f"{wl:12s} {budget:>7.0f} {q_slo:>5.2f} | "
                      f"{Q_dev:>5.3f} {'OK' if q_ok else 'FAIL':>6s} | "
                      f"{lat:>8.1%} | {'YES' if disc else 'NO':>5s}")
                cells.append({
                    "workload": wl, "budget_ms": budget, "q_slo": q_slo,
                    "Q_device": Q_dev, "q_ok": q_ok,
                    "lat_fail": round(lat, 4), "discriminating": disc,
                })
    total = len(cells)
    gate  = n_nd / total <= 0.50
    print(f"\n  Non-discriminating: {n_nd}/{total} ({n_nd/total:.0%})")
    print(f"  K1: {'PASS' if gate else 'FAIL — stop before Stage 1'}")
    return {"gate_passes": gate, "n_nd": n_nd, "n_total": total, "cells": cells}


# ── SIMULATION CORE ───────────────────────────────────────────────────────────

class Robot:
    __slots__ = ["rid", "context_L", "tok_per_turn", "n_sess",
                 "session_idx", "turn_in_session", "conv_idx"]

    def __init__(self, rid, ctx_total, n_sess, conv_idx):
        self.rid             = rid
        self.n_sess          = n_sess
        self.conv_idx        = conv_idx
        self.tok_per_turn    = (ctx_total / n_sess) / TURNS_PER_SESSION
        self.context_L       = 0.0
        self.session_idx     = 0
        self.turn_in_session = 0

    def step(self):
        self.turn_in_session += 1
        self.context_L       += self.tok_per_turn
        if self.turn_in_session >= TURNS_PER_SESSION:
            self.turn_in_session = 0
            self.session_idx    += 1

    @property
    def is_session_start(self):
        return self.turn_in_session == 0

    @property
    def active(self):
        return self.session_idx < self.n_sess


def _lru_admit(lru_order, prev_kv, robots, kv_budget, fidelity):
    """LRU admission for always_X policies. Returns new_kv dict."""
    # lru_order: deque of rids, most-recently-used at right
    new_kv   = {}
    kv_used  = 0
    # Re-admit robots in LRU order (most-recently-used get priority)
    ordered  = list(lru_order)  # oldest first
    lru_order.clear()
    for rid in reversed(ordered):                    # most recent first
        r   = robots[rid]
        kvb = kv_bytes(fidelity, r.context_L)
        if kv_used + kvb <= kv_budget:
            new_kv[rid] = fidelity
            kv_used    += kvb
            lru_order.appendleft(rid)                # maintain order
    # Robots not in new_kv fall to device; they lose their LRU slot
    lru_order_final = deque()
    for rid in lru_order:
        if rid in new_kv:
            lru_order_final.append(rid)
    lru_order.clear()
    lru_order.extend(lru_order_final)
    return new_kv, kv_used


def _greedy_admit(robots, kv_budget, accel_budget, workload, q_slo, policy):
    """Greedy admission for footprint_ranked, maintenance_aware, oracle."""
    # Build (priority, rid, fidelity, kv, accel_cost) for each robot
    candidates = []
    for rid, r in robots.items():
        if policy == "footprint_ranked":
            fid = _fp_ranked_fidelity(workload, q_slo, r.context_L)
        elif policy == "maintenance_aware":
            fid = _maint_aware_fidelity(workload, q_slo)
        else:  # oracle
            fid = _oracle_fidelity(workload, q_slo)
        if fid is None:
            continue
        kvb  = kv_bytes(fid, r.context_L)
        acms = (MAINT_MS[fid] + refresh_ms(fid, workload))
        if policy == "footprint_ranked":
            priority = Q_TABLE[(fid, workload, "qwen7b")] / kvb
        elif policy == "maintenance_aware":
            priority = -(MAINT_MS[fid] / Q_TABLE[(fid, workload, "qwen7b")])
        else:
            priority = Q_TABLE[(fid, workload, "qwen7b")]
        candidates.append((priority, rid, fid, kvb, acms))

    candidates.sort(reverse=True, key=lambda x: x[0])

    new_kv     = {}
    kv_used    = 0
    accel_used = 0
    kv_bound_hit   = False
    accel_bound_hit = False
    for _, rid, fid, kvb, acms in candidates:
        kv_ok    = kv_used + kvb <= kv_budget
        # accel constraint only enforced for maintenance_aware
        accel_ok = (policy != "maintenance_aware") or (accel_used + acms <= accel_budget)
        if kv_ok and accel_ok:
            new_kv[rid] = fid
            kv_used    += kvb
            accel_used += acms
        else:
            if not kv_ok:
                kv_bound_hit = True
            if not accel_ok:
                accel_bound_hit = True

    return new_kv, kv_used, accel_used, kv_bound_hit, accel_bound_hit


def run_one(policy, n_robots, kv_budget_bytes, workload, q_slo, seed):
    rng = random.Random(seed)

    # Build robot pool from LoCoMo conversation statistics
    robots = {}
    for rid in range(n_robots):
        conv_idx = rid % len(LOCOMO_CTX_TOKENS)
        ctx      = LOCOMO_CTX_TOKENS[conv_idx]
        n_sess   = LOCOMO_N_SESSIONS[conv_idx]
        robots[rid] = Robot(rid, ctx, n_sess, conv_idx)

    # For EgoSchema each robot draws a random context per query
    ego_ctx = list(EGOSCHEMA_CTX_TOKENS)

    # LRU deque for always_X policies
    lru_order = deque(range(n_robots))   # all robots start equally aged

    # Track warm-KV state across epochs
    prev_kv = {}   # rid -> fidelity

    # Accumulators
    records = []   # per-query: (ttft, admissible_quality, lat_miss, qual_miss)
    accel_serve_total = 0.0
    accel_refresh_total = 0.0
    accel_materialize_total = 0.0
    kv_bound_epochs = 0
    accel_bound_epochs = 0

    n_sessions_max = max(LOCOMO_N_SESSIONS)  # 32
    total_turns    = n_sessions_max * TURNS_PER_SESSION

    for epoch in range(total_turns):
        # Determine active robots this epoch
        active = {rid: r for rid, r in robots.items() if r.active}
        if not active:
            break

        # Compute admission for this epoch
        kv_bound   = False
        accel_bound = False

        if policy == "device_only":
            new_kv = {}

        elif policy in ("always_full", "always_window", "always_summary"):
            fid_map = {"always_full": "full", "always_window": "win10",
                       "always_summary": "sum200"}
            fid = fid_map[policy]
            # Check admissibility; if chosen fidelity not admissible, fall to device
            if Q_TABLE.get((fid, workload, "qwen7b"), 0.0) >= q_slo:
                # LRU admission within KV budget for active robots only
                active_lru = deque(r for r in lru_order if r in active)
                new_kv  = {}
                kv_used = 0
                # Most-recently-used (right side) get priority
                lru_list = list(active_lru)
                for rid in reversed(lru_list):
                    kvb = kv_bytes(fid, active[rid].context_L)
                    if kv_used + kvb <= kv_budget_bytes:
                        new_kv[rid] = fid
                        kv_used    += kvb
                    else:
                        kv_bound = True
                # Rebuild LRU order: admitted first (maintain relative order),
                # then non-admitted (they get evicted to back of queue)
                remaining = [r for r in lru_list if r in new_kv]
                evicted   = [r for r in lru_list if r not in new_kv]
                lru_order.clear()
                for r in evicted:
                    lru_order.appendleft(r)   # evicted to front (oldest)
                for r in remaining:
                    lru_order.append(r)        # admitted to back (newest)
            else:
                new_kv   = {}   # fidelity not admissible; everyone falls to device
                kv_bound = False

        else:  # footprint_ranked, maintenance_aware, oracle
            new_kv, kv_used, accel_used, kv_bound, accel_bound = _greedy_admit(
                active, kv_budget_bytes, TURN_INTERVAL_MS,
                workload, q_slo, policy)

        if kv_bound:
            kv_bound_epochs    += 1
        if accel_bound:
            accel_bound_epochs += 1

        # Score each robot
        for rid, r in active.items():
            is_ss       = r.is_session_start
            if rid in new_kv:
                fid         = new_kv[rid]
                newly       = (rid not in prev_kv) or (prev_kv[rid] != fid)
                if workload == "egoschema":
                    L_q = rng.choice(ego_ctx)
                    ttft = edge_serve_ms(fid, workload, L_q, is_ss, newly)
                else:
                    ttft = edge_serve_ms(fid, workload, r.context_L, is_ss, newly)
                Q_edge = Q_TABLE.get((fid, workload, "qwen7b"), 0.0)
                qual_ok = Q_edge >= q_slo
                # Accel accounting
                if newly:
                    accel_materialize_total += ttft
                else:
                    accel_serve_total += ttft
                accel_refresh_total += refresh_ms(fid, workload)
            else:
                # Fall to device
                if workload == "egoschema":
                    L_q  = rng.choice(ego_ctx)
                    ms   = device_cold_restore_ms(L_q)
                    ttft = ms if ms is not None else 120_000.0
                else:
                    ms   = device_incr_warm_ms(r.context_L)
                    ttft = ms if ms is not None else 120_000.0
                Q_dev  = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)
                qual_ok = Q_dev >= q_slo
                fid = None

            records.append((ttft, qual_ok))
            r.step()

        prev_kv = dict(new_kv)

    n_q  = len(records)
    result = {
        "policy": policy, "n_robots": n_robots,
        "kv_budget_bytes": kv_budget_bytes,
        "workload": workload, "q_slo": q_slo, "seed": seed,
        "n_queries": n_q,
    }

    for budget in TTFT_BUDGETS:
        n_both  = sum(1 for ttft, qok in records if ttft <= budget and qok)
        n_lat   = sum(1 for ttft, _   in records if ttft <= budget)
        n_qual  = sum(1 for _,    qok in records if qok)
        result[f"both_met_{int(budget)}ms"]   = round(n_both / n_q, 4)
        result[f"lat_met_{int(budget)}ms"]    = round(n_lat  / n_q, 4)
        result[f"lat_miss_{int(budget)}ms"]   = round((n_q - n_lat) / n_q, 4)
    result["qual_met"]       = round(sum(1 for _, qok in records if qok) / n_q, 4)
    result["qual_miss"]      = round(sum(1 for _, qok in records if not qok) / n_q, 4)
    result["kv_bound_frac"]  = round(kv_bound_epochs / max(1, total_turns), 4)
    result["accel_bound_frac"] = round(accel_bound_epochs / max(1, total_turns), 4)
    # binding resource: whichever fired more often
    if kv_bound_epochs == 0 and accel_bound_epochs == 0:
        result["binding_resource"] = "neither"
    elif kv_bound_epochs >= accel_bound_epochs:
        result["binding_resource"] = "memory"
    else:
        result["binding_resource"] = "accelerator"
    # Accel utilization split (totals in ms, normalized by epoch count)
    result["accel_serve_ms_per_epoch"]       = round(accel_serve_total / max(1, total_turns), 1)
    result["accel_refresh_ms_per_epoch"]     = round(accel_refresh_total / max(1, total_turns), 1)
    result["accel_materialize_ms_per_epoch"] = round(accel_materialize_total / max(1, total_turns), 1)
    accel_total_per_epoch = (accel_serve_total + accel_refresh_total + accel_materialize_total) / max(1, total_turns)
    result["accel_util_frac"] = round(accel_total_per_epoch / TURN_INTERVAL_MS, 4)
    return result


# ── STAGE 1 ───────────────────────────────────────────────────────────────────

N_ROBOTS_LIST = [5, 10, 20, 30, 50]
CAP_FRACS     = [0.25, 0.50, 0.75, 1.00]
SEEDS         = (42, 99, 137)


def run_stage1():
    total = (len(POLICY_NAMES) * len(WORKLOADS) * len(QUALITY_SLOS)
             * len(N_ROBOTS_LIST) * len(CAP_FRACS) * len(SEEDS))
    print(f"\n{'='*70}")
    print(f"STAGE 1 — Policy Sweep  ({total} runs)")
    print(f"  Policies: {', '.join(POLICY_NAMES)}")
    print(f"  Fleet sizes: {N_ROBOTS_LIST};  cap_fracs: {CAP_FRACS}")
    print(f"  KV budget = cap_frac × n_robots × KV_bytes(full, L_median={LOCOMO_L_MEDIAN})")
    print(f"  Accel budget: {TURN_INTERVAL_MS:.0f} ms/epoch [ASSUMPTION A4]")
    print(f"{'='*70}")

    KV_FULL_MEDIAN = int(LOCOMO_L_MEDIAN * KV_BYTES_PER_TOK_7B)

    results = []
    done    = 0
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            for nr in N_ROBOTS_LIST:
                for cf in CAP_FRACS:
                    kv_bud = int(cf * nr * KV_FULL_MEDIAN)
                    for seed in SEEDS:
                        for pol in POLICY_NAMES:
                            r = run_one(pol, nr, kv_bud, wl, q_slo, seed)
                            r["cap_frac"] = cf
                            results.append(r)
                            done += 1
                            if done % 200 == 0:
                                print(f"  {done}/{total} …")

    print(f"  {total}/{total} done.")
    return {"n_runs": len(results), "results": results,
            "kv_full_median_bytes": KV_FULL_MEDIAN}


# ── STAGE 2 ───────────────────────────────────────────────────────────────────

def run_stage2(stage1):
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("STAGE 2 — Per-cell analysis (admissibility model)")
    print(f"  Primary comparison: maintenance_aware vs footprint_ranked")
    print(f"{'='*70}")

    # Average over cap_frac and fleet size within (workload, budget, q_slo) cells
    # Also report per-(n_robots, cap_frac) for each policy
    sums = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for budget in TTFT_BUDGETS:
            key = (r["workload"], budget, r["q_slo"])
            sums[key][r["policy"]].append(r[f"both_met_{int(budget)}ms"])

    cells_out    = []
    k2_violations = []   # maintenance_aware vs device_only < 5pp
    kc_violations = []   # footprint_ranked beats or ties maintenance_aware to < 5pp margin

    INCUMBENT = "footprint_ranked"
    PROPOSED  = "maintenance_aware"

    for key in sorted(sums):
        wl, budget, q_slo = key
        pol_means = {p: statistics.mean(v) for p, v in sums[key].items()}
        ranked    = sorted(pol_means, key=pol_means.get, reverse=True)

        dev_mean  = pol_means.get("device_only", 0.0)
        lc_mean   = pol_means.get(PROPOSED,      0.0)
        fp_mean   = pol_means.get(INCUMBENT,     0.0)
        gap_lc_dev = (lc_mean - dev_mean) * 100.0
        gap_lc_fp  = (lc_mean - fp_mean)  * 100.0

        k2_ok = gap_lc_dev >= 5.0
        if not k2_ok:
            k2_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "gap_pp": round(gap_lc_dev, 2)})
        # Kill condition (c): footprint_ranked within 5pp of maintenance_aware (either direction)
        kc = abs(gap_lc_fp) < 5.0
        if kc:
            kc_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "gap_lc_minus_fp_pp": round(gap_lc_fp, 2)})

        cell = {
            "workload": wl, "budget_ms": budget, "q_slo": q_slo,
            "ranking": [{"policy": p, "both_met": round(pol_means[p], 4),
                          "gap_vs_device_pp": round((pol_means[p] - dev_mean) * 100, 2)}
                        for p in ranked],
            "maintenance_aware_vs_device_pp": round(gap_lc_dev, 2),
            "maintenance_aware_vs_footprint_pp": round(gap_lc_fp, 2),
            "k2_ok": k2_ok,
        }
        cells_out.append(cell)

    # Print table
    print(f"\n{'wl':12s} {'bud':>7s} {'q':>4s} | "
          f"{'dev':>6s} {'fp_rank':>8s} {'maint':>7s} | "
          f"{'maint-fp':>9s} | {'maint-dev':>10s} K2")
    print("-" * 74)
    for c in cells_out:
        def _g(pol):
            return next((x["both_met"] for x in c["ranking"] if x["policy"] == pol), 0.0)
        print(f"{c['workload']:12s} {c['budget_ms']:>7.0f} {c['q_slo']:>4.2f} | "
              f"{_g('device_only'):>6.3f} {_g(INCUMBENT):>8.3f} {_g(PROPOSED):>7.3f} | "
              f"{c['maintenance_aware_vs_footprint_pp']:>+8.1f}pp | "
              f"{c['maintenance_aware_vs_device_pp']:>+8.1f}pp {'PASS' if c['k2_ok'] else 'FAIL'}")

    print()
    print(f"K2 (maint_aware vs device >=5pp): "
          f"{'PASS' if not k2_violations else f'FAIL ({len(k2_violations)} cells)'}")
    print(f"KC (maint_aware vs footprint within 5pp): "
          f"{'FIRES ({} cells)'.format(len(kc_violations)) if kc_violations else 'no-fire'}")

    # Kill conditions summary
    kill = {}
    # (a) always_window within 5pp of maintenance_aware
    kill["a_always_window"] = sum(
        1 for c in cells_out
        if abs(c["maintenance_aware_vs_device_pp"] -
               next((x["gap_vs_device_pp"] for x in c["ranking"]
                     if x["policy"] == "always_window"), 0.0)) < 5.0
    )
    # (b) always_full within 5pp of maintenance_aware
    kill["b_always_full"] = sum(
        1 for c in cells_out
        if abs(next((x["both_met"] for x in c["ranking"] if x["policy"] == "always_full"), 0.0) -
               next((x["both_met"] for x in c["ranking"] if x["policy"] == "maintenance_aware"), 0.0))
        * 100 < 5.0
    )
    # (c) footprint_ranked within 5pp of maintenance_aware
    kill["c_footprint_ranked"] = len(kc_violations)
    print(f"\nKill conditions (cells where condition fires / {len(cells_out)} total):")
    print(f"  (a) always_window within 5pp of maint_aware: {kill['a_always_window']}")
    print(f"  (b) always_full   within 5pp of maint_aware: {kill['b_always_full']}")
    print(f"  (c) footprint_ranked within 5pp of maint_aware: {kill['c_footprint_ranked']}")

    return {
        "cells": cells_out,
        "k2_violations": k2_violations,
        "kc_violations": kc_violations,
        "k2_passes": not k2_violations,
        "kill_summary": kill,
    }


# ── BINDING RESOURCE DIAGNOSTIC ───────────────────────────────────────────────

def run_binding_diagnostic(stage1):
    """Per-policy per-fleet-size binding resource and accelerator utilization split."""
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("BINDING RESOURCE DIAGNOSTIC")
    print(f"  Which resource limits admission per policy per fleet size?")
    print(f"  Accel util = (serve+refresh+materialize) / {TURN_INTERVAL_MS:.0f} ms")
    print(f"{'='*70}")

    # Average over workloads, q_slo, cap_frac, seeds within (policy, n_robots)
    by_pol_nr = defaultdict(list)
    for r in rows:
        by_pol_nr[(r["policy"], r["n_robots"])].append(r)

    diag_rows = []
    print(f"\n{'policy':20s} {'n_rob':>5s} | {'kv_bound%':>9s} {'ac_bound%':>9s} {'binding':>9s} | "
          f"{'ac_serve':>8s} {'ac_refr':>7s} {'ac_mat':>7s} {'ac_util%':>8s}")
    print("-" * 90)

    for pol in POLICY_NAMES:
        for nr in N_ROBOTS_LIST:
            rlist = by_pol_nr.get((pol, nr), [])
            if not rlist:
                continue
            kv_b   = statistics.mean(r["kv_bound_frac"]   for r in rlist)
            ac_b   = statistics.mean(r["accel_bound_frac"] for r in rlist)
            ac_s   = statistics.mean(r["accel_serve_ms_per_epoch"]       for r in rlist)
            ac_r   = statistics.mean(r["accel_refresh_ms_per_epoch"]     for r in rlist)
            ac_m   = statistics.mean(r["accel_materialize_ms_per_epoch"] for r in rlist)
            ac_u   = statistics.mean(r["accel_util_frac"] for r in rlist)
            bind   = "memory" if kv_b >= ac_b else "accel" if ac_b > 0 else "neither"
            print(f"{pol:20s} {nr:>5d} | {kv_b:>9.1%} {ac_b:>9.1%} {bind:>9s} | "
                  f"{ac_s:>8.0f} {ac_r:>7.0f} {ac_m:>7.0f} {ac_u:>8.1%}")
            diag_rows.append({
                "policy": pol, "n_robots": nr,
                "kv_bound_frac": round(kv_b, 4), "accel_bound_frac": round(ac_b, 4),
                "binding": bind,
                "accel_serve_ms": round(ac_s, 1), "accel_refresh_ms": round(ac_r, 1),
                "accel_materialize_ms": round(ac_m, 1), "accel_util_frac": round(ac_u, 4),
            })
        print()

    # Kill condition (d): accelerator never binds for any policy/fleet-size
    any_accel_bind = any(r["accel_bound_frac"] > 0 for r in diag_rows)
    print(f"Kill condition (d) — accelerator never binds: "
          f"{'FIRES (accel never binds for any policy)' if not any_accel_bind else 'no-fire (accel binds in some cells)'}")

    return {"rows": diag_rows, "kd_fires": not any_accel_bind}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    s0 = run_stage0()
    (OUT_DIR / "stage0_headroom.json").write_text(json.dumps(s0, indent=2))
    if not s0["gate_passes"]:
        print("Stopping: K1 FAIL.")
        return

    s1 = run_stage1()
    (OUT_DIR / "stage1_sweep.json").write_text(json.dumps(s1, indent=2))
    print(f"Stage 1 saved: {s1['n_runs']} runs.")

    s2 = run_stage2(s1)
    (OUT_DIR / "stage2_analysis.json").write_text(json.dumps(s2, indent=2))

    bd = run_binding_diagnostic(s1)
    (OUT_DIR / "binding_diagnostic.json").write_text(json.dumps(bd, indent=2))

    print(f"\nAll outputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
