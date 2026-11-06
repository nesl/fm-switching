#!/usr/bin/env python3
"""StudyD14-trace — whole-clip decision times and causal SMALL frame rendering (CPU only; no model).

Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d14_prepare.py [--jobs 16] [--limit K]
Pre-registered in research/EXPERIMENTS.md (StudyD14-trace).

CLIPS   all 300 VALIDATION clips of results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv (cross-checked against
        d2_prepare.split). No test clip and no development clip is decoded.
TIMES   every whole second t = 3 ... floor(duration). No reference time.
FRAMES  as StudyD3: window [t - 3, t]; N = 9 targets evenly spaced (k = 0..8), N = 3 = k {0, 4, 8}, N = 1 = k {8};
        each target takes the LATEST decoded frame with pts <= target (PyAV decode timestamps). Pass 1 decodes the clip
        and records frame pts; pass 2 decodes again and saves only the selected frames (bounded memory). SMALL 768x432
        LANCZOS lossless PNG, outside the repo at ~/data/dashcam/d14_frames/small/<clip>/<pts_ms>.png; SHA-256 manifest.
HEADER  d3_prepare.header (t >= 3, so the span is always the full 3 s). Query is D2 / D3's (in the inference script).
LABELS  per row: clip, label, t, time_of_event, time_of_alert (positives), duration, scene, light, weather.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_prepare as P  # noqa: E402
import d3_prepare as D3P  # noqa: E402

REPO = HERE.parents[1]
OUT = REPO / "results/dashcam/study_d14_trace"
FR = Path.home() / "data/dashcam/d14_frames/small"
SPLIT = REPO / "results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv"
NS = (1, 3, 9)
SUB = D3P.SUB


def render(job):
    import av
    from PIL import Image
    clip, lab, ends = job
    path = str(P.NEX / lab / clip)
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        ts = sorted(float(fr.pts * s.time_base) for fr in c.decode(s) if fr.pts is not None)
    sel, need = {}, {}
    for e in ends:
        a = e - P.WIN
        targets = [a + k * (e - a) / 8 for k in range(9)]
        idx = []
        for tg in targets:
            j = None
            for i, t in enumerate(ts):
                if t <= tg + 1e-9:
                    j = i
                else:
                    break
            idx.append(j if j is not None else 0)
        pts = [ts[i] for i in idx]
        sel[e] = dict(idx=idx, pts=pts, span_s=e - a, causal=all(p <= e + 1e-9 for p in pts))
        for i in idx:
            need[round(ts[i], 6)] = i
    hashes = {}
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for fr in c.decode(s):
            if fr.pts is None:
                continue
            t = float(fr.pts * s.time_base)
            i = need.get(round(t, 6))
            if i is None or i in hashes:
                continue
            key = f"{int(round(t * 1000)):07d}"
            p = FR / clip.replace(".mp4", "") / f"{key}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                tmp = p.with_suffix(".tmp")
                Image.fromarray(fr.to_ndarray(format="rgb24")).resize(P.SMALL, Image.LANCZOS).save(
                    tmp, format="PNG", compress_level=1)
                tmp.rename(p)
            hashes[i] = (key, t, hashlib.sha256(p.read_bytes()).hexdigest())
    missing = set(need.values()) - set(hashes)
    assert not missing, (clip, sorted(missing)[:5])
    return clip, sel, hashes, len(ts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: first K clips only, written to a smoke file")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    split = list(csv.DictReader(open(SPLIT)))
    val = sorted([r for r in split if r["split"] == "val"], key=lambda r: (r["label"], r["file_name"]))
    assert len(val) == 300, len(val)
    meta = {(r["label"], r["file_name"]): r for r in P.load_meta()}
    sp = P.split(list(meta.values()))
    assert all(sp[(r["label"], r["file_name"])] == "val" for r in val), "CSV split disagrees with d2_prepare.split"
    clips = []
    for r in val:
        m = meta[(r["label"], r["file_name"])]
        d = float(r["duration_s"])
        assert abs(d - float(m["duration_s"])) < 1e-3, (r["file_name"], d, m["duration_s"])
        ts = list(range(3, math.floor(d) + 1))
        toe = float(m["time_of_event"]) if r["label"] == "positive" and m.get("time_of_event") not in (None, "") else None
        toa = float(m["time_of_alert"]) if r["label"] == "positive" and m.get("time_of_alert") not in (None, "") else None
        clips.append(dict(file_name=r["file_name"], label=r["label"], scene=r["scene"], light=r["light"],
                          weather=r["weather"], duration_s=d, time_of_event=toe, time_of_alert=toa, times=ts))
    if a.limit:
        clips = clips[:a.limit]
    jobs = [(c["file_name"], c["label"], [float(t) for t in c["times"]]) for c in clips]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = {clip: (sel, h, nf) for clip, sel, h, nf in ex.map(render, jobs, chunksize=1)}
    reqs, uniq = [], {}
    for c in clips:
        sel, h, _ = res[c["file_name"]]
        for i, (key, t, sha) in h.items():
            uniq[(c["file_name"], key)] = (t, sha)
        for t in c["times"]:
            s = sel[float(t)]
            assert s["causal"], (c["file_name"], t)
            assert abs(s["span_s"] - P.WIN) < 1e-9
            for n in NS:
                ii = [s["idx"][k] for k in SUB[n]]
                pts = [h[i][1] for i in ii]
                assert max(pts) <= t + 1e-9, (c["file_name"], t, n)
                reqs.append(dict(request_id=f"{c['file_name'].replace('.mp4', '')}_t{t:02d}_N{n}",
                                 file_name=c["file_name"], label=c["label"], t=t, n=n,
                                 time_of_event=c["time_of_event"], time_of_alert=c["time_of_alert"],
                                 duration_s=c["duration_s"], scene=c["scene"], light=c["light"], weather=c["weather"],
                                 frame_keys=[h[i][0] for i in ii], frame_pts=pts, small_sha256=[h[i][2] for i in ii],
                                 span_s=s["span_s"], short_span=False, header=D3P.header(n, s["span_s"]),
                                 last_pts_le_end=max(pts) <= t + 1e-9))
    tag = f"_smoke{a.limit}" if a.limit else ""
    with gzip.open(OUT / f"d14_requests_manifest{tag}.jsonl.gz", "wt") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    with gzip.open(OUT / f"frames_sha256_manifest{tag}.jsonl.gz", "wt") as f:
        for (clip, k), (t, sha) in sorted(uniq.items()):
            f.write(json.dumps(dict(file_name=clip, key=k, pts=t, small_sha256=sha,
                                    path=str(FR / clip.replace(".mp4", "") / f"{k}.png"))) + "\n")
    summ = dict(n_clips=len(clips), labels=dict(Counter(c["label"] for c in clips)),
                scenes=dict(Counter(f"{c['label']}/{c['scene']}" for c in clips).most_common()),
                decision_times=sum(len(c["times"]) for c in clips), requests=len(reqs),
                requests_per_n={n: sum(r["n"] == n for r in reqs) for n in NS}, unique_frames=len(uniq),
                decoded_frames_per_clip={c["file_name"]: res[c["file_name"]][2] for c in clips},
                all_causal=all(r["last_pts_le_end"] for r in reqs), headers=sorted({r["header"] for r in reqs}),
                split_csv=str(SPLIT.relative_to(REPO)), split_cross_checked_with_d2_prepare=True,
                clips=[{k: v for k, v in c.items() if k != "times"} for c in clips])
    (OUT / f"d14_sample{tag}.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps({k: v for k, v in summ.items() if k not in ("clips", "scenes", "decoded_frames_per_clip")}))


if __name__ == "__main__":
    main()
