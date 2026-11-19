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
# ===== v1.4 watchers (user ruling 2026-11-19 ~05:45). v1.3-fast (d944361) is NEVER run. =====
REL_HANDLED=$OUT/POLICY_RELEASE_V14_HANDLED
PIECE_HANDLED=$OUT/PIECE_FIX_V14_HANDLED
v14_suites() {   # all suites, server down; returns 0 only if every suite passes (environmental policy import excepted)
  local r=0 f=$OUT/v14_suites_$(date +%H%M).txt
  ( cd experiments/orchestration/live2/tests && for t in $(ls test_*.py | sed 's/\.py//'); do
      echo "== $t $(timeout 1500 $PY -m unittest $t 2>&1 | grep -E '^(Ran|OK|FAILED|FAIL:|ERROR:)' | tr '\n' ' ')"; done
    cd ../fleet/tests && echo "== fleet $(timeout 900 $PY test_live2_fleet.py 2>&1 | tail -1)"
    timeout 900 $PY test_scale.py >/dev/null 2>&1; echo "== test_scale exit $?"
    cd ../../../ && echo "== policy $(timeout 1800 $PY -m unittest discover -s policy/tests -t . 2>&1 | grep -E '^(Ran|OK|FAILED|ERROR:)' | tr '\n' ' ')" ) > $f 2>&1
  log "v1.4 suites: $(tr '\n' ' ' < $f | cut -c1-900)"
  grep -E "^== test_live2|^== fleet" $f | grep -qE "FAIL|ERROR" && r=1
  grep -q "^== fleet" $f && ! grep -q "^== fleet .*passed" $f && r=1
  return $r
}
v14_release() {
  local h=$1 hh=${1%% *}
  echo "$h" >> $REL_HANDLED
  log "PRIORITY 0 (v1.4): release found: $h"
  local note=$(git log -1 --format=%B $hh)
  echo "$note" > $OUT/v14_release_note_$hh.txt
  local prio=""; echo "$note" | grep -qiE -- "--scheduling-policy priority|scheduling.policy.{0,20}priority" && prio="--scheduling-policy priority"
  git pull --rebase -q 2>&1 | tail -1
  local arm=$(echo "$note" | grep -oE "covex-v1[0-9]+[a-z0-9-]*|policy-core-v1[0-9]+" | head -1); arm=${arm:-policy-core}
  $PY -c "import sys; sys.path.insert(0,'experiments/orchestration/live2'); import arms as A; A.make_arm('$arm')" >/dev/null 2>&1 || { log "v1.4: arm '$arm' from the note is not registered; using policy-core"; arm=policy-core; }
  log "v1.4: policy arm '$arm', server ${prio:-default fcfs}, HEAD $(git rev-parse --short HEAD)"
  if ! v14_suites; then log "v1.4: SUITES FAIL: no policy runs on $hh (reported); baselines continue"; item_done "v1.4 release $hh: suites fail, no policy runs"; return; fi
  log "bench_d119 start (server down)"
  $PY experiments/orchestration/policy/bench_d119.py --sizes 32,64,128 --out results/orchestration/live2/coord/perf/bench_d119_h100host_v14_$hh.json >> $LOG 2>&1
  log "bench_d119 done rc=$?"
  item_done "v1.4 release $hh: suites pass, bench_d119 on the H100 host"
  for seed in 0 4; do
    for n in 4 8 10 12 14 16 32; do cellv $arm $n $seed 27 _v14_$hh $prio >/dev/null; done
    item_done "v1.4 release $hh: $arm at 4, 8, 10, 12, 14, 16, 32 devices, seed $seed"
  done
}
v14_piecefix() {
  local h=$1 hh=${1%% *}
  echo "$h" >> $PIECE_HANDLED
  log "v1.4 piece-serialisation commit found: $h; rerunning edf-piece1024 / 2048 at 8 and 16"
  git pull --rebase -q 2>&1 | tail -1
  for a in edf-piece1024 edf-piece2048; do for n in 8 16; do cellv $a $n 0 27 _c8_piecefix_$hh --c-inflight 8 >/dev/null; done; done
  item_done "edf-piece1024 / 2048 at 8 and 16 after the v1.4 piece-serialisation fix $hh"
}
release_check() {
  git fetch -q 2>/dev/null
  local h=$(git log origin/main --format="%h %s" -120 | grep -E "^[0-9a-f]+ v1\.4-fast release" | while read hh rest; do
        grep -q "^$hh" $REL_HANDLED 2>/dev/null || { echo "$hh $rest"; break; }; done)
  [ -n "$h" ] && v14_release "$h"
  local p=$(git log origin/main --format="%h %s" -120 | grep -E "^[0-9a-f]+ v1\.4" | grep -iE "piece" | while read hh rest; do
        grep -q "^$hh" $PIECE_HANDLED 2>/dev/null || { echo "$hh $rest"; break; }; done)
  [ -n "$p" ] && v14_piecefix "$p"
  return 0
}
# cell ARM N SEED HOST TAG [extra flags]
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
    experiments/orchestration/study_live2_pilot4_driver.sh experiments/orchestration/study_live2_pilot4b_driver.sh experiments/orchestration/study_live2_pilot4d_driver.sh 2>/dev/null
  git commit -q -m "StudyLIVE2-pilot overnight baselines: $1 (pilot, not a round-1 result)" 2>&1 | tail -1
  local rb=$(git pull --rebase -q 2>&1 | tail -2); [ -n "$rb" ] && log "rebase note: $rb"
  local ps=$(git push -q 2>&1 | tail -1); [ -n "$ps" ] && log "PUSH NOT DONE (retry at the next item): $ps"
  log "ITEM DONE: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}
C8="--c-inflight 8"
LLFC=results/orchestration/live2/pilot/pilot4_llf_piece_flags.txt
lf() { cat $LLFC 2>/dev/null; }
lt() { [ -n "$(lf)" ] && echo _c8 || echo _c4; }
TUNED="--server-extra-flags=--long-prefill-token-threshold 1024"
SUM=results/orchestration/live2/pilot/pilot4_summary.json
# D130: break sizes found in item 2 (first failing size among 10, 12, 14 of always-cloud-fcfs, edf C8, llf)
item2_breaks() {
  for a in always-cloud-fcfs edf llf; do
    for n in 10 12 14; do
      v=$(jq -r --arg a $a --argjson n $n '[.rows[] | select(.arm==$a and .n==$n and .seed==0 and .host_gib==27 and .valid)] | first | if . == null then "none" elif .passes then "pass" else "fail" end' $SUM 2>/dev/null)
      [ "$v" = "fail" ] && { echo $n; break; }
    done
  done | sort -un | tr '\n' ' '
}
D130DONE=$OUT/D130_published_done
d130_published() {     # runs once, when a "baselines-published ready:" commit is on origin
  [ -f $D130DONE ] && return
  git fetch -q 2>/dev/null
  local subj=$(git log origin/main --format="%s" -80 | grep -m1 "^baselines-published ready:")
  if [ -z "$subj" ]; then log "D130: no 'baselines-published ready:' commit on origin yet"; return; fi
  git pull --rebase -q 2>&1 | tail -1
  local cand=$(echo "${subj#baselines-published ready:}" | tr ',;()' '    ' | tr ' ' '\n' | grep -E '^[a-z0-9][a-z0-9-]*$' | sort -u)
  local arms=""
  for a in $cand; do
    $PY -c "import sys; sys.path.insert(0,'experiments/orchestration/live2'); import arms as A; A.make_arm('$a')" >/dev/null 2>&1 && arms="$arms $a"
  done
  log "D130 published baselines: commit '$subj'; registered arms:${arms:- none}"
  [ -z "$arms" ] && { log "D130: no listed arm is registered in the code: nothing run"; touch $D130DONE; return; }
  local brk=$(item2_breaks)
  log "D130 sizes: 8, 16 and item-2 breaks: ${brk:-none}"
  for a in $arms; do
    v=$(cell $a 8 0 27 _published_validity120 --run-s 120)
    log "D130 validity $a: $(echo "$v" | jq -c '{valid, err, n_errors, lat_p99}')"
    if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then log "D130 $a failed its validity cell: its 600 s runs are skipped"; continue; fi
    for n in $(echo "8 16 $brk" | tr ' ' '\n' | sort -un); do cellv $a $n 0 27 _published >/dev/null; done
    item_done "D130 published baseline $a at 8, 16 and the item-2 breaks"
  done
  touch $D130DONE
  item_done "D130 published-system baselines:${arms}"
}
log "pilot4d driver start (START_ITEM=$START_ITEM): v1.4 watchers; v1.3-fast never run"
if [ $START_ITEM -le 1 ]; then for n in 4 16 32 64; do cellv edf $n 0 27 _c8 $C8 >/dev/null; done; item_done "item 1, edf C_inflight 8 at 4, 16, 32, 64"; fi
if [ $START_ITEM -le 2 ]; then for n in 10 12 14; do
    cellv always-cloud-fcfs $n 0 27 "" >/dev/null; cellv edf $n 0 27 _c8 $C8 >/dev/null; cellv llf $n 0 27 $(lt) $(lf) >/dev/null
  done; item_done "item 2, the breaks between 8 and 16: always-cloud-fcfs, edf C8, llf at 10, 12, 14"; fi
# D130 tuned-engine: always-cloud-fcfs on the P1 server at 8 and 16 (ahead of items 5-9)
if [ $START_ITEM -le 2 ]; then for n in 8 16; do cellv always-cloud-fcfs $n 0 27 _tuned-engine "$TUNED" >/dev/null; done
  item_done "D130 tuned-engine (--long-prefill-token-threshold 1024) as always-cloud-fcfs at 8, 16"; fi
# PRIORITY 0 follow-up: the released policy at the item-2 break sizes
POLICY_ARM=${POLICY_ARM:-covex-v13}
if [ -f $OUT/POLICY_RELEASE_HANDLED ] && [ -f $OUT/POLICY_RUNS_OK ]; then
  BRK2=$(item2_breaks)
  for n in $BRK2; do cellv $POLICY_ARM $n 0 27 _release >/dev/null; done
  [ -n "$BRK2" ] && item_done "$POLICY_ARM at the item-2 break sizes $BRK2"
fi
d130_published
if [ $START_ITEM -le 3 ]; then for n in 4 8 16 32; do cellv b9 $n 0 27 "" >/dev/null; done; item_done "item 3, b9 at 4, 8, 16, 32"; fi
d130_published
if [ $START_ITEM -le 4 ]; then for n in 4 8 16 32; do cellv utility-per-cost $n 0 27 "" >/dev/null; done; item_done "item 4, utility-per-cost at 4, 8, 16, 32"; fi
d130_published
if [ $START_ITEM -le 5 ]; then for n in 16 32 64; do cellv always-cloud-fcfs $n 0 27 "" >/dev/null; done; item_done "item 5, always-cloud-fcfs at 16, 32, 64"; fi
d130_published
if [ $START_ITEM -le 6 ]; then for n in 4 8 16 32; do cellv vllm-priority $n 0 27 _prio --scheduling-policy priority >/dev/null; done; item_done "item 6, vllm-priority in priority mode at 4, 8, 16, 32"; fi
d130_published
if [ -f $OUT/SKIP_ITEM7 ]; then log "item 7 SKIPPED: $(cat $OUT/SKIP_ITEM7)"; elif [ $START_ITEM -le 7 ]; then for a in edf-piece1024 edf-piece2048; do for n in 8 16; do cellv $a $n 0 27 $(lt) $(lf) >/dev/null; done; done; item_done "item 7, edf-piece1024 and edf-piece2048 at 8, 16"; fi
d130_published
if [ $START_ITEM -le 8 ]; then for n in 8 16; do
    cellv always-cloud-fcfs $n 0 256 "" >/dev/null; cellv edf $n 0 256 _c8 $C8 >/dev/null; cellv llf $n 0 256 $(lt) $(lf) >/dev/null; cellv b9 $n 0 256 "" >/dev/null
  done; item_done "item 8, roomy 256 GiB: always-cloud-fcfs, edf C8, llf, b9 at 8, 16"; fi
d130_published
if [ $START_ITEM -le 9 ]; then for n in 8 16; do cellv llf $n 4 27 $(lt)_devseed4 $(lf) >/dev/null; cellv edf $n 4 27 _c8_devseed4 $C8 >/dev/null; done; item_done "item 9, development seed 4: llf and edf C8 at 8, 16"; fi
log "BASELINE QUEUE DONE"; echo BASELINES_DONE > $OUT/STATUS
