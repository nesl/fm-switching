#!/bin/bash
# StudySH-EP step 3, cost under load (D145; pre-registered as reports/study_sh_ep.md section 5b.4): the kit's EP-G and C1
# on the 50 pre-registered shuffle-control clips (25 positive, 25 negative, EVAL), sent one request at a time by the
# unchanged kit runner while the live2 harness runs a 16-device dashcam : robot background under b7-edf-feasibility on
# the pinned round-1 32B server. BACKGROUND (user ruling 2026-11-20, after the two-type 50:50 load at 16 devices saturated
# the engine): the frozen grid's three-type load exactly, 40:40:20 dashcam : LH-REQ robot : SS2 single-shot, tight
# memory 27 GiB, enforcement on, seed 4). The background outlives the client: the client starts only once the background
# has been sending for WARM_S, and is stopped (resumable, recorded as incomplete) if it is still running KILL_MARGIN_S
# before the background ends, so it never straddles a run boundary (the harness preflight refuses on host Python).
# Run tag shep2-load: cache_salt and every image uuid differ from the unloaded shep2 run, so nothing is shared with it.
set -u
cd /home/pragya/Desktop/fm-switching
# GPU 2 for the harness and its exclusivity check, exactly as the frozen-grid driver exports them (without these the
# check defaults to GPU 1 and refuses on another user's job there)
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
RUN_S=${RUN_S:-3000}; WARM_S=${WARM_S:-300}; KILL_MARGIN_S=${KILL_MARGIN_S:-120}
PY=$HOME/.venvs/fm-switching-vllm/bin/python
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
O=results/dashcam/study_sh_ep/h100
NAME=b7-edf-feasibility_n16_s4_${RUN_S}s_h27_3t_shep_load
D=$HOME/data/live2/sh_ep_load/$NAME
LOG=$O/sh_ep_load_driver.log
OUTC=$O/sh_ep_requests_32BI_shep2-load.jsonl
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
mkdir -p $D
[ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" = "0" ] || { log "GPU 2 not idle: STOP"; exit 1; }
log "start background $NAME (run_s $RUN_S), HEAD $(git rev-parse --short HEAD)"
$PY experiments/orchestration/live2/run_live2_real.py --arm b7-edf-feasibility --n-devices 16 --run-s $RUN_S \
  --host-tier-gib 27 --seed 4 --ratio 40:40:20 --robot-question-set lh_req --kv-capacity-enforced --ss-question-set ss2 \
  --mode A --calibration $CAL \
  --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
  --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
  --work $HOME/data/live2/sh_ep_load/work --server http://127.0.0.1:8031 --server-kind vllm --start-server \
  --label "STUDY_SH_EP_LOAD_BACKGROUND $NAME" --out $D > $D.stdout 2>&1 &
BG=$!
# steady state: wait for the background's first request record, then WARM_S more
until [ -s $D/request.jsonl ] || ! kill -0 $BG 2>/dev/null; do sleep 2; done
kill -0 $BG 2>/dev/null || { log "background exited before sending: STOP (see $D.stdout)"; exit 1; }
T0=$(date +%s); log "background sending; client starts in ${WARM_S} s"
sleep $WARM_S
log "client start (EP-G and C1, shuffle_control_clips, run tag shep2-load, served 32BI, greys 0)"
$PY -I experiments/dashcam/sh_ep_runner.py --base http://127.0.0.1:8031 --model 32BI --served-model 32BI \
  --store $HOME/data/live2/jpeg/nexar_q90_sh_ep_view --run-tag shep2-load --conditions EP-G,C1 \
  --clips-from-meta shuffle_control_clips --greys 0 --header-mode constant --out $OUTC >> $LOG 2>&1 &
CL=$!
DEADLINE=$(( T0 + RUN_S - KILL_MARGIN_S ))
while kill -0 $CL 2>/dev/null; do
  if [ $(date +%s) -ge $DEADLINE ]; then kill $CL; log "client STOPPED at the background's end margin: INCOMPLETE ($(wc -l < $OUTC) records)"; break; fi
  sleep 5
done
wait $CL 2>/dev/null; log "client done: $(wc -l < $OUTC) records, errors $(jq -r 'select(.error)|1' $OUTC | wc -l), cached>0 $(jq -r 'select(.cached_tokens>0)|1' $OUTC | wc -l)"
wait $BG; rc=$?
log "background end rc=$rc: $(jq -c '{err, run_valid, digests_equal, n_requests, n_errors}' $D/cell.json 2>/dev/null)"
rm -rf $O/load_background; mkdir -p $O/load_background; cp -r $D $O/load_background/$NAME; cp $D.stdout $O/load_background/
find $O/load_background -type f -size +5M ! -name "*.gz" -exec gzip -9 {} \;
gzip -kf $OUTC
git add $OUTC.gz $LOG $O/load_background experiments/dashcam/sh_ep_load_h100.sh results/dashcam/study_sh_ep/sh_ep_run_meta_32BI_shep2-load.json 2>/dev/null
git commit -q -m "StudySH-EP-32B load: EP-G and C1 on the 50 shuffle-control clips under the frozen grid three-type b7 background at 16 devices (section 5b.4, user ruling)"
for i in 1 2 3; do git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null && break; sleep 5; done
log "pushed ($(git rev-parse --short HEAD))"
