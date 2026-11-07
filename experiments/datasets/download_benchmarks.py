import argparse, json, os, sys, time
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path("/mnt/ssd/hf_models/datasets")

# Each repo pinned to the SHA recorded in preflight. chunked_videos is excluded
# for OVO-Bench by the task; it is 153.3 GB of clips derived from src_videos.
DATASETS = {
    "ovo_bench": dict(
        repo="JoeLeelyf/OVO-Bench", sha="fec29e338574",
        annot=["README.md", ".gitattributes"],
        video=["src_videos.tar.parta*"],
        never=["chunked_videos.tar.part*"],
        gb=46.3),
    "rtv_bench": dict(
        repo="RTVBench/RTV-Bench", sha="62ec75f8cd7c8ec00ff1c382d950175065bea9b6",
        annot=["QA.json", "README.md", ".gitattributes"],
        video=["videos/**"],
        never=[],
        gb=101.1),
    "herbench": dict(
        repo="DanBenAmi/HERBench", sha="30b42e97180f",
        annot=["data/**", "assets/**", "README.md", "LICENSE", "CITATION.cff",
               ".gitignore", ".gitattributes", "videos/video_list.txt",
               "videos/videos.tar.checksums.txt", "videos/videos_lite_info.txt"],
        video=["videos/videos.tar.part.*"],
        never=[],
        gb=170.8),
    "streaming_bench": dict(
        repo="mjuicem/StreamingBench", sha="48872fa70712",
        annot=["StreamingBench/*.csv", "README.md", "figs/**", ".gitattributes"],
        video=["*.zip"],
        never=[],
        gb=202.6),
}

MIN_FREE_GB = 50.0


def free_gb():
    import shutil
    return shutil.disk_usage(ROOT).free / 1000**3


def fetch(name, phase, tries=5):
    d = DATASETS[name]
    dest = ROOT / name / "hf"
    dest.mkdir(parents=True, exist_ok=True)
    allow = d["annot"] if phase == "annot" else d["video"]
    ignore = d["never"] or None
    for attempt in range(1, tries + 1):
        f = free_gb()
        if f < MIN_FREE_GB:
            print(f"STOP: free {f:.1f} GB < {MIN_FREE_GB} GB", flush=True)
            sys.exit(3)
        try:
            t0 = time.time()
            snapshot_download(
                repo_id=d["repo"], repo_type="dataset", revision=d["sha"],
                local_dir=str(dest), allow_patterns=allow, ignore_patterns=ignore,
                max_workers=4,
            )
            print(f"OK {name}/{phase} in {time.time()-t0:.0f}s free={free_gb():.1f}GB", flush=True)
            return True
        except Exception as e:
            print(f"attempt {attempt}/{tries} failed for {name}/{phase}: "
                  f"{type(e).__name__}: {str(e)[:200]}", flush=True)
            if attempt == tries:
                return False
            time.sleep(min(60, 5 * 2 ** (attempt - 1)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["annot", "video"], required=True)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    # videos smallest dataset first
    names = sorted(DATASETS, key=lambda n: DATASETS[n]["gb"])
    if a.only:
        names = [n for n in names if n == a.only]
    bad = []
    for n in names:
        print(f"=== {n} / {a.phase} (free {free_gb():.1f} GB) ===", flush=True)
        if not fetch(n, a.phase):
            bad.append(n)
    print("FAILED:", bad if bad else "none", flush=True)
    sys.exit(1 if bad else 0)
