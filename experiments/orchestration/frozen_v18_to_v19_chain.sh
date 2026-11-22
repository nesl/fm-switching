#!/bin/bash
# D169 handover: STOP now; driver v18 finishes the current cell and exits; driver v19 starts (seed-7 pair at the front of the paper core, older-tag r3 / streamscout dropped;
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D169 + gap-fill drop): STOP set; after the current cell the driver hands over to v19" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v19.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v19 started" >> $LOG
