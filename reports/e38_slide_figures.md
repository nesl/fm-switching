# E38 — Slide Figures

**Status:** canonical.  
**Purpose:** Three advisor-presentation figures from committed data. Plotting only; no new measurements, no simulation.  
Script: `experiments/figures/e38_slide_figures.py`  
Output: `figures/slides/e38_fig{1,2,3}_*.{pdf,png}`

---

## Figures produced

| figure | file | content |
|---|---|---|
| Fig 1 | `e38_fig1_maintenance_cost.{pdf,png}` | Maintenance cost by state form (horizontal bar, log x) |
| Fig 2 | `e38_fig2_inversion.{pdf,png}` | Inversion: KV footprint vs maintenance cost (two-panel) |
| Fig 3 | `e38_fig3_effective_capacity.{pdf,png}` | Effective capacity = min(N_mem, N_accel) vs turn interval at kv=9 GiB |

---

## Provenance table

Every plotted value is listed here with its source file and, where available, the source line.

### Figure 1 — Maintenance cost by state form

| bar label | value | source | notes |
|---|---|---|---|
| full warm-append | **66 ms** | `reports/e34b_corrected_catchup.md` §Part 1 Table (N=1 row); confirmed by `reports/phase1_cost_profiling.md` Table "Update / Incremental Latency" L=1,024 incr_warm=66 ms | E26 also reports 66 ms at L=1k; median over multiple sessions |
| win10 growth | **36 ms** | `reports/e34b_corrected_catchup.md` §Part 1 (win10 intra-session, voice-rate regime, N=1→10) | Committed constant MAINT_WIN10_GROWTH_MS=36.0 in E36d/e/f/g/h |
| win10 amortized | **653 ms** | `reports/e34_maintenance_semantics.md` §Part C summary: "win10 amortized maintenance = 652 ms" (rounded to 653 ms); derived as SLIDE_FRAC × SLIDE_MS + (1−SLIDE_FRAC) × GROW_MS = 0.657 × 975 + 0.343 × 36 = 652.9 ms | **Discrepancy flag:** E35 (`reports/e34b_corrected_catchup.md`) measures win10 inter-session slide as 1,031 ms (MAINT_WIN10_SLIDE_MS=1031), giving amortized = 0.657×1031+0.343×36 = 689.7 ms. This alternative is used in all E36e–E36h simulations. Both are committed. Fig 1 uses the E34 report's stated value of 653 ms. Fig 3 uses 690 ms to match the analytic N_eff table in E36e Part A. |
| sum200 recursive | **5,822 ms** | `reports/e34b_corrected_catchup.md` §Part 2 (sum200 recursive median 5,784–6,210 ms; midpoint rounds to 5,997 ms; committed constant is 5,822 ms from E35 analysis JSON). Committed constant MAINT_SUM200_MS=5822 in all E36e–E36h scripts. | |
| vLLM caption | 1.10–1.17× faster cold prefill; 1.59–2.55× faster warm-append vs HF | `reports/phase1_cost_profiling.md` §"Runtime Calibration (vLLM)" summary table (E26) | Annotated as italic footer on Fig 1; not plotted |

### Figure 2 — The inversion

**KV footprints** (computed as tokens × KV_BYTES_PER_TOK = 57,344 B/tok from E23):

| representation | tokens | KV bytes | KV MB | source |
|---|---|---|---|---|
| sum200 | 160 | 9,175,040 B | **9.18 MB** | E29 (tokens_sum200=160 KV-equivalent); E23 (57,344 B/tok) |
| win10 | 7,275 | 417,177,600 B | **417 MB** | E33a Definition A (last-10-sessions, 7,275 tok median); E23 (57,344 B/tok) |
| full | 20,092 | 1,152,123,648 B | **1,152 MB = 1.152 GB** | E33a (L_locomo_median=20,092 tok); E23 (57,344 B/tok) |

**Discrepancy flags:**
- **sum200 KV:** Task spec stated 11.5 MB (= 200 tok × 57,344 B). The committed token count is 160 (KV-equivalent, not the text-token count of 200). E29 and all E36e–E36h scripts use 160. Fig 2 plots 9.18 MB from the committed value. If 200 tokens were intended, the value would be 11.47 MB; the ordering (sum200 ≪ win10 ≪ full) is unaffected.
- **win10 KV:** Task spec stated 409 MB. The arithmetic "7,275 tokens at 57,344 B/token" gives 417 MB. The committed token count (E33a Definition A) is 7,275. Fig 2 plots 417 MB.

**Maintenance costs** (same as Fig 1): sum200=5,822 ms, win10=653 ms, full=66 ms.

### Figure 3 — Effective capacity

**Fixed parameters:** kv_cap=9 GiB = 9,663,676,416 bytes; source: E36e sweep axis.

**N_mem** (floor(kv_cap / kv_per_session)):

| representation | kv_per_session | N_mem | E36e Part A check |
|---|---|---|---|
| full | 20,092 × 57,344 = 1,152,123,648 B | **8** | E36e table: "full: 8M" ✓ |
| win10 | 7,275 × 57,344 = 417,177,600 B | **23** | E36e table: "win10: 23M" ✓ |
| sum200 | 160 × 57,344 = 9,175,040 B | **1,053** | E36e table not shown (too large); analytic |

**N_accel** (floor(ti_ms / (maint_ms + serve_ms))):

*Note: Fig 3 uses win10_amz=690 ms to match E36e's analytic table (MAINT_WIN10_AMZ_SIM_MS=689.7 ≈ 690 ms). Fig 1 uses 653 ms (E34). See discrepancy note above.*

| representation | maint+serve | ti=5s | ti=15s | ti=30s | ti=60s | source |
|---|---|---|---|---|---|---|
| full | 66+59=125 ms | 40 | 120 | 240 | 480 | E36e Check 2; E35/B1 |
| win10 | 690+59=749 ms | 6 | 20 | 40 | 80 | E36e Part A table ✓ |
| sum200 | 5822+32=5854 ms | 0 | 2 | 5 | 10 | E36e Part A table ✓ |

**N_eff = min(N_mem, N_accel)**:

| representation | ti=5s | ti=15s | ti=30s | ti=60s | E36e source |
|---|---|---|---|---|---|
| full | **8** (M) | **8** (M) | **8** (M) | **8** (M) | "full: 8M at all ti" ✓ |
| win10 | **6** (A) | **20** (A) | **23** (M) | **23** (M) | "win10: 6A / 20A / 23M / 23M" ✓ |
| sum200 | **0** (A) | **2** (A) | **5** (A) | **10** (A) | "sum200: 0A / 2A / 5A / 10A" ✓ |

Crossover marked at **ti=17.2s**: E36e Part A2 P2 Table "win10 (amortized) crossover ti = 17.2s" — the turn interval at which win10's binding resource switches from accelerator to memory (N_accel(win10) = N_mem(win10) = 23). At this point win10 achieves its ceiling N_eff=23, firmly above full's N_eff=8.

---

## Results cross-check (6-check protocol)

**Check 1 — Cross-check against committed.**

| quantity | this figure | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| MAINT_FULL_MS | 66 ms | 66 ms | E35/E26 | 1.00 | ✓ |
| MAINT_WIN10_GROW_MS | 36 ms | 36 ms | E35 | 1.00 | ✓ |
| MAINT_WIN10_SLIDE_MS (Fig 1) | 975 ms | 975 ms | E34 Part A | 1.00 | ✓ |
| MAINT_WIN10_AMZ (Fig 1) | 653 ms | 652 ms (E34 report) | E34 §Part C | 1.00 | ✓ (rounding) |
| MAINT_WIN10_AMZ_SIM (Fig 3) | 690 ms | 689.7 ms | E36e/E36h constant | 1.00 | ✓ |
| MAINT_SUM200_MS | 5,822 ms | 5,822 ms | E35 | 1.00 | ✓ |
| KV_BYTES_PER_TOK | 57,344 B | 57,344 B | E23 | 1.00 | ✓ |
| TOKENS_FULL | 20,092 | 20,092 | E33a | 1.00 | ✓ |
| TOKENS_WIN10 | 7,275 | 7,275 | E33a | 1.00 | ✓ |
| TOKENS_SUM200 | 160 | 160 | E29/E36e | 1.00 | ✓ |
| N_MEM_FULL at kv=9GiB | 8 | 8 | E36e Part A | 1.00 | ✓ |
| N_MEM_WIN10 at kv=9GiB | 23 | 23 | E36e Part A | 1.00 | ✓ |
| N_eff(win10,ti=5s) | 6 | 6 | E36e Part A | 1.00 | ✓ |
| N_eff(win10,ti=15s) | 20 | 20 | E36e Part A | 1.00 | ✓ |
| N_eff(sum200,ti=15s) | 2 | 2 | E36e Part A | 1.00 | ✓ |
| crossover ti (win10) | 17.2s | 17.2s | E36e Part A2 P2 | 1.00 | ✓ |
| win10 amortized (E34 vs E35) | 653 ms vs 689.7 ms | both committed | E34/E35 | 1.06 | FLAG (2 committed values) |
| sum200 KV tokens | 160 | 200 (text tokens) | E29 KV vs text def | 0.80 | FLAG (KV ≠ text token count) |

Two flagged discrepancies documented in provenance above. Both within 1.25× and do not change direction of any claim.

**Check 2 — Physical plausibility.** All N_accel values consistent with committed maint+serve ms. No rate exceeds committed cost curves.

**Check 3 — Distribution sanity.** All values are analytic (single committed constants); no distribution. N/A.

**Check 4 — Definition audit.**

| name | definition in this run | consistent with prior? |
|---|---|---|
| win10 | last 10 sessions = 7,275 tok (E33a Definition A) | ✓ NOT the 400-tok or 261–488-tok Definition B (E30/cost_profile.py) |
| sum200 | 160 KV-equivalent tokens (E29), text representation ≈684 B | ✓ (E29, E36e) |
| full | full session history; L=20,092 tok median (E33a) | ✓ |
| N_eff | min(N_mem, N_accel) per E36e Part A formula | ✓ |
| N_mem | floor(kv_cap / kv_per_session) | ✓ (E36e) |
| N_accel | floor(ti_ms / (maint_ms + serve_ms)) | ✓ (E36e) |

**Note on win10 definition:** All KV footprint and N_eff computations in this document use 7,275 tokens (E33a Definition A). Earlier experiments (E30, cost_profile.py) used 400 tokens — a 18× error corrected by E33a. Figures use the correct 7,275-token value.

**Check 5 — Claim linkage.** Fig 2 (inversion) supports FORMULATION.md §capacity: footprint and maintenance orderings are reversed, so minimizing KV footprint maximizes maintenance cost. Fig 3 supports §refresh: binding resource (KV vs accelerator) depends on turn interval; win10 is N_eff-maximizing for ti>17s. Fig 1 supports §refresh maintenance cost ordering (full=66ms < win10_amz=653ms < sum200_recursive=5,822ms). No quantity measured here is scoped out by FORMULATION.md.

**Check 6 — Proxy validity.** All values are direct measurements or analytic derivations from committed constants. No proxy relationships.

All six checks pass (two flag items documented; neither changes direction of claims).

---

## After-any-task

- [x] Mechanism verification: N/A (plotting only; no causal claim tested in this experiment)
- [x] Consistency check: PERFORMED above
- [x] EXPERIMENTS.md row: E38 row appended (canonical)
- [x] INDEX.md: entry to be appended
- [x] STATUS.md: to be updated
- [x] Stop and ask user to commit
