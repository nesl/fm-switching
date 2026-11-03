# On-device one-frame measurement + identical-input manifest (Jetson AGX Orin)

**Date:** 2026-11-03 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp `c0fd786` (CUDA sm_87) · **E-id:** StudyDevOne

**Goal.** Record the N=1 (one-frame) device latency/energy and the exact image payloads (N=37/18/9/1) so the H100 can run byte-identical inputs. Jetson only; MAXN mode 0, GPU pinned 1.3005 GHz (verified and logged per request). Warm-up logged separately and excluded.

---

## Results (Part 2) — N=1 cold latency / energy / accuracy

**4B-Instruct F16, greedy, max 512, one request at a time, `cache_prompt=false` (COLD prefill), N=1 payload in the same prompt format as N=37.** 120 questions. Energy = per-request trapezoidal integral of total board power (sum of 3 INA3221 rails, 100 ms sampling); 60 s loaded-idle baseline.

| metric | N=1 cold (median / p90 / max) |
|---|---|
| input tokens (prompt_n) | 468 / 530 / 794 (min 410) |
| prefill ms | 445 / 467 / 580 |
| **TTFT s** | **0.506 / 0.536 / 0.645** |
| **total latency s** | **0.56 / 0.59 / 0.70** |
| generated tokens | 2 / 2 / 2 |
| **energy J/req** | **19.3 / 20.5 / 25.3** (min 13.6) |
| active power W | 34.6 (vs **9.94 W** loaded-idle) |
| GPU-rail energy J | 13.8 (≈71 % of board) |
| **accuracy (indicative)** | **12.5 % (15/120), Wilson-95 [7.7 %, 19.6 %]** |

Prefill rate 1,053 tok/s (median). Clock pinned at 1.3005 GHz on **all 130 logged requests** (0 bad). `cached_n = 0` on every row. Peak RAM 25.9 GB. tj_max 55.2 °C (cooler than the longer-input studies — N=1 requests are too short to heat the GPU). No throttle.

**Control gate — PASS.** 10 × N=9 (StudyDevFast conditions): TTFT median **3.881 s** vs corrected StudyDevFast **3.80 s** → ratio **1.021**, within 10 %. The device/harness reproduces StudyDevFast.

### Reading

- **N=1 is fast but insufficient.** A single most-recent frame answers in **0.51 s TTFT / 0.56 s total** at **19 J** — ~7× faster and ~8× cheaper than N=9 (3.9 s / 159 J). But **accuracy is 12.5 %, below the 20 % random baseline** for a 5-way MCQ: one frame carries too little of the 120 s window to answer these RECENT questions. The Wilson interval [7.7, 19.6 %] sits entirely at or below chance.
- **Completes the frame-count sweep** (Instruct, same sample). TTFT scales ~linearly-to-slightly-superlinearly with prompt tokens; accuracy rises with frames:

  | N | input tok | TTFT s | total latency s | energy J | accuracy (indic.) |
  |---|---|---|---|---|---|
  | 1 | 468 | 0.51 | 0.56 | 19 | 12.5 % |
  | 9 | 3,130 | 3.79 | 3.9 | 159 | 28 % |
  | 18 | 6,123 | 7.76 | 7.8 | 332 | 30 % |
  | 37 | 12,420 | 16.98 | 17.0 | 749 | 34 % |

  (N=9/18/37 from StudyDevFast.) Per-token prefill cost rises gently with length (1.08 → 1.37 ms/tok from N=1 → N=37) — the attention-quadratic term. **The useful fast-path floor is N=9** (≈4 s, 28 %), not N=1: dropping to one frame buys ~3 s but forfeits all task signal.

---

## Part 1 — identical-input manifest

`results/device/identical_input_manifest.json` (1.36 MB) records, for each of the 120 questions × N ∈ {37, 18, 9, 1}: frame timestamps, **sha256 of each 560×560 PNG payload**, width/height, byte size, and the `[t=Xs]` marker, plus a sha256 of the question text. N=37/18/9 use the StudyDevFast selection (all cached frames at N≥available; nearest-available subset otherwise); **N=1 is the frame at or nearest-before `question_time`**. Frame counts: N=37 median 37 (min 14 for short windows), N=18 median 18 (min 14), N=9 all 9, N=1 all 1.

The PNG bytes themselves live in Orin scratch (`devrecent_frames`); the manifest's per-frame sha256 is the verification key so the H100 can confirm it is running **byte-identical** inputs after the frames are transferred to it.

---

## Part 3 — reachability to the H100 (`sn4622120321`)

**The Orin cannot reach the H100 host as configured.** Without installing anything or changing network settings:

- **Name resolution FAILS:** `sn4622120321` does not resolve — no DNS entry, no `/etc/hosts` record, no `~/.ssh/config` alias (`gaierror: Temporary failure in name resolution`).
- Consequently `ping`, `ip route get`, and TCP probes (ports 22 / 8000 / 8080) all fail at resolution.
- **Transfer tools ARE already installed** (no install needed): `iperf3`, `nc`, `ssh`, `scp`, `rsync`, `curl`.

**Conclusion (stop this part):** the identical-input transfer path is not usable from this Orin until the host is made resolvable/routable (an IP, an `/etc/hosts` line, or an ssh-config alias — a change the user must authorize). The tooling for the transfer and a throughput test is present on the Orin side; only addressing/routing is missing. Raw result in `results/device/dev_one_reachability.json`.

---

## Results consistency check (6 checks)

**1. Cross-check vs committed — PASS.** Control N=9 TTFT median 3.881 s vs StudyDevFast 3.80 s (ratio 1.021, ≤10 %). N=1 is a new operating point (no prior); it extends the StudyDevFast Instruct curve monotonically (TTFT 0.51 < 3.79 < 7.76 < 16.98 s; energy 19 < 159 < 332 < 749 J).

**2. Physical plausibility — PASS.** N=1 prefill 1,053 tok/s = 1.3× the StudyDevFast N=9 rate (826 tok/s) — below the 2× flag, and *expected*: a shorter sequence pays less of the attention-quadratic penalty (per-token prefill 1.08 ms at N=1 vs 1.37 ms at N=37). TTFT ratio N=9/N=1 = 7.7× for a 6.7× token ratio — consistent slightly-superlinear scaling. `cached_n = 0` on all rows rules out a caching artifact. Energy satisfies `J ≈ W × s` by construction.

**3. Distribution sanity — PASS.** N=1 metrics are tight (TTFT IQR 0.029 s, energy IQR 1.3 J) — but this is **expected**, not short-circuiting: the N=1 input is near-constant (1 frame + short text), so low variance is correct. The spread that exists tracks question-text length (prompt_n 410–794).

**4. Definition audit — PASS.** N=1 = frame at/nearest-before qt (documented). `cache_prompt=false` ⇒ cold prefill, labelled. Energy = sum of 3 INA3221 rails (no VDD_IN on this Orin, as in StudyDevFast). GPU clock read from sysfs per request. **prompt_n verification:** every row prefilled the full prompt — `cached_n = 0` everywhere and min prompt_n = 410 ≫ a text-only prompt (~80–160 tok), i.e. the 332-token frame is always counted (no truncation, no cache hit). The 27 rows flagged >10 % from the prompt_n median are legitimate longer-option-text questions, not anomalies.

**5. Claim linkage — PASS.** Bears on the physical component of Context Inertia (latency/energy grow with context length): N=1 is the **floor** of the device curve, and the full {1,9,18,37} sweep shows TTFT ~linear in tokens with a small quadratic term. The manifest + sha256 enables the planned cross-tier (H100) identical-input comparison. No scoped-out quantity measured.

**6. Proxy validity — stated.** Accuracy is **indicative only** (A6000 is the reference via shared `dev_inputs.py`); the 12.5 % N=1 figure is on-device DEV-RECENT 5-way MCQ. Manifest sha256 is a verification proxy — it confirms frame identity but the PNG bytes must still be transferred to the H100 (Part 3: no current route). N=18/9 frames are nearest-available subsets of the cached N=37 frames (documented); N=1 is the single at/nearest-before-qt frame.

**Mechanism verification:** N/A — runtime latency + energy measurement + manifest, no causal claim (same as StudyDevFast / StudyDeviceLatency-sember); Steps 1–5 do not apply.

**STOP gates:** none tripped — control passed (ratio 1.021), clock correct (0 bad rows), total runtime ≈ 12 min (≪ 2 h).

---

## Files

- Harness: `experiments/device/study_dev_one.py` (reuses `dev_fast_latency.py`, `dev_inputs.py`).
- Manifest: `results/device/identical_input_manifest.json`.
- Per-request: `results/device/dev_one_n1.jsonl` (120, incl. energy), `dev_one_control_n9.jsonl` (10), `dev_one_warmup.json` (excluded).
- Energy trace: `results/device/dev_one_tegrastats.jsonl.gz`. Aggregates: `dev_one_stats.json`, `dev_one_summary.json`, `dev_one_control_result.json`. Reachability: `dev_one_reachability.json`.
- Model sha256 (verified in StudyDevFast): `results/device/model_hashes.txt`.
