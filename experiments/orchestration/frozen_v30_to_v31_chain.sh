#!/bin/bash
# D187 overnight handover: STOP now; driver v30 finishes the current cell and exits; driver v31 starts
# (robot deadline read from the tag _L<s> token, for the D191 recall-deadline 2.5 s lists).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D191 prep): STOP set; after the current cell the driver hands over to v31" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v31.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v31 started" >> $LOG
