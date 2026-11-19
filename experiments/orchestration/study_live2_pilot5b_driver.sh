#!/bin/bash
# StudyLIVE2-pilot D134: every ported published arm live (2026-11-19). PILOT, NOT A ROUND-1 RESULT.
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
RAW=$HOME/data/live2/pilot5
OUT=results/orchestration/live2/pilot/runs5
LOG=results/orchestration/live2/pilot/pilot5.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
mkdir -p $RAW/runs $RAW/work $OUT
START_ITEM=${START_ITEM:-1}
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
diskfree_gb() { df -BG --output=avail $HOME | tail -1 | tr -dc 0-9; }
safe_pull() {
  local target=$1
  git add $(ls -d $LOG $OUT results/orchestration/live2/pilot/pilot_monitor.jsonl results/orchestration/live2/pilot/pilot5_summary.json 2>/dev/null)
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
  $PY experiments/orchestration/live2/pilot_tools/pilot_summary.py $OUT $RAW results/orchestration/live2/pilot/pilot5_summary.json >> $LOG 2>&1
  git add $(ls -d $OUT $LOG results/orchestration/live2/pilot/pilot5_summary.json results/orchestration/live2/pilot/pilot_monitor.jsonl \
    experiments/orchestration/study_live2_pilot5_driver.sh experiments/orchestration/study_live2_pilot5b_driver.sh 2>/dev/null)
  git commit -q -m "StudyLIVE2-pilot D134 published arms: $1 (pilot, not a round-1 result)" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1); [ -n "$ps" ] && log "PUSH NOT DONE (retry at the next item): $ps"
  log "ITEM DONE: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
# ===== D134 (user prompt 2026-11-19 morning) =====
PUB_HANDLED=$OUT/PUBLISHED_HANDLED          # "baselines-published ready:" commits already handled, by hash
PLACE_FLAG=$OUT/PLACEMENT_FOUND              # written when a "placement" commit says placement is enacted
DONE_ARMS=$OUT/ARMS_DONE
[ -f $PUB_HANDLED ] || echo "ae50743 (the first published commit; its arms are item 1 or already run)" > $PUB_HANDLED
registered() { $PY -c "import sys; sys.path.insert(0,'experiments/orchestration/live2'); import arms as A; A.make_arm('$1')" >/dev/null 2>&1; }
# one arm: 120 s validity at 8, then 8, 10, 12, 14; 16 only if it passes 14; commit after the arm
run_arm() {
  local a=$1 tag=${2:-}
  grep -qx "$a$tag" $DONE_ARMS 2>/dev/null && { log "arm $a$tag already done"; return; }
  if ! registered $a; then log "arm $a is not registered in the code: skipped"; echo "$a$tag" >> $DONE_ARMS; return; fi
  local v=$(cell $a 8 0 27 _validity120$tag --run-s 120)
  log "validity $a$tag: $(echo "$v" | jq -c '{valid, err, n_errors, lat_p99}')"
  if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
    v=$(cell $a 8 0 27 _validity120${tag}_rerun --run-s 120)
    [ "$(echo "$v" | jq -r .valid)" != "true" ] && { log "$a$tag failed its validity cell twice: arm skipped"; echo "$a$tag" >> $DONE_ARMS; item_done "$a$tag: validity failed twice, not run"; return; }
  fi
  local last=""
  for n in 8 10 12 14; do d134_watch; v=$(cellv $a $n 0 27 "$tag"); last=$(echo "$v" | jq -r 'if .skipped then "skip" elif .pass then "pass" else "fail" end'); done
  [ "$last" = "pass" ] && cellv $a 16 0 27 "$tag" >/dev/null
  echo "$a$tag" >> $DONE_ARMS
  item_done "$a$tag at 8, 10, 12, 14 (16 only if it passed 14)"
}
d134_watch() {
  git fetch -q 2>/dev/null
  # (3) placement enacted: pause for the operator to apply the H100 wiring with its test
  local pl=$(git log origin/main --format="%h %s" -120 | grep -E "^[0-9a-f]+ placement" | while read hh rest; do
      git log -1 --format=%B $hh | grep -qi "enact" && { grep -q "^$hh" $PLACE_FLAG 2>/dev/null || { echo "$hh $rest"; break; }; }; done)
  if [ -n "$pl" ]; then echo "$pl" >> $PLACE_FLAG; log "PLACEMENT commit found: $pl; queue paused for the operator (H100 wiring + test)"; exit 0; fi
  # (2) new published arms: run them first, as they land
  local pub=$(git log origin/main --format="%h %s" -200 | grep -E "^[0-9a-f]+ baselines-published ready:" | while read hh rest; do
      grep -q "^$hh" $PUB_HANDLED || { echo "$hh $rest"; break; }; done)
  if [ -n "$pub" ]; then
    local hh=${pub%% *}
    echo "$pub" >> $PUB_HANDLED
    log "NEW published commit: $pub"
    safe_pull $hh || { item_done "published commit $hh: pull failed, nothing run"; return; }
    local names=$(git log -1 --format=%s $hh | sed 's/^baselines-published ready://' | tr ',;()' '    ' | tr ' ' '\n' | grep -E '^[A-Za-z0-9][A-Za-z0-9_.-]*$' | sort -u)
    local arms=""; for a in $names; do registered $a && arms="$arms $a"; done
    log "published commit $hh: registered arms:${arms:- none} (named: $(echo $names | tr '\n' ' '))"
    for a in $arms; do run_arm $a; done
  fi
}
log "pilot5b driver start (D134): watchers in the main shell, robust pre-pull add"
# (3) operator-applied placement: the five memory arms at 10 and 12, labelled with-placement
if [ -f $OUT/PLACEMENT_APPLIED ] && ! grep -qx placement-reruns $DONE_ARMS 2>/dev/null; then
  for a in mooncake kvflow lmcache pensieve attentionstore; do for n in 10 12; do cellv $a $n 0 27 _with-placement >/dev/null; done; done
  echo placement-reruns >> $DONE_ARMS; item_done "with placement: mooncake, kvflow, lmcache, pensieve, attentionstore at 10 and 12"
fi
# (1) the ported published arms not yet run live (new ones are run first by the watcher before every cell)
for a in hybrid-llm routellm perllm r3-streaming videostorm inar-vl uniscale preble kvflow lmcache pensieve mooncake; do
  d134_watch; run_arm $a
done
# (4) b9 and utility-per-cost at 8, 10, 12, 14
for a in b9 utility-per-cost; do
  grep -qx "$a" $DONE_ARMS 2>/dev/null && continue
  for n in 8 10 12 14; do d134_watch; cellv $a $n 0 27 "" >/dev/null; done; echo "$a" >> $DONE_ARMS; item_done "$a at 8, 10, 12, 14"
done
log "D134 QUEUE DONE"; echo D134_DONE > $OUT/STATUS
