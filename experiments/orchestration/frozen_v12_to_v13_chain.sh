#!/bin/bash
# 09:40 queue-change handover: STOP now; driver v12 finishes the current cell and exits; driver v13 starts (v5-rules-2 paired block pre-empts the sweep;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user queue change 09:40): STOP set; after the current cell the driver hands over to v13" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v13.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v13 started" >> $LOG
