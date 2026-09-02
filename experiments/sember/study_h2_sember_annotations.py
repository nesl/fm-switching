"""Study H2 — S-EMBER Annotation-Level Analysis.

CPU only. No model inference. Reads:
  results/sember/study_h/data/sember_grounding.jsonl
  results/sember/study_h/data/sember_mcq.jsonl

Writes:
  results/sember/study_h2/study_h2_session_structure.json
  results/sember/study_h2/study_h2_evidence_distance.json
  results/sember/study_h2/study_h2_evidence_distance_hist.csv
  results/sember/study_h2/study_h2_exclusion.json
  results/sember/study_h2/study_h2_session_feasibility.json
  results/sember/study_h2/study_h2_summary.json
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "results" / "sember" / "study_h" / "data"
OUT_DIR = REPO_ROOT / "results" / "sember" / "study_h2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GROUNDING_PATH = DATA_DIR / "sember_grounding.jsonl"
MCQ_PATH = DATA_DIR / "sember_mcq.jsonl"

PAPER_N_QA = 9448
PAPER_N_VIDEOS = 3141
COUNTING_CATEGORY = "counting_objects_events"
QUESTION_CATEGORIES = [
    "location_trace", "sequential_action", "counting_objects_events",
    "visual_detail_recall", "temporal_ordering_recognition", "time_duration",
    "object_comparison", "spatial_aware_reasoning",
]

# Token / memory constants from Study D and Study A/B
TOKENS_PER_FRAME = 324       # Qwen3-VL, 560×560, Study D
KV_BYTES_PER_TOKEN = 57344   # Study A/B, content-independent
A6000_TOTAL_GB = 48
MODEL_WEIGHTS_GB = 16        # Qwen3-VL-8B-Instruct
USABLE_VRAM_GB = A6000_TOTAL_GB - MODEL_WEIGHTS_GB   # 32 GB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def quantiles(data: list[float], qs=(0.10, 0.25, 0.50, 0.75, 0.90, 0.99)) -> dict:
    if not data:
        return {}
    s = sorted(data)
    n = len(s)
    result = {}
    for q in qs:
        idx = max(0, min(n - 1, int(n * q)))
        result[f"p{int(q*100)}"] = s[idx]
    result["min"] = s[0]
    result["max"] = s[-1]
    result["median"] = statistics.median(s)
    result["mean"] = statistics.mean(s)
    result["iqr"] = result["p75"] - result["p25"]
    result["n"] = n
    return {k: round(v, 3) for k, v in result.items()}


def log_hist(values: list[float]) -> list[dict]:
    """Log-spaced histogram: [0,1), [1,5), [5,15), [15,30), [30,60), [60,120), [120,300), [300+)."""
    boundaries = [0, 1, 5, 15, 30, 60, 120, 300, float("inf")]
    hist = []
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        cnt = sum(1 for v in values if lo <= v < hi)
        hist.append({"lo": lo, "hi": None if hi == float("inf") else hi, "count": cnt,
                     "pct": round(100 * cnt / len(values), 2) if values else 0})
    return hist


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
def run_sanity_checks(grounding: list[dict], mcq: list[dict]) -> dict:
    results = {}

    # SC1: QA count matches paper
    results["SC1_qa_count"] = {
        "expected": PAPER_N_QA,
        "grounding": len(grounding),
        "mcq": len(mcq),
        "pass": len(grounding) == PAPER_N_QA,
    }

    # SC2: Every grounding pair has valid temporal fields
    missing = []
    invalid_order = []  # answer_start > answer_end or answer_end > question_time
    negative_nearest = []
    negative_farthest = []
    mr_mismatch = []

    for i, r in enumerate(grounding):
        qt = r.get("question_time")
        ast = r.get("answer_start_time")
        aet = r.get("answer_end_time")
        mr = r.get("memory_recency")
        qid = r.get("question_id", f"row_{i}")

        if qt is None or ast is None or aet is None:
            missing.append(qid)
            continue

        qt, ast, aet = float(qt), float(ast), float(aet)

        # Order check: answer_start <= answer_end <= question_time
        if ast > aet:
            invalid_order.append({"qid": qid, "issue": "start>end", "ast": ast, "aet": aet})
        if aet > qt:
            invalid_order.append({"qid": qid, "issue": "end>qt", "aet": aet, "qt": qt})

        # Evidence distance signs
        nearest = qt - aet
        farthest = qt - ast
        if nearest < 0:
            negative_nearest.append({"qid": qid, "nearest": round(nearest, 3)})
        if farthest < 0:
            negative_farthest.append({"qid": qid, "farthest": round(farthest, 3)})

        # memory_recency verification: should equal qt - ast (farthest)
        if mr is not None:
            computed = round(qt - ast, 3)
            if abs(computed - round(float(mr), 3)) > 1.0:
                mr_mismatch.append({
                    "qid": qid, "mr_field": mr,
                    "computed_qt_minus_ast": computed,
                    "diff": round(abs(computed - float(mr)), 3)
                })

    results["SC2_valid_grounding"] = {
        "n_missing_temporal": len(missing),
        "missing_examples": missing[:5],
        "pass": len(missing) == 0,
    }
    # Characterize violations: all 1.0s violations with integer question_time
    # are a known annotation artifact (qt stored as floor-int, aet extends 1s past).
    all_exactly_one = all(
        abs(v.get("aet", 0) - v.get("qt", 0) - 1.0) < 0.01
        for v in invalid_order if "aet" in v and "qt" in v
    )
    results["SC3_temporal_order"] = {
        "n_violations": len(invalid_order),
        "examples": invalid_order[:5],
        "all_violations_are_1s_artifact": all_exactly_one,
        "pass": len(invalid_order) == 0,
        "action": (
            "10 records excluded from evidence distance (aet = floor(qt)+1 rounding artifact). "
            "Included in session structure. Not a causal-protocol violation."
            if all_exactly_one else "UNKNOWN — investigate before proceeding"
        ),
    }
    results["SC4_no_negative_nearest"] = {
        "n_negative": len(negative_nearest),
        "examples": negative_nearest[:5],
        "all_are_minus_one": all(abs(v.get("nearest", 0) + 1.0) < 0.01 for v in negative_nearest),
        "pass": len(negative_nearest) == 0,
        "action": "Same 10 artifact records as SC3; excluded from evidence distance analysis.",
    }
    results["SC4b_no_negative_farthest"] = {
        "n_negative": len(negative_farthest),
        "examples": negative_farthest[:5],
        "pass": len(negative_farthest) == 0,
    }
    results["SC5_memory_recency_matches_qt_minus_ast"] = {
        "n_mismatches": len(mr_mismatch),
        "examples": mr_mismatch[:5],
        "pass": len(mr_mismatch) == 0,
        "note": "memory_recency should equal question_time - answer_start_time (farthest distance)",
    }

    all_pass = all(v.get("pass", False) for v in results.values() if isinstance(v, dict))
    results["all_pass"] = all_pass
    return results


# ---------------------------------------------------------------------------
# Analysis 1: Session structure — does a growing prefix exist?
# ---------------------------------------------------------------------------
def analyze_session_structure(grounding: list[dict]) -> dict:
    # Group by video_id
    by_video: dict[str, list[float]] = defaultdict(list)
    for r in grounding:
        vid = r["video_id"]
        qt = r.get("question_time")
        if qt is not None:
            by_video[vid].append(float(qt))

    n_videos = len(by_video)

    # QA per video distribution
    qa_counts = sorted(len(v) for v in by_video.values())
    qa_dist = Counter(qa_counts)
    n_single = qa_dist[1]
    n_multi = n_videos - n_single

    # Among multi-question videos: are question_times distinct?
    n_all_same = 0       # all question_times identical
    n_near_same = 0      # spread < 10s (near-identical)
    spreads = []         # max - min question_time across questions
    spread_fracs = []    # spread / video duration (where available)

    duration_by_vid = {}
    for r in grounding:
        vid = r["video_id"]
        dur = r.get("duration")
        if dur is not None and vid not in duration_by_vid:
            duration_by_vid[vid] = float(dur)

    for vid, times in by_video.items():
        if len(times) < 2:
            continue
        spread = max(times) - min(times)
        spreads.append(spread)
        if spread == 0:
            n_all_same += 1
        if spread < 10:
            n_near_same += 1
        dur = duration_by_vid.get(vid)
        if dur and dur > 0:
            spread_fracs.append(spread / dur)

    # Per-video distinct qt counts
    n_distinct_dist = Counter(len(set(times)) for times in by_video.values())

    return {
        "n_videos_total": n_videos,
        "n_videos_single_question": n_single,
        "n_videos_multi_question": n_multi,
        "qa_per_video_distribution": {str(k): v for k, v in sorted(qa_dist.items())},
        "qa_per_video_stats": quantiles(qa_counts),
        "multi_question_videos": {
            "n": n_multi,
            "n_all_same_qt": n_all_same,
            "n_near_same_qt_lt10s": n_near_same,
            "frac_all_same": round(n_all_same / n_multi, 4) if n_multi else None,
            "frac_near_same": round(n_near_same / n_multi, 4) if n_multi else None,
            "spread_stats_s": quantiles(spreads) if spreads else {},
            "spread_frac_of_duration_stats": quantiles(spread_fracs) if spread_fracs else {},
        },
        "distinct_qt_per_video_distribution": {str(k): v for k, v in sorted(n_distinct_dist.items())},
    }


# ---------------------------------------------------------------------------
# Analysis 2: Evidence distance
# ---------------------------------------------------------------------------
def analyze_evidence_distance(grounding: list[dict]) -> dict:
    nearest_all = []
    farthest_all = []
    nearest_by_cat: dict[str, list[float]] = defaultdict(list)
    farthest_by_cat: dict[str, list[float]] = defaultdict(list)
    frac_nearest: list[float] = []   # nearest / question_time
    n_excluded_artifact = 0

    for r in grounding:
        qt = r.get("question_time")
        ast = r.get("answer_start_time")
        aet = r.get("answer_end_time")
        if qt is None or ast is None or aet is None:
            continue
        qt, ast, aet = float(qt), float(ast), float(aet)
        if qt <= 0:
            continue
        # Exclude the 10 known 1s-artifact records (aet > qt by exactly 1s)
        if aet > qt:
            n_excluded_artifact += 1
            continue
        cat = r.get("question_category", "unknown")
        nearest = qt - aet
        farthest = qt - ast
        nearest_all.append(nearest)
        farthest_all.append(farthest)
        nearest_by_cat[cat].append(nearest)
        farthest_by_cat[cat].append(farthest)
        frac_nearest.append(nearest / qt)

    by_cat = {}
    for cat in QUESTION_CATEGORIES:
        nv = nearest_by_cat.get(cat, [])
        fv = farthest_by_cat.get(cat, [])
        by_cat[cat] = {
            "nearest": quantiles(nv) if nv else {},
            "farthest": quantiles(fv) if fv else {},
        }

    # For verdict on category differences: collect median nearest per category
    cat_medians = {}
    for cat in QUESTION_CATEGORIES:
        nv = nearest_by_cat.get(cat, [])
        if nv:
            cat_medians[cat] = round(statistics.median(nv), 1)

    med_range = max(cat_medians.values()) - min(cat_medians.values()) if cat_medians else 0

    return {
        "overall_nearest": quantiles(nearest_all),
        "overall_farthest": quantiles(farthest_all),
        "nearest_frac_of_qt": quantiles(frac_nearest),
        "by_category": by_cat,
        "category_median_nearest_s": cat_medians,
        "category_median_range_s": round(med_range, 1),
        "histogram_nearest": log_hist(nearest_all),
        "histogram_farthest": log_hist(farthest_all),
        "n_excluded_artifact": n_excluded_artifact,
        "definition": {
            "nearest": "question_time - answer_end_time",
            "farthest": "question_time - answer_start_time (= precomputed memory_recency field)",
        },
    }


# ---------------------------------------------------------------------------
# Analysis 3: Exclusion
# ---------------------------------------------------------------------------
def analyze_exclusion(grounding: list[dict]) -> dict:
    total = len(grounding)
    counting = [r for r in grounding if r.get("question_category") == COUNTING_CATEGORY]
    remaining = [r for r in grounding if r.get("question_category") != COUNTING_CATEGORY]

    remaining_videos = set(r["video_id"] for r in remaining)
    by_cat = Counter(r.get("question_category", "unknown") for r in remaining)

    # Multi-question videos in remaining
    by_vid: dict[str, list] = defaultdict(list)
    for r in remaining:
        by_vid[r["video_id"]].append(r)
    multi_remaining = {vid: rows for vid, rows in by_vid.items() if len(rows) > 1}

    qa_per_vid = sorted(len(v) for v in by_vid.values())

    return {
        "total_qa": total,
        "counting_n": len(counting),
        "counting_frac": round(len(counting) / total, 4),
        "remaining_qa": len(remaining),
        "remaining_videos": len(remaining_videos),
        "remaining_multi_question_videos": len(multi_remaining),
        "remaining_by_category": dict(by_cat),
        "qa_per_video_stats_after_exclusion": quantiles(qa_per_vid),
    }


# ---------------------------------------------------------------------------
# Analysis 4: Session construction feasibility
# ---------------------------------------------------------------------------
def analyze_session_feasibility(grounding: list[dict], session_info: dict) -> dict:
    """For multi-question videos, compute per-question prefix growth and token accumulation."""

    duration_by_vid = {}
    for r in grounding:
        vid = r["video_id"]
        dur = r.get("duration")
        if dur is not None:
            duration_by_vid[vid] = float(dur)

    # Group by video, sorted by question_time
    by_video: dict[str, list[dict]] = defaultdict(list)
    for r in grounding:
        by_video[r["video_id"]].append(r)

    multi_videos = {vid: sorted(rows, key=lambda x: float(x.get("question_time", 0)))
                    for vid, rows in by_video.items() if len(rows) > 1}

    # For each multi-question video, compute per-question cumulative tokens and KV
    exceed_32gb = 0     # videos where final question exceeds 32 GB KV
    all_prefix_growths = []    # seconds added per successive question
    all_frame_growths = []     # frames added per successive question
    final_kv_gb = []           # KV GB at the LAST question of each video

    # Aggregate: cumulative frames at each question index (1-indexed), across all videos
    cumulative_frames_by_q_idx: dict[int, list[int]] = defaultdict(list)

    for vid, rows in multi_videos.items():
        prev_qt = 0.0
        for i, r in enumerate(rows):
            qt = float(r.get("question_time", 0))
            added_s = max(0.0, qt - prev_qt)
            added_frames = int(added_s)   # 1 fps: 1 frame per second
            all_prefix_growths.append(added_s)
            all_frame_growths.append(added_frames)
            cumulative_frames = int(qt)    # 1 fps from t=0
            cumulative_frames_by_q_idx[i + 1].append(cumulative_frames)
            prev_qt = qt

        # Final question KV
        final_qt = float(rows[-1].get("question_time", 0))
        final_frames = int(final_qt)
        total_tokens = final_frames * TOKENS_PER_FRAME
        kv_gb = total_tokens * KV_BYTES_PER_TOKEN / 1e9
        final_kv_gb.append(kv_gb)
        if kv_gb > USABLE_VRAM_GB:
            exceed_32gb += 1

    # Summarize per-q-index cumulative frames
    cumul_by_idx = {}
    for idx in sorted(cumulative_frames_by_q_idx.keys()):
        frames = cumulative_frames_by_q_idx[idx]
        kv_vals = [f * TOKENS_PER_FRAME * KV_BYTES_PER_TOKEN / 1e9 for f in frames]
        cumul_by_idx[str(idx)] = {
            "n_videos": len(frames),
            "median_cumulative_frames": int(statistics.median(frames)),
            "median_kv_gb": round(statistics.median(kv_vals), 2),
            "p90_kv_gb": round(kv_vals[int(len(kv_vals) * 0.9)], 2) if kv_vals else 0,
        }

    return {
        "fps": 1,
        "tokens_per_frame": TOKENS_PER_FRAME,
        "kv_bytes_per_token": KV_BYTES_PER_TOKEN,
        "usable_vram_gb": USABLE_VRAM_GB,
        "n_multi_question_videos": len(multi_videos),
        "per_question_prefix_growth_s": quantiles(all_prefix_growths),
        "per_question_frame_growth": quantiles(all_frame_growths),
        "final_question_kv_gb": quantiles(final_kv_gb),
        "n_exceed_32gb_at_final_question": exceed_32gb,
        "frac_exceed_32gb": round(exceed_32gb / len(multi_videos), 4) if multi_videos else None,
        "cumulative_by_question_index": cumul_by_idx,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Study H2 — S-EMBER Annotation Analysis")
    print("=" * 60)

    assert GROUNDING_PATH.exists(), f"Missing: {GROUNDING_PATH}"
    assert MCQ_PATH.exists(), f"Missing: {MCQ_PATH}"

    print("\nLoading annotations ...")
    grounding = load_jsonl(GROUNDING_PATH)
    mcq = load_jsonl(MCQ_PATH)
    print(f"  Grounding: {len(grounding)} rows")
    print(f"  MCQ:       {len(mcq)} rows")

    # ── Sanity checks ──────────────────────────────────────────────────────
    print("\n[Sanity checks]")
    sc = run_sanity_checks(grounding, mcq)
    (OUT_DIR / "study_h2_sanity.json").write_text(json.dumps(sc, indent=2))
    for name, res in sc.items():
        if isinstance(res, dict):
            status = "PASS" if res.get("pass") else "FAIL"
            print(f"  {name}: {status}")
            if not res.get("pass") and res.get("examples"):
                print(f"    examples: {res['examples'][:2]}")
    if not sc["all_pass"]:
        # Check if all failures are the known 1s artifact — continue if so
        sc3 = sc.get("SC3_temporal_order", {})
        sc4 = sc.get("SC4_no_negative_nearest", {})
        artifact_only = (
            sc3.get("all_violations_are_1s_artifact", False) and
            sc4.get("all_are_minus_one", False) and
            sc3.get("n_violations", 0) <= 15 and
            sc4.get("n_negative", 0) <= 15 and
            sc["SC2_valid_grounding"].get("pass") and
            sc["SC4b_no_negative_farthest"].get("pass") and
            sc["SC5_memory_recency_matches_qt_minus_ast"].get("pass")
        )
        if not artifact_only:
            print("\nSTOP: unexpected sanity check failures. Check study_h2_sanity.json.")
            return
        print(f"\n  SC3/SC4 failures are the known 1s annotation artifact "
              f"({sc3['n_violations']} records). Excluding from evidence distance; continuing.")

    # ── Analysis 1: session structure ──────────────────────────────────────
    print("\n[Analysis 1] Session structure ...")
    sess = analyze_session_structure(grounding)
    (OUT_DIR / "study_h2_session_structure.json").write_text(json.dumps(sess, indent=2))

    n_multi = sess["n_videos_multi_question"]
    n_all_same = sess["multi_question_videos"]["n_all_same_qt"]
    frac_same = sess["multi_question_videos"]["frac_all_same"]
    spread = sess["multi_question_videos"]["spread_stats_s"]

    print(f"  Videos: {sess['n_videos_total']} total, {sess['n_videos_single_question']} single-Q, {n_multi} multi-Q")
    print(f"  QA/video distribution: {dict(list(sorted(Counter({int(k): v for k, v in sess['qa_per_video_distribution'].items()}).items()))[:8])}")
    print(f"  Multi-Q: {n_all_same}/{n_multi} have identical question_time (frac={frac_same})")
    if spread:
        print(f"  Question_time spread among multi-Q: median={spread.get('median')}s, "
              f"IQR={spread.get('iqr')}s, p90={spread.get('p90')}s, max={spread.get('max')}s")

    # Verdict
    if frac_same is not None and frac_same > 0.9:
        verdict = ("REJECT: Questions within a video fire at near-identical timestamps. "
                   "No growing prefix. E2 rejection stands.")
    elif frac_same is not None and frac_same < 0.1:
        verdict = ("ACCEPT: Questions within a video fire at distinct, spread timestamps. "
                   "A growing prefix exists. A session can be constructed.")
    else:
        verdict = (f"MIXED: {frac_same:.1%} of multi-Q videos have identical timestamps; "
                   f"the remainder have distinct question_times. Further sub-analysis needed.")
    print(f"\n  VERDICT: {verdict}")

    # ── Analysis 2: evidence distance ──────────────────────────────────────
    print("\n[Analysis 2] Evidence distance ...")
    ed = analyze_evidence_distance(grounding)
    (OUT_DIR / "study_h2_evidence_distance.json").write_text(json.dumps(ed, indent=2))

    # Write histogram CSV
    with open(OUT_DIR / "study_h2_evidence_distance_hist.csv", "w") as f:
        f.write("lo_s,hi_s,count,pct,distance_type\n")
        for row in ed["histogram_nearest"]:
            f.write(f"{row['lo']},{row['hi']},{row['count']},{row['pct']},nearest\n")
        for row in ed["histogram_farthest"]:
            f.write(f"{row['lo']},{row['hi']},{row['count']},{row['pct']},farthest\n")

    o = ed["overall_nearest"]
    print(f"  Nearest (qt - end): n={o['n']}, median={o['median']}s, IQR={o['iqr']}s, "
          f"p90={o['p90']}s, p99={o['p99']}s, max={o['max']}s")
    f_o = ed["overall_farthest"]
    print(f"  Farthest (qt - start): median={f_o['median']}s, IQR={f_o['iqr']}s, "
          f"p90={f_o['p90']}s, p99={f_o['p99']}s")

    print("\n  Nearest distance histogram:")
    for row in ed["histogram_nearest"]:
        lo = row['lo']; hi = row['hi'] if row['hi'] else '∞'
        print(f"    [{lo:5}, {hi:5}): {row['count']:5d}  ({row['pct']:.1f}%)")

    print(f"\n  Category medians (nearest, s): range = {ed['category_median_range_s']}s")
    for cat, med in sorted(ed["category_median_nearest_s"].items(), key=lambda x: -x[1]):
        print(f"    {cat:35s}: {med}s")

    # ── Analysis 3: exclusion ──────────────────────────────────────────────
    print("\n[Analysis 3] Exclusion ...")
    excl = analyze_exclusion(grounding)
    (OUT_DIR / "study_h2_exclusion.json").write_text(json.dumps(excl, indent=2))
    print(f"  counting_objects_events: n={excl['counting_n']}, frac={excl['counting_frac']:.3f}")
    print(f"  Remaining: {excl['remaining_qa']} QA / {excl['remaining_videos']} videos / "
          f"{excl['remaining_multi_question_videos']} multi-Q videos")
    print(f"  By category: {excl['remaining_by_category']}")

    # ── Analysis 4: session feasibility ───────────────────────────────────
    print("\n[Analysis 4] Session construction feasibility (1 fps) ...")
    feas = analyze_session_feasibility(grounding, sess)
    (OUT_DIR / "study_h2_session_feasibility.json").write_text(json.dumps(feas, indent=2))

    kv = feas["final_question_kv_gb"]
    print(f"  Multi-Q videos: {feas['n_multi_question_videos']}")
    print(f"  Final-question KV: median={kv.get('median')}GB, p90={kv.get('p90')}GB, "
          f"max={kv.get('max')}GB")
    print(f"  Exceed 32 GB at final Q: {feas['n_exceed_32gb_at_final_question']} "
          f"({feas['frac_exceed_32gb']:.1%})")

    print("\n  Cumulative KV by question index (1 fps, across all multi-Q videos):")
    for idx, v in sorted(feas["cumulative_by_question_index"].items(), key=lambda x: int(x[0]))[:8]:
        print(f"    Q{idx}: n={v['n_videos']}, "
              f"median {v['median_cumulative_frames']} frames → "
              f"median {v['median_kv_gb']} GB KV (p90={v['p90_kv_gb']} GB)")

    # ── Summary ────────────────────────────────────────────────────────────
    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_verdict": verdict,
        "sanity_all_pass": sc["all_pass"],
        "n_videos": sess["n_videos_total"],
        "n_multi_q_videos": n_multi,
        "frac_multi_q_with_same_qt": frac_same,
        "qt_spread_median_s": spread.get("median") if spread else None,
        "qt_spread_p90_s": spread.get("p90") if spread else None,
        "evidence_distance_nearest_median_s": o["median"],
        "evidence_distance_nearest_iqr_s": o["iqr"],
        "evidence_distance_nearest_p90_s": o["p90"],
        "category_median_range_s": ed["category_median_range_s"],
        "counting_excluded_n": excl["counting_n"],
        "remaining_qa": excl["remaining_qa"],
        "remaining_videos": excl["remaining_videos"],
        "remaining_multi_q_videos": excl["remaining_multi_question_videos"],
        "session_feasibility_exceed_32gb_frac": feas["frac_exceed_32gb"],
        "session_feasibility_kv_median_gb": kv.get("median"),
    }
    (OUT_DIR / "study_h2_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nAll outputs written to {OUT_DIR}")
    print("\nFINAL VERDICT:", verdict)
    return summary


if __name__ == "__main__":
    main()
