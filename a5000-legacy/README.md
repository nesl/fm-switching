# FM Switching with SSM — Phase 1 Profiling

## Goal

Profile Mistral-7B on the A6000 to produce three empirical datasets:

1. **KV cache growth** — how context depth accumulates across concurrent sessions over time
2. **GPU utilization** — memory, compute, power under concurrent load
3. **Context inertia curve** — cold re-prefill cost as a function of session depth

Dataset 3 is the primary output. It characterizes the migration penalty that makes
reactive FM switching suboptimal and motivates the SSM-based proactive controller.

---

## Critical Concept: Two Kinds of Latency

These scripts produce **two fundamentally different latency measurements**. Confusing
them downstream (in the simulator, in paper figures, in cost models) would invalidate
your results. Understand the distinction before you touch the data:

### Incremental serving latency (`session_traces.csv` → `incremental_latency_s`)

Measured by `03_workload_generator.py`. This is the round-trip time for one turn of
an ongoing conversation **where the KV cache is already warm on the server**.

vLLM's prefix caching means the server already holds the KV activations for all prior
turns. Only the new user message needs to be prefilled. So latency at turn 15 is much
lower than the latency you'd see if the session had to start from scratch.

**What this tells you:** How inference serving cost grows as a session deepens. Useful
for understanding when a session becomes expensive to keep alive on a resource-constrained
platform — i.e., when the *serving* cost motivates offloading.

**What this does NOT tell you:** How much it costs to migrate the session. A session
with 8,000 tokens of context might have 200ms incremental latency but 4,000ms migration
cost. These are different numbers.

### Cold re-prefill cost / context inertia (`prefill_cost_curve.csv` → `prefill_time_ms`)

Measured by `04_prefill_benchmark.py`. This is Time to First Token (TTFT) when the
**full conversation history is submitted from scratch** to a server with no prior KV cache.

This simulates what happens during migration: the target device receives the session
transcript and must recompute all KV activations before it can generate a single token.
The cost grows with context depth — this is your **context inertia curve**.

**What this tells you:** The migration penalty at each context depth. This is the primary
input to your MPC cost function and the central empirical claim of the paper.

**Measurement note:** Script 04 uses streaming mode and records the timestamp when the
first token chunk arrives (true TTFT), not when the full HTTP response completes.
The server is started with prefix caching **disabled** so every measurement is a cold
computation, not a cache hit.

---

## Setup

```bash
# Use the project venv (Python 3.10 required — vLLM does not support 3.13)
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify GPU visibility:
```bash
nvidia-smi
# You should see GPU 0: RTX 3090 Ti (24GB) and GPU 1: RTX A6000 (48GB)
# All scripts default to GPU 1 (A6000)
```

---

## Running the Profiling Pipeline

Open **three terminals**, all from the `profiling/` directory with the venv activated.

### Terminal 1 — Inference server (blocks until you Ctrl+C)

```bash
cd profiling/
source ../.venv/bin/activate
python 01_start_server.py
# Auto-selects Mistral-7B-Instruct-v0.2 on A6000 (GPU 1)
# Prefix caching OFF by default — required for accurate inertia benchmarking
# Wait for: "Uvicorn running on http://0.0.0.0:8000"
```

### Terminal 2 — GPU metrics logger (run concurrently with everything else)

```bash
source ../.venv/bin/activate
python 02_gpu_logger.py
# Polls A6000 every 100ms → logs/gpu_metrics.csv
# Flushes to disk every ~10s (crash-safe)
# Stop with Ctrl+C when all experiments are done
```

### Terminal 3 — Experiments (run sequentially)

```bash
source ../.venv/bin/activate

# Step 1: Prefill benchmark — THE KEY MEASUREMENT, run this first
# Measures cold re-prefill TTFT at 8 context depths (3 repeats each)
python 04_prefill_benchmark.py

# Step 2: Workload generator — concurrent session simulation
# 4 sessions × 15 turns, runs ~10-20 min depending on model speed
python 03_workload_generator.py

# Step 3: Visualize — generate all plots from collected logs
python 05_visualize.py
```

> **Why script 04 before script 03?** The inertia benchmark needs a cold server with
> no cached prefixes. Running the workload generator first populates the KV cache and
> may interfere with subsequent prefill measurements even with prefix caching disabled
> (GPU memory state, thermal throttling). Start fresh.

---

## Output Files

| File | Produced by | Latency column | What it means |
|------|-------------|----------------|---------------|
| `logs/gpu_metrics.csv` | `02_gpu_logger.py` | — | GPU utilization, memory, power over time |
| `logs/session_traces.csv` | `03_workload_generator.py` | `incremental_latency_s` | Per-turn serving latency with warm KV cache. Shows how serving cost scales with depth. **Not migration cost.** |
| `logs/prefill_cost_curve.csv` | `04_prefill_benchmark.py` | `prefill_time_ms` (TTFT) | Cold re-prefill time at each context depth. **This is context inertia.** Direct input to MPC cost function. |

---

## Plots

| Plot | Source data | What to look for |
|------|-------------|-----------------|
| `plots/gpu_metrics.png` | `gpu_metrics.csv` | Memory jump when model loads, utilization spikes during prefill, sustained lower utilization during decode |
| `plots/session_traces.png` | `session_traces.csv` | Context growth rate varies by session type; incremental latency rises but slowly (cache helps) |
| `plots/context_inertia_curve.png` | `prefill_cost_curve.csv` | **The money plot.** Migration cost vs depth. If roughly linear → predictable. If superlinear → deeper sessions penalize migration disproportionately (stronger motivation for early proactive migration) |

---

## Known Limitations

- **Synthetic assistant responses in script 04**: Prefill benchmark uses repeated filler
  text for assistant turns. Token counts are accurate but activation patterns are more
  uniform than real conversations. Complement with real traces from script 03 for
  final paper figures.

- **Single GPU, single model**: Phase 1 profiles Mistral-7B on A6000 only. Phase 2
  will add the Jetson AGX Orin and a second model variant to measure cross-device
  and cross-model migration costs.

- **No actual KV cache transfer**: Scripts measure re-prefill cost (recompute from
  transcript), not KV cache serialization + network transfer + deserialization. The
  full migration pipeline will be characterized in Phase 2.
