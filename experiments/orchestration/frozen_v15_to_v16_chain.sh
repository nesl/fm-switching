#!/bin/bash
# D164 handover: STOP now; driver v15 finishes the current cell and exits; driver v16 starts (sweep seed 5, then BASELINE_MATRIX in its order;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D164): STOP set; after the current cell the driver hands over to v16" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v16.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v16 started" >> $LOG
