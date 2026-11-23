set -u
S=/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad
W=$S/ladder_flashD208; C=$S/d208_deliverables/results/orchestration/live2/ladder_final/cells
PY=/home/pragya/miniconda3/envs/fmtk/bin/python
cd $W/experiments/orchestration/live2
run () { arm=$1; label=$2; runner=$3
  echo "### $label arm=$arm load=$(uptime | sed 's/.*load average: //')"
  timeout 3600 $PY -I $runner --arm $arm --seed 4 --n 16 --run-s 1200 --cutoff-off \
    --rows-out $C/$label.rows.json > $C/$label.json 2>$C/$label.err || echo "  NONZERO EXIT"
  $PY -c "
import json
try:
    d=json.load(open('$C/$label.json')); print('  ->',d['arm'],d['digest'],d['rows'])
except Exception as e:
    print('  -> NO OUTPUT:',e); print(open('$C/$label.err').read()[-700:])"
}
run covex-v6-base              A_base              cf_pd_one_cell.py
run covex-v6-rules             A_rules             cf_pd_one_cell.py
run covex-v6-state-uo-c5attr   R2_committed        cf_pd_one_cell.py
run covex-v6-state-final       R2_final            cf_pd_one_cell.py
run covex-v6-fair-final        R3_final            cfr3_one_cell.py
run covex-v6-final             R4_final            cfr3_one_cell.py
echo "### ALL CELLS DONE load=$(uptime | sed 's/.*load average: //')"
