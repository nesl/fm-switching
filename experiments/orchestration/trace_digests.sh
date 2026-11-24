#!/bin/bash
# EVAL_PLAN: every trace the frozen grid uses at seeds 4-7 is generated once per (seed, devices, ratio, condition) by
# run_live2_real.py and reused by every arm (the directory key). This records each trace's digests ONCE, appending only
# directories not yet recorded, to results/orchestration/live2/frozen_test/trace_digests.jsonl. Bash + jq only.
cd /home/pragya/Desktop/fm-switching
T=$HOME/data/live2/frozen_grid/work/traces; D=results/orchestration/live2/frozen_test/trace_digests.jsonl; touch $D
for d in $T/seed[4-7]_n*; do
  [ -f $d/trace.jsonl ] && [ -f $d/trace_meta.json ] || continue; b=$(basename $d)
  grep -q "\"trace_dir\": \"$b\"" $D && continue
  jq -c --arg b "$b" --arg ts "$(sha256sum $d/trace.jsonl | cut -c1-64)" --arg da "$( [ -f $d/device_answers.jsonl ] && sha256sum $d/device_answers.jsonl | cut -c1-64)" \
    '{trace_dir: $b, trace_sha256: $ts, device_answers_sha256_file: $da, fairness_digest, n_dashcam, n_robot, n_assistive, mode, dashcam_format}' \
    $d/trace_meta.json | sed 's/"trace_dir":"\([^"]*\)"/"trace_dir": "\1"/' >> $D
done
echo "$(wc -l < $D) traces recorded"
