#!/usr/bin/env python3
"""Study K: Reasoning gate on ERQA — Qwen3-VL-4B-Thinking vs 4B-Instruct.

DECODING CORRECTION (2026-09-21):
  Initial run used do_sample=False (greedy) for THINKING — invalid.
  Qwen3-VL model card: "DO NOT use greedy decoding" for thinking mode.
  Model's generation_config.json specifies do_sample=True, top_k=20, top_p=0.95.
  Corrected THINKING decoding: temperature=0.6, top_p=0.95, top_k=20, min_p=0,
  do_sample=True, max_new_tokens=16384, 3 seeds.
  INSTRUCT greedy run is valid (replicated 42.0% vs published 41.3%).

Arms:
  INSTRUCT          greedy, max_new_tokens=512,   1 run  (already done, use --resume)
  INSTRUCT_PERMUTED greedy, max_new_tokens=512,   1 run  (already done)
  THINKING          sampled, max_new_tokens=16384, 3 seeds
  THINKING-QUICK    sampled, max_new_tokens=16384, 3 seeds
  THINKING_PERMUTED sampled, max_new_tokens=16384, 3 seeds

Data: RunsenXu/ERQA (HuggingFace, 400 questions, 28.2% multi-image).
"""

import os, sys, json, re, time, argparse
import torch
from pathlib import Path
from collections import Counter
from datasets import load_dataset
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

INSTRUCT_PATH = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
THINKING_PATH  = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
DEVICE         = "cuda:1"

THINKING_SEEDS = [42, 123, 456]

# Arms: instruct arms use seed=None (greedy); thinking arms run 3 seeds each.
ARMS = [
    {"name": "INSTRUCT",          "model": "instruct", "max_new_tokens": 512,   "quick": False, "permuted": False, "seeds": [None]},
    {"name": "INSTRUCT_PERMUTED", "model": "instruct", "max_new_tokens": 512,   "quick": False, "permuted": True,  "seeds": [None]},
    {"name": "THINKING",          "model": "thinking", "max_new_tokens": 16384, "quick": False, "permuted": False, "seeds": THINKING_SEEDS},
    {"name": "THINKING-QUICK",    "model": "thinking", "max_new_tokens": 16384, "quick": True,  "permuted": False, "seeds": THINKING_SEEDS},
    {"name": "THINKING_PERMUTED", "model": "thinking", "max_new_tokens": 16384, "quick": False, "permuted": True,  "seeds": THINKING_SEEDS},
]

# Exact wording of the quick-thinking instruction
QUICK_SUFFIX = " Answer quickly without overthinking."

# Model card sampling parameters for THINKING
THINKING_GEN_KWARGS = dict(
    do_sample=True,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    min_p=0.0,
)

OUT_DIR    = Path("results/erqa/study_k")
JSONL_PATH  = OUT_DIR / "study_k_trials.jsonl"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_erqa():
    ds = load_dataset("RunsenXu/ERQA", verification_mode="no_checks")["test"]
    return ds


def parse_options(q_text):
    """Return {A: str, ...} for 2/3/4-option questions, or None."""
    m = re.search(r'Choices:\s+(.*?)(?:\s+Please\s+answer|\s*$)', q_text, re.DOTALL)
    if not m:
        return None
    parts = re.split(r'\b([A-D])\.\s+', m.group(1))
    opts = {}
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            opts[parts[i]] = parts[i + 1].strip()
    return opts if len(opts) in (2, 3, 4) else None


def permute_question(q_text, correct_letter):
    """Cyclically shift options by 1: correct letter advances A→B, B→C, C→D, D→A."""
    opts = parse_options(q_text)
    if opts is None:
        return None, None
    letters = sorted(opts.keys())
    n = len(letters)
    old_idx = letters.index(correct_letter)
    old_list = [opts[l] for l in letters]
    new_list  = [old_list[(i - 1) % n] for i in range(n)]
    new_correct = letters[(old_idx + 1) % n]
    choices_str = ' '.join(f'{letters[i]}. {new_list[i]}' for i in range(n))
    new_q = re.sub(r'Choices:.*?(?=Please\s+answer)', f'Choices: {choices_str} ', q_text, flags=re.DOTALL)
    return new_q, new_correct


def build_messages(row, quick=False, permuted=False):
    """Return (messages, effective_correct_letter, build_status)."""
    q_text = row['question']
    images  = row['images_encoded']
    correct = row['answer']

    if permuted:
        new_q, correct = permute_question(q_text, correct)
        if new_q is None:
            return None, correct, "permute_failed"
        q_text = new_q

    if quick:
        q_text = q_text + QUICK_SUFFIX

    content = []
    img_idx = 0
    for j, part in enumerate(q_text.split('<image>')):
        if j > 0 and img_idx < len(images):
            content.append({"type": "image", "image": images[img_idx]})
            img_idx += 1
        if part:
            content.append({"type": "text", "text": part})
    while img_idx < len(images):
        content.append({"type": "image", "image": images[img_idx]})
        img_idx += 1

    return [{"role": "user", "content": content}], correct, "ok"


# ---------------------------------------------------------------------------
# Answer parsing
# ---------------------------------------------------------------------------

def extract_letter(text):
    """Return (letter_or_None, parse_status)."""
    t = text.strip()
    if t and t[0] in 'ABCD' and (len(t) == 1 or t[1] in '.\n ):,'):
        return t[0], "direct"
    m = re.search(r'(?:answer is|answer:|the answer)\s*[:\s]*([A-D])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(r'\b([A-D])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def run_arm(arm_cfg, seed, ds, model, processor):
    """Run one arm × one seed. Returns list of trial dicts."""
    arm_name       = arm_cfg["name"]
    quick          = arm_cfg["quick"]
    permuted       = arm_cfg["permuted"]
    max_new_tokens = arm_cfg["max_new_tokens"]
    is_thinking    = arm_cfg["model"] == "thinking"

    if is_thinking:
        gen_kwargs = dict(THINKING_GEN_KWARGS, max_new_tokens=max_new_tokens)
        if seed is not None:
            torch.manual_seed(seed)
    else:
        gen_kwargs = dict(do_sample=False, max_new_tokens=max_new_tokens)

    trials = []
    for qid, row in enumerate(ds):
        messages, correct_letter, build_status = build_messages(row, quick=quick, permuted=permuted)

        if messages is None:
            trials.append({
                "arm": arm_name, "seed": seed, "question_id": qid,
                "category": row["question_type"], "n_images": len(row["images_encoded"]),
                "n_input_tokens": 0, "n_think_tokens": 0, "n_answer_tokens": 0,
                "total_latency_ms": 0, "budget_hit": False, "think_closed": False,
                "predicted_letter": None, "correct_letter": correct_letter,
                "correct": False, "parse_status": build_status, "permuted": permuted,
            })
            continue

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text], images=image_inputs, videos=video_inputs,
            padding=True, return_tensors="pt",
        ).to(DEVICE)

        n_input_tokens = inputs["input_ids"].shape[1]

        t0 = time.time()
        with torch.no_grad():
            output_ids = model.generate(**inputs, **gen_kwargs)
        total_latency_ms = (time.time() - t0) * 1000

        generated   = output_ids[0][n_input_tokens:]
        full_output = processor.decode(generated, skip_special_tokens=True)
        budget_hit  = (len(generated) >= max_new_tokens)

        think_tokens = 0
        answer_text  = full_output
        think_closed = False

        if is_thinking:
            if "</think>" in full_output:
                think_closed = True
                think_part, answer_part = full_output.split("</think>", 1)
                think_content = re.sub(r'^<think>', '', think_part).strip()
                answer_text   = answer_part.strip()
                think_tokens  = len(processor.tokenizer.encode(think_content, add_special_tokens=False))
            else:
                think_closed = False
                answer_text  = full_output

        answer_tokens = len(processor.tokenizer.encode(answer_text, add_special_tokens=False))
        predicted_letter, parse_status = extract_letter(answer_text)
        if predicted_letter is None:
            predicted_letter, parse_status = extract_letter(full_output)

        correct = (predicted_letter == correct_letter) if predicted_letter else False

        trials.append({
            "arm": arm_name, "seed": seed, "question_id": qid,
            "category": row["question_type"], "n_images": len(row["images_encoded"]),
            "n_input_tokens": n_input_tokens,
            "n_think_tokens": think_tokens,
            "n_answer_tokens": answer_tokens,
            "total_latency_ms": round(total_latency_ms, 1),
            "budget_hit": budget_hit,
            "think_closed": think_closed,
            "predicted_letter": predicted_letter,
            "correct_letter": correct_letter,
            "correct": correct,
            "parse_status": parse_status,
            "permuted": permuted,
        })

        if qid % 100 == 99 or qid == 0:
            n_done = len(trials)
            n_correct = sum(t["correct"] for t in trials)
            print(f"[{arm_name} seed={seed}] q{qid+1}/400 acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%)", flush=True)

    n_correct = sum(t["correct"] for t in trials)
    print(f"[{arm_name} seed={seed}] DONE acc={n_correct}/400 ({100*n_correct/400:.1f}%)", flush=True)
    return trials


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", nargs="+", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Skip (arm, seed) pairs whose 400 trials are already in the JSONL")
    args = parser.parse_args()

    arm_names = args.arms or [a["name"] for a in ARMS]
    arm_cfgs  = [a for a in ARMS if a["name"] in arm_names]

    assert torch.cuda.is_available(), "CUDA not available"
    print(f"Device cuda:1 = {torch.cuda.get_device_name(1)}", flush=True)

    print("Loading ERQA ...", flush=True)
    ds = load_erqa()
    assert len(ds) == 400
    n_multi = sum(1 for r in ds if len(r['images_encoded']) > 1)
    print(f"  {len(ds)} questions, {n_multi} multi-image ({100*n_multi/400:.1f}%)", flush=True)
    for i, r in enumerate(ds):
        assert len(r['images_encoded']) >= 1
    print("  Image presence PASS", flush=True)

    # Load done (arm, seed) pairs
    done = set()
    if args.resume and JSONL_PATH.exists():
        existing = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
        from collections import Counter as C
        pair_counts = C((t["arm"], t.get("seed")) for t in existing)
        done = {pair for pair, cnt in pair_counts.items() if cnt >= 400}
        print(f"  Already done pairs: {sorted(done)}", flush=True)

    # Group by model
    for model_key, model_path in [("instruct", INSTRUCT_PATH), ("thinking", THINKING_PATH)]:
        batch = [a for a in arm_cfgs if a["model"] == model_key]
        if not batch:
            continue

        # Expand to (arm_cfg, seed) pairs, filtering done
        todo = []
        for a in batch:
            for seed in a["seeds"]:
                if (a["name"], seed) not in done:
                    todo.append((a, seed))
        if not todo:
            continue

        print(f"\nLoading {model_key} model ...", flush=True)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, device_map=DEVICE
        )
        model.eval()
        processor = AutoProcessor.from_pretrained(model_path)

        p = next(model.parameters())
        assert p.device.index == 1,       f"Expected cuda:1, got {p.device}"
        assert p.dtype == torch.bfloat16, f"Expected bfloat16, got {p.dtype}"
        print(f"  dtype={p.dtype} device={p.device} PASS", flush=True)

        for arm_cfg, seed in todo:
            print(f"\n=== ARM: {arm_cfg['name']}  seed={seed} ===", flush=True)
            trials = run_arm(arm_cfg, seed, ds, model, processor)
            with open(JSONL_PATH, "a") as f:
                for t in trials:
                    f.write(json.dumps(t) + "\n")

        del model
        torch.cuda.empty_cache()

    print(f"\nAll done. Trials in {JSONL_PATH}", flush=True)


if __name__ == "__main__":
    main()
