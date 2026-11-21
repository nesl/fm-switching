#!/bin/bash
# User ruling 2026-11-20 (D147 / D152): from the run boundary after the D151 calibration cells, robot deadline 3 s.
# Sets STOP as soon as the last calibration cell (llf 16 seed 6) starts, waits for driver v6 to exit at its end, then
# removes STOP and starts driver v7 (the 3 s handful, then the 3 s sweep).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
until grep -q "start llf_n16_s6_1200s_h27_3t " $LOG; do sleep 20; done
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D147 / D152): STOP set; after the last D151 calibration cell the driver hands over to v7 (robot deadline 3 s: the handful first, then the sweep)" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 15; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v7.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v7 started" >> $LOG
