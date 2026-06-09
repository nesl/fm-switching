"""
Quality Comparison: VLMs on Same Frames
=======================================
Run the same prompt + same frames through multiple VLMs, save outputs side by
side for direct human inspection. NO LLM stage — measures VLM scene
understanding only.

For each VLM (loaded one at a time to avoid memory pressure):
  1. Load VLM
  2. Run all selected frames with the same navigation prompt
  3. Record per-frame: output text, latency, token count
  4. Unload, free GPU memory
  5. Move to next VLM

Output JSON: per-frame results across all VLMs.
"""

import torch
import gc
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from PIL import Image

# ── SDPA compatibility shim for older Jetson torch ──────────────────────
import torch.nn.functional as _F
_orig_sdpa = _F.scaled_dot_product_attention
def _sdpa_compat(query, key, value, *args, **kwargs):
    enable_gqa = kwargs.pop("enable_gqa", False)
    if enable_gqa and key.shape[-3] != query.shape[-3]:
        n_rep = query.shape[-3] // key.shape[-3]
        key = key.repeat_interleave(n_rep, dim=-3)
        value = value.repeat_interleave(n_rep, dim=-3)
    return _orig_sdpa(query, key, value, *args, **kwargs)
_F.scaled_dot_product_attention = _sdpa_compat


# ── Model registry ──────────────────────────────────────────────────────
# (key, model_id, quantization, short_label)
# 6 cells: 3 model architectures × 2 quantizations (FP16 and INT4 / bnb-4bit).
# SmolVLMs have no pre-quantized INT4 repo on HF, so their INT4 cell uses
# runtime bnb-4bit on the FP16 weights (same eval, weights already cached).
DEFAULT_MODELS = [
    ("smolvlm_256m_fp16", "HuggingFaceTB/SmolVLM-256M-Instruct",     "fp16",         "SmolVLM-256M FP16"),
    ("smolvlm_256m_int4", "HuggingFaceTB/SmolVLM-256M-Instruct",     "bnb",          "SmolVLM-256M INT4 (runtime bnb)"),
    ("smolvlm_500m_fp16", "HuggingFaceTB/SmolVLM-500M-Instruct",     "fp16",         "SmolVLM-500M FP16"),
    ("smolvlm_500m_int4", "HuggingFaceTB/SmolVLM-500M-Instruct",     "bnb",          "SmolVLM-500M INT4 (runtime bnb)"),
    ("qwen_vl_3b_fp16",   "Qwen/Qwen2.5-VL-3B-Instruct",             "fp16",         "Qwen2.5-VL-3B FP16"),
    ("qwen_vl_3b_int4",   "unsloth/Qwen2.5-VL-3B-Instruct-bnb-4bit", "prequant-bnb", "Qwen2.5-VL-3B INT4 prequant"),
]

NAV_PROMPT = ("You are a robot navigator. Describe this scene: what is the path ahead, "
              "what obstacles are present, any signs or hazards, and what action should "
              "the robot take (go forward, turn left, turn right, slow down, stop)?")


def _build_load_kwargs(quantization):
    """quantization in {bnb, prequant-bnb, fp16}. For prequant-bnb-direct repos
    we skip BitsAndBytesConfig (weights are already 4-bit)."""
    load_kwargs = {"device_map": "auto", "torch_dtype": torch.float16}
    if quantization == "bnb":
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4",
        )
    return load_kwargs


def load_vlm(model_id, quantization, min_pixels=None, max_pixels=None):
    """Load a VLM. Returns (model, processor)."""
    load_kwargs = _build_load_kwargs(quantization)
    arch_hint = model_id.lower()
    proc_kwargs = {}
    if "qwen" in arch_hint and "vl" in arch_hint and (min_pixels or max_pixels):
        if min_pixels is not None:
            proc_kwargs["min_pixels"] = int(min_pixels)
        if max_pixels is not None:
            proc_kwargs["max_pixels"] = int(max_pixels)
    if "paligemma" in arch_hint:
        from transformers import PaliGemmaForConditionalGeneration, AutoProcessor
        model = PaliGemmaForConditionalGeneration.from_pretrained(model_id, **load_kwargs)
        proc = AutoProcessor.from_pretrained(model_id)
    elif "smolvlm" in arch_hint:
        from transformers import AutoModelForVision2Seq, AutoProcessor
        model = AutoModelForVision2Seq.from_pretrained(model_id, **load_kwargs)
        proc = AutoProcessor.from_pretrained(model_id)
    elif "qwen2.5-vl" in arch_hint or "qwen2_5_vl" in arch_hint:
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_id, **load_kwargs)
        proc = AutoProcessor.from_pretrained(model_id, **proc_kwargs)
    else:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        model = Qwen2VLForConditionalGeneration.from_pretrained(model_id, **load_kwargs)
        proc = AutoProcessor.from_pretrained(model_id, **proc_kwargs)
    return model, proc


def run_vlm(model, processor, image, model_id, prompt, max_tokens):
    """Run one VLM forward, return (text, latency_s, n_tokens)."""
    if "qwen" in model_id.lower():
        from qwen_vl_utils import process_vision_info
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ]}]
        text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text_input], images=image_inputs, videos=video_inputs,
                           padding=True, return_tensors="pt").to(model.device)
    elif "paligemma" in model_id.lower():
        inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)
    else:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ]}]
        inputs = processor.apply_chat_template(messages, return_tensors="pt",
                                                add_generation_prompt=True, tokenize=True).to(model.device)

    is_mapping = hasattr(inputs, "keys")
    # Capture the prompt length so we can slice the generation correctly.
    # apply_chat_template(tokenize=True) can return a bare tensor or a dict
    # depending on processor version; handle both.
    if is_mapping and "input_ids" in inputs:
        prompt_len = inputs["input_ids"].shape[1]
    else:
        prompt_len = inputs.shape[-1]
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        if is_mapping:
            output_ids = model.generate(**inputs, max_new_tokens=max_tokens)
        else:
            output_ids = model.generate(input_ids=inputs, max_new_tokens=max_tokens)
    torch.cuda.synchronize()
    latency = time.perf_counter() - t0

    gen_ids = output_ids[:, prompt_len:]
    if hasattr(processor, "decode"):
        text = processor.decode(gen_ids[0], skip_special_tokens=True)
    else:
        text = processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
    return text.strip(), latency, gen_ids.shape[1]


def main():
    parser = argparse.ArgumentParser(description="VLM quality comparison on same frames")
    parser.add_argument("--frames", required=True, help="Directory of input images")
    parser.add_argument("--max-frames", type=int, default=10, help="Number of frames per cell (default 10)")
    parser.add_argument("--max-tokens", type=int, default=100,
                        help="Per-VLM generation cap (default 100; need enough for nav decision)")
    parser.add_argument("--max-pixels", type=int, default=200704,
                        help="Cap on visual tokens for Qwen-VL processors (default 448*448=200704)")
    parser.add_argument("--prompt", default=NAV_PROMPT, help="Prompt text (default: navigation prompt)")
    parser.add_argument("--delete-cache-after", action="store_true", default=False,
                        help="Delete each VLM's HF cache after running it (saves disk on Jetson)")
    parser.add_argument("--only-models", default=None,
                        help="Comma-separated subset of model keys to run (e.g. 'smolvlm_256m,smolvlm_500m'). "
                             "Default: run all DEFAULT_MODELS.")
    parser.add_argument("--merge-into", default=None,
                        help="Path to existing quality_comparison.json — merge new results into it "
                             "instead of writing a fresh file.")
    parser.add_argument("--memory-limit", type=float, default=None,
                        help="Cap GPU memory in GB (simulates a smaller device). Default: no cap.")
    parser.add_argument("--output", default="results/quality_comparison.json")
    args = parser.parse_args()

    if args.memory_limit and torch.cuda.is_available():
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        fraction = min(args.memory_limit / total_gb, 1.0)
        torch.cuda.set_per_process_memory_fraction(fraction, 0)
        print(f"  GPU memory cap: {args.memory_limit:.1f} GB ({fraction:.1%} of {total_gb:.1f} GB)")

    # Load frame paths
    frame_dir = Path(args.frames)
    image_paths = sorted([p for p in frame_dir.iterdir()
                          if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    if not image_paths:
        print(f"No images in {frame_dir}")
        return
    image_paths = image_paths[:args.max_frames]
    print(f"Using {len(image_paths)} frames from {frame_dir}")

    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("=" * 60)
    print("EXP: VLM Quality Comparison")
    print(f"  Device: {device_name}")
    print(f"  Frames: {len(image_paths)}")
    print(f"  Max tokens: {args.max_tokens}")
    print(f"  Models: {[m[3] for m in DEFAULT_MODELS]}")
    print(f"  Prompt: {args.prompt[:80]}...")
    print("=" * 60)

    # Filter models if requested
    selected_models = DEFAULT_MODELS
    if args.only_models:
        wanted = {k.strip() for k in args.only_models.split(",") if k.strip()}
        selected_models = [m for m in DEFAULT_MODELS if m[0] in wanted]
        print(f"  Running subset: {[m[3] for m in selected_models]}")

    # Initialize per-frame result dicts (preserving prior data if --merge-into)
    if args.merge_into and Path(args.merge_into).exists():
        prior = json.loads(Path(args.merge_into).read_text())
        per_frame = {r["frame"]: dict(r) for r in prior.get("results", [])}
        # Make sure every selected frame has an entry
        for p in image_paths:
            per_frame.setdefault(p.name, {"frame": p.name})
        print(f"  Merging into {args.merge_into}: {len(prior.get('results', []))} prior frame entries")
    else:
        per_frame = {p.name: {"frame": p.name} for p in image_paths}

    metadata = {
        "device": device_name,
        "frames": [p.name for p in image_paths],
        "prompt": args.prompt,
        "max_tokens": args.max_tokens,
        "max_pixels": args.max_pixels,
        "models": [{"key": k, "id": mid, "quantization": q, "label": label}
                   for (k, mid, q, label) in DEFAULT_MODELS],
        "timestamp": datetime.now().isoformat(),
    }

    # Run each selected VLM in turn. Track which model_ids appear in *later*
    # cells so we only delete a cache after its final cell.
    later_uses = {}
    for idx, (k, mid, q, lbl) in enumerate(selected_models):
        for j in range(idx + 1, len(selected_models)):
            if selected_models[j][1] == mid:
                later_uses.setdefault(idx, True)
                break

    for cell_idx, (key, model_id, quantization, label) in enumerate(selected_models):
        print(f"\n{'─' * 60}")
        print(f"Loading {label}: {model_id}")
        print(f"{'─' * 60}")
        gc.collect()
        torch.cuda.empty_cache()
        time.sleep(1)
        try:
            t_load = time.perf_counter()
            vlm, vlm_proc = load_vlm(model_id, quantization,
                                      max_pixels=args.max_pixels if "qwen" in model_id.lower() else None)
            torch.cuda.synchronize()
            load_s = time.perf_counter() - t_load
            mem_mb = torch.cuda.memory_allocated(0) / 1024**2
            print(f"  Loaded in {load_s:.1f}s, {mem_mb:.0f} MB GPU")
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            for p in image_paths:
                per_frame[p.name][key] = {"error": f"load failed: {e}"}
            continue

        # Run each frame
        for i, path in enumerate(image_paths, 1):
            try:
                img = Image.open(path).convert("RGB")
                text, lat, n_tok = run_vlm(vlm, vlm_proc, img, model_id, args.prompt, args.max_tokens)
                per_frame[path.name][key] = {
                    "output": text,
                    "latency_s": round(lat, 3),
                    "tokens": int(n_tok),
                }
                print(f"  [{i:>2}/{len(image_paths)}] {path.name}: {lat:.2f}s, {n_tok}t -- {text[:60]!r}")
            except Exception as e:
                print(f"  [{i:>2}/{len(image_paths)}] {path.name}: ERROR {e}")
                per_frame[path.name][key] = {"error": str(e)}

        # Save partial results after each VLM (so a crash doesn't lose data)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "metadata": metadata,
            "results": list(per_frame.values()),
        }, indent=2))
        print(f"  Partial results saved to {out}")

        # Unload
        del vlm, vlm_proc
        gc.collect()
        torch.cuda.empty_cache()
        print(f"  Unloaded {label}")

        if args.delete_cache_after and not later_uses.get(cell_idx):
            import shutil
            cache_root = Path.home() / ".cache" / "huggingface" / "hub"
            cache_dir_name = "models--" + model_id.replace("/", "--")
            cp = cache_root / cache_dir_name
            if cp.exists():
                size_gb = sum(f.stat().st_size for f in cp.rglob("*") if f.is_file()) / 1024**3
                shutil.rmtree(cp, ignore_errors=True)
                print(f"  Cache deleted: {cache_dir_name} ({size_gb:.2f} GB freed)")
        elif args.delete_cache_after:
            print(f"  Skipping cache delete — later cell reuses {model_id}")

    # Final save
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "metadata": metadata,
        "results": list(per_frame.values()),
    }, indent=2))
    print(f"\nFinal results saved to {out}")

    # Quick summary
    print(f"\n{'=' * 60}")
    print("SUMMARY (avg latency per VLM)")
    print(f"{'=' * 60}")
    for key, _, _, label in DEFAULT_MODELS:
        lats = [r[key].get("latency_s") for r in per_frame.values()
                if key in r and "latency_s" in r[key]]
        if lats:
            print(f"  {label}: avg {sum(lats)/len(lats):.2f}s ({len(lats)} ok)")
        else:
            print(f"  {label}: no successful runs")


if __name__ == "__main__":
    main()
