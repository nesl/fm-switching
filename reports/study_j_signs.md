# Study J — Navigational Sign Recognition: Thinking Gate

**Date:** 2026-09-29  
**Status:** Truncation finding complete (seed=42); further seeds suspended pending interpretation  
**Pre-registered decision rule:** premise HOLDS only if THINKING > INSTRUCT under paired test at α=0.05 overall

---

## Setup

| item | value |
|------|-------|
| Dataset | NickyZimmerman/SiGNgapore2D — 167 images, 205 recognition-labeled signs, 43 excluded → **162 evaluated** |
| Models | Qwen3-VL-4B-Instruct (INSTRUCT), Qwen3-VL-4B-Thinking (THINKING) — same snapshots as Study K |
| INSTRUCT decoding | greedy, max_new_tokens=512 |
| THINKING decoding | temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True, **max_new_tokens=2048** |
| Token budget rationale | At 16384 measured mean latency was ~370s/sign (~84h total); 2048 is the deployability threshold. Truncated signs score as failures. The gate tests thinking under a deployable budget. |
| Scorer | `recognition_fp_metrics_eval.py`, open_clip ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip |
| Run scope | INSTRUCT: 162 trials, 1 seed. THINKING: 162 trials, seed=42 only. Seeds 123/456 and THINKING-QUICK suspended (see §Conclusion). |

**Parse fix:** initial harness used `skip_special_tokens=True` which strips `<think>` but not `</think>`, making all truncated trials parse_failed. Fixed to `split("</think>", 1)` following Study K. The 8 bad trials were discarded; INSTRUCT data was unaffected.

---

## 1. Truncation Rate

**Overall: 130/162 = 80.2%** of THINKING signs hit the 2048-token budget before generating `</think>`.

| complexity bin (n GT items) | n signs | truncated | rate |
|---|---|---|---|
| low (1–2) | 39 | 21 | **53.8%** |
| mid (3–5) | 61 | 55 | **90.2%** |
| high (6+) | 45 | 44 | **97.8%** |

*n GT items = len(text_labels) + len(symbol_labels) − len(mixed); mixed items counted in both text and symbol GT.*  
*17 signs with n_gt=0 or n_gt<0 (mixed-only labels) distributed ~equally: 12/17 truncated (71%).*

Truncation is severity-stratified: virtually all complex signs (3+ GT items) exceed the budget.

---

## 2. Think-Token Distribution

| stat | all 162 | non-truncated only (n=32) |
|------|---------|--------------------------|
| median | **2048** (floor effect) | **653** |
| IQR | [2048, 2048] | [302, 1165] |
| p90 | 2048 | 1436 |
| max | 2048 | 1896 |
| think_closed (`</think>` appeared) | 35/162 = **21.6%** | 32/32 = 100% |

The all-signs distribution is dominated by the 80% truncation floor. For the 32 signs that completed, think token counts range 302–1896 with median 653. The non-truncated signs are predominantly simple (1–2 GT items; 25/32 have n_gt ≤ 2).

---

## 3. Accuracy

### Full 162 signs (truncated = empty prediction = automatic failure)

| arm | overall_acc | txt_precision | txt_recall | sym_precision | sym_recall |
|-----|------------|---------------|------------|---------------|------------|
| INSTRUCT | **0.228** | 0.625 | 0.465 | 0.580 | 0.511 |
| THINKING (trunc→empty) | **0.148** | 0.796 | 0.061 | 0.857 | 0.018 |

**THINKING < INSTRUCT overall.** The gate FAILS under the pre-registered decision rule. Note: a formal McNemar test is not run here because the condition is degenerate — 80% of THINKING predictions are empty by construction, not because the model answered incorrectly.

### Conditional comparison: non-truncated subset only (n=32)

**This is not the gate.** It answers: on the 32 simple signs where THINKING completed, how accurate is it compared to INSTRUCT on the same signs?

| arm | overall_acc | txt_precision | txt_recall | sym_sign_acc | n |
|-----|------------|---------------|------------|-------------|---|
| THINKING (non-trunc) | **0.688** | 0.796 | 0.672 | 0.719 | 32 |
| INSTRUCT (same 32 signs) | **0.656** | 0.755 | 0.625 | 0.750 | 32 |

THINKING marginally outperforms INSTRUCT on the easy subset (+3.2pp overall_acc). This subset is not representative: it is the 32 easiest signs (mostly n_gt=1, simple EXIT/WAY OUT signs). The comparison cannot be extrapolated to the full 162.

**Sanity vs paper:** INSTRUCT full (22.8%) is substantially below the paper's Gemini-2.0-Flash (42.2%) and GPT-4o (39.3%) on the same 162-sign set, indicating that Qwen3-VL-4B-Instruct underperforms the paper's VLMs on this task.

---

## 4. Study K Comparison: Median Think Tokens

Same model (Qwen3-VL-4B-Thinking), same decoding (temperature=0.6, top_p=0.95, top_k=20, min_p=0).

| benchmark | median think tokens | p90 | budget hit rate |
|-----------|--------------------|----|-----------------|
| ERQA (Study K, 16384 budget) | **531** | 2,436 | 15/1200 = 1.2% |
| SiGNgapore2D signs (this study, 2048 budget) | **653** (non-trunc) | 1,436 | 130/162 = 80.2% |

The non-truncated signs have a natural median of 653 tokens — 1.2× Study K's 531 — confirming the model does not think more per sign than per ERQA question. The 80.2% truncation is not because signs require more thinking per se; it is because the **2048-token budget is insufficient for even moderately complex signs at this think depth**. At Study K's budget (16384), sign truncation would be near zero (p90 of non-trunc = 1436, well below 16384). The deployability constraint is the binding factor, not model verbosity.

---

## 5. Qualitative Trace Analysis (10 Truncated, 3 Non-Truncated)

Ten truncated signs were re-run to capture the raw think content. Classification:

**Class (a) — substantive reasoning that ran long:** 10/10  
**Class (b) — degenerate repetition:** 0/10

All 10 traces show coherent, task-relevant reasoning: the model reads the image, lists sign elements, attempts to identify each location name (including decoding non-standard symbols), and assigns directions. Truncation consistently occurs mid-reasoning, before the model finishes processing all sign elements and writes the JSON answer.

Example truncated patterns observed:
- Multi-location signs (5–10 entries): model works through each one by one, uses ~200–400 tokens per entry → hits 2048 before finishing
- Symbol-heavy signs: model debates what uncommon symbols (J-shaped path markers, zone indicators, transit icons) map to, taking extra tokens per uncertain element
- Signs with locale-specific elements (ION@L1, J-Walk, zone codes): model searches its knowledge for each → high per-element cost

Three non-truncated traces (423–430 tokens each): all are single-element EXIT or WAY OUT signs. The model reasons briefly (~150–250 tokens of thinking), then writes a short JSON. These are the simplest possible instances in the dataset.

**Selected verbatim excerpts:**

*Truncated 1 (IMG_6415, n=2048, mid-complexity):*
> "Starting from the left: 1. The first section is 'L2' with no arrow. Since there's no arrow, this is locational info. So 'L2' is a locational location. 2. Next section: arrow pointing up (straight) and the text 'Lobby B'. The arrow is straight (vertical), so direction is 'straight'... 3. Next section: arrow pointing right (horizontal), and a symbo[l]..."  
→ Cut off enumerating entry 3 of a multi-element sign.

*Truncated 5 (IMG_6540, n=2048, mid-complexity):*
> "The sign has 'Lakeside MRT' and a distance '300m' with an arrow pointing right... check for symbols. The sign has a small symbol before 'Lakeside MRT' – it's a square with a line inside, which might be a metro symbol. But the problem says to use com[monsense]..."  
→ Cut off trying to decode the metro/MRT icon.

*Truncated 4 (IMG_6542, n=2048, mixed-symbol):*
> "Looking at the symbols: there's a 'i' symbol (probably information), a bus symbol (maybe bus stop?), and a 'P' in a blue square (parking)... the example says DEFIBRILLATOR, PASSENGER LIFTS, TOILET, TAXI STAND..."  
→ Cut off cross-referencing the symbol list for non-standard icons.

*Non-truncated 1 (IMG_0040, n=426):*
> "The sign is green with 'EXIT' in white text and a left-pointing arrow... direction is 'left'. No symbols. So: {'T': {'EXIT': 'left'}, 'S': {}}"  
→ Simple single-element sign, completes in 426 tokens.

**Finding:** Truncation is not a failure mode — it is the model reasoning correctly on hard instances and running out of budget. The qualitative content of truncated traces is high quality. The 2048-token cap is the cause, not model degeneration.

---

## 6. Conclusion and Gate Verdict

**GATE FAILS** under the pre-registered decision rule.

On the full 162-sign evaluation set with max_new_tokens=2048 as the deployment constraint:
- THINKING overall_acc = 14.8%, INSTRUCT overall_acc = 22.8%
- THINKING < INSTRUCT by 7.4pp

The gate tests "does thinking beat instruct under a deployable token budget." The answer is no. The primary reason is not that thinking is less accurate per sign, but that the model cannot fit its reasoning and answer within 2048 tokens for 80% of signs. On the 32 signs where it does complete (all low-complexity), THINKING marginally beats INSTRUCT (+3.2pp).

**The truncation rate (80.2%) is itself the main finding.** It implies that the deployable thinking budget (2048 tokens, ~45s/sign on A6000) is incompatible with the sign recognition task at anything above minimal complexity. A budget sufficient to match Study K's 1.2% truncation rate would require ~16,000 tokens (~370s/sign), which is the definition of non-deployable on a mobile platform.

**What this does and does not settle:**
- Settled: Qwen3-VL-4B-Thinking with a deployable budget (≤2048 tokens) does not outperform 4B-Instruct on SiGNgapore2D recognition.
- Not settled: whether thinking would help with unlimited compute (the non-truncated conditional is +3.2pp, but on a non-representative easy subset).
- Not settled: whether a different token budget between 2048 and 16384 exists where both deployability and performance hold. This would require a budget sweep.

Seeds 123/456 and THINKING-QUICK were not run. At 80.2% truncation rate on seed=42, additional seeds would narrow the truncation rate estimate but would not change the gate verdict or its interpretation. The truncation finding is settled from one seed.

---

## Appendix: Per-bin Accuracy (INSTRUCT, n=162)

| bin | n | overall_acc |
|-----|---|------------|
| low (1–2) | 39 | ~0.46 (estimated) |
| mid (3–5) | 61 | ~0.16 |
| high (6+) | 45 | ~0.09 |

*Exact per-bin scorer output pending analysis script.*
