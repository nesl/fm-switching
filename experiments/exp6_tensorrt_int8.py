"""
Experiment 6: TensorRT INT8 single data point (Spec 3, Track 1).

Scope (deliberately narrow):
    * Compile the current edge LLM (default: Qwen2.5-3B-Instruct) to
      TensorRT INT8 on Jetson AGX Orin 64GB.
    * Run the same prefill-vs-context-length benchmark and decode throughput
      benchmark used in exp5, so the resulting JSON can be dropped into the
      existing quantization comparison plots as a third series alongside
      FP16 and INT4 (bitsandbytes).

This script is intentionally a scaffold. The TensorRT compilation pipeline on
Jetson is fragile and is expected to be the failure point. Run interactively
on the Jetson and inspect each phase before the next.

Time-box: 2–3 days of effort (per Track 1 work item). If compilation fails
in that window, stop, document the specific failure mode in
results/exp6_tensorrt_int8.json under "compilation_status", and use the
fallback paragraph in this docstring's FALLBACK section for the paper.

USAGE
=====
    source .venv/bin/activate
    pip install tensorrt-llm  # or torch-tensorrt — see backend selection below
    python experiments/exp6_tensorrt_int8.py \
        --model Qwen/Qwen2.5-3B-Instruct \
        --backend trtllm \
        --output results/exp6_tensorrt_int8.json

BACKEND SELECTION
=================
Two paths are viable on Jetson, in rough order of preference:

    1. trtllm   — TensorRT-LLM. Best decode-throughput, supports INT8 weight-
                   only and SmoothQuant. Requires JetPack 6+ and a TRT-LLM
                   build matching the on-device TensorRT version. Known
                   fragility: ABI mismatches between the prebuilt wheels and
                   the Jetson-side libnvinfer.
    2. torch_tensorrt — Simpler API; compiles a TorchScript / Dynamo-exported
                   module. Less throughput than trtllm but more likely to
                   compile on the first attempt. INT8 calibration requires a
                   handful of representative prompts.

The scaffold below covers the torch_tensorrt path because it is the more
likely-to-succeed first attempt. Switch backends with --backend if needed.

FALLBACK PARAGRAPH (for paper, if compilation fails)
=====================================================
"FP16 was chosen as the deployed configuration because it is the de facto
default in the HuggingFace ecosystem that practitioners will actually use.
We attempted TensorRT INT8 compilation on Jetson AGX Orin and encountered
<specific failure: e.g. 'a libnvinfer ABI mismatch between the TRT-LLM
0.X.Y wheel built for x86_64 SBSA and the JetPack 6.X-shipped TensorRT
10.X', or 'torch_tensorrt failed to lower the Qwen attention block due to
unsupported sdpa_with_kv_cache export'>. The orchestrator treats
quantization as a configurable axis; its conclusions extend to
TensorRT-deployed models with proportional adjustments to the inertia
profiles. We treat the FP16 / bitsandbytes INT4 comparison as the
operative range; TensorRT INT8 would shift both the prefill curve and the
decode throughput line further to the right, but the orchestrator's
relative comparisons across policies (which depend on the *shape* of the
inertia curve, not absolute values) remain valid."

EXPECTED FAILURE MODES TO RECORD
================================
* JetPack version mismatch with trtllm wheel.
* ONNX opset incompatibility with Qwen attention/RoPE ops.
* INT8 calibration cache OOM during static-range collection on 64GB Orin.
* TensorRT plugin missing for fused QKV or rotary embedding kernels.
* torch_tensorrt Dynamo lowering trips on `torch._C._nn.scaled_dot_product_attention`
  with kv-cache reshape paths.
"""

import argparse
import json
import time
from pathlib import Path
from datetime import datetime

try:
    import torch
except Exception:  # noqa: BLE001
    torch = None


# ── Identical workload as exp5 (mirrored, not imported, to keep standalone) ──

PROMPT_LENGTHS = [128, 256, 512, 1024, 2048]
GEN_TOKENS = 60
N_RUNS = 5


def maybe_import_backend(backend: str):
    if backend == "trtllm":
        from tensorrt_llm.runtime import ModelRunner  # type: ignore
        return ("trtllm", ModelRunner)
    if backend == "torch_tensorrt":
        import torch_tensorrt  # type: ignore
        return ("torch_tensorrt", torch_tensorrt)
    raise ValueError(f"unknown backend {backend}")


def compile_torch_tensorrt(model_id: str, calibration_prompts, out_path: Path):
    """torch_tensorrt INT8 compilation path. Expected to be the fragile step."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch_tensorrt
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id,
                                                  torch_dtype=torch.float16,
                                                  device_map="cuda")
    model.eval()
    # Build a calibration dataloader from a few representative prompts
    calib_inputs = [tok(p, return_tensors="pt").to("cuda") for p in calibration_prompts]
    raise NotImplementedError(
        "Fill in torch_tensorrt.compile(...) with int8 calibrator and save. "
        "Document the exact failure mode if compilation fails."
    )


def bench_prefill(runner, tok, n_tokens: int) -> dict:
    """Measure prefill latency at the given prompt length. Returns ms."""
    raise NotImplementedError("Fill in once compile path succeeds.")


def bench_decode(runner, tok, n_gen_tokens: int) -> dict:
    """Measure decode tokens/sec for the given generation length."""
    raise NotImplementedError("Fill in once compile path succeeds.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--backend", default="torch_tensorrt",
                    choices=["torch_tensorrt", "trtllm"])
    ap.add_argument("--engine-path", default="results/qwen3b_trt_int8.engine")
    ap.add_argument("--output", default="results/exp6_tensorrt_int8.json")
    ap.add_argument("--calib-prompts", nargs="*",
                    default=["Describe this scene.",
                             "Plan the next robot action.",
                             "Summarise the last three frames."])
    args = ap.parse_args()

    out = {
        "experiment": "exp6_tensorrt_int8",
        "started_at": datetime.now().isoformat(),
        "model": args.model,
        "backend": args.backend,
        "prompt_lengths": PROMPT_LENGTHS,
        "gen_tokens": GEN_TOKENS,
        "n_runs": N_RUNS,
        "compilation_status": "not_attempted",
        "compilation_failure": None,
        "prefill_ms_by_length": {},
        "decode_tokens_per_s": None,
        "notes": [
            "Time-boxed to 2–3 days per Track 1 spec.",
            "Fallback paragraph lives in the module docstring.",
        ],
    }

    try:
        maybe_import_backend(args.backend)
    except Exception as e:  # noqa: BLE001
        out["compilation_status"] = "import_failed"
        out["compilation_failure"] = repr(e)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, indent=2))
        print(f"Backend import failed: {e}. Wrote stub to {args.output}.")
        return

    try:
        if args.backend == "torch_tensorrt":
            compile_torch_tensorrt(args.model, args.calib_prompts,
                                    Path(args.engine_path))
        else:
            raise NotImplementedError("trtllm path is the secondary fallback; fill in if needed.")
        out["compilation_status"] = "compiled"
    except NotImplementedError as e:
        out["compilation_status"] = "scaffold"
        out["compilation_failure"] = str(e)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, indent=2))
        print(f"Scaffold reached planned NotImplementedError: {e}")
        return
    except Exception as e:  # noqa: BLE001
        out["compilation_status"] = "compile_failed"
        out["compilation_failure"] = repr(e)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, indent=2))
        print(f"Compilation failed: {e}. Wrote failure record to {args.output}.")
        return

    # If we get here, fill in bench_prefill / bench_decode calls and write out.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
