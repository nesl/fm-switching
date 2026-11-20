#!/usr/bin/env python3
"""StudySS2: build the committed manifests from the parquet staged on /dev/shm, and decode the
images (and RefSpatial masks) to files under the data root. No images or dataset blobs are
committed: the manifests carry question id, image FILENAME (resolved against the data root at run
time), the task text, the reference answer and strata only. The same manifests are rebuilt on the
H100 from the same parquet, so device and cloud share identical items. No model is run. No em dashes.

Datasets built here: RefSpatial-Bench (277; Apache-2.0) and RealWorldQA (765; CC BY-ND 4.0, images
NOT committed). CODA-LM is SKIPPED (CODA image terms gate; see ss2_bench_kit.py and the report), so no
CODA manifest is produced.

Staging: images decoded to lossless PNG so the ONLY imposed preprocessing is the shared q90
re-encode in ss2_bench_kit.preprocess_to_jpeg_bytes (identical for both tiers). RefSpatial masks decoded
to lossless PNG for scoring.
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/casestudy/study_ss2"
DATA = Path("/dev/shm/ss2_data")
REF_PQ = DATA / "refspatial_pq/data"
RWQ_PQ = DATA / "realworldqa/data"
REF_IMG = DATA / "refspatial_img"      # decoded images + masks, NOT committed
RWQ_IMG = DATA / "realworldqa_img"     # decoded images, NOT committed (ND licence)
SEED = 0


def sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def build_refspatial():
    (REF_IMG).mkdir(parents=True, exist_ok=True)
    rows = []
    for split in ["location", "placement", "unseen"]:
        p = sorted(glob.glob(str(REF_PQ / f"{split}-*.parquet")))[0]
        tab = pq.read_table(p).to_pylist()
        for r in tab:
            iid = str(r["id"])
            img_b = r["image"]["bytes"]
            msk_b = r["mask"]["bytes"]
            im = Image.open(io.BytesIO(img_b)).convert("RGB")
            mk = Image.open(io.BytesIO(msk_b))
            img_fn = f"refspatial_img/{split}_{iid}.png"
            msk_fn = f"refspatial_img/{split}_{iid}_mask.png"
            im.save(DATA / img_fn)
            mk.save(DATA / msk_fn)
            rows.append(dict(
                qid=f"refspatial/{split}/{iid}", dataset="refspatial", split=split,
                image=img_fn, mask=msk_fn, object=r["object"], prompt_text=r["prompt"],
                suffix=r["suffix"], step=int(r["step"]), width=im.size[0], height=im.size[1],
                image_sha16=sha16(img_b), gen_max_new_tokens=256))
    (OUT / "refspatial_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    info = dict(n=len(rows), by_split=dict(Counter(r["split"] for r in rows)),
                by_step=dict(Counter(r["step"] for r in rows)))
    return rows, info


def build_realworldqa():
    (RWQ_IMG).mkdir(parents=True, exist_ok=True)
    rows = []
    idx = 0
    for p in sorted(glob.glob(str(RWQ_PQ / "test-*.parquet"))):
        tab = pq.read_table(p).to_pylist()
        for r in tab:
            img_b = r["image"]["bytes"]
            im = Image.open(io.BytesIO(img_b)).convert("RGB")
            fn = f"realworldqa_img/rwq_{idx:04d}.png"
            im.save(DATA / fn)
            gold = str(r["answer"]).strip()
            subset = "mcq" if gold.upper() in ("A", "B", "C", "D") else "free_form"
            rows.append(dict(
                qid=f"realworldqa/{idx:04d}", dataset="realworldqa", image=fn,
                question=r["question"], references=[gold], subset=subset,
                width=im.size[0], height=im.size[1], image_sha16=sha16(img_b),
                gen_max_new_tokens=16))
            idx += 1
    (OUT / "realworldqa_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    info = dict(n=len(rows), by_subset=dict(Counter(r["subset"] for r in rows)))
    return rows, info


def smoke_ids(rows, key, n_per, seed=SEED):
    """A tiny seeded, stratified smoke set (n_per per stratum) for plumbing + the RefSpatial
    coordinate-convention check before the full sweep. Not a pilot; the full sets are small."""
    rng = random.Random(seed)
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r["qid"])
    picked = []
    for k in sorted(g):
        ids = sorted(g[k]); rng.shuffle(ids)
        picked += ids[:n_per]
    return sorted(picked)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref_rows, ref_info = build_refspatial()
    rwq_rows, rwq_info = build_realworldqa()

    ref_smoke = smoke_ids(ref_rows, "split", 3)       # 9 items, 3 per split
    rwq_smoke = smoke_ids(rwq_rows, "subset", 4)       # 8 items, 4 per subset
    (OUT / "refspatial_smoke.json").write_text(json.dumps(
        dict(seed=SEED, n=len(ref_smoke), stratify_by="split", qids=ref_smoke), indent=1))
    (OUT / "realworldqa_smoke.json").write_text(json.dumps(
        dict(seed=SEED, n=len(rwq_smoke), stratify_by="subset", qids=rwq_smoke), indent=1))

    meta = dict(
        study="StudySS2", built_by="experiments/casestudy/ss2_build_manifests.py", seed=SEED,
        data_root_runtime=str(DATA),
        licences=dict(
            refspatial="Apache-2.0 (BAAI/RefSpatial-Bench; RoboRefer, arXiv 2506.04308)",
            realworldqa="CC BY-ND 4.0 (xai-org/RealworldQA); images NOT committed (NoDerivatives)",
            coda_lm="SKIPPED: annotations Apache-2.0 but CODA images under CC BY-NC-SA 4.0 + Huawei "
                    "Dataset Terms (non-commercial, redistribution prohibited, accepted on "
                    "download); StudySS2 rule skips a dataset whose images need an agreement"),
        refspatial=ref_info, realworldqa=rwq_info,
        refspatial_note=("prompt = RoboRefer get_prompt Qwen branch; score = fraction of predicted "
                         "points inside the GT binary mask (summarize_acc.py), per-split mean; "
                         "coordinate convention validated on the smoke set before the full run"),
        realworldqa_note=("prompt = dataset question verbatim (lmms-eval default); MCQ iff gold in "
                          "{A,B,C,D}; free-form exact match after lower/strip/rstrip('.')"))
    (OUT / "ss2_manifest_meta.json").write_text(json.dumps(meta, indent=1))

    print("RefSpatial:", ref_info, "smoke", len(ref_smoke))
    print("RealWorldQA:", rwq_info, "smoke", len(rwq_smoke))
    print("wrote manifests + smoke sets + meta to", OUT)


if __name__ == "__main__":
    main()
