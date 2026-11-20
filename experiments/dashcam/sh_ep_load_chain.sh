#!/bin/bash
# User ruling 2026-11-20: run the StudySH-EP cost-under-load step AFTER the post-fix redo and BEFORE the sweep resumes.
# Touches STOP as soon as the last redo cell starts (the driver then exits at that cell's end, before the first sweep
# cell), runs the load step with GPU 2 idle, then removes STOP and restarts the frozen-grid driver (v6) for the sweep.
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
until grep -q "start hybrid-F-lhreq_n16_s6_1200s_h27_3t_postfix " $LOG; do sleep 20; done
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (user ruling): STOP set; after the last post-fix redo cell the StudySH-EP cost-under-load step runs (three-type background at 16 devices), then the sweep resumes" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 15; done
while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 5; done
bash experiments/dashcam/sh_ep_load_h100.sh
rm -f $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR: StudySH-EP cost-under-load step done; the sweep resumes from edf-piece1024" >> $LOG
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v6.sh"
