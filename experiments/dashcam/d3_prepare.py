#!/usr/bin/env python3
"""StudyD3-nexar — clips, reference times, causal SMALL frame rendering for N = 1 / 3 / 9 (CPU only; no model).

Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d3_prepare.py [--jobs 16]
Pre-registered in research/EXPERIMENTS.md (StudyD3-nexar).

CLIPS   every DEVELOPMENT clip of the seed-0 split (d2_prepare.split, identical rule) that is NOT in the StudyD2
        pilot sample. No validation / test clip is decoded.
REF     positives: time_of_event (observed). negatives: ASSIGNED — D2's rule over THESE clips: random.Random(0).choice
        over these clips' positive time_of_event values in the same duration bin (18-20 / 38-42 / other), negatives
        visited in file-name order, clipped to [3, D - 2] when D >= 5 s.
OFFSETS -3, -2.5, -2, -1.5, -1, -0.5, 0, +0.5, +1, +2 s; prefix end e = ref + offset.
FRAMES  window [max(0, e - 3), e]; N = 9 targets evenly spaced (k = 0..8), N = 3 targets {start, middle, e}
        (= N = 9's k = 0, 4, 8), N = 1 target {e}; each target takes the LATEST decoded frame with pts <= target
        (PyAV decode timestamps; d2_prepare's selection). SMALL 768x432 LANCZOS, lossless PNG, outside the repo at
        /home/pragya/data/dashcam/d3_frames/small/<clip>/<pts_ms>.png; SHA-256 manifest in results.
HEADER  N = 9 / 3: "The following are {N} consecutive dashcam frames covering {S} seconds, oldest first."
        N = 1: "The following is 1 dashcam frame."  S = "3" for a full window, else the actual span to 0.1 s
        (short spans logged). The query is D2's, unchanged.
"""
import argparse
import csv
import gzip
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_prepare as P  # noqa: E402

REPO = HERE.parents[1]
OUT = REPO / "results/dashcam/study_d3_nexar"
FR = Path.home() / "data/dashcam/d3_frames/small"
PILOT = REPO / "results/dashcam/study_d2_nexar/pilot_sample.json"
OFFSETS = [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]
NS = (1, 3, 9)
SUB = {9: list(range(9)), 3: [0, 4, 8], 1: [8]}


def header(n, span):
    if n == 1:
        return "The following is 1 dashcam frame."
    s = "3" if span >= P.WIN - 1e-6 else f"{span:.1f}"
    return f"The following are {n} consecutive dashcam frames covering {s} seconds, oldest first."


def render(job):
    import av
    from PIL import Image
    clip, lab, ends = job
    lo = max(0.0, min(ends) - P.WIN - 0.5)
    hi = max(ends) + 0.05
    frames = []
    with av.open(str(P.NEX / lab / clip)) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        c.seek(int(max(0.0, lo - 1.0) / s.time_base), stream=s, backward=True)
        for fr in c.decode(s):
            if fr.pts is None:
                continue
            t = float(fr.pts * s.time_base)
            if t > hi:
                break
            if t >= lo - 0.5:
                frames.append((t, fr))
    frames.sort(key=lambda x: x[0])
    ts = [t for t, _ in frames]
    sel, used = {}, set()
    for e in ends:
        a = max(0.0, e - P.WIN)
        targets = [a + k * (e - a) / 8 for k in range(9)]
        idx = []
        for tg in targets:
            cand = [i for i, t in enumerate(ts) if t <= tg + 1e-9]
            idx.append(cand[-1] if cand else 0)
        sel[e] = dict(targets=targets, idx=idx, pts=[ts[i] for i in idx], span_s=e - a,
                      causal=all(ts[i] <= e + 1e-9 for i in idx))
        used.update(idx)
    hashes = {}
    for i in used:
        t = ts[i]
        key = f"{int(round(t * 1000)):07d}"
        p = FR / clip.replace(".mp4", "") / f"{key}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            Image.fromarray(frames[i][1].to_ndarray(format="rgb24")).resize(P.SMALL, Image.LANCZOS).save(
                p, format="PNG", compress_level=1)
        hashes[i] = (key, t, hashlib.sha256(p.read_bytes()).hexdigest())
    return clip, sel, hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = P.load_meta()
    sp = P.split(rows)
    pilot = {c["file_name"] for c in json.load(open(PILOT))["clips"]}
    dev = [r for r in rows if sp[(r["label"], r["file_name"])] == "dev"]
    use = sorted([r for r in dev if r["file_name"] not in pilot], key=lambda r: (r["label"], r["file_name"]))
    posbin = defaultdict(list)
    for r in use:
        if r["label"] == "positive":
            posbin[P.dbin(r["duration_s"])].append(float(r["time_of_event"]))
    rng = random.Random(0)
    clips = []
    for r in use:
        d = r["duration_s"]
        b = P.dbin(d)
        base = dict(file_name=r["file_name"], label=r["label"], scene=r["scene"], light=r["light_conditions"],
                    weather=r["weather"], duration_s=d, bin=b)
        if r["label"] == "positive":
            toe, toa = float(r["time_of_event"]), float(r["time_of_alert"])
            clips.append(dict(base, ref=toe, ref_kind="observed (time_of_event)", time_of_alert=toa, lead=toe - toa,
                              subgroup="sudden" if toe - toa < 1.5 else "slow"))
        else:
            raw = rng.choice(sorted(posbin[b]))
            ref = min(max(raw, P.WIN), d - 2.0) if d >= P.WIN + 2.0 else raw
            clips.append(dict(base, ref=ref, ref_sampled=raw, ref_clipped=ref != raw, time_of_alert=None,
                              ref_kind="ASSIGNED (sampled from these clips' positive time_of_event, same bin)"))
    rcheck = {}
    from scipy.stats import ks_2samp
    for b in ("18-20", "38-42", "other"):
        p = [c["ref"] for c in clips if c["label"] == "positive" and c["bin"] == b]
        n = [c["ref"] for c in clips if c["label"] == "negative" and c["bin"] == b]
        rcheck[b] = dict(n_pos=len(p), n_neg=len(n),
                         pos_median=float(np.median(p)) if p else None, neg_median=float(np.median(n)) if n else None,
                         ks_p=float(ks_2samp(p, n).pvalue) if len(p) > 1 and len(n) > 1 else None)
    jobs = [(c["file_name"], c["label"], [c["ref"] + o for o in OFFSETS]) for c in clips]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = {clip: (sel, h) for clip, sel, h in ex.map(render, jobs, chunksize=2)}
    reqs, uniq, logs = [], {}, []
    for c in clips:
        sel, h = res[c["file_name"]]
        for i, (key, t, sha) in h.items():
            uniq[(c["file_name"], key)] = (t, sha)
        for o in OFFSETS:
            e = c["ref"] + o
            s = sel[e]
            assert s["causal"], (c["file_name"], o)
            gt = "negative" if c["label"] == "negative" else ("positive" if e >= c["time_of_alert"] - 1e-9 else
                                                             "unscored")
            short = s["span_s"] < P.WIN - 1e-6
            if short:
                logs.append(dict(file_name=c["file_name"], offset=o, end=e, span_s=s["span_s"]))
            for n in NS:
                ii = [s["idx"][k] for k in SUB[n]]
                reqs.append(dict(request_id=f"{c['file_name'].replace('.mp4', '')}_{o:+.1f}_N{n}",
                                 file_name=c["file_name"], label=c["label"], scene=c["scene"],
                                 subgroup=c.get("subgroup"), lead=c.get("lead"), offset=o, n=n, ref=c["ref"], end=e,
                                 time_of_alert=c["time_of_alert"], gt=gt,
                                 frame_keys=[h[i][0] for i in ii], frame_pts=[h[i][1] for i in ii],
                                 small_sha256=[h[i][2] for i in ii], span_s=s["span_s"], short_span=short,
                                 header=header(n, s["span_s"]),
                                 last_pts_le_end=all(h[i][1] <= e + 1e-9 for i in ii)))
    with open(OUT / "d3_requests_manifest.jsonl", "w") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    with gzip.open(OUT / "frames_sha256_manifest.jsonl.gz", "wt") as f:
        for (clip, k), (t, sha) in sorted(uniq.items()):
            f.write(json.dumps(dict(file_name=clip, key=k, pts=t, small_sha256=sha,
                                    path=str(FR / clip.replace(".mp4", "") / f"{k}.png"))) + "\n")
    summ = dict(n_clips=len(clips), labels=dict(Counter(c["label"] for c in clips)),
                subgroups=dict(Counter(c.get("subgroup") for c in clips if c["label"] == "positive")),
                scenes=dict(Counter(f"{c['label']}/{c['scene']}" for c in clips).most_common()),
                pilot_clips_excluded=len(pilot), overlap_with_pilot=len(pilot & {c["file_name"] for c in clips}),
                ref_time_check=rcheck, neg_ref_clipped=sum(bool(c.get("ref_clipped")) for c in clips),
                requests=len(reqs), per_n=len(reqs) // 3,
                gt_by_offset={str(o): dict(Counter(r["gt"] for r in reqs if r["offset"] == o and r["n"] == 9))
                              for o in OFFSETS},
                unique_frames=len(uniq), short_span_log=logs,
                all_causal=all(r["last_pts_le_end"] for r in reqs),
                headers=sorted({r["header"] for r in reqs}), clips=clips)
    (OUT / "d3_sample.json").write_text(json.dumps(summ, indent=1, default=str))
    print(json.dumps({k: v for k, v in summ.items() if k not in ("clips", "short_span_log", "scenes")}, default=str))
    print("short spans", len(logs))


if __name__ == "__main__":
    main()
