"""
Shared cost model parameters measured on Jetson AGX Orin (15W mode) plus A6000
cloud reference. All other simulator files import from here.
"""

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
# Empirical KV cache size per token. Measured: ~590 MB at ~2500 tokens (full
# mode, FP16 KV regardless of weight quant) on Jetson Orin running
# SmolLM2-1.7B + Qwen2.5-VL-3B. 0.236 MB/tok ≈ 242 KB/tok. Used by
# `memory_used_mb` for edge KV and (when needed) for KV-transfer sync cost
# calculations in the LH variants.
KV_BYTES_PER_TOKEN = 0.236 * 1024 * 1024   # bytes (≈ 247 530)
KV_MB_PER_TOKEN    = 0.236

# ── Quality scores per context mode ────────────────────────────────────
QUALITY = {
    "stateless":  0.70,
    "window-3":   0.85,
    "window-10":  0.90,
    "full":       1.00,
}

# Effective context tokens by mode (rough averages from exp5)
EFFECTIVE_TOKENS = {
    "stateless":  161,
    "window-3":   365,
    "window-10":  745,
    "full":       None,  # grows; computed dynamically
}


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
