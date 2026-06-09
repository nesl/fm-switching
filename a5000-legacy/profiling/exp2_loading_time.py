"""
Experiment 2: FM Loading Time (Migration Cost Floor)
====================================================
Measures cold-start loading time for VLM and LLM across multiple trials.
This is the minimum migration cost — even with zero KV cache, you pay this.

Each trial:
  1. Clears GPU memory completely
  2. Times model loading from disk → GPU ready
  3. Records time and memory

Hardware: NVIDIA A6000 (48GB)
Usage: python exp2_loading_time.py [--trials 5] [--vlm MODEL] [--llm MODEL]
"""

import torch
import gc
import time
import json
import argparse
import statistics
from datetime import datetime
from pathlib import Path


def clear_gpu():
    """Fully clear GPU memory."""
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()


def measure_load_time(model_id, model_type, load_kwargs, trial_num):
    """Load a model from scratch, return timing and memory info."""
    clear_gpu()
    torch.cuda.reset_peak_memory_stats()
    mem_before = torch.cuda.memory_allocated(0) / 1024**2

    torch.cuda.synchronize()
    t0 = time.perf_counter()

    if model_type == "vlm":
        from transformers import AutoModelForVision2Seq, AutoProcessor
        model = AutoModelForVision2Seq.from_pretrained(model_id, **load_kwargs)
        processor = AutoProcessor.from_pretrained(model_id)
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)
        tokenizer = AutoTokenizer.from_pretrained(model_id)

    torch.cuda.synchronize()
    load_time = time.perf_counter() - t0

    mem_after = torch.cuda.memory_allocated(0) / 1024**2
    model_mem = mem_after - mem_before

    print(f"    Trial {trial_num}: {load_time:.2f}s  (model memory: {model_mem:.0f} MB)")

    # Explicitly delete to free memory for next trial
    del model
    if model_type == "vlm":
        del processor
    else:
        del tokenizer
    clear_gpu()

    return {
        "trial": trial_num,
        "load_time_s": round(load_time, 3),
        "model_memory_mb": round(model_mem, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vlm", default="Qwen/Qwen2.5-VL-7B-Instruct")
    parser.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--trials", type=int, default=5,
                        help="Number of loading trials per model")
    parser.add_argument("--quantize", action="store_true", default=True)
    parser.add_argument("--no-quantize", dest="quantize", action="store_false")
    parser.add_argument("--output", default="exp2_results.json")
    args = parser.parse_args()

    print("=" * 70)
    print("EXPERIMENT 2: FM Loading Time (Migration Cost Floor)")
    print(f"  VLM: {args.vlm}")
    print(f"  LLM: {args.llm}")
    print(f"  Trials: {args.trials}")
    print(f"  Quantization: {'4-bit' if args.quantize else 'none'}")
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    load_kwargs = {"device_map": "cuda:0", "torch_dtype": torch.float16}
    if args.quantize:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )

    results = {
        "metadata": {
            "vlm": args.vlm,
            "llm": args.llm,
            "trials": args.trials,
            "quantization": "4-bit" if args.quantize else "none",
            "gpu": torch.cuda.get_device_name(0),
            "timestamp": datetime.now().isoformat(),
        },
        "vlm_trials": [],
        "llm_trials": [],
    }

    # ── VLM loading trials ───────────────────────────────────────────────
    print(f"\n── VLM Loading: {args.vlm} ──")
    for i in range(1, args.trials + 1):
        trial = measure_load_time(args.vlm, "vlm", load_kwargs, i)
        results["vlm_trials"].append(trial)

    vlm_times = [t["load_time_s"] for t in results["vlm_trials"]]
    vlm_mems = [t["model_memory_mb"] for t in results["vlm_trials"]]

    # ── LLM loading trials ───────────────────────────────────────────────
    print(f"\n── LLM Loading: {args.llm} ──")
    for i in range(1, args.trials + 1):
        trial = measure_load_time(args.llm, "llm", load_kwargs, i)
        results["llm_trials"].append(trial)

    llm_times = [t["load_time_s"] for t in results["llm_trials"]]
    llm_mems = [t["model_memory_mb"] for t in results["llm_trials"]]

    # ── Summary statistics ───────────────────────────────────────────────
    results["summary"] = {
        "vlm": {
            "mean_load_s": round(statistics.mean(vlm_times), 3),
            "std_load_s": round(statistics.stdev(vlm_times), 3) if len(vlm_times) > 1 else 0,
            "min_load_s": round(min(vlm_times), 3),
            "max_load_s": round(max(vlm_times), 3),
            "mean_memory_mb": round(statistics.mean(vlm_mems), 1),
        },
        "llm": {
            "mean_load_s": round(statistics.mean(llm_times), 3),
            "std_load_s": round(statistics.stdev(llm_times), 3) if len(llm_times) > 1 else 0,
            "min_load_s": round(min(llm_times), 3),
            "max_load_s": round(max(llm_times), 3),
            "mean_memory_mb": round(statistics.mean(llm_mems), 1),
        },
    }

    # ── Save ─────────────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n{'=' * 70}")
    print(f"Results saved to {out_path}")
    print(f"\n── Summary ──")
    print(f"  VLM load time: {results['summary']['vlm']['mean_load_s']:.2f}s "
          f"± {results['summary']['vlm']['std_load_s']:.2f}s  "
          f"(memory: {results['summary']['vlm']['mean_memory_mb']:.0f} MB)")
    print(f"  LLM load time: {results['summary']['llm']['mean_load_s']:.2f}s "
          f"± {results['summary']['llm']['std_load_s']:.2f}s  "
          f"(memory: {results['summary']['llm']['mean_memory_mb']:.0f} MB)")
    print(f"\n  These are the MINIMUM migration costs (model loading only).")
    print(f"  Any KV cache reconstruction adds to this baseline.")


if __name__ == "__main__":
    main()