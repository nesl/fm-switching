#!/usr/bin/env python3
"""
Study D2: Reasoning compute vs parameters — full 4-model run.

MAIN MATRIX  (quantitative): L1–L3, all 4 models, 3 reps each.
L4 PROBE     (qualitative):  L4, Thinking models only, 10 images, 1 rep.
                              Records per trial: did </think> close before budget?
                              termination_class:
                                non_termination  — hit cap while still inside reasoning block
                                verbose_bounded  — hit cap but </think> was found (answer produced)
                                complete         — did not hit cap

Changes from Study D:
  - max_new_tokens=8192 for Thinking (was 4096)
  - Scope: L1-L3 quantitative; L4 separate probe
  - tokens_per_second via cuda.synchronize()
  - Tolerance-based accuracy (within-1, within-2, rt25)
  - Within-cell point-biserial r: n_think vs correctness
  - Think tokens per GT person per level (token growth vs object growth)
"""

import csv
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

SELECTION_JSON = "results/vision/study_c/study_c_selection.json"
IMAGES_DIR     = "results/vision/study_c/study_c_images"
OUT_DIR        = "results/vision/study_d2"
TRIALS_CSV     = f"{OUT_DIR}/study_d2_trials.csv"
RESULTS_JSON   = f"{OUT_DIR}/study_d2_results.json"
FIG_DIR        = "figures/vision"
LOG_FILE       = "/tmp/study_d2_run.log"

HF_CACHE   = "/mnt/ssd/hf_models"
DEVICE     = "cuda:1"
DTYPE      = torch.bfloat16
SEED       = 42
N_REPS     = 3
MAIN_LEVELS = ["L1", "L2", "L3"]                  # quantitative matrix
LEVEL_BINS  = {"L1": (1, 1), "L2": (2, 3), "L3": (4, 7), "L4": (8, 999)}

MAX_NEW_TOKENS_INSTRUCT  = 40
MAX_NEW_TOKENS_THINKING  = 8192
BUDGET_STOP_FRAC  = 0.05
UNPARSE_STOP_FRAC = 0.05

# L4 probe parameters
L4_PROBE_N_IMAGES = 10
L4_PROBE_N_REPS   = 1

MODEL_CONFIGS = [
    {
        "slug": "qwen3vl4b",
        "mode": "instruct",
        "max_tok": MAX_NEW_TOKENS_INSTRUCT,
        "snap": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17",
    },
    {
        "slug": "qwen3vl8b",
        "mode": "instruct",
        "max_tok": MAX_NEW_TOKENS_INSTRUCT,
        "snap": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
    },
    {
        "slug": "qwen3vl4b_t",
        "mode": "thinking",
        "max_tok": MAX_NEW_TOKENS_THINKING,
        "snap": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e",
    },
    {
        "slug": "qwen3vl8b_t",
        "mode": "thinking",
        "max_tok": MAX_NEW_TOKENS_THINKING,
        "snap": "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b",
    },
]

# CSV_FIELDS includes probe and termination_class for unified output
CSV_FIELDS = [
    "model", "mode", "probe",           # probe: "main" or "L4_probe"
    "image_id", "level", "n_persons_gt",
    "rep", "n_input", "n_generated", "n_think_tokens", "n_answer_tokens",
    "latency_ms", "tokens_per_second",
    "budget_hit", "think_closed",       # think_closed: did </think> appear?
    "termination_class",                # complete | non_termination | verbose_bounded
    "parsed_answer", "parse_status", "correct",
]


# ── logging ────────────────────────────────────────────────────────────────────

_log_fh = None

def log(msg):
    print(msg, flush=True)
    global _log_fh
    if _log_fh is None:
        _log_fh = open(LOG_FILE, "a")
    _log_fh.write(msg + "\n")
    _log_fh.flush()


# ── data loading ───────────────────────────────────────────────────────────────

def load_selection():
    with open(SELECTION_JSON) as f:
        data = json.load(f)
    by_level = defaultdict(list)
    for item in data:
        by_level[item["level"]].append(item)
    return data, by_level


def load_image(level, image_id, n_persons_gt):
    p = os.path.join(IMAGES_DIR, f"{level}_{image_id:012d}_gt{n_persons_gt}.png")
    return Image.open(p).convert("RGB")


# ── parsing ────────────────────────────────────────────────────────────────────

def parse_instruct(text):
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        return int(nums[0]), "ok"
    return None, "unparseable"


def parse_thinking(text):
    """Split at </think>; first integer after is the answer."""
    end_think = text.find("</think>")
    think_closed = (end_think != -1)
    if not think_closed:
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            return int(nums[-1]), "no_think_tag", text, "", think_closed
        return None, "unparseable", text, "", think_closed
    think_text  = text[:end_think]
    answer_text = text[end_think + len("</think>"):].strip()
    nums = re.findall(r"\b\d+\b", answer_text)
    if nums:
        return int(nums[0]), "ok", think_text, answer_text, think_closed
    nums_all = re.findall(r"\b\d+\b", text)
    if nums_all:
        return int(nums_all[-1]), "fallback_last_number", think_text, answer_text, think_closed
    return None, "unparseable", think_text, answer_text, think_closed


def termination_class(budget_hit, think_closed):
    if not budget_hit:
        return "complete"
    if think_closed:
        return "verbose_bounded"   # answered, then kept going / answer block truncated
    return "non_termination"       # never closed reasoning block


def count_tokens(proc, text):
    if not text:
        return 0
    try:
        return len(proc.tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return 0


# ── CSV I/O ────────────────────────────────────────────────────────────────────

def append_trials(rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    # If file exists, check whether it already has the new columns
    write_header = not os.path.exists(TRIALS_CSV)
    if not write_header:
        with open(TRIALS_CSV) as f:
            existing_fields = f.readline().strip().split(",")
        if existing_fields != CSV_FIELDS:
            # Old format without probe/think_closed/termination_class — rewrite header
            # (only happens on first call after resume from partial data)
            write_header = False  # we'll append; column mismatch handled in analysis
    with open(TRIALS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def load_done_keys(slug, probe=False):
    """Return set of (image_id, level, rep, probe_flag) already written."""
    if not os.path.exists(TRIALS_CSV):
        return set(), 0
    keys = set()
    with open(TRIALS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("model") == slug:
                p = row.get("probe", "main")
                probe_flag = (p == "L4_probe")
                if probe_flag == probe:
                    keys.add((row["image_id"], row["level"], row["rep"]))
    return keys, len(keys)


# ── single trial ───────────────────────────────────────────────────────────────

def run_trial(proc, model, item, rep, max_t, mode, slug, probe_label):
    level    = item["level"]
    image_id = item["image_id"]
    gt       = item["n_persons_gt"]

    img  = load_image(level, image_id, gt)
    msgs = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text",  "text":  "How many people are in this image? Answer with a single integer."},
    ]}]
    txt    = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[txt], images=[img], return_tensors="pt").to(DEVICE)
    n_input = inputs.input_ids.shape[1]

    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=max_t,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    torch.cuda.synchronize(DEVICE)
    latency_ms = (time.perf_counter() - t0) * 1000

    gen_ids    = out_ids[0][n_input:]
    n_gen      = len(gen_ids)
    budget_hit = (n_gen >= max_t)
    gen_text   = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
    tps        = n_gen / (latency_ms / 1000) if latency_ms > 0 else 0.0

    n_think_tokens  = 0
    n_answer_tokens = n_gen
    think_closed_flag = False

    if mode == "instruct":
        parsed, status = parse_instruct(gen_text)
    else:
        parsed, status, think_text, answer_text, think_closed_flag = parse_thinking(gen_text)
        n_think_tokens  = count_tokens(proc, think_text)
        n_answer_tokens = count_tokens(proc, answer_text)

    correct = (parsed == gt) if parsed is not None else False
    tc      = termination_class(budget_hit, think_closed_flag)

    return {
        "model":            slug,
        "mode":             mode,
        "probe":            probe_label,
        "image_id":         image_id,
        "level":            level,
        "n_persons_gt":     gt,
        "rep":              rep,
        "n_input":          n_input,
        "n_generated":      n_gen,
        "n_think_tokens":   n_think_tokens,
        "n_answer_tokens":  n_answer_tokens,
        "latency_ms":       f"{latency_ms:.1f}",
        "tokens_per_second": f"{tps:.1f}",
        "budget_hit":       budget_hit,
        "think_closed":     think_closed_flag,
        "termination_class": tc,
        "parsed_answer":    parsed if parsed is not None else "",
        "parse_status":     status,
        "correct":          correct,
    }


# ── per-model main matrix (L1–L3) ─────────────────────────────────────────────

def run_main_matrix(cfg, selection):
    slug  = cfg["slug"]
    mode  = cfg["mode"]
    snap  = cfg["snap"]
    max_t = cfg["max_tok"]

    log(f"\n{'='*60}")
    log(f"MAIN MATRIX: {slug} ({mode})  levels=L1-L3  max_new_tokens={max_t}")
    log(f"Snapshot: {snap}")
    log(f"{'='*60}")

    done_keys, n_done = load_done_keys(slug, probe=False)
    log(f"  Already done: {n_done} rows (will skip matching keys)")

    # Filter selection to L1-L3 only
    main_selection = [item for item in selection if item["level"] in MAIN_LEVELS]

    log(f"  Loading weights ...")
    proc = AutoProcessor.from_pretrained(snap, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        snap, torch_dtype=DTYPE, device_map=DEVICE, trust_remote_code=True
    )
    model.eval()

    param0 = next(model.parameters())
    log(f"  device={param0.device}  dtype={param0.dtype}")
    assert param0.dtype == DTYPE, f"Expected {DTYPE}, got {param0.dtype}"

    # Vision token count sanity on first image
    first = main_selection[0]
    img0  = load_image(first["level"], first["image_id"], first["n_persons_gt"])
    msgs0 = [{"role": "user", "content": [
        {"type": "image", "image": img0},
        {"type": "text",  "text":  "How many people are in this image? Answer with a single integer."},
    ]}]
    txt0   = proc.apply_chat_template(msgs0, tokenize=False, add_generation_prompt=True)
    inp0   = proc(text=[txt0], images=[img0], return_tensors="pt").to(DEVICE)
    n_input_expected = inp0.input_ids.shape[1]
    log(f"  n_input ({mode}): {n_input_expected}")

    rng    = random.Random(SEED + hash(slug) % 10000)
    trials = [(item, rep) for item in main_selection for rep in range(N_REPS)]
    rng.shuffle(trials)

    new_rows   = []
    cell_stats = defaultdict(lambda: {"n": 0, "budget": 0, "unparse": 0})
    t_start    = time.perf_counter()

    for idx, (item, rep) in enumerate(trials):
        key = (str(item["image_id"]), item["level"], str(rep))
        if key in done_keys:
            continue

        row = run_trial(proc, model, item, rep, max_t, mode, slug, "main")
        n_input = row["n_input"]
        if abs(n_input - n_input_expected) > 0:
            log(f"  WARNING: n_input={n_input} != expected {n_input_expected} image_id={item['image_id']}")

        new_rows.append(row)
        cell_stats[(slug, item["level"])]["n"]      += 1
        cell_stats[(slug, item["level"])]["budget"] += int(row["budget_hit"])
        cell_stats[(slug, item["level"])]["unparse"] += int(row["parse_status"] == "unparseable")

        if (idx + 1) % 30 == 0 or idx == len(trials) - 1:
            elapsed = time.perf_counter() - t_start
            done_n  = n_done + len(new_rows)
            log(f"  [{done_n}/{len(trials)+n_done}] lv={item['level']} rep={rep} "
                f"gt={item['n_persons_gt']} parsed={row['parsed_answer']} "
                f"tc={row['termination_class']} n_gen={row['n_generated']} "
                f"lat={float(row['latency_ms']):.0f}ms tps={float(row['tokens_per_second']):.0f} "
                f"elapsed={elapsed:.0f}s")
            append_trials(new_rows)
            new_rows = []

    if new_rows:
        append_trials(new_rows)

    stop = False
    for (m, lv), st in cell_stats.items():
        n = st["n"]
        if n == 0:
            continue
        bfrac = st["budget"] / n
        ufrac = st["unparse"] / n
        if bfrac > BUDGET_STOP_FRAC:
            log(f"  STOP: {m}/{lv} budget_hit={bfrac:.1%} > {BUDGET_STOP_FRAC:.0%}")
            stop = True
        if ufrac > UNPARSE_STOP_FRAC:
            log(f"  STOP: {m}/{lv} unparseable={ufrac:.1%} > {UNPARSE_STOP_FRAC:.0%}")
            stop = True

    del model
    torch.cuda.empty_cache()
    return proc, stop


# ── L4 probe (Thinking models only) ───────────────────────────────────────────

def run_l4_probe(cfg, proc, by_level):
    """
    10 images × 1 rep for Thinking models at L4.
    Records termination_class: non_termination vs verbose_bounded vs complete.
    """
    slug  = cfg["slug"]
    mode  = cfg["mode"]
    snap  = cfg["snap"]
    max_t = cfg["max_tok"]

    assert mode == "thinking", f"L4 probe only for Thinking models, got mode={mode}"

    log(f"\n{'='*60}")
    log(f"L4 PROBE: {slug}  n_images={L4_PROBE_N_IMAGES}  n_reps={L4_PROBE_N_REPS}  max_tok={max_t}")
    log(f"{'='*60}")

    l4_images   = sorted(by_level["L4"], key=lambda x: x["image_id"])[:L4_PROBE_N_IMAGES]
    done_keys, n_done = load_done_keys(slug, probe=True)
    log(f"  Already done: {n_done} probe rows")

    log(f"  Loading weights ...")
    proc_local = AutoProcessor.from_pretrained(snap, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        snap, torch_dtype=DTYPE, device_map=DEVICE, trust_remote_code=True
    )
    model.eval()
    log(f"  device={next(model.parameters()).device}  dtype={next(model.parameters()).dtype}")

    new_rows = []
    tc_counts = defaultdict(int)

    for item in l4_images:
        for rep in range(L4_PROBE_N_REPS):
            key = (str(item["image_id"]), item["level"], str(rep))
            if key in done_keys:
                continue

            row = run_trial(proc_local, model, item, rep, max_t, mode, slug, "L4_probe")
            tc  = row["termination_class"]
            tc_counts[tc] += 1
            new_rows.append(row)

            log(f"  image_id={item['image_id']} gt={item['n_persons_gt']} "
                f"n_gen={row['n_generated']} think_closed={row['think_closed']} "
                f"tc={tc} lat={float(row['latency_ms']):.0f}ms "
                f"parsed={row['parsed_answer']}")

    append_trials(new_rows)

    log(f"\n  L4 probe termination summary ({slug}):")
    total = sum(tc_counts.values()) + n_done
    for tc, cnt in sorted(tc_counts.items()):
        log(f"    {tc}: {cnt}/{total}")

    del model
    torch.cuda.empty_cache()


# ── analysis ───────────────────────────────────────────────────────────────────

def _pct(vals, p):
    if not vals:
        return float("nan")
    sv  = sorted(vals)
    idx = int(len(sv) * p / 100)
    return sv[min(idx, len(sv) - 1)]


def _point_biserial(binary, continuous):
    n = len(binary)
    if n < 4:
        return float("nan")
    n1 = sum(binary)
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    m1 = statistics.mean(c for b, c in zip(binary, continuous) if b)
    m0 = statistics.mean(c for b, c in zip(binary, continuous) if not b)
    try:
        s = statistics.stdev(continuous)
    except statistics.StatisticsError:
        return float("nan")
    if s == 0:
        return float("nan")
    return (m1 - m0) / s * math.sqrt(n1 * n0 / n**2)


def _tolerance_acc(cell_rows, tol_int=None, tol_frac=None):
    n = len(cell_rows)
    if n == 0:
        return float("nan")
    correct = 0
    for r in cell_rows:
        pa = r.get("parsed_answer", "")
        if pa in ("", "None"):
            continue
        try:
            pa_int = int(pa)
        except (ValueError, TypeError):
            continue
        gt  = int(r["n_persons_gt"])
        err = abs(pa_int - gt)
        if tol_int is not None and err <= tol_int:
            correct += 1
        elif tol_frac is not None and gt > 0 and err / gt <= tol_frac:
            correct += 1
    return correct / n


def analyse():
    with open(TRIALS_CSV) as f:
        all_rows = list(csv.DictReader(f))

    # Split main matrix from probe
    main_rows  = [r for r in all_rows if r.get("probe", "main") == "main"]
    probe_rows = [r for r in all_rows if r.get("probe", "main") == "L4_probe"]

    log(f"\nTotal rows: {len(all_rows)}  (main={len(main_rows)}  L4_probe={len(probe_rows)})")

    slugs = [c["slug"] for c in MODEL_CONFIGS]
    results_main = {}

    for slug in slugs:
        for level in MAIN_LEVELS:
            cell = [r for r in main_rows if r["model"] == slug and r["level"] == level]
            n_total = len(cell)
            if n_total == 0:
                results_main[f"{slug}|{level}"] = {"n_total": 0}
                continue

            correct_c = sum(1 for r in cell if r.get("correct", "False") in ("True", True))
            acc_exact = correct_c / n_total
            acc_w1    = _tolerance_acc(cell, tol_int=1)
            acc_w2    = _tolerance_acc(cell, tol_int=2)
            acc_rt25  = _tolerance_acc(cell, tol_frac=0.25)

            budget_hits = sum(1 for r in cell if r.get("budget_hit", "False") in ("True", True))
            n_unparse   = sum(1 for r in cell if r.get("parse_status") == "unparseable")
            no_think_tag = sum(1 for r in cell if r.get("parse_status") == "no_think_tag")

            lat_vals = []
            tps_vals = []
            for r in cell:
                try:
                    lat_vals.append(float(r["latency_ms"]))
                    tps_vals.append(float(r.get("tokens_per_second", 0) or 0))
                except (ValueError, TypeError):
                    pass

            n_gen_vals   = [int(r["n_generated"]) for r in cell]
            n_think_vals = [int(r["n_think_tokens"]) for r in cell
                            if r.get("n_think_tokens") not in ("", "0", None, "None", 0)
                            and int(r.get("n_think_tokens", 0)) > 0]

            rpb = float("nan")
            if n_think_vals:
                think_rows = [r for r in cell
                              if r.get("n_think_tokens") not in ("", "0", None, "None", 0)
                              and int(r.get("n_think_tokens", 0)) > 0]
                binary_correct = [r.get("correct", "False") in ("True", True) for r in think_rows]
                rpb = _point_biserial(binary_correct, [int(r["n_think_tokens"]) for r in think_rows])

            gt_vals   = [int(r["n_persons_gt"]) for r in cell]
            gt_median = statistics.median(gt_vals)

            results_main[f"{slug}|{level}"] = {
                "n_total":          n_total,
                "n_unparse":        n_unparse,
                "no_think_tag":     no_think_tag,
                "budget_hits":      budget_hits,
                "budget_hit_frac":  budget_hits / n_total,
                "acc_exact":        acc_exact,
                "acc_within1":      acc_w1,
                "acc_within2":      acc_w2,
                "acc_rt25":         acc_rt25,
                "lat_median":       statistics.median(lat_vals) if lat_vals else float("nan"),
                "lat_p25":          _pct(lat_vals, 25),
                "lat_p75":          _pct(lat_vals, 75),
                "tps_median":       statistics.median(tps_vals) if tps_vals else float("nan"),
                "n_gen_median":     statistics.median(n_gen_vals) if n_gen_vals else float("nan"),
                "n_think_median":   statistics.median(n_think_vals) if n_think_vals else 0,
                "n_think_p25":      _pct(n_think_vals, 25) if n_think_vals else 0,
                "n_think_p75":      _pct(n_think_vals, 75) if n_think_vals else 0,
                "n_think_min":      min(n_think_vals) if n_think_vals else 0,
                "n_think_max":      max(n_think_vals) if n_think_vals else 0,
                "n_think_iqr_ratio": (
                    (_pct(n_think_vals, 75) - _pct(n_think_vals, 25)) / statistics.median(n_think_vals)
                    if n_think_vals and statistics.median(n_think_vals) > 0 else float("nan")
                ),
                "rpb_think_vs_correct": rpb,
                "gt_median":        gt_median,
                "think_per_gt":     (
                    statistics.median(n_think_vals) / gt_median
                    if n_think_vals and gt_median > 0 else float("nan")
                ),
            }

    # Probe analysis
    probe_summary = {}
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        pcell = [r for r in probe_rows if r["model"] == slug]
        n_total = len(pcell)
        if n_total == 0:
            continue
        from collections import Counter
        tc_counts = Counter(r.get("termination_class", "unknown") for r in pcell)
        probe_summary[slug] = {
            "n_total":         n_total,
            "tc_non_term":     tc_counts.get("non_termination", 0),
            "tc_verb_bounded": tc_counts.get("verbose_bounded", 0),
            "tc_complete":     tc_counts.get("complete", 0),
            "n_think_vals":    [int(r["n_think_tokens"]) for r in pcell
                                if r.get("n_think_tokens") not in ("", "0", None) and int(r.get("n_think_tokens", 0)) > 0],
            "lat_vals":        [float(r["latency_ms"]) for r in pcell],
        }

    # Print main matrix summaries
    log("\n=== Per-cell accuracy (main matrix L1–L3) ===")
    hdr = f"{'model':18} {'metric':10} {'L1':8} {'L2':8} {'L3':8}"
    log(hdr); log("-" * len(hdr))
    for slug in slugs:
        for metric, key in [("exact", "acc_exact"), ("within-1", "acc_within1"),
                             ("within-2", "acc_within2"), ("rt25", "acc_rt25")]:
            vals = [results_main.get(f"{slug}|{lv}", {}).get(key, float("nan")) for lv in MAIN_LEVELS]
            def fmt(v): return f"{v:.3f}" if not math.isnan(v) else "nan"
            log(f"{slug:18} {metric:10} {fmt(vals[0]):8} {fmt(vals[1]):8} {fmt(vals[2]):8}")

    log("\n=== Think token distributions (Thinking models, main matrix) ===")
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        log(f"  {slug}")
        for lv in MAIN_LEVELS:
            r = results_main.get(f"{slug}|{lv}", {})
            log(f"    {lv}: median={r.get('n_think_median',0):.0f} "
                f"[p25={r.get('n_think_p25',0):.0f} p75={r.get('n_think_p75',0):.0f}] "
                f"min={r.get('n_think_min',0):.0f} max={r.get('n_think_max',0):.0f} "
                f"IQR/median={r.get('n_think_iqr_ratio',float('nan')):.2f}")

    log("\n=== Point-biserial r (n_think vs correct, within cell) ===")
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        vals = [results_main.get(f"{slug}|{lv}", {}).get("rpb_think_vs_correct", float("nan")) for lv in MAIN_LEVELS]
        def fmt(v): return f"{v:+.3f}" if not math.isnan(v) else "nan"
        log(f"  {slug}: {' '.join(f'{lv}={fmt(v)}' for lv, v in zip(MAIN_LEVELS, vals))}")

    log("\n=== Think tokens per GT person ===")
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        vals = [results_main.get(f"{slug}|{lv}", {}).get("think_per_gt", float("nan")) for lv in MAIN_LEVELS]
        def fmt(v): return f"{v:.1f}" if not math.isnan(v) else "nan"
        log(f"  {slug}: {' '.join(f'{lv}={fmt(v)}' for lv, v in zip(MAIN_LEVELS, vals))}")

    log("\n=== Latency median (ms) ===")
    for slug in slugs:
        vals = [results_main.get(f"{slug}|{lv}", {}).get("lat_median", float("nan")) for lv in MAIN_LEVELS]
        def fmt(v): return f"{v:.0f}" if not math.isnan(v) else "nan"
        log(f"  {slug}: {' '.join(f'{lv}={fmt(v)}ms' for lv, v in zip(MAIN_LEVELS, vals))}")

    log("\n=== L4 probe — termination classification ===")
    for slug, ps in probe_summary.items():
        n   = ps["n_total"]
        nt  = ps["tc_non_term"]
        vb  = ps["tc_verb_bounded"]
        cp  = ps["tc_complete"]
        log(f"  {slug} (n={n}): non_termination={nt}({nt/n:.0%}) "
            f"verbose_bounded={vb}({vb/n:.0%}) complete={cp}({cp/n:.0%})")
        if ps["n_think_vals"]:
            log(f"    think_tokens: median={statistics.median(ps['n_think_vals']):.0f} "
                f"max={max(ps['n_think_vals']):.0f}")

    combined = {"main": results_main, "probe": probe_summary}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    log(f"\nResults saved to {RESULTS_JSON}")
    return results_main, probe_summary


# ── plotting ───────────────────────────────────────────────────────────────────

def plot(results_main, probe_summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    slugs   = [c["slug"] for c in MODEL_CONFIGS]
    levels  = MAIN_LEVELS
    x       = np.arange(len(levels))
    colors  = {"qwen3vl4b": "#1565C0", "qwen3vl4b_t": "#42A5F5",
               "qwen3vl8b": "#B71C1C", "qwen3vl8b_t": "#EF5350"}
    lspecs  = {"qwen3vl4b": ("-","o"), "qwen3vl4b_t": ("--","s"),
               "qwen3vl8b": ("-","^"), "qwen3vl8b_t": ("--","D")}
    xlabels = ["L1\n(1 person)", "L2\n(2–3)", "L3\n(4–7)"]
    lmap    = {"qwen3vl4b": "4B Instruct", "qwen3vl4b_t": "4B Thinking",
               "qwen3vl8b": "8B Instruct", "qwen3vl8b_t": "8B Thinking"}

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Panel 1: accuracy curves (exact + within-1)
    ax = axes[0]
    for slug in slugs:
        accs_e  = [results_main.get(f"{slug}|{lv}", {}).get("acc_exact",   float("nan")) for lv in levels]
        accs_w1 = [results_main.get(f"{slug}|{lv}", {}).get("acc_within1", float("nan")) for lv in levels]
        ls, mk  = lspecs[slug]
        ax.plot(x, accs_e,  color=colors[slug], ls=ls,  marker=mk, lw=2, ms=7, label=lmap[slug])
        ax.plot(x, accs_w1, color=colors[slug], ls=":", marker=mk, lw=1.2, ms=5, alpha=0.7)
    ax.plot([], [], "k-",  lw=2,   label="solid=exact")
    ax.plot([], [], "k:",  lw=1.2, label="dotted=within-1", alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylim(-0.05, 1.05); ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs Difficulty (L1–L3)", fontsize=11)
    ax.legend(fontsize=7); ax.grid(alpha=0.3)

    # Panel 2: think tokens with IQR shading
    ax = axes[1]
    for slug in [c["slug"] for c in MODEL_CONFIGS if c["mode"] == "thinking"]:
        meds = np.array([results_main.get(f"{slug}|{lv}", {}).get("n_think_median", 0) for lv in levels], dtype=float)
        p25s = np.array([results_main.get(f"{slug}|{lv}", {}).get("n_think_p25", 0)    for lv in levels], dtype=float)
        p75s = np.array([results_main.get(f"{slug}|{lv}", {}).get("n_think_p75", 0)    for lv in levels], dtype=float)
        ls, mk = lspecs[slug]
        ax.plot(x, meds, color=colors[slug], ls=ls, marker=mk, lw=2, ms=7, label=lmap[slug])
        ax.fill_between(x, p25s, p75s, color=colors[slug], alpha=0.15)
    ax.set_xticks(x); ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylabel("Think tokens (median ± IQR shading)")
    ax.set_title("Reasoning Length vs Difficulty", fontsize=11)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # Panel 3: latency
    ax = axes[2]
    for slug in slugs:
        lats = [results_main.get(f"{slug}|{lv}", {}).get("lat_median", float("nan")) / 1000 for lv in levels]
        ls, mk = lspecs[slug]
        ax.plot(x, lats, color=colors[slug], ls=ls, marker=mk, lw=2, ms=7, label=lmap[slug])
    ax.set_xticks(x); ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylabel("Median latency (s)")
    ax.set_title("Latency vs Difficulty", fontsize=11)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    fig.suptitle("Study D2: Reasoning Compute vs Parameters (Qwen3-VL 4B/8B)", fontsize=11)
    plt.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(f"{FIG_DIR}/study_d2_thinking.{ext}",
                    bbox_inches="tight", dpi=150 if ext == "png" else None)
    plt.close()
    log(f"Figures saved to {FIG_DIR}/study_d2_thinking.{{pdf,png}}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log(f"\n{'#'*60}")
    log(f"# Study D2 — {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    log(f"# Python {sys.version}")
    import transformers
    log(f"# transformers {transformers.__version__}  torch {torch.__version__}")
    log(f"# DEVICE={DEVICE}  DTYPE={DTYPE}")
    log(f"# MAIN_LEVELS={MAIN_LEVELS}  N_REPS={N_REPS}")
    log(f"# MAX_NEW_TOKENS_INSTRUCT={MAX_NEW_TOKENS_INSTRUCT}")
    log(f"# MAX_NEW_TOKENS_THINKING={MAX_NEW_TOKENS_THINKING}")
    log(f"# L4_PROBE: {L4_PROBE_N_IMAGES} images × {L4_PROBE_N_REPS} rep, Thinking only")
    log(f"{'#'*60}")

    selection, by_level = load_selection()
    log(f"Loaded {len(selection)} images; L4 available: {len(by_level['L4'])}")

    # Runtime estimate: L1-L3 only
    n_main  = sum(1 for item in selection if item["level"] in MAIN_LEVELS) * N_REPS
    n_probe = L4_PROBE_N_IMAGES * L4_PROBE_N_REPS * 2  # two Thinking models
    est_instruct = n_main * 2 * 0.15            # 2 Instruct models, ~150ms/trial
    est_think4b  = n_main * 15.0                # 4B-Thinking ~15s avg across L1-L3
    est_think8b  = n_main * 30.0                # 8B-Thinking ~30s avg across L1-L3
    est_probe    = n_probe * 250.0              # L4 full budget ~250s/trial
    est_total    = est_instruct + est_think4b + est_think8b + est_probe
    log(f"Estimated runtime: {est_total/3600:.1f}h ({est_total/60:.0f}min) "
        f"[instruct={est_instruct/60:.0f}m think4b={est_think4b/60:.0f}m "
        f"think8b={est_think8b/60:.0f}m probe={est_probe/60:.0f}m]")
    if est_total > 8 * 3600:
        log("STOP: Estimated runtime exceeds 8 hours. Halting.")
        sys.exit(1)

    stop_globally = False
    proc_cache    = {}   # reuse processor for L4 probe without reloading

    for cfg in MODEL_CONFIGS:
        slug = cfg["slug"]
        if stop_globally:
            log(f"Skipping {slug} (earlier stop condition).")
            continue
        proc, stop = run_main_matrix(cfg, selection)
        proc_cache[slug] = proc
        if stop:
            stop_globally = True
            log("Stop condition triggered.")

    # L4 probe — run regardless of stop_globally (it's a separate documented result)
    log("\n" + "="*60)
    log("L4 PROBE PHASE")
    log("="*60)
    for cfg in MODEL_CONFIGS:
        if cfg["mode"] != "thinking":
            continue
        run_l4_probe(cfg, proc_cache.get(cfg["slug"]), by_level)

    log("\nRunning analysis ...")
    results_main, probe_summary = analyse()
    plot(results_main, probe_summary)

    if stop_globally:
        log("\nPartial main matrix: stop condition fired on one model.")
    else:
        log("\nAll models complete.")


if __name__ == "__main__":
    main()
