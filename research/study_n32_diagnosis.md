# D301 n32 DIAGNOSIS (2026-11-26T18:34Z). PROVISIONAL, FOR A USER DECISION; CPU, committed cells (n16 1x, n16 3:11:2 preD249, n20 and n24 40:40:20 preD249, n32 3:11:2), read-only, nothing queued; scripts scratchpad qq3/. Mixes differ across sizes: one point per size.
## (1) Engine utilisation (the coordinator scrape was off; a separate 10 s sampler host_counters_d211.log exists in every cell: nvidia-smi util and vLLM counters, no running/waiting gauges; its local_compute tokens equal the request.jsonl uncached sum exactly (n32 5,461,366): reconstruction validated)
| cell | GPU util mean / windows >= 90 | uncached tok/s mean (p90) | in flight mean / p90 / max | time with >= 1 in flight | budget booked (s) | reconstructed P x uncached (s) |
|---|---|---|---|---|---|---|
| n16 1x | 92.6 / 84% | 4,243 (4,654) | 5.1 / 9 / 46 | 98% | 970 | 928 |
| n16 3:11:2 | 75.6 / 53% | 2,887 (3,720) | 2.2 / 5 / 23 | 83% | 617 | 632 |
| n20 | 94.7 / 91% | 4,319 (4,657) | 4.4 / 7 / 19 | 98% | 974 | 945 |
| n24 | 94.1 / 90% | 4,296 (4,759) | 4.6 / 8 / 24 | 98% | 980 | 941 |
| **n32 3:11:2** | 94.8 / 92% | 4,559 (5,891; max 6,598) | **18.5 / 36 / 72** | 98% | **585** | **996** |
Reference rates: committed COLD_PREFILL_TOK_S 4,500 at 11k to 3,800 at 28k (baselines/costs.py:81); D162 fit 5,481 tok/s; the cost_matrix.csv has no 32B/H100 row. n32 ran at the committed cold rate for the whole 1,200 s (5.46M uncached tokens take 1,214 s at 4,500). **THE 585 GPU-s BUDGET FIGURE DOES NOT MATCH THE ENGINE: the engine was saturated and the budget UNDER-COUNTED by 411 s (996 reconstructed against 585 booked). Cause: a build is booked at PIECE tokens only (coordinator.py:1526 "a build prefills exactly its piece"): at n32 286 of 536 robot pieces re-prefilled an EVICTED prefix, 2.22M tokens above piece size = 405 s; the uncharged intercept (219 s) and decode are minor.** So the 1,200 s budget was never binding (49 percent) while the GPU was at 95 percent util. Caveat: nvidia-smi util means a kernel was active, not that throughput was at its maximum; host CPU contended in n32 and n16 1x (other users about 32 cores).
## (2) The 170 robot REJECTs (all believed COLD; belief gives built tokens only, 4k to 10k)
37 first declines and 133 repeats across 37 sessions and all 22 robots; 23 sessions with 3 or more declines hold 88 percent; gap between declines within a session p50 14 s; 116 repeats within 60 s of the previous decline (the D261 latch pattern). The arm's readiness_tokens is not in the decision record: proxied from the session's prompt tokens (p50 13.9k, 5.2k to 26.3k), so the recompute is approximate: the est > slack + 0.5 s test (hybrid_arm.py:434-437) fires on the proxy for 77 of 170, est > slack for 99; the other 71 are either est_tokens above the proxy or latch repeats (cannot separate). **Post-hoc residency: 38 of 170 had a prior session request at least 50 percent cached; the next session request was at least 50 percent cached for 28 (23 within 20 s), 0 percent for 108, absent for 24; residency.jsonl tier before the decline cold for 151, gpu for 19: most were truly cold, roughly 20 to 25 percent had a warm signal (not reconciled).** Engine load at the rejects: p50 24 requests in flight (p90 35, max 61); queue ahead (in-flight uncached tokens / 4,500) p50 18.8 s, p10 0.57 s; only 23 of 170 had queue ahead of 1 s or less. A cold rebuild within the slack (about 2.9 s), cold TTFT alone: at the committed rate 71 fit alone and 99 cannot even on an idle engine (contexts above about 13k; 28 sessions above 19.5k); at the D162 rate 97 fit, 73 cannot; adding the measured queue ahead only 9 (committed) or 15 (D162) fit; 62 to 82 are blocked only by the queue. **The engine was almost never idle enough for a cold rebuild, and for about 58 percent of the rejects (long histories) it could not meet 3 s even when idle.**
## (3) Single-shot (assistive, 475)
within_L 145 (the harness says 142; the 3 probably undelivered); of about 330 not on time: 316 requested but late, ALL cold (normal for single-shot: median uncached 471 tokens); dispatch wait p50 0.10 s, solo TTFT p50 0.15 s; **engine-queue residual p50 14.5 s (p10 3.6, p90 38; 24 requests ahead at submit)**; classes: engine-queue dominant 267, dispatch plus queue 13, other 35, dispatch-only 1; 14 never released. With no queue every one would be on time (about 0.25 s against a 2 s deadline). On time elsewhere: n16 1x 351/357, n16 3:11:2 224/238, n20 470/475, n24 585/597.
## (4) D280 FAIR oracle share (unmodified oracle_bootstrap.arm_units; floor = the pooled D281 table value A_RD 0.257732 for recall and A_SD 0.547985 for single-shot, NOT per-question device answers; served credit A_RC_H 0.5688 for context at least 2,000 tokens or A_RC_N 0.2122; HINDSIGHT uses each cell's per-question device_correct rows)
| cell | FAIR both | FAIR recall | FAIR single-shot | HINDSIGHT both |
|---|---|---|---|---|
| n16 1x | 0.966 (reproduced) | 0.955 | 0.983 | 0.495 |
| n16 3:11:2 | 0.803 | 0.769 | 0.941 | 0.431 |
| n20 | 0.907 | 0.849 | 0.989 | 0.488 |
| n24 | 0.920 | 0.874 | 0.980 | 0.444 |
| **n32 3:11:2** | **0.165** | 0.127 | 0.305 | 0.110 |
n32: policy minus floor 27.2 against oracle minus floor 164.8 over 892 units. **CORRECTION: per-question device answers DO exist for n32 in cell.json robot_rows (harness device_only_accuracy 0.278177); the oracle FAIR value does not use them; my earlier "no device answers for this mix" referred to the older n16 3:11:2 cell.**
## (5) Cloud-correct rescored at the D281 device credit 0.257732 (cbd_expected = cloud-correct + 0.257732 x (questions not answered by the cloud on time))
| cell | cloud on-time | cloud-correct | harness cbd | cbd_expected | share |
|---|---|---|---|---|---|
| **n32** | 53/417 | 34 | 134 (0.321) | **127.8** | **0.3065** |
| n16 3:11:2 | 176/229 | 107 | 127 (0.555) | 120.7 | 0.527 |
| n16 1x | 126/132 | 82 | 83 (0.629) | 83.5 | 0.633 |
| n20 | 135/159 | 81 | 86 | 87.2 | 0.548 |
| n24 | 159/182 | 95 | 100 | 100.9 | 0.554 |
The harness device column at n32 is 100 correct of 364 (0.2747, real per-question 4B-I answers) against 93.8 expected: +6.2 questions. Cloud accuracy on the served 53 is 0.642. (n20 and n24: the harness cbd counts rows with device answers: partial, see the fleet-size note.)
## Scaling (one point per size, mixes differ)
| cell | robot cloud on-time | rejects | dashcam on-time | peak resident (GPU / host) | evictions | belief_to_cold |
|---|---|---|---|---|---|---|
| n16 1x | 95.5% | 0 | 71% | 48,975 / 0 | 0 | 3 |
| n20 | 84.9% | 15 (9%) | 52% | 53,192 / 0 | 0 | 4 |
| n24 | 87.4% | 12 (7%) | 36% | 46,443 / 0 | 0 | 9 |
| n16 3:11:2 | 76.9% | 21 (9%) | 81% | 63,215 / 9,337 | 2 | 32 |
| **n32 3:11:2** | **12.7%** | **170 (41%)** | **13%** | 65,775 / 70,352 | 33 | 111 |
**Saturating the engine does not by itself collapse robots** (n20 and n24 sit at 94 percent GPU util with robots at 85 to 87 percent); **the n32 collapse follows memory oversubscription (about 5.75k tokens per robot against 62,944 GPU tokens): rebuild storms, rejects and queue growth.**
## Operating point (a GUESS interpolated from two 3:11:2 points; n24 3:11:2 is already queued per the user, D302)
n16 3:11:2 is healthy (77 percent) and AT the cap (63,215, 100 percent); a larger 3:11:2 fleet only moves past it. **n24 3:11:2 (17 robots) would have about 98k resident demand (1.55 times the cap); linear interpolation on robots gives about 40 percent robot on-time: NOT "healthy but near the cap".** A knee may exist (the 40:40:20 series stayed at 85 to 87 percent) but there is no data between 11 and 22 robots. The agent's alternative: `covex-v6-fair-final 20 4 _c3-11-2_L3_epg_rq30` (about 4 dashcam, 14 robots, 2 assistive; roster rounding to verify on a dry run; linear guess about 60 percent robot on-time, resident demand about 80k = 1.28 times the cap). If health certainty is wanted, stay at n16 3:11:2.
