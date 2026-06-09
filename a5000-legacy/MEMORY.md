# FM Switching with SSM — Project Memory

## Current Status
Phase: 1 (Foundation)
Week: 1
Last session: 2026-03-18
Current focus: Profiling complete. Moving to simulator skeleton.

## Architecture Overview
- **Data Plane**: Context inertia profiling, async background pre-fill, session portfolio management
- **Control Plane**: SSM (Mamba) temporal encoder → MPC optimizer → migration decisions
- **Comparison**: RL policy (PPO) with same SSM encoder as head-to-head against MPC
- **Hardware**: Lab A6000 (48GB) + RTX 3090 Ti (24GB), Jetson AGX Orin (pending), cloud A100

## Key Decisions

### 2026-03-18 — Always use A6000 (GPU 1) as primary profiling device
All scripts default to `--gpu-id 1`. The 3090 Ti (GPU 0) can be used as "Platform B" proxy
for the Jetson until the Orin arrives.

### 2026-03-18 — Prefix caching must be OFF for inertia benchmarking
vLLM server started with `--no-enable-prefix-caching` for script 04. If left on, repeat
measurements at the same depth hit the KV cache and report near-zero prefill time — not
migration cost.

### 2026-03-18 — TTFT via streaming, not round-trip time
Script 04 uses streaming mode and timestamps the first SSE chunk. This gives true
Time-to-First-Token (= prefill time), excluding HTTP overhead and 1-token decode time.

### 2026-03-18 — vLLM /metrics replaces pynvml memory
pynvml memory is useless for vLLM (flat line = pre-allocated pool). SSM state vector
should use `vllm:kv_cache_usage_perc`, `vllm:num_requests_running`,
`vllm:num_requests_waiting` from the Prometheus endpoint at `/metrics`.

### 2026-03-18 — Experiment outputs saved to experiments/<model>_<gpu>_<date>/
All logs, plots, and config.json go to a timestamped directory. `run_profiling.sh`
handles this automatically.

## Experimental Results

### Experiment 2: Context Inertia — Mistral-7B-Instruct-v0.2 on A6000 (2026-03-18)
**Location**: `experiments/mistral-7b_a6000_20260318/`
**Model**: mistralai/Mistral-7B-Instruct-v0.2 | **GPU**: NVIDIA RTX A6000 48GB
**vLLM**: 0.17.1 | **max_model_len**: 16384 | **prefix_caching**: OFF

**Full inertia curve (cold re-prefill TTFT):**
| Tokens | TTFT (ms) | ±std | ms/token |
|--------|-----------|------|----------|
| 300    | 62.0      | 0.4  | 0.2068   |
| 565    | 91.6      | 1.1  | 0.1621   |
| 1084   | 155.9     | 0.6  | 0.1439   |
| 2054   | 303.6     | 1.8  | 0.1478   |
| 4110   | 603.4     | 1.1  | 0.1468   |
| 8463   | 1326.0    | 2.9  | 0.1567   |
| 12870  | 2168.5    | 2.5  | 0.1685   |
| 15378  | 2712.2    | 10.2 | 0.1764   |

**Linear fit**: TTFT = 0.1736 × n − 44.9 ms  (R² = 0.99640)
**Key findings**:
- U-shape in ms/token: minimum at ~1K tokens (0.1439 ms/tok), earlier than Qwen's 2K minimum
- Mistral is **12.7% more expensive per token** than Qwen2.5-7B (0.1736 vs 0.1541 ms/tok slope)
- At 8K tokens: ~1,326ms migration penalty; at 15K tokens: ~2,712ms
- The uptick in ms/token begins at ~1K (Mistral) vs ~2K (Qwen) — Mistral hits O(n²) attention overhead sooner
- Mistral is the paper's **primary model** for experiments; Qwen was the proxy

**Comparison plot**: `experiments/mistral-7b_a6000_20260318/plots/comparison_mistral_vs_qwen.png`

**Simulator parameters (Mistral — use these for MPC cost function)**:
- For contexts ≤ 2K: cost(n) ≈ 0.147 × n ms (near-constant in this range)
- For contexts > 2K: use empirical table or quadratic fit
- Linear approximation: TTFT(n) = 0.1736n − 44.9 ms (adequate for first MPC implementation)

### Experiment 1: Context Inertia — Qwen2.5-7B on A6000 (2026-03-18)
**Location**: `experiments/qwen2.5-7b_a6000_20260318/`
**Model**: Qwen/Qwen2.5-VL-7B-Instruct | **GPU**: NVIDIA RTX A6000 48GB
**vLLM**: 0.17.1 | **max_model_len**: 16384

**Full inertia curve (cold re-prefill TTFT):**
| Tokens | TTFT (ms) | ±std | ms/token |
|--------|-----------|------|----------|
| 293    | 53.8      | 0.8  | 0.1837   |
| 555    | 84.8      | 0.3  | 0.1527   |
| 1073   | 149.5     | 0.5  | 0.1394   |
| 2037   | 257.8     | 1.8  | 0.1266   |
| 4082   | 527.5     | 1.2  | 0.1292   |
| 8410   | 1180.4    | 2.7  | 0.1404   |
| 15732  | 2444.1    | 1.4  | 0.1554   |

**Linear fit**: TTFT = 0.1541 × n − 37.3 ms  (R² = 0.996)
**Key finding — U-shaped marginal cost**:
- ms/token DECREASES from 0.184 → 0.127 as depth goes 293 → 2037 tokens
  (GPU memory bandwidth saturates, prefill becomes more efficient)
- ms/token INCREASES from 0.127 → 0.155 from 2037 → 15732 tokens
  (attention is O(n²) in FLOPs; quadratic overhead wins over BW efficiency at scale)
- **Minimum marginal cost at ~2K tokens** — this is the efficiency sweet spot
- This U-shape means the linear fit is approximate; MPC cost function should use
  a piecewise or quadratic model for accuracy above 4K tokens

**Simulator parameters (use these)**:
- For contexts ≤ 4K: cost(n) ≈ 0.129 × n ms (near-constant ms/token in this range)
- For contexts > 4K: cost(n) rises, use the empirical table or quadratic fit
- At 8K tokens: ~1,180ms migration penalty
- At 15K tokens: ~2,444ms migration penalty

**Session traces (workload generator)**:
- 4 concurrent sessions × 15 turns
- Deep sessions (code_review, research_analysis, data_pipeline): ~520 tok/turn, reach 7,800–8,000 tokens
- Shallow session (short_qa): ~102 tok/turn, reaches 1,000 tokens in 10 turns
- Decode speed degradation: 43.9 → 32.5 tok/s over 15 turns (-26%) under concurrent load

## Open Questions / Blockers

- **Mistral-7B inertia curve**: DONE. See Experiment 2. Mistral is 12.7% costlier per token than Qwen.
- **U-shape in ms/token**: The inflection at ~2K tokens changes the MPC cost model.
  Need to decide: use linear approximation (simple, slightly wrong at deep contexts) or
  piecewise/quadratic (accurate, more complex MPC). Resolve before building MPC.
- **Jetson AGX Orin**: Not yet available. Using 3090 Ti as Platform B proxy for now.
  Flag for rerun when Orin arrives.
- **KV cache transfer cost not measured**: Scripts measure re-prefill cost (recompute from
  transcript). Full migration pipeline also includes KV serialization + network transfer.
  This is Phase 2 work.
- **16K depth failed** with Qwen (conversation builder overshoots exact 16384 limit).
  Used 15K depth target → got 15732 tokens. Fix: add a token-count trim step in
  `build_conversation_to_depth` to stay safely under `max_model_len - 1`.

## Milestone Tracker
- [x] Week 1 Day 1: venv setup, scripts written, all bugs fixed, vLLM running
- [x] Week 1: First inertia curve (Qwen proxy), session traces, GPU+vLLM metrics logger
- [x] Week 1: Rerun with Mistral-7B (primary model) — DONE
- [ ] Week 1 remaining: Build simulator skeleton
- [ ] Week 2: SSM encoder + workload generator + background pre-fill mechanism
- [ ] Week 3: MPC optimizer + SSM→MPC→simulator pipeline + RL baseline started
- [ ] Week 4: All baselines + Experiments 1-3
- [ ] Week 5: Ablations + pre-staging analysis + overhead measurements + MPC vs RL
- [ ] Week 6: Real-device validation + package results

## Session Log

### Session 1 — 2026-03-18
**Accomplished:**
- Set up Python 3.10 venv (vLLM requires ≤3.12; system had 3.13 + 3.10)
- Installed vLLM 0.17.1, PyTorch 2.10+cu128, all deps
- Reviewed and fixed all 5 profiling scripts:
  - Fixed `--disable-log-requests` → `--no-enable-log-requests` (vLLM 0.17.1 API change)
  - Fixed TTFT measurement: now uses streaming mode, timestamps first SSE chunk
  - Added `--no-enable-prefix-caching` to server (critical for benchmark validity)
  - Added periodic flush to GPU logger (crash safety)
  - Suppressed pynvml FutureWarning (transitive dep from vLLM, can't uninstall)
  - Renamed `latency_s` → `incremental_latency_s` to prevent confusion with migration cost
  - Added `--logs-dir`/`--output-dir` args to visualizer; scatter plot for GPU util
- Rewrote GPU logger to scrape vLLM /metrics (kv_cache_usage_perc, requests_running/waiting)
- Updated run_profiling.sh to save to timestamped experiments/ directories + config.json
- Downloaded Mistral-7B-Instruct-v0.2 (~15GB, cached)
- Ran full profiling pipeline with Qwen2.5-7B-Instruct (proxy model, already cached)
- Measured inertia curve across 7 depths from 293 to 15,732 tokens
- **Key discovery**: U-shaped ms/token curve — decreases to minimum at ~2K, then rises

**Decisions:**
- Use `vllm:kv_cache_usage_perc` (not pynvml memory) as primary memory signal in SSM state
- MPC cost function needs piecewise/quadratic model for contexts > 4K tokens
- All experiments default to GPU 1 (A6000)

**Next steps:**
1. Rerun experiment with Mistral-7B-Instruct-v0.2 (the paper's primary model)
2. Fix 16K depth overflow in `build_conversation_to_depth`
3. Build simulator skeleton in `simulator/`
