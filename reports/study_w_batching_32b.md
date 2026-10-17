# StudyW — HF static batching at 32B (the baseline for StudyX)

**Host:** h100nvl (GPU 3, exclusive) · **Run:** 2026-10-16 19:05 → 19:32 · **Timing only; no accuracy.**
**Stack:** HF transformers 5.10.2 + torch 2.8.0+cu128 (original `.venv`), `flash_attention_2` asserted at every load and
recorded per batch, left padding, one `generate()` per batch. **These are HF numbers. They are never pooled with
StudyX's vLLM numbers.**
**Script:** `experiments/cost/study_x_hf_static.py --mode sweep`.
**Data:** `results/cost/study_w/study_w_batches_h100nvl.jsonl` (62 batches), `study_w_questions_h100nvl.json`.

## Design

- **Questions:** 16 length-matched ERQA questions, the ones whose 32B-T flash-attn natural length (StudyR-fa2 arm D)
  is closest to the median (357 tokens). The same 16 at every batch size: batch size 1 → 16 batches, 2 → 8, 4 → 4,
  8 → 2, 16 → 1.
- **32B-Instruct:** greedy, `max_new_tokens=512`.
- **32B-Thinking:** CFG-A, `max_new_tokens=4096`, `set_seed(42 + first qid)`.
- **Per batch:**
  - wall time, which is the latency **every** request in the batch sees, because results return together;
  - each row's internal finish time (the step at which it emitted EOS);
  - real tokens (up to EOS);
  - per-step time;
  - peak allocated / reserved memory.

**No batch size ran out of memory** (peak reserved 90.9 GB at Thinking batch 16 with the 4,096 cap).

## Results

| model | batch size | total real tok/s | ms per decode step | per-request latency median / max (s) | row's own finish, median (s) | padding efficiency | peak alloc / reserved (GB) |
|---|---|---|---|---|---|---|---|
| 32B-Thinking | 1 | 18.5 | 53.9 | 19.8 / 20.6 | 19.8 | 1.00 | 67.7 / 68.0 |
| | 2 | 22.8 | 69.7 | 35.7 / 129.6 | 34.5 | 0.79 | 68.6 / 69.1 |
| | 4 | 29.5 | 71.1 | 67.1 / 159.5 | 29.8 | 0.53 | 70.8 / 72.2 |
| | 8 | 33.9 | 81.1 | 155.3 / 168.7 | 37.2 | 0.34 | 74.5 / 82.5 |
| | 16 | **60.9** | 101.0 | **161.1 / 161.1** | 50.7 | 0.39 | 81.7 / 90.9 |
| 32B-Instruct | 1 | 8.2 | 122 (prefill-dominated) | 0.2 / 0.5 | 0.2 | 1.00 | 67.7 / 68.1 |
| | 2 | 8.6 | 232 | 0.4 / 0.8 | 0.4 | 1.00 | 68.6 / 69.0 |
| | 4 | 8.1 | 493 | 1.1 / 1.3 | 1.1 | 1.00 | 70.3 / 72.4 |
| | 8 | 7.0 | 1,151 | 2.3 / 2.5 | 2.3 | 1.00 | 74.0 / 78.1 |
| | 16 | 6.6 | 2,426 | 4.9 / 4.9 | 4.8 | 1.00 | 81.0 / 85.0 |

Padding efficiency is real tokens ÷ (batch size × steps); 1.00 means no compute was spent on rows that had already
finished.

- **32B-Thinking:**
  - **Throughput:** total throughput rises only 3.3× at batch 16, because the per-step cost nearly doubles
    (54 → 101 ms) and 61–66% of row-steps are wasted on rows that already finished (padding efficiency 0.34–0.39).
  - **Latency:** per-request latency rises 8×, from 19.8 s to 161 s. Every request waits for the slowest in its
    batch. At batch 16 the median row's own trace finished at 50.7 s but was delivered at 161 s.
  - **Even with length-matched questions,** sampling spreads the lengths. In one batch-2 pair, one row finished
    at 228 tokens (15.9 s) but was delivered at 129.6 s, because its partner ran to 1,865 tokens.
- **32B-Instruct (2-token answers):** static batching gives **no** throughput (8.2 → 6.6 tok/s) and costs 25× in
  latency (0.2 → 4.9 s). The work is prompt processing (multimodal prompts), which scales linearly with batch size.
  Batching cannot amortize it.

**vs vLLM continuous batching (StudyX Part A, labelled cross-stack):**
- **Thinking:** at 16 concurrent, vLLM delivers 226 tok/s (natural) vs HF static batch 16's 61 tok/s, **3.7×**. vLLM's
  latency p50 is 11.1 s vs HF's 161 s.
- **Batch 1:** vLLM decodes at 39.3 vs HF's 18.5 tok/s, a 2.1× stack effect before any batching.
- **The static baseline's KV is allocated for the longest row:** HF could not hold Part B's 16k-token straggler in a
  batch of 8 at all (out of memory; StudyX report).

## Results consistency check

1. **Cross-check against committed measurements:** batch-1 32B-T 18.5 tok/s vs StudyR-fa2 18.7 tok/s (ratio 0.99).
   Batch-1 Instruct latency 0.2 s vs StudyR-fa2 arm C 0.2 s. Peak memory at batch 1 is 67.7 GB vs StudyU 32B 71.4 GB
   at 16k context (consistent, since this is shorter context).
2. **Physical plausibility:** the batch-16 decode step of 101 ms for 16 sequences is 6.3 ms per sequence-token. That
   is not faster than the weight-read floor per step (17.1 ms per step, shared across the batch). No anomaly.
3. **Distribution sanity:** the 16 batch-1 Thinking runs give 336–382 tokens at 18.3–18.7 tok/s. That is tight but
   not constant.
4. **Definitions:**
   - "Real tokens" = up to and including the first EOS per row.
   - "Latency" = `generate()` wall time (cold prefill + decode, fresh KV per call, no cross-batch caching).
5. **Claim linkage:** the static-batching baseline for the shared-tier serving cost (FORMULATION.md tier capacity).
   It supports the claim that per-request latency under static batching is set by the batch's slowest member.
6. **Proxy validity:** wall time is the actual delivery time for every request in a static batch, not a proxy.

## Caveats

- One pass per batch size (16 questions). Batch sizes 8 and 16 have 2 and 1 batches, so their latency figures are
  single-batch values.
- `max_new_tokens=4096` (Thinking) bounds the straggler effect. With the natural 16,384 cap, batch 8 runs out of
  memory (StudyX Part B).
- Cold prefill per batch; no prefix caching.
