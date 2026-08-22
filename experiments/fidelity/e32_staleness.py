"""
E32 — Staleness cost: quality degradation and catch-up latency for stale session state.

Workloads
---------
  LoCoMo (dense, primary staleness workload):
    N ∈ {0, 1, 5, 10, 20, 50, 100} turns behind current head
    Fidelities: full, win10, sum200
    Reports: accuracy vs N; inside/outside-evidence split; catch-up latency
  EgoSchema (gist, truncation control only):
    N ∈ {0, 1, 5} captions removed from end of clip
    Fidelities: full, win10, sum200
    NOT a staleness measurement — labelled truncation_control throughout

Modes
-----
  quality   — HF inference, per-question per-N per-fidelity correctness (GPU required)
  latency   — vLLM catch-up latency per-N per-fidelity (GPU required, LoCoMo only)
  analysis  — derive tradeoff table from quality + latency outputs (CPU)

Sanity check
  N=0 must reproduce committed E29 qwen7b per-question correctness within noise.
  Script reports per-condition delta and aborts quality pass if delta > 0.05.

Usage
-----
  # LoCoMo quality pass
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk \\
    python experiments/fidelity/e32_staleness.py --mode quality --workload locomo

  # EgoSchema quality pass (truncation control)
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk \\
    python experiments/fidelity/e32_staleness.py --mode quality --workload egoschema

  # Catch-up latency (LoCoMo, vLLM, same config as E26)
  CUDA_VISIBLE_DEVICES=1 VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 conda run -n fmtk \\
    python experiments/fidelity/e32_staleness.py --mode latency

  # Analysis (CPU, requires quality + latency outputs)
  python experiments/fidelity/e32_staleness.py --mode analysis
"""

import argparse
import gc
import json
import math
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy import stats as scipy_stats

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp
from premise_egoschema import LETTERS, load_egoschema, parse_choice

# ── Paths ──────────────────────────────────────────────────────────────────────
LOCOMO_DATA    = ROOT / "data" / "locomo" / "locomo10.json"
LOCOMO_SUBSET  = ROOT / "data" / "audit_subsets" / "phase0a" / "locomo_100.json"
EGO_DATA_DIR   = ROOT / "data" / "egoschema"
EGO_SUBSET     = ROOT / "data" / "audit_subsets" / "phase0a" / "egoschema_60.json"
EGO_CAPS       = ROOT / "results" / "fidelity" / "caches" / "captions_cache.json"
# Committed N=0 caches (from E29 / phase0a)
LOCOMO_SUM200_CACHE = ROOT / "results" / "fidelity" / "caches" / "locomo_summaries_200.json"
EGO_SUM200_CACHE    = ROOT / "results" / "fidelity" / "caches" / "summaries_cache_200.json"
# E29 committed per-question results (sanity check baseline)
E29_LOCOMO_BASELINE = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous" / "locomo_qwen7b_n100.json"
E29_EGO_BASELINE    = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous" / "egoschema_qwen7b_n60.json"
OUT_DIR             = ROOT / "results" / "fidelity" / "e32_staleness"
CACHE_DIR           = OUT_DIR / "caches"
FIG_DIR             = ROOT / "figures" / "fidelity"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────────────
MODEL_ID   = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG = "qwen7b"
DEVICE     = "nvidia_rtx_a6000"

LOCOMO_N_VALUES  = [0, 1, 5, 10, 20, 50, 100]
EGO_N_VALUES     = [0, 1, 5]   # truncation control only
FIDELITIES       = ["full", "win10", "sum200"]

# vLLM config — must match E26 exactly
MAX_MODEL_LEN    = 131072
GPU_MEM_FRAC     = 0.90
REPS             = 5
YARN_ROPE_SCALING = {
    "type": "yarn",
    "factor": 4.0,
    "original_max_position_embeddings": 32768,
}
YARN_L_THRESHOLD = 32768

# TTFT budgets (seconds) — reference lines for tradeoff table
TTFT_BUDGETS = {"voice_embodied_s": 0.3, "interactive_s": 1.0, "background_s": 10.0}

# ── Prompts (identical to E29 / phase0a; do not modify) ───────────────────────
QA_PROMPT = (
    "The following is a conversation history between two people.\n\n"
    "{context}\n\n"
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
BLIND_PROMPT = (
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
JUDGE_PROMPT = (
    "Is '{pred}' a correct or semantically equivalent answer to '{gold}'?\n"
    "Reply YES or NO only."
)
LOCOMO_SUMMARY_PROMPT = (
    "Summarize the following conversation history in approximately {max_tokens} tokens. "
    "Preserve all named facts, dates, and specific details mentioned.\n\n"
    "{context}\n\nSummary:"
)
EGO_SUMMARY_PROMPT = (
    "Summarize the following video frame descriptions in approximately {max_tokens} tokens. "
    "Preserve the main actions, objects, and people involved.\n\n"
    "Frame descriptions:\n{context}\n\nSummary:"
)


# ── Shared helpers ──────────────────────────────────────────────────────────────

def _normalize(s):
    return re.sub(r"\s+", " ", str(s).lower().strip())


def _save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return p, max(0.0, centre - margin), min(1.0, centre + margin)


def bootstrap_ci(v, reps=1000, seed=42):
    rng = np.random.default_rng(seed)
    v = np.array(v, dtype=float)
    boots = [np.mean(rng.choice(v, len(v), replace=True)) for _ in range(reps)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(np.mean(v)), float(lo), float(hi)


def summarise_latency(vals):
    s = sorted(vals)
    n = len(s)
    med = statistics.median(s)
    q1 = statistics.median(s[: n // 2]) if n >= 2 else med
    q3 = statistics.median(s[n - n // 2 :]) if n >= 2 else med
    return {"median_s": round(med, 4), "iqr_s": round(q3 - q1, 4), "all_s": [round(v, 4) for v in s]}


# ── LoCoMo data loading ─────────────────────────────────────────────────────────

def load_locomo_data():
    sub = json.loads(LOCOMO_SUBSET.read_text())
    subset_ids = set(sub["ids"])
    raw = json.loads(LOCOMO_DATA.read_text())

    questions, convs = [], {}
    for item in raw:
        cid = item["sample_id"]
        c = item["conversation"]
        sessions, dates, all_turns = [], [], []
        i = 1
        while f"session_{i}" in c:
            turns = c[f"session_{i}"]
            sessions.append(turns)
            dates.append(c.get(f"session_{i}_date_time", ""))
            all_turns.extend(turns)
            i += 1
        convs[cid] = {
            "sessions": sessions,
            "dates": dates,
            "all_turns": all_turns,
        }
        for qi, qa in enumerate(item["qa"]):
            if qa["category"] != 1:
                continue
            uid = f"{cid}_q{qi:04d}"
            if uid in subset_ids:
                questions.append({
                    "q_uid": uid,
                    "conv_id": cid,
                    "question": qa["question"],
                    "gold": str(qa["answer"]),
                    "evidence": qa.get("evidence", []),
                })
    return questions, convs


def sessions_to_text(sessions, dates):
    lines = []
    for si, (sess, date) in enumerate(zip(sessions, dates)):
        hdr = f"[Session {si + 1}" + (f" — {date}]" if date else "]")
        lines.append(hdr)
        for t in sess:
            lines.append(f"{t['speaker']}: {t['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def truncate_sessions(sessions, dates, N):
    """Drop last N individual utterances from the sessions list.
    Returns (truncated_sessions, truncated_dates, delta_turns).
    delta_turns is the list of turns that were removed.
    """
    all_turns = [t for s in sessions for t in s]
    total = len(all_turns)
    effective_N = min(N, total)
    keep = total - effective_N
    delta_turns = all_turns[keep:]

    result_sessions, result_dates = [], []
    remaining = keep
    for sess, date in zip(sessions, dates):
        if remaining <= 0:
            break
        if remaining >= len(sess):
            result_sessions.append(list(sess))
            result_dates.append(date)
            remaining -= len(sess)
        else:
            result_sessions.append(list(sess[:remaining]))
            result_dates.append(date)
            remaining = 0
    return result_sessions, result_dates, delta_turns


def build_locomo_stale_context(conv, N, fidelity, stale_sum200_cache, cid):
    """Build the stale context text for (fidelity, N). Returns (text, meta)."""
    sessions = conv["sessions"]
    dates = conv["dates"]
    all_turns = conv["all_turns"]
    total_turns = len(all_turns)

    stale_sessions, stale_dates, delta_turns = truncate_sessions(sessions, dates, N)
    stale_turns = [t for s in stale_sessions for t in s]

    # Session-equivalent: how many complete sessions does N turns represent
    # (approximate: N / mean turns-per-session for this conversation)
    n_sessions = len(sessions)
    mean_tps = total_turns / n_sessions if n_sessions > 0 else 1.0
    session_equiv = round(N / mean_tps, 2) if N > 0 else 0.0

    # Which sessions have been touched by the staleness boundary
    stale_n_sessions = len(stale_sessions)

    # Evidence-in-stale-window check is done at question level, not here.

    if fidelity == "full":
        text = sessions_to_text(stale_sessions, stale_dates)

    elif fidelity == "win10":
        # Last 10 sessions from stale history
        win_sessions = stale_sessions[-10:]
        win_dates = stale_dates[-10:]
        text = sessions_to_text(win_sessions, win_dates)

    elif fidelity == "sum200":
        key = f"{cid}_N{N}" if N > 0 else cid
        text = stale_sum200_cache.get(key, stale_sum200_cache.get(cid, ""))

    else:
        raise ValueError(f"unknown fidelity: {fidelity}")

    meta = {
        "total_turns": total_turns,
        "stale_turns": len(stale_turns),
        "delta_turns": len(delta_turns),
        "n_sessions_total": n_sessions,
        "n_sessions_stale": stale_n_sessions,
        "session_equiv": session_equiv,
    }
    return text, meta, delta_turns


def evidence_in_stale_window(evidence_list, all_turns, N):
    """Return True if ALL evidence turns are within the stale window (i.e. not in the delta)."""
    total = len(all_turns)
    stale_cutoff = max(0, total - N)
    dia_to_idx = {t["dia_id"]: i for i, t in enumerate(all_turns)}
    idxs = [dia_to_idx[e] for e in evidence_list if e in dia_to_idx]
    if not idxs:
        return None  # cannot determine
    return all(idx < stale_cutoff for idx in idxs)


# ── EgoSchema data loading ──────────────────────────────────────────────────────

def load_ego_data():
    sub = json.loads(EGO_SUBSET.read_text())
    subset_ids = set(sub["ids"])
    all_qs = load_egoschema(EGO_DATA_DIR / "questions.json", EGO_DATA_DIR / "subset_answers.json")
    caps = json.loads(EGO_CAPS.read_text()) if EGO_CAPS.exists() else {}
    items = []
    for q in all_qs:
        uid = q["q_uid"]
        if uid not in subset_ids:
            continue
        if uid not in caps:
            print(f"  WARNING: no captions for {uid}, skipping")
            continue
        items.append({
            "uid": uid,
            "question": q["question"],
            "options": q["options"],
            "gold_letter": LETTERS[q["gold_idx"]],
            "gold_idx": q["gold_idx"],
            "captions": caps[uid],
        })
    return items


# ── LLM helpers (HF, same pattern as E29) ──────────────────────────────────────

def load_hf_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print(f"Loading {MODEL_ID} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, device_map="cuda:0"
    )
    model.eval()
    import torch
    torch.cuda.reset_peak_memory_stats()
    return model, tok


def _hf_run(model, tok, prompt, max_new=40):
    import torch
    try:
        msgs = [{"role": "user", "content": prompt}]
        fmt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    except Exception:
        fmt = prompt
    inp = tok(fmt, return_tensors="pt", truncation=True, max_length=30000).to(model.device)
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            **inp, max_new_tokens=max_new, do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    lat = time.perf_counter() - t0
    text = tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return text, lat


def score_locomo(pred, gold, model, tok):
    p_n, g_n = _normalize(pred), _normalize(gold)
    if g_n in p_n or p_n in g_n:
        return 1, 1, 0.0
    resp, lat = _hf_run(model, tok, JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4)
    return 0, int(resp.upper().startswith("YES")), lat


def generate_summary(model, tok, context, max_tokens, prompt_template):
    prompt = prompt_template.format(max_tokens=max_tokens, context=context)
    text, _ = _hf_run(model, tok, prompt, max_new=max_tokens + 40)
    return text


# ── Stale sum200 cache generation ──────────────────────────────────────────────

def ensure_locomo_stale_sum200(model, tok, convs, n_vals, sum200_n0_cache):
    """Generate and cache stale sum200 for each (conv_id, N>0). Returns merged cache."""
    cache_path = CACHE_DIR / "locomo_sum200_stale.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
    else:
        # Seed from committed N=0 cache
        cache = {cid: v for cid, v in sum200_n0_cache.items()}

    for N in n_vals:
        if N == 0:
            continue
        missing = []
        for cid, conv in convs.items():
            key = f"{cid}_N{N}"
            if key not in cache:
                missing.append((cid, conv, N))
        if not missing:
            print(f"  stale sum200 N={N}: all cached", flush=True)
            continue
        print(f"  Generating stale sum200 for N={N}: {len(missing)} convs …", flush=True)
        for cid, conv, N_ in missing:
            sessions = conv["sessions"]
            dates = conv["dates"]
            stale_sessions, stale_dates, _ = truncate_sessions(sessions, dates, N_)
            stale_text = sessions_to_text(stale_sessions, stale_dates)
            summary = generate_summary(model, tok, stale_text, 200, LOCOMO_SUMMARY_PROMPT)
            cache[f"{cid}_N{N_}"] = summary
            _save_json(cache_path, cache)
            print(f"    {cid} N={N_}: {len(summary.split())} words", flush=True)

    return cache


def ensure_ego_stale_sum200(model, tok, items, n_vals, sum200_n0_cache):
    """Generate and cache stale sum200 for EgoSchema truncation control."""
    cache_path = CACHE_DIR / "egoschema_sum200_stale.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
    else:
        cache = {item["uid"]: sum200_n0_cache.get(item["uid"], "") for item in items}

    for N in n_vals:
        if N == 0:
            continue
        missing = [it for it in items if f"{it['uid']}_N{N}" not in cache]
        if not missing:
            print(f"  EgoSchema stale sum200 N={N}: all cached", flush=True)
            continue
        print(f"  Generating EgoSchema stale sum200 N={N}: {len(missing)} clips …", flush=True)
        for it in missing:
            caps = it["captions"]
            stale_caps = caps[:max(1, len(caps) - N)]
            context = "\n".join(f"{i+1}. {c}" for i, c in enumerate(stale_caps))
            summary = generate_summary(model, tok, context, 200, EGO_SUMMARY_PROMPT)
            cache[f"{it['uid']}_N{N}"] = summary
            _save_json(cache_path, cache)

    return cache


# ── Sanity check against E29 baseline ──────────────────────────────────────────

def sanity_check_locomo(records_n0):
    if not E29_LOCOMO_BASELINE.exists():
        print("  WARNING: E29 LoCoMo baseline not found; skipping sanity check.")
        return True
    baseline = json.loads(E29_LOCOMO_BASELINE.read_text())
    base_by_uid = {r["q_uid"]: r["conditions"] for r in baseline["records"]}
    n_disagree = defaultdict(int)
    n_total = defaultdict(int)
    for rec in records_n0:
        uid = rec["q_uid"]
        if uid not in base_by_uid:
            continue
        for fid in FIDELITIES:
            e29_cond = {"full": "full", "win10": "window-10", "sum200": "summary-200"}[fid]
            if e29_cond not in base_by_uid[uid]:
                continue
            e29_correct = base_by_uid[uid][e29_cond]["correct"]
            e32_correct = rec["conditions"].get(fid, {}).get("correct", None)
            if e32_correct is None:
                continue
            n_total[fid] += 1
            if e29_correct != e32_correct:
                n_disagree[fid] += 1
    print("\n  Sanity check vs E29 baseline (N=0):")
    any_fail = False
    for fid in FIDELITIES:
        if n_total[fid] == 0:
            continue
        delta = n_disagree[fid] / n_total[fid]
        flag = " FAIL (>0.05)" if delta > 0.05 else " ok"
        print(f"    {fid:<10}: {n_disagree[fid]}/{n_total[fid]} disagree  delta={delta:.3f}{flag}")
        if delta > 0.05:
            any_fail = True
    if any_fail:
        print("  SANITY CHECK FAILED: N=0 results diverge from E29 by >5%. "
              "Investigate before trusting N>0 results.", flush=True)
        return False
    print("  Sanity check passed.")
    return True


def sanity_check_ego(records_n0):
    if not E29_EGO_BASELINE.exists():
        print("  WARNING: E29 EgoSchema baseline not found; skipping sanity check.")
        return True
    baseline = json.loads(E29_EGO_BASELINE.read_text())
    base_by_uid = {r["uid"]: r["conditions"] for r in baseline["records"]}
    n_disagree = defaultdict(int)
    n_total = defaultdict(int)
    for rec in records_n0:
        uid = rec["uid"]
        if uid not in base_by_uid:
            continue
        for fid in FIDELITIES:
            e29_cond = {"full": "full", "win10": "window-10", "sum200": "summary-200"}[fid]
            if e29_cond not in base_by_uid[uid]:
                continue
            e29_c = base_by_uid[uid][e29_cond]["correct"]
            e32_c = rec["conditions"].get(fid, {}).get("correct", None)
            if e32_c is None:
                continue
            n_total[fid] += 1
            if e29_c != e32_c:
                n_disagree[fid] += 1
    print("\n  EgoSchema sanity check vs E29 baseline (N=0):")
    for fid in FIDELITIES:
        if n_total[fid] == 0:
            continue
        delta = n_disagree[fid] / n_total[fid]
        flag = " FAIL" if delta > 0.05 else " ok"
        print(f"    {fid:<10}: {n_disagree[fid]}/{n_total[fid]} disagree  delta={delta:.3f}{flag}")
    return True


# ── QUALITY MODE ───────────────────────────────────────────────────────────────

def run_quality_locomo():
    import torch
    questions, convs = load_locomo_data()
    model, hf_tok = load_hf_model()

    # Load N=0 sum200 cache (committed from phase0a)
    sum200_n0 = json.loads(LOCOMO_SUM200_CACHE.read_text())
    # Ensure / generate stale summaries for N>0
    stale_sum200 = ensure_locomo_stale_sum200(model, hf_tok, convs, LOCOMO_N_VALUES, sum200_n0)

    # Compute HF token lengths for all conversations (for reporting)
    print("  Computing token lengths ...", flush=True)
    tok_len = {cid: len(hf_tok.encode(
        sessions_to_text(conv["sessions"], conv["dates"]),
        add_special_tokens=False
    )) for cid, conv in convs.items()}

    all_records = []  # list of records, one per (question, N, fidelity)
    records_n0 = []   # for sanity check

    for N in LOCOMO_N_VALUES:
        part_path = OUT_DIR / f"locomo_quality_qwen7b_N{N:03d}.json"
        if part_path.exists():
            print(f"\n  N={N}: loading existing partial output …", flush=True)
            part = json.loads(part_path.read_text())
            if N == 0:
                records_n0 = part["records"]
            all_records.extend(part["records"])
            continue

        print(f"\n{'='*60}\n  N={N} turns behind\n{'='*60}", flush=True)
        n_records = []

        for i, q in enumerate(questions):
            cid = q["conv_id"]
            conv = convs[cid]
            all_turns = conv["all_turns"]

            rec = {
                "q_uid": q["q_uid"],
                "conv_id": cid,
                "question": q["question"],
                "gold": q["gold"],
                "N": N,
                "full_context_tokens": tok_len[cid],
                "conditions": {},
            }

            for fid in FIDELITIES:
                ctx, meta, delta_turns = build_locomo_stale_context(
                    conv, N, fid, stale_sum200, cid
                )
                # Evidence split
                ev_inside = evidence_in_stale_window(q["evidence"], all_turns, N)

                # Prompt
                if not ctx and fid != "sum200":
                    prompt = BLIND_PROMPT.format(question=q["question"])
                else:
                    prompt = QA_PROMPT.format(context=ctx, question=q["question"])

                pred, lat_ans = _hf_run(model, hf_tok, prompt, max_new=40)
                pred = pred.split("\n")[0].strip()
                em, jd, lat_judge = score_locomo(pred, q["gold"], model, hf_tok)

                rec["conditions"][fid] = {
                    "pred": pred,
                    "exact": em,
                    "correct": jd,
                    "evidence_inside_stale_window": ev_inside,
                    "stale_meta": meta,
                }

            prog = f"  {i+1:3d}/{len(questions)} N={N} " \
                   f"full={rec['conditions']['full']['correct']} " \
                   f"win10={rec['conditions']['win10']['correct']} " \
                   f"s200={rec['conditions']['sum200']['correct']} " \
                   f"ev_in={rec['conditions']['full']['evidence_inside_stale_window']}"
            print(prog, flush=True)
            n_records.append(rec)

        part_data = {
            "N": N,
            "n": len(n_records),
            "records": n_records,
        }
        _save_json(part_path, part_data)
        all_records.extend(n_records)
        if N == 0:
            records_n0 = n_records

    # Sanity check on N=0
    sanity_ok = sanity_check_locomo(records_n0)

    # Merge all N values into final output
    peak_gb = torch.cuda.max_memory_allocated() / 1e9
    out = {
        "metadata": {
            "experiment": "E32",
            "mode": "quality",
            "workload": "locomo",
            "model_slug": MODEL_SLUG,
            "model_id": MODEL_ID,
            "n_questions": len(questions),
            "n_convs": len(convs),
            "N_values": LOCOMO_N_VALUES,
            "fidelities": FIDELITIES,
            "sanity_check_passed": sanity_ok,
            "gpu_peak_gb": round(peak_gb, 2),
            "timestamp": datetime.now().isoformat(),
        },
        "records": all_records,
        "_provenance": stamp(
            script="e32_staleness.py",
            model=MODEL_SLUG,
            device=DEVICE,
            n=len(questions),
            args={"mode": "quality", "workload": "locomo"},
        ),
    }
    out_path = OUT_DIR / "locomo_quality_qwen7b.json"
    _save_json(out_path, out)
    print(f"\nSaved → {out_path}")
    _print_quality_summary(all_records, questions, "locomo")


def run_quality_egoschema():
    import torch
    items = load_ego_data()
    model, hf_tok = load_hf_model()

    # Load N=0 sum200 cache
    sum200_n0 = json.loads(EGO_SUM200_CACHE.read_text()) if EGO_SUM200_CACHE.exists() else {}
    stale_sum200 = ensure_ego_stale_sum200(model, hf_tok, items, EGO_N_VALUES, sum200_n0)

    all_records = []
    records_n0 = []

    for N in EGO_N_VALUES:
        part_path = OUT_DIR / f"egoschema_quality_qwen7b_N{N:03d}.json"
        if part_path.exists():
            print(f"\n  N={N}: loading existing partial output …", flush=True)
            part = json.loads(part_path.read_text())
            if N == 0:
                records_n0 = part["records"]
            all_records.extend(part["records"])
            continue

        print(f"\n{'='*60}\n  EgoSchema truncation control N={N}\n{'='*60}", flush=True)
        n_records = []

        for i, item in enumerate(items):
            uid = item["uid"]
            n_caps = len(item["captions"])
            effective_N = min(N, n_caps - 1)
            stale_caps = item["captions"][:n_caps - effective_N]

            rec = {
                "uid": uid,
                "question": item["question"],
                "gold": item["gold_letter"],
                "N": N,
                "effective_N": effective_N,
                "n_captions_stale": len(stale_caps),
                "type": "truncation_control",
                "conditions": {},
            }

            for fid in FIDELITIES:
                if fid == "full":
                    sel = stale_caps
                    header = (
                        "You are answering a multiple-choice question about a first-person "
                        "(egocentric) video. Below are chronological text descriptions of frames "
                        "sampled from the video, followed by a question and five options."
                    )
                    lines = "\n".join(f"{i2+1}. {c}" for i2, c in enumerate(sel))
                    obs = f"\n\nFrame descriptions (chronological):\n{lines}" if sel else "\n\n(No frame descriptions.)"
                    opt_block = "\n".join(f"{LETTERS[j]}. {opt}" for j, opt in enumerate(item["options"]))
                    instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
                    prompt = f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"

                elif fid == "win10":
                    sel = stale_caps[-10:]
                    header = (
                        "You are answering a multiple-choice question about a first-person "
                        "(egocentric) video. Below are chronological text descriptions of frames "
                        "sampled from the video, followed by a question and five options."
                    )
                    lines = "\n".join(f"{i2+1}. {c}" for i2, c in enumerate(sel))
                    obs = f"\n\nFrame descriptions (chronological):\n{lines}"
                    opt_block = "\n".join(f"{LETTERS[j]}. {opt}" for j, opt in enumerate(item["options"]))
                    instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
                    prompt = f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"

                elif fid == "sum200":
                    key = f"{uid}_N{N}" if N > 0 else uid
                    summary = stale_sum200.get(key, stale_sum200.get(uid, ""))
                    header = (
                        "You are answering a multiple-choice question about a first-person "
                        "(egocentric) video. Below is a summary of the video, followed by a question and five options."
                    )
                    obs = f"\n\nVideo summary:\n{summary}" if summary else "\n\n(No summary available.)"
                    opt_block = "\n".join(f"{LETTERS[j]}. {opt}" for j, opt in enumerate(item["options"]))
                    instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
                    prompt = f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"

                raw, _ = _hf_run(model, hf_tok, prompt, max_new=10)
                pred = parse_choice(raw) or "?"
                correct = int(pred == item["gold_letter"])
                rec["conditions"][fid] = {"pred": pred, "raw": raw, "correct": correct}

            print(f"  {i+1:2d}/{len(items)} N={N} "
                  f"full={rec['conditions']['full']['correct']} "
                  f"win10={rec['conditions']['win10']['correct']} "
                  f"s200={rec['conditions']['sum200']['correct']}", flush=True)
            n_records.append(rec)

        part_data = {"N": N, "n": len(n_records), "records": n_records}
        _save_json(part_path, part_data)
        all_records.extend(n_records)
        if N == 0:
            records_n0 = n_records

    sanity_check_ego(records_n0)

    peak_gb = torch.cuda.max_memory_allocated() / 1e9
    out = {
        "metadata": {
            "experiment": "E32",
            "mode": "quality",
            "workload": "egoschema",
            "type": "truncation_control",
            "model_slug": MODEL_SLUG,
            "n_items": len(items),
            "N_values": EGO_N_VALUES,
            "fidelities": FIDELITIES,
            "note": "EgoSchema is a 16-caption fixed clip; N removes last N captions. "
                    "This is context truncation, not temporal staleness.",
            "gpu_peak_gb": round(peak_gb, 2),
            "timestamp": datetime.now().isoformat(),
        },
        "records": all_records,
        "_provenance": stamp(
            script="e32_staleness.py",
            model=MODEL_SLUG,
            device=DEVICE,
            n=len(items),
            args={"mode": "quality", "workload": "egoschema"},
        ),
    }
    out_path = OUT_DIR / "egoschema_quality_qwen7b.json"
    _save_json(out_path, out)
    print(f"\nSaved → {out_path}")


def _print_quality_summary(all_records, questions, workload):
    by_N_fid = defaultdict(list)
    for rec in all_records:
        N = rec["N"]
        for fid in FIDELITIES:
            if fid in rec["conditions"]:
                by_N_fid[(N, fid)].append(rec["conditions"][fid]["correct"])

    print(f"\n{'='*70}")
    print(f"E32 {workload.upper()} QUALITY SUMMARY")
    print(f"{'='*70}")
    print(f"  {'N':>5}  {'fidelity':<10}  {'acc':>6}  {'CI_lo':>6}  {'CI_hi':>6}")
    for N in (LOCOMO_N_VALUES if workload == "locomo" else EGO_N_VALUES):
        for fid in FIDELITIES:
            v = by_N_fid[(N, fid)]
            if not v:
                continue
            p, lo, hi = wilson_ci(sum(v), len(v))
            print(f"  {N:>5}  {fid:<10}  {p:6.3f}  {lo:6.3f}  {hi:6.3f}")


# ── LATENCY MODE (vLLM) ────────────────────────────────────────────────────────

def find_model_cache_path():
    base = (Path.home() / ".cache" / "huggingface" / "hub"
            / "models--Qwen--Qwen2.5-7B-Instruct" / "snapshots")
    if base.exists():
        snaps = sorted(base.iterdir())
        if snaps:
            return str(snaps[-1])
    return None


def make_vllm_engine(model_path, prefix_caching, yarn=False):
    import tempfile, shutil
    from vllm import LLM
    if yarn:
        import json as _json
        tmp = Path(tempfile.mkdtemp()) / "qwen_yarn"
        tmp.mkdir()
        src = Path(model_path)
        cfg = _json.loads((src / "config.json").read_text())
        cfg["rope_scaling"] = YARN_ROPE_SCALING
        (tmp / "config.json").write_text(_json.dumps(cfg, indent=2))
        for f in src.iterdir():
            if f.name != "config.json":
                (tmp / f.name).symlink_to(f.resolve())
        model_path = str(tmp)

    return LLM(
        model=model_path,
        dtype="float16",
        gpu_memory_utilization=GPU_MEM_FRAC,
        enable_prefix_caching=prefix_caching,
        max_model_len=MAX_MODEL_LEN,
        enforce_eager=False,
    )


def vllm_warm_append(llm, stale_text, delta_text, reps):
    """Prime cache with stale_text, measure time to process stale_text + delta_text."""
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)
    extended = stale_text + "\n" + delta_text

    try:
        llm.generate([stale_text], sp)
    except Exception as e:
        return {"feasible": False, "error": f"cache prime failed: {e}"}
    try:
        llm.generate([extended], sp)
    except Exception as e:
        return {"feasible": False, "error": f"extension warm-up failed: {e}"}

    times = []
    for r in range(reps):
        llm.generate([stale_text], sp)  # re-prime
        t0 = time.perf_counter()
        try:
            llm.generate([extended], sp)
        except Exception as e:
            return {"feasible": False, "error": str(e), "reps_done": r}
        times.append(time.perf_counter() - t0)
        print(f"      warm-append rep {r+1}/{reps}: {times[-1]:.3f}s", flush=True)

    return {"feasible": True, **summarise_latency(times)}


def vllm_cold_prefill_decode(llm, context_text, decode_budget, reps):
    """Cold prefill + decode(decode_budget) on context_text."""
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=decode_budget, min_tokens=decode_budget, temperature=0.0)

    try:
        llm.generate([context_text], sp)  # warm-up
    except Exception as e:
        return {"feasible": False, "error": f"warm-up failed: {e}"}

    times = []
    for r in range(reps):
        t0 = time.perf_counter()
        try:
            llm.generate([context_text], sp)
        except Exception as e:
            return {"feasible": False, "error": str(e), "reps_done": r}
        times.append(time.perf_counter() - t0)
        print(f"      cold rep {r+1}/{reps}: {times[-1]:.3f}s", flush=True)

    return {"feasible": True, **summarise_latency(times)}


def run_latency():
    """Measure catch-up latency for LoCoMo conversations using vLLM (E26 config)."""
    import torch
    questions, convs = load_locomo_data()

    # Need stale sum200 cache (must exist; generate via --mode quality first if needed)
    stale_cache_path = CACHE_DIR / "locomo_sum200_stale.json"
    sum200_n0 = json.loads(LOCOMO_SUM200_CACHE.read_text())
    if stale_cache_path.exists():
        stale_sum200 = json.loads(stale_cache_path.read_text())
    else:
        print("WARNING: stale sum200 cache not found. Running --mode quality first is recommended.")
        stale_sum200 = {cid: v for cid, v in sum200_n0.items()}

    # Tokenizer for token counting
    from transformers import AutoTokenizer
    hf_tok = AutoTokenizer.from_pretrained(MODEL_ID)

    model_path = find_model_cache_path()
    if model_path is None:
        raise RuntimeError("Cannot find Qwen2.5-7B-Instruct model cache. Set HF_HOME or download first.")
    print(f"  Model cache: {model_path}", flush=True)

    # Sample all conversations (10 unique convs in the subset)
    sample_cids = list(convs.keys())
    print(f"  Measuring latency for {len(sample_cids)} conversations × "
          f"{len(LOCOMO_N_VALUES)-1} N-values …", flush=True)

    measurements = []

    # ── Phase A: warm-append (full and win10), prefix_caching=True ───────────
    print("\n── WARM-APPEND (full, win10, prefix_caching=True) ──", flush=True)
    # Check max context length to decide if YaRN needed
    max_full_tokens = max(
        len(hf_tok.encode(sessions_to_text(conv["sessions"], conv["dates"]), add_special_tokens=False))
        for conv in convs.values()
    )
    need_yarn = max_full_tokens > YARN_L_THRESHOLD
    print(f"  Max full context: {max_full_tokens:,} tokens  YaRN: {need_yarn}", flush=True)

    llm_warm = make_vllm_engine(model_path, prefix_caching=True, yarn=need_yarn)

    for cid in sample_cids:
        conv = convs[cid]
        total_turns = len(conv["all_turns"])
        full_text = sessions_to_text(conv["sessions"], conv["dates"])
        full_toks = len(hf_tok.encode(full_text, add_special_tokens=False))

        for N in LOCOMO_N_VALUES:
            if N == 0:
                continue

            stale_sessions, stale_dates, delta_turns = truncate_sessions(
                conv["sessions"], conv["dates"], N
            )
            stale_all = [t for s in stale_sessions for t in s]
            n_sessions = len(conv["sessions"])
            mean_tps = total_turns / n_sessions
            session_equiv = round(N / mean_tps, 2)

            # Delta text (the N missing turns as plain text)
            delta_lines = [f"{t['speaker']}: {t['text']}" for t in delta_turns]
            delta_text = "\n".join(delta_lines)
            delta_toks = len(hf_tok.encode(delta_text, add_special_tokens=False))

            for fid in ["full", "win10"]:
                stale_text, _, _ = build_locomo_stale_context(
                    conv, N, fid, stale_sum200, cid
                )
                stale_toks = len(hf_tok.encode(stale_text, add_special_tokens=False))

                print(f"\n  {cid} N={N} fid={fid} "
                      f"stale={stale_toks}tok delta={delta_toks}tok "
                      f"~{session_equiv} sessions", flush=True)

                result = vllm_warm_append(llm_warm, stale_text, delta_text, REPS)
                measurements.append({
                    "conv_id": cid,
                    "N": N,
                    "session_equiv": session_equiv,
                    "fidelity": fid,
                    "variant": "warm_append",
                    "stale_context_tokens": stale_toks,
                    "delta_tokens": delta_toks,
                    "full_context_tokens": full_toks,
                    **result,
                })

    del llm_warm
    gc.collect()
    torch.cuda.empty_cache()

    # ── Phase B: cold prefill+decode (sum200 full-regen and recursive) ───────
    print("\n── COLD PREFILL+DECODE (sum200, prefix_caching=False) ──", flush=True)
    llm_cold = make_vllm_engine(model_path, prefix_caching=False, yarn=need_yarn)

    for cid in sample_cids:
        conv = convs[cid]
        total_turns = len(conv["all_turns"])
        full_text = sessions_to_text(conv["sessions"], conv["dates"])
        full_toks = len(hf_tok.encode(full_text, add_special_tokens=False))
        n_sessions = len(conv["sessions"])
        mean_tps = total_turns / n_sessions

        for N in LOCOMO_N_VALUES:
            if N == 0:
                continue

            _, _, delta_turns = truncate_sessions(conv["sessions"], conv["dates"], N)
            delta_lines = [f"{t['speaker']}: {t['text']}" for t in delta_turns]
            delta_text = "\n".join(delta_lines)
            delta_toks = len(hf_tok.encode(delta_text, add_special_tokens=False))
            session_equiv = round(N / mean_tps, 2)

            # Full regen: cold prefill on full current history, decode 200 tok
            full_regen_prompt = LOCOMO_SUMMARY_PROMPT.format(
                max_tokens=200, context=full_text
            )
            full_regen_toks = len(hf_tok.encode(full_regen_prompt, add_special_tokens=False))
            print(f"\n  {cid} N={N} sum200/full_regen "
                  f"ctx={full_regen_toks}tok delta={delta_toks}tok", flush=True)
            r_regen = vllm_cold_prefill_decode(llm_cold, full_regen_prompt, 200, REPS)
            measurements.append({
                "conv_id": cid,
                "N": N,
                "session_equiv": session_equiv,
                "fidelity": "sum200",
                "variant": "full_regen",
                "stale_context_tokens": full_regen_toks,
                "delta_tokens": delta_toks,
                "full_context_tokens": full_toks,
                **r_regen,
            })

            # Recursive update: stale summary + N new turns, decode 200 tok
            stale_sum = stale_sum200.get(f"{cid}_N{N}", stale_sum200.get(cid, ""))
            recursive_ctx = stale_sum + "\n\n[New conversation turns:]\n" + delta_text
            recursive_prompt = LOCOMO_SUMMARY_PROMPT.format(
                max_tokens=200, context=recursive_ctx
            )
            recursive_toks = len(hf_tok.encode(recursive_prompt, add_special_tokens=False))
            print(f"  {cid} N={N} sum200/recursive "
                  f"ctx={recursive_toks}tok delta={delta_toks}tok", flush=True)
            r_rec = vllm_cold_prefill_decode(llm_cold, recursive_prompt, 200, REPS)
            measurements.append({
                "conv_id": cid,
                "N": N,
                "session_equiv": session_equiv,
                "fidelity": "sum200",
                "variant": "recursive",
                "stale_context_tokens": recursive_toks,
                "delta_tokens": delta_toks,
                "full_context_tokens": full_toks,
                **r_rec,
            })

    del llm_cold
    gc.collect()
    torch.cuda.empty_cache()

    out = {
        "metadata": {
            "experiment": "E32",
            "mode": "latency",
            "workload": "locomo",
            "model_slug": MODEL_SLUG,
            "vllm_config": {
                "max_model_len": MAX_MODEL_LEN,
                "gpu_mem_frac": GPU_MEM_FRAC,
                "reps": REPS,
                "yarn_above": YARN_L_THRESHOLD,
                "note": "warm_append uses prefix_caching=True; cold uses prefix_caching=False. "
                        "Matches E26 configuration.",
            },
            "N_values": LOCOMO_N_VALUES[1:],
            "n_convs": len(sample_cids),
            "timestamp": datetime.now().isoformat(),
        },
        "measurements": measurements,
        "_provenance": stamp(
            script="e32_staleness.py",
            model=MODEL_SLUG,
            device=DEVICE,
            n=len(measurements),
            args={"mode": "latency"},
        ),
    }
    out_path = OUT_DIR / "locomo_latency_qwen7b.json"
    _save_json(out_path, out)
    print(f"\nSaved → {out_path}")
    _print_latency_summary(measurements)


def _print_latency_summary(measurements):
    print(f"\n{'='*70}\nE32 LATENCY SUMMARY\n{'='*70}")
    from collections import defaultdict
    by_fid_var_N = defaultdict(list)
    for m in measurements:
        if m.get("feasible"):
            k = (m["fidelity"], m.get("variant", "warm_append"), m["N"])
            by_fid_var_N[k].append(m["median_s"])
    print(f"  {'fidelity':<10}  {'variant':<15}  {'N':>5}  {'med_s':>8}  {'delta_tok':>10}")
    for N in LOCOMO_N_VALUES[1:]:
        for fid in ["full", "win10", "sum200"]:
            for var in (["warm_append"] if fid in ("full", "win10") else ["full_regen", "recursive"]):
                vals = by_fid_var_N.get((fid, var, N), [])
                if vals:
                    print(f"  {fid:<10}  {var:<15}  {N:>5}  {statistics.median(vals):8.3f}")


# ── ANALYSIS MODE ──────────────────────────────────────────────────────────────

def run_analysis():
    q_path = OUT_DIR / "locomo_quality_qwen7b.json"
    l_path = OUT_DIR / "locomo_latency_qwen7b.json"

    if not q_path.exists():
        print(f"Quality output not found: {q_path}")
        sys.exit(1)

    q_data = json.loads(q_path.read_text())
    latency_data = json.loads(l_path.read_text()) if l_path.exists() else None

    records = q_data["records"]

    # Build accuracy table: (N, fidelity, evidence_split)
    by_key = defaultdict(list)  # (N, fid, split) → [correct]
    for rec in records:
        N = rec["N"]
        for fid in FIDELITIES:
            if fid not in rec["conditions"]:
                continue
            cond = rec["conditions"][fid]
            correct = cond["correct"]
            ev_in = cond.get("evidence_inside_stale_window")
            by_key[(N, fid, "all")].append(correct)
            if ev_in is True:
                by_key[(N, fid, "ev_inside")].append(correct)
            elif ev_in is False:
                by_key[(N, fid, "ev_outside")].append(correct)

    # Latency lookup: (fid, variant, N) → median_s (aggregated over convs)
    lat_by_key = {}
    if latency_data:
        from collections import defaultdict as dd
        tmp = dd(list)
        for m in latency_data["measurements"]:
            if m.get("feasible"):
                tmp[(m["fidelity"], m.get("variant", "warm_append"), m["N"])].append(m["median_s"])
        for k, vs in tmp.items():
            lat_by_key[k] = statistics.median(vs)

    rows = []
    for N in LOCOMO_N_VALUES:
        for fid in FIDELITIES:
            v = by_key.get((N, fid, "all"), [])
            if not v:
                continue
            acc, lo, hi = bootstrap_ci(v)
            ev_in_v = by_key.get((N, fid, "ev_inside"), [])
            ev_out_v = by_key.get((N, fid, "ev_outside"), [])
            ev_in_acc = float(np.mean(ev_in_v)) if ev_in_v else None
            ev_out_acc = float(np.mean(ev_out_v)) if ev_out_v else None

            # Latency
            if fid in ("full", "win10"):
                variant = "warm_append"
                lat_med = lat_by_key.get((fid, variant, N))
            else:
                lat_regen = lat_by_key.get(("sum200", "full_regen", N))
                lat_rec = lat_by_key.get(("sum200", "recursive", N))
                lat_med = lat_rec if lat_rec is not None else lat_regen  # prefer recursive

            # TTFT budget verdicts
            budget_verdicts = {}
            if lat_med is not None:
                for bname, bval in TTFT_BUDGETS.items():
                    budget_verdicts[bname] = "within" if lat_med <= bval else "exceeds"

            row = {
                "N": N,
                "fidelity": fid,
                "acc_stale": round(acc, 4),
                "acc_ci_lo": round(lo, 4),
                "acc_ci_hi": round(hi, 4),
                "acc_ev_inside": round(ev_in_acc, 4) if ev_in_acc is not None else None,
                "acc_ev_outside": round(ev_out_acc, 4) if ev_out_acc is not None else None,
                "n_ev_inside": len(ev_in_v),
                "n_ev_outside": len(ev_out_v),
                "catchup_latency_s": round(lat_med, 4) if lat_med is not None else None,
                "budget_verdicts": budget_verdicts,
            }
            rows.append(row)

    # Print tradeoff table
    print(f"\n{'='*90}\nE32 TRADEOFF TABLE (LoCoMo, qwen7b)\n{'='*90}")
    print(f"  {'N':>5}  {'fidelity':<10}  {'acc':>6}  {'ev_in':>6}  {'ev_out':>7}  "
          f"{'lat_s':>8}  {'voice':>6}  {'inter':>6}  {'bg':>6}")
    for row in rows:
        bv = row["budget_verdicts"]
        print(
            f"  {row['N']:>5}  {row['fidelity']:<10}  {row['acc_stale']:6.3f}  "
            f"{str(round(row['acc_ev_inside'],3)) if row['acc_ev_inside'] is not None else '  —  ':>6}  "
            f"{str(round(row['acc_ev_outside'],3)) if row['acc_ev_outside'] is not None else '  —   ':>7}  "
            f"{str(round(row['catchup_latency_s'],3)) if row['catchup_latency_s'] is not None else '    —   ':>8}  "
            f"{'ok' if bv.get('voice_embodied_s')=='within' else 'FAIL':>6}  "
            f"{'ok' if bv.get('interactive_s')=='within' else 'FAIL':>6}  "
            f"{'ok' if bv.get('background_s')=='within' else 'FAIL':>6}"
        )

    out = {
        "metadata": {
            "experiment": "E32",
            "mode": "analysis",
            "workload": "locomo",
            "TTFT_budgets_s": TTFT_BUDGETS,
            "timestamp": datetime.now().isoformat(),
        },
        "tradeoff_table": rows,
        "_provenance": stamp(
            script="e32_staleness.py",
            model=MODEL_SLUG,
            device=None,
            n=len(rows),
            args={"mode": "analysis"},
        ),
    }
    out_path = OUT_DIR / "analysis_qwen7b.json"
    _save_json(out_path, out)
    print(f"\nSaved → {out_path}")


# ── PLOTTING (called from analysis mode when matplotlib is available) ──────────

def make_plots():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available; skipping plots.")
        return

    q_path = OUT_DIR / "locomo_quality_qwen7b.json"
    if not q_path.exists():
        print("  Quality output not found; skipping plots.")
        return

    records = json.loads(q_path.read_text())["records"]

    by_N_fid = defaultdict(list)
    by_N_fid_in = defaultdict(list)
    by_N_fid_out = defaultdict(list)
    for rec in records:
        N = rec["N"]
        for fid in FIDELITIES:
            if fid not in rec["conditions"]:
                continue
            cond = rec["conditions"][fid]
            by_N_fid[(N, fid)].append(cond["correct"])
            ev_in = cond.get("evidence_inside_stale_window")
            if ev_in is True:
                by_N_fid_in[(N, fid)].append(cond["correct"])
            elif ev_in is False:
                by_N_fid_out[(N, fid)].append(cond["correct"])

    colors = {"full": "#1f77b4", "win10": "#ff7f0e", "sum200": "#2ca02c"}
    styles_in = {"full": "-", "win10": "-", "sum200": "-"}
    styles_out = {"full": "--", "win10": "--", "sum200": "--"}

    # ── Quality figure ─────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    for ax_idx, (split_key, split_label, split_dict) in enumerate([
        ("all", "All questions", by_N_fid),
        ("in", "Evidence inside stale window", by_N_fid_in),
        ("out", "Evidence outside stale window", by_N_fid_out),
    ]):
        ax = axes[ax_idx]
        for fid in FIDELITIES:
            xs, ys, los, his = [], [], [], []
            for N in LOCOMO_N_VALUES:
                v = split_dict.get((N, fid), [])
                if not v:
                    continue
                p, lo, hi = wilson_ci(sum(v), len(v))
                xs.append(N)
                ys.append(p)
                los.append(p - lo)
                his.append(hi - p)
            if xs:
                ax.errorbar(xs, ys, yerr=[los, his], label=fid,
                            color=colors[fid], marker="o", capsize=3, linewidth=1.5)
        ax.set_xlabel("N turns behind")
        ax.set_title(split_label, fontsize=9)
        ax.set_xticks(LOCOMO_N_VALUES)
        if ax_idx == 0:
            ax.set_ylabel("Accuracy")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, 1)

    fig.suptitle("E32: Staleness Quality Cost — LoCoMo (qwen7b)", fontsize=11)
    fig.tight_layout()
    for ext in ["pdf", "png"]:
        fig.savefig(FIG_DIR / f"e32_staleness_quality.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Quality figure saved → figures/fidelity/e32_staleness_quality.pdf")

    # ── Latency figure ─────────────────────────────────────────────────────────
    l_path = OUT_DIR / "locomo_latency_qwen7b.json"
    if not l_path.exists():
        print("  Latency output not found; skipping latency figure.")
        return

    measurements = json.loads(l_path.read_text())["measurements"]
    from collections import defaultdict as dd
    lat_by = dd(list)
    for m in measurements:
        if m.get("feasible"):
            k = (m["fidelity"], m.get("variant", "warm_append"), m["N"])
            lat_by[k].append(m["median_s"])

    fig, ax = plt.subplots(figsize=(8, 5))
    plot_series = [
        ("full", "warm_append", "full (warm-append)", "#1f77b4", "-"),
        ("win10", "warm_append", "win10 (warm-append)", "#ff7f0e", "-"),
        ("sum200", "recursive", "sum200 (recursive)", "#2ca02c", "--"),
        ("sum200", "full_regen", "sum200 (full-regen)", "#2ca02c", ":"),
    ]
    for fid, var, label, color, ls in plot_series:
        xs, ys = [], []
        for N in LOCOMO_N_VALUES[1:]:
            vs = lat_by.get((fid, var, N), [])
            if vs:
                xs.append(N)
                ys.append(statistics.median(vs))
        if xs:
            ax.plot(xs, ys, label=label, color=color, linestyle=ls, marker="o", linewidth=1.5)

    for bname, bval in TTFT_BUDGETS.items():
        ax.axhline(bval, color="gray", linestyle=":", linewidth=0.8)
        ax.text(LOCOMO_N_VALUES[-1] * 0.98, bval * 1.05, bname.split("_")[0],
                fontsize=7, color="gray", ha="right")

    ax.set_xlabel("N turns behind")
    ax.set_ylabel("Catch-up latency (s)")
    ax.set_xticks(LOCOMO_N_VALUES[1:])
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_title("E32: Catch-up Latency vs Staleness — LoCoMo (qwen7b)", fontsize=11)
    fig.tight_layout()
    for ext in ["pdf", "png"]:
        fig.savefig(FIG_DIR / f"e32_staleness_latency.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Latency figure saved → figures/fidelity/e32_staleness_latency.pdf")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="E32: staleness cost")
    ap.add_argument("--mode", choices=["quality", "latency", "analysis"], required=True)
    ap.add_argument("--workload", choices=["locomo", "egoschema", "both"],
                    default="locomo",
                    help="Workload for quality mode (ignored for latency/analysis).")
    args = ap.parse_args()

    if args.mode == "quality":
        if args.workload in ("locomo", "both"):
            run_quality_locomo()
        if args.workload in ("egoschema", "both"):
            run_quality_egoschema()
    elif args.mode == "latency":
        run_latency()
    elif args.mode == "analysis":
        run_analysis()
        make_plots()


if __name__ == "__main__":
    main()
