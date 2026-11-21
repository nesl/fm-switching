#!/bin/bash
# User decision 2026-11-20 (~18:50): policy-unblocking work first. STOP now, driver v8 exits after the current cell
# (simplestream 3 s seed 4), driver v9 starts with the priority order (WARMALL_CELLS_1F first).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user priority decision): STOP set; after the current cell the driver hands over to v9 (policy-unblocking first: WARM-ALL 1F, EP-G WARM-ALL, v5-rules, v5; baselines fill gaps)" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v9.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v9 started" >> $LOG
