# StudyCTX1: verification of StudyDASH2 Part 6 before a build (D207)

## Verdict

NOT BUILD-READY. Selecting on DEV and applying D153 (minimum 3 frames), the best condition is C3 (3 frames), not EP-B. C3's EVAL challenge mAP is 0.682, gain vs device-only +0.054 with CI [-0.022, +0.123] whose LOWER BOUND is below zero, so decision condition (a) fails. Gain vs EP-G is +0.019 (positive, (b) passes), and C3 survives Checks 2 and 3 ((c) passes), but (a) fails, so the context change is not build-ready. StudyDASH2 Part 6's EP-B result (0.724, +0.104) does NOT survive verification: it was inflated by cross-fitting into EVAL, by not applying D153 (24.5 percent of EP-B crops are non-decision instants that the live device would serve), and by selecting on the evaluation data. Under DEV selection with DEV-fitted calibration and D153, EP-B's DEV gain over device-only is -0.037 (worse than device-only). A recommendation; the user decides.

## Check 1: select on DEV, confirm on EVAL (device-only DEV 0.651, EVAL 0.627)

Workload clips: 88 DEV, 208 EVAL (crash clips 43 DEV, 103 EVAL; both above the 30-clip floor, no escalation). Calibration fitted on SH-EP DEV EP-G only, per tier. The DEV-selected condition is the result; the rest of the table is context.

| condition | DEV mAP | DEV gain vs device | EVAL mAP | non-decision crop frac (D153) | uncached tok/instant | peak prompt tok |
|---|---|---|---|---|---|---|
| C1 | 0.651 | +0.000 | 0.627 | 1.000 | 378 | 378 |
| C3 (DEV-selected) | 0.685 | +0.034 | 0.682 | 0.000 | 1056 | 1056 |
| C6 | 0.662 | +0.011 | 0.694 | 0.000 | 2070 | 2070 |
| EP-B | 0.614 | -0.037 | 0.665 | 0.245 | 376 | 3422 |
| EP-G | 0.578 | -0.073 | 0.663 | 0.000 | 372 | 7140 |

Selection: DEV ranking ['C3', 'C6', 'C1', 'EP-B', 'EP-G']; conditions within 0.02 of the top on DEV: ['C3']; selected C3. Horizon shift of C3 vs device-only on EVAL: {'0.5': 0.0, '1.0': 1.5, '1.5': 1.5}.

## Check 2: the restart contradiction

at restart crops the cloud serves 100 percent of instants (43 of 43), so the StudyDASH2 Part 3-ext 0.170 is NOT a device-fill or which-score-stands artefact; it is a small-sample value (43 positive crops) on genuinely fresh short context, and it does not enter any committed headline (the ceiling, StudyDSMAP and StudyEXIT2 use all crops, not the restart split). No committed headline is affected, so no escalation on Check 2.

## Check 3: the minimum-3-frames rule (D153)

StudyDASH2 Part 6 did NOT apply D153; it scored the cloud at every crop including non-decision instants. Under D153 C1 is 100 percent non-decision (one frame below the three-frame minimum, not deployable), EP-B is 24.5 percent non-decision (device stands on the first two instants of each 5 s block), and C3/C6/EP-G are 0 percent. The condition mAPs here are the D153-correct recomputation.

Non-decision crop fraction per condition: C1 1.000, C3 0.000, C6 0.000, EP-B 0.245, EP-G 0.000.

## Cost

Uncached tokens per decision instant (warm append): C1 378, C3 1056, C6 2070, EP-B 376, EP-G 372. Peak per-device episode prompt (KV) tokens: C1 378, C3 1056, C6 2070, EP-B 3422, EP-G 7140.

## Decision (pre-registered rule)

(a) EVAL gain vs device-only CI lower bound > 0: False. (b) EVAL gain vs EP-G point positive: True. (c) survives Checks 2 and 3: True. BUILD-READY = False: the DEV-selected condition does not meet all three decision conditions under D153.

## Sanity

device-only EVAL mAP 0.627 (the device table computation); label-shuffle selected-condition EVAL mAP 0.469 against the base rate 0.495 (drops to base rate); the selection used only DEV numbers.
