set -u
S=/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad
W=$S/d206x_flashD200; W2=$S/d206x_pristine_flashD200
OUT=$S/d200_deliverables/results/orchestration/live2/d200_one_deficit_weight/cells
PY=/home/pragya/miniconda3/envs/fmtk/bin/python
run () { tree=$1; arm=$2; label=$3; runner=$4
  echo "### $label arm=$arm tree=$(basename $tree) load=$(uptime | sed 's/.*load average: //')"
  cd $tree/experiments/orchestration/live2
  timeout 3000 $PY -I $runner --arm $arm --seed 4 --n 16 --run-s 1200 --cutoff-off \
    > $OUT/$label.json 2>$OUT/$label.err || echo "  NONZERO EXIT"
  $PY -c "
import json
try:
    d=json.load(open('$OUT/$label.json')); print('  ->',d['arm'],d['digest'],d['rows'])
except Exception as e:
    print('  -> NO OUTPUT:',e); print(open('$OUT/$label.err').read()[-600:])"
}
run $W  covex-v6-base             F1_base_patched     cf_pd_one_cell.py
run $W  covex-v6-state-uo-c5attr  F3_rung2_patched    cf_pd_one_cell.py
run $W  covex-v6-fair-c5attr      F4_rung3_patched    cf_pd_one_cell.py
run $W  covex-v6-cf-c5attr        F5_rung4_patched    cfr3_one_cell.py
run $W  covex-v6                  F2_v5full_patched   cf_pd_one_cell.py
run $W2 covex-v6                  F2_v5full_PRISTINE  cf_pd_one_cell.py
echo "### ALL CELLS DONE load=$(uptime | sed 's/.*load average: //')"
