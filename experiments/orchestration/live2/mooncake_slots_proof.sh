#!/bin/bash
# Mooncake GPU-warm slots sized to the KV pool (user ruling 2026-11-23): Step 2b proof, ONE SHA, TWO TREES.
#   before = `git archive` of the sha; after = the same archive plus the patched live2/arms_published.py only.
#   Runner: the committed dry recipe, cf_pd_one_cell.py --cutoff-off (posted knobs, 16 devices, seed 4, 1,200 s),
#   ONE dry cell per process, ONE AT A TIME (D216 (1) alone rule), each through proof_guard.sh (nice 19, no GPU,
#   never across a live-run boundary), loadavg recorded as a magnitude per cell.
# Expected: mooncake 1x IDENTICAL (slots 4 = 4); mooncake 0.25x DIFFERENT with capacity_read slots 1; every other
#   arm IDENTICAL at 1x and 0.25x. POSITIVE CONTROL first: covex-v6-base before 1x must read af8befb9420ad86a.
# Usage: mooncake_slots_proof.sh <sha> <patched arms_published.py> <scratch dir> <out json>
set -u
cd /home/pragya/Desktop/fm-switching
SHA=$1; PATCHED=$2; SP=$3; OUTJ=$4
PY=/home/pragya/.venvs/fm-switching-vllm/bin/python
mkdir -p $SP/before $SP/after $SP/cells
[ -f $SP/before/.done ] || { git archive $SHA experiments | tar -x -C $SP/before && touch $SP/before/.done; }
[ -f $SP/after/.done ] || { git archive $SHA experiments | tar -x -C $SP/after && cp $PATCHED $SP/after/experiments/orchestration/live2/arms_published.py && touch $SP/after/.done; }
cmp -s $SP/before/experiments/orchestration/live2/arms_published.py $SP/after/experiments/orchestration/live2/arms_published.py && { echo "after tree NOT patched"; exit 1; }
diff -rq -x __pycache__ $SP/before/experiments $SP/after/experiments | grep -v "arms_published.py" | grep -q . && { echo "trees differ outside the patch"; exit 1; }
one() {   # tree arm kv
  local t=$1 a=$2 k=$3 f=$SP/cells/${1}_${2}_kv${3}.json
  [ -s $f ] && return
  local la0; la0=$(cut -d' ' -f1 /proc/loadavg)
  ( cd $SP/$t/experiments/orchestration/live2 && bash /home/pragya/Desktop/fm-switching/experiments/orchestration/proof_guard.sh 420 "mk_${t}_${a}_kv${k}" -- \
      $PY -I $SP/$t/experiments/orchestration/live2/cf_pd_one_cell.py --arm $a --seed 4 --cutoff-off --kv-scale $k )
  local o=$HOME/data/live2/proofs/mk_${t}_${a}_kv${k}.out
  tail -1 $o | jq -c --arg t $t --arg la0 "$la0" --arg la1 "$(cut -d' ' -f1 /proc/loadavg)" '. + {tree: $t, loadavg_start: ($la0|tonumber), loadavg_end: ($la1|tonumber)}' > $f 2>/dev/null || echo "{\"tree\":\"$t\",\"arm\":\"$a\",\"kv_scale\":$k,\"error\":\"no json; see $o\"}" > $f
}
one before covex-v6-base 1.0
ctl=$(jq -r .digest $SP/cells/before_covex-v6-base_kv1.0.json)
ARMS="mooncake simplestream llf eco-llm confidence-cascade lmcache attentionstore-prefetch kvflow-prefetch b7-edf-feasibility always-cloud-fcfs edf streamscout querystream-proactive warm-all-lru covex-v6-base covex-v6-rules"
for a in $ARMS; do for k in 1.0 0.25; do for t in before after; do one $t $a $k; done; done; done
jq -s --arg ctl "$ctl" --arg sha $SHA '
  def pick(t; a; k): map(select(.tree == t and .arm == a and (.kv_scale|tostring) == (k|tostring))) | .[0];
  . as $all | {label: "mooncake gpu_warm_slots sized to the KV pool: one sha, two trees (user ruling 2026-11-23)", sha: $sha,
   recipe: "cf_pd_one_cell.py --cutoff-off, seed 4, 16 devices, 1200 s, posted knobs; one dry cell per process, one at a time (D216 (1)); interpreter ~/.venvs/fm-switching-vllm (the H100 has no fmtk env)",
   positive_control: {arm: "covex-v6-base", committed: "af8befb9420ad86a", h100_before: $ctl, reproduces_committed: ($ctl == "af8befb9420ad86a")},
   pairs: ([$all[] | {arm, kv_scale}] | unique | map(. as $p | ($all | pick("before"; $p.arm; $p.kv_scale)) as $b | ($all | pick("after"; $p.arm; $p.kv_scale)) as $f
           | {arm: $p.arm, kv_scale: $p.kv_scale, before: {digest: $b.digest, rows: $b.rows}, after: {digest: $f.digest, rows: $f.rows},
              identical: ($b.digest != null and $b.digest == $f.digest), loadavg: [$b.loadavg_start, $f.loadavg_start]})),
   cells: $all}
  | .expected_pass = ([.pairs[] | select((.arm == "mooncake" and .kv_scale == 0.25) | not) | .identical] | all)
  | .mooncake_025_moved = ([.pairs[] | select(.arm == "mooncake" and .kv_scale == 0.25) | (.identical | not)] | all)
  | .verdict = (if .expected_pass and .mooncake_025_moved then "PASS" else "FAIL" end)' $SP/cells/*.json > $OUTJ
jq -c '{verdict, positive_control, mooncake: [.pairs[] | select(.arm == "mooncake")]}' $OUTJ
