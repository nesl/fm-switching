#!/usr/bin/env python3
"""StudyB2 Stage 3: prepare one StreamingBench shard (by upstream archive) after its zips are pulled from flash.

For every zip of the shard (b2_sb.ARCHIVES[shard]):
  1. size and sha256 equal to the HF LFS entry in flash's preflight.json at the pinned commit (48872fa7);
  2. extract ONLY the "sample_N/video.mp4" members (no __MACOSX / .DS_Store) into
     /home/pragya/data/datasets/streaming_bench/extracted_by_task/<task dir>/ (flash's layout); zipfile checks each
     member's CRC-32 while extracting; existing files of the right size are kept (resumable).
Then for every extracted video: ffprobe (ffprobe_compare.probe: same fields as flash) compared with flash's
ffprobe.jsonl (size exact; duration / fps / codec / dims), and every question of the shard must have its video.
Writes results/datasets/sb_shard<k>_check_h100.json and appends to streaming_bench/ffprobe_h100.jsonl.
Exit 1 on any sha256 / size / annotation-video mismatch (stop and ask); ffprobe float differences are reported only.
Run: nice -n 19 ionice -c3 python3 experiments/datasets/sb_prepare_shard.py <shard>
"""
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "benchmarks"))
import ffprobe_compare as FP  # noqa: E402
import b2_sb as SB  # noqa: E402

DS = Path("/home/pragya/data/datasets/streaming_bench")
PRE = json.load(open("/home/pragya/data/flash/meta/preflight.json"))["mjuicem/StreamingBench"]
RES = HERE.parents[1] / "results/datasets"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def main():
    shard = int(sys.argv[1])
    lfs = {f["path"]: f for f in PRE["files"]}
    out = dict(shard=shard, at=datetime.now().isoformat(), hf_commit=PRE["sha"], archives=[], videos=[], issues=[])
    for z in SB.ARCHIVES[shard]:
        p = DS / "hf" / z
        ref = lfs.get(z)
        rec = dict(archive=z, bytes=p.stat().st_size if p.exists() else None, hf_size=ref and ref["size"],
                   hf_sha256=ref and ref["lfs_sha256"])
        rec["sha256"] = sha256(p) if p.exists() else None
        rec["ok"] = bool(ref and rec["bytes"] == ref["size"] and rec["sha256"] == ref["lfs_sha256"])
        out["archives"].append(rec)
        print(z, "sha256 ok" if rec["ok"] else "MISMATCH", flush=True)
        if not rec["ok"]:
            out["issues"].append(f"archive mismatch {z}")
            continue
        dest = DS / "extracted_by_task" / SB.ARCHIVE_DIR[z]
        with zipfile.ZipFile(p) as zf:
            members = [m for m in zf.infolist() if m.filename.endswith("/video.mp4") and not m.filename.startswith("__MACOSX")]
            rec["video_members"] = len(members)
            for m in members:
                target = dest / m.filename
                if target.exists() and target.stat().st_size == m.file_size:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, open(target, "wb") as dst:   # zipfile verifies CRC-32 at EOF
                    shutil.copyfileobj(src, dst, 1 << 24)
        print(z, "extracted", rec["video_members"], flush=True)
    flash = {r["path"].replace(FP.FLASH_ROOT, str(FP.ROOT)): r for r in map(json.loads, open(DS / "ffprobe.jsonl"))}
    items = [it for it in SB.build_items() if it["shard"] == shard]
    vids = sorted({it["video"] for it in items})
    with open(DS / "ffprobe_h100.jsonl", "a") as fo:
        for v in vids:
            vp = Path(v)
            if not vp.exists():
                out["issues"].append(f"missing video {v}")
                continue
            r = FP.probe(vp)
            r["path"] = v.replace(str(FP.ROOT), FP.FLASH_ROOT)
            fo.write(json.dumps(r) + "\n")
            f = flash.get(v)
            d = dict(path=v, size=r.get("size"), ok=r.get("ok"), in_flash=f is not None)
            if f:
                d.update(size_equal=r.get("size") == f.get("size"), codec_equal=r.get("codec") == f.get("codec"),
                         dims_equal=(r.get("width"), r.get("height")) == (f.get("width"), f.get("height")),
                         duration_diff=None if r.get("duration") is None or f.get("duration") is None
                         else round(r["duration"] - f["duration"], 6),
                         fps_diff=None if r.get("fps") is None or f.get("fps") is None else round(r["fps"] - f["fps"], 3))
                if not d["size_equal"]:
                    out["issues"].append(f"size differs from flash {v}")
            out["videos"].append(d)
    out["summary"] = dict(archives=len(out["archives"]), archives_ok=sum(a["ok"] for a in out["archives"]),
                          shard_questions=len(items), shard_videos=len(vids),
                          videos_present=sum(1 for v in vids if Path(v).exists()),
                          ffprobe_ok=sum(bool(v.get("ok")) for v in out["videos"]),
                          size_equal_flash=sum(bool(v.get("size_equal")) for v in out["videos"]),
                          codec_dims_equal=sum(bool(v.get("codec_equal") and v.get("dims_equal")) for v in out["videos"]),
                          duration_diff_nonzero=sum(1 for v in out["videos"] if v.get("duration_diff")),
                          max_abs_duration_diff=max([abs(v["duration_diff"]) for v in out["videos"] if v.get("duration_diff") is not None] or [0]),
                          issues=len(out["issues"]))
    (RES / f"sb_shard{shard}_check_h100.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"]), out["issues"][:5])
    if out["issues"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
