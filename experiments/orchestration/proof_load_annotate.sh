#!/bin/bash
# D209 per-cell proof-load record (user ruling, 2026-11-23). For every cell that ends, writes into its
# cell.json a block "proof_load_d209":
#   proof_ran            any proof_guard.sh sample inside the cell's host_load window
#   proof_peak_cores     max summed proof CPU (cores) in that window (sum over concurrent proofs per 5 s slot)
#   host_load_peak       max loadavg_1m and max other_cpu_cores from the cell's own host_load.jsonl.gz (D115)
#   decision_p99_ms      p99 of decision_time.jsonl.gz wall_ms; twin's value and the ratio
#   flags                proof_cores_gt_8, decision_p99_up_gt_10pct
# and commits cell.json alone. Runs 120 s after the NEXT cell's start, so no jq runs at a boundary.
# Usage: proof_load_annotate.sh <cell_name> [twin_cell_name]
set -u
cd /home/pragya/Desktop/fm-switching
O=results/orchestration/live2/frozen_test/runs; PL=$HOME/data/live2/proofs; c=$1; tw=${2:-}
d=$O/$c; [ -f $d/cell.json ] || { echo "no cell.json for $c"; exit 1; }
jq -e '.proof_load_d209' $d/cell.json >/dev/null 2>&1 && { echo "already annotated: $c"; exit 0; }
p99() { zcat -f $1/decision_time.jsonl* 2>/dev/null | jq -s '[.[].wall_ms] | sort | if length == 0 then null else .[((length * 0.99) | floor)] end'; }
read t0 t1 la oc < <(zcat -f $d/host_load.jsonl* | jq -s -r '[(map(.t)|min), (map(.t)|max), (map(.loadavg_1m)|max), (map(.other_cpu_cores)|max)] | @tsv')
pp=0; pr=false
if [ -f $PL/proof_load.jsonl ]; then
  pp=$(jq -s --argjson a $t0 --argjson b $t1 '[.[] | select(.event == "sample" and .t >= $a and .t <= $b)] | group_by((.t / 5) | floor) | map(map(.cores) | add) | max // 0' $PL/proof_load.jsonl)
  n=$(jq -s --argjson a $t0 --argjson b $t1 '[.[] | select(.event == "sample" and .t >= $a and .t <= $b)] | length' $PL/proof_load.jsonl)
  [ "$n" -gt 0 ] && pr=true
fi
mp=$(p99 $d); tp=null; [ -n "$tw" ] && [ -d $O/$tw ] && tp=$(p99 $O/$tw)
blk=$(jq -n --argjson pr $pr --argjson pp $pp --argjson la $la --argjson oc $oc --argjson mp ${mp:-null} --argjson tp ${tp:-null} --arg tw "$tw" '
  {proof_ran: $pr, proof_peak_cores: $pp, host_load_peak: {loadavg_1m: $la, other_cpu_cores: $oc},
   decision_p99_ms: $mp, twin: (if $tw == "" then null else $tw end), twin_decision_p99_ms: $tp,
   decision_p99_ratio: (if ($mp != null and $tp != null and $tp > 0) then (($mp / $tp) * 1000 | round / 1000) else null end),
   flags: {proof_cores_gt_8: ($pp > 8),
           decision_p99_up_gt_10pct: (if ($mp != null and $tp != null and $tp > 0) then ($mp > 1.10 * $tp) else null end)},
   reportable: ($pr and (($pp > 8) or (if ($mp != null and $tp != null and $tp > 0) then ($mp > 1.10 * $tp) else false end))),
   twin_note: "the twin is the committed 16-device 3 s 1x cell of the same arm and seed (for covex-v6-base / covex-v6-rules it is that arm under its committed name, hybrid-F-lhreq-noc3 / v5-rules-2, per arm_names_v6.OLD_TO_RUNG), so for a 0.25x, 2.5 s or 12/20-device cell the p99 ratio also carries the condition; only a cell with proof_ran = true is reported",
   rule: "D209 user ruling 2026-11-23 option 2: proofs unpinned, nice 19, <= 2, never across a boundary"}')
jq --argjson b "$blk" '. + {proof_load_d209: $b}' $d/cell.json > $d/cell.json.tmp && mv $d/cell.json.tmp $d/cell.json
echo "$c $(echo "$blk" | jq -c '{proof_ran, proof_peak_cores, host_load_peak, decision_p99_ms, twin_decision_p99_ms, decision_p99_ratio, flags, reportable}')"
git add $d/cell.json && git commit -q -m "proof-load record (D209): $c" && { timeout 60 git pull --rebase -q origin main; timeout 60 git push -q; } >/dev/null 2>&1
