#!/usr/bin/env python3
"""Study Q: Retry vs Scale on ERQA.

Arms (run order: E → D → A → B → C):
  E: 4B-Instruct×1 greedy max_new_tokens=512  — REUSE StudyK INSTRUCT arm
     NOTE: answer_text not stored in StudyK reused trials.
  D: 8B-Instruct×1 greedy max_new_tokens=512  — new; instruct_mode (no think tags)
  A: 4B-Thinking×1 seed=42 max_new_tokens=8192 — RE-RUN (StudyK used 16384; NOT REUSABLE)
  B: 4B-Thinking up to 5 passes, retry budget_hit only, reuse A as pass 1
  C: 8B-Thinking×1 seed=42 max_new_tokens=8192 — new

Pre-registered rule:
  BOUNDED PATH SUFFICES if 8B-I within 3pp of best reasoning arm with overlapping CIs.
  REASONING WINS if any reasoning arm exceeds 8B-I by >3pp with non-overlapping CIs.
"""

import os, sys, json, re, time, argparse, random
import torch
from pathlib import Path
from collections import defaultdict
from datasets import load_dataset
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

PATH_4BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
PATH_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
PATH_8BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"
PATH_8BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
DEVICE = "cuda:1"

STUDY_K_JSONL = Path("results/erqa/study_k/study_k_trials.jsonl")
OUT_DIR = Path("results/erqa/study_q")
JSONL_PATH = OUT_DIR / "study_q_trials.jsonl"

THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
MAX_NEW_TOKENS_THINKING = 8192
MAX_NEW_TOKENS_INSTRUCT = 512
RETRY_SEEDS = [123, 456, 789, 1011]
PROJECT_N = 5
HARD_STOP_H = 12.0
SUBSET_N = 150


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_erqa():
    # Pillow 9.2.0 compatibility: datasets image decoder uses PIL.Image.ExifTags.Base.Orientation
    # which was added in Pillow 9.3.0. Patch the missing attribute.
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
    """Return sorted list of n question indices, stratified by question_type."""
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
    # Trim or fill to exactly n
    while len(subset) > n:
        subset.pop()
    remaining = [i for i in range(total) if i not in set(subset)]
    rng.shuffle(remaining)
    while len(subset) < n:
        subset.append(remaining.pop())
    return sorted(subset)


def random_baseline(ds):
    """Return mean(1/n_options) across all 400 questions."""
    counts = []
    for row in ds:
        q = row['question']
        m = re.search(r'Choices:\s+(.*?)(?:\s+Please\s+answer|\s*$)', q, re.DOTALL)
        if not m:
            counts.append(4)
            continue
        parts = re.split(r'\b([A-D])\.\s+', m.group(1))
        n_opts = sum(1 for i in range(1, len(parts), 2) if i + 1 < len(parts))
        counts.append(n_opts if n_opts in (2, 3, 4) else 4)
    baseline = sum(1.0 / c for c in counts) / len(counts)
    print(f"Random baseline: {baseline*100:.2f}% (mean 1/n_options over 400 questions)")
    print(f"  Option counts: {sorted(set(counts))}, "
          f"distribution: {dict(sorted((c, counts.count(c)) for c in set(counts)))}")
    return baseline


def build_messages(row):
    """Return (messages, correct_letter)."""
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


# ---------------------------------------------------------------------------
# Answer parsing
# ---------------------------------------------------------------------------

def extract_letter(text):
    """Return (letter_or_None, parse_status). Mirrors StudyK."""
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
# Trial construction helpers
# ---------------------------------------------------------------------------

def make_trial(arm, qid, row, correct_letter, pass_index, seed,
               n_input, n_think, n_answer, lat_ms,
               budget_hit, think_closed, predicted_letter, parse_status, answer_text):
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
        "pass_index": pass_index,
        "seed": seed,
    }


def infer_one(model, processor, messages, gen_kwargs, max_new_tokens, is_thinking):
    """Run one inference. Returns (answer_text, n_input, n_think, n_answer, lat_ms,
                                   budget_hit, think_closed)."""
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text], images=image_inputs, videos=video_inputs,
        padding=True, return_tensors="pt",
    ).to(DEVICE)
    n_input = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)
    lat_ms = (time.time() - t0) * 1000

    generated = output_ids[0][n_input:]
    full_output = processor.decode(generated, skip_special_tokens=True)
    budget_hit = (len(generated) >= max_new_tokens)

    n_think = 0
    think_closed = None  # None means instruct mode (N/A)

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
        # Instruct mode: full output is the answer
        answer_text = full_output.strip()

    n_answer = len(processor.tokenizer.encode(answer_text, add_special_tokens=False)) if answer_text else 0
    return answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed


# ---------------------------------------------------------------------------
# Arm runners
# ---------------------------------------------------------------------------

def run_arm_thinking(arm_name, pass_index, seed, questions, ds, model, processor,
                     out_f, done_qids=None, is_retry=False):
    """Run a thinking arm over `questions` (list of qids). Returns list of trials.

    is_retry=True means we're in arm-B retry pass — stop this question on think_closed.
    done_qids: set of question_ids already written for this (arm, pass_index).
    """
    if done_qids is None:
        done_qids = set()

    torch.manual_seed(seed)
    gen_kwargs = dict(THINKING_GEN, max_new_tokens=MAX_NEW_TOKENS_THINKING)

    trials = []
    lat_history = []
    hard_stopped = False

    for i, qid in enumerate(questions):
        if qid in done_qids:
            continue

        row = ds[qid]
        messages, correct_letter = build_messages(row)

        answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed = infer_one(
            model, processor, messages, gen_kwargs, MAX_NEW_TOKENS_THINKING, is_thinking=True)

        predicted_letter, parse_status = extract_letter(answer_text)
        if predicted_letter is None:
            predicted_letter, parse_status = extract_letter(answer_text)

        t = make_trial(arm_name, qid, row, correct_letter, pass_index, seed,
                       n_input, n_think, n_answer, lat_ms,
                       budget_hit, think_closed, predicted_letter, parse_status, answer_text)
        trials.append(t)
        out_f.write(json.dumps(t) + "\n")
        out_f.flush()
        lat_history.append(lat_ms)

        n_done = i + 1
        n_correct = sum(x["correct"] for x in trials)
        if n_done % 50 == 1 or n_done == len(questions):
            term = sum(1 for x in trials if x["think_closed"])
            print(f"[{arm_name} pass={pass_index} seed={seed}] "
                  f"q{n_done}/{len(questions)} acc={n_correct}/{n_done} "
                  f"({100*n_correct/n_done:.1f}%) term={term}/{n_done}", flush=True)

        # Projection after PROJECT_N trials
        if len(lat_history) == PROJECT_N and not is_retry:
            mean_ms = sum(lat_history) / PROJECT_N
            proj_h = (mean_ms * len(questions)) / 3_600_000
            remain_h = (mean_ms * (len(questions) - n_done)) / 3_600_000
            print(f"\n=== RUNTIME PROJECTION: {arm_name} (after {PROJECT_N} trials) ===")
            print(f"  Mean lat: {mean_ms/1000:.1f}s  n_q: {len(questions)}")
            print(f"  Projected total: {proj_h:.1f}h  Remaining: {remain_h:.1f}h")
            if proj_h > HARD_STOP_H:
                print(f"  WARNING: projected {proj_h:.1f}h > {HARD_STOP_H}h — caller should reduce to {SUBSET_N}-Q subset")
            print()

    n_correct = sum(x["correct"] for x in trials)
    term = sum(1 for x in trials if x["think_closed"])
    print(f"[{arm_name} pass={pass_index} seed={seed}] "
          f"DONE acc={n_correct}/{len(trials)} ({100*n_correct/max(1,len(trials)):.1f}%) "
          f"term={term}/{len(trials)} "
          f"budget_hit={sum(1 for x in trials if x['budget_hit'])}", flush=True)
    return trials, hard_stopped


def run_arm_instruct(arm_name, questions, ds, model, processor, out_f, done_qids=None):
    """Run an instruct arm. think_closed=None (instruct mode), answer_text stored."""
    if done_qids is None:
        done_qids = set()

    gen_kwargs = dict(do_sample=False, max_new_tokens=MAX_NEW_TOKENS_INSTRUCT)
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

        t = make_trial(arm_name, qid, row, correct_letter, 1, None,
                       n_input, 0, n_answer, lat_ms,
                       budget_hit, None, predicted_letter, parse_status, answer_text)
        trials.append(t)
        out_f.write(json.dumps(t) + "\n")
        out_f.flush()
        lat_history.append(lat_ms)

        n_done = i + 1
        n_correct = sum(x["correct"] for x in trials)
        if n_done % 100 == 1 or n_done == len(questions):
            print(f"[{arm_name}] q{n_done}/{len(questions)} "
                  f"acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%)", flush=True)

        if len(lat_history) == PROJECT_N:
            mean_ms = sum(lat_history) / PROJECT_N
            proj_h = (mean_ms * len(questions)) / 3_600_000
            remain_h = (mean_ms * (len(questions) - n_done)) / 3_600_000
            print(f"\n=== RUNTIME PROJECTION: {arm_name} (after {PROJECT_N} trials) ===")
            print(f"  Mean lat: {mean_ms/1000:.1f}s  n_q: {len(questions)}")
            print(f"  Projected total: {proj_h:.1f}h  Remaining: {remain_h:.1f}h")
            if proj_h > HARD_STOP_H:
                print(f"  WARNING: projected {proj_h:.1f}h > {HARD_STOP_H}h — caller should reduce to {SUBSET_N}-Q subset")
            print()

    n_correct = sum(x["correct"] for x in trials)
    print(f"[{arm_name}] DONE acc={n_correct}/{len(trials)} "
          f"({100*n_correct/max(1,len(trials)):.1f}%)", flush=True)
    return trials


def run_arm_b_retries(arm_a_trials, questions, ds, model, processor, out_f, done_set):
    """Run arm B: reuse arm A as pass 1, retry budget_hit questions up to 4 more passes.

    done_set: set of (question_id, pass_index) already in JSONL.
    Returns all arm B trials including pass-1 copies.
    """
    # Copy arm A trials as arm B pass 1 (if not already done)
    arm_b_trials = []
    for t in arm_a_trials:
        if (t["question_id"], 1) not in done_set:
            tb = dict(t)
            tb["arm"] = "B"
            tb["pass_index"] = 1
            arm_b_trials.append(tb)
            out_f.write(json.dumps(tb) + "\n")
            out_f.flush()

    # Find questions needing retries (budget_hit on pass 1)
    retry_qids = {t["question_id"] for t in arm_a_trials if t["budget_hit"]}
    print(f"\n[B] {len(retry_qids)} questions have budget_hit on pass 1 → retrying", flush=True)

    # Track per-question termination
    terminated = {t["question_id"] for t in arm_a_trials if t["think_closed"]}

    for pass_idx, seed in enumerate(RETRY_SEEDS, start=2):
        still_pending = retry_qids - terminated
        if not still_pending:
            print(f"[B] All retry questions terminated before pass {pass_idx}; stopping.", flush=True)
            break

        print(f"\n[B] Pass {pass_idx} (seed={seed}): {len(still_pending)} questions pending", flush=True)
        torch.manual_seed(seed)
        gen_kwargs = dict(THINKING_GEN, max_new_tokens=MAX_NEW_TOKENS_THINKING)

        for qid in sorted(still_pending):
            if (qid, pass_idx) in done_set:
                terminated.add(qid)
                continue

            row = ds[qid]
            messages, correct_letter = build_messages(row)

            answer_text, n_input, n_think, n_answer, lat_ms, budget_hit, think_closed = infer_one(
                model, processor, messages, gen_kwargs, MAX_NEW_TOKENS_THINKING, is_thinking=True)

            predicted_letter, parse_status = extract_letter(answer_text)

            t = make_trial("B", qid, row, correct_letter, pass_idx, seed,
                           n_input, n_think, n_answer, lat_ms,
                           budget_hit, think_closed, predicted_letter, parse_status, answer_text)
            arm_b_trials.append(t)
            out_f.write(json.dumps(t) + "\n")
            out_f.flush()

            if think_closed:
                terminated.add(qid)
                print(f"  [B] q{qid} terminated at pass {pass_idx}", flush=True)

    n_retried = len(retry_qids)
    n_now_term = len(retry_qids & terminated)
    print(f"[B] Retries complete: {n_retried} budget_hit → {n_now_term} now terminated "
          f"({n_retried - n_now_term} never terminated after {len(RETRY_SEEDS)+1} passes)", flush=True)
    return arm_b_trials


# ---------------------------------------------------------------------------
# Already-done tracking
# ---------------------------------------------------------------------------

def load_done(jsonl_path):
    """Return dict arm → set of question_ids done, and (arm_b_q, pass_idx) set."""
    done_per_arm = defaultdict(set)
    done_b = set()
    if not jsonl_path.exists():
        return done_per_arm, done_b
    for line in open(jsonl_path):
        if not line.strip():
            continue
        t = json.loads(line)
        arm = t["arm"]
        qid = t["question_id"]
        done_per_arm[arm].add(qid)
        if arm == "B":
            done_b.add((qid, t.get("pass_index", 1)))
    return done_per_arm, done_b


# ---------------------------------------------------------------------------
# Load 8B-I checkpoint
# ---------------------------------------------------------------------------

def load_model(path, label):
    print(f"\nLoading {label} from {path.split('/')[-1][:20]}...", flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor = AutoProcessor.from_pretrained(path)
    p = next(model.parameters())
    assert p.device.index == 1, f"Expected cuda:1, got {p.device}"
    assert p.dtype == torch.bfloat16, f"Expected bfloat16, got {p.dtype}"
    print(f"  dtype={p.dtype} device={p.device} PASS", flush=True)
    return model, processor


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-done trials")
    parser.add_argument("--arms", nargs="+", default=["E", "D", "A", "B", "C"],
                        help="Arms to run (default: all in order E D A B C)")
    args = parser.parse_args()

    assert torch.cuda.is_available(), "CUDA not available"
    print(f"Device cuda:1 = {torch.cuda.get_device_name(1)}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading ERQA ...", flush=True)
    ds = load_erqa()
    n_multi = sum(1 for r in ds if len(r['images_encoded']) > 1)
    print(f"  {len(ds)} questions, {n_multi} multi-image ({100*n_multi/400:.1f}%)", flush=True)

    # Random baseline
    random_baseline(ds)

    # Stratified subset (pre-compute; used if hard stop triggered)
    subset_qids = compute_stratified_subset(ds, n=SUBSET_N)
    print(f"  Stratified {SUBSET_N}-Q subset pre-computed (first 5: {subset_qids[:5]})", flush=True)

    # Load done state
    done_per_arm, done_b = load_done(JSONL_PATH)
    if args.resume:
        print(f"  Resume: done arms = "
              f"{dict((k, len(v)) for k, v in done_per_arm.items())}", flush=True)

    # Active question set (may shrink to subset after projection)
    questions = list(range(400))
    reduced = False

    arms_to_run = args.arms
    out_f = open(JSONL_PATH, "a")

    # ---- ARM E: reuse StudyK INSTRUCT arm ----
    if "E" in arms_to_run:
        if len(done_per_arm["E"]) == 0 or (args.resume and len(done_per_arm["E"]) < 400):
            print("\n=== ARM E: REUSE StudyK INSTRUCT ===", flush=True)
            assert STUDY_K_JSONL.exists(), f"StudyK JSONL not found: {STUDY_K_JSONL}"
            k_trials = [json.loads(l) for l in open(STUDY_K_JSONL) if l.strip()]
            instruct_trials = [t for t in k_trials if t["arm"] == "INSTRUCT"]
            assert len(instruct_trials) == 400, f"Expected 400 INSTRUCT trials, got {len(instruct_trials)}"
            n_written = 0
            for t in instruct_trials:
                qid = t["question_id"]
                if args.resume and qid in done_per_arm["E"]:
                    continue
                e_trial = {
                    "arm": "E",
                    "question_id": qid,
                    "category": t["category"],
                    "n_images": t["n_images"],
                    "n_input_tokens": t["n_input_tokens"],
                    "n_think_tokens": 0,
                    "n_answer_tokens": t["n_answer_tokens"],
                    "total_latency_ms": t["total_latency_ms"],
                    "budget_hit": t["budget_hit"],
                    "think_closed": None,  # instruct: N/A
                    "predicted_letter": t["predicted_letter"],
                    "correct_letter": t["correct_letter"],
                    "correct": t["correct"],
                    "parse_status": t["parse_status"],
                    "answer_text": None,   # not stored in StudyK INSTRUCT
                    "pass_index": 1,
                    "seed": None,
                    "_reused_from": "study_k_INSTRUCT",
                }
                out_f.write(json.dumps(e_trial) + "\n")
                n_written += 1
            out_f.flush()
            n_correct = sum(1 for t in instruct_trials if t["correct"])
            print(f"[E] DONE: {n_written} trials written (reused from StudyK). "
                  f"acc={n_correct}/400 ({100*n_correct/400:.1f}%) [StudyK value]", flush=True)
        else:
            print(f"[E] Already done ({len(done_per_arm['E'])} trials) — skip", flush=True)

    # ---- ARM D: 8B-Instruct ----
    if "D" in arms_to_run:
        d_done = done_per_arm["D"]
        d_todo = [q for q in questions if q not in d_done] if args.resume else questions
        if d_todo:
            print("\n=== ARM D: 8B-Instruct×1 greedy ===", flush=True)
            model, processor = load_model(PATH_8BI, "8B-Instruct")
            run_arm_instruct("D", d_todo, ds, model, processor, out_f,
                             done_qids=d_done if args.resume else set())
            del model; torch.cuda.empty_cache()
        else:
            print(f"[D] Already done ({len(d_done)} trials) — skip", flush=True)

    # ---- ARM A: 4B-Thinking×1 seed=42 ----
    arm_a_trials = []  # needed for arm B
    if "A" in arms_to_run or "B" in arms_to_run:
        a_done = done_per_arm["A"]
        a_todo = [q for q in questions if q not in a_done] if args.resume else questions

        print("\n=== ARM A: 4B-Thinking×1 seed=42 max_new_tokens=8192 ===", flush=True)
        print("  NOTE: RE-RUN — StudyK used max_new_tokens=16384; NOT REUSABLE.", flush=True)

        if a_todo or not args.resume:
            model, processor = load_model(PATH_4BT, "4B-Thinking")

            if "A" in arms_to_run and a_todo:
                new_a, _ = run_arm_thinking(
                    "A", 1, 42, a_todo, ds, model, processor, out_f,
                    done_qids=a_done if args.resume else set())
                arm_a_trials.extend(new_a)

            # Also load any already-done arm A trials for arm B
            if args.resume and a_done:
                cached = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
                arm_a_trials = [t for t in cached if t["arm"] == "A"]

            # ---- ARM B: retries ----
            if "B" in arms_to_run and arm_a_trials:
                all_a = arm_a_trials
                if args.resume:
                    cached = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
                    all_a = [t for t in cached if t["arm"] == "A"]
                print("\n=== ARM B: 4B-Thinking retries (budget_hit only) ===", flush=True)
                run_arm_b_retries(all_a, questions, ds, model, processor, out_f, done_b)

            del model; torch.cuda.empty_cache()
        else:
            print(f"[A] Already done ({len(a_done)} trials) — skip", flush=True)
            if "B" in arms_to_run:
                cached = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
                all_a = [t for t in cached if t["arm"] == "A"]
                model, processor = load_model(PATH_4BT, "4B-Thinking (for arm B retries)")
                print("\n=== ARM B: 4B-Thinking retries (budget_hit only) ===", flush=True)
                run_arm_b_retries(all_a, questions, ds, model, processor, out_f, done_b)
                del model; torch.cuda.empty_cache()

    # ---- ARM C: 8B-Thinking×1 seed=42 ----
    if "C" in arms_to_run:
        c_done = done_per_arm["C"]
        c_todo = [q for q in questions if q not in c_done] if args.resume else questions
        if c_todo:
            print("\n=== ARM C: 8B-Thinking×1 seed=42 max_new_tokens=8192 ===", flush=True)
            model, processor = load_model(PATH_8BT, "8B-Thinking")
            run_arm_thinking("C", 1, 42, c_todo, ds, model, processor, out_f,
                             done_qids=c_done if args.resume else set())
            del model; torch.cuda.empty_cache()
        else:
            print(f"[C] Already done ({len(c_done)} trials) — skip", flush=True)

    out_f.close()

    # Final summary
    print("\n=== STUDY Q COMPLETE ===", flush=True)
    all_trials = [json.loads(l) for l in open(JSONL_PATH) if l.strip()]
    for arm in ["E", "D", "A", "B", "C"]:
        ts = [t for t in all_trials if t["arm"] == arm]
        if not ts:
            continue
        # For arm B, only count pass_1 trials for per-question accuracy
        if arm == "B":
            # Final answer per question: first think_closed pass
            by_q = defaultdict(list)
            for t in ts:
                by_q[t["question_id"]].append(t)
            n_correct = 0
            for qid, passes in by_q.items():
                term = [p for p in passes if p["think_closed"]]
                if term:
                    term.sort(key=lambda x: x["pass_index"])
                    if term[0]["correct"]:
                        n_correct += 1
            n_q = len(by_q)
            print(f"  arm={arm}: {n_q} questions, final acc={n_correct}/{n_q} "
                  f"({100*n_correct/max(1,n_q):.1f}%)", flush=True)
        else:
            n_q = len({t["question_id"] for t in ts})
            n_correct = sum(1 for t in ts if t["correct"])
            instruct = ts[0]["think_closed"] is None
            if instruct:
                term = sum(1 for t in ts if not t["budget_hit"])
            else:
                term = sum(1 for t in ts if t["think_closed"])
            print(f"  arm={arm}: {n_q} questions, acc={n_correct}/{n_q} "
                  f"({100*n_correct/max(1,n_q):.1f}%) term={term}/{n_q}", flush=True)

    print(f"\nTrials written to {JSONL_PATH}", flush=True)
    print("GIT RULE: Stop. Ask user to commit.", flush=True)


if __name__ == "__main__":
    main()
