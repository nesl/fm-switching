#!/bin/bash
# User 2026-11-23: confidence-cascade (D205-fixed) is now a real comparator; record each rerun seed's per-type numbers.
# Appends one row per landed cell to results/orchestration/live2/frozen_test/confidence_cascade_rerun_pertype.jsonl.
# Usage: cc_rerun_pertype.sh <cell_name>   (jq / zcat only)
cd /home/pragya/Desktop/fm-switching
O=results/orchestration/live2/frozen_test/runs; D=results/orchestration/live2/frozen_test/confidence_cascade_rerun_pertype.jsonl; c=$1; d=$O/$c
[ -f $d/cell.json ] || exit 0; touch $D; grep -q "\"cell\":\"$c\"" $D && exit 0
coord() { zcat -f $d/outcomes.jsonl* | jq -s -c --arg p "$1" '[.[] | select((.device_id // "") | startswith($p))] | {n: length, on_time: map(select(.cloud_payload != null and .cloud_payload.on_time)) | length, late: map(select(.cloud_payload != null and (.cloud_payload.on_time | not))) | length, unsent: map(select(.cloud_payload == null)) | length}'; }
mix=$(zcat -f $d/request.jsonl* | jq -s -c 'group_by((.device_id // "?")[0:4]) | map({key: .[0].device_id[0:4], value: length}) | from_entries')
jq -c --arg c "$c" --argjson dash "$(coord dash)" --argjson robo "$(coord robo)" --argjson mix "$mix" '
  .score.score as $s | $s.sweep[0] as $w |
  {cell: $c, seed: .seed, valid: .run_valid, n_requests: .n_requests, n_errors: .n_errors, requests_by_type: $mix,
   robot: {scorer_on_time: $w.robot_pool_on_time, scorer_n: $w.robot_pool_n, coordinator_register: $robo,
           by_deadline: $s.robot_headline.correct_answers_delivered_by_deadline, device_only_floor: $s.device_only.robot_accuracy},
   single_shot: {on_time_2s: $w.ss_pool_on_time, n: $w.ss_pool_n},
   dashcam: {all_meet: $w.dashcam_all_meet, pooled_on_time: (([$w.dashcam_per_device[].on_time] | add) / ([$w.dashcam_per_device[].n_instants] | add) * 10000 | round / 10000),
             per_device_on_time_frac: [$w.dashcam_per_device[] | ((.on_time / .n_instants) * 1000 | round / 1000)], coordinator_register: $dash},
   note: "D205-fixed confidence-cascade rerun (8986f593); robot scorer register is t_delivered; coordinator register is the first-token flag"}' $d/cell.json >> $D
tail -1 $D | jq -c '{seed, robot: "\(.robot.scorer_on_time)/\(.robot.scorer_n)", ss: "\(.single_shot.on_time_2s)/\(.single_shot.n)", dash: .dashcam.pooled_on_time, by: .robot.by_deadline}'
