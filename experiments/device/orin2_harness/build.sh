#!/usr/bin/env bash
# Build the StudyORIN2 Part 2 warm-recall harness against the SAME llama.cpp
# build used by StudyORIN1-dense (commit c0fd786). Links the prebuilt shared
# libraries in $LLAMA/build/bin; no rebuild of llama.cpp, no commit change.
set -euo pipefail
LLAMA=${LLAMA:-/home/nesl/llama.cpp}
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$LLAMA/build/bin"

test -f "$BIN/libllama.so"        || { echo "missing $BIN/libllama.so"; exit 1; }
test -f "$BIN/libmtmd.so"         || { echo "missing $BIN/libmtmd.so"; exit 1; }
test -f "$BIN/libllama-common.so" || { echo "missing $BIN/libllama-common.so"; exit 1; }

g++ -std=c++17 -O2 "$HERE/warm_recall.cpp" -o "$HERE/warm_recall" \
    -I"$LLAMA/include" \
    -I"$LLAMA/ggml/include" \
    -I"$LLAMA/common" \
    -I"$LLAMA/tools/mtmd" \
    -I"$LLAMA/vendor" \
    -L"$BIN" \
    -lllama -lmtmd -lllama-common -lggml -lggml-base \
    -Wl,-rpath,"$BIN"
echo "built $HERE/warm_recall"
