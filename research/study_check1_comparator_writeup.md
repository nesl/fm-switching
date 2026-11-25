# Check-1 comparator: write-up before any scorer change (user ruling 2026-11-24)

The scorer stays as committed until the user rules; this is the paragraph the ruling asked for, not a
patch. CPU-side reading of committed code and cells only.

**1. What check 1 does now (committed).** The rung verdict check 1, "alert per-episode target
attainment", lives in `experiments/orchestration/live2/d179_rung2_verdict.py` at
`verdict_for_seed`: the bar `b` is the COMPARATOR cell's mean per-episode attainment
(`d179_rung2_verdict.py:856-857`) and the arm passes iff `shares >= b - 1e-12`
(`d179_rung2_verdict.py:868`) -- an AT-LEAST test, with the comparator passed in by the caller and
NO silent default to the base after D232 (1) (rungs 2 and 3 pass the base, rung 4 passes same-code
`covex-v6-fair-final`). Two things still read base- or target-referenced and are the source of the
confusion: the module docstring at `d179_rung2_verdict.py:7` still says "AT LEAST THE BASE'S" (stale,
predates D232 (1)), and the cell scorer `experiments/orchestration/live2/scorer/score.py:776-777`
gates each dashcam device against the fixed 0.25 TARGET (`frac >= p_dash - 1e-12`), not against any
arm. So the scorer's printed per-cell attainment "meets" is the 0.25-target gate, NOT the same-code
check-1 bar, and must not be read as check 1; the same-code comparison is only correct when d179 is
called with `covex-v6-fair-final` as the comparator for rung 4.

**2. Proposed change.** Make the rung-4 check-1 bar explicitly the same-code comparator
`covex-v6-fair-final` at the SAME seed (already the D232 (1) wiring), and have the user rule three
still-open points the current code fixes by default rather than by decision: (a) STRICTLY ABOVE
(`shares > b`, the frozen `StudyLADDER_FINAL_prereg.json THE_BARS.covex-v6-final.check_1_alert`
reading) versus the committed AT-LEAST (`shares >= b - 1e-12`); (b) PER-SEED versus POOLED, which
matters now because D238 block A produces the comparator beside both ablations at seeds 5, 6 and 7,
so a rule written tonight is applied to a per-seed DISTRIBUTION tomorrow, not to single cells -- a
per-seed bar and a pooled bar can disagree and the choice must be explicit; (c) a TOLERANCE stated
against the D234 (3) measured noise floor rather than an exact threshold.

**3. Which committed numbers would move.** Against the base the rung-4 arm passes where against its
same-code comparator it fails or regresses, so the comparator choice flips committed verdicts:
per the prereg, rung-4 s7 check 1 FAILS at 0.6288 against `covex-v6-fair-final`'s 0.6483 where the
base-referenced reading PASSES it; s5 and s6 were left pending rescore and block A now supplies them
per seed. The sharper case is the five-factor state-channel ablation at 1x s4, which scores alert
attainment 0.448403 against the base's 0.442490 and so PASSES base-referenced by 0.0059, while
against its same-code comparator it is a REGRESSION of 0.170831 (6.16x the measured noise floor, 627
of 712 episodes moving) -- the committed base rule therefore returns a PASS on an arm that lost about
28 percent of its attainment. These are the verdicts the user needs listed before ruling, because
the direction of the flip (pass to fail) is what the change does.

**4. Positive control.** A known-good committed arm must still pass under the new rule: score
`covex-v6-fair-final` against ITS OWN same-code comparator at each seed -- it must pass (equality,
`shares = b`, passes at-least and is the boundary case for strictly-above, which must be stated), and
the base `hybrid-F-lhreq-noc3` as rung-2/3 comparator must reproduce the committed rung-2/3 check-1
verdicts byte-for-byte (D232 (1) already shows comparator=base reproduces them exactly). If a
known-good arm fails the new check, the check is broken, not the arm.

**Caveats to carry into the ruling.** (i) D234 (3) noise floor
(`results/orchestration/live2/d234_noise_floor/d234_noise_floor.json`): stratum-A max observed is
0.027752 over n=8 same-code pairs, and n=8 cannot support a p95 (the interpolated value is set by one
pair 3.8x the next); four earlier attainment verdicts were voided for sitting inside the floor at
0.0101 to 0.0157, so any new bar must state its tolerance against this floor rather than an exact
threshold, or it relocates the same problem. (ii) BOTH `covex-v6-fair-final` comparator cells have NO
`source_agreement` key (ABSENT, not OK) -- they predate the instrument, so the bar EITHER rule is
measured against is unaudited for source tearing; the first instrumented comparator replicates (H100
`_rep2`/`_rep3`) land tonight and the control-side audit follows. This write-up is a reading of
committed artifacts; no scorer code is changed by it.
