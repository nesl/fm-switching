"""
E36d — Fleet policy experiment with maintenance charged to accelerator.

Root cause of E36c null (two defects corrected here):
  (a) refresh_ms returned 0 for full and win10 — maintenance never charged.
  (b) Accel budget not enforced for always_X / footprint_ranked — only
      maintenance_aware saw it via the knapsack, but even that saw 0 refresh.

Fixes:
  1. Maintenance charged per turn for every representation:
       full   : 66 ms/turn  (warm append, E26/E34)
       win10  : 36 ms/turn (growth) or 1031 ms/turn (slide, session_idx >= 10)
       sum200 : 5822 ms/turn (regen, E35)
  2. serve_ms = warm-decode cost only (no double-count):
       full   : 59 ms  (proxy: win10 intra-session serve, E35) [ASSUMPTION B1]
       win10  : 59 ms  (E35 intra-session)
       sum200 : 32 ms  (E35 restore)
  3. Queue model: FIFO, TTFT_i = cumsum(maint_j + serve_j, j<=i).
     Robots whose TTFT > accel_budget fall to device for that epoch.
  4. Accel budget enforced for ALL policies, not just maintenance_aware.
  5. Phase-randomized robot initialization: each robot assigned a random
     (session_idx, turn_in_session) offset so slides are desynchronized.

Unchanged from E36c:
  - Sweep axes: n_robots, kv_cap_gib, turn_interval_s, workload, q_slo, seed.
  - Admissibility model: Q(f, qwen7b, wl) >= q_min.
  - Policy set (7 policies). EgoSchema no per-session refresh (A6).
  - Containment assertion on maintenance_aware.
  - Six-check consistency protocol run before conclusions.

Assumptions:
  A1: Device TTFT = measured 3B/7B ratio (E37, L-dep, clamped at 16384).
  A2: EgoSchema context in [1500, 2500] tokens (range).
  A3: Edge KV = kv_cap_gib (fixed sweep axis).
  A4: Turn interval = sweep axis {5, 15, 30, 60} s. [ASSUMPTION]
  A5: win10 slide fraction 65.7% (E34/E35); realized per session structure.
  A6: EgoSchema: independent cold queries, no per-session refresh.
  B1: full serve cost = 59 ms (win10 intra-session proxy; E26 warm-append
      may bundle decode — conservative estimate). [ASSUMPTION]
"""

import json
import random as _random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36d_fleet"

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

# Maintenance costs: making the object current [E26/E34/E35]
MAINT_FULL_MS        = 66.0     # warm append
MAINT_WIN10_GROW_MS  = 36.0     # growth (prefix preserved)
MAINT_WIN10_SLIDE_MS = 1031.0   # slide (head eviction + window re-prefill)
MAINT_SUM200_MS      = 5822.0   # background regen

WINDOW_SIZE_SESS = 10           # win10 = last 10 sessions

# Serve costs: warm decode from already-current object [E35; see B1 for full]
SERVE_FULL_MS    = 59.0         # [ASSUMPTION B1]
SERVE_WIN10_MS   = 59.0         # E35 intra-session
SERVE_SUM200_MS  = 32.0         # E35 restore

EDGE_COLD_PREFILL_RATE = 5984.0  # tok/s [E21/E26]
WIN10_TOKENS   = 7_275           # E33a
SUM200_TOKENS  = 160             # E35

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
FIDELITIES = ["full", "win10", "sum200"]

N_ROBOTS_LIST      = [5, 10, 20, 50]
KV_CAP_GIB_LIST    = [4.5, 9.0, 18.0, 36.0]
TURN_INTERVAL_LIST = [5.0, 15.0, 30.0, 60.0]
SEEDS              = (42, 99, 137)

KNAPSACK_OPT_BUDGET = 1000.0   # [ASSUMPTION A7]


# ── LATENCY / COST HELPERS ────────────────────────────────────────────────────

def _interp(table, L):
    keys = sorted(table)
    if L <= keys[0]:  return table[keys[0]] * L / keys[0]
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


def kv_bytes(fidelity, context_L):
    if fidelity == "full":   return int(max(context_L, 1) * KV_BYTES_PER_TOK_7B)
    if fidelity == "win10":  return WIN10_TOKENS * KV_BYTES_PER_TOK_7B
    return SUM200_TOKENS * KV_BYTES_PER_TOK_7B


def maint_ms(fidelity, session_idx, workload):
    """Cost to make the object current. Charged for every admitted robot."""
    if workload == "egoschema": return 0.0  # A6: no per-session refresh
    if fidelity == "full":   return MAINT_FULL_MS
    if fidelity == "win10":
        return MAINT_WIN10_SLIDE_MS if session_idx >= WINDOW_SIZE_SESS \
               else MAINT_WIN10_GROW_MS
    return MAINT_SUM200_MS


def serve_ms_warm(fidelity):
    """Warm-decode cost from an already-current object."""
    if fidelity == "full":   return SERVE_FULL_MS
    if fidelity == "win10":  return SERVE_WIN10_MS
    return SERVE_SUM200_MS


def edge_cold_serve_ms(fidelity, workload, context_L):
    """Cold-start serve cost (first admission or newly allocated)."""
    if workload == "egoschema":
        if fidelity == "sum200": return SERVE_SUM200_MS
        if fidelity == "win10":  return SERVE_WIN10_MS
        return edge_cold_restore_ms(context_L)
    if fidelity == "full":   return edge_cold_restore_ms(context_L)
    if fidelity == "win10":  return edge_cold_restore_ms(WIN10_TOKENS)
    return SERVE_SUM200_MS


def admissible(workload, q_min):
    return [f for f in FIDELITIES
            if Q_TABLE.get((f, workload, "qwen7b"), 0.0) >= q_min]


# ── ROBOT STATE ───────────────────────────────────────────────────────────────

class Robot:
    __slots__ = ["rid", "context_L", "tok_per_turn", "n_sess",
                 "session_idx", "turn_in_session", "ego_ctx_L"]

    def __init__(self, rid, ctx_total, n_sess, ego_ctx_L=None,
                 phase_session=0, phase_turn=0):
        self.rid             = rid
        self.n_sess          = n_sess
        self.tok_per_turn    = (ctx_total / n_sess) / TURNS_PER_SESSION
        self.session_idx     = phase_session
        self.turn_in_session = phase_turn
        self.context_L       = (phase_session * (ctx_total / n_sess)
                                + phase_turn * self.tok_per_turn)
        self.ego_ctx_L       = ego_ctx_L

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
    Cost metric now includes actual maintenance (not zero).
    """
    adm_fids = admissible(workload, q_slo)
    Q_dev = Q_TABLE.get(("full", workload, "qwen3b"), 0.0)

    candidates = []
    for rid, robot in active_robots.items():
        if workload == "locomo":
            dev_t = device_incr_warm_ms(robot.context_L)
            dev_t = dev_t if dev_t is not None else 120_000.0
        else:
            dev_t = device_cold_restore_ms(robot.ego_ctx_L) or 120_000.0
        dev_ok = (dev_t <= opt_budget) and (Q_dev >= q_slo)

        for fid in adm_fids:
            newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
            if newly:
                s_ms = edge_cold_serve_ms(fid, workload, robot.context_L)
            else:
                s_ms = serve_ms_warm(fid)
            m_ms = maint_ms(fid, robot.session_idx, workload)
            edge_ok = (s_ms <= opt_budget)  # first-robot position estimate
            gain = int(edge_ok) - int(dev_ok)
            if gain < 0: continue
            kv_c    = kv_bytes(fid, robot.context_L)
            accel_c = m_ms + s_ms
            candidates.append((gain, kv_c, accel_c, rid, fid))

    best_per_robot = {}
    for gain, kv_c, accel_c, rid, fid in sorted(candidates, key=lambda x: -x[0]):
        if rid not in best_per_robot:
            best_per_robot[rid] = (gain, kv_c, accel_c, fid)

    total_kv    = sum(v[1] for v in best_per_robot.values())
    total_accel = sum(v[2] for v in best_per_robot.values())
    kv_frac     = total_kv    / max(kv_cap,      1)
    accel_frac  = total_accel / max(accel_budget, 1)
    binding = "kv" if kv_frac >= accel_frac else "accel"

    def sort_key(item):
        gain, kv_c, accel_c, rid, fid = item
        cost = kv_c if binding == "kv" else accel_c
        return (gain, gain / max(cost, 1))

    sorted_cands = sorted(candidates, key=sort_key, reverse=True)

    new_kv     = {}
    kv_used    = 0.0
    accel_used = 0.0
    kv_bound   = False
    accel_bound= False

    for gain, kv_c, accel_c, rid, fid in sorted_cands:
        if rid in new_kv: continue
        if kv_used + kv_c > kv_cap:
            kv_bound = True; continue
        if accel_used + accel_c > accel_budget:
            accel_bound = True; continue
        new_kv[rid] = fid
        kv_used    += kv_c
        accel_used += accel_c

    return new_kv, kv_used, accel_used, binding, kv_bound, accel_bound


def _containment_assertion(workload="locomo", q_slo=0.20):
    class _R:
        context_L = 20000.0; session_idx = 0; ego_ctx_L = 2000.0
        is_session_start = False
    robots = {0: _R()}
    new_kv, _, _, _, _, _ = _maint_aware_admit(
        robots, {}, float("inf"), float("inf"), workload, q_slo)
    adm = admissible(workload, q_slo)
    if adm and 0 not in new_kv:
        raise AssertionError(
            f"Containment FAIL: maintenance_aware admitted 0 robots "
            f"(wl={workload}, q={q_slo}) under unlimited budgets; admissible={adm}.")


# ── QUEUE MODEL ───────────────────────────────────────────────────────────────

def queue_ttfts(admitted_order, active, prev_kv, workload, accel_budget_ms):
    """
    FIFO queue: compute per-robot TTFT and whether it falls within accel_budget.
    Returns dict rid -> (ttft_ms, served_at_edge, fid_or_None).
    """
    cumul_ms = 0.0
    result   = {}
    for rid, fid in admitted_order:
        r    = active[rid]
        newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
        m_ms = maint_ms(fid, r.session_idx, workload)
        if newly:
            s_ms = edge_cold_serve_ms(fid, workload, r.context_L)
        else:
            s_ms = serve_ms_warm(fid)
        cumul_ms += m_ms + s_ms
        within = cumul_ms <= accel_budget_ms
        result[rid] = (cumul_ms, within, fid)
    return result


def device_ttft(r, workload):
    if workload == "locomo":
        ms = device_incr_warm_ms(r.context_L)
        return ms if ms is not None else 120_000.0
    else:
        ms = device_cold_restore_ms(r.ego_ctx_L)
        return ms if ms is not None else 120_000.0


# ── STAGE 0 ───────────────────────────────────────────────────────────────────

def _locomo_lat_fail(budget_ms):
    fails = total = 0
    for ctx, n_sess in zip(LOCOMO_CTX_TOKENS, LOCOMO_N_SESSIONS):
        tps = ctx / n_sess; tpt = tps / TURNS_PER_SESSION
        for s in range(n_sess):
            for t in range(TURNS_PER_SESSION):
                L  = s * tps + t * tpt
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
    print("STAGE 0 — Headroom Gate")
    print("=" * 70)
    cells, n_nd = [], 0
    for wl in WORKLOADS:
        Q_dev  = Q_TABLE.get(("full", wl, "qwen3b"), 0.0)
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


# ── RUN ONE SIMULATION ────────────────────────────────────────────────────────

def run_one(policy, n_robots, kv_cap_bytes, accel_budget_ms,
            workload, q_slo, seed):
    rng = _random.Random(seed)

    # Build robots with randomized phase offsets
    robots = {}
    for rid in range(n_robots):
        conv_idx = rid % len(LOCOMO_CTX_TOKENS)
        ctx      = LOCOMO_CTX_TOKENS[conv_idx]
        n_sess   = LOCOMO_N_SESSIONS[conv_idx]
        ego_ctx  = EGOSCHEMA_CTX_TOKENS[rid % len(EGOSCHEMA_CTX_TOKENS)]
        # Desynchronize within-session only: all robots start at session 0 but
        # at a random turn offset (0..TURNS_PER_SESSION-1). This preserves the
        # correct fleet-level slide fraction (~65.7% committed) while preventing
        # synchronized slide bursts at epoch boundaries.
        ph_turn  = rng.randint(0, TURNS_PER_SESSION - 1)
        robots[rid] = Robot(rid, ctx, n_sess, ego_ctx_L=ego_ctx,
                            phase_session=0, phase_turn=ph_turn)

    from collections import deque as _deque
    lru_order = _deque(range(n_robots))

    prev_kv = {}   # rid -> fid (warm at edge)

    records          = []   # (fid_or_None, ttft_ms, from_device, L_i, is_ss, newly)
    kv_used_series   = []
    accel_used_series= []
    binding_counter  = defaultdict(int)
    mixed_count      = 0
    total_epochs     = 0
    kv_bound_count   = 0
    accel_bound_count= 0
    eviction_count   = 0
    n_slides_obs     = 0
    n_slide_total    = 0

    n_sessions_max = max(LOCOMO_N_SESSIONS)

    for epoch in range(n_sessions_max * TURNS_PER_SESSION):
        active = {rid: r for rid, r in robots.items() if r.active}
        if not active:
            break
        total_epochs += 1

        # Track realized slide fraction
        for r in active.values():
            n_slide_total += 1
            if r.session_idx >= WINDOW_SIZE_SESS:
                n_slides_obs += 1

        kv_used_ep    = 0.0
        accel_used_ep = 0.0
        kv_bound = accel_bound = False

        # ── Determine KV admission (identical to E36c except accel budget now real) ──
        if policy == "device_only":
            new_kv = {}

        elif policy in ("always_full", "always_window", "always_summary"):
            fid_map = {"always_full": "full", "always_window": "win10",
                       "always_summary": "sum200"}
            fid = fid_map[policy]
            if Q_TABLE.get((fid, workload, "qwen7b"), 0.0) >= q_slo:
                new_kv  = {}
                ordered = list(lru_order)
                lru_order.clear()
                for rid in reversed(ordered):
                    if rid not in active: continue
                    kvb = kv_bytes(fid, active[rid].context_L)
                    if kv_used_ep + kvb <= kv_cap_bytes:
                        new_kv[rid]   = fid
                        kv_used_ep   += kvb
                        lru_order.appendleft(rid)
                    else:
                        kv_bound = True
                        lru_order.appendleft(rid)
                        if rid in prev_kv: eviction_count += 1
                admitted_rids = [r for r in reversed(list(lru_order)) if r in new_kv]
                evicted_rids  = [r for r in lru_order if r not in new_kv]
                lru_order.clear()
                for r in evicted_rids:  lru_order.appendleft(r)
                for r in admitted_rids: lru_order.append(r)
            else:
                new_kv = {}

        elif policy == "footprint_ranked":
            cands = []
            for rid, r in active.items():
                fid = _fp_ranked_fidelity(workload, q_slo, r.context_L)
                if fid is None: continue
                kvb     = kv_bytes(fid, r.context_L)
                density = Q_TABLE[(fid, workload, "qwen7b")] / max(kvb, 1)
                cands.append((density, rid, fid, kvb))
            cands.sort(reverse=True)
            new_kv = {}
            for _, rid, fid, kvb in cands:
                if kv_used_ep + kvb <= kv_cap_bytes:
                    new_kv[rid]   = fid
                    kv_used_ep   += kvb
                else:
                    kv_bound = True
                    if rid in prev_kv: eviction_count += 1

        elif policy == "maintenance_aware":
            new_kv, kv_used_ep, accel_used_ep, bind_res, kv_bound, accel_bound = \
                _maint_aware_admit(active, prev_kv, kv_cap_bytes, accel_budget_ms,
                                   workload, q_slo)
            binding_counter[bind_res] += 1

        elif policy == "oracle":
            cands = []
            for rid, r in active.items():
                fid = _oracle_fidelity(workload, q_slo)
                if fid is None: continue
                kvb = kv_bytes(fid, r.context_L)
                cands.append((Q_TABLE.get((fid, workload, "qwen7b"), 0.0), rid, fid, kvb))
            cands.sort(reverse=True)
            new_kv = {}
            for _, rid, fid, kvb in cands:
                if kv_used_ep + kvb <= kv_cap_bytes:
                    new_kv[rid]   = fid
                    kv_used_ep   += kvb
                else:
                    kv_bound = True
                    if rid in prev_kv: eviction_count += 1
        else:
            raise ValueError(f"Unknown policy: {policy}")

        if kv_bound:    kv_bound_count    += 1

        # ── Queue model: compute TTFT for each admitted robot ────────────────
        admitted_order = [(rid, fid) for rid, fid in new_kv.items()]
        q_result = queue_ttfts(admitted_order, active, prev_kv, workload, accel_budget_ms)

        # accel accounting from queue
        if q_result:
            total_accel_used = max(v[0] for v in q_result.values())
            accel_used_ep    = total_accel_used
            if accel_used_ep > accel_budget_ms:
                accel_bound = True; accel_bound_count += 1
        kv_used_series.append(kv_used_ep)
        accel_used_series.append(accel_used_ep)
        if len(set(new_kv.values())) >= 2: mixed_count += 1

        # ── Score each robot ─────────────────────────────────────────────────
        for rid, r in active.items():
            if rid in q_result:
                ttft_ms, within_budget, fid = q_result[rid]
                if within_budget:
                    newly = (rid not in prev_kv) or (prev_kv.get(rid) != fid)
                    L_q = r.ego_ctx_L if workload == "egoschema" else r.context_L
                    records.append((fid, ttft_ms, False, L_q, r.is_session_start, newly))
                else:
                    # Queue overflow: falls to device
                    dev_t = device_ttft(r, workload)
                    L_q   = r.ego_ctx_L if workload == "egoschema" else r.context_L
                    records.append((None, dev_t, True, L_q, r.is_session_start, True))
            else:
                # Not KV-admitted: device
                dev_t = device_ttft(r, workload)
                L_q   = r.ego_ctx_L if workload == "egoschema" else r.context_L
                records.append((None, dev_t, True, L_q, r.is_session_start, True))

            r.step()

        prev_kv = dict(new_kv)

    # ── Post-process ─────────────────────────────────────────────────────────
    n_q = len(records)
    out = {
        "policy": policy, "n_robots": n_robots,
        "kv_cap_bytes": kv_cap_bytes,
        "accel_budget_ms": accel_budget_ms,
        "workload": workload, "q_slo": q_slo, "seed": seed,
        "n_queries": n_q,
        "realized_slide_frac": round(n_slides_obs / max(n_slide_total, 1), 4),
    }

    for budget in TTFT_BUDGETS:
        n_both = n_lat = 0
        for fid, ttft, from_dev, L_i, is_ss, newly in records:
            if from_dev:
                q_ok  = Q_TABLE.get(("full", workload, "qwen3b"), 0.0) >= q_slo
                lat_ok = ttft <= budget
            else:
                q_ok   = Q_TABLE.get((fid, workload, "qwen7b"), 0.0) >= q_slo
                lat_ok = ttft <= budget
            if lat_ok: n_lat  += 1
            if lat_ok and q_ok: n_both += 1
        out[f"both_met_{int(budget)}ms"] = round(n_both / max(n_q, 1), 4)
        out[f"lat_met_{int(budget)}ms"]  = round(n_lat  / max(n_q, 1), 4)

    out["kv_bound_frac"]    = round(kv_bound_count    / max(total_epochs, 1), 4)
    out["accel_bound_frac"] = round(accel_bound_count / max(total_epochs, 1), 4)
    out["mixed_frac"]       = round(mixed_count        / max(total_epochs, 1), 4)
    out["eviction_count"]   = eviction_count

    if kv_used_series:
        kv_s = sorted(kv_used_series); n = len(kv_s)
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
    print(f"  kv_cap_gib:    {KV_CAP_GIB_LIST}")
    print(f"  turn_interval: {TURN_INTERVAL_LIST} s")
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
    print("STAGE 2 — Per-cell analysis")
    print(f"  Primary comparison: maintenance_aware vs footprint_ranked, by turn_interval")
    print(f"{'='*70}")

    # For E36d, the key axis is turn_interval_s (the accel binding axis)
    # Cell = (workload, budget, q_slo, turn_interval_s)
    sums = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for budget in TTFT_BUDGETS:
            key = (r["workload"], budget, r["q_slo"], r["turn_interval_s"])
            sums[key][r["policy"]].append(r[f"both_met_{int(budget)}ms"])

    cells_out = []
    k2_violations = []
    kc_violations = []

    for key in sorted(sums):
        wl, budget, q_slo, ti = key
        pol_means = {p: statistics.mean(v) for p, v in sums[key].items()}
        ranked    = sorted(pol_means, key=pol_means.get, reverse=True)
        dev_mean  = pol_means.get("device_only",       0.0)
        ma_mean   = pol_means.get("maintenance_aware",  0.0)
        fp_mean   = pol_means.get("footprint_ranked",   0.0)
        gap_ma_dev = (ma_mean - dev_mean) * 100
        gap_ma_fp  = (ma_mean - fp_mean)  * 100
        k2_ok = gap_ma_dev >= 5.0
        kc_ok = abs(gap_ma_fp) >= 5.0
        if not k2_ok:
            k2_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "turn_interval_s": ti, "gap_pp": round(gap_ma_dev, 2)})
        if not kc_ok:
            kc_violations.append({"workload": wl, "budget_ms": budget, "q_slo": q_slo,
                                   "turn_interval_s": ti, "gap_pp": round(gap_ma_fp, 2)})
        cell = {
            "workload": wl, "budget_ms": budget, "q_slo": q_slo,
            "turn_interval_s": ti,
            "ranking": [{"policy": p, "both_met": round(pol_means[p], 4)}
                        for p in ranked],
            "maint_vs_device_pp": round(gap_ma_dev, 2),
            "maint_vs_fp_pp":     round(gap_ma_fp,  2),
            "k2_ok": k2_ok,
        }
        cells_out.append(cell)

    # Print table for key cells: n_queries-weighted view, ti=5 vs ti=60
    print(f"\n{'wl':12s} {'bud':>7s} {'q':>4s} {'ti':>4s} | {'dev':>6s} "
          f"{'fp':>7s} {'ma':>7s} | {'ma-fp':>7s}")
    print("-" * 72)
    for c in cells_out:
        if c["budget_ms"] != 1000.0: continue  # primary SLO
        def _g(p): return next((x["both_met"] for x in c["ranking"] if x["policy"] == p), 0.0)
        print(f"{c['workload']:12s} {c['budget_ms']:>7.0f} {c['q_slo']:>4.2f} "
              f"{c['turn_interval_s']:>4.0f} | "
              f"{_g('device_only'):>6.3f} {_g('footprint_ranked'):>7.3f} "
              f"{_g('maintenance_aware'):>7.3f} | "
              f"{c['maint_vs_fp_pp']:>+6.1f}pp")

    print(f"\nK2 (ma>=5pp over device):        "
          f"{'PASS' if not k2_violations else f'FAIL ({len(k2_violations)} cells)'}")
    print(f"KC (ma within 5pp of fp_ranked): "
          f"{'FIRES (' + str(len(kc_violations)) + ' cells)' if kc_violations else 'no-fire'}")

    def _within5(pol_a, pol_b, cell):
        a = next((x["both_met"] for x in cell["ranking"] if x["policy"] == pol_a), 0.0)
        b = next((x["both_met"] for x in cell["ranking"] if x["policy"] == pol_b), 0.0)
        return abs(a - b) * 100 < 5.0

    n_total = len(cells_out)
    kill = {
        "a": sum(1 for c in cells_out if _within5("always_window",   "maintenance_aware", c)),
        "b": sum(1 for c in cells_out if _within5("always_full",     "maintenance_aware", c)),
        "c": sum(1 for c in cells_out if _within5("footprint_ranked","maintenance_aware", c)),
        "d": sum(1 for c in cells_out if _within5("device_only",     "maintenance_aware", c)),
    }
    print(f"\nKill conditions ({n_total} cells):")
    print(f"  (a) always_window within 5pp of maint_aware:  {kill['a']}/{n_total}")
    print(f"  (b) always_full   within 5pp of maint_aware:  {kill['b']}/{n_total}")
    print(f"  (c) fp_ranked     within 5pp of maint_aware:  {kill['c']}/{n_total}")
    print(f"  (d) device_only   within 5pp of maint_aware:  {kill['d']}/{n_total}")

    return {"cells": cells_out, "k2_violations": k2_violations,
            "kc_violations": kc_violations, "k2_passes": not k2_violations,
            "kill_abcd": kill, "n_cells": n_total}


# ── BINDING RESOURCE DIAGNOSTIC ───────────────────────────────────────────────

def run_binding_diagnostic(stage1):
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("BINDING RESOURCE DIAGNOSTIC")
    print(f"{'='*70}")

    from itertools import product

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
        kv_p50= statistics.mean(r.get("kv_occ_p50_gib", 0.0)  for r in rlist)
        sl_fr = statistics.mean(r.get("realized_slide_frac", 0.0) for r in rlist)
        binding = "memory" if kv_b >= ac_b else ("accel" if ac_b > 0 else "neither")
        diag.append({
            "policy": pol, "n_robots": nr, "kv_cap_gib": kv_gib,
            "turn_interval_s": ti,
            "kv_bound_frac": round(kv_b, 4), "accel_bound_frac": round(ac_b, 4),
            "binding": binding,
            "mixed_frac": round(mix, 4), "accel_util_frac": round(ac_u, 4),
            "kv_occ_p50_gib": round(kv_p50, 3),
            "realized_slide_frac": round(sl_fr, 4),
        })

    any_accel = any(r["accel_bound_frac"] > 0 for r in diag)
    print(f"\n  Kill condition (d) — accelerator never binds: "
          f"{'FIRES' if not any_accel else 'no-fire'}")

    # Realized slide fraction sanity
    slide_fracs = [r["realized_slide_frac"] for r in diag if r["realized_slide_frac"] > 0]
    if slide_fracs:
        print(f"  Realized slide fraction: mean={statistics.mean(slide_fracs):.1%}  "
              f"(committed: 65.7%)")

    # Snapshot: per-policy at n=50, kv=9 GiB across turn intervals
    print(f"\n  Snapshot: n_robots=50, kv=9 GiB")
    print(f"  {'policy':20s} {'ti':>4s} {'kv_bd%':>7s} {'ac_bd%':>7s} "
          f"{'bind':>7s} {'ac_util%':>9s}")
    print("  " + "-" * 58)
    for d in sorted(diag, key=lambda x: (x["policy"], x["turn_interval_s"])):
        if d["n_robots"] == 50 and d["kv_cap_gib"] == 9.0:
            print(f"  {d['policy']:20s} {d['turn_interval_s']:>4.0f} "
                  f"{d['kv_bound_frac']:>7.1%} {d['accel_bound_frac']:>7.1%} "
                  f"{d['binding']:>7s} {d['accel_util_frac']:>9.1%}")

    return {"rows": diag, "kd_fires": not any_accel}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            _containment_assertion(wl, q_slo)
    print("Containment assertion: PASS")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    s0 = run_stage0()
    (OUT_DIR / "e36d_stage0_headroom.json").write_text(json.dumps(s0, indent=2))
    if not s0["gate_passes"]:
        print("Stopping: K1 FAIL.")
        return

    s1 = run_stage1()
    (OUT_DIR / "e36d_stage1_sweep.json").write_text(json.dumps(s1, indent=2))
    print(f"Stage 1 saved: {s1['n_runs']} runs.")

    s2 = run_stage2(s1)
    (OUT_DIR / "e36d_stage2_analysis.json").write_text(json.dumps(s2, indent=2))

    bd = run_binding_diagnostic(s1)
    (OUT_DIR / "e36d_binding_diagnostic.json").write_text(json.dumps(bd, indent=2))

    print(f"\nAll outputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
