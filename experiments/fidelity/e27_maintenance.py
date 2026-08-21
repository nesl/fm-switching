"""
E27: Maintenance-mechanism kill test.

Tests whether the ~80x lifecycle-cost inversion (window ~0.98s vs sum200 ~78s at L=32k,
found in E24c) survives recursive/incremental summarization. If recursive mode reduces
refresh input from ~32k tokens to ~1-2k tokens, the lifecycle cost ratio narrows to ~24x
(still substantial but not 80x). Quality impact under recursive compression is the kill test.

Maintenance modes:
  full_regen   — summarize entire history from scratch at every checkpoint
  recursive    — summarize [previous_summary + new sessions] at every checkpoint
  periodic_2   — full_regen every 2 sessions; use previous summary otherwise
  periodic_5   — full_regen every 5 sessions; use previous summary otherwise
  periodic_10  — full_regen every 10 sessions; use previous summary otherwise

Budgets: sum80, sum200

Checkpoints: 25%, 50%, 75%, 100% of session count

Workloads:
  LoCoMo (n=100 phase0a questions): dense-incompressible; quality test is meaningful
  EgoSchema (n=60 phase0a clips): gist-compressible; lifecycle cost analysis only

Output:
  results/fidelity/e27_maintenance/e27_maintenance_qwen7b.json
  results/fidelity/e27_maintenance/per_step/ (per-conversation step data)
  results/fidelity/e27_maintenance/quality/ (per-checkpoint accuracy)
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")

import torch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

DATA_LOCOMO   = ROOT / "data" / "locomo" / "locomo10.json"
DATA_EGO_Q    = ROOT / "data" / "egoschema" / "questions.json"
DATA_EGO_ANS  = ROOT / "data" / "egoschema" / "subset_answers.json"
CAPS_CACHE    = ROOT / "results" / "fidelity" / "caches" / "captions_cache.json"
SUBSET_LOCOMO = ROOT / "data" / "audit_subsets" / "phase0a" / "locomo_100.json"
SUBSET_EGO    = ROOT / "data" / "audit_subsets" / "phase0a" / "egoschema_60.json"
OUT_DIR       = ROOT / "results" / "fidelity" / "e27_maintenance"

MODEL_ID   = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG = "qwen7b"

CHECKPOINT_FRACS = [0.25, 0.50, 0.75, 1.0]
MODES   = ["full_regen", "recursive", "periodic_2", "periodic_5", "periodic_10"]
BUDGETS = ["sum80", "sum200"]

# Cold-prefill cost table (a6000), in seconds — from cost_matrix.csv
_A6K_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_A6K_S = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]

# Phase0a reference accuracy (E13, LoCoMo n=282 cat=1)
SANITY_REF = {"sum80": 0.099, "sum200": 0.099, "tol": 0.05}

# LoCoMo summarizer prompts (identical to frontier_locomo.py)
_LOCOMO_SUM_INSTR = {
    "sum80": (
        "Summarize this conversation history between two people into a concise paragraph "
        "capturing key events, facts, relationships, and dates, in under ~80 tokens."
    ),
    "sum200": (
        "Summarize this conversation history between two people into a detailed paragraph "
        "capturing all key events, facts, relationships, dates, and context, "
        "in under ~200 tokens."
    ),
}
_LOCOMO_SUM_MAX_NEW = {"sum80": 120, "sum200": 300}

# EgoSchema summarizer prompts
_EGO_SUM_INSTR = {
    "sum80": (
        "Summarize these video scene captions into a concise description (under ~80 tokens) "
        "capturing the key activity, setting, objects involved, and sequence of events."
    ),
    "sum200": (
        "Summarize these video scene captions into a detailed description (under ~200 tokens) "
        "capturing the key activity, setting, objects involved, sequence of events, "
        "and any notable interactions or outcomes."
    ),
}
_EGO_SUM_MAX_NEW = {"sum80": 120, "sum200": 300}

# QA prompts
_LOCOMO_QA_PROMPT = (
    "The following is a conversation history between two people.\n\n"
    "{context}\n\n"
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
_LOCOMO_BLIND_PROMPT = (
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
_EGO_QA_PROMPT = (
    "Based on the following video description, answer the question.\n\n"
    "Video: {context}\n\n"
    "Question: {question}\n"
    "Options:\n{options}\n"
    "Answer with the letter of the correct option (A/B/C/D/E). Answer:"
)

_JUDGE_PROMPT = (
    "Is '{pred}' a correct or semantically equivalent answer to '{gold}'?\n"
    "Reply YES or NO only."
)


# ── Cost table interpolation ──────────────────────────────────────────────────

def cold_prefill_s(n_tokens: int) -> float:
    """Interpolate cold-prefill cost (seconds) from a6000 cost table."""
    if n_tokens <= _A6K_L[0]:
        return _A6K_S[0]
    if n_tokens >= _A6K_L[-1]:
        slope = (_A6K_S[-1] - _A6K_S[-2]) / (_A6K_L[-1] - _A6K_L[-2])
        return _A6K_S[-1] + slope * (n_tokens - _A6K_L[-1])
    import bisect
    idx = bisect.bisect_right(_A6K_L, n_tokens)
    L0, L1 = _A6K_L[idx-1], _A6K_L[idx]
    t0, t1 = _A6K_S[idx-1], _A6K_S[idx]
    return t0 + (t1 - t0) * (n_tokens - L0) / (L1 - L0)


# ── Model helpers ─────────────────────────────────────────────────────────────

def load_model(device="cuda"):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading {MODEL_ID} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.float16, device_map=device)
    model.eval()
    return model, tok


def _run(model, tok, prompt: str, max_new: int = 40) -> str:
    fmt = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True)
    inp = tok(fmt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inp, max_new_tokens=max_new, do_sample=False,
            pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inp["input_ids"].shape[1]:],
                      skip_special_tokens=True).strip()


def _count_tokens(tok, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False))


# ── Text normalization ────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).lower().strip())


# ── LoCoMo data loading ───────────────────────────────────────────────────────

def load_locomo():
    raw = json.loads(DATA_LOCOMO.read_text())
    convs = {}
    all_questions = {}  # q_uid → {question, gold, conv_id, evidence}

    for item in raw:
        cid = item["sample_id"]
        conv = item["conversation"]
        sessions, dates = [], []
        i = 1
        while f"session_{i}" in conv:
            turns = conv[f"session_{i}"]
            if turns:
                sessions.append(turns)
                dates.append(conv.get(f"session_{i}_date_time", ""))
            i += 1
        convs[cid] = {"sessions": sessions, "dates": dates}

        for qi, qa in enumerate(item["qa"]):
            if qa["category"] != 1:
                continue
            uid = f"{cid}_q{qi:04d}"
            all_questions[uid] = {
                "q_uid": uid, "conv_id": cid,
                "question": qa["question"],
                "gold": str(qa["answer"]),
                "evidence": qa.get("evidence", []),
            }

    return convs, all_questions


def sessions_to_text(sessions, dates, k: int) -> str:
    """Render sessions 1..k as text block."""
    lines = []
    for si in range(k):
        date_label = dates[si] if si < len(dates) else ""
        hdr = f"[Session {si+1}" + (f" — {date_label}]" if date_label else "]")
        lines.append(hdr)
        for t in sessions[si]:
            lines.append(f"{t['speaker']}: {t['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def evidence_max_session(evidence: list) -> int:
    """Return max session number referenced in evidence list (1-indexed). 0 if empty."""
    max_s = 0
    for e in evidence:
        m = re.match(r"D(\d+):", e)
        if m:
            max_s = max(max_s, int(m.group(1)))
    return max_s


def checkpoint_indices(n_sessions: int) -> list:
    """Checkpoint session counts at 25/50/75/100% of n_sessions."""
    return [max(1, round(n_sessions * f)) for f in CHECKPOINT_FRACS]


# ── Summarization ─────────────────────────────────────────────────────────────

def summarize(model, tok, text: str, budget: str, workload: str,
              prev_summary: str = None, new_text: str = None,
              is_recursive: bool = False) -> dict:
    """
    Generate a summary. Returns dict with text, input_tokens, output_tokens, latency_s.

    For recursive mode: input = [prev_summary + new_text]
    For full_regen: input = text (full history)
    """
    if workload == "locomo":
        instr = _LOCOMO_SUM_INSTR[budget]
        max_new = _LOCOMO_SUM_MAX_NEW[budget]
        if is_recursive and prev_summary:
            context = f"Previous summary:\n{prev_summary}\n\nNew sessions:\n{new_text}"
            prompt = f"{instr}\n\n{context}"
        else:
            prompt = f"{instr}\n\n{text}"
    else:  # egoschema
        instr = _EGO_SUM_INSTR[budget]
        max_new = _EGO_SUM_MAX_NEW[budget]
        if is_recursive and prev_summary:
            context = f"Previous summary:\n{prev_summary}\n\nNew captions:\n{new_text}"
            prompt = f"{instr}\n\n{context}"
        else:
            prompt = f"{instr}\n\n{text}"

    input_tokens = _count_tokens(tok, prompt)
    t0 = time.perf_counter()
    summary_text = _run(model, tok, prompt, max_new=max_new)
    latency_s = time.perf_counter() - t0
    output_tokens = _count_tokens(tok, summary_text)

    return {
        "text": summary_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_s": round(latency_s, 4),
    }


def build_summaries_for_conv(model, tok, conv_id: str, sessions: list, dates: list,
                              checkpoints: list, workload: str = "locomo") -> dict:
    """
    Build summaries for all modes × budgets at each checkpoint.
    Returns nested dict: mode → budget → [list of checkpoint dicts]
    """
    n = len(sessions)
    result = {mode: {budget: [] for budget in BUDGETS} for mode in MODES}

    for budget in BUDGETS:
        # State for recursive mode: carry forward previous summary
        recursive_prev = None
        recursive_prev_cp = 0  # sessions covered by previous summary

        # State for periodic modes
        periodic_prev = {K: None for K in [2, 5, 10]}
        periodic_last_regen = {K: 0 for K in [2, 5, 10]}  # session count at last regen

        for cp_idx, cp_k in enumerate(checkpoints):
            full_text = sessions_to_text(sessions, dates, cp_k)

            # --- full_regen ---
            fr = summarize(model, tok, full_text, budget, workload)
            fr["checkpoint_k"] = cp_k
            fr["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
            result["full_regen"][budget].append(fr)

            # --- recursive ---
            if recursive_prev is None:
                # First checkpoint: same as full_regen
                rec = summarize(model, tok, full_text, budget, workload)
            else:
                # Input = [prev summary + new sessions since last checkpoint]
                new_text = sessions_to_text(sessions, dates, cp_k)
                # Strip the sessions already covered by the previous summary
                new_sessions_text = sessions_to_text(
                    sessions[recursive_prev_cp:], dates[recursive_prev_cp:],
                    cp_k - recursive_prev_cp)
                rec = summarize(model, tok, full_text, budget, workload,
                                prev_summary=recursive_prev,
                                new_text=new_sessions_text,
                                is_recursive=True)
            rec["checkpoint_k"] = cp_k
            rec["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
            result["recursive"][budget].append(rec)
            recursive_prev = rec["text"]
            recursive_prev_cp = cp_k

            # --- periodic_K ---
            for K in [2, 5, 10]:
                mode_key = f"periodic_{K}"
                sessions_since_regen = cp_k - periodic_last_regen[K]
                if periodic_prev[K] is None or sessions_since_regen >= K:
                    # Full regen
                    prd = summarize(model, tok, full_text, budget, workload)
                    prd["is_regen"] = True
                    periodic_prev[K] = prd["text"]
                    periodic_last_regen[K] = cp_k
                else:
                    # Reuse previous summary, no new LLM call; cost = 0
                    prd = {
                        "text": periodic_prev[K],
                        "input_tokens": 0,
                        "output_tokens": _count_tokens(tok, periodic_prev[K]),
                        "latency_s": 0.0,
                        "is_regen": False,
                    }
                prd["checkpoint_k"] = cp_k
                prd["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
                result[mode_key][budget].append(prd)

    return result


# ── QA scoring ────────────────────────────────────────────────────────────────

def score_locomo(pred: str, gold: str, model, tok) -> int:
    """Returns 1 if correct, 0 otherwise. LLM judge on substring miss."""
    pn, gn = _normalize(pred), _normalize(gold)
    if gn in pn or pn in gn:
        return 1
    resp = _run(model, tok, _JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4)
    return int(resp.upper().startswith("YES"))


def score_ego(pred: str, correct_letter: str) -> int:
    """EgoSchema: exact match on option letter."""
    m = re.search(r"\b([A-E])\b", pred.upper())
    if m:
        return int(m.group(1) == correct_letter.upper())
    return 0


# ── LoCoMo QA evaluation at a checkpoint ─────────────────────────────────────

def eval_locomo_checkpoint(model, tok, questions_for_conv: list, conv: dict,
                            summaries: dict, checkpoint_k: int,
                            cp_idx: int) -> dict:
    """
    Score all questions whose evidence is fully ≤ checkpoint_k.
    Returns dict: mode → budget → {n, correct, accuracy}
    """
    # Gate questions
    gated = [q for q in questions_for_conv
             if evidence_max_session(q["evidence"]) <= checkpoint_k]
    if not gated:
        return {"n_gated": 0}

    sessions = conv["sessions"]
    dates = conv["dates"]
    results = {"n_gated": len(gated)}

    # Reference: blind, full, window-10 (computed once)
    ref_scores = {"blind": [], "full": [], "window_10": []}

    for q in gated:
        question = q["question"]
        gold = q["gold"]

        # blind
        pred = _run(model, tok, _LOCOMO_BLIND_PROMPT.format(question=question), max_new=40)
        ref_scores["blind"].append(score_locomo(pred, gold, model, tok))

        # full (all sessions up to checkpoint_k)
        full_ctx = sessions_to_text(sessions, dates, checkpoint_k)
        pred = _run(model, tok,
                    _LOCOMO_QA_PROMPT.format(context=full_ctx, question=question),
                    max_new=40)
        ref_scores["full"].append(score_locomo(pred, gold, model, tok))

        # window-10
        win_sessions = sessions[max(0, checkpoint_k-10):checkpoint_k]
        win_dates = dates[max(0, checkpoint_k-10):checkpoint_k]
        win_ctx = sessions_to_text(win_sessions, win_dates, len(win_sessions))
        pred = _run(model, tok,
                    _LOCOMO_QA_PROMPT.format(context=win_ctx, question=question),
                    max_new=40)
        ref_scores["window_10"].append(score_locomo(pred, gold, model, tok))

    for ref_cond, scores in ref_scores.items():
        n = len(scores)
        c = sum(scores)
        results[ref_cond] = {"n": n, "correct": c, "accuracy": c/n if n else None}

    # Summary conditions
    for mode in MODES:
        for budget in BUDGETS:
            cp_data = summaries[mode][budget][cp_idx]
            summary_text = cp_data["text"]
            scores = []
            for q in gated:
                pred = _run(model, tok,
                            _LOCOMO_QA_PROMPT.format(context=summary_text,
                                                      question=q["question"]),
                            max_new=40)
                scores.append(score_locomo(pred, q["gold"], model, tok))
            n, c = len(scores), sum(scores)
            key = f"{mode}_{budget}"
            results[key] = {"n": n, "correct": c, "accuracy": c/n if n else None}

    return results


# ── EgoSchema QA evaluation ───────────────────────────────────────────────────

def eval_ego_checkpoint(model, tok, clip_id: str, q_data: dict, answer_idx: int,
                         captions: list, summaries: dict,
                         checkpoint_k: int, cp_idx: int) -> dict:
    """
    Score a single EgoSchema clip at checkpoint k (k captions visible).
    Returns dict of scores per condition.
    """
    question = q_data["question"]
    options = [q_data[f"option {i}"] for i in range(5)]
    correct_letter = chr(ord("A") + int(answer_idx))

    opts_text = "\n".join(f"{chr(ord('A')+i)}. {opt}" for i, opt in enumerate(options))

    results = {}

    # Reference: blind (no captions)
    blind_prompt = (
        f"Question: {question}\n"
        f"Options:\n{opts_text}\n"
        "Answer with the letter of the correct option (A/B/C/D/E). Answer:"
    )
    pred = _run(model, tok, blind_prompt, max_new=10)
    results["blind"] = score_ego(pred, correct_letter)

    # Reference: full captions up to checkpoint_k
    full_cap_text = "\n".join(f"Caption {i+1}: {c}" for i, c in enumerate(captions[:checkpoint_k]))
    pred = _run(model, tok,
                _EGO_QA_PROMPT.format(context=full_cap_text, question=question, options=opts_text),
                max_new=10)
    results["full"] = score_ego(pred, correct_letter)

    # Summary conditions
    for mode in MODES:
        for budget in BUDGETS:
            cp_data = summaries[mode][budget][cp_idx]
            summary_text = cp_data["text"]
            pred = _run(model, tok,
                        _EGO_QA_PROMPT.format(context=summary_text,
                                               question=question, options=opts_text),
                        max_new=10)
            results[f"{mode}_{budget}"] = score_ego(pred, correct_letter)

    return results


def build_ego_summaries(model, tok, captions: list, checkpoints: list) -> dict:
    """Build summaries for all modes × budgets × checkpoints for one EgoSchema clip."""
    n = len(captions)
    result = {mode: {budget: [] for budget in BUDGETS} for mode in MODES}

    for budget in BUDGETS:
        recursive_prev = None
        recursive_prev_cp = 0
        periodic_prev = {K: None for K in [2, 5, 10]}
        periodic_last_regen = {K: 0 for K in [2, 5, 10]}

        for cp_idx, cp_k in enumerate(checkpoints):
            cap_text = "\n".join(f"Caption {i+1}: {c}"
                                 for i, c in enumerate(captions[:cp_k]))

            # full_regen
            fr = summarize(model, tok, cap_text, budget, "egoschema")
            fr["checkpoint_k"] = cp_k
            fr["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
            result["full_regen"][budget].append(fr)

            # recursive
            if recursive_prev is None:
                rec = summarize(model, tok, cap_text, budget, "egoschema")
            else:
                new_caps = "\n".join(
                    f"Caption {i+1}: {c}"
                    for i, c in enumerate(captions[recursive_prev_cp:cp_k],
                                          start=recursive_prev_cp))
                rec = summarize(model, tok, cap_text, budget, "egoschema",
                                prev_summary=recursive_prev,
                                new_text=new_caps,
                                is_recursive=True)
            rec["checkpoint_k"] = cp_k
            rec["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
            result["recursive"][budget].append(rec)
            recursive_prev = rec["text"]
            recursive_prev_cp = cp_k

            # periodic_K
            for K in [2, 5, 10]:
                mode_key = f"periodic_{K}"
                sessions_since_regen = cp_k - periodic_last_regen[K]
                if periodic_prev[K] is None or sessions_since_regen >= K:
                    prd = summarize(model, tok, cap_text, budget, "egoschema")
                    prd["is_regen"] = True
                    periodic_prev[K] = prd["text"]
                    periodic_last_regen[K] = cp_k
                else:
                    prd = {
                        "text": periodic_prev[K],
                        "input_tokens": 0,
                        "output_tokens": _count_tokens(tok, periodic_prev[K]),
                        "latency_s": 0.0,
                        "is_regen": False,
                    }
                prd["checkpoint_k"] = cp_k
                prd["checkpoint_frac"] = CHECKPOINT_FRACS[cp_idx]
                result[mode_key][budget].append(prd)

    return result


# ── Lifecycle cost analysis ───────────────────────────────────────────────────

def compute_lifecycle_cost(per_conv_step_data: dict, per_clip_step_data: dict) -> dict:
    """
    For each mode × budget, compute:
      - mean input tokens per refresh event
      - estimated refresh latency (cold_prefill_s(mean_input_tokens))
      - ratio vs full_regen
    """
    def _agg(step_data_list):
        agg = defaultdict(lambda: {"input_tokens": [], "latency_s": []})
        for item_data in step_data_list:
            for mode in MODES:
                for budget in BUDGETS:
                    key = f"{mode}_{budget}"
                    for cp in item_data.get("summaries", {}).get(mode, {}).get(budget, []):
                        if cp.get("input_tokens", 0) > 0:
                            agg[key]["input_tokens"].append(cp["input_tokens"])
                            agg[key]["latency_s"].append(cp["latency_s"])
        return agg

    locomo_agg = _agg(per_conv_step_data.values())
    ego_agg = _agg(per_clip_step_data.values())

    def _summarize_agg(agg):
        out = {}
        fr_mean_tok = None
        for key in agg:
            toks = agg[key]["input_tokens"]
            lats = agg[key]["latency_s"]
            mean_tok = sum(toks) / len(toks) if toks else 0
            mean_lat = sum(lats) / len(lats) if lats else 0
            est_lat = cold_prefill_s(int(mean_tok)) if mean_tok > 0 else 0
            out[key] = {
                "n_refresh_events": len(toks),
                "mean_input_tokens": round(mean_tok, 1),
                "mean_measured_latency_s": round(mean_lat, 4),
                "est_refresh_latency_s": round(est_lat, 4),
            }
            if key.startswith("full_regen"):
                fr_mean_tok = mean_tok
        # Compute ratio vs full_regen (same budget)
        for budget in BUDGETS:
            fr_key = f"full_regen_{budget}"
            fr_tok = out.get(fr_key, {}).get("mean_input_tokens", None)
            for mode in MODES:
                key = f"{mode}_{budget}"
                if key in out and fr_tok and fr_tok > 0:
                    out[key]["token_ratio_vs_full_regen"] = round(
                        out[key]["mean_input_tokens"] / fr_tok, 4)
        return out

    return {
        "locomo": _summarize_agg(locomo_agg),
        "egoschema": _summarize_agg(ego_agg),
    }


# ── Sanity check ─────────────────────────────────────────────────────────────

def sanity_check(locomo_accuracy: dict) -> dict:
    """
    Check that full_regen at 100% checkpoint matches phase0a reference (±0.05).
    Reference: sum80=0.099, sum200=0.099.
    """
    cp_100 = 3  # index for 100% checkpoint (CHECKPOINT_FRACS[3] = 1.0)
    results = {}
    for budget in BUDGETS:
        key = f"full_regen_{budget}"
        cp_data = locomo_accuracy.get(cp_100, {}).get(key, {})
        acc = cp_data.get("accuracy")
        ref = SANITY_REF[budget]
        if acc is None:
            results[budget] = {"status": "no_data", "accuracy": None, "reference": ref}
        else:
            diff = abs(acc - ref)
            ok = diff <= SANITY_REF["tol"]
            results[budget] = {
                "status": "pass" if ok else "FAIL",
                "accuracy": round(acc, 4),
                "reference": ref,
                "diff": round(diff, 4),
                "tol": SANITY_REF["tol"],
            }
    return results


# ── Decisions ─────────────────────────────────────────────────────────────────

def classify_outcome(locomo_accuracy: dict, lifecycle: dict) -> str:
    """
    Decision rule (pre-registered):
      A — recursive is cheap (token_ratio < 0.20) AND quality holds (gap ≤ 0.03)
      B — recursive is cheap AND quality drifts (gap > 0.03)
      C — periodic dominates (best periodic < recursive in cost, quality matches)
    """
    cp_100 = 3  # 100% checkpoint index
    gaps = []
    for budget in BUDGETS:
        fr_acc = locomo_accuracy.get(cp_100, {}).get(f"full_regen_{budget}", {}).get("accuracy")
        rec_acc = locomo_accuracy.get(cp_100, {}).get(f"recursive_{budget}", {}).get("accuracy")
        if fr_acc is not None and rec_acc is not None:
            gaps.append(fr_acc - rec_acc)  # positive = recursive degrades

    if not gaps:
        return "unknown"

    max_quality_gap = max(gaps)

    # Token ratio for recursive vs full_regen
    rec_ratio = lifecycle["locomo"].get("recursive_sum200", {}).get("token_ratio_vs_full_regen", 1.0)

    is_cheap = rec_ratio is not None and rec_ratio < 0.20
    quality_holds = max_quality_gap <= 0.03

    if is_cheap and quality_holds:
        return "A"
    if is_cheap and not quality_holds:
        return "B"

    # Check if periodic dominates
    best_periodic_ratio = min(
        lifecycle["locomo"].get(f"periodic_{K}_sum200", {}).get("token_ratio_vs_full_regen", 1.0)
        for K in [2, 5, 10])
    periodic_quality_gap = max(
        (locomo_accuracy.get(cp_100, {}).get(f"full_regen_{budget}", {}).get("accuracy", 0) -
         locomo_accuracy.get(cp_100, {}).get(f"periodic_{K}_{budget}", {}).get("accuracy", 0))
        for K in [2, 5, 10] for budget in BUDGETS)
    if best_periodic_ratio < rec_ratio and periodic_quality_gap <= 0.03:
        return "C"

    return "B"  # recursive cheap but quality drifts, or nothing clearly wins


# ── Save helpers ─────────────────────────────────────────────────────────────

def _save(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Main experiment ───────────────────────────────────────────────────────────

def run_locomo(model, tok, smoke: bool, out_dir: Path) -> tuple:
    """Run LoCoMo maintenance experiment. Returns (per_conv_step, accuracy_by_cp)."""
    convs, all_questions = load_locomo()

    subset = json.loads(SUBSET_LOCOMO.read_text())
    phase0a_ids = set(subset["ids"])

    # Filter phase0a questions
    phase0a_questions = {uid: q for uid, q in all_questions.items() if uid in phase0a_ids}

    # Group by conversation
    by_conv = defaultdict(list)
    for uid, q in phase0a_questions.items():
        by_conv[q["conv_id"]].append(q)

    conv_ids = sorted(by_conv.keys())
    if smoke:
        conv_ids = conv_ids[:2]
        # Trim to 5 questions per conversation for smoke
        by_conv = {cid: qs[:5] for cid, qs in by_conv.items() if cid in conv_ids}
        print(f"SMOKE: 2 convs, up to 5 Q each", flush=True)

    per_conv_step = {}
    accuracy_by_cp = defaultdict(dict)  # cp_idx → {mode_budget: {n, correct, accuracy}}

    for conv_id in conv_ids:
        conv = convs[conv_id]
        sessions, dates = conv["sessions"], conv["dates"]
        n = len(sessions)
        checkpoints = checkpoint_indices(n)

        # Resume: load cached summarization if available
        step_path = out_dir / "per_step" / f"locomo_{conv_id}.json"
        if step_path.exists():
            print(f"\n[LoCoMo] {conv_id}: loading cached summaries ({n} sessions)", flush=True)
            cached = json.loads(step_path.read_text())
            summaries = cached["summaries"]
            per_conv_step[conv_id] = cached
        else:
            print(f"\n[LoCoMo] {conv_id}: {n} sessions, checkpoints={checkpoints}", flush=True)
            t_sum_start = time.perf_counter()
            summaries = build_summaries_for_conv(model, tok, conv_id, sessions, dates,
                                                  checkpoints, workload="locomo")
            t_sum = time.perf_counter() - t_sum_start
            print(f"  Summarization done in {t_sum:.1f}s", flush=True)
            per_conv_step[conv_id] = {
                "n_sessions": n, "checkpoints": checkpoints, "summaries": summaries
            }
            step_path.parent.mkdir(parents=True, exist_ok=True)
            _save(step_path, per_conv_step[conv_id])

        # QA evaluation at each checkpoint (resume: skip if quality file already exists)
        questions = by_conv[conv_id]
        for cp_idx, cp_k in enumerate(checkpoints):
            cp_path = out_dir / "quality" / f"locomo_{conv_id}_cp{cp_idx}.json"

            if cp_path.exists():
                cp_file = json.loads(cp_path.read_text())
                cp_results = cp_file["results"]
                print(f"  Checkpoint {cp_idx+1}/4 (k={cp_k}): loaded from cache", flush=True)
            else:
                print(f"  Checkpoint {cp_idx+1}/4 (k={cp_k}): evaluating {len(questions)} Q...",
                      flush=True)
                cp_results = eval_locomo_checkpoint(
                    model, tok, questions, conv, summaries, cp_k, cp_idx)
                cp_path.parent.mkdir(parents=True, exist_ok=True)
                _save(cp_path, {"conv_id": conv_id, "checkpoint_k": cp_k,
                                 "checkpoint_frac": CHECKPOINT_FRACS[cp_idx],
                                 "results": cp_results})

            # Accumulate accuracy
            n_gated = cp_results.get("n_gated", 0)
            for key, val in cp_results.items():
                if key == "n_gated":
                    continue
                if cp_idx not in accuracy_by_cp:
                    accuracy_by_cp[cp_idx] = defaultdict(lambda: {"n": 0, "correct": 0})
                d = accuracy_by_cp[cp_idx][key]
                d["n"] += val.get("n", 0)
                d["correct"] += val.get("correct", 0)

    # Finalize accuracy
    final_accuracy = {}
    for cp_idx, cond_dict in accuracy_by_cp.items():
        final_accuracy[cp_idx] = {}
        for cond, vals in cond_dict.items():
            n, c = vals["n"], vals["correct"]
            final_accuracy[cp_idx][cond] = {
                "n": n, "correct": c,
                "accuracy": round(c/n, 4) if n > 0 else None,
            }

    return per_conv_step, final_accuracy


def run_egoschema(model, tok, smoke: bool, out_dir: Path) -> tuple:
    """Run EgoSchema maintenance experiment. Returns (per_clip_step, accuracy_by_cp)."""
    caps_cache = json.loads(CAPS_CACHE.read_text())
    # questions.json is a list; build dict keyed by q_uid (= clip UUID)
    ego_questions_list = json.loads(DATA_EGO_Q.read_text())
    ego_questions = {q["q_uid"]: q for q in ego_questions_list}
    ego_answers = json.loads(DATA_EGO_ANS.read_text())  # {clip_uuid: answer_index}
    subset = json.loads(SUBSET_EGO.read_text())
    if isinstance(subset, list):
        clip_ids = subset
    else:
        clip_ids = subset.get("ids", subset.get("clip_ids", []))

    if smoke:
        clip_ids = clip_ids[:2]
        print(f"SMOKE EgoSchema: 2 clips", flush=True)

    EGO_N_CAPS = 16
    EGO_CHECKPOINTS = [4, 8, 12, 16]  # 25/50/75/100% of 16 captions

    per_clip_step = {}
    accuracy_by_cp = defaultdict(lambda: defaultdict(lambda: {"n": 0, "correct": 0}))

    for clip_id in clip_ids:
        captions = caps_cache.get(clip_id, [])
        if len(captions) < 16:
            print(f"  [EgoSchema] {clip_id}: only {len(captions)} captions, skipping", flush=True)
            continue

        q_data = ego_questions.get(clip_id)
        answer_idx = ego_answers.get(clip_id)
        if q_data is None or answer_idx is None:
            print(f"  [EgoSchema] {clip_id}: missing question or answer, skipping", flush=True)
            continue

        print(f"\n[EgoSchema] {clip_id}", flush=True)

        summaries = build_ego_summaries(model, tok, captions, EGO_CHECKPOINTS)
        per_clip_step[clip_id] = {
            "n_captions": 16, "checkpoints": EGO_CHECKPOINTS, "summaries": summaries
        }
        step_path = out_dir / "per_step" / f"ego_{clip_id}.json"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        _save(step_path, per_clip_step[clip_id])

        for cp_idx, cp_k in enumerate(EGO_CHECKPOINTS):
            cp_results = eval_ego_checkpoint(
                model, tok, clip_id, q_data, answer_idx, captions, summaries, cp_k, cp_idx)
            for cond, val in cp_results.items():
                accuracy_by_cp[cp_idx][cond]["n"] += 1
                accuracy_by_cp[cp_idx][cond]["correct"] += val

        # Save checkpoint quality
        cp_path = out_dir / "quality" / f"ego_{clip_id}.json"
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        for cp_idx, cp_k in enumerate(EGO_CHECKPOINTS):
            _save(cp_path, {"clip_id": clip_id, "checkpoints": EGO_CHECKPOINTS,
                             "results_by_cp": {
                                 cp_idx: {cond: accuracy_by_cp[cp_idx][cond]
                                          for cond in accuracy_by_cp[cp_idx]}
                             }})

    final_accuracy = {}
    for cp_idx, cond_dict in accuracy_by_cp.items():
        final_accuracy[cp_idx] = {}
        for cond, vals in cond_dict.items():
            n, c = vals["n"], vals["correct"]
            final_accuracy[cp_idx][cond] = {
                "n": n, "correct": c,
                "accuracy": round(c/n, 4) if n > 0 else None,
            }

    return per_clip_step, final_accuracy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="Smoke test: 2 convs, 2 clips, 5 Q each")
    parser.add_argument("--locomo-only", action="store_true")
    parser.add_argument("--ego-only", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "per_step").mkdir(exist_ok=True)
    (OUT_DIR / "quality").mkdir(exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, tok = load_model(device)

    locomo_step, locomo_accuracy, ego_step, ego_accuracy = {}, {}, {}, {}

    if not args.ego_only:
        print("\n=== LoCoMo ===", flush=True)
        locomo_step, locomo_accuracy = run_locomo(model, tok, args.smoke, OUT_DIR)

    if not args.locomo_only:
        print("\n=== EgoSchema ===", flush=True)
        ego_step, ego_accuracy = run_egoschema(model, tok, args.smoke, OUT_DIR)

    # Lifecycle cost analysis
    print("\n=== Lifecycle cost analysis ===", flush=True)
    lifecycle = compute_lifecycle_cost(locomo_step, ego_step)

    # Sanity check
    sanity = sanity_check(locomo_accuracy)
    print("\nSanity check (full_regen@100% vs phase0a):")
    for budget, s in sanity.items():
        print(f"  {budget}: {s['status']} acc={s.get('accuracy')} ref={s['reference']} diff={s.get('diff')}")

    # Decision
    outcome = classify_outcome(locomo_accuracy, lifecycle)
    print(f"\nDecision: Outcome {outcome}")

    # Print accuracy summary
    print("\n=== LoCoMo accuracy at 100% checkpoint ===")
    cp100 = locomo_accuracy.get(3, {})
    for key in sorted(cp100):
        d = cp100[key]
        print(f"  {key}: n={d['n']} acc={d.get('accuracy')}")

    print("\n=== Lifecycle cost (LoCoMo) ===")
    for key, d in sorted(lifecycle["locomo"].items()):
        print(f"  {key}: mean_input_tok={d.get('mean_input_tokens')} "
              f"ratio={d.get('token_ratio_vs_full_regen')}")

    # Assemble final result
    prov = stamp(
        script="e27_maintenance.py",
        model=MODEL_SLUG,
        device="nvidia_rtx_a6000",
        n=100,
        args=args,
    )

    result = {
        "experiment": "E27",
        "smoke": args.smoke,
        "locomo_accuracy": locomo_accuracy,
        "egoschema_accuracy": ego_accuracy,
        "lifecycle_cost": lifecycle,
        "sanity_check": sanity,
        "outcome": outcome,
        "_provenance": prov,
    }

    suffix = "_smoke" if args.smoke else ""
    out_path = OUT_DIR / f"e27_maintenance_{MODEL_SLUG}{suffix}.json"
    _save(out_path, result)
    print(f"\nSaved to {out_path}", flush=True)

    if not args.smoke:
        print("\nSanity check details:", json.dumps(sanity, indent=2))

    return outcome


if __name__ == "__main__":
    main()
