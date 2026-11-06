#!/usr/bin/env bash
# Extract OVO-Bench source videos into flash's layout: ovo_bench/src_videos/ <- cat hf/src_videos.tar.part* | tar -x
# (the tar's own top folder ./src_videos/ gives ovo_bench/src_videos/src_videos/..., as on flash). Archives kept;
# nothing deleted. Stops if ~/.fmnet_latency_active exists or free space would fall below FLOOR_GB (default 20).
set -u
cd /home/pragya/data/datasets/ovo_bench
LOG=/home/pragya/Desktop/fm-switching/logs/datasets_pull.log
[ -e ~/.fmnet_latency_active ] && { echo "$(date '+%F %T') HOLD: latency marker — OVO extraction not started" | tee -a $LOG; exit 3; }
need=$(cat hf/src_videos.tar.part* | wc -c); free=$(df -B1 --output=avail . | tail -1)
[ $((free - need)) -lt $(( ${FLOOR_GB:-20} * 1024 ** 3 )) ] && { echo "$(date '+%F %T') STOP: OVO extraction would fall below floor" | tee -a $LOG; exit 4; }
mkdir -p src_videos
echo "$(date '+%F %T') EXTRACT ovo_bench src_videos ($need B)" | tee -a $LOG
cat hf/src_videos.tar.part* | nice -n 19 ionice -c3 tar -x -C src_videos; rc=$?
echo "$(date '+%F %T') END rc=$rc EXTRACT ovo_bench ($(find src_videos -type f -name '*.mp4' | wc -l) mp4)" | tee -a $LOG
exit $rc
