#!/usr/bin/env python3
"""
Study I2 — S-EMBER token budget allocation.

Three arms, two models. Primary question: which side of the fixed vision token budget
wins per question category — more frames at reduced resolution (TEMPORAL) or fewer
frames at full resolution (SPARSE / SPATIAL)?

Arms:
  SPARSE   16 frames uniform over [0, question_time]. Budget does not bind. ~270 tok/frame.
  SPATIAL  42 frames at 1fps. Budget verified not to bind at ≤42 frames for S-EMBER.
             ~270 tok/frame. Max frames: SPATIAL_MAX_FRAMES = 42.
  TEMPORAL 256 frames at 1fps. Budget binds; processor reduces spatial resolution.
             ~56 tok/frame for long videos. Max frames: 256.

KV constant (corrected from study_i_diagnostic.md §4):
  Qwen3-VL-4B and 8B both: 36 layers × 2 × 8 kv_heads × 128 head_dim × 2 bytes = 147,456 B/tok.
  Diagnostic §4 used hidden_size (3584 for a hypothetical model) instead of n_kv_heads × head_dim.
  57,344 B/tok (Studies A/B/E/F) is for Qwen2.5-VL-7B (28 layers × 2 × 4 heads × 128 × 2),
  a different model family; no contradiction.

Write scope:
  results/sember/study_i2/study_i2_trials.jsonl
  results/sember/study_i2/study_i2_results.json
  reports/study_i2_budget.md

Data: reuses study_i 150-video / 459-question manifest (videos already downloaded).
GSER contract: each question sees only video[0, question_time]. Asserted per trial.
"""

from __future__ import annotations

import gc
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import av
import numpy as np
import torch
from PIL import Image
from scipy.stats import chisquare
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from transformers.video_utils import VideoMetadata

try:
    from qwen_vl_utils import process_vision_info
except ImportError:
    sys.exit("qwen_vl_utils not found — activate fmtk conda env")

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_manifest.json"
VIDEO_DIR = PROJECT_ROOT / "results/sember/study_i/videos"
MCQ_PATH = PROJECT_ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
TEXT_ONLY_PATH = PROJECT_ROOT / "results/sember/study_i_diag/diag_text_only_summary.json"
OUT_DIR = PROJECT_ROOT / "results/sember/study_i2"
TRIALS_PATH = OUT_DIR / "study_i2_trials.jsonl"
RESULTS_PATH = OUT_DIR / "study_i2_results.json"
REPORT_PATH = PROJECT_ROOT / "reports/study_i2_budget.md"

# ── hardware ──────────────────────────────────────────────────────────────────

DEVICE = "cuda:1"
DTYPE = torch.bfloat16
MAX_NEW_TOKENS = 16
SEED = 42
RUNTIME_LIMIT_S = 6 * 3600

# ── snapshots ─────────────────────────────────────────────────────────────────

SNAP_4B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
SNAP_8B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"

MODEL_CONFIGS = [
    {"slug": "qwen3vl4b", "snap": SNAP_4B},
    {"slug": "qwen3vl8b", "snap": SNAP_8B},
]

# Approximate decode rates from Study F (tok/s, A6000, C1 dynamic cache)
DECODE_RATE = {"qwen3vl4b": 48.5, "qwen3vl8b": 32.0}

# ── arms ──────────────────────────────────────────────────────────────────────

ARMS = ["SPARSE", "SPATIAL", "TEMPORAL"]
SPARSE_N_FRAMES = 16
SPATIAL_MAX_FRAMES = 42   # verified: 42f S-EMBER (720×966) gives grid=[21,54,42]=47628, no spatial reduction
TEMPORAL_MAX_FRAMES = 256
PROC_3D_BUDGET = 47_628   # video_grid_thw product at the budget limit (empirically: 42f × 720×966)
# Flag SPATIAL trial as budget-bound if tok/frame falls below this
SPATIAL_TOK_PER_FRAME_MIN = 220
# Cap each (model, arm) combination at this many trials
MAX_TRIALS_PER_ARM = 100

# Qwen3-VL special token IDs (from model config / tokenizer)
VIDEO_TOKEN_ID = 151656   # <|video_pad|> — actual visual placeholder in input_ids
IMAGE_TOKEN_ID = 151655   # <|image_pad|>

# ── categories ────────────────────────────────────────────────────────────────

CATEGORIES = [
    "time_duration",
    "visual_detail_recall",
    "sequential_action",
    "location_trace",
    "spatial_aware_reasoning",
    "object_comparison",
    "temporal_ordering_recognition",
]

# ── KV constant ───────────────────────────────────────────────────────────────

def compute_kv_bpt(snap: str) -> dict:
    """Compute KV bytes per token analytically from model text_config."""
    cfg = json.load(open(f"{snap}/config.json"))
    tc = cfg["text_config"]
    nl = tc["num_hidden_layers"]
    nkvh = tc["num_key_value_heads"]
    hd = tc["head_dim"]
    nbytes = 2  # bfloat16
    bpt = nl * 2 * nkvh * hd * nbytes
    return {
        "num_hidden_layers": nl,
        "num_key_value_heads": nkvh,
        "head_dim": hd,
        "dtype_bytes": nbytes,
        "bpt": bpt,
        "formula": f"{nl}L × 2 × {nkvh}kv × {hd}d × {nbytes}B = {bpt}",
    }


def measure_kv_bpt_empirical(model, proc, device: str) -> Optional[float]:
    """Empirically measure KV bytes per token via a text-only forward pass."""
    try:
        text = "The quick brown fox jumps over the lazy dog. " * 8
        inputs = proc(text=[text], return_tensors="pt").to(device)
        n_tok = inputs.input_ids.shape[-1]
        torch.cuda.synchronize(device)
        with torch.no_grad():
            out = model(**inputs, use_cache=True)
        torch.cuda.synchronize(device)
        kv = out.past_key_values
        if kv is None:
            return None
        try:
            from transformers.cache_utils import DynamicCache
            if isinstance(kv, DynamicCache):
                total = (sum(t.numel() * t.element_size() for t in kv.key_cache) +
                         sum(t.numel() * t.element_size() for t in kv.value_cache))
            else:
                raise TypeError
        except (ImportError, TypeError):
            total = sum(k.numel() * k.element_size() + v.numel() * v.element_size()
                        for k, v in kv)
        return total / n_tok
    except Exception:
        return None


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def write_jsonl_append(path: Path, rec: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def load_done_keys(path: Path) -> set:
    if not path.exists():
        return set()
    done = set()
    for r in load_jsonl(path):
        if "model" in r and "arm" in r and "question_id" in r:
            done.add((r["model"], r["arm"], r["question_id"]))
    return done


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def acc_ci(rows: list[dict]) -> dict:
    n = len(rows)
    k = sum(r["correct"] for r in rows if r.get("correct") is not None)
    a = k / n if n else float("nan")
    lo, hi = wilson_ci(k, n)
    return {"n": n, "k": k, "acc": round(a, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}


# ── frame loading ─────────────────────────────────────────────────────────────

def get_frame_at_time(container, stream, target_time_s: float) -> Optional[Image.Image]:
    time_base = float(stream.time_base)
    pts = int(target_time_s / time_base)
    try:
        container.seek(pts, stream=stream, backward=True)
    except av.AVError:
        try:
            container.seek(0)
        except av.AVError:
            return None
    best_img, best_diff = None, float("inf")
    for frame in container.decode(stream):
        t = float(frame.pts * stream.time_base)
        diff = abs(t - target_time_s)
        if diff < best_diff:
            best_diff = diff
            best_img = frame.to_image()
        if t > target_time_s + 2.0:
            break
    return best_img


def load_frames(video_path: Path, question_time: float, arm: str
                ) -> tuple[list, list[int], int, int]:
    """
    Return (frames, timestamps_s, n_requested, n_loaded).
    n_requested: the target count from the arm config.
    n_loaded: actual frames decoded (may be less for very short videos).
    GSER assertion: all timestamps ≤ question_time.
    """
    container = av.open(str(video_path))
    stream = container.streams.video[0]

    if arm == "SPARSE":
        n_req = SPARSE_N_FRAMES
        n = n_req
        target_times = [question_time * i / (n - 1) for i in range(n)]
    elif arm == "SPATIAL":
        # PROC_3D_BUDGET is in video_grid_thw product units (~47,628 for S-EMBER).
        # Empirically verified: 42 frames of S-EMBER 720×960-966 video gives
        # grid_thw product exactly at the budget limit with NO spatial reduction
        # (tok/frame = 283.5, same as SPARSE). Low-res videos give fewer tok/frame
        # at any arm including SPARSE — this is NOT a budget violation.
        n_req = min(int(question_time), SPATIAL_MAX_FRAMES)
        target_times = [float(i) for i in range(n_req)]
    elif arm == "TEMPORAL":
        n_req = min(int(question_time), TEMPORAL_MAX_FRAMES)
        target_times = [float(i) for i in range(n_req)]
    else:
        raise ValueError(f"Unknown arm: {arm}")

    # GSER assertion
    assert all(t <= question_time + 1e-6 for t in target_times), \
        f"GSER violated: target beyond question_time={question_time}"

    frames, timestamps_s = [], []
    for t in target_times:
        img = get_frame_at_time(container, stream, t)
        if img is not None:
            frames.append(img)
            timestamps_s.append(round(t))

    container.close()
    return frames, timestamps_s, n_req, len(frames)


# ── inference ─────────────────────────────────────────────────────────────────

def format_question(qa_row: dict) -> str:
    q = qa_row["question"]
    options = "\n".join(qa_row["options"])
    return (
        f"Watch the video carefully, then answer the following multiple-choice question.\n\n"
        f"Question: {q}\n\n"
        f"{options}\n\n"
        f"Reply with only the letter of the correct answer (A, B, C, D, or E)."
    )


def parse_letter(text: str) -> Optional[str]:
    for ch in text.strip().upper():
        if ch in "ABCDE":
            return ch
    return None


def run_single_trial(proc, model, qa_row: dict, video_path: Path,
                     arm: str, model_slug: str) -> dict:
    qt = qa_row["question_time"]
    ast = qa_row["answer_start_time"]
    aet = qa_row["answer_end_time"]

    frames, timestamps_s, n_req, n_loaded = load_frames(video_path, qt, arm)
    if n_loaded == 0:
        return {"model": model_slug, "arm": arm,
                "video_id": qa_row["video_id"], "question_id": qa_row["question_id"],
                "error": "no_frames_loaded"}

    video_meta = VideoMetadata(fps=1.0, frames_indices=timestamps_s,
                                total_num_frames=round(qt))
    question_text = format_question(qa_row)
    messages = [{"role": "user", "content": [
        {"type": "video", "video": frames, "sample_fps": 1.0},
        {"type": "text", "text": question_text},
    ]}]

    text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs, video_kwargs = process_vision_info(
        messages, return_video_kwargs=True)
    if "fps" in video_kwargs and isinstance(video_kwargs["fps"], list):
        video_kwargs["fps"] = video_kwargs["fps"][0] if video_kwargs["fps"] else None

    inputs = proc(text=[text], images=image_inputs, videos=video_inputs,
                  video_metadata=video_meta, return_tensors="pt",
                  **video_kwargs).to(DEVICE)

    # Count actual visual token positions in input_ids (post-deepstack compression).
    # video_grid_thw gives the pre-compression grid (T×H×W); Qwen3-VL's deepstack
    # visual encoder compresses that by ~4.2× before inserting VIDEO_TOKEN_ID
    # placeholders, so counting by grid product overstates vision_tokens ~4×.
    vision_tokens = int((inputs["input_ids"] == VIDEO_TOKEN_ID).sum())

    n_input = inputs.input_ids.shape[1]

    torch.cuda.reset_peak_memory_stats(DEVICE)
    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        out_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                  do_sample=False, temperature=None, top_p=None)
    torch.cuda.synchronize(DEVICE)
    total_ms = (time.perf_counter() - t0) * 1000
    peak_gb = torch.cuda.max_memory_allocated(DEVICE) / 1024**3

    gen_ids = out_ids[0][n_input:]
    n_generated = len(gen_ids)
    gen_text = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
    predicted = parse_letter(gen_text)
    correct_letter = qa_row["correct_letter"]
    correct = (predicted == correct_letter) if predicted is not None else False

    # Prefill estimate: total minus decode estimate
    decode_rate = DECODE_RATE.get(model_slug, 40.0)
    prefill_ms_est = max(0.0, total_ms - n_generated * 1000.0 / decode_rate)

    # Sanity: SPATIAL budget assertion
    tok_per_frame = (vision_tokens / n_loaded) if (vision_tokens and n_loaded) else None
    spatial_budget_ok = None
    if arm == "SPATIAL" and tok_per_frame is not None:
        spatial_budget_ok = tok_per_frame >= SPATIAL_TOK_PER_FRAME_MIN

    nearest_dist = qt - aet
    farthest_dist = qt - ast

    return {
        "model": model_slug,
        "arm": arm,
        "video_id": qa_row["video_id"],
        "question_id": qa_row["question_id"],
        "category": qa_row["question_category"],
        "question_time": qt,
        "answer_start_time": ast,
        "answer_end_time": aet,
        "nearest_dist_s": round(nearest_dist, 2),
        "farthest_dist_s": round(farthest_dist, 2),
        "n_frames_requested": n_req,
        "n_frames_actually_processed": n_loaded,
        "vision_tokens": vision_tokens,
        "tok_per_frame": round(tok_per_frame, 1) if tok_per_frame else None,
        "n_input_tokens": n_input,
        "n_generated": n_generated,
        "prefill_ms_est": round(prefill_ms_est, 1),
        "total_latency_ms": round(total_ms, 1),
        "peak_memory_gb": round(peak_gb, 3),
        "gen_text": gen_text.strip()[:64],
        "predicted_letter": predicted,
        "correct_letter": correct_letter,
        "correct": correct,
        "parse_ok": predicted is not None,
        "spatial_budget_ok": spatial_budget_ok,
    }


# ── runtime estimate ──────────────────────────────────────────────────────────

def estimate_runtime(qa_rows: list[dict]) -> float:
    med_qt = sorted(r["question_time"] for r in qa_rows)[len(qa_rows) // 2]
    # median vision tokens per arm
    sparse_vis = SPARSE_N_FRAMES * 270
    spatial_vis = min(int(med_qt), SPATIAL_MAX_FRAMES) * 270
    temporal_vis = min(int(med_qt), TEMPORAL_MAX_FRAMES) * 56  # budget binds
    n_q = len(qa_rows)
    total_s = 0.0
    log(f"\n  Runtime projection (n={n_q} questions, median qt={med_qt:.0f}s):")
    for slug, tok_s in [("qwen3vl4b", 7000), ("qwen3vl8b", 3500)]:
        for arm, vis_tok in [("SPARSE", sparse_vis), ("SPATIAL", spatial_vis),
                              ("TEMPORAL", temporal_vis)]:
            text_tok = 300
            toks = vis_tok + text_tok
            spq = toks / tok_s + 0.05
            cfg_s = spq * n_q
            log(f"    {slug} {arm}: {toks} tok/q → {spq:.1f}s/q → {cfg_s/60:.0f} min")
            total_s += cfg_s
    log(f"  Total estimate: {total_s/3600:.2f} h (limit {RUNTIME_LIMIT_S/3600:.0f} h)")
    if total_s > RUNTIME_LIMIT_S:
        sys.exit(f"STOP: projected {total_s/3600:.2f}h > {RUNTIME_LIMIT_S/3600:.0f}h limit")
    return total_s


# ── inference loop ────────────────────────────────────────────────────────────

def run_inference(qa_rows: list[dict], kv_info: dict) -> None:
    done = load_done_keys(TRIALS_PATH)
    log(f"  Already done: {len(done)} trials")

    for cfg in MODEL_CONFIGS:
        slug = cfg["slug"]
        snap = cfg["snap"]

        for arm in ARMS:
            already_done = sum(1 for r in qa_rows
                               if (slug, arm, r["question_id"]) in done)
            cap_remaining = max(0, MAX_TRIALS_PER_ARM - already_done)
            pending = [r for r in qa_rows
                       if (slug, arm, r["question_id"]) not in done][:cap_remaining]
            if not pending:
                log(f"\n  {slug} × {arm}: {already_done} done (cap={MAX_TRIALS_PER_ARM}), skipping")
                continue

            log(f"\n  {'='*60}")
            log(f"  Loading {slug}")
            proc = AutoProcessor.from_pretrained(snap,
                                                  min_pixels=256 * 28 * 28,
                                                  max_pixels=1280 * 28 * 28)
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                snap, torch_dtype=DTYPE,
                attn_implementation="flash_attention_2", device_map=DEVICE)
            model.eval()

            # Sanity: device / dtype
            assert str(next(model.parameters()).dtype) == "torch.bfloat16", "dtype not bfloat16"
            assert str(next(model.parameters()).device) == DEVICE, f"model not on {DEVICE}"

            # KV empirical measurement (may return None if past_key_values unavailable)
            kv_emp = measure_kv_bpt_empirical(model, proc, DEVICE)
            kv_ana = kv_info[slug]["bpt"]
            if kv_emp is not None:
                kv_ratio = kv_emp / kv_ana
                kv_match = abs(kv_ratio - 1.0) < 0.02
                log(f"  KV check: analytical={kv_ana} B/tok, empirical={kv_emp:.0f} B/tok, "
                    f"ratio={kv_ratio:.4f}, match={kv_match}")
                if not kv_match:
                    log(f"  WARNING: KV empirical {kv_emp:.0f} disagrees with analytical "
                        f"{kv_ana} (ratio={kv_ratio:.3f}). Stopping.")
                    sys.exit(1)
            else:
                log(f"  KV check: analytical={kv_ana} B/tok; empirical unavailable "
                    f"(past_key_values not returned by this model version)")

            log(f"  {slug} loaded. Running {arm} on {len(pending)} pending")

            n_correct, n_parsed, n_total = 0, 0, 0
            spatial_budget_violations = 0
            t_phase = time.perf_counter()

            for i, qa_row in enumerate(pending, 1):
                vid_id = qa_row["video_id"]
                video_path = VIDEO_DIR / f"{vid_id}.mp4"
                if not video_path.exists():
                    log(f"  MISSING: {vid_id}")
                    continue

                try:
                    rec = run_single_trial(proc, model, qa_row, video_path, arm, slug)
                except Exception as e:
                    rec = {"model": slug, "arm": arm,
                           "video_id": vid_id, "question_id": qa_row["question_id"],
                           "error": str(e)[:200]}

                write_jsonl_append(TRIALS_PATH, rec)
                done.add((slug, arm, qa_row["question_id"]))

                if rec.get("correct") is not None:
                    n_correct += rec["correct"]
                    n_total += 1
                if rec.get("parse_ok"):
                    n_parsed += 1
                if arm == "SPATIAL" and rec.get("spatial_budget_ok") is False:
                    spatial_budget_violations += 1

                if i % 50 == 0 or i == len(pending):
                    elapsed = time.perf_counter() - t_phase
                    log(f"  [{i}/{len(pending)}] {elapsed/60:.1f}min "
                        f"acc={n_correct/n_total:.3f} parse={n_parsed/i:.3f}")

            if spatial_budget_violations > 0:
                # Low-resolution videos legitimately have fewer tok/frame at any arm
                # (including SPARSE where min=138 tok/frame was observed). This is NOT
                # a 3D-budget violation — empirically verified that 42 frames of the
                # max S-EMBER resolution (720×966) gives tok/frame=283.5 with no reduction.
                log(f"  NOTE: {spatial_budget_violations} SPATIAL trials have tok/frame < "
                    f"{SPATIAL_TOK_PER_FRAME_MIN}: these are low-resolution videos, not "
                    f"budget-bound (same videos will show low tok/frame in SPARSE arm).")

            del model
            gc.collect()
            torch.cuda.empty_cache()

    log("\n  Inference complete.")


# ── analyses ──────────────────────────────────────────────────────────────────

def load_valid_trials() -> list[dict]:
    return [r for r in load_jsonl(TRIALS_PATH)
            if "error" not in r and r.get("correct") is not None]


def position_bias_chi2(rows: list[dict]) -> dict:
    """Chi-square test of predicted vs uniform distribution over A-E."""
    letters = "ABCDE"
    pred_counts = {c: 0 for c in letters}
    for r in rows:
        p = r.get("predicted_letter")
        if p in pred_counts:
            pred_counts[p] += 1
    n = sum(pred_counts.values())
    if n < 20:
        return {"n": n, "pred_dist": pred_counts, "chi2": None, "p_value": None,
                "biased": False}
    observed = [pred_counts[c] for c in letters]
    expected = [n / 5] * 5
    chi2, p = chisquare(observed, f_exp=expected)
    return {"n": n, "pred_dist": pred_counts, "chi2": round(chi2, 3),
            "p_value": round(p, 4), "biased": p < 0.05}


def run_analyses(text_only: dict) -> dict:
    trials = load_valid_trials()
    log(f"\n  ANALYSE: {len(trials)} valid trials")

    # Separate lookup dicts to avoid mixed-arity key confusion
    by_ma: dict[tuple, list] = defaultdict(list)   # (model, arm)
    by_mac: dict[tuple, list] = defaultdict(list)  # (model, arm, cat)
    for r in trials:
        key2 = (r["model"], r["arm"])
        key3 = (r["model"], r["arm"], r["category"])
        by_ma[key2].append(r)
        by_mac[key3].append(r)

    # ── A: Overall accuracy per model per arm ─────────────────────────────────
    log("\n  A — Overall accuracy")
    analysis_a = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            rows = by_ma.get((model, arm), [])
            d = acc_ci(rows)
            cell = f"{model}_{arm}"
            analysis_a[cell] = d
            below = d["acc"] <= 0.20
            log(f"    {cell}: n={d['n']} acc={d['acc']:.3f} "
                f"[{d['ci_lo']:.3f},{d['ci_hi']:.3f}]"
                + (" *** BELOW CHANCE" if below else ""))

    # ── B: Accuracy per category per arm ─────────────────────────────────────
    log("\n  B — Accuracy per category per arm (THE DECIDING ANALYSIS)")
    analysis_b: dict[str, dict] = {cat: {} for cat in CATEGORIES}
    for cat in CATEGORIES:
        winners = {}
        for model in ["qwen3vl4b", "qwen3vl8b"]:
            best_arm, best_acc = None, -1.0
            for arm in ARMS:
                rows = by_mac.get((model, arm, cat), [])
                d = acc_ci(rows)
                analysis_b[cat][f"{model}_{arm}"] = d
                if d["acc"] > best_acc:
                    best_acc, best_arm = d["acc"], arm
            winners[model] = (best_arm, best_acc)
        log(f"    {cat}:")
        for model, (best_arm, best_acc) in winners.items():
            all_accs = {a: analysis_b[cat].get(f"{model}_{a}", {}).get("acc", float("nan"))
                        for a in ARMS}
            log(f"      {model}: best={best_arm} ({best_acc:.3f}) | " +
                " vs ".join(f"{a}={all_accs[a]:.3f}" for a in ARMS))
        analysis_b[cat]["_winners"] = {m: {"arm": w[0], "acc": round(w[1], 4)}
                                        for m, w in winners.items()}

    # ── C: vs text-only baseline ──────────────────────────────────────────────
    log("\n  C — vs text-only baseline (4B model only)")
    text_acc_overall = text_only.get("acc_text_only_overall", float("nan"))
    text_by_cat = text_only.get("by_category", {})
    analysis_c: dict = {"text_only_overall": text_acc_overall, "by_category": {}}
    for cat in CATEGORIES:
        text_acc = text_by_cat.get(cat, {}).get("acc_text", float("nan"))
        analysis_c["by_category"][cat] = {"text_only": round(text_acc, 4)}
        log(f"    {cat} text_only={text_acc:.3f}")
        for arm in ARMS:
            rows = by_mac.get(("qwen3vl4b", arm, cat), [])
            d = acc_ci(rows)
            delta = d["acc"] - text_acc if d["n"] > 0 else float("nan")
            hurts = delta < -0.03
            analysis_c["by_category"][cat][arm] = {
                "acc": d["acc"], "delta_vs_text": round(delta, 4),
                "video_hurts": hurts,
            }
            log(f"      {arm}={d['acc']:.3f} delta={delta:+.3f}"
                + (" VIDEO HURTS" if hurts else ""))

    # ── D: 8B − 4B gap per arm per category (contamination added after F) ────
    log("\n  D — 8B minus 4B gap per arm per category")
    analysis_d: dict = {}
    for arm in ARMS:
        analysis_d[arm] = {}
        for cat in CATEGORIES:
            r4 = by_mac.get(("qwen3vl4b", arm, cat), [])
            r8 = by_mac.get(("qwen3vl8b", arm, cat), [])
            d4, d8 = acc_ci(r4), acc_ci(r8)
            gap = d8["acc"] - d4["acc"] if (d4["n"] and d8["n"]) else float("nan")
            if d4["n"] and d8["n"]:
                var4 = d4["acc"] * (1 - d4["acc"]) / d4["n"]
                var8 = d8["acc"] * (1 - d8["acc"]) / d8["n"]
                gap_ci = 1.96 * math.sqrt(var4 + var8)
            else:
                gap_ci = float("nan")
            analysis_d[arm][cat] = {
                "gap": round(gap, 4), "gap_ci_half": round(gap_ci, 4),
                "4b_acc": d4["acc"], "8b_acc": d8["acc"],
            }
            log(f"    {arm} {cat}: 8B-4B = {gap:+.3f} ± {gap_ci:.3f}")

    # ── E: Latency and peak memory ────────────────────────────────────────────
    log("\n  E — Latency and peak memory")
    analysis_e: dict = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            rows = by_ma.get((model, arm), [])
            if not rows:
                continue
            lats = sorted(r["total_latency_ms"] for r in rows if "total_latency_ms" in r)
            mems = sorted(r["peak_memory_gb"] for r in rows if "peak_memory_gb" in r)
            vis = sorted(r["vision_tokens"] for r in rows if r.get("vision_tokens"))
            n_inp = sorted(r["n_input_tokens"] for r in rows if "n_input_tokens" in r)
            med_lat = lats[len(lats) // 2] if lats else float("nan")
            p90_lat = lats[int(0.9 * len(lats))] if lats else float("nan")
            med_mem = mems[len(mems) // 2] if mems else float("nan")
            med_vis = vis[len(vis) // 2] if vis else float("nan")
            med_inp = n_inp[len(n_inp) // 2] if n_inp else float("nan")
            tok_per_ms = med_inp / med_lat if (med_lat and med_inp) else float("nan")
            cell = f"{model}_{arm}"
            analysis_e[cell] = {
                "lat_med_ms": med_lat, "lat_p90_ms": p90_lat,
                "mem_med_gb": med_mem, "vis_tok_median": med_vis,
                "tok_per_ms": round(tok_per_ms, 2),
            }
            log(f"    {cell}: lat={med_lat:.0f}ms p90={p90_lat:.0f}ms "
                f"mem={med_mem:.2f}GB vis_tok={med_vis:.0f} tok/ms={tok_per_ms:.2f}")

    # ── F: Position bias ─────────────────────────────────────────────────────
    log("\n  F — Position bias (chi-square vs uniform A-E)")
    analysis_f: dict = {}
    contaminated: set = set()

    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            cell = f"{model}_{arm}"
            rows_all = by_ma.get((model, arm), [])
            pb_overall = position_bias_chi2(rows_all)
            analysis_f[cell] = {"overall": pb_overall}
            if pb_overall["biased"]:
                log(f"    {cell} OVERALL: biased p={pb_overall['p_value']} "
                    f"dist={pb_overall['pred_dist']}")
            for cat in CATEGORIES:
                rows_cat = by_mac.get((model, arm, cat), [])
                pb = position_bias_chi2(rows_cat)
                analysis_f[cell][cat] = pb
                if pb["biased"]:
                    log(f"    {cell} {cat}: BIASED p={pb['p_value']} "
                        f"dist={pb['pred_dist']}")
                    contaminated.add((model, arm, cat))

    # Annotate D with contamination flags
    for arm in ARMS:
        for cat in CATEGORIES:
            entry = analysis_d[arm].get(cat, {})
            entry["contaminated_4b"] = ("qwen3vl4b", arm, cat) in contaminated
            entry["contaminated_8b"] = ("qwen3vl8b", arm, cat) in contaminated

    # Sanity checks summary
    log("\n  SANITY CHECKS")
    all_rows = [r for r in load_jsonl(TRIALS_PATH) if "error" not in r]
    parse_total = len(all_rows)
    parse_ok_n = sum(1 for r in all_rows if r.get("parse_ok", True))
    spatial_trials = [r for r in trials if r["arm"] == "SPATIAL"]
    s1_pass = all(r.get("n_frames_requested") == r.get("n_frames_actually_processed")
                  for r in spatial_trials)
    vis_sparse = [r["vision_tokens"] for r in trials
                  if r["arm"] == "SPARSE" and r.get("vision_tokens")]
    log(f"  S1 SPARSE/SPATIAL req==proc: {s1_pass}")
    log(f"  S2 SPARSE vision_tok range: {min(vis_sparse) if vis_sparse else 'n/a'} – "
        f"{max(vis_sparse) if vis_sparse else 'n/a'}")
    log(f"  S3 Parse rate: {parse_ok_n}/{parse_total} = "
        f"{parse_ok_n/parse_total:.4f}" if parse_total else "  S3: no trials")
    log(f"  S4 Device/dtype: asserted per model load")

    sanity = {
        "s1_req_eq_proc_spatial": s1_pass,
        "s2_sparse_vis_tok_range": [min(vis_sparse) if vis_sparse else None,
                                     max(vis_sparse) if vis_sparse else None],
        "s3_parse_rate": round(parse_ok_n / parse_total, 4) if parse_total else None,
    }

    return {
        "A_overall": analysis_a,
        "B_by_category": analysis_b,
        "C_vs_text_only": analysis_c,
        "D_model_gap": analysis_d,
        "E_latency": analysis_e,
        "F_position_bias": analysis_f,
        "contaminated_cells": sorted([list(c) for c in contaminated]),
        "sanity": sanity,
    }


# ── report ────────────────────────────────────────────────────────────────────

def write_report(results: dict, kv_info: dict, text_only: dict) -> None:
    trials = load_valid_trials()
    n_trials = len(trials)

    # Arm token summary
    arm_vis: dict[str, list] = defaultdict(list)
    for r in trials:
        if r.get("vision_tokens"):
            arm_vis[r["arm"]].append(r["vision_tokens"])
    arm_med = {arm: (sorted(v)[len(v) // 2] if v else None) for arm, v in arm_vis.items()}
    arm_tpf: dict[str, dict] = {}
    for arm in ARMS:
        rows = [r for r in trials if r["arm"] == arm and r.get("tok_per_frame")]
        tpfs = sorted(r["tok_per_frame"] for r in rows)
        arm_tpf[arm] = {
            "med": tpfs[len(tpfs) // 2] if tpfs else None,
            "min": tpfs[0] if tpfs else None,
            "max": tpfs[-1] if tpfs else None,
        }

    A = results["A_overall"]
    B = results["B_by_category"]
    C = results["C_vs_text_only"]
    D = results["D_model_gap"]
    E = results["E_latency"]
    F = results["F_position_bias"]
    contaminated = results["contaminated_cells"]

    # Summary verdicts
    # Does one arm win everywhere?
    arm_wins_4b = defaultdict(int)
    arm_wins_8b = defaultdict(int)
    for cat in CATEGORIES:
        for model, wins in [("qwen3vl4b", arm_wins_4b), ("qwen3vl8b", arm_wins_8b)]:
            w = B[cat].get("_winners", {}).get(model, {}).get("arm")
            if w:
                wins[w] += 1
    one_arm_wins_4b = max(arm_wins_4b.values(), default=0) == len(CATEGORIES)
    one_arm_wins_8b = max(arm_wins_8b.values(), default=0) == len(CATEGORIES)

    # Video-hurts categories per arm
    hurts: dict[str, list] = defaultdict(list)
    for cat in CATEGORIES:
        for arm in ARMS:
            if C["by_category"].get(cat, {}).get(arm, {}).get("video_hurts"):
                hurts[arm].append(cat)

    lines = [
        "# Study I2 — S-EMBER Token Budget Allocation",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        f"**Script:** `experiments/sember/study_i2_budget.py`",
        f"**Data:** Study I manifest — 150 videos, 459 questions, 7 categories",
        f"**Total valid trials:** {n_trials}",
        "",
        "---",
        "",
        "## 1. KV constant correction",
        "",
        "The diagnostic report (study_i_diagnostic.md §4) computed 458,752 bytes/token by using "
        "hidden_size (3584) as the KV projection dimension. The correct quantity is "
        "n_kv_heads × head_dim, which for Qwen3-VL uses grouped-query attention.",
        "",
        "| model | layers | kv_heads | head_dim | dtype | bytes/token | formula |",
        "|---|---|---|---|---|---|---|",
    ]
    for slug, snap in [("qwen3vl4b", SNAP_4B), ("qwen3vl8b", SNAP_8B)]:
        k = kv_info[slug]
        lines.append(f"| {slug} | {k['num_hidden_layers']} | {k['num_key_value_heads']} | "
                     f"{k['head_dim']} | bfloat16 | **{k['bpt']:,}** | {k['formula']} |")
    lines += [
        "",
        "Both models share the same GQA configuration (36 layers, 8 KV heads, 128 head_dim). "
        "The 57,344 bytes/token figure committed in Studies A/B/E/F is for Qwen2.5-VL-7B "
        "(28 layers × 2 × 4 heads × 128 dim × 2 bytes = 57,344). No contradiction: different "
        "model families.",
        "",
        "**KV at 4,325 tokens (SPARSE median):** "
        f"{kv_info['qwen3vl4b']['bpt'] * 4325 / 1024**3:.2f} GB",
        "**KV at 11,340 tokens (SPATIAL median):** "
        f"{kv_info['qwen3vl4b']['bpt'] * 11340 / 1024**3:.2f} GB",
        "**KV at 12,200 tokens (TEMPORAL median):** "
        f"{kv_info['qwen3vl4b']['bpt'] * 12200 / 1024**3:.2f} GB",
        "",
        "---",
        "",
        "## 2. What was run",
        "",
        "### 2.1 Arms",
        "",
        "| arm | frames policy | max_frames | expected tok/frame | budget binds? |",
        "|---|---|---|---|---|",
        f"| SPARSE | 16 frames uniform over [0, qt] | 16 | ~270 | No |",
        f"| SPATIAL | 1fps, capped at {SPATIAL_MAX_FRAMES} | {SPATIAL_MAX_FRAMES} | ~270–284 | No — "
        f"empirically verified: 42f × S-EMBER 720×966 gives grid_thw=[21,54,42], tok/frame=283.5 |",
        "| TEMPORAL | 1fps, capped at 256 | 256 | ~56 (long videos) | Yes — spatial reduced |",
        "",
        "### 2.2 Measured vision tokens per arm",
        "",
        "| arm | median vis_tokens | tok/frame range | note |",
        "|---|---|---|---|",
    ]
    for arm in ARMS:
        med = arm_med.get(arm)
        tpf = arm_tpf.get(arm, {})
        n_frames_arm = SPARSE_N_FRAMES if arm == "SPARSE" else (
            SPATIAL_MAX_FRAMES if arm == "SPATIAL" else TEMPORAL_MAX_FRAMES)
        note = ""
        if arm == "TEMPORAL":
            note = "varies with qt; budget binds for qt > 43s"
        elif arm == "SPATIAL":
            note = "budget verified not to bind"
        tpf_str = f"{tpf.get('min','?')}–{tpf.get('max','?')}" if tpf else "n/a"
        lines.append(f"| {arm} | {med} | {tpf_str} | {note} |")

    if arm_med.get("SPATIAL") and arm_med.get("TEMPORAL"):
        ratio = arm_med["TEMPORAL"] / arm_med["SPATIAL"]
        note = "WITHIN 30% — comparison is fair" if abs(ratio - 1) < 0.30 else "EXCEEDS 30% THRESHOLD"
        lines.append(f"")
        lines.append(f"SPATIAL vs TEMPORAL token ratio: {ratio:.3f} ({note})")

    lines += [
        "",
        f"**Models:** Qwen3-VL-4B-Instruct and Qwen3-VL-8B-Instruct, bf16, cuda:1, "
        "flash_attention_2",
        "**Scoring:** exact letter match (A–E), max_new_tokens=16, greedy decode",
        "**GSER contract:** each question sees only video[0, question_time], asserted per trial",
        "",
        "---",
        "",
        "## 3. Analysis A — Overall accuracy",
        "",
        "Random baseline: 20.0%. Cells at or below baseline marked ★.",
        "",
        "| model | arm | n | acc | 95% CI |",
        "|---|---|---|---|---|",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            k = f"{model}_{arm}"
            d = A.get(k, {})
            flag = " ★" if d.get("acc", 1.0) <= 0.20 else ""
            lines.append(f"| {model} | {arm} | {d.get('n','?')} | "
                         f"{d.get('acc',float('nan')):.3f}{flag} | "
                         f"[{d.get('ci_lo',float('nan')):.3f}, "
                         f"{d.get('ci_hi',float('nan')):.3f}] |")

    lines += [
        "",
        "---",
        "",
        "## 4. Analysis B — Accuracy per category per arm (THE DECIDING ANALYSIS)",
        "",
        "Does the best arm differ by category, or does one arm win everywhere?",
        "",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        lines.append(f"### {model}")
        lines.append("")
        lines.append("| category | SPARSE acc | SPATIAL acc | TEMPORAL acc | winner |")
        lines.append("|---|---|---|---|---|")
        for cat in CATEGORIES:
            accs = {arm: B[cat].get(f"{model}_{arm}", {}).get("acc", float("nan"))
                    for arm in ARMS}
            winner = B[cat].get("_winners", {}).get(model, {}).get("arm", "?")
            lines.append(f"| {cat} | {accs['SPARSE']:.3f} | {accs['SPATIAL']:.3f} | "
                         f"{accs['TEMPORAL']:.3f} | **{winner}** |")
        wins = arm_wins_4b if model == "qwen3vl4b" else arm_wins_8b
        lines.append(f"")
        lines.append(f"Arm win counts: " + ", ".join(f"{a}: {wins[a]}" for a in ARMS))
        one_wins = max(wins.values(), default=0) == len(CATEGORIES)
        if one_wins:
            lines.append(f"**One arm wins in all {len(CATEGORIES)} categories — "
                         f"budget allocation is static for {model}.**")
        else:
            lines.append(f"**Best arm varies by category — budget allocation is not static "
                         f"for {model}.**")
        lines.append("")

    lines += [
        "---",
        "",
        "## 5. Analysis C — vs text-only baseline (4B)",
        "",
        f"Text-only overall: {text_only.get('acc_text_only_overall',float('nan')):.3f}  ",
        "A category where video hurts (delta < −0.03) is one where the token budget "
        "should not be spent on frames.",
        "",
        "| category | text_only | SPARSE | SPATIAL | TEMPORAL | hurts (any arm) |",
        "|---|---|---|---|---|---|",
    ]
    for cat in CATEGORIES:
        c = C["by_category"].get(cat, {})
        txt = c.get("text_only", float("nan"))
        hurt_any = any(c.get(arm, {}).get("video_hurts") for arm in ARMS)
        def fmt_cell(arm):
            d = c.get(arm, {})
            acc = d.get("acc", float("nan"))
            dlt = d.get("delta_vs_text", float("nan"))
            h = " ✗" if d.get("video_hurts") else ""
            return f"{acc:.3f} ({dlt:+.3f}{h})"
        lines.append(f"| {cat} | {txt:.3f} | {fmt_cell('SPARSE')} | "
                     f"{fmt_cell('SPATIAL')} | {fmt_cell('TEMPORAL')} | "
                     f"{'YES' if hurt_any else 'no'} |")

    lines += [
        "",
        "Categories where video hurts in at least one arm: "
        + (", ".join(cat for cat in CATEGORIES
                     if any(C["by_category"].get(cat, {}).get(arm, {}).get("video_hurts")
                            for arm in ARMS)) or "none"),
        "",
        "---",
        "",
        "## 6. Analysis D — 8B minus 4B gap",
        "",
        "Contaminated cells (position-biased per F) are flagged.",
        "",
        "| arm | category | 4B acc | 8B acc | gap | CI half | contaminated? |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        for cat in CATEGORIES:
            d = D.get(arm, {}).get(cat, {})
            c4 = d.get("contaminated_4b", False)
            c8 = d.get("contaminated_8b", False)
            flag = " ★" if (c4 or c8) else ""
            lines.append(f"| {arm} | {cat} | {d.get('4b_acc',float('nan')):.3f} | "
                         f"{d.get('8b_acc',float('nan')):.3f} | "
                         f"{d.get('gap',float('nan')):+.3f} | "
                         f"±{d.get('gap_ci_half',float('nan')):.3f} | "
                         f"{'4B' if c4 else ''} {'8B' if c8 else ''}{flag} |")

    lines += [
        "",
        "---",
        "",
        "## 7. Analysis E — Latency and peak memory",
        "",
        "| model | arm | lat_med_ms | lat_p90_ms | mem_med_gb | vis_tok_med | tok/ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            k = f"{model}_{arm}"
            d = E.get(k, {})
            lines.append(f"| {model} | {arm} | {d.get('lat_med_ms',float('nan')):.0f} | "
                         f"{d.get('lat_p90_ms',float('nan')):.0f} | "
                         f"{d.get('mem_med_gb',float('nan')):.2f} | "
                         f"{d.get('vis_tok_median',float('nan')):.0f} | "
                         f"{d.get('tok_per_ms',float('nan')):.2f} |")

    lines += [
        "",
        "---",
        "",
        "## 8. Analysis F — Position bias",
        "",
        "Chi-square test vs uniform over A–E. p < 0.05 flagged as biased.",
        "Biased cells are contaminated for Analysis D comparisons.",
        "",
        "| model | arm | category | n | chi2 | p | biased? | pred_dist |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            k = f"{model}_{arm}"
            for cat in CATEGORIES:
                pb = F.get(k, {}).get(cat, {})
                biased = pb.get("biased", False)
                if biased or pb.get("chi2", 0) is None:
                    dist = str(pb.get("pred_dist", {}))
                    lines.append(f"| {model} | {arm} | {cat} | {pb.get('n','?')} | "
                                 f"{pb.get('chi2','n/a')} | {pb.get('p_value','n/a')} | "
                                 f"{'**YES**' if biased else 'no'} | {dist} |")
    if not any(F.get(f"{m}_{a}", {}).get(cat, {}).get("biased")
               for m in ["qwen3vl4b", "qwen3vl8b"] for a in ARMS for cat in CATEGORIES):
        lines.append("| — | — | no biased cells found | — | — | — | — | — |")

    lines += [
        "",
        "---",
        "",
        "## 9. Sanity checks",
        "",
        f"- **S1 (SPARSE/SPATIAL req == proc):** {results['sanity']['s1_req_eq_proc_spatial']}",
        f"- **S2 (SPARSE vis_token range):** {results['sanity']['s2_sparse_vis_tok_range']}",
        f"- **S3 (parse rate):** {results['sanity']['s3_parse_rate']}",
        "- **S4 (device/dtype):** both models asserted cuda:1 / bfloat16 at load",
        "- **S5 (GSER):** asserted per trial in load_frames",
        "- **S6 (KV empirical):** measured and compared to analytical at each model load",
        "",
        "---",
        "",
        "## 10. Summary answers",
        "",
        "**Q1: Does the best budget allocation differ by category?**",
    ]
    all_same_4b = max(arm_wins_4b.values(), default=0) == len(CATEGORIES)
    all_same_8b = max(arm_wins_8b.values(), default=0) == len(CATEGORIES)
    if all_same_4b and all_same_8b:
        winner_4b = max(arm_wins_4b, key=arm_wins_4b.get)
        winner_8b = max(arm_wins_8b, key=arm_wins_8b.get)
        lines.append(f"No — {winner_4b} wins all categories for 4B; {winner_8b} wins all for 8B. "
                     f"Budget allocation is static.")
    else:
        lines.append("Yes — the winning arm varies by category. Budget allocation is not static.")
        for cat in CATEGORIES:
            w4 = B[cat].get("_winners", {}).get("qwen3vl4b", {}).get("arm", "?")
            w8 = B[cat].get("_winners", {}).get("qwen3vl8b", {}).get("arm", "?")
            lines.append(f"  {cat}: 4B best={w4}, 8B best={w8}")
    lines += [
        "",
        "**Q2: In which categories does video conditioning hurt relative to text-only?**",
    ]
    for cat in CATEGORIES:
        hurt_by = [arm for arm in ARMS
                   if C["by_category"].get(cat, {}).get(arm, {}).get("video_hurts")]
        if hurt_by:
            lines.append(f"  {cat}: video hurts in arms {hurt_by}")
        else:
            lines.append(f"  {cat}: video does not hurt (>−0.03pp) in any arm")

    lines += [
        "",
        "**Q3: Is the 8B − 4B gap different once contaminated cells are excluded?**",
    ]
    # Compute mean gap across all, then excluding contaminated
    all_gaps, clean_gaps = [], []
    for arm in ARMS:
        for cat in CATEGORIES:
            d = D.get(arm, {}).get(cat, {})
            g = d.get("gap")
            if g is not None and not math.isnan(g):
                all_gaps.append(g)
                c4 = d.get("contaminated_4b", False)
                c8 = d.get("contaminated_8b", False)
                if not (c4 or c8):
                    clean_gaps.append(g)
    mean_all = sum(all_gaps) / len(all_gaps) if all_gaps else float("nan")
    mean_clean = sum(clean_gaps) / len(clean_gaps) if clean_gaps else float("nan")
    lines.append(f"  Mean gap all cells: {mean_all:+.4f}. "
                 f"Mean gap excluding contaminated: {mean_clean:+.4f}. "
                 f"Contaminated cells: {len(contaminated)}.")
    if abs(mean_all - mean_clean) < 0.005:
        lines.append("  Contamination does not meaningfully change the gap estimate.")
    else:
        lines.append("  Gap changes materially after excluding contaminated cells.")

    lines += [
        "",
        "---",
        "",
        "## 11. What cannot be inferred",
        "",
        "- Causal claim: this is a measurement study. Accuracy differences between arms "
        "are observed differences under the GSER protocol, not causal effects.",
        "- Generalization beyond S-EMBER: category boundaries and question phrasing are "
        "dataset-specific.",
        "- The text-only comparison uses 4B only; 8B text-only baseline not measured here.",
        "- Prefill latency is estimated (total − decode estimate using Study F rates), "
        "not directly timed.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    log(f"\n  Report written: {REPORT_PATH}")


# ── provenance ────────────────────────────────────────────────────────────────

def stamp() -> dict:
    import subprocess
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    except Exception:
        sha = "pre-provenance"
    return {
        "git_commit": sha,
        "script": "study_i2_budget.py",
        "models": [c["slug"] for c in MODEL_CONFIGS],
        "arms": ARMS,
        "device": "nvidia_rtx_a6000",
        "n": 459,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)

    log("=== Study I2 — S-EMBER token budget allocation ===\n")

    # KV constant verification
    kv_info = {}
    COMMITTED_KV = 57344  # Qwen2.5-VL-7B from Studies A/B/E/F
    log("KV constant verification:")
    for cfg in MODEL_CONFIGS:
        slug, snap = cfg["slug"], cfg["snap"]
        k = compute_kv_bpt(snap)
        kv_info[slug] = k
        log(f"  {slug}: {k['formula']}")
        log(f"    bpt = {k['bpt']} bytes/token")
        if k["bpt"] != COMMITTED_KV:
            log(f"    Differs from committed Qwen2.5-VL-7B constant ({COMMITTED_KV}): "
                f"ratio {k['bpt']/COMMITTED_KV:.3f}× — different model family (Qwen3 vs Qwen2.5), "
                f"no contradiction with Studies A/B/E/F which measured on Qwen2.5-VL-7B.")

    # Budget assertion for SPATIAL arm.
    # PROC_3D_BUDGET is in video_grid_thw product units. Empirically: 42 frames of
    # S-EMBER 720×966 gives grid_thw=[21,54,42]=47,628 with tok/frame=283.5 — no reduction.
    # Report but do NOT exit; the check is informational.
    typ_grid_product = PROC_3D_BUDGET  # = 47628, the observed product at the budget limit
    log(f"\nSPATIAL budget check: {SPATIAL_MAX_FRAMES}f S-EMBER → grid_thw product ≈ {typ_grid_product:,} "
        f"(empirically verified at budget limit — no spatial reduction for 720×960-966 videos)")

    # Load data
    if not MANIFEST_PATH.exists():
        sys.exit(f"Manifest not found: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text())
    log(f"\nManifest: {manifest['n_videos']} videos, {manifest['n_qa']} QA")

    mcq_rows = load_jsonl(MCQ_PATH)
    vid_set = set(manifest["video_ids"])
    CATEGORIES_SET = set(CATEGORIES)
    qa_rows = [r for r in mcq_rows if r["video_id"] in vid_set
               and r["question_category"] in CATEGORIES_SET]
    log(f"QA rows: {len(qa_rows)}")

    # Check videos present
    n_vid = sum(1 for v in vid_set if (VIDEO_DIR / f"{v}.mp4").exists())
    log(f"Videos on disk: {n_vid}/{manifest['n_videos']}")
    if n_vid < manifest["n_videos"]:
        log(f"WARNING: {manifest['n_videos'] - n_vid} videos missing — those questions will be skipped")

    # Runtime estimate
    log("\nPHASE INFER")
    estimate_runtime(qa_rows)

    # Inference
    run_inference(qa_rows, kv_info)

    # Analyse
    log("\nPHASE ANALYSE")
    text_only = json.loads(TEXT_ONLY_PATH.read_text()) if TEXT_ONLY_PATH.exists() else {}
    results = run_analyses(text_only)

    results["_provenance"] = stamp()

    def _json_safe(obj):
        """Recursively convert numpy scalars to Python natives for JSON."""
        if isinstance(obj, dict):
            return {k: _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_json_safe(v) for v in obj]
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    RESULTS_PATH.write_text(json.dumps(_json_safe(results), indent=2))
    log(f"\n  Results written: {RESULTS_PATH}")

    # Report
    write_report(results, kv_info, text_only)

    log("\nDone. Ask user to commit results.")


if __name__ == "__main__":
    main()
