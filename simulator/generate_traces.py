"""
Step 1: Generate workload traces.

Reads existing exp2/exp5 result JSONs if present (to extract real per-cycle
VLM measurements). Then writes 3 synthetic 100-cycle workload traces using
measured cost-model parameters from cost_model.py.
"""

import csv
import json
import random
from pathlib import Path

from cost_model import (FP16, INT4, KV_GROWTH_MB_PER_CYCLE,
                        TOKENS_PER_CYCLE_FULL)

ROOT = Path(__file__).parent
RESULTS = ROOT.parent / "results"
OUT = ROOT / "traces" / "workload"
OUT.mkdir(parents=True, exist_ok=True)


def maybe_load_real_traces():
    """If exp5 JSON files exist, extract per-cycle VLM/LLM data so we have a
    'real' reference trace alongside the synthetic ones."""
    out_dir = ROOT / "traces" / "real"
    out_dir.mkdir(parents=True, exist_ok=True)
    pulled = []
    for tag, path in [
        ("exp5_fp16_13gb", RESULTS / "exp5_fp16_13gb.json"),
        ("exp5_int4_13gb", RESULTS / "exp5_int4_13gb.json"),
    ]:
        if not path.exists():
            print(f"  (skip) {path} not found")
            continue
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            print(f"  (skip) {path} parse error: {e}")
            continue
        vlm_records = data.get("vlm_records", [])
        modes = data.get("modes", {})
        # Emit one CSV per (mode) using full-mode cycles for reference
        for mode_name, m in modes.items():
            cycles = m.get("cycles", [])
            if not cycles:
                continue
            csv_path = out_dir / f"{tag}_{mode_name}.csv"
            with csv_path.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["cycle", "vlm_latency_s", "llm_prefill_ms",
                            "llm_decode_ms", "llm_total_ms",
                            "context_tokens", "peak_memory_mb"])
                for c in cycles:
                    vlm_lat = (vlm_records[c["cycle"]]["vlm_latency_ms"] / 1000.0
                               if c["cycle"] < len(vlm_records)
                               and "vlm_latency_ms" in vlm_records[c["cycle"]] else None)
                    w.writerow([c["cycle"], vlm_lat, c.get("prefill_ms"),
                                c.get("generation_ms"), c.get("total_ms"),
                                c.get("prompt_tokens"), c.get("peak_mb")])
            pulled.append(csv_path)
            print(f"  Wrote {csv_path.relative_to(ROOT)}")
    return pulled


def write_synthetic(name, n_cycles=100, vlm_fn=None, seed=0):
    """vlm_fn(i) -> vlm_latency_s for cycle i. Default = constant FP16 mean."""
    rng = random.Random(seed)
    if vlm_fn is None:
        vlm_fn = lambda i: FP16["vlm_mean_s"]

    path = OUT / f"trace_{name}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "vlm_latency_s", "llm_prefill_ms",
                    "llm_decode_ms", "llm_total_ms",
                    "context_tokens", "peak_memory_mb"])
        ctx = 161  # initial prompt tokens (system + first scene description)
        peak = FP16["weights_total_mb"]
        for i in range(n_cycles):
            vlm = vlm_fn(i)
            # Reference LLM costs: FP16 edge, full-accumulation mode
            prefill = FP16["llm_prefill_ms_per_token"] * ctx
            decode = FP16["llm_typical_decode_ms"] * 10  # 10 generated tokens
            total = prefill + decode
            w.writerow([i, round(vlm, 3), round(prefill, 2),
                        round(decode, 2), round(total, 2),
                        int(ctx), round(peak, 1)])
            ctx += TOKENS_PER_CYCLE_FULL
            peak += KV_GROWTH_MB_PER_CYCLE
    print(f"  Wrote {path.relative_to(ROOT)}")
    return path


def main():
    print("Step 1: workload traces")
    print("  Real exp data extraction:")
    maybe_load_real_traces()

    print("\n  Synthetic traces (100 cycles each):")
    rng = random.Random(42)

    # 1. steady — uniform scenes
    write_synthetic("steady",
                    vlm_fn=lambda i: FP16["vlm_mean_s"],
                    seed=1)

    # 2. variable — random walk in [7, 15]s
    def variable_fn(i):
        return 7.0 + rng.random() * 8.0
    rng2 = random.Random(42)
    write_synthetic("variable",
                    vlm_fn=lambda i: 7.0 + rng2.random() * 8.0,
                    seed=42)

    # 3. burst — mostly 9s, periodic 15s spikes every 20 cycles
    def burst_fn(i):
        if i > 0 and i % 20 == 0:
            return 15.0
        return 9.0
    write_synthetic("burst", vlm_fn=burst_fn, seed=7)

    print("\nStep 1 complete.")


if __name__ == "__main__":
    main()
