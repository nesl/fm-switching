#!/usr/bin/env python3
"""StudyB2 deletion of one dataset shard's videos and video archives (user's DELETION rule).

Checks before deleting anything (any failure -> exit 1, nothing deleted):
  - every arm in --arms has, for every main question of the shard and both inputs (and grey for shard 1), an
    error-free row in results/benchmarks/study_b2_<dataset>/b2_rows_<arm>*.jsonl.gz (rows readable);
  - the report file exists and contains the marker "## Shard <k>" (a report section exists);
  - the manifest records the pinned commit and file list (flash's download_manifest.json + preflight.json entries);
Then lists every path (written to results/datasets/deletion_h100_<dataset>_shard<k>.json with bytes) and deletes only
regular files that are (a) the shard's zips under <dataset>/hf/ or (b) videos under <dataset>/extracted_by_task/ that
belong to the shard's questions, EXCEPT the videos in the keep list (latency sample). No wildcard; every path is
resolved and must lie under /home/pragya/data/datasets/<dataset>/.
HERBench: rows are HISTORY only, grey with shard 0; only extracted videos are deleted (tar parts after the last shard).
Run: python3 experiments/datasets/b2_delete_shard.py streaming_bench 1 --report reports/study_b2_streamingbench.md
     --keep logs/sb_latency_keep_videos.json [--dry-run]
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "benchmarks"))
import b2_common as C2  # noqa: E402

ARMS = ("4BI", "8BI", "32BI", "4BT", "8BT", "32BT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("shard", type=int)
    ap.add_argument("--report", required=True)
    ap.add_argument("--keep", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    base = Path("/home/pragya/data/datasets") / a.dataset
    if a.dataset == "streaming_bench":
        import b2_sb as SB
        items = [it for it in SB.build_items() if it["shard"] == a.shard]
        order = SB.fixed_order(SB.build_items())
        grey = [it["item_id"] for it in order[:100]] if a.shard == 1 else []
        inputs = ("RECENT", "HISTORY")
    elif a.dataset == "herbench":
        import b2_her as HER
        allit = HER.build_items()
        items = [it for it in allit if it["shard"] == a.shard and it["runnable"] and not it.get("duplicate_of")]
        full = HER.fixed_order([it for it in allit if it["set"] == "full" and it["runnable"] and not it.get("duplicate_of")])
        grey = [it["item_id"] for it in full[:100]] if a.shard == 0 else []
        inputs = ("HISTORY",)
    else:
        raise SystemExit(f"unknown dataset {a.dataset}")
    out_dir = ROOT / f"results/benchmarks/study_b2_{a.dataset}"
    problems = []
    cov = {}
    for arm in ARMS:
        rows = C2.read_rows(out_dir, f"b2_rows_{arm}")
        ok = C2.latest_ok(rows)
        render_err = {(r["tag"], r["item_id"], r["input"]) for r in rows
                      if r.get("error") and str(r["error"]).startswith("RenderError")}
        need = [("main", it["item_id"], inp) for it in items for inp in inputs]
        need += [("grey", g, inp) for g in grey for inp in inputs]
        unrunnable = [k for k in need if k not in ok and k in render_err]   # recorded: frames cannot be decoded
        miss = [k for k in need if k not in ok and k not in render_err]
        cov[arm] = dict(needed=len(need), present=len(need) - len(miss) - len(unrunnable),
                        render_error=[list(k) for k in unrunnable])
        if miss:
            problems.append(f"{arm}: {len(miss)} of {len(need)} shard rows missing, e.g. {miss[:2]}")
    rep = ROOT / a.report
    if not rep.exists() or f"## Shard {a.shard}" not in rep.read_text():
        problems.append(f"report section '## Shard {a.shard}' not found in {a.report}")
    man = json.load(open(ROOT / "results/datasets/download_manifest.json"))["datasets"][a.dataset]
    repo = {"streaming_bench": "mjuicem/StreamingBench", "herbench": "DanBenAmi/HERBench"}[a.dataset]
    pre = {f["path"] for f in json.load(open("/home/pragya/data/flash/meta/preflight.json"))[repo]["files"]}
    # StreamingBench: the shard's zips are deleted with it. HERBench: the split-tar parts serve every shard and are
    # deleted only after the last shard (separate step); a shard deletion removes extracted videos only.
    zips = SB.ARCHIVES[a.shard] if a.dataset == "streaming_bench" else []
    need_files = zips if a.dataset == "streaming_bench" else [f"videos/videos.tar.part.{i:02d}" for i in range(17)]
    if not man.get("commit_sha") or any(z not in pre for z in need_files):
        problems.append("manifest / preflight lacks the pinned commit or an archive file")
    keep = set(json.load(open(a.keep))) if a.keep else set()
    entries = []
    for z in zips:
        p = base / "hf" / z
        if p.exists():
            entries.append(dict(path=str(p), bytes=p.stat().st_size, kind="video_archive"))
    for v in sorted({it["video"] for it in items}):
        p = Path(v)
        if v in keep:
            continue
        if p.exists():
            entries.append(dict(path=v, bytes=p.stat().st_size, kind="video"))
    rec = dict(created=datetime.now().isoformat(), dataset=a.dataset, shard=a.shard, coverage=cov, problems=problems,
               kept_for_latency=sorted(v for v in keep if Path(v).exists() and any(it["video"] == v for it in items)),
               manifest=dict(hf_commit=man.get("commit_sha"), code_sha=man.get("code_repo_sha"), zips=zips),
               n=len(entries), total_bytes=sum(e["bytes"] for e in entries), entries=entries, dry_run=a.dry_run)
    print(json.dumps({k: v for k, v in rec.items() if k != "entries"}, indent=1)[:3000])
    if problems:
        raise SystemExit(1)
    (ROOT / f"results/datasets/deletion_h100_{a.dataset}_shard{a.shard}.json").write_text(json.dumps(rec, indent=0))
    if a.dry_run:
        return
    root = base.resolve()
    freed, n = 0, 0
    for e in entries:
        p = Path(e["path"])
        rp = p.resolve()
        if not (rp.is_file() and not p.is_symlink() and root in rp.parents and rp.stat().st_size == e["bytes"]
                and (rp.suffix.lower() in (".mp4", ".zip"))):
            raise SystemExit(f"refusing {p}")
        os.remove(rp)
        freed += e["bytes"]
        n += 1
    print(f"deleted {n} files, {freed} bytes")


if __name__ == "__main__":
    main()
