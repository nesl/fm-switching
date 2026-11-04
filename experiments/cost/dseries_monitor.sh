#!/usr/bin/env bash
# Once-per-second host record while the chain runs: all GPUs, processes every 10 s, loadavg; PCIe/util via dmon.
cd /home/pragya/Desktop/fm-switching
SID=$1
nvidia-smi dmon -s ut -d 1 -o T >> logs/dseries_dmon.log 2>&1 & DM=$!
while ps -s "$SID" >/dev/null 2>&1; do
  ts=$(date '+%F %T')
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used,power.draw,clocks.sm,temperature.gpu --format=csv,noheader | sed "s/^/$ts, /" >> logs/dseries_gpus.csv
  echo "$ts $(cat /proc/loadavg)" >> logs/dseries_loadavg.log
  if [ $(( $(date +%s) % 10 )) -eq 0 ]; then nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader | while IFS=, read g p m; do echo "$ts,$g,$p,$m,$(ps -o user= -p $p | tr -d ' ')"; done >> logs/dseries_gpu_procs.csv; fi
  sleep 1
done
kill $DM
