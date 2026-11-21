#!/bin/bash
# 12:30 queue-change handover: STOP now; driver v14 finishes the current cell and exits; driver v15 starts (sweep seed 5 after noc3 s6, then the s7 pair;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (queue change 12:30): STOP set; after the current cell the driver hands over to v15" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v15.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v15 started" >> $LOG
