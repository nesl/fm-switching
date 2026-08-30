"""
Study C: Does the 3B-vs-7B accuracy gap on object counting widen with scene difficulty?

Data source: COCO val2017 via HuggingFace (detection-datasets/coco), person category.
Difficulty axis: annotated person count (L1=1, L2=2-3, L3=4-7, L4=8+).
Resolution: all images resized to 560×560 → constant input token count (400 vision tokens).

RQ1: Does generated token count scale with difficulty?
RQ2: Does the accuracy gap between 3B and 7B widen with difficulty?
RQ3: Does step-by-step reasoning on 3B close the gap to 7B?
"""

import argparse
import csv
import io
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import PIL.Image
import torch
import numpy as np

SEED = 42
DEVICE = "cuda:1"
DTYPE = torch.bfloat16
TARGET_SIZE = (560, 560)
N_PER_LEVEL = 30
N_REPS = 3
MAX_NEW_TOKENS_DIRECT = 30
MAX_NEW_TOKENS_STEPWISE = 512
BUDGET_HIT_THRESHOLD = 0.05  # stop if >5% of any cell hits budget

DIFFICULTY_LEVELS = {
    "L1": (1, 1),
    "L2": (2, 3),
    "L3": (4, 7),
    "L4": (8, 999),
}

MODELS = {
    "qwenvl7b": "Qwen/Qwen2.5-VL-7B-Instruct",
    "qwenvl3b": "Qwen/Qwen2.5-VL-3B-Instruct",
}

DIRECT_PROMPT = (
    "How many people are in this image? "
    "Answer with a single integer only. Do not explain."
)

STEPWISE_PROMPT = (
    "How many people are in this image? "
    "Think step by step: describe each person you can see. "
    "Then give your final answer on its own line starting exactly with "
    "'Final answer:' followed by the number. Example: Final answer: 3"
)

RESULTS_DIR = Path(__file__).parent.parent.parent / "results" / "vision" / "study_c"
IMAGES_DIR = RESULTS_DIR / "study_c_images"
FIGURES_DIR = Path(__file__).parent.parent.parent / "figures" / "vision"


def load_coco_person_images(n_per_level: int, seed: int) -> list[dict]:
    """Load COCO val images, select n_per_level per difficulty level."""
    import datasets
    from datasets import Image as HFImage

    print("Loading COCO val metadata (no image decode)...", flush=True)
    ds = datasets.load_dataset("detection-datasets/coco", split="val", streaming=True)
    ds = ds.cast_column("image", HFImage(decode=False))

    cat_feat = ds.features["objects"]["category"].feature
    person_idx = cat_feat.names.index("person")
    print(f"Person category index: {person_idx}", flush=True)

    buckets: dict[str, list[dict]] = {lvl: [] for lvl in DIFFICULTY_LEVELS}

    for i, ex in enumerate(ds):
        cats = ex["objects"]["category"]
        n_persons = sum(1 for c in cats if c == person_idx)
        for lvl, (lo, hi) in DIFFICULTY_LEVELS.items():
            if lo <= n_persons <= hi:
                buckets[lvl].append({
                    "image_id": ex["image_id"],
                    "n_persons_gt": n_persons,
                    "level": lvl,
                    "width": ex["width"],
                    "height": ex["height"],
                    "image_bytes": ex["image"]["bytes"],
                })
                break
        if i % 1000 == 0:
            print(f"  scanned {i} images...", flush=True)

    rng = random.Random(seed)
    selected = []
    for lvl, items in buckets.items():
        rng.shuffle(items)
        chosen = items[:n_per_level]
        print(f"  {lvl}: {len(items)} available → {len(chosen)} selected "
              f"(person range {DIFFICULTY_LEVELS[lvl]}, counts: {[x['n_persons_gt'] for x in chosen[:5]]}...)",
              flush=True)
        selected.extend(chosen)

    return selected


def save_images(images: list[dict], out_dir: Path):
    """Save selected images as PNGs for inspection. Returns per-image resized PIL images."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pil_cache = {}
    for item in images:
        img_id = item["image_id"]
        lvl = item["level"]
        n_gt = item["n_persons_gt"]
        raw = PIL.Image.open(io.BytesIO(item["image_bytes"])).convert("RGB")
        resized = raw.resize(TARGET_SIZE, PIL.Image.LANCZOS)
        fname = out_dir / f"{lvl}_{img_id:012d}_gt{n_gt}.png"
        if not fname.exists():
            resized.save(str(fname))
        pil_cache[img_id] = resized
    print(f"Saved {len(images)} images to {out_dir}", flush=True)
    return pil_cache


def verify_input_tokens(model, processor, pil_cache: dict, images: list[dict]) -> dict:
    """Verify that input token count is identical across difficulty levels."""
    token_counts = {}
    for item in images[:4]:
        img_id = item["image_id"]
        img = pil_cache[img_id]
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": DIRECT_PROMPT},
            ],
        }]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[img], return_tensors="pt")
        n_input = inputs["input_ids"].shape[1]
        token_counts[img_id] = n_input

    unique_counts = set(token_counts.values())
    print(f"Input token count verification: unique counts = {unique_counts}", flush=True)
    return token_counts


def parse_direct(text: str) -> tuple[int | None, str]:
    """Extract first integer from a direct-mode response."""
    text = text.strip()
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        return int(nums[0]), "ok"
    return None, "no_number"


def parse_stepwise(text: str) -> tuple[int | None, str]:
    """Extract number from 'Final answer: N' line."""
    text = text.strip()
    m = re.search(r"(?i)final\s+answer\s*[:：]\s*(\d+)", text)
    if m:
        return int(m.group(1)), "ok"
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        return int(nums[-1]), "fallback_last_number"
    return None, "unparseable"


def run_trial(model, processor, img: PIL.Image.Image, prompt: str,
              max_new_tokens: int, mode: str) -> dict:
    """Run one generation trial. Returns dict with latency, n_generated, raw_text."""
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": prompt},
        ],
    }]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[img], return_tensors="pt")
    inputs = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
    n_input = inputs["input_ids"].shape[1]

    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    torch.cuda.synchronize(DEVICE)
    t1 = time.perf_counter()

    gen_ids = out[0][n_input:]
    n_generated = len(gen_ids)
    raw_text = processor.decode(gen_ids, skip_special_tokens=True)
    latency_ms = (t1 - t0) * 1000.0
    budget_hit = n_generated >= max_new_tokens

    return {
        "n_input": n_input,
        "n_generated": n_generated,
        "latency_ms": latency_ms,
        "raw_text": raw_text,
        "budget_hit": budget_hit,
    }


def run_model(model_slug: str, model_id: str, images: list[dict],
              pil_cache: dict, trials_csv_path: Path,
              existing_trial_keys: set) -> list[dict]:
    """Load model, run all trials in randomized order, return trial records."""
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

    print(f"\n{'='*60}", flush=True)
    print(f"Loading {model_slug} ({model_id})...", flush=True)

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=DTYPE,
        device_map=DEVICE,
        trust_remote_code=True,
    )
    model.eval()

    # Verify device placement
    param_device = next(model.parameters()).device
    print(f"Model device: {param_device}", flush=True)
    assert str(param_device) == DEVICE, f"Model not on {DEVICE}: {param_device}"

    # Verify input token count consistency
    sample_items = images[:8]
    token_counts = verify_input_tokens(model, processor, pil_cache, sample_items)
    unique_counts = set(token_counts.values())
    assert len(unique_counts) == 1, f"Input token count varies: {unique_counts}"
    n_input_canonical = list(unique_counts)[0]
    print(f"Input token count (canonical): {n_input_canonical}", flush=True)

    # Build trial list: (image_id, level, n_gt, mode, rep)
    trial_specs = []
    for item in images:
        for mode in ["direct", "stepwise"]:
            for rep in range(N_REPS):
                key = (model_slug, item["image_id"], mode, rep)
                if key not in existing_trial_keys:
                    trial_specs.append({
                        "model": model_slug,
                        "image_id": item["image_id"],
                        "level": item["level"],
                        "n_persons_gt": item["n_persons_gt"],
                        "mode": mode,
                        "rep": rep,
                    })

    # Randomize order (fixed seed includes model slug so different per model)
    rng = random.Random(SEED + hash(model_slug) % 10000)
    rng.shuffle(trial_specs)
    print(f"Trials to run: {len(trial_specs)}", flush=True)

    # Warmup
    print("Warmup run...", flush=True)
    warmup_item = images[0]
    warmup_img = pil_cache[warmup_item["image_id"]]
    run_trial(model, processor, warmup_img, DIRECT_PROMPT, MAX_NEW_TOKENS_DIRECT, "direct")

    records = []
    csv_header = [
        "model", "image_id", "level", "n_persons_gt", "mode", "rep",
        "n_input", "n_generated", "latency_ms", "budget_hit",
        "parsed_answer", "parse_status", "correct",
    ]
    write_header = not trials_csv_path.exists()
    csv_file = open(trials_csv_path, "a", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=csv_header)
    if write_header:
        writer.writeheader()

    try:
        for i, spec in enumerate(trial_specs):
            img_id = spec["image_id"]
            mode = spec["mode"]
            n_gt = spec["n_persons_gt"]

            img = pil_cache[img_id]
            prompt = DIRECT_PROMPT if mode == "direct" else STEPWISE_PROMPT
            max_tok = MAX_NEW_TOKENS_DIRECT if mode == "direct" else MAX_NEW_TOKENS_STEPWISE

            result = run_trial(model, processor, img, prompt, max_tok, mode)

            if mode == "direct":
                parsed, parse_status = parse_direct(result["raw_text"])
            else:
                parsed, parse_status = parse_stepwise(result["raw_text"])

            correct = (parsed == n_gt) if parsed is not None else None

            row = {
                "model": model_slug,
                "image_id": img_id,
                "level": spec["level"],
                "n_persons_gt": n_gt,
                "mode": mode,
                "rep": spec["rep"],
                "n_input": result["n_input"],
                "n_generated": result["n_generated"],
                "latency_ms": round(result["latency_ms"], 1),
                "budget_hit": result["budget_hit"],
                "parsed_answer": parsed,
                "parse_status": parse_status,
                "correct": correct,
            }
            writer.writerow(row)
            csv_file.flush()

            records.append({**row, "raw_text": result["raw_text"]})

            if (i + 1) % 50 == 0:
                print(f"  [{model_slug}] {i+1}/{len(trial_specs)} done", flush=True)
    finally:
        csv_file.close()

    del model
    torch.cuda.empty_cache()
    return records


def analyse(all_records: list[dict]) -> dict:
    """Compute per-cell summary statistics."""
    from statistics import median

    cells: dict[tuple, list] = {}
    for r in all_records:
        key = (r["model"], r["mode"], r["level"])
        cells.setdefault(key, []).append(r)

    summary = {}
    for (model, mode, level), recs in cells.items():
        n_total = len(recs)
        n_budget_hit = sum(1 for r in recs if r["budget_hit"])
        budget_hit_frac = n_budget_hit / n_total if n_total else 0.0

        parsed_recs = [r for r in recs if r["parsed_answer"] is not None]
        unparseable_frac = (n_total - len(parsed_recs)) / n_total if n_total else 0.0

        accuracy = sum(1 for r in parsed_recs if r.get("correct")) / len(parsed_recs) if parsed_recs else 0.0

        gen_tokens = [r["n_generated"] for r in recs]
        latencies = [r["latency_ms"] for r in recs]
        n_inputs = [r["n_input"] for r in recs]

        key_str = f"{model}|{mode}|{level}"
        summary[key_str] = {
            "model": model, "mode": mode, "level": level,
            "n_trials": n_total,
            "n_images": len(set(r["image_id"] for r in recs)),
            "accuracy": round(accuracy, 4),
            "budget_hit_frac": round(budget_hit_frac, 4),
            "unparseable_frac": round(unparseable_frac, 4),
            "n_generated_median": median(gen_tokens),
            "n_generated_min": min(gen_tokens),
            "n_generated_max": max(gen_tokens),
            "n_generated_p25": float(np.percentile(gen_tokens, 25)),
            "n_generated_p75": float(np.percentile(gen_tokens, 75)),
            "latency_ms_median": round(median(latencies), 1),
            "n_input_unique": list(set(n_inputs)),
        }

    return summary


def check_budget_hits(summary: dict) -> list[str]:
    """Return list of cells where >5% of trials hit the generation budget."""
    violations = []
    for key, cell in summary.items():
        if cell["budget_hit_frac"] > BUDGET_HIT_THRESHOLD:
            violations.append(
                f"{key}: {cell['budget_hit_frac']:.1%} budget hit "
                f"({cell['mode']}, {cell['level']})"
            )
    return violations


def check_length_separation(summary: dict) -> list[str]:
    """Check that step-by-step generates substantially more tokens than direct."""
    issues = []
    models = set(v["model"] for v in summary.values())
    levels = set(v["level"] for v in summary.values())
    for model in models:
        for level in levels:
            k_direct = f"{model}|direct|{level}"
            k_step = f"{model}|stepwise|{level}"
            if k_direct in summary and k_step in summary:
                direct_med = summary[k_direct]["n_generated_median"]
                step_med = summary[k_step]["n_generated_median"]
                if step_med <= direct_med * 1.5:
                    issues.append(
                        f"{model}/{level}: stepwise={step_med} tokens vs "
                        f"direct={direct_med} tokens — not substantially longer"
                    )
    return issues


def plot_results(summary: dict, out_dir: Path):
    """Generate accuracy vs difficulty and token count vs difficulty plots."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    levels = ["L1", "L2", "L3", "L4"]
    level_labels = ["L1 (1 person)", "L2 (2-3)", "L3 (4-7)", "L4 (8+)"]
    x = range(len(levels))

    conditions = [
        ("qwenvl3b", "direct", "3B direct", "C0", "o", "-"),
        ("qwenvl3b", "stepwise", "3B step-by-step", "C0", "s", "--"),
        ("qwenvl7b", "direct", "7B direct", "C1", "o", "-"),
        ("qwenvl7b", "stepwise", "7B step-by-step", "C1", "s", "--"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Accuracy plot
    ax = axes[0]
    for model, mode, label, color, marker, ls in conditions:
        accs = [summary.get(f"{model}|{mode}|{lvl}", {}).get("accuracy", float("nan"))
                for lvl in levels]
        ax.plot(list(x), accs, marker=marker, linestyle=ls, color=color, label=label, linewidth=1.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(level_labels, fontsize=10)
    ax.set_ylabel("Accuracy (exact count match)", fontsize=11)
    ax.set_xlabel("Difficulty level", fontsize=11)
    ax.set_title("Accuracy vs Difficulty", fontsize=12)
    ax.legend(fontsize=9)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)

    # Token count plot
    ax = axes[1]
    for model, mode, label, color, marker, ls in conditions:
        toks = [summary.get(f"{model}|{mode}|{lvl}", {}).get("n_generated_median", float("nan"))
                for lvl in levels]
        ax.plot(list(x), toks, marker=marker, linestyle=ls, color=color, label=label, linewidth=1.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(level_labels, fontsize=10)
    ax.set_ylabel("Median generated tokens", fontsize=11)
    ax.set_xlabel("Difficulty level", fontsize=11)
    ax.set_title("Generated Token Count vs Difficulty", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["pdf", "png"]:
        p = out_dir / f"study_c_difficulty.{ext}"
        plt.savefig(str(p), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Plots saved to {out_dir}", flush=True)


def get_package_versions() -> dict:
    import subprocess
    import transformers
    versions = {
        "transformers": transformers.__version__,
        "torch": torch.__version__,
        "PIL": PIL.__version__,
        "python": sys.version.split()[0],
    }
    try:
        cuda_out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                            "--format=csv,noheader,nounits"],
                                           text=True).strip()
        versions["gpu_info"] = cuda_out
    except Exception:
        pass
    try:
        import datasets
        versions["datasets"] = datasets.__version__
    except Exception:
        pass
    return versions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["select", "run", "analyse", "all"], default="all")
    parser.add_argument("--model", choices=list(MODELS.keys()) + ["both"], default="both")
    parser.add_argument("--resume", action="store_true", help="Resume from existing CSV")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    selection_path = RESULTS_DIR / "study_c_selection.json"
    trials_csv_path = RESULTS_DIR / "study_c_trials.csv"
    results_json_path = RESULTS_DIR / "study_c_results.json"

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    # ---- Phase 1: data selection ----
    if args.phase in ("select", "all"):
        if selection_path.exists() and args.resume:
            print("Loading existing selection...", flush=True)
            with open(selection_path) as f:
                selection_meta = json.load(f)
            print(f"Loaded {len(selection_meta)} images from cache", flush=True)
        else:
            images_with_bytes = load_coco_person_images(N_PER_LEVEL, SEED)
            # Save metadata without bytes
            selection_meta = [{k: v for k, v in item.items() if k != "image_bytes"}
                              for item in images_with_bytes]
            with open(selection_path, "w") as f:
                json.dump(selection_meta, f, indent=2)
            print(f"Saved selection metadata: {selection_path}", flush=True)

        if args.phase == "select":
            print("Phase select done. Re-run with --phase run or --phase all.", flush=True)
            return

    # Reload images from COCO (need bytes for PIL)
    print("Reloading image bytes from COCO for inference...", flush=True)
    if selection_path.exists():
        with open(selection_path) as f:
            selection_meta = json.load(f)
        needed_ids = set(item["image_id"] for item in selection_meta)
    else:
        images_with_bytes = load_coco_person_images(N_PER_LEVEL, SEED)
        selection_meta = [{k: v for k, v in item.items() if k != "image_bytes"}
                          for item in images_with_bytes]
        with open(selection_path, "w") as f:
            json.dump(selection_meta, f, indent=2)
        needed_ids = set(item["image_id"] for item in selection_meta)

    import datasets
    from datasets import Image as HFImage
    ds = datasets.load_dataset("detection-datasets/coco", split="val", streaming=True)
    ds = ds.cast_column("image", HFImage(decode=False))

    meta_by_id = {item["image_id"]: item for item in selection_meta}
    images_with_bytes = []
    collected_ids = set()
    for ex in ds:
        if ex["image_id"] in needed_ids and ex["image_id"] not in collected_ids:
            meta = meta_by_id[ex["image_id"]]
            images_with_bytes.append({**meta, "image_bytes": ex["image"]["bytes"]})
            collected_ids.add(ex["image_id"])
        if collected_ids == needed_ids:
            break

    print(f"Collected {len(images_with_bytes)} images with bytes", flush=True)
    pil_cache = save_images(images_with_bytes, IMAGES_DIR)

    # ---- Phase 2: run inference ----
    if args.phase in ("run", "all"):
        # Check existing trials to support resume
        existing_trial_keys = set()
        if args.resume and trials_csv_path.exists():
            with open(trials_csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_trial_keys.add(
                        (row["model"], int(row["image_id"]), row["mode"], int(row["rep"]))
                    )
            print(f"Resuming: {len(existing_trial_keys)} existing trials found", flush=True)

        models_to_run = list(MODELS.keys()) if args.model == "both" else [args.model]
        all_records = []

        for model_slug in models_to_run:
            model_id = MODELS[model_slug]
            records = run_model(
                model_slug, model_id, images_with_bytes, pil_cache,
                trials_csv_path, existing_trial_keys
            )
            all_records.extend(records)

    # ---- Phase 3: analysis ----
    if args.phase in ("analyse", "all"):
        # Load all trials from CSV (includes previous runs)
        all_records = []
        if trials_csv_path.exists():
            with open(trials_csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["n_input"] = int(row["n_input"])
                    row["n_generated"] = int(row["n_generated"])
                    row["latency_ms"] = float(row["latency_ms"])
                    row["budget_hit"] = row["budget_hit"] == "True"
                    row["n_persons_gt"] = int(row["n_persons_gt"])
                    row["image_id"] = int(row["image_id"])
                    row["rep"] = int(row["rep"])
                    row["parsed_answer"] = (int(row["parsed_answer"])
                                            if row["parsed_answer"] not in ("", "None") else None)
                    row["correct"] = (row["correct"] == "True" if row["correct"] not in ("", "None")
                                      else None)
                    all_records.append(row)

        print(f"\nTotal trials: {len(all_records)}", flush=True)

        summary = analyse(all_records)

        # Sanity checks
        print("\n--- Sanity checks ---", flush=True)

        # SC1: input token count constant across levels
        n_input_vals = set()
        for cell in summary.values():
            for v in cell["n_input_unique"]:
                n_input_vals.add(v)
        if len(n_input_vals) == 1:
            print(f"SC1 PASS: input token count = {list(n_input_vals)[0]} (constant)", flush=True)
        else:
            print(f"SC1 FAIL: input token counts vary: {n_input_vals}", flush=True)

        # SC2: step-by-step substantially longer than direct
        length_issues = check_length_separation(summary)
        if not length_issues:
            print("SC2 PASS: step-by-step generates substantially more tokens than direct", flush=True)
        else:
            print("SC2 WARNING:", flush=True)
            for issue in length_issues:
                print(f"  {issue}", flush=True)

        # SC3: budget hits
        budget_violations = check_budget_hits(summary)
        if not budget_violations:
            print("SC3 PASS: no cell exceeds 5% budget-hit rate", flush=True)
        else:
            print("SC3 FAIL — budget hit violations:", flush=True)
            for v in budget_violations:
                print(f"  {v}", flush=True)

        # SC4: unparseable fractions
        for key, cell in summary.items():
            if cell["unparseable_frac"] > 0.05:
                print(f"SC4 WARNING: {key} unparseable={cell['unparseable_frac']:.1%}", flush=True)
        print("SC4 checked", flush=True)

        # Print summary table
        print("\n--- Per-cell summary ---", flush=True)
        header = f"{'model':12} {'mode':10} {'level':5} {'n':5} {'acc':6} {'tokens_med':10} {'budget%':8} {'unparse%':9}"
        print(header, flush=True)
        for key in sorted(summary.keys()):
            c = summary[key]
            print(f"{c['model']:12} {c['mode']:10} {c['level']:5} "
                  f"{c['n_trials']:5} {c['accuracy']:6.3f} "
                  f"{c['n_generated_median']:10.1f} "
                  f"{c['budget_hit_frac']:8.3f} "
                  f"{c['unparseable_frac']:9.3f}", flush=True)

        # Save results
        pkg_versions = get_package_versions()
        results = {
            "config": {
                "seed": SEED,
                "device": DEVICE,
                "dtype": "bfloat16",
                "target_size": list(TARGET_SIZE),
                "n_per_level": N_PER_LEVEL,
                "n_reps": N_REPS,
                "max_new_tokens_direct": MAX_NEW_TOKENS_DIRECT,
                "max_new_tokens_stepwise": MAX_NEW_TOKENS_STEPWISE,
                "difficulty_levels": {k: list(v) for k, v in DIFFICULTY_LEVELS.items()},
                "models": MODELS,
                "direct_prompt": DIRECT_PROMPT,
                "stepwise_prompt": STEPWISE_PROMPT,
                "data_source": "HuggingFace detection-datasets/coco, split=val, person category",
            },
            "package_versions": pkg_versions,
            "summary": summary,
            "sanity_checks": {
                "SC1_input_token_constant": len(n_input_vals) == 1,
                "SC1_n_input_values": list(n_input_vals),
                "SC2_length_separation": len(length_issues) == 0,
                "SC2_issues": length_issues,
                "SC3_budget_hits": len(budget_violations) == 0,
                "SC3_violations": budget_violations,
            },
        }

        with open(results_json_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {results_json_path}", flush=True)

        # Generate plots
        try:
            plot_results(summary, FIGURES_DIR)
        except Exception as e:
            print(f"Plot failed: {e}", flush=True)

        # Budget hit stop condition
        if budget_violations:
            print("\nSTOP: Budget hit violations detected. See above.", flush=True)
            sys.exit(1)

        # Length separation stop condition
        if length_issues:
            print("\nSTOP: Step-by-step and direct modes produce similar lengths. See above.", flush=True)
            sys.exit(1)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
