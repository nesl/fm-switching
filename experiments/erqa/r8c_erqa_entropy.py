#!/usr/bin/env python3
"""StudyR8c — ERQA 4B-Thinking re-run with per-step full-vocabulary entropy.

Same 400 questions, prompt construction, sdpa backend, max_new_tokens and parsing as
experiments/erqa/r4_device_signals.py's thinking arm (imported, not copied). Two
deliberate, pre-registered changes:

  1. decoding moves to the model card (temperature 1.0) where R4 used 0.6;
  2. every generation step records full-vocabulary entropy after temperature and
     BEFORE top-k / top-p, the chosen token's logprob, and the top-5 (id, logprob).

Sampling is done by this script's own processor rather than by HuggingFace's warper
chain, because a custom processor is merged AFTER the default warpers and would see a
distribution that top-k has already truncated. generation_config is therefore left at
temperature 1.0 / top_k 0 / top_p 1.0 (no warpers added) and the processor applies
temperature, then top-k, then top-p -- HuggingFace's own order.

Durations recorded here are CONTENDED (R8a and R8b share the host by the scheduling
rule) and are not latency measurements.
"""
import argparse, gzip, json, math, sys, time
from pathlib import Path

import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from transformers.generation.logits_process import LogitsProcessor

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))

import r4_device_signals as R4S
from _provenance import stamp

OUT_DIR = ROOT / "results/erqa/r8c_signals"

TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 20
REPETITION_PENALTY = 1.0      # presence_penalty 0 == no penalty == HF default
MAX_NEW = R4S.MAX_NEW_THINKING
TOPN_STORE = 5
ATTN_IMPL = R4S.ATTN_IMPL
SHARD_BYTES = 18 * 1024 * 1024


class EntropyRecorder(LogitsProcessor):
    """Records pre-truncation statistics, then performs temperature/top-k/top-p itself.

    The chosen token is not known when the processor runs, so each step's log-softmax is
    held until the next call, where input_ids[-1] reveals what was sampled.
    """

    def __init__(self, temperature, top_k, top_p):
        self.temperature, self.top_k, self.top_p = temperature, top_k, top_p
        self.reset()

    def reset(self):
        self.ent, self.chosen_lp, self.top_ids, self.top_lp = [], [], [], []
        self._prev_lp = None
        self._n_prompt = None
        self.truncated_input = 0

    def _settle(self, input_ids):
        """Fill in the previous step's chosen-token logprob."""
        if self._prev_lp is None:
            return
        tok = int(input_ids[0, -1])
        self.chosen_lp.append(round(float(self._prev_lp[tok]), 4))
        self._prev_lp = None

    def finalize(self, last_token_id):
        if self._prev_lp is not None:
            self.chosen_lp.append(round(float(self._prev_lp[int(last_token_id)]), 4))
            self._prev_lp = None

    def __call__(self, input_ids, scores):
        self._settle(input_ids)
        if torch.isinf(scores).any():
            self.truncated_input += 1       # someone truncated before us; recorded, not hidden
        s = scores.float() / self.temperature
        lp = torch.log_softmax(s, dim=-1)[0]
        p = lp.exp()
        ent = float(-(p * lp).sum() / math.log(2.0))
        self.ent.append(round(ent, 4))
        v, i = torch.topk(lp, TOPN_STORE)
        self.top_ids.append([int(x) for x in i.tolist()])
        self.top_lp.append([round(float(x), 4) for x in v.tolist()])
        self._prev_lp = lp.detach().to("cpu")

        out = s
        if self.top_k and self.top_k > 0:
            kth = torch.topk(out, min(self.top_k, out.shape[-1]))[0][..., -1, None]
            out = out.masked_fill(out < kth, float("-inf"))
        if self.top_p is not None and self.top_p < 1.0:
            srt, idx = torch.sort(out, descending=True, dim=-1)
            cum = torch.softmax(srt, dim=-1).cumsum(dim=-1)
            drop = cum - torch.softmax(srt, dim=-1) >= self.top_p
            drop[..., 0] = False
            out = out.masked_fill(drop.scatter(1, idx, drop), float("-inf"))
        return out


class ShardWriter:
    """Gzipped jsonl, rolled to a new shard before any file passes SHARD_BYTES."""

    def __init__(self, stem):
        self.stem, self.n, self.f, self.paths = stem, 0, None, []
        self._roll()

    def _roll(self):
        if self.f:
            self.f.close()
        self.n += 1
        p = Path(f"{self.stem}_part{self.n:02d}.jsonl.gz")
        self.f = gzip.open(p, "at")
        self.paths.append(p)

    def write(self, obj):
        self.f.write(json.dumps(obj) + "\n")
        self.f.flush()
        if self.paths[-1].stat().st_size > SHARD_BYTES:
            self._roll()

    def close(self):
        if self.f:
            self.f.close()
        self.paths = [p for p in self.paths if p.stat().st_size > 20]
        return self.paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--temperature", type=float, default=TEMPERATURE)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()

    assert torch.cuda.is_available(), "no CUDA device visible"
    gpu = torch.cuda.get_device_name(0)
    print(f"device {args.device} = {gpu}", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items = R4S.load_erqa_items()
    if args.limit:
        items = items[:args.limit]
    print(f"{len(items)} ERQA questions", flush=True)

    path = R4S.PATH_4BT
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, device_map=args.device,
        attn_implementation=ATTN_IMPL)
    model.eval()
    processor = AutoProcessor.from_pretrained(path)
    tok = processor.tokenizer
    got = getattr(model.config, "_attn_implementation", None)
    assert got == ATTN_IMPL, f"expected {ATTN_IMPL}, got {got}"
    print(f"  attn {got}  dtype {next(model.parameters()).dtype}", flush=True)

    lt_ids = R4S.letter_token_ids(tok, R4S.WORKLOADS["erqa"]["letters"])
    rec = EntropyRecorder(args.temperature, TOP_K, TOP_P)

    suffix = f"_{args.tag}" if args.tag else ""
    stem = OUT_DIR / f"r8c_erqa_thinking_s{args.seed}{suffix}"
    writer = ShardWriter(str(stem))

    torch.manual_seed(args.seed)
    n_done = n_correct = n_oom = n_mismatch = 0
    t_start = time.time()
    for i, item in enumerate(items):
        letters = item["letters"]
        rec.reset()
        try:
            inputs = R4S.prepare(processor, R4S.erqa_messages(item), args.device)
            t0 = time.time()
            with torch.no_grad():
                out = model.generate(
                    **inputs, do_sample=True, temperature=1.0, top_k=0, top_p=1.0,
                    repetition_penalty=REPETITION_PENALTY, max_new_tokens=MAX_NEW,
                    logits_processor=[rec])
            dur_ms = (time.time() - t0) * 1000
            oom = False
        except torch.cuda.OutOfMemoryError as e:
            torch.cuda.empty_cache()
            n_oom += 1
            print(f"  OOM qid={item['qid']}: {e}", flush=True)
            writer.write(dict(workload="erqa", arm="thinking", qid=item["qid"], oom=True,
                              seed=args.seed, correct=False, predicted_letter=None))
            n_done += 1
            continue

        n_input = inputs["input_ids"].shape[1]
        gen = out[0][n_input:]
        gen_ids = gen.tolist()
        rec.finalize(gen_ids[-1] if gen_ids else 0)
        full = processor.decode(gen, skip_special_tokens=True)

        end_id = tok.convert_tokens_to_ids("</think>")
        think_closed, start = False, 0
        if end_id is not None and end_id in gen_ids:
            think_closed = True
            start = gen_ids.index(end_id) + 1
            think_text = processor.decode(gen[:start - 1], skip_special_tokens=True)
            think_text = think_text[len("<think>"):].strip() if think_text.startswith("<think>") else think_text.strip()
            answer_text = processor.decode(gen[start:], skip_special_tokens=True).strip()
        elif "</think>" in full:
            think_closed = True
            tp, ap_ = full.split("</think>", 1)
            think_text = tp[len("<think>"):].strip() if tp.startswith("<think>") else tp.strip()
            answer_text = ap_.strip()
        else:
            think_text, answer_text = full, full

        pos, found = R4S.find_answer_pos(gen_ids, tok, letters, start=start)
        prefix = torch.cat([inputs["input_ids"][0], gen[:pos]]).unsqueeze(0)
        fwd = {k: v for k, v in inputs.items() if k not in ("input_ids", "attention_mask")}
        fwd["input_ids"] = prefix
        fwd["attention_mask"] = torch.ones_like(prefix)
        with torch.no_grad():
            logits = model(**fwd, logits_to_keep=1).logits[0, -1]
        sig = R4S.signals_from_logits(logits, tok, lt_ids, letters)

        # smoke gate quantities, recorded on every trial
        n_steps = len(rec.ent)
        steps_match = (n_steps == len(gen_ids))
        reassembled = tok.decode(gen_ids, skip_special_tokens=True)
        text_match = (reassembled == full)
        if not (steps_match and text_match):
            n_mismatch += 1

        pred, parse_status = R4S.extract_letter_erqa(answer_text or "")
        correct = (pred == item["correct_letter"]) if pred else False
        n_think = len(tok.encode(think_text, add_special_tokens=False)) if think_text else 0

        writer.write({
            "workload": "erqa", "arm": "thinking", "qid": item["qid"],
            "category": item.get("category"), "n_images": item["n_images"],
            "option_letters": letters, "correct_letter": item["correct_letter"],
            "predicted_letter": pred, "parse_status": parse_status, "correct": correct,
            "oom": False, "attn_implementation": ATTN_IMPL, "model": "qwen3vl4b_thinking",
            "seed": args.seed, "temperature": args.temperature, "top_p": TOP_P, "top_k": TOP_K,
            "answer_text": answer_text, "think_text": think_text, "think_closed": think_closed,
            "n_input_tokens": n_input, "n_generated": len(gen_ids), "n_think_tokens": n_think,
            "n_think_tokens_in_steps": start if think_closed else len(gen_ids),
            "budget_hit": len(gen_ids) >= MAX_NEW,
            "answer_pos": pos, "answer_pos_is_letter": found,
            "contended_duration_ms": round(dur_ms, 1),
            "n_steps": n_steps, "steps_equal_generated": steps_match,
            "reassembled_equals_generated": text_match,
            "truncated_input_steps": rec.truncated_input,
            "steps": {"ent_bits": rec.ent, "chosen_lp": rec.chosen_lp,
                      "top5_ids": rec.top_ids, "top5_lp": rec.top_lp},
            **sig, **R4S.reasoning_signals(think_text, letters),
        })

        n_done += 1
        n_correct += int(correct)
        if n_done == 5 or n_done % 25 == 0 or n_done == len(items):
            el = time.time() - t_start
            print(f"[r8c s{args.seed}] {n_done}/{len(items)} acc={n_correct}/{n_done} "
                  f"({100*n_correct/n_done:.1f}%) elapsed={el/3600:.2f}h "
                  f"proj={el/n_done*len(items)/3600:.2f}h mismatch={n_mismatch} oom={n_oom}",
                  flush=True)

    paths = writer.close()
    elapsed_h = (time.time() - t_start) / 3600
    meta = {
        "study": "StudyR8c", "workload": "erqa", "arm": "thinking", "seed": args.seed,
        "n_trials": n_done, "n_correct": n_correct, "n_oom": n_oom,
        "n_gate_mismatch": n_mismatch, "elapsed_h": round(elapsed_h, 3),
        "contended": True,
        "contention_note": "R8a (CPU) and R8b (A6000) shared the host; every duration recorded "
                           "here is contended, not a latency measurement",
        "attn_implementation": ATTN_IMPL, "model_path": path, "gpu": gpu,
        "gen_config": dict(do_sample=True, temperature=args.temperature, top_p=TOP_P,
                           top_k=TOP_K, presence_penalty=0.0,
                           repetition_penalty=REPETITION_PENALTY, max_new_tokens=MAX_NEW,
                           seed=args.seed),
        "deliberate_changes_vs_r4": [
            "temperature 0.6 -> 1.0 (model card); accuracy drift expected",
            "sampling applied by this script's processor so entropy is pre-truncation",
        ],
        "entropy_definition": "full-vocabulary Shannon entropy in bits of softmax(logits/T), "
                              "computed before top-k and top-p",
        "files": [str(p.relative_to(ROOT)) for p in paths],
        "file_sizes_mb": [round(p.stat().st_size / 1e6, 3) for p in paths],
        "_provenance": stamp(script="r8c_erqa_entropy.py", model="qwen3vl4b_thinking",
                             device="rtx3090ti", n=n_done, seed=args.seed, args=args),
    }
    mp = OUT_DIR / f"r8c_erqa_thinking_s{args.seed}{suffix}_meta.json"
    json.dump(meta, open(mp, "w"), indent=2)
    print(f"\nDONE r8c s{args.seed}: n={n_done} acc={n_correct}/{n_done} "
          f"({100*n_correct/max(1,n_done):.1f}%) mismatch={n_mismatch} oom={n_oom} "
          f"elapsed={elapsed_h:.2f}h -> {mp}", flush=True)


if __name__ == "__main__":
    main()
