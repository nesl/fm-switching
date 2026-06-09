"""
02_gpu_logger.py — GPU + vLLM internal metrics logger

Polls two data sources on every tick:

  1. pynvml (NVML) — GPU compute utilization, temperature, power.
     NOTE: pynvml memory figures are useless for vLLM workloads because vLLM
     pre-allocates its entire KV cache pool at startup. Memory stays flat at
     ~(weights + full_cache_pool) regardless of actual session load.

  2. vLLM /metrics (Prometheus) — actual KV cache block occupancy and request
     concurrency. These are the signals that matter for the SSM state vector:
       - vllm_cache_usage_pct   : fraction of KV cache blocks currently occupied
       - vllm_requests_running  : active requests on GPU
       - vllm_requests_waiting  : queued requests (backpressure indicator)
       - vllm_requests_swapped  : requests paged out to CPU (should be 0 normally)

Run in a separate terminal alongside the workload generator.
Stop with Ctrl+C — it will flush and save cleanly.

Usage:
    python 02_gpu_logger.py [--interval-ms 100] [--output logs/gpu_metrics.csv]
                             [--vllm-url http://localhost:8000]
"""

import time
import csv
import os
import re
import argparse
import warnings
from datetime import datetime

import requests as http_requests

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import pynvml
except ImportError:
    print("Install nvidia-ml-py: pip install nvidia-ml-py")
    exit(1)

# Flush the CSV to disk every this many samples (~10 seconds at 100ms interval).
FLUSH_EVERY_N_SAMPLES = 100

# vLLM Prometheus metric names we care about
VLLM_GAUGE_METRICS = {
    "vllm:kv_cache_usage_perc":  "vllm_cache_usage_pct",   # fraction of KV blocks occupied
    "vllm:num_requests_running": "vllm_requests_running",
    "vllm:num_requests_waiting": "vllm_requests_waiting",
    "vllm:num_requests_swapped": "vllm_requests_swapped",
}


def parse_prometheus_gauges(text: str, metric_names: dict) -> dict:
    """Extract scalar gauge values from a Prometheus exposition format response.

    Only handles gauge/counter scalar lines (not histograms or summaries).
    Returns -1 for any metric not found in the response.

    Args:
        text: Raw text from /metrics endpoint.
        metric_names: Dict mapping prometheus name → output column name.

    Returns:
        Dict of output_column_name → float value.
    """
    result = {col: -1.0 for col in metric_names.values()}
    for prom_name, col_name in metric_names.items():
        # Match: metric_name{any labels} value
        # or:    metric_name value   (no labels)
        pattern = rf'^{re.escape(prom_name)}(?:\{{[^}}]*\}})?\s+([-\d.e+]+)'
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            try:
                result[col_name] = float(match.group(1))
            except ValueError:
                pass
    return result


def scrape_vllm_metrics(vllm_url: str, timeout: float = 0.5) -> dict:
    """Scrape vLLM /metrics endpoint and return parsed gauge values.

    Uses a tight timeout to avoid blocking the logging loop if the server
    is briefly busy. Returns -1 for all metrics on failure.

    Args:
        vllm_url: Base URL of vLLM server.
        timeout: Request timeout in seconds.

    Returns:
        Dict of metric column names → float values.
    """
    fallback = {col: -1.0 for col in VLLM_GAUGE_METRICS.values()}
    try:
        resp = http_requests.get(f"{vllm_url}/metrics", timeout=timeout)
        if resp.status_code == 200:
            return parse_prometheus_gauges(resp.text, VLLM_GAUGE_METRICS)
    except Exception:
        pass
    return fallback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-ms", type=int, default=100,
                        help="Polling interval in milliseconds")
    parser.add_argument("--output", type=str, default="logs/gpu_metrics.csv")
    parser.add_argument("--gpu-index", type=int, default=1,
                        help="GPU index to monitor (default: 1 = A6000)")
    parser.add_argument("--vllm-url", type=str, default="http://localhost:8000",
                        help="vLLM server URL to scrape /metrics from. "
                             "Set to empty string to disable vLLM scraping.")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(args.gpu_index)
    device_name = pynvml.nvmlDeviceGetName(handle)
    total_mem = pynvml.nvmlDeviceGetMemoryInfo(handle).total / (1024**3)

    scrape_vllm = bool(args.vllm_url)

    print(f"Logging GPU metrics for: {device_name} ({total_mem:.1f} GB)")
    print(f"Polling every {args.interval_ms}ms → {args.output}")
    print(f"vLLM metrics: {'enabled (' + args.vllm_url + ')' if scrape_vllm else 'disabled'}")
    print(f"Flushing to disk every {FLUSH_EVERY_N_SAMPLES} samples "
          f"({FLUSH_EVERY_N_SAMPLES * args.interval_ms / 1000:.1f}s)")
    print("Press Ctrl+C to stop.\n")

    fieldnames = [
        "timestamp",
        "elapsed_s",
        # GPU hardware metrics (from NVML)
        "gpu_utilization_pct",
        "temperature_c",
        "power_draw_w",
        # vLLM internal KV cache metrics (from /metrics endpoint)
        # These replace pynvml memory — they reflect actual session load, not pool allocation.
        "vllm_cache_usage_pct",      # fraction of KV cache blocks occupied (0–1)
        "vllm_requests_running",     # requests actively computing on GPU
        "vllm_requests_waiting",     # requests queued (backpressure signal)
        "vllm_requests_swapped",     # requests paged to CPU (should be 0)
        # Raw NVML memory retained for reference (flat/useless for vLLM but kept for completeness)
        "memory_used_gb",
    ]

    start_time = time.time()
    sample_count = 0

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()

        try:
            while True:
                now = time.time()
                elapsed = now - start_time

                # NVML query
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except pynvml.NVMLError:
                    temp = -1

                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                except pynvml.NVMLError:
                    power = -1

                # vLLM /metrics scrape
                vllm_metrics = scrape_vllm_metrics(args.vllm_url) if scrape_vllm else {
                    col: -1.0 for col in VLLM_GAUGE_METRICS.values()
                }

                row = {
                    "timestamp": datetime.now().isoformat(),
                    "elapsed_s": round(elapsed, 3),
                    "gpu_utilization_pct": util.gpu,
                    "temperature_c": temp,
                    "power_draw_w": round(power, 1),
                    "vllm_cache_usage_pct": round(vllm_metrics["vllm_cache_usage_pct"], 4),
                    "vllm_requests_running": int(vllm_metrics["vllm_requests_running"]),
                    "vllm_requests_waiting": int(vllm_metrics["vllm_requests_waiting"]),
                    "vllm_requests_swapped": int(vllm_metrics["vllm_requests_swapped"]),
                    "memory_used_gb": round(mem_info.used / (1024**3), 2),
                }

                writer.writerow(row)
                sample_count += 1

                if sample_count % FLUSH_EVERY_N_SAMPLES == 0:
                    f.flush()

                # Print status every 10 seconds
                if sample_count % (10000 // args.interval_ms) == 0:
                    cache_pct = vllm_metrics["vllm_cache_usage_pct"]
                    running = int(vllm_metrics["vllm_requests_running"])
                    waiting = int(vllm_metrics["vllm_requests_waiting"])
                    print(f"  [{elapsed:7.1f}s] GPU: {util.gpu:3d}% | "
                          f"Temp: {temp}°C | Power: {power:.0f}W | "
                          f"KV cache: {cache_pct*100:.1f}% | "
                          f"Reqs: {running} running, {waiting} waiting")

                sleep_time = (args.interval_ms / 1000.0) - (time.time() - now)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            pass

    duration = time.time() - start_time
    print(f"\nLogged {sample_count} samples over {duration:.1f}s → {args.output}")
    pynvml.nvmlShutdown()


if __name__ == "__main__":
    main()
