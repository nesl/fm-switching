#!/bin/bash
# StudySH-EP (D145) on H100 GPU 2: 32BI ONLY (user correction 2026-11-20), the kit's conditions in the kit's order, one
# request at a time, each condition pushed as "StudySH-EP-32B <condition>" when it finishes. Header: the committed count
# header for C1 (single frame), the count-free header for every multi-frame condition (user ruling, item 1). Controls:
# the kit's greys in every invocation and the shuffled-context control (C6, EP-G). --store is a link view of the D91 store
# under the kit's flat file names (the store on this host is laid out frames/<clip>/t<t>.jpg; every link resolves).
cd /home/pragya/Desktop/fm-switching
O=results/dashcam/study_sh_ep/h100
LOG=$O/sh_ep_h100_driver.log
VIEW=/home/pragya/data/live2/jpeg/nexar_q90_sh_ep_view
log() { echo "[$(date '+%F %T')] $*" >> $LOG; }
for c in C1 C3 C6 EP-B EP-G; do
  [ -f $O/STOP ] && { log "STOP file found: exits before $c"; exit 0; }
  hm=constant; [ $c = C1 ] && hm=count
  out=$O/sh_ep_requests_32BI_shep1-$c.jsonl
  log "start $c header=$hm"
  ~/.venvs/fm-switching-vllm/bin/python -I experiments/dashcam/sh_ep_runner.py --base http://127.0.0.1:8031 --model 32BI \
    --store $VIEW --run-tag shep1-$c --conditions $c --shuffle-control --header-mode $hm --out $out >> $LOG 2>&1
  rc=$?
  n=$(wc -l < $out); e=$(jq -r 'select(.error) | 1' $out | wc -l); nb=$(jq -r 'select(.neither) | 1' $out | wc -l)
  ca=$(jq -r 'select(has("cached_tokens")|not) | 1' $out | wc -l)
  log "end $c rc=$rc records=$n errors=$e neither=$nb cached_tokens_absent=$ca"
  gzip -kf $out
  git add $out.gz $O/sh_ep_h100_driver.log results/dashcam/study_sh_ep/sh_ep_run_meta_32BI_shep1-$c.json 2>/dev/null
  git commit -q -m "StudySH-EP-32B $c" 2>/dev/null
  for i in 1 2 3; do git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null && break; sleep 5; done
  log "pushed $c ($(git rev-parse --short HEAD))"
  [ $rc -ne 0 ] && { log "runner rc=$rc: STOP"; exit 1; }
  # kit section 7 STOP conditions on this condition's records: > 1 percent failing or neither, cached_tokens absent everywhere
  awk -v n=$n -v e=$e -v nb=$nb 'BEGIN{exit !((e/n > 0.01) || (nb/n > 0.01))}' && { log "STOP: errors $e or neither $nb above 1 percent of $n"; exit 1; }
  [ "$ca" = "$n" ] && { log "STOP: cached_tokens absent from every record"; exit 1; }
done
log "ALL CONDITIONS DONE"
