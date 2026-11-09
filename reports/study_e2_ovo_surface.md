# StudyE2-ovo-surface: does 32B become correct earlier than 4B within an OVO-Bench entry, and does HISTORY change that?

**E-id:** StudyE2-ovo-surface (pre-registered 2026-11-09 ~15:20, before any computation; authorised by the user).

**Status:** COMPLETE 2026-11-09. SSR stopped by rule; the interaction is not estimable.

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES.** It uses StudyB1's 32B-I rows and StudyB2-ovo-rtv's 4B-I / 8B-I rows. No new inference, CPU only, Instruct only (no Thinking rows).

**Script:** `experiments/orchestration/study_e2_ovo_surface.py`.

**Results:** `results/orchestration/study_e2/e2_results.json`.

## Data, comparability and definitions
- **Rows:** OVO-Bench forward-active tasks (CRR, SSR, REC), one row per sub-query at its own `realtime`, which the rows record as `t`.
  - Models: 4B-I @ebb281ec (StudyB2), 8B-I @0c351dd0 (StudyB2), 32B-I @0cfaf481 (StudyB1).
  - Inputs: RECENT and HISTORY. Every model has all 1,567 sub-queries per input, with 0 errors.
- **Input, stack and decoding:** all three are identical across models within an input.
  - Frames: re-verified here, 0 frame-SHA-256 mismatches and 0 time mismatches across 4B / 8B / 32B on 3,134 (item, input) pairs.
  - Stack: vLLM 0.31.0, same flags.
  - Decoding: greedy, 64 tokens. `b1_common.py` is unchanged (SHA verified).
- **RECENT vs HISTORY is a comparison of inputs:** 9 frames over the last 3 s (~3.1k prompt tokens) vs 37 frames over [0, t] (~12.6k), **about 4× the tokens**. This applies to every input contrast below.
- **Correctness:** the upstream scorer as recorded. CRR: "Yes" / "No" substring or exact Y / N. REC: digits joined == count.
- **Settle point (pre-registered):** per entry and model, the smallest sub-query index k such that the model is correct at every sub-query ≥ k.
  - Its time is that sub-query's realtime, reported relative to the entry's first sub-query.
  - Entries where the model is wrong at the last sub-query **never settle** and are counted separately.
- **Statistics:** paired differences use entries where both models settle. CIs are video bootstrap, 2,000 resamples, seed 0.

## Observations (no interpretation in this section)

### Structure (from the annotations as used by StudyB1 / B2)

| task | entries | sub-queries | per entry min / median / max | entries with ONE question text | sub-query times non-decreasing | gap between sub-queries (s) min / median / max | gold changes per entry | decision |
|---|---|---|---|---|---|---|---|---|
| CRR | 48 | 240 | 5 / 5 / 5 | 48 / 48 | yes | 1 / 8 / 59 | {'1': 48} | analysed |
| SSR | 42 | 629 | 12 / 13 / 28 | 0 / 42 | no | -5 / 3 / 174 | {'4': 26, '6': 14, '8': 1, '10': 1} | **STOPPED**: not the same question over time |
| REC | 82 | 698 | 2 / 7 / 33 | 82 / 82 | yes | 0 / 6 / 87 | {'0': 9, '1': 16, '2': 12, '3': 13, '4': 13, '5': 4, '6': 4, '7': 4, '8': 3, '9': 4} | analysed |

### Accuracy by sub-query index (upstream scorer [video-bootstrap 95 % CI]; n entries with that index)


**CRR**

| model | input | j0 | j1 | j2 | j3 | j4 |
|---|---|---|---|---|---|---|
| 4BI | RECENT | 0.94 [0.86, 0.99] (n 48) | 0.92 [0.85, 0.98] (n 48) | 0.15 [0.05, 0.26] (n 48) | 0.06 [0.00, 0.11] (n 48) | 0.00 [0.00, 0.00] (n 48) |
| 4BI | HISTORY | 0.96 [0.89, 1.00] (n 48) | 0.96 [0.89, 1.00] (n 48) | 0.08 [0.00, 0.19] (n 48) | 0.10 [0.00, 0.28] (n 48) | 0.19 [0.09, 0.33] (n 48) |
| 8BI | RECENT | 0.90 [0.81, 0.97] (n 48) | 0.90 [0.83, 0.96] (n 48) | 0.21 [0.16, 0.29] (n 48) | 0.08 [0.02, 0.17] (n 48) | 0.02 [0.00, 0.08] (n 48) |
| 8BI | HISTORY | 0.79 [0.64, 0.90] (n 48) | 0.71 [0.57, 0.80] (n 48) | 0.33 [0.23, 0.52] (n 48) | 0.35 [0.19, 0.61] (n 48) | 0.33 [0.22, 0.49] (n 48) |
| 32BI | RECENT | 0.81 [0.70, 0.89] (n 48) | 0.81 [0.70, 0.91] (n 48) | 0.27 [0.17, 0.41] (n 48) | 0.06 [0.00, 0.11] (n 48) | 0.02 [0.00, 0.06] (n 48) |
| 32BI | HISTORY | 0.67 [0.55, 0.77] (n 48) | 0.60 [0.48, 0.70] (n 48) | 0.46 [0.35, 0.63] (n 48) | 0.40 [0.24, 0.63] (n 48) | 0.56 [0.45, 0.68] (n 48) |

**REC**

| model | input | j0 | j1 | j2 | j3 | j4 | j5 | j6 | j7 | j8 | j9 | j10 | j11 | j12 | j13 | j14 | j15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4BI | RECENT | 0.66 [0.56, 0.76] (n 82) | 0.39 [0.29, 0.50] (n 82) | 0.36 [0.26, 0.46] (n 81) | 0.15 [0.07, 0.23] (n 74) | 0.02 [0.00, 0.05] (n 60) | 0.00 [0.00, 0.00] (n 50) | 0.02 [0.00, 0.07] (n 43) | 0.00 [0.00, 0.00] (n 31) | 0.00 [0.00, 0.00] (n 27) | 0.00 [0.00, 0.00] (n 26) | 0.00 [0.00, 0.00] (n 21) | 0.00 [0.00, 0.00] (n 16) | 0.00 [0.00, 0.00] (n 15) | 0.00 [0.00, 0.00] (n 13) | 0.00 [0.00, 0.00] (n 11) | 0.00 [0.00, 0.00] (n 10) |
| 4BI | HISTORY | 0.70 [0.60, 0.79] (n 82) | 0.61 [0.51, 0.72] (n 82) | 0.46 [0.35, 0.57] (n 81) | 0.41 [0.30, 0.51] (n 74) | 0.33 [0.22, 0.45] (n 60) | 0.26 [0.14, 0.38] (n 50) | 0.28 [0.16, 0.42] (n 43) | 0.16 [0.03, 0.32] (n 31) | 0.33 [0.15, 0.52] (n 27) | 0.19 [0.04, 0.35] (n 26) | 0.14 [0.00, 0.29] (n 21) | 0.12 [0.00, 0.31] (n 16) | 0.07 [0.00, 0.20] (n 15) | 0.08 [0.00, 0.23] (n 13) | 0.00 [0.00, 0.00] (n 11) | 0.10 [0.00, 0.30] (n 10) |
| 8BI | RECENT | 0.77 [0.67, 0.87] (n 82) | 0.45 [0.34, 0.56] (n 82) | 0.32 [0.22, 0.42] (n 81) | 0.12 [0.05, 0.20] (n 74) | 0.02 [0.00, 0.05] (n 60) | 0.00 [0.00, 0.00] (n 50) | 0.02 [0.00, 0.07] (n 43) | 0.00 [0.00, 0.00] (n 31) | 0.00 [0.00, 0.00] (n 27) | 0.00 [0.00, 0.00] (n 26) | 0.00 [0.00, 0.00] (n 21) | 0.00 [0.00, 0.00] (n 16) | 0.00 [0.00, 0.00] (n 15) | 0.00 [0.00, 0.00] (n 13) | 0.00 [0.00, 0.00] (n 11) | 0.00 [0.00, 0.00] (n 10) |
| 8BI | HISTORY | 0.73 [0.63, 0.83] (n 82) | 0.66 [0.55, 0.76] (n 82) | 0.56 [0.44, 0.65] (n 81) | 0.46 [0.35, 0.57] (n 74) | 0.37 [0.25, 0.48] (n 60) | 0.28 [0.16, 0.40] (n 50) | 0.33 [0.19, 0.47] (n 43) | 0.26 [0.10, 0.42] (n 31) | 0.30 [0.11, 0.48] (n 27) | 0.23 [0.08, 0.38] (n 26) | 0.19 [0.05, 0.38] (n 21) | 0.19 [0.00, 0.38] (n 16) | 0.07 [0.00, 0.20] (n 15) | 0.00 [0.00, 0.00] (n 13) | 0.09 [0.00, 0.27] (n 11) | 0.10 [0.00, 0.30] (n 10) |
| 32BI | RECENT | 0.67 [0.56, 0.78] (n 82) | 0.43 [0.33, 0.54] (n 82) | 0.22 [0.14, 0.31] (n 81) | 0.11 [0.04, 0.18] (n 74) | 0.03 [0.00, 0.08] (n 60) | 0.02 [0.00, 0.06] (n 50) | 0.00 [0.00, 0.00] (n 43) | 0.00 [0.00, 0.00] (n 31) | 0.00 [0.00, 0.00] (n 27) | 0.00 [0.00, 0.00] (n 26) | 0.00 [0.00, 0.00] (n 21) | 0.00 [0.00, 0.00] (n 16) | 0.00 [0.00, 0.00] (n 15) | 0.00 [0.00, 0.00] (n 13) | 0.00 [0.00, 0.00] (n 11) | 0.00 [0.00, 0.00] (n 10) |
| 32BI | HISTORY | 0.77 [0.67, 0.85] (n 82) | 0.74 [0.65, 0.84] (n 82) | 0.67 [0.57, 0.77] (n 81) | 0.55 [0.45, 0.66] (n 74) | 0.42 [0.28, 0.53] (n 60) | 0.32 [0.20, 0.46] (n 50) | 0.30 [0.16, 0.44] (n 43) | 0.13 [0.03, 0.26] (n 31) | 0.19 [0.04, 0.33] (n 27) | 0.08 [0.00, 0.19] (n 26) | 0.14 [0.00, 0.29] (n 21) | 0.19 [0.00, 0.38] (n 16) | 0.00 [0.00, 0.00] (n 15) | 0.08 [0.00, 0.23] (n 13) | 0.27 [0.00, 0.55] (n 11) | 0.00 [0.00, 0.00] (n 10) |

### Settle point per entry (first sub-query after which the model stays correct)

| task | model | input | entries | settle | never settle | settle at the first sub-query | median settle time after the entry's first sub-query (s) |
|---|---|---|---|---|---|---|---|
| CRR | 4BI | RECENT | 48 | 0 | 48 | 0 | — |
| CRR | 4BI | HISTORY | 48 | 9 | 39 | 0 | 40.0 |
| CRR | 8BI | RECENT | 48 | 1 | 47 | 0 | 14.0 |
| CRR | 8BI | HISTORY | 48 | 16 | 32 | 2 | 36.0 |
| CRR | 32BI | RECENT | 48 | 1 | 47 | 0 | 33.0 |
| CRR | 32BI | HISTORY | 48 | 27 | 21 | 3 | 38.0 |
| REC | 4BI | RECENT | 82 | 6 | 76 | 2 | 16.0 |
| REC | 4BI | HISTORY | 82 | 21 | 61 | 12 | 0.0 |
| REC | 8BI | RECENT | 82 | 4 | 78 | 3 | 0.0 |
| REC | 8BI | HISTORY | 82 | 28 | 54 | 15 | 0.0 |
| REC | 32BI | RECENT | 82 | 2 | 80 | 1 | 4.0 |
| REC | 32BI | HISTORY | 82 | 27 | 55 | 19 | 0.0 |

### Paired settle-time difference (big − small, seconds; negative = big settles earlier), entries where both settle; video bootstrap

| task | pair | input | both settle | only big settles | only small settles | mean diff [CI] | median diff | big earlier / same |
|---|---|---|---|---|---|---|---|---|
| CRR | 32BI-4BI | RECENT | 0 | 1 | 0 | — [—, —] | — | — / — |
| CRR | 32BI-4BI | HISTORY | 9 | 18 | 0 | -17.6 [-25.0, -8.3] | -8.0 | 0.56 / 0.44 |
| CRR | 32BI-8BI | RECENT | 0 | 1 | 1 | — [—, —] | — | — / — |
| CRR | 32BI-8BI | HISTORY | 14 | 13 | 2 | -5.7 [-12.6, 2.8] | 0.0 | 0.36 / 0.36 |
| CRR | 8BI-4BI | RECENT | 0 | 1 | 0 | — [—, —] | — | — / — |
| CRR | 8BI-4BI | HISTORY | 9 | 7 | 0 | -10.9 [-19.0, -2.8] | -8.0 | 0.56 / 0.44 |
| REC | 32BI-4BI | RECENT | 2 | 0 | 4 | -14.5 [-37.0, 8.0] | -14.5 | 0.50 / 0.00 |
| REC | 32BI-4BI | HISTORY | 16 | 11 | 5 | -5.4 [-12.1, -0.2] | 0.0 | 0.25 / 0.62 |
| REC | 32BI-8BI | RECENT | 2 | 0 | 2 | 4.0 [0.0, 8.0] | 4.0 | 0.00 / 0.50 |
| REC | 32BI-8BI | HISTORY | 17 | 10 | 11 | -6.6 [-16.4, 0.4] | 0.0 | 0.18 / 0.71 |
| REC | 8BI-4BI | RECENT | 4 | 0 | 2 | -9.2 [-27.8, 0.0] | 0.0 | 0.25 / 0.75 |
| REC | 8BI-4BI | HISTORY | 17 | 11 | 4 | 2.4 [-9.7, 13.9] | 0.0 | 0.18 / 0.53 |

### Interaction: (big − small)HISTORY − (big − small)RECENT, on entries where all four settle

| task | pair | n | mean [CI] |
|---|---|---|---|
| CRR | 32BI-4BI | 0 | not estimable (n = 0) |
| CRR | 32BI-8BI | 0 | not estimable (n = 0) |
| CRR | 8BI-4BI | 0 | not estimable (n = 0) |
| REC | 32BI-4BI | 0 | not estimable (n = 0) |
| REC | 32BI-8BI | 0 | not estimable (n = 0) |
| REC | 8BI-4BI | 2 | 15.0 [0.0, 30.0] |

### Key observations
- **Structure:**
  - **CRR:** 48 entries of 5 sub-queries each, all the same question text, times increasing. The gold changes exactly once per entry, from "No" (type 0) to "Yes" (type 1): typically 0, 0, 1, 1, 1.
  - **REC:** 82 entries of 2–33 sub-queries (median 7), the same question each time ("how many times did they …"), times non-decreasing. The gold count rises 0–9 times per entry.
  - **SSR: STOPPED.** All 42 entries ask about a different procedure step at each sub-query (42 / 42 have more than one question text), and times are not monotone. SSR is not one question asked at different times, so it was not analysed further, per the stop rule.
- **CRR by sub-query:** all three models are right on the first two "No" sub-queries (0.60–0.96).
  - **RECENT:** accuracy falls to 0.00–0.06 at the last sub-query, after the gold has switched to "Yes".
  - **HISTORY:** last-sub-query accuracy is 0.19 (4B), 0.33 (8B), 0.56 (32B).
- **REC by sub-query:** accuracy falls with index under both inputs, as the count grows.
  - **RECENT:** ≤ 0.03 from j4 on, for every model.
  - **HISTORY:** 0.13–0.42 over j4–j11.
- **Settling:**
  - **RECENT:** almost no entry settles: CRR 0–1 per model, REC 2–6.
  - **HISTORY:** CRR settles 9 (4B), 16 (8B), 27 (32B) of 48; REC 21 / 28 / 27 of 82.
- **Paired 32B − 4B settle time, HISTORY:**
  - **CRR:** −17.6 s [−25.0, −8.3] on 9 entries where both settle (median −8 s). 32B settles alone on 18 entries; 4B never settles alone.
  - **REC:** −5.4 s [−12.1, −0.2] on 16 (median 0; 62 % the same sub-query). Only-32B 11, only-4B 5.
- **Paired 32B − 4B settle time, RECENT:** CRR n = 0; REC n = 2 (−14.5 s, CI spans 0).
- **8B (secondary):**
  - **32B − 8B, HISTORY:** CRR −5.7 s [−12.6, +2.8] (n 14); REC −6.7 s [−16.4, +0.4] (n 17).
  - **8B − 4B, HISTORY:** CRR −10.9 s [−19.0, −2.8] (n 9); REC +2.4 s [−9.7, +13.9] (n 17).
- **Interaction (pre-registered):** (32B − 4B)HISTORY − (32B − 4B)RECENT is **not estimable**: no CRR or REC entry settles under RECENT for both models while also settling under HISTORY for both (n = 0). Only 8B − 4B on REC has n = 2.
  - No substitute metric was used, because that would change the registered definition. The per-sub-query accuracies above are the registered descriptive alternative.

## Results consistency check
1. **Cross-check against committed measurements:**
   - CRR per-sub-query accuracies pooled over j reproduce StudyB2-ovo-rtv exactly (32B-I 0.396 RECENT, 0.537 HISTORY).
   - REC pooled over the indices shown (n ≥ 10 per index; 642 of 698 sub-queries) is 0.185 / 0.458, vs 0.170 / 0.421 over all 698. The difference is the omitted high-index tail, where accuracy is lower.
   - Same rows. No > 2× disagreement.
2. **Physical plausibility:** not applicable (no latency or throughput).
3. **Distribution sanity:** accuracies vary by index, model and input. Settle counts and times vary. Paired medians of 0 reflect settling at the same sub-query (62 % on REC HISTORY), and are reported with that fraction.
4. **Definition audit:**
   - Settle point as pre-registered; RECENT / HISTORY as StudyB1; the upstream scorer as recorded.
   - The CRR "No → Yes" pattern means early sub-queries reward a "No" bias. A model that always says "No" is correct on j0–j1 and never settles.
5. **Claim linkage:** FORMULATION.md §Regime uncertainty / §Decisions. With full history, a larger model reaches a stable correct answer earlier within an entry on CRR, which **supports** the idea that capability tiers differ in when they become reliable on a standing question. Under the 3-second window neither tier becomes reliable, so the window, not the tier, limits the outcome there.
6. **Proxy validity:**
   - "Settle time" is a proxy for "becomes correct", and it is strict: one later error un-settles an entry.
   - Entries that never settle are excluded from the paired differences, so the paired n is small (9–17 under HISTORY) and selected toward easier entries.

**Outcome:** no check failed. SSR stopped by rule. The interaction is not estimable (n = 0).

## Interpretation
- **CRR with full history:** 32B settles on the correct answer earlier than 4B: about 18 s earlier on entries where both settle, and on 18 entries only 32B ever settles.
- **REC with full history:** the difference is smaller and mostly zero (same sub-query).
- **With only the last 3 seconds:** no model reliably gets these forward-active questions right once the answer changes. So "does HISTORY change the 32B − 4B difference" cannot be answered with the registered settle metric: under RECENT the difference is undefined, not zero.
- **Descriptively:** the 32B advantage at late sub-queries appears only under HISTORY, but HISTORY also carries about 4× the tokens.
- **CRR's early sub-queries reward saying "No"**, so a high early accuracy is not evidence of understanding.

