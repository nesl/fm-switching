#!/bin/bash
# D187 overnight handover: STOP now; driver v29 finishes the current cell and exits; driver v30 starts
# (server flags from any gated list for the D189 real-0.25x cells; engine KV pool logged per cell).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D189 prep): STOP set; after the current cell the driver hands over to v30" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v30.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v30 started" >> $LOG
