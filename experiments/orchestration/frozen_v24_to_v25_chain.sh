#!/bin/bash
# C5-first handover: STOP now; driver v24 finishes the current cell and exits; driver v25 starts (uo s4-5, C5DIAG_CELLS, uo s6-7, matrix tail, _kv0.5;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (C5-first addendum): STOP set; after the current cell the driver hands over to v25" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v25.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v25 started" >> $LOG
