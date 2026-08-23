# E33a — Definition Audit and Evidence Ledger

Generated: 2026-08-23  
Analysis only — no GPU, no model inference, no new experiments.  
Every claim traces to a file in this repo. Untraceable items are marked UNTRACEABLE.  
Source files for the audit: `experiments/fidelity/frontier_locomo.py`, `experiments/cost/cost_profile.py`, `experiments/cost/e30_capacity.py`, `experiments/fidelity/e32_staleness.py`, `experiments/cost/e31b_network.py`, `results/cost/cost_matrix.csv`, `results/cost/profiles/a6000_qwen7b.json`, `data/locomo/locomo10.json`, `results/fidelity/e32_staleness/locomo_latency_qwen7b.json`, `results/cost/e31b_network/e31b_summary.json`, `results/cost/e30_capacity/binding_crossover.csv`, `reports/e30_capacity_arithmetic.md`.

Machine-readable outputs: `results/audit/definitions.csv`, `results/audit/evidence_ledger.csv`.

---

## Part 1 — Definition Audit

### 1.1 win-10

**The most critical definitional conflict in the codebase.**

#### Definition A — fidelity experiments (PAPER SETTING)

Source: `experiments/fidelity/frontier_locomo.py`, line 18 (comment), line 221 (code).

```python
# window-10 — last 10 sessions (or all if < 10)
return _sessions_to_text(sessions, dates, max_sessions=10)
```

Concrete definition: the concatenated text of the last 10 `session_N` blocks in the LoCoMo JSON. Each session is a full multi-exchange conversation day (not a single turn).

**Measured token count** (from `data/locomo/locomo10.json`, n=10 conversations, 4 chars/tok estimate):
- Median: **7,275 tokens** (range 5,597–8,548)

#### Definition B — cost profile (WRONG DEFINITION for paper)

Source: `experiments/cost/cost_profile.py`, line 75.

```python
WINDOW_TURNS = 10  # last 10 turns of assembled corpus
```

Concrete definition: the last 10 individual speaker utterances in the assembled turn sequence (~26–49 tokens each).

**Measured token count** (from `results/cost/profiles/a6000_qwen7b.json`): 261–488 tokens across L.

#### Definition used in E30

Source: `experiments/cost/e30_capacity.py`, line 75.

```python
WINDOW_TOKENS = 400  # jetson profile shows 261–488 tok across L; use midpoint
```

This imports Definition B and applies it to the capacity calculation. **The comment traces to the cost profile, not to the fidelity experiment.** The two definitions disagree by 18×.

#### Which definition is correct for the paper?

The paper's claim is about the win-10 representation used in the fidelity experiments (E05, E10, E13, E27, E29, E32). All of those experiments use `frontier_locomo.py` or `e32_staleness.py`, both of which use Definition A (last 10 sessions). The cost profile is an implementation artifact measuring a different object. **Definition A (7,275 tokens median) is correct for all cost capacity reasoning about the paper's win-10.**

#### Corrected E30 capacity under the correct win-10 definition

E30's memory capacity table for win-10 (A6000 edge tier):

| | E30 (reported) | Corrected |
|---|---|---|
| Token count | 400 | 7,275 |
| KV/session | 22.9 MB | 417 MB |
| N_memory (A6000, 32.6 GB usable) | **1,421** | **78** |

E30's accelerator demand for win-10:
- E30 used restore_ms = ~65 ms (from cost_matrix.csv `window` row, which measures 10-turn window restore)
- Correct win-10 restore ≈ 1,292 ms (interpolated from cost_matrix.csv `incr_cold` at L=4k→716 ms, L=8k→1,458 ms, for 7,275 tokens)
- E30 N_accel(win10, A6000, ri=60s) = 60,000 / 65 = 923; **corrected = 60,000 / 1,292 = 46**

Corrected binding crossover for win-10 at A6000:
- ri_crossover = N_memory × restore_ms = 78 × 1.292 = **~101 s** (E30 claimed 57 s for L=8k)

**The qualitative memory-ordering result survives:** sum-80 ≫ sum-200 > win-10 > full remains true. The sum-80 and sum-200 definitions are unchanged (80-token and 200-token budgets respectively) and their N_memory rows are unaffected. However, all quantitative win-10 claims in E30 — N_memory, N_accel, binding crossover — are superseded.

---

### 1.2 sum-80

Source: `experiments/fidelity/frontier_locomo.py` (summarizer call).  
Definition: 80-token budget passed to the LM summarizer. Measured output on LoCoMo ≈ 51 tokens actual; the budget determines the maximum decode cost.  
Status: **consistent across all experiments.** No conflict.

### 1.3 sum-200

Source: `experiments/fidelity/frontier_locomo.py` (summarizer call).  
Definition: 200-token budget passed to the LM summarizer. Measured output on LoCoMo ≈ 113 tokens actual.  
Status: **consistent across all experiments.** No conflict.

### 1.4 full

Source: `experiments/fidelity/frontier_locomo.py`, full session text construction.  
Definition: complete concatenated text of all prior sessions.  
Measured on `data/locomo/locomo10.json` (n=10): median 20,470 tokens (range 11,404–23,510; 4 chars/tok estimate).  
Status: **consistent.** E30 full rows use L (the variable context length) for KV capacity, not the measured LoCoMo value. This is correct for the capacity sweep; the LoCoMo measurement characterizes one specific workload point.

### 1.5 blind

Definition: no prior context. Token count = 0. Consistent across all experiments.

### 1.6 turn / session (LoCoMo)

| term | in fidelity experiments | in cost profile |
|---|---|---|
| session | one `session_N` block (full conversation day, ~22 utterances) | n/a |
| turn | used loosely; effectively means session | individual speaker utterance (~26–49 tokens) |

The naming mismatch is the root cause of the win-10 definition conflict. `WINDOW_TURNS=10` in `cost_profile.py` picks 10 utterances; `max_sessions=10` in `frontier_locomo.py` picks 10 session blocks.

### 1.7 reachable

| definition | source | signal | status |
|---|---|---|---|
| State=D (app download active) | E31 (`e31_network.py`) | application-layer activity | INVALID proxy |
| cell_id != '-1' (has serving cell) | E31b (`e31b_network.py`) | radio-layer signal | VALID |

E31 Part C and E31b Part B/C each report predictability metrics; only E31b's are based on a valid signal. The State=D proxy collapses real radio gaps (cell_id=-1) with app-idle pauses and is not usable for mobility-aware prefetch decisions.

### 1.8 stale-by-N (E32)

Source: `experiments/fidelity/e32_staleness.py`.  
Definition: N missing individual turns (speaker utterances). N ∈ {0, 1, 5, 10, 20, 50, 100}.  
At N=100, delta_tokens = 2,993 (median across 10 conversations), equivalent to ~4.4 sessions (median 22 utterances/session). This means the staleness sweep spans intra-session staleness (N ≤ 20) to modest cross-session staleness (N = 50, 100 ≈ 2–5 sessions).

### 1.9 cold-prefill

Source: `results/cost/cost_matrix.csv`, `restore_ms` for `full` and `incr_cold` representations.  
Definition: TTFT from empty KV cache, fresh model load, no prefix-cache warm state.  
Measured at L ∈ {1k, 2k, 4k, 8k, 16k, 24k, 32k, 49k, 64k} on A6000 + qwen7b.  
Key values: L=8k → 1,369 ms (full); L=64k → 21,720 ms.  
Implied throughput at L=8k: 8,192 / 1.369 ≈ **5,984 tokens/s**.

### 1.10 warm-append

Two distinct definitions exist in the repo:

**cost_matrix.csv (`incr_warm`):** TTFT of appending L new tokens to a 0-length KV cache (effectively a fresh prefill with warm GPU/CUDA context). L=8k → 62.67 ms for 8,192 tokens.

**E32 (`warm_append` variant):** claimed to measure TTFT after extending a stale KV cache with N missing turns. **DISPUTED** — see Section 2 and Evidence Ledger. Per-measurement analysis shows flat ~82 ms across delta_tokens 20–2,993, which is inconsistent with true warm-append computation.

### 1.11 refresh / materialize

| term | definition | source |
|---|---|---|
| refresh (summaries) | time to regenerate a new summary from current full context (`update_ms`, corrected one-time cost) | cost_matrix.csv |
| materialize | re-prefill from text to produce KV cache (`restore_ms`) | cost_matrix.csv |

These are consistent across E21–E26 and E30. No conflicts.

---

## Part 2 — Evidence Ledger

Status codes: **VERIFIED** = traced to committed file, cross-checked, consistent. **SUPERSEDED** = value is replaced by a corrected calculation. **DISPUTED** = measurement cannot be trusted as stated; rerun required. **INVALID** = measurement procedure was incorrect; data not usable. **ESTIMATED** = computed by interpolation from committed values; not directly measured.

### Core cost measurements

| quantity | value | source | status | cross-check |
|---|---|---|---|---|
| KV bytes/token (qwen7b) | 57,344 B/tok | cost_matrix.csv (kv_bytes/L) | VERIFIED | consistent E21–E26 |
| A6000 usable VRAM for KV | 32.6 GB | cost_matrix.csv peak_mem_gb + spec | VERIFIED | 48 – 15.46 = 32.54 GB |
| sum-80 restore (A6000) | 28–31 ms (all L) | cost_matrix.csv restore_ms | VERIFIED | flat across L as expected |
| sum-200 restore (A6000) | 31–36 ms (all L) | cost_matrix.csv restore_ms | VERIFIED | slight growth with L |
| full restore (A6000, L=8k) | 1,369 ms | cost_matrix.csv restore_ms | VERIFIED | phase1 report consistent |
| full restore (A6000, L=64k) | 21,720 ms | cost_matrix.csv restore_ms | VERIFIED | phase1 report consistent |
| cold prefill throughput (A6000 L=8k) | ~5,984 tok/s | cost_matrix.csv full restore_ms | VERIFIED | 8192/1.369s |
| sum-80 update/refresh (A6000 L=8k) | 4,804 ms | cost_matrix.csv update_ms | VERIFIED | update_corrected=1 |
| sum-200 update/refresh (A6000 L=8k) | 9,565 ms | cost_matrix.csv update_ms | VERIFIED | update_corrected=1 |
| win-10 restore (10-turn window) | 62–98 ms (all L) | cost_matrix.csv window restore_ms | VERIFIED (wrong object) | valid for 10-turn window; wrong definition for paper |

### win-10 token count (critical)

| quantity | value | source | status |
|---|---|---|---|
| win-10 tokens (last 10 sessions, LoCoMo, n=10) | 7,275 median (5,597–8,548) | data/locomo/locomo10.json + this audit | VERIFIED |
| win-10 tokens (last 10 turns, cost profile, LoCoMo) | 261–488 | results/cost/profiles/a6000_qwen7b.json | VERIFIED |
| E30 WINDOW_TOKENS | 400 | experiments/cost/e30_capacity.py:75 | SUPERSEDED (wrong definition) |

### E30 derived quantities

| quantity | E30 value | corrected value | status |
|---|---|---|---|
| N_memory(win10, A6000) | 1,421 | 78 | SUPERSEDED |
| win-10 restore_ms used | ~65 ms (10-turn window) | ~1,292 ms (7,275 tok, interpolated) | SUPERSEDED / ESTIMATED |
| N_accel(win10, A6000, ri=60s) | 923 | ~46 | SUPERSEDED / ESTIMATED |
| win-10 binding crossover (A6000) | ~57 s (L=8k) | ~101 s | SUPERSEDED / ESTIMATED |
| N_memory(sum-80, A6000) | 7,106 (all L) | **unchanged** | VERIFIED |
| N_memory(sum-200, A6000) | 2,842 (all L) | **unchanged** | VERIFIED |
| N_memory(full, A6000, L=8k) | 69 | **unchanged** | VERIFIED |
| sum-80 always accelerator-bound | yes | **unchanged** | VERIFIED |
| qualitative ordering sum-80≫sum-200>win-10>full | correct | **survives in direction** | VERIFIED (direction) |

### E31 / E31b network

| quantity | value | source | status |
|---|---|---|---|
| E31 Part C reachability (State=D/I) | 0.829 connected | e31_network/ | INVALID (wrong proxy) |
| E31 Part D payloads | KV cache sizes | e31_network_characterization.md | INVALID (wrong payload type) |
| E31b reachability (cell_id!=-1) | 0.856 connected | e31b_network/e31b_summary.json | VERIFIED |
| E31b no-cell gap: p50=1s, p95=2s | — | e31b_network/e31b_summary.json | VERIFIED |
| E31b text transfer at p50 BW (9.6 Mbps) | 43–528× faster than cold prefill | e31b_network/e31b_summary.json | VERIFIED |
| Irish 5G BW p10/p50/p90 | 0.9/9.6/102.9 Mbps | e31_network/bandwidth_series.csv | VERIFIED |

### E32 latency — DISPUTED

| quantity | reported value | per-measurement distribution | implied throughput | status |
|---|---|---|---|---|
| full/warm_append (all N) | ~82 ms | min=61.5ms, max=91.5ms; FLAT across N=1 (delta=20tok) to N=100 (delta=2993tok) | 35,000 tok/s at N=100 (impossible vs 5,984 tok/s measured) | DISPUTED |
| sum200/full_regen (per conversation) | 6,771–9,242 ms | <0.5% intra-conversation variation despite delta varying 10–3,466 tokens across N | — | DISPUTED |

**Evidence for DISPUTED status:**  
For `full/warm_append`: the median latency is 81.6 ms at N=1 (mean delta=20 tokens) and 85.4 ms at N=100 (mean delta=2,993 tokens). If this were a true warm-append, latency should scale with delta_tokens; 2,993 tokens at 5,984 tok/s (committed cold prefill rate) would take ~500 ms, not 85 ms. The constant ~82 ms across all N is consistent with a prefix-cache hit serving the full context without recomputing the new delta.

For `sum200/full_regen`: conv-30 shows 6,772 ms at N=1 (delta=10 tokens) and 6,776 ms at N=100 (delta=2,753 tokens) — essentially identical despite 276× more tokens to incorporate. Conv-26 shows 7,509 ms at N=1 and 7,488 ms at N=100 despite delta growing from 32 to 3,466 tokens. The <0.5% intra-conversation variation proves the computation is not processing the delta tokens; a cached base-context prefill is being served.

**Implication:** E32 Part B latency measurements characterize cache-hit TTFT, not warm-append or full-regen catch-up costs. They cannot be used to assess the catch-up latency budget for a state refresh policy without reruns with caching disabled.

---

## Part 3 — What Verified Evidence Supports

### Claims that rest on VERIFIED evidence

1. **Regime taxonomy** (gist-compressible / structured-compressible / dense-incompressible):  
   Supported by E05, E06, E10–E11, E13, E15, E27, E29, E32 quality measurements (all VERIFIED).  
   E32 quality results (flat accuracy across N) are VERIFIED because they use HuggingFace inference, not vLLM with prefix caching — separate from the disputed latency measurements.

2. **KV footprint ordering** (sum-80 ≪ sum-200 ≪ win-10 ≪ full):  
   Supported by cost_matrix.csv KV bytes and the corrected token counts (VERIFIED). Direction survives; win-10 magnitude is corrected.

3. **Sum-80 and sum-200 always accelerator-bound** (N_accel ≪ N_mem):  
   E30 result for sum reps is VERIFIED — uses 80-token and 200-token budgets which are correct definitions. N_memory is large; N_accel is not the bottleneck at any ri.

4. **Network not the bottleneck; text transfer faster than cold prefill** (E31b):  
   Supported by Irish 5G BW measurements (VERIFIED) and cold-prefill latency from cost_matrix.csv (VERIFIED). Transfer 43–528× faster at p50 BW.

5. **Outdoor 5G has brief radio gaps** (14% no-cell time, gaps 1–3s):  
   Supported by E31b cell_id=-1 analysis (VERIFIED).

### Claims that rest on DISPUTED or SUPERSEDED evidence

6. **win-10 capacity and binding crossover** (E30):  
   SUPERSEDED. Corrected N_memory ≈ 78 (not 1,421); corrected crossover ~101s (not 57s). Qualitative ordering survives.

7. **win-10/full warm-append catch-up latency** (E32 Part B):  
   DISPUTED. Must rerun with prefix caching explicitly disabled.

8. **sum-200 full-regen catch-up latency** (E32 Part B):  
   DISPUTED. Must rerun with prefix caching explicitly disabled. Current measurements are constant per-conversation regardless of delta size.

9. **E31 Part C predictability metrics**:  
   INVALID (wrong proxy). Replaced by E31b Part B/C (VERIFIED).

### Priority rerun list

| priority | experiment | what to rerun | why |
|---|---|---|---|
| 1 (blocking) | E32b | Part B latency: full/warm_append and sum200/full_regen with vLLM prefix caching explicitly disabled; label warm and cold conditions | Current E32 Part B is cache-hit TTFT; policy routing and catch-up budget claims rest on this |
| 2 (blocking) | E30b | Capacity arithmetic for win-10 using WINDOW_TOKENS=7275 (or parameterized); recompute N_memory, N_accel, binding crossover for all tiers | Corrected estimates here use interpolated restore_ms; a direct measurement at 7,275 tokens would replace the interpolation |
| 3 (recommended) | — | Directly measure win-10 (10-session) restore latency on A6000 as a single cost_profile.py entry at L≈7275 | The corrected win-10 restore_ms (~1,292 ms) is interpolated, not measured |
| 4 (recommended) | — | Rerun E31b Part A with Lumos5G (pedestrian trace) once IEEE DataPort registration is obtained | Current E31b is driving-only; indoor/pedestrian premise check is still UNVERIFIED |

---

## Consistency check (self-audit of this report)

**Check 1 (cross-check):** All token counts and latency values traced to committed files. win-10 correction is 18× (well above 2× threshold); reasoning documented.

**Check 2 (physical plausibility):** E32 warm-append implied rate of 35,000 tok/s vs committed 5,984 tok/s cold prefill = 5.8× — above the 2× flag threshold. DISPUTED status applied.

**Check 3 (distribution sanity):** E32 sum200/full_regen shows <0.5% intra-conversation variance despite 276× increase in delta_tokens. Flagged as cache artifact.

**Check 4 (definition audit):** This is the definition audit. win-10 conflict documented; all terms enumerated.

**Check 5 (claim linkage):** All claims traced to specific experiment IDs and result files.

**Check 6 (proxy validity):** E31 State=D/I proxy documented as INVALID; E31b cell_id=-1 documented as VALID.
