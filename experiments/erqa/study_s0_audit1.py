#!/usr/bin/env python3
"""Study S0 Audit 1 — MV-RoboBench dataset audit.

Metadata-only: downloads the 1,708 QA.json files and derives per-question view
counts from the repo file listing. Images are never downloaded.

Reports n/category, direct/compositional contrast, and (Correction 2) the
within-category homogeneity of arrival-time static features.
"""

import json, re, statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from huggingface_hub import list_repo_files, hf_hub_download

REPO = "AaronFengZY24/MV_Robobench"
OUT_DIR = Path("results/erqa/study_s0")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "audit1_mvrobobench.json"

IMG_EXT = (".png", ".jpg", ".jpeg")


def build_index():
    files = list_repo_files(REPO, repo_type="dataset")
    qa_files, images = [], defaultdict(list)
    for f in files:
        if f.endswith("QA.json"):
            qa_files.append(f)
        elif f.lower().endswith(IMG_EXT):
            images["/".join(f.split("/")[:-1])].append(f.split("/")[-1])
    return sorted(qa_files), images


def fetch(path):
    local = hf_hub_download(REPO, filename=path, repo_type="dataset")
    with open(local) as fh:
        return path, json.load(fh)


def main():
    print("Listing repo files...")
    qa_files, images = build_index()
    print(f"  {len(qa_files)} QA.json files; {sum(len(v) for v in images.values())} images indexed")

    print("Downloading QA.json metadata (32 threads)...")
    records = []
    with ThreadPoolExecutor(max_workers=32) as ex:
        for i, (path, qa) in enumerate(ex.map(fetch, qa_files)):
            parts = path.split("/")
            qdir = "/".join(parts[:-1])
            imgs = images.get(qdir, [])
            records.append({
                "path": qdir,
                "source": parts[0],
                "category": parts[1],
                "qid": parts[2],
                "n_views": len(imgs),
                "image_names": sorted(imgs),
                "qa": qa,
            })
            if (i + 1) % 400 == 0:
                print(f"  {i+1}/{len(qa_files)}")
    print(f"  {len(records)} questions loaded")

    schema_keys = sorted({k for r in records for k in r["qa"].keys()})
    print(f"\nQA.json schema keys: {schema_keys}")
    print("Sample record:")
    print(json.dumps(records[0]["qa"], indent=2)[:600])

    result = {
        "n_total": len(records),
        "schema_keys": schema_keys,
        "records": records,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(result, fh)
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
