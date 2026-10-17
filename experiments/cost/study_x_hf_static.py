"""HF static batching at 32B (ORIGINAL .venv: torch 2.8.0+cu128, transformers 5.10.2, flash_attention_2 asserted).

Two uses (TIMING ONLY, no accuracy):
  --mode partB   StudyX Part B, HF side: the same 5 mixed batches as the vLLM side (7 short + 1 long; the long row
                 is forced to >= 8192 tokens by masking EOS for that row only — the per-row equivalent of vLLM's
                 min_tokens). One generate() per batch, left padding, CFG-A, set_seed(42 + long qid).
  --mode sweep   StudyW: batch sizes 1, 2, 4, 8, 16 over 16 length-matched ERQA questions, 32B-Instruct (greedy,
                 512) and 32B-Thinking (CFG-A, max_new_tokens 4096). OOM at a batch size is recorded, larger sizes
                 skipped.

Per batch: wall time (= latency every request in a static batch actually sees: results return when generate()
returns), per-row internal finish time (step at which that row emitted EOS, from per-step timestamps), real tokens
per row (up to and including EOS), peak allocated / reserved VRAM.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from transformers import (AutoProcessor, LogitsProcessor, LogitsProcessorList, Qwen3VLForConditionalGeneration,
                          StoppingCriteria, StoppingCriteriaList, set_seed)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "erqa"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r_erqa as R  # noqa: E402
from _provenance import stamp  # noqa: E402
from qwen_vl_utils import process_vision_info  # noqa: E402

REPO = {"32BI": ("Qwen/Qwen3-VL-32B-Instruct", "0cfaf48183f594c314753d30a4c4974bc75f3ccb"),
        "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1")}
ATTN = "flash_attention_2"
DEV = "h100nvl"
CFG_A = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
EOS = [151645, 151643]
CURRENT = Path("logs/study_x_current.json")


class StepClock(StoppingCriteria):
    def __init__(self):
        self.t, self.finished_at = [], {}

    def __call__(self, input_ids, scores, **kw):
        torch.cuda.synchronize()
        self.t.append(time.perf_counter())
        last = input_ids[:, -1].tolist()
        for i, tok in enumerate(last):
            if i not in self.finished_at and tok in EOS:
                self.finished_at[i] = len(self.t)
        return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)


class ForceRow(LogitsProcessor):
    """Mask EOS for one batch row until it has generated `min_new` tokens (per-row min_new_tokens)."""
    def __init__(self, row, min_new, prompt_len):
        self.row, self.min_new, self.prompt_len = row, min_new, prompt_len

    def __call__(self, input_ids, scores):
        if input_ids.shape[1] - self.prompt_len < self.min_new:
            scores[self.row, EOS] = -float("inf")
        return scores


def load(key):
    from huggingface_hub import snapshot_download
    path = snapshot_download(REPO[key][0], revision=REPO[key][1], local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=ATTN).eval()
    if model.config._attn_implementation != ATTN:
        raise SystemExit(f"!!! ATTENTION BACKEND ASSERT FAILED: {model.config._attn_implementation}")
    from attn_guard import assert_fa2   # repo convention (upstream 2026-10-16): every tower, not just the top config
    assert_fa2(model, where=key)
    proc = AutoProcessor.from_pretrained(path)
    proc.tokenizer.padding_side = "left"
    return model, proc


def batch_inputs(proc, ds, qids):
    texts, imgs = [], []
    for q in qids:
        msgs, _ = R.build_messages(ds[q])
        texts.append(proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True))
        im, _ = process_vision_info(msgs)
        imgs.extend(im or [])
    return proc(text=texts, images=imgs or None, padding=True, return_tensors="pt").to("cuda:0")


def run_batch(model, proc, ds, qids, gen, seed, force_row=None, force_min=None, label=""):
    inputs = batch_inputs(proc, ds, qids)
    plen = inputs["input_ids"].shape[1]
    clock = StepClock()
    lp = LogitsProcessorList([ForceRow(force_row, force_min, plen)]) if force_row is not None else None
    CURRENT.write_text(json.dumps(dict(label=label, qids=qids, at=datetime.now().isoformat())))
    set_seed(seed)
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**inputs, **gen, stopping_criteria=StoppingCriteriaList([clock]),
                             logits_processor=lp)
    torch.cuda.synchronize()
    wall = time.perf_counter() - t0
    gen_ids = out[:, plen:]
    rows = []
    for i, q in enumerate(qids):
        ids = gen_ids[i].tolist()
        n_real = next((k + 1 for k, t in enumerate(ids) if t in EOS), len(ids))
        fin_step = clock.finished_at.get(i)
        rows.append(dict(question_id=q, row=i, n_real_tokens=n_real, hit_max=fin_step is None,
                         internal_finish_s=round(clock.t[fin_step - 1] - t0, 3) if fin_step else round(wall, 3),
                         think_closed="</think>" in proc.decode(gen_ids[i][:n_real], skip_special_tokens=True)))
    return dict(qids=qids, batch_size=len(qids), n_input_padded=int(plen), steps=len(clock.t),
                wall_s=round(wall, 3), real_tokens=sum(r["n_real_tokens"] for r in rows),
                agg_real_tok_s=round(sum(r["n_real_tokens"] for r in rows) / wall, 3),
                padded_tok_s=round(len(qids) * len(clock.t) / wall, 3),
                peak_alloc_gb=round(torch.cuda.max_memory_allocated(0) / 1e9, 2),
                peak_reserved_gb=round(torch.cuda.max_memory_reserved(0) / 1e9, 2),
                rows=rows, seed=seed, attn_implementation=model.config._attn_implementation,
                wall_end=datetime.now().isoformat(), _hardware=DEV,
                _cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"))


def warm(model, proc, ds):
    with torch.no_grad():
        model.generate(**batch_inputs(proc, ds, [0]), do_sample=False, max_new_tokens=16)


def append(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def done(path, key):
    return path.exists() and any(json.loads(l).get("key") == key for l in open(path))


def part_b(cap=16384):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sel = json.loads(Path("results/erqa/study_u/study_u_selection.json").read_text())
    longest = [q["question_id"] for q in sel["questions"] if q["stratum"] == "long"][:5]
    short = [q["question_id"] for q in sel["questions"] if q["stratum"] == "short"]
    # cap=8192 (2026-10-16 re-run, matched to the vLLM B8k runs): every row max_new_tokens=8192, long row forced to
    # exactly 8,192. cap=16384 ran out of memory on the first batch (StudyX report).
    out = Path(f"results/cost/study_x/study_x_hf_static_partB{'_cap8192' if cap == 8192 else ''}_{DEV}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = R.load_erqa()
    model, proc = load("32BT")
    warm(model, proc, ds)
    for b in range(5):
        key = f"B{'8k' if cap == 8192 else ''}_hf_static_b{b}"
        if done(out, key):
            continue
        qids = [longest[b]] + [short[(b * 7 + j) % len(short)] for j in range(7)]
        rec = run_batch(model, proc, ds, qids, dict(CFG_A, max_new_tokens=cap), seed=42 + longest[b],
                        force_row=0, force_min=8192, label=key)
        rec.update(key=key, b=b, long=longest[b], short=qids[1:], forced_long_min_new_tokens=8192, cap=cap)
        append(out, rec)
        print(f"[{key}] wall {rec['wall_s']}s steps {rec['steps']} long {rec['rows'][0]['n_real_tokens']} "
              f"short internal finish {[r['internal_finish_s'] for r in rec['rows'][1:]]}", flush=True)


def sweep():
    out = Path(f"results/cost/study_w/study_w_batches_{DEV}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    # 16 length-matched questions: 32B-T flash-attn natural lengths closest to the median (StudyR-fa2 arm D)
    d = {r["question_id"]: r["n_generated"] for r in map(json.loads, open(
        "results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl")) if r["arm"] == "D"}
    med = float(np.median(list(d.values())))
    qids = sorted(d, key=lambda q: (abs(d[q] - med), q))[:16]
    Path(f"results/cost/study_w/study_w_questions_{DEV}.json").write_text(json.dumps(dict(
        rule="16 ERQA qids whose 32B-T flash-attn natural n_generated (StudyR-fa2 arm D) is closest to the median",
        median=med, questions={q: d[q] for q in qids}), indent=1))
    ds = R.load_erqa()
    for key, gen in (("32BI", dict(do_sample=False, max_new_tokens=512)),
                     ("32BT", dict(CFG_A, max_new_tokens=4096))):
        model, proc = load(key)
        warm(model, proc, ds)
        for bs in (1, 2, 4, 8, 16):
            oom = False
            for j in range(0, 16, bs):
                k = f"W_{key}_bs{bs}_{j // bs}"
                if done(out, k):
                    continue
                try:
                    rec = run_batch(model, proc, ds, qids[j:j + bs], gen, seed=42 + qids[j], label=k)
                except torch.cuda.OutOfMemoryError as e:
                    append(out, dict(key=k, model=key, batch_size=bs, oom=True, error=str(e)[:300]))
                    print(f"[{k}] OOM", flush=True)
                    torch.cuda.empty_cache()
                    oom = True
                    break
                rec.update(key=k, model=key, oom=False)
                append(out, rec)
                print(f"[{k}] wall {rec['wall_s']}s real {rec['real_tokens']} tok agg {rec['agg_real_tok_s']} tok/s "
                      f"peak {rec['peak_alloc_gb']}/{rec['peak_reserved_gb']} GB", flush=True)
            if oom:
                break
        del model
        torch.cuda.empty_cache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["partB", "sweep"], required=True)
    ap.add_argument("--cap", type=int, default=16384, choices=[8192, 16384], help="partB max_new_tokens")
    args = ap.parse_args()
    part_b(args.cap) if args.mode == "partB" else sweep()
    print("provenance", json.dumps(stamp(script="study_x_hf_static.py", model="qwen3vl-32b", device=DEV,
                                         args=args)), flush=True)


if __name__ == "__main__":
    main()
