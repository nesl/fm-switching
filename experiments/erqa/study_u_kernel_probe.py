"""StudyU kernel probe — which attention kernel actually runs under HF `attn_implementation="sdpa"`.

Portable: run on ANY machine (H100 now; the A6000 queue later). Loads one Qwen3-VL model with SDPA, runs one
real ERQA prompt (prefill + 16 decode steps) and records, for every scaled_dot_product_attention call:
  * the args that drive kernel selection (q/k/v shapes, dtype, mask present + dtype, is_causal, enable_gqa)
  * torch._fused_sdp_choice(...) — PyTorch's own dispatcher decision (MATH / FLASH / EFFICIENT / CUDNN)
and, independently, the CUDA kernel names seen by torch.profiler (classified flash / mem-efficient / cudnn / math).
Also records the global enable flags. Optionally (--also-fa2) records the kernels of the flash_attention_2 path.

Usage (from repo root):
  H100:  CUDA_VISIBLE_DEVICES=3 .venv/bin/python experiments/erqa/study_u_kernel_probe.py --model 8BT --device-slug h100nvl
  A6000: CUDA_VISIBLE_DEVICES=<gpu> python experiments/erqa/study_u_kernel_probe.py --model 8BT --device-slug a6000 \
             [--model-path /mnt/ssd/hf_models/<snapshot>]      # and again with --model 4BT
Output: results/erqa/study_u/study_u_kernel_<model>_<device-slug>.json
"""
import argparse
import collections
import json
import platform
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import transformers

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r_erqa as R  # noqa: E402  (build_messages / prepare / load_erqa)
from _provenance import stamp  # noqa: E402
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, set_seed  # noqa: E402

REPO = {
    "4BT":  ("Qwen/Qwen3-VL-4B-Thinking",  "1de27d8c51f12e819435303b9e84c4e25ba8401e"),
    "8BT":  ("Qwen/Qwen3-VL-8B-Thinking",  "92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"),
    "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1"),
}
SDP_NAMES = {-1: "ERROR", 0: "MATH", 1: "FLASH_ATTENTION", 2: "EFFICIENT_ATTENTION", 3: "CUDNN_ATTENTION",
             4: "OVERRIDEABLE"}
OUT_DIR = Path("results/erqa/study_u")
PROBE_QID = 0          # fixed, real ERQA question (same on every machine)
DECODE_STEPS = 16


def classify(name):
    n = name.lower()
    if "flash" in n:
        return "flash"
    if "fmha" in n or "efficient" in n or "cutlass" in n and "attention" in n:
        return "mem_efficient"
    if "cudnn" in n and ("attn" in n or "attention" in n or "sdpa" in n or "fmha" in n):
        return "cudnn"
    if "softmax" in n:
        return "softmax (math path if no fused kernel present)"
    return None


def resolve(key, model_path):
    if model_path:
        return model_path, None
    from huggingface_hub import snapshot_download
    repo, rev = REPO[key]
    path = snapshot_download(repo, revision=rev, local_files_only=True)
    return path, rev or Path(path).name


def probe(key, attn, model_path):
    path, rev = resolve(key, model_path)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=attn).eval()
    got = model.config._attn_implementation
    if got != attn:
        raise SystemExit(f"!!! ATTENTION BACKEND ASSERT FAILED: requested {attn}, model uses {got} !!!")
    proc = AutoProcessor.from_pretrained(path)
    ds = R.load_erqa()
    msgs, _ = R.build_messages(ds[PROBE_QID])
    inputs = R.prepare(proc, msgs)
    gen = dict(do_sample=False, max_new_tokens=DECODE_STEPS, min_new_tokens=DECODE_STEPS)

    calls = []
    orig = F.scaled_dot_product_attention

    def spy(q, k, v, attn_mask=None, dropout_p=0.0, is_causal=False, scale=None, **kw):
        if len(calls) < 4000:
            try:
                choice = torch._fused_sdp_choice(q, k, v, attn_mask, dropout_p, is_causal, scale=scale,
                                                 enable_gqa=kw.get("enable_gqa", False))
            except Exception as e:  # noqa: BLE001
                choice = f"err:{type(e).__name__}"
            calls.append(dict(
                q=list(q.shape), k=list(k.shape), dtype=str(q.dtype), mask=attn_mask is not None,
                mask_dtype=str(attn_mask.dtype) if attn_mask is not None else None,
                mask_shape=list(attn_mask.shape) if attn_mask is not None else None,
                is_causal=bool(is_causal), enable_gqa=bool(kw.get("enable_gqa", False)),
                q_contig=q.is_contiguous(), choice=SDP_NAMES.get(choice, str(choice))))
        return orig(q, k, v, attn_mask=attn_mask, dropout_p=dropout_p, is_causal=is_causal, scale=scale, **kw)

    with torch.no_grad():
        model.generate(**inputs, **gen)                       # warm-up (excluded)
        F.scaled_dot_product_attention = spy
        try:
            model.generate(**inputs, **gen)
        finally:
            F.scaled_dot_product_attention = orig
        from torch.profiler import ProfilerActivity, profile
        with profile(activities=[ProfilerActivity.CUDA, ProfilerActivity.CPU]) as prof:
            model.generate(**inputs, **gen)
            torch.cuda.synchronize()

    kern = collections.Counter()
    for e in prof.events():
        if e.device_type == torch.autograd.DeviceType.CUDA:
            kern[e.name] += 1
    attn_kernels = {n: c for n, c in kern.items() if classify(n)}
    classes = collections.Counter()
    for n, c in attn_kernels.items():
        classes[classify(n)] += c
    # SDPA dispatcher decisions, split into prefill (q_len > 1) and decode (q_len == 1)
    by_phase = collections.defaultdict(collections.Counter)
    sig = collections.defaultdict(collections.Counter)
    for c in calls:
        ph = "prefill" if c["q"][-2] > 1 else "decode"
        by_phase[ph][c["choice"]] += 1
        sig[ph][json.dumps({k: c[k] for k in ("dtype", "mask", "mask_dtype", "is_causal", "enable_gqa",
                                              "q_contig")}, sort_keys=True)] += 1
    out = dict(
        model_key=key, repo=REPO[key][0], revision=rev, attn_implementation=got,
        n_input_tokens=int(inputs["input_ids"].shape[1]), decode_steps=DECODE_STEPS, probe_question_id=PROBE_QID,
        sdpa_dispatch_by_phase={k: dict(v) for k, v in by_phase.items()},
        sdpa_call_signatures={k: dict(v) for k, v in sig.items()},
        sdpa_example_calls={ph: next((c for c in calls if (c["q"][-2] > 1) == (ph == "prefill")), None)
                            for ph in ("prefill", "decode")},
        profiler_attention_kernel_classes=dict(classes),
        profiler_attention_kernels=dict(sorted(attn_kernels.items(), key=lambda x: -x[1])[:25]),
        profiler_top_kernels=dict(kern.most_common(25)),
    )
    del model
    torch.cuda.empty_cache()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(REPO), required=True)
    ap.add_argument("--device-slug", required=True)
    ap.add_argument("--model-path", default=None, help="local snapshot dir (A6000: /mnt/ssd/hf_models/...)")
    ap.add_argument("--also-fa2", action="store_true", help="also profile attn_implementation=flash_attention_2")
    args = ap.parse_args()
    set_seed(0)
    res = dict(
        device_slug=args.device_slug, gpu_name=torch.cuda.get_device_name(0),
        compute_capability=list(torch.cuda.get_device_capability(0)),
        torch=torch.__version__, cuda=torch.version.cuda, cudnn=torch.backends.cudnn.version(),
        transformers=transformers.__version__, python=platform.python_version(),
        enable_flags=dict(flash=torch.backends.cuda.flash_sdp_enabled(),
                          mem_efficient=torch.backends.cuda.mem_efficient_sdp_enabled(),
                          math=torch.backends.cuda.math_sdp_enabled(),
                          cudnn=torch.backends.cuda.cudnn_sdp_enabled()),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    try:
        import flash_attn
        res["flash_attn_pkg"] = flash_attn.__version__
    except ImportError:
        res["flash_attn_pkg"] = None
    res["sdpa"] = probe(args.model, "sdpa", args.model_path)
    if args.also_fa2:
        res["flash_attention_2"] = probe(args.model, "flash_attention_2", args.model_path)
    res["_provenance"] = stamp(script="study_u_kernel_probe.py", model=args.model, device=args.device_slug,
                               n=1, args=args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"study_u_kernel_{args.model.lower()}_{args.device_slug}.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res["sdpa"][k] for k in ("sdpa_dispatch_by_phase", "profiler_attention_kernel_classes")}))
    print("wrote", p)


if __name__ == "__main__":
    main()
