# PRE-REGISTRATION: the queue-register fix (r2), committed BEFORE its cells

D187 (2). Written and committed before any `covex-v6-state-shares-r2` cell is posted. Nothing here
may be edited after a cell runs; a later correction is appended with its date and reason.

## THE MECHANISM, established from the FIT'S OWN CODE, not from a judgement

The release re-check predicts a first token with the committed D162 model and compares it against
the remaining slack. It is fed the queue term as
`queued_uncached_ahead=self._uncached_in_flight` (`coordinator.py:937` for alerts, `:1279` for
recall and assistance).

`_uncached_in_flight` DRAINS AT COMPLETION: its decrement is in the settle path
(`coordinator.py:1774-1775`), so a request stays counted through its whole decode.

THE MODEL'S OWN REGRESSOR IS NOT THAT QUANTITY. `cost_model_gate_d162.py:97-98` builds it as

    qu = _queue_ahead([(r["t_submit"], r["t_submit"] + r["first_token_s"],
                        uncached_tokens, i) for r in base], "uncached")

and `_queue_ahead` (`:60-74`) sums the weight of intervals OPEN AT THE START INSTANT. So the fitted
`queue_uncached_ahead` is the uncached tokens of requests that are BETWEEN SUBMIT AND FIRST TOKEN
when this request is submitted. That is the D179 W quantity, which already exists in this
coordinator as the `WTracker` (submit to first token, drained at `answer_on_first` and at settle).

SO THE RE-CHECK FEEDS THE MODEL A LARGER QUANTITY THAN THE ONE IT WAS FITTED ON, which OVERESTIMATES
the predicted first token and REFUSES WORK THAT WOULD HAVE FITTED. This is a wrong-register bug of
exactly the kind this project has hit repeatedly, and the comment in `share_admission.py` already
states the distinction in the opposite direction: `_uncached_in_flight` is "the right queue input for
the D174 budget charge and the wrong resource for D179 admission".

## WHY THIS IS THE BINDING CONSTRAINT NOW

In the r1 residual diagnosis (`d187_r1_residual_diagnosis.json`), of the 34 remaining recall skips at
seed 4 only NINE were refused by the size term; the other TWENTY-FIVE were refused by the QUEUE term
with a predicted u that already fits the slack (seed 5: 7 size, 5 queue). No prefix fix can reach
those. Three prefix candidates were disqualified or rejected on measurement, including one I
proposed, which would have converted a skip into a late answer on the exact row it targeted.

## THE FIX

1. Track W unconditionally. `WTracker` updates are currently gated on `self._share_admission`, so an
   arm with the re-check but no share admission would see W as 0, which UNDERSTATES the queue and is
   the UNSAFE direction. Tracking is cheap and is read only where needed.
2. Pass `self._w.total()` as `queued_uncached_ahead` at both re-check call sites. Total, not
   per-type, because the fit sums over ALL open intervals regardless of type.

Nothing else changes: no coefficient, no price, no floor, no W_max, no deadline, no target, no bar,
no margin, no workload, no seed, no baseline. The D174 budget charge keeps `_uncached_in_flight`,
which is the quantity it was ruled to use.

## THE PASS CHECK, pre-registered, with its failure condition

PRIMARY, at seeds 4 and 6, the two that fail under r1:
1. `release_infeasible_recall` falls from 34 (s4) and 21 (s6).
2. `robot_pool_on_time` rises from 95 (s4, toward 118) and 92 (s6, toward 107).
3. Check 2 retention rises from 0.7229 (s4) and 0.77 (s6) toward the 0.90 bar.

SEED 5 IS A CONTROL, NOT A TARGET: it already passes at 0.9773 and must NOT REGRESS below 0.90.

THE FAILURE CONDITION: if the queue-refused skips do not fall, the named mechanism is wrong and is
reported as wrong. The fix is not kept for being harmless.

THE UNSAFE DIRECTION, and the specific thing to watch: a SMALLER queue input means a SMALLER
predicted first token, so the re-check will admit MORE. If the model is right, those admissions
arrive on time. If it is optimistic, they arrive LATE. r1 has almost no lateness to spend: robot
late is 2 at s4, 1 at s5, 5 at s6. So the pre-registered harm bound is: ROBOT LATE MUST NOT EXCEED
10 AT ANY SEED. If it does, the fix is trading skips for misses and must be reported as such rather
than as an improvement, since a skip and a late answer score identically (both miss the deadline)
but a late answer also consumed engine time that another request could have used.

POSITIVE CONTROL ON THE CHECK ITSELF: the alert path uses the same corrected quantity, so
`release_infeasible_alert` should also fall. If NOTHING falls anywhere, the change did not reach a
decision and the result is an ABSENT LINK, not a negative.

A CONTROL STATED ON A QUANTITY THE MECHANISM OWNS, learning from the r1 control that was
unfalsifiable because it rested on a shared counter: the predicted first token for a given
(uncached, queue) pair is unchanged, since no coefficient moves. Only the QUEUE INPUT changes.

## PROOFS BEFORE ANY CELL

- Byte-identity on `covex-v6-base` and `covex-v6-state-uo`, each audited against a value committed
  BEFORE the change. `covex-v6-state-uo` matters most: it is check 2's comparator and has no
  re-check, so making W tracking unconditional must not move it.
- THE DRY TRAP, again: on a dry cell `on_first` never fires (no backend), so W drains only at settle
  and the two quantities nearly coincide. A dry cell therefore proves this change HARMLESS and
  proves almost NOTHING about its size. The firing proof is live.
