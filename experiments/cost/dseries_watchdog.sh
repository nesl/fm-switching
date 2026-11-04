#!/usr/bin/env bash
# D-series watchdog (GPU 2): any GPU-2 process outside the chain's session -> stop the chain (TERM, then KILL after 10 s).
cd /home/pragya/Desktop/fm-switching
UUID=${DS_GPU_UUID:-GPU-4f1d7e47-e769-a289-4860-e71c0d97267c}
SID=$1; LOG=logs/dseries_chain.log
while ps -s "$SID" >/dev/null 2>&1; do
  for pid in $(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader 2>/dev/null | awk -F', ' -v u=$UUID '$1==u{print $2}'); do
    s=$(ps -o sid= -p "$pid" 2>/dev/null | tr -d ' '); [ -z "$s" ] && s="?(exited)"
    if [ "$s" != "$SID" ]; then
      owner=$(ps -o user= -p "$pid" 2>/dev/null | tr -d ' '); cmd=$(ps -o args= -p "$pid" 2>/dev/null)
      pkill -TERM -s "$SID"; sleep 10; pkill -9 -s "$SID"
      echo "=== DS $(date '+%F %T') FOREIGN PROCESS ON GPU 2: pid=$pid sid=$s owner=${owner:-?} cmd=${cmd:0:160} — CHAIN STOPPED ===" | tee -a $LOG
      exit 1
    fi
  done
  sleep 1
done
