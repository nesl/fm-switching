#!/usr/bin/env python3
"""
Study A: Does scene content change the cost of a frame?
Research question: For a fixed encoder configuration, does image content change
(a) vision token count, (b) prefill latency, (c) KV cache bytes, (d) output token count?

CODE INSPECTION FINDING (recorded before any measurements run):
  Token count is determined by smart_resize(H, W, factor=patch_size*merge_size) then
  grid_h=H_resized//patch_size, grid_w=W_resized//patch_size,
  num_vision_tokens = grid_h*grid_w // merge_size**2.
  smart_resize is a deterministic arithmetic function of (H, W) with no content dependence.
  image_grid_thw = [1, grid_h, grid_w] for every image at the same pixel dimensions.
  No content-adaptive branching exists anywhere in the image processing pipeline.
  CONCLUSION: H1 is confirmed by code inspection for metric (a).
  H2 is falsified by code inspection.
  Metrics (b), (c), (d) are measured empirically.
"""
import csv
import json
import math
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

MODEL7B_PATH = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots/cc594898137f460bfe9f0759e9844b3ce807cfb5"
MODEL3B_PATH = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-3B-Instruct/snapshots"

DEVICE = "cuda:1"   # A6000 (GPU 1)
DTYPE = torch.bfloat16
N_REPS = 3
TARGET_SIZE = (560, 560)   # H×W; smart_resize will keep this exact (divisible by 28)
QUERY = "What is the main color in this image? Answer in one word."
MAX_NEW_TOKENS = 10

OUT_DIR = Path("results/vision/study_a")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Analytical KV bytes per token for Qwen2.5-VL-7B text LM
# num_hidden_layers=28, num_kv_heads=4, head_dim=3584/28=128, bfloat16=2B
KV_BYTES_PER_TOKEN_ANALYTICAL = 2 * 4 * 128 * 28 * 2   # = 57344


# ── Image generation ──────────────────────────────────────────────────────────
def make_images(size):
    H, W = size
    imgs = {}

    # 1. Flat uniform (black)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    imgs["flat_black"] = Image.fromarray(arr)

    # 2. Flat uniform (red)
    arr = np.zeros((H, W, 3), dtype=np.uint8); arr[:, :, 0] = 200
    imgs["flat_red"] = Image.fromarray(arr)

    # 3. Linear gradient (horizontal)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    arr[:, :, 0] = np.tile(np.linspace(0, 255, W, dtype=np.uint8), (H, 1))
    arr[:, :, 2] = np.tile(np.linspace(255, 0, W, dtype=np.uint8), (H, 1))
    imgs["gradient"] = Image.fromarray(arr)

    # 4. Simple geometric — concentric circles
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2
    for r in range(10, min(W, H) // 2, 30):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 200), width=3)
    imgs["circles"] = img

    # 5. Checkerboard (dense regular texture)
    tile = 14   # one patch = 14 px
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(H):
        for j in range(W):
            if ((i // tile) + (j // tile)) % 2 == 0:
                arr[i, j] = [255, 255, 255]
    imgs["checkerboard"] = Image.fromarray(arr)

    # 6. Fine stripes (vertical, 2px period)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    arr[:, 1::2] = [255, 255, 255]
    imgs["fine_stripes"] = Image.fromarray(arr)

    # 7. Random noise (high entropy)
    rng = np.random.default_rng(SEED)
    arr = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    imgs["random_noise"] = Image.fromarray(arr)

    # 8. Blurred random noise (low-frequency noise)
    from PIL import ImageFilter
    imgs["blurred_noise"] = imgs["random_noise"].filter(ImageFilter.GaussianBlur(radius=15))

    # 9. Sparse dots on white
    arr = np.full((H, W, 3), 255, dtype=np.uint8)
    rng2 = np.random.default_rng(SEED + 1)
    ys = rng2.integers(0, H, 50)
    xs = rng2.integers(0, W, 50)
    for y, x in zip(ys, xs):
        arr[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = [0, 0, 0]
    imgs["sparse_dots"] = Image.fromarray(arr)

    # 10–12: Natural photographs (resized to target)
    natural = {
        "photo_worker": Path("/home/pragya/Desktop/worker.jpeg"),
        "photo_park":   Path("/home/pragya/Desktop/park.jpeg"),
        "photo_room":   Path("/home/pragya/Desktop/livingroom.jpg"),
    }
    for name, path in natural.items():
        if path.exists():
            img = Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
            imgs[name] = img
        else:
            print(f"WARNING: {path} not found, skipping")

    return imgs


def jpeg_entropy_proxy(img: Image.Image) -> tuple[int, float]:
    """Return (jpeg_bytes_at_q85, shannon_entropy_grayscale_histogram)."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    jpeg_bytes = buf.tell()

    gray = np.array(img.convert("L"))
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    hist = hist.astype(float)
    hist = hist[hist > 0]
    p = hist / hist.sum()
    entropy = float(-np.sum(p * np.log2(p)))
    return jpeg_bytes, entropy


# ── Analytical vision token count check ──────────────────────────────────────
def analytical_vision_tokens(H, W, patch_size=14, merge_size=2,
                              min_pixels=56*56, max_pixels=28*28*1280):
    """Compute expected vision token count from dimensions alone."""
    factor = patch_size * merge_size  # = 28
    h_bar = round(H / factor) * factor
    w_bar = round(W / factor) * factor
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((H * W) / max_pixels)
        h_bar = max(factor, math.floor(H / beta / factor) * factor)
        w_bar = max(factor, math.floor(W / beta / factor) * factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (H * W))
        h_bar = math.ceil(H * beta / factor) * factor
        w_bar = math.ceil(W * beta / factor) * factor
    grid_h = h_bar // patch_size
    grid_w = w_bar // patch_size
    return grid_h * grid_w // (merge_size ** 2), h_bar, w_bar


# ── Measurement helpers ───────────────────────────────────────────────────────
def get_past_kv_bytes(past_key_values):
    """Sum all tensor bytes in a DynamicCache or tuple-of-tuples KV cache."""
    total = 0
    if past_key_values is None:
        return 0
    # DynamicCache (transformers >= 4.38) or tuple of tuples
    if hasattr(past_key_values, "key_cache"):
        for k, v in zip(past_key_values.key_cache, past_key_values.value_cache):
            if k is not None:
                total += k.nbytes() if hasattr(k, "nbytes") else k.numel() * k.element_size()
            if v is not None:
                total += v.nbytes() if hasattr(v, "nbytes") else v.numel() * v.element_size()
    else:
        for layer in past_key_values:
            for t in layer:
                if t is not None:
                    total += t.numel() * t.element_size()
    return total


def timed_generate(model, inputs, max_new_tokens):
    """Run measurements: separate prefill forward pass, then full generate."""
    import time as _time

    input_len = inputs["input_ids"].shape[1]

    with torch.no_grad():
        # --- Prefill measurement: one forward pass, use_cache=True ---
        torch.cuda.synchronize(DEVICE)
        t0 = _time.perf_counter()
        fwd_out = model(
            **inputs,
            use_cache=True,
            return_dict=True,
        )
        torch.cuda.synchronize(DEVICE)
        t1 = _time.perf_counter()
        prefill_ms = (t1 - t0) * 1000.0

        past_kv = fwd_out.past_key_values
        kv_bytes_measured = get_past_kv_bytes(past_kv)
        del fwd_out, past_kv

        # --- Full generate for output tokens and generation latency ---
        torch.cuda.synchronize(DEVICE)
        tg0 = _time.perf_counter()
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            use_cache=True,
        )
        torch.cuda.synchronize(DEVICE)
        tg1 = _time.perf_counter()

    total_gen_ms = (tg1 - tg0) * 1000.0
    # gen_ms = decode-only portion (subtract prefill from total)
    gen_ms = max(0.0, total_gen_ms - prefill_ms)

    return out, prefill_ms, gen_ms, kv_bytes_measured, None


def run_one(model, processor, img_or_none, query, max_new_tokens, device):
    """Prepare inputs, run timed_generate, return record dict."""
    if img_or_none is not None:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": img_or_none},
            {"type": "text", "text": query},
        ]}]
    else:
        messages = [{"role": "user", "content": [{"type": "text", "text": query}]}]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    if img_or_none is not None:
        inputs = processor(text=[text], images=[img_or_none], return_tensors="pt")
    else:
        inputs = processor(text=[text], return_tensors="pt")

    inputs = {k: v.to(device) for k, v in inputs.items()
              if isinstance(v, torch.Tensor)}

    # Vision token count from image_grid_thw
    vision_tokens = 0
    if "image_grid_thw" in inputs:
        thw = inputs["image_grid_thw"]
        merge_size = processor.image_processor.merge_size
        vision_tokens = int(thw.prod() // (merge_size ** 2))
    total_input_tokens = int(inputs["input_ids"].shape[1])

    out, prefill_ms, gen_ms, kv_bytes_measured, past_kv = timed_generate(
        model, inputs, max_new_tokens
    )

    # Analytical KV bytes for full sequence
    kv_bytes_analytical = total_input_tokens * KV_BYTES_PER_TOKEN_ANALYTICAL

    # Output token count
    input_len = inputs["input_ids"].shape[1]
    n_generated = int(out.shape[1]) - input_len

    # Peak VRAM
    peak_vram = torch.cuda.max_memory_allocated(device)
    torch.cuda.reset_peak_memory_stats(device)

    return {
        "vision_tokens": vision_tokens,
        "total_input_tokens": total_input_tokens,
        "prefill_ms": round(prefill_ms, 2),
        "gen_ms": round(gen_ms, 2),
        "kv_bytes_measured": kv_bytes_measured,
        "kv_bytes_analytical": kv_bytes_analytical,
        "n_generated": n_generated,
        "peak_vram_bytes": peak_vram,
    }


def load_7b():
    print("Loading Qwen2.5-VL-7B on", DEVICE)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL7B_PATH, torch_dtype=DTYPE, device_map=DEVICE
    )
    model.eval()
    proc = AutoProcessor.from_pretrained(MODEL7B_PATH)
    return model, proc


def load_3b():
    snap = list(Path(MODEL3B_PATH).iterdir())[0]
    print("Loading Qwen2.5-VL-3B on", DEVICE, "from", snap)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        snap, torch_dtype=DTYPE, device_map=DEVICE
    )
    model.eval()
    proc = AutoProcessor.from_pretrained(snap)
    return model, proc


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 70)
    print("Study A: Does scene content change the cost of a frame?")
    print("CODE INSPECTION FINDING:")
    print("  Token count is a pure function of pixel dimensions (H, W).")
    print("  H1 confirmed by inspection; H2 falsified by inspection.")
    print("  Measuring (b) prefill latency, (c) KV bytes, (d) output tokens.")
    print("=" * 70)

    # Analytical check for TARGET_SIZE
    n_vision_analytical, h_bar, w_bar = analytical_vision_tokens(*TARGET_SIZE)
    print(f"\nTarget size: {TARGET_SIZE[0]}×{TARGET_SIZE[1]} px")
    print(f"smart_resize → {h_bar}×{w_bar} px")
    print(f"Analytical vision tokens: {n_vision_analytical}")
    print(f"Analytical KV bytes per sequence token: {KV_BYTES_PER_TOKEN_ANALYTICAL}")

    # Generate images
    print("\nGenerating controlled images...")
    images = make_images(TARGET_SIZE)
    print(f"  {len(images)} images prepared: {list(images.keys())}")

    # Complexity proxies
    print("\nComplexity proxies (JPEG bytes @ q85, Shannon entropy):")
    complexity = {}
    for name, img in images.items():
        jb, ent = jpeg_entropy_proxy(img)
        complexity[name] = {"jpeg_bytes": jb, "entropy_bits": round(ent, 4)}
        print(f"  {name:20s}: jpeg={jb:7d} B, entropy={ent:.4f} bits")

    # Save images for inspection
    for name, img in images.items():
        img.save(OUT_DIR / f"img_{name}.png")

    # Load 7B model
    model7b, proc7b = load_7b()

    # Warmup (not recorded)
    print("\nWarming up...")
    first_img = list(images.values())[0]
    _ = run_one(model7b, proc7b, first_img, QUERY, MAX_NEW_TOKENS, DEVICE)
    torch.cuda.empty_cache()
    print("  Warmup complete.")

    # Sanity check: pixel_values shape identical across all images
    print("\nSANITY CHECK 1: pixel_values shape identical across images...")
    shapes_seen = set()
    for name, img in images.items():
        messages = [{"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": QUERY},
        ]}]
        text = proc7b.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = proc7b(text=[text], images=[img], return_tensors="pt")
        shapes_seen.add(tuple(inputs["pixel_values"].shape))
        thw = inputs["image_grid_thw"]
    shape_check = len(shapes_seen) == 1
    print(f"  Unique pixel_values shapes: {shapes_seen}")
    print(f"  PASS: {shape_check}" if shape_check else f"  FAIL: {shapes_seen}")

    # Sanity check: text-only control produces zero vision tokens
    print("\nSANITY CHECK 2: text-only control vision token count...")
    text_only_inputs = proc7b(
        text=[proc7b.apply_chat_template(
            [{"role": "user", "content": [{"type": "text", "text": QUERY}]}],
            tokenize=False, add_generation_prompt=True
        )],
        return_tensors="pt"
    )
    text_only_vision_tokens = 0
    if "image_grid_thw" in text_only_inputs:
        thw = text_only_inputs["image_grid_thw"]
        merge_size = proc7b.image_processor.merge_size
        text_only_vision_tokens = int(thw.prod() // (merge_size ** 2))
    sc2_pass = (text_only_vision_tokens == 0)
    print(f"  Text-only vision tokens: {text_only_vision_tokens}")
    print(f"  PASS: {sc2_pass}" if sc2_pass else "  FAIL: text-only has vision tokens")

    # Text-only baseline measurement
    print("\nRunning text-only baseline (3 reps)...")
    text_only_recs = []
    for rep in range(N_REPS):
        rec = run_one(model7b, proc7b, None, QUERY, MAX_NEW_TOKENS, DEVICE)
        rec["image_name"] = "text_only"
        rec["rep"] = rep
        rec["is_baseline"] = True
        text_only_recs.append(rec)
        print(f"  rep {rep}: tokens={rec['total_input_tokens']} prefill={rec['prefill_ms']}ms out={rec['n_generated']}")

    # Main measurement matrix: 12 images × 3 reps
    print(f"\nMain matrix: {len(images)} images × {N_REPS} reps each...")
    all_recs = []
    vision_token_counts = {}

    for name, img in images.items():
        recs_this = []
        for rep in range(N_REPS):
            torch.cuda.empty_cache()
            rec = run_one(model7b, proc7b, img, QUERY, MAX_NEW_TOKENS, DEVICE)
            rec["image_name"] = name
            rec["rep"] = rep
            rec["is_baseline"] = False
            rec["jpeg_bytes"] = complexity[name]["jpeg_bytes"]
            rec["entropy_bits"] = complexity[name]["entropy_bits"]
            recs_this.append(rec)
            all_recs.append(rec)

        vision_token_counts[name] = recs_this[0]["vision_tokens"]
        med_prefill = np.median([r["prefill_ms"] for r in recs_this])
        med_gen = np.median([r["gen_ms"] for r in recs_this])
        med_kv = np.median([r["kv_bytes_measured"] for r in recs_this])
        print(f"  {name:20s}: vtok={recs_this[0]['vision_tokens']} "
              f"prefill={med_prefill:.1f}ms gen={med_gen:.1f}ms "
              f"kv_meas={med_kv/1e6:.1f}MB "
              f"out={recs_this[0]['n_generated']}")

    # SANITY CHECK 3: repeat control variance
    print("\nSANITY CHECK 3: repeat control variance (noise floor)...")
    repeat_image = list(images.values())[0]
    repeat_recs = []
    for rep in range(N_REPS):
        torch.cuda.empty_cache()
        rec = run_one(model7b, proc7b, repeat_image, QUERY, MAX_NEW_TOKENS, DEVICE)
        repeat_recs.append(rec)
    prefill_vals = [r["prefill_ms"] for r in repeat_recs]
    prefill_var = max(prefill_vals) - min(prefill_vals)
    print(f"  Repeat-control prefill latencies: {prefill_vals}")
    print(f"  Spread (max-min): {prefill_var:.1f} ms (this is the noise floor)")

    # SANITY CHECK 4: measured vs analytical KV bytes
    print("\nSANITY CHECK 4: measured vs analytical KV bytes...")
    sc4_pass = True
    for rec in all_recs[:len(images)]:   # first rep per image
        ratio = rec["kv_bytes_measured"] / rec["kv_bytes_analytical"] if rec["kv_bytes_analytical"] > 0 else 0
        ok = abs(ratio - 1) < 0.10
        if not ok:
            sc4_pass = False
            print(f"  FAIL {rec['image_name']}: ratio={ratio:.3f} "
                  f"measured={rec['kv_bytes_measured']} analytical={rec['kv_bytes_analytical']}")
    if sc4_pass:
        sample = all_recs[0]
        ratio = sample["kv_bytes_measured"] / sample["kv_bytes_analytical"]
        print(f"  PASS: ratio={ratio:.3f} for all images (within 10%)")
    else:
        print("  STOP: analytical/measured KV bytes disagree by >10% — see above.")

    # SANITY CHECK 3b: vision token count identical across images
    print("\nSANITY CHECK (H1 empirical verify): vision tokens identical across images?")
    vtok_set = set(vision_token_counts.values())
    sc_h1 = len(vtok_set) == 1
    print(f"  Unique vision token counts: {vtok_set}")
    print(f"  Expected analytical: {n_vision_analytical}")
    print(f"  PASS (H1 confirmed empirically): {sc_h1}" if sc_h1 else
          f"  FAIL (unexpected variation): {vision_token_counts}")

    # Cross-model check: Qwen2.5-VL-3B, token count only
    print("\nCross-model check: Qwen2.5-VL-3B token count only...")
    del model7b
    torch.cuda.empty_cache()
    model3b, proc3b = load_3b()

    vtok_3b = {}
    for name, img in images.items():
        messages = [{"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": QUERY},
        ]}]
        text = proc3b.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = proc3b(text=[text], images=[img], return_tensors="pt")
        vision_tokens = 0
        if "image_grid_thw" in inputs:
            thw = inputs["image_grid_thw"]
            merge_size = proc3b.image_processor.merge_size
            vision_tokens = int(thw.prod() // (merge_size ** 2))
        vtok_3b[name] = vision_tokens

    vtok_3b_set = set(vtok_3b.values())
    print(f"  Unique 3B vision token counts: {vtok_3b_set}")
    print(f"  7B: {set(vision_token_counts.values())}  3B: {vtok_3b_set}")
    cross_model_match = vtok_3b_set == set(vision_token_counts.values())
    print(f"  Same as 7B: {cross_model_match}")

    del model3b
    torch.cuda.empty_cache()

    # Assemble complete results
    print("\nSummary of all recs...")
    all_recs_with_baseline = text_only_recs + all_recs

    # Compute per-image medians for the main table
    summary = {}
    for rec in all_recs:
        n = rec["image_name"]
        if n not in summary:
            summary[n] = {"prefill_ms": [], "gen_ms": [], "kv_bytes_measured": [],
                          "n_generated": [], "vision_tokens": rec["vision_tokens"],
                          "jpeg_bytes": rec["jpeg_bytes"], "entropy_bits": rec["entropy_bits"]}
        summary[n]["prefill_ms"].append(rec["prefill_ms"])
        summary[n]["gen_ms"].append(rec["gen_ms"])
        summary[n]["kv_bytes_measured"].append(rec["kv_bytes_measured"])
        summary[n]["n_generated"].append(rec["n_generated"])

    print(f"\n{'image':22s} {'vtok':>6} {'prefill_med':>12} {'prefill_rng':>12} "
          f"{'kv_MB_med':>10} {'n_out_med':>9} {'jpeg_kB':>8} {'entropy':>8}")
    print("-" * 100)
    for name, s in summary.items():
        med_p = np.median(s["prefill_ms"])
        rng_p = max(s["prefill_ms"]) - min(s["prefill_ms"])
        med_k = np.median(s["kv_bytes_measured"]) / 1e6
        med_o = np.median(s["n_generated"])
        print(f"  {name:20s} {s['vision_tokens']:>6} {med_p:>12.1f} {rng_p:>12.1f} "
              f"{med_k:>10.1f} {med_o:>9.1f} {s['jpeg_bytes']//1000:>8} {s['entropy_bits']:>8.4f}")

    # Cross-image prefill spread
    all_prefill_meds = [np.median(s["prefill_ms"]) for s in summary.values()]
    prefill_across = max(all_prefill_meds) - min(all_prefill_meds)
    print(f"\nCross-image prefill spread (max−min of medians): {prefill_across:.1f} ms")
    print(f"Repeat-control noise floor: {prefill_var:.1f} ms")
    if prefill_across <= prefill_var:
        print("  Cross-image prefill variation does not exceed noise floor — content has no detectable effect on latency.")
    else:
        print(f"  Cross-image prefill variation exceeds noise floor by {prefill_across - prefill_var:.1f} ms.")

    # Build full result structure
    results = {
        "study": "A",
        "research_question": "Does scene content change the cost of a frame?",
        "code_inspection": {
            "finding": "H1 confirmed: token count is a pure function of input pixel dimensions (H, W). "
                       "smart_resize is deterministic arithmetic; image_grid_thw = [1, H//patch, W//patch]. "
                       "No content-adaptive branching. H2 falsified by inspection.",
            "analytical_vision_tokens_at_560x560": n_vision_analytical,
            "analytical_resized_hw": [h_bar, w_bar],
            "kv_bytes_per_token_analytical": KV_BYTES_PER_TOKEN_ANALYTICAL,
            "kv_config": {"num_hidden_layers": 28, "num_kv_heads": 4, "head_dim": 128,
                          "dtype_bytes": 2, "formula": "2 * 4 * 128 * 28 * 2"},
        },
        "config": {
            "model": "Qwen2.5-VL-7B-Instruct", "device": DEVICE, "dtype": "bfloat16",
            "target_image_size_HW": list(TARGET_SIZE),
            "query": QUERY, "max_new_tokens": MAX_NEW_TOKENS,
            "n_reps": N_REPS, "seed": SEED,
        },
        "sanity_checks": {
            "sc1_pixel_values_shape_identical": shape_check,
            "sc1_unique_shapes": [list(s) for s in shapes_seen],
            "sc2_text_only_zero_vision_tokens": sc2_pass,
            "sc2_text_only_vision_token_count": text_only_vision_tokens,
            "sc3_repeat_control_prefill_spread_ms": round(prefill_var, 2),
            "sc3_repeat_control_values_ms": prefill_vals,
            "sc4_kv_bytes_ratio_within_10pct": sc4_pass,
            "sc_h1_empirical_vision_token_unique": sc_h1,
            "sc_h1_unique_token_counts": list(vtok_set),
        },
        "cross_model_check": {
            "model": "Qwen2.5-VL-3B-Instruct",
            "vision_tokens_per_image": vtok_3b,
            "unique_token_counts": list(vtok_3b_set),
            "matches_7b": cross_model_match,
        },
        "complexity_proxies": complexity,
        "per_image_summary": {
            name: {
                "vision_tokens": s["vision_tokens"],
                "prefill_ms_median": round(float(np.median(s["prefill_ms"])), 2),
                "prefill_ms_min": round(float(min(s["prefill_ms"])), 2),
                "prefill_ms_max": round(float(max(s["prefill_ms"])), 2),
                "kv_bytes_measured_median": int(np.median(s["kv_bytes_measured"])),
                "n_generated_median": int(np.median(s["n_generated"])),
                "jpeg_bytes": s["jpeg_bytes"],
                "entropy_bits": s["entropy_bits"],
            }
            for name, s in summary.items()
        },
        "text_only_baseline": {
            "prefill_ms_median": round(float(np.median([r["prefill_ms"] for r in text_only_recs])), 2),
            "prefill_ms_values": [r["prefill_ms"] for r in text_only_recs],
            "total_input_tokens_median": int(np.median([r["total_input_tokens"] for r in text_only_recs])),
            "n_generated_median": int(np.median([r["n_generated"] for r in text_only_recs])),
        },
        "cross_image_prefill_spread_ms": round(prefill_across, 2),
        "repeat_control_noise_floor_ms": round(prefill_var, 2),
        "elapsed_total_s": round(time.time() - t0, 1),
    }

    out_json = OUT_DIR / "study_a_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to {out_json}")

    # Write per-trial CSV
    out_csv = OUT_DIR / "study_a_trials.csv"
    fieldnames = list(all_recs_with_baseline[0].keys())
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_recs_with_baseline:
            writer.writerow(rec)
    print(f"Per-trial CSV written to {out_csv}")

    print(f"\nTotal elapsed: {results['elapsed_total_s']} s")
    print("\n=== STUDY A COMPLETE ===")
    return results


if __name__ == "__main__":
    main()
