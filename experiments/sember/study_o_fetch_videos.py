#!/usr/bin/env python3
"""Fetch the minimum S-EMBER videos that repair the Study O §8.2 cell-balance failure.

The committed blocker (reports/study_o_results.md §8.2) reads "~400 GB of absent video". That is
the size of the whole corpus; the check that actually fails needs only enough videos to lift 12
of 24 (question_category x distance_bin) cells to >= TARGET questions each. At TARGET=30 that is
84 videos, ~10 GB.

Both pre-registered gates were verified to pass on the resulting pool before this script existed:
  §8.1 power check  — questions with evidence distance > 120 s: 31.2% (expected ~29.7%)
  §8.2 cell balance — smallest cell 30

distance_bin uses `memory_recency`, which is identical to question_time - answer_start_time and
reproduces the committed §8.1 figure of 31.2% exactly on the current 520-question local pool.

Dry run by default. Pass --go to download.
"""

import argparse, collections, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GROUNDING = ROOT / "results/sember/study_h/data/sember_grounding.jsonl"
VIDEO_DIR = ROOT / "results/sember/study_i/videos"
REPO = "facebook/S-EMBER"


def distance_bin(rec):
    d = float(rec["memory_recency"])
    return "<=60s" if d <= 60 else ("60-120s" if d <= 120 else ">120s")


def select(target):
    rows = [json.loads(l) for l in open(GROUNDING)]
    local = {f[:-4] for f in os.listdir(VIDEO_DIR) if f.endswith(".mp4")}
    cells = sorted({(r["question_category"], distance_bin(r)) for r in rows})
    have = collections.Counter(
        (r["question_category"], distance_bin(r)) for r in rows if r["video_id"] in local)
    deficit = {k: target - have.get(k, 0) for k in cells if have.get(k, 0) < target}

    by_vid = collections.defaultdict(list)
    for r in rows:
        k = (r["question_category"], distance_bin(r))
        if r["video_id"] not in local and k in deficit:
            by_vid[r["video_id"]].append(k)

    need, chosen = dict(deficit), []
    while any(n > 0 for n in need.values()):
        best = max(by_vid, key=lambda v: sum(1 for k in by_vid[v] if need.get(k, 0) > 0),
                   default=None)
        if best is None or sum(1 for k in by_vid[best] if need.get(k, 0) > 0) == 0:
            break
        for k in by_vid[best]:
            if need.get(k, 0) > 0:
                need[k] -= 1
        chosen.append(best)
        del by_vid[best]

    unmet = {k: n for k, n in need.items() if n > 0}
    return rows, local, cells, chosen, unmet


def report(rows, local, cells, chosen, baseline=None):
    """`baseline` is the question count before any download; pass it explicitly, because
    after a --go run `local` already contains the new videos and would print "was <new>"."""
    pool = set(local) | set(chosen)
    sel = [r for r in rows if r["video_id"] in pool]
    cnt = collections.Counter((r["question_category"], distance_bin(r)) for r in sel)
    far = sum(1 for r in sel if float(r["memory_recency"]) > 120) / len(sel) * 100
    was = baseline if baseline is not None else sum(1 for r in rows if r["video_id"] in local)
    print(f"  questions in pool : {len(sel)}  (was {was})")
    print(f"  §8.1  >120s       : {far:.1f}%  (expected ~29.7%)")
    print(f"  §8.2  smallest cell: {min(cnt.get(k, 0) for k in cells)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=30,
                    help="questions per (category x distance_bin) cell; §8.2 needs >=20")
    ap.add_argument("--go", action="store_true", help="actually download (default: dry run)")
    args = ap.parse_args()

    rows, local, cells, chosen, unmet = select(args.target)
    baseline = sum(1 for r in rows if r["video_id"] in local)
    print(f"target >={args.target}/cell   local videos {len(local)}   to fetch {len(chosen)}")
    if unmet:
        raise SystemExit(f"FATAL: target unreachable even with every remote video: {unmet}")
    report(rows, local, cells, chosen, baseline=baseline)

    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    size = {s.rfilename: (s.size or 0)
            for s in api.repo_info(REPO, repo_type="dataset", files_metadata=True).siblings}
    total = sum(size.get(f"videos/{v}.mp4", 0) for v in chosen)
    print(f"  download size     : {total/1e9:.2f} GB")

    if not args.go:
        print("\nDRY RUN — nothing downloaded. Re-run with --go.")
        return

    # local_dir keeps the bytes out of the shared HF cache: downloading into the cache and then
    # copying would occupy ~2x the download size on a volume that is already 92% full.
    for i, v in enumerate(chosen, 1):
        dest = VIDEO_DIR / f"{v}.mp4"
        if dest.exists():
            print(f"[{i}/{len(chosen)}] skip (present) {v}", flush=True)
            continue
        got = Path(hf_hub_download(REPO, f"videos/{v}.mp4", repo_type="dataset",
                                   local_dir=VIDEO_DIR))
        if got != dest:
            os.replace(got, dest)          # same filesystem: a rename, not a copy
        print(f"[{i}/{len(chosen)}] {v}  {dest.stat().st_size/1e6:.0f} MB", flush=True)
    nested = VIDEO_DIR / "videos"
    if nested.is_dir() and not any(nested.iterdir()):
        nested.rmdir()

    print("\nPost-download verification:")
    rows2, local2, cells2, chosen2, unmet2 = select(args.target)
    report(rows2, local2, cells2, [], baseline=baseline)


if __name__ == "__main__":
    main()
