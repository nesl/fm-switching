#!/usr/bin/env bash
# StreamingBench zips all reuse the sample_N/ namespace, so unzipping them into one
# directory silently drops videos. Upstream README:76-84 groups them into
# real/ omni/ sqa/ proactive/, but the six "omni" tasks each ship sample_1..50 and
# would overwrite each other there. Extract one directory per TASK instead: lossless,
# and still reducible to the upstream grouping. Nothing is renamed or re-encoded.
set -u
R=/mnt/ssd/hf_models/datasets/streaming_bench
mkdir -p "$R/extracted_by_task"
for z in "$R"/hf/*.zip; do
  b=$(basename "$z" .zip)
  task=$(echo "$b" | sed -E 's/_[0-9]+-[0-9]+$//')
  d="$R/extracted_by_task/$task"
  mkdir -p "$d"
  unzip -q -o "$z" -x '__MACOSX/*' -d "$d" || echo "UNZIP FAILED: $z"
  echo "  $(basename "$z") -> $task/"
done
echo "=== per-task video counts ==="
for d in "$R"/extracted_by_task/*/; do
  printf "  %-44s %s\n" "$(basename "$d")" "$(find "$d" -name 'video.mp4' | wc -l)"
done
echo "TOTAL: $(find "$R/extracted_by_task" -name 'video.mp4' | wc -l)"
