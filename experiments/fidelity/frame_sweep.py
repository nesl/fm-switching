"""
Experiment 8: Frame-count sweep on EgoSchema (accuracy vs. inertia vs. frames)
===============================================================================
Characterises how many sampled frames are needed to achieve a given accuracy
gain, and at what prefill-cost. Runs on the first 150 clips (the known-good
range from exp7 — avoids clip-256 crash; resumable via caption checkpoint).

Strategy (one captioning pass, multiple scoring passes):
  1. Caption each clip at FRAMES_MAX=32 frames, persisted to a dedicated cache.
  2. Derive lower counts {4, 8, 16} as evenly-spaced nested subsets of the 32
     captions — no re-captioning. Every frame count shares the same underlying
     captions, so accuracy differences are purely due to context size, not
     caption content.
  3. Score the 6 exp7 conditions for each frame count. Primary metrics:
       full-context accuracy, prefill ms, prompt tokens.
     Also report stateless as the floor.
  4. Window sizes that exceed N (e.g. window-10 at N=4) are automatically
     capped by Python slice semantics; the output notes the effective cap.

Subsampling: given 32 captions [c_0 … c_31], derive N by taking every
(32/N)-th entry: N=16 → stride 2 → [c_0, c_2, …, c_30]; N=8 → stride 4;
N=4 → stride 8 → [c_0, c_8, c_16, c_24].

Reuse contract: imports exp7 helpers (load_egoschema, build_egoschema_prompt,
parse_choice, compute_verdict, CONDITIONS, LETTERS, SHUFFLE_SEED) and exp5
helpers (load_vlm, run_vlm, load_llm, run_llm_two_call) — never mutates them.

  Caption run (A6000, ~2 hrs, resumable):
    python experiments/exp8_frame_sweep.py --limit 150 --caption-only

  Scoring run (fast, CPU-free-able after captions exist):
    python experiments/exp8_frame_sweep.py --limit 150 --skip-captioning

  Full pipeline (caption + score):
    python experiments/exp8_frame_sweep.py --limit 150

  Dry-run (no GPU, no data):
    python experiments/exp8_frame_sweep.py --dry-run --limit 8
"""

import argparse
import gc
import json
import random
import re
from datetime import datetime
from pathlib import Path

# ── Reuse exp7 constants and pure helpers ───────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from premise_egoschema import (
    CONDITIONS, LETTERS, SHUFFLE_SEED,
    MATERIALLY_BEATS_PP, NON_LEAKY_PP, LEAKY_PP, CONFOUNDED_PP,
    load_egoschema, build_egoschema_prompt, parse_choice,
    compute_verdict, summarize, shuffled_captions,
    _load_caption_cache, _save_caption_cache, sample_frames,
)

FRAMES_MAX_DEFAULT = 32
FRAME_COUNTS_DEFAULT = [4, 8, 16, 32]


# ── Subsampling ─────────────────────────────────────────────────────────

def subsample_captions(caps_32: list, n: int) -> list:
    """Return n evenly-spaced captions from the 32-frame list.

    Stride = len(caps_32) // n so {4,8,16,32} are all exact divisors of 32.
    Falls back to the full list if n >= len(caps_32).
    """
    total = len(caps_32)
    if n >= total:
        return list(caps_32)
    stride = total // n
    return [caps_32[i] for i in range(0, total, stride)][:n]


# ── Phase 1: VLM captioning at FRAMES_MAX ───────────────────────────────

def caption_questions_32(questions, videos_dir: Path, vlm_id, quantization,
                         max_pixels, vlm_max_tokens, captions_path: Path,
                         frames_max: int = FRAMES_MAX_DEFAULT):
    """Caption each clip at frames_max frames; checkpoint after every clip."""
    import torch
    from context_inertia import load_vlm, run_vlm

    captions = _load_caption_cache(captions_path)
    todo = [q for q in questions if q["q_uid"] not in captions]
    if captions:
        print(f"\nCaption cache ({frames_max}-frame): {len(captions)} done, "
              f"{len(todo)} remaining.")
    if not todo:
        print("  All clips already captioned — skipping VLM load.")
        return captions

    print(f"\nLoading VLM for {frames_max}-frame captioning...")
    vlm, vlm_proc = load_vlm(vlm_id, quantization, max_pixels)
    for qi, q in enumerate(todo):
        vpath = videos_dir / f"{q['q_uid']}.mp4"
        if not vpath.exists():
            alt = next((p for p in videos_dir.glob(f"{q['q_uid']}.*")), None)
            vpath = alt if alt else vpath
        try:
            frames = sample_frames(vpath, frames_max)
        except Exception as ex:
            print(f"  [{qi+1}/{len(todo)}] {q['q_uid']}: frame error: {ex}")
            captions[q["q_uid"]] = []
            _save_caption_cache(captions_path, captions)
            continue
        caps = []
        for img in frames:
            try:
                text, _lat = run_vlm(vlm, vlm_proc, img, vlm_id, vlm_max_tokens)
                caps.append(text)
            except Exception as ex:
                print(f"    VLM frame error (skipped): {ex}")
        captions[q["q_uid"]] = caps
        _save_caption_cache(captions_path, captions)
        print(f"  [{qi+1}/{len(todo)}] {q['q_uid']}: {len(caps)} captions")

    del vlm, vlm_proc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return captions


# ── Phase 2: reasoning sweep over frame counts ──────────────────────────

def reason_frame_sweep(questions, captions_32, llm_id, quantization,
                       llm_max_tokens, frame_counts, save_cb=None):
    """For each frame count in frame_counts, score all 6 conditions.

    Returns dict: {n_frames: per_question_list}.
    """
    from context_inertia import load_llm, run_llm_two_call

    print("\nLoading LLM (reasoner)...")
    llm, llm_tok = load_llm(llm_id, quantization)

    # Shuffled pool: built from all cached captions across all clips.
    pool_32 = [(uid, c) for uid, caps in captions_32.items() for c in caps]
    # Infer the base frame count from the cache (number of captions per clip).
    _sample_caps = next(iter(captions_32.values()), [])
    cache_frames_max = len(_sample_caps) if _sample_caps else FRAMES_MAX_DEFAULT

    results = {}
    for n_frames in frame_counts:
        print(f"\n── Scoring {n_frames} frames ──")
        per_question = []
        for qi, q in enumerate(questions):
            caps_full = captions_32.get(q["q_uid"], [])
            caps = subsample_captions(caps_full, n_frames)
            gold_letter = LETTERS[q["gold_idx"]]
            cond_recs = {}
            for cond in CONDITIONS:
                if cond == "shuffled":
                    # Draw shuffled pool entries at cache_frames_max, then subsample.
                    raw = shuffled_captions(q["q_uid"], cache_frames_max, pool_32,
                                           SHUFFLE_SEED + qi)
                    sub = subsample_captions(raw, n_frames) if raw else []
                    prompt = build_egoschema_prompt("shuffled", sub,
                                                    q["question"], q["options"])
                else:
                    prompt = build_egoschema_prompt(cond, caps,
                                                    q["question"], q["options"])
                rec = run_llm_two_call(llm, llm_tok, prompt,
                                       max_tokens=llm_max_tokens)
                pred = parse_choice(rec["response"])
                cond_recs[cond] = {
                    "pred": pred,
                    "correct": int(pred == gold_letter),
                    "prefill_ms": rec["prefill_ms"],
                    "prompt_tokens": rec["prompt_tokens"],
                    "effective_n_caps": len(caps),
                }
            per_question.append({
                "q_uid": q["q_uid"],
                "gold": gold_letter,
                "n_frames_requested": n_frames,
                "n_captions_available": len(caps_full),
                "n_captions_used": len(caps),
                "conditions": cond_recs,
            })
            if (qi + 1) % 10 == 0 or qi == 0 or qi == len(questions) - 1:
                blind = cond_recs["blind"]["correct"]
                full = cond_recs["full"]["correct"]
                print(f"  [{qi+1}/{len(questions)}] {q['q_uid']} "
                      f"gold={gold_letter} blind={blind} full={full}")
        results[n_frames] = per_question
        if save_cb:
            save_cb(results)
    return results


# ── Aggregation + rendering ─────────────────────────────────────────────

def summarize_sweep(results: dict) -> dict:
    """Aggregate per frame count. Returns {n_frames: {cond: metrics}}."""
    sweep = {}
    for n_frames, per_q in results.items():
        sweep[n_frames] = summarize(per_q)
    return sweep


def render_sweep_table(sweep: dict) -> str:
    lines = ["=" * 78, "FRAME-COUNT SWEEP TABLE", "=" * 78,
             f"{'frames':>8}  {'full acc':>9}  {'full ms':>9}  "
             f"{'full tok':>10}  {'stateless acc':>14}",
             "-" * 78]
    for n in sorted(sweep.keys()):
        s = sweep[n]
        full = s.get("full", {})
        sl = s.get("stateless", {})
        lines.append(
            f"{n:>8}  {full.get('accuracy', 0):>9.3f}  "
            f"{full.get('mean_prefill_ms', 0):>9.1f}  "
            f"{full.get('mean_prompt_tokens', 0):>10.1f}  "
            f"{sl.get('accuracy', 0):>14.3f}"
        )
    lines.append("-" * 78)
    return "\n".join(lines)


# ── Dry-run ─────────────────────────────────────────────────────────────

def _dry_run_results(n_q, seed=0):
    """Fabricate plausible frame-sweep results (no GPU, no data)."""
    import random as _random
    rng = _random.Random(seed)
    # accuracy and inertia both climb with frame count
    profile = {
        4:  {"full_acc": 0.38, "full_ms": 120,  "full_tok": 420,  "sl_acc": 0.30},
        8:  {"full_acc": 0.46, "full_ms": 240,  "full_tok": 810,  "sl_acc": 0.33},
        16: {"full_acc": 0.54, "full_ms": 460,  "full_tok": 1580, "sl_acc": 0.35},
        32: {"full_acc": 0.58, "full_ms": 910,  "full_tok": 3100, "sl_acc": 0.36},
    }
    results = {}
    for n, p in profile.items():
        per_q = []
        for i in range(n_q):
            gold = LETTERS[rng.randrange(5)]
            cond_recs = {}
            for cond in CONDITIONS:
                if cond == "full":
                    correct = int(rng.random() < p["full_acc"])
                    ms, tok = p["full_ms"] + rng.uniform(-10, 10), p["full_tok"]
                elif cond == "stateless":
                    correct = int(rng.random() < p["sl_acc"])
                    ms, tok = 55 + rng.uniform(-5, 5), 300
                else:
                    correct = int(rng.random() < 0.35)
                    ms, tok = 100, 600
                pred = gold if correct else LETTERS[(LETTERS.index(gold)+1) % 5]
                cond_recs[cond] = {"pred": pred, "correct": correct,
                                   "prefill_ms": round(ms, 1),
                                   "prompt_tokens": tok,
                                   "effective_n_caps": n}
            per_q.append({"q_uid": f"dry_{i}", "gold": gold,
                           "n_frames_requested": n,
                           "n_captions_used": n, "conditions": cond_recs})
        results[n] = per_q
    return results


# ── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Exp 8: Frame-count sweep on EgoSchema (accuracy vs. inertia)")
    ap.add_argument("--vlm", default="Qwen/Qwen2.5-VL-3B-Instruct")
    ap.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"],
                    default="fp16")
    ap.add_argument("--videos-dir", default="data/egoschema/videos")
    ap.add_argument("--questions", default="data/egoschema/questions.json")
    ap.add_argument("--answers", default="data/egoschema/subset_answers.json")
    ap.add_argument("--max-pixels", type=int, default=200704)
    ap.add_argument("--vlm-max-tokens", type=int, default=60)
    ap.add_argument("--llm-max-tokens", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0,
                    help="Only the first K questions (0 = all).")
    ap.add_argument("--frames-max", type=int, default=FRAMES_MAX_DEFAULT,
                    help="Number of frames to caption per clip (the base for "
                         "subsampling). Default 32.")
    ap.add_argument("--frame-counts", default=None,
                    help="Comma-separated frame counts to score, e.g. 4,8,16. "
                         "Must all be <= --frames-max. Default: 4,8,16,32.")
    ap.add_argument("--captions-cache",
                    default=None,
                    help="Caption cache path. Defaults to "
                         "results/egoschema_captions_<frames-max>.json.")
    ap.add_argument("--caption-only", action="store_true",
                    help="Run Phase 1 (captioning) only; skip reasoning.")
    ap.add_argument("--skip-captioning", action="store_true",
                    help="Skip Phase 1; run reasoning off existing cache.")
    ap.add_argument("--output", default="results/framesweep_qwen7b.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="No GPU/data — fabricate results to validate table.")
    args = ap.parse_args()

    frames_max = args.frames_max
    frame_counts = (
        [int(x) for x in args.frame_counts.split(",")]
        if args.frame_counts else
        [n for n in FRAME_COUNTS_DEFAULT if n <= frames_max]
    )
    captions_cache = (
        args.captions_cache or
        f"results/egoschema_captions_{frames_max}.json"
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        n_q = args.limit or 8
        print(f"DRY-RUN: fabricating {n_q} synthetic questions.")
        results = _dry_run_results(n_q)
        sweep = summarize_sweep(results)
        print("\n" + render_sweep_table(sweep))
        out_path.write_text(json.dumps(
            {"metadata": {"dry_run": True, "n_questions": n_q},
             "sweep_summary": {str(k): v for k, v in sweep.items()}}, indent=2))
        print(f"\nResults written to {out_path}")
        return

    import torch
    questions = load_egoschema(Path(args.questions), Path(args.answers))
    if args.limit:
        questions = questions[:args.limit]

    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    captions_path = Path(captions_cache)
    captions_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("EXP 8: Frame-count sweep — EgoSchema")
    print(f"  Device: {device}   VLM: {args.vlm}   LLM: {args.llm}")
    print(f"  Questions: {len(questions)}   Frames (max): {frames_max}")
    print(f"  Frame counts to score: {frame_counts}")
    print("=" * 78)

    # ── Phase 1: captioning ──
    if args.skip_captioning:
        captions_base = _load_caption_cache(captions_path)
        if not captions_base:
            raise SystemExit(
                f"--skip-captioning requested but cache empty: {captions_path}")
        print(f"\nSkipping captioning — loaded {len(captions_base)} clips from cache.")
    else:
        captions_base = caption_questions_32(
            questions, Path(args.videos_dir), args.vlm, args.quantization,
            args.max_pixels, args.vlm_max_tokens, captions_path,
            frames_max=frames_max)

    if args.caption_only:
        print(f"\nCaption-only mode complete. Cache: {captions_path}")
        return

    # Reasoning operates on questions with captions present.
    questions_to_score = [q for q in questions if q["q_uid"] in captions_base]
    print(f"\nScoring {len(questions_to_score)} questions across "
          f"frame counts {frame_counts}.")

    meta = {
        "dry_run": False, "device": device,
        "vlm": args.vlm, "llm": args.llm,
        "quantization": args.quantization,
        "frames_max": frames_max, "frame_counts": frame_counts,
        "n_questions": len(questions_to_score),
        "captions_cache": str(captions_path),
        "timestamp_start": datetime.now().isoformat(),
    }

    def _save(res):
        sw = summarize_sweep(res)
        out_path.write_text(json.dumps({
            "metadata": {**meta,
                         "timestamp_last_save": datetime.now().isoformat()},
            "sweep_summary": {str(k): v for k, v in sw.items()},
            "per_question": {str(k): v for k, v in res.items()},
        }, indent=2))

    results = reason_frame_sweep(
        questions_to_score, captions_base, args.llm, args.quantization,
        args.llm_max_tokens, frame_counts, save_cb=_save)

    sweep = summarize_sweep(results)
    _save(results)

    print("\n" + render_sweep_table(sweep))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
