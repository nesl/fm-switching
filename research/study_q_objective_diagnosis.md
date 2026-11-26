# WHY `-q` TOUCHES FAR LESS THAN RUNG 3 (2026-11-26T00:22Z). DIAGNOSIS ONLY, NOTHING BUILT. None of the three suspected mis-specifications explains the gap; a fourth mechanism does.

**Register: replay figures are DRY-REPLAY (constructed): seed 4, n16, 1200 s, 40:40:20, 1x, no engine telemetry, scratch tree at origin d06f9c7d. LIVE figures are the committed cells. Never blended.** Dry: rung 3 TOUCH 2,954, `-q` 1,175 (gap 1,779). Live: 2,674 and 906 (gap 1,768).
Controls: rung 3 reproduces 14,539 / 5a03c2807da3681a. `-q` reproduces the Method A value 12,555 / 41724e38cfaa2eb4. **The digest 11,386 / b7bb6e018b6e1d27 that I put in the brief is the PRE-D259 (old bar) value; my brief was stale and the agent caught it.** Recomputed harm equals the planner's `harm_touch` at 0 mismatches over 61,678 and 60,920 decisions.

## The three suspected mis-specifications
1. **Queue in the gain: real but small.** Gain is added the CURRENT queue (`arms_v6state.py:437`, qa from `:607`; qa median 168, mean 4,647, p90 17,842). TOUCH under gain variants on the `-q` trajectory: as built 1,175; q=0 1,465; q=median 1,501; decayed current queue 1,183; expected over the qa distribution 518 (unvalidated proxy, do not headline). Of the 352 rung-3 touches rejected at the `-q` margin by the queue pricing, 351 are restored by the gain alone and 0 by harm alone. Mechanism share: **+290 touches, about 16 percent of the gap.** At rung 3's own margin (0.658) rung-3 pricing on `-q` states gives 0 touches, so pricing is not what separates the arms.
2. **Harm weight 1.0: the premise is false.** The `"weight": 1.0` field (`:399`, `:500`) is written and never read here (ABSENT). Harm is already deficit-weighted: `ob.py:844` reads `counters.weight(device_id)` (`deficit_feed.py:309`, w in [1,3]). Dashcam victim weight mean 1.040, exactly 1.0 in only 5.7 percent of rows; robot victims 1.85. Harm on devices at target is 3.4 percent. Re-weighting by (w-1): 1,178 against 1,175. **About +3 touches.**
3. **Avoided-rebuild credit: confirmed absent.** KEEP is the fixed zero reference (`cf_planner.py:718`); TOUCH value is w*pq*(pw-pc) - harm_touch (`:679-681`, `:708`); the only avoided-harm term is HOLD_BACK = harm_warm (`:733`), scored only when a MATERIALIZE is pending (`arms_v6state.py:620,625`).

## What accounts for the gap: HOLD_BACK driven by in-flight harm rows, about 100 percent
Rung 3's 2,954 touch states all sit in 4 sessions, and all 4 had an earlier HOLD_BACK in `-q` (18 sessions have one). At the same (session, time) rung 3's built prefix averages 10,381 tokens and `-q`'s 2,535 (`-q` smaller in 100 percent), so mean touch gain is 0.72 against 0.13. `-q` chose HOLD_BACK 74 times against 0; all 74 values exceed 0.658 (median 3.10) and come from the in-flight rows. The held-back rebuilds are the missing build pieces (88 submitted against 163). First divergence: decision 3,012, t=206.9 s.
| full replay on the `-q` arm | TOUCH | HOLD_BACK | pieces | digest |
|---|---|---|---|---|
| control | 1,175 | 74 | 88 | 41724e38cfaa2eb4 |
| in-flight rows off, HOLD_BACK path only | **7,353** | 1 | 162 | be0d89c156910feb |
| queue term in the gain off | 1,465 | 74 | 88 | d1d7551ca0f8cf10 |
| in-flight rows off, TOUCH harm only | 1,178 | 74 | 88 | 7ca37584c95cd6b3 |
**Not additive (combined 9,288 against a sum of 7,643). The overshoot past rung 3 comes from the halved margin, which on rung 3's own states raises 2,956 touches to 9,484, so removing the HOLD_BACK path alone would likely OVER-touch.**
**Live corroboration, read from the committed cells (the signature, not the causal split):** HOLD_BACK chosen 87 (`-q`) against 2 (rung 3); `harm_warm_nonzero` 63,639 against 1,853; pieces submitted 62 against 145. The dry replay shows 74 against 0, 24,217 against 1,607 and 88 against 163, the same direction in every field.
**Why it is a mis-specification:** HOLD_BACK charges a full rebuild against every in-flight request (delay capped at 2.781 s, `ob.py:838-839`) with no credit for the later cold rebuild, so held-back sessions stay cold and their own questions pay.

## Proposed `-q2` (a NEW arm and a NEW pre-registered gate; the `-q` 1x failure stands). Not built.
1. Exclude in-flight rows from the HOLD_BACK / WARM `_harm_warm` call (`arms_v6state.py:625`) via an include_inflight flag on `_queued_behind` (`:466`, `:508-509`); keep them in the TOUCH harm (`:641`). My hour estimate: 6 to 8 flash CPU h including separate switches (today one `arm_enables` gates both the queue term and the rows), registration (`arms_v6cfr3.py:769`, `arms_final_ladder.py:87,340`) and proofs.
2. Avoided-rebuild term on KEEP (`cf_planner.py:718`) and HOLD_BACK (`:733`): new modelling needing its own derivation. My estimate: 10 to 14 h more.
3. Expected-queue pricing of the future question: DO NOT ship until the question-time queue is measured (the proxy moves the result by about 1,000 touches).
4. Deficit-aware harm already live; delete or document the dead field. 
Proofs: off-switch byte identity per arm (q2 off equals rung 3 and `-q`, as D265); Step 2b decision-log diff against both; port-rule fields non-zero (HOLD_BACK count and the credit count); negative control (credit zeroed reproduces `-q`-like HOLD_BACK). About 6 dry cells, 1.2 CPU h (one dry cell is about 11 min). Any change is a run-path change needing its own window.
**Caveat: the explanation is DRY-REPLAY. The live gap shows the same signature but a live causal split has not been done.**
