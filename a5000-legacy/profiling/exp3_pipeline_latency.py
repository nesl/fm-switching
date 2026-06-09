"""
Experiment 3: End-to-End Pipeline Latency (VLM → LLM)
======================================================
Measures the full planning cycle latency:
  1. VLM processes camera image(s) → scene description
  2. LLM takes scene description + planning prompt → waypoints/decision

Varies:
  - Number of input images (1, 2, 4)
  - Resolution (224, 448)
  - LLM output length (short plan vs detailed plan)

This validates the "1-2 Hz at best" claim.

Hardware: NVIDIA A6000 (48GB)
Usage: python exp3_pipeline_latency.py [--trials 5]
"""

import torch
import gc
import time
import json
import argparse
import statistics
import numpy as np
from datetime import datetime
from pathlib import Path
from PIL import Image


def clear_cache():
    gc.collect()
    torch.cuda.empty_cache()


def make_driving_image(resolution):
    """Create a synthetic driving-scene-like image."""
    arr = np.random.randint(0, 255, (resolution, resolution, 3), dtype=np.uint8)
    # Add a rough horizon line to make it vaguely scene-like
    arr[resolution // 2 - 5 : resolution // 2 + 5, :, :] = [128, 128, 128]
    return Image.fromarray(arr)


PLANNING_PROMPT = """You are an autonomous vehicle planner. Based on the scene description below, provide:
1. The recommended action (go straight, turn left, turn right, slow down, stop)
2. Target speed in km/h
3. Any hazards to watch for

Scene description: {scene}

Respond concisely with action, speed, and hazards."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vlm", default="Qwen/Qwen2.5-VL-7B-Instruct")
    parser.add_argument("--llm", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--quantize", action="store_true", default=True)
    parser.add_argument("--no-quantize", dest="quantize", action="store_false")
    parser.add_argument("--output", default="exp3_results.json")
    args = parser.parse_args()

    print("=" * 70)
    print("EXPERIMENT 3: End-to-End Pipeline Latency (VLM → LLM)")
    print(f"  VLM: {args.vlm}")
    print(f"  LLM: {args.llm}")
    print(f"  Trials per config: {args.trials}")
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    # ── Load both models ─────────────────────────────────────────────────
    load_kwargs = {"device_map": "cuda:0", "torch_dtype": torch.float16}
    if args.quantize:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )

    print("\n── Loading VLM ──")
    from transformers import AutoModelForVision2Seq, AutoProcessor
    vlm = AutoModelForVision2Seq.from_pretrained(args.vlm, **load_kwargs)
    vlm_processor = AutoProcessor.from_pretrained(args.vlm)
    print("  VLM loaded.")

    print("\n── Loading LLM ──")
    from transformers import AutoModelForCausalLM, AutoTokenizer
    llm = AutoModelForCausalLM.from_pretrained(args.llm, **load_kwargs)
    llm_tokenizer = AutoTokenizer.from_pretrained(args.llm)
    if llm_tokenizer.pad_token is None:
        llm_tokenizer.pad_token = llm_tokenizer.eos_token
    print("  LLM loaded.")

    alloc_mb = torch.cuda.memory_allocated(0) / 1024**2
    print(f"  Both models loaded: {alloc_mb:.0f} MB allocated")

    # ── Run pipeline experiments ─────────────────────────────────────────
    results = {
        "metadata": {
            "vlm": args.vlm,
            "llm": args.llm,
            "trials": args.trials,
            "quantization": "4-bit" if args.quantize else "none",
            "gpu": torch.cuda.get_device_name(0),
            "timestamp": datetime.now().isoformat(),
        },
        "configs": [],
    }

    configs = [
        {"n_images": 1, "resolution": 224},
        {"n_images": 1, "resolution": 448},
        {"n_images": 2, "resolution": 224},
        {"n_images": 2, "resolution": 448},
        {"n_images": 4, "resolution": 224},
    ]

    for cfg in configs:
        n_imgs = cfg["n_images"]
        res = cfg["resolution"]
        print(f"\n── Config: {n_imgs} image(s) @ {res}x{res} ──")

        config_results = {
            "n_images": n_imgs,
            "resolution": res,
            "trials": [],
        }

        for trial in range(1, args.trials + 1):
            clear_cache()
            images = [make_driving_image(res) for _ in range(n_imgs)]

            # ── Step 1: VLM inference ────────────────────────────────────
            image_content = [{"type": "image", "image": img} for img in images]
            image_content.append({
                "type": "text",
                "text": "Describe this driving scene briefly. What objects, road conditions, and potential hazards do you see?"
            })
            messages = [{"role": "user", "content": image_content}]

            from qwen_vl_utils import process_vision_info
            text_input = vlm_processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            vlm_inputs = vlm_processor(
                text=[text_input],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to("cuda:0")

            vlm_input_tokens = vlm_inputs["input_ids"].shape[1]

            torch.cuda.synchronize()
            t_vlm_start = time.perf_counter()
            with torch.no_grad():
                vlm_output_ids = vlm.generate(**vlm_inputs, max_new_tokens=150)
            torch.cuda.synchronize()
            t_vlm_end = time.perf_counter()
            vlm_latency = t_vlm_end - t_vlm_start

            # Decode VLM output
            generated_ids = vlm_output_ids[:, vlm_inputs["input_ids"].shape[1]:]
            scene_description = vlm_processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
            vlm_output_tokens = generated_ids.shape[1]

            # ── Step 2: LLM inference ────────────────────────────────────
            planning_prompt = PLANNING_PROMPT.format(scene=scene_description)
            llm_inputs = llm_tokenizer(
                planning_prompt, return_tensors="pt", padding=True
            ).to("cuda:0")
            llm_input_tokens = llm_inputs["input_ids"].shape[1]

            torch.cuda.synchronize()
            t_llm_start = time.perf_counter()
            with torch.no_grad():
                llm_output_ids = llm.generate(
                    **llm_inputs, max_new_tokens=100,
                    pad_token_id=llm_tokenizer.pad_token_id,
                )
            torch.cuda.synchronize()
            t_llm_end = time.perf_counter()
            llm_latency = t_llm_end - t_llm_start

            llm_output_tokens = llm_output_ids.shape[1] - llm_input_tokens
            total_latency = vlm_latency + llm_latency
            max_hz = 1.0 / total_latency if total_latency > 0 else float('inf')

            trial_result = {
                "trial": trial,
                "vlm_latency_s": round(vlm_latency, 4),
                "vlm_input_tokens": vlm_input_tokens,
                "vlm_output_tokens": vlm_output_tokens,
                "llm_latency_s": round(llm_latency, 4),
                "llm_input_tokens": llm_input_tokens,
                "llm_output_tokens": llm_output_tokens,
                "total_latency_s": round(total_latency, 4),
                "max_planning_hz": round(max_hz, 2),
            }
            config_results["trials"].append(trial_result)
            print(f"  Trial {trial}: VLM={vlm_latency:.3f}s  LLM={llm_latency:.3f}s  "
                  f"total={total_latency:.3f}s  ({max_hz:.1f} Hz)")

        # Compute summary for this config
        vlm_lats = [t["vlm_latency_s"] for t in config_results["trials"]]
        llm_lats = [t["llm_latency_s"] for t in config_results["trials"]]
        total_lats = [t["total_latency_s"] for t in config_results["trials"]]

        config_results["summary"] = {
            "vlm_mean_s": round(statistics.mean(vlm_lats), 4),
            "llm_mean_s": round(statistics.mean(llm_lats), 4),
            "total_mean_s": round(statistics.mean(total_lats), 4),
            "total_std_s": round(statistics.stdev(total_lats), 4) if len(total_lats) > 1 else 0,
            "mean_planning_hz": round(1.0 / statistics.mean(total_lats), 2),
        }
        results["configs"].append(config_results)

    # ── Save results ─────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.write_text(json.dumps(results, indent=2))

    # ── Print summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"Results saved to {out_path}")
    print(f"\n── Summary Table ──")
    print(f"  {'Config':<20} | {'VLM (s)':>8} | {'LLM (s)':>8} | {'Total (s)':>10} | {'Hz':>6}")
    print(f"  {'-'*20}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}-+-{'-'*6}")
    for cfg in results["configs"]:
        label = f"{cfg['n_images']}img @ {cfg['resolution']}"
        s = cfg["summary"]
        print(f"  {label:<20} | {s['vlm_mean_s']:>8.3f} | {s['llm_mean_s']:>8.3f} | "
              f"{s['total_mean_s']:>10.3f} | {s['mean_planning_hz']:>5.1f}")

    print(f"\n  Conclusion: FM planning pipeline operates at "
          f"{min(c['summary']['mean_planning_hz'] for c in results['configs']):.1f} - "
          f"{max(c['summary']['mean_planning_hz'] for c in results['configs']):.1f} Hz")


if __name__ == "__main__":
    main()