"""
Experiment 1: Memory Breakdown for VLM + LLM Co-Loading
========================================================
Measures:
  1. Baseline GPU memory before loading any model
  2. Memory after loading VLM (Qwen2.5-VL-7B-Instruct, 4-bit)
  3. Memory after co-loading LLM (Qwen2.5-7B-Instruct, 4-bit)
  4. Peak activation memory during VLM inference with varying:
     - Number of images: 1, 2, 4, 6
     - Resolutions: 224x224, 448x448, 768x768

Hardware: NVIDIA A6000 (48GB)
Usage: python exp1_memory_breakdown.py [--vlm MODEL] [--llm MODEL]
"""

import torch
import gc
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

def get_gpu_memory_mb():
    """Return (allocated_MB, reserved_MB, total_MB) for cuda:0."""
    return (
        torch.cuda.memory_allocated(0) / 1024**2,
        torch.cuda.memory_reserved(0) / 1024**2,
        torch.cuda.get_device_properties(0).total_memory / 1024**2,
    )

def log_memory(label, results_list):
    alloc, reserved, total = get_gpu_memory_mb()
    entry = {
        "label": label,
        "allocated_mb": round(alloc, 1),
        "reserved_mb": round(reserved, 1),
        "total_mb": round(total, 1),
        "free_mb": round(total - reserved, 1),
    }
    results_list.append(entry)
    print(f"  [{label}]  alloc={alloc:.0f} MB  reserved={reserved:.0f} MB  free={total-reserved:.0f} MB")
    return entry

def clear_cache():
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

def make_dummy_images(n, resolution):
    """Create n PIL images at the given resolution."""
    from PIL import Image
    import numpy as np
    imgs = []
    for _ in range(n):
        arr = np.random.randint(0, 255, (resolution, resolution, 3), dtype=np.uint8)
        imgs.append(Image.fromarray(arr))
    return imgs

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vlm", default="Qwen/Qwen2.5-VL-7B-Instruct",
                        help="HuggingFace VLM model ID")
    parser.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct",
                        help="HuggingFace LLM model ID")
    parser.add_argument("--quantize", action="store_true", default=True,
                        help="Load models in 4-bit quantization (default: True)")
    parser.add_argument("--no-quantize", dest="quantize", action="store_false")
    parser.add_argument("--output", default="exp1_results.json",
                        help="Output JSON file")
    args = parser.parse_args()

    print("=" * 70)
    print("EXPERIMENT 1: Memory Breakdown — VLM + LLM Co-Loading")
    print(f"  VLM: {args.vlm}")
    print(f"  LLM: {args.llm}")
    print(f"  Quantization: {'4-bit' if args.quantize else 'none'}")
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    results = {
        "metadata": {
            "vlm": args.vlm,
            "llm": args.llm,
            "quantization": "4-bit" if args.quantize else "none",
            "gpu": torch.cuda.get_device_name(0),
            "gpu_total_mb": round(torch.cuda.get_device_properties(0).total_memory / 1024**2, 1),
            "timestamp": datetime.now().isoformat(),
        },
        "memory_stages": [],
        "activation_scaling": [],
    }

    # ── Quantization config ──────────────────────────────────────────────
    load_kwargs = {"device_map": "cuda:0", "torch_dtype": torch.float16}
    if args.quantize:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )

    # ── Stage 0: Baseline ────────────────────────────────────────────────
    clear_cache()
    print("\n── Stage 0: Baseline (no models loaded) ──")
    log_memory("baseline", results["memory_stages"])

    # ── Stage 1: Load VLM ────────────────────────────────────────────────
    print(f"\n── Stage 1: Loading VLM ({args.vlm}) ──")
    from transformers import AutoModelForVision2Seq, AutoProcessor
    t0 = time.time()
    vlm = AutoModelForVision2Seq.from_pretrained(args.vlm, **load_kwargs)
    vlm_processor = AutoProcessor.from_pretrained(args.vlm)
    vlm_load_time = time.time() - t0
    print(f"  VLM loaded in {vlm_load_time:.1f}s")
    log_memory("vlm_loaded", results["memory_stages"])
    results["metadata"]["vlm_load_time_s"] = round(vlm_load_time, 2)

    # ── Stage 2: Load LLM ────────────────────────────────────────────────
    print(f"\n── Stage 2: Loading LLM ({args.llm}) ──")
    from transformers import AutoModelForCausalLM, AutoTokenizer
    t0 = time.time()
    llm = AutoModelForCausalLM.from_pretrained(args.llm, **load_kwargs)
    llm_tokenizer = AutoTokenizer.from_pretrained(args.llm)
    llm_load_time = time.time() - t0
    print(f"  LLM loaded in {llm_load_time:.1f}s")
    log_memory("vlm_plus_llm_loaded", results["memory_stages"])
    results["metadata"]["llm_load_time_s"] = round(llm_load_time, 2)

    # ── Stage 3: Activation memory scaling ───────────────────────────────
    print("\n── Stage 3: VLM Activation Memory Scaling ──")
    print("  (Measuring peak memory during VLM inference)")

    num_images_list = [1, 2, 4, 6]
    resolutions = [224, 448, 768]

    for res in resolutions:
        for n_imgs in num_images_list:
            clear_cache()
            # Record memory before inference
            alloc_before = torch.cuda.memory_allocated(0) / 1024**2

            print(f"\n  Config: {n_imgs} image(s) @ {res}x{res}")
            images = make_dummy_images(n_imgs, res)

            # Build the multi-image message for Qwen2.5-VL
            image_content = [{"type": "image", "image": img} for img in images]
            image_content.append({"type": "text", "text": "Describe the driving scene."})
            messages = [{"role": "user", "content": image_content}]

            try:
                # Process inputs
                from qwen_vl_utils import process_vision_info
                text_input = vlm_processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                image_inputs, video_inputs = process_vision_info(messages)
                inputs = vlm_processor(
                    text=[text_input],
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors="pt",
                ).to("cuda:0")

                # Count input tokens
                n_tokens = inputs["input_ids"].shape[1]

                # Reset peak tracking
                torch.cuda.reset_peak_memory_stats()

                # Run inference
                with torch.no_grad():
                    output = vlm.generate(**inputs, max_new_tokens=100)

                # Measure peak
                peak_mb = torch.cuda.max_memory_allocated(0) / 1024**2
                alloc_after = torch.cuda.memory_allocated(0) / 1024**2
                activation_mb = peak_mb - alloc_before

                entry = {
                    "n_images": n_imgs,
                    "resolution": res,
                    "input_tokens": n_tokens,
                    "peak_memory_mb": round(peak_mb, 1),
                    "activation_memory_mb": round(activation_mb, 1),
                    "alloc_before_mb": round(alloc_before, 1),
                }
                results["activation_scaling"].append(entry)
                print(f"    tokens={n_tokens}  peak={peak_mb:.0f} MB  "
                      f"activation={activation_mb:.0f} MB")

            except torch.cuda.OutOfMemoryError:
                print(f"    *** OOM at {n_imgs} images @ {res}x{res} ***")
                results["activation_scaling"].append({
                    "n_images": n_imgs,
                    "resolution": res,
                    "status": "OOM",
                })
                clear_cache()
            except Exception as e:
                print(f"    *** Error: {e} ***")
                results["activation_scaling"].append({
                    "n_images": n_imgs,
                    "resolution": res,
                    "status": f"error: {str(e)}",
                })
                clear_cache()

    # ── Save results ─────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n{'=' * 70}")
    print(f"Results saved to {out_path}")

    # ── Print summary table ──────────────────────────────────────────────
    print(f"\n── Summary ──")
    print(f"  VLM weights: {results['memory_stages'][1]['allocated_mb'] - results['memory_stages'][0]['allocated_mb']:.0f} MB")
    vlm_mem = results['memory_stages'][1]['allocated_mb']
    llm_plus = results['memory_stages'][2]['allocated_mb']
    print(f"  LLM weights: {llm_plus - vlm_mem:.0f} MB")
    print(f"  Both models: {llm_plus:.0f} MB")
    print(f"  GPU free after both: {results['memory_stages'][2]['free_mb']:.0f} MB")

    print(f"\n  Activation memory scaling:")
    print(f"  {'Res':>6} | {'1 img':>8} | {'2 imgs':>8} | {'4 imgs':>8} | {'6 imgs':>8}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}")
    for res in resolutions:
        row = f"  {res:>6} |"
        for n in num_images_list:
            match = [e for e in results["activation_scaling"]
                     if e.get("n_images") == n and e.get("resolution") == res]
            if match and "activation_memory_mb" in match[0]:
                row += f" {match[0]['activation_memory_mb']:>6.0f}MB |"
            elif match and match[0].get("status") == "OOM":
                row += f"     OOM |"
            else:
                row += f"     ERR |"
        print(row)


if __name__ == "__main__":
    main()