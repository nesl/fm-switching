"""
Experiment 1: Memory Footprint & Loading Time on Jetson
=======================================================
For each model, measures:
  - Cold-start loading time (seconds)
  - GPU memory consumed by weights (MB)
  - Peak system power during loading (W)
  - GPU temperature after loading (C)

Runs multiple trials per model with full GPU clear between trials.
"""

import torch
import gc
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# ── jtop helper (optional, graceful fallback) ────────────────────────────

JTOP_AVAILABLE = False
try:
    from jtop import jtop
    JTOP_AVAILABLE = True
except ImportError:
    pass


def get_jetson_stats():
    """Grab a single jtop sample. Returns dict or None."""
    if not JTOP_AVAILABLE:
        return None
    try:
        with jtop() as j:
            return {
                "power_w": j.power[0].get("tot", {}).get("avg", 0) / 1000.0
                           if isinstance(j.power[0], dict)
                           else sum(v / 1000.0 for v in j.power[1].values()) if j.power else 0,
                "gpu_temp_c": j.temperature.get("GPU", 0),
                "cpu_temp_c": j.temperature.get("CPU", 0),
            }
    except Exception:
        return None


# ── GPU memory helpers ───────────────────────────────────────────────────

def gpu_mem_mb():
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated(0) / 1024**2
    return 0


def gpu_total_mb():
    if torch.cuda.is_available():
        return torch.cuda.get_device_properties(0).total_memory / 1024**2
    return 0


def clear_gpu():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


# ── Model definitions ────────────────────────────────────────────────────

MODELS = {
    # VLMs
    "smolvlm-256m":   {"id": "HuggingFaceTB/SmolVLM-256M-Instruct",  "type": "vlm"},
    "smolvlm-500m":   {"id": "HuggingFaceTB/SmolVLM-500M-Instruct",  "type": "vlm"},
    "qwen2.5-vl-3b":  {"id": "Qwen/Qwen2.5-VL-3B-Instruct",         "type": "vlm"},
    "paligemma-3b":   {"id": "google/paligemma-3b-mix-224",           "type": "vlm"},
    # LLMs
    "smollm2-135m":   {"id": "HuggingFaceTB/SmolLM2-135M-Instruct",  "type": "llm"},
    "smollm2-1.7b":   {"id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",  "type": "llm"},
    "qwen2.5-1.5b":   {"id": "Qwen/Qwen2.5-1.5B-Instruct",          "type": "llm"},
    "qwen2.5-3b":     {"id": "Qwen/Qwen2.5-3B-Instruct",            "type": "llm"},
}

# Pre-quantized bnb-4bit repos (Unsloth). Weights already 4-bit on disk → smaller
# download and faster load (no runtime quantize step). Models without an entry
# fall back to runtime bnb quantization on the original FP16 repo.
PREQUANT_BNB_MAP = {
    "Qwen/Qwen2.5-VL-3B-Instruct":         "unsloth/Qwen2.5-VL-3B-Instruct-bnb-4bit",
    "Qwen/Qwen2.5-3B-Instruct":            "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",
    "Qwen/Qwen2.5-1.5B-Instruct":          "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct": "unsloth/SmolLM2-1.7B-Instruct-bnb-4bit",
}


def resolve_model_id(model_id, quantization):
    """Returns (effective_id, skip_runtime_quant). For prequant-bnb mode, swaps
    in the pre-quantized repo when available; otherwise falls through to runtime bnb.
    Also detects pre-quantized IDs passed directly so we don't double-quantize."""
    if model_id.endswith("-bnb-4bit") or model_id in PREQUANT_BNB_MAP.values():
        return model_id, True
    if quantization == "prequant-bnb" and model_id in PREQUANT_BNB_MAP:
        return PREQUANT_BNB_MAP[model_id], True
    return model_id, False


def load_model(model_id, model_type, quantization="bnb"):
    """Load a model and return (model, processor/tokenizer, effective_id)."""
    effective_id, skip_quant = resolve_model_id(model_id, quantization)
    load_kwargs = {"device_map": "auto", "torch_dtype": torch.float16}
    needs_runtime_quant = quantization in ("bnb", "prequant-bnb") and not skip_quant
    if needs_runtime_quant:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )

    # Architecture detection still uses the original model_id (effective ids may
    # be name-mangled, e.g. "...-bnb-4bit" without "qwen" or "smolvlm" markers
    # — but in practice unsloth keeps the base name, so checking effective_id works too).
    arch_hint = effective_id.lower()
    if model_type == "vlm":
        if "paligemma" in arch_hint:
            from transformers import PaliGemmaForConditionalGeneration, AutoProcessor
            model = PaliGemmaForConditionalGeneration.from_pretrained(effective_id, **load_kwargs)
            proc = AutoProcessor.from_pretrained(effective_id)
        elif "smolvlm" in arch_hint:
            from transformers import AutoModelForVision2Seq, AutoProcessor
            model = AutoModelForVision2Seq.from_pretrained(effective_id, **load_kwargs)
            proc = AutoProcessor.from_pretrained(effective_id)
        elif "qwen2.5-vl" in arch_hint or "qwen2_5_vl" in arch_hint:
            from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(effective_id, **load_kwargs)
            proc = AutoProcessor.from_pretrained(effective_id)
        else:
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            model = Qwen2VLForConditionalGeneration.from_pretrained(effective_id, **load_kwargs)
            proc = AutoProcessor.from_pretrained(effective_id)
        return model, proc, effective_id
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        model = AutoModelForCausalLM.from_pretrained(effective_id, **load_kwargs)
        tok = AutoTokenizer.from_pretrained(effective_id)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        return model, tok, effective_id


def main():
    parser = argparse.ArgumentParser(description="Exp 1: Memory & loading time")
    parser.add_argument("--models", nargs="+", default=list(MODELS.keys()),
                        help="Which models to profile (default: all)")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"], default="bnb",
                        help="bnb: runtime 4-bit quantize FP16 weights (current default). "
                             "prequant-bnb: load pre-quantized 4-bit repos (Unsloth) where available, "
                             "else fall back to runtime bnb. fp16: no quantization.")
    parser.add_argument("--memory-limit", type=float, default=None,
                        help="Cap GPU memory in GB (simulates a smaller device). Default: no cap.")
    parser.add_argument("--output", default="results/exp1.json")
    parser.add_argument("--delete-after", action="store_true", default=True,
                        help="Delete each model's HF cache after profiling (saves disk on Jetson)")
    parser.add_argument("--keep-cache", dest="delete_after", action="store_false")
    args = parser.parse_args()

    if args.memory_limit and torch.cuda.is_available():
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        fraction = min(args.memory_limit / total_gb, 1.0)
        torch.cuda.set_per_process_memory_fraction(fraction, 0)
        print(f"  GPU memory cap: {args.memory_limit:.1f} GB ({fraction:.1%} of {total_gb:.1f} GB)")

    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    total_mem = gpu_total_mb()

    print("=" * 60)
    print("EXP 1: Memory Footprint & Loading Time")
    print(f"  Device: {device_name}")
    print(f"  Total GPU memory: {total_mem:.0f} MB")
    print(f"  Quantization mode: {args.quantization}")
    print(f"  jtop available: {JTOP_AVAILABLE}")
    print(f"  Trials per model: {args.trials}")
    print("=" * 60)

    results = {
        "metadata": {
            "device": device_name,
            "total_memory_mb": round(total_mem, 1),
            "quantization": args.quantization,
            "jtop_available": JTOP_AVAILABLE,
            "timestamp": datetime.now().isoformat(),
        },
        "models": {},
    }

    for name in args.models:
        if name not in MODELS:
            print(f"\n  Skipping unknown model: {name}")
            continue

        info = MODELS[name]
        print(f"\n{'─' * 40}")
        print(f"  Model: {name} ({info['id']})")
        print(f"{'─' * 40}")

        trials = []
        effective_id = info["id"]  # actual repo loaded (may differ from info["id"] in prequant mode)
        for t in range(1, args.trials + 1):
            clear_gpu()
            time.sleep(2)  # let GPU settle

            mem_before = gpu_mem_mb()
            stats_before = get_jetson_stats()

            torch.cuda.synchronize()
            t0 = time.perf_counter()

            try:
                model, proc, effective_id = load_model(info["id"], info["type"], args.quantization)
                torch.cuda.synchronize()
                load_time = time.perf_counter() - t0

                mem_after = gpu_mem_mb()
                model_mem = mem_after - mem_before
                stats_after = get_jetson_stats()

                trial_data = {
                    "trial": t,
                    "load_time_s": round(load_time, 3),
                    "model_memory_mb": round(model_mem, 1),
                    "mem_before_mb": round(mem_before, 1),
                    "mem_after_mb": round(mem_after, 1),
                    "effective_id": effective_id,
                }
                if stats_after:
                    trial_data["power_after_w"] = stats_after.get("power_w", 0)
                    trial_data["gpu_temp_after_c"] = stats_after.get("gpu_temp_c", 0)

                print(f"    Trial {t}: {load_time:.2f}s, {model_mem:.0f} MB")
                trials.append(trial_data)

                del model, proc

            except Exception as e:
                print(f"    Trial {t}: FAILED - {e}")
                trials.append({"trial": t, "status": f"error: {str(e)}"})

            clear_gpu()

        # Summary for this model
        good_trials = [t for t in trials if "load_time_s" in t]
        if good_trials:
            load_times = [t["load_time_s"] for t in good_trials]
            mems = [t["model_memory_mb"] for t in good_trials]
            results["models"][name] = {
                "model_id": info["id"],
                "model_type": info["type"],
                "trials": trials,
                "summary": {
                    "mean_load_s": round(sum(load_times) / len(load_times), 3),
                    "min_load_s": round(min(load_times), 3),
                    "max_load_s": round(max(load_times), 3),
                    "mean_memory_mb": round(sum(mems) / len(mems), 1),
                },
            }
            s = results["models"][name]["summary"]
            print(f"  Summary: {s['mean_load_s']:.2f}s avg, {s['mean_memory_mb']:.0f} MB")
        else:
            results["models"][name] = {"model_id": info["id"], "trials": trials, "status": "all_failed"}

        # Save partial results after each model (so a crash mid-run doesn't lose data)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2))

        # Delete this model's HF cache to free disk before the next model
        if args.delete_after:
            import shutil
            cache_root = Path.home() / ".cache" / "huggingface" / "hub"
            cache_dir_name = "models--" + effective_id.replace("/", "--")
            cache_path = cache_root / cache_dir_name
            if cache_path.exists():
                size_gb = sum(f.stat().st_size for f in cache_path.rglob("*") if f.is_file()) / 1024**3
                shutil.rmtree(cache_path, ignore_errors=True)
                print(f"  Cache deleted: {cache_dir_name} ({size_gb:.2f} GB freed)")

    # Save
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
