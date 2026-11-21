#!/bin/bash
# D158 handover. Waits until D158 is in research/policy_design_log.md on origin (the user's rulings, relayed by flash),
# then sets STOP; driver v9 exits at the next run boundary and driver v10 starts (warm-ahead arms wait for the race fix
# or 23:00; EP-G non-piece cells meanwhile).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
until git fetch -q 2>/dev/null; git show origin/main:research/policy_design_log.md | grep -q "^| D158 "; do sleep 60; done
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (D158, in the design log): STOP set; after the current cell the driver hands over to v10" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v10.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v10 started" >> $LOG
