# Phase 1 — a6000 measurement notes

Model: qwen7b (Qwen/Qwen2.5-7B-Instruct)
GPU: NVIDIA RTX A6000 (51.0 GB)
L sweep: [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
Reps: 5
Timestamp: 2026-08-19T09:52:27.055241

Result file: results/phase1/cost_profiles/a6000_qwen7b.json

## Notes

- Window-10 = last 10 corpus turns (~200 tokens/turn), capped by available context; actual window token count in result JSON.
- Summary restore uses a fixed ~80/200-token stub text.
- Summary update generates from the first 8000 chars of context (capped to avoid extreme input lengths for the update path).
- Incremental warm = forward pass of 200 new tokens given cached KV.
- Incremental cold = full prefill of L+200 tokens without KV cache.
- First rep excluded from stats (warm-up).
- OOM and >120 s measurements recorded as infeasible.
- KV cache size is analytical (FP16, measured model config).
- Transfer costs are derived in phase1_analysis.py.
