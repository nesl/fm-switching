"""
Inertia Profile — Re-prefill latency vs. context-token count (canonical profiler)
==================================================================================
Measures how LLM re-prefill latency scales with accumulated context tokens on
a target device. Output feeds directly into cost_model.py's inertia curves.

Output schema: results/inertia_<model>_<device>.json
  e.g.  inertia_smollm2_jetson.json   (SmolLM2-1.7B on Jetson AGX Orin)
        inertia_qwen7b_a6000.json     (Qwen2.5-7B on A6000)

Output JSON schema (list, readable by cost_model._load_inertia_curve):
  [{"context_tokens": N, "reprefill_ms": M, "std_ms": S, "reps": R}, ...]

Usage:
    # Jetson AGX Orin — SmolLM2-1.7B (edge model):
    python experiments/inertia_profile.py \\
        --model smollm2 --device jetson \\
        --llm HuggingFaceTB/SmolLM2-1.7B-Instruct \\
        --quantization fp16

    # A6000 server — Qwen2.5-7B (cloud model):
    python experiments/inertia_profile.py \\
        --model qwen7b --device a6000 \\
        --llm Qwen/Qwen2.5-7B-Instruct \\
        --quantization fp16

    # Quick smoke test (a few token counts, 2 reps):
    python experiments/inertia_profile.py \\
        --model smollm2 --device jetson --reps 2 \\
        --token-counts 100,300,500

Protocol:
  For each context_tokens value in --token-counts:
    1. Build a synthetic prompt of exactly that many tokens (padding tokens).
    2. Run --reps forward passes (max_new_tokens=1, do_sample=False).
    3. Record mean and std of prefill_ms (TTFT, two-call method from context_inertia).
  First rep is a warm-up (excluded from stats) unless --reps < 2.
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from context_inertia import load_llm
from _provenance import stamp

DEFAULT_TOKEN_COUNTS = [64, 128, 256, 384, 512, 768, 1024, 1536, 2048]
DEFAULT_REPS = 5


def _make_synthetic_input_ids(llm_tok, n_tokens: int):
    """Return a list of exactly n_tokens token IDs without a text roundtrip.

    Bypasses decode→re-encode so BPE merging of filler characters cannot
    compress the context. Uses BOS + repeated filler token; truncates/pads
    to hit exactly n_tokens.
    """
    bos = llm_tok.bos_token_id
    # Pick a stable single-token filler (period is 1 token in most BPE vocabs
    # when encoded in isolation; we use the raw ID directly, no text roundtrip).
    filler = llm_tok.encode(".", add_special_tokens=False)[0]
    base = [bos] if bos is not None else []
    remaining = max(0, n_tokens - len(base))
    ids = (base + [filler] * remaining)[:n_tokens]
    # Pad up if BOS was None and filler list came short (shouldn't happen).
    ids += [filler] * (n_tokens - len(ids))
    return ids


def profile_inertia(llm, llm_tok, token_counts, reps, use_chat_template=False):
    """For each token count, measure re-prefill latency (ms).

    Returns list of dicts: [{context_tokens, reprefill_ms, std_ms, reps}, ...].
    """
    results = []
    pad_id = llm_tok.eos_token_id if use_chat_template else llm_tok.pad_token_id

    for n_tok in token_counts:
        if use_chat_template:
            # Text path: chat template adds structural tokens; actual count will
            # differ from n_tok but is reported accurately via input_ids.shape.
            base = "Answer the following question in one word: What color is the sky?"
            base_ids = llm_tok.encode(base, add_special_tokens=False)
            filler = llm_tok.encode(".", add_special_tokens=False)[0]
            target = max(0, n_tok - len(base_ids))
            prompt = llm_tok.decode(base_ids + [filler] * target)
            formatted = llm_tok.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False, add_generation_prompt=True,
            )
            inputs = llm_tok(formatted, return_tensors="pt").to(llm.device)
        else:
            # Direct ID path: exact token count, no text roundtrip.
            ids = _make_synthetic_input_ids(llm_tok, n_tok)
            input_ids = torch.tensor([ids], dtype=torch.long).to(llm.device)
            inputs = {
                "input_ids": input_ids,
                "attention_mask": torch.ones_like(input_ids),
            }

        actual_tokens = int(inputs["input_ids"].shape[1])
        ms_samples = []

        for rep in range(reps):
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                _ = llm.generate(**inputs, max_new_tokens=1,
                                  do_sample=False, pad_token_id=pad_id)
            torch.cuda.synchronize()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if rep > 0 or reps == 1:  # exclude first rep as warm-up
                ms_samples.append(elapsed_ms)

        mean_ms = sum(ms_samples) / len(ms_samples)
        std_ms = math.sqrt(
            sum((x - mean_ms) ** 2 for x in ms_samples) / len(ms_samples)
        ) if len(ms_samples) > 1 else 0.0

        results.append({
            "context_tokens": actual_tokens,
            "reprefill_ms": round(mean_ms, 2),
            "std_ms": round(std_ms, 2),
            "reps": len(ms_samples),
        })
        print(f"  {actual_tokens:>5} tok: {mean_ms:>8.1f} ± {std_ms:>5.1f} ms  "
              f"(target {n_tok}, {len(ms_samples)} reps)")

    return results


def main():
    ap = argparse.ArgumentParser(
        description="Inertia profiler: re-prefill latency vs. context-token count"
    )
    ap.add_argument("--model",  required=True,
                    help="Model slug for output filename, e.g. smollm2, qwen7b.")
    ap.add_argument("--device", required=True,
                    help="Device slug for output filename, e.g. jetson, a6000.")
    ap.add_argument("--llm",    required=True,
                    help="HuggingFace model ID, e.g. HuggingFaceTB/SmolLM2-1.7B-Instruct.")
    ap.add_argument("--quantization", choices=["bnb", "prequant-bnb", "fp16"],
                    default="fp16")
    ap.add_argument("--use-chat-template", action="store_true",
                    help="Wrap prompts in chat template (required for instruction-tuned "
                         "models like SmolLM2).")
    ap.add_argument("--token-counts", default=None,
                    help="Comma-separated context token counts to probe. "
                         f"Default: {','.join(str(x) for x in DEFAULT_TOKEN_COUNTS)}")
    ap.add_argument("--reps", type=int, default=DEFAULT_REPS,
                    help=f"Repetitions per token count (first excluded as warm-up). "
                         f"Default: {DEFAULT_REPS}.")
    ap.add_argument("--output", default=None,
                    help="Override output path "
                         "(default: results/inertia_<model>_<device>.json).")
    args = ap.parse_args()

    token_counts = (
        [int(x) for x in args.token_counts.split(",")]
        if args.token_counts else DEFAULT_TOKEN_COUNTS
    )
    out_path = Path(
        args.output or f"results/inertia_{args.model}_{args.device}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print("=" * 64)
    print(f"INERTIA PROFILE — model={args.model}  device={args.device}")
    print(f"  GPU    : {device_name}")
    print(f"  LLM    : {args.llm}")
    print(f"  Counts : {token_counts}")
    print(f"  Reps   : {args.reps} (first excluded as warm-up)")
    print("=" * 64)

    print("\nLoading LLM...")
    llm, llm_tok = load_llm(args.llm, args.quantization)

    print(f"\nProfiling {len(token_counts)} token counts...")
    data = profile_inertia(llm, llm_tok, token_counts, args.reps,
                            use_chat_template=args.use_chat_template)

    provenance = stamp(
        script="inertia_profile.py",
        model=args.model,
        device=args.device,
        n=len(data),
        args=args,
    )

    out_path.write_text(json.dumps({
        "metadata": {
            "model": args.model,
            "device": args.device,
            "llm": args.llm,
            "quantization": args.quantization,
            "use_chat_template": args.use_chat_template,
            "gpu": device_name,
            "reps_per_count": args.reps,
            "token_counts_requested": token_counts,
            "timestamp": datetime.now().isoformat(),
        },
        "data": data,
        "_provenance": provenance,
    }, indent=2))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
