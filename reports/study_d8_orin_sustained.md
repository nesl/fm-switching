# StudyD8 — continuous local sensing cost (Jetson AGX Orin)

**Date:** 2026-11-04 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp `c0fd786` (CUDA sm_87) · **Model:** Qwen3VL-4B-Instruct-F16 (+mmproj-F16), sha256 verified · **E-id:** StudyD8

**Goal.** Measure what Qwen3VL-4B-Instruct costs when it runs as a *standing query* — a sensor polled on a schedule, or flat-out — rather than as isolated one-shot requests. Jetson only; MAXN mode 0, GPU pinned 1.3005 GHz (verified + logged per request, 0 bad rows). Greedy (temp 0), max 512, seed 0, **`cache_prompt=false` (cold every request)**. Inputs are the exact N=1 and N=9 payloads from `identical_input_manifest.json` (per-PNG sha256 re-verified: **240/240 match**), the 120 questions cycled in fixed order. Energy = per-request trapezoidal integral of total board power (3 INA3221 rails, no VDD_IN on this Orin, 100 ms sampling); hourly energy "above baseline" uses the 10-min loaded-idle baseline.

---

## Results (observations)

**Baseline (server loaded, no requests, 10 min):** **9.61 W** board, tj 48.6 °C. This is the standing cost of keeping the 4B model resident and idle (34.6 kJ/h, ~9.6 Wh/h) before any inference.

| arm | input | cadence | dur | **req / missed** | TTFT p50 / p90 / p99 (s) | latency p50 (s) | staleness p50 (s) | **E / req** | **mean board W** | **E/h total** | **E/h above base** | tj_max | match | acc (indic.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | N=1 | every 1 s | 30 m | **1800 / 0** | 0.513 / 0.544 / 0.561 | 0.567 | 0.004 | **16.0 J** | 28.2 | 101.7 kJ (28.2 Wh) | 67.1 kJ (18.6 Wh) | 59.2 °C | 1.000 | 12.5 % (15/120) |
| **B** | N=9 | every 5 s | 30 m | **360 / 0** | 3.843 / 3.934 / 4.005 | 3.899 | 0.036 | **149.9 J** | 38.4 | 138.3 kJ (38.4 Wh) | 103.7 kJ (28.8 Wh) | 63.3 °C | 1.000 | 28.3 % (34/120) |
| **C** | N=9 | back-to-back | 60 m | **878 / 0** | 3.848 / 3.930 / 3.993 | 3.904 | 0.196* | **159.5 J** | 40.9 | 147.2 kJ (40.9 Wh) | 112.6 kJ (31.3 Wh) | 65.7 °C | 1.000 | 28.3 % (34/120) |

*Arm C has no fixed schedule; its "staleness" is the inter-request gap (0.15 s settle + dispatch), not scheduling lag.

**Drift (first 10 min → last 10 min TTFT p50):** A 0.513 → 0.514 s · B 3.847 → 3.841 s · C 3.839 → 3.853 s. **No drift** in any arm (≤ 14 ms over an hour for C). Mean board power is also flat across each arm's first/last 10 min.

**Throttle / clock / caching:** No throttling in any arm — tj peaked at **65.7 °C** (arm C), far below the 90 °C stop guard and the 95/99/104.5 °C trip points; power never ramped down. GPU clock pinned 1.3005 GHz on **all 3,038 sustained requests + 360 warm/sanity** (0 bad rows). **`cached_n = 0` on every row** (cold prefill confirmed; prefix cache never served a request). Peak RAM ~25.8 GB.

**Throughput delivered:** A met 1 req/s exactly (1800 in 1800 s); B met 1 req/5 s exactly (360 in 1800 s); C ran saturated at **878 N=9 inferences/h** (= 4.10 s/req, i.e. latency-bound). No arm ever skipped a tick — the device is never behind schedule at these cadences.

---

## Reading (interpretation)

- **Running as a standing query carries no per-request penalty and no degradation.** Per-request TTFT, latency, and energy under 30–60 min of continuous load are statistically identical to isolated one-shot measurements (sanity below), and show zero drift. The Orin sustains 1 Hz N=1 or 5 s-cadence / back-to-back N=9 indefinitely at these points without thermal throttling (plateau 65.7 °C) or clock loss.
- **The cost of a standing query is duty-cycle × per-request + a fixed resident idle.** Keeping the 4B model loaded costs **9.6 W (34.6 kJ/h) doing nothing**. Each inference then adds a fixed increment: **~16 J per N=1** or **~150–160 J per N=9**. Hourly energy is set by how often you poll: N=1 @1 Hz = 28 Wh/h; N=9 @0.2 Hz = 38 Wh/h; N=9 flat-out = 41 Wh/h.
- **Saturation is cheaper per unit work than slow polling, in incremental terms.** Arm C does ~22 % more N=9 inferences/h than arm B (878 vs 720/h) for only ~9 % more board power (40.9 vs 38.4 W), because B's idle gaps keep paying the 9.6 W resident cost while doing less work. Per *active* request C is marginally higher (159.5 vs 149.9 J) — a saturated GPU starts each request from a warmer, higher-power floor; B cools toward idle between 5 s ticks, so its per-request integration window begins lower.
- **The N=1 fast path stays fast under load but remains task-insufficient.** Arm A holds 0.51 s TTFT / 16 J at 1 Hz, but indicative accuracy is 12.5 % — below the 20 % random baseline, exactly reproducing StudyDevOne. N=1 is a cheap *liveness* poll, not an *answer*. N=9 (3.8 s, ~155 J, 28 %) is the useful sustained operating point.
- **Determinism holds:** greedy decoding gave byte-identical letters on every repeated question (match rate 1.000 across all three arms, 120 questions repeated 3–15×).

---

## Sanity checks (as required)

1. **Isolated N=1 / N=9 TTFT vs prior (no tuning applied):** isolated N=1 median **0.498 s** vs reference 0.51 s (ratio 0.976); isolated N=9 median **3.832 s** vs reference 3.80 s (ratio 1.008). Both within noise of the StudyDevOne/StudyDevFast figures; reported as measured, nothing adjusted to match.
2. **Greedy letter-match on repeated identical requests:** **1.000** in every arm (120 repeated questions each). Decoding is deterministic as expected.
3. **`cached_n` = 0:** confirmed on every one of the 3,038 sustained requests (min = max = 0). No prefix-cache reuse; every request is a true cold prefill.
4. **Thermal:** tj_max 65.7 °C ≪ 90 °C stop guard; no arm stopped, no throttle event.

---

## Results consistency check (6 checks)

**1. Cross-check against committed measurements — PASS** (all ratios ≤ 1.2×, well within the 2× gate):

| quantity | StudyD8 | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| N=1 TTFT | 0.513 s (arm A p50); 0.498 s (iso) | 0.506 s | StudyDevOne | 1.01 / 0.98 | ✓ |
| N=9 TTFT | 3.843 s (arm B p50); 3.832 s (iso) | 3.80 s (corrected); 3.881 s (control) | StudyDevFast / StudyDevOne | 1.01 | ✓ |
| N=1 prefill rate | ~1,050 tok/s | 1,053 tok/s | StudyDevOne | 1.00 | ✓ |
| N=9 prefill rate | ~815 tok/s | 826 tok/s | StudyDevFast | 0.99 | ✓ |
| N=9 energy/req | 159.5 J (arm C) | 159 J | StudyDevFast N=9 | 1.00 | ✓ |
| N=1 energy/req | 16.0 J (arm A) | 19.3 J | StudyDevOne | 0.83 | ✓ (explained) |
| loaded-idle | 9.61 W | 9.94 W | StudyDevOne | 0.97 | ✓ |
| N=1 accuracy (indic.) | 12.5 % | 12.5 % | StudyDevOne | 1.00 | ✓ |
| N=9 accuracy (indic.) | 28.3 % | 28 % | StudyDevFast/DevOne | 1.01 | ✓ |

The one sub-unity outlier (N=1 energy 16.0 vs 19.3 J, ratio 0.83) is explained and self-consistent: arm A polls at 1 Hz, leaving ~0.43 s idle between each ~0.57 s request, so the GPU decays toward 10 W between ticks (raw trace swings 10.3 ↔ 39 W) and each request's clamped integration window starts from a lower floor than StudyDevOne's back-to-back N=1 sweep. The same effect orders the N=9 arms correctly (arm B @5 s = 149.9 J < arm C back-to-back = 159.5 J ≈ StudyDevFast's tight 159 J). Latency, rate, power-point and accuracy — the headline quantities — reproduce priors to ≤ 1 %.

**2. Physical plausibility — PASS.** N=1 prefill ~468 tok / 0.445 s ≈ 1,050 tok/s; N=9 ~3,130 tok / 3.84 s ≈ 815 tok/s — both ≤ the committed cold-prefill curves (no rate > 2× faster, so no caching artifact), and `cached_n=0` rules caching out directly. Energy satisfies J ≈ W × s by construction. Board power 28–41 W active vs 9.6 W idle is consistent with StudyDevFast (42–44 W at longer inputs) and StudyDevOne (34.6 W at N=1).

**3. Distribution sanity — PASS.** All latency/energy figures are reported as distributions (p50/p90/p99, min/max). TTFT spreads are non-degenerate (A 0.48–0.66 s; B 3.65–4.05 s; C 3.65–4.05 s) — tight, as expected for a fixed-length prefill-bound request, but not frozen, so no short-circuiting. The 1.000 match rate is the *intended* determinism check (greedy + identical input), not a constant standing in for a distribution; the underlying TTFTs still vary request-to-request.

**4. Definition audit — PASS.** N=1/N=9 = manifest payloads (sha256-verified). `cache_prompt=false` ⇒ cold (cached_n=0 every row). Energy = sum of 3 INA3221 rails (no VDD_IN, as StudyDevFast/DevOne). "Missed tick" = a scheduled slot with no request issued (skip-not-queue; non-overlap guaranteed by single-threaded synchronous dispatch). "Staleness" = wall_start − scheduled (for back-to-back arm C this is the inter-request gap, flagged in-table). GPU clock read from sysfs per request. Same definitions as the prior device studies.

**5. Claim linkage — PASS.** Bears on the **physical component of Context Inertia** and on the per-turn *standing-query operating cost* a trace-driven simulator must charge: it shows that cost is load-independent (no sustained-mode penalty) and decomposes as resident-idle + duty-cycle × per-request. Relevant to the representation × placement × timing trade-off (when to keep an FM resident and sensing locally vs offload), and supplies the device-side cost of a continuously-running local agent. No quantity scoped out by FORMULATION.md is measured.

**6. Proxy validity — stated.** Accuracy is **indicative only** (A6000 is the accuracy reference; device DEV-RECENT 5-way MCQ via shared `dev_inputs.py`), and the 12.5 % / 28.3 % figures reproduce StudyDevOne rather than establishing new accuracy. Board power = 3-rail sum (no VDD_IN rail exposed). tj is the junction-temperature proxy for throttle risk.

**Mechanism verification:** N/A — runtime power/latency/energy measurement, no causal claim (same as StudyDevFast / StudyDevOne); Steps 1–5 do not apply.

**STOP gates:** none tripped — clock correct (0 bad rows), inputs verified (240/240), no throttle, no control/estimate failure.

---

## Files

- Harness: `experiments/device/study_d8_sustained.py` (reuses `dev_fast_latency.py`, `study_dev_one.py`, `dev_inputs.py`).
- Per-request (incl. per-request energy): `results/device/study_d8/arm_A.jsonl` (1800), `arm_B.jsonl` (360), `arm_C.jsonl` (878); `isolated_sanity.jsonl` (20).
- Continuous power/temp traces: `results/device/study_d8/arm_{baseline,A,B,C}_tegrastats.jsonl.gz` (100 ms).
- Aggregates: `results/device/study_d8/study_d8_summary.json`.
- Model sha256 (verified): `results/device/model_hashes.txt`. Inputs: `results/device/identical_input_manifest.json`.
