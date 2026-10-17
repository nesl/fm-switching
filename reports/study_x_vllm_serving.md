# StudyX — vLLM serving at 32B: what a non-terminating request costs a shared tier

**Host:** h100nvl (`sn4622120321`, GPU 3, exclusive; watchdog on the chain's session) · **Run:** 2026-10-16 14:05 → 19:05; policy comparison and matched-cap Part B 2026-10-16 21:04 → 2026-10-17 01:15 (tmux `studyx2`)
**Stack (every StudyX number unless labelled otherwise):** vLLM 0.31.0+cu129, torch 2.13.0+cu129, transformers 5.17.0,
in the separate venv `~/.venvs/fm-switching-vllm`. The original `.venv` is untouched (identical `pip freeze` before and
after).
- **Server settings:** OpenAI-compatible server, `tensor_parallel_size=1`, `gpu_memory_utilization=0.90`,
  `max_model_len=32768`, bf16, prefix caching **off** (every request is a cold prefill; no cross-request cache hits),
  chunked prefill at vLLM default.
- **Attention:** vLLM's own choice, **FLASH_ATTN (FlashAttention-3)**, with torch.compile and CUDA graphs.
- **Sampler:** vLLM's PyTorch-native top-k/top-p (`VLLM_USE_FLASHINFER_SAMPLER=0`; see Setup).
- **Models:** Qwen3-VL-32B-Instruct @`0cfaf481`, Qwen3-VL-32B-Thinking @`7edd10ff`.
- **Decoding:** Thinking uses CFG-A (temp 0.6, top_p 0.95, top_k 20, min_p 0); Instruct is greedy.

**vLLM and HF numbers are never pooled in one table without a stack label.** HF comparisons come from the original
`.venv` (torch 2.8.0+cu128, transformers 5.10.2) and are labelled HF.

## Headline

**The tier holds 62,944 tokens of KV cache (15.37 GiB, after 62.66 GiB of weights).** That is 2.4 non-terminating
24,576-token sign requests (each holds 25.5–25.9k tokens = 6.7 GB = **41% of the tier** at the end of its life). One
stuck request plus ordinary traffic already fills the cache:

| stuck requests (forced 24,576) | KV at 100%? | evictions during the hold | normal-request stall time (sum) | stuck-request stall time | normal TTFT p90 | normals waiting (mean / max) |
|---|---|---|---|---|---|---|
| 0 (natural cap-hitters, which all terminated; control) | no (max 31–91%) | 0 | 0 s | 0 s | 1.1–2.9 s | 0 / 0 |
| 1 | yes | 6 | 1,326 s | 0 s | 1.1 s | 1.5 / 6 |
| 2 | yes | 7 | 1,598 s | 0 s | 7.4 s | 2.9 / 7 |
| 3 | yes | 18 | **4,187 s** | 155 s | 9.9 s | 4.2 / 8 |
| 4 | yes | 28 | **4,768 s** | 465 s | **73.0 s** | 5.1 / 9 |

1. **The stuck request does not pay; the requests around it do.** vLLM's default (FCFS) scheduler evicts the most
   recently admitted running request when it needs KV blocks (`self.running[-1]`, `v1/core/sched/scheduler.py`). A
   request that never stops becomes the oldest, so it is the last to be evicted.
   - With 1–2 stuck requests, every eviction hit a normal request. Each eviction coincides with a 56–292 s stall in
     that request's token stream, followed by recompute of its prompt plus everything generated so far.
   - The stuck requests decoded at a flat 32–33 ms/token with no stall.
2. **From 3 stuck requests, the stuck ones also evict each other.** That is the first time demand from the stuck
   requests alone exceeds the KV budget (3 × 25.7k > 62.9k).
   - Stuck holds stretch from about 780–807 s to 975 s (k=3) and 1,125 s (k=4).
   - Evictions roughly triple, normal stall time roughly triples, and admission queueing appears: a new request's
     p90 time-to-first-token rises from 1.1 s to 73 s.
3. **Answer to "how many simultaneous cap-hitters before vLLM cannot admit new requests?"**
   - **1 is enough to fill the KV cache and start evictions** under real sign traffic, because ordinary sign
     requests are themselves long: 2–3 of every 22–30 "normal" signs also ran to 24,576.
   - **At 3, the stuck requests alone exceed capacity.**
   - **At 4, new arrivals wait more than a minute (TTFT p90 73 s)** before their first token.

   Against the measured budget, that is 62,944 tokens ÷ 25.7k per stuck request = 2.4.

**Policy comparison (Part C2): who pays is set by the eviction order, and a token budget removes the cost.**

| | FCFS (default) | priority, stuck deprioritized | abort every request at 8,192 tokens | CPU KV offload |
|---|---|---|---|---|
| who is evicted | newest normals; the stuck request is shielded | **the stuck request** (normals only while it is already out) | nobody (0 evictions) | newest normals (as FCFS) |
| normal completions per min (k=2) | 1.19 | **2.47** | **3.08** | 1.22 |
| cost moved to | co-tenants | the stuck request itself (hold 1,420–1,970 s) | requests over budget (3–4 normals per run cut) | — (offload restored 3.5% of queried tokens) |

**Part B at a matched 8,192 cap:** short requests wait **894 s under HF static batching (batch 8) vs a median 7.4 s
under vLLM, about 121×.**

## Setup (Step 0)

**Install:** vLLM 0.31.0's default (PyPI) build needs CUDA 13, and the host driver is 570 (CUDA ≤ 12.8). The
cu129 release wheel was used instead, under CUDA's minor-version compatibility. Two install fixes were applied
before any timing, inside the 1 h debugging budget:
1. **torchcodec:** the PyPI build (0.17.0) is CUDA 13 (`libnvrtc.so.13` missing). It was replaced by
   0.16.0+cu129.
2. **Sampler:** FlashInfer's top-k/top-p sampler JIT-compiles on first use, and the host has only nvcc 11.1 and no
   ninja. vLLM therefore uses its PyTorch-native sampler: same sampling semantics, different implementation.

**Checks before any timing:**
- **Session check:** every GPU-3 process (the `VLLM::EngineCore` subprocess) is in the chain's session and process
  group. The watchdog never mistook it for a foreign process.
- **Inputs identical to HF:** prompt tokens match exactly. Instruct 834 = 834 and Thinking 836 = 836 on the smoke
  question; 40/40 Instruct prompts match after an annotated reference fix in `study_x_drift_h100nvl.json` (the
  reference counts had used the Thinking processor, whose prompt ends `<think>\n`). Images are the exact pixels HF's
  pipeline produces (`experiments/cost/study_x_prep.py`).
- **KV budget, from the startup log:** 62,944 tokens, 15.37 GiB available, max concurrency at 32,768 tokens = 1.92×.
  This matches the pre-run estimate (about 65k). KV bytes per token = 64 layers × 8 KV heads × 128 × 2 × 2 B =
  262,144 B.

**Accuracy drift check** (the only accuracy work in StudyX): 32B-Instruct greedy, 512 tokens, StudyU's 40 ERQA
questions, sequential.

| comparison | differing answers |
|---|---|
| vLLM vs committed HF H100 arm C (SDPA) | **2/40 (5.0%)** |
| vLLM vs committed HF H100 arm C (flash-attn) | 2/40 (5.0%) |
| HF SDPA vs HF flash-attn (same questions) | 2/40 (5.0%) |

That is below the 10% flag and the same size as HF's own backend-to-backend noise (and the A6000→H100 3.5%).
Pooling vLLM and HF *answers* is defensible at this level. Timing is never pooled across the two stacks.

## Part C — non-terminating requests under continuous batching (signs, 32B-Thinking)

**Design:**
- Closed loop at concurrency 7 + k: k "lead" requests, with the other slots refilled with normal signs the moment
  one finishes, until every lead request has finished. All requests use `max_tokens=24576`.
- **Normal signs:** the 23 signs that closed `</think>` within 8,192 tokens in StudyT core under both HF backends,
  cycled; repeats get seed 42 + 1000 × cycle.
- **C1 (natural):** the three StudyT signs that never terminated by 24,576 under HF, at seed 42.
- **C3 (forced, labelled):** k = 1–4 requests with `min_tokens = max_tokens = 24576`, `ignore_eos` (a synthetic
  non-terminator that measures the tier, not the workload). Leads are IMG_0037, IMG_6431, IMG_6443, then IMG_0040.
  What these signs generated naturally: StudyT HF 24,576 / 24,576 / 24,576 (cap) and IMG_0040 closed within 8,192;
  under vLLM in C1, 13,815 / 7,201 / 1,726 tokens.

### C1 — StudyT's cap-hitters terminate under vLLM

| sign | StudyT HF: closed by 24,576? (SDPA / flash-attn) | vLLM tokens | closed | slot hold | normals completed during hold |
|---|---|---|---|---|---|
| IMG_6431 | **no** / yes | 7,201 | yes | 220 s | 10 |
| IMG_6443 | **no** / yes | 1,726 | yes | 50 s | 4 |
| IMG_0037 | yes / **no** | 13,815 | yes | 429 s | 15 |

**All three terminate under vLLM's sampler.** Meanwhile, 2 + 2 + 0 of the "normal" signs, which had terminated
within 8,192 under both HF backends, ran to the 24,576 cap unclosed. Two examples are IMG_6546 and IMG_6548 in the
IMG_6431 run.

Non-termination follows the attempt, not the sign. **This is the fourth independent demonstration of per-attempt
stochasticity:**
1. seed (StudyJ4);
2. attention backend (StudyJ2-FA2, StudyT-fa2);
3. model size (StudyT);
4. now the serving stack.

A sign's "known cap-hitter" status does not transfer across stacks, so a policy cannot pre-identify hitters by
content.

### C3 — the cost a stuck request externalizes

All values are per run.
- **Normal latency** is the latency of normals submitted during the run (including their own waiting and stalls).
- **Stalls** are gaps of more than 2 s in a request's token stream. Every eviction counted in `/metrics` coincides
  with the start of exactly one stall (verified for k=1: 9/9).

| k | stuck hold (s) | stuck KV at end (per request) | stuck KV, lifetime mean | normals done during hold | normal latency p50 / p90 / max (s) | evictions (whole run / during hold) | time at ≥99% KV |
|---|---|---|---|---|---|---|---|
| 1 | 776 | 25.7k tok, 6.7 GB, 41% of tier | 21% | 23 | 131 / 606 / 1,016 | 9 / 6 | 3.4% |
| 2 | 807, 807 | 41% each | 21% | 16 | 153 / 777 / 1,057 | 7 / 7 | 3.7% |
| 3 | 804, 804, 975 | 41% each | 21% | 13 | 173 / 1,139 / 1,322 | 26 / 18 | 6.7% |
| 4 | 780, 780, 942, 1,125 | 41% each | 21% | 17 | 178 / 980 / 1,283 | 29 / 28 | 8.6% |

- **One stuck request's lifetime:** about 13 minutes of one slot, growing linearly to 41% of the tier's KV. It
  averages 21% of the tier over its life, which is roughly what 5 ordinary 3–5k-token sign requests would use.
- **Normal completions per minute of hold fall with k up to 3:** 1.78 (k=1) → 1.19 (k=2) → 0.80 (k=3), then
  0.91 at k=4 (17 in 1,125 s), which is flat within noise. Each run also has 2–3 natural cap-hits among the
  normals.
- **Which requests get evicted:** at k=1–2, only normals (6 normals stalled 175–292 s each at k=1). From k=3, the
  stuck requests too.

**Mechanism verification (CLAUDE.md):**
1. **Causal chain.** A request that does not terminate holds KV that grows linearly with its tokens (FORMULATION.md:
   decode state / memory cost is a function of context length). When the sum of resident KV exceeds the tier's
   budget, the scheduler must queue new arrivals or evict a running request. Eviction under FCFS falls on the
   newest arrivals. The cost appears as their stalls, recompute and queueing, not the stuck request's.
2. **Instantiated quantities:**

   | link | quantity | value | varies as claimed? |
   |---|---|---|---|
   | KV held by the stuck request grows | prompt + generated tokens × 262,144 B | → 6.7 GB (41%) | yes, linear |
   | resident KV exceeds the budget | `kv_cache_usage_perc` | max 31–91% (k=0) → 100% (k ≥ 1) | yes |
   | queueing | `num_requests_waiting` | 0 (k=0) → mean 1.5 → 5.1 | yes, monotone |
   | eviction | `num_preemptions_total` | 0 (k=0) → 6–28 during hold | yes |
   | who pays | stall gaps per request | stuck 0 s at k ≤ 2; normals 1,326–4,768 s | yes |

3. **Trace of one unit (k=1).** IMG_0037 forced, 1,106 prompt tokens:
   - Decodes 24,576 tokens at a median 32 ms/token, no stall, 776 s.
   - Its KV reaches 25,682 tokens (6.73 GB).
   - Evictions at t = 515, 523, 539, 565, 607 and 725 s fall on normals IMG_0073, IMG_0070, IMG_0069, IMG_0058,
     IMG_6602 and IMG_6548, which stall 292, 284, 244, 218, 175 and 56 s.
   - Three more evictions follow after the hold.
4. **Negative control.** C1, the same harness with the lead request terminating naturally (mechanism absent), gives
   0 evictions, 0 waiting and KV max 31–91% (3 runs). Forcing non-termination (k=1) gives KV 100% and evictions.
5. **Alternative explanation.** *Normal sign requests are themselves long, and they alone fill the KV cache.* This is
   partly true: 2–3 normals per run hit 24,576 naturally. But C1 also contained 2 natural cap-hitting normals per run
   and produced zero evictions, so the forced stuck request is what crosses the budget. The effect is
   **additive with the workload's own long tail**, not independent of it. On a short-answer workload, one stuck
   request alone would not fill the tier; 2–3 would.

## Part C2 — policy comparison (run 2026-10-16 21:04 → 2026-10-17 01:15)

**Design:**
- Every run replays **exactly C3's request sequence**: same stuck signs, same normal-sign stream, same seeds, and
  concurrency 7 + k. Exactly **one** thing changes per run.
- **Baselines:** C3_forced_k1 and C3_forced_k2 (FCFS scheduler, no budget, no offload).
- **Same stack** as above (vLLM 0.31.0, FA3, 62,944-token KV).
- **"Normal stalls while a stuck request was itself evicted"** counts normal-request stalls that began inside a stuck
  request's eviction window. That is the attribution needed to tell *who the scheduler chose*.
- **Refill guard:** refills stop after 45 min, a guard against starvation under priority scheduling. It never
  triggered.

| run | k | stuck hold (s) | stuck stall (s) | normal stall events (sum s) | of which while a stuck request was evicted | normal completions per min of hold | normal TTFT p90 (s) | evictions in hold | normals cut by budget |
|---|---|---|---|---|---|---|---|---|---|
| FCFS (C3) | 1 | 776 | 0 | 9 (1,326) | 0 | 1.78 | 1.1 | 6 | — |
| priority, equal priorities (control) | 1 | 793 | 0 | 18 (989) | 0 | 1.82 | 1.2 | 16 | — |
| **priority, stuck deprioritized** | 1 | **1,451** | **677** | 10 (951) | **10 of 10** | 1.94 | 4.8 | 16 | — |
| FCFS (C3) | 2 | 807, 807 | 0, 0 | 7 (1,598) | 0 | 1.19 | 7.4 | 7 | — |
| **priority, stuck deprioritized** | 2 | **1,420, 1,970** | **626, 1,188** | 37 (786) | **37 of 37** | **2.47** | 2.8 | 21 | — |
| **token budget: abort every request at 8,192** | 1 | 238 (cut at 8,192) | 0 | **0** | — | **3.28** | 1.0 | **0** | 3 |
| **token budget: abort every request at 8,192** | 2 | 245, 253 (cut) | 0 | **0** | — | **3.08** | 1.4 | **0** | 4 |
| CPU KV offload, 64 GiB native connector | 2 | 786, 786 | 0, 0 | 13 (1,904) | 0 | 1.22 | 3.0 | 4 | — |

### (a) Priority scheduling: the shielding mechanism is demonstrated, not inferred

**Under FCFS**, vLLM evicts `self.running[-1]` (the most recently scheduled request). **Under `--scheduling-policy
priority`**, it evicts `max(running, key=(priority, arrival_time))`.

1. **The control, priority policy with equal priorities, reproduces FCFS.** The stuck request is never evicted
   (0 stalls), and every eviction lands on normals. The scheduler switch alone changes nothing.
2. **Deprioritizing the stuck request reverses it.**
   - **The scheduler always evicts the stuck request first.** With the stuck request at priority 10 and normals at
     0, the stuck request absorbs the evictions (677 s of stall at k=1, 626 + 1,188 s at k=2), and its hold
     nearly doubles (776 → 1,451 s; 807 → 1,420 and 1,970 s).
   - **Every remaining normal stall** (10/10 at k=1, 37/37 at k=2) began while a stuck request was *already
     evicted*, i.e. there was no lower-priority running request left to take. Those are normals evicting each other
     in the sign set's own long tail. One normal, IMG_0070, again ran to 24,576 naturally.
   - **Normal throughput rises:** at k=2, completions per minute go from 1.19 to 2.47 (2.1×).

   So newest-first (FCFS) eviction is what shields the oldest request. Flipping the eviction order through priority
   moves the cost back onto the stuck request.
3. **What priority cannot do:** it needs the stuck request to be identified *at submission*. C1 shows that "known
   cap-hitter" status does not transfer even across stacks. A deployable version would need priority assigned by
   request class (for example a long-budget class), or changed mid-flight. vLLM 0.31's API does not expose a way to
   change a running request's priority.

### (b) Token budget (abort at 8,192 streamed tokens): removes the externality, at a price

- **Applied to every request** (a gateway policy). The client closes the stream at 8,192 tokens, vLLM aborts the
  request, and its KV is freed at once.
- **The result:** zero evictions, zero waiting, no KV saturation (max 66% / 71%), and the highest normal throughput
  measured (3.1–3.3 completions per minute, 1.8–2.6× FCFS). The stuck request holds its slot for 238–253 s instead of
  776–807 s.
- **The price:** 3 of 20 and 4 of 21 normal requests were cut off at 8,192 tokens. Those are answers that would have
  come later (in the matching C3 runs, 2–3 normal signs ran to 24,576 without closing and 2–3 closed after 8,192 tokens). The budget
  converts an externalized latency cost into lost or late answers for requests over budget. That trade-off is what
  the timeout/escalation policy has to price.

### (c) CPU KV offload: marginal and ineffective in this configuration

`--kv-offloading-size 64 --kv-offloading-backend native`:
- vLLM created an `OffloadingConnector` with a 68.7 GB `/dev/shm` region.
- Over the run, the connector restored **896 tokens out of 25,822 queried (3.5%)**
  (`external_prefix_cache_hits_total`).
- Evicted requests were otherwise recomputed from scratch. Normal stalls are not reduced (13 events, 1,904 s, vs
  FCFS 7 events, 1,598 s).

Every StudyX run disables prefix caching (cold prefills), and the native offload connector matches blocks by prefix
hash, which is the most likely reason it barely engages. Enabling prefix caching would change the cold-prefill
design for one run only, so it was not done (pre-agreed: skip offload if it is not effective). **The result says
offload does not mitigate the stuck-request externality in the cold-prefill configuration. It does not say offload
could not help with prefix caching on.**

### Mechanism verification for (a)

The FCFS result in C3 rested on an inferred link: "eviction order shields the oldest request". Run (a) is the
negative/positive control for it:
- **Equal priorities:** the link is unchanged, and the outcome is unchanged (stuck stalls 0).
- **Inverted eviction order:** the outcome inverts (stuck stalls 677–1,814 s, and 100% of normal stalls fall in
  windows where a stuck request was already evicted).

The alternative explanation, that normals stall because of their own long tail regardless of eviction order, is
what produces the residual normal stalls under (a). It cannot produce the stuck-request stalls, which appear only
when the order is inverted.

## Part B — head-of-line behaviour (ERQA, 32B-Thinking, 7 short + 1 long)

### Primary comparison: both stacks at a matched cap of 8,192 tokens

**Same 5 batches on both stacks:**
- **Long request:** one of StudyU's 5 longest-ranked questions, forced to **exactly 8,192 tokens** (vLLM
  `min_tokens = max_tokens = 8192`; HF: EOS masked for that row until 8,192, with `max_new_tokens=8192`).
- **Short requests:** StudyU's short stratum, natural length up to **8,192**.
- **Decoding:** CFG-A sampling, seeds as in the original Part B. The two stacks draw different tokens, so the short
  requests' lengths differ between stacks (31–2,150 tokens on vLLM, 31–1,155 on HF).

**Stacks:**
- **vLLM:** 8 requests submitted at once, no further arrivals.
- **HF static:** original `.venv` (transformers 5.10.2, torch 2.8.0+cu128), `flash_attention_2` asserted on every
  tower (`attn_guard.assert_fa2`), left padding, one `generate()` per batch. Every request is delivered when
  `generate()` returns.

| batch (long request) | vLLM 0.31 continuous batching: 7 short latencies (s) | vLLM long request | HF static batching, batch 8: delivered latency of each of the 7 short requests | HF short requests' own finish inside the batch (s) | HF long request / ms per step |
|---|---|---|---|---|---|
| b0 (q355) | 3.5, 5.0, 7.4, 8.7, 11.8, 14.8, 56.1 | 213 s | **828 s** | 11.9–82.6 | 828 s / 101 |
| b1 (q382) | 2.2, 3.8, 3.9, 7.8, 9.1, 12.2, 16.2 | 214 s | **896 s** | 6.7–55.0 | 896 s / 109 |
| b2 (q48) | 2.1, 3.7, 3.7, 3.8, 5.3, 15.2, 38.5 | 213 s | **894 s** | 6.6–100.3 | 894 s / 109 |
| b3 (q115) | 3.2, 3.2, 4.4, 7.3, 8.5, 11.0, 34.7 | 213 s | **824 s** | 12.6–30.3 | 824 s / 101 |
| b4 (q138) | 2.5, 4.1, 5.6, 8.1, 9.4, 12.7, 56.1 | 216 s | **898 s** | 6.8–84.8 | 898 s / 110 |
| **all 35 short requests** | **median 7.4 s, p90 27 s, max 56 s** | | **median 894 s (824–898)** | median 17 s | |

- **The head-of-line cost of static batching, measured:**
  - Short requests are delivered after **824–898 s instead of a median 7.4 s: about 121× worse at the median, and
    15–16× worse than the slowest vLLM short request (14.7–16.0×).**
  - Inside the static batch, the short traces had finished after a median 17 s. They spend about 98% of their
    latency waiting for the straggler.
- **The long request itself** takes 213 s on vLLM vs 824–898 s on HF (about 4×). Part of that is the stack (vLLM's
  batch-1 decode is 2.1× HF flash-attn; Part A) and part is HF's per-step cost at batch 8 (101–110 ms).
- **HF memory at this cap:** 87.5–90.5 GB allocated, up to 99.2 GB reserved. It fits, with about 1 GB of headroom on
  the 100.5 GB card.

**Refill variant, vLLM only, at the matched cap** (closed loop at 8, short requests refilling while the long one
runs):
- 184, 202, 195, 187 and 206 short completions during the long request.
- The long request took 249–256 s (+17–20% vs 213 s alone), because it shares every decode step with 7 busy slots.
- Short-request latency: p50 6.1–6.5 s, p90 17–21 s.
- Static batching has no refill equivalent: nothing new is admitted until the batch returns.

### vLLM at the original cap of 16,384 (descriptive only; no HF counterpart)

The original Part B (14:11 → 17:38) let the long request continue past 8,192 up to 16,384.
- **vLLM:** the long request ran to the cap in 4 of 5 batches (435–438 s; b1 terminated at 8,372 tokens in the
  refill run). The short latencies were 2.1–56.8 s (median 7.4 s), the same as at the 8,192 cap.
- **HF static batching at this cap ran out of memory on the first batch** after about 26 minutes:

  > `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 216.00 MiB. GPU 0 has a total capacity of 93.10 GiB of which 215.44 MiB is free … 90.98 GiB is allocated by PyTorch` (in `_upad_input` → `_index_first_axis`)

  Static batching allocates KV for all 8 rows for the whole generation. At 16,384 steps that is about 37 GB on top of
  66.7 GB of weights, which no attention backend fits. HF's padded flash-attn path also copies K and V (gathered by
  index) at every decode step. **No HF latency exists at this cap**, so the 16,384-cap vLLM numbers are not compared
  with HF anywhere.

## Part A — throughput vs concurrency (ERQA, closed loop)

**Load:** N requests always in flight, `max(4N, 16)` per level, using the same randomly ordered questions (rng 0) at
every level.

**Workloads:**
- **natural:** real ERQA answers. Instruct answers are 2 tokens, so Instruct throughput is reported in requests/s.
- **fixed1024:** `min_tokens = max_tokens = 1024`, `ignore_eos`. This is the clean decode-throughput curve.

**fixed1024 (decode capacity; 32B-Instruct and 32B-Thinking are identical to within 1%):**

| concurrency | total tok/s | ×c=1 | per-request decode tok/s | latency p50 / p99 (s) | TTFT p50 / p90 (s) | KV max | evictions |
|---|---|---|---|---|---|---|---|
| 1 | 39.0 | 1.0 | 39.3 | 26.2 / 26.6 | 0.13 / 0.37 | 5% | 0 |
| 2 | 77.8 / 77.2 | 2.0 | 39.3 | 26.3 / 26.8 | 0.2 / 0.5 | 8% | 0 |
| 4 | 153 / 151 | 3.9 | 38.8 | 26.7 / 26.9 | 0.3 / 0.6 | 13% | 0 |
| 8 | 285 / 282 | 7.3 | 37.0 | 28.6 / 29.6 | 0.9 / 1.8 | 30% | 0 |
| 16 | 499 / 493 | 12.8 | 33.5 | 32.2 / 35.7 | 1.9 / 2.9 | 67% | 0 |
| 32 | **771 / 767** | **19.8** | 28.0 | 38.8 / 49.1 | 3.3 / 4.8 | **99.5%** | 2 |

- **Saturation:** total throughput is still rising at 32 (×1.55 from 16 to 32), but **the KV cache is full at 32**
  (32 × ~2k tokens ≈ the 62.9k budget). The tier hits its *memory* limit before its *compute* limit.
- **What the throughput costs each request:** per-request decode rate falls 29% (39.3 → 28.0 tok/s), latency p50
  rises 48% (26.2 → 38.8 s), and p99 rises 84%. That buys 19.8× throughput.
- **This is the arithmetic-intensity argument for a shared tier:** one GPU serves about 20 concurrent decodes at
  70% of single-stream speed. Its ceiling is KV, so the shared tier's capacity is exactly the resource a
  non-terminating request consumes (Part C).

**natural, 32B-Thinking:**

| concurrency | total tok/s | requests/s | latency p50 / p90 / p99 (s) | TTFT p90 (s) | KV max | waiting max |
|---|---|---|---|---|---|---|
| 1 | 38.8 | 0.056 | 7.3 / 50.5 / 77.3 | 0.41 | 7% | 0 |
| 4 | 89.0 | 0.120 | 7.4 / 54.6 / 93.1 | 0.51 | 12% | 0 |
| 8 | 192.7 | 0.255 | 9.1 / 58.7 / 105.5 | 0.63 | 29% | 0 |
| 16 | 225.9 | 0.323 | 11.1 / 57.6 / 147.5 | 3.45 | 56% | 0 |
| 32 | 402.5 | 0.694 | 16.7 / 57.2 / 113.7 | 4.79 | 87% | 7 |

(c=2: 55.1 tok/s, p50 7.9 s.) The natural levels have only 16–128 requests, so their tails are noisy: a single
16k-token trace dominates a level's span.

**natural, 32B-Instruct (2-token answers; prefill-bound):** requests/s goes 3.7 (c=1) → 6.2 (2) → 7.0 (4) → 6.2 (8)
→ 5.0 (16) → 5.7 (32). Latency p50 goes 0.18 → 0.28 → 0.57 → 1.05 → 2.6 → 5.0 s. **Instruct saturates at about
4 concurrent (about 7 requests/s)**, with prompt processing of multimodal input as the bottleneck. Beyond that,
concurrency only adds queueing.

**Batch-1 speed, vLLM vs HF (same machine and model, different stacks):** vLLM decodes 32B at **39.3 tok/s
(25.4 ms/token)**, vs HF batch 1 at 24.0 tok/s (SDPA) / 18.7 (flash-attn) (StudyR, StudyU). That is **1.6× / 2.1×
per request with no batching**, a stack effect (CUDA graphs, torch.compile, FlashAttention-3, fused kernels), not a
batching effect. It is consistent with StudyU/StudyV's finding that HF batch-1 decode here is limited by per-layer
overhead (about 0.84 ms per decoder layer under HF flash-attn). vLLM's 25.4 ms is still 1.5× above the 17.1 ms
weight-read floor.

## Results consistency check (CLAUDE.md)

1. **Cross-check against committed measurements.**

   | quantity | StudyX (vLLM) | prior | source | ratio |
   |---|---|---|---|---|
   | KV tokens available | 62,944 | ~65k estimate | pre-run arithmetic | 0.97 |
   | 32B-T decode, batch 1 | 39.3 tok/s | 24.0 (HF SDPA) / 18.7 (HF FA2) | `h100_night_summary.md` | **1.6 / 2.1** |
   | Instruct greedy answer drift | 5.0% | 3.5% (A6000 → H100) | `h100_night_summary.md` | 1.4 |

   The vs-HF-FA2 decode ratio exceeds 2×. It is explained, not an artifact: the per-request rate is measured
   from streamed token timestamps (25.4 ms/token, above the 17.1 ms bandwidth floor), and the overhead-bound HF
   path is established independently (StudyU/V: constant per-layer cost across 4B/8B/32B).
2. **Physical plausibility.**
   - The peak total 771 tok/s means about 32 × 24 ms per step: 41.5 ms per batched step for 32 sequences, well
     within compute.
   - KV per token, from the log, equals the architecture value (262,144 B).
   - No rate beats the weight-read floor (17.1 ms/token per step).
3. **Distribution sanity.** Percentiles are reported everywhere. fixed1024 latencies are tight (p50 26.2 vs p99
   26.6 s at c=1), as expected for fixed length. Natural levels are wide.
4. **Definition audit.**
   - "Normal sign" = closed within 8,192 in StudyT core under both HF backends (23 signs).
   - "Stuck" = forced `min_tokens = max_tokens = 24576`, `ignore_eos`.
   - "Stall" = an inter-token gap of more than 2 s.
   - tok/s total = completion tokens / (last end − first submit).
   - TTFT = first streamed content token − submit.
5. **Claim linkage.** This bears on FORMULATION.md's tier capacity / reconstruction-cost terms and the
   non-termination arm of the timeout/escalation policy.
   - It **supports**: a shared tier's binding resource for reasoning workloads is KV memory, and a non-terminating
     request's cost is externalized to co-tenants.
   - It **weakens**: any model that treats a stuck request's cost as its own latency only.
6. **Proxy validity.** Evictions are attributed to requests through stall gaps, a proxy. It is validated for k=1:
   9 evictions, exactly 9 stall starts, at matching timestamps. The forced-length request is a labelled proxy for a
   non-terminating trace: it measures the tier, not how often non-termination happens.

## Caveats

- One seed per configuration; the natural levels and C1 have small n.
- Part C normals are drawn from a sign set with a natural long tail, so results are workload-specific (stated
  above).
- Scheduler behaviour is vLLM 0.31.0's.
  - FCFS (newest-first eviction), priority scheduling, a client-side 8,192-token abort and native CPU offload were
    tested (Part C2). `--max-num-seqs` was not.
  - Priority values were assigned *with knowledge of which request is stuck*. That is an oracle; a deployable policy
    must assign them by request class.
  - The token budget's cost (aborted answers) is counted but not scored for accuracy (timing study).
- Part B's HF side exists only at the 8,192 cap. At 16,384 it ran out of memory, and the 16,384-cap vLLM numbers are
  reported without any HF comparison.
- The first two Step-0 attempts failed on install issues (torchcodec, FlashInfer JIT) before any timing; both are
  logged in `logs/queue_chain.log`.
- Integrity: no foreign process on GPU 3 for the whole queue (`logs/queue_gpu_procs.csv`). GPUs 0, 1 and 2 ran other
  users' jobs (logged, not contamination). The SSH session dropped about 17:30 but the queue ran detached and
  completed.

## Files

- **Code (`experiments/cost/`):**
  - `study_x_prep.py` (prompt pack, original venv)
  - `study_x_vllm.py` (vLLM harness, vLLM venv)
  - `study_x_hf_static.py` (HF Part B + StudyW)
  - `study_x_analyse.py`
- **Data:**
  - `results/cost/study_x/study_x_{run_meta,drift,results}_h100nvl.json`
  - `study_x_{requests,metrics,stamps}_h100nvl.jsonl.gz` (gzipped, stamps delta-encoded; read with `experiments/lib/rawio.py`)
  - `study_x_hf_static_partB_cap8192_h100nvl.jsonl` (HF side of Part B)
- **Logs:** `logs/queue_*`, `logs/study_x_server_*.log`
