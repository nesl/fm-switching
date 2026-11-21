#!/bin/bash
# 11:10 queue-change handover: STOP now; driver v13 finishes the current cell and exits; driver v14 starts (V5FULL first; sweep seed 5 after the paired block;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user queue change 11:10): STOP set; after the current cell the driver hands over to v14" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v14.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v14 started" >> $LOG
