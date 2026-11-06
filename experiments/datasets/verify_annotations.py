#!/usr/bin/env python3
"""Verify the annotation / metadata files and code clones pulled from flash (H100 copy of the four benchmarks).

Run: python3 experiments/datasets/verify_annotations.py   (CPU-light; network only for the HF metadata query)
Inputs: /home/pragya/data/datasets/<ds>/ (pulled with fmpull, flash's layout) and flash's own reports pulled to
/home/pragya/data/flash/meta/ (preflight.json = flash's HF listing at the pinned commits; annotations_report.json).
Checks, reported without resolving anything:
 1. every non-video file under <ds>/hf/ against Hugging Face's record AT THE PINNED COMMIT (flash's preflight sha):
    size, git blob sha1 (HfApi files_metadata blob_id) and, for LFS files, sha256; plus size vs flash's preflight.
 2. question counts and unique video ids recomputed with flash's definitions (from its annotations_report keys) and
    compared with flash's numbers and video-id lists.
 3. code clones: HEAD commit, remote URL, `git fsck` and a clean work tree.
Writes results/datasets/annotations_check_h100.json.
"""
import csv
import glob
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/home/pragya/data/datasets")
FLASH = Path("/home/pragya/data/flash/meta")
OUT = Path(__file__).resolve().parents[2] / "results/datasets/annotations_check_h100.json"
REPO = {"rtv_bench": "RTVBench/RTV-Bench", "ovo_bench": "JoeLeelyf/OVO-Bench", "herbench": "DanBenAmi/HERBench",
        "streaming_bench": "mjuicem/StreamingBench"}
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".zip", ".tar")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def blob_sha1(p):
    data = Path(p).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def hf_check(ds, pre):
    from huggingface_hub import HfApi
    sha = pre[REPO[ds]]["sha"]
    info = HfApi(token=False).dataset_info(REPO[ds], revision=sha, files_metadata=True)
    hf = {s.rfilename: s for s in info.siblings}
    flash = {f["path"]: f for f in pre[REPO[ds]]["files"]}
    rows = []
    base = ROOT / ds / "hf"
    for p in sorted(base.rglob("*")):
        rel = str(p.relative_to(base))
        if p.is_dir() or rel.startswith(".cache/") or p.name.lower().endswith(VIDEO_EXT) or ".part" in p.name:
            continue
        s = hf.get(rel)
        r = dict(path=rel, size=p.stat().st_size, in_hf=s is not None, in_flash_preflight=rel in flash)
        if s is not None:
            lfs = s.lfs
            lfs_sha = (lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)) if lfs else None
            r.update(hf_size=s.size, size_match=s.size == r["size"])
            if lfs_sha:
                r.update(lfs=True, sha256=sha256(p), sha256_match=sha256(p) == lfs_sha)
            else:
                r.update(lfs=False, blob_sha1=blob_sha1(p), blob_match=blob_sha1(p) == s.blob_id, sha256=sha256(p))
        if rel in flash:
            r["flash_size_match"] = flash[rel]["size"] == r["size"]
        rows.append(r)
    bad = [r for r in rows if not r["in_hf"] or not r.get("size_match", False) or r.get("blob_match") is False
           or r.get("sha256_match") is False or r.get("flash_size_match") is False]
    return dict(revision=sha, revision_matches_flash=info.sha == sha, files=rows, mismatches=bad)


def counts(ds):
    d = ROOT / ds
    if ds == "rtv_bench":
        q = json.load(open(d / "hf/QA.json"))
        return dict(questions=len(q), unique_videos=len({x["video"] for x in q}), video_ids=sorted({x["video"] for x in q}),
                    files={"hf/QA.json": sha256(d / "hf/QA.json")})
    if ds == "ovo_bench":
        f = d / "code/data/ovo_bench_new.json"
        o = json.load(open(f))
        fw = [x for x in o if x["task"] in ("REC", "SSR", "CRR")]
        back = [x for x in o if x["task"] not in ("REC", "SSR", "CRR")]
        sub = sum(len(x.get("test_info") or []) for x in fw)
        return dict(questions=len(back) + sub, entries=len(o), backward_entries=len(back), forward_subqueries=sub,
                    unique_videos=len({x["video"] for x in o}), video_ids=sorted({x["video"] for x in o}),
                    files={"code/data/ovo_bench_new.json": sha256(f)})
    if ds == "herbench":
        f = {k: d / f"hf/data/{k}" for k in ("herbench_annotations.json", "herbench_annotations_lite.json",
                                             "herbench_annotations_lite_v2.json", "video_metadata.json")}
        full = json.load(open(f["herbench_annotations.json"]))
        lite = json.load(open(f["herbench_annotations_lite.json"]))
        lite2 = json.load(open(f["herbench_annotations_lite_v2.json"]))
        meta = json.load(open(f["video_metadata.json"]))
        vid = lambda x: x.get("video_path") or x.get("video_id")  # noqa: E731
        return dict(questions=len(full), unique_videos=len({vid(x) for x in full}), video_ids=sorted({vid(x) for x in full}),
                    lite_questions=len(lite), lite_videos=len({vid(x) for x in lite}),
                    lite_v2_questions=len(lite2), lite_v2_videos=len({vid(x) for x in lite2}),
                    metadata_videos=len(meta["videos"]) if isinstance(meta, dict) else len(meta), files={str(p.relative_to(d)): sha256(p) for p in f.values()})
    if ds == "streaming_bench":
        per, allv, nq, hashes = {}, set(), 0, {}
        for f in sorted(glob.glob(str(d / "hf/StreamingBench/*.csv"))):
            r = list(csv.DictReader(open(f, encoding="utf-8")))
            v = {x["question_id"].rsplit("_", 1)[0] for x in r}
            name = Path(f).name
            per[name] = dict(rows=len(r), videos=len(v))
            hashes[f"hf/StreamingBench/{name}"] = sha256(f)
            if name != "Proactive_Output_50.csv":
                nq += len(r)
                allv |= v
        return dict(questions=nq, unique_videos=len(allv), video_ids=sorted(allv), per_file=per, files=hashes,
                    note="questions / videos exclude Proactive_Output_50.csv (as flash's totals 4,500 / 901 imply)")


def code_check(ds):
    c = ROOT / ds / "code"
    run = lambda *a: subprocess.run(["git", "-C", str(c), *a], capture_output=True, text=True)  # noqa: E731
    fsck = run("fsck", "--no-dangling")
    return dict(head=run("rev-parse", "HEAD").stdout.strip(), remote=run("remote", "get-url", "origin").stdout.strip(),
                fsck_ok=fsck.returncode == 0, fsck_err=fsck.stderr.strip()[:300],
                dirty=[l for l in run("status", "--porcelain").stdout.splitlines()][:20])


def main():
    pre = json.load(open(FLASH / "preflight.json"))
    rep = json.load(open(FLASH / "annotations_report.json"))
    res = {}
    for ds in ("ovo_bench", "rtv_bench", "herbench", "streaming_bench"):
        c = counts(ds)
        fr = rep[ds]
        cmp = {k: dict(h100=c[k], flash=fr.get(k), match=c[k] == fr.get(k)) for k in c
               if k not in ("video_ids", "files", "note")}
        ids = dict(h100_only=sorted(set(c["video_ids"]) - set(fr["video_ids"]))[:20],
                   flash_only=sorted(set(fr["video_ids"]) - set(c["video_ids"]))[:20],
                   match=set(c["video_ids"]) == set(fr["video_ids"]))
        res[ds] = dict(hf=hf_check(ds, pre), counts=cmp, video_id_sets=ids, annotation_sha256=c["files"],
                       count_note=c.get("note"), code=code_check(ds))
        h = res[ds]["hf"]
        print(ds, "rev", h["revision"][:8], "hf files", len(h["files"]), "mismatches", len(h["mismatches"]),
              "| counts", {k: (v["h100"], v["flash"]) for k, v in cmp.items() if not isinstance(v["h100"], dict)},
              "all match", all(v["match"] for v in cmp.values()), "| ids match", ids["match"],
              "| code", res[ds]["code"]["head"][:8], "fsck", res[ds]["code"]["fsck_ok"], "dirty", len(res[ds]["code"]["dirty"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
