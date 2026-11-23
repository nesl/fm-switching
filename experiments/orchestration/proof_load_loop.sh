#!/bin/bash
# D209: annotate every cell that ends with its proof-load record, 120 s after the next cell starts.
cd /home/pragya/Desktop/fm-switching
LOG=results/orchestration/live2/frozen_test/frozen_grid.log; O=results/orchestration/live2/frozen_test/runs
seen=$(grep -cE "\] end " $LOG)
while true; do
  n=$(grep -cE "\] end " $LOG)
  if [ "$n" -gt "$seen" ]; then
    grep -E "\] end " $LOG | tail -n $((n - seen)) | grep -oE "\] end [^ ]+" | cut -c7- | while read c; do
      e=$(grep -E "\] end $c " $LOG | tail -1 | cut -c2-20)
      for i in $(seq 1 120); do awk -v t="$e" 'substr($0,2,19) > t' $LOG | grep -qE "\] (start |sweep: nothing)" && break; sleep 5; done
      sleep 120
      tw=$(echo "$c" | sed -E 's/_kv0\.25//; s/_L2\.5_/_L3_/; s/_n12_/_n16_/; s/_n20_/_n16_/; s/^covex-v6-base_/hybrid-F-lhreq-noc3_/; s/^covex-v6-rules_/v5-rules-2_/')
      [ -f $O/$tw/cell.json ] || tw=${tw}_rerun; [ -f $O/$tw/cell.json ] && [ "$tw" != "$c" ] || tw=""
      echo "[$(date '+%F %T')] $(nice -n 19 bash experiments/orchestration/proof_load_annotate.sh $c $tw 2>&1 | tail -1)" >> $HOME/data/live2/proofs/annotate.log
    done
    seen=$n
  fi
  sleep 30
done
