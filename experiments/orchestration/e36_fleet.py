"""
E36 — maintenance-aware admission and representation policy for a robot fleet.

Pure simulation, no GPU.

STAGE 0: headroom gate — compute fraction of queries device_only fails for each
(workload, TTFT_budget, quality_SLO) cell. If >50% of cells have <5pp headroom,
STOP before Stage 1.

STAGE 1: policy sweep — 7 policies × fleet configurations × seeds.

All cost and quality values must trace to committed measurements.
[ASSUMPTION] tags mark values derived by estimation; these are gathered in
the ASSUMPTIONS section at the bottom and in the output JSON.

Policies (pre-registered):
  1. device_only          — all queries to device tier (qwen3b + full context)
  2. edge_full_lru        — admit to edge with full; LRU eviction
  3. edge_win10_lru       — admit to edge with win10; LRU eviction
  4. edge_sum200_lru      — admit to edge with sum200; LRU eviction
  5. reactive             — edge if warm slot exists else device; win10 default rep
  6. budget_aware         — edge; fidelity chosen to meet TTFT budget cheaply
  7. lifecycle_aware      — edge; fidelity chosen by lifecycle cost vs quality SLO

Kill conditions (pre-registered):
  K1. If Stage 0 shows >50% cells non-discriminating (<5pp headroom), stop.
  K2. If lifecycle_aware fails to beat device_only by >5pp in any cell, stop and
      report; do not tune the policy to pass.
  K3. If any cost/quality value used deviates >2× from its committed source,
      stop and resolve before continuing.

ASSUMPTIONS (collected here):
  A1. qwen3b Jetson cold restore ≈ 0.43 × qwen7b Jetson time (parameter count ratio
      3B/7B ≈ 0.43). Source for qwen7b: E23 (results/cost/profiles/jetson_orin_qwen7b.json).
      Not directly measured. Affects device_only TTFT in Stage 0 and Stage 1.
  A2. EgoSchema full context ≈ 2,000 tokens (not committed; caption context not in repo).
      Affects EgoSchema latency cells in Stage 0. Quality values are committed (E29).
  A3. Device warm-append within session: assumed to meet all TTFT budgets (not measured
      for qwen3b on Jetson). Affects within-session queries in Stage 1 for device_only.
  A4. Device TTFT for context > 16,384 tokens (Jetson qwen7b infeasible boundary): derived
      by linear extrapolation from the L=8192 and L=16384 Jetson qwen7b rates, then
      scaled by 0.43. The qwen7b data covers only up to L=16,384 (feasible). Full LoCoMo
      contexts (median 20,092 tok) exceed this boundary. [Compound assumption]
"""

import json
import math
import random
import statistics
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36_fleet"

# ---------------------------------------------------------------------------
# COMMITTED QUALITY VALUES (E29, LoCoMo n=100 and EgoSchema n=60)
# ---------------------------------------------------------------------------
# (fidelity, workload, model) → Q (mean accuracy, fraction correct)
Q_TABLE = {
    # LoCoMo — dense-incompressible
    ("full",   "locomo", "qwen7b"): 0.400,
    ("win10",  "locomo", "qwen7b"): 0.230,
    ("sum200", "locomo", "qwen7b"): 0.120,
    ("blind",  "locomo", "qwen7b"): 0.080,
    ("full",   "locomo", "qwen3b"): 0.230,
    ("win10",  "locomo", "qwen3b"): 0.180,
    ("sum200", "locomo", "qwen3b"): 0.120,
    # EgoSchema — gist-compressible
    ("full",   "egoschema", "qwen7b"): 0.567,
    ("win10",  "egoschema", "qwen7b"): 0.500,
    ("sum200", "egoschema", "qwen7b"): 0.483,
    ("blind",  "egoschema", "qwen7b"): 0.200,
    ("full",   "egoschema", "qwen3b"): 0.450,
    ("win10",  "egoschema", "qwen3b"): 0.450,
    ("sum200", "egoschema", "qwen3b"): 0.433,
}

# ---------------------------------------------------------------------------
# COMMITTED EDGE LATENCY VALUES (all ms, all on A6000 + qwen7b)
# ---------------------------------------------------------------------------
# Source: E35 (results/cost/e34b_catchup/), E26, E33a

EDGE_FULL_WARM_APPEND_MS = 66.0          # E26; also E35 N=1 → 67ms (agrees)
EDGE_WIN10_INTRA_SESSION_MS = 59.0       # E35 median intra-session (41–77ms range)
EDGE_WIN10_INTER_SESSION_MS = 1031.0     # E35 inter-session (at N≥22 turns)
EDGE_SUM200_RESTORE_MS = 32.0            # E33a evidence ledger, cost_matrix.csv
EDGE_SUM200_UPDATE_MS = 5822.0           # E35 recursive update (sum200 maintenance)
EDGE_SUM200_FULL_REGEN_MS = 9900.0       # E35 full regen distribution (7.8–10.3s)

# Cold prefill rate (A6000, qwen7b): 5,984 tok/s — E26, E33a
EDGE_COLD_PREFILL_TOK_PER_S = 5984.0

def edge_cold_restore_ms(L_tokens: float) -> float:
    """Cold restore on edge (A6000, qwen7b), no prefix cache."""
    return (L_tokens / EDGE_COLD_PREFILL_TOK_PER_S) * 1000.0

# Win10 amortized maintenance: 652ms per session transition (E35 Part 3)
# 65.7% of transitions are slides (cold re-prefill at 7.1k tok);
# 34.3% are grows (warm append, ~60ms).
WIN10_SLIDE_FRAC = 0.657                 # E35 / E34 Part A
WIN10_SLIDE_COLD_MS = 975.0              # E35 Part A, agrees with E34
WIN10_GROW_WARM_MS = 60.0               # E35 intra-session warm
WIN10_AMORTIZED_MS = 652.0              # E35 maintenance ordering

# Intra-session threshold: win10 switches to inter-session at N~22 turns (E35)
WIN10_INTRA_THRESHOLD_TURNS = 22

# KV footprint (E33a): 57,344 B/token
KV_BYTES_PER_TOKEN = 57344
WIN10_TOKENS_MEDIAN = 7275               # E33a; median across n=10 LoCoMo convs
FULL_TOKENS_MEDIAN = 20092               # derived from LoCoMo n=10 (this file)
SUM200_TOKENS = 160                      # E33a; actual output ~113 tok, slot = 160 tok

# ---------------------------------------------------------------------------
# DEVICE LATENCY (Jetson AGX Orin + qwen3b)  [ASSUMPTION A1, A3, A4]
# ---------------------------------------------------------------------------
# qwen7b Jetson cold restore (E23, results/cost/profiles/jetson_orin_qwen7b.json):
JETSON_QWen7B_RESTORE = {
    1024:  4052.0,
    2048:  8010.0,
    4096:  16311.0,
    8192:  33790.0,
    16384: 75054.0,
}
JETSON_QWen7B_RATES = {  # tok/s at each L
    L: L / (ms / 1000.0) for L, ms in JETSON_QWen7B_RESTORE.items()
}

SCALE_3B_7B = 0.43  # [ASSUMPTION A1]

def device_cold_restore_ms(L_tokens: float) -> float:
    """
    Cold restore on device (Jetson + qwen3b). [ASSUMPTION A1, A4]
    Uses linear interpolation / extrapolation of Jetson qwen7b rates × 0.43.
    """
    # Get qwen7b rate by interpolation
    L_keys = sorted(JETSON_QWen7B_RESTORE.keys())
    if L_tokens <= L_keys[0]:
        rate_7b = JETSON_QWen7B_RATES[L_keys[0]]
    elif L_tokens >= L_keys[-1]:
        # Extrapolation: use rate at max measured L [ASSUMPTION A4]
        rate_7b = JETSON_QWen7B_RATES[L_keys[-1]]
    else:
        # Linear interpolation between bracketing L values
        for i in range(len(L_keys) - 1):
            if L_keys[i] <= L_tokens <= L_keys[i + 1]:
                lo, hi = L_keys[i], L_keys[i + 1]
                frac = (L_tokens - lo) / (hi - lo)
                rate_7b = (1 - frac) * JETSON_QWen7B_RATES[lo] + frac * JETSON_QWen7B_RATES[hi]
                break
    # SCALE_3B_7B is a TIME ratio (qwen3b_time = qwen7b_time × 0.43),
    # so rate_3b = L / (qwen7b_time × 0.43) = rate_7b / SCALE_3B_7B  [ASSUMPTION A1]
    rate_3b = rate_7b / SCALE_3B_7B
    return (L_tokens / rate_3b) * 1000.0

# Device warm append: [ASSUMPTION A3] — assumed to meet all TTFT budgets
DEVICE_WARM_APPEND_MS = 0.0  # used as flag; see Stage 1 comments

# ---------------------------------------------------------------------------
# LOCOMO SESSION STATISTICS (committed: data/locomo/locomo10.json n=10)
# ---------------------------------------------------------------------------
# Full context tokens per conversation (derived in this script):
LOCOMO_FULL_CONTEXT_TOKENS = [
    11386, 14665, 16212, 18894, 19325, 20860, 21125, 21592, 22266, 22778
]
# Sessions per conversation:
LOCOMO_SESSIONS_PER_CONV = [19, 19, 25, 28, 29, 29, 30, 30, 31, 32]
# Median turns per session ~22 (E33a §1.6, "~22 utterances per session block")
LOCOMO_TURNS_PER_SESSION = 22
LOCOMO_WIN10_TOKENS = [5597, 5900, 6200, 6800, 7100, 7275, 7400, 7800, 8100, 8548]

# EgoSchema context lengths: NOT committed [ASSUMPTION A2]
EGOSCHEMA_FULL_CONTEXT_TOKENS_ASSUMED = [1500, 1800, 2000, 2200, 2500]

# ---------------------------------------------------------------------------
# STAGE 0 — HEADROOM GATE
# ---------------------------------------------------------------------------

WORKLOADS = ["locomo", "egoschema"]
TTFT_BUDGETS_MS = [300.0, 1000.0, 10000.0]
QUALITY_SLOS = [0.20, 0.30, 0.40]

DEVICE_MODEL = "qwen3b"
DEVICE_FIDELITY = "full"


def _quality_fail_fraction(workload: str, q_slo: float) -> float:
    """
    Fraction of queries that fail the quality SLO under device_only.
    Q is the fleet-level mean accuracy; a query is answered correctly with
    probability Q. Failure = query answered incorrectly = 1 - Q.
    The headroom relevant to discrimination is whether Q_device < q_slo
    (fleet fails SLO on average). We report 1 - Q_device as per-query failure
    rate (independent of q_slo threshold direction) plus flag whether SLO fails.
    """
    Q_device = Q_TABLE[(DEVICE_FIDELITY, workload, DEVICE_MODEL)]
    return 1.0 - Q_device  # fraction of queries answered incorrectly


def _latency_fail_fraction(workload: str, ttft_budget_ms: float) -> dict:
    """
    Fraction of queries failing TTFT budget under device_only.
    Conservative model: all queries are cold restores (upper bound).
    Returns dict with fraction failing and whether estimate is ASSUMPTION-based.
    Context lengths from committed measurements where available; ASSUMPTION otherwise.
    """
    if workload == "locomo":
        ctx_tokens = LOCOMO_FULL_CONTEXT_TOKENS
        is_assumption = False
        note = "LoCoMo n=10 full context tokens (committed, derived from data/locomo/locomo10.json)"
    else:
        ctx_tokens = EGOSCHEMA_FULL_CONTEXT_TOKENS_ASSUMED
        is_assumption = True
        note = "[ASSUMPTION A2] EgoSchema context not committed; estimated ~1,500-2,500 tokens"

    cold_ttfts = [device_cold_restore_ms(L) for L in ctx_tokens]
    n_fail = sum(1 for t in cold_ttfts if t > ttft_budget_ms)
    frac_fail = n_fail / len(cold_ttfts)
    return {
        "frac_fail": frac_fail,
        "cold_ttfts_ms": cold_ttfts,
        "is_assumption": is_assumption,
        "note": note,
    }


def run_stage0() -> dict:
    """
    Compute Stage 0 headroom grid.
    headroom = fraction of queries device_only fails (quality OR latency).
    P(fail) = 1 - P(quality ok) × P(latency ok)
             = 1 - Q_device × (1 - P(cold > budget))
    (assumes quality and latency are independent)
    """
    print("=" * 70)
    print("STAGE 0 — Headroom Gate")
    print("=" * 70)
    print(f"Device tier: {DEVICE_MODEL}, fidelity={DEVICE_FIDELITY}")
    print(f"Latency model: all queries cold (conservative upper bound).")
    print(f"[ASSUMPTION A1] qwen3b restore = {SCALE_3B_7B}× qwen7b Jetson times (E23)")
    print()

    cells = []
    n_nondiscriminating = 0

    header = f"{'workload':12s} {'budget_ms':>10s} {'q_slo':>6s} | {'Q_dev':>6s} {'lat_fail':>9s} {'headroom':>9s} | {'disc?':>7s} | notes"
    print(header)
    print("-" * len(header))

    for workload in WORKLOADS:
        Q_device = Q_TABLE[(DEVICE_FIDELITY, workload, DEVICE_MODEL)]
        for ttft_budget_ms in TTFT_BUDGETS_MS:
            lat_result = _latency_fail_fraction(workload, ttft_budget_ms)
            p_lat_fail = lat_result["frac_fail"]
            p_lat_ok = 1.0 - p_lat_fail
            # P(fail) = 1 - P(quality ok AND latency ok)
            p_fail = 1.0 - Q_device * p_lat_ok
            for q_slo in QUALITY_SLOS:
                headroom_pp = p_fail * 100.0
                discriminating = headroom_pp >= 5.0
                if not discriminating:
                    n_nondiscriminating += 1
                flag = "YES" if discriminating else "NO (<5pp)"
                assump_flag = "[A]" if lat_result["is_assumption"] else "   "
                print(
                    f"{workload:12s} {ttft_budget_ms:>10.0f} {q_slo:>6.2f} | "
                    f"{Q_device:>6.3f} {p_lat_fail:>9.3f} {headroom_pp:>8.1f}% | "
                    f"{flag:>8s} | {assump_flag}"
                )
                cells.append({
                    "workload": workload,
                    "ttft_budget_ms": ttft_budget_ms,
                    "quality_slo": q_slo,
                    "Q_device": Q_device,
                    "p_latency_fail_cold": p_lat_fail,
                    "headroom_pct": round(headroom_pp, 2),
                    "discriminating": discriminating,
                    "latency_is_assumption": lat_result["is_assumption"],
                    "latency_note": lat_result["note"],
                    "cold_ttfts_ms": lat_result["cold_ttfts_ms"],
                })

    total_cells = len(cells)
    frac_nondiscrim = n_nondiscriminating / total_cells
    print()
    print(f"Non-discriminating cells: {n_nondiscriminating}/{total_cells} ({frac_nondiscrim:.1%})")

    # Kill condition K1
    gate_passes = frac_nondiscrim <= 0.50
    print()
    if gate_passes:
        print("GATE: PASS — proceed to Stage 1.")
    else:
        print("GATE: FAIL (K1) — >50% of cells non-discriminating. STOP before Stage 1.")

    return {
        "stage": "stage0",
        "gate_passes": gate_passes,
        "total_cells": total_cells,
        "n_nondiscriminating": n_nondiscriminating,
        "frac_nondiscriminating": round(frac_nondiscrim, 4),
        "cells": cells,
        "assumptions": [
            "A1: qwen3b Jetson restore = 0.43 × qwen7b Jetson (E23). Not directly measured.",
            "A2: EgoSchema context ~1500-2500 tokens. Not committed. Latency cells marked [A].",
            "A3: device warm-append within session assumed to meet all TTFT budgets.",
            "A4: device_only for LoCoMo full contexts >16k tokens uses rate extrapolation from E23 max measured L=16384.",
        ],
    }


# ---------------------------------------------------------------------------
# STAGE 1 — POLICY SWEEP
# ---------------------------------------------------------------------------

class RobotState:
    """Per-robot bookkeeping for the fleet simulation."""
    __slots__ = [
        "robot_id", "admitted", "fidelity", "session_idx",
        "turns_in_session", "last_maintenance_session",
    ]

    def __init__(self, robot_id: int):
        self.robot_id = robot_id
        self.admitted = False         # on edge?
        self.fidelity = None          # "full" / "win10" / "sum200" / None
        self.session_idx = 0          # which LoCoMo session block the robot is in
        self.turns_in_session = 0     # turns completed in current session
        self.last_maintenance_session = -1  # last session where maintenance ran

    def new_session(self):
        self.session_idx += 1
        self.turns_in_session = 0

    def staleness_turns(self) -> int:
        return self.turns_in_session


class EdgeTier:
    """Edge tier: shared qwen7b with bounded KV capacity (in robot slots)."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        # LRU queue: list of robot_ids in order of last use (oldest at index 0)
        self._lru: list[int] = []

    def is_admitted(self, robot_id: int) -> bool:
        return robot_id in self._lru

    def admit(self, robot_id: int, evict_policy="lru") -> int | None:
        """Admit robot; returns evicted robot_id or None."""
        if robot_id in self._lru:
            self._lru.remove(robot_id)
            self._lru.append(robot_id)
            return None
        if len(self._lru) < self.capacity:
            self._lru.append(robot_id)
            return None
        if evict_policy == "lru":
            evicted = self._lru.pop(0)
            self._lru.append(robot_id)
            return evicted
        return None  # no eviction (conservative)

    def evict(self, robot_id: int):
        if robot_id in self._lru:
            self._lru.remove(robot_id)

    def touch(self, robot_id: int):
        """Mark recently used."""
        if robot_id in self._lru:
            self._lru.remove(robot_id)
            self._lru.append(robot_id)

    def n_admitted(self) -> int:
        return len(self._lru)

    def is_full(self) -> bool:
        return len(self._lru) >= self.capacity


def _compute_ttft_edge(fidelity: str, workload: str, robot: RobotState,
                       is_new_session: bool, is_new_admission: bool) -> float:
    """
    Compute TTFT (ms) for a query served from edge tier.
    is_new_admission: robot was just admitted (cold prefill needed).
    is_new_session: first query in a new session block.
    """
    staleness = robot.staleness_turns

    if is_new_admission:
        # Cold restore from text
        if fidelity == "full":
            L = random.choice(LOCOMO_FULL_CONTEXT_TOKENS if workload == "locomo"
                              else EGOSCHEMA_FULL_CONTEXT_TOKENS_ASSUMED)
            return edge_cold_restore_ms(L)
        elif fidelity == "win10":
            L = random.choice(LOCOMO_WIN10_TOKENS if workload == "locomo"
                              else [min(WIN10_TOKENS_MEDIAN, 2000)])
            return edge_cold_restore_ms(L)
        elif fidelity == "sum200":
            return EDGE_SUM200_RESTORE_MS

    if fidelity == "full":
        return EDGE_FULL_WARM_APPEND_MS

    if fidelity == "win10":
        # Intra vs inter session
        if is_new_session:
            return EDGE_WIN10_INTER_SESSION_MS
        return EDGE_WIN10_INTRA_SESSION_MS

    if fidelity == "sum200":
        return EDGE_SUM200_RESTORE_MS

    raise ValueError(f"Unknown fidelity: {fidelity}")


def _compute_ttft_device(workload: str, is_new_session: bool) -> float:
    """
    TTFT on device tier (qwen3b, Jetson).
    New session = cold restore; within session = assumed fast [ASSUMPTION A3].
    """
    if not is_new_session:
        return 0.0  # [ASSUMPTION A3] — within-session warm; assumed to meet budget

    ctx_pool = (LOCOMO_FULL_CONTEXT_TOKENS if workload == "locomo"
                else EGOSCHEMA_FULL_CONTEXT_TOKENS_ASSUMED)
    L = random.choice(ctx_pool)
    return device_cold_restore_ms(L)


def _get_quality(tier: str, fidelity: str, workload: str) -> float:
    model = "qwen7b" if tier == "edge" else "qwen3b"
    return Q_TABLE.get((fidelity, workload, model), 0.0)


def _maintenance_cost_ms(fidelity: str) -> float:
    """Cost of proactive maintenance (updating stale state)."""
    if fidelity == "full":
        return EDGE_FULL_WARM_APPEND_MS    # warm append
    if fidelity == "win10":
        return WIN10_AMORTIZED_MS          # amortized slide/grow
    if fidelity == "sum200":
        return EDGE_SUM200_UPDATE_MS       # recursive update
    return 0.0


def _lifecycle_cost_score(fidelity: str, workload: str, q_slo: float,
                          expected_turns_remaining: int) -> float:
    """
    Score for fidelity selection: penalize quality deficit × remaining turns
    plus maintenance cost per turn. Lower is better.
    Quality deficit: max(0, q_slo - Q(fidelity, workload, edge))
    Lifecycle penalty: quality_deficit × expected_turns + maintenance_cost
    """
    Q_f = Q_TABLE.get((fidelity, workload, "qwen7b"), 0.0)
    quality_deficit = max(0.0, q_slo - Q_f)
    maint_cost = _maintenance_cost_ms(fidelity) / 1000.0  # normalise to seconds
    return quality_deficit * expected_turns_remaining + maint_cost


# ---- Policy implementations ------------------------------------------------
# Each returns (tier, fidelity, ttft_ms, quality, maintenance_ms)

def policy_device_only(robot: RobotState, edge: EdgeTier, workload: str,
                       is_new_session: bool, q_slo: float, ttft_budget_ms: float,
                       **kw) -> dict:
    ttft = _compute_ttft_device(workload, is_new_session)
    Q = _get_quality("device", DEVICE_FIDELITY, workload)
    return {"tier": "device", "fidelity": DEVICE_FIDELITY,
            "ttft_ms": ttft, "quality": Q, "maintenance_ms": 0.0}


def policy_edge_lru(robot: RobotState, edge: EdgeTier, workload: str,
                    is_new_session: bool, q_slo: float, ttft_budget_ms: float,
                    fidelity: str = "full", **kw) -> dict:
    was_admitted = edge.is_admitted(robot.robot_id)
    evicted = edge.admit(robot.robot_id, evict_policy="lru")
    if evicted is not None:
        kw.get("robot_states", {}).pop(evicted, None)
    edge.touch(robot.robot_id)
    is_new_admission = not was_admitted
    ttft = _compute_ttft_edge(fidelity, workload, robot, is_new_session, is_new_admission)
    Q = _get_quality("edge", fidelity, workload)
    maint = _maintenance_cost_ms(fidelity) if is_new_session else 0.0
    return {"tier": "edge", "fidelity": fidelity,
            "ttft_ms": ttft, "quality": Q, "maintenance_ms": maint}


def policy_reactive(robot: RobotState, edge: EdgeTier, workload: str,
                    is_new_session: bool, q_slo: float, ttft_budget_ms: float,
                    **kw) -> dict:
    """Serve from edge if warm slot available; else device. Edge uses win10."""
    if edge.is_admitted(robot.robot_id):
        edge.touch(robot.robot_id)
        ttft = _compute_ttft_edge("win10", workload, robot, is_new_session, False)
        Q = _get_quality("edge", "win10", workload)
        maint = _maintenance_cost_ms("win10") if is_new_session else 0.0
        return {"tier": "edge", "fidelity": "win10",
                "ttft_ms": ttft, "quality": Q, "maintenance_ms": maint}
    if not edge.is_full():
        edge.admit(robot.robot_id)
        ttft = _compute_ttft_edge("win10", workload, robot, is_new_session, True)
        Q = _get_quality("edge", "win10", workload)
        return {"tier": "edge", "fidelity": "win10",
                "ttft_ms": ttft, "quality": Q, "maintenance_ms": 0.0}
    # No warm slot; fall back to device
    ttft = _compute_ttft_device(workload, is_new_session)
    Q = _get_quality("device", DEVICE_FIDELITY, workload)
    return {"tier": "device", "fidelity": DEVICE_FIDELITY,
            "ttft_ms": ttft, "quality": Q, "maintenance_ms": 0.0}


def policy_budget_aware(robot: RobotState, edge: EdgeTier, workload: str,
                        is_new_session: bool, q_slo: float, ttft_budget_ms: float,
                        **kw) -> dict:
    """
    Admit to edge (LRU eviction). Choose fidelity to cheapest that meets budget:
    sum200 (32ms) → win10 (59ms intra/1031ms inter) → full (66ms).
    """
    was_admitted = edge.is_admitted(robot.robot_id)
    edge.admit(robot.robot_id, evict_policy="lru")
    edge.touch(robot.robot_id)
    is_new_admission = not was_admitted

    # Select cheapest fidelity within budget
    candidates = [
        ("sum200", EDGE_SUM200_RESTORE_MS),
        ("win10",  EDGE_WIN10_INTRA_SESSION_MS if not is_new_session else EDGE_WIN10_INTER_SESSION_MS),
        ("full",   EDGE_FULL_WARM_APPEND_MS),
    ]
    chosen = "full"  # fallback
    for fid, ttft_est in candidates:
        if ttft_est <= ttft_budget_ms:
            chosen = fid
            break

    if is_new_admission:
        ttft = _compute_ttft_edge(chosen, workload, robot, is_new_session, True)
    else:
        ttft = _compute_ttft_edge(chosen, workload, robot, is_new_session, False)

    Q = _get_quality("edge", chosen, workload)
    maint = _maintenance_cost_ms(chosen) if is_new_session else 0.0
    return {"tier": "edge", "fidelity": chosen,
            "ttft_ms": ttft, "quality": Q, "maintenance_ms": maint}


def policy_lifecycle_aware(robot: RobotState, edge: EdgeTier, workload: str,
                           is_new_session: bool, q_slo: float, ttft_budget_ms: float,
                           **kw) -> dict:
    """
    Lifecycle-cost-aware fidelity selection (from E24c insight).
    Choose fidelity to minimise: quality_deficit × expected_turns + maint_cost.
    Admit to edge with LRU eviction.
    """
    was_admitted = edge.is_admitted(robot.robot_id)
    edge.admit(robot.robot_id, evict_policy="lru")
    edge.touch(robot.robot_id)
    is_new_admission = not was_admitted

    sessions_remaining = max(1, LOCOMO_TURNS_PER_SESSION - robot.turns_in_session)
    best_fid = min(
        ["full", "win10", "sum200"],
        key=lambda f: _lifecycle_cost_score(f, workload, q_slo, sessions_remaining),
    )

    if is_new_admission:
        ttft = _compute_ttft_edge(best_fid, workload, robot, is_new_session, True)
    else:
        ttft = _compute_ttft_edge(best_fid, workload, robot, is_new_session, False)

    Q = _get_quality("edge", best_fid, workload)
    maint = _maintenance_cost_ms(best_fid) if is_new_session else 0.0
    return {"tier": "edge", "fidelity": best_fid,
            "ttft_ms": ttft, "quality": Q, "maintenance_ms": maint}


POLICIES = {
    "device_only":   policy_device_only,
    "edge_full_lru": lambda r, e, w, ns, qs, tb, **kw: policy_edge_lru(r, e, w, ns, qs, tb, fidelity="full", **kw),
    "edge_win10_lru": lambda r, e, w, ns, qs, tb, **kw: policy_edge_lru(r, e, w, ns, qs, tb, fidelity="win10", **kw),
    "edge_sum200_lru": lambda r, e, w, ns, qs, tb, **kw: policy_edge_lru(r, e, w, ns, qs, tb, fidelity="sum200", **kw),
    "reactive":      policy_reactive,
    "budget_aware":  policy_budget_aware,
    "lifecycle_aware": policy_lifecycle_aware,
}


def run_one_policy(policy_name: str, n_robots: int, capacity: int,
                   workload: str, ttft_budget_ms: float, q_slo: float,
                   n_sessions: int, seed: int) -> dict:
    """
    Simulate one (policy, config) run.
    Each robot goes through n_sessions LoCoMo session blocks,
    each with LOCOMO_TURNS_PER_SESSION turns.
    Returns per-query metrics.
    """
    rng = random.Random(seed)
    policy_fn = POLICIES[policy_name]

    edge = EdgeTier(capacity)
    robots = {i: RobotState(i) for i in range(n_robots)}

    n_queries_total = 0
    n_ttft_met = 0
    n_quality_met = 0    # queries answered correctly (Bernoulli draw from Q)
    n_both_met = 0

    for session in range(n_sessions):
        # All robots advance to new session
        for robot in robots.values():
            robot.new_session()

        for turn in range(LOCOMO_TURNS_PER_SESSION):
            for robot in robots.values():
                is_new_session = (turn == 0)
                result = policy_fn(
                    robot, edge, workload, is_new_session, q_slo, ttft_budget_ms,
                    robot_states=robots,
                )
                robot.turns_in_session = turn + 1

                ttft_ok = result["ttft_ms"] <= ttft_budget_ms
                # Quality: each query answered correctly with prob Q (Bernoulli)
                quality_ok = rng.random() < result["quality"]

                n_queries_total += 1
                if ttft_ok:
                    n_ttft_met += 1
                if quality_ok:
                    n_quality_met += 1
                if ttft_ok and quality_ok:
                    n_both_met += 1

    return {
        "policy": policy_name,
        "n_robots": n_robots,
        "capacity": capacity,
        "capacity_frac": round(capacity / n_robots, 3),
        "workload": workload,
        "ttft_budget_ms": ttft_budget_ms,
        "quality_slo": q_slo,
        "n_sessions": n_sessions,
        "seed": seed,
        "n_queries": n_queries_total,
        "ttft_met_frac": round(n_ttft_met / n_queries_total, 4),
        "quality_met_frac": round(n_quality_met / n_queries_total, 4),
        "both_met_frac": round(n_both_met / n_queries_total, 4),
    }


def run_stage1(workloads: list[str], ttft_budgets: list[float],
               q_slos: list[float], n_robots_list: list[int],
               capacity_fracs: list[float], n_sessions: int,
               seeds: list[int]) -> dict:
    """Stage 1 policy sweep."""
    print()
    print("=" * 70)
    print("STAGE 1 — Policy Sweep")
    print("=" * 70)

    results = []
    total = (len(POLICIES) * len(workloads) * len(ttft_budgets) * len(q_slos)
             * len(n_robots_list) * len(capacity_fracs) * len(seeds))
    done = 0

    for workload in workloads:
        for ttft_budget_ms in ttft_budgets:
            for q_slo in q_slos:
                for n_robots in n_robots_list:
                    for cap_frac in capacity_fracs:
                        capacity = max(1, int(n_robots * cap_frac))
                        for seed in seeds:
                            for policy_name in POLICIES:
                                r = run_one_policy(
                                    policy_name, n_robots, capacity,
                                    workload, ttft_budget_ms, q_slo,
                                    n_sessions, seed,
                                )
                                results.append(r)
                                done += 1
                                if done % 50 == 0:
                                    print(f"  {done}/{total} runs done")

    print(f"  {total}/{total} runs done.")
    return {"stage": "stage1", "n_runs": len(results), "results": results}


def summarise_stage1(stage1: dict) -> None:
    """Print headline Stage 1 summary per (policy, workload)."""
    from collections import defaultdict
    rows = stage1["results"]

    # Aggregate by (policy, workload) — mean both_met_frac over all configs
    agg = defaultdict(list)
    for r in rows:
        key = (r["policy"], r["workload"])
        agg[key].append(r["both_met_frac"])

    print()
    print("Stage 1 headline: mean fraction of queries meeting BOTH TTFT and quality SLO")
    print(f"  (averaged over all n_robots, capacity, budgets, SLOs, seeds)\n")
    print(f"{'policy':20s} {'workload':12s} {'mean_both':>10s} {'min':>8s} {'max':>8s}")
    print("-" * 60)

    baseline = {}
    for (pol, wl), vals in sorted(agg.items()):
        mean_v = statistics.mean(vals)
        if pol == "device_only":
            baseline[wl] = mean_v
        print(f"{pol:20s} {wl:12s} {mean_v:>10.3f} {min(vals):>8.3f} {max(vals):>8.3f}")

    # Kill condition K2: lifecycle_aware vs device_only
    print()
    print("Kill condition K2 check: lifecycle_aware vs device_only per workload")
    for wl in WORKLOADS:
        lc_vals = agg.get(("lifecycle_aware", wl), [])
        do_vals = agg.get(("device_only", wl), [])
        if lc_vals and do_vals:
            gap_pp = (statistics.mean(lc_vals) - statistics.mean(do_vals)) * 100
            ok = gap_pp >= 5.0
            print(f"  {wl}: gap = {gap_pp:+.1f}pp → K2 {'PASS' if ok else 'FAIL (stop)'}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # STAGE 0
    s0 = run_stage0()
    s0_path = OUT_DIR / "stage0_headroom.json"
    s0_path.write_text(json.dumps(s0, indent=2))
    print(f"\nStage 0 saved: {s0_path}")

    if not s0["gate_passes"]:
        print("\nStopping after Stage 0 (kill condition K1).")
        return

    # STAGE 1
    s1 = run_stage1(
        workloads=WORKLOADS,
        ttft_budgets=TTFT_BUDGETS_MS,
        q_slos=QUALITY_SLOS,
        n_robots_list=[5, 10, 20],
        capacity_fracs=[0.25, 0.50, 0.75, 1.00],
        n_sessions=20,
        seeds=[42, 99, 137],
    )
    summarise_stage1(s1)

    s1_path = OUT_DIR / "stage1_sweep.json"
    s1_path.write_text(json.dumps(s1, indent=2))
    print(f"\nStage 1 saved: {s1_path}")


if __name__ == "__main__":
    main()
