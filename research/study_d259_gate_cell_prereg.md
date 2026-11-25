# THE D249 `-q` GATE CELL AND ITS PASS RULE, AS PRE-REGISTERED BEFORE THE CELL RAN

## *** AMENDMENT BY USER RULING, TIMESTAMPED 2026-11-25T22:51:05Z (local 14:51:05 PST), AND WRITTEN BEFORE ANY RESULT OF THE CELL HAS BEEN SEEN. ***

**At the moment of this commit the cell `covex-v6-fair-final-q 16 4 _L3_epg_rq30` is RUNNING and NO FIGURE
FROM IT HAS REACHED THIS SESSION. That is the whole point of the timestamp: an amendment to a pass rule is
legitimate only before the result, and this one is.**

*** THE ROBOT CLOUD ON-TIME CRITERION IS REPLACED WITH THE D264 FORM. PASS REQUIRES BOTH: ***
```
1. ROBOT CORRECT-BY-DEADLINE count beats SAME-CODE RUNG 3 by MORE THAN 2
   comparator: the committed cell NAMED IN THE PREREG, the un-suffixed
   covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30 , cbd 83 of 132
   SO PASS NEEDS -q cbd OF AT LEAST 86.
2. DASHCAM ON-TIME not worse beyond its same-code observation
   comparator dashcam 8,377 ; the same-code spread against _rep2 (8,323) is 54 counts
   SO CONDITION 2 FAILS ONLY IF DASHCAM IS WORSE BY MORE THAN 54.
```
**REPORTED BESIDE IT, ALWAYS: robot cloud on-time, cloud-correct, device-correct, and cloud accuracy on
served.**
*** AND A PROPERTY OF THE NEW BAR WORTH SEEING: THE THRESHOLD OF "MORE THAN 2" IS **EXACTLY** THE OBSERVED
cbd SPREAD BETWEEN THE TWO REPLICATES, 83 AND 85. SO THE BAR SITS PRECISELY ON THE REPLICATE NOISE, WHICH IS
WHAT D264 INTENDS, AND A SCORE OF 85 WOULD TIE `_rep2` AND STILL FAIL. ***

### THE REACHABILITY CHECK STANDS, AND IT NEEDS TWO FIELDS, NOT ONE
**The ruling says ZERO TOUCH CHOSEN MAKES THE CELL AN ABSENT LINK, NOT A RESULT. That is `state_chosen_TOUCH`
in the state planner, which was 0 of 61,678 at the old bar and 1,175 at the recalibrated one.**
*** BUT THAT FIELD ALONE CANNOT SHOW THE D249 SWITCH DID ANYTHING, BECAUSE PLAIN RUNG 3 ALSO CHOOSES TOUCH,
2,676 TIMES IN `_rep2` AND 2,954 IN THE DRY PROBE. THE `-q` ARM TOUCHES **LESS**, NOT MORE, SINCE THE
QUEUE-AWARE TERM MAKES A TOUCH DEARER EVEN AT A LOWER BAR. SO THE DIRECTION OF THE TOUCH DELTA IS NOT A PASS
CRITERION AND MUST NOT BE READ AS ONE. ***
**The field that shows the SWITCH acted is `d249_queued_ahead_reads`, which must be NON-ZERO in the `-q`
cell and ABSENT OR ZERO on rung 3, with `d249_pwc_queue_priced` and `d249_pwc_queue_capped` beside it. The
two checks answer different questions: TOUCH CHOSEN asks whether the arm did anything, and the d249 read
count asks whether the switch is what made it do so.**

### WHAT THE AMENDMENT DOES NOT CHANGE
**Check 7 on the comparator before the comparison is read; the comparator's `source_agreement` being ABSENT
rather than OK, stated as the provenance weakness it is; `_rep2` reported beside it with any verdict
difference between the two comparators reported AS A FINDING rather than resolved by picking; an unfloored
dashcam delta reported as UNFLOORED; and A FAIL IS REPORTED AS A FAIL, with the margin NOT re-derived, the
quantile NOT moved and the bins NOT changed.**


*** COMMITTED NOW, MINUTES BEFORE THE CELL STARTS, BECAUSE UNTIL THIS COMMIT THE PASS RULE EXISTED ONLY IN
A SCRATCH DIRECTORY. A PRE-REGISTRATION THAT LIVES ONE CLEANUP FROM DELETION IS NOT A PRE-REGISTRATION. The
text below is the file written before any gate cell existed, sha256 prefix `84b34f170f347aa5`, reproduced
verbatim and unaltered. ***

## *** ONE TENSION THE USER SHOULD SETTLE, AND I AM NOT SETTLING IT MYSELF ***

**This rule is on ROBOT CLOUD ON-TIME. The D250 pass rule was later REPLACED, at `0aba48bd`, to be on
ROBOT CORRECT-BY-DEADLINE instead, on the grounds that on-time alone decides nothing.**
**They are different experiments: D250 compares rung 3 against baselines under memory pressure, and this
gate compares the `-q` arm against rung 3 at 1x. So there is no contradiction in them differing.**
*** BUT TODAY'S OWN EVIDENCE IS THAT ON-TIME IS THE WEAKER METRIC: `simplestream` delivered 132 of 132
ROBOT QUESTIONS ON TIME AND WAS RIGHT 16.7 PERCENT OF THE TIME, SCORING BELOW THE DEVICE FLOOR. SO A `-q`
GATE DECIDED ON ON-TIME COULD PASS AN ARM THAT ANSWERS WORSE. ***
**I am applying the rule AS PRE-REGISTERED and reporting correct-by-deadline and cloud accuracy on served
beside it, per D257 (3), so either reading is available afterwards. CHANGING A PRE-REGISTERED PASS RULE IS
THE USER'S CALL AND IT MUST BE MADE BEFORE THE RESULT IS SEEN, WHICH IS NOW.**

## AND THE COMPARATOR IS NOW STRONGER THAN THE PREREG COULD ASSUME

**The prereg demanded "a SAME-CODE rung-3 1x s4 cell", written when the recalibrated margin was still going
to be global and would therefore have moved rung 3. Under D261 the margin is scoped to the `-q` arm ALONE,
and the D265 proof returned 0 positional and 0 setwise for rung 3 at the full posted cell.** *** SO THE
COMMITTED `covex-v6-fair-final 16 4 _L3_epg_rq30_preD249` CELL **IS** THE SAME-CODE COMPARATOR, BY PROOF
RATHER THAN BY ASSUMPTION. The prereg's requirement is met by the committed cell. ***
**The prereg's own provenance caveat still stands and is not cancelled by that: the comparator cell carries
NO `source_agreement` key, so its code-agreement verdict is ABSENT rather than OK, and check 7 on it is
mandatory before the comparison is read.**

## THE PORT RULE, WHICH IS THE CHECK THAT DECIDES WHETHER THE CELL MEANS ANYTHING

*** THE `-q` ARM EXISTS TO MAKE TOUCH DECISIONS. AT THE OLD BAR, TOUCH WAS UNREACHABLE AT EVERY ONE OF
61,678 DECISIONS; AT THE METHOD A BAR IT WAS CHOSEN 1,175 TIMES IN THE DRY PROBE. SO THE GATE CELL MUST
SHOW ITS CHARACTERISTIC DECISION OCCURRING AT LEAST ONCE. IF TOUCH IS ZERO IN THE LIVE CELL, THE ARM DID
NOTHING AND THE COMPARISON IS AN ABSENT LINK, NOT A RESULT, WHATEVER THE PASS RULE SAYS. *** The dry figure
of 1,175 is a CONSTRUCTED expectation from a dry probe and not a prediction for a live cell; the test is
non-zero, not a target.

---
---

# THE PRE-REGISTERED FILE FOLLOWS, VERBATIM

# D259 PRE-REGISTRATION OF THE LIVE GATE CELL AND ITS PASS RULE
Written BEFORE the cell is run. THE CELL IS NOT RUN BY THIS AGENT. The parent and the accelerator
box run it; this document and the light proofs are what is handed over.

## WHAT IS RUN
One cell, `covex-v6-fair-final-q`, 1x, seed 4, n16, 1200 s, 40:40:20, lh_req, ss2, epg, per-frame,
rq30, with the `_dev` suffix on the cell directory, on a tree carrying EXACTLY TWO changes against
the committed rung-3 tree:
1. the D256 (a) queue cap in `arms_v6state.py::_p_warm_cold` (mirrors `cf_objective.py:838-839`);
2. `cf_margin.MARGIN_CF = 0.0828915`, so `cf_objective.attainment_margin` returns
   `MARGIN_CF_ON_TIME = 0.331566`, the D259 Method A value.
Plus, as part of (2) and not as a third change, the import-time value guard in
`cf_protect_defer.py` RE-PINNED from 0.6582 to 0.331566. It remains a guard.
ONE CELL PER PROCESS. The cell must not share a process with any other cell, because a dry or live
cell is scored under a planner wall-clock budget.

## THE COMPARATOR, NAMED BEFORE THE RUN
`covex-v6-fair-final` (rung 3), 1x, seed 4, SAME CODE: run on the SAME tree as the `_dev` cell, not
read from the committed cell. The committed rung-3 1x s4 figures (robot cloud on-time 126 of 132,
single-shot 0.9832, dashcam on-time 8,377, alert attainment 0.619234, as quoted in
`research/EXPERIMENTS.md` StudyD233-STATEOFF) are CONTEXT for sanity only and are NOT the bar.
CHECK 7 IS MANDATORY AND APPLIES TO THE COMPARATOR: before the comparison is read, the same-code
rung-3 arm's own numbers are cross-checked against those committed values. A same-code rung-3 cell
that lands far from its committed self is a BROKEN CONTROL and the comparison is not read at all.
The committed rung-3 1x s4 comparator cell carries NO `source_agreement` key (StudyD233-STATEOFF),
and that caveat travels with every use of it as context.

## THE PASS RULE, as D259 states it
PASS requires BOTH:
1. **Robot cloud on-time NOT BELOW the same-code rung-3 1x s4 count by more than 2 opportunities.**
   An absolute count out of the robot denominator, never a fraction: D234 (3) measured that the
   count transfers and the fraction does not.
2. **Dashcam not worse beyond the same-code observation**, i.e. the dashcam on-time count is not
   below the same-code rung-3 cell's by more than the same-code difference already observed
   between two runs of the same arm. Where no same-code dashcam floor exists for this condition,
   the dashcam delta is reported as UNFLOORED and may not be called a difference.

## REPORTED BESIDE IT, MANDATORY
**PER USER RULING D257 (3), ROBOT CLOUD ON-TIME MAY NEVER BE QUOTED ALONE.** Every quotation of it,
in the gate report and anywhere else, carries in the same sentence:
- **robot CORRECT-BY-DEADLINE** (count and denominator), and
- **CLOUD ACCURACY ON SERVED** (correct of served, with the denominator).
Also reported: `state_chosen_TOUCH`, `state_touch_emitted`, the ENACTED touch count
(`submitted_touch` / `completed_touch` in the live harness), `state_chosen_HOLD_BACK` and
`state_hold_back_enacted`, `state_chosen_WARM`, RELOAD and SLICE counts, `state_deviations`,
`d249_pwc_queue_capped` and `d249_pwc_queue_max_milli`, and the cell's `source_agreement` verdict.

## PRE-DECLARED, SO IT IS NOT DECIDED AFTER THE FACT
- A FAIL is reported as a FAIL. The margin is NOT re-derived, the quantile is NOT moved, the bins
  are NOT re-cut and Method B is NOT substituted, under any outcome. D259's pre-commitment binds
  the margin to Method A's value whatever the gate then shows.
- If the gate passes, the margin change is still a RECALIBRATION OF AN INSTRUMENT and the value
  guards listed in the dev record as owed (`cf_pd_tests.py:85-86`,
  `tests/test_cf_objective_d191.py:144-145`, `tests/test_cf_objective_d177.py:145-149` and
  `:210`, `d249_queue_unit_proofs.py:216-217`, plus the narrative 0.6582 strings in
  `v5/cf_planner.py:101,409`, `arms_v6cf_device.py:21`, `arms.py:774`,
  `d190_rung4_r3_proofs.py:168`) must be re-pinned to 0.331566 in the same change, or the suite
  fails by design and the failure means nothing.
- KV capacity is NOT enforced in this harness (`kv_capacity_enforced` False in `test_hybrid.dry`),
  so NO kv0.5r claim may be made from this cell.
