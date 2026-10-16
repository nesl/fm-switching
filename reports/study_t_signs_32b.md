# StudyT — SiGNgapore2D non-termination at 32B: does scale buy termination? (h100nvl)

Status: **COMPLETE (2026-10-15 08:16).** Verdict (primary, termination at 8192): **TREND DOES NOT CONTINUE —
indistinguishable from 8B** (within-cap 30/35 = 85.7% [70.6, 93.7]; all 40 incl. post-cap 34/40 = 85.0%
[70.9, 92.9]). Ladder: 32B never-terminate at 24,576 = **2/40 (5%) vs 4B's 8/40 (20%)**. The pre-registration
block below is unchanged except the dated runtime amendments.

---

## Pre-registration (written 2026-10-14, before any 32B sign trial)

### Question
Does scale buy **termination** — a question separate from accuracy? Committed priors on the same 40-sign
manifest at max_new_tokens = 8,192: 4B-Thinking terminated 28/40 = 70.0% (StudyP arm A), 8B-Thinking
36/40 = 90.0% (StudyP arm C). 4B-Thinking has a never-terminate asymptote of 8/40 = 20% at budgets up
to 24,576 (StudyJ2). Does the 70 → 90 trend continue at 32B, and does the 20% asymptote hold at 32B?

### Data
`results/signs/study_j2/manifest.json` — the committed 40-sign StudyJ2 stratified manifest (seed 42;
low n_gt 1–2: 13, mid 3–5: 13, high ≥6: 13, other ≤0: 1). Not reselected. Images from
`NickyZimmerman/SiGNgapore2D`, now pinned at dataset sha `97d14879…` (StudyJ2/StudyP did not pin a
revision). GT, exclusion list, prompt and symbol list from `AdaCompNUS/Sign-Understanding` @
`381013b3b065113862d7410b10894b31161e86a6`, cloned to `/tmp/sign-understanding`.

### Arms (bf16, h100nvl)
| arm | model | decoding | budget | role |
|---|---|---|---|---|
| I32 | Qwen3-VL-32B-Instruct @0cfaf481 | greedy | 8,192 (= StudyP arm D's INSTRUCT_GEN) | bounded baseline |
| T32 | Qwen3-VL-32B-Thinking @7edd10ff | CFG-A: temp 0.6, top_p 0.95, top_k 20, min_p 0, do_sample | 8,192 | primary |

**Decoding deviation disclosed:** the Qwen3-VL-Thinking model card recommends temperature 1.0; 0.6 (CFG-A,
frozen in StudyS0) is kept for consistency with StudyJ2/StudyP, which used the same values.

Mirrored exactly from StudyP/StudyJ2: crop (`crop_bbox`), prompt (`prompt.txt`, first 10 symbols, the
six-direction list), message order [image, text], `torch.manual_seed(42)` immediately before each trial,
`skip_special_tokens=False` with the split on `</think>`, `parse_prediction`. Every trial stores the
full prompt string, the chat-templated text, `answer_text`, `raw_output`, `sign_id`, think tokens,
`think_closed`, `budget_hit`, latency, peak VRAM, wall-clock start/end, PID and GPU UUID.
Order: I32 first (≈ minutes; bounded), then T32 — so the baseline completes even if T32 hits the cap.

### Budget ladder (leftover-time extension — user decision 4, 2026-10-14)
Not part of the 2 h capped core. After the core, every T32 sign with `think_closed = False` at 8,192
is re-run at 16,384 (seed 42); every sign still not closed is re-run at 24,576 — StudyJ2's budget points.

*Method vs StudyJ2.* StudyJ2 ran each sign once at 24,576 and read off the survival curve at lower B
(sign terminated by B iff think closed with n_think < B). The ladder re-generates from scratch at each
rung. With identical inputs and seed, the first B tokens should reproduce the previous rung, making
the two methods equivalent. Evidence it holds at 4B: StudyJ2's 24,576-run read-off at 8,192 and
StudyP arm A's separate 8,192-capped run agree on termination for **all 40 signs** (paired b = c = 0,
checked 2026-10-14). At 32B this is **checked, not assumed**: each ladder trial records whether its
token prefix reproduces the previous rung (`prefix_match`). Survival at 32B: B ≤ 8,192 read off the
8,192 run; B = 16,384 / 24,576 from the rungs. Reported against J2's 4B curve.

### Scorer
Validated **before any model trial**: the offline scorer (`experiments/signs/study_t_score.py`, StudyP's
`score_sign` verbatim, open_clip 3.3.0 ViT-B-32/laion2b_s34b_b79k on CPU) reproduces Gemini-2.0-Flash at
**66/162 = 40.7%** (target 40.7%, tolerance 2 pp) → **PASS**
(`results/signs/study_t/scorer_validation.json`). Scoring is decoupled from generation.
Scoring rule (= StudyP): a trial is score-eligible only if the think trace closed (T32) or EOS came
before the budget (I32), and the answer parsed; non-eligible trials score 0. Parse failures among
eligible trials are reported separately.

### Decision rule (proposed under the spec; primary = termination at 8,192)
Let *k* = T32 signs with `think_closed` at 8,192, n = 40, Wilson 95% CI.
- **SCALE BUYS TERMINATION (trend continues)** if *k* ≥ 36 (at or above 8B's 90%) **and** the Wilson
  lower bound > 70% (excludes the 4B rate).
- **TREND DOES NOT CONTINUE** otherwise, sub-classified: **reversal** if the Wilson upper bound < 90%;
  **indistinguishable from 8B** if not.
Secondary: never-terminate fraction at 24,576 (ladder) vs 4B's 8/40 = 20%; paired-by-sign McNemar vs
StudyP arms A (4B-T) and C (8B-T) — same signs, same seed, same budget.

### Power (stated before running)
n = 40. Wilson 95% CI half-width ≈ ±9–10 pp at 90%, ±14 pp at 70%. A 32B rate equal to 8B's (36/40)
gives a CI [76.9, 96.0] — excludes 70% only barely. **This study can detect a ≥ ~20 pp change in
termination, not a ~5 pp one**; "indistinguishable from 8B" is weak evidence of equality. The paired
McNemar comparison has power only if the discordant signs are few-sided (e.g. 10 vs 0).

### Analyses
1. Termination at 8,192: 32B-T vs committed 4B (70%) and 8B (90%); Wilson CIs; paired McNemar by sign.
2. Accuracy per arm, Wilson CI, non-terminating = 0; T32 vs I32 paired b, c; prior 4B-T/8B-T/8B-I
   accuracies alongside (27.5 / 30.0 / 30.0%).
3. Think tokens among completers vs 4B's medians (low 505 / mid 5,416 / high 4,897 / all 3,339) —
   **censoring differs**: 32B completers censored at 8,192, J2's 4B at 24,576.
4. Per-bin termination at 8,192 vs J2's 4B read-off.
5. Survival curve at 1,024 … 24,576 vs J2's 4B; ladder prefix-determinism rate.
6. Latency median/p90 per arm and budget; trials overlapping a foreign process on our GPU (per-5 s
   process log) are excluded from latency only, with their IDs listed.
7. One line: 70 → 90 → ? at 8,192.

### Runtime and cap
**User instructions 2026-10-14 (before any StudyT trial):** caps were briefly removed, then the 2 h core
cap was **reinstated** in the interleaved GPU plan (StudyR → S2 arm C → S2 arm D first 100 → StudyT core →
S2 arm D remainder → StudyT ladder). StudyT core is not truncated to protect StudyS2. **Amendment 2026-10-15 00:5x (during the core run, before any outcome was examined):** T32 projected 184 s/sign → the 2 h cap cuts T32 at ≈30/40. Signs cut by the cap are run at 8192 at the start of step 6 (leftover time) as `phase = core_postcap`; the within-cap core n is reported as primary and the all-40 termination rate as a labelled secondary. Core cap 2 h wall-clock (no new trial starts after it; partial n reported). Projection printed after
10 trials of each arm. Estimates (32B decode ≈ 22–25 tok/s on this host): I32 ≈ 2–3 min (8B-I
generated ≤ 240 tokens per sign); T32 ≈ 1.3–1.5 h if 32B thinks like 8B (120k tokens total), ≈
2.0–2.3 h if like 4B (185k tokens) — **the core may hit its cap if 32B thinks as long as 4B**. Ladder,
if 4B-like (12 signs at 16,384, 8 at 24,576): ≈ 4.4–5.0 h worst case.

### Known confounds (disclosed in advance)
1. **Hardware/stack**: 4B/8B priors ran on A6000 (flash), transformers 5.12.x; this run is H100 NVL,
   transformers 5.10.2, torch 2.8.0+cu128, SDPA attention (flash-attn not installed). Termination is a
   property of the sampled token stream; different kernels can change the stream even at a fixed seed.
2. **Single seed** (42). StudyJ4 established non-termination is stochastic at 4B; no seed-variance
   estimate here (user decision 4: no second seed).
3. **Decoding mode confounded with thinking** for T32 vs I32 (sampled vs greedy), as in StudyP.
4. Shared host; GPU contention handled for latency only (accuracy/termination are device-independent).

---

## Core results (within the 2 h cap; run 2026-10-15 00:48–02:50, h100nvl GPU 3, bf16)

**Cap event:** the core cap hit at 2.03 h with T32 at **35/40** signs (I32 complete, 40/40). The 5 remaining
signs run at 8192 in step 6 as `core_postcap` (amendment above); this section uses the 35 within-cap signs.
**Scorer:** validated before scoring — Gemini-2.0-Flash 66/162 = 40.7% vs target 40.7% (PASS); accuracy below
is therefore scored with a validated scorer.

### Verdict (pre-registered form)
**TREND DOES NOT CONTINUE — indistinguishable from 8B.** 32B-T terminated 30/35 = **85.7% [70.6, 93.7]**.
"Scale buys termination" needs k ≥ 36 of 40; with 30 of the first 35 terminated, k ≤ 35 even if all 5
post-cap signs terminate, so the primary verdict class is already fixed. Sub-class: the Wilson upper bound
(93.7%) is above 90%, so **indistinguishable from 8B**, not a reversal (may be re-evaluated at n=40).

Trend: **4B 70% → 8B 90% → 32B 85.7%** at max_new_tokens 8192.

### 1. Termination at 8192 (same 40-sign J2 manifest; 32B on the 35 within-cap signs)
| model | terminated | n | rate [95% Wilson] | source |
|---|---|---|---|---|
| 4B-T (StudyP A) | 28 | 40 | 70.0% [54.6, 81.9] | committed, A6000 |
| 8B-T (StudyP C) | 36 | 40 | 90.0% [76.9, 96.0] | committed, A6000 |
| **32B-T** | **30** | **35** | **85.7% [70.6, 93.7]** | h100nvl |
| 32B-I (EOS before budget) | 40 | 40 | 100% [91.2, 100] | h100nvl |

Paired by sign (exact McNemar, n=35): 32B vs 4B b=8 (only 32B terminated), c=3, p=0.23; 32B vs 8B b=3, c=4,
p=1.00.

### 2. Accuracy at 8192 (non-terminating scored 0; scorer VALIDATED)
| arm | correct / n | acc [95% Wilson] | parse failed | not eligible (non-term) |
|---|---|---|---|---|
| 4B-T (StudyP A) | 11/40 | 27.5% [16.1, 42.8] | — | — |
| 8B-T (StudyP C) | 12/40 | 30.0% [18.1, 45.4] | — | — |
| 8B-I (StudyP D) | 12/40 | 30.0% [18.1, 45.4] | — | — |
| 32B-T | 11/35 | 31.4% [18.6, 48.0] | 0 | 5 |
| 32B-I | 16/40 | 40.0% [26.3, 55.4] | 0 | 0 |

32B-T vs 32B-I paired (n=35): b (T✓ I✗) = 4, c (I✓ T✗) = 6 — thinking does not beat instruct here either.

### 3. Think tokens among completers (32B censored at 8192; 4B J2 completers censored at 24,576 — not like-for-like)
| bin | 32B completers | 32B median | IQR | p90 | 4B median |
|---|---|---|---|---|---|
| low | 10/11 | 1,456 | 640–2,392 | 3,229 | 505 |
| mid | 10/11 | 4,977 | 4,452–5,302 | 6,352 | 5,416 |
| high | 9/12 | 6,270 | 5,104–6,686 | 7,900 | 4,897 |
| all | 30/35 | 4,486 | 2,655–6,058 | 6,806 | 3,339 |

32B thinks **longer** than 4B on low- and high-complexity signs among completers. Unlike ERQA (StudyR), where
32B-T thought about half as long as 4B, sign recognition draws long traces at 32B too.

### 4. Per-bin termination at 8192
| bin | 32B-T | 4B-T (J2 read-off at 8192) |
|---|---|---|
| low | 10/11 | 12/13 |
| mid | 10/11 | 6/13 |
| high | 9/12 | 9/13 |
| other | 1/1 | 1/1 |

The 32B gain over 4B is concentrated in the **mid** bin (10/11 vs 6/13).

### 5. Survival (fraction NOT terminated by budget B)
| B | 32B-T | 4B-T (J2) |
|---|---|---|
| 1,024 | 31/35 (88.6%) | 32/40 (80.0%) |
| 2,048 | 28/35 (80.0%) | 29/40 (72.5%) |
| 4,096 | 22/35 (62.9%) | 21/40 (52.5%) |
| 8,192 | 5/35 (14.3%) | 12/40 (30.0%) |
| 16,384 / 24,576 | ladder pending (5 signs not closed at 8192) | 8/40 (20.0%) |

32B starts slower (fewer signs closed by 1–4k tokens) but crosses below 4B by 8,192. Whether a hard
never-terminate core like 4B's 20% exists at 32B is answered by the ladder (pending). *(Analysis-script fix
applied before writing this: the survival table previously dropped unobserved non-terminators at 16k/24k and
printed a spurious 0/30; it now reports them as not-yet-run.)*

### 6. Latency (no prefix cache; one sign at a time; contended trials: 0)
| arm | n | median s | p90 s | decode tok/s |
|---|---|---|---|---|
| 32B-I | 40 | 2.8 | 6.3 | 23.0 |
| 32B-T | 35 | 216.9 | 342.4 | 23.9 |

Peak reserved VRAM: I32 68.1 GB, T32 73.5 GB. Decode ≈23–24 tok/s matches the StudyR probe (22.6 tok/s).

Files: `results/signs/study_t/study_t_trials_h100nvl.jsonl`, `study_t_scores_h100nvl.jsonl`,
`study_t_results_h100nvl.json`, `scorer_validation.json`, `study_t_run_meta_h100nvl.json`.

---

## Final results (all 40 signs at 8192 + budget ladder; completed 2026-10-15 08:16)

Post-cap completion ran the 5 cap-cut signs at 8192 (06:30–06:49, `phase = core_postcap`); the ladder then
re-ran the 6 signs not closed at 8192 at 16,384, and the 2 still open at 24,576. Scorer validated (Gemini 40.7%).

### Primary verdict (unchanged by the post-cap signs)
**TREND DOES NOT CONTINUE — indistinguishable from 8B.** Within-cap 30/35 = 85.7% [70.6, 93.7]; all 40:
**34/40 = 85.0% [70.9, 92.9]** (< 36 required; Wilson upper > 90%, so not a reversal).
Trend at 8192: **4B 70% → 8B 90% → 32B 85%.** Paired by sign: 32B vs 4B b=9 / c=3 (p=0.15); 32B vs 8B b=3 / c=5
(p=0.73).

### Secondary — the 20% never-terminate asymptote at 32B (ladder)
| B | 32B-T not terminated | 4B-T not terminated (J2) |
|---|---|---|
| 1,024 | 34/40 (85.0%) | 32/40 (80.0%) |
| 2,048 | 31/40 (77.5%) | 29/40 (72.5%) |
| 4,096 | 25/40 (62.5%) | 21/40 (52.5%) |
| 8,192 | 6/40 (15.0%) | 12/40 (30.0%) |
| 16,384 | 2/40 (5.0%) | 8/40 (20.0%) |
| 24,576 | **2/40 (5.0%)** | **8/40 (20.0%)** |

- **4B's 20% asymptote does not hold at 32B: 5% never terminate by 24,576** (2/40: IMG_6431 high bin,
  IMG_6443 low bin; both hit 24,576 with `</think>` open).
- **The never-terminating signs are disjoint across scale:** none of 4B's 8 never-terminators is among 32B's 2,
  and all 8 terminate at 32B; both of 32B's terminate at 4B. Paired: 4B-only b=8, 32B-only c=2, exact McNemar
  p=0.11 (n=40 is not powered for this). Non-termination looks like a sign × model interaction, not a property
  of intrinsically "hard" signs.
- 32B starts slower than 4B (more signs still open at 1–4k tokens) but overtakes by 8,192.
- **Ladder determinism: 8/8 re-runs reproduced the previous rung's tokens as an exact prefix**, so the
  re-run ladder is equivalent to a single long run and directly comparable with J2's read-off curve.

### Accuracy at 8192 (validated scorer; non-terminating = 0)
| arm | correct / n | acc [95% Wilson] |
|---|---|---|
| 4B-T (StudyP A) | 11/40 | 27.5% [16.1, 42.8] |
| 8B-T (StudyP C) | 12/40 | 30.0% [18.1, 45.4] |
| 8B-I (StudyP D) | 12/40 | 30.0% [18.1, 45.4] |
| **32B-T** | 14/40 | 35.0% [22.1, 50.5] (6 non-terminating scored 0; 0 parse failures among terminated) |
| **32B-I** | 16/40 | 40.0% [26.3, 55.4] |

32B-T vs 32B-I paired: b (T✓ I✗) = 5, c (I✓ T✗) = 7 — thinking does not beat instruct at 32B on signs either.

### Think tokens among completers at 8192 (32B censored at 8192; 4B at 24,576 — not like-for-like)
| bin | 32B completers | 32B median | IQR | 4B median |
|---|---|---|---|---|
| low | 12/13 | 1,112 | 501–2,018 | 505 |
| mid | 11/13 | 5,211 | 4,486–5,746 | 5,416 |
| high | 10/13 | 5,989 | 4,591–6,683 | 4,897 |
| all | 34/40 | 4,419 | 2,018–6,058 | 3,339 |

Per-bin termination at 8192: low 12/13 (4B 12/13), mid 11/13 (4B 6/13), high 10/13 (4B 9/13) — the 32B gain is in
the mid bin.

### Latency (no prefix cache; one sign at a time; contended trials 0)
| arm | budget | n | median s | p90 s | tok/s |
|---|---|---|---|---|---|
| I32 | 8192 | 40 | 2.8 | 6.3 | 23.0 |
| T32 | 8192 | 40 | 209.9 | 342.1 | 23.9 |
| T32 | 16,384 | 6 | 591.3 | 677.4 | 24.2 |
| T32 | 24,576 | 2 | 1,040.4 | 1,042.8 | 23.6 |

**VRAM note (corrected 2026-10-15, see the flash-attn re-measure below):** peak *reserved* reached 99.2 GB at
24,576 tokens, but peak *allocated* was 73.6 GB (I32 68.1 GB; T32 ≤ 73.5 GB at 8192); the gap is allocator
fragmentation, reproduced identically under flash-attn, not memory the model needs and not offloading.

### Consistency and mechanism checks
- **Cross-check:** 4B/8B termination and accuracy are the committed StudyP/J2 values; 32B decode 23–24 tok/s
  matches StudyR's probe (22.6) and StudyS2 (23.9).
- **Distribution:** think tokens and latency reported with IQR/p90; no constants.
- **Definitions:** "terminated by B" = `think_closed` and n_think < B (reproduces J2's table exactly);
  bins from n_gt (low 1–2, mid 3–5, high ≥6) as in J2.
- **Claim linkage:** bears on the termination line (StudyJ2/J4/P): **weakens** "a ~20% never-terminate floor is
  intrinsic to the signs" — at 32B the floor is 5% and on different signs. No CLAIMS.md C1–C5 entry is about
  termination.
- **Mechanism:** thinking present in all T32 trials; termination varies with scale and budget; ladder
  determinism verified (8/8) → the survival comparison is valid.
- **Implementation incidents (no data affected):** (1) the analysis survival table first dropped unobserved
  non-terminators (fixed before any write-up); (2) the ladder process crashed after its last trial because
  `meta["ladder"]` aliased the `LADDER` list being iterated (fixed; rerun with nothing left to run finalised
  the metadata).

Files: `results/signs/study_t/study_t_trials_h100nvl.jsonl`, `study_t_scores_h100nvl.jsonl`,
`study_t_results_h100nvl.json`, `scorer_validation.json`, `study_t_run_meta_h100nvl.json`; scripts
`experiments/signs/study_t_signs_32b.py`, `study_t_score.py`, `study_t_analyse.py`.

---

## Flash-attn re-measure of the long-budget traces (2026-10-15 08:51–10:15, h100nvl GPU 3)

Step 2 of the flash-attn re-run. flash-attn 2.8.3 installed `--no-deps` (+ `einops` 0.8.2); torch 2.8.0+cu128,
transformers 5.10.2 unchanged. Every load passes `attn_implementation="flash_attention_2"` and asserts
`model.config._attn_implementation == "flash_attention_2"` (passed); the value is stored per trial. The 8
SDPA long-budget traces were re-run with the same sign, budget and seed, plus one **forced-length probe**
(`min_new_tokens = 24,576`) so the 24,576 peak is measured even if the flash-attn trace closes earlier. The
allocator cache was emptied before each trace. File: `results/signs/study_t/study_t_longtrace_h100nvl_fa2.jsonl`.

| sign | budget | SDPA: gen / closed / alloc GB / reserved GB / tok/s | flash-attn: gen / closed / alloc GB / reserved GB / tok/s |
|---|---|---|---|
| IMG_6431 | 24,576 | 24,576 / no / 73.60 / 99.23 / 23.7 | 10,283 / yes / 69.83 / 78.57 / 18.9 |
| IMG_6443 | 24,576 | 24,576 / no / 73.52 / 90.42 / 23.6 | 2,444 / yes / 67.66 / 67.99 / 18.9 |
| **IMG_6431 (forced)** | 24,576 | — | **24,576 / — / 73.60 / 99.22 / 18.2** |
| IMG_6415 | 16,384 | 13,435 / yes / 70.62 / 87.64 / 24.2 | 12,187 / yes / 70.29 / 85.25 / 18.9 |
| IMG_6431 | 16,384 | 16,384 / no / 71.44 / 99.20 / 24.2 | 10,283 / yes / 69.83 / 78.57 / 18.9 |
| IMG_6443 | 16,384 | 16,384 / no / 71.35 / 72.31 / 24.2 | 2,444 / yes / 67.66 / 67.99 / 19.0 |
| IMG_0042 | 16,384 | 13,005 / yes / 70.45 / 72.31 / 24.1 | 11,084 / yes / 70.00 / 78.68 / 18.9 |
| IMG_0037 | 16,384 | 15,196 / yes / 71.06 / 72.31 / 24.2 | 16,384 / no / 71.38 / 99.23 / 18.7 |
| IMG_6566 | 16,384 | 8,527 / yes / 69.26 / 72.31 / 24.1 | 4,284 / yes / 68.14 / 68.79 / 18.9 |

### The 99.2 GB figure — finding
- **It is not an SDPA artifact.** At 24,576 generated tokens, flash-attn gives **peak allocated 73.60 GB and peak
  reserved 99.22 GB**, identical to SDPA (73.60 / 99.23), even with the allocator cache emptied first.
- **It is reserved, not required, memory.** The model needs **73.6 GB** (weights 66.7 GB + KV cache for ≈25.9k
  tokens ≈ 6.5 GB + activations). The ≈25.6 GB above that is caching-allocator fragmentation: the KV cache is
  re-allocated larger every decode step and freed blocks stay reserved. Reserved varies 68–99 GB for traces of
  similar length under both backends (e.g. 99.2 GB at only 16,384 under flash-attn, IMG_0037).
- **No offload or swap occurred.** The card has 95,830 MiB (≈100.5 GB; it is not an 80 GB part), weights are
  pinned to one GPU (`device_map={"": 0}`, no offload path — overflow would raise OOM), and SDPA decode throughput
  was flat at 23.6–24.2 tok/s from short traces to 24,576 tokens. **The SDPA long-trace latencies measure
  inference, not swap; they stand.**
- **Correction to the earlier text:** the core section's "peak reserved VRAM reached 99.2 GB … at the card's
  limit" is restated as: peak *allocated* 73.6 GB at 24,576 tokens (both backends); peak *reserved* up to 99.2 GB
  from allocator fragmentation. The SDPA figure is neither an attention artifact nor offloading, so it is not
  retracted, but it must not be read as the memory the model needs. (Untested refinement:
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` should bring reserved close to allocated.)

### Other observations (not verdicts)
- Flash-attn is **deterministic per seed** (IMG_6431 and IMG_6443 produce identical traces at 16,384 and
  24,576), as SDPA was, but its token sequences differ from SDPA's — the same seed lands on different paths.
  Termination is therefore re-sampled: 3 signs that never closed under SDPA closed under flash-attn
  (IMG_6431, IMG_6443 at 10,283 / 2,444 tokens), and one that closed under SDPA did not (IMG_0037).
- **Flash-attn decoded at 18.2–19.0 tok/s vs SDPA's 23.6–24.2 tok/s, at every length** — slower, not faster.
  Decode is single-CPU-core bound (python at ~100% of one core) and other users' jobs were active on the same
  NUMA-0 CPUs during this run (load average ~15–21; not logged for the SDPA run), so this cross-session
  comparison is **confounded by CPU contention** and is not a backend speed measurement. A same-process,
  interleaved SDPA↔flash-attn timing on identical forced-length prompts is required to attribute it.

---

## Flash-attn re-run — core (2026-10-15 12:02–15:01, h100nvl GPU 3; no cap)

Same 40 signs, seed, decoding and budgets; only the attention backend changes (`flash_attention_2`, asserted
at load and stored per trial). Scorer validated. Files: `study_t_trials_h100nvl_fa2.jsonl`,
`study_t_scores_h100nvl_fa2.jsonl`, `study_t_results_h100nvl_fa2_core.json`.

### ⚠ Verdict sub-class FLIPS between backends — both reported, neither picked
| | SDPA (2026-10-14) | flash-attn (2026-10-15) |
|---|---|---|
| 32B-T terminated at 8192 | 34/40 = 85.0% [70.9, 92.9] | **29/40 = 72.5% [57.2, 83.9]** |
| Primary verdict | TREND DOES NOT CONTINUE | TREND DOES NOT CONTINUE |
| Sub-class | indistinguishable from 8B (upper 92.9 ≥ 90) | **reversal** (upper 83.9 < 90) |
| Paired vs 8B-T (b / c, p) | 3 / 5, p=0.73 | 2 / 9, p=0.065 |
| Paired vs 4B-T (b / c, p) | 9 / 3, p=0.15 | 6 / 5, p=1.00 |

- **The primary verdict is backend-stable; the sub-classification is not.** Under flash-attn, 32B terminates
  no better than 4B (72.5% vs 70%) and below 8B; under SDPA it sat between them.
- **SDPA vs flash-attn termination, paired by sign:** both terminated 27, neither 4, SDPA-only 7, flash-attn-only 2
  (exact McNemar p=0.18). The two backends draw different token paths from the same seed, so termination is
  re-sampled; a 5-sign swing at n=40 is within what that noise allows (p=0.18) and is the measured backend-to-
  backend variability of this endpoint. **Conclusion: at n=40 the reversal-vs-indistinguishable distinction is not
  resolvable; "scale does not buy termination beyond 8B" is the robust statement.**

### Accuracy (validated scorer)
| arm | SDPA | flash-attn | delta |
|---|---|---|---|
| 32B-I (greedy) | 16/40 = 40.0% | 16/40 = 40.0% | **0.0 pp** (37/40 answer texts identical; the 3 differing texts score the same) |
| 32B-T | 14/40 = 35.0% | 16/40 = 40.0% | +5.0 pp (sampling noise; 11 non-terminating scored 0) |
| 32B-T vs 32B-I b / c | 5 / 7 | 5 / 5 | thinking does not beat instruct under either backend |

The greedy instruct arm is unchanged (< 1 pp), as expected for mathematically equivalent kernels.

### Think tokens among completers at 8192 (flash-attn)
low 13/13 median 1,910; mid 8/13 median 4,090; high 7/13 median 5,328; all 29/40 median 3,928
(SDPA: all 34/40 median 4,419). Per-bin termination flash-attn vs SDPA: low 13/13 vs 12/13, mid 8/13 vs 11/13,
high 7/13 vs 10/13.

### Decode rate
T32 median 18.8 tok/s (flash-attn) vs 23.9 (SDPA). Same caveat as the long-trace section: cross-session and
CPU-contention-confounded; not yet a backend measurement.

## Flash-attn re-run — budget ladder (2026-10-15 21:47–23:59)

11 signs not closed at 8192 under flash-attn were re-run at 16,384; the 1 still open went to 24,576. Ladder
determinism: **12/12 re-runs reproduced the previous rung's tokens as an exact prefix** (SDPA: 8/8).
Files: `study_t_results_h100nvl_fa2.json` (full), `study_t_scores_h100nvl_fa2.jsonl`.

### Survival side by side (fraction NOT terminated by budget B)
| B | 32B SDPA | 32B flash-attn | 4B (J2, SDPA) |
|---|---|---|---|
| 1,024 | 34/40 (85.0%) | 36/40 (90.0%) | 32/40 (80.0%) |
| 2,048 | 31/40 (77.5%) | 33/40 (82.5%) | 29/40 (72.5%) |
| 4,096 | 25/40 (62.5%) | 23/40 (57.5%) | 21/40 (52.5%) |
| 8,192 | 6/40 (15.0%) | 11/40 (27.5%) | 12/40 (30.0%) |
| 16,384 | 2/40 (5.0%) | **1/40 (2.5%)** | 8/40 (20.0%) |
| 24,576 | **2/40 (5.0%)** | **1/40 (2.5%)** | **8/40 (20.0%)** |

- **The never-terminate finding is backend-robust:** at 24,576, 32B leaves 5% (SDPA) / 2.5% (flash-attn) of
  signs open vs 4B's 20%. 4B's 20% asymptote does not hold at 32B under either kernel.
- **The 8,192 rate is not backend-robust** (85% vs 72.5%; core section above): flash-attn's extra non-terminators
  at 8,192 are slow completers, not never-terminators — 10 of 11 close by 16,384 (8,395–12,107 think tokens).
  The 8,192 primary endpoint is therefore sensitive to where the budget sits relative to a dense cluster of
  ~8–12k-token traces; the asymptote is the stable quantity.
- **The never-terminating signs differ by backend as well as by scale:** flash-attn's only never-terminator
  (IMG_0037, open at 24,576) closed under SDPA at 15,196 tokens; SDPA's two (IMG_6431, IMG_6443) close under
  flash-attn at 10,283 / 2,444. With 4B's 8 disjoint from both, non-termination is a property of the sampled
  path, not of the sign.
- Peak at 24,576 (IMG_0037, natural): allocated 73.54 GB, reserved 99.2 GB — the same allocator-fragmentation
  signature as SDPA.
- Decode: I32 18.1 tok/s, T32 18.3–18.8 tok/s under flash-attn vs 23.0 / 23.6–24.2 under SDPA — the slowdown
  appears for the short greedy instruct answers (tens to a few hundred tokens) too, consistent with per-step overhead (CPU-bound launch,
  flash-attn varlen/unpad path) rather than attention FLOPs; still cross-session and CPU-contention-confounded.
