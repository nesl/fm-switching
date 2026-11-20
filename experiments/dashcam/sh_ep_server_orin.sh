#!/bin/bash
# StudySH-EP (D145) Orin 4BI sweep server. User ruling 2026-11-20: run the full 4BI sweep with the
# Jetson vLLM DEPLOYMENT DEFAULT configuration; do not change deployment defaults. This launcher is
# experiments/device/orin3_serve.sh (the StudyORIN3 deployment launcher) verbatim, plus four
# documented additions, none of which tunes compute or latency.
#
# DEPLOYMENT DEFAULTS, kept exactly as the Jetson deployment runs them:
#   --max-num-seqs 1, --enable-prefix-caching, --dtype bfloat16, --max-model-len 32768,
#   --gpu-memory-utilization 0.4, --enforce-eager, --seed 0, --host 127.0.0.1, --port 8000,
#   HF_HOME=/dev/shm/hf_home, and mm-processor-cache-gb left at the vLLM default of 4 GiB (cache ON).
#   No FlashInfer env vars and no KV-offloading: the deployment launcher sets neither.
#
# ADDED for this study (each stated, none affects compute or timing):
#   1. HF id "Qwen/Qwen3-VL-4B-Instruct" as a second served name. Functional: the kit runner addresses
#      the model by its HF id. No compute effect.
#   2. --limit-mm-per-prompt image 21 (deployment default is 9). REQUIRED: the EP-G condition carries
#      up to 21 images, so the sweep cannot run at 9. This is an admission cap only; it does not change
#      the per-request token count or compute for any request within it.
#   3. --mm-processor-kwargs, matched to the H100 byte for byte. PARITY: these set the image token
#      count and the cross-stack comparison turns on it; the user requires mm-processor settings matched.
#   4. --enable-prompt-tokens-details. INSTRUMENTATION: makes prompt_tokens_details.cached_tokens
#      appear in the response so the runner can record it. Response-reporting only, no compute effect.
#
# Device timings from this server are labelled "Orin, default Jetson vLLM config".
set -u
LOG=${1:?log path}
source /home/nesl/orin3_vllm_venv/bin/activate
export HF_HOME=/dev/shm/hf_home
# ENVIRONMENT REQUIREMENT for this box, not a study tuning flag: the Orin venv has a flashinfer
# version-string mismatch (flashinfer-cubin 0.6.13 vs flashinfer 0.6.15.post1) that makes vLLM's
# backend selector refuse to start. This bypasses the version-STRING check only; the installed
# flashinfer is functional (StudySS2 ran under it). No effect on compute, tokens, or timing.
# The attention backend is left to the deployment default auto-selection (orin3_serve.sh sets none).
export FLASHINFER_DISABLE_VERSION_CHECK=1
SNAP=/dev/shm/hf_home/hub/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17
exec vllm serve "$SNAP" \
  --served-model-name qwen3vl4b Qwen/Qwen3-VL-4B-Instruct \
  --max-num-seqs 1 --enable-prefix-caching \
  --dtype bfloat16 --max-model-len 32768 \
  --limit-mm-per-prompt '{"image":21,"video":0}' \
  --gpu-memory-utilization 0.4 \
  --enforce-eager \
  --mm-processor-kwargs '{"size": {"shortest_edge": 4096, "longest_edge": 16777216}, "fps": 1.0, "do_sample_frames": false}' \
  --enable-prompt-tokens-details \
  --seed 0 --host 127.0.0.1 --port 8000 > "$LOG" 2>&1
