"""
FindingDory frame-budget frontier.

Sweeps frame budgets {96, 48, 24, 12, 6} on temporal and multi-goal episodes
to measure visual-context compressibility. Uses the SFT model
yali30/findingdory-qwen2.5-VL-3B-finetuned (trained on full 96-frame videos).

Gold answer indices are in 0-95 mp4-position space.
When subsampling to K frames, model output is interpreted as a positional index
in [0, K-1]; we map it back to original mp4 index before scoring against gold.

Output: results/frontier_findingdory_qwenvl3b.json
"""

import argparse
import ast
import json
import os
import sys
import time
from pathlib import Path

import cv2
import torch
from PIL import Image
from datasets import load_dataset
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

sys.path.insert(0, str(Path(__file__).parent.parent))
from experiments._provenance import stamp

# ── constants ──────────────────────────────────────────────────────────────────
MODEL_ID      = "yali30/findingdory-qwen2.5-VL-3B-finetuned"
BASE_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"   # SFT model has no processor config
DATA_DIR   = Path(__file__).parent.parent / "data" / "findingdory" / "videos"
RESULTS    = Path(__file__).parent.parent / "results"
CKPT_PATH  = RESULTS / "frontier_findingdory_qwenvl3b_ckpt.json"

BUDGETS    = [96, 48, 24, 12, 6]
TARGET_CATS = {"Single-Goal Temporal Tasks", "Multi-Goal Tasks"}

DEVICE_STR = "cuda:0"   # CUDA_VISIBLE_DEVICES=1 remaps the A6000 to cuda:0
SYSTEM_MSG = None   # use model default "You are a helpful assistant."

# ── frame extraction ───────────────────────────────────────────────────────────

def extract_frames(mp4_path: Path, n: int = 96) -> list[Image.Image]:
    cap = cv2.VideoCapture(str(mp4_path))
    frames = []
    while len(frames) < n:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames


def subsample(frames: list[Image.Image], budget: int) -> tuple[list[Image.Image], list[int]]:
    n = len(frames)
    if budget >= n:
        return frames, list(range(n))
    step = n / budget
    indices = [int(i * step) for i in range(budget)]
    return [frames[i] for i in indices], indices

# ── inference ──────────────────────────────────────────────────────────────────

def run_inference(model, processor, frames: list[Image.Image], question: str,
                  max_new_tokens: int = 512) -> tuple[str, float]:
    content = [{"type": "image", "image": f} for f in frames]
    content.append({"type": "text", "text": question})
    messages = [{"role": "user", "content": content}]
    if SYSTEM_MSG:
        messages = [{"role": "system", "content": SYSTEM_MSG}] + messages
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(
        text=[text], images=image_inputs,
        padding=True, return_tensors="pt"
    ).to(DEVICE_STR)

    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    elapsed = time.perf_counter() - t0

    gen = out[0][inputs["input_ids"].shape[1]:]
    decoded = processor.decode(gen, skip_special_tokens=True).strip()
    return decoded, elapsed

# ── parsing ────────────────────────────────────────────────────────────────────

def parse_prediction(raw: str) -> list[list[int]] | None:
    raw = raw.strip()
    for attempt in [raw, raw.split("\n")[0]]:
        try:
            parsed = ast.literal_eval(attempt)
            if isinstance(parsed, list):
                if parsed and isinstance(parsed[0], int):
                    return [parsed]
                if parsed and isinstance(parsed[0], list):
                    return parsed
        except Exception:
            pass
    import re
    m = re.search(r'\[\s*\[.*?\]\s*\]', raw, re.DOTALL)
    if m:
        try:
            return ast.literal_eval(m.group())
        except Exception:
            pass
    m = re.search(r'\[[\d,\s]+\]', raw)
    if m:
        try:
            inner = ast.literal_eval(m.group())
            if isinstance(inner, list) and inner:
                return [inner]
        except Exception:
            pass
    # Truncated output fallback: extract the first integer after '[['
    m = re.search(r'\[\s*\[\s*(\d+)', raw)
    if m:
        return [[int(m.group(1))]]
    m = re.search(r'\[\s*(\d+)', raw)
    if m:
        return [[int(m.group(1))]]
    return None

# ── scoring ────────────────────────────────────────────────────────────────────

def _map_pred_index(pred_pos: int, kept_indices: list[int]) -> int:
    """Map a predicted positional index to original mp4 index (0-95)."""
    if 0 <= pred_pos < len(kept_indices):
        return kept_indices[pred_pos]
    return pred_pos   # model may already output 0-95 directly


def score_task(pred_raw: str, gold_str: str, kept_indices: list[int]) -> dict:
    gold = ast.literal_eval(gold_str)          # list of lists (0-95 mp4 space)
    n_goals = len(gold)
    gold_sets = [set(g) for g in gold]
    gold_union = set().union(*gold_sets)

    parsed = parse_prediction(pred_raw)
    if parsed is None:
        return {"hl_sr": 0, "any_in": 0, "parse_ok": False,
                "per_goal": [0] * n_goals, "parsed": None, "n_goals": n_goals}

    # HL-SR: first predicted index of each goal sublist must be in gold set.
    goal_hits_strict = []
    # any-in: any predicted index (across all sublists) in gold union.
    all_pred_orig = []
    for gi in range(n_goals):
        sublist = parsed[gi] if gi < len(parsed) else []
        if not sublist:
            goal_hits_strict.append(0)
            continue
        orig_indices = [_map_pred_index(p, kept_indices) for p in sublist]
        all_pred_orig.extend(orig_indices)
        first_orig = orig_indices[0]
        goal_hits_strict.append(1 if first_orig in gold_sets[gi] else 0)

    # any-in: at least one predicted orig index overlaps any gold set
    any_in = int(bool(set(all_pred_orig) & gold_union))

    return {
        "hl_sr":    int(all(h == 1 for h in goal_hits_strict)),
        "any_in":   any_in,
        "parse_ok": True,
        "per_goal": goal_hits_strict,
        "parsed":   parsed,
        "n_goals":  n_goals,
    }

# ── data selection ─────────────────────────────────────────────────────────────

def select_tasks(ds, n_episodes: int, max_per_ep: int) -> list[dict]:
    rows_by_ep: dict[str, list] = {}
    for row in ds:
        if row["high_level_category"] not in TARGET_CATS:
            continue
        ep = row["ep_id"]
        rows_by_ep.setdefault(ep, []).append(row)

    selected = []
    for ep_id in sorted(rows_by_ep.keys())[:n_episodes]:
        ep_rows = rows_by_ep[ep_id][:max_per_ep]
        for row in ep_rows:
            mp4 = DATA_DIR / row["video"].lstrip("videos/")
            if not mp4.exists():
                mp4 = DATA_DIR / "val" / f"{ep_id}.mp4"
            row = dict(row)
            row["_mp4"] = str(mp4)
            selected.append(row)
    return selected

# ── checkpoint helpers ─────────────────────────────────────────────────────────

def load_ckpt() -> dict:
    if CKPT_PATH.exists():
        with open(CKPT_PATH) as f:
            return json.load(f)
    return {}


def save_ckpt(ckpt: dict):
    CKPT_PATH.parent.mkdir(exist_ok=True)
    with open(CKPT_PATH, "w") as f:
        json.dump(ckpt, f)

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_episodes",  type=int, default=25)
    parser.add_argument("--max_per_ep",  type=int, default=2)
    parser.add_argument("--sanity_only", action="store_true",
                        help="Run 96-frame sanity check on first 10 episodes only")
    parser.add_argument("--device",      default="nvidia_rtx_a6000")
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)

    print("Loading FindingDory validation split...")
    ds = load_dataset("yali30/findingdory-subsampled-96", split="validation")

    n_ep  = 10 if args.sanity_only else args.n_episodes
    budgets = [96] if args.sanity_only else BUDGETS

    tasks = select_tasks(ds, n_ep, args.max_per_ep)
    print(f"Selected {len(tasks)} tasks from {n_ep} episodes  "
          f"(budgets: {budgets})")
    cat_counts = {}
    for t in tasks:
        cat_counts[t["high_level_category"]] = cat_counts.get(t["high_level_category"], 0) + 1
    print("Category breakdown:", cat_counts)
    print()

    print(f"Loading {MODEL_ID}...")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map=DEVICE_STR
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(BASE_MODEL_ID)
    print("Model ready.\n")

    ckpt = load_ckpt()
    records: list[dict] = []

    total = len(tasks) * len(budgets)
    done  = 0

    for task in tasks:
        ep_id   = task["ep_id"]
        task_id = task["task_id"]
        mp4     = Path(task["_mp4"])
        question = task["question"]
        gold_str = task["answer"]
        hl_cat   = task["high_level_category"]
        ll_cat   = task["low_level_category"]

        if not mp4.exists():
            print(f"  SKIP {ep_id}/{task_id} — mp4 not found: {mp4}")
            continue

        all_frames = extract_frames(mp4, n=96)
        if len(all_frames) < 96:
            print(f"  WARN {ep_id}/{task_id} — only {len(all_frames)} frames extracted")

        for budget in budgets:
            key = f"{ep_id}_{task_id}_b{budget}"
            done += 1

            if key in ckpt:
                records.append(ckpt[key])
                print(f"  [{done}/{total}] {key} (cached) hl_sr={ckpt[key]['hl_sr']}")
                continue

            frames_k, kept_idx = subsample(all_frames, budget)
            raw, elapsed = run_inference(model, processor, frames_k, question)
            result = score_task(raw, gold_str, kept_idx)

            rec = {
                "ep_id":      ep_id,
                "task_id":    task_id,
                "budget":     budget,
                "hl_sr":      result["hl_sr"],
                "any_in":     result.get("any_in", 0),
                "parse_ok":   result["parse_ok"],
                "per_goal":   result["per_goal"],
                "n_goals":    result["n_goals"],
                "hl_cat":     hl_cat,
                "ll_cat":     ll_cat,
                "gold":       gold_str,
                "pred_raw":   raw,
                "pred_parsed":result["parsed"],
                "kept_indices": kept_idx,
                "elapsed_s":  round(elapsed, 3),
            }
            ckpt[key] = rec
            save_ckpt(ckpt)
            records.append(rec)

            print(f"  [{done}/{total}] {key}  hl_sr={result['hl_sr']}  "
                  f"any_in={result.get('any_in',0)}  "
                  f"pred={raw[:60]!r}  {elapsed:.1f}s")

    # ── aggregate results ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINDINGDORY FRAME-BUDGET FRONTIER")
    print("=" * 70)

    by_budget_cat_hlsr:  dict[tuple, list] = {}
    by_budget_cat_anyin: dict[tuple, list] = {}
    for r in records:
        for bcat in [(r["budget"], "overall"), (r["budget"], r["hl_cat"])]:
            by_budget_cat_hlsr.setdefault(bcat, []).append(r["hl_sr"])
            by_budget_cat_anyin.setdefault(bcat, []).append(r.get("any_in", 0))

    print(f"\n{'budget':>8}  {'category':<40}  {'hl_sr':>6}  {'any_in':>7}  {'n':>4}")
    print("-" * 72)
    for budget in budgets:
        for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            hl_vals   = by_budget_cat_hlsr.get((budget, cat), [])
            anyin_vals = by_budget_cat_anyin.get((budget, cat), [])
            if not hl_vals:
                continue
            hl_acc  = sum(hl_vals) / len(hl_vals)
            ai_acc  = sum(anyin_vals) / len(anyin_vals)
            print(f"{budget:>8}  {cat:<40}  {hl_acc:>6.3f}  {ai_acc:>7.3f}  {len(hl_vals):>4}")

    # ── write result JSON ──────────────────────────────────────────────────────
    summary = {}
    for budget in budgets:
        summary[str(budget)] = {}
        for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            hl_vals   = by_budget_cat_hlsr.get((budget, cat), [])
            anyin_vals = by_budget_cat_anyin.get((budget, cat), [])
            if hl_vals:
                summary[str(budget)][cat] = {
                    "hl_sr":  round(sum(hl_vals) / len(hl_vals), 4),
                    "any_in": round(sum(anyin_vals) / len(anyin_vals), 4),
                    "n": len(hl_vals),
                }

    prov = stamp(
        script="frontier_findingdory.py",
        model="qwenvl3b",
        device=args.device,
        n=len(records),
        args=args,
    )

    out = {
        "summary_by_budget_category": summary,
        "records": records,
        "_provenance": prov,
    }
    out_path = RESULTS / "frontier_findingdory_qwenvl3b.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults written to {out_path}")

    if args.sanity_only:
        recs96 = [r for r in records if r["budget"] == 96]
        hl_acc  = sum(r["hl_sr"] for r in recs96) / len(recs96) if recs96 else 0
        ai_acc  = sum(r.get("any_in",0) for r in recs96) / len(recs96) if recs96 else 0
        print(f"\nSANITY @ 96 frames: hl_sr={hl_acc:.3f}  any_in={ai_acc:.3f}  (n={len(recs96)})")
        print("Reference: authors report ~52.4% HL-SR overall; temporal subset typically lower")


if __name__ == "__main__":
    main()
