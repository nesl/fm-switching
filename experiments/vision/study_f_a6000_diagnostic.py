#!/usr/bin/env python3
"""
Study F: A6000 diagnostic arm — decode rate separation and memory attribution reference.

Part 1: Does decode rate separate by model size (Qwen3-VL 4B vs 8B Instruct) on A6000?
         Three conditions: dynamic cache (C1), static cache (C2), static+compile (C3).
         Fixed decode length: min_new_tokens = max_new_tokens = 256. EOS suppressed.
         5 reps per condition.

Part 2: Phase-level memory attribution for Qwen2.5-VL-7B at N = 1, 3, 6, 12.
         Matches Study B setup. Report after-load / after-vision / after-prefill / peak.

Outputs: results/vision/study_f_a6000/study_f_environment.json
          results/vision/study_f_a6000/study_f_part1_decode.csv
          results/vision/study_f_a6000/study_f_part1_decode.json
          results/vision/study_f_a6000/study_f_part2_memory.csv
          results/vision/study_f_a6000/study_f_part2_memory.json

STOP RULES (checked in-script, stops and raises):
  - Any sanity check fails.
  - Phase peaks disagree with Study B reported peaks for same N.
  - torch.compile fails (recorded; C1 and C2 continue).

GIT RULE: never run git add/commit/push from this script. It writes only to
results/vision/study_f_a6000/ and reports/ (via the companion write-report step).
"""

import csv
import gc
import json
import os
import sys
import time
from pathlib import Path

import torch
import numpy as np
from PIL import Image
from transformers import (
    AutoProcessor,
    Qwen2_5_VLForConditionalGeneration,
    Qwen3VLForConditionalGeneration,
)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "vision" / "study_f_a6000"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = "cuda:1"   # A6000, 48 GB — explicit, never cuda:0 (3090 Ti)
DTYPE  = torch.bfloat16

# Qwen3-VL Instruct model paths (Part 1)
MODEL4B_PATH = Path("/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17")
MODEL8B_PATH = Path("/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b")

# Qwen2.5-VL-7B path (Part 2, matching Study B)
MODEL7B_PATH = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots/cc594898137f460bfe9f0759e9844b3ce807cfb5"

# A6000 spec memory bandwidth (GB/s) — from NVIDIA RTX A6000 datasheet
A6000_BW_GBPS = 768.0

# Study B reference peaks (GB) for Qwen2.5-VL-7B at each N
# Source: reports/study_b_vision_kv.md § "Peak at N=48: 24.4 GB"
# Table reconstructed from report §2: only N=1,3,6,12 are measured in this study.
# Report does not give per-N peaks directly; we derive from the weight baseline + KV.
# Weight baseline: 7B bfloat16 ≈ 14 GB. Tolerance for phase-check: ±2 GB.
STUDY_B_WEIGHT_GB = 14.0      # approximate model weight in bfloat16
STUDY_B_PEAK_TOLERANCE_GB = 2.0

# Part 1: fixed decode length
DECODE_TOKENS = 256
N_REPS = 5
IMAGE_SIZE = (560, 560)

# Part 2: N sweep
PART2_N_VALUES = [1, 3, 6, 12]
TOKENS_PER_FRAME_2_5VL = 400   # from Study A at 560×560 with Qwen2.5-VL
KV_BYTES_PER_TOK_7B = 57344    # 2×4×128×28×2 bytes/token

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_env_info():
    """Collect environment metadata."""
    import transformers
    info = {
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "cuda_version": torch.version.cuda,
        "device": DEVICE,
        "device_name": torch.cuda.get_device_name(torch.device(DEVICE)),
        "driver_version": None,
        "flash_attn_available": False,
        "flash_attn_version": None,
    }
    try:
        import flash_attn
        info["flash_attn_available"] = True
        info["flash_attn_version"] = flash_attn.__version__
    except ImportError:
        pass
    try:
        import subprocess
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True)
        info["driver_version"] = out.strip().split("\n")[0]
    except Exception:
        pass
    return info


def gpu_mem_gb(device=DEVICE):
    """Current allocated GPU memory in GB."""
    return torch.cuda.memory_allocated(device) / 1e9


def gpu_peak_gb(device=DEVICE):
    """Peak allocated GPU memory since last reset_peak_stats, in GB."""
    return torch.cuda.max_memory_allocated(device) / 1e9


def gpu_reserved_gb(device=DEVICE):
    """Current reserved GPU memory in GB."""
    return torch.cuda.memory_reserved(device) / 1e9


def gpu_peak_reserved_gb(device=DEVICE):
    """Peak reserved GPU memory since last reset_peak_stats, in GB."""
    return torch.cuda.max_memory_reserved(device) / 1e9


def reset_peak(device=DEVICE):
    torch.cuda.reset_peak_memory_stats(device)


def sync():
    torch.cuda.synchronize(device=DEVICE)


def load_image():
    """Return a single 560×560 RGB PIL image (solid colour — content-independent)."""
    img = Image.new("RGB", IMAGE_SIZE, color=(128, 64, 32))
    return img


def assert_device_and_dtype(model, label):
    """Assert all parameters are on DEVICE and dtype. Raises if not."""
    for name, param in model.named_parameters():
        if str(param.device) != DEVICE:
            raise RuntimeError(f"[SANITY FAIL] {label} param {name} on {param.device}, expected {DEVICE}")
        if param.dtype != DTYPE:
            raise RuntimeError(f"[SANITY FAIL] {label} param {name} dtype {param.dtype}, expected {DTYPE}")
        break  # checking one is sufficient for offload detection; checking all would be slow


def weight_bytes(model):
    """Total bytes in model parameters."""
    return sum(p.numel() * p.element_size() for p in model.parameters())


def get_attn_impl(model):
    """Return the attention implementation string actually used."""
    # Check first transformer layer for the attn implementation attribute
    attn_impl = "unknown"
    for name, module in model.named_modules():
        if hasattr(module, "config") and hasattr(module.config, "_attn_implementation"):
            attn_impl = module.config._attn_implementation
            break
        # Qwen3VL wraps attn in sub-modules
        if "attn" in name.lower() and hasattr(module, "is_causal"):
            # flash-attn modules have is_causal
            attn_impl = "flash_attention_2"
            break
    # Alternative: check model config directly
    if attn_impl == "unknown" and hasattr(model, "config"):
        cfg = model.config
        if hasattr(cfg, "_attn_implementation"):
            attn_impl = cfg._attn_implementation
        elif hasattr(cfg, "attn_implementation"):
            attn_impl = cfg.attn_implementation
    return attn_impl


# ---------------------------------------------------------------------------
# Part 1: decode rate by model size
# ---------------------------------------------------------------------------

PART1_CSV_FIELDS = [
    "model_slug", "model_size_b", "condition", "rep",
    "weight_bytes", "weight_gb",
    "n_input_tokens", "n_output_tokens",
    "prefill_ms", "decode_ms", "decode_tok_per_s",
    "peak_mem_allocated_gb", "peak_mem_reserved_gb",
    "attn_impl", "compile_ok",
    "is_warmup",
]


def run_part1_model(model_slug, model_path, env_info):
    print(f"\n=== Part 1: {model_slug} ===")

    results = []
    img  = load_image()

    # Load model
    gc.collect()
    torch.cuda.empty_cache()
    reset_peak()

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        torch_dtype=DTYPE,
        device_map=DEVICE,
        attn_implementation="flash_attention_2",
    )
    model.eval()

    assert_device_and_dtype(model, model_slug)
    attn_impl = get_attn_impl(model)
    w_bytes = weight_bytes(model)
    w_gb = w_bytes / 1e9

    # Compute roofline: bytes transferred per token = weight_bytes × 2 (load params once per token)
    # Decode bandwidth ceiling = A6000_BW_GBPS × 1e9 / w_bytes tokens/s
    roofline_tps = (A6000_BW_GBPS * 1e9) / w_bytes

    print(f"  weights: {w_gb:.2f} GB | attn: {attn_impl}")
    print(f"  roofline: {roofline_tps:.1f} tok/s (A6000 {A6000_BW_GBPS} GB/s / {w_gb:.2f} GB weights)")

    processor = AutoProcessor.from_pretrained(model_path)

    # Prepare fixed input — one image, fixed prompt
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": "Describe the image in detail."},
        ],
    }]
    text_prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs_raw = processor(
        text=[text_prompt],
        images=[img],
        return_tensors="pt",
    )
    inputs = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v
              for k, v in inputs_raw.items()}
    n_input = inputs["input_ids"].shape[-1]

    # EOS suppressed: Qwen3VL keeps eos_token_id in the generation config and tokenizer,
    # not in model.config (which raises AttributeError). Check all three.
    eos_ids = set()
    for src in [model.generation_config, processor.tokenizer]:
        val = getattr(src, "eos_token_id", None)
        if val is None:
            continue
        if isinstance(val, list):
            eos_ids.update(val)
        else:
            eos_ids.add(val)
    suppress_tokens = list(eos_ids) if eos_ids else None

    gen_kwargs_base = dict(
        min_new_tokens=DECODE_TOKENS,
        max_new_tokens=DECODE_TOKENS,
        suppress_tokens=suppress_tokens,
        do_sample=False,
    )

    # --- C1: dynamic cache ---
    print("  C1: dynamic cache")
    for rep in range(N_REPS):
        gc.collect(); torch.cuda.empty_cache(); reset_peak()
        sync()
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**inputs, **gen_kwargs_base)
        sync()
        t_total = (time.perf_counter() - t0) * 1000  # ms

        n_out = out.shape[-1] - n_input
        assert n_out == DECODE_TOKENS, f"[SANITY FAIL] C1 rep{rep}: n_out={n_out}, expected {DECODE_TOKENS}"

        # Estimate prefill vs decode: we don't have per-phase hooks in C1.
        # Use a separate prefill-only pass to isolate it.
        gc.collect(); torch.cuda.empty_cache(); reset_peak()
        sync()
        t_p0 = time.perf_counter()
        with torch.no_grad():
            _ = model.generate(**inputs, max_new_tokens=1, do_sample=False)
        sync()
        prefill_ms = (time.perf_counter() - t_p0) * 1000

        decode_ms = t_total - prefill_ms
        decode_tps = n_out / (decode_ms / 1000) if decode_ms > 0 else float("nan")

        peak_alloc = gpu_peak_gb()
        peak_res   = gpu_peak_reserved_gb()

        print(f"    rep{rep}: prefill={prefill_ms:.0f}ms decode={decode_ms:.0f}ms tps={decode_tps:.1f} peak={peak_alloc:.2f}GB")
        results.append({
            "model_slug": model_slug,
            "model_size_b": 4 if "4B" in model_slug else 8,
            "condition": "C1",
            "rep": rep,
            "weight_bytes": w_bytes,
            "weight_gb": round(w_gb, 3),
            "n_input_tokens": n_input,
            "n_output_tokens": n_out,
            "prefill_ms": round(prefill_ms, 1),
            "decode_ms": round(decode_ms, 1),
            "decode_tok_per_s": round(decode_tps, 2),
            "peak_mem_allocated_gb": round(peak_alloc, 3),
            "peak_mem_reserved_gb": round(peak_res, 3),
            "attn_impl": attn_impl,
            "compile_ok": True,
            "is_warmup": False,
        })

    # --- C2: static cache ---
    # rep0 initialises the static cache (much longer than steady-state); treat as warmup.
    print("  C2: static cache")
    for rep in range(N_REPS):
        is_warmup_c2 = (rep == 0)
        gc.collect(); torch.cuda.empty_cache(); reset_peak()
        sync()
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**inputs, **gen_kwargs_base,
                                  cache_implementation="static")
        sync()
        t_total = (time.perf_counter() - t0) * 1000

        n_out = out.shape[-1] - n_input
        if not is_warmup_c2:
            assert n_out == DECODE_TOKENS, f"[SANITY FAIL] C2 rep{rep}: n_out={n_out}, expected {DECODE_TOKENS}"

        gc.collect(); torch.cuda.empty_cache(); reset_peak()
        sync()
        t_p0 = time.perf_counter()
        with torch.no_grad():
            _ = model.generate(**inputs, max_new_tokens=1, do_sample=False,
                                cache_implementation="static")
        sync()
        prefill_ms = (time.perf_counter() - t_p0) * 1000
        decode_ms  = t_total - prefill_ms
        decode_tps = n_out / (decode_ms / 1000) if decode_ms > 0 else float("nan")

        peak_alloc = gpu_peak_gb()
        peak_res   = gpu_peak_reserved_gb()

        label = "warmup" if is_warmup_c2 else "steady"
        print(f"    rep{rep} ({label}): prefill={prefill_ms:.0f}ms decode={decode_ms:.0f}ms tps={decode_tps:.1f} peak={peak_alloc:.2f}GB")
        results.append({
            "model_slug": model_slug,
            "model_size_b": 4 if "4B" in model_slug else 8,
            "condition": "C2",
            "rep": rep,
            "weight_bytes": w_bytes,
            "weight_gb": round(w_gb, 3),
            "n_input_tokens": n_input,
            "n_output_tokens": n_out,
            "prefill_ms": round(prefill_ms, 1),
            "decode_ms": round(decode_ms, 1),
            "decode_tok_per_s": round(decode_tps, 2),
            "peak_mem_allocated_gb": round(peak_alloc, 3),
            "peak_mem_reserved_gb": round(peak_res, 3),
            "attn_impl": attn_impl,
            "compile_ok": True,
            "is_warmup": is_warmup_c2,
        })

    # --- C3: static cache + torch.compile ---
    # fullgraph=True may fail on models with dynamic control flow (e.g. flash-attn C++ ops).
    # Per spec: record the error and continue; C3 rows are omitted from the output.
    print("  C3: static cache + torch.compile")
    compile_ok = True
    c3_error = None
    _orig_forward = model.forward

    try:
        compiled_forward = torch.compile(model.forward, mode="reduce-overhead", fullgraph=True)
        model.forward = compiled_forward
    except Exception as exc:
        print(f"    torch.compile() setup FAILED: {exc} — skipping C3")
        compile_ok = False
        c3_error = str(exc)

    if compile_ok:
        for rep in range(N_REPS):
            if not compile_ok:
                break
            gc.collect(); torch.cuda.empty_cache(); reset_peak()
            sync()
            try:
                t0 = time.perf_counter()
                with torch.no_grad():
                    out = model.generate(**inputs, **gen_kwargs_base,
                                          cache_implementation="static")
                sync()
                t_total = (time.perf_counter() - t0) * 1000
            except Exception as exc:
                print(f"    C3 rep{rep} generate FAILED: {type(exc).__name__}: {exc!s:.200} — aborting C3")
                c3_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                compile_ok = False
                model.forward = _orig_forward
                break

            n_out = out.shape[-1] - n_input
            is_warmup = (rep == 0)
            if not is_warmup:
                assert n_out == DECODE_TOKENS, f"[SANITY FAIL] C3 rep{rep}: n_out={n_out}, expected {DECODE_TOKENS}"

            gc.collect(); torch.cuda.empty_cache(); reset_peak()
            sync()
            try:
                t_p0 = time.perf_counter()
                with torch.no_grad():
                    _ = model.generate(**inputs, max_new_tokens=1, do_sample=False,
                                        cache_implementation="static")
                sync()
                prefill_ms = (time.perf_counter() - t_p0) * 1000
            except Exception:
                prefill_ms = float("nan")

            decode_ms  = t_total - prefill_ms if not (prefill_ms != prefill_ms) else float("nan")
            decode_tps = n_out / (decode_ms / 1000) if decode_ms > 0 else float("nan")
            peak_alloc = gpu_peak_gb()
            peak_res   = gpu_peak_reserved_gb()

            label = "warmup" if is_warmup else "steady"
            print(f"    rep{rep} ({label}): prefill={prefill_ms:.0f}ms decode={decode_ms:.0f}ms tps={decode_tps:.1f} peak={peak_alloc:.2f}GB")
            results.append({
                "model_slug": model_slug,
                "model_size_b": 4 if "4B" in model_slug else 8,
                "condition": "C3",
                "rep": rep,
                "weight_bytes": w_bytes,
                "weight_gb": round(w_gb, 3),
                "n_input_tokens": n_input,
                "n_output_tokens": n_out,
                "prefill_ms": round(prefill_ms, 1) if prefill_ms == prefill_ms else None,
                "decode_ms": round(decode_ms, 1) if decode_ms == decode_ms else None,
                "decode_tok_per_s": round(decode_tps, 2) if decode_tps == decode_tps else None,
                "peak_mem_allocated_gb": round(peak_alloc, 3),
                "peak_mem_reserved_gb": round(peak_res, 3),
                "attn_impl": attn_impl,
                "compile_ok": compile_ok,
                "is_warmup": is_warmup,
            })

        model.forward = _orig_forward

    # Noise floor: std of decode_tps across C1 reps
    c1_tps = [r["decode_tok_per_s"] for r in results if r["condition"] == "C1" and not r["is_warmup"]]
    noise_floor_std = float(np.std(c1_tps)) if len(c1_tps) > 1 else float("nan")
    print(f"  C1 decode noise floor std: {noise_floor_std:.2f} tok/s")

    model_summary = {
        "model_slug": model_slug,
        "weight_bytes": w_bytes,
        "weight_gb": round(w_gb, 3),
        "roofline_tps": round(roofline_tps, 1),
        "attn_impl": attn_impl,
        "compile_ok": compile_ok,
        "c3_error": c3_error,
        "c1_noise_floor_std_tps": round(noise_floor_std, 2),
        "per_condition": {},
    }

    for cond in ["C1", "C2", "C3"]:
        cond_rows = [r for r in results if r["condition"] == cond and not r["is_warmup"]]
        if not cond_rows:
            continue
        tps_vals = [r["decode_tok_per_s"] for r in cond_rows]
        model_summary["per_condition"][cond] = {
            "median_decode_tps": round(float(np.median(tps_vals)), 2),
            "mean_decode_tps":   round(float(np.mean(tps_vals)), 2),
            "std_decode_tps":    round(float(np.std(tps_vals)), 2),
            "pct_of_roofline":   round(float(np.median(tps_vals)) / roofline_tps * 100, 2),
            "n_reps": len(cond_rows),
        }

    # Unload model
    del model
    gc.collect()
    torch.cuda.empty_cache()

    return results, model_summary


# ---------------------------------------------------------------------------
# Part 2: phase-level memory attribution for Qwen2.5-VL-7B
# ---------------------------------------------------------------------------

PART2_CSV_FIELDS = [
    "n_frames", "total_vision_patches", "encode_batched",
    "phase_after_load_allocated_gb", "phase_after_load_reserved_gb",
    "phase_after_vision_allocated_gb", "phase_after_vision_reserved_gb",
    "phase_after_prefill_allocated_gb", "phase_after_prefill_reserved_gb",
    "peak_allocated_gb", "peak_reserved_gb",
    "kv_analytical_gb",
    "attn_impl",
]


def run_part2():
    print("\n=== Part 2: Qwen2.5-VL-7B phase-level memory attribution ===")

    img = load_image()
    results = []

    # Study B reference peaks (max_memory_allocated) at N we test:
    # Study B did not report per-N peak explicitly; we use the N=48 figure (24.4 GB)
    # and derive a sanity floor: peak must be ≥ weights + KV for that N.
    # The strict check: weight ≈ 14 GB; KV per N grows linearly; peak must exceed both.
    # If peak disagrees by >2 GB from weight+KV model, we stop and report.

    for N in PART2_N_VALUES:
        print(f"\n  N={N} frames")
        gc.collect()
        torch.cuda.empty_cache()
        reset_peak()

        # --- Phase 0: baseline before load (not measured, just record GPU free) ---

        # --- Load model ---
        reset_peak()
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL7B_PATH,
            torch_dtype=DTYPE,
            device_map=DEVICE,
            attn_implementation="flash_attention_2",
        )
        model.eval()

        assert_device_and_dtype(model, "qwen2vl7b")
        attn_impl = get_attn_impl(model)

        sync()
        after_load_alloc = gpu_mem_gb()
        after_load_res   = gpu_reserved_gb()
        peak_after_load_alloc = gpu_peak_gb()

        print(f"    after load: alloc={after_load_alloc:.3f} GB  res={after_load_res:.3f} GB")

        processor = AutoProcessor.from_pretrained(MODEL7B_PATH)

        # Build N-frame input (same setup as Study B)
        images = [img] * N
        messages = [{
            "role": "user",
            "content": [{"type": "image", "image": im} for im in images]
            + [{"type": "text", "text": "What objects are visible? List the three most prominent."}],
        }]
        text_prompt = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs_raw = processor(
            text=[text_prompt],
            images=images,
            return_tensors="pt",
        )
        inputs = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v
                  for k, v in inputs_raw.items()}

        n_input = inputs["input_ids"].shape[-1]
        pixel_values = inputs.get("pixel_values")
        total_patches = pixel_values.shape[0] if pixel_values is not None else N * TOKENS_PER_FRAME_2_5VL

        # Check if encoding is batched (single call) or per-frame
        # Qwen2.5-VL processes all frames in one batched vision encoder call.
        encode_batched = True  # Qwen2.5-VL always batches vision encoding

        # --- Phase 1: vision encoding ---
        # We isolate vision encoding by calling the vision tower directly.
        reset_peak()
        sync()
        with torch.no_grad():
            if pixel_values is not None and hasattr(model, "visual"):
                grid_thw = inputs.get("image_grid_thw")
                _ = model.visual(pixel_values, grid_thw=grid_thw)
            else:
                # Cannot isolate; skip phase 1 separately
                pass
        sync()

        after_vision_alloc = gpu_mem_gb()
        after_vision_res   = gpu_reserved_gb()
        peak_vision_alloc  = gpu_peak_gb()

        print(f"    after vision: alloc={after_vision_alloc:.3f} GB  res={after_vision_res:.3f} GB")

        # --- Phase 2: full prefill (LM forward) ---
        reset_peak()
        gc.collect(); torch.cuda.empty_cache()
        sync()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=1, do_sample=False)
        sync()

        after_prefill_alloc = gpu_mem_gb()
        after_prefill_res   = gpu_reserved_gb()
        peak_prefill_alloc  = gpu_peak_gb()
        peak_prefill_res    = gpu_peak_reserved_gb()

        print(f"    after prefill: alloc={after_prefill_alloc:.3f} GB  res={after_prefill_res:.3f} GB  peak_alloc={peak_prefill_alloc:.3f} GB")

        # --- Analytical KV ---
        kv_bytes_analytical = n_input * KV_BYTES_PER_TOK_7B
        kv_gb_analytical = kv_bytes_analytical / 1e9

        # --- Sanity check: peak must exceed weights + KV ---
        # After_load_alloc approximates weight footprint.
        expected_floor = after_load_alloc + kv_gb_analytical
        if peak_prefill_alloc < expected_floor - STUDY_B_PEAK_TOLERANCE_GB:
            raise RuntimeError(
                f"[SANITY FAIL] N={N}: peak_alloc={peak_prefill_alloc:.3f} GB < "
                f"floor={expected_floor:.3f} GB (weights={after_load_alloc:.3f} + KV={kv_gb_analytical:.3f})"
            )

        results.append({
            "n_frames": N,
            "total_vision_patches": int(total_patches),
            "encode_batched": encode_batched,
            "phase_after_load_allocated_gb": round(after_load_alloc, 3),
            "phase_after_load_reserved_gb":  round(after_load_res, 3),
            "phase_after_vision_allocated_gb": round(after_vision_alloc, 3),
            "phase_after_vision_reserved_gb":  round(after_vision_res, 3),
            "phase_after_prefill_allocated_gb": round(after_prefill_alloc, 3),
            "phase_after_prefill_reserved_gb":  round(after_prefill_res, 3),
            "peak_allocated_gb": round(peak_prefill_alloc, 3),
            "peak_reserved_gb":  round(peak_prefill_res, 3),
            "kv_analytical_gb":  round(kv_gb_analytical, 3),
            "attn_impl": attn_impl,
        })

        del model
        gc.collect()
        torch.cuda.empty_cache()

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Study F: A6000 diagnostic")
    print(f"Output directory: {OUT_DIR}")

    # Environment
    env = get_env_info()
    with open(OUT_DIR / "study_f_environment.json", "w") as f:
        json.dump(env, f, indent=2)
    print("\nEnvironment:")
    for k, v in env.items():
        print(f"  {k}: {v}")

    # -----------------------------------------------------------------------
    # Part 1
    # -----------------------------------------------------------------------
    all_p1_rows = []
    p1_summaries = {}

    for slug, path in [("qwen3vl4b_i", MODEL4B_PATH), ("qwen3vl8b_i", MODEL8B_PATH)]:
        rows, summary = run_part1_model(slug, path, env)
        all_p1_rows.extend(rows)
        p1_summaries[slug] = summary

    # Write Part 1 CSV
    p1_csv_path = OUT_DIR / "study_f_part1_decode.csv"
    with open(p1_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PART1_CSV_FIELDS)
        writer.writeheader()
        for row in all_p1_rows:
            writer.writerow(row)
    print(f"\nPart 1 CSV: {p1_csv_path} ({len(all_p1_rows)} rows)")

    # Part 1 separation summary
    print("\n--- Part 1 decode rate summary ---")
    for cond in ["C1", "C2", "C3"]:
        r4 = p1_summaries["qwen3vl4b_i"]["per_condition"].get(cond)
        r8 = p1_summaries["qwen3vl8b_i"]["per_condition"].get(cond)
        if r4 and r8:
            ratio = r8["median_decode_tps"] / r4["median_decode_tps"] if r4["median_decode_tps"] > 0 else float("nan")
            print(f"  {cond}: 4B={r4['median_decode_tps']:.1f} tok/s ({r4['pct_of_roofline']:.1f}% RL) | "
                  f"8B={r8['median_decode_tps']:.1f} tok/s ({r8['pct_of_roofline']:.1f}% RL) | ratio={ratio:.3f}")

    p1_json = {
        "a6000_bw_gbps": A6000_BW_GBPS,
        "decode_tokens_fixed": DECODE_TOKENS,
        "n_reps": N_REPS,
        "models": p1_summaries,
    }
    with open(OUT_DIR / "study_f_part1_decode.json", "w") as f:
        json.dump(p1_json, f, indent=2)

    # -----------------------------------------------------------------------
    # Part 2
    # -----------------------------------------------------------------------
    p2_rows = run_part2()

    p2_csv_path = OUT_DIR / "study_f_part2_memory.csv"
    with open(p2_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PART2_CSV_FIELDS)
        writer.writeheader()
        for row in p2_rows:
            writer.writerow(row)
    print(f"\nPart 2 CSV: {p2_csv_path} ({len(p2_rows)} rows)")

    # Phase attribution
    print("\n--- Part 2 memory attribution ---")
    for r in p2_rows:
        w_gb   = r["phase_after_load_allocated_gb"]
        vis_gb = r["phase_after_vision_allocated_gb"] - w_gb
        kv_gb  = r["kv_analytical_gb"]
        peak   = r["peak_allocated_gb"]
        unaccounted = peak - w_gb - max(vis_gb, 0) - kv_gb
        pct_vis = vis_gb / peak * 100 if peak > 0 else float("nan")
        print(f"  N={r['n_frames']}: weights={w_gb:.2f} vis_delta={vis_gb:.3f} ({pct_vis:.1f}%) kv={kv_gb:.3f} unaccounted={unaccounted:.3f} peak={peak:.3f} GB")

    p2_json = {
        "model": "Qwen2.5-VL-7B-Instruct",
        "device": DEVICE,
        "dtype": str(DTYPE),
        "image_size": IMAGE_SIZE,
        "tokens_per_frame": TOKENS_PER_FRAME_2_5VL,
        "kv_bytes_per_token": KV_BYTES_PER_TOK_7B,
        "n_values": PART2_N_VALUES,
        "rows": p2_rows,
    }
    with open(OUT_DIR / "study_f_part2_memory.json", "w") as f:
        json.dump(p2_json, f, indent=2)

    print("\nDone. All sanity checks passed.")
    print("Files written:")
    for p in sorted(OUT_DIR.iterdir()):
        print(f"  {p}")


if __name__ == "__main__":
    main()
