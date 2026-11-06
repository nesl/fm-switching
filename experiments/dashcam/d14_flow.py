#!/usr/bin/env python3
"""StudyD14-trace optical-flow features: the unchanged d2_flow.feats (17 features, Farneback on 384x216 grey) applied
to each (clip, t)'s N = 9 SMALL prefix frames (all at or before t; CPU only). Writes
results/dashcam/study_d14_trace/d14_flow_features.csv.gz keyed by the N = 9 request_id (+ file_name, t).
Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d14_flow.py [--jobs 16]
Writes logs/dseries_done/D14_flow on success (it runs in its own tmux session, beside the GPU queue).
"""
import argparse
import csv
import gzip
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_flow as F  # noqa: E402

REPO = HERE.parents[1]
F.FR = Path.home() / "data/dashcam/d14_frames/small"
OUT = REPO / "results/dashcam/study_d14_trace"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    mp = OUT / "d14_requests_manifest.jsonl"
    reqs = [r for r in map(json.loads, open(mp) if mp.exists() else gzip.open(str(mp) + ".gz", "rt")) if r["n"] == 9]
    assert all(max(r["frame_pts"]) <= r["t"] + 1e-9 for r in reqs)
    with ProcessPoolExecutor(a.jobs) as ex:
        res = dict(ex.map(F.feats, reqs, chunksize=16))
    with gzip.open(OUT / "d14_flow_features.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["request_id", "file_name", "t"] + F.FEATS)
        for r in reqs:
            w.writerow([r["request_id"], r["file_name"], r["t"]] + [f"{res[r['request_id']][k]:.6g}" for k in F.FEATS])
    print(len(res), "requests")
    (REPO / "logs/dseries_done/D14_flow").write_text(datetime.now().isoformat() + "\n")


if __name__ == "__main__":
    main()
