#!/bin/bash
# H100 pusher (2026-11-24): every 60 s, if the local HEAD is not contained in origin/main, commit the tracked logs and
# push with an explicit target. Independent of any Claude session or watcher (the driver's own push has failed silently
# on this clone, and the run-watch that covered it expires when the session is blocked). Never force, never stash,
# never reset. git's stderr goes to ~/data/live2/pusher.log so a failure is diagnosable.
cd /home/pragya/Desktop/fm-switching
P=$HOME/data/live2/pusher.log
G=results/orchestration/live2/frozen_test/frozen_grid.log
while true; do
  # 2026-11-24 09:28: a rebase here moved flash's a43ad7f into the working tree while a cell was
  # importing its modules; the runner loaded the old file and the coordinator child the new one, and
  # the cell died (ContextLimitUnreadable). So never rebase within 180 s of a cell's start: the run's
  # imports happen at start-up, and the driver itself pulls before the next cell.
  ls=$(grep -E "^\[[0-9-]+ [0-9:]+\] start " $G 2>/dev/null | tail -1 | cut -c2-20)
  if [ -n "$ls" ] && [ $(( $(date +%s) - $(date -d "$ls" +%s) )) -lt 180 ]; then sleep 20; continue; fi
  # 2026-11-24 11:39: the pusher also raced the driver BETWEEN cells (its end-of-cell commit and pull, then the next
  # start). So also hold while the last cell event is an "end" younger than 120 s (an idle driver cannot block forever).
  le=$(grep -E "^\[[0-9-]+ [0-9:]+\] (start|end) " $G 2>/dev/null | tail -1)
  case "$le" in *"] end "*) [ $(( $(date +%s) - $(date -d "$(echo "$le" | cut -c2-20)" +%s) )) -lt 120 ] && { sleep 10; continue; };; esac
  # 2026-11-25 11:30 (incident: an outside actor checked out branch live-experiment in this tree): push ONLY from
  # branch main. `git push origin HEAD:main` from any other branch would put that branch's HEAD on main if it ever
  # diverges. Refuse and log instead; commits wait locally until the tree is back on main.
  br=$(git symbolic-ref --short -q HEAD)
  if [ "$br" != "main" ]; then echo "[$(date '+%F %T')] REFUSED: working tree is on branch [$br], not main; not pushing" >> $P; sleep 60; continue; fi
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
