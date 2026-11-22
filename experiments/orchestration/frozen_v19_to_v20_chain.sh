#!/bin/bash
# D172 handover: STOP now; driver v19 finishes the current cell and exits; driver v20 starts (V6_CELLS pre-empt;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D172): STOP set; after the current cell the driver hands over to v20" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v20.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v20 started" >> $LOG
