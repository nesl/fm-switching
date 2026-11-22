#!/bin/bash
# kv0.5 memory-sweep handover: STOP now; driver v22 finishes the current cell and exits; driver v23 starts (after BASELINE_MATRIX the paper core at _kv0.5, no old gap-fill;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (E5 memory-sweep ruling): STOP set; after the current cell the driver hands over to v23" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v23.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v23 started" >> $LOG
