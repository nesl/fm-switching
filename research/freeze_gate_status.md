# FREEZE GATE STATUS: `research/conformance_matrix.md` section 10, re-checked against `covex-v6-fair-final`

## 0. PROVENANCE

| what | value |
|---|---|
| pinned sha, every file read with `git show <sha>:<path>` | **`16622e2f8cae28f110d3e23d8918d16cd864456d`** (`origin/main`, 2026-11-24 19:18:46 -0800, "D238: the overnight policy block, twenty eight cells, recorded before it is relayed") |
| how the sha was fixed | `git fetch origin` then `git rev-parse origin/main`, resolved ONCE and printed before any read |
| the shared working tree | **2,079 commits behind** this sha (`git rev-list --count HEAD..<sha>`). NOTHING below was read from it, and no absence below was established from it |
| the matrix | `research/conformance_matrix.md` at the pinned sha, 904 lines, 105,160 bytes. Added at **`4a73e125`** ("D225: conformance matrix and the adjacent-rung switch diff"), last touched at the pinned sha's own history for section 10.19 |
| matrix's own pin | section 0 pins the code read at `c5e7bb49` (switches resolved at `a4eaf9bc`). Both commits exist. Every code read BELOW is at the pinned sha, not at the matrix's pin, which is the point of this re-check |
| register of this document | **read-only verification by a session that did NOT write the matrix** and did not write the policy code. No cell was run, no tracked repo file was edited, nothing was committed or pushed |
| timestamp (UTC) | 2026-11-25T04:40:00Z |
| free disk at start | 32 GB available on the volume holding both the repo and the scratchpad, above the 15 GB refusal floor |
| "No space left on device" probe | 0 occurrences in every artefact relied on below (the four proof and verdict JSONs, and `cell.json` plus `.stdout` for all five rung-3 cells). Probe proved live by feeding it a synthetic `OSError: [Errno 28] No space left on device`, which it matched |
| INVALID probe | run STRUCTURALLY, on the E-id cell of each row (the `NOTICE` at `research/EXPERIMENTS.md:13-16` states flags live in the E-id cell), not on a bracket pattern. It returns **nine** flagged rows (E24, E24b, E24c, StudyD, StudyD2, StudyI2, StudyI3, StudyI3-reanalysis, StudyJ), all spelled `**[INVALID ... audit 2026-11-03]**` with an en/em dash inside the brackets. That is the positive control. **None of the four D233 to D235 rows cited below carries a flag.** |

## 1. ROW COUNT: CONFIRMED 16, AND THE COLUMN STRUCTURE

**16 is correct, confirmed by census and not accepted on report.** Section 10 of the matrix spans
lines 579 to 875 and declares "16 rows, in five groups". The census of row identifiers in that span
returns exactly sixteen: `10.1` to `10.16`. The group headers sum to the same number: Group A 7 rows
(10.1 to 10.7), Group B 4 rows (10.8 to 10.11), Group C 3 rows (10.12 to 10.14), Group D 1 row
(10.15), Group E 1 row (10.16). Three further `### 10.N` headers exist in the span (10.17, 10.18,
10.19) and are **not** gate rows: 10.17 records two checks on posted results, 10.18 certifies four
standing-note claims as closed, and 10.19 is the D232 (2) question-deferral removal. They were
excluded by reading each one, not by pattern.

**Exact row identifiers worked from:** 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10,
10.11, 10.12, 10.13, 10.14, 10.15, 10.16.

**Column structure.** Section 10 is **not a table and has no columns.** Each of the sixteen rows is a
prose block opened by a bold `**10.N <title>. <D-row citations>.**` line, carrying file:line
citations, OBSERVED counter values with the cell named, and, for most rows, an explicit
`**Closes when:**` clause. Group B rows additionally carry a CLAUDE.md Rule 2 class
(UNEXERCISED, ABSENT, UNEXPRESSIBLE). The tables elsewhere in the matrix (sections 4.1 to 4.5) use a
six-column form, `| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live
evidence (OBSERVED) | status |`, and section 1 defines the four registers CODE, OBSERVED, ABSENT and
ORDERED that every cell in those tables carries. The status table in section 3 below therefore
imposes four columns the matrix itself does not have.

## 2. THE RULING THAT RE-SCOPES EVERY ROW, VERIFIED IN THE LEDGER

`research/policy_design_log.md` at the pinned sha carries **D234 (4): "The FREEZE CANDIDATE is rung
3, `covex-v6-fair-final`, which contains the counterfactual state planner"** and **D234 (5): "Freeze
= rung 3 + network handling, then network cells and held-out seeds 1 to 3"**. D233 (2) as amended by
D234 (1) records the rung-4 rebuild `covex-v6-final-kr` as **NOT built, future work**.

Consequence for this check, and it cuts both ways:

- A row that is a rung-4-only defect no longer blocks the freeze, because the artefact it defects in
  is not the freeze candidate.
- A row the matrix classified as rung-4-only **must be re-read at rung 3 before it is called moot**,
  because rungs 2 and 3 run the same counterfactual state planner. One row fails that re-read: see
  10.2 below, and the carried gap under 10.16.

## 3. STATUS TABLE

| ROW | STATUS | CITATION OR WHAT IS MISSING | NOTES |
|---|---|---|---|
| **10.1** DEVICE_ANSWERS, rung 4's third request candidate (D218 (1), D221) | **closed** | Built at **`51cfb077`** ("D232 (2), D218, D166: covex-v6-final-nqd, rung 4 without the question-deferral leg"), which adds `experiments/orchestration/live2/arms_v6cf_device.py` (confirmed present at the pinned sha by `git ls-tree`). FIRED live: `arm_stats.device_answers_enabled` True and `pd_request_device_answers` = **55** in `covex-v6-final-nqd_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` and **2** in the 1x s4 cell (both cell dirs confirmed present) | Closed as built-and-live, and the arm it lives in is then ruled out ON EVIDENCE: D233 records `covex-v6-final-nqd` kv0.5r s4 as FAILED (robot cloud on-time 66 of 132 against rung 3's 121). Does not bear on the freeze candidate, which has the request-side legs off. **Single cell per condition, seed 4 only** |
| **10.2** D222 (1) item 1, hard-coded zero queued-ahead | **open** | **MISSING: the matrix's MOOT classification does not survive a re-read at rung 3.** 10.19 marks this moot because its only read was `arms_v6cfr3.py:198-199`, the removed leg. But the identical defect sits in the FREEZE CANDIDATE's state planner: `arms_v6state.py:273` `CC.predict(cf.model, int(est_tokens), int(built_tokens), 0, 0)`, `:274` the cold twin, and `:312` `CC.predict(cf.model, tok, 0, 0, 0)`. `cf_cost.predict`'s signature is `(model, tokens, cached_tokens=0, overlap_ft=0, overlap_decode=0, ...)` (`v5/cf_cost.py:182-184`), so those trailing zeros ARE `overlap_ft` and `overlap_decode`, the queue term. What is missing is either real queued-ahead work at those three sites, or a D-row recording that rung 3's state planner prices without a queue term | The one row of the sixteen whose status I would change from the matrix's own. The quantity is READ at each of those three sites and changes a WARM-against-cold probability, so this is not a write-only field. `state_decisions` = 65,044 with 2,386 deviations in the rung-3 1x s4 cell, so the priced path is heavily exercised |
| **10.3** D222 (1) item 2, debit one decision period from the deferral | **closed** | Closed by REMOVAL, not by building. **D232** is in the ledger (`research/policy_design_log.md`, row present, probe proved live by finding D230, D231, D232, D233, D234, D236 at one row each). D232 (2) removes question deferral from rung 4; `covex-v6-final-nqd` (`51cfb077`) is the arm without it. Nothing in rung 3 defers a request, so there is no deferral left to debit | Genuinely moot, unlike 10.2: the missing debit has no reader anywhere outside the removed leg. Remains a real defect if the leg is ever re-admitted |
| **10.4** D222 (1) item 5, the committed `rd_decisions` log | **closed** | The matrix reported `find -name '*rd_decision*'` returning 0 over 334 cell dirs. At the pinned sha it returns **2**, and they are exactly the two cells the D232 (2) removal rests on: `covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun/rd_decisions.jsonl.gz` and `covex-v6-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_ms/rd_decisions.jsonl.gz`. Both confirmed by `git ls-tree -r`. Probe proved live by the same listing returning 317 `coordinator_result.json` | 10.19 asked for exactly this and deliberately left the row open: "the log is the audit trail for the two cells this removal rests on". Both now have one. No future rung-4 cell will emit one and none needs to |
| **10.5** D223 (2), read max-model-len instead of the hard-coded 32,768 | **closed** | Built at **`a43ad7f7`** ("D223 (2): the context limit is the server's configured max-model-len, read once at run start") and re-proved at **`2e4c5961`**. `experiments/orchestration/live2/context_limit.py` exists at the pinned sha; all three sites the matrix named now read through it (`hybrid/hybrid_arm.py`, `arms_v6cf.py`, `arms_v6fair.py`), and `run_live2_real.py` sets it at run start. `grep` for the literal `32768` on the live path now hits only `context_limit.MODEL_ARCH_MAX_TOKENS`, documented in its own module as not a fallback for a server run, with `parse_max_model_len` raising instead | The last-occurrence argv parse is explicit and matters: at 0.5x the pinned flag list carries `32768` at index 7 and `31472` at index 39, and a first-occurrence parse would have read 32,768 and left the defect in silence. This row was the stated prerequisite for 10.8, and it is now discharged |
| **10.6** D220 (1), harm weighted by the accuracy gain | **closed** | Closed by RULING, which is what the row asked for ("Closes when: the user rules, and the code matches"). **D228 (2)** in the ledger: "D220 (1)'s GAIN WEIGHTING IS WITHDRAWN (planner error): harm sums losses across query types, and weighting by each type's cloud-minus-device accuracy gap is the cross-type exchange rate D149 (1) and D177 forbid (no per-type gain table exists either). Harm stays in D177 units ... MARGIN_CF 0.6582 unchanged". Code is unchanged and is now conformant: `v5/cf_objective.py` still computes `w_o * (p_before - p_after)` and its docstring at `:724` states exactly that | The matrix flagged this as "a tension for the user, not a bug", and the user resolved it against D220 (1). The row closes with NO code change, which is why a code-only re-check would have reported it still open |
| **10.7** D178 (3) per-type guard thresholds, and D166 (3) guard exit hysteresis | **waiting on a named overnight cell: `covex-v6-fair-final-ptg` at 1x `L3_epg_rq30` s4**, the `ptg` cell D238 inserts DIRECTLY AFTER BLOCK A | BUILT at **`42aa4fbe`** ("D230 (2), D178 (3), D166: covex-v6-fair-final-ptg, the per-type saturation guard"), from the implementation held at `f097f5d3`. `arms_v5rules2.py` now carries `GUARD_PER_TYPE_SWITCH`, `GUARD_LAG_S_BY_CLASS_D178`, and the D166 (3) exit hysteresis as `GUARD_EXIT_FACTOR_D166 = 0.5` with `GUARD_EXIT_HOLD_S_D166 = 2.0`, read at `:321` (per-type entry) and `:346-368` (exit latch). DEFAULT OFF (`arms_v5rules2.py:107`), ON only in `covex-v6-fair-final-ptg`. **It is proof-ready**, so D238's condition is met: `results/orchestration/live2/d231_ptg_guard/d231_ptg_guard_proofs.json` has `ALL_PASS` true, with a Step 2b diff ("DIFFERING DECISIONS: the switch reaches a decision") and two negative controls (thresholds disabled collapses EXACTLY to `covex-v6-fair-final`; hysteresis disabled moves 6,145 positions). MISSING: the cell itself. No `covex-v6-fair-final-ptg*` directory exists under `frozen_test/runs/` at the pinned sha | **A second thing is missing that no cell can supply: a ruling on whether the frozen arm is `-ptg` or plain.** The freeze candidate named by D234 (4) is `covex-v6-fair-final`, in which `guard_per_type` is OFF, so even a passing ptg cell leaves D178 (3)'s per-type thresholds outside the artefact being frozen. Bar 1 is the amended three-valued one (`AMENDMENT_4_bar1_tolerance.md`) against max observed 0.027752, and bars 2 and 3 do not inherit that floor |
| **10.8** Per-type host retention and offload, rung 2's headline mechanism | **open** | Two of the matrix's three claims are now REFUTED and the third stands. REFUTED: "no reduced-memory cell exists for rungs 2, 3 or 4 anywhere in the tree" (rung 3 now has kv0.5r at s4, s5, s6 and s7, and rung 4 has one), and "`over_cap` = 0" (`memory_pressure.pressure.epochs_over_cap` is 5 or 6 in every rung-3 kv0.5r cell, peak 32,470 to 32,768 against a 31,472 cap, and `evicted` = 6, so the EVICTION branch is reached). STANDS: `enact_placement_totals.offloaded` = **0** in all six 0.5x cells checked (rung-3 s4/s5/s6/s7, `-notouch` kv0.5r s4, `-stateoff` kv0.5r s4 `_rerun`) and in the rung-4 `_ms` cell. MISSING: a condition in which `offloaded` is non-zero for rungs 2 to 4, or a D-row recording the offload leg as unexercised at the reported memory levels | **BLOCK C** (`covex-v6-state-final` s4 to s7 at 0.5x) supplies the only thing still structurally absent, a reduced-memory cell for RUNG 2, whose headline mechanism this is. It cannot close the offload leg, which is already zero at 0.5x on four rung-3 seeds. **Distribution-sanity flag, CLAUDE.md check 3:** `evicted` = 6 and `peak_tokens` = 32,470 in five of the six 0.5x cells, across three different arms and four different seeds. A constant where a distribution is expected. Not diagnosed here; flagged |
| **10.9** Engine-metric KV bound (D216 (2), D209 (2) hit 6) | **open** | The ABSENT-LINK half is CLOSED and proved: `results/orchestration/live2/d227_e1_metrics/d227_e1_metrics_proofs.json` passes five parts, `asyncbackend.py:295` `metrics()` now carries the comment "THE READ THAT MAKES THE SCRAPE LIVE", `published_engine_metrics` gates the allow list, and part_d2 reports `engine_metric_binds_published` = **596** against `engine_metric_binds_forced_zero` = **0**. MISSING: the OBSERVED half. **No committed live policy cell shows a non-zero `pd_kv_bound_by_engine_metric`.** In the one committed policy cell with the scrape on, `covex-v6-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_ms` (`metrics_health.state` = `scraped_ok`, `engine_metrics_trusted` true, and `vllm:kv_cache_usage_perc` present in `metric_names_found`), `pd_kv_bound_by_engine_metric` is **ABSENT** while `pd_kv_bound_by_belief` = **342** = `pd_decisions`. Both rung-3 ablation cells read `state` = `never_scraped`, and **both comparator cells have no `metrics_health` key at all** | **Register, marked at the point of use:** the 596 is a DETERMINISTIC REPLAY of one recorded input tape, not a census of a live cell, and part_e's live smoke ran against the committed CPU stub `live/fake_server.py`, where `pd_kv_bound_by_engine_metric_on` = **0** with every `pd_*` counter ABSENT. **A driver dependency that decides whether the overnight blocks can close this:** the runner default is still OFF (`run_live2_real.py:160`, `--metrics-scrape ... default=False`). `study_frozen_grid_driver_v38.sh:97` passes `--metrics-scrape` on EVERY cell; `v37.sh:97` enables it only on a cell whose tag carries an `_ms` token, and **none of the D238 BLOCK A, B, C or D cell names carries one**. Also worth a look: `n_scrapes` = 2 in the `_ms` cell over 1,200 s at a stated ~10 s poll cadence |
| **10.10** Guard backlog leg (D178 (3)) | **open** | Still UNEXERCISED, now on four more cells than the matrix had. `arm_stats.guard_by_backlog` = **0** with `guard_by_lag` carrying 100 percent in every rung-3 cell checked: 1x s4 (0 against 71), kv0.5r s4 (0 against 451), kv0.5r s5/s6/s7, `-stateoff` kv0.5r (0 against 1,721), `-notouch` kv0.5r (0 against 282), and the rung-4 `_ms` cell (0 against 353). MISSING: a condition that reaches the backlog leg, or a D-row recording the leg as unexercised at this fleet size | The 0.5x cells the matrix hoped for now exist and the leg still did not fire, so adding seeds is unlikely to close it. The realistic closure is the D-row, not a cell. BLOCK A adds s5/s6/s7 at 0.5x and will say so on three more seeds |
| **10.11** Flexible split by `w_d` (D185 (3)(b), gap recorded by D224) | **open** | HALF FIXED, and the fixed half is the half the matrix called absent. `coordinator.py:1763-1765` now PASSES `weights_by_type=_wbt` into `SA.allowed`, with a comment at `:1751` naming this as the absent link ("`share_admission.py:162-168` has always READ `weights_by_type`, and this call site did not PASS it"). MISSING: the gate still short-circuits before it. `coordinator.py:1748` returns True when `not self._share_admission`, `_share_admission` comes from `SA.arm_enables(arm)` reading `live2_share_admission` from the INSTANCE only (`share_admission.py:264-278`), and no ladder arm sets it: the only non-proof setter in the tree is `arms_v6shares.py`. OBSERVED confirmation on the freeze candidate's 1x s4 cell: `share_events` = `[]`, `share_events_total` = 0, and NO `share_*` key in `counts` (ABSENT, not zero). So the weight is still computed and never consumed on this arm | Closure is a ruling, not a build: either switch it on in a labelled rung-3 variant with proofs, or set `_feed_split` False on these arms, or carry the Rule 2 class at its definition, which is what the matrix asked for. Until then the ON switch misleads a reader of the freeze candidate |
| **10.12** The lexicographic objective (D165 (A)) | **open** | Unchanged, and now pointed straight at the freeze candidate. `experiments/orchestration/live2/arm_names_v6.py:59` still carries `"missing": ["the D165 lexicographic objective is not built"]` on the **rung 3** entry of `V6_LADDER`, and `research/policy_spec_v6.md:276` still marks it **MISSING**, with line 24 still asserting the lexicographic structure. No later D-row removes it: D233, D234, D236 and D238 do not mention it. MISSING: built, or a D-row ruling it out | **The cleanest gate blocker in the matrix, and D234 (4) made it worse rather than better:** when the freeze candidate was undecided this was a defect in a rung; now it is a declared missing component of the arm being frozen, declared in the code's own registry, which raises on any arm whose `missing` list is non-empty unless the caller accepts it |
| **10.13** The two unbuilt compounds (D165 (D)) | **open** | HALF RULED OUT. KEEP-READY SET: ruled FUTURE WORK by **D234 (1)** in the ledger ("The `covex-v6-final-kr` build (keep-ready set, pre-warm, shadow-price harm; flash estimate 25 to 44 h, `reports/study_kr_estimate.md`) is NOT built now; recorded as future work"), with the assessment committed at `reports/study_kr_estimate.md` (10,278 bytes, present at the sha) and registered as `StudyD233-KR-ESTIMATE`. MISSING: **ADMIT WITH PROTECTED VICTIM** is named by no ruling. `policy_spec_v6.md:281` still marks both compounds MISSING, and `arms_v6cf.py:692` and `cf_protect_defer.py:881` still list "admit with protected victim" in their `not_built` arrays | The KR estimate itself carries a finding that bears on 10.13 and on 10.7's sibling: `plan_state` has NO candidate loop (one `device_id`, six scalar candidates, argmax, no pool term), and **there is no enact branch for `chosen == "WARM"`, so lifting the expressibility tie would make WARM a write-only choice.** The rung-3 1x s4 cell shows `state_chosen_WARM` = 4, which is that write-only choice being logged |
| **10.14** Reload from host as an explicit action, and counterfactual sync | **open** | Unchanged in code and now explicitly ORDERED BEFORE THE FREEZE, so the matrix's "closes when the user rules whether D226 (1) covers it" is answered: it does not. **D233 (3)**: "`plan_sync` is wired into the live path before the freeze, OFF by default, exercised only in post-freeze network cells (D226)". **D234 (5)**: "P1 is now the policy's network handling, required before the freeze ... and the counterfactual sync planner `plan_sync` on the live path. Freeze = rung 3 + network handling". MISSING: the wiring. At the pinned sha `plan_sync` still appears only in the v5 limb (`v5/cf_planner.py`, `v5/cf_proofs.py`, `v5/cf_objective.py`, `v5/cf_cost.py`), in proof scripts, and in the `not_built` arrays at `arms_v6cf.py:692` and `cf_protect_defer.py:881`. `policy_spec_v6.md:257` still marks the reload action **MISSING** | The row became a hard blocker between the matrix's writing and this sha, by ruling rather than by code change. The per-device link estimate and outage handling named in D234 (5) are in the same P1 and are not matrix rows at all |
| **10.15** C2 and C5 at rung 1 (D179 (5)) | **closed** | Closed EXACTLY as the row specified ("Closes when: someone reads the rung-1 counter-merge path and says which of the two it is. Cheap: it is one code read, not a cell"), and then confirmed against cells. The code read: `coordinator.py:167-197` `_arm_stats` walks `_rules` / `_base` / `_scorer` and merges every Counter, and its docstring names this very gap: "every committed `v5-rules-2` cell carries `warm_ahead_emitted` and `guard_active_epochs` and carries NO `c2_throttle_periods`, `c2_throttled_dash` or `c5_dash_held`, although the base counts all three on every period". **So it is the INSTRUMENTATION arm of the disjunction, not a non-firing mechanism.** OBSERVED confirmation: all **11** `covex-v6-rules` cells carry the keys, and the four older `v5-rules-2` cells carry none. Values in `covex-v6-rules_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30`: `c2_throttle_periods` 1,589, `c2_throttled_dash` 6,899, `c2_robots_at_risk_while_throttling` 109, `c5_dash_held` 64,777, `c5_decrease` 598, `c5_increase` 83, with `arm_version` `v5-rules-2.0` confirming it is the same arm | The matrix declined to assign a Rule 2 class here on purpose, because counter absence cannot distinguish "did not fire" from "not reported at this rung". The answer is the second, and it is now settled rather than deferred. **Defect found in the matrix while checking this:** its own section 4.1 table cross-references this row as "see 10.5", which is the context-limit row; the correct pointer is 10.15 |
| **10.16** The rung-4 service prediction priced from the failed-gate model (D151 (6), D162, D168, D222 (1) item 1) | **closed as scoped, with a gap carried forward** | Both rulings the row asked for are made and the first is built. **D228 (1)**: "ITEM 1 = reading (B): the deferral's latest-safe-start prediction moves from the model `cf.model` currently reads (its own `GATE_STATUS` says it FAILS spec v5 section 12) to the D162 model (the one that passed, D168), with uncached tokens queued ahead", which answers the row's (a) and its (b) in the same sentence. Built: `arms_v6cfr3.py` attaches `cf.model_d162 = CC.load_d162_model()` and raises `WeightWiringError` unless `per_queue_token` is present, "so the queued-ahead term would [not] be priced in the wrong units"; `v5/cf_cost.py:218-226` `predict_d162` carries its units in its argument names, and `:204` records that the key incompatibility is deliberate so the 247x error becomes a `KeyError` | **THE GAP THE ROW DOES NOT COVER AND NO OTHER ROW COVERS EITHER.** D228 (1) deliberately leaves `cf.model` as it was, because "`cf_planner`'s `plan_queue`/`plan_state`/`plan_sync` and `cf_protect_defer` price with it" (`arms_v6cfr3.py:450-453`). So the FREEZE CANDIDATE's state planner still prices every state decision from the failed-gate model: `v5/cf_planner.py:367` `self.model = CC.load_gate_model()`, and `v5/cf_cost.py:100` `GATE_STATUS = "FAILS (spec v5 section 12) ..."`. The accidental mercy survives in the same shape, since `arms_v6state.py` also passes `overlap_ft = overlap_decode = 0`, so the 247x is LATENT at rung 3 exactly as it was at rung 4. **This is 10.2 and 10.16 meeting one rung down, and neither row, as written, says so** |

## 4. WHICH ROWS BLOCK THE FREEZE, AND WHICH DO NOT

The gate is D225 (6): no freeze and no held-out seeds 1 to 3 until every row is built-and-live or
ruled out with evidence. The freeze is now D234 (5)'s "rung 3 + network handling".

**BLOCK THE FREEZE (7, counting the carried gap under 10.16):**

1. **10.12**, the lexicographic objective. Declared missing in the code's own ladder registry on the
   rung being frozen, and no D-row removes it. The hardest of the seven, because closing it is a
   build or a user ruling and nothing else.
2. **10.14**, `plan_sync` on the live path plus the explicit reload action. Ordered before the freeze
   by D233 (3) and again by D234 (5), and not wired at this sha.
3. **10.2 as re-scoped**, the hard-zero queue term at `arms_v6state.py:273`, `:274`, `:312`. The
   matrix marks it moot for rung 4; rung 3 is the freeze candidate and the defect is live there.
4. **The carried gap under 10.16**, the freeze candidate's state planner pricing from the model whose
   own `GATE_STATUS` says it fails. Same three call sites as item 3, different defect.
5. **10.7**, pending the `covex-v6-fair-final-ptg` 1x s4 cell AND a ruling on whether the frozen arm
   is `-ptg` or plain. The cell alone does not close it.
6. **10.13**, the ADMIT WITH PROTECTED VICTIM half, which no ruling names.
7. **10.11**, the ON switch on the freeze candidate that cannot reach a decision. Cheapest of the
   seven: it closes by a ruling or by setting a switch False.

**DO NOT BLOCK (6 closed):** 10.1, 10.3, 10.4, 10.5, 10.6, 10.15, plus 10.16 within its own stated
scope. Five of these closed since the matrix was written; **10.6 closed with NO code change at all**,
by D228 (2) withdrawing the decision, which is why a code-only re-check would have reported it open.

**BLOCK ONLY UNTIL A D-ROW RECORDS THEM (3): 10.8, 10.9, 10.10.** All three are reachability or
instrument gaps rather than conformance gaps in the frozen arm's decisions, and each of the three
matrix rows offers "or a D-row recording it unexercised" as its own alternative closure. Of the
D238 cells, **BLOCK C** bears on 10.8 (the only structurally missing thing, a rung-2 cell at 0.5x)
and **BLOCK A** bears on 10.9 and 10.10 only if the blocks run under driver v38.

## 5. THE THREE CAVEATS, VERIFIED HERE AND NOT TAKEN ON REPORT

**(a) Every ablation verdict on origin is SEED 4 ONLY, one cell per arm.** Confirmed in
`results/orchestration/live2/d233_stateoff/d233_ablation_attainment.json`, whose own
`CAVEATS_THAT_TRAVEL` ends "all figures are seed 4, one cell per arm". Every row above that cites an
ablation number (10.1's `-nqd` failure, 10.8's offload zeros at 0.5x, 10.9's `never_scraped`, 10.10's
backlog zeros) is single-cell evidence at seed 4 unless it names s5, s6 or s7 explicitly. The four
rung-3 kv0.5r comparator cells at s4 to s7 are the exception and are the only multi-seed 0.5x reading
in the set. D238 BLOCK A exists to turn the rest into per-seed distributions.

**(b) Both `covex-v6-fair-final` comparator cells have NO `source_agreement` key at all. VERIFIED
INDEPENDENTLY, and it is ABSENT, not OK.** Probed all four JSONs (`run_meta.json`, `cell.json`,
`header.json`, `coordinator_result.json`) of
`covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30` and
`covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30`: **zero occurrences in all eight files.**
The probe is proved live by the positive control: the same probe on
`covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_L3_epg_rq30` and
`covex-v6-fair-final-notouch_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` returns exactly one occurrence
each, in `cell.json`, `header.json` and `coordinator_result.json`, and the stateoff cell's
`header.source_agreement` reads `verdict: "OK"` with `torn_lazy_import: []` and
`tree_files_changed_during_cell_n: 0`. **So the bar every verdict above is measured against is
unaudited for source tearing.** This matters to the comparison and not only to the treatment: D238
rule 2 requires a `source_agreement` verdict on every cell precisely because `run_meta.run_valid` is
TRUE on torn cells, and the one cell struck as INVALID today was struck on that key alone, after
`run_valid` passed it.

**(c) The 0.5x ablation verdicts are thin.** From the same committed file:
`-stateoff` kv0.5r `_rerun` difference -0.032969, `ratio_to_stratumA_max_observed` **1.188**, with
verdict "clears the same-code floor THINLY; FAILS the in-condition stratum-B bound; the two strata
DISAGREE ... Real but weak, sign robust, NOT settled at one seed"; `-notouch` kv0.5r difference
+0.028312, ratio **1.0202**, "clears the same-code floor by 2.0 PERCENT ONLY; fails stratum B".
Only the 1x `-stateoff` reading is decisive: difference -0.170831, ratio **6.157**, "DECISIVE; clears
every stratum-A construction and also stratum B (1.99x)", 627 of 712 episodes moved. Three further
caveats travel with those numbers and are recorded in the file itself: stratum A is n=8 and cannot
support a p95, its max observed 0.027752 is set by one pair 3.8x the next largest; there is NO
same-code replicate in the `L3_epg_rq30` condition at all; and single-shot and dashcam on-time have
NO measured floor, so the +12 of 357 and +383 of 11,764 are unfloored and are not effects.

## 6. THE D-ROWS THAT ARE CITED AND ARE NOT IN THE LEDGER

Probed `research/policy_design_log.md` at the pinned sha for a row start `| D<n> |`. The probe is
proved live: it returns exactly one row each for D230, D231, D232, D233, D234 and D236.

| D-row | in the ledger? | where it is cited instead |
|---|---|---|
| D233, D234, D236 | **yes**, one row each | used above as rulings |
| D228, D232 | **yes**, one row each | 10.6 and 10.16 close on D228; 10.3 closes on D232 |
| **D235** | **NOT IN THE LEDGER** | cited inside the **D236** row itself ("after the per-question membership check of the robot tie and the guarded rung-3 comparator reruns (D235 (2))"), registered in `research/EXPERIMENTS.md` as `StudyD235-UPLINK-TIERS` (which cites "D234 (5)", not D235), and cited in the commit message of `77f33760` as "D235 (6)" |
| **D237** | **NOT IN THE LEDGER**, and not cited anywhere I read | zero occurrences in the design log; not in the H100 handoff |
| **D238** | **NOT IN THE LEDGER** | `research/OVERNIGHT_HANDOFF_H100.md:3`, as the only D238 occurrence in that file, headed "USER RULING 2026-11-24, PROVISIONAL, revisit later (recorded first, before relaying): THE OVERNIGHT POLICY BLOCK, 28 CELLS", and in the pinned sha's own commit subject |

These are reported as NOT IN THE LEDGER, which is a statement about the ledger, not about the
rulings: D238's content is committed and its cell list is verifiable, and D235 (2) is load-bearing
inside a row that IS in the ledger. The standing rule those files repeat is "every ruling into this
file first", and for D235, D237 and D238 the design log is not that file.

Block counts in the handoff agree with the relayed list: BLOCK A 9 cells, BLOCK B 8, BLOCK C 7,
BLOCK D 4 at s4 to s7, totalling the 28 the header declares.

## 7. WHAT THIS CHECK CANNOT ESTABLISH

1. **It cannot establish that any row is closed in the sense that matters, namely that the frozen
   policy's decisions are what the decisions say.** Every "closed" above is closed against the
   matrix's own stated closing condition. Four closed on a ruling (10.3, 10.6, 10.13's KR half,
   10.16) and a ruling is not a measurement.
2. **It cannot audit the comparator.** Caveat (b) is the whole of it: the two `covex-v6-fair-final`
   cells that every verdict is measured against carry no `source_agreement` key, so for those two
   cells the question "did the tree move under this run" has no answer in the repo. A broken control
   passes every check applied to the treatment.
3. **It cannot turn a single cell into a distribution.** Caveat (a). Nothing above about `-stateoff`,
   `-notouch` or `-nqd` is more than one cell per arm at seed 4, and the two 0.5x ablation readings
   are at 1.19x and 1.02x of a floor built from n=8 pairs on seeds 0 and 6, in a different condition,
   under a different robot deadline.
4. **It cannot distinguish "did not fire" from "not instrumented at this rung" for any counter it
   read as absent**, except where a positive control was run. `arm_stats` is SPARSE: a counter that
   never increments is absent from the JSON. I ran that control for 10.15 (the older `v5-rules-2`
   cells against the newer `covex-v6-rules` cells) and for `source_agreement`, and did NOT run it for
   `offloaded`, `over_cap` or `pd_kv_bound_by_engine_metric`, where I instead read the sibling key in
   the same block (`evicted`, `epochs_over_cap`, `pd_kv_bound_by_belief`) to show the block is live.
5. **It cannot tell whether the engine-metric bound works in a real cell.** 10.9's proof is a replay
   of a recorded tape plus a CPU-stub smoke test in which the counter it exists to move reads 0. No
   engine-backed policy cell at this sha binds on the engine metric.
6. **It cannot confirm that the D238 blocks will scrape.** That depends on which driver version runs
   them, and the planned cell names carry no `_ms` token. v37 would leave the scrape off; v38 turns
   it on for every cell. Which one the H100 is running is not readable from this sha.
7. **It cannot see any mechanism absent from both the code and the matrix.** The matrix's own section
   11 scopes out the baselines, `v5/cf_objective.py` and `v5/cf_planner.py` internal constants (17
   and 20 of them), `engine_actions.py`'s other 11 module constants, and C5's AIMD internals. The
   carried gap under 10.16 is an instance of exactly that: a defect in the freeze candidate that no
   row of the matrix names, found only because D234 (4) moved the candidate.
8. **It cannot verify the matrix's own numbers at the matrix's own sha.** Everything here was read at
   `16622e2f`. Where a matrix figure disagrees with what I read, I report the pinned-sha value and
   say the matrix's claim is refuted at this sha; I do not claim the matrix was wrong when written.
   One such case is section 11's "zero decision logs for `covex-v6-state-final`,
   `covex-v6-fair-final` or `covex-v6-final`": both comparator cells carry `decision.jsonl.gz` at
   this sha, and whether that is new or a `.gz` spelling the matrix's census missed is not
   established here.
9. **It cannot replace the user's ruling on any of the seven blockers.** Four of them (10.7's arm
   choice, 10.11, 10.12, 10.13's protected victim) close by a decision, not by work.
