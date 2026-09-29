#!/usr/bin/env python3
"""Study J: Reasoning gate on SiGNgapore2D sign recognition.

PRE-REGISTERED DECISION RULE (EXPERIMENTS.md):
  premise HOLDS only if THINKING > INSTRUCT under paired test at α=0.05 overall.
  If THINKING ≤ INSTRUCT, on-device thinking is NOT supported on this workload.

Arms:
  INSTRUCT       greedy, max_new_tokens=512, 1 run
  THINKING       sampled, max_new_tokens=2048, 3 seeds (42, 123, 456)
  THINKING-QUICK sampled, max_new_tokens=2048, 3 seeds (with "answer quickly" suffix)

TOKEN BUDGET (pre-registered, 2026-09-29): max_new_tokens=16384 produced ~370s/sign
  on A6000 (~84h total), unmeasurable. 2048 (~45s/sign) is the deployability threshold.
  Signs hitting the budget are truncated and score as failures. The gate tests thinking
  under a deployable budget, not unlimited compute. Truncation rate is a primary result.

PARSE FIX (bug, 2026-09-29): initial run used skip_special_tokens=True which strips
  <think> but not </think>; corrected to split on </think> (same as Study K).

Dataset: HF NickyZimmerman/SiGNgapore2D (167 images, 205 recognition-labeled signs,
  43 excluded → 162 evaluated). GT crops from boundingBox (cx, cy, w, h format).
Scorer: /tmp/sign-understanding/recognition_fp_metrics_eval.py with
  open_clip ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip.
"""

import os, sys, json, ast, re, time, argparse
import torch
from pathlib import Path
from PIL import Image
from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

INSTRUCT_PATH = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
THINKING_PATH  = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
DEVICE         = "cuda:1"

HF_REPO        = "NickyZimmerman/SiGNgapore2D"
GT_PATH        = "/tmp/sign-understanding/gt/gt_annotation.json"
EXCLUDE_PATH   = "/tmp/sign-understanding/gt/recognition-exclude-imgs.txt"
PROMPT_PATH    = "/tmp/sign-understanding/prompts/prompt.txt"
SYMBOLS_PATH   = "/tmp/sign-understanding/prompts/symbols.txt"

THINKING_SEEDS = [42, 123, 456]

ARMS = [
    {"name": "INSTRUCT",       "model": "instruct", "max_new_tokens": 512,  "quick": False, "seeds": [None]},
    {"name": "THINKING",       "model": "thinking", "max_new_tokens": 2048, "quick": False, "seeds": THINKING_SEEDS},
    {"name": "THINKING-QUICK", "model": "thinking", "max_new_tokens": 2048, "quick": True,  "seeds": THINKING_SEEDS},
]

QUICK_SUFFIX = " Answer quickly without overthinking."

THINKING_GEN_KWARGS = dict(
    do_sample=True,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    min_p=0.0,
)

DIRECTIONS = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']

OUT_DIR    = Path("results/signs/study_j")
JSONL_PATH = OUT_DIR / "study_j_trials.jsonl"


def load_gt():
    with open(GT_PATH) as f:
        return json.load(f)

def load_exclude():
    with open(EXCLUDE_PATH) as f:
        return set(l.strip() for l in f if l.strip())

def load_prompt():
    with open(PROMPT_PATH) as f:
        text = f.read()
    with open(SYMBOLS_PATH) as f:
        symbols = [l.strip() for l in f if l.strip()]
    text = text.replace("GT_SYMBOL_LIST", ", ".join(symbols))
    text = text.replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS))
    return text

def crop_bbox(img, bbox):
    """bbox = [cx, cy, w, h] → PIL Image crop."""
    cx, cy, w, h = bbox
    x1 = max(0, int(cx - w / 2))
    y1 = max(0, int(cy - h / 2))
    x2 = min(img.width,  int(cx + w / 2))
    y2 = min(img.height, int(cy + h / 2))
    return img.crop((x1, y1, x2, y2))

def build_sign_list(gt, exclude):
    signs = []
    for entry in gt:
        img_path = entry["imagePath"]
        stem = img_path[:-4]
        for i, ann in enumerate(entry["annotation"]):
            mx = ann.get("mixed", {})
            tl = ann.get("text labels", {})
            sl = ann.get("symbol labels", {})
            if tl == {} and sl == {} and (mx == {} or mx is None):
                continue
            crop_name = f"{stem}_{i}.jpg"
            if crop_name in exclude:
                continue
            signs.append({
                "imagePath": img_path,
                "objectID": i,
                "bbox": ann["boundingBox"],
                "text_labels": tl,
                "symbol_labels": sl,
                "mixed": mx if mx else {},
                "crop_name": crop_name,
            })
    return signs

def download_hf_image(img_path, hf_cache):
    if img_path in hf_cache:
        return hf_cache[img_path]
    local = hf_hub_download(
        repo_id=HF_REPO,
        filename=f"images/{img_path}",
        repo_type="dataset",
    )
    img = Image.open(local).convert("RGB")
    hf_cache[img_path] = img
    return img

def load_done(jsonl_path):
    done = set()
    if not jsonl_path.exists():
        return done
    with open(jsonl_path) as f:
        for line in f:
            try:
                t = json.loads(line)
                done.add((t["arm"], t["seed"], t["crop_name"]))
            except Exception:
                pass
    return done

def extract_think_and_answer(full_output, is_thinking, processor):
    """
    Parse think tokens and answer from model output.
    skip_special_tokens=True strips <think> but keeps </think>.
    So full_output = "[thinking content]</think>[answer]"  (if closed)
    or "[thinking content]"                                (if truncated).

    Returns (think_content, answer_text, n_think_tokens, think_closed).
    """
    if is_thinking and "</think>" in full_output:
        think_part, answer_part = full_output.split("</think>", 1)
        think_content = think_part.strip()
        answer_text   = answer_part.strip()
        think_closed  = True
    elif is_thinking:
        think_content = full_output.strip()
        answer_text   = ""
        think_closed  = False
    else:
        think_content = ""
        answer_text   = full_output.strip()
        think_closed  = True

    n_think = len(processor.tokenizer.encode(think_content, add_special_tokens=False)) if think_content else 0
    return think_content, answer_text, n_think, think_closed

def parse_prediction(answer_text):
    """Parse the model's JSON dict response → {"T": {...}, "S": {...}}."""
    text = re.sub(r"```(?:json)?", "", answer_text).strip().strip("`").strip()
    for parser in (ast.literal_eval, json.loads):
        try:
            d = parser(text)
            if isinstance(d, dict):
                T = d.get("T", d.get("t", {})) or {}
                S = d.get("S", d.get("s", {})) or {}
                return {"T": T, "S": S}, "ok"
        except Exception:
            pass
    return None, "parse_failed"

def run_arm(arm_cfg, seed, signs, model, processor, prompt_text, hf_cache, jsonl_path, done):
    arm_name       = arm_cfg["name"]
    quick          = arm_cfg["quick"]
    max_new_tokens = arm_cfg["max_new_tokens"]
    is_thinking    = arm_cfg["model"] == "thinking"

    if is_thinking and seed is not None:
        torch.manual_seed(seed)
        gen_kwargs = dict(THINKING_GEN_KWARGS, max_new_tokens=max_new_tokens)
    else:
        gen_kwargs = dict(do_sample=False, max_new_tokens=max_new_tokens)

    user_prompt = prompt_text + (QUICK_SUFFIX if quick else "")
    n_total = len(signs)

    with open(jsonl_path, "a") as fout:
        for idx, sign in enumerate(signs):
            crop_name = sign["crop_name"]
            key = (arm_name, seed, crop_name)
            if key in done:
                continue

            try:
                full_img = download_hf_image(sign["imagePath"], hf_cache)
                crop_img = crop_bbox(full_img, sign["bbox"])
            except Exception as e:
                trial = {
                    "arm": arm_name, "seed": seed, "crop_name": crop_name,
                    "imagePath": sign["imagePath"], "objectID": sign["objectID"],
                    "n_input_tokens": 0, "n_think_tokens": 0, "n_answer_tokens": 0,
                    "total_latency_ms": 0, "truncated": False, "think_closed": False,
                    "prediction": None, "parse_status": f"image_error: {e}",
                }
                fout.write(json.dumps(trial) + "\n")
                fout.flush()
                done.add(key)
                continue

            messages = [{"role": "user", "content": [
                {"type": "image", "image": crop_img},
                {"type": "text",  "text": user_prompt},
            ]}]

            text_input = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text_input], images=image_inputs, videos=video_inputs,
                padding=True, return_tensors="pt",
            ).to(DEVICE)

            n_input = inputs["input_ids"].shape[1]

            t0 = time.time()
            with torch.no_grad():
                output_ids = model.generate(**inputs, **gen_kwargs)
            latency_ms = (time.time() - t0) * 1000

            generated   = output_ids[0][n_input:]
            full_output = processor.decode(generated, skip_special_tokens=True)
            truncated   = (len(generated) >= max_new_tokens)

            think_content, answer_text, n_think, think_closed = extract_think_and_answer(
                full_output, is_thinking, processor
            )
            n_answer = len(processor.tokenizer.encode(answer_text, add_special_tokens=False)) if answer_text else 0

            pred, parse_status = parse_prediction(answer_text)

            trial = {
                "arm": arm_name,
                "seed": seed,
                "crop_name": crop_name,
                "imagePath": sign["imagePath"],
                "objectID": sign["objectID"],
                "n_input_tokens": n_input,
                "n_think_tokens": n_think,
                "n_answer_tokens": n_answer,
                "total_latency_ms": round(latency_ms, 1),
                "truncated": truncated,
                "think_closed": think_closed,
                "prediction": pred,
                "parse_status": parse_status,
                "answer_text": answer_text[:300],
            }
            fout.write(json.dumps(trial) + "\n")
            fout.flush()
            done.add(key)

            n_done_arm_seed = sum(1 for k in done if k[0] == arm_name and k[1] == seed)
            if n_done_arm_seed % 20 == 0 or n_done_arm_seed == n_total:
                trunc_str = " TRUNCATED" if truncated else ""
                print(
                    f"  [{arm_name} s={seed}] {n_done_arm_seed}/{n_total}"
                    f"  lat={latency_ms/1000:.1f}s  think={n_think}tok  parse={parse_status}{trunc_str}",
                    flush=True,
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", nargs="*", default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gt      = load_gt()
    exclude = load_exclude()
    prompt  = load_prompt()
    signs   = build_sign_list(gt, exclude)
    print(f"Signs to evaluate: {len(signs)} (after exclusion)")

    done = load_done(JSONL_PATH)
    print(f"Already done: {len(done)} trials")

    arms_to_run = ARMS
    if args.arms:
        arms_to_run = [a for a in ARMS if a["name"] in args.arms]

    # Project total remaining
    total_thinking_remaining = sum(
        sum(1 for s in signs if (a["name"], seed, s["crop_name"]) not in done)
        for a in ARMS if a["model"] == "thinking"
        for seed in a["seeds"]
    )
    if total_thinking_remaining > 0:
        est_hours = total_thinking_remaining * 45 / 3600
        print(f"Projected remaining THINKING trials: {total_thinking_remaining} × ~45s = ~{est_hours:.1f}h")

    hf_cache = {}
    current_model_type = None
    model = processor = None

    for arm_cfg in arms_to_run:
        arm_name   = arm_cfg["name"]
        model_type = arm_cfg["model"]

        all_done = all(
            (arm_name, seed, s["crop_name"]) in done
            for seed in arm_cfg["seeds"]
            for s in signs
        )
        if all_done:
            print(f"[{arm_name}] all done — skipping")
            continue

        if model_type != current_model_type:
            del model
            model = None
            torch.cuda.empty_cache()
            model_path = INSTRUCT_PATH if model_type == "instruct" else THINKING_PATH
            print(f"Loading {model_type} model ...", flush=True)
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                model_path, torch_dtype=torch.bfloat16, device_map=DEVICE
            )
            model.eval()
            processor = AutoProcessor.from_pretrained(model_path)
            current_model_type = model_type

        for seed in arm_cfg["seeds"]:
            n_remaining = sum(
                1 for s in signs
                if (arm_name, seed, s["crop_name"]) not in done
            )
            if n_remaining == 0:
                print(f"[{arm_name} seed={seed}] already complete — skipping")
                continue
            print(f"\n=== {arm_name}  seed={seed}  remaining={n_remaining} ===", flush=True)
            run_arm(arm_cfg, seed, signs, model, processor, prompt, hf_cache, JSONL_PATH, done)

    print(f"\nDone. Trials in {JSONL_PATH}")


if __name__ == "__main__":
    main()
