#!/usr/bin/env python3
"""
Study I — S-EMBER tier gap: accuracy × category × evidence distance, latency.

Primary question: does the accuracy gap between Qwen3-VL-4B and -8B depend on
(a) question category, and (b) evidence distance? Does the gap justify two-tier
placement for this workload?

Write scope:
  results/sember/study_i/study_i_manifest.json   — selected 150 videos
  results/sember/study_i/study_i_trials.jsonl     — one record per trial
  results/sember/study_i/study_i_results.json     — analysis summary
  results/sember/study_i/videos/                  — downloaded video files

Phases (run sequentially; each phase is skippable if output already exists):
  SELECT   → choose 150 multi-Q videos, write manifest, estimate download size
  DOWNLOAD → download video files via huggingface_hub
  INFER    → 2 models × 2 sampling modes × all questions in selected videos
  ANALYSE  → A–E analyses, write results JSON

GSER protocol: each question sees only video[0, question_time]. Asserted per trial.
Coverage arithmetic: uses answer_start_time, not answer_end_time (per Study H2 SC5 correction).
Sampling:
  SPARSE — 16 frames uniform over [0, question_time]
  DENSE  — 1 fps over [0, question_time], capped at 256 frames
Scoring: exact letter match (A/B/C/D/E); max_new_tokens=16; greedy decode.
"""

from __future__ import annotations

import gc
import json
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av
import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from transformers.video_utils import VideoMetadata

try:
    from qwen_vl_utils import process_vision_info
except ImportError:
    sys.exit("qwen_vl_utils not found — activate fmtk conda env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MCQ_PATH = PROJECT_ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
GROUNDING_PATH = PROJECT_ROOT / "results/sember/study_h/data/sember_grounding.jsonl"
OUT_DIR = PROJECT_ROOT / "results/sember/study_i"
VIDEO_DIR = OUT_DIR / "videos"
MANIFEST_PATH = OUT_DIR / "study_i_manifest.json"
TRIALS_PATH = OUT_DIR / "study_i_trials.jsonl"
RESULTS_PATH = OUT_DIR / "study_i_results.json"

HF_REPO = "facebook/S-EMBER"
N_VIDEOS = 150
MIN_Q_PER_CAT = 15
TARGET_Q_PER_CAT = 22

CATEGORIES = [
    "time_duration",
    "visual_detail_recall",
    "sequential_action",
    "location_trace",
    "spatial_aware_reasoning",
    "object_comparison",
    "temporal_ordering_recognition",
]

DEVICE = "cuda:1"
DTYPE = torch.bfloat16
MAX_NEW_TOKENS = 16
SEED = 42

SNAP_4B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
SNAP_8B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"

MODEL_CONFIGS = [
    {"slug": "qwen3vl4b", "snap": SNAP_4B},
    {"slug": "qwen3vl8b", "snap": SNAP_8B},
]
SAMPLING_MODES = ["SPARSE", "DENSE"]
SPARSE_N_FRAMES = 16
DENSE_FPS = 1
DENSE_MAX_FRAMES = 256

RUNTIME_LIMIT_S = 6 * 3600
DOWNLOAD_LIMIT_GB = 200.0

# Per-video estimated size (396 GB total across 3141 videos)
EST_MB_PER_VIDEO = 396 * 1024 / 3141


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl_append(path: Path, record: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


# ── PHASE 1: SELECT ───────────────────────────────────────────────────────────

def select_videos(mcq_rows: list[dict]) -> tuple[list[str], dict]:
    """
    Select N_VIDEOS multi-Q videos stratified to give >= TARGET_Q_PER_CAT
    questions per category (over 7 categories after counting exclusion).

    Strategy:
      1. Collect multi-Q video pool (>= 2 Q after counting exclusion).
      2. Greedy cover: for each category sorted rarest-first, add videos
         that have Q in that category until TARGET_Q_PER_CAT is reached.
         Prefer videos with Q in multiple rare categories.
      3. Fill to N_VIDEOS with random videos from the pool.
      4. Verify >= MIN_Q_PER_CAT per category.
    """
    random.seed(SEED)

    # Build per-video QA list (excluding counting)
    vid_qs: dict[str, list[dict]] = defaultdict(list)
    for row in mcq_rows:
        if row["question_category"] in CATEGORIES:
            vid_qs[row["video_id"]].append(row)

    multi_q_vids = {v: qs for v, qs in vid_qs.items() if len(qs) >= 2}
    log(f"  Multi-Q video pool: {len(multi_q_vids)} videos, "
        f"{sum(len(v) for v in multi_q_vids.values())} QA")

    # Per-category video sets
    cat_vids: dict[str, list[str]] = defaultdict(list)
    for vid, qs in multi_q_vids.items():
        for q in qs:
            cat = q["question_category"]
            if cat not in cat_vids or vid not in cat_vids[cat]:
                cat_vids[cat].append(vid)

    # Count Q per cat in a candidate selection
    def q_counts(selected: set[str]) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for v in selected:
            for q in multi_q_vids[v]:
                c[q["question_category"]] += 1
        return c

    # Greedy cover: rarest category first
    cat_sizes = {cat: len(cat_vids[cat]) for cat in CATEGORIES}
    sorted_cats = sorted(CATEGORIES, key=lambda c: cat_sizes[c])

    selected: set[str] = set()

    for cat in sorted_cats:
        # Sort candidate videos by Q count in this category (desc),
        # then by how many rare-category Q they also cover
        remaining_vids = [v for v in cat_vids[cat] if v not in selected]
        random.shuffle(remaining_vids)  # break ties randomly

        counts = q_counts(selected)
        if counts.get(cat, 0) >= TARGET_Q_PER_CAT:
            continue

        # Score each candidate by cat-Q count (primary) and scarcity coverage
        def _score(v, _cat=cat, _rare=sorted_cats[:3]):
            n_cat_q = sum(1 for q in multi_q_vids[v] if q["question_category"] == _cat)
            n_rare_q = sum(1 for q in multi_q_vids[v] if q["question_category"] in _rare)
            return (n_cat_q, n_rare_q)

        remaining_vids.sort(key=_score, reverse=True)

        for v in remaining_vids:
            counts = q_counts(selected)
            if counts.get(cat, 0) >= TARGET_Q_PER_CAT:
                break
            selected.add(v)
            if len(selected) >= N_VIDEOS:
                break

    log(f"  After greedy cover: {len(selected)} videos")

    # Fill to N_VIDEOS
    if len(selected) < N_VIDEOS:
        remaining = [v for v in multi_q_vids if v not in selected]
        random.shuffle(remaining)
        selected.update(remaining[:N_VIDEOS - len(selected)])

    # Trim to N_VIDEOS if overshoot (remove non-critical videos)
    selected_list = list(selected)
    if len(selected_list) > N_VIDEOS:
        # Trim: prefer removing videos that contribute least to rarest categories
        random.shuffle(selected_list)
        selected_list = selected_list[:N_VIDEOS]

    # Verify
    counts = q_counts(set(selected_list))
    log("  Per-category Q counts in selection:")
    for cat in sorted(CATEGORIES):
        n = counts.get(cat, 0)
        status = "OK" if n >= MIN_Q_PER_CAT else "FAIL"
        log(f"    {cat}: {n} [{status}]")

    for cat in CATEGORIES:
        if counts.get(cat, 0) < MIN_Q_PER_CAT:
            sys.exit(f"STOP: category {cat} has only {counts.get(cat,0)} Q < {MIN_Q_PER_CAT}")

    total_q = sum(counts.values())
    log(f"  Total QA in selection: {total_q} across {len(selected_list)} videos")

    return selected_list, counts


def write_manifest(selected_vids: list[str], mcq_rows: list[dict]) -> dict:
    vid_set = set(selected_vids)
    qa_in_selection = [r for r in mcq_rows
                       if r["video_id"] in vid_set
                       and r["question_category"] in CATEGORIES]

    # Estimate download size
    durations = {r["video_id"]: r["duration"] for r in mcq_rows if r["video_id"] in vid_set}
    total_dur_h = sum(durations.values()) / 3600
    est_gb = len(selected_vids) * EST_MB_PER_VIDEO / 1024

    manifest = {
        "n_videos": len(selected_vids),
        "n_qa": len(qa_in_selection),
        "est_download_gb": round(est_gb, 1),
        "total_duration_h": round(total_dur_h, 1),
        "video_ids": sorted(selected_vids),
        "video_file_paths": sorted({
            r["video"] for r in mcq_rows if r["video_id"] in vid_set
        }),
    }
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    log(f"  Manifest written: {MANIFEST_PATH}")
    log(f"  Estimated download: {est_gb:.1f} GB ({len(selected_vids)} videos, "
        f"{total_dur_h:.1f} h total duration)")
    return manifest


# ── PHASE 2: DOWNLOAD ─────────────────────────────────────────────────────────

def download_videos(manifest: dict) -> None:
    from huggingface_hub import hf_hub_download

    est_gb = manifest["est_download_gb"]
    if est_gb > DOWNLOAD_LIMIT_GB:
        sys.exit(f"STOP: estimated download {est_gb:.1f} GB > {DOWNLOAD_LIMIT_GB} GB limit")

    log(f"  Downloading {manifest['n_videos']} videos (~{est_gb:.1f} GB) to {VIDEO_DIR}")
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    file_paths = manifest["video_file_paths"]
    n = len(file_paths)
    for i, fp in enumerate(file_paths, 1):
        # fp is like "videos/<video_id>.mp4"
        local_path = VIDEO_DIR / Path(fp).name
        if local_path.exists():
            log(f"  [{i}/{n}] Already exists: {local_path.name}")
            continue
        log(f"  [{i}/{n}] Downloading {fp} ...")
        t0 = time.perf_counter()
        # local_dir=OUT_DIR so HF places "videos/<id>.mp4" at VIDEO_DIR/<id>.mp4
        hf_hub_download(
            repo_id=HF_REPO,
            repo_type="dataset",
            filename=fp,
            local_dir=str(OUT_DIR),
        )
        # hf_hub_download preserves the filename path under local_dir:
        # OUT_DIR / "videos" / "<id>.mp4" == VIDEO_DIR / "<id>.mp4" ✓
        if not local_path.exists():
            log(f"  WARNING: expected file not found at {local_path}")
        dt = time.perf_counter() - t0
        if local_path.exists():
            sz_mb = local_path.stat().st_size / 1024 / 1024
            log(f"       {sz_mb:.1f} MB in {dt:.1f}s")
        else:
            log(f"  WARNING: expected file not found at {local_path}")


# ── PHASE 3: INFER — frame loading ───────────────────────────────────────────

def get_frame_at_time(container, stream, target_time_s: float) -> Image.Image | None:
    """Seek to target_time_s and return the nearest decoded frame as PIL."""
    time_base = float(stream.time_base)
    pts = int(target_time_s / time_base)
    try:
        container.seek(pts, stream=stream, backward=True)
    except av.AVError:
        try:
            container.seek(0)
        except av.AVError:
            return None

    best_img = None
    best_diff = float("inf")
    for frame in container.decode(stream):
        t = float(frame.pts * stream.time_base)
        diff = abs(t - target_time_s)
        if diff < best_diff:
            best_diff = diff
            best_img = frame.to_image()
        # Once we've passed the target by more than 2s, stop decoding
        if t > target_time_s + 2.0:
            break
    return best_img


def load_frames(
    video_path: Path, question_time: float, sampling_mode: str
) -> tuple[list, list[int], int]:
    """
    Load frames from video trimmed to [0, question_time] (GSER assertion).

    SPARSE: 16 frames uniform over [0, question_time]
    DENSE:  1 fps over [0, question_time], capped at DENSE_MAX_FRAMES frames

    Returns (frames: list[PIL.Image], frame_timestamps_s: list[int], n_frames: int)
    frame_timestamps_s: frame timestamps in seconds (integer, for VideoMetadata with fps=1)
    """
    container = av.open(str(video_path))
    stream = container.streams.video[0]

    # GSER assertion: all target_times are in [0, question_time]
    if sampling_mode == "SPARSE":
        n = SPARSE_N_FRAMES
        if n == 1:
            target_times = [0.0]
        else:
            target_times = [question_time * i / (n - 1) for i in range(n)]
    else:  # DENSE
        n_sec = min(int(question_time), DENSE_MAX_FRAMES)
        target_times = [float(i) for i in range(n_sec)]

    assert all(t <= question_time + 1e-6 for t in target_times), \
        f"GSER violated: target beyond question_time={question_time}"

    frames = []
    timestamps_s = []
    for t in target_times:
        img = get_frame_at_time(container, stream, t)
        if img is not None:
            frames.append(img)
            timestamps_s.append(round(t))  # integer seconds, for VideoMetadata fps=1

    container.close()
    return frames, timestamps_s, len(frames)


# ── PHASE 3: INFER — MCQ inference ───────────────────────────────────────────

def format_question(qa_row: dict) -> str:
    """Format MCQ as multi-choice question with options."""
    q = qa_row["question"]
    options = "\n".join(qa_row["options"])
    return (
        f"Watch the video carefully, then answer the following multiple-choice question.\n\n"
        f"Question: {q}\n\n"
        f"{options}\n\n"
        f"Reply with only the letter of the correct answer (A, B, C, D, or E)."
    )


def parse_letter(text: str) -> str | None:
    """Extract first A-E letter from model output."""
    for ch in text.strip().upper():
        if ch in "ABCDE":
            return ch
    return None


def run_single_trial(
    proc,
    model,
    qa_row: dict,
    grounding_row: dict | None,
    video_path: Path,
    sampling_mode: str,
    model_slug: str,
) -> dict:
    """Run one (question, model, sampling_mode) trial and return metrics dict."""
    video_id = qa_row["video_id"]
    question_id = qa_row["question_id"]
    qt = qa_row["question_time"]
    ast = qa_row["answer_start_time"]
    aet = qa_row["answer_end_time"]

    # GSER assertion: qt is the cutoff
    frames, timestamps_s, n_frames = load_frames(video_path, qt, sampling_mode)
    if len(frames) == 0:
        return {
            "model": model_slug, "sampling": sampling_mode,
            "video_id": video_id, "question_id": question_id,
            "error": "no_frames_loaded",
        }

    # VideoMetadata with fps=1 so timestamp = frames_indices[i] / 1 = actual time in seconds.
    # This provides correct temporal position embeddings to the model.
    video_meta = VideoMetadata(
        fps=1.0,
        frames_indices=timestamps_s,  # integer seconds of each sampled frame
        total_num_frames=round(qt),
    )

    question_text = format_question(qa_row)

    messages = [
        {"role": "user", "content": [
            {"type": "video", "video": frames, "sample_fps": 1.0},
            {"type": "text", "text": question_text},
        ]}
    ]

    text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs, video_kwargs = process_vision_info(messages, return_video_kwargs=True)

    # Unwrap fps list if needed (returned as [fps] for a single-video batch)
    if "fps" in video_kwargs and isinstance(video_kwargs["fps"], list):
        video_kwargs["fps"] = video_kwargs["fps"][0] if video_kwargs["fps"] else None

    inputs = proc(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        video_metadata=video_meta,  # correct temporal embeddings
        return_tensors="pt",
        **video_kwargs,
    ).to(DEVICE)

    n_input = inputs.input_ids.shape[1]

    torch.cuda.reset_peak_memory_stats(DEVICE)
    torch.cuda.synchronize(DEVICE)
    t0 = time.perf_counter()

    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=None,
            top_p=None,
        )

    torch.cuda.synchronize(DEVICE)
    total_ms = (time.perf_counter() - t0) * 1000
    peak_mem_gb = torch.cuda.max_memory_allocated(DEVICE) / 1024**3

    gen_ids = out_ids[0][n_input:]
    n_generated = len(gen_ids)
    gen_text = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
    predicted_letter = parse_letter(gen_text)
    correct = (predicted_letter == qa_row["correct_letter"]) if predicted_letter else False

    # Evidence distance metrics
    nearest_dist = qt - aet  # how recently evidence closed
    farthest_dist = qt - ast  # = memory_recency (how long ago evidence began)

    # Coverage: window of k seconds before qt covers evidence if ast >= qt - k
    # Using ast because ENTIRE evidence window [ast, aet] must be within [qt-k, qt]
    # => k must be >= qt - ast (= farthest_dist)
    coverage_binding_dist = farthest_dist  # window must be >= this to cover the evidence

    return {
        "model": model_slug,
        "sampling": sampling_mode,
        "video_id": video_id,
        "question_id": question_id,
        "category": qa_row["question_category"],
        "question_time": qt,
        "answer_start_time": ast,
        "answer_end_time": aet,
        "nearest_dist_s": round(nearest_dist, 2),
        "farthest_dist_s": round(farthest_dist, 2),
        "coverage_binding_dist_s": round(coverage_binding_dist, 2),
        "n_frames_sampled": n_frames,
        "n_input_tokens": n_input,
        "n_generated": n_generated,
        "total_latency_ms": round(total_ms, 1),
        "peak_memory_gb": round(peak_mem_gb, 3),
        "gen_text": gen_text.strip()[:64],
        "predicted_letter": predicted_letter,
        "correct_letter": qa_row["correct_letter"],
        "correct": correct,
    }


def load_done_keys(trials_path: Path) -> set[tuple]:
    """Return set of (model, sampling, question_id) already written."""
    done = set()
    if not trials_path.exists():
        return done
    with open(trials_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["model"], r["sampling"], r["question_id"]))
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def estimate_runtime(qa_rows: list[dict]) -> float:
    """Print runtime projection and return estimate in seconds."""
    # Estimate frames per trial
    qts = [r["question_time"] for r in qa_rows]
    med_qt = statistics.median(qts)
    sparse_frames = SPARSE_N_FRAMES
    dense_frames = min(int(med_qt), DENSE_MAX_FRAMES)
    sparse_tokens = sparse_frames * 324 + 300
    dense_tokens = dense_frames * 324 + 300

    # Prefill throughput: ~7000 tok/s for 4B, ~3500 tok/s for 8B (A6000)
    configs = [
        ("qwen3vl4b", "SPARSE", sparse_tokens, 7000),
        ("qwen3vl4b", "DENSE",  dense_tokens,  7000),
        ("qwen3vl8b", "SPARSE", sparse_tokens, 3500),
        ("qwen3vl8b", "DENSE",  dense_tokens,  3500),
    ]
    n_q = len(qa_rows)
    total_s = 0.0
    log(f"\n  Runtime projection ({n_q} questions, median qt={med_qt:.0f}s):")
    for slug, mode, toks, tok_s in configs:
        secs_per_q = toks / tok_s + 0.05  # +50ms decode/overhead
        total_config = secs_per_q * n_q
        log(f"    {slug} {mode}: {toks} tok/q → {secs_per_q:.1f}s/q → {total_config/60:.0f} min")
        total_s += total_config
    log(f"  Total estimate: {total_s/3600:.2f} h (limit {RUNTIME_LIMIT_S/3600:.0f} h)")

    if total_s > RUNTIME_LIMIT_S:
        sys.exit(f"STOP: projected runtime {total_s/3600:.2f}h > {RUNTIME_LIMIT_S/3600:.0f}h limit")
    return total_s


# ── PHASE 3: INFER — outer loop ───────────────────────────────────────────────

def run_inference(mcq_rows: list[dict], manifest: dict) -> None:
    vid_set = set(manifest["video_ids"])
    qa_subset = [r for r in mcq_rows
                 if r["video_id"] in vid_set and r["question_category"] in CATEGORIES]

    log(f"\n  INFER: {len(qa_subset)} questions across {len(vid_set)} videos")
    est_secs = estimate_runtime(qa_subset)

    done_keys = load_done_keys(TRIALS_PATH)
    log(f"  Already done: {len(done_keys)} trials")

    for cfg in MODEL_CONFIGS:
        slug = cfg["slug"]
        snap = cfg["snap"]

        for mode in SAMPLING_MODES:
            pending = [r for r in qa_subset
                       if (slug, mode, r["question_id"]) not in done_keys]
            if not pending:
                log(f"\n  {slug} × {mode}: all {len(qa_subset)} done, skipping")
                continue

            log(f"\n  {'='*60}")
            log(f"  Loading {slug} from {snap}")
            proc = AutoProcessor.from_pretrained(
                snap,
                min_pixels=256 * 28 * 28,
                max_pixels=1280 * 28 * 28,
            )
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                snap,
                torch_dtype=DTYPE,
                attn_implementation="flash_attention_2",
                device_map=DEVICE,
            )
            model.eval()
            log(f"  {slug} loaded. Running {mode} on {len(pending)} pending questions")

            n_correct = 0
            n_total = 0
            t_phase_start = time.perf_counter()

            for i, qa_row in enumerate(pending, 1):
                vid_id = qa_row["video_id"]
                video_path = VIDEO_DIR / f"{vid_id}.mp4"
                if not video_path.exists():
                    # Try nested path from hf_hub_download
                    alt = VIDEO_DIR / "videos" / f"{vid_id}.mp4"
                    if alt.exists():
                        video_path = alt
                    else:
                        log(f"  MISSING video: {vid_id}")
                        continue

                try:
                    rec = run_single_trial(
                        proc, model, qa_row, None, video_path, mode, slug
                    )
                except Exception as e:
                    log(f"  ERROR trial {qa_row['question_id']}: {e}")
                    rec = {
                        "model": slug, "sampling": mode,
                        "video_id": vid_id,
                        "question_id": qa_row["question_id"],
                        "error": str(e)[:200],
                    }

                write_jsonl_append(TRIALS_PATH, rec)
                done_keys.add((slug, mode, qa_row["question_id"]))

                if rec.get("correct") is not None:
                    n_correct += rec["correct"]
                    n_total += 1

                if i % 20 == 0 or i == len(pending):
                    elapsed = time.perf_counter() - t_phase_start
                    rate = i / elapsed if elapsed > 0 else 0
                    acc = n_correct / n_total if n_total > 0 else 0
                    log(f"  [{i}/{len(pending)}] elapsed={elapsed/60:.1f}min "
                        f"rate={rate:.2f}q/s acc={acc:.3f}")

            del model
            gc.collect()
            torch.cuda.empty_cache()


# ── PHASE 4: ANALYSIS ─────────────────────────────────────────────────────────

def load_trials() -> list[dict]:
    rows = []
    with open(TRIALS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if "error" not in r and "correct" in r:
                    rows.append(r)
            except json.JSONDecodeError:
                pass
    return rows


def acc(rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    return sum(r["correct"] for r in rows) / len(rows)


def run_analysis(mcq_rows: list[dict]) -> None:
    trials = load_trials()
    log(f"\n  ANALYSE: {len(trials)} valid trials")

    by_model_mode: dict[tuple, list] = defaultdict(list)
    for r in trials:
        by_model_mode[(r["model"], r["sampling"])].append(r)

    # ── Analysis A: Overall accuracy ─────────────────────────────────────────
    log("\n  A — Overall accuracy")
    overall: dict[str, dict] = {}
    for (slug, mode), rows in sorted(by_model_mode.items()):
        key = f"{slug}_{mode}"
        a = acc(rows)
        overall[key] = {"n": len(rows), "acc": round(a, 4)}
        log(f"    {key}: n={len(rows)} acc={a:.3f}")

    # Gap: 8B minus 4B
    for mode in SAMPLING_MODES:
        k4 = f"qwen3vl4b_{mode}"
        k8 = f"qwen3vl8b_{mode}"
        if k4 in overall and k8 in overall:
            gap = overall[k8]["acc"] - overall[k4]["acc"]
            log(f"    Gap 8B-4B ({mode}): {gap:+.3f}")
            overall[f"gap_{mode}"] = round(gap, 4)

    # ── Analysis B: Accuracy by category ─────────────────────────────────────
    log("\n  B — Accuracy by category")
    by_cat: dict[str, dict] = {}
    for cat in CATEGORIES:
        by_cat[cat] = {}
        for (slug, mode), rows in sorted(by_model_mode.items()):
            cat_rows = [r for r in rows if r["category"] == cat]
            key = f"{slug}_{mode}"
            by_cat[cat][key] = {"n": len(cat_rows), "acc": round(acc(cat_rows), 4)}
        # Gap per category
        for mode in SAMPLING_MODES:
            k4 = f"qwen3vl4b_{mode}"
            k8 = f"qwen3vl8b_{mode}"
            if k4 in by_cat[cat] and k8 in by_cat[cat]:
                gap = by_cat[cat][k8]["acc"] - by_cat[cat][k4]["acc"]
                by_cat[cat][f"gap_{mode}"] = round(gap, 4)
        log(f"    {cat}: " + ", ".join(
            f"{k}={v['acc']:.3f}(n={v['n']})"
            for k, v in sorted(by_cat[cat].items()) if "gap" not in k
        ))

    # ── Analysis C: Accuracy vs evidence distance ─────────────────────────────
    log("\n  C — Accuracy vs evidence distance (nearest_dist_s bins)")
    dist_bins = [0, 5, 30, 60, 120, float("inf")]
    dist_labels = ["[0,5)", "[5,30)", "[30,60)", "[60,120)", "[120,∞)"]
    by_dist: dict[str, dict] = {}
    for label in dist_labels:
        by_dist[label] = {}
    for (slug, mode), rows in sorted(by_model_mode.items()):
        key = f"{slug}_{mode}"
        for label, lo, hi in zip(dist_labels, dist_bins[:-1], dist_bins[1:]):
            bin_rows = [r for r in rows
                        if lo <= r.get("nearest_dist_s", -1) < hi]
            by_dist[label][key] = {"n": len(bin_rows), "acc": round(acc(bin_rows), 4)}
    for label in dist_labels:
        log(f"    {label}: " + ", ".join(
            f"{k}={v['acc']:.3f}(n={v['n']})"
            for k, v in sorted(by_dist[label].items())
        ))

    # ── Analysis D: Latency ───────────────────────────────────────────────────
    log("\n  D — Latency (total_latency_ms) and n_input_tokens")
    latency: dict[str, dict] = {}
    for (slug, mode), rows in sorted(by_model_mode.items()):
        key = f"{slug}_{mode}"
        lats = [r["total_latency_ms"] for r in rows if "total_latency_ms" in r]
        toks = [r["n_input_tokens"] for r in rows if "n_input_tokens" in r]
        if lats:
            latency[key] = {
                "lat_med_ms": round(statistics.median(lats), 1),
                "lat_p90_ms": round(sorted(lats)[int(0.9 * len(lats))], 1),
                "tokens_med": round(statistics.median(toks), 0) if toks else None,
            }
            log(f"    {key}: lat_med={latency[key]['lat_med_ms']}ms "
                f"lat_p90={latency[key]['lat_p90_ms']}ms "
                f"tok_med={latency[key]['tokens_med']}")

    # ── Analysis E: Coverage arithmetic ──────────────────────────────────────
    log("\n  E — Coverage arithmetic (correct formula: ast-based)")
    # How much of the evidence is covered by windows of size k?
    # Coverage requires: ast >= qt - k, i.e., farthest_dist <= k
    # Using the 4B SPARSE trials as the reference set for evidence distance
    ref_rows = [r for r in trials
                if r["model"] == "qwen3vl4b" and r["sampling"] == "SPARSE"]
    n_ref = len(ref_rows)
    coverage_by_k: dict[str, float] = {}
    for k in [3, 10, 30, 60, 120, 300]:
        covered = sum(1 for r in ref_rows
                      if r.get("farthest_dist_s", float("inf")) <= k)
        frac = covered / n_ref if n_ref > 0 else 0
        coverage_by_k[str(k)] = round(frac, 4)
        log(f"    window k={k:4d}s: {covered}/{n_ref} = {frac:.1%} evidence covered")
    log(f"  (Coverage requires ENTIRE [ast,aet] window within [qt-k, qt], "
        f"binding constraint = qt - ast = farthest_dist)")

    results = {
        "n_trials_total": len(trials),
        "A_overall": overall,
        "B_by_category": by_cat,
        "C_by_evidence_dist": by_dist,
        "D_latency": latency,
        "E_coverage": coverage_by_k,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\n  Results written: {RESULTS_PATH}")

    # Verdict on two-tier placement question
    gaps_by_mode = {mode: overall.get(f"gap_{mode}", float("nan"))
                    for mode in SAMPLING_MODES}
    log("\n  VERDICT — Does two-tier placement have anything to decide?")
    for mode, gap in gaps_by_mode.items():
        log(f"    {mode}: 8B-4B gap = {gap:+.3f}")
    gap_by_cat = {
        cat: by_cat[cat].get("gap_SPARSE", float("nan")) for cat in CATEGORIES
    }
    log("  Category gap range (SPARSE): "
        f"min={min(gap_by_cat.values()):.3f} "
        f"max={max(gap_by_cat.values()):.3f}")


# ── PROVENANCE ────────────────────────────────────────────────────────────────

def stamp() -> dict:
    import subprocess
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        sha = "pre-provenance"
    return {
        "git_commit": sha,
        "script": "study_i_tier_gap.py",
        "models": [c["slug"] for c in MODEL_CONFIGS],
        "device": "nvidia_rtx_a6000",
        "n_videos": N_VIDEOS,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)

    log("=== Study I — S-EMBER tier gap ===\n")

    mcq_rows = load_jsonl(MCQ_PATH)
    log(f"Loaded {len(mcq_rows)} MCQ rows")

    # ── SELECT ───────────────────────────────────────────────────────────────
    if MANIFEST_PATH.exists():
        log(f"\nPHASE SELECT: manifest exists, loading {MANIFEST_PATH}")
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        log(f"  {manifest['n_videos']} videos, {manifest['n_qa']} QA, "
            f"est {manifest['est_download_gb']} GB")
    else:
        log("\nPHASE SELECT")
        selected_vids, _ = select_videos(mcq_rows)
        manifest = write_manifest(selected_vids, mcq_rows)

    # ── DOWNLOAD ─────────────────────────────────────────────────────────────
    vid_set = set(manifest["video_ids"])
    n_present = sum(1 for v in vid_set if (VIDEO_DIR / f"{v}.mp4").exists())
    if n_present == manifest["n_videos"]:
        log(f"\nPHASE DOWNLOAD: all {n_present} videos already present, skipping")
    else:
        log(f"\nPHASE DOWNLOAD: {n_present}/{manifest['n_videos']} present, downloading missing")
        download_videos(manifest)
        n_present = sum(1 for v in vid_set if (VIDEO_DIR / f"{v}.mp4").exists())
        log(f"  After download: {n_present}/{manifest['n_videos']} videos present")

    # ── INFER ─────────────────────────────────────────────────────────────────
    log("\nPHASE INFER")
    run_inference(mcq_rows, manifest)

    # ── ANALYSE ──────────────────────────────────────────────────────────────
    log("\nPHASE ANALYSE")
    if TRIALS_PATH.exists():
        run_analysis(mcq_rows)
    else:
        log("  No trials file found — ANALYSE skipped")

    prov = stamp()
    log(f"\nProvenance: {prov}")
    log("\nDone. Ask user to commit results.")


if __name__ == "__main__":
    main()
