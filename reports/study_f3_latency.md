# StudyF3-latency: single-request latency, exclusive

E-id: StudyF3-latency (`research/EXPERIMENTS.md`, pre-registered 2026-11-10). Host: h100nvl **GPU 1** (user decision 2026-11-10), localhost, no network.

## 0. Mechanism verification (recorded BEFORE the sweep, 2026-11-10)

**Step 1, causal chain.**
- Single-request latency at fixed hardware is prefill-bound at these lengths (max_tokens 8): TTFT grows with prompt tokens. FORMULATION's physical component is reconstruction cost growing with context.
- Two other factors can shift the curve at equal token count:
  - **input format**, because a video input is temporally merged and processed differently from separate images;
  - **cache state**, because with prefix caching ON the cached prefix is not recomputed.
- E4 found a ~1.2 s gap at ~12.4k tokens between video-format (R1 single) and image-format (H5) cold latency. Cell f measures the same K1/K3 frames in both formats on one server stack and card, to test whether format alone explains it.

**Step 2, instantiate each link.**

| causal link | implementing quantity | planned range | varies as expected? | evidence |
|---|---|---|---|---|
| tokens drive prefill | prompt tokens per cell | F1 ≈ 0.44k / 1.1k / 3.0k; U 1.8k–23.9k; D2 0.5k–30.7k; summary ≈ 12.5k + captions; K1/K3 video ≈ 12.4–13.2k, as images ≈ 2× (no temporal merge) | yes, by design (token-binned samples) | `f3_plan.json` |
| format | video vs separate images on identical frames (cell f) | K1, K3 × {video, images} | yes | cell f |
| cache state | cached_tokens | 0 on every COLD request (asserted; STOP otherwise); > 0 on WARM requests after a session's first | yes | cell d |
| exclusivity | other jobs of ours | none, enforced by the chain and a 30-s monitor (VOID on overlap) | — | `f3_monitor_h100nvl.jsonl` |

Sampling shortfall, reported rather than hidden: arm U's token range is sparse at the low end. Its 6 equal-width bins hold 4, 9, 175, 129, 293 and 235 questions, so cell b sends **53** requests, not 60.

**Step 3, trace one unit.** Every row records prompt tokens, cached tokens, body bytes, the SM clock at send, TTFT and total.

**Step 4, negative control.**
- Cold cells must show cached_tokens = 0. The runner stops otherwise.
- In WARM cell d, the first request of each session has only the header to reuse, so it must be near the cold curve; later requests must fall below it.

**Step 5, alternative explanation.** A format gap at equal tokens could come from a host-state difference (clock, other tenants) rather than the format. Both formats in cell f run back to back on the same card, with the SM clock and other users' GPU activity logged per request and every 30 s.

## 1. Status, exclusivity and checks

**COMPLETE** 2026-11-10 15:11, h100nvl GPU 1 (GPU-235c6d2d-40df-9060-e2f8-6524c4928d2d). **Not VOID.**

- **Attempt 1 (14:09) stopped in group b_4BI. My bug, reported:** the D11 U video loader (`npz_frames`) was not registered in the server, because F3 put `d11_site` on PYTHONPATH but did not set `D11_NPZ_LOADER=1`. Every b_U request returned HTTP 500, and the runner stopped on the server-log error.
- **Fix:** the variable is set and cleared around the D11 groups.
- **Relaunch:** 14:14. Group a_4BI (already complete) was kept. The 54 failed b_4BI rows are marked `superseded` and excluded; b_4BI was re-run from its start on a fresh server.

| check | value |
|---|---|
| rows used / discarded warm-ups / errors | 727 / 9 (one per group) / 0 |
| COLD requests with cached_tokens ≠ 0 | 0 |
| missing TTFT | 0 |
| monitor snapshots (14:09:36 – 15:11:07, every 30 s) | 130 |
| processes of ours outside the job tree | 0 in every snapshot |
| foreign processes on GPU 1 | 0 in every snapshot |
| other users on the host's GPUs | gaofeng (other GPUs, throughout); pragya = our own server on GPU 1 |
| SM clock at send | 1,680 – 1,785 MHz (idle readings between groups go down to 345 MHz) |

## 2. Per-cell latency (single request, localhost, max_tokens 8; seconds)

| model / cell | format | cache | n | prompt tokens p50 [min – max] | TTFT p50 / p90 / max | total p50 / p90 / max | body MB p50 |
|---|---|---|---|---|---|---|---|
| 4B a F1 N = 1 | images | COLD | 50 | 458 [411 – 602] | 0.133 / 0.146 / 0.165 | 0.136 / 0.149 / 0.168 | 0.5 |
| 4B a F1 N = 3 | images | COLD | 50 | 1,120 | 0.161 / 0.170 / 0.193 | 0.164 / 0.174 / 0.197 | 1.6 |
| 4B a F1 N = 9 | images | COLD | 50 | 3,076 | 0.264 / 0.282 / 0.307 | 0.268 / 0.286 / 0.310 | 4.8 |
| 4B b D11 U | video | COLD | 53 | 13,617 [1,810 – 22,387] | 1.502 / 2.362 / 2.520 | 1.512 / 2.378 / 2.535 | 104.8 |
| 4B e F2 summary | video | COLD | 50 | 13,136 [12,373 – 14,561] | 1.904 / 1.986 / 2.015 | 1.913 / 1.994 / 2.024 | 46.0 |
| 32B a F1 N = 1 | images | COLD | 50 | 458 | 0.193 / 0.208 / 0.220 | 0.217 / 0.231 / 0.243 | 0.5 |
| 32B a F1 N = 3 | images | COLD | 50 | 1,120 | 0.323 / 0.339 / 0.353 | 0.346 / 0.363 / 0.377 | 1.6 |
| 32B a F1 N = 9 | images | COLD | 50 | 3,076 | 0.688 / 0.705 / 0.731 | 0.712 / 0.729 / 0.754 | 4.8 |
| 32B b D11 U | video | COLD | 53 | 13,617 [1,810 – 22,387] | 3.743 / 6.227 / 6.590 | 3.774 / 6.261 / 6.625 | 104.8 |
| 32B c RH4 D2 | images | COLD | 60 | 15,703 [2,238 – 30,701] | 3.925 / 7.455 / 9.023 | 3.958 / 7.492 / 9.086 | 28.3 |
| 32B d RH4 D2 | images | **WARM** | 41 (10 sessions) | 12,222 [2,278 – 25,905] | 1.293 / 3.092 / 4.374 | 1.320 / 3.126 / 4.413 | 27.6 |
| 32B e F2 summary | video | COLD | 50 | 13,136 | 3.957 / 4.207 / 4.330 | 3.986 / 4.236 / 4.367 | 46.0 |
| 32B f K1 | video | COLD | 30 | 12,594 [11,524 – 12,786] | 3.816 / 3.895 / 3.925 | 3.847 / 3.942 / 3.959 | 48.8 |
| 32B f K1 | images | COLD | 30 | 23,146 [21,471 – 24,123] | 6.282 / 6.355 / 6.544 | 6.319 / 6.392 / 6.581 | 48.8 |
| 32B f K3 | video | COLD | 30 | 12,431 [11,964 – 12,543] | 3.808 / 3.876 / 3.933 | 3.836 / 3.904 / 3.982 | 46.7 |
| 32B f K3 | images | COLD | 30 | 23,782 [23,190 – 23,941] | 6.300 / 6.334 / 6.382 | 6.342 / 6.383 / 6.422 | 46.8 |

**Per token bin** (6 equal-width bins per arm; TTFT p50 / p90 / max, s):

| bin | U tokens p50 (n) | 4B U | 32B U | D2 tokens p50 (n) | 32B D2 COLD |
|---|---|---|---|---|---|
| 0 | 3,276 (4) | 0.43 / 0.55 / 0.58 | 0.82 / 1.16 / 1.22 | 3,895 (10) | 0.85 / 1.08 / 1.08 |
| 1 | 6,995 (9) | 0.80 / 0.90 / 0.95 | 1.82 / 2.14 / 2.27 | 8,870 (10) | 2.11 / 2.30 / 2.47 |
| 2 | 12,264 (10) | 1.40 / 1.43 / 1.43 | 3.40 / 3.46 / 3.50 | 11,123 (10) | 2.70 / 3.85 / 3.92 |
| 3 | 14,797 (10) | 1.61 / 1.71 / 1.78 | 4.09 / 4.43 / 4.46 | 16,801 (10) | 4.25 / 4.79 / 4.83 |
| 4 | 19,338 (10) | 2.11 / 2.20 / 2.30 | 5.53 / 5.71 / 5.88 | 23,208 (10) | 6.33 / 7.01 / 7.05 |
| 5 | 21,321 (10) | 2.37 / 2.50 / 2.52 | 6.23 / 6.47 / 6.59 | 26,775 (10) | 7.51 / 7.76 / 9.02 |

Total latency is TTFT + 0.01–0.03 s throughout; full totals per bin are in `f3_results.json` → `bins`.

## 3. Fitted curves (TTFT vs prompt tokens; never pooled across format or cache state)

| model / format / cache | cells | n | token range | linear slope (ms per 1k tokens) | R² (lin / quad) | quad fit at 2k / 6k / 12.4k / 20k (s) |
|---|---|---|---|---|---|---|
| 32B / images / COLD | F1 N1/3/9, D2, K1/K3 images | 270 | 411 – 30,701 | 270 | 0.997 / 0.999 | 0.49 / 1.36 / 2.96 / 5.18 |
| 32B / video / COLD | U, F2, K1/K3 video | 163 | 1,810 – 22,387 | 294 | 0.976 / 0.979 | 0.32 / 1.68 / 3.69 / 5.82 |
| 32B / images / WARM | D2 WARM | 41 | 2,278 – 25,905 | 104 vs total tokens (R² 0.46); **244 vs uncached tokens** (R² 0.78, intercept 0.47 s) | — | — / 1.00 / 1.54 / 2.43 |
| 4B / images / COLD | F1 N1/3/9 | 150 | 411 – 3,220 | 51 | 0.965 / 0.966 | 0.21 at 2k (no longer range) |
| 4B / video / COLD | U, F2 | 103 | 1,810 – 22,387 | 104 | 0.805 / 0.860 | 0.07 / 0.79 / 1.66 / 2.27 |

- Quadratic coefficients are in `f3_results.json` → `curves`.
- The 4B video fit is poor (R² 0.86): the F2 cell sits about 0.4 s above U at equal tokens (1.90 s at 13.1k vs U bin 2: 1.40 s at 12.3k). F2 adds a text block and sends 122 frames vs U's mixed counts. This is reported, not modelled.

## 4. Format reconciliation (cell f; resolves E4's ~1.2 s gap)

Same K1 / K3 frames, same server stack, same card, back to back (32B, paired over 30 questions each):

| | video tokens | video TTFT p50 | images tokens | images TTFT p50 | images − video total (paired p50) |
|---|---|---|---|---|---|
| K1 | 12,594 | 3.816 | 23,146 | 6.282 | +2.46 s |
| K3 | 12,431 | 3.808 | 23,782 | 6.300 | +2.51 s |

- **Same frames:** sent as separate images they cost 1.84–1.91× the tokens (no temporal 2-frame merge) and are 2.5 s *slower*.
- **Equal token count:** video is *slower* than images. Video TTFT − the cold image-curve prediction at the same tokens:
  - K1 video +0.83 s, K3 video +0.84 s, F2 +0.78 s, U +0.48 s (p50).
- **E4's sources:**
  - H5 (32B N = 37 images, 12,420 tokens) measured 3.00 s TTFT. F3's cold image curve gives 2.96 s at 12.4k, which **reproduces H5**.
  - R1 single K1 / K3 video measured 4.24 / 4.18 s. F3 measures the same requests at 3.82 / 3.81 s, which is 0.37–0.43 s faster than R1 single.
- **Decomposition of E4's 1.2 s gap** (R1 video 4.2 s vs H5 images 3.0 s at about 12.4k tokens):
  - **about 0.84 s is format** (video vs images at equal tokens, same run);
  - **about 0.4 s is run-to-run / host difference** in R1's single-request measurement (R1 ran on GPU 3, a different session).
  - E4's mixed-format cold curve therefore overstated the video penalty by about 0.4 s.

## 5. Warm vs cold (cell d, RH4 D2, 32B; labelled WARM, never pooled)

- **First request of each session** (only the 32-token header cached): TTFT − cold-curve prediction = −0.05 s p50 (range −0.10 to +0.03; n = 10). It sits on the cold curve. **The Step 4 negative control passes.**
- **Later requests** (cached 2,192 – 21,264 tokens, p50 10,384): TTFT − cold prediction = −1.93 s p50 (range −4.59 to −0.38; n = 31).
- WARM TTFT tracks *uncached* tokens: 244 ms per 1k uncached tokens + 0.47 s, close to the cold image slope (270 ms per 1k). The prefix cache removes the cached tokens' prefill and little else.

## 6. Mechanism verification, post-sweep

| link | outcome |
|---|---|
| tokens drive prefill | confirmed (images COLD R² 0.997 linear over 0.4k – 30.7k) |
| format | confirmed and quantified (+0.8 s video at equal tokens; −2.5 s video on the same frames) |
| cache state | confirmed (COLD cached = 0 on all 686 cold rows; WARM later requests reuse 2.2k – 21k tokens) |
| exclusivity | confirmed (0 overlaps in 130 snapshots) |
| Step 4 | PASS (cold cached = 0; WARM first-in-session on the cold curve) |
| Step 5 | Host state ruled out for the format gap: both formats ran back to back at the same SM clock band (1,680 – 1,785 MHz), with no foreign process on GPU 1. |

## 7. Consistency check (6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | PASS for images: the curve gives 2.96 s at 12.4k vs H5 3.00 s. **FLAG for video:** 3.81 s vs R1 single 4.2 s (−0.4 s, outside R1's p50–p90 spread). This is the run-to-run term in §4; the cause is not isolated (different GPU and session). |
| 2 | physical plausibility | PASS. 32B prefill at about 270 ms per 1k tokens is about 3.7k tok/s. At 2 × 32e9 FLOPs per token, that is about 240 TFLOP/s, or about 28 % of H100 NVL dense bf16 peak (about 835 TFLOP/s), plausible for single-request prefill with a vision encoder. 4B is 5.3× faster per token (51 vs 270 ms per 1k), against an 8× parameter ratio. |
| 3 | distribution sanity | PASS. Monotone in tokens; p90 / p50 within 1.2× inside each fixed-size cell; the wide p90 / max in U and D2 come from their token spread (see bins). |
| 4 | definition audit | TTFT = first streamed content token after the request is sent with a pre-serialized body; total = last token (max_tokens 8). Localhost; network time is not included. COLD = prefix caching off. |
| 5 | claim linkage | Physical component (reconstruction cost vs context): gives per-format, per-cache cost curves for E4-style decisions. |
| 6 | proxy validity | Single-request localhost. These are not latencies under load or over a WAN. |

## 8. Observations

1. 32B cold TTFT is linear in prompt tokens for images: 270 ms per 1k + 0.09 s (R² 0.997, 0.4k – 30.7k tokens).
2. At equal tokens, video input is about 0.8 s slower than images (K1 / K3 / F2), and U is about 0.5 s slower.
3. On the same K1 / K3 frames, video is 2.5 s faster than images, because images cost about 1.9× the tokens.
4. E4's 1.2 s gap is about 0.84 s format plus about 0.4 s difference between R1's earlier run and this one.
5. The F2 summary arm costs 3.96 s TTFT (32B) vs K3 video 3.81 s: +0.15 s for a median of +414 summary tokens.
6. F1 short windows: 32B 0.19 / 0.32 / 0.69 s and 4B 0.13 / 0.16 / 0.26 s for N = 1 / 3 / 9.
7. WARM prefix caching cuts later in-session TTFT by 1.9 s p50 and follows uncached tokens at about the cold slope.

## 9. Interpretation (inference, labelled)

- **Video penalty at equal tokens:** the likely cause is the vision encoder, which sees 2 raw frames per merged video token, so it does about twice the encoder work per LLM token compared with images. Not tested directly.
- **Latency models:** they should use per-format curves; a single tokens → latency curve is wrong by about 0.8 s at 12k tokens.
- **E4's video-vs-image cold comparison:** it should be re-read with the F3 curves (same card, same session). This is not done here.
