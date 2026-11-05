#!/usr/bin/env python3
"""StudyD2-nexar pilot — split, pilot sample, reference times, causal frame rendering (CPU only; no model).

Run: ~/.venvs/dashcam/bin/python -I experiments/dashcam/d2_prepare.py [--jobs 16]
Pre-registered in research/EXPERIMENTS.md (StudyD2-nexar).

SPLIT   Nexar TRAIN only (1,500 clips; train/{positive,negative}/metadata.csv). Seed 0. Cells = label x scene; within
        each cell clips are sorted by file name, shuffled with random.Random(0) (cells visited in sorted order, one
        generator), and allocated 50 / 20 / 30 % dev / val / test by largest remainder (ties -> dev, val, test).
SAMPLE  75 positive + 75 negative DEV clips. Per label, scene quotas are proportional to the label's dev scene counts
        (largest remainder); a quota larger than its cell is capped and the excess re-allocated to the remaining
        cells in descending-remainder order; clips drawn with random.Random(0).sample over the sorted cell. Unfillable
        cells recorded. No clip is inspected.
REF     positive: time_of_event (observed). negative: ASSIGNED — random.Random(0).choice over DEV-positive
        time_of_event values in the same duration bin (18-20 s, 38-42 s, other; duration = ffprobe video-stream
        duration from nexar_check.json), then clipped to [3, D - 2] when D >= 5 s.
OFFSETS -3, -1.5, -1, -0.5, 0, +1, +2 s; prefix end e = ref + offset.
FRAMES  N = 9 targets evenly spaced on [max(0, e - 3), e]; each target takes the LATEST decoded frame with
        pts <= target (PyAV decode timestamps; never a frame after e). Span < 3 s (e < 3) logged. Lossless PNG at
        native 1280x720 and SMALL 768x432 (PIL LANCZOS from the decoded RGB frame), stored outside the repo at
        /home/pragya/data/dashcam/d2_frames/{native,small}/<clip>/<pts_ms>.png, SHA-256 manifest in results.
Only DEV clips are decoded. Outputs in results/dashcam/study_d2_nexar/.
"""
import argparse
import csv
import gzip
import hashlib
import json
import random
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
NEX = Path.home() / "data/dashcam/nexar/hf/train"
FR = Path.home() / "data/dashcam/d2_frames"
OUT = REPO / "results/dashcam/study_d2_nexar"
CHECK = REPO / "results/data_check/nexar_check.json"
OFFSETS = [-3.0, -1.5, -1.0, -0.5, 0.0, 1.0, 2.0]
N = 9
WIN = 3.0
SMALL = (768, 432)
FRAC = (("dev", 0.5), ("val", 0.2), ("test", 0.3))


def dbin(d):
    return "18-20" if 18.0 <= d < 20.0 else ("38-42" if 38.0 <= d <= 42.0 else "other")


def alloc(n, weights):
    """Largest-remainder allocation of n over named weights (ties broken by order given)."""
    tot = sum(w for _, w in weights)
    raw = [(k, n * w / tot) for k, w in weights]
    base = {k: int(np.floor(v)) for k, v in raw}
    rest = n - sum(base.values())
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i][1] - np.floor(raw[i][1])), i))
    for i in order[:rest]:
        base[raw[i][0]] += 1
    return base


def load_meta():
    rows = []
    for lab in ("positive", "negative"):
        with open(NEX / lab / "metadata.csv", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(dict(r, label=lab))
    dur = {r["probe"]["rel"]: r["probe"] for r in json.load(open(CHECK))["rows"] if r["split"] == "train"}
    for r in rows:
        p = dur[f"train/{r['label']}/{r['file_name']}"]
        r["duration_s"] = p["duration_s"]
        r["stream_duration_s"] = p.get("stream_duration_s")
    return rows


def split(rows):
    rng = random.Random(0)
    cells = defaultdict(list)
    for r in rows:
        cells[(r["label"], r["scene"])].append(r)
    out = {}
    for key in sorted(cells):
        cl = sorted(cells[key], key=lambda r: r["file_name"])
        rng.shuffle(cl)
        a = alloc(len(cl), list(FRAC))
        i = 0
        for name, _ in FRAC:
            for r in cl[i:i + a[name]]:
                out[(r["label"], r["file_name"])] = name
            i += a[name]
    return out


def sample(dev, label, n, rng):
    cells = defaultdict(list)
    for r in dev:
        if r["label"] == label:
            cells[r["scene"]].append(r)
    scenes = sorted(cells)
    q = alloc(n, [(s, len(cells[s])) for s in scenes])
    unfilled = {}
    excess = 0
    for s in scenes:
        if q[s] > len(cells[s]):
            unfilled[s] = dict(quota=q[s], available=len(cells[s]))
            excess += q[s] - len(cells[s])
            q[s] = len(cells[s])
    while excess:
        room = [s for s in scenes if q[s] < len(cells[s])]
        if not room:
            break
        for s in sorted(room, key=lambda s: -len(cells[s])):
            if excess and q[s] < len(cells[s]):
                q[s] += 1
                excess -= 1
    picks = []
    for s in scenes:
        picks += rng.sample(sorted(cells[s], key=lambda r: r["file_name"]), q[s])
    return picks, q, unfilled


def render(job):
    """Decode one clip once; return per-offset frame selections and write unique PNGs (both resolutions)."""
    import av
    from PIL import Image
    clip, lab, ref, ends = job
    path = NEX / lab / clip
    lo = max(0.0, min(ends) - WIN - 0.5)
    hi = max(ends) + 0.05
    frames = []
    with av.open(str(path)) as c:
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
                frames.append((t, fr.to_ndarray(format="rgb24")))
    frames.sort(key=lambda x: x[0])
    ts = [t for t, _ in frames]
    sel, used = {}, {}
    for e in ends:
        a = max(0.0, e - WIN)
        targets = [a + k * (e - a) / (N - 1) for k in range(N)]
        idx = []
        for tg in targets:
            cand = [i for i, t in enumerate(ts) if t <= tg + 1e-9]
            idx.append(cand[-1] if cand else None)
        if any(i is None for i in idx):
            first = next(i for i in range(len(ts)))     # target before the first decoded frame -> first frame
            idx = [first if i is None else i for i in idx]
        sel[e] = dict(targets=targets, pts=[ts[i] for i in idx], span_s=e - a, short_span=(e - a) < WIN - 1e-6,
                      causal=all(ts[i] <= e + 1e-9 for i in idx))
        for i in idx:
            used[i] = ts[i]
    hashes = {}
    for i, t in used.items():
        key = f"{int(round(t * 1000)):07d}"
        im = Image.fromarray(frames[i][1])
        rec = {}
        for res, img in (("native", im), ("small", im.resize(SMALL, Image.LANCZOS))):
            p = FR / res / clip.replace(".mp4", "") / f"{key}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                img.save(p, format="PNG", compress_level=1)
            rec[res] = dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), size=list(img.size))
        hashes[key] = dict(pts=t, **rec)
    return clip, sel, hashes, frames[0][1].shape if frames else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_meta()
    assert len(rows) == 1500
    sp = split(rows)
    with open(OUT / "nexar_train_split_seed0.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "label", "scene", "light", "weather", "duration_s", "split"])
        for r in sorted(rows, key=lambda r: (r["label"], r["file_name"])):
            w.writerow([r["file_name"], r["label"], r["scene"], r["light_conditions"], r["weather"], r["duration_s"],
                        sp[(r["label"], r["file_name"])]])
    split_counts = {f"{k[0]}/{k[1]}": v for k, v in Counter((r["label"], sp[(r["label"], r["file_name"])])
                                                             for r in rows).items()}
    dev = [r for r in rows if sp[(r["label"], r["file_name"])] == "dev"]
    rng = random.Random(0)
    pos, qp, up = sample(dev, "positive", 75, rng)
    neg, qn, un = sample(dev, "negative", 75, rng)
    # reference times
    devpos_by_bin = defaultdict(list)
    for r in dev:
        if r["label"] == "positive":
            devpos_by_bin[dbin(r["duration_s"])].append(float(r["time_of_event"]))
    rrng = random.Random(0)
    clips = []
    for r in pos:
        clips.append(dict(file_name=r["file_name"], label="positive", scene=r["scene"], light=r["light_conditions"],
                          weather=r["weather"], duration_s=r["duration_s"], bin=dbin(r["duration_s"]),
                          ref=float(r["time_of_event"]), ref_kind="observed (time_of_event)",
                          time_of_alert=float(r["time_of_alert"])))
    for r in sorted(neg, key=lambda r: r["file_name"]):
        b = dbin(r["duration_s"])
        raw = rrng.choice(sorted(devpos_by_bin[b]))
        d = r["duration_s"]
        ref = min(max(raw, WIN), d - 2.0) if d >= WIN + 2.0 else raw
        clips.append(dict(file_name=r["file_name"], label="negative", scene=r["scene"], light=r["light_conditions"],
                          weather=r["weather"], duration_s=d, bin=b, ref=ref, ref_sampled=raw,
                          ref_clipped=ref != raw, ref_kind="ASSIGNED (sampled from dev-positive time_of_event, same "
                                                           "duration bin)", time_of_alert=None))
    # reference-time distribution check within bins
    rcheck = {}
    for b in ("18-20", "38-42", "other"):
        p = [c["ref"] for c in clips if c["label"] == "positive" and c["bin"] == b]
        n = [c["ref"] for c in clips if c["label"] == "negative" and c["bin"] == b]
        rcheck[b] = dict(n_pos=len(p), n_neg=len(n),
                         pos_q=[float(x) for x in np.percentile(p, [5, 25, 50, 75, 95])] if p else None,
                         neg_q=[float(x) for x in np.percentile(n, [5, 25, 50, 75, 95])] if n else None)
        if len(p) > 1 and len(n) > 1:
            from scipy.stats import ks_2samp
            rcheck[b]["ks_p"] = float(ks_2samp(p, n).pvalue)
    # render
    jobs = [(c["file_name"], c["label"], c["ref"], [c["ref"] + o for o in OFFSETS]) for c in clips]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = {clip: (sel, hashes, shape) for clip, sel, hashes, shape in ex.map(render, jobs)}
    reqs, uniq, logs = [], {}, []
    for c in clips:
        sel, hashes, shape = res[c["file_name"]]
        for k, h in hashes.items():
            uniq[(c["file_name"], k)] = h
        for o in OFFSETS:
            e = c["ref"] + o
            s = sel[e]
            keys = [f"{int(round(t * 1000)):07d}" for t in s["pts"]]
            if c["label"] == "negative":
                gt = "negative"
            else:
                gt = "positive" if e >= c["time_of_alert"] - 1e-9 else "unscored"
            assert s["causal"], (c["file_name"], o)
            if s["short_span"]:
                logs.append(dict(file_name=c["file_name"], offset=o, end=e, span_s=s["span_s"]))
            reqs.append(dict(request_id=f"{c['file_name'].replace('.mp4', '')}_{o:+.1f}", file_name=c["file_name"],
                             label=c["label"], scene=c["scene"], offset=o, ref=c["ref"], end=e,
                             time_of_alert=c["time_of_alert"], gt=gt, frame_keys=keys, frame_pts=s["pts"],
                             targets=s["targets"], span_s=s["span_s"], short_span=s["short_span"],
                             last_pts_le_end=s["causal"],
                             native_sha256=[hashes[k]["native"]["sha256"] for k in keys],
                             small_sha256=[hashes[k]["small"]["sha256"] for k in keys],
                             native_size=hashes[keys[0]]["native"]["size"], small_size=hashes[keys[0]]["small"]["size"],
                             decoded_shape=list(shape)))
    with open(OUT / "pilot_requests.jsonl", "w") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    with gzip.open(OUT / "frames_sha256_manifest.jsonl.gz", "wt") as f:
        for (clip, k), h in sorted(uniq.items()):
            f.write(json.dumps(dict(file_name=clip, key=k, pts=h["pts"],
                                    native_sha256=h["native"]["sha256"], small_sha256=h["small"]["sha256"],
                                    native_path=h["native"]["path"], small_path=h["small"]["path"])) + "\n")
    summ = dict(split_counts=split_counts, split_rule=__doc__.split("SPLIT")[1].split("SAMPLE")[0].strip(),
                sample=dict(pos_quota=qp, neg_quota=qn, pos_unfilled=up, neg_unfilled=un,
                            pos_scene=dict(Counter(c["scene"] for c in clips if c["label"] == "positive")),
                            neg_scene=dict(Counter(c["scene"] for c in clips if c["label"] == "negative"))),
                clips=clips, ref_time_check=rcheck,
                neg_ref_clipped=sum(bool(c.get("ref_clipped")) for c in clips),
                requests=len(reqs), gt_counts=dict(Counter(r["gt"] for r in reqs)),
                gt_by_offset={str(o): dict(Counter(r["gt"] for r in reqs if r["offset"] == o)) for o in OFFSETS},
                unique_frames=len(uniq), short_span_log=logs, all_causal=all(r["last_pts_le_end"] for r in reqs),
                frames_dir=str(FR), small_size=list(SMALL), offsets=OFFSETS, n_frames=N, window_s=WIN)
    (OUT / "pilot_sample.json").write_text(json.dumps(summ, indent=1, default=str))
    print(json.dumps({k: summ[k] for k in ("split_counts", "requests", "gt_counts", "unique_frames", "all_causal",
                                           "neg_ref_clipped")}, default=str))
    print("unfilled", up, un, "short spans", len(logs))
    print(json.dumps(rcheck, indent=0)[:1500])


if __name__ == "__main__":
    main()
