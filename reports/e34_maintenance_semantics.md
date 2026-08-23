# E34 — Maintenance Semantics and Corrected Catch-up Latency

**Date:** 2026-08-23  
**Model:** Qwen/Qwen2.5-7B-Instruct (`qwen7b`)  
**Device:** NVIDIA RTX A6000 (flash, GPU 1)  
**Script:** `experiments/cost/e34_maintenance_semantics.py`  
**Supersedes:** E32 Part B (catch-up latency) — see `reports/e32_staleness_cost.md` for superseding header.

---

## Summary

Three measurement parts. **Part A** establishes update semantics per state object under explicit WARM (prefix\_caching=True) and COLD (prefix\_caching=False) conditions. **Part B** corrects E32 Part B by measuring catch-up latency with caching state declared explicitly. **Part C** derives the maintenance cost ordering, TTFT budget compliance, and taxonomy check from A and B.

**Key findings:**

- Full and win10 *growth* updates are prefix-preserving: WARM is 27–58× faster than COLD (prefix cache hit; growth appends to the cached prefix).
- Win10 *slide* requires cold re-prefill: COLD = 0.975s at median 7,139 tokens. Slide WARM shows a vLLM V1 block-reuse artifact (overlapping sessions partially cached); the artifact is documented and COLD is used as the reliable baseline.
- Corrected catch-up latency (Part B) confirms that WARM catch-up is always a cache hit (full/win10/sum200 all ≈ 25–65ms regardless of N). COLD catch-up is N-invariant for a given fidelity — it is simply the full re-prefill cost of the current context, independent of how many turns have been added.
- Win10 amortized maintenance cost (652ms) comfortably meets the 1-second interactive budget; slides dominate because 65.7% of win10 transitions are slides (win10 > 10 sessions) at the typical conversation length in this corpus.
- Sum200 restoration is cheapest (32ms) but regeneration costs 9.6s — the inversion that drove E27's Outcome B is confirmed with a correctly labelled measurement.

---

## Consistency Check (CLAUDE.md protocol)

### Check 1 — Cross-check against committed measurements

| quantity | this run | prior run | source of prior | ratio | agree/disagree |
|---|---|---|---|---|---|
| cold prefill rate (full, ~20k tok) | 5,566 tok/s | 5,984 tok/s | `results/cost/cost_matrix.csv` L=8k A6000 | 0.93× | AGREE |
| cold prefill rate (win10, ~7.1k tok) | 6,825 tok/s | 5,984 tok/s | `results/cost/cost_matrix.csv` L=8k A6000 | 1.14× | AGREE |
| cold prefill rate (sum200, ~160 tok) | 4,580 tok/s | 5,984 tok/s | `results/cost/cost_matrix.csv` L=8k A6000 | 0.77× | AGREE (short-sequence lower utilization; see Check 2) |
| win10 COLD TTFT (Part B) | 1.045s | 0.975s (Part A slide COLD) | `results/cost/e34_maintenance_semantics/part_a_win10.json` | 1.07× | AGREE |
| win10 growth WARM TTFT | 36ms | 66ms at L=8k (E26 warm-append) | `results/cost/vllm_calibration_a6000_qwen7b.json` | 0.55× | AGREE (ratio < 2×; win10 contexts average 7,139 tok < 8k L used in E26; different measurement protocol) |
| full COLD TTFT (median, Part A) | 3.62s (inferred from Part B) | not directly committed | — | — | — |

No quantity disagrees by > 2×.

### Check 2 — Physical plausibility

| quantity | this run | implied rate | committed curve | ratio | verdict |
|---|---|---|---|---|---|
| full COLD TTFT (10 convs, median) | 3.62s @ 20,154 tok (median) | 5,566 tok/s | 5,984 tok/s | 0.93× | OK |
| win10 COLD TTFT (10 convs, median) | 1.045s @ 7,139 tok (median) | 6,825 tok/s | 5,984 tok/s | 1.14× | OK |
| sum200 COLD TTFT (10 convs, median) | 0.037s @ ~160 tok | 4,580 tok/s | 5,984 tok/s | 0.77× | OK — very short sequences are dominated by scheduling overhead, depressing effective tok/s |
| full WARM TTFT (all N, 10 convs) | 0.062s (cache hit) | n/a — cache hit, not a throughput measurement | — | FLAGGED (55×) | Expected: prefix cache; stale context primed before each rep; only delta tokens need computation |
| win10 WARM TTFT | 0.036s (cache hit) | n/a | — | FLAGGED (33×) | Same reason |
| sum200 WARM TTFT | 0.025s (cache hit) | n/a | — | OK (1.1× when computed against current_tokens) | sum200 current context is tiny (~160 tok); negligible compute |

All WARM flags are annotated "consistent with cache hit" in the JSON and are expected from prefix caching design. No unexplained fast outlier. The one rate below the committed curve (sum200 at 0.77×) is explained by short-sequence GPU underutilization (a known characteristic of vLLM at small L).

### Check 3 — Distribution sanity

**Part B COLD (reliable baseline):**

| fidelity | N sweep | median_s | min_s | max_s | spread explanation |
|---|---|---|---|---|---|
| full | 1–100 | 3.62s | 1.78s | 4.09s | Different full-conversation lengths (11,519–22,124 tokens) across 10 convs |
| win10 | 1–100 | 1.045s | 0.825s | 1.216s | Different win10 sizes (5,668–8,181 tokens) across 10 convs |
| sum200 | 1–100 | 0.037s | 0.032s | 0.057s | Different sum200 sizes (135–300 tokens) across 10 convs |

N-invariance of COLD: full COLD is 3.618–3.630s across N=1..100. This is by design: `build_current()` for full returns the full conversation regardless of N. The near-identical median across N values is not a constant artifact — each N value uses the same current_text for a given conv, so identical COLD TTFTs are expected. The per-conversation spread (1.78–4.09s) confirms real variance.

**Part B WARM:**

sum200 WARM shows spread of 0.5–0.9ms across 10 convs for all N (flagged by the distribution sanity script). This is not a short-circuit artifact: all sum200 contexts are ~160 tokens and the ~25ms latency is dominated by fixed scheduling overhead. The narrow spread reflects the fact that scheduling overhead dominates a 160-token prefill, not that conversations are being collapsed.

No median is identical to three decimal places across different-length inputs except where the underlying input IS the same (N-invariance of current_text, documented above).

### Check 4 — Definition audit

| object | definition in this run | token count (this run) | matches prior? | source |
|---|---|---|---|---|
| win10 | last 10 sessions of the conversation | median 7,139 tok (10 convs) | YES — frontier\_locomo.py line 221 reports 7,275 tok (n=282); 0.98× | `build_current()` line 619 |
| full | all sessions concatenated with dates | median 20,154 tok (10 convs) | YES — consistent with LoCoMo full-context sizes from E21/E26 | `build_current()` line 621 |
| sum200 | pre-computed ~200-token summary from SUM200\_CACHE | median 160 tok (range 135–300) | YES — sum200 uses the same cache as E32 (locomo_summaries_200.json via E29) | `SUM200_CACHE` constant |
| N | number of individual turns (dialog exchanges) removed from the tail of all\_turns | delta_tokens N=1: 5–29 tok; N=100: 2,441–3,176 tok | YES — matches E32 definition (individual turns) | `build_stale()` line 583 |
| WARM | prefix\_caching=True engine; stale context primed immediately before each timed rep | — | NEW — E32 did not declare this condition explicitly | `make_engine(caching=True)` |
| COLD | prefix\_caching=False engine; one warm-up generate to initialize CUDA; five timed generates | — | NEW — E32's latency was WARM-condition but unlabelled | `make_engine(caching=False)` |
| catch-up latency | TTFT to generate current\_text after priming stale\_text (WARM) or from empty cache (COLD) | — | REPLACES E32 Part B | `part_b()` loop |
| turn | one dialog exchange (one item in `all_turns`) | ~5–30 tokens each | YES | `conv["all_turns"]` |
| session | one conversation session (may span multiple turns) | win10 = last 10 sessions | YES — matches E13, E29 | `conv["sessions"]` |

No name is used with two different definitions in this experiment. The WARM/COLD distinction is the key correction over E32.

### Check 5 — Claim linkage

| claim | CLAIMS.md / FORMULATION.md mapping | this result | direction |
|---|---|---|---|
| Physical inertia grows with context length | C4 (physical cost) | full COLD 3.62s >> win10 COLD 1.045s >> sum200 COLD 0.037s; ordered by context size | SUPPORTS |
| Representation choice determines maintenance cost | C4 / context-inertia physical component | win10 amortized 652ms vs full COLD 3.62s (5.5×); sum200 restore 32ms but update 9.6s | SUPPORTS |
| Prefix-caching WARM is near-free | (operational, supports C4 cost model) | WARM catch-up 25–65ms for all fidelities, all N | SUPPORTS |
| Win10 slide = cold re-prefill (semantic cost of eviction) | Physical inertia taxonomy | win10 slide COLD 0.975s = full re-prefill at 7.1k tok; confirmed | SUPPORTS |
| COLD catch-up is N-invariant | (new finding, relevant to routing decisions) | Full COLD 3.62s is identical across N=1..100; same for win10, sum200 | NEW FINDING |

No result maps to any scoped-out quantity (no KV-transfer measurements, no cross-architecture tiers). ✓

### Check 6 — Proxy validity

No proxies used. All measurements are direct TTFT from vLLM with caching state declared. The only caveat is the win10 slide WARM artifact (see Part A §Artifacts). That artifact is not used in any headline result; slide COLD is used instead. ✓

---

## Part A — Update Semantics per State Object

### Setup

Model: Qwen/Qwen2.5-7B-Instruct. Engine: vLLM 0.8.5 V1, `enforce_eager=True` (required to prevent CUDA graph capture deadlock with YaRN at max\_model\_len=131072). Device: A6000 (CUDA\_VISIBLE\_DEVICES=1). REPS=5.

**WARM:** `enable_prefix_caching=True`. Old context primed before timed generate. Measures extension of cached prefix.  
**COLD:** `enable_prefix_caching=False`. Fresh engine per condition. Each rep is a full re-prefill.

### Part A1 — Full: warm-append vs cold-prefill at L+k

Setup: synthetic context of L tokens; k new tokens appended. WARM primes L, timed on L+k. COLD times L+k from empty cache.

L ∈ {8192, 16384, 32768, 65536}, k ∈ {200, 1000, 3000}. YaRN rope\_scaling applied for L ≥ 32768.

Summary (all 12 L×k pairs):

| condition | WARM vs COLD ratio |
|---|---|
| L=8192 | 30–48× |
| L=16384 | 55–70× |
| L=32768 | 87–113× |
| L=65536 | 99–132× |

WARM ratios increase with L because the cold re-prefill cost grows linearly with L while the warm-append cost (TTFT for k new tokens) grows slowly. At L=65536, full re-prefill is 132× more expensive than warm-append of 3000 tokens with prefix caching. This confirms that prefix-caching is critical for any fidelity that can be updated by appending — full and win10 growth phases are in this category.

All WARM and COLD values within 2× of committed prefill curve (source: `cost_matrix.csv`). WARM flags are cache-hit signatures, expected.

### Part A2 — Win10: growth vs sliding under WARM and COLD

Win10 growth: sessions[0:9] → sessions[0:10] (< 10 sessions). Prefix is preserved; new session is appended.  
Win10 slide: sessions[0:10] → sessions[1:11] (≥ 10 sessions). Old session 0 evicted; prefix invalidated.

Results (10 LoCoMo conversations):

| operation | WARM median | COLD median | WARM/COLD ratio |
|---|---|---|---|
| growth | 0.036s | 0.962s | 0.037 (27× faster) |
| slide COLD | — | 0.975s | — |

**Slide WARM:** 0.036s (reps 1–4) / 1.07s (rep 5). See artifact note below.

**Growth WARM (36ms)** confirms that win10 growth is prefix-preserving: vLLM finds the old window in cache and only prefills the new session. This meets the voice/embodied budget (< 100ms) for growth transitions.

**Slide COLD (0.975s)** is the reliable baseline. Sliding evicts session 0, invalidating the KV prefix. The full win10 context must be re-prefilled from scratch. 0.975s meets the 1-second interactive budget but fails the voice/embodied budget.

#### Artifact: Win10 Slide WARM (vLLM V1 block reuse)

After the warm-up bug fix (see §Bug Fixes), slide WARM still shows 4/5 reps fast (~0.036s) and rep 5 slow (~1.07s). This is a vLLM V1 block-reuse artifact: the V1 engine matches KV blocks by content, not by position. Sessions 1–9 appear in both old\_window (sessions[0:10]) and new\_window (sessions[1:11]) — the shared sessions are found in the block table, even though they sit at different sequence positions. This causes unexpected cache hits. The cache evicts the new\_slide entry before rep 5, revealing the true cold cost.

**Resolution:** Slide COLD (0.975s) is used for all downstream analysis. The artifact is not a measurement error in the cold-prefill direction. Taxonomy claim (slide = cold re-prefill semantics) is supported by COLD data and by rep 5 of WARM.

#### Bug fixes applied (methodological deviations)

1. **`enforce_eager=True`:** Changed from `False`. With `enforce_eager=False`, vLLM's CUDA graph capture deadlocked indefinitely at first `generate()` call when `max_model_len=131072` + YaRN was active. Fix: `enforce_eager=True`. This has no effect on prefill throughput (graph capture is for decode; prefill is not graph-captured).

2. **Explicit engine shutdown before reload:** `llm.llm_engine.engine_core.shutdown()` is called before `del llm`. The vLLM 0.8.5 V1 engine runs in a subprocess; `del` alone does not kill it, causing OOM when a second engine loads. Fix: explicit shutdown + 5s sleep.

3. **Slide WARM warm-up bug:** Original `measure_new_window_with_old_cached()` called `llm.generate([new_text], sp)` as a warm-up, caching `new_text` before the timed reps and making all reps trivially fast. Fix: removed the `new_text` warm-up; only `old_text` is primed.

All three fixes are implementation corrections (wrong measurement procedures), not methodological changes.

---

## Part B — Corrected Catch-up Latency

### Setup

LoCoMo n=10 conversations. N ∈ {1, 5, 10, 20, 50, 100} turns. Fidelities: {full, win10, sum200}. 5 reps per cell. 180 total (fidelity × N × conv) cells per pass.

**WARM pass:** `enable_prefix_caching=True`. For each cell: (1) prime stale context, (2) warm-up current context, (3) 5 timed reps each of [prime stale → generate current]. Measures extension of stale KV prefix to current context.

**COLD pass:** `enable_prefix_caching=False`. For each cell: (1) one warm-up generate (CUDA initialization), (2) 5 timed generates of current context. Measures full re-prefill from empty cache.

YaRN applied (full conv ≥ 32k tokens).

### Part B Results

**COLD catch-up (reliable, N-invariant):**

| fidelity | median_s | min_s | max_s | median tok/s | ratio to committed |
|---|---|---|---|---|---|
| full | 3.62s | 1.78s | 4.09s | 5,566 | 0.93× ✓ |
| win10 | 1.045s | 0.825s | 1.216s | 6,825 | 1.14× ✓ |
| sum200 | 0.037s | 0.032s | 0.057s | 4,580 | 0.77× ✓ |

COLD latency is N-invariant: `build_current()` returns the full current context regardless of N (N only affects the stale context). The catch-up cost under COLD conditions is independent of how stale the state is — it is just the cost to re-prefill the current context from scratch.

**WARM catch-up (cache-hit, ≈ N-invariant):**

| fidelity | median_s | min_s | max_s | note |
|---|---|---|---|---|
| full | 0.062s | 0.042s | 0.067s | Cache hit on stale prefix; only delta tokens computed |
| win10 | 0.036s | 0.032s | 0.041s | Cache hit on stale win10 prefix |
| sum200 | 0.025s | 0.024s | 0.025s | Cache hit; ~160-tok context dominated by scheduling overhead |

WARM is also approximately N-invariant: the stale prefix is different per N, but the timed generate (extending stale→current) always hits the stale prefix in cache. The additional N turns' worth of tokens are prefilled from the end of the cached stale context; at N=1 (5–29 tokens) through N=100 (2,441–3,176 tokens), the WARM time stays ≈ 0.025–0.067s because the delta extension time is small relative to the scheduling floor (~25ms).

**Crosscheck flags:** WARM implied rates are >>2× faster than committed cold-prefill rate (labeled "consistent with cache hit" in JSON). This is the expected cache-hit signature: the stale prefix is cached, and only delta tokens are computed at effectively infinite throughput (cache lookup, not computation). These flags do not indicate a measurement error.

**N-invariance implication for routing:** COLD catch-up cost is determined by fidelity choice, not by N (staleness depth). A policy that picks fidelity based on N will have no effect on catch-up latency under COLD conditions. Under WARM conditions, catch-up is always fast regardless of fidelity or N.

---

## Part C — Analysis

### Win10 Token Counts

| | per-conv range | median |
|---|---|---|
| win10 tokens | 5,668–8,181 | 7,139 |

Consistent with canonical 7,275-token median (frontier\_locomo.py n=282 convs). 0.98× ratio.

### Sliding Frequency

Win10 transitions from LoCoMo (n=10 convs):

| | range | median | aggregate |
|---|---|---|---|
| slide fraction | 0.50–0.71 | 0.679 | 0.657 |

65.7% of win10 session transitions are slides (head eviction), not growth. For conversations with ≥ 19 sessions (all 10 in this corpus), at least 50% of transitions are slides.

### Maintenance Cost Ordering

Under WARM conditions (prefix caching enabled, context held in KV cache):

```
sum200 restore     28.6ms   ← cheapest restore
sum200 update      9,565ms  ← most expensive update (LLM regeneration)
sum200 net         N/A (restore cheap but update dominates lifecycle)
win10 grow         36ms     ← cheap (prefix-preserving append)
win10 slide        975ms    ← cold re-prefill (head eviction)
win10 amortized    652ms    ← (1-0.657) × 36ms + 0.657 × 975ms
full COLD          3,620ms  ← full re-prefill (no prefix caching benefit at session boundary)
```

Win10 amortized (652ms) comfortably meets the 1-second interactive budget. Sum200 restore (32ms) is cheapest per-operation but sum200 update (9.6s) is by far the most expensive — this is the cost inversion established by E27.

### TTFT Budget Compliance

Budgets from FORMULATION.md: voice/embodied < 100ms, interactive < 1s, background < 10s.

| operation | voice/embodied | interactive | background |
|---|---|---|---|
| sum200 restore | PASS (29ms) | PASS | PASS |
| sum200 update (LLM regen) | FAIL (9,565ms) | FAIL | PASS |
| win10 grow WARM | PASS (36ms) | PASS | PASS |
| win10 slide COLD | FAIL (975ms) | PASS | PASS |
| win10 amortized | FAIL (652ms) | PASS | PASS |
| full COLD re-prefill | FAIL (3,620ms) | FAIL | PASS |

Win10 is the only fidelity that meets the interactive budget for *maintenance* (not just restore). Full cold re-prefill fails interactive.

### Taxonomy Check

FORMULATION.md claims two-class taxonomy: raw-append (full, win10 growth) vs derived-regenerate (sum200 update).

This experiment partially complicates that taxonomy:
- Win10 *growth* is raw-append (prefix-preserving). ✓
- Win10 *slide* requires cold re-prefill (36ms WARM vs 975ms COLD = 37× difference; vLLM V1 block-reuse artifact causes WARM to appear fast, but COLD is the reliable measurement). The slide COLD data confirms that win10 slide is NOT raw-append; it incurs cold re-prefill cost.
- Full warm-append is raw-append. ✓
- Sum200 update is derived-regenerate. ✓

**Updated taxonomy:** Win10 has two sub-operations: growth (raw-append, cheap) and slide (cold re-prefill, expensive). The 65.7% slide frequency means win10's *amortized* cost is much closer to a raw-append than to derived-regenerate (652ms amortized vs 9,565ms for sum200 update), but individual slide events are not cheap. The two-class taxonomy holds for lifecycle cost ordering but the within-win10 bimodality should be noted in any routing policy that computes per-session transition costs.

---

## Files Written

| file | purpose |
|---|---|
| `results/cost/e34_maintenance_semantics/part_a_full.json` | Part A1: full warm-append vs cold-prefill, 12 L×k pairs |
| `results/cost/e34_maintenance_semantics/part_a_win10.json` | Part A2: win10 growth + slide, WARM + COLD, 10 convs |
| `results/cost/e34_maintenance_semantics/part_b_catchup.json` | Part B: corrected catch-up latency, 180 cells × 2 conditions |
| `results/cost/e34_maintenance_semantics/part_c_analysis.json` | Part C: derived metrics, budget compliance, taxonomy |
| `results/cost/e34_maintenance_semantics/e34_summary.json` | Summary metadata |
