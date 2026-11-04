#!/usr/bin/env python3
"""StudyD0-nexar: verify the downloaded Nexar collision-prediction dataset against its card / paper (read-only).

Run (CPU only):  ~/.venvs/dashcam/bin/python -I experiments/data_check/nexar_check.py [--data DIR] [--jobs N]
Reads every metadata CSV, ffprobes every video, fully decodes every video (ffmpeg -v error -f null) to find corrupt
files, and hashes every source file (SHA-256). Writes:
  results/data_check/nexar_check.json            all computed values
  results/data_check/nexar_sha256_manifest.txt   sha256  size  relative path   (every file in the HF snapshot)
Nothing in the data directory is modified.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/data_check"
SPLITS = ["train", "test-public", "test-private"]
LABELS = ["positive", "negative"]
Q = [0, 5, 25, 50, 75, 95, 100]


def stats(x):
    x = np.asarray([v for v in x if v is not None], float)
    if not len(x):
        return dict(n=0)
    p = np.percentile(x, Q)
    return dict(n=int(len(x)), min=float(p[0]), p5=float(p[1]), p25=float(p[2]), p50=float(p[3]), p75=float(p[4]),
                p95=float(p[5]), max=float(p[6]), mean=float(x.mean()), sd=float(x.std(ddof=1)) if len(x) > 1 else 0.0)


def fnum(s):
    s = (s or "").strip()
    return float(s) if s else None


def ffprobe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)],
                       capture_output=True, text=True)
    out = dict(probe_ok=r.returncode == 0 and bool(r.stdout.strip()), probe_err=r.stderr.strip()[:300] or None)
    if out["probe_ok"]:
        j = json.loads(r.stdout)
        v = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
        fmt = j.get("format", {})
        out["duration_s"] = fnum(fmt.get("duration"))
        out["size_bytes"] = int(fmt.get("size", 0))
        out["format"] = fmt.get("format_name")
        if v:
            s = v[0]
            num, den = (s.get("avg_frame_rate") or "0/1").split("/")
            rn, rd = (s.get("r_frame_rate") or "0/1").split("/")
            out.update(width=s.get("width"), height=s.get("height"), codec=s.get("codec_name"),
                       pix_fmt=s.get("pix_fmt"), avg_fps=float(num) / float(den) if float(den) else None,
                       r_fps=float(rn) / float(rd) if float(rd) else None,
                       nb_frames=int(s["nb_frames"]) if s.get("nb_frames", "").isdigit() else None,
                       stream_duration_s=fnum(s.get("duration")))
        out["n_audio"] = sum(s.get("codec_type") == "audio" for s in j.get("streams", []))
    return out


def decode(p):
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "2", "-i", str(p), "-f", "null", "-"],
                       capture_output=True, text=True)
    return dict(decode_rc=r.returncode, decode_err=r.stderr.strip()[:300] or None)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path.home() / "data/dashcam/nexar/hf"))
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    root = Path(a.data)
    assert (root.parent / "DOWNLOAD_COMPLETE").exists(), "download not marked complete (size-verified) — not checking"
    res = dict(data_dir=str(root), at=datetime.now().isoformat())

    # ---- layout
    files = sorted(p for p in root.rglob("*") if p.is_file() and ".cache" not in p.parts)
    res["layout"] = dict(top_level=sorted(p.name for p in root.iterdir() if p.name != ".cache"),
                         n_files=len(files), total_bytes=sum(p.stat().st_size for p in files),
                         by_dir={str(d.relative_to(root)): dict(
                             mp4=len(list(d.glob("*.mp4"))), other=sorted(p.name for p in d.iterdir()
                                                                          if p.suffix != ".mp4"))
                                 for s in SPLITS for d in [root / s / l for l in LABELS] if d.exists()})

    # ---- metadata
    rows = []
    for s in SPLITS:
        for l in LABELS:
            m = root / s / l / "metadata.csv"
            if not m.exists():
                continue
            with open(m, newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames
                for r in rd:
                    rows.append(dict(r, split=s, label_dir=l, _cols=tuple(cols)))
    res["metadata_columns"] = {f"{r['split']}/{r['label_dir']}": list(r["_cols"]) for r in rows}
    per = {}
    for s in SPLITS:
        for l in LABELS:
            rs = [r for r in rows if r["split"] == s and r["label_dir"] == l]
            if not rs:
                continue
            d = root / s / l
            names = {r["file_name"] for r in rs}
            mp4 = {p.name for p in d.glob("*.mp4")}
            per[f"{s}/{l}"] = dict(
                rows=len(rs), mp4_files=len(mp4), rows_without_file=sorted(names - mp4)[:20],
                n_rows_without_file=len(names - mp4), files_without_row=sorted(mp4 - names)[:20],
                n_files_without_row=len(mp4 - names), duplicate_rows=len(rs) - len(names),
                missing={c: sum(not (r.get(c) or "").strip() for r in rs) for c in rs[0]["_cols"]},
                light=dict(Counter(r.get("light_conditions") for r in rs)),
                weather=dict(Counter(r.get("weather") for r in rs)), scene=dict(Counter(r.get("scene") for r in rs)),
                time_to_accident=dict(Counter(r.get("time_to_accident") for r in rs)))
    res["per_split"] = per
    res["rows_total"] = len(rows)
    res["videos_total"] = sum(v["mp4_files"] for v in per.values())
    extra_label_cols = sorted({c for r in rows for c in r["_cols"]} - {"file_name", "time_of_event", "time_of_alert",
                                                                       "light_conditions", "weather", "scene",
                                                                       "time_to_accident"})
    res["extra_columns_beyond_card"] = extra_label_cols

    # ---- ffprobe + decode + sha256 over every video (parallel)
    vids = [(r, root / r["split"] / r["label_dir"] / r["file_name"]) for r in rows]
    vids = [(r, p) for r, p in vids if p.exists()]

    def work(rp):
        r, p = rp
        return dict(ffprobe(p), **decode(p), rel=str(p.relative_to(root)))
    with ThreadPoolExecutor(a.jobs) as ex:
        probes = list(ex.map(work, vids))
    with ThreadPoolExecutor(a.jobs) as ex:
        hashes = list(ex.map(sha, files))
    man = OUT / "nexar_sha256_manifest.txt"
    with open(man, "w") as f:
        f.write(f"# sha256  size_bytes  path (relative to {root}); HF dataset nexar-ai/nexar_collision_prediction; "
                f"{datetime.now().isoformat()}\n")
        for p, h in zip(files, hashes):
            f.write(f"{h}  {p.stat().st_size}  {p.relative_to(root)}\n")
    res["sha256_manifest"] = str(man.relative_to(REPO))
    rev = sorted((root / ".cache/huggingface/download").rglob("*.metadata"))[:1]
    res["hf_snapshot_note"] = "local_dir download (hf download --local-dir); per-file commit hashes in .cache metadata"
    if rev:
        res["hf_commit_from_cache_metadata"] = rev[0].read_text().splitlines()[0]

    for (r, _), pr in zip(vids, probes):
        r["probe"] = pr
    bad = [dict(rel=pr["rel"], probe_ok=pr["probe_ok"], probe_err=pr["probe_err"], decode_rc=pr["decode_rc"],
                decode_err=pr["decode_err"]) for pr in probes if not pr["probe_ok"] or pr["decode_rc"] != 0
           or pr["decode_err"]]
    res["corrupt_or_unreadable"] = dict(n=len(bad), n_videos=len(probes),
                                        frac=len(bad) / max(1, len(probes)), items=bad[:50])

    def vstat(rs):
        ps = [r["probe"] for r in rs if r.get("probe", {}).get("probe_ok")]
        hist = np.histogram([p["duration_s"] for p in ps], bins=np.arange(0, 66, 2))
        return dict(duration_s=stats([p["duration_s"] for p in ps]),
                    duration_hist_2s=dict(zip([f"{int(b)}-{int(b) + 2}" for b in hist[1][:-1]],
                                              [int(c) for c in hist[0]])),
                    avg_fps=dict(Counter(round(p["avg_fps"], 2) for p in ps if p.get("avg_fps")).most_common(8)),
                    r_fps=dict(Counter(round(p["r_fps"], 2) for p in ps if p.get("r_fps")).most_common(8)),
                    resolution=dict(Counter(f"{p.get('width')}x{p.get('height')}" for p in ps)),
                    codec=dict(Counter(p.get("codec") for p in ps)), pix_fmt=dict(Counter(p.get("pix_fmt") for p in ps)),
                    audio_streams=dict(Counter(p.get("n_audio") for p in ps)))
    res["video_props"] = {k: vstat([r for r in rows if f"{r['split']}/{r['label_dir']}" == k]) for k in per}
    res["video_props"]["train_all"] = vstat([r for r in rows if r["split"] == "train"])

    # ---- timing fields
    tim = {}
    for k in per:
        rs = [r for r in rows if f"{r['split']}/{r['label_dir']}" == k]
        toe = [fnum(r["time_of_event"]) for r in rs]
        toa = [fnum(r["time_of_alert"]) for r in rs]
        dur = [r.get("probe", {}).get("duration_s") for r in rs]
        both = [(e, al, d) for e, al, d in zip(toe, toa, dur) if e is not None and al is not None]
        t = dict(n=len(rs), has_time_of_event=sum(e is not None for e in toe),
                 has_time_of_alert=sum(x is not None for x in toa))
        if both:
            gap = [e - al for e, al, _ in both]
            after = [d - e for e, _, d in both if d is not None]
            t.update(time_of_event=stats([e for e, _, _ in both]), time_of_alert=stats([al for _, al, _ in both]),
                     event_minus_alert=stats(gap), n_alert_after_event=sum(g < 0 for g in gap),
                     n_alert_equals_event=sum(g == 0 for g in gap),
                     footage_after_event=stats(after),
                     frac_after_event_ge_1s=float(np.mean([x >= 1 for x in after])) if after else None,
                     frac_after_event_ge_2s=float(np.mean([x >= 2 for x in after])) if after else None,
                     n_event_beyond_duration=sum(x < 0 for x in after),
                     footage_before_alert=stats([al for _, al, _ in both]),
                     frac_before_alert_ge_3s=float(np.mean([al >= 3 for _, al, _ in both])),
                     frac_before_event_ge_4s=float(np.mean([e >= 4 for e, _, _ in both])))
        tim[k] = t
    res["timing"] = tim

    # ---- test clips: does each clip end time_to_accident before the event?
    tc = {}
    for s in ("test-public", "test-private"):
        rs = [r for r in rows if r["split"] == s and r["label_dir"] == "positive" and r.get("probe", {}).get("probe_ok")
              and fnum(r["time_of_event"]) is not None]
        if rs:
            tc[s] = dict(event_minus_duration_minus_tta=stats(
                [fnum(r["time_of_event"]) - r["probe"]["duration_s"] - fnum(r["time_to_accident"]) for r in rs]),
                duration=stats([r["probe"]["duration_s"] for r in rs]))
    res["test_clip_timebase"] = tc

    # ---- negatives
    res["negatives"] = {k: dict(rows=v["rows"], time_of_event_present=v["rows"] - v["missing"].get("time_of_event", 0),
                                time_of_alert_present=v["rows"] - v["missing"].get("time_of_alert", 0),
                                time_to_accident=v["time_to_accident"])
                        for k, v in per.items() if k.endswith("negative")}
    res["collision_type_field"] = ("absent: no metadata column distinguishes collision from near-collision"
                                   if not extra_label_cols else f"extra columns present: {extra_label_cols}")
    for r in rows:
        r.pop("_cols", None)
    (OUT / "nexar_check.json").write_text(json.dumps(dict(res, rows=rows), indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("rows_total", "videos_total", "corrupt_or_unreadable")}, default=str)[:2000])


if __name__ == "__main__":
    sys.exit(main())
