#!/bin/bash
# StudyLIVE2-pilot rerun (user ruling 2026-11-18): run_live2_real.py, server restarted per run, Step 1 then the EDF ladder
# then always-cloud FCFS up to EDF's first failing size. PILOT, NOT A ROUND-1 RESULT.
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export F_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export CLEAN_GPU_UUID=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
export HF_TOKEN=$(cat hf-token.txt)   # read from file, never printed
PY=~/.venvs/fm-switching-vllm/bin/python
OUT=results/orchestration/live2/pilot/runs2
L=results/orchestration/live2/pilot/pilot2.log
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
COMMON="--seed 0 --ratio 50:50 --mode A --host-tier-gib 27 --calibration $CAL --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref --work $HOME/data/live2/pilot2/work --label PILOT_NOT_A_ROUND1_RESULT"
mkdir -p $OUT
cell() { # arm n run_s tag
  local arm=$1 n=$2 rs=$3 tag=$4
  local d=$OUT/${arm}_n${n}_${rs%.*}s${tag}
  local srv="--server http://127.0.0.1:8031 --server-kind vllm --start-server"
  [ "$arm" = "device-only" ] && srv="--server-kind none"
  echo "[$(date +%T)] start $arm n=$n run_s=$rs HEAD $(git rev-parse --short HEAD)" >> $L
  $PY experiments/orchestration/live2/run_live2_real.py --arm $arm --n-devices $n --run-s $rs --out $d $COMMON $srv > $d.stdout 2>&1
  local rc=$?
  local summ=$(jq -c '{err, run_valid, p99:.lateness.p99_ms, digests_equal, n_requests, n_errors, scored:.score.ok, score_err:.score.error, met:.score.score.sweep[0].capacity_met, dash:.score.score.sweep[0].dashcam_all_meet, rob_elig:.score.score.sweep[0].robot_pool_eligible, rob_meets:.score.score.sweep[0].robot_pool_meets}' $d/cell.json 2>/dev/null)
  echo "[$(date +%T)] end $arm n=$n rc=$rc $summ" >> $L
  echo "$summ"
}
valid() { echo "$1" | jq -e '.run_valid == true and .err == null and .n_errors == 0 and .scored == true' >/dev/null; }
# ---- Step 1
for arm in device-only edf policy-core always-cloud-fcfs edf-piece1024 edf-piece2048 utility-per-cost b9; do
  s=$(cell $arm 8 120 _step1)
  if ! valid "$s" && [ "$arm" != "device-only" -o "$(echo "$s" | jq -r .err)" != "null" ]; then
    echo "[$(date +%T)] STEP 1 FAILED on $arm: $s" >> $L; echo STEP1_FAILED > $OUT/STATUS; exit 1; fi
done
echo "[$(date +%T)] STEP 1 cells done (detailed checks in the analysis)" >> $L
# ---- EDF ladder
edf_fail=""
n=4
while :; do
  s=$(cell edf $n 600 "")
  if ! valid "$s"; then
    echo "[$(date +%T)] edf n=$n INVALID or errored, rerun once" >> $L
    s=$(cell edf $n 600 _rerun)
    if ! valid "$s"; then echo "[$(date +%T)] edf n=$n INVALID twice: harness does not keep up; ladder stops" >> $L; edf_fail="harness@$n"; break; fi
  fi
  if [ "$(echo "$s" | jq -r .met)" != "true" ]; then edf_fail=$n; echo "[$(date +%T)] EDF first failing size $n" >> $L; break; fi
  n=$((n*2))
done
echo "$edf_fail" > $OUT/EDF_FIRST_FAIL
# ---- always-cloud FCFS up to and including EDF's first failing size
lim=${edf_fail#harness@}
for m in 4 8 16 32 64 128 256 512; do
  [ $m -gt $lim ] && break
  s=$(cell always-cloud-fcfs $m 600 "")
  valid "$s" || { echo "[$(date +%T)] fcfs n=$m INVALID, rerun once" >> $L; cell always-cloud-fcfs $m 600 _rerun >/dev/null; }
done
echo "[$(date +%T)] STAGE 1 DONE (Step 1, EDF ladder, FCFS)" >> $L; echo STAGE1_DONE > $OUT/STATUS
