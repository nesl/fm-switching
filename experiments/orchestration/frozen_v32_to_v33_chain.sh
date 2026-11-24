#!/bin/bash
# EVAL_PLAN handover: STOP now; driver v32 finishes the current cell and exits; driver v33 starts
# (v33 = v32 plus tag tokens _rq<k> (re-ask) and _c<d>-<r>-<a> (composition), and GPU 2 utilization, memory and
# generation tokens on the 10-s host_counters_d211.log line; every existing tag gives v32's arguments exactly).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (EVAL_PLAN): STOP set; after the current cell the driver hands over to v33" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v33.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v33 started" >> $LOG
