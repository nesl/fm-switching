#!/usr/bin/env python3
"""Study S1 — fetch MV-RoboBench images for the main experiment.

Audit 1 deliberately avoided downloading images. The main experiment needs all
of them to run the models. Fetches to the HF cache with a thread pool.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from huggingface_hub import list_repo_files, hf_hub_download

REPO = "AaronFengZY24/MV_Robobench"
IMG_EXT = (".png", ".jpg", ".jpeg")


def fetch(path):
    try:
        return hf_hub_download(REPO, filename=path, repo_type="dataset")
    except Exception as e:
        return f"ERROR {path}: {e}"


def main():
    files = [f for f in list_repo_files(REPO, repo_type="dataset")
             if f.lower().endswith(IMG_EXT)]
    print(f"{len(files)} images to ensure cached")

    errors, done = [], 0
    with ThreadPoolExecutor(max_workers=32) as ex:
        futs = {ex.submit(fetch, f): f for f in files}
        for fu in as_completed(futs):
            r = fu.result()
            done += 1
            if isinstance(r, str) and r.startswith("ERROR"):
                errors.append(r)
            if done % 500 == 0:
                print(f"  {done}/{len(files)}  errors={len(errors)}")

    print(f"done: {done}/{len(files)}, errors={len(errors)}")
    for e in errors[:10]:
        print("  ", e)


if __name__ == "__main__":
    main()
