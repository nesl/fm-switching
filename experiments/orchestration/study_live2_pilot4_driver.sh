#!/bin/bash
# StudyLIVE2-pilot, overnight baseline ladders (D127-D129), 2026-11-18/19. PILOT, NOT A ROUND-1 RESULT.
# Seed 0 (item 9: development seed 4), 600 s, 50:50, push-all, uniform links, 27 GiB unless noted; server restarted
# before every run; preflight every-ref check inside the runner; scored after the server stops; D115 logging.
# D128: "edf" means C_inflight 8 (passed as --c-inflight 8; the code default is still 4). llf and edf-piece* run at
# their committed default (4), labelled in the header. Between runs: if a commit starting "v1.3-fast release" is on
# origin, the driver writes POLICY_RELEASE and exits after the current run so the operator handles PRIORITY 0.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
PY=~/.venvs/fm-switching-vllm/bin/python
RAW=$HOME/data/live2/pilot4
OUT=results/orchestration/live2/pilot/runs4
LOG=results/orchestration/live2/pilot/pilot4.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
mkdir -p $RAW/runs $RAW/work $OUT
START_ITEM=${START_ITEM:-1}
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
diskfree_gb() { df -BG --output=avail $HOME | tail -1 | tr -dc 0-9; }
release_check() {
  git fetch -q 2>/dev/null
  local h=$(git log origin/main --format="%h %s" -80 | grep -m1 " v1.3-fast release")
  if [ -n "$h" ]; then log "PRIORITY 0: release found: $h; queue paused after the current run"; echo "$h" > $OUT/POLICY_RELEASE; exit 0; fi
}
# cell ARM N SEED HOST TAG [extra flags]
cell() {
  local arm=$1 n=$2 seed=$3 host=$4 tag=$5; shift 5
  local name=${arm}_n${n}_s${seed}_600s_h${host%.*}${tag}
  local d=$RAW/runs/$name
  if [ "$(diskfree_gb)" -lt 50 ]; then log "DISK below 50 GB: not launching $name"; echo '{"skipped":"disk","valid":false}'; return; fi
  log "start $name HEAD $(git rev-parse --short HEAD)"
  $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s 600 --host-tier-gib $host \
    --seed $seed --ratio 50:50 --mode A --calibration $CAL --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server \
    --label "PILOT_NOT_A_ROUND1_RESULT $name" --out $d "$@" > $d.stdout 2>&1
  local rc=$?
  rm -rf $OUT/$name; cp -r $d $OUT/$name 2>/dev/null; cp $d.stdout $OUT/$name.stdout 2>/dev/null
  find $OUT/$name -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
  local v=$(jq -c '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms, scored:.score.ok,
     dash:.score.score.sweep[0].dashcam_all_meet, rob_elig:.score.score.sweep[0].robot_pool_eligible,
     rob_meets:.score.score.sweep[0].robot_pool_meets, rob_on:.score.score.sweep[0].robot_pool_on_time,
     rob_n:.score.score.sweep[0].robot_pool_n}' $d/cell.json 2>/dev/null)
  [ -z "$v" ] && v='{"err":"no cell.json","run_valid":false}'
  v=$(echo "$v" | jq -c --arg name "$name" --argjson rc $rc '. + {name:$name, rc:$rc,
     valid:((.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0)),
     pass:((.dash==true) and ((.rob_elig!=true) or (.rob_meets==true)))}')
  log "end $name $v"
  echo "$v"
}
cellv() {
  release_check
  local v=$(cell "$@")
  if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
    log "INVALID, rerun once: $(echo "$v" | jq -c '{name, err, run_valid, lat_p99, n_errors, digests_equal}')"
    local a=$1 n=$2 s=$3 h=$4 t=$5; shift 5
    v=$(cell $a $n $s $h "${t}_rerun" "$@")
    [ "$(echo "$v" | jq -r .valid)" != "true" ] && { log "INVALID TWICE: cell skipped and recorded"; v=$(echo "$v" | jq -c '. + {skipped:"invalid twice"}'); }
  fi
  echo "$v"
}
item_done() {   # summarise (server down), commit, push
  $PY experiments/orchestration/live2/pilot_tools/pilot_summary.py $OUT $RAW results/orchestration/live2/pilot/pilot4_summary.json >> $LOG 2>&1
  git add $OUT $LOG results/orchestration/live2/pilot/pilot4_summary.json results/orchestration/live2/pilot/pilot_monitor.jsonl \
    experiments/orchestration/study_live2_pilot4_driver.sh 2>/dev/null
  git commit -q -m "StudyLIVE2-pilot overnight baselines: $1 (pilot, not a round-1 result)" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1); [ -n "$ps" ] && log "PUSH NOT DONE (retry at the next item): $ps"
  log "ITEM DONE: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
C8="--c-inflight 8"
# decision 1 (up-front): llf and edf-piece* C_inflight, read at RUN time so a ruling can change it without editing
# this running script: the file holds e.g. "--c-inflight 8"; empty or absent = the committed default (4)
LLFC=results/orchestration/live2/pilot/pilot4_llf_piece_flags.txt
lf() { cat $LLFC 2>/dev/null; }
lt() { [ -n "$(lf)" ] && echo _c8 || echo _c4; }
log "pilot4 driver start (START_ITEM=$START_ITEM)"
if [ $START_ITEM -le 1 ]; then for n in 4 16 32 64; do cellv edf $n 0 27 _c8 $C8 >/dev/null; done; item_done "item 1, edf C_inflight 8 at 4, 16, 32, 64"; fi
if [ $START_ITEM -le 2 ]; then for n in 10 12 14; do
    cellv always-cloud-fcfs $n 0 27 "" >/dev/null; cellv edf $n 0 27 _c8 $C8 >/dev/null; cellv llf $n 0 27 $(lt) $(lf) >/dev/null
  done; item_done "item 2, the breaks between 8 and 16: always-cloud-fcfs, edf C8, llf C4 at 10, 12, 14"; fi
if [ $START_ITEM -le 3 ]; then for n in 4 8 16 32; do cellv b9 $n 0 27 "" >/dev/null; done; item_done "item 3, b9 at 4, 8, 16, 32"; fi
if [ $START_ITEM -le 4 ]; then for n in 4 8 16 32; do cellv utility-per-cost $n 0 27 "" >/dev/null; done; item_done "item 4, utility-per-cost at 4, 8, 16, 32"; fi
if [ $START_ITEM -le 5 ]; then for n in 16 32 64; do cellv always-cloud-fcfs $n 0 27 "" >/dev/null; done; item_done "item 5, always-cloud-fcfs at 16, 32, 64"; fi
if [ $START_ITEM -le 6 ]; then for n in 4 8 16 32; do cellv vllm-priority $n 0 27 _prio --scheduling-policy priority >/dev/null; done; item_done "item 6, vllm-priority in priority mode at 4, 8, 16, 32"; fi
if [ $START_ITEM -le 7 ]; then for a in edf-piece1024 edf-piece2048; do for n in 8 16; do cellv $a $n 0 27 $(lt) $(lf) >/dev/null; done; done; item_done "item 7, edf-piece1024 and edf-piece2048 (C4) at 8, 16"; fi
if [ $START_ITEM -le 8 ]; then for n in 8 16; do
    cellv always-cloud-fcfs $n 0 256 "" >/dev/null; cellv edf $n 0 256 _c8 $C8 >/dev/null; cellv llf $n 0 256 $(lt) $(lf) >/dev/null; cellv b9 $n 0 256 "" >/dev/null
  done; item_done "item 8, roomy 256 GiB: always-cloud-fcfs, edf C8, llf C4, b9 at 8, 16"; fi
if [ $START_ITEM -le 9 ]; then for n in 8 16; do cellv llf $n 4 27 $(lt)_devseed4 $(lf) >/dev/null; cellv edf $n 4 27 _c8_devseed4 $C8 >/dev/null; done; item_done "item 9, development seed 4: llf C4 and edf C8 at 8, 16"; fi
log "BASELINE QUEUE DONE"; echo BASELINES_DONE > $OUT/STATUS
