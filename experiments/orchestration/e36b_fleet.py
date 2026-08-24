"""
E36b — E36 re-run with measured 3B/7B device-tier time ratio replacing assumption A1.

Identical structure to e36_fleet.py with two changes:
  1. Device TTFT uses the measured L-dependent ratio from E37/E37b (a1_ratio_table.csv)
     rather than the assumed s ∈ {0.43, 1.00} bounds.
  2. A1_SCALES axis is removed; Stage 1 is a single-curve run (1,512 runs vs E36's 3,024).

Measured ratios (3B/7B, jetson_orin, E37):
  incr_warm  : {1024: 0.5934, 4096: 0.6406, 8192: 0.6810, 16384: 0.7046}  rises with L
  full_restore: {1024: 0.4749, 4096: 0.4960, 8192: 0.5175, 16384: 0.5419}  rises with L
  Both clamped at last measured value for L > 16384 (A4 still applies to 7B baseline).

Window rows excluded from ratio table: E37 window token counts are 261–483 (wrong
short-turn definition; correct win10 = 7,275 tok, E33a). No win10 device TTFT is computed.

EgoSchema note: modeled as short independent sessions (cold restore per query).
Device TTFT for EgoSchema uses the measured full_restore ratio.

Pre-registered kill conditions (unchanged from E36):
  K1: >50% non-discriminating → stop before Stage 1.
  K2: lifecycle_aware fails to beat device_only by >5pp in ANY cell → report; do NOT tune.
"""

import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36b_fleet"

# ─────────────────────────────────────────────────────────────────────────────
# COMMITTED MEASUREMENTS
# ─────────────────────────────────────────────────────────────────────────────

JETSON_7B_INCR_WARM    = {1024: 579.4, 2048: 666.8, 4096: 855.4,
                           8192: 1252.5, 16384: 2162.8}
JETSON_7B_FULL_RESTORE = {1024: 4052.5, 2048: 8009.5, 4096: 16310.6,
                           8192: 33790.3, 16384: 75053.7}
JETSON_7B_INFEASIBLE_L = 24576

# Measured 3B/7B ratios (E37/E37b, a1_ratio_table.csv)
A1_INCR_WARM_RATIO    = {1024: 0.5934, 4096: 0.6406, 8192: 0.6810, 16384: 0.7046}
A1_FULL_RESTORE_RATIO = {1024: 0.4749, 4096: 0.4960, 8192: 0.5175, 16384: 0.5419}

EDGE_FULL_WARM_APPEND_MS   = 66.0
EDGE_WIN10_INTRA_MS        = 59.0
EDGE_WIN10_INTER_MS        = 1031.0
EDGE_SUM200_RESTORE_MS     = 32.0
EDGE_SUM200_UPDATE_MS      = 5822.0
EDGE_COLD_PREFILL_RATE     = 5984.0

WIN10_TOKENS_MEDIAN        = 7275
SUM200_TOKENS              = 160

Q_TABLE = {
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

LOCOMO_CTX_TOKENS = [11386, 14665, 16212, 18894, 19325,
                     20860, 21125, 21592, 22266, 22778]
LOCOMO_N_SESSIONS = [19, 19, 25, 28, 29, 29, 30, 30, 31, 32]
TURNS_PER_SESSION = 22
EGOSCHEMA_CTX_TOKENS = [1500, 1800, 2000, 2200, 2500]

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

def _interp_table(table: dict, L: float) -> float | None:
    if L >= JETSON_7B_INFEASIBLE_L:
        return None
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


def _interp_ratio(ratio_table: dict, L: float) -> float:
    """Interpolate measured ratio, clamped at last measured value for L > max."""
    keys = sorted(ratio_table)
    if L <= keys[0]:
        return ratio_table[keys[0]]
    if L >= keys[-1]:
        return ratio_table[keys[-1]]
    for i in range(len(keys) - 1):
        if keys[i] <= L <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            f = (L - lo) / (hi - lo)
            return (1 - f) * ratio_table[lo] + f * ratio_table[hi]


def device_incr_warm_ms(L: float) -> float | None:
    """qwen3b Jetson warm-append TTFT using measured L-dependent ratio (E37)."""
    v7 = _interp_table(JETSON_7B_INCR_WARM, L)
    if v7 is None:
        return None
    return v7 * _interp_ratio(A1_INCR_WARM_RATIO, L)


def device_cold_restore_ms(L: float) -> float | None:
    """qwen3b Jetson cold-restore TTFT using measured L-dependent ratio (E37)."""
    v7 = _interp_table(JETSON_7B_FULL_RESTORE, L)
    if v7 is None:
        return None
    return v7 * _interp_ratio(A1_FULL_RESTORE_RATIO, L)


def edge_cold_restore_ms(L_tokens: float) -> float:
    return (L_tokens / EDGE_COLD_PREFILL_RATE) * 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 0 — HEADROOM GATE
# ─────────────────────────────────────────────────────────────────────────────

def _locomo_lat_fail(budget_ms: float) -> float:
    fails, total = 0, 0
    for ctx, n_sess in zip(LOCOMO_CTX_TOKENS, LOCOMO_N_SESSIONS):
        tps = ctx / n_sess
        tpt = tps / TURNS_PER_SESSION
        for s in range(n_sess):
            for t in range(TURNS_PER_SESSION):
                L = s * tps + t * tpt
                ms = device_incr_warm_ms(L)
                total += 1
                if ms is None or ms > budget_ms:
                    fails += 1
    return fails / total


def _egoschema_lat_fail(budget_ms: float) -> float:
    fails = sum(
        1 for L in EGOSCHEMA_CTX_TOKENS
        if (lambda v: v is None or v > budget_ms)(device_cold_restore_ms(L))
    )
    return fails / len(EGOSCHEMA_CTX_TOKENS)


def run_stage0() -> dict:
    print("=" * 70)
    print("STAGE 0 — Headroom Gate (measured A1 ratio, E37)")
    print("  Device TTFT: measured 3B/7B ratio, L-dependent (E37/E37b)")
    print("  LoCoMo: warm-append per turn; EgoSchema: cold-restore per query")
    print("=" * 70)

    cells = []
    n_nd = 0

    hdr = (f"{'workload':12s} {'budget':>7s} {'q_slo':>5s} | "
           f"{'Q_dev':>5s} {'q≥SLO':>12s} | {'lat_fail':>8s} | {'disc?':>5s}")
    print(hdr)
    print("-" * len(hdr))

    for wl in WORKLOADS:
        Q_dev = Q_TABLE[("full", wl, "qwen3b")]
        for budget in TTFT_BUDGETS:
            lat = _locomo_lat_fail(budget) if wl == "locomo" else _egoschema_lat_fail(budget)
            for q_slo in QUALITY_SLOS:
                q_passes = Q_dev >= q_slo
                disc = (not q_passes) or (lat > 0.05)
                if not disc:
                    n_nd += 1
                q_str = "PASS" if q_passes else f"FAIL({q_slo-Q_dev:+.2f})"
                print(
                    f"{wl:12s} {budget:>7.0f} {q_slo:>5.2f} | "
                    f"{Q_dev:>5.3f} {q_str:>12s} | "
                    f"{lat:>8.1%} | {'NO' if not disc else 'YES':>5s}"
                )
                cells.append({
                    "workload": wl, "budget_ms": budget, "quality_slo": q_slo,
                    "Q_device": Q_dev, "quality_passes": q_passes,
                    "lat_fail": round(lat, 4), "discriminating": disc,
                })

    total = len(cells)
    print(f"\n  Non-discriminating: {n_nd}/{total} ({n_nd/total:.0%})")
    gate = n_nd / total <= 0.50
    print(f"  GATE (K1): {'PASS' if gate else 'FAIL — stop before Stage 1'}")

    return {
        "stage": "stage0_measured", "gate_passes": gate,
        "n_cells": total, "n_nondiscrim": n_nd,
        "cells": cells,
        "device_model": "Measured 3B/7B ratio (E37/E37b, a1_ratio_table.csv)",
        "incr_warm_ratio_table": A1_INCR_WARM_RATIO,
        "full_restore_ratio_table": A1_FULL_RESTORE_RATIO,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION CORE
# ─────────────────────────────────────────────────────────────────────────────

class _EdgeTier:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._lru: list[int] = []

    def has_slot(self) -> bool:
        return len(self._lru) < self.capacity

    def is_warm(self, rid: int) -> bool:
        return rid in self._lru

    def touch(self, rid: int):
        if rid in self._lru:
            self._lru.remove(rid)
        self._lru.append(rid)

    def admit_lru(self, rid: int) -> int | None:
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
    __slots__ = ["rid", "session_idx", "turn_in_session", "context_L",
                 "admitted", "fidelity", "_ctx_per_session", "_tok_per_turn"]

    def __init__(self, rid: int, ctx_per_session: float, tok_per_turn: float):
        self.rid = rid
        self.session_idx = 0
        self.turn_in_session = 0
        self.context_L = 0.0
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

    @property
    def is_session_start(self) -> bool:
        return self.turn_in_session == 0


def _edge_ttft(fidelity: str, workload: str, robot: _RobotState,
               newly_admitted: bool) -> float:
    if workload == "egoschema":
        if fidelity == "sum200":
            return EDGE_SUM200_RESTORE_MS
        elif fidelity == "win10":
            return EDGE_WIN10_INTRA_MS
        else:
            L = random.choice(EGOSCHEMA_CTX_TOKENS)
            return edge_cold_restore_ms(L)

    if newly_admitted:
        if fidelity == "full":
            return edge_cold_restore_ms(robot.context_L)
        elif fidelity == "win10":
            return edge_cold_restore_ms(WIN10_TOKENS_MEDIAN)
        else:
            return EDGE_SUM200_RESTORE_MS

    if fidelity == "full":
        return EDGE_FULL_WARM_APPEND_MS
    elif fidelity == "win10":
        if robot.is_session_start:
            return EDGE_WIN10_INTER_MS
        return EDGE_WIN10_INTRA_MS
    else:
        return EDGE_SUM200_RESTORE_MS


def _device_ttft(workload: str, robot: _RobotState) -> float:
    if workload == "egoschema":
        L = random.choice(EGOSCHEMA_CTX_TOKENS)
        ms = device_cold_restore_ms(L)
        return ms if ms is not None else 120_000.0
    ms = device_incr_warm_ms(robot.context_L)
    return ms if ms is not None else 120_000.0


def _get_quality(tier: str, fidelity: str, workload: str) -> float:
    model = "qwen7b" if tier == "edge" else "qwen3b"
    return Q_TABLE.get((fidelity, workload, model), 0.0)


def _lifecycle_fidelity(workload: str, q_slo: float, turns_remaining: int) -> str:
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
            restore = (EDGE_SUM200_RESTORE_MS if fid == "sum200"
                       else edge_cold_restore_ms(WIN10_TOKENS_MEDIAN) if fid == "win10"
                       else edge_cold_restore_ms(20_000))
            if restore <= budget_ms:
                return fid
    return "full"


def run_one(policy: str, n_robots: int, capacity: int,
            workload: str, q_slo: float, n_sessions: int, seed: int) -> dict:
    rng = random.Random(seed)

    robots: dict[int, _RobotState] = {}
    for rid in range(n_robots):
        conv_idx = rid % len(LOCOMO_CTX_TOKENS)
        ctx = LOCOMO_CTX_TOKENS[conv_idx]
        ns  = LOCOMO_N_SESSIONS[conv_idx]
        cps = ctx / ns
        tpt = cps / TURNS_PER_SESSION
        robots[rid] = _RobotState(rid, cps, tpt)

    edge = _EdgeTier(capacity)
    records: list[tuple[float, bool]] = []

    for _sess in range(n_sessions):
        for rid in list(robots):
            robots[rid].new_session()

        for _turn in range(TURNS_PER_SESSION):
            for rid in list(robots):
                robot = robots[rid]
                is_ss = robot.is_session_start

                if policy == "device_only":
                    ttft = _device_ttft(workload, robot)
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
                    ttft = _edge_ttft(fid, workload, robot, newly)
                    qual = rng.random() < _get_quality("edge", fid, workload)

                elif policy == "reactive":
                    if edge.is_warm(rid):
                        edge.touch(rid)
                        ttft = _edge_ttft("win10", workload, robot, False)
                        qual = rng.random() < _get_quality("edge", "win10", workload)
                    elif edge.has_slot():
                        edge.admit_lru(rid)
                        robot.admitted = True
                        robot.fidelity = "win10"
                        ttft = _edge_ttft("win10", workload, robot, True)
                        qual = rng.random() < _get_quality("edge", "win10", workload)
                    else:
                        ttft = _device_ttft(workload, robot)
                        qual = rng.random() < _get_quality("device", "full", workload)

                elif policy == "budget_aware":
                    was_warm = edge.is_warm(rid)
                    evicted  = edge.admit_lru(rid)
                    if evicted is not None and evicted in robots:
                        robots[evicted].admitted = False
                        robots[evicted].fidelity = None
                    newly = not was_warm
                    edge.touch(rid)
                    fid = _budget_fidelity(workload, min(TTFT_BUDGETS), is_ss, newly)
                    robot.admitted = True
                    robot.fidelity = fid
                    ttft = _edge_ttft(fid, workload, robot, newly)
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
                    ttft = _edge_ttft(fid, workload, robot, newly)
                    qual = rng.random() < _get_quality("edge", fid, workload)

                else:
                    raise ValueError(f"Unknown policy: {policy}")

                records.append((ttft, qual))
                robot.advance_turn()

    n_q = len(records)
    result = {
        "policy": policy, "n_robots": n_robots, "capacity": capacity,
        "cap_frac": round(capacity / n_robots, 2),
        "workload": workload, "q_slo": q_slo,
        "n_sessions": n_sessions, "seed": seed, "n_queries": n_q,
    }
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

def run_stage1(n_sessions: int = 20, seeds: tuple = (42, 99, 137)) -> dict:
    n_robots_list = [5, 10, 20]
    cap_fracs     = [0.25, 0.50, 0.75, 1.00]
    total_runs = (len(POLICY_NAMES) * len(WORKLOADS) * len(QUALITY_SLOS)
                  * len(n_robots_list) * len(cap_fracs) * len(seeds))
    print(f"\n{'='*70}")
    print(f"STAGE 1 — Policy Sweep  ({total_runs} runs, measured A1 ratio)")
    print(f"{'='*70}")

    results, done = [], 0
    for wl in WORKLOADS:
        for q_slo in QUALITY_SLOS:
            for nr in n_robots_list:
                for cf in cap_fracs:
                    cap = max(1, round(nr * cf))
                    for seed in seeds:
                        for pol in POLICY_NAMES:
                            r = run_one(pol, nr, cap, wl, q_slo, n_sessions, seed)
                            results.append(r)
                            done += 1
                            if done % 100 == 0:
                                print(f"  {done}/{total_runs} …")

    print(f"  {total_runs}/{total_runs} done.")
    return {"stage": "stage1", "n_runs": len(results), "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_stage2(stage1: dict) -> dict:
    rows = stage1["results"]
    print(f"\n{'='*70}")
    print("STAGE 2 — Per-cell Policy Ranking (measured A1 ratio)")
    print(f"  Metric: both_met (TTFT ≤ budget AND quality correct)")
    print(f"{'='*70}")

    sums: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for budget in TTFT_BUDGETS:
            key = (r["workload"], budget, r["q_slo"])
            sums[key][r["policy"]].append(r[f"both_met_{int(budget)}ms"])

    cells_out = []
    k2_violations = []

    for key in sorted(sums):
        wl, budget, q_slo = key
        pol_means = {p: statistics.mean(v) for p, v in sums[key].items()}
        ranked = sorted(pol_means, key=pol_means.get, reverse=True)

        dev_mean = pol_means.get("device_only", 0.0)
        lc_mean  = pol_means.get("lifecycle_aware", 0.0)
        gap_pp   = (lc_mean - dev_mean) * 100.0

        k2_ok = gap_pp >= 5.0
        if not k2_ok:
            k2_violations.append((wl, budget, q_slo, gap_pp))

        cell = {
            "workload": wl, "budget_ms": budget, "quality_slo": q_slo,
            "ranking": [{
                "policy": p, "both_met": round(pol_means[p], 4),
                "gap_vs_device_pp": round((pol_means[p] - dev_mean) * 100, 2),
            } for p in ranked],
            "lifecycle_vs_device_gap_pp": round(gap_pp, 2),
            "k2_ok": k2_ok,
        }
        cells_out.append(cell)

    print(f"\n{'workload':12s} {'budget':>7s} {'q_slo':>5s} | "
          f"{'device':>7s} {'lc_aware':>9s} {'gap_pp':>8s} | K2")
    print("-" * 60)
    for c in cells_out:
        dev = next((x["both_met"] for x in c["ranking"] if x["policy"] == "device_only"), 0.0)
        lc  = next((x["both_met"] for x in c["ranking"] if x["policy"] == "lifecycle_aware"), 0.0)
        k2  = "PASS" if c["k2_ok"] else "FAIL"
        print(f"{c['workload']:12s} {c['budget_ms']:>7.0f} {c['quality_slo']:>5.2f} | "
              f"{dev:>7.3f} {lc:>9.3f} {c['lifecycle_vs_device_gap_pp']:>7.1f}pp | {k2}")

    print()
    if k2_violations:
        print(f"K2 VIOLATIONS ({len(k2_violations)} cells):")
        for v in k2_violations:
            wl, bud, q_slo, gap = v
            print(f"  {wl} / {bud:.0f}ms / q_slo={q_slo}: gap={gap:+.1f}pp")
    else:
        print("K2: PASS — lifecycle_aware beats device_only by >5pp in all cells.")

    return {
        "stage": "stage2",
        "cells": cells_out,
        "k2_violations": [
            {"workload": v[0], "budget_ms": v[1], "quality_slo": v[2], "gap_pp": round(v[3], 2)}
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
