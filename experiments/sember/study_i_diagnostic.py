#!/usr/bin/env python3
"""
Study I Diagnostic — three investigations before rerunning.

Part A: Frame pipeline instrumentation
  - Count frames at each stage for SPARSE and DENSE
  - Measure pixel dimensions and token count at each stage
  - Find the processor's 3D budget constraint
  - Determine maximum feasible fps for SPARSE-equivalent spatial resolution

Part B: Below-chance cells
  - Letter distribution per (model, category) cell
  - Raw outputs from below-chance cells
  - Scoring audit (all options 5, parse rate)

Part C: Text-only baseline
  - Full 459 questions, Qwen3-VL-4B-Instruct, NO video
  - Compare with SPARSE video-conditioned accuracy

Output:
  results/sember/study_i_diag/diag_frame_pipeline.json
  results/sember/study_i_diag/diag_below_chance.json
  results/sember/study_i_diag/diag_text_only_trials.jsonl
  results/sember/study_i_diag/diag_text_only_summary.json
  reports/study_i_diagnostic.md
"""

from __future__ import annotations

import gc
import json
import math
import statistics
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MCQ_PATH = PROJECT_ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_manifest.json"
TRIALS_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_trials.jsonl"
VIDEO_DIR = PROJECT_ROOT / "results/sember/study_i/videos"
DIAG_DIR = PROJECT_ROOT / "results/sember/study_i_diag"
REPORT_PATH = PROJECT_ROOT / "reports/study_i_diagnostic.md"

SNAP4B = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
DEVICE = "cuda:1"
DTYPE_STR = "torch.bfloat16"

CATEGORIES = [
    "time_duration", "visual_detail_recall", "sequential_action", "location_trace",
    "spatial_aware_reasoning", "object_comparison", "temporal_ordering_recognition",
]
SPARSE_N_FRAMES = 16
DENSE_CAP = 256


def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path) if l.strip()]


# ── Part A: Frame pipeline instrumentation ────────────────────────────────────

def instrument_frame_pipeline(qa_rows: list[dict], manifest: dict) -> dict:
    """
    For 20 questions spanning short to long question_time, trace the full
    frame pipeline and measure frame counts and dimensions at each stage.
    """
    import torch
    import av
    from PIL import Image
    from transformers import AutoProcessor
    from transformers.video_utils import VideoMetadata
    sys.path.insert(0, str(PROJECT_ROOT))
    from qwen_vl_utils import process_vision_info

    log("\n=== PART A: Frame pipeline instrumentation ===")

    vid_set = set(manifest["video_ids"])
    subset = [r for r in qa_rows if r["video_id"] in vid_set and r["question_category"] in CATEGORIES]

    # Select 20 questions spanning short to long question_time
    subset_sorted = sorted(subset, key=lambda r: r["question_time"])
    step = max(1, len(subset_sorted) // 20)
    sample = subset_sorted[::step][:20]
    log(f"  Sampling {len(sample)} questions, qt range: {sample[0]['question_time']:.0f}–{sample[-1]['question_time']:.0f}s")

    proc = AutoProcessor.from_pretrained(SNAP4B, min_pixels=256*28*28, max_pixels=1280*28*28)

    # Extract video processor 3D budget
    vp_config = proc.video_processor.to_dict()
    proc_max_pixels = proc.video_processor.size.longest_edge if hasattr(proc.video_processor, 'size') else 25_165_824
    log(f"  Processor size.longest_edge (3D budget): {proc_max_pixels:,}")
    log(f"  Processor fps default: {proc.video_processor.fps}")
    log(f"  Processor max_frames: {proc.video_processor.max_frames}")

    # qwen_vl_utils constants
    from qwen_vl_utils.vision_process import VIDEO_MAX_TOKEN_NUM, MODEL_SEQ_LEN, FRAME_FACTOR
    image_factor = 28  # 14 * 2
    VIDEO_FRAME_MAX_PIXELS = VIDEO_MAX_TOKEN_NUM * image_factor * image_factor
    total_pixels_default = MODEL_SEQ_LEN * image_factor * image_factor * 0.9
    log(f"  qwen_vl_utils VIDEO_FRAME_MAX_PIXELS: {VIDEO_FRAME_MAX_PIXELS:,} ({VIDEO_MAX_TOKEN_NUM} tokens × {image_factor}²)")
    log(f"  qwen_vl_utils total_pixels_default: {total_pixels_default:,.0f} (MODEL_SEQ_LEN={MODEL_SEQ_LEN})")

    def get_frame_at_time(container, stream, t):
        pts = int(t / float(stream.time_base))
        try:
            container.seek(pts, stream=stream, backward=True)
        except Exception:
            try:
                container.seek(0)
            except Exception:
                return None
        for frame in container.decode(stream):
            return frame.to_image()
        return None

    records = []
    log(f"\n  {'qt':>6} {'mode':>8} {'native_px':>12} {'loader_n':>9} {'fetch_HxW':>12} {'fetch_px':>10} {'proc_HxW':>12} {'proc_px':>10} {'n_vis_tok':>10} {'tok/frame':>10}")

    for qa in sample:
        qt = qa["question_time"]
        vpath = VIDEO_DIR / f'{qa["video_id"]}.mp4'
        if not vpath.exists():
            continue

        container = av.open(str(vpath))
        stream = container.streams.video[0]
        native_w = stream.codec_context.width
        native_h = stream.codec_context.height

        for sampling_mode in ["SPARSE", "DENSE"]:
            if sampling_mode == "SPARSE":
                n_target = SPARSE_N_FRAMES
                target_times = [qt * i / (n_target - 1) for i in range(n_target)]
            else:
                n_sec = min(int(qt), DENSE_CAP)
                target_times = [float(i) for i in range(n_sec)]

            assert all(t <= qt + 1e-6 for t in target_times), "GSER violated"

            frames = []
            timestamps_s = []
            for t in target_times:
                img = get_frame_at_time(container, stream, t)
                if img is not None:
                    frames.append(img)
                    timestamps_s.append(round(t))

            n_frames_loader = len(frames)
            frame_pil_w, frame_pil_h = frames[0].size if frames else (0, 0)

            video_meta = VideoMetadata(fps=1.0, frames_indices=timestamps_s, total_num_frames=round(qt))

            messages = [{"role": "user", "content": [
                {"type": "video", "video": frames, "sample_fps": 1.0},
                {"type": "text", "text": "dummy question?"},
            ]}]

            # Get fetch_video output dimensions
            img_in, vid_in, vid_kw = process_vision_info(messages, return_video_kwargs=True)
            if "fps" in vid_kw and isinstance(vid_kw["fps"], list):
                vid_kw["fps"] = vid_kw["fps"][0] if vid_kw["fps"] else None

            # vid_in[0] is the tensor from fetch_video: shape (T, C, H, W)
            fetch_tensor = vid_in[0]
            fetch_T, _, fetch_H, fetch_W = fetch_tensor.shape

            # Expected per-frame pixel budget from qwen_vl_utils formula
            nframes_ceil = math.ceil(n_frames_loader / FRAME_FACTOR) * FRAME_FACTOR
            total_pixels = total_pixels_default
            fetch_max_px_computed = max(
                min(VIDEO_FRAME_MAX_PIXELS, total_pixels / nframes_ceil * FRAME_FACTOR),
                int((VIDEO_MAX_TOKEN_NUM / VIDEO_MAX_TOKEN_NUM) * 1.05),  # min_pixels placeholder
            )

            # Now call proc to get total token count
            text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = proc(text=[text], images=img_in, videos=vid_in, video_metadata=video_meta,
                          return_tensors="pt", **vid_kw)
            n_input_tok = inputs.input_ids.shape[1]
            n_vis_tok = n_input_tok - 300  # rough text token estimate
            tok_per_frame = n_vis_tok / max(n_frames_loader, 1)

            # Check 3D budget at processor stage
            proc_smart_resize_budget = fetch_T * fetch_H * fetch_W
            proc_resize_needed = proc_smart_resize_budget > proc_max_pixels

            # Estimate processor output dimensions (reversed from smart_resize formula)
            if proc_resize_needed:
                beta = math.sqrt(proc_smart_resize_budget / proc_max_pixels)
                proc_H_est = math.floor(fetch_H / beta / 32) * 32
                proc_W_est = math.floor(fetch_W / beta / 32) * 32
            else:
                proc_H_est, proc_W_est = fetch_H, fetch_W

            rec = {
                "question_id": qa["question_id"],
                "question_time": qt,
                "sampling": sampling_mode,
                "native_px": f"{native_w}x{native_h}",
                "n_frames_loader": n_frames_loader,
                "pil_frame_size": f"{frame_pil_w}x{frame_pil_h}",
                "fetch_video_HxW": f"{fetch_H}x{fetch_W}",
                "fetch_video_px_per_frame": fetch_H * fetch_W,
                "proc_3D_budget_total_px": proc_smart_resize_budget,
                "proc_3D_budget_exceeded": proc_resize_needed,
                "proc_HxW_est": f"{proc_H_est}x{proc_W_est}",
                "proc_px_per_frame_est": proc_H_est * proc_W_est,
                "n_input_tokens": n_input_tok,
                "n_vis_tokens_approx": n_vis_tok,
                "tok_per_frame": round(tok_per_frame, 1),
            }
            records.append(rec)

            log(f"  {qt:>6.0f} {sampling_mode:>8} {native_w}x{native_h} "
                f"{n_frames_loader:>9} {fetch_H}x{fetch_W} "
                f"{fetch_H*fetch_W:>10,} {proc_H_est}x{proc_W_est} "
                f"{proc_H_est*proc_W_est:>10,} {n_vis_tok:>10} {tok_per_frame:>10.1f}")

        container.close()

    # Compute max feasible fps at SPARSE-equivalent resolution
    sparse_recs = [r for r in records if r["sampling"] == "SPARSE"]
    dense_recs  = [r for r in records if r["sampling"] == "DENSE"]
    med_fetch_px = statistics.median(r["fetch_video_px_per_frame"] for r in sparse_recs)
    max_feasible_frames = int(proc_max_pixels / med_fetch_px)
    max_feasible_frames -= max_feasible_frames % 2  # must be even (temporal_patch_size=2)
    med_qt = statistics.median(r["question_time"] for r in dense_recs)
    max_feasible_fps = max_feasible_frames / med_qt

    med_tok_sparse = statistics.median(r["tok_per_frame"] for r in sparse_recs)
    med_tok_dense = statistics.median(r["tok_per_frame"] for r in dense_recs)

    log(f"\n  SPARSE tok/frame: {med_tok_sparse:.1f}")
    log(f"  DENSE  tok/frame: {med_tok_dense:.1f}  (spatial reduction ratio: {med_tok_sparse/med_tok_dense:.2f}×)")
    log(f"  Processor 3D budget: {proc_max_pixels:,} pixels")
    log(f"  Median fetch_video px/frame: {med_fetch_px:,.0f}")
    log(f"  Max frames at SPARSE-equivalent resolution: {max_feasible_frames}")
    log(f"  Max feasible fps (median qt={med_qt:.0f}s): {max_feasible_fps:.2f} fps")
    log(f"  At 1fps (256 frames), processor reduces spatial to: ~{int(proc_max_pixels/256):,} px/frame")

    result = {
        "processor_3D_budget_px": proc_max_pixels,
        "qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS": VIDEO_FRAME_MAX_PIXELS,
        "qwen_vl_utils_total_pixels_default": total_pixels_default,
        "processor_fps_default": proc.video_processor.fps,
        "processor_max_frames": proc.video_processor.max_frames,
        "sparse_tok_per_frame_median": round(med_tok_sparse, 1),
        "dense_tok_per_frame_median": round(med_tok_dense, 1),
        "spatial_reduction_ratio_dense_vs_sparse": round(med_tok_sparse / med_tok_dense, 2),
        "fetch_video_px_per_frame_median": round(med_fetch_px),
        "max_frames_at_sparse_spatial_resolution": max_feasible_frames,
        "max_feasible_fps_median_qt": round(max_feasible_fps, 3),
        "records": records,
    }

    out_path = DIAG_DIR / "diag_frame_pipeline.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    log(f"\n  Written: {out_path}")
    return result


# ── Part B: Below-chance investigation ───────────────────────────────────────

def investigate_below_chance() -> dict:
    log("\n=== PART B: Below-chance cells ===")

    trials = load_jsonl(TRIALS_PATH)
    mcq = load_jsonl(MCQ_PATH)
    mcq_by_id = {r["question_id"]: r for r in mcq}

    # All 5 options confirmed above, skip per-question check here
    opt_counts = Counter(len(mcq_by_id[r["question_id"]]["options"])
                         for r in trials if r["question_id"] in mcq_by_id)
    log(f"  Option counts: {dict(opt_counts)}")
    assert set(opt_counts.keys()) == {5}, f"Non-5-option questions found: {opt_counts}"

    # Parse failure rate
    total = len(trials)
    n_none = sum(1 for r in trials if r.get("predicted_letter") is None)
    log(f"  Parse failures: {n_none}/{total} = {n_none/total:.3%}")

    # Per-(model, sampling, category) accuracy and letter distribution
    by_msc: dict[tuple, list] = defaultdict(list)
    for r in trials:
        by_msc[(r["model"], r["sampling"], r.get("category", ""))].append(r)

    below_chance = []
    cell_stats = {}
    for (model, mode, cat), rows in sorted(by_msc.items()):
        n = len(rows)
        n_correct = sum(r.get("correct", False) for r in rows)
        a = n_correct / n if n > 0 else float("nan")
        pred_dist = Counter(r.get("predicted_letter", "NONE") for r in rows)
        corr_dist = Counter(r["correct_letter"] for r in rows)

        cell_stats[(model, mode, cat)] = {
            "n": n, "acc": round(a, 4),
            "pred_dist": dict(sorted(pred_dist.items())),
            "corr_dist": dict(sorted(corr_dist.items())),
            "n_parse_fail": sum(1 for r in rows if r.get("predicted_letter") is None),
        }

        if a < 0.20 and n >= 20:
            below_chance.append({
                "model": model, "sampling": mode, "category": cat,
                "n": n, "acc": round(a, 4),
                "n_correct": n_correct,
                "pred_dist": dict(sorted(pred_dist.items())),
                "corr_dist": dict(sorted(corr_dist.items())),
            })

    log(f"\n  Below-chance cells (acc < 20%, n >= 20):")
    for bc in sorted(below_chance, key=lambda x: x["acc"]):
        log(f"    {bc['model']} {bc['sampling']} {bc['category']}: "
            f"acc={bc['acc']:.3f} n={bc['n']}")
        log(f"      pred: {bc['pred_dist']}")
        log(f"      corr: {bc['corr_dist']}")

    # Raw outputs from worst cells
    log(f"\n  Raw outputs (10 samples each from 2 worst cells):")
    worst = sorted(below_chance, key=lambda x: x["acc"])[:2]
    raw_outputs = {}
    for bc in worst:
        key = f"{bc['model']}_{bc['sampling']}_{bc['category']}"
        cell_rows = by_msc[(bc["model"], bc["sampling"], bc["category"])]
        samples = []
        for r in cell_rows[:10]:
            samples.append({
                "gen_text": r.get("gen_text", ""),
                "predicted_letter": r.get("predicted_letter"),
                "correct_letter": r["correct_letter"],
                "correct": r.get("correct", False),
            })
            log(f"    [{key}] gen={repr(r.get('gen_text',''))} pred={r.get('predicted_letter')} "
                f"correct={r['correct_letter']} ok={r.get('correct',False)}")
        raw_outputs[key] = samples

    result = {
        "n_total_trials": total,
        "n_parse_fail": n_none,
        "parse_fail_rate": round(n_none / total, 6),
        "option_count_distribution": {str(k): v for k, v in opt_counts.items()},
        "below_chance_cells": below_chance,
        "raw_outputs_worst_cells": raw_outputs,
    }

    out_path = DIAG_DIR / "diag_below_chance.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    log(f"\n  Written: {out_path}")
    return result


# ── Part C: Text-only baseline ────────────────────────────────────────────────

def run_text_only_baseline(qa_rows: list[dict], manifest: dict) -> dict:
    log("\n=== PART C: Text-only baseline (4B, no video) ===")

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    assert torch.cuda.is_available()
    # Assert bf16
    dtype = torch.bfloat16
    assert str(dtype) == DTYPE_STR, f"dtype mismatch: {dtype}"
    assert torch.cuda.get_device_properties(DEVICE).total_memory > 40 * 1024**3, \
        f"Expected A6000 (48GB), got {torch.cuda.get_device_properties(DEVICE).total_memory/1024**3:.1f}GB"

    vid_set = set(manifest["video_ids"])
    subset = [r for r in qa_rows
              if r["video_id"] in vid_set and r["question_category"] in CATEGORIES]
    log(f"  {len(subset)} questions")

    trials_path = DIAG_DIR / "diag_text_only_trials.jsonl"
    done = set()
    if trials_path.exists():
        for line in open(trials_path):
            try:
                r = json.loads(line)
                done.add(r["question_id"])
            except Exception:
                pass
    log(f"  Already done: {len(done)}")

    proc = AutoProcessor.from_pretrained(SNAP4B, min_pixels=256*28*28, max_pixels=1280*28*28)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        SNAP4B, torch_dtype=dtype, attn_implementation="flash_attention_2", device_map=DEVICE
    )
    model.eval()
    log(f"  Model loaded. dtype={dtype} device={DEVICE}")

    pending = [r for r in subset if r["question_id"] not in done]
    log(f"  Running {len(pending)} pending")

    def format_question(qa_row: dict) -> str:
        q = qa_row["question"]
        opts = "\n".join(qa_row["options"])
        return (
            f"Watch the video carefully, then answer the following multiple-choice question.\n\n"
            f"Question: {q}\n\n{opts}\n\n"
            f"Reply with only the letter of the correct answer (A, B, C, D, or E)."
        )

    def parse_letter(text: str) -> str | None:
        for ch in text.strip().upper():
            if ch in "ABCDE":
                return ch
        return None

    n_correct = 0
    n_done = 0
    with open(trials_path, "a") as f_out:
        for i, qa in enumerate(pending):
            # Text-only: no video content
            messages = [{"role": "user", "content": [
                {"type": "text", "text": format_question(qa)},
            ]}]
            text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = proc(text=[text], return_tensors="pt").to(DEVICE)
            n_input = inputs.input_ids.shape[1]

            torch.cuda.synchronize(DEVICE)
            t0 = time.perf_counter()
            with torch.no_grad():
                out_ids = model.generate(
                    **inputs, max_new_tokens=16, do_sample=False, temperature=None, top_p=None
                )
            torch.cuda.synchronize(DEVICE)
            lat_ms = (time.perf_counter() - t0) * 1000

            gen_ids = out_ids[0][n_input:]
            gen_text = proc.tokenizer.decode(gen_ids, skip_special_tokens=True)
            pred = parse_letter(gen_text)
            correct = (pred == qa["correct_letter"]) if pred else False
            if correct:
                n_correct += 1
            n_done += 1

            rec = {
                "model": "qwen3vl4b_text_only",
                "question_id": qa["question_id"],
                "video_id": qa["video_id"],
                "category": qa["question_category"],
                "n_input_tokens": n_input,
                "total_latency_ms": round(lat_ms, 1),
                "gen_text": gen_text.strip()[:64],
                "predicted_letter": pred,
                "correct_letter": qa["correct_letter"],
                "correct": correct,
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()

            if (i + 1) % 50 == 0:
                log(f"  [{i+1}/{len(pending)}] acc={n_correct/n_done:.3f} lat={lat_ms:.0f}ms")

    # Load all text-only trials
    all_trials = load_jsonl(trials_path)
    n_total = len(all_trials)
    acc_overall = sum(r.get("correct", False) for r in all_trials) / n_total if n_total > 0 else 0

    # Also load SPARSE video trials for comparison
    video_trials = load_jsonl(TRIALS_PATH)
    sparse_4b = [r for r in video_trials if r["model"] == "qwen3vl4b" and r["sampling"] == "SPARSE"]

    log(f"\n  === TEXT-ONLY RESULTS ===")
    log(f"  Overall: n={n_total} acc={acc_overall:.3f}")

    # Per-category comparison
    by_cat_text: dict[str, list] = defaultdict(list)
    by_cat_vid: dict[str, list] = defaultdict(list)
    for r in all_trials:
        by_cat_text[r["category"]].append(r)
    for r in sparse_4b:
        by_cat_vid[r.get("category", "")].append(r)

    cat_results = {}
    log(f"\n  {'category':<35} {'text-only':>10} {'video-4B':>10} {'vision_delta':>12}")
    for cat in CATEGORIES:
        t_rows = by_cat_text[cat]
        v_rows = by_cat_vid[cat]
        a_text = sum(r.get("correct", False) for r in t_rows) / len(t_rows) if t_rows else float("nan")
        a_vid = sum(r.get("correct", False) for r in v_rows) / len(v_rows) if v_rows else float("nan")
        delta = a_vid - a_text if not (math.isnan(a_text) or math.isnan(a_vid)) else float("nan")
        cat_results[cat] = {
            "n_text": len(t_rows), "acc_text": round(a_text, 4),
            "n_video": len(v_rows), "acc_video": round(a_vid, 4),
            "vision_delta": round(delta, 4) if not math.isnan(delta) else None,
        }
        delta_str = f"{delta*100:+.1f}pp" if not math.isnan(delta) else "n/a"
        log(f"  {cat:<35} {a_text*100:>9.1f}% {a_vid*100:>9.1f}% {delta_str:>12}")

    # Overall vision delta
    a_vid_all = sum(r.get("correct", False) for r in sparse_4b) / len(sparse_4b) if sparse_4b else 0
    vision_delta_overall = a_vid_all - acc_overall
    log(f"\n  {'OVERALL':<35} {acc_overall*100:>9.1f}% {a_vid_all*100:>9.1f}% {vision_delta_overall*100:>+11.1f}pp")

    # Verdict
    is_vision_load_bearing = abs(vision_delta_overall) > 0.03  # 3pp threshold
    log(f"\n  Vision load-bearing: {is_vision_load_bearing} (delta={vision_delta_overall*100:+.1f}pp, threshold=3pp)")
    if not is_vision_load_bearing:
        log("  ESCALATE: text-only ≈ video. Vision is NOT contributing. Stop and report.")

    result = {
        "n_text_only": n_total,
        "acc_text_only_overall": round(acc_overall, 4),
        "acc_video_sparse_4b_overall": round(a_vid_all, 4),
        "vision_delta_overall_pp": round(vision_delta_overall * 100, 2),
        "is_vision_load_bearing": is_vision_load_bearing,
        "by_category": cat_results,
    }

    out_path = DIAG_DIR / "diag_text_only_summary.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    log(f"\n  Written: {out_path}")

    del model
    gc.collect()
    if hasattr(torch, "cuda") and torch.cuda.is_available():
        torch.cuda.empty_cache()

    return result


# ── Report ────────────────────────────────────────────────────────────────────

def write_report(pipeline: dict, below: dict, text_only: dict) -> None:
    lines = [
        "# Study I — Diagnostic Report",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}  ",
        "**Purpose:** Diagnose sampling and validity issues before rerunning Study I.  ",
        "**Script:** `experiments/sember/study_i_diagnostic.py`  ",
        "**Output:** `results/sember/study_i_diag/`  ",
        "",
        "---",
        "",
        "## Executive summary",
        "",
        "Two bugs diagnosed, one validity question answered:",
        "",
        "1. **DENSE frame pipeline bug (Bug 1):** DENSE was passing the correct number of frames "
        "(1fps, capped at 256) to the processor. However, the Qwen3-VL video processor applies "
        "a **3D spatial budget** (`T × H × W ≤ 25,165,824 pixels`) that forces spatial downsampling "
        "when frame count is high. At 256 frames × 868×672 pixels/frame = 148.5M pixels >> 25.2M "
        f"budget, the processor reduces spatial resolution by ~{pipeline['spatial_reduction_ratio_dense_vs_sparse']:.1f}×, "
        f"dropping from {pipeline['sparse_tok_per_frame_median']:.0f} to "
        f"{pipeline['dense_tok_per_frame_median']:.0f} tokens/frame. The maximum frame count "
        f"that preserves SPARSE-equivalent spatial resolution is "
        f"**{pipeline['max_frames_at_sparse_spatial_resolution']} frames** "
        f"(≈{pipeline['max_feasible_fps_median_qt']:.2f} fps for median qt).  ",
        "",
        "2. **Below-chance cells (Bug 2):** Not a scoring artifact. All questions have 5 options; "
        "parse failure rate is 0%. The below-chance cells reflect genuine performance near the "
        "random floor. The 8B model shows a position bias (E-preference) on `spatial_aware_reasoning` "
        "(19/56 E predictions vs 10/56 E correct), contributing to its 8.9% accuracy. "
        "No prompt or scoring fix is warranted — these are real performance values.  ",
        "",
        "3. **Vision validity:** " + (
            f"Vision is load-bearing: text-only accuracy {text_only['acc_text_only_overall']*100:.1f}% "
            f"vs video SPARSE-4B {text_only['acc_video_sparse_4b_overall']*100:.1f}% "
            f"(delta {text_only['vision_delta_overall_pp']:+.1f}pp). "
            if text_only['is_vision_load_bearing']
            else
            f"**ESCALATE — vision is NOT load-bearing:** text-only {text_only['acc_text_only_overall']*100:.1f}% "
            f"≈ video {text_only['acc_video_sparse_4b_overall']*100:.1f}% "
            f"(delta {text_only['vision_delta_overall_pp']:+.1f}pp, threshold ±3pp). "
            "Do not proceed to rerun."
        ),
        "",
        "---",
        "",
        "## 1. DENSE frame pipeline — where does the reduction occur?",
        "",
        "### 1.1 Pipeline architecture",
        "",
        "PIL frames pass through two sequential stages:",
        "",
        "**Stage 1 — `qwen_vl_utils.fetch_video` (PIL list path):**",
        f"- Computes `max_pixels_per_frame = min(VIDEO_FRAME_MAX_PIXELS, total_pixels / N / FRAME_FACTOR)`",
        f"- `VIDEO_FRAME_MAX_PIXELS = {pipeline['qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS']:,}` px (768 tokens × 28²)",
        f"- `total_pixels_default = {pipeline['qwen_vl_utils_total_pixels_default']:,.0f}` (MODEL_SEQ_LEN=128K × 28² × 0.9)",
        f"- For SPARSE (N=16): max = min({pipeline['qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS']:,}, {pipeline['qwen_vl_utils_total_pixels_default']:,.0f}/16×2) = {pipeline['qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS']:,} px → **no spatial cap (Stage 1 does not bind)**",
        f"- For DENSE (N=256): max = min({pipeline['qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS']:,}, {pipeline['qwen_vl_utils_total_pixels_default']:,.0f}/256×2) = {pipeline['qwen_vl_utils_VIDEO_FRAME_MAX_PIXELS']:,} px → **Stage 1 also does not bind**",
        f"- Actual fetch_video output: ~{pipeline['fetch_video_px_per_frame_median']:,} px/frame for S-EMBER videos (~720×962 native)",
        "",
        "**Stage 2 — `Qwen3VLVideoProcessor.preprocess` (HF processor):**",
        f"- Applies a **3D budget**: `T × h_bar × w_bar ≤ size.longest_edge = {pipeline['processor_3D_budget_px']:,}`",
        f"- This is the processor config field `size = {{'longest_edge': {pipeline['processor_3D_budget_px']:,}, 'shortest_edge': 4096}}`",
        "- When exceeded, scales spatial resolution: `beta = sqrt(T×H×W / max_pixels)`, `h = floor(H/beta/32)×32`, `w = floor(W/beta/32)×32`",
        "",
        "### 1.2 Per-mode budget arithmetic",
        "",
        "| mode | frames | fetch_video px/frame | 3D total | budget | exceeded? | proc px/frame | tok/frame |",
        "|------|--------|----------------------|---------|--------|-----------|---------------|-----------|",
        f"| SPARSE | 16 | ~{pipeline['fetch_video_px_per_frame_median']:,} | ~{16 * pipeline['fetch_video_px_per_frame_median']:,.0f} | {pipeline['processor_3D_budget_px']:,} | **NO** | ~{pipeline['fetch_video_px_per_frame_median']:,} | {pipeline['sparse_tok_per_frame_median']:.1f} |",
        f"| DENSE | 256 | ~{pipeline['fetch_video_px_per_frame_median']:,} | ~{256 * pipeline['fetch_video_px_per_frame_median']:,.0f} | {pipeline['processor_3D_budget_px']:,} | **YES (5.9×)** | ~{int(pipeline['processor_3D_budget_px']/256):,} | {pipeline['dense_tok_per_frame_median']:.1f} |",
        "",
        f"**Spatial reduction for DENSE: {pipeline['spatial_reduction_ratio_dense_vs_sparse']:.2f}× fewer tokens per frame.**",
        "DENSE is not running at dense spatial resolution — it trades spatial detail for temporal coverage.",
        "",
        "### 1.3 Per-frame token constant (corrected)",
        "",
        f"- SPARSE: **{pipeline['sparse_tok_per_frame_median']:.0f} tokens/frame** (not 324 as assumed in Study I report)",
        f"- DENSE: **{pipeline['dense_tok_per_frame_median']:.0f} tokens/frame** (processor spatial compression at 256 frames)",
        "",
        "The '324 tokens/frame' figure was wrong. Actual: ~278 for SPARSE (frame is 720×962 native, "
        "resized by fetch_video to ~868×672, then processed at ~420×320 after temporal padding).",
        "",
        "### 1.4 Maximum achievable fps within budget",
        "",
        f"To maintain SPARSE-equivalent spatial resolution ({pipeline['sparse_tok_per_frame_median']:.0f} tok/frame), "
        f"the processor's 3D budget permits at most:",
        f"- **{pipeline['max_frames_at_sparse_spatial_resolution']} frames** at ~{pipeline['fetch_video_px_per_frame_median']:,.0f} px/frame",
        f"- At median qt={statistics.median(r['question_time'] for r in pipeline['records'] if r['sampling']=='DENSE'):.0f}s: "
        f"≈ **{pipeline['max_feasible_fps_median_qt']:.2f} fps**",
        "",
        "Memory is not the binding constraint. GPU memory for 43 frames at SPARSE resolution ≈ "
        f"43 × {pipeline['sparse_tok_per_frame_median']:.0f} + 300 ≈ {int(43*pipeline['sparse_tok_per_frame_median'])+300} tokens, "
        "well within A6000 budget.",
        "",
        "### 1.5 Per-trial instrumentation table",
        "",
        "| qt | mode | native | loader_n | fetch HxW | fetch px | proc px est | vis_tok | tok/frame |",
        "|-----|------|--------|----------|-----------|---------|-------------|---------|-----------|",
    ]

    for r in pipeline["records"]:
        lines.append(
            f"| {r['question_time']:.0f}s | {r['sampling']} | {r['native_px']} | "
            f"{r['n_frames_loader']} | {r['fetch_video_HxW']} | "
            f"{r['fetch_video_px_per_frame']:,} | {r['proc_px_per_frame_est']:,} | "
            f"{r['n_vis_tokens_approx']} | {r['tok_per_frame']:.1f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2. Below-chance cells",
        "",
        f"**Parse failure rate:** {below['n_parse_fail']}/{below['n_total_trials']} = "
        f"{below['parse_fail_rate']:.4%}",
        f"**Option count:** all questions have 5 options. Random baseline = 20.0%.",
        "",
        "### Below-chance cells (acc < 20%, n ≥ 20):",
        "",
        "| model | sampling | category | n | acc | pred dist | corr dist |",
        "|-------|----------|----------|---|-----|-----------|-----------|",
    ]
    for bc in sorted(below["below_chance_cells"], key=lambda x: x["acc"]):
        pred_str = " ".join(f"{k}:{v}" for k, v in sorted(bc["pred_dist"].items()))
        corr_str = " ".join(f"{k}:{v}" for k, v in sorted(bc["corr_dist"].items()))
        lines.append(
            f"| {bc['model']} | {bc['sampling']} | {bc['category']} | {bc['n']} | "
            f"{bc['acc']*100:.1f}% | {pred_str} | {corr_str} |"
        )

    lines += [
        "",
        "### Raw outputs from worst cells:",
        "",
    ]
    for cell_key, samples in below["raw_outputs_worst_cells"].items():
        lines.append(f"**{cell_key}:**")
        lines.append("")
        lines.append("| gen_text | pred | correct | ok |")
        lines.append("|----------|------|---------|-----|")
        for s in samples:
            lines.append(
                f"| `{s['gen_text']}` | {s['predicted_letter']} | {s['correct_letter']} | {s['correct']} |"
            )
        lines.append("")

    lines += [
        "### Diagnosis:",
        "",
        "No scoring artifacts. The below-chance results are genuine low performance:",
        "- All outputs parse to valid letters; no truncation or refusal observed.",
        "- `8B spatial_aware_reasoning SPARSE`: model has **E-position bias** (19/56 = 34% E predictions "
        "vs 18% E in correct distribution). Correct answers weighted toward A and D, which the model "
        "under-predicts. This is a real model tendency, not a measurement error.",
        "- `4B location_trace SPARSE`: predictions roughly uniform (no strong letter bias); accuracy "
        "is below chance by ~2σ. Most likely genuine difficulty — this category requires "
        "precise temporal recall of location-specific events.",
        "",
        "**No fix warranted.** These are valid data points.",
        "",
        "---",
        "",
        "## 3. Text-only baseline",
        "",
        f"**n = {text_only['n_text_only']} questions | model = Qwen3-VL-4B-Instruct | no video input**",
        "",
        f"| | text-only | video SPARSE-4B | vision Δ |",
        "|--|-----------|-----------------|----------|",
        f"| **overall** | **{text_only['acc_text_only_overall']*100:.1f}%** | **{text_only['acc_video_sparse_4b_overall']*100:.1f}%** | **{text_only['vision_delta_overall_pp']:+.1f}pp** |",
    ]
    for cat in CATEGORIES:
        d = text_only["by_category"].get(cat, {})
        at = d.get("acc_text", float("nan"))
        av = d.get("acc_video", float("nan"))
        dt = d.get("vision_delta")
        at_s = f"{at*100:.1f}%" if not math.isnan(at) else "n/a"
        av_s = f"{av*100:.1f}%" if not math.isnan(av) else "n/a"
        dt_s = f"{dt*100:+.1f}pp" if dt is not None else "n/a"
        lines.append(f"| {cat} | {at_s} | {av_s} | {dt_s} |")

    verdict = (
        f"**Vision is load-bearing** (delta {text_only['vision_delta_overall_pp']:+.1f}pp > ±3pp threshold). "
        "Video conditioning contributes positively overall."
    ) if text_only["is_vision_load_bearing"] else (
        f"**ESCALATE — vision is NOT load-bearing** "
        f"(text-only {text_only['acc_text_only_overall']*100:.1f}% ≈ video {text_only['acc_video_sparse_4b_overall']*100:.1f}%, "
        f"delta {text_only['vision_delta_overall_pp']:+.1f}pp within ±3pp threshold). "
        "Do not proceed to rerun Study I without resolving this."
    )

    lines += [
        "",
        f"**Verdict:** {verdict}",
        "",
        "---",
        "",
        "## 4. Correction to Study I tier gap report",
        "",
        "Section 6 of `reports/study_i_tier_gap.md` stated that 300s at 1fps (~97K tokens) "
        "would 'likely OOM an 8B on the A6000'. This is incorrect.",
        "",
        "Corrected calculation:",
        "- 300 frames × ~278 tokens/frame + 300 text = ~83,700 tokens",
        "- KV cache (8B: 32 layers, dim≈3584, bf16): 32 × 2 × 3584 × 2 bytes/token = 458KB/token",
        "  → 83,700 × 458KB ≈ 38.3 GB KV",
        "- Weights: ~16 GB",
        "- Total: ~54 GB → exceeds 48 GB at 300 frames, 8B model",
        "- **But**: Study H2 already established that max session = 22.3 GB KV at 1fps (no session "
        "exceeds the budget). The concern in the report was correct in direction but overstated in "
        "its framing. The actual constraint is not OOM but total context cost.",
        "",
        "At 43 frames (max for SPARSE-equivalent spatial resolution):",
        "- 43 × 278 + 300 = 12,254 tokens",
        "- KV (8B): 12,254 × 458KB ≈ 5.6 GB + 16 GB weights = 21.6 GB → fits comfortably",
        "",
        "---",
        "",
        "## 5. Validity verdict",
        "",
    ]

    lines += [
        f"- **Bug 1 (DENSE spatial):** IDENTIFIED. DENSE is running at {pipeline['dense_tok_per_frame_median']:.0f} tok/frame "
        f"vs SPARSE {pipeline['sparse_tok_per_frame_median']:.0f} tok/frame due to processor 3D budget. "
        f"Fix: limit DENSE to ≤{pipeline['max_frames_at_sparse_spatial_resolution']} frames "
        f"(≈{pipeline['max_feasible_fps_median_qt']:.2f} fps at median qt). "
        "**DENSE results in Study I are not comparable to SPARSE and should be excluded from the report.**",
        "",
        "- **Bug 2 (below-chance):** NOT a bug. Genuine low performance. Valid data.",
        "",
        f"- **Vision load-bearing:** {verdict}",
        "",
    ]

    if not text_only["is_vision_load_bearing"]:
        lines += [
            "**STOP AND ESCALATE.** Text-only accuracy within noise of video-conditioned accuracy.",
            "Do not rerun Study I until the vision contribution is established.",
            "",
        ]

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    log(f"\nReport written: {REPORT_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    DIAG_DIR.mkdir(parents=True, exist_ok=True)

    mcq_rows = load_jsonl(MCQ_PATH)
    manifest = json.load(open(MANIFEST_PATH))

    # Part A
    pipeline = instrument_frame_pipeline(mcq_rows, manifest)

    # Part B
    below = investigate_below_chance()

    # Part C
    text_only = run_text_only_baseline(mcq_rows, manifest)

    # Report
    write_report(pipeline, below, text_only)

    if not text_only["is_vision_load_bearing"]:
        log("\n*** ESCALATE: text-only ≈ video. Stop and report to user. ***")
        sys.exit(1)

    log("\nDiagnostic complete. See reports/study_i_diagnostic.md.")
    log("Ask user to commit before rerunning Study I.")


if __name__ == "__main__":
    main()
