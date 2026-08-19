"""
Experiment 9: Representation Sweep (additive extension of Exp 7)
=================================================================
Adds new *representation* conditions to the EgoSchema premise test without
re-running existing conditions or overwriting existing results.

New conditions
--------------
summary   : compress all 16 frame captions into ONE compact paragraph using
            the same LLM (Qwen2.5-7B-Instruct, greedy, do_sample=False) with
            instruction:
              "Summarize these frame-by-frame captions into a concise paragraph
               capturing key events, objects, and actions, in under ~80 tokens."
            Summary cached per clip in results/egoschema_summaries.json.

external  : (optional, --with-external) embed each caption + the question
            with sentence-transformers (all-MiniLM-L6-v2), retrieve top-3
            captions by cosine similarity to the question (in chronological
            order), reason over those 3.
            Requires: pip install sentence-transformers

Both conditions run on the SAME 150 clips used in the exp7 premise run, in the
same order, for direct comparability.

Metrics recorded: accuracy, mean prompt tokens (state size), mean prefill ms.
Prefix caching is effectively disabled (full prompt rebuilt each call,
same as exp7). TTFT is measured via the two-call method from exp5.

Output: results/exp7_representation_sweep.json (ADDITIVE — never overwrites).
Summary cache: results/egoschema_summaries.json (per-clip LLM summaries,
               incrementally written so the run is resumable).

Usage:
    python experiments/exp9_representation_sweep.py

    # also run the retrieval condition:
    python experiments/exp9_representation_sweep.py --with-external

    # smoke test (first 5 questions):
    python experiments/exp9_representation_sweep.py --limit 5

    # skip re-summarizing (summaries already cached):
    python experiments/exp9_representation_sweep.py --skip-summarization
"""

import argparse
import gc
import json
import sys
from datetime import datetime
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from premise_egoschema import (
    LETTERS,
    _load_caption_cache,
    _save_caption_cache,
    build_egoschema_prompt,
    load_egoschema,
    parse_choice,
)

# Baseline conditions pulled from exp7 for the comparison table (not re-run).
EXP7_REFERENCE_CONDITIONS = ["blind", "stateless", "full"]

SUMMARIZE_INSTRUCTION = (
    "Summarize these frame-by-frame captions into a concise paragraph "
    "capturing key events, objects, and actions, in under ~80 tokens."
)


# ── Summary generation ──────────────────────────────────────────────────

def _build_summarize_prompt(captions):
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(captions))
    return (
        f"{SUMMARIZE_INSTRUCTION}\n\n"
        f"Frame captions:\n{numbered}\n\n"
        "Summary:"
    )


def generate_summaries(q_uids, captions, llm, llm_tok, summaries_path):
    """Generate one compact summary per clip using the already-loaded LLM.

    Skips clips already in the cache; persists after each clip.
    Returns updated summaries dict {q_uid: str}.
    """
    summaries = _load_caption_cache(summaries_path)
    todo = [uid for uid in q_uids if uid not in summaries]
    if not todo:
        print(f"Summary cache: all {len(summaries)} clips already done.")
        return summaries
    print(f"Summary cache: {len(summaries)} done, {len(todo)} to generate.")

    for i, uid in enumerate(todo):
        caps = captions.get(uid, [])
        if not caps:
            summaries[uid] = ""
            _save_caption_cache(summaries_path, summaries)
            continue
        prompt = _build_summarize_prompt(caps)
        inputs = llm_tok(prompt, return_tensors="pt").to(llm.device)
        with torch.no_grad():
            out = llm.generate(
                **inputs,
                max_new_tokens=120,
                do_sample=False,
                pad_token_id=llm_tok.pad_token_id,
            )
        gen_ids = out[:, inputs["input_ids"].shape[1]:]
        text = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
        summaries[uid] = text
        _save_caption_cache(summaries_path, summaries)
        if (i + 1) % 10 == 0 or i == 0 or i == len(todo) - 1:
            print(f"  [{i+1}/{len(todo)}] {uid}: {text[:90]!r}")

    return summaries


# ── External (retrieval) condition ──────────────────────────────────────

def load_retrieval_model():
    """Load sentence-transformers model for the external condition."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise SystemExit(
            "sentence-transformers is required for --with-external.\n"
            "Install it with: pip install sentence-transformers"
        )
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model


def retrieve_top_k(question, captions, ret_model, k=3):
    """Return top-k captions most relevant to the question (cosine sim),
    in chronological order."""
    import numpy as np

    if not captions:
        return []
    texts = captions + [question]
    embs = ret_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    cap_embs = embs[:-1]
    q_emb = embs[-1]
    scores = cap_embs @ q_emb
    top_idx = sorted(np.argsort(scores)[::-1][:k].tolist())
    return [captions[i] for i in top_idx]


# ── Prompt builder for new representation conditions ────────────────────

def build_repr_prompt(mode, captions, summary_text, question, options, ret_model=None):
    """Build the MC prompt for a new representation condition."""
    header = (
        "You are answering a multiple-choice question about a first-person "
        "(egocentric) video. Below are text descriptions of the video, "
        "followed by a question and five options."
    )
    opt_block = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))
    instr = (
        "\n\nSelect the single best answer. Respond with ONLY the letter "
        "(A, B, C, D, or E)."
    )

    if mode == "summary":
        ctx = summary_text or ""
        obs = f"\n\nVideo summary:\n{ctx}" if ctx else "\n\n(No summary available.)"
    elif mode == "external":
        sel = retrieve_top_k(question, captions, ret_model, k=3)
        if sel:
            lines = "\n".join(f"{i+1}. {c}" for i, c in enumerate(sel))
            obs = (
                "\n\nMost relevant frame descriptions "
                "(top-3 retrieved by question relevance, chronological order):\n"
                + lines
            )
        else:
            obs = "\n\n(No frame descriptions available.)"
    else:
        raise ValueError(f"unknown representation condition: {mode}")

    return (
        f"{header}{obs}\n\n"
        f"Question: {question}\n\n"
        f"Options:\n{opt_block}{instr}\nAnswer:"
    )


# ── Scoring sweep ────────────────────────────────────────────────────────

def score_repr_conditions(questions, captions, summaries, llm, llm_tok,
                          llm_max_tokens, conditions, ret_model=None, save_cb=None):
    """Sweep new representation conditions over the 150 questions.
    Returns per_question list (same schema as exp7)."""
    import time

    per_question = []
    for qi, q in enumerate(questions):
        uid = q["q_uid"]
        caps = captions.get(uid, [])
        summary_text = summaries.get(uid, "") if summaries is not None else ""
        gold_letter = LETTERS[q["gold_idx"]]
        cond_recs = {}

        for cond in conditions:
            prompt = build_repr_prompt(
                cond, caps, summary_text,
                q["question"], q["options"],
                ret_model=ret_model,
            )
            inputs = llm_tok(prompt, return_tensors="pt", padding=True).to(llm.device)
            prompt_len = inputs["input_ids"].shape[1]

            # Two-call TTFT (matches exp5 / exp7 timing methodology exactly).
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                _ = llm.generate(
                    **inputs, max_new_tokens=1, do_sample=False,
                    pad_token_id=llm_tok.pad_token_id,
                )
            torch.cuda.synchronize()
            prefill_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Full generation (for the actual answer).
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                out = llm.generate(
                    **inputs, max_new_tokens=llm_max_tokens, do_sample=False,
                    pad_token_id=llm_tok.pad_token_id,
                )
            torch.cuda.synchronize()

            gen_ids = out[:, prompt_len:]
            response = llm_tok.decode(gen_ids[0], skip_special_tokens=True).strip()
            pred = parse_choice(response)
            cond_recs[cond] = {
                "pred": pred,
                "correct": int(pred == gold_letter),
                "prefill_ms": prefill_ms,
                "prompt_tokens": int(prompt_len),
            }

        per_question.append({
            "q_uid": uid,
            "gold": gold_letter,
            "n_captions": len(caps),
            "conditions": cond_recs,
        })
        if (qi + 1) % 10 == 0 or qi == 0 or qi == len(questions) - 1:
            rpt = "  ".join(f"{c}={cond_recs[c]['correct']}" for c in conditions)
            print(f"  [{qi+1}/{len(questions)}] {uid} gold={gold_letter}  {rpt}")
        if save_cb:
            save_cb(per_question)

    return per_question


# ── Aggregation + comparison table ──────────────────────────────────────

def aggregate(per_question, conditions):
    summary = {}
    for cond in conditions:
        recs = [q["conditions"][cond] for q in per_question
                if cond in q.get("conditions", {})]
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


def render_table(repr_summary, exp7_summary, conditions):
    """Side-by-side table: exp7 reference conditions + new representation conditions."""
    ref_display = [("blind (exp7)", exp7_summary.get("blind", {})),
                   ("stateless (exp7)", exp7_summary.get("stateless", {})),
                   ("full (exp7)", exp7_summary.get("full", {}))]
    new_display = [(c, repr_summary.get(c, {})) for c in conditions]
    rows = ref_display + new_display

    lines = [
        "=" * 76,
        "REPRESENTATION SWEEP — COMPARISON TABLE",
        "=" * 76,
        f"{'condition':<22} {'accuracy':>10} {'prefill ms':>12} {'prompt tok':>12} {'n':>6}",
        "-" * 76,
    ]
    for label, s in rows:
        if not s:
            continue
        lines.append(
            f"{label:<22} {s.get('accuracy', 0):>10.3f} "
            f"{s.get('mean_prefill_ms', 0):>12.1f} "
            f"{s.get('mean_prompt_tokens', 0):>12.1f} "
            f"{s.get('n', 0):>6}"
        )
    lines.append("-" * 76)
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Exp 9: Representation sweep (additive ext of Exp 7)")
    ap.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"],
                    default="fp16")
    ap.add_argument("--questions",       default="data/egoschema/questions.json")
    ap.add_argument("--answers",         default="data/egoschema/subset_answers.json")
    ap.add_argument("--captions-cache",  default="results/captions_cache.json")
    ap.add_argument("--summaries-cache", default="results/summaries_cache_80.json")
    ap.add_argument("--premise-results", default="results/premise_qwen7b_n150.json",
                    help="Exp7 results — used to get the canonical 150 q_uid order "
                         "and reference summary stats.")
    ap.add_argument("--output", default="results/representation_sweep_qwen7b_n150.json")
    ap.add_argument("--llm-max-tokens", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0,
                    help="Only first K questions (0 = all 150 from premise run).")
    ap.add_argument("--with-external", action="store_true",
                    help="Also run the retrieval-based 'external' condition "
                         "(requires: pip install sentence-transformers).")
    ap.add_argument("--skip-summarization", action="store_true",
                    help="Skip summary generation — load existing summaries cache.")
    args = ap.parse_args()

    conditions = ["summary"]
    if args.with_external:
        conditions.append("external")

    # ── Load premise results to get the canonical q_uid order + baseline stats ──
    premise_path = Path(args.premise_results)
    if not premise_path.exists():
        raise SystemExit(f"Premise results not found: {premise_path}")
    premise_data = json.loads(premise_path.read_text())
    premise_q_uids = [q["q_uid"] for q in premise_data["per_question"]]
    exp7_summary = premise_data.get("summary", {})
    print(f"Loaded premise run: {len(premise_q_uids)} q_uids from {premise_path}")

    # ── Load caption cache ───────────────────────────────────────────────
    captions = _load_caption_cache(Path(args.captions_cache))
    if not captions:
        raise SystemExit(f"Caption cache empty or missing: {args.captions_cache}")
    print(f"Caption cache: {len(captions)} clips")

    # ── Reconstruct ordered question list from the premise run ───────────
    all_questions = load_egoschema(Path(args.questions), Path(args.answers))
    q_by_uid = {q["q_uid"]: q for q in all_questions}
    questions = [q_by_uid[uid] for uid in premise_q_uids if uid in q_by_uid]
    if args.limit:
        questions = questions[: args.limit]
    print(f"Scoring {len(questions)} questions (same order as exp7 premise run)")

    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}   LLM: {args.llm}   Conditions: {conditions}")

    # ── Load LLM once for both summarization and scoring ─────────────────
    from context_inertia import load_llm

    print("\nLoading LLM...")
    llm, llm_tok = load_llm(args.llm, args.quantization)

    # ── Phase 1: generate summaries (if needed) ───────────────────────────
    summaries = None
    summaries_path = Path(args.summaries_cache)
    if "summary" in conditions:
        summaries_path.parent.mkdir(parents=True, exist_ok=True)
        if args.skip_summarization:
            summaries = _load_caption_cache(summaries_path)
            if not summaries:
                raise SystemExit(
                    f"--skip-summarization set but cache missing: {summaries_path}"
                )
            print(f"Skipping summarization — loaded {len(summaries)} summaries.")
        else:
            print("\n── Phase 1: Summarization ──────────────────────────────")
            q_uids_to_summarize = [q["q_uid"] for q in questions]
            summaries = generate_summaries(
                q_uids_to_summarize, captions, llm, llm_tok, summaries_path
            )

    # ── Load retrieval model if needed ────────────────────────────────────
    ret_model = None
    if "external" in conditions:
        print("\nLoading retrieval model (all-MiniLM-L6-v2)...")
        ret_model = load_retrieval_model()

    # ── Phase 2: score new conditions ─────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "exp": "exp9_representation_sweep",
        "extends": str(premise_path),
        "device": device,
        "llm": args.llm,
        "quantization": args.quantization,
        "n_questions": len(questions),
        "conditions": conditions,
        "captions_cache": args.captions_cache,
        "summaries_cache": str(summaries_path) if summaries is not None else None,
        "timestamp_start": datetime.now().isoformat(),
    }

    def _save(per):
        out_path.write_text(json.dumps({
            "metadata": {**meta, "timestamp_last_save": datetime.now().isoformat()},
            "per_question": per,
            "summary": aggregate(per, conditions),
            "exp7_summary_reference": exp7_summary,
        }, indent=2))

    print("\n── Phase 2: Scoring ──────────────────────────────────────")
    per_question = score_repr_conditions(
        questions, captions, summaries, llm, llm_tok,
        args.llm_max_tokens, conditions,
        ret_model=ret_model, save_cb=_save,
    )

    del llm, llm_tok
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ── Final save + table ────────────────────────────────────────────────
    repr_summary = aggregate(per_question, conditions)
    out_path.write_text(json.dumps({
        "metadata": {**meta, "timestamp_end": datetime.now().isoformat()},
        "per_question": per_question,
        "summary": repr_summary,
        "exp7_summary_reference": exp7_summary,
    }, indent=2))

    print("\n" + render_table(repr_summary, exp7_summary, conditions))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
