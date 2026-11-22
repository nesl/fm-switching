#!/bin/bash
# overnight handover (replaces the v19 to v20 chain): STOP now; driver v19 finishes the current cell and exits; driver v21 starts (V6_CELLS, V6STATE_CELLS, V6FAIR_CELLS ahead of baselines;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (overnight brief): STOP set; after the current cell the driver hands over to v21 (v20 superseded, never started)" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v21.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v21 started" >> $LOG
