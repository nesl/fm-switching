# StudyX2a — natural non-termination at the recommended sampling settings

**Host:** h100nvl (`sn4622120321`, GPU 3, exclusive; session watchdog; only our vLLM process in all 544 GPU-3 monitor samples) ·
**Run:** 2026-10-17 09:51 → 11:25 (tmux `studyx3`) · **Pre-registered:** `research/EXPERIMENTS.md` row StudyX2a, written
before launch.
**Stack:** vLLM 0.31.0+cu129, torch 2.13.0+cu129, transformers 5.17.0 (venv `~/.venvs/fm-switching-vllm`). This is the
StudyX server unchanged:
- FLASH_ATTN (FA3), CUDA graphs;
- `gpu_memory_utilization` 0.90, `max_model_len` 32,768, prefix caching off;
- KV 62,944 tokens;
- PyTorch-native sampler.

**Model:** Qwen3-VL-32B-Thinking @`7edd10ff`. **No forcing:** no `min_tokens`, no `ignore_eos`. All numbers are vLLM;
there is no HF data here. Timing is not a result; only lengths and closure are.

## Answer

**At the model card's VL setting (T1.0), natural non-termination is negligible: 1 cap hit in 115 requests (0.9%,
Wilson 95% CI 0.15–4.8%). The pre-registered rule (rate < 2% and upper bound < 5%) is met, so 2b was not started.**

- At the shipped `generation_config.json` setting (T0.8) there were **0 of 115** (CI 0–3.2%).
- The StudyX setting (T0.6, temperature below both recommendations) produced **4 of 115** (3.5%, CI 1.4–8.6%). All
  four are repetition loops.
- **The three StudyX runaways** (IMG_6546@42, IMG_6548@42, IMG_0070@1042) are the 2b lead candidates.
  - They **ran away again at T0.6** and **terminated at both T0.8 and T1.0** (2,615–11,390 tokens).
  - So 2b's candidate leads do not exist at the card setting: their runaway is an artifact of temperature 0.6.

## Settings (verbatim)

**Model card, "Generation Hyperparameters" → "VL":**
```bash
export greedy='false'
export top_p=0.95
export top_k=20
export repetition_penalty=1.0
export presence_penalty=0.0
export temperature=1.0
export out_seq_length=40960
```

**Shipped `generation_config.json` (rev `7edd10ff`):**
```json
"do_sample": true, "top_k": 20, "top_p": 0.95, "repetition_penalty": 1.0, "temperature": 0.8
```
It also contains `eos_token_id` [151645, 151643], `bos_token_id` / `pad_token_id` 151643, and has no
`presence_penalty`.

**Arms.** Every parameter was sent explicitly per request, so vLLM's generation-config defaults never applied:

| arm | temperature | top_p | top_k | min_p | repetition_penalty | presence_penalty | max_tokens |
|---|---|---|---|---|---|---|---|
| T1.0 (card VL) | 1.0 | 0.95 | 20 | 0 | 1.0 | 0.0 | 24,576 |
| T0.8 (generation_config) | 0.8 | 0.95 | 20 | 0 | 1.0 | 0.0 | 24,576 |
| T0.6 (StudyX CFG-A) | 0.6 | 0.95 | 20 | 0 | 1.0 | 0.0 | 24,576 |

**Deviation from the card (pre-registered):** `max_tokens` is 24,576, not `out_seq_length` 40,960, because the
server's 32,768 context cannot hold about 1k prompt tokens plus 40,960. A "cap hit" means "did not close `</think>`
within 24,576 tokens".

**Workload:**
- the 23-sign StudyX normal pool × seeds 42, 1,042, 2,042, 3,042, 4,042 (the StudyX normal-stream seeds) = 115 per arm;
- closed loop at concurrency 12, seed-major order, arms run T1.0 → T0.8 → T0.6;
- full text stored;
- 0 errors in 345 requests.

## Results

| | T1.0 (card) | T0.8 (gen. config) | T0.6 (StudyX) |
|---|---|---|---|
| **cap hits (never closed) / n** | **1 / 115** | **0 / 115** | **4 / 115** |
| rate (Wilson 95% CI) | 0.9% (0.15–4.8%) | 0.0% (0–3.2%) | 3.5% (1.4–8.6%) |
| closed `</think>` but capped in the answer | 0 | 0 | 0 |
| capped traces that loop (8-gram rep ≥ 0.5, last 4,096 tok) | 0 of 1 (rep 0.28) | — | **4 of 4 (rep 0.97–0.99)** |
| terminating traces: 8-gram rep median / p90 / max | 0.10 / 0.18 / 0.27 | 0.11 / 0.20 / 0.59 | 0.15 / 0.25 / 0.70 |
| terminating length median / p90 / p95 / max (tok) | 4,692 / 8,518 / 10,236 / 15,101 | 3,968 / 7,676 / 8,560 / 14,847 | 4,226 / 8,823 / 9,836 / 19,685 |
| mean length, all requests (tok) | 4,942 | 4,264 | 5,310 |
| arm wall time | 30.5 min | 23.9 min | 39.2 min |

**Which attempts hit the cap:**
- **T1.0:** IMG_6447@2042.
- **T0.6:**
  - IMG_6546@42 and IMG_6548@42 (both 10/10 in StudyX);
  - IMG_0070@1042 (4/4 in StudyX);
  - IMG_6578@3042 (0/1 in StudyX).

**Arm contrasts (Fisher exact):**
- T1.0 vs T0.6: p = 0.37, not distinguishable at n = 115.
- T0.8 vs T0.6: p = 0.12.
- T1.0 and T0.8 pooled (1/230) vs T0.6 (4/115): p = 0.044.

The direction is consistent with 0.6 being worse, and the evidence is weak.

### Per-sign structure (pre-registered tests)

- **T1.0 and T0.8:** with fewer than 2 cap hits, overdispersion and leave-one-seed-out predictability are **not
  testable**, as pre-registered.
- **T0.6:** the 4 hits fall on **4 different signs**.
  - **Overdispersion:** χ² = 19.7 on 22 df, permutation p = 1.00. No clustering by sign; hits are as spread out as
    they can be.
  - **Leave-one-seed-out:** a sign's rate on its other 4 seeds does not predict the 5th. AUROC 0.43, and the Brier
    score is 0.043 for the sign-based predictor vs 0.034 for the base rate, so the sign predictor is worse.
- **What *is* reproducible is the specific (sign, seed) attempt.** The 89 T0.6 (sign, seed) pairs that also ran in
  StudyX agree with StudyX's majority outcome in **86 of 89**. All three StudyX attempts that hit in every replay
  hit again here, under different batch composition.
- **Reading:** at T0.6 a runaway is close to a deterministic property of the seeded attempt, not of the sign. This
  resolves the StudyX audit's AUROC 0.95 vs 0.67: the 0.95 was seed reuse.

### Loop vs progress

- **The T0.6 runaways are loops.** In the final 4,096 tokens, 97–99% of 8-grams repeat. For example, IMG_6546@42
  ends by repeating `The first symbol: two figures (a male and a female) in one square? Actually, the image
  shows:` verbatim. The other three cycle on one sentence or one JSON line in the same way.
- **The single T1.0 cap hit is not a loop by the pre-registered measure.** Its 8-gram repetition is 0.28, just
  above the terminating-trace maximum of 0.27. Qualitatively it is circular deliberation, re-deriving
  how to quote a JSON key (`"So the only valid solution is to put double quotes around the key…"`), rather than
  verbatim repetition.
- No terminating trace at T1.0 reaches the loop threshold. At T0.8 and T0.6, 1 and 2 terminating traces cross it
  and then escape.

## Consequences

1. **For StudyX:** its natural cap-hit rate (8% of normals, 28/351) was inflated twice over.
   - **By temperature:** it ran at 0.6, where runaways are repetition loops.
   - **By seed reuse:** IMG_6546@42 and IMG_6548@42 were replayed 10 times.

   Across its 89 distinct attempts, StudyX had 5 majority-hit attempts (5.6%). That is consistent with this T0.6 arm
   (3.5%).
2. **At the settings a deployment would use** (card 1.0 or shipped 0.8), the measured rate is 1 in 230 combined
   (0.4%). The forced-resident cost in StudyX Part C still describes what *any* 25k-token resident costs the tier.
   But a natural non-terminating trace is a rare event at these settings, not a workload property.
3. **2b as specified has no leads at the card setting.** Its candidate leads terminate at T1.0 and T0.8. At T0.6
   they reproduce reliably, so a 2b at T0.6 is feasible, but it would study a setting the model card does not
   recommend.

## Mechanism verification

This is a rate measurement with no causal claim, so the CLAUDE.md mechanism protocol does not apply beyond the
following.
- **Forcing absent:** no request carried `min_tokens` or `ignore_eos` (checked in `params` of all 345 records).
- **Every parameter explicit:** the per-request `params` match the arm table.
- **Cap hits are real:** every cap hit has `finish_reason = "length"`, `completion_tokens` = 24,576 and no
  `</think>`.

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | StudyX2a | prior | source | ratio |
   |---|---|---|---|---|
   | KV tokens | 62,944 | 62,944 | StudyX server log | 1.00 |
   | T0.6 cap-hit rate, per distinct attempt | 3.5% (4/115) | 5.6% (5/89 majority-hit) | StudyX C1/C3/C4/C6 normals | 0.6 |
   | T0.6 outcome of the same (sign, seed) | — | 86/89 agree | StudyX | — |
   | T0.6 terminating length, median | 4,226 | 4,326 (all StudyX normals, incl. capped) | StudyX | 0.98 |

2. **Physical plausibility.** Aggregate decode was 260 / 310 / 342 tok/s (T0.6 / T1.0 / T0.8) with a mean of 8.6 /
   10.2 / 11.0 running requests, i.e. about 30–31 tok/s per request. That is within StudyX Part A's measured 28–39
   tok/s per request. KV reached 100% in every arm, with 67 / 54 / 1 preemptions (recompute). That changes batch
   composition, which StudyX already showed does not change a seeded attempt's outcome (86/89 agreement). Not a
   result here.
3. **Distribution sanity.** Terminating lengths range from 452–482 tokens up to 14,847–19,685 per arm, with no
   constants. Repetition
   rates spread 0.0–0.7 in terminating traces.
4. **Definitions.**
   - **Cap hit:** `completion_tokens` ≥ 24,576 AND no `</think>`, as StudyX.
   - **8-gram repetition:** the fraction of 8-token windows in the last 4,096 generated tokens (Qwen tokenizer)
     already seen earlier in that window.
   - **Pool:** StudyX `normal_signs()` (23).
5. **Claim linkage.**
   - **Supports:** natural non-termination is rare at recommended settings.
   - **Weakens:** treating StudyX's T0.6 cap-hit rate as the workload's rate.
   - **No bearing on:** the forced-resident tier cost (StudyX Part C).
6. **Proxy validity.** "Did not close within 24,576" stands in for "does not terminate". The card's budget is 40,960,
   so T1.0's single hit might have closed later. The rate is an upper bound for non-termination at 40,960.

## Caveats

- **n = 115 per arm** bounds rates only to about ±3–5 points. The T1.0 vs T0.6 difference is not significant on its
  own.
- **Seeds:** 5 per sign, the StudyX seeds (chosen for continuity, as pre-registered).
- **Workload:** one task (SiGNgapore2D signs). Other tasks may differ.
- **No accuracy:** answers are stored but not scored (accuracy was not part of 2a).

## Files

- **Code:**
  - `experiments/cost/study_x2a_natural.py` (vLLM venv; reuses `study_x_vllm.py` client and server)
  - `experiments/cost/study_x2a_analyse.py` (original `.venv`)
- **Data (`results/cost/study_x2a/`):**
  - `study_x2a_requests_h100nvl.jsonl.gz` (345 records with full text)
  - `study_x2a_{stamps,metrics}_h100nvl.jsonl.gz`
  - `study_x2a_run_meta_h100nvl.json` (server info, arms, provenance)
  - `study_x2a_results_h100nvl.json`
- **Logs:** `logs/queue3_*`, `logs/study_x_server_32BT_1017_095108.log`
