#!/usr/bin/env python3
"""StudyD3-nexar optical-flow features: d2_flow.feats (17 features, Farneback on 384x216 grey) applied to each
(clip, offset)'s N = 9 SMALL prefix frames (all at or before the offset). Writes
results/dashcam/study_d3_nexar/flow_features.csv keyed by request_id of the N = 9 request.
Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d3_flow.py [--jobs 16]
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_flow as F  # noqa: E402

F.FR = Path.home() / "data/dashcam/d3_frames/small"
OUT = HERE.parents[1] / "results/dashcam/study_d3_nexar"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    reqs = [r for r in map(json.loads, open(OUT / "d3_requests_manifest.jsonl")) if r["n"] == 9]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = dict(ex.map(F.feats, reqs, chunksize=16))
    with open(OUT / "flow_features.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["request_id"] + F.FEATS)
        for r in reqs:
            w.writerow([r["request_id"]] + [f"{res[r['request_id']][k]:.6g}" for k in F.FEATS])
    print(len(res), "requests")


if __name__ == "__main__":
    main()
