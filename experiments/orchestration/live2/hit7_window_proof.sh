#!/bin/bash
# Hit 7 (user ruling 2026-11-23): SimpleStream's fitted window applied through RecallAction.window_s. ONE SHA, TWO TREES:
#   before = `git archive` of the sha; after = the same plus the patch to baselines/interface.py, live2/cstate.py,
#   live2/coordinator.py and baselines/simplestream_adapted.py ONLY (checked below).
# (1) every other paper arm and reference at 1x: decision digest IDENTICAL (cf_pd_one_cell.py --cutoff-off);
# (2) simplestream: hit7_window_probe.py in both trees; robot frames per RECENT send 6 -> 1 and
#     recent_window_s_sends > 0 only AFTER (the field is read).
# One dry cell per process, ONE AT A TIME (D216 (1)), each through proof_guard.sh; loadavg recorded per cell.
# Usage: hit7_window_proof.sh <sha> <scratch dir holding before/ and after/> <out json>
set -u
cd /home/pragya/Desktop/fm-switching
SHA=$1; SP=$2; OUTJ=$3
PY=/home/pragya/.venvs/fm-switching-vllm/bin/python
mkdir -p $SP/cells
CH=$(diff -rq -x __pycache__ $SP/before/experiments $SP/after/experiments | grep -vE "baselines/interface.py|live2/cstate.py|live2/coordinator.py|baselines/simplestream_adapted.py")
[ -n "$CH" ] && { echo "trees differ outside the patch: $CH"; exit 1; }
run() {   # tree label script args...
  local t=$1 lab=$2; shift 2; local f=$SP/cells/${t}_${lab}.json
  [ -s $f ] && return
  local la0; la0=$(cut -d' ' -f1 /proc/loadavg)
  bash experiments/orchestration/proof_guard.sh 420 "h7_${t}_${lab}" -- $PY -I "$@"
  tail -1 $HOME/data/live2/proofs/h7_${t}_${lab}.out | jq -c --arg t $t --arg l $lab --arg la0 "$la0" --arg la1 "$(cut -d' ' -f1 /proc/loadavg)" \
    '. + {tree: $t, label: $l, loadavg_start: ($la0|tonumber), loadavg_end: ($la1|tonumber)}' > $f 2>/dev/null \
    || echo "{\"tree\":\"$t\",\"label\":\"$lab\",\"error\":\"no json\"}" > $f
}
for t in before after; do run $t probe_simplestream $SP/$t/experiments/orchestration/live2/hit7_window_probe.py simplestream; done
ARMS="simplestream mooncake llf eco-llm confidence-cascade lmcache attentionstore-prefetch kvflow-prefetch b7-edf-feasibility always-cloud-fcfs edf streamscout querystream-proactive warm-all-lru covex-v6-base covex-v6-rules"
for a in $ARMS; do for t in before after; do run $t digest_$a $SP/$t/experiments/orchestration/live2/cf_pd_one_cell.py --arm $a --seed 4 --cutoff-off; done; done
jq -s --arg sha $SHA '
  def get(t; l): map(select(.tree == t and .label == l)) | .[0];
  . as $all | ($all | get("before"; "probe_simplestream")) as $pb | ($all | get("after"; "probe_simplestream")) as $pa |
  {label: "Hit 7: SimpleStream fitted window applied via RecallAction.window_s (one sha, two trees)", sha: $sha,
   recipe: "cf_pd_one_cell.py --cutoff-off and hit7_window_probe.py (same posted knobs), seed 4, 16 devices, 1200 s; one dry cell per process, one at a time (D216 (1)); interpreter ~/.venvs/fm-switching-vllm",
   decision_key_note: "test_hybrid._decision_key = (t, kind, opportunity_ids, representation, defer_s), and the digest serialises decision ROWS, which coordinator._log_decision builds field by field (SC.DecisionRecord); RecallAction / Opportunity are never serialised into a row, so the new optional fields cannot move a digest through serialisation",
   simplestream: {before: $pb, after: $pa,
                  frames_6_to_1: (($pb.robot_request_frames | keys) == ["6"] and ($pa.robot_request_frames | keys) == ["1"]),
                  window_read_only_after: (($pb.recent_window_s_sends // 0) == 0 and ($pa.recent_window_s_sends // 0) > 0)},
   identity: ([$all[] | select(.label | startswith("digest_")) | .label] | unique | map(. as $l | ($all | get("before"; $l)) as $b | ($all | get("after"; $l)) as $f
              | {arm: ($l | ltrimstr("digest_")), before: {digest: $b.digest, rows: $b.rows}, after: {digest: $f.digest, rows: $f.rows},
                 identical: ($b.digest != null and $b.digest == $f.digest), loadavg: [$b.loadavg_start, $f.loadavg_start]})),
   cells: $all}
  | .others_identical = ([.identity[] | select(.arm != "simplestream") | .identical] | all)
  | .verdict = (if .others_identical and .simplestream.frames_6_to_1 and .simplestream.window_read_only_after then "PASS" else "FAIL" end)' $SP/cells/*.json > $OUTJ
jq -c '{verdict, others_identical, simplestream: {frames_6_to_1: .simplestream.frames_6_to_1, window_read_only_after: .simplestream.window_read_only_after, before: .simplestream.before.robot_request_frames, after: .simplestream.after.robot_request_frames}, ss_digest: [.identity[] | select(.arm == "simplestream")]}' $OUTJ
