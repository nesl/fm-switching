"""
E29 — Tier-heterogeneous fidelity audit, EgoSchema workload.

Instruments: same as multimodel_egoschema.py (identical scorer, prompts).
Model pair: qwen3b (device tier) and qwen7b (edge/cloud tier).
Subset: data/audit_subsets/phase0a/egoschema_60.json (n=60).

Conditions per model:
  blind, window-10, summary-80, summary-200, full  (own summaries)
  cross-qwen7b-sum80, cross-qwen7b-sum200          (qwen3b reader, qwen7b summaries)
  cross-qwen3b-sum80, cross-qwen3b-sum200          (qwen7b reader, qwen3b summaries)

Cross conditions are skipped with a warning if the other model's summary cache does not exist.

Usage:
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk python experiments/fidelity/e29_egoschema.py --model qwen3b
  CUDA_VISIBLE_DEVICES=1 conda run -n fmtk python experiments/fidelity/e29_egoschema.py --model qwen7b
"""

import argparse
import gc
import json
import math
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
from premise_egoschema import LETTERS, build_egoschema_prompt, load_egoschema, parse_choice
from _provenance import stamp

DATA_DIR      = ROOT / "data" / "egoschema"
CAPTION_CACHE = ROOT / "results" / "fidelity" / "caches" / "captions_cache.json"
SUBSET_PATH   = ROOT / "data" / "audit_subsets" / "phase0a" / "egoschema_60.json"
# qwen7b EgoSchema summary caches (from phase0a run)
SUM80_7B_CACHE  = ROOT / "results" / "fidelity" / "caches" / "summaries_cache_80.json"
SUM200_7B_CACHE = ROOT / "results" / "fidelity" / "caches" / "summaries_cache_200.json"

OUT_DIR = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = {
    "qwen3b": "Qwen/Qwen2.5-3B-Instruct",
    "qwen7b": "Qwen/Qwen2.5-7B-Instruct",
}

CONDITIONS = ["blind", "window-10", "summary-80", "summary-200", "full"]
CROSS_3B_ON_7B = ["cross-qwen7b-sum80", "cross-qwen7b-sum200"]
CROSS_7B_ON_3B = ["cross-qwen3b-sum80", "cross-qwen3b-sum200"]

SUMMARY_PROMPT_TPLT = (
    "Summarize the following video frame descriptions in approximately {max_tokens} tokens. "
    "Preserve the main actions, objects, and people involved.\n\n"
    "Frame descriptions:\n{context}\n\nSummary:"
)


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


def load_subset_items():
    sub = json.loads(SUBSET_PATH.read_text())
    subset_ids = set(sub["ids"])
    all_questions = load_egoschema(DATA_DIR / "questions.json", DATA_DIR / "subset_answers.json")
    captions = json.loads(CAPTION_CACHE.read_text()) if CAPTION_CACHE.exists() else {}
    items = []
    for q in all_questions:
        uid = q["q_uid"]
        if uid not in subset_ids:
            continue
        if uid not in captions:
            print(f"  WARNING: no captions for {uid}, skipping", flush=True)
            continue
        items.append({
            "uid":         uid,
            "question":    q["question"],
            "options":     q["options"],
            "gold_letter": LETTERS[q["gold_idx"]],
            "gold_idx":    q["gold_idx"],
            "captions":    captions[uid],
        })
    return items


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

def _run(model, tok, prompt, max_new=10):
    try:
        msgs = [{"role": "user", "content": prompt}]
        fmt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    except Exception:
        fmt = prompt
    inp = tok(fmt, return_tensors="pt", truncation=True, max_length=28000).to(model.device)
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            **inp, max_new_tokens=max_new, do_sample=False,
            pad_token_id=tok.eos_token_id)
    lat = time.perf_counter() - t0
    text = tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return text, lat

def summarize_captions(model, tok, captions, max_tokens):
    context = "\n".join(f"{i+1}. {c}" for i, c in enumerate(captions))
    prompt = SUMMARY_PROMPT_TPLT.format(max_tokens=max_tokens, context=context)
    text, _ = _run(model, tok, prompt, max_new=max_tokens + 40)
    return text

def build_prompt_for_cond(cond, item, sum80, sum200):
    if cond == "window-10":
        sel = item["captions"][-10:]
        header = (
            "You are answering a multiple-choice question about a first-person "
            "(egocentric) video. Below are chronological text descriptions of frames "
            "sampled from the video, followed by a question and five options."
        )
        lines = "\n".join(f"{i+1}. {c}" for i, c in enumerate(sel))
        obs = f"\n\nFrame descriptions (chronological):\n{lines}"
        opt_block = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(item["options"]))
        instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
        return f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"
    if cond in ("blind", "full"):
        return build_egoschema_prompt(cond, item["captions"], item["question"], item["options"])
    # Summary conditions (own or cross)
    summary = sum80 if cond in ("summary-80", "cross-qwen7b-sum80", "cross-qwen3b-sum80") else sum200
    header = (
        "You are answering a multiple-choice question about a first-person "
        "(egocentric) video. Below is a summary of the video, followed by a question and five options."
    )
    obs = f"\n\nVideo summary:\n{summary}" if summary else "\n\n(No summary available.)"
    opt_block = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(item["options"]))
    instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
    return f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"


def run(model_slug):
    model_id = MODELS[model_slug]
    items = load_subset_items()
    print(f"Loaded {len(items)} items from subset", flush=True)

    model, tok = load_llm(model_id)

    # qwen7b reuses existing phase0a summary caches; qwen3b generates its own
    if model_slug == "qwen7b":
        sums80_7b  = json.loads(SUM80_7B_CACHE.read_text())
        sums200_7b = json.loads(SUM200_7B_CACHE.read_text())
        sums80_own  = {it["uid"]: sums80_7b.get(it["uid"], "")  for it in items}
        sums200_own = {it["uid"]: sums200_7b.get(it["uid"], "") for it in items}
    else:
        cache80  = OUT_DIR / f"egoschema_sum80_{model_slug}.json"
        cache200 = OUT_DIR / f"egoschema_sum200_{model_slug}.json"
        sums80_own  = json.loads(cache80.read_text())  if cache80.exists()  else {}
        sums200_own = json.loads(cache200.read_text()) if cache200.exists() else {}
        to_gen = [it for it in items if it["uid"] not in sums80_own]
        if to_gen:
            print(f"  Generating summaries for {len(to_gen)} clips …", flush=True)
        for it in to_gen:
            sums80_own[it["uid"]]  = summarize_captions(model, tok, it["captions"], 80)
            sums200_own[it["uid"]] = summarize_captions(model, tok, it["captions"], 200)
            _save_json(cache80,  sums80_own)
            _save_json(cache200, sums200_own)

    # Cross-model summaries
    if model_slug == "qwen3b":
        cross_conds = CROSS_3B_ON_7B
        _s80_7b  = json.loads(SUM80_7B_CACHE.read_text())
        _s200_7b = json.loads(SUM200_7B_CACHE.read_text())
        sums80_cross  = {it["uid"]: _s80_7b.get(it["uid"], "")  for it in items}
        sums200_cross = {it["uid"]: _s200_7b.get(it["uid"], "") for it in items}
    else:
        cache3b_80  = OUT_DIR / "egoschema_sum80_qwen3b.json"
        cache3b_200 = OUT_DIR / "egoschema_sum200_qwen3b.json"
        if cache3b_80.exists() and cache3b_200.exists():
            cross_conds = CROSS_7B_ON_3B
            sums80_cross  = json.loads(cache3b_80.read_text())
            sums200_cross = json.loads(cache3b_200.read_text())
        else:
            print("WARNING: qwen3b summary caches not found; skipping cross-qwen3b conditions. "
                  "Run qwen3b first, then re-run qwen7b.", flush=True)
            cross_conds   = []
            sums80_cross  = {}
            sums200_cross = {}

    conds = list(CONDITIONS) + cross_conds

    records = []
    latencies = defaultdict(list)

    for i, item in enumerate(items):
        uid  = item["uid"]
        gold = item["gold_letter"]
        rec = {
            "uid":        uid,
            "question":   item["question"],
            "gold":       gold,
            "conditions": {},
        }

        for cond in conds:
            # Select summary for this condition
            if cond in ("summary-80", "cross-qwen7b-sum80", "cross-qwen3b-sum80"):
                s80  = sums80_cross.get(uid, "") if cond.startswith("cross-") else sums80_own.get(uid, "")
                s200 = ""
            else:
                s80  = ""
                s200 = sums200_cross.get(uid, "") if cond.startswith("cross-") else sums200_own.get(uid, "")
            # Combine for prompt builder
            prompt = build_prompt_for_cond(cond, item, sums80_own.get(uid, ""), sums200_own.get(uid, ""))
            # Override for cross conditions
            if cond.startswith("cross-"):
                if "sum80" in cond:
                    summary = sums80_cross.get(uid, "")
                else:
                    summary = sums200_cross.get(uid, "")
                header = (
                    "You are answering a multiple-choice question about a first-person "
                    "(egocentric) video. Below is a summary of the video, followed by a question and five options."
                )
                obs = f"\n\nVideo summary:\n{summary}" if summary else "\n\n(No summary available.)"
                opt_block = "\n".join(f"{LETTERS[j]}. {opt}" for j, opt in enumerate(item["options"]))
                instr = "\n\nSelect the single best answer. Respond with ONLY the letter (A, B, C, D, or E)."
                prompt = f"{header}{obs}\n\nQuestion: {item['question']}\n\nOptions:\n{opt_block}{instr}\nAnswer:"

            raw, lat = _run(model, tok, prompt, max_new=10)
            pred = parse_choice(raw) or "?"
            correct = int(pred == gold)
            latencies[cond].append(lat)
            rec["conditions"][cond] = {"pred": pred, "raw": raw, "correct": correct}

        print(f"  {i+1:2d}/{len(items)} gold={gold} "
              f"full={rec['conditions']['full']['correct']} "
              f"s80={rec['conditions']['summary-80']['correct']} "
              f"blind={rec['conditions']['blind']['correct']}", flush=True)
        records.append(rec)

    peak_gb = torch.cuda.max_memory_allocated() / 1e9
    mean_lat = {c: sum(v)/len(v) for c, v in latencies.items() if v}
    n = len(records)

    def _acc(cond):
        return [r["conditions"][cond]["correct"] for r in records if cond in r["conditions"]]

    full_v = _acc("full")
    print(f"\n{'='*70}")
    print(f"E29 EGOSCHEMA RESULTS — {model_slug.upper()}  (n={n})")
    print(f"{'='*70}")
    full_p = sum(full_v) / n
    print(f"  {'cond':<28} {'acc':>6}  {'CI':>22}  {'vs-full':>9}")
    for cond in conds:
        v = _acc(cond)
        if not v:
            continue
        p, lo, hi = wilson_ci(sum(v), len(v))
        diff = full_p - p if cond != "full" else 0.0
        print(f"  {cond:<28} {p:6.3f}  [{lo:.3f}, {hi:.3f}]  {diff:+9.3f}")

    print("\n  McNemar (full vs condition):")
    for cond in conds:
        if cond == "full":
            continue
        v = _acc(cond)
        if not v:
            continue
        chi2, p = mcnemar(full_v, v)
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(f"    full vs {cond}: chi2={chi2:.2f}  p={p:.4f}  {sig}")

    print(f"\n  GPU peak: {peak_gb:.1f} GB")

    out = {
        "metadata": {
            "experiment":  "E29",
            "model_slug":  model_slug,
            "model_id":    model_id,
            "workload":    "egoschema",
            "n":           n,
            "subset":      "egoschema_60",
            "conditions":  conds,
            "cross_conditions": cross_conds,
            "scorer":      "mcq_letter_parse_choice",
            "caption_source":  "cached_qwen25vl3b_16frames",
            "summary_source":  "qwen7b_cache" if model_slug == "qwen7b" else f"{model_slug}_generated",
            "gpu_peak_gb": round(peak_gb, 2),
            "mean_latency_per_cond_s": {c: round(v, 3) for c, v in mean_lat.items()},
            "timestamp":   datetime.now().isoformat(),
        },
        "records": records,
        "_provenance": stamp(
            script="e29_egoschema.py",
            model=model_slug,
            device="nvidia_rtx_a6000",
            n=n,
            args={"model": model_slug},
        ),
    }
    out_path = OUT_DIR / f"egoschema_{model_slug}_n{n}.json"
    _save_json(out_path, out)
    print(f"Saved → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODELS.keys()), required=True)
    args = ap.parse_args()
    run(args.model)


if __name__ == "__main__":
    main()
