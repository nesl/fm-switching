# DRAFT replacement for the `StudyCOVEX-harden` row in research/EXPERIMENTS.md

**NOT APPLIED. Verdict and status are the user's call, so this is drafted for review and
`research/EXPERIMENTS.md` is untouched.** The committed row at line 264 covers D124 only and is
stale by roughly 40 commits (D125 to D134). Fields below are offered in the row's column order.

---

## claim (append to the existing text)

Extended under D125 to D134 from an audit of COVEX v1.0 to a continuing EVALUATOR role across
v1.1, v1.2, v1.3-scarcity, the v1.3-fast release `d944361`, covex-v2, and the 19 to 22 ported
published arms. Still NEW FILES ONLY, every hook a wrapper installed from inside `policy/audit/`
and removed afterwards, every result from a pinned worktree with a stated HEAD, development seeds
0, 4, 5 and 6 only, with seeds 1 to 3 refused by name.

## n / sweep (replace)

196-cell D131 grid (7 sizes x 4 seeds x 7 arms) plus a 242-cell denominator post-process; 124,354
candidates in the blind-spot audits; 12,898 candidate pairs in the state-value entry-point audit;
8,120-decision switch-moves comparisons; 41-question feasibility and task-value joins.

## verdict (DRAFT)

**GATE: FAIL, at every version and at every size, on both axes.** Against the D131 bar, which
includes the ported published arms, COVEX does not beat the best baseline at any size on either
axis and meets the D71/D82 capacity conjunct in **0 of 28 cells** against eco-llm's 10. No
`harden GATE PASS` string was ever emitted.

**The transferable result is the MECHANISM, not the gate.** (1) The crossover is located at **10
to 12 devices** and is sharp, all four dev seeds transitioning together: llf falls 0.81 to 0.41 and
edf C=8 0.86 to 0.17 on robot on-time, while COVEX is flat and has no collapse. (2) The robot axis
is a **queueing** problem, not a GPU-budget one: identical 38 recall requests at identical ~2.4 s
service differ only in delay against a 5.0 s deadline, 2.34 s for eco-llm against 5.81 s for llf,
and relaxing the deadline to 7.0 s triples llf's deliveries. (3) The **idle-GPU feasibility
ceiling** is 0.8871 at 32 devices and below 0.90 in 11 of 28 cells, so under D132 the headline
robot target is p=0.90 over FEASIBLE questions; that correction nearly doubles every baseline's
capacity passes and moves COVEX **0 to 0**, so its gap is scheduling and not arithmetic.
(4) **Representation quality is NOT monotone in cost**: committed 32B tables put D2 above RICH on
4 of 8 categories (location_trace +17.2 pp) and below on 3 (visual_detail_recall -7.9 pp), while
the trace-weighted aggregate agrees to +0.14 pp by cancellation. (5) This robot workload is
**history-insensitive**: `recent_covers_frac` 0.8852, full history worth +1.18 pp overall with a CI
including zero and +17.5 pp only on the 11.5 percent stratum where RECENT misses, the opposite of
LoCoMo's -24.1 pp.

**SIX DEAD OR ABSENT CHANNELS**, each established by the absence of a READER rather than of a
reference: the action `order` field; `desired_tier`, written twice and read nowhere, so live2
models KV OCCUPANCY but not KV PLACEMENT (a harness gap, NOT scoped out: FORMULATION.md line 118
names selective materialization as a policy the optimizer should discover);
`RecallAction.representation`, fixed at `e924005`; B2's z[RC], which reaches 543.58 and no
decision; RCprio, which never fires even at a 5.0 s slack; and spec 5.3 state value, which is
non-zero in 96.6 percent of branches and **cancels exactly** between them in 12,898 of 12,898
candidates.

**ERRATA AGAINST MY OWN WORK, all recorded in place rather than deleted:** E1 (dead-writer regex),
E2 (dispatch labelled as delivery), E3 (F-A7 reversed at 16 devices under delivery), E4 (an
inference presented as a consequence), E5 (a fixed-signature wrapper), E6 (the screen assumed
optimistic, measured pessimistic), E7 (my own int cast coerced to bool), E8 (an eyeball sum, 12 of
28 against a counted 10/9/9), plus a withdrawn 16-device pass, a withdrawn 32-device win, and a
withdrawn "UPPER BOUND" label.

## status (DRAFT)

**SCREEN AND AUDIT COMPLETE for D124 to D134 as of 2026-11-19. NOT a measurement of policy
behaviour: every number is a DRY RUN and is labelled as such.** Two caveats qualify every row:
**no memory limit was enforced** (`gpu_kv_tokens` handed to arms and never enforced, no automatic
eviction), and **the comparator moved** at `e924005`, eco-llm improving in all four bar-check cells
with s4 n=16 flipping the capacity conjunct FAIL to PASS, while remaining **too low** because
eco-llm plans at 0.35 x history and is charged min(467, history). **The full-grid re-score is HELD
pending session 1's memory-pressure work**, to be fired once against one clean regime boundary.

## consistency_check (DRAFT)

Six-check protocol run. Check 1 (cross-check) FAILED and was reported rather than worked around:
the stated +17.5 pp full-history premium is a SUBSET quantity, `K1_minus_K3` being +1.18 pp with a
CI of [-0.0152, +0.0389] that does not exclude zero, against `K1_minus_K3_recent_misses` at +17.5
pp. Check 3 (distribution) produced four catalogued misleading-column signatures plus two more.
Check 4 (definition) produced the dispatch-vs-delivery resolution, the llf C=4-vs-C=8 relabelling,
and the RECENT 467-vs-0.35 resolution. Check 6 (proxy validity) refused the dry robot-accuracy
column outright because `cloud_letter` is a placeholder `"X"`.

## mechanism_verification (DRAFT)

Applied throughout and it is what produced most of the findings. Two switches classified
**INCONCLUSIVE under Rule 2 rather than as negatives** (B2 and RCprio, each changing 0 of 8,120
decisions with the switch verified to reach the arm). The v1.3 scarcity price classified CONSTANT
under Step 2 (mu p50 and p90 both 1.000 at 8 and 16 devices). A five-category deviation taxonomy
recorded: cancelled-by-geometry, unexpressible, unscorable, unexercised, and
fired-and-did-not-help, with only the last a finding about COVEX.

**Proposed protocol amendment, for the user:** Step 2 as written cannot see a write-only field. A
quantity that is set and never read is non-zero, varies across conditions and is instrumentable, so
it passes Step 2, and the Step 4 negative control passes too because disabling it correctly
collapses to the null. **For every quantity named as implementing a causal link, show the READ that
consumes it, not merely that it is set.** Second amendment, on this session's recommendation and
already adopted by the coordinator for all three sessions: **run `switch_moves.py` on every NEW
switch BEFORE it is scored**, not after a suspicious null; five plumbing faults in three nights
were each caught only after a null had been produced.

## outputs (append)

31 result files under `results/orchestration/live2/covex_harden/`, all indexed in
`results/INDEX.md` with their findings; report `reports/study_covex_hardening.md` sections 0 to 33.
