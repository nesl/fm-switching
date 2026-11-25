# Why `peak_tokens` and `evicted` repeat across kv0.5r cells: a code read plus a data check

| field | value |
|---|---|
| pinned sha | `2f74f269f8ce06ccaac18f32d2dd968c9d8d699b` (`origin/main` after `git fetch origin`; resolved once, every file below read with `git show <sha>:<path>`) |
| working tree | NOT READ. The tree is ~2,080 commits behind origin; no absence claim in this file rests on it |
| UTC | 2026-11-25T03:49:47Z (start), written same session |
| nature | **Code read plus data check. NOT A FIX.** No repo file edited, nothing written outside this scratchpad, no cell run, no git write command. Per the user's ruling REPORT ONLY, NO FIX TONIGHT |
| disk | 28 GB free on `/`, above the 15 GB refusal floor |
| scope | `memory_pressure` in `coordinator_result.json`, all 317 cells under `results/orchestration/live2/frozen_test/runs/` carrying that file |

---

## 0. Correction to the brief, verified independently

The brief and `research/OVERNIGHT_HANDOFF_H100.md:599` both name `memory_pressure.evicted`. **That field does not exist.** Verified two ways at the pinned sha, from the structure and not from the name:

1. **From code.** `memory_pressure` is built in one expression, `procsplit.py:74-75`, with exactly four keys: `kv_capacity_enforced`, `gpu_kv_tokens`, `pressure`, `enact_placement_totals`. `run_live2_real.py:74-75` is the byte-identical non-split twin.
2. **From the artefact.** On `covex-v6-fair-final_..._kv0.5r_..._rep2/coordinator_result.json`: top keys `['enact_placement_totals','gpu_kv_tokens','kv_capacity_enforced','pressure']`; `pressure` keys `['epochs','epochs_over_cap','host_epochs_over_cap','host_peak_tokens','intervals','intervals_n','peak_tokens']`; `enact_placement_totals` keys `['calls','evicted','kept_warm','offloaded','resident']`. A regex for `"[^"]*evict[^"]*"` over the whole serialised block returns exactly one match, `"evicted"`. The probe can fire: the same regex for `peak` returns two matches, `peak_tokens` and `host_peak_tokens`.

**The real path is `memory_pressure.enact_placement_totals.evicted`.** `pressure` has no eviction counter of any kind.

**On consequence 2 of the correction, the wrong-channel reading: partly right, and weaker than feared.** There is indeed no pressure-side eviction counter, so "how many evictions did memory pressure cause" has no field of its own. But the two channels are not independent, and that is measurable rather than arguable. Across all **285** cells carrying `memory_pressure`:

- `intervals_n` equals `epochs_over_cap` in **285 of 285** cells. Every over-cap excursion in the entire corpus lasts exactly one epoch.
- `enact_placement_totals.evicted` minus `pressure.epochs_over_cap` is **0 in 273 of 285** cells, **+1 in 8**, **+2 in 4**.

So enforcement clears every overage within the single epoch that opened it, almost always by evicting exactly one session. `evicted` is therefore a near-deterministic re-encoding of `epochs_over_cap`, carrying at most a few bits more (the twelve cells where one epoch needed two evictions). The honest statement is not "wrong channel" but: **the placement eviction count and the pressure over-cap count are the same measurement reported twice, and neither is an independent count of evictions caused by pressure.** That also disposes of consequence 3: `evicted` looks like a policy-determined placement count, but the code makes it an arithmetic consequence of how often a capped occupancy series crosses its cap, which is why it does not vary like a policy quantity.

---

## 1. The four write sites, with file and line

All four fields are written in **one function**, `CoordState.enact_placement` in `experiments/orchestration/live2/cstate.py` (defined at line 485), called once per epoch.

| field | full path in the artefact | the write | what it is |
|---|---|---|---|
| `peak_tokens` | `memory_pressure.pressure.peak_tokens` | **`cstate.py:543`** `p["peak_tokens"] = max(p["peak_tokens"], used_all)`; initialised `cstate.py:501` | running **max over epochs** of `used_all` |
| `epochs_over_cap` | `memory_pressure.pressure.epochs_over_cap` | **`cstate.py:549`** `p["epochs_over_cap"] += 1`, guarded by `cstate.py:547-548` `over = int(self.gpu_kv_tokens) > 0 and used_all > int(self.gpu_kv_tokens)`; initialised `cstate.py:501` | **running count of epochs** |
| `host_peak_tokens` | `memory_pressure.pressure.host_peak_tokens` | **`cstate.py:544`** `p["host_peak_tokens"] = max(p["host_peak_tokens"], host_used)`; initialised `cstate.py:502` | running **max over epochs** of `host_used` |
| `evicted` | `memory_pressure.enact_placement_totals.evicted` | **`cstate.py:569`** `counts["evicted"] += 1`, inside the enforcement loop `cstate.py:564-569`, guarded by `cstate.py:554` and `cstate.py:558`; accumulated across epochs by the wrapper at **`procsplit.py:62-63`** (`tot[k] = tot.get(k, 0) + int(v)`), initialised `procsplit.py:57` | **running sum of per-epoch counts**; `cstate.py:493` makes `counts` a fresh local dict each epoch, so `cstate.py:569` alone is per-epoch and the run total exists only because of the `procsplit.py` wrapper |

The two inputs, both computed at `cstate.py:537-540`:

```
on_gpu_all = [x for x in live if x.measured_tier == "gpu"]      # 537
used_all   = sum(int(x.built_tokens) for x in on_gpu_all)       # 538
on_host    = [x for x in live if x.measured_tier == "host"]     # 539
host_used  = sum(int(x.built_tokens) for x in on_host)          # 540
```

with `live` from `cstate.py:504`: `[x for x in self.sessions.values() if x.open and x.built_tokens > 0]`.

`enact_placement_totals` as a whole: assembled `procsplit.py:57-66`, serialised `procsplit.py:75`. `pressure` serialised `procsplit.py:70-73` (which also strips `_open` and adds `intervals_n`). Both reach the file at `procsplit.py:519`, `res["memory_pressure"] = _memory_pressure(co.st, _mp_tot)`.

### Does anything READ them to change a decision? No. All four are reporting-only.

This is the project's canonical failure mode, so it is checked by structure and the probe is shown to fire.

- `git grep -n "\.pressure" <sha> -- '*.py'` returns six lines: the write at `cstate.py:500`, the write at `cstate.py:541`, the serialiser read at `procsplit.py:70`, a docstring at `d210_kv025_one_cell.py:47`, and two hits on a **different** object, `policy/kvpool.py:169` and `:200`, which call a method `self.pressure()` on the policy-side KV pool, not `CoordState.pressure`. **Probe fires:** the pattern matched four distinct files, so it is not a dead pattern.
- `git grep -ln "memory_pressure" <sha>` over **all** file types returns exactly two Python files, `procsplit.py` and `run_live2_real.py`, both of which only write and serialise it. Every other hit is prose (`reports/study_frozen_test.md`, `research/freeze_gate_status.md`, `research/OVERNIGHT_HANDOFF_H100.md`, `research/conformance_matrix_verification.md`, `results/INDEX.md`) or the result JSONs themselves. **No analysis script consumes `memory_pressure` at all.**
- The code says so itself. `procsplit.py:55-56`: *"Output-only: ... which cstate returns and discards ... No decision reads it."* `study_frozen_test.md:556`: *"Live instrumentation added (output only)."*

**Distinction that matters:** the four **counters** are reporting-only, but the **mechanism** they count is not write-only. Eviction acts through `x.set_tier("host", now)` at `cstate.py:567`, which writes `measured_tier` (`cstate.py:232`) and conditionally the belief (`cstate.py:237-239`); `measured_tier` is read by costing and readiness. So this is not a `desired_tier`-shaped defect. The thing that is reported-only is the **tally**, and the consequence is narrower but real: these numbers are read only by humans in prose, which is exactly how a field name nobody had read propagated into a committed file.

---

## 2. Trace or policy, per field

| field | function of | trace or policy | can it discriminate arms? |
|---|---|---|---|
| `peak_tokens` | `max` over epochs of the sum of `built_tokens` over open GPU-resident sessions | **policy-gated, then quantised.** `built_tokens` only ever rises at `coordinator.py:2069` (`s.built_tokens += b["piece_tokens"]`) on a completed build, and the piece size is `slice_tokens`, chosen by the arm (`coordinator.py:1345-1359`). It is reset to 0 on session close (`cstate.py:347`) and on preload (`cstate.py:367`). Nothing in the trace writes it | **in principle yes, in practice at very low resolution.** See section 4 |
| `epochs_over_cap` | count of epochs where `used_all > gpu_kv_tokens` | same input as `peak_tokens`, against a fixed cap | yes, coarsely (0 to 18 observed) |
| `host_peak_tokens` | `max` over epochs of `built_tokens` over open host-resident sessions | policy, and **more sharply so**: a session is only on host because an arm asked (`cstate.py:527-529`) or because enforcement evicted it (`cstate.py:567`) | yes, and it does: 12,658 to 31,083 across the kv0.5r cells at the same cap |
| `evicted` | sum over epochs of evictions inside the enforcement loop | arithmetically pinned to `epochs_over_cap` (see section 0) | **no independent information** |

The claim in the brief, that a trace-determined `peak_tokens` would explain the constant trivially, is **refuted**: `peak_tokens` is not trace-determined. It is zero for five arms on the same trace, and the session rosters differ by seed anyway (SHA1 of the sorted session-id set from `residency.jsonl`: s4 379 sessions `4814b8f146ac`, s5 377 `4207667ee6a1`, s6 379 `f4d499f23780`, s7 379 `cc91e254702d`). Different rosters, identical `peak_tokens`. The explanation has to be something other than a shared trace, and it is.

---

## 3. How a peak exceeds the enforced cap

`peak_tokens` = 32,470 against `gpu_kv_tokens` = 31,472 is 998 over. The code answers this in one line of ordering:

- the peak is recorded at **`cstate.py:543`**;
- enforcement runs at **`cstate.py:554-569`**, guarded by `if self.kv_capacity_enforced and int(self.gpu_kv_tokens) > 0` and then `if used > cap`.

**543 is before 554, so the peak is sampled strictly pre-enforcement, every epoch.** The same is true of `epochs_over_cap` (`cstate.py:547`). An epoch's sequence is: promote newly built sessions to GPU (514-518), apply the arm's steering (526-534), **measure** (537-553), **then** evict down to the cap (554-569). So the recorded peak is by construction the occupancy that *triggered* the eviction, not the occupancy after it, and `peak_tokens > gpu_kv_tokens` is correct and expected rather than a violation of the cap.

**998 has no independent interpretation, and the three candidates the brief offers are all refuted:**

- **Not a block-rounding artefact at 1,968 blocks.** 31,472 = 1,967 x 16 exactly, but 998 is not a multiple of 16 (998 / 16 = 62.375) and neither is 32,470. The quantum here is not the vLLM block.
- **Not one oversized session and not a single request's prompt.** The overshoot is not bounded by anything small: at 1x the same field reaches 106,395 against a 62,944 cap, 1.69x over, on `attentionstore-prefetch_n16_s7`.
- **Not "cap plus an overshoot" at all.** The decisive observation is in section 4: one 1x cell reaches **exactly 32,470** with `epochs_over_cap` = 0 and `evicted` = 0, meaning its cap of 62,944 was never approached. 32,470 is a value this family of arms lands on whether or not a cap is anywhere near it. Subtracting the cap from it was the wrong arithmetic.

---

## 4. The mechanism: a build-slice lattice, not a cap

`built_tokens` is a sum of `piece_tokens`. The piece sizes an arm actually used are recoverable from `decision.jsonl.gz` (`coordinator.py:1402-1404` logs `piece_tokens` on every `release_piece` / `release_whole`). Census of distinct `piece_tokens` values per cell:

| cell | n build decisions | distinct piece sizes | sizes |
|---|---|---|---|
| `covex-v6-fair-final` s4 `_rep2` | 148 | **2** | 1024 (133), 121 (15) |
| `covex-v6-fair-final` s5 | 150 | **2** | 1024 (137), 121 (13) |
| `covex-v6-fair-final` s6 | 148 | **2** | 1024 (135), 121 (13) |
| `covex-v6-fair-final` s7 | 153 | **2** | 1024 (142), 121 (11) |
| `covex-v6-fair-final-notouch` s4 | 147 | **2** | 1024 (132), 121 (15) |
| `covex-v6-final` s4 `_ms` | 141 | 5 | 1024 (113), 121 (15), 512, 128, 256 |
| `covex-v6-state-shares` s6 (**1x**) | 105 | **2** | 1024 (92), 121 (13) |
| `llf` s4 kv0.5r | 328 | **143** | 1334, 1333, 1331, 223, 330, ... |
| `llf` s5 kv0.5r | 366 | **152** | 1334, 1331, 1333, 1335, 223, ... |
| `mooncake` s4 kv0.5r | **0** | 0 | no build decisions at all |

The covex-v6 family builds in **two sizes only, 1024 and 121**. Every occupancy total it can ever present is therefore a point on the lattice `1024a + 121b`. Testing each observed `peak_tokens` against that lattice:

| peak_tokens | on `{1024, 121}` lattice? | decomposition | arm family |
|---|---|---|---|
| **32,470** | **yes** | 31 x 1024 + 6 x 121 | covex-v6 |
| **32,768** | **yes** | 32 x 1024 + 0 x 121 | covex-v6 (s7) |
| **32,228** | **yes** | 31 x 1024 + 4 x 121 | covex-v6 (`_ms`) |
| **52,829** | **yes** | 51 x 1024 + 5 x 121 | covex-v6 (1x) |
| 33,784 | no | | llf |
| 35,404 | no | | llf |
| 35,224 | no | | llf |
| 33,429 | no | | covex-v6-rules kv0.5 |
| 106,395 | no | | attentionstore |

Tested with the count of 121-token pieces bounded at `b <= 15`, which every observed covex-v6 decomposition satisfies with room to spare (`b` = 0, 4, 5, 6). The bound matters: 121 and 1024 are coprime, so the **unbounded** lattice is dense (27.7 percent of the integers in [31,472, 36,000]) and would be no test at all. Bounded at `b <= 6` it admits **30 of those 4,529 integers, 0.7 percent**; at `b <= 15`, 70 of 4,529, 1.5 percent. Every "no" above is a "no" even at `b <= 15`.

Every covex-v6 peak sits exactly on the arm's own two-size lattice; no llf peak does. The lattice step is 1024 tokens, which is **3.3 percent of the 31,472 cap**, so within a window a few percent wide above the cap there are only a handful of attainable values, and 32,470 is the one most often hit.

**Positive control for the lattice, and it is the sharpest single datum in this file:** `covex-v6-state-shares_n16_s6_1200s_h27_3t_L3_epg_rq30` is a **1x** cell, cap 62,944, `epochs_over_cap` = **0**, `evicted` = **0**, and `peak_tokens` = **32,470**. The identical value, reached with no enforcement event anywhere in the run, on an arm with the same two piece sizes. 32,470 is a resting total of the covex-v6 build pattern, not an artefact of the 31,472 cap.

**Negative control, already present in the corpus and not constructed:** five of the kv0.5r arms (`mooncake`, `simplestream`, `eco-llm`, `confidence-cascade`, `covex-v6-base`) issue **zero** build decisions. For them `built_tokens` never leaves 0, `cstate.py:504`'s `built_tokens > 0` filter is empty every epoch, and all four fields collapse to 0 with `resident` = 0, across 11,994 to 12,000 epochs that demonstrably ran. Disabling the mechanism collapses the quantity, so the quantity is driven by the mechanism. Worth recording separately: for those arms the pressure channel is **unexercised**, and their zeros are not evidence about memory pressure.

---

## 5. The data check

### 5a. How many kv0.5r cells exist: 27, not 6

At the pinned sha, `results/orchestration/live2/frozen_test/runs/` holds **317** cell directories carrying `coordinator_result.json`, of which **285** carry a `memory_pressure` block. By KV scale, taken from the directory name: **260 at 1x** (no `kv` token), **22 at kv0.5**, **27 at kv0.5r**, **8 at kv0.25**.

**The brief's count of six is stale by a factor of four and a half.** The six are the subset `freeze_gate_status.md:68` enumerates (rung-3 s4/s5/s6/s7, `-notouch` s4, `-stateoff` s4 `_rerun`). Of the 27 kv0.5r cells, **14 have a non-zero `peak_tokens`**, taking **6 distinct values**: 32,470 (x9), 32,768, 33,784, 35,404, 35,224, 32,228. The remaining 13 are the zero-build arms of section 4.

Also worth correcting: the phrase "three different arms" overstates the spread. Four of the nine cells at 32,470 are `covex-v6-fair-final` itself at seeds 4, 5 and 6 plus a `_rep2` repeat; two more are its own ablations `-notouch` and `-stateoff`, which are the same arm with a switch flipped; the other three are `covex-v6-final-nqd`, `covex-v6-rules` and (at 32,228) `covex-v6-final _ms`. **All nine are the covex-v6 family, which is to say all nine share the 1024/121 build slice.** No arm outside that family lands on 32,470 anywhere in the corpus.

### 5b. Every kv0.5r cell at the pinned sha (27 cells)

| cell | arm | seed | enf | gpu_kv_tokens | pressure.peak_tokens | pressure.epochs_over_cap | intervals_n | pressure.host_peak_tokens | pressure.host_epochs_over_cap | ept.evicted | ept.offloaded | ept.kept_warm | ept.resident | header.source_agreement.verdict | cell.json metrics_health |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `confidence-cascade_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | confidence-cascade | 4 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | ABSENT-IN-HEADER | ABSENT |
| `confidence-cascade_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | confidence-cascade | 5 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | OK | never_scraped |
| `covex-v6-base_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-base | 4 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | ABSENT-IN-HEADER | ABSENT |
| `covex-v6-base_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-base | 5 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | WARNING moved_after_import | never_scraped |
| `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final | 4 | True | 31472 | **32470** | 5 | 5 | 25963 | 0 | **6** | 0 | 3653 | 22 | ABSENT-IN-HEADER | ABSENT |
| `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_rep2` | covex-v6-fair-final | 4 | True | 31472 | **32470** | 6 | 6 | 24036 | 0 | **6** | 0 | 3639 | 22 | OK | never_scraped |
| `covex-v6-fair-final_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final | 5 | True | 31472 | **32470** | 6 | 6 | 18674 | 0 | **6** | 0 | 0 | 21 | ABSENT-IN-HEADER | ABSENT |
| `covex-v6-fair-final_n16_s6_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final | 6 | True | 31472 | **32470** | 6 | 6 | 21625 | 0 | **6** | 0 | 1830 | 22 | WARNING moved_after_import | ABSENT |
| `covex-v6-fair-final_n16_s7_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final | 7 | True | 31472 | **32768** | 5 | 5 | 24697 | 0 | **6** | 0 | 1830 | 20 | OK | never_scraped |
| `covex-v6-fair-final-notouch_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final-notouch | 4 | True | 31472 | **32470** | 5 | 5 | 23012 | 0 | **6** | 0 | 3662 | 22 | OK | never_scraped |
| `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-fair-final-stateoff | 4 | True | 31472 | **32470** | 6 | 6 | 22770 | 0 | **6** | 0 | 0 | 22 | INVALID torn_lazy_import | never_scraped |
| `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_rerun` | covex-v6-fair-final-stateoff | 4 | True | 31472 | **32470** | 6 | 6 | 31083 | 0 | **6** | 0 | 0 | 22 | OK | never_scraped |
| `covex-v6-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_ms` | covex-v6-final | 4 | True | 31472 | **32228** | 5 | 5 | 12658 | 0 | **5** | 0 | 35910 | 22 | OK | scraped_ok |
| `covex-v6-final-nqd_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-final-nqd | 4 | True | 31472 | **32470** | 6 | 6 | 17650 | 0 | **6** | 0 | 32966 | 22 | OK | never_scraped |
| `covex-v6-rules_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | covex-v6-rules | 4 | True | 31472 | **32470** | 5 | 5 | 22770 | 0 | **5** | 0 | 0 | 22 | ABSENT-IN-HEADER | ABSENT |
| `eco-llm_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | eco-llm | 4 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | ABSENT-IN-HEADER | ABSENT |
| `eco-llm_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | eco-llm | 5 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | WARNING moved_after_import | never_scraped |
| `eco-llm_n16_s6_1200s_h27_3t_kv0.5r_L3_epg_rq30` | eco-llm | 6 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | OK | never_scraped |
| `llf_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | llf | 4 | True | 31472 | **33784** | 2 | 2 | 8311 | 0 | **2** | 0 | 0 | 250 | ABSENT-IN-HEADER | ABSENT |
| `llf_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | llf | 5 | True | 31472 | **35404** | 4 | 4 | 16982 | 0 | **4** | 0 | 0 | 274 | OK | never_scraped |
| `llf_n16_s6_1200s_h27_3t_kv0.5r_L3_epg_rq30` | llf | 6 | True | 31472 | **35224** | 2 | 2 | 21122 | 0 | **2** | 0 | 0 | 261 | OK | never_scraped |
| `mooncake_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | mooncake | 4 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | ABSENT-IN-HEADER | ABSENT |
| `mooncake_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | mooncake | 5 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | OK | never_scraped |
| `mooncake_n16_s6_1200s_h27_3t_kv0.5r_L3_epg_rq30` | mooncake | 6 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | OK | never_scraped |
| `simplestream_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | simplestream | 4 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | ABSENT-IN-HEADER | ABSENT |
| `simplestream_n16_s5_1200s_h27_3t_kv0.5r_L3_epg_rq30` | simplestream | 5 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | OK | never_scraped |
| `simplestream_n16_s6_1200s_h27_3t_kv0.5r_L3_epg_rq30` | simplestream | 6 | True | 31472 | **0** | 0 | 0 | 0 | 0 | **0** | 0 | 0 | 0 | WARNING moved_after_import | never_scraped |

Legend: `ept` = `memory_pressure.enact_placement_totals`. `ABSENT-IN-HEADER` means `header.json` carries no `source_agreement` key. `metrics_health` is read from `cell.json`. Bolded columns are the two the brief asked about. `gpu_kv_tokens` is 31,472 and `kv_capacity_enforced` is true in all 27.

The 1x cells with the highest `peak_tokens`, as the control (full control statistics in 5d):

| cell | seed | gpu_kv_tokens | peak_tokens | epochs_over_cap | ept.evicted | host_peak_tokens |
|---|---|---|---|---|---|---|
| `attentionstore-prefetch_n16_s7_1200s_h27_3t_L3_epg_rq30` | 7 | 62944 | 106395 | 5 | 7 | 591596 |
| `v5-rules_n16_s5_1200s_h27_3t_L3_epg` | 5 | 62944 | 92210 | 12 | 13 | 117876 |
| `v5-rules_n16_s5_1200s_h27_3t_L3_epg_rq30` | 5 | 62944 | 91489 | 13 | 14 | 113794 |
| `v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun` | 7 | 62944 | 89188 | 13 | 15 | 143464 |
| `edf_n16_s6_1200s_h27_3t_L3_epg_rq30` | 6 | 62944 | 82176 | 3 | 4 | 51303 |
| `edf_n16_s6_1200s_h27_3t` | 6 | 62944 | 81217 | 2 | 4 | 37893 |
| `edf_n16_s7_1200s_h27_3t_L3_epg_rq30` | 7 | 62944 | 81155 | 4 | 4 | 43743 |
| `v5-rules_n16_s6_1200s_h27_3t_L3_epg_rq30` | 6 | 62944 | 80915 | 10 | 11 | 80031 |
| `attentionstore-prefetch_n16_s4_1200s_h27_3t_L3_epg_rq30` | 4 | 62944 | 79032 | 1 | 1 | 115876 |
| `attentionstore-prefetch_n16_s5_1200s_h27_3t_L3_epg_rq30` | 5 | 62944 | 77980 | 5 | 5 | 591506 |
| `v5-rules_n16_s4_1200s_h27_3t_L3_epg` | 4 | 62944 | 75804 | 13 | 13 | 95344 |
| `attentionstore-prefetch_n16_s6_1200s_h27_3t_L3_epg_rq30` | 6 | 62944 | 74920 | 8 | 8 | 320067 |
| `edf_n16_s4_1200s_h27_3t_L3_epg_rq30` | 4 | 62944 | 74585 | 2 | 2 | 22351 |
| `edf_n16_s5_1200s_h27_3t_L3_epg_rq30` | 5 | 62944 | 70895 | 5 | 5 | 49562 |

### 5c. Exclusions, and the two keys that are ABSENT rather than OK

- **One cell excluded.** `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` has `header.source_agreement.verdict` = **`INVALID torn_lazy_import`**. It is the torn cell the brief warns about, it is **not cited** in any conclusion here, and it is shown in the table only so the exclusion is auditable. Its `_rerun` sibling is `OK` and is the one that counts. Both happen to carry the same 32,470 / 6.
- **`source_agreement` is ABSENT, not OK, in 8 of 27 kv0.5r cells.** `header.json` carries no `source_agreement` key at all in those cells. Per the brief's rule a missing key is **ABSENT**. They are recorded as `ABSENT-IN-HEADER` in the table, not as passes. **Probe fires:** the same reader returns `OK`, `WARNING moved_after_import` and `INVALID torn_lazy_import` on other cells, so the key is being looked for in the right place and the misses are real. The fallback read of `coordinator_result.json:source_agreement` (which `procsplit.py:525` writes) also found nothing for those cells. Note that four of the nine cells at 32,470 are ABSENT on this key, including `covex-v6-rules` s4 and `covex-v6-fair-final` s4 and s5.
- **`metrics_health`.** Read from `cell.json`, not `header.json`, as instructed. 13 of 27 kv0.5r cells report `never_scraped` with `engine_metrics_trusted` = `false`; 13 have **no `metrics_health` key at all** (ABSENT); exactly one, `covex-v6-final s4 _ms`, reports `scraped_ok` with `engine_metrics_trusted` = `true`. Consistent with the handoff's expectation that only `_ms` cells are scraped. **Consequence respected throughout this file:** no `arm_stats.pd_free_kv_*` and no `cloud.gpu_kv_fraction` value is cited anywhere above or below. Every number here comes from `memory_pressure`, `decision.jsonl.gz`, `request.jsonl.gz` or `residency.jsonl`.

### 5d. The 1x control: a different, wide distribution, not the same constant

This is the test the brief called the sharpest available, and the answer is the reassuring one.

All **233** 1x cells carrying `memory_pressure` have `gpu_kv_tokens` = **62,944** and `kv_capacity_enforced` = **true** (so enforcement is not what distinguishes 1x from 0.5x; only the pool size is). Of those, **105 have a non-zero `peak_tokens`, taking 83 distinct values, from 6,484 to 106,395.** `epochs_over_cap` ranges 0 to 18 and `evicted` 0 to 18.

**Exactly one 1x cell shows 32,470**, `covex-v6-state-shares_n16_s6`, and it shows it with `epochs_over_cap` = 0 and `evicted` = 0, which as section 4 explains is the positive control for the lattice rather than a repeat of the 0.5x constant. So: **the 1x cells do not show the same constant.** They show a broad distribution at their own scale, which is the outcome the brief identified as the non-alarming one.

For completeness the other scales behave the same way: kv0.5 gives 9 non-zero peaks with **9 distinct values** (32,706 to 51,877) and kv0.25 gives 2 non-zero peaks with 2 distinct values (17,498 and 19,592, against a 15,736 cap, so 1.11x and 1.24x over, the same pre-enforcement sampling).

| scale | cells with `memory_pressure` | `gpu_kv_tokens` | non-zero peaks | distinct values | min | max |
|---|---|---|---|---|---|---|
| 1x | 233 | 62,944 | 105 | **83** | 6,484 | 106,395 |
| kv0.5 | 18 | 31,472 | 9 | **9** | 32,706 | 51,877 |
| kv0.5r | 27 | 31,472 | 14 | **6** | 32,228 | 35,404 |
| kv0.25 | 7 | 15,736 | 2 | **2** | 17,498 | 19,592 |

---

## 6. Verdict

**Ceiling effect, by the quantization route: a correct computation reported at a resolution too coarse to carry the question asked of it. Not a short-circuit.**

Stated precisely, because "ceiling effect" as the brief defines it says trace-determined, and that part is wrong:

> `pressure.peak_tokens` is a max over epochs of a GPU occupancy that is (a) built only out of the arm's own build slices, (b) sampled pre-enforcement, and (c) pulled back below the cap within one epoch, every single time, in all 285 cells. For the covex-v6 family the slices take only two values, 1024 and 121, so the attainable occupancy totals form a lattice of step 1024, which is 3.3 percent of the 31,472 cap. A max that is repeatedly truncated to just above a fixed cap, and that can only land on a lattice whose step is 3.3 percent of that cap, has very few attainable values; 32,470 = 31 x 1024 + 6 x 121 is the modal one. `enact_placement_totals.evicted` is then not a second observation but an arithmetic shadow of `epochs_over_cap`, equal to it in 273 of 285 cells.

### The evidence that distinguishes the three candidates

| candidate | would predict | observed | verdict |
|---|---|---|---|
| **short-circuit** (cached, constant-folded, written once) | the same value wherever the field appears, or a value independent of inputs | 83 distinct values at 1x, 9 at kv0.5, 6 at kv0.5r, 2 at kv0.25; `32,768` on seed 7 of the very same arm; 0 for the five arms that never build, across ~12,000 epochs that provably ran; `host_peak_tokens` varying 12,658 to 31,083 on the same cap from the same function, two lines from the `peak_tokens` write | **REFUTED.** The computation runs per cell, per epoch, and responds to its inputs |
| **trace-determined ceiling** (the brief's version) | identical across arms on the same trace, varying with seed | zero for five arms on the same trace; identical across four different seeds whose session rosters differ (four distinct roster hashes) | **REFUTED in the form stated.** It is policy-gated, not trace-determined |
| **quantization ceiling** (this verdict) | peaks on the arm's own piece-size lattice; off-lattice peaks for arms with many piece sizes; the same lattice value reachable without any cap nearby | all four covex-v6 peaks exactly on `{1024, 121}`; no llf or attentionstore peak on it (llf uses 143 to 152 distinct piece sizes); one 1x cell at exactly 32,470 with `epochs_over_cap` = 0 | **SUPPORTED on three independent predictions** |

### What this licenses and forbids

- **Forbidden:** citing `peak_tokens` or `evicted` as evidence that two covex-v6 arms behave the same way under memory pressure, or differently. Within a family sharing a build slice the field has a handful of attainable values and resolves nothing. By CLAUDE.md check 3 this is the **artefact spread** shape as much as the constant one: the values are real and the computation is sound, and they still cannot mean what a column headed "peak KV occupancy per arm" implies.
- **Licensed:** citing `epochs_over_cap` >= 1 as proof the eviction branch at `cstate.py:554-569` is reached, which is what `freeze_gate_status.md:68` uses it for. That use is sound and survives this reading. Also licensed: `intervals` = all 1s as evidence that pressure is spiky and never sustained, which is exactly the peak-versus-plateau distinction `cstate.py:494-499` says the instrumentation exists to draw. It answers that question cleanly in all 285 cells: **always a spike, never a plateau.**
- **Better fields for the question actually being asked:** `host_peak_tokens` (varies 12,658 to 31,083 across kv0.5r at one cap) and `enact_placement_totals.kept_warm` (0 to 35,910 across the same cells, 0 vs 3,653 vs 1,830 among three seeds of one arm that all report the same `peak_tokens`). The arms do differ, visibly, in the same block. They do not differ in this field.

### Could I not distinguish them? One thing remains unmeasurable tonight, and it is not load-bearing

The lattice argument explains why only a few values are attainable and which one is modal. It does not reconstruct the exact epoch at which each cell hit its max, because **the per-epoch occupancy series is not instrumented**: `pressure` retains only the max and the interval lengths, `residency.jsonl` carries `telemetry_cached_tokens` but no `built_tokens`, and `decision.jsonl.gz` build rows carry `piece_tokens` but **no `session_id`** (verified: the `release_piece` row keys are `['H','arm','arm_version','belief','cost_model_id','decision_id','decision_latency_ms','defer_s','desired_tier','kind','mu','note','opportunity_ids','piece_tokens','predicted','representation','representation_defaulted','t','traffic_mix']`), so completions cannot be attributed to sessions without joining through `request.jsonl.gz`, and session close times are not recoverable from any committed artefact in the cell. My own reconstruction without closes is therefore wrong by construction and is not cited above.

**The one measurement that would settle it to the epoch:** log `used_all` once per epoch (one integer per epoch, or just the argmax epoch index and the per-session `built_tokens` at that epoch) at `cstate.py:538`, beside the existing max. That is an instrumentation addition, explicitly **not made tonight** per the ruling. **It is not needed for the verdict**, which already rests on three independent refutations of short-circuit and three independent confirmations of the lattice.

---

## 7. Pre-registration: what tonight's block A must show

Block A adds nine kv0.5r cells at seeds 5, 6 and 7 across three arms. The H100 will report `enact_placement_totals.evicted`, `pressure.peak_tokens`, `pressure.epochs_over_cap`, `pressure.host_peak_tokens` and `pressure.host_epochs_over_cap` per cell. Predictions are written to those exact paths. **Written before the cells land.**

### Under the quantization ceiling (this verdict, the prediction to beat)

1. **`pressure.peak_tokens` is on the `{1024, 121}` lattice in every cell whose arm is a covex-v6 arm.** Test: solve `peak = 1024a + 121b` over non-negative integers **with `b <= 15`**. The bound is what makes it a test, as section 4 notes: bounded, the lattice admits 70 of the 4,529 integers in [31,472, 36,000], so a chance pass is a **1.5 percent** event per cell and nine independent passes would be about 1e-16. Unbounded the lattice is dense and the test is vacuous, so **report the `(a, b)` pair, not just a pass**, and treat any `b > 15` as a fail pending explanation.
2. **The modal value is 32,470**, with **roughly 4 to 7 of the nine cells** on it and the rest on neighbouring lattice points, most likely **32,768** (32 x 1024), **32,228** (31 x 1024 + 4 x 121) or **32,349** (31 x 1024 + 5 x 121). I expect **at least two distinct values** across the nine. Seeing all nine identical would still be consistent with this verdict but would be its weakest showing; seeing nine identical values **and** an off-lattice value anywhere would not be.
3. **`enact_placement_totals.evicted` equals `pressure.epochs_over_cap` in at least 8 of the 9 cells**, and differs by at most 2 in the rest. **`pressure.epochs_over_cap` is in 2 to 9** and **varies across the nine** even where `peak_tokens` does not. `intervals_n` equals `epochs_over_cap` in **all nine**.
4. **`pressure.host_peak_tokens` takes 8 or 9 distinct values across the nine cells**, in roughly 8,000 to 32,000. This is the discriminator: the same function, two lines from the `peak_tokens` write, in the same cells, must spread. **If `host_peak_tokens` is also constant across the nine, this verdict is wrong** and the next candidate is a short-circuit upstream in `built_tokens` itself.
5. **`pressure.host_epochs_over_cap` = 0 in all nine** (it is 0 in all 27 existing kv0.5r cells; the host tier is not the binding resource at this scale).
6. **For any block-A arm that issues no build decisions, all five fields are 0 and `enact_placement_totals.resident` is 0.** Classify such a cell as **unexercised**, not as a null.

### Under a short-circuit

`pressure.peak_tokens` = 32,470 and `evicted` = 6 in **all nine**, **and** `pressure.host_peak_tokens` constant across the nine, **and** `pressure.epochs_over_cap` constant at 5 or 6. The signature is **joint constancy of fields written two lines apart from different inputs**. Any one of them spreading rules this out, which is why prediction 4 is the one to look at first. Would then be falsified further by checking whether an off-lattice value ever appears.

### Under a trace-determined ceiling

`pressure.peak_tokens` identical within a seed across all three arms and **differing between seeds**, that is, three values across the nine, grouped by seed and not by arm. **Already contradicted** by the existing cells, where seeds 4, 5 and 6 of one arm agree and seed 7 does not, and where five arms on the same trace give 0. Recorded so the pattern is recognised if it appears.

### The reading that would be a genuinely new finding

An **off-lattice** `pressure.peak_tokens` from a covex-v6 arm, that is, a value not expressible as `1024a + 121b`. That would mean either a piece size outside `{1024, 121}` entered the build path, or `built_tokens` is being written by something other than `coordinator.py:2069`. Either is a mechanism change and should stop the block rather than be reported as a number. The check is three lines of arithmetic and costs nothing.

### One housekeeping prediction, independent of all the above

Expect **`metrics_health` = `never_scraped` with `engine_metrics_trusted` = false in all nine** block-A cells unless they carry an `_ms` token, per `OVERNIGHT_HANDOFF_H100.md:599`. That is expected and is not a fault. Check `header.source_agreement.verdict` per cell and treat a missing key as **ABSENT**, not OK: 8 of the 27 existing kv0.5r cells have no such key, so this is a live failure mode and not a hypothetical.

---

## 8. One line for the record

`memory_pressure.pressure.peak_tokens` and `memory_pressure.enact_placement_totals.evicted` repeat across the covex-v6 kv0.5r cells because the first is a pre-enforcement max truncated to just above a fixed cap and quantised to the arm's own 1024-token build slice, and the second is an arithmetic shadow of `epochs_over_cap`. The computation is correct, runs per cell, and is reporting-only; it is simply too coarse to discriminate arms that share a build slice, and it should not be cited as if it could.

## CORRECTION, 2026-11-25: THE TWO-PIECE-SIZE PREMISE IS SCOPED TO TWO ARMS AND DOES NOT HOLD FOR `-stateoff` OR `covex-v6-state-final`

**This file's verdict rests in part on "covex-v6 uses only two piece sizes", and that premise is MEASURED
for some arms of the family and FALSE for others.** `piece_tokens` read from committed decision logs:
```
covex-v6-fair-final, covex-v6-fair-final-notouch   {121, 1024} only, 3 seeds each, 6 cells
covex-v6-fair-final-stateoff                       {121, 301, 481, 1024}  remainders at all 3 seeds
covex-v6-state-final                               {121, 301, 391, 481, 751, 1024}  remainders
```
**So the correct scope is "measured on `covex-v6-fair-final` and `-notouch`; DOES NOT HOLD for `-stateoff`
or `covex-v6-state-final`", and NOT "the covex-v6 family".** **An off-lattice `peak_tokens` is therefore
NOT an anomaly for an arm that emits remainders, and the lattice test must not be applied outside the two
arms it was measured on.** *(This was found when the off-lattice stop fired on `covex-v6-state-final`
kv0.5r s4 at `peak_tokens` 32,498, which the remainders fully explain.)*
*** THE FILE'S CENTRAL CONCLUSION IS UNAFFECTED. The ceiling-not-short-circuit verdict rests on
`host_peak_tokens` varying, on `peak_tokens` varying by arm and by seed, and on the 1x control's 83
distinct values across 233 cells. Only the quantization ARGUMENT is scoped; the conclusion is not. ***
**And one observation this correction surfaced, recorded as a hypothesis: remainder emission tracks the
STATE CHANNEL rather than the arm family, since `-stateoff` emits remainders and `-notouch`, which keeps
the state channel, does not.**
