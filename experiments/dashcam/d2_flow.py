#!/usr/bin/env python3
"""StudyD2-nexar optical-flow baseline features (CPU; no model). Same 9 SMALL frames as the model input.

Per request: frames -> grayscale, resized to 384x216 (INTER_AREA); dense Farneback flow (pyr 0.5, levels 3, win 15,
iters 3, poly_n 5, poly_sigma 1.2) between the 8 consecutive pairs. Per pair: mean magnitude (whole frame), mean
magnitude in the central region (middle 50 % of width and height), mean magnitude in the periphery, mean RADIAL
component in the central region (flow . unit vector from the image centre; > 0 = expansion / approach), mean absolute
frame difference. Request features (17):
  mag_mean, mag_max, mag_std, mag_last, mag_slope            (whole-frame magnitude over the 8 pairs)
  cmag_mean, cmag_last, pmag_mean, c_over_p                  (centre vs periphery)
  exp_mean, exp_max, exp_last, exp_slope                     (central radial expansion)
  diff_mean, diff_max, diff_last, diff_slope                 (frame differencing)
Slopes are least-squares over pair index 0..7. Writes results/dashcam/study_d2_nexar/flow_features.csv.
Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d2_flow.py [--jobs 16]
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/dashcam/study_d2_nexar"
FR = Path.home() / "data/dashcam/d2_frames/small"
W, H = 384, 216
FEATS = ["mag_mean", "mag_max", "mag_std", "mag_last", "mag_slope", "cmag_mean", "cmag_last", "pmag_mean", "c_over_p",
         "exp_mean", "exp_max", "exp_last", "exp_slope", "diff_mean", "diff_max", "diff_last", "diff_slope"]


def slope(v):
    x = np.arange(len(v))
    return float(np.polyfit(x, v, 1)[0])


def feats(req):
    import cv2
    cv2.setNumThreads(1)
    ims = [cv2.resize(cv2.imread(str(FR / req["file_name"].replace(".mp4", "") / f"{k}.png"), cv2.IMREAD_GRAYSCALE),
                      (W, H), interpolation=cv2.INTER_AREA) for k in req["frame_keys"]]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = (W - 1) / 2, (H - 1) / 2
    rx, ry = xx - cx, yy - cy
    rn = np.sqrt(rx ** 2 + ry ** 2) + 1e-6
    ux, uy = rx / rn, ry / rn
    centre = (np.abs(rx) <= W / 4) & (np.abs(ry) <= H / 4)
    mag, cmag, pmag, exp, diff = [], [], [], [], []
    for a, b in zip(ims[:-1], ims[1:]):
        f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        m = np.sqrt(f[..., 0] ** 2 + f[..., 1] ** 2)
        mag.append(float(m.mean()))
        cmag.append(float(m[centre].mean()))
        pmag.append(float(m[~centre].mean()))
        exp.append(float((f[..., 0] * ux + f[..., 1] * uy)[centre].mean()))
        diff.append(float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()))
    v = dict(mag_mean=np.mean(mag), mag_max=np.max(mag), mag_std=np.std(mag), mag_last=mag[-1], mag_slope=slope(mag),
             cmag_mean=np.mean(cmag), cmag_last=cmag[-1], pmag_mean=np.mean(pmag),
             c_over_p=np.mean(cmag) / (np.mean(pmag) + 1e-6), exp_mean=np.mean(exp), exp_max=np.max(exp),
             exp_last=exp[-1], exp_slope=slope(exp), diff_mean=np.mean(diff), diff_max=np.max(diff),
             diff_last=diff[-1], diff_slope=slope(diff))
    return req["request_id"], {k: float(v[k]) for k in FEATS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    reqs = [json.loads(l) for l in open(OUT / "pilot_requests.jsonl")]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = dict(ex.map(feats, reqs, chunksize=8))
    with open(OUT / "flow_features.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["request_id"] + FEATS)
        for r in reqs:
            w.writerow([r["request_id"]] + [f"{res[r['request_id']][k]:.6g}" for k in FEATS])
    print(len(res), "requests;", len(FEATS), "features")


if __name__ == "__main__":
    main()
