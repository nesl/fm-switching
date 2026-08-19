"""
Phase 1 — Physical-Inertia Cost Profile
=========================================
Measures restore/update latency for each state representation as a function of
context length L on a target tier, using real text sampled from LoCoMo and
Infini-THOR logs so the token distribution is realistic.

Output:
  results/phase1/cost_profiles/{tier}_{model}.json   — raw per-(L, rep) data
  results/phase1/{tier}/README.md                     — per-host measurement notes

Tier slugs  : a6000 | rtx3090ti | jetson_orin
Model slugs : qwen7b | smollm2 | qwen3b

Usage:
  # A6000 (GPU index 1 on this machine):
  conda run -n fmtk python experiments/phase1_cost_profile.py \\
      --model qwen7b --tier a6000 --gpu 1

  # RTX 3090 Ti (GPU index 0):
  conda run -n fmtk python experiments/phase1_cost_profile.py \\
      --model qwen7b --tier rtx3090ti --gpu 0

  # Smoke test (fast):
  conda run -n fmtk python experiments/phase1_cost_profile.py \\
      --model qwen7b --tier a6000 --gpu 1 --token-counts 1024,2048 --reps 2

Measurements per L (5 reps; median + IQR reported):
  full_restore     : TTFT (ms) to prefill L tokens; peak GPU memory (GB)
  window_restore   : TTFT for last-10-turns window (~2 K tokens, constant)
  sum80_restore    : TTFT for 80-token summary
  sum200_restore   : TTFT for 200-token summary
  sum80_update     : time (ms) to generate 80 new tokens from L-token context
  sum200_update    : time (ms) to generate 200 new tokens from L-token context
  incremental_warm : TTFT for 200 new tokens given warm KV cache of L tokens
  incremental_cold : TTFT to cold-prefill L+200 tokens (baseline for warm)

State sizes (bytes) per representation at each L:
  full_bytes, window_bytes, sum80_bytes, sum200_bytes, kv_bytes (analytical)

Transfer-cost columns are derived in phase1_analysis.py from state_bytes and
effective bandwidths {1, 10, 100} Mbps plus RTT {50, 200} ms.
"""

import argparse
import gc
import json
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import torch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))

DATA_LOCOMO    = ROOT / "data" / "locomo" / "locomo10.json"
DATA_TRAJ_TEST = ROOT / "data" / "infinithor" / "traj_test"
DATA_TRAJ      = ROOT / "data" / "infinithor" / "traj"
OUT_DIR        = ROOT / "results" / "phase1" / "cost_profiles"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = {
    "qwen7b":  "Qwen/Qwen2.5-7B-Instruct",
    "smollm2": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "qwen3b":  "Qwen/Qwen2.5-3B-Instruct",
}

DEFAULT_L_SWEEP = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
DEFAULT_REPS    = 5
TIMEOUT_S       = 120   # mark infeasible if a single measurement exceeds this
WINDOW_TURNS    = 10    # number of turns in the window representation
CHUNK_TOKENS    = 200   # approximate tokens per corpus "turn"

SUMMARY_PROMPT = (
    "Summarize the following context in approximately {n} tokens. "
    "Preserve all key facts and named entities.\n\n"
    "{context}\n\nSummary:"
)

# ── Corpus construction ───────────────────────────────────────────────────────

def load_locomo_turns():
    """Return list of speaker-line strings from all LoCoMo conversations."""
    raw = json.loads(DATA_LOCOMO.read_text())
    turns = []
    for item in raw:
        c = item["conversation"]
        i = 1
        while f"session_{i}" in c:
            for t in c[f"session_{i}"]:
                turns.append(f"{t['speaker']}: {t['text']}")
            i += 1
    return turns

def load_infinithor_chunks(max_traj=80):
    """Return list of Infini-THOR plan+action blocks (one block per 'turn')."""
    chunks = []
    for d in (DATA_TRAJ_TEST, DATA_TRAJ):
        if not d.exists():
            continue
        for p in sorted(d.glob("*.txt"))[:max_traj]:
            raw = p.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"<image>", "", raw)
            # Split into plan-block units at each <|goal|> or <|plan|> boundary
            blocks = re.split(r"(?=<\|(?:goal|plan)\|>)", raw)
            for b in blocks:
                b = re.sub(r"<\|[a-z_]+\|>", " | ", b).strip()
                if len(b) > 20:
                    chunks.append(b)
        if len(chunks) >= max_traj * 10:
            break
    return chunks

def build_corpus(tok, target_chunk_tokens=CHUNK_TOKENS):
    """
    Build a flat list of text chunks, each approximately target_chunk_tokens tokens.
    Mix LoCoMo turns (smaller) and Infini-THOR blocks (larger).
    Returns (chunks: List[str], window_text_fn: Callable).
    """
    locomo_turns = load_locomo_turns()
    infini_blocks = load_infinithor_chunks()
    # Merge into interleaved corpus
    merged = []
    li, ii = 0, 0
    while li < len(locomo_turns) or ii < len(infini_blocks):
        # Add ~4 LoCoMo turns per 1 Infini-THOR block for realistic token mix
        for _ in range(4):
            if li < len(locomo_turns):
                merged.append(locomo_turns[li])
                li += 1
        if ii < len(infini_blocks):
            merged.append(infini_blocks[ii])
            ii += 1
    return merged

def sample_context(corpus, tok, target_L, device):
    """
    Build a context string of approximately target_L tokens from the corpus.
    Returns (context_text, turns_list, actual_token_count).
    'turns_list' preserves individual turn boundaries for window extraction.
    """
    turns = []
    total = 0
    idx = 0
    while total < target_L and idx < len(corpus):
        chunk = corpus[idx % len(corpus)]
        chunk_toks = len(tok.encode(chunk, add_special_tokens=False))
        if total + chunk_toks > target_L * 1.15:
            break
        turns.append(chunk)
        total += chunk_toks
        idx += 1
    # Pad if short: repeat corpus
    while total < target_L * 0.9 and len(corpus) > 0:
        chunk = corpus[idx % len(corpus)]
        chunk_toks = len(tok.encode(chunk, add_special_tokens=False))
        turns.append(chunk)
        total += chunk_toks
        idx += 1
    context_text = "\n".join(turns)
    actual_count = tok(context_text, return_tensors="pt", truncation=True,
                       max_length=target_L + 512)["input_ids"].shape[1]
    return context_text, turns, min(actual_count, target_L)


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model(model_id, device_idx):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"  Loading {model_id} on cuda:{device_idx} …", flush=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.float16, device_map=f"cuda:{device_idx}")
    model.eval()
    cfg = model.config
    # KV cache bytes per token (analytical, FP16)
    n_kv_heads  = getattr(cfg, "num_key_value_heads", cfg.num_attention_heads)
    head_dim    = cfg.hidden_size // cfg.num_attention_heads
    n_layers    = cfg.num_hidden_layers
    kv_bytes    = 2 * n_kv_heads * head_dim * n_layers * 2  # K+V, FP16=2 bytes
    print(f"  KV bytes/token: {kv_bytes:,}  ({kv_bytes/1024:.1f} KB)")
    return model, tok, kv_bytes


# ── Measurement primitives ────────────────────────────────────────────────────

class TimeoutError(Exception):
    pass

def _ttft(model, tok, text, device, max_length=None, timeout=TIMEOUT_S):
    """Time to first token (TTFT) for a text input. Returns (ms, peak_gb)."""
    ml = max_length or (1 << 17)
    inp = tok(text, return_tensors="pt", truncation=True,
               max_length=ml).to(device)
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    t0 = time.perf_counter()

    def _handler(sig, frame):
        raise TimeoutError()
    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    try:
        with torch.no_grad():
            _ = model.generate(**inp, max_new_tokens=1, do_sample=False,
                                pad_token_id=tok.eos_token_id)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    torch.cuda.synchronize(device)
    ms   = (time.perf_counter() - t0) * 1000
    peak = torch.cuda.max_memory_allocated(device) / 1e9
    return ms, peak

def _generate_time(model, tok, text, device, max_new, max_length=None, timeout=TIMEOUT_S):
    """Time to generate max_new tokens from a text input. Returns ms."""
    ml = max_length or (1 << 17)
    inp = tok(text, return_tensors="pt", truncation=True,
               max_length=ml).to(device)

    def _handler(sig, frame):
        raise TimeoutError()
    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    try:
        torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model.generate(**inp, max_new_tokens=max_new, do_sample=False,
                                pad_token_id=tok.eos_token_id)
        torch.cuda.synchronize(device)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    return (time.perf_counter() - t0) * 1000

def _incremental(model, tok, ctx_text, new_text, device, max_length=None, timeout=TIMEOUT_S):
    """
    Warm: prefill ctx, then append new_text using KV cache.
    Cold: prefill ctx+new_text from scratch.
    Returns (warm_ms, cold_ms, new_token_count).
    """
    ml = max_length or (1 << 17)
    ctx_inp = tok(ctx_text, return_tensors="pt", truncation=True,
                  max_length=ml).to(device)
    new_inp = tok(new_text,  return_tensors="pt", truncation=True,
                  max_length=512).to(device)
    new_tok_count = new_inp["input_ids"].shape[1]

    def _handler(sig, frame):
        raise TimeoutError()
    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout * 2)
    try:
        # Warm: pre-fill context, cache KV, then append new turn
        with torch.no_grad():
            out = model(**ctx_inp, use_cache=True)
            past_kv = out.past_key_values

            torch.cuda.synchronize(device)
            t0 = time.perf_counter()
            _ = model(input_ids=new_inp["input_ids"], past_key_values=past_kv,
                      use_cache=False)
            torch.cuda.synchronize(device)
            warm_ms = (time.perf_counter() - t0) * 1000

        del past_kv, out
        torch.cuda.empty_cache()

        # Cold: full prefill of ctx + new_text
        all_ids = torch.cat([ctx_inp["input_ids"], new_inp["input_ids"]], dim=1)
        attn    = torch.ones_like(all_ids)
        torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model(input_ids=all_ids, attention_mask=attn, use_cache=False)
        torch.cuda.synchronize(device)
        cold_ms = (time.perf_counter() - t0) * 1000
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    return warm_ms, cold_ms, new_tok_count


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _stats(samples):
    s = sorted(samples)
    n = len(s)
    med  = s[n // 2]
    q1   = s[n // 4]
    q3   = s[3 * n // 4]
    return {"median": round(med, 2), "q1": round(q1, 2), "q3": round(q3, 2),
            "n": n, "samples": [round(x, 2) for x in samples]}

def _safe(fn, label):
    """Run fn(); return result or an infeasible sentinel on OOM/Timeout."""
    try:
        return fn(), True
    except torch.cuda.OutOfMemoryError:
        print(f"    [OOM] {label}", flush=True)
        torch.cuda.empty_cache()
        return None, False
    except TimeoutError:
        print(f"    [TIMEOUT]{label}", flush=True)
        return None, False
    except Exception as e:
        print(f"    [ERROR] {label}: {e}", flush=True)
        return None, False


# ── Fixed summary/window stubs ────────────────────────────────────────────────

# 80-token summary stub (actual text from phase0a LoCoMo cache)
SUM80_TEXT = (
    "Two friends maintain close contact discussing personal milestones, career changes, "
    "health concerns, travel plans, and relationship updates over several months. "
    "Key events include job transitions, medical appointments, family gatherings, "
    "and shared hobbies. Both speakers express mutual support and regularly check in."
)
SUM200_TEXT = (
    "Caroline and her friend have maintained a close relationship over several months, "
    "regularly discussing life events including career changes, health updates, travel "
    "plans, family news, and romantic relationships. Caroline underwent a medical procedure "
    "and recovered well. Her friend changed jobs and relocated to a new city. Both attended "
    "mutual friends' events. They discussed career goals, financial planning, and long-term "
    "ambitions. Regular check-ins covered weekend activities, exercise routines, diet changes, "
    "and shared interests in films and books. Their conversations reflect consistent emotional "
    "support and detailed personal disclosure over an extended period of friendship."
)
NEW_TURN_TEXT = (
    "Speaker A: So I was thinking about what you said last time about the project timeline. "
    "I actually went ahead and scheduled a meeting with the team for next Thursday. "
    "We're going to review all the deliverables and figure out if we need to adjust anything. "
    "I also reached out to the client to let them know there might be a slight delay. "
    "They seemed understanding about it, which is a relief honestly."
)


# ── Main profiling loop ───────────────────────────────────────────────────────

def profile_one_L(model, tok, kv_bytes, corpus, L, reps, device, device_idx):
    """Run all measurements for a single context length L. Returns result dict."""
    print(f"\n  L={L:,} tokens …", flush=True)

    ctx_text, turns, actual_L = sample_context(corpus, tok, L, device)
    window_turns = turns[-WINDOW_TURNS:] if len(turns) >= WINDOW_TURNS else turns
    window_text  = "\n".join(window_turns)
    sum80_text   = SUM80_TEXT
    sum200_text  = SUM200_TEXT

    # State sizes in bytes (UTF-8 encoded)
    state_bytes = {
        "full":       len(ctx_text.encode("utf-8")),
        "window":     len(window_text.encode("utf-8")),
        "summary_80": len(sum80_text.encode("utf-8")),
        "summary_200":len(sum200_text.encode("utf-8")),
        "kv_cache":   actual_L * kv_bytes,
    }

    # Precompute actual token counts (for reporting)
    window_toks  = tok(window_text,  return_tensors="pt", truncation=True,
                       max_length=4096)["input_ids"].shape[1]
    sum80_toks   = tok(sum80_text,   return_tensors="pt", truncation=True,
                       max_length=256)["input_ids"].shape[1]
    sum200_toks  = tok(sum200_text,  return_tensors="pt", truncation=True,
                       max_length=512)["input_ids"].shape[1]

    token_counts = {
        "full": actual_L, "window": int(window_toks),
        "summary_80": int(sum80_toks), "summary_200": int(sum200_toks),
    }

    # Per-rep raw samples
    raw = {k: [] for k in [
        "full_restore_ms", "full_restore_peak_gb",
        "window_restore_ms", "sum80_restore_ms", "sum200_restore_ms",
        "sum80_update_ms", "sum200_update_ms",
        "incremental_warm_ms", "incremental_cold_ms",
    ]}
    feasible = {k: True for k in [
        "full_restore", "window_restore", "sum80_restore", "sum200_restore",
        "sum80_update", "sum200_update", "incremental",
    ]}

    sum_prompt_80  = SUMMARY_PROMPT.format(n=80,  context=ctx_text[:8000])
    sum_prompt_200 = SUMMARY_PROMPT.format(n=200, context=ctx_text[:8000])

    for rep in range(reps):
        print(f"    rep {rep+1}/{reps}", end=" ", flush=True)

        # Full restore (TTFT + peak memory)
        result, ok = _safe(
            lambda: _ttft(model, tok, ctx_text, device, max_length=actual_L + 64),
            "full_restore")
        if ok and result:
            raw["full_restore_ms"].append(result[0])
            raw["full_restore_peak_gb"].append(result[1])
        else:
            feasible["full_restore"] = False
        torch.cuda.empty_cache()

        # Window restore
        result, ok = _safe(
            lambda: _ttft(model, tok, window_text, device, max_length=window_toks + 64),
            "window_restore")
        if ok and result:
            raw["window_restore_ms"].append(result[0])
        else:
            feasible["window_restore"] = False
        torch.cuda.empty_cache()

        # Summary-80 restore
        result, ok = _safe(
            lambda: _ttft(model, tok, sum80_text, device, max_length=sum80_toks + 64),
            "sum80_restore")
        if ok and result:
            raw["sum80_restore_ms"].append(result[0])
        else:
            feasible["sum80_restore"] = False
        torch.cuda.empty_cache()

        # Summary-200 restore
        result, ok = _safe(
            lambda: _ttft(model, tok, sum200_text, device, max_length=sum200_toks + 64),
            "sum200_restore")
        if ok and result:
            raw["sum200_restore_ms"].append(result[0])
        else:
            feasible["sum200_restore"] = False
        torch.cuda.empty_cache()

        # Summary-80 update (generate 80 new tokens from L-token context)
        result, ok = _safe(
            lambda: _generate_time(model, tok, sum_prompt_80, device,
                                   max_new=90, max_length=actual_L + 256),
            "sum80_update")
        if ok and result is not None:
            raw["sum80_update_ms"].append(result)
        else:
            feasible["sum80_update"] = False
        torch.cuda.empty_cache()

        # Summary-200 update (generate 200 new tokens from L-token context)
        result, ok = _safe(
            lambda: _generate_time(model, tok, sum_prompt_200, device,
                                   max_new=210, max_length=actual_L + 256),
            "sum200_update")
        if ok and result is not None:
            raw["sum200_update_ms"].append(result)
        else:
            feasible["sum200_update"] = False
        torch.cuda.empty_cache()

        # Incremental update (warm KV append vs cold prefill)
        result, ok = _safe(
            lambda: _incremental(model, tok, ctx_text, NEW_TURN_TEXT,
                                 device, max_length=actual_L + 64),
            "incremental")
        if ok and result:
            raw["incremental_warm_ms"].append(result[0])
            raw["incremental_cold_ms"].append(result[1])
        else:
            feasible["incremental"] = False
        torch.cuda.empty_cache()
        gc.collect()
        print("✓", flush=True)

    # Aggregate stats (skip first rep as warm-up if reps > 1)
    skip = 1 if reps > 1 else 0

    def agg(key):
        v = raw[key][skip:]
        return _stats(v) if v else None

    measurements = {}
    for m in ["full_restore_ms", "full_restore_peak_gb",
               "window_restore_ms", "sum80_restore_ms", "sum200_restore_ms",
               "sum80_update_ms", "sum200_update_ms",
               "incremental_warm_ms", "incremental_cold_ms"]:
        measurements[m] = agg(m)

    return {
        "L_target":    L,
        "L_actual":    actual_L,
        "token_counts": token_counts,
        "state_bytes":  state_bytes,
        "feasible":     feasible,
        "measurements": measurements,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Phase 1 cost profiler")
    ap.add_argument("--model",        required=True, choices=list(MODELS))
    ap.add_argument("--tier",         required=True,
                    help="Tier slug: a6000 | rtx3090ti | jetson_orin")
    ap.add_argument("--gpu",          type=int, default=0,
                    help="CUDA device index (default 0)")
    ap.add_argument("--token-counts", default=None,
                    help="Comma-separated L values to sweep. "
                         f"Default: {','.join(str(x) for x in DEFAULT_L_SWEEP)}")
    ap.add_argument("--reps",         type=int, default=DEFAULT_REPS)
    ap.add_argument("--resume",       action="store_true",
                    help="Skip L points already in the output file.")
    args = ap.parse_args()

    token_counts = ([int(x) for x in args.token_counts.split(",")]
                    if args.token_counts else DEFAULT_L_SWEEP)
    device     = f"cuda:{args.gpu}"
    device_idx = args.gpu
    out_path   = OUT_DIR / f"{args.tier}_{args.model}.json"
    notes_dir  = ROOT / "results" / "phase1" / args.tier
    notes_dir.mkdir(parents=True, exist_ok=True)

    gpu_name = torch.cuda.get_device_name(device_idx)
    gpu_mem  = torch.cuda.get_device_properties(device_idx).total_memory / 1e9

    print("=" * 68)
    print(f"PHASE 1 COST PROFILE  tier={args.tier}  model={args.model}")
    print(f"  GPU    : {gpu_name}  ({gpu_mem:.1f} GB)")
    print(f"  Device : {device}")
    print(f"  LLM    : {MODELS[args.model]}")
    print(f"  L sweep: {token_counts}")
    print(f"  Reps   : {args.reps} (first excluded as warm-up if reps > 1)")
    print(f"  Output : {out_path}")
    print("=" * 68)

    # Load existing results for --resume
    existing = {}
    if args.resume and out_path.exists():
        prev = json.loads(out_path.read_text())
        for pt in prev.get("data", []):
            existing[pt["L_target"]] = pt
        print(f"Resuming: {len(existing)} L-points already done.")

    # Load model
    model, tok, kv_bytes = load_model(MODELS[args.model], device_idx)
    torch.cuda.empty_cache()

    # Build corpus
    print("Building corpus …", flush=True)
    corpus = build_corpus(tok)
    print(f"  Corpus: {len(corpus)} turns", flush=True)

    # Run sweep
    results = list(existing.values())
    done_Ls = set(existing.keys())

    for L in token_counts:
        if L in done_Ls:
            print(f"  L={L:,}: already done, skipping.")
            continue
        pt = profile_one_L(model, tok, kv_bytes, corpus, L, args.reps,
                           device, device_idx)
        results.append(pt)
        done_Ls.add(L)

        # Incremental save after each L point
        out = {
            "metadata": {
                "tier":      args.tier,
                "model":     args.model,
                "llm":       MODELS[args.model],
                "gpu":       gpu_name,
                "gpu_mem_gb": round(gpu_mem, 1),
                "device":    device,
                "reps":      args.reps,
                "kv_bytes_per_token": kv_bytes,
                "token_counts_requested": token_counts,
                "timestamp": datetime.now().isoformat(),
            },
            "data": sorted(results, key=lambda x: x["L_target"]),
        }
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2))
        tmp.replace(out_path)
        print(f"  Saved → {out_path}", flush=True)

    # Write per-host notes
    notes_path = notes_dir / "README.md"
    notes_path.write_text(
        f"# Phase 1 — {args.tier} measurement notes\n\n"
        f"Model: {args.model} ({MODELS[args.model]})\n"
        f"GPU: {gpu_name} ({gpu_mem:.1f} GB)\n"
        f"L sweep: {token_counts}\n"
        f"Reps: {args.reps}\n"
        f"Timestamp: {datetime.now().isoformat()}\n\n"
        f"Result file: results/phase1/cost_profiles/{args.tier}_{args.model}.json\n\n"
        "## Notes\n\n"
        "- Window-10 = last 10 corpus turns (~200 tokens/turn), "
          "capped by available context; actual window token count in result JSON.\n"
        "- Summary restore uses a fixed ~80/200-token stub text.\n"
        "- Summary update generates from the first 8000 chars of context "
          "(capped to avoid extreme input lengths for the update path).\n"
        "- Incremental warm = forward pass of 200 new tokens given cached KV.\n"
        "- Incremental cold = full prefill of L+200 tokens without KV cache.\n"
        "- First rep excluded from stats (warm-up).\n"
        "- OOM and >120 s measurements recorded as infeasible.\n"
        "- KV cache size is analytical (FP16, measured model config).\n"
        "- Transfer costs are derived in phase1_analysis.py.\n"
    )
    print(f"\nDone. Notes → {notes_path}")


if __name__ == "__main__":
    main()
