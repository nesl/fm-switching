import argparse, csv, glob, hashlib, json, os, re, subprocess, sys, tarfile, zipfile
import collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path("/mnt/ssd/hf_models/datasets")
FFPROBE = "/home/pragya/miniconda3/envs/media/bin/ffprobe"
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".MP4"}
NAMES = ["rtv_bench", "herbench", "ovo_bench", "streaming_bench"]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


# ---------------- archives ----------------

def test_archives(name):
    out = []
    base = ROOT / name
    for p in sorted(base.rglob("*.zip")):
        try:
            with zipfile.ZipFile(p) as z:
                bad = z.testzip()
            out.append({"archive": str(p), "type": "zip", "ok": bad is None,
                        "first_bad": bad, "members": None})
        except Exception as e:
            out.append({"archive": str(p), "type": "zip", "ok": False,
                        "error": f"{type(e).__name__}: {e}"})
    # split tars: concatenated parts
    for pat, label in [("src_videos.tar.parta*", "src_videos.tar"),
                       ("videos/videos.tar.part.*", "videos.tar")]:
        # .cache/huggingface/download/ holds .lock/.metadata sidecars with the same
        # names; concatenating those into the stream corrupts it.
        parts = sorted(q for q in base.rglob(pat)
                       if ".cache" not in q.parts and q.suffix not in {".lock", ".metadata"})
        if not parts:
            continue
        # -i is required: HERBench's parts 00-03 are a complete Lite tar whose
        # end-of-archive marker sits mid-stream (videos/videos_lite_info.txt).
        cmd = ("set -o pipefail; cat "
               + ' '.join(repr(str(x)) for x in parts)
               + " | tar -tif - | wc -l")
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        out.append({"archive": f"{base}/{label} (from {len(parts)} parts)",
                    "type": "split-tar", "ok": r.returncode == 0,
                    "members": r.stdout.strip() if r.returncode == 0 else None,
                    "error": r.stderr[-300:] if r.returncode else None})
    return out


def check_sizes(name, pre):
    """Compare on-disk sizes against HF metadata recorded in preflight."""
    rid = pre["repo_id"]
    exp = {f["path"]: f["size"] for f in pre["files"]}
    hf = ROOT / name / "hf"
    rows = []
    for rel, size in exp.items():
        p = hf / rel
        if not p.exists():
            continue
        got = p.stat().st_size
        rows.append({"path": rel, "expected": size, "got": got, "match": got == size})
    return rows


def herbench_checksums():
    f = ROOT / "herbench" / "hf" / "videos" / "videos.tar.checksums.txt"
    if not f.exists():
        return []
    rows = []
    for line in f.read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, fname = parts[0], os.path.basename(parts[-1])
        p = ROOT / "herbench" / "hf" / "videos" / fname
        if not p.exists():
            rows.append({"file": fname, "status": "MISSING"})
            continue
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 22), b""):
                h.update(b)
        rows.append({"file": fname, "expected": digest, "got": h.hexdigest(),
                     "match": h.hexdigest() == digest})
    return rows


# ---------------- ffprobe ----------------

def probe(p):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration,format_name:stream=codec_name,codec_type,width,height,r_frame_rate",
         "-of", "json", str(p)],
        capture_output=True, text=True)
    rec = {"path": str(p), "size": os.path.getsize(p)}
    if r.returncode != 0:
        rec.update(ok=False, error=r.stderr.strip()[-250:])
        return rec
    try:
        j = json.loads(r.stdout)
        v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
        num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
        fps = round(int(num) / int(den), 3) if den and int(den) else None
        rec.update(ok=True, duration=float(j.get("format", {}).get("duration") or 0),
                   width=v.get("width"), height=v.get("height"), fps=fps,
                   codec=v.get("codec_name"),
                   n_audio=sum(1 for s in j.get("streams", []) if s.get("codec_type") == "audio"))
    except Exception as e:
        rec.update(ok=False, error=f"parse: {type(e).__name__}: {e}")
    return rec


def ffprobe_all(name, workers):
    base = ROOT / name
    SKIP = ("code", "__MACOSX")
    vids = [p for p in base.rglob("*") if p.suffix in VIDEO_EXT and p.is_file()
            and ".cache" not in p.parts
            and not any(s in p.parts for s in SKIP)
            and not any("INCORRECT" in q or "lite_subset" in q for q in p.parts)]
    out = ROOT / name / "ffprobe.jsonl"
    done = set()
    if out.exists():
        for line in out.open():
            try:
                done.add(json.loads(line)["path"])
            except Exception:
                pass
    todo = [p for p in vids if str(p) not in done]
    print(f"{name}: {len(vids)} videos, {len(todo)} to probe", flush=True)
    with out.open("a") as fh, ThreadPoolExecutor(workers) as ex:
        for i, rec in enumerate(ex.map(probe, todo), 1):
            fh.write(json.dumps(rec) + "\n")
            if i % 200 == 0:
                fh.flush()
                print(f"  {name}: {i}/{len(todo)}", flush=True)
    return len(vids)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["archives", "ffprobe", "sizes"])
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    names = [a.only] if a.only else NAMES
    res = {}
    for n in names:
        if a.stage == "archives":
            res[n] = test_archives(n)
        elif a.stage == "ffprobe":
            res[n] = ffprobe_all(n, a.workers)
        elif a.stage == "sizes":
            pre = json.load(open(ROOT / "preflight.json"))
            key = {"rtv_bench": "RTVBench/RTV-Bench", "herbench": "DanBenAmi/HERBench",
                   "ovo_bench": "JoeLeelyf/OVO-Bench",
                   "streaming_bench": "mjuicem/StreamingBench"}[n]
            res[n] = check_sizes(n, pre[key])
    ap = ROOT / "archives.json"
    if a.stage == "archives":
        prev = json.load(open(ap)) if ap.exists() else {}
        prev.update(res)
        json.dump(prev, open(ap, "w"), indent=1)
        print("merged into", ap)
    print(json.dumps(res, indent=1)[:2000])
