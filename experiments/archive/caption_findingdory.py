"""
FindingDory Caption Pilot — v2
===============================
Decoupled perception-reasoning architecture for the FindingDory workload-gate test.

Changes from v1:
  - Clip captioning: 4-6 consecutive frames per clip instead of single frames,
    so the VLM sees motion (pick vs place disambiguation).
  - Directive prompt v2: explicit ACTION / OBJECT / RECEPTACLE structure.
  - GT extraction: short 6-frame clip centered on gold frames, question in prompt.
  - Chain-of-thought reasoning: LLM lists detected interactions in order first.
  - Summary condition added for stop-condition check.
  - Salient-split diagnostic: reports accuracy for tasks whose GT matches the
    most-frequent caption object vs tasks where it does not.

Architecture:
  VLM (Qwen2.5-VL-7B)  → clip captions (4-6 frames, labeled "Frames N-M: ...")
  LLM (Qwen2.5-7B)     → chain-of-thought ordering + answer over caption stream
  LLM judge            → semantic equivalence scoring

Ground truth (fallback — semantic labels not in released dataset):
  6-frame clip around gold frames, captioned with question text as context.
  Mildly circular (same VLM for input captions and GT). Noted as limitation.

Conditions (re-pilot): blind, full, summary-80
Full frontier (Step 3): blind, window-3, window-10, full, shuffled, summary-80, summary-200

Output:
  results/fd_captions_v2_qwenvl7b.json   — clip caption cache (keyed by ep_id)
  results/fd_pilot_v2_qwen7b.json        — re-pilot results

Usage:
  # Re-pilot: same 3 episodes, all three stop-condition checks
  CUDA_VISIBLE_DEVICES=1 python experiments/caption_findingdory.py --pilot

  # Specify episodes
  CUDA_VISIBLE_DEVICES=1 python experiments/caption_findingdory.py \\
      --pilot --episodes ep_1 ep_2 ep_3
"""

import argparse
import ast
import gc
import json
import math
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from experiments._provenance import stamp

# ── Constants ─────────────────────────────────────────────────────────────────

CAPTION_MODEL_ID   = "Qwen/Qwen2.5-VL-7B-Instruct"
REASONING_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

DATA_DIR = Path(__file__).parent.parent / "data" / "findingdory" / "videos" / "val"
RESULTS  = Path(__file__).parent.parent / "results"

CAPTION_PROMPT_VERSION = "v2"
CLIP_SIZE = 5  # frames per clip (96 frames → ~19 clips)

# ── Prompts ────────────────────────────────────────────────────────────────────

# Clip caption prompt: explicit ACTION / OBJECT / RECEPTACLE
CLIP_CAPTION_PROMPT = (
    "A robot arm is performing a household rearrangement task (first-person egocentric "
    "view). These {n} consecutive frames show a single motion segment.\n"
    "Describe the action in one sentence using this format:\n"
    "\"Frames {start}-{end}: The robot [picks up / places / moves toward] "
    "[SPECIFIC OBJECT NAME] [from / on / toward] [SPECIFIC RECEPTACLE/SURFACE NAME].\"\n"
    "Use precise, distinct names for both the object and the receptacle "
    "(e.g., 'purple tape' from 'kitchen counter', not just 'object' or 'table').\n"
    "If no clear pick/place: \"Frames {start}-{end}: The robot navigates through "
    "[room or area].\""
)

# GT extraction: clip with question context
GT_CLIP_PROMPT = (
    "A robot arm is at its goal location in these {n} frames.\n"
    "The task question is: \"{question}\"\n"
    "Name the specific receptacle or object visible in these frames that is the "
    "answer to this question. Give only the concise name (2-5 words), for example: "
    "'kitchen counter', 'android figure', 'wooden dresser', 'purple tape'.\n"
    "Nothing else — just the name."
)

# Reasoning prompt with chain-of-thought
FULL_COT_PROMPT = (
    "You are a robot's memory system. Below are captioned motion clips from a task.\n\n"
    "{captions}\n\n"
    "Step 1 — List ALL detected interactions in temporal order:\n"
    "Interaction 1: [what happened, object, receptacle]\n"
    "Interaction 2: ...\n"
    "(If no clear interaction in a clip, skip it.)\n\n"
    "Step 2 — Answer the question: {question}\n\n"
    "Give only the concise name of the target object or receptacle (2-5 words).\n"
    "Answer:"
)

BLIND_PROMPT = (
    "Question: {question}\n\n"
    "Name the specific object or receptacle the question refers to. "
    "Give only the concise name (2-5 words). Do not explain.\nAnswer:"
)

SUMMARY_PROMPT = (
    "Summarize the following robot interaction log in plain English, preserving "
    "the sequence and names of objects and receptacles interacted with. "
    "Under 80 tokens.\n\n"
    "{captions}\n\nSummary:"
)

SUMMARY_QA_PROMPT = (
    "Robot interaction summary:\n{summary}\n\n"
    "Question: {question}\n\n"
    "Based only on the summary, name the specific object or receptacle the question "
    "refers to. Give only the concise name (2-5 words).\nAnswer:"
)

JUDGE_PROMPT = (
    "Do these two descriptions refer to the same object or receptacle?\n"
    "Description A: {pred}\n"
    "Description B: {gold}\n"
    "Answer YES if they are the same or very similar "
    "(e.g., 'counter' ≈ 'kitchen counter', 'table' ≈ 'wooden table').\n"
    "Answer NO if they are clearly different.\n"
    "Reply with only YES or NO."
)

TARGET_HL = "Single-Goal Temporal Tasks"
TARGET_LL = "Interaction Order"
DEVICE_STR = "cuda:0"

# ── JSON helpers ──────────────────────────────────────────────────────────────

def _load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def _save_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(mp4: Path, n: int = 96) -> list:
    cap = cv2.VideoCapture(str(mp4))
    frames = []
    while len(frames) < n:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames


def make_clips(frames: list, clip_size: int = CLIP_SIZE) -> list:
    """Return list of (start_idx, end_idx, [PIL frames]) non-overlapping clips."""
    clips = []
    n = len(frames)
    for start in range(0, n, clip_size):
        end = min(start + clip_size - 1, n - 1)
        clips.append((start, end, frames[start:end + 1]))
    return clips


# ── VLM loading ───────────────────────────────────────────────────────────────

def load_vlm():
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info as _pvi
    print(f"Loading VLM: {CAPTION_MODEL_ID} ...")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        CAPTION_MODEL_ID, dtype=torch.bfloat16, device_map=DEVICE_STR,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(CAPTION_MODEL_ID)
    return model, processor, _pvi


def _vlm_run(model, processor, pvi_fn, images: list, text_prompt: str,
             max_new: int = 80) -> str:
    """Run VLM on a list of PIL images + text prompt."""
    content = [{"type": "image", "image": img} for img in images]
    content.append({"type": "text", "text": text_prompt})
    messages = [{"role": "user", "content": content}]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, _ = pvi_fn(messages)
    inputs = processor(
        text=[text], images=image_inputs, padding=True, return_tensors="pt"
    ).to(DEVICE_STR)

    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new, do_sample=False,
            pad_token_id=processor.tokenizer.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return processor.tokenizer.decode(gen, skip_special_tokens=True).strip()


def caption_episode_clips(model, processor, pvi_fn, ep_id: str,
                          frames: list, cache: dict) -> list:
    """Return list of clip caption strings. Updates cache in-place.

    Each entry: "Frames N-M: ..."
    """
    cached = cache.get(ep_id)
    clips = make_clips(frames, CLIP_SIZE)
    expected = len(clips)
    if cached and len(cached) == expected:
        print(f"  {ep_id}: clip captions cached ({expected} clips). Skipping.")
        return cached

    captions = list(cached or [])
    start_clip_i = len(captions)
    print(f"  {ep_id}: captioning clips {start_clip_i}–{expected - 1} "
          f"({CLIP_SIZE} frames/clip) ...")

    for i, (start, end, clip_frames) in enumerate(clips[start_clip_i:],
                                                    start=start_clip_i):
        n_frames = end - start + 1
        prompt = CLIP_CAPTION_PROMPT.format(
            n=n_frames, start=start, end=end
        )
        caption = _vlm_run(model, processor, pvi_fn, clip_frames, prompt, max_new=80)
        # Normalise: strip any extra sentences beyond the first
        first_sentence = caption.split(".")[0].strip() + "."
        captions.append(first_sentence)
        print(f"    Clip {i:02d} (frames {start:02d}-{end:02d}): {first_sentence[:90]!r}")

    cache[ep_id] = captions
    return captions


def derive_gt_clip(model, processor, pvi_fn, frames: list,
                   gold_frames: list, question: str) -> str:
    """Caption a 6-frame clip centered on gold frames, with question context."""
    if not gold_frames or not frames:
        return "unknown"
    mid = gold_frames[len(gold_frames) // 2]
    start = max(0, mid - 3)
    end   = min(len(frames) - 1, mid + 2)
    clip  = frames[start:end + 1]
    prompt = GT_CLIP_PROMPT.format(n=len(clip), question=question)
    raw = _vlm_run(model, processor, pvi_fn, clip, prompt, max_new=20)
    cleaned = raw.split("\n")[0].strip().rstrip(".")
    return cleaned


# ── LLM ──────────────────────────────────────────────────────────────────────

def load_llm():
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading LLM: {REASONING_MODEL_ID} ...")
    tok = AutoTokenizer.from_pretrained(REASONING_MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        REASONING_MODEL_ID, torch_dtype=torch.float16, device_map=DEVICE_STR,
    )
    model.eval()
    return model, tok


def _llm_run(model, tok, prompt: str, max_new: int = 80) -> str:
    formatted = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tok(formatted, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new, do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return tok.decode(gen, skip_special_tokens=True).strip()


def _extract_final_answer(cot_response: str) -> str:
    """Extract the name after 'Answer:' from a chain-of-thought response."""
    if "Answer:" in cot_response:
        after = cot_response.split("Answer:")[-1].strip()
        # Take only the first line (the concise name)
        return after.split("\n")[0].strip()
    # Fallback: last non-empty line
    lines = [l.strip() for l in cot_response.strip().splitlines() if l.strip()]
    return lines[-1] if lines else cot_response.strip()


def captions_to_text(captions: list, condition: str,
                     shuffle_seed: int = None) -> str | None:
    """Build the caption text block for a given condition."""
    if condition == "full":
        return "\n".join(captions)
    if condition == "shuffled":
        rng = random.Random(shuffle_seed)
        shuffled = list(captions)
        rng.shuffle(shuffled)
        return "\n".join(shuffled)
    if condition.startswith("window-"):
        k = int(condition.split("-")[1])
        return "\n".join(captions[-k:])
    return None  # blind or summary handled separately


def answer_question(model, tok, captions: list, question: str,
                    condition: str, shuffle_seed: int = 42) -> tuple[str, str]:
    """Return (raw_response, final_answer) for the given condition."""
    if condition == "blind":
        prompt = BLIND_PROMPT.format(question=question)
        raw = _llm_run(model, tok, prompt, max_new=20)
        return raw, raw.split("\n")[0].strip()

    if condition in ("summary-80", "summary-200"):
        ctx = captions_to_text(captions, "full")
        sum_prompt = SUMMARY_PROMPT.format(captions=ctx)
        summary = _llm_run(model, tok, sum_prompt, max_new=120)
        qa_prompt = SUMMARY_QA_PROMPT.format(summary=summary, question=question)
        raw = _llm_run(model, tok, qa_prompt, max_new=20)
        return f"[summary]: {summary[:120]}\n[answer]: {raw}", raw.split("\n")[0].strip()

    ctx = captions_to_text(captions, condition, shuffle_seed)
    if ctx is None:
        return "(no context)", "unknown"
    prompt = FULL_COT_PROMPT.format(captions=ctx, question=question)
    raw = _llm_run(model, tok, prompt, max_new=200)
    final = _extract_final_answer(raw)
    return raw, final


# ── Scoring ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def substring_match(pred: str, gold: str) -> int:
    return int(_normalize(gold) in _normalize(pred))


def llm_judge(model, tok, pred: str, gold: str) -> int:
    prompt = JUDGE_PROMPT.format(pred=pred.strip(), gold=gold.strip())
    response = _llm_run(model, tok, prompt, max_new=4)
    return 1 if response.strip().upper().startswith("YES") else 0


# ── Salience detection ────────────────────────────────────────────────────────

def detect_salient_objects(captions: list) -> str:
    """Return the most frequently mentioned non-trivial noun phrase in captions."""
    # Extract object/receptacle names from clip caption strings
    # "The robot picks up X from Y" or "places X on Y" or "navigates toward Y"
    tokens = []
    for cap in captions:
        cap_lower = cap.lower()
        # Extract after 'picks up', 'places', 'navigates toward'
        for pattern in [r'picks up (.+?) from',
                        r'picks up (.+?) on',
                        r'places? (.+?) on',
                        r'places? (.+?) from',
                        r'navigates? toward (.+?)[\.,]',
                        r'navigates? through (.+?)[\.,]']:
            m = re.search(pattern, cap_lower)
            if m:
                tokens.append(m.group(1).strip())
        # Also extract the receptacle (after 'from' or 'on')
        for pattern in [r'from (.+?)[\.,]',
                        r' on (.+?)[\.,]',
                        r'toward (.+?)[\.,]']:
            m = re.search(pattern, cap_lower)
            if m:
                tokens.append(m.group(1).strip())
    if not tokens:
        return "unknown"
    counts = Counter(tokens)
    return counts.most_common(1)[0][0]


def is_salient(gt_label: str, salient_obj: str) -> bool:
    """True if gt_label overlaps with the salient object."""
    return bool(_normalize(salient_obj) and
                (_normalize(salient_obj) in _normalize(gt_label) or
                 _normalize(gt_label) in _normalize(salient_obj)))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_tasks(ep_ids: list) -> list:
    from datasets import load_dataset
    ds = load_dataset("yali30/findingdory-subsampled-96", split="validation")
    tasks = []
    for row in ds:
        if row["ep_id"] not in ep_ids:
            continue
        if row["high_level_category"] != TARGET_HL:
            continue
        if row["low_level_category"] != TARGET_LL:
            continue
        gold_frames = []
        try:
            lists = ast.literal_eval(row["answer"])
            for g in lists:
                if isinstance(g, list):
                    gold_frames.extend(g)
        except Exception:
            pass
        tasks.append({
            "ep_id":      row["ep_id"],
            "task_id":    row["task_id"],
            "question":   row["question"],
            "answer_raw": row["answer"],
            "gold_frames": sorted(set(gold_frames)),
        })
    return tasks


# ── Pilot run ─────────────────────────────────────────────────────────────────

def run_pilot(ep_ids: list, caption_cache_path: Path, out_path: Path):
    RESULTS.mkdir(exist_ok=True)
    caption_cache = _load_json(caption_cache_path) or {}

    conditions = ["blind", "full", "summary-80"]

    # ── Phase 1: VLM — clip captions + GT extraction ─────────────────────────
    print("\n── Phase 1: VLM clip captioning + GT extraction ───────────────────")
    vlm, vlm_proc, pvi_fn = load_vlm()

    all_frames:   dict[str, list] = {}
    all_captions: dict[str, list] = {}  # ep_id → list of clip caption strings

    for ep_id in ep_ids:
        mp4 = DATA_DIR / f"{ep_id}.mp4"
        if not mp4.exists():
            print(f"  SKIP {ep_id}: mp4 not found at {mp4}")
            continue
        print(f"\n  {ep_id}: extracting frames ...")
        frames = extract_frames(mp4, n=96)
        all_frames[ep_id] = frames
        print(f"  {ep_id}: {len(frames)} frames → {math.ceil(len(frames)/CLIP_SIZE)} clips.")
        caps = caption_episode_clips(vlm, vlm_proc, pvi_fn, ep_id, frames,
                                     caption_cache)
        all_captions[ep_id] = caps

    _save_json(caption_cache_path, caption_cache)
    print(f"\n  Clip caption cache saved → {caption_cache_path}")

    # Load tasks and derive GT for each
    print("\n── Deriving GT labels from gold-frame clips (question in context) ──")
    tasks = load_tasks(ep_ids)
    print(f"  {len(tasks)} Interaction Order tasks across {len(ep_ids)} episodes.")

    gt_errors = []
    for task in tasks:
        ep_id  = task["ep_id"]
        frames = all_frames.get(ep_id, [])
        gold   = task["gold_frames"]
        q      = task["question"]
        if not frames or not gold:
            task["gt_label"] = "unknown"
            gt_errors.append(task["task_id"])
            continue
        gt = derive_gt_clip(vlm, vlm_proc, pvi_fn, frames, gold, q)
        task["gt_label"] = gt
        # Quick sanity check: reject obviously bad GT
        bad_patterns = ["robot", "hand", "floor", "goal location", "unknown",
                        "wall", "ceiling", "nothing"]
        if any(b in gt.lower() for b in bad_patterns):
            task["gt_quality"] = "suspect"
        else:
            task["gt_quality"] = "ok"
        print(f"  {ep_id}/{task['task_id']:10s}: gold={gold[:3]}... "
              f"gt={gt!r:30s} [{task['gt_quality']}]")

    del vlm, vlm_proc, pvi_fn
    gc.collect()
    torch.cuda.empty_cache()
    print("\n  VLM unloaded.")

    # ── Phase 2: Salience detection ───────────────────────────────────────────
    print("\n── Salience analysis ──────────────────────────────────────────────")
    ep_salient = {}
    for ep_id, caps in all_captions.items():
        sal = detect_salient_objects(caps)
        ep_salient[ep_id] = sal
        print(f"  {ep_id}: most salient object = {sal!r}")

    for task in tasks:
        sal = ep_salient.get(task["ep_id"], "")
        task["is_salient"] = is_salient(task.get("gt_label", ""), sal)
        task["episode_salient_obj"] = sal

    n_sal = sum(t["is_salient"] for t in tasks)
    print(f"  Salient tasks: {n_sal}/{len(tasks)}, "
          f"Non-salient: {len(tasks) - n_sal}/{len(tasks)}")

    # ── Phase 3: LLM reasoning ────────────────────────────────────────────────
    print("\n── Phase 3: LLM reasoning (blind, full, summary-80) ───────────────")
    llm, llm_tok = load_llm()

    records = []
    for task in tasks:
        ep_id   = task["ep_id"]
        task_id = task["task_id"]
        q       = task["question"]
        gt      = task.get("gt_label", "unknown")
        caps    = all_captions.get(ep_id, [])

        if not caps:
            continue

        rec = {
            "ep_id":               ep_id,
            "task_id":             task_id,
            "question":            q,
            "gold_frames_sample":  task["gold_frames"][:5],
            "gt_label":            gt,
            "gt_quality":          task.get("gt_quality", "unknown"),
            "is_salient":          task["is_salient"],
            "episode_salient_obj": task["episode_salient_obj"],
            "conditions":          {},
        }

        for cond in conditions:
            t0 = time.perf_counter()
            raw, final = answer_question(llm, llm_tok, caps, q, cond)
            elapsed = time.perf_counter() - t0

            sub  = substring_match(final, gt)
            judg = llm_judge(llm, llm_tok, final, gt)
            rec["conditions"][cond] = {
                "pred_final":      final,
                "pred_raw_truncated": raw[:300],
                "substring_match": sub,
                "llm_judge":       judg,
                "elapsed_s":       round(elapsed, 2),
            }
            sal_flag = "SAL" if task["is_salient"] else "   "
            print(f"  {ep_id}/{task_id} [{cond:10s}] {sal_flag} "
                  f"pred={final!r:30s} gt={gt!r:25s} "
                  f"sub={sub} judge={judg}")

        records.append(rec)

    del llm, llm_tok
    gc.collect()
    torch.cuda.empty_cache()

    # ── Statistics ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("STOP-CONDITION DIAGNOSTIC")
    print("=" * 90)

    def _acc(recs, cond, metric="llm_judge"):
        vals = [r["conditions"][cond][metric]
                for r in recs if cond in r["conditions"]]
        return (sum(vals) / len(vals), len(vals)) if vals else (0.0, 0)

    # Split: ok-quality GT only (suspect GT excluded from headline)
    ok_recs     = [r for r in records if r.get("gt_quality") != "suspect"]
    salient_ok  = [r for r in ok_recs if     r["is_salient"]]
    nonsalient  = [r for r in ok_recs if not r["is_salient"]]

    print(f"\nGT quality breakdown:")
    print(f"  ok    : {len(ok_recs)}/{len(records)} tasks")
    print(f"  suspect: {len(records) - len(ok_recs)}/{len(records)} tasks "
          f"(excluded from headline)")

    print(f"\n{'':30s} {'blind':>8} {'full':>8} {'summary-80':>12}")
    print("-" * 62)
    for label, recs in [("ALL (ok GT)", ok_recs),
                          ("  salient", salient_ok),
                          ("  non-salient ← KEY", nonsalient)]:
        row = f"  {label:<28}"
        for cond in conditions:
            acc, n = _acc(recs, cond)
            row += f"  {acc:.2f}({n:2d})"
        print(row)

    print()
    # Stop-condition evaluation
    nonsalient_full_acc, n_ns   = _acc(nonsalient, "full")
    nonsalient_blind_acc, _     = _acc(nonsalient, "blind")
    nonsalient_sum_acc, _       = _acc(nonsalient, "summary-80")
    salient_full_acc, _         = _acc(salient_ok, "full")

    sc1 = "PASS" if all(r.get("gt_quality") == "ok" for r in records) else (
          f"PARTIAL — {len(records) - len(ok_recs)} suspect GT labels")
    sc2 = ("PASS" if nonsalient_full_acc > 0.10 else
           f"FAIL (full={nonsalient_full_acc:.2f}, blind={nonsalient_blind_acc:.2f})")
    sc3 = ("PASS" if (nonsalient_full_acc - nonsalient_sum_acc) > 0.05 else
           f"FAIL (full={nonsalient_full_acc:.2f}, sum80={nonsalient_sum_acc:.2f}, "
           f"gap={nonsalient_full_acc - nonsalient_sum_acc:.2f})")

    print("Stop-condition checks (non-salient, ok-GT tasks only):")
    print(f"  1. Clean verified GT:                 {sc1}")
    print(f"  2. Full-context ordered recall > blind floor: {sc2}")
    print(f"  3. Visible full→summary drop:         {sc3}")
    print()
    if "PASS" in sc1 and "PASS" in sc2 and "PASS" in sc3:
        print("ALL THREE STOP-CONDITIONS PASS → proceed to 50-episode frontier.")
    else:
        print("NOT ALL STOP-CONDITIONS PASS → do not proceed to full frontier.")

    # ── Caption samples ────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("CHECKPOINT 2 (RE-PILOT) — CLIP CAPTION SAMPLES")
    print("=" * 90)
    for ep_id in ep_ids:
        caps = all_captions.get(ep_id)
        if not caps:
            continue
        clips = make_clips(all_frames.get(ep_id, []), CLIP_SIZE)
        print(f"\n{ep_id} — every 4th clip:")
        for i, cap in enumerate(caps):
            if i % 4 == 0:
                start, end, _ = clips[i]
                print(f"  [{i:02d}] Frames {start:02d}-{end:02d}: {cap[:100]!r}")

    print("\n── GT table ───────────────────────────────────────────────────────")
    print(f"{'ep/task':<22} {'question (trunc)':<55} {'GT label':<25} quality  salient")
    print("-" * 112)
    for task in tasks:
        ep_tid = f"{task['ep_id']}/{task['task_id']}"
        print(f"{ep_tid:<22} {task['question'][:53]:<55} "
              f"{task.get('gt_label','?'):<25} "
              f"{task.get('gt_quality','?'):<8} "
              f"{'Y' if task['is_salient'] else 'N'}")

    # ── Save output ────────────────────────────────────────────────────────────
    device = (torch.cuda.get_device_name(0)
              if torch.cuda.is_available() else "cpu")
    prov = stamp(
        script="caption_findingdory.py",
        model="qwenvl7b+qwen7b",
        device=device.lower().replace(" ", "_"),
        n=len(records),
        args=argparse.Namespace(
            caption_prompt_version=CAPTION_PROMPT_VERSION,
            clip_size=CLIP_SIZE,
            captioner=CAPTION_MODEL_ID,
            reasoner=REASONING_MODEL_ID,
            episodes=ep_ids,
            conditions=conditions,
        ),
    )

    out = {
        "metadata": {
            "caption_model":          CAPTION_MODEL_ID,
            "reasoning_model":        REASONING_MODEL_ID,
            "caption_prompt_version": CAPTION_PROMPT_VERSION,
            "clip_size":              CLIP_SIZE,
            "target_hl_category":     TARGET_HL,
            "target_ll_category":     TARGET_LL,
            "episodes":               ep_ids,
            "n_tasks":                len(records),
            "conditions":             conditions,
            "gt_source":              "gold_frame_clip_with_question_context_qwenvl7b",
            "gt_circularity_note":    (
                "GT derived by captioning a 6-frame clip centered on gold frames "
                "using the same VLM as input captioning. Mildly circular. "
                "Noted as limitation."
            ),
            "semantic_labels_in_dataset": False,
            "timestamp": datetime.now().isoformat(),
        },
        "ep_salient_objects": ep_salient,
        "records":  records,
        "stop_conditions": {
            "sc1_clean_gt":            sc1,
            "sc2_nonsalient_recall":   sc2,
            "sc3_full_to_summary_drop": sc3,
        },
        "_provenance": prov,
    }
    _save_json(out_path, out)
    print(f"\n  Results saved → {out_path}")
    print(f"  Caption cache → {caption_cache_path}")
    print("\nStopped after re-pilot. Do not stage or commit.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="FindingDory caption re-pilot v2 — Checkpoint 2 re-run"
    )
    ap.add_argument("--pilot", action="store_true",
                    help="Run re-pilot on 3 episodes")
    ap.add_argument("--episodes", nargs="+", default=None,
                    help="Episode ids (default: ep_1 ep_2 ep_3)")
    ap.add_argument("--caption-cache",
                    default="results/fd_captions_v2_qwenvl7b.json")
    ap.add_argument("--out",
                    default="results/fd_pilot_v2_qwen7b.json")
    args = ap.parse_args()

    if args.pilot:
        ep_ids = args.episodes or ["ep_1", "ep_2", "ep_3"]
        run_pilot(ep_ids, Path(args.caption_cache), Path(args.out))
    else:
        print("Use --pilot to run the re-pilot.")
        ap.print_help()


if __name__ == "__main__":
    main()
