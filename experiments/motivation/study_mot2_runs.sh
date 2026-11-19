#!/bin/bash
# StudyMOT2-dayinlife (pre-registered cffdbb2): edf, 12 devices 50:50, mode A, 600 s, seeds 9 and 10, round-1 server
# (27 GiB host) restarted before each run, FINAL calibration, decision period 100 ms. HF token read from file, never printed.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
OUT=results/motivation/mot2/runs; mkdir -p $OUT
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
for seed in 9 10; do
  d=$OUT/seed$seed
  echo "[$(date +%T)] start seed $seed HEAD $(git rev-parse --short HEAD)" >> results/motivation/mot2/mot2.log
  ~/.venvs/fm-switching-vllm/bin/python experiments/orchestration/live2/run_live2_real.py --arm edf --n-devices 12 \
    --ratio 50:50 --mode A --run-s 600 --seed $seed --host-tier-gib 27 --calibration $CAL --decision-period-s 0.1 \
    --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
    --work $HOME/data/live2/mot2/work --label "StudyMOT2-dayinlife seed $seed (motivation measurement)" \
    --server http://127.0.0.1:8031 --server-kind vllm --start-server --out $d > $d.stdout 2>&1
  echo "[$(date +%T)] end seed $seed rc=$? $(jq -c '{p99:.lateness.p99_ms, run_valid, digests_equal, n_requests, n_errors, err}' $d/cell.json 2>/dev/null)" >> results/motivation/mot2/mot2.log
done
echo "[$(date +%T)] MOT2 RUNS DONE" >> results/motivation/mot2/mot2.log
