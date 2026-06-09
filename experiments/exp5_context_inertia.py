"""
Experiment 5: Context Inertia on Jetson
========================================
Measures how accumulated LLM context affects inference cost.
Tests four context modes:
  1. stateless     -- no history, only current VLM scene description
  2. window-3      -- last 3 VLM descriptions + current
  3. window-10     -- last 10 VLM descriptions + current
  4. full          -- ALL prior VLM descriptions + LLM responses (grows every cycle)

For each cycle we measure VLM latency, LLM prefill (TTFT via 1-token call),
LLM total latency (60-token call), and peak GPU memory. The growth in prefill
time across cycles in mode 4 is the *context inertia* curve.
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


# ── Pre-quant repos / loading helpers (mirrors exp2) ────────────────────
PREQUANT_BNB_MAP = {
    "Qwen/Qwen2.5-VL-3B-Instruct":         "unsloth/Qwen2.5-VL-3B-Instruct-bnb-4bit",
    "Qwen/Qwen2.5-3B-Instruct":            "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",
    "Qwen/Qwen2.5-1.5B-Instruct":          "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct": "unsloth/SmolLM2-1.7B-Instruct-bnb-4bit",
}


def resolve_model_id(model_id, quantization):
    if model_id.endswith("-bnb-4bit") or model_id in PREQUANT_BNB_MAP.values():
        return model_id, True
    if quantization == "prequant-bnb" and model_id in PREQUANT_BNB_MAP:
        return PREQUANT_BNB_MAP[model_id], True
    return model_id, False


def _build_load_kwargs(quantization, skip_quant):
    load_kwargs = {"device_map": "auto", "torch_dtype": torch.float16}
    if quantization in ("bnb", "prequant-bnb") and not skip_quant:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4",
        )
    return load_kwargs


def load_vlm(model_id, quantization, max_pixels=None):
    effective_id, skip_quant = resolve_model_id(model_id, quantization)
    load_kwargs = _build_load_kwargs(quantization, skip_quant)
    proc_kwargs = {}
    arch_hint = effective_id.lower()
    if "qwen" in arch_hint and "vl" in arch_hint and max_pixels:
        proc_kwargs["max_pixels"] = int(max_pixels)
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
        proc = AutoProcessor.from_pretrained(effective_id, **proc_kwargs)
    else:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        model = Qwen2VLForConditionalGeneration.from_pretrained(effective_id, **load_kwargs)
        proc = AutoProcessor.from_pretrained(effective_id, **proc_kwargs)
    return model, proc


def load_llm(model_id, quantization):
    effective_id, skip_quant = resolve_model_id(model_id, quantization)
    load_kwargs = _build_load_kwargs(quantization, skip_quant)
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model = AutoModelForCausalLM.from_pretrained(effective_id, **load_kwargs)
    tok = AutoTokenizer.from_pretrained(effective_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return model, tok


# ── VLM inference (Qwen-VL focused; same prompt every cycle) ────────────
VLM_PROMPT = ("Briefly describe this scene for an inspection robot. "
              "What do you see — path, obstacles, hazards, signs?")


def run_vlm(model, processor, image, model_id, max_tokens=60):
    if "qwen" in model_id.lower():
        from qwen_vl_utils import process_vision_info
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": VLM_PROMPT},
        ]}]
        text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text_input], images=image_inputs, videos=video_inputs,
                           padding=True, return_tensors="pt").to(model.device)
    elif "paligemma" in model_id.lower():
        inputs = processor(text=VLM_PROMPT, images=image, return_tensors="pt").to(model.device)
    else:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": VLM_PROMPT},
        ]}]
        inputs = processor.apply_chat_template(messages, return_tensors="pt",
                                                add_generation_prompt=True, tokenize=True).to(model.device)

    is_mapping = hasattr(inputs, "keys")
    if is_mapping and "input_ids" in inputs:
        prompt_len = inputs["input_ids"].shape[1]
    else:
        prompt_len = inputs.shape[-1]

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        if is_mapping:
            out = model.generate(**inputs, max_new_tokens=max_tokens)
        else:
            out = model.generate(input_ids=inputs, max_new_tokens=max_tokens)
    torch.cuda.synchronize()
    latency = time.perf_counter() - t0

    gen_ids = out[:, prompt_len:]
    if hasattr(processor, "decode"):
        text = processor.decode(gen_ids[0], skip_special_tokens=True)
    else:
        text = processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
    return text.strip(), latency


# ── LLM (two-call: TTFT for prefill, full for generation) ───────────────
SYSTEM_PROMPT = (
    "You are an inspection robot controller. You receive scene descriptions "
    "from your camera and maintain awareness of your inspection progress. "
    "Based on the current and past observations, decide your next action and "
    "note any hazards or anomalies.\n"
    "Actions: move_forward, turn_left, turn_right, stop, flag_hazard\n"
    "Respond concisely as: Observation: [...], Action: [...], Status: [...]"
)


def build_prompt(mode, cycle_idx, vlm_descriptions, llm_responses):
    """mode in {stateless, window-3, window-10, full}.
    cycle_idx is 0-indexed; vlm_descriptions has length >= cycle_idx+1;
    llm_responses has length cycle_idx (responses for prior cycles)."""
    current = vlm_descriptions[cycle_idx]

    if mode == "stateless":
        history = ""
    elif mode in ("window-3", "window-10"):
        win = 3 if mode == "window-3" else 10
        start = max(0, cycle_idx - win)
        lines = [f"- Cycle {i}: \"{vlm_descriptions[i]}\"" for i in range(start, cycle_idx)]
        history = "Previous observations:\n" + "\n".join(lines) + "\n\n" if lines else ""
    elif mode == "full":
        if cycle_idx == 0:
            history = ""
        else:
            parts = []
            for i in range(cycle_idx):
                parts.append(f"Cycle {i} scene: \"{vlm_descriptions[i]}\"")
                parts.append(f"Cycle {i} response: {llm_responses[i]}")
            history = "Previous observations and decisions:\n" + "\n".join(parts) + "\n\n"
    else:
        raise ValueError(f"unknown mode: {mode}")

    return (f"{SYSTEM_PROMPT}\n\n"
            f"{history}"
            f"Current scene (Cycle {cycle_idx}): \"{current}\"\n\n"
            f"Your response:")


def run_llm_two_call(model, tokenizer, prompt, max_tokens=60):
    """Two calls: max_new_tokens=1 for TTFT (prefill), then full for generation.
    Decode time = total - prefill. Returns dict of metrics + response text."""
    inputs = tokenizer(prompt, return_tensors="pt", padding=True).to(model.device)
    prompt_len = inputs["input_ids"].shape[1]

    torch.cuda.reset_peak_memory_stats()

    # Call 1: TTFT (prefill)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        _ = model.generate(**inputs, max_new_tokens=1, do_sample=False,
                           pad_token_id=tokenizer.pad_token_id)
    torch.cuda.synchronize()
    prefill_s = time.perf_counter() - t0

    # Call 2: full generation
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                             pad_token_id=tokenizer.pad_token_id)
    torch.cuda.synchronize()
    total_s = time.perf_counter() - t0
    peak_mb = torch.cuda.max_memory_allocated(0) / 1024**2

    gen_ids = out[:, prompt_len:]
    response = tokenizer.decode(gen_ids[0], skip_special_tokens=True).strip()
    gen_tokens = int(gen_ids.shape[1])

    return {
        "response": response,
        "prefill_ms": round(prefill_s * 1000, 1),
        "generation_ms": round(max(total_s - prefill_s, 0.0) * 1000, 1),
        "total_ms": round(total_s * 1000, 1),
        "prompt_tokens": int(prompt_len),
        "gen_tokens": gen_tokens,
        "peak_mb": round(peak_mb, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Exp 5: context inertia")
    parser.add_argument("--vlm", required=True)
    parser.add_argument("--llm", required=True)
    parser.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"], default="fp16")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--num-cycles", type=int, default=30)
    parser.add_argument("--max-pixels", type=int, default=200704)
    parser.add_argument("--vlm-max-tokens", type=int, default=60)
    parser.add_argument("--llm-max-tokens", type=int, default=60)
    parser.add_argument("--memory-limit", type=float, default=None,
                        help="Cap GPU memory in GB (simulates a smaller device).")
    parser.add_argument("--output", default="results/exp5.json")
    args = parser.parse_args()

    if args.memory_limit and torch.cuda.is_available():
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        fraction = min(args.memory_limit / total_gb, 1.0)
        torch.cuda.set_per_process_memory_fraction(fraction, 0)
        print(f"  GPU memory cap: {args.memory_limit:.1f} GB ({fraction:.1%} of {total_gb:.1f} GB)")

    frame_dir = Path(args.frames)
    image_paths = sorted([p for p in frame_dir.iterdir()
                          if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    image_paths = image_paths[:args.num_cycles]
    if not image_paths:
        print(f"No images found in {frame_dir}")
        return

    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("=" * 60)
    print(f"EXP 5: Context Inertia ({args.quantization})")
    print(f"  Device: {device_name}")
    print(f"  VLM: {args.vlm}")
    print(f"  LLM: {args.llm}")
    print(f"  Cycles: {len(image_paths)}")
    print("=" * 60)

    # Load both models
    print("\nLoading VLM...")
    vlm, vlm_proc = load_vlm(args.vlm, args.quantization, args.max_pixels)
    mem_after_vlm = torch.cuda.memory_allocated(0) / 1024**2
    print(f"  VLM loaded: {mem_after_vlm:.0f} MB")

    print("Loading LLM...")
    llm, llm_tok = load_llm(args.llm, args.quantization)
    mem_after_both = torch.cuda.memory_allocated(0) / 1024**2
    print(f"  Both loaded: {mem_after_both:.0f} MB")

    metadata = {
        "device": device_name,
        "vlm": args.vlm, "llm": args.llm,
        "quantization": args.quantization,
        "memory_limit_gb": args.memory_limit,
        "max_pixels": args.max_pixels,
        "vlm_max_tokens": args.vlm_max_tokens,
        "llm_max_tokens": args.llm_max_tokens,
        "num_cycles_requested": args.num_cycles,
        "mem_after_vlm_mb": round(mem_after_vlm, 1),
        "mem_after_both_mb": round(mem_after_both, 1),
        "timestamp_start": datetime.now().isoformat(),
    }

    def _save(vlm_records, mode_results, actual_cycles):
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "metadata": {**metadata, "num_cycles_actual": actual_cycles,
                         "timestamp_last_save": datetime.now().isoformat()},
            "vlm_records": vlm_records,
            "modes": mode_results,
        }, indent=2))

    # Phase 1: VLM pass — compute scene descriptions for all cycles
    print(f"\n{'─' * 50}")
    print(f"Phase 1: VLM pass over {len(image_paths)} frames")
    print(f"{'─' * 50}")
    vlm_records = []
    for i, path in enumerate(image_paths):
        img = Image.open(path).convert("RGB")
        torch.cuda.reset_peak_memory_stats()
        try:
            text, lat = run_vlm(vlm, vlm_proc, img, args.vlm, args.vlm_max_tokens)
        except torch.cuda.OutOfMemoryError as e:
            print(f"  Cycle {i}: VLM OOM - {str(e)[:80]}")
            vlm_records.append({"cycle": i, "frame": path.name, "error": "vlm_oom"})
            break
        peak_mb = torch.cuda.max_memory_allocated(0) / 1024**2
        vlm_records.append({
            "cycle": i, "frame": path.name,
            "vlm_latency_ms": round(lat * 1000, 1),
            "vlm_peak_mb": round(peak_mb, 1),
            "description": text,
        })
        print(f"  [{i+1:>2}/{len(image_paths)}] {path.name}: {lat:.2f}s -- {text[:60]!r}")
        _save(vlm_records, {}, len([r for r in vlm_records if "description" in r]))

    vlm_descriptions = [r["description"] for r in vlm_records if "description" in r]
    actual_cycles = len(vlm_descriptions)
    print(f"\nVLM phase complete: {actual_cycles} usable scene descriptions")

    # Phase 2: LLM with each context mode
    modes = ["stateless", "window-3", "window-10", "full"]
    mode_results = {}

    for mode in modes:
        print(f"\n{'─' * 50}")
        print(f"Phase 2 [{mode}]: {actual_cycles} LLM cycles")
        print(f"{'─' * 50}")
        cycles_data = []
        llm_responses = []
        oom_info = None

        for i in range(actual_cycles):
            prompt = build_prompt(mode, i, vlm_descriptions, llm_responses)
            try:
                rec = run_llm_two_call(llm, llm_tok, prompt, max_tokens=args.llm_max_tokens)
            except torch.cuda.OutOfMemoryError as e:
                msg = str(e)[:200]
                print(f"  Cycle {i}: LLM OOM ({mode}) - {msg[:80]}")
                oom_info = {"cycle": i, "stage": "llm", "error": msg,
                            "prompt_tokens_attempted": int(llm_tok(prompt, return_tensors='pt')['input_ids'].shape[1])}
                gc.collect()
                torch.cuda.empty_cache()
                break
            cycles_data.append({
                "cycle": i,
                "vlm_latency_ms": vlm_records[i].get("vlm_latency_ms"),
                "vlm_peak_mb": vlm_records[i].get("vlm_peak_mb"),
                **rec,
                "kv_cache_tokens": rec["prompt_tokens"] + rec["gen_tokens"],
                "gpu_memory_mb_after": round(torch.cuda.memory_allocated(0) / 1024**2, 1),
            })
            llm_responses.append(rec["response"])

            if (i + 1) % 5 == 0 or i == 0 or i == actual_cycles - 1:
                print(f"  [{i+1:>2}/{actual_cycles}] tokens={rec['prompt_tokens']:>4} "
                      f"prefill={rec['prefill_ms']:>7.1f}ms gen={rec['generation_ms']:>6.1f}ms "
                      f"peak={rec['peak_mb']:>7.1f}MB")

        mode_results[mode] = {
            "cycles_completed": len(cycles_data),
            "cycles": cycles_data,
            "oom_info": oom_info,
        }
        _save(vlm_records, mode_results, actual_cycles)

    # Summary
    print(f"\n{'=' * 78}")
    print("SUMMARY")
    print(f"{'=' * 78}")
    print(f"{'Mode':<12} {'avg tokens':>11} {'prefill@1':>11} "
          f"{'prefill@N':>11} {'growth':>8} {'peak mem':>10}")
    print("─" * 78)
    for mode in modes:
        d = mode_results[mode]
        if not d["cycles"]:
            print(f"{mode:<12}  no completed cycles")
            continue
        c = d["cycles"]
        first_pref = c[0]["prefill_ms"]
        last_pref = c[-1]["prefill_ms"]
        growth = ((last_pref - first_pref) / first_pref * 100) if first_pref > 0 else 0
        avg_tokens = sum(x["prompt_tokens"] for x in c) / len(c)
        peak = max(x["peak_mb"] for x in c)
        suffix = f" OOM@cycle {d['oom_info']['cycle']}" if d.get("oom_info") else ""
        print(f"{mode:<12} {avg_tokens:>11.0f} {first_pref:>10.1f}ms {last_pref:>10.1f}ms "
              f"{growth:>7.1f}% {peak:>9.1f}MB{suffix}")
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
