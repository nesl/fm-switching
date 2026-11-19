#!/bin/bash
# StudyLIVE2-pilot (D95, D97, D101, D104, D111, D114, D115, D116), unattended overnight run, 2026-11-18.
# PILOT, NEVER A ROUND-1 RESULT. Server restarted before every run (run_live2_real.py --start-server); the preflight
# every-ref check runs inside the runner before the server starts. HF token read from file, never printed.
# User rulings on the up-front defaults (2026-11-18): Step 1 failures of utility-per-cost, b9 or edf-piece2048 are
# recorded but do not stop the pilot; policy-core and edf run at EVERY base size 4..64; above 64 each arm doubles on
# its own while it passes (ceiling 128); each arm's break is its own first failing size.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
PY=~/.venvs/fm-switching-vllm/bin/python
RAW=$HOME/data/live2/pilot3
OUT=results/orchestration/live2/pilot/runs3
LOG=results/orchestration/live2/pilot/pilot3.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
CINFLIGHT_FLAG="${CINFLIGHT_FLAG:-}"      # set from flash's D114 commit; empty = the C_inflight 8 cell is skipped
mkdir -p $RAW/runs $RAW/work $OUT
COMMON="--seed 0 --ratio 50:50 --mode A --calibration $CAL --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
 --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
 --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server"
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
diskfree_gb() { df -BG --output=avail $HOME | tail -1 | tr -dc 0-9; }

# cell ARM N RUN_S HOST_GIB TAG [extra flags...] -> prints a one-line JSON verdict
cell() {
  local arm=$1 n=$2 rs=$3 host=$4 tag=$5; shift 5
  local name=${arm}_n${n}_${rs%.*}s_h${host%.*}${tag}
  local d=$RAW/runs/$name
  if [ "$(diskfree_gb)" -lt 50 ]; then log "DISK below 50 GB: not launching $name"; echo '{"skipped":"disk"}'; return; fi
  log "start $name HEAD $(git rev-parse --short HEAD)"
  local extra=""
  [ "$arm" = "device-only" ] && extra="--no-score"
  if [ "$arm" = "device-only" ]; then
    $PY experiments/orchestration/live2/run_live2_real.py --arm device-only --n-devices $n --run-s $rs \
      --host-tier-gib $host --seed 0 --ratio 50:50 --mode A --calibration $CAL --decision-period-s 0.1 \
      --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
      --work $RAW/work --server-kind none --label "PILOT_NOT_A_ROUND1_RESULT $name" --out $d "$@" > $d.stdout 2>&1
  else
    $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $rs --host-tier-gib $host \
      $COMMON --label "PILOT_NOT_A_ROUND1_RESULT $name" --out $d "$@" > $d.stdout 2>&1
  fi
  local rc=$?
  # publish: copy the run directory, gzip anything over 5 MB
  rm -rf $OUT/$name.tmp; cp -r $d $OUT/$name.tmp 2>/dev/null && rm -rf $OUT/$name && mv $OUT/$name.tmp $OUT/$name
  cp $d.stdout $OUT/$name.stdout 2>/dev/null
  find $OUT/$name -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
  local v=$(jq -c '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms,
     scored:.score.ok, score_err:.score.error,
     dash:.score.score.sweep[0].dashcam_all_meet, rob_elig:.score.score.sweep[0].robot_pool_eligible,
     rob_meets:.score.score.sweep[0].robot_pool_meets, cap:.score.score.sweep[0].capacity_met}' $d/cell.json 2>/dev/null)
  [ -z "$v" ] && v='{"err":"no cell.json","run_valid":false}'
  v=$(echo "$v" | jq -c --arg name "$name" --argjson rc $rc '. + {name:$name, rc:$rc,
     valid:((.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0)),
     pass:((.dash==true) and ((.rob_elig!=true) or (.rob_meets==true))),
     robot_measurable:(.rob_elig==true)}')
  log "end $name $v"
  echo "$v"
}
# cellv: run, rerun once if INVALID; returns the verdict of the last attempt, with "skipped" if INVALID twice
cellv() {
  local v=$(cell "$@")
  if [ "$(echo "$v" | jq -r .valid)" != "true" ] && [ "$(echo "$v" | jq -r '.arm // empty')" != "device-only" ]; then
    log "INVALID, rerun once: $(echo "$v" | jq -c '{name, err, run_valid, lat_p99, n_errors, digests_equal}')"
    local a=$1 n=$2 rs=$3 h=$4 t=$5; shift 5
    v=$(cell $a $n $rs $h "${t}_rerun" "$@")
    if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
      log "INVALID TWICE: cell skipped and recorded"
      v=$(echo "$v" | jq -c '. + {skipped:"invalid twice"}')
    fi
  fi
  echo "$v"
}
commit_stage() {
  # the pilot's exclusivity-monitor log is appended by every server start; it is committed with the pilot so the
  # working tree is clean and the rebase of unpushed commits can run (D116: no stash, reset or force-push)
  git add $OUT $LOG experiments/orchestration/study_live2_pilot3_driver.sh \
    results/orchestration/live2/pilot/pilot_monitor.jsonl 2>/dev/null
  git commit -q -m "$1" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2)
  [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1)
  [ -n "$ps" ] && log "PUSH NOT DONE (will retry at the next stage): $ps"
  log "commit: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
STOPF=$OUT/STATUS

# ================= D123 (user ruling 2026-11-18 ~18:45): policy-core v1.0 is superseded (D122); only
# policy-independent cells tonight, in this order. edf's remaining BASE sizes (32, 64) run under the earlier ruling
# (both arms at every base size); per-arm doubling above 64 only while the arm passes. edf's break so far: 8.
log "D123 start (pilot3b driver)"
declare -A PASS
PASS[edf:4]=pass; PASS[edf:8]=fail; PASS[edf:16]=fail
# 1. edf's remaining ladder
for n in 32 64; do
  v=$(cellv edf $n 600 27 "")
  PASS[edf:$n]=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end')
  log "ladder edf n=$n: ${PASS[edf:$n]} (robot measurable: $(echo "$v" | jq -r .robot_measurable))"
done
if [ "${PASS[edf:64]}" = "pass" ]; then v=$(cellv edf 128 600 27 ""); PASS[edf:128]=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end'); log "ladder edf n=128: ${PASS[edf:128]}"; fi
EB=8; for n in 4 8 16 32 64 128; do [ "${PASS[edf:$n]}" = "fail" ] && { EB=$n; break; }; done
log "BREAK edf: first failing size $EB"
commit_stage "StudyLIVE2-pilot: edf ladder complete, first failing size $EB (pilot, not a round-1 result)"
# 2. always-cloud FCFS up to and including edf's break
for n in 4 8 16 32 64 128; do [ $n -gt $EB ] && break; cellv always-cloud-fcfs $n 600 27 "" > /dev/null; done
# 3. D114 sensitivity: edf at C_inflight = 8 at edf's break
cellv edf $EB 600 27 _cinflight8 --c-inflight 8 > /dev/null
commit_stage "StudyLIVE2-pilot: always-cloud-fcfs up to edf's break and edf at C_inflight 8 (pilot, not a round-1 result)"
# 4. llf ladder: INFORMATIVE, NOT PART OF D95
for n in 4 8 16 32 64; do
  v=$(cellv llf $n 600 27 _informative)
  PASS[llf:$n]=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end')
  log "ladder llf (informative, not part of D95) n=$n: ${PASS[llf:$n]}"
done
if [ "${PASS[llf:64]}" = "pass" ]; then cellv llf 128 600 27 _informative > /dev/null; fi
commit_stage "StudyLIVE2-pilot: llf ladder, informative and not part of D95 (pilot, not a round-1 result)"
# 5. vllm-priority smoke cell: 8 devices, 120 s, server in priority mode; VALIDITY ONLY
v=$(cell vllm-priority 8 120 27 _priority_smoke --scheduling-policy priority)
log "vllm-priority smoke (validity only): $v"
echo D123_RUNS_DONE > $STOPF
commit_stage "StudyLIVE2-pilot: vllm-priority 120 s smoke cell with the server in priority mode, validity only (pilot, not a round-1 result)"
log "D123 RUNS DONE"
