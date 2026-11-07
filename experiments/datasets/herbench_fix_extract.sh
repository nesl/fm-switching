#!/usr/bin/env bash
# HERBench videos.tar is a nested split: parts 00-03 are a COMPLETE Lite tar whose
# end-of-archive marker sits mid-stream (see videos/videos_lite_info.txt). Plain
# `tar -xf` therefore stops after 68 videos. -i / --ignore-zeros reads past it.
set -u
R=/mnt/ssd/hf_models/datasets/herbench

echo "=== verify published sha256 checksums ==="
cd "$R/hf/videos" && sha256sum -c videos.tar.checksums.txt
echo "checksum exit=$?"

echo "=== re-extract FULL with --ignore-zeros ==="
mkdir -p "$R/extracted_full"
cat "$R"/hf/videos/videos.tar.part.* | tar -xif - -C "$R/extracted_full"
echo "tar exit=$?"
echo "videos extracted: $(find "$R/extracted_full" -type f -name '*.mp4' | wc -l)"
du -sh "$R/extracted_full"
