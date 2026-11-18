#!/bin/bash
# StudyLIVE2-harness addendum: one real-32B cell. args: tag arm n [run_s]
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)
tag=$1; arm=$2; n=$3; rs=${4:-120}
OUT=results/orchestration/live2/harness_addendum/$tag; mkdir -p $OUT
git rev-parse HEAD > $OUT/git_head.txt; git diff HEAD -- experiments/orchestration/live2 > $OUT/working_tree.diff
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
~/.venvs/fm-switching-vllm/bin/python experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $rs \
  --seed 0 --ratio 50:50 --mode A --host-tier-gib 27 --calibration $CAL \
  --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref \
  --work $HOME/data/live2/pilot2/work --label "StudyLIVE2-harness addendum $tag (harness check, not a result)" \
  --server http://127.0.0.1:8031 --server-kind vllm --start-server --out $OUT/run > $OUT/stdout.txt 2>&1
echo "rc=$?" > $OUT/DONE
