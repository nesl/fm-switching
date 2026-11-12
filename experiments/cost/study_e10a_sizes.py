#!/usr/bin/env python3
"""StudyE10a-jpeg Job A — payload sizes (CPU only; ORIGINAL .venv: transformers 5.10.2 / torch / PIL / ffprobe).

(i) Nexar: 500 SMALL 768x432 PNGs from the D14 frame set (sorted file list, random.Random(0).sample). Bytes of the
    stored file, PNG re-encoded with PIL defaults, JPEG q in {75, 85, 90, 95} (PIL defaults otherwise: 4:2:0).
(ii) S-EMBER: 40 videos (sorted, random.Random(0).sample) x 5 frames (same rng) from the 1 fps JPEG q88 cache. Each
    frame is decoded and resized to every RECENT and RICH final_hw in the R1 manifest with the pipeline's resampling
    (transformers Qwen3-VL video-processor resize, bicubic, on float, rounded and clamped to uint8, as
    study_r1_inputs.py does in its final step; single-stage from the cache frame), and to D2 352x256 with RH3/RH4's
    PIL bicubic (study_rh3_inputs.load, orientation-aware). Encodings: PNG (PIL defaults), PNG compress_level 1
    (R1's transport), JPEG q in {75, 85, 88, 90}. Request-weighted bytes per construction = per request, frames x
    median bytes per frame at its final_hw.
(iii) Source bitrate of every S-EMBER mp4: size x 8 / duration (ffprobe format duration).
Writes results/cost/study_e10/e10a_sizes.json.
"""
import io
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/sember"))
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_e10"
D14 = Path.home() / "data/dashcam/d14_frames/small"
SEM = Path.home() / ".cache/fm-switching/sember_frames"
VID = Path.home() / ".cache/fm-switching/sember_videos"
SNAP = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/"
        "0cfaf48183f594c314753d30a4c4974bc75f3ccb")
NEX_Q = (75, 85, 90, 95)
SEM_Q = (75, 85, 88, 90)


def enc(im, kind, q=None):
    buf = io.BytesIO()
    if kind == "png":
        im.save(buf, format="PNG")
    elif kind == "png1":
        im.save(buf, format="PNG", compress_level=1)
    else:
        im.save(buf, format="JPEG", quality=q)
    return buf.tell()


def quart(xs):
    xs = np.asarray(xs, float)
    return dict(n=len(xs), p25=float(np.percentile(xs, 25)), median=float(np.median(xs)), p75=float(np.percentile(xs, 75)),
                mean=float(xs.mean()))


def nexar_one(p):
    im = Image.open(p).convert("RGB")
    out = dict(stored=p.stat().st_size, png=enc(im, "png"), size=list(im.size))
    for q in NEX_Q:
        out[f"jpeg{q}"] = enc(im, "jpeg", q)
    return out


_VP = None


def sem_one(job):
    """job = (frame path, list of (construction, h, w)); returns {(cons,h,w): {enc: bytes}}."""
    global _VP
    import torch
    from transformers.image_processing_utils_fast import SizeDict
    if _VP is None:
        from transformers import AutoVideoProcessor
        _VP = AutoVideoProcessor.from_pretrained(SNAP)
        torch.set_num_threads(1)
    import study_rh3_inputs as B3
    path, targets = job
    src = Image.open(path).convert("RGB")
    t = torch.from_numpy(np.asarray(src).copy()).permute(2, 0, 1)[None].float()
    res = {}
    for cons, h, w in targets:
        if cons == "D2":
            im = B3.load(path, (352, 256))
        else:
            fin = _VP.resize(t, size=SizeDict(height=h, width=w), resample=_VP.resample)
            arr = fin.round().clamp(0, 255).to(torch.uint8)[0].permute(1, 2, 0).numpy()
            im = Image.fromarray(np.ascontiguousarray(arr))
        e = dict(png=enc(im, "png"), png1=enc(im, "png1"))
        for q in SEM_Q:
            e[f"jpeg{q}"] = enc(im, "jpeg", q)
        res[f"{cons}|{im.height}x{im.width}"] = e
    return str(path), res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = dict(label="StudyE10a-jpeg Job A: payload sizes (bytes), CPU only")
    # (i) Nexar
    allp = sorted(D14.rglob("*.png"))
    pick = random.Random(0).sample(allp, 500)
    with Pool(32) as pool:
        nx = pool.map(nexar_one, pick, chunksize=8)
    assert all(tuple(r["size"]) == (768, 432) for r in nx), Counter(tuple(r["size"]) for r in nx)
    res["nexar"] = dict(n_frames=500, pool=len(allp), size="768x432",
                        bytes={k: quart([r[k] for r in nx]) for k in ["stored", "png"] + [f"jpeg{q}" for q in NEX_Q]})
    res["nexar"]["ratio_to_png_median"] = {k: float(np.median([r[k] / r["png"] for r in nx]))
                                          for k in ["stored"] + [f"jpeg{q}" for q in NEX_Q]}
    # (ii) S-EMBER
    import gzip
    man = [json.loads(l) for l in gzip.open(REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt")]
    hw = Counter((r["construction"], *r["final_hw"]) for r in man)
    targets = sorted(hw) + [("D2", 352, 256)]
    vids = sorted(p.name for p in SEM.iterdir() if (p / "index.json").exists())
    rng = random.Random(0)
    vsel = rng.sample(vids, 40)
    jobs = []
    for v in vsel:
        idx = json.load(open(SEM / v / "index.json"))["frames"]
        for t, f in rng.sample(idx, 5):
            jobs.append((SEM / v / f, targets))
    with Pool(64) as pool:
        out = pool.map(sem_one, jobs, chunksize=1)
    per = defaultdict(lambda: defaultdict(list))
    for _, r in out:
        for key, e in r.items():
            for k, b in e.items():
                per[key][k].append(b)
    encs = ["png", "png1"] + [f"jpeg{q}" for q in SEM_Q]
    res["sember"] = dict(n_frames=len(jobs), videos=40, source="1 fps JPEG q88 cache", encodings=encs,
                         per_resolution={k: dict(n_requests_using=hw.get(tuple([k.split("|")[0]] + [int(x) for x in k.split("|")[1].split("x")]), None),
                                                 bytes={e: quart(v[e]) for e in encs}) for k, v in sorted(per.items())})
    # request-weighted bytes per construction (frames x median bytes per frame at that final_hw)
    med = {k: {e: float(np.median(v[e])) for e in encs} for k, v in per.items()}
    rq = {}
    for cons in ("RECENT", "RICH"):
        rows = [r for r in man if r["construction"] == cons]
        rq[cons] = {e: quart([r["n_frames_padded"] * med[f"{cons}|{r['final_hw'][0]}x{r['final_hw'][1]}"][e] for r in rows])
                    for e in encs}
        rq[cons]["frames_per_request"] = quart([r["n_frames_padded"] for r in rows])
    # D2: frames per request from RH4 (all 845 D2 requests)
    rh4 = [json.loads(l) for l in gzip.open(REPO / "results/sember/study_rh4/study_rh4_inputs_manifest.jsonl.gz", "rt")]
    d2k = next(k for k in med if k.startswith("D2|"))
    rq["D2"] = {e: quart([r["n_images"] * med[d2k][e] for r in rh4 if r["cell"] == "D2"]) for e in encs}
    rq["D2"]["frames_per_request"] = quart([r["n_images"] for r in rh4 if r["cell"] == "D2"])
    res["sember"]["request_bytes"] = rq
    res["sember"]["main_resolutions"] = {k: res["sember"]["per_resolution"][k] for k in
                                         ("RECENT|512x384", "RICH|352x256", d2k)}
    # (iii) bitrate
    br = []
    for p in sorted(VID.glob("*.mp4")):
        d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                           capture_output=True, text=True).stdout.strip()
        br.append(dict(video=p.name, bytes=p.stat().st_size, duration_s=float(d),
                       bitrate_bps=p.stat().st_size * 8 / float(d)))
    b = np.array([r["bitrate_bps"] for r in br])
    res["sember_bitrate"] = dict(n_videos=len(br), p5_mbps=float(np.percentile(b, 5) / 1e6),
                                 p50_mbps=float(np.median(b) / 1e6), p95_mbps=float(np.percentile(b, 95) / 1e6),
                                 min_mbps=float(b.min() / 1e6), max_mbps=float(b.max() / 1e6),
                                 duration_s_p50=float(np.median([r["duration_s"] for r in br])))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10a_sizes.py", model="none", device="cpu", n=500 + len(jobs) + len(br))
    (OUT / "e10a_sizes.json").write_text(json.dumps(res, indent=1))
    n = res["nexar"]["bytes"]
    print("NEXAR", {k: round(v["median"]) for k, v in n.items()})
    for k, v in res["sember"]["main_resolutions"].items():
        print(k, {e: round(x["median"]) for e, x in v["bytes"].items()})
    print("REQ", {c: {e: round(v[e]["median"]) for e in encs} for c, v in rq.items()})
    print("BITRATE", res["sember_bitrate"])


if __name__ == "__main__":
    main()
