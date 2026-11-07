#!/usr/bin/env bash
# StudyB1-flash watchdog. Monitors disk, GPU and both runs; restarts a dead run (resume is
# idempotent via the per-request `key`). Never touches a job it did not start.
set -u
REPO=/home/pragya/Desktop/FM-switching
VENV=/mnt/ssd/hf_models/venvs/fm-switching-vllm/bin/python
STOP_AT=$(date -d "2026-11-06 09:00:00" +%s)
MIN_FREE_GB=50
LOG=$REPO/logs/b1_watchdog.log

start_run () {  # $1=session $2=gpu $3=model $4=port
  tmux has-session -t "$1" 2>/dev/null && return 0
  echo "$(date '+%F %T') RESTART $1 (gpu $2, $3)" >> $LOG
  tmux new-session -d -s "$1" \
    "cd $REPO && $VENV experiments/benchmarks/b1_run.py --gpu $2 --model $3 --port $4 \
     --concurrency 8 --render-threads 8 2>&1 | tee -a $REPO/logs/b1_run_$3.log"
}

while :; do
  NOW=$(date +%s)
  FREE=$(df -BG --output=avail /mnt/ssd | tail -1 | tr -dc '0-9')
  GPU=$(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader | tr '\n' ' | ')
  FOREIGN=$(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader \
            | grep -vi "vllm\|python" | head -3 | tr '\n' ';')
  R4=$(tmux has-session -t b1_4b 2>/dev/null && echo up || echo DOWN)
  R8=$(tmux has-session -t b1_8b 2>/dev/null && echo up || echo DOWN)
  echo "$(date '+%F %T') free=${FREE}G gpu=[$GPU] 4B=$R4 8B=$R8 foreign=[$FOREIGN]" >> $LOG

  if [ "$FREE" -lt "$MIN_FREE_GB" ]; then
    echo "$(date '+%F %T') STOP: free ${FREE}G < ${MIN_FREE_GB}G -- killing runs" >> $LOG
    tmux kill-session -t b1_4b 2>/dev/null; tmux kill-session -t b1_8b 2>/dev/null
    break
  fi
  if [ "$NOW" -ge "$STOP_AT" ]; then
    echo "$(date '+%F %T') 09:00 reached -- no restarts from here" >> $LOG
    break
  fi
  start_run b1_4b 0 4B 8010
  start_run b1_8b 1 8B 8020
  sleep 120
done
echo "$(date '+%F %T') watchdog exit" >> $LOG
