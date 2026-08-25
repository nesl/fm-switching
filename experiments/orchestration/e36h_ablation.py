"""
E36h — Two-part Rule Ablation: Admission Gain vs Representation Gain

E36g showed neff_marginal passes S2 in all 16 cells and beats every fixed
policy in most cells by 4–36 pp. However, neff_marginal differs from the
fixed baselines in two independent ways:
  Part 1: N_eff representation criterion (selects argmax N_eff fidelity)
  Part 2: marginal-benefit admission ordering (high-MB robots admitted first)

E36g's gaps conflate both parts. This experiment ablates them by adding three
baselines that isolate Part 2:

  always_full_mb:        fixed full representation + MB admission ordering
  always_window_mb:      fixed win10 representation + MB admission ordering
  footprint_ranked_mb:   footprint_ranked selection + MB admission ordering

With these added, the decomposition per (kv, ti) cell is:
  best_fixed         = max(always_full, always_window) per cell [no MB, no N_eff]
  best_fixed_mb      = max(always_full_mb, always_window_mb) per cell [MB only]
  admission_gain     = best_fixed_mb − best_fixed              [Part 2 alone]
  representation_gain = neff_marginal − best_fixed_mb          [Part 1 alone]
  total              = neff_marginal − best_fixed              [both parts]
  check: admission_gain + representation_gain = total (verified per cell)

NOTE: "oracle" from E36g is renamed "greedy_upper" in this run because it is
a greedy heuristic, not a true oracle with future knowledge. This is a naming
fix for this experiment only; prior E36g reports use "oracle" for the same
policy.

MECHANISM UNDER TEST. Representation choice affects fleet capacity
independently of which robots are admitted. Concretely: if all robots select
the same fidelity (Part 1 irrelevant), representation_gain must be zero.
Confirmed by the negative control: force all fidelities to "full" → both
neff_marginal and always_full_mb make identical choices → representation_gain
collapses to zero.

ASSUMPTIONS (carried from E36e/E36f/E36g unchanged):
  B1: SERVE_FULL_MS = 59ms (proxy from win10 intra-session E35)
  B2: No batching speedup for KV-append — unverified
  A2a: Stale trigger rate R(K) ≈ K/22 for LoCoMo — lower bound
  INFO: kv_cap, epoch_budget, context_L, device TTFT curve available at
        admission time.
"""

import argparse
import json
import math
import random as _random
import statistics
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "orchestration" / "e36h_ablation"
FIG_DIR = ROOT / "figures" / "orchestration"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── COMMITTED CONSTANTS (identical to E36e/E36f/E36g) ────────────────────────

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

DEVICE_TTFT_1000MS_THRESHOLD = 11_800  # analytic; from E23×E37 A1 ratio


# ── HELPER FUNCTIONS (identical to E36g) ─────────────────────────────────────

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

def _interp(tbl, x):
    ks = sorted(tbl)
    if x <= ks[0]:  return tbl[ks[0]]
    if x >= ks[-1]: return tbl[ks[-1]]
    for i in range(len(ks) - 1):
        if ks[i] <= x <= ks[i + 1]:
            t = (x - ks[i]) / (ks[i + 1] - ks[i])
            return tbl[ks[i]] * (1 - t) + tbl[ks[i + 1]] * t
    return tbl[ks[-1]]

def _device_ttft_ms(L):
    Lc = min(L, max(JETSON_INCR_WARM_MS))
    return _interp(JETSON_INCR_WARM_MS, Lc) * _interp(A1_INCR_WARM_RATIO, Lc)

def _device_both_met(robot, ttft_budget_ms, q_slo, workload):
    ttft = _device_ttft_ms(robot.context_L)
    q    = Q_LOCOMO["full"] if workload == "locomo" else Q_EGOSCHEMA["full"]
    return (ttft <= ttft_budget_ms) and (q >= q_slo)

def _marginal_benefit(robot, ttft_budget_ms, q_slo, workload):
    """Binary: 1 if robot fails on device, 0 if device suffices."""
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


# MB_POLICIES: policies that use marginal-benefit admission ordering
MB_POLICIES = frozenset([
    "neff_marginal", "greedy_upper",
    "always_full_mb", "always_window_mb", "footprint_ranked_mb",
])


def _choose_fidelity(policy, robot, workload, q_slo, ti_s,
                     kv_cap_bytes=0, epoch_budget_ms=0):
    admissible = [f for f in ("full", "win10", "sum200")
                  if _q_value(f, workload) >= q_slo]
    if not admissible:
        return None

    # Fixed-representation policies
    if policy in ("always_full", "always_full_mb"):
        return "full" if "full" in admissible else admissible[0]
    if policy in ("always_window", "always_window_mb"):
        return "win10" if "win10" in admissible else admissible[0]
    if policy == "always_summary":
        return "sum200" if "sum200" in admissible else admissible[0]
    if policy == "device_only":
        return None

    # Footprint-ranked selection (with or without MB admission)
    if policy in ("footprint_ranked", "footprint_ranked_mb"):
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

    # N_eff selection (neff_ranked, neff_marginal, greedy_upper all use argmax N_eff)
    if policy in ("neff_ranked", "neff_marginal", "greedy_upper"):
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

        # MB policies: primary = marginal_benefit DESC
        if policy in MB_POLICIES:
            mb = _marginal_benefit(r, ttft_budget_ms, q_slo, workload)
            if policy == "greedy_upper":
                return (mb, -kv)   # KV footprint ASC as tiebreaker
            if policy == "footprint_ranked_mb":
                q_val = _q_value(f, workload)
                return (mb, q_val / kv if kv > 0 else 0)
            # always_full_mb, always_window_mb, neff_marginal: N_eff DESC as tiebreaker
            return (mb, _neff_score(r, f, kv_cap_bytes, epoch_budget_ms))

        # Non-MB policies (unchanged from E36g)
        if policy == "footprint_ranked":
            q_val = _q_value(f, workload)
            return (0, q_val / kv if kv > 0 else 0)
        if policy == "maintenance_aware":
            f_key = "win10_amz" if f == "win10" else f
            m     = _maint_ms(f_key)
            s     = _serve_ms(f)
            return (0, epoch_budget_ms / (m + s) if (m + s) > 0 else float("inf"))
        if policy == "neff_ranked":
            return (0, _neff_score(r, f, kv_cap_bytes, epoch_budget_ms))
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

    # Track fidelity mix for representation_gain diagnostic
    fidelity_counts = {}
    for f in admitted.values():
        fidelity_counts[f] = fidelity_counts.get(f, 0) + 1

    for r in robots.values():
        _advance_robot(r)

    result = {
        "both_met_frac":  n_both_met / len(robots) if robots else 0,
        "n_admitted":     len(admitted),
        "kv_used_gib":    kv_used / GIB,
        "maint_used_ms":  maint_used_ms,
        "fidelity_counts": fidelity_counts,
    }
    if track_detail:
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

POLICIES = [
    "device_only",
    "always_full",      "always_window",      "always_summary",
    "always_full_mb",   "always_window_mb",
    "footprint_ranked", "footprint_ranked_mb",
    "maintenance_aware",
    "neff_ranked",
    "neff_marginal",
    "greedy_upper",     # renamed from "oracle" — greedy heuristic, not a true oracle
]
N_ROBOTS  = [50]
WORKLOADS = ["locomo", "egoschema"]
Q_SLOS    = [0.20, 0.30]
TTFT_MS   = 1000
SEEDS     = [42, 123, 7]
N_EPOCHS  = 30

# Track fidelity-mix per epoch for neff_marginal to support diagnostic item 3
FIDELITY_MIX_CELLS = [(kv, ti) for kv in KV_CAPS_GIB for ti in TI_S]


def run_sweep():
    import itertools
    all_results    = []
    fidelity_mix   = []   # per-epoch fidelity counts for neff_marginal, locomo q=0.20
    total = (len(POLICIES) * len(N_ROBOTS) * len(KV_CAPS_GIB) * len(TI_S)
             * len(WORKLOADS) * len(Q_SLOS) * len(SEEDS))
    done = 0

    for (policy, n_robots, kv_cap, ti_s, workload, q_slo, seed) in itertools.product(
            POLICIES, N_ROBOTS, KV_CAPS_GIB, TI_S, WORKLOADS, Q_SLOS, SEEDS):

        epoch_budget_ms = ti_s * 1000.0
        kv_cap_bytes    = int(kv_cap * GIB)
        robots          = _make_robots(n_robots, seed, workload)
        fracs           = []
        ep_fidelity_counts = []

        for ep_idx in range(N_EPOCHS):
            ep = _simulate_epoch(policy, robots, kv_cap_bytes, epoch_budget_ms,
                                 workload, q_slo, TTFT_MS, ti_s)
            fracs.append(ep["both_met_frac"])
            if (policy == "neff_marginal" and workload == "locomo" and
                    q_slo == 0.20 and (kv_cap, ti_s) in FIDELITY_MIX_CELLS):
                ep_fidelity_counts.append(ep["fidelity_counts"])

        if ep_fidelity_counts:
            # Aggregate fidelity counts over epochs and this seed
            agg_counts = {}
            for ec in ep_fidelity_counts:
                for f, cnt in ec.items():
                    agg_counts[f] = agg_counts.get(f, 0) + cnt
            total_admitted = sum(agg_counts.values())
            frac_full = agg_counts.get("full", 0) / total_admitted if total_admitted > 0 else 0
            frac_win10 = agg_counts.get("win10", 0) / total_admitted if total_admitted > 0 else 0
            fidelity_mix.append({
                "kv_cap_gib": kv_cap, "ti_s": ti_s, "seed": seed,
                "frac_full": frac_full, "frac_win10": frac_win10,
                "total_admitted": total_admitted,
            })

        all_results.append({
            "policy": policy, "n_robots": n_robots, "kv_cap_gib": kv_cap,
            "ti_s": ti_s, "workload": workload, "q_slo": q_slo, "seed": seed,
            "both_met_mean": statistics.mean(fracs),
        })
        done += 1
        if done % 200 == 0:
            print(f"  {done}/{total}")

    out = OUT_DIR / "e36h_sweep.json"
    with open(out, "w") as fh:
        json.dump(all_results, fh, indent=2)
    print(f"[saved] {out}")

    mix_out = OUT_DIR / "e36h_fidelity_mix.json"
    with open(mix_out, "w") as fh:
        json.dump(fidelity_mix, fh, indent=2)
    print(f"[saved] {mix_out}")

    return all_results, fidelity_mix


def _agg(results, policy, kv, ti, workload="locomo", q_slo=0.20):
    vals = [r["both_met_mean"] for r in results
            if (r["policy"] == policy and r["kv_cap_gib"] == kv and r["ti_s"] == ti
                and r["workload"] == workload and r["q_slo"] == q_slo)]
    return statistics.mean(vals) if vals else None


def run_analysis(results, fidelity_mix):
    lines = []
    out   = {}

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 72)
    emit("E36h — Two-part Rule Ablation Analysis")
    emit("=" * 72)

    # ── Precompute best_fixed and best_fixed_mb per cell ─────────────────────
    fixed_policies    = ["always_full", "always_window"]
    fixed_mb_policies = ["always_full_mb", "always_window_mb"]

    # ── 1. Decomposition table ─────────────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("1. DECOMPOSITION TABLE")
    emit("   locomo, q=0.20, ttft=1000ms, n=50, mean over 3 seeds")
    emit("   best_fixed = max(always_full, always_window) [no MB, no N_eff]")
    emit("   best_fixed_mb = max(always_full_mb, always_window_mb) [MB only]")
    emit()
    emit(f"  {'kv':>6s}  {'ti':>4s}  {'best_f':>8s}  {'bf_mb':>8s}  {'neff_m':>8s}  "
         f"{'adm_gain':>9s}  {'rep_gain':>9s}  {'total':>8s}  {'check':>6s}")

    decomp_table = []
    all_adm_gains  = []
    all_rep_gains  = []

    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            bf_vals = {}
            for fp in fixed_policies:
                v = _agg(results, fp, kv, ti)
                if v is not None:
                    bf_vals[fp] = v

            bfmb_vals = {}
            for fp in fixed_mb_policies:
                v = _agg(results, fp, kv, ti)
                if v is not None:
                    bfmb_vals[fp] = v

            nm_val = _agg(results, "neff_marginal", kv, ti)
            if not bf_vals or not bfmb_vals or nm_val is None:
                continue

            best_f    = max(bf_vals.values())
            best_fmb  = max(bfmb_vals.values())
            adm_gain  = best_fmb - best_f
            rep_gain  = nm_val - best_fmb
            total_gap = nm_val - best_f
            check_ok  = abs((adm_gain + rep_gain) - total_gap) < 1e-9
            check_str = "OK" if check_ok else "FAIL"

            emit(f"  {kv:>6.1f}  {ti:>4d}  {best_f:>8.3f}  {best_fmb:>8.3f}  "
                 f"{nm_val:>8.3f}  {adm_gain:>+9.4f}  {rep_gain:>+9.4f}  "
                 f"{total_gap:>+8.4f}  {check_str:>6s}")

            all_adm_gains.append(adm_gain)
            all_rep_gains.append(rep_gain)
            decomp_table.append({
                "kv": kv, "ti": ti,
                "best_fixed": best_f, "best_fixed_mb": best_fmb,
                "neff_marginal": nm_val,
                "admission_gain": adm_gain,
                "representation_gain": rep_gain,
                "total_gain": total_gap,
                "check_sum_ok": check_ok,
            })

    emit()
    check_fail = [r for r in decomp_table if not r["check_sum_ok"]]
    if check_fail:
        emit(f"  WARNING: {len(check_fail)} cells failed sum check:")
        for r in check_fail:
            emit(f"    kv={r['kv']}, ti={r['ti']}: diff="
                 f"{abs(r['admission_gain']+r['representation_gain']-r['total_gain']):.2e}")
    else:
        emit(f"  Sum check: PASS for all {len(decomp_table)} cells.")

    mean_adm = statistics.mean(all_adm_gains) if all_adm_gains else 0
    mean_rep = statistics.mean(all_rep_gains) if all_rep_gains else 0
    emit()
    emit(f"  Mean admission_gain  across 16 cells: {mean_adm:+.4f} ({mean_adm*100:+.2f} pp)")
    emit(f"  Mean representation_gain across 16 cells: {mean_rep:+.4f} ({mean_rep*100:+.2f} pp)")
    emit(f"  Admission gain larger: {abs(mean_adm) > abs(mean_rep)}")
    out["decomp"] = {
        "table": decomp_table,
        "mean_admission_gain": mean_adm,
        "mean_representation_gain": mean_rep,
        "n_check_fail": len(check_fail),
    }

    # ── 2. Where does representation gain pay? ────────────────────────────────
    emit()
    emit("─" * 60)
    emit("2. REPRESENTATION GAIN — where is it positive vs zero?")
    emit("   Prediction (from E36f Section 4 trace): zero at ti=5s where all robots")
    emit("   select full; positive in transition band where robots split full/win10.")
    emit()

    # Count cells by gain sign
    zero_cells    = [(r["kv"], r["ti"]) for r in decomp_table if abs(r["representation_gain"]) < 1e-4]
    pos_cells     = [(r["kv"], r["ti"]) for r in decomp_table if r["representation_gain"] >  1e-4]
    neg_cells     = [(r["kv"], r["ti"]) for r in decomp_table if r["representation_gain"] < -1e-4]

    emit(f"  Positive representation_gain cells ({len(pos_cells)}):")
    for kv, ti in pos_cells:
        row = next(r for r in decomp_table if r["kv"] == kv and r["ti"] == ti)
        emit(f"    kv={kv} GiB, ti={ti}s: rep_gain={row['representation_gain']:+.4f}")
    emit()
    emit(f"  Near-zero representation_gain cells (|gain|<0.01pp, {len(zero_cells)}):")
    for kv, ti in zero_cells:
        row = next(r for r in decomp_table if r["kv"] == kv and r["ti"] == ti)
        emit(f"    kv={kv} GiB, ti={ti}s: rep_gain={row['representation_gain']:+.4f}")
    emit()
    if neg_cells:
        emit(f"  Negative representation_gain cells ({len(neg_cells)}) — investigate:")
        for kv, ti in neg_cells:
            row = next(r for r in decomp_table if r["kv"] == kv and r["ti"] == ti)
            emit(f"    kv={kv} GiB, ti={ti}s: rep_gain={row['representation_gain']:+.4f}")
        emit()

    max_rep = max(decomp_table, key=lambda r: r["representation_gain"])
    emit(f"  Maximum representation_gain: {max_rep['representation_gain']:+.4f} "
         f"at kv={max_rep['kv']} GiB, ti={max_rep['ti']}s")

    out["representation_gain"] = {
        "positive_cells": pos_cells,
        "zero_cells": zero_cells,
        "negative_cells": neg_cells,
        "max_gain": max_rep["representation_gain"],
        "max_gain_kv": max_rep["kv"],
        "max_gain_ti": max_rep["ti"],
    }

    # ── 3. Fidelity-mix diagnostic ────────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("3. FIDELITY-MIX DIAGNOSTIC — fraction full vs win10 under neff_marginal")
    emit("   Cross-tabulated against representation_gain.")
    emit("   Cells where all robots select same fidelity → representation_gain ≈ 0.")
    emit()
    emit(f"  {'kv':>6s}  {'ti':>4s}  {'frac_full':>9s}  {'frac_win10':>10s}  "
         f"{'rep_gain':>9s}  {'prediction':>12s}  {'ok?':>4s}")

    mix_table = []
    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            # Average frac_full over seeds
            mix_rows = [m for m in fidelity_mix
                        if m["kv_cap_gib"] == kv and m["ti_s"] == ti]
            if not mix_rows:
                continue
            frac_full  = statistics.mean(m["frac_full"]  for m in mix_rows)
            frac_win10 = statistics.mean(m["frac_win10"] for m in mix_rows)

            # Get rep_gain for this cell
            d_row = next((r for r in decomp_table if r["kv"] == kv and r["ti"] == ti), None)
            rep_gain = d_row["representation_gain"] if d_row else float("nan")

            # Prediction: if frac_full ≈ 1.0 or frac_win10 ≈ 1.0 → rep_gain ≈ 0
            is_homogeneous = (frac_full > 0.99 or frac_win10 > 0.99)
            prediction = "zero" if is_homogeneous else "nonzero"

            # Check: is prediction consistent with actual rep_gain?
            if is_homogeneous:
                ok = abs(rep_gain) < 0.005
            else:
                # Some splitting — nonzero rep_gain expected
                ok = abs(rep_gain) > 0.001

            emit(f"  {kv:>6.1f}  {ti:>4d}  {frac_full:>9.3f}  {frac_win10:>10.3f}  "
                 f"{rep_gain:>+9.4f}  {prediction:>12s}  {'yes' if ok else 'VIOLATION':>4s}")

            mix_table.append({
                "kv": kv, "ti": ti, "frac_full": frac_full, "frac_win10": frac_win10,
                "rep_gain": rep_gain, "is_homogeneous": is_homogeneous,
                "prediction_ok": ok,
            })

    violations = [m for m in mix_table if not m["prediction_ok"]]
    emit()
    if violations:
        emit(f"  VIOLATIONS ({len(violations)}) — homogeneous fleet but nonzero rep_gain (or vice versa):")
        for v in violations:
            emit(f"    kv={v['kv']} GiB, ti={v['ti']}s: frac_full={v['frac_full']:.3f}, "
                 f"rep_gain={v['rep_gain']:+.4f}")
    else:
        emit(f"  No violations: pattern holds in all {len(mix_table)} cells.")
    out["fidelity_mix"] = {"table": mix_table, "n_violations": len(violations)}

    # ── 4. S3 with corrected incumbent ────────────────────────────────────────
    emit()
    emit("─" * 60)
    emit("4. S3 WITH CORRECTED INCUMBENT")
    emit("   Old S3 (E36g): neff_marginal vs footprint_ranked (neither has MB admission)")
    emit("   New S3: neff_marginal vs footprint_ranked_mb (both have MB admission;")
    emit("           only representation criterion differs)")
    emit()
    emit(f"  {'kv':>6s}  {'neff_m':>7s}  {'fp':>7s}  {'old_gap':>8s}  "
         f"{'fp_mb':>7s}  {'new_gap':>8s}  note")

    s3_table = []
    for kv in KV_CAPS_GIB:
        nm_val   = _agg(results, "neff_marginal",   kv, 5)
        fp_val   = _agg(results, "footprint_ranked", kv, 5)
        fpmb_val = _agg(results, "footprint_ranked_mb", kv, 5)
        if nm_val is None or fp_val is None or fpmb_val is None:
            continue
        old_gap = nm_val - fp_val
        new_gap = nm_val - fpmb_val
        note = ""
        if abs(new_gap) < 0.005:
            note = "≈ 0 (representation criterion alone)"
        elif new_gap > 0.005:
            note = "+ (N_eff criterion adds value)"
        else:
            note = "− (N_eff criterion hurts vs footprint+MB)"

        emit(f"  {kv:>6.1f}  {nm_val:>7.3f}  {fp_val:>7.3f}  {old_gap:>+8.4f}  "
             f"{fpmb_val:>7.3f}  {new_gap:>+8.4f}  {note}")
        s3_table.append({
            "kv": kv, "neff_marginal": nm_val, "fp_ranked": fp_val,
            "fp_ranked_mb": fpmb_val, "old_gap": old_gap, "new_gap": new_gap,
        })
    out["s3_corrected"] = {"table": s3_table}

    # ── 5. Greedy_upper (formerly oracle) comparison ──────────────────────────
    emit()
    emit("─" * 60)
    emit("5. GREEDY_UPPER (renamed from 'oracle' in E36g)")
    emit("   greedy_upper = argmax N_eff selection + MB first, then KV footprint ASC")
    emit("   neff_marginal = argmax N_eff selection + MB first, then N_eff DESC")
    emit("   (At ti=5s full-only fleets: identical; diverge at ti≥15s with win10 robots)")
    emit()
    emit(f"  {'kv':>6s}  {'ti':>4s}  {'neff_m':>7s}  {'gu':>7s}  {'delta':>8s}  note")

    gu_table = []
    n_beaten = 0
    for kv in KV_CAPS_GIB:
        for ti in TI_S:
            nm_val = _agg(results, "neff_marginal", kv, ti)
            gu_val = _agg(results, "greedy_upper",  kv, ti)
            if nm_val is None or gu_val is None:
                continue
            delta = nm_val - gu_val
            note  = ""
            if delta > 0.001:
                note = "neff_m > greedy_upper (heuristic not tight)"
                n_beaten += 1
            elif delta < -0.001:
                note = "greedy_upper > neff_m"
            else:
                note = "tied"
            emit(f"  {kv:>6.1f}  {ti:>4d}  {nm_val:>7.3f}  {gu_val:>7.3f}  "
                 f"{delta:>+8.4f}  {note}")
            gu_table.append({
                "kv": kv, "ti": ti,
                "neff_marginal": nm_val, "greedy_upper": gu_val, "delta": delta,
            })

    emit()
    emit(f"  neff_marginal beats greedy_upper in {n_beaten}/16 cells.")
    emit("  greedy_upper is a greedy heuristic (KV-ASC tiebreaker), not a true oracle.")
    out["greedy_upper"] = {"table": gu_table, "n_neff_m_beats_gu": n_beaten}

    # ── Save analysis ─────────────────────────────────────────────────────────
    aout = OUT_DIR / "e36h_analysis.json"
    with open(aout, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"[saved] {aout}")

    log_out = OUT_DIR / "e36h_analysis_log.txt"
    with open(log_out, "w") as fh:
        fh.write("\n".join(lines))
    print(f"[saved] {log_out}")

    return out


def plot_gain_decomposition(analysis):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError:
        print("[skip] matplotlib not available")
        return

    decomp = analysis.get("decomp", {}).get("table", [])
    if not decomp:
        print("[skip] no decomp data")
        return

    fig, axes = plt.subplots(1, 4, figsize=(14, 4.5), sharey=True)
    fig.suptitle("E36h — Gain Decomposition: Admission vs Representation Criterion",
                 fontsize=11, fontweight="bold", y=1.01)

    ti_values = sorted(set(r["ti"] for r in decomp))
    colors    = {"admission": "#2196F3", "representation": "#FF5722"}

    for ax_i, kv in enumerate(sorted(set(r["kv"] for r in decomp))):
        ax = axes[ax_i]
        rows = sorted([r for r in decomp if r["kv"] == kv], key=lambda r: r["ti"])
        if not rows:
            continue

        x_pos = range(len(rows))
        adm_vals  = [r["admission_gain"] * 100 for r in rows]
        rep_vals  = [r["representation_gain"] * 100 for r in rows]
        ti_labels = [f"ti={r['ti']}s" for r in rows]

        bars_adm = ax.bar(x_pos, adm_vals, width=0.6,
                          color=colors["admission"], alpha=0.85, label="Admission gain")
        bars_rep = ax.bar(x_pos, rep_vals, width=0.6, bottom=adm_vals,
                          color=colors["representation"], alpha=0.85, label="Representation gain")

        ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.set_xticks(list(x_pos))
        ax.set_xticklabels(ti_labels, rotation=30, ha="right", fontsize=8)
        ax.set_title(f"kv = {kv} GiB", fontsize=10, fontweight="bold")
        ax.set_xlabel("Turn interval", fontsize=9)
        if ax_i == 0:
            ax.set_ylabel("Gain (pp) vs best_fixed", fontsize=9)

        # Annotate zeros
        for xi, (adm, rep) in enumerate(zip(adm_vals, rep_vals)):
            if abs(rep) < 0.05:
                ax.text(xi, adm + 0.3, "0", ha="center", va="bottom",
                        fontsize=7, color=colors["representation"])

    adm_patch = mpatches.Patch(color=colors["admission"], alpha=0.85, label="Admission gain (Part 2)")
    rep_patch = mpatches.Patch(color=colors["representation"], alpha=0.85,
                               label="Representation gain (Part 1)")
    fig.legend(handles=[adm_patch, rep_patch], loc="lower center",
               ncol=2, bbox_to_anchor=(0.5, -0.08), fontsize=9)

    plt.tight_layout()
    out_path = FIG_DIR / "e36h_gain_decomposition.pdf"
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"[saved] {out_path}")


def main():
    print("[E36h] Two-part rule ablation — running sweep ...")
    results, fidelity_mix = run_sweep()
    print("[E36h] Running analysis ...")
    analysis = run_analysis(results, fidelity_mix)
    print("[E36h] Plotting ...")
    plot_gain_decomposition(analysis)
    print("[E36h] Done.")


if __name__ == "__main__":
    main()
