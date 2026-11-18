#!/bin/bash
cd /home/pragya/Desktop/fm-switching/experiments/orchestration/live2
PY=~/.venvs/fm-switching-vllm/bin/python
S=/tmp/claude-1009/-home-pragya-Desktop/0a38779b-3a70-47f4-92f9-ae7f8486a4e0/scratchpad/d110
snap() { # tag cpu
  local sib=$(( ($2 + 64) % 128 ))
  a=$(grep -E "^cpu($2|$sib) " /proc/stat); sleep 3; b=$(grep -E "^cpu($2|$sib) " /proc/stat)
  u=$(paste <(echo "$a") <(echo "$b") | awk '{t1=0;for(i=2;i<=11;i++)t1+=$i; i1=$5+$6; t2=0;for(i=13;i<=22;i++)t2+=$i; i2=$16+$17; printf "%s=%.0f%% ", $1, 100*(1-(i2-i1)/(t2-t1))}')
  echo "$1 $(date +%T) $(uptime | sed 's/.*load average: /loadavg /') | $u| $(ps -eo user,pcpu,psr,comm --sort=-pcpu | sed -n '2,5p' | awk '{u=$1; if(u!="pragya"&&u!="root")u="other"; printf "%s:%s%%@cpu%s ", u, $2, $3}')" >> $S/pinned_load.log
}
for cell in "idle 50 32" "idle 50 64" "shared 26 32" "shared 26 64"; do
  set -- $cell
  snap "before $1 n$3 cpu$2" $2
  taskset -c $2 $PY fix_checks.py speed --out $S/pin_$1_n$3 --window-s 180 --sizes $3 >> $S/pinned_run.log 2>&1
  snap "after  $1 n$3 cpu$2" $2
done
echo "PINNED DONE $(date +%T)" >> $S/pinned_load.log
