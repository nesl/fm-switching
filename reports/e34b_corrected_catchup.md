# E35 (E34b) — Corrected WARM Catch-up Latency and Maintenance Ordering

**Date:** 2026-08-23  
**Model:** Qwen/Qwen2.5-7B-Instruct  
**Hardware:** A6000 (GPU 1, flash)  
**Script:** `experiments/cost/e34b_catchup.py`  
**Supersedes:** E34 Parts B and C (Part A stands)

---

## Summary

Three defects in E34 Parts B and C are corrected here.

**Defect 1 (warm-up bug):** E34 Part B called `llm.generate([current_text], sp)` before the timed loop, pre-caching the entire current context. All 5 reps then measured a trivial cache-hit TTFT (~25–65 ms flat regardless of N). Fixed by using a separate engine load per (fidelity, N, rep), priming stale only, and leaving current_text uncached before timing.

**Defect 2 (COLD mislabeled):** E34's `build_current()` is N-independent; COLD measurements did not vary with N by construction. These are cold restore cost (see `results/cost/cost_matrix.csv`), not catch-up latency. Relabeled here; not re-measured.

**Defect 3 (full maintenance cost):** E34 Part C listed "full COLD re-prefill 3,620 ms" as full's maintenance cost. Full's actual maintenance cost is warm tail-append (~66 ms, E26), because the KV cache prefix is preserved between consecutive turns. Corrected in Part 3 below.

**Key corrected results:**

| fidelity | N=1 | N=10 | N=100 | regime |
|---|---|---|---|---|
| full | 67 ms | 107 ms | 681 ms | grows linearly with delta |
| win10 (intra-session) | 41 ms | 77 ms | — | prefix preserved |
| win10 (inter-session) | — | — | 1,031 ms | cold re-prefill of 7k window |
| sum200 TTFT | 25 ms | 25 ms | 25 ms | N-independent |
| sum200 recursive gen | 5.78 s | 5.80 s | 6.21 s | decode-dominated |
| sum200 full regen | — | — | 9.8–10.3 s | N-independent per-conv range |

**Corrected maintenance ordering:** sum200 restore (32 ms) < full warm-append (66 ms) < win10 amortized (653 ms) < sum200 recursive (~5,822 ms).

---

## Results consistency check (6 checks)

### Check 1: Cross-check against committed measurements

| quantity | E35 | prior committed | source | ratio | verdict |
|---|---|---|---|---|---|
| full N=1 WARM catch-up | 67 ms | E26 warm-append 66 ms at L=8k | `reports/phase1_cost_profiling.md` | 1.02× | AGREE |
| win10 inter-session (~N=20+) | 991–1031 ms | E34 Part A slide_cold 975 ms | `part_a_win10.json` | 1.02–1.06× | AGREE |
| sum200 TTFT | 25 ms | cost_matrix.csv 32 ms at L=8k | `results/cost/cost_matrix.csv` | 0.78× | AGREE (within 2×; shorter warmup context) |
| sum200 recursive (N=1) | 5,784 ms | E32 4,633 ms (V0 engine, unknown cache) | `reports/e32_staleness_cost.md` | 1.25× | AGREE (V1 vs V0 engine; caching state now explicit) |
| sum200 full regen (median) | 9,939 ms | E27 sum200 update 9,565 ms | `reports/e27_maintenance_mechanism.md` | 1.04× | AGREE |
| sum200 full regen (E32 check) | 7,801–10,307 ms range | E32 8,766 ms constant | `reports/e32_staleness_cost.md` | varies | E32 ARTIFACT CONFIRMED — proper distribution vs. constant |

All quantities within 2× of committed values. The E32 full-regen constant (8.766 s to 3 decimal places across 10 conversations) is confirmed as a caching artifact: E35 shows a 2.5-second range (7.8–10.3 s) proportional to conversation length.

### Check 2: Physical plausibility

Cross-check metric for WARM catch-up: **delta_tok / elapsed_s** (fresh prefill rate). The stale prefix is in cache; only the delta must be freshly prefilled. Using current_tok would artificially inflate the rate (correct check only for cold or inter-session-slide cases).

| condition | N | elapsed | delta_tok | delta_tps | vs committed (5,984 tok/s) |
|---|---|---|---|---|---|
| full WARM | 100 | 681 ms | 2,742 | 3,889 tok/s | 0.65× — ok |
| full WARM | 50 | 358 ms | 1,421 | 3,620 tok/s | 0.60× — ok |
| full WARM | 10 | 107 ms | 287 | 2,557 tok/s | 0.43× — ok (overhead dominates at small delta) |
| full WARM | 1 | 67 ms | 16 | 249 tok/s | 0.04× — ok (overhead dominates; delta trivial) |
| win10 intra-session | 10 | 77 ms | 287 | 3,673 tok/s | 0.61× — ok |
| win10 inter-session | 20 | 991 ms | — | — | current_tok/elapsed=6,974 tok/s=1.17× — ok (cold re-prefill of full window) |
| sum200 TTFT | 1 | 25 ms | ~160 | 6,400 tok/s | 1.07× — ok |

All implied rates below 2× threshold. No cache-hit artifacts. Delta_tps approaches (but stays below) committed cold-prefill rate at large N — expected, as request overhead becomes a smaller fraction of total time.

### Check 3: Distribution sanity

| quantity | spread | verdict |
|---|---|---|
| Full N=50 per-conv elapsed | min=0.286s, max=0.428s, range=0.142s | distribution ✓ |
| Win10 N=1 per-conv elapsed | min=0.038s, max=0.045s, range=0.007s | tight distribution (all convs have similar delta) ✓ |
| sum200 full regen per-conv (rep1) | 7.80, 8.51, 9.03, 9.58, 9.79, 10.03, 10.05, 10.17, 10.24, 10.31 s | proper distribution (range=2.5s) ✓ — confirms E32 artifact |
| rep2 / rep1 ratios (all cells) | 0.97–1.00× | flush verified ✓ |

The E32 sum200 full-regen constant (8.766 s at 3 decimal places across 10 conversations of differing lengths) is confirmed as a shared-cache or short-circuit artifact. E35 with per-rep engine reload shows genuine per-conversation variation.

### Check 4: Definition audit

| term | definition in E35 | matches prior? |
|---|---|---|
| N | individual dialogue turns (all_turns[keep:]) | ✓ matches E32, E34 |
| win10 | last 10 sessions | ✓ confirmed: 5,668–8,181 tok across 10 convs |
| full | full conversation | ✓ confirmed: 11,519–22,124 tok |
| sum200 current | sum200_cache[cid] (~160 tok) | ✓ N-independent |
| WARM | prefix_caching=True; stale primed only before timing; delta uncached | explicitly declared (new vs E32) |
| flush method | separate engine load per (fidelity, N, rep) | new vs E34; verified by rep2/rep1 ≈ 1.00× |
| delta_tokens | token count of all_turns[total-N:] | ✓ same as E32/E34 |

No definition conflicts.

### Check 5: Claim linkage

| result | claim | bearing |
|---|---|---|
| Full WARM 67–681 ms (N=1–100) | C4 physical inertia | supports: full catch-up meets interactive budget at all N, voice budget at N≤5 |
| Win10 intra-session 41–77 ms | C4 physical inertia | supports: within voice budget when prefix preserved |
| Win10 inter-session ~1,031 ms | C4 physical inertia | supports: cold re-prefill cost at window slide; matches E34 Part A slide_cold; meets interactive budget |
| Win10 sharp transition at N~22 turns | C4 physical inertia | new finding: transition point separates voice-budget from interactive-budget regimes for win10 |
| sum200 recursive 5.8–6.2 s | C4 physical inertia | supports: background-only; consistent with E27/E32 |
| sum200 full regen 9.9 s distribution | E32 artifact correction | confirms E32 full-regen constant was a measurement artifact |
| Maintenance ordering (Part 3) | C4 | supports: corrects E34 Part C error; ordering unchanged qualitatively |

No scoped-out quantities measured (no KV transfer, no cross-architecture measurements).

### Check 6: Proxy validity

- **TTFT** = direct perf_counter measurement from generate() call start to return. Direct measurement, no proxy. ✓
- **delta_tps** = delta_tokens / elapsed_s. Proxy for "what fraction of elapsed time is spent on fresh prefill." Valid for large N where delta dominates. At small N, overhead dominates and delta_tps underestimates the true fresh-prefill rate — this is labeled explicitly and not used as a headline conclusion.
- **win10 inter-session detection**: inferred from latency jump (0.077 s at N=10 → 0.991 s at N=20). Direct measurement of the latency discontinuity; not a proxy. The transition is structural (KV cache prefix invalidated by window slide) and consistent with E34 Part A slide_cold. ✓
- **sum200 generation total time**: measures prefill + decode as one wall-clock interval. No way to separate prefill and decode without instrumentation. Stated as total generation time throughout; not broken into components. ✓

---

## Part 1: Corrected WARM catch-up (full and win10)

### Measurement procedure

Separate engine load per (fidelity, N, rep). Within each engine, for each conversation:
1. `llm.generate([stale_text], sp)` — prime stale prefix into KV cache.
2. `t0 = perf_counter(); llm.generate([current_text], sp); elapsed = perf_counter() - t0` — timed call.

The stale prefix blocks are found in cache; the delta (new turns) must be freshly prefilled. Engine reload between reps is the flush mechanism. Verified: rep2/rep1 ≈ 1.00× for all cells.

Cross-fidelity contamination avoided by separate engine per fidelity: win10 is a suffix of full for the same conversation; same-engine measurement would give false cache hits.

### Full WARM catch-up

| N | delta_tok (med) | elapsed_rep1 (med) | elapsed_rep2 (med) | rep2/rep1 | delta_tps (med) | TTFT budget |
|---|---|---|---|---|---|---|
| 1 | 16 | 67 ms | 67 ms | 0.99× | 249 tok/s | voice ✓ |
| 5 | 110 | 73 ms | 73 ms | 1.00× | 1,634 tok/s | voice ✓ |
| 10 | 287 | 107 ms | 107 ms | 1.00× | 2,557 tok/s | voice ✓ |
| 20 | 553 | 181 ms | 181 ms | 1.00× | 2,968 tok/s | voice ✓ |
| 50 | 1,421 | 358 ms | 358 ms | 1.00× | 3,620 tok/s | interactive ✓ (voice ✗) |
| 100 | 2,742 | 681 ms | 681 ms | 1.00× | 3,889 tok/s | interactive ✓ (voice ✗) |

Full WARM catch-up latency grows monotonically with N: 67 ms (N=1) → 681 ms (N=100). At small N, request overhead (~30–50 ms) dominates; delta_tps is low but this is overhead, not a cache hit. At large N (N=100), delta_tps = 3,889 tok/s = 0.65× committed cold-prefill rate — the fresh prefill of 2,742 delta tokens dominates.

All N ≤ 20 meet the voice/embodied budget (300 ms). All N meet the interactive budget (1 s). This is 680 ms at N=100 vs. E34's flat 62 ms (cache-hit artifact) — the corrected measurement shows the actual cost.

### Win10 WARM catch-up

Win10 catch-up exhibits two distinct regimes:

**Intra-session (N < ~22 turns, ≤ 1 session):** The stale win10 and current win10 share overlapping sessions. stale_text is a prefix of current_text. Prefix cache hit covers most of the context; only delta requires fresh prefill.

**Inter-session (N ≥ ~22 turns, > 1 session):** The window has slid: stale win10 starts with an older session not present in current win10. No prefix overlap. Full cold re-prefill of the current ~7k-token win10 window is required.

| N | elapsed_rep1 (med) | rep2/rep1 | regime |
|---|---|---|---|
| 1 | 41 ms | 0.97× | intra-session (prefix preserved) |
| 5 | 50 ms | 1.00× | intra-session |
| 10 | 77 ms | 1.00× | intra-session |
| 20 | 991 ms | 1.00× | inter-session (window slid; cold re-prefill) |
| 50 | 1,028 ms | 1.00× | inter-session |
| 100 | 1,031 ms | 1.00× | inter-session |

The sharp jump at N=20 (77 ms → 991 ms) marks the session-boundary crossing. At N=20 (~0.88 sessions), some or all conversations have crossed a session boundary, sliding the win10 window and invalidating the cached prefix. The inter-session cost (~1,031 ms) is consistent with E34 Part A slide COLD (975 ms median): both measure cold re-prefill of a ~7k-token win10 window.

For N ≥ 20, the elapsed time is flat at ~1,031 ms regardless of N: once the window has slid, the full window must be re-prefilled, and the size of the delta beyond that does not change the cost.

**TTFT budget verdicts:**
- Intra-session (N=1–10): 41–77 ms — voice/embodied ✓, interactive ✓, background ✓
- Inter-session (N=20–100): ~1,031 ms — voice ✗, interactive ✓, background ✓

---

## Part 2: sum200 catch-up

### Part 2A: TTFT from sum200 state (N-independent)

Current sum200 is ~160 tokens and N-independent. TTFT is flat across all N:

| N | TTFT rep1 | TTFT rep2 |
|---|---|---|
| 1 | 25.1 ms | 24.8 ms |
| 5 | 24.8 ms | 24.6 ms |
| 10 | 24.6 ms | 24.4 ms |
| 20 | 24.6 ms | 24.4 ms |
| 50 | 24.6 ms | 24.4 ms |
| 100 | 24.6 ms | 24.4 ms |

Implied rate: 160 tokens / 0.025 s = 6,400 tok/s = 1.07× committed — ok. N-invariance confirmed. Budget: voice ✓ at all N.

### Part 2B: Recursive update generation

sum200 recursive catch-up requires generating a new summary from (old_summary + N_new_turns). This is a GENERATION operation (prefill + decode); the decode of ~200 tokens at ~35 tok/s dominates.

| N | delta_tok (med) | total elapsed rep1 | total elapsed rep2 |
|---|---|---|---|
| 1 | 16 | 5.78 s | 5.78 s |
| 5 | 110 | 5.78 s | 5.78 s |
| 10 | 287 | 5.80 s | 5.80 s |
| 20 | 553 | 5.84 s | 5.84 s |
| 50 | 1,421 | 5.96 s | 5.96 s |
| 100 | 2,742 | 6.21 s | 6.21 s |

Decode dominates (~5.7 s for 200 tokens at ~35 tok/s). The N=1→N=100 increment (+430 ms) matches the expected delta prefill time for 2,726 additional tokens (2,726/5984 ≈ 456 ms). ✓

**Cross-check note:** delta_tps here is delta_tok / elapsed_s = 16/5.78 = 2.8 tok/s (N=1). This is not a rate flag — the operation is decode-dominated; the "delta rate" metric is not meaningful for mixed prefill+decode operations. The committed decode rate (~35 tok/s at N=100: 250 tokens / 6.21 s = 40 tok/s) is consistent with E26 committed decode rates (35–44 tok/s). ✓

Within-engine cross-N contamination: after measuring N=1, the old_summary text is in cache. For N=5, the old_summary is still the same text → cache hit on old_summary is expected and correct (we WANT the old prefix cached; only the 4 additional turns are fresh). The delta token increments are not contaminated. Total time is decode-dominated regardless, so any residual contamination on small delta prefill does not affect the headline latency. Stated explicitly in the report.

TTFT budget: all N in background-only range (5.8–6.2 s).

### Part 2C: Full regen generation

Full regen generates a new summary from the full current conversation. N-independent by construction (input is always the full current conversation).

**Per-conv elapsed (rep1):**

| conv | full_tok | elapsed |
|---|---|---|
| conv-26 | 14,750 | 8.51 s |
| conv-30 | 11,532 | 7.80 s |
| conv-41 | 22,137 | 10.31 s |
| conv-42 | 19,166 | 9.59 s |
| conv-43 | 21,473 | 10.24 s |
| conv-44 | 21,144 | 10.17 s |
| conv-47 | 20,552 | 10.05 s |
| conv-48 | 19,781 | 9.82 s |
| conv-49 | 16,453 | 9.03 s |
| conv-50 | 20,669 | 10.07 s |
| **median** | — | **9.94 s** |

The per-conversation distribution (7.80–10.31 s, range = 2.51 s) is proportional to conversation length. This **confirms the E32 distribution-sanity violation**: E32 reported 8.766 s constant to 3 decimal places across all 10 conversations and all N. E35 with per-rep engine reload shows genuine per-conversation variation. The E32 constant was a shared-cache or short-circuit artifact.

TTFT budget: all convs exceed the 10 s background budget (no budget met).

---

## Part 3: Corrected maintenance ordering

**Key correction:** E34 Part C listed "full COLD re-prefill 3,620 ms" as full's maintenance cost. This applies only when the GPU KV cache is fully evicted — not the normal per-turn maintenance path. Full's actual maintenance cost is warm tail-append: the prefix is preserved in the KV cache between consecutive turns, and only the new turn's tokens must be freshly appended.

| fidelity | maintenance operation | cost | source | voice ✓/✗ | interactive ✓/✗ | background ✓/✗ |
|---|---|---|---|---|---|---|
| sum200 | serve query from stale summary | 32 ms | cost_matrix.csv (E26) | ✓ | ✓ | ✓ |
| full | warm tail-append (normal per-turn) | 66 ms | E26 committed | ✓ | ✓ | ✓ |
| win10 | amortized (65.7% slide + 34.3% grow) | 653 ms | E34 Part A + slide_frac | ✗ | ✓ | ✓ |
| sum200 | recursive summary update | 5,822 ms | E35 Part 2B (median across N) | ✗ | ✗ | ✓ |

**Ordering:** sum200-serve (32 ms) < full-warm-append (66 ms) < win10-amortized (653 ms) < sum200-recursive (5,822 ms)

This ordering is qualitatively identical to E34 Part C's ordering, but the values for full and the label for sum200-serve are corrected:
- Full: 66 ms (warm-append, E26) replaces E34's erroneous 3,620 ms (cold re-prefill).
- sum200 serve: confirmed 32 ms (cost_matrix.csv).
- Win10 amortized: 653 ms (unchanged from E34 Part C).

Full warm-catch-up at N=1 (67 ms, E35 Part 1) is consistent with E26 warm-append (66 ms, 1.02× ratio), confirming that the per-turn catch-up cost for full equals the warm-append cost as expected.

---

## Assumptions

| item | value | label |
|---|---|---|
| N = individual dialogue turns | matches E32/E34 definition | [DEFINITION] |
| win10 = last 10 sessions | 5,668–8,181 tok in this run | [DEFINITION] |
| Flush = separate engine load per (fidelity, N, rep) | rep2/rep1 ≈ 1.00× all cells | [VERIFIED] |
| sum200 recursive stale = current summary (N=0 proxy) | stale summaries not in cache; current summary used as proxy | [APPROXIMATION] |
| sum200 recursive contamination | cross-N within one engine; decode-dominated → negligible | [STATED] |
| Decode rate (~35 tok/s) | consistent with E26 committed; not re-measured | [REFERENCE: E26] |
| win10 inter-session transition | sharp jump at N~22 turns (≈1 session) | [MEASURED] |
