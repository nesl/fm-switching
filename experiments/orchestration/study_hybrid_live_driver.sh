#!/bin/bash
# hybrid-live (D138 P1): live screening of the H100 hybrid. PILOT SCREENING, NOT A ROUND-1 RESULT.
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
RAW=$HOME/data/live2/hybrid_live
OUT=results/orchestration/live2/hybrid/live_runs
LOG=results/orchestration/live2/hybrid/hybrid_live.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
mkdir -p $RAW/runs $RAW/work $OUT
START_ITEM=${START_ITEM:-1}
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
diskfree_gb() { df -BG --output=avail $HOME | tail -1 | tr -dc 0-9; }
safe_pull() {
  local target=$1
  git add $(ls -d $LOG $OUT results/orchestration/live2/pilot/pilot_monitor.jsonl results/orchestration/live2/pilot/hybrid_live_summary.json 2>/dev/null)
  git commit -q -m "StudyLIVE2-pilot overnight logs before pulling $target (pilot, not a round-1 result)" 2>/dev/null
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "pull note: $rb"
  git push -q 2>/dev/null
  if git merge-base --is-ancestor $target HEAD 2>/dev/null; then log "pulled: $target is in HEAD $(git rev-parse --short HEAD)"; return 0; fi
  log "PULL FAILED: $target is NOT in HEAD $(git rev-parse --short HEAD): nothing run for it"; return 1
}
release_check() { d134_watch; return 0; }
cell() {
  local arm=$1 n=$2 seed=$3 host=$4 tag=$5; shift 5
  local name=${arm}_n${n}_s${seed}_600s_h${host%.*}${tag}
  local d=$RAW/runs/$name
  if [ -f $OUT/$name/cell.json ]; then     # any finished run (valid or not) is reused, never repeated
    log "skip $name: already run"; jq -c --arg name "$name" '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms, scored:.score.ok, dash:.score.score.sweep[0].dashcam_all_meet, rob_elig:.score.score.sweep[0].robot_pool_eligible, rob_meets:.score.score.sweep[0].robot_pool_meets} + {name:$name} | . + {valid:((.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0)), pass:((.dash==true) and ((.rob_elig!=true) or (.rob_meets==true)))}' $OUT/$name/cell.json; return; fi
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
  : 
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
  $PY experiments/orchestration/live2/pilot_tools/pilot_summary.py $OUT $RAW results/orchestration/live2/pilot/hybrid_live_summary.json >> $LOG 2>&1
  git add $(ls -d $OUT $LOG results/orchestration/live2/pilot/hybrid_live_summary.json results/orchestration/live2/pilot/pilot_monitor.jsonl \
    experiments/orchestration/study_hybrid_live_driver.sh experiments/orchestration/live2/hybrid 2>/dev/null)
  git commit -q -m "hybrid-live: $1 (pilot screening, not a round-1 result)" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1); [ -n "$ps" ] && log "PUSH NOT DONE (retry at the next item): $ps"
  log "ITEM DONE: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
# ===== hybrid-live screening (D138 P1) =====
SS1_FLAG=$OUT/STUDYSS1_FOUND
d134_watch() {   # here: watch for the StudySS1 kit (P2); flag it for the operator, never run it blind
  git fetch -q 2>/dev/null
  local h=$(git log origin/main --format="%h %s" -200 | grep -E "^[0-9a-f]+ StudySS1" | head -1)
  if [ -n "$h" ] && ! grep -q "^${h%% *}" $SS1_FLAG 2>/dev/null; then echo "$h" >> $SS1_FLAG; log "P2: StudySS1 commit found: $h (operator slots it between screening runs)"; fi
}
mkdir -p $OUT
until grep -q "ACC2 RUN EXIT" results/sember/study_acc2/acc2_run.log; do sleep 2; done
while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
log "hybrid-live driver start: screening (decision 14 grid), HEAD $(git rev-parse --short HEAD)"
score() {   # rank key for a config across 10 and 12: dashcams all meet at both, then robot on-time sum
  local cfg=$1 seed=$2 dm=0 ro=0
  for n in 10 12; do f=$OUT/${cfg}_n${n}_s${seed}_600s_h27/cell.json; [ -f $f ] || continue
    [ "$(jq -r '.score.score.sweep[0].dashcam_all_meet' $f)" = "true" ] && dm=$((dm+1))
    ro=$((ro + $(jq -r '.score.score.sweep[0].robot_pool_on_time // 0' $f))); done
  echo "$dm $ro"
}
for cfg in hybrid-base hybrid-c5 hybrid-c1c5 hybrid-c1c2k1c5 hybrid-c1c2k2c5; do
  for n in 10 12; do d134_watch; cellv $cfg $n 0 27 "" >/dev/null; item_done "$cfg at $n devices, seed 0"; done
done
K1=$(score hybrid-c1c2k1c5 0); K2=$(score hybrid-c1c2k2c5 0)
BEST_ALL=hybrid-all-k1; [ "$(printf '%s\n%s\n' "$K2 k2" "$K1 k1" | sort -k1,1nr -k2,2nr | head -1 | awk '{print $3}')" = "k2" ] && BEST_ALL=hybrid-all-k2
log "C3 on the better k_r: $BEST_ALL (k1: $K1; k2: $K2)"
for n in 10 12; do d134_watch; cellv $BEST_ALL $n 0 27 "" >/dev/null; item_done "$BEST_ALL at $n devices, seed 0"; done
TOP=$(for cfg in hybrid-base hybrid-c5 hybrid-c1c5 hybrid-c1c2k1c5 hybrid-c1c2k2c5 $BEST_ALL; do echo "$(score $cfg 0) $cfg"; done | sort -k1,1nr -k2,2nr | head -2 | awk '{print $3}' | tr '\n' ' ')
log "best two on seed 0: $TOP"
for cfg in $TOP; do for n in 10 12; do d134_watch; cellv $cfg $n 4 27 _devseed4 >/dev/null; item_done "$cfg at $n devices, development seed 4"; done; done
log "HYBRID SCREENING DONE; handing GPU 2 to the D134 baseline queue (P3)"
echo SCREENING_DONE > $OUT/STATUS
echo "[$(date '+%F %T')] RESUME (operator, auto): D134 queue resumed after hybrid screening" >> results/orchestration/live2/pilot/pilot5.log
exec bash experiments/orchestration/study_live2_pilot5b_driver.sh
