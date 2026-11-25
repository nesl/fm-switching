#!/usr/bin/env bash
# D243 session runner. Wraps the watchdog's `claude -p` worker so that its EXIT DISPOSITION is
# recorded, not merely its last activity time.
#
# WHY THIS FILE EXISTS: every gate tried before this one was a FRESHNESS test (tmux session present,
# heartbeat mtime, log or commit recency). A freshness test cannot tell "the prompt completed and the
# process exited" from "the process died mid-work", because BOTH leave nothing running and a
# timestamp that only gets older. The distinguishing fact is not available from the outside at all:
# it is the worker's own exit status, which exists for one instant and must be WRITTEN DOWN. That is
# all this wrapper does.
#
# It writes ops/session.lease:
#   status=RUNNING  pid=<claude pid>  starttime=<its /proc stat field 22>  started=<epoch>
#   status=DONE     rc=<exit status>  finished=<epoch>   (plus the pid/starttime it had)
# pid is paired with starttime so a RECYCLED pid cannot be mistaken for the worker still running.
set -uo pipefail

REPO=${WATCHDOG_REPO:-/home/pragya/Desktop/FM-switching}
CLAUDE=${WATCHDOG_CLAUDE:-/home/pragya/.local/bin/claude}
LEASE=$REPO/ops/session.lease
TRACK=$REPO/ops/track.log

proc_starttime() {
  local st rest
  st=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
  rest=${st#*) }
  printf '%s\n' "$rest" | awk '{print $20}'
}

write_lease() {
  local tmp=$LEASE.$$
  printf '%s\n' "$@" > "$tmp" && mv -f "$tmp" "$LEASE"
}

"$CLAUDE" "$@" >> "$TRACK" 2>&1 &
cpid=$!
cstart=$(proc_starttime "$cpid")
started=$(date +%s)
write_lease "status=RUNNING" "pid=$cpid" "starttime=${cstart:-0}" "started=$started"

wait "$cpid"; rc=$?

# Reached on a normal exit AND on a signal death of the worker (rc 128+n), so both are recorded.
# If this wrapper is itself killed, the lease stays RUNNING with a pid that is gone, which the
# watchdog reads as a mid-work death. That is the correct reading: nothing is left doing the work.
write_lease "status=DONE" "pid=$cpid" "starttime=${cstart:-0}" "started=$started" \
            "rc=$rc" "finished=$(date +%s)"
printf 'exited rc=%s\n' "$rc" >> "$TRACK"
exit "$rc"
