#!/bin/bash
# D179 handover: STOP now; driver v25 finishes the current cell and exits; driver v26 starts (gated V6SHARES_CELLS after uo s6-7, before the matrix tail;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D179 addendum): STOP set; after the current cell the driver hands over to v26" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v26.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v26 started" >> $LOG
