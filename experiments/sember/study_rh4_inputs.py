#!/usr/bin/env python3
"""StudyRH4 input builder (ORIGINAL .venv: transformers 5.10.2). CPU only.

Fixed-stride separate-image histories: frames at t = 0, s, 2s, ... <= question_time (StudyO's 1 fps frame cache, the
same JPEGs as RH3), never re-spaced, never capped by count, so each new frame is appended after an unchanged prefix.
  D1  stride 2 s, 288x224 (RH3 B's size, 65 tok/img)
  D2  stride 2 s, 352x256 (90 tok/img) — the integer-stride cell nearest K1's 12,127 mean history tokens (s = 2 at
      288x224 gives 8.4k, s = 1 gives 16.7k and overflows the context on 80 questions; see EXPERIMENTS StudyRH4)
Message = [header text, images in time order, R1's question text] exactly as RH3 B (no per-image timestamp markers;
RH3 B had none). Resize / encode / processor bounds: RH3's (study_rh3_inputs.load, PROC_SIZE). Expected prompt
tokens = HF processor on exactly these images. Manifest: results/sember/study_rh4/study_rh4_inputs_manifest.jsonl.
"""
import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_rh3_inputs as B3  # noqa: E402
from rawio import read_jsonl  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO / "results/sember/study_rh4/study_rh4_inputs_manifest.jsonl"
STRIDE_S = 2
SIZES = {"D1": (288, 224), "D2": (352, 256)}
HEADERS = {c: f"[RH4_{c}] device 00 session 0: egocentric camera history, one frame every {STRIDE_S} s from the session start."
           for c in SIZES}
MAX_MODEL_LEN, MAX_TOKENS = 32768, 512


def select(cell, video_id, t_now):
    idx = B3.frames_index(video_id)
    return [(t, idx[t], SIZES[cell]) for t in sorted(idx) if t <= t_now + 1e-6 and t % STRIDE_S == 0]


def messages(cell, n, text):
    return [{"role": "user", "content": [{"type": "text", "text": HEADERS[cell]}] + [{"type": "image"}] * n
             + [{"type": "text", "text": text}]}]


_W = {}


def _init():
    import study_o_q4 as O
    from transformers import AutoProcessor
    _W["O"] = O
    _W["proc"] = AutoProcessor.from_pretrained(str(B3.SNAP_I))
    _W["mcq"] = {r["question_id"]: r for r in map(json.loads, open(B3.MCQ))}


def build(row):
    O, P, mcq = _W["O"], _W["proc"], _W["mcq"]
    rec = mcq[row["question_id"]]
    out = []
    for cell in SIZES:
        sel = select(cell, row["video_id"], float(row["question_time"]))
        imgs = [B3.load(p, hw) for _, p, hw in sel]
        text = P.apply_chat_template(messages(cell, len(imgs), row["text"]), tokenize=False,
                                     add_generation_prompt=True)
        inp = P(text=[text], images=imgs, images_kwargs=dict(size=B3.PROC_SIZE), return_tensors="pt")
        grids = inp["image_grid_thw"].tolist()
        assert all(g[1] * 16 == im.height and g[2] * 16 == im.width for g, im in zip(grids, imgs)), row["question_id"]
        ts = [t for t, _, _ in sel]
        n_in = int(inp["input_ids"].shape[1])
        out.append(dict(question_id=row["question_id"], video_id=row["video_id"], cell=cell,
                        question_time=row["question_time"], question_category=row["question_category"],
                        correct_letter=row["correct_letter"], n_images=len(imgs), frame_t=ts,
                        hw=sorted({(im.height, im.width) for im in imgs}),
                        image_tokens=int(sum(g[1] * g[2] // 4 + 2 for g in grids)),
                        evidence_covered=bool(O.covered(ts, rec)), r1_evidence_covered=row["evidence_covered"],
                        header=HEADERS[cell], text=row["text"], n_input_instruct=n_in,
                        over_context=n_in + MAX_TOKENS > MAX_MODEL_LEN, hw_per_image=None))
        for im in imgs:
            im.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()
    rows = sorted((r for r in read_jsonl(B3.R1_MANIFEST) if r["construction"] == "RICH"),
                  key=lambda r: (r["video_id"], r["question_id"]))
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
