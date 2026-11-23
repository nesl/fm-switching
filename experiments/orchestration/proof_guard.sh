#!/bin/bash
# D209 proof guard (user ruling, 2026-11-23, option 2). Runs ONE CPU-only dry proof during live cells:
#   unpinned (the measured launch is not changed), nice 19, CUDA_VISIBLE_DEVICES empty,
#   at most two proof processes at a time, never across a run boundary.
# Usage: proof_guard.sh <expected_seconds> <label> -- <command...>
# A proof starts only if now + expected <= the current cell's start + DEADLINE_S; otherwise it waits for
# the next cell start (+ START_GRACE_S) and re-checks. It is killed (SIGINT, then SIGKILL) at the deadline,
# so it can never straddle a boundary. Its CPU (cores, process group) is sampled every 5 s into
# $PL/proof_load.jsonl; proof_load_annotate.sh folds that into each cell's cell.json.
set -u
cd /home/pragya/Desktop/fm-switching
EXP=$1; LABEL=$2; shift 2; [ "${1:-}" = "--" ] && shift
LOG=results/orchestration/live2/frozen_test/frozen_grid.log
PL=$HOME/data/live2/proofs; mkdir -p $PL/running
DEADLINE_S=${DEADLINE_S:-1230}     # cells take ~1,280 s start to end; stop proofs 50 s before
START_GRACE_S=${START_GRACE_S:-60} # never start inside the first minute of a cell (server warm-up)
MAXP=2
plog() { echo "{\"t\": $(date +%s.%N | cut -c1-14), \"label\": \"$LABEL\", $1}" >> $PL/proof_load.jsonl; }
cell_start() { local l; l=$(grep -E "\] start " $LOG | tail -1); date -d "$(echo "$l" | cut -c2-20)" +%s; }
alive() { local n=0; for f in $PL/running/*.pid; do [ -f "$f" ] || continue; kill -0 "$(cat $f)" 2>/dev/null && n=$((n+1)) || rm -f "$f"; done; echo $n; }
while true; do
  now=$(date +%s); S=$(cell_start); dl=$((S + DEADLINE_S))
  if [ "$(alive)" -lt $MAXP ] && [ $now -ge $((S + START_GRACE_S)) ] && [ $((now + EXP)) -le $dl ]; then break; fi
  sleep 15
done
plog "\"event\": \"start\", \"expected_s\": $EXP, \"cell_start\": $S, \"deadline\": $dl, \"cmd\": $(printf '%s' "$*" | jq -Rs .)"
CUDA_VISIBLE_DEVICES= setsid nice -n 19 "$@" > $PL/${LABEL}.out 2>&1 &
pid=$!; echo $pid > $PL/running/${LABEL}.pid
while kill -0 $pid 2>/dev/null; do
  c=$(ps -o pcpu= -g $pid 2>/dev/null | awk '{s+=$1} END{printf "%.3f", s/100}')
  plog "\"event\": \"sample\", \"cores\": ${c:-0}"
  if [ $(date +%s) -ge $dl ]; then
    plog "\"event\": \"killed_at_deadline\""; kill -INT -$pid 2>/dev/null; sleep 10; kill -KILL -$pid 2>/dev/null; break
  fi
  sleep 5
done
wait $pid 2>/dev/null; rc=$?
rm -f $PL/running/${LABEL}.pid
plog "\"event\": \"end\", \"rc\": $rc"
exit $rc
