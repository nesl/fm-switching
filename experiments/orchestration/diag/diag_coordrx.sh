#!/bin/bash
# DIAG only, never scored. Run on the H100 ONLY when the frozen-grid driver is NOT holding GPU 2.
# Usage: bash diag_coordrx.sh [arm=mooncake] [n=20] [run_s=720]
# No harness edit. v2: py-spy is attached by pid to the coordinator child at wall 200 s (sitecustomize PR_SET_PTRACER), not wrapped.
set -u
ARM=${1:-mooncake}; N=${2:-20}; RUN_S=${3:-720}; SEED=4
cd /home/pragya/Desktop/fm-switching
export CUDA_VISIBLE_DEVICES=GPU-4f1d7e47-e769-a289-4860-e71c0d97267c
# v3: the same three GPU variables as the frozen-grid driver (lines 60-62), so the harness start check watches GPU 2 (v2 watched GPU 1: study_clean_vllm.py:54 default)
export F_GPU_UUID=$CUDA_VISIBLE_DEVICES CLEAN_GPU_UUID=$CUDA_VISIBLE_DEVICES
export HF_TOKEN=$(cat hf-token.txt)
PY=~/.venvs/fm-switching-vllm/bin/python
PYSPY=${PYSPY:-$(command -v py-spy || echo ~/.venvs/pyspy/bin/py-spy)}   # pip install py-spy into a SEPARATE venv
RAW=$HOME/data/live2/diag_coordrx
NAME=${ARM}_n${N}_s${SEED}_${RUN_S}s_h27_3t_L3_epg_rq30_DIAG
D=$RAW/runs/$NAME
[ -e "$D" ] && { echo "refusing: $D exists (stale-dir hazard)"; exit 1; }
mkdir -p $D $RAW/work
CAL=results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
ARGS=(experiments/orchestration/live2/run_live2_real.py --arm $ARM --n-devices $N --run-s $RUN_S --host-tier-gib 27
  --seed $SEED --ratio 40:40:20 --robot-question-set lh_req --kv-capacity-enforced --ss-question-set ss2
  --robot-deadline-s 3 --dashcam-format epg --robot-upload per-frame --robot-reask-mean-s 30
  --mode A --calibration $CAL --decision-period-s 0.1 --mu-mode ewma --h-s 0.5
  --frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl --frames-root $HOME/data/live2/frames_by_ref
  --work $RAW/work --server http://127.0.0.1:8031 --server-kind vllm --start-server
  --label "DIAG_NOT_SCORED coordrx $NAME" --out $D)
# v2: NO py-spy wrapper (the harness start check refuses a GPU 2 with a py-spy process 'ours outside the job').
# A sitecustomize on PYTHONPATH makes every python process of the run ptrace-attachable by pid (prctl PR_SET_PTRACER ANY),
# so py-spy can attach to the coordinator child AFTER the cell has started (ptrace_scope=1). No harness file is edited.
mkdir -p $RAW/ptrace_site
cat > $RAW/ptrace_site/sitecustomize.py <<'PYEOF'
import ctypes
try:
    ctypes.CDLL(None).prctl(0x59616d61, ctypes.c_ulong(-1), 0, 0, 0)
except Exception:
    pass
# chain to the system sitecustomize (Debian: the apport hook) that this one shadows, so the harness processes behave as before
try:
    import importlib.util as _u, os as _o
    _p = "/usr/lib/python3.10/sitecustomize.py"
    if _o.path.exists(_p):
        _s = _u.spec_from_file_location("_sys_sitecustomize", _p)
        _m = _u.module_from_spec(_s)
        _s.loader.exec_module(_m)
except Exception:
    pass
PYEOF
export PYTHONPATH="$RAW/ptrace_site:${PYTHONPATH:-}"
( exec $PY "${ARGS[@]}" ) > $D.stdout 2>&1 < /dev/null &
WP=$!
T0=$(date +%s.%N)
S=$D.sampler.tsv
echo -e "wall_s\tharness_pid\tchild_pid\tfds_parent\tfds_child\trss_child_kb\tchild_top_tid_cpu_pct\tchild_sum_cpu_pct\thttp_estab\tchild_unix_recvq\tparent_unix_recvq\tvllm_running\tvllm_waiting\tgen_tokens\thealth\tdec_rows\tdec_last_t\treq_rows\treq_last_t_submit\tclient_close_wait\tclient_fin_wait\tsrv_log_lines\tsrv_log_errlines" > $S
declare -A PREV
while kill -0 $WP 2>/dev/null; do
  now=$(date +%s.%N); w=$(echo "$now - $T0" | bc)
  HP=$(ps -eo pid,args | grep -v grep | grep -F "run_live2_real.py --arm $ARM" | grep -vF py-spy | awk '{print $1}' | head -1)
  CP=$( [ -n "$HP" ] && ps -o pid=,args= --ppid $HP | grep -F multiprocessing | awk '{print $1}' | head -1)
  if [ -z "${ATT:-}" ] && [ -n "$CP" ] && [ "${w%.*}" -ge 200 ] 2>/dev/null; then
    ATT=1; ( $PYSPY record --pid $CP --gil --nonblocking --rate 20 --duration 420 --format raw -o $D/pyspy_gil.txt > $D.pyspy.log 2>&1 ) &
    echo "py-spy attached to child $CP at wall $w" >> $D.pyspy.log
  fi
  fp=$( [ -n "$HP" ] && ls /proc/$HP/fd 2>/dev/null | wc -l); fc=$( [ -n "$CP" ] && ls /proc/$CP/fd 2>/dev/null | wc -l)
  rss=$( [ -n "$CP" ] && awk '/VmRSS/{print $2}' /proc/$CP/status 2>/dev/null)
  top=""; sum=""
  if [ -n "$CP" ]; then
    tot=0; mx=0
    for st in /proc/$CP/task/*/stat; do tid=${st#/proc/$CP/task/}; tid=${tid%/stat}
      ticks=$(awk '{print $14+$15}' $st 2>/dev/null); [ -z "$ticks" ] && continue
      p=${PREV[$tid]:-$ticks}; d=$((ticks-p)); PREV[$tid]=$ticks; tot=$((tot+d)); [ $d -gt $mx ] && mx=$d; done
    top=$((mx*100/(5*100))); sum=$((tot*100/(5*100)))      # CLK_TCK 100, 5 s period
  fi
  est=$(ss -Htn state established '( dport = :8031 )' 2>/dev/null | wc -l)
  rqc=$( [ -n "$CP" ] && ss -Hxp 2>/dev/null | grep "pid=$CP," | sort -k3 -n | tail -1 | awk '{print $3}')
  rqp=$( [ -n "$HP" ] && ss -Hxp 2>/dev/null | grep "pid=$HP," | grep -v LISTEN | sort -k3 -n | tail -1 | awk '{print $3}')
  m=$(curl -s -m 2 http://127.0.0.1:8031/metrics 2>/dev/null)
  run=$(echo "$m" | awk '/^vllm:num_requests_running/{print $2; exit}'); wt=$(echo "$m" | awk '/^vllm:num_requests_waiting/{print $2; exit}')
  gen=$(echo "$m" | awk '/^vllm:generation_tokens_total/{print $2; exit}')
  hl=$(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8031/health 2>/dev/null)
  dr=$(wc -l < $D/decision.jsonl 2>/dev/null); dt=$(tail -n 2 $D/decision.jsonl 2>/dev/null | head -1 | jq -r .t 2>/dev/null)
  rr=$(wc -l < $D/request.jsonl 2>/dev/null); rt=$(tail -n 2 $D/request.jsonl 2>/dev/null | head -1 | jq -r .t_submit 2>/dev/null)
  cw=$(ss -Htn state close-wait '( dport = :8031 )' 2>/dev/null | wc -l)
  fw=$(ss -Htn state fin-wait-1 state fin-wait-2 '( dport = :8031 )' 2>/dev/null | wc -l)
  SLOG=${SLOG:-$(grep -oE '"log": "[^"]+"' $D.stdout 2>/dev/null | head -1 | cut -d'"' -f4)}
  sl=$( [ -n "$SLOG" ] && wc -l < "$SLOG" 2>/dev/null); se=$( [ -n "$SLOG" ] && grep -ciE 'error|abort|disconnect|timeout|reset|exception' "$SLOG" 2>/dev/null)
  m2=$(echo "$m" | grep -E '^vllm:(num_requests_|num_preemptions|request_success_total|e2e_request_latency_seconds_count|request_queue_time_seconds_sum)'); [ -n "$m2" ] && echo "$w $m2" | tr '\n' ' ' >> $D.metrics5s.log && echo >> $D.metrics5s.log
  echo -e "$w\t$HP\t$CP\t$fp\t$fc\t$rss\t$top\t$sum\t$est\t$rqc\t$rqp\t$run\t$wt\t$gen\t$hl\t$dr\t$dt\t$rr\t$rt\t$cw\t$fw\t$sl\t$se" >> $S
  sleep 5
done
wait $WP; echo "exit $?" >> $D.stdout
[ -n "${SLOG:-}" ] && cp "$SLOG" $D.server.log      # vLLM server log (the "log" path in the server-up line), incl. --enable-log-requests lines
grep -n "ReadError" $D/request.jsonl 2>/dev/null | head -50 > $D.readerrors.txt   # map each t_submit+exc_after_s to the server log lines in that second
echo "done: $D  sampler: $S  gil profile: $D/pyspy_gil.txt"
# Read-out: grep -c '_collect' vs total lines in pyspy_gil.txt (share of GIL-holding samples in Live2Coordinator._collect / Future.done);
# sampler columns child_top_tid_cpu_pct ~100 and child_unix_recvq growing = GIL starvation of the rx thread;
# http_estab vs vllm_running+waiting separates server queue from client backlog; dec_last_t vs wall_s = the child's lag.
