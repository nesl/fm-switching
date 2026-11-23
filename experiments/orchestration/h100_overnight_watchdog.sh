#!/bin/bash
# D187 OVERNIGHT watchdog (user brief 2026-11-22 ~18:10), run by cron every 10 min and @reboot. Bash only, no host
# Python. DRY=1 logs what it would do and changes nothing.
#   1. Driver: if neither the tmux session "frozengrid" nor a driver process exists (and no handover chain is running),
#      restart the latest driver in tmux. The driver skips finished cells (cell.json present and valid), so this resumes
#      from the last committed state. A STOP file younger than 30 min is an operator stop and is respected; an older one
#      with no driver is stale and is removed (logged), so GPU 2 never idles on a forgotten STOP.
#   2. Server: the harness starts its own vLLM server per cell (--start-server, committed launch config) and passes the
#      preflight before each cell, so "restart the server" means "restart the driver". What can block it is an ORPHANED
#      server (ours, on GPU 2, no harness process): the driver waits for GPU 2 to be free before each cell, so an orphan
#      deadlocks it. An orphan seen on two consecutive passes is stopped with SIGINT, then SIGKILL after 30 s.
#      A process on GPU 2 that is not ours is NEVER touched; it is logged.
#   3. Claude: if no claude process of this user exists and none was launched in the last 20 min, resume this
#      conversation non-interactively in tmux "claudeh100" with --permission-mode auto, the mode the interactive
#      session runs in (user ruling ~19:00, after the test showed the default mode refuses tmux, ps, git and writes).
#      It runs from /home/pragya/Desktop because that is the project directory of the conversation being continued.
cd /home/pragya/Desktop/fm-switching || exit 1
export PATH=/home/pragya/.local/bin:/usr/local/bin:/usr/bin:/bin
ST=$HOME/data/live2/watchdog; mkdir -p $ST
exec 9>$ST/lock; flock -n 9 || exit 0
OUT=results/orchestration/live2/frozen_test/runs
LOG=results/orchestration/live2/frozen_test/frozen_grid.log
WL=$ST/watchdog.log
DRIVER=experiments/orchestration/study_frozen_grid_driver_v30.sh
GPU=4f1d7e47
HP='^/home/pragya/.venvs/fm-switching-vllm/bin/python[0-9.]* experiments/orchestration/live2/(run_live2_real|offload_verify)\.py'
DRY=${DRY:-0}
# test overrides (DRY tests only): names the checks look for
SESS=${SESS:-frozengrid}; DPAT=${DPAT:-study_frozen_grid_driver_v[0-9]+\.sh}; CPAT=${CPAT:-frozen_v[0-9]+_to_v[0-9]+_chain\.sh}; CPROC=${CPROC:-claude}; CSESS=${CSESS:-claudeh100}
w() { echo "[$(date '+%F %T')] $*" >> $WL; }
act() { if [ "$DRY" = 1 ]; then w "DRY, would: $*"; else w "DO: $*"; eval "$*"; fi; }

# 1. driver
if pgrep -u pragya -f "$CPAT" >/dev/null; then
  w "driver: handover chain running, no action"
elif tmux has-session -t $SESS 2>/dev/null || pgrep -u pragya -f "$DPAT" >/dev/null; then
  w "driver: running"
else
  restart=1
  if [ -f $ST/HOLD ]; then w "driver: absent, HOLD file present (operator hold, e.g. a broken import on origin), not restarting"; restart=0; fi
  if [ $restart = 1 ] && [ -f $OUT/STOP ]; then
    age=$(( $(date +%s) - $(stat -c %Y $OUT/STOP) ))
    if [ $age -lt 1800 ]; then w "driver: absent, STOP is ${age}s old (operator stop), not restarting"; restart=0
    else act "rm -f $OUT/STOP"; [ "$DRY" = 1 ] || echo "[$(date '+%F %T')] WATCHDOG (D187): stale STOP (${age}s, no driver) removed" >> $LOG; fi
  fi
  if [ $restart = 1 ]; then
    act "tmux new-session -d -s frozengrid 'bash $DRIVER'"
    [ "$DRY" = 1 ] || echo "[$(date '+%F %T')] WATCHDOG (D187): driver was not running; restarted $(basename $DRIVER) in tmux (finished cells are skipped; each cell starts its own server and preflight)" >> $LOG
  fi
fi

# 2. orphaned server (ours, on GPU 2, no harness), confirmed on two consecutive passes
pids=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader 2>/dev/null | grep $GPU | cut -d, -f1 | tr -d ' ')
ours=""
for p in $pids; do
  u=$(ps -o user= -p $p 2>/dev/null | tr -d ' ')
  if [ "$u" = pragya ]; then ours="$ours $p"; else w "FOREIGN process on GPU 2: pid $p user $u (not touched)"; fi
done
if [ -n "$ours" ] && ! pgrep -u pragya -f "$HP" >/dev/null; then
  if [ -f $ST/orphan_seen ]; then
    for p in $ours; do act "kill -INT $p"; done
    [ "$DRY" = 1 ] || { sleep 30; for p in $ours; do kill -0 $p 2>/dev/null && { w "DO: kill -9 $p"; kill -9 $p; }; done
      echo "[$(date '+%F %T')] WATCHDOG (D187): orphaned server on GPU 2 (pids$ours, no harness on two passes) stopped: SIGINT, then SIGKILL" >> $LOG; }
    rm -f $ST/orphan_seen
  else w "server: GPU 2 held by ours (pids$ours) with no harness; confirming on the next pass"; touch $ST/orphan_seen; fi
else
  rm -f $ST/orphan_seen
  if [ -n "$ours" ]; then w "server: held by a harness run (pids$ours)"; else w "server: GPU 2 free"; fi
fi

# 3. Claude session
if pgrep -u pragya -x $CPROC >/dev/null || tmux has-session -t $CSESS 2>/dev/null; then
  w "claude: a session is running"
elif [ -f $ST/claude_launched ] && [ $(( $(date +%s) - $(stat -c %Y $ST/claude_launched) )) -lt 600 ]; then
  w "claude: absent, last launch under 10 min ago, waiting"
else
  act "tmux new-session -d -s claudeh100 \"cd /home/pragya/Desktop && claude -c --permission-mode auto -p 'Read fm-switching/research/OVERNIGHT_HANDOFF_H100.md (and fm-switching/research/OVERNIGHT_HANDOFF.md for flash state) and continue the H100 queue under D187' >> $ST/claude_resume.log 2>&1\""
  [ "$DRY" = 1 ] || touch $ST/claude_launched
fi
