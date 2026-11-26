# `-q2` STAGE 1: THE TWO GATES, PRE-REGISTERED BEFORE ANY CELL EXISTS (2026-11-26T00:32:06Z). No cell has run; nothing is built yet.

**User ruling. The 1x `-q` failure (`3ce9ba27`) stands and so does `-q`'s halved-memory pass.** `-q2` is a NEW labelled arm `covex-v6-fair-final-q2` = `-q` with in-flight rows EXCLUDED from the HOLD_BACK harm. Justification (user): under the D162 model a rebuild submitted now queues behind in-flight work, so it cannot delay it; only later arrivals are harmed. Separate switch, default OFF.

## The two gates, single seed s4, D275 form
**(a) 1x, `covex-v6-fair-final-q2 16 4 _L3_epg_rq30`** against rung 3's committed comparator (the un-suffixed cell: cbd 83, dashcam 8,377). PASS needs cbd >= 86 AND dashcam not worse beyond 54. `-q` beside it: cbd 79, dashcam 8,719.
**(b) halved memory, `covex-v6-fair-final-q2 16 4 _kv0.5r_h0.5_L3_epg_rq30`** against rung 3's D250 cell (cbd 72, dashcam 6,112, worst 0.4544). PASS needs cbd >= 75 AND dashcam not worse than 6,112 beyond 154. `-q` beside it: cbd 77, dashcam 6,759.
Report beside each: robot cloud on-time, cloud-correct, device-correct, cloud accuracy on served. Check 7 on each comparator, with `source_agreement` read from `header.json` (not `cell.json`).

## Reachability, first, as before
`state_chosen_TOUCH` > 0, else the cell is an ABSENT LINK and the pass rule is not scored. `HOLD_BACK` count REPORTED for `-q2`, `-q` and rung 3. A named `q2_` counter (recorded in the build record before any cell) must be non-zero in `-q2` and absent on `-q` and rung 3, so the NEW switch is shown to have acted, separately from the `-q` switch.

## A prediction, recorded now so it cannot be fitted afterwards (NOT a pass criterion)
The dry replay of this exact change (scratch monkeypatch, 40:40:20 posted dry cell) gave TOUCH 7,353 and HOLD_BACK 1, against `-q` 1,175 and 74 and rung 3 2,954. **Live `-q` HOLD_BACK was 87 against rung 3's 2. So the expected direction is HOLD_BACK down sharply and TOUCH UP, possibly OVER rung 3 because the halved margin raises rung 3's own touches from 2,956 to 9,484 on its states. If `-q2` over-touches and fails, the margin is the next suspect, and the margin is NOT re-derived (D259 stands).**

## Unchanged
A fail is a fail; the margin, quantile and bins are untouched; an unfloored dashcam delta is reported as unfloored; robot on-time is never quoted alone. Proofs required before any cell: every other arm byte-identical to main; `-q2` with the switch off identical to `-q`; Step 2b decision diff; negative control; push only through a D265-style window.

## AMENDMENT 2026-11-26T01:10:06Z, BEFORE ANY `-q2` CELL EXISTS: build record and the named counters
Built and proved on CPU (dry, constructed). **Switch `live2_q2_inflight_exclusion`** (instance-level, default OFF; a truthy class attribute raises). **READ SITE:** `arms_v6state.py` `_queued_behind` branch at `:518` (`if not include_inflight and self._q2_on()`), called with include_inflight=False from the HOLD_BACK/WARM call at `:640`; the TOUCH harm call is unchanged and still includes the in-flight rows.
**Port-rule counters (arm stats, ABSENT on `-q` and rung 3): `q2_hbwarm_evals` and `q2_inflight_excluded_evals`; the latter must be non-zero in `-q2`.** Dry values: 114 and 112.
Proofs: positive control rung 3 14,539 / 5a03c2807da3681a and `-q` 12,555 / 41724e38cfaa2eb4; 13 Tier A arms byte-identical at 1,200 s (0 positional, 0 setwise) and `-q` unchanged; `-q2` switch OFF identical to `-q`; switch ON 18,927 rows / be0d89c156910feb, TOUCH 7,353, HOLD_BACK 1, which reproduces the earlier monkeypatch counterfactual exactly. **Dry only, no engine telemetry; the live effect is untested.**
Push: 4 changed paths (`arms_final_ladder.py`, `arms_v6cfr3.py`, `arms_v6state.py`, `d249_queue_visibility.py`), live2 `5edd1245...` to `5fcf8a2515ea5ea90aa00f3ad4d0e6400eddfc1f` (reproduced independently on the current tip), baselines subtree unchanged `e784d873...`.
