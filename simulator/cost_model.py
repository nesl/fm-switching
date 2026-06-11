"""
Shared cost model parameters measured on Jetson AGX Orin (15W mode) plus A6000
cloud reference. All other simulator files import from here.

DATA PROVENANCE
===============
Accuracy (QUALITY) and mean state-size (EFFECTIVE_TOKENS):
  Source : results/exp10_frontier_500_smollm2.json
  Exp    : exp11 — EgoSchema 500-clip representation frontier.
           Edge reasoner: HuggingFaceTB/SmolLM2-1.7B-Instruct (fp16, chat-template).
           Captioner:     Qwen/Qwen2.5-VL-3B-Instruct (fp16, 16 frames/clip).
           Summaries:     Qwen/Qwen2.5-7B-Instruct (7B-generated, reused from exp10).
           Dataset:       EgoSchema public 500-question subset, 5-way MC.
  Date   : 2026-06-10
  Note   : QUALITY values are EgoSchema accuracy (task-quality proxy for the
           edge model). Old synthetic normalised scores kept as comments.

KV bytes per token — edge tier:
  KV_MB_PER_TOKEN_EDGE = 0.1875 MB/tok (SmolLM2-1.7B, fp16 KV, Jetson AGX Orin 15W).
  Derivation: 2 (K+V) × 24 layers × 32 heads × 64 head_dim × 2 B (fp16) = 196 608 B.
  Old measured value (0.236 MB/tok, ~590 MB @ ~2 500 tok, both models combined)
  kept as a comment below.

KV bytes per token — server tier:
  KV_MB_PER_TOKEN_SERVER = PLACEHOLDER — Qwen2.5-7B on A5000, pending A5000 inertia run.

Inertia curves (re-prefill + KV-transfer latency vs. context-token count):
  Edge  : results/exp_inertia_jetson-edge_SmolLM2-1.7B.json   [file pending]
  Server: results/exp_inertia_a5000-server_*.json              [PLACEHOLDER — A5000 run pending]
  Both files are loaded at import time via _load_inertia_curve(); if absent, a
  linear fallback using llm_prefill_ms_per_token is used and a warning is printed.
  Expected JSON schema (bare list or {"data": [...]} wrapper):
      [{"context_tokens": N, "reprefill_ms": M}, ...]
  Accepted latency key aliases: "reprefill_ms", "mean_reprefill_ms", "prefill_ms".
"""

import json
import os
import warnings
from pathlib import Path


# ── Inertia curve loader ───────────────────────────────────────────────
def _load_inertia_curve(json_path: str):
    """Load a re-prefill inertia curve from *json_path*.

    Returns a sorted list of (context_tokens, reprefill_ms) pairs, or None
    if the file is missing/malformed. Callers use linear interpolation.

    Expected JSON (bare list or {"data": [...]} wrapper):
        [{"context_tokens": N, "reprefill_ms": M}, ...]
    Accepted latency-key aliases: "reprefill_ms", "mean_reprefill_ms", "prefill_ms".
    """
    p = Path(json_path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
    except Exception as exc:
        warnings.warn(f"cost_model: could not parse {json_path}: {exc}")
        return None
    rows = raw if isinstance(raw, list) else raw.get("data", [])
    pairs = []
    for row in rows:
        tok = row.get("context_tokens") or row.get("tokens")
        lat = (row.get("reprefill_ms")
               or row.get("mean_reprefill_ms")
               or row.get("prefill_ms"))
        if tok is not None and lat is not None:
            pairs.append((int(tok), float(lat)))
    if not pairs:
        warnings.warn(f"cost_model: {json_path} has no usable (tokens, latency) rows")
        return None
    return sorted(pairs, key=lambda x: x[0])


def _interpolate_inertia(curve, context_tokens: int) -> float:
    """Linear interpolation over a sorted (tokens, ms) curve.
    Clamps to the curve's endpoints for out-of-range queries."""
    if not curve:
        return None
    if context_tokens <= curve[0][0]:
        return curve[0][1]
    if context_tokens >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        t0, m0 = curve[i]
        t1, m1 = curve[i + 1]
        if t0 <= context_tokens <= t1:
            frac = (context_tokens - t0) / (t1 - t0)
            return m0 + frac * (m1 - m0)
    return curve[-1][1]


# Resolve paths relative to this file so imports work from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Frontier JSON loader (quality/tokens from measured accuracy runs) ────
def _load_frontier(json_path: str):
    """Load QUALITY and EFFECTIVE_TOKENS from a frontier_<model>.json result.

    Returns (quality_dict, tokens_dict) or (None, None) if file is absent.
    """
    p = Path(json_path)
    if not p.exists():
        return None, None
    try:
        raw = json.loads(p.read_text())
        summary = raw.get("summary", {})
        quality = {c: s["accuracy"] for c, s in summary.items() if "accuracy" in s}
        tokens  = {c: s["mean_prompt_tokens"] for c, s in summary.items()
                   if "mean_prompt_tokens" in s}
        return quality, tokens
    except Exception as exc:
        warnings.warn(f"cost_model: could not parse {json_path}: {exc}")
        return None, None

# Edge inertia — SmolLM2-1.7B on Jetson AGX Orin 15W.
# Schema path: results/inertia_smollm2_jetson.json  [pending Jetson run]
# Generate with: python experiments/inertia_profile.py --model smollm2 --device jetson
_INERTIA_EDGE_PATH = _REPO_ROOT / "results" / "inertia_smollm2_jetson.json"
_INERTIA_EDGE = _load_inertia_curve(str(_INERTIA_EDGE_PATH))
if _INERTIA_EDGE is None:
    warnings.warn(
        "cost_model: edge inertia curve not found "
        f"({_INERTIA_EDGE_PATH.name}); falling back to linear FP16 prefill rate. "
        "Run: python experiments/inertia_profile.py --model smollm2 --device jetson"
    )

# Server inertia — Qwen2.5-7B on A5000 (GQA). PLACEHOLDER until A5000 run lands.
# Schema path: results/inertia_qwen7b_a5000.json  [pending A5000 run]
# Generate with: python experiments/inertia_profile.py --model qwen7b --device a5000
_INERTIA_SERVER_PATH = _REPO_ROOT / "results" / "inertia_qwen7b_a5000.json"
_INERTIA_SERVER = _load_inertia_curve(str(_INERTIA_SERVER_PATH))
if _INERTIA_SERVER is None:
    warnings.warn(
        "cost_model: server inertia curve not found "
        f"({_INERTIA_SERVER_PATH.name}); falling back to linear CLOUD prefill rate. "
        "Run: python experiments/inertia_profile.py --model qwen7b --device a5000"
    )

# ── Edge FP16 (Qwen2.5-VL-3B + SmolLM2-1.7B) ───────────────────────────
FP16 = {
    "vlm_mean_s":            9.2,    # mean VLM latency (60-token, 448px cap)
    "vlm_min_s":             8.12,
    "vlm_max_s":             14.2,
    "llm_stateless_prefill_ms":  272,
    "llm_prefill_ms_per_token":  1.37,
    "llm_decode_ms_per_token":   5,    # short responses, EOS quickly
    "llm_typical_decode_ms":     5,
    "vlm_weights_mb":        7163,
    "llm_weights_mb":        3264,
    "weights_total_mb":      10427,
    "vlm_load_cold_s":       117,
    "vlm_load_warm_s":       76,
    "llm_load_cold_s":       88,
    "llm_load_warm_s":       47,
    "power_avg_w":           14.7,
}

# ── Edge INT4 (unsloth prequant) ───────────────────────────────────────
INT4 = {
    "vlm_mean_s":            12.95,
    "vlm_min_s":             12.5,
    "vlm_max_s":             15.5,
    "llm_stateless_prefill_ms":  537,
    "llm_prefill_ms_per_token":  1.66,
    "llm_decode_ms_per_token":   5,
    "llm_typical_decode_ms":     5,
    "vlm_weights_mb":        2344,
    "llm_weights_mb":        1056,
    "weights_total_mb":      3400,
    "vlm_load_cold_s":       36,
    "vlm_load_warm_s":       11,
    "llm_load_cold_s":       20,
    "llm_load_warm_s":       11,
    "power_avg_w":           11.7,
}

# ── Cloud (A6000, server-side) ─────────────────────────────────────────
CLOUD = {
    "llm_stateless_prefill_ms":  25,
    "llm_prefill_ms_per_token":  0.154,
    "llm_decode_ms_per_token":   3,
    "llm_typical_decode_ms":     3,
    # Migration to cloud: just round-trip + remote prefill (model already loaded).
    # Migration from cloud: load model on edge (warm) + edge prefill.
}

# ── KV cache + workload growth ─────────────────────────────────────────
KV_GROWTH_MB_PER_CYCLE = 20      # measured: ~590 MB over 30 cycles in full mode
TOKENS_PER_CYCLE_FULL  = 80      # avg per-cycle context growth in full mode
LLM_TRAINING_CONTEXT_LIMIT = 2048  # SmolLM2-1.7B trained context window

# KV bytes per token — PER TIER.
# Edge (SmolLM2-1.7B, fp16 KV, Jetson AGX Orin 15W):
#   Measured from architecture: 2×24×32×64×2 B = 196 608 B ≈ 0.1875 MB/tok.
#   Source: exp11 design note (2026-06-10).
#   Old combined measurement (both models, ~590 MB @ ~2 500 tok): 0.236 MB/tok.
KV_MB_PER_TOKEN_EDGE   = 0.1875                          # SmolLM2-1.7B, fp16 KV
KV_BYTES_PER_TOKEN_EDGE = KV_MB_PER_TOKEN_EDGE * 1024 * 1024  # ≈ 196 608 B

# Server (Qwen2.5-7B on A5000): PLACEHOLDER — A5000 inertia run pending.
# Replace with measured value once exp_inertia_a5000-server_*.json lands.
KV_MB_PER_TOKEN_SERVER   = None   # ← PLACEHOLDER
KV_BYTES_PER_TOKEN_SERVER = None  # ← PLACEHOLDER

# Default aliases used by existing functions (edge model is the primary target).
# Old value: KV_MB_PER_TOKEN = 0.236  (kept here for reference; superseded above)
KV_MB_PER_TOKEN    = KV_MB_PER_TOKEN_EDGE
KV_BYTES_PER_TOKEN = KV_BYTES_PER_TOKEN_EDGE

# ── Quality scores + token counts: load from frontier_smollm2.json ──────
# Schema path: results/frontier_smollm2.json  (generated by representation_frontier.py)
# Falls back to the measured values from exp11 (2026-06-10) if JSON is absent.
_FRONTIER_SMOLLM2_PATH = _REPO_ROOT / "results" / "frontier_smollm2.json"
_q_loaded, _t_loaded = _load_frontier(str(_FRONTIER_SMOLLM2_PATH))

# ── Quality scores per context mode ────────────────────────────────────
# Source: results/frontier_smollm2.json (SmolLM2-1.7B, EgoSchema n=500, 2026-06-10).
# Values are 5-way MC accuracy — task-quality proxy for the edge reasoner.
# Old synthetic normalised scores (pre-exp11):
#   "stateless": 0.70,  "window-3": 0.85,  "window-10": 0.90,  "full": 1.00
_QUALITY_FALLBACK = {
    "blind":       0.264,
    "stateless":   0.332,
    "window-3":    0.356,
    "window-10":   0.360,
    "full":        0.384,
    "shuffled":    0.264,
    "summary-80":  0.388,   # best Pareto point (equal accuracy, 3× fewer tokens than full)
    "summary-200": 0.384,
}
QUALITY = _q_loaded if _q_loaded else _QUALITY_FALLBACK

# ── Mean context token count by mode ───────────────────────────────────
# Source: results/frontier_smollm2.json, mean_prompt_tokens, 500-clip EgoSchema.
# Old rough averages from context_inertia.py (fewer frames, different captioner):
#   "stateless": 161,  "window-3": 365,  "window-10": 745,  "full": None
_TOKENS_FALLBACK = {
    "blind":       279,
    "stateless":   341,
    "window-3":    467,
    "window-10":   909,
    "full":        None,    # grows dynamically; mean 1290 tok at 500 clips
    "shuffled":    1290,
    "summary-80":  385,
    "summary-200": 532,
}
EFFECTIVE_TOKENS = _t_loaded if _t_loaded else _TOKENS_FALLBACK


def inertia_ms(tier: str, context_tokens: int) -> float:
    """Return the measured re-prefill (+ KV-transfer) latency in ms for
    *context_tokens* tokens on *tier* ('edge' | 'server').

    Uses the measured inertia curve when available; falls back to the linear
    prefill-rate model from FP16/CLOUD dicts when the curve JSON is absent.

    Provenance:
      edge   — _INERTIA_EDGE loaded from results/exp_inertia_jetson-edge_SmolLM2-1.7B.json
      server — _INERTIA_SERVER loaded from results/exp_inertia_a5000-server_*.json
               [PLACEHOLDER — A5000 run pending; linear fallback active]
    """
    if tier == "edge":
        val = _interpolate_inertia(_INERTIA_EDGE, context_tokens)
        if val is not None:
            return val
        # Linear fallback: stateless offset + per-token rate (FP16).
        return (FP16["llm_stateless_prefill_ms"]
                + FP16["llm_prefill_ms_per_token"] * context_tokens)
    elif tier == "server":
        val = _interpolate_inertia(_INERTIA_SERVER, context_tokens)
        if val is not None:
            return val
        # Linear fallback: CLOUD prefill rate (no stateless offset measured yet).
        return CLOUD["llm_prefill_ms_per_token"] * context_tokens
    else:
        raise ValueError(f"inertia_ms: unknown tier {tier!r}; expected 'edge' or 'server'")


def edge_compute_ms(quant, context_tokens, gen_tokens=10):
    """Edge-only compute time (ms): prefill + decode. No network."""
    params = FP16 if quant == "fp16" else INT4
    return (params["llm_prefill_ms_per_token"] * context_tokens
            + params["llm_typical_decode_ms"] * gen_tokens)


def cloud_compute_ms(context_tokens, gen_tokens=10):
    """Cloud-only compute time (ms): prefill + decode. No network."""
    return (CLOUD["llm_prefill_ms_per_token"] * context_tokens
            + CLOUD["llm_typical_decode_ms"] * gen_tokens)


def llm_latency_ms(quant, location, context_tokens, gen_tokens=10, network_rtt_ms=0):
    """Return total LLM latency in ms for one cycle.
    quant: 'fp16' | 'int4'  -- only relevant when location='edge'
    location: 'edge' | 'cloud'
    context_tokens: prompt token count
    gen_tokens: tokens to generate (default 10 — short response)
    network_rtt_ms: only used if location='cloud'.

    Cloud branch = `cloud_compute_ms(...) + network_rtt_ms`. The simulator's
    network model currently exposes per-state RTT but **bandwidth_mbps is
    intentionally unused** — there is no input/output byte transfer term.
    TODO: when implementing the KV-transfer sync variant for LH-B/C, plumb
    in a bandwidth-dependent term using `KV_BYTES_PER_TOKEN` and the
    Markov state's `bandwidth_mbps`.
    """
    if location == "edge":
        return edge_compute_ms(quant, context_tokens, gen_tokens)
    return cloud_compute_ms(context_tokens, gen_tokens) + network_rtt_ms


def cloud_serve_outcome(trajectory, ctx_tokens, gen_tokens=10):
    """Within-cycle cloud-serve outcome given a 1-Hz trajectory of
    (rtt_ms, connected) across the cycle's first ceil(T_cloud_compute) sub-ticks.

    Returns:
      success (bool)        : True iff every sub-tick in the window is connected.
      mean_rtt_ms (float)   : average RTT across the window (5 ms on empty window).
      elapsed_s (float)     : time spent on cloud before failure (or full T_cloud
                               if successful). Used by LH-variant fallbacks.

    T_cloud is purely the cloud compute time (no RTT) to avoid circular
    dependence on the RTT we're trying to derive from the trajectory.
    """
    t_cloud_s = cloud_compute_ms(ctx_tokens, gen_tokens) / 1000.0
    import math as _m
    n = max(1, _m.ceil(t_cloud_s))
    window = trajectory[:n] if trajectory else []
    if not window:
        return True, 5.0, t_cloud_s
    success = all(c for _, c in window)
    if success:
        mean_rtt = sum(r for r, _ in window) / len(window)
        return True, float(mean_rtt), t_cloud_s
    # Failure: find first disconnected sub-tick; elapsed = its index in seconds
    for i, (_, c) in enumerate(window):
        if not c:
            elapsed = float(i)
            connected_rtts = [r for r, conn in window[:i] if conn]
            mean_rtt = sum(connected_rtts) / len(connected_rtts) if connected_rtts else 5000.0
            return False, float(mean_rtt), elapsed
    # unreachable
    return True, 5.0, t_cloud_s


def cloud_prefill_extend_s(from_tokens, to_tokens, network_rtt_ms, gen_tokens=0):
    """Cost (s) to extend an existing cloud KV cache from depth `from_tokens` to
    `to_tokens`. Charges per-token prefill on the *delta* only, plus one RTT.
    If gen_tokens > 0, also include the decode for those tokens. Used by the
    latency-hiding policy's buffer-and-replay step: cloud has already prefilled
    to `from_tokens` during warming; we now replay the turns that arrived since
    warm-start (the delta) before switching over.
    """
    delta = max(0, to_tokens - from_tokens)
    prefill_ms = CLOUD["llm_prefill_ms_per_token"] * delta
    decode_ms = CLOUD["llm_typical_decode_ms"] * gen_tokens
    return (prefill_ms + decode_ms + network_rtt_ms) / 1000.0


def migration_cost_s(direction, target_quant, context_tokens, network_rtt_ms,
                     warm_cache=True, gen_tokens=10):
    """direction: 'to_cloud' | 'to_edge'.
    Returns total seconds the LLM is unavailable during the migration.
    """
    if direction == "to_cloud":
        # Send context, prefill on cloud, no model load needed
        prefill_ms = CLOUD["llm_prefill_ms_per_token"] * context_tokens
        decode_ms  = CLOUD["llm_typical_decode_ms"] * gen_tokens
        return (prefill_ms + decode_ms + network_rtt_ms) / 1000.0
    elif direction == "to_edge":
        # Load model on edge + prefill locally
        params = FP16 if target_quant == "fp16" else INT4
        load_s = params["llm_load_warm_s"] if warm_cache else params["llm_load_cold_s"]
        prefill_ms = params["llm_prefill_ms_per_token"] * context_tokens
        return load_s + (prefill_ms / 1000.0)
    else:
        raise ValueError(direction)


def memory_used_mb(quant, location, context_tokens):
    """Approximate GPU memory used. VLM always on edge. LLM may be remote."""
    weights = FP16 if quant == "fp16" else INT4
    vlm_mem = weights["vlm_weights_mb"]
    llm_mem = weights["llm_weights_mb"] if location == "edge" else 0
    kv = KV_MB_PER_TOKEN * context_tokens if location == "edge" else 0
    return vlm_mem + llm_mem + kv


def replica_compute_ms(replica_tier, new_tokens, quant="fp16"):
    """Redundant-compute replica sync cost (ms).

    Per Track 1 sign-off (Q4): the replica pays its OWN tier's prefill rate
    on the new tokens of each turn. cloud replica → 0.154 ms/tok;
    edge replica → 1.37 ms/tok (FP16) or 1.66 ms/tok (INT4).
    """
    if new_tokens <= 0:
        return 0.0
    if replica_tier == "cloud":
        return CLOUD["llm_prefill_ms_per_token"] * new_tokens
    params = FP16 if quant == "fp16" else INT4
    return params["llm_prefill_ms_per_token"] * new_tokens


def replica_memory_mb(replica_tier, context_tokens, quant="fp16"):
    """Memory footprint of a warm replica holding weights + KV.

    The VLM lives on edge regardless of LLM placement; replica memory
    accounts only for the LLM weights + KV at the replica tier.
    """
    if replica_tier == "edge":
        params = FP16 if quant == "fp16" else INT4
        return params["llm_weights_mb"] + KV_MB_PER_TOKEN * context_tokens
    # Cloud replica: FP16 weights + KV
    return FP16["llm_weights_mb"] + KV_MB_PER_TOKEN * context_tokens
