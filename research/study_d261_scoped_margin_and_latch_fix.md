# D261: THE SCOPED MARGIN AND THE robo001 LATCH FIX. ALL PROOFS PASS, AND TWO SELF-CAUGHT DEFECTS ARE THE MOST VALUABLE PART.

**CPU only, dry harness, own scratch tree. NOTHING committed to `experiments/`, nothing pushed, no live
cell. The accelerator box is held. No kv0.5r claim is made from any of it: KV is not enforced in this
harness.**

## D261's THREE PROOFS, ALL HITTING THE MANDATED NUMBERS

| proof | required | measured | verdict |
|---|---|---|---|
| rung 3 byte-identical | 14,539 rows, `5a03c2807da3681a`, 0 / 0 | 14,539, `5a03c2807da3681a`, **0 / 0** | PASS |
| `-q` reachability | 61,678 decisions; 1,177 clear; TOUCH 1,175 / 1,175 | 61,678; **1,177**; **1,175 / 1,175**; Z max 0.555587965 | PASS |
| *** unit suite *** | *** 20 of 20, not 18 of 20 *** | *** 20 of 20, 0 failed. NO LEAK *** | PASS |

**The suite was the sharp check and it passed clean: both tests that fail by construction under a global
re-pin pass again, and `cf_pd_tests.py` runs 36 of 36, covering the `:85-86` pin to 0.6582. The twelve sites
pinned to the committed value are untouched, and the one-declaration audit still reports one declaration, 0
elsewhere, 0 conflicts.**

| arm | `margin_cf_override` | bar in force |
|---|---|---|
| `covex-v6-fair-final` (rung 3) | None | **0.65824, unchanged** |
| **`covex-v6-fair-final-q`** | 0.0828915 | **0.331566** |
| `covex-v6-state-final` (rung 2) | None | 0.65824 |
| module constant | unchanged | 0.16456 / 0.65824 |

**THE NAMED READ, as a census rather than a construction: `bars_actually_used_by_decisions = {0.331566:
61678}`, read per decision off `Decision.margin`, with the module constant still at 0.65824 printed beside
it. All 61,678 decisions used the scoped bar; TOUCH went 0 to 1,175.** The consuming read is
`cf_planner.py:805`, `m_eff = effective_margin(m.value, w)`.

## *** SELF-CAUGHT DEFECT 1: THE PROBE WOULD HAVE BEEN WRONG BY EXACTLY A FACTOR OF TWO ***

**The existing reachability probe sets `BAR = attainment_margin(cf_margin.MARGIN_CF)` ONCE and recovers
`w_d = margin_effective / BAR`. Under scoping that denominator is 0.65824 while the real `-q` bar is
0.331566, a ratio of 1.9853.** *** SO EVERY Z WOULD HAVE BEEN WRONG BY A FACTOR OF TWO, AND IT IS THIS
PROJECT'S OWN NAMED FAILURE MODE: A COMPARATOR PRICED AT ONE BAR AND CHARGED ANOTHER. *** The probe was
rewritten to read the bar off each decision and report the SET of bars seen, which is why the census above
exists at all.

## *** SELF-CAUGHT DEFECT 2: A UNIT PROOF WRITTEN TO ASSERT THE WRONG THING, CAUGHT BY STEP 2b ***

**The first build of the latch module had a clause saying any later reading SETTLED the mark, so a second
zero made it permanent and no rejection could clear it. THE DIAGNOSED CASE IS TWO CONSECUTIVE ZEROS
(t=743.94 pt=6,041 and t=789.94 pt=7,031), so that clause defeated the exact case the fix exists to fix,
and it smuggled back the option that had been rejected as unexercised.**
*** IT PASSED 15 OF 15 UNIT PROOFS, BECAUSE THE UNIT PROOF HAD BEEN WRITTEN TO ASSERT "CONFIRMED". THE
WHOLE-CELL POSITIVE CONTROL CAUGHT IT: `d262_cold_marked` 1 AND `d262_cold_unlatched` **0**, WITH THE
DECISION LOG BYTE-IDENTICAL. THAT IS AN ABSENT LINK, NOT A NEGATIVE. *** The clause is removed and the unit
check inverted.

## THE LATCH FIX ITSELF

**Option chosen: a decline is NOT proof of cold. The alternative, re-evaluate on the next telemetry
reading, is UNEXERCISED in the diagnosed condition and therefore a stopping condition rather than a fix:
`robo001` received NO REQUEST OF ANY KIND after t=789.94 for the remaining 276 s, so there is no next
reading at any of the 12 instants, and the decline is precisely what prevents the reading.**
**The rule: a corrector demotion from a telemetry zero records the tier held before the FIRST zero; a
further zero refreshes and keeps it; a NON-ZERO reading drops the mark; and a REJECT on a marked session
clears it and restores the recorded tier. `REJECT` only, never `DEVICE`.**

### IDENTITY PROOF, AND THE VACUITY OF EACH HALF ADDRESSED

| condition | result |
|---|---|
| the posted `-q` cell, base vs fix | 11,386 rows both, `b7bb6e018b6e1d27` both, **0 / 0**, every counter equal |
| **a CONSTRUCTED no-zero condition** | 11,082 rows both, `d339de04acda2fb8` both, **0 / 0** |
| rung 3 on the fixed tree | 14,539, `5a03c2807da3681a`, 0 / 0, switch reads **false** |

*** THE POSTED CELL HAS NO TELEMETRY AT ALL. It is DRY: `usage={}`, so the corrector returns "no usage
reported", and it shows 550 `belief_corrections` with `belief_corrections_changed` ABSENT, so zero. THE
MARKING SITE IS UNEXERCISED THERE, SO THAT PROOF ALONE WOULD BE VACUOUS AS TO HALF THE MECHANISM. *** It is
not vacuous as to the CLEARING site: the cell has 29 `recall_REJECT`, so the clear path executes 29 times
and correctly returns nothing each time because no mark exists.
**So a no-zero condition was constructed explicitly: 202 live readings, 0 zeros, and the corrector CHANGES
7 beliefs. The marking site is now reached, no mark can be written because no reading is zero, and the logs
are byte-identical. THAT is the non-vacuous identity proof.**

### POSITIVE CONTROL: THE LATCH CLEARS, AND THE PRICE IS REPORTED

**Constructed to match the diagnosis: same device and session, belief gpu before the zero, zero over the
session's own built prefix, TWO consecutive zeros, est_tokens 26,491 against the diagnosis's 25,576, robot
deadline exactly 3.0 s, and the rejection at `hybrid_arm.py:437` via the readiness read at `:412`.**
**`recall_REJECT` 10 to 6; `recall_CLOUD` 479 to 483; `d262_cold_unlatched` 6; 3,376 positional and 492
setwise differing decisions. Four instants flip from `decline` to `release_recall`.**
**Internal consistency checked here: 10 minus 6 equals 483 minus 479 equals 4, so the four recovered
questions and the four extra releases are the same four. Six clears produced four releases, which AGREES
with the reported alternation rather than with a clean fix.**
*** THE PRICE, REPORTED RATHER THAN HIDDEN: the condition drops the prefix PERMANENTLY, so each probe the
fix lets through returns another zero, re-demotes, and the next decline clears again. The session recovers
4 of its 10 lost questions and the latch never re-forms. AND NO VALUE CLAIM IS MADE, BECAUSE THE DIAGNOSIS
RECORDS robo001's CLOUD ANSWERS AS 0 OF 4 CORRECT WHEN SERVED. The fix recovers questions whose answers
were wrong anyway; whether it is worth anything is untested. ***
**An assumption was re-derived rather than restated and was wrong: `defer_s` was guessed at 2.0 and read
off the arm as 0.5, and at 0.5 both of the diagnosis's cold figures reject, which CONFIRMS the diagnosis's
"both over the deadline". `recall_ttft_s(467, "COLD") = 0.1038 s` is recorded and NOT used.**
**Unit proofs 16 of 16, including the diagnosed two-zero case and the non-zero supersede.**

## LIGHT PROOFS, WITH THE CAP PLUS THE SCOPED MARGIN PLUS THE LATCH FIX

**All pass, including the positive control (`llf` 14,075 / `961be8fe4942d86b`, 0 / 0, matching committed)
AND its non-vacuity (`llf` against rung 3 differs at ROW INDEX 0). The 247.5x unit guard holds: 4 of 4
`CC.predict(` sites still carry literal `0, 0`, byte-identical argument lists.**
**One consistency difference, under the 2x rule and explained: `d249_pwc_queue_capped` 5,852 against the
committed 5,740, ratio 1.0195, because the scoped margin changes the `-q` trajectory so a different set of
decisions prices a queue.**

## OWED, AND ONE NAMING PROBLEM TO SETTLE FIRST

1. *** THE BUILD CALLS THE LATCH FIX "D262" AND NAMES ITS MODULE `d262_cold_unlatch.py`, BUT NO USER RULING
   D262 EXISTS. The latch fix was ordered inside the D261 message. The committed log ends at D261. A D-number
   must not be minted by a build, so either the user issues D262 to cover it or the module is renamed before
   anything is committed. NOT LOGGED AS A RULING. ***
2. **No live gate cell, as instructed. Whether TOUCH at 1,175 survives on a live cell is untested.**
3. **`StudyD249-QPLANNER` needs D261 and the latch fix added, with both new modules in its files column, and
   a `results/INDEX.md` row.**
4. **Pre-existing and NOT caused by either change, verified identically on the base tree: 4 errors in
   `test_live2_coord.py`, 6 in `test_live2_fix.py`, and rung 4 unbuildable for a missing cost-model gate
   file.**
5. **`cf_protect_defer.MARGIN_CF_ON_TIME` left at 0.65824, verified off the `-q` path: its only consumer is
   `PD.bar`, called only from `cf_request_defer.py:358`, imported only by the rung-4 arms, and the `-q` cell
   records no `pd_` or `rd_` stats at all.**
