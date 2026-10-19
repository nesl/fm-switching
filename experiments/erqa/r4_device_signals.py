#!/usr/bin/env python3
"""R4 prep — device-side confidence signals on ERQA and MV-RoboBench.

Produces per-question confidence features for the two image workloads where the
32B cloud model has already been run (StudyQ/StudyR on ERQA, StudyS2 on
MV-RoboBench), so the R4 escalation experiment can test whether the device can
tell when it needs the cloud. This script collects signals; it makes no claim.

Input construction is reused verbatim from the runs this pairs against:
  ERQA          -> study_q_erqa.build_messages / extract_letter   (A-D)
  MV-RoboBench  -> study_s2_mvrobobench_32b.build_messages        (A-E)

Backend: the reference arm (StudyQ arm E, reused from StudyK INSTRUCT) carries
attn_implementation=null, i.e. it predates attn_guard and ran on the default
sdpa path. This run therefore uses sdpa too, not flash-attention-2, and records
the backend on every trial. Asking for FA2 here would change the very
predictions the 20-question gate is checking.
"""
import argparse, json, math, os, re, sys, time
from pathlib import Path

import torch
import torch.nn as nn

if not hasattr(nn.Module, "set_submodule"):
    def _set_submodule(self, target, module):
        parts = target.split(".")
        parent = self
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], module)
    nn.Module.set_submodule = _set_submodule

import PIL.Image
if not hasattr(PIL.Image, "ExifTags"):
    class _Base:
        Orientation = 274
    class _FakeExifTags:
        Base = _Base()
    PIL.Image.ExifTags = _FakeExifTags()
from PIL import Image

from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

PATH_4BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17"
PATH_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"

MVROBO_ROOT = Path("/home/pragya/.cache/huggingface/hub/datasets--AaronFengZY24--MV_Robobench/"
                   "snapshots/869ea1113cf2f08498e81f57ced72597238455c0")
MVROBO_MANIFEST = ROOT / "results/erqa/study_s2/study_s2_manifest.json"
MVROBO_PROMPT_SUFFIX = "Answer with the option's letter from the given choices directly."

OUT_DIR = ROOT / "results/erqa/r4_signals"

THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
MAX_NEW_THINKING = 8192
MAX_NEW_INSTRUCT = 512
THINKING_SEED = 42
TOPK_STORE = 20
ATTN_IMPL = "sdpa"


# ---------------------------------------------------------------------------
# Workload loaders — each yields uniform items: (qid, messages, letters, correct)
# ---------------------------------------------------------------------------

def erqa_option_letters(q_text):
    """Letters actually offered by this question; StudyQ's random_baseline parse."""
    m = re.search(r'Choices:\s+(.*?)(?:\s+Please\s+answer|\s*$)', q_text, re.DOTALL)
    if not m:
        return list("ABCD")
    parts = re.split(r'\b([A-D])\.\s+', m.group(1))
    letters = [parts[i] for i in range(1, len(parts), 2) if i + 1 < len(parts)]
    return letters or list("ABCD")


def load_erqa_items():
    from datasets import load_dataset
    ds = load_dataset("RunsenXu/ERQA", verification_mode="no_checks")["test"]
    assert len(ds) == 400, f"expected 400 ERQA questions, got {len(ds)}"
    items = []
    for i, row in enumerate(ds):
        items.append({
            "qid": i,
            "category": row["question_type"],
            "n_images": len(row["images_encoded"]),
            "letters": erqa_option_letters(row["question"]),
            "correct_letter": row["answer"],
            "_row": row,
        })
    return items


def erqa_messages(item):
    """study_q_erqa.build_messages, verbatim."""
    row = item["_row"]
    q_text, images = row["question"], row["images_encoded"]
    content, img_idx = [], 0
    for j, part in enumerate(q_text.split("<image>")):
        if j > 0 and img_idx < len(images):
            content.append({"type": "image", "image": images[img_idx]})
            img_idx += 1
        if part:
            content.append({"type": "text", "text": part})
    while img_idx < len(images):
        content.append({"type": "image", "image": images[img_idx]})
        img_idx += 1
    return [{"role": "user", "content": content}]


def load_mvrobo_items():
    man = json.load(open(MVROBO_MANIFEST))
    assert man["n"] == 401, f"expected 401 MV-RoboBench questions, got {man['n']}"
    items = []
    for it in man["items"]:
        items.append({
            "qid": it["path"],
            "index": it["index"],
            "category": it["category"],
            "source": it["source"],
            "n_images": it["n_views"],
            "letters": sorted(it["options"].keys()),
            "correct_letter": it["correct_letter"],
            "_item": it,
        })
    return items


def mvrobo_messages(item):
    """study_s2_mvrobobench_32b.build_messages, verbatim."""
    it = item["_item"]
    content = []
    for k, (name, ill) in enumerate(zip(it["image_names"], it["illustrations"]), 1):
        label = f"View {k}" + (f" ({ill})" if ill else "") + ":"
        content.append({"type": "text", "text": label})
        content.append({"type": "image",
                        "image": Image.open(MVROBO_ROOT / it["path"] / name).convert("RGB")})
    opts = "\n".join(f"{k}. {v}" for k, v in sorted(it["options"].items()))
    content.append({"type": "text",
                    "text": f"{it['question']}\nOptions:\n{opts}\n{MVROBO_PROMPT_SUFFIX}"})
    return [{"role": "user", "content": content}]


WORKLOADS = {
    "erqa":   dict(load=load_erqa_items, messages=erqa_messages, letters="ABCD"),
    "mvrobo": dict(load=load_mvrobo_items, messages=mvrobo_messages, letters="ABCDE"),
}


# ---------------------------------------------------------------------------
# Answer extraction — each workload keeps its own committed parser
# ---------------------------------------------------------------------------

def extract_letter_erqa(text):
    """study_q_erqa.extract_letter, verbatim (A-D)."""
    t = text.strip()
    if t and t[0] in "ABCD" and (len(t) == 1 or t[1] in ".\n ):,"):
        return t[0], "direct"
    m = re.search(r'(?:answer is|answer:|the answer)\s*[:\s]*([A-D])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(r'\b([A-D])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


def extract_letter_mvrobo(text):
    """study_s2_mvrobobench_32b.extract_letter, verbatim (A-E)."""
    letters = "ABCDE"
    t = text.strip()
    if t and t[0] in letters and (len(t) == 1 or t[1] in ".\n ):,"):
        return t[0], "direct"
    m = re.search(rf'(?:answer is|answer:|the answer)\s*[:\s]*([{letters}])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(rf'<answer>\s*([{letters}])\s*</answer>', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "answer_tag"
    m = re.search(rf'\b([{letters}])\b', t[-300:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


EXTRACT = {"erqa": extract_letter_erqa, "mvrobo": extract_letter_mvrobo}


# ---------------------------------------------------------------------------
# Confidence signals
# ---------------------------------------------------------------------------

def letter_token_ids(tok, letters):
    """Single-token ids that render as each option letter, across leading-space forms."""
    out = {}
    for L in letters:
        ids = set()
        for variant in (L, " " + L, "\n" + L, "**" + L):
            enc = tok.encode(variant, add_special_tokens=False)
            if len(enc) == 1:
                ids.add(enc[0])
        out[L] = sorted(ids)
    return out


def find_answer_pos(gen_ids, tok, letters, start=0):
    """First generated position at or after `start` whose token renders as an option letter."""
    for i in range(start, len(gen_ids)):
        if tok.decode([gen_ids[i]]).strip() in letters:
            return i, True
    return (start if start < len(gen_ids) else max(0, len(gen_ids) - 1)), False


def signals_from_logits(logits, tok, lt_ids, letters):
    """Option-letter distribution and top-20 logprobs at one position."""
    lp = torch.log_softmax(logits.float(), dim=-1)
    p = lp.exp()
    per = {L: float(sum(p[i].item() for i in lt_ids[L])) for L in letters}
    mass = sum(per.values())
    norm = {L: (per[L] / mass if mass > 0 else 0.0) for L in letters}
    ent = -sum(v * math.log2(v) for v in norm.values() if v > 0)
    srt = sorted(norm.values(), reverse=True)
    margin = (srt[0] - srt[1]) if len(srt) > 1 else srt[0]
    tv, ti = torch.topk(lp, min(TOPK_STORE, lp.shape[-1]))
    top = [{"token": tok.decode([int(i)]), "id": int(i), "logprob": round(float(v), 6)}
           for v, i in zip(tv.tolist(), ti.tolist())]
    return {
        "option_prob": {k: round(v, 8) for k, v in per.items()},
        "option_prob_norm": {k: round(v, 8) for k, v in norm.items()},
        "option_mass": round(mass, 8),
        "option_entropy_bits": round(ent, 6),
        "option_margin_norm": round(margin, 8),
        "argmax_letter": max(norm, key=norm.get) if norm else None,
        "top20": top,
    }


def reasoning_signals(think_text, letters):
    """Hesitation markers and the answer-letter trajectory inside the reasoning."""
    wait = len(re.findall(r'\bwait\b', think_text, re.IGNORECASE))
    but = len(re.findall(r'\bbut\b', think_text, re.IGNORECASE))
    seq = [m for m in re.findall(r'\b([A-E])\b', think_text) if m in letters]
    changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    return {
        "hesitation_wait": wait,
        "hesitation_but": but,
        "hesitation_total": wait + but,
        "letter_appears_in_reasoning": bool(seq),
        "n_letter_mentions": len(seq),
        "n_letter_changes": changes,
        "letters_in_reasoning": seq[:200],
        "first_letter_in_reasoning": seq[0] if seq else None,
        "last_letter_in_reasoning": seq[-1] if seq else None,
    }


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def prepare(processor, messages, device):
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    return processor(text=[text], images=image_inputs, videos=video_inputs,
                     padding=True, return_tensors="pt").to(device)


def run_instruct(model, processor, inputs, letters, lt_ids):
    """Greedy. output_scores is affordable here: generation stops after a few tokens."""
    tok = processor.tokenizer
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, do_sample=False, max_new_tokens=MAX_NEW_INSTRUCT,
                             output_scores=True, return_dict_in_generate=True)
    lat_ms = (time.time() - t0) * 1000
    n_input = inputs["input_ids"].shape[1]
    gen = out.sequences[0][n_input:]
    gen_ids = gen.tolist()
    full = processor.decode(gen, skip_special_tokens=True)
    pos, found = find_answer_pos(gen_ids, tok, letters)
    sig = signals_from_logits(out.scores[pos][0], tok, lt_ids, letters)
    return dict(answer_text=full.strip(), n_input_tokens=n_input, n_generated=len(gen_ids),
                n_think_tokens=0, think_text=None, think_closed=None,
                budget_hit=len(gen_ids) >= MAX_NEW_INSTRUCT,
                answer_pos=pos, answer_pos_is_letter=found, lat_ms=round(lat_ms, 1), **sig)


def run_thinking(model, processor, inputs, letters, lt_ids, device):
    """Sampled. Scores are recovered by one extra forward with logits_to_keep=1 —
    keeping 8192 steps of full-vocab logits would cost ~5 GB of the 24 GB card."""
    tok = processor.tokenizer
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, **THINKING_GEN, max_new_tokens=MAX_NEW_THINKING)
    lat_ms = (time.time() - t0) * 1000
    n_input = inputs["input_ids"].shape[1]
    gen = out[0][n_input:]
    gen_ids = gen.tolist()
    full = processor.decode(gen, skip_special_tokens=True)

    end_id = tok.convert_tokens_to_ids("</think>")
    think_closed = False
    start = 0
    if end_id is not None and end_id in gen_ids:
        think_closed = True
        start = gen_ids.index(end_id) + 1
        think_text = re.sub(r'^<think>', '', processor.decode(gen[:start - 1],
                                                              skip_special_tokens=True)).strip()
        answer_text = processor.decode(gen[start:], skip_special_tokens=True).strip()
    elif "</think>" in full:
        think_closed = True
        tp, ap = full.split("</think>", 1)
        think_text = re.sub(r'^<think>', '', tp).strip()
        answer_text = ap.strip()
    else:
        think_text, answer_text = full, full

    pos, found = find_answer_pos(gen_ids, tok, letters, start=start)

    prefix = torch.cat([inputs["input_ids"][0], gen[:pos]]).unsqueeze(0)
    fwd = {k: v for k, v in inputs.items() if k not in ("input_ids", "attention_mask")}
    fwd["input_ids"] = prefix
    fwd["attention_mask"] = torch.ones_like(prefix)
    with torch.no_grad():
        logits = model(**fwd, logits_to_keep=1).logits[0, -1]
    sig = signals_from_logits(logits, tok, lt_ids, letters)

    n_think = len(tok.encode(think_text, add_special_tokens=False)) if think_text else 0
    return dict(answer_text=answer_text, n_input_tokens=n_input, n_generated=len(gen_ids),
                n_think_tokens=n_think, think_text=think_text, think_closed=think_closed,
                budget_hit=len(gen_ids) >= MAX_NEW_THINKING,
                answer_pos=pos, answer_pos_is_letter=found, lat_ms=round(lat_ms, 1),
                **sig, **reasoning_signals(think_text, letters))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True, choices=list(WORKLOADS))
    ap.add_argument("--arm", required=True, choices=["instruct", "thinking"])
    ap.add_argument("--limit", type=int, default=None,
                    help="first N questions only (sanity check / smoke)")
    ap.add_argument("--tag", default="", help="output filename suffix, e.g. 'check20'")
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()

    assert torch.cuda.is_available(), "no CUDA device visible"
    gpu = torch.cuda.get_device_name(0)
    print(f"device: {args.device} = {gpu}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    jsonl = OUT_DIR / f"r4_{args.workload}_{args.arm}{suffix}.jsonl"

    done = set()
    if jsonl.exists():
        for line in open(jsonl):
            try:
                done.add(json.loads(line)["qid"])
            except Exception:
                continue
        print(f"resuming: {len(done)} trials already in {jsonl.name}", flush=True)

    wl = WORKLOADS[args.workload]
    print("loading questions...", flush=True)
    items = wl["load"]()
    if args.limit:
        items = items[:args.limit]
    print(f"{len(items)} questions", flush=True)

    path = PATH_4BI if args.arm == "instruct" else PATH_4BT
    model_slug = "qwen3vl4b_instruct" if args.arm == "instruct" else "qwen3vl4b_thinking"
    print(f"loading {path} ({ATTN_IMPL}) ...", flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, device_map=args.device,
        attn_implementation=ATTN_IMPL)
    model.eval()
    processor = AutoProcessor.from_pretrained(path)
    tok = processor.tokenizer
    got = getattr(model.config, "_attn_implementation", None)
    assert got == ATTN_IMPL, f"expected {ATTN_IMPL} backend, got {got}"
    print(f"  attn backend: {got}  dtype: {next(model.parameters()).dtype}", flush=True)

    lt_ids = letter_token_ids(tok, wl["letters"])
    print(f"  option-letter token ids: {lt_ids}", flush=True)
    for L, ids in lt_ids.items():
        assert ids, f"no single-token id found for option letter {L}"

    if args.arm == "thinking":
        torch.manual_seed(THINKING_SEED)

    extract = EXTRACT[args.workload]
    n_oom = n_done = n_correct = 0
    t_start = time.time()
    lat_hist = []

    with open(jsonl, "a") as f:
        for i, item in enumerate(items):
            if item["qid"] in done:
                continue
            letters = item["letters"]
            try:
                inputs = prepare(processor, wl["messages"](item), args.device)
                if args.arm == "instruct":
                    r = run_instruct(model, processor, inputs, letters, lt_ids)
                else:
                    r = run_thinking(model, processor, inputs, letters, lt_ids, args.device)
                oom = False
            except torch.cuda.OutOfMemoryError as e:
                torch.cuda.empty_cache()
                n_oom += 1
                print(f"  OOM on qid={item['qid']} (n_images={item['n_images']}): {e}", flush=True)
                r = dict(answer_text=None, n_input_tokens=None, n_generated=None,
                         n_think_tokens=None, think_text=None, think_closed=None,
                         budget_hit=None, answer_pos=None, answer_pos_is_letter=None,
                         lat_ms=None)
                oom = True

            pred, parse_status = (None, "oom") if oom else extract(r["answer_text"] or "")
            correct = (pred == item["correct_letter"]) if pred else False

            trial = {
                "workload": args.workload,
                "arm": args.arm,
                "qid": item["qid"],
                "category": item.get("category"),
                "source": item.get("source"),
                "n_images": item["n_images"],
                "option_letters": letters,
                "correct_letter": item["correct_letter"],
                "predicted_letter": pred,
                "parse_status": parse_status,
                "correct": correct,
                "oom": oom,
                "attn_implementation": ATTN_IMPL,
                "model": model_slug,
                "seed": THINKING_SEED if args.arm == "thinking" else None,
                "peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                **r,
            }
            f.write(json.dumps(trial) + "\n")
            f.flush()

            n_done += 1
            n_correct += int(correct)
            if r["lat_ms"]:
                lat_hist.append(r["lat_ms"])
            if n_done == 5 or n_done % 50 == 0 or n_done == len(items):
                mean_s = (sum(lat_hist) / len(lat_hist) / 1000) if lat_hist else 0
                remain = len(items) - len(done) - n_done
                print(f"[{args.workload}/{args.arm}] {n_done}/{len(items) - len(done)} "
                      f"acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%) "
                      f"mean={mean_s:.1f}s proj_remaining={mean_s*remain/3600:.2f}h "
                      f"oom={n_oom}", flush=True)

    elapsed_h = (time.time() - t_start) / 3600
    print(f"\nDONE {args.workload}/{args.arm}: n={n_done} acc={n_correct}/{n_done} "
          f"({100*n_correct/max(1,n_done):.1f}%) oom={n_oom} elapsed={elapsed_h:.2f}h", flush=True)

    meta = {
        "workload": args.workload, "arm": args.arm, "n_trials": n_done,
        "n_correct": n_correct, "n_oom": n_oom, "elapsed_h": round(elapsed_h, 3),
        "attn_implementation": ATTN_IMPL, "model_path": path,
        "gen_config": (dict(do_sample=False, max_new_tokens=MAX_NEW_INSTRUCT)
                       if args.arm == "instruct"
                       else dict(THINKING_GEN, max_new_tokens=MAX_NEW_THINKING,
                                 seed=THINKING_SEED)),
        "gpu": gpu, "jsonl": str(jsonl.relative_to(ROOT)),
        "_provenance": stamp(script="r4_device_signals.py", model=model_slug,
                             device="rtx3090ti", n=n_done,
                             seed=THINKING_SEED if args.arm == "thinking" else None,
                             args=args),
    }
    meta_path = OUT_DIR / f"r4_{args.workload}_{args.arm}{suffix}_meta.json"
    json.dump(meta, open(meta_path, "w"), indent=2)
    print(f"meta -> {meta_path}", flush=True)


if __name__ == "__main__":
    main()
