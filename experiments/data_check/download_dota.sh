#!/usr/bin/env bash
# DoTA: clone annotation repo, then resumable gdown of the full frame archive; if Drive blocks it,
# try the split-archive folder once. No other source.
set -uo pipefail
DATA=${DATA:-/home/pragya/data/dashcam}
D=$DATA/dota; LOG=$DATA/logs/dota_download.log
mkdir -p "$D/archive" "$D/split"; rm -f "$D/DOWNLOAD_COMPLETE"
[ -d "$D/repo/.git" ] || git clone https://github.com/MoonBlvd/Detection-of-Traffic-Anomaly "$D/repo" >> "$LOG" 2>&1
(cd "$D/repo" && echo "repo commit: $(git rev-parse HEAD)") >> "$LOG"
G=~/.venvs/dashcam/bin/gdown
ok=0
for attempt in 1 2 3; do
  echo "$(date -Is) full-archive attempt $attempt" >> "$LOG"
  if (cd "$D/archive" && $G --continue 1RQp4hOP9X7TW6S3_vbqZvFSkrbbFzrRj >> "$LOG" 2>&1); then ok=1; echo full > "$D/SOURCE"; break; fi
  sleep 60
done
if [ $ok = 0 ]; then
  echo "$(date -Is) full archive failed; trying split archives once" >> "$LOG"
  if (cd "$D/split" && $G --folder --continue https://drive.google.com/drive/folders/1_WzhwZC2NIpzZIpX7YCvapq66rtBc67n >> "$LOG" 2>&1); then ok=1; echo split > "$D/SOURCE"; fi
fi
if [ $ok = 1 ]; then date -Is > "$D/DOWNLOAD_COMPLETE"; echo "$(date -Is) COMPLETE" >> "$LOG"; else echo "$(date -Is) FAILED" >> "$LOG"; exit 1; fi
