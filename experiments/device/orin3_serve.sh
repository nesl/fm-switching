#!/usr/bin/env bash
# StudyORIN3 vLLM server launcher (smoke / runs). Serial: max-num-seqs 1, prefix caching on.
set -u
source /home/nesl/orin3_vllm_venv/bin/activate
export HF_HOME=/dev/shm/hf_home
SNAP=/dev/shm/hf_home/hub/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17
MML="${MAX_MODEL_LEN:-32768}"
GMU="${GPU_MEM_UTIL:-0.4}"
EAGER="${ENFORCE_EAGER:-1}"
EXTRA=()
[ "$EAGER" = "1" ] && EXTRA+=(--enforce-eager)
exec vllm serve "$SNAP" \
  --served-model-name qwen3vl4b \
  --max-num-seqs 1 --enable-prefix-caching \
  --dtype bfloat16 --max-model-len "$MML" \
  --limit-mm-per-prompt '{"image":9,"video":0}' \
  --gpu-memory-utilization "$GMU" \
  "${EXTRA[@]}" \
  --seed 0 --host 127.0.0.1 --port 8000
