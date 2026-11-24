# StudyD222-PASS1 ADDENDUM — `covex-v6-final-nqd`, the reshaped rung 4 (D232 (2))

**THE ONE LINE.** `covex-v6-final-nqd` is `covex-v6-fair-final` (rung 3) plus protect-and-defer,
DEVICE_ANSWERS (D218's rule in D177 units, `MARGIN_CF` 0.6582, no gain weighting) and the
deficit-fed state planner, with the **question-deferral leg REMOVED from the arm's MRO** rather
than switched off, so `rd_question_defers` is zero by construction; its bars are
`covex-v6-fair-final` kv0.5r s4 and 1x s4 as written out verbatim in section 3 below.

Base sha for every proof and every cell named here: `1a092abd9009df90e4e0ce88b9af640369dd62be`
(origin/main, resolved once). A digest is comparable only within one base sha.

---

## 1. EVERY ITEM, EACH **BUILT** OR **EXPLICITLY DEFERRED**

The standing rule, from the failure where pass 1 was pre-registered, all three proofs passed, and
the posted cell lacked DEVICE_ANSWERS because the proofs ran on a tree that was not the pushed
tree. A reader must not have to infer an item's state from the absence of a mention.

| item | state | where / why |
|---|---|---|
| **the arm `covex-v6-final-nqd`** | **BUILT** | `experiments/orchestration/live2/arms_v6cf_device.py`, class `V6FinalNQD`, factory `make_nqd` |
| **question deferral REMOVED** | **BUILT (as a removal)** | `_Rung4Mixin` is **absent from `V6FinalNQD.__mro__`**. No `decide` override, no `rd_*` instance state, no `RD.SWITCH_ATTR` written on any object in the decide chain. See section 2 |
| **protect-and-defer** | **BUILT** | `arms_v6cf._ProtectDeferMixin` over `arms_final_ladder.V6FairFinal`, unchanged module, switch `live2_cf_protect_defer` set on every `_pd_targets()` object and read back |
| **DEVICE_ANSWERS** (D218, D177 units, `MARGIN_CF_ON_TIME` 0.6582, **no gain weighting** — D228 (2) withdrew it) | **BUILT** | the rule in `cf_protect_defer.decide`, the enactment and counters in `arms_v6cf._ProtectDeferMixin`, the switch `live2_cf_device_answers` turned on only by `arms_v6cf_device` |
| **deficit-fed state planner (D206 (3))** | **BUILT** | `planner_deficit_weights.wire_planner`, **one copy**, inherited through `arms_final_ladder._PlannerFeedMixin`; `-nqd`'s builder reads the source back and raises unless it is a live `PlannerDeficitWeights` on the **same feed object** as the legs |
| **D162 pricing, reading (B), for protect-and-defer** | **BUILT, AND IT WAS ALREADY ON ORIGIN** | `cf_protect_defer` imports `d162_price`, whose `PER_QUEUE_S` is drift-checked against `per_queue_token` (per uncached token). Protect-and-defer never carried the `per_overlap`-per-REQUEST form that pass-1 item 1 replaced; that form was the question-deferral gate's. **Nothing was re-applied here.** See section 4 |
| **safety 1.767170 as `safety * engine_s + LINK_RTT_S`** | **NOT IN THIS ARM, AND NOT APPLIED** | its only reader in the tree is `cf_request_defer.py`, the removed leg. Protect-and-defer's latest safe start is `cf_cost.latest_safe_start` at `KAPPA = 1.5775406165458339` (`cf_margin.safety_factor`), network **inside** the factor. Re-pointing protect-and-defer at the refit would change the gate that decides when DEVICE_ANSWERS becomes reachable, which is a methodological change nobody has ruled. **EXPLICITLY DEFERRED to a user ruling.** See section 4 |
| **pass-1 items 1, 2, 4, 5a, 5b** | **EXPLICITLY ABSENT FROM THIS ARM, as a consequence of the removal** | all five are implemented inside the question-deferral leg (`arms_v6cfr3._rd_u` / `_rd_one` / `_rd_record` / `decide`, and `cf_request_defer`). With the leg out of the MRO none of them has a reader in `-nqd`: no `rd_decisions.jsonl.gz` is written (`coordinator.write_rd_decisions` returns `None` on an arm with no `rd_decisions`), and `decision.predicted.*` keeps the committed empty record (`last_predictions` is never filled). They remain BUILT on origin and live in `covex-v6-final`. See section 4 |
| **the `-da` arm `covex-v6-final-da`** | **BUILT, NOT A BAR CELL HERE** | same module; kept so the D218 dry proofs stay reproducible |
| **Step 4 controls on the DEVICE_ANSWERS branch** | **BUILT as named arms, NOT RUN as cells** | `covex-v6-final-nqd-harm0` and `covex-v6-final-nqd-margin-huge`, one cell each when wanted |
| **the off-switch bar `covex-v6-final-nqd-off`** | **BUILT and RUN as proof (b)** | protect-and-defer and DEVICE_ANSWERS both off; must equal `covex-v6-fair-final` byte-identically |
| **`metrics_health` honesty** | **BUILT (unchanged from origin)** | E1 is **not** fixed and this build does **not** wait for it (D232 (2)). `metrics_health` must read `never_scraped_by_decisions`; **`scraped_ok` may not be claimed.** A previous cell claimed it with 2 scrapes both after the measurement window while no decision ever saw the gauge: the field answered "did the scrape work?" when the question is "did a decision see it?" |
| **protect-and-defer binds on the BELIEF meanwhile** | **BUILT (unchanged from origin)** | `_pd_free_kv` takes `max(engine-metric occupancy, belief occupancy)`, the pessimistic one, and records `pd_kv_bound_by_belief` / `pd_kv_bound_by_engine_metric` every decision |
| **the `coordinator.py` `-da` held patch** | **EXPLICITLY NOT APPLIED** | it is a **reverse** patch against this base: its hunks only DELETE, and applying it would revert Hit 7 (`requested_window_s`) and D213 item 3 (`_belief_prefix_record`). Its stated "+2 lines" are not in it. No coordinator change is needed: `ra.decision == "DEVICE"` is already read (origin `coordinator.py:959`) and `_arm_stats` already merges every `stats` mapping in the delegation chain, so the new counters reach `coordinator_result.json -> arm_stats` with no edit. See section 4 |
| **folding `-nqd` into `covex-v6-final`** | **EXPLICITLY DEFERRED** | D221 governs the fold; two cells differing by arm cannot be confused by when a commit landed |
| **0.25x cells, any arm** | **EXPLICITLY EXCLUDED** | D223 (1) |
| **any `experiments/` push** | **EXPLICITLY DEFERRED to the user** | the user clears the window with the H100; no push in a cell's start-up window, and the user posts cells |

---

## 2. HOW (d) IS BY CONSTRUCTION — a claim about code, not a count

`covex-v6-final` is `type("V6Final", (_Rung4Mixin, _ProtectDeferMixin, V6FairFinal), ...)`.
`covex-v6-final-nqd` is `type("V6FinalNQD", (_ProtectDeferMixin, V6FairFinal), ...)` — the **same
MRO with `_Rung4Mixin` deleted from it**. Four consequences, each checkable:

1. `arms_v6cfr3.py:412`, `self.stats["rd_question_defers"] += 1`, is the **only** write to that
   counter anywhere outside `held/` in the tree (`git grep` at the base sha: one write, four
   reads, all in reporting scripts). It sits inside `_Rung4Mixin.decide`, which is not in the
   MRO, so there is no call path to it.
2. `_Rung4Mixin.decide` is the only `decide` that reads `RD.arm_enables`. With the mixin gone,
   the leg cannot be re-enabled by setting a flag: there is no reader. `make_nqd` also never
   writes `RD.SWITCH_ATTR` on any object, so the switch is **absent**, not false.
3. No `rd_decisions` / `rd_nets` / `rd_bars` / `rd_trace_*` attribute is created, so
   `rd_report()` does not exist on the arm and `coordinator.write_rd_decisions` returns `None`.
4. The builder **asserts all four** at construction and raises `QuestionDeferralStillPresent`
   otherwise, so an arm that silently regained the leg fails in construction rather than in a
   null three minutes into a cell.

Proof (d) therefore reports the MRO, the four assertions, and — beside them, not instead of them
— the observed count of `rd_*` keys in the arm's stats after a full dry cell, which must be the
empty set.

---

## 3. THE BARS, VERBATIM

### kv0.5r s4 — `covex-v6-final-nqd_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30`
against `covex-v6-fair-final` kv0.5r s4:

* robot on-time **AND** robot correct-by-deadline **above** rung 3's
* alert attainment **>=** rung 3's
* single-shot **>= 90 %** within 2 s

**Register, pre-registered rather than discovered afterwards:** the named comparator
`covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` is **`ScoringRefused`** under the
D226 guard (1 delivered cloud answer, `r10175`, absent from a 10,174-row request log), so its
robot, alert and single-shot numbers **do not yet exist**. This cell runs regardless; the
comparison is arithmetic afterwards and the kv0.5r verdict is final only once the Orin's rescore
lands. Rung 3 kv0.5r is complete at s5, s6 and s7, so the comparator family exists even though
this cell's specific comparator does not.

**Denominator caution, applied to every robot count:** the robot pool size moves between seeds —
132 at 1x s4, and 127 / 121 / 105 at kv0.5r s5 / s6 / s7. Every robot count reported for this
study carries its denominator beside it, and the 0.5x bar is against **s4 specifically**.

### 1x s4 — `covex-v6-final-nqd_n16_s4_1200s_h27_3t_L3_epg_rq30`
against `covex-v6-fair-final` 1x s4:

* alerts **>=** rung 3's
* robot retention **>= 0.90**
* single-shot **>= 90 %**

**0.619 governs** (D232 (1), the same-code rule): the comparator is same-code
`covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30` at mean per-episode alert attainment
**0.619234** (712 episodes, 11,764 alert instants, 19-instant per-episode denominator), **not**
the frozen pre-registration's literal **0.441233**, which belongs to `covex-v6-fair-c5attr`'s s4
cell — a superseded cell of the same name and the same definition, 1.40x apart. Committed
comparator values this verdict will be read against, quoted now:

| quantity | `covex-v6-fair-final` 1x s4 | source |
|---|---|---|
| mean per-episode alert attainment | 0.619234 | `results/orchestration/live2/d222_pass1/d222_1x_s4_verdict.json` |
| robot correct-by-deadline | 0.628788 (n = 132) | that cell's `cell.json` `score.score.robot_headline` |
| robot cloud answers standing | 126 of 132 | same, `robot_value` |
| single-shot on-time within 2 s | 0.983193 (351 of 357) | same, `assistive_value` |
| rung-4 pass 1's attainment, for reference | 0.609181 — **FAIL** on the named bar by -0.010053 | `d222_1x_s4_verdict.json` |

---

## 4. FOUR PREMISE CORRECTIONS, RECORDED BEFORE ANY CELL RATHER THAN AFTER A RESULT

1. **The safety refit is not protect-and-defer's.** 1.767170 is read only by `cf_request_defer`.
   Not applied to protect-and-defer; deferred to a ruling. Protect-and-defer keeps KAPPA
   1.5775406165458339, which is the same gate the committed D218 dry proofs ran against, so
   `-nqd` is consistent with them.
2. **D162 reading (B) was already protect-and-defer's.** Via `d162_price`, drift-checked against
   `per_queue_token`. Nothing re-applied. Protect-and-defer's own service prediction is
   `cf_cost.predict(cf.model, ...)`, and `cf.model_d162` is **deliberately not attached** to
   `-nqd`: with the deferral leg gone it would have no reader, and a quantity written and never
   read is ABSENT (CLAUDE.md Step 2).
3. **All five pass-1 items live in the removed leg.** `-nqd` therefore carries none of them. This
   is a consequence of the ruled removal, stated here so no reader infers pass 1 is in the cell.
4. **The `-da` coordinator patch is a reverse patch and is not applied.** Forcing it would
   silently revert two landed changes, which is precisely what its own README warns against.

## 5. NULL HANDLING, PRE-COMMITTED

If proof (c) finds **zero** differing decisions, that is an **ABSENT LINK** and is reported as
such, never as a negative (CLAUDE.md Step 2b). If a bar is missed, Rule 2's class is stated
explicitly — and only *fired and did not help* is evidence about the policy.
