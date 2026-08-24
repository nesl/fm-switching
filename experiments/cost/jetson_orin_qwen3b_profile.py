"""
Jetson AGX Orin — Qwen2.5-3B-Instruct cold-prefill and warm-append profile.

Resolves ASSUMPTION A1 in E36: measures the qwen3b/qwen7b time ratio on the
Jetson directly so the 0.43–1.00 sensitivity range can be replaced with a
committed value.

Measurements (5 reps each, median + IQR):
  full_restore_ms    : cold prefill of L tokens, 1 new token generated (TTFT)
  incr_warm_ms       : warm-append TTFT — KV cache of L tokens already warm,
                       append ~200 new tokens, time only the append
  incr_cold_ms       : cold baseline — prefill L+200 tokens from scratch

Target L values: {1024, 4096, 8192, 16384}

After measurement, prints the 3B/7B time ratio at each L against the committed
qwen7b values from E23 (hardcoded below).

Protocol matches cost_profile.py / E23 so numbers are directly comparable:
  - HuggingFace transformers, float16, device_map=cuda:0
  - Corpus: LoCoMo turns (data/locomo/locomo10.json)
  - 120 s per-measurement timeout
  - SIGALRM-based timeout (Linux only)

Output: results/cost/profiles/jetson_orin_qwen3b.json

Run on Jetson:
  git pull origin main
  conda run -n fmtk --no-capture-output python \\
      experiments/cost/jetson_orin_qwen3b_profile.py
"""

import gc
import json
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

MODEL_ID   = "Qwen/Qwen2.5-3B-Instruct"
MODEL_SLUG = "qwen3b"
DEVICE_IDX = 0            # Jetson has one GPU (cuda:0)
REPS       = 5
TIMEOUT_S  = 120
DELTA_TEXT_BUDGET = 200   # target new tokens for warm-append delta (same as E23)

L_TARGETS = [1024, 4096, 8192, 16384]

OUT_PATH = ROOT / "results" / "cost" / "profiles" / "jetson_orin_qwen3b.json"

# ── Committed qwen7b values from E23 for ratio computation ────────────────────
# Source: results/cost/profiles/jetson_orin_qwen7b.json
QWEN7B_FULL_RESTORE_MS = {
    1024:  4052.48,
    4096:  16310.65,
    8192:  33790.28,
    16384: 75053.67,
}
QWEN7B_INCR_WARM_MS = {
    1024:  579.4,
    4096:  855.4,
    8192:  1252.5,
    16384: 2162.8,
}


# ── Corpus ────────────────────────────────────────────────────────────────────

def load_locomo_turns():
    raw = json.loads((ROOT / "data" / "locomo" / "locomo10.json").read_text())
    turns = []
    for item in raw:
        c = item["conversation"]
        i = 1
        while f"session_{i}" in c:
            for t in c[f"session_{i}"]:
                turns.append(f"{t['speaker']}: {t['text']}")
            i += 1
    return turns


def build_context(tok, target_L, device):
    corpus = load_locomo_turns()
    turns, total, idx = [], 0, 0
    while total < target_L and idx < len(corpus) * 4:
        chunk = corpus[idx % len(corpus)]
        n = len(tok.encode(chunk, add_special_tokens=False))
        if total + n > target_L * 1.15:
            break
        turns.append(chunk)
        total += n
        idx += 1
    while total < target_L * 0.85 and len(corpus) > 0:
        chunk = corpus[idx % len(corpus)]
        turns.append(chunk)
        total += len(tok.encode(chunk, add_special_tokens=False))
        idx += 1
    return "\n".join(turns)


def build_delta(tok, budget=DELTA_TEXT_BUDGET):
    corpus = load_locomo_turns()
    turns, total = [], 0
    for chunk in corpus:
        n = len(tok.encode(chunk, add_special_tokens=False))
        if total + n > budget * 1.2:
            break
        turns.append(chunk)
        total += n
        if total >= budget:
            break
    return "\n".join(turns)


# ── Measurement primitives (same protocol as cost_profile.py) ─────────────────

class _Timeout(Exception):
    pass


def _arm(seconds):
    def _h(sig, frame):
        raise _Timeout()
    signal.signal(signal.SIGALRM, _h)
    signal.alarm(seconds)


def _disarm():
    signal.alarm(0)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)


def ttft_cold(model, tok, text, device):
    """Cold TTFT: encode text, generate 1 token, measure end-to-end."""
    inp = tok(text, return_tensors="pt", truncation=True,
               max_length=1 << 17).to(device)
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    t0 = time.perf_counter()
    _arm(TIMEOUT_S)
    try:
        with torch.no_grad():
            _ = model.generate(**inp, max_new_tokens=1, do_sample=False,
                                pad_token_id=tok.eos_token_id)
    finally:
        _disarm()
    torch.cuda.synchronize(device)
    ms   = (time.perf_counter() - t0) * 1000
    peak = torch.cuda.max_memory_allocated(device) / 1e9
    return ms, peak


def incremental(model, tok, ctx_text, new_text, device):
    """
    Warm and cold incremental measures.
    warm_ms: KV cache of ctx pre-filled, then append new_text tokens only.
    cold_ms: full prefill of ctx + new_text from scratch.
    """
    ctx_inp = tok(ctx_text, return_tensors="pt", truncation=True,
                  max_length=1 << 17).to(device)
    new_inp = tok(new_text, return_tensors="pt", truncation=True,
                  max_length=512).to(device)
    delta_n = new_inp["input_ids"].shape[1]

    _arm(TIMEOUT_S * 2)
    try:
        with torch.no_grad():
            out = model(**ctx_inp, use_cache=True)
            past_kv = out.past_key_values

            torch.cuda.synchronize(device)
            t0 = time.perf_counter()
            _ = model(input_ids=new_inp["input_ids"],
                      past_key_values=past_kv, use_cache=False)
            torch.cuda.synchronize(device)
            warm_ms = (time.perf_counter() - t0) * 1000

        del past_kv, out
        gc.collect()
        torch.cuda.empty_cache()

        all_ids = torch.cat([ctx_inp["input_ids"], new_inp["input_ids"]], dim=1)
        attn    = torch.ones_like(all_ids)
        torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model(input_ids=all_ids, attention_mask=attn, use_cache=False)
        torch.cuda.synchronize(device)
        cold_ms = (time.perf_counter() - t0) * 1000
    finally:
        _disarm()

    return warm_ms, cold_ms, delta_n


def _stats(samples):
    s = sorted(samples)
    n = len(s)
    return {
        "median": round(s[n // 2], 2),
        "q1":     round(s[n // 4], 2),
        "q3":     round(s[3 * n // 4], 2),
        "n":      n,
        "samples": [round(x, 2) for x in samples],
    }


def _safe(fn, label):
    try:
        return fn(), True
    except torch.cuda.OutOfMemoryError:
        print(f"    [OOM] {label}", flush=True)
        torch.cuda.empty_cache()
        return None, False
    except _Timeout:
        print(f"    [TIMEOUT] {label}", flush=True)
        return None, False
    except Exception as e:
        print(f"    [ERROR] {label}: {e}", flush=True)
        return None, False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    device = f"cuda:{DEVICE_IDX}"
    print(f"Loading {MODEL_ID} …", flush=True)
    tok   = AutoTokenizer.from_pretrained(MODEL_ID)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, device_map=device)
    model.eval()

    cfg      = model.config
    n_kv_h   = getattr(cfg, "num_key_value_heads", cfg.num_attention_heads)
    head_dim = cfg.hidden_size // cfg.num_attention_heads
    n_layers = cfg.num_hidden_layers
    kv_bytes = 2 * n_kv_h * head_dim * n_layers * 2
    gpu_mem  = torch.cuda.get_device_properties(DEVICE_IDX).total_memory / 1e9
    print(f"  KV bytes/token: {kv_bytes:,}  GPU mem: {gpu_mem:.1f} GB", flush=True)

    delta_text = build_delta(tok)
    delta_n    = len(tok.encode(delta_text, add_special_tokens=False))
    print(f"  Delta (warm-append) text: ~{delta_n} tokens", flush=True)

    records = []

    for L in L_TARGETS:
        print(f"\n── L = {L} ──────────────────────────────────────────────", flush=True)
        ctx_text   = build_context(tok, L, device)
        actual_inp = tok(ctx_text, return_tensors="pt", truncation=True,
                         max_length=L + 512)
        L_actual   = actual_inp["input_ids"].shape[1]
        print(f"  Actual token count: {L_actual}", flush=True)

        # ── Cold prefill (full_restore) ───────────────────────────────────────
        fr_samples, fr_peak_samples = [], []
        feasible_fr = True
        for rep in range(REPS):
            gc.collect(); torch.cuda.empty_cache()
            result, ok = _safe(
                lambda: ttft_cold(model, tok, ctx_text, device),
                f"full_restore rep {rep+1}")
            if not ok:
                feasible_fr = False
                break
            ms, peak = result
            fr_samples.append(ms)
            fr_peak_samples.append(peak)
            print(f"    full_restore rep {rep+1}: {ms:.1f} ms  peak={peak:.2f} GB", flush=True)

        # ── Warm append (incr_warm) + cold baseline (incr_cold) ───────────────
        warm_samples, cold_samples = [], []
        feasible_incr = True
        for rep in range(REPS):
            gc.collect(); torch.cuda.empty_cache()
            result, ok = _safe(
                lambda: incremental(model, tok, ctx_text, delta_text, device),
                f"incremental rep {rep+1}")
            if not ok:
                feasible_incr = False
                break
            w, c, dn = result
            warm_samples.append(w)
            cold_samples.append(c)
            print(f"    incr rep {rep+1}: warm={w:.1f} ms  cold={c:.1f} ms  delta_n={dn}", flush=True)

        rec = {
            "L_target": L,
            "L_actual": L_actual,
            "delta_tokens": delta_n,
            "feasible": {
                "full_restore": feasible_fr,
                "incremental":  feasible_incr,
            },
            "measurements": {},
        }
        if feasible_fr and fr_samples:
            rec["measurements"]["full_restore_ms"]      = _stats(fr_samples)
            rec["measurements"]["full_restore_peak_gb"] = _stats(fr_peak_samples)
        else:
            rec["measurements"]["full_restore_ms"]      = None
            rec["measurements"]["full_restore_peak_gb"] = None

        if feasible_incr and warm_samples:
            rec["measurements"]["incremental_warm_ms"] = _stats(warm_samples)
            rec["measurements"]["incremental_cold_ms"] = _stats(cold_samples)
        else:
            rec["measurements"]["incremental_warm_ms"] = None
            rec["measurements"]["incremental_cold_ms"] = None

        records.append(rec)

    # ── 3B / 7B ratio table ───────────────────────────────────────────────────
    print("\n\n── 3B / 7B time ratios (vs committed qwen7b E23 values) ───────────────")
    print(f"{'L':>7}  {'3B_restore_ms':>14}  {'7B_restore_ms':>14}  {'ratio_restore':>14}  "
          f"{'3B_warm_ms':>12}  {'7B_warm_ms':>12}  {'ratio_warm':>12}")
    ratios = []
    for rec in records:
        L = rec["L_target"]
        fr3 = rec["measurements"]["full_restore_ms"]
        iw3 = rec["measurements"]["incremental_warm_ms"]
        fr3_med = fr3["median"] if fr3 else None
        iw3_med = iw3["median"] if iw3 else None
        fr7 = QWEN7B_FULL_RESTORE_MS.get(L)
        iw7 = QWEN7B_INCR_WARM_MS.get(L)
        r_fr = round(fr3_med / fr7, 3) if (fr3_med and fr7) else None
        r_iw = round(iw3_med / iw7, 3) if (iw3_med and iw7) else None
        print(f"{L:>7}  {str(fr3_med):>14}  {str(fr7):>14}  {str(r_fr):>14}  "
              f"{str(iw3_med):>12}  {str(iw7):>12}  {str(r_iw):>12}")
        ratios.append({"L": L, "full_restore_ratio_3b_7b": r_fr,
                       "incr_warm_ratio_3b_7b": r_iw,
                       "qwen3b_full_restore_ms": fr3_med,
                       "qwen7b_full_restore_ms": fr7,
                       "qwen3b_incr_warm_ms": iw3_med,
                       "qwen7b_incr_warm_ms": iw7})

    # ── Write output ──────────────────────────────────────────────────────────
    output = {
        "metadata": {
            "tier":        "jetson_orin",
            "model":       MODEL_SLUG,
            "llm":         MODEL_ID,
            "gpu":         "Orin",
            "gpu_mem_gb":  round(gpu_mem, 1),
            "device":      device,
            "reps":        REPS,
            "kv_bytes_per_token": kv_bytes,
            "delta_tokens": delta_n,
            "token_counts_requested": L_TARGETS,
            "timestamp":   datetime.now().isoformat(),
            "purpose":     "Resolves E36 ASSUMPTION A1: qwen3b/qwen7b time ratio on Jetson.",
        },
        "qwen7b_reference_E23": {
            "full_restore_ms": QWEN7B_FULL_RESTORE_MS,
            "incr_warm_ms":    QWEN7B_INCR_WARM_MS,
        },
        "ratios_3b_7b": ratios,
        "data": records,
        "_provenance": stamp(
            script="jetson_orin_qwen3b_profile.py",
            model=MODEL_SLUG,
            device="jetson_orin",
            n=len(L_TARGETS) * REPS,
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nSaved: {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
