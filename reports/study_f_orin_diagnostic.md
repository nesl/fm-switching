# Study F (Orin diagnostic) — are Study E's two suspect numbers real, or stack artifacts?

**Date:** 2026-08-31 · **Device:** Jetson AGX Orin (nesl-orin-3, 64 GB) ONLY · Diagnostic, not a rerun.
Writes only under `results/vision/study_f_orin/` + this report + `experiments/vision/study_f_orin_diagnostic.py`.

**Both suspect numbers are confirmed measurement artifacts of the software stack, not device properties.**
- (a) decode ~9.4 tok/s identical for 4B and 8B → **framework per-token overhead floor (~106–110 ms/token)** in HF `generate()` with a dynamic cache. Not bandwidth. Not a device property.
- (b) 53.4 GB @ 6 frames + OOM @ 12 frames → **Study E's Orin `measure_full` omitted `torch.no_grad()`**, retaining the autograd graph. With `no_grad`, N=6 = 17.6 GB and N=12 = 18.7 GB, no OOM.

Raw data: `results/vision/study_f_orin/orin_part1.json`, `orin_part2.json`.

---

## 1. Device and stack configuration

| item | value |
|---|---|
| Power mode | **MAXN (nvpmodel mode 0)**, 12 CPUs online @ 2.2016 GHz |
| GPU clock | **pinned 1,300,500,000 Hz** (jetson_clocks max), verified via `/sys/.../17000000.gpu/devfreq/cur_freq` |
| Applied? | State verified identical to Study E via sysfs (no reboot since Study E, so MAXN + jetson_clocks persisted). Passwordless sudo was unavailable this session, so the commands were not re-issued; re-applying jetson_clocks at max is a no-op, and the state is confirmed identical — the comparison to Study E is valid. |
| JetPack / L4T | JetPack 6.2 / L4T R36.5.0 · CUDA 12.6 |
| torch / transformers | 2.8.0 / 5.10.2 |
| flash-attn | **absent** |
| triton | **absent** (blocks static-cache and `torch.compile` paths — see Part 1 C2/C3) |
| **Attention impl (asserted from loaded model, not config)** | **`sdpa`** for the LM and the vision tower, for both Qwen3-VL (4B/8B) and Qwen2.5-VL-7B (`config._attn_implementation` / `vision_config._attn_implementation`) |

---

## 2. Raw measurements

### Part 1 — decode: overhead-bound or bandwidth-bound?

Fixed 256-token decode (`min_new_tokens = max_new_tokens = 256`, EOS suppressed), one fixed image + prompt, 5 reps + 1 warmup, greedy. Bandwidth roofline uses **204.8 GB/s** (NVIDIA Jetson AGX Orin series datasheet: 256-bit LPDDR5 @ 3200 MT/s). Weight bytes measured from the loaded model.

| model | weights (total / LM-only) | roofline (total / LM) | C1 decode | ms/token | % of total roofline | CV |
|---|---|---|---|---|---|---|
| Qwen3-VL-4B-Instruct | 8.88 / 8.04 GB | 23.1 / 25.5 tok/s | **9.40 tok/s** | 106 | **40.7%** | 0.0012 |
| Qwen3-VL-8B-Instruct | 17.53 / 16.38 GB | 11.7 / 12.5 tok/s | **9.09 tok/s** | 110 | **77.8%** | 0.0014 |

- Prefill (TTFT): 4B 280 ms, 8B 435 ms. n_gen asserted == 256 in every run. Peak (256-tok decode): 4B 9.0 GB, 8B 26.7 GB.
- **C2 (static cache) and C3 (static + `torch.compile`): both FAILED — `TritonMissing: Cannot find a working triton installation`.** Static-cache and compiled decode paths require triton, which is not installed on this aarch64 stack. Per instructions I did not install it. Recorded and moved on.

**Reading.** The two models decode at essentially the same rate (9.40 vs 9.09 tok/s, 3% apart) despite a 2× weight difference. The 4B runs at only **40.7% of its 23.1 tok/s bandwidth roofline** — a bandwidth-bound 4B decode would be ~23 tok/s. Per-token time is **106–110 ms for both** — a fixed floor. Bandwidth-bound decode would put the 4B at ~2× the 8B's rate; instead both are pinned near a ~106 ms/token ceiling. This is the signature of a fixed per-token overhead (Python dispatch + per-token kernel launches + dynamic-cache growth), exactly as the background arithmetic predicted (~106 ms floor).

### Part 2 — where does the memory go?

Qwen2.5-VL-7B, Study B frames (synthetic 560×560, 400 vision tok/frame) and query. Memory instrumented by phase with `torch.cuda.max_memory_allocated`/`max_memory_reserved` **and** a 20 ms background sampler of system RAM (`/proc/meminfo`, the unified-memory ground truth). All forwards under `torch.no_grad()`. Vision frames are encoded in **one batched `visual()` call** (patch-attention could be O(total_patches²)).

Weights after load: **torch counter 16.58 GB, but system-RAM delta only 8.52 GB** (see unified-memory caveat, §3).

| N | patches | input tok | vision-only peak | **full-call peak** | reserved | **RAM Δ (peak)** | unaccounted |
|---|---|---|---|---|---|---|---|
| 1 | 1,600 | 435 | 16.68 GB | 16.77 GB | 16.92 GB | 0.33 GB | 0.18 GB |
| 3 | 4,800 | 1,239 | 16.88 GB | 17.11 GB | 17.54 GB | 0.51 GB | 0.53 GB |
| 6 | 9,600 | 2,445 | 17.18 GB | **17.64 GB** | 18.55 GB | 0.95 GB | 1.06 GB |
| 12 | 19,200 | 4,857 | 17.76 GB | **18.67 GB** | 20.43 GB | 1.76 GB | 2.08 GB |

Full-call peak grows **linearly and gently** with N (16.8 → 18.7 GB from N=1 to N=12); **N=12 does not OOM.** The vision-tower phase alone is barely above the weights (17.2 GB @ N=6). Analytical expectation (≈16.6 GB weights + ~140 MB KV @ N=6 ≈ 16.7 GB) matches within ~1 GB of activation. (Measured KV came back 0 because the `Cache` API changed in transformers 5.10.2 — `key_cache` attribute absent; analytical KV = 140 MB @ N=6, immaterial to the peak.)

**Reproduction of the 53.4 GB (the diagnostic core).** Importing Study E's exact `measure_full` (`experiments/vision/study_e_state_cost.py`) and running it at N=6:

| code path | N=6 peak | N=12 |
|---|---|---|
| Study E `measure_full` (forward **without** `torch.no_grad()`) | **53.39 GB** (reproduces Study E) | **OOM** |
| forward **with** `torch.no_grad()` (Study B's original code / this Study F) | **17.64 GB** | **19.36 GB (feasible)** |

Study E's Orin `measure_full` runs `model(**inputs, use_cache=True)` **outside** any `torch.no_grad()` (Study B on the A6000 wrapped the identical call in `with torch.no_grad()`). `model.eval()` does **not** disable gradient tracking. Without `no_grad`, the forward builds the full autograd graph and retains activations for backward — dominated by the vision tower's patch-attention, which grows with total patch count — inflating peak ~3× and exhausting memory at N=12. The 53.4 GB is retained autograd state, not a live working-set the device needs to serve.

---

## 3. Sanity checks

| check | result |
|---|---|
| Attention impl asserted (from loaded model) | **PASS** — `sdpa` for LM and vision tower, logged for all three models |
| Generation produced exactly 256 tokens (Part 1) | **PASS** — `assert n_gen == 256` in every run |
| Models on GPU at bf16 | **PASS** — `param.dtype == bfloat16`, `param.device == cuda:0`, asserted |
| Noise floor (repeated identical runs) | **PASS** — decode-tps CV = 0.0012 (4B), 0.0014 (8B) |
| Memory instrumentation reliable under unified memory? | **NO — flagged (STOP-and-say-so).** torch's CUDA counters over-report vs actual RAM by ~2× (16.58 GB counter vs 8.52 GB RAM for the weights). On Jetson's unified LPDDR5 they are allocator accounting, not a discrete-VRAM working set. Reported alongside the `/proc/meminfo` RAM-delta cross-check. The **relative** comparison (with vs without `no_grad`) is unaffected, and the RAM-delta confirms the true incremental memory is small (≤1.8 GB across N). |

---

## 4. Verdicts on the two suspect numbers

**(a) 9.4 tok/s parameter-independence — FRAMEWORK OVERHEAD ARTIFACT, not a device property.**
There is a ~106–110 ms/token fixed overhead floor in HF `generate()` + dynamic cache on this stack. The 4B decodes at 40.7% of its 23.1 tok/s bandwidth roofline; a bandwidth-bound 4B would be ~23 tok/s. The near-identical 4B/8B rate across a 2× weight difference is the overhead signature, not silicon. Study E's own thermal record (65 °C, zero throttle over 14.5 h) corroborates: the GPU was stalling on CPU dispatch, not saturated. The interventions that would remove the overhead (static cache C2, `torch.compile` C3) could not be measured because triton is absent on this stack — but they were not needed to reach the verdict.

**(b) 53.4 GB peak / N=6 ceiling / OOM at N=12 — MEASUREMENT ARTIFACT (missing `torch.no_grad()`), not vision-tower device memory.**
Reproduced exactly: Study E's `measure_full` (no `no_grad`) = 53.39 GB @ N=6 and OOM @ N=12; the same forward under `no_grad` = 17.6 GB @ N=6 and 18.7 GB @ N=12 with no OOM, matching the ~16.7 GB arithmetic. The 37 GB "unaccounted" is retained autograd activations (dominated by vision patch-attention), released the moment gradients are disabled. The vision-tower attention is real and does grow with patches, but under correct inference (`no_grad`) it never materializes into a ceiling in the tested range.

---

## 5. Study E claims that must be retracted or amended (explicit)

1. **RETRACT** — "Full-retention state ceiling = N=6 (peak 53.4 GB); OOM at N=12; Orin ceiling ~8× lower than A6000; caused by O(L²) SDPA attention memory despite 64 GB unified." This is entirely a `torch.no_grad()` omission in the Study E Orin measurement script. Under correct inference the Orin holds N=12 at 18.7 GB with no OOM; there is no N=6 ceiling. The A6000-vs-Orin ceiling comparison compared a gradient-tracking-bugged Orin run against a correct (`no_grad`) A6000 run and is invalid.

2. **RETRACT / AMEND** — "decode ≈ 9.4 tok/s regardless of model size (device is overhead/bandwidth-bound, not parameter-bound)." The parameter-independence is a **framework** overhead artifact of HF `generate()` + dynamic cache on a triton-less stack, not a device property. The device's bandwidth roofline is ~23 tok/s (4B) / ~12 tok/s (8B); the 9.4 figure reflects ~106 ms/token of Python/dispatch overhead. Any statement using 9.4 tok/s as the Orin's achievable decode rate (including the "Orin decodes ~3–5× slower than A6000" cross-tier ratio, since the A6000 ran the same overhead-bound path) understates the device and conflates framework overhead with silicon.

3. **AMEND** — every Study E Part 2 memory figure and the "peak memory" column that used `torch.cuda.max_memory_allocated` on the Orin: these over-report ~2× vs actual RAM under unified memory and must be qualified as allocator accounting, cross-checked against system RAM.

4. **RETAIN** — Study E's thermal/throttle result (max tj 65 °C, zero throttling, flat throughput) stands, and in fact corroborates verdict (a): the GPU was idle-waiting on CPU dispatch.

---

## Plain answers

- **Is 9.4 tok/s parameter-independence a device property or a framework overhead artifact?** A **framework overhead artifact.** A ~106–110 ms/token fixed cost in HF `generate()` + dynamic cache dominates; the 4B runs at 40% of its bandwidth roofline, and the 4B/8B parity across a 2× weight gap is the overhead signature. It is not the device's decode capability.
- **Is the 53.4 GB peak explained, and by what?** **Yes — by a missing `torch.no_grad()`** in Study E's Orin `measure_full`, which retained the autograd graph (activations for backward, dominated by vision patch-attention). Under correct inference the peak is 17.6 GB @ N=6 and 18.7 GB @ N=12 with no OOM. Additionally, the torch memory counters over-report ~2× vs actual RAM on this unified-memory device.
