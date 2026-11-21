#!/bin/bash
# User ruling 2026-11-21 ~13:00: at the next run boundary after flash posts its live verification script for the
# per-request host-offload controls (max_offload_tokens / max_load_tokens / kv_load_tiers), take ONE ~10 min break on a
# fresh round-1 server, run the script UNCHANGED (nothing is built on this host), then resume the seed-5 sweep (driver v16,
# which skips finished cells).
# Trigger contract, posted by flash on origin as runs/OFFLOAD_VERIFY:
#   CMD <script path relative to the repo> <args...>     (run with the live2 venv python, exactly as written)
#   OUT <results dir relative to the repo>               (committed after the run)
# The script starts and stops its own round-1 server (study_live2_pilot.start_server(27), as run_live2_real --start-server).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
G=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
gpu_busy() { nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47; }
# 1. wait for the trigger on origin
while true; do
  git fetch -q 2>/dev/null
  git show origin/main:$OUT/OFFLOAD_VERIFY > /dev/null 2>&1 && break
  sleep 60
done
log "OPERATOR (offload-verify ruling): OFFLOAD_VERIFY on origin; STOP set, the break starts at the next run boundary"
touch $OUT/STOP
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
git pull --rebase -q 2>&1 | tail -2 >> $LOG
CMD=$(grep -m1 '^CMD ' $OUT/OFFLOAD_VERIFY | cut -c5-)
VOUT=$(grep -m1 '^OUT ' $OUT/OFFLOAD_VERIFY | cut -c5-)
if [ -z "$CMD" ]; then
  log "OFFLOAD VERIFY: no CMD line in OFFLOAD_VERIFY; break skipped, sweep resumes"
else
  while [ "$(gpu_busy)" != "0" ]; do sleep 2; done
  log "OFFLOAD VERIFY start HEAD $(git rev-parse --short HEAD): $CMD"
  mkdir -p results/orchestration/live2/offload_verify
  VL=results/orchestration/live2/offload_verify/offload_verify_h100.stdout
  ( export CUDA_VISIBLE_DEVICES=$G F_GPU_UUID=$G CLEAN_GPU_UUID=$G; export HF_TOKEN=$(cat hf-token.txt)
    timeout 900 ~/.venvs/fm-switching-vllm/bin/python $CMD ) > $VL 2>&1
  rc=$?
  log "OFFLOAD VERIFY end rc=$rc (124 = the 15-min cap)"
  # the script owns its server; if one of ours is still on GPU 2 after 60 s, stop it so the sweep starts clean
  for i in $(seq 1 30); do [ "$(gpu_busy)" = "0" ] && break; sleep 2; done
  for p in $(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | grep 4f1d7e47 | cut -d, -f1 | tr -d ' '); do
    [ "$(ps -o user= -p $p | tr -d ' ')" = "pragya" ] && { log "OFFLOAD VERIFY: leftover server pid $p stopped"; kill $p; }
  done
  for i in $(seq 1 60); do [ "$(gpu_busy)" = "0" ] && break; sleep 2; done
  git add $VL ${VOUT:+$VOUT} 2>/dev/null
  git commit -q -m "H100 offload-control live verification (user ruling ~13:00): flash's script run unchanged on a fresh round-1 server, rc=$rc" 2>/dev/null
  git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null
fi
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v16.sh"
log "OPERATOR: offload-verify break over; driver v16 restarted (seed-5 sweep resumes, then BASELINE_MATRIX)"
