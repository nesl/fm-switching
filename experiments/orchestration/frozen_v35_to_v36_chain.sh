#!/bin/bash
# v36 (2026-11-24): _ms tag -> runner --metrics-scrape (flash, rung-4 pass 1 at 0.5x); pre-launch assertion of the real
# 0.5x server args for _kv0.5r tags; push check by content. STOP now; driver v35 finishes the current cell and exits;
# driver v36 starts. The watchdog's DRIVER line points at v36 from the same commit.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (v36): STOP set; after the current cell the driver hands over to v36" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v36.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v36 started" >> $LOG
