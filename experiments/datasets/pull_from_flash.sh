#!/usr/bin/env bash
# Pull dataset paths from flash's read-only share (fmnet-flash, root /mnt/ssd/hf_models/datasets) with ~/.local/bin/fmpull.
# Usage: pull_from_flash.sh <list file>   — each line: "<dataset> <relative path under the dataset>"
# Destination: /home/pragya/data/datasets/<dataset>/<parent of path>/ (flash's layout kept). One path at a time, in list
# order; fmpull resumes (--partial --append-verify) and never deletes. Low CPU / IO priority. Before each path: stop if
# ~/.fmnet_latency_active exists (StudyD7b running) or if free space after this path would fall below the ${FLOOR_GB:-20} GB floor.
# Every call and its exit code are logged to logs/datasets_pull.log.
cd /home/pragya/Desktop/fm-switching
LOG=logs/datasets_pull.log; LIST=$1; FLOOR=$(( ${FLOOR_GB:-20} * 1024 * 1024 * 1024 ))  # user lowered the floor from 130 GB to 20 GB (2026-11-05)
while read -r ds rel; do
  [ -z "$ds" ] || [ "${ds:0:1}" = "#" ] && continue
  if [ -e ~/.fmnet_latency_active ]; then echo "$(date '+%F %T') HOLD: latency marker present — stopping before $ds/$rel" | tee -a $LOG; exit 3; fi
  need=$(rsync --list-only -r "fmnet-flash:$ds/$rel" 2>/dev/null | awk '$1 !~ /^d/ {gsub(",","",$2); s+=$2} END {print s+0}')
  have=$(du -sb "/home/pragya/data/datasets/$ds/$rel" 2>/dev/null | cut -f1); have=${have:-0}
  free=$(df -B1 --output=avail /home/pragya/data | tail -1)
  if [ $((free - (need - have))) -lt $FLOOR ]; then echo "$(date '+%F %T') STOP: $ds/$rel needs $((need - have)) B more; free $free B; would fall below the ${FLOOR_GB:-20} GB floor" | tee -a $LOG; exit 4; fi
  parent=$(dirname "$rel"); dest=/home/pragya/data/datasets/$ds/; [ "$parent" != "." ] && dest=$dest$parent/
  echo "$(date '+%F %T') PULL $ds/$rel ($need B) -> $dest" | tee -a $LOG
  nice -n 19 ionice -c3 ~/.local/bin/fmpull fmnet-flash "$ds/$rel" "$dest" >> logs/datasets_pull_rsync.log 2>&1; rc=$?
  echo "$(date '+%F %T') END rc=$rc $ds/$rel" | tee -a $LOG
  [ $rc -ne 0 ] && exit $rc
done < "$LIST"
echo "$(date '+%F %T') LIST DONE $LIST" | tee -a $LOG
