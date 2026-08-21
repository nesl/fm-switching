"""
E26 — vLLM cold-prefill + decode + warm-append calibration on A6000
=====================================================================
Measurements:
  1. TTFT (cold prefill, prefix_caching=False) at L ∈ {1k,8k,32k,64k}, 5 reps
  2. Total refresh latency (prefill(L) + decode(budget)) for budget ∈ {80, 200}
  3. Warm-append (prefix_caching=True): prime cache with L tokens, then extend
     by ~200 tokens, 5 reps. Directly comparable to HF "incremental warm".
  4. YaRN retry for L=32768 and L=65536: rope_scaling via local config override.

Cross-engine comparison note:
  Items 1-3 are fully within vLLM so the window-vs-summary gap is valid.
  HF incremental warm reference: 66ms@1k, 62ms@8k (from phase1_cost_profiling.md).

KV-memory note:
  vLLM preallocates a fixed GPU memory pool; torch.cuda.max_memory_allocated()
  returns 0 inside the vLLM worker. KV pool metadata is reported from engine logs.

Run on A6000 (GPU 1):
  CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID \\
  VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \\
  python experiments/cost/vllm_calibration.py
"""

import argparse
import gc
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
sys.path.insert(0, str(ROOT / "experiments" / "cost"))

MODEL_ID    = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG  = "qwen7b"
DEVICE_SLUG = "a6000"
OUT_PATH    = ROOT / "results" / "cost" / "vllm_calibration_a6000_qwen7b.json"

MAX_MODEL_LEN    = 131072
DEFAULT_L_TOKENS = [1024, 8192, 32768, 65536]
DEFAULT_REPS     = 5
DECODE_BUDGETS   = [80, 200]

# YaRN config to retry L=32768/65536
YARN_ROPE_SCALING = {
    "type": "yarn",
    "factor": 4.0,
    "original_max_position_embeddings": 32768,
}
YARN_L_SWEEP = [32768, 65536]


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
    """Build context of ≤target_L tokens, clipped to exactly target_L."""
    turns, total = [], 0
    idx = 0
    while total < target_L and idx < len(corpus_turns):
        chunk = corpus_turns[idx % len(corpus_turns)]
        ids   = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target_L:
            clip  = target_L - total
            turns.append(tok.decode(ids[:clip]))
            total += clip
            break
        turns.append(chunk)
        total += len(ids)
        idx   += 1
    context = "\n".join(turns)
    actual  = len(tok.encode(context, add_special_tokens=False))
    return context, actual


def build_extension(corpus_turns, tok, prompt_idx, target=200):
    """Build ~target-token extension from corpus after the prompt."""
    turns, total = [], 0
    idx = prompt_idx
    while total < target:
        chunk = corpus_turns[idx % len(corpus_turns)]
        ids   = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target:
            clip = target - total
            turns.append(tok.decode(ids[:clip]))
            total += clip
            break
        turns.append(chunk)
        total += len(ids)
        idx   += 1
    return "\n".join(turns), total


def make_engine(model_path, gpu_mem_frac, prefix_caching, max_model_len):
    from vllm import LLM
    return LLM(
        model=model_path,
        dtype="float16",
        gpu_memory_utilization=gpu_mem_frac,
        enable_prefix_caching=prefix_caching,
        max_model_len=max_model_len,
        enforce_eager=False,
    )


def make_yarn_model_dir(base_model_cache_path):
    """Create a temp dir with modified config.json (YaRN) + symlinks to weights."""
    tmp = Path(tempfile.mkdtemp()) / "qwen_yarn"
    tmp.mkdir()
    src = Path(base_model_cache_path)
    cfg = json.loads((src / "config.json").read_text())
    cfg["rope_scaling"] = YARN_ROPE_SCALING
    (tmp / "config.json").write_text(json.dumps(cfg, indent=2))
    for f in src.iterdir():
        if f.name != "config.json":
            (tmp / f.name).symlink_to(f.resolve())
    return str(tmp)


def find_model_cache_path():
    """Locate the HF snapshot dir for Qwen2.5-7B-Instruct."""
    base = Path.home() / ".cache" / "huggingface" / "hub" / "models--Qwen--Qwen2.5-7B-Instruct" / "snapshots"
    if base.exists():
        snaps = sorted(base.iterdir())
        if snaps:
            return str(snaps[-1])
    return None


def measure_cold_and_decode(llm, prompt_text, reps, decode_budgets):
    """Cold prefill (max_tokens=1) + decode for each budget. Returns (cold, decode) dicts."""
    from vllm import SamplingParams
    sp_cold = SamplingParams(max_tokens=1, temperature=0.0)
    cold_times = []
    failed = False

    # Warm-up
    try:
        llm.generate([prompt_text], sp_cold)
    except Exception as e:
        return {"feasible": False, "error": str(e)}, {}

    for r in range(reps):
        t0 = time.perf_counter()
        try:
            llm.generate([prompt_text], sp_cold)
        except Exception as e:
            print(f"    cold rep {r+1} failed: {e}")
            return {"feasible": False, "error": str(e), "reps_done": r}, {}
        elapsed = time.perf_counter() - t0
        cold_times.append(elapsed)
        print(f"    cold rep {r+1}/{reps}: {elapsed:.3f}s")

    cold_result = {"feasible": True, **summarise(cold_times)}
    cold_med    = statistics.median(sorted(cold_times))

    decode_results = {}
    for budget in decode_budgets:
        sp_dec = SamplingParams(max_tokens=budget, min_tokens=budget, temperature=0.0)
        try:
            llm.generate([prompt_text], sp_dec)  # warm-up
        except Exception as e:
            print(f"    decode budget={budget} warm-up failed: {e}")
            decode_results[f"budget_{budget}"] = {"feasible": False, "error": str(e)}
            continue

        times = []
        for r in range(reps):
            t0 = time.perf_counter()
            try:
                llm.generate([prompt_text], sp_dec)
            except Exception as e:
                print(f"    decode budget={budget} rep {r+1} failed: {e}")
                decode_results[f"budget_{budget}"] = {"feasible": False, "error": str(e), "reps_done": r}
                failed = True
                break
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            print(f"    decode budget={budget} rep {r+1}/{reps}: {elapsed:.3f}s")

        if not failed and times:
            total_med  = statistics.median(sorted(times))
            dec_only   = total_med - cold_med
            tps        = budget / dec_only if dec_only > 0 else None
            decode_results[f"budget_{budget}"] = {
                "feasible":      True,
                "total_refresh": summarise(times),
                "decode_only_s": round(dec_only, 4),
                "decode_tps":    round(tps, 2) if tps else None,
                "note": "total_refresh = cold_prefill + decode(budget); decode_only = total_med - cold_med",
            }

    return cold_result, decode_results


def measure_warm_append(llm, prompt_text, extension_text, actual_ext_toks, reps):
    """Prefix-cache warm append: prime cache with prompt, time extension. Returns result dict."""
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)
    extended = prompt_text + "\n" + extension_text

    # Prime the prefix cache
    try:
        llm.generate([prompt_text], sp)
    except Exception as e:
        return {"feasible": False, "error": f"cache prime failed: {e}"}

    # Warm-up of the extension call
    try:
        llm.generate([extended], sp)
    except Exception as e:
        return {"feasible": False, "error": f"extension warm-up failed: {e}"}

    times = []
    for r in range(reps):
        # Re-prime to ensure the prefix is still cached
        llm.generate([prompt_text], sp)
        t0 = time.perf_counter()
        try:
            llm.generate([extended], sp)
        except Exception as e:
            return {"feasible": False, "error": str(e), "reps_done": r}
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        print(f"    warm-append rep {r+1}/{reps}: {elapsed:.3f}s")

    med = statistics.median(sorted(times))
    return {
        "feasible":          True,
        "extension_tokens":  actual_ext_toks,
        **summarise(times),
        "note": "time for vLLM to process extension with prefix cached; prefix re-primed each rep",
    }


def run_l_point(model_path, L, corpus, hf_tok, reps, decode_budgets, gpu_mem_frac,
                label=""):
    """Run all measurements for one L point. Returns (actual_L, cold, decode, warm) dicts."""
    import torch

    prompt_text, actual_L = build_prompt_text(corpus, hf_tok, L)
    # Extension: ~200 tokens from the second half of the corpus (won't overlap with prompt).
    ext_start = len(corpus) // 2
    extension_text, ext_toks = build_extension(corpus, hf_tok, ext_start, target=200)
    print(f"\n  L={L:,}{label}: actual={actual_L:,}tok  extension={ext_toks}tok")

    # ── Phase A: cold + decode (prefix_caching=False) ─────────────────────────
    print(f"  Initialising cold engine …")
    cold_result = decode_result = {"feasible": False, "error": "not run"}
    try:
        llm_cold = make_engine(model_path, gpu_mem_frac, False, MAX_MODEL_LEN)
    except Exception as e:
        print(f"  Engine init failed: {e}")
        return actual_L, {"feasible": False, "error": str(e)}, {}, {"feasible": False, "error": "cold init failed"}

    cold_result, decode_result = measure_cold_and_decode(
        llm_cold, prompt_text, reps, decode_budgets)

    del llm_cold
    gc.collect()
    torch.cuda.empty_cache()

    if not cold_result.get("feasible"):
        return actual_L, cold_result, decode_result, {"feasible": False, "error": "cold infeasible"}

    # ── Phase B: warm append (prefix_caching=True) ────────────────────────────
    print(f"  Initialising warm engine (prefix_caching=True) …")
    try:
        llm_warm = make_engine(model_path, gpu_mem_frac, True, MAX_MODEL_LEN)
    except Exception as e:
        print(f"  Warm engine init failed: {e}")
        gc.collect(); torch.cuda.empty_cache()
        return actual_L, cold_result, decode_result, {"feasible": False, "error": str(e)}

    print(f"  Warm append measurement …")
    warm_result = measure_warm_append(llm_warm, prompt_text, extension_text, ext_toks, reps)

    del llm_warm
    gc.collect()
    torch.cuda.empty_cache()

    return actual_L, cold_result, decode_result, warm_result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--l-tokens",         default=",".join(str(x) for x in DEFAULT_L_TOKENS))
    ap.add_argument("--reps",             type=int, default=DEFAULT_REPS)
    ap.add_argument("--gpu-mem-fraction", type=float, default=0.92)
    ap.add_argument("--skip-yarn",        action="store_true", help="Skip YaRN retry")
    args = ap.parse_args()

    l_sweep = [int(x) for x in args.l_tokens.split(",")]

    from cost_profile import build_corpus
    try:
        from vllm import LLM, SamplingParams
        import vllm
        vllm_version = vllm.__version__
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

    import torch
    torch_version = torch.__version__
    cuda_version  = torch.version.cuda

    print(f"vLLM {vllm_version} | torch {torch_version} | CUDA {cuda_version}")
    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES','unset')}")

    from transformers import AutoTokenizer
    print("Loading tokenizer …")
    hf_tok = AutoTokenizer.from_pretrained(MODEL_ID)
    print("Building corpus …")
    corpus = build_corpus(hf_tok)
    print(f"  {len(corpus)} chunks")

    cold_results   = {}
    decode_results = {}
    warm_results   = {}
    engine_failed  = False
    kv_info        = {"total_kv_tokens": 517264, "block_size": 16,
                      "note": "from engine log: GPU KV cache size: 517,264 tokens at max_model_len=131072"}

    # ── Main sweep ────────────────────────────────────────────────────────────
    for L in l_sweep:
        if engine_failed:
            cold_results[str(L)]   = {"feasible": False, "error": "skipped: prior L failed"}
            decode_results[str(L)] = {}
            warm_results[str(L)]   = {"feasible": False, "error": "skipped"}
            continue

        actual_L, cr, dr, wr = run_l_point(
            MODEL_ID, L, corpus, hf_tok, args.reps,
            DECODE_BUDGETS, args.gpu_mem_fraction)

        cold_results[str(L)]   = {"actual_L_tokens": actual_L, **cr}
        decode_results[str(L)] = {"actual_L_tokens": actual_L, **dr}
        warm_results[str(L)]   = {"actual_L_tokens": actual_L, **wr}

        if not cr.get("feasible"):
            engine_failed = True

    # ── YaRN retry for large L ────────────────────────────────────────────────
    yarn_results = {}
    if not args.skip_yarn:
        print(f"\n{'='*60}")
        print(f"  YaRN retry: L ∈ {YARN_L_SWEEP}")
        print(f"  rope_scaling={YARN_ROPE_SCALING}")
        print(f"{'='*60}")
        cache_path = find_model_cache_path()
        if cache_path:
            yarn_dir = make_yarn_model_dir(cache_path)
            print(f"  YaRN config dir: {yarn_dir}")
            yarn_failed = False
            for L in YARN_L_SWEEP:
                if yarn_failed:
                    yarn_results[str(L)] = {"feasible": False, "error": "skipped: prior YaRN L failed"}
                    continue
                actual_L, cr, dr, wr = run_l_point(
                    yarn_dir, L, corpus, hf_tok, args.reps,
                    DECODE_BUDGETS, args.gpu_mem_fraction, label=" (YaRN)")
                yarn_results[str(L)] = {
                    "actual_L_tokens": actual_L,
                    "rope_scaling":    YARN_ROPE_SCALING,
                    "cold_prefill":    cr,
                    "decode":          dr,
                    "warm_append":     wr,
                }
                if not cr.get("feasible"):
                    yarn_failed = True
            shutil.rmtree(Path(yarn_dir).parent, ignore_errors=True)
        else:
            yarn_results = {"error": "model cache path not found"}

    # ── Provenance ─────────────────────────────────────────────────────────────
    from _provenance import stamp
    prov = stamp(
        script="vllm_calibration.py",
        model=MODEL_SLUG, device=DEVICE_SLUG,
        n=len(l_sweep) * args.reps, args=args)
    prov["vllm_version"]          = vllm_version
    prov["torch_version"]         = torch_version
    prov["cuda_version"]          = cuda_version
    prov["max_model_len"]         = MAX_MODEL_LEN
    prov["cuda_visible_devices"]  = os.environ.get("CUDA_VISIBLE_DEVICES", "unset")
    prov["kv_note"] = (
        "peak_gpu_gb not reported: vLLM preallocates KV pool; "
        "torch.cuda.max_memory_allocated()=0 inside vLLM worker. See kv_cache_config.")

    result = {
        "experiment":    "E26",
        "description":   "vLLM cold-prefill + decode + warm-append calibration vs HF baseline",
        "model":         MODEL_ID, "model_slug": MODEL_SLUG, "device": DEVICE_SLUG,
        "l_sweep":       l_sweep, "reps": args.reps, "decode_budgets": DECODE_BUDGETS,
        "kv_cache_config": kv_info,
        "cold_prefill":  cold_results,
        "decode":        decode_results,
        "warm_append":   warm_results,
        "yarn_retry":    yarn_results,
        "_provenance":   prov,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT_PATH}")

    # ── Summary ───────────────────────────────────────────────────────────────
    hf_cold  = {1024: 0.165, 8192: 1.369, 32768: 7.805, 65536: 21.720}
    hf_warm  = {1024: 0.066, 8192: 0.062, 32768: 0.065, 65536: 0.068}
    hf_upd   = {
        1024:  {"80": 2.598, "200": 5.714},
        8192:  {"80": 4.804, "200": 9.565},
        32768: {"80": 15.930, "200": 26.879},
        65536: {"80": 15.925, "200": 26.881},
    }

    print("\nCOLD PREFILL")
    print(f"{'L':>8} | {'vLLM(s)':>8} | {'HF(s)':>7} | {'HF/vLLM':>8}")
    for L in l_sweep:
        cr = cold_results.get(str(L), {})
        vc = cr.get("median_s", float("nan"))
        hc = hf_cold.get(L, float("nan"))
        print(f"{L:>8,} | {vc:>8.3f} | {hc:>7.3f} | {hc/vc:>7.2f}×" if vc == vc and vc else
              f"{L:>8,} | {'infeas':>8} | {hc:>7.3f} | {'—':>8}")

    print("\nWARM APPEND (~200 token extension)")
    print(f"{'L':>8} | {'vLLM(s)':>8} | {'HF(s)':>7} | {'HF/vLLM':>8}")
    for L in l_sweep:
        wr = warm_results.get(str(L), {})
        vw = wr.get("median_s", float("nan")) if wr.get("feasible") else float("nan")
        hw = hf_warm.get(L, float("nan"))
        print(f"{L:>8,} | {vw:>8.3f} | {hw:>7.3f} | {hw/vw:>7.2f}×" if vw == vw and wr.get("feasible") else
              f"{L:>8,} | {'infeas':>8} | {hw:>7.3f} | {'—':>8}")

    for bk in DECODE_BUDGETS:
        print(f"\nTOTAL REFRESH (budget={bk})")
        print(f"{'L':>8} | {'vLLM(s)':>8} | {'HF(s)':>7} | {'HF/vLLM':>8}")
        for L in l_sweep:
            dr  = decode_results.get(str(L), {}).get(f"budget_{bk}", {})
            vt  = dr.get("total_refresh", {}).get("median_s", float("nan")) if dr.get("feasible") else float("nan")
            ht  = hf_upd.get(L, {}).get(str(bk), float("nan"))
            print(f"{L:>8,} | {vt:>8.3f} | {ht:>7.3f} | {ht/vt:>7.2f}×" if vt == vt and dr.get("feasible") else
                  f"{L:>8,} | {'infeas':>8} | {ht:>7.3f} | {'—':>8}")

    print("\nYaRN RESULTS")
    for L in YARN_L_SWEEP:
        yr = yarn_results.get(str(L), {})
        cr = yr.get("cold_prefill", {})
        wr = yr.get("warm_append", {})
        vc = cr.get("median_s", "infeas") if cr.get("feasible") else "infeas"
        vw = wr.get("median_s", "infeas") if wr.get("feasible") else "infeas"
        print(f"  L={L:,}: cold={vc}s  warm={vw}s")


if __name__ == "__main__":
    main()
