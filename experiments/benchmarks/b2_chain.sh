#!/usr/bin/env bash
# StudyB2 GPU queue on GPU 2 (tmux "b2chain"); a copy of experiments/cost/dseries_chain.sh with a hard-stop file.
# Steps are read one at a time from the queue file (re-read every step, so lines can be appended while it runs); a step's
# done marker (logs/dseries_done/<name>) makes it skip on restart. CONTINUE_ON_FAIL=1: a failed step gets a FAILED marker
# and the queue goes on. logs/dseries_HALT (b1_common SHA change, frame-hash mismatch, repeat-control failure) stops the
# queue before the next step; only the user clears it. A foreign process on GPU 2 stops everything via the watchdog;
# experiments/benchmarks/b2_supervisor.sh restarts the queue once GPU 2 has been free for 5 minutes.
cd /home/pragya/Desktop/fm-switching
export DS_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=$DS_GPU_UUID CUDA_VISIBLE_DEVICES=$DS_GPU_UUID HF_HUB_OFFLINE=1
export VL=~/.venvs/fm-switching-vllm/bin/python
export CONTINUE_ON_FAIL=1
LOG=logs/dseries_chain.log; Q=${1:-logs/b2_queue.txt}; mkdir -p logs/dseries_done
SID=$(ps -o sid= -p $$ | tr -d ' ')
tmux kill-session -t b2wd 2>/dev/null; tmux kill-session -t b2mon 2>/dev/null
tmux new-session -d -s b2wd "bash experiments/cost/dseries_watchdog.sh $SID"
tmux new-session -d -s b2mon "bash experiments/cost/dseries_monitor.sh $SID"
host() { echo "--- host $1 $(date '+%F %T'): load $(cut -d' ' -f1-3 /proc/loadavg)"; nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader | while IFS=, read g p m; do echo "    $g pid$p $m $(ps -o user=,args= -p $p | cut -c1-100)"; done; }
while true; do
  if [ -e logs/dseries_HALT ]; then echo "=== DS $(date '+%F %T') CHAIN HALTED (logs/dseries_HALT): $(cat logs/dseries_HALT)" | tee -a $LOG; break; fi
  line=$(grep -v '^#' "$Q" | while read -r name cmd; do [ -n "$name" ] && [ ! -e logs/dseries_done/$name ] && { echo "$name $cmd"; break; }; done)
  [ -z "$line" ] && { echo "=== DS CHAIN QUEUE EMPTY $(date '+%F %T')" | tee -a $LOG; break; }
  name=${line%% *}; cmd=${line#* }
  { echo "=== DS $(date '+%F %T') START $name: $cmd"; host start; } | tee -a $LOG
  bash -c "$cmd" 2>&1 | tee -a $LOG; rc=${PIPESTATUS[0]}
  { host end; echo "=== DS $(date '+%F %T') END rc=$rc $name"; } | tee -a $LOG
  if [ $rc -ne 0 ]; then
    if [ -e logs/dseries_HALT ]; then echo "=== DS $(date '+%F %T') CHAIN HALTED at $name: $(cat logs/dseries_HALT)" | tee -a $LOG; break; fi
    echo "FAILED rc=$rc $(date -Is)" > logs/dseries_done/$name
    echo "=== DS $(date '+%F %T') JOB FAILED/STOPPED: $name (rc=$rc) — recorded; continuing with the next job" | tee -a $LOG
    continue
  fi
  date -Is > logs/dseries_done/$name
done
tmux kill-session -t b2mon 2>/dev/null; tmux kill-session -t b2wd 2>/dev/null
