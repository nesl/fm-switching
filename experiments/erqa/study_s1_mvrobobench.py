#!/usr/bin/env python3
"""Study S1 — MV-RoboBench thinking-mode experiment.

Design: reports/study_s0_plan.md v4.
  Arm I = Qwen3-VL-4B-Instruct (greedy, max_new_tokens=512)
  Arm T = Qwen3-VL-4B-Thinking, frozen config CFG-A per StudyS0 Audit 2
          (temp 0.6, top_p 0.95, top_k 20, max_new_tokens 8192)

Both arms run all 1,708 questions. This script only produces trials; the Gate 1
and Gate 2 analyses are separate.
"""

import argparse, json, os, re, time
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

from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

REPO = "AaronFengZY24/MV_Robobench"
PATH_4BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec"
PATH_4BT = ("/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/"
            "1de27d8c51f12e819435303b9e84c4e25ba8401e")

AUDIT1 = Path("results/erqa/study_s0/audit1_mvrobobench.json")
OUT_DIR = Path("results/mvrobobench/study_s1")
JSONL = OUT_DIR / "study_s1_trials.jsonl"

GEN = {
    "I": dict(do_sample=False, max_new_tokens=512),
    "T": dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20,
              max_new_tokens=8192),
}
MODEL_PATH = {"I": PATH_4BI, "T": PATH_4BT}

LETTER_RE = re.compile(r"\b([A-E])\b")
END_TAG = "</think>"


def resolve_snapshot(base):
    """Snapshot dirs may be abbreviated; expand to the real path."""
    p = Path(base)
    if p.exists():
        return str(p)
    parent, prefix = p.parent, p.name
    if parent.exists():
        for c in parent.iterdir():
            if c.name.startswith(prefix):
                return str(c)
    raise FileNotFoundError(f"no snapshot matching {base}")


def load_questions():
    recs = json.load(open(AUDIT1))["records"]
    for r in recs:
        r["block_id"] = r["qa"]["question"]
    return recs


def build_messages(rec):
    qa = rec["qa"]
    content = []
    for img in qa.get("images", []):
        rel = img["path"].lstrip("./")
        local = hf_hub_download(REPO, filename=f"{rec['path']}/{rel}",
                                repo_type="dataset")
        label = img.get("illustration", "")
        if label:
            content.append({"type": "text", "text": f"[{label}]"})
        content.append({"type": "image", "image": local})
    opts = qa.get("options", {}) or {}
    opt_text = "\n".join(f"{k}. {v}" for k, v in sorted(opts.items()))
    content.append({"type": "text",
                    "text": f"{qa['question']}\n\n{opt_text}\n\n"
                            "Answer with only the letter of the correct option "
                            "and nothing else."})
    return [{"role": "user", "content": content}]


def extract_letter(text, valid):
    m = re.search(r"<answer>\s*([A-Ea-e])\s*</answer>", text, re.I)
    if m:
        return m.group(1).upper()
    tail = text[-300:]
    hits = [h for h in LETTER_RE.findall(tail) if h in valid]
    return hits[-1] if hits else "X"


def load_done():
    done = set()
    if JSONL.exists():
        for line in open(JSONL):
            try:
                t = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add((t["arm"], t["qid_path"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["I", "T"])
    ap.add_argument("--device", default="cuda:1")
    ap.add_argument("--limit", type=int, default=None,
                    help="run only the first N (for runtime projection)")
    ap.add_argument("--category", default=None,
                    help="restrict to one category")
    ap.add_argument("--block-contains", default=None,
                    help="restrict to blocks whose question text contains this")
    ap.add_argument("--project-after", type=int, default=10)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    import transformers as tr
    print(f"transformers {tr.__version__} | torch {torch.__version__}")
    path = resolve_snapshot(MODEL_PATH[args.arm])
    print(f"arm {args.arm} | {path}")
    print(f"gen: {GEN[args.arm]}")

    recs = load_questions()
    if args.category:
        recs = [r for r in recs if r["category"] == args.category]
    if args.block_contains:
        recs = [r for r in recs if args.block_contains in r["block_id"]]
    done = load_done()
    todo = [r for r in recs if (args.arm, r["path"]) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(recs)} questions, {len(done)} trials already done, "
          f"{len(todo)} to run")
    if not todo:
        print("nothing to do")
        return

    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, device_map=args.device)
    processor = AutoProcessor.from_pretrained(path)
    print(f"loaded in {time.time()-t0:.1f}s | "
          f"VRAM {torch.cuda.memory_allocated(model.device)/1e9:.2f}GB")

    out_f = open(JSONL, "a")
    torch.manual_seed(42)
    n_correct = 0
    lat_sum = 0.0

    for i, rec in enumerate(todo):
        qa = rec["qa"]
        valid = set((qa.get("options") or {}).keys())
        messages = build_messages(rec)
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text], images=image_inputs,
                           videos=video_inputs, padding=True,
                           return_tensors="pt").to(model.device)
        n_input = inputs["input_ids"].shape[1]

        t_start = time.time()
        with torch.no_grad():
            out_ids = model.generate(**inputs, **GEN[args.arm])
        lat_ms = (time.time() - t_start) * 1000
        lat_sum += lat_ms

        gen_ids = out_ids[0][n_input:]
        n_gen = len(gen_ids)
        output = processor.decode(gen_ids, skip_special_tokens=False)

        if args.arm == "T":
            if END_TAG in output:
                idx = output.index(END_TAG)
                think_closed = True
                n_think = len(processor.tokenizer.tokenize(output[:idx]))
                answer_text = output[idx + len(END_TAG):]
            else:
                think_closed = False
                n_think = 0
                answer_text = output
        else:
            think_closed = None
            n_think = 0
            answer_text = output

        pred = extract_letter(answer_text, valid)
        correct = bool(pred == qa.get("correct") and (think_closed is not False))
        n_correct += correct

        out_f.write(json.dumps({
            "arm": args.arm,
            "qid_path": rec["path"],
            "source": rec["source"],
            "category": rec["category"],
            "block_id": rec["block_id"],
            "n_views": rec["n_views"],
            "correct": correct,
            "pred": pred,
            "answer": qa.get("correct"),
            "think_closed": think_closed,
            "budget_hit": bool(n_gen >= GEN[args.arm]["max_new_tokens"] - 5),
            "n_input": n_input,
            "n_think": n_think,
            "n_gen": n_gen,
            "lat_ms": round(lat_ms, 1),
        }) + "\n")
        out_f.flush()

        if i + 1 == args.project_after:
            per = lat_sum / (i + 1) / 1000
            print(f"\n[PROJECTION] {per:.1f}s/question over {i+1} trials "
                  f"=> {per*len(todo)/3600:.2f}h for {len(todo)} remaining\n",
                  flush=True)
        if (i + 1) % 50 == 0:
            print(f"  [{args.arm}] {i+1}/{len(todo)} "
                  f"acc={n_correct/(i+1)*100:.1f}% "
                  f"elapsed={(time.time()-t0)/3600:.2f}h", flush=True)

    out_f.close()
    print(f"arm {args.arm} done: {n_correct}/{len(todo)} = "
          f"{n_correct/len(todo)*100:.1f}%")


if __name__ == "__main__":
    main()
