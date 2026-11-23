## 2026-11-22 (main flash session): shares seed 4 scored, check 2 fails, and three of my own readings corrected

**Last updated: 2026-11-23
to 12. NOT A VERDICT: seeds 5, 6 and 7 are still running and the verdict is the user's.

**SEED 4, on the pre-registered scorer** (written and pushed before any shares cell existed,
positive control exact on 48 of 48 counts, and shown to discriminate at both degenerate endpoints):
check 1 PASSES, alert attainment 0.6473 against base 0.4425; check 3 PASSES at 0.9492 per-device
min; CHECK 2 FAILS at 0.3012 against a 0.90 bar.

**What the result actually says.** The committed rung 2 bought its robot gain by making alerts far
worse than base: `dashcam_all_meet` is true for base at every seed and false for rung 2 at every
seed. Shares restores alerts to better than base and hands back most of the robot gain. So D179
fixed what it was built to fix, at a price the pre-registered bar rejects. A shares-against-rung-2
comparison alone over-credits the mechanism, which is why the base figure sits beside it everywhere.

**The check-2 failure is a property of the design, not a bug.** Two of the three types are
routinely OVERSIZE against their own share (assistance 1,372 against 843.7; recall 7,717 against
1,256.7; only alert fits, 374 against 2,223), and D179 (3) admits an oversize request only when
nothing else of its type is in flight. So recall and assistance are SERIALISED, one at a time:
`oversize_wait_for_own_type` fired 430 times, on top of 70 release re-check declines against a
132-question pool. W_max therefore does not bind those two types at all and the floors genuinely
constrain only alert.

**Three readings of mine were wrong and are corrected in place rather than quietly dropped.** The
pre-registered W-overrun signature FIRED: `alert+assistance` reached 1,174 time samples with no
recall present, because my dry claim that only recall is oversize was an artefact of smaller dry
assistance bodies. "Alerts are never denied" was a dry reading; live they are denied 17.4 percent
of gate calls. And I quoted `by_deadline` retention of 52 percent as a second reading of check 2,
when `by_deadline` is an ACCURACY that falls back to the device answer and so re-admits the side
D177 excludes; the two readings differ 0.3012 against 0.5267 and the wrong one flatters.

**A field read and never written, in my own instrumentation.** `_log_decision` accepts `key` and
never puts it in the `DecisionRecord`, so the hold rows resolved 0 of 1,266 in the scorer while
every other number looked right. The instant travels in `opportunity_ids`.

**Next.** Seeds 5 to 7, then the scorer over all four and the D184 verdict. Two items are for the
user and not for a mid-grid fix: `pending_by_type` is declared in `allowed()` and never read, so
D179 (3)'s "the flexible pool goes to types WITH PENDING WORK" is unimplemented and every share is
tighter than specified; and the oversize serialisation above is the lever that would change check 2.

## 2026-11-22 (main flash session): rung 2 shares cells gated and running; rung 3's deficit feed found absent twice over

**Last updated: 2026-11-23.** StudyD179-SHARES, StudyFAIR-FEED and StudyPORT-EXCL, under D179 to
D182 and the user addenda 1 to 12.

**RUNG 2.** V6SHARES_CELLS is posted at `19d8b416` (sha256 `75909a17cdb886ea`) and gated
independently by the H100: covex-v6-state-shares at 16 devices, seeds 4 to 7, running from about
16:16. The gate passed on the release re-check's alert skip rate of 0.1781 against a 0.50 bar, down
from 0.999836 before the `414d332a` register fix, on off-switch byte identity against pre-change
committed values, on an ATTRIBUTABLE Step 2b, on the port rule (87 denials over 30 distinct
instants, alerts never denied), and on W not leaking. The three pre-registered D179 (6) checks are
in the cell-list header and will be reported per seed whatever the outcome. If any fails, rung 2
adopts c5attr as a logged override of the D181 rule (addendum 9 item A) and no further C5 variants
are built.

**RUNG 3 IS NOT YET EVIDENCE, and the reason is worth reading before any fair cell is believed.**
The deficit feed was built correct, non-constant and with a live read, and it moved ZERO decisions
in both of two conditions. That is an absent link twice over: the coordinator never PASSED the
weights to the allocator that has always read them (a write-only field, and the main session had
told the building session the consumer was wired when it was not), and with the channel restored by
a shim the weights STILL could not matter, because they scale only the flexible pool and no type's
typical request falls in the band where that pool decides. 98.3 percent of share decisions took
weight-blind branches. The user's remedy adds ORDERING as the primary consumer, with floors, W_max
and the oversize rule untouched.

**A PRE-REGISTRATION WAS CORRECTED BEFORE ANY CELL RAN, AND THE ERROR WAS THE MAIN SESSION'S.**
Gain 2.0 was declared with the justification "a type at half its target counts double, range 1 to
3". The raw form `w = 1 + gain x shortfall` does not do that: a shortfall cannot exceed its own
target, so the range is 1 to 1 + gain x target, which is [1.0, 1.5] for alert and [1.0, 2.8] for
recall and assistance. The error ran against the type with the largest deficit. The normalised form
now stands, is what the justification always described, and the raw form is not run.

**EXCLUSIONS.** cascade-routing and r3-streaming are out of the scored baselines under D130 for
failing the port rule by construction, with their cells kept for provenance and the paper listing
both with the reason. The anomaly that led there was a misread of the arm-independent device-only
floor, caught by consistency check 7.

**Next.** Rung 2's verdict at about 17:50 from the pre-registered scorer, which is being built
BEFORE the cells land so the computation cannot be shaped by the result; rung 3's two consumers and
its pre-registered pass condition; rung 4's protect-and-defer.

## 2026-11-22 (main flash session): D179 share-based admission under construction, and a register fault that fired a STOP

**Last updated: 2026-11-22.** StudyD179-SHARES and the StudyC5-ATTR outcome, under D179 to D181
and the user addenda of 2026-11-22.
**NO SHARES RESULT EXISTS. The allocator has no call site, so both switches are registered and
read by nothing, and the 17-of-17 off-switch byte-identity proof is TRUE AND VACUOUS until that
changes.** `runs/V6SHARES_CELLS` is deliberately NOT posted: driver v27 already reads that path at
top priority, so posting it now would run the arm with write-only switches and produce a cell
byte-identical to `covex-v6-state-uo` under a new name, which would read as a shares result and be
a rename.

**StudyC5-ATTR is CLOSED as a candidate, by a rule pre-registered before its cells ran.** Alert
verdict FAIL / MEETS / MEETS / MEETS at seeds 4 to 7, with dashcam on-time gains of +901, +1,253
and +646 at s4 to s6, so the mechanism fires and helps on its own target. It is still not adopted:
adoption required the alert target at 3 of 4 seeds WITH robot `by_deadline` within 0.01 of the
comparator, s4 fails on alert and s6's robot gap is -0.033, so at most 2 of 4 could qualify, and
that was settled before s7 ran. The ROBOT COST disqualifies it, not the alert bucket. The engine
flag fallback is also null, measured at both rungs. So share-based admission is now the ONLY live
route, which raises the cost of getting it wrong.

**Frozen and committed.** `W_max` 4,323.3 uncached tokens; floors alert 1,622.1, recall 655.8,
assistance 242.8, summing to 58.3 percent, so D180's 0.75 cap does not fire and no floor is
scaled; both D180 bounds are import-time assertions. D181's lambda rule is applied per type, and
addendum 5's check passes with a zero: the feasibility share of the 7,149 unsent alert
opportunities is 0.00 percent against a 2 percent bound, established from the code and from the
data independently.

**Four faults found BEFORE any sweep, each of which would have produced a believable shares
failure rather than a crash:** an oversize branch that refused every 2,048-token warm chunk in
every state, which is warming switched off and not tight floors; background denied its own type's
floor, which D179 (3) places there; a headroom test that refused the median recall question, so
the arm would have served no robot traffic; and a floor tested after headroom, which refused a
374-token alert for the 1.48 s prefill of one oversize recall and so rebuilt the head-of-line
blocking D179 exists to remove. A floor is an admission guarantee, not a budget line.

**A STOP fired and is classified, not worked around.** The wire-time release re-check skipped
12,166 of 12,168 alert requests, against a 50 percent bar. Cause: `_uncached_in_flight` was
incremented at four unconditional sites and decremented only under `if self._d162_pricing`, so on
an unpriced arm it was the run's cumulative uncached volume under a name that says queue depth.
Every earlier read sat inside the same gate, so nothing was wrong until the re-check became the
first reader outside it. Fixed in `414d332a`, proved decision-neutral on one priced and one
unpriced arm against pre-change committed digests. Under Rule 2 the run is INCONCLUSIVE,
wrong-register input, and is not evidence about the policy. The field passed Step 2 and Step 2b
while meaning the wrong thing, which is exactly why the register is marked at the point of use.

**Stated limit of the mechanism, to be read before any shares result.** The oversize exemption
necessarily overruns `W_max`, and nothing can be preempted, so a floor can only be protected
prospectively. One median recall holds W above `W_max` for about 1.48 s, roughly 22 percent of
wall time at the base's measured 179 recalls per cell, with about 14.5 alert opportunities inside
each overrun. Alerts inside their floor still flow; alerts above it wait. Reports must plot W
including overruns rather than clipping at `W_max`.

**Definition audit, check 4.** Live W is submit to FIRST TOKEN; dry W is submit to SETTLE, because
`on_first` is wired only when a real backend exists (`procsplit.py:430-433`). Same name, different
quantities, the dry one larger. Dry and live W must never be compared, and a dry cell can prove
the allocator's logic and determinism but cannot size W.

**Next.** Wire the allocator and the W tracker into the coordinator's admission path, which is the
step that turns four passing-but-vacuous proofs into real ones; re-run the release re-check on a
D162-priced arm now that its input means what it says; then the dry s4 report, the section 12
rows, and only then a cell list.

## 2026-11-22 (session C5-B): two CANDIDATE fixes and one engine diagnostic for rung 1's dashcam loss, all default off

**Last updated: 2026-11-22.** StudyC5-ATTR, under the user ruling of 2026-11-22 (addendum).
**NOTHING IS ADOPTED AND NO WINNER IS DECLARED; that choice is the user's.** Every switch is
default off and is turned on only by an arm a cell list names.

**Built.** `covex-v6-state-uo-c5attr` (`experiments/orchestration/live2/arms_v6c5.py`, a subclass of
`covex-v6-state-uo`, whose own file is untouched): identical in every respect except that C5 does
not halve its cap for a slow monitor whose wait overlapped a robot prefill THE COORDINATOR ITSELF
RELEASED (a build, touch or recall with uncached >= 200 tokens). The overlap test is the
coordinator's (`_self_released_overlap`, reported on the completion hook that feeds the EWMA); the
decision is the arm's (`_attr_suppresses`, read in `_aimd`); the switch is an INSTANCE attribute on
the HybridArm that owns the cap.

**Proved.** Step 2b on the committed live traces (`c5attr_replay_proofs.json`, read-only): the rule
prevents **436 to 514 of the 539 to 599 cap halvings per rung-1 cell** (the counter reads 4,153 to
4,899 suppression EVENTS, because a suppression does not advance C5's one-second cooldown and the
rule re-evaluates every 0.1 s epoch while the trip persists), cap decreases fall **539-599 to 85-112**,
epochs with the cap at its floor fall **7,544-8,428 to 3,324-4,877** of 12,000, and **4,529 to
6,528 epochs end with a different cap**. Controls: the committed replay reproduces
`c5_loss_split.json`'s own reconstruction exactly and the base arms' own counters within one count;
NEVER-SUPPRESS reproduces the committed trajectory exactly; ALWAYS-SUPPRESS moves it. Dry, in
code (`c5attr_digest_proofs.json`, ALL_PASS): the four committed arms are byte-identical across this
work with the BEFORE side taken from git; the cap series moves, the first halving slips 7.1 s to
11.0 s and cap decreases fall 1,193 to 699; and
**differing decisions are ZERO, declared UNEXERCISED** because the dry stand-in's monitor latency is
a constant, so above the trip the cap sits at its floor in both arms.

**What bounds it, from the same read-only pass** (`c5attr_trip_attribution.json`, under the user's
second addendum): only **50.7 to 54.7 percent** of rung-1 halvings fire on evidence the rule can
attribute to our own released work. **30.5 to 37.6 percent** are trips where the EWMA is above
0.8 s while no individual pending monitor was, 3.9 to 7.3 percent fire on monitors that overlapped
NOTHING of ours, and the rest are mixed; the rule suppresses none of those by design. At rung 2 itself (covex-v6-state-uo s4 and s5) the
rule can see more: **63.4 and 63.7 percent** of halvings fire on all-ours evidence. The same pass
reproduces the user's release-delay reading on those cells exactly (p50 0.742 and 0.724 s, p90
0.968 and 0.953, 71.6 and 71.3 percent over 0.5 s, first token p50 0.483, dashcam uncached 376),
against the base's 0.201 to 0.362 s and 26 to 43 percent, so **the lateness is release delay inside
the coordinator, not engine time**, and the engine-flag cells are secondary.

**NOT an outcome.** A replay holds the trace fixed. Nothing here shows that either candidate
improves alert on-time delivery; the posted live cells are the only thing that can.

**Posted for the H100:** `results/orchestration/live2/frozen_test/runs/C5DIAG_CELLS` - two
`covex-v6-state-uo-c5attr` cells (seeds 4, 5) and two ENGINE-FLAG DIAGNOSTIC cells
(`covex-v6-state-uo` and `covex-v6-base`, seed 5, tag `_L3_epg_rq30_lpt2048`) that the H100 must
launch with `--long-prefill-token-threshold 2048` and then restore the committed no-flag
configuration. **N = 2048 is pre-registered in `research/prereg_c5_engine_flag.md`** with the
arithmetic from the vLLM 0.31.0 source. The flag is SERVER-WIDE: adopting it would mean rerunning
every arm, which is why it is a diagnostic and not a candidate policy.

## 2026-11-22 (session E): the cascade arms' DEV threshold calibration, one arm released of three

**Last updated: 2026-11-22.** StudyCASCADE-calib, pre-registered in
`research/prereg_cascade_calibration.md` and committed BEFORE any threshold was computed
(`d8b88619`), per D164 and the user ruling of 2026-11-22 item 2.

**`confidence-cascade` IS CALIBRATED AND RELEASED.** One floor per CONFIDENCE TYPE, by its own
card's procedure (the median committed device confidence over DEV questions), each on that type's
own DEV population: robot **0.800338** (LH-REQ DEV 28, per D143 A), ss_mcq **0.985936** (131),
ss_free_form **0.984783** (98), ss_point **0.817276** (83, DECLARED WEAK, no headline). The robot
floor moves 0.7358 to 0.800338, ratio 1.088, which is a POPULATION change and not a method change.
Its characteristic decision occurs IN BOTH DIRECTIONS for every type (223 CLOUD against 266 DEVICE
over 489 queries, 0 absent confidences, 0 unresolved types), Step 2b moves 264 / 262 / 178 / 238
decisions per type, and the cross-process identity control passed first. **Its EPISODIC threshold
`tau_trigger` is UNEXPRESSIBLE here** and that is declared on every row: live2's delivered stream
score is a placeholder, two distinct values in 72,000 reads, so the dashcam side escalates
unconditionally whatever tau is.

**`cascade-routing` IS NOT RELEASED, for two independent reasons.** Its card's method cannot be
expressed (lambda is fitted offline against a cost budget B; live2 has only physical capacity, D58,
and D174 (1) found zero budget refusals anywhere), and it FAILS the CLAUDE.md port rule: 0 of 489
recall decisions are its characteristic skip-or-cascade choice, all are post-hoc stops, and
lambda 0.02 against 2.0 moves 0 decisions. **`eco-llm` is not released either, but nothing found
here blocks it**: its card specifies no threshold and it reads no confidence at all, so the
matrix's own premise was wrong for it and releasing it is a one-line user ruling.

**D168 / D155 (5) is CLEARED for both device-waiting cascade arms**, verified on the coordinator's
own counters: 18,364 and 18,463 measured lookups with every `no_measured_value` counter absent, so
neither reads the superseded 0.567 s proxy. **One stale label reported and not changed:**
`scorer/score.py:cascade_device_wait()` compares two constants and so still stamps `proxy-0.567`
on every cascade score header. Report `reports/study_cascade_calibration.md`.

## 2026-11-22 morning (session D): D174 applied, rung 2 posted, and the rung-1 gap explained

**Last updated: 2026-11-22. The 06:00 summary below is superseded on the budget charge and on
whether a rung-2 cell list is posted; everything else in it stands.**

### D174 (1): the budget charge is uncached tokens only, and it PASSES D102 both halves

The charge is `0.0001824312597782467 x uncached`. No 0.0678 s intercept (per-request OCCUPANCY,
not work) and no queue term (delay SUFFERED, not work); both excluded terms stay in the planner's
harm to others, where they are the right quantity.

| half of D102 | result |
|---|---|
| never binds artificially | 0 budget refusals on a dry 8-device probe cell, 2,038 state decisions, 4,376 decision rows against covex-v6-rules' 4,376. Work-only gave 298 refusals and 4,317 rows; the full first-token formula gave 10,612 and silenced `plan_state` entirely |
| utilisation tracks measured GPU busy time | per-uncached term 737.5 s against measured 721.9 s (s4) and 985.3 against 964.5 s (s5), ratio 1.022 on both; implied 5,482 tok/s against the committed 5,600; utilisation 0.61 and 0.82 of wall against measured busy fractions 0.60 and 0.80, nothing oversubscribed. Work-only reached 1.07 and 1.34 and FAILED here |

`V6STATE_CELLS` is reposted as `covex-v6-state-uo` at seeds 4 to 7, a DISTINCT name so the
budget-mispriced s4/s5 and held-code s6/s7 cells keep their meaning. The rung-1 rerun is skipped
per the ruling: the budget never bound there.

**The charge MODE is now arm-scoped** (`live2_charge_mode`), not a module global. A global that any
code path can move is how covex-v6-state s6 ran an unruled charge and died at t = 264 s of 1,200.

### D174 (2): the rung-1 dashcam submission gap is C5's AIMD cap collapsing

Read-only from the committed cells, no new cells. Identical opportunity streams (11,764 monitor
opportunities at s4 in both arms); released fraction 0.41 to 0.46 at rung 1 against the base's
0.83 to 0.89 across seeds 4 to 7. **Both hypotheses in the ruling fail, and the mechanism is a
third one.**

- **(a) warm builds occupy slots: not the per-epoch mechanism, and it cannot be.** C5 subtracts
  only `running_by_class["episodic"]` from its cap and cstate classes piece and whole builds under
  `"recall"`, so a build cannot take a dashcam cap slot at all. 59 to 70 percent of the epochs
  where a monitor goes unreleased have NO build in flight.
- **(b) C2 fires more often: REFUTED WITH THE OPPOSITE SIGN.** Epochs with a robot inside
  k_r = 0.9 s are 261 to 562 at rung 1 against the BASE's 578 to 711, because warming is what
  stops a question being at risk. At-risk epochs touch 2 to 6 percent of the gap epochs.
- **(c) the AIMD cap collapses.** 156 to 180 long builds per cell, under one in flight on average,
  push monitor first-token p90 from 0.65 to 0.71 s to 1.39 to 1.65 s and the share above C5's 0.8 s
  trip from 4 to 6 percent to 21 to 27. Each trip HALVES the cap (floor 4) and recovery is +1 per
  5 s, so the cap sits at its floor for 7,544 to 8,428 of 12,000 epochs against the base's 1,844
  to 2,989, and the release budget (cap minus episodic in flight) is zero in 87 to 93 percent of
  the gap epochs. The hysteresis is why (a) reads as absent per epoch: the damage outlives the
  build that caused it.

**Positive control:** the reconstructed AIMD trajectory reproduces the base arm's own `c5_decrease`
and `c5_increase` exactly on all four base cells (154/154, 112/111, 118/117, 92/92 and 97/97,
106/106, 97/97, 77/77). Without that the cap trajectory would be a model output compared against
nothing.

**Declared proxy (check 6):** the C2 test is reconstructed from arrival and release times inside
k_r, not from the arm's predicted remaining work, so it OVERSTATES at-risk periods and the
refutation runs in the safe direction. It exists because v5-rules-2's `arm_stats` reports only its
own warming counters: the base hybrid it wraps keeps `c2_throttle_periods`, `c2_throttled_dash` and
`c5_dash_held` in a separate Counter that NO committed v5-rules-2 cell surfaces. Recommended for
future cells.

**What this means for the ladder.** The rung-1 dashcam loss is not budget (zero refusals), not the
cap arithmetic and not C2. It is the base policy's own controller reacting to a latency signal that
warming moves, so repricing could never have fixed it. Any fix is a change to C5's AIMD rule or to
how warming yields: **a policy change for the user to rule on, not an implementation fix, and it
has not been made.**

### D174 (3): the oversized logs are mirrored and verified

The four attentionstore-prefetch `decision.jsonl.gz` (8.1 to 10.5 MB, 1.01 to 1.34 M rows, 99
percent `state_action`) stay off git. Mirrored to `/home/pragya/fm_oversized_logs/runs/<cell>/` and
verified against `oversized_logs_manifest.jsonl` on sha256, byte count, row count, kind histogram
and first and last timestamp: four of four exact. The H100's key is read-only on flash and flash's
key is confined to the H100's rsync root, so the transfer is a PULL from the share; no new key was
needed and nothing was worked around.

## 06:00 summary (session D, 2026-11-21 overnight): the v6 ladder built to rung 3, and why no cell list was posted

**Last updated: 2026-11-21 (overnight). The section below this one is SUPERSEDED for everything it
says about arm names and about full v5 being built; its cost-model-gate analysis stands.**

### What was built, rung by rung

D172 renamed the ladder and `research/arm_name_map.md` maps every committed name onto it.
Committed cells keep their original names.

| rung | name | was | state tonight |
|---|---|---|---|
| 0 | `covex-v6-base` | `hybrid-F-lhreq-noc3` | READY, 6 committed cells, reused |
| 1 | `covex-v6-rules` | `v5-rules-2` | READY, 4 committed cells, reused |
| 2 | `covex-v6-state` | did not exist | **BUILT tonight** (`arms_v6state.py`) |
| 3 | `covex-v6-fair` | did not exist | **BUILT tonight** (`arms_v6fair.py`) |
| 4 | `covex-v6` | `v5-full` | runnable **for the first time**, ZERO cells |

### The three findings that matter more than the build

**1. `v5-full` had never run.** It raised `RecursionError` on its first observation, every time,
because `__call__` dispatched through `self._rules.__class__`, which resolves against the object
actually running, so a `V5FullArm` borrowing `V5Rules2Arm.__call__` found that same method again.
988 frames and out. Every earlier statement that full v5 was built described a class that existed,
not an arm that ran. Fixed by naming the delegate class statically. Its first completed decisions
were made tonight: 6 counterfactual request decisions on a dry cell.

**2. Three mechanisms are live, fed, and still inert, each for a measured reason.** This is the
same shape three times and it must not be reported as three nulls:

| mechanism | was inert because | is now inert because |
|---|---|---|
| device term in the counterfactual (D171 (3)) | the input was a flat 0.567 s proxy | the measured robot warm latency, 0.2503 to 0.3108 s, is inside every robot deadline |
| deficit weighting (D172 rung 3) | `observe()` had no caller, so every weight was exactly 1.0 | the feed runs, and at 8 devices 4,333 of 4,333 answers are on time, so every shortfall is 0 |
| `plan_state` (D172 rung 2) | it had no caller outside the proofs, so it was ABSENT | it decides, and the model-error margin overrides it |

The first two moved from **artefact** to **measured fact**, which is a different claim from
"constant" and the one that is true. Under Rule 2 they are UNEXERCISED, not negative.

**3. The margin stops `plan_state`; the rung still moves, through a different switch.**
`covex-v6-state` makes **44,300** state decisions at 16 devices and chooses KEEP on every one.
`plan_state`'s own argmax prefers a non-KEEP candidate on 44,299 of them; D151's margin rule then
overrides it back. Maximum predicted gain **0.151** against `MARGIN_CF` **0.16456**, with an
arithmetic ceiling of 0.250, so it is a near miss and not a cap.

But the rung is **not** byte-identical to `covex-v6-rules` at 16 devices: digest
`6e8927b9f7f92040` against `ae997d6af16a2ef4`, 15,734 rows against 17,050. At **8** devices it
*is* byte-identical (`69874e94d2ddee85` both). So the difference is not `plan_state`, which emits
nothing, but one of the rung's other three additions, and it appears only where the budget binds.
**Attributed by one-factor ablation: state-based pricing, alone.**

| arm | digest | rows |
|---|---|---|
| `covex-v6-rules` | `ae997d6af16a2ef4` | 17,050 |
| `covex-v6-state` | `6e8927b9f7f92040` | 15,734 |
| `-off` | `ae997d6af16a2ef4` | collapses, so the control is a control |
| `-noprice` | `ae997d6af16a2ef4` | **the only ablation that returns** |
| `-noretain` | `6e8927b9f7f92040` | unchanged |
| `-nobelief` | `6e8927b9f7f92040` | unchanged |

**The last two rows are not nulls.** Per-type host retention acts by sending `kv_transfer_params`
to vLLM, and the belief corrector runs off the engine's own `cached_tokens`. A dry cell has
neither, so both are **unexercisable there by construction** and those two ablations could not
have differed. The coordinator's own comment says exactly this of the belief read: a dry
byte-identity screen proves the correction harmless and proves nothing about it. Reporting either
as "no effect" would be the E36 failure again.

Only **65** of the 44,300 state decisions coincide with an actual rebuild, and all 65 had nothing
queued behind them, so `harm_warm` was 0 on every one and `HOLD_BACK`'s gain was 0 throughout.
The computed `harm_warm` therefore did not get a chance to act in this cell.

### What was posted

**`runs/V6STATE_CELLS`**, four cells, `covex-v6-state` at 16 devices, seeds 4 to 7, `_L3_epg_rq30`.
Posted only after the ablation above named the switch. Two of the rung's four additions cannot be
tested without an engine, so the dry evidence is exhausted and these cells are the only way to
exercise them. Expect **no TOUCH**: `plan_state` never deviates, and that is the predicted result,
not a fault.

**No `V6FAIR_CELLS`, no `V6_CELLS`.** Rung 3's D165 lexicographic objective is not built; rung 4
needs `plan_sync` wired, the compounds, the episode switch and D170's over-limit rule.
`MARGIN_CF` is never changed (D157, D172).

### `harm_warm` is computed, not declared

Pre-registered in `research/prereg_harm_warm_d172.md` **before** any grid was rerun under it
(ruling relayed by the H100; marked PROVISIONAL under D106 / D116 until the user confirms).
`HOLD_BACK`'s value **is** `harm_warm`, and until tonight every caller handed that number in: in
`d171_proofs.py::P5` 33 of 48 state deltas came back exactly equal to the grid's own input. It now
comes from the committed D162 `per_queue_token` coefficient (0.00015358, **not**
`per_uncached_token` 0.00018243, which is 19 percent larger and answers a different question),
through the same `p_on_time` curve and valued by the same `option_value` as `harm_to_others`, so
gain and harm stay in one currency. Capped at the healthy-regime bound 2.781 s with
`harm_warm_capped` counted.

On a dry 8-device cell: priced on 527 of 2,035 decisions, mean over the priced set 0.1039, max
0.120, capped 0. `WARM`'s mean gain is **negative**, -0.0218, because warming now carries the cost
it imposes on the queue behind it.

### Bugs found by building, each of which would have produced a confident null

1. The question-rate lookup was keyed on `session_id`; the rules arm keys `_gap_ewma` on **device**
   id. Every lookup missed, `plan_state` planned nothing in 21,003 epochs, and every surface sign
   said the rung was wired. Caught by counting skips **by reason** instead of trusting the zero.
2. The four capability flags were class attributes, so `covex-v6-state-off` kept them on and the
   "negative control" differed from the rung below by 4,376 rows while claiming to be it.
3. `state_delta_milli_sum` landed inside the per-candidate loop and triple-counted every delta.
4. `harm_warm`'s mean was divided by all decisions rather than the priced ones: 0.0269 against the
   correct 0.1039.
5. `deficit_feed_unseen_declines` was named in a docstring and a commit message and never
   incremented. Now live: 2 declines the feed cannot see, against 4,333 it can.

### The posted cells were skipped once, and the reason is a verification failure worth keeping

`covex-v6-state` s4 crashed 80 s in with `KeyError: unknown arm 'covex-v6-state'` and all four
cells were skipped. I had checked that the v6 names resolved by importing `arm_names_v6` in **my**
process and calling `make_arm`. They did. `run_live2_real.py` imports `hybrid` and nothing else,
so in the **harness's** process they were never registered.

**A name resolves in the process that resolves it.** A check run in a process the harness does not
use is not a check of the harness, and `make_arm` returning an object proves only that whatever
*that* caller imported was enough. This is the register rule from the other side: the entry
existed, and I never verified it existed where it is read.

Fixed by registering the ladder in `arms.py` beside the other arm families, so importing `arms` is
enough. Proved by `v6_harness_name_proof.py`, which **spawns `run_live2_real.py` itself** with the
real command line; all five names return rc=0 and the cells complete. Its negative control is not
optional: "no KeyError appeared" passes trivially if the subprocess never reached `make_arm`, so a
deliberately unknown name must still raise, and it does.

### PROVISIONAL decisions (D106 / D116, user away)

- Rungs that are not built are registered to a factory that **raises** and names its missing
  components, rather than being left unregistered. Either way a driver skips the item; a raising
  factory says why. Reversible in one line.
- The `harm_warm` ruling arrived relayed by the H100 and is marked PROVISIONAL until confirmed.
- Belief correction was made **arm-scoped**. It was a process-wide env switch, so enabling it for
  one arm enabled it for every arm in the same run, which the switch's own comment forbids.

### Blockers

- **rung 2 and 3 cell lists**: the predicted gain does not clear `MARGIN_CF`. Recorded, not worked
  around.
- **rung 3**: the D165 lexicographic objective is not built.
- **rung 4**: `plan_sync` has no caller, the compound candidates are unbuilt, the episode-rule
  switch is missing, and D170's explicit over-limit rule is not in.
- **the deficit feed's blind spot**: declined opportunities never reach the completion hook, so a
  device whose requests are declined has its shortfall undercounted. Counted, not corrected.

---

## 06:00 analysis summary (session D): v5-rules, the cost-model gate, and what is blocked

**Last updated: 2026-11-21 09:00 (StudyFIG paper figures M1-M8 motivation and E1-E8 evaluation (PILOT) plus a one-page contact sheet complete and pushed; StudyORIN-REC-REASK seeds 4-7 complete, parity 75 of 78 reproduce part 1 and 78 of 78 reproduce warm, 141 of 398 re-asks change the device answer. PREVIOUSLY 2026-11-21 07:30: section 1b superseded, section 5 extended; the 06:00 summary itself stands).** Headline figures for every arm and cell are the H100's, in
`reports/study_frozen_test.md` section "06:00 SUMMARY (2026-11-21, H100 overnight; D156 (5) form)".
Nothing in this section restates a number from that table; the analysis below is the other half.
Full write-ups: `reports/study_v5_rules.md`, `reports/study_cost_model_gate_d156.md`.

### 1. FULL v5 DOES NOT GO LIVE. The D156 (4) cost-model gate FAILS, measured tonight for the first time.

The gate could not run until all four held-out EP-G WARM-ALL cells were valid, which happened at
about 03:45. It then failed on three independent grounds
(`results/orchestration/live2/frozen_test/cost_model_gate_d156.json`):

| | n | predicted p50 | actual p50 | ratio | negative predictions |
|---|---|---|---|---|---|
| in sample (CAL1F) | 27,985 | **-1.2727 s** | 0.7629 s | **-1.67** | **52.2 percent** |
| held out (EP-G) | 42,417 | **-1.4344 s** | 0.7081 s | **-2.03** | **61.6 percent** |

1. The fitted model predicts **negative first-token latency** for 52.2 percent of its own fit data
   and 61.6 percent of held-out data. Physically impossible, so the model is **invalid rather than
   inaccurate**, and this is visible **in sample** with no held-out test needed (check 2).
2. The held-out ratio is negative, so there is no sense in which it is off by a factor.
3. Held-out p90 absolute first-token error is **31.92 s** against a 1.0 s dashcam deadline.

**Diagnosis: the FIT set is internally confounded by arm.** The two CAL1F fit cells differ by 160x
in overlapping-request count (969 against 6) and 120x in first-token latency on the same workload,
so OLS spans that with one linear term and buys the cheap end by driving the intercept to -2.37 s.
This is the assessment's recorded *warm is confounded with arm* recurring as **load confounded with
arm inside the fit set**, which is worse: the earlier confound limited what the gate could identify,
this one makes the fitted model invalid.

**Positive control passes (check 7):** the committed `cost_model_gate.json` recorded intercept
-0.024 and held-out ratios 0.91 to 1.13 over 26 pre-EP-G cells, same functions, same code path. So
the estimator is sound and the **fit set** is not. The estimator was imported unchanged from
`live2/cost_model_gate.py`; only the split differs.

### 1b. ADDENDUM 07:30, superseding the 06:25 addendum: a severity separation, NOT a bracketed knee

`reports/study_saturation_knee.md`, commits `939b300` then `8673361`, instrument
`experiments/orchestration/live2/v5/knee_two_sets.py`. The earlier instrument
`knee_within_run.py` and its JSON carry a **withdrawn** bound; the report holds the full retraction
and what I claimed first, which is the record. This section holds only what currently stands.

**WITHDRAWN at 07:30:** the knee "bracketed to [4,511.7, 4,685.8] uncached tok/s, 3.9 percent, zero
misclassifications in 29 cells", which I published at 06:25 and the H100 adopted. Putting the
committed gate's own 26 cells on the same axis gives an **overlapping** partition at the same
declared 2.0 s criterion: highest non-crossing 4,706.9, lowest crossing 4,670.5, interleaved across
that band. No threshold among 2.0, 5.0 and 10.0 s separates the combined 56 cells, and at 5.0 s the
EP-G set inverts on its own. The clean partition existed only inside the set whose gap I used to
pick the threshold, and the sensitivity check I reported was applied to crossing *times* rather
than to the *partition*, which is the check that would have caught it.

**WHAT STANDS.** A severity separation with the middle unoccupied: across the gate's 26 cells the
worst first-token p50 in any 100 s window **never exceeds 2.781 s** and is 0.915 s or below in 23
of them, while every severe cell in either set is at 5,190 uncached tok/s or above with a worst
window of **31 to 478 s**. Run-mean uncached tok/s does **not** determine which side a cell falls
on, so this is a transition zone of roughly 4,500 to 4,750, not a threshold, and the axis is
incomplete.

**Section 1's gate diagnosis is UNAFFECTED and does not depend on the withdrawn bound.** The two
CAL1F fit cells sit at 4,511.7 and 5,476.2 tok/s with worst windows of 0.26 s and 31.89 s, a **120x
severity difference inside one fit set**. That is what drives the OLS intercept to -2.37 s and makes
52 percent of in-sample predictions negative. The verdict is unchanged, v5 still does not go live,
and the remedy is still specific: a fit set whose cells do not differ 120x in service severity.

**Also unaffected:** for the 10 EP-G crossing cells the **pooled** first-token p50 is a two-regime
mixture and may not be compared between arms, since the controlled pair 1.0 percent apart in load
differs 47x pooled and 1.9x on the terminal window. That rests on the per-cell within-run ramps,
not on any threshold. No scored quantity moves, because deadline and on-time are per request and
are never pooled across the regimes. The H100 has adopted this in `reports/study_frozen_test.md`.

**A second correction against myself, still standing:** I hypothesised that *crossing time*
explained the severity spread. Terminal-window p50 correlates with run-mean load at rho **+0.84**
and with crossing time at rho **-0.13**. Refuted by my own instrument.

**The cache lead is closed unresolved.** The dashcam COLD share nearly triples at the crossing and
accounts for roughly 1,900 of the ~4,000 tok/s rise, but LRU pressure is refuted at request level
with the wrong sign, and the queue-to-cold test is **void** because `session_id` is null on all
9,434 dashcam request rows, which pooled 6 devices into one pseudo-session. It needs
instrumentation, not another file: a per-dashcam-session cache log or an engine-side eviction trace.

### 2. MARGIN_CF stays unset, and both pre-registered conditions for setting it are now MET

This is the important change since 21:00 and it needs a user decision.

| condition | state |
|---|---|
| D158 (1): all four held-out cells run clean after the race fix | **MET** |
| D157 (2): `P_hat` frozen and committed with its hash before scoring | **MET** (`cf_ontime_model_frozen.json`, `payload_sha256 2dc415b7...`, `code_sha256 15aa23c0...`) |

**So the user's own conditions are satisfied and the margin still must not be set.** The reason is
structural and is declared in session B's own artefact: `cf_ontime_frozen` builds `P_hat` from the
committed gate's `by_arm` split, and that split's payload records **`warm_rows_held_out: 0`.**
Confirmed independently in the committed gate JSON, whose `by_arm` held-out block has only `all`
and `cold` strata, both n=101,498, while all 1,797 warm requests sit in the fit set.

**`P_hat` has therefore never been validated on a single warm request, and the held-out cells it
would be scored on are 83 to 91 percent warm.** The one test that would have validated the
underlying cost model on this workload is the D156 (4) gate, and it failed tonight.

**Credit where it belongs: B declared `warm_rows_held_out: 0` in the frozen payload.** It is why
this took two minutes to find rather than never, and it is the register-marking CLAUDE.md asks for.

### 3. v5-rules: the result, stated in the register that survived every correction

**v5-rules escalates 44 of 45 robot questions against its base's 24 of 45, 1.83x, plus 83,961
warm-ahead prefills at seed 5 alone.** The fate of the 20 escalations the two arms differ on:

| fate of the 20 extra escalations | n |
|---|---|
| cloud answer correct where the device was wrong | **2** |
| cloud answer wrong where the device was **right** | **1** |
| no change, of which **resolved to the device's own answer anyway** | 17, of which **16** |

**Sixteen of twenty extra escalations produced the answer that would have been produced without
them.** The device is carrying the robot task, and escalation pays only on the conjunction
device-wrong AND cloud-right AND returns-by-deadline, **hit 2 times in 20**.

**Statistical register.** Across 45 questions there are 9 discordant pairs, 5 favouring v5-rules and
4 the base: **McNemar exact two-sided p = 1.0.** Six of the nine flips are on questions where both
arms made the *same* decision, so queue noise flips 0.24 of questions while the effect is 0.022 per
question. Detecting a difference this size would need about **3,200 robot questions**, roughly 70x
what these cells carry (CONSTRUCTED from the observed discordance rate). **The finding is the
asymmetry, not the sign:** the gain is one discordant pair and needs a power analysis; the losses are
thousands of unreleased requests and do not.

**The warm chain, engine-observed `cache_path` throughout (never the belief, which is biased
conservative):** v5-rules reaches GPU-WARM on **25 of 44** released robot questions, 56.8 percent,
while `hybrid-F-lhreq-noc3` and `b7` reach it **0** times. So warmth is reached for most questions
and buys nothing, and the base is a genuine **mechanism-absent comparator** rather than a weaker
variant (confirmed structural: `release_piece` 0, `submitted_piece` 0, both cells post-fix, zero 400s).

**Rule 2, settled:** **fired and did not help** on the warm-ahead side, with the break localized to
the **warm-to-on-time** link (5 of 9 warm extras fell back to the base's device answer, and 2 of the
4 cloud answers that did arrive were wrong). **Cancelled by geometry** on the release side, where
the deadline rather than the decision settles all 11 cold cases.

**Mechanism, measured twice on different arms.** Unconditional prefill drives overlapping requests
from about 10 to about 2,000; EP-G multiplies the result about 3x. **Prefilling ahead of demand buys
cache residency and spends the engine**, which is why 57 percent warmth converts to nothing: the arm
wins in the register of cache residency and loses in the register where the deadline is decided.

**One result supports the thesis rather than qualifying it.** Targeted warming reaches warm more
often than unconditional warming, 1.7x pooled over three warm-all cells, with the direction
replicating at both seeds (about 1.3x at seed 4, 3.6x at seed 5) and the magnitude unstable.
Indiscriminate prefill thrashes the LRU pool. Reported as direction-with-unstable-magnitude:
seed 4 alone is not significant (Fisher exact p = 0.39) and the pooled version (p = 0.035) owes its
significance to one outlier cell.

### 4. What landed and is proved

- **The submission race is fixed and proved on a valid held-out cell**: HTTP 400 went from **4,244
  to 0** on the same arm, workload and seed, with the queue untouched. Stronger than D158 (2)'s third
  proof, which asked only for a replay. My `cc22429` prediction, that the fix removes the 400s and
  not the queue, holds exactly.
- **The race was also a confound on WARMTH**, not only on errors: warm robot deliveries went 1 to 6
  on that cell, because a piece whose bytes 400'd left the history cold. **Every piece-chaining cell
  run before the fix has its warm count biased downward.** The v5-rules cells both ran post-fix.
- **All three engine actions confirmed on the 32B deployment stack** (M1 warm-ahead 31x, M2 touch
  moves a history between tiers, M3 reload 15x), and **two of the three are unwired**: `_enact` sets
  `desired_tier` and emits no request, and `believed_tier` is never `host`. `desired_tier` now has a
  *measured* mechanism behind it, so the remedy is to wire it, not remove it.
- **WARM-ALL's characteristic property is verified, not assumed**: at least one release at GPU-WARM
  with `cached_tokens` > 0 in every valid cell (port rule).
- **A within-cell natural experiment, n = 1 of its kind**: on one cell, warm deliveries rose six-fold
  and 4,244 failures were removed, and correct-by-deadline did not move. Confound named, the fix
  changed both at once. `_kv0.25` has no pre-fix twin, so this cannot be replicated.

### 5. Session B's state

- **`P_hat` IS frozen and committed with its hash** (see section 2), which satisfies D157 (2).
- **`P_hat`'s zero warm held-out rows are STRUCTURAL, measured at 07:20.** Full write-up:
  `reports/study_counterfactual_warm_holdout.md`, commit `8673361`. At 06:00 I had the declaration
  `warm_rows_held_out: 0` from B's own artefact but not the cause. `cf_cost.py:63-66` sets
  `GATE_SPLIT = "by_arm"`, that split holds out the hybrids, and **all eight hybrid cells are 0.00
  percent warm at request level**. The split holds out exactly the arms that contain no warm rows,
  so it **cannot validate warm first-token prediction even in principle**. The whole 26-cell gate
  set is 1,797 warm of 345,072 requests, 0.52 percent, reconciling to the gate JSON's own totals
  within 6 requests (explained by `features()`' stricter row filter).

  So `P_hat` is fitted at 0.52 percent warm, validated at **0.00 percent structurally**, and applied
  to EP-G WARM-ALL cells that are **83 to 91 percent warm**. A **second** extrapolation sits on a
  different axis: the gate is fitted where the service is never more than **2.781 s** behind and
  applied where it is up to **478 s** behind, about 170x, on the axis its own linear `overlap` term
  is supposed to carry.

  **Check 7 passes and locates the fault.** The `by_seed` split is the positive control: it carries
  1,797 warm held-out rows at a warm first-token ratio of 0.9108. The estimator can be validated on
  warm data when a split provides any, so **the failure is the split, not the estimator**, the same
  shape as the D156 (4) gate. The remedy is therefore specific rather than more data: hold out an
  arm that produces warm rows, which among committed cells means `by_seed` or a new split over the
  WARM-ALL arms. **This is a user decision, not an analysis step.**

  NOT CLAIMED: that `P_hat` is wrong on warm or on loaded requests. Only that the committed
  `by_arm` validation cannot speak to either regime, so its held-out error is not evidence about
  the regime MARGIN_CF is scored in.
- **The deficit weighting and the p99 instrument: UNKNOWN.** B pushed **nothing during the overnight
  window**; its last commit is `023ce6f` at 2026-11-20 20:02, before 21:00. Neither I nor the H100
  heard from B. Reported as unknown rather than inferred from the files.

### 6. What is BLOCKED, and why

| blocked | on what | can analysis clear it? |
|---|---|---|
| full v5 going live | the D156 (4) gate, which FAILS | **no**, needs a user ruling on the fit set or the model form |
| MARGIN_CF | `P_hat`'s cost model never validated on a warm request | **no**, needs a gate that passes on this workload |
| M2 and M3 in the policy | `desired_tier` is write-only; `believed_tier` never `host` | no, both are policy changes |
| the warm-ahead yield (W2) | probable defect: the key is absent from `arm_stats`, value a genuine zero in 12,001 epochs | diagnosable, not tonight |
| dashcam scoring on EP-G cells | the Orin's EP-G device re-record | no |
| cascade arms | still on the 0.567 s proxy, labelled `proxy-0.567` | no |
| D97 eligibility for per-frame cells | recompute at `eligibility.py:94` | yes, not done |

### 7. PROVISIONAL and labels

EP-G budget charge is the new-token charge with the true-up deferred (D156 (3)); dashcam scoring on
EP-G cells is PROVISIONAL until the Orin's re-record; the belief-correction observer runs in
`observe` mode and changes no policy behaviour (D157 (4)); cells run before the race fix with any
piece-chaining arm are **race-affected**, and that includes the gate's own CAL1F `warm-all-lru` fit
cell (226 HTTP 400s), which is also its load outlier; `n_requests` and `n_errors` come back **null**
in `cell.json` on every warm-all cell, recorded as a **defect**, with error counts taken from
`request.jsonl`.

### 8. Corrections made tonight, recorded rather than edited away

Four, all caught before or shortly after publication, three of them by the H100 and one by my own
check:

1. **A register error**: I compared one arm's engine-observed warm share against another's internal
   belief, on different populations. **It reversed the ranking.** A coincidence hid it, both
   numerators were 25.
2. **A scoping clause withdrawn**: I proposed that warm-ahead's target state is unreachable at this
   operating point. It is reached 57 percent of the time; the chain breaks later.
3. **My MARGIN_CF n-argument was arithmetically wrong** (I conflated the warm stratum with D157 (2)'s
   population), and the cold-share figure that replaced it came from one cell, which is the same
   register error twice in three sections.
4. **The queue is created by the ARM, not by EP-G**, caught before publication this time.

### 9. For the user: decisions, each with my default

1. **The gate.** Default: **leave it. The gate fails as pre-registered, MARGIN_CF stays unset, full
   v5 does not go live.** Alternatives: refit on a fit set stratified by load (changes a
   pre-registered split, and trades the confound for a coverage gap, since the excluded cell is the
   only fit cell in the loaded regime); or change the model form, constraining the intercept to be
   non-negative and adding a queueing term. **The data points at the model form**, because a linear
   overlap term cannot describe a system spanning 0.27 s to 138 s, but it is a change to the
   instrument and needs pre-registration.
2. **MARGIN_CF.** Default: **stays unset**, because `P_hat` rests on a cost model held out on zero
   warm rows. The clean-cell p90 is available as a DIAGNOSTIC labelled not-the-margin per D158 (1)
   and I have not computed it as a margin.
3. **v5-rules in the paper.** Default: report it as the "v5 without the counterfactual" ablation with
   the economic reading leading (1.83x the escalations, 16 of 20 answered by the device anyway,
   McNemar p = 1.0), and the warm analysis second. The ablation produced one measured instance of the
   harm D151's counterfactual exists to decline, which is evidence **for** the full policy.
4. **Tomorrow's first items**, unchanged and user-ruled: belief promotion to host (D157 (4)),
   `deadline_work_at_risk` as a probable defect, the value reader at admission with `p_question`, the
   base surrogate audit, and the D156 (3) budget true-up.

## 06:00 run summary (H100): what ran overnight on GPU 2

**Last updated: 2026-11-21 06:00.** The authoritative per-cell table (correct answers delivered by the deadline, device-only
row, robot on time, SS within 2 s, dashcam, errors, engine-observed warm count, excluded dashcam instants) is
`reports/study_frozen_test.md`, section "06:00 SUMMARY (2026-11-21, H100 overnight; D156 (5) form)". The analysis is the
session D section above. Ran on GPU 2 from 17:00 to 06:00, GPU 2 never idle except the two planned engine-action breaks:
- 3 s handful at seed 4, dashcam-1f (b7, eco-llm, mooncake, edf, llf, simplestream); D151 calibration cells; the two
  CALIBRATION-1F WARM-ALL cells; the 32B engine-action confirmation (M1, M3 b685fbb; M2 e77fa65: all three PASS).
- EP-G + per-frame (`upload-pf`), race-fixed after 2b8714c: the four WARM-ALL held-out cells (all VALID by 03:43), the
  D156 v5-rules block at seeds 4 and 5 (v5-rules beside 7 arms), and the EP-G handful at seed 4 (all 11 arms; the last,
  hybrid-F-lhreq with C3, gives correct by deadline 0.35 and on time 16/20 against its C3-off twin's 0.45 and 8/20, so the
  RECENT fallback buys deliveries that are wrong, as pre-registered). The EP-G handful at seed 5 continues past 06:00.
- Full v5 did NOT run: the cost-model gate FAILS (session D, 6dc49db). One INVALID cell (warm-all-lru s5 first attempt,
  harness link reset) was re-run once per D143 and the rerun is valid. No foreign process on GPU 2 all night.
- Incidents (details in the report): `import hybrid` broken by 5d7c084 (fixed e2c8933 / e7b4dda); the submission race
  (fixed 2b8714c, 0 HTTP 400 on every later cell); scorer version skew (f1d32c7 mid-run); null n_requests / n_errors in
  cell.json on several arms (DEFECT, counts from request.jsonl).
- For the user: the confidence-injection wiring change (flagged earlier) now decides five cascade arms' single-shot results
  through their missing-field default, so those rows are not measurements of the arms; whether -reactive and -off (run
  before 2b8714c) count as "clean after the fix" for D158 (1); and a controlled load sweep if the saturation knee (4,512 to
  5,192 uncached tok/s, session D) is to be located rather than bounded.

Last updated: 2026-11-20 21:30 (**StudyORIN-REC part 2 pushed.** On the full S-EMBER recall suite the 4B device model scores 0.27-0.29 across both representations and both splits, a few points below the A6000 proxy (0.33-0.38), and agrees with the proxy's letter on about half the questions per split (0.50-0.54, never pooled). RICH history does not beat RECENT on the device (D2 vs RECENT within CI on both splits) while costing ~2x the TTFT (RECENT cold TTFT p50 3.32 s, D2/RICH p50 6.86 s, p90 16.83 s) and pushing 6 EVAL questions over the 32,768-token context, reported as over-context and never truncated. Parity control passed (RECENT prompt_tokens p50 5,524 = committed ACC2 median). COLD run throughout. StudyORIN-REC part 1 and WARM pushed earlier tonight. Next: StudySS2 re-record + RefSpatial rescore.) PREVIOUSLY 2026-11-20 22:15 (**StudySS2 device-confidence re-record + RefSpatial rescore pushed, all controls pass.** The 357 single-shot recall questions that had no answer probability now have one: 1,042 items re-recorded on the committed SS2 device config (orin3_serve.sh verbatim, released processor, cap 9) with logprobs on. Equality control PASS-in-intent PROVISIONAL (1,040/1,042 byte-identical; the 2 diffs are prefix-cache cold/warm nondeterminism, one score-invariant and one a 0.25-nat MCQ near-tie that flipped to the correct letter). Confidence table: MCQ letter-mass median 0.986, geometric-mean median 0.848. RefSpatial rescore control: device rows moved 0 (PASS), cloud moved 4 (0.3714 to 0.3787), 277 masks hashed. Wiring proof: the field reaches all 5 reader arms and the characteristic decision fires, control b7 byte-identical, but recall coverage stays 20/377 because injecting the new single-shot confidences into the harness query objects is a separate methodological wiring change, FLAGGED for the user and NOT applied overnight.) PREVIOUSLY 2026-11-20 18:40 (**D153 to D155 land; the dashcam format changes under every arm and the v5 gate still fails.** D153 fixes the dashcam format BY THE TASK rather than by StudySH-EP's verdict: every dashcam query uses D148's append-only episode context (EP-G), never one frame per call, with a 3-frame floor excluded identically for every arm. **The live contract is still one frame per call and `bodies.py:148` RAISES on a multi-frame monitor body, so every committed cell is `dashcam-1f` and no EP-G measurement of any policy exists yet**; the H100 is labelling its current cells accordingly and has armed `runs/EPG_ARGS` to switch at a boundary. Measured for the floor decision: EP-G already carries NINE frames at the first decision instant in 287 of 300 clips because the StudySH-EP manifest built a 4 s pre-roll from 165 frames that are NOT in the committed D91 store, so in live2, whose grid starts at 3.0 s with no pre-roll, every episode starts at ONE frame and the floor costs 2 instants per episode rather than 0.15 percent. The refresh is the largest open number: D153's literal fresh-context-with-no-carry-over gives a median 10 frames per request and excludes 1,429 of 13,193 instants, against a sliding cap's 21 frames and 378. **WARM-ALL AS BRIEFED IS UNEXPRESSIBLE**: warming AHEAD of a question was rejected by the validator, so the arm issues 0 prefills and is behaviourally b7 (Rule 2 unexpressible, not a negative). A user-ruled patch now adds `Observation.live_sessions`, making proactive warming expressible for the first time, with a 50-arm before/after prescreen running as its byte-identity proof; `warm-all-lru-reactive` passes all four proofs meanwhile (645 prefills against the base's 0, Step 2b 1,394). **Six KV-cache baselines publish a proactive mechanism none of them could express until tonight**, so every committed comparison against them was against an adapter that could not do what its paper says; D155 (5) implements them per card, mooncake first. **The D151 (6) cost-model gate FAILS** because warm is confounded with arm, so D154 (2) leaves MARGIN_CF unsettable and NO v5 cell may run. StudyORIN-REC part 1 measured the device at DEV 2/28, closing G7 and removing the tie that made D152 (2) look derived, so D155 (4) imposes it as a user rule; D149 (4)'s acceptance test now discriminates at warm/keep. D155 (3)'s by-deadline headline changes no ranking at 0.146 to 0.225 s device latency, classified unexercised. StudySH-EP is CLOSED, one frame, fired and did not help. Policy v5 assessment: 1 of 27 elements dry-proved, 0 live-validated, and the critical path cannot complete before 06:00.) PREVIOUSLY 2026-11-20 18:40 (**StudySH-EP CLOSED and the policy v5 gate FAILS.** StudySH-EP is final: dashcams stay one-frame, classified FIRED AND DID NOT HELP. The 32B beats the 4B in every condition with a CI excluding zero, but H1's second half fails everywhere and no 32B condition differs from its own C1; H2 holds as DETECTION COUNT (15 of 15 cells) and fails as LEAD TIME (14 of 15 CIs include zero), so the 32B detects crashes the 4B never detects rather than warning earlier; H3 holds decisively, warm episode context costing 0.1324 s against one frame's 0.1302 s while the same breadth COLD costs 2.9x, which is the physical component of Context Inertia measured on the dashcam workload. Two results the hypotheses did not ask for: multi-frame input hurts the 4B at the two highest frame counts (-0.060, -0.072, both CIs excluding zero) and helps the 32B at none, so the two LARGEST 32B-minus-4B gaps sit on the two conditions nobody should adopt and ranking by the gap column selects exactly the formats that damage the device. Section 12.5 pre-registered that EP-G would either leave the verdict alone or widen the gap by the 4B degrading, and named the latter as a trap rather than a reason to adopt; the landed cell is the latter. **THE D151 (6) COST-MODEL GATE FAILS, so v5 does NOT go live.** Decode over-predicts by 25 to 32 percent held out, and the cause is not the recorded scarcity of warm requests but that WARM IS CONFOUNDED WITH ARM: arms that rebuild histories go warm and show hundreds of thousands of engine prefix hits, arms that do not show zero of both, so the warm coefficient is fitted on edf and llf and applied to arms that never go warm. Only WARM-ALL + LRU can identify it. Also recorded PROVISIONAL: `telemetry_cached_tokens` is positive in none of 18,738 residency rows, which is NOT a broken write (it is logged on the history-build path only), but the belief does understate residency on partially built histories by construction, as `coordinator.py:745-752` already states; wiring it will not by itself fix that. `believed_tier` is never `host` in 39 cells, so reload-from-host has no observed trigger state. Sessions A (spec v5, value readers) and C (engine actions, WARM-ALL) landed or are running on flash; B waits on C's interface note. New E-id rows: StudyPOLICY-V5, StudyV5-ENGINE, StudyORIN-REC, StudyD14b-FULL.) PREVIOUSLY 2026-11-20 07:30 (**StudyFROZEN-test overnight: three-type grid running; at 16 devices on seeds 4 and 5 hybrid-F-lhreq leads every baseline (robots 36 vs 33 of 45, SS 682 vs 652 of 713), F6 does not beat F and breaches the 100 ms decision period in 2.7 percent of periods; morning summary in reports/study_frozen_test.md; four user rulings pending.**) PREVIOUSLY 2026-11-20 (**StudyPOLICY-F FROZEN, with three findings that change what the freeze means and three questions for the user.** D143 rulings A and B are applied and the four freeze proofs are in `results/orchestration/live2/hybrid/policy_f_proofs.json`. (1) **THE VALUE TERM IS DECISION-INERT.** The value and quality tables are read in exactly one place, C1's ordering index, and a Step 4 control moves ZERO decisions of 16,361 under a flat table, a 100x dashcam skew, a 1000x SS skew and a 10,000x robot inversion. Dashcam items carry one constant value and one constant work so C1's order is identically EDF, and every recall item is kept unconditionally by the cap, so C1 reaches only the unexpressible `order` channel: CANCELLED BY GEOMETRY, not unexercised. Consequence: ruling A's LH-REQ swap, the 4.4x half-one correction and the SS ordering flip all change a quantity the frozen policy does not read, and the SS flip must NOT be read as evidence about single-shot against robot recall. (2) **C6 WAS DEAD in every -lhreq cell** until this run: ruling A's DEV-fit class covered 4 of the 5 (representation, tier) conditions the escalation path reads, raised MissingEvidence on cloud RICH and device N1, and `_c6_prepare` swallowed it into a counter while `live2_describe` still reported c6=True. Fixed by re-raising MissingEvidence and by two PROVISIONAL substitutions that both understate the cross-tier gain; C6 now fires 254 times and moves 3 decisions, which clears Step 2b and says nothing about whether it is worth a policy-core mirror every period. Two regression tests added, one of which would have caught it at the first cell. (3) **The SS at-risk flag is now constant at never** (0 of 356 to 717 SS requests per cell): ruling B's 0.6 s against a 2 s deadline is the same always-on defect with the sign reversed, recorded and not acted on. Also corrected: `_differing` counted LOG POSITIONS, not decisions, so proof 2's first numbers were in the wrong register (C6 11,794 positional against 3 actual); both metrics now ship, labelled. Proof 1 byte-identical on all 4 two-type cells, proof 3 at 30 of 30 dry cells, fleet suite 234 of 234, test_hybrid 7 of 7. **FOR THE USER:** (a) 20 devices offers 97 percent of the committed 15.10 req/s one-frame peak, which is what the H100's transport errors are (StudyMOT1 and StudyD7 precedent), so 16 and 18 are the feasible pair and 18 holds the same pooled robot counts as 16; (b) the over-context question in LH-REQ session 1848337166005249 needs a counting rule, since StudyRH8's exclusion rested on it being identical across policies and here it is not; (c) whether an inert value term is acceptable in a frozen policy (`reports/study_policy_f.md` section 11).)

# FM-switching — Project Status

Last updated: 2026-11-19 (later 6) (**LH-REQ TRACE OPTION READY, and the run length is fixed by overnight rule 1's FALLBACK.** `DS.robot_sessions("eval"|"lh_req")` plus `generate_trace(robot_question_set=...)`; ids are READ from the committed `lh_req_definition.json`, never re-derived, folded on BOTH sides and asserted against the committed `per_split` totals, which is the only control that catches the case trap that caught two sessions independently (folding one side gives EVAL 43 / DEV 20 with 34 unmatched, and 34 is exactly the count of upper-case LH-REQ ids). Returns 69, the committed EVAL figure, per D143 ruling A. **`s2` MUST NOT COMMIT A SECOND LH-REQ FILTER:** this one is on origin, and two independently written filters over the same 97 would differ somewhere with nothing to catch it; any change goes here. Default path proved BYTE-IDENTICAL on five cells against origin's `fleet/` (digests `80b376c550007686`, `9bdb6450ea039e94`, `94c4193f5e51b1d3`, `4cfb07914aa353df`, `a0c69109477e5ebb`), with the n=12 robot counts 21 at seed 0 and 27 at seed 4 reproducing the committed `study_hybrid_live.md` figures as a positive control; `test_live2_fleet.py` 234 of 234, check (h) included. **The pool is 69 questions over 51 sessions** against EVAL's 602 over 164, about 1.35 questions per session played at a 600 s median session, so the pooled count is governed by how many sessions a device can chain through. **REPEATS ARE ZERO in all 84 cells measured** (pooled equals distinct everywhere, asks per distinct 1.0), so the pooled count is not inflated by re-asking. At 600 s, **24 of 28 cells are below D82's minimum of 20 pooled**; only n=28 and n=32 clear it. **RUN LENGTH: 1200 s, fallback in force** - rule 1's 8 cells (12 and 16 devices, seeds 0/4/5/6) do not all reach 20 at 600 s (all 8 fail), 900 s (7 of 8 fail) or 1200 s (3 of 8 fail: n=12 at seeds 0, 4 and 6 with 15, 16 and 17), so 1200 s is used and the robot result is labelled NOT MEASURABLE in those three cells. Reported but NOT applied, since rule 1 fixed the candidates: **1800 s clears every cell at every size, 12 devices included, minimum 21**, and is the shortest length in evidence that removes the label. Pool coverage stays low either way: the best 600 s cell touches 0.32 of the 69 questions. **Quality table committed as an INPUT FILE** (`lh_req_quality.json`), fitted on DEV and drawn on EVAL per ruling A, Wilson intervals beside every point estimate; four controls pass including the committed `d2_acc` 45.3608, `recent_acc` 21.6495 and D87's 845 / 277 / 32.781 percent. **The half-one correction is 4.4x, not 7.3x**: the 7.3x compared `TRACE_MIX`'s +3.23 pp against the all-97 gap of +23.71 pp, but ruling A fits on DEV, whose gap is +14.29 pp. Direction and conclusion unchanged, magnitude corrected (`reports/study_lh_req.md` section 4).)

Last updated: 2026-11-19 (later 5) (**StudySS2 DEVICE PASS COMPLETE (Jetson Orin, Qwen3-VL-4B under
vLLM, StudySS1 config). Three CPS single-shot candidates; device side + shared benchmark kit only,
cloud 32B gap / qualification pending on the H100. Licence STOP gate: RefSpatial-Bench Apache-2.0 and
RealWorldQA CC BY-ND 4.0 cleared (images not committed); CODA-LM SKIPPED because its images need
agreeing to CODA's CC BY-NC-SA + Huawei non-commercial / no-redistribution terms on download. DEVICE
4B: RefSpatial-Bench 277 point-in-mask 0.251 [0.200,0.305] (location 0.335 / placement 0.230 / unseen
0.169; by reasoning step 0.433 at step1 falling to 0.000 at step5), RealWorldQA 765 exact match 0.655
[0.621,0.689] (MCQ 0.637 / free-form 0.679). A Step 2b check BEFORE the sweep caught a RefSpatial
scoring artifact: Qwen3-VL emits NORMALISED 0..1000 point coordinates, not absolute pixels; the
default would have reported a false 0.000 for the 4B. COORD_MODE=norm1000 locked and applied to both
tiers. Kit pushed as ss2_bench_kit.py because a parallel session already owns ss2_kit.py (its CODA-LM
1..10 judge parser); the two coexist. 0 errors on 1,042 items, full run 22 min, disk flat.
reports/study_ss2.md.**)

Last updated: 2026-11-19 (later 2) (**StudyEGOLIFE-feas, annotation-only, NO VIDEO, for D139. HEADLINE:
THE USABLE COUNT IS 3 AND THE RULE FIRES - OFFLINE CORROBORATION ONLY. Applying the rule as written (gap >
2 min, D2 history <= 19,400 tokens, no audio, no names) to the same-day single-target analysis set: 281 ->
281 -> 20 -> 15 -> 3. The margin is not close: an upper bound that repairs every excluded multi-target row
most favourably gives 4, and a 32,768 budget gives 5. `need_name` IS THE BINDING FILTER, NOT THE TOKEN
BUDGET - 197 of 281 questions need identity recognition and only 34 of 281 need neither audio nor names.
Coverage, reported with its denominator because 43.8 percent of rows are excluded: of 500 rows, analysis 281,
`time_list` 36, cross-day 170, MALFORMED 13 - and the 13 pack several timestamps into the single `time`
string, so a reader taking the first 8 characters gets a plausible gap from a malformed field and raises
nothing. EgoLifeQA is a MULTI-HOUR benchmark, not a minutes-scale one: 207 of 281 beyond 30 min, median 1 h
46 m, and over all 500 rows the median question would need 951,241 D2 tokens, 49x budget. Tokens taken from
live2's own `d2_batch_tokens` rather than re-derived: 20 of 46 fit under 19,400 and under the 19,381
breakeven, 39 under 32,768; 19.4k buys 7 min 10 s of D2 history. Disk at 14.5 MB per 30 s clip: 0.55 GB for
the 3 usable, 9.74 GB deduplicated for all 46, neither fetched. MIT and UNGATED, so the StudyOEQA gate does
not fire. The `3f2002c` GRAVEYARD closure answered a DIFFERENT question and is recorded, not re-litigated;
what carries forward is that recurring failure mode 2 is AGGRAVATED, because the dense caption layer is
CHINESE-ONLY. SEPARATELY, a check on the LH-REQ headline in flight that CORRECTS THE PREMISE IT WAS GIVEN:
S-EMBER is FIVE-option, so chance is 20.00 percent and not 25. RECENT's 21.65 percent is 21 of 97 against
19.4 expected, exact binomial p = 0.381, INDISTINGUISHABLE FROM CHANCE but 1.65 pp ABOVE it, not below;
D2's 45.36 percent is p = 1.5e-8. State the gap as 'D2 is above chance where RECENT is not', never as
'RECENT is below chance'. Report `reports/study_egolife_feas.md`.**)

Last updated: 2026-11-19 (**StudyLIVE2-pilot MORNING REPORT (section 8): overnight baselines on seed 0 break between 8 and 10 devices for every arm that passes at 8; no policy runs (v1.3-fast failed its own piece test, v1.4-fast not released); transport ReadErrors at 16 devices for always-send arms need a ruling. STOPPED for review.**)

Last updated: 2026-11-18 (later 9) (**StudyLIVE2-pilot INTERIM report on the D114 build (section 7): baselines done; edf's 8-device break comes from D114's C_inflight 4 (C_inflight 8 passes like always-cloud FCFS); policy-core v1.0 superseded; waiting for v1.2-fast release (D125). Pilot results are never round-1 results.**)

Last updated: 2026-11-19 (later 4) (**StudySS1 DEVICE PASS COMPLETE (Jetson Orin, Qwen3-VL-4B under
vLLM, StudyORIN3 config, real inference; D136): the single-shot dataset-selection benchmark kit is
built and the device 4B side is measured on both full sets, 0 errors on 5,019 questions. VizWiz-VQA
val (4,319) VQA accuracy 0.659 [0.645, 0.672] (answerable-only 0.575; unanswerable 0.837, yes/no
0.813, number 0.654, other 0.556); EgoThink (700) containment match 0.471 [0.434, 0.507]
(Localization 0.75, Object 0.64, Reasoning 0.49, Forecasting 0.45, Activity 0.32, Planning 0.09, the
last a strict-match floor on long answers). TTFT p50 0.86 s (VizWiz) / 1.47 s (EgoThink); full run
113 min, under the 6 h gate. Licences cleared (VizWiz CC BY 4.0, EgoThink Apache-2.0). Per the user
disk ruling Mistral-7B was NOT downloaded: the EgoThink open-judge (scorer a) is DEFERRED to flash
(Mistral judge on EgoThink plus OpenEQA), and the H100 runs the identical kit with the 32B so the
device-vs-cloud gap and the SS qualification verdict are decided later; NO dataset is qualified yet.
Serve deviations recorded (gpu_mem_util 0.22, max_model_len 8192 after clearing a 29 GiB orphaned
engine core; FLASHINFER_DISABLE_VERSION_CHECK=1 with FLASH_ATTN). Free disk flat (no download).
Report `reports/study_ss1.md`; kit `experiments/casestudy/ss1_*.py`; data `results/casestudy/study_ss1/`.**)

Last updated: 2026-11-19 (later 3) (**StudyACC2 COMPLETE (H100): history help not detectable above 19.4k tokens; committed RECENT and D2 quality tables overstate live2's formats, reports/study_acc2.md.** **StudyAOI-spacing COMPLETE (Jetson Orin, CPU only, offline,
committed data only): THE SPACING OF CLOUD CHECKS DOES NOT MATTER at a fixed cloud-served budget on
the Nexar metric, so the per-instant opportunity model needs no age-of-information spacing term. At
each budget f in {0.10, 0.25, 0.50, 0.75} the three event-agnostic patterns (EVEN, CLUSTERED k in
{2,4,8}, RANDOM; 100 seeds) are indistinguishable on streaming AP and challenge mAP at every
horizon: the largest paired difference is 0.006 challenge mAP against a 0.104 device-to-cloud gap
(streaming AP differences at most 0.0003), almost every paired clip-bootstrap CI includes zero, and
the one resolvable loser (CLUSTERED_k8 at f=0.25, -0.006) is confounded by a 0.207 achieved budget.
REAL NEGATIVE (Rule 2): the cloud==device negative control collapses every schedule onto
device-only exactly, and FRONT-loading at f=0.5 reaches challenge mAP 0.602 against BACK-loading's
0.507, so PHASE relative to the event matters by about 0.10 mAP while the pattern does not, and no
event-agnostic rule can exploit phase without a runtime event signal. The cloud-minus-device gain
autocorrelation is 0.44 at 0.5 s, 0.30 at 1.0 s and 0 by 6 s, a redundancy timescale of about 0.5
to 1.0 s. Scorers imported unchanged (StudyE9b ApEngine, StudyE9c/E9d Challenge); scores calibrated
per tier out of fold with the D105 FINAL maps; zero-latency reference arms reproduce StudyE9c within
5 percent. Report `reports/study_aoi_spacing.md`; data `results/dashcam/study_aoi/aoi_spacing_results.json`.**)

Last updated: 2026-11-19 (later 1) (**MOTIVATION CORRECTION, D135, recorded here so it is not
re-quoted: the +17.5 pp history benefit holds ONLY for questions whose evidence lies outside the
recent window, about 12 percent of them. Across all questions history HELPS 8.05 percent and HURTS
6.86 percent, net +1.18 pp with a CI of [-1.42, +3.79] that does not exclude zero. That figure is
what launched Part C's accuracy-column rationale. StudyEVNEED also finds that NOTHING in the
candidate set predicts the HURTS flow (coverage scores 0.068 precision against a 0.0714 base rate,
below chance), that the per-category lever dies on DEV-to-EVAL, and that sending RECENT instead of
full history would save 95.6 to 95.8 percent of recall GPU time and rescue 28 of 28 infeasible
questions on the 10/12/14 band - a lever that cannot yet be converted into a policy because both a
runtime signal and a long-history accuracy measurement are missing. Report
`reports/study_evidence_need.md`. The six protocol amendments this work earned were ACCEPTED under
D135 and are now in CLAUDE.md.**)

Last updated: 2026-11-19 (**StudyCOVEX-harden, session 2, D124 to D134. THE CROSSOVER IS LOCATED
AT 10 TO 12 DEVICES and is sharp, with all four dev seeds transitioning together: llf falls 0.81
to 0.41 and edf C=8 0.86 to 0.17 on robot on-time, while COVEX is flat and has no collapse. On the
D131 bar, which includes the ported published arms, COVEX LOSES AT EVERY SIZE on both axes and
meets the D71/D82 capacity conjunct in 0 of 28 cells against eco-llm's 10. The IDLE-GPU
FEASIBILITY CEILING is 0.8871 at 32 devices and below 0.90 in 11 of 28 cells, so under D132 the
headline robot target is p = 0.90 over FEASIBLE questions; that correction nearly doubles every
baseline's capacity passes and moves COVEX 0 to 0, so its gap is scheduling and not arithmetic.
The robot axis is a QUEUEING problem: identical 38 recall requests at identical ~2.4 s service
differ only in delay against a 5.0 s deadline, 2.34 s for eco-llm against 5.81 s for llf. SIX DEAD
OR ABSENT CHANNELS catalogued: the action `order` field, `desired_tier` (written twice, never
read, so live2 models KV OCCUPANCY but not KV PLACEMENT), `RecallAction.representation` (now fixed
at e924005), B2's z[RC], RCprio, and state value which cancels exactly between branches in 12,898
of 12,898 candidates. TWO CAVEATS ON EVERY DRY ROW: no memory limit was enforced, and this robot
workload is HISTORY-INSENSITIVE (recent_covers_frac 0.8852, full history worth +1.18 pp overall
with a CI including zero), the opposite of LoCoMo's -24.1 pp. Report
`reports/study_covex_hardening.md`. Next: the eco-llm bar check across e924005, Part D refresh,
and the EXPERIMENTS.md verdicts, which are DRAFTED FOR THE USER AND NOT SET.**)

Last updated: 2026-11-18 (later 9) (**D114: the EDF family is now WORK-CONSERVING, releasing from the head of the same EDF order while in-flight cloud requests are below c_inflight = 4, pre-registered before the code as a BASELINE change, so every committed edf, edf-piece1024 and edf-piece2048 number is superseded. The 10/s ceiling is gone (per-period max 1 to 4) but requirement 3 is a NEGATIVE: robot questions released before their deadline fell from 11 to 9 of 29, because D114 removes the release ceiling and not EDF's deadline order, so the freed capacity goes to dashcam instants; a per-class share or slack order is named and NOT applied, for the planner to rule. Spec 3.5 still reads "one unit at a time", so arm and rollout now agree and both differ from the text: an amendment or recorded deviation is owed. All five non-EDF arms byte-identical over 30 of 30 grid cells and 5 of 5 replays; D97's entry points under D101 are UNCHANGED at 5 / 8 / 14. Next: the H100's acceptance rerun and the pilot.**)

Last updated: 2026-11-18 (later 8) (**StudyLIVE2-harness ADDENDUM ACCEPTED on the real 32B: answers leave at their first token and requests are stamped at the wire, so emulator lateness p99 <= 0.17 ms in edf 8 / 64 and policy-core 8 / 64 and policy-core's slowness shows as submit delay. Next: StudyMOT2-dayinlife, then the StudyLIVE2-pilot rerun from Step 1.**)

Last updated: 2026-11-18 (later 7) (**StudyMOT1-dayinlife AMENDMENT 3 COMPLETE: at light load (8 dashcams) chunked rebuilds serve both the fleet and the robot, so the best way to serve the robot's question differs in each cell of the light/heavy x tight/roomy grid; the tight-host host-warm prediction failed (PARTIAL or COLD in 5 of 5). Figure data results/motivation/mot1/mot1_figdata_amend3.json.**)

Last updated: 2026-11-18 (later 6) (**StudyLIVE2-pre Part 1 extension: the S-EMBER D2 JPEG store now covers every EVAL session to its end (6,437 new frames, 38,579 total; source re-extraction byte-identical on the overlap; E10a check unflagged). Next: StudyLIVE2-pilot rerun from Step 1 once flash's harness addendum is on origin.**)

Last updated: 2026-11-18 (later 5) (**StudyMOT1-dayinlife AMENDMENT 2 COMPLETE: with a roomy 256 GiB host a host-warm robot history costs the 20-dashcam fleet nothing and the robot answers in 0.69 s (cold one go: 59 missed instants, 3.56 s; 1,024 pieces: 0 missed, 6.87 s); with the tight 27 GiB host the prepared history is already cold by the question (5 of 5, as predicted). Figure data results/motivation/mot1/mot1_figdata_amend2.json.**)

Last updated: 2026-11-18 (later 4) (**StudyMOT1-dayinlife COMPLETE (amended design): with 20 dashcams monitored at one request per 2 s each, one cold 11k robot rebuild done in one go costs a median 57 missed dashcam instants in a 5.5 s burst across the whole fleet; 2,048-token pieces cut it to 24, 1,024-token pieces to 0, and the robot's answer moves from 3.5 s to 5.9 / 6.8 s. Figure data for the Orin in results/motivation/mot1/mot1_figdata.json. Report reports/study_mot1_dayinlife.md.**)

Last updated: 2026-11-18 (later 4) (**StudyFIG1-motivation COMPLETE: paper motivation figures M1-M6 (7 files) built from committed results only, no GPU/model/new measurement; every annotated number cross-checked against its source report (per-figure JSON, all ratios ~1.000). Report `reports/study_fig1_motivation.md`, scripts `plots/motivation/`, outputs `figures/motivation/`.**)

Last updated: 2026-11-18 (later 3) (**StudyMOT1-dayinlife STOPPED AT N SELECTION: at a 0.5 s monitoring cadence even 8 dashcam streams (16 requests/s) exceed the 32B's 15.1 requests/s one-frame peak, so no grid point was >= 99 % on time (N = 8: 11.7 %). A feasible fleet size or cadence is the user's decision. Report reports/study_mot1_dayinlife.md.**)

Last updated: 2026-11-18 (later 2) (**StudyLIVE2-pilot STOPPED AT STEP 1: the first real-server cell (edf, 8 devices) failed the harness lateness requirement (emulator p99 511.6 ms > 50 ms) while passing every other end-to-end check; the request path blocks the single-process emulator loop. Needs a harness fix on flash before the pilot can run. Report reports/study_live2_pilot.md.**)

Last updated: 2026-11-18 (later) (**StudyLIVE2-pre Part 2 COMPLETE: dense calibration re-run on the committed StudyD3 scored body (42,014 of 42,014 scored) and confirmed byte-identical to the live coordinator's body after StudyLIVE2-fix2; calibration FINAL (32B a 0.138, Orin a 0.133, 5-fold by clip). The pilot's preconditions are checked next.**)

Last updated: 2026-11-18 (**StudyENG1f-disk COMPLETE (h100nvl, overnight): a disk tier for computed KV works on vLLM 0.31.0 with the in-tree fs tier and is numerically equivalent; a disk reload costs 0.36x to 0.43x of a recompute and imposes almost nothing on others under load, but concurrent disk loads are bandwidth-bound (4 at once: 3.53 s each, slower than one recompute) and the write-through raises ordinary TTFT by 18.8 % at P40; verdict D2 by the pre-registered concurrency rule. StudyLIVE2-pilot did NOT run: its preconditions (StudyLIVE2-fix, design-log D98 to D105, LIVE2-pre Part 2 calibration) were never met overnight. Report reports/study_eng1f_disk.md.**)

Last updated: 2026-11-17 (later 9) (**StudyLIVE2-pre (h100nvl, overnight): Part 1 PASS, round-1 JPEGs encoded once and stored (42,014 Nexar instants, 32,142 S-EMBER D2 frames, no E10a quartile flagged; input parsing an OVERNIGHT DECISION, PROVISIONAL); Part 2 dense calibration STOPPED, because the live coordinator's monitoring body records no cloud score; Part 3 cache isolation PASS on the real engine (27 GiB round-1 server). The pilot waits for StudyLIVE2-fix (a scored monitoring body) and Part 2. Report reports/study_live2_pre.md.**)

Last updated: 2026-11-17 (later 8) (**StudyENG1e-chain COMPLETE (h100nvl GPU 2): H-gap SUPPORTED in all 16 chain cells in both injection modes; every piece of a chained rebuild runs in ONE engine step and the engine serves queued background work in the 0.11 to 0.40 s gaps between pieces, so arrivals wait for the current piece, not the chain (rho_b vs chain end 0.06 to 0.26) and chains impose 8 to 52 % of mono's delay; H-merge mostly PARTIAL (background prefill in 13 to 29 % of piece steps, 43 to 79 % at S4). The per-step add-on FAILED its unloaded overhead gate and PASSED at P40; outputs labelled. Data for StudyPOL6 Part B. Report reports/study_eng1e_chain.md.**)

Last updated: 2026-11-17 (later 7) (**StudyORIN3-vllm COMPLETE (Jetson AGX Orin, native vLLM 0.20.0+cu126, BF16 Qwen3-VL-4B-Instruct, serial max-num-seqs 1, clock pinned): THE DEVICE UNDER vLLM MATCHES THE H100 4B ALMOST EXACTLY, SO StudyORIN1's ~1-LOG DEVICE SCORE GAP WAS A llama.cpp-vs-vLLM SERVING-STACK ARTIFACT, NOT DEVICE FIDELITY.** Part 1 (6,010 StudyD3 DEV N=1 + 2,000-request D14b sample, integer-second subset): vLLM-Orin vs H100 vLLM 4B Pearson 0.9962 mean +0.004 (d3dev) / 0.9958 (d14b); vs llama.cpp-Orin 0.9417 +0.262, which reconciles ORIN2's llama.cpp-vs-H100 -0.2576. The vLLM-Orin Platt map (0.114703, 1.141292) reproduces the H100 4B map (0.114603, 1.140751), so StudyCTRL1c's H100 calibration is reusable on the Orin under vLLM (it was not under llama.cpp 0.114932/1.174287); tier residual -0.0178 (ORIN2 -0.0171); challenge AP stack-invariant (0.5695 / 0.5728 / 0.5682); 0 null/neither, clock pinned, prompt_tokens 378 all; warm-header TTFT p50 0.255 vs llama.cpp 0.471 s, cold check -1.65% (<5%, immaterial). Part 2 (warm recall, StudyORIN2 design, 11k/28k, 20 DEV questions): efficient prefix-cache (99.4-99.8% hit, verified via /metrics since vLLM 0.20.0 omits cached_tokens from the OpenAI API) TTFT p50 0.657/1.596 s vs re-send recompute 5.861/23.917 s = 8.9x/15.0x. THE EQUIVALENCE GATE IS A PRE-REGISTERED FAILURE (0.05 nats, NOT changed) that revealed a real property: vLLM's prefix-cache path is NOT output-identical to recompute (first-token drift p50 0.222 / max 0.451 nats; top-20 identical 31/40; answers 39/40, one flip; within-launch cold-vs-warm 0.251 nats; server self-jitter 0.0). The device warm-recall baseline used elsewhere (D61) stays the StudyORIN2 in-process llama.cpp harness (faster and output-equivalent within 0.15 nats); the vLLM numbers are a serving-stack sensitivity result. Native install required five documented workarounds (jetson torch 2.11.0+cu126, libcudss via nvidia-cudss-cu12, xgrammar 0.1.32 vs apache-tvm-ffi 0.1.9 pin, torchvision 0.26.0, FLASHINFER_DISABLE_VERSION_CHECK=1 with FLASH_ATTN as the active backend). Open follow-up (deferred): whether a different vLLM attention backend / no chunked prefill / fp32 logits yields a numerically exact cache path. `reports/study_orin3_vllm.md`.)

Last updated: 2026-11-17 (later 6) (**StudyPOL6-chain PART A ADDENDUM (flash, CPU only): A CONTRADICTION BETWEEN TWO COMMITTED REPORTS IS RESOLVED BY MEASUREMENT. StudyPOL5 SECTION 1.5 IS RIGHT, StudyPOL6 PART A SECTION 6 WAS WRONG, AND pol4 OVER-MERGES RATHER THAN FAILING TO MERGE.** Asked by the user before Part B. pol4 is deterministic and its own step log names the requests prefilling in each step, so this was settled by reading its output rather than either report. On StudyENG1c Part D FIT, pol4 shares a piece's step with a background prefill in 54.98 per cent of chained piece1024 steps (497 of 904) and 69.31 per cent of piece2048 steps (341 of 492), against 2.05 per cent for mono11k; pooling each variant's n_parts==1 trials gives 52.80 and 65.35 per cent, so StudyPOL5's 54 and 66 per cent lie inside the range the two plausible denominators span and its 4 per cent mono figure is within two points. StudyPOL6 Part A's claim that pol4 never merges was an INFERENCE from reading EngineSim._schedulable stated as a measurement; the erratum is in StudyPOL6's report, inline at every occurrence plus section 11, and in pol6_engine.py and pol6_terms.json (the superseded wording kept under statement_erratum). StudyPOL5 gets a provenance note only (section 1.5a): its three figures were typed into its report and are NOT in its committed pol5_diagnosis.json, so its exact denominator is unrecoverable, and the measurement is now a committed result file. NEW FACT NEITHER REPORT HAD, WHICH INVERTS THE MECHANISM: pol4 admits up to 6, 8 and 21 prefills into a SINGLE step against the engine's observed maximum ctx_req of 2, so it merges more often AND much wider than the engine (derived 40 and 48 per cent of piece steps carry other prefill tokens). Over-merging into an over-long step AMPLIFIES the granularity error instead of offsetting it, since the step's whole duration is charged to every request merged into it, which matches the direction of the residual (+265.1 s on the with-arm of the busy position); restated as H-granularity with H-OVERMERGE, and what Part B must fit is not whether to merge but how many prefills a step may hold and how long that step then takes. LEFT OPEN: the ENGINE itself merges on ENG1c chains (derived 40 to 48 per cent) while StudyENG1d measured 0 of 248 in-window arrivals admitted, with uuid image references against image bytes, and the chain's ~45 ms request cadence, as the two untested candidates; that is exactly StudyENG1e's mode B against mode A, and the ENG1c side is a DERIVED proxy against ENG1d's measurement, not two measurements. NOTHING IN PART A SECTIONS 3 TO 5 CHANGES: the gaps, pol4's own simulated gap time, the chain-span agreement to 1 per cent and the 89 / 10 per cent position decomposition all stand, and H-gap remains contradicted as an explanation. Nothing fitted, nothing frozen, pol4 still the frozen and default model; 357 tests pass (7 new pinning the corrected claim); all 12 T0b freeze md5s verified. PART B IS RE-SCOPED BY THE USER to the in-step residual, per injection mode, and is NOT STARTED: awaiting StudyENG1e-chain's commit and the user's go. Report: reports/study_pol6_chain.md section 11.)

Last updated: 2026-11-17 (later 5) (**StudyPOL6-chain PART A COMPLETE (flash, CPU only): THE INTER-PIECE GAP IS REAL AND IS NOT WHAT THE MODEL GETS WRONG. H-GAP IS CONTRADICTED AS AN EXPLANATION, 89 PER CENT OF THE OVER-PREDICTION IS IN-STEP, AND NOTHING WAS FITTED OR FROZEN.** StudyPOL5 section 3A recorded, as an untested hypothesis, that a chained rebuild's pieces leave the engine free between them and that a model treating the chain as contiguous over-charges background requests served in those windows. Pre-checked on StudyENG1c Part D FIT only (240 pairs, 360 trials, 161 chained; no holdout of ENG1 Part C, ENG1c, ENG1d or ENG1e read), with StudyENG1d's own derived attribution method and the clocks verified rather than assumed. THE GAPS ARE REAL: 1,235 of them, median 45.7 ms, almost entirely the next piece's front-end window (42.4 ms; client turnaround 0.6 ms, engine tail 2.9 ms), and of the 841 gaps that contain a step boundary ALL 841 carry other work, so the engine does serve background requests in them. BUT pol4 IS NOT TREATING THE CHAIN AS CONTIGUOUS: it prices a front-end window per request, so its own simulation already holds 0.284 s of gap per chain against a measured 0.513 s (piece1024) and 0.217 s against 0.312 s (piece2048), it places at least as many background requests inside its own gaps as the measurement does, and it reproduces a chain's total span to within 1 per cent (3.318 s against 3.332 s). Of the 303.9 s of TTFT-sum over-prediction across the 161 chained trials the gap position carries 31.3 s (10.3 per cent) while the BUSY position, a background request whose first token lands while the engine is actually prefilling a piece, carries 270.5 s (89.0 per cent), and the error is in the with-arm prediction (+265.1 s) not the without-arm (-5.4 s). REAL NEGATIVE under Rule 2, not inconclusive: every link was instrumented, non-zero and varying, two negative controls collapse the effect (mono11k ratio 1.13 with zero other prefill tokens in its own steps and max ctx_req 1; the 79 n_parts==1 piece trials over-predict by 0.018 s), and the hypothesis failed by being measured. The trial medians REPLICATE StudyPOL5's independent ENG1d localization to within 1.05x (1.917 / 1.694 / 1.125 against 1.83 / 1.62 / 1.13). LEADING ALTERNATIVE, a hypothesis with FIT evidence and explicitly NOT a finding, H-granularity with H-merge: pol4 gets each piece's prefill DURATION right to 5 to 12 per cent (0.242 s and 0.454 s measured against pol4's 0.271 s and 0.479 s) but puts it in ONE step where the engine uses about 1.8 (1.75 and 1.92 steps per piece, median step 0.157 s and 0.170 s), and never lets a background prefill share a piece's step, which the engine does on 17 of 20 and 10.5 of 11.5 of them (median 3,780 and 3,402 other prefill tokens inside the pieces' own steps, max ctx_req 2); mono exceeds the step budget, runs alone, and pol4 gets its step count right, which is why its ratio is only 1.13. The two are NOT distinguished from each other by this data and the per-step composition is a DERIVED proxy, so no term was fitted. BUILT: pol6 as a new unwired module with every flag off by default (`piece_gap_scheduling` implemented and off, because substituting the image-aware front-end term would OVERSHOOT at 58.2 and 95.4 ms against measured 34.9 and 44.1 ms where pol4 charges 29.8 ms; `step_granularity` and `in_step_merge` raise rather than run unparameterised), a terms file carrying NO coefficient of its own, and a StudyENG1e membership loader that declares its required fields BEFORE the schema is committed and fences the ENG1e HOLDOUT. 350 tests pass (34 new); all 12 T0b freeze md5s verified; results/cost/ untouched; pol4 remains the frozen and default model. STOPPED at the brief's own STOP AND ASK. NEXT: StudyENG1e-chain's per-step request membership is the one measurement that separates granularity from merge, and Part B's diagnosis step should be re-scoped around the 89 per cent rather than H-gap. Report: reports/study_pol6_chain.md.)

Last updated: 2026-11-17 (later 4) (**StudyT0b-fidelity ONE-SHOT COMPLETE ON BOTH HELD-OUT SETS AND StudyPOL5 Part 3 (RESIDENCY) WIRED IN (flash, CPU only): THE FROZEN pol4 MODEL RANKS ACTIONS AND PRICES THEIR OWN COMPLETION WELL ON FRESH DATA, AND STILL FAILS (i-b) ON THE SIZE OF THE DELAY A CHAINED REBUILD IMPOSES ON OTHERS.** Each holdout was run ONCE through the refusal mechanism, with all 12 frozen md5s verified at run time and the amended row frozen beforehand (md5 927813b86a3c9b618b915e232ce44671 at 19:06:23Z). ENG1c Part D HOLDOUT (120 pairs): (i-b) primary latency, bar 0.90, ceiling 0.8889, model 0.5417, ratio 0.6094 FAIL; (ii) 0.9500 PASS; (iii) 0.0429 PASS. ENG1d HOLDOUT (60 pairs): (i-b) primary ceiling 1.0000, model 0.8167, ratio 0.8167 FAIL, but the secondary TTFT definition PASSES at 0.9086; (ii) 1.0000 PASS; (iii) 0.0744 PASS. (iv) is not applicable on either set, so T0's 0.9718 stands. The failure is SHAPE-specific rather than holdout-specific: mono11k passes 0.900 on ENG1c and 20 of 20 on ENG1d, while ENG1c's CHAINED piece1024 passes 8 of 40, which is StudyPOL5 Part 1's diagnosis arriving intact on held-out data. Over-prediction dominates (102 of 120, 38 of 60), so the bias runs AGAINST pieces and a live policy that prefers them is not being flattered by its cost model. The FIT dry run predicted the holdout to 0.009 on (i-b). Also done: StudyRES1's residency model is now the controller's belief (policy/residency_belief.py, reached through non-frozen rollout and coordinator fields; None keeps the old path), replacing tiers.EVICTION_RULE_ASSUMPTION, with a boundary rule that reports POSSIBLY COLD as a belief SPLIT within 1.58 per cent of the cap (RES1's 3,064-token accounting error plus 816 tokens of block rounding) and a disclosed block-rounding fix that does NOT re-score RES1's TEST set. No holdout remains for StudyT0b.)

Last updated: 2026-11-17 (later 3) (**StudyPOL5-engine STOPPED AT THE REGRESSION GATE (flash, CPU only): THE PIECE OVER-PREDICTION IS LOCATED BUT NOT FIXED, pol5 IS NOT FROZEN, pol4 STAYS THE FROZEN MODEL, AND NO HOLDOUT WAS READ.** Part 1 succeeded: the error is the arrivals inside the action's engine span (96 to 98 per cent of the measured total), the same under the latency and TTFT definitions, specific to StudyENG1c Part D's CHAINED cold rebuilds (against StudyENG1d's own per-arrival bins the same model runs 0.75 to 1.23), and it is not the step model (0.85 to 0.97 when fed the engine's own step composition) nor base queueing (0.92 to 0.98 on the background-only arm). pol4 merges background prefills into the action's steps in 54 to 66 per cent of piece steps, and 513 of 513 such merges involve a request handed over after the previous step started, against StudyENG1d's 0 of 248 in-window arrivals admitted. BUT the two structural rules that follow from this were both REJECTED ON FIT (a one-step scheduling lag: piece1024 1.74 to 2.42; one prefill per step: 1.74 to 3.25, and its premise, the step-log field it[1], is not a prefill count), and with both off pol5 still regresses on ENG1c FIT, so the pre-registered stop condition fired. Kept and fitted for a later row: an image-aware front end (R2 0.985 on 58,085 measured windows) and the host-rate reconciliation (counters 44.69 against 50.14 GB/s; ENG1c's 29 GB/s is an end-to-end rate carrying 53.3 ms of non-transfer overhead per reload). An erratum was raised against StudyPOL4-engine section 2A.6: its rho values are biased low because its denominator includes the front-end window, and its 'short actions: arrivals join the running batch' reading is withdrawn. NEXT: the engine's per-step request MEMBERSHIP is what every remaining hypothesis needs and no committed log carries it; and the defect lives in chained rebuilds, which StudyENG1d did not exercise.)

Last updated: 2026-11-17 (latest) (**StudyENG1d-loadedblock COMPLETE (h100nvl GPU 2): UNDER LOAD AN ARRIVAL DURING A LONG PREFILL WAITS OUT ALL OF ITS REMAINING WORK AND THEN THE CATCH-UP OF THE QUEUE AHEAD OF IT (H1, STRONGER THAN SERIAL); ARRIVALS ARE NOT ADMITTED INTO THE ACTION'S STEPS (H2 REJECTED).** Run 08:05 to 10:07, not VOID, both gates PASS (unloaded control within ENG1 Part B; P40 mono11k total 44.9 s within ENG1 Part C's 22.5 to 64.4 s); 180 FIT pairs, 60 HOLDOUT pairs recorded and NOT analysed (unspent for T0b); 0 / 13,149 cached-token mismatches; derived step conservation 180 / 180. rho_b (from the action's scheduling, offsets 25 to 75 %): mono11k 1.17 (S2), 1.26 (P25), 1.37 (P40), 1.43 (S4); piece2048 0.91 to 1.44; piece1024 0.82 to 1.07; S2 piece1024 PARTIAL (n = 6). Only 3 to 6 % (mono11k) and 0 / 248 (pieces) of in-window arrivals got into the action's steps; the excess over remaining work is 0.034 to 0.042 s per request in flight, about one N=1 prefill each. Arrivals during the action's front-end window (0.7 s for mono11k under load, 0.1 to 0.2 s for pieces) wait the whole engine span and carry 22 to 57 % of the imposed delay. ENG1 Part C FIT replication: same verdicts in all 12 cells. FOR StudyPOL5-engine: the loaded data do NOT support a blocking fraction below 1 for pieces (POL4 2A.6's 0.68 to 0.70 mixed in the front-end window and the short span); the measured terms are front-end window, serial remaining work and per-queued-request catch-up. GPUs 0, 1, 3 busy (other users) throughout; host CPU at most 3.1 %. Report: reports/study_eng1d_loadedblock.md.)

Last updated: 2026-11-17 (later 2) (**StudyRES1-residency COMPLETE (flash, CPU only; design decision D56): THE SCHEDULER'S OWN BOOKKEEPING PREDICTS WHICH TIER EACH HISTORY IS IN, AT 0.9946 ON FOUR CLASSES, WITH NO FITTED PARAMETER AND NO MEASURED COUNTER.** The question StudyT0b excluded by taking tier at arrival as a given input is now answered on StudyENG1c Parts B to E: a chunk-level two-tier LRU model implementing ENG1c Part A's identified rule, driven only by arrivals, prompt tokens, prefix identity and the two capacities, gets 2,559 of 2,573 TEST requests right (R1 PASS, 0.9936 to 1.0000 per cap), with every error a capacity-boundary case and no confusion at all between GPU-warm and host-warm. R2 FAILS on one comparison: the rule beats FIFO, LRU-host-only and occupancy-only with bootstrap CIs excluding 0, but ties LRU-by-any-access, because the asymmetric host-refresh clause that ENG1c Part A was built to demonstrate changes exactly 2 of 2,573 predictions on streams of this shape (on Part A, in-sample, the same gap is 7.7 points). R3 FAILS at 0.2962 against 0.10: the host fraction is measurable almost only in ENG1c's 60 GiB occupancy-0.5 boundary cell, where a 1.37 per cent error in cumulative write accounting becomes a 0.29 error in the fraction; the fix (charge whole blocks only, which is 816 of the 3,064-token gap) was NOT applied because that would be fitting on TEST. Under concurrency the telemetry degrades and the bookkeeping does not: 0.8636 against 1.0000 on the 88 round-level-determined Part C requests, and correcting bookkeeping with ambiguous telemetry makes it worse. Stated scope limit: R1 to R3 do not cover the GPU-versus-host split under concurrency 4 and 8, which needs per-request attribution under concurrency to close. The ENG1c Part D holdout was replayed for capacity and never scored; the StudyT0b freeze is untouched and all 12 of its md5s still verify.)

Last updated: 2026-11-17 (later) (**StudyT0b-fidelity PART 2 FIT DRY RUN COMPLETE, HOLDOUT UNSPENT (flash, CPU only; design log D60): THE REVISED COST MODEL ROUGHLY DOUBLES ITS AGREEMENT WITH MEASUREMENT OUT OF SAMPLE AND STILL FAILS CRITERION (i), AND THE RESIDUAL IS THE PIECE-WISE REBUILDS.** Scored on 360 StudyENG1c Part D FIT pairs, out of sample for the model (no coefficient saw an ENG1c datum), under ENG1c's own definition of imposed delay (latency deltas, reproduced on all 360 trials to 1.4e-14 s) with StudyT0's TTFT definition reported beside it. Criterion (i): bar 0.90, measurement repeatability ceiling 0.8889, old model 0.2972, new model 0.5500, (i-b) ratio 0.6188 against the 0.90 bar, FAIL. Failures 253 to 162, median signed error +4.691 s to +1.932 s, 88 % of it over-prediction. (ii) 0.9412, down from the old model's 1.0000 on a single pair whose measured medians are 0.021 s and 0.009 s, recorded as a regression. (iii) median ARE 0.1628 to 0.0496. (iv) 0.9839 on ENG1c Part B but nearly degenerate, so T0's 0.9718 stays informative. mono11k carries out of sample, 0.408 to 0.908, which is the merged-step correction holding on a different host configuration; piece2048 0.450 and piece1024 0.292 stay over-predicted by about 1.6 to 1.7x, matching Part 1b's loaded-blocking estimates behind piece rebuilds (rho 0.68 to 0.70). REAL NEGATIVE, not inconclusive. The 120 HOLDOUT pairs are unspent; whether to spend them now or after StudyENG1d is the open decision. Also: StudyPOL4-engine Part 1b committed and pushed, and the T0b freeze's post-rebase sha erratum recorded with all 12 frozen md5s re-verified. NEXT GATE (user ruling 2026-11-17): the ENG1c holdout is NOT to be spent now; StudyENG1d (H100, loaded-arrival blocking, running, about 3 h) measures the missing quantity directly. After its report and the user's go, StudyPOL5-engine adds a load-dependent blocking term fitted on ENG1d FIT only (ENG1 Part C FIT as cross-check, per action type), reconciles term (a)'s 50.14 GB/s against ENG1c's measured 29 GB/s on ENG1c non-holdout rows, re-freezes, and only then runs T0b one-shot on BOTH the ENG1c and ENG1d holdouts, reported separately. Already done ahead of it, before any holdout read: the primary imposed-delay definition is fixed in the T0b row (latency sum primary, TTFT sum secondary) and the criterion (ii) regression on the 21 ms versus 9 ms pair is recorded as a stop event and as a known limitation of the 2x inclusion rule, which is NOT changed.)

Last updated: 2026-11-17 (**StudyENG1c-hostfull COMPLETE (h100nvl GPU 2): HOST RESIDENCY IS DECIDED BY TOKENS WRITTEN AFTER THE HISTORY, NOT BY HOST OCCUPANCY; A MIXED GPU/HOST TOUCH LOSES THE WHOLE HISTORY; NO HOST-FULL TAX.** M6 for D56. Caps set by host space beyond the 62,944-token GPU pool (27 / 38 / 60 GiB = 4.3 / 8.3 / 16.4 histories beyond GPU) plus 256 GiB reference and a 12 GiB demonstration; every cap enforced (mmap = cap). Host eviction is LRU with the code-reading refresh rule (95 / 95 target probes): a request served wholly from GPU refreshes its host copy, one that loads anything from host refreshes only what it loaded. Touching keeps a host-only history (15 / 15) and a GPU-resident one only if served wholly from GPU (12 / 12; block-aligned prompts take one chunk from host and fail 0 / 3); a half-evicted touch loses the whole history (0 / 15). A host smaller than the GPU pool recovers nothing. P_host is a step in write volume after the history: full at 38 / 60 / 256 GiB occ 0, zero beyond the cap, partial at the boundary (60 GiB occ 0.5: 0.57); older occupancy is harmless (20 / 20). Per-request cached tokens report the tier correctly; at 27 GiB concurrency 8 host-warm histories are lost to concurrent cold write-through before scheduling (3 / 16 survive). Churn: cold mono rebuild imposes 14 to 16.5 s on others, 1,024-token pieces 2.9 to 3.6 s (+1 s job TTFT); warm arrivals about 0 s. No host-full tax (step +0.5 %). 0 / 18,768 paired mismatches; 120 HOLDOUT pairs recorded, not analysed. GPU 3 (another user) busy throughout. Report: `reports/study_eng1c_hostfull.md`.)

Last updated: 2026-11-17 (**StudyPOL4-engine COMPLETE (flash, CPU only; design log D60, Parts 1 AND 1b): THE THREE ENGINE-MODEL GAPS StudyT0-fidelity ATTRIBUTED CRITERION (i)'s FAILURE TO ARE NOW NAMED TERMS, FITTED ON NON-HOLDOUT DATA AND FROZEN FOR StudyT0b, AND CRITERION (i) RISES FROM 0.6355 TO 0.7562 AGAINST A 0.8276 REPEATABILITY CEILING.** (a) host-KV transfer, previously absent altogether, is 262,144 B per token at 50.1377 GB per s plus a 0.8845 ms lookup, fitted from the kv_offload counters of StudyENG1 Part D at concurrency 1, where they are demonstrably attributable per request (30 of 30 host rows, 0 of 30 gpu, 0 of 30 cold, one bytes-per-token value; at concurrency 4 they are contaminated). (b) long cold prefill scale 0.789119 + 0.009228 x L/1000, fitted on 17 StudyENG1 Part A and B long-prefill cells, brings the solo monolithic 11k cross-check from 1.093 to 0.995 of the measured 2.673 s and mono11k's criterion (i) from 0.529 to 1.000, which is that cell's own noise ceiling. (c) sub-linear batching: PART 1 REPORTED A PENALTY (-0.030) AND CONCLUDED THAT StudyT0's DIAGNOSIS C WAS REFUTED; PART 1b TRACED THAT TO A DEFECT IN THE TERM'S OWN FIT SCRIPT AND REVERSED IT. `fit_pol4_terms._a1_cells` passed each A1 cell's `N` to the simulator as an image count, but `N` is the QUERY'S FRAME COUNT (378 tokens at N=1, about 1,062 at N=3, i.e. 36 question tokens plus 342 per query image, both recovered to 342.0 from the record) while the simulator counts encoder work in the step model's own 90-token units (4 and 12, not 1 and 3), so every A1 request was charged a quarter of its measured encoder work. CORRECTED, the exponent is +0.100, A GAIN (10 per cent window 0.090 to 0.110, excluding zero; the secondary absolute objective now agrees in sign at +0.150), the old model is shown to give 15 to 18 per cent TOO LITTLE batching gain at k=16 against the published anchors (0.5859 against 0.510, 0.8644 against 0.731), and DIAGNOSIS C IS SUPPORTED. On the 406 Part C FIT trials, IN-SAMPLE FOR THE CHOICE OF TERMS and not a test of the revised model: (i) 0.6355 to 0.7562, still FAIL against the 0.90 bar but 12.1 points better and now only 7.1 points below the measurement's own repeatability ceiling of 0.8276 where the old model was 19.2 below; (ii) 0.9667 to 0.9833 PASS; (iii) 0.1643 to 0.1039 PASS; (iv) 0.9718 unchanged PASS. Every load improves or holds (P25 0.750 to 0.810, P40 0.488 to 0.655 which is above its own 0.611 ceiling, S2 0.821 to 0.905, S4 0.452 to 0.726, W25 flat), over-prediction falls from 68.7 to 57.1 per cent of trials and the median signed error from +0.0894 to +0.0221 s, and the regression stop condition did NOT trigger for the frozen configuration. PART 1b ALSO ATTRIBUTED THE burst4 OVER-PREDICTION, which the user required before any term could be kept or dropped: it is the over-charge of a MERGED multi-prefill step (predicted 0.2390 s against a measured floor of 0.1764 s, ratio 1.355, matching Part A's independently measured 1.084 to 1.346), NOT the front-end serialization (36 microseconds of a 131 ms over-prediction), NOT the compared-request set (balanced in all 406 trials; the superset definition moves the ratio 1.529 to 1.502) and NOT the per-image admission stall (the charge for the action's own images is exactly 0.00 ms and zeroing both admission coefficients changes nothing). The k-independent base under-prediction Part 1 reported (0.804 at k=1) DOES NOT EXIST, being the same convention defect: under the simulator's convention the base is 0.996 at A1 k=1 N=1 and 0.945 on Part B's 20 independent idle-engine solo requests, so NO TERM WAS ADDED. LOADED BLOCKING IS IDENTIFIABLE from the Part C FIT per-request rows under a pre-stated criterion: rho = 0.803 (95 per cent CI 0.727 to 0.856) pooled, 0.735 / 0.869 / 0.759 at P25 / P40 / S2, and 1.149 (1.123 to 1.206) behind a monolithic prefill, i.e. ABOVE the simulator's rho = 1 and above StudyENG1 Part B's unloaded 0.97 to 1.00; reported IN-SAMPLE and DELIBERATELY NOT ADDED, with StudyENG1d after StudyENG1c as the way to pin it. ONE THING IS STILL LEFT DELIBERATELY UNMODELLED FOR WANT OF A MEASUREMENT: the W25 warm sessions' own host reloads, which the run-level counter cannot attribute per request. The 174 Part C HOLDOUT triples were NOT read, predicted or evaluated and the exclusion is asserted in code. RE-FROZEN after Part 1b at 2026-11-17T05:36:55Z: results/orchestration/study_t0b/t0b_freeze.json, model `pol4`, 12 file md5s, the step model UNCHANGED at 7da0a984bca4ba4f0ff81d5cee54d18c, chosen BY MECHANISM and not by FIT score, pol4_nobatch being rejected because switching term (c) off asserts that merged multi-prefill steps are charged correctly, which two independent measurements say they are not. 226 tests green, 211 after Part 1, 184 before. ERRATUM RAISED AGAINST StudyT0-fidelity AND RECORDED IN ITS REPORT (section 0A) ON THE USER'S INSTRUCTION: its headline repeatability ceiling of 83.9 per cent is the PRE-`COMPARED_KINDS`-fix value and the correct one is 82.76 per cent (72 of 87; the single flipped repeat pair is W25|piece1024|0, identified by scoring the same 87 repeats both ways), which T0's own committed dry-run JSON already records. No T0 verdict changes, the shortfall of model below ceiling widens from 25.3 to 24.2 points, and T0's registered artifacts were not edited. NEXT GATE UNCHANGED: StudyT0b must score this frozen model on FRESH held-out data with per-trial repeats, which needs StudyENG1c on the H100; results/cost/study_eng1c/ does not exist yet, so Part 2 was not started. reports/study_pol4_engine.md.) Previous entry, 2026-11-16 (later 4): (**StudyCTRL1c-calibrated SECOND RUN COMPLETE (flash, CPU only): THE OPEN STOP AND ASK IS CLOSED AND THE ANSWER TO Q11 CHANGES. THE CLOUD-INITIATED TRICKLE AT A 10 % CALL BUDGET BEATS RANDOM ESCALATION.** The user ruled the YES branch, and it is valid: StudyD3 Nexar DEV holds 4B and 32B scores at N = 1 for 601 clips (6,010 rows per tier) with the SAME two models at the SAME revisions, the SAME query and the SAME 378-token one-image prompt as the StudyD14b evaluation traces, and ZERO clip overlap with the 300 evaluation clips. ONE Platt map per tier fitted there (device a +0.114603 b +1.140751, cloud a +0.129472 b +1.848187), used for BOTH the trigger decisions and the scoring, is the FINAL PRIMARY; the first run's fully cross-fitted reading is now a LABELLED SENSITIVITY. Under it sanity check (a) HOLDS EXACTLY: device-only 0.4776042449177038 and always-cloud 0.5675307471627266 reproduce the committed values to 0.0 and StudyE9b's streaming AP to 1.7e-18 / 6.9e-18, so the challenge gap returns to the committed 0.0899. The gate passes (positives-only oracle 0.5703711658 against 0.4776042449, margin +0.0927669). Under the pre-registered decision rule the CLOUD-INITIATED TRICKLE at 10 % captures +127.0 % of the streaming-AP gap, +116.8 capture-fraction points over random with CI [+3.5, +359.0], on an 8-s background cadence with a LIVE trigger in 5 of 5 folds, and is the recommended family at a budget at or below 20 %; the context-modulated trickle at 10 % also beats random (+88.1, CI [+5.4, +399.6]) but its trigger is degenerate in 4 of 5 folds. The win is weakly resolved (CI half-width 177.7 points), concentrated in folds 1 and 4, and absent on the secondary challenge metric. At 5, 20 and 40 % no causal arm beats random, and at 5 % the cloud trickle is WORSE than random with a trigger that cannot fire. A NEW POWER TABLE puts the design's minimum detectable difference at 80 % power and alpha 0.05 at 82 to 1,935 capture-fraction points, so under the user's 10-point band NO CAUSAL CELL SURVIVES AS A REAL NEGATIVE: 18 cells move from real negative to INCONCLUSIVE (UNDERPOWERED), including the device filter, the absolute-confidence trigger and both learned ceilings at every budget. StudyE9b's corrected capture is 0.11686 / 0.48984 / 0.34158 / 0.37140 with BYTE-IDENTICAL decisions and invocation counts 2,269 / 4,419 / 7,562 / 12,785, and beside the matched random arm on the primary metric it is NOT distinguishable at any comparable trigger rate. `ctrl1c_fits_d3dev.json` was verified by refitting fold 0 from scratch with 0 leaf differences. ONE DECLARED DEVIATION from the ruling: StudyD3 holds a 10-offset event-anchored design (0.5-s spacing within a 5-s neighbourhood), not the dense whole-clip cadence; the required sensitivity against a D14b-DEV-fitted map gives slopes 2.6x to 3.0x steeper while the tier offset at the p = 0.5 crossing agrees to 0.46 log units. Report `reports/study_ctrl1c_calibrated.md` sections 16 to 22; results `results/dashcam/ctrl1c/ctrl1c_pooled_d3dev.json` and the four other d3dev files. NO OPEN STOP AND ASK REMAINS ON THIS ROW.)

Last updated: 2026-11-16 (later 4) (**StudyCTRL1c-calibrated SECOND RUN COMPLETE (flash, CPU only): THE OPEN STOP AND ASK IS CLOSED AND THE ANSWER TO Q11 CHANGES. THE CLOUD-INITIATED TRICKLE AT A 10 % CALL BUDGET BEATS RANDOM ESCALATION.** The user ruled the YES branch, and it is valid: StudyD3 Nexar DEV holds 4B and 32B scores at N = 1 for 601 clips (6,010 rows per tier) with the SAME two models at the SAME revisions, the SAME query and the SAME 378-token one-image prompt as the StudyD14b evaluation traces, and ZERO clip overlap with the 300 evaluation clips. ONE Platt map per tier fitted there (device a +0.114603 b +1.140751, cloud a +0.129472 b +1.848187), used for BOTH the trigger decisions and the scoring, is the FINAL PRIMARY; the first run's fully cross-fitted reading is now a LABELLED SENSITIVITY. Under it sanity check (a) HOLDS EXACTLY: device-only 0.4776042449177038 and always-cloud 0.5675307471627266 reproduce the committed values to 0.0 and StudyE9b's streaming AP to 1.7e-18 / 6.9e-18, so the challenge gap returns to the committed 0.0899. The gate passes (positives-only oracle 0.5703711658 against 0.4776042449, margin +0.0927669). Under the pre-registered decision rule the CLOUD-INITIATED TRICKLE at 10 % captures +127.0 % of the streaming-AP gap, +116.8 capture-fraction points over random with CI [+3.5, +359.0], on an 8-s background cadence with a LIVE trigger in 5 of 5 folds, and is the recommended family at a budget at or below 20 %; the context-modulated trickle at 10 % also beats random (+88.1, CI [+5.4, +399.6]) but its trigger is degenerate in 4 of 5 folds. The win is weakly resolved (CI half-width 177.7 points), concentrated in folds 1 and 4, and absent on the secondary challenge metric. At 5, 20 and 40 % no causal arm beats random, and at 5 % the cloud trickle is WORSE than random with a trigger that cannot fire. A NEW POWER TABLE puts the design's minimum detectable difference at 80 % power and alpha 0.05 at 82 to 1,935 capture-fraction points, so under the user's 10-point band NO CAUSAL CELL SURVIVES AS A REAL NEGATIVE: 18 cells move from real negative to INCONCLUSIVE (UNDERPOWERED), including the device filter, the absolute-confidence trigger and both learned ceilings at every budget. StudyE9b's corrected capture is 0.11686 / 0.48984 / 0.34158 / 0.37140 with BYTE-IDENTICAL decisions and invocation counts 2,269 / 4,419 / 7,562 / 12,785, and beside the matched random arm on the primary metric it is NOT distinguishable at any comparable trigger rate. `ctrl1c_fits_d3dev.json` was verified by refitting fold 0 from scratch with 0 leaf differences. ONE DECLARED DEVIATION from the ruling: StudyD3 holds a 10-offset event-anchored design (0.5-s spacing within a 5-s neighbourhood), not the dense whole-clip cadence; the required sensitivity against a D14b-DEV-fitted map gives slopes 2.6x to 3.0x steeper while the tier offset at the p = 0.5 crossing agrees to 0.46 log units. Report `reports/study_ctrl1c_calibrated.md` sections 16 to 22; results `results/dashcam/ctrl1c/ctrl1c_pooled_d3dev.json` and the four other d3dev files. NO OPEN STOP AND ASK REMAINS ON THIS ROW.)

Last updated: 2026-11-16 (later 3) (**StudyCTRL1c-calibrated COMPLETE (flash, CPU only): PER-TIER CALIBRATION IS WHERE THE VALUE IS, AND Q11 STILL DOES NOT SEPARATE THE TRIGGER FAMILIES.** StudyCTRL1b's three defects are removed. The tier offset falls from -5.1250 to -0.0639 log-odds and the positives-only oracle moves from -0.0865 BELOW device-only to +0.0923 ABOVE it, so decision D57's artifact is real and gone; StudyE9b's own device-triggered escalation, with BYTE-IDENTICAL decisions and invocation counts, goes from capturing 3 / 13 / 13 / 18 % of the always-cloud minus device-only gap to 12 / 49 / 34 / 37 % on one common scale. But under the pre-registered rule on the new primary metric (StudyE9b streaming AP over all decision instants, averaged over horizons 0.5 / 1.0 / 1.5 s), NOT ONE of the five causal trigger families beats random escalation at 5 / 10 / 20 / 40 %, under all three calibrations and both scale readings; only the two non-causal oracles do, and at 5 % the two trickle arms are measurably WORSE than random. The cloud trickle is now FEASIBLE at 10 % with a live trigger (8-s cadence, 5 of 5 folds), but at 5 % the only cadence that fits (10 s) costs exactly the budget, so its trigger cannot fire and that cell is INCONCLUSIVE by design, as are the context trickle's 5 % and 10 % cells. **ONE OPEN STOP AND ASK:** sanity check (a) holds EXACTLY for one per-tier map (the committed 0.4776042449 and 0.5675307472 reproduce to 0.0, StudyE9b's streaming AP to 7e-18) and cannot hold under the pre-registered CROSS-FITTED calibration, because five folds carry five different affine maps while both metrics rank across clips; the references move by -0.0251 and -0.0046 and the gap grows from 0.0899 to 0.1104. Both readings are reported in full and the user must decide which is primary. The saved maps (`results/dashcam/ctrl1c/ctrl1c_calibration.json`, with `single_map.platt.dev90` recommended) are the artefact spec 4.1's u_SH should load, and they are the map StudyPOL3's D57 path was waiting for. StudyCTRL1b-crossfit is SUPERSEDED FOR COMPARISON, not deleted.)

Last updated: 2026-11-16 (later 2) (**StudyPOL3-update AND StudyT0-fidelity COMPLETE (flash, CPU only): THE POLICY'S COST MODEL PREDICTS HELD-OUT LIVE ENGINE BEHAVIOUR WELL ENOUGH TO RANK ACTIONS AND TIME JOBS, AND THE A6 DEFERRAL RISK IS COMPUTABLE FROM POOL BOOKKEEPING ALONE.** T0 ran ONCE on the 174 held-out StudyENG1 Part C triples under a recorded freeze. Verdicts, verbatim as pre-registered: ranking PASS (61 of 63 action pairs differing by more than 2x = 96.8 %); job completion time PASS (median absolute relative error 16.69 %); StudyENG1b prefix-loss class PASS (828 of 852 = 97.2 %, MAE of fraction lost 0.0247, mechanistic with no ENG1b-fitted parameter); delay imposed on others FAIL, reported as three numbers together: bar 90 %, measurement repeatability ceiling 83.9 %, model 58.6 %. The bar was above what the measurement supports, AND the model is 25.3 points below that ceiling too, so the FAIL is a REAL FIDELITY GAP and not only an over-strict bar; on the one action whose measurement is perfectly repeatable (monolithic 11k, ceiling 1.000) the model still passes 52.9 %. Classified REAL NEGATIVE, not inconclusive. The model is BIASED HIGH on the imposed delay of a monolithic cold reconstruction (1.3 to 2.15x), traced to a 1.09x over-prediction of that request's own 2.7-s block amplified by the 12 to 45 arrivals queued behind it, which must be carried into any later finding that the policy prefers pieces. StudyPOL3-update brought the library to D56 (three tiers, both warm tiers bounded, P_host derived from host occupancy in place of the constant 0.0, host eviction rule an ASSUMPTION until StudyENG1c), D57 (per-tier score calibration with a loud failure on any uncalibrated cross-tier comparison; no map fitted, so that path raises until StudyCTRL1c) and StudyENG1b's mechanistic prefix loss; mu stays 0 and PLACEHOLDER because the spec defines no estimator, and the estimator is now an explicit parameter whose default does nothing and says why. 120 tests before, 182 after. BOTH OPEN DECISIONS RULED BY THE USER THE SAME DAY. The holdout stays ONE-SHOT and was not re-run: criterion (ii) was re-scored from the same frozen predictions under the corrected compared-request definition as a labelled SECONDARY check, 59 of 61 = 96.7 % PASS against the registered 61 of 63 = 96.8 % PASS, the registered artifacts byte-identical before and after. The correction is a SCORING-DEFINITION error, not a model change, and it affected only the five W25 cells, three of which moved by more than 2x (W25 append5, piece1024, piece2048). Criterion (i)'s FAIL stands, and StudyT0b-fidelity is now PRE-REGISTERED with a repeatability-scaled criterion (i-b) and a binding constraint that the 174 HOLDOUT triples are SPENT; its data source is TBD, a new H100 collection with per-trial repeats. FIT-only error attribution: the model OVER-PREDICTS (68.7 % of trials, 77.7 % of the failures), driven by mono11k and burst4 under the S4 and P40 loads, with one systematic under-prediction (hostreload, a missing host-KV-transfer term). Next: design and pre-register the fresh T0b collection.)
Last updated: 2026-11-17 (**StudyORIN2-stack COMPLETE (Jetson AGX Orin): two device-stack fidelity fixes (design log D61).** Part 1: the Orin 4B needs its OWN score calibration. Orin vs H100 4B scores correlate (Pearson 0.9418 over 6,010 StudyD3 DEV N=1 requests) but carry a mean offset (-0.2576 log units), so StudyCTRL1c's H100 map cannot be reused. The Orin 4B Platt map is a=0.114932, b=1.174287 (raw log P(Yes) at p=0.5 = -10.2173); the fit routine reproduces StudyCTRL1c's published H100 4B map to <1e-4 (validation), since ctrl1c_calibrate.py was absent from the repo. After calibration the Orin 4B is tier-aligned with the 32B (residual -0.0171 log-odds, tighter than the H100 4B's -0.1197); dev/eval clip overlap 0. Part 2: the device's warm-recall latency, measured WITHOUT re-sending the image history each call, is about 10x to 15x lower than the server path. No server-native no-resend path exists at c0fd786, so an in-process libllama+libmtmd harness was built; it passes an equivalence gate (token-identical prompts, identical answers and top-20 sets, first-token logprobs within a post-hoc 0.15-nat tolerance; server self-jitter 0.0). Harness warm-recall TTFT p50 0.146 s (11k) / 0.225 s (28k) vs server 1.416 s / 3.433 s (ratio 9.7x / 15.2x); the server TTFT is ~91% API image re-send (everything_else 1285 / 3245 ms), only ~9% model work (125 / 188 ms), which the harness matches (146 / 225 ms). The harness is the device warm-recall baseline for policy evaluation; the server path is an API artifact and must not be used as the device cost. Cross-path check PASS on all 40 (totals identical, 0 answer mismatch, harness evaluates a conservative 15-token superset). Next: the device cost curves (Part 2 harness) and the device-calibrated scores (Part 1 map) feed the trace-driven policy simulator.)

Last updated: 2026-11-16 (later) (**StudyENG1b-prefix-survival COMPLETE (h100nvl GPU 2): A DEFERRED, UNREFERENCED PREFIX SURVIVES EXACTLY UNTIL OTHER WORK HAS ALLOCATED THE FREE KV POOL; THE HOST TIER RECOVERS 99.9 % OF WHAT IS EVICTED.** Survival is a step function of KV allocated before the resume is scheduled (not of gap length): resident below 1.0 of the free pool, tail-first partial loss at 1.0 to 1.25, total above; episodic-only load never evicts; warm sessions' re-references shrink the effective pool. P_host 0.999; restore by reload +0.12 s vs rebuild +2.15 s. The larger cost of deferring a piece under another build's pressure is queueing behind that build (6.9 to 9.9 s). The engine's kv_cache_usage reads 0.0 for unreferenced prefixes, so the rollout must model the KV pool itself. Next: T0 on the ENG1 HOLDOUT and the KV-pool model check against ENG1b's per-trial ground truth.)

Last updated: 2026-11-16 (**StudyENG1-steptime COMPLETE (h100nvl GPU 2): THE ENGINE IS SUB-LINEAR IN BATCHED SMALL PREFILLS, BLOCKS A NEW REQUEST SERIALLY BEHIND A RUNNING PREFILL'S REMAINING WORK, AND HAS TWO MEASURED COSTS OUTSIDE THE STEP: A SERIAL FRONT END AND A MULTIMODAL ADMISSION STALL.** H-step sub-linear (16-batch / 16 x single = 0.51 N=1, 0.73 N=3). H-admit (a): an episodic call arriving during a monolithic ~11k prefill waits for all of its remaining work (rho 0.97 to 1.00); T1 changes one cell. H-tier: counters attribute GPU vs host hits exactly at concurrency 1 (100 %) and not under concurrency (40 %). Step model (piecewise-linear, R^2 0.985) + front end (29.6 ms + 20.2 ms / MB idle, per-MB part serial) + admission stall (12.7 ms + 1.15 ms / image, paid by every running request). Part C ground truth (FIT): one monolithic ~11k cold prefill imposes 16 to 71 s of total delay on others, a 2,048-token piece 0.4 to 2.6 s, a host reload of the same history about 0; 0 cached-token mismatches over 580 pairs; HOLDOUT (174 triples) recorded for T0 and untouched. Defect: the ENG1 plugin wrote no rows on KV-HOST servers (fixed; data recovered from iteration logs). Next: StudyENG1b-prefix-survival (pre-registered), then T0 on the HOLDOUT.)

Last updated: 2026-11-15 (**StudyCTRL1b-crossfit and StudyPOL2-build COMPLETE.** Cross-fitting on all 300 clips resolves the always-cloud minus device-only gap at last (+0.0899, CI +0.0357 to +0.1497), and the binding problem turns out not to be trigger quality but SCORE CALIBRATION between tiers: the 32B's scores run a median -5.125 log units below the 4B's, so a label-correlated trigger moves the rank metric by itself. The v3.1 policy core is built, tested and measured, with every conditional mechanism off by default.)

## Last updated: 2026-11-15 (StudyCTRL1b-crossfit, StudyPOL2-build)

**Two studies on flash, CPU only; no GPU, no model server, no inference, and no scikit-learn.** Both prerequisites named by the brief are now on disk and were moved into `research/` with a filesystem `mv`, uncommitted: `research/POLICY_SPEC_v3.md` and `research/POLICY_SPEC_v3_1_ADDENDUM.md` (v3.1 = v3 plus the addendum; where they conflict the addendum wins).

**StudyCTRL1b-crossfit: the gap is resolved, and the problem is not the trigger.** Five label-stratified folds over all 300 D14b clips, every tunable chosen on the other four folds, the pooled result concatenating the five held-out folds. The denominator the 210-clip subset could not resolve is now resolved: always-cloud minus device-only is **+0.0899, CI +0.0357 to +0.1497**. Capture fractions at the 20 % call-fraction budget: device filter (spec 7.7) +24 % [-6, +60], cloud trickle +14 % [-16, +43], context-modulated trickle +11 % [-21, +38], learned ceiling +25 % [+5, +66], absolute confidence +6 % [-60, +38], random +16 % [-16, +48], and the non-causal timing bound +80 % [+53, +101].

**The finding that reorders the question.** The two tiers' scores are not on one scale: the 32B's log P(Yes) runs a median -5.125 log units below the 4B's, and at the crop instants the cloud's score is usually LOWER than the device's. The challenge metric ranks one crop per clip across clips, so an escalation pattern correlated with the label biases it through the offset alone. The brief's positives-only oracle therefore scores 0.4042, BELOW device-only 0.4951, while the identical timing applied to every clip's crop instant scores 0.4179. The control that isolates this holds the timing fixed and removes only the label correlation. The brief's two requirements for that arm (escalate only before positive events, and bound any trigger at that budget) are incompatible on this metric, so both readings are reported. The policy consequence is direct: spec 4.1's u_SH must be a CALIBRATED utility, never a raw tier score, which is how StudyPOL2-build's library reads it.

**Two gaps in the machine, declared rather than worked around.** The cloud trickle is INFEASIBLE at the 5 % and 10 % budgets because the brief's cheapest background cadence of 4 s already costs 0.1250 of the call rate; the grid was not widened, since that would be a methodological change beyond the brief. And the predictability ceiling could use no visual feature at all: the D14b frame store (`/home/pragya/data/dashcam/d14b_frames`) does not exist on this machine and opencv is absent, while ego speed does not exist in the committed Nexar table (its columns are file_name, label, scene, light, weather, duration_s, split). Elapsed time in the clip was excluded by decision, because Nexar events sit at a characteristic position and the clock would leak the dataset's event placement. The ceiling is therefore a ceiling on SCORE-DYNAMICS-AND-CONTEXT predictability (training r2 0.023 to 0.042 across folds) and NOT on what images could add.

**StudyFRAMES1 re-run on all 300 clips.** Cross-fitting it is a power gain rather than a bias removal, because the matched-delay comparison has no tunable. Pooled matched-delay gain -0.0041 at zero delay and -0.0254 at 3 s; at own latencies the 32B at N = 3 is -0.0172 against N = 1 (CI -0.0774 to +0.0402). The genuinely cross-fitted object is CHOOSE-N, which picks N on the training folds and applies it held out.

**StudyPOL2-build: the v3.1 policy core exists, is tested and is measured.** `experiments/orchestration/policy/`, 17 modules, 58 spec sections mapped to named symbols with the map itself asserted by a test, 120 unit and property tests passing. All five conditional mechanisms default OFF and each carries its unmet enabling condition in code; merging is not merely unestablished but WEAKENED, so the m = 3 utility table cannot be read unless merging is explicitly enabled. The engine model is behind one protocol, built from committed evidence only, and tags every prediction with an in_sample flag that the rollout and DeltaJ propagate, which is the instrumentation the later T0-T4 verification needs. The v3.1 addendum is implemented: one escalation basis Ghat for every request type, used by the device's filter AND inside the cloud's DeltaJ_H (equal to 12 decimal places on SH), evidence coverage wired to the two committed device tables whose gap IS the value of the cloud holding more evidence, a non-learned keyword and temporal-reference type posterior, a timeliness gate that zeroes Ghat, and a device-uncertainty multiplier left at IDENTITY and marked PLACEHOLDER because no committed DEV table maps uncertainty to gain. Queries escalate as metadata only and the payload is pulled solely on admission. No request type is routed by a hard-coded rule and that is tested four ways. Queries are sent COMPLETE by default per the revised A2, with question-first as an exception path for an RC query whose unsent history is large AND whose uplink already carries higher-value traffic; the delivered delay is computed for the path actually used, the question-first path charges one control round trip and the coordinator's own measured decision latency, and a declined query is DISCARDED with nothing left in the pending set. Two defects surfaced and were fixed in the process: deferring job registration to admission revealed that the rollout could not see the candidate job, so every RC admission had been scoring exactly zero; and spec 3.5's terminal backlog term, written as a plus while mu is a price, had backlog RAISING terminal value, which now subtracts. The addendum FILE still carries the superseded metadata-first wording in A2, so the code follows the user's instruction and the discrepancy is recorded rather than silently resolved. Addendum A6, partial-prefix survival, is implemented too: the rollout carries a KV pool whose predicted eviction supplies P_loss, the expected remaining work under deferral feeds the continuation value, the feasibility class and piece sizing, an in-progress prefix is valued in the memory decision at its continuation value at risk plus its state value for future questions with the single-counting rule ASSERTED on every rollout, and the coordinator verifies believed residency before releasing a piece and re-plans on loss. Under KV pressure the prefix is predicted fully lost if the piece is deferred and fully safe if it is released, so deferring scores -1.7991 with the pool against -0.4338 without; at zero pressure every A6 term is exactly zero. Two findings about the spec came out of it: restore work that still meets the deadline cannot move an indicator Phat_r, so A6 reaches release timing only through the backlog price mu, which is a placeholder at zero and therefore silent by default; and charging the eviction risk over the whole horizon made deferring look cheaper than releasing until the exposure window was scoped to begin when the job last referenced its prefix. M4: one DeltaJ_H costs 0.33 ms, but a 64-item release loop costs 59.2 ms, which is 8 % of a 0.75-s horizon, so spec 7.2's release loop and not the rollout is the cost to watch; one Ghat costs about 4 microseconds and changes nothing.

**What is still open.** T0 has not been run, so the rollout's fidelity is unmeasured and every DeltaJ_H rests on a model known to fail out of sample on slice-versus-episodic mixtures. T1 to T4 are untouched: no baseline comparison and no capacity number. The addendum's Q11 (which SH trigger family) is left open in code on purpose, with the three families interchangeable, so the decision can be made from StudyCTRL1b's table with one assignment.

**Supersedes, not deletes.** StudyCTRL1-episodes' 90/210 results and StudyFRAMES1's remain in `results/dashcam/ctrl1/`, `results/dashcam/frames1/`, `reports/study_ctrl1_episodes.md` and `reports/study_frames1.md`, and are labelled superseded there and here.

## Last updated: 2026-11-15 (StudyCTRL1-episodes, StudyFRAMES1, StudyPROF1-dev)

**Three studies on flash, CPU only; no GPU, no model server, no inference. Part 4
(StudyPOL2-build, the v3 policy core) is NOT started: the spec is present on disk as
`policy_spec.md` at the repository root but is untracked and unpushed, and the brief names
`research/POLICY_SPEC_v3.md`.**

**A stop condition fired first, and the answer changed the shape of all three studies.** The
brief asked for the Nexar DEV / EVAL split covering StudyD14b's clips. There is none: the
canonical split is dev 751 / val 300 / test 449 and **StudyD14b IS the 300 val clips**, while
StudyD3 ran the dev clips as a 10-offset design with no 0.25-s trajectory for a window length, a
lag or a frame count to be fitted against. The user authorized a pre-registered video-level split
of the 300: sha256(file_name) order, lowest 30 % to DEV, stratified by label, giving **DEV 90 /
EVAL 210 with overlap 0**. Consequence carried on every number: the committed challenge-mAP
references (0.5675 and 0.4776 over all 300) are recomputed per side (EVAL 0.5420 and 0.4822) and
the all-300 values are reference-only. The pipeline reproduces both committed values to 1 ulp,
which is the strongest available check that the delivery model, crop geometry and AP are
StudyE9b / E9c / E9d's own.

**StudyCTRL1-episodes: the controller is sound and its DEV-fitted parameters transfer nothing.**
Spec 7.7 with the price term off, reading only the device's own delivered 0.75-s samples. On the
90 DEV clips a 162-combination search captures 46 / 60 / 96 / 129 % of the cloud-minus-device gap
at the 5 / 10 / 20 / 40 % escalation budgets. On the 210 held-out clips the same settings capture
**-18.2 / +1.9 / -3.2 / +15.2 %, every CI spanning zero**, and no paired difference excludes zero
anywhere, including always-cloud minus device-only itself (+0.0598, CI -0.0076 to +0.1395). So the
key number is **INCONCLUSIVE by power** (CLAUDE.md Rule 2), not a real negative: the mechanism was
verified present before the EVAL numbers were written. Self-normalization is not measurably better
than an absolute-confidence threshold, nor better than random escalation at the same budget, and
the point estimates sit inside StudyE9b's committed 3-18 % range. Episodes run 2.10 to 13.38 per
device-minute with p50 length 1.25-1.75 s, and **false episodes on negative clips track the
escalation rate almost exactly** (2.14 against 2.10 per minute at the 5 % budget), which is the
cleanest statement that the controller fires at a rate rather than at the right moments. The
negative control is the most consequential single result: replacing the cloud's score with the
device's own does NOT collapse to the null, decomposing the DEV gain into **30-45 % cloud path
freshness and 55-70 % cloud score quality**. Workload traces (escalations, episode call times,
eligible-opportunity grid) are written for the live evaluation.

**StudyFRAMES1: frames are the wrong place to spend.** At matched total delivered delay the third
frame buys nothing measurable on EVAL (32B +0.0017 at 0 s, -0.0296 at 1.5 s, -0.0402 at 3 s; the
4B is negative at every delay), and charged its own upload the 32B at N=3 is **-0.0291 mAP behind
N=1** (CI -0.0989 to +0.0285). DEV says the opposite at short delay (+0.0943), which is the same
transfer failure again. The row BOUNDS spec 7.9's merge rule rather than measuring it, because
StudyD14b's N=3 is three consecutive frames, the most redundant arrangement; one GPU run on
cadence-spaced pairs would close it.

**StudyPROF1-dev: the DEV profile tables exist, with their provenance on their face.** One JSON,
every entry marked MEASURED, DERIVED RULE, ASSUMPTION or PROPOSAL. u_SH uses the identity mapping
(challenge AP is already bounded) and shows the device overtaking a cloud answer beyond about 1 s
of delivered delay. Five RC tables restricted to the same 243 S-EMBER DEV questions reproduce the
committed accuracies exactly before restriction. omega_RC = 0.4246 against omega_SH = 1 is
**computed but marked a PROPOSAL awaiting approval**, and omega_SS is null because no committed SS
pair exists. Eight of ten duration families are marked for replacement by StudyENG1, and catch-up
per frame is a DERIVED RULE because no video-domain measurement exists. **Two gaps are reported
rather than filled:** committed data carries connectivity bits, not a bandwidth series, so
bandwidth percentiles do not exist and jitter is declared absent rather than invented; and spec
6.4's conditional recall rate is NOT COMPUTABLE, because escalation episodes live on the Nexar
traces and recall questions on S-EMBER videos and no committed trace carries both on one stream,
so the mechanism is left off.

Last updated: 2026-11-16 (**StudyORIN1-dense Part 1 COMPLETE (Jetson Orin); all three parts now done.** The dense 0.25 s Orin scores are finished: all 42,014 StudyD14b N=1 requests were scored on the Orin, one request at a time, cold prompt. The dense frames did not fit on the device at once, so the Mac sent them in two halves (139 then 161 clips); each half was sha256-verified against the D14b frame manifest (0 missing, 0 mismatch), scored, then had its fractional frames deleted, with the 10,660 integer-second StudyD15 frames kept throughout. The Orin reproduces StudyD15 exactly on the integer-second overlap (Pearson 1.000000, max abs diff 0.0, n=10,660). Against the H100 4B D14b arm the device scores correlate strongly over all 42,014 (Pearson 0.9426, Spearman 0.9416) with about a 1 log-unit absolute offset, the StudyD15 cross-stack effect (vLLM BF16 vs llama.cpp F16); on the challenge set the device and the H100 4B arm are indistinguishable in average precision (Orin 0.5735 vs H100 0.5764, diff -0.0029, 95 percent CI [-0.0079, 0.0019], includes 0). The Orin is a faithful stand-in for the H100 4B detection arm, with a documented constant-offset caveat on absolute log P(Yes) that does not affect ranking or AP (`reports/study_orin1_dense.md`).)

Last updated: 2026-11-15 (later 3) (**StudyORIN1-dense Parts 2 and 3 COMPLETE (Jetson Orin); Part 1 HELD for frames.** Part 1 (dense 0.25 s Orin scores) stopped at the gate: 31,354 of 42,014 D14b N=1 frames are missing on the Orin (all fractional grid points, 300/300 clips); nothing scored, no substitution; held until the Mac transfers them. Part 2: the device controller signals (window median/IQR, robust relative score, rise=score(t)-score(t-2s), instability) cost mean 8.4/19.3/80.0 us per 4 Hz update for windows 20/60/240, at most 0.034 percent of a tick; the controller is effectively free on the Orin CPU. Part 3 (warm D2 recall latency, previously only an assumed rule): answering an S-EMBER DEV question on a warm KV-cached D2 history costs TTFT p50 1.41 s at 11k tokens and 3.43 s at 28k, though only the 123 question tokens are evaluated; latency scales about 0.12 ms per history token and is dominated by client-side resend and parse of the full image payload (StudyD15b), not model compute (server prompt-eval 0.13 to 0.19 s). This refutes any orchestration rule that treated a warm device recall as near-free. 20 DEV questions x 2 sizes = 40; both sizes held; tj max 57 C, clock pinned (`reports/study_orin1_dense.md`).)

Last updated: 2026-11-13 (later 2) (**StudySLICE1 PART D COMPLETE (h100nvl GPU 2): ONE COORDINATED BACKGROUND LANE REMOVES BUNCHING BUT NOT THE COLD-SLICE BOTTLENECK, AND MOST OF THE GAP-AWARE BENEFIT DOES NOT SURVIVE CADENCE-ONLY KNOWLEDGE FOR 2,048-TOKEN SLICES.** D-a (exact Poisson schedule): P6 (at most one background unit in flight, EDF lane, EWMA-predicted service, slack guard, coalescing) held 1 unit in flight in all 27 lane cells and cut bunching from 90 of 275 units (no-lane control) to 0; over-budget episodic calls then overlapped only cold slices. C4a capacity stayed 10 % (P6 and P6b; D1 NO), C1b P6_1024 20 % (NO). Warm only (C2): P6 40 % ladder top vs P0 30 %, but with 57 % of escalations <= 5 s at 40 % (30 % if escalations must hold 90 %). D-b (S streams at a 0.5-s cadence, random phase, per-call half-normal jitter p90 0.044 s ASSUMED, predictor = last arrival + 0.5 s, margin 0.044 s): smooth arrivals alone raise pass-through capacity (C0 >= 5 streams = 66 %, C2 4); 1,024-token slices fit the 0.456-s gap and gain (P3_1024 C1a 3 streams, P4_1024 / P6_1024 C1b 2); 2,048-token P4 loses its known-schedule benefit (C1a 2 -> 0 streams) but keeps it at zero jitter (2), so the result hinges on the jitter assumption; a measured per-call latency trace (Orin / 5G) is the gate. The plain lane deadlocks with warm sessions under cadence (D-b C4a P6 DEGENERATE; C2 P6 not run); P6b (deadline guards, stream-ended rule, catch-up slicing; pre-registered §17a) removes the deadlock but reaches < 1 stream at C4a and 3 at C2 (P0 4), slowing escalations (p50 2 to 4.5 s). Tuned engine (E10e P1) halves pass-through p99 under cold recall but stays < 1 stream. 74 cells, 8 h 40 min GPU, not VOID; consistency PASS 6/6; mechanism verification before the sweep, amendment before P6b (report §17-22).)

Last updated: 2026-11-13 (later) (**StudySLICE1 PART C COMPLETE (h100nvl GPU 2): MANAGING WARM TRAFFIC LIKE COLD SLICES DOES NOT RESTORE EPISODIC CAPACITY.** P5 (Part B's P4 cold path + warm appends held until a predicted episodic gap, escalations gap-aligned) reaches 10 % at C4a (KV-HOST k 8 + cold r 0.05) and < 10 % at C4 (r 0.1; 0.453 s at 10 %, inside run noise of 0.007 s) against this run's warm-only C2-P0 ceiling of 30 %, and does not raise warm-only capacity (C2 P5 30 % = P0 30 %). Recalls (100 % <= 10 s) and escalations (100 % <= 5 s) meet their deadlines; escalation letters agree with P0 (99 / 95 / 100 %); warm GPU work 1.00x. Mechanism (measured): appends take longer under load than the low-load prediction (0.425 vs 0.307 s) and independently gap-released held work bunches into the same gaps, so the hold helps at 10 % and hurts at 20 % and above. Real negative for this rule; a load-aware, jointly scheduled release is untested. Coalescing UNEXERCISED (held appends release within 3.4 s, next append due at 10 s); no claim. P4 with 1,024-token slices at C1b: 25 % (Part B n 2,048: 20 %), 86.7 % <= 10 s, below the 30 % rule. 22 cells, 2 h 44 min, not VOID; consistency PASS 6/6; mechanism verification before the sweep (report §11-16).)

Last updated: 2026-11-13 (later 2) (**StudyB-baselines amendment 2, StudyLIVE1-port and StudyMAP1-bridge COMPLETE.** The headline evaluation will run LIVE on the H100 through the StudySLICE1 harness; the simulator is secondary. 33 literature and constructed arms now run unchanged in the live harness, and live cells can be scored on StudyE9c's challenge mAP.)

## Last updated: 2026-11-13 (later 2) (StudyB-baselines amendment 2, StudyLIVE1-port, StudyMAP1-bridge)

**Three studies, in order, on flash, CPU only; no GPU, no model server, no inference. The
HEADLINE evaluation is now decided: it runs LIVE on the H100 through the StudySLICE1 harness,
and the simulator is SECONDARY.**

**StudyB-baselines amendment 2 applied all eight accepted StudySIM1d fixes, plus three decisions
the application forced.** 15 of 37 runnable arms change on StudySIM1d's representative cell and
22 do not change at all. VideoStorm's L is now each configuration's own hold shift with no
backlog recursion (U(local) = -0.23957 against U(cloud/32BI_N1@0.25) = +0.01690, where it used to
be -10.234 against +0.01043), and because utility no longer depends on a_k the allocation is now
the assigned configuration's DEMAND rather than a greedy delta (ADAPTATION A5b): videostorm/maxmin
and /maxsum both go from the device-only 0.4776 to 0.5263, B9-noHost to 0.5259. covstream,
simplestream and streamscout follow DEFAULTS["episodic_mode"]. B10 IS StudySLICE1's P2 and B11 IS
P3_2048, `run.py` applies session actions before recall actions, and B11 now slices (engine
slice_steps 0 -> 14) while B10 now holds (0 -> 403 DEFERs) and misses a 5-s deadline P2 was never
designed against. **Two pre-registered stop conditions fired and both were answered by the user.**
The first: confidence-cascade and r3-streaming changed outside the declared set because they read
state the harness had never supplied; items 3 and 4 were kept for every arm (one shared
observation), the device answer is now CHARGED (StudyD8's 0.567 s, a RULE) to any arm that reads
its confidence, and the field is gated by whether the arm's PUBLISHED mechanism observes that
answer - hybrid-llm's router reads the QUERY, so it no longer receives it. The second: the
committed device-confidence tables overlapped the recall evaluation set completely, so an S-EMBER
DEV / EVAL split was pre-registered and computed (by video, sha256 order, lowest 30 % to DEV,
stratified by video-length bucket after the trigger fired): **DEV 70 videos / 243 questions, EVAL
164 / 602, overlap 0 and 0.** Every S-EMBER-fitted constant is now fitted on DEV (there is
exactly one in the suite: confidence-cascade's floor, 0.7358) and every reported recall metric is
computed on EVAL only, so **the committed StudySIM1c recall numbers are SUPERSEDED FOR
COMPARISON, not INVALID**. The fitting audit also LISTS what is measured on evaluation clips and
feeds a decision rule - the resource-quality profile and StudyE9d's V(d) and d* curves, inputs to
11 arms - reported and not fixed, because re-measuring them needs GPU time.

**The simulator sweep was re-run with the amendment-2 fixes (optional last item).** 59,940 runs and 2,997 cells on the finer ladder (fleets 1-6, 8 plus anchors 16 and 32, three mixes, deadlines 2 / 5 / 10 s, 20 seeds) in 1 h 52 min on 12 CPU workers; tables in
`reports/study_b_baselines.md` section 23, every one of them labelled **UNCALIBRATED SIMULATOR
(gate 19/29, out-of-sample fail): secondary, not headline**, with B10 and B11 excluded from
every comparison. The fixes move VideoStorm, B9-noHost, covstream, simplestream, streamscout
and the KV arms off the device-only floor 0.4776; the best cell is 0.5530 against cloud-only
0.5675; arms tie at the low fleet levels, where nothing binds, and separate from F=5 upward.

**StudyLIVE1-port: the literature baselines can run live tomorrow.** Every registry arm is
classified ORCHESTRATOR-LEVEL or ENGINE-LEVEL with its reason; the orchestrator-level arms run
unchanged inside a live loop through the same `baselines/interface.py` contract, with the
observation built from measured TTFTs, in-flight state, the server's own `/metrics` and the
harness's session bookkeeping, and with actions enacted against an OpenAI-compatible endpoint.
The orchestrator knows only the cadence-only schedule of StudySLICE1 Part D-b, never the future.
44 registry entries classified: 34 orchestrator-level, 2 engine-level (attentionstore, pensieve),
2 server configurations (tuned-engine, lmcache), 6 not built; 33 run live. All 34 exercised arms ran
against a fake OpenAI-compatible server whose delays are committed draws: **34 of 34 ok, 0 failed,
every action legal, the arrival-trace sha256 identical across arms
(6d468569bdc40df14e863f05bb122e98), 0 future reads, one decision trace per arm.** Nothing from the
stub is a measurement. The H100 run plan is written and **NOT run**: 33 arms in 3 tiers,
**39.9 GPU-hours** in full and 13.3 for the first two tiers, costed from Part C's measured 7.45 min
per cell. One integration item remains: injecting the committed body builders at the `Backend`
protocol.

**StudyMAP1-bridge: live cells can now be scored on the headline metric, and at these loads the
metric cannot see the capacity story.** The bridge replays each episodic request's MEASURED
delivery time through StudyE9b's delivery model on StudyD14b's committed traces; the live-to-D14b
mapping is an exact lookup (every live request id is a StudyD14 id that StudyD14b's manifest
carries on the coinciding grid point), and the pre-registered gate passes: the delivered arrays
are StudyE9d's own bit for bit on all 300 clips and the challenge mAP matches StudyE9c to 1 ulp
(the committed ap_fast-vs-sklearn difference). Applied to all 50 committed StudySLICE1 Part B and
Part C cells: a 9x spread in p99 delivery time across policies (C1b 10 %: P0 4.581 s against P4
0.516 s) moves challenge mAP by at most 0.0087, **every one of the 27 paired clip-bootstrap
intervals includes zero**, and the per-cell CI is 0.128 wide. The reason is the cells, not the
bridge: each touches 12 to 44 of the 300 scored clips on StudyD14's 1-s grid, and the challenge
crop reads one grid point per clip. Part D's cell design can fix all three.

## Last updated: 2026-11-13 (StudySIM1d-validate)

**StudySIM1d-validate is COMPLETE and two pre-registered stopping conditions fired.** It is an
offline analysis on flash, CPU only; no GPU, no model server, no inference.

**Part A, the arm audit.** Every degenerate-looking arm in StudySIM1c-scoped now has a named
cause. Of the 17 arms audited, five are FAITHFUL (hybrid-llm, B7-edf-feasibility, B3-best-static,
tuned-engine and always-cloud-fcfs), seven are ADAPTER BUGS and six are SCOPE INTERACTIONS, with
streamscout in both. **Eight proposed changes, affecting 12 arms, are listed in
`reports/study_sim1d_validate.md` section 1.5 and have NOT been applied**, because each
would change what an arm decides, which is the pre-registered stopping condition. The headline
ones: B9-noHost is routed to the device by its VideoStorm MaxMin component, not by the disabled
host offload, because our lag is a hold shift fed into the paper's backlog recursion; B10 never
defers and B11 never slices, so both are bit-identical to always-cloud-fcfs in engine work.
**Until those are decided, no StudySIM1c number for those 11 arms should be read as a statement
about the published method.**

**Part B, the mode-independent overlap cost.** The effect StudySIM1b measured and did not model is
real, mode-independent and BLOCKING; it is now an OFF-by-default engine option fitted entirely on
cells in no gate cell. **The calibration gate still fails** (19/29 and 11/16 against an 80 % bar),
and the N = 3 over-queueing is diagnosed as a missing sub-linear batched-prefill term - an ABSENT
link that needs a measurement nobody has taken.

**Part C, out-of-sample validation.** The simulator was run against StudySLICE1 Part B, which it
has never seen. **It FAILS in all three configurations** (15/19 = 79 % against an 80 % bar, and the
C1a policy ordering wrong), although the per-cell agreement is good. The failure is localised: the
model mis-prices a slice sharing an engine step with episodic work, in both directions.

**What this gates.** The next step is not another sweep. It is (1) a decision on the 8 Part A
proposals, (2) a committed measurement of prefill wall time against batch token count, which both
Part B's N = 3 diagnosis and Part C's failure point at, and (3) StudySLICE1 Part C (P5), which
gives a second held-out check for free. A finer fleet ladder and a separate multi-replica row are
proposed in the report and deliberately not run.


Last updated: 2026-11-12 (later 12) (**StudySLICE1 COMPLETE (h100nvl GPU 2) — SLICING RESTORES EPISODIC CAPACITY AT C1 r 0.05.** Part B (28 cells, E0, ~11k D2 cold recalls): an orchestrator that sends the cold history as 2,048-token prefix-chained slices and holds each slice until no episodic call is due within it (P4) lifts episodic capacity from < 10 % to 30 % of peak (C0 40 %), 94 % of recalls answered <= 10 s, letters unchanged, +0.5 % prefill work; recall latency rises (median 3.4-8.2 s). Not at C1 r 0.1 (20 %) or C4 (warm traffic unmanaged; all < 10 %). Holding without slicing (P2) and slicing without holding (P3) do not restore it. Report `reports/study_slice1.md` §5-10.)

Last updated: 2026-11-12 (later 11) (**StudySIM1b-hosttax and StudySIM1c-scoped COMPLETE (flash, CPU only). StudySIM1's attribution of its own gate failure was WRONG, and the baseline sweep has now run in the world where the simulator calibrates.** (1) **StudySIM1b: the KV-HOST episodic slowdown is a per-request MODE COST, not a per-overlap cost.** StudyE10b ran episodic-only ladders (k = 0 warm sessions, r = 0 cold recall) under BOTH KV modes, and those cells appear in NO StudySIM1 gate cell: with no warm session and no recall request of any kind in the system, KV-HOST is +0.0414 s slower in episodic TTFT p50 at 25 % load (CI +0.0384, +0.0456) and +0.0355 s at 50 % than the identical KV-GPU ladder, against a between-study drift floor of 0.0165 s at N = 1; at N = 3 the effect is BELOW that N's 0.0362 s floor and is reported but not used. The cost sits on the NON-BLOCKING path - it is largest at low load and gone at 75-90 % (-0.0006 / +0.0170 s), the opposite of what an added service time would do. Hypothesis (ii) is REJECTED: the OVERLAP-minus-CLEAR penalty is +0.0526 s in the KV-HOST cells and +0.0574 s in the cell-matched KV-GPU controls at N = 1, 25 %, so recall in flight costs an episodic request 0.05-0.07 s in EITHER KV mode, and the regression coefficient on the overlapping request's cached_tokens - the pre-registered proxy for KV bytes reloaded - is -0.000007 s per 1,000 tokens with a CI spanning zero, an ABSENT link under CLAUDE.md Step 2. Modelled as an OFF-by-default engine option (0.0385 s, from the held-out cells only), the gate rises from 18/29 and 10/16 to **20/29 and 11/16 (62 % -> 69 %, bar 80 %) and STILL FAILS**, so the pre-registered stopping condition fired and the study did not iterate. What it did close is the p50 gap the failure was diagnosed from: KV-HOST k = 16 at N = 1, 25 % goes 0.144 -> 0.1825 s against a measured 0.180 s, and that ladder's capacity goes 40 % -> 30 %, matching the measurement. Four of the five remaining ladder disagreements and three of the nine cell disagreements are the N = 3 over-queueing gap, reported separately and not addressed. Controls 1 and 2 pass; **control 3 FAILED as specified** - forcing the cost onto a KV-GPU cell moves both test cells away from their measurement but flips only one of two outside the +/-25 % band, because +/-25 % of a 0.383 s p99 is +/-0.096 s - and the failure is reported rather than redefined. PRACTICAL CONSEQUENCE: **enabling host offload is a fleet-wide cost, not a per-session one**, so it is a replica-level decision and its break-even is a rate, not a threshold (`reports/study_sim1b_hosttax.md`). ALSO FOUND: StudySIM1's warm-miss draw used Python's randomised hash() keyed on the touch alone, so its two KV-GPU k = 8 collapse cells were irreproducible and all five arrival seeds of a warm cell shared one miss pattern; the draw is now keyed on (cell, arrival seed) and those two values are superseded (125.257 / 124.254 -> 138.737 / 132.441 s) with no cell changing its pass/fail status. (2) **StudySIM1c: the SCOPED gate PASSED (p99 16/20 and capacity 8/10, both exactly at the 80 % bar) and the full sweep RAN - 37,800 runs, 0 failures, 37 arms in every one of 900 cells.** 3 of 40 arms are NOT RUNNABLE IN SCOPE because the host tier IS their contribution (AttentionStore, LMCache, Pensieve); B9 runs as the labelled B9-noHost with only its host-offload component disabled by the harness's availability flag, never by editing its logic. **ONE 32B REPLICA SUPPORTS A FLEET OF 2 CLOUD EPISODIC STREAMS** at the pre-registered dual target (challenge mAP >= 0.5475 and recall timely accuracy >= best static minus 2 pp), rising to 4-8 only in the recall-dominant mix where the static recall bar is lower, and only 5 of 35 deployable arms ever meet it. **Past capacity the cloud is worse than the device: 27 of 37 arms fall below the device-only 0.4776 mAP at a 16-stream balanced fleet**; arms that keep streams local sit flat at the device value across the whole ladder. Starvation ranges from 1.000 (thinking-qwenvl-atdm never answers recall in time) to 0.000 (device-only, r3-streaming, confidence-cascade). With StudySLICE1's MEASURED per-slice overhead as the primary setting and its pre-registered sweep as sensitivity, the slice overhead is immaterial here (mean mAP 0.5060 -> 0.5053 across the whole range) because B11 slices only each session's one warm promotion. Sanity checks 1-3 pass BIT-EXACTLY (all-cloud-no-recall reproduces StudyE9c's delivered cloud cell 0.5675 and all-device 0.4776, both to 0.0000e+00); check 4 fails on its 90 % bar at 32/37 and is reported, with all five wrong-way moves <= 0.0162 mAP and all five in arms that decide from observed load or a seeded draw. The hash rule was answered empirically - re-executing 3 cells x 12 arms with the current code returns the recorded numbers with 0 of 36 mismatches at zero tolerance. **NO CLAIM is made about any arm WITH host offload, and none about which baseline is best beyond the tables; our scheduler is not in this study** (`reports/study_sim1c_scoped.md`).)

Last updated: 2026-11-12 (later 10) (**StudySLICE1 PART A COMPLETE (h100nvl GPU 2) — A COLD D2 HISTORY CAN BE REBUILT AS SHORT PREFIX-CHAINED REQUESTS AT ~1-9 % EXTRA ENGINE WORK; GATE PASSED.** 40 RH4 D2 sessions (20 at ~11k, 20 at ~27k tokens), vLLM 0.31.0 defaults, prefix caching ON, RH7 uuid image-by-reference protocol (no engine change): a chain where each request = the previous cached prefix + the next n tokens of frames reuses the prefix to within 5-20 tokens every time, costs 1.093x (n 1,024) / 0.990x (n 2,048) the monolithic engine time with median per-link overhead 0.015 / -0.004 s, and gives the monolithic answer in 158 / 160 chains (both mismatches one session whose monolithic answer is itself unstable). The longest engine unit falls from 2.1 s (11k) / 6.1 s (27k) to 0.23-0.31 s (n 1,024) or 0.39-0.55 s (n 2,048). Part B (live orchestrator vs episodic capacity) awaits user decisions on the cold-recall history size and scale. Consistency PASS 6/6 for Part A (`reports/study_slice1.md`).)

Last updated: 2026-11-12 (later 9) (**StudyE10f-engine-residual COMPLETE (h100nvl GPU 2) — NO vLLM 0.31.0 SCHEDULING SETTING MEETS THE EPISODIC BUDGET UNDER COLD RECALL; THE BEST CUTS THE TAIL ~3x.** E10e's two untested combinations on its harness (P0 control reproduces E10e at 1.01 / 1.01): Q1 `--max-num-batched-tokens 2048 --long-prefill-token-threshold 512` and Q2 `--long-prefill-token-threshold 1024 --no-async-scheduling`. Both keep 40 % without recall and fall below 10 % with cold recall, so by the pre-registered rule neither removes the interference. Q1 is the first setting that moves the tail substantially (C1 p99 2.67 -> 0.92 s, p90 0.42 s; C4 4.71 -> 1.29 s) for +8-9 % cold TTFT and no warm or C0 cost; Q2 is no better than the cap alone (C1 2.01 s). Both split the cold prefill (engine phase 2.46 -> 2.63-2.66 s; held requests released mid-prefill); Q1's residual sits in the cold request's first engine steps (vision encoder + one 2,048-token alone-step). With E10c-E10e (priority, 2,048 budget, cap 512 / 1024 +- priority) the engine-side question is closed for vLLM 0.31.0: cold recall needs isolation or admission control. Consistency PASS 6/6 (`reports/study_e10f_engine_residual.md`).)

Last updated: 2026-11-12 (later 8) (**StudyE9d-delay COMPLETE; the StudyB-baselines AMENDMENT DELIVERED; StudySIM1-mixed's CALIBRATION GATE FAILED, so no baseline was run and the study stopped before its sweep.** (1) **StudyE9d-delay (flash, CPU only): the value-versus-delay curve, with all four controls EXACT.** At d = 0 the engine reproduces StudyE9b's streaming AP (point AND CI) and StudyE9c's challenge mAP bit for bit over 122 cells, so every curve is the effect of delay or blocking alone. THE CLOUD'S ADVANTAGE HAS A SHELF LIFE OF SECONDS: 32B N1 at cadence 0.5 s keeps its challenge-mAP advantage over the device until d* = 2.54 s of added delay (streaming AP at h = 0: 1.13 s); 32B N3 1.38 s and 0.74 s - a bigger payload buys LESS delay tolerance. d* IS NOT A THRESHOLD (CIs span 0.0-2.9 s; 832-1,998 of 2,000 resamples cross), the CURVE is the usable object. QUEUE, DO NOT SUSPEND: with the cloud path blocked for w seconds, queueing beats falling back to the device in 12/12 cells on challenge mAP (CI excludes 0 in 6) - a stale 32B score beats a fresh 4B score up to w = 4 s. The blocking loss is CONVEX in w above 1 s (ratios 2.1-2.8) and inside the noise floor (about 0.001 mAP) below it (`reports/study_e9d_delay.md`). (2) **StudyB-baselines amendment:** the interface gained MATERIALIZE(session, target_tokens, slice_tokens) and per-stream SUSPEND_UNTIL(t), both validated; slice_tokens = None is recorded as the PROPERTY UNDER TEST; five baselines whose papers prefetch or eagerly warm are wired to MATERIALIZE, which changes WHAT THEY DECLARE, NOT WHAT THEY ARE CHARGED (the re-run smoke record is identical field for field apart from the new counters). Recall accuracy tables built from COMMITTED per-question flags only (10 configurations x category x question-time bin, with 4B-D2 labelled the DEVICE PROXY and StudyD15's rejection carried); profiles.py now reads StudyE9d's curves. B10 blocking-aware-admission and B11 naive-slicing added: 40/40 configurations ran, respected the interface and stayed in budget, registry 44 entries. B10's deferral rule DOES NOT FIRE in the smoke replay (both sessions stay HOST-WARM) and that is stated rather than hidden behind a PASS; it is exercised by a new toy test, 24 named behaviours all reproduced. B11's per-slice overhead is UNMEASURED and every B11 result is labelled parametric until StudySLICE1 measures it (`reports/study_b_baselines.md` sections 13-15). (3) **StudySIM1-mixed: GATE FAILED - 18/29 p99 cells within +/-25 % (62 %, bar 80 %) and 10/16 capacity ladders matching (62 %, bar 80 %), so NO BASELINE WAS RUN, NO POLICY WAS COMPARED AND NO SWEEP WAS STARTED.** The simulator DOES reproduce the C0 ladder (capacity 40 % / 50 % exactly), the cold-recall head-of-line hold and the KV-GPU eviction collapse (13/13 of those cells agree or collapse-agree). It does NOT reproduce any warm-session cell, and the p50 diagnosis names why: the MEASURED episodic p50 rises 0.144 -> 0.200 s under KV-HOST k = 8 and 0.146 -> 0.211 s at C4 while the SIMULATED p50 does not move at all. A mechanism that slows the MEDIAN request slows more than half of them, so the absent link is that A RESIDENT LONG-CONTEXT RECALL REQUEST LENGTHENS EVERY STEP IT SHARES (StudyE10b named it in prose; this is the first time we have had to model it). The quantity needed - a per-step / TPOT interference cost at 8-28k context - EXISTS IN NO COMMITTED MEASUREMENT, and the two derivations available from StudyE10b's utilisation deltas differ by 2x and neither closes the gap. All three negative controls pass, no parameter was tuned, and under Rule 2 this is NEITHER a real negative NOR an inconclusive result about any baseline - it is a design-stage stop. **Two decisions are waiting on the user** (report section 10): whether StudyE10b's committed per-request rows can yield the per-step interference cost without a new GPU run, and whether to narrow the gate to the mechanisms the simulator does carry and run the sweep with the warm arms excluded and declared (`reports/study_sim1_mixed.md`).)

Last updated: 2026-11-12 (later 7) (**StudyB-baselines: ALL FIVE OPEN QUESTIONS ANSWERED by the user; no new experiment, no measurement, no baseline number changed.** (1) **The tuned engine is now StudyE10e's P1** (`--long-prefill-token-threshold 1024`, default step budget, FCFS), superseding the "later 5" entry's reading that it stays the DEFAULT: P1 does NOT restore capacity (E10e's verdict stands) but it cuts episodic p99 19-25 % at C1 and 18-30 % at C4 at no C0 capacity cost and, alone among P1 / P2 / P3, barely touches warm recall (C4 append x1.02, escalation x1.01, against P2 x1.37 / x1.30 and P3 x1.53 / x2.09); its cost is confined to cold recall (TTFT p99 +12-14 %). `tuned_engine.py` now carries `TUNED = P1` and keeps `BEST_MEASURED = E0` as a separate recorded sense, exposes all seven measured configurations and STILL RAISES on any unmeasured name; `cards/tuned_engine.md` is rewritten with E10c / E10d / E10e's verdicts and every measured cost. (2) Ekya: citation-only use APPROVED - the clone and pin stay, nothing in it is opened. (3) StudyRH8: the oracle / causal split is APPROVED as proposed. (4) **Every flagged citation is resolved**: SpotVLM-edgeVLM arXiv:2508.12638, MSAO arXiv:2604.02945, AceSpec arXiv:2609.02514, Splitwise-DRL arXiv:2512.23310 (a DIFFERENT Splitwise from ISCA'24 - both are now listed as separate rows), SAIL DOI 10.1145/3745756.3809224 (MobiSys 2026), HERMES ACL 2026 `2026.acl-long.381`, each re-checked here against the arXiv API, Crossref or the ACL Anthology; llm-d is cited AS SOFTWARE not a paper, CacheRoute is DROPPED (no identifier), and **Route2Look and Fairway are DROPPED as unverified** - OpenAlex has no record under either title, so nothing was built and nothing else was done. **QueryStream VERIFIED but NOT BUILT**: ICLR 2026 poster, OpenReview `738HjJEbml`, Apache-2.0 author-linked code pinned at `b793153403f7` - its QDP pruning is unexpressible in our action space (the R3-Streaming limitation) and its **RTAR trigger is named in the README but neither defined there nor implemented in the release**, so building it would mean inventing the firing condition; the missing component is recorded by name. (5) FlashBack and TMO: NOT BUILT for now, both still verified and recorded, TMO's clone and pin stand. The report's section 9 is now a decisions table and no citation in it is unverified (`reports/study_b_baselines.md`).)

Last updated: 2026-11-12 (later 5) (**StudyB-baselines: the one UNDER-SPECIFIED baseline is RESOLVED by StudyE10e, and the answer is unchanged - the tuned engine is the DEFAULT.** StudyE10e tested the long-prefill threshold (P1 1024, P2 512, P3 1024 + priority) and found that NO config removes the cold-recall interference: all three hold C0 capacity at the 40% ladder top like the default and all three collapse to < 10% under cold recall, five levels below their own C0. They are strictly WORSE under recall (cold TTFT p99 +12-13% at C1, +14-21% at C4; at C4 P2 appends +37%, P3 escalation x2.1), even though the caps do cut episodic p99 at C1 by about 25%. `tuned_engine.py` now exposes all seven measured configurations and keeps BEST_MEASURED = E0 on a measurement rather than a gap; its card, the report's section 0(a) and open-question 1 are rewritten. Caveat carried from StudyE10e: two documented 0.31.0 combinations were not tried (2,048-token step + 512-token cap; --no-async-scheduling). **StudyD15 also bounds the suite's device arm:** it tested the H100-4BI-stands-for-the-Orin proxy that every episodic baseline uses and REJECTED it as an exact numerical stand-in under its strict bar, while confirming a strong first-order match (Pearson / Spearman 0.943, 4 of 5 AP horizons' CIs containing 0, and where it differs the real device is slightly BETTER). The report's section 8 now records that no exact device-side number may be read off these baselines. No baseline number, cost constant or case decision changed (`reports/study_b_baselines.md`).)

Last updated: 2026-11-12 (later 6) (**StudyE10e-partial-prefill COMPLETE (h100nvl GPU 2) — THE LONG-PREFILL CAP DOES NOT REMOVE THE COLD-RECALL INTERFERENCE.** vLLM 0.31.0's `--long-prefill-token-threshold` at 1024 (P1), 512 (P2) and 1024 + priority (P3) against the default (P0, reproducing E10c / E10d at ratio 0.89-0.97) on E10c's C0 / C1 / C4 ladders (N1): every config keeps 40 % without recall and falls below 10 % with cold recall (C1 p99 at 10 %: 2.65 / 2.12 / 1.98 / 2.15 s; C4: 4.71 / 3.50 / 3.27 / 3.85 s vs 0.45 s budget), so by the pre-registered rule none removes it. The cap acts (some held episodic requests are released 1.0-1.8 s before the cold first token; p99 -18 to -30 %) but rarely binds: it is skipped while the cold request is alone, and with async scheduling (on by default) both 8,192-token steps of the 12.6k-token prefill are usually committed before an episodic request is visible (cold engine phase unchanged, 2.46-2.51 s). Cost: cold TTFT +2-23 %, warm escalation x2.1 under priority, no C0 loss. `--max-num-partial-prefills` / `--max-long-partial-prefills` do not exist in 0.31.0. Untested: cap + `--max-num-batched-tokens 2048`, `--no-async-scheduling`. Cold recall still needs isolation or admission control. Consistency PASS 6/6 (`reports/study_e10e_partial_prefill.md`).)

Last updated: 2026-11-12 (later 5) (**StudyD15-orin-nexar + StudyD15b-device-overhead COMPLETE (Jetson AGX Orin).** D15 Part A: scored all 10,660 D14 N=1 Nexar requests on the real device (llama.cpp F16) and compared with the H100 `4BI_N1` scores E9/E9b/E12 used as the device stand-in. **ACCEPTANCE = REJECTED as an *exact* numerical stand-in, but a strong first-order match** — Pearson/Spearman 0.94, trigger same-side 90–97 %, 4/5 streaming-AP horizons CI∋0, and **E9's primary rule 1 UNCHANGED**; it fails the strict bar only on h=0.5 s AP (Orin +0.017, CI excludes 0 — device *higher*) and E9 rule 2 (20→16 met cells). Cause = disclosed cross-stack numerics (H100 vLLM/BF16 vs device llama.cpp/F16), a real negative, not a defect. Implication: cite E9 rule-1 as device-validated; flag the rule-2 count (20/108) as stack-sensitive (→16/108 on true device scores). neither 0.000 %, cache_n 0 all rows, clock pinned all rows, determinism bit-identical, grey Yes-rate 0 (`reports/study_d15_orin_nexar.md`). D15b: StudyE8's per-request TTFT growth is **confirmed request-handling of resent history images, not compute** — server evaluates 1 tok/append (KV cached), prompt-eval 55–95 ms, yet TTFT grows ~9.7 ms/held frame to 5.17 s at 480 frames (matches E8 ~5.2 s); 578-frame body is 104 MB and the 60 % residual is transfer+base64 parse, decode 31 %, model 2 %. — **StudyD14b-dense, StudyE10a-full and StudyE10c-engine COMPLETE (h100nvl GPU 2).** D14b: 0.25-s Nexar score trace for 4B N1, 32B N1, 32B N3 (+ secondary 4B N3) on D14's 300 clips, integer-t scores bit-identical to D14 on 42,640 / 42,640, grey 0 / 400, integer-grid AP reproduces E9 exactly; input for an E9 / E12 replay without whole-second rounding (`reports/study_d14b_dense.md`). E10a-full: JPEG q88 on all 845 S-EMBER questions is **NOT acceptable** under the ±2 pp rule (K3 +0.83 pp [−0.24, +2.01], K1 −0.59 pp [−2.14, +0.84]; both CIs contain 0 and miss the band narrowly), so StudyE9 §16 (iii) stays UNVALIDATED for S-EMBER (`reports/study_e10a_full.md`). E10c: vLLM priority scheduling, a 2,048-token step budget, and both together restore **no** episodic capacity under any recall load (identical to the default engine in every comparable ladder) and cost none without recall; each cold K1 recall holds episodic requests until its whole multimodal prefill completes, so cold recall needs isolation or admission control, not scheduler tuning. No recall class starves (`reports/study_e10c_engine.md`).)

Last updated: 2026-11-12 (later 4) (**StudyB-baselines ADDENDUM DELIVERED (flash, CPU only) - still an engineering and literature task, still no experiment and no performance claim.** **Verification first, as the addendum required: Route2Look and Fairway DO NOT EXIST in any index we can reach**, so both are marked unverified and not built; **QueryStream, requested as a P1 component baseline, is also unfindable** (no identifier, only "ICLR 2026") and is treated the same way - all three need an identifier. Nine new paper baselines built and verified by the arXiv API or OpenAlex: ECO-LLM (arXiv:2507.09003; a DIFFERENT 2024 paper shares the name), StreamScout (arXiv:2609.00291), Preble (arXiv:2407.00023, Apache-2.0, pinned), Mooncake (ACM TOS 2025, Apache-2.0, pinned), KVFlow (arXiv:2507.07400), UniScale (arXiv:2605.30898), Thinking-QwenVL (arXiv:2604.18459), SimpleStream (arXiv:2604.02317, pinned, NO LICENCE FILE), CoVStream (arXiv:2606.22804). **Three venue claims in the addendum could not be verified and are flagged** - KVFlow's NeurIPS 2025, UniScale's ICML 2026, Thinking-QwenVL's ICLR 2026; each paper's arXiv id IS verified. Six new reconstructions with toy tests, bringing the suite to **13 reconstructions and 80 named behaviours, all reproduced**. Six constructed baselines added (B3, B4, B6, B7, B8 and **B9, the primary competitor**: four modern mechanisms running INDEPENDENTLY on the same resources with the same estimators, cost curves and host-offload facilities our scheduler will get, their conflicts resolved by a fixed documented precedence - which is exactly what a jointly-optimising scheduler is meant to beat). **The six fairness rules are ENFORCED, not documented**: `check_fairness` raises on a non-suite model, an undeclared action-space restriction or an unknown experiment; the harness charges each session's FIRST promotion to GPU-warm at the measured cold-prefill cost (no policy gets free history), charges uplink bytes per episodic cloud call, and asserts the demand trace's SHA-256 digest is identical for every policy. **38 of 38 baseline configurations ran, respected the interface and stayed in budget.** Registry now 42 entries with 24 cards, grouped by experiment (18 episodic, 13 recall, 23 mixed). CoVStream was PROMOTED from the first pass's related-work-only decision once the addendum required its construction compute to be charged; the superseded entry is kept so the change is visible, and its remaining substitution - we do not caption and do not build an entity graph - is the largest in the suite. SimpleStream's window is fitted on StudyD3's development split (1 s, AUROC 0.654), never set to a straw-man value (`reports/study_b_baselines.md`).)

Last updated: 2026-11-12 (later 3) (**StudyB-baselines SUITE DELIVERED (flash, CPU only) - an ENGINEERING AND LITERATURE task that runs no experiment, makes no performance claim and compares no two baselines.** The policy interface is defined first and ENFORCED: causal observations only (`scrub()` asserts none of 17 forbidden field names reached the policy, every epoch), one action space (`validate_action` rejects anything outside the registered domain or naming an entity the observation lacked), one set of defaults applied identically to every baseline, one shared budget checked by the harness. Hyperparameters are fitted ONLY on StudyD3's DEVELOPMENT clips (6,010 rows / 601 clips); StudyD14 / D14b stay untouched. Built: 7 naive baselines, 14 shortlist baselines (5 case B with originals cloned at pinned commits outside the repo, 7 case D with BOTH a faithful reconstruction and an adapted version, 1 case A, 1 our own), 7 reconstructions with toy tests in each paper's own abstract setting (41 named behaviours, all reproduced), 14 reviewer cards, a 24-entry registry, and a 10-minute replay smoke test in which **23 of 23 configurations ran, respected the interface and stayed in budget**. No candidate was case C: every paper without code also needed adaptation. **THREE ITEMS NEED A DECISION, reported rather than guessed:** (1) **StudyE10e does not exist** (no report, no registry row), and StudyE10c's own verdict is that no engine setting beats the default, so the "tuned engine" baseline is under-specified - `tuned_engine.py` defaults to E0 with the reason attached and RAISES on any unmeasured name; (2) **Ekya's repository has no licence file**, so it was cloned for citation only - nothing opened, run or copied, and the adapted baseline written from the paper; (3) **StudyRH8's MIX-DEMAND reads the ground-truth demand labels** (its own 2026-11-03 audit says so), which the interface forbids, so both readings ship labelled - an oracle upper bound and a causal policy RH8 never measured. One genuine interface conflict is reported not hybridised: **CoVStream** needs a caption/entity-graph representation we have never built or costed. Related work: 25 citations checked against OpenAlex, the arXiv API and publisher pages, each with a one-line reason it is not a baseline; **7 could not be verified and are flagged, not cited**, and 4 more are verified only as preprints. Five places the suite is furthest from the originals are listed in the report, all consequences of our action space (`reports/study_b_baselines.md`).)

Last updated: 2026-11-12 (later 2) (**StudyE9c-challenge-metric COMPLETE (flash, CPU only) - THE PROJECT'S "NEXAR AP" WAS THE RIGHT ORDERING ON THE WRONG SCALE.** The Nexar challenge's own evaluation (arXiv 2503.03848) - one crop per clip, horizons 0.5 / 1.0 / 1.5 s, the alert rule, fake negative event times, scikit-learn AP, unweighted mAP - computed exactly on our 300 validation clips. Chance AP is 0.407 here against the streaming metric's 0.00728, a factor of 56. Zero-latency mAP: 4B N1 0.5223, 32B N1 0.6368, 32B N3 0.6493; delivered at (ii) @25 %: device-only 0.4776, always-cloud 32B N1 0.5675. **Every sign and ordering the project derived from its streaming AP survives translation**: 32B > 4B at zero latency, delivered cloud > delivered device at both loads, load costs the cloud, and escalation buys nothing at these horizons (neither CI excluding 0) - StudyE9b's finding 7 from the other side. **What does not transfer:** absolute levels never; excess-over-chance ratios only while both arms are near chance (they match within 35 % for the delivered contrasts but compress 2x for zero-latency 32B-vs-4B, where the balanced metric is near its ceiling). **One committed finding is narrowed:** StudyE9b's "32B N = 3 falls below N = 1 once delivered" is specific to h <= about 0.25 s - N = 3 keeps 23% of N = 1's excess over chance at h = 0 but 89% on challenge mAP, and still beats device-only with a CI excluding 0. **Terminology from here: say CHALLENGE mAP or STREAMING AP, never "Nexar AP" unqualified**; neither replaces the other and only the streaming metric speaks to h < 0.5 s. Both controls pass (3,088 crops equal the committed trace exactly; label shuffling gives 1.02-1.03x the base rate); consistency 6/6. NOT leaderboard-comparable (validation clips; 3-s window, not the challenge's 10-s crop) (`reports/study_e9c_challenge_metric.md`).)

Last updated: 2026-11-12 (later) (**StudyE10d-blocking COMPLETE (h100nvl GPU 2) — THE LANGUAGE-MODEL PREFILL IS THE UNSPLITTABLE UNIT.** A cold K1 RICH recall was replaced by four variants on E10c's C1 harness (E0 default and E2 2,048-token step, N1 at 10 / 25 %): V1 PNG (control, reproduces E10c / E10b at ratio 0.99–1.09), V2 JPEG q88 (body 50.3 → 8.2 MB), V3 text-only token-matched exactly (12,645 tok, 0.036 MB, no vision encoder). **All three block on both engines** (episodic p99 at 10 %: V1 2.97 / 2.92 s, V2 3.52 / 3.17 s, V3 2.57 / 2.59 s vs 0.45 s budget), and held requests are released at the cold first token (median 0.0–0.4 s after) in 12 / 12 cells. Idle phases: frontend 1.47 s PNG / 0.75 s JPEG / 0.04 s text, vision encoder ≈ 0.2 s, LM prefill 2.17 s. So the body (a) and the encoder (b) only lengthen the window; the ~12.6k-token prefill (c) alone holds episodic scoring. V4 (encoder-cached) skipped: vLLM reuses encoder output only for an immediate repeat (−0.19 s) and evicts it after 20 episodic requests. Engine check (docs only): encoder disaggregation exists (`--ec-transfer-config`, `--mm-encoder-only`) but would not help; no chunked vision-encoder scheduling; untested lever `--long-prefill-token-threshold` (default 0). Consistency PASS 6/6 (`reports/study_e10d_blocking.md`).)

Last updated: 2026-11-12 (**StudyE9b-dense COMPLETE (flash, CPU only).** StudyE9's and StudyE12's episode and admission studies re-run on StudyD14b's 0.25-s grid with an explicit delivery model - every score has a compute time and a delivery time = compute time + the MEASURED latency, and the application reads the most recent score already delivered - in place of `d = ceil(latency)`. **Control (a) passes exactly**: with step 1 s and 1-s cadences this engine reproduces StudyE9's baselines and 108 escalation cells and StudyE12's 672 committed admission cells bit for bit (worst AP difference 0.000000000000), so the dense results are a change of delivery model and nothing else. **The link both earlier studies carried as CONSTANT is real:** 0.567 s and 0.395 s both rounded to 1 s, so the delay difference between device and cloud was identically zero in every cell of StudyE9 and StudyE12; on the 0.25-s grid the cloud's 32B N=1 answer is readable 0.25 s before the device's own and carries 3.0x its AP at h = 0 (0.0384 against 0.0126), ahead at every horizon, and the advantage survives at StudyE9's own 1.0 s call rate. **More frames is the wrong way to spend capability once the payload must cross the uplink:** 32B N=3 is the best arm at zero latency (0.0820) and falls to 0.0146 delivered, below N=1, on a 1.00 s hold shift. Decision rule 1 MET at N=1, not at N=3, as in StudyE9. Decision rule 2 met in 154 of 360 cells under its unchanged absolute 0.01 AP tolerance but 40 under the scale-matched 0.0026 - a property of a rule written for a 4x coarser grid (chance AP 0.00728 here against 0.0281 there), pre-registered as such. Study 2's admission rule is NOT MET at neither of the two pre-registered horizons; the device score alone is the admission signal, and P-score separates from P-random in 1 of 18 cells - a REAL NEGATIVE (predictor AUROC 0.648-0.764 out of sample, P-oracle headroom present). All controls pass; consistency 6/6. Limitations labelled: the device's 0.75 s saturated cadence is extrapolated from StudyD8's measured 1 Hz, no cloud capacity limit is modelled, and setting (iii) JPEG is transport only (`reports/study_e9b_dense.md`).)

Last updated: 2026-11-12 (**StudyD14b-dense, StudyE10a-full and StudyE10c-engine COMPLETE (h100nvl GPU 2).** D14b: 0.25-s Nexar score trace for 4B N1, 32B N1, 32B N3 (+ secondary 4B N3) on D14's 300 clips, integer-t scores bit-identical to D14 on 42,640 / 42,640, grey 0 / 400, integer-grid AP reproduces E9 exactly; input for an E9 / E12 replay without whole-second rounding (`reports/study_d14b_dense.md`). E10a-full: JPEG q88 on all 845 S-EMBER questions is **NOT acceptable** under the ±2 pp rule (K3 +0.83 pp [−0.24, +2.01], K1 −0.59 pp [−2.14, +0.84]; both CIs contain 0 and miss the band narrowly), so StudyE9 §16 (iii) stays UNVALIDATED for S-EMBER (`reports/study_e10a_full.md`). E10c: vLLM priority scheduling, a 2,048-token step budget, and both together restore **no** episodic capacity under any recall load (identical to the default engine in every comparable ladder) and cost none without recall; each cold K1 recall holds episodic requests until its whole multimodal prefill completes, so cold recall needs isolation or admission control, not scheduler tuning. No recall class starves (`reports/study_e10c_engine.md`).)