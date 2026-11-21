#!/bin/bash
# device-wait hold handover: STOP now; driver v17 finishes the current cell and exits; driver v18 starts (same order, device-wait arms HELD;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (device-wait hold ruling): STOP set; after the current cell the driver hands over to v18" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v18.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v18 started" >> $LOG
