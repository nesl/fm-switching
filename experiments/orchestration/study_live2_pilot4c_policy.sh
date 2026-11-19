#!/bin/bash
# StudyLIVE2-pilot, overnight baseline ladders (D127-D129) + D130 published baselines and tuned-engine; replaces pilot4 driver mid-run (skips runs already done), 2026-11-18/19. PILOT, NOT A ROUND-1 RESULT.
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
  # PRIORITY 0 fires only for a release NEWER than the one already handled (POLICY_RELEASE_HANDLED)
  [ -n "$h" ] && [ "$h" = "$(cat $OUT/POLICY_RELEASE_HANDLED 2>/dev/null)" ] && h=""
  if [ -n "$h" ]; then log "PRIORITY 0: release found: $h; queue paused after the current run"; echo "$h" > $OUT/POLICY_RELEASE; exit 0; fi
}
# cell ARM N SEED HOST TAG [extra flags]
cell() {
  local arm=$1 n=$2 seed=$3 host=$4 tag=$5; shift 5
  local name=${arm}_n${n}_s${seed}_600s_h${host%.*}${tag}
  local d=$RAW/runs/$name
  if [ -f $OUT/$name/cell.json ] && [ "$(jq -r '(.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0)' $OUT/$name/cell.json)" = "true" ]; then
    log "skip $name: already done and valid"; jq -c --arg name "$name" '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms, scored:.score.ok, dash:.score.score.sweep[0].dashcam_all_meet, rob_elig:.score.score.sweep[0].robot_pool_eligible, rob_meets:.score.score.sweep[0].robot_pool_meets} + {name:$name, valid:true} | . + {pass:((.dash==true) and ((.rob_elig!=true) or (.rob_meets==true)))}' $OUT/$name/cell.json; return; fi
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
    experiments/orchestration/study_live2_pilot4_driver.sh experiments/orchestration/study_live2_pilot4b_driver.sh 2>/dev/null
  git commit -q -m "StudyLIVE2-pilot overnight baselines: $1 (pilot, not a round-1 result)" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1); [ -n "$ps" ] && log "PUSH NOT DONE (retry at the next item): $ps"
  log "ITEM DONE: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
# ===== PRIORITY 0 (D127-D129): the v1.3-fast release, then back to the baseline queue =====
POLICY_ARM=covex-v13
REL=$(git log origin/main --format="%h %s" -80 | grep -m1 " v1.3-fast release")
echo "$REL" > $OUT/POLICY_RELEASE_HANDLED
log "PRIORITY 0 start: $REL (arm $POLICY_ARM), HEAD $(git rev-parse --short HEAD)"
# bench_d119 on this host's CPU, server down (no server is up between runs)
BOUT=results/orchestration/live2/coord/perf/bench_d119_h100host_v13.json
log "bench_d119 start (server down)"
$PY experiments/orchestration/policy/bench_d119.py --sizes 32,64,128 --out $BOUT >> $LOG 2>&1
log "bench_d119 done: rc=$? -> $BOUT"
item_done "PRIORITY 0: bench_d119 on the H100 host CPU, v1.3-fast build"
# the released policy at 4, 8, 16, 32; doubling while it passes, ceiling 64
LAST=fail
for n in 4 8 16 32; do
  v=$(cellv $POLICY_ARM $n 0 27 _release)
  LAST=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end')
  log "release ladder $POLICY_ARM n=$n: $LAST (robot $(echo "$v" | jq -r '.rob_on')/$(echo "$v" | jq -r '.rob_n'))"
done
[ "$LAST" = "pass" ] && cellv $POLICY_ARM 64 0 27 _release >/dev/null
item_done "PRIORITY 0: $POLICY_ARM (v1.3-fast) at 4, 8, 16, 32 devices"
log "PRIORITY 0 done: resuming the baseline queue"
exec bash experiments/orchestration/study_live2_pilot4b_driver.sh
