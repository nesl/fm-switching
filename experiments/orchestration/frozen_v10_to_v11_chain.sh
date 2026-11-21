#!/bin/bash
# D159 handover: STOP now; driver v10 finishes the current EP-G cell and exits; driver v11 starts (reruns, load sweep,
# rq30 block, baselines fill gaps).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D159): STOP set; after the current EP-G cell the driver hands over to v11" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v11.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v11 started" >> $LOG
