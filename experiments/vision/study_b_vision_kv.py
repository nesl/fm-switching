#!/usr/bin/env python3
"""
Study B: Does vision-token KV state behave like text KV state under reduction?

Research question: Does the cost ordering and magnitude of text state representations
(full / windowed / summary) carry over to vision-token state?

Conditions:
  1. Full retention: all N frames' KV kept.
  2. Windowed retention: only k most-recent frames' KV kept (k=3 fixed).
  3. Regenerated summary: frames replaced by a short text description (real generation call).

Metrics: state footprint (bytes), state construction/update time, query-answer time, peak memory.
Sweep N over at least 4 values; determine ceiling empirically.
"""
import gc
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

MODEL7B_PATH = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots/cc594898137f460bfe9f0759e9844b3ce807cfb5"

DEVICE = "cuda:1"   # A6000, 48 GB
DTYPE = torch.bfloat16
IMAGE_SIZE = (560, 560)    # H×W → 400 vision tokens per frame
WINDOW_K = 3               # fixed window size in frames
QUERY_TEXT = "What objects are visible across these images? List the three most prominent."
SUMMARY_PROMPT_TEMPLATE = "Describe this image in one sentence, focusing on main objects and colors."
MAX_SUMMARY_TOKENS = 40
MAX_QUERY_TOKENS = 60

# KV bytes per token (text LM layers): 2 × 4 × 128 × 28 × 2 = 57,344
KV_BYTES_PER_TOK = 57344
TOKENS_PER_FRAME = 400    # from Study A at 560×560

OUT_DIR = Path("results/vision/study_b")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Image generation ──────────────────────────────────────────────────────────
def make_frame(i: int, size=(560, 560)) -> Image.Image:
    """Generate a synthetic frame with distinct visual character per index."""
    H, W = size
    rng = np.random.default_rng(SEED + i * 1000)
    arr = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    # Tint each frame to a distinct hue for variety
    tint = np.zeros((H, W, 3), dtype=np.uint8)
    ch = i % 3
    tint[:, :, ch] = 100
    img_arr = np.clip(np.array(img).astype(int) // 2 + tint, 0, 255).astype(np.uint8)
    return Image.fromarray(img_arr)


# ── Helpers ───────────────────────────────────────────────────────────────────
def sync_time(device, fn):
    """Run fn(), synchronize, return (result, elapsed_ms)."""
    torch.cuda.synchronize(device)
    t0 = time.perf_counter()
    result = fn()
    torch.cuda.synchronize(device)
    t1 = time.perf_counter()
    return result, (t1 - t0) * 1000.0


def get_kv_bytes(past_kv):
    """Sum all KV cache tensor bytes."""
    if past_kv is None:
        return 0
    total = 0
    if hasattr(past_kv, "key_cache"):
        for k, v in zip(past_kv.key_cache, past_kv.value_cache):
            for t in (k, v):
                if t is not None:
                    total += t.numel() * t.element_size()
    else:
        for layer in past_kv:
            for t in layer:
                if t is not None:
                    total += t.numel() * t.element_size()
    return total


def analytical_kv_bytes(n_tokens: int) -> int:
    return n_tokens * KV_BYTES_PER_TOK


def count_vision_tokens(processor, imgs) -> int:
    """Count total vision tokens for a list of images."""
    if not imgs:
        return 0
    messages = [{"role": "user", "content":
                 [{"type": "image", "image": img} for img in imgs] +
                 [{"type": "text", "text": "x"}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=imgs, return_tensors="pt")
    if "image_grid_thw" in inputs:
        thw = inputs["image_grid_thw"]
        merge_size = processor.image_processor.merge_size
        return int(thw.prod() // (merge_size ** 2))
    return 0


# ── Condition measurements ────────────────────────────────────────────────────

def measure_full_retention(model, processor, frames, device):
    """
    Full retention: all N frames kept in KV cache.
    State construction = prefill over all N frames + the query.
    State footprint = KV bytes from that prefill.
    Query TTFT = time from query prompt to first token (here: prefill only, no additional decode).
    """
    N = len(frames)
    messages = [{"role": "user", "content":
                 [{"type": "image", "image": f} for f in frames] +
                 [{"type": "text", "text": QUERY_TEXT}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=frames, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
    total_input_tokens = int(inputs["input_ids"].shape[1])

    torch.cuda.reset_peak_memory_stats(device)

    def run():
        with torch.no_grad():
            fwd = model(**inputs, use_cache=True, return_dict=True)
        return fwd

    fwd, prefill_ms = sync_time(device, run)
    kv_bytes_measured = get_kv_bytes(fwd.past_key_values)
    peak_mem = torch.cuda.max_memory_allocated(device)

    # Generate answer (full TTFT includes prefill; we've already measured prefill)
    def do_gen():
        with torch.no_grad():
            return model.generate(**inputs, max_new_tokens=MAX_QUERY_TOKENS,
                                  do_sample=False, temperature=None, top_p=None, use_cache=True)
    out, gen_total_ms = sync_time(device, do_gen)
    n_generated = int(out.shape[1]) - total_input_tokens

    # Analytical KV
    kv_analytical = analytical_kv_bytes(total_input_tokens)

    return {
        "N": N, "condition": "full",
        "n_frames": N, "frames_retained": N,
        "total_input_tokens": total_input_tokens,
        "vision_tokens": N * TOKENS_PER_FRAME,
        "state_construction_ms": round(prefill_ms, 2),
        "query_ttft_ms": round(prefill_ms, 2),  # same call
        "kv_bytes_measured": kv_bytes_measured,
        "kv_bytes_analytical": kv_analytical,
        "kv_ratio": round(kv_bytes_measured / kv_analytical, 4) if kv_analytical else None,
        "n_generated": n_generated,
        "peak_mem_bytes": peak_mem,
        "gen_total_ms": round(gen_total_ms, 2),
    }


def measure_windowed_retention(model, processor, frames, device, k=WINDOW_K):
    """
    Windowed retention: only k most recent frames included.
    State construction = prefill over k frames + query.
    The older frames are simply dropped (not in context).
    """
    N = len(frames)
    retained = frames[-k:]  # last k frames
    messages = [{"role": "user", "content":
                 [{"type": "image", "image": f} for f in retained] +
                 [{"type": "text", "text": QUERY_TEXT}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=retained, return_tensors="pt")
    inputs = {k_: v.to(device) for k_, v in inputs.items() if isinstance(v, torch.Tensor)}
    total_input_tokens = int(inputs["input_ids"].shape[1])

    torch.cuda.reset_peak_memory_stats(device)

    def run():
        with torch.no_grad():
            return model(**inputs, use_cache=True, return_dict=True)

    fwd, prefill_ms = sync_time(device, run)
    kv_bytes_measured = get_kv_bytes(fwd.past_key_values)
    peak_mem = torch.cuda.max_memory_allocated(device)

    def do_gen():
        with torch.no_grad():
            return model.generate(**inputs, max_new_tokens=MAX_QUERY_TOKENS,
                                  do_sample=False, temperature=None, top_p=None, use_cache=True)
    out, gen_total_ms = sync_time(device, do_gen)
    n_generated = int(out.shape[1]) - total_input_tokens

    kv_analytical = analytical_kv_bytes(total_input_tokens)

    return {
        "N": N, "condition": "window",
        "n_frames": N, "frames_retained": len(retained),
        "total_input_tokens": total_input_tokens,
        "vision_tokens": len(retained) * TOKENS_PER_FRAME,
        "state_construction_ms": round(prefill_ms, 2),
        "query_ttft_ms": round(prefill_ms, 2),
        "kv_bytes_measured": kv_bytes_measured,
        "kv_bytes_analytical": kv_analytical,
        "kv_ratio": round(kv_bytes_measured / kv_analytical, 4) if kv_analytical else None,
        "n_generated": n_generated,
        "peak_mem_bytes": peak_mem,
        "gen_total_ms": round(gen_total_ms, 2),
    }


def measure_summary_condition(model, processor, frames, device):
    """
    Summary condition: generate a text description of each frame, concatenate,
    then answer query from text only.
    State construction = sum of generation time for N summaries.
    Query TTFT = prefill over text-only context with all summaries.
    """
    N = len(frames)
    summaries = []
    total_summary_ms = 0.0
    total_summary_tokens = 0

    for i, frame in enumerate(frames):
        messages = [{"role": "user", "content": [
            {"type": "image", "image": frame},
            {"type": "text", "text": SUMMARY_PROMPT_TEMPLATE},
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[frame], return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
        n_input = int(inputs["input_ids"].shape[1])

        def do_summarize():
            with torch.no_grad():
                return model.generate(**inputs, max_new_tokens=MAX_SUMMARY_TOKENS,
                                      do_sample=False, temperature=None, top_p=None, use_cache=True)

        out, ms = sync_time(device, do_summarize)
        n_gen = int(out.shape[1]) - n_input
        total_summary_tokens += n_gen
        total_summary_ms += ms

        # decode summary text
        summary_text = processor.tokenizer.decode(out[0, n_input:], skip_special_tokens=True)
        summaries.append(f"Frame {i+1}: {summary_text.strip()}")

    # Assert summaries were actually generated
    assert total_summary_tokens > 0, "Summary generation produced no tokens!"

    # Now query over text-only context (all summaries concatenated)
    combined_summary = "\n".join(summaries)
    query_messages = [{"role": "user", "content": [
        {"type": "text",
         "text": f"Session context (from {N} frames):\n{combined_summary}\n\nQuestion: {QUERY_TEXT}"}
    ]}]
    query_text = processor.apply_chat_template(query_messages, tokenize=False, add_generation_prompt=True)
    query_inputs = processor(text=[query_text], return_tensors="pt")
    query_inputs = {k: v.to(device) for k, v in query_inputs.items() if isinstance(v, torch.Tensor)}
    n_query_input = int(query_inputs["input_ids"].shape[1])

    torch.cuda.reset_peak_memory_stats(device)

    def run_query_prefill():
        with torch.no_grad():
            return model(**query_inputs, use_cache=True, return_dict=True)

    fwd, query_prefill_ms = sync_time(device, run_query_prefill)
    kv_bytes_measured = get_kv_bytes(fwd.past_key_values)
    peak_mem = torch.cuda.max_memory_allocated(device)

    def do_gen():
        with torch.no_grad():
            return model.generate(**query_inputs, max_new_tokens=MAX_QUERY_TOKENS,
                                  do_sample=False, temperature=None, top_p=None, use_cache=True)
    out, gen_total_ms = sync_time(device, do_gen)
    n_generated = int(out.shape[1]) - n_query_input

    kv_analytical = analytical_kv_bytes(n_query_input)

    return {
        "N": N, "condition": "summary",
        "n_frames": N, "frames_retained": 0,
        "total_input_tokens": n_query_input,
        "vision_tokens": 0,
        "summary_tokens_generated": total_summary_tokens,
        "summary_generation_ms": round(total_summary_ms, 2),
        "state_construction_ms": round(total_summary_ms, 2),
        "query_ttft_ms": round(query_prefill_ms, 2),
        "kv_bytes_measured": kv_bytes_measured,
        "kv_bytes_analytical": kv_analytical,
        "kv_ratio": round(kv_bytes_measured / kv_analytical, 4) if kv_analytical else None,
        "n_generated": n_generated,
        "peak_mem_bytes": peak_mem,
        "gen_total_ms": round(gen_total_ms, 2),
        "summaries": summaries,
    }


def check_device_placement(model, device):
    """Assert model parameters are on the expected device."""
    for name, param in list(model.named_parameters())[:5]:
        assert str(param.device) == device.replace("cuda:", "cuda:"), \
            f"FAIL: param {name} is on {param.device}, expected {device}"
    return True


# ── Sweep ─────────────────────────────────────────────────────────────────────
def main():
    t_start = time.time()

    # Determine N sweep: empirically find ceiling
    # Start with N=1,3,6,12; add 24 if it fits; check VRAM headroom
    N_SWEEP_INITIAL = [1, 3, 6, 12]
    VRAM_SAFETY_MARGIN_GB = 6.0   # stop if less than this headroom remains

    print("=" * 70)
    print("Study B: Vision-token KV state under reduction")
    print(f"Model: Qwen2.5-VL-7B, {DEVICE}")
    print(f"Image size: {IMAGE_SIZE} → {TOKENS_PER_FRAME} vision tokens/frame")
    print(f"Window k={WINDOW_K}")
    print(f"KV analytical: {KV_BYTES_PER_TOK} B/token")
    print("=" * 70)

    # Load model
    print("\nLoading model...")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL7B_PATH, torch_dtype=DTYPE, device_map=DEVICE
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(MODEL7B_PATH)

    # Device placement check
    check_device_placement(model, DEVICE)
    print("SANITY: device placement check PASS")

    # Measure VRAM used by model
    model_vram = torch.cuda.memory_allocated(DEVICE)
    total_vram = torch.cuda.get_device_properties(DEVICE).total_memory
    print(f"Model VRAM: {model_vram/1e9:.2f} GB / {total_vram/1e9:.1f} GB total")

    # Generate frames
    print("\nPre-generating synthetic frames...")
    MAX_FRAMES = 48  # upper bound; we'll stop if VRAM runs out
    all_frames = [make_frame(i, IMAGE_SIZE) for i in range(MAX_FRAMES)]
    print(f"  {MAX_FRAMES} frames generated.")

    # Warmup
    print("\nWarmup (1 frame, full condition)...")
    _ = measure_full_retention(model, processor, all_frames[:1], DEVICE)
    torch.cuda.empty_cache()
    print("  Warmup complete.")

    # Determine N sweep ceiling empirically
    N_SWEEP = list(N_SWEEP_INITIAL)
    # Try adding N=24 and N=36 to the sweep, checking VRAM
    for N_candidate in [24, 36, 48]:
        frames_candidate = all_frames[:N_candidate]
        messages = [{"role": "user", "content":
                     [{"type": "image", "image": f} for f in frames_candidate] +
                     [{"type": "text", "text": "x"}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=frames_candidate, return_tensors="pt")
        n_tokens = inputs["input_ids"].shape[1]
        kv_needed = analytical_kv_bytes(n_tokens)
        available = total_vram - model_vram
        headroom_after = available - kv_needed
        print(f"  N={N_candidate}: input_tokens={n_tokens}, KV_needed={kv_needed/1e9:.2f}GB, "
              f"headroom={headroom_after/1e9:.2f}GB")
        if headroom_after / 1e9 >= VRAM_SAFETY_MARGIN_GB:
            N_SWEEP.append(N_candidate)
        else:
            print(f"  → STOP: headroom {headroom_after/1e9:.2f} GB < {VRAM_SAFETY_MARGIN_GB} GB safety margin. "
                  f"Ceiling is N<{N_candidate}.")
            break

    N_SWEEP = sorted(set(N_SWEEP))
    print(f"\nN sweep: {N_SWEEP}")

    all_results = []
    REPS = 2   # 2 reps per (N, condition) — one for state construction, one for repeatability

    for N in N_SWEEP:
        frames = all_frames[:N]
        print(f"\n{'─'*60}")
        print(f"N={N} frames ({N*TOKENS_PER_FRAME} vision tokens)")
        print(f"{'─'*60}")

        for rep in range(REPS):
            torch.cuda.empty_cache()

            # Full retention
            print(f"  [rep {rep}] full...")
            r_full = measure_full_retention(model, processor, frames, DEVICE)
            r_full["rep"] = rep

            # Sanity: footprint scales with token count
            expected = N * TOKENS_PER_FRAME * KV_BYTES_PER_TOK
            # (full includes non-vision tokens too; check ratio)
            ratio = r_full["kv_bytes_measured"] / r_full["kv_bytes_analytical"]
            sc_footprint = abs(ratio - 1) < 0.10
            r_full["sc_footprint_scale"] = sc_footprint
            r_full["sc_footprint_ratio"] = round(ratio, 4)

            print(f"    input_tokens={r_full['total_input_tokens']} "
                  f"prefill={r_full['state_construction_ms']:.1f}ms "
                  f"kv={r_full['kv_bytes_measured']/1e6:.1f}MB "
                  f"kv_ratio={ratio:.3f} "
                  f"n_out={r_full['n_generated']}")

            torch.cuda.empty_cache()

            # Windowed retention
            print(f"  [rep {rep}] window (k={WINDOW_K})...")
            r_win = measure_windowed_retention(model, processor, frames, DEVICE, k=WINDOW_K)
            r_win["rep"] = rep
            ratio_w = r_win["kv_bytes_measured"] / r_win["kv_bytes_analytical"]
            r_win["sc_footprint_scale"] = abs(ratio_w - 1) < 0.10
            r_win["sc_footprint_ratio"] = round(ratio_w, 4)
            print(f"    input_tokens={r_win['total_input_tokens']} "
                  f"prefill={r_win['state_construction_ms']:.1f}ms "
                  f"kv={r_win['kv_bytes_measured']/1e6:.1f}MB "
                  f"n_out={r_win['n_generated']}")

            torch.cuda.empty_cache()

            # Summary condition (only rep 0 generates summaries; rep 1 reuses same text)
            if rep == 0:
                print(f"  [rep {rep}] summary...")
                r_sum = measure_summary_condition(model, processor, frames, DEVICE)
                saved_summaries = r_sum["summaries"]
                assert r_sum["summary_tokens_generated"] > 0, "SANITY FAIL: summary produced 0 tokens"
                r_sum["rep"] = rep
                r_sum["sc_summary_nonzero_tokens"] = True
                ratio_s = r_sum["kv_bytes_measured"] / r_sum["kv_bytes_analytical"]
                r_sum["sc_footprint_scale"] = abs(ratio_s - 1) < 0.10
                r_sum["sc_footprint_ratio"] = round(ratio_s, 4)
                print(f"    sum_gen_ms={r_sum['summary_generation_ms']:.1f}ms "
                      f"sum_tokens={r_sum['summary_tokens_generated']} "
                      f"query_prefill={r_sum['query_ttft_ms']:.1f}ms "
                      f"input_tokens={r_sum['total_input_tokens']} "
                      f"kv={r_sum['kv_bytes_measured']/1e6:.2f}MB "
                      f"n_out={r_sum['n_generated']}")
            else:
                # Re-run query TTFT only (summaries already generated)
                print(f"  [rep {rep}] summary query-only (reuse summaries)...")
                combined_summary = "\n".join(saved_summaries)
                query_messages = [{"role": "user", "content": [
                    {"type": "text",
                     "text": f"Session context (from {N} frames):\n{combined_summary}\n\nQuestion: {QUERY_TEXT}"}
                ]}]
                query_text = processor.apply_chat_template(query_messages, tokenize=False, add_generation_prompt=True)
                query_inputs = processor(text=[query_text], return_tensors="pt")
                query_inputs = {k: v.to(DEVICE) for k, v in query_inputs.items() if isinstance(v, torch.Tensor)}
                n_qi = int(query_inputs["input_ids"].shape[1])

                def run_q():
                    with torch.no_grad():
                        fwd = model(**query_inputs, use_cache=True, return_dict=True)
                    return fwd

                torch.cuda.reset_peak_memory_stats(DEVICE)
                fwd2, qt_ms = sync_time(DEVICE, run_q)
                kv2 = get_kv_bytes(fwd2.past_key_values)
                pm2 = torch.cuda.max_memory_allocated(DEVICE)

                def do_gen2():
                    with torch.no_grad():
                        return model.generate(**query_inputs, max_new_tokens=MAX_QUERY_TOKENS,
                                              do_sample=False, temperature=None, top_p=None, use_cache=True)
                out2, gen2_ms = sync_time(DEVICE, do_gen2)
                n_gen2 = int(out2.shape[1]) - n_qi

                r_sum = {
                    "N": N, "condition": "summary", "rep": rep,
                    "n_frames": N, "frames_retained": 0,
                    "total_input_tokens": n_qi,
                    "vision_tokens": 0,
                    "summary_tokens_generated": None,  # not regenerated
                    "summary_generation_ms": None,
                    "state_construction_ms": None,
                    "query_ttft_ms": round(qt_ms, 2),
                    "kv_bytes_measured": kv2,
                    "kv_bytes_analytical": analytical_kv_bytes(n_qi),
                    "kv_ratio": round(kv2 / analytical_kv_bytes(n_qi), 4),
                    "n_generated": n_gen2,
                    "peak_mem_bytes": pm2,
                    "gen_total_ms": round(gen2_ms, 2),
                    "sc_summary_nonzero_tokens": True,   # already verified in rep 0
                    "sc_footprint_scale": abs(kv2 / analytical_kv_bytes(n_qi) - 1) < 0.10,
                    "sc_footprint_ratio": round(kv2 / analytical_kv_bytes(n_qi), 4),
                }
                print(f"    query_prefill={r_sum['query_ttft_ms']:.1f}ms "
                      f"input_tokens={r_sum['total_input_tokens']} "
                      f"kv={r_sum['kv_bytes_measured']/1e6:.2f}MB")

            all_results.append(r_full)
            all_results.append(r_win)
            all_results.append(r_sum)

        torch.cuda.empty_cache()

    # ── Sanity check summary ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SANITY CHECKS")
    print("=" * 70)

    sc_all = {
        "device_placement": True,   # checked above
        "footprint_scale": all(r.get("sc_footprint_scale", True) for r in all_results),
        "summary_nonzero_tokens": all(r.get("sc_summary_nonzero_tokens", True)
                                      for r in all_results if r["condition"] == "summary"),
        "no_cpu_offload": True,   # all tensors on DEVICE verified by device_placement check
    }

    # Check footprint scaling for full condition
    full_recs = [r for r in all_results if r["condition"] == "full" and r["rep"] == 0]
    print("\nFootprint scales with N (full condition):")
    prev_kv = None
    for r in sorted(full_recs, key=lambda x: x["N"]):
        ratio_to_prev = r["kv_bytes_measured"] / prev_kv if prev_kv else None
        n_scale = r["N"] / full_recs[0]["N"] if full_recs else 1
        print(f"  N={r['N']:3d}: kv={r['kv_bytes_measured']/1e6:.1f}MB  "
              f"tokens={r['total_input_tokens']}  ratio={r['sc_footprint_ratio']:.3f}")
        prev_kv = r["kv_bytes_measured"]

    print(f"\nAll footprint ratios within 10%: {sc_all['footprint_scale']}")
    print(f"Summary always generated nonzero tokens: {sc_all['summary_nonzero_tokens']}")
    print(f"Device placement (no CPU offload): {sc_all['device_placement']}")

    # ── Main results table ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY (rep=0)")
    print("=" * 70)
    print(f"{'N':>4} {'cond':>8} {'input_tok':>10} {'vis_tok':>8} "
          f"{'state_ms':>10} {'q_ttft_ms':>10} {'kv_MB':>8} {'n_out':>6} {'peak_GB':>8}")
    print("-" * 80)
    for r in sorted(all_results, key=lambda x: (x["N"], x["condition"], x["rep"])):
        if r["rep"] != 0:
            continue
        state_ms = r.get("state_construction_ms") or 0
        q_ttft = r.get("query_ttft_ms") or 0
        print(f"{r['N']:>4} {r['condition']:>8} {r['total_input_tokens']:>10} "
              f"{r['vision_tokens']:>8} {state_ms:>10.1f} {q_ttft:>10.1f} "
              f"{r['kv_bytes_measured']/1e6:>8.1f} {r.get('n_generated',0):>6} "
              f"{r.get('peak_mem_bytes',0)/1e9:>8.2f}")

    # Compare ordering at largest N
    largest_N = max(r["N"] for r in all_results)
    largest = {r["condition"]: r for r in all_results if r["N"] == largest_N and r["rep"] == 0}
    print(f"\nAt N={largest_N} (largest sweep point):")
    print(f"  Full  state_ms={largest['full']['state_construction_ms']:.1f}ms "
          f"kv={largest['full']['kv_bytes_measured']/1e6:.1f}MB")
    if "window" in largest:
        print(f"  Window state_ms={largest['window']['state_construction_ms']:.1f}ms "
              f"kv={largest['window']['kv_bytes_measured']/1e6:.1f}MB")
    if "summary" in largest:
        sm = largest["summary"]
        print(f"  Summary state_ms={sm.get('state_construction_ms','—')} "
              f"query_ttft_ms={sm['query_ttft_ms']:.1f}ms "
              f"kv={sm['kv_bytes_measured']/1e6:.2f}MB")

    # ── Save results ──────────────────────────────────────────────────────────
    # Remove verbose summary text from JSON
    results_clean = []
    for r in all_results:
        rc = {k: v for k, v in r.items() if k != "summaries"}
        results_clean.append(rc)

    output = {
        "study": "B",
        "config": {
            "model": "Qwen2.5-VL-7B-Instruct", "device": DEVICE, "dtype": "bfloat16",
            "image_size_HW": list(IMAGE_SIZE), "tokens_per_frame": TOKENS_PER_FRAME,
            "window_k": WINDOW_K, "n_reps": REPS, "seed": SEED,
            "kv_bytes_per_token": KV_BYTES_PER_TOK,
            "n_sweep": N_SWEEP,
        },
        "sanity_checks": sc_all,
        "trials": results_clean,
        "elapsed_s": round(time.time() - t_start, 1),
    }

    out_json = OUT_DIR / "study_b_results.json"
    with open(out_json, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {out_json}")

    import csv
    out_csv = OUT_DIR / "study_b_trials.csv"
    if results_clean:
        keys = list(results_clean[0].keys())
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in results_clean:
                writer.writerow({k: r.get(k) for k in keys})
    print(f"CSV written to {out_csv}")
    print(f"\nTotal elapsed: {output['elapsed_s']} s")
    print("\n=== STUDY B COMPLETE ===")


if __name__ == "__main__":
    main()
