#!/usr/bin/env python3
"""StudyB1-h100 input check (CPU): seek-based frame selection (b1_common.select_frames) must pick exactly the frames a
FULL sequential decode picks (latest decoded frame with pts <= target), for RECENT and HISTORY targets, on videos
covering every (codec, height) group present, plus the longest videos. Also times HISTORY renders.
Writes results/benchmarks/study_b1_h100/frame_selection_check.json.
Run: nice -n 10 ~/.venvs/fm-switching-vllm/bin/python experiments/benchmarks/b1_check_frames.py [--jobs 16]
"""
import argparse
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b1_common as B  # noqa: E402

OUT = HERE.parents[1] / "results/benchmarks/study_b1_h100"


def full_decode_pts(path, upto):
    import av
    ts = []
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for fr in c.decode(s):
            if fr.pts is None:
                continue
            t = float(fr.pts * s.time_base)
            ts.append(t)
            if t > upto + 1.0:
                break
    return sorted(ts)


def ref_select(ts, tg):
    best = None
    for t in ts:
        if t <= tg + 1e-9:
            best = t
        else:
            break
    return best if best is not None else ts[0]


def check(job):
    path, t, inp = job
    tg, _ = B.targets(t, B.INPUTS[inp])
    t0 = time.time()
    got = [ts for ts, _ in B.select_frames(path, tg, encode=False)]
    t_seek = time.time() - t0
    ref_ts = full_decode_pts(path, t)
    ref = [ref_select(ref_ts, x) for x in tg]
    return dict(path=path, t=t, input=inp, match=all(abs(a - b) < 1e-9 for a, b in zip(got, ref)),
                mismatches=[(x, a, b) for x, a, b in zip(tg, got, ref) if abs(a - b) >= 1e-9][:5],
                max_pts_le_t=max(got) <= t + 1e-6, select_s=round(t_seek, 2))


def timing(job):
    path, t = job
    tg, _ = B.targets(t, 37)
    t0 = time.time()
    fr = B.render(path, tg)
    return dict(path=path, t=t, render_s=round(time.time() - t0, 2), n_distinct=len({x[0] for x in fr}),
                max_pts_le_t=max(x[0] for x in fr) <= t + 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    rng = random.Random(0)
    groups = {}
    for ds, base in (("ovo_bench", "src_videos/src_videos/"), ("rtv_bench", "hf/videos/")):
        for l in open(B.DATA / ds / "ffprobe_h100.jsonl"):
            r = json.loads(l)
            p = str(B.DATA / ds / r["path"].split(f"/{ds}/", 1)[1])
            groups.setdefault((ds, r["codec"], r["height"]), []).append((p, r["duration"]))
    jobs = []
    for k in sorted(groups, key=str):
        cand = sorted(groups[k], key=lambda x: x[1])  # shortest in the group keeps the full decode cheap
        p, d = cand[0]
        if d is None or d < 4:
            continue
        for inp in ("RECENT", "HISTORY"):
            jobs.append((p, round(rng.uniform(3.0, min(d, 240.0)), 3), inp))
        jobs.append((p, 1.7, "RECENT"))  # short-span case (t < 3)
    allv = [x for v in groups.values() for x in v if x[1]]
    longest = sorted(allv, key=lambda x: -x[1])[:4]
    tjobs = [(p, round(d * 0.9, 3)) for p, d in longest]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = list(ex.map(check, jobs))
        tim = list(ex.map(timing, tjobs))
    out = dict(n_checks=len(res), all_match=all(r["match"] for r in res), all_le_t=all(r["max_pts_le_t"] for r in res),
               groups=len(groups), checks=res, history_render_timing=tim)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frame_selection_check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("checks",)}, indent=1)[:2500])
    bad = [r for r in res if not r["match"]]
    print("mismatching:", json.dumps(bad[:5])[:1500])


if __name__ == "__main__":
    main()
