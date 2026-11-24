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
      tw=$(echo "$c" | sed -E 's/_kv0\.25//; s/_kv0\.5r//; s/_c[0-9]+-[0-9]+-[0-9]+//; s/_L[0-9.]+_/_L3_/; s/_rq[0-9]+$/_rq30/; s/_n(8|12|20|24)_/_n16_/; s/^covex-v6-base_/hybrid-F-lhreq-noc3_/; s/^covex-v6-rules_/v5-rules-2_/')
      [ -f $O/$tw/cell.json ] || tw=${tw}_rerun; [ -f $O/$tw/cell.json ] && [ "$tw" != "$c" ] || tw=""
      echo "[$(date '+%F %T')] $(nice -n 19 bash experiments/orchestration/proof_load_annotate.sh $c $tw 2>&1 | tail -1)" >> $HOME/data/live2/proofs/annotate.log
      # EVAL_PLAN: record each newly generated trace's digests once, and commit them
      nice -n 19 bash experiments/orchestration/trace_digests.sh >/dev/null 2>&1
      git add results/orchestration/live2/frozen_test/trace_digests.jsonl && git commit -q -m "trace digests (EVAL_PLAN)" >/dev/null 2>&1 && { timeout 60 git pull --rebase -q origin main; timeout 60 git push -q; } >/dev/null 2>&1
    done
    seen=$n
  fi
  sleep 30
done
