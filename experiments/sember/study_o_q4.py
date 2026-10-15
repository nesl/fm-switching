#!/usr/bin/env python3
"""Study O — Q4 only (3 cells, not the 9-cell factorial).

Authorised 2026-10-14 after the §8 halt: the failed check was Q1's cell-balance
requirement, which Q4 does not depend on. Q4's own power check passed.

Cells (plan §3 "Q4 designations"):
  local            = 4B-I  x RECENT
  remote (Instruct)= 8B-I  x RICH
  remote (Thinking)= 4B-T  x RICH

D1: 4B-T resolves to Qwen3-VL-4B-Thinking (separate checkpoint, not a flag).
D2: CFG-A decoding; instruct arms greedy.
D3: max_new_tokens 8192 for thinking; think_closed/budget_hit per trial.
D4: evidence_covered computed from ACTUAL sampled frame timestamps.
"""

import argparse, json, os, re, time
from pathlib import Path

import av
import torch
import torch.nn as nn

if not hasattr(nn.Module, "set_submodule"):
    def _set_submodule(self, target, module):
        parts = target.split(".")
        parent = self
        for p in parts[:-1]:
            parent = getattr(parent, p)
        setattr(parent, parts[-1], module)
    nn.Module.set_submodule = _set_submodule

import PIL.Image
if not hasattr(PIL.Image, "ExifTags"):
    class _B: Orientation = 274
    class _F: Base = _B()
    PIL.Image.ExifTags = _F()

from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from transformers.video_utils import VideoMetadata
from qwen_vl_utils import process_vision_info

# Match StudyI3's validated processor config: the per-frame pixel cap is what
# keeps dense arms at ~44-56 tok/frame instead of ~660.
MIN_PIXELS = 256 * 28 * 28
MAX_PIXELS = 1280 * 28 * 28

ROOT = Path("/home/pragya/Desktop/FM-switching")
MCQ = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
VIDEOS = ROOT / "results/sember/study_i/videos"
OUT_DIR = ROOT / "results/sember/study_o"
JSONL = OUT_DIR / "study_o_q4_trials.jsonl"
CACHE = Path(os.environ.get("O_FRAME_CACHE",
                            "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/"
                            "8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/oframes"))

SNAP = {
    "4B-I": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17",
    "8B-I": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
    "4B-T": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e",
}
# D2 / D3
GEN = {
    "4B-I": dict(do_sample=False, max_new_tokens=512),
    "8B-I": dict(do_sample=False, max_new_tokens=512),
    "4B-T": dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20,
                 min_p=0.0, max_new_tokens=8192),
}
CELLS = [("4B-I", "RECENT"), ("8B-I", "RICH"), ("4B-T", "RICH")]

RECENT_W = 120.0
RICH_CAP = 256
LETTER = re.compile(r"\b([A-E])\b")
END_TAG = "</think>"


def load_questions():
    have = {p.stem for p in VIDEOS.glob("*.mp4")}
    recs = [json.loads(l) for l in open(MCQ)]
    out = []
    for r in recs:
        if r["video_id"] not in have:
            continue
        if r.get("answer_start_time") is None:
            continue
        qt = float(r["question_time"])
        far = qt - min(float(r["answer_start_time"]), float(r["answer_end_time"]))
        if far < 0:
            continue
        r["farthest"] = far
        out.append(r)
    out.sort(key=lambda r: (r["video_id"], r["question_id"]))
    return out


def cache_video(video_id, max_qt):
    """Decode once at 1 fps up to max_qt; cache JPEGs. Returns sorted [(t, path)]."""
    d = CACHE / video_id
    idx = d / "index.json"
    if idx.exists():
        try:
            saved = json.load(open(idx))
            if saved["max_qt"] >= max_qt - 1:
                return [(t, d / f) for t, f in saved["frames"]]
        except Exception:
            pass
    d.mkdir(parents=True, exist_ok=True)
    container = av.open(str(VIDEOS / f"{video_id}.mp4"))
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    tb = float(stream.time_base)
    frames, next_t = [], 0.0
    for frame in container.decode(stream):
        if frame.pts is None:
            continue
        t = frame.pts * tb
        if t + 1e-6 < next_t:
            continue
        if t > max_qt + 1.0:
            break
        fn = f"{int(round(t)):05d}.jpg"
        frame.to_image().save(d / fn, quality=88)
        frames.append((round(t, 3), fn))
        next_t = t + 1.0
    container.close()
    json.dump({"max_qt": max_qt, "frames": frames}, open(idx, "w"))
    return [(t, d / f) for t, f in frames]


def select(arm, cached, qt):
    """Return (timestamps, paths) actually sampled for this arm."""
    if arm == "RECENT":
        lo = max(0.0, qt - RECENT_W)
        sel = [(t, p) for t, p in cached if lo - 1e-6 <= t <= qt + 1e-6]
    else:  # RICH
        sel = [(t, p) for t, p in cached if t <= qt + 1e-6]
        if len(sel) > RICH_CAP:
            step = (len(sel) - 1) / (RICH_CAP - 1)
            sel = [sel[int(round(i * step))] for i in range(RICH_CAP)]
    if not sel and cached:
        sel = [cached[0]]
    return [t for t, _ in sel], [p for _, p in sel]


def covered(ts, rec):
    """D4: any SAMPLED timestamp inside [answer_start_time, answer_end_time]."""
    a = float(rec["answer_start_time"]); b = float(rec["answer_end_time"])
    if b < a:
        a, b = b, a
    return any(a <= t <= b for t in ts)


def build_messages(rec, frames):
    """Frames go in as a VIDEO so the processor's per-frame pixel cap applies."""
    return [{"role": "user", "content": [
        {"type": "video", "video": frames, "sample_fps": 1.0},
        {"type": "text", "text":
            "Watch the video carefully, then answer the following "
            f"multiple-choice question.\n\nQuestion: {rec['question']}\n\n"
            + "\n".join(rec["options"]) +
            "\n\nReply with only the letter of the correct answer "
            "(A, B, C, D, or E)."},
    ]}]


def done_keys():
    s = set()
    if JSONL.exists():
        for line in open(JSONL):
            try:
                t = json.loads(line)
            except json.JSONDecodeError:
                continue
            s.add((t["model_arm"], t["state_arm"], t["question_id"]))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, choices=["4B-I", "8B-I", "4B-T"])
    ap.add_argument("--device", default="cuda:1")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    model_arm = args.cell
    state_arm = dict(CELLS)[model_arm]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    qs = load_questions()
    done = done_keys()
    todo = [r for r in qs if (model_arm, state_arm, r["question_id"]) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"cell {model_arm} x {state_arm}: {len(qs)} questions, "
          f"{len(todo)} to run", flush=True)
    if not todo:
        print("nothing to do"); return

    max_qt = {}
    for r in qs:
        max_qt[r["video_id"]] = max(max_qt.get(r["video_id"], 0.0),
                                    float(r["question_time"]))

    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        SNAP[model_arm], torch_dtype=torch.bfloat16, device_map=args.device)
    proc = AutoProcessor.from_pretrained(
        SNAP[model_arm], min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    print(f"loaded {model_arm} in {time.time()-t0:.1f}s "
          f"VRAM={torch.cuda.memory_allocated(model.device)/1e9:.1f}GB", flush=True)

    out = open(JSONL, "a")
    torch.manual_seed(42)
    n_ok = n_run = 0
    cur_vid, cached = None, None

    for i, rec in enumerate(todo):
        vid = rec["video_id"]
        if vid != cur_vid:
            cached = cache_video(vid, max_qt[vid])
            cur_vid = vid
        qt = float(rec["question_time"])
        ts, paths = select(state_arm, cached, qt)
        imgs = [PIL.Image.open(p).convert("RGB") for p in paths]
        msgs = build_messages(rec, imgs)
        text = proc.apply_chat_template(msgs, tokenize=False,
                                        add_generation_prompt=True)
        vmeta = VideoMetadata(fps=1.0, frames_indices=[int(round(t)) for t in ts],
                              total_num_frames=max(1, round(qt)))
        image_inputs, video_inputs, vkw = process_vision_info(
            msgs, return_video_kwargs=True)
        if "fps" in vkw and isinstance(vkw["fps"], list):
            vkw["fps"] = vkw["fps"][0] if vkw["fps"] else None
        inputs = proc(text=[text], images=image_inputs, videos=video_inputs,
                      video_metadata=vmeta, return_tensors="pt",
                      **vkw).to(model.device)
        n_in = inputs["input_ids"].shape[1]

        t1 = time.time()
        with torch.no_grad():
            ids = model.generate(**inputs, **GEN[model_arm])
        lat = (time.time() - t1) * 1000
        gen = ids[0][n_in:]
        txt = proc.decode(gen, skip_special_tokens=False)

        if model_arm == "4B-T":
            if END_TAG in txt:
                k = txt.index(END_TAG)
                think_closed = True
                n_think = len(proc.tokenizer.tokenize(txt[:k]))
                ans = txt[k + len(END_TAG):]
            else:
                think_closed, n_think, ans = False, 0, txt
        else:
            think_closed, n_think, ans = None, 0, txt

        hits = LETTER.findall(ans[-300:])
        pred = hits[-1] if hits else "X"
        correct = bool(pred == rec["correct_letter"]
                       and think_closed is not False)
        n_ok += correct; n_run += 1

        out.write(json.dumps({
            "model_arm": model_arm, "state_arm": state_arm,
            "question_id": rec["question_id"], "video_id": vid,
            "question_category": rec["question_category"],
            "question_time": qt, "farthest": rec["farthest"],
            "correct": correct, "pred": pred,
            "correct_letter": rec["correct_letter"],
            "evidence_covered": covered(ts, rec),
            "n_frames": len(ts),
            "frame_t_min": min(ts) if ts else None,
            "frame_t_max": max(ts) if ts else None,
            "think_closed": think_closed,
            "budget_hit": bool(len(gen) >= GEN[model_arm]["max_new_tokens"] - 5),
            "n_input": n_in, "n_think": n_think, "n_gen": len(gen),
            "lat_ms": round(lat, 1),
        }) + "\n")
        out.flush()
        for im in imgs:
            im.close()

        if n_run == 10:
            per = (time.time() - t0) / 10
            print(f"\n[PROJECTION] {per:.1f}s/question over 10 trials "
                  f"=> {per*len(todo)/3600:.2f}h for {len(todo)} in this cell\n",
                  flush=True)
        if n_run % 25 == 0:
            print(f"  [{model_arm}] {n_run}/{len(todo)} acc={n_ok/n_run*100:.1f}% "
                  f"elapsed={(time.time()-t0)/3600:.2f}h", flush=True)

    out.close()
    print(f"cell {model_arm} done: {n_ok}/{n_run} = {n_ok/max(n_run,1)*100:.1f}%",
          flush=True)


if __name__ == "__main__":
    main()
