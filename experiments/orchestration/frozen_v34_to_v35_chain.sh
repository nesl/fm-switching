#!/bin/bash
# Push fix: STOP now; driver v34 finishes the current cell and exits; driver v35 starts.
# v35 = v34 with the per-cell push loop naming its target (git pull --rebase origin main; git push origin HEAD:main):
# a bare `git pull --rebase` fails on this clone ("Cannot rebase onto multiple branches"), so v34 never pushed.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (push fix): STOP set; after the current cell the driver hands over to v35" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v35.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v35 started" >> $LOG
