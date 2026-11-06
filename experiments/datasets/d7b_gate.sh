#!/usr/bin/env bash
# Queue gate around StudyD7b. "on": create ~/.fmnet_latency_active (fmpull refuses while it exists) and stop any dataset
# pull still running (tmux sessions dl*; fmpull resumes with --partial --append-verify), logging what was stopped.
# "off": remove the marker after D7b.
cd /home/pragya/Desktop/fm-switching; LOG=logs/datasets_pull.log
case "$1" in
  on)  date -Is > ~/.fmnet_latency_active
       for s in $(tmux ls -F '#S' 2>/dev/null | grep '^dl'); do
         echo "$(date '+%F %T') PAUSED for StudyD7b: tmux session $s stopped (resumable)" | tee -a $LOG
         tmux kill-session -t "$s"
       done
       sleep 5; pgrep -u "$USER" -f "rsync .*fmnet-flash" && { pkill -u "$USER" -f "rsync .*fmnet-flash"; echo "$(date '+%F %T') PAUSED: leftover rsync stopped" | tee -a $LOG; }
       exit 0;;
  off) rm -f ~/.fmnet_latency_active; echo "$(date '+%F %T') StudyD7b finished: latency marker removed" | tee -a $LOG;;
esac
