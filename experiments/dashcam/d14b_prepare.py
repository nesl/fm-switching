#!/usr/bin/env python3
"""StudyD14b-dense — 0.25-s decision times and causal SMALL frame rendering (CPU only; no model).

Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d14b_prepare.py [--jobs 16] [--limit K]
Pre-registered in research/EXPERIMENTS.md (StudyD14b-dense).

CLIPS   the same 300 VALIDATION clips as StudyD14 (d14_sample.json, re-derived from the split CSV and cross-checked).
TIMES   t = 3.0, 3.25, 3.5, ... up to the clip's last full 0.25-s step (t <= duration).
FRAMES  exactly StudyD14 / D3: window [t - 3, t]; the 9 D3 targets a + k * 3 / 8; N = 3 = k {0, 4, 8}, N = 1 = k {8};
        each target takes the LATEST decoded frame with pts <= target (PyAV decode timestamps). Only frames needed for
        N = 1 / 3 are written. SMALL 768x432 LANCZOS PNG (compress_level 1), D14's renderer. A frame StudyD14 already
        rendered (same clip, same pts key) is HARD-LINKED from ~/data/dashcam/d14_frames/small (byte-identical, no
        disk); others are rendered to ~/data/dashcam/d14b_frames/small/<clip>/<pts_ms>.png. SHA-256 manifest.
HEADER  d3_prepare.header. Integer-t requests carry d14_request_id (the byte-identical D14 request) for the
        determinism control.
"""
import argparse
import bisect
import gzip
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_prepare as P  # noqa: E402
import d3_prepare as D3P  # noqa: E402

REPO = HERE.parents[1]
OUT = REPO / "results/dashcam/study_d14b"
D14 = REPO / "results/dashcam/study_d14_trace"
FR14 = Path.home() / "data/dashcam/d14_frames/small"
FR = Path.home() / "data/dashcam/d14b_frames/small"
NS = (1, 3)
SUB = D3P.SUB
STEP = 0.25
MIN_FREE_GB = 5.0


def times_for(d):
    return [3.0 + STEP * j for j in range(int(math.floor((d - 3.0) / STEP + 1e-9)) + 1)]


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
    ks = sorted(set(SUB[1]) | set(SUB[3]))
    for e in ends:
        a = e - P.WIN
        targets = {k: a + k * (e - a) / 8 for k in ks}
        idx = {}
        for k, tg in targets.items():
            j = bisect.bisect_right(ts, tg + 1e-9) - 1        # latest pts <= target (same tolerance as D14)
            idx[k] = j if j >= 0 else 0
        pts = {k: ts[i] for k, i in idx.items()}
        sel[e] = dict(idx=idx, pts=pts, span_s=e - a, causal=all(p <= e + 1e-9 for p in pts.values()))
        for i in idx.values():
            need[round(ts[i], 6)] = i
    out, linked, rendered = {}, 0, 0
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for fr in c.decode(s):
            if fr.pts is None:
                continue
            t = float(fr.pts * s.time_base)
            i = need.get(round(t, 6))
            if i is None or i in out:
                continue
            key = f"{int(round(t * 1000)):07d}"
            p = FR / clip.replace(".mp4", "") / f"{key}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                src = FR14 / clip.replace(".mp4", "") / f"{key}.png"
                if src.exists():
                    os.link(src, p)
                    linked += 1
                else:
                    if shutil.disk_usage(FR).free / 1e9 < MIN_FREE_GB:
                        raise SystemExit(f"free disk < {MIN_FREE_GB} GB — STOP")
                    tmp = p.with_suffix(".tmp")
                    Image.fromarray(fr.to_ndarray(format="rgb24")).resize(P.SMALL, Image.LANCZOS).save(
                        tmp, format="PNG", compress_level=1)
                    tmp.rename(p)
                    rendered += 1
            out[i] = (key, t, hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_nlink > 1)
    missing = set(need.values()) - set(out)
    assert not missing, (clip, sorted(missing)[:5])
    return clip, sel, out, len(ts), linked, rendered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FR.mkdir(parents=True, exist_ok=True)
    s14 = json.load(open(D14 / "d14_sample.json"))
    clips = s14["clips"]
    assert len(clips) == 300 and Counter(c["label"] for c in clips) == {"positive": 150, "negative": 150}
    if a.limit:
        clips = clips[:a.limit]
    jobs = [(c["file_name"], c["label"], times_for(c["duration_s"])) for c in clips]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = {r[0]: r[1:] for r in ex.map(render, jobs, chunksize=1)}
    reqs, uniq = [], {}
    nl = nr = 0
    for c in clips:
        sel, h, _, linked, rendered = res[c["file_name"]]
        nl += linked
        nr += rendered
        for i, (key, t, sha, _) in h.items():
            uniq[(c["file_name"], key)] = (t, sha)
        for t in times_for(c["duration_s"]):
            s = sel[t]
            assert s["causal"], (c["file_name"], t)
            assert abs(s["span_s"] - P.WIN) < 1e-9
            for n in NS:
                ii = [s["idx"][k] for k in SUB[n]]
                pts = [h[i][1] for i in ii]
                assert max(pts) <= t + 1e-9, (c["file_name"], t, n)
                stem = c["file_name"].replace(".mp4", "")
                reqs.append(dict(request_id=f"{stem}_t{t:05.2f}_N{n}",
                                 d14_request_id=(f"{stem}_t{int(t):02d}_N{n}" if t == int(t) else None),
                                 file_name=c["file_name"], label=c["label"], t=t, n=n,
                                 time_of_event=c["time_of_event"], time_of_alert=c["time_of_alert"],
                                 duration_s=c["duration_s"], scene=c["scene"], light=c["light"], weather=c["weather"],
                                 frame_keys=[h[i][0] for i in ii], frame_pts=pts, small_sha256=[h[i][2] for i in ii],
                                 span_s=s["span_s"], short_span=False, header=D3P.header(n, s["span_s"]),
                                 last_pts_le_end=max(pts) <= t + 1e-9))
    # byte-identity of integer-t requests against D14's manifest (frames, header)
    d14 = {r["request_id"]: r for r in map(json.loads, gzip.open(D14 / "d14_requests_manifest.jsonl.gz", "rt"))}
    ident = [(r["small_sha256"] == d14[r["d14_request_id"]]["small_sha256"] and r["header"] == d14[r["d14_request_id"]]["header"])
             for r in reqs if r["d14_request_id"]]
    tag = f"_smoke{a.limit}" if a.limit else ""
    with gzip.open(OUT / f"d14b_requests_manifest{tag}.jsonl.gz", "wt") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    with gzip.open(OUT / f"frames_sha256_manifest{tag}.jsonl.gz", "wt") as f:
        for (clip, k), (t, sha) in sorted(uniq.items()):
            f.write(json.dumps(dict(file_name=clip, key=k, pts=t, small_sha256=sha,
                                    path=str(FR / clip.replace(".mp4", "") / f"{k}.png"))) + "\n")
    new_bytes = sum((FR / clip.replace(".mp4", "") / f"{k}.png").stat().st_size for (clip, k) in uniq
                    if (FR / clip.replace(".mp4", "") / f"{k}.png").stat().st_nlink == 1)
    all_bytes = sum((FR / clip.replace(".mp4", "") / f"{k}.png").stat().st_size for (clip, k) in uniq)
    summ = dict(n_clips=len(clips), labels=dict(Counter(c["label"] for c in clips)), step_s=STEP,
                decision_times=sum(len(times_for(c["duration_s"])) for c in clips),
                integer_decision_times=sum(1 for r in reqs if r["d14_request_id"] and r["n"] == 1),
                requests=len(reqs), requests_per_n={n: sum(r["n"] == n for r in reqs) for n in NS},
                unique_frames=len(uniq), hardlinked_from_d14_this_run=nl, rendered_new_this_run=nr,
                new_frame_gb=new_bytes / 1e9, all_frame_gb_logical=all_bytes / 1e9,
                frames_dir=str(FR), integer_t_identical_to_d14=f"{sum(ident)}/{len(ident)}",
                all_causal=all(r["last_pts_le_end"] for r in reqs), headers=sorted({r["header"] for r in reqs}),
                clips=[{k: v for k, v in c.items()} for c in clips])
    (OUT / f"d14b_sample{tag}.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps({k: v for k, v in summ.items() if k != "clips"}))
    if sum(ident) != len(ident):
        raise SystemExit("integer-t requests are not byte-identical to D14 — STOP")


if __name__ == "__main__":
    main()
