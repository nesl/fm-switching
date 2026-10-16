# StudyR — Device vs cloud tier on ERQA: does Instruct-vs-Thinking stay null at 32B? (h100nvl)

Status: **COMPLETE (2026-10-14).** Verdict: **THINKING DOES NOT PAY AT SCALE** (D−C spatial +2.5 pp,
95% CI [−5.1, +11.0]). The pre-registration block below is unchanged since before the first 32B trial;
results follow it.

Replaces the interrupted A6000 StudyR (BnB NF4, arm D at temp=1.0, 224/400 D trials). Those trials
remain in `results/erqa/study_r/study_r_trials.jsonl` and are **not** used here.

---

## Pre-registration (written 2026-10-14, before any 32B trial)

### Question
Does the Instruct-vs-Thinking null measured at 4B–8B (counting, SiGNgapore2D, ERQA, MV-RoboBench)
persist at 32B? Hypothesis under test: the vendor ladder's sign reversal on pointing/grounding
between 8B and 32B (RefSpatialBench −9.6 → +5.8; RoboSpatialHome −4.9 → +9.6) appears on ERQA's
spatial categories. (Vendor numbers as supplied in the study spec; not re-verified here.)

### Decision rule (verbatim)
"THINKING PAYS AT 32B if the 32B thinking effect (D−C) exceeds 5pp with a 95% paired CI excluding 0,
on the spatial subset. THINKING DOES NOT PAY AT SCALE if it does not. Report separately: size effect at
instruct (C−A), size effect at thinking (D−B), thinking effect at 4B (B−A), thinking effect at 32B (D−C),
total device-to-cloud gap (D−A)."

**The primary test is the thinking effect at 32B (D−C), not the total gap.** D−A is expected to be
positive from size alone and says nothing about reasoning.

### Arms
| arm | model | decoding | source |
|---|---|---|---|
| A | Qwen3-VL-4B-Instruct @ebb281ec | greedy, max_new_tokens=512 | REUSE StudyQ arm E (= StudyK INSTRUCT); A6000; `answer_text` not stored |
| B | Qwen3-VL-4B-Thinking @1de27d8c | CFG-A, max_new_tokens=**8192**, seed 42 once per arm | REUSE StudyQ arm A; A6000 |
| C | Qwen3-VL-32B-Instruct @0cfaf481 | greedy, max_new_tokens=512 | NEW, h100nvl |
| D | Qwen3-VL-32B-Thinking @7edd10ff | CFG-A, max_new_tokens=**16384**, `set_seed(42+qid)` | NEW, h100nvl |
| A_h100 (supplementary) | 4B-Instruct @ebb281ec | greedy 512 | NEW, h100nvl — **latency only**, for a same-hardware D/A ratio |

CFG-A = temperature 0.6, top_p 0.95, top_k 20, min_p 0, do_sample. **Deviation disclosed:** the
Qwen3-VL-Thinking model card recommends temperature 1.0; 0.6 is kept for cross-study consistency (StudyS0).

### Data
ERQA (RunsenXu/ERQA), 400 questions, identical to StudyK/StudyQ (category labels verified identical
for all 400). **Primary: spatial subset = Spatial Reasoning (84) + Pointing (34) = n = 118.**
Secondary: overall n = 400. Run order is spatial-first so the primary subset completes regardless of the
cost cut.

### Power (stated before running)
Paired discordance between B and A on the spatial subset is 20/118 = 16.9% (b=14, c=6); overall 27.3%.
At n=118:

| assumed discordance | 95% CI half-width | MDE (α=0.05, 80% power) |
|---|---|---|
| 0.17 (4B observed) | ±7.4 pp | 10.6 pp |
| 0.20 | ±8.1 pp | 11.5 pp |
| 0.35 | ±10.7 pp | 15.2 pp |

**The spatial subset is under-powered for a 5 pp effect.** Detecting 5 pp at 80% power needs n ≈ 530 at
17% discordance. Under the rule, an observed D−C must be at least ~7–11 pp for the CI to exclude 0, so a
true 5 pp effect will usually be classed as "does not pay". A "does not pay" verdict is therefore
**weak evidence of absence** unless the CI upper bound is itself below 5 pp.

### Statistics (fixed now)
- Accuracy CIs: Wilson 95%.
- Paired effects (all five decomposition terms): question-level paired bootstrap, 10,000 resamples,
  percentile 95% CI, rng seed 0; exact McNemar p and discordant counts b, c reported alongside.
- Parse failures (`no_letter`) are counted as incorrect for accuracy (as in StudyK/Q) **and** reported
  separately per arm; `last_found` parses are reported separately too.
- Random baseline 25% (4-option MCQ).

### Quantization decision (fixed rule)
Probe: 32B-Thinking in bf16, largest-input ERQA question, forced to generate exactly 16,384 tokens.
bf16 if peak reserved VRAM < 75 GB; otherwise BnB NF4 (nf4, compute bf16, double quant) for **both**
32B arms.

### Runtime rule
Projection after 10 trials of arm D. If the full 400 projects > 15 h, run the spatial subset only for D,
and report that the overall secondary analysis was dropped for cost. The spatial subset is never reduced.

### Known asymmetries and confounds (disclosed in advance)
1. **Budget**: B at 8,192 vs D at 16,384. D is additionally re-scored as if capped at 8,192
   to give a budget-matched D−B: for trials with `n_generated > 8192`, the stored raw output is
   re-tokenized, truncated to its first 8,192 tokens, and re-parsed with the same think-split and
   `extract_letter` used for B (an exact mirror of how B would have scored that trace).
2. **Hardware/stack**: A, B on A6000 (StudyQ stack); C, D on H100 NVL, transformers 5.10.2, SDPA
   attention (flash-attn not installed). Accuracy comparisons across stacks assume decoding is
   numerically equivalent; latency comparisons across stacks are not valid — the D/A latency ratio is
   reported with A_h100 (same hardware) as primary and reused-A only as a labelled cross-hardware figure.
3. **Decoding mode is confounded with thinking**: C greedy vs D sampled. D−C measures "thinking
   checkpoint + sampled decoding" vs "instruct checkpoint + greedy", exactly as B−A did at 4B.
4. **Single seed** for D: no seed-variance estimate; the paired CI covers question sampling only.
5. **Seeding scheme differs**: D seeds per question (resume-safe); reused B seeded once per arm.
6. Host is shared (`research/HOST_H100.md`); GPU 3 only; per-second monitor logged.

### Analyses
1. Accuracy per arm, n, Wilson CI, 25% baseline; spatial and overall separately.
2. Decomposition on spatial: C−A, D−B, B−A, D−C, D−A, each with paired CI.
3. Verdict in the exact form of the rule.
4. Termination rate and think-token distribution per thinking arm (B vs D); budget hits.
5. Latency per arm: median, p90; D/A ratio (A_h100 primary; reused A labelled cross-hardware).
6. Discordance b, c for D vs C and B vs A; reshuffling signature vs net gain.

Sanity checks: four distinct checkpoints + snapshot paths + quantization per arm; peak VRAM per arm;
transformers version; reused trials labelled with source and decoding; parse failures separate;
4B-I / 4B-T vs published 41.3 / 47.3.

---

## Results (run 2026-10-14, h100nvl, bf16)

### Verdict (pre-registered form)
**THINKING DOES NOT PAY AT SCALE.** The 32B thinking effect on the spatial subset (n=118) is
**D−C = +2.5 pp, 95% paired bootstrap CI [−5.1, +11.0]**, b=13 / c=10, McNemar p=0.68. It does not
exceed 5 pp and the CI includes 0.

This is **weak evidence of absence**, as the power section anticipated: the CI upper bound (+11.0 pp)
is above 5 pp, so a real effect of the vendor-table size (+6 to +15 pp) is not excluded at n=118.

### Decomposition — spatial subset (primary, n=118)
| term | diff pp | 95% paired CI | b (x✓y✗) | c (x✗y✓) | McNemar p |
|---|---|---|---|---|---|
| C−A size @instruct | +10.2 | [+0.0, +19.5] | 24 | 12 | 0.065 |
| D−B size @thinking | +5.9 | [−4.2, +16.1] | 22 | 15 | 0.324 |
| B−A thinking @4B | +6.8 | [+0.0, +14.4] | 14 | 6 | 0.115 |
| **D−C thinking @32B (PRIMARY)** | **+2.5** | **[−5.1, +11.0]** | **13** | **10** | **0.678** |
| D−A total device→cloud | +12.7 | [+3.4, +22.0] | 23 | 8 | 0.011 |

Secondary — overall (n=400, D complete):

| term | diff pp | 95% paired CI | b | c | McNemar p |
|---|---|---|---|---|---|
| C−A | +4.8 | [−1.0, +10.2] | 75 | 56 | 0.116 |
| D−B | +6.8 | [+1.5, +12.0] | 70 | 43 | 0.014 |
| B−A | +1.2 | [−4.0, +6.2] | 57 | 52 | 0.702 |
| D−C | +3.2 | [−1.5, +8.0] | 53 | 40 | 0.213 |
| D−A | +8.0 | [+2.2, +13.8] | 84 | 52 | 0.008 |

### Analysis 6 — discordance: reshuffling or net gain?
- **D vs C, spatial:** 23 of 118 answers change (19.5%); net +3 (b=13, c=10).
- **D vs C, overall:** 93 of 400 change (23.3%); net +13 (b=53, c=40).
- **B vs A, spatial:** 20 of 118 (16.9%); net +8. **Overall:** 109 of 400 (27.3%); net +5.
- At 32B, thinking keeps the **reshuffling signature** seen at 4B–8B: about a fifth to a quarter of
  answers change, the net is small and not significant on either subset. There is no evidence of a
  genuine net gain. The overall D−C point estimate (+3.2 pp) is positive but its CI includes 0.
- The only terms whose CIs exclude 0 are **D−A** (both subsets) and **D−B** (overall): the
  device-to-cloud gap is carried by **size**, not by thinking.

### Analysis 1 — accuracy (random baseline 25%)
| arm | spatial n=118 | 95% Wilson CI | overall n=400 | 95% Wilson CI | no_letter (sp / all) |
|---|---|---|---|---|---|
| A 4B-Instruct (reused, A6000) | 43.2 | [34.6, 52.2] | 42.0 | [37.3, 46.9] | 0 / 0 |
| B 4B-Thinking (reused, A6000, 8192) | 50.0 | [41.1, 58.9] | 43.2 | [38.5, 48.1] | 1 / 3 |
| C 32B-Instruct | 53.4 | [44.4, 62.1] | 46.8 | [41.9, 51.6] | 0 / 0 |
| D 32B-Thinking (16384) | 55.9 | [46.9, 64.6] | 50.0 | [45.1, 54.9] | 0 / 0 |
| A_h100 4B-Instruct (supplementary) | 41.5 | [33.0, 50.5] | 40.8 | [36.0, 45.6] | 0 / 0 |

Parse failures are scored wrong and listed separately; `last_found` = 0 for every arm. Every arm is
above the 25% baseline.

### Analysis 4 — termination and think tokens
| arm | subset | n | think closed | budget hits | think tokens median | IQR | p90 | max |
|---|---|---|---|---|---|---|---|---|
| B (4B, 8192) | spatial | 118 | 97.5% | 3 | 652 | 174–1698 | 3285 | 5964 |
| B | overall | 400 | 98.8% | 5 (1.2%) | 506 | 185–1168 | 2311 | 6583 |
| D (32B, 16384) | spatial | 118 | 100% | 0 | 364 | 153–894 | 2488 | 6704 |
| D | overall | 400 | 100% | 0 | 372 | 158–852 | 1874 | 7221 |

32B loops less than 4B: 0 budget hits vs 5 (1.2%), and about 45% shorter median traces. **Budget-matched
check:** no D trial exceeded 8,192 generated tokens, so re-scoring D at B's 8,192 budget changes 0 scores;
D−B and D−C are unchanged at a matched budget.

### Analysis 5 — latency (caching: none; HF `generate`, no prefix cache, one question at a time)
| arm | hardware | spatial median / p90 s | overall median / p90 s |
|---|---|---|---|
| A (reused) | A6000 | 0.18 / 0.36 | 0.17 / 0.31 |
| B (reused) | A6000 | 15.89 / 90.63 | 12.15 / 68.69 |
| C | H100 NVL | 0.24 / 0.44 | 0.23 / 0.41 |
| D | H100 NVL | 15.56 / 104.43 | 15.97 / 79.27 |
| A_h100 | H100 NVL | 0.08 / 0.13 | 0.08 / 0.12 |

**D/A median ratio, same hardware (A_h100, primary): 188× spatial, 200× overall.** Cross-hardware
(reused A on A6000, labelled): 87× / 93×. Thinking at 32B costs about two orders of magnitude in
latency for a non-significant +2.5 pp.

### Analysis 7 — 4B vs published (overall)
- A (4B-Instruct): 42.0% vs published 41.3% (+0.7 pp) — reproduces.
- B (4B-Thinking): 43.2% vs published 47.3% (−4.1 pp) — **does not reproduce**; inherited from the
  reused StudyQ arm A (CFG-A temp 0.6, 8192 budget, single seed vs the vendor's settings). Flagged, not
  reconciled here.

### Sanity checks
| check | result |
|---|---|
| checkpoints | 4B-I @ebb281ec, 4B-T @1de27d8c (reused), 32B-I @0cfaf481, 32B-T @7edd10ff — four distinct snapshots, all pinned |
| quantization | **bf16 for both 32B arms.** Probe peak reserved 76.85 GB > the 75 GB rule → the rule said NF4; **the user waived the rule** (card has ~94 GiB), recorded before any 32B trial |
| peak VRAM (reserved) | C 75.4 GB, D 75.7 GB, A_h100 13.4 GB; probe 76.85 GB |
| stack | transformers **5.10.2** (not 5.17.x; StudyS0 used 5.12.1), torch 2.8.0+cu128, SDPA |
| reused trials | A = StudyQ arm E (= StudyK INSTRUCT), B = StudyQ arm A; labelled `_reused_from`, A6000 |
| parse failures | reported separately above |
| hardware split | C and D trials 1–23 ran on **GPU 2** (18:59–19:19; GPU 3 then held another user's job); D trials 24–400 and A_h100 on **GPU 3** (from 19:20). Same SKU; D's per-question seeds make outputs GPU-independent. |
| contention | per-5-s process log: **no foreign process** on GPU 2 during our window or on GPU 3 after 19:20 → 0 trials excluded |
| GPU 3 monitor | 12,630 s logged; max 76 °C; busy-time SM clock median 1,785 MHz, min 585 MHz; SW-power-cap throttle in 223 of 12,506 busy seconds (1.8%); no thermal throttle |

### Results consistency check (CLAUDE.md)
1. **Cross-check against committed measurements.** A and B are the committed StudyQ trials (identical by
   construction). The new A_h100 rerun of the same greedy 4B-Instruct on H100/transformers 5.10.2 gives
   40.8% vs A's 42.0% (ratio 0.97); **14 of 400 predicted letters differ (3.5%)** between the two stacks
   despite greedy decoding. This is the size of the cross-stack numerical noise, and it bears on every
   term that pairs an A6000 arm with an H100 arm (C−A, D−B, D−A): about 3.5% of their discordant pairs could
   be stack, not model. It does not touch the primary D−C (same stack).
2. **Physical plausibility.** D decodes 372 median think tokens at ~16 s median ≈ 23–25 tok/s, matching
   the probe's 22.6 tok/s for 32B bf16. C answers in 2 tokens (max `n_generated` = 2) at 0.23 s. A_h100
   (4B) at 0.08 s. No rate is faster than measured curves.
3. **Distribution sanity.** Latency and think tokens reported with IQR/p90/max; no constant values.
4. **Definition audit.** "Spatial subset" = Spatial Reasoning (84) + Pointing (34) = 118, identical labels
   to StudyK/Q. "Budget hit" = generated == max_new_tokens without `</think>`. Same as StudyQ.
5. **Claim linkage.** This bears on the reasoning-tier feasibility line (StudyK/Q/S0), not on C1–C5 in
   `research/CLAIMS.md`: it **weakens** "a cloud reasoning tier is justified by thinking" and
   **supports** "the device-to-cloud gap on ERQA is a size gap". No CLAIMS.md entry is directly about
   thinking mode.
6. **Proxy validity.** ERQA spatial categories are used as a proxy for the vendor tables' spatial
   benchmarks (RefSpatialBench, RoboSpatialHome). They are different benchmarks, so "no reversal on ERQA
   spatial" does not contradict the vendor numbers; it says the reversal does not transfer here.

### Mechanism verification
1. **Causal chain.** Thinking can only help if (a) the thinking model produces a reasoning trace,
   (b) the trace terminates so an answer is produced, and (c) the trace changes answers. Size enters
   through the checkpoint.
2. **Instantiation.**

   | link | quantity | value | varies? |
   |---|---|---|---|
   | trace present | D `n_think_tokens` | median 372, IQR 158–852 (C: 0) | yes |
   | trace terminates | D `think_closed` | 100% (B: 98.8%) | yes vs 4B |
   | trace changes answers | D vs C discordance | 23.3% overall | yes |
   | scale | weights | 66.7 GB (32B) vs ~8.9 GB (4B) | yes |

   No link is ABSENT or CONSTANT: the null is a **real negative** at this n (Rule 2), not a design
   failure, with the power caveat above.
3. **Trace of one unit (q5, Action Reasoning, D):** 288 input tokens → 255 think tokens, `</think>` closed,
   259 generated, answer "A" (gold A, correct), 10.9 s, peak reserved 72.3 GB.
4. **Negative control.** The thinking mechanism cannot be switched off inside one checkpoint; C (same size,
   no thinking) is the contrast.
5. **Alternative explanation.** A small D−C gain could come from sampled vs greedy decoding (confound 3)
   rather than reasoning; with D−C non-significant this does not change the verdict.

### Files
- Trials: `results/erqa/study_r/study_r_trials_h100nvl.jsonl` (A 400 and B 400 reused; C, D, A_h100 400 each)
- Run meta: `results/erqa/study_r/study_r_run_meta_h100nvl.json`; VRAM probe: `study_r_vram_probe_h100nvl.json`
- Results JSON: `results/erqa/study_r/study_r_results_h100nvl.json`
- Scripts: `experiments/erqa/study_r_erqa.py`, `experiments/erqa/study_r_analyse.py`

---

## Flash-attn re-run (2026-10-15 10:15 → 2026-10-16 02:56, h100nvl GPU 3)

Arms C and D only (A/B are 4B and out of scope here); same 400 questions, same decoding, budgets, seeds and bf16
weights; only the attention backend changes. flash-attn 2.8.3 (`--no-deps`, + einops 0.8.2; torch 2.8.0+cu128 and
transformers 5.10.2 verified unchanged). Every load passed `attn_implementation="flash_attention_2"` and asserted
`model.config._attn_implementation == "flash_attention_2"`; the value is stored per trial (800/800). Order: spatial
subset first (10:15–12:02), the non-spatial rest last (23:59–02:56). A watchdog would have halted the run on any
foreign GPU-3 process: none appeared; 0 contended trials. Files: `study_r_trials_h100nvl_fa2.jsonl`,
`study_r_run_meta_h100nvl_fa2.json`.

**Expectation (stated before comparing):** the kernels are mathematically equivalent, so the greedy C arm should be
near-identical (≤ ~1 pp) and D should differ only by sampling noise.

### Side by side
| | SDPA (2026-10-14) | flash-attn (2026-10-15/16) |
|---|---|---|
| C spatial (greedy) | 63/118 = 53.4% | 62/118 = 52.5% (−0.8 pp; 2 letters changed) |
| C overall (greedy) | 187/400 = 46.8% | 187/400 = 46.8% (**0.0 pp**; 3 letters changed) |
| D spatial | 66/118 = 55.9% | 68/118 = 57.6% (flash-only right 4, SDPA-only right 2) |
| D overall | 200/400 = 50.0% | 195/400 = 48.8% (17 vs 22) |
| **D−C spatial (PRIMARY)** | **+2.5 pp [−5.1, +11.0]**, b=13 c=10 | **+5.1 pp [−2.6, +13.6]**, b=15 c=9 |
| D−C overall | +3.3 pp [−1.5, +8.0], b=53 c=40 | +2.0 pp [−2.8, +6.8], b=48 c=40 |
| **Verdict** | **THINKING DOES NOT PAY AT SCALE** | **THINKING DOES NOT PAY AT SCALE** |
| D think_closed / budget hits | 100% / 0 | 99.75% / 1 (1 `no_letter`) |
| D think tokens median | 372 | 343 |
| D latency median / p90 s | 16.0 / 79.3 | 19.2 / 86.9 |
| D peak allocated / reserved | 73.6 / 75.7 GB | 73.5 / 80.3 GB |

- **No verdict flip.** Both instruct-arm checks pass (−0.8 pp spatial, 0.0 pp overall).
- **⚠ Fragility flag:** under flash-attn the spatial point estimate is **+5.08 pp, above the 5 pp threshold**;
  the verdict stays "does not pay" only because the CI includes 0. The backend-to-backend swing of the primary
  (+2.5 → +5.1 pp) is sampling noise of the thinking arm (4 vs 2 discordant answers) plus one greedy letter on C,
  i.e. ±2–3 pp is the run-to-run noise floor of D−C at n=118. A 5 pp threshold sits inside that noise; the
  pre-registered rule's CI clause is what keeps the verdict stable.
- Reshuffling signature reproduced: thinking changes ~20% (spatial) / ~22% (overall) of answers with a small net.

### Backend mismatch (labelled)
Arms A and B (4B, reused from StudyQ) ran on the A6000 with **SDPA**. Under the flash-attn columns, **C−A, D−B and
D−A are BACKEND-MISMATCHED** until A/B are re-run with flash-attn on the A6000. The SDPA columns are backend-matched
(the A6000 `erqa/` family is SDPA; commit `d39aa58`), with the separately measured ~3.5% A6000-vs-H100 greedy noise.
The primary D−C is within-size and same-backend in each column: **clean**.
