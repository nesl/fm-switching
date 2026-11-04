#!/usr/bin/env python3
"""StudyD0 DoTA, METADATA ONLY (frames unavailable: both Google Drive links returned 404 on 2026-11-04).

Reads the cloned repo (github.com/MoonBlvd/Detection-of-Traffic-Anomaly) dataset/metadata_{train,val}.json and the
per-clip annotation JSONs (dataset/DoTA_annotations.zip, unzipped outside the repo); writes
results/data_check/dota_metadata_check.json. Times use 10 fps (the frame-extraction rate, video2frames.py -f 10).
Run: ~/.venvs/dashcam/bin/python -I experiments/data_check/dota_metadata_check.py
"""
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
D = Path.home() / "data/dashcam/dota"
EGO5 = ["ego: turning", "ego: lateral", "ego: moving_ahead_or_waiting", "ego: oncoming", "ego: start_stop_or_stationary"]
FPS = 10.0


def st(x):
    p = np.percentile(x, [0, 5, 25, 50, 75, 95, 100])
    return dict(n=len(x), min=float(p[0]), p5=float(p[1]), p25=float(p[2]), p50=float(p[3]), p75=float(p[4]),
                p95=float(p[5]), max=float(p[6]), mean=float(np.mean(x)))


def main():
    ds = D / "repo/dataset"
    t = json.load(open(ds / "metadata_train.json"))
    v = json.load(open(ds / "metadata_val.json"))
    m = {**t, **v}
    ann = {p.stem: json.load(open(p)) for p in (D / "annotations_zip/annotations").glob("*.json")}
    ego = {k: r for k, r in m.items() if r["anomaly_class"] in EGO5}
    pre = [r["anomaly_start"] / FPS for r in ego.values()]
    post = [(r["num_frames"] - r["anomaly_start"]) / FPS for r in ego.values()]
    mism = [k for k, r in m.items() if k in ann and (ann[k]["num_frames"] != r["num_frames"]
                                                     or ann[k]["anomaly_start"] != r["anomaly_start"])]
    res = dict(
        source="github.com/MoonBlvd/Detection-of-Traffic-Anomaly",
        repo_commit=subprocess.run(["git", "-C", str(D / "repo"), "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip(),
        file_sha256={f: hashlib.sha256((ds / f).read_bytes()).hexdigest() for f in
                     ("metadata_train.json", "metadata_val.json", "DoTA_annotations.zip")},
        frames_on_disk="UNAVAILABLE — full archive (Drive file 1RQp4hOP9X7TW6S3_vbqZvFSkrbbFzrRj) and split-archive "
                       "folder (1_WzhwZC2NIpzZIpX7YCvapq66rtBc67n) both returned HTTP 404 to gdown and curl on 2026-11-04",
        n_train=len(t), n_val=len(v), n_overlap_keys=len(set(t) & set(v)), sum_num_frames=int(sum(r["num_frames"] for r in m.values())),
        sum_num_frames_train=int(sum(r["num_frames"] for r in t.values())),
        sum_num_frames_val=int(sum(r["num_frames"] for r in v.values())),
        paper_frames=731932, n_annotation_jsons=len(ann), metadata_keys_without_annotation=len(set(m) - set(ann)),
        annotation_vs_metadata_mismatch=len(mism),
        sum_num_frames_annotations=int(sum(a["num_frames"] for a in ann.values())),
        sum_label_entries_annotations=int(sum(len(a["labels"]) for a in ann.values())),
        class_counts=dict(Counter(r["anomaly_class"] for r in m.values()).most_common()),
        ego5_classes=EGO5, ego5_count=len(ego), ego5_by_class=dict(Counter(r["anomaly_class"] for r in ego.values())),
        ego5_pre_onset_s=st(pre), ego5_frac_pre_ge={k: float(np.mean([p >= k for p in pre])) for k in (2, 3, 4, 5)},
        ego5_post_onset_s=st(post), ego5_frac_post_ge={k: float(np.mean([p >= k for p in post])) for k in (2, 4)},
        ego5_num_frames=st([r["num_frames"] for r in ego.values()]),
        fps_assumed=FPS)
    out = REPO / "results/data_check/dota_metadata_check.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("n_train", "n_val", "sum_num_frames", "n_annotation_jsons",
                                          "sum_num_frames_annotations", "sum_label_entries_annotations",
                                          "annotation_vs_metadata_mismatch", "ego5_count", "ego5_frac_pre_ge",
                                          "ego5_frac_post_ge")}))


if __name__ == "__main__":
    main()
