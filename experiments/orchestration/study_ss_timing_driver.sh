#!/bin/bash
# SS timing (D142 item 4): idle, then injected into b7 background runs at 12 and 16 devices (50:50, push-all, seed 0).
# Robots: LH-REQ if "lh-req ready" is on origin when the background starts, else MIXED (labelled). The injector starts
# only after the background run is deciding (past its GPU-exclusivity preflight).
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
PY=$HOME/.venvs/fm-switching-vllm/bin/python
LOG=results/orchestration/live2/ss_timing/ss_timing.log; mkdir -p results/orchestration/live2/ss_timing $HOME/data/ss_timing/runs
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
until grep -q "SS1-32B RUN EXIT" <(tail -n 3 results/casestudy/study_ss1/ss1_cloud32b_run.log) 2>/dev/null; do sleep 5; done
while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
log "SS timing start, HEAD $(git rev-parse --short HEAD)"
$PY experiments/orchestration/live2/ss_timing.py idle >> $LOG 2>&1; log "idle exit $?"
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
for n in 12 16; do
  git fetch -q; ROB=MIXED; git log origin/main --format=%s -400 | grep -q "^lh-req ready" && ROB=LHREQ
  [ "$ROB" = LHREQ ] && { log "lh-req ready found but the LH-REQ runner flag is not wired here yet: using MIXED and labelling it"; ROB=MIXED; }
  name=ss_bg_b7_n${n}_s0_${ROB}; d=$HOME/data/ss_timing/runs/$name
  [ -e $d ] && mv $d ${d}_prev_$(date +%s)
  while [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c 4f1d7e47)" != "0" ]; do sleep 2; done
  log "start background $name (robots $ROB)"
  $PY experiments/orchestration/live2/run_live2_real.py --arm b7-edf-feasibility --n-devices $n --run-s 600 --host-tier-gib 27 \
    --seed 0 --ratio 50:50 --mode A --calibration $CAL --decision-period-s 0.1 --mu-mode ewma --h-s 0.5 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $HOME/data/ss_timing/work --server http://127.0.0.1:8031 --server-kind vllm --start-server \
    --label "SS_TIMING_BACKGROUND_NOT_A_GRID_CELL $name" --out $d > $d.stdout 2>&1 &
  RP=$!
  until [ -s $d/decision.jsonl ] || ! kill -0 $RP 2>/dev/null; do sleep 1; done
  if kill -0 $RP 2>/dev/null; then $PY experiments/orchestration/live2/ss_timing.py inject ${name} $d >> $LOG 2>&1; fi
  wait $RP; log "background $name exit $? ; $(jq -c '{run_valid, n_errors, dash:.score.score.sweep[0].dashcam_all_meet}' $d/cell.json 2>/dev/null)"
  mkdir -p results/orchestration/live2/ss_timing/runs; cp $d/cell.json results/orchestration/live2/ss_timing/runs/$name.cell.json 2>/dev/null
done
log "SS TIMING DONE"
