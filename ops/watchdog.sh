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
MAX_RESTARTS=6
WINDOW_S=3600
CLAUDE=/home/pragya/.local/bin/claude
PROMPT='Read research/OVERNIGHT_HANDOFF.md and the D187 rules recorded in it; continue the next step.'

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" >> "$LOG"; }

mkdir -p "$REPO/ops"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "OK session $SESSION alive"
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
  "$CLAUDE -c -p '$PROMPT' >> $REPO/ops/track.log 2>&1; echo exited >> $REPO/ops/track.log" \
  && log "started" || log "FAILED to start tmux session"
