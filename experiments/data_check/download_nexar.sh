#!/usr/bin/env bash
# Resumable download of nexar-ai/nexar_collision_prediction (HF dataset).
# Token: HF_TOKEN env var; if unset, read from the gitignored repo file into the env (never printed/written).
set -uo pipefail
DATA=${DATA:-/home/pragya/data/dashcam}
OUT=$DATA/nexar/hf; LOG=$DATA/logs/nexar_download.log
mkdir -p "$OUT"; rm -f "$DATA/nexar/DOWNLOAD_COMPLETE"
if [ -z "${HF_TOKEN:-}" ] && [ -f /home/pragya/Desktop/fm-switching/hf-token.txt ]; then
  export HF_TOKEN="$(tr -d '[:space:]' < /home/pragya/Desktop/fm-switching/hf-token.txt)"
  echo "$(date -Is) HF_TOKEN taken from repo token file (not printed)" >> "$LOG"
fi
export HF_HUB_ENABLE_HF_TRANSFER=0 HF_HUB_OFFLINE=0
for attempt in 1 2 3 4 5; do
  echo "$(date -Is) attempt $attempt" >> "$LOG"
  if ~/.venvs/dashcam/bin/hf download nexar-ai/nexar_collision_prediction --repo-type dataset \
       --local-dir "$OUT" --max-workers 8 >> "$LOG" 2>&1 \
     && ~/.venvs/dashcam/bin/python -I "$(dirname "$(readlink -f "$0")")/verify_nexar_download.py" "$OUT" >> "$LOG" 2>&1; then
    date -Is > "$DATA/nexar/DOWNLOAD_COMPLETE"; echo "$(date -Is) COMPLETE" >> "$LOG"; exit 0
  fi
  echo "$(date -Is) attempt $attempt failed" >> "$LOG"; sleep 30
done
echo "$(date -Is) FAILED" >> "$LOG"; exit 1
