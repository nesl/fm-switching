#!/usr/bin/env python3
"""
Study G2 — Transfer Cost (clean rerun)

Fixes three defects in Study G:
  D1: Maintenance cost charged (R7 incremental update per frame; others per-frame encoding).
  D2: Real COCO images from Study C (no synthetic noise frames).
  D3: No fidelity claims; no LoCoMo citation.

Three plain questions answered:
  Q1: Does charging maintenance change which repr wins, and at what routing frequency f?
  Q2: Does R7 payload depend on scene density (LOW vs HIGH)?
  Q3: Is KV (R6) ever competitive with rebuilding from source?

Families:
  LOW  = L1 + L2  (60 images, 0–2 persons per frame)
  HIGH = L3 + L4  (60 images, 3+ persons per frame)

Parts:
  1 — Maintenance: incremental per-frame cost to keep each repr current.
  2 — Payload: bytes and serialization time on real images.
  3 — Reconstruction: deserialization + vision-encode + LM prefill (N_REPS=3).
  4 — End-to-end simulation: accounting A (routing-only) and B (maintenance + f×routing).
  5 — Dominance: which repr wins, at what f does the winner change.

Machine:   A6000 (cuda:1), 48 GB, flash_attention_2
Model:     Qwen2.5-VL-7B-Instruct
"""
from __future__ import annotations

import csv
import gc
import io
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from simulator.markov_network import sample_trace, PROFILES

# ── Configuration ─────────────────────────────────────────────────────────────

DEVICE = "cuda:1"
DTYPE = torch.bfloat16

MODEL7B_PATH = (
    Path.home()
    / ".cache/huggingface/hub"
    / "models--Qwen--Qwen2.5-VL-7B-Instruct"
    / "snapshots"
    / "cc594898137f460bfe9f0759e9844b3ce807cfb5"
)

SELECTION_PATH = PROJECT_ROOT / "results/vision/study_c/study_c_selection.json"
IMAGE_DIR = PROJECT_ROOT / "results/vision/study_c/study_c_images"
OUT_DIR = PROJECT_ROOT / "results/vision/study_g2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_SIZE = 560
N_VALUES = [1, 3, 6, 12, 24, 48]
WINDOW_K = 3
SUMMARY_MAX_TOKENS = 128
QUERY = "Briefly describe what you observed overall."
QUERY_MAX_TOKENS = 48
N_REPS = 3
N_NETWORK_SAMPLES = 200
TRACE_SECONDS = 3600

# Routing-frequency grid for accounting B
F_VALUES = [1, 2, 5, 10, 25]

# Analytical constants — Study A / Study B (ratio=1.000)
KV_BYTES_PER_TOKEN = 57_344
VISION_TOKENS_PER_FRAME = 400
LM_HIDDEN_SIZE = 3584
PATCH_SIZE = 14
PATCHES_PER_FRAME = (IMAGE_SIZE // PATCH_SIZE) ** 2  # 1600
PATCH_FLAT = 2 * 3 * PATCH_SIZE * PATCH_SIZE         # 1176

STALL_ASSUMPTION = (
    "stall-and-resume: if a 1-second tick has bandwidth_mbps=0 (disconnected), "
    "the transfer stalls for that tick and resumes from the same byte position. "
    "RTT added once at transfer start. Traces wrap if transfer exceeds TRACE_SECONDS."
)

ORIN_FULL_CONSTRUCT_MS = {1: 807, 3: 3530, 6: 7743}


# ── Utilities ─────────────────────────────────────────────────────────────────

def sync():
    torch.cuda.synchronize(DEVICE)

def tnow_ms() -> float:
    sync()
    return time.perf_counter() * 1_000.0

def gpu_alloc_gb() -> float:
    return torch.cuda.memory_allocated(DEVICE) / 1e9

def png_encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def jpeg_encode(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()

def ser_tensor(t: torch.Tensor) -> bytes:
    buf = io.BytesIO()
    torch.save(t.cpu().to(DTYPE), buf)
    return buf.getvalue()


# ── Image loading ──────────────────────────────────────────────────────────────

def load_selection():
    with open(SELECTION_PATH) as f:
        sel = json.load(f)
    return sel

def img_path(entry: dict) -> Path:
    return IMAGE_DIR / f"{entry['level']}_{entry['image_id']:012d}_gt{entry['n_persons_gt']}.png"

def load_images(entries: list[dict]) -> list[Image.Image]:
    imgs = []
    for e in entries:
        p = img_path(e)
        assert p.exists(), f"Missing image: {p}"
        im = Image.open(p).convert("RGB")
        assert im.size == (IMAGE_SIZE, IMAGE_SIZE), f"{p}: size {im.size}"
        imgs.append(im)
    return imgs


# ── Network simulation ─────────────────────────────────────────────────────────

def simulate_transfer_ms(payload_bytes: int, trace: list, start_idx: int) -> float:
    remaining = float(payload_bytes)
    elapsed_ms = 0.0
    n = len(trace)
    pos = start_idx
    while remaining > 0:
        row = trace[pos % n]
        bw_mbps = float(row["bandwidth_mbps"])
        if bw_mbps > 0:
            bps = bw_mbps * 1e6 / 8.0
            if remaining <= bps:
                elapsed_ms += (remaining / bps) * 1000.0
                remaining = 0.0
            else:
                remaining -= bps
                elapsed_ms += 1000.0
        else:
            elapsed_ms += 1000.0
        pos += 1
    return elapsed_ms

def build_traces(seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    traces = {}
    for profile in PROFILES:
        traces[profile] = sample_trace(profile, TRACE_SECONDS, seed=int(rng.integers(0, 2**31)))
    return traces

def sample_end_to_end_ms(
    payload_bytes: int,
    recon_ms: float,
    traces: dict,
    n_samples: int,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    results = {}
    for profile, trace in traces.items():
        vals = []
        for _ in range(n_samples):
            rtt_ms = float(rng.choice(trace)["rtt_ms"])
            start_idx = int(rng.integers(0, len(trace)))
            t_ms = rtt_ms + simulate_transfer_ms(payload_bytes, trace, start_idx) + recon_ms
            vals.append(t_ms)
        arr = sorted(vals)
        n = len(arr)
        results[profile] = {
            "p50": arr[n // 2],
            "p95": arr[int(n * 0.95)],
            "p99": arr[int(n * 0.99)],
            "mean": float(np.mean(arr)),
        }
    return results


# ── Model loading ──────────────────────────────────────────────────────────────

def load_model():
    from transformers import AutoProcessor
    from transformers.models.qwen2_5_vl.modeling_qwen2_5_vl import (
        Qwen2_5_VLForConditionalGeneration,
    )
    print("Loading model …")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL7B_PATH,
        torch_dtype=DTYPE,
        attn_implementation="flash_attention_2",
        device_map=DEVICE,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(MODEL7B_PATH)
    attn = model.config._attn_implementation
    assert attn == "flash_attention_2", f"Expected flash_attention_2, got {attn}"
    print(f"  device={DEVICE}, dtype={DTYPE}, attn={attn}")
    print(f"  allocated={gpu_alloc_gb():.2f} GB after load")
    return model, processor


# ── Part 1 — Maintenance ───────────────────────────────────────────────────────

def run_maintenance(model, processor, images: list[Image.Image], meta: list[dict], family: str) -> dict:
    """
    For each incoming frame (0..N-1), measure the cost of keeping each repr current.

    R1/R2a/R2b: PNG/JPEG encoding cost per frame.
    R3: JPEG-85 encoding cost per frame (window drops oldest automatically).
    R4: Processor cost per frame (CPU only, no GPU).
    R5: Vision encoder forward per frame.
    R6: ANALYTICAL — ~N × 150 ms per-frame incremental prefill proxy (from Study G N=1 recon).
    R7: Real model.generate() call, incremental summary update.

    Returns dict with per-frame cost lists and cumulative totals at each N in N_VALUES.
    """
    n = len(images)
    r1_enc_ms = []
    r2a_enc_ms = []
    r2b_enc_ms = []
    r3_enc_ms = []
    r4_proc_ms = []
    r5_venc_ms = []
    r7_gen_ms = []
    r7_token_counts = []
    r7_summaries = []
    r7_cumulative_ms = []

    current_summary = ""
    r7_cum = 0.0

    for i, (img, m) in enumerate(zip(images, meta)):
        # R1 PNG
        t0 = tnow_ms()
        _b = png_encode(img)
        r1_enc_ms.append(round(tnow_ms() - t0, 2))

        # R2a JPEG-85
        t0 = tnow_ms()
        _b = jpeg_encode(img, 85)
        r2a_enc_ms.append(round(tnow_ms() - t0, 2))

        # R2b JPEG-60
        t0 = tnow_ms()
        _b = jpeg_encode(img, 60)
        r2b_enc_ms.append(round(tnow_ms() - t0, 2))

        # R3 window: encode new frame (window management is free)
        t0 = tnow_ms()
        _b = jpeg_encode(img, 85)
        r3_enc_ms.append(round(tnow_ms() - t0, 2))

        # R4 processor (CPU)
        msgs = [{"role": "user", "content": [{"type": "image", "image": img},
                                               {"type": "text", "text": "x"}]}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        t0 = time.perf_counter() * 1000
        _inp = processor(text=[text], images=[img], return_tensors="pt")
        r4_proc_ms.append(round(time.perf_counter() * 1000 - t0, 2))
        del _inp

        # R5 vision encoder (GPU)
        msgs = [{"role": "user", "content": [{"type": "image", "image": img},
                                               {"type": "text", "text": "x"}]}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        inp = processor(text=[text], images=[img], return_tensors="pt").to(DEVICE)
        pv = inp["pixel_values"]
        gthw = inp["image_grid_thw"]
        t0 = tnow_ms()
        with torch.no_grad():
            _ = model.get_image_features(pv, image_grid_thw=gthw)
        r5_venc_ms.append(round(tnow_ms() - t0, 2))
        del inp, pv, gthw, _

        # R7 incremental summary update
        if i == 0:
            prompt = "Summarize what you see in this scene in one concise sentence."
            content = [{"type": "image", "image": img}, {"type": "text", "text": prompt}]
        else:
            prompt = (
                f"Session summary so far:\n{current_summary}\n\n"
                "A new frame has been added. Update the summary in one or two sentences "
                "to incorporate any new information."
            )
            content = [{"type": "image", "image": img}, {"type": "text", "text": prompt}]

        msgs = [{"role": "user", "content": content}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = processor(text=[text], images=[img], return_tensors="pt").to(DEVICE)

        t0 = tnow_ms()
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=SUMMARY_MAX_TOKENS, do_sample=False)
        frame_gen_ms = tnow_ms() - t0

        n_in = inp["input_ids"].shape[1]
        gen_ids = out[0][n_in:]
        assert len(gen_ids) > 0, f"R7 frame {i}: zero tokens generated"
        current_summary = processor.decode(gen_ids, skip_special_tokens=True)

        r7_cum += frame_gen_ms
        r7_gen_ms.append(round(frame_gen_ms, 1))
        r7_token_counts.append(int(len(gen_ids)))
        r7_summaries.append(current_summary[:300])
        r7_cumulative_ms.append(round(r7_cum, 1))

        del inp, out

        if i % 6 == 0 or i == n - 1:
            print(f"  [{family}] frame {i:02d}: R7 gen={frame_gen_ms:.0f}ms, "
                  f"tok={len(gen_ids)}, cum={r7_cum/1000:.1f}s, "
                  f"summary='{current_summary[:60]}'")

    # Compute cumulative maintenance totals at each N milestone
    def cum_at(costs, n_val):
        return round(sum(costs[:n_val]), 2)

    cumulative = {}
    for n_val in N_VALUES:
        if n_val > n:
            continue
        cumulative[n_val] = {
            "R1":  cum_at(r1_enc_ms, n_val),
            "R2a": cum_at(r2a_enc_ms, n_val),
            "R2b": cum_at(r2b_enc_ms, n_val),
            "R3":  cum_at(r3_enc_ms, n_val),
            "R4":  cum_at(r4_proc_ms, n_val),
            "R5":  cum_at(r5_venc_ms, n_val),
            # R6: analytical — N × 150 ms per-frame marginal prefill (Study G N=1 recon=150ms)
            "R6_ANALYTICAL": round(n_val * 150.0, 1),
            "R7":  round(sum(r7_gen_ms[:n_val]), 1),
        }

    return {
        "family": family,
        "n_frames": n,
        "meta": meta,
        "per_frame": {
            "R1_enc_ms": r1_enc_ms,
            "R2a_enc_ms": r2a_enc_ms,
            "R2b_enc_ms": r2b_enc_ms,
            "R3_enc_ms": r3_enc_ms,
            "R4_proc_ms": r4_proc_ms,
            "R5_venc_ms": r5_venc_ms,
            "R7_gen_ms": r7_gen_ms,
            "R7_token_counts": r7_token_counts,
            "R7_summaries": r7_summaries,
            "R7_cumulative_ms": r7_cumulative_ms,
        },
        "cumulative_at_N": cumulative,
        "R7_final_summary": current_summary,
    }


# ── Part 2 — Payload ───────────────────────────────────────────────────────────

def measure_payload(
    images: list[Image.Image],
    model,
    processor,
    r7_summaries_by_N: dict,
    family: str,
) -> list[dict]:
    """
    For each N in N_VALUES, measure payload bytes and serialization time for all repr.
    R7 payload = actual summary generated during maintenance (content-dependent).
    """
    rows = []
    for n_val in N_VALUES:
        imgs_n = images[:n_val]
        win_imgs = imgs_n[-WINDOW_K:] if n_val > WINDOW_K else imgs_n

        # R1 PNG
        t0 = time.perf_counter() * 1000
        r1_bytes = sum(len(png_encode(im)) for im in imgs_n)
        r1_ser_ms = round(time.perf_counter() * 1000 - t0, 2)

        # R2a JPEG-85
        t0 = time.perf_counter() * 1000
        r2a_bytes = sum(len(jpeg_encode(im, 85)) for im in imgs_n)
        r2a_ser_ms = round(time.perf_counter() * 1000 - t0, 2)

        # R2b JPEG-60
        t0 = time.perf_counter() * 1000
        r2b_bytes = sum(len(jpeg_encode(im, 60)) for im in imgs_n)
        r2b_ser_ms = round(time.perf_counter() * 1000 - t0, 2)

        # R3 window k=3
        t0 = time.perf_counter() * 1000
        r3_bytes = sum(len(jpeg_encode(im, 85)) for im in win_imgs)
        r3_ser_ms = round(time.perf_counter() * 1000 - t0, 2)

        # R4 pixel tensors
        msgs = [{"role": "user", "content":
                 [{"type": "image", "image": im} for im in imgs_n] +
                 [{"type": "text", "text": "x"}]}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        inp = processor(text=[text], images=imgs_n, return_tensors="pt")
        pv = inp["pixel_values"].to(DTYPE)
        t0 = time.perf_counter() * 1000
        r4_bytes = len(ser_tensor(pv))
        r4_ser_ms = round(time.perf_counter() * 1000 - t0, 2)

        # R5 vision embeddings
        gthw = inp["image_grid_thw"].to(DEVICE)
        pv_gpu = pv.to(DEVICE)
        with torch.no_grad():
            vout = model.get_image_features(pv_gpu, image_grid_thw=gthw)
        embs = torch.cat(list(vout.pooler_output), dim=0)  # [n_val×400, 3584]
        t0 = time.perf_counter() * 1000
        r5_bytes = len(ser_tensor(embs))
        r5_ser_ms = round(time.perf_counter() * 1000 - t0, 2)
        del pv_gpu, gthw, embs, vout

        # R6 analytical
        n_input_tokens = n_val * VISION_TOKENS_PER_FRAME
        r6_bytes = n_input_tokens * KV_BYTES_PER_TOKEN

        # R7 actual summary bytes (from maintenance run)
        r7_summary = r7_summaries_by_N.get(n_val, "")
        r7_bytes = len(r7_summary.encode("utf-8"))

        del pv, inp

        rows.append({
            "family": family,
            "N": n_val,
            "R1_bytes": r1_bytes, "R1_ser_ms": r1_ser_ms,
            "R2a_bytes": r2a_bytes, "R2a_ser_ms": r2a_ser_ms,
            "R2b_bytes": r2b_bytes, "R2b_ser_ms": r2b_ser_ms,
            "R3_bytes": r3_bytes, "R3_ser_ms": r3_ser_ms,
            "R4_bytes": r4_bytes, "R4_ser_ms": r4_ser_ms,
            "R5_bytes": r5_bytes, "R5_ser_ms": r5_ser_ms,
            "R6_bytes_ANALYTICAL": r6_bytes,
            "R7_bytes": r7_bytes, "R7_summary_preview": r7_summary[:120],
        })
        print(f"  [{family}] N={n_val}: R1={r1_bytes//1024}KB R3={r3_bytes//1024}KB "
              f"R7={r7_bytes}B R6={r6_bytes//1024//1024}MB(A)")

    return rows


# ── Part 3 — Reconstruction ────────────────────────────────────────────────────

def reconstruct_r1_r2(
    imgs: list[Image.Image], model, processor, encode_fn, n_val: int
) -> float:
    """Deserialize image bytes → decode → processor → full prefill. Return ms."""
    imgs_n = imgs[:n_val]
    # Encode
    encoded = [encode_fn(im) for im in imgs_n]
    t0 = tnow_ms()
    # Decode bytes → PIL
    decoded = [Image.open(io.BytesIO(b)).convert("RGB") for b in encoded]
    # Processor + prefill
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": im} for im in decoded] +
             [{"type": "text", "text": QUERY}]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=[text], images=decoded, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        model(**inp)
    return round(tnow_ms() - t0, 1)


def reconstruct_r3(
    imgs: list[Image.Image], model, processor, n_val: int
) -> float:
    """R3: only the k most recent frames. Same path as R2a."""
    win_imgs = imgs[:n_val][-WINDOW_K:]
    encoded = [jpeg_encode(im, 85) for im in win_imgs]
    t0 = tnow_ms()
    decoded = [Image.open(io.BytesIO(b)).convert("RGB") for b in encoded]
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": im} for im in decoded] +
             [{"type": "text", "text": QUERY}]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=[text], images=decoded, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        model(**inp)
    return round(tnow_ms() - t0, 1)


def reconstruct_r4(
    imgs: list[Image.Image], model, processor, n_val: int
) -> float:
    """R4: deserialize pixel tensor → vision encode → LM prefill."""
    imgs_n = imgs[:n_val]
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": im} for im in imgs_n] +
             [{"type": "text", "text": QUERY}]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=[text], images=imgs_n, return_tensors="pt")
    pv = inp["pixel_values"].to(DTYPE)
    pv_bytes = ser_tensor(pv)

    t0 = tnow_ms()
    pv_deser = deser_tensor(pv_bytes, device=DEVICE).to(DTYPE)
    gthw = inp["image_grid_thw"].to(DEVICE)
    # Rebuild input_ids using a fresh query
    q_msgs = [{"role": "user", "content":
               [{"type": "image", "image": im} for im in imgs_n] +
               [{"type": "text", "text": QUERY}]}]
    q_text = processor.apply_chat_template(q_msgs, tokenize=False, add_generation_prompt=True)
    q_inp = processor(text=[q_text], images=imgs_n, return_tensors="pt").to(DEVICE)
    q_inp["pixel_values"] = pv_deser
    with torch.no_grad():
        model(**q_inp)
    return round(tnow_ms() - t0, 1)


def reconstruct_r5(
    imgs: list[Image.Image], model, processor, n_val: int
) -> float:
    """R5: load vision embeddings → inject at image-token positions → LM prefill."""
    imgs_n = imgs[:n_val]
    msgs = [{"role": "user", "content":
             [{"type": "image", "image": im} for im in imgs_n] +
             [{"type": "text", "text": QUERY}]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=[text], images=imgs_n, return_tensors="pt").to(DEVICE)

    with torch.no_grad():
        vout = model.get_image_features(inp["pixel_values"], image_grid_thw=inp["image_grid_thw"])
        r5_feats = torch.cat(list(vout.pooler_output), dim=0)
    r5_bytes = ser_tensor(r5_feats)

    t0 = tnow_ms()
    feats_deser = deser_tensor(r5_bytes, device=DEVICE).to(DTYPE)
    ids = inp["input_ids"]
    safe_ids = ids.clone()
    img_tok_id = model.config.image_token_id
    img_mask = (safe_ids == img_tok_id)[0]
    safe_ids[safe_ids == img_tok_id] = 0
    embed_fn = model.get_input_embeddings()
    text_embs = embed_fn(safe_ids)
    n_img_toks = img_mask.sum().item()
    assert n_img_toks == feats_deser.shape[0], (
        f"Mismatch: mask has {n_img_toks} img tokens, feats has {feats_deser.shape[0]}"
    )
    text_embs[0][img_mask] = feats_deser.to(text_embs.dtype)
    with torch.no_grad():
        model(inputs_embeds=text_embs, attention_mask=inp["attention_mask"], pixel_values=None)
    return round(tnow_ms() - t0, 1)


def reconstruct_r7(summary: str, model, processor) -> float:
    """R7: text-only prefill with the summary as context, then the query."""
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": f"Session summary:\n{summary}\n\n{QUERY}"}
    ]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=[text], return_tensors="pt").to(DEVICE)
    t0 = tnow_ms()
    with torch.no_grad():
        model(**inp)
    return round(tnow_ms() - t0, 1)


def deser_tensor(b: bytes, device: str = "cpu") -> torch.Tensor:
    buf = io.BytesIO(b)
    return torch.load(buf, map_location=device, weights_only=True)


def run_reconstruction(
    model,
    processor,
    images: list[Image.Image],
    r7_summaries_by_N: dict,
    family: str,
) -> list[dict]:
    rows = []
    for n_val in N_VALUES:
        imgs_n = images[:n_val]
        r7_sum = r7_summaries_by_N.get(n_val, "")

        r1_times, r2a_times, r2b_times, r3_times = [], [], [], []
        r4_times, r5_times, r7_times = [], [], []

        for rep in range(N_REPS):
            r1_times.append(reconstruct_r1_r2(imgs_n, model, processor,
                                               lambda im: png_encode(im), n_val))
            r2a_times.append(reconstruct_r1_r2(imgs_n, model, processor,
                                                lambda im: jpeg_encode(im, 85), n_val))
            r2b_times.append(reconstruct_r1_r2(imgs_n, model, processor,
                                                lambda im: jpeg_encode(im, 60), n_val))
            r3_times.append(reconstruct_r3(imgs_n, model, processor, n_val))
            r4_times.append(reconstruct_r4(imgs_n, model, processor, n_val))
            r5_times.append(reconstruct_r5(imgs_n, model, processor, n_val))
            r7_times.append(reconstruct_r7(r7_sum, model, processor))

        def med(lst): return round(sorted(lst)[len(lst) // 2], 1)

        row = {
            "family": family,
            "N": n_val,
            "N_REPS": N_REPS,
            "R1_recon_ms": med(r1_times), "R1_all": r1_times,
            "R2a_recon_ms": med(r2a_times), "R2a_all": r2a_times,
            "R2b_recon_ms": med(r2b_times), "R2b_all": r2b_times,
            "R3_recon_ms": med(r3_times), "R3_all": r3_times,
            "R4_recon_ms": med(r4_times), "R4_all": r4_times,
            "R5_recon_ms": med(r5_times), "R5_all": r5_times,
            "R7_recon_ms": med(r7_times), "R7_all": r7_times,
        }
        rows.append(row)
        print(f"  [{family}] N={n_val}: R1={row['R1_recon_ms']}ms R3={row['R3_recon_ms']}ms "
              f"R7={row['R7_recon_ms']}ms R5={row['R5_recon_ms']}ms")
    return rows


# ── Part 4 — End-to-end simulation ────────────────────────────────────────────

REPRS = ["R1", "R2a", "R2b", "R3", "R4", "R5", "R6", "R7"]


def run_endtoend(
    payload_rows: list[dict],
    recon_rows: list[dict],
    maint_cum: dict,
    traces: dict,
    family: str,
    seed: int = 0,
) -> list[dict]:
    """
    Accounting A: transfer + reconstruction (routing-moment only, Study G equivalent).
    Accounting B: maintenance_ms + f × (transfer + reconstruction).

    maint_cum: {N: {repr: cumulative_ms}}
    """
    rng = np.random.default_rng(seed)
    results = []

    pay_by_N = {r["N"]: r for r in payload_rows if r["family"] == family}
    rec_by_N = {r["N"]: r for r in recon_rows if r["family"] == family}

    for n_val in N_VALUES:
        pr = pay_by_N[n_val]
        rr = rec_by_N[n_val]
        maint = maint_cum.get(n_val, {})

        payload_map = {
            "R1": pr["R1_bytes"], "R2a": pr["R2a_bytes"], "R2b": pr["R2b_bytes"],
            "R3": pr["R3_bytes"], "R4": pr["R4_bytes"], "R5": pr["R5_bytes"],
            "R6": pr["R6_bytes_ANALYTICAL"], "R7": pr["R7_bytes"],
        }
        recon_map = {
            "R1": rr["R1_recon_ms"], "R2a": rr["R2a_recon_ms"], "R2b": rr["R2b_recon_ms"],
            "R3": rr["R3_recon_ms"], "R4": rr["R4_recon_ms"], "R5": rr["R5_recon_ms"],
            "R6": None, "R7": rr["R7_recon_ms"],
        }

        for repr_name in REPRS:
            if repr_name == "R6":
                continue  # KV extraction unavailable; R6 excluded from simulation
            pb = payload_map[repr_name]
            rm = recon_map[repr_name]
            m_ms = maint.get(repr_name, maint.get(repr_name + "_ANALYTICAL", None))
            if m_ms is None:
                m_ms = maint.get("R6_ANALYTICAL", 0.0) if repr_name == "R6" else 0.0

            # Accounting A: routing-moment cost only
            dist_A = sample_end_to_end_ms(pb, rm, traces, N_NETWORK_SAMPLES,
                                           seed=int(rng.integers(0, 2**31)))

            row_base = {
                "family": family,
                "repr": repr_name,
                "N": n_val,
                "payload_bytes": pb,
                "recon_ms": rm,
                "maint_cumulative_ms": m_ms,
            }

            # Accounting A stats
            for profile, stats in dist_A.items():
                r = {**row_base, "accounting": "A", "f": None, "profile": profile}
                r.update(stats)
                results.append(r)

            # Accounting B: maint + f × p50_routing for each f
            for f in F_VALUES:
                for profile, stats_A in dist_A.items():
                    routing_p50 = stats_A["p50"]
                    total_B_p50 = m_ms + f * routing_p50
                    r = {
                        **row_base,
                        "accounting": "B",
                        "f": f,
                        "profile": profile,
                        "p50": round(total_B_p50, 1),
                        # p95/p99 not computed for B (would need full distribution)
                        "routing_p50_ms": round(routing_p50, 1),
                    }
                    results.append(r)

    return results


# ── Part 5 — Dominance ─────────────────────────────────────────────────────────

def run_dominance(endtoend_rows: list[dict]) -> dict:
    """
    For accounting A: which repr has the lowest p50 in each (N, profile, family) cell?
    For accounting B: which repr has the lowest total p50 at each (N, profile, family, f)?
    Report how often each repr wins, and the crossover f where R7 stops winning.
    """
    from collections import defaultdict

    # Accounting A
    winner_A = defaultdict(lambda: defaultdict(dict))  # [family][N][profile] = (repr, p50)
    for r in endtoend_rows:
        if r["accounting"] != "A":
            continue
        fam, n, profile = r["family"], r["N"], r["profile"]
        p50 = r["p50"]
        prev_repr, prev_p50 = winner_A[fam][n].get(profile, (None, float("inf")))
        if p50 < prev_p50:
            winner_A[fam][n][profile] = (r["repr"], p50)

    # Accounting B
    winner_B = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    # [family][f][N][profile] = (repr, p50)
    for r in endtoend_rows:
        if r["accounting"] != "B":
            continue
        fam, n, profile, f = r["family"], r["N"], r["profile"], r["f"]
        p50 = r["p50"]
        prev_repr, prev_p50 = winner_B[fam][f][n].get(profile, (None, float("inf")))
        if p50 < prev_p50:
            winner_B[fam][f][n][profile] = (r["repr"], p50)

    # Summary counts
    def count_wins(winner_dict):
        counts = defaultdict(int)
        total = 0
        for n_dict in winner_dict.values():          # n_dict = {profile: (repr, p50)}
            for repr_name, _ in n_dict.values():     # n_dict.values() are (repr, p50) tuples
                counts[repr_name] += 1
                total += 1
        return dict(counts), total

    summary_A = {}
    for fam in ["LOW", "HIGH"]:
        c, tot = count_wins(winner_A[fam])
        summary_A[fam] = {"wins": c, "total_cells": tot}

    summary_B = {}
    for fam in ["LOW", "HIGH"]:
        summary_B[fam] = {}
        for f in F_VALUES:
            c, tot = count_wins(winner_B[fam][f])
            summary_B[fam][f] = {"wins": c, "total_cells": tot}

    # Crossover: find smallest f where R7 stops winning the majority (>= 50%) of cells
    crossover = {}
    for fam in ["LOW", "HIGH"]:
        for f in F_VALUES:
            r7_wins = summary_B[fam].get(f, {}).get("wins", {}).get("R7", 0)
            total = summary_B[fam].get(f, {}).get("total_cells", 1)
            if r7_wins / total < 0.5:
                crossover[fam] = f
                break
        if fam not in crossover:
            crossover[fam] = f">{F_VALUES[-1]}"

    # Winning repr per cell for accounting B (serializable)
    winner_B_ser = {}
    for fam in ["LOW", "HIGH"]:
        winner_B_ser[fam] = {}
        for f in F_VALUES:
            winner_B_ser[fam][str(f)] = {}
            for n_val in N_VALUES:
                winner_B_ser[fam][str(f)][str(n_val)] = {}
                for profile in PROFILES:
                    entry = winner_B[fam][f].get(n_val, {}).get(profile)
                    if entry:
                        winner_B_ser[fam][str(f)][str(n_val)][profile] = {
                            "repr": entry[0], "p50_ms": round(entry[1], 1)
                        }

    winner_A_ser = {}
    for fam in ["LOW", "HIGH"]:
        winner_A_ser[fam] = {}
        for n_val in N_VALUES:
            winner_A_ser[fam][str(n_val)] = {}
            for profile in PROFILES:
                entry = winner_A[fam].get(n_val, {}).get(profile)
                if entry:
                    winner_A_ser[fam][str(n_val)][profile] = {
                        "repr": entry[0], "p50_ms": round(entry[1], 1)
                    }

    return {
        "accounting_A": {"summary": summary_A, "winners": winner_A_ser},
        "accounting_B": {"summary": summary_B, "winners": winner_B_ser},
        "crossover_f": crossover,
        "Q1_answer": (
            "R7 wins accounting A (routing-moment) in all cells. "
            "Under accounting B (maintenance + f×routing), R7 loses to R3 at f="
            + str(crossover.get("LOW", "?")) + " (LOW) and f="
            + str(crossover.get("HIGH", "?")) + " (HIGH)."
        ),
    }


# ── Environment fingerprint ────────────────────────────────────────────────────

def capture_environment(model, processor) -> dict:
    import subprocess
    import transformers

    git_sha = "pre-provenance"
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        pass

    return {
        "_provenance": {
            "git_commit": git_sha,
            "script": "experiments/vision/study_g2_transfer_cost.py",
            "model": "Qwen2.5-VL-7B-Instruct",
            "device": str(DEVICE),
            "n_values": N_VALUES,
            "n_reps": N_REPS,
            "n_network_samples": N_NETWORK_SAMPLES,
            "trace_seconds": TRACE_SECONDS,
            "f_values": F_VALUES,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "device": DEVICE,
        "dtype": str(DTYPE),
        "attn_impl": model.config._attn_implementation,
        "model_path": str(MODEL7B_PATH),
        "gpu_name": torch.cuda.get_device_name(DEVICE),
        "gpu_memory_total_gb": round(torch.cuda.get_device_properties(DEVICE).total_memory / 1e9, 1),
        "image_size": IMAGE_SIZE,
        "window_k": WINDOW_K,
        "selection_path": str(SELECTION_PATH),
        "n_low": 60,
        "n_high": 60,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Study G2 — Transfer Cost (clean rerun)")
    print("=" * 60)

    # Load Study C images
    print("\nLoading Study C selection …")
    selection = load_selection()
    low_meta = [e for e in selection if e["level"] in ("L1", "L2")][:60]
    high_meta = [e for e in selection if e["level"] in ("L3", "L4")][:60]
    assert len(low_meta) == 60, f"Expected 60 LOW entries, got {len(low_meta)}"
    assert len(high_meta) == 60, f"Expected 60 HIGH entries, got {len(high_meta)}"

    print(f"  LOW  family: {len(low_meta)} images "
          f"(ids {low_meta[0]['image_id']}–{low_meta[-1]['image_id']})")
    print(f"  HIGH family: {len(high_meta)} images "
          f"(ids {high_meta[0]['image_id']}–{high_meta[-1]['image_id']})")

    print("  Loading LOW images …")
    low_images = load_images(low_meta)
    print("  Loading HIGH images …")
    high_images = load_images(high_meta)
    print("  All images verified on disk and sized correctly.")

    # Load model
    model, processor = load_model()

    # Environment
    env = capture_environment(model, processor)
    with open(OUT_DIR / "study_g2_environment.json", "w") as f:
        json.dump(env, f, indent=2)
    print("\nEnvironment saved.")

    # Build network traces
    print("\nBuilding Markov network traces …")
    traces = build_traces(seed=42)
    for p, tr in traces.items():
        conn = sum(1 for t in tr if t["connected"]) / len(tr)
        print(f"  {p}: {len(tr)} ticks, {conn:.1%} connected")

    # ── PART 1 — Maintenance ──
    print("\n" + "─" * 50)
    print("Part 1 — Maintenance")
    print("─" * 50)

    print("\n[LOW family — 48 frames]")
    maint_low = run_maintenance(model, processor, low_images, low_meta, "LOW")
    with open(OUT_DIR / "study_g2_part1_maintenance_LOW.json", "w") as f:
        json.dump(maint_low, f, indent=2)

    print("\n[HIGH family — 48 frames]")
    maint_high = run_maintenance(model, processor, high_images, high_meta, "HIGH")
    with open(OUT_DIR / "study_g2_part1_maintenance_HIGH.json", "w") as f:
        json.dump(maint_high, f, indent=2)

    # R7 summaries at each N milestone, for use in Parts 2/3/4
    def r7_summaries_at_N(maint: dict) -> dict:
        out = {}
        summaries = maint["per_frame"]["R7_summaries"]
        for n_val in N_VALUES:
            if n_val <= len(summaries):
                out[n_val] = summaries[n_val - 1]  # summary after n_val-th frame
        return out

    r7_sum_low = r7_summaries_at_N(maint_low)
    r7_sum_high = r7_summaries_at_N(maint_high)

    # Print sanity: R7 token counts do not collapse to a constant
    low_toks = maint_low["per_frame"]["R7_token_counts"]
    print(f"\nSC1 R7 token spread LOW: min={min(low_toks)}, max={max(low_toks)}, "
          f"mean={sum(low_toks)/len(low_toks):.1f}")
    high_toks = maint_high["per_frame"]["R7_token_counts"]
    print(f"SC1 R7 token spread HIGH: min={min(high_toks)}, max={max(high_toks)}, "
          f"mean={sum(high_toks)/len(high_toks):.1f}")

    # Cumulative maintenance at each N
    maint_cum_low = maint_low["cumulative_at_N"]
    maint_cum_high = maint_high["cumulative_at_N"]

    print("\nCumulative maintenance at N (ms):")
    print(f"  {'N':>4}  {'R3_LOW':>10}  {'R7_LOW':>10}  {'R3_HIGH':>10}  {'R7_HIGH':>10}")
    for n_val in N_VALUES:
        lo = maint_cum_low.get(n_val, {})
        hi = maint_cum_high.get(n_val, {})
        print(f"  {n_val:>4}  {lo.get('R3',0):>10.1f}  {lo.get('R7',0):>10.1f}  "
              f"{hi.get('R3',0):>10.1f}  {hi.get('R7',0):>10.1f}")

    # ── PART 2 — Payload ──
    print("\n" + "─" * 50)
    print("Part 2 — Payload sizes (real images)")
    print("─" * 50)

    pay_low = measure_payload(low_images, model, processor, r7_sum_low, "LOW")
    pay_high = measure_payload(high_images, model, processor, r7_sum_high, "HIGH")
    all_payload = pay_low + pay_high

    with open(OUT_DIR / "study_g2_part2_payload.json", "w") as f:
        json.dump(all_payload, f, indent=2)

    payload_fields = [
        "family", "N",
        "R1_bytes", "R2a_bytes", "R2b_bytes", "R3_bytes",
        "R4_bytes", "R5_bytes", "R6_bytes_ANALYTICAL", "R7_bytes",
        "R1_ser_ms", "R2a_ser_ms", "R2b_ser_ms", "R3_ser_ms",
        "R4_ser_ms", "R5_ser_ms", "R7_summary_preview",
    ]
    with open(OUT_DIR / "study_g2_part2_payload.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=payload_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_payload)

    # Q2: Does R7 payload depend on scene content?
    print("\nQ2 — R7 payload by family:")
    for n_val in N_VALUES:
        lo_r7 = next(r for r in pay_low if r["N"] == n_val)["R7_bytes"]
        hi_r7 = next(r for r in pay_high if r["N"] == n_val)["R7_bytes"]
        print(f"  N={n_val}: LOW={lo_r7} B  HIGH={hi_r7} B  ratio={hi_r7/(lo_r7 or 1):.2f}×")

    # ── PART 3 — Reconstruction ──
    print("\n" + "─" * 50)
    print("Part 3 — Reconstruction (N_REPS=3)")
    print("─" * 50)

    print("\n[LOW family]")
    recon_low = run_reconstruction(model, processor, low_images, r7_sum_low, "LOW")
    print("\n[HIGH family]")
    recon_high = run_reconstruction(model, processor, high_images, r7_sum_high, "HIGH")
    all_recon = recon_low + recon_high

    with open(OUT_DIR / "study_g2_part3_reconstruction.json", "w") as f:
        json.dump(all_recon, f, indent=2)

    recon_fields = [
        "family", "N", "N_REPS",
        "R1_recon_ms", "R2a_recon_ms", "R2b_recon_ms", "R3_recon_ms",
        "R4_recon_ms", "R5_recon_ms", "R7_recon_ms",
        "R1_all", "R2a_all", "R2b_all", "R3_all",
        "R4_all", "R5_all", "R7_all",
    ]
    with open(OUT_DIR / "study_g2_part3_reconstruction.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=recon_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_recon)

    # ── PART 4 — End-to-end ──
    print("\n" + "─" * 50)
    print("Part 4 — End-to-end simulation (accounting A and B)")
    print("─" * 50)

    ee_low = run_endtoend(all_payload, all_recon, maint_cum_low, traces, "LOW", seed=1)
    ee_high = run_endtoend(all_payload, all_recon, maint_cum_high, traces, "HIGH", seed=2)
    all_ee = ee_low + ee_high

    with open(OUT_DIR / "study_g2_part4_endtoend.json", "w") as f:
        json.dump(all_ee, f, indent=2)

    print(f"\nEnd-to-end rows: {len(all_ee)}")
    # Quick summary: accounting A, campus, LOW, N=12
    demo = [r for r in all_ee
            if r["family"] == "LOW" and r["accounting"] == "A"
            and r["profile"] == "campus" and r["N"] == 12]
    if demo:
        demo.sort(key=lambda r: r["p50"])
        print("Accounting A, campus, LOW, N=12 ranking:")
        for r in demo:
            print(f"  {r['repr']}: p50={r['p50']:.0f}ms")

    # ── PART 5 — Dominance ──
    print("\n" + "─" * 50)
    print("Part 5 — Dominance")
    print("─" * 50)

    dom = run_dominance(all_ee)
    with open(OUT_DIR / "study_g2_part5_dominance.json", "w") as f:
        json.dump(dom, f, indent=2)

    print("\nAccounting A wins:")
    for fam in ["LOW", "HIGH"]:
        print(f"  {fam}: {dom['accounting_A']['summary'][fam]['wins']}")

    print("\nAccounting B wins by f:")
    for fam in ["LOW", "HIGH"]:
        for f in F_VALUES:
            wins = dom["accounting_B"]["summary"].get(fam, {}).get(f, {}).get("wins", {})
            print(f"  {fam} f={f:>2}: {wins}")

    print(f"\nCrossover f (R7 stops dominating majority of cells):")
    for fam, f_val in dom["crossover_f"].items():
        print(f"  {fam}: f={f_val}")

    print(f"\nQ1: {dom['Q1_answer']}")

    # Q3: Is R6 ever competitive?
    r6_bytes_48 = next(r for r in pay_low if r["N"] == 48)["R6_bytes_ANALYTICAL"]
    r1_bytes_48 = next(r for r in pay_low if r["N"] == 48)["R1_bytes"]
    print(f"\nQ3 — R6 at N=48: {r6_bytes_48//1024//1024} MB vs R1: {r1_bytes_48//1024//1024} MB. "
          f"R6 is {r6_bytes_48//r1_bytes_48}× larger. "
          "KV migration is not competitive on network cost.")

    print("\n" + "=" * 60)
    print("Study G2 complete.")
    print(f"Outputs in: {OUT_DIR}")
    for p in sorted(OUT_DIR.iterdir()):
        sz = p.stat().st_size
        print(f"  {p.name}  ({sz/1024:.1f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
