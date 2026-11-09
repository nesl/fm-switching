#!/usr/bin/env python3
"""StudyB2 Stage 4: prepare one HERBench shard (b2_her shards) from the split tar pulled from flash.

1. Every tar part needed (shard 0: parts 00-03, which hold the 68 Lite-v2 videos; other shards: all 17 parts) must be
   present and have sha256 equal to BOTH HERBench's published videos.tar.checksums.txt AND the HF LFS sha256 in flash's
   preflight.json (pinned commit 30b42e97), and the HF size. Part hashes are cached in
   results/datasets/her_parts_check_h100.json (a part is hashed once).
2. Extract only the shard's videos: cat parts | tar -x --ignore-zeros -T <member list> into herbench/extracted_full/
   (flash re-extracted with --ignore-zeros too; herbench_fix.log). Existing files of the tar-listed size are kept.
3. ffprobe every shard video (ffprobe_compare.probe) and compare with flash's ffprobe.jsonl (size exact; codec / dims;
   duration reported).
Writes results/datasets/her_shard<k>_check_h100.json. Exit 1 on any hash / size / missing-video mismatch.
Run: nice -n 10 ionice -c3 <venv python> experiments/datasets/her_prepare_shard.py <shard>
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "benchmarks"))
import ffprobe_compare as FP  # noqa: E402
import b2_her as H  # noqa: E402

DS = Path("/home/pragya/data/datasets/herbench")
PARTS_DIR = DS / "hf/videos"
RES = HERE.parents[1] / "results/datasets"
PRE = json.load(open("/home/pragya/data/flash/meta/preflight.json"))["DanBenAmi/HERBench"]
PARTS = [f"videos.tar.part.{i:02d}" for i in range(17)]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def main():
    shard = int(sys.argv[1])
    need = PARTS[:4] if shard == 0 else PARTS
    published = {l.split()[1]: l.split()[0] for l in open(PARTS_DIR / "videos.tar.checksums.txt") if l.strip()}
    lfs = {f["path"]: f for f in PRE["files"]}
    cache_p = RES / "her_parts_check_h100.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    out = dict(shard=shard, at=datetime.now().isoformat(), hf_commit=PRE["sha"], parts=[], videos=[], issues=[])
    for part in need:
        p = PARTS_DIR / part
        ref = lfs.get(f"videos/{part}")
        size = p.stat().st_size if p.exists() else None
        c = cache.get(part)
        if not (c and c.get("bytes") == size and c.get("ok")):
            h = sha256(p) if p.exists() else None
            c = dict(bytes=size, sha256=h, published=published.get(part), hf_sha256=ref and ref["lfs_sha256"],
                     hf_size=ref and ref["size"])
            c["ok"] = bool(h and h == c["published"] == c["hf_sha256"] and size == c["hf_size"])
            cache[part] = c
            cache_p.write_text(json.dumps(cache, indent=1))
        out["parts"].append(dict(part=part, **c))
        print(part, "ok" if c["ok"] else "MISMATCH", flush=True)
        if not c["ok"]:
            out["issues"].append(f"part {part} hash/size mismatch or missing")
    items = [it for it in H.build_items() if it["shard"] == shard and it["runnable"]]
    vids = sorted({it["video_key"] for it in items})
    if not out["issues"]:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
            tf.write("\n".join(v for v in vids if not (H.VID / v).exists()) + "\n")
            lst = tf.name
        todo = sum(1 for v in vids if not (H.VID / v).exists())
        print("extracting", todo, "of", len(vids), "videos", flush=True)
        if todo:
            H.VID.mkdir(parents=True, exist_ok=True)
            cat = subprocess.Popen(["cat"] + [str(PARTS_DIR / x) for x in need], stdout=subprocess.PIPE)
            r = subprocess.run(["tar", "-x", "--ignore-zeros", "-f", "-", "-C", str(H.VID), "-T", lst],
                               stdin=cat.stdout, capture_output=True, text=True)
            cat.stdout.close()
            cat.wait()
            out["tar_rc"] = r.returncode
            out["tar_stderr"] = r.stderr[-600:]
    flash = {r["path"].replace(H.FLASH_ROOT, ""): r for r in map(json.loads, open(H.FFPROBE))}
    with open(DS / "ffprobe_h100.jsonl", "a") as fo:
        for v in vids:
            vp = H.VID / v
            if not vp.exists():
                out["issues"].append(f"missing video {v}")
                continue
            r = FP.probe(vp)
            r["path"] = H.FLASH_ROOT + v
            fo.write(json.dumps(r) + "\n")
            f = flash.get(v)
            d = dict(video=v, size=r.get("size"), ok=r.get("ok"), in_flash=f is not None)
            if f:
                d.update(size_equal=r.get("size") == f.get("size"), codec_equal=r.get("codec") == f.get("codec"),
                         dims_equal=(r.get("width"), r.get("height")) == (f.get("width"), f.get("height")),
                         duration_diff=None if r.get("duration") is None or f.get("duration") is None
                         else round(r["duration"] - f["duration"], 6))
                if not d["size_equal"]:
                    out["issues"].append(f"size differs from flash {v}")
            out["videos"].append(d)
    out["summary"] = dict(parts=len(need), parts_ok=sum(p["ok"] for p in out["parts"]), shard_questions=len(items),
                          shard_videos=len(vids), videos_present=sum(1 for v in vids if (H.VID / v).exists()),
                          ffprobe_ok=sum(bool(v.get("ok")) for v in out["videos"]),
                          size_equal_flash=sum(bool(v.get("size_equal")) for v in out["videos"]),
                          codec_dims_equal=sum(bool(v.get("codec_equal") and v.get("dims_equal")) for v in out["videos"]),
                          max_abs_duration_diff=max([abs(v["duration_diff"]) for v in out["videos"]
                                                     if v.get("duration_diff") is not None] or [0]),
                          issues=len(out["issues"]))
    (RES / f"her_shard{shard}_check_h100.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"]), out["issues"][:5])
    if out["issues"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
