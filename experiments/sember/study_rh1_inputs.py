#!/usr/bin/env python3
"""StudyRH1 input builder (ORIGINAL .venv: transformers 5.10.2 — StudyO / StudyR1 preprocessing stack). CPU only.

H1a (HALF) / H1b (QUARTER): R1's RICH input with its frame list uniformly subsampled to 50% / 25%, order kept, at
R1's per-frame resolution. Starting point = R1's final-size uint8 RICH frames (~/.cache/fm-switching/r1_inputs/RICH;
built by study_r1_inputs.py). The first n_frames entries are R1's selected frames (the rest are qwen_vl_utils' even
padding). Keep k = max(1, round(n·f)) frames at indices round(i·(n−1)/(k−1)) (StudyO's own RICH-cap rule), then pad
to even by repeating the last frame (as qwen_vl_utils does).

Per-frame resolution is held at R1's on purpose. Rerunning StudyO's pipeline on fewer frames would let the
processor's total-pixel budget upscale every frame (RECENT's 121 frames came out at 512x384 vs RICH's 352x256),
which keeps prompt tokens near 12.5k instead of halving them. Here the frames are already at the final size and
inside the processor's pixel bounds, so smart_resize is a no-op (asserted: HF grid h,w == R1's grid h,w).

Per question -> ~/.cache/fm-switching/rh1_inputs/<HALF|QUARTER>/<qid>.npz (outside the repo; frame INDICES only, the
pixels are read from R1's npz at request time): keep (into R1's frames), frames_indices (padded), ids_instruct
(expected prompt ids under the 32B-I chat template, HF processor on exactly the frames vLLM will receive).
Manifest (repo): results/sember/study_rh1/study_rh1_inputs_manifest.jsonl.
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
MANIFEST = REPO / "results/sember/study_rh1/study_rh1_inputs_manifest.jsonl"
MCQ = REPO / "results/sember/study_h/data/sember_mcq.jsonl"
R1_INP = Path.home() / ".cache/fm-switching/r1_inputs"
OUT = Path.home() / ".cache/fm-switching/rh1_inputs"
SNAP_I = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/"
          "0cfaf48183f594c314753d30a4c4974bc75f3ccb")
FRACTIONS = {"HALF": 0.5, "QUARTER": 0.25}

_W = {}


def keep_idx(n, f):
    k = max(1, int(round(n * f)))
    if k == 1:
        return [0]
    step = (n - 1) / (k - 1)
    return [int(round(i * step)) for i in range(k)]


def _init():
    import study_o_q4 as O
    from transformers import AutoProcessor
    _W["O"] = O
    _W["proc"] = AutoProcessor.from_pretrained(str(SNAP_I), min_pixels=O.MIN_PIXELS, max_pixels=O.MAX_PIXELS)
    _W["mcq"] = {r["question_id"]: r for r in map(json.loads, open(MCQ))}


def build(row):
    import torch
    from transformers.video_utils import VideoMetadata
    O, P, mcq = _W["O"], _W["proc"], _W["mcq"]
    rec = mcq[row["question_id"]]
    z = np.load(R1_INP / "RICH" / f"{row['question_id']}.npz")
    n = row["n_frames"]
    r1_idx = [int(i) for i in z["frames_indices"][:n]]
    out = []
    for cons, f in FRACTIONS.items():
        keep = keep_idx(n, f)
        ts = [row["frame_t"][i] for i in keep]
        idx = [r1_idx[i] for i in keep]
        keep_p = keep + [keep[-1]] * (len(keep) % 2)
        fidx = idx + [idx[-1]] * (len(keep) % 2)
        dest = OUT / cons / f"{row['question_id']}.npz"
        msgs = O.build_messages(rec, [])
        text = P.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        vid = torch.from_numpy(z["frames"][keep_p])
        vmeta = VideoMetadata(fps=1.0, frames_indices=idx, total_num_frames=row["total_num_frames"])
        inp = P(text=[text], videos=[vid], video_metadata=vmeta, fps=1.0, do_sample_frames=False,
                  return_tensors="pt")
        ids = inp["input_ids"][0].numpy().astype(np.int32)
        grid = inp["video_grid_thw"][0].tolist()
        assert grid[1:] == row["grid_thw"][1:] and grid[0] == len(keep_p) // 2, (row["question_id"], cons, grid,
                                                                                 row["grid_thw"], len(keep_p))
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp.npz")
        np.savez(tmp, keep=np.array(keep_p, np.int32), frames_indices=np.array(fidx, np.int32), ids_instruct=ids,
                 grid=np.array(grid, np.int32))
        os.replace(tmp, dest)
        out.append(dict(question_id=row["question_id"], video_id=row["video_id"], construction=cons,
                        question_time=row["question_time"], question_category=row["question_category"],
                        correct_letter=row["correct_letter"], n_frames=len(keep), r1_n_frames=n, frame_t=ts,
                        evidence_covered=O.covered(ts, rec), r1_evidence_covered=row["evidence_covered"],
                        total_num_frames=row["total_num_frames"], text=row["text"], n_frames_padded=len(keep_p),
                        final_hw=row["final_hw"], grid_thw=grid, n_input_instruct=int(len(ids)),
                        r1_n_input_instruct=row["n_input_instruct"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None, help="first N questions only (probe)")
    args = ap.parse_args()
    rows = sorted((r for r in read_jsonl(R1_MANIFEST) if r["construction"] == "RICH"),
                  key=lambda r: (r["video_id"], r["question_id"]))
    rows = rows[: args.limit] if args.limit else rows
    done = {r["question_id"] for r in map(json.loads, open(MANIFEST))} if MANIFEST.exists() else set()
    todo = [r for r in rows if r["question_id"] not in done]
    print(f"{len(rows)} questions, {len(done)} done, {len(todo)} to build", flush=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers, initializer=_init) as pool, open(MANIFEST, "a") as out:
        for i, rr in enumerate(pool.imap_unordered(build, todo, chunksize=4), 1):
            for r in rr:
                out.write(json.dumps(r) + "\n")
            out.flush()
            if i % 50 == 0 or i == len(todo):
                print(f"[{i}/{len(todo)}]", flush=True)


if __name__ == "__main__":
    main()
