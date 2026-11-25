#!/bin/bash
# v37 (2026-11-24): an automatic rerun's server-flag lookup strips trailing _rerun tokens (before v37 a kv0.5r rerun got
# no flags; v36's pre-launch assertion refused it and the policy ablation covex-v6-fair-final-stateoff kv0.5r s4 was
# skipped after a torn-tree INVALID). STOP now; driver v36 finishes the current cell and exits; the two SKIPPED entries
# that v36's defect wrote for that cell are removed (it then reruns as _rerun under v37); driver v37 starts. The
# watchdog's DRIVER line points at v37 from the same commit.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (v37): STOP set; after the current cell the driver hands over to v37" >> $LOG
while tmux has-session -t =frozengrid 2>/dev/null; do sleep 10; done
for n in covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30 covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_rerun; do
  sed -i "/^${n}\$/d" $OUT/SKIPPED; [ -f $OUT/SKIPPED_ARGS ] && sed -i "/^${n}\$/d" $OUT/SKIPPED_ARGS; done
echo "[$(date '+%F %T')] OPERATOR (v37): removed the v36-defect SKIPPED entries for covex-v6-fair-final-stateoff kv0.5r s4 (it reruns as _rerun)" >> $LOG
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v37.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v37 started" >> $LOG
