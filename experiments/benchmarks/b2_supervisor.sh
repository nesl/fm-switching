#!/usr/bin/env bash
# StudyB2 supervisor (tmux "b2sup"): (re)starts the B2 queue (tmux "b2chain") when no queue of ours is running, the queue
# has pending steps, there is no HALT file, and GPU 2 has had no compute process for 5 consecutive minutes. This starts
# Stage 1 after StudyB1's chain ("dseries") ends, and resumes after a foreign-process stop once GPU 2 is free again.
cd /home/pragya/Desktop/fm-switching
UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c; Q=logs/b2_queue.txt; LOG=logs/b2_supervisor.log; free=0
while true; do
  if tmux has-session -t b2chain 2>/dev/null || tmux has-session -t dseries 2>/dev/null; then free=0
  elif [ -e logs/dseries_HALT ]; then free=0
  elif [ -z "$(grep -v '^#' $Q 2>/dev/null | while read -r n c; do [ -n "$n" ] && [ ! -e logs/dseries_done/$n ] && { echo $n; break; }; done)" ]; then free=0
  else
    busy=$(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader 2>/dev/null | grep -c "^$UUID")
    if [ "$busy" -eq 0 ]; then free=$((free+1)); else
      [ $free -gt 0 ] || echo "$(date '+%F %T') GPU 2 busy ($(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader | grep "^$UUID" | head -3 | tr '\n' ' ')) — waiting" >> $LOG
      free=0; fi
    if [ $free -ge 5 ]; then
      echo "$(date '+%F %T') GPU 2 free 5 min; starting b2chain" >> $LOG
      tmux new-session -d -s b2chain "bash experiments/benchmarks/b2_chain.sh $Q"; free=0
    fi
  fi
  sleep 60
done
