# Device runtime probe — Qwen3-VL-4B-Thinking on Jetson AGX Orin

**Date:** 2026-10-17 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Status:** Track A step 4 COMPLETE; Track A step 5 (bf16 parity) BLOCKED on-device; Track B (vLLM) not started (gated behind this report per the chosen plan).

This is the gate report. It covers **Track A (llama.cpp)**. Track B and Track A step 5 are open decisions at the end.

---

## 1. Device & stack configuration (as reported at start)

| item | value |
|---|---|
| GPU availability | **free** — GR3D 0%, no foreign processes, nobody else logged in |
| JetPack / L4T | R36.5.0 (JetPack 6.2) |
| CUDA | 12.6 (nvcc V12.6.68) |
| Power mode / clocks | **MAXN (mode 0)**, 12 CPUs online, **GPU pinned 1.3005 GHz** (jetson_clocks state persisted from a prior session; passwordless sudo unavailable this session so `sudo jetson_clocks` was not re-issued — device verified already at max via sysfs) |
| RAM | 61 GB total, ~51 GB free at start |
| Disk | 57 GB eMMC; freed 25 GB of stale Study-F Instruct caches → ~28 GB free before builds, 23 GB after |

**Build fix worth recording:** JetPack ships the cuBLAS *runtime* but not the *dev* package (`libcublas-dev-12-6`), so llama.cpp's CUDA backend would not configure (`CUDA::cublas` not found, no `cublas_v2.h`). `sudo apt install` was not possible (no passwordless sudo). Resolved **without root**: `apt-get download libcublas-dev-12-6` (228 MB, no root), `dpkg-deb -x` into a user prefix, and a merged writable CUDA root at `~/cuda_local` (system CUDA symlinked + cuBLAS headers/libs/`.so` overlaid) passed to cmake via `-DCUDAToolkit_ROOT`. Also `cmake -DCMAKE_CUDA_FLAGS="-cudart shared"` because only the shared `libcudart` is installed (no static archive).

---

## 2. Track A — llama.cpp

### Build
- Source: `github.com/ggml-org/llama.cpp`, **commit `c0fd78626405c6d9b934efef0ec7291fcc20e3d6`** (version 0.7.0-dev, build b11714).
- Config: `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87 -DCMAKE_CUDA_FLAGS="-cudart shared" -DCUDAToolkit_ROOT=~/cuda_local -DLLAMA_CURL=ON`.
- `llama-server` links `libggml-cuda.so`, `libcudart.so.12`, `libcublas.so.12` — CUDA backend confirmed. (`llama-mtmd-cli` target name changed in 0.7.0-dev and did not build; not needed — the server carries multimodal via `--mmproj`.)
- Note: OpenSSL absent → llama-server's built-in HTTPS model download disabled; irrelevant, models fetched via HF hub.

### Models (hashes recorded)
| file | size | sha256 |
|---|---|---|
| `Qwen3VL-4B-Thinking-Q8_0.gguf` (LM) | 4.28 GB | `7c6f9a84ef6d4d62500f6a68a35df26e9abe31833bb6b9c812970593b09525cb` |
| `mmproj-Qwen3VL-4B-Thinking-F16.gguf` | 0.84 GB | `b8b81037542461bd874e66cfc2c72d3c7e50007cb4ed5b37257474e031b405c6` |

Repo `Qwen/Qwen3-VL-4B-Thinking-GGUF`. Model load warned: *"Qwen-VL models require ≥1024 image tokens for grounding; try `--image-min-tokens 1024`"* — left at default for the counting probe (not a grounding task); **flag for the parity step**, where it should match whatever the reference run used.

### Server invocation
```
llama-server -m <Q8_0> --mmproj <mmproj-F16> -ngl 99 -fa on -c 16384 \
  --jinja --reasoning-format deepseek \
  --temp 1.0 --top-p 0.95 --top-k 20 --presence-penalty 0.0
```
`-fa on` = flash attention (accepted, server ran). Resident RSS 9.21 GB. **`--reasoning-format deepseek` splits thinking into `delta.reasoning_content` and the answer into `delta.content`** — reasoning is cleanly separable in the stream (confirmed: 139 reasoning deltas then 1 answer delta on a counting item).

### Step 4 — probe results (`experiments/device/llamacpp_stream_probe.py` → `results/device/llamacpp_probe.json`)

Caching: server default prompt-caching ON; cold vs cached prefill measured and labelled explicitly below.

**Streaming + per-token timestamps + reasoning/answer marking** — working. Example trace (single 560×560 image, "how many people?"):
```
 t=0.087s [reason] 'So'      t=0.121s [reason] ','     t=0.156s [reason] ' let'  ... → [answer] '2'
```
Inter-token interval ~34.7 ms, steady.

**Latency (single image, 3 reps):**
| metric | value |
|---|---|
| TTFT | 0.081–0.105 s |
| **decode tok/s (median over trace)** | **28.76** (reps 28.75/28.76/28.77) |
| prefill — cold (N=1, 350 prompt tok) | **430 ms** |
| prefill — warm/cache-hit (prefix reused) | **35 ms** |

**Abort (cancel stream after 40 reasoning tokens):** client disconnect → **server-side stop latency 0.002 s** (polled `/slots` `is_processing`→false). Working abort, near-instant server-side.

**Forced early answer (inject `</think>`):** raw `/completion` ending in the partial trace + `</think>\n\n` → answer emitted immediately (0.156 s, 2 decoded tokens). ⚠️ The raw `/completion` path did **not** carry vision tokens (prompt_n reflected text only), so this demonstrates the **forced-termination mechanism**, not a grounded answer. Image-grounded prefill reuse is shown separately:

**Prompt-cache reuse (image-grounded):** two identical chat requests — call 2 prefilled only **1 token in 35 ms** vs the cold **350 tokens in 430 ms** (12× reduction). Caching avoids re-prefilling the image+prompt prefix, which is the property the forced-answer flow needs.

**Multi-image scaling (1/8/16 images, one prompt):**
| images | prompt_n | prefill | decode tok/s (median) | RAM Δ (unified, noisy) |
|---|---|---|---|---|
| 1 | 350 | 430 ms | 28.75 | +77 MB |
| 8 | 2,303 | 2,775 ms | 27.28 | +111 MB |
| 16 | 2,629 | 3,361 ms | 25.72 | −6 MB (noise) |
Prefill scales ~linearly with prompt tokens; decode degrades only mildly with KV size (28.8→25.7). *Note:* S-EMBER video frames are not on this box, so this used COCO 560×560 frames — valid for a cost measurement because vision-token count is content-independent at fixed resolution (Study A). RAM deltas via tegrastats are unreliable on unified memory (flagged) — the real footprint signal is prompt_n (KV) + the 9.2 GB resident model.

### Step 4 verdict vs the gate rule
llama.cpp Q8_0 **meets every runtime criterion**: decode **28.8 tok/s ≥ 20** ✓ · streaming with timestamps ✓ · working abort (2 ms server-side) ✓ · forced answer ✓. The one open item is the **bf16 agreement** (quantization) check — step 5.

### Step 5 — accuracy parity: BLOCKED on-device
The Study O pool is **long S-EMBER video questions** (median ~121 frames, ~12,392 input tokens/question; 520 questions over 150 videos). **The frames/videos are not on this box** — only the trial output JSONL is. Running Q8_0-vs-bf16 parity on identical inputs on the Orin would require:
- fetching ~10 GB of S-EMBER video **and** the ~9 GB HF bf16 4B-Thinking weights — together exceeding the 23 GB free (GGUF already occupies ~5 GB);
- HF bf16 inference on ~12k-token multi-image prompts × 100 questions with long reasoning — many hours at the Orin's overhead-bound HF decode (~9 tok/s, per Study F) and OOM-prone at that prompt length.

Per the task's own fallback ("if HF bf16 cannot run on the Orin, say so"), **full on-device parity is not feasible**. Options are listed at the end; this does not change the runtime verdict, only leaves the quantization-agreement number pending.

### Recommendation so far
**llama.cpp Q8_0 is a passing device runtime** on all measured runtime criteria (28.8 tok/s, streaming+timestamps, abort, forced answer, 12× prefix-cache reuse). Final recommendation is conditional on the bf16 agreement check (step 5), which must run where the frames + bf16 fit (A6000), or via a documented local proxy.

---

## 3. Track B — vLLM from source
Not started. Chosen plan was "Track A first, gate before B" because vLLM-from-source on aarch64 is a multi-hour, disk-hungry (15–40 GB build), failure-prone build that does not fit alongside Track A's artifacts in 23 GB free. Decision pending below.

---

## Open decisions (STOP)
1. **Step 5 parity:** (a) run Q8_0-vs-bf16 on flash/A6000 where frames+bf16 fit; (b) a scoped on-device proxy on local ground-truth images (e.g. COCO counting) measuring Q8_0 vs bf16 agreement + Q8_0 run-to-run flip rate; or (c) defer and accept the runtime-only verdict.
2. **Track B:** attempt the vLLM-from-source build (needs disk headroom management), or stop at the llama.cpp recommendation.
