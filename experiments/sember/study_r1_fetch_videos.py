#!/usr/bin/env python3
"""StudyR1/R5: fetch the 234 S-EMBER videos behind StudyO's 845-question pool (gated facebook/S-EMBER).

Video IDs come from results/sember/study_o/study_o_q4_trials_fa2.jsonl. Files go to a local cache OUTSIDE the repo
(default ~/.cache/fm-switching/sember_videos; never committed). Token: HF_TOKEN env (this box: from the git-ignored
hf-token.txt). Resumable: present files are skipped. Prints total disk used at the end.
"""
import json
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

REPO = "facebook/S-EMBER"
TRIALS = Path("results/sember/study_o/study_o_q4_trials_fa2.jsonl")
DEST = Path(os.environ.get("SEMBER_VIDEOS", Path.home() / ".cache/fm-switching/sember_videos"))


def main():
    vids = sorted({json.loads(l)["video_id"] for l in open(TRIALS)})
    DEST.mkdir(parents=True, exist_ok=True)
    size = {s.rfilename: (s.size or 0)
            for s in HfApi().repo_info(REPO, repo_type="dataset", files_metadata=True).siblings}
    print(f"{len(vids)} videos, {sum(size.get(f'videos/{v}.mp4', 0) for v in vids) / 1e9:.2f} GB -> {DEST}", flush=True)
    for i, v in enumerate(vids, 1):
        dest = DEST / f"{v}.mp4"
        if dest.exists() and dest.stat().st_size == size.get(f"videos/{v}.mp4"):
            continue
        got = Path(hf_hub_download(REPO, f"videos/{v}.mp4", repo_type="dataset", local_dir=DEST))
        if got != dest:
            os.replace(got, dest)
        print(f"[{i}/{len(vids)}] {v} {dest.stat().st_size / 1e6:.0f} MB", flush=True)
    bad = [v for v in vids if not (DEST / f"{v}.mp4").exists()
           or (DEST / f"{v}.mp4").stat().st_size != size.get(f"videos/{v}.mp4")]
    used = sum(p.stat().st_size for p in DEST.glob("*.mp4"))
    print(f"DONE: {len(vids) - len(bad)}/{len(vids)} verified by size; disk used {used / 1e9:.2f} GB", flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
