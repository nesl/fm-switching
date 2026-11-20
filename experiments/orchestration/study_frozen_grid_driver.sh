#!/bin/bash
# StudyFROZEN-test: the THREE-TYPE grid (user rulings 2026-11-19 evening; D143).
#   dashcam : LH-REQ EVAL robot : single-shot (RefSpatial + RealWorldQA EVAL) = 40 : 40 : 20, SS deadline 2 s, one per
#   10 s per assistive device; 1200 s (flash's committed run-length table, fallback in force); tight 27 GiB; push-all
#   (mode A); --kv-capacity-enforced.
#   Step 1: b7, eco-llm, mooncake, hybrid-F, hybrid-F6 at 16 and 20 devices, seeds 0 and 4 (hybrid-F6 at 20 only after
#           "policy-F6 fast"; until then its 20-device cells run last in the step). Step 2: seeds 5 and 6. Step 3: 14
#           and 24 devices, seeds 0 and 4.
# Control files (read at every run boundary, so nothing here is edited mid-run):
#   $OUT/SS_POOL_ARGS   extra runner flags selecting the RefSpatial + RealWorldQA EVAL pool (set from flash's interface)
#   $OUT/HYBRID_ARMS    "hybrid-F hybrid-F6" arm names once "policy-F ready" and its proofs are checked (empty = baselines)
#   $OUT/F6_FAST        exists once "policy-F6 fast" is on origin
#   $OUT/STOP           exists = stop at the next run boundary
# Rules: INVALID = rerun once, then skip and log; one restart on a server crash (the rerun); commit after every run.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
PY=~/.venvs/fm-switching-vllm/bin/python
RAW=$HOME/data/live2/frozen_grid
OUT=results/orchestration/live2/frozen_test/runs
LOG=results/orchestration/live2/frozen_test/frozen_grid.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
RUN_S=1200
mkdir -p $RAW/runs $RAW/work $OUT
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
diskfree_gb() { df -BG --output=avail $HOME | tail -1 | tr -dc 0-9; }
BASE_ARMS="b7-edf-feasibility eco-llm mooncake"

metrics_loop() {   # $1 = output file; curl only; stops when the server stops answering after it came up
  local f=$1 up=0
  while true; do
    if curl -s -m 5 -o $f.tmp http://127.0.0.1:8031/metrics 2>/dev/null; then
      up=1
      echo "$(date '+%F %T') $(grep -E '^vllm:(prefix_cache_queries|prefix_cache_hits|mm_cache_queries|mm_cache_hits|request_success)(_total)?[{ ]' $f.tmp | sed 's/{[^}]*}//' | awk '{a[$1]+=$2} END {for (k in a) printf "%s=%d ", k, a[k]}')" >> $f
    elif [ $up = 1 ]; then break; fi
    sleep 10
  done
  rm -f $f.tmp
}

mm_gate() {   # $1 = run dir: non-vacuous multimodal-cache gate + request-body UUID check (A6000 / user ruling D143 item 4)
  local d=$1 m=$1/metrics_snapshots.log
  local first=$(grep -m1 "mm_cache_queries" $m 2>/dev/null) last=$(grep "mm_cache_queries" $m 2>/dev/null | tail -1)
  jq -n --arg f "$first" --arg l "$last" '
    def parse(s): (s | split(" ") | map(select(contains("="))) | map(split("=") | {key: (.[0] | sub("^vllm:"; "") | sub("_total$"; "")), value: (.[1] | tonumber)}) | from_entries);
    (parse($f)) as $a | (parse($l)) as $b |
    {present: {mm_cache_queries: ($b | has("mm_cache_queries")), mm_cache_hits: ($b | has("mm_cache_hits"))},
     first_snapshot: $a, last_snapshot: $b,
     delta: {mm_cache_queries: (if ($b|has("mm_cache_queries")) and ($a|has("mm_cache_queries")) then $b.mm_cache_queries - $a.mm_cache_queries else null end),
             mm_cache_hits: (if ($b|has("mm_cache_hits")) and ($a|has("mm_cache_hits")) then $b.mm_cache_hits - $a.mm_cache_hits else null end),
             prefix_cache_hits: (if ($b|has("prefix_cache_hits")) and ($a|has("prefix_cache_hits")) then $b.prefix_cache_hits - $a.prefix_cache_hits else null end)}}
    | .gate = (if (.delta.mm_cache_queries == null or .delta.mm_cache_hits == null) then "INSTRUMENT NOT REPORTING"
               elif .delta.mm_cache_queries > 0 and .delta.mm_cache_hits == 0 then "pass"
               else "FAIL: multimodal hits in a run whose payloads should all be unique (SS timing column not usable)" end)
    | .note = "server-wide counters from 10-s snapshots, first to last (the window can omit the first and last ~10 s); dashcam and robot frames carry per-(device, frame) UUIDs (D84), so total hits bound single-shot hits"' > $d/mm_gate.json
  # request-body check: single-shot requests (assistive devices), distinct mm UUIDs over SS requests
  jq -s '[.[] | select((.device_id // "") | startswith("asst"))] |
         {ss_requests: length, distinct_mm_uuids: ([.[].mm_uuids[]?] | unique | length),
          ss_requests_with_uuid: (map(select((.mm_uuids // []) | length > 0)) | length)}' $d/request.jsonl > $d/mm_uuid_check.json 2>/dev/null
}

cell() {   # arm n seed [tag]
  local arm=$1 n=$2 seed=$3 tag=${4:-}
  local name=${arm}_n${n}_s${seed}_${RUN_S}s_h27_3t${tag}
  local d=$RAW/runs/$name
  if [ -f $OUT/$name/cell.json ]; then log "skip $name: already run"; jq -c '{err, run_valid, digests_equal, n_errors} | . + {valid:((.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0))}' $OUT/$name/cell.json; return; fi
  if [ "$(diskfree_gb)" -lt 50 ]; then log "DISK below 50 GB: not launching $name"; echo '{"valid":false,"skipped":"disk"}'; return; fi
  local ssargs=$(cat $OUT/SS_POOL_ARGS 2>/dev/null)
  while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
  log "start $name HEAD $(git rev-parse --short HEAD) ss-pool [$ssargs]"
  mkdir -p $d
  ( metrics_loop $d/metrics_snapshots.log ) &
  local mp=$!
  $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $RUN_S --host-tier-gib 27 \
    --seed $seed --ratio 40:40:20 --robot-question-set lh_req --kv-capacity-enforced $ssargs --mode A --calibration $CAL \
    --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server \
    --label "FROZEN_TEST_THREE_TYPE $name" --out $d > $d.stdout 2>&1
  local rc=$?
  kill $mp 2>/dev/null; wait $mp 2>/dev/null
  mm_gate $d
  rm -rf $OUT/$name; cp -r $d $OUT/$name 2>/dev/null; cp $d.stdout $OUT/$name.stdout 2>/dev/null
  find $OUT/$name -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
  local v=$(jq -c '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms, scored:.score.ok}' $d/cell.json 2>/dev/null)
  [ -z "$v" ] && v='{"err":"no cell.json","run_valid":false}'
  v=$(echo "$v" | jq -c --arg name "$name" --argjson rc $rc --slurpfile g $d/mm_gate.json '. + {name:$name, rc:$rc, mm_gate:($g[0].gate // null),
       valid:((.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0))}')
  log "end $name $v"
  echo "$v"
}

commit_cell() {
  git add $OUT $LOG experiments/orchestration/study_frozen_grid_driver.sh 2>/dev/null
  git commit -q -m "frozen-test: $1 (three-type grid, 1200 s)" 2>/dev/null
  for i in 1 2 3; do git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null && break
    git add results/orchestration/live2/pilot/pilot_monitor.jsonl 2>/dev/null; git commit -q -m "logs" 2>/dev/null; done
  log "COMMITTED: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}

ordered_cells() {   # prints "arm n seed" lines in the ruled order, given the current control files
  local hyb=$(cat $OUT/HYBRID_ARMS 2>/dev/null) f6fast=0; [ -f $OUT/F6_FAST ] && f6fast=1
  for step in 1 2 3; do
    case $step in 1) seeds="0 4"; sizes="16 20";; 2) seeds="5 6"; sizes="16 20";; 3) seeds="0 4"; sizes="14 24";; esac
    local late=""
    for s in $seeds; do for n in $sizes; do for a in $BASE_ARMS $hyb; do
      if [ "$a" = "hybrid-F6" ] && [ "$n" = "20" -o "$n" = "24" ] && [ $f6fast = 0 ]; then late="$late
$a $n $s"; continue; fi
      echo "$a $n $s"; done; done; done
    [ $f6fast = 0 ] && [ -n "$late" ] && echo "$late" | sed '/^$/d' | sed 's/$/ F6LATE/'
  done
}

log "frozen grid driver start, HEAD $(git rev-parse --short HEAD)"
while true; do
  [ -f $OUT/STOP ] && { log "STOP file found: driver exits at a run boundary"; exit 0; }
  git fetch -q 2>/dev/null
  git log origin/main --format=%s -400 | grep -q "^policy-F6 fast" && [ ! -f $OUT/F6_FAST ] && { touch $OUT/F6_FAST; log "policy-F6 fast on origin: hybrid-F6 at 20 joins in order"; }
  next=""
  while read a n s late; do
    [ -z "$a" ] && continue
    [ "$late" = "F6LATE" ] && [ ! -f $OUT/F6_FAST ] && continue    # F6 at 20 waits for "policy-F6 fast"
    name=${a}_n${n}_s${s}_${RUN_S}s_h27_3t
    grep -qx "$name" $OUT/SKIPPED 2>/dev/null && continue
    [ -f $OUT/$name/cell.json ] && [ "$(jq -r '(.err==null) and (.run_valid==true) and (.digests_equal==true) and ((.n_errors//1)==0)' $OUT/$name/cell.json)" = "true" ] && continue
    [ -f $OUT/${name}_rerun/cell.json ] && continue
    next="$a $n $s"; break
  done < <(ordered_cells)
  if [ -z "$next" ]; then
    if [ -n "$(cat $OUT/HYBRID_ARMS 2>/dev/null)" ] && [ -f $OUT/F6_FAST ]; then log "FROZEN GRID DONE"; echo DONE > $OUT/STATUS; exit 0; fi
    log "grid: nothing runnable now (waiting for policy-F / F6 fast); driver exits so the operator can refill GPU 2"; echo WAITING > $OUT/STATUS; exit 0
  fi
  set -- $next
  v=$(cell $1 $2 $3)
  if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
    log "INVALID, rerun once: $(echo "$v" | jq -c '{name, err, run_valid, n_errors}')"
    v=$(cell $1 $2 $3 _rerun)
    [ "$(echo "$v" | jq -r .valid)" != "true" ] && { log "INVALID TWICE: skipped and recorded"; echo "${1}_n${2}_s${3}_${RUN_S}s_h27_3t" >> $OUT/SKIPPED; }
  fi
  commit_cell "$1 at $2 devices, seed $3"
done
