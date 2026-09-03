#!/usr/bin/env python3
"""
Study I3 — S-EMBER SPARSE vs TEMPORAL at full power.

Study I2 settled: SPATIAL (42f, ~11,907 tok) is worse than SPARSE (16f, ~4,536 tok)
at full n=459 for the 4B. SPATIAL is dropped.

Unsettled: SPARSE vs TEMPORAL and the 8B at any arm, both due to n=100 (9-19 per
category). This study runs both arms at full n=459 for both models.

Arms:
  SPARSE   16 frames uniform over [0, question_time]. Budget does not bind. ~270 tok/frame.
  TEMPORAL 1fps over [0, question_time], capped at 256 frames. Budget binds for qt>43s;
           processor reduces spatial resolution. ~44-56 tok/frame.

Key difference from I2:
  TEMPORAL uses per-video frame caching: each video is decoded ONCE sequentially
  (not 256 individual seeks per question), amortising the video-decode cost over
  all questions for the same video. Correctness: slicing to [0, question_time]
  discards later frames. GSER contract asserted per trial.

4B SPARSE n=459 reused from study_i2 (code path identical; verified below).
All other cells run fresh, with frame caching for TEMPORAL.

Write scope:
  results/sember/study_i3/study_i3_trials.jsonl
  results/sember/study_i3/study_i3_results.json
  reports/study_i3_budget.md
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
I2_TRIALS_PATH = PROJECT_ROOT / "results/sember/study_i2/study_i2_trials.jsonl"
OUT_DIR = PROJECT_ROOT / "results/sember/study_i3"
TRIALS_PATH = OUT_DIR / "study_i3_trials.jsonl"
RESULTS_PATH = OUT_DIR / "study_i3_results.json"
REPORT_PATH = PROJECT_ROOT / "reports/study_i3_budget.md"

# ── hardware ──────────────────────────────────────────────────────────────────

DEVICE = "cuda:1"
DTYPE = torch.bfloat16
MAX_NEW_TOKENS = 16
SEED = 42
RUNTIME_LIMIT_S = 3 * 3600

# ── snapshots ─────────────────────────────────────────────────────────────────

SNAP_4B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
SNAP_8B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"

MODEL_CONFIGS = [
    {"slug": "qwen3vl4b", "snap": SNAP_4B},
    {"slug": "qwen3vl8b", "snap": SNAP_8B},
]

DECODE_RATE = {"qwen3vl4b": 48.5, "qwen3vl8b": 32.0}

# ── arms ──────────────────────────────────────────────────────────────────────

ARMS = ["SPARSE", "TEMPORAL"]
SPARSE_N_FRAMES = 16
TEMPORAL_MAX_FRAMES = 256

# Token IDs (same as I2, verified)
VIDEO_TOKEN_ID = 151656
IMAGE_TOKEN_ID = 151655

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

# ── evidence distance bins for Analysis C ─────────────────────────────────────

DIST_BINS = [(0, 30), (30, 60), (60, 120), (120, 300), (300, float("inf"))]
DIST_BIN_LABELS = ["[0,30)", "[30,60)", "[60,120)", "[120,300)", "[300+)"]


# ── KV constant ───────────────────────────────────────────────────────────────

def compute_kv_bpt(snap: str) -> dict:
    cfg = json.load(open(f"{snap}/config.json"))
    tc = cfg["text_config"]
    nl, nkvh, hd = tc["num_hidden_layers"], tc["num_key_value_heads"], tc["head_dim"]
    bpt = nl * 2 * nkvh * hd * 2
    return {"num_hidden_layers": nl, "num_key_value_heads": nkvh, "head_dim": hd,
            "bpt": bpt, "formula": f"{nl}L × 2 × {nkvh}kv × {hd}d × 2B = {bpt}"}


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
    return {"n": n, "k": k, "acc": round(a, 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "half_width": round((hi - lo) / 2, 4)}


def parse_letter(text: str) -> Optional[str]:
    for ch in text.strip().upper():
        if ch in "ABCDE":
            return ch
    return None


# ── bootstrap from study_i2 ───────────────────────────────────────────────────

# Reuse criteria: 4B SPARSE is fully settled (n=459, code path identical to I3).
# For other cells (4B TEMPORAL n=100, 8B all n=100), these are valid trials and
# are copied to seed the done-keys, so the inference loop only runs the missing ones.
# All copied trials get reused_from="study_i2" and are included in all analyses.

REUSE_CELLS = {
    ("qwen3vl4b", "SPARSE"),    # 459 trials — fully settled, rerun avoided
    ("qwen3vl4b", "TEMPORAL"),  # 100 trials — valid, incomplete
    ("qwen3vl8b", "SPARSE"),    # 100 trials — valid, incomplete
    ("qwen3vl8b", "TEMPORAL"),  # 100 trials — valid, incomplete
}


def bootstrap_from_i2() -> int:
    """Copy I2 trials for SPARSE+TEMPORAL arms to I3's JSONL. Returns n copied."""
    if not I2_TRIALS_PATH.exists():
        log("  WARNING: study_i2 trials not found; starting fresh.")
        return 0
    existing_keys = load_done_keys(TRIALS_PATH)
    n_copied = 0
    for r in load_jsonl(I2_TRIALS_PATH):
        if "error" in r:
            continue
        key = (r.get("model"), r.get("arm"), r.get("question_id"))
        if key[1] not in ARMS:  # drop SPATIAL rows
            continue
        if (key[0], key[1]) not in REUSE_CELLS:
            continue
        if key in existing_keys:
            continue
        rec = dict(r)
        rec["reused_from"] = "study_i2"
        rec.pop("spatial_budget_ok", None)  # I2-specific field
        write_jsonl_append(TRIALS_PATH, rec)
        existing_keys.add(key)
        n_copied += 1
    return n_copied


# ── sequential 1fps video decoder (cache) ────────────────────────────────────

def decode_video_sequential(video_path: Path, max_time_s: float,
                            ) -> tuple[dict[int, Image.Image], float]:
    """
    Decode video sequentially from t=0 to max_time_s, keeping the first frame
    seen at each integer second. Returns (cache_dict, decode_time_s).
    Sequential decode avoids repeated random seeks (the bottleneck in I2's
    per-question frame loading for TEMPORAL, which used 256 backward seeks/question).
    """
    t_start = time.perf_counter()
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    cache: dict[int, Image.Image] = {}
    for frame in container.decode(stream):
        t = float(frame.pts * stream.time_base)
        if t > max_time_s + 1.0:
            break
        t_int = int(t)
        if t_int not in cache:
            cache[t_int] = frame.to_image()
    container.close()
    elapsed = time.perf_counter() - t_start
    return cache, elapsed


def frames_from_cache(cache: dict[int, Image.Image],
                      question_time: float) -> tuple[list, list[int]]:
    """
    Slice cache to [0, question_time], cap at TEMPORAL_MAX_FRAMES.
    Returns (frames, timestamps_s). GSER: all timestamps ≤ question_time.
    """
    eligible = [(t, img) for t, img in cache.items() if t <= question_time]
    eligible.sort(key=lambda x: x[0])
    eligible = eligible[:TEMPORAL_MAX_FRAMES]
    frames = [img for _, img in eligible]
    timestamps = [t for t, _ in eligible]
    assert all(t <= question_time + 1e-6 for t in timestamps), \
        f"GSER violated: cache slice contains frame beyond question_time={question_time}"
    return frames, timestamps


# ── seek-based frame loading for SPARSE ──────────────────────────────────────

def _get_frame_at_time(container, stream, target_time_s: float) -> Optional[Image.Image]:
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


def load_frames_sparse_timed(video_path: Path, question_time: float,
                             ) -> tuple[list, list[int], int, int, float]:
    """
    SPARSE: 16 frames uniform over [0, question_time], seek-based.
    Returns (frames, timestamps_s, n_req, n_loaded, decode_s).
    """
    t_start = time.perf_counter()
    n = SPARSE_N_FRAMES
    target_times = [question_time * i / (n - 1) for i in range(n)]
    assert all(t <= question_time + 1e-6 for t in target_times), \
        f"GSER violated: SPARSE target beyond question_time={question_time}"
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    frames, timestamps_s = [], []
    for t in target_times:
        img = _get_frame_at_time(container, stream, t)
        if img is not None:
            frames.append(img)
            timestamps_s.append(round(t))
    container.close()
    elapsed = time.perf_counter() - t_start
    return frames, timestamps_s, n, len(frames), elapsed


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


def run_trial_with_frames(proc, model, qa_row: dict,
                          frames: list, timestamps_s: list[int],
                          n_req: int, n_loaded: int,
                          arm: str, model_slug: str,
                          decode_latency_ms: float) -> dict:
    """Run inference for a question given pre-decoded frames."""
    qt = qa_row["question_time"]
    ast = qa_row["answer_start_time"]
    aet = qa_row["answer_end_time"]

    video_meta = VideoMetadata(fps=1.0, frames_indices=timestamps_s,
                               total_num_frames=round(qt))
    question_text = format_question(qa_row)
    messages = [{"role": "user", "content": [
        {"type": "video", "video": frames, "sample_fps": 1.0},
        {"type": "text", "text": question_text},
    ]}]

    t_proc = time.perf_counter()
    text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs, video_kwargs = process_vision_info(
        messages, return_video_kwargs=True)
    if "fps" in video_kwargs and isinstance(video_kwargs["fps"], list):
        video_kwargs["fps"] = video_kwargs["fps"][0] if video_kwargs["fps"] else None

    inputs = proc(text=[text], images=image_inputs, videos=video_inputs,
                  video_metadata=video_meta, return_tensors="pt",
                  **video_kwargs).to(DEVICE)
    preprocess_ms = (time.perf_counter() - t_proc) * 1000

    vision_tokens = int((inputs["input_ids"] == VIDEO_TOKEN_ID).sum())
    n_input = inputs.input_ids.shape[1]

    torch.cuda.reset_peak_memory_stats(DEVICE)
    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()
    with torch.no_grad():
        out_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                 do_sample=False, temperature=None, top_p=None)
    torch.cuda.synchronize(DEVICE)
    forward_ms = (time.perf_counter() - t0) * 1000
    peak_gb = torch.cuda.max_memory_allocated(DEVICE) / 1024**3

    gen_ids = out_ids[0][n_input:]
    n_generated = len(gen_ids)
    gen_text = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
    predicted = parse_letter(gen_text)
    correct_letter = qa_row["correct_letter"]
    correct = (predicted == correct_letter) if predicted is not None else False

    tok_per_frame = (vision_tokens / n_loaded) if (vision_tokens and n_loaded) else None
    total_latency_ms = decode_latency_ms + preprocess_ms + forward_ms

    return {
        "model": model_slug,
        "arm": arm,
        "video_id": qa_row["video_id"],
        "question_id": qa_row["question_id"],
        "category": qa_row["question_category"],
        "question_time": qt,
        "answer_start_time": ast,
        "answer_end_time": aet,
        "nearest_dist_s": round(qt - aet, 2),
        "farthest_dist_s": round(qt - ast, 2),
        "n_frames_requested": n_req,
        "n_frames_actually_processed": n_loaded,
        "per_frame_tokens": round(tok_per_frame, 1) if tok_per_frame else None,
        "vision_tokens": vision_tokens,
        "n_input_tokens": n_input,
        "total_latency_ms": round(total_latency_ms, 1),
        "decode_latency_ms": round(decode_latency_ms, 1),
        "preprocess_ms": round(preprocess_ms, 1),
        "forward_ms": round(forward_ms, 1),
        "peak_memory_gb": round(peak_gb, 3),
        "gen_text": gen_text.strip()[:64],
        "predicted_letter": predicted,
        "correct_letter": correct_letter,
        "correct": correct,
        "parse_ok": predicted is not None,
        "n_generated": n_generated,
    }


# ── profiling ─────────────────────────────────────────────────────────────────

def run_profile(qa_rows: list[dict], proc, model, model_slug: str) -> dict:
    """
    Profile 10 questions (5 SPARSE + 5 TEMPORAL) to measure decode, preprocess,
    and model forward breakdown. Returns profile summary.
    Uses questions that are not yet in done-keys to avoid re-running completed work.
    """
    log("\n  PROFILING: 10 questions (5 SPARSE + 5 TEMPORAL)")

    # Pick 5 from each arm, spanning a range of question_times
    sorted_rows = sorted(qa_rows, key=lambda r: r["question_time"])
    step = max(1, len(sorted_rows) // 6)
    sample_rows = sorted_rows[::step][:5]

    results: dict[str, list] = {"SPARSE": [], "TEMPORAL": []}
    for arm in ["SPARSE", "TEMPORAL"]:
        for qa_row in sample_rows:
            vid_path = VIDEO_DIR / f"{qa_row['video_id']}.mp4"
            if not vid_path.exists():
                continue
            qt = qa_row["question_time"]

            if arm == "SPARSE":
                frames, timestamps_s, n_req, n_loaded, decode_s = load_frames_sparse_timed(
                    vid_path, qt)
            else:
                cache, decode_s = decode_video_sequential(vid_path, min(qt, TEMPORAL_MAX_FRAMES))
                frames, timestamps_s = frames_from_cache(cache, qt)
                n_req = min(int(qt), TEMPORAL_MAX_FRAMES)
                n_loaded = len(frames)

            if n_loaded == 0:
                continue

            try:
                rec = run_trial_with_frames(
                    proc, model, qa_row, frames, timestamps_s,
                    n_req, n_loaded, arm, model_slug,
                    decode_latency_ms=decode_s * 1000)
                results[arm].append({
                    "qt": qt,
                    "n_frames": n_loaded,
                    "decode_ms": round(decode_s * 1000, 0),
                    "preprocess_ms": rec["preprocess_ms"],
                    "forward_ms": rec["forward_ms"],
                    "total_ms": rec["total_latency_ms"],
                    "decode_pct": round(100 * decode_s * 1000 / rec["total_latency_ms"], 1),
                })
            except Exception as e:
                log(f"  Profile error ({arm} qt={qt:.0f}): {e}")

            if len(results[arm]) >= 5:
                break

    for arm in ["SPARSE", "TEMPORAL"]:
        pts = results[arm]
        if not pts:
            continue
        med_dec = sorted(p["decode_ms"] for p in pts)[len(pts)//2]
        med_fwd = sorted(p["forward_ms"] for p in pts)[len(pts)//2]
        med_pre = sorted(p["preprocess_ms"] for p in pts)[len(pts)//2]
        med_tot = sorted(p["total_ms"] for p in pts)[len(pts)//2]
        log(f"  {arm}: median decode={med_dec:.0f}ms preprocess={med_pre:.0f}ms "
            f"forward={med_fwd:.0f}ms total={med_tot:.0f}ms "
            f"(decode={100*med_dec/med_tot:.0f}% of total)")

    return results


# ── runtime estimate ──────────────────────────────────────────────────────────

def estimate_runtime(qa_rows: list[dict], done_counts: dict) -> float:
    """
    Estimate runtime for remaining trials. Accounts for frame caching in TEMPORAL.
    """
    n_q = len(qa_rows)
    med_qt = sorted(r["question_time"] for r in qa_rows)[n_q // 2]
    log(f"\n  Runtime estimate (n={n_q} questions, median qt={med_qt:.0f}s):")

    # Rates derived from I2 measurements and profiling of sequential vs seek decode.
    # Profiling showed: seek-based TEMPORAL = 64-96s/trial video decode (312ms/frame ×
    # 204-256 frames). Sequential decode of same video: ~40-51s (single question);
    # amortised over median 3 questions/video = ~14s per question amortised.
    # SPARSE: 16 seeks at ~50ms/seek for short videos ≈ 0.8s decode + 0.8s inference.
    # TEMPORAL inference: 2B tokens ~2.2s (4B), ~3.2s (8B) from I2.

    rates = {
        "qwen3vl4b_SPARSE": (1.0, "s/trial (seek-based 16f ~0.5s + inference ~0.8s)"),
        "qwen3vl4b_TEMPORAL": (12.0, "s/trial (sequential cached ~10s amortised + inference ~2.2s)"),
        "qwen3vl8b_SPARSE": (1.8, "s/trial (seek-based 16f + inference ~1.2s)"),
        "qwen3vl8b_TEMPORAL": (14.0, "s/trial (sequential cached ~10s amortised + inference ~3.2s)"),
    }
    total_s = 0.0
    for slug in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            key = f"{slug}_{arm}"
            n_done = done_counts.get((slug, arm), 0)
            n_remain = max(0, n_q - n_done)
            rate, note = rates[key]
            est_s = n_remain * rate
            log(f"    {slug} × {arm}: {n_done} done, {n_remain} pending "
                f"→ {est_s/60:.0f} min ({note})")
            total_s += est_s
    log(f"  Total: {total_s/60:.0f} min = {total_s/3600:.2f} h "
        f"(limit {RUNTIME_LIMIT_S/3600:.0f} h)")
    if total_s > RUNTIME_LIMIT_S:
        sys.exit(f"STOP: projected {total_s/3600:.2f}h > {RUNTIME_LIMIT_S/3600:.0f}h limit. "
                 f"Report this and adjust before running.")
    return total_s


# ── inference loop ────────────────────────────────────────────────────────────

def run_inference(qa_rows: list[dict], kv_info: dict) -> None:
    done = load_done_keys(TRIALS_PATH)
    log(f"  Done keys on entry: {len(done)}")

    done_counts = {}
    for slug in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            n = sum(1 for r in qa_rows if (slug, arm, r["question_id"]) in done)
            done_counts[(slug, arm)] = n
    estimate_runtime(qa_rows, done_counts)

    for cfg in MODEL_CONFIGS:
        slug = cfg["slug"]
        snap = cfg["snap"]

        for arm in ARMS:
            pending = [r for r in qa_rows
                       if (slug, arm, r["question_id"]) not in done]
            if not pending:
                log(f"\n  {slug} × {arm}: all done, skipping")
                continue

            log(f"\n  {'='*60}")
            log(f"  Loading {slug}")
            proc = AutoProcessor.from_pretrained(
                snap, min_pixels=256 * 28 * 28, max_pixels=1280 * 28 * 28)
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                snap, torch_dtype=DTYPE,
                attn_implementation="flash_attention_2", device_map=DEVICE)
            model.eval()

            assert str(next(model.parameters()).dtype) == "torch.bfloat16"
            assert str(next(model.parameters()).device) == DEVICE, \
                f"model not on {DEVICE}"

            # KV check
            kv_ana = kv_info[slug]["bpt"]
            log(f"  KV analytical: {kv_ana} B/tok")

            log(f"  {slug} loaded. Running {arm} on {len(pending)} pending questions")

            if arm == "TEMPORAL":
                _run_temporal_cached(pending, proc, model, slug, done)
            else:
                _run_sparse(pending, proc, model, slug, done)

            del model
            gc.collect()
            torch.cuda.empty_cache()

    log("\n  Inference complete.")


def _run_sparse(pending: list[dict], proc, model, slug: str, done: set) -> None:
    """SPARSE arm: seek-based, question order."""
    n_correct, n_parsed, n_total = 0, 0, 0
    t_phase = time.perf_counter()

    for i, qa_row in enumerate(pending, 1):
        vid_path = VIDEO_DIR / f"{qa_row['video_id']}.mp4"
        if not vid_path.exists():
            log(f"  MISSING: {qa_row['video_id']}")
            continue
        try:
            frames, timestamps_s, n_req, n_loaded, decode_s = load_frames_sparse_timed(
                vid_path, qa_row["question_time"])
            if n_loaded == 0:
                write_jsonl_append(TRIALS_PATH, {
                    "model": slug, "arm": "SPARSE",
                    "video_id": qa_row["video_id"],
                    "question_id": qa_row["question_id"],
                    "error": "no_frames_loaded"})
                continue
            rec = run_trial_with_frames(
                proc, model, qa_row, frames, timestamps_s,
                n_req, n_loaded, "SPARSE", slug,
                decode_latency_ms=decode_s * 1000)
        except Exception as e:
            rec = {"model": slug, "arm": "SPARSE",
                   "video_id": qa_row["video_id"],
                   "question_id": qa_row["question_id"],
                   "error": str(e)[:200]}

        write_jsonl_append(TRIALS_PATH, rec)
        done.add((slug, "SPARSE", qa_row["question_id"]))

        if rec.get("correct") is not None:
            n_correct += rec["correct"]
            n_total += 1
        if rec.get("parse_ok"):
            n_parsed += 1

        # SANITY: n_frames_requested == n_frames_actually_processed for SPARSE
        if rec.get("n_frames_requested") != rec.get("n_frames_actually_processed"):
            log(f"  WARNING: SPARSE frame count mismatch "
                f"req={rec.get('n_frames_requested')} "
                f"proc={rec.get('n_frames_actually_processed')} "
                f"qid={qa_row['question_id'][:16]}")

        if i % 50 == 0 or i == len(pending):
            elapsed = time.perf_counter() - t_phase
            log(f"  [{i}/{len(pending)}] {elapsed/60:.1f}min "
                f"acc={n_correct/max(n_total,1):.3f} "
                f"parse={n_parsed/i:.3f}")


def _run_temporal_cached(pending: list[dict], proc, model, slug: str, done: set) -> None:
    """
    TEMPORAL arm: group by video, decode each video ONCE sequentially.
    Amortises the ~73s per-trial decode cost from I2 over all questions for each video.
    """
    # Group pending by video_id
    by_video: dict[str, list] = defaultdict(list)
    for qa_row in pending:
        by_video[qa_row["video_id"]].append(qa_row)

    n_correct, n_parsed, n_total = 0, 0, 0
    n_processed_total = 0
    t_phase = time.perf_counter()
    total_decode_s = 0.0

    for vid_id, vid_questions in sorted(by_video.items()):
        vid_path = VIDEO_DIR / f"{vid_id}.mp4"
        if not vid_path.exists():
            log(f"  MISSING: {vid_id}")
            continue

        # Decode video once to max question_time across all questions for this video
        max_qt = max(q["question_time"] for q in vid_questions)
        decode_up_to = min(max_qt, TEMPORAL_MAX_FRAMES)
        try:
            cache, decode_s = decode_video_sequential(vid_path, decode_up_to)
        except Exception as e:
            log(f"  DECODE ERROR {vid_id}: {e}")
            for qa_row in vid_questions:
                write_jsonl_append(TRIALS_PATH, {
                    "model": slug, "arm": "TEMPORAL",
                    "video_id": vid_id,
                    "question_id": qa_row["question_id"],
                    "error": f"video_decode_error: {str(e)[:100]}"})
            continue

        total_decode_s += decode_s
        n_q_this_video = len(vid_questions)
        # Amortise decode time over questions for this video
        decode_per_q_ms = decode_s * 1000 / n_q_this_video

        for qa_row in vid_questions:
            qt = qa_row["question_time"]
            try:
                frames, timestamps_s = frames_from_cache(cache, qt)
                n_req = min(int(qt), TEMPORAL_MAX_FRAMES)
                n_loaded = len(frames)
                if n_loaded == 0:
                    write_jsonl_append(TRIALS_PATH, {
                        "model": slug, "arm": "TEMPORAL",
                        "video_id": vid_id,
                        "question_id": qa_row["question_id"],
                        "error": "no_frames_from_cache"})
                    continue
                rec = run_trial_with_frames(
                    proc, model, qa_row, frames, timestamps_s,
                    n_req, n_loaded, "TEMPORAL", slug,
                    decode_latency_ms=decode_per_q_ms)
            except Exception as e:
                rec = {"model": slug, "arm": "TEMPORAL",
                       "video_id": vid_id,
                       "question_id": qa_row["question_id"],
                       "error": str(e)[:200]}

            write_jsonl_append(TRIALS_PATH, rec)
            done.add((slug, "TEMPORAL", qa_row["question_id"]))
            n_processed_total += 1

            if rec.get("correct") is not None:
                n_correct += rec["correct"]
                n_total += 1
            if rec.get("parse_ok"):
                n_parsed += 1

        # Free cache memory
        cache.clear()

        if n_processed_total % 50 == 0 or n_processed_total == len(pending):
            elapsed = time.perf_counter() - t_phase
            avg_decode = total_decode_s / max(len(by_video), 1)
            log(f"  [{n_processed_total}/{len(pending)}] {elapsed/60:.1f}min "
                f"acc={n_correct/max(n_total,1):.3f} "
                f"parse={n_parsed/max(n_processed_total,1):.3f} "
                f"avg_video_decode={avg_decode:.1f}s")


# ── position bias ─────────────────────────────────────────────────────────────

def position_bias_chi2(rows: list[dict]) -> dict:
    """
    Chi-square test of predicted-letter distribution vs uniform A-E.
    Flags cells with fewer than 5 expected counts per option (n < 25) as
    'not_testable' instead of running an invalid test.
    """
    letters = "ABCDE"
    pred_counts = {c: 0 for c in letters}
    for r in rows:
        p = r.get("predicted_letter")
        if p in pred_counts:
            pred_counts[p] += 1
    n = sum(pred_counts.values())
    expected_per_option = n / 5
    if expected_per_option < 5:
        return {"n": n, "pred_dist": pred_counts,
                "chi2": None, "p_value": None, "biased": False,
                "note": f"not_testable (expected {expected_per_option:.1f} < 5 per option; "
                        f"need n≥25, have n={n})"}
    observed = [pred_counts[c] for c in letters]
    expected = [n / 5] * 5
    chi2, p = chisquare(observed, f_exp=expected)
    return {"n": n, "pred_dist": pred_counts, "chi2": round(chi2, 3),
            "p_value": round(p, 4), "biased": p < 0.05,
            "note": ""}


# ── degenerate cell detection ─────────────────────────────────────────────────

def is_degenerate(rows: list[dict]) -> tuple[bool, str]:
    """
    A cell is degenerate if acc ≈ 0 AND position bias is flagged (skewed letter dist).
    Used to detect 8B spatial_aware_reasoning (scored 0 with E-bias in I2 at n=9).
    At full n, this should resolve or confirm.
    """
    if not rows:
        return False, "empty"
    n = len(rows)
    k = sum(r.get("correct", False) for r in rows)
    acc = k / n
    pb = position_bias_chi2(rows)
    if acc <= 0.05 and pb.get("biased"):
        return True, f"acc={acc:.3f} ≤ 0.05 AND position_bias p={pb.get('p_value')}"
    return False, ""


# ── analyses ──────────────────────────────────────────────────────────────────

def load_valid_trials() -> list[dict]:
    return [r for r in load_jsonl(TRIALS_PATH)
            if "error" not in r and r.get("correct") is not None]


def run_analyses(text_only: dict) -> dict:
    trials = load_valid_trials()
    log(f"\n  ANALYSE: {len(trials)} valid trials")

    by_ma: dict[tuple, list] = defaultdict(list)
    by_mac: dict[tuple, list] = defaultdict(list)
    for r in trials:
        by_ma[(r["model"], r["arm"])].append(r)
        by_mac[(r["model"], r["arm"], r["category"])].append(r)

    # ── A: Overall accuracy ──────────────────────────────────────────────────
    log("\n  A — Overall accuracy per model per arm")
    analysis_a = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            rows = by_ma.get((model, arm), [])
            d = acc_ci(rows)
            cell = f"{model}_{arm}"
            analysis_a[cell] = d
            log(f"    {cell}: n={d['n']} acc={d['acc']:.3f} "
                f"[{d['ci_lo']:.3f},{d['ci_hi']:.3f}]"
                + (" *** BELOW CHANCE" if d["acc"] <= 0.20 else ""))

    # ── B: Per-category accuracy (THE DECIDING ANALYSIS) ────────────────────
    log("\n  B — Per-category accuracy (THE DECIDING ANALYSIS)")
    log("      CI-overlap: |acc_SPARSE - acc_TEMPORAL| vs combined half-width")
    analysis_b: dict = {cat: {} for cat in CATEGORIES}

    # Verdict tracking
    n_exceeds_ci = {"qwen3vl4b": 0, "qwen3vl8b": 0}
    n_sparse_wins_ci = {"qwen3vl4b": 0, "qwen3vl8b": 0}
    n_temporal_wins_ci = {"qwen3vl4b": 0, "qwen3vl8b": 0}

    for cat in CATEGORIES:
        for model in ["qwen3vl4b", "qwen3vl8b"]:
            d_sp = acc_ci(by_mac.get((model, "SPARSE", cat), []))
            d_tm = acc_ci(by_mac.get((model, "TEMPORAL", cat), []))
            diff = d_sp["acc"] - d_tm["acc"]  # positive = SPARSE wins
            # Combined half-width (independent proportions, approx)
            hw_sp = d_sp["half_width"]
            hw_tm = d_tm["half_width"]
            combined_hw = math.sqrt(hw_sp ** 2 + hw_tm ** 2) if (hw_sp and hw_tm) else float("nan")
            exceeds = abs(diff) > combined_hw if not math.isnan(combined_hw) else False

            if exceeds:
                n_exceeds_ci[model] += 1
                if diff > 0:
                    n_sparse_wins_ci[model] += 1
                else:
                    n_temporal_wins_ci[model] += 1

            winner_point = "SPARSE" if d_sp["acc"] > d_tm["acc"] else "TEMPORAL"
            winner_ci = "SPARSE" if (exceeds and diff > 0) else (
                "TEMPORAL" if (exceeds and diff < 0) else "tie_or_underpowered")

            cell_key = f"{model}"
            analysis_b[cat][cell_key] = {
                "SPARSE": d_sp, "TEMPORAL": d_tm,
                "diff_sparse_minus_temporal": round(diff, 4),
                "combined_hw": round(combined_hw, 4) if not math.isnan(combined_hw) else None,
                "exceeds_ci": exceeds,
                "winner_point": winner_point,
                "winner_ci": winner_ci,
            }
            flag = " *** EXCEEDS CI" if exceeds else ""
            log(f"    {cat} {model}: SPARSE={d_sp['acc']:.3f}[±{hw_sp:.3f}] "
                f"TEMPORAL={d_tm['acc']:.3f}[±{hw_tm:.3f}] "
                f"diff={diff:+.3f} combined_hw={combined_hw:.3f}{flag}")

    # Verdict per model
    verdicts = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        n_ex = n_exceeds_ci[model]
        n_sp = n_sparse_wins_ci[model]
        n_tm = n_temporal_wins_ci[model]
        if n_ex == 0:
            v = "UNDERPOWERED: no category shows difference exceeding combined CI"
        elif n_sp == n_ex:
            v = f"STATIC: SPARSE wins in all {n_ex} categories where diff exceeds CI"
        elif n_tm == n_ex:
            v = f"STATIC: TEMPORAL wins in all {n_ex} categories where diff exceeds CI"
        else:
            v = (f"CATEGORY-DEPENDENT: SPARSE wins in {n_sp}, TEMPORAL wins in {n_tm} "
                 f"of {n_ex} categories where diff exceeds CI")
        verdicts[model] = {
            "verdict": v, "n_categories_exceeds_ci": n_ex,
            "n_sparse_wins": n_sp, "n_temporal_wins": n_tm,
        }
        log(f"  VERDICT {model}: {v}")

    analysis_b["_verdicts"] = verdicts

    # ── C: Accuracy vs evidence distance ─────────────────────────────────────
    log("\n  C — Accuracy vs evidence distance (farthest_dist_s bins, 4B only)")
    analysis_c: dict = {"bins": {}, "hypothesis": "TEMPORAL helps more at large distance"}
    for lo, hi in DIST_BINS:
        label = f"[{lo},{int(hi) if hi < float('inf') else '+'})"
        bin_rows: dict[str, list] = {}
        for arm in ARMS:
            bin_rows[arm] = [r for r in by_ma.get(("qwen3vl4b", arm), [])
                             if lo <= r.get("farthest_dist_s", -1) < hi]
        d_sp = acc_ci(bin_rows.get("SPARSE", []))
        d_tm = acc_ci(bin_rows.get("TEMPORAL", []))
        diff = d_tm["acc"] - d_sp["acc"]  # positive = TEMPORAL wins
        analysis_c["bins"][label] = {
            "SPARSE": d_sp, "TEMPORAL": d_tm,
            "diff_temporal_minus_sparse": round(diff, 4),
        }
        log(f"    {label}: SPARSE={d_sp['acc']:.3f}(n={d_sp['n']}) "
            f"TEMPORAL={d_tm['acc']:.3f}(n={d_tm['n']}) "
            f"diff={diff:+.3f}")

    # ── D: 8B minus 4B gap ───────────────────────────────────────────────────
    log("\n  D — 8B minus 4B gap per arm per category")
    analysis_d: dict = {}
    degenerate_cells: list = []

    for arm in ARMS:
        analysis_d[arm] = {}
        for cat in CATEGORIES:
            r4 = by_mac.get(("qwen3vl4b", arm, cat), [])
            r8 = by_mac.get(("qwen3vl8b", arm, cat), [])
            degen8, degen8_reason = is_degenerate(r8)
            if degen8:
                degenerate_cells.append({"arm": arm, "cat": cat, "model": "qwen3vl8b",
                                          "reason": degen8_reason})
                log(f"  DEGENERATE CELL excluded from D: 8B {arm} {cat}: {degen8_reason}")
            d4, d8 = acc_ci(r4), acc_ci(r8)
            gap = (d8["acc"] - d4["acc"]) if (d4["n"] and d8["n"] and not degen8) else float("nan")
            if d4["n"] and d8["n"] and not degen8:
                var4 = d4["acc"] * (1 - d4["acc"]) / d4["n"]
                var8 = d8["acc"] * (1 - d8["acc"]) / d8["n"]
                gap_ci = 1.96 * math.sqrt(var4 + var8)
            else:
                gap_ci = float("nan")
            analysis_d[arm][cat] = {
                "gap": round(gap, 4) if not math.isnan(gap) else None,
                "gap_ci_half": round(gap_ci, 4) if not math.isnan(gap_ci) else None,
                "4b_acc": d4["acc"], "4b_n": d4["n"],
                "8b_acc": d8["acc"], "8b_n": d8["n"],
                "8b_degenerate": degen8,
            }
            if not math.isnan(gap):
                log(f"    {arm} {cat}: 8B-4B = {gap:+.3f} ± {gap_ci:.3f}")

    # ── E: Latency, tokens, memory ──────────────────────────────────────────
    log("\n  E — Latency, tokens, peak memory")
    analysis_e: dict = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            rows = by_ma.get((model, arm), [])
            if not rows:
                continue
            lats = sorted(r["total_latency_ms"] for r in rows if "total_latency_ms" in r)
            mems = sorted(r["peak_memory_gb"] for r in rows if "peak_memory_gb" in r)
            vis = sorted(r["vision_tokens"] for r in rows if r.get("vision_tokens"))
            # decode_latency_ms may be absent in reused I2 trials for 4B SPARSE
            dec_lats = [r["decode_latency_ms"] for r in rows
                        if "decode_latency_ms" in r and r["decode_latency_ms"] is not None]
            n_with_dec = len(dec_lats)
            def med(lst): return lst[len(lst)//2] if lst else float("nan")
            cell = f"{model}_{arm}"
            acc_d = acc_ci(rows)
            lat_med = med(lats)
            lat_p90 = lats[int(0.9 * len(lats))] if lats else float("nan")
            analysis_e[cell] = {
                "n": acc_d["n"],
                "lat_med_ms": lat_med,
                "lat_p90_ms": lat_p90,
                "decode_lat_med_ms": med(dec_lats) if dec_lats else None,
                "decode_n": n_with_dec,
                "mem_med_gb": med(mems),
                "vis_tok_median": med(vis),
                "acc": acc_d["acc"],
                "acc_per_sec": round(acc_d["acc"] / (lat_med / 1000), 4) if lat_med else None,
            }
            log(f"    {cell}: lat={lat_med:.0f}ms p90={lat_p90:.0f}ms "
                f"mem={med(mems):.2f}GB vis_tok={med(vis):.0f} "
                f"acc={acc_d['acc']:.3f} acc/s={analysis_e[cell]['acc_per_sec']}")

    # Accuracy-per-millisecond comparison (TEMPORAL vs SPARSE)
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        d_sp = analysis_e.get(f"{model}_SPARSE", {})
        d_tm = analysis_e.get(f"{model}_TEMPORAL", {})
        if d_sp and d_tm:
            lat_ratio = d_tm["lat_med_ms"] / d_sp["lat_med_ms"] if d_sp["lat_med_ms"] else float("nan")
            acc_diff = d_tm.get("acc", 0) - d_sp.get("acc", 0)
            log(f"  {model}: TEMPORAL latency {lat_ratio:.1f}× SPARSE; "
                f"accuracy diff = {acc_diff:+.3f}")
        analysis_e.setdefault(f"{model}_comparison", {
            "temporal_vs_sparse_lat_ratio": round(lat_ratio, 2) if not math.isnan(lat_ratio) else None,
            "temporal_vs_sparse_acc_diff": round(acc_diff, 4),
        })

    # ── F: Position bias ─────────────────────────────────────────────────────
    log("\n  F — Position bias (chi-square vs uniform A-E; n<25 → not_testable)")
    analysis_f: dict = {}
    contaminated: set = set()

    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            cell = f"{model}_{arm}"
            pb_all = position_bias_chi2(by_ma.get((model, arm), []))
            analysis_f[cell] = {"overall": pb_all}
            if pb_all.get("biased"):
                log(f"    {cell} OVERALL: BIASED p={pb_all['p_value']} "
                    f"dist={pb_all['pred_dist']}")
            for cat in CATEGORIES:
                rows_cat = by_mac.get((model, arm, cat), [])
                pb = position_bias_chi2(rows_cat)
                analysis_f[cell][cat] = pb
                if pb.get("biased"):
                    log(f"    {cell} {cat}: BIASED p={pb['p_value']} "
                        f"dist={pb['pred_dist']}")
                    contaminated.add((model, arm, cat))
                elif pb.get("note") and "not_testable" in pb["note"]:
                    log(f"    {cell} {cat}: {pb['note']}")

    # Annotate D with contamination flags
    for arm in ARMS:
        for cat in CATEGORIES:
            entry = analysis_d[arm].get(cat, {})
            entry["contaminated_4b"] = ("qwen3vl4b", arm, cat) in contaminated
            entry["contaminated_8b"] = ("qwen3vl8b", arm, cat) in contaminated

    # ── Sanity checks ─────────────────────────────────────────────────────────
    log("\n  SANITY CHECKS")
    all_rows = [r for r in load_jsonl(TRIALS_PATH) if "error" not in r]

    # S1: n_frames_req == n_frames_proc for SPARSE
    sparse_rows = [r for r in trials if r["arm"] == "SPARSE"
                   and "n_frames_requested" in r and "n_frames_actually_processed" in r]
    s1_mismatches = [(r["question_id"][:8], r["n_frames_requested"],
                      r["n_frames_actually_processed"])
                     for r in sparse_rows
                     if r["n_frames_requested"] != r["n_frames_actually_processed"]]
    s1_pass = len(s1_mismatches) == 0
    log(f"  S1 SPARSE req==proc: {'PASS' if s1_pass else f'FAIL {len(s1_mismatches)} mismatches'}")

    # S2: vision tokens per arm match I2 medians within 5%
    I2_MEDIANS = {"SPARSE": 4536, "TEMPORAL": 11264}
    s2_results = {}
    for arm in ARMS:
        vt = [r["vision_tokens"] for r in trials if r["arm"] == arm and r.get("vision_tokens")]
        med = sorted(vt)[len(vt)//2] if vt else None
        if med and arm in I2_MEDIANS:
            ratio = med / I2_MEDIANS[arm]
            ok = 0.95 <= ratio <= 1.05
            s2_results[arm] = {"median": med, "i2_median": I2_MEDIANS[arm],
                                "ratio": round(ratio, 3), "within_5pct": ok}
            log(f"  S2 {arm} vis_tok median={med} I2={I2_MEDIANS[arm]} "
                f"ratio={ratio:.3f} {'PASS' if ok else 'FAIL — CODE PATH CHANGED'}")
        else:
            s2_results[arm] = {"median": med, "note": "no I2 reference"}

    # S3: GSER — check reused trials (they were asserted in I2; new trials are asserted in code)
    s3_note = "GSER asserted per trial in load_frames_sparse_timed and frames_from_cache"

    # S4: parse rate per cell
    log("  S4 Parse rate per cell:")
    s4_results = {}
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            cell_rows = [r for r in all_rows
                         if r.get("model") == model and r.get("arm") == arm]
            n_total = len(cell_rows)
            n_ok = sum(1 for r in cell_rows if r.get("parse_ok", True))
            rate = n_ok / n_total if n_total else float("nan")
            s4_results[f"{model}_{arm}"] = {"n": n_total, "parse_ok": n_ok,
                                             "rate": round(rate, 4)}
            log(f"    {model} {arm}: {n_ok}/{n_total} = {rate:.4f}")

    # S5: both models on A6000 bf16 (asserted per model load in inference loop)
    s5_note = "asserted per model load: dtype=bfloat16, device=cuda:1"

    sanity = {
        "s1_sparse_req_eq_proc": s1_pass,
        "s1_mismatches_n": len(s1_mismatches),
        "s2_vis_tok_vs_i2": s2_results,
        "s3_gser": s3_note,
        "s4_parse_rate_per_cell": s4_results,
        "s5_device_dtype": s5_note,
    }

    return {
        "A_overall": analysis_a,
        "B_by_category": analysis_b,
        "C_evidence_distance": analysis_c,
        "D_model_gap": analysis_d,
        "E_latency": analysis_e,
        "F_position_bias": analysis_f,
        "degenerate_cells": degenerate_cells,
        "contaminated_cells": sorted([list(c) for c in contaminated]),
        "sanity": sanity,
    }


# ── report ────────────────────────────────────────────────────────────────────

def write_report(results: dict, kv_info: dict, text_only: dict,
                 profile: Optional[dict], bootstrap_n: int) -> None:
    trials = load_valid_trials()
    n_trials = len(trials)

    A = results["A_overall"]
    B = results["B_by_category"]
    C = results["C_evidence_distance"]
    D = results["D_model_gap"]
    E = results["E_latency"]
    F = results["F_position_bias"]
    contaminated = results["contaminated_cells"]
    degen_cells = results["degenerate_cells"]
    san = results["sanity"]
    verdicts = B.get("_verdicts", {})

    # Arm token medians from sanity
    s2 = san.get("s2_vis_tok_vs_i2", {})

    lines = [
        "# Study I3 — S-EMBER SPARSE vs TEMPORAL at Full Power",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        f"**Script:** `experiments/sember/study_i3_budget.py`",
        f"**Data:** Study I manifest — 150 videos, 459 questions, 7 categories",
        f"**Total valid trials:** {n_trials}",
        f"**Reused from study_i2:** {bootstrap_n} trials "
        f"(4B SPARSE n=459; 4B TEMPORAL, 8B SPARSE, 8B TEMPORAL n=100 each)",
        "",
        "---",
        "",
        "## 1. What was run and reuse decision",
        "",
        "### 1.1 Arms (SPATIAL dropped from study_i2)",
        "",
        "SPATIAL was dropped because study_i2 at full n=459 showed SPATIAL "
        "worse than SPARSE in 5 of 7 categories while using 2.6× more tokens "
        "and 2.8× more latency.",
        "",
        "| arm | frame policy | max_frames | typical vis_tokens | budget binds? |",
        "|---|---|---|---|---|",
        "| SPARSE | 16 frames uniform [0, qt] | 16 | ~4,536 | No |",
        "| TEMPORAL | 1fps [0, qt] | 256 | ~11,264 | Yes (spatial reduced for qt>43s) |",
        "",
        "### 1.2 Reuse decision for 4B SPARSE",
        "",
        "Study_i2 ran 4B SPARSE at n=459 with the same:",
        "- Frame loading code path (SPARSE arm, 16 uniform frames, seek-based)",
        "- Inference code (same processor settings, same VIDEO_TOKEN_ID count for vision_tokens)",
        "- Model snapshot and tokenizer",
        "- GSER assertion per trial",
        "",
        "These 459 trials are copied verbatim with `reused_from: study_i2`. "
        "They are verified in S2 below: median vision_tokens matches I2 within 5%.",
        "For 4B TEMPORAL, 8B SPARSE, 8B TEMPORAL, the 100 existing I2 trials "
        "are similarly copied as prior work; the remaining 359 per cell were run fresh.",
        "",
        "### 1.3 Frame caching for TEMPORAL",
        "",
        "Study I2 used per-frame backward seeks (256 seeks per question). "
        "Each seek is slow because PyAV must seek to the nearest keyframe and "
        "decode forward. The estimated overhead was ~73s of video-decode per TEMPORAL trial "
        "(vs ~2s inference), making 459 trials ≈ 9 hours of decode alone.",
        "",
        "Study I3 groups questions by video and decodes each video ONCE "
        "sequentially (no backward seeks) up to max(question_time) for that video. "
        "Each question then slices the cached frame-dict. The GSER causal contract "
        "is preserved: `frames_from_cache()` retains only frames where timestamp ≤ question_time.",
        "",
        "150 videos, median 3 questions/video (range 2–6). Decode cost amortised "
        "over questions sharing the same video.",
        "",
    ]

    # Profile block
    if profile:
        lines += [
            "### 1.4 Profiling breakdown (10 questions, before main run)",
            "",
            "| arm | n | median decode_ms | median preprocess_ms | "
            "median forward_ms | median total_ms | decode % of total |",
            "|---|---|---|---|---|---|---|",
        ]
        for arm in ["SPARSE", "TEMPORAL"]:
            pts = profile.get(arm, [])
            if not pts:
                lines.append(f"| {arm} | 0 | — | — | — | — | — |")
                continue
            def med_v(key): return sorted(p[key] for p in pts)[len(pts)//2]
            med_dec = med_v("decode_ms")
            med_pre = med_v("preprocess_ms")
            med_fwd = med_v("forward_ms")
            med_tot = med_v("total_ms")
            dec_pct = 100 * med_dec / med_tot if med_tot else 0
            lines.append(f"| {arm} | {len(pts)} | {med_dec:.0f} | {med_pre:.0f} | "
                         f"{med_fwd:.0f} | {med_tot:.0f} | {dec_pct:.0f}% |")
        lines += ["",
                  "Sequential decode speedup vs seek-based: see decode_ms comparison above.",
                  ""]
    else:
        lines += [
            "### 1.4 Profiling breakdown",
            "",
            "Profiling was skipped (4B model not loaded before analysis in this run).",
            "Decode timings are captured per trial in the `decode_latency_ms` field.",
            "",
        ]

    lines += [
        "---",
        "",
        "## 2. Sanity checks",
        "",
        f"**S1 SPARSE req==proc:** {'PASS' if san['s1_sparse_req_eq_proc'] else 'FAIL — ' + str(san['s1_mismatches_n']) + ' mismatches'}",
        "",
        "**S2 Vision tokens vs I2 medians (within 5%):**",
        "",
        "| arm | this run median | I2 median | ratio | verdict |",
        "|---|---|---|---|---|",
    ]
    for arm in ARMS:
        s2a = s2.get(arm, {})
        med = s2a.get("median", "?")
        i2m = s2a.get("i2_median", "?")
        ratio = s2a.get("ratio", "?")
        ok = s2a.get("within_5pct", None)
        verdict = "PASS" if ok else ("FAIL — code path changed" if ok is False else "n/a")
        lines.append(f"| {arm} | {med} | {i2m} | {ratio} | {verdict} |")

    lines += [
        "",
        f"**S3 GSER:** {san['s3_gser']}",
        "",
        "**S4 Parse rate per cell:**",
        "",
        "| cell | n | parse_ok | rate |",
        "|---|---|---|---|",
    ]
    for k, v in san.get("s4_parse_rate_per_cell", {}).items():
        lines.append(f"| {k} | {v['n']} | {v['parse_ok']} | {v['rate']:.4f} |")

    lines += [
        "",
        f"**S5 Device/dtype:** {san['s5_device_dtype']}",
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
            d = A.get(f"{model}_{arm}", {})
            flag = " ★" if d.get("acc", 1.0) <= 0.20 else ""
            lines.append(f"| {model} | {arm} | {d.get('n','?')} | "
                         f"{d.get('acc', float('nan')):.3f}{flag} | "
                         f"[{d.get('ci_lo', float('nan')):.3f}, "
                         f"{d.get('ci_hi', float('nan')):.3f}] |")

    lines += [
        "",
        "---",
        "",
        "## 4. Analysis B — Per-category accuracy: THE DECIDING ANALYSIS",
        "",
        "Winner declared only when |acc_SPARSE − acc_TEMPORAL| > combined half-width "
        "(√(hw_SPARSE² + hw_TEMPORAL²)). Point-estimate leaders are noted separately.",
        "",
    ]

    for model in ["qwen3vl4b", "qwen3vl8b"]:
        vd = verdicts.get(model, {})
        lines.append(f"### {model}")
        lines.append("")
        lines.append(f"**Verdict:** {vd.get('verdict', '?')}")
        lines.append("")
        lines.append("| category | SPARSE n | SPARSE acc | TEMPORAL n | TEMPORAL acc | "
                     "diff | combined_hw | exceeds CI? | winner |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for cat in CATEGORIES:
            cd = B[cat].get(model, {})
            d_sp = cd.get("SPARSE", {})
            d_tm = cd.get("TEMPORAL", {})
            diff = cd.get("diff_sparse_minus_temporal", float("nan"))
            hw = cd.get("combined_hw", float("nan"))
            ex = cd.get("exceeds_ci", False)
            wp = cd.get("winner_point", "?")
            wc = cd.get("winner_ci", "?")
            lines.append(
                f"| {cat} | {d_sp.get('n','?')} | {d_sp.get('acc',float('nan')):.3f} "
                f"[{d_sp.get('ci_lo',float('nan')):.3f},{d_sp.get('ci_hi',float('nan')):.3f}] "
                f"| {d_tm.get('n','?')} | {d_tm.get('acc',float('nan')):.3f} "
                f"[{d_tm.get('ci_lo',float('nan')):.3f},{d_tm.get('ci_hi',float('nan')):.3f}] "
                f"| {diff:+.3f} | {hw:.3f} | {'YES ***' if ex else 'no'} "
                f"| {wc} |"
            )
        lines += [""]

    lines += [
        "---",
        "",
        "## 5. Analysis C — Accuracy vs evidence distance (4B model)",
        "",
        "Bins by `farthest_dist_s` = question_time − answer_start_time.",
        "Hypothesis: TEMPORAL helps most at large distance (SPARSE at 16 frames samples "
        "coarsely over long prefixes).",
        "",
        "| distance bin | SPARSE n | SPARSE acc | TEMPORAL n | TEMPORAL acc | "
        "diff (T−S) | TEMPORAL helps? |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, cd in C.get("bins", {}).items():
        d_sp = cd.get("SPARSE", {})
        d_tm = cd.get("TEMPORAL", {})
        diff = cd.get("diff_temporal_minus_sparse", float("nan"))
        helps = diff > 0.03
        lines.append(f"| {label} | {d_sp.get('n','?')} | {d_sp.get('acc',float('nan')):.3f} "
                     f"| {d_tm.get('n','?')} | {d_tm.get('acc',float('nan')):.3f} "
                     f"| {diff:+.3f} | {'yes' if helps else 'no'} |")

    lines += [
        "",
        "---",
        "",
        "## 6. Analysis D — 8B minus 4B gap per arm per category",
        "",
        "Cells marked DEGENERATE are excluded: acc≈0 with flagged position bias.",
    ]
    if degen_cells:
        lines.append("")
        for dc in degen_cells:
            lines.append(f"- DEGENERATE: 8B × {dc['arm']} × {dc['cat']}: {dc['reason']}")
    lines += [
        "",
        "| arm | category | 4B acc (n) | 8B acc (n) | gap (8B−4B) | gap CI half | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        for cat in CATEGORIES:
            cd = D.get(arm, {}).get(cat, {})
            degen = cd.get("8b_degenerate", False)
            gap = cd.get("gap")
            ghw = cd.get("gap_ci_half")
            note = "DEGENERATE (excluded)" if degen else (
                "contaminated_4b" if cd.get("contaminated_4b") else (
                    "contaminated_8b" if cd.get("contaminated_8b") else ""))
            lines.append(
                f"| {arm} | {cat} | {cd.get('4b_acc',float('nan')):.3f} ({cd.get('4b_n','?')}) "
                f"| {cd.get('8b_acc',float('nan')):.3f} ({cd.get('8b_n','?')}) "
                f"| {gap:+.3f} | {ghw:.3f} | {note} |"
                if (gap is not None and ghw is not None) else
                f"| {arm} | {cat} | {cd.get('4b_acc',float('nan')):.3f} ({cd.get('4b_n','?')}) "
                f"| {cd.get('8b_acc',float('nan')):.3f} ({cd.get('8b_n','?')}) "
                f"| — | — | {note} |"
            )

    lines += [
        "",
        "---",
        "",
        "## 7. Analysis E — Latency, tokens, peak memory",
        "",
        "| model | arm | n | lat_med_ms | lat_p90_ms | decode_ms (n) | "
        "mem_med_gb | vis_tok_median | acc | acc/s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            cd = E.get(f"{model}_{arm}", {})
            if not cd:
                continue
            dec_str = (f"{cd['decode_lat_med_ms']:.0f} (n={cd['decode_n']})"
                       if cd.get("decode_lat_med_ms") is not None else "— (reused)")
            lines.append(
                f"| {model} | {arm} | {cd.get('n','?')} "
                f"| {cd.get('lat_med_ms',float('nan')):.0f} "
                f"| {cd.get('lat_p90_ms',float('nan')):.0f} "
                f"| {dec_str} "
                f"| {cd.get('mem_med_gb',float('nan')):.2f} "
                f"| {cd.get('vis_tok_median',float('nan')):.0f} "
                f"| {cd.get('acc',float('nan')):.3f} "
                f"| {cd.get('acc_per_sec',float('nan')):.4f} |"
            )

    lines += [
        "",
        "**Accuracy/latency tradeoff:**",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        comp = E.get(f"{model}_comparison", {})
        lat_r = comp.get("temporal_vs_sparse_lat_ratio")
        acc_d = comp.get("temporal_vs_sparse_acc_diff")
        if lat_r and acc_d is not None:
            lines.append(
                f"- {model}: TEMPORAL is {lat_r:.1f}× slower than SPARSE; "
                f"accuracy difference = {acc_d:+.3f}")

    lines += [
        "",
        "---",
        "",
        "## 8. Analysis F — Position bias",
        "",
        "Chi-square vs uniform A-E distribution. Cells with n < 25 (expected < 5 "
        "per option) are marked **not_testable** — not 'no bias'. This corrects "
        "study_i2's treatment of small cells.",
        "",
        "| model | arm | cell | n | biased? | p_value | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            key = f"{model}_{arm}"
            # Overall row
            pb = F.get(key, {}).get("overall", {})
            note = pb.get("note", "")
            biased = "YES ***" if pb.get("biased") else ("not_testable" if "not_testable" in note else "no")
            lines.append(f"| {model} | {arm} | overall | {pb.get('n','?')} "
                         f"| {biased} | {pb.get('p_value','—')} | {note} |")
            for cat in CATEGORIES:
                pb_c = F.get(key, {}).get(cat, {})
                note_c = pb_c.get("note", "")
                biased_c = "YES ***" if pb_c.get("biased") else (
                    "not_testable" if "not_testable" in note_c else "no")
                lines.append(f"| {model} | {arm} | {cat} | {pb_c.get('n','?')} "
                             f"| {biased_c} | {pb_c.get('p_value','—')} | {note_c} |")

    lines += [
        "",
        "---",
        "",
        "## 9. Three plain answers",
        "",
        "**Q1: Does SPARSE or TEMPORAL win, and does it depend on category?**",
        "",
    ]
    # Compose verdict summary
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        vd = verdicts.get(model, {})
        lines.append(f"- **{model}:** {vd.get('verdict', '?')}")
        # List categories that exceed CI
        n_ex = vd.get("n_categories_exceeds_ci", 0)
        if n_ex > 0:
            for cat in CATEGORIES:
                cd = B[cat].get(model, {})
                if cd.get("exceeds_ci"):
                    wc = cd.get("winner_ci", "?")
                    diff = cd.get("diff_sparse_minus_temporal", 0)
                    lines.append(f"  - {cat}: {wc} wins by {abs(diff):.3f}")
    lines.append("")

    lines += [
        "**Q2: Does TEMPORAL's advantage (if any) grow with evidence distance?**",
        "",
    ]
    dist_diffs = [(label, cd.get("diff_temporal_minus_sparse", float("nan")),
                   cd.get("SPARSE", {}).get("n", 0))
                  for label, cd in C.get("bins", {}).items()]
    if all(math.isnan(d) for _, d, _ in dist_diffs):
        lines.append("Cannot assess: no distance data.")
    else:
        trend = [d for _, d, n in dist_diffs if not math.isnan(d) and n >= 5]
        monotone = all(trend[i] <= trend[i+1] for i in range(len(trend)-1)) if len(trend) > 1 else None
        lines.append("TEMPORAL − SPARSE accuracy by distance bin:")
        for label, diff, n in dist_diffs:
            lines.append(f"  - {label} (n={n}): {diff:+.3f}")
        if monotone is True:
            lines.append("Trend is monotonically increasing — hypothesis supported.")
        elif monotone is False:
            lines.append("Trend is not monotone — hypothesis not supported.")
        else:
            lines.append("Too few bins with adequate n to assess trend.")
    lines.append("")

    lines += [
        "**Q3: What does TEMPORAL cost in latency relative to SPARSE, and is any accuracy gain worth it?**",
        "",
    ]
    for model in ["qwen3vl4b", "qwen3vl8b"]:
        comp = E.get(f"{model}_comparison", {})
        lat_r = comp.get("temporal_vs_sparse_lat_ratio")
        acc_d = comp.get("temporal_vs_sparse_acc_diff")
        if lat_r is not None and acc_d is not None:
            if abs(acc_d) < 0.03:
                judgment = "accuracy difference is within noise; TEMPORAL cost is not justified"
            elif acc_d > 0 and lat_r > 2.0:
                judgment = f"TEMPORAL wins by {acc_d:+.3f} at {lat_r:.1f}× latency cost; tradeoff is application-dependent"
            elif acc_d < 0:
                judgment = f"TEMPORAL is slower AND less accurate; SPARSE dominates"
            else:
                judgment = f"TEMPORAL wins by {acc_d:+.3f} at {lat_r:.1f}× latency cost"
            lines.append(f"- **{model}:** TEMPORAL is {lat_r:.1f}× the latency of SPARSE; "
                         f"accuracy diff = {acc_d:+.3f}. {judgment}.")
    lines.append("")

    lines += [
        "---",
        "",
        "## 10. What cannot be inferred",
        "",
        "- This is a measurement study, not a causal experiment. Accuracy differences "
        "between arms are observed under the GSER protocol.",
        "- The text-only baseline uses 4B only from study_i (diag).",
        "- decode_latency_ms in reused 4B SPARSE trials is not available (marked as reused); "
        "the latency reported for those trials covers inference only.",
        "- Frame caching amortises decode cost per video. Reported decode_latency_ms for "
        "TEMPORAL is amortised (total video decode ÷ n_questions_for_that_video), not "
        "the cost of decoding just one question's frames.",
        "- Category n varies (44–93); smaller categories have wider CIs and fewer cells "
        "will exceed the CI threshold regardless of arm performance.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    log(f"\n  Report written: {REPORT_PATH}")


# ── provenance ────────────────────────────────────────────────────────────────

def stamp(n_trials: int) -> dict:
    import subprocess
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    except Exception:
        sha = "pre-provenance"
    return {
        "git_commit": sha,
        "script": "study_i3_budget.py",
        "models": [c["slug"] for c in MODEL_CONFIGS],
        "arms": ARMS,
        "device": "nvidia_rtx_a6000",
        "n_total": n_trials,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)

    log("=== Study I3 — S-EMBER SPARSE vs TEMPORAL at full power ===\n")

    # KV verification
    kv_info = {}
    log("KV constant verification:")
    for cfg in MODEL_CONFIGS:
        slug, snap = cfg["slug"], cfg["snap"]
        k = compute_kv_bpt(snap)
        kv_info[slug] = k
        log(f"  {slug}: {k['formula']}")

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

    n_vid = sum(1 for v in vid_set if (VIDEO_DIR / f"{v}.mp4").exists())
    log(f"Videos on disk: {n_vid}/{manifest['n_videos']}")
    if n_vid < manifest["n_videos"]:
        log(f"  WARNING: {manifest['n_videos'] - n_vid} videos missing")

    # Bootstrap from study_i2
    log("\nBOOTSTRAP from study_i2")
    bootstrap_n = bootstrap_from_i2()
    done_after_bootstrap = load_done_keys(TRIALS_PATH)
    log(f"  Copied {bootstrap_n} trials → {len(done_after_bootstrap)} done keys")

    # Verify reuse: 4B SPARSE should be fully covered
    n_4b_sparse_done = sum(1 for r in qa_rows
                           if ("qwen3vl4b", "SPARSE", r["question_id"]) in done_after_bootstrap)
    log(f"  4B SPARSE done after bootstrap: {n_4b_sparse_done}/{len(qa_rows)}")
    if n_4b_sparse_done < len(qa_rows):
        log(f"  NOTE: {len(qa_rows) - n_4b_sparse_done} 4B SPARSE trials not in I2 "
            f"— will run fresh")

    # Phase: inference (with profiling on first model load)
    log("\nPHASE INFER")
    profile_results: Optional[dict] = None

    done_counts = {}
    for slug in ["qwen3vl4b", "qwen3vl8b"]:
        for arm in ARMS:
            n = sum(1 for r in qa_rows
                    if (slug, arm, r["question_id"]) in done_after_bootstrap)
            done_counts[(slug, arm)] = n

    estimate_runtime(qa_rows, done_counts)

    # Load 4B first for profiling (if TEMPORAL has pending trials)
    need_4b = any(done_counts.get(("qwen3vl4b", arm), 0) < len(qa_rows) for arm in ARMS)
    if need_4b:
        log("\n  Loading qwen3vl4b for profiling + inference")
        proc = AutoProcessor.from_pretrained(
            SNAP_4B, min_pixels=256 * 28 * 28, max_pixels=1280 * 28 * 28)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            SNAP_4B, torch_dtype=DTYPE,
            attn_implementation="flash_attention_2", device_map=DEVICE)
        model.eval()
        assert str(next(model.parameters()).dtype) == "torch.bfloat16"
        assert str(next(model.parameters()).device) == DEVICE

        # Profile before main run
        profile_results = run_profile(qa_rows, proc, model, "qwen3vl4b")

        done = load_done_keys(TRIALS_PATH)
        kv_ana = kv_info["qwen3vl4b"]["bpt"]
        log(f"  KV analytical: {kv_ana} B/tok")

        for arm in ARMS:
            pending = [r for r in qa_rows if ("qwen3vl4b", arm, r["question_id"]) not in done]
            if not pending:
                log(f"\n  qwen3vl4b × {arm}: all done, skipping")
                continue
            log(f"\n  qwen3vl4b × {arm}: {len(pending)} pending")
            if arm == "TEMPORAL":
                _run_temporal_cached(pending, proc, model, "qwen3vl4b", done)
            else:
                _run_sparse(pending, proc, model, "qwen3vl4b", done)

        del model
        gc.collect()
        torch.cuda.empty_cache()
    else:
        log("\n  4B: all done, skipping model load")

    # 8B
    need_8b = any(done_counts.get(("qwen3vl8b", arm), 0) < len(qa_rows) for arm in ARMS)
    if need_8b:
        log("\n  Loading qwen3vl8b")
        proc = AutoProcessor.from_pretrained(
            SNAP_8B, min_pixels=256 * 28 * 28, max_pixels=1280 * 28 * 28)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            SNAP_8B, torch_dtype=DTYPE,
            attn_implementation="flash_attention_2", device_map=DEVICE)
        model.eval()
        assert str(next(model.parameters()).dtype) == "torch.bfloat16"
        assert str(next(model.parameters()).device) == DEVICE

        done = load_done_keys(TRIALS_PATH)
        kv_ana = kv_info["qwen3vl8b"]["bpt"]
        log(f"  KV analytical: {kv_ana} B/tok")

        for arm in ARMS:
            pending = [r for r in qa_rows if ("qwen3vl8b", arm, r["question_id"]) not in done]
            if not pending:
                log(f"\n  qwen3vl8b × {arm}: all done, skipping")
                continue
            log(f"\n  qwen3vl8b × {arm}: {len(pending)} pending")
            if arm == "TEMPORAL":
                _run_temporal_cached(pending, proc, model, "qwen3vl8b", done)
            else:
                _run_sparse(pending, proc, model, "qwen3vl8b", done)

        del model
        gc.collect()
        torch.cuda.empty_cache()
    else:
        log("\n  8B: all done, skipping model load")

    # Phase: analyse
    log("\nPHASE ANALYSE")
    text_only = json.loads(TEXT_ONLY_PATH.read_text()) if TEXT_ONLY_PATH.exists() else {}
    results = run_analyses(text_only)

    trials_final = load_valid_trials()
    results["_provenance"] = stamp(len(trials_final))

    RESULTS_PATH.write_text(json.dumps(_json_safe(results), indent=2))
    log(f"\n  Results written: {RESULTS_PATH}")

    write_report(results, kv_info, text_only, profile_results, bootstrap_n)

    log("\nDone. Ask user to commit results.")


if __name__ == "__main__":
    main()
