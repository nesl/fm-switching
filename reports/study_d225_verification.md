# D225 (5) VERIFICATION OF THE CONFORMANCE MATRIX

Register of this file: an INDEPENDENT re-derivation. This session did not write
`research/conformance_matrix.md` or `experiments/orchestration/live2/d225_switch_diff.py` and has not
edited either. D225 (5) requires the matrix be verified by a session that did not build it; D225 (6)
makes the matrix the freeze gate, so this file is a check on the gate's credibility and not a summary
of it.

Every claim below is marked **CONFIRMED** (re-derived here, with the command), **REFUTED** (with the
command and its output), or **NOT CHECKABLE** from what the row gives, which is itself a D225 finding
because D225 requires a reader to check each cell without asking the author.

## 0. WHAT WAS VERIFIED, AND AGAINST WHAT

| item | value |
|---|---|
| artefacts verified | `research/conformance_matrix.md` (824 lines), `experiments/orchestration/live2/d225_switch_diff.py` (409 lines) |
| published at | `4a73e12537cb74008de26c2ff046ae46dafd6de3` (2026-11-24 09:22:25 -0800) |
| matrix's own code pin | `c5e7bb4926a23c68e12d22c3f337462897408d51` |
| staleness checked against | `origin/main` = `704d21724bc33e9866aeb1ffbad4c08cc513e02b`, re-resolved 2026-11-24 17:46 UTC, **19 commits after `4a73e125`** |
| how files were read | `git show <sha>:<path>` only, plus a private export of `4a73e125` turned into a real checkout. Nothing read from a shared worktree |
| script re-run in | a fresh export of `4a73e125` with `git init` plus an objects alternate and `update-ref HEAD 4a73e125`, so `git rev-parse HEAD` resolves and the run is attributable |

**On worktrees, because the hazard is real and the figure is not one figure.** Two stale trees are in
play and they are not the same tree. `/home/pragya/Desktop/FM-switching` is at HEAD `17bdf159`, which
is what the matrix measured. `/tmp/claude-1001/mapwt` is at HEAD `47237572` and was **941 commits
behind `origin/main` at 2026-11-24 17:41 UTC**, not the ~1,800 of the briefing. Any commits-behind
number must name its tree as well as its timestamp. Nothing in this report was read from either.

**Tally: 26 claims CONFIRMED, 6 REFUTED, 4 NOT CHECKABLE.** No finding requires escalation: nothing
found here contradicts a D-row in a way that changes a posted result.

## 1. THE SWITCH-DIFF SCRIPT, RUN HERE

    cd <export of 4a73e125>
    python -I experiments/orchestration/live2/d225_switch_diff.py \
        --live2 experiments/orchestration/live2 \
        --design-log research/policy_design_log.md --json out.json
    EXIT=0

**CONFIRMED, exactly.** `tree sha ... : 4a73e12537cb74008de26c2ff046ae46dafd6de3`.

| quantity | matrix claims | this run | agree |
|---|---|---|---|
| exit status | 0 | **0** | yes |
| total differences | 56 | **56** | yes |
| rung0 -> rung1 | 10 | **10** | yes |
| rung1 -> rung2 | 16 | **16** | yes |
| rung2 -> rung3 | 17 | **17** | yes |
| rung3 -> rung4 | 13 | **13** | yes |
| unattributed (defects) | 0 | **0** | yes |
| attribution D-rows absent from the design log | not claimed | **none** | - |

The matrix asserts this result at `c5e7bb49` from a tree hash rather than a re-run, and says so. That
reasoning is sound and is confirmed in section 3 below. The run above makes it a measured result at a
fourth sha. Note `4a73e125`'s `live2` tree is `e2e4b56a`, not the `23233f43` of the three pinned shas,
because `4a73e125` is the commit that adds this script to `live2`; no other file in `live2` differs.

**A safeguard that fired on me, unprompted, and deserves recording.** My first run was from a plain
`git archive` export with no `.git`. The script printed `sha UNRESOLVED (git -C ... rev-parse HEAD
exited 128). Every switch value below is therefore UNATTRIBUTABLE TO A COMMIT: run this inside a real
checkout, not an exported snapshot, before citing it in the conformance matrix.` Section 7's claim
that it "refuses to print a bare unknown sha" is **CONFIRMED by independent trigger**. It still exits
0 in that state, which is correct against its documented contract (exit status encodes unattributed
differences only) but means a careless caller can get an unattributable 56 with a zero exit.

### 1.1 The three near-misses the builder flagged

**Near-miss 1, the composition chain. CONFIRMED.** The script prints the chain it walked at each rung
and it reaches `_b7` at every one:

    rung0  covex-v6-base         HybridArm         chain=arm -> arm._b7
    rung1  covex-v6-rules        V5Rules2Arm       chain=arm -> arm._base -> arm._base._b7
    rung2  covex-v6-state-final  V6StateFinal      chain=arm -> arm._rules -> arm._rules._base -> arm._rules._base._b7
    rung3  covex-v6-fair-final   V6FairFinalWired  chain=arm -> arm._rules -> arm._feed -> arm._rules._base -> arm._rules._base._b7
    rung4  covex-v6-final        V6Final           chain=arm -> arm._rules -> arm._feed -> arm._rules._base -> arm._rules._base._b7

**No rung's switch set is empty**: 58 / 65 / 75 / 85 / 95 switches, which also confirms the figures
section 6.1 quotes. Re-deriving monotonicity myself over the resolved surface, the number of switches
that are `True` at a lower rung and `False` or absent at a higher one is **0**, so section 6.1's "0
breaks" is CONFIRMED. The only presence change in the downward direction is `_cf`, `None` at rung 2
and absent at rungs 3 and 4; that is a cached engine handle which is a scalar `None` before
`_cf_engine()` runs and a live object afterwards, so rungs 3 and 4 have more, not less. The script
prints that row rather than hiding it, attributed to "D99 (3), D116".

Minor notation point, not a defect: section 2's chain column writes rung 1 as `arm -> arm._base ->
arm._b7` and omits the `_b7` leg for rungs 2 to 4. `arm._b7` resolves to the same object through
`__getattr__`, so nothing is wrong, but the script's own printed paths are the exact ones.

**Near-miss 2, `sw` is a dict. CONFIRMED.** Rung 0 has 58 switches, among them all six of
`sw[c1]` to `sw[c6]`, so the scalar-only failure mode is not present. Re-derived values, identical at
all five rungs, which is section 6.1's read-from-code inheritance proof for rung 0's whole mechanism
set:

| switch | R0 | R1 | R2 | R3 | R4 | identical |
|---|---|---|---|---|---|---|
| `sw[c1]` | True | True | True | True | True | yes |
| `sw[c2]` | True | True | True | True | True | yes |
| `sw[c3]` | False | False | False | False | False | yes |
| `sw[c4]` | False | False | False | False | False | yes |
| `sw[c5]` | True | True | True | True | True | yes |
| `sw[c6]` | False | False | False | False | False | yes |

**Near-miss 3, nothing silently exempted. PARTLY REFUTED. This is finding R2 and R3 below.** The
`INTERNAL_OF` half is CONFIRMED: `_feed_gain`, `_feed_on`, `_feed_ordering`, `_feed_split`, `gain`,
`_pd_w_source` and the declared readers all still print, each marked `via <public switch>`, so no twin
is suppressed. The `NOT_SWITCHES` half does not hold as section 7 states it.

## 2. FINDINGS

### R1. REFUTED. `d218_prereg.json` exists. (10.1, Group A)

10.1 states: "`d218_prereg.json`, which D221 names as the pre-registration record, is not present in
`experiments/orchestration/live2/`."

    $ git ls-tree -r --name-only 4a73e125 | grep d218_prereg
    results/orchestration/live2/d218_device_answers/d218_prereg.json
    results/orchestration/live2/d218_device_answers/d218_prereg_addendum.json

Both files are present at `4a73e125` and at `origin/main`. D221 reads "Record of pre-registration:
d218_prereg.json (the earlier of two, identical in substance)", and there are exactly two. The
sentence is literally true of the `experiments/` path and false of the claim a reader takes from it.
It is also the wrong place to look by the repo's own convention: CLAUDE.md's layout schema puts every
result JSON under `results/<purpose>/`, so `experiments/orchestration/live2/` is where this file
should NOT be. **The substance of 10.1 is unaffected** and is separately CONFIRMED below, so 10.1
stays a valid gate row with one evidence item struck.

### R2. REFUTED. 18 of 19 bookkeeping exemptions do not name a read site.

Section 7 states: "Everything exempted as bookkeeping (`_pd_rows_key`, `_q_cache`, the counter lists)
is named in `NOT_SWITCHES` with its read site, so the exemptions are checkable one by one."

`NOT_SWITCHES` has **19** entries. Exactly **one**, `_pd_rows_key`, carries a read site
(`arms_v6cf.py:203-204`). The other 18 are named without one. Named-but-unsited is a weaker property
than the sentence claims, and naming the read site is the whole of what makes an exemption checkable
without asking the author.

### R3. REFUTED. `dry` and `dry_margin` are switches, not bookkeeping.

`NOT_SWITCHES` is introduced as "run-time state or bookkeeping, not switches". `dry` and `dry_margin`
are in it. They are neither:

    arms_v6state.py:184   self.dry = bool(dry)
    arms_v6state.py:185   self.dry_margin = dry_margin
    arms_v6state.py:208   kw: Dict[str, Any] = dict(dry=self.dry, dry_margin=self.dry_margin, ...)
    arms_v6state.py:256   margin="DRY_OVERRIDE" if self.dry else "cf_margin.MARGIN_CF",
    arms_v6state.py:257   scorable=not self.dry),

A flag that overrides the counterfactual margin and marks a cell unscorable is a behaviour-changing
switch. Re-running `resolve()` with `NOT_SWITCHES` emptied, the switch surface is 58 / 65 / **78 / 89
/ 104** rather than 58 / 65 / 75 / 85 / 95, and nine exempted names change between adjacent rungs:
`dry`, `dry_margin`, `_q_cache_key` (rung1 -> rung2), `_planner_reads_feed_declared` (rung2 -> rung3),
`_pd_rows_key`, `pd_trace_kept`, `pd_trace_crossed`, `rd_trace_kept`, `rd_trace_crossed` (rung3 ->
rung4).

**Consequence, stated in the right register.** Every one of those nine changes is `<ABSENT>` to an
inert value (`False`, or `None`), never a value change, so **no decision differs and the "0
unattributed" verdict is not endangered**. What is wrong is the census: the switch surface is
under-counted by two genuine switches on the reported arms, and the gate's stated purpose is that
every switch that differs carry a D-row. Including them makes rung1 -> rung2 18 and the total 58. The
remedy is one line: move `dry` and `dry_margin` to `ATTRIBUTION` with their D-row and a note that they
are False in every reported cell.

### R4. REFUTED. The cell census is pinned to `2e5cd9a5`, not to `c5e7bb49`.

Section 0 says "every file:line below re-read at `c5e7bb49`" and "committed cells read from ... **286
cells** carrying `coordinator_result.json`", and justifies the re-pin with four tree hashes. Those
four hashes are CONFIRMED (section 3). **`results` is not among them**, and its tree hash differs at
all three shas: `2db1b516` at `2e5cd9a5`, `35974e6f` at `a4eaf9bc`, `70344dd3` at `c5e7bb49`. Every
census figure in the matrix matches the FIRST sha exactly and is off by one at the published pin:

| census, under `frozen_test/runs/` | matrix | `2e5cd9a5` | `a4eaf9bc` | `c5e7bb49` |
|---|---|---|---|---|
| cell directories | 334 | **334** | 335 | 335 |
| `coordinator_result.json` | 286 | **286** | 287 | 287 |
| `decision.jsonl` | 39 | **39** | 39 | 39 |
| `request.jsonl` | 16 | **16** | 16 | 16 |
| `outcomes.jsonl` | 9 | **9** | 10 | 10 |

Five for five at `2e5cd9a5`. The tree-hash argument re-pinned the CODE register and carried the
OBSERVED register forward silently, which is the register slip the matrix itself warns about.

**Mitigation, and it is a real one.** The whole difference is a single added cell:

    $ git diff --name-status 2e5cd9a5 c5e7bb49 -- results/orchestration/live2/frozen_test/runs | grep -v llf_n8_s4
    (no output, rc=1)

Everything that changed is `llf_n8_s4_1200s_h27_3t_L3_epg_rq30`, a baseline. **No ladder cell changed**,
so every OBSERVED number the matrix states about the 20 ladder cells is sound as published. Also,
section 0 says the six intervening commits changed "two cells"; only **one** cell directory changed
under `runs/`. The remedy is one sentence, not a re-census.

### R5. REFUTED. 10.8's `kept_warm` range excludes a zero that exists.

10.8 argues the retention path "demonstrably works: `kept_warm` is 173 to 4,300 across the ladder
cells". Read from the cells at `c5e7bb49`, the rung-2/3/4 ladder values are:

| arm | s4 | s5 | s6 | s7 |
|---|---|---|---|---|
| `covex-v6-state-final` | 3650 | **0** | 1828 | 2435 |
| `covex-v6-fair-final` | 4300 | 175 | 1835 | 2434 |
| `covex-v6-final` | 4111 | 173 | 1829 | 2441 |

The true range is **0 to 4,300**. `covex-v6-state-final` s5 retained nothing, and that cell is exactly
a cell in which the mechanism did not demonstrate that it works. The stated minimum of 173 is the
second-smallest value. This is a distribution-reporting slip in the one Group B row whose argument
rests on the spread.

### R6. STALE, as anticipated. 10.5 is closed for every site D223 (2) names, with one residual.

10.5 says "All four sites still literal: `hybrid/hybrid_arm.py:157`, `arms_v6cf.py:86`,
`arms_v6fair.py:90`, `d170_overlimit.py:33`". At `origin/main`, after `a43ad7f7` and `2e4c5961`:

| site | `4a73e125` | `origin/main` |
|---|---|---|
| `hybrid/hybrid_arm.py` | `:157 CONTEXT_LIMIT_TOKENS = 32768` | **gone**, `:162 import context_limit as CL` |
| `arms_v6cf.py` | `:86 CONTEXT_LIMIT_TOKENS = 32768` | **gone**, `:90 import context_limit as CL` |
| `arms_v6fair.py` | `:90 limit_tokens=32768` | **gone**, `:52 import context_limit as CL` |
| `d170_overlimit.py` | `:33 LIMIT = 32768` | **still literal** |

D223 (2) names exactly three sites, `arms_v6cf.py:86`, `arms_v6fair.py:90` and
`hybrid/hybrid_arm.py:157`, and all three are closed. The fourth is the matrix's own addition and is a
reporting script, not a policy site. Two cautions. The surviving mentions in the three policy files
are code COMMENTS recording the old defect, so a future grep for `32768` will re-find them and must
not re-report them. And `d170_overlimit.py`'s committed output
`frozen_test/d170_overlimit.json` is computed against a 32,768 bar while a 0.5x engine serves 31,472;
it is superseded in practice by `d223_overlimit_counts.py` and `results/orchestration/live2/d223_overlimit_counts.json`.
**No posted result changes**, which is 10.17's own finding and it still holds: 1x is byte-identical by
D223 (2) and every covex 0.5x cell has `n_errors = 0`.

### N1. NOT CHECKABLE as written. The OBSERVED reproduction path is wrong for three Group B rows.

Section 1 defines the OBSERVED register as "open that cell's `coordinator_result.json` -> `arm_stats`".
Following that instruction for 10.8's counters returns nothing: `offloaded`, `over_cap`, `evicted` and
`kept_warm` are absent from `arm_stats` and from `counts`. They live at

    coordinator_result.json -> memory_pressure/enact_placement_totals/{offloaded,kept_warm,evicted}
    coordinator_result.json -> memory_pressure/pressure/epochs_over_cap

and `over_cap` is spelled `epochs_over_cap` in the file. This is not a small matter of taste: under the
matrix's own section-1 trap 1, a key absent from `arm_stats` reads as "never fired in this cell", so a
verifier who follows the stated path gets a confident false negative on the headline mechanism of rung
2. **Once the real path is used every number confirms**, which is why this is NOT CHECKABLE rather than
REFUTED. The briefing noted the twin error in the other direction for the `pd_` counters, so the
document has this class of path defect twice.

### N2. NOT CHECKABLE. The 20 ladder cells are never listed.

"20 of 20 ladder cells", "all 16 cells", "all 20 ladder headers" and "all four of its cells" all rest
on a cell set the matrix never enumerates. I could identify 12 unambiguously, the rung-2/3/4 arms at
`n16_s[4-7]_1200s_h27_3t_L3_epg_rq30`. The other 8 I cannot: at `c5e7bb49` there is **no**
`covex-v6-base_n16_s[4-7]_..._L3_epg_rq30` and **no** `covex-v6-rules_n16_s[4-7]_..._L3_epg_rq30`
cell. Rung-0 and rung-1 1x cells exist only at n8, n12 and n20, and `covex-v6-rules` has five 1x cells
(n8 s4, n12 s4, n12 s5, n20 s4, n20 s5) against 10.15's "all four of its cells". Listing the 20
directory names once would close this and several rows depend on it.

### N3. NOT CHECKABLE to the stated precision, and immaterial. The 418 denominator.

Section 0's "35 of origin's 418 `coordinator_result.json`, 8.4 percent" for
`/home/pragya/Desktop/FM-switching`. The **35 is CONFIRMED** at HEAD `17bdf159`, and the sharper fact
is that **0** of them are under `frozen_test/runs/`, which is the hazard itself. The denominator I
measure across all of `results/` at `c5e7bb49` is **424**, not 418, giving 8.25 percent.

### N4. NOT CHECKABLE here, and correctly labelled by the matrix. Section 7 at `c5e7bb49`.

The matrix states plainly that the 56/0/exit-0 result is asserted at `c5e7bb49` from the tree hash and
that a re-run was attempted and died in `git checkout`. The tree-hash reasoning is confirmed in
section 3. My run is at `4a73e125`. No session has run the script at `c5e7bb49` itself, and the matrix
does not claim one has.

## 3. CLAIMS CONFIRMED BY RE-DERIVATION

**Section 0's tree-hash identity. CONFIRMED, all twelve hashes.**

| sha | `live2` | `baselines` | `policy` | `experiments/lib` |
|---|---|---|---|---|
| `2e5cd9a5` | `23233f43` | `e1717290` | `64f7a284` | `46a6bf61` |
| `a4eaf9bc` | `23233f43` | `e1717290` | `64f7a284` | `46a6bf61` |
| `c5e7bb49` | `23233f43` | `e1717290` | `64f7a284` | `46a6bf61` |

`git rev-list --count 2e5cd9a5..c5e7bb49` is **6**, matching "the six intervening commits". The
argument that a tree hash settles identity where an empty diff cannot is sound and the conclusion for
the CODE register holds. It does not extend to `results` (finding R4).

**The design log has 229 rows, and the briefing's 227 is wrong. CONFIRMED.** Parsing every
`| D<n> |` row of `research/policy_design_log.md`: **229 rows, 229 distinct, no duplicates**, numeric
D1 to D227 with **no gaps**, plus the two lettered rows `D155a` and `D156a`. This is exactly section
0's "229 rows: D1 to D227 plus D155a and D156a", stated explicitly, so the matrix does say which row
count it is against. `D227` is present, landing at `c5e7bb49` (09:10:47) which is **before** the
matrix commit (09:22:25), so the matrix was built against a log that already contained it. **No `D228`
row exists**: the maximum is D227. The log blob is byte-identical, `270c5347`, at `c5e7bb49`,
`4a73e125` and current `origin/main`.

**The partition. CONFIRMED in full, independently.** Parsing the four class lists out of sections 3
and 3.2 and intersecting against the 229 parsed log rows:

| quantity | matrix | re-derived | agree |
|---|---|---|---|
| M | 140 | **140** | yes |
| P | 48 | **48** | yes |
| E | 31 | **31** | yes |
| W | 14 | **14** | yes |
| sum of four | 233 | **233** | yes |
| union | 229 | **229** | yes |
| rows in the log and in no class (unclassified) | 0 | **0** | yes |
| strings in a class that are not real log rows | 0 | **0** | yes |
| `M & P` | `{D190}` | **`{D190}`** | yes |
| `M & E` | `{D209, D213}` | **`{D209, D213}`** | yes |
| `M & W` | `{D84}` | **`{D84}`** | yes |
| `P & E`, `P & W`, `E & W` | all empty | **all empty** | yes |
| 233 - 4 | 229 | **229** | yes |
| 3.2: 48 + 31 + 14 | 93 | **93** | yes |
| 3.2: 93 - 4 dual-class | 89 | **89** | yes |

The four faults the builder reports in its own first attempt (D72, D139 and D163 left unclassified; a
non-existent "D227" in the E list; four undeclared overlaps) are all absent from the published
version: D72 and D139 are in M by the stated "Plus" clause, D163 is in P, D227 is a real row and is in
M, and the four overlaps are declared and are exactly the four I find. The partition is a genuine
partition of the real log.

**One arithmetic typo, self-contradicted in the same section.** The M paragraph ends "Plus D72 and
D139, which the mu row and the LH-REQ row of section 4 cover: **139 in all**". The enumerated names
before that sentence number **138**, and 138 + 2 = **140**, which is what the section-3 table says and
what the union requires. "139" is an off-by-one in prose only; the table is right.

**OBSERVED claims, read from committed cells at `c5e7bb49`. CONFIRMED, exactly.**

| matrix claim | row | re-derived | agree |
|---|---|---|---|
| `pd_kv_bound_by_belief` equals `pd_decisions` at 302 / 299 / 293 / 259 | 10.9 | 302/302, 299/299, 293/293, 259/259 | yes |
| the belief bound 1,153 of 1,153 decisions | 10.9 | 302+299+293+259 = **1,153** | yes |
| `pd_kv_bound_by_engine_metric` absent in all four rung-4 cells | 10.9 | absent in all four | yes |
| `guard_by_backlog` present and zero everywhere | 10.10 | 0 in every ladder cell carrying it | yes |
| `guard_by_lag` at rung 4 is 80 / 32 / 117 / 22 | 10.10 | **80 / 32 / 117 / 22** | yes |
| `offloaded` = 0, `over_cap` = 0 on the ladder | 10.8 | 0 in all 12 rung-2/3/4 cells, `evicted` 0 too | yes |
| `attentionstore-prefetch` kv0.5 shows `offloaded` 35, `evicted` 6 | 10.8 | s4: `offloaded` 35, `evicted` 6, `kept_warm` 10,547 | yes |
| no reduced-memory cell for rungs 2, 3 or 4 anywhere | 10.8 | **0** `kv0.*` cells for the three arms | yes |
| `arm_stats` sizes 78 / 81 / 128 at s4 for rungs 2 / 3 / 4 | 6.1 | **78 / 81 / 128** | yes |
| zero decision logs for the three final rungs | 11 | 0 `decision.jsonl`, 0 `request.jsonl`, 0 `outcomes.jsonl` | yes |
| 30 stub cells with no `arm_stats` | 11 | **30** of 287 | yes |

The 10.8 control is the one worth naming, because validating the control and not only the result is
where this kind of check usually fails. `attentionstore-prefetch` at kv0.5 is the arm that proves the
offload channel is not broken, and it reads `offloaded` 35 and `evicted` 6 as stated. The zeros on the
ladder are therefore an unexercised mechanism and not a dead instrument, which is what 10.8 claims.

**The "do not pool the zeros" discipline was kept. CONFIRMED.** 10.8 names three distinct causes for
one shared `offloaded = 0` (rung 0 wholly inert for want of a state layer, rung 1 tracking residency
and evicting once at s7, rungs 2 to 4 unexercised) rather than reporting a single zero. 10.15 goes
further and **declines to assign a Rule 2 class at all** to the rung-1 C2/C5 gap, on the stated
ground that sparse `arm_stats` cannot distinguish "did not fire" from "not reported", and says so
explicitly rather than quietly picking one. Section 6.3 assigns a separate class per row
(unexpressible, unexercised, ABSENT, not built) instead of one label for the group. This is the
discipline the briefing asked about and the matrix has it.

**Sections 8 and 9, spot-checked at `c5e7bb49`. CONFIRMED.** `DASH_DEADLINE_S = 1.0` at
`hybrid/hybrid_arm.py:59`; `RECENT_TOKENS = 467` at `:70`; `CONTEXT_LIMIT_TOKENS = 32768` at `:157`;
the `sw` dict at `:188`; `GUARD_LAG_S_DEFAULT = 2.0` at `arms_v5rules2.py:81` and
`GUARD_BACKLOG_DEFAULT = 100` at `:83`; `WARM_AHEAD_SLICE_TOKENS = 1024` at `engine_actions.py:96` and
`WARM_AHEAD_TARGET = 10 ** 9` at `:97`. The **citation trap reproduces exactly**: `:95` is
`W2_LAXITY_FRACTION = 0.3  # D143 ruling B`, one line above, so a proximity grep does attribute D143
to both constants, and section 8's warning that a proximity grep is not an attribution is correct.
`HARM_FORM_DEFAULT` is **declaration-only as claimed**: three occurrences in `cf_protect_defer.py`,
`:336` the definition, `:387` a dict value and `:639` the describe block, and no branch anywhere.
Miscitation 2 confirmed: `v5/cf_objective.py:220` sets `ON_TIME_TARGET` to 0.90 for robot, dashcam and
single_shot with `:221 ON_TIME_TARGET_SOURCE = "D133 robot headline ... applied per type"`, and D133
sets only the robot target.

## 4. GROUP A STALENESS AFTER `4a73e125`

19 commits landed between `4a73e125` and `origin/main` `704d2172`. Re-checked each Group A row against
`origin/main`:

| row | ordered by | state at `origin/main` | stale |
|---|---|---|---|
| 10.1 DEVICE_ANSWERS | D218 (1), D221 | `cf_request_defer.py:177 ACTIONS = ("BASE", "DEFER_TO_LATEST_SAFE_START")`, two actions; only live `ra.decision` writes are `"DEFER"` | **no** (one evidence item refuted, R1) |
| 10.2 zero queued-ahead | D222 (1) item 1 | `arms_v6cfr3.py:199 pred = CC.predict(cf.model, int(u_request), 0, 0, 0)` | **no** |
| 10.3 deferral debit | D222 (1) item 3 | `:175 MIN_DEFERRAL_S = PD.DECISION_PERIOD_S`, used as a floor at `:267`; `cf_cost.py` still `max(lss - now_s, 0.0)` | **no** |
| 10.4 `rd_decisions` log | D222 (1) item 5 | 4,000 cap still in `arms_v6cfr3.py`; **0** files matching `rd_decision` in the whole tree | **no** |
| **10.5 context limit** | **D223 (2)** | **all three D-row-named sites now read `context_limit.py`** | **YES, close it** |
| 10.6 harm gain weighting | D220 (1) | still absent; `cf_objective.py` docstring still records the D177 (1) removal | **no** |
| 10.7 per-type guard | D178 (3) | one `GUARD_LAG_S_DEFAULT = 2.0`, read at `arms_v5rules2.py:196 by_lag = lag >= self.guard_lag_s` | **no** |

**10.5 is the only stale Group A row**, and the briefing predicted it. Checked outside Group A as well:

**10.9 is partially overtaken but NOT closed.** `metrics_health()` has landed since the matrix was
written, at `asyncbackend.py:182-187` and `live/adapter.py:219`, which is the D227 / E3 work. But
`scrape_metrics` at `asyncbackend.py:175` **still has zero callers**, `METRICS_SCRAPE_DEFAULT` at
`:161` is **still `False`**, and `:178` and `:185` both still gate on it. The row's substance stands
and it remains a gate blocker. Line numbers in 10.1 and 10.6 have drifted at `origin/main` because
`arms_v6cf.py` and `cf_objective.py` were edited, but the matrix is pinned at `c5e7bb49` where they
hold, so that is not a defect in the matrix.

## 5. IS THE FREEZE-GATE LIST COMPLETE

**First, a correction to the brief this verification was given, because it matters more than any row.**
The task described "15 freeze-gate rows in four groups (A 7, B 4, C 3, D 1)". The artefact says
"**16 rows, in five groups**" and carries a **Group E**: 10.16, the rung-4 service prediction computed
from the failed-gate model in units 247.46x away from D162's ruled term. Counting the headings 10.1 to
10.16 gives A 7 + B 4 + C 3 + D 1 + E 1 = **16**. The matrix's own figure is right. A verifier working
to the 15-row brief would have skipped the single most consequential row on the list, and 10.16 is the
row that most deserves the user's attention: it is the one where every check in groups A to D passes,
the switch is on, the gate is reached and the counters fire, and what is wrong is the register of the
number being predicted. The matrix also records the mercy that the 247x error is latent rather than
active because `overlap_ft` is the hard-coded zero of 10.2, and warns that honouring D222 (1) item 1
without first resolving the unit makes it active. That warning is the most valuable sentence in the
document and it should not be lost.

**Judgement: substantially complete and honestly bounded.** The list is the real output of the
exercise, every row says what would close it, and the two rows that could have touched a posted result
were checked and cleared in 10.17. Section 11's statement of what the matrix does not cover is
unusually candid, in particular that no final rung has a committed decision log, that 30 of 286 cells
are stubs including both `b7-edf-feasibility` 1x cells in the D213 paper set, and that the
`v5/cf_objective.py` and `v5/cf_planner.py` limb is the largest unexamined surface. I would make one
removal and three additions.

**REMOVE 10.5.** Closed for all three sites D223 (2) names, by `a43ad7f7` and `2e4c5961`. Keep a
one-line residual noting `d170_overlimit.py:33 LIMIT = 32768` and that its committed output is
superseded by `d223_overlimit_counts.json`. Note that 10.8 cites 10.5 as a prerequisite ("Closes when:
a 0.5x cell for rungs 2 to 4, which needs 10.5 first"), so closing 10.5 **unblocks** the only action
that can close 10.8. That is the single highest-value consequence of this verification.

**ADD, as a Group A row: `dry` and `dry_margin` are unattributed switches on the reported arms**
(R3). Inert today, so no behaviour is at risk, but the gate's premise is that every switch that
differs between rungs carries a D-row, and these differ and do not. One line to fix.

**ADD, as a gate item on the matrix itself: three Group B rows are not reproducible from what they
give** (N1, N2). Group B is where the briefing rightly says the real weight sits, because a switch
being on, attributed and mechanically clean is not evidence it fires. Yet 10.8, 10.9 and 10.10 send a
reader to `arm_stats` for counters that live under `memory_pressure/`, against a cell set that is never
listed. D225 (6)'s gate is that a row be checkable without asking the author, and these are not. One
paragraph naming `memory_pressure/enact_placement_totals` and the 20 cell directories closes it. I
confirmed every one of these numbers, but only after finding the path myself, which is the thing the
gate exists to make unnecessary.

**ADD, as a provenance correction, not a gate blocker: the census/pin mismatch** (R4) and the
`kept_warm` range (R5). Section 0's provenance sentence is the foundation the rest of the document
rests on and it currently claims more than was verified. The fix is one sentence: code pinned at
`c5e7bb49` by tree hash, cell census at `2e5cd9a5`, with the fact that no ladder cell changed between
them, which is what makes the OBSERVED rows sound.

**I would remove nothing else.** In particular I would not relax 10.15, which is the row most likely
to be mistaken for pedantry. Its refusal to classify the rung-1 C2/C5 gap is correct: it is one code
read away from being settled, and guessing the class would convert an instrumentation gap into a
finding about the policy.

**Nothing found here requires escalation.** No mechanism contradicts a D-row in a way that would
change a posted result. The two candidate paths were checked: 10.5's 1,296-token window does not bite
because 1x is byte-identical and every covex 0.5x cell has `n_errors = 0`, and 10.16's 247x unit
mismatch is latent for as long as `overlap_ft` is hard-coded zero.

## 6. WHAT THIS VERIFICATION DID NOT COVER

- **Section 5**, the spec-versus-D-row contradictions C1 to C17, was read but not re-derived against
  `research/policy_spec_v6.md` line by line. Section 5 is a substantial part of the matrix and is
  unverified here.
- **Section 4's 140 mechanism rows individually.** I re-derived the classification arithmetic for all
  229 rows and spot-checked the file:line citations in sections 4.1, 8 and 9. I did not open all 140.
- **Sections 4.6 and 4.7**, the superseded and ruled-out rows and the two added mismatch rows,
  including 4.7.1's full 247x chain, which I checked only as far as `cost_model_gate.json` being the
  model both rung-4 legs load.
- **10.11 through 10.14 and 10.16** were read, and their code sites were not independently re-derived.
- **The miscitation table's rows 1, 3 and 4.** Row 1, the D133 miscitation, was supplied as verified in
  the task brief and I did not re-check it; row 2 I confirmed myself.
- **Baselines**, which the matrix scopes out in section 11.

