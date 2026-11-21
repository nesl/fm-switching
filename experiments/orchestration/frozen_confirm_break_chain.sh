#!/bin/bash
# User priority item (1): flash's 32B engine-action confirmation (24c5492) in ONE break at a run boundary. STOP now; the
# driver exits after the current cell; run the wrapper (round-1 server, ~10 min + start); then resume driver v9.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user priority item 1): STOP set; after the current cell, the 32B engine-action confirmation break (flash 24c5492), then driver v9 resumes" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 5; done
echo "[$(date '+%F %T')] OPERATOR: 32B engine-action confirmation starts" >> $LOG
~/.venvs/fm-switching-vllm/bin/python experiments/orchestration/live2/run_confirm_engine_actions_32b.py > results/orchestration/live2/v5/engine_actions_32b_confirmation.stdout 2>&1
rc=$?
echo "[$(date '+%F %T')] OPERATOR: 32B engine-action confirmation ended rc=$rc; verdicts: $(jq -c '.headline // {stopped}' results/orchestration/live2/v5/engine_actions_32b_confirmation.json 2>/dev/null | cut -c1-300)" >> $LOG
while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 5; done
git add results/orchestration/live2/v5/engine_actions_32b_confirmation.json results/orchestration/live2/v5/engine_actions_32b_confirmation_server.json results/orchestration/live2/v5/engine_actions_32b_confirmation.stdout experiments/orchestration/live2/run_confirm_engine_actions_32b.py experiments/orchestration/frozen_confirm_break_chain.sh $LOG 2>/dev/null
git commit -q -m "32B engine-action confirmation (flash 24c5492) on the H100 round-1 server, rc=$rc" 2>/dev/null
for i in 1 2 3; do git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null && break; sleep 5; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v9.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v9 resumed after the confirmation break" >> $LOG
