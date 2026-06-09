#!/bin/bash
# Run all three profiling experiments on A6000
# Usage: bash run_all_experiments.sh

set -e

echo "============================================="
echo "FM Pipeline Profiling Suite"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo "============================================="

# Install dependencies if needed
# pip install -r requirements_profiling.txt --break-system-packages

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTDIR="results_${TIMESTAMP}"
mkdir -p "$OUTDIR"

echo ""
echo ">>> Experiment 1: Memory Breakdown"
echo "    (Co-loading VLM+LLM, activation scaling with cameras/resolution)"
echo ""
python exp1_memory_breakdown.py --output "$OUTDIR/exp1_memory.json"

echo ""
echo ">>> Experiment 2: Model Loading Time"
echo "    (Cold-start loading, 5 trials each)"
echo ""
python exp2_loading_time.py --trials 5 --output "$OUTDIR/exp2_loading.json"

echo ""
echo ">>> Experiment 3: Pipeline Latency"
echo "    (VLM → LLM end-to-end, varying configs)"
echo ""
python exp3_pipeline_latency.py --trials 5 --output "$OUTDIR/exp3_latency.json"

echo ""
echo "============================================="
echo "All experiments complete!"
echo "Results in: $OUTDIR/"
echo "============================================="