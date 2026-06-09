#!/usr/bin/env bash
# run_profiling.sh — Run the full Phase 1 profiling pipeline in one terminal.
#
# Saves all outputs to experiments/<model>_<gpu>_<date>/ for reproducibility.
# Also writes a config.json summarising the run parameters.
#
# Usage:
#   ./run_profiling.sh [options]

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
GPU_ID=1
MODEL=""
SESSIONS=4
TURNS=15
SERVER_PORT=8000
SERVER_STARTUP_TIMEOUT=300
VENV_PATH="$(cd "$(dirname "$0")/.." && pwd)/.venv"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT_NAME=""   # auto-generated if empty

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)           MODEL="$2";           shift 2 ;;
        --gpu-id)          GPU_ID="$2";          shift 2 ;;
        --sessions)        SESSIONS="$2";        shift 2 ;;
        --turns)           TURNS="$2";           shift 2 ;;
        --port)            SERVER_PORT="$2";     shift 2 ;;
        --experiment-name) EXPERIMENT_NAME="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./run_profiling.sh [options]"
            echo "  --model MODEL           HuggingFace model (default: auto-select)"
            echo "  --gpu-id N              GPU index (default: 1 = A6000)"
            echo "  --sessions N            Concurrent sessions for workload gen (default: 4)"
            echo "  --turns N               Turns per session (default: 15)"
            echo "  --port N                Server port (default: 8000)"
            echo "  --experiment-name NAME  Override auto-generated experiment directory name"
            exit 0 ;;
        *) echo "Unknown arg: $1. Use --help for usage."; exit 1 ;;
    esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${RESET} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${RESET} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${RESET} $*"; }
die()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗ ERROR:${RESET} $*" >&2; exit 1; }

# ── Cleanup ───────────────────────────────────────────────────────────────────
SERVER_PID=""
LOGGER_PID=""

cleanup() {
    echo ""
    log "Shutting down background processes..."
    if [[ -n "$LOGGER_PID" ]] && kill -0 "$LOGGER_PID" 2>/dev/null; then
        kill "$LOGGER_PID"; wait "$LOGGER_PID" 2>/dev/null || true
        ok "GPU logger stopped"
    fi
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID"; wait "$SERVER_PID" 2>/dev/null || true
        ok "vLLM server stopped"
    fi
    log "Done. Results in: $EXP_DIR"
}
trap cleanup EXIT

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ -d "$VENV_PATH" ]] || die "venv not found at $VENV_PATH"
source "$VENV_PATH/bin/activate"
python -c "import vllm" 2>/dev/null || die "vLLM not installed in venv"
python -c "import pynvml" 2>/dev/null || die "pynvml not installed in venv"

mkdir -p "$SCRIPT_DIR/logs"
cd "$SCRIPT_DIR"

# ── Resolve model name for directory naming ───────────────────────────────────
# Auto-detect GPU name for the experiment directory
GPU_NAME=$(python -c "
import warnings
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    import torch
idx = min($GPU_ID, torch.cuda.device_count()-1)
name = torch.cuda.get_device_properties(idx).name.lower()
name = name.replace('nvidia ', '').replace(' ', '-')
print(name)
" 2>/dev/null || echo "gpu$GPU_ID")

# Auto-detect or format model short name
if [[ -n "$MODEL" ]]; then
    MODEL_SHORT=$(echo "$MODEL" | sed 's|.*/||' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-*$//')
else
    MODEL_SHORT="auto"
fi

DATE_STR=$(date '+%Y%m%d')

if [[ -z "$EXPERIMENT_NAME" ]]; then
    EXPERIMENT_NAME="${MODEL_SHORT}_${GPU_NAME}_${DATE_STR}"
fi

EXP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/experiments/${EXPERIMENT_NAME}"
mkdir -p "$EXP_DIR/logs" "$EXP_DIR/plots"

SERVER_URL="http://localhost:$SERVER_PORT"

# ── Print config ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  FM Switching — Phase 1 Profiling Pipeline${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════════════${RESET}"
echo -e "  GPU:        ${BOLD}$GPU_ID ($GPU_NAME)${RESET}"
[[ -n "$MODEL" ]] && echo -e "  Model:      ${BOLD}$MODEL${RESET}" || echo -e "  Model:      ${BOLD}auto-select${RESET}"
echo -e "  Sessions:   ${BOLD}$SESSIONS${RESET}"
echo -e "  Turns:      ${BOLD}$TURNS${RESET}"
echo -e "  Experiment: ${BOLD}$EXP_DIR${RESET}"
echo ""

# ── Step 1: Start vLLM server ─────────────────────────────────────────────────
log "Step 1/5 — Starting vLLM server → $EXP_DIR/logs/server.log"

SERVER_CMD=(python 01_start_server.py --gpu-id "$GPU_ID" --port "$SERVER_PORT")
[[ -n "$MODEL" ]] && SERVER_CMD+=(--model "$MODEL")

"${SERVER_CMD[@]}" > "$EXP_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!

ELAPSED=0
POLL_INTERVAL=5
while true; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        die "vLLM server process died.\n$(tail -20 "$EXP_DIR/logs/server.log")"
    fi
    if curl -sf "$SERVER_URL/health" > /dev/null 2>&1; then
        echo ""; ok "Server ready after ${ELAPSED}s"
        break
    fi
    LAST_LOG=$(tail -1 "$EXP_DIR/logs/server.log" 2>/dev/null | cut -c1-60 || true)
    printf "\r  [%3ds] %s" "$ELAPSED" "$LAST_LOG"
    sleep "$POLL_INTERVAL"; ELAPSED=$((ELAPSED + POLL_INTERVAL))
    [[ $ELAPSED -ge $SERVER_STARTUP_TIMEOUT ]] && die "Server startup timeout"
done

# Detect actual model name loaded
LOADED_MODEL=$(curl -sf "$SERVER_URL/v1/models" | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "$MODEL")
[[ -z "$MODEL_SHORT" || "$MODEL_SHORT" == "auto" ]] && \
    MODEL_SHORT=$(echo "$LOADED_MODEL" | sed 's|.*/||' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')

# ── Write config.json ─────────────────────────────────────────────────────────
python -c "
import json, subprocess, datetime
config = {
    'model': '$LOADED_MODEL',
    'gpu_id': $GPU_ID,
    'gpu_name': '$GPU_NAME',
    'sessions': $SESSIONS,
    'turns_per_session': $TURNS,
    'server_port': $SERVER_PORT,
    'date': '$(date '+%Y-%m-%d')',
    'timestamp': '$(date -Iseconds)',
}
with open('$EXP_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('  Wrote config.json')
"

# ── Step 2: Start GPU + vLLM metrics logger ───────────────────────────────────
log "Step 2/5 — Starting GPU + vLLM metrics logger → $EXP_DIR/logs/gpu_metrics.csv"

python 02_gpu_logger.py \
    --gpu-index "$GPU_ID" \
    --output "$EXP_DIR/logs/gpu_metrics.csv" \
    --vllm-url "$SERVER_URL" \
    > "$EXP_DIR/logs/gpu_logger.log" 2>&1 &
LOGGER_PID=$!

sleep 1
kill -0 "$LOGGER_PID" 2>/dev/null || die "GPU logger failed. Check $EXP_DIR/logs/gpu_logger.log"
ok "GPU + vLLM metrics logger running (PID $LOGGER_PID)"

# ── Step 3: Prefill benchmark ─────────────────────────────────────────────────
log "Step 3/5 — Prefill benchmark (context inertia curve)"

python 04_prefill_benchmark.py \
    --server-url "$SERVER_URL" \
    --output "$EXP_DIR/logs/prefill_cost_curve.csv"

ok "Prefill benchmark complete → $EXP_DIR/logs/prefill_cost_curve.csv"

# ── Step 4: Workload generator ────────────────────────────────────────────────
log "Step 4/5 — Workload generator ($SESSIONS sessions × $TURNS turns)"

python 03_workload_generator.py \
    --server-url "$SERVER_URL" \
    --sessions "$SESSIONS" \
    --turns-per-session "$TURNS" \
    --output "$EXP_DIR/logs/session_traces.csv"

ok "Workload generator complete → $EXP_DIR/logs/session_traces.csv"

# ── Step 5: Visualize ─────────────────────────────────────────────────────────
log "Step 5/5 — Generating plots"

python 05_visualize.py \
    --logs-dir "$EXP_DIR/logs" \
    --output-dir "$EXP_DIR/plots"

ok "Plots saved → $EXP_DIR/plots/"

# ── Compute and append summary stats to config.json ───────────────────────────
python -c "
import json, pandas as pd, numpy as np
config_path = '$EXP_DIR/config.json'
with open(config_path) as f:
    config = json.load(f)

try:
    df = pd.read_csv('$EXP_DIR/logs/prefill_cost_curve.csv')
    by_depth = df.groupby('actual_prompt_tokens')['prefill_time_ms'].mean()
    x = by_depth.index.values.astype(float)
    y = by_depth.values
    coeffs = np.polyfit(x, y, 1)
    r2 = 1 - np.sum((y - np.polyval(coeffs, x))**2) / np.sum((y - y.mean())**2)
    config['results'] = {
        'inertia_slope_ms_per_token': round(float(coeffs[0]), 4),
        'inertia_intercept_ms': round(float(coeffs[1]), 1),
        'inertia_r2': round(float(r2), 5),
        'max_depth_tokens': int(x.max()),
        'max_migration_cost_ms': round(float(y.max()), 1),
        'extrapolated_8k_ms': round(float(np.polyval(coeffs, 8192)), 0),
        'extrapolated_16k_ms': round(float(np.polyval(coeffs, 16384)), 0),
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print('  Updated config.json with results summary')
    print(f'  Inertia: {coeffs[0]:.4f} ms/token, R²={r2:.5f}')
except Exception as e:
    print(f'  Could not compute summary: {e}')
"

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Experiment complete: ${EXPERIMENT_NAME}${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════════════${RESET}"
echo -e "  ${GREEN}$EXP_DIR/logs/prefill_cost_curve.csv${RESET}"
echo -e "  ${GREEN}$EXP_DIR/logs/session_traces.csv${RESET}"
echo -e "  ${GREEN}$EXP_DIR/logs/gpu_metrics.csv${RESET}"
echo -e "  ${GREEN}$EXP_DIR/plots/context_inertia_curve.png${RESET}"
echo -e "  ${GREEN}$EXP_DIR/config.json${RESET}"
echo ""
