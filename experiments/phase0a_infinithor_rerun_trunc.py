"""
Reruns the `full` condition for the three Infini-THOR trajectories that were
silently truncated at the 28000-token cutoff in the n=60 audit.

Qwen2.5-7B-Instruct (128K context): all three fit → reruns at max_length=90000.
Mistral-7B-Instruct-v0.2 (32K context): all three exceed 32K → reported as
context-exceeded, no inference run.

Output: results/phase0a/infinithor_truncated_rerun.json
"""

import ast
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import torch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

DATA_DIR = ROOT / "data" / "infinithor"
OUT_PATH = ROOT / "results" / "phase0a" / "infinithor_truncated_rerun.json"

TRUNCATED_QIDS = [
    "floorplan210_19_618_1746864406_q1",
    "floorplan230_9_507_1746931717_q23",
    "floorplan210_19_618_1746864406_q18",
]

MODELS = {
    "qwen7b":    ("Qwen/Qwen2.5-7B-Instruct",          128000),
    "mistral7b": ("mistralai/Mistral-7B-Instruct-v0.2", 32768),
}

FULL_PROMPT = (
    "You are reviewing a log of a robot's actions in a household environment.\n\n"
    "=== TRAJECTORY LOG ===\n{context}\n=== END LOG ===\n\n"
    "Question: {question}\n\n"
    "Answer with only the object or location name, as concisely as possible "
    "(e.g. 'SideTable', 'Dresser', 'Pen'). Do not explain.\nAnswer:"
)
JUDGE_PROMPT = (
    "Is '{pred}' the same object or location as '{gold}'? "
    "Allow minor spelling variants (e.g. 'SideTable' = 'Side Table'). "
    "Reply YES or NO only."
)


def _normalize(s):
    return re.sub(r"[\s_-]+", "", str(s).lower().strip())

def _save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)

def load_trajectory(traj_id):
    for d in (DATA_DIR / "traj_test", DATA_DIR / "traj"):
        p = d / f"{traj_id}.txt"
        if p.exists():
            raw = p.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"<image>", "", raw)
            raw = re.sub(r"<\|[a-z_]+\|>", " | ", raw)
            return raw.strip()
    return None

def load_items():
    mc_csv = DATA_DIR / "qa_set_nsieh_multi_clue.csv"
    id_to_row = {}
    with open(mc_csv) as f:
        for row in csv.DictReader(f):
            id_to_row[row["qid"]] = row
    items = []
    for qid in TRUNCATED_QIDS:
        row = id_to_row.get(qid)
        if row is None:
            print(f"  WARNING: {qid} not in CSV")
            continue
        traj_id = qid.rsplit("_q", 1)[0]
        traj = load_trajectory(traj_id)
        if traj is None:
            print(f"  WARNING: trajectory {traj_id} not found")
            continue
        items.append({"qid": qid, "traj_id": traj_id,
                      "question": row["question"], "answer": row["answer"],
                      "traj_text": traj})
    return items

def load_llm(model_id):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.float16, device_map="cuda:0")
    model.eval()
    torch.cuda.reset_peak_memory_stats()
    return model, tok

def _run(model, tok, prompt, max_new=20, max_length=90000):
    try:
        msgs = [{"role": "user", "content": prompt}]
        fmt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    except Exception:
        fmt = prompt
    inp = tok(fmt, return_tensors="pt", truncation=True, max_length=max_length).to(model.device)
    actual_len = inp["input_ids"].shape[1]
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    lat = time.perf_counter() - t0
    text = tok.decode(out[0][actual_len:], skip_special_tokens=True).strip()
    return text, lat, actual_len

def score_answer(pred, gold, model, tok):
    p_n, g_n = _normalize(pred), _normalize(gold)
    if g_n == p_n or g_n in p_n or p_n in g_n:
        return 1, 1
    resp, _, _ = _run(model, tok, JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4, max_length=256)
    return 0, int(resp.upper().startswith("YES"))

def run_model(model_slug, items, results):
    model_id, ctx_limit = MODELS[model_slug]
    print(f"\n=== {model_slug.upper()} (ctx={ctx_limit}) ===", flush=True)

    for it in items:
        qid = it["qid"]
        gold = it["answer"]
        try:
            gold_str = ast.literal_eval(gold)
            if isinstance(gold_str, list):
                gold_str = gold_str[0]
        except Exception:
            gold_str = str(gold)

        from transformers import AutoTokenizer
        tok_check = AutoTokenizer.from_pretrained(model_id)
        traj_tokens = len(tok_check.encode(it["traj_text"], add_special_tokens=False))
        prompt_est  = traj_tokens + 300  # rough overhead

        if prompt_est > ctx_limit:
            print(f"  {qid}: CONTEXT EXCEEDED ({prompt_est} > {ctx_limit})", flush=True)
            results.setdefault(qid, {})[model_slug] = {
                "status": "context_exceeded",
                "traj_tokens": traj_tokens,
                "ctx_limit": ctx_limit,
            }
            continue

        print(f"  {qid}: traj_tokens={traj_tokens}, running full condition …", flush=True)
        if not hasattr(run_model, "_model") or run_model._model_slug != model_slug:
            run_model._model, run_model._tok = load_llm(model_id)
            run_model._model_slug = model_slug

        model = run_model._model
        tok   = run_model._tok

        prompt = FULL_PROMPT.format(context=it["traj_text"], question=it["question"])
        pred, lat, actual_len = _run(model, tok, prompt, max_new=20, max_length=ctx_limit - 50)
        pred = pred.split("\n")[0].strip()
        em, jd = score_answer(pred, gold_str, model, tok)
        peak_gb = torch.cuda.max_memory_allocated() / 1e9

        print(f"    pred={pred!r}  gold={gold_str!r}  exact={em}  judge={jd}  "
              f"tokens={actual_len}  lat={lat:.1f}s  peak={peak_gb:.1f}GB", flush=True)

        results.setdefault(qid, {})[model_slug] = {
            "status": "ok",
            "traj_tokens": traj_tokens,
            "prompt_tokens": actual_len,
            "ctx_limit": ctx_limit,
            "pred": pred,
            "gold": gold_str,
            "exact": em,
            "judge_correct": jd,
            "latency_s": round(lat, 2),
        }

def main():
    items = load_items()
    print(f"Loaded {len(items)} truncated items", flush=True)

    results = {}
    for model_slug in ("qwen7b", "mistral7b"):
        run_model(model_slug, items, results)

    out = {
        "metadata": {
            "purpose": "rerun full condition at raised cutoff for truncated Infini-THOR items",
            "truncated_qids": TRUNCATED_QIDS,
            "timestamp": datetime.now().isoformat(),
        },
        "results": results,
    }
    _save_json(OUT_PATH, out)
    print(f"\nSaved → {OUT_PATH}")

if __name__ == "__main__":
    main()
