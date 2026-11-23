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
REPO=/home/pragya/Desktop/FM-switching
SESSION=fmsw-overnight
LOG=$REPO/ops/watchdog.log
STATE=$REPO/ops/watchdog.state
# Raised from 6 to 12 at 05:40Z. The restarts are no longer a crash loop, they are a POLL: a
# `claude -p` session exits when its prompt completes, so the heartbeat goes stale 600 s later and
# the next cron tick starts a fresh one-turn worker. That cadence is exactly 6 per hour, which was
# the old budget, so the loop would have exhausted its own ceiling and stopped overnight while the
# work was still progressing. 12 leaves headroom for jitter while still stopping a genuine crash
# loop, which would restart every 2 minutes and reach 30 per hour.
MAX_RESTARTS=12
WINDOW_S=3600
CLAUDE=/home/pragya/.local/bin/claude
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
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "OK session $SESSION alive"
  exit 0
fi

# HEARTBEAT GATE, added 02:40Z after the watchdog spawned three sessions in twenty minutes.
# The original condition was "does the tmux session exist", which was WRONG in both directions.
# The session doing the work was never in tmux, so it looked DOWN and the watchdog kept spawning;
# and each spawned `claude -p` exits when its prompt finishes, so the tmux session vanishes and the
# next cron tick spawns another. The spawned sessions are also effectively READ-ONLY (refused repo
# writes and even reads under /tmp), so each restart burned tokens and could not do the work.
# A live worker touches the heartbeat; if it is fresh, there is nothing to restart.
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
    exit 0
  fi
  if [ -n "$exp" ]; then
    log "STANDDOWN EXPIRED, resuming normal watchdog behaviour"
  fi
fi

HEARTBEAT=$REPO/ops/heartbeat
STALE_S=600
if [ -f "$HEARTBEAT" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT") ))
  if [ "$age" -lt "$STALE_S" ]; then
    log "OK worker heartbeat ${age}s old (< ${STALE_S}s), not restarting"
    exit 0
  fi
  log "heartbeat STALE at ${age}s"
fi

# DEFECT FOUND 2026-11-23 02:2x: guarding only on the tmux session NAME is not enough. A Claude
# session started any other way (a user resume, an IDE, a second terminal) is invisible to that
# test, so the watchdog can start a SECOND session onto the same repo and the same handoff file.
# That happened: the 02:20:01Z restart ran alongside a separately resumed session, and both were
# told to "continue the next step" on the same work. Duplicate concurrent runs are a recorded
# hazard in this project. So: refuse to start if any claude process is already working this repo.
# `ps -C` plus grep, never `pgrep -f`, which self-matches the checking shell.
if ps -C claude -o args= 2>/dev/null | grep -v grep | grep -q -- "-c -p"; then
  log "STAND DOWN: a claude session is already working this repo; not starting a second one"
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

log "RESTART $count/$MAX_RESTARTS: session $SESSION absent, starting in tmux"
tmux new-session -d -s "$SESSION" -c "$REPO" \
  "$CLAUDE -c --permission-mode $PERM_MODE -p '$PROMPT' >> $REPO/ops/track.log 2>&1; echo exited >> $REPO/ops/track.log" \
  && log "started" || log "FAILED to start tmux session"
