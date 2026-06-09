#!/usr/bin/env bash
# Download a small KITTI raw drive sample (~80 MB, ~100 frames, image_02 left color).
# Source: official KITTI raw_data archive, drive 2011_09_26_drive_0001_sync (city scene).
set -euo pipefail

DEST="$(dirname "$0")/frames"
TMP="$(mktemp -d)"
URL="https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_drive_0001/2011_09_26_drive_0001_sync.zip"

mkdir -p "$DEST"
echo "Downloading KITTI drive 0001 sync (~80 MB)..."
curl -L --fail -o "$TMP/drive.zip" "$URL"

echo "Extracting image_02 (left color camera)..."
unzip -q -j "$TMP/drive.zip" "*/image_02/data/*.png" -d "$DEST"

rm -rf "$TMP"
echo "Done. $(ls "$DEST" | wc -l) frames in $DEST"
du -sh "$DEST"
