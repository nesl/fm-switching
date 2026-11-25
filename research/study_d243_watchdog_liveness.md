# D243: a replacement liveness gate for `ops/watchdog.sh`. PREPARED AND PROVED IN SCRATCH. NOTHING INSTALLED.

**Status: the ruling says "Report the diff before installing it", so nothing is installed and
`ops/watchdog.sh` is byte-identical to origin/main (md5 `5d638dc6b7e81ca7efbc170bd2f6be14` both ways).**
Precedent for this form: `research/study_fix102_prepared.md`, prepared and not applied.
**Full candidate files and the 263-line diff:**
`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/work/`
(`proposed.diff`, `watchdog.sh`, `session_runner.sh`). **Scratch is cleared on reboot; copy before relying
on it.**

## *** THE 11-MINUTE LAPSE COST TWO RESTARTS. VERIFIED IN THE LOG, NOT INFERRED. ***

```
2026-11-25T15:00:01Z STANDDOWN EXPIRED, resuming normal watchdog behaviour
2026-11-25T15:00:01Z heartbeat STALE at 119064s
2026-11-25T15:00:01Z RESTART 1/12: session fmsw-overnight absent, starting in tmux
2026-11-25T15:10:01Z RESTART 2/12: ... (heartbeat STALE at 119664s)
2026-11-25T15:20:01Z STANDDOWN active for 998 more minutes, not starting Claude.   <- re-armed, holding
```
**The previous expiry was 07:00 local and the re-arm landed at 07:11, so two ticks fired in the gap and
started two sessions. The 15:20Z tick confirms the new file holds.** **5 RESTART lines today in total.**

## *** TWO GATES IN THE CURRENT FILE ARE NOT WEAK SIGNALS. THEY ARE CONSTANTS. BOTH VERIFIED ON THIS BOX. ***

**1. The heartbeat gate could never pass.** `ops/heartbeat` is **0 bytes, mtime 2026-11-23 21:55**, and
**NOTHING IN THE REPO WRITES IT**: a repo-wide grep finds only `watchdog.sh`'s own comments (lines 17, 56,
58), its variable assignment at line 77, and an unrelated ECG file where "heartbeat" is a cardiac signal.
**So `age < 600` was unreachable and the gate was unconditionally STALE at 119,664 s and climbing.** The
comment at line 17 already explains why the gate was wrong BY DESIGN; this is a second, independent
failure, BY FACT.

**2. The alone-guard is a constant FALSE, and this is the FOURTH such guard in this project.**
```
live claude processes on this box: 5
OLD guard  ps -C claude -o args= | grep -- "-c -p"   ->  *** ALONE (would start a second session) ***
pid 2840107  exe=/home/pragya/.local/share/claude/versions/2.1.326  cwd=/home/pragya/Desktop/FM-switching
```
**No command line contains the literal `-c -p`, so the guard matches nothing, ever, while a session sits in
the repo.** Prior three: a name pattern, a basename list, a tree snapshot, all reporting `alone: true` on a
busy box.

## The design, and why BOTH options the ruling offered are rejected

*** A HEARTBEAT MTIME, A RECENT COMMIT, AND A RECENT `track.log` WRITE ARE THE SAME INSTRUMENT: A FRESHNESS
TEST. IT CANNOT DO THIS JOB. *** **"The prompt completed and the process exited" and "the process died
mid-work" leave IDENTICAL outside evidence - nothing running, and a timestamp that only gets older.** A
session that finished cleanly at 04:00 and one killed at 04:00 have an equally stale last commit at 05:00.
**And a worker legitimately inside one 21-minute GPU cell writes nothing at all, so recency confuses "slow
but working" with "dead" in the direction that costs tokens.**
**The fact that separates the cases is the worker's EXIT STATUS. It exists for one instant and is not
observable afterwards, so it must be WRITTEN DOWN.** Hence a new `ops/session_runner.sh` wraps the worker
and records `status=RUNNING pid= starttime= started=` then `status=DONE rc= finished=` in
`ops/session.lease`, and the gate reads that.

| lease state | verdict | restart? |
|---|---|---|
| RUNNING, that exact process present | LIVE | no |
| **DONE, rc=0** | **COMPLETED** | **NO - this is the old gate's bug** |
| RUNNING, process gone | DIED | yes |
| RUNNING, pid alive but starttime differs | DIED (recycled pid) | yes |
| DONE, rc!=0 | FAILED | yes |
| no lease | NEVER_STARTED | yes (bootstrap) |

**The identity test is pid PAIRED WITH `/proc/<pid>/stat` field 22 (starttime), never a name and never a
command-line pattern**, so a recycled pid cannot read as the worker still running, and nothing can
self-match the checking shell. **`--classify` prints the verdict and exits without starting anything.**

## The proofs: all three pass, and case 3 is the one that matters

| case | verdict | restart | evidence |
|---|---|---|---|
| **1. live worker** (real process hashing 1.87M file reads, not a `sleep`) | **LIVE** | **no** | no `watchdog.state` written, no tmux session created |
| **2. died mid-work** (killed `-9`, wrapper first, so no rc could be recorded) | **DIED** | **yes** | `RESTART 1/12`, tmux session created |
| **2b. worker killed, wrapper survived** | **FAILED** (rc=137) | yes | lease recorded the signal death |
| **2c. recycled pid** | **DIED** | yes | `pid 1 exists but starttime 31 != leased 130` |
| **3. completed normally and exited** | **COMPLETED** | **NO** | `rc=0`; state unchanged before and after |
*** AND THE OLD GATE, RUN VERBATIM ON CASE 3's IDENTICAL STATE: "heartbeat STALE at 120236s -> WOULD
RESTART a session that finished cleanly." So cases 2 and 3 are distinguished, and by `rc`, not by a timing
margin. ***
**Alone-guard controls, both run: NEGATIVE CONTROL on the real repo named pid 2840107 and stood down, where
the old guard said ALONE at the same instant; POSITIVE CONTROL on a tree with no claude process correctly
said alone.** **It logs the pids it classified, so the verdict can be checked rather than trusted.**

## *** TWO SUBTLETIES I FOUND THAT THE AGENT'S OWN TESTS COULD NOT SEE ***

**1. The guard returns a FALSE "alone" when run from inside a Claude session.** I ran it myself and got
`alone`, then found why: **it excludes `$$` and `$PPID` as the self chain, and on this box `$PPID` IS
2840107, the claude process of the session doing the running.** **In production the parent is cron, so the
exclusion is harmless and the guard is correct. But anyone who tests it from a session gets the reassuring
wrong answer**, which is the precise failure this project keeps hitting. **It should be tested only from a
non-Claude parent, and that belongs in a comment beside the guard.**
**2. It silently skips processes whose `/proc` it cannot read.** Of the 5 live claude processes, **4 have
unreadable `exe` and `cwd`** and are skipped by `continue`. **If a conflicting session were one of those,
the guard would say alone.** Not a defect in the readable case, but the skip should be LOGGED rather than
silent, so an unreadable process is visible as unknown rather than absent.

## What this gate CANNOT distinguish, and the trade to weigh

1. **Hung versus working: both read LIVE and neither restarts.** Deliberate: the only discriminator is a
   progress timestamp, the instrument just removed. Past `MAX_RUN_S = 21600` it logs a WARNING naming the
   runtime and the age of the newest progress write. **A hung worker will hang until a human looks. That is
   a real reduction in autonomy and it is the trade chosen rather than reinstate false restarts.**
2. *** CLEAN COMPLETION WITH WORK REMAINING VERSUS NOTHING LEFT: both are rc=0, both COMPLETED, neither
   restarts. SO THE WATCHDOG BECOMES CRASH-ONLY RATHER THAN A POLLER. *** **After one clean completion it
   stays quiet until the lease changes, so resuming after a reboot or after new work is queued becomes an
   explicit act (delete `ops/session.lease`, or an `@reboot` tick reading NEVER_STARTED).** **This is the
   behaviour change to weigh most, and making it automatic needs a work-remaining signal that nothing in
   the repo provides.**
3. **A prompt that legitimately ended in an error versus a crash: both rc!=0, both restart**, bounded by
   the budget.

## Two defects found and deliberately NOT fixed

- **The restart budget is structurally unreachable and remains so.** The window reset means 6 ticks per
  hour can never reach 12, and `BUDGET SPENT` has fired **0 times in 109 restarts**. **With the poll
  removed, 12 is no longer sized for anything.** Annotated only; changing it is a policy call.
- **`ops/heartbeat` has no writer.** Left in place rather than deleting state; it is dead after this change.

## Installing, when ruled on

**`ops/` is entirely UNTRACKED in this checkout** (`git ls-files --error-unmatch ops/watchdog.sh` errors),
though its content matches origin/main. **So installing is a plain file write and committing is a separate
act.** Steps: copy the two scratch files to `ops/watchdog.sh` and `ops/session_runner.sh`, `chmod +x` the
runner, confirm with `ops/watchdog.sh --classify` (prints `NEVER_STARTED` on a first run). **Deleting
`ops/STANDDOWN` is the LAST step, not the first.**
