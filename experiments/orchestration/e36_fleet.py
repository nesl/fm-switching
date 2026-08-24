"""
E36 — maintenance-aware admission and representation policy for a robot fleet.

Pure simulation, no GPU.  All cost/quality values trace to committed measurements.
[ASSUMPTION] tags mark values not directly measured.

STAGE 0  : headroom gate (corrected) — use this module's run_stage0().
STAGE 1  : policy sweep across fleet configurations.
STAGE 2  : per-cell policy ranking and kill-condition checks.

ASSUMPTIONS (all flagged inline):
  A1 : qwen3b Jetson time = s × qwen7b Jetson time.  s is a time ratio.
       Shown at s=0.43 (3B/7B param-count lower bound) and s=1.00 (no speedup
       upper bound).  Not directly measured — A1 will be replaced once the
       Jetson qwen3b run (results/cost/profiles/jetson_orin_qwen3b.json)
       is committed.
  A2 : EgoSchema full-context size ≈ 1500–2500 tokens.  Not committed.
  A4 : LoCoMo incr_warm for L in (16384, 24576): interpolated from the rate at
       the last measured point (L=16384).  Does not extrapolate past the
       infeasibility boundary (L=24576) where E23 recorded infeasible,
       not a slower rate.

PRE-REGISTERED KILL CONDITIONS:
  K1 : if >50% of Stage 0 cells non-discriminating, stop before Stage 1.
  K2 : if lifecycle_aware fails to beat device_only by >5pp in ANY cell
       (at either A1 bound), stop and report; do NOT tune the policy.

POLICIES (pre-registered, in order):
  1. device_only       — all queries to device tier (qwen3b)
  2. edge_full_lru     — edge + full, LRU admission/eviction
  3. edge_win10_lru    — edge + win10, LRU admission/eviction
  4. edge_sum200_lru   — edge + sum200, LRU admission/eviction
  5. reactive          — edge if free slot exists, else device; win10 default
  6. budget_aware      — edge + cheapest fidelity that meets TTFT budget
  7. lifecycle_aware   — edge + fidelity chosen by lifecycle cost vs quality SLO

EgoSchema note: modeled as short independent sessions (cold restore per query,
no accumulated context).  Discriminating cells for EgoSchema reflect per-query
materialization latency, not maintenance.  EgoSchema is the gist regime; it
is not described as a compressible long-lived session.
"""

import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36_fleet"

# ─────────────────────────────────────────────────────────────────────────────
# COMMITTED MEASUREMENTS
# ─────────────────────────────────────────────────────────────────────────────

# Jetson qwen7b (E23) — incr_warm and full_restore in ms
JETSON_7B_INCR_WARM    = {1024: 579.4, 2048: 666.8, 4096: 855.4,
                           8192: 1252.5, 16384: 2162.8}
JETSON_7B_FULL_RESTORE = {1024: 4052.5, 2048: 8009.5, 4096: 16310.6,
                           8192: 33790.3, 16384: 75053.7}
JETSON_7B_INFEASIBLE_L = 24576   # E23: both full_restore and incr_warm infeasible at L>=24576

# A6000 qwen7b — edge tier (E26, E35, cost_matrix.csv)
EDGE_FULL_WARM_APPEND_MS   = 66.0    # E26; E35 N=1 → 67ms (1.02×, agree)
EDGE_WIN10_INTRA_MS        = 59.0    # E35 median intra-session (41–77ms range)
EDGE_WIN10_INTER_MS        = 1031.0  # E35 inter-session (first query of new session)
EDGE_SUM200_RESTORE_MS     = 32.0    # E35 / cost_matrix.csv
EDGE_SUM200_UPDATE_MS      = 5822.0  # E35 recursive update
EDGE_COLD_PREFILL_RATE     = 5984.0  # tok/s — E26/E33a; A6000 qwen7b

WIN10_TOKENS_MEDIAN        = 7275    # E33a
SUM200_TOKENS              = 160     # E33a (~113 actual + headroom)

# Quality table (E29)
Q_TABLE = {
    # (fidelity, workload, model)
    ("full",   "locomo",    "qwen7b"): 0.400,
    ("win10",  "locomo",    "qwen7b"): 0.230,
    ("sum200", "locomo",    "qwen7b"): 0.120,
    ("blind",  "locomo",    "qwen7b"): 0.080,
    ("full",   "locomo",    "qwen3b"): 0.230,
    ("win10",  "locomo",    "qwen3b"): 0.180,
    ("sum200", "locomo",    "qwen3b"): 0.120,
    ("full",   "egoschema", "qwen7b"): 0.567,
    ("win10",  "egoschema", "qwen7b"): 0.500,
    ("sum200", "egoschema", "qwen7b"): 0.483,
    ("blind",  "egoschema", "qwen7b"): 0.200,
    ("full",   "egoschema", "qwen3b"): 0.450,
    ("win10",  "egoschema", "qwen3b"): 0.450,
    ("sum200", "egoschema", "qwen3b"): 0.433,
}

# LoCoMo: n=10 conversations (committed from data/locomo/locomo10.json)
LOCOMO_CTX_TOKENS   = [11386, 14665, 16212, 18894, 19325,
                        20860, 21125, 21592, 22266, 22778]
LOCOMO_N_SESSIONS   = [19, 19, 25, 28, 29, 29, 30, 30, 31, 32]
TURNS_PER_SESSION   = 22       # E33a §1.6

# EgoSchema: short independent queries [ASSUMPTION A2]
EGOSCHEMA_CTX_TOKENS = [1500, 1800, 2000, 2200, 2500]

A1_SCALES = [0.43, 1.00]       # [ASSUMPTION A1] sensitivity range

WORKLOADS    = ["locomo", "egoschema"]
TTFT_BUDGETS = [300.0, 1000.0, 10000.0]
QUALITY_SLOS = [0.20, 0.30, 0.40]
POLICY_NAMES = [
    "device_only", "edge_full_lru", "edge_win10_lru", "edge_sum200_lru",
    "reactive", "budget_aware", "lifecycle_aware",
]

# ─────────────────────────────────────────────────────────────────────────────
# LATENCY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _interp_7b(table: dict, L: float):
    """Interpolate Jetson qwen7b value at L.  Returns (val, note) or (None, reason)."""
    if L >= JETSON_7B_INFEASIBLE_L:
        return None, "infeasible-boundary"
    keys = sorted(table)
    if L <= keys[0]:
        return table[keys[0]] * L / keys[0], "extrap-below-min"
    if L > keys[-1]:
        # Do not extrapolate past infeasibility; interpolate within the gap [max, infeasible)
        rate = keys[-1] / table[keys[-1]]   # tok/ms at last measured point [A4]
        return L / rate, "extrap-above-max[A4]"
    for i in range(len(keys) - 1):
        if keys[i] <= L <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            f = (L - lo) / (hi - lo)
            return (1 - f) * table[lo] + f * table[hi], "interpolated"


def device_incr_warm_ms(L: float, scale: float) -> float | None:
    """qwen3b Jetson warm-append TTFT at context length L.  [A1, A4]"""
    v, _ = _interp_7b(JETSON_7B_INCR_WARM, L)
    return None if v is None else v * scale


def device_cold_restore_ms(L: float, scale: float) -> float | None:
    """qwen3b Jetson cold-restore TTFT at context length L.  [A1]"""
    v, _ = _interp_7b(JETSON_7B_FULL_RESTORE, L)
    return None if v is None else v * scale


def edge_cold_restore_ms(L_tokens: float) -> float:
    """A6000 qwen7b cold prefill from text at L tokens."""
    return (L_tokens / EDGE_COLD_PREFILL_RATE) * 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 0 — HEADROOM GATE (corrected)
# ─────────────────────────────────────────────────────────────────────────────

def _locomo_lat_fail(budget_ms: float, scale: float) -> float:
    fails, total = 0, 0
    for ctx, n_sess in zip(LOCOMO_CTX_TOKENS, LOCOMO_N_SESSIONS):
        tps = ctx / n_sess
        tpt = tps / TURNS_PER_SESSION
        for s in range(n_sess):
            for t in range(TURNS_PER_SESSION):
                L = s * tps + t * tpt
                ms = device_incr_warm_ms(L, scale)
                total += 1
                if ms is None or ms > budget_ms:
                    fails += 1
    return fails / total


def _egoschema_lat_fail(budget_ms: float, scale: float) -> float:
    fails = sum(
        1 for L in EGOSCHEMA_CTX_TOKENS
        if (lambda v: v is None or v > budget_ms)(device_cold_restore_ms(L, scale))
    )
    return fails / len(EGOSCHEMA_CTX_TOKENS)


def run_stage0() -> dict:
    print("=" * 70)
    print("STAGE 0 — Headroom Gate (corrected)")
    print("  LoCoMo:    warm-append per turn (E23 incr_warm, qwen7b x A1)")
    print("  EgoSchema: cold restore per query (E23 full_restore, qwen7b x A1)")
    print("  A1 range:  s=0.43 (lower bound) to s=1.00 (upper bound)")
    print("=" * 70)

    cells = []
    n_nd = {s: 0 for s in A1_SCALES}

    hdr = (f"{'workload':12s} {'budget':>7s} {'q_slo':>5s} | "
           f"{'Q_dev':>5s} {'q≥SLO':>7s} | "
           f"{'lat_s43':>8s} {'lat_s10':>8s} | {'disc?':>8s}")
    print(hdr)
    print("-" * len(hdr))

    for wl in WORKLOADS:
        Q_dev = Q_TABLE[("full", wl, "qwen3b")]
        for budget in TTFT_BUDGETS:
            lat = {}
            for s in A1_SCALES:
                lat[s] = (_locomo_lat_fail(budget, s) if wl == "locomo"
                          else _egoschema_lat_fail(budget, s))
            for q_slo in QUALITY_SLOS:
                q_passes = Q_dev >= q_slo
                disc = {s: (not q_passes) or (lat[s] > 0.05) for s in A1_SCALES}
                for s in A1_SCALES:
                    if not disc[s]:
                        n_nd[s] += 1
                d_str = ("YES" if all(disc.values())
                         else "NO" if not any(disc.values())
                         else "PARTIAL")
                q_str = "PASS" if q_passes else f"FAIL({q_slo-Q_dev:+.2f})"
                print(
                    f"{wl:12s} {budget:>7.0f} {q_slo:>5.2f} | "
                    f"{Q_dev:>5.3f} {q_str:>12s} | "
                    f"{lat[0.43]:>7.1%} {lat[1.00]:>7.1%} | {d_str:>8s}"
                )
                cells.append({
                    "workload": wl, "budget_ms": budget, "quality_slo": q_slo,
                    "Q_device": Q_dev, "quality_passes": q_passes,
                    "lat_fail_s043": round(lat[0.43], 4),
                    "lat_fail_s100": round(lat[1.00], 4),
                    "disc_s043": disc[0.43],
                    "disc_s100": disc[1.00],
                })

    total = len(cells)
    print()
    for s in A1_SCALES:
        print(f"  Non-discriminating (s={s:.2f}): {n_nd[s]}/{total} "
              f"({n_nd[s]/total:.0%})")
    gate = all(n_nd[s] / total <= 0.50 for s in A1_SCALES)
    print(f"\nGATE (K1): {'PASS' if gate else 'FAIL — stop before Stage 1'}")

    return {
        "stage": "stage0_corrected", "gate_passes": gate,
        "n_cells": total, "n_nondiscrim": n_nd,
        "cells": cells,
        "assumptions": [
            "A1: qwen3b_time = s x qwen7b_time (time ratio, not rate). "
            "Shown at s=0.43 and s=1.00. Not directly measured.",
            "A2: EgoSchema contexts assumed 1500-2500 tok. Not committed.",
            "A4: incr_warm for L in (16384, 24576) uses rate extrapolated "
            "from last measured point L=16384; not past infeasibility boundary.",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION CORE
# ─────────────────────────────────────────────────────────────────────────────

class _EdgeTier:
    """Shared KV cache with LRU admission."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._lru: list[int] = []   # oldest first

    def has_slot(self) -> bool:
        return len(self._lru) < self.capacity

    def is_warm(self, rid: int) -> bool:
        return rid in self._lru

    def touch(self, rid: int):
        if rid in self._lru:
            self._lru.remove(rid)
        self._lru.append(rid)

    def admit_lru(self, rid: int) -> int | None:
        """Admit rid; return evicted rid or None."""
        if rid in self._lru:
            self.touch(rid)
            return None
        if len(self._lru) < self.capacity:
            self._lru.append(rid)
            return None
        evicted = self._lru.pop(0)
        self._lru.append(rid)
        return evicted

    def evict(self, rid: int):
        if rid in self._lru:
            self._lru.remove(rid)


class _RobotState:
    __slots__ = ["rid", "session_idx", "turn_in_session",
                 "context_L", "admitted", "fidelity",
                 "_ctx_per_session", "_tok_per_turn"]

    def __init__(self, rid: int, ctx_per_session: float, tok_per_turn: float):
        self.rid = rid
        self.session_idx = 0
        self.turn_in_session = 0
        self.context_L = 0.0            # current KV context length on device
        self.admitted = False
        self.fidelity: str | None = None
        self._ctx_per_session = ctx_per_session
        self._tok_per_turn = tok_per_turn

    def advance_turn(self):
        self.turn_in_session += 1
        self.context_L += self._tok_per_turn

    def new_session(self):
        self.session_idx += 1
        self.turn_in_session = 0
        # full representation: context grows each session
        # (context_L already accumulated; a new session adds another block)

    @property
    def is_session_start(self) -> bool:
        return self.turn_in_session == 0


# ─────────────────────────────────────────────────────────────────────────────
# EDGE TTFT CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def _edge_ttft(fidelity: str, workload: str, robot: _RobotState,
               newly_admitted: bool, scale: float) -> float:
    """TTFT served from edge (A6000, qwen7b)."""
    if workload == "egoschema":
        # EgoSchema: each query is independent; even on edge, context must be
        # re-loaded for each new question.
        if fidelity == "sum200":
            return EDGE_SUM200_RESTORE_MS
        elif fidelity == "win10":
            return EDGE_WIN10_INTRA_MS    # short caption window, always intra-like
        else:  # full
            L = random.choice(EGOSCHEMA_CTX_TOKENS)
            return edge_cold_restore_ms(L)

    # LoCoMo: continuous session
    if newly_admitted:
        if fidelity == "full":
            return edge_cold_restore_ms(robot.context_L)
        elif fidelity == "win10":
            return edge_cold_restore_ms(WIN10_TOKENS_MEDIAN)
        else:  # sum200
            return EDGE_SUM200_RESTORE_MS

    if fidelity == "full":
        return EDGE_FULL_WARM_APPEND_MS
    elif fidelity == "win10":
        if robot.is_session_start:
            return EDGE_WIN10_INTER_MS
        return EDGE_WIN10_INTRA_MS
    else:  # sum200
        return EDGE_SUM200_RESTORE_MS


def _device_ttft(workload: str, robot: _RobotState, scale: float) -> float:
    """TTFT served from device (Jetson, qwen3b). [A1]"""
    if workload == "egoschema":
        L = random.choice(EGOSCHEMA_CTX_TOKENS)
        ms = device_cold_restore_ms(L, scale)
        return ms if ms is not None else 120_000.0   # infeasible → 120 s penalty
    # LoCoMo: warm-append from device's own KV cache
    ms = device_incr_warm_ms(robot.context_L, scale)
    return ms if ms is not None else 120_000.0


def _get_quality(tier: str, fidelity: str, workload: str) -> float:
    model = "qwen7b" if tier == "edge" else "qwen3b"
    return Q_TABLE.get((fidelity, workload, model), 0.0)


def _lifecycle_fidelity(workload: str, q_slo: float,
                        turns_remaining: int) -> str:
    """Fidelity minimising quality_deficit*turns_remaining + maint_cost_norm."""
    # Maintenance cost (ms → s): full=66ms/turn, win10=1031ms/session, sum200=5822ms/update
    costs = {"full": 0.066, "win10": 1.031, "sum200": 5.822}
    best, best_score = "full", float("inf")
    for fid in ("full", "win10", "sum200"):
        Q_f = Q_TABLE.get((fid, workload, "qwen7b"), 0.0)
        deficit = max(0.0, q_slo - Q_f)
        score = deficit * turns_remaining + costs[fid]
        if score < best_score:
            best_score = score
            best = fid
    return best


def _budget_fidelity(workload: str, budget_ms: float,
                     is_session_start: bool, newly_admitted: bool) -> str:
    """Cheapest fidelity whose typical TTFT fits within budget."""
    candidates = [
        ("sum200", EDGE_SUM200_RESTORE_MS),
        ("win10",  EDGE_WIN10_INTER_MS if is_session_start else EDGE_WIN10_INTRA_MS),
        ("full",   EDGE_FULL_WARM_APPEND_MS),
    ]
    for fid, est in candidates:
        if not newly_admitted:
            if est <= budget_ms:
                return fid
        else:
            # cold-admit cost is always higher; still try to pick cheapest
            restore = (EDGE_SUM200_RESTORE_MS if fid == "sum200"
                       else edge_cold_restore_ms(WIN10_TOKENS_MEDIAN) if fid == "win10"
                       else edge_cold_restore_ms(20_000))
            if restore <= budget_ms:
                return fid
    return "full"   # fallback: best quality


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION RUN
# ─────────────────────────────────────────────────────────────────────────────

def run_one(policy: str, n_robots: int, capacity: int,
            workload: str, q_slo: float, n_sessions: int,
            scale: float, seed: int) -> dict:
    """
    Simulate one fleet configuration.  Returns per-(budget, q_slo) metrics.
    """
    rng = random.Random(seed)

    # Build robots — each robot is assigned one LoCoMo conversation (cycling)
    robots: dict[int, _RobotState] = {}
    for rid in range(n_robots):
        conv_idx = rid % len(LOCOMO_CTX_TOKENS)
        ctx = LOCOMO_CTX_TOKENS[conv_idx]
        ns  = LOCOMO_N_SESSIONS[conv_idx]
        cps = ctx / ns                    # tokens per session block
        tpt = cps / TURNS_PER_SESSION     # tokens per turn
        robots[rid] = _RobotState(rid, cps, tpt)

    edge = _EdgeTier(capacity)

    # Per-query records: (ttft_ms, quality_correct)
    records: list[tuple[float, bool]] = []

    for _sess in range(n_sessions):
        for rid in list(robots):
            robots[rid].new_session()

        for _turn in range(TURNS_PER_SESSION):
            for rid in list(robots):
                robot = robots[rid]
                is_ss = robot.is_session_start

                if policy == "device_only":
                    ttft = _device_ttft(workload, robot, scale)
                    qual = rng.random() < _get_quality("device", "full", workload)

                elif policy in ("edge_full_lru", "edge_win10_lru", "edge_sum200_lru"):
                    fid = {"edge_full_lru": "full",
                           "edge_win10_lru": "win10",
                           "edge_sum200_lru": "sum200"}[policy]
                    was_warm = edge.is_warm(rid)
                    evicted  = edge.admit_lru(rid)
                    if evicted is not None and evicted in robots:
                        robots[evicted].admitted = False
                        robots[evicted].fidelity = None
                    newly = not was_warm
                    robot.admitted = True
                    robot.fidelity = fid
                    edge.touch(rid)
                    ttft = _edge_ttft(fid, workload, robot, newly, scale)
                    qual = rng.random() < _get_quality("edge", fid, workload)

                elif policy == "reactive":
                    if edge.is_warm(rid):
                        edge.touch(rid)
                        ttft = _edge_ttft("win10", workload, robot, False, scale)
                        qual = rng.random() < _get_quality("edge", "win10", workload)
                    elif edge.has_slot():
                        edge.admit_lru(rid)
                        robot.admitted = True
                        robot.fidelity = "win10"
                        ttft = _edge_ttft("win10", workload, robot, True, scale)
                        qual = rng.random() < _get_quality("edge", "win10", workload)
                    else:
                        ttft = _device_ttft(workload, robot, scale)
                        qual = rng.random() < _get_quality("device", "full", workload)

                elif policy == "budget_aware":
                    was_warm = edge.is_warm(rid)
                    evicted  = edge.admit_lru(rid)
                    if evicted is not None and evicted in robots:
                        robots[evicted].admitted = False
                        robots[evicted].fidelity = None
                    newly = not was_warm
                    edge.touch(rid)
                    # Choose fidelity at planning time; actual TTFT computed below
                    fid = _budget_fidelity(workload, min(TTFT_BUDGETS), is_ss, newly)
                    robot.admitted = True
                    robot.fidelity = fid
                    ttft = _edge_ttft(fid, workload, robot, newly, scale)
                    qual = rng.random() < _get_quality("edge", fid, workload)

                elif policy == "lifecycle_aware":
                    was_warm = edge.is_warm(rid)
                    evicted  = edge.admit_lru(rid)
                    if evicted is not None and evicted in robots:
                        robots[evicted].admitted = False
                        robots[evicted].fidelity = None
                    newly = not was_warm
                    edge.touch(rid)
                    turns_rem = TURNS_PER_SESSION - robot.turn_in_session
                    fid = _lifecycle_fidelity(workload, q_slo, turns_rem)
                    robot.admitted = True
                    robot.fidelity = fid
                    ttft = _edge_ttft(fid, workload, robot, newly, scale)
                    qual = rng.random() < _get_quality("edge", fid, workload)

                else:
                    raise ValueError(f"Unknown policy: {policy}")

                records.append((ttft, qual))
                robot.advance_turn()

    n_q = len(records)
    result = {"policy": policy, "n_robots": n_robots, "capacity": capacity,
              "cap_frac": round(capacity / n_robots, 2),
              "workload": workload, "q_slo": q_slo,
              "n_sessions": n_sessions, "scale": scale, "seed": seed,
              "n_queries": n_q}
    for budget in TTFT_BUDGETS:
        n_both = sum(1 for ttft, q in records if ttft <= budget and q)
        n_lat  = sum(1 for ttft, _ in records if ttft <= budget)
        result[f"both_met_{int(budget)}ms"] = round(n_both / n_q, 4)
        result[f"lat_met_{int(budget)}ms"]  = round(n_lat  / n_q, 4)
    result["quality_met"] = round(sum(q for _, q in records) / n_q, 4)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — POLICY SWEEP
# ─────────────────────────────────────────────────────────────────────────────

def run_stage1(n_sessions: int = 20,
               seeds: list[int] = (42, 99, 137)) -> dict:
    n_robots_list  = [5, 10, 20]
    cap_fracs      = [0.25, 0.50, 0.75, 1.00]
    total_runs = (len(POLICY_NAMES) * len(WORKLOADS) * len(QUALITY_SLOS)
                  * len(n_robots_list) * len(cap_fracs)
                  * len(A1_SCALES) * len(seeds))
    print(f"\n{'='*70}")
    print(f"STAGE 1 — Policy Sweep  ({total_runs} runs)")
    print(f"{'='*70}")

    results, done = [], 0
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            for nr in n_robots_list:
                for cf in cap_fracs:
                    cap = max(1, round(nr * cf))
                    for scale in A1_SCALES:
                        for seed in seeds:
                            for pol in POLICY_NAMES:
                                r = run_one(pol, nr, cap, wl, q_slo,
                                            n_sessions, scale, seed)
                                results.append(r)
                                done += 1
                                if done % 100 == 0:
                                    print(f"  {done}/{total_runs} …")

    print(f"  {total_runs}/{total_runs} done.")
    return {"stage": "stage1", "n_runs": len(results), "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — ANALYSIS AND KILL-CONDITION CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def _agg_key(r: dict, budget: float) -> tuple:
    return (r["workload"], budget, r["q_slo"], r["scale"])


def run_stage2(stage1: dict) -> dict:
    """Per-cell policy ranking and K2 check."""
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("STAGE 2 — Per-cell Policy Ranking")
    print(f"  Metric: both_met (TTFT ≤ budget AND quality correct)")
    print(f"  A1 sensitivity carried through at s=0.43 and s=1.00")
    print(f"{'='*70}")

    # Aggregate by (workload, budget, q_slo, scale, policy)
    sums: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for budget in TTFT_BUDGETS:
            key = _agg_key(r, budget)
            sums[key][r["policy"]].append(r[f"both_met_{int(budget)}ms"])

    cells_out = []
    k2_violations = []

    for key in sorted(sums):
        wl, budget, q_slo, scale = key
        pol_means = {p: statistics.mean(v) for p, v in sums[key].items()}
        ranked = sorted(pol_means, key=pol_means.get, reverse=True)

        dev_mean = pol_means.get("device_only", 0.0)
        lc_mean  = pol_means.get("lifecycle_aware", 0.0)
        gap_pp   = (lc_mean - dev_mean) * 100.0

        k2_ok = gap_pp >= 5.0
        if not k2_ok:
            k2_violations.append((wl, budget, q_slo, scale, gap_pp))

        cell = {
            "workload": wl, "budget_ms": budget, "quality_slo": q_slo,
            "scale": scale,
            "ranking": [{
                "policy": p, "both_met": round(pol_means[p], 4),
                "gap_vs_device_pp": round((pol_means[p] - dev_mean) * 100, 2),
            } for p in ranked],
            "lifecycle_vs_device_gap_pp": round(gap_pp, 2),
            "k2_ok": k2_ok,
        }
        cells_out.append(cell)

    # Print Stage 2 table
    print(f"\n{'workload':12s} {'budget':>7s} {'q_slo':>5s} {'s':>5s} | "
          f"{'device':>7s} {'lc_aware':>9s} {'gap_pp':>8s} | K2")
    print("-" * 70)
    for c in cells_out:
        dev = next((x["both_met"] for x in c["ranking"] if x["policy"] == "device_only"), 0.0)
        lc  = next((x["both_met"] for x in c["ranking"] if x["policy"] == "lifecycle_aware"), 0.0)
        k2  = "PASS" if c["k2_ok"] else "FAIL"
        print(f"{c['workload']:12s} {c['budget_ms']:>7.0f} {c['quality_slo']:>5.2f} "
              f"{c['scale']:>5.2f} | {dev:>7.3f} {lc:>9.3f} {c['lifecycle_vs_device_gap_pp']:>7.1f}pp | {k2}")

    print()
    if k2_violations:
        print(f"K2 VIOLATIONS ({len(k2_violations)} cells):")
        for v in k2_violations:
            wl, bud, q_slo, sc, gap = v
            print(f"  {wl} / {bud:.0f}ms / q_slo={q_slo} / s={sc:.2f}: gap={gap:+.1f}pp")
    else:
        print("K2: PASS — lifecycle_aware beats device_only by >5pp in all cells.")

    return {
        "stage": "stage2",
        "cells": cells_out,
        "k2_violations": [
            {"workload": v[0], "budget_ms": v[1], "quality_slo": v[2],
             "scale": v[3], "gap_pp": round(v[4], 2)}
            for v in k2_violations
        ],
        "k2_passes": len(k2_violations) == 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    s0 = run_stage0()
    (OUT_DIR / "stage0_headroom.json").write_text(json.dumps(s0, indent=2))
    print(f"\nStage 0 saved.")

    if not s0["gate_passes"]:
        print("Stopping at Stage 0 (K1).")
        return

    s1 = run_stage1()
    (OUT_DIR / "stage1_sweep.json").write_text(json.dumps(s1, indent=2))
    print(f"Stage 1 saved: {len(s1['results'])} runs.")

    s2 = run_stage2(s1)
    (OUT_DIR / "stage2_analysis.json").write_text(json.dumps(s2, indent=2))
    print(f"Stage 2 saved.")


if __name__ == "__main__":
    main()
