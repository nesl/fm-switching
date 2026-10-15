# H100 night run — summary (2026-10-14 18:59 → 2026-10-15 08:16, h100nvl)

Three pre-registered studies on Qwen3-VL-32B-{Instruct,Thinking} (bf16) on the shared H100 NVL host
(`sn4622120321`), run unattended in an interleaved chain on GPU 3 (StudyR's arm C and first 23 D trials on
GPU 2). No foreign process touched our GPU during any trial. transformers 5.10.2, torch 2.8.0+cu128, SDPA.

## Cross-study question: does the 4B–8B thinking null persist at 32B?

**Yes.** On two accuracy workloads, 32B thinking reshuffles answers (19–32% changed) and nets ≈0, exactly the
4B–8B signature. The device-to-cloud gap at 32B is carried by **size** (+8 to +13 pp), not by thinking. On
signs, scale does not buy termination beyond 8B, and 32B thinking again does not beat 32B instruct.

## Verdicts

| study | workload | pre-registered test | result | verdict |
|---|---|---|---|---|
| **StudyR** | ERQA spatial (n=118) | D−C (32B-T − 32B-I) > 5 pp, CI excl. 0 | **+2.5 pp [−5.1, +11.0]**, b=13 c=10 | **THINKING DOES NOT PAY AT SCALE** (weak evidence of absence: CI upper > 5) |
| **StudyS2** | MV-RoboBench SDJ+RTS (n=401) | net_rescue D−C > 5 pp, CI excl. 0 | **−1.50 pp [−6.98, +3.99]**, b=61 c=67 | **THINKING DOES NOT PAY AT 32B** — S1's 4B negative is not scale-specific (CI upper < 5: absence at the pre-registered size) |
| **StudyT** | SiGNgapore2D 40 signs | termination at 8192 ≥ 36/40 and Wilson LB > 70% | **34/40 = 85.0% [70.9, 92.9]** (within-cap 30/35); 4B 70% → 8B 90% → 32B 85% | **TREND DOES NOT CONTINUE — indistinguishable from 8B**; never-terminate at 24,576: 5% (2/40) vs 4B 20% (8/40) |

## Key numbers

**Thinking effect at 32B (paired, same stack):**
| workload | n | D−C pp [95% CI] | b / c | answers changed |
|---|---|---|---|---|
| ERQA spatial | 118 | +2.5 [−5.1, +11.0] | 13 / 10 | 19.5% |
| ERQA overall | 400 | +3.2 [−1.5, +8.0] | 53 / 40 | 23.3% |
| MV-RoboBench | 401 | −1.5 [−7.0, +4.0] | 61 / 67 | 31.9% |
| SiGNgapore2D (accuracy, validated scorer) | 40 | −5.0 (35.0% vs 40.0%) | 5 / 7 | 30% |

**Size effect (32B vs 4B):** ERQA spatial instruct +10.2 pp [0.0, +19.5] (paired, cross-stack); thinking
+5.9 [−4.2, +16.1]; total D−A +12.7 [+3.4, +22.0]. MV-RoboBench (cross-study vs StudyS1 aggregates, unpaired):
instruct +10.5 [+3.6, +17.2], thinking +8.0 [+1.1, +14.7].

**Termination:** 32B-T closes `</think>` in 100% of ERQA and 99.5% of MV-RoboBench trials (4B-T on ERQA:
1.2% budget hits). On signs: 85% at 8192 (4B 70%, 8B 90%); by 24,576 only 2/40 (5%) never terminate vs 4B's 8/40 (20%), and the never-terminating signs are disjoint across scale (ladder re-runs reproduced earlier tokens exactly, 8/8). Peak reserved VRAM reached 99.2 GB at 24,576 tokens — the card's limit.

**Latency cost of thinking at 32B (same hardware):** ERQA D/A_h100 ≈190–200×; MV-RoboBench D/C 92×;
signs T32 median 210 s vs I32 2.8 s (at 8192).

## Caveats that apply across the night
1. Single seed per thinking arm; CIs cover question sampling only.
2. Decoding confound: thinking arms sampled (CFG-A, temp 0.6 — model card says 1.0), instruct greedy.
3. Cross-stack noise: greedy 4B-Instruct changes 14/400 (3.5%) ERQA answers between A6000 and H100 stacks —
   bounds any A6000-vs-H100 pairing (StudyR C−A, D−B, D−A). The primary D−C tests are all same-stack.
4. StudyS1 is flash-only (open reproducibility gap); StudyS2's 4B terms are cross-study aggregates.
5. 4B-Thinking ERQA 43.2% vs published 47.3% (−4.1 pp), inherited from StudyQ; unexplained (also StudyS0).
6. Power: StudyR spatial is under-powered for 5 pp; StudyS2 is not decisive for small effects but its CI
   excludes the 5 pp threshold; StudyT n=40 detects ~20 pp changes.

Reports: `reports/study_r_device_vs_cloud.md`, `reports/study_s2_mvrobobench_32b.md`,
`reports/study_t_signs_32b.md`.
