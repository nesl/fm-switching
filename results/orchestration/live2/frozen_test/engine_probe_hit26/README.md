# Hit 26 probe (D209 (4)): real engine keys on the H100, vLLM 0.31.0+cu129, Qwen3-VL-32B ("32BI")

Captured 2026-11-23T15:04:47-0800 by one read-only GET of /metrics on the live server (port 8031,
GPU 2) during covex-v6-base_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30 (engine pool 15,760 tokens,
native CPU offload on). Raw scrape: metrics_scrape_h100.txt (no secrets; checked). Counters are
cumulative since server start for that cell, not per request.

## Per-request usage block (the schema engine_actions.py:399-401 guesses at)
Read from the installed source, vllm/entrypoints/serve/engine/protocol.py:121-140:
  UsageInfo: prompt_tokens, total_tokens, completion_tokens, prompt_tokens_details, completion_tokens_details
  PromptTokenUsageInfo: cached_tokens, created_cache_tokens, multimodal_tokens
NONE of EXTERNAL_HIT_KEYS ("external_computed_tokens", "num_external_computed_tokens",
"connector_cached_tokens", "kv_connector_cached_tokens", "offloaded_cached_tokens") exists in the
per-request usage block. external_cached_tokens_of() therefore returns None on every request.
The harness stores processed fields only (cache_path, cached_tokens, cached_fraction, prompt_tokens),
not the raw block; no raw response was captured, because that needs a request injected into a live
measured cell.

## Host / CPU residency DOES exist, aggregate only, in /metrics
  vllm:prompt_tokens_by_source_total{source="local_compute"}        3,669,175
  vllm:prompt_tokens_by_source_total{source="local_cache_hit"}     10,094,768
  vllm:prompt_tokens_by_source_total{source="external_kv_transfer"} 4,943,072   (26 % of 18,707,015 prompt tokens)
  vllm:external_prefix_cache_hits_total 4,945,760 / queries 8,618,089
  vllm:prefix_cache_hits_total 10,103,248 / queries 18,721,337
  vllm:prompt_tokens_cached_total 15,037,840 (= local_cache_hit + external_kv_transfer)
  vllm:kv_offload_load_bytes_total (CPU_to_GPU) 1.2965e12 over 1,847 loads; store (GPU_to_CPU) 9.507e11 over 4,995
  vllm:kv_offload_cpu_cache_usage_perc 0.0347
So host hits are real and frequent on the live engine; per-request, they are folded into
prompt_tokens_details.cached_tokens, indistinguishable from GPU hits.

## Second finding: the GPU-KV fraction key is also wrong
cstate.py:663 and live/adapter.py:269 read "vllm:gpu_cache_usage_perc". This engine emits
"vllm:kv_cache_usage_perc" (value 0.7215 at capture) and NO gpu_cache_usage_perc. So
cloud.gpu_kv_fraction falls to its 0.0 default on every live cell on this build, independent of
the swallowed exception in hit 6: a missing key, not an exception, also yields the MIN.
