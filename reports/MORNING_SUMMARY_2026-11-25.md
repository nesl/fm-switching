# Morning summary, 2026-11-25, 07:00 PST

**Written by flash's main session for the 07:00 report D242 required. Every figure below is quoted from a
committed file, named at the point of use. Figures I could not re-derive this morning are marked
NEEDS RE-DERIVATION rather than restated from the overnight thread.**

---

## 1. The queue as run: 28 of 28 cells, all valid

| block | cells | result |
|---|---|---|
| A, kv0.5r s5/s6/s7 interleaved by seed | 9 | **9 of 9 valid**, `source_agreement` OK on all nine, no ENOSPC, no INVALID, no reruns |
| `ptg` at 1x s4 | 1 | ran, valid, 11,491 requests |
| B, baselines | 8 | **8 of 8 valid**, one incident recorded (section 6) |
| C, ladder | 7 | **7 of 7 valid**; the one stop fired on a false premise and was retired on a verified ruling |
| D, `-notouch` at 1x s4 to s7 | 4 | **4 of 4 valid**, `source_agreement` OK on all four |

**No cell was lost. No INVALID cell was produced. No rerun was needed.** The off-lattice stop armed for
blocks A and C fired once, in block C, and is **retired**: it rested on a piece-size model that the cells'
own decision logs refute (section 7).
**After block D the driver moved to the ready-matrix filler, which the H100 checked against the standing
rules before letting it run: seeds 4 and 5 only, no 0.25x lines, and the `_c10-4-2` / `_c3-11-2` tags are
fleet COMPOSITIONS rather than network or outage conditions, so D240 is not breached. I agree with that
reading.**

## 2. Block A verdict: `research/study_blockA_verdict.md`

**Two headline readings, both quoted from the file:**

**(1) `-stateoff` is negative at all three seeds and DECLINING MONOTONICALLY: 1.77x, 1.10x, 0.87x against
the 0.027752 bar.** It clears the widest bar at two of three seeds and falls INSIDE it at s7. **So the
halved-pool state-channel effect is seed-dependent in magnitude and cannot be reported as "decisive at
kv0.5r".** The 1x reading of 6.16x is at a different memory level and is untouched.

**(2) `-notouch` is INSIDE the bar at all three seeds on fixed-19: 0.62x, 0.39x, 0.99x.** Its sign pattern
holds across four seeds, **but no magnitude clears the bar at any block-A seed.**

**The registered prediction** (the sign of the s7 fixed-19 delta, committed before cell 9 started with the
commit timestamp as proof of ordering) **was POSITIVE, +373 over 13,566, confirmed from the raw logs with
all three integers agreeing exactly.** **Magnitude was excluded from the test in advance, and that
provision became load-bearing: the s7 magnitude is 0.99x, INSIDE.**
*** AND THE TWO SCALES DISAGREE ABOUT s7: fixed-19 gives +0.027495 against a 0.027752 bar, INSIDE by 257
millionths; the true-denominator scale gives +0.033324 against 0.029705, OUTSIDE at 1.122x. ANY CLAIM ABOUT
s7's SEPARABILITY MUST NAME THE SCALE. ***

## 3. Block D verdict: the touches factor is not established as load-bearing at 1x

| seed | stratum | robot | cbd | single-shot | dashcam | dose notouch / comp |
|---|---|---|---|---|---|---|
| s4 | **SAME CODE** | -3 | **-1** | +1 | **+245** | 2,633 / 2,676 |
| s5 | B | 0 | **0** | -3 | +35 | 175 / 172 |
| s6 | B | -1 | **0** | 0 | -12 | 406 / 413 |
| s7 | B | 0 | **0** | -1 | +28 | 2,211 / 2,205 |

**`correct_by_deadline` moves -1, 0, 0, 0 against denominators of 132, 127, 121 and 105. Three of four
channels are indistinguishable from zero in EVERY cell.**
*** AND THE ONE NOTABLE VALUE IS NOT CORROBORATED BY THE CELL BEST PLACED TO DO IT: s4 and s7 carry
comparable doses (2,633 and 2,211, ratio 1.19) and dashcam deltas of +245 and +28 (ratio 8.8). The effect
does NOT track the dose. ***
**RULE 2: classified "FIRED AND DID NOT HELP"** - the mechanism was present and varied over a 15-fold dose
range, `submitted_touch` 0 throughout, the comparator's `completed_touch` matching within 1.7 percent at
every seed and `state_decisions` within 0.5 percent, so the difference was in ENACTMENT. **Step 4 applies
directly without a separate control run, because `-notouch` IS the negative control for the factor.**
**SCOPE: one factor, four seeds, at 1x. NOT a finding about the policy as a whole, and it says nothing
about the other four factors.**
**Block D cannot be pooled across seeds: three comparator code states across four pairs, so only s6 and s7
are mutually comparable and s4 is the single clean pair.**

## 4. `ptg` (per-type saturation guard), freeze-gate 10.7

**The cell ran and is valid.** **Bar 1 is the amended THREE-VALUED bar at
`results/orchestration/live2/d231_ptg_guard/AMENDMENT_4_bar1_tolerance.md`: PASS, NO DIFFERENCE or FAIL
against rung 3's 0.619234 at the same seed with a 0.027752 floor, where a difference under about 0.028 IS
NOT A RESULT and must be reported as "inside the floor".**
*** THE OPEN QUESTION IS YOURS AND IT IS A COMPARATOR RULING, NOT A MEASUREMENT: whether bar 1 is scored
against the pre-registered comparator or against a same-code one. The two choices give different verdicts.
*** **NEEDS RE-DERIVATION: the exact attainment figures and the resulting verdict under each choice. I did
not re-derive them this morning and will not restate them from memory.**
**A LEDGER GAP, separate and worth a line of yours: `AMENDMENT_4`'s three-valued bar GOVERNS a bar that has
no D-row recording it.**

## 5. D242, the outage build: COMPLETE, NOTHING OWED, BLOCKED ON TWO RULINGS

**`research/study_outage_corr_BUILD_STATUS.md`. Items A, B, C, D and E are built and proved.**
**The last owed proof closed overnight: the 1,200 second outages-OFF identity.** Both new arms are
element-by-element identical to rung 3 over 14,539 rows, `first_diff_index` null, **proved in two
configurations (planner wall-clock cutoff ON and OFF, same digests, so that confound is retired)**, with a
**positive control** (`llf`, 14,075 rows, differing at row 0 in kind) and the runner first validated against
a committed 300 s digest. **The arms demonstrably ran: `outage_last_arrival_reads` 11,996, scaling with the
cell, ABSENT rather than zero on the comparator.** **And the identity holds structurally: the branch returns
the action BY IDENTITY when no reconnection is detected, so the read site fires 11,996 times and correctly
changes nothing.**
**Operational finding: the earlier attempt failed because the proof script runs SEVEN cells in one process.
One cell per process, a 1,200 s cell is 180 s and the whole proof is 27 minutes.**

*** THE TWO BLOCKERS, BOTH NEEDING YOU. NO CELL SHOULD BE QUEUED UNTIL THEY ARE RULED. ***
1. **BLOCKER 1, the ordering is a PURE PERMUTATION:** the two arms' full decision-row multisets are
   identical, so the `-outage` and `-outage-fifo` comparison **cannot differ at 1x**. Rule 2 classification
   **INCONCLUSIVE, "cancelled by geometry"**. The only regime where a gate refuses is below 1x, **which
   D240 forbids**. So the experiment as designed cannot produce a difference.
2. **BLOCKER 2, independent: the grid's premise is unsupported.** The 55,000-token history figure could not
   be sourced. It needs re-sourcing or retiring.
**Also needing a ruling: whether the pool is empty or occupied at reconnection, and whether the grid itself
needs changing.**
**Remaining hours: none are needed. The build is finished and idle. It consumed no GPU time, per D241.**

## 6. An incident, bounded and declined

*** AN s7 END-OF-WINDOW STALL IN SIX OF ELEVEN kv0.5r s7 CELLS: zero completions between about 1,196.3 s
and about 1,199.5 s. ***
```
STALLED      confidence-cascade, covex-v6-fair-final (BOTH code states), -notouch, -stateoff, covex-v6-rules
NOT STALLED  covex-v6-base, eco-llm, llf, mooncake, simplestream, covex-v6-state-final
```
**ALL THREE BLOCK-A s7 CELLS ARE IN THE STALLED GROUP**, so those deltas are between cells that share the
event. **Per-cell loss is at most 8, 5 and 4 requests against the s7 denominator of 11,779 instants, with an
inter-arm spread of 4. NO FIGURE MOVES.**
**Five hypotheses eliminated: builds, code state, the piece-size pattern, the rules core, and the state
channel (all four combinations of channel-presence and stall occur).**
**CAUSE NOT DIAGNOSED, NEEDS ENGINE TIMING: bounded and declined overnight, not missed.** A GPU-side look at
the vLLM server log would settle it; it is not urgent and moves nothing.

## 7. Two corrections to committed files, and one lead

**(a) The piece-size lattice is SCOPED, not refuted.** `piece_tokens` read from all nine block-A decision
logs: `covex-v6-fair-final` and `-notouch` emit only {121, 1024} at every seed, **so their decompositions
stand**; `-stateoff` and `covex-v6-state-final` emit REMAINDERS (301, 391, 481, 751), **so the lattice test
is invalid for them and the off-lattice stop that fired on state-final was a false positive.** The
`peak_tokens` ceiling verdict is unaffected: it rests on `host_peak_tokens` varying, on `peak_tokens`
varying by arm and seed, and on the 1x control's 83 distinct values across 233 cells.

**(b) A MECHANISTIC LEAD, recorded as a HYPOTHESIS.** `-stateoff` IS `fair-final` with the state channel
off, and it emits remainders where `fair-final` does not; `-notouch` keeps the channel and emits none.
**Remainder emission tracks the state channel exactly across nine cells.** *** THAT IS A CANDIDATE
MECHANISM FOR WHAT THE STATE CHANNEL DOES, and the first found that concerns the BUILD PATH rather than
scheduling. *** **Nine cells show the correlation; nothing shows causation or that remainders cost
anything. It is worth chasing because the state channel is the ablation that costs the most and no
mechanism for that cost had otherwise been identified.**

**(c) Request-count retention, stated in the unit measured.** `fair-final` keeps about **86 percent** of its
1x request count under a halved pool (s4 same-code and same-digest: 10,585 / 12,177 = 0.869);
`state-final` about **52 percent**. *** NEITHER NUMBER IS SERVED CAPACITY. `n_requests` is what the arm
CHOSE to send, and `state-final` declines to send 54 to 63 percent of dashcam instants; the engine is NO
LESS BUSY under it (4,700 to 4,800 tok/s against 4,200 to 4,500), so it sends fewer but larger requests. ***
**A framing of this as "capacity falls linearly, quality superlinearly" was withdrawn before being
recorded: it mixed a policy choice with service capacity.**

## 8. My own error rate overnight, reported because it bears on how to read the above

**I produced sixteen carried-value or confound errors overnight, and the accelerator box caught most of
them.** The recurring mechanism is single: **a value read in one context, reused in a statement about
another.** Instances included a denominator carried between seeds **three times**, a request rate carried
between arms, a secondary metric used where the headline one was meant **after being corrected on exactly
that**, an absence asserted while the grep refuting it ran in the same command block, and **a sign-reversal
claim built on a confound whose alternative explanation had been supplied in the message that gave me the
number.**
**Two of these were produced INSIDE a sentence whose purpose was to be the more careful version of a claim
just corrected**, which is the form worth guarding against: an overclaim dressed as caution is harder to
catch than the one it replaces.
*** THE ONE REMEDY THAT WORKED: putting figures into the committed verdict so the report reads them from a
file rather than recalling them. Every number in this report is quoted from a committed file for that
reason, and three of the overnight readings were WITHDRAWN IN THE FILE rather than quietly dropped. ***

## 9. What waits on you

| item | what is needed |
|---|---|
| **D242 blocker 1** | the ordering is a pure permutation at 1x; the experiment cannot differ as designed |
| **D242 blocker 2** | re-source or retire the 55,000-token premise |
| **D242, two more** | pool empty or occupied at reconnection; whether the grid changes |
| **`ptg` bar 1** | pre-registered comparator or same-code comparator; the choice decides the verdict |
| **Ledger gap** | `AMENDMENT_4`'s three-valued bar governs a bar with no D-row |
| **The watchdog** | it restarted this session at 07:00 on a STALE HEARTBEAT THAT NOTHING WRITES; `ops/heartbeat` is 0 bytes and the only writes are comments. It is yours to stop |
| **Mirror permission** | left open; it belongs to you |

**Nothing above is blocked on the H100 or on flash. The GPU is working inside the standing rules.**
