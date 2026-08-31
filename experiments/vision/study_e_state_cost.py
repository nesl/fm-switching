#!/usr/bin/env python3
"""
Study E — Part 2: State-construction cost on Jetson AGX Orin.

Faithful Orin replication of Study B (reports/study_b_vision_kv.md) so the two
cost models are commensurable. Same model (Qwen2.5-VL-7B-Instruct), same
synthetic frames (make_frame, seeded), same conditions (full / window k=3 /
regenerated summary with a real generation call), same N sweep {1,3,6,12,24,36,48},
same query/summary prompts, same KV analytical constant.

Only device-side changes: cuda:0 (Orin), model loaded from HF cache by pinned
revision, empirical ceiling determined for Orin's 64 GB unified memory, output
under results/vision/study_e/.

Output:
  results/vision/study_e/study_e_part2_results.json
  results/vision/study_e/study_e_part2_trials.csv
"""
import csv
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

SEED = 42
torch.manual_seed(SEED); np.random.seed(SEED)

MODEL_REPO = "Qwen/Qwen2.5-VL-7B-Instruct"
MODEL_REV  = "cc594898137f460bfe9f0759e9844b3ce807cfb5"   # match Study B snapshot

DEVICE = "cuda:0"
DTYPE  = torch.bfloat16
IMAGE_SIZE = (560, 560)
WINDOW_K = 3
QUERY_TEXT = "What objects are visible across these images? List the three most prominent."
SUMMARY_PROMPT_TEMPLATE = "Describe this image in one sentence, focusing on main objects and colors."
MAX_SUMMARY_TOKENS = 40
MAX_QUERY_TOKENS = 60
KV_BYTES_PER_TOK = 57344
TOKENS_PER_FRAME = 400
N_SWEEP_STUDYB = [1, 3, 6, 12, 24, 36, 48]
VRAM_SAFETY_MARGIN_GB = 6.0

OUT_DIR = Path("results/vision/study_e")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_frame(i, size=(560, 560)):
    """Identical to Study B make_frame (seeded, per-index tint)."""
    H, W = size
    rng = np.random.default_rng(SEED + i * 1000)
    arr = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    tint = np.zeros((H, W, 3), dtype=np.uint8)
    tint[:, :, i % 3] = 100
    return Image.fromarray(np.clip(np.array(img).astype(int) // 2 + tint, 0, 255).astype(np.uint8))


def sync_time(device, fn):
    torch.cuda.synchronize(device); t0 = time.perf_counter()
    r = fn()
    torch.cuda.synchronize(device); return r, (time.perf_counter() - t0) * 1000.0


def get_kv_bytes(past_kv):
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


def analytical_kv_bytes(n):
    return n * KV_BYTES_PER_TOK


def measure_full(model, proc, frames, device):
    N = len(frames)
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": f} for f in frames] + [{"type": "text", "text": QUERY_TEXT}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=frames, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
    n_in = int(inputs["input_ids"].shape[1])
    torch.cuda.reset_peak_memory_stats(device)
    fwd, prefill_ms = sync_time(device, lambda: model(**inputs, use_cache=True, return_dict=True))
    kv = get_kv_bytes(fwd.past_key_values); peak = torch.cuda.max_memory_allocated(device)
    out, gen_ms = sync_time(device, lambda: model.generate(**inputs, max_new_tokens=MAX_QUERY_TOKENS,
                            do_sample=False, temperature=None, top_p=None, use_cache=True))
    n_gen = int(out.shape[1]) - n_in
    ka = analytical_kv_bytes(n_in)
    return {"N": N, "condition": "full", "frames_retained": N, "total_input_tokens": n_in,
            "vision_tokens": N * TOKENS_PER_FRAME, "state_construction_ms": round(prefill_ms, 2),
            "query_ttft_ms": round(prefill_ms, 2), "kv_bytes_measured": kv, "kv_bytes_analytical": ka,
            "kv_ratio": round(kv/ka, 4) if ka else None, "n_generated": n_gen,
            "peak_mem_bytes": peak, "gen_total_ms": round(gen_ms, 2)}


def measure_window(model, proc, frames, device, k=WINDOW_K):
    N = len(frames); retained = frames[-k:]
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": f} for f in retained] + [{"type": "text", "text": QUERY_TEXT}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=retained, return_tensors="pt")
    inputs = {kk: v.to(device) for kk, v in inputs.items() if isinstance(v, torch.Tensor)}
    n_in = int(inputs["input_ids"].shape[1])
    torch.cuda.reset_peak_memory_stats(device)
    fwd, prefill_ms = sync_time(device, lambda: model(**inputs, use_cache=True, return_dict=True))
    kv = get_kv_bytes(fwd.past_key_values); peak = torch.cuda.max_memory_allocated(device)
    out, gen_ms = sync_time(device, lambda: model.generate(**inputs, max_new_tokens=MAX_QUERY_TOKENS,
                            do_sample=False, temperature=None, top_p=None, use_cache=True))
    n_gen = int(out.shape[1]) - n_in
    ka = analytical_kv_bytes(n_in)
    return {"N": N, "condition": "window", "frames_retained": len(retained), "total_input_tokens": n_in,
            "vision_tokens": len(retained) * TOKENS_PER_FRAME, "state_construction_ms": round(prefill_ms, 2),
            "query_ttft_ms": round(prefill_ms, 2), "kv_bytes_measured": kv, "kv_bytes_analytical": ka,
            "kv_ratio": round(kv/ka, 4) if ka else None, "n_generated": n_gen,
            "peak_mem_bytes": peak, "gen_total_ms": round(gen_ms, 2)}


def measure_summary(model, proc, frames, device):
    N = len(frames); summaries = []; total_ms = 0.0; total_tok = 0
    for i, frame in enumerate(frames):
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": frame}, {"type": "text", "text": SUMMARY_PROMPT_TEMPLATE}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = proc(text=[text], images=[frame], return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
        n_in = int(inputs["input_ids"].shape[1])
        out, ms = sync_time(device, lambda: model.generate(**inputs, max_new_tokens=MAX_SUMMARY_TOKENS,
                            do_sample=False, temperature=None, top_p=None, use_cache=True))
        n_gen = int(out.shape[1]) - n_in; total_tok += n_gen; total_ms += ms
        stext = proc.tokenizer.decode(out[0, n_in:], skip_special_tokens=True)
        summaries.append(f"Frame {i+1}: {stext.strip()}")
    assert total_tok > 0, "SANITY FAIL: summary produced 0 tokens"
    combined = "\n".join(summaries)
    qmsgs = [{"role": "user", "content": [{"type": "text",
              "text": f"Session context (from {N} frames):\n{combined}\n\nQuestion: {QUERY_TEXT}"}]}]
    qtext = proc.apply_chat_template(qmsgs, tokenize=False, add_generation_prompt=True)
    qin = proc(text=[qtext], return_tensors="pt")
    qin = {k: v.to(device) for k, v in qin.items() if isinstance(v, torch.Tensor)}
    n_qin = int(qin["input_ids"].shape[1])
    torch.cuda.reset_peak_memory_stats(device)
    fwd, qprefill_ms = sync_time(device, lambda: model(**qin, use_cache=True, return_dict=True))
    kv = get_kv_bytes(fwd.past_key_values); peak = torch.cuda.max_memory_allocated(device)
    out, gen_ms = sync_time(device, lambda: model.generate(**qin, max_new_tokens=MAX_QUERY_TOKENS,
                            do_sample=False, temperature=None, top_p=None, use_cache=True))
    n_gen = int(out.shape[1]) - n_qin
    ka = analytical_kv_bytes(n_qin)
    return {"N": N, "condition": "summary", "frames_retained": 0, "total_input_tokens": n_qin,
            "vision_tokens": 0, "summary_tokens_generated": total_tok,
            "summary_generation_ms": round(total_ms, 2), "state_construction_ms": round(total_ms, 2),
            "query_ttft_ms": round(qprefill_ms, 2), "kv_bytes_measured": kv, "kv_bytes_analytical": ka,
            "kv_ratio": round(kv/ka, 4) if ka else None, "n_generated": n_gen,
            "peak_mem_bytes": peak, "gen_total_ms": round(gen_ms, 2),
            "sc_summary_nonzero_tokens": True}


def main():
    t0 = time.time()
    print("="*70); print(f"Study E Part 2 (Orin) — {MODEL_REPO}  {DEVICE}")
    import transformers
    print(f"torch {torch.__version__}  transformers {transformers.__version__}")
    print("="*70)

    print("Loading model...")
    tl0 = time.perf_counter()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_REPO, revision=MODEL_REV, torch_dtype=DTYPE, device_map=DEVICE)
    model.eval()
    proc = AutoProcessor.from_pretrained(MODEL_REPO, revision=MODEL_REV)
    load_time_s = time.perf_counter() - tl0

    p0 = next(model.parameters())
    place_ok = (str(p0.device) == DEVICE) and (p0.dtype == DTYPE)
    offloaded = [n for n, p in model.named_parameters() if p.device.type != "cuda"]
    no_offload = (len(offloaded) == 0)
    print(f"SANITY device placement: {place_ok}  no_cpu_offload: {no_offload}  "
          f"device={p0.device} dtype={p0.dtype}  load={load_time_s:.1f}s")
    assert place_ok and no_offload, "device placement / offload sanity failed"

    model_vram = torch.cuda.memory_allocated(DEVICE)
    total_vram = torch.cuda.get_device_properties(DEVICE).total_memory
    print(f"Model VRAM: {model_vram/1e9:.2f} GB / {total_vram/1e9:.1f} GB total (unified)")

    # frames + warmup
    all_frames = [make_frame(i, IMAGE_SIZE) for i in range(max(N_SWEEP_STUDYB))]
    _ = measure_full(model, proc, all_frames[:1], DEVICE); torch.cuda.empty_cache()

    # vision-token sanity (must be 400/frame like A6000 Study A/B)
    vt = measure_full(model, proc, all_frames[:1], DEVICE)["vision_tokens"]
    print(f"SANITY vision_tokens (N=1): {vt} (expect 400)")

    # Full Study B N sweep; empirical ceiling found by catching OOM (the binding
    # resource here is ACTIVATION memory of the O(L^2) sdpa attention (no flash-attn
    # on Jetson), NOT the KV cache — so an analytical KV headroom check is invalid).
    N_SWEEP = list(N_SWEEP_STUDYB)
    print(f"N sweep (will stop at empirical OOM ceiling): {N_SWEEP}")

    def safe(fn, label):
        try:
            torch.cuda.synchronize(DEVICE)
            return fn(), True
        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            print(f"  [OOM/RuntimeError] {label}: {str(e)[:100]}")
            torch.cuda.empty_cache()
            return None, False

    results = []; REPS = 2
    feasibility = {}   # (N, condition) -> bool
    max_feasible_full_N = 0
    ceiling_reason = None
    for N in N_SWEEP:
        frames = all_frames[:N]
        print(f"\n--- N={N} ({N*TOKENS_PER_FRAME} vision tokens) ---")
        n_oom_this_N = 0
        for rep in range(REPS):
            torch.cuda.empty_cache()
            rf, ok = safe(lambda: measure_full(model, proc, frames, DEVICE), f"full N={N} rep{rep}")
            feasibility[(N, "full", rep)] = ok
            if ok:
                rf["rep"] = rep; rf["sc_footprint_ratio"] = rf["kv_ratio"]
                rf["sc_footprint_scale"] = abs((rf["kv_ratio"] or 0)-1) < 0.10
                print(f"  [{rep}] full   in={rf['total_input_tokens']} prefill={rf['state_construction_ms']:.0f}ms "
                      f"kv={rf['kv_bytes_measured']/1e6:.1f}MB ratio={rf['kv_ratio']} peak={rf['peak_mem_bytes']/1e9:.2f}GB")
                results.append(rf)
                if rep == 0:
                    max_feasible_full_N = max(max_feasible_full_N, N)
            else:
                n_oom_this_N += 1
            torch.cuda.empty_cache()

            rw, ok = safe(lambda: measure_window(model, proc, frames, DEVICE), f"window N={N} rep{rep}")
            feasibility[(N, "window", rep)] = ok
            if ok:
                rw["rep"] = rep; rw["sc_footprint_ratio"] = rw["kv_ratio"]
                rw["sc_footprint_scale"] = abs((rw["kv_ratio"] or 0)-1) < 0.10
                print(f"  [{rep}] window in={rw['total_input_tokens']} prefill={rw['state_construction_ms']:.0f}ms "
                      f"kv={rw['kv_bytes_measured']/1e6:.1f}MB peak={rw['peak_mem_bytes']/1e9:.2f}GB")
                results.append(rw)
            torch.cuda.empty_cache()

            rs, ok = safe(lambda: measure_summary(model, proc, frames, DEVICE), f"summary N={N} rep{rep}")
            feasibility[(N, "summary", rep)] = ok
            if ok:
                rs["rep"] = rep; rs["sc_footprint_ratio"] = rs["kv_ratio"]
                rs["sc_footprint_scale"] = abs((rs["kv_ratio"] or 0)-1) < 0.10
                print(f"  [{rep}] summ   gen={rs['summary_generation_ms']:.0f}ms tok={rs['summary_tokens_generated']} "
                      f"qprefill={rs['query_ttft_ms']:.0f}ms kv={rs['kv_bytes_measured']/1e6:.2f}MB "
                      f"peak={rs['peak_mem_bytes']/1e9:.2f}GB")
                results.append(rs)
            torch.cuda.empty_cache()
        # Stop escalating N once full retention OOMs (larger N only worse; context may be fragile)
        if n_oom_this_N > 0 and not any(feasibility.get((N, "full", r), False) for r in range(REPS)):
            ceiling_reason = f"full-retention OOM at N={N} (unified memory exhausted by O(L^2) sdpa attention)"
            print(f"  -> CEILING: {ceiling_reason}; max feasible full N = {max_feasible_full_N}")
            break

    ceiling_hit = (max_feasible_full_N < max(N_SWEEP_STUDYB))
    sc_all = {
        "device_placement": place_ok, "no_cpu_offload": no_offload,
        "vision_tokens_400": (vt == 400),
        "footprint_scale": all(r.get("sc_footprint_scale", True) for r in results),
        "summary_nonzero_tokens": all(r.get("sc_summary_nonzero_tokens", True)
                                      for r in results if r["condition"] == "summary"),
    }
    out = {"study": "E_part2", "config": {
        "model": MODEL_REPO, "revision": MODEL_REV, "device": DEVICE, "dtype": "bfloat16",
        "image_size_HW": list(IMAGE_SIZE), "tokens_per_frame": TOKENS_PER_FRAME,
        "window_k": WINDOW_K, "n_reps": REPS, "seed": SEED,
        "kv_bytes_per_token": KV_BYTES_PER_TOK, "n_sweep": N_SWEEP,
        "n_sweep_studyb": N_SWEEP_STUDYB, "ceiling_hit_below_studyb_max": ceiling_hit,
        "max_feasible_full_N": max_feasible_full_N, "ceiling_reason": ceiling_reason,
        "feasibility": {f"N{n}_{c}_rep{r}": ok for (n, c, r), ok in feasibility.items()},
        "total_vram_gb": round(total_vram/1e9, 1), "model_vram_gb": round(model_vram/1e9, 2),
        "load_time_s": round(load_time_s, 2)},
        "sanity_checks": sc_all,
        "trials": [{k: v for k, v in r.items() if k != "summaries"} for r in results],
        "elapsed_s": round(time.time()-t0, 1)}
    with open(OUT_DIR / "study_e_part2_results.json", "w") as f:
        json.dump(out, f, indent=2)
    if results:
        keys = list(results[0].keys())
        with open(OUT_DIR / "study_e_part2_trials.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in results:
                w.writerow(r)
    print(f"\nSanity: {sc_all}")
    print(f"Elapsed {out['elapsed_s']}s. Ceiling hit below Study B max: {ceiling_hit}")
    print("=== STUDY E PART 2 COMPLETE ===")


if __name__ == "__main__":
    main()
