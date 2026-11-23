# HANDOFF. READ THIS FIRST.

## HOW TO READ THIS FILE

  WRITTEN AT origin/main tip: 06b1acedbaca96969efe84c3de3602f044b2bc7f
  WRITTEN AT: 2026-11-23T15:21-08:00 (23:21Z). EVERY TIME IN THIS FILE STATES ITS ZONE.
  EXPIRES: immediately on any new commit to origin/main.

ORIGIN IS TAKING COMMITS ABOUT ONCE A MINUTE TODAY, so by the time you read this it is almost
certainly expired. THAT IS NORMAL AND IT MEANS WHAT IT SAYS: re-derive the state from `git log`,
`results/INDEX.md` and `research/policy_design_log.md` rather than trusting the summary below. Use
`git log --date=iso-strict`, which prints the UTC offset; a format that drops the offset is how an
earlier version of this file turned a machine that had just committed into one idle for eight hours.

A HANDOFF THAT SAYS STAND DOWN MUST CARRY THE COMMIT IT WAS WRITTEN AT AND AN EXPIRY, and a resumed
session must check the tip against it before obeying. A stale stand-down already stopped one session
while real work was pending.

## THE H100 IS RUNNING. THERE IS NO IDLE GPU PROBLEM.

The previous version of this file said THE H100 IS NOT RUNNING, that about eight hours of GPU were
lost, and that only the user could fix it. THAT WAS FALSE AND IT WAS THE FILE'S HEADLINE ALARM.

Derived here with offsets: the H100's newest cell-output commit is `8be71182` at
2026-11-23T15:05:26-08:00, sixteen minutes before this file was written, and it has been committing
all afternoon (`e608b7aa` 14:05:53-08:00, `9f7cfae8` 14:27:20-08:00, `f82eeea1` 14:49:11-08:00). The
newest commit of any kind is 15:20:14-08:00. NOTHING IS IDLE AND THE USER DOES NOT NEED TO BE CALLED.

A CLAIM THAT A MACHINE IS IDLE IS AN OPERATIONAL ALARM. It can send the user to a terminal at night,
and an error in this direction is the difference between "all is well" and "broken since morning".
DERIVE IDLENESS FROM THE NEWEST COMMIT'S TIMESTAMP WITH ITS OFFSET, never from a bare clock time.

## THREE SESSIONS ARE LIVE ON THIS BOX. CHECK BEFORE YOU EDIT A LIVE-PATH FILE.

Verified by `ps -C python,python3` and `/proc/<pid>/cwd` at 15:21-08:00. Check the same way before
touching anything; the shared worktree `/tmp/claude-1001/mapwt` carries 106 uncommitted entries from
several sessions and its ` M` marks are NOT yours to assume.

  SESSION A   hits 22, 26 and 6 folded into the ladder. Owns `engine_actions.py`, `touch_policy.py`,
              `live/adapter.py`. Running `d209_digest_driver.py --jobs 10` out of `scratchpad/before`
              and `scratchpad/after`.
  SESSION B   the final ladder. Owns `arms_v6state.py`, `v5/*`, the final-rung modules. Running in
              `scratchpad/ladder_flashD208`.
  SESSION D   rung 4 completeness at 0.25x, and now `arms.py`. Running in `scratchpad/sessionD/co`.
  SESSION C   STOPPED ON PURPOSE. Ablations are deferred by D210; do not build, diff or post one.

IF YOU SEE PAIRED IDENTICAL `cf_pd_one_cell.py` COMMANDS, THAT IS NOT A DUPLICATE RUN. Session A runs
each arm in a `before/` tree and an `after/` tree at ONE sha, which is the byte-identity method; the
command lines are identical because only the working directory differs, and each writes to its own
tmpdir. Confirm with `/proc/<pid>/cwd` before killing anything. Do NOT use `pgrep -f` or `pkill -f` on
a pattern matching your own command line: it kills the session shell with exit 144.

ANOTHER SESSION DELETED A PEER'S SCRATCHPAD WORKING DIRECTORY TODAY and cost it a 2.2 GB export and
six in-flight cells. The shared scratchpad root is NOT session-unique in practice. Write cell output
DIRECTLY into your deliverables directory rather than copying at the end, and use a session-unique
subdirectory for everything else.

## WHAT IS SETTLED SINCE THE LAST HANDOFF

  -rr        `covex-v6-fair-c5attr-rr` PASSES ALL THREE D179 CHECKS AT ALL FOUR SEEDS. Alert mean
             per-episode attainment against rung 3: 0.4412 to 0.6256, 0.4269 to 0.6366, 0.4356 to
             0.6399, 0.4750 to 0.6527. Robot 122 to 126, 114 to 121, 109 to 110, 84 to 84; retention
             1.0459, 1.0805, 1.0147, 1.0000. Late alerts fell 84 to 86 percent WITH on-time alerts
             RISING by 2,485, 2,798, 2,739 and 2,391, and THAT RISE IS THE LOAD-BEARING HALF: it shows
             the freed capacity reached the alerts behind the skips rather than removing requests from
             the numerator, which was the pre-registered failure condition and did not occur.
             THE FOUR PASSES ARE NOT EQUAL: s7 is weakest, the only robot tie, on the lowest bar.
             Verdicts `d196_rr_s{4,5,6,7}_verdict.json` and `d196_rr_four_seed_verdict.json`.
  D208       -rr JOINS RUNG 3 and rung 4 is rebuilt on it.
  NAMES      RULED. The final ladder is `covex-v6-state-final`, `covex-v6-fair-final`,
             `covex-v6-final`, ALL THREE SUFFIXED, with every existing registration and committed cell
             UNTOUCHED. The clean names were already registered arms and `arms.ARMS` is a dict, so
             re-registering would have silently re-pointed `covex-v6-state`, which carries six
             committed cells. Mapping block in `results/INDEX.md`. Paper labels map at write-up.
  D206       Option D built and proved at `0ca54444`: the declared constant returns EXACTLY what the
             unfed counter returned at all five read sites, 18 of 18 by `==`, each with a positive
             control that does move the result; a guard proves 0 live paths construct
             `DeficitCounters`; rung 4's digest MOVED, which IS the Step 2b pass.
  GATE A     The would-have-missed COUNT IS RETIRED: overrun = (b - SAFETY_FACTOR) x service has the
             sign of `(b - SAFETY_FACTOR)` alone, so it can only be 0 or N. Replaced by EXPOSURE
             46 of 463 = 9.94 percent at q90 1.863404, worst overrun 1.5035x. Old count kept only as
             a labelled identity column.
  D209/D210  Parity rule, roles, run order; ablations DEFERRED until the policy is frozen. A metric
             correction is a RESCORE and never needs a rerun; a rerun is needed only when a code fix
             changes an arm's decisions.
  D176       Reporting column applied. TWO THINGS A READER GETS WRONG: the column DOES NOT ALWAYS
             RISE (`eco-llm` falls 0.7810 to 0.7701, `hybrid-F-lhreq` 0.9429 to 0.9310, having
             answered the questions from a SHORT representation at `tokens_charged` 467, so an
             on-time answer there is not an over-limit send); and the positive control found a
             SECOND NON-ZERO CASE OF THE D175 (1) GUARD, `always-cloud-fcfs` s7's committed
             `robot_pool_on_time` of 1 being a refusal, so THAT CELL'S FIGURE IS STALE, not the
             column. Arm-invariant BY SET EQUALITY at all four seeds, so no comparison moves.

## TWO FIDELITY FAULTS THAT CHANGE WHAT OLD RESULTS CAN MEAN

  HIT 6 IS PERMANENT, NOT OCCASIONAL. `cstate.py:663` reads `vllm:gpu_cache_usage_perc`; this engine
  emits `vllm:kv_cache_usage_perc` (0.7215 at capture). So `gpu_kv_fraction` has been 0.0 - THE
  MINIMUM, the most permissive value an admission gate can be handed - IN EVERY LIVE CELL ON THIS
  BUILD, independent of the swallowed `except Exception: return {}`. The fix needs BOTH the key and
  the missing-value policy; fixing only the exception path would leave the gate at 0.0 and look like
  a pass.

  CAPACITY MAY NEVER REACH A DECISION AT ALL, FOR A SECOND INDEPENDENT REASON. `arms.py:82 _caps` is
  write-only. If our own arms cannot observe GPU-KV capacity, then a flat 0.25x-versus-1x result was
  never evidence about the policy: it is an UNEXERCISED channel under Rule 2. Session D owns this and
  must fix it BEFORE any 0.25x policy cell. DO NOT CONFLATE THE TWO CAUSES; fixing one does not fix
  the other.

  HIT 26: host residency is observable ONLY IN AGGREGATE on this engine
  (`vllm:prompt_tokens_by_source_total{source="external_kv_transfer"}` and friends), NOT per request:
  per request it folds into `prompt_tokens_details.cached_tokens` and cannot be told apart from a GPU
  hit. So a per-request host belief may be STRUCTURALLY unachievable and RELOAD may be UNEXERCISED
  for a structural reason, which is a stronger statement than a key fix. Do not invent a key.

## AWAITING A USER RULING

  1. THE SECURITY WARNING (Auto-Mode Bypass) that fired on the session which produced the seven
     D201/D205 commits (`de23b354`, `9b49801a`, `13e9978c`, `8986f593`, `2487e345`, `29742254`,
     `1b99b6af`). ALL SEVEN ARE ON ORIGIN AND UNRULED. A later check showed the cell outputs those
     commits touch are byte-identical across all four warned commits, but the warning itself stands.
  2. `inar-vl` and `hybrid-llm` changed ZERO decisions after their score fix. That is an ABSENT LINK
     per Step 2b, NOT a negative: `inar-vl` cancelled by geometry, `hybrid-llm` unexercised. Sweeping
     either knob is METHODOLOGICAL and was not done.
  3. `arms_v6state.py:453` buckets state deltas at pre-flip literals including 0.16456; reported, not
     edited, because a stats-key rename changes what committed proofs read.

## D187 RULES STILL IN FORCE

Every change justified by a measured mechanism and PRE-REGISTERED, COMMITTED BEFORE ITS CELLS. Never
change targets, deadlines, metrics, workload, seeds (NEVER 1 to 3, NEVER HOLDOUT), baselines or pass
bars. NEVER TUNE TOWARD PASSING. REPORT EVERY RESULT WHATEVER ITS DIRECTION. Held or unproved code
defaults OFF. One dry cell per process. A DIGEST IS COMPARABLE ONLY WITHIN ONE RECIPE, and the
committed one is `cf_pd_one_cell.py --cutoff-off` with the posted knobs (16 devices, seed 4, 1200 s,
ratio 40:40:20, lh_req, ss2, epg, per-frame, reask 30.0); comparing a `--cutoff-off` bar against a
cutoff-live run has already produced one false alarm. fmtk only, and never a heredoc piped into
`conda run` (it silently no-ops and exits 0). D166 commit rules: identity shpragya8, NO AI
ATTRIBUTION, no em dashes, no force-push, reset, stash or amend, no files over 5 MB, proofs on a clean
checkout. Resolve origin/main to ONE literal sha for read-tree, the INDEX rebuild and commit-tree
alike, and RE-RESOLVE IMMEDIATELY BEFORE COMMITTING: a split ref silently reverts another session's
files with a clean fast-forward at push time.

ALSO IN FORCE, FROM D209/D210: NO 0.25x POLICY CELLS until rung 4 is proven dry and the user approves
the first one; `KV025_RUNGS` stays held. NO ABLATIONS. Baseline fidelity fixes belong to the H100's
sessions; rescoring and figures belong to the Orin.
