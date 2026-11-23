#!/bin/bash
# D187 overnight handover: STOP now; driver v27 finishes the current cell (eco-llm s7) and exits; driver v28 starts
# (any other gated list FIRST, then V6SHARES; an empty queue polls instead of exiting).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D187 overnight): STOP set; after the current cell the driver hands over to v28" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v28.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v28 started" >> $LOG
