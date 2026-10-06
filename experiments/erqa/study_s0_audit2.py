#!/usr/bin/env python3
"""Study S0 Audit 2 — Decoding and software-stack validation.
Run 4B-Thinking on 100 ERQA questions under 3 decoding configs.
"""

import os, sys, json, re, time, math, random
import torch
import torch.nn as nn
from pathlib import Path
from collections import defaultdict

if not hasattr(nn.Module, 'set_submodule'):
    def _set_submodule(self, target, module):
        parts = target.split('.')
        parent = self
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], module)
    nn.Module.set_submodule = _set_submodule

from datasets import load_dataset
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info
import transformers
import PIL.Image

if not hasattr(PIL.Image, 'ExifTags'):
    class _Base:
        Orientation = 274
    class _FakeExifTags:
        Base = _Base()
    PIL.Image.ExifTags = _FakeExifTags()

PATH_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
OUT_DIR = Path("results/erqa/study_s0")
OUT_DIR.mkdir(parents=True, exist_ok=True)
JSONL = OUT_DIR / "audit2_trials.jsonl"
N_QUESTIONS = 100
SEED = 42

CONFIGS = {
    "CFG-A": dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20,
                  max_new_tokens=8192),
    "CFG-B": dict(do_sample=True, temperature=1.0, top_p=0.95, top_k=20,
                  max_new_tokens=40960),
    "CFG-C": dict(do_sample=True, temperature=1.0, top_p=0.95, top_k=20,
                  max_new_tokens=16384),
}

ANSWER_RE = re.compile(r'<answer>\s*([A-Ea-e])\s*</answer>', re.IGNORECASE)
ANSWER_LAST_RE = re.compile(r'\b([A-E])\b')


def load_erqa_100():
    ds = load_dataset("RunsenXu/ERQA", split="test")
    rng = random.Random(SEED)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    selected = sorted(indices[:N_QUESTIONS])
    rows = []
    for idx in selected:
        row = ds[idx]
        row["question_id"] = idx
        rows.append(row)
    return rows


def build_messages(row):
    q_text = row["question"]
    images = row["images_encoded"]
    content = []
    img_idx = 0
    for j, part in enumerate(q_text.split("<image>")):
        if j > 0 and img_idx < len(images):
            content.append({"type": "image", "image": images[img_idx]})
            img_idx += 1
        if part:
            content.append({"type": "text", "text": part})
    while img_idx < len(images):
        content.append({"type": "image", "image": images[img_idx]})
        img_idx += 1
    return [{"role": "user", "content": content}]


def detect_repetition(text, n=10, window=500):
    """Fraction of last `window` chars that is verbatim n-gram repetition."""
    tail = text[-window:] if len(text) > window else text
    words = tail.split()
    if len(words) < 2 * n:
        return False
    ngrams = [tuple(words[i:i+n]) for i in range(len(words)-n)]
    seen = set()
    for ng in ngrams:
        if ng in seen:
            return True
        seen.add(ng)
    return False


def load_done():
    done = set()
    if JSONL.exists():
        for line in open(JSONL):
            t = json.loads(line)
            done.add((t["config"], t["question_id"]))
    return done


def main():
    import transformers as tr
    print(f"transformers: {tr.__version__}")
    print(f"torch: {torch.__version__}")
    major, minor, *_ = tr.__version__.split(".")
    if int(major) >= 5 and int(minor) >= 17:
        print("!!! WARNING: transformers 5.17.x — Qwen3-VL looping issue known !!!")
    else:
        print(f"  Looping issue: NOT AFFECTED ({tr.__version__})")
    print(f"4B-Thinking snapshot: {PATH_4BT.split('/')[-1]}")
    print(f"GPUs: {torch.cuda.device_count()}")
    print()

    print("Loading ERQA 100-question subset...")
    ds = load_erqa_100()
    print(f"  {len(ds)} questions selected")
    done = load_done()
    print(f"  Already done: {len(done)} trials")

    print("Loading 4B-Thinking model...")
    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        PATH_4BT, torch_dtype=torch.bfloat16, device_map="cuda:1"
    )
    processor = AutoProcessor.from_pretrained(PATH_4BT)
    print(f"  Loaded in {time.time()-t0:.1f}s")
    vram = {i: round(torch.cuda.memory_allocated(i)/1e9, 2)
            for i in range(torch.cuda.device_count())}
    print(f"  VRAM: {vram}")
    print()

    out_f = open(JSONL, "a")

    for cfg_name, gen_kwargs in CONFIGS.items():
        todo = [row for row in ds if (cfg_name, row["question_id"]) not in done]
        print(f"=== {cfg_name}: {len(todo)} questions ===")
        if not todo:
            print("  All done, skipping.")
            continue

        torch.manual_seed(SEED)
        correct_n = 0
        budget_hits = 0
        think_lens = []
        loops = 0

        for i, row in enumerate(todo):
            qid = row["question_id"]
            messages = build_messages(row)
            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text], images=image_inputs, videos=video_inputs,
                padding=True, return_tensors="pt"
            ).to(model.device)

            n_input = inputs["input_ids"].shape[1]
            t_start = time.time()
            with torch.no_grad():
                out_ids = model.generate(**inputs, **gen_kwargs)
            lat_ms = (time.time() - t_start) * 1000

            gen_ids = out_ids[0][n_input:]
            n_gen = len(gen_ids)
            output_text = processor.decode(gen_ids, skip_special_tokens=False)

            # Chat template injects <think>\n into the prompt; gen starts inside
            # the think block, so look for </think> to detect closure.
            END_TAG = '</think>'
            if END_TAG in output_text:
                idx = output_text.index(END_TAG)
                think_text = output_text[:idx]
                think_closed = True
                answer_text = output_text[idx + len(END_TAG):]
                n_think = len(processor.tokenizer.tokenize(think_text))
            else:
                think_closed = False
                answer_text = output_text
                n_think = 0

            budget_hit = (n_gen >= gen_kwargs["max_new_tokens"] - 5)
            if budget_hit:
                budget_hits += 1

            has_loop = detect_repetition(output_text)
            if has_loop:
                loops += 1

            m = ANSWER_RE.search(answer_text)
            if m:
                pred = m.group(1).upper()
            else:
                matches = ANSWER_LAST_RE.findall(answer_text[-200:])
                pred = matches[-1].upper() if matches else "X"

            is_correct = (pred == row["answer"]) and think_closed
            correct_n += is_correct
            think_lens.append(n_think)

            trial = {
                "config": cfg_name,
                "question_id": qid,
                "correct": bool(is_correct),
                "pred": pred,
                "answer": row["answer"],
                "think_closed": think_closed,
                "budget_hit": budget_hit,
                "has_loop": has_loop,
                "n_input": n_input,
                "n_think": n_think,
                "n_gen": n_gen,
                "lat_ms": round(lat_ms, 1),
            }
            out_f.write(json.dumps(trial) + "\n")
            out_f.flush()

            if (i+1) % 20 == 0:
                print(f"  [{cfg_name}] q{i+1}/{len(todo)} "
                      f"acc={correct_n/(i+1)*100:.1f}%")

        n_done = len(todo)
        import numpy as np
        print(f"  DONE: acc={correct_n/n_done*100:.1f}%  "
              f"budget_hit={budget_hits}/{n_done} ({budget_hits/n_done*100:.1f}%)  "
              f"loops={loops}/{n_done} ({loops/n_done*100:.1f}%)")
        if think_lens:
            arr = np.array(think_lens)
            print(f"  think tokens: median={np.median(arr):.0f}  "
                  f"IQR=[{np.percentile(arr,25):.0f},{np.percentile(arr,75):.0f}]  "
                  f"max={arr.max()}")
        print()

    out_f.close()
    print("Audit 2 complete.")


if __name__ == "__main__":
    main()
