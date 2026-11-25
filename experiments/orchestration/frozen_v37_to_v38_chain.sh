#!/bin/bash
# v38 (D230 (7), staged, not installed until the E1 split fix): every cell passes --metrics-scrape and records metrics_health; _ms is a no-op kept for parse
# compatibility; the v36 pre-launch 0.5x server-args assertion and the push check by content stay. STOP now; driver v36
# finishes the current cell and exits; driver v37 starts. The watchdog's DRIVER line points at v38 from the same commit.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (v38): STOP set; after the current cell the driver hands over to v38" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v38.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v38 started" >> $LOG
