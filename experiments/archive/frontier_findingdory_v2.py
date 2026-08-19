"""
FindingDory frame-budget frontier — v2 (authors' exact eval pipeline).

Changes from v1:
  - Video passed as {"type": "video", "video": [pil...]} through the video pathway
    (training used videos=..., not images=...; these use different model tokens)
  - Empty system message block matches training format (use_system_message=False)
  - Scoring: calculate_relaxed_match from findingdory-train/evaluate_llm_outputs.py
    (product of per-goal precision, not "first element" or "any overlap")
  - gold_survived tracking: partition REASONING (gold in input) vs REMOVED (not shown)
  - Gate test (--gate_only): run budget=96 on ~30 episodes first; abort if score is wildly
    below expected range before running the expensive sweep

Index convention (confirmed):
  Gold answers are in 0-95 mp4-position space.
  Frames carry ORIGINAL video frame numbers ("Frame: 289" at mp4 pos 49 for ep_1).
  Model was trained to output 0-95 positional indices; outputs are compared directly
  to gold in 0-95 space with no mapping.

Output: results/frontier_findingdory_qwenvl3b.json (overwrites prior run)
"""

import argparse
import ast
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from datasets import load_dataset
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForVision2Seq, AutoProcessor

sys.path.insert(0, str(Path(__file__).parent.parent))
from experiments._provenance import stamp

# ── constants ──────────────────────────────────────────────────────────────────
MODEL_ID      = "yali30/findingdory-qwen2.5-VL-3B-finetuned"
BASE_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
DATA_DIR      = Path(__file__).parent.parent / "data" / "findingdory" / "videos"
RESULTS       = Path(__file__).parent.parent / "results"
CKPT_PATH     = RESULTS / "frontier_findingdory_v2_ckpt.json"

BUDGETS       = [96, 48, 24, 12, 6]
TARGET_CATS   = {"Single-Goal Temporal Tasks", "Multi-Goal Tasks"}
MAX_PIXELS    = 360 * 420   # matches training: max_pixels in video message
DEVICE_STR    = "cuda:0"    # CUDA_VISIBLE_DEVICES=1 remaps A6000 to cuda:0

# ── authors' exact scoring functions ──────────────────────────────────────────

def parse_list_string(list_string: str) -> list:
    """From findingdory-train/findingdory/evaluate_llm_outputs.py — verbatim."""
    try:
        return ast.literal_eval(list_string)
    except Exception:
        try:
            last_open  = list_string.rfind("[")
            last_close = list_string.rfind("]")
            if last_open != -1 and last_close != -1:
                potential  = list_string[last_open : last_close + 1]
                parsed     = ast.literal_eval(potential)
                if isinstance(parsed, list):
                    if parsed and isinstance(parsed[0], int):
                        return [parsed]
                    elif parsed and isinstance(parsed[0], list):
                        return parsed
                return []
            return []
        except Exception:
            return []


def calculate_relaxed_match(pred_lists: list, gt_lists: list) -> float:
    """From findingdory-train/findingdory/evaluate_llm_outputs.py — verbatim."""
    if len(pred_lists) != len(gt_lists):
        return 0.0
    precision_all_goals = []
    for pred_sublist, gt_sublist in zip(pred_lists, gt_lists):
        if len(pred_sublist) == 0 and len(gt_sublist) == 0:
            precision = 1.0
        elif len(pred_sublist) == 0 or len(gt_sublist) == 0:
            precision = 0.0
        else:
            precision = sum(p in gt_sublist for p in pred_sublist) / len(pred_sublist)
            precision_all_goals.append(precision)
    return float(np.prod(precision_all_goals))


def extract_assistant_response(text: str) -> str:
    """From findingdory-train/findingdory/utils.py — verbatim."""
    if "assistant\n" in text:
        return text.split("assistant\n", 1)[1].strip()
    return text

# ── frame extraction ──────────────────────────────────────────────────────────

def extract_frames(mp4_path: Path, n: int = 96) -> list:
    cap    = cv2.VideoCapture(str(mp4_path))
    frames = []
    while len(frames) < n:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames


def subsample(frames: list, budget: int) -> tuple:
    n = len(frames)
    if budget >= n:
        return frames, list(range(n))
    step    = n / budget
    indices = [int(i * step) for i in range(budget)]
    return [frames[i] for i in indices], indices

# ── gold utilities ─────────────────────────────────────────────────────────────

def gold_mp4_positions(gold_str: str) -> set:
    """Return set of all mp4 positions appearing in a gold answer string."""
    try:
        lists = ast.literal_eval(gold_str)
        out   = set()
        for g in lists:
            if g == [-1]:
                continue
            out.update(g)
        return out
    except Exception:
        return set()


def is_valid_gold(gold_str: str) -> bool:
    """Reject tasks whose gold answer contains [-1] (not answerable in subsampled video)."""
    try:
        lists = ast.literal_eval(gold_str)
        return not any(g == [-1] for g in lists)
    except Exception:
        return False

# ── inference ─────────────────────────────────────────────────────────────────

def run_inference(model, processor, frames_pil: list, question: str,
                  max_new_tokens: int = 512) -> tuple:
    """
    Authors' exact inference format:
      - system turn with empty text (matches training use_system_message=False)
      - video as list of PIL images through {"type": "video", ...} pathway
      - no add_generation_prompt; full decode + extract_assistant_response
    """
    messages = [
        {"role": "system", "content": [{"type": "text", "text": ""}]},
        {
            "role": "user",
            "content": [
                {"type": "video", "video": frames_pil, "max_pixels": MAX_PIXELS},
                {"type": "text",  "text": question},
            ],
        },
    ]

    text        = processor.apply_chat_template(messages, tokenize=False)
    video_input = process_vision_info(messages)[1][0]

    inputs = processor(
        text=[text], videos=[video_input], padding=True, return_tensors="pt"
    ).to(DEVICE_STR)

    t0 = time.perf_counter()
    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            use_cache=True,
        )
    elapsed = time.perf_counter() - t0

    output_text = processor.tokenizer.batch_decode(
        out_ids, skip_special_tokens=True
    )[0]
    output_text = extract_assistant_response(output_text)

    return output_text, elapsed

# ── scoring wrapper ────────────────────────────────────────────────────────────

def score_task(pred_raw: str, gold_str: str) -> dict:
    gt_lists   = parse_list_string(gold_str)
    pred_lists = parse_list_string(pred_raw)
    parse_ok   = bool(pred_lists)
    if not gt_lists or not pred_lists:
        rm = 0.0
    else:
        rm = calculate_relaxed_match(pred_lists, gt_lists)
    return {"relaxed_match": rm, "parse_ok": parse_ok,
            "pred_lists": pred_lists, "gt_lists": gt_lists}

# ── data selection ─────────────────────────────────────────────────────────────

def select_tasks(ds, n_episodes: int, max_per_cat: int) -> list:
    """
    For each episode (up to n_episodes), pick up to max_per_cat valid tasks
    from EACH target category separately (not mixed). Skips [-1] golds.
    """
    by_ep_cat: dict = {}
    for row in ds:
        cat = row["high_level_category"]
        if cat not in TARGET_CATS:
            continue
        if not is_valid_gold(row["answer"]):
            continue
        ep = row["ep_id"]
        key = (ep, cat)
        by_ep_cat.setdefault(key, []).append(row)

    selected  = []
    ep_counts: dict = {}   # ep_id → count of episodes used for that ep
    for (ep_id, cat), rows in sorted(by_ep_cat.items()):
        ep_counts.setdefault(ep_id, 0)
        if ep_counts[ep_id] >= n_episodes:
            continue
        mp4 = DATA_DIR / "val" / f"{ep_id}.mp4"
        if not mp4.exists():
            continue
        for row in rows[:max_per_cat]:
            row = dict(row)
            row["_mp4"]  = str(mp4)
            row["_cat"]  = cat
            selected.append(row)
        ep_counts[ep_id] += 1

    return selected


def select_tasks_balanced(ds, n_ep_per_cat: int, max_per_cat: int = 1) -> list:
    """
    Collect exactly n_ep_per_cat episodes per category.
    Each episode contributes max_per_cat tasks of that category.
    """
    ep_seen: dict = {}   # cat → set of ep_ids already picked
    for cat in TARGET_CATS:
        ep_seen[cat] = set()

    by_ep_cat: dict = {}
    for row in ds:
        cat = row["high_level_category"]
        if cat not in TARGET_CATS:
            continue
        if not is_valid_gold(row["answer"]):
            continue
        ep = row["ep_id"]
        by_ep_cat.setdefault((ep, cat), []).append(row)

    selected = []
    for (ep_id, cat), rows in sorted(by_ep_cat.items()):
        if len(ep_seen[cat]) >= n_ep_per_cat:
            continue
        mp4 = DATA_DIR / "val" / f"{ep_id}.mp4"
        if not mp4.exists():
            continue
        ep_seen[cat].add(ep_id)
        for row in rows[:max_per_cat]:
            row = dict(row)
            row["_mp4"] = str(mp4)
            row["_cat"] = cat
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

# ── reporting helpers ──────────────────────────────────────────────────────────

def aggregate(records: list, budgets_list: list) -> dict:
    by_bcat_rm:  dict = {}
    for r in records:
        for bcat in [(r["budget"], "overall"), (r["budget"], r["hl_cat"])]:
            by_bcat_rm.setdefault(bcat, []).append(r["relaxed_match"])

    summary = {}
    for budget in budgets_list:
        summary[str(budget)] = {}
        for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            rm_vals = by_bcat_rm.get((budget, cat), [])
            if rm_vals:
                n   = len(rm_vals)
                mu  = float(np.mean(rm_vals))
                ci  = 1.96 * float(np.std(rm_vals, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
                summary[str(budget)][cat] = {"relaxed_match": round(mu, 4),
                                              "ci95": round(ci, 4), "n": n}
    return summary


def partition_summary(records: list, budgets_list: list, cat_filter=None) -> dict:
    """Aggregate separately for REASONING (gold_survived>=1) and REMOVED (==0)."""
    out = {}
    for part_name, pred in [("reasoning", lambda r: r["gold_survived"] >= 1),
                              ("removed",   lambda r: r["gold_survived"] == 0)]:
        subset = [r for r in records if pred(r)]
        if cat_filter:
            subset = [r for r in subset if r["hl_cat"] == cat_filter]
        out[part_name] = {}
        for budget in budgets_list:
            sub_b = [r for r in subset if r["budget"] == budget]
            if not sub_b:
                continue
            mu = float(np.mean([r["relaxed_match"] for r in sub_b]))
            n  = len(sub_b)
            ci = 1.96 * float(np.std([r["relaxed_match"] for r in sub_b], ddof=1) / np.sqrt(n)) if n > 1 else 0.0
            out[part_name][str(budget)] = {"relaxed_match": round(mu, 4), "ci95": round(ci, 4), "n": n}
    return out

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_ep_per_cat", type=int, default=30,
                        help="Episodes per category (temporal, multi-goal) for the sweep")
    parser.add_argument("--max_per_cat",  type=int, default=1,
                        help="Tasks per category per episode")
    parser.add_argument("--gate_only",    action="store_true",
                        help="Step 2: run budget=96 only, then stop and report")
    parser.add_argument("--device",       default="nvidia_rtx_a6000")
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)

    print("Loading FindingDory validation split...")
    ds = load_dataset("yali30/findingdory-subsampled-96", split="validation")

    budgets = [96] if args.gate_only else BUDGETS

    print(f"Selecting tasks: {args.n_ep_per_cat} episodes per category, "
          f"{args.max_per_cat} task(s) per category per episode...")
    tasks = select_tasks_balanced(ds, args.n_ep_per_cat, args.max_per_cat)

    cat_counts: dict = {}
    for t in tasks:
        cat_counts[t["_cat"]] = cat_counts.get(t["_cat"], 0) + 1
    print(f"Total tasks selected: {len(tasks)}")
    print("Category breakdown:", cat_counts)
    print()

    print(f"Loading {MODEL_ID}...")
    model = AutoModelForVision2Seq.from_pretrained(
        MODEL_ID,
        dtype=torch.bfloat16,
        device_map=DEVICE_STR,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(BASE_MODEL_ID)
    print("Model ready.\n")

    ckpt    = load_ckpt()
    records = []

    total = len(tasks) * len(budgets)
    done  = 0

    for task in tasks:
        ep_id    = task["ep_id"]
        task_id  = task["task_id"]
        mp4      = Path(task["_mp4"])
        question = task["question"]
        gold_str = task["answer"]
        hl_cat   = task["high_level_category"]
        ll_cat   = task["low_level_category"]

        if not mp4.exists():
            print(f"  SKIP {ep_id}/{task_id} — mp4 not found")
            continue

        all_frames = extract_frames(mp4, n=96)
        if len(all_frames) < 6:
            print(f"  SKIP {ep_id}/{task_id} — only {len(all_frames)} frames")
            continue

        gold_pos = gold_mp4_positions(gold_str)

        for budget in budgets:
            ck_key = f"{ep_id}_{task_id}_b{budget}_v2"
            done  += 1

            if ck_key in ckpt:
                records.append(ckpt[ck_key])
                r = ckpt[ck_key]
                print(f"  [{done}/{total}] {ck_key} (cached) "
                      f"rm={r['relaxed_match']:.3f} survived={r['gold_survived']}")
                continue

            frames_k, kept_idx = subsample(all_frames, budget)
            gold_survived = len(gold_pos & set(kept_idx))

            raw, elapsed = run_inference(model, processor, frames_k, question)
            scored = score_task(raw, gold_str)

            rec = {
                "ep_id":          ep_id,
                "task_id":        task_id,
                "budget":         budget,
                "relaxed_match":  scored["relaxed_match"],
                "parse_ok":       scored["parse_ok"],
                "hl_cat":         hl_cat,
                "ll_cat":         ll_cat,
                "gold_survived":  gold_survived,
                "gold_n_frames":  len(gold_pos),
                "kept_n":         len(kept_idx),
                "gold":           gold_str,
                "pred_raw":       raw,
                "pred_lists":     scored["pred_lists"],
                "gt_lists":       scored["gt_lists"],
                "elapsed_s":      round(elapsed, 3),
            }
            ckpt[ck_key] = rec
            save_ckpt(ckpt)
            records.append(rec)

            print(f"  [{done}/{total}] {ck_key}  rm={scored['relaxed_match']:.3f}  "
                  f"survived={gold_survived}/{len(gold_pos)}  "
                  f"pred={raw[:50]!r}  {elapsed:.1f}s")

    # ── gate check ────────────────────────────────────────────────────────────
    recs96 = [r for r in records if r["budget"] == 96]
    if recs96:
        rm96  = float(np.mean([r["relaxed_match"] for r in recs96]))
        n_ok  = sum(r["parse_ok"] for r in recs96)
        print(f"\n{'='*70}")
        print("STEP 2 GATE — budget=96 (full context)")
        print(f"  n={len(recs96)}  relaxed_match={rm96:.3f}  parse_ok={n_ok}/{len(recs96)}")
        print(f"  (authors' Habitat HL-SR ~52.4%; text relaxed_match expected lower)")
        for cat in ["Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            sub = [r for r in recs96 if r["hl_cat"] == cat]
            if sub:
                print(f"  {cat[:35]}: rm={np.mean([r['relaxed_match'] for r in sub]):.3f}  n={len(sub)}")
        if args.gate_only:
            print("\nGate-only run complete. Inspect rm96 before proceeding to sweep.")
            print(f"  If rm96 is near 0.0 → harness is still wrong; do NOT run sweep.")
            print(f"  If rm96 is 0.1–0.4 → text metric is lower than HL-SR; proceed.")
            return

    if not recs96 or args.gate_only:
        return

    # ── full report ───────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("FINDINGDORY v2 FRAME-BUDGET FRONTIER — authors' relaxed_match metric")
    print(f"{'='*70}\n")

    print(f"{'budget':>8}  {'category':<40}  {'rm':>6}  {'ci95':>6}  {'n':>4}")
    print("-" * 68)
    for budget in BUDGETS:
        for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            sub = [r for r in records if r["budget"] == budget
                   and (cat == "overall" or r["hl_cat"] == cat)]
            if not sub:
                continue
            mu  = float(np.mean([r["relaxed_match"] for r in sub]))
            n   = len(sub)
            ci  = 1.96 * float(np.std([r["relaxed_match"] for r in sub], ddof=1) / np.sqrt(n)) if n > 1 else 0.0
            print(f"{budget:>8}  {cat:<40}  {mu:>6.3f}  ±{ci:>5.3f}  {n:>4}")

    print(f"\n{'='*70}")
    print("REASONING vs REMOVED partition (gold_survived ≥ 1 vs = 0)")
    print(f"{'='*70}")
    for cat in ["Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
        print(f"\n  {cat}")
        for part_name, pred in [("REASONING (gold in input)", lambda r: r["gold_survived"] >= 1),
                                  ("REMOVED (gold deleted)",    lambda r: r["gold_survived"] == 0)]:
            print(f"    {part_name}:")
            for budget in BUDGETS:
                sub = [r for r in records if r["budget"] == budget
                       and r["hl_cat"] == cat and pred(r)]
                if not sub:
                    continue
                mu = float(np.mean([r["relaxed_match"] for r in sub]))
                n  = len(sub)
                ci = 1.96 * float(np.std([r["relaxed_match"] for r in sub], ddof=1) / np.sqrt(n)) if n > 1 else 0.0
                print(f"      b={budget:>2}: rm={mu:.3f} ±{ci:.3f}  n={n}")

    # gold survival fractions per budget
    print(f"\n{'='*70}")
    print("GOLD SURVIVAL: fraction of tasks where gold mp4 positions are in input")
    print(f"{'budget':>8}  {'overall':>10}  {'temporal':>10}  {'multi-goal':>12}")
    print("-" * 46)
    for budget in BUDGETS:
        for_cat = {}
        for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
            sub = [r for r in records if r["budget"] == budget
                   and (cat == "overall" or r["hl_cat"] == cat)]
            if sub:
                for_cat[cat] = sum(r["gold_survived"] >= 1 for r in sub) / len(sub)
        print(f"{budget:>8}  {for_cat.get('overall', 0):>10.3f}  "
              f"{for_cat.get('Single-Goal Temporal Tasks', 0):>10.3f}  "
              f"{for_cat.get('Multi-Goal Tasks', 0):>12.3f}")

    # ── write output JSON ─────────────────────────────────────────────────────
    summary  = aggregate(records, BUDGETS)
    prov     = stamp(script="frontier_findingdory_v2.py", model="qwenvl3b",
                     device=args.device, n=len(records), args=args)

    # Build full partition summary
    partition = {}
    for cat in ["overall", "Single-Goal Temporal Tasks", "Multi-Goal Tasks"]:
        cat_records = records if cat == "overall" else [r for r in records if r["hl_cat"] == cat]
        partition[cat] = partition_summary(cat_records, BUDGETS)

    out = {
        "summary_by_budget_category": summary,
        "reasoning_vs_removed":       partition,
        "records":                    records,
        "_provenance":                prov,
    }
    out_path = RESULTS / "frontier_findingdory_qwenvl3b.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
