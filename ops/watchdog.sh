#!/usr/bin/env bash
# D187 (5) watchdog. Keeps the overnight track alive across an SSH outage.
# Cron: every 10 minutes plus @reboot. Starts the track inside tmux so SSH loss cannot kill it.
#
# DELIBERATE LIMITS, because a watchdog that restarts a FAILING session is worse than no watchdog:
#   - a restart budget (MAX_RESTARTS in WINDOW_S); once spent it logs and stops rather than looping
#   - it never starts a second session for a track that already has one (duplicate runs are a
#     recorded hazard in this project: parallel duplicates once produced duplicate trials)
#   - it uses only the permission settings already configured: no --dangerously-skip-permissions,
#     no TLS changes, no new credentials
set -uo pipefail
# WATCHDOG_REPO / WATCHDOG_CLAUDE exist so the gate can be exercised against a throwaway tree in a
# test. Cron passes no environment, so cron gets the defaults below.
REPO=${WATCHDOG_REPO:-/home/pragya/Desktop/FM-switching}
SESSION=fmsw-overnight
LOG=$REPO/ops/watchdog.log
STATE=$REPO/ops/watchdog.state
# Raised from 6 to 12 at 05:40Z. The restarts are no longer a crash loop, they are a POLL: a
# `claude -p` session exits when its prompt completes, so the heartbeat goes stale 600 s later and
# the next cron tick starts a fresh one-turn worker. That cadence is exactly 6 per hour, which was
# the old budget, so the loop would have exhausted its own ceiling and stopped overnight while the
# work was still progressing. 12 leaves headroom for jitter while still stopping a genuine crash
# loop, which would restart every 2 minutes and reach 30 per hour.
# D243 NOTE, value deliberately UNCHANGED: the justification above ("the restarts are a POLL") is
# retired by this commit, because a completed session no longer looks dead and so no longer polls.
# 12 is therefore no longer sized for anything in particular, and a SEPARATE defect recorded in
# research/OVERNIGHT_HANDOFF.md still stands: the window reset below means the budget has never once
# been spent in 109 restarts. Both are the user's call, not this change's, so nothing here moves.
MAX_RESTARTS=12
WINDOW_S=3600
CLAUDE=${WATCHDOG_CLAUDE:-/home/pragya/.local/bin/claude}
RUNNER=$REPO/ops/session_runner.sh
LEASE=$REPO/ops/session.lease
# --classify prints the liveness verdict and exits WITHOUT starting anything. Every claim in the
# D243 proof was produced with this flag, and it is the supported way to ask "what would you do now".
CLASSIFY_ONLY=0
[ "${1:-}" = "--classify" ] && CLASSIFY_ONLY=1
# --permission-mode auto, on the user's explicit ruling ("Resume session with auto mode"), which
# overrides D187 (5)'s earlier "only the permission settings already configured". Applied because
# the DEFAULT mode made a resumed session useless: it was refused repo writes, refused even grep
# READS under /tmp/claude-1001/ where the whole workflow lives, and prompted for tmux ls. A
# watchdog that faithfully restarts a session which cannot do the work is not resilience, and that
# limitation was reported to the user rather than worked around until they ruled. The H100 made the
# same change to its own watchdog at 4188b698 after the same test, so both boxes now resume in the
# mode their interactive sessions already run in. This is NOT a bypass: permission checks still
# apply, nothing disables TLS, and no credential is introduced.
PERM_MODE=auto
# DEFECT FOUND 2026-11-23: the prompt named a path that does NOT EXIST in this checkout. The
# handoff file is committed on origin/main and present in the /tmp worktree, but this repo is at an
# older commit, so a resumed session was told to read its own instructions from a missing file. The
# prompt now tells it where the file actually is and how to read it when the checkout is stale.
PROMPT='Read the overnight handoff: it is committed on origin/main as research/OVERNIGHT_HANDOFF.md. If that path is missing in this checkout, read it with: git show origin/main:research/OVERNIGHT_HANDOFF.md. Follow the D187 rules recorded in it and continue the next step. Before changing any live-path file, check whether another session is already working: read ops/watchdog.log and ops/track.log, and check for uncommitted edits in the shared worktree at /tmp/claude-1001/mapwt.'

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" >> "$LOG"; }

mkdir -p "$REPO/ops"
# D243 MOVED THE `tmux has-session` CHECK DOWN, to just before the launch. It used to sit here and
# exit 0 on its own, which made the NAME of a tmux session the liveness test - the gate line 51
# already records as wrong in both directions. Its absence is no longer read as death (the lease
# gate below decides that), and its presence is no longer read as health: a tmux window whose shell
# outlives the dead worker would otherwise suppress a restart that is genuinely needed. It survives
# only in its one sound role, which is refusing to create a SECOND session under the same name.

# HEARTBEAT GATE, added 02:40Z after the watchdog spawned three sessions in twenty minutes.
# The original condition was "does the tmux session exist", which was WRONG in both directions.
# The session doing the work was never in tmux, so it looked DOWN and the watchdog kept spawning;
# and each spawned `claude -p` exits when its prompt finishes, so the tmux session vanishes and the
# next cron tick spawns another. The spawned sessions are also effectively READ-ONLY (refused repo
# writes and even reads under /tmp), so each restart burned tokens and could not do the work.
# A live worker touches the heartbeat; if it is fresh, there is nothing to restart.
# *** THE HEARTBEAT GATE IS REMOVED BY D243 (2026-11-25). IT NEVER WORKED, IN TWO SEPARATE WAYS. ***
#   (a) BY DESIGN, as the comment at line 17 already says: a `claude -p` worker exits when its prompt
#       completes, so the heartbeat goes stale 600 s later on a HEALTHY completion and the watchdog
#       reads a finished session as a dead one. That produced 20 restarts and 16 one-shot resumes
#       that each found nothing to do.
#   (b) BY FACT: ops/heartbeat is 0 bytes with an mtime of 2026-11-23 21:55, and NOTHING IN THE REPO
#       EVER WRITES IT. The only two matches for a write are the comments on lines 56 and 58 of this
#       file. So the age was 119,664 s and climbing and the gate was unconditionally STALE: it was
#       not a weak liveness test, it was a constant.
# Both halves point the same way: NO FRESHNESS TEST CAN DO THIS JOB. "Finished and exited" and "died
# mid-work" leave the SAME outside evidence - nothing running, and a timestamp that only gets older.
# That is why D243's alternative of "a recent commit or track.log write" is ALSO REJECTED here: it is
# the same instrument. A session that finishes at 04:00 and a session killed at 04:00 have an equally
# old last commit at 05:00, and a worker legitimately inside one 21-minute GPU cell writes nothing at
# all, so recency confuses "slow but working" with "dead" in the one direction that costs tokens.
# The fact that separates the two cases is the worker's EXIT STATUS, which exists for one instant and
# has to be written down. ops/session_runner.sh writes it. This gate reads it.
# SELF-EXPIRING STANDDOWN, added 09:35Z after 20 restarts and 16 one-shot resumes that each found
# NOTHING TO DO. Every `claude -c -p` resume works, exits, lets the heartbeat go stale, and the next
# tick starts another, so with no work left the loop pays for a full session to run one cheap check.
# ops/STANDDOWN holds a unix EXPIRY on its first line. While now < expiry the watchdog logs and does
# NOT start Claude. IT EXPIRES ON ITS OWN so a stale file cannot silently disable resilience, and
# deleting the file restores normal behaviour immediately.
STANDDOWN=$REPO/ops/STANDDOWN
if [ -f "$STANDDOWN" ]; then
  exp=$(head -1 "$STANDDOWN" 2>/dev/null | tr -dc '0-9')
  now=$(date +%s)
  if [ -n "$exp" ] && [ "$now" -lt "$exp" ]; then
    log "STANDDOWN active for $(( (exp - now) / 60 )) more minutes, not starting Claude. \
Delete ops/STANDDOWN to resume immediately. Reason: $(sed -n 2p "$STANDDOWN")"
    # ORDERING, 2026-11-25 (user ruling, provisional): this exit is CONDITIONAL. It used to be
    # unconditional, which made `--classify` print NOTHING whenever ops/STANDDOWN existed
    # (stdout=[] rc=0, verified twice on this file), because CLASSIFY_ONLY is set at line 37 and
    # honoured only at the classify exit further down. A standdown must stop a session being
    # STARTED; it must not stop the gate being ASKED what it would do. Under --classify we fall
    # through to the lease gate and that classify exit, which is read-only and sits ABOVE the
    # alone-guard, the budget write and the tmux launch, so no session can start on that path.
    # Without --classify the behaviour is unchanged: log the line above and exit 0.
    [ "$CLASSIFY_ONLY" = 1 ] || exit 0
  fi
  if [ -n "$exp" ]; then
    log "STANDDOWN EXPIRED, resuming normal watchdog behaviour"
  fi
fi

# LEASE GATE (D243). ops/session.lease is written by ops/session_runner.sh, which wraps the worker.
# Four states, and the first two are the whole point of the change:
#   RUNNING + that exact process still present  -> LIVE,      do not restart
#   DONE    + rc=0                              -> COMPLETED, do not restart   <- the old gate's bug
#   RUNNING + that process gone                 -> DIED mid-work, restart
#   DONE    + rc!=0                             -> FAILED, restart
#   no lease at all                             -> NEVER_STARTED, restart (first run, or bootstrap)
# The identity test is pid PAIRED WITH /proc starttime, never a name and never a command-line
# pattern: `pgrep -f`/`pkill -f` self-match the checking shell and have taken out a session here.
# Pairing with starttime is what stops a RECYCLED pid from reading as the worker still running.
lease_get() { sed -n "s/^$1=//p" "$LEASE" 2>/dev/null | tail -1; }
proc_starttime() {
  local st rest
  st=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
  rest=${st#*) }
  printf '%s\n' "$rest" | awk '{print $20}'
}

VERDICT=NEVER_STARTED; DETAIL="no $LEASE"
if [ -f "$LEASE" ]; then
  l_status=$(lease_get status); l_pid=$(lease_get pid); l_start=$(lease_get starttime)
  l_rc=$(lease_get rc); l_started=$(lease_get started)
  case "$l_status" in
    RUNNING)
      cur=$(proc_starttime "${l_pid:-0}" || true)
      if [ -n "$cur" ] && [ "$cur" = "$l_start" ]; then
        VERDICT=LIVE
        DETAIL="pid $l_pid starttime $l_start still present, cwd=$(readlink -f /proc/$l_pid/cwd 2>/dev/null), \
running $(( $(date +%s) - ${l_started:-0} ))s"
      elif [ -n "$cur" ]; then
        VERDICT=DIED; DETAIL="pid $l_pid exists but starttime $cur != leased $l_start (RECYCLED PID)"
      else
        VERDICT=DIED; DETAIL="lease says RUNNING, pid $l_pid is gone: died holding work"
      fi
      ;;
    DONE)
      if [ "${l_rc:-1}" = "0" ]; then
        VERDICT=COMPLETED; DETAIL="worker pid $l_pid finished its prompt cleanly (rc=0) at $(lease_get finished)"
      else
        VERDICT=FAILED; DETAIL="worker pid $l_pid exited rc=$l_rc at $(lease_get finished)"
      fi
      ;;
    *) VERDICT=NEVER_STARTED; DETAIL="unreadable lease (status='$l_status')" ;;
  esac
fi

# HUNG WARNING, LOG ONLY, AND DELIBERATELY NOT A RESTART. A process that is present but making no
# progress is the one case this gate cannot call, and acting on a progress timestamp would reinstate
# exactly the instrument removed above. So it is reported for a human and nothing else.
MAX_RUN_S=21600
if [ "$VERDICT" = LIVE ]; then
  ran=$(( $(date +%s) - $(lease_get started) ))
  if [ "$ran" -gt "$MAX_RUN_S" ]; then
    newest=0
    for f in "$REPO/ops/track.log" "$REPO/.git/HEAD"; do
      [ -f "$f" ] && m=$(stat -c %Y "$f") && [ "$m" -gt "$newest" ] && newest=$m
    done
    log "WARNING: worker alive ${ran}s (> ${MAX_RUN_S}s); newest progress write $(( $(date +%s) - newest ))s \
ago. NOT restarting: a live process is never killed by this watchdog. Check it by hand."
  fi
fi

log "LIVENESS $VERDICT: $DETAIL"
if [ "$CLASSIFY_ONLY" = 1 ]; then
  echo "$VERDICT"
  exit 0
fi
case "$VERDICT" in
  LIVE)      exit 0 ;;
  COMPLETED) exit 0 ;;
esac

# DEFECT FOUND 2026-11-23 02:2x: guarding only on the tmux session NAME is not enough. A Claude
# session started any other way (a user resume, an IDE, a second terminal) is invisible to that
# test, so the watchdog can start a SECOND session onto the same repo and the same handoff file.
# That happened: the 02:20:01Z restart ran alongside a separately resumed session, and both were
# told to "continue the next step" on the same work. Duplicate concurrent runs are a recorded
# hazard in this project. So: refuse to start if any claude process is already working this repo.
# `ps -C` plus grep, never `pgrep -f`, which self-matches the checking shell.
# D243 REPLACES THE `ps -C claude ... grep -- "-c -p"` FORM OF THIS GUARD, which was measured on this
# box on 2026-11-25 and reported "alone" while FIVE claude processes were live, one of them with its
# cwd in this very repo: none of their command lines contained the literal `-c -p`, so the guard was
# a constant false. That is the FOURTH alone-guard in this project (name pattern, basename list, tree
# snapshot) to report alone:true on a busy box. This one is bounded by WHAT a process IS: its
# /proc/<pid>/exe resolving into a claude install, AND its /proc/<pid>/cwd being inside this repo. It
# logs the pids it classified, so its verdict can be checked rather than trusted.
others=""
self_chain=" $$ $PPID "
for d in /proc/[0-9]*; do
  pid=${d#/proc/}
  case "$self_chain" in *" $pid "*) continue ;; esac
  exe=$(readlink -f "$d/exe" 2>/dev/null) || continue
  case "$exe" in *claude*) ;; *) continue ;; esac
  cwd=$(readlink -f "$d/cwd" 2>/dev/null) || continue
  case "$cwd" in "$REPO"|"$REPO"/*) others="$others $pid" ;; esac
done
if [ -n "$others" ]; then
  log "STAND DOWN: claude process(es)$others have cwd inside $REPO; not starting a second one"
  exit 0
fi
log "alone check: no claude process has cwd inside $REPO"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "STAND DOWN: liveness $VERDICT but tmux session $SESSION still exists; refusing to create a \
second one. If its worker is really gone, kill the session and the next tick will restart it."
  exit 0
fi

now=$(date +%s)
count=0; first=$now
if [ -f "$STATE" ]; then
  read -r first count < "$STATE" 2>/dev/null || { first=$now; count=0; }
  if [ $((now - first)) -gt $WINDOW_S ]; then first=$now; count=0; fi
fi
if [ "$count" -ge "$MAX_RESTARTS" ]; then
  log "BUDGET SPENT: $count restarts within ${WINDOW_S}s, NOT restarting. A session that dies this \
often is failing, not unlucky; leaving it down for the user."
  exit 0
fi
count=$((count + 1))
echo "$first $count" > "$STATE"

log "RESTART $count/$MAX_RESTARTS: liveness $VERDICT, starting in tmux"
# The worker now runs under ops/session_runner.sh, which records the exit status the gate above
# reads. Launching $CLAUDE directly would leave no lease and every tick would read NEVER_STARTED.
tmux new-session -d -s "$SESSION" -c "$REPO" \
  "$RUNNER -c --permission-mode $PERM_MODE -p '$PROMPT'" \
  && log "started" || log "FAILED to start tmux session"
