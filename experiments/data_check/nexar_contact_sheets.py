#!/usr/bin/env python3
"""StudyD0-nexar contact sheets — FOR HUMAN INSPECTION ONLY; never used to select or exclude clips.

Sample (seed 0, random.Random(0)): the metadata has no collision / near-collision field (see nexar_check.json), so per
the spec's fallback: 10 train positives + 5 train negatives, each drawn with Random(0).sample from the file-name-sorted
list of that label (positives first, then negatives, same generator).
Each sheet: row 1 = 8 frames evenly across the whole clip (t_k = k * (D - 2/fps) / 7, D = video-stream duration); for positives row 2 = 8 frames
evenly across [time_of_event - 4 s, time_of_event + 2 s] clipped to [0, D - 2/fps]. Every frame is labelled with its
timestamp and its offset from time_of_event ("ev+x.xxs"); frames at or after time_of_alert carry a ">=alert" tag and the frame
closest to time_of_alert gets an orange border; the header states time_of_event, time_of_alert and duration.
Frames are decoded with ffmpeg (accurate seek), downscaled, sheet saved as JPEG with quality lowered until < 500 KB.
Run: ~/.venvs/dashcam/bin/python -I experiments/data_check/nexar_contact_sheets.py
"""
import csv
import io
import json
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
ROOT = Path.home() / "data/dashcam/nexar/hf"
OUT = REPO / "results/data_check/contact_sheets"
TW, TH, HDR, LBL = 240, 135, 34, 30
LIMIT = 500 * 1024


def font(n):
    try:
        return ImageFont.load_default(size=n)
    except TypeError:
        return ImageFont.load_default()


def meta(label):
    with open(ROOT / "train" / label / "metadata.csv", newline="") as f:
        return sorted(csv.DictReader(f), key=lambda r: r["file_name"])


def probe(p):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                                   str(p)], capture_output=True, text=True).stdout)
    v = [s for s in j["streams"] if s["codec_type"] == "video"][0]
    n, d = v["avg_frame_rate"].split("/")
    sd = float(v.get("duration") or j["format"]["duration"])     # video-stream duration (format can be longer)
    return min(sd, float(j["format"]["duration"])), float(n) / float(d)


def frame(p, t):
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    if not r.stdout:
        return None
    return Image.open(io.BytesIO(r.stdout)).convert("RGB").resize((TW, TH), Image.LANCZOS)


def even(a, b, n=8):
    return [a + k * (b - a) / (n - 1) for k in range(n)]


def sheet(r, label, idx):
    p = ROOT / "train" / label / r["file_name"]
    dur, fps = probe(p)
    last = dur - 2.0 / fps          # last decodable frame time (seek to D - 1/fps can return nothing)
    toe = float(r["time_of_event"]) if r["time_of_event"] else None
    toa = float(r["time_of_alert"]) if r["time_of_alert"] else None
    rows = [("whole clip", even(0.0, last))]
    if toe is not None:
        a, b = max(0.0, toe - 4.0), min(last, toe + 2.0)
        rows.append((f"event window [{a - toe:+.2f}, {b - toe:+.2f}] s", even(a, b)))
    W = 8 * TW
    H = HDR + len(rows) * (LBL + TH + 16)
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    f1, f2 = font(16), font(12)
    head = (f"Nexar train/{label}/{r['file_name']}  |  duration {dur:.2f} s @ {fps:.2f} fps  |  "
            f"time_of_event {r['time_of_event'] or '—'}  time_of_alert {r['time_of_alert'] or '—'}  |  "
            f"light {r['light_conditions']}, weather {r['weather']}, scene {r['scene']}  |  INSPECTION ONLY")
    dr.text((6, 8), head, fill="black", font=f1)
    y = HDR
    used = []
    for title, ts in rows:
        dr.text((6, y + 2), title, fill=(60, 60, 60), font=f2)
        y += 16
        near = min(range(len(ts)), key=lambda k: abs(ts[k] - toa)) if toa is not None else None
        for k, t in enumerate(ts):
            x = k * TW
            fr = frame(p, t) or frame(p, max(0.0, t - 0.1))
            if fr is not None:
                im.paste(fr, (x, y + LBL))
            else:
                dr.text((x + 6, y + LBL + 50), "decode failed", fill="red", font=f2)
            lab = f"t={t:.2f}s"
            if toe is not None:
                lab += f"  ev{t - toe:+.2f}s"
            if toa is not None and t >= toa:
                lab += "  >=alert"
            dr.text((x + 4, y + 2), lab, fill="black", font=f2)
            if toa is not None and len(rows) > 1 and title != "whole clip" and k == near:
                dr.rectangle([x + 1, y + LBL + 1, x + TW - 2, y + LBL + TH - 2], outline=(255, 140, 0), width=4)
            used.append(dict(row=title, t=round(t, 3), offset_from_event=None if toe is None else round(t - toe, 3),
                             decoded=fr is not None))
        y += LBL + TH
    q = 85
    while True:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=q, optimize=True)
        if buf.tell() < LIMIT or q <= 30:
            break
        q -= 5
    name = f"nexar_{label}_{idx:02d}_{r['file_name'].replace('.mp4', '')}.jpg"
    (OUT / name).write_bytes(buf.getvalue())
    return dict(file=str((OUT / name).relative_to(REPO)), clip=f"train/{label}/{r['file_name']}", bytes=buf.tell(),
                jpeg_quality=q, duration_s=dur, fps=fps, time_of_event=toe, time_of_alert=toa, frames=used)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    pos, neg = meta("positive"), meta("negative")
    picks = [("positive", r) for r in rng.sample(pos, 10)] + [("negative", r) for r in rng.sample(neg, 5)]
    out = [sheet(r, lab, i) for i, (lab, r) in enumerate(picks, 1)]
    (REPO / "results/data_check/nexar_contact_sheets.json").write_text(json.dumps(dict(
        seed=0, rule="random.Random(0).sample(sorted train positives, 10) then .sample(sorted train negatives, 5); "
                     "collision type unavailable in metadata", purpose="inspection only; must not select clips",
        sheets=out), indent=1))
    print("\n".join(f"{o['file']} {o['bytes'] // 1024} KB q{o['jpeg_quality']}" for o in out))


if __name__ == "__main__":
    main()
