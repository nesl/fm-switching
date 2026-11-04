#!/usr/bin/env bash
# D-series GPU queue on GPU 2 (tmux "dseries"). Steps are read one at a time from the queue file; a step's done marker
# (logs/dseries_done/<name>) makes it skip on restart. One GPU job at a time. Host state logged at start/end of each step.
cd /home/pragya/Desktop/fm-switching
export DS_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=$DS_GPU_UUID CUDA_VISIBLE_DEVICES=$DS_GPU_UUID HF_HUB_OFFLINE=1
export VL=~/.venvs/fm-switching-vllm/bin/python
LOG=logs/dseries_chain.log; Q=${1:-logs/dseries_queue.txt}; mkdir -p logs/dseries_done
SID=$(ps -o sid= -p $$ | tr -d ' ')
tmux new-session -d -s dswd "bash experiments/cost/dseries_watchdog.sh $SID"
tmux new-session -d -s dsmon "bash experiments/cost/dseries_monitor.sh $SID"
host() { echo "--- host $1 $(date '+%F %T'): load $(cut -d' ' -f1-3 /proc/loadavg)"; nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader | while IFS=, read g p m; do echo "    $g pid$p $m $(ps -o user=,args= -p $p | cut -c1-100)"; done; }
while true; do
  line=$(grep -v '^#' "$Q" | while read -r name cmd; do [ -n "$name" ] && [ ! -e logs/dseries_done/$name ] && { echo "$name $cmd"; break; }; done)
  [ -z "$line" ] && break
  name=${line%% *}; cmd=${line#* }
  { echo "=== DS $(date '+%F %T') START $name: $cmd"; host start; } | tee -a $LOG
  bash -c "$cmd" 2>&1 | tee -a $LOG; rc=${PIPESTATUS[0]}
  { host end; echo "=== DS $(date '+%F %T') END rc=$rc $name"; } | tee -a $LOG
  [ $rc -eq 0 ] || { echo "=== DS CHAIN STOPPED at $name" | tee -a $LOG; exit $rc; }
  date -Is > logs/dseries_done/$name
done
echo "=== DS CHAIN QUEUE EMPTY $(date '+%F %T')" | tee -a $LOG
