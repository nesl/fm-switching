"""
01_start_server.py — Launch vLLM OpenAI-compatible server

This starts an inference server that handles concurrent requests,
manages KV cache via PagedAttention, and exposes an OpenAI-compatible API.

IMPORTANT: Prefix caching is explicitly disabled (--no-enable-prefix-caching).
This is required for accurate context inertia benchmarking in 04_prefill_benchmark.py.
With prefix caching on, repeat prefill requests at the same depth hit the cache and
report falsely low latencies, corrupting the inertia curve.

Usage:
    python 01_start_server.py [--model MODEL_NAME] [--gpu-id 1] [--gpu-mem-fraction 0.85]
"""

import subprocess
import argparse
import os
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import torch


def get_gpu_memory_gb(gpu_id: int = 1):
    """Detect GPU memory to auto-select model.

    Args:
        gpu_id: Index within the visible CUDA device set (after CUDA_VISIBLE_DEVICES is set).
    """
    if torch.cuda.is_available():
        idx = min(gpu_id, torch.cuda.device_count() - 1)
        mem = torch.cuda.get_device_properties(idx).total_memory / (1024**3)
        name = torch.cuda.get_device_properties(idx).name
        return mem, name
    return 0, "No GPU"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default=None,
                        help="HuggingFace model name. Auto-selected if not provided.")
    parser.add_argument("--gpu-id", type=int, default=1,
                        help="GPU index to use (default: 1 = A6000)")
    parser.add_argument("--gpu-mem-fraction", type=float, default=0.85,
                        help="Fraction of GPU memory vLLM can use (leave headroom for monitoring)")
    parser.add_argument("--max-model-len", type=int, default=16384,
                        help="Maximum context length to support")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--enable-prefix-caching", action="store_true", default=False,
                        help="Enable vLLM prefix caching. OFF by default — must be off for "
                             "accurate re-prefill benchmarking. Only enable for 03_workload_generator.py runs.")
    args = parser.parse_args()

    # Pin vLLM to the target GPU via CUDA_VISIBLE_DEVICES.
    # vLLM will see this GPU as device 0 internally.
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
    print(f"Targeting GPU {args.gpu_id} (CUDA_VISIBLE_DEVICES={args.gpu_id})")

    mem_gb, gpu_name = get_gpu_memory_gb(0)  # index 0 within the visible set
    print(f"Detected GPU: {gpu_name} ({mem_gb:.1f} GB)")

    # Auto-select model based on GPU memory
    if args.model is None:
        if mem_gb >= 40:
            args.model = "mistralai/Mistral-7B-Instruct-v0.2"
            print(f"Auto-selected: {args.model} (>=40GB GPU)")
        elif mem_gb >= 20:
            args.model = "microsoft/phi-2"
            print(f"Auto-selected: {args.model} (>=20GB GPU)")
        else:
            args.model = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
            print(f"Auto-selected: {args.model} (<20GB GPU)")

    # Build vLLM server command.
    # Key flags:
    #   --gpu-memory-utilization: leave ~15% for monitoring overhead
    #   --max-model-len: support up to 16K context for deep sessions
    #   --no-enable-prefix-caching: CRITICAL for benchmarking — ensures every prefill
    #       request is computed fresh, not served from cache. Without this, repeat
    #       measurements at the same depth return cached results and appear much faster
    #       than a real cold migration would be.
    #   --disable-log-requests: reduce terminal noise
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--port", str(args.port),
        "--gpu-memory-utilization", str(args.gpu_mem_fraction),
        "--max-model-len", str(args.max_model_len),
        "--no-enable-log-requests",
    ]

    if not args.enable_prefix_caching:
        cmd.append("--no-enable-prefix-caching")

    print(f"\nStarting vLLM server...")
    print(f"  Model:              {args.model}")
    print(f"  Port:               {args.port}")
    print(f"  Max context:        {args.max_model_len} tokens")
    print(f"  GPU memory fraction:{args.gpu_mem_fraction}")
    print(f"  Prefix caching:     {'ON' if args.enable_prefix_caching else 'OFF (correct for benchmarking)'}")
    print(f"\nWait for 'Uvicorn running on http://0.0.0.0:{args.port}' before running other scripts.")
    print(f"Server will be at: http://localhost:{args.port}/v1\n")

    subprocess.run(cmd, env=os.environ)


if __name__ == "__main__":
    main()
