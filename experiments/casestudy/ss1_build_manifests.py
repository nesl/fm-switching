#!/usr/bin/env python3
"""StudySS1: build the committed manifests and the seeded stratified pilots for VizWiz-VQA (val)
and EgoThink, from the raw data staged on /dev/shm. No images or dataset blobs are committed: the
manifests carry question id, image FILENAME (resolved against the data root at run time),
question, references and strata only. EgoThink images are decoded from the HuggingFace parquet to
JPEG files under the data root (not committed). No model is run. No em dashes.

Licences recorded: VizWiz-VQA CC BY 4.0 (Gurari et al., CVPR 2018); EgoThink Apache-2.0 (Cheng et
al., CVPR 2024), images bundled in the HF dataset, sourced from Ego4D (acknowledged upstream).
"""
from __future__ import annotations

import hashlib
import io
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/casestudy/study_ss1"
DATA = Path("/dev/shm/ss1_data")
VIZ = DATA / "vizwiz"
EGO = DATA / "egothink"
EGO_IMG = DATA / "egothink_images"          # extracted, NOT committed
SEED = 0
PILOT_N = 300

EGO_DIMS = ["Activity", "Forecasting", "Localization_location", "Localization_spatial",
            "Object_affordance", "Object_attribute", "Object_existence",
            "Planning_assistance", "Planning_navigation", "Reasoning_comparing",
            "Reasoning_counting", "Reasoning_situated"]
# the six capability areas, for reporting
EGO_AREA = {d: d.split("_")[0] for d in EGO_DIMS}


def sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def build_vizwiz():
    v = json.loads((VIZ / "val.json").read_text())
    rows = []
    for e in v:
        refs = [a["answer"] for a in e["answers"]]
        assert len(refs) == 10, (e["image"], "expected 10 answers")
        rows.append(dict(
            qid="vizwiz_val/" + e["image"].rsplit(".", 1)[0],
            dataset="vizwiz_vqa", split="val", image=e["image"], question=e["question"],
            references=refs, answer_type=e["answer_type"], answerable=int(e["answerable"]),
            n_references=10, gen_max_new_tokens=30))
    (OUT / "vizwiz_val_manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    strat = Counter(r["answer_type"] for r in rows)
    return rows, dict(n=len(rows), by_answer_type=dict(strat),
                      n_answerable=sum(r["answerable"] for r in rows))


def build_egothink():
    EGO_IMG.mkdir(parents=True, exist_ok=True)
    rows = []
    for dim in EGO_DIMS:
        p = EGO / dim / "test-00000-of-00001.parquet"
        tab = pq.read_table(p).to_pylist()
        for i, r in enumerate(tab):
            img = r["image"]
            assert isinstance(img, dict) and img.get("bytes"), (dim, i, "no image bytes")
            b = img["bytes"]
            im = Image.open(io.BytesIO(b)).convert("RGB")
            fn = "%s_%03d.jpg" % (dim, i)
            im.save(EGO_IMG / fn, format="JPEG", quality=95)
            rows.append(dict(
                qid="egothink/%s/%03d" % (dim, i), dataset="egothink", split="test",
                image="egothink_images/" + fn, question=r["question"], references=[r["answer"]],
                dimension=dim, area=EGO_AREA[dim], n_references=1,
                image_sha16=sha16(b),
                gen_max_new_tokens=(300 if dim in ("Planning_assistance", "Planning_navigation")
                                    else 30)))
    (OUT / "egothink_manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    strat = Counter(r["dimension"] for r in rows)
    multi = 0   # single image per row by construction
    return rows, dict(n=len(rows), by_dimension=dict(strat), by_area=dict(Counter(
        r["area"] for r in rows)), n_multi_image_or_temporal_excluded=multi)


def stratified_pilot(rows, key, n, seed=SEED):
    """Proportional allocation across strata, seeded; largest-remainder to hit exactly n."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r["qid"])
    for g in groups.values():
        g.sort()
        rng.shuffle(g)
    total = len(rows)
    raw = {k: len(g) * n / total for k, g in groups.items()}
    alloc = {k: int(x) for k, x in raw.items()}
    rem = n - sum(alloc.values())
    for k in sorted(groups, key=lambda k: raw[k] - alloc[k], reverse=True)[:rem]:
        alloc[k] += 1
    picked = []
    for k, g in groups.items():
        picked.extend(g[:alloc[k]])
    picked.sort()
    return picked, {k: alloc[k] for k in sorted(alloc)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vz_rows, vz_info = build_vizwiz()
    eg_rows, eg_info = build_egothink()

    vz_pilot, vz_alloc = stratified_pilot(vz_rows, "answer_type", PILOT_N)
    eg_pilot, eg_alloc = stratified_pilot(eg_rows, "dimension", PILOT_N)
    (OUT / "vizwiz_pilot300.json").write_text(json.dumps(
        dict(seed=SEED, n=len(vz_pilot), stratify_by="answer_type", allocation=vz_alloc,
             qids=vz_pilot), indent=1))
    (OUT / "egothink_pilot300.json").write_text(json.dumps(
        dict(seed=SEED, n=len(eg_pilot), stratify_by="dimension", allocation=eg_alloc,
             qids=eg_pilot), indent=1))

    meta = dict(
        study="StudySS1", built_by="experiments/casestudy/ss1_build_manifests.py", seed=SEED,
        data_root_runtime=str(DATA),
        licences=dict(vizwiz_vqa="CC BY 4.0 (Gurari et al., CVPR 2018)",
                      egothink="Apache-2.0 (Cheng et al., CVPR 2024); images bundled in the HF "
                               "dataset EgoThink/EgoThink, sourced from Ego4D (acknowledged)"),
        vizwiz=vz_info, egothink=eg_info,
        vizwiz_val_size_note=("official VQA 2020 val split = 4,319 image/question pairs; the "
                              "StudySS1 prompt's 3,173 is the 2018 paper split and is a corrected "
                              "discrepancy (user ruling 2026-11-19)"),
        vizwiz_quality_flags=("the VQA val release carries answer_type and answerable only; the "
                              "blur/framing/obstruction image-quality flags live in the separate "
                              "VizWiz image-quality dataset and are NOT joined here (PROVISIONAL: "
                              "pilot stratified by answer_type; quality-flag stratification "
                              "deferred as the join is a separate download with uncertain overlap)"),
        pilot=dict(n=PILOT_N, vizwiz_allocation=vz_alloc, egothink_allocation=eg_alloc))
    (OUT / "ss1_manifest_meta.json").write_text(json.dumps(meta, indent=1))

    print("VizWiz:", vz_info)
    print("  pilot alloc:", vz_alloc, "=", sum(vz_alloc.values()))
    print("EgoThink:", eg_info)
    print("  pilot alloc:", eg_alloc, "=", sum(eg_alloc.values()))
    print("wrote manifests + pilots to", OUT)


if __name__ == "__main__":
    main()
