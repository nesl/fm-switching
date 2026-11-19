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

# ---------------- STEP 1 (D104): 8 devices, 120 s, every arm
log "STEP 1 start"
CRIT="policy-core edf always-cloud-fcfs edf-piece1024 device-only"
for arm in device-only edf policy-core always-cloud-fcfs edf-piece1024 edf-piece2048 utility-per-cost b9; do
  v=$(cell $arm 8 120 27 _step1)
  ok=true
  if [ "$arm" = "device-only" ]; then
    [ "$(echo "$v" | jq -r .err)" = "null" ] && [ "$(echo "$v" | jq -r .run_valid)" = "true" ] || ok=false
  else
    [ "$(echo "$v" | jq -r .valid)" = "true" ] && [ "$(echo "$v" | jq -r .scored)" = "true" ] || ok=false
    d=$RAW/runs/${arm}_n8_120s_h27_step1
    nbad=$(jq -s '[.[] | select(.cache_salt==null or (.mm_uuids|length)==0 or .cached_tokens==null or .cache_path==null)] | length' $d/request.jsonl 2>/dev/null)
    [ "${nbad:-1}" = "0" ] || ok=false
    log "step1 $arm request checks: requests missing cache_salt / mm uuids / cached_tokens / cache_path: ${nbad:-unreadable}"
  fi
  if [ "$ok" != "true" ]; then
    if echo " $CRIT " | grep -q " $arm "; then
      log "STEP 1 FAILED on $arm (a pilot arm): STOP"; echo "STEP1_FAILED $arm" > $STOPF
      commit_stage "StudyLIVE2-pilot stopped at Step 1: $arm failed the end-to-end check (pilot, not a round-1 result)"; exit 1
    else
      log "STEP 1 failure on $arm (not a pilot arm): recorded, pilot continues"
    fi
  fi
done
log "STEP 1 done"
commit_stage "StudyLIVE2-pilot Step 1 end-to-end check on the D114 build (pilot, not a round-1 result)"

# ---------------- STEP 2a: ladder (policy-core and edf at every base size, then per-arm doubling to 128)
declare -A PASS
for n in 4 8 16 32 64; do
  for arm in policy-core edf; do
    v=$(cellv $arm $n 600 27 "")
    PASS[$arm:$n]=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end')
    log "ladder $arm n=$n: ${PASS[$arm:$n]} (robot measurable: $(echo "$v" | jq -r .robot_measurable))"
  done
done
for arm in policy-core edf; do
  if [ "${PASS[$arm:64]}" = "pass" ]; then
    v=$(cellv $arm 128 600 27 "")
    PASS[$arm:128]=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end')
    log "ladder $arm n=128: ${PASS[$arm:128]}"
  fi
done
brk() { for n in 4 8 16 32 64 128; do [ "${PASS[$1:$n]}" = "fail" ] && { echo $n; return; }; done; echo none; }
lastpass() { local lp=none; for n in 4 8 16 32 64 128; do [ "${PASS[$1:$n]}" = "pass" ] && lp=$n; [ "${PASS[$1:$n]}" = "fail" ] && break; done; echo $lp; }
PB=$(brk policy-core); EB=$(brk edf); PL=$(lastpass policy-core)
log "BREAKS: policy-core first failing size $PB (last passing $PL); edf first failing size $EB"
echo "{\"policy_break\":\"$PB\",\"policy_last_pass\":\"$PL\",\"edf_break\":\"$EB\"}" > $OUT/BREAKS.json
commit_stage "StudyLIVE2-pilot ladder: policy-core break $PB, edf break $EB (pilot, not a round-1 result)"

# ---------------- STEP 2b: always-cloud FCFS up to and including edf's break
lim=$([ "$EB" = "none" ] && echo 128 || echo $EB)
for n in 4 8 16 32 64 128; do
  [ $n -gt $lim ] && break
  [ $n -eq 128 ] && [ -z "${PASS[edf:128]}" ] && break      # FCFS only at sizes edf itself ran
  cellv always-cloud-fcfs $n 600 27 "" > /dev/null
done
# ---------------- STEP 2c: edf + 1,024 pieces around and above the policy's break
if [ "$PB" = "none" ]; then SIZES="64 128"; else
  nxt=$((PB*2)); [ $nxt -gt 128 ] && nxt=""
  SIZES="$([ "$PL" != "none" ] && echo $PL) $PB $nxt"; fi
log "edf-piece1024 sizes: $SIZES"
for n in $SIZES; do cellv edf-piece1024 $n 600 27 "" > /dev/null; done
# ---------------- STEP 2d: roomy check (256 GiB), each arm at its own tight break
PBR=$([ "$PB" = "none" ] && echo 128 || echo $PB); EBR=$([ "$EB" = "none" ] && echo 128 || echo $EB)
cellv policy-core $PBR 600 256 "" > /dev/null
cellv edf $EBR 600 256 "" > /dev/null
# ---------------- STEP 2e: D114 sensitivity, edf at C_inflight = 8 at edf's break
if [ -n "$CINFLIGHT_FLAG" ]; then cellv edf $EBR 600 27 _cinflight8 $CINFLIGHT_FLAG > /dev/null
else log "C_inflight 8 cell SKIPPED: the D114 build exposes no setting for it (recorded, not added in arm code)"; fi
log "PILOT RUNS DONE"
echo PILOT_RUNS_DONE > $STOPF
commit_stage "StudyLIVE2-pilot runs complete: FCFS, edf-piece1024, roomy and sensitivity cells (pilot, not a round-1 result)"
