# StudyU — is the flash-attn/SDPA throughput difference a size effect or a machine effect?

**Host:** h100nvl (`sn4622120321`, GPU 3, exclusive) · **Run:** 2026-10-16 10:44 → 14:00 · **Timing study only — no accuracy is
recorded or reported.**
**Stack:** original `.venv` — torch 2.8.0+cu128, transformers 5.10.2, flash-attn 2.8.3. HF `generate`, batch 1, bf16.
Both backends asserted at load (`model.config._attn_implementation`) and recorded per trial.

## Question

| machine | model | SDPA tok/s vs generated length | flash-attn vs SDPA |
|---|---|---|---|
| A6000 (committed on `origin/main`: `reports/study_q_fa2_backend.md`, `study_p_fa2_backend.md`, `study_j2_fa2_backend.md`) | 4B-T, 8B-T | falls with length (4B-T 43.7 → 16.8 on signs; 8B-T 29.6 → 25.0 on ERQA) | 1.0× short → 1.15–2.4× long |
| H100 (32B, StudyR/S2/T, `reports/h100_night_summary.md`) | 32B-T | flat 23.6–24.2 | 0.79× at every length |

Model size and machine were perfectly confounded. **Hypothesis under test:** at batch 1, the 32B model's ~66 GB weight
read hides attention cost, so 32B shows no SDPA slowdown; a smaller model would. **Test:** run 8B-Thinking on the H100.
If it slows down with length → SIZE EFFECT; if it stays flat like 32B → MACHINE/KERNEL EFFECT.

## Verdict

**MACHINE/KERNEL EFFECT.** On the H100, 8B-Thinking under SDPA is flat with generation position — 24.39 ms/token at
positions 0–500 and 24.59 ms at 8k–16k (forced traces: slope −0.003 ms per 1k tokens) — exactly like 32B. Flash-attn is
0.80× of SDPA at 8B in every length bucket, the same ratio as 32B. The same 8B-Thinking model on the A6000 loses 15–21%
of its SDPA throughput over the same length range, and gains from flash-attn there. So model size does not explain the
A6000 behaviour; the machine (or the software stack on it) does.

**The kernel profile shows why the comparison is not like-for-like across machines.** On the H100, HF's `sdpa` path
runs **PyTorch's bundled FlashAttention-2 kernel** (`pytorch_flash::flash_fwd_splitkv_kernel`) for 100% of prefill and
decode attention calls, at both 8B and 32B (PyTorch's own dispatcher, `torch._fused_sdp_choice`, returns
`FLASH_ATTENTION` for every call; no attention mask is passed). So on this machine "SDPA vs flash-attn" compares two
packagings of the **same** FlashAttention-2 algorithm, and the 20% gap is overhead in HF's `flash_attention_2` code
path, not the attention kernel. Which kernel the A6000's SDPA selected is **NOT OBTAINED** — the probe
`experiments/erqa/study_u_kernel_probe.py` is in the repo for that machine's queue. If the A6000 falls back to the
memory-efficient or math kernel for these calls, then "SDPA" was never one thing across the two machines, and the
A6000 "flash-attn speedup" is FlashAttention-2 against a slower kernel. That would make the size question moot. This
is inference until the A6000 probe runs.

## Design

- **Model:** Qwen/Qwen3-VL-8B-Thinking @ `92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b` (17.53 GB bf16). For the 32B reference:
  Qwen3-VL-32B-Thinking @ `7edd10ff…` (66.71 GB).
- **Questions:** 40 ERQA questions, chosen to cover a range of generated lengths (`results/erqa/study_u/study_u_selection.json`).
  All 400 were ranked by the longest committed trace any model produced on them (4B-T A6000; 32B-T H100 under SDPA
  and flash-attn). The set is the 20 longest, 10 around the median rank, and 10 evenly spaced over the shorter half.
- **Decoding:** CFG-A (temp 0.6, top_p 0.95, top_k 20, min_p 0, sampling), `max_new_tokens=16384`, and
  `set_seed(42 + qid)` before every generate (the same seed under both backends).
- **Interleaving:** both 8B backends were loaded in **one process** (two copies, 35 GB). Each question ran back to back
  under both, with the order alternating per question. This removes the separate-session caveat of the 32B
  comparison.
- **Timing:** per-step timestamps from a stopping-criterion hook with a CUDA sync. HF already syncs every step, and the
  hook's overhead is unmeasurable: 32B SDPA is 41.6 ms/token here vs 41.8 ms in StudyR, which had no hook. The step
  intervals sum to total latency, checked by the smoke test (7325.0 vs 7325.2 ms).
- **Forced-length probes:** labelled, and **never pooled with natural traces**. They use
  `min_new_tokens = max_new_tokens = 16384`.
  - 8B: the 4 longest-ranked questions under both backends, interleaved.
  - 32B: the 2 longest-ranked questions under both backends, loaded sequentially because two 32B copies do not fit.
  - Natural lengths of the forced questions in this run (8B, SDPA / flash-attn): q355 4,292 / 4,294; q382 6,115 / 2,840;
    q48 1,865 / 3,124; q115 4,561 / 1,973. The forced probe measures the hardware out to 16k, which the
    natural ERQA workload only rarely reaches.
- **Caching:** no prefix or KV reuse across trials. Each trial is a cold prefill followed by decode (HF `generate`, a
  fresh cache per call). A 32-token warm-up generate per model before timing is excluded.

## Results

### Lengths obtained (natural 8B)

| backend | n | p10 | median | p90 | max | budget hits | <2k / 2–8k / >8k |
|---|---|---|---|---|---|---|---|
| SDPA | 40 | 141 | 774 | 4,716 | 9,706 | 0 | 27 / 11 / 2 |
| flash-attn | 40 | 141 | 564 | 4,479 | 16,384 | 3 | 29 / 8 / 3 |

### Throughput by own generated length (natural 8B; tok/s = n_generated / latency)

| bucket | SDPA n | SDPA tok/s | SDPA ms/token | FA2 n | FA2 tok/s | FA2 ms/token | FA2/SDPA |
|---|---|---|---|---|---|---|---|
| <2k | 27 | 40.71 | 24.56 | 29 | 32.42 | 30.85 | 0.796× |
| 2–8k | 11 | 40.90 | 24.45 | 8 | 32.53 | 30.74 | 0.795× |
| >8k | 2 | 40.75 | 24.54 | 3 | 32.19 | 31.07 | 0.790× |

**Same-question paired ratio** (FA2 tok/s ÷ SDPA tok/s): **0.796×** median, IQR 0.793–0.798, range 0.789–0.825
(n=40). It is 0.79–0.80× under every bucketing rule (by SDPA length, by FA2 length, or both in the same bucket).
**Wall-time** ratios on the same pairs range from 0.71× to 2.47× depending on which backend's length defines the bucket.
That is the A6000 bucketing artifact again, and it is why only throughput is reported.

### ms/token vs generation position (primary instrument)

Median of the per-trial median step time in each position bin, with the number of trials reaching the bin in brackets.

| model / traces | backend | 0–500 | 500–2k | 2k–4k | 4k–8k | 8k+ | slope (ms per 1k tokens) |
|---|---|---|---|---|---|---|---|
| 8B natural | SDPA | 24.39 (40) | 24.41 (24) | 24.43 (13) | 24.48 (6) | 24.57 (2) | +0.033 (n=18) |
| 8B natural | FA2 | 30.68 (40) | 30.70 (23) | 30.70 (11) | 30.70 (6) | 31.43 (3) | +0.026 (n=15) |
| 8B forced 16k | SDPA | 24.59 (4) | 24.65 | 24.65 | 24.62 | 24.59 | **−0.003** (n=4) |
| 8B forced 16k | FA2 | 30.88 (4) | 30.93 | 30.98 | 30.97 | 31.46 | +0.070 (n=4) |
| 32B forced 16k | SDPA | 41.46 (2) | 41.57 | 41.63 | 41.66 | 41.62 | +0.005 (n=2) |
| 32B forced 16k | FA2 | 52.98 (2) | 52.90 | 52.83 | 52.95 | 54.02 | +0.149 (n=2) |

- **SDPA is flat at both sizes**: over 16k tokens, 8B changes by 0.0 ms and 32B by +0.16 ms (+0.4%). The A6000's 8B-T
  SDPA throughput loss over a comparable range (29.6 → 25.0 tok/s) is about +6 ms/token (33.8 → 40.0 ms), against +0.0 ms (8B) and +0.16 ms (32B) on the H100.
- **Flash-attn shows a small step past 8k** (+0.5 ms at 8B, +1.0 ms at 32B, about 2%), consistent across natural and
  forced traces. It goes in the opposite direction from "flash-attn pays off at long context" on this machine.
- **Flash-attn/SDPA per-token time**: 8B 1.26×, 32B 1.28× (i.e. 0.79×/0.78× throughput). It is essentially
  size-independent.

### Kernel selection on the H100 (`results/erqa/study_u/study_u_kernel_{8bt,32bt}_h100nvl.json`)

| model | HF backend | dispatcher choice (prefill / decode calls) | attention kernels seen by the profiler | other GPU kernel launches (prefill + 16 decode steps) |
|---|---|---|---|---|
| 8B | sdpa | FLASH_ATTENTION 63 / 540 | `pytorch_flash::flash_fwd_splitkv_kernel` + combine (1,206) | 37,162 |
| 8B | flash_attention_2 | n/a (no SDPA calls) | `flash::flash_fwd_splitkv_kernel` + combine (1,179) | 39,894 (+7.4%) |
| 32B | sdpa | FLASH_ATTENTION 91 / 960 | `pytorch_flash::…` (2,038) | 62,707 |
| 32B | flash_attention_2 | n/a | `flash::…` (2,011) | 67,626 (+7.8%) |

**Global SDPA backend switches:** flash, mem_efficient, math and cudnn are all enabled.

**Per-call attention inputs at decode:** bf16, `enable_gqa=True`, `is_causal=False`, no mask, contiguous q.

**Extra kernels in the flash_attention_2 path:** about 2,700–4,900 more kernel launches per probe. Per decode
layer-step, that adds small integer elementwise ops (add, arange, abs, reduce, copy) and one device-to-host copy.
That pattern matches the variable-length bookkeeping HF does around `flash_attn_varlen_func` (cumulative sequence
lengths, max-seqlen computation that syncs to the host).

This is consistent with a fixed per-step cost and a ~20% slowdown when decode is overhead-bound. It is **not** a
timed attribution: the kernel counts are measured; how much of the 6.3 ms (8B) or 11.5 ms (32B) per token each extra
launch costs is not.

## Mechanism verification (CLAUDE.md)

**Step 1 — causal chain.**
1. If SDPA's per-token decode cost grows with KV length while flash-attn's does not, flash-attn gains in throughput as
   the generated length grows.
2. If that growth comes from attention work, it should be larger relative to the per-step total for a smaller model,
   because weight-read time shrinks with size while the cost of reading the KV cache shrinks less.
3. Either way, the claim rests on SDPA executing an attention kernel whose cost grows with context length.

This links to the latency/cost terms of FORMULATION.md's tier cost model (reconstruction and decode latency vs
context length), which every cross-tier latency figure in the project inherits.

**Step 2 — instantiate each link.**

| causal link | quantity | value in this run | varies as expected? | evidence |
|---|---|---|---|---|
| KV length grows | generation position | 0 → 16,384 (forced), up to 9.7k (natural) | yes | step series |
| SDPA cost grows with KV | SDPA step ms vs position | 24.39 → 24.59 (8B), 41.46 → 41.62 (32B) | **CONSTANT** | slope ≈ 0 |
| attention kernel actually executing | profiler kernel names | FlashAttention-2 (`pytorch_flash`) | present | kernel probe |
| model size changes the weight-read share | weight floor | 4.49 ms (8B), 17.11 ms (32B) at 3.9 TB/s | yes | param bytes |

The CONSTANT entry is the finding, not a design failure. The quantity was exercised over the full 0–16k range and
measured at 0.0–0.4% change. That is a **real negative** for the size hypothesis *on this machine*.

**Step 3 — trace one unit.** q355, 8B, forced 16,384 tokens, SDPA (`forced8:8BT:sdpa:q355`):
- 836 input tokens; TTFT 72 ms;
- 16,383 step intervals, median 24.52 ms (intervals + TTFT sum to 402,128.4 ms vs measured 402,128.7 ms);
- position bins 24.43 / 24.49 / 24.50 / 24.53 / 24.53 ms;
- latency 402.1 s = 16,384 tokens / 40.74 tok/s;
- peak allocated memory 37.7 GB (two 8B copies plus the KV cache).

**Step 4 — negative control.** Disabling "attention cost grows with context" is what the flash-attn arm would do *if*
SDPA were a slower kernel. Here the dispatcher shows SDPA is already FlashAttention-2, so the control is built in:
two implementations of the same algorithm produce the same (flat) shape. A position-dependent cost would have to come
from the kernel, and none appears in either.

**Step 5 — alternative explanations.**
1. *The H100 is too fast for attention to matter at any size, while the A6000's lower bandwidth (768 GB/s) exposes
   it.* Bandwidth arithmetic argues against this as the whole story. The 8B KV cache at 16k is about 2.4 GB, about
   3 ms to read on the A6000, but the A6000's SDPA penalty at 8B-T is about 6 ms/token and at 4B-T about 37 ms/token.
   That is more than a bandwidth-bound FlashAttention-2 kernel would cost.
2. *Different SDPA kernel on the A6000* (memory-efficient or math fallback, or a different torch version's dispatch
   rules). This is the leading hypothesis and is directly testable by running the probe there.

## Results consistency check (CLAUDE.md)

1. **Cross-check against committed measurements:**

   | quantity | this run | prior | source | ratio |
   |---|---|---|---|---|
   | 32B SDPA ms/token | 41.6 (hook) | 41.8 | `reports/h100_night_summary.md` linear fit | 1.00 |
   | 32B FA2/SDPA throughput | 0.78× | 0.79× | same | 0.99 |
   | 8B-T SDPA tok/s, short | 40.7 (H100) | 29.6 (A6000) | `origin/main:reports/study_q_fa2_backend.md` | 1.38 |

   The last row is a cross-machine comparison, expected to differ. None exceeds 2×.
2. **Physical plausibility.** 8B at 24.4 ms/token is 5.4× its weight-read floor; 32B at 41.6 ms is 2.4× its floor.
   Nothing beats a floor. The cost per decoder layer is nearly equal across sizes (8B 0.68 ms over 36 layers; 32B
   0.65 ms over 64 layers) despite a 3.8× difference in weight size. That indicates decode bound by per-layer overhead
   (kernel launches, Python), not bandwidth. This was an inference from two sizes. **StudyV (2026-10-16) has since
   measured it directly:** 4B and 8B (both 36 layers, 2× different weights) decode at 30.15 vs 30.70 ms/token under
   HF flash-attn, about 0.84 ms/layer at 4B, 8B and 32B (`reports/study_v_size_ladder_timing.md`).
3. **Distribution sanity.** Per-trial step medians: 8B SDPA 24.29–24.54 ms, 8B FA2 30.57–30.92 ms (n=40 each); TTFT
   medians 69 / 75 ms. The values are tight but vary trial to trial; no exact constants.
4. **Definition audit.** tok/s = n_generated / (prefill + decode) latency, as in the H100 throughput re-check (which
   included instruct trials) and the A6000 corrections. Buckets use the trial's own n_generated. "ms/token by
   position" uses step intervals and excludes the first token (prefill).
5. **Claim linkage.** This bears on the latency/cost terms (FORMULATION.md cost model; CLAIMS C4-type latency
   figures). It **weakens** any statement that "flash-attn speeds up long reasoning traces" as a hardware-general
   claim. The speedup is machine- and stack-specific (A6000 yes, H100 no) and must be quoted with its machine.
6. **Proxy validity.** Kernel identity comes from two independent sources that agree: the dispatcher decision and the
   profiler kernel names. Throughput includes prefill, which is negligible for traces over 100 tokens (TTFT
   60–260 ms).

## Caveats

- **Watchdog gap:** the StudyU watchdog was armed against the wrong process group for about 2 minutes at chain start
  (10:44:56–~10:47, during the 8B kernel probe only, which records kernel identity, not timing). From then on it guarded
  the chain, and no foreign process appeared on GPU 3 for the whole run.
  - Logs: `logs/study_u_gpu_procs.csv` shows only our PIDs on GPU 3. GPUs 0 and 1 (and later another GPU) ran other
    users' jobs, logged but not counted as contamination. Load average ranged 3.2–33.0 (`logs/study_u_loadavg.log`).
- **First dispatcher record failed:** it threw a TypeError (`scale` is keyword-only in torch 2.8). It was fixed and the
  8B probe re-run at 14:02; the profiler kernel names were valid in both runs.
- **Small >8k cells:** the natural >8k buckets have n=2–3. The forced probes (labelled, not pooled) cover 8k–16k with
  4 (8B) and 2 (32B) traces per backend.
- **32B arms were loaded sequentially** (not interleaved) because two 32B copies do not fit.
- **Batch 1, HF `generate` only.** These conclusions say nothing about batched serving or other stacks.

## Files

- **Code:**
  - `experiments/erqa/study_u_fa2_size.py`
  - `experiments/erqa/study_u_kernel_probe.py` (portable; to be run on the A6000)
  - `experiments/erqa/study_u_analyse.py`
- **Data:** `results/erqa/study_u/`
  - `study_u_selection.json`
  - `study_u_trials_h100nvl.jsonl` (92 trials)
  - `study_u_steps_h100nvl.jsonl.gz` (per-step ms)
  - `study_u_results_h100nvl.json`
  - `study_u_run_meta_h100nvl.json`
  - `study_u_kernel_8bt_h100nvl.json`, `study_u_kernel_32bt_h100nvl.json`
- **Logs:** `logs/study_u*.{log,csv}`
