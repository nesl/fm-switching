#!/bin/bash
# 08:10 rulings handover: STOP now; driver v11 finishes the current cell and exits; driver v12 starts (RQ30 on the trace alone, seeds 4 to 7;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user rulings 08:10): STOP set; after the current cell the driver hands over to v12" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v12.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v12 started" >> $LOG
