#!/usr/bin/env python3
"""StudyRH3 input builder (ORIGINAL .venv: transformers 5.10.2 — the StudyO / R1 / RH1 preprocessing stack). CPU only.

History as SEPARATE IMAGES (the format R5/RH2 can append under prefix caching), one row per question x cell:
  A  R5/RH2 history exactly: every 1 fps frame with t <= question_time (StudyO's frame cache, the same JPEGs R5
     replays), the most recent 640 if longer, each resized to 160x128 (HxW; 128x160 landscape), R5's header.
  B  R1's RICH frame list (same timestamps, <= 256), every frame at ONE fixed size SIZE_B.
  C  every 1 fps frame with question_time - 120 <= t <= question_time at SIZE_C_RECENT, plus frames older than that at
     t = 0, 8, 16, ... (1 per 8 s) at 160x128.
Message = [header text, image, image, ..., R1's question text] (R1's exact text, so the only change from R1 is the
history representation). Resize: PIL bicubic from the cached JPEG (R5's frame_b64), sent as PNG, so vLLM decodes the
same pixels. Every size is a multiple of 32 (Qwen3-VL patch 16 x merge 2), and the processor's pixel bounds are set
(PROC_SIZE, also passed to the server) so no image is rescaled: tokens per image = (H/32)(W/32) + 2 delimiters.

Expected prompt tokens = HF processor (32B-I chat template) on exactly these images and text, per question and cell.
Manifest (repo): results/sember/study_rh3/study_rh3_inputs_manifest.jsonl (frame timestamps, sizes, expected counts).
--probe prints the mean prompt tokens per candidate size (formula + text tokens) so SIZE_B / SIZE_C_RECENT can be set.
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
R1_MANIFEST = REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl"
MANIFEST = REPO / "results/sember/study_rh3/study_rh3_inputs_manifest.jsonl"
MCQ = REPO / "results/sember/study_h/data/sember_mcq.jsonl"
FRAMES = Path.home() / ".cache/fm-switching/sember_frames"
SNAP_I = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/"
          "0cfaf48183f594c314753d30a4c4974bc75f3ccb")
PROC_SIZE = {"shortest_edge": 4096, "longest_edge": 16777216}
SIZE_A = (160, 128)            # R5 / RH2 (portrait HxW)
SIZE_B = (288, 224)            # set from --probe (see EXPERIMENTS StudyRH3)
SIZE_C_RECENT = (384, 288)     # set from --probe
SIZE_C_OLD = (160, 128)
MAX_IMAGES = 640
RECENT_S = 120
OLD_EVERY_S = 8
HEADERS = {
    "A": "[RH3_A] device 00 session 0: egocentric camera history, one frame per second.",   # R5's header format
    "B": "[RH3_B] device 00 session 0: egocentric camera history, frames sampled uniformly from the session start.",
    "C": ("[RH3_C] device 00 session 0: egocentric camera history, one frame every 8 seconds, then one frame per "
          "second for the last 120 seconds."),
}

_W = {}


def orient(hw, w, h):
    """(H, W) for this frame: portrait as given, landscape swapped (R5's rule)."""
    return hw if h >= w else (hw[1], hw[0])


def frames_index(vid):
    return {float(t): FRAMES / vid / f for t, f in json.load(open(FRAMES / vid / "index.json"))["frames"]}


def select(cell, row, idx):
    """[(t, path, (H, W) portrait-base)] in time order."""
    qt = float(row["question_time"])
    ts_all = sorted(t for t in idx if t <= qt + 1e-6)
    if cell == "A":
        sel = [(t, SIZE_A) for t in ts_all[-MAX_IMAGES:]]
    elif cell == "B":
        sel = [(float(t), SIZE_B) for t in row["frame_t"]]
    else:
        sel = [(t, SIZE_C_OLD) for t in ts_all if t < qt - RECENT_S and t % OLD_EVERY_S == 0]
        sel += [(t, SIZE_C_RECENT) for t in ts_all if t >= qt - RECENT_S]
    return [(t, idx[t], hw) for t, hw in sel]


def load(path, hw):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    H, W = orient(hw, im.width, im.height)
    return im.resize((W, H), Image.BICUBIC)


def messages(cell, n, text):
    return [{"role": "user", "content": [{"type": "text", "text": HEADERS[cell]}] + [{"type": "image"}] * n
             + [{"type": "text", "text": text}]}]


def _init():
    import study_o_q4 as O
    from transformers import AutoProcessor
    _W["O"] = O
    _W["proc"] = AutoProcessor.from_pretrained(str(SNAP_I))
    _W["mcq"] = {r["question_id"]: r for r in map(json.loads, open(MCQ))}


def build(row):
    O, P, mcq = _W["O"], _W["proc"], _W["mcq"]
    rec = mcq[row["question_id"]]
    idx = frames_index(row["video_id"])
    out = []
    for cell in ("A", "B", "C"):
        sel = select(cell, row, idx)
        imgs = [load(p, hw) for _, p, hw in sel]
        text = P.apply_chat_template(messages(cell, len(imgs), row["text"]), tokenize=False,
                                     add_generation_prompt=True)
        inp = P(text=[text], images=imgs, images_kwargs=dict(size=PROC_SIZE), return_tensors="pt")
        grids = inp["image_grid_thw"].tolist()
        sizes = [[im.height, im.width] for im in imgs]
        assert all(g[1] * 16 == s[0] and g[2] * 16 == s[1] for g, s in zip(grids, sizes)), (row["question_id"], cell)
        ts = [t for t, _, _ in sel]
        n_qt = sum(1 for t in idx if t <= float(row["question_time"]) + 1e-6)
        out.append(dict(question_id=row["question_id"], video_id=row["video_id"], cell=cell,
                        question_time=row["question_time"], question_category=row["question_category"],
                        correct_letter=row["correct_letter"], n_images=len(imgs), frame_t=ts,
                        hw=[[int(h), int(w)] for h, w in sorted({tuple(s) for s in sizes})],
                        hw_per_image=sizes if cell == "C" else None,
                        image_tokens=int(sum(g[1] * g[2] // 4 + 2 for g in grids)),
                        capped=(cell == "A" and n_qt > MAX_IMAGES), n_frames_available=n_qt,
                        evidence_covered=bool(O.covered(ts, rec)), r1_evidence_covered=row["evidence_covered"],
                        header=HEADERS[cell], text=row["text"], n_input_instruct=int(inp["input_ids"].shape[1]),
                        r1_n_input_instruct=row["n_input_instruct"]))
        for im in imgs:
            im.close()
    return out


def probe(rows):
    """Mean prompt tokens per candidate size: text tokens (HF, zero images) + per-image formula."""
    _init()
    P = _W["proc"]
    n_text = {}
    for r in rows:
        t = P.apply_chat_template(messages("B", 0, r["text"]), tokenize=False, add_generation_prompt=True)
        n_text[r["question_id"]] = len(P.tokenizer(t)["input_ids"])
    tt = np.array(list(n_text.values()), float)
    print(f"text+header tokens: mean {tt.mean():.1f} min {tt.min():.0f} max {tt.max():.0f}")
    tok = lambda hw: (hw[0] // 32) * (hw[1] // 32) + 2  # noqa: E731
    k1 = np.mean([r["n_input_instruct"] for r in rows])
    print(f"K1 mean prompt tokens {k1:.1f}")
    nb = np.array([len(r["frame_t"]) for r in rows], float)
    for hw in [(256, 192), (288, 224), (320, 224), (288, 256), (320, 256)]:
        print(f"B {hw}: {tok(hw)} tok/img, mean {np.mean(tt + nb * tok(hw)):.0f}, max {np.max(tt + nb * tok(hw)):.0f}")
    rec, old = [], []
    for r in rows:
        ts = [t for t in frames_index(r["video_id"]) if t <= float(r["question_time"]) + 1e-6]
        qt = float(r["question_time"])
        old.append(sum(1 for t in ts if t < qt - RECENT_S and t % OLD_EVERY_S == 0))
        rec.append(sum(1 for t in ts if t >= qt - RECENT_S))
    rec, old = np.array(rec, float), np.array(old, float)
    print(f"C recent frames mean {rec.mean():.1f}, old frames mean {old.mean():.1f}")
    for hw in [(288, 224), (320, 256), (352, 256), (352, 288), (384, 288), (416, 320)]:
        v = tt + rec * tok(hw) + old * tok(SIZE_C_OLD)
        print(f"C recent {hw}: {tok(hw)} tok/img, mean {v.mean():.0f}, max {v.max():.0f}")
    na = np.array([min(MAX_IMAGES, sum(1 for t in frames_index(r['video_id']) if t <= float(r['question_time']) + 1e-6))
                   for r in rows], float)
    print(f"A mean {np.mean(tt + na * tok(SIZE_A)):.0f}, images mean {na.mean():.1f}, capped "
          f"{sum(1 for r in rows if sum(1 for t in frames_index(r['video_id']) if t <= float(r['question_time']) + 1e-6) > MAX_IMAGES)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    rows = sorted((r for r in read_jsonl(R1_MANIFEST) if r["construction"] == "RICH"),
                  key=lambda r: (r["video_id"], r["question_id"]))
    rows = rows[: args.limit] if args.limit else rows
    if args.probe:
        return probe(rows)
    done = {r["question_id"] for r in map(json.loads, open(MANIFEST))} if MANIFEST.exists() else set()
    todo = [r for r in rows if r["question_id"] not in done]
    print(f"{len(rows)} questions, {len(done)} done, {len(todo)} to build", flush=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers, initializer=_init) as pool, open(MANIFEST, "a") as out:
        for i, rr in enumerate(pool.imap_unordered(build, todo, chunksize=2), 1):
            for r in rr:
                out.write(json.dumps(r) + "\n")
            out.flush()
            if i % 50 == 0 or i == len(todo):
                print(f"[{i}/{len(todo)}]", flush=True)


if __name__ == "__main__":
    main()
