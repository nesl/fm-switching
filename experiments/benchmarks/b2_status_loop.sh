#!/usr/bin/env bash
# tmux "b2status": rewrite results/benchmarks/study_b2_status.md every 30 min (nice'd; light while a latency step runs).
cd /home/pragya/Desktop/fm-switching
while true; do nice -n 19 ~/.venvs/fm-switching-vllm/bin/python experiments/benchmarks/b2_status.py >> logs/b2_status.log 2>&1; sleep 1800; done
