"""
Experiment 7: Premise validation on EgoSchema (go/no-go for the stateful thesis)
================================================================================
Falsification test: does *accumulated episodic context* measurably improve
TASK ACCURACY, not just grow prefill cost? This replaces the hardcoded
`QUALITY[context_mode]` assumption in the simulator with a MEASURED metric on a
real multiple-choice benchmark (EgoSchema, public 500-question subset).

Pipeline (the existing two-stage architecture is preserved):
  VLM (Qwen2.5-VL-3B) captions each sampled frame  ──►  LLM (default
  Qwen2.5-7B-Instruct) reads the accumulated captions + question + 5 options
  (A–E) and selects one. The LLM is the stage whose context grows, so the
  inertia lives there.

Conditions swept (the four exp5 context modes + two screening baselines):
  blind       -- question + options only, ZERO captions (leakage screen)
  stateless   -- only the single most recent frame caption
  window-3    -- last 3 captions
  window-10   -- last 10 captions
  full        -- all N captions
  shuffled    -- full-length captions sampled from OTHER clips (fixed seed, no
                 overlap with the true clip): a content control. If full≈shuffled
                 the model is not using this clip's visual content (CONFOUNDED).

Metrics per condition:
  - accuracy        -- exact-match over the 5-way MC (replaces QUALITY lookup)
  - mean prefill ms -- exp5's two-call TTFT prefill timing (the inertia signal)
  - mean prompt tok -- prompt token count

Reuse contract: this file IMPORTS exp5's helpers verbatim (run_vlm,
run_llm_two_call, load_vlm, load_llm, and the module-level SDPA/GQA shim) and
NEVER mutates them. The MC prompt is built by a NEW function here because exp5's
`build_prompt` is hardwired to the inspection-robot task (no question/options/
blind concept, off-by-one windows, per-cycle response interleaving).

Prefix caching is effectively disabled exactly as in exp5: every LLM call
rebuilds the full prompt; there is no KV reuse across calls or cycles.

This is a PREMISE test only — NO orchestrator, NO simulator, NO
KV-transfer/summarization variants.

  Lab-GPU run (A5000/A6000), full subset:
    python experiments/exp7_premise_egoschema.py \
        --videos-dir data/egoschema/videos \
        --questions  data/egoschema/questions.json \
        --answers    data/egoschema/subset_answers.json \
        --vlm Qwen/Qwen2.5-VL-3B-Instruct --llm Qwen/Qwen2.5-7B-Instruct \
        --frames 16 --output results/exp7_premise.json

  Smoke test (sanity-check table shape + verdict before GPU hours):
    ... --limit 5

  GPU-free validation of the table/verdict logic (runs anywhere):
    python experiments/exp7_premise_egoschema.py --self-test
    python experiments/exp7_premise_egoschema.py --dry-run --limit 8
"""

import argparse
import gc
import json
import math
import random
import re
from datetime import datetime
from pathlib import Path


# ── Conditions ──────────────────────────────────────────────────────────
# The blind leakage screen FIRST (most important line), then the four exp5
# context modes, then the `shuffled` content control. Both blind and shuffled
# are screening baselines (see the LEAKY and CONFOUNDED verdict branches).
CONDITIONS = ["blind", "stateless", "window-3", "window-10", "full", "shuffled"]
LETTERS = "ABCDE"

# Fixed seed for the `shuffled` content control (reproducible cross-clip draw).
SHUFFLE_SEED = 1234

# Verdict thresholds (5-way MC; chance = 20%). User-approved 5pp / 10pp / 3pp.
MATERIALLY_BEATS_PP = 0.05   # full (or window-10) must beat stateless by this
NON_LEAKY_PP        = 0.10   # full must beat blind by this for a clean GO
LEAKY_PP            = 0.03   # |full - blind| <= this  => benchmark is leaky
CONFOUNDED_PP       = 0.05   # full - shuffled < this => not using visual content


# ── EgoSchema loading ───────────────────────────────────────────────────

def load_egoschema(questions_path: Path, answers_path: Path):
    """Return list of dicts: {q_uid, question, options[5], gold_idx}.

    Supports both EgoSchema layouts:
      questions.json  -> list of entries OR {q_uid: entry}
      answers.json    -> {q_uid: gold_index}
    Entries carry the options under keys "option 0".."option 4".
    """
    q_raw = json.loads(Path(questions_path).read_text())
    a_raw = json.loads(Path(answers_path).read_text())

    if isinstance(q_raw, dict):
        entries = [{**v, "q_uid": v.get("q_uid", k)} for k, v in q_raw.items()]
    else:
        entries = list(q_raw)

    out = []
    for e in entries:
        quid = e["q_uid"]
        if quid not in a_raw:
            continue  # only the public-answer subset
        opts = [str(e[f"option {i}"]) for i in range(5)]
        out.append({
            "q_uid": quid,
            "question": str(e["question"]),
            "options": opts,
            "gold_idx": int(a_raw[quid]),
        })
    return out


def sample_frame_indices(total: int, n: int):
    """Evenly spaced indices across [0, total-1]."""
    if total <= 0:
        return []
    if n >= total:
        return list(range(total))
    if n == 1:
        return [total // 2]
    return [int(round(i * (total - 1) / (n - 1))) for i in range(n)]


def sample_frames(video_path: Path, n: int):
    """Sample N frames evenly across the clip. Uses decord (preferred)."""
    try:
        import decord
    except ImportError as ex:
        raise RuntimeError(
            "decord is required to sample frames from clips. Install it on the "
            "lab GPU box (`pip install decord`), or pass pre-extracted frames "
            "by adapting --videos-dir to a frames dir."
        ) from ex
    from PIL import Image
    vr = decord.VideoReader(str(video_path))
    idxs = sample_frame_indices(len(vr), n)
    if not idxs:
        return []
    batch = vr.get_batch(idxs).asnumpy()  # (n, H, W, 3)
    return [Image.fromarray(batch[i]) for i in range(batch.shape[0])]


# ── MC prompt builder (NEW — exp5.build_prompt cannot represent this) ────

def build_egoschema_prompt(mode: str, captions, question: str, options):
    """Build the multiple-choice prompt for one (question, condition).

    `captions` is the chronological list of all N frame captions for the clip.
    The condition selects how many of them the reasoner sees.
    """
    if mode == "blind":
        sel = []
    elif mode == "stateless":
        sel = captions[-1:]
    elif mode == "window-3":
        sel = captions[-3:]
    elif mode == "window-10":
        sel = captions[-10:]
    elif mode in ("full", "shuffled"):
        # `shuffled` is full-length but the caller passes captions drawn from
        # OTHER clips (content control); structurally identical to `full`.
        sel = list(captions)
    else:
        raise ValueError(f"unknown condition: {mode}")

    header = (
        "You are answering a multiple-choice question about a first-person "
        "(egocentric) video. Below are chronological text descriptions of frames "
        "sampled from the video, followed by a question and five options."
    )
    if sel:
        lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(sel))
        obs = f"\n\nFrame descriptions (chronological):\n{lines}"
    else:
        obs = "\n\n(No frame descriptions are provided.)"

    opt_block = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))
    instr = ("\n\nSelect the single best answer. Respond with ONLY the letter "
             "(A, B, C, D, or E).")
    return f"{header}{obs}\n\nQuestion: {question}\n\nOptions:\n{opt_block}{instr}\nAnswer:"


def shuffled_captions(true_uid, k, pool, seed):
    """Full-length caption set for the `shuffled` content control: draw k
    captions from clips OTHER than `true_uid` (no overlap with the true clip),
    deterministically under `seed`. Returns [] if k<=0 or no other captions."""
    cand = [cap for (uid, cap) in pool if uid != true_uid]
    if not cand or k <= 0:
        return []
    rng = random.Random(seed)
    if len(cand) >= k:
        return rng.sample(cand, k)
    return [rng.choice(cand) for _ in range(k)]


# ── Answer parsing ──────────────────────────────────────────────────────

def parse_choice(text: str):
    """Extract an A–E letter from free-text LLM output. None if unparseable."""
    if not text:
        return None
    m = re.search(r"answer\s*[:\-]?\s*\(?\s*([A-E])\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([A-E])\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"([A-E])", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


# ── Verdict logic (pure function — covered by --self-test) ───────────────

def compute_verdict(acc: dict):
    """acc maps condition -> accuracy in [0,1]. Returns verdict dict."""
    full = acc.get("full", 0.0)
    w10 = acc.get("window-10", 0.0)
    sl = acc.get("stateless", 0.0)
    blind = acc.get("blind", 0.0)
    has_shuffle = "shuffled" in acc
    shuffled = acc.get("shuffled", 0.0)

    d_blind = full - blind                 # higher => less leaky
    d_ctx = max(full, w10) - sl            # higher => context materially helps
    d_shuffle = full - shuffled            # higher => uses THIS clip's content

    if d_blind <= LEAKY_PP:
        label = "NO-GO / LEAKY"
        reason = (f"blind≈full (full-blind={d_blind:+.3f} ≤ {LEAKY_PP}); "
                  "benchmark answerable without history — SWITCH BENCHMARK "
                  "(e.g. FindingDory), do not abandon the premise.")
    elif has_shuffle and d_shuffle < CONFOUNDED_PP:
        label = "NO-GO / CONFOUNDED"
        reason = (f"full≈shuffled (full-shuffled={d_shuffle:+.3f} < "
                  f"{CONFOUNDED_PP}); model answers the same with captions from "
                  "OTHER clips — it is not using this clip's visual content. "
                  "Fix the captioner/prompt or switch benchmark.")
    elif d_ctx >= MATERIALLY_BEATS_PP and d_blind >= NON_LEAKY_PP:
        label = "GO"
        reason = (f"context materially helps (max(full,window-10)-stateless="
                  f"{d_ctx:+.3f} ≥ {MATERIALLY_BEATS_PP}) and task is not leaky "
                  f"(full-blind={d_blind:+.3f} ≥ {NON_LEAKY_PP}).")
    elif d_ctx < MATERIALLY_BEATS_PP:
        label = "NO-GO / PREMISE-FAILS"
        reason = (f"non-leaky blind screen (full-blind={d_blind:+.3f}) but "
                  f"accuracy is flat across stateless→full "
                  f"(max(full,window-10)-stateless={d_ctx:+.3f} < "
                  f"{MATERIALLY_BEATS_PP}).")
    else:
        label = "NO-GO / INCONCLUSIVE"
        reason = (f"context helps (d_ctx={d_ctx:+.3f}) but blind margin is "
                  f"marginal (full-blind={d_blind:+.3f}, between {LEAKY_PP} and "
                  f"{NON_LEAKY_PP}); collect more questions or inspect blind.")

    return {
        "label": label,
        "reason": reason,
        "full_minus_blind": round(d_blind, 4),
        "ctx_minus_stateless": round(d_ctx, 4),
        "full_minus_shuffled": round(d_shuffle, 4) if has_shuffle else None,
        "thresholds": {
            "materially_beats_pp": MATERIALLY_BEATS_PP,
            "non_leaky_pp": NON_LEAKY_PP,
            "leaky_pp": LEAKY_PP,
            "confounded_pp": CONFOUNDED_PP,
        },
    }


# ── Aggregation + rendering ─────────────────────────────────────────────

def summarize(per_question: list):
    """Aggregate per-condition accuracy / mean prefill ms / mean prompt tokens."""
    summary = {}
    for cond in CONDITIONS:
        recs = [q["conditions"][cond] for q in per_question
                if cond in q["conditions"]]
        n = len(recs)
        if n == 0:
            summary[cond] = {"accuracy": 0.0, "mean_prefill_ms": 0.0,
                             "mean_prompt_tokens": 0.0, "n": 0}
            continue
        summary[cond] = {
            "accuracy": round(sum(r["correct"] for r in recs) / n, 4),
            "mean_prefill_ms": round(sum(r["prefill_ms"] for r in recs) / n, 1),
            "mean_prompt_tokens": round(sum(r["prompt_tokens"] for r in recs) / n, 1),
            "n": n,
        }
    return summary


def render_table(summary: dict):
    lines = []
    lines.append("=" * 72)
    lines.append("WORKLOAD-LEGITIMACY TABLE")
    lines.append("=" * 72)
    lines.append(f"{'condition':<12} {'accuracy':>10} {'prefill ms':>12} "
                 f"{'prompt tok':>12} {'n':>6}")
    lines.append("-" * 72)
    for cond in CONDITIONS:
        s = summary[cond]
        lines.append(f"{cond:<12} {s['accuracy']:>10.3f} "
                     f"{s['mean_prefill_ms']:>12.1f} "
                     f"{s['mean_prompt_tokens']:>12.1f} {s['n']:>6}")
    lines.append("-" * 72)
    return "\n".join(lines)


# ── Phase 1: VLM captioning ─────────────────────────────────────────────

def _load_caption_cache(captions_path: Path) -> dict:
    """Load existing caption cache from disk; return empty dict if absent."""
    if captions_path.exists():
        try:
            return json.loads(captions_path.read_text())
        except Exception:
            pass
    return {}


def _save_caption_cache(captions_path: Path, captions: dict) -> None:
    """Atomically persist caption cache: write to .tmp then rename."""
    tmp = captions_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(captions, indent=2))
    tmp.replace(captions_path)


def caption_questions(questions, videos_dir: Path, vlm_id, quantization,
                      n_frames, max_pixels, vlm_max_tokens,
                      captions_path: Path | None = None):
    """Load VLM once, caption N frames per clip, unload. Returns captions dict
    {q_uid: [caption, ...]}. If captions_path is given, loads existing captions
    on startup (skipping done clips) and persists after each clip."""
    import torch
    from context_inertia import load_vlm, run_vlm  # reuse, never mutate

    captions = _load_caption_cache(captions_path) if captions_path else {}
    todo = [q for q in questions if q["q_uid"] not in captions]
    if captions_path and len(captions) > 0:
        print(f"\nCaption cache: {len(captions)} clips already done, "
              f"{len(todo)} remaining.")
    if not todo:
        print("  All clips already captioned — skipping VLM load.")
        return captions

    print("\nLoading VLM...")
    vlm, vlm_proc = load_vlm(vlm_id, quantization, max_pixels)
    for qi, q in enumerate(todo):
        vpath = videos_dir / f"{q['q_uid']}.mp4"
        if not vpath.exists():
            alt = next((p for p in videos_dir.glob(f"{q['q_uid']}.*")), None)
            vpath = alt if alt else vpath
        try:
            frames = sample_frames(vpath, n_frames)
        except Exception as ex:  # noqa: BLE001
            print(f"  [{qi+1}/{len(todo)}] {q['q_uid']}: frame error: {ex}")
            captions[q["q_uid"]] = []
            if captions_path:
                _save_caption_cache(captions_path, captions)
            continue
        caps = []
        for img in frames:
            try:
                text, _lat = run_vlm(vlm, vlm_proc, img, vlm_id, vlm_max_tokens)
                caps.append(text)
            except Exception as ex:  # noqa: BLE001 — CUDA assert or OOM
                print(f"  [{qi+1}/{len(todo)}] {q['q_uid']}: VLM frame error (skipped): {ex}")
        captions[q["q_uid"]] = caps
        if captions_path:
            _save_caption_cache(captions_path, captions)
        print(f"  [{qi+1}/{len(todo)}] {q['q_uid']}: {len(caps)} captions")

    del vlm, vlm_proc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return captions


# ── Phase 2: LLM reasoning sweep ────────────────────────────────────────

def reason_questions(questions, captions, llm_id, quantization, llm_max_tokens,
                     save_cb=None):
    """Load LLM once, sweep CONDITIONS over cached captions. Returns
    per_question records."""
    from context_inertia import load_llm, run_llm_two_call  # reuse

    print("\nLoading LLM (reasoner)...")
    llm, llm_tok = load_llm(llm_id, quantization)

    # Pool of (q_uid, caption) across ALL clips for the `shuffled` content
    # control; assembled once since Phase 1 captioned everything up front.
    pool = [(uid, c) for uid, caps in captions.items() for c in caps]

    per_question = []
    for qi, q in enumerate(questions):
        caps = captions.get(q["q_uid"], [])
        gold_letter = LETTERS[q["gold_idx"]]
        cond_recs = {}
        for cond in CONDITIONS:
            if cond == "shuffled":
                sub = shuffled_captions(q["q_uid"], len(caps), pool,
                                        SHUFFLE_SEED + qi)
                prompt = build_egoschema_prompt("shuffled", sub,
                                                q["question"], q["options"])
            else:
                prompt = build_egoschema_prompt(cond, caps, q["question"],
                                                q["options"])
            rec = run_llm_two_call(llm, llm_tok, prompt, max_tokens=llm_max_tokens)
            pred = parse_choice(rec["response"])
            cond_recs[cond] = {
                "pred": pred,
                "correct": int(pred == gold_letter),
                "prefill_ms": rec["prefill_ms"],
                "prompt_tokens": rec["prompt_tokens"],
            }
        per_question.append({
            "q_uid": q["q_uid"],
            "gold": gold_letter,
            "n_captions": len(caps),
            "conditions": cond_recs,
        })
        if (qi + 1) % 10 == 0 or qi == 0 or qi == len(questions) - 1:
            acc = {c: cond_recs[c]["correct"] for c in CONDITIONS}
            print(f"  [{qi+1}/{len(questions)}] {q['q_uid']} gold={gold_letter} "
                  f"blind={acc['blind']} full={acc['full']}")
        if save_cb:
            save_cb(per_question)
    return per_question


# ── Dry-run / self-test (GPU-free validation of table + verdict) ─────────

def _synthetic_per_question(n_q, seed=0):
    """Fabricate per-question records with a monotone accuracy gradient so the
    table renders and the GO branch exercises end-to-end. NO models, NO data."""
    rng = random.Random(seed)
    # condition -> P(correct); blind low, context climbing => expect GO
    p = {"blind": 0.22, "stateless": 0.30, "window-3": 0.40,
         "window-10": 0.52, "full": 0.58, "shuffled": 0.30}
    base_tok = {"blind": 120, "stateless": 200, "window-3": 360,
                "window-10": 900, "full": 1400, "shuffled": 1400}
    per = []
    for i in range(n_q):
        gold = LETTERS[rng.randrange(5)]
        cond_recs = {}
        for c in CONDITIONS:
            correct = int(rng.random() < p[c])
            cond_recs[c] = {
                "pred": gold if correct else LETTERS[(LETTERS.index(gold) + 1) % 5],
                "correct": correct,
                "prefill_ms": round(base_tok[c] * 0.15 + rng.uniform(-5, 5), 1),
                "prompt_tokens": base_tok[c] + rng.randint(-20, 20),
            }
        per.append({"q_uid": f"synthetic_{i}", "gold": gold,
                    "n_captions": 16, "conditions": cond_recs})
    return per


def run_self_test():
    """Assert the verdict function classifies the three named regimes."""
    cases = {
        "GO": {"blind": 0.22, "stateless": 0.30, "window-3": 0.40,
               "window-10": 0.52, "full": 0.58, "shuffled": 0.30},
        "NO-GO / LEAKY": {"blind": 0.56, "stateless": 0.40, "window-3": 0.50,
                          "window-10": 0.57, "full": 0.58, "shuffled": 0.55},
        "NO-GO / CONFOUNDED": {"blind": 0.22, "stateless": 0.30,
                               "window-3": 0.45, "window-10": 0.50,
                               "full": 0.55, "shuffled": 0.53},
        "NO-GO / PREMISE-FAILS": {"blind": 0.22, "stateless": 0.34,
                                  "window-3": 0.35, "window-10": 0.36,
                                  "full": 0.37, "shuffled": 0.30},
    }
    ok = True
    for expected, acc in cases.items():
        v = compute_verdict(acc)
        status = "PASS" if v["label"] == expected else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{status}] expected {expected:<24} got {v['label']:<24} "
              f"(d_blind={v['full_minus_blind']:+.3f}, "
              f"d_ctx={v['ctx_minus_stateless']:+.3f})")
    print("\nself-test:", "ALL PASS" if ok else "FAILURES PRESENT")
    return ok


# ── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Exp 7: EgoSchema premise validation")
    ap.add_argument("--vlm", default="Qwen/Qwen2.5-VL-3B-Instruct")
    ap.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct",
                    help="Capable reasoner (NOT SmolLM2 — avoid false negative).")
    ap.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"],
                    default="fp16")
    ap.add_argument("--videos-dir", default="data/egoschema/videos")
    ap.add_argument("--questions", default="data/egoschema/questions.json")
    ap.add_argument("--answers", default="data/egoschema/subset_answers.json")
    ap.add_argument("--frames", type=int, default=16,
                    help="N frames sampled evenly per clip.")
    ap.add_argument("--max-pixels", type=int, default=200704)
    ap.add_argument("--vlm-max-tokens", type=int, default=60)
    ap.add_argument("--llm-max-tokens", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0,
                    help="Only the first K questions (0 = all). Smoke test: 5.")
    ap.add_argument("--output", default="results/premise_qwen7b_n150.json")
    ap.add_argument("--captions-cache", default="results/captions_cache.json",
                    help="Path to per-clip caption cache (keyed by q_uid). "
                         "Written incrementally during captioning; read on resume.")
    ap.add_argument("--skip-captioning", action="store_true",
                    help="Skip Phase 1 entirely — run reasoning only against the "
                         "existing captions cache. Errors if cache is empty.")
    ap.add_argument("--dry-run", action="store_true",
                    help="No models/data: fabricate records to validate table+verdict.")
    ap.add_argument("--self-test", action="store_true",
                    help="Assert verdict logic on synthetic accuracy regimes; exit.")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(0 if run_self_test() else 1)

    # ── Assemble per-question records ──
    if args.dry_run:
        n_q = args.limit or 8
        print(f"DRY-RUN: fabricating {n_q} synthetic questions (no GPU, no data).")
        per_question = _synthetic_per_question(n_q)
        meta = {"dry_run": True, "n_questions": n_q}
    else:
        import torch
        questions = load_egoschema(Path(args.questions), Path(args.answers))
        if args.limit:
            questions = questions[:args.limit]
        device = (torch.cuda.get_device_name(0)
                  if torch.cuda.is_available() else "cpu")
        print("=" * 72)
        print("EXP 7: EgoSchema premise validation")
        print(f"  Device: {device}   VLM: {args.vlm}   LLM: {args.llm}")
        print(f"  Questions: {len(questions)}   Frames/clip: {args.frames}")
        print("=" * 72)
        if "cuda" not in device and device != "cpu":
            pass
        if device == "cpu":
            print("  WARNING: no CUDA device — this is a premise/accuracy test "
                  "meant for the lab A5000/A6000, not CPU/Jetson.")

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        captions_path = Path(args.captions_cache)
        captions_path.parent.mkdir(parents=True, exist_ok=True)

        if args.skip_captioning:
            captions = _load_caption_cache(captions_path)
            if not captions:
                raise SystemExit(
                    f"--skip-captioning requested but caption cache is empty "
                    f"or missing: {captions_path}"
                )
            print(f"\nSkipping captioning — loaded {len(captions)} clips from cache.")
        else:
            captions = caption_questions(
                questions, Path(args.videos_dir), args.vlm, args.quantization,
                args.frames, args.max_pixels, args.vlm_max_tokens,
                captions_path=captions_path)

        # Reasoning operates on questions whose captions are present in cache,
        # respecting --limit. The full cache is used for the shuffled pool.
        questions_to_score = [q for q in questions if q["q_uid"] in captions]
        print(f"\nReasoning over {len(questions_to_score)} captioned questions "
              f"(cache has {len(captions)} total clips).")

        meta = {
            "dry_run": False,
            "device": device,
            "vlm": args.vlm, "llm": args.llm,
            "quantization": args.quantization,
            "n_frames": args.frames,
            "n_questions": len(questions_to_score),
            "captions_cache": str(captions_path),
            "skip_captioning": args.skip_captioning,
            "conditions": CONDITIONS,
            "timestamp_start": datetime.now().isoformat(),
        }

        def _save(per):
            out_path.write_text(json.dumps({
                "metadata": {**meta, "timestamp_last_save": datetime.now().isoformat()},
                "per_question": per,
                "summary": summarize(per),
            }, indent=2))

        per_question = reason_questions(
            questions_to_score, captions, args.llm, args.quantization,
            args.llm_max_tokens, save_cb=_save)

    # ── Summary + verdict ──
    summary = summarize(per_question)
    acc = {c: summary[c]["accuracy"] for c in CONDITIONS}
    verdict = compute_verdict(acc)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "metadata": {**meta, "timestamp_end": datetime.now().isoformat()},
        "per_question": per_question,
        "summary": summary,
        "verdict": verdict,
    }, indent=2))

    print("\n" + render_table(summary))
    print(f"\nVERDICT: {verdict['label']}")
    print(f"  {verdict['reason']}")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
