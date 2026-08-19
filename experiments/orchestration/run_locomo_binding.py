"""
run_locomo_binding.py — Orchestration-binding test for Context Inertia on LoCoMo.

v3 changes (this version):
  1. Composite h0 in JointInertia: evaluates [MIGRATE_TO_CLOUD, SET_FULL_CONTEXT]
     as a planned two-step sequence — policy can now discover cloud+full strategy.
  2. Planning gap is the PRIMARY metric: total_planning_gap_s (cumulative LLM-
     unavailable seconds) and reasoning_available_frac = 1 - gap/total_time.
  3. Two Q_slo levels:
       Q_slo=0.12 — feasible: {window-10, full}; starts edge/window-10
       Q_slo=0.20 — feasible: {full only}; starts cloud/full (full OOMs on edge)
  4. Inertia at 18822 tokens (beyond measured ceiling): reported as power-law-low
     and linear-high extrapolation bounds. Simulation runs with both for Q_slo=0.20.
     Clamped value (12.6 s) is labeled as an underestimate.
  5. Explicit fallback capability:
       JointInertia has_warm_window10_fallback=True → cloud failure uses 7180-tok
       re-prefill (warm window-10 KV maintained on edge); reflected in MPC and sim.
       Reactive policies → cloud failure uses full 18822-tok re-prefill (or bound).
  6. VLM cost confirmed in _print_vlm_confirmation().
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

_SIM = Path(__file__).resolve().parent.parent.parent / "simulator"
sys.path.insert(0, str(_SIM.parent / "experiments" / "lib"))
sys.path.insert(0, str(_SIM))

import cost_model
from cost_model import FP16
from markov_network import sample_trace
from orchestrator_sim import run_episode, STAY
from policies import ReactiveThreshold
from rq3_policies import InertiaBlindAdaptive, PlaceOnly, JointInertia

# ── Constants ──────────────────────────────────────────────────────────────────

Q_SLO_LOW        = 0.12   # feasible: window-10 (0.16), full (0.26)
Q_SLO_HIGH       = 0.20   # feasible: full only (0.26); window-10 below threshold
MEMORY_CAP_MB    = 13_900 # edge cap: window-10 (11773 MB) fits; full (13956 MB) OOM
N_CYCLES         = 60
N_SECONDS        = 720
VALIDATION_SEEDS = [0]
VALIDATION_MOBILITY = ["urban", "harsh"]
POLICY_NAMES = ["JointInertia", "ReactiveThreshold", "InertiaBlindAdaptive", "PlaceOnly"]

_REPO = Path(__file__).resolve().parent.parent.parent

# Penalty for infeasible representations (QUALITY_WEIGHT_S × (1 + 1000) ≈ 5005 s/cycle).
_INFEASIBLE_Q = -1000.0

# Warm window-10 fallback context depth for JointInertia.
_WIN10_FALLBACK_CTX = 7180

# ── Inertia extrapolation bounds ────────────────────────────────────────────────

def _compute_inertia_bounds(json_path, target_tok=18822):
    """Return (clamped_ms, powerlaw_ms, linear_ms) for target_tok.

    Fits power-law and linear models to the measured curve and extrapolates.
    clamped_ms = last measured value (current simulator default, underestimate).
    """
    raw = json.loads(Path(json_path).read_text())
    depths_raw = raw.get("depths", raw if isinstance(raw, list) else [])
    pairs = sorted(
        [(d.get("depth") or d.get("context_tokens"),
          d.get("prefill_ms_mean") or d.get("reprefill_ms") or d.get("prefill_ms"))
         for d in depths_raw
         if (d.get("depth") or d.get("context_tokens")) and
            (d.get("prefill_ms_mean") or d.get("reprefill_ms") or d.get("prefill_ms"))],
        key=lambda x: x[0]
    )
    if not pairs:
        return None, None, None

    # Power-law OLS on log-log: log(ms) = alpha*log(tok) + beta
    log_x = [math.log(t) for t, _ in pairs]
    log_y = [math.log(m) for _, m in pairs]
    n = len(log_x)
    mx, my = sum(log_x) / n, sum(log_y) / n
    num = sum((log_x[i] - mx) * (log_y[i] - my) for i in range(n))
    den = sum((log_x[i] - mx) ** 2 for i in range(n)) + 1e-12
    alpha = num / den
    beta  = my - alpha * mx
    powerlaw_ms = math.exp(alpha * math.log(target_tok) + beta)

    # Linear extrapolation from the last measured segment
    (t0, m0), (t1, m1) = pairs[-2], pairs[-1]
    slope = (m1 - m0) / (t1 - t0 + 1e-6)
    linear_ms = m1 + slope * (target_tok - t1)

    clamped_ms = pairs[-1][1]
    return clamped_ms, powerlaw_ms, linear_ms


_JETSON_JSON = _REPO / "results" / "inertia_smollm2_jetson.json"
_A6000_JSON  = _REPO / "results" / "inertia_smollm2_a6000.json"

_EDGE_CLAMPED_MS, _EDGE_POWERLAW_MS, _EDGE_LINEAR_MS = (
    _compute_inertia_bounds(_JETSON_JSON) if _JETSON_JSON.exists()
    else (12585.0, 25900.0, 30400.0)
)
_SERVER_CLAMPED_MS, _SERVER_POWERLAW_MS, _SERVER_LINEAR_MS = (
    _compute_inertia_bounds(_A6000_JSON) if _A6000_JSON.exists()
    else (469.0, 970.0, 1095.0)
)

# Inertia configs: (label, edge_override_ms, server_override_ms)
_INERTIA_CONFIGS = {
    "powerlaw": ("power-law low",  _EDGE_POWERLAW_MS, _SERVER_POWERLAW_MS),
    "linear":   ("linear high",    _EDGE_LINEAR_MS,   _SERVER_LINEAR_MS),
}

# ── Load quality and token tables ─────────────────────────────────────────────

def _load_quality_tokens(json_path):
    raw = json.loads(Path(json_path).read_text())
    sm  = raw["summary"]
    quality = {c: s["accuracy"]                       for c, s in sm.items()}
    tokens  = {c: int(round(s["mean_prompt_tokens"])) for c, s in sm.items()}
    tokens.pop("full",     None)
    tokens.pop("shuffled", None)
    return quality, tokens


LOCOMO_QUALITY, LOCOMO_TOKENS = _load_quality_tokens(
    _REPO / "results" / "frontier_locomo_qwen7b.json")


def _make_slo_quality(q_slo):
    return {k: (v if v >= q_slo else _INFEASIBLE_Q) for k, v in LOCOMO_QUALITY.items()}


def _mode_from_config(cfg):
    return cfg.split("/")[-1]


# ── SLO guard wrapper ─────────────────────────────────────────────────────────

_ACTION_TO_MODE = {
    "set_stateless":    "stateless",
    "set_window_3":     "window-3",
    "set_window_10":    "window-10",
    "set_full_context": "full",
    "set_summary_80":   "summary-80",
    "set_summary_200":  "summary-200",
}


class _SLOGuard:
    """Block policy actions that would switch to a representation below Q_slo.

    Reactive policies (ReactiveThreshold) may trigger SET_STATELESS via CTX_THRESH
    even when stateless quality is far below Q_slo. This wrapper intercepts such
    actions and returns STAY so the policy continues serving the current (feasible)
    representation. Placement actions (MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE) are never
    blocked.
    """
    def __init__(self, inner, actual_quality, q_slo):
        self.inner = inner
        self._aq   = actual_quality
        self._q_slo = q_slo
        self.name  = getattr(inner, "name", str(type(inner).__name__))

    def decide(self, state):
        action = self.inner.decide(state)
        mode_after = _ACTION_TO_MODE.get(action)
        if mode_after is not None and self._aq.get(mode_after, 0.0) < self._q_slo:
            return STAY
        return action


# ── Context manager: patch cost_model dicts in-place ─────────────────────────

class _WorkloadContext:
    """Patch cost_model.QUALITY and cost_model.EFFECTIVE_TOKENS in-place.

    All policy modules hold references to the SAME dict objects from import time.
    In-place mutation propagates to all importers without re-importing.
    """
    def __init__(self, quality, tokens):
        self._q   = quality
        self._tok = tokens

    def __enter__(self):
        self._orig_q   = dict(cost_model.QUALITY)
        self._orig_tok = dict(cost_model.EFFECTIVE_TOKENS)
        cost_model.QUALITY.update(self._q)
        cost_model.EFFECTIVE_TOKENS.update(self._tok)
        return self

    def __exit__(self, *_):
        cost_model.QUALITY.clear()
        cost_model.QUALITY.update(self._orig_q)
        cost_model.EFFECTIVE_TOKENS.clear()
        cost_model.EFFECTIVE_TOKENS.update(self._orig_tok)


# ── Workload generator ────────────────────────────────────────────────────────

def _make_workload(seed, n):
    rng   = random.Random(seed + 9999)
    mu    = math.log(FP16["vlm_mean_s"])
    sigma = (math.log(FP16["vlm_max_s"]) - math.log(FP16["vlm_min_s"])) / 3.0
    return [
        {"cycle": i,
         "vlm_latency_s": max(FP16["vlm_min_s"],
                               min(FP16["vlm_max_s"],
                                   math.exp(rng.gauss(mu, sigma))))}
        for i in range(n)
    ]


# ── Policy factory ─────────────────────────────────────────────────────────────

def _policy_factory(name, quality_slo, actual_quality, q_slo_val, oom_fallback="window-10"):
    """Build policy; wrap reactive policies with SLO guard so they don't select
    infeasible representations when the feasible set narrows (e.g. Q_slo=0.20)."""
    if name == "JointInertia":
        return JointInertia(quality=quality_slo, oom_fallback=oom_fallback)
    if name == "ReactiveThreshold":
        inner = ReactiveThreshold()
        return _SLOGuard(inner, actual_quality, q_slo_val)
    if name == "InertiaBlindAdaptive":
        return InertiaBlindAdaptive()
    if name == "PlaceOnly":
        return PlaceOnly()
    raise ValueError(f"unknown policy: {name}")


# ── Single run ─────────────────────────────────────────────────────────────────

def _run_one(policy_name, mobility, seed, q_slo_val, inertia_key):
    actual_quality = LOCOMO_QUALITY
    quality_slo    = _make_slo_quality(q_slo_val)

    net = sample_trace(mobility, n_seconds=N_SECONDS, seed=seed)
    wl  = _make_workload(seed, N_CYCLES)
    pol = _policy_factory(policy_name, quality_slo, actual_quality, q_slo_val,
                          oom_fallback="window-10")

    # Inertia override for context depths beyond the measured ceiling.
    _, edge_ms, server_ms = _INERTIA_CONFIGS[inertia_key]
    cost_model._INERTIA_EXTRAPOLATED.clear()
    if edge_ms is not None and edge_ms > 0:
        cost_model._INERTIA_EXTRAPOLATED[("edge",   8193)] = edge_ms
    if server_ms is not None and server_ms > 0:
        cost_model._INERTIA_EXTRAPOLATED[("server", 8193)] = server_ms

    # Episode setup differs by Q_slo level:
    #   Q_slo=0.12 — start edge/window-10 (full OOMs edge; window-10 always feasible)
    #   Q_slo=0.20 — start cloud/full (only representation above SLO; edge OOMs anyway)
    if q_slo_val <= Q_SLO_LOW:
        start_loc  = "edge"
        start_mode = "window-10"
        oom_fb     = "window-10"
    else:
        start_loc  = "cloud"
        start_mode = "full"
        oom_fb     = "window-10"  # graceful edge fallback when full OOMs

    # Cloud failure context override: JointInertia maintains warm window-10 KV on
    # edge regardless of Q_slo level, so its cloud failure re-prefill is at 7180 tok
    # (not 18822). Reactive policies pay the full context re-prefill on cloud failure.
    cf_override = (_WIN10_FALLBACK_CTX
                   if getattr(pol, "has_warm_window10_fallback", False)
                   else None)

    try:
        with _WorkloadContext(quality_slo, LOCOMO_TOKENS):
            m = run_episode(
                wl, net, pol,
                memory_cap_mb=MEMORY_CAP_MB,
                start_location=start_loc,
                start_mode=start_mode,
                initial_accumulated_tokens=18822,
                oom_fallback_mode=oom_fb,
                quality_override=quality_slo,
                cloud_failure_ctx_override=cf_override,
            )
    finally:
        cost_model._INERTIA_EXTRAPOLATED.clear()

    # SLO violations: actual quality (from config string) < q_slo_val.
    slo_viols = sum(1 for c in m.cycles
                    if actual_quality.get(_mode_from_config(c.config), 0.0) < q_slo_val)
    mean_actual_q = (sum(actual_quality.get(_mode_from_config(c.config), 0.0)
                         for c in m.cycles) / max(1, len(m.cycles)))

    total_time_s = N_CYCLES * m.mean_cycle_latency_s
    avail_frac   = 1.0 - (m.total_planning_gap_s / total_time_s) if total_time_s > 0 else 1.0

    return {
        "planning_gap_s":            round(m.total_planning_gap_s, 3),
        "reasoning_avail_frac":      round(avail_frac, 4),
        "mean_latency_s":            round(m.mean_cycle_latency_s, 4),
        "mean_actual_quality":       round(mean_actual_q, 4),
        "slo_viol_rate_quality":     round(slo_viols / N_CYCLES, 4),
        "num_migrations":            m.num_migrations,
        "cloud_fail_reprefill_s":    round(m.cloud_failure_reprefill_s, 3),
        "mode_switch_reprefill_s":   round(m.mode_switch_reprefill_s, 3),
        "oom_events":                m.oom_events,
        "has_warm_fallback":         getattr(pol, "has_warm_window10_fallback", False),
    }


# ── VLM cost confirmation ──────────────────────────────────────────────────────

def _print_vlm_confirmation():
    vlm_mean = FP16["vlm_mean_s"]
    vlm_min  = FP16["vlm_min_s"]
    vlm_max  = FP16["vlm_max_s"]
    mu    = math.log(vlm_mean)
    sigma = (math.log(vlm_max) - math.log(vlm_min)) / 3.0

    print("\n── VLM per-cycle cost ──────────────────────────────────────────────────────")
    print(f"  FP16['vlm_mean_s'] = {vlm_mean} s   (fixed configured parameter)")
    print(f"  FP16['vlm_min_s']  = {vlm_min} s")
    print(f"  FP16['vlm_max_s']  = {vlm_max} s")
    print(f"  Distribution: lognormal(μ=ln({vlm_mean:.2f})={mu:.4f}, σ={sigma:.4f})")
    print(f"  Per-cycle VLM latency: drawn from this lognormal, clipped to [{vlm_min}, {vlm_max}]")
    print(f"  Workload generated once with fixed seed → deterministic per run, varies cycle-to-cycle.")
    print(f"  NOT a fixed 9.2 s constant; mean ≈ 9.2 s. NOT inflated — measured device param.")
    print()
    print(f"  Dominant per-cycle cost AFTER warm-cache fix:")
    print(f"    VLM (mean): {vlm_mean:.2f} s")
    from cost_model import TOKENS_PER_CYCLE_FULL, edge_compute_ms
    warm_ms = edge_compute_ms("fp16", 7180, gen_tokens=10,
                               warm_prefill_tokens=TOKENS_PER_CYCLE_FULL)
    print(f"    LLM (edge, warm {TOKENS_PER_CYCLE_FULL} tok): {warm_ms:.1f} ms = {warm_ms/1000:.4f} s")
    print(f"  VLM/LLM ratio: {vlm_mean/(warm_ms/1000):.0f}× — VLM dominates; LLM cost is noise.")
    print()


# ── Inertia bounds report ──────────────────────────────────────────────────────

def _print_inertia_bounds():
    target = 18822
    print("── Inertia at 18822 tokens (SmolLM2 proxy; Qwen7B not profiled) ──────────")
    if _JETSON_JSON.exists():
        print(f"  Edge (Jetson AGX Orin) at {target:,} tokens:")
        print(f"    Clamped at measured ceiling (8192 tok): {_EDGE_CLAMPED_MS:.0f} ms = "
              f"{_EDGE_CLAMPED_MS/1000:.2f} s  ← underestimate (used to label 'low')")
        print(f"    Power-law extrapolation:                {_EDGE_POWERLAW_MS:.0f} ms = "
              f"{_EDGE_POWERLAW_MS/1000:.2f} s  ← 'low bound' run")
        print(f"    Linear extrapolation (last segment):    {_EDGE_LINEAR_MS:.0f} ms = "
              f"{_EDGE_LINEAR_MS/1000:.2f} s  ← 'high bound' run")
    if _A6000_JSON.exists() and _SERVER_POWERLAW_MS is not None:
        print(f"  Server (A6000) at {target:,} tokens:")
        print(f"    Power-law: {_SERVER_POWERLAW_MS:.0f} ms = {_SERVER_POWERLAW_MS/1000:.3f} s  "
              f"[cheap — server upload is fast]")
    else:
        print(f"  Server (A6000): inertia_smollm2_a6000.json not found; "
              f"using clamped fallback from cost_model.")
    print(f"\n  JointInertia warm fallback: on cloud failure re-prefills {_WIN10_FALLBACK_CTX:,} tok "
          f"(window-10, always warm on edge).")
    print(f"  Reactive policies: re-prefill full {target:,} tok "
          f"(pays power-law or linear bound).")
    print()

    from cost_model import inertia_ms
    w10_edge_s = inertia_ms("edge", 7180) / 1000.0
    print(f"  Quick reference (measured SmolLM2 proxy, from curve):")
    print(f"    Edge window-10 (7180 tok):   {w10_edge_s:.2f} s  [applies to JI warm fallback]")
    if _JETSON_JSON.exists():
        print(f"    Edge full    (18822 tok): power-law {_EDGE_POWERLAW_MS/1000:.2f} s / "
              f"linear {_EDGE_LINEAR_MS/1000:.2f} s  [applies to reactive policies]")
    print()


# ── Validation print ───────────────────────────────────────────────────────────

def _print_validation(results_by_slo):
    from cost_model import inertia_ms
    kv_sm = 0.1875
    w10_mem  = int(7180  * kv_sm + 3264 + 7163)
    full_mem = int(18822 * kv_sm + 3264 + 7163)

    for q_slo, mob_results in results_by_slo.items():
        feasible_modes   = {k: v for k, v in LOCOMO_QUALITY.items()
                            if v >= q_slo and k != "shuffled"}
        infeasible_modes = {k: v for k, v in LOCOMO_QUALITY.items()
                            if 0.0 <= v < q_slo and k != "shuffled"}

        print("=" * 108)
        print(f"Q_slo = {q_slo:.2f}")
        print(f"  Feasible:   " + ", ".join(f"{k}={v:.3f}" for k, v in sorted(feasible_modes.items())))
        print(f"  Infeasible: " + ", ".join(f"{k}={v:.3f}" for k, v in sorted(infeasible_modes.items())))
        print(f"  Edge memory cap = {MEMORY_CAP_MB:,} MB  |  "
              f"window-10: {w10_mem:,} MB ({'fits' if w10_mem < MEMORY_CAP_MB else 'OOM'})  |  "
              f"full: {full_mem:,} MB ({'OOM on edge' if full_mem > MEMORY_CAP_MB else 'fits'})")
        if q_slo > Q_SLO_LOW:
            print(f"  Start: cloud/full.  JointInertia warm fallback → re-prefill {_WIN10_FALLBACK_CTX} tok "
                  f"({inertia_ms('edge', _WIN10_FALLBACK_CTX)/1000:.2f} s) on cloud fail.")
            print(f"  Reactive policies → re-prefill 18822 tok (power-law={_EDGE_POWERLAW_MS/1000:.2f}s, "
                  f"linear={_EDGE_LINEAR_MS/1000:.2f}s) on cloud fail.")

        # Column header
        hdr = (f"\n  {'Policy':<24} {'inertia':>10} {'gap_s':>8} {'avail%':>8} "
               f"{'lat_s':>7} {'quality':>8} {'slo_viol':>9} "
               f"{'migs':>5} {'cf_rep_s':>9} {'ms_rep_s':>9} {'oom':>4}")
        sep = "  " + "-" * 104

        for mob in VALIDATION_MOBILITY:
            if mob not in mob_results:
                continue
            print(f"\n  [{mob.upper()}]")
            print(hdr)
            print(sep)
            for pol in POLICY_NAMES:
                for ik, (ilabel, _, _) in _INERTIA_CONFIGS.items():
                    key = (mob, pol, ik)
                    if key not in mob_results[mob]:
                        continue
                    r = mob_results[mob][key]
                    wf = " ★" if r.get("has_warm_fallback") else "  "
                    print(f"  {pol:<24} {ilabel:>10} "
                          f"{r['planning_gap_s']:>8.2f} "
                          f"{r['reasoning_avail_frac']:>7.1%} "
                          f"{r['mean_latency_s']:>7.3f} "
                          f"{r['mean_actual_quality']:>8.3f} "
                          f"{r['slo_viol_rate_quality']:>8.1%} "
                          f"{r['num_migrations']:>5} "
                          f"{r['cloud_fail_reprefill_s']:>9.2f} "
                          f"{r['mode_switch_reprefill_s']:>9.2f} "
                          f"{r['oom_events']:>4}{wf}")
        print()

    print("=" * 108)
    print("★ = has_warm_window10_fallback (JointInertia only)")
    print()

    # Decisive comparison
    print("── DECISIVE COMPARISON: JointInertia vs ReactiveThreshold ─────────────────")
    for q_slo, mob_results in results_by_slo.items():
        print(f"\n  Q_slo={q_slo:.2f}")
        for mob in VALIDATION_MOBILITY:
            if mob not in mob_results:
                continue
            print(f"\n    [{mob.upper()}]")
            for ik, (ilabel, _, _) in _INERTIA_CONFIGS.items():
                kj = (mob, "JointInertia", ik)
                kr = (mob, "ReactiveThreshold", ik)
                rmr = mob_results[mob]
                if kj not in rmr or kr not in rmr:
                    continue
                rj, rr = rmr[kj], rmr[kr]
                d_gap  = rj["planning_gap_s"] - rr["planning_gap_s"]
                d_avail = rj["reasoning_avail_frac"] - rr["reasoning_avail_frac"]
                d_lat  = rj["mean_latency_s"] - rr["mean_latency_s"]
                d_q    = rj["mean_actual_quality"] - rr["mean_actual_quality"]

                print(f"    [{ilabel}]")
                print(f"      JointInertia:      gap={rj['planning_gap_s']:.2f}s  "
                      f"avail={rj['reasoning_avail_frac']:.1%}  "
                      f"quality={rj['mean_actual_quality']:.3f}  "
                      f"migs={rj['num_migrations']}")
                print(f"      ReactiveThreshold: gap={rr['planning_gap_s']:.2f}s  "
                      f"avail={rr['reasoning_avail_frac']:.1%}  "
                      f"quality={rr['mean_actual_quality']:.3f}  "
                      f"migs={rr['num_migrations']}")
                print(f"      Δ(JI−RT): gap={d_gap:+.2f}s  avail={d_avail:+.1%}  "
                      f"lat={d_lat:+.3f}s  quality={d_q:+.3f}")

                # Verdict
                if d_q > 0.04 and d_gap <= 0:
                    v = "POSITIVE: JI higher quality with no extra planning gap."
                elif d_q > 0.04 and d_gap > 0:
                    v = f"PARTIAL: JI +{d_q:.3f} quality at +{d_gap:.2f}s extra planning gap."
                elif d_q < -0.04:
                    v = "KILL: JI lower quality than RT."
                elif abs(d_lat) <= 0.2 and abs(d_q) <= 0.04:
                    v = "NULL: no meaningful difference (|Δq|≤0.04, |Δlat|≤0.2s)."
                else:
                    v = f"MIXED: Δgap={d_gap:+.2f}s  Δlat={d_lat:+.3f}s  Δq={d_q:+.3f}"
                print(f"      Verdict: {v}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true", default=True)
    parser.add_argument("--no-validate-only", dest="validate_only", action="store_false")
    args = parser.parse_args()

    _print_vlm_confirmation()
    _print_inertia_bounds()

    if not args.validate_only:
        print("Full matrix not implemented — rerun with --validate-only.")
        return

    print(f"Validation: {POLICY_NAMES}")
    print(f"  Regimes: {VALIDATION_MOBILITY}, seed={VALIDATION_SEEDS[0]}")
    print(f"  Q_slo levels: {Q_SLO_LOW} (start edge/window-10) and "
          f"{Q_SLO_HIGH} (start cloud/full)")
    print(f"  Inertia bounds: power-law-low and linear-high at 18822 tokens\n")

    # results_by_slo[q_slo][mob][(mob, pol, ik)] = metrics dict
    results_by_slo = {}

    for q_slo in (Q_SLO_LOW, Q_SLO_HIGH):
        mob_results = {}
        for mob in VALIDATION_MOBILITY:
            mob_results[mob] = {}
            for pol in POLICY_NAMES:
                # For Q_slo=0.12: inertia bounds don't affect edge/window-10 policies;
                # run both for completeness.  For Q_slo=0.20: bounds matter for
                # reactive policies (cloud failure re-prefill at 18822 tok).
                for ik in _INERTIA_CONFIGS:
                    label_short = _INERTIA_CONFIGS[ik][0]
                    print(f"  Running Q_slo={q_slo}  {mob}/{pol}  [{label_short}]  seed=0 ...",
                          flush=True)
                    r = _run_one(pol, mob, 0, q_slo, ik)
                    mob_results[mob][(mob, pol, ik)] = r
                    print(f"    gap={r['planning_gap_s']:.2f}s  "
                          f"avail={r['reasoning_avail_frac']:.1%}  "
                          f"lat={r['mean_latency_s']:.3f}s  "
                          f"q={r['mean_actual_quality']:.3f}  "
                          f"slo_viol={r['slo_viol_rate_quality']:.1%}  "
                          f"migs={r['num_migrations']}  "
                          f"cf_rep={r['cloud_fail_reprefill_s']:.2f}s")
        results_by_slo[q_slo] = mob_results

    _print_validation(results_by_slo)
    print("Stopped after validation. Do not stage or commit.")


if __name__ == "__main__":
    main()
