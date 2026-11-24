#!/bin/bash
# H100 pusher (2026-11-24): every 60 s, if the local HEAD is not contained in origin/main, commit the tracked logs and
# push with an explicit target. Independent of any Claude session or watcher (the driver's own push has failed silently
# on this clone, and the run-watch that covered it expires when the session is blocked). Never force, never stash,
# never reset. git's stderr goes to ~/data/live2/pusher.log so a failure is diagnosable.
cd /home/pragya/Desktop/fm-switching
P=$HOME/data/live2/pusher.log
while true; do
  git fetch -q origin 2>>$P
  if ! git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
    echo "[$(date '+%F %T')] HEAD $(git rev-parse --short HEAD) not on origin/main $(git rev-parse --short origin/main); pushing" >> $P
    git add results/orchestration/live2/frozen_test/frozen_grid.log results/orchestration/live2/pilot/pilot_monitor.jsonl 2>>$P
    git diff --cached --quiet || git commit -q -m "logs" 2>>$P
    git status --porcelain | grep -v '^??' | sed 's/^/  dirty: /' >> $P
    # No `git pull`: a concurrent fetch can rewrite FETCH_HEAD under it ("Cannot rebase onto multiple branches").
    # Rebase onto the remote-tracking ref instead, which no other process rewrites mid-operation.
    if timeout 90 git fetch -q origin main 2>>$P && timeout 90 git rebase -q origin/main 2>>$P && timeout 90 git push -q origin HEAD:main 2>>$P; then
      git fetch -q origin 2>>$P; echo "[$(date '+%F %T')] pushed; HEAD $(git rev-parse --short HEAD) on origin: $(git merge-base --is-ancestor HEAD origin/main && echo yes || echo NO)" >> $P
    else echo "[$(date '+%F %T')] PUSH FAILED (see stderr above)" >> $P; fi
  fi
  sleep 60
done
