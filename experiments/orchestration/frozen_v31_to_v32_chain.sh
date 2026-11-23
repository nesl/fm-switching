#!/bin/bash
# D211 recording handover: STOP now; driver v31 finishes the current cell and exits; driver v32 starts
# (v32 = v31 plus, from the same 10-s /metrics scrape, host_counters_d211.log per cell: the host-hit counters with
# their labels, a unix timestamp and /proc/loadavg with magnitude. Read-only; the measured launch is unchanged).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D211 recording): STOP set; after the current cell the driver hands over to v32" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v32.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v32 started" >> $LOG
