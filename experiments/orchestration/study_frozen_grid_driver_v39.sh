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
      # v32 (D211 recording request, read-only): from the SAME scrape (no extra GET), the host-hit counters with their
      # labels kept (source / transfer_type), a unix timestamp and /proc/loadavg with magnitude, one line per 10 s
      # v33 (EVAL_PLAN per-cell series): GPU 2 utilization and memory, and generation tokens, on the same line
      echo "t=$(date +%s.%N | cut -c1-14) loadavg=$(cut -d' ' -f1-3 /proc/loadavg | tr ' ' ',') gpu2=$(nvidia-smi -i $CLEAN_GPU_UUID --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ') $(grep -E '^vllm:(generation_tokens_total|prompt_tokens_by_source_total|external_prefix_cache_hits_total|external_prefix_cache_queries_total|kv_offload_load_bytes_total|kv_offload_store_bytes_total|prompt_tokens_cached_total|prompt_tokens_total|kv_cache_usage_perc|kv_offload_cpu_cache_usage_perc)[{ ]' $f.tmp | sed -E 's/engine="0",model_name="[^"]*",?//; s/\{\}//; s/\{/[/; s/\}/]/; s/"//g' | awk '{printf "%s=%s ", $1, $2}')" >> $(dirname $f)/host_counters_d211.log
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
  # v31 (D191 (3), recall deadline 2.5 s edge condition): the robot deadline is read from the tag's _L<seconds> token,
  # so _L3 keeps giving 3 s exactly as before and _L2.5 gives 2.5 s; no token keeps the harness default
  local lflag="" _dl wl_ms=""
  _dl=$(echo "$tag" | sed -nE 's/.*_L([0-9]+(\.[0-9]+)?)(_.*)?$/\1/p')
  [ -n "$_dl" ] && lflag="--robot-deadline-s $_dl"
  # D151 WARM-ALL calibration, PROVISIONAL (user away; pre-registered default): "0.5x / 0.25x GPU pool" is the harness's
  # LOGICAL pool with enforcement on (coordinator belief and enforcement); the engine's real pool is pinned and unchanged
  case "$tag" in *_kv0.5*) lflag="$lflag --gpu-kv-tokens 31472";; *_kv0.25*) lflag="$lflag --gpu-kv-tokens 15736";; esac
  # v36 (flash 2026-11-24, rung-4 pass 1 at 0.5x): a tag token _ms turns the engine /metrics scrape ON for that cell
  # (runner --metrics-scrape; the runner default is OFF since 3b610470). Matched as a whole token, so the cell name says
  # it scraped and no arm is special-cased.
  case "${tag}_" in *_ms_*) lflag="$lflag --metrics-scrape"; wl_ms=" metrics-scrape";; *) wl_ms="";; esac
  # D153: a cell tagged _epg runs the EP-G dashcam episode workload with the arguments flash's commit put in EPG_ARGS;
  # a cell without it is dashcam-1f (one frame per call), recorded in its label
  local wl="dashcam-1f upload-30s"; case "$tag" in *_cal1f*) wl="CALIBRATION-1F dashcam-1f upload-30s";; esac
  # D156 (2): every EP-G cell (the WARM-ALL held-out cells onward) also uploads robot frames per frame (flash 34a4af0)
  case "$tag" in *_epg*) lflag="$lflag $(grep -v '^#' $OUT/EPG_ARGS | tr '\n' ' ') --robot-upload per-frame"; wl="dashcam-EP-G upload-pf";; esac
  # D158 (4): a piece-chaining arm ($OUT/PIECE_ARMS) run before the race fix (no $OUT/RACE_FIXED) is race-affected
  if [ ! -f $OUT/RACE_FIXED ] && grep -v '^#' $OUT/PIECE_ARMS 2>/dev/null | grep -qx "$arm"; then wl="$wl race-affected"; fi
  case "$tag" in *_rf*) wl="$wl race-fixed-rerun";; esac
  # D159 (4): a cell tagged _rq30 runs flash's repeat-question trace; its harness arguments come from $OUT/RQ30_ARGS
  # v33 (EVAL_PLAN re-ask conditions): a tag token _rq<k> gives --robot-reask-mean-s k. _rq30 still takes RQ30_ARGS
  # verbatim (byte-identical to v32); any other k is passed directly.
  local _rq; _rq=$(echo "$tag" | sed -nE 's/.*_rq([0-9]+)(_.*)?$/\1/p')
  case "$_rq" in
    "") ;;
    30) lflag="$lflag $(grep -v '^#' $OUT/RQ30_ARGS 2>/dev/null | tr '\n' ' ')"; wl="$wl rq30 reask-device-PROVISIONAL";;
    *) lflag="$lflag --robot-reask-mean-s $_rq"; wl="$wl rq$_rq reask-device-PROVISIONAL";;
  esac
  # v39 (D244, authorised by flash under D244 2026-11-25 ~07:55): a tag token _out-k<K>-d<D> runs the D242 trace-level
  # correlated multi-robot outage; run_live2_real.py defaults both flags to 0 = OFF, so without this the tag would be
  # a switch that never reaches the run. EPG_ARGS and RQ30_ARGS still apply (the rq parse reads 30 off ..._rq30_out-...).
  # LIMIT: D is captured as an INTEGER (d([0-9]+)); the harness takes a float and names its trace dir with %g, so a
  # fractional D (e.g. 120.5 -> _outk3d120.5) is NOT expressible in a tag and would also miss the trace_meta glob below.
  local _ok _od; _ok=$(echo "$tag" | sed -nE 's/.*_out-k([0-9]+)-d([0-9]+)(_.*)?$/\1/p'); _od=$(echo "$tag" | sed -nE 's/.*_out-k([0-9]+)-d([0-9]+)(_.*)?$/\2/p')
  [ -n "$_ok" ] && { lflag="$lflag --outage-robots-k $_ok --outage-duration-s $_od"; wl="$wl outage-k${_ok}-d${_od}"; }
  # v33 (EVAL_PLAN composition conditions): a tag token _c<d>-<r>-<a> sets --ratio d:r:a (it must be a key of
  # live2/fleet/trace.py RATIOS_3); no token keeps the committed 40:40:20
  local ratio; ratio=$(echo "$tag" | sed -nE 's/.*_c([0-9]+)-([0-9]+)-([0-9]+)(_.*)?$/\1:\2:\3/p')
  [ -z "$ratio" ] && ratio=40:40:20
  [ "$ratio" != 40:40:20 ] && wl="$wl composition-$ratio"
  # D154 (5) / BASELINE_MATRIX note: arms that WAIT for the device answer (scorer cascade_device_wait) wait the flat
  # costs.py DEV_LAT_S = 0.567 s, not the measured warm p50; their cells run and carry this label until the measured-wait rerun
  # corrected 2026-11-22 ~10:00: an arm released in $OUT/DEVWAIT_READY waits the MEASURED Orin table (coordinator _device_wait_s),
  # so it is labelled device-wait-measured; only an unreleased device-waiting arm would still be on the 0.567 s proxy
  case "$arm" in confidence-cascade|cascade-routing|r3-streaming|streamscout|thinking-qwenvl)
    if grep -qx "$arm" $OUT/DEVWAIT_READY 2>/dev/null; then wl="$wl device-wait-measured"; else wl="$wl device-wait-proxy-0.567"; fi;; esac
  # D159 (3): a cell tagged _ls<k> is a load-sweep cell; its extra harness arguments are on its LOADSWEEP_CELLS line
  case "$tag" in *_ls*) lflag="$lflag $(grep -v '^#' $OUT/LOADSWEEP_CELLS 2>/dev/null | awk -v a="$arm" -v n="$n" -v s="$seed" -v t="$tag" '$1==a && $2==n && $3==s && $4==t {for (i=5;i<=NF;i++) printf "%s ", $i}')"; wl="$wl load-sweep";; esac
  # user addendum ~10:45 (resolve C5 first): a C5DIAG_CELLS line may carry SERVER flags in fields 5+ (e.g. flash's
  # pre-registered --long-prefill-token-threshold N); they go to the harness's --server-extra-flags, the cell is labelled
  # engine-flag-diagnostic (never headline), and a watcher checks the flag is LIVE in the launched server's own argv,
  # stopping the cell with SIGINT (atexit stops the server) if it is not. Every cell restarts the server, so the next cell
  # is on the standard server again.
  local sxf=""
  # v37 (2026-11-24): an automatic rerun is tagged ..._rerun, but its server flags live on the ORIGINAL list line, so
  # the lookup strips trailing _rerun tokens (before v37 a kv0.5r rerun got NO flags: under v35 it would have run on
  # the FULL pool under a 0.5x name; v36's pre-launch assertion refused it instead, and the cell was skipped).
  local _ltag="$tag"; while [ "${_ltag%_rerun}" != "$_ltag" ]; do _ltag="${_ltag%_rerun}"; done
  # v30 (D189, user ruling 2026-11-23 ~07:40: REAL engine 0.25x): server flags may come from fields 5+ of ANY GATED list
  # (C5DIAG_CELLS or any list recorded with its current sha256 in V6_GATE_OK); the first gated match wins
  local _f
  for _f in C5DIAG_CELLS $(awk '{print $1}' $OUT/V6_GATE_OK 2>/dev/null | sort -u); do
    grep -qx "$_f $(sha256sum $OUT/$_f 2>/dev/null | cut -c1-64)" $OUT/V6_GATE_OK 2>/dev/null || continue
    sxf=$(grep -v '^#' $OUT/$_f 2>/dev/null | awk -v a="$arm" -v n="$n" -v s="$seed" -v t="$_ltag" '$1==a && $2==n && $3==s && $4==t {for (i=5;i<=NF;i++) printf "%s ", $i}' | head -1 | sed 's/ *$//')
    [ -n "$sxf" ] && break
  done
  # a KV / context override is a D189 EDGE CONDITION (reported in the usual table), not an engine-flag diagnostic
  case "$sxf" in
    "") ;;
    *num-gpu-blocks-override*|*kv-cache-memory*|*max-model-len*) wl="$wl engine-kv-override[$sxf]";;
    *) wl="$wl engine-flag-diagnostic[$sxf]";;
  esac
  wl="$wl$wl_ms"
  # v36 (flash's caution, 2026-11-24): a _kv0.5r cell's tag now can carry two meanings (_kv0.5r and _ms), so the REAL
  # 0.5x server args are ASSERTED before launch, never inferred after: without both flags the cell does not run (a
  # full-pool cell wearing a 0.5x name is the failure this prevents). Logged and recorded in SKIPPED_ARGS.
  case "$tag" in *_kv0.5r*)
    if ! { echo " $sxf " | grep -qF -- " --num-gpu-blocks-override 1968 " && echo " $sxf " | grep -qF -- " --max-model-len 31472 "; }; then
      log "ENGINE ARGS MISMATCH for $name: tag _kv0.5r but server flags [$sxf] lack --num-gpu-blocks-override 1968 --max-model-len 31472; NOT RUN"
      echo "$name" >> $OUT/SKIPPED_ARGS; echo "$name" >> $OUT/SKIPPED
      echo '{"valid":false,"skipped":"engine-args-mismatch"}'; return; fi;;
  esac
  # v39 (D244): the -outage / -outage-fifo ordering arms are EXCLUDED by the ruling; refuse any line naming them.
  case "$arm" in *-outage*)
    log "EXCLUDED ARM (D244) $name: the -outage ordering arms are excluded by ruling; NOT RUN"
    echo "$name" >> $OUT/SKIPPED_ARGS; echo "$name" >> $OUT/SKIPPED
    echo '{"valid":false,"skipped":"excluded-arm-d244"}'; return;; esac
  # v39 (D244 condition 2): a cell whose tag carries _out is REFUSED unless the harness flags it will launch with carry
  # BOTH --outage-robots-k and --outage-duration-s with non-zero values (an outage-tagged cell running outages-OFF is
  # the failure this prevents). Logged and recorded in SKIPPED_ARGS, as for the _kv0.5r assertion.
  case "$tag" in *_out*)
    if [ -z "$_ok" ] || [ -z "$_od" ] || [ "$_ok" -le 0 ] || [ "$_od" -le 0 ] || ! echo " $lflag " | grep -qF -- " --outage-robots-k $_ok " || ! echo " $lflag " | grep -qF -- " --outage-duration-s $_od "; then
      log "OUTAGE ARGS MISMATCH for $name: tag carries _out but harness flags [$lflag] lack non-zero --outage-robots-k / --outage-duration-s; NOT RUN"
      echo "$name" >> $OUT/SKIPPED_ARGS; echo "$name" >> $OUT/SKIPPED
      echo '{"valid":false,"skipped":"outage-args-mismatch"}'; return; fi;;
  esac
  while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
  log "start $name HEAD $(git rev-parse --short HEAD) TREE $(git rev-parse --short=12 HEAD:experiments) ss-pool [$ssargs] deadline [${lflag:-robot 5 s}] workload [$wl]"
  mkdir -p $d
  # v39 (D244 conditions 2 and 3): once launched, the harness's OWN argv must carry both outage flags, and the cell's
  # trace_meta.json must RECORD the outage (.outage.args k and D); otherwise the cell is stopped with SIGINT by its pid.
  if [ -n "$_ok" ]; then
    # SAFETY OF pgrep -f HERE RESTS ON THE PATTERN'S SPECIFICITY, not on the flag: the string below occurs only in the
    # harness's own argv; this subshell carries the DRIVER's cmdline (bash .../study_frozen_grid_driver_v39.sh), so it
    # cannot match itself. Do NOT shorten the pattern (e.g. to "run_live2_real"), or it may self-match or match others.
    ( hp=""; for i in $(seq 1 300); do
        hp=$(pgrep -n -u pragya -f "live2/run_live2_real.py --arm $arm --n-devices $n ")
        if [ -n "$hp" ]; then
          argv=$(tr '\0' ' ' < /proc/$hp/cmdline)
          if echo " $argv " | grep -qF -- " --outage-robots-k $_ok " && echo " $argv " | grep -qF -- " --outage-duration-s $_od " && echo " $argv " | grep -qF -- " --seed $seed "; then
            log "OUTAGE FLAGS LIVE for $name: harness pid $hp argv carries --outage-robots-k $_ok --outage-duration-s $_od"
          else log "OUTAGE FLAGS NOT LIVE for $name: harness pid $hp argv lacks them; stopping the cell (SIGINT)"; echo "outage flags not live in harness argv" > $d/VOID_OUTAGE_STOP; kill -INT $hp; exit 0; fi
          break; fi
        sleep 2; done
      for i in $(seq 1 300); do
        tm=$(ls -t $RAW/work/traces/seed${seed}_n${n}_*_outk${_ok}d${_od}*/trace_meta.json 2>/dev/null | head -1)
        if [ -n "$tm" ]; then
          if jq -e --argjson k $_ok --argjson d $_od '.outage.args.outage_robots_k == $k and .outage.args.outage_duration_s == $d' "$tm" >/dev/null 2>&1; then
            log "OUTAGE RECORDED for $name: $tm .outage $(jq -c '{robots: .outage.robots, t_start: .outage.t_start, t_end: .outage.t_end, device_only_q: (.outage.device_only_question_ids | length)}' "$tm")"
          else log "OUTAGE NOT RECORDED for $name: $tm lacks .outage matching k=$_ok d=$_od; stopping the cell (SIGINT)"; echo "outage not recorded in trace_meta" > $d/VOID_OUTAGE_STOP; [ -n "$hp" ] && kill -INT $hp; fi
          break; fi
        sleep 2; done ) &
  fi
  ( metrics_loop $d/metrics_snapshots.log ) &
  local mp=$!
  if [ -n "$sxf" ]; then
    ( for i in $(seq 1 300); do
        sp=$(pgrep -n -u pragya -f "fm-switching-vllm/bin/vllm serve")
        if [ -n "$sp" ]; then
          argv=$(tr '\0' ' ' < /proc/$sp/cmdline)
          ok=1; for tok in $sxf; do echo " $argv " | grep -qF -- " $tok " || ok=0; done
          if [ $ok = 1 ]; then log "ENGINE FLAG LIVE for $name: [$sxf] found in server pid $sp argv"
          else log "ENGINE FLAG NOT LIVE for $name: [$sxf] missing from server pid $sp argv; stopping the cell (SIGINT)"
            pkill -INT -u pragya -f "live2/run_live2_real.py --arm $arm --n-devices $n .*--seed $seed "; fi
          break; fi
        sleep 2; done ) &
  fi
  $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $RUN_S --host-tier-gib 27 \
    --seed $seed --ratio $ratio --robot-question-set lh_req --kv-capacity-enforced $ssargs $lflag --mode A --calibration $CAL \
    --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server ${sxf:+--server-extra-flags "$sxf"} \
    --label "FROZEN_TEST_THREE_TYPE $wl $name" --out $d > $d.stdout 2>&1
  local rc=$?
  # v30 (D189 "confirm the server starts at that KV setting"): record the ENGINE-reported GPU KV pool for every cell,
  # read from the server's own log, beside the harness's logical pool
  local slog kvp
  slog=$(grep -oE '"log": "[^"]+"' $d.stdout 2>/dev/null | head -1 | cut -d'"' -f4)
  kvp=$(grep -oE "GPU KV cache size: [0-9,]+ tokens" "$slog" 2>/dev/null | tail -1 | grep -oE "[0-9,]+" | tr -d ,)
  log "KV POOL $name: engine ${kvp:-unknown} tokens; logical $(echo "$lflag" | grep -oE -- '--gpu-kv-tokens [0-9]+' | cut -d' ' -f2) (blank = default 62944); server flags [${sxf:-none}]"
  kill $mp 2>/dev/null; wait $mp 2>/dev/null
  mm_gate $d
  rm -rf $OUT/$name; cp -r $d $OUT/$name 2>/dev/null; cp $d.stdout $OUT/$name.stdout 2>/dev/null
  find $OUT/$name -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
  # v39 (D244 condition 6): a cell stopped by the outage checks is VOID. Any cell.json it wrote is renamed
  # cell.json.VOID (in the raw dir and the committed copy) so no scorer can read it as a result, and the cell is
  # recorded in SKIPPED (never rerun automatically, never scored).
  if [ -f $d/VOID_OUTAGE_STOP ]; then
    for f in $d/cell.json $OUT/$name/cell.json; do [ -f $f ] && mv $f $f.VOID; done
    log "VOID (D244 outage check failed: $(cat $d/VOID_OUTAGE_STOP)) $name: any cell.json renamed cell.json.VOID; recorded in SKIPPED"
    echo "$name" >> $OUT/SKIPPED_ARGS; echo "$name" >> $OUT/SKIPPED
  fi
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
  # D166: never commit a file over 5 MB (still over 5 MB after the gzip above): unstage it, keep it on disk, log it
  git diff --cached --name-only --diff-filter=AM -z | while IFS= read -r -d '' f; do
    if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 5242880 ]; then git restore --staged -- "$f"; log "NOT COMMITTED (over 5 MB, D166): $f"; fi; done
  git commit -q -m "frozen-test: $1 (three-type grid, 1200 s)" 2>/dev/null
  local _cc=$(git rev-parse HEAD) _cf
  _cf=$(git diff-tree --no-commit-id --name-only -r $_cc 2>/dev/null)
  for i in 1 2 3; do git pull --rebase -q origin main 2>/dev/null; git push -q origin HEAD:main 2>/dev/null && break
    git add results/orchestration/live2/pilot/pilot_monitor.jsonl 2>/dev/null; git commit -q -m "logs" 2>/dev/null; done
  log "COMMITTED: $1 ($(git rev-parse --short HEAD)); origin $(git rev-parse --short origin/main)"
  # v35 POSITIVE push check (flash 2026-11-24): success is asserted, never inferred from a silent push. HEAD must be
  # contained in origin/main after a fresh fetch; if not, say so loudly (the watcher greps for PUSH NOT ON ORIGIN).
  git fetch -q origin 2>/dev/null
  # v36: a concurrent pusher may REBASE the cell commit before it is pushed, giving it a new id; the id check then
  # reports a false "not on origin". So the decisive check is by CONTENT: every file the cell commit wrote must have
  # the same blob on origin/main. The id check is kept and logged beside it.
  local _miss=0 _f
  for _f in $_cf; do [ "$(git rev-parse -q --verify $_cc:$_f 2>/dev/null)" = "$(git rev-parse -q --verify origin/main:$_f 2>/dev/null)" ] || _miss=$((_miss+1)); done
  if [ -n "$_cf" ] && [ $_miss = 0 ]; then log "PUSH VERIFIED (content): all $(echo "$_cf" | wc -l) files of $(git rev-parse --short $_cc) are on origin/main; id check: $(git merge-base --is-ancestor HEAD origin/main 2>/dev/null && echo contained || echo rebased)"
  else log "PUSH NOT ON ORIGIN: $1: $_miss of $(echo "$_cf" | wc -l) files of $(git rev-parse --short $_cc) differ from origin/main $(git rev-parse --short origin/main)"; fi
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
  # D159 (user rulings 2026-11-21 ~07:20), ahead of everything below:
  #  (2) the pre-race-fix reruns flash lists: $OUT/RERUN_CELLS, "arm n seed tag"
  #  (3) flash's controlled load sweep for the cost-model refit: $OUT/LOADSWEEP_CELLS, "arm n seed tag [extra harness args]"
  #  (4) once flash posts the repeat-question trace ($OUT/RQ30_ARGS) AND v5-rules-2 ($OUT/V5RULES2_CELLS, arm name in
  #      column 1): v5-rules-2, v5-rules, hybrid-F-lhreq-noc3, b7, mooncake, eco-llm, llf, edf, warm-all-lru at 3 s, 16
  #      devices, seeds 4 then 5, EP-G + per-frame, labelled rq30
  #  (5) baselines fill gaps (below)
  # user queue change 2026-11-21 ~11:10: FULL v5 cells pre-empt everything once flash posts $OUT/V5FULL_CELLS ("arm n seed
  # tag" per line) WITH the cost-model gate passed
  # D172 (user, ~18:45): the full policy's cells are posted as $OUT/V6_CELLS (spec v6 names: covex-v6-base, -rules, -state,
  # -fair, covex-v6), REPLACING V5FULL_CELLS, under the same release conditions; both are read so neither name is missed
  # OVERNIGHT brief (user, ~18:50): flash's V6STATE_CELLS, V6FAIR_CELLS and V6_CELLS each run at the next boundary AHEAD
  # of the remaining baselines, seeds 4-7; covex-v6 (V6_CELLS) FIRST if several are pending, then the ladder order
  # (state, fair). A line "arm n seed tag" is taken as is; a bare arm name expands to 16 devices, seeds 4-7, _L3_epg_rq30.
  # user ruling ~19:15 (harm_warm from the D162 cost model, never a declared grid value; pre-registered first): a v6 /
  # full-policy cell list is read ONLY when the operator has checked it and recorded "<file> <sha256>" in the LOCAL,
  # gitignored $OUT/V6_GATE_OK; if the posted file changes after the check, its hash no longer matches and it is ignored
  # user addendum ~10:45 (RESOLVE C5 FIRST), order: (1) V6STATE_CELLS seeds 4 and 5; (2) C5DIAG_CELLS (gated like the v6
  # lists; covex-v6-state-uo-c5attr s4 / s5, then the engine-flag-diagnostic cells); (3) V6STATE_CELLS seeds 6 and 7, then
  # the other v6 lists; (4) the matrix tail, then the _kv0.5 memory cells (below).
  _gated() { [ -s $OUT/$1 ] && grep -qx "$1 $(sha256sum $OUT/$1 | cut -c1-64)" $OUT/V6_GATE_OK 2>/dev/null; }
  _lines() { grep -v '^#' $OUT/$1 | awk 'NF>=3 {print $1, $2, $3, $4} NF==1 {for (s=4; s<=7; s++) print $1, 16, s, "_L3_epg_rq30"}'; }
  # user addendum ~12:40: the moment flash posts the D179 shares list with proofs passed (and it is gated), the SHARES
  # cells take priority over anything not yet started, s4 first then s5, s6, s7
  # D187 OVERNIGHT (user, ~18:10): any OTHER list the operator gates in V6_GATE_OK (shares-r1, rung-3, rung-4 from flash)
  # runs FIRST, in gate-file order, each sorted by seed; the gate (posted hash + proofs) is still the operator's check
  for f in $(awk '{print $1}' $OUT/V6_GATE_OK 2>/dev/null | grep -vxE "V6SHARES_CELLS|V6STATE_CELLS|C5DIAG_CELLS|V6_CELLS|V6FAIR_CELLS|V5FULL_CELLS"); do _gated $f && _lines $f | sort -s -k3,3n; done
  _gated V6SHARES_CELLS && _lines V6SHARES_CELLS | sort -s -k3,3n
  _gated V6STATE_CELLS && _lines V6STATE_CELLS | awk '$3==4 || $3==5'
  # C5DIAG_CELLS also carries c5attr s6 / s7 when flash adds them (user addendum ~12:40): ahead of the matrix tail
  _gated C5DIAG_CELLS && _lines C5DIAG_CELLS
  _gated V6STATE_CELLS && _lines V6STATE_CELLS | awk '$3!=4 && $3!=5'
  for f in V6_CELLS V6FAIR_CELLS V5FULL_CELLS; do _gated $f && _lines $f; done
  grep -v '^#' $OUT/RERUN_CELLS 2>/dev/null | awk 'NF>=3 {print $1, $2, $3, $4}'
  local v5r2=$(grep -v '^#' $OUT/V5RULES2_CELLS 2>/dev/null | awk 'NF>=1 {print $1}' | sort -u | tr '\n' ' ')
  local rq=""; [ -s $OUT/RQ30_ARGS ] && [ -s $OUT/EPG_ARGS ] && rq=1
  # user queue change 2026-11-21 ~09:40: once flash posts V5RULES2_CELLS (with its seven proofs), at the next boundary,
  # PRE-EMPTING the load sweep: (1) v5-rules-2 and hybrid-F-lhreq-noc3 PAIRED at seeds 4, 5, 6, 7; (2) b7, mooncake, llf,
  # warm-all-lru at seeds 4 to 7; (3) the rest of the rq30 block (eco-llm, edf at 4 to 7; old v5-rules at 4 and 5 ONLY, the
  # ablation ladder, its seeds 6 and 7 dropped). Then the load sweep resumes. Robot results PROVISIONAL until the Orin's
  # REASK device answers for that seed are joined.
  # D164 (user, ~13:00): (1) finish the seed-5 load sweep; (2) the host-offload verification break (offload_verify_break.sh);
  # (3) then flash's $OUT/BASELINE_MATRIX IN ITS ORDER ("arm n seed tag" per line; paper core seeds 4-7 first). Cascade
  # arms and kvflow join when flash marks them ready, i.e. uncomments their lines. The rq30 v5-rules-2 / noc3 cells at
  # seeds 4-6 already run are REUSED (a finished cell is never rerun). Until BASELINE_MATRIX lands, the v15 order below
  # keeps GPU 2 busy.
  if [ -s $OUT/BASELINE_MATRIX ]; then
    for s in 4 5 6; do for x in $v5r2 hybrid-F-lhreq-noc3; do echo "$x 16 $s _L3_epg_rq30"; done; done
    grep -v '^#' $OUT/LOADSWEEP_CELLS 2>/dev/null | awk 'NF>=4 {print $1, $2, $3, $4}'
    # user ruling ~16:15 (D169): the margin population is the healthy-window robot questions of the rq30 v5-rules-2 /
    # noc3 PAIR at seeds 4-7, so the seed-7 pair runs IN the paper core, at its front (it appears again later in the
    # matrix; a finished cell is never rerun)
    for x in $v5r2 hybrid-F-lhreq-noc3; do echo "$x 16 7 _L3_epg_rq30"; done
    grep -v '^#' $OUT/BASELINE_MATRIX | awk 'NF>=4 {print $1, $2, $3, $4}'
    # user ruling ~09:00 (E5 memory sweep): when BASELINE_MATRIX has no runnable lines left, run the paper core at HALF
    # GPU KV memory (the committed _kv0.25 pool-fraction mechanism: _kv0.5 -> --gpu-kv-tokens 31472), seeds 4 and 5, same
    # workload, and then NOTHING older: the old gap-fill tags are dropped (D170). covex-v6 rung lists above still pre-empt.
    for s in 4 5; do for x in covex-v6-base covex-v6-rules edf llf b7-edf-feasibility always-cloud-fcfs mooncake \
        attentionstore-prefetch simplestream querystream-proactive warm-all-lru; do echo "$x 16 $s _kv0.5_L3_epg_rq30"; done; done
    return 0
  elif [ -n "$rq" ] && [ -n "$v5r2" ]; then
    for s in 4 5 6; do for x in $v5r2 hybrid-F-lhreq-noc3; do echo "$x 16 $s _L3_epg_rq30"; done; done
    # queue change ~12:30: after noc3 s6, the load sweep's seed-5 cells NEXT (they unblock the D162 gate for full v5),
    # THEN the v5-rules-2 / noc3 pair at seed 7, then b7, mooncake, llf, warm-all-lru
    grep -v '^#' $OUT/LOADSWEEP_CELLS 2>/dev/null | awk 'NF>=4 {print $1, $2, $3, $4}'
    for x in $v5r2 hybrid-F-lhreq-noc3; do echo "$x 16 7 _L3_epg_rq30"; done
    for s in 4 5 6 7; do for x in b7-edf-feasibility mooncake llf warm-all-lru; do echo "$x 16 $s _L3_epg_rq30"; done; done
    for s in 4 5; do echo "v5-rules 16 $s _L3_epg_rq30"; done
    for s in 4 5 6 7; do for x in eco-llm edf; do echo "$x 16 $s _L3_epg_rq30"; done; done
  fi
  grep -v '^#' $OUT/LOADSWEEP_CELLS 2>/dev/null | awk 'NF>=4 {print $1, $2, $3, $4}'
  # without v5-rules-2 yet: the rq30 block after the sweep (D159 order), old v5-rules at seeds 4 and 5 only
  if [ -n "$rq" ] && [ -z "$v5r2" ]; then
    for s in 4 5 6 7; do for x in hybrid-F-lhreq-noc3 b7-edf-feasibility mooncake llf warm-all-lru eco-llm edf; do
      echo "$x 16 $s _L3_epg_rq30"; done; [ $s -le 5 ] && echo "v5-rules 16 $s _L3_epg_rq30"; done
  fi
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

log "frozen grid driver v39 (v37 + D244 _out-k<K>-d<D> tag -> outage harness flags, asserted pre-launch and checked live) start, HEAD $(git rev-parse --short HEAD)"
while true; do
  [ -f $OUT/STOP ] && { log "STOP file found: driver exits at a run boundary"; exit 0; }
  git fetch -q 2>/dev/null
  git log origin/main --format=%s -400 | grep -q "^policy-F6 fast" && [ ! -f $OUT/F6_FAST ] && { touch $OUT/F6_FAST; log "policy-F6 fast on origin: hybrid-F6 at 20 joins in order"; }
  next=""
  while read a n s tag; do
    [ -z "$a" ] && continue
    name=${a}_n${n}_s${s}_${RUN_S}s_h27_3t${tag}
    grep -qx "$name" $OUT/SKIPPED 2>/dev/null && continue
    # user ruling 2026-11-21 ~14:45: arms that WAIT for the device answer do NOT run on the 0.567 s proxy; HELD, at any
    # tag, until flash wires the measured Orin warm latency into their live wait and lists the arm in $OUT/DEVWAIT_READY
    case "$a" in confidence-cascade|cascade-routing|r3-streaming|streamscout|thinking-qwenvl)
      grep -qx "$a" $OUT/DEVWAIT_READY 2>/dev/null || continue;; esac
    # user ruling ~16:15: older-tag gap-fill cells of r3-streaming and streamscout are DROPPED (not the final workload);
    # only their BASELINE_MATRIX cells (_L3_epg_rq30) count
    case "$a" in r3-streaming|streamscout) [ "$tag" = "_L3_epg_rq30" ] || continue;; esac
    [ -f $OUT/$name/cell.json ] && [ "$(jq -r '(.err==null) and (.run_valid==true) and (.digests_equal==true)' $OUT/$name/cell.json)" = "true" ] && continue
    [ -f $OUT/${name}_rerun/cell.json ] && continue
    next="$a $n $s $tag"; break
  done < <(ordered_cells)
  if [ -z "$next" ]; then
    if [ -s $OUT/TOP5 ]; then log "SWEEP DONE (all queued cells run)"; echo DONE > $OUT/STATUS; exit 0; fi
    # D187: never exit on an empty queue overnight; poll every 5 min so a newly gated list starts without an operator
    [ -f $RAW/driver_idle ] || log "sweep: nothing runnable now; driver polls every 5 min for newly gated lists (D187)"; touch $RAW/driver_idle; sleep 300; continue
  fi
  set -- $next
  tg=${4:-}
  t0=$(date +%s)
  v=$(cell $1 $2 $3 "$tg")
  # v29 (2026-11-22 ~22:50, after origin/main's arms.py stopped importing and v28 auto-skipped five cells that never
  # ran): a cell that ends with no cell.json within 120 s never reached its workload, which is an INFRASTRUCTURE
  # failure (import error, preflight refusal), not a property of the cell. Do NOT rerun it and do NOT record it in
  # SKIPPED: log it, set STOP plus the watchdog's HOLD, and exit, so the queue is not burned and an operator fixes it.
  # v39 (D244): a D244 refusal (excluded arm / outage args) or a VOID outage stop is a recorded SKIP of ONE cell,
  # not an infrastructure failure, so it must not stop the whole queue; every other case is unchanged from v37.
  if [ "$(echo "$v" | jq -r .valid)" != "true" ] && [ $(( $(date +%s) - t0 )) -lt 120 ] && [ ! -f $OUT/${1}_n${2}_s${3}_${RUN_S}s_h27_3t${tg}/cell.json ] && ! echo "$v" | jq -e '.skipped == "outage-args-mismatch" or .skipped == "excluded-arm-d244"' >/dev/null 2>&1 && [ ! -f $RAW/runs/${1}_n${2}_s${3}_${RUN_S}s_h27_3t${tg}/VOID_OUTAGE_STOP ]; then
    log "INFRASTRUCTURE FAILURE (no cell.json within $(( $(date +%s) - t0 )) s): $(echo "$v" | jq -c '{name, err, rc}'); NOT rerun, NOT skipped; STOP + HOLD set, driver exits. stdout tail: $(tail -1 $OUT/${1}_n${2}_s${3}_${RUN_S}s_h27_3t${tg}.stdout 2>/dev/null | cut -c1-200)"
    touch $OUT/STOP; mkdir -p $HOME/data/live2/watchdog; echo "infrastructure failure $(date '+%F %T') on ${1} s${3}" > $HOME/data/live2/watchdog/HOLD
    commit_cell "infrastructure failure, $1 at $2 devices, seed $3 (no cell.json; driver stopped)"; exit 1
  fi
  if [ "$(echo "$v" | jq -r .valid)" != "true" ]; then
    log "INVALID, rerun once: $(echo "$v" | jq -c '{name, err, run_valid, n_errors}')"
    v=$(cell $1 $2 $3 "${tg}_rerun")
    [ "$(echo "$v" | jq -r .valid)" != "true" ] && { log "INVALID TWICE: skipped and recorded"; echo "${1}_n${2}_s${3}_${RUN_S}s_h27_3t${tg}" >> $OUT/SKIPPED; }
  fi
  commit_cell "$1 at $2 devices, seed $3${tg:+ ($tg)}"
  rm -f $RAW/driver_idle
done
