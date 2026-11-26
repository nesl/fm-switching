#!/usr/bin/env python3
"""StudyORACLE capacity T per cell: max 1 s-window uncached prefill rate (D230 (12)), CPU, read-only.

Method (reports/study_oracle.md, capacity T): each request's UNCACHED tokens
(prompt_tokens - cached_tokens) are spread uniformly over its measured prefill span
[t_submit, t_first_token] and summed into 1 s windows; T = max window rate. Floor T >= 5600 tok/s
(the saturated peak) is applied by the caller. Output is per cell, with the argmax window.

Validation (positive control): reproduces the committed T(kv0.5r)=15569.8 at window 229 s on
mooncake_n16_s4_kv0.5r before any h0.5 value is used.
"""
from __future__ import annotations
import gzip, json, sys, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"


def window_rate(cell_dir: Path):
    """Return (max_rate_tok_s, argmax_window_start_s, n_requests) over 1 s windows."""
    p = cell_dir / "request.jsonl.gz"
    if not p.exists():
        return None
    acc = collections.defaultdict(float)
    n = 0
    with gzip.open(p, "rt") as f:
        for line in f:
            r = json.loads(line)
            ts, tf = r.get("t_submit"), r.get("t_first_token")
            pt, ct = r.get("prompt_tokens"), r.get("cached_tokens") or 0
            if ts is None or tf is None or pt is None:
                continue
            unc = max(0, pt - ct)
            n += 1
            span = tf - ts
            if unc <= 0:
                continue
            if span <= 1e-9:                      # instantaneous: charge the submit window
                acc[int(ts)] += unc
                continue
            rate = unc / span
            t = ts
            while t < tf:                         # uniform spread across 1 s window pieces
                w = int(t)
                seg = min(tf, w + 1) - t
                acc[w] += rate * seg
                t = w + 1
    if not acc:
        return None
    w, v = max(acc.items(), key=lambda kv: kv[1])
    return round(v, 1), w, n


if __name__ == "__main__":
    cells = sys.argv[1:]
    for c in cells:
        res = window_rate(RUNS / c)
        print(c, res)
