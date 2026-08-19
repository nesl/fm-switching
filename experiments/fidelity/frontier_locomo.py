"""
LoCoMo Representation Frontier
===============================
Measures how context compression affects QA accuracy on long dialogue histories.

Dataset : LoCoMo (locomo10.json) — 10 conversations, each 11K-23K tokens of
          multi-session dialogue with 105-260 QA pairs per conversation.
          Categories: 1=single-hop, 2=multi-hop, 3=temporal, 4=open-domain, 5=adversarial.

Model   : Qwen2.5-7B-Instruct (32K context). SmolLM2-1.7B's 2048-token limit is
          far below the shortest full history (11K tokens) — 'full' is infeasible
          on the edge model. This is flagged as a finding, not a workaround.

Conditions (same 8 as EgoSchema frontier):
  blind       — question only (no history)
  stateless   — last 1 dialogue turn (most recent single message)
  window-3    — last 3 sessions
  window-10   — last 10 sessions (or all if < 10)
  full        — all sessions (9K-23K tok; fits Qwen2.5-7B, NOT SmolLM2)
  shuffled    — sessions in shuffled order (content/order control)
  summary-80  — Qwen2.5-7B summary of full history ~80 tokens
  summary-200 — Qwen2.5-7B summary of full history ~200 tokens

Scorer  : free-form generation + normalized substring match against gold answer.
          Applied identically across all conditions.

Plug points relative to representation_frontier.py:
  - load_egoschema()          → load_locomo() (text QA, not MCQ)
  - build_egoschema_prompt()  → build_locomo_prompt() (dialogue history, not captions)
  - parse_choice() MCQ match  → score_answer() substring match
  - VLM phase                 → absent (history is already text)

Usage:
    # Pilot (n=50 single-hop questions, 5 per conversation):
    CUDA_VISIBLE_DEVICES=1 python experiments/frontier_locomo.py --limit 50

    # Full single-hop (cat=1) run:
    CUDA_VISIBLE_DEVICES=1 python experiments/frontier_locomo.py --category 1

    # All categories:
    CUDA_VISIBLE_DEVICES=1 python experiments/frontier_locomo.py

Output:
    results/frontier_locomo_qwen7b.json
    results/frontier_locomo_qwen7b_perquestion.json
"""

import argparse
import gc
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")

import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from _provenance import stamp

CONDITIONS = [
    "blind", "stateless", "window-3", "window-10",
    "full", "shuffled", "summary-80", "summary-200",
]

# Category labels from LoCoMo paper
CATEGORY_NAMES = {1: "single-hop", 2: "multi-hop", 3: "temporal",
                  4: "open-domain", 5: "adversarial"}

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG = "qwen7b"
SHUFFLE_SEED = 42

_SUM_INSTR = {
    "summary-80": (
        "Summarize this conversation history between two people into a concise paragraph "
        "capturing key events, facts, relationships, and dates, in under ~80 tokens."
    ),
    "summary-200": (
        "Summarize this conversation history between two people into a detailed paragraph "
        "capturing all key events, facts, relationships, dates, and context, "
        "in under ~200 tokens."
    ),
}
_SUM_MAX_NEW_TOKENS = {"summary-80": 120, "summary-200": 300}


# ── Atomic JSON helpers ────────────────────────────────────────────────────

def _load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def _save_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Data loader ────────────────────────────────────────────────────────────

def load_locomo(data_path: Path, category: int = None, limit: int = 0,
                per_conv_limit: int = 0):
    """Load LoCoMo questions and conversation histories.

    Returns:
        questions : list of {q_uid, conv_id, question, gold_answer, category, evidence}
        histories : dict conv_id → {sessions: [[{speaker,text},...], ...],
                                    dates: [str,...],
                                    speaker_a: str, speaker_b: str}
    """
    raw = json.loads(data_path.read_text())
    questions = []
    histories = {}

    for item in raw:
        conv_id = item["sample_id"]
        conv = item["conversation"]

        speaker_a = conv.get("speaker_a", "A")
        speaker_b = conv.get("speaker_b", "B")

        # Collect sessions in order
        sessions = []
        dates = []
        i = 1
        while f"session_{i}" in conv:
            turns = conv[f"session_{i}"]
            if turns:
                sessions.append(turns)
                dates.append(conv.get(f"session_{i}_date_time", ""))
            i += 1

        histories[conv_id] = {
            "sessions": sessions,
            "dates": dates,
            "speaker_a": speaker_a,
            "speaker_b": speaker_b,
        }

        # Filter QA by category
        qa_items = item["qa"]
        if category is not None:
            qa_items = [q for q in qa_items if q["category"] == category]

        # Apply per-conversation limit (for balanced sampling across convs)
        if per_conv_limit > 0:
            qa_items = qa_items[:per_conv_limit]

        for qi, qa in enumerate(qa_items):
            questions.append({
                "q_uid": f"{conv_id}_q{qi:04d}",
                "conv_id": conv_id,
                "question": qa["question"],
                "gold_answer": qa["answer"],
                "category": qa["category"],
                "evidence": qa.get("evidence", []),
            })

    # Global limit applied after balanced per-conv sampling
    if limit > 0:
        questions = questions[:limit]

    return questions, histories


# ── History text builders ──────────────────────────────────────────────────

def _sessions_to_text(sessions, dates, max_sessions=None, reverse=False,
                      shuffle_seed=None):
    """Render sessions as a text block. max_sessions=None means all."""
    sess_list = sessions
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        sess_list = list(sessions)
        rng.shuffle(sess_list)
        dates = ["(shuffled)" for _ in dates]

    if max_sessions is not None:
        sess_list = sess_list[-max_sessions:]
        dates = dates[-max_sessions:] if dates else dates

    lines = []
    for si, sess in enumerate(sess_list):
        date_label = dates[si] if si < len(dates) else ""
        header = f"[Session {si+1}" + (f" — {date_label}]" if date_label else "]")
        lines.append(header)
        for turn in sess:
            lines.append(f"{turn['speaker']}: {turn['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def build_context(cond, history, shuffle_seed=None):
    """Return the context string for a given condition."""
    sessions = history["sessions"]
    dates = history["dates"]

    if cond == "blind":
        return ""
    if cond == "stateless":
        # Last single dialogue turn
        if sessions and sessions[-1]:
            t = sessions[-1][-1]
            return f"{t['speaker']}: {t['text']}"
        return ""
    if cond == "window-3":
        return _sessions_to_text(sessions, dates, max_sessions=3)
    if cond == "window-10":
        return _sessions_to_text(sessions, dates, max_sessions=10)
    if cond == "full":
        return _sessions_to_text(sessions, dates)
    if cond == "shuffled":
        return _sessions_to_text(sessions, dates, shuffle_seed=shuffle_seed)
    raise ValueError(f"build_context: unknown condition {cond!r}")


def build_locomo_prompt(cond, history, sum80_text, sum200_text, question,
                        shuffle_seed=None):
    """Build the full prompt for a LoCoMo QA question under a given condition."""
    speaker_a = history["speaker_a"]
    speaker_b = history["speaker_b"]
    header = (
        f"You are answering a question about a conversation history between "
        f"{speaker_a} and {speaker_b}."
    )

    if cond in ("summary-80", "summary-200"):
        ctx_text = sum80_text if cond == "summary-80" else sum200_text
        obs = f"\n\nConversation summary:\n{ctx_text}" if ctx_text else \
              "\n\n(No summary available.)"
    elif cond == "blind":
        obs = ""
    else:
        ctx_text = build_context(cond, history, shuffle_seed=shuffle_seed)
        obs = f"\n\nConversation history:\n{ctx_text}" if ctx_text else ""

    return (
        f"{header}{obs}\n\n"
        f"Question: {question}\n\n"
        f"Answer concisely in a few words:\nAnswer:"
    )


# ── Scoring ────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_answer(generated: str, gold: str) -> int:
    """1 if normalized gold answer is a substring of normalized generated text."""
    gen_n = _normalize(generated)
    gold_n = _normalize(gold)
    if not gold_n:
        return 0
    return int(gold_n in gen_n)


# ── Phase 1: Summarization ─────────────────────────────────────────────────

def _build_sum_prompt(history, instruction):
    full_text = _sessions_to_text(history["sessions"], history["dates"])
    return (
        f"{instruction}\n\n"
        f"Conversation history:\n{full_text}\n\n"
        f"Summary:"
    )


def summarize_all(histories, llm, llm_tok, summaries_path: Path, budget_key: str):
    """Generate summaries for all conversations. Resumes from summaries_path."""
    instruction = _SUM_INSTR[budget_key]
    max_new = _SUM_MAX_NEW_TOKENS[budget_key]
    cache = _load_json(summaries_path) or {}

    todo = [cid for cid in histories if cid not in cache]
    if not todo:
        print(f"  Summary cache ({budget_key}): all {len(cache)} conversations done.")
        return cache

    print(f"  Summary cache ({budget_key}): {len(cache)} done, {len(todo)} remaining.")

    for i, conv_id in enumerate(todo):
        history = histories[conv_id]
        prompt = _build_sum_prompt(history, instruction)

        # Use chat template for better instruction following
        formatted = llm_tok.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False, add_generation_prompt=True,
        )
        inputs = llm_tok(formatted, return_tensors="pt").to(llm.device)
        prompt_toks = inputs["input_ids"].shape[1]

        with torch.no_grad():
            out = llm.generate(
                **inputs, max_new_tokens=max_new, do_sample=False,
                pad_token_id=llm_tok.eos_token_id,
            )
        gen_ids = out[:, prompt_toks:]
        text = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
        cache[conv_id] = text
        _save_json(summaries_path, cache)

        print(f"  [{i+1}/{len(todo)}] {conv_id} ({budget_key}, {prompt_toks} tok in, "
              f"{gen_ids.shape[1]} tok out): {text[:80]!r}")

    return cache


# ── Phase 2: Scoring ───────────────────────────────────────────────────────

def score_all(questions, histories, sums80, sums200, llm, llm_tok,
              checkpoint_per_q: list, save_cb=None):
    """Score all conditions for all questions. Returns per-question records."""
    done_uids = {r["q_uid"] for r in checkpoint_per_q}
    remaining = [q for q in questions if q["q_uid"] not in done_uids]
    per_question = list(checkpoint_per_q)

    if not remaining:
        print("  All questions already scored (loaded from checkpoint).")
        return per_question

    offset = len(per_question)
    print(f"  Scoring {len(remaining)} questions "
          f"({offset} already done, {len(questions)} total).")

    for qi_local, q in enumerate(remaining):
        qi_global = offset + qi_local
        uid = q["q_uid"]
        conv_id = q["conv_id"]
        history = histories[conv_id]
        gold = q["gold_answer"]
        shuffle_seed = SHUFFLE_SEED + qi_global

        sum80 = sums80.get(conv_id, "")
        sum200 = sums200.get(conv_id, "")

        cond_recs = {}
        for cond in CONDITIONS:
            raw_prompt = build_locomo_prompt(
                cond, history, sum80, sum200, q["question"],
                shuffle_seed=shuffle_seed,
            )

            formatted = llm_tok.apply_chat_template(
                [{"role": "user", "content": raw_prompt}],
                tokenize=False, add_generation_prompt=True,
            )
            inputs = llm_tok(formatted, return_tensors="pt").to(llm.device)
            prompt_len = int(inputs["input_ids"].shape[1])

            # TTFT via 1-token prefill
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                llm.generate(**inputs, max_new_tokens=1, do_sample=False,
                              pad_token_id=llm_tok.eos_token_id)
            torch.cuda.synchronize()
            prefill_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Full generation
            with torch.no_grad():
                out = llm.generate(**inputs, max_new_tokens=64, do_sample=False,
                                   pad_token_id=llm_tok.eos_token_id)
            gen_ids = out[:, prompt_len:]
            response = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
            correct = score_answer(response, gold)

            cond_recs[cond] = {
                "pred": response[:120],   # truncated for storage
                "correct": correct,
                "prefill_ms": prefill_ms,
                "prompt_tokens": prompt_len,
            }

        per_question.append({
            "q_uid": uid,
            "conv_id": conv_id,
            "gold": gold,
            "category": q["category"],
            "evidence": q["evidence"],
            "conditions": cond_recs,
        })

        n_done = qi_local + 1
        if n_done % 5 == 0 or n_done == 1 or n_done == len(remaining):
            rpt = "  ".join(
                f"{c}={cond_recs[c]['correct']}" for c in CONDITIONS
            )
            print(f"  [{offset + n_done}/{len(questions)}] {uid}  {rpt}")
            print(f"    gold={gold!r}  full_pred={cond_recs['full']['pred'][:60]!r}")

        if save_cb:
            save_cb(per_question)

    return per_question


# ── Statistics ─────────────────────────────────────────────────────────────

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
                             "mean_prefill_ms": 0.0, "mean_prompt_tokens": 0.0, "n": 0}
            continue
        acc = sum(r["correct"] for r in recs) / n
        ci_lo, ci_hi = wilson_ci(acc, n)
        ms_vals = [r["prefill_ms"] for r in recs]
        ms_mean = sum(ms_vals) / n
        summary[cond] = {
            "accuracy": round(acc, 4),
            "ci_lo": ci_lo, "ci_hi": ci_hi,
            "mean_prefill_ms": round(ms_mean, 1),
            "mean_prompt_tokens": round(
                sum(r["prompt_tokens"] for r in recs) / n, 1),
            "n": n,
        }

    correct_by_uid = {
        q["q_uid"]: {c: q["conditions"][c]["correct"]
                     for c in conditions if c in q.get("conditions", {})}
        for q in per_question
    }

    significance = {}
    for cond_a, cond_b in mcnemar_pairs:
        b = c = 0
        for uid, cv in correct_by_uid.items():
            if cond_a not in cv or cond_b not in cv:
                continue
            if cv[cond_a] == 1 and cv[cond_b] == 0:
                b += 1
            elif cv[cond_a] == 0 and cv[cond_b] == 1:
                c += 1
        key = f"{cond_a}_vs_{cond_b}".replace("-", "_")
        significance[key] = {
            "cond_a": cond_a, "cond_b": cond_b,
            "b": b, "c": c,
            "mcnemar_p": mcnemar_p(b, c),
            "delta_accuracy": round(
                summary.get(cond_a, {}).get("accuracy", 0)
                - summary.get(cond_b, {}).get("accuracy", 0), 4),
        }
    return summary, significance


def render_table(summary, conditions, n_questions):
    lines = [
        "=" * 90,
        f"LOCOMO REPRESENTATION FRONTIER — {n_questions} QUESTIONS",
        "=" * 90,
        f"{'condition':<14} {'acc':>7} {'95% CI':>14} {'prefill ms':>12} {'tok':>8} {'n':>6}",
        "-" * 90,
    ]
    for cond in conditions:
        s = summary.get(cond, {})
        if not s or s.get("n", 0) == 0:
            continue
        ci = f"[{s['ci_lo']:.3f},{s['ci_hi']:.3f}]"
        lines.append(
            f"{cond:<14} {s['accuracy']:>7.3f} {ci:>14} "
            f"{s['mean_prefill_ms']:>12.1f} {s['mean_prompt_tokens']:>8.1f} {s['n']:>6}"
        )
    lines.append("-" * 90)
    return "\n".join(lines)


def render_significance(significance):
    lines = [
        "",
        "MCNEMAR SIGNIFICANCE (continuity-corrected, two-sided)",
        "-" * 65,
        f"{'pair':<35} {'delta':>7} {'p':>10} {'b':>6} {'c':>6}",
        "-" * 65,
    ]
    for key, s in significance.items():
        pair = f"{s['cond_a']} vs {s['cond_b']}"
        lines.append(
            f"{pair:<35} {s['delta_accuracy']:>+7.3f} "
            f"{s['mcnemar_p']:>10.4f} {s['b']:>6} {s['c']:>6}"
        )
    lines.append("-" * 65)
    return "\n".join(lines)


MCNEMAR_PAIRS = [
    ("full", "blind"),
    ("full", "shuffled"),
    ("full", "stateless"),
    ("summary-80", "full"),
    ("summary-200", "full"),
    ("window-10", "full"),
    ("summary-80", "summary-200"),
]


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="LoCoMo representation frontier: dialogue history compression vs QA accuracy"
    )
    ap.add_argument("--data",   default="data/locomo/locomo10.json")
    ap.add_argument("--model",  default=MODEL_ID)
    ap.add_argument("--category", type=int, default=1,
                    help="QA category to filter (1=single-hop, 2=multi-hop, "
                         "3=temporal, 4=open-domain, 5=adversarial, 0=all). Default: 1.")
    ap.add_argument("--limit",  type=int, default=50,
                    help="Max total questions (0=all). Default: 50 for pilot.")
    ap.add_argument("--per-conv-limit", type=int, default=5,
                    help="Max questions per conversation before global limit. Default: 5.")
    ap.add_argument("--quantization", choices=["bnb", "fp16"], default="fp16")
    ap.add_argument("--sum80-cache",  default="results/locomo_summaries_80.json")
    ap.add_argument("--sum200-cache", default="results/locomo_summaries_200.json")
    ap.add_argument("--output",     default="results/frontier_locomo_qwen7b.json")
    ap.add_argument("--per-q-output",
                    default="results/frontier_locomo_qwen7b_perquestion.json")
    ap.add_argument("--skip-summarization", action="store_true")
    args = ap.parse_args()

    category = args.category if args.category != 0 else None
    out_path   = Path(args.output)
    per_q_path = Path(args.per_q_output)
    for p in [out_path, per_q_path,
              Path(args.sum80_cache), Path(args.sum200_cache)]:
        p.parent.mkdir(parents=True, exist_ok=True)

    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("=" * 72)
    print("LOCOMO REPRESENTATION FRONTIER")
    print(f"  Device : {device}")
    print(f"  Model  : {args.model}")
    print(f"  Category: {CATEGORY_NAMES.get(category, 'all')} (cat={category})")
    print(f"  Limit  : {args.limit or 'all'} questions  (per-conv: {args.per_conv_limit})")
    print()
    print("  SmolLM2-1.7B context limit = 2048 tokens.")
    print("  LoCoMo full histories: 11K-23K tokens.")
    print("  → 'full' condition is infeasible on the edge model (SmolLM2).")
    print("  → Running frontier on Qwen2.5-7B (32K ctx) only.")
    print("=" * 72)

    # ── Load data ──────────────────────────────────────────────────────────
    data_path = Path(args.data)
    questions, histories = load_locomo(
        data_path,
        category=category,
        limit=args.limit,
        per_conv_limit=args.per_conv_limit,
    )
    print(f"\nLoaded {len(questions)} questions from {len(histories)} conversations.")
    cat_dist = {}
    for q in questions:
        cat_dist[q["category"]] = cat_dist.get(q["category"], 0) + 1
    print(f"Category distribution: {cat_dist}")

    # Print token range for full condition
    tok_sizes = []
    for cid, h in histories.items():
        full_text = _sessions_to_text(h["sessions"], h["dates"])
        approx_tok = int(len(full_text.split()) / 0.75)
        tok_sizes.append(approx_tok)
    print(f"Full history token range: {min(tok_sizes):,} - {max(tok_sizes):,} "
          f"(mean {sum(tok_sizes)//len(tok_sizes):,}) — all fit Qwen2.5-7B 32K")

    # ── Load model ─────────────────────────────────────────────────────────
    print(f"\nLoading {args.model}...")
    from context_inertia import load_llm
    llm, llm_tok = load_llm(args.model, args.quantization)

    # ── Phase 1: Summarization ─────────────────────────────────────────────
    print("\n── Phase 1: Summarization ─────────────────────────────────────────")
    if args.skip_summarization:
        sums80  = _load_json(Path(args.sum80_cache))  or {}
        sums200 = _load_json(Path(args.sum200_cache)) or {}
        print(f"  Skipped: {len(sums80)} sum80, {len(sums200)} sum200 loaded from cache.")
    else:
        sums80  = summarize_all(histories, llm, llm_tok,
                                Path(args.sum80_cache),  "summary-80")
        sums200 = summarize_all(histories, llm, llm_tok,
                                Path(args.sum200_cache), "summary-200")

    # ── Phase 2: Scoring ───────────────────────────────────────────────────
    print("\n── Phase 2: Scoring ───────────────────────────────────────────────")
    checkpoint_per_q = _load_json(per_q_path) or []
    if checkpoint_per_q:
        print(f"  Checkpoint: {len(checkpoint_per_q)} questions already scored.")

    meta = {
        "model": MODEL_SLUG,
        "llm": args.model,
        "quantization": args.quantization,
        "category_filter": category,
        "n_questions_requested": len(questions),
        "conditions": CONDITIONS,
        "device": device,
        "timestamp_start": datetime.now().isoformat(),
        "smollm2_full_infeasible": True,
        "smollm2_context_limit_tokens": 2048,
        "locomo_full_history_token_range": [min(tok_sizes), max(tok_sizes)],
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

    per_question = score_all(
        questions, histories, sums80, sums200,
        llm, llm_tok,
        checkpoint_per_q,
        save_cb=_save,
    )

    del llm, llm_tok
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ── Final statistics ───────────────────────────────────────────────────
    print("\n── Computing statistics ────────────────────────────────────────────")
    summary, significance = compute_statistics(per_question, CONDITIONS, MCNEMAR_PAIRS)

    prov = stamp(
        script="frontier_locomo.py",
        model=MODEL_SLUG,
        device=device.lower().replace(" ", "_"),
        n=len(per_question),
        args=args,
    )

    _save_json(per_q_path, per_question)
    _save_json(out_path, {
        "metadata": {
            **meta,
            "n_questions_scored": len(per_question),
            "timestamp_end": datetime.now().isoformat(),
        },
        "summary": summary,
        "significance": significance,
        "per_question_path": str(per_q_path),
        "_provenance": prov,
    })

    print("\n" + render_table(summary, CONDITIONS, len(per_question)))
    print(render_significance(significance))

    # Key diagnostic: summary vs full gap
    full_acc   = summary.get("full",        {}).get("accuracy", float("nan"))
    sum80_acc  = summary.get("summary-80",  {}).get("accuracy", float("nan"))
    sum200_acc = summary.get("summary-200", {}).get("accuracy", float("nan"))
    blind_acc  = summary.get("blind",       {}).get("accuracy", float("nan"))

    print(f"\nKEY GAP: summary-80 vs full = {sum80_acc - full_acc:+.3f}")
    print(f"KEY GAP: summary-200 vs full = {sum200_acc - full_acc:+.3f}")
    print(f"Blind baseline: {blind_acc:.3f}  Full: {full_acc:.3f}")
    if sum80_acc < full_acc - 0.05:
        print("VERDICT: INCOMPRESSIBLE — summary collapses vs full (gap > 5pp).")
    elif abs(sum80_acc - full_acc) <= 0.05:
        print("VERDICT: COMPRESSIBLE — summary ≈ full (gap ≤ 5pp), like EgoSchema.")
    else:
        print("VERDICT: AMBIGUOUS — summary above full (leakage or scoring artifact).")

    print(f"\nResults written to {out_path}")
    print(f"Per-question data: {per_q_path}")


if __name__ == "__main__":
    main()
