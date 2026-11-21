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
#   $OUT/DEFER_SIZES    sizes held to the end of the whole queue (e.g. "20": 97 percent of the committed peak, overload)
# Rules (D144): a run that completed counts whatever its request errors (each dropped or over-context request is a
#   per-question miss); error count and requests offered are recorded, saturated if > 5 percent errored. Only a run
#   with no result (crash, refusal) is rerun once, then skipped and logged. Commit after every run.
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
  # body checks. (1) PRESENCE on the WIRE body, per image part and per class (asyncbackend counts after materialize and
  # strip_internal): parts carrying a non-empty "uuid" over parts. (2) the client-side record (request.jsonl): SS
  # requests and distinct mm UUIDs (equal by construction; reported, not used as the content-class proof, which is the
  # server gate's). (3) mm_cache_queries beside the run's request count (lower = scrape lag, not a skipped cache).
  local bk=$(jq -c '(.backend // {}) | {wire_image_parts, wire_image_parts_with_uuid}' $d/coordinator_result.json 2>/dev/null)
  jq -s --argjson bk "${bk:-null}" --slurpfile g $d/mm_gate.json --argjson nreq "$(jq '.n_requests // null' $d/cell.json 2>/dev/null || echo null)" '
         [.[] | select((.device_id // "") | startswith("asst"))] |
         {wire_presence: $bk,
          client_record: {ss_requests: length, distinct_mm_uuids: ([.[].mm_uuids[]?] | unique | length),
                          ss_requests_with_uuid: (map(select((.mm_uuids // []) | length > 0)) | length)},
          mm_cache_queries_delta: ($g[0].delta.mm_cache_queries), run_requests: $nreq}' $d/request.jsonl > $d/mm_uuid_check.json 2>/dev/null
}

cell() {   # arm n seed [tag]
  local arm=$1 n=$2 seed=$3 tag=${4:-}
  local name=${arm}_n${n}_s${seed}_${RUN_S}s_h27_3t${tag}
  local d=$RAW/runs/$name
  if [ -f $OUT/$name/cell.json ]; then log "skip $name: already run"; jq -c '{err, run_valid, digests_equal, n_errors} | . + {valid:((.err==null) and (.run_valid==true) and (.digests_equal==true))}' $OUT/$name/cell.json; return; fi
  if [ "$(diskfree_gb)" -lt 50 ]; then log "DISK below 50 GB: not launching $name"; echo '{"valid":false,"skipped":"disk"}'; return; fi
  local ssargs=$(cat $OUT/SS_POOL_ARGS 2>/dev/null)
  # D147 (user ruling 2026-11-20): a cell tagged _L3 runs at robot deadline 3 s (SS 2 s and dashcam 1 s unchanged)
  local lflag=""; case "$tag" in *_L3*) lflag="--robot-deadline-s 3";; esac
  # D151 WARM-ALL calibration, PROVISIONAL (user away; pre-registered default): "0.5x / 0.25x GPU pool" is the harness's
  # LOGICAL pool with enforcement on (coordinator belief and enforcement); the engine's real pool is pinned and unchanged
  case "$tag" in *_kv0.5*) lflag="$lflag --gpu-kv-tokens 31472";; *_kv0.25*) lflag="$lflag --gpu-kv-tokens 15736";; esac
  # D153: a cell tagged _epg runs the EP-G dashcam episode workload with the arguments flash's commit put in EPG_ARGS;
  # a cell without it is dashcam-1f (one frame per call), recorded in its label
  local wl="dashcam-1f upload-30s"; case "$tag" in *_cal1f*) wl="CALIBRATION-1F dashcam-1f upload-30s";; esac
  # D156 (2): every EP-G cell (the WARM-ALL held-out cells onward) also uploads robot frames per frame (flash 34a4af0)
  case "$tag" in *_epg*) lflag="$lflag $(grep -v '^#' $OUT/EPG_ARGS | tr '\n' ' ') --robot-upload per-frame"; wl="dashcam-EP-G upload-pf";; esac
  # D158 (4): a piece-chaining arm ($OUT/PIECE_ARMS) run before the race fix (no $OUT/RACE_FIXED) is race-affected
  if [ ! -f $OUT/RACE_FIXED ] && grep -v '^#' $OUT/PIECE_ARMS 2>/dev/null | grep -qx "$arm"; then wl="$wl race-affected"; fi
  case "$tag" in *_rf*) wl="$wl race-fixed-rerun";; esac
  while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
  log "start $name HEAD $(git rev-parse --short HEAD) ss-pool [$ssargs] deadline [${lflag:-robot 5 s}] workload [$wl]"
  mkdir -p $d
  ( metrics_loop $d/metrics_snapshots.log ) &
  local mp=$!
  $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $RUN_S --host-tier-gib 27 \
    --seed $seed --ratio 40:40:20 --robot-question-set lh_req --kv-capacity-enforced $ssargs $lflag --mode A --calibration $CAL \
    --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server \
    --label "FROZEN_TEST_THREE_TYPE $wl $name" --out $d > $d.stdout 2>&1
  local rc=$?
  kill $mp 2>/dev/null; wait $mp 2>/dev/null
  mm_gate $d
  rm -rf $OUT/$name; cp -r $d $OUT/$name 2>/dev/null; cp $d.stdout $OUT/$name.stdout 2>/dev/null
  find $OUT/$name -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
  local v=$(jq -c '{err, run_valid, digests_equal, n_requests, n_errors, lat_p99:.lateness.p99_ms, scored:.score.ok}' $d/cell.json 2>/dev/null)
  [ -z "$v" ] && v='{"err":"no cell.json","run_valid":false}'
  v=$(echo "$v" | jq -c --arg name "$name" --argjson rc $rc --slurpfile g $d/mm_gate.json '. + {name:$name, rc:$rc, mm_gate:($g[0].gate // null),
       valid:((.err==null) and (.run_valid==true) and (.digests_equal==true)),
       request_errors:(.n_errors // null), requests_offered:(.n_requests // null),
       saturated:(if (.n_requests // 0) > 0 then (((.n_errors // 0) / .n_requests) > 0.05) else null end)}')
  log "end $name $v"
  echo "$v"
}

commit_cell() {
  git add $OUT $LOG 2>/dev/null
  git commit -q -m "frozen-test: $1 (three-type grid, 1200 s)" 2>/dev/null
  for i in 1 2 3; do git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null && break
    git add results/orchestration/live2/pilot/pilot_monitor.jsonl 2>/dev/null; git commit -q -m "logs" 2>/dev/null; done
  log "COMMITTED: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
}

ordered_cells() {   # user order (2026-11-20, after D144): the requeued seed-6 hybrids at 16; then the BASELINE SWEEP:
  # pass 1 every arm in $OUT/SWEEP_ARMS at 16 devices seed 4, pass 2 the same at 18 seed 4, pass 3 the arms in $OUT/TOP5
  # at seeds 5, 6, 0 (16 devices, PROVISIONAL). Both files are read at every run boundary, one arm name per line.
  for a in hybrid-F-lhreq hybrid-F6-lhreq; do echo "$a 16 6"; done
  # user ruling 2026-11-20: after the RECENT-send fix, REDO eco-llm and hybrid-F-lhreq at 16 devices seeds 0, 4, 5, 6
  # AHEAD of the rest of the sweep, as new cells tagged _postfix (the pre-fix runs are kept, labelled pre-fix)
  for s in 0 4 5 6; do for a in eco-llm hybrid-F-lhreq; do echo "$a 16 $s _postfix"; done; done
  # user ruling 2026-11-20 (D151): flash's cost-model-gate calibration cells run AHEAD of the remaining sweep. Read at
  # every run boundary from $OUT/CALIB_CELLS, one "arm n seed" per line, so cells needing an arm not yet built (WARM-ALL
  # plus LRU, warm-ahead) can be appended when it exists. A cell already run in the frozen grid or sweep is skipped.
  grep -v '^#' $OUT/CALIB_CELLS 2>/dev/null | awk 'NF>=3 {print $1, $2, $3}'
  # D147 / D152 (user ruling 2026-11-20): from here every cell runs at robot deadline 3 s, tagged _L3 (cells run at 5 s
  # stay labelled by their names). HANDFUL FIRST at 16 devices, seed 4, then seeds 5 and 6, from $OUT/HANDFUL_L3 (read
  # at every boundary, so an arm flash lands later joins at the next boundary); then the rest of the sweep at 3 s.
  local hf=$(grep -v '^#' $OUT/HANDFUL_L3 2>/dev/null | tr -s ' \n' ' ')
  local sw=$(grep -v '^#' $OUT/SWEEP_ARMS 2>/dev/null | tr -s ' \n' ' ') top=$(grep -v '^#' $OUT/TOP5 2>/dev/null | tr -s ' \n' ' ')
  # overnight queue (user ruling 2026-11-20, item 2): handful seed 4 -> the WARM-ALL calibration cells (when flash's arm
  # is on origin with its proofs; $OUT/WARMALL_CELLS, "arm n seed tag") -> v5 at 16 seed 4 (only if flash posts
  # "policy-v5 ready" with the gate and the 32B confirmation passed; $OUT/V5_CELLS) -> handful seeds 5 and 6 -> the rest
  # of the sweep at 3 s. An empty or missing file is skipped, so the queue never stalls.
  # D153 (user decision 2026-11-20): the dashcam workload is the append-only episode format (EP-G). Once flash's EP-G
  # live-bodies commit is on origin with its proofs, $OUT/EPG_ARGS holds the harness arguments that select it, and from
  # the next boundary: the WARM-ALL calibration cells (EP-G ONLY, never dashcam-1f) -> the 3 s handful redone on EP-G
  # at seed 4, then seeds 5 and 6 -> the rest of the sweep on EP-G (PROVISIONAL: the brief names only the handful).
  # Until then the one-frame queue below keeps GPU 2 busy; every such cell is labelled dashcam-1f (sensitivity only).
  # PRIORITY (user decision 2026-11-20 ~18:50): policy-unblocking work FIRST, baselines only fill gaps.
  #  (1) flash's 32B engine-action confirmation: run by the operator at a boundary (STOP, run, resume), not by this loop
  #  (2) WARMALL_CELLS_1F: warm-all-lru and warm-all-lru-reactive, seed 4, 3 s, dashcam-1f, labelled CALIBRATION-1F
  #  (3) the EP-G WARM-ALL cells once EPG_ARGS lands
  #  (4) v5-rules once flash posts "v5-rules ready" ($OUT/V5RULES_CELLS)
  #  (5) full v5 only with the gate passed ($OUT/V5_CELLS)
  # then baselines: EP-G (handful seeds 4, 5, 6, then the sweep) once available, else dashcam-1f.
  grep -v '^#' $OUT/WARMALL_CELLS_1F 2>/dev/null | awk 'NF>=3 {print $1, $2, $3, $4}'
  # D158 (user rulings 2026-11-20 ~20:30). Arms that WARM AHEAD ($OUT/WAIT_ARMS: warm-all-lru, -noyield, v5-rules) wait
  # for flash's race fix ($OUT/RACE_FIXED, written when its three proofs pass). Until then: the EP-G WARM-ALL held-out
  # cells of the other arms (-reactive, -off), then the EP-G handful (none of its 11 arms piece-chains). When RACE_FIXED
  # exists OR from 23:00 (to 06:00), whichever is first: v5-rules beside its 7 comparison arms at seeds 4 and 5 (labelled
  # race-affected without the fix); then, only after the fix, the waiting held-out cells re-run or run (_rf).
  local wa=$(grep -v '^#' $OUT/WAIT_ARMS 2>/dev/null | tr -s ' \n' ' ')
  local fixed=""; [ -f $OUT/RACE_FIXED ] && fixed=1
  local hm=$(date +%H%M); local v5go=""
  { [ -n "$fixed" ] || [ "$hm" -ge 2300 ] || [ "$hm" -lt 600 ]; } && v5go=1
  local v5r=$(grep -v '^#' $OUT/V5RULES_CELLS 2>/dev/null | awk 'NF>=1 {print $1}' | sort -u | tr '\n' ' ')
  if [ -s $OUT/EPG_ARGS ]; then
    grep -v '^#' $OUT/WARMALL_CELLS 2>/dev/null | awk -v wa=" $wa " 'NF>=3 {t=$4; if (t !~ /_epg/) t=t "_epg"; if (index(wa, " " $1 " ") == 0) print $1, $2, $3, t}'
    if [ -n "$v5r" ] && [ -n "$v5go" ]; then
      for s in 4 5; do for x in $v5r b7-edf-feasibility hybrid-F-lhreq-noc3 mooncake eco-llm edf llf warm-all-lru; do
        echo "$x 16 $s _L3_epg"; done; done
    fi
    if [ -n "$fixed" ]; then
      grep -v '^#' $OUT/WARMALL_CELLS 2>/dev/null | awk -v wa=" $wa " 'NF>=3 {t=$4; if (t !~ /_epg/) t=t "_epg"; if (index(wa, " " $1 " ") > 0) print $1, $2, $3, t "_rf"}'
    fi
  fi
  grep -v '^#' $OUT/V5_CELLS 2>/dev/null | awk 'NF>=3 {print $1, $2, $3, $4}'
  if [ -s $OUT/EPG_ARGS ]; then
    for s in 4 5 6; do for x in $hf; do echo "$x 16 $s _L3_epg"; done; done
    for x in $sw; do echo "$x 16 4 _L3_epg"; done
  fi
  for x in $hf; do echo "$x 16 4 _L3"; done
  for s in 5 6; do for x in $hf; do echo "$x 16 $s _L3"; done; done
  for x in $sw; do echo "$x 16 4 _L3"; done
  for x in $sw; do echo "$x 18 4 _L3"; done
  for s in 5 6 0; do for x in $top; do echo "$x 16 $s _L3"; done; done
  return 0
}

log "frozen grid driver v10 (D158: warm-ahead arms wait for the race fix or 23:00; EP-G non-piece cells meanwhile) start, HEAD $(git rev-parse --short HEAD)"
while true; do
  [ -f $OUT/STOP ] && { log "STOP file found: driver exits at a run boundary"; exit 0; }
  git fetch -q 2>/dev/null
  git log origin/main --format=%s -400 | grep -q "^policy-F6 fast" && [ ! -f $OUT/F6_FAST ] && { touch $OUT/F6_FAST; log "policy-F6 fast on origin: hybrid-F6 at 20 joins in order"; }
  next=""
  while read a n s tag; do
    [ -z "$a" ] && continue
    name=${a}_n${n}_s${s}_${RUN_S}s_h27_3t${tag}
    grep -qx "$name" $OUT/SKIPPED 2>/dev/null && continue
    [ -f $OUT/$name/cell.json ] && [ "$(jq -r '(.err==null) and (.run_valid==true) and (.digests_equal==true)' $OUT/$name/cell.json)" = "true" ] && continue
    [ -f $OUT/${name}_rerun/cell.json ] && continue
    next="$a $n $s $tag"; break
  done < <(ordered_cells)
  if [ -z "$next" ]; then
    if [ -s $OUT/TOP5 ]; then log "SWEEP DONE (all queued cells run)"; echo DONE > $OUT/STATUS; exit 0; fi
    log "sweep: nothing runnable now (passes 1 and 2 done; TOP5 not yet set); driver exits so the operator can refill GPU 2"; echo WAITING > $OUT/STATUS; exit 0
  fi
  set -- $next
  tg=${4:-}
  v=$(cell $1 $2 $3 "$tg")
  if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
    log "INVALID, rerun once: $(echo "$v" | jq -c '{name, err, run_valid, n_errors}')"
    v=$(cell $1 $2 $3 "${tg}_rerun")
    [ "$(echo "$v" | jq -r .valid)" != "true" ] && { log "INVALID TWICE: skipped and recorded"; echo "${1}_n${2}_s${3}_${RUN_S}s_h27_3t${tg}" >> $OUT/SKIPPED; }
  fi
  commit_cell "$1 at $2 devices, seed $3${tg:+ ($tg)}"
done
