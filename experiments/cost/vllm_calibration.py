"""
E26 — vLLM cold-prefill calibration on A6000
=============================================
Measures TTFT (cold materialization cost) under vLLM with prefix_caching=False,
comparing to the HF baseline in results/cost/cost_matrix.csv.

Run on A6000 (GPU 1) — set CUDA_VISIBLE_DEVICES=1 before launching:
  CUDA_VISIBLE_DEVICES=1 python experiments/cost/vllm_calibration.py

Secondary warm-append is gated by --warm flag.
"""

import argparse
import gc
import json
import os
import statistics
import subprocess
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

DEFAULT_L_TOKENS = [1024, 8192, 32768, 65536]
DEFAULT_REPS     = 5
WARM_EXTEND_TOKS = 200   # tokens to extend in warm-append secondary


def nvidia_smi_mem_gb():
    """Return current used MiB on CUDA_VISIBLE_DEVICES=0 (remapped to GPU 1)."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True
        ).strip().splitlines()
        # With CUDA_VISIBLE_DEVICES=1 remapped to index 0 inside the process
        return int(out[0]) / 1024.0
    except Exception:
        return None


def peak_mem_gb():
    """Peak allocated GPU memory via torch (inside vLLM process)."""
    try:
        import torch
        return torch.cuda.max_memory_allocated() / (1024 ** 3)
    except Exception:
        return nvidia_smi_mem_gb()


def run_cold_pass(llm, prompts, sampling_params):
    """
    Time llm.generate() for a list of single-prompt calls.
    Returns list of elapsed seconds (one per prompt).
    """
    elapsed = []
    for p in prompts:
        t0 = time.perf_counter()
        llm.generate([p], sampling_params)
        elapsed.append(time.perf_counter() - t0)
    return elapsed


def summarise(vals):
    s = sorted(vals)
    med = statistics.median(s)
    q1 = statistics.median(s[: len(s) // 2])
    q3 = statistics.median(s[len(s) - len(s) // 2 :])
    return {"median_s": round(med, 4),
            "iqr_s": round(q3 - q1, 4),
            "all_s": [round(v, 4) for v in s]}


def build_prompt_text(corpus_turns, tok, target_L):
    """Build a context string of ~target_L tokens from the corpus."""
    turns, total = [], 0
    idx = 0
    while total < target_L and idx < len(corpus_turns):
        chunk = corpus_turns[idx % len(corpus_turns)]
        ids = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target_L * 1.15:
            break
        turns.append(chunk)
        total += len(ids)
        idx += 1
    while total < target_L * 0.9:
        chunk = corpus_turns[idx % len(corpus_turns)]
        ids = tok.encode(chunk, add_special_tokens=False)
        turns.append(chunk)
        total += len(ids)
        idx += 1
    context = "\n".join(turns)
    actual = len(tok.encode(context, add_special_tokens=False))
    return context, min(actual, target_L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--l-tokens", default=",".join(str(x) for x in DEFAULT_L_TOKENS),
                    help="Comma-separated L values to sweep")
    ap.add_argument("--reps", type=int, default=DEFAULT_REPS)
    ap.add_argument("--warm", action="store_true",
                    help="Also run warm-append secondary (prefix_caching=True)")
    ap.add_argument("--gpu-mem-fraction", type=float, default=0.92,
                    help="vLLM gpu_memory_utilization fraction")
    args = ap.parse_args()

    l_sweep = [int(x) for x in args.l_tokens.split(",")]

    # ── import corpus builder from cost_profile ────────────────────────────────
    from cost_profile import build_corpus

    # ── import vllm ────────────────────────────────────────────────────────────
    try:
        from vllm import LLM, SamplingParams
        import vllm
        vllm_version = vllm.__version__
    except ImportError as e:
        print(f"ERROR: vLLM not available in this environment: {e}", file=sys.stderr)
        sys.exit(1)

    import torch
    torch_version = torch.__version__
    cuda_version  = torch.version.cuda

    print(f"vLLM {vllm_version} | torch {torch_version} | CUDA {cuda_version}")
    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES','unset')}")

    # ── tokenizer for corpus building (use HF tok, not vllm's) ────────────────
    from transformers import AutoTokenizer
    print(f"Loading tokenizer for corpus sampling …")
    hf_tok = AutoTokenizer.from_pretrained(MODEL_ID)

    print(f"Building corpus …")
    corpus = build_corpus(hf_tok)
    print(f"  Corpus: {len(corpus)} chunks")

    # ── COLD MEASUREMENT (prefix_caching=False) ────────────────────────────────
    print("\n=== COLD PASS (enable_prefix_caching=False) ===")
    # max_model_len: let vLLM auto-detect from model config.
    # For L > model's max_position_embeddings, set VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
    # in the calling environment; vLLM will attempt the longer context.
    max_L = max(l_sweep)
    env_max_len = int(os.environ.get("VLLM_MAX_MODEL_LEN", max_L + 512))
    llm_cold = LLM(
        model=MODEL_ID,
        dtype="float16",
        gpu_memory_utilization=args.gpu_mem_fraction,
        enable_prefix_caching=False,
        max_model_len=env_max_len,
        enforce_eager=False,
    )
    sp_cold = SamplingParams(max_tokens=1, temperature=0.0)
    torch.cuda.reset_peak_memory_stats()

    cold_results = {}
    for L in l_sweep:
        print(f"\n  L={L:,} tokens …")
        prompt_text, actual_L = build_prompt_text(corpus, hf_tok, L)
        print(f"    actual tokens (hf_tok): {actual_L:,}")

        # Warm-up: one pass outside timing to avoid first-call JIT overhead
        try:
            llm_cold.generate([prompt_text], sp_cold)
        except Exception as e:
            print(f"    warm-up failed: {e}")
            cold_results[str(L)] = {"error": str(e), "feasible": False}
            continue

        # Timed reps
        times = []
        peak_gbs = []
        failed = False
        for r in range(args.reps):
            torch.cuda.reset_peak_memory_stats()
            t0 = time.perf_counter()
            try:
                llm_cold.generate([prompt_text], sp_cold)
            except Exception as e:
                print(f"    rep {r+1} failed: {e}")
                cold_results[str(L)] = {"error": str(e), "feasible": False, "reps_completed": r}
                failed = True
                break
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            peak_gbs.append(peak_mem_gb())
            print(f"    rep {r+1}/{args.reps}: {elapsed:.3f}s  peak={peak_gbs[-1]:.2f}GB")

        if not failed:
            cold_results[str(L)] = {
                "actual_L_tokens": actual_L,
                "feasible": True,
                **summarise(times),
                "peak_gpu_gb_median": round(statistics.median(peak_gbs), 2),
            }

    # Free cold engine
    del llm_cold
    gc.collect()
    torch.cuda.empty_cache()

    # ── WARM-APPEND SECONDARY (prefix_caching=True) ────────────────────────────
    warm_results = {}
    if args.warm:
        print("\n=== WARM-APPEND SECONDARY (enable_prefix_caching=True) ===")
        print("  NOTE: vLLM prefix-cache append is semantically different from")
        print("  HF KV-resident incremental append. vLLM reuses cached prefix KV")
        print("  for matching token sequences; this approximates warm append only")
        print("  when the same prefix is resent. Not directly comparable to HF incr_warm.")

        llm_warm = LLM(
            model=MODEL_ID,
            dtype="float16",
            gpu_memory_utilization=args.gpu_mem_fraction,
            enable_prefix_caching=True,
            max_model_len=env_max_len,
            enforce_eager=False,
        )
        sp_warm_full = SamplingParams(max_tokens=1, temperature=0.0)
        sp_warm_ext  = SamplingParams(max_tokens=1, temperature=0.0)

        ext_text = " ".join(["Continue."] * (WARM_EXTEND_TOKS // 2))

        for L in l_sweep:
            print(f"\n  L={L:,} tokens …")
            prompt_text, actual_L = build_prompt_text(corpus, hf_tok, L)
            extended_prompt = prompt_text + "\n" + ext_text

            # Prime the prefix cache
            llm_warm.generate([prompt_text], sp_warm_full)

            # Now measure extension (cache should be hit for the prefix)
            times = []
            for r in range(args.reps):
                t0 = time.perf_counter()
                llm_warm.generate([extended_prompt], sp_warm_ext)
                elapsed = time.perf_counter() - t0
                times.append(elapsed)
                print(f"    rep {r+1}/{args.reps}: {elapsed:.3f}s")

            warm_results[str(L)] = {
                "actual_L_tokens": actual_L,
                "extend_tokens": WARM_EXTEND_TOKS,
                **summarise(times),
                "note": (
                    "vLLM prefix-cache append: prefix cached from prior call; "
                    "extension includes ~200 new tokens. Not directly comparable "
                    "to HF KV-resident incr_warm (different engine internals)."
                ),
            }

        del llm_warm
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
    prov["vllm_version"]  = vllm_version
    prov["torch_version"] = torch_version
    prov["cuda_version"]  = cuda_version
    prov["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES", "unset")

    result = {
        "experiment": "E26",
        "description": "vLLM cold-prefill calibration vs HF baseline (E21)",
        "model": MODEL_ID,
        "model_slug": MODEL_SLUG,
        "device": DEVICE_SLUG,
        "prefix_caching_cold": False,
        "reps": args.reps,
        "l_sweep": l_sweep,
        "cold_prefill": cold_results,
        "warm_append_secondary": warm_results,
        "_provenance": prov,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT_PATH}")

    # Quick summary table
    print("\nL (tok)   | vLLM cold (s) | HF cold (s) | ratio")
    print("----------|---------------|-------------|------")
    hf_ref = {
        1024:  0.165,
        8192:  1.369,
        32768: 7.805,
        65536: 21.720,
    }
    for L in l_sweep:
        r = cold_results.get(str(L), {})
        vllm_s = r.get("median_s", float("nan"))
        hf_s   = hf_ref.get(L, float("nan"))
        ratio  = hf_s / vllm_s if vllm_s else float("nan")
        print(f"{L:9,} | {vllm_s:13.3f} | {hf_s:11.3f} | {ratio:.2f}×")


if __name__ == "__main__":
    main()
