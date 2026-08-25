"""
E36g — Marginal-benefit Admission Ordering

E36f showed S2 fails at ti=5s even when ALL robots select full (as confirmed
by the Section 4 trace at kv=9/36 GiB). The cause is admission ordering, not
selection. neff_ranked scores robots by N_eff(full, L) which is HIGHER for
small-L robots (smaller KV footprint → larger N_mem). Small-L robots are
therefore admitted first. But small-L robots may already meet both SLOs on
device (device TTFT < 1000ms at L < ~11,800 tokens, from E23×E37); admitting
them wastes scarce edge capacity on robots that derive zero marginal benefit
from edge residency. Large-L robots, which fail on device and depend on edge
residency, are evicted to make room.

This experiment adds two policies that separate representation selection from
admission ordering:

  neff_marginal (the fix):
    Part 1 (representation): argmax N_eff = min(N_mem, N_accel) per robot.
                              Identical to neff_ranked.
    Part 2 (admission):      order robots by marginal benefit of edge residency
                             (binary: 1 if device fails both_met, 0 if device
                             passes), then by N_eff DESC as tiebreaker.
    Marginal benefit is BINARY. A robot with marginal_benefit=0 contributes
    nothing to both_met whether or not it is admitted; a robot with
    marginal_benefit=1 contributes +1 only if admitted to the edge.

  oracle (upper bound):
    Part 1: same as neff_marginal.
    Part 2: marginal_benefit DESC, then KV footprint ASC (= L ASC for full,
            equivalent to N_eff DESC — packs maximum high-MB robots in KV).
    Note: at ti=5s when all robots select full, oracle = neff_marginal exactly
    (N_eff DESC ≡ KV ASC for full). Divergence appears at ti≥15s when some
    robots switch to win10 (fixed footprint 417MB regardless of L).

All other policies (neff_ranked, maintenance_aware, footprint_ranked, always_*,
device_only) are carried forward unchanged from E36f.

ASSUMPTIONS (carried from E36e/E36f):
  B1: SERVE_FULL_MS = 59ms (proxy from win10 intra-session E35)
  B2: No batching speedup for KV-append — unverified
  A2a: Stale trigger rate R(K) ≈ K/22 for LoCoMo — lower bound
  INFO: kv_cap and epoch_budget are fleet parameters; context_L and device
        TTFT are per-robot state available at admission time.

Diagnosis check (required item 2): at the three E36f failing cells (kv=4.5/9/36
at ti=5s), report admitted robots' context_L distribution split by
marginal_benefit, and compare neff_ranked vs neff_marginal vs always_full.
"""

import argparse
import json
import math
import random as _random
import statistics
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36g_marginal"
FIG_DIR = ROOT / "figures" / "orchestration"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── COMMITTED CONSTANTS (identical to E36e/E36f) ──────────────────────────────

KV_BYTES_PER_TOK     = 57_344
L_LOCOMO_MEDIAN      = 20_092
TOKENS_WIN10         = 7_275
TOKENS_SUM200        = 160

MAINT_FULL_MS        = 66.0
MAINT_WIN10_GROW_MS  = 36.0
MAINT_WIN10_SLIDE_MS = 1_031.0
SLIDE_FRAC           = 0.657
MAINT_WIN10_AMZ_MS   = SLIDE_FRAC * MAINT_WIN10_SLIDE_MS + (1 - SLIDE_FRAC) * MAINT_WIN10_GROW_MS
MAINT_SUM200_MS      = 5_822.0

SERVE_FULL_MS   = 59.0   # [ASSUMPTION B1]
SERVE_WIN10_MS  = 59.0
SERVE_SUM200_MS = 32.0

GIB          = 1 << 30
KV_CAPS_GIB  = [4.5, 9.0, 18.0, 36.0]
TI_S         = [5, 15, 30, 60]
WINDOW_SIZE_SESS = 10

JETSON_INCR_WARM_MS = {1024: 579.4, 2048: 666.8, 4096: 855.4,
                        8192: 1252.5, 16384: 2162.8}
A1_INCR_WARM_RATIO  = {1024: 0.5934, 4096: 0.6406, 8192: 0.6810, 16384: 0.7046}

LOCOMO_CTX_TOKENS = [20513, 17234, 19867, 23102, 15987, 22456, 18923, 21345,
                     16782, 19234, 20892, 17654, 21109, 19456, 18234, 20678,
                     22134, 17890, 21567, 18456]
LOCOMO_N_SESSIONS = [22, 19, 21, 25, 18, 24, 20, 23, 18, 21,
                     23, 19, 22, 21, 20, 22, 24, 19, 23, 20]
TURNS_PER_SESSION = 22

Q_LOCOMO    = {"full": 0.40, "win10": 0.23, "sum200": 0.12}
Q_EGOSCHEMA = {"full": 0.567, "win10": 0.500, "sum200": 0.483}

# Device TTFT crosses 1000ms at roughly this context_L (from E23 × E37 A1 ratio)
DEVICE_TTFT_1000MS_THRESHOLD = 11_800   # analytic; exact value from _device_ttft_ms


def _maint_ms(fidelity):
    if fidelity == "full":         return MAINT_FULL_MS
    if fidelity == "win10_amz":    return MAINT_WIN10_AMZ_MS
    if fidelity == "win10_slide":  return MAINT_WIN10_SLIDE_MS
    if fidelity == "win10_growth": return MAINT_WIN10_GROW_MS
    return MAINT_SUM200_MS

def _serve_ms(fidelity):
    if fidelity == "full":   return SERVE_FULL_MS
    if fidelity in ("win10_amz", "win10_slide", "win10_growth", "win10"): return SERVE_WIN10_MS
    return SERVE_SUM200_MS

def _robot_kv_bytes(robot, fidelity):
    if fidelity == "full":
        return KV_BYTES_PER_TOK * max(1, int(robot.context_L))
    if fidelity == "win10":
        return KV_BYTES_PER_TOK * TOKENS_WIN10
    return KV_BYTES_PER_TOK * TOKENS_SUM200

def _robot_maint_ms(robot, fidelity, workload):
    if workload == "egoschema": return 0.0
    if fidelity == "full":      return MAINT_FULL_MS
    if fidelity == "win10":
        return MAINT_WIN10_SLIDE_MS if robot.is_slide else MAINT_WIN10_GROW_MS
    return MAINT_SUM200_MS

def _q_value(fidelity, workload):
    if workload == "locomo": return Q_LOCOMO.get(fidelity, 0)
    return Q_EGOSCHEMA.get(fidelity, 0)

def _device_ttft_ms(L):
    bp = sorted(JETSON_INCR_WARM_MS)
    Lc = min(L, max(bp))
    def _interp(tbl, x):
        ks = sorted(tbl)
        if x <= ks[0]:  return tbl[ks[0]]
        if x >= ks[-1]: return tbl[ks[-1]]
        for i in range(len(ks)-1):
            if ks[i] <= x <= ks[i+1]:
                t = (x - ks[i]) / (ks[i+1] - ks[i])
                return tbl[ks[i]] * (1-t) + tbl[ks[i+1]] * t
        return tbl[ks[-1]]
    return _interp(JETSON_INCR_WARM_MS, Lc) * _interp(A1_INCR_WARM_RATIO, Lc)

def _device_both_met(robot, ttft_budget_ms, q_slo, workload):
    ttft = _device_ttft_ms(robot.context_L)
    q    = Q_LOCOMO["full"] if workload == "locomo" else Q_EGOSCHEMA["full"]
    return (ttft <= ttft_budget_ms) and (q >= q_slo)

def _marginal_benefit(robot, ttft_budget_ms, q_slo, workload):
    """Binary: 1 if robot fails on device (edge residency has positive value), 0 if device suffices."""
    return 0 if _device_both_met(robot, ttft_budget_ms, q_slo, workload) else 1


class Robot:
    __slots__ = ("rid", "ctx_tokens", "n_sess", "session_idx", "turn_idx")
    def __init__(self, rid, ctx_tokens, n_sess, session_idx, turn_idx):
        self.rid, self.ctx_tokens = rid, ctx_tokens
        self.n_sess, self.session_idx, self.turn_idx = n_sess, session_idx, turn_idx

    @property
    def context_L(self):
        tps = self.ctx_tokens / self.n_sess
        return min(self.session_idx * tps + self.turn_idx * (tps / TURNS_PER_SESSION),
                   self.ctx_tokens)

    @property
    def is_slide(self):
        return self.session_idx >= WINDOW_SIZE_SESS


def _make_robots(n, seed, workload):
    rng = _random.Random(seed)
    robots = {}
    for i in range(n):
        if workload == "egoschema":
            ctx = rng.randint(1500, 2500)
            robots[i] = Robot(i, ctx, 1, 0, rng.randint(0, TURNS_PER_SESSION - 1))
        else:
            idx   = i % len(LOCOMO_CTX_TOKENS)
            ctx   = LOCOMO_CTX_TOKENS[idx]
            nsess = LOCOMO_N_SESSIONS[idx]
            robots[i] = Robot(i, ctx, nsess,
                              rng.randint(0, nsess - 1),
                              rng.randint(0, TURNS_PER_SESSION - 1))
    return robots


def _advance_robot(robot):
    robot.turn_idx += 1
    if robot.turn_idx >= TURNS_PER_SESSION:
        robot.turn_idx = 0
        robot.session_idx = min(robot.session_idx + 1, robot.n_sess - 1)


def _neff_score(robot, fidelity, kv_cap_bytes, epoch_budget_ms):
    kv_r = _robot_kv_bytes(robot, fidelity)
    nm   = math.floor(kv_cap_bytes / kv_r) if kv_r > 0 else int(1e9)
    f_key = "win10_amz" if fidelity == "win10" else fidelity
    m    = _maint_ms(f_key)
    s    = _serve_ms(fidelity)
    na   = math.floor(epoch_budget_ms / (m + s)) if (m + s) > 0 else int(1e9)
    return min(nm, na)


def _choose_fidelity(policy, robot, workload, q_slo, ti_s,
                     kv_cap_bytes=0, epoch_budget_ms=0):
    admissible = [f for f in ("full", "win10", "sum200")
                  if _q_value(f, workload) >= q_slo]
    if not admissible:
        return None

    if policy == "always_full":    return "full"    if "full"    in admissible else admissible[0]
    if policy == "always_window":  return "win10"   if "win10"   in admissible else admissible[0]
    if policy == "always_summary": return "sum200"  if "sum200"  in admissible else admissible[0]
    if policy == "device_only":    return None

    if policy == "footprint_ranked":
        return max(admissible, key=lambda f: (
            _q_value(f, workload) / _robot_kv_bytes(robot, f)
            if _robot_kv_bytes(robot, f) > 0 else 0))

    if policy == "maintenance_aware":
        def _accel_score(f):
            f_key = "win10_amz" if f == "win10" else f
            m     = _maint_ms(f_key)
            s     = _serve_ms(f)
            return epoch_budget_ms / (m + s) if (m + s) > 0 else float("inf")
        return max(admissible, key=_accel_score)

    if policy in ("neff_ranked", "neff_marginal", "oracle"):
        # Part 1 for both neff_marginal and oracle: argmax N_eff (identical to neff_ranked)
        return max(admissible,
                   key=lambda f: _neff_score(robot, f, kv_cap_bytes, epoch_budget_ms))

    return "full"


def _simulate_epoch(policy, robots, kv_cap_bytes, epoch_budget_ms,
                    workload, q_slo, ttft_budget_ms, ti_s,
                    track_detail=False):
    per_robot_fidelity = {}
    for rid, r in robots.items():
        f = _choose_fidelity(policy, r, workload, q_slo, ti_s,
                             kv_cap_bytes=kv_cap_bytes,
                             epoch_budget_ms=epoch_budget_ms)
        per_robot_fidelity[rid] = f

    def admission_score(rid):
        f = per_robot_fidelity[rid]
        if f is None:
            return (-1e9, -1e9)
        r  = robots[rid]
        kv = _robot_kv_bytes(r, f)

        if policy == "footprint_ranked":
            q = _q_value(f, workload)
            return (0, q / kv if kv > 0 else 0)
        if policy == "maintenance_aware":
            f_key = "win10_amz" if f == "win10" else f
            m     = _maint_ms(f_key)
            s     = _serve_ms(f)
            return (0, epoch_budget_ms / (m + s) if (m + s) > 0 else float("inf"))
        if policy == "neff_ranked":
            return (0, _neff_score(r, f, kv_cap_bytes, epoch_budget_ms))
        if policy == "neff_marginal":
            # Part 2: marginal benefit first, then N_eff as tiebreaker
            mb   = _marginal_benefit(r, ttft_budget_ms, q_slo, workload)
            neff = _neff_score(r, f, kv_cap_bytes, epoch_budget_ms)
            return (mb, neff)
        if policy == "oracle":
            # Part 2: marginal benefit first, then KV footprint ASC (= -kv_bytes)
            # For full-only fleets, -kv_bytes DESC ≡ N_eff DESC ≡ L ASC.
            # Diverges from neff_marginal when robots choose win10 (fixed footprint).
            mb = _marginal_benefit(r, ttft_budget_ms, q_slo, workload)
            return (mb, -kv)
        return (0, 1.0)

    sorted_rids   = sorted(robots.keys(), key=admission_score, reverse=True)
    kv_used       = 0
    maint_used_ms = 0.0
    admitted      = {}

    for rid in sorted_rids:
        f = per_robot_fidelity[rid]
        if f is None:
            continue
        r  = robots[rid]
        kv = _robot_kv_bytes(r, f)
        m  = _robot_maint_ms(r, f, workload)
        s  = SERVE_WIN10_MS if f == "win10" else (SERVE_FULL_MS if f == "full" else SERVE_SUM200_MS)
        n_after = len(admitted) + 1
        if (kv_used + kv <= kv_cap_bytes and
                maint_used_ms + m + n_after * s <= epoch_budget_ms):
            admitted[rid] = f
            kv_used       += kv
            maint_used_ms += m

    n_both_met = 0
    for rid, r in robots.items():
        if rid in admitted:
            f    = admitted[rid]
            ttft = SERVE_WIN10_MS if f == "win10" else (SERVE_FULL_MS if f == "full" else SERVE_SUM200_MS)
            q    = _q_value(f, workload)
            both = (ttft <= ttft_budget_ms) and (q >= q_slo)
        else:
            both = _device_both_met(r, ttft_budget_ms, q_slo, workload)
        if both:
            n_both_met += 1

    for r in robots.values():
        _advance_robot(r)

    result = {
        "both_met_frac": n_both_met / len(robots) if robots else 0,
        "n_admitted":    len(admitted),
        "kv_used_gib":   kv_used / GIB,
        "maint_used_ms": maint_used_ms,
    }
    if track_detail:
        # Track admitted robots' context_L and marginal_benefit at this epoch
        admitted_detail = []
        for rid in admitted:
            r  = robots[rid]
            mb = _marginal_benefit(r, ttft_budget_ms, q_slo, workload)
            admitted_detail.append({
                "rid": rid,
                "context_L": r.context_L,
                "marginal_benefit": mb,
                "fidelity": admitted[rid],
            })
        result["admitted_detail"] = admitted_detail
    return result


# ── SWEEP CONFIGURATION ───────────────────────────────────────────────────────

POLICIES  = ["device_only", "always_full", "always_window",
             "footprint_ranked", "maintenance_aware",
             "neff_ranked", "neff_marginal", "oracle"]
N_ROBOTS  = [50]
WORKLOADS = ["locomo", "egoschema"]
Q_SLOS    = [0.20, 0.30]
TTFT_MS   = 1000
SEEDS     = [42, 123, 7]
N_EPOCHS  = 30

# Cells where we track admitted-robot detail (diagnosis check items)
DIAG_CELLS = [(4.5, 5), (9.0, 5), (36.0, 5)]


def run_sweep():
    import itertools
    all_results  = []
    diag_records = []   # detailed admission records for DIAG_CELLS
    total = (len(POLICIES) * len(N_ROBOTS) * len(KV_CAPS_GIB) * len(TI_S)
             * len(WORKLOADS) * len(Q_SLOS) * len(SEEDS))
    done  = 0

    for (policy, n_robots, kv_cap, ti_s, workload, q_slo, seed) in itertools.product(
            POLICIES, N_ROBOTS, KV_CAPS_GIB, TI_S, WORKLOADS, Q_SLOS, SEEDS):

        is_diag = ((kv_cap, ti_s) in DIAG_CELLS and
                   workload == "locomo" and q_slo == 0.20 and
                   policy in ("neff_ranked", "neff_marginal", "always_full", "oracle"))

        epoch_budget_ms = ti_s * 1000.0
        kv_cap_bytes    = int(kv_cap * GIB)
        robots          = _make_robots(n_robots, seed, workload)
        fracs           = []

        for ep_idx in range(N_EPOCHS):
            track = is_diag and (ep_idx == 0)
            ep    = _simulate_epoch(policy, robots, kv_cap_bytes, epoch_budget_ms,
                                    workload, q_slo, TTFT_MS, ti_s,
                                    track_detail=track)
            fracs.append(ep["both_met_frac"])
            if track:
                for d in ep.get("admitted_detail", []):
                    diag_records.append({
                        "policy": policy, "kv_cap_gib": kv_cap, "ti_s": ti_s,
                        "seed": seed, **d
                    })

        all_results.append({
            "policy": policy, "n_robots": n_robots, "kv_cap_gib": kv_cap,
            "ti_s": ti_s, "workload": workload, "q_slo": q_slo, "seed": seed,
            "both_met_mean": statistics.mean(fracs),
        })
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{total}")

    out = OUT_DIR / "e36g_sweep.json"
    with open(out, "w") as fh:
        json.dump(all_results, fh, indent=2)
    print(f"[saved] {out}")

    dout = OUT_DIR / "e36g_diag_detail.json"
    with open(dout, "w") as fh:
        json.dump(diag_records, fh, indent=2)
    print(f"[saved] {dout}")

    return all_results, diag_records


def _agg(results, policy, kv, ti, workload="locomo", q_slo=0.20):
    vals = [r["both_met_mean"] for r in results
            if (r["policy"] == policy and r["kv_cap_gib"] == kv and r["ti_s"] == ti
                and r["workload"] == workload and r["q_slo"] == q_slo)]
    return statistics.mean(vals) if vals else None


def run_analysis(results, diag_records):
    lines = []
    out   = {}

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 72)
    emit("E36g — Marginal-benefit Admission Ordering Analysis")
    emit("=" * 72)

    # ── 1. S2 for neff_marginal alongside neff_ranked ─────────────────────────
    emit()
    emit("─" * 60)
    emit("1. S2 — neff_marginal and neff_ranked vs best fixed policy")
    emit("   locomo, q=0.20, ttft=1000ms, n=50, mean over 3 seeds")
    emit()

    fixed_policies = ["always_full", "always_window", "always_summary"]
    s2_table = []

    emit(f"  {'kv':>6s}  {'ti':>4s}  {'best_fixed':>14s}  {'bf':>5s}  "
         f"{'neff_r':>6s}  {'reg_r':>6s}  {'verd_r':>6s}  "
         f"{'neff_m':>6s}  {'reg_m':>6s}  {'verd_m':>6s}")

    s2_fail_neff_r = []
    s2_fail_neff_m = []

    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            fp_vals = {}
            for fp in fixed_policies:
                v = _agg(results, fp, kv, ti)
                if v is not None:
                    fp_vals[fp] = v
            if not fp_vals:
                continue
            best_fp   = max(fp_vals, key=lambda p: fp_vals[p])
            bf_val    = fp_vals[best_fp]
            nr_val    = _agg(results, "neff_ranked",   kv, ti)
            nm_val    = _agg(results, "neff_marginal", kv, ti)
            if nr_val is None or nm_val is None:
                continue

            reg_r  = bf_val - nr_val
            reg_m  = bf_val - nm_val
            verd_r = "PASS" if reg_r <= 0.05 else "FAIL"
            verd_m = "PASS" if reg_m <= 0.05 else "FAIL"
            if verd_r == "FAIL": s2_fail_neff_r.append((kv, ti, reg_r))
            if verd_m == "FAIL": s2_fail_neff_m.append((kv, ti, reg_m))

            emit(f"  {kv:>6.1f}  {ti:>4d}  {best_fp:>14s}  {bf_val:>5.3f}  "
                 f"{nr_val:>6.3f}  {reg_r:>+6.3f}  {verd_r:>6s}  "
                 f"{nm_val:>6.3f}  {reg_m:>+6.3f}  {verd_m:>6s}")

            s2_table.append({
                "kv": kv, "ti": ti, "best_fixed": best_fp, "bf_val": bf_val,
                "neff_ranked_val": nr_val, "regret_ranked": reg_r, "verdict_ranked": verd_r,
                "neff_marginal_val": nm_val, "regret_marginal": reg_m, "verdict_marginal": verd_m,
            })

    emit()
    emit(f"  neff_ranked:   {'PASS' if not s2_fail_neff_r else 'FAIL'} — {len(s2_fail_neff_r)} cells")
    emit(f"  neff_marginal: {'PASS' if not s2_fail_neff_m else 'FAIL'} — {len(s2_fail_neff_m)} cells")
    if s2_fail_neff_m:
        for kv, ti, r in s2_fail_neff_m:
            emit(f"    FAIL: kv={kv} GiB, ti={ti}s, regret={r:+.3f}")
    out["s2"] = {"table": s2_table, "neff_ranked_fails": s2_fail_neff_r,
                 "neff_marginal_fails": s2_fail_neff_m}

    # ── 2. Diagnosis check ────────────────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("2. DIAGNOSIS CHECK — admitted robots' context_L at ti=5s")
    emit("   Prediction: neff_ranked admits many below-threshold robots;")
    emit(f"   neff_marginal admits few. Device threshold L ≈ {DEVICE_TTFT_1000MS_THRESHOLD} tokens.")
    emit()
    emit("   (epoch 0 only; mean over 3 seeds)")
    emit()

    diag_out = {}
    for kv in [4.5, 9.0, 36.0]:
        emit(f"  kv={kv} GiB, ti=5s:")
        emit(f"  {'policy':>14s}  {'n_admitted':>10s}  {'n_high_MB':>9s}  "
             f"{'n_low_MB':>8s}  {'mean_L_admitted':>15s}  {'median_L_admitted':>17s}")

        cell_diag = {}
        for policy in ("always_full", "neff_ranked", "neff_marginal", "oracle"):
            recs = [d for d in diag_records
                    if (d["policy"] == policy and d["kv_cap_gib"] == kv and d["ti_s"] == 5)]
            if not recs:
                emit(f"  {policy:>14s}  (no data)")
                continue

            n_high = [r["marginal_benefit"] for r in recs]
            n_low  = [1 - r["marginal_benefit"] for r in recs]
            Ls     = [r["context_L"] for r in recs]

            # Average counts over seeds (each seed contributes the admitted list once)
            seeds_seen = set()
            per_seed_high = {}
            per_seed_low  = {}
            per_seed_n    = {}
            per_seed_L    = {}
            for r in recs:
                s = r["seed"]
                if s not in per_seed_high:
                    per_seed_high[s] = 0
                    per_seed_low[s]  = 0
                    per_seed_n[s]    = 0
                    per_seed_L[s]    = []
                per_seed_high[s] += r["marginal_benefit"]
                per_seed_low[s]  += (1 - r["marginal_benefit"])
                per_seed_n[s]    += 1
                per_seed_L[s].append(r["context_L"])

            seeds = list(per_seed_n)
            mean_n    = statistics.mean(per_seed_n[s]    for s in seeds)
            mean_high = statistics.mean(per_seed_high[s] for s in seeds)
            mean_low  = statistics.mean(per_seed_low[s]  for s in seeds)
            all_L     = [x for s in seeds for x in per_seed_L[s]]
            mean_L    = statistics.mean(all_L)   if all_L else 0
            median_L  = statistics.median(all_L) if all_L else 0

            emit(f"  {policy:>14s}  {mean_n:>10.1f}  {mean_high:>9.1f}  "
                 f"{mean_low:>8.1f}  {mean_L:>15.0f}  {median_L:>17.0f}")

            cell_diag[policy] = {
                "mean_n_admitted": mean_n, "mean_n_high_mb": mean_high,
                "mean_n_low_mb": mean_low, "mean_L": mean_L, "median_L": median_L,
            }

        emit()

        # Verdict: check if neff_ranked admits more low-MB than neff_marginal
        if ("neff_ranked" in cell_diag and "neff_marginal" in cell_diag):
            nr_low = cell_diag["neff_ranked"].get("mean_n_low_mb", 0)
            nm_low = cell_diag["neff_marginal"].get("mean_n_low_mb", 0)
            if nr_low > nm_low:
                emit(f"  DIAGNOSIS CONFIRMED at kv={kv} GiB: neff_ranked admits "
                     f"{nr_low:.1f} low-MB robots vs neff_marginal {nm_low:.1f}")
            else:
                emit(f"  DIAGNOSIS NOT CONFIRMED at kv={kv} GiB: neff_ranked {nr_low:.1f} "
                     f"low-MB, neff_marginal {nm_low:.1f} — re-diagnose")
        emit()
        diag_out[f"kv_{kv}"] = cell_diag

    out["diagnosis"] = diag_out

    # ── 3. S3 — neff_marginal vs footprint_ranked at ti=5s ───────────────────
    emit("─" * 60)
    emit("3. S3 — neff_marginal vs footprint_ranked at ti=5s")
    emit("   (E36f reported neff_ranked gap = −0.007 at kv=9GiB; prediction: clearly positive with fix)")
    emit()
    emit(f"  {'kv':>6s}  {'neff_m':>7s}  {'fp':>7s}  {'gap':>7s}  verdict")
    s3_table = []
    s3_pass  = True
    for kv in KV_CAPS_GIB:
        nm_val = _agg(results, "neff_marginal",  kv, 5)
        fp_val = _agg(results, "footprint_ranked", kv, 5)
        if nm_val is None or fp_val is None:
            continue
        gap     = nm_val - fp_val
        verdict = "PASS" if gap > -0.01 else "FAIL"
        if verdict == "FAIL":
            s3_pass = False
        emit(f"  {kv:>6.1f}  {nm_val:>7.3f}  {fp_val:>7.3f}  {gap:>+7.3f}  {verdict}")
        s3_table.append({"kv": kv, "neff_marginal": nm_val, "fp": fp_val, "gap": gap})
    emit(f"  S3: {'PASS' if s3_pass else 'FAIL'}")
    out["s3"] = {"table": s3_table, "pass": s3_pass}

    # ── 4. Distinguishability ─────────────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("4. DISTINGUISHABILITY — neff_marginal vs every fixed policy by >1pp")
    emit()
    emit(f"  {'kv':>6s}  {'ti':>4s}  {'neff_m':>7s}  {'af':>7s}  {'aw':>7s}  "
         f"{'d_from_af':>9s}  {'d_from_aw':>9s}  both?")
    dist_table = []
    n_out_dist = 0
    total_cells = 0
    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            nm_val = _agg(results, "neff_marginal", kv, ti)
            af_val = _agg(results, "always_full",   kv, ti)
            aw_val = _agg(results, "always_window",  kv, ti)
            if any(v is None for v in [nm_val, af_val, aw_val]):
                continue
            total_cells += 1
            d_af = abs(nm_val - af_val)
            d_aw = abs(nm_val - aw_val)
            both = (d_af > 0.01) and (d_aw > 0.01)
            if both:
                n_out_dist += 1
            emit(f"  {kv:>6.1f}  {ti:>4d}  {nm_val:>7.3f}  {af_val:>7.3f}  "
                 f"{aw_val:>7.3f}  {d_af:>9.3f}  {d_aw:>9.3f}  {'YES' if both else 'no'}")
            dist_table.append({
                "kv": kv, "ti": ti, "neff_marginal": nm_val,
                "always_full": af_val, "always_window": aw_val,
                "d_from_af": d_af, "d_from_aw": d_aw, "both_distinguishable": both,
            })
    emit(f"  neff_marginal outcome-distinguishable from every fixed policy: "
         f"{n_out_dist}/{total_cells} cells")
    emit()
    emit("  Context: E36f found neff_ranked 11/16 cells outcome-distinguishable.")
    out["distinguishability"] = {"table": dist_table, "n_distinguishable": n_out_dist,
                                  "total_cells": total_cells}

    # ── 5. Oracle comparison ──────────────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("5. ORACLE COMPARISON — does any policy beat oracle?")
    emit("   Oracle definition: fidelity = argmax N_eff (same as neff_marginal/neff_ranked);")
    emit("   admission = marginal_benefit DESC, then KV footprint ASC.")
    emit("   For full-only fleets: oracle ≡ neff_marginal (N_eff DESC = KV ASC for full).")
    emit("   Divergence expected at ti≥15s where some robots switch to win10 (fixed KV).")
    emit()
    emit(f"  {'kv':>6s}  {'ti':>4s}  {'oracle':>6s}  {'neff_m':>6s}  {'af':>6s}  "
         f"{'aw':>6s}  {'oracle_beaten?':>14s}  {'by_whom':>12s}")
    oracle_beaten_cells = []
    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            or_val = _agg(results, "oracle",        kv, ti)
            nm_val = _agg(results, "neff_marginal", kv, ti)
            af_val = _agg(results, "always_full",   kv, ti)
            aw_val = _agg(results, "always_window",  kv, ti)
            if any(v is None for v in [or_val, nm_val, af_val, aw_val]):
                continue
            beaten_by = []
            if nm_val > or_val + 0.001: beaten_by.append(f"neff_m (+{nm_val-or_val:.3f})")
            if af_val > or_val + 0.001: beaten_by.append(f"af (+{af_val-or_val:.3f})")
            if aw_val > or_val + 0.001: beaten_by.append(f"aw (+{aw_val-or_val:.3f})")
            beaten = len(beaten_by) > 0
            if beaten:
                oracle_beaten_cells.append((kv, ti, beaten_by))
            emit(f"  {kv:>6.1f}  {ti:>4d}  {or_val:>6.3f}  {nm_val:>6.3f}  "
                 f"{af_val:>6.3f}  {aw_val:>6.3f}  "
                 f"  {'YES' if beaten else 'no':>14s}  {', '.join(beaten_by) if beaten_by else '—':>12s}")
    emit()
    if oracle_beaten_cells:
        emit("  NOTE: oracle beaten in some cells. Two explanations:")
        emit("  (a) Oracle is not a strict upper bound if always_full occasionally packs")
        emit("      slightly more robots by coincidence of ID order.")
        emit("  (b) Implementation gap: oracle sorts by KV ASC within high-MB group,")
        emit("      but always_full sorts by ID which may happen to align with KV ASC.")
        emit("  This is flagged as an artifact; oracle is a practical upper bound, not")
        emit("  the globally optimal solution to the joint KV+accel knapsack.")
    else:
        emit("  No policy beats oracle in any cell. Oracle is a valid upper bound.")
    out["oracle"] = {"beaten_cells": oracle_beaten_cells}

    # ── Summary ───────────────────────────────────────────────────────────────
    emit()
    emit("=" * 72)
    emit("SUMMARY")
    emit(f"  S2 neff_marginal: {'PASS' if not s2_fail_neff_m else f'FAIL ({len(s2_fail_neff_m)} cells)'}")
    emit(f"  S2 neff_ranked:   {'PASS' if not s2_fail_neff_r else f'FAIL ({len(s2_fail_neff_r)} cells)'}")
    emit(f"  S3 neff_marginal: {'PASS' if s3_pass else 'FAIL'}")
    emit(f"  Distinguishable:  {n_out_dist}/{total_cells} cells by >1pp")
    emit(f"  Oracle beaten:    {len(oracle_beaten_cells)} cells")
    emit("=" * 72)

    # Save
    out_path = OUT_DIR / "e36g_analysis.json"
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[saved] {out_path}")

    log_path = OUT_DIR / "e36g_analysis_log.txt"
    with open(log_path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"[saved] {log_path}")

    return out


def make_figures(results, diag_records, analysis):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[figure] matplotlib not available; skipping.")
        return

    # Figure 1: admitted-by-context-length at ti=5s
    # For each of the 3 diagnosis cells × 4 policies: histogram of admitted robots' context_L
    focus_policies   = ["always_full", "neff_ranked", "neff_marginal", "oracle"]
    focus_kv         = [4.5, 9.0, 36.0]
    colors           = {"always_full": "#2166ac", "neff_ranked": "#d6604d",
                        "neff_marginal": "#1a7a2e", "oracle": "#7b2d8b"}
    labels           = {"always_full": "always_full", "neff_ranked": "neff_ranked",
                        "neff_marginal": "neff_marginal", "oracle": "oracle"}

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=False)
    threshold = DEVICE_TTFT_1000MS_THRESHOLD
    bins = np.linspace(0, 25000, 26)

    for ax_idx, kv in enumerate(focus_kv):
        ax = axes[ax_idx]
        for policy in focus_policies:
            recs = [d for d in diag_records
                    if (d["policy"] == policy and d["kv_cap_gib"] == kv
                        and d["ti_s"] == 5)]
            if not recs:
                continue
            Ls = [d["context_L"] for d in recs]
            ax.hist(Ls, bins=bins, alpha=0.6, label=labels[policy],
                    color=colors[policy], density=True, histtype="stepfilled")
        ax.axvline(threshold, color="black", ls="--", lw=1.5, alpha=0.8,
                   label=f"device threshold (~{threshold//1000}k tok)")
        ax.set_title(f"kv={kv} GiB, ti=5s", fontsize=10, fontweight="bold")
        ax.set_xlabel("context_L of admitted robot (tokens)", fontsize=8)
        ax.set_ylabel("density" if ax_idx == 0 else "", fontsize=8)
        ax.set_xlim(0, 25000)
        ax.grid(True, alpha=0.2)
        if ax_idx == 0:
            ax.legend(fontsize=7, loc="upper right")

    plt.suptitle("E36g: Admitted robots' context_L per policy at ti=5s\n"
                 "Prediction: neff_ranked admits small-L (below threshold = zero marginal benefit);\n"
                 "neff_marginal concentrates admissions on large-L robots that fail on device.",
                 fontsize=8)
    plt.tight_layout()
    fig_path = FIG_DIR / "e36g_admitted_by_context_length.pdf"
    plt.savefig(fig_path, bbox_inches="tight")
    print(f"[figure] {fig_path}")
    plt.close()

    # Figure 2 (optional): S2 outcome comparison per cell
    fig2, axes2 = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    for ax_idx, kv in enumerate(KV_CAPS_GIB):
        ax = axes2[ax_idx // 2][ax_idx % 2]
        for policy, color, ls in [
                ("always_full",    "#2166ac", "--"),
                ("always_window",  "#d6604d", "--"),
                ("neff_ranked",    "#e08214", "-"),
                ("neff_marginal",  "#1a7a2e", "-"),
                ("oracle",         "#7b2d8b", ":"),
                ("maintenance_aware", "#888888", "-.")]:
            vals = [_agg(results, policy, kv, ti) or 0 for ti in TI_S]
            ax.plot(TI_S, vals, ls, label=policy, lw=2 if "marginal" in policy or policy=="oracle" else 1.5,
                    color=color, alpha=0.85)
        ax.set_title(f"kv={kv} GiB", fontsize=10, fontweight="bold")
        ax.set_ylabel("both_met", fontsize=8)
        ax.set_xticks(TI_S)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("Turn interval (s)", fontsize=8)
        ax.grid(True, alpha=0.2)
        if ax_idx == 0:
            ax.legend(fontsize=7)
    plt.suptitle("E36g: both_met by policy × turn interval\n"
                 "locomo, q=0.20, ttft=1000ms, n=50", fontsize=9)
    plt.tight_layout()
    fig2_path = FIG_DIR / "e36g_policy_comparison.pdf"
    plt.savefig(fig2_path, bbox_inches="tight")
    print(f"[figure] {fig2_path}")
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis-only", action="store_true")
    args = ap.parse_args()

    if args.analysis_only:
        sweep_path = OUT_DIR / "e36g_sweep.json"
        diag_path  = OUT_DIR / "e36g_diag_detail.json"
        if not sweep_path.exists():
            print("No sweep file found; run without --analysis-only first.")
            return
        with open(sweep_path) as fh:
            results = json.load(fh)
        with open(diag_path) as fh:
            diag_records = json.load(fh)
    else:
        print("E36g — running sweep...")
        results, diag_records = run_sweep()

    print("Running analysis...")
    analysis = run_analysis(results, diag_records)
    make_figures(results, diag_records, analysis)
    print("\nDone. Outputs in results/orchestration/e36g_marginal/ and figures/orchestration/")


if __name__ == "__main__":
    main()
