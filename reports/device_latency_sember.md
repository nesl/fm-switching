# On-device latency (S-EMBER, DEV-RECENT inputs) — design ready; BLOCKED on gated video access

**Date:** 2026-10-17 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp commit `c0fd786` (CUDA sm_87)

**Status:** The device input construction (DEV-RECENT) is defined, calibrated, and verified; the 120-question sample is drawn; the runtime estimate is ~2.4 h (< 8 h, no cuts). **The timing runs (STEP 4) are BLOCKED**: the S-EMBER videos cannot be obtained on this box — `facebook/S-EMBER` is a gated HF dataset, the only stored HF token is **invalid**, the A6000 is unreachable (no name resolution, no shared filesystem), and no video decoder is installed. Awaiting a valid HF token with S-EMBER access (and I will pip-install PyAV into the venv, no root needed).

> **Supersedes the earlier STEP-1 STOP in this file.** Per your decision we are NOT reproducing Study O's HF video construction; the device defines its own image-path construction (DEV-RECENT) and the A6000 will mirror it for accuracy. The earlier Study-O-video-match analysis is retained in git history.

---

## STEP 0 preflight
GPU free (GR3D 0%, 0 other sessions, no foreign procs); any prior llama-server stopped. **MAXN (mode 0)**, 12 CPUs, **GPU 1.3005 GHz** (sudo not passwordless → `jetson_clocks` not re-issued; already at max per sysfs, unchanged). JetPack/L4T **R36.5.0**, CUDA **12.6**. RAM 51 GB free, disk 23 GB free. `git pull`: at `origin/main` (0/0). *Note:* the Track-A probe + Step-1 report you mentioned committing are **not on origin** (origin still at `2609a2a`) and remain uncommitted in this working tree — likely committed on flash and not yet pushed; flagged for you.

## STEP 2 — DEV-RECENT definition (module `experiments/device/dev_inputs.py`, importable by the A6000)
- **Frames:** uniformly spaced over `[question_time − 120 s, question_time]` (no frame after `question_time`), in time order, passed to llama.cpp as **separate images** (no temporal merging — this is the device's own construction, deliberately not Study O's HF video path). Each image is preceded in the prompt by its timestamp as `[t=XXs]`.
- **Resolution:** every frame resized to exactly **560×560** with `PIL.Image.resize((560,560), LANCZOS)` (aspect not preserved; fixed square → per-frame visual-token count is constant, content- and source-independent).
- **Budget / N:** calibrated against this build's llama-server tokenizer — a 560×560 frame + its `[t=XXs]` marker costs **332 tokens** (measured 5f=1823, 15f=5142, 30f=10123 → 332/frame, ~163 text/overhead intercept). **N = 37** is the largest frame count with `37×332 + text ≤ 12,500`; when the window is shorter than 120 s or rounding collapses timestamps, N is smaller (per-question).
- **Prompt / answer:** copied verbatim from `experiments/sember/study_o_q4.py` (`"Watch the video carefully, then answer the following multiple-choice question.\n\nQuestion: … \n\n<options>\n\nReply with only the letter of the correct answer (A, B, C, D, or E)."`), with the per-frame `[t=XXs]` markers added.

**Verification (3 questions, total input tokens ≤ 12,500 confirmed):**
| qid | question_time | N | total input tokens | frame timestamps |
|---|---|---|---|---|
| `003969ab…` | 46 s | 36 | 12,155 | 0…46 s (1 s spacing; window < 120 s) |
| `00ac6f93…` | 285 s | 37 | 12,493 | 165…285 s (120 s window) |
| `00c92b5c…` | 579 s | 37 | 12,468 | 459…579 s (120 s window) |

## STEP 3 — sample
Stratified sample of **120 / 845** RECENT questions (seed 0; 16 strata = 8 `question_category` × `evidence_covered`), proportional allocation, saved to `results/device/latency_sember_sample.json`. Spans **97 unique videos** (fetch/decode will dominate wall-clock). Plan: fetch one video → extract that video's DEV-RECENT frames (cached as small 560×560 PNGs, reused across all model phases to avoid re-downloading 97 videos 3×) → delete the video → ≤ 2 videos on disk at a time.

## STEP 6 — runtime estimate (before any run; < 8 h, no cuts)
From the 845 4B-T trials in `study_o_q4_trials_fa2.jsonl`: generation **median 206 tokens, mean 426, p90 897, max 8192; budget-hit 0.6%** — generations are short, so **prefill (~12,450 tok ÷ ~800 tok/s ≈ 15.6 s/question) dominates**. With F16 decode ≈ 14.5 tok/s (half of Q8_0's measured 29) and Q8_0 ≈ 29:
| phase | model | n | est |
|---|---|---|---|
| 4a | 4B-T F16 (think, max 16384) | 120 | ~1.5 h (mean-gen based) |
| 4b | 4B-I F16 (greedy, max 512) | 120 | ~0.6 h |
| 4c | 4B-T Q8_0 (think) | 40 | ~0.3 h |
**Total ≈ 2.4 h inference** (+ ~1–3 h of 97-video fetch/decode overhead). Under 8 h → proceed without cuts once unblocked.

---

## BLOCKER (STOP) — gated S-EMBER video access
- `facebook/S-EMBER` is a **gated** HF dataset; file download returns **401 Unauthorized**.
- The stored token (`~/.cache/huggingface/token`) is **invalid** ("Invalid user token").
- The **A6000 is unreachable** from this box (no DNS resolution for `flash`, no shared filesystem) → no rsync fallback.
- **No video decoder** installed (no PyAV/cv2/ffmpeg) — I will `pip install av` into the venv (no root) once videos are reachable.

**To unblock:** provide a valid HF token with `facebook/S-EMBER` access, e.g. `! hf auth login` (or set `HF_TOKEN`). Then I install PyAV, run STEP 4 (all three phases), and complete this report with the per-configuration latency tables, evidence_covered/category splits, a streamed-trace excerpt, and secondary on-device accuracy.

**Fallback if videos stay inaccessible (your call):** run the latency characterization with **placeholder 560×560 frames** (COCO) but the **real questions**. This yields faithful **prefill, TTFT, decode tok/s, peak memory, and throttling** (all content-independent at fixed resolution), but **not** real think-length, total latency, or accuracy (those depend on the model seeing the actual S-EMBER frames). It would measure the device's hardware latency envelope, clearly labelled as placeholder-content.

## Runtime facts already established (this box, `reports/device_runtime_probe.md`)
llama.cpp Q8_0 decode **28.8 tok/s**, TTFT ~0.09 s, abort 0.002 s, forced answer + 12× prefix-cache reuse. The runtime is ready; the only blocker is S-EMBER video access.
