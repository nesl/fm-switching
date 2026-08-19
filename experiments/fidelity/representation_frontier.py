"""
Representation Frontier — EgoSchema accuracy vs state-size (canonical runner)
==============================================================================
Publication-grade per-condition accuracy with significance tests on the
500-clip EgoSchema public subset.

  --model qwen7b   (default) — full pipeline: caption → summarize → score
                                Qwen2.5-7B-Instruct reasoner, raw prompts.
  --model smollm2             — scoring only (reuses cached captions/summaries)
                                SmolLM2-1.7B-Instruct reasoner, chat-template.

Conditions (8 total):
  blind       — question + options only (leakage screen)
  stateless   — last 1 caption
  window-3    — last 3 captions
  window-10   — last 10 captions
  full        — all 16 captions
  shuffled    — full-length captions drawn from OTHER clips (content control)
  summary-80  — LLM paragraph ~80 tok
  summary-200 — LLM paragraph ~200 tok

Design notes for smollm2:
  - Summaries remain 7B-generated (reused from qwen7b run). This isolates the
    REASONING capability gap of the 1.7B model from its summarization capability.
  - SmolLM2-Instruct requires chat-template wrapping to produce meaningful output.
    Absolute accuracy is not directly comparable to qwen7b; the SHAPE is the signal.

Output (schema: <function>_<model>.json):
  results/frontier_<model>.json           — summary + significance + provenance
  results/frontier_<model>_perquestion.json — per-question arrays (checkpoint)
  results/frontier_skipped_clips.json     — CUDA-failed clips (qwen7b phase 1)
  results/captions_cache.json             — caption cache (extended incrementally)
  results/summaries_cache_80.json         — summary-80 cache (extended)
  results/summaries_cache_200.json        — summary-200 cache (new for 200-tok)

Usage:
    # qwen7b full pipeline:
    CUDA_VISIBLE_DEVICES=1 python experiments/representation_frontier.py --model qwen7b

    # smollm2 scoring only (caches must exist from qwen7b run):
    CUDA_VISIBLE_DEVICES=1 python experiments/representation_frontier.py --model smollm2

    # resume after interruption (all phases auto-detect completed work):
    CUDA_VISIBLE_DEVICES=1 python experiments/representation_frontier.py --model qwen7b

    # skip completed phases explicitly:
    CUDA_VISIBLE_DEVICES=1 python experiments/representation_frontier.py --model qwen7b \\
        --skip-captioning --skip-summarization

    # smoke test (first 5 questions):
    CUDA_VISIBLE_DEVICES=1 python experiments/representation_frontier.py --model qwen7b \\
        --limit 5

Determinism: greedy / do_sample=False throughout; prompt format and choice-scoring
identical across runs; frame count / VLM unchanged (16 frames, Qwen2.5-VL-3B).
"""

import argparse
import gc
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")

import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from premise_egoschema import (
    LETTERS,
    SHUFFLE_SEED,
    _load_caption_cache,
    _save_caption_cache,
    build_egoschema_prompt,
    load_egoschema,
    parse_choice,
    sample_frames,
    shuffled_captions,
)
from _provenance import stamp

CONDITIONS = [
    "blind", "stateless", "window-3", "window-10",
    "full", "shuffled", "summary-80", "summary-200",
]

SUMMARY_CONDITIONS = {"summary-80", "summary-200"}

MODEL_LLM_ID = {
    "qwen7b":  "Qwen/Qwen2.5-7B-Instruct",
    "smollm2": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
}
MODEL_VLM_ID = "Qwen/Qwen2.5-VL-3B-Instruct"

_SUM_INSTR = {
    "summary-80": (
        "Summarize these frame-by-frame captions into a concise paragraph "
        "capturing key events, objects, and actions, in under ~80 tokens."
    ),
    "summary-200": (
        "Summarize these frame-by-frame captions into a detailed paragraph "
        "capturing all key events, objects, actions, and scene context, "
        "in under ~200 tokens."
    ),
}
_SUM_MAX_NEW_TOKENS = {"summary-80": 120, "summary-200": 300}


# ── Atomic JSON helpers ──────────────────────────────────────────────────

def _load_json_list(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return []


def _save_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Phase 1: Captioning ──────────────────────────────────────────────────

def caption_500(questions, videos_dir: Path, vlm_id, quantization,
                n_frames, max_pixels, vlm_max_tokens,
                captions_path: Path, skipped_path: Path):
    """Caption all clips. Resumes from captions_path; logs failures to skipped_path."""
    from context_inertia import load_vlm, run_vlm

    captions = _load_caption_cache(captions_path)
    skipped = {e["q_uid"]: e for e in _load_json_list(skipped_path)}

    todo = [q for q in questions
            if q["q_uid"] not in captions and q["q_uid"] not in skipped]
    if not todo:
        print(f"  Caption cache complete: {len(captions)} clips "
              f"({len(skipped)} skipped).")
        return captions

    print(f"  Caption cache: {len(captions)} done, {len(skipped)} skipped, "
          f"{len(todo)} remaining.")
    print("  Loading VLM...")
    vlm, vlm_proc = load_vlm(vlm_id, quantization, max_pixels)

    for qi, q in enumerate(todo):
        uid = q["q_uid"]
        vpath = videos_dir / f"{uid}.mp4"
        if not vpath.exists():
            alt = next((p for p in videos_dir.glob(f"{uid}.*")), None)
            vpath = alt if alt else vpath

        try:
            frames = sample_frames(vpath, n_frames)
        except Exception as ex:
            msg = str(ex)
            print(f"  [{qi+1}/{len(todo)}] {uid}: frame-load error — {msg[:80]}")
            skipped[uid] = {"q_uid": uid, "stage": "frame_load",
                            "exception": msg, "frame_indices": []}
            _save_json(skipped_path, list(skipped.values()))
            captions[uid] = []
            _save_caption_cache(captions_path, captions)
            continue

        caps = []
        frame_errors = []
        for fi, img in enumerate(frames):
            try:
                text, _ = run_vlm(vlm, vlm_proc, img, vlm_id, vlm_max_tokens)
                caps.append(text)
            except Exception as ex:
                msg = str(ex)
                print(f"  [{qi+1}/{len(todo)}] {uid} frame {fi}: VLM error — "
                      f"{msg[:60]}")
                frame_errors.append({"fi": fi, "exception": msg})
                if "CUDA error" in msg or "device-side assert" in msg:
                    try:
                        torch.cuda.synchronize()
                    except Exception:
                        captions[uid] = caps
                        _save_caption_cache(captions_path, captions)
                        skipped[uid] = {
                            "q_uid": uid, "stage": "cuda_context_corrupted",
                            "frame_errors": frame_errors,
                        }
                        _save_json(skipped_path, list(skipped.values()))
                        print(f"\n  CUDA context corrupted at {uid} frame {fi}."
                              f" Progress saved ({len(captions)} clips done)."
                              f" Restart to continue.")
                        sys.exit(0)

        if frame_errors and not caps:
            skipped[uid] = {"q_uid": uid, "stage": "vlm_all_frames",
                            "frame_errors": frame_errors, "frame_indices": []}
            _save_json(skipped_path, list(skipped.values()))

        captions[uid] = caps
        _save_caption_cache(captions_path, captions)
        if (qi + 1) % 20 == 0 or qi == 0 or qi == len(todo) - 1:
            print(f"  [{qi+1}/{len(todo)}] {uid}: {len(caps)} captions"
                  + (f" ({len(frame_errors)} frame errors)" if frame_errors else ""))

    del vlm, vlm_proc
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    print(f"  Captioning done. Cache: {len(captions)} clips, skipped: {len(skipped)}.")
    return captions


# ── Phase 2: Summarization ───────────────────────────────────────────────

def _build_sum_prompt(captions, instruction):
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(captions))
    return f"{instruction}\n\nFrame captions:\n{numbered}\n\nSummary:"


def summarize_500(q_uids, captions, llm, llm_tok,
                  summaries_path: Path, budget_key: str):
    """Generate summaries for all q_uids. Resumes from summaries_path."""
    instruction = _SUM_INSTR[budget_key]
    max_new = _SUM_MAX_NEW_TOKENS[budget_key]
    cache = _load_caption_cache(summaries_path)
    todo = [uid for uid in q_uids if uid not in cache]
    if not todo:
        print(f"  Summary cache ({budget_key}): all {len(cache)} clips done.")
        return cache
    print(f"  Summary cache ({budget_key}): {len(cache)} done, {len(todo)} remaining.")

    for i, uid in enumerate(todo):
        caps = captions.get(uid, [])
        if not caps:
            cache[uid] = ""
            _save_caption_cache(summaries_path, cache)
            continue
        prompt = _build_sum_prompt(caps, instruction)
        inputs = llm_tok(prompt, return_tensors="pt").to(llm.device)
        with torch.no_grad():
            out = llm.generate(
                **inputs, max_new_tokens=max_new, do_sample=False,
                pad_token_id=llm_tok.pad_token_id,
            )
        gen_ids = out[:, inputs["input_ids"].shape[1]:]
        text = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
        cache[uid] = text
        _save_caption_cache(summaries_path, cache)
        if (i + 1) % 20 == 0 or i == 0 or i == len(todo) - 1:
            print(f"  [{i+1}/{len(todo)}] {uid} ({budget_key}): "
                  f"{gen_ids.shape[1]} gen_toks — {text[:80]!r}")
    return cache


# ── Prompt builder (all 8 conditions) ────────────────────────────────────

def build_prompt(cond, captions, sum80_text, sum200_text, question, options):
    """Unified prompt builder for all 8 conditions."""
    if cond in ("blind", "stateless", "window-3", "window-10", "full", "shuffled"):
        return build_egoschema_prompt(
            cond if cond != "shuffled" else "full",
            captions, question, options,
        )
    header = (
        "You are answering a multiple-choice question about a first-person "
        "(egocentric) video. Below are text descriptions of the video, "
        "followed by a question and five options."
    )
    opt_block = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))
    instr = ("\n\nSelect the single best answer. Respond with ONLY the letter "
             "(A, B, C, D, or E).")
    ctx = sum80_text if cond == "summary-80" else sum200_text
    obs = f"\n\nVideo summary:\n{ctx}" if ctx else "\n\n(No summary available.)"
    return (f"{header}{obs}\n\nQuestion: {question}\n\n"
            f"Options:\n{opt_block}{instr}\nAnswer:")


# ── Phase 3: Scoring ──────────────────────────────────────────────────────

def score_500(questions, captions, sums80, sums200, llm, llm_tok,
              llm_max_tokens, pool, checkpoint_per_q,
              use_chat_template=False, save_cb=None):
    """Score all 8 conditions.

    use_chat_template=True wraps each raw prompt in the tokenizer's chat
    template before tokenizing — required for instruction-tuned models like
    SmolLM2-1.7B-Instruct that produce empty output on raw text.
    """
    done_uids = {r["q_uid"] for r in checkpoint_per_q}
    remaining = [q for q in questions if q["q_uid"] not in done_uids]
    per_question = list(checkpoint_per_q)

    if not remaining:
        print("  All questions already scored (loaded from checkpoint).")
        return per_question

    offset = len(per_question)
    print(f"  Scoring {len(remaining)} questions "
          f"({offset} already done, {len(questions)} total).")

    # pad_token_id differs by model family
    pad_id = (llm_tok.eos_token_id if use_chat_template
               else llm_tok.pad_token_id)

    for qi_local, q in enumerate(remaining):
        qi_global = offset + qi_local
        uid = q["q_uid"]
        caps = captions.get(uid, [])
        gold_letter = LETTERS[q["gold_idx"]]
        sum80 = sums80.get(uid, "") if sums80 else ""
        sum200 = sums200.get(uid, "") if sums200 else ""
        cond_recs = {}

        for cond in CONDITIONS:
            sel_caps = (shuffled_captions(uid, len(caps), pool, SHUFFLE_SEED + qi_global)
                        if cond == "shuffled" else caps)
            raw_prompt = build_prompt(cond, sel_caps, sum80, sum200,
                                      q["question"], q["options"])

            if use_chat_template:
                formatted = llm_tok.apply_chat_template(
                    [{"role": "user", "content": raw_prompt}],
                    tokenize=False, add_generation_prompt=True,
                )
                inputs = llm_tok(formatted, return_tensors="pt", padding=True).to(llm.device)
            else:
                inputs = llm_tok(raw_prompt, return_tensors="pt", padding=True).to(llm.device)

            prompt_len = int(inputs["input_ids"].shape[1])

            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                _ = llm.generate(**inputs, max_new_tokens=1,
                                  do_sample=False, pad_token_id=pad_id)
            torch.cuda.synchronize()
            prefill_ms = round((time.perf_counter() - t0) * 1000, 1)

            torch.cuda.synchronize()
            with torch.no_grad():
                out = llm.generate(**inputs, max_new_tokens=llm_max_tokens,
                                   do_sample=False, pad_token_id=pad_id)
            torch.cuda.synchronize()

            gen_ids = out[:, prompt_len:]
            response = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
            pred = parse_choice(response)
            cond_recs[cond] = {
                "pred": pred,
                "correct": int(pred == gold_letter),
                "prefill_ms": prefill_ms,
                "prompt_tokens": prompt_len,
            }

        per_question.append({
            "q_uid": uid,
            "gold": gold_letter,
            "n_captions": len(caps),
            "conditions": cond_recs,
        })

        n_done = qi_local + 1
        if n_done % 10 == 0 or n_done == 1 or n_done == len(remaining):
            rpt = "  ".join(f"{c}={cond_recs[c]['correct']}" for c in CONDITIONS)
            print(f"  [{offset + n_done}/{len(questions)}] "
                  f"{uid} gold={gold_letter}  {rpt}")
        if save_cb:
            save_cb(per_question)

    return per_question


# ── Statistics: Wilson CI + McNemar ─────────────────────────────────────

def wilson_ci(p: float, n: int, z: float = 1.96):
    if n == 0:
        return 0.0, 0.0
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def mcnemar_p(b: int, c: int) -> float:
    if b + c == 0:
        return 1.0
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    return round(1.0 - math.erf(math.sqrt(chi2 / 2)), 6)


def compute_statistics(per_question, conditions, mcnemar_pairs):
    summary = {}
    for cond in conditions:
        recs = [q["conditions"][cond] for q in per_question
                if cond in q.get("conditions", {})]
        n = len(recs)
        if n == 0:
            summary[cond] = {"accuracy": 0.0, "ci_lo": 0.0, "ci_hi": 0.0,
                             "mean_prefill_ms": 0.0, "std_prefill_ms": 0.0,
                             "mean_prompt_tokens": 0.0, "n": 0}
            continue
        acc = sum(r["correct"] for r in recs) / n
        ci_lo, ci_hi = wilson_ci(acc, n)
        ms_vals = [r["prefill_ms"] for r in recs]
        ms_mean = sum(ms_vals) / n
        ms_std = math.sqrt(sum((x - ms_mean) ** 2 for x in ms_vals) / n)
        summary[cond] = {
            "accuracy": round(acc, 4),
            "ci_lo": ci_lo, "ci_hi": ci_hi,
            "mean_prefill_ms": round(ms_mean, 1),
            "std_prefill_ms": round(ms_std, 1),
            "mean_prompt_tokens": round(
                sum(r["prompt_tokens"] for r in recs) / n, 1),
            "n": n,
        }

    correct_by_uid = {}
    for q in per_question:
        uid = q["q_uid"]
        correct_by_uid[uid] = {
            c: q["conditions"][c]["correct"]
            for c in conditions if c in q.get("conditions", {})
        }

    significance = {}
    for (cond_a, cond_b) in mcnemar_pairs:
        b = c = 0
        for uid, cv in correct_by_uid.items():
            if cond_a not in cv or cond_b not in cv:
                continue
            if cv[cond_a] == 1 and cv[cond_b] == 0:
                b += 1
            elif cv[cond_a] == 0 and cv[cond_b] == 1:
                c += 1
        pair_key = f"{cond_a}_vs_{cond_b}".replace("-", "_")
        significance[pair_key] = {
            "cond_a": cond_a, "cond_b": cond_b,
            "b_a_correct_b_wrong": b, "c_a_wrong_b_correct": c,
            "mcnemar_p": mcnemar_p(b, c),
            "delta_accuracy": round(
                summary.get(cond_a, {}).get("accuracy", 0)
                - summary.get(cond_b, {}).get("accuracy", 0), 4),
        }
    return summary, significance


# ── Console rendering ────────────────────────────────────────────────────

def render_table(summary, conditions):
    lines = [
        "=" * 86,
        "REPRESENTATION FRONTIER — 500 QUESTIONS",
        "=" * 86,
        f"{'condition':<14} {'acc':>7} {'95% CI':>14} {'prefill ms':>12} "
        f"{'tok':>8} {'n':>6}",
        "-" * 86,
    ]
    for cond in conditions:
        s = summary.get(cond, {})
        if not s or s.get("n", 0) == 0:
            continue
        ci = f"[{s['ci_lo']:.3f},{s['ci_hi']:.3f}]"
        lines.append(
            f"{cond:<14} {s['accuracy']:>7.3f} {ci:>14} "
            f"{s['mean_prefill_ms']:>9.1f}±{s['std_prefill_ms']:<4.1f}"
            f" {s['mean_prompt_tokens']:>8.1f} {s['n']:>6}"
        )
    lines.append("-" * 86)
    return "\n".join(lines)


def render_significance(significance):
    lines = [
        "",
        "MCNEMAR SIGNIFICANCE (continuity-corrected, two-sided)",
        "-" * 60,
        f"{'pair':<35} {'delta':>7} {'p':>10} {'b':>6} {'c':>6}",
        "-" * 60,
    ]
    for key, s in significance.items():
        pair = f"{s['cond_a']} vs {s['cond_b']}"
        lines.append(
            f"{pair:<35} {s['delta_accuracy']:>+7.3f} "
            f"{s['mcnemar_p']:>10.4f} "
            f"{s['b_a_correct_b_wrong']:>6} {s['c_a_wrong_b_correct']:>6}"
        )
    lines.append("-" * 60)
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

MCNEMAR_PAIRS = [
    ("full", "blind"),
    ("full", "shuffled"),
    ("stateless", "summary-80"),
    ("summary-200", "full"),
    ("window-10", "full"),
    ("summary-80", "summary-200"),
]


def main():
    ap = argparse.ArgumentParser(
        description="Representation frontier on full 500-clip EgoSchema subset"
    )
    ap.add_argument("--model", choices=["qwen7b", "smollm2"], default="qwen7b",
                    help="Model slug. qwen7b=Qwen2.5-7B (full pipeline); "
                         "smollm2=SmolLM2-1.7B (scoring only, reuses caches).")
    ap.add_argument("--llm", default=None,
                    help="Override LLM HuggingFace ID (default set by --model).")
    ap.add_argument("--vlm", default=MODEL_VLM_ID)
    ap.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"],
                    default="fp16")
    ap.add_argument("--videos-dir",      default="data/egoschema/videos")
    ap.add_argument("--questions",       default="data/egoschema/questions.json")
    ap.add_argument("--answers",         default="data/egoschema/subset_answers.json")
    ap.add_argument("--captions-cache",  default="results/captions_cache.json")
    ap.add_argument("--sum80-cache",     default="results/summaries_cache_80.json")
    ap.add_argument("--sum200-cache",    default="results/summaries_cache_200.json")
    ap.add_argument("--skipped-log",     default="results/frontier_skipped_clips.json")
    ap.add_argument("--output",          default=None,
                    help="Override output path (default: results/frontier_<model>.json).")
    ap.add_argument("--per-q-output",    default=None,
                    help="Override per-question path "
                         "(default: results/frontier_<model>_perquestion.json).")
    ap.add_argument("--frames",      type=int, default=16)
    ap.add_argument("--max-pixels",  type=int, default=200704)
    ap.add_argument("--vlm-max-tokens", type=int, default=60)
    ap.add_argument("--llm-max-tokens", type=int, default=16)
    ap.add_argument("--limit",       type=int, default=0,
                    help="Only first K questions (0=all 500). Smoke test: 5.")
    ap.add_argument("--skip-captioning",    action="store_true")
    ap.add_argument("--skip-summarization", action="store_true")
    args = ap.parse_args()

    # Resolve model-specific settings.
    model = args.model
    llm_id = args.llm or MODEL_LLM_ID[model]
    use_chat_template = (model == "smollm2")
    # smollm2 never needs to run captioning/summarization (reuses qwen7b caches)
    skip_captioning    = args.skip_captioning    or (model == "smollm2")
    skip_summarization = args.skip_summarization or (model == "smollm2")
    llm_max_tokens = 32 if model == "smollm2" else args.llm_max_tokens

    out_path    = Path(args.output    or f"results/frontier_{model}.json")
    per_q_path  = Path(args.per_q_output or f"results/frontier_{model}_perquestion.json")

    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("=" * 72)
    print(f"REPRESENTATION FRONTIER (--model {model})")
    print(f"  Device : {device}")
    print(f"  VLM    : {args.vlm}")
    print(f"  LLM    : {llm_id}  (chat-template={use_chat_template})")
    print(f"  CUDA_LAUNCH_BLOCKING: {os.environ.get('CUDA_LAUNCH_BLOCKING', '0')}")
    print("=" * 72)

    for p in [out_path, per_q_path, Path(args.skipped_log),
              Path(args.captions_cache), Path(args.sum80_cache),
              Path(args.sum200_cache)]:
        p.parent.mkdir(parents=True, exist_ok=True)

    all_questions = load_egoschema(Path(args.questions), Path(args.answers))
    if args.limit:
        all_questions = all_questions[: args.limit]
    print(f"\nQuestions: {len(all_questions)}")

    # ── Phase 1: Captioning ──────────────────────────────────────────────
    print("\n── Phase 1: Captioning ─────────────────────────────────────────")
    if skip_captioning:
        captions = _load_caption_cache(Path(args.captions_cache))
        print(f"  Skipped: loaded {len(captions)} clips from cache.")
    else:
        captions = caption_500(
            all_questions, Path(args.videos_dir),
            args.vlm, args.quantization,
            args.frames, args.max_pixels, args.vlm_max_tokens,
            Path(args.captions_cache), Path(args.skipped_log),
        )

    # ── Phase 2: Summarization ───────────────────────────────────────────
    print("\n── Phase 2: Summarization ──────────────────────────────────────")
    q_uids_all = [q["q_uid"] for q in all_questions]

    if skip_summarization:
        sums80  = _load_caption_cache(Path(args.sum80_cache))
        sums200 = _load_caption_cache(Path(args.sum200_cache))
        print(f"  Skipped: {len(sums80)} sum80, {len(sums200)} sum200.")
    else:
        from context_inertia import load_llm
        print("  Loading LLM for summarization...")
        llm, llm_tok = load_llm(llm_id, args.quantization)

        sums80 = summarize_500(
            q_uids_all, captions, llm, llm_tok,
            Path(args.sum80_cache), "summary-80",
        )
        sums200 = summarize_500(
            q_uids_all, captions, llm, llm_tok,
            Path(args.sum200_cache), "summary-200",
        )

        del llm, llm_tok
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ── Phase 3: Scoring ─────────────────────────────────────────────────
    print("\n── Phase 3: Scoring ────────────────────────────────────────────")

    checkpoint_per_q = _load_json_list(per_q_path)
    if checkpoint_per_q:
        print(f"  Checkpoint: {len(checkpoint_per_q)} questions already scored.")

    pool = [(uid, cap) for uid, caps in captions.items() for cap in caps]
    print(f"  Shuffled pool: {len(pool)} captions from {len(captions)} clips.")

    meta = {
        "model": model,
        "llm": llm_id,
        "vlm": args.vlm,
        "quantization": args.quantization,
        "n_frames": args.frames,
        "use_chat_template": use_chat_template,
        "n_questions_requested": len(all_questions),
        "conditions": CONDITIONS,
        "device": device,
        "timestamp_start": datetime.now().isoformat(),
    }

    def _save(per_q):
        _save_json(per_q_path, per_q)
        summary, _ = compute_statistics(per_q, CONDITIONS, [])
        _save_json(out_path, {
            "metadata": {**meta, "n_scored": len(per_q),
                         "timestamp_last_save": datetime.now().isoformat()},
            "summary": summary,
            "per_question_path": str(per_q_path),
        })

    from context_inertia import load_llm
    print("  Loading LLM for scoring...")
    llm, llm_tok = load_llm(llm_id, args.quantization)

    if use_chat_template:
        test_msg = [{"role": "user", "content": "Reply with exactly the letter A."}]
        test_fmt = llm_tok.apply_chat_template(test_msg, tokenize=False,
                                                add_generation_prompt=True)
        test_ids = llm_tok(test_fmt, return_tensors="pt").input_ids.to(llm.device)
        with torch.no_grad():
            test_out = llm.generate(test_ids, max_new_tokens=10, do_sample=False,
                                    pad_token_id=llm_tok.eos_token_id)
        test_resp = llm_tok.decode(test_out[0][test_ids.shape[1]:],
                                   skip_special_tokens=True).strip()
        print(f"  Chat-template sanity check → '{test_resp}'")
        if not test_resp:
            raise SystemExit("Model produced empty output — check model/template.")

    per_question = score_500(
        all_questions, captions, sums80, sums200,
        llm, llm_tok, llm_max_tokens,
        pool, checkpoint_per_q,
        use_chat_template=use_chat_template,
        save_cb=_save,
    )

    del llm, llm_tok
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    # ── Final statistics + output ────────────────────────────────────────
    print("\n── Computing statistics ────────────────────────────────────────")
    summary, significance = compute_statistics(per_question, CONDITIONS, MCNEMAR_PAIRS)

    provenance = stamp(
        script="representation_frontier.py",
        model=model,
        device=device.lower().replace(" ", "_"),
        n=len(per_question),
        args=args,
    )

    _save_json(per_q_path, per_question)
    _save_json(out_path, {
        "metadata": {
            **meta,
            "n_questions_scored": len(per_question),
            "captions_cache": args.captions_cache,
            "sum80_cache": args.sum80_cache,
            "sum200_cache": args.sum200_cache,
            "timestamp_end": datetime.now().isoformat(),
        },
        "summary": summary,
        "significance": significance,
        "per_question_path": str(per_q_path),
        "_provenance": provenance,
    })

    print("\n" + render_table(summary, CONDITIONS))
    print(render_significance(significance))
    print(f"\nResults written to {out_path}")
    print(f"Per-question data: {per_q_path}")


if __name__ == "__main__":
    main()
