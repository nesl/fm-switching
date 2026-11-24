# Study RUNG4-S5-FAILURE -- why `covex-v6-final` fails check 2 at seed 5

User-commissioned investigation, 2026-11-23. Read-only: **committed cells only, no dry replay, no code change, no new cell.**
Study row: `StudyLADDER-FINAL` in `research/EXPERIMENTS.md` (E-id PROPOSED, NOT YET CONFIRMED). Nothing cited here is marked INVALID.

## REGISTERS, DECLARED ONCE AND MARKED AGAIN AT EVERY POINT OF USE

| register | definition | where it is used here |
|---|---|---|
| **GOVERNING** | delivery at **COMPLETION** (prefill + decode), D146, default since 2026-11-20. `t_delivered = request.t_done + (outcomes.t_delivered - outcomes.t_cloud_done)`, on-time iff `t_delivered - t_opportunity <= L_rob`, `L_rob = 3.0 s` | every headline count, every pass/fail statement |
| **first token** | the coordinator's own `cloud_payload.on_time` / committed `outcomes.t_delivered` | reported beside the governing number, never substituted for it |
| OBSERVED count | a census over the committed logs | the cause counts, the gate counts, the reconciliation |
| CONSTRUCTED | arithmetic on committed values, not a run | the "would the grid delay alone explain it" column, the costing in the conclusion |

**No replay was needed or run.** Every item of the spec except 6 (iv) was answerable from the committed cell files. A peer 52-cell byte-identity sweep was running on flash and the H100 was running the ladder; the ALONE rule (D216 (1)) was never engaged because no cell was launched.

## Scorer reproduction and the positive control (spec prerequisite)

The scorer's governing register was re-implemented from `experiments/orchestration/live2/scorer/score.py` (`load` D146 rewrite at `:566`, `refused_request_ids` at `:484`, `_within` at `:687`, `attainment` at `:722`) and run against the committed `cell.json -> score.score.sweep[0]`.

| cell | committed `robot_pool_on_time` | reproduced | per-device table exact |
|---|---|---|---|
| `covex-v6-final` s5 | 107 / 127 | 107 | yes, all 7 devices |
| `covex-v6-fair-final` s5 (**the control**) | 121 / 127 | 121 | yes, all 7 devices |
| `covex-v6-state-final` s5 | 112 / 127 | 112 | yes |
| `hybrid-F-lhreq-noc3` s5 (base) | 27 / 127 | 27 | yes |
| `covex-v6-final` s4 | 121 / 132 | 121 | yes |
| `covex-v6-fair-final` s4 (**the control**) | 126 / 132 | 126 | yes |

Positive control PASSES on six of six committed arms, including both control arms. The check is not broken and neither control arm is.

**First use of `L_rob`: the sweep value is 3, not 5.** `cell.json -> score.score.sweep[0].L_rob = 3` and `target_defaults.L_rob = 3` ("D71 as amended by D82"), while `header.json -> targets.robot.L_s = 5.0` and the scorer module constant `ROB_L_S = DS.ROBOT_DEADLINE_S  # 5.0` both say 5. At `L_rob = 5` the arm scores 115 and the control 123 and there is no failure at all. Every number in this report is at `L_rob = 3`, the value the committed score block used. The stale 5.0 in `header.json -> targets` is flagged in the definition audit below.

---

# MECHANISM VERIFICATION (CLAUDE.md), recorded before any count was written up

**Step 0 -- what would make this uninterpretable.** (a) Using the wrong on-time register: checked, both registers computed and labelled, and the governing one reproduces the committed score exactly. (b) Using the wrong `L_rob`: checked, found a two-valued name in one cell, resolved to the sweep's 3. (c) Reading `desired_tier` as a live mechanism: checked, it is `null` on every row of both cells and is a known write-only field; not used. (d) Comparing arms whose base differed: checked, both cells carry `arm_version "covex-v6-fair-feed-1.0"` and `digests_equal true`; they ran on **different coordinator commits** (`f99f69e8` for rung 4, `bf1ae16d` for rung 3), which is recorded as a limitation. (e) Assuming an absence from the stale working tree: all source was read with `git show <origin sha>:<path>`.

**Step 1 -- the causal chain.** If the question-deferral leg's latest safe start (`cf_request_defer.decide`, `cf_cost.latest_safe_start`) is computed from a service prediction that is systematically optimistic, then a question deferred to that start is re-offered with less slack than its service actually needs; the base arm's own feasibility ladder (`arms_builder.BuilderArm._recall`, `est <= slack` / `est <= slack + defer_s` / else reject) then either admits it too late to complete inside `L_rob`, or re-defers it by its fixed 0.5 s quantum past the deadline, or rejects it; and a question never sent is also a prefix never touched, so the session is less resident when its next question arrives. Each link is grounded in committed code, cited at file and line below.

**Step 2 -- each link instantiated, with the READ that consumes it.**

| causal link | implementing quantity | value / range in this run (s5, rung 4) | varies as expected | evidence: the READ |
|---|---|---|---|---|
| the leg fires at all | `rd_question_defers` | **37** (rung 3: 0) | yes, 0 vs 37 across arms | `arms_v6cfr3.py:297-298` writes `ra.decision="DEFER"`, `ra.defer_s`; **read** at `coordinator.py:858` `o.defer_until = t + max(float(ra.defer_s),0)` |
| the safe start | `cf_cost.latest_safe_start(...).deferral_s` | 0.582 to 2.575 s over the 37 | yes | `cf_request_defer.py:258` `defer_s = float(lss["deferral_s"])`, returned as `deferral_s` and read by `arms_v6cfr3.py:298` |
| the safety factor | `cf_request_defer.SAFETY_FACTOR` | **1.8721**, constant | constant **by design** (committed, not swept) | `cf_request_defer.py:249` `CC.latest_safe_start(now, deadline, pred, SAFETY_FACTOR)` |
| the service prediction | `CC.predict(model, u_request, 0, 0, 0).total_s` | implied 0.177 to 0.583 s on the 12 deferred-and-lost | yes | `arms_v6cfr3.py:197`; consumed at `cf_cost.py:270` `need = safety * pred.total_s` |
| **the queued-ahead term** | `overlap_ft`, `overlap_decode` arguments | **0 on every deferral decision** | **CONSTANT AT ZERO** | `arms_v6cfr3.py:197` passes literal `0, 0`; `cf_cost.py:153-157` multiplies `per_overlap * 0` |
| the deficit weight | `w_decider` on the bar and on `own_loss` | > 1.0 on **87 of 152** decisions | yes | `cf_request_defer.py:329` `w_r = float(w_of(decider_device_id))`, `:336` `PD.bar(w_of, decider_device_id, ...)`; `cf_protect_defer.py:254,259` `bar = w * MARGIN_CF_ON_TIME` |
| the bar | `MARGIN_CF_ON_TIME` | 0.65824 on-time answers (from `cf_margin.MARGIN_CF` 0.16456) | constant by design | `cf_protect_defer.py:259` |
| the base re-check | `BuilderArm.defer_s` | **0.5 s, 8 firings** (rung 3: 0; base arm `hybrid-F-lhreq-noc3` s5: 12, all exactly 0.5) | yes | `arms_builder.py:258-259` `elif est <= slack + self.defer_s: RecallAction(..., "DEFER", defer_s=self.defer_s)`; read at `coordinator.py:858` |
| the sweep of a question past its deadline | `coordinator.py:2102` | 12 unsent in rung 4 vs 4 in rung 3 | yes | `coordinator.py:894-895` requires `defer_until <= t` **and** `deadline_abs() >= t` to re-offer; `:2102` sweeps the rest |
| the lost prefix touch | `request.cached_tokens` for a later question on the same session | `opp0008287`: 19,392 (rung 3) vs **11,536** (rung 4) on an identical 23,535-token prompt | yes | engine telemetry in `request.jsonl.gz`, consumed by the next request's prefill |

Two entries are marked and they are findings, not failures:

* **`overlap_ft` / `overlap_decode` are CONSTANT AT ZERO.** They are not absent from the simulation (`cf_cost.predict` reads them, `cf_cost.py:153-157`), they are written as the literal `0` by the only caller on this path. The deferral therefore plans its restart as if the engine were empty, on a decision the gate only reaches when the harm population is non-empty. This is the central defect this report identifies.
* **`desired_tier` is NULL on all 11,641 rung-4 decision rows and all 11,823 rung-3 rows.** It is the known write-only field. Not used.
* **The protect-and-defer leg is UNEXERCISED.** `pd_decisions = 299`, gates `no_active_alert_episode` 39 + `rebuild_fits_without_evicting` 260 = 299, so **zero** decisions reached the harm computation and zero `PROTECT_AND_DEFER` actions were taken. Spec cause (c), "a protect-and-defer of ANOTHER session displaced it", is therefore **ruled out by census for all 14 losses**, and this matches `arms_v6cfr3.py`'s own pre-registered statement that the leg is unexercised at 1x.

**Step 2b -- the switch reaches a decision.** It does, and the diff is the committed pair: the two cells' decision logs differ in 45 `defer` rows (37 question-deferrals plus 8 downstream base-rule defers), 5 vs 3 `decline` rows, 472 vs 480 `release_recall`, and 1,907 vs 2,046 `release_infeasible`. The first differing decision is rung 4's `d1037`, `kind=defer`, `t = 114.04`, `defer_s = 2.254699`, `opportunity_ids=["opp0001024"]`, with no counterpart in rung 3. This is not an ABSENT LINK.

**Step 3 -- one unit traced end to end.** `opp0001513`, `robo006`, session `...340298_start_0.0_end_402.612`, rung 4:

```
t_opportunity          160.812962      deadline (t_opp + L_rob 3.0)   163.812962
t = 160.84  kind=defer  decision_id=d1493  defer_s=2.157984
            implied planned service = (163.813 - 160.84 - 2.157984) / 1.8721 = 0.435 s
            planned latest safe start = 160.84 + 2.157984 = 162.998
            belief at this instant: believed_tier "gpu", telemetry_cached_tokens 7,744 (residency.jsonl t=155.85)
t = 163.04  kind=release_recall  decision_id=d1514  representation "D2" (representation_defaulted TRUE)
            epoch-grid delay past the planned start: 163.040 - 162.998 = 0.042 s
request     t_submit 163.051  prompt_tokens 10,324  cached_tokens 8,736  cache_path WARM  http_status 200
            uncached u = 1,588;  requests in flight at submit = 4, carrying 3,113 uncached tokens
            D162 as the arm evaluated it (queued_ahead = 0): 0.0678 + 0.000182*1588          = 0.357 s
            D162 with the queue actually present:            + 0.000154*3113                 = 0.836 s
            observed first token 163.869 - 163.051                                           = 0.818 s
            observed / predicted(queue=0) = 2.29;  observed / predicted(queue observed) = 0.98
            t_first_token 163.869   t_done 163.952
outcome     first-token register   163.891 - 160.813 = 3.078 s   -> LATE
            GOVERNING completion   163.974 - 160.813 = 3.161 s   -> LATE, overrun +0.161 s
            budget bound: neither KV nor accelerator; the binding constraint is the DEADLINE,
            via a service prediction short by the whole queue term.
            rung 3, same opportunity, no deferral: released t=160.92, completion latency 1.481 s, ON TIME.
```

**Step 4 -- negative control, on committed cells and therefore free.** Disabling the mechanism under test is exactly the comparator: `covex-v6-fair-final` is rung 4 minus the two counterfactual legs, and it emits **zero** `defer` rows. The result changes: 121 of 127 against 107 of 127 in the governing register at s5, and 126 of 132 against 121 of 132 at s4. The control changes the result, so the mechanism is driving the difference. Cell: s5, 16 devices, 1,200 s, `h27_3t_L3_epg_rq30`, 1x memory (`gpu_kv_tokens` 62,944, `memory_setting` "tight"), identical on both arms.

**Step 5 -- the alternative explanation, and what distinguishes it.** The 14-question gap could be produced by (a) the deferral's mispredicted safe start, the claimed mechanism, or (b) ordinary run-to-run engine variance between two separately executed live cells, which would scatter losses across questions the counterfactual never touched. **The data distinguishes them: 12 of the 14 lost questions carry a `defer` row in rung 4 and no `defer` row exists anywhere in rung 3**, and the two that carry none are on sessions whose earlier questions rung 4 dropped. A third candidate, (c) a residency-belief error that admitted a question it should have refused, is **refuted by census**: across 115 rung-4 robot recall requests with a prior residency row, the belief was PESSIMISTIC (understating the resident prefix, which makes `u` larger and the safe start EARLIER) on 111, optimistic on 4, and in **zero** cases did a believed-warm session come back `cache_path COLD`.

---

# RESULTS CONSISTENCY CHECK (CLAUDE.md), run before any conclusion

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| s5 robot pool n, all arms | 127 | 127 | `cell.json` all four arms; `robot_pool_n_equal_across_arms` | 1.000 | agree |
| s5 rung 4 on-time, GOVERNING | 107 | 107 | `covex-v6-final` s5 `cell.json` | 1.000 | agree |
| s5 rung 3 on-time, GOVERNING | 121 | 121 | `covex-v6-fair-final` s5 `cell.json` | 1.000 | agree |
| s5 base on-time, GOVERNING | 27 | 27 | `hybrid-F-lhreq-noc3` s5 `cell.json` | 1.000 | agree |
| s5 retained | 0.851064 = (107-27)/(121-27) | 0.851064 | user brief / scorer check 2 | 1.000 | agree |
| s4 rung 4 / rung 3 on-time | 121 / 126 | 121 / 126 | `EXPERIMENTS.md` StudyLADDER-FINAL ("121 on time against 126") | 1.000 | agree |
| s4 retention | 0.945055 = (121-35)/(126-35) | 0.9451 | `EXPERIMENTS.md` StudyLADDER-FINAL | 1.000 | agree |
| `MARGIN_CF` on-time units | 0.65824 | 0.6582 | user brief; `cf_protect_defer.py:26` | 1.000 | agree |
| deferral safety factor | **1.8721** | **1.863** (as quoted in the brief) | `cf_request_defer.py:126,137` -> `d190_measured_safety.SAFETY_FACTOR` | 1.005 | **disagree, explained**: the committed value is 1.8721, the nearest-rank q90 (which at n=5 is the maximum) of `observed_over_predicted` in `results/orchestration/live2/frozen_test/d190_recall_lag_diagnosis.json`. 1.863 is not in the tree. Under 2x, resolved in favour of the committed value |
| `cf_protect_defer.KAPPA` | 1.5775406165458339 | same | `cf_protect_defer.py:71` | 1.000 | agree, and **this is not the factor the question-deferral uses** |
| D162 first-token model | `0.0678 + 0.000182*unc + 0.000154*queued_ahead` | same | user brief; `d190_measured_safety.py:21` | 1.000 | agree |

**2. Physical plausibility.** Implied prefill rate = uncached tokens / (t_first_token - t_submit), over every request with an opportunity id:

| cell | n | min tok/s | p50 tok/s | max tok/s |
|---|---|---|---|---|
| `covex-v6-final` s5 | 9,186 | 68 | 1,217 | **4,761** |
| `covex-v6-fair-final` s5 | 9,274 | 68 | 1,211 | **4,986** |
| `covex-v6-final` s4 | 9,346 | 4 | 1,188 | 4,954 |
| `covex-v6-fair-final` s4 | 9,369 | 4 | 1,181 | 5,205 |
| `covex-v6-state-final` s5 | 9,560 | 69 | 841 | 4,579 |
| `hybrid-F-lhreq-noc3` s5 | 10,209 | 62 | 932 | 4,458 |

The maximum anywhere is 5,205 tok/s against the committed A6000 cold prefill of about 7,100 tok/s (`reports/phase1_cost_profiling.md`). **Nothing in this analysis implies a rate faster than the committed curve, let alone 2x faster.** No caching artefact.

**Caching, stated as the methodological parameter it is.** These are vLLM runs with prefix caching ON. `cache_path` is WARM on every request discussed here and `cached_tokens` is the engine's own report of the prefix it reused. Every latency quoted is therefore a **warm append**, never a cold prefill, and is not comparable with the committed cold-prefill curves except as the one-sided bound used in check 2 above. The two arms warm differently and that difference is part of the finding (see `opp0008287`).

**3. Distribution sanity.** No median is reported without its spread. The two constants in the data were chased to their sources rather than trusted:

* `defer_s = 0.5` exactly, 8 times out of 45 rung-4 `defer` rows. **Explained, not breakage:** it is `arms_builder.BuilderArm.__init__(defer_s=0.5)` (`arms_builder.py:75,258-259`), the base feasibility ladder's fixed quantum, cross-confirmed by the base arm `hybrid-F-lhreq-noc3` s5 emitting 12 `defer` rows all of which are exactly 0.5. The remaining 37 are the counterfactual's and are all distinct (0.582 to 2.575).
* `representation = "D2"` with `representation_defaulted = TRUE` on **472 of 472** rung-4 `release_recall` rows and **480 of 480** rung-3 rows. The representation lever is **CONSTANT across this comparison**. This pair of cells tests the TIMING lever alone; it is not evidence about representation x timing. Marked at the point of use in the claim linkage below.
* `belief` (`cold_tokens_by_session` / `gpu_tokens_by_session` / `host_tokens_by_session`), `mu`, `H`, `cost_model_id`, `predicted.ttft_s`, `predicted.completion_s` and `predicted.imposed_delay_s_by_request` are **empty or null on every row of both decision logs**. The residency belief had to be read from `residency.jsonl` instead and the predictions reconstructed from the committed D162 formula. This is an instrumentation gap, recorded under "not determined".
* Observed/predicted first-token ratio over the 28 counterfactually-deferred questions that were sent at s5: min 1.266, p50 1.787, p90 2.293, max 2.923. Over all 115 robot recall requests in that cell: min 1.266, p50 2.080, p90 3.822, max 6.706. A real distribution, not a constant.
* **The effect is concentrated and the stratum is reported beside the mean.** 20 of 127 questions miss in rung 4, 7.1 percent of the pool is deferred by the counterfactual, and the losses sit entirely inside that stratum plus two knock-ons. A pool-level mean would read as a 11-point drop with no mechanism attached; the stratum is where the mechanism is.

**4. Definition audit.**

| object | definition used here | matches prior committed use |
|---|---|---|
| on-time (robot) | GOVERNING: completion delivery, D146, `L_rob = 3.0 s` | yes, reproduces the committed score block exactly on 6 of 6 arms |
| `L_rob` | **3** (`cell.json -> sweep[0].L_rob`, `target_defaults.L_rob`) | **NAME USED WITH TWO VALUES IN ONE CELL**: `header.json -> targets.robot.L_s = 5.0` and the scorer module default `ROB_L_S = 5.0` both say 5, and the sweep and `header.json -> robot_deadline_s = 3.0` both say 3. The committed score used 3. Reported, not reconciled here: it is another session's field |
| a "deferral" | one `decision.jsonl` row with `kind == "defer"`, split by `defer_s == 0.5` (base ladder) against everything else (counterfactual), with the split verified against `arm_stats.rd_question_defers = 37` and `counts.recall_DEFER = 45` | yes, 37 + 8 = 45 exactly |
| the safety factor | `cf_request_defer.SAFETY_FACTOR = 1.8721`, a FIRST-TOKEN bias ratio | see check 6: it is applied to a quantity that includes decode |
| `u` (uncached) | `prompt_tokens - cached_tokens` from the engine's own request log | the arm's own `u_request` is `readiness_tokens - max(built_tokens, telemetry_cached_tokens)`, a different and belief-based quantity; both are named and never mixed |

**5. Claim linkage.** `research/CLAIMS.md` **C5** ("joint representation x placement x timing beats decomposed policies under a quality SLO"). This result **WEAKENS the specific instantiation** of C5's timing lever at 1x: adding the timing counterfactual to rung 3 cost 14 of 127 robot questions at s5 and 5 of 132 at s4, and failed the pre-registered retention bar at s5. It **does not speak to C5 in general**, for two stated reasons: the representation lever was constant (`D2`, defaulted, on every release in both arms), so this pair tests timing alone; and the loss is traced to a service-prediction defect in the implementation rather than to the timing decision's value. Nothing measured here is scoped out by `research/FORMULATION.md` (no KV transfer between tiers, no cross-architecture claim).

**6. Proxy validity.**

| signal | used as a proxy for | what it actually measures | valid for the claim |
|---|---|---|---|
| requests with `t_submit < x.t_submit < t_done` | the work queued ahead of request x | requests whose submit-to-done interval contains x's submit instant, over all kinds (monitor, piece, recall, touch) | valid as a LOWER BOUND on queued-ahead work, which is the direction that matters: the arm used zero. Used for the magnitude of the under-prediction, which is a limitation-grade number, not for the cause attribution |
| `residency.jsonl.telemetry_cached_tokens` at the last row before a submit | the arm's belief about the session's resident prefix | the coordinator's last telemetry snapshot for that session, which `coordinator.py:770-790` states is never reset on eviction | valid for the direction of the error (and the direction is the SAFE one, 111 of 115 pessimistic), not for its exact magnitude |
| `defer_s == 0.5` | "this defer came from the base ladder, not the counterfactual" | a numeric coincidence test | validated independently: it reconciles exactly against `arm_stats.rd_question_defers = 37` and the base arm's 12-of-12 at 0.5 |

**7. Validate the control, not only the result.** Done first, above. Both control arms (`covex-v6-fair-final` s5 and s4) reproduce their committed on-time counts and their full per-device tables exactly, and so do the base and rung-2 arms. The positive control passes on 6 of 6. A broken control is excluded.

---

# OBSERVATIONS

## 1. The pairing (spec item 1)

All 127 s5 robot questions matched one-to-one by `opportunity_id`; the two arms' pools are identical sets, which the scorer also asserts.

| class | s5 count | s4 count |
|---|---|---|
| on time in both | 107 | 119 |
| **on time in rung 3 only (a LOSS)** | **14** | **7** |
| **on time in rung 4 only (a GAIN)** | **0** | **2** |
| missed in both | 6 | 4 |

The spec expected "about 14 to 18" rung-3-only questions. The OBSERVED count is **exactly 14**, and there are **zero** rung-4-only questions at s5.

Whole-arm miss census, both registers, so the brief's figures can be placed:

| arm, s5 | GOVERNING on-time | first-token on-time | unsent | late (GOVERNING) | late (first token) |
|---|---|---|---|---|---|
| `covex-v6-fair-final` (rung 3) | **121** | 121 | 4 | 2 | 2 |
| `covex-v6-final` (rung 4) | **107** | 109 | **12** | **8** | 6 |
| `covex-v6-state-final` (rung 2) | 112 | 118 | 4 | 11 | 5 |
| `hybrid-F-lhreq-noc3` (base) | 27 | 33 | 82 | 18 | 12 |

The brief's "12 unsent vs 4, 6 late vs 2" is the **first-token** register (12 + 6 = 18 misses = 127 - 109). In the GOVERNING register it is 12 unsent vs 4 and **8** late vs 2 (12 + 8 = 20 = 127 - 107). The two extra losses are both `robo002` (`opp0005513`, `opp0010734`): first token inside 3.0 s, completion outside it. Rung 3's per-device table and rung 4's differ on `robo002` by exactly that pair, 27 of 27 in the first-token register against 25 of 27 governing. **Every count below is the governing one.**

## 2 and 3. Every differing question, traced (spec items 2 and 3)


#### seed s5  --  14 paired questions differ (14 rung-3-only, 0 rung-4-only)

| opportunity | device | class | t_opp | deadline | R3 lat (ft / completion) | R4 lat (ft / completion) | R4 cf-defers (defer_s) | R4 base-0.5 defers | R4 decline | R4 re-release t | R4 sent |
|---|---|---|---|---|---|---|---|---|---|---|---|
| opp0001513 | robo006 | rung 3 only | 160.813 | 163.813 | 1.449 / 1.481 | 3.078 / 3.161 | 1 (2.158) | 0 | 0 | 163.04 | yes |
| opp0001842 | robo003 | rung 3 only | 192.345 | 195.345 | 0.623 / 0.842 | - / - | 1 (2.423) | 1 | 0 | - | NO |
| opp0005182 | robo005 | rung 3 only | 516.745 | 519.745 | 0.826 / 0.926 | - / - | 1 (2.575) | 1 | 0 | - | NO |
| opp0005513 | robo002 | rung 3 only | 548.652 | 551.652 | 1.043 / 1.083 | 2.964 / 3.016 | 1 (1.902) | 0 | 0 | 550.75 | yes |
| opp0006201 | robo000 | rung 3 only | 613.913 | 616.913 | 0.529 / 0.550 | - / - | 2 (1.772, 0.610) | 1 | 0 | - | NO |
| opp0006322 | robo005 | rung 3 only | 625.601 | 628.601 | 0.784 / 0.812 | 3.068 / 3.162 | 1 (2.132) | 0 | 0 | 627.85 | yes |
| opp0007388 | robo003 | rung 3 only | 729.427 | 732.427 | 1.189 / 1.222 | - / - | 1 (2.423) | 1 | 0 | - | NO |
| opp0007414 | robo005 | rung 3 only | 731.411 | 734.411 | 0.760 / 0.889 | - / - | 1 (2.467) | 1 | 0 | - | NO |
| opp0007559 | robo005 | rung 3 only | 744.764 | 747.764 | 0.765 / 0.808 | - / - | 1 (2.237) | 1 | 1 | - | NO |
| opp0008287 | robo005 | rung 3 only | 815.739 | 818.739 | 1.640 / 1.667 | 3.532 / 3.616 | 0 (-) | 0 | 0 | 815.86 | yes |
| opp0008338 | robo006 | rung 3 only | 820.921 | 823.921 | 2.204 / 2.567 | 3.418 / 3.776 | 0 (-) | 0 | 0 | 820.96 | yes |
| opp0008976 | robo006 | rung 3 only | 882.547 | 885.547 | 1.240 / 1.316 | - / - | 1 (2.315) | 1 | 0 | - | NO |
| opp0008991 | robo006 | rung 3 only | 883.620 | 886.620 | 0.376 / 0.416 | - / - | 1 (2.358) | 1 | 1 | - | NO |
| opp0010734 | robo002 | rung 3 only | 1052.636 | 1055.636 | 1.027 / 1.063 | 2.996 / 3.033 | 1 (2.252) | 0 | 0 | 1054.96 | yes |

| opportunity | R4 u (uncached) | R4 queued-ahead u | D162 pred (qa=0, as used) | D162 pred (qa observed) | observed first token | obs/pred(qa=0) | kappa in use | R3 u | R3 cached | R4 cached |
|---|---|---|---|---|---|---|---|---|---|---|
| opp0001513 | 1588 | 3113 | 0.357 | 0.836 | 0.818 | 2.29 | 1.8721 | 1498 | 8736 | 8736 |
| opp0001842 | - | - | - | - | NOT SENT | - | 1.8721 | 652 | 12688 | - |
| opp0005182 | - | - | - | - | NOT SENT | - | 1.8721 | 771 | 9264 | - |
| opp0005513 | 1472 | 742 | 0.336 | 0.450 | 0.820 | 2.44 | 1.8721 | 1382 | 23584 | 23584 |
| opp0006201 | - | - | - | - | NOT SENT | - | 1.8721 | 199 | 17104 | - |
| opp0006322 | 2211 | 366 | 0.470 | 0.527 | 0.764 | 1.63 | 1.8721 | 2121 | 12864 | 12864 |
| opp0007388 | - | - | - | - | NOT SENT | - | 1.8721 | 1300 | 22768 | - |
| opp0007414 | - | - | - | - | NOT SENT | - | 1.8721 | 315 | 19440 | - |
| opp0007559 | - | - | - | - | NOT SENT | - | 1.8721 | 679 | 19616 | - |
| opp0008287 | 11999 | 1118 | 2.252 | 2.424 | 3.372 | 1.50 | 1.8721 | 4143 | 19392 | 11536 |
| opp0008338 | 8646 | 4894 | 1.641 | 2.395 | 3.339 | 2.03 | 1.8721 | 6198 | 15568 | 13120 |
| opp0008976 | - | - | - | - | NOT SENT | - | 1.8721 | 972 | 23584 | - |
| opp0008991 | - | - | - | - | NOT SENT | - | 1.8721 | 262 | 24384 | - |
| opp0010734 | 808 | 746 | 0.215 | 0.330 | 0.628 | 2.92 | 1.8721 | 724 | 19888 | 19984 |

#### seed s4  --  9 paired questions differ (7 rung-3-only, 2 rung-4-only)

| opportunity | device | class | t_opp | deadline | R3 lat (ft / completion) | R4 lat (ft / completion) | R4 cf-defers (defer_s) | R4 base-0.5 defers | R4 decline | R4 re-release t | R4 sent |
|---|---|---|---|---|---|---|---|---|---|---|---|
| opp0001451 | robo000 | rung 3 only | 156.678 | 159.678 | 1.313 / 1.351 | 2.828 / 3.123 | 1 (1.396) | 0 | 0 | 158.17 | yes |
| opp0003111 | robo006 | rung 4 only | 316.219 | 319.219 | 4.008 / 4.219 | 0.656 / 0.813 | 0 (-) | 0 | 0 | 316.27 | yes |
| opp0003132 | robo006 | rung 3 only | 318.387 | 321.387 | 1.841 / 2.052 | - / - | 1 (2.709) | 1 | 0 | - | NO |
| opp0005847 | robo004 | rung 3 only | 581.010 | 584.010 | 1.315 / 1.342 | - / - | 1 (2.083) | 1 | 1 | - | NO |
| opp0008132 | robo001 | rung 3 only | 801.360 | 804.360 | 1.450 / 1.501 | 2.938 / 3.001 | 1 (2.000) | 0 | 0 | 803.58 | yes |
| opp0008461 | robo001 | rung 3 only | 834.709 | 837.709 | 0.911 / 0.963 | 2.812 / 3.120 | 1 (1.867) | 0 | 0 | 836.68 | yes |
| opp0009518 | robo006 | rung 4 only | 934.472 | 937.472 | 2.466 / 3.315 | 1.283 / 1.307 | 0 (-) | 0 | 0 | 934.58 | yes |
| opp0009524 | robo000 | rung 3 only | 934.913 | 937.913 | 2.874 / 2.900 | 3.352 / 3.359 | 1 (0.621) | 0 | 0 | 935.68 | yes |
| opp0009788 | robo001 | rung 3 only | 961.245 | 964.245 | 1.283 / 1.338 | - / - | 1 (2.301) | 1 | 1 | - | NO |

| opportunity | R4 u (uncached) | R4 queued-ahead u | D162 pred (qa=0, as used) | D162 pred (qa observed) | observed first token | obs/pred(qa=0) | kappa in use | R3 u | R3 cached | R4 cached |
|---|---|---|---|---|---|---|---|---|---|---|
| opp0001451 | 4483 | 2534 | 0.884 | 1.274 | 1.293 | 1.46 | 1.8721 | 4483 | 2976 | 2976 |
| opp0003111 | 392 | 16912 | 0.139 | 2.744 | 0.574 | 4.12 | 1.8721 | 488 | 16464 | 16560 |
| opp0003132 | - | - | - | - | NOT SENT | - | 1.8721 | 210 | 16832 | - |
| opp0005847 | - | - | - | - | NOT SENT | - | 1.8721 | 1468 | 25472 | - |
| opp0008132 | 1630 | 752 | 0.364 | 0.480 | 0.679 | 1.86 | 1.8721 | 1540 | 13584 | 13584 |
| opp0008461 | 1624 | 373 | 0.363 | 0.421 | 0.784 | 2.16 | 1.8721 | 1630 | 15024 | 15120 |
| opp0009518 | 1038 | 2165 | 0.257 | 0.590 | 1.130 | 4.40 | 1.8721 | 1038 | 24832 | 24832 |
| opp0009524 | 10985 | 2053 | 2.067 | 2.383 | 2.535 | 1.23 | 1.8721 | 10985 | 0 | 0 |
| opp0009788 | - | - | - | - | NOT SENT | - | 1.8721 | 1268 | 21056 | - |

### The two life histories, in words

**Pattern A, "deferred then dropped" (8 of 14 at s5, 3 of 7 at s4).** The counterfactual defers the question to its latest safe start, consuming 1.77 to 2.58 s of a 3.0 s budget. On the re-offer the base's own feasibility ladder sees `est > slack` and takes the middle rung, `est <= slack + 0.5`, issuing **its** fixed 0.5 s defer (`arms_builder.py:258-259`). `coordinator.py:858` sets `defer_until = t + 0.5`, which is now **past** the question's absolute deadline, so `coordinator.py:894-895` can never re-offer it (the re-offer requires `defer_until <= t` AND `deadline_abs() >= t`) and `coordinator.py:2102` sweeps it as a miss with no answer. Worked example, `opp0001842`: `t_opportunity` 192.345, deadline 195.345; counterfactual defer at t=192.44 for 2.423 s; base defer at t=194.94 for 0.5 s, so the next look is at 195.44, which is 0.095 s past the deadline. Two of the eight (`opp0007559`, `opp0008991`) survived one more epoch and got an explicit `decline` instead, the ladder's bottom rung. **No request was ever submitted for any of the eight.**

**Pattern B, "deferred then late" (4 of 14 at s5, 4 of 7 at s4).** The question is re-offered at the planned start and submitted, and the service overruns the remaining budget. Decomposed:

| opportunity | planned latest safe start | re-released at | epoch-grid delay | GOVERNING completion latency | overrun | the grid delay alone explains it? |
|---|---|---|---|---|---|---|
| s5 `opp0001513` | 162.998 | 163.040 | 0.042 s | 3.161 s | +0.161 s | no, service under-prediction dominates |
| s5 `opp0005513` | 550.652 | 550.750 | 0.098 s | 3.016 s | +0.016 s | **yes** |
| s5 `opp0006322` | 627.782 | 627.850 | 0.068 s | 3.162 s | +0.162 s | no |
| s5 `opp0010734` | 1054.912 | 1054.960 | 0.048 s | 3.033 s | +0.033 s | **yes** |
| s4 `opp0001451` | 158.166 | 158.170 | 0.004 s | 3.123 s | +0.123 s | no |
| s4 `opp0008132` | 803.480 | 803.580 | 0.100 s | 3.001 s | +0.001 s | **yes** |
| s4 `opp0008461` | 836.647 | 836.680 | 0.033 s | 3.120 s | +0.120 s | no |
| s4 `opp0009524` | 935.601 | 935.680 | 0.079 s | 3.359 s | +0.359 s | no |

Register: the last column is a **CONSTRUCTED** first-order shift (subtract the grid delay from the observed completion), not a replayed outcome. On that construction, 2 of the 4 at s5 and 1 of the 4 at s4 are lost to the 100 ms decision grid alone: `defer_s` is computed to land the start *exactly* at the latest safe start, and the opportunity is then re-offered at the next epoch boundary, which is strictly later. `cf_request_defer.py:173-175` acknowledges the grid ("a deferral shorter than one decision period cannot be enacted") and uses it as a floor on `deferral_s`, but nothing subtracts a period from `deferral_s` to pay for the quantization.

**Pattern C, "the counterfactual never touched it" (2 of 14 at s5, 0 of 7 at s4).** `opp0008287` (`robo005`) and `opp0008338` (`robo006`) carry no `defer`, no base defer and no `decline`; both were released in rung 4 within 0.12 s of their release in rung 3. They were late because their session was **less resident at submit**, on a byte-identical prompt:

| opportunity | prompt tokens, both arms | cached, rung 3 | cached, rung 4 | uncached, rung 3 | uncached, rung 4 | first token, rung 3 | first token, rung 4 |
|---|---|---|---|---|---|---|---|
| `opp0008287` | 23,535 | 19,392 | **11,536** | 4,143 | **11,999** | 1.505 s | **3.372 s** |
| `opp0008338` | 21,766 | 15,568 | **13,120** | 6,198 | **8,646** | 2.046 s | **3.339 s** |

For `opp0008287` the chain is traceable and it is the arm's own: on session `robo005|s001|...614065`, rung 3 sent 12 recall requests before t=816 and rung 4 sent 9, the three missing ones being `opp0005182`, `opp0007414` and `opp0007559`, all Pattern A. The engine's telemetry for that session climbs to 20,160 tokens in rung 3 by t=790 and **falls** to 15,984 in rung 4 over the same window. **A question the arm drops is also a prefix the arm stops touching**, and the prefix ages out. For `opp0008338` the arm's own decisions and beliefs for that session are identical in the two arms (same 4 release counts, `believed_tier "gpu"` and `telemetry_cached_tokens` 15,936 at t=740.5 in both), yet the engine held 13,120 against 15,568: that divergence is cross-session eviction pressure from a fleet whose request schedule rung 4 shifted by 37 deferrals, i.e. spec cause (d), downstream congestion, with 4 requests carrying 4,894 uncached tokens in flight at its submit instant.

### The gains (spec item 3)

**At s5 there are none.** Thirty-seven question-deferrals fired and not one converted a rung-3 miss into a rung-4 hit. At s4 there are two, and they are the mechanism working as designed:

| opportunity | device | rung 3 (ft / GOVERNING) | rung 4 (ft / GOVERNING) | own defers | queued-ahead uncached at submit |
|---|---|---|---|---|---|
| `opp0003111` | robo006 | 4.008 / **4.219** LATE | 0.656 / **0.813** ON TIME | none | 16,912 tokens over 4 requests |
| `opp0009518` | robo006 | 2.466 / **3.315** LATE | 1.283 / **1.307** ON TIME | none | 2,165 tokens over 6 requests |

Neither was itself deferred: both were *helped* by other questions being held back, which is exactly the saving the inequality is supposed to buy. Note the register: `opp0009518` was on time at first token in rung 3 (2.466 s) and late at completion (3.315 s), so it is a gain only in the governing register.

## 4. Counts by cause, and the reconciliation (spec item 4)

Cause letters as the spec defines them.

| cause | s5 | s4 | opportunities (s5) |
|---|---|---|---|
| **(b) deferred, then dropped by the release re-check** (counterfactual defer, then the base ladder's 0.5 s defer past the deadline, 2 of them with an explicit `decline`) | **8** | 3 | `opp0001842`, `opp0005182`, `opp0006201`, `opp0007388`, `opp0007414`, `opp0007559`\*, `opp0008976`, `opp0008991`\* |
| **(a) deferral ran past the deadline** (re-offered, submitted, delivered late; safe start mispredicted) | **4** | 4 | `opp0001513`, `opp0005513`, `opp0006322`, `opp0010734` |
| (c) a protect-and-defer of ANOTHER session displaced it | **0** | 0 | ruled out by census: zero `PROTECT_AND_DEFER` actions in the run |
| **(d) the counterfactual did not touch it; lost to downstream congestion** | **1** | 0 | `opp0008338` (4 requests, 4,894 uncached tokens, in flight at submit) |
| **(e) other: the counterfactual did not touch it; lost to residency the arm's OWN earlier drops gave up** | **1** | 0 | `opp0008287` (3 questions dropped earlier on the same session; cached 11,536 against 19,392) |
| **total losses** | **14** | **7** | |
| gains (cause: other questions deferred out of the way) | **0** | **2** | |

\* also received an explicit `decline`.

Sub-cause of (a), from the table above: 2 of the 4 at s5 are attributable to the 100 ms epoch grid alone on a CONSTRUCTED shift, 2 to service under-prediction proper.

**Reconciliation.**

```
losses  14
gains  - 0
----------
net    14      against the observed gap 121 - 107 = 14
residual 0
```

s4: losses 7, gains 2, net 5, against the observed gap 126 - 121 = 5, **residual 0**.

Cross-check from the independent direction, the whole-arm miss census: new unsent 12 - 4 = 8 (equals the cause (b) count) and new late 8 - 2 = 6 (equals causes (a) + (d) + (e) = 4 + 1 + 1). Both decompositions close with no unexplained residual.

## 5. Seed contrast (spec item 5)

| | s4 (rung 4 PASSED, 0.945) | s5 (rung 4 FAILED, 0.851) |
|---|---|---|
| pool n | 132 | 127 |
| rung 3 / rung 4 on time, GOVERNING | 126 / 121 | 121 / 107 |
| retention against the 0.90 bar | 0.945055 PASS | 0.851064 FAIL |
| question-deferrals fired (`rd_question_defers`) | 29 | **37** |
| base-ladder 0.5 s defers downstream of one | 3 | **8** |
| explicit `decline` rows | 2 | 5 |
| losses: (b) dropped / (a) late / (d) / (e) | 3 / 4 / 0 / 0 | **8 / 4 / 1 / 1** |
| **gains** | **2** | **0** |
| net | 5 | 14 |
| deferred-re-offer observed/predicted service, completion: p50 / p90 / max | 2.134 / 3.800 / 29.703 | 1.887 / 2.595 / 3.095 |
| fraction of deferred re-offers whose completion bias exceeds the 1.8721 factor | 0.654 | 0.500 |

**The loss mechanism is the same at both seeds and only its size differs, with one qualification that matters: the *gain* side also differs in kind.** The losses are the same two patterns in the same proportions per deferral (s4: 7 losses from 29 deferrals, 0.24 per deferral; s5: 12 defer-attributable losses from 37 deferrals, 0.32 per deferral). What flips the verdict is that s4's 29 deferrals bought 2 rescues and s5's 37 bought **none**, so at s5 the mechanism is pure cost. At s5 the counterfactual also pushed twice as many questions into the base ladder's reject band (8 against 3), which is the part that scales worse than linearly: a deferral that merely delays a question costs at most one question, while a deferral that pushes a question off the end of the ladder also costs its session's warm prefix and so can cost a second question (`opp0008287`).

**s6 and s7: NOT RUN for these arms.** At `origin/main = 26f036ba8bd652fdc35816c1ec82c6da8f21df8b`, resolved at the end of this investigation, `results/orchestration/live2/frozen_test/runs/` contains `hybrid-F-lhreq-noc3_n16_s6_...` and `_s7_...` but **no** `covex-v6-final` or `covex-v6-fair-final` cell at s6 or s7; only s4 and s5 exist for the ladder arms. Per the brief this is reported, not waited on.

```
$ git ls-tree --name-only 26f036ba:results/orchestration/live2/frozen_test/runs/ \
    | grep -E 'covex-v6-(final|fair-final)_n16_s[4567]_1200s_h27_3t_L3_epg_rq30$'
covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30
covex-v6-fair-final_n16_s5_1200s_h27_3t_L3_epg_rq30
covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30
covex-v6-final_n16_s5_1200s_h27_3t_L3_epg_rq30
rc=0
```

## 6. Mechanism checks (spec item 6)

**(i) Is the latest safe start computed with the per-request q90 safety factor, or an older value?** It uses the **MEASURED D162 under-prediction factor, `SAFETY_FACTOR = 1.8721`**, not the older service-residual kappa and not 1.863. `cf_request_defer.py:137` reads `d190_measured_safety.SAFETY_FACTOR`; `:249` passes it to `cf_cost.latest_safe_start`; `:121-135` states explicitly that `cf_protect_defer.KAPPA = 1.5775406165458339` is **not** used on this path and is left alone because its arms belong to another session. The value is the nearest-rank q90 over **n = 5** recall questions in `d190_recall_lag_diagnosis.json`, which at n = 5 **is the maximum of the sample**; two caveats travel with it in the code (the split is held-out-by-arm, and the residual summary carries `gate_status: FAILS`). The brief's 1.863 is not a value in the tree.

**And the factor is too small for this traffic, measured on the cells' own data.** Observed over D162-predicted, completion, on the questions the counterfactual deferred and then re-offered: s5 p50 1.887, p90 2.595, max 3.095, with **50 percent above 1.8721**; s4 p50 2.134, p90 3.800, **65 percent above**. Over all 115 robot recall requests at s5 the first-token ratio is p50 2.080, p90 3.822, max 6.706, 65 percent above the factor. A q90 chosen to be a q90 is sitting near this traffic's **median**.

**And it is a register mismatch at the point of use.** The factor was fitted on `observed_over_predicted` of **first token** (`d190_measured_safety.py:21,56`), and it multiplies `pred.total_s`, which `cf_cost.py:10-16,130-132` defines as first token **plus decode** plus link. A first-token bias ratio applied to a first-token-plus-decode budget is not the same quantity, and decode is the part that grows with context length (`cf_cost.py:10`: "at a 3 s deadline decode is up to 47 percent of the budget").

**And the deepest part is not the factor at all: the service prediction zeroes the queue.** `arms_v6cfr3.py:197` calls `CC.predict(cf.model, int(u_request), 0, 0, 0)`: `overlap_ft = 0` and `overlap_decode = 0`. D162's second term is `0.000154 * uncached_queued_ahead`, so the deferral prices its restart **as if the engine were empty**, on a decision `cf_request_defer.py:267-269` only reaches when the harm population is non-empty, i.e. precisely when it is not. Measured on the six sent losses at s5:

| opportunity | u | queued-ahead uncached (OBSERVED proxy) | D162 as the arm used it (queue = 0) | D162 with the queue | observed first token | obs/pred(queue=0) | obs/pred(queue real) |
|---|---|---|---|---|---|---|---|
| `opp0001513` | 1,588 | 3,113 | 0.357 s | 0.836 s | 0.818 s | 2.29 | **0.98** |
| `opp0005513` | 1,472 | 742 | 0.336 s | 0.450 s | 0.820 s | 2.44 | 1.82 |
| `opp0006322` | 2,211 | 366 | 0.470 s | 0.527 s | 0.764 s | 1.63 | 1.45 |
| `opp0008287` | 11,999 | 1,118 | 2.252 s | 2.424 s | 3.372 s | 1.50 | 1.39 |
| `opp0008338` | 8,646 | 4,894 | 1.641 s | 2.395 s | 3.339 s | 2.03 | **1.39** |
| `opp0010734` | 808 | 746 | 0.215 s | 0.330 s | 0.628 s | 2.92 | 1.90 |

Restoring the queue term alone removes most of the bias on the two largest cases and all of it on one. The committed 1.8721 factor **does** cover the residual bias on 4 of the 6 once the queue term is present.

**(ii) Is the robot question's own `w_d` in the deferral comparison, and with which sign?** Yes, **twice, and both signs protect the question**.

* On the net: `own_loss = w_R * max(p_before - p_after, 0)` with `w_R = w_of(decider_device_id)`, the question's **own** device (`cf_request_defer.py:329`), and `net = harm_saved - own_loss` (`:335`). A lagging robot device therefore makes the deferral look **worse**. Sign: **negative on the net**.
* On the bar: `bar = w_d * MARGIN_CF_ON_TIME` with `reading = "decider"`, so `w_d` is again the question's own device (`cf_protect_defer.py:253-259`), and the gate is `net > bar`. A lagging robot device therefore **raises** the bar. Sign: **positive on the bar**, which also defers less.

It is live and it varies: `arm_stats.rd_decider_weight_above_floor = 87` of `rd_decisions = 152` at s5 had `w_decider > 1.0`, so 57 percent of candidates carried a weight off the D185 floor. This is not `cancelled by geometry`: `cf_protect_defer.py:241-249` records that scaling the weight *does* cancel between harm and bar, which is why the Step 4 control scales the bar alone, and the decider weight enters the net through `own_loss`, which no harm row carries.

**(iii) How often did a deferred question's re-offer find the session cold when the belief said warm?** **ZERO.** All 28 sent re-offers at s5 came back `cache_path = WARM` with `cached_tokens > 0`, and the belief said `believed_tier = "gpu"` on every one. Across all 115 rung-4 robot recall requests that had a prior `residency.jsonl` row, **zero** had a non-cold belief meet a `COLD` cache path, and the belief's token count was **pessimistic on 111 of 115** (understating the resident prefix, which inflates `u`, inflates the predicted service and moves the latest safe start **earlier**, the safe direction) and optimistic on only 4, worst overstatement 4,448 tokens. The rung-3 control is 4 optimistic of 123, worst 1,456 tokens. **The residency belief is not the cause of this failure and this check excludes it.** What the belief *does* get wrong is magnitude inside a correct label, exactly the exposure `cf_request_defer.RESIDENCY_INPUT` pre-declares: on `opp0008338` both arms believed `gpu` at 15,936 tokens while the engine held 15,568 in one and 13,120 in the other, so the belief could not tell the two situations apart.

**(iv) Is any loss a decision the pre-registration says the counterfactual must not make, i.e. a deviation below `w_d x MARGIN_CF`?** **NOT DETERMINABLE PER-DECISION FROM THE COMMITTED CELL, and the reason is an instrumentation gap, not an absent mechanism.** `cf_request_defer.decide` computes `net_gain`, `bar_value`, `w_decider`, `harm_now`, `harm_saved`, `own_loss` and `would_miss_deadline_under_measured_bias` on every candidate and `arms_v6cfr3._rd_record` keeps up to 4,000 of them in `self.rd_decisions`, but the committed cell carries only the **aggregates** in `coordinator_result.json -> arm_stats` (`rd_decisions` is the integer 152, not the list), and `decision.jsonl.gz` has no harm, bar, `w_d`, `crosses_bar` or gate field at all. What can be said, and the register is **CONSTRUCTED from the code path plus the OBSERVED gate census rather than audited per decision**: the gate is a strict `net > bar` at `cf_request_defer.py:339`, nothing enacts below it (`arms_v6cfr3.py:291` returns unless `action == "DEFER_TO_LATEST_SAFE_START"`), and the census is consistent with that -- `rd_gate_saving_does_not_exceed_margin = 69` candidates were refused by the bar, `rd_gate_must_start_now_no_slack = 31`, `rd_gate_no_active_alert_episode = 15`, and `rd_gate_defer_to_latest_safe_start = 37` fired, summing to 152. So **no loss appears to be a sub-margin deviation**, but that is an inference from the gate counts and the code, not a per-question verification, and it would take one instrumented replay to close.

---

# CONCLUSION (spec item 7), separated from the observations above

## The dominant cause, with its count

**The dominant cause is the question-deferral's own mispredicted latest safe start, and it accounts for 12 of the 14 lost questions.** It fails in two ways from one root. In 8 of 14 the deferral consumed so much of the 3.0 s budget that the base arm's feasibility ladder re-deferred the question by its fixed 0.5 s quantum past the deadline and the coordinator swept it unsent; in 4 of 14 the question was re-offered at the planned start and the service overran. The remaining 2 of 14 are knock-ons of the same mechanism acting a step away: a question dropped by the counterfactual is also a prefix the arm stops touching (`opp0008287`, cached 11,536 against 19,392 on an identical prompt), and the deferrals' reshuffling of the fleet's request schedule changed what the engine evicted (`opp0008338`). Protect-and-defer contributed **nothing**: it took zero actions in the whole run.

**This is a null of the kind Rule 2 calls `fired and did not help`, on the gain side, with a measured cost side.** The mechanism was present, reached a decision 152 times, fired 37 times, and the Step 4 negative control (rung 3, the same arm without the two legs) changes the result. At s5 it produced zero rescues and 12 direct losses; at s4 it produced 2 rescues and 7 losses. It is not `unexercised`, not `cancelled by geometry`, not `unexpressible` and not `unscorable`. It is a real negative about this implementation of the timing lever at 1x, and it is still not a settled negative about the timing lever itself, for the reason in the next paragraph.

## Defect or property of the design at 1x

**It is a DEFECT, and it is an implementation defect with a calibration defect sitting on top of it. It is not a property of the design at 1x.** Three findings separate the two, in descending order of how clearly they are bugs:

1. **Implementation. The service prediction that sets the latest safe start zeroes the queue.** `arms_v6cfr3.py:197` calls `CC.predict(cf.model, int(u_request), 0, 0, 0)`, so D162's `0.000154 * uncached_queued_ahead` term is identically zero on every deferral decision, on a gate that is only reached when other requests are pending. Measured on the six sent losses, restoring that term alone takes the observed-over-predicted ratio from 2.29 to 0.98 on `opp0001513` and from 2.03 to 1.39 on `opp0008338`, and brings 4 of the 6 inside the committed 1.8721 factor. This is a zero written into a live model argument, which is the same shape as the write-only-field family this codebase keeps finding.
2. **Implementation. The deferral is computed to land exactly on the latest safe start and then enacted one epoch later.** `deferral_s = latest_start - now` with no allowance for the 100 ms decision grid, while the opportunity can only be re-offered at an epoch boundary. On a CONSTRUCTED shift this alone accounts for 2 of the 4 "deferred and late" losses at s5 and 1 of 4 at s4, all of them inside 0.035 s of the deadline. `cf_request_defer.py:173-175` uses the period as a floor on the deferral and nowhere as a debit against it.
3. **Calibration. The safety factor is a q90 of n = 5 that sits near this traffic's median, and it is a first-token ratio applied to a first-token-plus-decode budget.** `SAFETY_FACTOR = 1.8721` is exceeded by the completion bias on **50 percent** of s5's deferred re-offers and **65 percent** of s4's. A factor meant to bound the 90th percentile is bounding about the 50th.

What is *not* the cause, and each is excluded by a census rather than by argument: the residency belief (zero believed-warm-met-cold in 115 requests; the belief errs pessimistic, the safe direction, on 111 of 115); protect-and-defer (zero actions); the representation lever (constant `D2`, defaulted, on 472 of 472 and 480 of 480 releases, so this pair of cells does not test it); the over-32k context limit (seed 5 has no such question); and the `arms_v6cf.py` docstring confound (already ruled decision-neutral and not re-opened).

Why s4 passed and s5 failed, stated plainly: the cost side behaves the same at both seeds, and the **benefit** side is a coin flip at this volume. Twenty-nine deferrals bought 2 rescues at s4 and 37 bought 0 at s5. With a 0.90 bar on a 127-question pool, 13 questions is the entire margin, so a mechanism whose gains are 0 to 2 per 30 firings and whose losses are 7 to 12 cannot clear that bar at 1x on either seed by design; **s4's pass at 0.945 is the luckier draw of the same losing trade, not a different regime.** That is the part of the conclusion the user should weigh most heavily, because it says the s5 failure is the honest reading and the s4 pass is the one that needs the caveat.

## The change that would remove it, COSTED, NOT BUILT

Four items, in the order their cost-to-benefit ratio favours. **None of these is built, and none should be built before the user rules, because items 1 and 3 change what every committed rung-4 cell measures.**

**Item 1 -- pass the real queue into the deferral's service prediction.** Change `arms_v6cfr3.py:197` from `CC.predict(cf.model, int(u_request), 0, 0, 0)` to pass the uncached tokens of the requests the arm already enumerates in `_pd_others` as `overlap_ft`, and the same for `overlap_decode`. *Cost:* a one-line call-site change plus a reader for a quantity the arm already assembles for the harm sum, so no new observation and no coordinator edit; roughly half a day including the proof that the quantity reaching `predict` is the one intended. **Then the full s4 and s5 pair must be re-run and re-scored (4 live cells), because this moves every deferral decision**, plus a Step 2b decision-log diff on one cell before the sweep and a port-rule count confirming the deferral still fires. *Expected effect, from the table in check (i):* 4 of the 6 sent losses come inside the existing factor; it does nothing for the 8 unsent, which are lost to the magnitude of the deferral rather than to its endpoint, so expect it to recover the 4 Pattern-B losses and some fraction of the 8 by shortening the deferrals that caused them. *Risk:* a larger predicted service means an earlier safe start, which means shorter deferrals and less harm saved, so the 2 gains at s4 may shrink too. This is the change I would make first and it is the only one that is unambiguously a bug fix.

**Item 2 -- debit one decision period from the deferral.** `deferral_s = max(latest_start - now - DECISION_PERIOD_S, 0.0)` in `cf_request_defer.decide`, with the existing `MIN_DEFERRAL_S` gate unchanged. *Cost:* one line, one unit test in `cf_pd_tests.py`, and the same 4-cell re-run as item 1 (it should be made in the same pass, not a second one). *Expected effect:* removes the 2 s5 and 1 s4 losses whose overrun is smaller than their grid delay, on the CONSTRUCTED arithmetic above. *Risk:* near zero; it moves the start earlier, which is the safe direction, and costs at most 100 ms of harm saved per deferral.

**Item 3 -- do not let a deferral push a question into the base ladder's reject band.** This is the 8-of-14 majority cause and it is the expensive one, because the fix is a design choice and not a line. The cheapest version that is still honest: before enacting, require that the post-deferral slack still leave the **base's own** admission test satisfiable, i.e. refuse the deferral when `latest_start` would leave less than the base's `est + defer_s`, and count the refusals. *Cost:* the arm must read the base's feasibility estimate, which it does not currently do (`arms_builder._rc_service_s` is the base's own method and the counterfactual mixin does not call it), so this is a new coupling between rung 4 and the base arm, about two days with its proofs, and it needs a pre-registered statement of what the new gate is before any cell runs. Then the same 4-cell re-run. *Expected effect:* converts most of the 8 Pattern-A losses into non-deferrals, i.e. into rung-3 behaviour, which recovers the questions and gives up whatever harm those deferrals were saving. *Risk:* this is the change most likely to turn rung 4 into rung 3 with extra steps, and if it does, that is itself the finding -- it would say the question-deferral has no room to act at this deadline.

**Item 4 -- re-fit the safety factor on an adequate sample, or state it as a lower bound.** The present factor rests on n = 5 and is a first-token ratio used against a completion budget. *Cost:* no new cells -- the committed rung-3 cells at s4 and s5 together carry 244 robot recall requests with the fields needed, so this is a read-only fit of a few hours. *But it must be ruled on first:* `cf_request_defer.py:121-135` pre-registers that the factor comes from the **base's** committed cells and not rung 4's, and re-fitting it on cells that now include rung 4's own would be tuning to the cells under diagnosis. The defensible version is to re-fit on the rung-3 cells only, on the **completion** ratio rather than the first-token one, and to report the change in register. *Expected effect:* a factor near 2.6 to 3.1 instead of 1.8721, which shortens every deferral by 40 to 60 percent and therefore overlaps heavily with items 1 and 3. **Do item 1 first and re-measure before touching this**, because item 1 may remove most of the apparent bias that would otherwise be absorbed into a larger factor.

A fifth item is worth one line because it is what made 6 (iv) unanswerable: **commit the per-decision `rd_decisions` list that the arm already builds.** `arms_v6cfr3._rd_record` keeps up to 4,000 rows with `harm_now`, `harm_saved`, `own_loss`, `net`, `bar`, `w_decider`, `deferral_s` and `would_miss_under_measured_bias`, and none of it reaches the cell; only `arm_stats` aggregates do. Writing that list beside `decision.jsonl.gz` is a few lines and would have made the sub-margin audit a grep instead of an inference.

## What could NOT be determined, and why

| item | why |
|---|---|
| spec 6 (iv), per-question audit of `net` against `w_d x MARGIN_CF` | the committed cell carries only `arm_stats` aggregates; `decision.jsonl.gz` has no harm, bar, `w_d`, `crosses_bar` or gate field. Answered by construction from the code path plus the gate census, which is a weaker register and is marked as such |
| spec 2, "the harm, the bar, `w_d`, `crosses_bar`, gate reason" per question | same gap. Reported at run level from `arm_stats` instead |
| spec 2, "predicted vs actual first token" as the arm recorded it | `decision.predicted.ttft_s` and `predicted.completion_s` are **null on all 11,641 rung-4 rows**. Reconstructed from the committed D162 formula and the arm's own `u` rule, which is a reconstruction and not the arm's recorded prediction |
| spec 5, s6 and s7 | no `covex-v6-final` or `covex-v6-fair-final` cell exists at s6 or s7 at `origin/main = 26f036ba`; only the base arm has them. Reported, not waited on, per the brief |
| whether the two arms' different coordinator commits (`f99f69e8` against `bf1ae16d`) contributed | `digests_equal` is true and both carry `arm_version "covex-v6-fair-feed-1.0"`, and the already-ruled docstring check found the tree difference decision-neutral, so this is recorded as a limitation rather than a suspected cause. Closing it would need a dry replay, which this investigation did not run |
| the exact queued-ahead token count the engine saw | the proxy is submit-to-done interval overlap from the request log, valid as a lower bound. Used for magnitude only, never for cause attribution |

---

# PROPOSED `research/EXPERIMENTS.md` ROW (a PROPOSAL; no E-id is invented here and none is claimed)

This investigation is a read-only diagnostic of cells that already belong to `StudyLADDER-FINAL`, so the cheapest correct home for it is a verdict amendment on that row rather than a new study. If the user prefers a row of its own, the proposed text is below and the id is deliberately left blank for the user to assign. **Nothing in `research/EXPERIMENTS.md`, `research/STATUS.md` or any run-path file was edited by this session**, because the ladder freeze was in force and those files are other sessions' write targets tonight.

> `| Study<ID-TO-BE-ASSIGNED> | orchestration | Read-only diagnosis of why covex-v6-final (rung 4) fails check 2 at seed 5: pair every s5 robot question against covex-v6-fair-final by opportunity_id, classify each loss and gain by cause, and audit the question-deferral leg's latest safe start. No code change, no new cell, no replay. | read-only analysis of the committed cells; scorer register re-implemented from the committed experiments/orchestration/live2/scorer/score.py | committed cells covex-v6-{final,fair-final,state-final}_n16_s{4,5}_1200s_h27_3t_L3_epg_rq30 and hybrid-F-lhreq-noc3_n16_s5; no new measurements | reports/study_rung4_s5_failure.md | flash (CPU only) | 6 committed cells, 259 paired robot questions, 0 cells run | THE 14-QUESTION GAP IS FULLY ACCOUNTED FOR, residual ZERO, and the dominant cause is OUR OWN DEFECT. 12 of 14 losses are the question-deferral's mispredicted latest safe start: 8 deferred then re-deferred by the base ladder's fixed 0.5 s quantum past the deadline and swept unsent, 4 re-offered and delivered late. 2 of 14 are knock-ons (a dropped question is a prefix no longer touched: cached 11,536 against 19,392 on an identical 23,535-token prompt). Protect-and-defer took ZERO actions (299 decisions, all stopped at two gates), so cause (c) is ruled out by census. ROOT CAUSE, arms_v6cfr3.py:197 passes overlap_ft=overlap_decode=0, so D162's queued-ahead term is identically zero on a gate only reached when requests ARE queued; restoring it takes observed/predicted from 2.29 to 0.98 on opp0001513. SECOND, deferral_s lands exactly on the latest safe start and is enacted one 100 ms epoch later, which alone explains 2 of the 4 late losses on a constructed shift. THIRD, SAFETY_FACTOR 1.8721 (q90 of n=5, and a FIRST-TOKEN ratio applied to a first-token-plus-decode budget) is exceeded by the observed completion bias on 50 percent of s5 and 65 percent of s4 deferred re-offers. EXCLUDED BY CENSUS: residency belief (0 of 115 believed-warm-met-cold; pessimistic, the safe direction, on 111 of 115), protect-and-defer, the representation lever (constant D2 defaulted on 472 of 472 and 480 of 480 releases, so this pair tests TIMING ALONE), and the over-32k limit (absent at s5). SEED CONTRAST: the same mechanism at s4, 7 losses and 2 gains for net 5; at s5, 14 losses and ZERO gains. s4's 0.945 pass is the luckier draw of the same losing trade, not a different regime. | consistency_check 7 of 7 PASS, positive control EXACT on 6 of 6 committed arms including both controls; one name with two values found (header.json targets.robot.L_s = 5.0 against the sweep's L_rob = 3) | mechanism_verification Steps 0 to 5 RECORDED, negative control on committed cells CHANGES the result (121 against 107), Rule 2 class FIRED AND DID NOT HELP; spec item 6 (iv) NOT DETERMINABLE from the committed cell (per-decision harm, bar and w_d are not committed, only arm_stats aggregates) |`

## Scratch artefacts (not committed, session-local, may be cleared)

`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/r4s5/` holds the extracted cell files and the analysis scripts `pair.py`, `trace.py`, `full.py`, `census.py`, `sess.py`, `tables.py` with their outputs `pairs_s{4,5}.json`, `diff_s{4,5}.json`, `full_s{4,5}.json` and `tables.md`. Every number in this report is reproducible from the committed cells with those scripts; nothing was written into the repository except this report and one `results/INDEX.md` row.
