# HANDOFF. READ THIS FIRST.

## HOW TO READ THIS FILE

  WRITTEN AT origin/main tip: 9537bddeeb068d206d05553704695f8ffdbd0302
  WRITTEN AT: 2026-11-23T17:45-0800. EVERY TIME IN THIS FILE STATES ITS ZONE.
  NEWEST COMMIT WHEN WRITTEN: 9537bdde at 2026-11-23T17:43:44-08:00
  EXPIRES: immediately on any new commit to origin/main.
  REFRESHED 2026-11-23T17:45-0800, after 66 commits had landed since the previous stamp. Every
  section below is UNCHANGED; the STATE block that follows this one is the newest text in the file
  and SUPERSEDES the NEXT STEP section.

ORIGIN TAKES COMMITS EVERY FEW MINUTES, so this is probably already expired. THAT IS NORMAL AND IT
MEANS WHAT IT SAYS: re-derive state from `git log`, `results/INDEX.md` and
`research/policy_design_log.md` rather than trusting the summary below. Use
`git log --date=iso-strict`, which prints the UTC offset. A format that drops the offset is how an
earlier version of this file turned a machine that had just committed into one idle for eight hours.

A HANDOFF THAT SAYS STAND DOWN MUST CARRY THE COMMIT IT WAS WRITTEN AT AND AN EXPIRY, and a resumed
session must check the tip against it before obeying. A stale stand-down already stopped one session
while real work was pending.

## STATE AT 2026-11-23T17:45-0800. TWO OF THE THREE BLOCKS ARE CLEARED.

THE "NEXT STEP" SECTION BELOW IS PARTLY STALE. Read this first; it was written later.

  (a) RE-BAR confidence-cascade  DONE. Record at `ladder_final/rebar/rebar_record.json`. New bar
      `b1ff48e40387a997` / 3,834, superseding `b9290071679f1baa` / 12,253. Ran ALONE: 0 other cell
      runners before, 0 appeared DURING, loadavg 0.60 at start and 1.00 at end AS MAGNITUDES, from a
      clean archive of `3fa41f51` with `8986f593` verified an ancestor first.
      AND THE PART WORTH MORE THAN THE ALONE RUN: TWO INDEPENDENT RUNS AGREE, the earlier one (NOT
      formally alone, loadavg 2.21) and the guarded one (0.60), both giving `b1ff48e40387a997` /
      3,834. This arm's determinism question is settled by AGREEMENT ACROSS A 3.7x LOAD RANGE, not by
      preferring the quiet run.
      TWO STALE FIELDS IN ITS BAR ROW WERE CORRECTED at `49827c88`: `_bar_validity` still read "BAR IS
      STALE" with `proof_a_escalates` FALSE and "RE-BAR OWED" while the row's own `_escalates_on_move`
      read True, and `_provenance` still pointed at the file that produced the SUPERSEDED bar. A reader
      trusting `proof_a_escalates` FALSE would NOT escalate on a future move, which is exactly the
      mis-score the D213 item 4 provenance rule exists to prevent. Both originals kept beside.
  (b) E1 (`asyncbackend.py`)  LANDED at `5c319fc8`, byte-identical while default-off, proved on three
      arms including rung 4. The D216 (2) precondition on a 0.25x POLICY cell is satisfied IN CODE.
      NOTE IT LANDED DEFAULT-OFF: enabling it is a SEPARATE step, and a 0.25x policy cell still needs
      the user's approval of the first one.
  (c) Session B posts FINAL_LADDER_CELLS  STILL OPEN, AND THE ONLY REMAINING BLOCK. No
      `FINAL_LADDER_CELLS` exists under `frozen_test/runs/`. SESSION B CANNOT BE RESUMED UNTIL 19:00
      AMERICA/LOS_ANGELES. DO NOT START A REPLACEMENT: resume with SendMessage, or its in-flight chain
      is duplicated, which has already happened once today.

RUNNING ON FLASH AT THE TIME OF WRITING, verified by `ps` plus `/proc/<pid>/cwd` rather than assumed:
`d216_final_kv025_driver.py`, the 0.25x DRY proof on `covex-v6-final` ordered as check 3 of the user's
StudyD210-KV025 section 1.6 ruling. SO THE BOX IS NOT FREE AND THE D216 (1) ALONE RULE FORBIDS STARTING
ANOTHER PROOF CELL. Session D's counts do NOT transfer to `covex-v6-final`, which differs by the
id(obs) fix, the planner-on-feed at rung 3 and the alert release re-check, all decision-changing; its
structure and channel analysis DO transfer.

ALSO STOPPED AND NEEDING A RESUME RATHER THAN A REPLACEMENT: the D214 figure-instrumentation agent did
not finish before the previous session ended. Its transcript is saved.

`ops/watchdog.log` AND `ops/track.log` ARE BOTH EMPTY, so the instruction to read them for
who-holds-what yields nothing; derive ownership from `ps`, `/proc/<pid>/cwd` and `git status` instead.
The shared worktree currently carries 113 UNCOMMITTED PATHS from other sessions INCLUDING live-path
files (`arms.py`, `coordinator.py`, `v5/cf_objective.py`, `hybrid/hybrid_arm.py`,
`share_admission.py`). DO NOT EDIT A LIVE-PATH FILE THERE: ship such a change as a PATCH SCRIPT
asserting `count == 1` per replacement, which is the pattern that has worked today.

## THE TWO FLASH AGENTS ARE RATE-LIMITED UNTIL 19:00 AMERICA/LOS_ANGELES. THE COMPUTE IS NOT.

Both flash agents (Session A, hits 22/26/6; Session B, the final ladder) terminated on
"You've hit your 5-hour limit, resets 7pm (America/Los_Angeles), out of usage credits". THEIR WORK IS
SAVED AND THEIR SHELL CHAINS ARE STILL RUNNING AND STILL WRITING CELLS. Do NOT start replacement
agents: resume each with SendMessage once requests are accepted again, or the in-flight chains will be
duplicated, which has already happened once today.

VERIFIED LIVE at the time of writing, by `ps -C python,python3` plus `/proc/<pid>/cwd`:
  Session A   `d209_digest_driver.py` across THREE trees, `before`, `after`, `after_no22`
              (b9, simplestream, confidence-cascade in flight).
  Session B   the proof (a) chain in `ladder_flashD208`, writing `ladder_final/cells/a_<arm>.json`.
  Session D   `d210_kv025_driver.py`, the rung-4 0.25x dry proof. NOT in the agent roster any more
              (it was dropped when an earlier process exited) so it CANNOT be messaged; read its
              output instead.
PAIRED IDENTICAL `cf_pd_one_cell.py` COMMAND LINES ARE NOT A DUPLICATE RUN: Session A runs each arm in
a before and an after tree at ONE sha, which is the byte-identity method. Confirm with
`/proc/<pid>/cwd` before stopping anything. Never `pgrep -f` or `pkill -f` on a pattern matching
your own command line; it kills the session shell with exit 144.

## PROOF (a): 5 MEASURED, 5 MATCH, 0 MOVED. NOTHING HAS MOVED.

Scored by RUNNING THE COMMITTED SCORER `d208_score_proof_a.py`, not by eye. It needs the repo layout
(it derives `ROOT = HERE.parents[2]`), exits 0 with "nothing has moved so far", and returns nonzero if
any arm moves.

  always-cloud-fcfs   c7f86bb7755828de / 12,253   MATCH   loadavg 24.81
  b7-edf-feasibility  b9aadd1c3a2b26d5 / 12,265   MATCH   loadavg 20.45
  edf                 9db366ac8f684d45 / 16,327   MATCH   loadavg 19.16
  covex-v6-base       af8befb9420ad86a / 12,085   MATCH   loadavg 10.80
  covex-v6-rules      18067c4c66bb44b8 / 11,955   MATCH   loadavg 13.80

THE REPORTED-BASELINE SET IS NOT A JUDGEMENT CALL. It is the committed D164 BASELINE MATRIX at
`results/orchestration/live2/frozen_test/runs/BASELINE_MATRIX`, headed "RUN NOW: the paper core, seeds
4 to 7": 18 distinct ACTIVE (non-#) arms, every active line at the single tag `_L3_epg_rq30`. Score
that set and no other. Reading it REMOVED work twice: a plan for 13 extra cells, then a narrowed plan
for 3, both dropped once it was clear `preble`, `b9` and `uniscale` ARE NOT IN THE MATRIX, so hit
6's effect on them is not something the paper needs to measure.

TWO TRAPS IN THAT TABLE, recorded because neither is visible from the output alone:
  - IT HAS 17 ROWS BUT FEWER DISTINCT ARMS. `covex-v6-base` and `hybrid-F-lhreq-noc3` are ONE ARM
    UNDER TWO NAMES, as are `covex-v6-rules` and `v5-rules-2`. So two rows read PENDING while the arms
    they name have MATCHED. "5 of 17" understates coverage; on distinct arms it is 7 of 15.
  - THE SCORER PRINTS LOAD AS "?" for every row. It does not read loads. They live in
    `cells/chain.out`, `cells/chain_a.out` and `d208_proof_a_loadavg.json`.

COVERAGE MISSING, which is the honest verdict for an arm with NO committed bar, since "byte-identical"
and "moved" are both undefined without one: `hybrid-F-lhreq`, `lmcache`, `r3-streaming`,
`streamscout`, `v5-rules`. Reporting such an arm as unchanged would be a vacuous pass.

## THE LOAD BOUNDARY. TWO CLAIMS WERE WRONG; HERE IS WHAT SURVIVES.

STATE IT AS: FOR `--cutoff-off` DIGEST CELLS LOAD IS NOT A COMPARABILITY THREAT; FOR ANYTHING
TIMING-DEPENDENT IT IS. Carried by TWO legs and explicitly NOT by precedent:
  1. THE MECHANISM: the planner wall-clock cutoff is patched off, so the time-dependent quantity load
     could perturb is out of play. An argument from what the code does; it does not weaken at load.
  2. FIVE BIT-EXACT MATCHES FROM TODAY'S REGIME, at 10.80, 13.80, 19.16, 20.45 and 24.81.

WHAT WAS WITHDRAWN, kept because the shape recurs: a claim that "the committed d179 run recorded
`loadavg_end` up to 20.13" was relayed between sessions and IS FALSE. The highest load any committed
artefact records is 9.00 (`d184_r3_c5attr_proofs.json` 1.03 to 9.00);
`d179_offswitch_digest_proofs.json` carries only a BOOLEAN `after_self_reproduces_under_load` WITH NO
MAGNITUDE; `20.13` appears nowhere under `results/orchestration/`. The correction ran AGAINST the
argument it was offered to support: there was NO precedent for today's regime, which is why the five
matches above had to be earned rather than assumed. It had already reached a committed artefact as
`"_committed_run_loadavg_end_up_to_20": true`, both FALSE and UNVERIFIABLE in the form written.
THEN THE CORRECTION ITSELF CARRIED A TRANSPOSED LOAD (10.08 for 10.80), fixed from the authoritative
`cells/chain.out`. A load claim must be READ BACK FROM ITS SOURCE, not retyped, and a magnitude must
never be recorded as a boolean. All versions are kept side by side on purpose.

## THE REGISTER ERROR THAT KEEPS RECURRING: A MENTION IS NOT A MEASUREMENT

`lmcache`'s digest `2b789696e98821c4` appears in FIVE committed files, which looks like it satisfies
the two-record rule. Only ONE is a paired digest measurement. The others are `frozen_grid.log`, the
`DEVWAIT_S67_CELLS` cell list, a narrative row in `results/INDEX.md`, and
`d187_streamscout_lmcache_livepath_check.json` WHOSE OWN `digest` FIELD IS A DIFFERENT VALUE
(`30b2806a117c9c57`). COUNTING FILES RATHER THAN MEASUREMENTS is the error. `lmcache` is COVERAGE
MISSING. Same family as a boolean standing in for a magnitude: the artefact looks like evidence and is
not.

AND THE RULE THAT PREVENTS A FALSE ESCALATION: NEVER BUILD A BAR TABLE AS A UNION over committed
records. `covex-v6-rules` reads `18067c4c66bb44b8` / 11,955 in ELEVEN records and
`a3c000f4ae2f37f5` / 12,179 in ONE older `d175_digest_proofs.json`. A union takes the outlier and
scores a CORRECT cell as MOVED. Score against d179's table alone; use an arm's own record only where
d179 has no entry AND TWO records agree. The d175 value is SUPERSEDED.

## SETTLED SINCE THE LAST HANDOFF

  NAMES    EXECUTED. The final ladder is `covex-v6-state-final`, `covex-v6-fair-final`,
           `covex-v6-final`, ALL THREE SUFFIXED, every existing registration and committed cell
           UNTOUCHED. Mapping block in `results/INDEX.md`; `MAPPING_for_INDEX.md` beside the proofs.
  PREREG   StudyLADDER-FINAL IS FROZEN:
           `sha256 d6d8b6c121d23f20f46b03832883fd6b90126f42c7b2fa8224f3d6614bc5f221`, 2026-11-23T23:34:28Z,
           BEFORE any ladder cell. Hash independently recomputed before commit. ZERO ladder cells exist.
  BASE     `covex-v6-base` AND `hybrid-F-lhreq-noc3` ARE ONE ARM UNDER TWO NAMES, not a definition
           clash. `arm_names_v6.py` `OLD_TO_RUNG` maps them; `d181_share_floors.json`'s `source`
           writes both; and the committed digest table gives BOTH the same digest, so the alias is
           visible in the MEASUREMENTS. The 1x plain-tag run DIRECTORIES use the OLD name while the
           `_kv0.25`, `_kv0.5` and `_lpt2048` variants use the NEW one: an output-naming
           inconsistency only. No base cell needed running.
  BAR      THE FINAL RUNG 3's ALERT BAR IS MATERIALLY HARDER THAN THE ONE `-rr` CLEARED. Base's alert
           attainment EXCEEDS committed rung 2's at every seed (0.44249 against 0.2288 at s4, through
           0.553811 against 0.2482 at s7), so D208's "above base's" asks the final rung 3 to beat the
           ALERT-RICH end of the alert-versus-recall curve WHILE KEEPING rung 2's robot gain. It is
           frozen as D208 words it. D187 forbids moving a pass bar or tuning toward passing, SO A MISS
           IS A REPORTABLE RESULT, and it must be stated in the write-up whichever way it falls, or a
           reader who knows only that `-rr` beat rung 3 will misread a miss as a regression.
  GUARD    `covex-v6-state-uo` and `covex-v6-state-noprice` (both `9a4be873eb3c5fba` / 14,218) are
           marked TO-BE-RE-BARRED. Do NOT escalate on a digest change in those two AFTER the
           touch-price flip (D209 (1) rules it expected); DO escalate on any other arm, and on those
           two BEFORE the flip. `covex-v6-base` and `covex-v6-rules` have no state planner and never
           read `gpu_kv_fraction`, so a movement there IS a real escalation.

## THE NEXT STEP, AND WHAT BLOCKS IT

*** CORRECTED 2026-11-23T16:52-0800. THE BLOCK DESCRIBED HERE IS GONE AND ONE OF ITS CLAIMS IS
MEASURED FALSE. READ THIS BEFORE ACTING ON ANYTHING BELOW. ***

WHAT THIS SECTION SAID: that Session A must land and must actually flip `TOUCH_PRICE_MODE`, that
`touch_policy.py:108` still read `"reload-proxy"` so hit 22 was built but default-off, and that THE
FLIP MOVES RUNG 3'S AND RUNG 4'S DIGESTS, so "a rung 3 that does NOT move after the flip is the
problem".

WHAT IS TRUE NOW, both verified at origin before this correction was written:
  1. SESSION A HAS LANDED, at `c707610d`, confirmed an ancestor of origin/main. THE DEFAULT IS FLIPPED:
     `touch_policy.py:126` reads `TOUCH_PRICE_MODE = "d174-uncached-only"`, and `price_for_touch` now
     RAISES on an unknown mode instead of falling through to the proxy. So the fix is not
     reachable-but-off; it is the default.
  2. *** THE FLIP MOVES NEITHER RUNG 3 NOR RUNG 4. MEASURED ON BOTH TREES. *** Rung 3 is
     `12e4f73ce0ebd865` / 13,812 on BOTH sides, equal to its committed bar, and rung 4 is identical on
     both sides too. SO THE SENTENCE "a rung 3 that does NOT move after the flip is the problem" IS
     BACKWARDS: a rung 3 that does not move is the measured outcome, and the four `-rr` verdicts
     therefore DO NOT sit on superseded code because of the touch price. Anyone treating an unmoved
     rung 3 as a defect will chase a fault that is not there.
     WHY IT DOES NOT MOVE, which is the useful part: the touch price is UNEXERCISED at 1x. It has
     exactly one call site, `coordinator.py:1161`, and the gate refuses 0 OF 2,267 TOUCHES AT EITHER
     PRICE. Under CLAUDE.md Rule 2 that is UNEXERCISED, not a no-op and not a negative. The correction
     still matters, because the cell that motivated D174 is one where the budget DID bind, and a 0.25x
     or tighter-budget cell can bind again.
  3. THE OVERCHARGE WAS 105.50x TO 154.50x, p50 131.49x, NOT the 3.6x to 9.8x that circulated here and
     in several messages. That figure was against the INTERMEDIATE `d162-warm-hit` price, whose
     intercept is 96.1 percent of it, so it understated the defect by about 26x. `d162-warm-hit` is NOT
     the corrected mode either: its 0.070534 s intercept is 25.8x the ruled charge, which D174 (1)
     excludes as occupancy.

SO THE REAL REMAINING BLOCK IS NOT SESSION A. It is, in order:
  a. RE-BAR `confidence-cascade` ALONE on the committed recipe from post-fix code. Its bar
     `b9290071679f1baa` / 12,253 PREDATES its own ruled D205 fix (`8986f593` changed
     `cascade_adapted.py`; `delivered_scores` is gone from it), so its measured move to
     `b1ff48e40387a997` / 3,834 is the fix landing, not contention: that cell ran at loadavg 2.21, the
     LOWEST in the sweep, while twelve arms matched bit-exactly at loads up to 24.81.
  b. E1 (`asyncbackend.py`) MUST LAND BEFORE ANY 0.25x POLICY CELL (D216 (2)).
  c. Session B then posts `FINAL_LADDER_CELLS`.

THEN, in order: Session B re-resolves to ONE sha, rebuilds on the Session A commit, fills the measured
numbers against the FROZEN bars, runs proofs (b), (c) and (d), and posts `FINAL_LADDER_CELLS` with the
s4 lines written `covex-v6-fair-final`, `covex-v6-final`, `covex-v6-state-final` (the driver
stable-sorts by seed, so WITHIN s4 the written order is the run order, and fail-fast depends on it).
s5 to s7 go in SEPARATE LATER POSTS only as per-seed verdicts allow.

THE TOUCH-PRICE QUESTION NEEDS NO NEW GPU: Session A's `after_no22` versus `after` diff ISOLATES THE
FLIP ALONE on a state-planner arm at the committed recipe. What makes it decisive is that the touch
price has exactly ONE call site in the live2 tree, `coordinator.py:1161`, with no arm or planner module
calling it. DO NOT rely on "the flip is dry-inert": a probe found zero calls over a 180 s dry window BUT
ITS POSITIVE CONTROL FAILED TO ATTACH, and `test_hybrid.py:66` constructs a `Live2Coordinator` so
`coordinator.py:1161` IS reachable dry. That zero is an UNINSTRUMENTED WINDOW, not a null.

## AWAITING A USER RULING. DO NOT ASSUME ANY OF THESE.

  1. THE SECURITY WARNING (Auto-Mode Bypass) on the seven D201/D205 commits (`de23b354`, `9b49801a`,
     `13e9978c`, `8986f593`, `2487e345`, `29742254`, `1b99b6af`). ALL SEVEN ARE ON ORIGIN AND
     UNRULED. A later check found the cell outputs they touch byte-identical across the warned commits,
     but the warning stands.
  2. `inar-vl` AND `hybrid-llm` CHANGED ZERO DECISIONS after their score fix. ABSENT LINK per Step 2b,
     NOT a negative: `inar-vl` cancelled by geometry, `hybrid-llm` unexercised. Sweeping either knob
     is METHODOLOGICAL and was not done.
  3. THE MATRIX VERSUS D209 (2). D209 (2) orders fidelity fixes for `pensieve`, `kvflow`, `rh8`,
     `attentionstore`, `inar-vl` and `routellm`, and NONE is in the active matrix. The two readings
     have very different costs, which is why it is the user's: if the matrix is STALE, the paper's arm
     set is wrong and the fixes matter; if the matrix is CURRENT, six arms are being fixed and rerun for
     a paper that will not report them, which is H100 time spent for nothing. Asked from two sessions
     independently so it reaches the user once from each rather than being assumed resolved.
  4. TWO PERMISSION ALLOW RULES IN `.claude/settings.local.json` HAVE A WILDCARD BEFORE THE REST OF THE
     COMMAND (the two `Bash(mv ~/fm-switching/...)` rules), so they also match options inserted at that
     position and approve them WITHOUT A PROMPT. Flagged by the harness, reported, NOT edited: settings
     are the user's. The fix is to replace the `*` with the exact value meant, or use `*` only after
     the subcommand.

## D187 RULES STILL IN FORCE

Every change justified by a measured mechanism and PRE-REGISTERED, COMMITTED BEFORE ITS CELLS. Never
change targets, deadlines, metrics, workload, seeds (NEVER 1 to 3, NEVER HOLDOUT), baselines or pass
bars. NEVER TUNE TOWARD PASSING. REPORT EVERY RESULT WHATEVER ITS DIRECTION. Held or unproved code
defaults OFF. One dry cell per process. A DIGEST IS COMPARABLE ONLY WITHIN ONE RECIPE, the committed one
being `cf_pd_one_cell.py --cutoff-off` with the posted knobs (16 devices, seed 4, 1200 s, ratio
40:40:20, lh_req, ss2, epg, per-frame, reask 30.0); comparing a `--cutoff-off` bar against a
cutoff-live run has already produced one false alarm. fmtk only, and NEVER a heredoc piped into
`conda run` (it silently no-ops and exits 0; `conda` is also not on PATH inside a conda-run child, so
use `/home/pragya/miniconda3/envs/fmtk/bin/python`). D166 commit rules: identity shpragya8, NO AI
ATTRIBUTION, no em dashes, no force-push, reset, stash or amend, no files over 5 MB (gzip instead),
proofs on a clean checkout. Resolve origin/main to ONE literal sha for read-tree, the INDEX rebuild and
commit-tree alike, and RE-RESOLVE IMMEDIATELY BEFORE COMMITTING: a split ref silently reverts another
session's files with a clean fast-forward at push time. COMMIT A RESCUED BUNDLE FROM THE AGENT'S SCOPED
LIST, not a `find` over its root, or strays land at the repo root.

ALSO IN FORCE: NO 0.25x POLICY CELLS until rung 4 is proven dry AND the user approves the first one;
`KV025_RUNGS` stays HELD. NO ABLATIONS (D210). Baseline fidelity fixes belong to the H100's sessions;
rescoring and figures to the Orin. D211 (host residency must be OBSERVED, not merely native) is Session
A's, with its OWN frozen pre-registration separate from the ladder's, and ships GATED OFF with the D211
fallback as default; its agreement bar can only be evaluated on cells from about 15:53-08:00 onward,
because NONE of its counter keys was recorded on ANY committed cell.

## TWO SHARED-BOX HAZARDS THAT HAVE ALREADY COST WORK TODAY

ANOTHER SESSION DELETED A PEER'S SCRATCHPAD WORKING DIRECTORY and cost it a 2.2 GB export and six
in-flight cells. The shared scratchpad root is NOT session-unique in practice. Write cell output
DIRECTLY into the deliverables directory, keep insurance copies outside the scratchpad
(`/home/pragya/fm_bundle_rescue/`), and use a session-unique subdirectory for everything else.

TWO SESSIONS WERE BRIEFED ON THE SAME D208 WORK and ran IDENTICAL 15-arm proof (a) chains at once,
against committed bars, on a loaded host. One chain was stopped and ONE copy of each artefact survives.
There is a peer session on this box (`A6000`, reachable at `uds:/tmp/cc-socks/2840107.sock`). AGREED
OWNERSHIP: `results/INDEX.md` is this session's; `research/policy_design_log.md` and
`research/EXPERIMENTS.md` go to whichever session the user addresses, with BOTH keeping the duplicate
guard (assert the key absent, SKIP on byte-identity, then diff the built tree against the freshly
resolved sha and expect only your own rows). THE GUARD, NOT OWNERSHIP, is what has actually prevented
loss: it has fired four times today across the two sessions.

## WHAT LANDED AFTER THIS FILE WAS FIRST WRITTEN (read git log; these are the load-bearing ones)

PROOF (a) IS COMPLETE OVER THE D213 PAPER SET: 12 MATCH, 1 MOVED-BUT-RULED (`confidence-cascade`,
above), 0 MOVED UNEXPLAINED, 4 COVERAGE MISSING (`cascade-routing`, `kvflow-prefetch`, `lmcache`,
`streamscout`: no d179 bar, so NOT scored and NOT reported as unchanged), 1 NOT APPLICABLE
(`device-only`, offline by design per D79). Twelve bit-exact matches span loadavg 2.15 to 24.81 with
ZERO movement. THE LOAD BOUNDARY RESTS ON THE MECHANISM (the cutoff is patched off, so the
time-dependent quantity is out of play) PLUS THAT SPREAD, NEVER ON PRECEDENT: the highest load any
committed artefact records is 9.00, and an earlier claim here of "loadavg_end up to 20.13" was FALSE and
is withdrawn.

BAR PROVENANCE IS A STANDING RULE (D213 item 4) and all 17 rows are backfilled: each carries the commit
that produced it (`2f3824ea`), the ruled fixes it predates, which of those touched that arm, and a
computed `_escalates_on_move`. PROOF (a) ESCALATES ONLY WHEN AN ARM MOVES ON CODE WITH NO RULED CHANGE
SINCE ITS BAR. Arms with a ruled-but-UNLANDED fix also do not escalate (`simplestream`, `eco-llm`,
`attentionstore-prefetch`), or the clause would fire on exactly the moves D213 ordered.

THE ALONE RULE IS STANDING ON EVERY BOX (D216 (1)): any dry cell whose digest is used as a proof bar or
a Step 2b baseline RUNS ALONE, with loadavg recorded AS A MAGNITUDE, never a boolean. AN UNFIXED RUNG-2
DIGEST IS NEVER A VALID BAR: a COMMENT-ONLY edit moved `covex-v6-state-uo-c5attr` by 85 committed-key
decisions and 11 rows through allocation, because `_queued_behind` keys its cache on `id(obs)`.
OPERATIONAL CAVEAT, unresolved: with three or more sessions holding cells on flash the rule cannot be
honoured unilaterally, and it was NOT honoured for some cells, which are labelled with their load.

NETWORK (StudyNET-TIER1, `e70948e1`), and both answers are the inconvenient ones:
  - N1: THE LINK ARITHMETIC IS LIVE BUT THE PER-DEVICE LINK IS ABSENT. Bandwidth and RTT are read and
    do change delivered times, but NO CALLER EVER PASSES per-device values and the emulator overwrites
    them with one fleet-wide `LinkSpec`, so EVERY live2 cell ever run used the single D75 pair. The
    per-device mechanism is UNREACHABLE, the same shape as the `desired_tier` failure. Tier 1's
    mixed-fleet condition cannot run without a build, so N3's definitions were deliberately NOT POSTED.
  - N2: THE IRISH 5G PERCENTILES ARE DOWNLINK. D75's standing caveat is REFUTED, not confirmed. Had
    they been used as uplink, every Tier 1 cell would have been wrong IN THE EASY DIRECTION, since
    downlink runs several times uplink and the poor-link condition would have been far too generous.
    RTT is OBSERVED and the earlier "not available" note is also wrong.

E1's RESULT, built but NOT landed: live2 NEVER SCRAPED /metrics at all (`AsyncLive2Backend` is not an
`HttpBackend` subclass and contains no `/metrics` string), so `gpu_kv_fraction` was 0.0 in every
reported live2 cell because NOTHING READ IT, not because a key was renamed. With the scrape in,
`obs.cloud.gpu_kv_fraction` goes 0.0 to 0.7215 and rung 4's free KV 51,944 to 17,527, the counter
flipping from `pd_kv_bound_by_belief` to `pd_kv_bound_by_engine_metric`. Item 3's recording site is
`coordinator.py:2126`, which COLLIDES with the H100's hit-7 claim: THE H100 GOES FIRST, then E1 rebuilds
on its tip. `vllm:num_requests_waiting` is DELIBERATELY NOT PUBLISHED, pending a user ruling, so
`queued_by_class` cannot move for every arm behind a one-gate fix.

STILL UNRULED: the Auto-Mode Bypass warning on the seven D201/D205 commits; the `inar-vl` and
`hybrid-llm` ZERO-DECISION absent links; whether to connect `vllm:num_requests_waiting`; owners for E3
(one line so the cell flag reaches `cell.json`) and the two misleading doc lines at `cstate.py:17` and
`arms_v6cf.py:283`.
