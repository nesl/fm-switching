#!/usr/bin/env python3
"""Study R: Device-tier vs Cloud-tier on ERQA — 2×2 factorial (size × thinking mode).

Arms:
  A: 4B-Instruct  greedy             — REUSE StudyQ arm E (answer_text=None in reused trials)
  B: 4B-Thinking  seed=42, temp=0.6  — REUSE StudyQ arm A
     NOTE DECODING ASYMMETRY: reused arm ran at temp=0.6; this study specifies temp=1.0.
     Known asymmetry; stated explicitly.
  C: 32B-Instruct greedy             — new, BnB NF4
  D: 32B-Thinking seed=42, temp=1.0  — new, BnB NF4 (CLOUD TIER)

Quantization: BitsAndBytes NF4 (no official Qwen AWQ for 32B Thinking; BnB NF4 gives
equivalent ~17GB footprint and is safe at any token budget).

Pre-registered rule:
  CLOUD TIER JUSTIFIED if D > A by >5pp with non-overlapping CIs.
"""

import os, sys, json, re, time, math, random, argparse
import torch
import torch.nn as nn
from pathlib import Path

# PyTorch 2.4+cu118 is missing set_submodule; add it so BnB 4-bit loading works.
if not hasattr(nn.Module, 'set_submodule'):
    def _set_submodule(self, target: str, module: nn.Module) -> None:
        parts = target.split('.')
        parent = self
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], module)
    nn.Module.set_submodule = _set_submodule
from collections import defaultdict
from datasets import load_dataset
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, BitsAndBytesConfig
from qwen_vl_utils import process_vision_info
import transformers

PATH_4BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
PATH_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
PATH_32BI_HUB = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/0cfaf48183f594c314753d30a4c4974bc75f3ccb"
PATH_32BT_HUB = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-32B-Thinking/snapshots/7edd10ffd1196091948fb245ff63e406ccb2d4d1"
HF_CACHE = "/mnt/ssd/hf_models"

STUDY_Q_JSONL = Path("results/erqa/study_q/study_q_trials.jsonl")
OUT_DIR = Path("results/erqa/study_r")
JSONL_PATH = OUT_DIR / "study_r_trials.jsonl"

MAX_NEW_TOKENS_THINKING = 16384
MAX_NEW_TOKENS_INSTRUCT = 512
THINKING_GEN = dict(do_sample=True, temperature=1.0, top_p=0.95, top_k=20,
                    max_new_tokens=MAX_NEW_TOKENS_THINKING)
INSTRUCT_GEN = dict(do_sample=False, max_new_tokens=MAX_NEW_TOKENS_INSTRUCT)

PROJECT_N = 5
HARD_STOP_H = 20.0
SUBSET_N = 150


# ---------------------------------------------------------------------------
# Transformers version check
# ---------------------------------------------------------------------------

def check_transformers_version():
    v = transformers.__version__
    print(f"transformers version: {v}", flush=True)
    major, minor, *_ = v.split(".")
    if int(major) >= 5 and int(minor) >= 17:
        print(f"WARNING: transformers {v} is in the looping-issue range (>=5.17.0). "
              f"Consider downgrading to 5.7.x if budget_hit rate exceeds 10%.", flush=True)
    else:
        print(f"  Looping issue (5.17.x): NOT AFFECTED", flush=True)
    return v


# ---------------------------------------------------------------------------
# Data helpers (mirrors study_q_erqa.py)
# ---------------------------------------------------------------------------

def load_erqa():
    import PIL.Image
    if not hasattr(PIL.Image, 'ExifTags'):
        class _Base:
            Orientation = 274
        class _FakeExifTags:
            Base = _Base()
        PIL.Image.ExifTags = _FakeExifTags()
    ds = load_dataset("RunsenXu/ERQA", verification_mode="no_checks")["test"]
    assert len(ds) == 400
    return ds


def compute_stratified_subset(ds, n=SUBSET_N, seed=42):
    rng = random.Random(seed)
    by_cat = defaultdict(list)
    for i, row in enumerate(ds):
        by_cat[row['question_type']].append(i)
    subset = []
    total = len(ds)
    for cat, idxs in sorted(by_cat.items()):
        n_cat = max(1, round(n * len(idxs) / total))
        chosen = rng.sample(idxs, min(n_cat, len(idxs)))
        subset.extend(chosen)
    subset = sorted(set(subset))
    while len(subset) > n:
        subset.pop()
    remaining = [i for i in range(total) if i not in set(subset)]
    rng.shuffle(remaining)
    while len(subset) < n:
        subset.append(remaining.pop())
    return sorted(subset)


def build_messages(row):
    q_text = row['question']
    images = row['images_encoded']
    correct = row['answer']
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
    return [{"role": "user", "content": content}], correct


def extract_letter(text):
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
# Model loading
# ---------------------------------------------------------------------------

def measure_vram():
    used = {}
    for i in range(torch.cuda.device_count()):
        used[i] = torch.cuda.memory_allocated(i) / 1e9
    return used


def load_model_bnb4(hub_name_or_path, label, use_cache=True):
    """Load model with BitsAndBytes NF4 quantization, device_map='auto'."""
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    vram_before = measure_vram()
    print(f"\nLoading {label} with BnB NF4 ...", flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        hub_name_or_path,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(hub_name_or_path)
    vram_after = measure_vram()
    vram_used = {k: round(vram_after[k] - vram_before.get(k, 0), 2) for k in vram_after}
    total_vram = sum(vram_used.values())
    print(f"  VRAM used: {vram_used} = {total_vram:.1f}GB total", flush=True)
    print(f"  device_map: {model.hf_device_map if hasattr(model, 'hf_device_map') else 'N/A'}", flush=True)
    return model, processor, vram_used


def load_model_bf16(path, label):
    """Load a small model in bf16 on cuda:1."""
    print(f"\nLoading {label} (bf16, cuda:1) ...", flush=True)
    vram_before = measure_vram()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, device_map="cuda:1")
    model.eval()
    processor = AutoProcessor.from_pretrained(path)
    vram_after = measure_vram()
    vram_used = {k: round(vram_after[k] - vram_before.get(k, 0), 2) for k in vram_after}
    total_vram = sum(vram_used.values())
    print(f"  VRAM used: {vram_used} = {total_vram:.1f}GB total", flush=True)
    return model, processor, vram_used


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def infer_one(model, processor, messages, gen_kwargs, max_new_tokens, is_thinking):
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)

    # For device_map="auto" models, inputs go to first device
    first_device = next(iter(set(v for v in model.hf_device_map.values()
                                  if isinstance(v, (int, str))))) \
        if hasattr(model, 'hf_device_map') else "cuda:1"
    # Simplest: let processor handle placement via model's device
    inputs = processor(
        text=[text], images=image_inputs, videos=video_inputs,
        padding=True, return_tensors="pt",
    )
    # Move to the first device of the model
    if hasattr(model, 'hf_device_map'):
        # Find the embedding device
        embed_device = model.hf_device_map.get('model.embed_tokens', 'cuda:0')
        inputs = inputs.to(embed_device)
    else:
        inputs = inputs.to("cuda:1")

    n_input = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)
    lat_ms = (time.time() - t0) * 1000

    generated = output_ids[0][n_input:]
    full_output = processor.decode(generated, skip_special_tokens=True)
    budget_hit = (len(generated) >= max_new_tokens)

    n_think = 0
    think_closed = None

    if is_thinking:
        think_closed = False
        if "</think>" in full_output:
            think_closed = True
            think_part, answer_part = full_output.split("</think>", 1)
            think_content = re.sub(r'^<think>', '', think_part).strip()
            answer_text = answer_part.strip()
            n_think = len(processor.tokenizer.encode(think_content, add_special_tokens=False))
        else:
            answer_text = full_output
    else:
        answer_text = full_output.strip()

    n_answer = len(processor.tokenizer.encode(answer_text, add_special_tokens=False)) if answer_text else 0
    return answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed


def make_trial(arm, qid, row, correct_letter, seed, n_input, n_think, n_answer,
               lat_ms, budget_hit, think_closed, predicted_letter, parse_status, answer_text):
    correct = (predicted_letter == correct_letter) if predicted_letter else False
    return {
        "arm": arm,
        "question_id": qid,
        "category": row["question_type"],
        "n_images": len(row["images_encoded"]),
        "n_input_tokens": n_input,
        "n_think_tokens": n_think,
        "n_answer_tokens": n_answer,
        "total_latency_ms": round(lat_ms, 1),
        "budget_hit": budget_hit,
        "think_closed": think_closed,
        "predicted_letter": predicted_letter,
        "correct_letter": correct_letter,
        "correct": correct,
        "parse_status": parse_status,
        "answer_text": answer_text,
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# Arm runners
# ---------------------------------------------------------------------------

def run_thinking_arm(arm_name, seed, questions, ds, model, processor,
                     out_f, done_qids, hard_stop_h=None):
    torch.manual_seed(seed)
    gen_kwargs = dict(THINKING_GEN, max_new_tokens=MAX_NEW_TOKENS_THINKING)
    trials = []
    lat_history = []

    for i, qid in enumerate(questions):
        if qid in done_qids:
            continue
        row = ds[qid]
        messages, correct_letter = build_messages(row)
        answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed = infer_one(
            model, processor, messages, gen_kwargs, MAX_NEW_TOKENS_THINKING, is_thinking=True)
        predicted_letter, parse_status = extract_letter(answer_text)
        t = make_trial(arm_name, qid, row, correct_letter, seed, n_input, n_think, n_answer,
                       lat_ms, budget_hit, think_closed, predicted_letter, parse_status, answer_text)
        trials.append(t)
        out_f.write(json.dumps(t) + "\n")
        out_f.flush()
        lat_history.append(lat_ms)

        n_done = len(trials)
        n_correct = sum(x["correct"] for x in trials)
        if n_done % 50 == 1 or n_done == len(questions):
            term = sum(1 for x in trials if x["think_closed"])
            bh = sum(1 for x in trials if x["budget_hit"])
            print(f"[{arm_name} seed={seed}] q{n_done}/{len(questions)} "
                  f"acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%) "
                  f"term={term} bh={bh} last_lat={lat_ms/1000:.1f}s", flush=True)

        if len(lat_history) == PROJECT_N:
            mean_ms = sum(lat_history) / PROJECT_N
            proj_h = (mean_ms * len(questions)) / 3_600_000
            remain_h = (mean_ms * (len(questions) - n_done)) / 3_600_000
            print(f"\n=== RUNTIME PROJECTION: {arm_name} (after {PROJECT_N} trials) ===")
            print(f"  Mean lat: {mean_ms/1000:.1f}s  n_q: {len(questions)}")
            print(f"  Projected total: {proj_h:.1f}h  Remaining: {remain_h:.1f}h")
            if hard_stop_h is not None and proj_h > hard_stop_h:
                print(f"  WARNING: projected {proj_h:.1f}h > {hard_stop_h}h — "
                      f"caller should reduce to {SUBSET_N}-Q subset")
            print()

    n_correct = sum(x["correct"] for x in trials)
    term = sum(1 for x in trials if x["think_closed"])
    bh = sum(1 for x in trials if x["budget_hit"])
    print(f"[{arm_name} seed={seed}] DONE acc={n_correct}/{len(trials)} "
          f"({100*n_correct/max(1,len(trials)):.1f}%) term={term} bh={bh}", flush=True)
    return trials


def run_instruct_arm(arm_name, questions, ds, model, processor, out_f, done_qids):
    gen_kwargs = dict(INSTRUCT_GEN)
    trials = []
    lat_history = []

    for i, qid in enumerate(questions):
        if qid in done_qids:
            continue
        row = ds[qid]
        messages, correct_letter = build_messages(row)
        answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed = infer_one(
            model, processor, messages, gen_kwargs, MAX_NEW_TOKENS_INSTRUCT, is_thinking=False)
        predicted_letter, parse_status = extract_letter(answer_text)
        t = make_trial(arm_name, qid, row, correct_letter, None, n_input, 0, n_answer,
                       lat_ms, budget_hit, None, predicted_letter, parse_status, answer_text)
        trials.append(t)
        out_f.write(json.dumps(t) + "\n")
        out_f.flush()
        lat_history.append(lat_ms)

        n_done = len(trials)
        n_correct = sum(x["correct"] for x in trials)
        if n_done % 100 == 1 or n_done == len(questions):
            print(f"[{arm_name}] q{n_done}/{len(questions)} "
                  f"acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%)", flush=True)

        if len(lat_history) == PROJECT_N:
            mean_ms = sum(lat_history) / PROJECT_N
            proj_h = (mean_ms * len(questions)) / 3_600_000
            print(f"\n=== RUNTIME PROJECTION: {arm_name} (after {PROJECT_N} trials) ===")
            print(f"  Mean lat: {mean_ms/1000:.1f}s  Projected total: {proj_h:.1f}h\n")

    n_correct = sum(x["correct"] for x in trials)
    print(f"[{arm_name}] DONE acc={n_correct}/{len(trials)} "
          f"({100*n_correct/max(1,len(trials)):.1f}%)", flush=True)
    return trials


# ---------------------------------------------------------------------------
# Resume / done tracking
# ---------------------------------------------------------------------------

def load_done(jsonl_path):
    done = defaultdict(set)
    if not jsonl_path.exists():
        return done
    for line in open(jsonl_path):
        if not line.strip():
            continue
        t = json.loads(line)
        done[t["arm"]].add(t["question_id"])
    return done


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--arms", nargs="+", default=["A", "B", "C", "D"])
    args = parser.parse_args()

    assert torch.cuda.is_available(), "CUDA not available"
    n_gpus = torch.cuda.device_count()
    print(f"GPUs available: {n_gpus}", flush=True)
    for i in range(n_gpus):
        props = torch.cuda.get_device_properties(i)
        print(f"  cuda:{i} = {props.name}  {props.total_memory/1e9:.1f}GB", flush=True)

    tv = check_transformers_version()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading ERQA ...", flush=True)
    ds = load_erqa()
    n_multi = sum(1 for r in ds if len(r['images_encoded']) > 1)
    print(f"  {len(ds)} questions, {n_multi} multi-image ({100*n_multi/400:.1f}%)", flush=True)

    subset_qids = compute_stratified_subset(ds, n=SUBSET_N)
    questions = list(range(400))
    reduced = False

    done = load_done(JSONL_PATH)
    if args.resume:
        print(f"  Resume: done = {dict((k, len(v)) for k, v in done.items())}", flush=True)

    out_f = open(JSONL_PATH, "a")
    arms_to_run = args.arms

    # ---- ARM A: reuse StudyQ arm E ----
    if "A" in arms_to_run:
        if len(done["A"]) < 400 or not args.resume:
            print("\n=== ARM A: REUSE StudyQ arm E (4B-Instruct greedy) ===", flush=True)
            assert STUDY_Q_JSONL.exists(), f"StudyQ JSONL not found: {STUDY_Q_JSONL}"
            q_trials = [json.loads(l) for l in open(STUDY_Q_JSONL) if l.strip()]
            e_trials = [t for t in q_trials if t["arm"] == "E"]
            assert len(e_trials) == 400
            n_written = 0
            for t in e_trials:
                qid = t["question_id"]
                if args.resume and qid in done["A"]:
                    continue
                a_trial = {
                    "arm": "A",
                    "question_id": qid,
                    "category": t["category"],
                    "n_images": t["n_images"],
                    "n_input_tokens": t["n_input_tokens"],
                    "n_think_tokens": 0,
                    "n_answer_tokens": t["n_answer_tokens"],
                    "total_latency_ms": t["total_latency_ms"],
                    "budget_hit": t["budget_hit"],
                    "think_closed": None,
                    "predicted_letter": t["predicted_letter"],
                    "correct_letter": t["correct_letter"],
                    "correct": t["correct"],
                    "parse_status": t["parse_status"],
                    "answer_text": None,
                    "seed": None,
                    "_reused_from": "study_q_arm_E",
                    "_reused_decoding": "greedy max_new_tokens=512",
                }
                out_f.write(json.dumps(a_trial) + "\n")
                n_written += 1
            out_f.flush()
            n_correct = sum(1 for t in e_trials if t["correct"])
            print(f"[A] {n_written} trials written. acc={n_correct}/400 ({100*n_correct/400:.1f}%) [StudyQ]", flush=True)
        else:
            print(f"[A] Already done — skip", flush=True)

    # ---- ARM B: reuse StudyQ arm A ----
    if "B" in arms_to_run:
        if len(done["B"]) < 400 or not args.resume:
            print("\n=== ARM B: REUSE StudyQ arm A (4B-Thinking seed=42) ===", flush=True)
            print("  DECODING ASYMMETRY: reused arm ran at temp=0.6; this study specifies temp=1.0.", flush=True)
            assert STUDY_Q_JSONL.exists()
            q_trials = [json.loads(l) for l in open(STUDY_Q_JSONL) if l.strip()]
            a_trials = [t for t in q_trials if t["arm"] == "A"]
            assert len(a_trials) == 400
            n_written = 0
            for t in a_trials:
                qid = t["question_id"]
                if args.resume and qid in done["B"]:
                    continue
                b_trial = {
                    "arm": "B",
                    "question_id": qid,
                    "category": t["category"],
                    "n_images": t["n_images"],
                    "n_input_tokens": t["n_input_tokens"],
                    "n_think_tokens": t["n_think_tokens"],
                    "n_answer_tokens": t["n_answer_tokens"],
                    "total_latency_ms": t["total_latency_ms"],
                    "budget_hit": t["budget_hit"],
                    "think_closed": t["think_closed"],
                    "predicted_letter": t["predicted_letter"],
                    "correct_letter": t["correct_letter"],
                    "correct": t["correct"],
                    "parse_status": t["parse_status"],
                    "answer_text": t.get("answer_text"),
                    "seed": 42,
                    "_reused_from": "study_q_arm_A",
                    "_reused_decoding": "temp=0.6 top_p=0.95 top_k=20 min_p=0 max_new_tokens=8192 (ASYMMETRY: study_r spec=temp=1.0 max_new_tokens=16384)",
                }
                out_f.write(json.dumps(b_trial) + "\n")
                n_written += 1
            out_f.flush()
            n_correct = sum(1 for t in a_trials if t["correct"])
            tc = sum(1 for t in a_trials if t.get("think_closed"))
            bh = sum(1 for t in a_trials if t.get("budget_hit"))
            print(f"[B] {n_written} trials written. acc={n_correct}/400 ({100*n_correct/400:.1f}%) "
                  f"think_closed={tc} budget_hit={bh} [StudyQ]", flush=True)
        else:
            print(f"[B] Already done — skip", flush=True)

    # ---- ARM C: 32B-Instruct BnB NF4 ----
    if "C" in arms_to_run:
        c_done = done["C"]
        c_todo = [q for q in questions if q not in c_done] if args.resume else questions
        if c_todo:
            print("\n=== ARM C: 32B-Instruct BnB NF4 greedy ===", flush=True)
            model, processor, vram_c = load_model_bnb4(PATH_32BI_HUB, "32B-Instruct BnB NF4")
            run_instruct_arm("C", c_todo, ds, model, processor, out_f,
                             c_done if args.resume else set())
            del model; torch.cuda.empty_cache()
        else:
            print(f"[C] Already done — skip", flush=True)

    # ---- ARM D: 32B-Thinking BnB NF4 ----
    if "D" in arms_to_run:
        d_done = done["D"]
        d_todo = [q for q in questions if q not in d_done] if args.resume else questions
        if d_todo:
            print("\n=== ARM D: 32B-Thinking BnB NF4 seed=42 temp=1.0 max_new_tokens=16384 ===", flush=True)
            model, processor, vram_d = load_model_bnb4(PATH_32BT_HUB, "32B-Thinking BnB NF4")

            # Check if we need to reduce to subset (projection after PROJECT_N trials)
            # If projection > HARD_STOP_H, switch to subset_qids
            d_todo_active = d_todo
            run_thinking_arm("D", 42, d_todo_active, ds, model, processor, out_f,
                             d_done if args.resume else set(),
                             hard_stop_h=HARD_STOP_H)
            del model; torch.cuda.empty_cache()
        else:
            print(f"[D] Already done — skip", flush=True)

    out_f.close()

    # Final summary
    print("\n=== STUDY R COMPLETE ===", flush=True)
    print(f"transformers version: {tv}", flush=True)
    all_trials = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
    print(f"\nTotal trials: {len(all_trials)}")
    for arm in ["A", "B", "C", "D"]:
        ts = [t for t in all_trials if t["arm"] == arm]
        if not ts:
            continue
        n = len(ts)
        correct = sum(1 for t in ts if t["correct"])
        bh = sum(1 for t in ts if t.get("budget_hit"))
        tc_val = ts[0].get("think_closed")
        is_instruct = tc_val is None
        if is_instruct:
            term = sum(1 for t in ts if not t.get("budget_hit"))
            term_label = "EOS-term"
        else:
            term = sum(1 for t in ts if t.get("think_closed"))
            term_label = "think_closed"
        lats = [t["total_latency_ms"] for t in ts]
        mean_lat = sum(lats) / len(lats) / 1000
        total_h = sum(lats) / 3_600_000
        print(f"  arm={arm}: n={n} correct={correct} ({100*correct/n:.1f}%) "
              f"{term_label}={term} bh={bh} mean_lat={mean_lat:.1f}s total_h={total_h:.2f}h")

    print("\nGIT RULE: Stop. Ask user to commit.", flush=True)


if __name__ == "__main__":
    main()
