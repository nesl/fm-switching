# PRE-REGISTRATION: the queue-register fix (r2), committed BEFORE its cells

D187 (2) and (3). Written and pushed before any `covex-v6-state-shares-r2` cell exists, so the pass
check cannot be shaped by the result. Nothing here is edited after a cell runs; a correction is
appended with its date and reason.

## THE QUESTION THE PREVIOUS HANDOFF SAID MUST BE SETTLED FIRST, NOW SETTLED FROM THE FITTING SCRIPT

The release re-check is fed `queued_uncached_ahead=self._uncached_in_flight`
(`coordinator.py:937` and `:1279`). That counter drains at COMPLETION, so it carries the DECODE
TAIL of requests whose prefill has already finished. The handoff recorded, correctly, that this
must NOT be swapped until the D162 fit's own regressor definition was established, because
swapping lowers the predicted first token and therefore admits more work, which is the direction
that flatters the arm under test.

IT IS NOW ESTABLISHED, from the fitting script rather than inferred:

- `experiments/orchestration/live2/cost_model_gate_d162.py:60` `_queue_ahead(items, weight_key)`
  returns, for each interval, "the summed WEIGHT of intervals open at its start instant".
- Line 97 builds the first-token regressor from intervals
  `(r["t_submit"], r["t_submit"] + r["first_token_s"], ...)`.
- Lines 99 to 100 build a SEPARATE regressor, `queue_decode_ahead`, from
  `(t_submit + first_token_s, t_submit + first_token_s + decode_s, ...)`.
- Line 175 fits `first_token_s` on `[1, uncached_tokens, queue_uncached_ahead]`; line 177 fits
  decode on `[1, queue_decode_ahead]`, a different coefficient.

SO THE FIT'S `queue_uncached_ahead` IS THE SUBMIT-TO-FIRST-TOKEN QUANTITY, and the decode-ahead work
is a deliberately separate term that the first-token model never sees. Feeding
`_uncached_in_flight`, which spans submit to COMPLETION, conflates the two regressors the fit went
to the trouble of separating.

THIS IS AN IMPLEMENTATION BUG UNDER D187 (3), not a design change and not a recalibration: the
model is being fed a quantity it was not fitted on. The coefficient stays exactly as committed.
`share_admission.py`'s own docstring already said `_uncached_in_flight` is "the right queue input
for the D174 budget charge and the wrong resource here" and that reasoning was applied to W and
never to the re-check.

## THE FIX

Feed the re-check the D179 W tracker's total, which is by construction submitted-and-not-yet-at-
first-token, the same interval the fit used. W tracking becomes UNCONDITIONAL so the quantity exists
on any arm carrying the re-check, including the `-noadmit` ablation, where an empty W would read as
a zero queue and under-predict: the unsafe direction.

## DIRECTION, STATED PLAINLY BECAUSE IT CUTS AGAINST ME

W <= `_uncached_in_flight` always, so this LOWERS the predicted first token and admits MORE
requests. It therefore moves the arm under test toward passing. The justification is NOT that it
improves the result; it is that the fit's regressor is first-token-based and the code was feeding it
the wrong interval. If the fitting script had shown a completion-based regressor, the correct action
would have been to leave the code alone, and that is what the previous session would have done.

UNDERSTATING THE QUEUE IS THE UNSAFE DIRECTION: it admits work that cannot fit, which surfaces as
LATENESS, not as skips. r1 s4 has only 2 late robot requests and s5 has 1, so there is no lateness
budget. The pass check below therefore treats lateness as a FAILURE condition, not as a cost.

## THE PASS CHECK, pre-registered with its failure conditions

PRIMARY, at seeds 4 to 7, against the committed r1 cells:
1. `release_infeasible_recall` falls further at s4, from 34 toward at most 13 (the pre-registered
   r1 bar, unchanged).
2. `robot_pool_on_time` rises further at s4, from 95 toward 118.
3. Check 2 retention reaches 0.90 at s4. s5 already passes at 0.9773 and MUST NOT REGRESS.

FAILURE CONDITIONS, any of which means the fix is reported as not working rather than kept:
- LATENESS RISES MATERIALLY. Late robot requests above 5 at any seed (r1 has 2 and 1) means the
  queue is now understated and the fix is harmful, whatever it does to the skip count.
- s5 or any passing seed REGRESSES below its bar.
- The skip count falls WITHOUT on-time rising to match, which is the same lateness signature by
  another route.
- Alert attainment or assistance falls below its own bar (checks 1 and 3 pass at both r1 seeds).

POSITIVE CONTROL: on an arm with NO release re-check, the queue input is read by nothing, so
`covex-v6-base` and `covex-v6-state-uo` must be byte-identical, audited against values committed
BEFORE this change.

NEGATIVE CONTROL: the `-noadmit` ablation, which carries the re-check without share admission, must
now receive a NON-ZERO W. If it reads zero, W tracking did not become unconditional and the fix
would be silently under-predicting on that arm.

## WHAT IS NOT CHANGED

No coefficient, intercept, floor, W_max, target, deadline, metric, workload, seed, baseline, bar or
margin. The oversize rule is untouched per D186. The cold-pricing fix of 79eedc6d stays as it is.
