#!/bin/bash
cd /home/pragya/Desktop/fm-switching
for c in "acc2_edf_n8 edf 8" "acc2_edf_n64 edf 64" "acc2_pc_n8 policy-core 8" "acc2_pc_n64 policy-core 64"; do
  echo "[$(date +%T)] start $c" >> logs/addendum_accept2.log
  bash experiments/orchestration/study_live2_harness_addendum_cell.sh $c
  echo "[$(date +%T)] end $c $(cat results/orchestration/live2/harness_addendum/${c%% *}/DONE)" >> logs/addendum_accept2.log
done
echo "[$(date +%T)] ALL DONE" >> logs/addendum_accept2.log
