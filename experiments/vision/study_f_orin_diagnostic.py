#!/usr/bin/env python3
"""
Study F (Orin-only) — diagnostic: are Study E's two suspect numbers real device
properties or software-stack artifacts?

  (a) decode ~9.4 tok/s IDENTICAL for Qwen3-VL-4B and 8B  -> overhead vs bandwidth?
  (b) 53.4 GB peak for 6 frames of Qwen2.5-VL-7B state     -> where does the memory go?

Jetson AGX Orin (nesl-orin-3) ONLY. Writes ONLY under results/vision/study_f_orin/.

Part 1: forced 256-token decode (min_new=max_new=256, EOS suppressed), Instruct only,
        one fixed image+prompt, 5 reps. C1 dynamic cache / C2 static cache / C3 static+compile.
Part 2: Qwen2.5-VL-7B, Study B frames/conditions, phase-instrumented memory with a
        background system-RAM peak sampler (unified-memory cross-check vs torch counters).

Usage: python experiments/vision/study_f_orin_diagnostic.py --part both [--skip-compile]
"""
import argparse, gc, glob, json, os, threading, time
import numpy as np
import torch
from PIL import Image

OUT = "results/vision/study_f_orin"
IMG_DIR = "results/vision/study_c/study_c_images"
DTYPE = torch.bfloat16
DEV = "cuda:0"

REPO = {
    "qwen3vl4b": ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
    "qwen3vl8b": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
    "qwen25vl7b": ("Qwen/Qwen2.5-VL-7B-Instruct", "cc594898137f460bfe9f0759e9844b3ce807cfb5"),
}
# AGX Orin 64GB: 204.8 GB/s (256-bit LPDDR5 @ 3200 MT/s), NVIDIA Jetson AGX Orin series datasheet.
BANDWIDTH_GBs = 204.8
BANDWIDTH_SRC = "NVIDIA Jetson AGX Orin series datasheet: 256-bit LPDDR5 @ 3200 MT/s = 204.8 GB/s"
KV_PER_TOK = 57344  # Study B / Study E measured, Qwen2.5-VL-7B


def stack_info():
    import transformers
    try:
        import flash_attn; fa = flash_attn.__version__
    except Exception:
        fa = None
    return {"torch": torch.__version__, "cuda": torch.version.cuda,
            "transformers": transformers.__version__, "flash_attn_present": fa is not None,
            "flash_attn_version": fa, "gpu": torch.cuda.get_device_name(0),
            "total_mem_gb": round(torch.cuda.get_device_properties(0).total_memory/1e9, 1),
            "power_mode": open("/sys/devices/system/cpu/online").read().strip(),
            "gpu_locked_freq_hz": open("/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu/cur_freq").read().strip()}


def mem_used_mb():
    """System RAM used (MB) from /proc/meminfo — the unified-memory ground truth."""
    mt = ma = None
    for line in open("/proc/meminfo"):
        if line.startswith("MemTotal:"): mt = int(line.split()[1])
        elif line.startswith("MemAvailable:"): ma = int(line.split()[1])
    return (mt - ma)/1024.0 if (mt and ma) else None


class RamPeak:
    """Background sampler of system RAM used; captures the transient peak during a region."""
    def __init__(self, interval=0.02):
        self.interval = interval; self._run = False; self.peak = 0.0; self.base = mem_used_mb()
    def __enter__(self):
        self._run = True; self.peak = self.base = mem_used_mb()
        self.t = threading.Thread(target=self._loop, daemon=True); self.t.start(); return self
    def _loop(self):
        while self._run:
            m = mem_used_mb()
            if m and m > self.peak: self.peak = m
            time.sleep(self.interval)
    def __exit__(self, *a):
        self._run = False; self.t.join(timeout=1.0)
    def delta_gb(self):
        return round((self.peak - self.base)/1024.0, 2)
    def peak_gb(self):
        return round(self.peak/1024.0, 2)


def weight_bytes(model):
    total = sum(p.numel()*p.element_size() for p in model.parameters())
    lm = sum(p.numel()*p.element_size() for n, p in model.named_parameters() if "visual" not in n)
    return total, lm


# ── Part 1 ──────────────────────────────────────────────────────────────────
def part1(skip_compile):
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    res = {"machine": "orin", "device": DEV, "stack": stack_info(),
           "bandwidth_GBs": BANDWIDTH_GBs, "bandwidth_src": BANDWIDTH_SRC, "models": {}}
    img = Image.open(sorted(glob.glob(f"{IMG_DIR}/L2_*.png"))[0]).convert("RGB")
    PROMPT = "Describe this image in detail, listing everything you can see."
    N_TOK = 256

    for slug in ["qwen3vl4b", "qwen3vl8b"]:
        repo, rev = REPO[slug]
        print(f"\n{'='*60}\nPART1 {slug} ({repo})", flush=True)
        proc = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=True)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            repo, revision=rev, torch_dtype=DTYPE, device_map=DEV, trust_remote_code=True)
        model.eval()
        p0 = next(model.parameters())
        attn = getattr(model.config, "_attn_implementation", "?")
        attn_text = getattr(getattr(model.config, "text_config", None), "_attn_implementation", None)
        tot_b, lm_b = weight_bytes(model)
        roof_total = BANDWIDTH_GBs*1e9/tot_b
        roof_lm = BANDWIDTH_GBs*1e9/lm_b
        assert p0.dtype == DTYPE and str(p0.device) == DEV, "bf16/device sanity failed"
        md = {"repo": repo, "attn_impl_asserted": attn, "attn_impl_text": attn_text,
              "param_device": str(p0.device), "param_dtype": str(p0.dtype),
              "weight_bytes_total": tot_b, "weight_bytes_lm_only": lm_b,
              "roofline_tps_total_weights": round(roof_total, 1),
              "roofline_tps_lm_only": round(roof_lm, 1), "conditions": {}}
        print(f"  attn={attn} text_attn={attn_text} wt_total={tot_b/1e9:.2f}GB wt_lm={lm_b/1e9:.2f}GB "
              f"roof_total={roof_total:.1f} roof_lm={roof_lm:.1f} tok/s", flush=True)

        msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": PROMPT}]}]
        txt = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = proc(text=[txt], images=[img], return_tensors="pt").to(DEV)
        n_in = int(inputs.input_ids.shape[1])
        md["n_input"] = n_in

        def one(cache_impl, gm):
            # prefill / TTFT
            torch.cuda.synchronize(); t0 = time.perf_counter()
            with torch.no_grad():
                gm.generate(**inputs, min_new_tokens=1, max_new_tokens=1, do_sample=False,
                            cache_implementation=cache_impl, pad_token_id=proc.tokenizer.eos_token_id)
            torch.cuda.synchronize(); prefill = (time.perf_counter()-t0)*1000
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize(); t0 = time.perf_counter()
            with torch.no_grad():
                out = gm.generate(**inputs, min_new_tokens=N_TOK, max_new_tokens=N_TOK, do_sample=False,
                                  cache_implementation=cache_impl, pad_token_id=proc.tokenizer.eos_token_id)
            torch.cuda.synchronize(); total = (time.perf_counter()-t0)*1000
            n_gen = int(out.shape[1]) - n_in
            assert n_gen == N_TOK, f"expected {N_TOK} got {n_gen}"
            peak = torch.cuda.max_memory_allocated()
            return {"prefill_ms": round(prefill,1), "decode_ms": round(total-prefill,1),
                    "decode_tps": round((N_TOK-1)/((total-prefill)/1000),2),
                    "peak_gb": round(peak/1e9,3), "n_gen": n_gen}

        for cond, ci in [("C1_dynamic", None), ("C2_static", "static")]:
            try:
                one(ci, model)  # warmup (not recorded)
                samples = [one(ci, model) for _ in range(5)]
                dt = [s["decode_tps"] for s in samples]
                md["conditions"][cond] = {"samples": samples,
                    "decode_tps_median": round(float(np.median(dt)), 2),
                    "decode_tps_cv": round(float(np.std(dt)/np.mean(dt)), 4),
                    "pct_roofline_total": round(100*np.median(dt)/roof_total, 1),
                    "pct_roofline_lm": round(100*np.median(dt)/roof_lm, 1)}
                print(f"  {cond}: decode_tps={md['conditions'][cond]['decode_tps_median']} "
                      f"(%roof_total={md['conditions'][cond]['pct_roofline_total']} "
                      f"%roof_lm={md['conditions'][cond]['pct_roofline_lm']}) cv={md['conditions'][cond]['decode_tps_cv']}", flush=True)
            except Exception as e:
                md["conditions"][cond] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                print(f"  {cond} ERROR: {e}", flush=True)

        if not skip_compile:
            try:
                model.generation_config.cache_implementation = "static"
                cm = torch.compile(model, mode="reduce-overhead", fullgraph=True)
                t0 = time.perf_counter(); first = one("static", cm); first_wall = (time.perf_counter()-t0)
                steady = [one("static", cm) for _ in range(5)]
                dt = [s["decode_tps"] for s in steady]
                md["conditions"]["C3_static_compile"] = {"first_call_wall_s": round(first_wall,1),
                    "first_call": first, "steady_samples": steady,
                    "decode_tps_steady_median": round(float(np.median(dt)),2),
                    "pct_roofline_total": round(100*np.median(dt)/roof_total,1),
                    "pct_roofline_lm": round(100*np.median(dt)/roof_lm,1)}
                print(f"  C3: steady decode_tps={float(np.median(dt)):.2f} first_call={first_wall:.0f}s", flush=True)
            except Exception as e:
                md["conditions"]["C3_static_compile"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
                print(f"  C3 ERROR (recorded, continuing): {type(e).__name__}: {str(e)[:150]}", flush=True)
        else:
            md["conditions"]["C3_static_compile"] = {"skipped": True}

        res["models"][slug] = md
        del model; gc.collect(); torch.cuda.empty_cache()

    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/orin_part1.json", "w").write(json.dumps(res, indent=2, default=str))
    print(f"\nPart 1 -> {OUT}/orin_part1.json")


# ── Part 2 ──────────────────────────────────────────────────────────────────
def make_frame(i, size=(560, 560)):  # identical to Study B
    H, W = size
    rng = np.random.default_rng(42 + i*1000)
    arr = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    tint = np.zeros((H, W, 3), dtype=np.uint8); tint[:, :, i % 3] = 100
    return Image.fromarray(np.clip(np.array(Image.fromarray(arr)).astype(int)//2 + tint, 0, 255).astype(np.uint8))


def part2():
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
    repo, rev = REPO["qwen25vl7b"]
    res = {"machine": "orin", "device": DEV, "stack": stack_info(), "unified_memory": True,
           "unified_caveat": ("Jetson LPDDR5 is unified with CPU RAM. torch.cuda.max_memory_allocated/"
                              "reserved track the CUDA caching allocator's device-visible allocations, "
                              "not a discrete VRAM pool. Cross-checked against /proc/meminfo system-RAM "
                              "peak (ram_peak_delta_gb) sampled at 20 ms during each phase."),
           "kv_bytes_per_token": KV_PER_TOK, "N": {}}
    print(f"\n{'='*60}\nPART2 {repo}", flush=True)
    proc = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=True)
    ram_before_load = mem_used_mb()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        repo, revision=rev, torch_dtype=DTYPE, device_map=DEV)
    model.eval()
    p0 = next(model.parameters())
    assert p0.dtype == DTYPE and str(p0.device) == DEV
    attn = getattr(model.config, "_attn_implementation", "?")
    vis_attn = getattr(getattr(model.config, "vision_config", None), "_attn_implementation", None)
    vision_tower = getattr(model, "visual", None) or model.model.visual  # 5.10.2: model.model.visual
    tot_b, lm_b = weight_bytes(model)
    torch.cuda.synchronize()
    torch_after_load = torch.cuda.memory_allocated()
    ram_after_load = mem_used_mb()
    res.update({"attn_impl_asserted": attn, "vision_attn_impl": vis_attn,
                "weight_bytes_total": tot_b,
                "torch_mem_after_load_gb": round(torch_after_load/1e9, 2),
                "ram_used_after_load_delta_gb": round((ram_after_load-ram_before_load)/1024, 2)})
    print(f"  attn={attn} vision_attn={vis_attn} weights={tot_b/1e9:.2f}GB "
          f"torch_after_load={torch_after_load/1e9:.2f}GB ram_delta_load={(ram_after_load-ram_before_load)/1024:.2f}GB", flush=True)

    QUERY = "What objects are visible across these images? List the three most prominent."
    for N in [1, 3, 6, 12]:
        frames = [make_frame(i) for i in range(N)]
        msgs = [{"role": "user", "content": [{"type": "image", "image": f} for f in frames] + [{"type": "text", "text": QUERY}]}]
        txt = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = proc(text=[txt], images=frames, return_tensors="pt")
        grid = inp.get("image_grid_thw")
        total_patches = int(grid.prod(dim=1).sum()) if grid is not None else None
        n_in = int(inp["input_ids"].shape[1])
        pv_shape = list(inp["pixel_values"].shape) if "pixel_values" in inp else None
        inpd = {k: v.to(DEV) for k, v in inp.items() if isinstance(v, torch.Tensor)}
        e = {"input_tokens": n_in, "total_patches_into_vision_tower": total_patches,
             "pixel_values_shape": pv_shape, "vision_encoded_in_single_batched_call": True,
             "kv_bytes_analytical": n_in*KV_PER_TOK}

        # Phase A: vision tower only
        try:
            torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize()
            with RamPeak() as rp, torch.no_grad():
                pv = inpd["pixel_values"].type(DTYPE)
                emb = vision_tower(pv, grid_thw=inpd["image_grid_thw"])
                torch.cuda.synchronize()
            e["vision_only_torch_peak_alloc_gb"] = round(torch.cuda.max_memory_allocated()/1e9, 2)
            e["vision_only_torch_peak_reserved_gb"] = round(torch.cuda.max_memory_reserved()/1e9, 2)
            e["vision_only_ram_peak_delta_gb"] = rp.delta_gb()
            emb_t = getattr(emb, "last_hidden_state", emb)
            e["vision_embed_shape"] = list(emb_t.shape) if hasattr(emb_t, "shape") else str(type(emb).__name__)
            del emb, pv; torch.cuda.empty_cache()
        except (torch.cuda.OutOfMemoryError, RuntimeError) as ex:
            e["vision_only_error"] = f"{type(ex).__name__}: {str(ex)[:120]}"; torch.cuda.empty_cache()

        # Phase B: full prefill (whole call peak)
        try:
            torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize()
            with RamPeak() as rp, torch.no_grad():
                fwd = model(**inpd, use_cache=True, return_dict=True)
                torch.cuda.synchronize()
            full_alloc = torch.cuda.max_memory_allocated()
            e["full_call_torch_peak_alloc_gb"] = round(full_alloc/1e9, 2)
            e["full_call_torch_peak_reserved_gb"] = round(torch.cuda.max_memory_reserved()/1e9, 2)
            e["full_call_ram_peak_delta_gb"] = rp.delta_gb()
            pkv = fwd.past_key_values; kb = 0
            if hasattr(pkv, "key_cache"):
                for k, v in zip(pkv.key_cache, pkv.value_cache):
                    for t in (k, v):
                        if t is not None: kb += t.numel()*t.element_size()
            e["kv_bytes_measured"] = kb
            e["attrib_weights_gb"] = round(torch_after_load/1e9, 2)
            e["attrib_kv_gb"] = round(kb/1e9, 3)
            e["attrib_vision_torch_peak_gb"] = e.get("vision_only_torch_peak_alloc_gb")
            e["attrib_full_torch_peak_gb"] = round(full_alloc/1e9, 2)
            e["attrib_unaccounted_gb"] = round((full_alloc - torch_after_load - kb)/1e9, 2)
            del fwd; torch.cuda.empty_cache()
            print(f"  N={N} patches={total_patches} in={n_in} vis_peak={e.get('vision_only_torch_peak_alloc_gb')}GB "
                  f"full_peak={e['full_call_torch_peak_alloc_gb']}GB ram_delta={e['full_call_ram_peak_delta_gb']}GB "
                  f"kv={kb/1e6:.0f}MB unacc={e['attrib_unaccounted_gb']}GB", flush=True)
        except (torch.cuda.OutOfMemoryError, RuntimeError) as ex:
            e["full_call_error"] = f"{type(ex).__name__}: {str(ex)[:120]}"
            print(f"  N={N} FULL-CALL OOM/err: {str(ex)[:80]}", flush=True)
            torch.cuda.empty_cache()

        res["N"][str(N)] = e
        torch.cuda.empty_cache(); gc.collect()

    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/orin_part2.json", "w").write(json.dumps(res, indent=2, default=str))
    print(f"\nPart 2 -> {OUT}/orin_part2.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="both", choices=["1", "2", "both"])
    ap.add_argument("--skip-compile", action="store_true")
    args = ap.parse_args()
    print(f"Study F Orin diagnostic — part={args.part}")
    if args.part in ("1", "both"): part1(args.skip_compile)
    if args.part in ("2", "both"): part2()


if __name__ == "__main__":
    main()
