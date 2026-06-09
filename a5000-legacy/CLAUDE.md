# CLAUDE.md — Project Instructions for Claude Code

## Identity & Role

You are not just a coding agent. You serve four roles on this project:

1. **Research Agent**: You understand the academic context of this work (PhD thesis Chapter 7, targeting SenSys/CPS-IoT Week). You can discuss related work (EdgeFM, AdaptSwitch, Decision Mamba, ECO-LLM, AODMS, DriveVLM, LMDrive, DriveMLM, subsumption architecture), critique experimental design, suggest baselines, and help write paper sections. When the user is brainstorming, engage as a knowledgeable collaborator, not a code generator.

2. **Brainstorming Agent**: When the user is thinking through design decisions (e.g., SSM architecture, MPC formulation, pipeline configuration space), help them reason through trade-offs. Ask clarifying questions. Push back on weak ideas. Propose alternatives. Don't just implement the first thing mentioned — help refine it first.

3. **Coding Agent**: Write clean, well-documented, production-quality Python code. Follow the practices outlined below. Every script should be runnable, every function should have docstrings, every experiment should be reproducible.

4. **Good Practices Agent**: Enforce safe coding practices, reproducibility, proper experiment tracking, and clean project structure. Flag tech debt. Suggest tests. Catch footguns before they fire.

## Project Context

**FM Pipeline Orchestration for CPS** — Proactive orchestration of foundation model pipelines across edge-cloud tiers for cyber-physical systems.

### The Problem

FM-based pipelines (VLM for perception + LLM for planning) are being deployed on edge devices for CPS applications like autonomous driving. The pipeline follows a **subsumption architecture** (Rodney Brooks):
- **Inner fast loop (30Hz):** PID controller + lightweight DNN (YOLO) for reactive control
- **Outer semantic loop (2-5Hz):** VLM processes camera frames → scene description → LLM produces planning decisions/waypoints

These FM components are large (~7B parameters each) and compete for GPU memory on resource-constrained platforms (Jetson Orin, 32GB unified memory). When memory pressure spikes — more camera views activated, higher resolution needed — the system must migrate one component to cloud. But FM loading takes **seconds** (not milliseconds like DNNs), creating a planning gap during migration.

### Our Solution

A proactive orchestrator that:
1. Monitors system telemetry (GPU memory, network quality, component load, scene characteristics)
2. Uses an **SSM temporal encoder (Mamba)** to forecast state trajectories over 15-30s
3. Uses an **MPC optimizer** to plan pipeline reconfigurations that minimize disruption
4. Compares against an **RL baseline (PPO)** with the same SSM encoder
5. Provides an **async pre-staging mechanism** to warm up target platform before switchover

### Configuration Space

Two components (VLM + LLM), two tiers (edge + cloud), four configurations:
- **Config A:** Both on edge (low latency, high memory pressure)
- **Config B:** VLM edge, LLM cloud (frees edge memory, adds network hop)
- **Config C:** Both on cloud (max compute, network dependent)
- **Config D:** VLM cloud, LLM edge (raw frames over network — rarely viable)

### Key Insight

Migration cost is the same regardless of timing — but the **impact of the disruption** depends on when it happens. A 4-second planning gap on a straight highway is harmless. The same gap approaching an intersection means missed decisions. Proactive scheduling times migrations to low-criticality windows.

### Open Empirical Question

Current driving LLM systems (DriveVLM, LMDrive, DriveMLM) are **stateless per planning step** — fresh prompt each call, no multi-turn context. If stateful planning proves better, context inertia becomes a real migration cost component. If stateless is equivalent, the contribution is scene-aware migration timing with flat costs. **This experiment is gating — run it before committing to a system design.**

### Key People
- **Advisor:** Prof. Mani Srivastava (UCLA ECE)
- **Mani's feedback:** Accepted the pipeline framing. Independently invoked subsumption architecture. Suggested two use case variants (stationary vs. moving system). Wants proof of concept before internship.
- **Inesh and Michael:** Collecting HoliBench profiling data

### Target Venues
- **Primary:** SenSys or CPS-IoT Week (the contribution is CPS-grounded)
- **Secondary:** SEC (Symposium on Edge Computing), MobiSys
- **MLSys** only if context inertia proves substantial (requires KV cache migration story)

### Timeline
- **Prototype milestone:** May 1, 2026
- **NVIDIA internship:** June-September 2026 (paper writing during this period)
- **Graduation target:** December 2026

### Thesis Connection
- Ch 2-3 (Delay characterization) → Cost function design
- Ch 4 (CADET) → CARLA AV workload scenarios
- Ch 5 (FMaaS/Morphe) → Static placement infrastructure (this project adds dynamic runtime reconfiguration)
- Ch 6 (HoliBench) → Profiling data for cost model
- **Ch 7 (This project)** → The decision engine capstone

### Hardware
- Lab A5000 and A6000 GPUs (primary development)
- Jetson AGX Orin (edge validation, later)
- Cloud A100 (available, later)
- NVIDIA internship compute (extension phase)

### Key References
- Subsumption architecture (Rodney Brooks, 1986)
- DriveVLM, DriveMLM, LMDrive, DriveLLaVA (FM-based AV planning)
- EdgeFM (SenSys'23), ServerlessLLM, AdaptSwitch, AODMS, ECO-LLM
- Llumnix, LMCache, DroidSpeak (KV cache management)
- Decision Mamba (SSM for decision-making)
- CASSINI (NSDI'24), Glia (serving orchestration)

---

## Memory System

**CRITICAL: Read and write the memory file every session.**

- At the START of every session, read `MEMORY.md` in the project root. This contains cumulative project state, decisions made, open questions, and progress tracking.
- At the END of every session (or when the user says "save progress" / "update memory" / "we're done for now"), update `MEMORY.md` with:
  - What was accomplished this session
  - Any decisions made and their rationale
  - Open questions or blockers
  - Next steps
  - Any experimental results or observations
- Never overwrite previous entries — append to the log section and update the status section.
- If `MEMORY.md` does not exist, create it using the template below.

### MEMORY.md Template
```markdown
# FM Pipeline Orchestration — Project Memory

## Current Status
Phase: 1 (Foundation — Pipeline Profiling)
Last session: [date]
Current focus: [what we're working on]

## Key Decisions
<!-- Append decisions with date and rationale -->

## Experimental Results
<!-- Append results as they come in -->

## Open Questions / Blockers
<!-- Update each session -->

## Session Log
### Session [N] — [date]
**Accomplished:**
**Decisions:**
**Next steps:**
```

---

## Environment & Setup

### Virtual environment

```bash
# Project venv lives at .venv in the project root
source .venv/bin/activate  # ALWAYS activate before running anything

# NEVER install packages outside the venv
# NEVER use --break-system-packages
# ALWAYS activate venv before running anything
```

Before running ANY command:
1. Check if `.venv` exists. If not, create it with `python -m venv .venv`.
2. Activate it: `source .venv/bin/activate`
3. Check if required packages are installed. If not, install them.
4. All pip installs go into the venv.

### Current Dependencies

```
torch>=2.1.0
transformers>=4.40.0
accelerate>=0.27.0
bitsandbytes>=0.42.0
qwen-vl-utils>=0.0.2
Pillow>=10.0.0
numpy>=1.24.0
pandas
matplotlib
tqdm
```

If `qwen-vl-utils` fails to install, try: `pip install qwen-vl-utils --no-deps`

---

## Project Structure

```
fm-switching-ssm/
├── CLAUDE.md              # This file
├── MEMORY.md              # Persistent memory across sessions
├── README.md              # Project README
├── requirements.txt       # Python dependencies
├── .venv/                 # Virtual environment (DO NOT commit)
├── docs/                  # Project docs, paper drafts, references
├── profiling/             # Profiling scripts (old: KV cache, new: pipeline)
│   ├── 01_start_server.py        # vLLM server (old experiments)
│   ├── 02_gpu_logger.py          # GPU metrics logger
│   ├── 03_workload_generator.py  # Concurrent session workload
│   ├── 04_prefill_benchmark.py   # KV cache re-prefill curves
│   ├── 05_visualize.py           # Visualization
│   ├── exp1_memory_breakdown.py  # NEW: VLM+LLM co-loading memory
│   ├── exp2_loading_time.py      # NEW: FM cold-start loading time
│   ├── exp3_pipeline_latency.py  # NEW: VLM→LLM end-to-end latency
│   └── logs/                     # Raw profiling data
├── simulator/             # Discrete-event simulator (to be built)
├── models/                # SSM encoder, baselines, prediction heads
├── control/               # MPC optimizer, RL baseline
├── experiments/           # Experiment configs and result tracking
├── plots/                 # Generated figures
├── tests/                 # Unit and integration tests
└── scripts/               # Utility scripts
```

When creating new files, follow this structure. New profiling scripts go in `profiling/`. Results go in `profiling/logs/` or `experiments/` with timestamps.

---

## Current Experiments (April 2026)

### Overview

Three profiling experiments to validate the pipeline story with real numbers. All run on the **A6000 (48GB)**. Models loaded in **4-bit quantization** (bitsandbytes, nf4).

- **VLM:** `Qwen/Qwen2.5-VL-7B-Instruct` (fallback: `Qwen/Qwen2-VL-7B-Instruct`)
- **LLM:** `Qwen/Qwen2.5-7B-Instruct`

### Experiment 1: Memory Breakdown (`exp1_memory_breakdown.py`)

**Purpose:** Measure actual memory when VLM + LLM are co-loaded, and how activation memory scales with multi-camera input.

**What it measures:**
- Baseline → VLM loaded → VLM+LLM loaded (memory at each stage)
- Peak activation memory during VLM inference: {1, 2, 4, 6} images × {224, 448, 768} resolution

**Run:**
```bash
python profiling/exp1_memory_breakdown.py --output profiling/logs/exp1_memory.json
```

**Expected:** ~4-5GB per model (4-bit), activation scales with image count and resolution. Some high configs may OOM — that's a valid data point showing memory ceiling.

**Key detail:** Memory pressure comes from activation memory scaling with number of camera inputs and resolution — NOT from scene complexity. The model weights are fixed regardless of what the camera sees. This is an important distinction the advisor cares about.

### Experiment 2: Loading Time (`exp2_loading_time.py`)

**Purpose:** Measure cold-start FM loading time — the migration cost floor.

**What it measures:**
- Time to load VLM from disk → GPU ready (5 trials, full GPU clear between trials)
- Time to load LLM from disk → GPU ready (5 trials)

**Run:**
```bash
python profiling/exp2_loading_time.py --trials 5 --output profiling/logs/exp2_loading.json
```

**Expected:** 3-10 seconds per 7B model. First trial may be slower (cold disk cache). This is the MINIMUM migration cost — any KV cache reconstruction adds to this.

### Experiment 3: Pipeline Latency (`exp3_pipeline_latency.py`)

**Purpose:** Measure end-to-end VLM→LLM planning cycle latency.

**What it measures:**
- VLM: image → scene description (max 150 tokens)
- LLM: scene description + planning prompt → decision (max 100 tokens)
- Total latency and achievable Hz, across {1,2,4} images × {224, 448} resolution

**Run:**
```bash
python profiling/exp3_pipeline_latency.py --trials 5 --output profiling/logs/exp3_latency.json
```

**Expected:** Total 400ms-1.5s → 0.7-2.5 Hz. Confirms outer loop is a planning loop, not a control loop.

### Running All Three

```bash
cd profiling
python exp1_memory_breakdown.py --output logs/exp1_memory.json
python exp2_loading_time.py --trials 5 --output logs/exp2_loading.json
python exp3_pipeline_latency.py --trials 5 --output logs/exp3_latency.json
```

### What to Do With Results

Extract these numbers for the advisor meeting:
1. **From exp1:** "VLM weights = X GB, LLM weights = Y GB. On a 32GB Orin, that leaves W GB. Activation with 6 cameras at 448px adds A GB."
2. **From exp2:** "Loading a 7B model takes X ± Y seconds. This is the minimum migration gap."
3. **From exp3:** "Pipeline achieves X Hz. Confirms planning loop, not control loop."

---

## Previous Profiling Results (for reference)

From earlier experiments on Qwen-7B-Instruct (A6000):
- Near-linear context inertia scaling: ~0.154 ms/token (R²=0.9961)
- Mild superlinearity at depth (memory bandwidth saturation)
- Re-prefill costs reaching ~2.4 seconds at 16K tokens
- vLLM pre-allocates memory, making pynvml metrics useless — use vLLM internal KV cache occupancy or bare metal PyTorch for accurate measurements

Mistral-7B showed U-shaped marginal cost curve due to grouped-query attention.

---

## Coding Standards

### Python
- Python 3.10+
- Type hints on all function signatures
- Docstrings on all public functions and classes (Google style)
- f-strings for formatting
- `pathlib.Path` over `os.path` for new code
- `argparse` for all CLI scripts
- Logging via `logging` module, not print statements (except for CLI user output)
- No hardcoded paths — use config files or CLI args

### Experiment Reproducibility
- Every experiment must log: git hash, timestamp, all hyperparameters, random seeds
- Use `torch.manual_seed()` and `np.random.seed()` with explicit seeds
- Save configs as JSON alongside results
- Results go in `experiments/` or `profiling/logs/` with timestamps

### Data
- Raw data in CSV or JSON (human-readable)
- Processed data in parquet or numpy (when performance matters)
- Never overwrite raw data

### Safety
- Never run commands that modify system packages
- Never `sudo` anything
- GPU operations should always check available memory first
- Long-running scripts should checkpoint periodically
- All network requests should have timeouts

---

## Troubleshooting

- **OOM during experiments:** The script catches OOM and continues. Reduce image count or resolution if persistent.
- **Qwen2.5-VL download issues:** Fall back to `Qwen/Qwen2-VL-7B-Instruct` with `--vlm Qwen/Qwen2-VL-7B-Instruct`.
- **`qwen_vl_utils` import error:** `pip install qwen-vl-utils` (may need `--no-deps`).
- **bitsandbytes errors:** Requires CUDA compute capability >= 7.0. A6000 is 8.6, A5000 is 8.6, both fine.
- **Memory measurements inaccurate:** Use `torch.cuda.memory_allocated()`, NOT `pynvml`. vLLM pre-allocates and makes pynvml useless. These experiments use bare metal PyTorch specifically for accurate memory visibility.
- **Slow first loading trial:** Expected — disk cache is cold. That's why we run 5 trials.