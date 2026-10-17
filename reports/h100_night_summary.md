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
1.2% budget hits). On signs: 85% at 8192 (4B 70%, 8B 90%); by 24,576 only 2/40 (5%) never terminate vs 4B's 8/40 (20%), and the never-terminating signs are disjoint across scale (ladder re-runs reproduced earlier tokens exactly, 8/8). Peak reserved VRAM reached 99.2 GB at 24,576 tokens, but peak allocated was 73.6 GB — the gap is allocator fragmentation (reproduced identically under flash-attn on 2026-10-15), not offload.

**Latency cost of thinking at 32B (same hardware):** ERQA D/A_h100 ≈190–200×; MV-RoboBench D/C 92×;
signs T32 median 210 s vs I32 2.8 s (at 8192).

**Basis established 2026-10-16.** All three figures above are **median-of-medians**, verified against the trial files: ERQA D/A_h100 = 198.8× (mean-of-means 328.4×, n=400); MV-RoboBench D/C = 91.6× (mean 153.2×, n=401); signs T32@8192 / I32 = 76.1× (mean 58.4×, n=40/40, medians 209.9 s and 2.76 s). The H100 family is therefore already on the project's canonical basis (adopted 2026-10-16) and no figure here changes. Reference table: `reports/cost_ratio_basis.md`. One caution: StudyR's cross-hardware D/A row (92.9×) and StudyS2's D/C row (91.6×) are numerically almost identical and measure different things — 32B-vs-4B across two GPUs versus thinking-vs-instruct at fixed size on one — so they should not be cited near each other without the distinction.

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

---

## Addendum — flash-attn re-run of all 32B arms (2026-10-15 08:51 → 2026-10-16 02:56)

All 32B arms re-run with `flash_attention_2` (asserted at load, recorded per trial); same questions, decoding,
budgets and seeds. GPU 3 was exclusive throughout (watchdog; 0 contended trials).

| study | primary (SDPA) | primary (flash-attn) | verdict flip? | greedy instruct shift |
|---|---|---|---|---|
| StudyR (ERQA spatial) | D−C +2.5 [−5.1, +11.0] | D−C **+5.1** [−2.6, +13.6] | no (⚠ point estimate crosses 5 pp; CI keeps verdict) | −0.8 pp spatial / 0.0 overall |
| StudyS2 (MV-RoboBench) | net_rescue −1.5 [−7.0, +4.0] | −4.2 [−9.7, +1.0] | no (CI upper < 5 under both) | +0.25 pp |
| StudyT (signs, termination @8192) | 34/40 = 85.0%, indistinguishable from 8B | 29/40 = 72.5%, **reversal** | **sub-class flips** (primary "trend does not continue" stable) | 0.0 pp |
| StudyT never-terminate @24,576 | 2/40 (5%) | 1/40 (2.5%) | no — vs 4B 20% under both | — |

**The cross-study answer is unchanged:** the 4B–8B thinking null persists at 32B under both attention kernels.
Greedy instruct arms move ≤ 0.8 pp (all checks passed), as expected for equivalent kernels; every difference in the
thinking arms is consistent with re-sampled token paths. The StudyT 8,192 sub-classification and the StudyR
primary's distance to 5 pp are inside that sampling noise and should not be over-read.

**99.2 GB peak:** not an SDPA artifact and not offload — flash-attn reproduces it exactly at 24,576 tokens
(allocated 73.6 GB; reserved 99.2 GB = allocator fragmentation). SDPA long-trace latencies stand.

**Speed (prediction not supported):** decode rate by generated length, all thinking-arm trials:

| bucket | SDPA tok/s median (n) | flash-attn tok/s median (n) | flash/SDPA |
|---|---|---|---|
| short (< 1k) | 23.7 (565) | 18.7 (573) | 0.79× |
| medium (2k–6k) | 23.9 (100) | 18.9 (112) | 0.79× |
| long (≥ 12k) | 24.2 (7) | 18.6 (7) | 0.77× |

The prediction "little gain at short context, more at long" did not hold: flash-attn is a **flat ~21% slower at
every length**, and decode rate is flat in length under both backends — attention is not the bottleneck at
batch 1 (consistent with launch/per-step-overhead-bound decode), and flash-attn adds a constant per-step cost in
this HF Qwen3-VL path. Both distributions are tight (IQR ±0.2 tok/s), which argues against fluctuating CPU
contention as the cause, but the runs are cross-session; an interleaved same-process SDPA↔flash-attn timing is
still required before attributing it to the kernel.

**Throughput re-check (2026-10-16, analysis only, no inference; `experiments/erqa/h100_fa2_throughput.py`).**
Prompted by the A6000 retraction (buckets defined by one backend's token count, wall time compared across
re-sampled sequences of different length). The table above was **already** tok/s = `n_generated / latency` per
trial, bucketed by that trial's *own* `n_generated`, so it is not that artifact — **no retraction**. Recomputed
over all 3,793 H100 trials (0 missing `n_generated` or latency; the 800 A6000-reused arm A/B rows excluded),
buckets by own length:

| bucket (own tokens) | SDPA tok/s median [IQR] (n) | flash-attn tok/s median [IQR] (n) | flash/SDPA |
|---|---|---|---|
| < 2k, thinking arms | 23.75 [23.55–23.88] (717) | 18.73 [18.56–18.91] (711) | 0.79× |
| 2k–8k | 23.87 [23.79–23.97] (113) | 18.90 [18.79–18.99] (118) | 0.79× |
| > 8k | 24.13 [23.82–24.21] (19) | 18.80 [18.75–18.85] (33) | 0.78× |

All `< 2k` trials including instruct give 0.73×, but those are 2–7-token answers whose tok/s is dominated by
prefill, not decode. Paired by trial (n=1,681), the tok/s ratio is 0.78–0.82× under every bucketing rule. The
**wall-time** ratio, by contrast, swings from 0.90× to 2.01× in the same 2k–8k bucket depending on which backend's
token count defines it. That is the A6000 artifact reproduced on this data, and it is why only throughput is
reported here. **The SDPA collapse with length does not reproduce on H100:** SDPA is flat at 23.6–24.2 tok/s
from <500 to 16–30k tokens, with a linear fit of 41.8 ms/token and a negligible quadratic term. The H100 (32B) and
A6000 (smaller models, different GPU) results are not directly contradictory, since model, GPU and possibly SDPA
kernel selection all differ; this data cannot say which factor drives the A6000 collapse.

**Backend mismatch:** every cross-size comparison against the 4B/8B baselines (SDPA, A6000) is BACKEND-MISMATCHED
in the flash-attn columns until those are re-run with flash-attn on the A6000; Jetson rows are SDPA permanently.
