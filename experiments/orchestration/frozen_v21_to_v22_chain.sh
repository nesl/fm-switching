#!/bin/bash
# v6-gate handover: STOP now; driver v21 finishes the current cell and exits; driver v22 starts (v6 cell lists only after the operator gate;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (harm_warm ruling, v6 gate): STOP set; after the current cell the driver hands over to v22" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v22.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v22 started" >> $LOG
