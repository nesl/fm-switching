"""
E26 — vLLM cold-prefill + decode calibration on A6000
=======================================================
Measures:
  1. TTFT (cold prefill, prefix_caching=False) at L ∈ {1k,8k,32k,64k}, 5 reps
  2. Total refresh latency (prefill of L + decode of 80 / 200 output tokens),
     single request at a time, 5 reps each budget
     — comparable to HF "update latency" numbers in reports/phase1_cost_profiling.md
     and to E27 full_regen latencies in reports/e27_maintenance_mechanism.md.

KV-memory note: vLLM preallocates a fixed GPU memory pool for KV cache blocks.
torch.cuda.max_memory_allocated() is 0 inside the vLLM worker process because vLLM
manages its own allocator. We report the KV cache configuration (total tokens, block
size) from engine metadata instead.

Run on A6000 (GPU 1):
  CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID \\
  VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \\
  python experiments/cost/vllm_calibration.py
"""

import argparse
import gc
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
sys.path.insert(0, str(ROOT / "experiments" / "cost"))

MODEL_ID    = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG  = "qwen7b"
DEVICE_SLUG = "a6000"
OUT_PATH    = ROOT / "results" / "cost" / "vllm_calibration_a6000_qwen7b.json"

# Qwen2.5-7B-Instruct official max context is 131072 tokens.
# The locally cached copy may have max_position_embeddings=32768 (older snapshot);
# if so, set VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 and re-download if needed.
MAX_MODEL_LEN    = 131072
DEFAULT_L_TOKENS = [1024, 8192, 32768, 65536]
DEFAULT_REPS     = 5
DECODE_BUDGETS   = [80, 200]   # output token counts for refresh measurement


def summarise(vals):
    s = sorted(vals)
    n = len(s)
    med = statistics.median(s)
    q1  = statistics.median(s[: n // 2]) if n >= 2 else med
    q3  = statistics.median(s[n - n // 2 :]) if n >= 2 else med
    return {
        "median_s": round(med, 4),
        "iqr_s":    round(q3 - q1, 4),
        "all_s":    [round(v, 4) for v in s],
    }


def build_prompt_text(corpus_turns, tok, target_L):
    """Build a context string of ≤target_L tokens from the corpus."""
    turns, total = [], 0
    idx = 0
    # First pass: add turns until we reach target_L
    while total < target_L and idx < len(corpus_turns):
        chunk = corpus_turns[idx % len(corpus_turns)]
        ids   = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target_L:
            # Add a partial final turn clipped to exactly target_L
            clip  = target_L - total
            turns.append(tok.decode(ids[:clip]))
            total += clip
            break
        turns.append(chunk)
        total += len(ids)
        idx   += 1
    context    = "\n".join(turns)
    actual_tok = len(tok.encode(context, add_special_tokens=False))
    return context, actual_tok


def get_kv_cache_info(llm):
    """Extract KV cache configuration from the vLLM engine."""
    try:
        # vLLM 0.8.x V1 engine
        eng = llm.llm_engine
        # Try scheduler cache_config
        if hasattr(eng, "cache_config"):
            cc = eng.cache_config
            return {
                "num_gpu_blocks": getattr(cc, "num_gpu_blocks", None),
                "block_size":     getattr(cc, "block_size", 16),
            }
    except Exception:
        pass
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--l-tokens", default=",".join(str(x) for x in DEFAULT_L_TOKENS))
    ap.add_argument("--reps",     type=int, default=DEFAULT_REPS)
    ap.add_argument("--gpu-mem-fraction", type=float, default=0.92)
    args = ap.parse_args()

    l_sweep = [int(x) for x in args.l_tokens.split(",")]

    from cost_profile import build_corpus

    try:
        from vllm import LLM, SamplingParams
        import vllm
        vllm_version = vllm.__version__
    except ImportError as e:
        print(f"ERROR: vLLM not available: {e}", file=sys.stderr)
        sys.exit(1)

    import torch
    torch_version = torch.__version__
    cuda_version  = torch.version.cuda

    print(f"vLLM {vllm_version} | torch {torch_version} | CUDA {cuda_version}")
    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES','unset')}")
    print(f"VLLM_ALLOW_LONG_MAX_MODEL_LEN={os.environ.get('VLLM_ALLOW_LONG_MAX_MODEL_LEN','unset')}")

    from transformers import AutoTokenizer
    print("Loading tokenizer …")
    hf_tok = AutoTokenizer.from_pretrained(MODEL_ID)

    print("Building corpus …")
    corpus = build_corpus(hf_tok)
    print(f"  {len(corpus)} chunks")

    # ── Per-L loop: one engine shared across prefill+decode for that L ─────────
    # A CUDA assertion at L > max_position_embeddings kills the engine process.
    # We create a fresh engine per L-point so a failure at 32k doesn't lose 1k/8k.
    # After the first infeasible L, all larger L are also infeasible (same root cause).

    kv_info      = {}
    cold_results = {}
    decode_results = {}

    engine_failed = False  # once True, skip all remaining L

    for L in l_sweep:
        print(f"\n{'='*60}")
        print(f"  L={L:,} tokens")
        print(f"{'='*60}")

        if engine_failed:
            cold_results[str(L)]   = {"feasible": False, "error": "skipped: prior L failed (RoPE OOB)"}
            decode_results[str(L)] = {"skipped": "prior L infeasible"}
            continue

        prompt_text, actual_L = build_prompt_text(corpus, hf_tok, L)
        print(f"  actual tokens: {actual_L:,}")

        # Fresh engine for each L; CUDA assertion at large L is unrecoverable.
        print(f"  Initialising engine (max_model_len={MAX_MODEL_LEN}) …")
        try:
            llm = LLM(
                model=MODEL_ID,
                dtype="float16",
                gpu_memory_utilization=args.gpu_mem_fraction,
                enable_prefix_caching=False,
                max_model_len=MAX_MODEL_LEN,
                enforce_eager=False,
            )
            if not kv_info:
                kv_info = get_kv_cache_info(llm)
                print(f"  KV cache config: {kv_info}")
        except Exception as e:
            print(f"  Engine init failed: {e}")
            cold_results[str(L)]   = {"feasible": False, "error": str(e)}
            decode_results[str(L)] = {"skipped": "engine init failed"}
            engine_failed = True
            continue

        sp_cold = SamplingParams(max_tokens=1, temperature=0.0)

        # ── Cold prefill ──────────────────────────────────────────────────────
        print(f"\n  COLD PREFILL (max_tokens=1) …")
        try:
            llm.generate([prompt_text], sp_cold)  # warm-up
        except Exception as e:
            print(f"  warm-up failed: {e}")
            cold_results[str(L)]   = {"feasible": False, "error": str(e), "actual_L_tokens": actual_L}
            decode_results[str(L)] = {"skipped": "cold prefill infeasible"}
            del llm; gc.collect(); torch.cuda.empty_cache()
            engine_failed = True
            continue

        times  = []
        failed = False
        for r in range(args.reps):
            t0 = time.perf_counter()
            try:
                llm.generate([prompt_text], sp_cold)
            except Exception as e:
                print(f"  rep {r+1} failed: {e}")
                cold_results[str(L)] = {"feasible": False, "error": str(e), "reps_done": r,
                                         "actual_L_tokens": actual_L}
                failed = True; engine_failed = True
                break
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            print(f"  prefill rep {r+1}/{args.reps}: {elapsed:.3f}s")

        if failed:
            decode_results[str(L)] = {"skipped": "cold prefill failed mid-run"}
            del llm; gc.collect(); torch.cuda.empty_cache()
            continue

        cold_results[str(L)] = {
            "actual_L_tokens": actual_L,
            "feasible": True,
            **summarise(times),
        }
        cold_med = statistics.median(sorted(times))

        # ── Decode (prefill + generate) ───────────────────────────────────────
        print(f"\n  DECODE (single request, no batching) …")
        decode_results[str(L)] = {"actual_L_tokens": actual_L}

        for budget in DECODE_BUDGETS:
            print(f"\n  budget={budget} tokens …")
            sp_dec = SamplingParams(max_tokens=budget, min_tokens=budget, temperature=0.0)

            try:
                llm.generate([prompt_text], sp_dec)  # warm-up
            except Exception as e:
                print(f"  warm-up failed: {e}")
                decode_results[str(L)][f"budget_{budget}"] = {"feasible": False, "error": str(e)}
                continue

            times  = []
            failed = False
            for r in range(args.reps):
                t0 = time.perf_counter()
                try:
                    llm.generate([prompt_text], sp_dec)
                except Exception as e:
                    print(f"  rep {r+1} failed: {e}")
                    decode_results[str(L)][f"budget_{budget}"] = {
                        "feasible": False, "error": str(e), "reps_done": r}
                    failed = True
                    break
                elapsed = time.perf_counter() - t0
                times.append(elapsed)
                print(f"  decode rep {r+1}/{args.reps}: {elapsed:.3f}s")

            if not failed:
                total_med  = statistics.median(sorted(times))
                dec_only_s = total_med - cold_med
                tps        = budget / dec_only_s if dec_only_s > 0 else None
                decode_results[str(L)][f"budget_{budget}"] = {
                    "feasible":      True,
                    "total_refresh": summarise(times),
                    "decode_only_s": round(dec_only_s, 4),
                    "decode_tps":    round(tps, 2) if tps else None,
                    "note": "total_refresh = cold_prefill(L) + decode(budget); "
                            "decode_only_s = total_median - cold_prefill_median",
                }

        del llm
        gc.collect()
        torch.cuda.empty_cache()

    # ── Provenance ─────────────────────────────────────────────────────────────
    from _provenance import stamp
    prov = stamp(
        script="vllm_calibration.py",
        model=MODEL_SLUG,
        device=DEVICE_SLUG,
        n=len(l_sweep) * args.reps,
        args=args,
    )
    prov["vllm_version"]    = vllm_version
    prov["torch_version"]   = torch_version
    prov["cuda_version"]    = cuda_version
    prov["max_model_len"]   = MAX_MODEL_LEN
    prov["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES", "unset")
    prov["kv_note"] = (
        "peak_gpu_gb not reported: vLLM preallocates a fixed KV pool; "
        "torch.cuda.max_memory_allocated() returns 0 inside the vLLM worker process. "
        "Use kv_cache_config for pool size."
    )

    result = {
        "experiment":    "E26",
        "description":   "vLLM cold-prefill + decode calibration vs HF baseline (E21/E27)",
        "model":         MODEL_ID,
        "model_slug":    MODEL_SLUG,
        "device":        DEVICE_SLUG,
        "l_sweep":       l_sweep,
        "reps":          args.reps,
        "decode_budgets": DECODE_BUDGETS,
        "kv_cache_config": kv_info,
        "cold_prefill":  cold_results,
        "decode":        decode_results,
        "_provenance":   prov,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT_PATH}")

    # ── Summary table ──────────────────────────────────────────────────────────
    hf_cold = {1024: 0.165, 8192: 1.369, 32768: 7.805, 65536: 21.720}
    # HF update latency (prefill+decode) from phase1_cost_profiling.md, a6000/qwen7b
    hf_upd  = {
        1024:  {"80": 2.598, "200": 5.714},
        8192:  {"80": 4.804, "200": 9.565},
        32768: {"80": 15.930, "200": 26.879},
        65536: {"80": 15.925, "200": 26.881},
    }

    print("\nCOLD PREFILL")
    print(f"{'L':>8} | {'vLLM (s)':>10} | {'HF (s)':>8} | {'ratio':>6}")
    print("-" * 44)
    for L in l_sweep:
        r      = cold_results.get(str(L), {})
        v_s    = r.get("median_s", float("nan"))
        hf_s   = hf_cold.get(L, float("nan"))
        ratio  = hf_s / v_s if v_s and not (v_s != v_s) else float("nan")
        print(f"{L:>8,} | {v_s:>10.3f} | {hf_s:>8.3f} | {ratio:>5.2f}×")

    for bk in DECODE_BUDGETS:
        print(f"\nTOTAL REFRESH (budget={bk}): prefill(L) + generate({bk} tokens)")
        print(f"{'L':>8} | {'vLLM (s)':>10} | {'HF (s)':>8} | {'ratio':>6}")
        print("-" * 44)
        for L in l_sweep:
            dr = decode_results.get(str(L), {}).get(f"budget_{bk}", {})
            v_s   = dr.get("total_refresh", {}).get("median_s", float("nan"))
            hf_s  = hf_upd.get(L, {}).get(str(bk), float("nan"))
            ratio = hf_s / v_s if v_s and not (v_s != v_s) else float("nan")
            print(f"{L:>8,} | {v_s:>10.3f} | {hf_s:>8.3f} | {ratio:>5.2f}×")


if __name__ == "__main__":
    main()
