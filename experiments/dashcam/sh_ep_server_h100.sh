#!/bin/bash
# StudySH-EP (D145): the round-1 32B server on H100 GPU 2, fresh start. The command is the round-1 live2 server's
# command byte for byte (prefix caching ON via the later --enable-prefix-caching, mm processor cache 128 GB, image cap
# 640, the round-1 mm-processor-kwargs, native KV offloading 27 GiB), with ONE addition: the model's HF id as a second
# served name, because the kit runner sends model="Qwen/Qwen3-VL-32B-Instruct".
set -u
LOG=${1:?log path}
SNAP=/home/pragya/.cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/0cfaf48183f594c314753d30a4c4974bc75f3ccb
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=2 VLLM_USE_FLASHINFER_SAMPLER=0
exec /home/pragya/.venvs/fm-switching-vllm/bin/vllm serve $SNAP --served-model-name 32BI Qwen/Qwen3-VL-32B-Instruct \
  --port 8031 --max-model-len 32768 --gpu-memory-utilization 0.9 --tensor-parallel-size 1 --no-enable-prefix-caching \
  --limit-mm-per-prompt '{"image": 16}' --dtype bfloat16 --seed 0 --limit-mm-per-prompt '{"image": 640, "video": 1}' \
  --mm-processor-kwargs '{"size": {"shortest_edge": 4096, "longest_edge": 16777216}, "fps": 1.0, "do_sample_frames": false}' \
  --trust-request-mm-kwargs --host 127.0.0.1 --enable-prefix-caching --enable-prompt-tokens-details \
  --mm-processor-cache-gb 128 --kv-offloading-backend native --kv-offloading-size 27 --enable-log-requests \
  --enable-logging-iteration-details > $LOG 2>&1
