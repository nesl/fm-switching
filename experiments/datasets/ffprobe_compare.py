#!/usr/bin/env python3
"""ffprobe every video of a pulled dataset and compare with flash's ffprobe.jsonl (pulled with the dataset).

Run (one process, low priority): nice -n 19 ionice -c3 python3 experiments/datasets/ffprobe_compare.py <dataset> [--sha]
Fields as flash's records: path, size, ok, duration (first video stream; container duration kept as
format_duration), width, height, fps (r_frame_rate rounded to 3 decimals; avg_frame_rate kept), codec, n_audio. Flash paths /mnt/ssd/hf_models/datasets/... map to
/home/pragya/data/datasets/.... --sha: sha256 of every video, compared with the HF LFS sha256 in flash's
preflight.json where the video is itself an HF file (RTV-Bench). Reports differences; resolves nothing.
Writes /home/pragya/data/datasets/<ds>/ffprobe_h100.jsonl and results/datasets/ffprobe_check_h100_<ds>.json.
"""
import hashlib
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path("/home/pragya/data/datasets")
FLASH_ROOT = "/mnt/ssd/hf_models/datasets"
RES = Path(__file__).resolve().parents[2] / "results/datasets"
VIDEO_DIRS = {"ovo_bench": "src_videos", "rtv_bench": "hf/videos"}
HF = {"rtv_bench": "RTVBench/RTV-Bench"}
TOL = 1e-6


def fps(s):
    try:
        f = Fraction(s)
        return float(f) if f else None
    except (ValueError, ZeroDivisionError):
        return None


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)],
                       capture_output=True, text=True)
    rec = dict(path=str(p).replace(str(ROOT), FLASH_ROOT), size=p.stat().st_size, ok=r.returncode == 0)
    if r.returncode != 0:
        rec["error"] = r.stderr.strip()[:300]
        return rec
    j = json.loads(r.stdout)
    v = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]
    d = j.get("format", {}).get("duration")
    vd = v[0].get("duration") if v else None
    rf = fps(v[0].get("r_frame_rate")) if v else None
    # Flash's definitions (found by comparison, 2026-11-05): duration = first video stream's duration (container
    # duration if absent), fps = r_frame_rate rounded to 3 decimals. Container duration and avg_frame_rate also kept.
    rec.update(duration=float(vd) if vd else (float(d) if d else None), format_duration=float(d) if d else None,
               width=v[0].get("width") if v else None, height=v[0].get("height") if v else None,
               fps=round(rf, 3) if rf else None, r_fps=rf, avg_fps=fps(v[0].get("avg_frame_rate")) if v else None,
               codec=v[0].get("codec_name") if v else None, n_audio=len(a))
    return rec


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ds = sys.argv[1]
    do_sha = "--sha" in sys.argv
    base = ROOT / ds
    vids = sorted(p for p in (base / VIDEO_DIRS[ds]).rglob("*.mp4") if p.is_file())
    flash = {r["path"]: r for r in map(json.loads, open(base / "ffprobe.jsonl"))}
    lfs = {}
    if do_sha and ds in HF:
        pre = json.load(open("/home/pragya/data/flash/meta/preflight.json"))[HF[ds]]
        lfs = {f"{FLASH_ROOT}/{ds}/hf/{f['path']}": f["lfs_sha256"] for f in pre["files"] if f["lfs_sha256"]}
    out = base / "ffprobe_h100.jsonl"
    rows, diffs = [], []
    with open(out, "w") as fo:
        for i, p in enumerate(vids):
            r = probe(p)
            if do_sha:
                r["sha256"] = sha256(p)
                if r["path"] in lfs:
                    r["hf_sha256_match"] = r["sha256"] == lfs[r["path"]]
            fo.write(json.dumps(r) + "\n")
            rows.append(r)
            f = flash.get(r["path"])
            if f is None:
                diffs.append(dict(path=r["path"], issue="not in flash's ffprobe.jsonl"))
                continue
            for k in ("size", "ok", "width", "height", "codec", "n_audio"):
                if f.get(k) != r.get(k):
                    diffs.append(dict(path=r["path"], field=k, flash=f.get(k), h100=r.get(k)))
            for k in ("duration", "fps"):
                if (f.get(k) is None) != (r.get(k) is None) or (f.get(k) is not None and abs(f[k] - r[k]) > TOL):
                    diffs.append(dict(path=r["path"], field=k, flash=f.get(k), h100=r.get(k),
                                      h100_r_fps=r.get("r_fps") if k == "fps" else None))
            if (i + 1) % 100 == 0:
                print(f"{ds}: {i + 1}/{len(vids)}", flush=True)
    missing = sorted(set(flash) - {r["path"] for r in rows})
    res = dict(dataset=ds, videos=len(rows), flash_videos=len(flash), ffprobe_failures=[r for r in rows if not r["ok"]],
               flash_failures=[r for r in flash.values() if not r.get("ok")], differences=diffs[:200],
               n_differences=len(diffs), in_flash_not_h100=missing[:50], n_in_flash_not_h100=len(missing),
               sha256_checked=do_sha, hf_sha256_mismatch=[r["path"] for r in rows if r.get("hf_sha256_match") is False],
               hf_sha256_matched=sum(bool(r.get("hf_sha256_match")) for r in rows))
    RES.mkdir(parents=True, exist_ok=True)
    (RES / f"ffprobe_check_h100_{ds}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()}))


if __name__ == "__main__":
    main()
