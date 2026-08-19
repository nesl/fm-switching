"""
Phase 0a — Infini-THOR multi-model audit.
Runs the Infini-THOR regime check on a fixed subset under both models.

Conditions: blind, window-10, summary-80, summary-200, full
  + cross-{other}-sum80 / cross-{other}-sum200 when the other model's
    summary cache already exists (auto-detected).
Scoring: identical to frontier_infinithor.py (exact + lazy LLM judge)

Incremental: if the result file already exists, only missing conditions
per item are computed and the file is updated.

Usage:
  conda run -n fmtk python experiments/phase0a_infinithor.py --model qwen7b
  conda run -n fmtk python experiments/phase0a_infinithor.py --model mistral7b
  # extended n=60 gate:
  conda run -n fmtk python experiments/phase0a_infinithor.py --model qwen7b --subset infinithor_60
  conda run -n fmtk python experiments/phase0a_infinithor.py --model mistral7b --subset infinithor_60
"""

import argparse
import ast
import csv
import gc
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import torch
from scipy import stats as scipy_stats

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

DATA_DIR    = ROOT / "data" / "infinithor"
SUBSET_DIR  = ROOT / "data" / "audit_subsets" / "phase0a"
OUT_DIR     = ROOT / "results" / "phase0a"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = {
    "qwen7b":    "Qwen/Qwen2.5-7B-Instruct",
    "mistral7b": "mistralai/Mistral-7B-Instruct-v0.2",
}
OTHER_MODEL = {"qwen7b": "mistral7b", "mistral7b": "qwen7b"}

CONDITIONS = ["blind", "window-10", "summary-80", "summary-200", "full"]
WINDOW_K   = 10

# Prompts — identical to frontier_infinithor.py
FULL_PROMPT = (
    "You are reviewing a log of a robot's actions in a household environment.\n\n"
    "=== TRAJECTORY LOG ===\n{context}\n=== END LOG ===\n\n"
    "Question: {question}\n\n"
    "Answer with only the object or location name, as concisely as possible "
    "(e.g. 'SideTable', 'Dresser', 'Pen'). Do not explain.\nAnswer:"
)
BLIND_PROMPT = (
    "Question about a household robot's past actions: {question}\n\n"
    "Answer with only the object or location name, as concisely as possible. "
    "Do not explain.\nAnswer:"
)
SUMMARY_PROMPT_TPLT = (
    "Summarize the following robot action log in plain English, preserving the "
    "names of all objects and the receptacles they were placed on or picked from. "
    "Under {max_tokens} tokens.\n\n{context}\n\nSummary:"
)
JUDGE_PROMPT = (
    "Is '{pred}' the same object or location as '{gold}'? "
    "Allow minor spelling variants (e.g. 'SideTable' = 'Side Table'). "
    "Reply YES or NO only."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(s):
    return re.sub(r"[\s_-]+", "", str(s).lower().strip())

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


# ── Trajectory loading ────────────────────────────────────────────────────────

def load_trajectory(traj_id):
    for d in (DATA_DIR / "traj_test", DATA_DIR / "traj"):
        p = d / f"{traj_id}.txt"
        if p.exists():
            raw = p.read_text(encoding="utf-8", errors="replace")
            # Strip image placeholders
            raw = re.sub(r"<image>", "", raw)
            # Strip vision tokens
            raw = re.sub(r"<\|[a-z_]+\|>", " | ", raw)
            return raw.strip()
    return None

def load_subset_rows(subset_path):
    sub = json.loads(subset_path.read_text())
    mc_csv = DATA_DIR / "qa_set_nsieh_multi_clue.csv"
    id_to_row = {}
    with open(mc_csv) as f:
        for row in csv.DictReader(f):
            id_to_row[row["qid"]] = row
    result = []
    for qid in sub["ids"]:
        row = id_to_row.get(qid)
        if row is None:
            print(f"  WARNING: {qid} not found in CSV", flush=True)
            continue
        traj_id = qid.rsplit("_q", 1)[0]
        traj = load_trajectory(traj_id)
        if traj is None:
            print(f"  WARNING: trajectory {traj_id} not found", flush=True)
            continue
        result.append({
            "qid":          qid,
            "traj_id":      traj_id,
            "question":     row["question"],
            "answer":       row["answer"],
            "num_evidence": int(row.get("num_evidence", 1)),
            "gt_steps":     row.get("gt_steps", ""),
            "traj_text":    traj,
        })
    return result

def build_context(cond, traj_text, sum80, sum200):
    if cond == "blind":
        return None
    if cond == "window-10":
        lines = [l for l in traj_text.splitlines() if l.strip()]
        return "\n".join(lines[-WINDOW_K:])
    if cond == "summary-80":
        return sum80
    if cond == "summary-200":
        return sum200
    if cond == "full":
        return traj_text
    return None

def salient_receptacles(traj_text, k=3):
    acts = re.findall(r"PutObject\s+\S+\s+(\S+)", traj_text)
    return {r for r, _ in Counter(acts).most_common(k)}


# ── LLM ──────────────────────────────────────────────────────────────────────

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

def _run(model, tok, prompt, max_new=30):
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

def score_answer(pred, gold, model, tok):
    p_n, g_n = _normalize(pred), _normalize(gold)
    if g_n == p_n or g_n in p_n or p_n in g_n:
        return 1, 1, 0.0
    resp, lat = _run(model, tok, JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4)
    return 0, int(resp.upper().startswith("YES")), lat

def summarize(model, tok, traj_text, max_tokens):
    prompt = SUMMARY_PROMPT_TPLT.format(max_tokens=max_tokens, context=traj_text)
    text, _ = _run(model, tok, prompt, max_new=max_tokens + 40)
    return text


# ── Main audit ────────────────────────────────────────────────────────────────

def run(model_slug, subset_name):
    model_id  = MODELS[model_slug]
    other     = OTHER_MODEL[model_slug]
    subset_path = SUBSET_DIR / f"{subset_name}.json"
    if not subset_path.exists():
        raise FileNotFoundError(f"Subset not found: {subset_path}")

    items = load_subset_rows(subset_path)
    n_subset = len(items)
    print(f"Loaded {n_subset} items from {subset_name}", flush=True)

    # Determine output path and load any existing result for incremental mode
    out_path = OUT_DIR / f"infinithor_{model_slug}_n{n_subset}.json"
    existing_conds = {}  # qid -> {cond: entry}
    if out_path.exists():
        old = json.loads(out_path.read_text())
        for r in old.get("records", []):
            existing_conds[r["qid"]] = r.get("conditions", {})
        print(f"  Incremental mode: loaded {len(existing_conds)} existing records", flush=True)

    model, tok = load_llm(model_id)

    # Own summary caches
    sum_cache_80  = OUT_DIR / f"infinithor_sum80_{model_slug}.json"
    sum_cache_200 = OUT_DIR / f"infinithor_sum200_{model_slug}.json"
    sums80  = json.loads(sum_cache_80.read_text())  if sum_cache_80.exists()  else {}
    sums200 = json.loads(sum_cache_200.read_text()) if sum_cache_200.exists() else {}

    to_gen = [it for it in items if it["qid"] not in sums80]
    if to_gen:
        print(f"  Generating {len(to_gen)} summaries …", flush=True)
    for it in to_gen:
        sums80[it["qid"]]  = summarize(model, tok, it["traj_text"], 80)
        sums200[it["qid"]] = summarize(model, tok, it["traj_text"], 200)
        _save_json(sum_cache_80,  sums80)
        _save_json(sum_cache_200, sums200)

    # Cross-model summary caches (other model must have run first)
    cross_cache_80  = OUT_DIR / f"infinithor_sum80_{other}.json"
    cross_cache_200 = OUT_DIR / f"infinithor_sum200_{other}.json"
    cross_sums80  = json.loads(cross_cache_80.read_text())  if cross_cache_80.exists()  else {}
    cross_sums200 = json.loads(cross_cache_200.read_text()) if cross_cache_200.exists() else {}
    cross_available = bool(cross_sums80)
    CROSS_CONDITIONS = [f"cross-{other}-sum80", f"cross-{other}-sum200"] if cross_available else []
    if cross_available:
        print(f"  Cross conditions enabled: {CROSS_CONDITIONS}", flush=True)

    ALL_CONDITIONS = CONDITIONS + CROSS_CONDITIONS

    records = []
    latencies = defaultdict(list)

    for i, it in enumerate(items):
        qid       = it["qid"]
        gold      = it["answer"]
        traj_text = it["traj_text"]

        # Salience: gold is stored as stringified list e.g. "['SideTable']"; unwrap for comparison
        try:
            gold_unwrapped = ast.literal_eval(gold)
            gold_str = gold_unwrapped[0] if isinstance(gold_unwrapped, list) else str(gold_unwrapped)
        except Exception:
            gold_str = str(gold)
        is_salient = gold_str in salient_receptacles(traj_text)

        # Evidence distance
        try:
            gt = ast.literal_eval(it["gt_steps"]) if it["gt_steps"] else []
        except Exception:
            gt = []
        traj_lines = [l for l in traj_text.splitlines() if l.strip()]
        if gt:
            max_step = max(gt) if isinstance(gt[0], int) else max(int(s) for s in gt)
            dist = len(traj_lines) - max_step
            dist_bin = "near" if dist <= 5 else ("mid" if dist <= 20 else "far")
        else:
            dist, dist_bin = -1, "not_found"

        tok_count = len(tok.encode(traj_text, add_special_tokens=False))

        # Start from existing record if available (incremental)
        prior = existing_conds.get(qid, {})
        rec = {
            "qid":          qid,
            "traj_id":      it["traj_id"],
            "question":     it["question"],
            "gold":         gold,
            "num_evidence": it["num_evidence"],
            "is_salient":   is_salient,
            "traj_tokens":  tok_count,
            "dist_from_end": dist,
            "distance_bin": dist_bin,
            "conditions":   dict(prior),
        }

        todo = [c for c in ALL_CONDITIONS if c not in prior]
        for cond in todo:
            if cond.startswith("cross-"):
                ctx80  = cross_sums80.get(qid, "")
                ctx200 = cross_sums200.get(qid, "")
                ctx = ctx80 if cond.endswith("sum80") else ctx200
                prompt = FULL_PROMPT.format(context=ctx, question=it["question"])
            else:
                ctx = build_context(cond, traj_text, sums80.get(qid, ""), sums200.get(qid, ""))
                if cond == "blind":
                    prompt = BLIND_PROMPT.format(question=it["question"])
                else:
                    prompt = FULL_PROMPT.format(context=ctx, question=it["question"])
            pred, lat_ans = _run(model, tok, prompt, max_new=20)
            pred = pred.split("\n")[0].strip()
            em, jd, lat_j = score_answer(pred, gold, model, tok)
            latencies[cond].append(lat_ans + lat_j)
            rec["conditions"][cond] = {"pred": pred, "exact": em, "correct": jd}

        sal_tag = "salient" if is_salient else "non-sal"
        full_c = rec["conditions"].get("full", {}).get("correct", "?")
        s80_c  = rec["conditions"].get("summary-80", {}).get("correct", "?")
        print(f"  {i+1:2d}/{n_subset} [{sal_tag}] [{dist_bin:8s}] "
              f"full={full_c} s80={s80_c}"
              + (f" [+{len(todo)} new conds]" if todo else " [cached]"),
              flush=True)
        records.append(rec)

    peak_gb = torch.cuda.max_memory_allocated() / 1e9
    mean_lat = {c: sum(v)/len(v) for c, v in latencies.items() if v}

    # ── Stats ─────────────────────────────────────────────────────────────────
    ns = [r for r in records if r["is_salient"] is False]
    n_all, n_ns = len(records), len(ns)

    # Determine which conditions are present across all records
    present_conds = [c for c in ALL_CONDITIONS
                     if all(c in r["conditions"] for r in records)]

    def _acc(recs, cond):
        return [r["conditions"][cond]["correct"] for r in recs if cond in r["conditions"]]

    print(f"\n{'='*70}")
    print(f"INFINI-THOR PHASE0a RESULTS — {model_slug.upper()}  (n_all={n_all}, n_ns={n_ns})")
    print(f"{'='*70}")
    for label, recs in [("ALL", records), ("NON-SALIENT", ns)]:
        n = len(recs)
        if n == 0:
            continue
        full_v = _acc(recs, "full")
        full_p = sum(full_v) / n
        print(f"\n  [{label}] n={n}")
        for cond in present_conds:
            v = _acc(recs, cond)
            p, lo, hi = wilson_ci(sum(v), len(v))
            diff = full_p - p if cond != "full" else 0.0
            print(f"    {cond:<28} {p:6.3f}  [{lo:.3f}, {hi:.3f}]  {diff:+8.3f}")
        for cond in [c for c in present_conds if c != "full"]:
            v = _acc(recs, cond)
            chi2, p = mcnemar(full_v, v)
            sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
            print(f"    full vs {cond}: chi2={chi2:.2f}  p={p:.4f}  {sig}")

    print(f"\n  GPU peak: {peak_gb:.1f} GB")

    out = {
        "metadata": {
            "model_slug":   model_slug,
            "model_id":     model_id,
            "workload":     "infinithor",
            "n":            n_all,
            "n_nonsalient": n_ns,
            "subset":       subset_name,
            "conditions":   present_conds,
            "cross_conditions": CROSS_CONDITIONS,
            "scorer":       "exact_normalized_plus_lazy_llm_judge",
            "gpu_peak_gb":  round(peak_gb, 2),
            "mean_latency_per_cond_s": {c: round(v, 3) for c, v in mean_lat.items()},
            "timestamp":    datetime.now().isoformat(),
        },
        "records": records,
    }
    _save_json(out_path, out)
    print(f"Saved → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODELS.keys()), required=True)
    ap.add_argument("--subset", default="infinithor_40",
                    help="Subset name (no .json) in data/audit_subsets/phase0a/")
    args = ap.parse_args()
    run(args.model, args.subset)


if __name__ == "__main__":
    main()
