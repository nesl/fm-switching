# StudyS2 — MV-RoboBench spatial strata at 32B: does thinking pay at 32B? (h100nvl)

Status: **COMPLETE (2026-10-15 06:30).** Verdict: **THINKING DOES NOT PAY AT 32B on this stratum** — net_rescue
(D−C) −1.50 pp, 95% CI [−6.98, +3.99], n=401. The pre-registration block below is unchanged since before the
first StudyS2 trial; results follow it.

---

## Pre-registration (written 2026-10-14, before any StudyS2 trial)

### Design revision history (all before any StudyS2 trial)
1. First drafted as a fresh four-arm study (4B-I, 4B-T, 32B-I, 32B-T all re-run here).
2. **User revision (2026-10-14, before any trial): two new arms only — C (32B-Instruct) and D
   (32B-Thinking). No 4B re-run.** 4B values are taken from StudyS1 as **cross-study** numbers and labelled
   as such. The 80 %-think_closed inconclusive rule proposed in draft 1 is **dropped**. The pre-registered
   5 pp threshold is unchanged.
3. **User revision (2026-10-14): interleaved GPU schedule** — arm D is run in two blocks (see Runtime);
   the blocks are one run, pooled, with no interim analysis.

### StudyS1 reproducibility gap (open)
StudyS1's results, script and manifest exist only on flash; they are not on this machine or in the repo
(registry row StudyS1 records the gap). Its values (arm I 37.4 %, arm T 38.4 %, net_rescue +1.00 pp,
CI [−4.74, +6.74], n = 401) were supplied in the study spec and cannot be re-verified here. Only these
aggregates are available — **no per-question 4B answers** — so no paired 4B-vs-32B term can be computed.

### Question
StudyS1 found no net thinking benefit at 4B on two MV-RoboBench spatial categories. Is that negative
scale-specific? Vendor tables show the thinking effect on spatial benchmarks reversing sign between 8B and
32B (RefSpatialBench −9.6 → +5.8; RoboSpatialHome −4.9 → +9.6; as supplied in the spec, not re-verified).

### Decision rule (verbatim)
"THINKING PAYS AT 32B on this stratum if net_rescue (D-C) exceeds 5pp with a 95% paired CI excluding 0.
Otherwise the StudyS1 negative is NOT scale-specific and the four-workload negative stands at 32B."

net_rescue(D−C) = P(C wrong, D right) − P(C right, D wrong) = mean paired difference (D − C), computed on
all questions answered by both C and D (complete-case). The stratum is both categories pooled, or whatever
prefix of the fixed order D completes (see Runtime); the analysed n and its MDE are stated with the verdict.

### Data — manifest provenance
- Dataset `AaronFengZY24/MV_Robobench` pinned at `869ea1113cf2f08498e81f57ced72597238455c0` (HEAD
  2026-10-14); QA.json + all 1,365 view images downloaded for the 401 questions.
- Manifest `results/erqa/study_s2/study_s2_manifest.json` was **rebuilt from StudyS0 audit1 metadata**
  (`results/erqa/study_s0/audit1_mvrobobench.json`, sha256 `7bd2777e8425…`), **not copied from StudyS1**:
  all of `spatial_distance_judgement` (SDJ, 201) + `robotic_trajectory_selection` (RTS, 200), no sampling.
  Counts match S1's n = 401; whether S1 used exactly this set cannot be checked here.
- Verified: all images present; options/correct letters match S0 metadata (0 mismatches); every question has
  5 options → **random baseline 20 %**; 3 views (agiworld) or 4 (bridgev2).
- Question key `path`; `index` = manifest position (SDJ sorted by path, then RTS sorted by path).

### Arms (bf16, h100nvl, identical prompt)
| arm | model @ revision | decoding | max_new_tokens | source |
|---|---|---|---|---|
| C | Qwen3-VL-32B-Instruct @0cfaf481 | greedy | 512 | NEW |
| D | Qwen3-VL-32B-Thinking @7edd10ff | CFG-A | 8192 | NEW |
| I (4B-Instruct) | — | — | — | StudyS1, cross-study aggregate 37.4 % |
| T (4B-Thinking) | — | — | 8192 | StudyS1, cross-study aggregate 38.4 % |

- CFG-A: temperature 0.6, top_p 0.95, top_k 20, min_p 0, do_sample. **Deviation disclosed:** the model
  card recommends temperature 1.0; 0.6 kept for cross-study consistency (StudyS0).
- D budget 8192 matches StudyS1's thinking arm, so scale is not confounded with budget.
- Seeding: per-question `set_seed(42 + index)` for D (resume-safe; identical whichever block a question
  runs in). Single seed.

### Prompt template (ours — MV-RoboBench ships no eval prompt)
```
View 1 (<illustration>): <image>
...
<question>
Options:
A. <option A>
...
E. <option E>
Answer with the option's letter from the given choices directly.
```
Same prompt for C and D; full prompt string stored per trial. StudyS1's template is unknown — a further
reason the 4B comparison is cross-study only.

### Parsing
`extract_letter` (StudyK/Q/R) widened to A–E: direct → "answer is X" → last letter in final 80 chars. D
parses only text after `</think>` (full text if unclosed). `no_letter` scored wrong **and** reported
separately; `last_found` reported separately.

### Power (stated before running)
Paired McNemar, n = (z_α + z_β)² · p_disc / δ² (α = 0.05 two-sided, 80 % power), discordance assumed
0.25–0.35 (4B–8B thinking changed ~27–35 % of answers):

| assumed discordance | n | 95 % CI half-width | MDE |
|---|---|---|---|
| 0.25 / 0.30 / 0.35 | 401 | ±4.9 / ±5.4 / ±5.8 pp | 7.0 / 7.7 / 8.3 pp |
| 0.25 / 0.30 / 0.35 | 201 | ±6.9 / ±7.6 / ±8.2 pp | 9.9 / 10.8 / 11.7 pp |
| 0.25 / 0.30 / 0.35 | 100 | ±9.8 / ±10.7 / ±11.6 pp | 14.0 / 15.3 / 16.6 pp |

**Under-powered for 5 pp at every reachable n** (5 pp needs n ≈ 785–1,100). A "does not pay" verdict is
weak evidence of absence unless the CI upper bound is itself below 5 pp. The final MDE is recomputed with
the observed discordance and the completed n.

### Statistics (fixed now)
- Accuracy: Wilson 95 % CI.
- **Primary D−C:** question-level paired bootstrap (10,000 resamples, percentile 95 % CI, rng seed 0),
  exact McNemar p, **b and c reported separately**.
- **4B-involving terms (C−I, D−T, T−I, D−I) are cross-study and unpaired:** difference of aggregate
  accuracies with an unpaired Wilson-based (Newcombe) 95 % CI, labelled CROSS-STUDY (different host, stack,
  prompt possibly, and S1's question set not verifiable). T−I is S1's own value. These do not enter the
  verdict.
- Per-category results descriptive only.

### Runtime — interleaved schedule (user instruction 2026-10-14)
GPU 3 order: StudyR (to its 4 h cap) → **S2 arm C, all 401** → **S2 arm D, manifest indices 0–99** →
StudyT core (2 h cap) → **S2 arm D, indices 100–400** → StudyT budget ladder.
- Arm D's order is **fixed now** as manifest order (no shuffling), recorded in
  `results/erqa/study_s2/study_s2_armD_order.json`. The two D blocks are **one run resumed**, not two
  studies; all completed D trials are pooled into one analysis at the end.
- **No interim peek:** at the 100 boundary only elapsed time and a revised projection for the remaining
  301 are reported. No accuracy, b/c, net_rescue or D-vs-C comparison is computed before the end.
- If time runs short, the second D block is the one truncated; the report states the completed n (a prefix
  of the fixed order: indices 0–99 are all SDJ, so a short run is SDJ-weighted — disclosed) and its MDE.
- Contention: run continues; trials overlapping a foreign process on GPU 3 (per-5-s process log) are
  excluded from latency only and their IDs listed.

### Known asymmetries and confounds (disclosed in advance)
1. Decoding confounded with thinking (C greedy, D sampled), as at 4B.
2. Single seed for D.
3. Stack: transformers 5.10.2 (StudyS0: 5.12.1; not 5.17.x), torch 2.8.0+cu128, SDPA, H100 NVL.
4. 4B comparisons are cross-study (S1 on flash; stack, prompt and exact question set unverifiable).
5. Budget hits at 8192 usually yield `no_letter` (scored wrong) — reported for D.
6. Instruct answers include option text ("A. The blue line."); leading letter parsed (smoke-tested).
7. A truncated second D block makes the analysed set SDJ-heavy relative to the 401.

### Mechanism verification (CLAUDE.md)
1. Causal chain: an explicit reasoning trace helps multi-view spatial judgement only if the model can use it
   to integrate evidence across views; vendor tables suggest this emerges between 8B and 32B → D−C > 0
   while S1's T−I ≈ 0.
2. Instantiation: `n_think_tokens` > 0 for D, 0 for C; `think_closed` and budget hits reported for D;
   scale 66.7 GB weights (32B). Termination is reported, not used as a verdict gate (80 % rule dropped).
3. Trace: one full D trial record (prompt, think length, answer, parse) pasted in the results.
4. Negative control: none possible without changing models; C (no thinking) is the contrast.
5. Alternative explanation: a D−C gain could come from sampling vs greedy (confound 1) or from C
   under-using its 512 budget; C's `n_generated` is reported.

### Analyses
1. Accuracy C, D (n, Wilson CI, 20 % baseline), stratum and per category; 4B S1 values alongside, labelled
   cross-study.
2. The 2×2 table 4B-I / 4B-T (S1, cross-study) / 32B-I / 32B-T side by side.
3. D−C paired: diff, CI, b and c separately, McNemar p; reshuffling signature (~30 % changed, net ≈ 0) vs
   genuine net gain.
4. Verdict in the exact pre-registered form, with analysed n and MDE.
5. Cross-study terms C−I, D−T, D−I (unpaired, labelled).
6. D termination, budget hits, think-token distribution vs S1's T where known.
7. Latency C and D (median, p90), contended trials excluded.

Scripts: `experiments/erqa/study_s2_mvrobobench_32b.py` (run; `--arms C`, `--arms D --stop-at 100`, then
`--arms D`), `experiments/erqa/study_s2_analyse.py` (analysis). Outputs under `results/erqa/study_s2/`.

---

## Results (run 2026-10-14 22:49 → 2026-10-15 06:30, h100nvl GPU 3, bf16)

Run record: arm C all 401 (22:49–22:52); arm D indices 0–99 (22:52–00:48); StudyT core ran in between
(00:48–02:50); arm D indices 100–400 resumed (02:50–06:30). **Both arms complete, n = 401 each.** No
interim analysis was run: at the 100 boundary only elapsed time (1 h 56 min) and a projection were
reported; the first computation of any D accuracy or D−C quantity is this analysis, after the last D trial.

### Verdict (pre-registered form)
**THINKING DOES NOT PAY AT 32B on this stratum. The StudyS1 negative is NOT scale-specific and the
four-workload negative stands at 32B.** net_rescue (D−C) = **−1.50 pp, 95% paired bootstrap CI [−6.98, +3.99]**,
n = 401, b = 61 (D✓ C✗), c = 67 (D✗ C✓), McNemar p = 0.66.

Power, recomputed with the observed discordance (0.319) at n = 401: CI half-width ≈ ±5.5 pp, MDE ≈ 7.8 pp.
Unlike StudyR, the CI upper bound (+3.99 pp) is **below the 5 pp threshold**, so this is a positive finding of
absence at the pre-registered effect size, not just a failure to detect.

### Analysis 3 — reshuffling signature (b and c)
| subset | n | b (D✓ C✗) | c (D✗ C✓) | changed | net | D−C pp [95% CI] |
|---|---|---|---|---|---|---|
| stratum | 401 | 61 | 67 | 128 (31.9%) | −6 | −1.50 [−6.98, +3.99] |
| SDJ (descriptive) | 201 | 27 | 31 | 58 (28.9%) | −4 | −1.99 [−9.45, +5.47] |
| RTS (descriptive) | 200 | 34 | 36 | 70 (35.0%) | −2 | −1.00 [−9.50, +7.50] |

**32B shows the same reshuffling signature as 4B–8B:** thinking changes ~32% of answers (vs ~30% at 4B–8B,
ERQA 59/49, MV-RoboBench 71/67) and nets ≈0 (here slightly negative). No genuine net gain at 32B.

### Analyses 1–2 — accuracy and the 2×2
| | Instruct | Thinking |
|---|---|---|
| 4B (StudyS1, **cross-study**, n=401) | 37.4% | 38.4% |
| 32B (this run, n=401) | **47.9% [43.0, 52.8]** | **46.4% [41.6, 51.3]** |

Random baseline 20% (5 options). Per category (descriptive): SDJ C 50.7% / D 48.8%; RTS C 45.0% / D 44.0%.
Parse: C 401 direct; D 399 direct + 2 `extracted` ("answer is X" pattern), 0 `no_letter`.

### Analysis 5 — cross-study terms vs StudyS1 4B aggregates (unpaired Newcombe CI; NOT in verdict)
| term | 32B | S1 4B | diff pp | 95% unpaired CI |
|---|---|---|---|---|
| C−I size @instruct | 47.9 | 37.4 | +10.5 | [+3.6, +17.2] |
| D−T size @thinking | 46.4 | 38.4 | +8.0 | [+1.1, +14.7] |
| D−I total device→cloud | 46.4 | 37.4 | +9.0 | [+2.2, +15.7] |
| T−I thinking @4B (S1's own) | — | — | +1.00 | [−4.74, +6.74] |

CROSS-STUDY caveats: different host/stack (S1 on flash), S1's prompt and exact question set unverifiable, and
StudyR measured ~3.5% of greedy answers changing across A6000/H100 stacks. The size gap (~+8–10 pp) mirrors
StudyR's ERQA result, but these terms are not paired evidence.

### Analysis 6 — D termination and think tokens
| subset | n | think closed | budget hits (8192) | think tok median | IQR | p90 | max |
|---|---|---|---|---|---|---|---|
| stratum | 401 | 99.5% | 2 (0.5%) | 759 | 436–1,459 | 2,623 | 8,010 |
| SDJ | 201 | 99.0% | 2 (1.0%) | 875 | 501–1,662 | 2,919 | 8,010 |
| RTS | 200 | 100% | 0 | 659 | 376–1,179 | 2,148 | 4,961 |

Thinking is fully exercised (99.5% closed). S1's 4B-T termination is not available here for comparison.

### Analysis 7 — latency (no prefix cache; one question at a time; contended trials: 0)
| arm | subset | median s | p90 s |
|---|---|---|---|
| C | stratum | 0.35 | 0.47 |
| D | stratum | 32.1 | 112.0 |
| D | SDJ / RTS | 36.6 / 27.6 | 125.9 / 90.4 |

D/C median ratio **92×** (same hardware). C latency is bimodal by view count (3-view agiworld ≈0.16 s,
4-view bridgev2 ≈0.27–0.47 s; full range 0.16–0.65 s), not constant. D decodes at a median 23.9 tok/s,
matching the StudyR probe (22.6) and StudyT (23.9).

### Sanity and consistency checks (CLAUDE.md)
| check | result |
|---|---|
| checkpoints / quant | 32B-I @0cfaf481, 32B-T @7edd10ff, both bf16; peak reserved C 67.6 GB, D 73.5 GB |
| stack | transformers 5.10.2 (not 5.17.x), torch 2.8.0+cu128, SDPA; dataset @869ea111 |
| run split | D indices 0–99 vs 100–400: b/c 13/14 and 48/53 — same per-question seeds; one run, pooled |
| contention | no foreign process on GPU 3 during any S2 trial. A first pass flagged 1 trial (D RTS QA080) because our own StudyT process (PID 964355), started by the chain as D exited, was missing from the PID list; with all own PIDs listed, 0 contended |
| 1. cross-check | no prior 32B MV-RoboBench measurement; 4B comparison is cross-study only (S1 flash-only) |
| 2. plausibility | D ≈24 tok/s; C generates ≤12 tokens in 0.16–0.65 s |
| 3. distribution | latency and think tokens reported with IQR/p90/max; C bimodal by view count |
| 4. definitions | net_rescue = mean paired (D − C) on the 401; stratum = SDJ + RTS from S0 metadata |
| 5. claim linkage | reasoning-tier feasibility line (StudyK/Q/S0/S1/R): **supports** "the 4B thinking null persists at 32B"; no CLAIMS.md C1–C5 entry is directly about thinking mode |
| 6. proxy validity | MV-RoboBench SDJ/RTS stand in for "spatial" in the vendor tables (RefSpatialBench, RoboSpatialHome); different benchmarks, so the vendor-table reversal is not contradicted, it does not transfer here |

### Mechanism verification
1. Causal chain: a reasoning trace improves multi-view spatial judgement only if it is produced, terminates,
   and changes answers toward the gold.
2. Instantiation: think tokens median 759 (C: 0) — present; 99.5% closed — terminates; 31.9% discordance —
   changes answers. No ABSENT/CONSTANT link → **real negative** (Rule 2), not a design failure.
3. Trace (D, agiworld/robotic_trajectory_selection/QA001, 3 views): 1,034 input tokens → 315 think tokens,
   `</think>` closed, answer "B" (gold B, correct), 13.5 s, peak reserved 69.0 GB.
4. Negative control: C (same checkpoint size, no thinking) is the contrast; none other possible.
5. Alternative: sampled vs greedy decoding (confound 1) could move answers without reasoning; the
   discordance is consistent with that, and with the null, the distinction does not change the verdict.

### Files
`results/erqa/study_s2/study_s2_manifest.json`, `study_s2_armD_order.json`, `study_s2_trials_h100nvl.jsonl`,
`study_s2_run_meta_h100nvl.json`, `study_s2_results_h100nvl.json`; scripts
`experiments/erqa/study_s2_mvrobobench_32b.py`, `experiments/erqa/study_s2_analyse.py`.
