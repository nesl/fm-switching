#!/usr/bin/env bash
# Extract benchmark archives. Originals are KEPT; nothing is deleted or re-encoded.
set -u
R=/mnt/ssd/hf_models/datasets
MIN_FREE_GB=50

freegb() { df --output=avail -BG "$R" | tail -1 | tr -dc '0-9'; }
guard() { f=$(freegb); if [ "$f" -lt "$MIN_FREE_GB" ]; then echo "STOP: free ${f}GB < ${MIN_FREE_GB}GB"; exit 3; fi; }

echo "=== OVO-Bench: concatenate src_videos parts and untar ==="
guard
mkdir -p "$R/ovo_bench/src_videos"
if [ -z "$(ls -A "$R/ovo_bench/src_videos" 2>/dev/null)" ]; then
  cat "$R"/ovo_bench/hf/src_videos.tar.parta* | tar -xf - -C "$R/ovo_bench/src_videos" && echo "OVO ok"
else echo "OVO already extracted, skipping"; fi

echo "=== HERBench: concatenate videos.tar parts and untar ==="
guard
mkdir -p "$R/herbench/extracted"
if [ -z "$(ls -A "$R/herbench/extracted" 2>/dev/null)" ]; then
  cat "$R"/herbench/hf/videos/videos.tar.part.* | tar -xf - -C "$R/herbench/extracted" && echo "HER ok"
else echo "HERBench already extracted, skipping"; fi

echo "=== StreamingBench: unzip each archive, upstream layout ==="
mkdir -p "$R/streaming_bench/extracted"
for z in "$R"/streaming_bench/hf/*.zip; do
  guard
  echo "  unzip: $(basename "$z")"
  unzip -n -q "$z" -d "$R/streaming_bench/extracted" || echo "  UNZIP FAILED: $z"
done
echo "SB ok"

echo "=== RTV-Bench: no archives (plain .mp4 in hf/videos) ==="
find "$R/rtv_bench/hf/videos" -name '*.mp4' | wc -l

echo "=== free after extraction: $(freegb) GB ==="
