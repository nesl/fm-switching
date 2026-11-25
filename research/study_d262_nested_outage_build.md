# D266 ITEM 2 IS BUILT. ALL CPU PROOFS PASS. AND ONE PRE-RUN FINDING CHANGES HOW SCOPE A MUST BE READ.

**Flash, CPU only. No GPU, no cell, nothing committed to `experiments/`, nothing pushed. The build sits in a
handoff directory with every changed and new file at its repo-relative path, ready to be committed from a
scoped list.**

## *** THE FINDING TO READ FIRST: THE k CONTRAST IS NEARLY DOSE-FREE AT THE RULED DESIGN POINT ***

**Measured on CPU from the traces alone, BEFORE any cell, at exactly the ruled point (n=16, `3:11:2`,
run_s 1200, D=120, centre window 540.0 to 660.0 s, rq30, L=3):**
| pair | nested | same window | added victims | **forced-miss floor** | backlog, D2 tokens |
|---|---|---|---|---|---|
| s4, k 1 to 3 | yes | 540.0 | robo003, robo009 | **2 questions** | 5,400 to 16,200 |
| s4, k 3 to 5 | yes | 540.0 | robo004, robo010 | **1 question** | 16,200 to 26,820 |
| **s5, k 1 to 3** | yes | 540.0 | robo007, robo009 | *** 0 *** | 5,400 to 16,200 |
| **s5, k 3 to 5** | yes | 540.0 | robo006, robo008 | *** 0 *** | 16,200 to 26,910 |
*** AT SEED 5 THE FORCED-DEVICE-ONLY-QUESTION CHANNEL IS EXACTLY ZERO AT BOTH RUNGS. SO AT SEED 5 NOTHING
ARITHMETICALLY REQUIRES ANY ROBOT METRIC TO MOVE WITH k, AND A NULL THERE IS **UNEXERCISED ON THAT CHANNEL**,
NOT A NEGATIVE. The only live channel at seed 5 is the reconnect backlog, which does grow by about 10,700 D2
tokens per rung at both seeds. ***
**REGISTERED IN THE PREREG BEFORE ANY CELL: a k-effect at seed 4 and not at seed 5 is consistent with the
forced-miss channel ALONE and is NOT evidence about the policy. ONLY AN EFFECT AT BOTH SEEDS CAN BE
ATTRIBUTED TO THE BACKLOG.** The abandon check therefore classifies on BOTH channels, so a seed-5 null is
labelled `ABANDON-ON-THE-BACKLOG-CHANNEL` rather than miscalled either `ABANDON` or "no dose".
**This is a Step 0 finding in the strict sense: it would have cost accelerator hours to learn after the fact.**

## *** AND IT CORRECTS A CONCLUSION I COMMITTED AT `523b350d` ***

**I recorded that the headline robot metric gives 121/132 at BOTH k=3 and k=5, and that if nesting did not
separate them the k-effect would be UNSCORABLE and the design should stop at 8 cells.**
*** THAT IS TRUE OF CLOUD ON-TIME AND FALSE OF CORRECT-BY-DEADLINE. The same committed pair reads
`correct_answers_delivered_by_deadline` 0.621212 at k=3 and 0.666667 at k=5, n=132 both, which is 82 against
88 questions: A SIX-QUESTION SEPARATION ON THE METRIC THE USER RULED ON FOR D250. ***
**So "cloud on-time is flat" is not "the robot metrics are flat", and my abandon-check premise rested on the
wrong metric. THE DESIGN MAY NOT NEED ABANDONING AT ALL. The check now classifies EVERY recorded metric per
D251 rather than one.**

## THE ETA, AND MY ESTIMATE WAS WRONG BY ABOUT SIX TIMES IN THE USER'S FAVOUR

| | committed estimate | actual |
|---|---|---|
| flash CPU | **14.5 to 23.0 h** | *** 2.5 to 4.0 h, about 1.5 spent *** |
| accelerator, scope A | 2.88 h | 2.88 h, unchanged |
| accelerator, scope B plus the k=1 rung | 10.79 h | 10.79 h, 7.91 h after scope A |
*** THE REASON IS SPECIFIC RATHER THAN OPTIMISM: THE TWO INSTRUMENTS THE BUILD NEEDED ALREADY EXISTED AND
THE ESTIMATE PRICED BUILDING THEM. An existing per-arm decision-log identity instrument and an existing
one-sha-two-trees trace-digest idiom were reused; the only change to the former was adding a `--ratio` flag. ***
**And the build RECOMMENDS NOT CHARGING the estimate's separate 0.72 h two-cell keying gate, because its
question - does the new keying nest the victims and hold the window - is answered on CPU exactly and for
free by the nesting and trace-identity proofs. Spending two accelerator cells to re-learn a bit-exact CPU
fact is the wrong trade.**

## OFF-BY-DEFAULT IDENTITY: ZERO MISMATCHES, SIX ARMS, TWO MIXES

**`covex-v6-fair-final`, `-stateoff`, `llf`, `mooncake`, `simplestream` and `b7-edf-feasibility` as a
positive control: 0 mismatches at both 40:40:20 and 3:11:2, over 1,493 to 3,381 decisions each.** The
instrument's own determinism was measured in both trees FIRST, and the proof is non-vacuous for this patch
because the dry path calls the changed generator.
**Plus a TRACE-LEVEL proof, one sha two trees: with the outage off the trace, device answers and fairness
digest are byte-identical at both mixes; AND WITH THE OUTAGE ON UNDER THE COMMITTED BAND RULE THEY ARE ALSO
BYTE-IDENTICAL AND REPRODUCE THE COMMITTED RECORD EXACTLY (k=3 robo003/005/006 at 786.901505 s, k=5 robo001
to robo005 at 509.505651 s), so the committed outage cells stay reproducible from the patched file.**
*** ONE CAVEAT NOT BURIED: `covex-v6-fair-final` AND `-stateoff` RETURN THE IDENTICAL DIGEST, because the dry
path emits ZERO `state_action` rows for either. `-stateoff`'s characteristic decision never fires on this
instrument, so its row is a valid check of the SHARED PATH and NOT evidence about its own mechanism. That is
the port rule applied to the proof itself. ***

## THE SWITCH PROOFS, INCLUDING A CONTROL THAT MUST FAIL AND DOES

- **centre nests**: victims `{robo001}` to `{robo001, robo003, robo009}` to five, `t_start` 540.0 at EVERY k,
  span across k **0.0 s**, and `robots == sorted(victim_permutation[:k])` holds.
- *** THE BAND POSITIVE CONTROL FAILS, AS IT MUST: span 335.9 s across k with disjoint victim sets. A NESTING
  CHECK THAT PASSED THERE WOULD BE A BROKEN CHECK. ***
- **Step 2b**: instrument self-diff 0 of 1535; band against centre **1,044 differing decisions, first at row
  401**. The switch reaches decisions.
- **Arrival and not merely passing**: `placement` reads back as the string `"centre"`, `t_start` 540.0 equals
  the committed band's exact centre and lies inside `[270, 810]`, the stream key carries NO k, the trace-dir
  token differs between rules, and an invalid placement RAISES rather than falling back.
- **The D240 stack refusal is tested: `_nest_kv0.5r` and `_nest_h0.5` are both refused.**

## TWO OF THE FIVE INVALIDATION RISKS ARE FIXED IN CODE, AND RISK 3's FIX FOUND A LATENT DEFECT

**Risk 2, the trace-dir cache serving the old placement: FIXED. The placement rule is now IN the trace-dir
token, and the default adds nothing so every committed trace name stays addressable.**
*** RISK 3, the driver validating a different cell's meta: FIXED, AND THE FIX EXPOSED WORSE. Versions 39 to
41 globbed `seed<S>_n<N>_*_outk<K>d<D>*` and took the newest match, and that `*` spans the ratio and every
workload token. It now reads the resolved `trace_dir` out of the cell's OWN header and asserts k, D, the
placement AND the permutation prefix. AND A WAIT TIMEOUT NOW **VOIDS**: UNDER v41 A TIMEOUT WROTE NOTHING
AND LOOKED LIKE A PASS. ***
**Risk 4, the `_preD249` comparator, is NOT solved by design and is a sequencing question for the user.
Risk 5, the E-id, is open and is a stopping condition before any cell runs: verified at current origin that
ZERO rows cover this study.**

## THE MISSING OBSERVABLE IS BUILT AND ALREADY DISCRIMINATES ARMS

**Committed definition only (WARM iff `cached_tokens > 0`), ask time from the trace which the outage does not
move. On the five committed cells, victims cached at the first post-reconnect question, with the pre-outage
control beside every after-number:**
| cell | victims | pre-outage | device-only |
|---|---|---|---|
| fair-final k3 s4 | **3/3** | 3/3 | 4 |
| fair-final k5 s4 | **5/5** | 5/5 | 6 |
| `-stateoff` k3 s4 | 2/3 | **0/3** | 4 |
| `llf` k3 s4 | **0 readable** | 0/3 | 4 |
**The device-only count of 4 at k=3 s4 REPRODUCES THE COMMITTED AMENDMENT 2 FIGURE EXACTLY, which is the
cross-check that the window and victims this script reconstructs are the ones those cells actually ran.**
*** TWO LIMITS REGISTERED BEFORE USE. (1) THE DENOMINATOR IS k AND IT CAN BE ZERO: a robot question has a
request row only if the arm SENT it, so on `llf` the ruling's object is unreadable for ALL THREE victims,
which is an ABSENT LINK FOR THAT ARM AND NOT A NULL. (2) PROXY VALIDITY IS OPEN: WARM can come from the
history surviving (claimed) or from the reconnect burst having just prefilled the prefix (alternative), and
what distinguishes them is the PRE-OUTAGE CONTROL - rung 3 reads 3/3 before and 3/3 after, the claimed
signature, while `-stateoff` reads 0/3 before and 2/3 after, the ALTERNATIVE signature. No headline is taken
from an after-number alone. ***
**Prefix caching is PROVED from the cell's own header rather than assumed, including the last-wins argv
override, and a cell with no warm request anywhere is declared UNSCORABLE rather than reported as zeros.**

## TWO OPERATIONAL NOTES

**`origin/main` moved 23 commits during the build. Checked rather than hoped: all five changed files are
byte-identical at the old and new shas, so the patch applies with no rebase, and no driver v42 exists on
origin so the name does not collide.**
*** SOMETHING OTHER THAN THIS BUILD WROTE INTO ITS SCRATCH TREE: two paragraphs appeared in the prereg
asserting a stale origin sha and a finding from another study. The build checked the specific claim, found it
already stale, replaced the block with claims it verified itself, and dropped the other study's finding it
could not vouch for. THE SHARED SCRATCHPAD HOLDS SEVERAL AGENTS' FILES AND IS NOT A SAFE RECORD; the handoff
directory copies are the verified ones. ***
