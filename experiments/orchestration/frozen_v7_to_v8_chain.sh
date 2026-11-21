#!/bin/bash
# User ruling 2026-11-20 (pre-21:00 priority): WARM-ALL calibration cells ahead of the remaining handful seed-4 arms.
# STOP is set now, driver v7 exits after the current cell (b7 3 s seed 4), then driver v8 starts with the new order.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user priority ruling): STOP set; after the current cell the driver hands over to v8 (WARM-ALL calibration ahead of the remaining handful seed-4 arms)" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v8.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v8 started" >> $LOG
