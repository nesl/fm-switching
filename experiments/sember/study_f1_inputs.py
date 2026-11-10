#!/usr/bin/env python3
"""StudyF1-shortwin inputs (CPU; dashcam or vLLM venv, needs PyAV + PIL). Pre-registered in research/EXPERIMENTS.md.

For each of the 845 S-EMBER questions (StudyR1's set): decode the source mp4 at its native rate (12 fps) and keep the
frames whose decode timestamp (pts) lies in [qt - 3, qt].
  N = 1   the last decoded frame with pts <= qt
  N = 3/9 evenly spaced targets lo + (qt - lo) i / (N - 1), lo = qt - 3, each mapped to the nearest decoded frame in
          the window (ties -> earlier frame), oldest first, de-duplicated
Each frame is resized to 560x560 with PIL LANCZOS, aspect not preserved (StudyDevFast / DevOne's resize_560_b64), and
saved as a lossless PNG (PIL default compression) under ~/.cache/fm-switching/f1_frames/<video_id>/<frame_index>.png.
Header (only frame count and span; no clip timestamps or file names):
  N = 1  "The following is the most recent camera frame."
  N > 1  "The following are {N} camera frames evenly spaced over the last 3 seconds, oldest first."
Writes results/sember/study_f1/f1_inputs_manifest.jsonl (per question x N: frame indices, pts, sha256, header, R1
text) and f1_frames_sha256.json (every PNG), then packs frames + manifests into ~/.cache/fm-switching/f1_orin.tar.
"""
import argparse
import gzip
import hashlib
import json
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VIDEOS = Path.home() / ".cache/fm-switching/sember_videos"
FR = Path.home() / ".cache/fm-switching/f1_frames"
OUT = REPO / "results/sember/study_f1"
MAN = OUT / "f1_inputs_manifest.jsonl"
SHA = OUT / "f1_frames_sha256.json"
TAR = Path.home() / ".cache/fm-switching/f1_orin.tar"
R1MAN = REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
SPAN = 3.0
NS = (1, 3, 9)
SIZE = (560, 560)


def header(n):
    return ("The following is the most recent camera frame." if n == 1 else
            f"The following are {n} camera frames evenly spaced over the last 3 seconds, oldest first.")


def pick(frames, qt, n):
    """frames: [(idx, pts)] sorted, all pts in [qt-3, qt]."""
    if n == 1:
        return [frames[-1]]
    lo = qt - SPAN
    out = []
    for i in range(n):
        tgt = lo + (qt - lo) * i / (n - 1)
        best = min(frames, key=lambda f: (abs(f[1] - tgt), f[1]))
        if best not in out:
            out.append(best)
    return out


def do_video(args):
    import av
    from PIL import Image
    vid, qs = args
    qts = sorted({q["qt"] for q in qs})
    lo_all, hi_all = min(qts) - SPAN - 1e-6, max(qts) + 1e-6
    keep = {}                                     # idx -> (pts, PIL image) for frames inside any window
    with av.open(str(VIDEOS / f"{vid}.mp4")) as c:
        st = c.streams.video[0]
        st.thread_type = "AUTO"
        idx = -1
        for fr in c.decode(st):
            idx += 1
            t = float(fr.pts * st.time_base)
            if t > hi_all:
                break
            if t < lo_all or not any(q - SPAN - 1e-6 <= t <= q + 1e-6 for q in qts):
                continue
            keep[idx] = (t, fr.to_image())
    ordered = sorted((i, p) for i, (p, _) in keep.items())
    rows, used = [], set()
    for q in qs:
        win = [(i, p) for i, p in ordered if q["qt"] - SPAN - 1e-6 <= p <= q["qt"] + 1e-6]
        assert win, (vid, q["qid"])
        for n in NS:
            sel = pick(win, q["qt"], n)
            used.update(i for i, _ in sel)
            rows.append(dict(question_id=q["qid"], video_id=vid, question_time=q["qt"], n=n, n_frames=len(sel),
                             frame_index=[i for i, _ in sel], frame_pts=[round(p, 6) for _, p in sel],
                             window_frames=len(win), header=header(len(sel) if n > 1 else 1)))
    d = FR / vid
    d.mkdir(parents=True, exist_ok=True)
    sha = {}
    for i in sorted(used):
        p = d / f"{i:06d}.png"
        if not p.exists():
            keep[i][1].convert("RGB").resize(SIZE, Image.LANCZOS).save(p, format="PNG")
        sha[f"{vid}/{i:06d}.png"] = hashlib.sha256(p.read_bytes()).hexdigest()
    for r in rows:
        r["frame_sha256"] = [sha[f"{vid}/{i:06d}.png"] for i in r["frame_index"]]
        r["frame_files"] = [f"{vid}/{i:06d}.png" for i in r["frame_index"]]
    return rows, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--tar", action="store_true", help="only (re)build the Orin tar")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not a.tar:
        r1 = {}
        for l in gzip.open(R1MAN, "rt"):
            r = json.loads(l)
            if r["construction"] == "RECENT":
                r1[r["question_id"]] = r
        assert len(r1) == 845
        byv = {}
        for q, r in r1.items():
            byv.setdefault(r["video_id"], []).append(dict(qid=q, qt=float(r["question_time"])))
        rows, sha = [], {}
        with ProcessPoolExecutor(a.workers) as ex:
            for k, (rs, s) in enumerate(ex.map(do_video, sorted(byv.items())), 1):
                rows += rs
                sha.update(s)
                if k % 20 == 0:
                    print(f"{k}/{len(byv)} videos", flush=True)
        for r in rows:
            r1r = r1[r["question_id"]]
            r.update(question_category=r1r["question_category"], correct_letter=r1r["correct_letter"], text=r1r["text"])
        rows.sort(key=lambda r: (r["video_id"], r["question_time"], r["question_id"], r["n"]))
        assert len(rows) == 845 * len(NS)
        with open(MAN, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        SHA.write_text(json.dumps(dict(n_files=len(sha), size=list(SIZE), resize="PIL LANCZOS, aspect not preserved",
                                       format="PNG lossless (PIL default)", files=sha), indent=0))
        print(f"{len(rows)} rows, {len(sha)} unique PNGs")
    with tarfile.open(TAR, "w") as t:
        t.add(MAN, arcname="f1/f1_inputs_manifest.jsonl")
        t.add(SHA, arcname="f1/f1_frames_sha256.json")
        t.add(FR, arcname="f1/frames")
    print(f"tar {TAR} {TAR.stat().st_size} bytes")


if __name__ == "__main__":
    main()
