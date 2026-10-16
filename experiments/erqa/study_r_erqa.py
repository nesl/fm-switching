#!/usr/bin/env python3
"""Study R (H100 rerun): does the Instruct-vs-Thinking null at 4B persist at 32B on ERQA?

Replaces the interrupted A6000 StudyR run (BnB NF4, arm D at temp=1.0; its partial trials
remain in results/erqa/study_r/study_r_trials.jsonl and are NOT mixed into this run).

2x2 arms:
  A: Qwen3-VL-4B-Instruct  greedy, max_new_tokens=512   REUSE StudyQ arm E (itself StudyK INSTRUCT);
                                                         answer_text absent in reused trials; A6000 latency.
  B: Qwen3-VL-4B-Thinking  CFG-A, max_new_tokens=8192   REUSE StudyQ arm A (seed 42, A6000).
  C: Qwen3-VL-32B-Instruct greedy, max_new_tokens=512   NEW (h100nvl)
  D: Qwen3-VL-32B-Thinking CFG-A sampling, max_new_tokens=16384  NEW (h100nvl) — the cloud tier
  A_h100 (supplementary): arm A rerun on h100nvl for a same-hardware D/A latency ratio only;
     accuracy of the primary analysis still uses the reused arm A.

Decoding (thinking): temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True
  (CFG-A, StudyS0; model card recommends temp=1.0 — deviation disclosed).
  Budget asymmetry: B ran at 8192, D at 16384 (spec). n_generated is stored so D can be
  re-scored as if capped at 8192.
Seeding: per-question set_seed(42 + question_id) (resume-safe). Reused B seeded once per arm.

Device: run with CUDA_VISIBLE_DEVICES=<gpu> so the target GPU is cuda:0 (see research/HOST_H100.md).
Quantization: --quant bf16|nf4, decided by --probe (bf16 iff peak < 75 GB at 16384 new tokens).
  Both 32B arms must use the same --quant.

Order: spatial questions (Spatial Reasoning + Pointing) first, then the rest, so the primary
subset completes even if the overall run is cut for cost (projection after 10 trials of arm D).
"""

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
import transformers
from datasets import load_dataset
from qwen_vl_utils import process_vision_info
from transformers import (AutoProcessor, BitsAndBytesConfig,
                          Qwen3VLForConditionalGeneration, set_seed)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp  # noqa: E402

REPO = {
    "4BI":  ("Qwen/Qwen3-VL-4B-Instruct",  "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
    "32BI": ("Qwen/Qwen3-VL-32B-Instruct", "0cfaf48183f594c314753d30a4c4974bc75f3ccb"),
    "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1"),
}
REUSED_SNAPSHOTS = {  # from StudyQ (A6000, /mnt/ssd/hf_models)
    "A": "Qwen/Qwen3-VL-4B-Instruct@ebb281ec70b05090aa6165b016eac8ec08e71b17",
    "B": "Qwen/Qwen3-VL-4B-Thinking@1de27d8c51f12e819435303b9e84c4e25ba8401e",
}

DEVICE_SLUG = "h100nvl"
STUDY_Q_JSONL = Path("results/erqa/study_q/study_q_trials.jsonl")
OUT_DIR = Path("results/erqa/study_r")
JSONL_PATH = OUT_DIR / f"study_r_trials_{DEVICE_SLUG}.jsonl"
META_PATH = OUT_DIR / f"study_r_run_meta_{DEVICE_SLUG}.json"
# Attention backend (2026-10-15 flash-attn re-run). flash_attention_2 is MANDATORY for every load and is
# asserted after loading (Qwen3-VL silently falls back to sdpa if flash-attn is not importable).
# --attn sdpa reproduces the original 2026-10-14 runs and writes the un-suffixed files.
ATTN = "flash_attention_2"


def set_attn(attn):
    """Select backend; flash-attn runs write to *_fa2 files so the SDPA results are never overwritten."""
    global ATTN, JSONL_PATH, META_PATH
    ATTN = attn
    if attn == "flash_attention_2":
        JSONL_PATH = OUT_DIR / f"study_r_trials_{DEVICE_SLUG}_fa2.jsonl"
        META_PATH = OUT_DIR / f"study_r_run_meta_{DEVICE_SLUG}_fa2.json"


def assert_attn(model):
    got = getattr(model.config, "_attn_implementation", None)
    if got != ATTN:
        raise SystemExit(f"!!! ATTENTION BACKEND ASSERT FAILED: requested {ATTN}, model uses {got} — aborting !!!")
    return got
PROBE_PATH = OUT_DIR / f"study_r_vram_probe_{DEVICE_SLUG}.json"

SPATIAL = {"Spatial Reasoning", "Pointing"}
MAX_NEW_THINKING = 16384
MAX_NEW_INSTRUCT = 512
THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
                    max_new_tokens=MAX_NEW_THINKING)
INSTRUCT_GEN = dict(do_sample=False, max_new_tokens=MAX_NEW_INSTRUCT)
BF16_PEAK_LIMIT_GB = 75.0
PROJECT_AFTER = 10
FULL_RUN_LIMIT_H = 15.0


# --------------------------------------------------------------------------- data
# build_messages / extract_letter are identical to study_q_erqa.py (cross-study scoring).

def load_erqa():
    ds = load_dataset("RunsenXu/ERQA", verification_mode="no_checks")["test"]
    assert len(ds) == 400
    return ds


def build_messages(row):
    q_text = row['question']
    images = row['images_encoded']
    correct = row['answer']
    content = []
    img_idx = 0
    for j, part in enumerate(q_text.split('<image>')):
        if j > 0 and img_idx < len(images):
            content.append({"type": "image", "image": images[img_idx]})
            img_idx += 1
        if part:
            content.append({"type": "text", "text": part})
    while img_idx < len(images):
        content.append({"type": "image", "image": images[img_idx]})
        img_idx += 1
    return [{"role": "user", "content": content}], correct


def extract_letter(text):
    t = text.strip()
    if t and t[0] in 'ABCD' and (len(t) == 1 or t[1] in '.\n ):,'):
        return t[0], "direct"
    m = re.search(r'(?:answer is|answer:|the answer)\s*[:\s]*([A-D])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(r'\b([A-D])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


def question_order(ds):
    spatial = [i for i in range(len(ds)) if ds[i]["question_type"] in SPATIAL]
    rest = [i for i in range(len(ds)) if ds[i]["question_type"] not in SPATIAL]
    return spatial, rest


# --------------------------------------------------------------------------- model

def resolve_snapshot(key):
    from huggingface_hub import snapshot_download
    repo, rev = REPO[key]
    return snapshot_download(repo, revision=rev, local_files_only=True)


def load_model(key, quant):
    path = resolve_snapshot(key)
    kw = dict(device_map={"": 0}, attn_implementation=ATTN)
    if quant == "nf4":
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    else:
        kw["dtype"] = torch.bfloat16
    torch.cuda.reset_peak_memory_stats(0)
    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(path, **kw).eval()
    assert_attn(model)
    processor = AutoProcessor.from_pretrained(path)
    info = {
        "key": key, "repo": REPO[key][0], "revision": REPO[key][1], "snapshot_path": path,
        "quant": quant, "attn_implementation": getattr(model.config, "_attn_implementation", None),
        "load_s": round(time.time() - t0, 1),
        "weights_allocated_gb": round(torch.cuda.memory_allocated(0) / 1e9, 2),
    }
    print(f"Loaded {key}: {info}", flush=True)
    return model, processor, info


def prepare(processor, messages):
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    return processor(text=[text], images=image_inputs, videos=video_inputs,
                     padding=True, return_tensors="pt").to("cuda:0")


def infer_one(model, processor, messages, gen_kwargs, is_thinking, seed=None):
    inputs = prepare(processor, messages)
    n_input = inputs["input_ids"].shape[1]
    if seed is not None:
        set_seed(seed)
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    torch.cuda.synchronize()
    lat_ms = (time.time() - t0) * 1000
    peak_gb = torch.cuda.max_memory_allocated(0) / 1e9
    reserved_gb = torch.cuda.max_memory_reserved(0) / 1e9

    gen = out[0][n_input:]
    n_generated = int(gen.shape[0])
    full = processor.decode(gen, skip_special_tokens=True)
    budget_hit = n_generated >= gen_kwargs["max_new_tokens"]
    n_think, think_closed = 0, None
    if is_thinking:
        think_closed = "</think>" in full
        if think_closed:
            think_part, answer_part = full.split("</think>", 1)
            think_content = re.sub(r'^<think>', '', think_part).strip()
            answer_text = answer_part.strip()
            n_think = len(processor.tokenizer.encode(think_content, add_special_tokens=False))
        else:
            answer_text = full
    else:
        answer_text = full.strip()
    n_answer = len(processor.tokenizer.encode(answer_text, add_special_tokens=False)) if answer_text else 0
    return dict(answer_text=answer_text, raw_output=full, n_input_tokens=n_input,
                n_think_tokens=n_think, n_answer_tokens=n_answer, n_generated=n_generated,
                total_latency_ms=round(lat_ms, 1), budget_hit=budget_hit,
                think_closed=think_closed, peak_alloc_gb=round(peak_gb, 2),
                peak_reserved_gb=round(reserved_gb, 2))


# --------------------------------------------------------------------------- probe

def run_probe(ds, quant):
    """Worst-case VRAM: largest-input question, forced to generate exactly MAX_NEW_THINKING tokens."""
    model, processor, info = load_model("32BT", quant)
    sizes = []
    for i in range(len(ds)):
        msgs, _ = build_messages(ds[i])
        sizes.append((prepare(processor, msgs)["input_ids"].shape[1], i))
    n_in, qid = max(sizes)
    print(f"Probe: largest input q{qid} n_input={n_in}; forcing {MAX_NEW_THINKING} new tokens", flush=True)
    msgs, _ = build_messages(ds[qid])
    gen = dict(THINKING_GEN, min_new_tokens=MAX_NEW_THINKING)
    r = infer_one(model, processor, msgs, gen, is_thinking=True, seed=42)
    result = {
        "model": info, "question_id": qid, "n_input_tokens": n_in,
        "forced_new_tokens": MAX_NEW_THINKING, "n_generated": r["n_generated"],
        "peak_alloc_gb": r["peak_alloc_gb"], "peak_reserved_gb": r["peak_reserved_gb"],
        "latency_s": round(r["total_latency_ms"] / 1000, 1),
        "decode_tok_per_s": round(r["n_generated"] / (r["total_latency_ms"] / 1000), 1),
        "limit_gb": BF16_PEAK_LIMIT_GB,
        "decision": ("bf16" if r["peak_reserved_gb"] < BF16_PEAK_LIMIT_GB else "nf4")
                    if quant == "bf16" else "nf4 (probed in nf4)",
        "gpu": torch.cuda.get_device_name(0),
        "gpu_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1),
        "transformers": transformers.__version__, "torch": torch.__version__,
    }
    result["_provenance"] = stamp(script="study_r_erqa.py", model="qwen3vl32b_thinking",
                                  device=DEVICE_SLUG, n=1, seed=42)
    PROBE_PATH.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "_provenance"}, indent=2), flush=True)


# --------------------------------------------------------------------------- arms

def load_done(path):
    done = defaultdict(set)
    if path.exists():
        for line in open(path):
            if line.strip():
                t = json.loads(line)
                done[t["arm"]].add(t["question_id"])
    return done


def write_reused(out_f, done):
    q = [json.loads(l) for l in open(STUDY_Q_JSONL) if l.strip()]
    spec = {
        "A": ("E", "study_q_arm_E (=study_k INSTRUCT)", "greedy max_new_tokens=512; A6000; answer_text not stored"),
        "B": ("A", "study_q_arm_A", "temp=0.6 top_p=0.95 top_k=20 min_p=0 max_new_tokens=8192, seed=42 once per arm; A6000"),
    }
    for arm, (src_arm, src, dec) in spec.items():
        src_trials = [t for t in q if t["arm"] == src_arm and t.get("pass_index", 1) in (1, None)]
        if src_arm == "A":
            src_trials = [t for t in src_trials if t.get("seed") == 42]
        assert len(src_trials) == 400, (arm, len(src_trials))
        n = 0
        for t in src_trials:
            if t["question_id"] in done[arm]:
                continue
            r = {k: t.get(k) for k in ("question_id", "category", "n_images", "n_input_tokens",
                                        "n_think_tokens", "n_answer_tokens", "total_latency_ms",
                                        "budget_hit", "think_closed", "predicted_letter",
                                        "correct_letter", "correct", "parse_status")}
            r.update(arm=arm, answer_text=t.get("answer_text") if arm == "B" else None,
                     seed=42 if arm == "B" else None, _reused_from=src, _reused_decoding=dec,
                     _reused_snapshot=REUSED_SNAPSHOTS[arm], _hardware="a6000")
            out_f.write(json.dumps(r) + "\n")
            n += 1
        out_f.flush()
        print(f"[{arm}] reused {n} trials from {src}", flush=True)


def run_arm(arm, key, quant, is_thinking, qids, ds, out_f, done, meta, project=False):
    todo = [q for q in qids if q not in done[arm]]
    if not todo:
        print(f"[{arm}] nothing to do", flush=True)
        return
    model, processor, info = load_model(key, quant)
    meta.setdefault("arms", {})[arm] = info
    gen = THINKING_GEN if is_thinking else INSTRUCT_GEN
    peak_alloc = peak_res = 0.0
    lats, n_new = [], 0
    for qid in todo:
        row = ds[qid]
        msgs, correct_letter = build_messages(row)
        r = infer_one(model, processor, msgs, gen, is_thinking,
                      seed=(42 + qid) if is_thinking else None)
        pred, status = extract_letter(r["answer_text"])
        r.update(arm=arm, question_id=qid, category=row["question_type"],
                 n_images=len(row["images_encoded"]), predicted_letter=pred,
                 correct_letter=correct_letter, correct=(pred == correct_letter) if pred else False,
                 parse_status=status, seed=(42 + qid) if is_thinking else None,
                 quant=quant, _hardware=DEVICE_SLUG,
                 attn_implementation=model.config._attn_implementation)
        out_f.write(json.dumps(r) + "\n")
        out_f.flush()
        done[arm].add(qid)
        peak_alloc, peak_res = max(peak_alloc, r["peak_alloc_gb"]), max(peak_res, r["peak_reserved_gb"])
        lats.append(r["total_latency_ms"])
        n_new += 1
        if n_new % 10 == 0 or n_new == len(todo):
            print(f"[{arm}] {n_new}/{len(todo)} last q{qid} {row['question_type'][:12]} "
                  f"gen={r['n_generated']} lat={r['total_latency_ms']/1000:.1f}s "
                  f"peak={peak_res:.1f}GB", flush=True)
        if project and n_new == PROJECT_AFTER:
            mean_s = sum(lats) / len(lats) / 1000
            proj_full = mean_s * 400 / 3600
            proj_spatial = mean_s * len([q for q in qids if ds[q]["question_type"] in SPATIAL]) / 3600
            decision = "full_400" if proj_full <= FULL_RUN_LIMIT_H else "spatial_only"
            meta["projection_D"] = dict(after_trials=PROJECT_AFTER, mean_latency_s=round(mean_s, 1),
                                        projected_full_400_h=round(proj_full, 2),
                                        projected_spatial_h=round(proj_spatial, 2),
                                        limit_h=FULL_RUN_LIMIT_H, decision=decision)
            META_PATH.write_text(json.dumps(meta, indent=2))
            print(f"=== PROJECTION D: mean {mean_s:.1f}s/trial -> full 400 {proj_full:.1f}h, "
                  f"spatial {proj_spatial:.1f}h -> {decision} ===", flush=True)
            if decision == "spatial_only":
                # qids are spatial-first, so stopping once spatial is done drops only the rest.
                meta["overall_dropped_for_cost"] = True
                meta["_stop_after_spatial"] = True
        if meta.get("_stop_after_spatial") and all(
                q in done[arm] for q in qids if ds[q]["question_type"] in SPATIAL):
            print(f"[{arm}] spatial subset complete; overall dropped for cost", flush=True)
            break
    meta["arms"][arm].update(peak_alloc_gb=round(peak_alloc, 2), peak_reserved_gb=round(peak_res, 2),
                             n_new_trials=n_new)
    META_PATH.write_text(json.dumps(meta, indent=2))
    del model
    torch.cuda.empty_cache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="worst-case VRAM probe for 32B-Thinking")
    ap.add_argument("--quant", choices=["bf16", "nf4"], required=True)
    ap.add_argument("--arms", nargs="+", default=["A", "B", "C", "D", "A_h100"])
    ap.add_argument("--attn", choices=["flash_attention_2", "sdpa"], default="flash_attention_2")
    ap.add_argument("--subset", choices=["all", "spatial", "rest"], default="all",
                    help="restrict to the spatial subset or the non-spatial rest (same fixed order)")
    args = ap.parse_args()
    set_attn(args.attn)

    assert torch.cuda.device_count() >= 1
    print(f"cuda:0 = {torch.cuda.get_device_name(0)}; transformers {transformers.__version__}; "
          f"torch {torch.__version__}", flush=True)
    if transformers.__version__.startswith("5.17"):
        print("!!! WARNING: transformers 5.17.x — Qwen3-VL repetition-loop regression (olmo-eval #441) !!!",
              flush=True)
    ds = load_erqa()
    if args.probe:
        run_probe(ds, args.quant)
        return

    spatial, rest = question_order(ds)
    order = {"all": spatial + rest, "spatial": spatial, "rest": rest}[args.subset]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    meta.update(transformers=transformers.__version__, torch=torch.__version__,
                gpu=torch.cuda.get_device_name(0), quant_32b=args.quant,
                n_spatial=len(spatial), thinking_gen=THINKING_GEN, instruct_gen=INSTRUCT_GEN,
                attn_implementation=ATTN)
    meta.setdefault("subset_runs", []).append(dict(subset=args.subset, arms=args.arms,
                                                   at=time.strftime("%Y-%m-%dT%H:%M:%S")))
    if meta.get("quant_32b_locked") and meta["quant_32b_locked"] != args.quant:
        sys.exit(f"quant mismatch: run started with {meta['quant_32b_locked']}")
    meta["quant_32b_locked"] = args.quant
    done = load_done(JSONL_PATH)
    with open(JSONL_PATH, "a") as out_f:
        if "A" in args.arms or "B" in args.arms:
            write_reused(out_f, done)
        if "C" in args.arms:
            run_arm("C", "32BI", args.quant, False, order, ds, out_f, done, meta)
        if "D" in args.arms:
            run_arm("D", "32BT", args.quant, True, order, ds, out_f, done, meta, project=True)
        if "A_h100" in args.arms:
            run_arm("A_h100", "4BI", "bf16", False, order, ds, out_f, done, meta)
    meta["_provenance"] = stamp(script="study_r_erqa.py", model="qwen3vl32b", device=DEVICE_SLUG,
                                n=400, seed=42, args=args)
    META_PATH.write_text(json.dumps(meta, indent=2))
    print("STUDY R run finished. GIT RULE: do not commit; ask the user.", flush=True)


if __name__ == "__main__":
    main()
