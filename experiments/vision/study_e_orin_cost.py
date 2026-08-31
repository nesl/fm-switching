#!/usr/bin/env python3
"""
Study E — Part 1: Device-side inference cost on Jetson AGX Orin.

Measures inference cost for Qwen3-VL Instruct/Thinking on the SAME COCO images
and difficulty bins as Study D2, restricted to L2 and L3, 15 images/level, 3 reps.
Matches Study D2's prompt, greedy decode, and max_new_tokens (Instruct=40,
Thinking=8192) so the Orin numbers are directly comparable to the committed
A6000 numbers in reports/study_d2_thinking.md.

Adds instrumentation Study D2 lacked: time-to-first-token (TTFT), decode
tokens/sec (separated from prefill), peak memory, model load time, idle memory
after load, and a repeat-control noise floor.

Device config (power mode, clocks, versions) and thermal sampling are handled
outside this script (see run wrapper + thermal_sampler.py).

Output:
  results/vision/study_e/study_e_part1_trials.csv     (raw per-trial)
  results/vision/study_e/study_e_part1_results.json   (per-model, per-cell, sanity)
"""
import argparse
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

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

SELECTION_JSON = "results/vision/study_c/study_c_selection.json"
IMAGES_DIR     = "results/vision/study_c/study_c_images"
OUT_DIR        = "results/vision/study_e"
TRIALS_CSV     = f"{OUT_DIR}/study_e_part1_trials.csv"
RESULTS_JSON   = f"{OUT_DIR}/study_e_part1_results.json"
LOG_FILE       = "/tmp/study_e_part1.log"

DEVICE   = "cuda:0"            # Orin single GPU
DTYPE    = torch.bfloat16
SEED     = 42
N_REPS   = 3
LEVELS   = ["L2", "L3"]        # task: L2 and L3 only
N_IMAGES_PER_LEVEL = 15        # task: 15 images/level (deterministic subset of D2's 30)
LEVEL_BINS = {"L2": (2, 3), "L3": (4, 7)}
# A6000 committed reference (Study D2, reports/study_d2_thinking.md / EXPERIMENTS.md StudyD2):
# n_input is constant within mode = 348 (instruct) / 350 (thinking). This IS the
# "vision token count matches A6000 for the same model" check (n_input = vision+text).
# Raw vision tokens for Qwen3-VL-4B @560x560 = 324 (grid 36x36 / merge_size^2=4);
# note this differs from Qwen2.5-VL's 400 (Study A/B) — a different model, not an error.
A6000_N_INPUT = {"instruct": 348, "thinking": 350}
EXPECTED_VISION_TOKENS_QWEN3VL = 324
NOISE_FLOOR_REPS = 5           # repeat-control on one fixed trial
PROMPT = "How many people are in this image? Answer with a single integer."

# repo_id, revision (pinned to Study D2 snapshots), mode, max_new_tokens
MODEL_CONFIGS = [
    ("qwen3vl4b",   "Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17", "instruct", 40),
    ("qwen3vl4b_t", "Qwen/Qwen3-VL-4B-Thinking", "1de27d8c51f12e819435303b9e84c4e25ba8401e", "thinking", 8192),
    ("qwen3vl8b",   "Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b", "instruct", 40),
    ("qwen3vl8b_t", "Qwen/Qwen3-VL-8B-Thinking", "92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b", "thinking", 8192),
]

CSV_FIELDS = [
    "model", "mode", "image_id", "level", "n_persons_gt", "rep",
    "n_input", "n_generated", "n_think_tokens", "n_answer_tokens",
    "ttft_ms", "latency_ms", "decode_tps", "total_tps",
    "peak_mem_bytes", "budget_hit", "think_closed", "termination_class",
    "parsed_answer", "parse_status", "correct",
]

_log_fh = None
def log(msg):
    print(msg, flush=True)
    global _log_fh
    if _log_fh is None:
        _log_fh = open(LOG_FILE, "a")
    _log_fh.write(msg + "\n"); _log_fh.flush()


# ── data ────────────────────────────────────────────────────────────────────
def load_subset():
    with open(SELECTION_JSON) as f:
        data = json.load(f)
    by_level = defaultdict(list)
    for item in data:
        by_level[item["level"]].append(item)
    subset = []
    for lv in LEVELS:
        items = sorted(by_level[lv], key=lambda x: x["image_id"])[:N_IMAGES_PER_LEVEL]
        assert len(items) == N_IMAGES_PER_LEVEL, f"{lv}: only {len(items)} images"
        subset.extend(items)
    return subset

def load_image(level, image_id, gt):
    p = os.path.join(IMAGES_DIR, f"{level}_{image_id:012d}_gt{gt}.png")
    return Image.open(p).convert("RGB")


# ── parsing (matches Study D2) ──────────────────────────────────────────────
def parse_instruct(text):
    nums = re.findall(r"\b\d+\b", text)
    return (int(nums[0]), "ok") if nums else (None, "unparseable")

def parse_thinking(text):
    end = text.find("</think>")
    closed = (end != -1)
    if not closed:
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            return int(nums[-1]), "no_think_tag", text, "", closed
        return None, "unparseable", text, "", closed
    think_text  = text[:end]
    answer_text = text[end + len("</think>"):].strip()
    nums = re.findall(r"\b\d+\b", answer_text)
    if nums:
        return int(nums[0]), "ok", think_text, answer_text, closed
    nums_all = re.findall(r"\b\d+\b", text)
    if nums_all:
        return int(nums_all[-1]), "fallback_last_number", think_text, answer_text, closed
    return None, "unparseable", think_text, answer_text, closed

def termination_class(budget_hit, think_closed):
    if not budget_hit:
        return "complete"
    return "verbose_bounded" if think_closed else "non_termination"

def count_tokens(proc, text):
    if not text:
        return 0
    try:
        return len(proc.tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return 0

def count_vision_tokens(proc, img):
    msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": "x"}]}]
    txt = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = proc(text=[txt], images=[img], return_tensors="pt")
    if "image_grid_thw" in inp:
        thw = inp["image_grid_thw"]
        m = proc.image_processor.merge_size
        return int(thw.prod() // (m ** 2))
    return -1


# ── one trial (adds TTFT + decode_tps + peak_mem) ───────────────────────────
def build_inputs(proc, img):
    msgs = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text",  "text": PROMPT},
    ]}]
    txt = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[txt], images=[img], return_tensors="pt").to(DEVICE)
    return inputs

def run_trial(proc, model, item, rep, max_t, mode, slug):
    img = load_image(item["level"], item["image_id"], item["n_persons_gt"])
    inputs = build_inputs(proc, img)
    n_input = int(inputs.input_ids.shape[1])

    gen_kw = dict(do_sample=False, temperature=None, top_p=None, use_cache=True)

    # TTFT: prefill + 1 token
    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        _ = model.generate(**inputs, max_new_tokens=1, **gen_kw)
    torch.cuda.synchronize(DEVICE)
    ttft_ms = (time.perf_counter() - t0) * 1000

    # Full generation (peak measured here)
    torch.cuda.reset_peak_memory_stats(DEVICE)
    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        out_ids = model.generate(**inputs, max_new_tokens=max_t, **gen_kw)
    torch.cuda.synchronize(DEVICE)
    latency_ms = (time.perf_counter() - t0) * 1000
    peak_mem = torch.cuda.max_memory_allocated(DEVICE)

    gen_ids = out_ids[0][n_input:]
    n_gen = int(len(gen_ids))
    budget_hit = (n_gen >= max_t)
    gen_text = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
    total_tps = n_gen / (latency_ms / 1000) if latency_ms > 0 else 0.0
    decode_s = (latency_ms - ttft_ms) / 1000.0
    decode_tps = (n_gen - 1) / decode_s if (n_gen > 1 and decode_s > 0) else 0.0

    n_think = 0; n_answer = n_gen; closed = False
    if mode == "instruct":
        parsed, status = parse_instruct(gen_text)
    else:
        parsed, status, think_text, answer_text, closed = parse_thinking(gen_text)
        n_think  = count_tokens(proc, think_text)
        n_answer = count_tokens(proc, answer_text)

    gt = item["n_persons_gt"]
    correct = (parsed == gt) if parsed is not None else False
    return {
        "model": slug, "mode": mode, "image_id": item["image_id"],
        "level": item["level"], "n_persons_gt": gt, "rep": rep,
        "n_input": n_input, "n_generated": n_gen, "n_think_tokens": n_think,
        "n_answer_tokens": n_answer,
        "ttft_ms": f"{ttft_ms:.1f}", "latency_ms": f"{latency_ms:.1f}",
        "decode_tps": f"{decode_tps:.1f}", "total_tps": f"{total_tps:.1f}",
        "peak_mem_bytes": peak_mem, "budget_hit": budget_hit,
        "think_closed": closed, "termination_class": termination_class(budget_hit, closed),
        "parsed_answer": parsed if parsed is not None else "",
        "parse_status": status, "correct": correct,
    }


def append_trials(rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    write_header = not os.path.exists(TRIALS_CSV)
    with open(TRIALS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# ── per-model run ───────────────────────────────────────────────────────────
def run_model(slug, repo, rev, mode, max_t, subset, sanity):
    log(f"\n{'='*64}\nMODEL {slug} ({mode})  max_new_tokens={max_t}\n  {repo}@{rev[:8]}\n{'='*64}")

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(DEVICE)
    mem_before = torch.cuda.memory_allocated(DEVICE)

    t0 = time.perf_counter()
    proc = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        repo, revision=rev, torch_dtype=DTYPE, device_map=DEVICE, trust_remote_code=True)
    model.eval()
    load_time_s = time.perf_counter() - t0
    idle_mem = torch.cuda.memory_allocated(DEVICE) - mem_before

    # ── Sanity checks (stop on failure) ──
    p0 = next(model.parameters())
    sc = {}
    sc["device_placement"] = (str(p0.device) == DEVICE)
    sc["dtype_ok"] = (p0.dtype == DTYPE)
    # no CPU offload: every param on the intended cuda device
    offloaded = [n for n, p in model.named_parameters() if p.device.type != "cuda"]
    sc["no_cpu_offload"] = (len(offloaded) == 0)
    # raw vision token count (record; Qwen3-VL @560 = 324)
    img0 = load_image(subset[0]["level"], subset[0]["image_id"], subset[0]["n_persons_gt"])
    vtok = count_vision_tokens(proc, img0)
    sc["vision_tokens"] = vtok
    sc["vision_tokens_expected_qwen3vl"] = EXPECTED_VISION_TOKENS_QWEN3VL
    # n_input constant within mode + matches A6000 Study D2 (THE preprocessing-match check)
    n_inputs = []
    for it in subset[:5]:
        im = load_image(it["level"], it["image_id"], it["n_persons_gt"])
        n_inputs.append(int(build_inputs(proc, im).input_ids.shape[1]))
    sc["n_input_values_first5"] = n_inputs
    sc["n_input_constant"] = (len(set(n_inputs)) == 1)
    exp_ni = A6000_N_INPUT[mode]
    sc["n_input_a6000_expected"] = exp_ni
    sc["n_input_matches_a6000"] = (n_inputs[0] == exp_ni)
    log(f"  load_time={load_time_s:.1f}s  idle_mem={idle_mem/1e9:.2f}GB")
    log(f"  device={p0.device} dtype={p0.dtype} vision_tokens={vtok} "
        f"n_input(first5)={n_inputs} (A6000 expects {exp_ni})")
    log(f"  SANITY: place={sc['device_placement']} dtype={sc['dtype_ok']} "
        f"no_offload={sc['no_cpu_offload']} n_input_match_a6000={sc['n_input_matches_a6000']} "
        f"n_input_const={sc['n_input_constant']}")

    hard_fail = not (sc["device_placement"] and sc["dtype_ok"] and sc["no_cpu_offload"]
                     and sc["n_input_matches_a6000"] and sc["n_input_constant"])
    if hard_fail:
        log(f"  *** SANITY FAILURE for {slug} — recording and STOPPING this model ***")
        sanity[slug] = sc
        del model; torch.cuda.empty_cache()
        return None, sc, load_time_s, idle_mem

    # ── Warmup (not recorded) ──
    for it in subset[:2]:
        _ = run_trial(proc, model, it, 0, max_t, mode, slug)
    torch.cuda.empty_cache()

    # ── Repeat-control noise floor (fixed trial, back-to-back) ──
    fixed = subset[0]
    nf_lat = []
    for _ in range(NOISE_FLOOR_REPS):
        r = run_trial(proc, model, fixed, 0, max_t, mode, slug)
        nf_lat.append(float(r["latency_ms"]))
    nf_median = statistics.median(nf_lat)
    nf_cv = (statistics.pstdev(nf_lat) / nf_median) if nf_median else float("nan")
    sc["noise_floor_latency_ms"] = [round(x, 1) for x in nf_lat]
    sc["noise_floor_cv"] = round(nf_cv, 4)
    log(f"  noise-floor latency (n={NOISE_FLOOR_REPS}): median={nf_median:.1f}ms "
        f"CV={nf_cv:.3%}  vals={[round(x,1) for x in nf_lat]}")

    # ── Main matrix: randomized order ──
    rng = random.Random(SEED + hash(slug) % 10000)
    trials = [(it, rep) for it in subset for rep in range(N_REPS)]
    rng.shuffle(trials)

    t_start = time.perf_counter()
    for idx, (it, rep) in enumerate(trials):
        row = run_trial(proc, model, it, rep, max_t, mode, slug)
        append_trials([row])   # flush every trial (durability + live visibility)
        el = time.perf_counter() - t_start
        log(f"  [{idx+1}/{len(trials)}] lv={it['level']} rep={rep} gt={it['n_persons_gt']} "
            f"ngen={row['n_generated']} ttft={float(row['ttft_ms']):.0f} "
            f"lat={float(row['latency_ms']):.0f}ms dtps={float(row['decode_tps']):.1f} "
            f"tc={row['termination_class']} el={el:.0f}s")

    sanity[slug] = sc
    per_model = {"load_time_s": round(load_time_s, 2), "idle_mem_bytes": int(idle_mem)}
    del model; torch.cuda.empty_cache()
    return per_model, sc, load_time_s, idle_mem


# ── analysis (cost-focused) ─────────────────────────────────────────────────
def median_f(vals):
    return statistics.median(vals) if vals else float("nan")

def analyse(per_model_meta, sanity):
    with open(TRIALS_CSV) as f:
        rows = list(csv.DictReader(f))
    cells = {}
    slugs = [m[0] for m in MODEL_CONFIGS]
    for slug in slugs:
        for lv in LEVELS:
            cell = [r for r in rows if r["model"] == slug and r["level"] == lv]
            if not cell:
                continue
            lat = [float(r["latency_ms"]) for r in cell]
            ttft = [float(r["ttft_ms"]) for r in cell]
            dtps = [float(r["decode_tps"]) for r in cell if float(r["decode_tps"]) > 0]
            ngen = [int(r["n_generated"]) for r in cell]
            nthink = [int(r["n_think_tokens"]) for r in cell if int(r["n_think_tokens"]) > 0]
            peak = [int(r["peak_mem_bytes"]) for r in cell]
            budg = sum(1 for r in cell if r["budget_hit"] in ("True", True))
            cells[f"{slug}|{lv}"] = {
                "n": len(cell),
                "lat_median_ms": round(median_f(lat), 1),
                "lat_p25_ms": round(sorted(lat)[len(lat)//4], 1),
                "lat_p75_ms": round(sorted(lat)[3*len(lat)//4], 1),
                "ttft_median_ms": round(median_f(ttft), 1),
                "decode_tps_median": round(median_f(dtps), 1) if dtps else None,
                "n_gen_median": median_f(ngen),
                "n_think_median": median_f(nthink) if nthink else 0,
                "peak_mem_median_gb": round(median_f(peak)/1e9, 3),
                "budget_hit_frac": round(budg/len(cell), 3),
            }
    # merge per_model/sanity across invocations (models run in separate processes)
    prev_pm, prev_sc = {}, {}
    if os.path.exists(RESULTS_JSON):
        try:
            prev = json.load(open(RESULTS_JSON))
            prev_pm = prev.get("per_model", {}); prev_sc = prev.get("sanity", {})
        except Exception:
            pass
    prev_pm.update(per_model_meta); prev_sc.update(sanity)
    out = {"cells": cells, "per_model": prev_pm, "sanity": prev_sc,
           "config": {"device": DEVICE, "dtype": "bfloat16", "seed": SEED,
                      "levels": LEVELS, "n_images_per_level": N_IMAGES_PER_LEVEL,
                      "n_reps": N_REPS, "max_tok_instruct": 40, "max_tok_thinking": 8192}}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"\nResults -> {RESULTS_JSON}")
    # print table
    log("\n=== Part 1 cost summary (median) ===")
    log(f"{'cell':16} {'n':>3} {'ttft_ms':>8} {'lat_ms':>9} {'dec_tps':>8} {'ngen':>6} {'peakGB':>7} {'budg':>5}")
    for k, c in cells.items():
        log(f"{k:16} {c['n']:>3} {c['ttft_median_ms']:>8.0f} {c['lat_median_ms']:>9.0f} "
            f"{str(c['decode_tps_median']):>8} {c['n_gen_median']:>6.0f} "
            f"{c['peak_mem_median_gb']:>7.2f} {c['budget_hit_frac']:>5.2f}")
    return out


# ── main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="qwen3vl4b,qwen3vl4b_t",
                    help="comma-separated slugs to run (subset of configs)")
    ap.add_argument("--analyse-only", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    import transformers
    log(f"\n{'#'*64}\n# Study E Part 1 — {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    log(f"# python {sys.version.split()[0]}  torch {torch.__version__}  transformers {transformers.__version__}")
    log(f"# device={DEVICE} dtype={DTYPE} gpu={torch.cuda.get_device_name(0)}")
    log(f"# levels={LEVELS} n_img/level={N_IMAGES_PER_LEVEL} reps={N_REPS}")
    log(f"{'#'*64}")

    subset = load_subset()
    log(f"Subset: {len(subset)} images ({N_IMAGES_PER_LEVEL}/level, L2+L3)")

    want = set(args.models.split(","))
    per_model_meta = {}
    sanity = {}

    if not args.analyse_only:
        for slug, repo, rev, mode, max_t in MODEL_CONFIGS:
            if slug not in want:
                continue
            pm, sc, lt, im = run_model(slug, repo, rev, mode, max_t, subset, sanity)
            if pm is not None:
                per_model_meta[slug] = pm

    analyse(per_model_meta, sanity)
    log("\n=== Study E Part 1 done ===")


if __name__ == "__main__":
    main()
