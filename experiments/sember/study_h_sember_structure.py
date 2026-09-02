"""Study H — S-EMBER Benchmark Structure Analysis.

CPU-only. No model inference. Downloads annotation JSONL files from
HuggingFace (gated; requires approved access) and produces:
  results/sember/study_h/study_h_video_structure.json
  results/sember/study_h/study_h_qa_structure.json
  results/sember/study_h/study_h_evidence_distance.json
  results/sember/study_h/study_h_evidence_distance_hist.csv
  results/sember/study_h/study_h_exclusion.json
  results/sember/study_h/study_h_feasibility.json
  results/sember/study_h/study_h_summary.json

Two escalation conditions are checked and reported:
  E1: HF gated access (403) — annotation files cannot be downloaded.
  E2: No shared session stream — each question gets a fresh forward pass
      over video[0, question_time]; there is no accumulating state.
"""

from __future__ import annotations

import json
import os
import re
import sys
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "results" / "sember" / "study_h"
DATA_DIR = OUT_DIR / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

HF_DATASET = "facebook/S-EMBER"
GROUNDING_FILE = "sember_grounding.jsonl"
MCQ_FILE = "sember_mcq.jsonl"

# ---------------------------------------------------------------------------
# Constants from codebase and paper (for partial offline analysis)
# ---------------------------------------------------------------------------
PAPER_N_VIDEOS = 3141
PAPER_N_QA = 9448
PAPER_HOURS = 388
QUESTION_CATEGORIES = [
    "location_trace",
    "sequential_action",
    "counting_objects_events",
    "visual_detail_recall",
    "temporal_ordering_recognition",
    "time_duration",
    "object_comparison",
    "spatial_aware_reasoning",
]
COUNTING_CATEGORY = "counting_objects_events"

# Qwen3-VL token formula (Study D / Study F): 324 tokens per 560×560 frame.
# Qwen3-VL: patch_size=16, merge_size=2 → 560 → grid 18×18 (rounded) = 324 tokens.
QWEN3VL_TOKENS_PER_FRAME_560 = 324

# Ray-Ban Meta glasses resolution: 1920×1080 (per paper).
# Downscaled to 560 short-side → 560×315 → grid (20×11 = 220 tokens after merge_size=2).
# Conservative: use 560×560 crop estimate = 324 tokens/frame (upper bound).
GLASSES_RESOLUTION = "1920×1080"
TOKENS_PER_FRAME_UPPER = 324  # 560×560 crop upper bound
TOKENS_PER_FRAME_LOWER = 220  # 560×315 portrait lower bound

# A6000 vRAM: 48 GB. Model weights (Qwen3-VL-8B): ~16 GB. Usable for KV+activations: ~32 GB.
A6000_VRAM_GB = 48
QWEN3VL_8B_WEIGHTS_GB = 16
USABLE_VRAM_GB = A6000_VRAM_GB - QWEN3VL_8B_WEIGHTS_GB
# KV bytes per token (Study A/B): 57,344 B/token.
KV_BYTES_PER_TOKEN = 57344


# ---------------------------------------------------------------------------
# Step 1: Download annotations (requires HF approval)
# ---------------------------------------------------------------------------
def download_annotations() -> tuple[Path | None, Path | None]:
    """Attempt to download grounding and mcq JSONL files from HuggingFace.

    Returns (grounding_path, mcq_path). Either may be None if download fails.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed.")
        return None, None

    token_path = Path.home() / ".cache" / "huggingface" / "token"
    token = token_path.read_text().strip() if token_path.exists() else None

    paths = {}
    for fname in [GROUNDING_FILE, MCQ_FILE]:
        local = DATA_DIR / fname
        if local.exists():
            print(f"  Using cached {fname} ({local.stat().st_size/1e6:.1f} MB)")
            paths[fname] = local
            continue
        try:
            path = hf_hub_download(
                repo_id=HF_DATASET,
                filename=fname,
                repo_type="dataset",
                local_dir=str(DATA_DIR),
                token=token,
            )
            print(f"  Downloaded {fname}: {Path(path).stat().st_size/1e6:.1f} MB")
            paths[fname] = Path(path)
        except Exception as e:
            print(f"  BLOCKED: {fname} — {type(e).__name__}: {e}")
            paths[fname] = None

    return paths.get(GROUNDING_FILE), paths.get(MCQ_FILE)


# ---------------------------------------------------------------------------
# Step 2: Video structure from HuggingFace metadata (offline — no annotation needed)
# ---------------------------------------------------------------------------
def analyze_video_structure_offline() -> dict:
    """Parse video durations from HF file metadata (no annotation download required)."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"error": "huggingface_hub not installed"}

    print("  Fetching video file metadata from HuggingFace ...")
    api = HfApi()
    info = api.dataset_info(HF_DATASET, files_metadata=True)
    video_files = [s for s in info.siblings if s.rfilename.startswith("videos/")]

    pattern = re.compile(r"_start_([\d.]+)_end_([\d.]+)\.mp4$")
    durations = []
    sizes_bytes = []
    for s in video_files:
        m = pattern.search(s.rfilename)
        if m:
            start = float(m.group(1))
            end = float(m.group(2))
            durations.append(end - start)
        if s.size is not None:
            sizes_bytes.append(s.size)

    durations.sort()
    sizes_bytes.sort()
    n = len(durations)

    def pct(data, p):
        idx = max(0, min(len(data) - 1, int(len(data) * p / 100)))
        return data[idx]

    total_hours = sum(durations) / 3600

    # Video duration histogram (seconds buckets)
    hist_boundaries = [0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 700, 1300]
    hist = {}
    for i in range(len(hist_boundaries) - 1):
        lo, hi = hist_boundaries[i], hist_boundaries[i + 1]
        cnt = sum(1 for d in durations if lo <= d < hi)
        hist[f"{lo}-{hi}"] = cnt

    return {
        "n_videos": n,
        "paper_n_videos": PAPER_N_VIDEOS,
        "n_matches_paper": n == PAPER_N_VIDEOS,
        "total_hours": round(total_hours, 1),
        "paper_hours": PAPER_HOURS,
        "duration_stats_s": {
            "min": round(min(durations), 1),
            "p10": round(pct(durations, 10), 1),
            "q1": round(pct(durations, 25), 1),
            "median": round(statistics.median(durations), 1),
            "q3": round(pct(durations, 75), 1),
            "p90": round(pct(durations, 90), 1),
            "max": round(max(durations), 1),
            "iqr": round(pct(durations, 75) - pct(durations, 25), 1),
        },
        "duration_histogram_s": hist,
        "total_video_size_gb": round(sum(sizes_bytes) / 1e9, 1),
        "annotation_size_mb": round((11062463 + 10643763) / 1e6, 1),
        "source": "huggingface_metadata_filenames",
    }


# ---------------------------------------------------------------------------
# Step 3: Read and parse annotation files
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def analyze_qa_structure(grounding_rows: list[dict], mcq_rows: list[dict]) -> dict:
    """Distribution of QA pairs per video and question categories."""
    # Count QA per video (use grounding as primary; mcq should be same videos)
    video_qa_count = Counter(r["video_id"] for r in grounding_rows)
    counts = sorted(video_qa_count.values())
    n_videos = len(video_qa_count)

    category_counts = Counter(r.get("question_category", "unknown") for r in grounding_rows)
    category_counts_mcq = Counter(r.get("question_category", "unknown") for r in mcq_rows)

    return {
        "grounding_n_rows": len(grounding_rows),
        "mcq_n_rows": len(mcq_rows),
        "paper_n_qa": PAPER_N_QA,
        "n_videos_in_grounding": n_videos,
        "sanity_qa_count_agrees": len(grounding_rows) == PAPER_N_QA,
        "sanity_video_count_agrees": n_videos == PAPER_N_VIDEOS,
        "qa_per_video": {
            "min": min(counts),
            "median": statistics.median(counts),
            "q3": counts[3 * len(counts) // 4],
            "max": max(counts),
            "n_single_qa": sum(1 for c in counts if c == 1),
            "n_ge5_qa": sum(1 for c in counts if c >= 5),
        },
        "category_counts_grounding": dict(category_counts),
        "category_counts_mcq": dict(category_counts_mcq),
    }


# ---------------------------------------------------------------------------
# Step 4: Evidence distance analysis
# ---------------------------------------------------------------------------
def analyze_evidence_distance(grounding_rows: list[dict]) -> dict:
    """Compute evidence distance = question_time - answer_end_time per QA pair."""
    missing_grounding = 0
    negative_distance = []
    distances = []
    distances_by_cat = defaultdict(list)

    for r in grounding_rows:
        qt = r.get("question_time")
        ast = r.get("answer_start_time")
        aet = r.get("answer_end_time")

        if qt is None or aet is None:
            missing_grounding += 1
            continue

        # Primary: use answer_end_time (nearest end of grounding interval)
        dist = qt - aet
        if dist < 0:
            negative_distance.append({
                "question_id": r.get("question_id"),
                "question_time": qt,
                "answer_end_time": aet,
                "distance": dist,
            })
            # Still include — may represent annotation tolerance
        distances.append(dist)
        cat = r.get("question_category", "unknown")
        distances_by_cat[cat].append(dist)

        # Also check memory_recency field if present (should match)
        mr = r.get("memory_recency")
        if mr is not None:
            computed = round(qt - aet, 3)
            if abs(computed - mr) > 1.0:
                pass  # Flag but don't stop

    def stats(vals):
        if not vals:
            return {}
        s = sorted(vals)
        n = len(s)
        def p(pct): return s[max(0, min(n-1, int(n*pct/100)))]
        return {
            "n": n,
            "min": round(min(s), 1),
            "p10": round(p(10), 1),
            "q1": round(p(25), 1),
            "median": round(statistics.median(s), 1),
            "q3": round(p(75), 1),
            "p90": round(p(90), 1),
            "p99": round(p(99), 1),
            "max": round(max(s), 1),
            "iqr": round(p(75) - p(25), 1),
        }

    by_category = {}
    for cat in QUESTION_CATEGORIES:
        vals = distances_by_cat.get(cat, [])
        by_category[cat] = stats(vals)

    return {
        "overall": stats(distances),
        "by_category": by_category,
        "n_missing_grounding": missing_grounding,
        "n_negative_distance": len(negative_distance),
        "negative_distance_examples": negative_distance[:5],
        "primary_distance_definition": "question_time - answer_end_time (nearest end of grounding interval)",
    }


def make_distance_histogram(distances: list[float]) -> list[dict]:
    """Log-spaced histogram for evidence distance (seconds)."""
    import math
    # Buckets: [0,1), [1,5), [5,15), [15,30), [30,60), [60,120), [120,300), [300+)
    boundaries = [0, 1, 5, 15, 30, 60, 120, 300, float("inf")]
    hist = []
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        cnt = sum(1 for d in distances if lo <= d < hi)
        hist.append({"lo": lo, "hi": hi if hi != float("inf") else None, "count": cnt})
    return hist


# ---------------------------------------------------------------------------
# Step 5: Exclusion check
# ---------------------------------------------------------------------------
def analyze_exclusion(grounding_rows: list[dict]) -> dict:
    """Report counting category fraction and remaining n after exclusion."""
    total = len(grounding_rows)
    counting = [r for r in grounding_rows if r.get("question_category") == COUNTING_CATEGORY]
    remaining = [r for r in grounding_rows if r.get("question_category") != COUNTING_CATEGORY]

    remaining_videos = set(r["video_id"] for r in remaining)
    by_cat = Counter(r.get("question_category", "unknown") for r in remaining)

    return {
        "total_qa": total,
        "counting_n": len(counting),
        "counting_fraction": round(len(counting) / total, 4),
        "remaining_n": len(remaining),
        "remaining_videos": len(remaining_videos),
        "remaining_by_category": dict(by_cat),
    }


# ---------------------------------------------------------------------------
# Step 6: Feasibility arithmetic
# ---------------------------------------------------------------------------
def compute_feasibility(video_stats: dict) -> dict:
    """Estimate vision token count for full video at various sampling rates."""
    # Typical S-EMBER video: median 367s, max 1213s
    # Frame rates: 1fps (typical eval), 2fps, 4fps
    median_dur = video_stats["duration_stats_s"]["median"]
    max_dur = video_stats["duration_stats_s"]["max"]

    results = {}
    for label, duration in [("median_video_367s", median_dur), ("max_video_1213s", max_dur)]:
        for fps in [1, 2, 4]:
            n_frames = int(duration * fps)
            tokens_upper = n_frames * TOKENS_PER_FRAME_UPPER
            tokens_lower = n_frames * TOKENS_PER_FRAME_LOWER
            kv_upper_gb = tokens_upper * KV_BYTES_PER_TOKEN / 1e9
            kv_lower_gb = tokens_lower * KV_BYTES_PER_TOKEN / 1e9
            fits_48gb = kv_upper_gb < USABLE_VRAM_GB
            results[f"{label}_{fps}fps"] = {
                "duration_s": duration,
                "fps": fps,
                "n_frames": n_frames,
                "vision_tokens_upper": tokens_upper,
                "vision_tokens_lower": tokens_lower,
                "kv_bytes_upper_gb": round(kv_upper_gb, 2),
                "kv_bytes_lower_gb": round(kv_lower_gb, 2),
                "fits_48gb_vram": fits_48gb,
            }

    return {
        "model": "Qwen3-VL-8B-Instruct",
        "tokens_per_frame_upper_560x560": TOKENS_PER_FRAME_UPPER,
        "tokens_per_frame_lower_560x315": TOKENS_PER_FRAME_LOWER,
        "kv_bytes_per_token": KV_BYTES_PER_TOKEN,
        "a6000_vram_gb": A6000_VRAM_GB,
        "model_weights_gb": QWEN3VL_8B_WEIGHTS_GB,
        "usable_vram_gb": USABLE_VRAM_GB,
        "scenarios": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Study H — S-EMBER Benchmark Structure")
    print("=" * 60)

    # ── Disk check ──
    import shutil
    disk = shutil.disk_usage("/mnt/ssd")
    print(f"\nDisk /mnt/ssd: {disk.free/1e9:.0f} GB free of {disk.total/1e9:.0f} GB")
    print(f"  Annotation files: ~21.7 MB (safe)")
    print(f"  Video files:      ~396 GB (fits; not needed for this study)")

    # ── Video structure (offline) ──
    print("\n[1] Video structure (from HF filename metadata, no download) ...")
    video_stats = analyze_video_structure_offline()
    (OUT_DIR / "study_h_video_structure.json").write_text(
        json.dumps(video_stats, indent=2)
    )
    print(f"  {video_stats['n_videos']} videos, {video_stats['total_hours']} hours")
    s = video_stats["duration_stats_s"]
    print(f"  Duration: min={s['min']}s, median={s['median']}s, max={s['max']}s, IQR={s['iqr']}s")

    # ── Escalation check E2: session model ──
    print("\n[!] ESCALATION E2: Session model check (from codebase)")
    print("  utils.py sember_doc_to_visual(): returns {video_path, video_end=question_time}")
    print("  qwen3_vl.py: passes video_end to model wrapper → video trimmed to question_time")
    print("  data/README.md: 'GSER: model shown only segment [0, question_time]. Frames after")
    print("    question_time are never sampled.' EACH QUESTION PROCESSED INDEPENDENTLY.")
    print("  VERDICT: NO shared accumulating session stream. STOP CONDITION MET.")

    # ── Annotation download attempt ──
    print("\n[2] Attempting annotation download ...")
    grounding_path, mcq_path = download_annotations()

    if grounding_path is None or mcq_path is None:
        print("\n[!] ESCALATION E1: HF gated access blocked (403). Cannot download annotations.")
        print("    Request access at huggingface.co/datasets/facebook/S-EMBER")
        print("    Annotation-level analyses (B, C, D) require access approval.")
        print("    Proceeding with annotation-independent analyses only (A partial, E).")

        # Feasibility (no annotation needed)
        print("\n[6] Feasibility arithmetic ...")
        feasibility = compute_feasibility(video_stats)
        (OUT_DIR / "study_h_feasibility.json").write_text(
            json.dumps(feasibility, indent=2)
        )
        for k, v in feasibility["scenarios"].items():
            fit = "FITS" if v["fits_48gb_vram"] else "OOM"
            print(f"  {k}: {v['n_frames']} frames, "
                  f"{v['vision_tokens_upper']:,} tokens upper, "
                  f"KV={v['kv_bytes_upper_gb']:.1f} GB → {fit}")

        # Summary
        summary = {
            "escalation_e1_hf_blocked": True,
            "escalation_e2_no_session": True,
            "annotation_analyses_completed": [],
            "offline_analyses_completed": ["video_structure", "feasibility"],
            "verdict": (
                "STOP: Two escalation conditions met. "
                "E1: HF dataset gated (403); request access at huggingface.co/datasets/facebook/S-EMBER. "
                "E2: S-EMBER evaluation protocol does not use a shared accumulating stream. "
                "Each question triggers a fresh model forward pass over video[0, question_time]. "
                "There is no session in the FM-switching sense. "
                "Workload retention decision has nothing to bite on."
            ),
        }
        (OUT_DIR / "study_h_summary.json").write_text(
            json.dumps(summary, indent=2)
        )
        print(f"\nSummary written to {OUT_DIR / 'study_h_summary.json'}")
        return summary

    # ── If annotations are available, run full analysis ──
    print("\n[2b] Loading annotation files ...")
    grounding_rows = load_jsonl(grounding_path)
    mcq_rows = load_jsonl(mcq_path)
    print(f"  Grounding: {len(grounding_rows)} rows")
    print(f"  MCQ: {len(mcq_rows)} rows")

    # ── QA structure ──
    print("\n[3] QA structure ...")
    qa_stats = analyze_qa_structure(grounding_rows, mcq_rows)
    (OUT_DIR / "study_h_qa_structure.json").write_text(
        json.dumps(qa_stats, indent=2)
    )
    sanity1 = "PASS" if qa_stats["sanity_qa_count_agrees"] else "FAIL"
    sanity2 = "PASS" if qa_stats["sanity_video_count_agrees"] else "FAIL"
    print(f"  SC1 (QA count = 9448): {sanity1} (got {qa_stats['grounding_n_rows']})")
    print(f"  SC2 (video count = 3141): {sanity2} (got {qa_stats['n_videos_in_grounding']})")

    # ── Evidence distance ──
    print("\n[4] Evidence distance ...")
    ed = analyze_evidence_distance(grounding_rows)
    hist = make_distance_histogram([
        r["question_time"] - r["answer_end_time"]
        for r in grounding_rows
        if r.get("question_time") is not None and r.get("answer_end_time") is not None
    ])
    ed["histogram"] = hist
    (OUT_DIR / "study_h_evidence_distance.json").write_text(
        json.dumps(ed, indent=2)
    )
    # CSV histogram
    with open(OUT_DIR / "study_h_evidence_distance_hist.csv", "w") as f:
        f.write("lo_s,hi_s,count\n")
        for row in hist:
            f.write(f"{row['lo']},{row['hi']},{row['count']}\n")

    o = ed["overall"]
    print(f"  Overall: n={o['n']}, median={o['median']}s, IQR={o['iqr']}s, "
          f"p90={o['p90']}s, p99={o['p99']}s")
    print(f"  Missing grounding: {ed['n_missing_grounding']}")
    print(f"  Negative distances: {ed['n_negative_distance']}")

    sanity3 = "PASS" if ed["n_missing_grounding"] == 0 else "FAIL"
    sanity4 = "PASS" if ed["n_negative_distance"] == 0 else f"FAIL ({ed['n_negative_distance']} negative)"
    print(f"  SC3 (all have grounding): {sanity3}")
    print(f"  SC4 (all non-negative distance): {sanity4}")

    print("\n  Evidence distance by category:")
    for cat in QUESTION_CATEGORIES:
        s = ed["by_category"].get(cat, {})
        if s:
            print(f"    {cat[:30]:30s}: median={s['median']:6.1f}s, IQR={s['iqr']:5.1f}s, n={s['n']}")

    # Check if task types differ
    medians = {cat: ed["by_category"][cat]["median"] for cat in QUESTION_CATEGORIES
               if cat in ed["by_category"] and ed["by_category"][cat]}
    if medians:
        med_range = max(medians.values()) - min(medians.values())
        print(f"\n  Evidence distance range across categories: {med_range:.1f}s "
              f"({'wide' if med_range > 60 else 'narrow'})")

    # ── Exclusion ──
    print("\n[5] Exclusion (counting category) ...")
    excl = analyze_exclusion(grounding_rows)
    (OUT_DIR / "study_h_exclusion.json").write_text(
        json.dumps(excl, indent=2)
    )
    print(f"  counting_objects_events: n={excl['counting_n']}, "
          f"fraction={excl['counting_fraction']:.3f}")
    print(f"  Remaining after exclusion: n={excl['remaining_n']} "
          f"over {excl['remaining_videos']} videos")

    # ── Feasibility ──
    print("\n[6] Feasibility arithmetic ...")
    feasibility = compute_feasibility(video_stats)
    (OUT_DIR / "study_h_feasibility.json").write_text(
        json.dumps(feasibility, indent=2)
    )
    for k, v in feasibility["scenarios"].items():
        fit = "FITS" if v["fits_48gb_vram"] else "OOM"
        print(f"  {k}: {v['n_frames']} frames, "
              f"{v['vision_tokens_upper']:,} tokens upper, "
              f"KV={v['kv_bytes_upper_gb']:.1f} GB → {fit}")

    # ── Summary ──
    dist_wide = o.get("iqr", 0) > 60 or o.get("p90", 0) > 120
    summary = {
        "escalation_e1_hf_blocked": False,
        "escalation_e2_no_session": True,  # Always True from codebase
        "annotation_analyses_completed": ["qa_structure", "evidence_distance", "exclusion"],
        "offline_analyses_completed": ["video_structure", "feasibility"],
        "verdict": (
            "STOP (E2): S-EMBER does not use a shared accumulating stream. "
            "Each question triggers a fresh forward pass over video[0, question_time]. "
            "The workload retention decision has nothing to bite on."
        ),
        "plain_answers": {
            "shared_stream": "NO. Each question is a fresh forward pass over video[0, question_time]. GSER protocol; no accumulating session.",
            "evidence_distance_wide": (
                f"{'WIDE' if dist_wide else 'NARROW'}: median={o.get('median')}s, "
                f"IQR={o.get('iqr')}s, p90={o.get('p90')}s, p99={o.get('p99')}s."
            ),
            "task_types_differ": f"Median range across categories: {med_range:.1f}s.",
            "after_exclusion": f"n={excl['remaining_n']} QA pairs over {excl['remaining_videos']} videos.",
        },
        "sanity_checks": {
            "SC1_qa_count": sanity1,
            "SC2_video_count": sanity2,
            "SC3_all_have_grounding": sanity3,
            "SC4_no_negative_distance": sanity4,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    (OUT_DIR / "study_h_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(f"\nDone. All outputs written to {OUT_DIR}")
    return summary


if __name__ == "__main__":
    result = main()
    print("\n=== SUMMARY ===")
    print(json.dumps(result, indent=2))
