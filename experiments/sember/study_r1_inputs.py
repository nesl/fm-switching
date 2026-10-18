#!/usr/bin/env python3
"""StudyR1 input builder (ORIGINAL .venv: transformers 5.10.2, qwen_vl_utils — StudyO's exact preprocessing stack).

For each of StudyO's 845 questions and each construction (RICH, RECENT) this reproduces study_o_q4.py exactly:
cache_video (1 fps JPEG q88) -> select (RICH: [0, qt] capped at 256, uniform; RECENT: last 120 s) -> build_messages
(frames as a VIDEO, sample_fps 1.0) -> process_vision_info -> processor (min/max pixels as StudyO, VideoMetadata
fps=1, frames_indices=round(t), total_num_frames=round(qt)).

Then, so that vLLM receives the SAME video without re-deriving it, the processor's own final resize (smart_resize to
its total-pixel budget, bicubic) is applied here in float and rounded to uint8. vLLM's processor then sees frames
already at the final size, so its resize is a no-op and the patch grid is identical. Verified on the first video:
identical prompt token ids; pixel difference vs StudyO's float path = uint8 rounding + clipping of bicubic overshoot
(mean |d| 0.0018, max 0.128 in normalised units).

Per request -> ~/.cache/fm-switching/r1_inputs/<CONSTRUCTION>/<qid>.npz (outside the repo):
  frames uint8 [T_padded, 3, H, W] (qwen_vl_utils' even-padded set), frames_indices (len T_padded; last repeated
  if padded), ids_instruct / ids_thinking (expected prompt token ids under the 32B-I / 32B-T chat templates).
Manifest (repo): results/sember/study_r1/study_r1_inputs_manifest.jsonl (one row per question x construction).
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parent.parent.parent
TRIALS = REPO / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
MANIFEST = REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl"
VIDEOS = Path(os.environ.get("SEMBER_VIDEOS", Path.home() / ".cache/fm-switching/sember_videos"))
FRAMES = Path.home() / ".cache/fm-switching/sember_frames"
OUT = Path.home() / ".cache/fm-switching/r1_inputs"
HUB = Path.home() / ".cache/huggingface/hub"
SNAP = {"I": HUB / "models--Qwen--Qwen3-VL-32B-Instruct/snapshots/0cfaf48183f594c314753d30a4c4974bc75f3ccb",
        "T": HUB / "models--Qwen--Qwen3-VL-32B-Thinking/snapshots/7edd10ffd1196091948fb245ff63e406ccb2d4d1"}

_W = {}


def _init():
    import study_o_q4 as O
    from transformers import AutoProcessor
    O.VIDEOS, O.CACHE, O.MCQ = VIDEOS, FRAMES, REPO / "results/sember/study_h/data/sember_mcq.jsonl"
    _W["O"] = O
    _W["proc"] = {k: AutoProcessor.from_pretrained(str(p), min_pixels=O.MIN_PIXELS, max_pixels=O.MAX_PIXELS)
                  for k, p in SNAP.items()}
    _W["mcq"] = {r["question_id"]: r for r in map(json.loads, open(O.MCQ))}


def build_video(args):
    vid, qids, max_qt = args
    import PIL.Image
    import torch
    from qwen_vl_utils import process_vision_info
    from transformers.image_processing_utils_fast import SizeDict
    from transformers.models.qwen3_vl.video_processing_qwen3_vl import smart_resize
    from transformers.video_utils import VideoMetadata
    O, P, mcq = _W["O"], _W["proc"], _W["mcq"]
    cached = O.cache_video(vid, max_qt)
    rows = []
    for qid in qids:
        rec = mcq[qid]
        qt = float(rec["question_time"])
        for cons in ("RICH", "RECENT"):
            dest = OUT / cons / f"{qid}.npz"
            ts, paths = O.select(cons, cached, qt)
            imgs = [PIL.Image.open(p).convert("RGB") for p in paths]
            msgs = O.build_messages(rec, imgs)
            idx = [int(round(t)) for t in ts]
            vmeta = VideoMetadata(fps=1.0, frames_indices=idx, total_num_frames=max(1, round(qt)))
            _, vi, vkw = process_vision_info(msgs, return_video_kwargs=True)
            if "fps" in vkw and isinstance(vkw["fps"], list):
                vkw["fps"] = vkw["fps"][0] if vkw["fps"] else None
            row = dict(question_id=qid, video_id=vid, construction=cons, question_time=qt,
                       question_category=rec["question_category"], correct_letter=rec["correct_letter"],
                       n_frames=len(ts), frame_t=ts, evidence_covered=O.covered(ts, rec),
                       total_num_frames=max(1, round(qt)), text=msgs[0]["content"][1]["text"])
            if not dest.exists():
                ids = {}
                for k in ("I", "T"):
                    text = P[k].apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                    inp = P[k](text=[text], videos=vi, video_metadata=vmeta, return_tensors="pt", **vkw)
                    ids[k] = inp["input_ids"][0].numpy().astype(np.int32)
                    grid = inp["video_grid_thw"][0].tolist()
                vp = P["I"].video_processor
                T_, _, H_, W_ = vi[0].shape
                rh, rw = smart_resize(num_frames=T_, height=H_, width=W_, temporal_factor=vp.temporal_patch_size,
                                      factor=vp.patch_size * vp.merge_size, min_pixels=vp.size["shortest_edge"],
                                      max_pixels=vp.size["longest_edge"])
                fin = vp.resize(vi[0], size=SizeDict(height=rh, width=rw), resample=vp.resample)
                fin = fin.round().clamp(0, 255).to(torch.uint8).numpy()
                fidx = idx + [idx[-1]] * (T_ - len(idx))
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".tmp.npz")
                np.savez_compressed(tmp, frames=fin, frames_indices=np.array(fidx, np.int32),
                                    ids_instruct=ids["I"], ids_thinking=ids["T"], grid=np.array(grid, np.int32))
                os.replace(tmp, dest)
                row.update(n_frames_padded=int(T_), final_hw=[int(rh), int(rw)], grid_thw=grid,
                           n_input_instruct=int(len(ids["I"])), n_input_thinking=int(len(ids["T"])))
            else:
                z = np.load(dest)
                row.update(n_frames_padded=int(z["frames"].shape[0]), final_hw=list(z["frames"].shape[2:]),
                           grid_thw=z["grid"].tolist(), n_input_instruct=int(len(z["ids_instruct"])),
                           n_input_thinking=int(len(z["ids_thinking"])))
            for im in imgs:
                im.close()
            rows.append(row)
    return vid, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--videos", type=int, default=None, help="only the first N videos (probe)")
    args = ap.parse_args()
    T = [json.loads(l) for l in open(TRIALS)]
    byvid = {}
    for t in T:
        byvid.setdefault(t["video_id"], set()).add(t["question_id"])
    vids = sorted(byvid)[: args.videos] if args.videos else sorted(byvid)
    done = set()
    if MANIFEST.exists():
        done = {json.loads(l)["video_id"] for l in open(MANIFEST)}
    mcq_qt = {t["question_id"]: t["question_time"] for t in T}
    todo = [(v, sorted(byvid[v]), max(mcq_qt[q] for q in byvid[v])) for v in vids
            if v not in done and (VIDEOS / f"{v}.mp4").exists()]
    print(f"{len(vids)} videos, {len(done)} already in manifest, {len(todo)} available to build", flush=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers, initializer=_init) as pool, open(MANIFEST, "a") as out:
        for i, (vid, rows) in enumerate(pool.imap_unordered(build_video, todo), 1):
            for r in rows:
                out.write(json.dumps(r) + "\n")
            out.flush()
            print(f"[{i}/{len(todo)}] {vid}: {len(rows)} requests", flush=True)


if __name__ == "__main__":
    main()
