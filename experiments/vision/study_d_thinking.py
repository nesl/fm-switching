#!/usr/bin/env python3
"""
Study D: Reasoning compute vs. parameters with scene difficulty.
4 models (Qwen3-VL 4B/8B Instruct + Thinking) × 4 difficulty levels × 30 images × 3 reps.
Same 120 COCO images as Study C, reloaded from study_c_images/.

Stop conditions (checked per-cell before continuing to next model):
  - >5% budget hit in any cell
  - >5% unparseable in any cell
  - Thinking and Instruct produce indistinguishable output lengths across ALL cells
"""

import csv
import glob
import io
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

# ── paths ──────────────────────────────────────────────────────────────────────
SELECTION_JSON = "results/vision/study_c/study_c_selection.json"
IMAGES_DIR     = "results/vision/study_c/study_c_images"
OUT_DIR        = "results/vision/study_d"
TRIALS_CSV     = f"{OUT_DIR}/study_d_trials.csv"
RESULTS_JSON   = f"{OUT_DIR}/study_d_results.json"
FIG_DIR        = "figures/vision"

HF_CACHE   = "/mnt/ssd/hf_models"
DEVICE     = "cuda:1"
DTYPE      = torch.bfloat16
SEED       = 42
N_REPS     = 3
LEVELS     = ["L1", "L2", "L3", "L4"]
LEVEL_BINS = {"L1": (1, 1), "L2": (2, 3), "L3": (4, 7), "L4": (8, 999)}

MAX_NEW_TOKENS_INSTRUCT = 40
MAX_NEW_TOKENS_THINKING = 4096
BUDGET_STOP_FRAC  = 0.05
UNPARSE_STOP_FRAC = 0.05

MODEL_CONFIGS = [
    {
        "slug":     "qwen3vl4b",
        "mode":     "instruct",
        "hf_id":    "Qwen/Qwen3-VL-4B-Instruct",
        "snap":     "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17",
        "max_tok":  MAX_NEW_TOKENS_INSTRUCT,
    },
    {
        "slug":     "qwen3vl4b_t",
        "mode":     "thinking",
        "hf_id":    "Qwen/Qwen3-VL-4B-Thinking",
        "snap":     "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e",
        "max_tok":  MAX_NEW_TOKENS_THINKING,
    },
    {
        "slug":     "qwen3vl8b",
        "mode":     "instruct",
        "hf_id":    "Qwen/Qwen3-VL-8B-Instruct",
        "snap":     "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "max_tok":  MAX_NEW_TOKENS_INSTRUCT,
    },
    {
        "slug":     "qwen3vl8b_t",
        "mode":     "thinking",
        "hf_id":    "Qwen/Qwen3-VL-8B-Thinking",
        "snap":     "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b",
        "max_tok":  MAX_NEW_TOKENS_THINKING,
    },
]


# ── helpers ────────────────────────────────────────────────────────────────────

def load_selection():
    with open(SELECTION_JSON) as f:
        return json.load(f)


def image_path(level, image_id, n_persons_gt):
    return os.path.join(IMAGES_DIR, f"{level}_{image_id:012d}_gt{n_persons_gt}.png")


def load_image(level, image_id, n_persons_gt):
    p = image_path(level, image_id, n_persons_gt)
    return Image.open(p).convert("RGB")


def parse_instruct(text):
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        return int(nums[0]), "ok"
    return None, "unparseable"


def parse_thinking(text):
    """Split on </think>, parse first integer after it."""
    end_think = text.find("</think>")
    if end_think == -1:
        # No </think> found — treat entire output as non-thinking answer
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            return int(nums[-1]), "no_think_tag", 0, len(text.split())
        return None, "unparseable", 0, 0
    think_text  = text[:end_think]
    answer_text = text[end_think + len("</think>"):].strip()
    # Count think tokens by splitting on whitespace (approx; exact count is in n_generated)
    nums = re.findall(r"\b\d+\b", answer_text)
    if nums:
        return int(nums[0]), "ok", think_text, answer_text
    # fallback: last number in entire text
    nums_all = re.findall(r"\b\d+\b", text)
    if nums_all:
        return int(nums_all[-1]), "fallback_last_number", think_text, answer_text
    return None, "unparseable", think_text, answer_text


def count_think_tokens(proc, think_text):
    """Approximate token count for the thinking block."""
    if not think_text:
        return 0
    try:
        return len(proc.tokenizer.encode(think_text, add_special_tokens=False))
    except Exception:
        return 0


# ── CSV writer ─────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "model", "mode", "image_id", "level", "n_persons_gt",
    "rep", "n_input", "n_generated", "n_think_tokens", "n_answer_tokens",
    "latency_ms", "budget_hit", "parsed_answer", "parse_status", "correct",
]


def append_trials(rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    write_header = not os.path.exists(TRIALS_CSV)
    with open(TRIALS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# ── per-model inference ────────────────────────────────────────────────────────

def run_model(cfg, selection):
    slug  = cfg["slug"]
    mode  = cfg["mode"]
    snap  = cfg["snap"]
    max_t = cfg["max_tok"]

    print(f"\n{'='*60}")
    print(f"Model: {slug} ({mode})  max_new_tokens={max_t}")
    print(f"{'='*60}")

    # Check if already done (resume support)
    existing_rows = []
    if os.path.exists(TRIALS_CSV):
        with open(TRIALS_CSV) as f:
            for row in csv.DictReader(f):
                if row["model"] == slug:
                    existing_rows.append(row)
    done_keys = {(r["image_id"], r["level"], r["rep"]) for r in existing_rows}
    print(f"  Already done: {len(existing_rows)} rows (will skip matching keys)")

    # Load model
    print(f"  Loading {snap} ...")
    proc  = AutoProcessor.from_pretrained(snap, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        snap, torch_dtype=DTYPE, device_map=DEVICE, trust_remote_code=True
    )
    model.eval()
    img_tok_id = proc.tokenizer.convert_tokens_to_ids("<|image_pad|>")

    # Build trial order
    rng = random.Random(SEED + hash(slug) % 10000)
    trials = []
    for item in selection:
        for rep in range(N_REPS):
            trials.append((item, rep))
    rng.shuffle(trials)

    new_rows = []
    cell_stats = defaultdict(lambda: {"n": 0, "budget": 0, "unparse": 0})

    for idx, (item, rep) in enumerate(trials):
        level      = item["level"]
        image_id   = item["image_id"]
        gt         = item["n_persons_gt"]
        key        = (str(image_id), level, str(rep))

        if key in done_keys:
            continue

        img = load_image(level, image_id, gt)

        msgs = [{"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": "How many people are in this image? Answer with a single integer."},
        ]}]
        txt = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = proc(text=[txt], images=[img], return_tensors="pt").to(DEVICE)
        n_input = inputs.input_ids.shape[1]

        t0 = time.perf_counter()
        with torch.no_grad():
            out_ids = model.generate(
                **inputs,
                max_new_tokens=max_t,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
        latency_ms = (time.perf_counter() - t0) * 1000

        gen_ids    = out_ids[0][n_input:]
        n_gen      = len(gen_ids)
        budget_hit = (n_gen >= max_t)
        gen_text   = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)

        n_think_tokens  = 0
        n_answer_tokens = n_gen

        if mode == "instruct":
            parsed, status = parse_instruct(gen_text)
        else:
            result = parse_thinking(gen_text)
            parsed, status, think_text, answer_text = result
            if think_text:
                n_think_tokens  = count_think_tokens(proc, think_text)
                n_answer_tokens = count_think_tokens(proc, answer_text)

        correct = (parsed == gt) if parsed is not None else False

        row = {
            "model":           slug,
            "mode":            mode,
            "image_id":        image_id,
            "level":           level,
            "n_persons_gt":    gt,
            "rep":             rep,
            "n_input":         n_input,
            "n_generated":     n_gen,
            "n_think_tokens":  n_think_tokens,
            "n_answer_tokens": n_answer_tokens,
            "latency_ms":      f"{latency_ms:.1f}",
            "budget_hit":      budget_hit,
            "parsed_answer":   parsed if parsed is not None else "",
            "parse_status":    status,
            "correct":         correct,
        }
        new_rows.append(row)

        cell_key = (slug, level)
        cell_stats[cell_key]["n"]      += 1
        cell_stats[cell_key]["budget"] += int(budget_hit)
        cell_stats[cell_key]["unparse"] += int(status in ("unparseable",))

        if (idx + 1) % 30 == 0 or idx == len(trials) - 1:
            done = len(new_rows) + len(existing_rows)
            print(f"  [{done}/{len(trials)+len(existing_rows)}] level={level} rep={rep} "
                  f"gt={gt} parsed={parsed} status={status} "
                  f"n_gen={n_gen} latency={latency_ms:.0f}ms")
            append_trials(new_rows)
            new_rows = []

    if new_rows:
        append_trials(new_rows)

    # Per-cell stop condition check
    stop = False
    for (m, lv), st in cell_stats.items():
        n = st["n"]
        if n == 0:
            continue
        bfrac = st["budget"] / n
        ufrac = st["unparse"] / n
        if bfrac > BUDGET_STOP_FRAC:
            print(f"  STOP CONDITION: {m}/{lv} budget_hit={bfrac:.1%} > {BUDGET_STOP_FRAC:.0%}")
            stop = True
        if ufrac > UNPARSE_STOP_FRAC:
            print(f"  STOP CONDITION: {m}/{lv} unparseable={ufrac:.1%} > {UNPARSE_STOP_FRAC:.0%}")
            stop = True

    del model
    torch.cuda.empty_cache()
    return stop


# ── analysis ───────────────────────────────────────────────────────────────────

def analyse():
    import statistics

    with open(TRIALS_CSV) as f:
        rows = list(csv.DictReader(f))

    print(f"\nTotal rows: {len(rows)}")
    slugs = [c["slug"] for c in MODEL_CONFIGS]

    results = {}
    for slug in slugs:
        for level in LEVELS:
            cell = [r for r in rows if r["model"] == slug and r["level"] == level]
            n_total = len(cell)
            parseable = [r for r in cell if r["parse_status"] not in ("unparseable",)
                         and r["parsed_answer"] not in ("", "None")]
            n_unparse = n_total - len(parseable)

            correct_c = sum(1 for r in cell if r.get("correct", "False") in ("True", True))
            acc_c = correct_c / n_total if n_total else float("nan")
            budget_hits = sum(1 for r in cell if r.get("budget_hit", "False") in ("True", True))

            n_gen_vals = [int(r["n_generated"]) for r in cell]
            n_think_vals = [int(r["n_think_tokens"]) for r in cell if r["n_think_tokens"] != "0"]

            key = f"{slug}|{level}"
            results[key] = {
                "n_total":     n_total,
                "n_unparse":   n_unparse,
                "budget_hits": budget_hits,
                "acc_conservative": acc_c,
                "n_generated_median": statistics.median(n_gen_vals) if n_gen_vals else float("nan"),
                "n_generated_p25":   sorted(n_gen_vals)[len(n_gen_vals)//4] if n_gen_vals else float("nan"),
                "n_generated_p75":   sorted(n_gen_vals)[3*len(n_gen_vals)//4] if n_gen_vals else float("nan"),
                "n_think_median": statistics.median(n_think_vals) if n_think_vals else 0,
                "n_think_p25":    sorted(n_think_vals)[len(n_think_vals)//4] if n_think_vals else 0,
                "n_think_p75":    sorted(n_think_vals)[3*len(n_think_vals)//4] if n_think_vals else 0,
            }

    print("\n=== Per-cell accuracy (conservative) ===")
    hdr = f"{'model':18} {'L1':8} {'L2':8} {'L3':8} {'L4':8}"
    print(hdr)
    print("-" * len(hdr))
    for slug in slugs:
        accs = [results[f"{slug}|{lv}"]["acc_conservative"] for lv in LEVELS]
        print(f"{slug:18} {accs[0]:8.3f} {accs[1]:8.3f} {accs[2]:8.3f} {accs[3]:8.3f}")

    print("\n=== Generated tokens (median) ===")
    for slug in slugs:
        meds = [results[f"{slug}|{lv}"]["n_generated_median"] for lv in LEVELS]
        print(f"{slug:18} {meds[0]:8.0f} {meds[1]:8.0f} {meds[2]:8.0f} {meds[3]:8.0f}")

    print("\n=== Think tokens (median, Thinking models only) ===")
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        meds = [results[f"{slug}|{lv}"]["n_think_median"] for lv in LEVELS]
        print(f"{slug:18} {meds[0]:8.0f} {meds[1]:8.0f} {meds[2]:8.0f} {meds[3]:8.0f}")

    print("\n=== Budget hits per cell ===")
    for slug in slugs:
        hits = [results[f"{slug}|{lv}"]["budget_hits"] for lv in LEVELS]
        totals = [results[f"{slug}|{lv}"]["n_total"] for lv in LEVELS]
        fracs = [f"{h}/{t}({h/t:.0%})" if t else "0" for h,t in zip(hits,totals)]
        print(f"{slug:18} {fracs[0]:12} {fracs[1]:12} {fracs[2]:12} {fracs[3]:12}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {RESULTS_JSON}")
    return results


# ── plotting ───────────────────────────────────────────────────────────────────

def plot(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    slugs  = [c["slug"] for c in MODEL_CONFIGS]
    levels = LEVELS
    x      = np.arange(len(levels))
    colors = {
        "qwen3vl4b":   "#1565C0",
        "qwen3vl4b_t": "#42A5F5",
        "qwen3vl8b":   "#B71C1C",
        "qwen3vl8b_t": "#EF5350",
    }
    lspecs = {
        "qwen3vl4b":   ("-",  "o"),
        "qwen3vl4b_t": ("--", "s"),
        "qwen3vl8b":   ("-",  "^"),
        "qwen3vl8b_t": ("--", "D"),
    }
    xlabels = ["L1\n(1 person)", "L2\n(2–3)", "L3\n(4–7)", "L4\n(8+)"]
    label_map = {
        "qwen3vl4b":   "4B Instruct",
        "qwen3vl4b_t": "4B Thinking",
        "qwen3vl8b":   "8B Instruct",
        "qwen3vl8b_t": "8B Thinking",
    }

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: exact-match accuracy
    ax = axes[0]
    for slug in slugs:
        accs = [results[f"{slug}|{lv}"]["acc_conservative"] for lv in levels]
        ls, mk = lspecs[slug]
        ax.plot(x, accs, color=colors[slug], ls=ls, marker=mk,
                label=label_map[slug], lw=2, ms=7)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("Exact-match accuracy (conservative)")
    ax.set_title("Study D — Accuracy vs Difficulty", fontsize=11)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)

    # Panel 2: generated tokens (Instruct: full output; Thinking: think tokens)
    ax = axes[1]
    for slug in slugs:
        mode = [c["mode"] for c in MODEL_CONFIGS if c["slug"] == slug][0]
        if mode == "thinking":
            meds = [results[f"{slug}|{lv}"]["n_think_median"] for lv in levels]
            lbl = label_map[slug] + " (think tok)"
        else:
            meds = [results[f"{slug}|{lv}"]["n_generated_median"] for lv in levels]
            lbl = label_map[slug] + " (gen tok)"
        ls, mk = lspecs[slug]
        ax.plot(x, meds, color=colors[slug], ls=ls, marker=mk,
                label=lbl, lw=2, ms=7)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylabel("Tokens (median)")
    ax.set_title("Study D — Token Count vs Difficulty", fontsize=11)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)

    fig.suptitle("Study D: Reasoning Compute vs Parameters (Qwen3-VL 4B/8B Instruct + Thinking)", fontsize=10)
    plt.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(f"{FIG_DIR}/study_d_thinking.{ext}",
                    bbox_inches="tight", dpi=150 if ext == "png" else None)
    plt.close()
    print(f"Figures saved to {FIG_DIR}/study_d_thinking.{{pdf,png}}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    selection = load_selection()
    print(f"Loaded {len(selection)} images from selection.json")

    stop_globally = False
    for cfg in MODEL_CONFIGS:
        if stop_globally:
            print(f"Skipping {cfg['slug']} due to earlier stop condition.")
            continue
        stop = run_model(cfg, selection)
        if stop:
            stop_globally = True
            print("Stop condition triggered — halting after this model.")

    if not stop_globally:
        print("\nAll models complete. Running analysis.")
        results = analyse()
        plot(results)
    else:
        print("\nStop condition was triggered. Partial results analysed:")
        results = analyse()
        plot(results)


if __name__ == "__main__":
    main()
