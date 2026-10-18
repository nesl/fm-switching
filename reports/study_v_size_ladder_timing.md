# StudyV — 4B / 8B / 32B decode timing on one machine and one backend

**Host:** h100nvl (GPU 3, exclusive) · **Run:** 2026-10-16 19:32 → 20:21 · **Timing only; no accuracy** (accuracy
exists in StudyQ/P/S1; re-running here would only add cross-stack noise).
**Stack:** HF transformers 5.10.2 + torch 2.8.0+cu128 (original `.venv`), **`flash_attention_2`** asserted at load and
recorded per trial, batch 1, bf16, cold prefill per trial.
**Harness:** StudyU's (`experiments/erqa/study_u_fa2_size.py` `run_trial`, unchanged except that it now labels greedy
trials "greedy"), with per-step timestamps.
**Questions:** StudyU's 40 ERQA questions (`results/erqa/study_u/study_u_selection.json`).

| model | revision | weights | decoder layers | trials | source |
|---|---|---|---|---|---|
| 4B-Instruct | `ebb281ec` | 8.88 GB | 36 | 40 | StudyV (greedy, 512) |
| 4B-Thinking | `1de27d8c` | 8.88 GB | 36 | 40 | StudyV (CFG-A, 16,384, seed 42 + qid) |
| 8B-Instruct | `0c351dd0` | 17.53 GB | 36 | 40 | StudyV (greedy, 512) |
| 8B-Thinking | `92f3c4b4` | 17.53 GB | 36 | 40 | **reused** StudyU natural flash-attn trials (all 40 `natural:8BT:flash_attention_2:*`) |
| 32B-Instruct / Thinking | `0cfaf481` / `7edd10ff` | 66.7 GB | 64 | 400 / 400 | committed StudyR-fa2 arms C / D (same machine and backend; no per-step stamps) |

## Results

**Throughput by own generated length** (median tok/s = n_generated / latency; n in brackets):

| model | generated p50 / max | <2k | 2–8k | >8k | decode step ms (median) |
|---|---|---|---|---|---|
| 4B-Thinking | 958 / 16,384 | 33.1 (25) | 33.1 (13) | 32.9 (2) | 30.15 |
| 8B-Thinking | 564 / 16,384 | 32.4 (29) | 32.5 (8) | 32.2 (3) | 30.70 |
| 32B-Thinking | 357 / 16,384 | 18.6 (371) | 18.7 (26) | 18.6 (3) | 53.1 (StudyU forced) |
| 4B-Instruct | 2 / 4 | 19.2 (40)* | — | — | 29.7 |
| 8B-Instruct | 2 / 2 | 19.7 (40)* | — | — | 30.2 |
| 32B-Instruct | 2 | 8.3 (400)* | — | — | — |

\*Instruct answers are 2 tokens, so tok/s is dominated by prompt processing (TTFT 72–76 ms at 4B/8B).

**ms/token vs generation position** (median of per-trial medians; trials reaching each bin in brackets):

| model | 0–500 | 500–2k | 2k–4k | 4k–8k | 8k+ |
|---|---|---|---|---|---|
| 4B-Thinking | 30.13 (40) | 30.20 (25) | 30.22 (15) | 30.24 (8) | 30.46 (2) |
| 8B-Thinking | 30.68 (40) | 30.70 (23) | 30.70 (11) | 30.70 (6) | 31.43 (3) |
| 32B-Thinking (StudyU forced, n=2) | 52.98 | 52.90 | 52.83 | 52.95 | 54.02 |

## Findings

**Scope of every finding below: H100 NVL, HF eager execution (no torch.compile, no CUDA graphs), batch 1,
`flash_attention_2`.** The conclusions do not extend to other stacks. Under vLLM (CUDA graphs, FA3), 32B decodes at
25.4 ms/token (StudyX), so the per-layer overhead that dominates here is largely removed. They also do not extend
to other batch sizes or to SDPA, nor to other GPUs: on the A6000, 4B-T under the same HF flash-attn path ran at 44.5
tok/s vs 33.1 here (consistency check 1).

1. **4B and 8B decode at the same speed:** 30.15 vs 30.70 ms/token (+1.8%), although 8B has 2.0× the weights. Both
   have 36 decoder layers. 32B, with 64 layers, takes 53.1 ms. **The cost per decoder layer is constant across
   sizes:**

   | model | ms per layer |
   |---|---|
   | 4B | 0.84 |
   | 8B | 0.85 |
   | 32B | 0.83 |

   HF eager batch-1 flash-attention-2 decode on this H100 is therefore set by **layer count**, i.e. fixed per-layer kernel-launch / Python
   overhead, not by weight bandwidth. The weight-read floors (at 3.9 TB/s) are well below the measured times:

   | model | weight-read floor | measured | ratio |
   |---|---|---|---|
   | 4B | 2.3 ms | 30.15 ms | 13× |
   | 8B | 4.5 ms | 30.70 ms | 6.8× |
   | 32B | 17.1 ms | 53.1 ms | 3.1× |

   This confirms, by direct measurement, what StudyU could only infer from two sizes.
2. **Flat with position at every size:** under 1% change from position 0 to 8k at 4B and 8B. The small rise past 8k
   (4B +0.3 ms, 8B +0.7 ms, 32B +1.0 ms) is the flash-attn step StudyU already found.
3. **Practical consequence for the cost model (H100, HF eager, batch 1, flash-attention-2 only):** on this stack, a
   4B "device" model and an 8B model have the *same* per-token decode latency. Smaller models do not decode faster here. The size ladder buys memory, not speed, at
   batch 1. A different stack does change this: vLLM runs 32B at 25.4 ms/token (StudyX), faster than HF runs 4B. So
   every latency figure in the cost model must carry its stack.
4. **The 4B/8B/32B ladder is now complete on one machine and one backend,** for comparison with the A6000 ladder (SDPA
   and flash-attn; `origin/main` StudyQ/P/J2-fa2 reports).

## Results consistency check

1. **Cross-check against committed measurements:**

   | quantity | StudyV | prior | source | ratio |
   |---|---|---|---|---|
   | 8B-T flash-attn tok/s | 32.4 | 32.4 | StudyU (same trials, reused) | 1.0 |
   | 32B-T flash-attn tok/s | 18.6 | 18.7 | StudyR-fa2 | 1.0 |
   | 4B-T flash-attn tok/s | 33.1 (H100) | 44.5 (A6000, short bucket) | `origin/main:reports/study_q_fa2_backend.md` | 0.74 |

   The A6000 being faster than the H100 at 4B under HF flash-attn is consistent with overhead-bound decode (CPU /
   launch overhead per layer differs by host). It is not a bandwidth effect.
2. **Physical plausibility:** no model beats its weight-read floor.
3. **Distribution sanity:** per-position medians come from 2–40 trials; >8k cells are small (n=2–3), as stated.
4. **Definitions:** as StudyU (throughput includes prefill; position curves exclude the first token).
5. **Claim linkage:** the latency terms of the device/edge/cloud cost model. It weakens any assumption that decode
   latency scales with model size **on H100, HF eager, batch 1, flash-attention-2**. It says nothing about compiled
   or graph-captured stacks (vLLM), batched decode, or other GPUs.
6. **Proxy validity:** layer count as the explanatory variable is supported by two models with identical layer
   counts and 2× different weights. That is a direct test, not a proxy.

## Caveats

- Instruct timings are prefill-dominated (2-token answers) and say little about decode.
- The 32B rows come from StudyR-fa2 (no position stamps) and StudyU's forced probes (n=2).
- One seed per question.

## Files

- **Code:**
  - `experiments/erqa/study_v_size_ladder.py`
  - `experiments/erqa/study_v_analyse.py`
- **Data:** `results/erqa/study_v/`
  - `study_v_trials_h100nvl.jsonl` (120 trials)
  - `study_v_steps_h100nvl.jsonl.gz`
  - `study_v_run_meta_h100nvl.json` (lists the 40 reused StudyU trial IDs)
  - `study_v_results_h100nvl.json`
