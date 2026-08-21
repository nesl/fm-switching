"""
E29 — Tier-heterogeneous fidelity audit, LoCoMo workload.

Instruments: same as multimodel_locomo.py (identical scorer, judge, prompts).
Model pair: qwen3b (device tier) and qwen7b (edge/cloud tier).
Subset: data/audit_subsets/phase0a/locomo_100.json (n=100, cat=1).

Conditions per model:
  blind, window-10, summary-80, summary-200, full  (own summaries)
  cross-qwen7b-sum80, cross-qwen7b-sum200          (qwen3b reader, qwen7b summaries)
  cross-qwen3b-sum80, cross-qwen3b-sum200          (qwen7b reader, qwen3b summaries — requires qwen3b run first)

Cross conditions are skipped with a warning if the other model's summary cache does not exist.

Usage:
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk python experiments/fidelity/e29_locomo.py --model qwen3b
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk python experiments/fidelity/e29_locomo.py --model qwen7b
"""

import argparse
import gc
import json
import math
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch
from scipy import stats as scipy_stats

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

DATA_PATH   = ROOT / "data" / "locomo" / "locomo10.json"
SUM80_7B    = ROOT / "results" / "fidelity" / "caches" / "locomo_summaries_80.json"
SUM200_7B   = ROOT / "results" / "fidelity" / "caches" / "locomo_summaries_200.json"
SUBSET_PATH = ROOT / "data" / "audit_subsets" / "phase0a" / "locomo_100.json"
OUT_DIR     = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = {
    "qwen3b": "Qwen/Qwen2.5-3B-Instruct",
    "qwen7b": "Qwen/Qwen2.5-7B-Instruct",
}

CONDITIONS = ["blind", "window-10", "summary-80", "summary-200", "full"]
CROSS_3B_ON_7B = ["cross-qwen7b-sum80", "cross-qwen7b-sum200"]
CROSS_7B_ON_3B = ["cross-qwen3b-sum80", "cross-qwen3b-sum200"]

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
PRESENCE_PROMPT = (
    "Does the following text contain the answer or fact '{gold}'?\n"
    "Text: {text}\n\n"
    "Reply YES or NO only."
)
SUMMARY_PROMPT = (
    "Summarize the following conversation history in approximately {max_tokens} tokens. "
    "Preserve all named facts, dates, and specific details mentioned.\n\n"
    "{context}\n\nSummary:"
)


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
    centre = (p + z**2 / (2*n)) / denom
    margin = z * math.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    return p, max(0, centre - margin), min(1, centre + margin)

def mcnemar(va, vb):
    b = sum(1 for a, b_ in zip(va, vb) if a == 1 and b_ == 0)
    c = sum(1 for a, b_ in zip(va, vb) if a == 0 and b_ == 1)
    if b + c == 0:
        return float("nan"), float("nan")
    chi2 = (abs(b - c) - 1)**2 / (b + c)
    p = 1 - scipy_stats.chi2.cdf(chi2, df=1)
    return chi2, p


def load_subset():
    sub = json.loads(SUBSET_PATH.read_text())
    return set(sub["ids"]), sub

def load_data(subset_ids):
    raw = json.loads(DATA_PATH.read_text())
    questions, convs = [], {}
    for item in raw:
        cid = item["sample_id"]
        c   = item["conversation"]
        sessions, dates, all_turns = [], [], []
        i = 1
        while f"session_{i}" in c:
            turns = c[f"session_{i}"]
            sessions.append(turns)
            dates.append(c.get(f"session_{i}_date_time", ""))
            all_turns.extend(turns)
            i += 1
        lines = []
        for si, (sess, date) in enumerate(zip(sessions, dates)):
            hdr = f"[Session {si+1}" + (f" — {date}]" if date else "]")
            lines.append(hdr)
            for t in sess:
                lines.append(f"{t['speaker']}: {t['text']}")
            lines.append("")
        full_text = "\n".join(lines).strip()
        convs[cid] = {
            "sessions": sessions, "dates": dates,
            "all_turns": all_turns, "full_text": full_text,
        }
        for qi, qa in enumerate(item["qa"]):
            if qa["category"] != 1:
                continue
            uid = f"{cid}_q{qi:04d}"
            if uid in subset_ids:
                questions.append({
                    "q_uid":    uid,
                    "conv_id":  cid,
                    "question": qa["question"],
                    "gold":     str(qa["answer"]),
                    "evidence": qa.get("evidence", []),
                })
    return questions, convs

def ev_distance(evidence_list, all_turns):
    dia_to_idx = {t["dia_id"]: i for i, t in enumerate(all_turns)}
    idxs = [dia_to_idx[e] for e in evidence_list if e in dia_to_idx]
    if not idxs:
        return {"found": False, "turns_from_end": -1, "distance_bin": "not_found"}
    dist = len(all_turns) - 1 - max(idxs)
    bin_ = "near" if dist <= 5 else ("mid" if dist <= 20 else "far")
    return {"found": True, "turns_from_end": dist, "distance_bin": bin_}

def build_context(cond, conv):
    if cond == "blind":
        return ""
    if cond == "window-10":
        sess = conv["sessions"][-10:]
        d    = conv["dates"][-10:]
        lines = []
        for si, (s, date) in enumerate(zip(sess, d)):
            hdr = f"[Session {si+1}" + (f" — {date}]" if date else "]")
            lines.append(hdr)
            for t in s:
                lines.append(f"{t['speaker']}: {t['text']}")
            lines.append("")
        return "\n".join(lines).strip()
    if cond == "full":
        return conv["full_text"]
    return ""


def load_llm(model_id):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading {model_id} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.float16, device_map="cuda:0")
    model.eval()
    torch.cuda.reset_peak_memory_stats()
    return model, tok

def _run(model, tok, prompt, max_new=40):
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
            pad_token_id=tok.eos_token_id)
    latency = time.perf_counter() - t0
    text = tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return text, latency

def score(pred, gold, model, tok):
    p_n, g_n = _normalize(pred), _normalize(gold)
    if g_n in p_n or p_n in g_n:
        return 1, 1, 0.0
    resp, lat = _run(model, tok, JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4)
    return 0, int(resp.upper().startswith("YES")), lat

def check_presence(text, gold, model, tok):
    if _normalize(gold) in _normalize(text):
        return {"exact": True, "judge": True, "judge_called": False}
    resp, _ = _run(model, tok, PRESENCE_PROMPT.format(gold=gold, text=text[:3000]), max_new=4)
    return {"exact": False, "judge": resp.upper().startswith("YES"), "judge_called": True}

def generate_summaries(model, tok, convs, target_tokens, cache_path):
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        missing = [cid for cid in convs if cid not in cached]
        if not missing:
            print(f"  Summary cache complete ({len(cached)} convs): {cache_path.name}")
            return cached
        print(f"  Generating summaries for {len(missing)} missing convs …")
    else:
        cached = {}
        missing = list(convs.keys())
        print(f"  Generating summaries for {len(missing)} convs …")
    for cid in missing:
        full_text = convs[cid]["full_text"]
        prompt = SUMMARY_PROMPT.format(max_tokens=target_tokens, context=full_text)
        summary, _ = _run(model, tok, prompt, max_new=target_tokens + 40)
        cached[cid] = summary
        _save_json(cache_path, cached)
        print(f"    {cid}: {len(summary.split())} words", flush=True)
    return cached


def run(model_slug):
    model_id = MODELS[model_slug]
    subset_ids, _ = load_subset()
    questions, convs = load_data(subset_ids)
    print(f"Loaded {len(questions)} questions for {len(convs)} conversations", flush=True)

    # Load qwen7b summary caches (always available; used for cross conditions)
    sum80_7b  = json.loads(SUM80_7B.read_text())
    sum200_7b = json.loads(SUM200_7B.read_text())

    model, tok = load_llm(model_id)

    # Own summaries
    if model_slug == "qwen7b":
        sum80_own  = sum80_7b
        sum200_own = sum200_7b
    else:
        sum80_own  = generate_summaries(model, tok, convs, 80,
                         OUT_DIR / f"locomo_sum80_{model_slug}.json")
        sum200_own = generate_summaries(model, tok, convs, 200,
                         OUT_DIR / f"locomo_sum200_{model_slug}.json")

    # Cross-model summary caches
    # qwen3b reads qwen7b summaries (always available)
    # qwen7b reads qwen3b summaries (available only if qwen3b was run first)
    if model_slug == "qwen3b":
        cross_conds = CROSS_3B_ON_7B
        sum80_cross  = sum80_7b
        sum200_cross = sum200_7b
    else:
        cache3b_80  = OUT_DIR / "locomo_sum80_qwen3b.json"
        cache3b_200 = OUT_DIR / "locomo_sum200_qwen3b.json"
        if cache3b_80.exists() and cache3b_200.exists():
            cross_conds  = CROSS_7B_ON_3B
            sum80_cross  = json.loads(cache3b_80.read_text())
            sum200_cross = json.loads(cache3b_200.read_text())
        else:
            print("WARNING: qwen3b summary caches not found; skipping cross-qwen3b conditions. "
                  "Run qwen3b first, then re-run qwen7b.", flush=True)
            cross_conds  = []
            sum80_cross  = {}
            sum200_cross = {}

    conds = list(CONDITIONS) + cross_conds

    tok_len = {cid: len(tok.encode(cv["full_text"], add_special_tokens=False))
               for cid, cv in convs.items()}

    records = []
    latencies = defaultdict(list)

    for i, q in enumerate(questions):
        cid  = q["conv_id"]
        cv   = convs[cid]
        gold = q["gold"]
        ev   = ev_distance(q["evidence"], cv["all_turns"])

        rec = {
            "q_uid":             q["q_uid"],
            "conv_id":           cid,
            "question":          q["question"],
            "gold":              gold,
            "evidence_distance": ev,
            "full_context_tokens": tok_len[cid],
            "conditions":        {},
        }

        for cond in conds:
            if cond in ("cross-qwen7b-sum80", "cross-qwen3b-sum80"):
                ctx = sum80_cross.get(cid, "")
            elif cond in ("cross-qwen7b-sum200", "cross-qwen3b-sum200"):
                ctx = sum200_cross.get(cid, "")
            elif cond == "summary-80":
                ctx = sum80_own.get(cid, "")
            elif cond == "summary-200":
                ctx = sum200_own.get(cid, "")
            else:
                ctx = build_context(cond, cv)

            if cond == "blind":
                prompt = BLIND_PROMPT.format(question=q["question"])
            else:
                prompt = QA_PROMPT.format(context=ctx, question=q["question"])

            pred, lat_ans = _run(model, tok, prompt, max_new=40)
            pred = pred.split("\n")[0].strip()
            em, jd, lat_judge = score(pred, gold, model, tok)
            latencies[cond].append(lat_ans + lat_judge)
            rec["conditions"][cond] = {"pred": pred, "exact": em, "correct": jd}

        # Omission audit
        presence = {}
        for rep, text in [("full", cv["full_text"]),
                           ("summary-80", sum80_own.get(cid, "")),
                           ("summary-200", sum200_own.get(cid, ""))]:
            presence[rep] = check_presence(text, gold, model, tok)
        rec["gold_presence"] = presence

        print(f"  {i+1:3d}/{len(questions)} [{ev.get('distance_bin','?'):8s}] "
              f"full={rec['conditions']['full']['correct']} "
              f"s80={rec['conditions']['summary-80']['correct']} "
              f"gold_in_s80={presence['summary-80']['judge']}", flush=True)
        records.append(rec)

    peak_gb  = torch.cuda.max_memory_allocated() / 1e9
    alloc_gb = torch.cuda.memory_allocated() / 1e9
    print(f"\nGPU peak: {peak_gb:.1f} GB  current: {alloc_gb:.1f} GB")

    mean_lat = {c: sum(v)/len(v) for c, v in latencies.items() if v}
    n = len(records)

    def _acc(cond):
        return [r["conditions"][cond]["correct"] for r in records if cond in r["conditions"]]

    full_v = _acc("full")
    print(f"\n{'='*70}")
    print(f"E29 LOCOMO RESULTS — {model_slug.upper()}  (n={n})")
    print(f"{'='*70}")
    print(f"{'cond':<28} {'acc':>6}  {'CI':>22}  {'vs-full':>9}")
    full_p = sum(full_v) / n
    for cond in conds:
        v = _acc(cond)
        if not v:
            continue
        p, lo, hi = wilson_ci(sum(v), len(v))
        diff = full_p - p if cond != "full" else 0.0
        print(f"  {cond:<26} {p:6.3f}  [{lo:.3f}, {hi:.3f}]  {diff:+9.3f}")

    print("\n  McNemar (full vs condition):")
    for cond in conds:
        if cond == "full":
            continue
        v = _acc(cond)
        if not v:
            continue
        chi2, p = mcnemar(full_v, v)
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(f"    full vs {cond:<26}: chi2={chi2:.2f}  p={p:.4f}  {sig}")

    out = {
        "metadata": {
            "experiment":  "E29",
            "model_slug":  model_slug,
            "model_id":    model_id,
            "workload":    "locomo",
            "n":           n,
            "subset":      "locomo_100",
            "conditions":  conds,
            "cross_conditions": cross_conds,
            "scorer":      "exact_normalized_substring_plus_lazy_llm_judge",
            "gpu_peak_gb": round(peak_gb, 2),
            "mean_latency_per_cond_s": {c: round(v, 3) for c, v in mean_lat.items()},
            "timestamp":   datetime.now().isoformat(),
        },
        "records": records,
        "_provenance": stamp(
            script="e29_locomo.py",
            model=model_slug,
            device="nvidia_rtx_a6000",
            n=n,
            args={"model": model_slug},
        ),
    }
    out_path = OUT_DIR / f"locomo_{model_slug}_n{n}.json"
    _save_json(out_path, out)
    print(f"\nSaved → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODELS.keys()), required=True)
    args = ap.parse_args()
    run(args.model)


if __name__ == "__main__":
    main()
