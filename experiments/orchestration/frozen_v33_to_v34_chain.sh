#!/bin/bash
# Hit-7 landing + driver v34, atomically at the run boundary AFTER the last final-ladder cell (agreed with flash:
# all 12 ladder cells share one tree; hit 7 lands after them, then flash's item 3).
#   1. STOP now; driver v33 finishes the current cell (covex-v6-state-final s7) and exits.
#   2. Copy in the four PROVEN hit-7 files (proof PASS, results/orchestration/live2/hit7_window/, commit 0047db2),
#      refusing if any target file changed on origin since the proof's base, then commit them alone and push.
#   3. Start driver v34 (= v33 + the experiments/ TREE id on every cell's start line; a tree id survives a rebase).
cd /home/pragya/Desktop/fm-switching
OUT=results/orchestration/live2/frozen_test/runs; LOG=results/orchestration/live2/frozen_test/frozen_grid.log
P=$1      # directory holding the proven after-tree (…/h7/after/experiments/orchestration)
FILES="baselines/interface.py live2/cstate.py live2/coordinator.py baselines/simplestream_adapted.py"
touch $OUT/STOP; echo "[$(date '+%F %T')] OPERATOR (hit 7 landing): STOP set; after the last ladder cell the patch lands and v34 starts" >> $LOG
while tmux has-session -t frozengrid 2>/dev/null; do sleep 10; done
for f in $FILES; do
  git diff --quiet c4547f03d8fc06575b9533bd74cde30710ffe7b1 HEAD -- experiments/orchestration/$f \
    || { echo "[$(date '+%F %T')] OPERATOR: hit 7 NOT LANDED: $f changed since the proof base; v33 restarted unchanged" >> $LOG
         rm -f $OUT/STOP; tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v33.sh"; exit 1; }
done
for f in $FILES; do cp $P/$f experiments/orchestration/$f; done
git add $(for f in $FILES; do echo experiments/orchestration/$f; done)
git commit -q -m "hit 7 LANDED: SimpleStream applies its fitted window (RecallAction.window_s, read in cstate.tokens_for_representation and the coordinator RECENT frame slice); proof PASS at 0047db2 (all other arms byte-identical; robot frames per RECENT send 6 -> 1)"
for i in 1 2 3; do timeout 60 git pull --rebase -q origin main && timeout 60 git push -q && break; sleep 15; done
echo "[$(date '+%F %T')] OPERATOR: hit 7 LANDED at $(git rev-parse --short HEAD) (tree $(git rev-parse --short=12 HEAD:experiments)); origin $(git rev-parse --short origin/main)" >> $LOG
rm -f $OUT/STOP
tmux new-session -d -s frozengrid "bash experiments/orchestration/study_frozen_grid_driver_v34.sh"
echo "[$(date '+%F %T')] OPERATOR: driver v34 started" >> $LOG
