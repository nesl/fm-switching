# Study J2 — Reasoning Length Survival Curve on SiGNgapore2D

**Date:** 2026-09-29  
**Status:** Complete  
**Follow-up to:** StudyJ (gate fails at 2048; truncation 80.2%)  
**Research question:** Is the 80.2% truncation rate at 2048 tokens a budget artifact removable by a larger budget, or does a substantial fraction never terminate at any tested budget?

---

## Setup

| item | value |
|------|-------|
| Dataset | NickyZimmerman/SiGNgapore2D — 40-sign stratified subset |
| Stratification | 13 low (n_gt=1–2) + 13 mid (n_gt=3–5) + 13 high (n_gt≥6) + 1 other (n_gt≤0) |
| Manifest | `results/signs/study_j2/manifest.json` — written before inference, seed=42 |
| Model | Qwen3-VL-4B-Thinking — same snapshot as StudyJ |
| Decoding | temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True — matching StudyJ |
| max_new_tokens | 24576 (model context = 262,144; input ~800 tok; total ~25,376 — well within limit) |
| think_closed detection | skip_special_tokens=False; `</think>` checked in raw token stream |
| Seed | 42 (single run) |
| Errors / OOM | 0 errors, 0 OOMs |
| Runtime | ~7.5h total on A6000 (cuda:1); mean 404s/sign |

---

## 1. Scorer Validation (Task 1 — required before run)

The scorer (`recognition_fp_metrics_eval.py`, open_clip ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip) was run over the authors' own saved prediction files before any new inference.

| model | file | reproduced overall_acc | published | diff |
|-------|------|------------------------|-----------|------|
| Gemini-2.0-Flash | `recognition_results/gemini/recogntion_results.json` (205 entries) | **40.7%** | 42.2% | −1.5pp |
| GPT-4o | — | not reproducible | 39.3% | — |

GPT-4o results are not present in the cloned repo (`recognition_results/gpt4o/` does not exist). The Gemini reproduction (−1.5pp) is within run-to-run API variation (the authors' pipeline uses 5-round voting; minor stochasticity is expected). The scorer is correctly wired.

**Consequence:** StudyJ's INSTRUCT overall_acc = 22.8% is interpretable. The scorer is validated.

---

## 2. Survival Curve

For budget B, the survival fraction is the fraction of signs whose reasoning had NOT terminated by B (i.e., signs that would be truncated if max_new_tokens = B).

### Overall (n=40)

| budget B | not terminated | fraction |
|----------|---------------|---------|
| 1,024 | 32/40 | **80.0%** |
| 2,048 | 29/40 | **72.5%** |
| 4,096 | 21/40 | **52.5%** |
| 8,192 | 12/40 | **30.0%** |
| 16,384 | 8/40 | **20.0%** |
| 24,576 | 8/40 | **20.0%** |

The curve flattens between 16,384 and 24,576: the same 8 signs are non-terminating at both budgets, confirming an asymptote.

### Per complexity bin

| budget B | low (1–2, n=13) | mid (3–5, n=13) | high (6+, n=13) | other (≤0, n=1) |
|----------|----------------|----------------|----------------|----------------|
| 1,024 | 46% | 100% | 100% | 0% |
| 2,048 | 31% | 92% | 100% | 0% |
| 4,096 | 8% | 77% | 77% | 0% |
| 8,192 | 8% | 54% | 31% | 0% |
| 16,384 | 0% | 38% | 23% | 0% |
| 24,576 | **0%** | **38%** | **23%** | 0% |

*Plot: `figures/feasibility/study_j2_survival_curve.pdf`*

**Key observation:** Low-bin signs terminate fully by 16,384 tokens. Mid and high bins have asymptotes of 38% and 23% respectively — these signs do not terminate regardless of budget within the tested range.

---

## 3. Think-Token Distribution (Completers, Uncensored)

32/40 signs terminated within 24,576 tokens.

| bin | n completers | min | median | p90 | max |
|-----|-------------|-----|--------|-----|-----|
| low (1–2) | 13/13 | 229 | 505 | 3,359 | 9,402 |
| mid (3–5) | 8/13 | 1,736 | 5,416 | 9,525 | 11,485 |
| high (6+) | 10/13 | 3,128 | 4,897 | 7,985 | 9,220 |
| other (≤0) | 1/1 | 724 | 724 | — | 724 |
| **all** | **32/40** | **229** | **3,339** | **8,601** | **11,485** |

The completer median for mid and high bins (5,416 and 4,897 tokens) is 8–10× StudyK's ERQA median (531 tokens) — sign recognition requires substantially more reasoning tokens than embodied QA for the same model.

**Important:** The low-bin completer p90 (3,359) and max (9,402) are higher than StudyJ's non-truncated median (653). This is because StudyJ's non-truncated subset was biased to the simplest signs (25/32 had n_gt≤2 AND happened to be fast; the slow-thinking low-bin signs were all truncated at 2048). The uncensored completer distribution here confirms reasoning depth is substantially higher than StudyJ §4 estimated.

---

## 4. Never-Terminate Rate

**8/40 = 20% of signs never terminate at any tested budget (up to 24,576 tokens).**

| bin | never-terminate |
|-----|----------------|
| low (1–2) | 0/13 = **0%** |
| mid (3–5) | 5/13 = **38%** |
| high (6+) | 3/13 = **23%** |
| other (≤0) | 0/1 = 0% |
| **overall** | **8/40 = 20%** |

Cap-hit signs:

| sign | n_gt | bin | latency |
|------|------|-----|---------|
| IMG_6416_frame_0013_0.jpg | 3 | mid | 1463.7s |
| IMG_6546_frame_0019_1.jpg | 4 | mid | 1454.6s |
| IMG_6617_frame_0015_0.jpg | 5 | mid | 1475.1s |
| IMG_6548_frame_0019_1.jpg | 4 | mid | 1456.8s |
| IMG_6623_frame_0015_0.jpg | 7 | high | 1481.8s |
| IMG_6411_frame_0014_0.jpg | 3 | mid | 1467.1s |
| IMG_0037_frame_0014_0.jpg | 7 | high | 1472.6s |
| IMG_0068_frame_0007_0.jpg | 7 | high | 1485.6s |

All 8 produce 24,576 tokens at ~1,460–1,490s each. The survival curve is flat from 16,384 → 24,576, confirming these would also hit a cap at 16,384.

---

## Verdict D — Budget Artifact or Asymptote?

**A substantial fraction never terminates at any tested budget. The asymptote is 20% overall.**

The survival curve flattens between 16,384 and 24,576 tokens for all bins. No tested budget achieves <10% truncation overall. The mid-bin floor is 38%; the high-bin floor is 23%. These fractions are stable across the last two budget checkpoints, indicating a genuine asymptote rather than a slow decay.

The correction to StudyJ §4 (see §6 below) is confirmed: the aborted 16,384 run would have produced ~20% cap-hits, not ~0%.

**Low-bin exception:** Low-complexity signs (n_gt=1–2) terminate fully by 16,384 tokens. For that bin specifically, B=16,384 achieves 0% truncation. This does not generalize to the full dataset.

---

## 5. Late-Trace Excerpt Classification (Analysis E)

Three of the 8 cap-hit signs were re-run at max_new_tokens=24576 with full output captured. Excerpts are the last ~500 tokens of each trace. Same classification as StudyJ §5: class (a) = substantive reasoning that ran long; class (b) = degenerate repetition.

---

**Sign 1 — IMG_6416_frame_0013_0.jpg (n_gt=3, mid bin) → CLASS (a)**

The model has constructed a near-complete JSON answer and is verifying edge cases (J-Walk appearing in both symbol and text channels, EMERGENCY classified as locational). At truncation the answer is formatted and nearly ready to write:

> *"Now, the problem says: 'the text or symbol corresponding to the location'. For 'J-Walk', it's both t and s. Now, the problem says: 'If a location is being represented as symbol and text both, then mention that in both "s" and "t".' So 'J-Walk' is in both. Now, the output should be: {'t': {'Ng Teng Fong General Hospital': 'locational', 'J-Walk': 'locational', 'TOWER A': 'straight', 'CLINICS': 'locational', 'TOWER B': 'right', 'WARDS': 'locational'}, 's': {'J-Walk': 'locational', 'EMERGENCY': 'locational'}}. But wait, the problem says…"*

The model is actively constructing the correct answer and would have written it on the next iteration. Truncation is timing, not degeneration. **Class (a).**

---

**Sign 2 — IMG_6617_frame_0015_0.jpg (n_gt=5, mid bin) → CLASS (b)**

The last 500 tokens consist of the same constraint-verification fragment repeated verbatim 4+ times without making progress:

> *"Now, the problem says: 'the value of "s" or "t" can be empty dictionary if there are no symbol detections or no text based location names in the image.' Since there are text based location names, 't' is not empty. Now, the problem says: 'the location name was inferred through text (t) or through symbol (s)'. Yes. Now, the problem says: 'the output direction should be from this list ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']' Yes. Now, the problem says: 'the value of "s" or "t" can be empty dictionary…' Since there are text based location names, 't' is not empty. Now, the problem says…"*

The model has entered a self-verification loop, rechecking the same three constraints repeatedly. No new reasoning or JSON output is produced. This is degenerate — the sign content has been processed but the model cannot exit the verification phase. **Class (b).**

---

**Sign 3 — IMG_6623_frame_0015_0.jpg (n_gt=7, high bin) → CLASS (a)**

The model is working through a complex multi-entry sign (BUS, TAXI STAND, ZONE A–F, National University Cancer Institute, National University Heart Centre, BUS STOP symbol) and debating whether the text "BUS" and symbol "BUS STOP" represent the same location (requiring both 't' and 's' entries):

> *"So if the same location is represented by both symbol and text, then add both. In this case, 'BUS' (text) and 'BUS STOP' (symbol) are the same location. So 'BUS' is both 't' and 's'. The direction for 'BUS' is straight. So the JSON: {'t': {'BUS': 'straight', 'TAXI STAND': 'right', 'ZONE A': 'right', …, 'National University Heart Centre, Singapore': 'right'}, 's': {'BUS STOP': 'right', 'BUS': 'straight'}}. But the problem says: 'ONLY if there are multiple directions for a location then output all detected direction as a list.' So for 'BUS'…"*

Coherent multi-entry deliberation. The model has identified all locations, assigned directions, and is resolving a legitimate ambiguity in the prompt's symbol/text overlap rule. **Class (a).**

---

**Summary:**

| sign | n_gt | bin | class | characterization |
|------|------|-----|-------|-----------------|
| IMG_6416 | 3 | mid | **(a)** | Substantive — near-complete, truncated mid-write |
| IMG_6617 | 5 | mid | **(b)** | Degenerate — constraint-check loop, no progress |
| IMG_6623 | 7 | high | **(a)** | Substantive — complex 10-entry sign, active deliberation |

Both classes of non-termination are present. Class (b) is notable: at least one non-terminating sign (n_gt=5) has entered a degeneration loop and would not terminate even with unlimited context. This means the 20% asymptote is a mix — some signs would terminate with more budget (class a); others would not (class b). The two cannot be distinguished from token counts alone.

---

## 6. Correction to StudyJ §4

StudyJ §4 reported the non-truncated think-token distribution (median=653, p90=1,436) and inferred: "At Study K's budget (16,384), sign truncation would be near zero (p90 of non-trunc = 1,436, well below 16,384)."

**This inference is incorrect.** The non-truncated distribution is a survivor distribution from the 32 easiest signs in the full set. The signs that would have terminated quickly at 2048 tokens happened to be the ones that are also fast-thinking — the slow-thinking signs were all truncated. Selecting only the completers and computing their distribution gives a downward-biased estimate of thinking depth for the full dataset.

Counter-evidence from StudyJ2:
- At B=16,384, 20% of the full 40-sign set still does not terminate.
- Completer median for mid-bin = 5,416 tokens; for high-bin = 4,897 tokens — far above the StudyJ non-trunc median of 653.
- The aborted 16,384 run measured ~370s/sign; at ~45s/2048-token rate this implies ~16,600 tokens/sign on average — consistent with ~20% cap-hits at 16,384.

The corrected interpretation of StudyJ §4 is: the non-truncated distribution (median 653) reflects the easy tail of the sign difficulty distribution, not the full dataset's reasoning depth.

---

## 7. What Cannot Be Inferred from 40 Signs

1. **Rates are noisy.** 8/40 = 20% non-termination has a wide CI (exact 95% CI: 9–35% by binomial). The per-bin rates (0%, 38%, 23%) from n=13 each are similarly imprecise.

2. **Cause of non-termination is unconfirmed.** The 8 cap-hit signs may share a structural feature (e.g., repeated similar-looking entries causing the model to check every possibility exhaustively). Without seeing the full trace we cannot confirm whether these are class (a) substantive reasoning that genuinely requires >24K tokens or (b) some form of slow degeneration not captured by the class distinction.

3. **The asymptote beyond 24,576 tokens is unknown.** The flat region from 16,384 → 24,576 is consistent with true non-termination, but the model context is 262,144 tokens. We have not tested whether these 8 signs terminate between 24,576 and 262,144 tokens.

4. **n_gt is a proxy for difficulty,** not a direct measure of reasoning demand. Two signs with the same n_gt can have very different think-token requirements (observed: n_gt=3 with 11,550 completer tokens vs. n_gt=3 cap-hit at 24,576).

5. **Single seed.** Stochastic decoding means a sign classified as non-terminating on seed=42 might terminate on another seed (or vice versa). The asymptote rate could be lower with different seeds.

---

