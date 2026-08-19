"""
Phase 1 — Summary-update rerun with full L-token context.

The initial profile sweep measured sum-80 and sum-200 update latency from the
first 8000 characters of context (a cap introduced for sweep tractability).
This script reruns those two measurements using the full L-token context as
the summarization input, as originally specified.

Adds to each L-point in the existing result JSON:
  measurements.sum80_update_full_ms
  measurements.sum200_update_full_ms

The original (truncated-input) keys are preserved unchanged for the appendix.

Usage:
  conda run -n fmtk python experiments/phase1_update_rerun.py \\
      --tier a6000 --model qwen7b --gpu 1
  conda run -n fmtk python experiments/phase1_update_rerun.py \\
      --tier rtx3090ti --model qwen7b --gpu 0
"""

import argparse
import gc
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import torch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

# Import shared helpers from the profiler
from phase1_cost_profile import (
    MODELS, OUT_DIR, TIMEOUT_S, SUMMARY_PROMPT,
    build_corpus, sample_context,
    load_model, _stats, _safe, TimeoutError,
)

REPS = 5   # total reps; first excluded as warm-up → 4 measured


def _generate_time_full(model, tok, context_text, device, max_new,
                         max_length=None, timeout=TIMEOUT_S * 3):
    """Generate max_new tokens from the full context_text. Returns ms."""
    ml = max_length or (1 << 17)
    inp = tok(context_text, return_tensors="pt", truncation=True,
               max_length=ml).to(device)
    actual_L = inp["input_ids"].shape[1]

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
        ms = (time.perf_counter() - t0) * 1000
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    return ms, actual_L


def rerun_one_L(model, tok, corpus, pt, device, max_length):
    """Rerun sum80 and sum200 update for one L-point dict. Returns (s80_stats, s20_stats)."""
    L_target = pt["L_target"]
    L_actual = pt["L_actual"]
    print(f"\n  L={L_actual:,} tokens …", flush=True)

    ctx_text, _, _ = sample_context(corpus, tok, L_target, device)

    # Build the summary prompt using the FULL context
    sum_prompt_80  = SUMMARY_PROMPT.format(n=80,  context=ctx_text)
    sum_prompt_200 = SUMMARY_PROMPT.format(n=200, context=ctx_text)

    raw80, raw200 = [], []

    for rep in range(REPS):
        print(f"    rep {rep+1}/{REPS}", end=" ", flush=True)

        result, ok = _safe(
            lambda: _generate_time_full(model, tok, sum_prompt_80, device,
                                        max_new=90, max_length=max_length),
            "sum80_update_full")
        if ok and result:
            raw80.append(result[0])
            actual_tok = result[1]
        else:
            raw80.append(None)
        torch.cuda.empty_cache()

        result, ok = _safe(
            lambda: _generate_time_full(model, tok, sum_prompt_200, device,
                                        max_new=210, max_length=max_length),
            "sum200_update_full")
        if ok and result:
            raw200.append(result[0])
        else:
            raw200.append(None)
        torch.cuda.empty_cache()
        gc.collect()
        print("✓", flush=True)

    # Exclude first rep as warm-up
    skip = 1 if REPS > 1 else 0
    s80  = [v for v in raw80[skip:]  if v is not None]
    s200 = [v for v in raw200[skip:] if v is not None]
    return (_stats(s80) if s80 else None), (_stats(s200) if s200 else None)


def main():
    ap = argparse.ArgumentParser(description="Phase 1 summary-update rerun (full context)")
    ap.add_argument("--tier",  required=True)
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--gpu",   type=int, default=0)
    ap.add_argument("--resume", action="store_true",
                    help="Skip L-points that already have sum80_update_full_ms.")
    args = ap.parse_args()

    out_path   = OUT_DIR / f"{args.tier}_{args.model}.json"
    device     = f"cuda:{args.gpu}"
    device_idx = args.gpu

    if not out_path.exists():
        print(f"ERROR: {out_path} not found. Run phase1_cost_profile.py first.")
        sys.exit(1)

    res   = json.loads(out_path.read_text())
    meta  = res["metadata"]
    data  = res["data"]

    gpu_name = torch.cuda.get_device_name(device_idx)
    print("=" * 68)
    print(f"PHASE 1 UPDATE RERUN (full context)  tier={args.tier}  model={args.model}")
    print(f"  GPU    : {gpu_name}")
    print(f"  File   : {out_path}")
    print(f"  L pts  : {len(data)}")
    print(f"  Reps   : {REPS} (first excluded as warm-up)")
    print("=" * 68)

    model, tok, _ = load_model(MODELS[args.model], device_idx)
    torch.cuda.empty_cache()
    ctx_lim = model.config.max_position_embeddings

    print("Building corpus …", flush=True)
    corpus = build_corpus(tok)
    print(f"  Corpus: {len(corpus)} turns", flush=True)

    for i, pt in enumerate(data):
        # Skip if already done and --resume
        if args.resume and pt.get("measurements", {}).get("sum80_update_full_ms"):
            print(f"  L={pt['L_actual']:,}: already done, skipping.")
            continue

        s80, s200 = rerun_one_L(model, tok, corpus, pt, device, max_length=ctx_lim)

        pt["measurements"]["sum80_update_full_ms"]  = s80
        pt["measurements"]["sum200_update_full_ms"] = s200
        if s80 is None:
            pt.setdefault("feasible", {})["sum80_update_full"]  = False
        if s200 is None:
            pt.setdefault("feasible", {})["sum200_update_full"] = False

        # Incremental save
        res["metadata"]["rerun_timestamp"] = datetime.now().isoformat()
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, indent=2))
        tmp.replace(out_path)
        print(f"  Saved → {out_path}", flush=True)

    print(f"\nDone. All L-points updated in {out_path}")


if __name__ == "__main__":
    main()
