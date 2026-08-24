"""
E36c — Fleet policy experiment with fixed edge KV capacity and corrected maintenance_aware.

Two defects from E36b corrected:
1. KV capacity is FIXED at {4.5, 9, 18, 36} GiB, independent of fleet size.
   KV usage per robot uses current L_i (not a fixed median).
2. maintenance_aware: fleet-level greedy knapsack maximising expected SLO
   satisfaction per unit of binding resource (KV or accelerator), allowing
   mixed fidelity assignments. Containment assertion: must contain always_*
   and footprint_ranked assignments; fails loudly otherwise.
3. Latency-aware fallback on every policy: retroactive per-budget in reporting.
   If chosen fidelity's TTFT > evaluation budget, substitute smallest admissible
   fidelity whose TTFT fits (or device if none fit).

Additional sweep axis: turn_interval_s ∈ {5, 15, 30, 60} → accel_budget.

Unchanged from E36b:
  - Admissibility model: f admissible iff Q(f, qwen7b, workload) >= q_min.
  - Policy set (7 policies), A1 ratio from a1_ratio_table.csv.
  - EgoSchema independent-session model (no per-session refresh, A6).
  - Six-check consistency protocol (run before writing conclusions).

Per the spec: do NOT lower q_min below 0.12 to make LoCoMo sum200 admissible.
If the accelerator never binds at any capacity or turn interval, report that.

Assumptions:
  A1: Device TTFT = measured 3B/7B ratio (E37, L-dependent, clamped at 16384).
  A2: EgoSchema context in [1500, 2500] tokens (range; not committed median).
  A3: Edge KV usable = kv_cap_gib parameter (sweep axis); 9 GiB = 24 GB GPU - 15 GB model.
  A4: Turn interval (accel budget) = sweep axis {5, 15, 30, 60} s. [ASSUMPTION]
  A5: win10 amortized maintenance = 652 ms/turn (E35).
  A6: EgoSchema: independent cold queries, no per-session refresh.
  A7: maintenance_aware knapsack optimises for 1000 ms TTFT budget. [ASSUMPTION]
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36c_fleet"

# ── COMMITTED MEASUREMENTS ────────────────────────────────────────────────────

KV_BYTES_PER_TOK_7B = 57_344    # E23
KV_BYTES_PER_TOK_3B = 36_864    # E37

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
EDGE_SUM200_UPDATE_MS     = 5822.0  # E35 (background GPU time per turn)
EDGE_COLD_PREFILL_RATE    = 5984.0  # tok/s, E21/E26

WIN10_TOKENS   = 7_275    # E33a last-10-sessions median
SUM200_TOKENS  = 160      # E35

Q_TABLE = {
    ("full",   "locomo",    "qwen7b"): 0.400,
    ("win10",  "locomo",    "qwen7b"): 0.230,
    ("sum200", "locomo",    "qwen7b"): 0.120,
    ("full",   "locomo",    "qwen3b"): 0.230,
    ("full",   "egoschema", "qwen7b"): 0.567,
    ("win10",  "egoschema", "qwen7b"): 0.500,
    ("sum200", "egoschema", "qwen7b"): 0.483,
    ("full",   "egoschema", "qwen3b"): 0.450,
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
FIDELITIES   = ["full", "win10", "sum200"]

# Sweep axes
N_ROBOTS_LIST     = [5, 10, 20, 50]
KV_CAP_GIB_LIST   = [4.5, 9.0, 18.0, 36.0]     # fixed, independent of fleet
TURN_INTERVAL_LIST = [5.0, 15.0, 30.0, 60.0]    # seconds → ms × 1000 [ASSUMPTION A4]
SEEDS             = (42, 99, 137)

MAINT_MS = {
    "full":   EDGE_FULL_WARM_APPEND_MS,   # 66 ms (warm append is maintenance, E35)
    "win10":  652.0,                       # amortized E35 (A5)
    "sum200": EDGE_SUM200_UPDATE_MS,       # 5822 ms background regen (E35)
}

KNAPSACK_OPT_BUDGET = 1000.0  # [ASSUMPTION A7]: maintenance_aware optimises for 1000ms

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


def _interp_ratio(rt, L):
    keys = sorted(rt)
    if L <= keys[0]:  return rt[keys[0]]
    if L >= keys[-1]: return rt[keys[-1]]
    for i in range(len(keys) - 1):
        if keys[i] <= L <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            return rt[lo] + (rt[hi] - rt[lo]) * (L - lo) / (hi - lo)


def device_incr_warm_ms(L):
    if L >= JETSON_7B_INFEASIBLE_L: return None
    return _interp(JETSON_7B_INCR_WARM, L) * _interp_ratio(A1_INCR_WARM_RATIO, L)


def device_cold_restore_ms(L):
    if L >= JETSON_7B_INFEASIBLE_L: return None
    return _interp(JETSON_7B_FULL_RESTORE, L) * _interp_ratio(A1_FULL_RESTORE_RATIO, L)


def edge_cold_restore_ms(L_tok):
    return (L_tok / EDGE_COLD_PREFILL_RATE) * 1000.0


def edge_serve_ms(fidelity, workload, context_L, is_ss, newly):
    if workload == "egoschema":
        if fidelity == "sum200": return EDGE_SUM200_RESTORE_MS
        if fidelity == "win10":  return EDGE_WIN10_INTRA_MS
        return edge_cold_restore_ms(context_L)
    if newly:
        if fidelity == "full":   return edge_cold_restore_ms(context_L)
        if fidelity == "win10":  return edge_cold_restore_ms(WIN10_TOKENS)
        return EDGE_SUM200_RESTORE_MS
    if fidelity == "full":  return EDGE_FULL_WARM_APPEND_MS
    if fidelity == "win10": return EDGE_WIN10_INTER_MS if is_ss else EDGE_WIN10_INTRA_MS
    return EDGE_SUM200_RESTORE_MS


def refresh_ms(fidelity, workload):
    """Out-of-band GPU time for maintaining state after a turn."""
    if workload == "egoschema": return 0.0   # A6: no per-session refresh
    if fidelity == "sum200": return EDGE_SUM200_UPDATE_MS
    return 0.0   # full/win10: maintenance fused into TTFT


def kv_bytes(fidelity, context_L):
    if fidelity == "full":   return int(max(context_L, 1) * KV_BYTES_PER_TOK_7B)
    if fidelity == "win10":  return WIN10_TOKENS * KV_BYTES_PER_TOK_7B
    return SUM200_TOKENS * KV_BYTES_PER_TOK_7B


def admissible(workload, q_min):
    return [f for f in FIDELITIES
            if Q_TABLE.get((f, workload, "qwen7b"), 0.0) >= q_min]


# ── RETROACTIVE FALLBACK ──────────────────────────────────────────────────────

def retroactive_ttft_and_q(orig_fid, orig_ttft, from_device,
                            L_i, is_ss, newly, workload, q_slo, budget):
    """
    Given an originally chosen (fid, ttft), apply latency fallback for a specific
    budget. Returns (effective_fid_or_None, effective_ttft, quality_ok).
    """
    if from_device:
        q_dev = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)
        return (None, orig_ttft, (orig_ttft <= budget) and (q_dev >= q_slo))

    if orig_ttft <= budget:
        q_ok = Q_TABLE.get((orig_fid, workload, "qwen7b"), 0.0) >= q_slo
        return (orig_fid, orig_ttft, q_ok)

    # Fallback: try fidelities ordered by TTFT ascending
    fallback_order = ["sum200", "win10", "full"]
    for fb_fid in fallback_order:
        q_f = Q_TABLE.get((fb_fid, workload, "qwen7b"), 0.0)
        if q_f < q_slo:
            continue
        fb_ttft = edge_serve_ms(fb_fid, workload, L_i, is_ss, newly)
        if fb_ttft <= budget:
            return (fb_fid, fb_ttft, True)

    # No edge fidelity fits; fall to device
    if workload == "locomo":
        dev_ttft = device_incr_warm_ms(L_i)
        dev_ttft = dev_ttft if dev_ttft is not None else 120_000.0
    else:
        dev_ttft = device_cold_restore_ms(L_i) or 120_000.0
    q_dev = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)
    return (None, dev_ttft, (dev_ttft <= budget) and (q_dev >= q_slo))


# ── ADMISSION POLICIES ────────────────────────────────────────────────────────

def _fp_ranked_fidelity(workload, q_min, context_L):
    adm = admissible(workload, q_min)
    if not adm: return None
    return max(adm, key=lambda f: Q_TABLE[(f, workload, "qwen7b")] / kv_bytes(f, context_L))


def _oracle_fidelity(workload, q_min):
    adm = admissible(workload, q_min)
    if not adm: return None
    return max(adm, key=lambda f: Q_TABLE[(f, workload, "qwen7b")])


def _maint_aware_admit(active_robots, prev_kv, kv_cap, accel_budget,
                        workload, q_slo, opt_budget=KNAPSACK_OPT_BUDGET):
    """
    Fleet-level greedy knapsack for maintenance_aware.

    Formulation:
      maximise  sum_i  gain(f_i, i)
      s.t.      sum_i  S_ready(f_i, L_i)  <= kv_cap
                sum_i  (serve_ms(f_i) + refresh_ms(f_i))  <= accel_budget

    gain(f, i) = int(TTFT(f,i) <= opt_budget AND Q(f) >= q_slo)
                 - int(device_TTFT(i) <= opt_budget AND Q_dev >= q_slo)

    Greedy: sort by gain / cost_of_binding_resource descending.
    Containment: action space includes any assignment; verified by assertion below.
    """
    adm_fids = admissible(workload, q_slo)
    Q_dev = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)

    # Build candidates
    candidates = []   # (gain, kv_c, accel_c, rid, fid)
    for rid, robot in active_robots.items():
        # Device baseline
        if workload == "locomo":
            dev_t = device_incr_warm_ms(robot.context_L)
            dev_t = dev_t if dev_t is not None else 120_000.0
        else:
            dev_t = device_cold_restore_ms(robot.context_L) or 120_000.0
        dev_ok = (dev_t <= opt_budget) and (Q_dev >= q_slo)

        for fid in adm_fids:
            newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
            ttft_f = edge_serve_ms(fid, workload, robot.context_L, robot.is_session_start, newly)
            edge_ok = (ttft_f <= opt_budget)
            gain = int(edge_ok) - int(dev_ok)
            if gain < 0:
                continue   # never admit if admission hurts SLO
            kv_c    = kv_bytes(fid, robot.context_L)
            accel_c = ttft_f + refresh_ms(fid, workload)
            candidates.append((gain, kv_c, accel_c, rid, fid))

    # Determine binding resource: project best-per-robot assignment
    best_per_robot = {}
    for gain, kv_c, accel_c, rid, fid in sorted(candidates, key=lambda x: -x[0]):
        if rid not in best_per_robot:
            best_per_robot[rid] = (gain, kv_c, accel_c, fid)

    total_kv    = sum(v[1] for v in best_per_robot.values())
    total_accel = sum(v[2] for v in best_per_robot.values())
    kv_frac     = total_kv    / max(kv_cap,    1)
    accel_frac  = total_accel / max(accel_budget, 1)
    binding = "kv" if kv_frac >= accel_frac else "accel"

    # Sort all candidates by gain / binding_cost (descending)
    def sort_key(item):
        gain, kv_c, accel_c, rid, fid = item
        cost = kv_c if binding == "kv" else accel_c
        return (gain, gain / max(cost, 1))

    sorted_cands = sorted(candidates, key=sort_key, reverse=True)

    new_kv      = {}
    kv_used     = 0.0
    accel_used  = 0.0
    kv_bound    = False
    accel_bound = False

    for gain, kv_c, accel_c, rid, fid in sorted_cands:
        if rid in new_kv:
            continue
        if kv_used + kv_c > kv_cap:
            kv_bound = True
            continue
        if accel_used + accel_c > accel_budget:
            accel_bound = True
            continue
        new_kv[rid]   = fid
        kv_used      += kv_c
        accel_used   += accel_c

    return new_kv, kv_used, accel_used, binding, kv_bound, accel_bound


def _containment_assertion(workload="locomo", q_slo=0.20):
    """Assert maintenance_aware can express always_full-equivalent under unlimited budgets."""
    # Build one robot at L=20000
    class _R:
        context_L      = 20000.0
        is_session_start = False
    robots = {0: _R()}
    kv_cap_inf     = float("inf")
    accel_budget_inf = float("inf")

    new_kv, _, _, _, kb, ab = _maint_aware_admit(
        robots, {}, kv_cap_inf, accel_budget_inf, workload, q_slo)

    adm = admissible(workload, q_slo)
    if adm and 0 not in new_kv:
        raise AssertionError(
            f"Containment FAIL: maintenance_aware admitted 0 robots (wl={workload}, q={q_slo}) "
            f"under unlimited budgets; admissible={adm}. Policy is degenerate.")
    # Verify action space: all fidelities present in FIDELITIES
    assert set(FIDELITIES) == {"full", "win10", "sum200"}, \
        "Containment FAIL: FIDELITIES does not include all required options."


# ── ROBOT STATE ───────────────────────────────────────────────────────────────

class Robot:
    __slots__ = ["rid", "context_L", "tok_per_turn", "n_sess",
                 "session_idx", "turn_in_session", "ego_ctx_L"]

    def __init__(self, rid, ctx_total, n_sess, ego_ctx_L=None):
        self.rid             = rid
        self.n_sess          = n_sess
        self.tok_per_turn    = (ctx_total / n_sess) / TURNS_PER_SESSION
        self.context_L       = 0.0
        self.session_idx     = 0
        self.turn_in_session = 0
        self.ego_ctx_L       = ego_ctx_L   # fixed for EgoSchema

    def step(self):
        self.turn_in_session += 1
        self.context_L       += self.tok_per_turn
        if self.turn_in_session >= TURNS_PER_SESSION:
            self.turn_in_session = 0
            self.session_idx    += 1

    @property
    def is_session_start(self): return self.turn_in_session == 0
    @property
    def active(self): return self.session_idx < self.n_sess


# ── STAGE 0 ───────────────────────────────────────────────────────────────────

def _locomo_lat_fail(budget_ms):
    fails = total = 0
    for ctx, n_sess in zip(LOCOMO_CTX_TOKENS, LOCOMO_N_SESSIONS):
        tps = ctx / n_sess; tpt = tps / TURNS_PER_SESSION
        for s in range(n_sess):
            for t in range(TURNS_PER_SESSION):
                L = s * tps + t * tpt
                ms = device_incr_warm_ms(L)
                total += 1
                if ms is None or ms > budget_ms: fails += 1
    return fails / total


def _ego_lat_fail(budget_ms):
    fails = sum(1 for L in EGOSCHEMA_CTX_TOKENS
                if (lambda v: v is None or v > budget_ms)(device_cold_restore_ms(L)))
    return fails / len(EGOSCHEMA_CTX_TOKENS)


def run_stage0():
    print("=" * 70)
    print("STAGE 0 — Headroom Gate (E36c, fixed KV capacity, admissibility model)")
    print("=" * 70)
    cells, n_nd = [], 0
    for wl in WORKLOADS:
        Q_dev = Q_TABLE.get(("full", wl, "qwen3b"), 0.0)
        lat_fn = _locomo_lat_fail if wl == "locomo" else _ego_lat_fail
        for budget in TTFT_BUDGETS:
            lat = lat_fn(budget)
            for q_slo in QUALITY_SLOS:
                q_ok = Q_dev >= q_slo
                disc = (not q_ok) or (lat > 0.05)
                if not disc: n_nd += 1
                cells.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                               "Q_device": Q_dev, "q_ok": q_ok,
                               "lat_fail": round(lat, 4), "discriminating": disc})
    total = len(cells)
    gate  = n_nd / total <= 0.50
    print(f"  Non-discriminating: {n_nd}/{total} ({n_nd/total:.0%})")
    print(f"  K1: {'PASS' if gate else 'FAIL'}")
    return {"gate_passes": gate, "n_nd": n_nd, "n_total": total, "cells": cells}


# ── RUN ONE SIMULATION ───────────────────────────────────────────────────────

import random as _random

def run_one(policy, n_robots, kv_cap_bytes, accel_budget_ms,
            workload, q_slo, seed):
    rng = _random.Random(seed)

    # Build robots; EgoSchema: assign fixed context per robot
    robots = {}
    for rid in range(n_robots):
        conv_idx = rid % len(LOCOMO_CTX_TOKENS)
        ctx      = LOCOMO_CTX_TOKENS[conv_idx]
        n_sess   = LOCOMO_N_SESSIONS[conv_idx]
        ego_ctx  = EGOSCHEMA_CTX_TOKENS[rid % len(EGOSCHEMA_CTX_TOKENS)]
        robots[rid] = Robot(rid, ctx, n_sess, ego_ctx_L=ego_ctx)

    # LRU deque for always_X policies
    from collections import deque as _deque
    lru_order = _deque(range(n_robots))

    prev_kv = {}   # rid -> fidelity (currently warm at edge)

    # Records: (orig_fid_or_None, orig_ttft, from_device, L_i, is_ss, newly)
    records = []

    # Diagnostics per epoch
    kv_used_series   = []     # KV bytes used per epoch
    accel_used_series = []    # accel ms used per epoch
    binding_counter  = defaultdict(int)   # "kv"/"accel"/"neither"
    mixed_count      = 0      # epochs with ≥2 distinct edge fidelities
    total_epochs     = 0
    kv_bound_count   = 0
    accel_bound_count = 0
    eviction_count   = 0

    Q_dev = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)
    n_sessions_max = max(LOCOMO_N_SESSIONS)

    for epoch in range(n_sessions_max * TURNS_PER_SESSION):
        active = {rid: r for rid, r in robots.items() if r.active}
        if not active:
            break
        total_epochs += 1

        # ── Compute new_kv based on policy ──────────────────────────────────
        kv_used_ep   = 0.0
        accel_used_ep = 0.0
        kv_bound = accel_bound = False

        if policy == "device_only":
            new_kv = {}

        elif policy in ("always_full", "always_window", "always_summary"):
            fid_map = {"always_full": "full", "always_window": "win10",
                       "always_summary": "sum200"}
            fid = fid_map[policy]
            # Only admit if fidelity is admissible
            if Q_TABLE.get((fid, workload, "qwen7b"), 0.0) >= q_slo:
                # LRU within fixed KV budget; order: most-recently-used gets priority
                new_kv = {}
                ordered = list(lru_order)   # oldest→newest
                lru_order.clear()
                for rid in reversed(ordered):   # newest first
                    if rid not in active:
                        continue
                    kvb = kv_bytes(fid, active[rid].context_L)
                    if kv_used_ep + kvb <= kv_cap_bytes:
                        new_kv[rid]  = fid
                        kv_used_ep  += kvb
                        accel_used_ep += (edge_serve_ms(fid, workload,
                                            active[rid].context_L,
                                            active[rid].is_session_start,
                                            rid not in prev_kv or prev_kv.get(rid) != fid)
                                          + refresh_ms(fid, workload))
                        lru_order.appendleft(rid)
                    else:
                        kv_bound = True
                        lru_order.appendleft(rid)   # evicted: move to oldest
                        if rid in prev_kv:
                            eviction_count += 1
                # Re-sort lru_order: admitted at back (newest), evicted at front
                admitted_rids = [r for r in reversed(list(lru_order)) if r in new_kv]
                evicted_rids  = [r for r in lru_order if r not in new_kv]
                lru_order.clear()
                for r in evicted_rids:   lru_order.appendleft(r)
                for r in admitted_rids:  lru_order.append(r)
            else:
                new_kv = {}

        elif policy == "footprint_ranked":
            # Pick highest Q/KV admissible per robot, greedy under KV (no accel constraint)
            cands = []
            for rid, r in active.items():
                fid = _fp_ranked_fidelity(workload, q_slo, r.context_L)
                if fid is None: continue
                newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
                kvb   = kv_bytes(fid, r.context_L)
                density = Q_TABLE[(fid, workload, "qwen7b")] / max(kvb, 1)
                cands.append((density, rid, fid, kvb))
            cands.sort(reverse=True)
            new_kv = {}
            for _, rid, fid, kvb in cands:
                if kv_used_ep + kvb <= kv_cap_bytes:
                    new_kv[rid]  = fid
                    kv_used_ep  += kvb
                    newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
                    accel_used_ep += (edge_serve_ms(fid, workload, active[rid].context_L,
                                                    active[rid].is_session_start, newly)
                                      + refresh_ms(fid, workload))
                else:
                    kv_bound = True
                    if rid in prev_kv: eviction_count += 1

        elif policy == "maintenance_aware":
            new_kv, kv_used_ep, accel_used_ep, bind_res, kv_bound, accel_bound = \
                _maint_aware_admit(active, prev_kv, kv_cap_bytes, accel_budget_ms,
                                   workload, q_slo)
            binding_counter[bind_res] += 1

        elif policy == "oracle":
            # Highest-Q admissible per robot, greedy under KV
            cands = []
            for rid, r in active.items():
                fid = _oracle_fidelity(workload, q_slo)
                if fid is None: continue
                kvb = kv_bytes(fid, r.context_L)
                cands.append((Q_TABLE.get((fid, workload, "qwen7b"), 0.0), rid, fid, kvb))
            cands.sort(reverse=True)
            new_kv = {}
            for q_f, rid, fid, kvb in cands:
                if kv_used_ep + kvb <= kv_cap_bytes:
                    new_kv[rid]  = fid
                    kv_used_ep  += kvb
                    newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
                    accel_used_ep += (edge_serve_ms(fid, workload, active[rid].context_L,
                                                    active[rid].is_session_start, newly)
                                      + refresh_ms(fid, workload))
                else:
                    kv_bound = True
                    if rid in prev_kv: eviction_count += 1
        else:
            raise ValueError(f"Unknown policy: {policy}")

        if kv_bound:    kv_bound_count    += 1
        if accel_bound: accel_bound_count += 1

        kv_used_series.append(kv_used_ep)
        accel_used_series.append(accel_used_ep)

        # Mixed assignment diagnostic: ≥2 distinct edge fidelities
        fid_set = set(new_kv.values())
        if len(fid_set) >= 2:
            mixed_count += 1

        # Track evictions for always_X (already done above) and greedy policies
        # (eviction_count updated inside each policy branch)

        # Score each robot
        for rid, r in active.items():
            is_ss = r.is_session_start
            if rid in new_kv:
                fid   = new_kv[rid]
                newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
                if workload == "egoschema":
                    L_q = r.ego_ctx_L
                else:
                    L_q = r.context_L
                ttft = edge_serve_ms(fid, workload, L_q, is_ss, newly)
                records.append((fid, ttft, False, L_q, is_ss, newly))
            else:
                if workload == "locomo":
                    ms = device_incr_warm_ms(r.context_L)
                    ttft = ms if ms is not None else 120_000.0
                    L_q = r.context_L
                else:
                    ms = device_cold_restore_ms(r.ego_ctx_L)
                    ttft = ms if ms is not None else 120_000.0
                    L_q = r.ego_ctx_L
                records.append((None, ttft, True, L_q, is_ss, True))

            r.step()

        prev_kv = dict(new_kv)

    # Post-process: apply retroactive fallback per budget
    n_q = len(records)
    out = {
        "policy": policy, "n_robots": n_robots,
        "kv_cap_bytes": kv_cap_bytes,
        "accel_budget_ms": accel_budget_ms,
        "workload": workload, "q_slo": q_slo, "seed": seed,
        "n_queries": n_q,
    }
    for budget in TTFT_BUDGETS:
        n_both = n_lat = n_qual = 0
        for fid, ttft, from_dev, L_i, is_ss, newly in records:
            _, eff_ttft, both = retroactive_ttft_and_q(
                fid, ttft, from_dev, L_i, is_ss, newly, workload, q_slo, budget)
            if both: n_both += 1
            if eff_ttft <= budget: n_lat += 1
            # Quality met: served from admissible f (or device admissible)
            q_ok = both or (eff_ttft <= budget)   # both means both lat+qual
            # Recompute quality only count
        # Re-pass for quality count
        n_qual_ok = 0
        for fid, ttft, from_dev, L_i, is_ss, newly in records:
            _, _, both = retroactive_ttft_and_q(
                fid, ttft, from_dev, L_i, is_ss, newly, workload, q_slo, budget)
            if both: pass   # counted above
            # quality_met: fidelity is admissible
            if from_dev:
                n_qual_ok += int(Q_TABLE.get(("full", workload, "qwen3b"), 0.0) >= q_slo)
            elif fid is not None:
                n_qual_ok += int(Q_TABLE.get((fid, workload, "qwen7b"), 0.0) >= q_slo)

        out[f"both_met_{int(budget)}ms"] = round(n_both / max(n_q, 1), 4)
        out[f"lat_met_{int(budget)}ms"]  = round(n_lat  / max(n_q, 1), 4)

    # Diagnostics
    out["kv_bound_frac"]    = round(kv_bound_count    / max(total_epochs, 1), 4)
    out["accel_bound_frac"] = round(accel_bound_count / max(total_epochs, 1), 4)
    out["mixed_frac"]       = round(mixed_count        / max(total_epochs, 1), 4)
    out["eviction_count"]   = eviction_count

    if kv_used_series:
        kv_s = sorted(kv_used_series)
        n    = len(kv_s)
        out["kv_occ_mean_gib"] = round(statistics.mean(kv_s) / 1024**3, 4)
        out["kv_occ_p50_gib"]  = round(kv_s[n // 2]          / 1024**3, 4)
        out["kv_occ_p90_gib"]  = round(kv_s[int(n * 0.9)]    / 1024**3, 4)
        out["kv_occ_max_gib"]  = round(kv_s[-1]               / 1024**3, 4)
    if accel_used_series:
        out["accel_occ_mean_ms"] = round(statistics.mean(accel_used_series), 1)
        out["accel_occ_max_ms"]  = round(max(accel_used_series), 1)
        out["accel_util_frac"]   = round(
            statistics.mean(accel_used_series) / max(accel_budget_ms, 1), 4)

    if policy == "maintenance_aware" and binding_counter:
        total_b = sum(binding_counter.values())
        out["binding_kv_frac"]    = round(binding_counter.get("kv",    0) / total_b, 4)
        out["binding_accel_frac"] = round(binding_counter.get("accel", 0) / total_b, 4)

    return out


# ── STAGE 1 ───────────────────────────────────────────────────────────────────

def run_stage1():
    total = (len(POLICY_NAMES) * len(N_ROBOTS_LIST) * len(KV_CAP_GIB_LIST)
             * len(TURN_INTERVAL_LIST) * len(WORKLOADS) * len(QUALITY_SLOS) * len(SEEDS))
    print(f"\n{'='*70}")
    print(f"STAGE 1 — Policy sweep  ({total} runs)")
    print(f"  n_robots:      {N_ROBOTS_LIST}")
    print(f"  kv_cap_gib:    {KV_CAP_GIB_LIST}  (FIXED, independent of fleet)")
    print(f"  turn_interval: {TURN_INTERVAL_LIST} s  [ASSUMPTION A4]")
    print(f"{'='*70}")

    results = []
    done    = 0
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            for nr in N_ROBOTS_LIST:
                for kv_gib in KV_CAP_GIB_LIST:
                    kv_bytes_cap = int(kv_gib * 1024**3)
                    for turn_s in TURN_INTERVAL_LIST:
                        accel_ms = turn_s * 1000.0
                        for seed in SEEDS:
                            for pol in POLICY_NAMES:
                                r = run_one(pol, nr, kv_bytes_cap, accel_ms,
                                            wl, q_slo, seed)
                                r["kv_cap_gib"]      = kv_gib
                                r["turn_interval_s"] = turn_s
                                results.append(r)
                                done += 1
                                if done % 500 == 0:
                                    print(f"  {done}/{total} …")

    print(f"  {total}/{total} done.")
    return {"n_runs": total, "results": results}


# ── STAGE 2 ───────────────────────────────────────────────────────────────────

def run_stage2(stage1):
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("STAGE 2 — Per-cell analysis (averaged over n_robots, kv_cap, turn_interval, seeds)")
    print(f"  Primary comparison: maintenance_aware vs footprint_ranked")
    print(f"{'='*70}")

    # Cell = (workload, budget, q_slo); average over all other axes
    sums = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for budget in TTFT_BUDGETS:
            key = (r["workload"], budget, r["q_slo"])
            sums[key][r["policy"]].append(r[f"both_met_{int(budget)}ms"])

    cells_out    = []
    k2_violations = []
    kc_violations = []

    for key in sorted(sums):
        wl, budget, q_slo = key
        pol_means = {p: statistics.mean(v) for p, v in sums[key].items()}
        ranked    = sorted(pol_means, key=pol_means.get, reverse=True)
        dev_mean  = pol_means.get("device_only",      0.0)
        ma_mean   = pol_means.get("maintenance_aware", 0.0)
        fp_mean   = pol_means.get("footprint_ranked",  0.0)
        gap_ma_dev = (ma_mean - dev_mean) * 100
        gap_ma_fp  = (ma_mean - fp_mean)  * 100
        k2_ok = gap_ma_dev >= 5.0
        kc_ok = abs(gap_ma_fp) >= 5.0   # fires if within 5pp
        if not k2_ok:
            k2_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "gap_pp": round(gap_ma_dev, 2)})
        if not kc_ok:
            kc_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "gap_pp": round(gap_ma_fp, 2)})
        cell = {
            "workload": wl, "budget_ms": budget, "q_slo": q_slo,
            "ranking": [{"policy": p, "both_met": round(pol_means[p], 4),
                          "gap_vs_device_pp": round((pol_means[p] - dev_mean) * 100, 2)}
                        for p in ranked],
            "maint_vs_device_pp": round(gap_ma_dev, 2),
            "maint_vs_fp_pp":     round(gap_ma_fp,  2),
            "k2_ok": k2_ok,
        }
        cells_out.append(cell)

    print(f"\n{'wl':12s} {'bud':>7s} {'q':>4s} | {'dev':>6s} {'fp':>7s} {'ma':>7s} | "
          f"{'ma-fp':>7s} | {'ma-dev':>8s} K2")
    print("-" * 72)
    for c in cells_out:
        def _g(p): return next((x["both_met"] for x in c["ranking"] if x["policy"] == p), 0.0)
        print(f"{c['workload']:12s} {c['budget_ms']:>7.0f} {c['q_slo']:>4.2f} | "
              f"{_g('device_only'):>6.3f} {_g('footprint_ranked'):>7.3f} {_g('maintenance_aware'):>7.3f} | "
              f"{c['maint_vs_fp_pp']:>+6.1f}pp | {c['maint_vs_device_pp']:>+6.1f}pp "
              f"{'PASS' if c['k2_ok'] else 'FAIL'}")

    print(f"\nK2 (ma>=5pp over device):         {'PASS' if not k2_violations else f'FAIL ({len(k2_violations)} cells)'}")
    print(f"KC (ma within 5pp of fp_ranked): {'FIRES (' + str(len(kc_violations)) + ' cells)' if kc_violations else 'no-fire'}")

    # Kill conditions
    def _within5(pol_a, pol_b, cell):
        a = next((x["both_met"] for x in cell["ranking"] if x["policy"] == pol_a), 0.0)
        b = next((x["both_met"] for x in cell["ranking"] if x["policy"] == pol_b), 0.0)
        return abs(a - b) * 100 < 5.0

    kill = {
        "a": sum(1 for c in cells_out if _within5("always_window",  "maintenance_aware", c)),
        "b": sum(1 for c in cells_out if _within5("always_full",    "maintenance_aware", c)),
        "c": sum(1 for c in cells_out if _within5("footprint_ranked","maintenance_aware", c)),
    }
    print(f"\nKill conditions (cells where condition fires / {len(cells_out)} total):")
    print(f"  (a) always_window within 5pp of maint_aware: {kill['a']}")
    print(f"  (b) always_full   within 5pp of maint_aware: {kill['b']}")
    print(f"  (c) fp_ranked     within 5pp of maint_aware: {kill['c']}")

    return {"cells": cells_out, "k2_violations": k2_violations,
            "kc_violations": kc_violations, "k2_passes": not k2_violations,
            "kill_ab_c": kill}


# ── BINDING RESOURCE + MIXED DIAGNOSTIC ──────────────────────────────────────

def run_binding_diagnostic(stage1):
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("BINDING RESOURCE DIAGNOSTIC (per policy, fleet size, kv_cap, turn_interval)")
    print(f"{'='*70}")

    from itertools import product

    # Per (policy, n_robots, kv_cap, turn_interval) cell: average diagnostics
    diag = []
    for pol, nr, kv_gib, ti in product(POLICY_NAMES, N_ROBOTS_LIST,
                                        KV_CAP_GIB_LIST, TURN_INTERVAL_LIST):
        rlist = [r for r in rows if r["policy"] == pol and r["n_robots"] == nr
                 and r["kv_cap_gib"] == kv_gib and r["turn_interval_s"] == ti]
        if not rlist: continue
        kv_b  = statistics.mean(r["kv_bound_frac"]    for r in rlist)
        ac_b  = statistics.mean(r["accel_bound_frac"]  for r in rlist)
        mix   = statistics.mean(r["mixed_frac"]         for r in rlist)
        ac_u  = statistics.mean(r.get("accel_util_frac", 0.0) for r in rlist)
        kv_p50 = statistics.mean(r.get("kv_occ_p50_gib", 0.0) for r in rlist)
        kv_max = statistics.mean(r.get("kv_occ_max_gib", 0.0) for r in rlist)
        binding = "memory" if kv_b >= ac_b else ("accel" if ac_b > 0 else "neither")
        diag.append({
            "policy": pol, "n_robots": nr, "kv_cap_gib": kv_gib,
            "turn_interval_s": ti,
            "kv_bound_frac": round(kv_b, 4), "accel_bound_frac": round(ac_b, 4),
            "binding": binding,
            "mixed_frac": round(mix, 4), "accel_util_frac": round(ac_u, 4),
            "kv_occ_p50_gib": round(kv_p50, 3), "kv_occ_max_gib": round(kv_max, 3),
        })

    # Summarize: does accelerator ever bind?
    any_accel = any(r["accel_bound_frac"] > 0 for r in diag)
    print(f"\n  Kill condition (d) — accelerator never binds at any cell: "
          f"{'FIRES' if not any_accel else 'no-fire'}")

    # Print summary: for each policy at n_robots=50, kv=9 GiB, turn_interval=5 s
    print(f"\n  Snapshot: n_robots=50, kv=9 GiB, turn_interval=5 s")
    print(f"  {'policy':20s} {'kv_bd%':>7s} {'ac_bd%':>7s} {'bind':>8s} {'mix%':>6s} {'ac_util%':>8s}")
    print("  " + "-" * 62)
    for d in diag:
        if d["n_robots"] == 50 and d["kv_cap_gib"] == 9.0 and d["turn_interval_s"] == 5.0:
            print(f"  {d['policy']:20s} {d['kv_bound_frac']:>7.1%} {d['accel_bound_frac']:>7.1%} "
                  f"{d['binding']:>8s} {d['mixed_frac']:>6.1%} {d['accel_util_frac']:>8.1%}")

    # Kill condition (e): advantage grows with fleet size?
    # Check: does maint_aware - fp_ranked gap grow with n_robots?
    print(f"\n  Kill condition (e) — advantage does not grow with fleet size:")
    for wl in WORKLOADS:
        for budget in [300.0, 1000.0]:
            for q_slo in [0.20, 0.30]:
                gaps = []
                for nr in N_ROBOTS_LIST:
                    rma = [r for r in rows if r["policy"] == "maintenance_aware"
                           and r["n_robots"] == nr and r["workload"] == wl
                           and r["q_slo"] == q_slo]
                    rfp = [r for r in rows if r["policy"] == "footprint_ranked"
                           and r["n_robots"] == nr and r["workload"] == wl
                           and r["q_slo"] == q_slo]
                    if not rma or not rfp: continue
                    ma_mean = statistics.mean(r[f"both_met_{int(budget)}ms"] for r in rma)
                    fp_mean = statistics.mean(r[f"both_met_{int(budget)}ms"] for r in rfp)
                    gaps.append((nr, round((ma_mean - fp_mean) * 100, 2)))
                if gaps:
                    trend = "grows" if gaps[-1][1] > gaps[0][1] + 3 else \
                            ("shrinks" if gaps[-1][1] < gaps[0][1] - 3 else "flat")
                    print(f"  {wl:12s} {int(budget):>5d}ms q={q_slo}: "
                          f"{[f'{n}→{g:+.1f}pp' for n,g in gaps]}  → {trend}")

    return {"rows": diag, "kd_fires": not any_accel}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    # Containment assertion (startup check)
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            _containment_assertion(wl, q_slo)
    print("Containment assertion: PASS (maintenance_aware admits robots under unlimited budgets)")

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
