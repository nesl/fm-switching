# StudyRH4 — fixed-stride, append-only histories (H100, vLLM)

**Stack:**
- vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3, CUDA graphs, gmu 0.90, max_model_len 32768.
- Qwen3-VL-32B-Instruct @0cfaf481 on h100nvl GPU 3.
- The watchdog and monitor ran for the whole chain; no foreign process appeared on GPU 3.
- Builder and analysis: original `.venv` (transformers 5.10.2), CPU.
- K1/K3 (R1) and A/B (RH3) were run on the same stack.

**Pre-registration:** research/EXPERIMENTS.md, StudyRH4, written 2026-10-19 before any GPU run. The user approved defaults 1a/2a/3a and three additions.

**Run times:**
- Part 0: 17:57–17:59.
- Cells: 18:00–18:58. D1 took 22.2 min and D2 32.3 min, against a 1.04 h estimate.

## Decision: **ACCURATE-WARMABLE FORMAT EXISTS** (for sessions up to about 12 minutes)

| pre-registered condition | value | met? |
|---|---|---|
| Part 0: appending 30 s reuses ≥ 95% of the earlier prompt | 99.2–99.5% on 5/5 questions | yes |
| D2 − K1 ≥ −1.5 pp | **−0.24 pp** | yes |
| … with a 95% CI including 0 | [−2.80, +2.41] | yes |
| D2 − K1 on RECENT-miss (97): CI includes 0 | +4.26 [−4.60, +13.10] | yes |

**What D2 is:**
- Frames at t = 0, 2, 4, … s at 352×256, never re-spaced, as separate images after a one-line header.
- It is append-only: each 10 s adds 5 images (450 tokens) after an unchanged prefix.
- Its accuracy cannot be told apart from K1 overall or on old-evidence questions.
- RH3's incompatibility, where the warmable format was 9 pp worse, came from the low resolution of RH3 A, not from appending.

**The rule passes in the sensitivity analysis as well.** Counting the 6 over-context D2 questions as wrong (all 845 questions), D2 − K1 is −0.24 [−2.78, +2.39] and RECENT-miss is +4.12 [−4.40, +12.63].

**Limits of the "exists" verdict:**
1. **Session length: the format's own limit.** A fixed-stride history grows without bound.
   - Inside 32,768 − 512 tokens, D2 can serve at most **710 s (11.8 min)** for the mean question text (702 s for the longest text). D1 can serve 984 s (16.4 min).
   - Six of the 845 questions (0.7%) lie beyond D2's limit:
     - qt 757, 1000, 1011, 1124, 1146 and 1155 s;
     - 3 of the 6 are RECENT-miss.
   - Past that length a warm cloud history needs a **rollover policy**, for example a coarser stride for the oldest part or a re-based prefix. A rollover rewrites the prefix and costs one cold prefill.
   - No rollover was measured here.
2. **Power on the old-evidence test is low.** The RECENT-miss CI is ±9 pp on 97 questions. "Not significantly below K1" rules out a large loss, not a moderate one.
3. **Warm capacity is small and grows with session length.** At the mean history (11.3k tokens):

   | KV | clean tails (0.55×) | degraded tails (0.85×) |
   |---|---|---|
   | bf16 | 3 devices | 4 devices |
   | FP8 | 6 devices | 9 devices |

   - These are projections from the RH2 footprint rule, not measured latency.
   - A single 11-min session holds about 30k tokens (max history 30,541), which is 0.47× the bf16 KV.

## Results

Paired n = 839: questions answered without error in every cell. All 6 D2 HTTP-400 questions are excluded, along with D1's 4, which are a subset of them.

| cell | representation | mean history tok (max) | accuracy [Wilson 95%] | RECENT-miss / cover | warm devices bf16 0.55× / 0.85× | FP8 0.55× / 0.85× | append-only |
|---|---|---|---|---|---|---|---|
| K1 | RICH, one video | 12,124 (12,967) | 39.81 [36.6, 43.2] | 43.6 / 39.3 | 2 / 4 | 5 / 9 | no (RH3 Part 0) |
| K3 | RECENT, one video | 12,112 (12,525) | 38.62 [35.4, 42.0] | 25.5 / 40.3 | 2 / 4 | 5 / 9 | no |
| A | 1 fps, 160×128 (RH3) | 5,533 (14,104) | 30.51 [27.5, 33.7] | 34.0 / 30.1 | 6 / 10 | 12 / 19 | yes |
| B | RICH frames, 288×224 (RH3) | 12,583 (16,667) | 40.52 [37.3, 43.9] | 47.9 / 39.6 | 2 / 4 | 5 / 8 | only ≤ 256 s |
| **D1** | stride 2 s, 288×224 | **8,188 (22,066)** | **36.83 [33.6, 40.1]** | 44.7 / 35.8 | 4 / 6 | 8 / 13 | **yes** |
| **D2** | stride 2 s, 352×256 | **11,325 (30,541)** | **39.57 [36.3, 42.9]** | 47.9 / 38.5 | 3 / 4 | 6 / 9 | **yes** |

**Contrasts** (video-clustered bootstrap, 2,000 resamples, seed 0):

| contrast | overall | RECENT-miss (97) | RECENT-cover | DiD |
|---|---|---|---|---|
| **D2 − K1** | **−0.24 [−2.80, +2.41]** | +4.26 [−4.60, +13.10] | −0.81 [−3.55, +1.99] | +5.06 [−4.32, +14.59] |
| D1 − K1 | **−2.98 [−5.94, −0.12]** | +1.06 [−8.74, +11.37] | −3.49 [−6.58, −0.54] | +4.55 [−5.64, +15.58] |
| D2 − B | −0.95 [−3.42, +1.34] | +0.00 [−7.96, +8.05] | −1.07 [−3.56, +1.37] | +1.07 [−7.14, +9.50] |
| D2 − A | **+9.06 [+6.26, +11.85]** | +13.83 [+6.45, +21.98] | +8.46 [+5.39, +11.44] | +5.37 [−2.31, +14.03] |
| D2 − D1 | **+2.74 [+0.84, +4.71]** | +3.19 [−4.08, +9.88] | +2.68 [+0.68, +4.78] | +0.51 [−7.11, +7.81] |
| D2 − K3 | +0.95 [−1.95, +3.83] | **+22.34 [+12.77, +32.63]** | −1.74 [−4.66, +1.21] | **+24.09 [+13.94, +34.61]** |

Answer agreement: D2 vs K1 72%, D2 vs B 81%, D2 vs D1 85%.

**Reading:**
- **Re-spacing costs nothing.** D2 ≈ B (−0.95 [−3.42, +1.34]): the same kind of history, never re-spaced, at a slightly larger frame size and 0.9× the tokens.
- **Per-frame resolution matters at a fixed stride.**
  - D1 (288×224, 8.2k tokens) is −2.98 pp vs K1 and −2.74 vs D2.
  - It still sits well above A (+6.32), so 2 s at 288×224 beats 1 s at 160×128 at about 1.5× A's tokens.
- **D2 keeps K1's full-history advantage.** On questions where the last 120 s miss the evidence, D2 is +22.3 pp over RECENT (K3).

## Part 0 — is the fixed-stride format warmable? **Yes.**

**Server:** RH3's image server with prefix caching ON. KV capacity 62,944 tokens.

**Procedure:** for 5 questions with qt > 300 s that fit the context, send the D2 history up to qt − 30 s (FIRST), then up to qt (SECOND). The text is the same and the 15 new frames are appended.

| question | qt | frames FIRST→SECOND | FIRST prompt / cached | SECOND prompt / cached | SECOND cached ÷ FIRST prompt |
|---|---|---|---|---|---|
| 4DF0872F25 | 387 | 179→194 | 16,224 / 0 | 17,574 / 16,144 | 0.995 |
| 18C977EDB2 | 568 | 270→285 | 24,474 / 32 | 25,824 / 24,320 | 0.994 |
| 2EA41E4F62 | 379 | 175→190 | 15,926 / 15,776 | 17,276 / 17,120 | 1.075 |
| aa6c82624d | 314 | 143→158 | 13,004 / 32 | 14,354 / 12,896 | 0.992 |
| E4F71ADF7D | 498 | 235→250 | 21,329 / 32 | 22,679 / 21,184 | 0.993 |

**Notes on this table:**
- What SECOND does not reuse is the question text plus the last partial block. The question text follows the history and is never shared.
- 2EA41E4F62 is from the same video as 18C977EDB2, so its FIRST request was already a prefix of 18C977EDB2's history. That is the format working as intended across questions on one session. The other four show the cold-then-append case.
- The cached 32 tokens on some FIRST requests are the shared chat template plus header blocks. The header is identical across sessions (`device 00 session 0`), unlike RH2's per-device headers.

## Over-context questions (pre-registered addition 2)

| cell | over 32,768 − 512 | RECENT-miss among them | qt (s) | errored in the run | longest servable session |
|---|---|---|---|---|---|
| D1 | 5 | 2 | 1000, 1011, 1124, 1146, 1155 | 4 | 984 s = 16.4 min (mean text), 974 s (longest text) |
| D2 | 6 | 3 | 757, 1000, 1011, 1124, 1146, 1155 | 6 | 710 s = 11.8 min (mean text), 702 s (longest text) |

- One D1 question (qt 1000, prompt 32,758) was flagged by the pre-registered rule (prompt + 512 > 32,768) but was accepted by vLLM. vLLM caps generation at the remaining 10 tokens rather than rejecting the request, and the answer needs 1–2 tokens. It is answered but is outside the primary paired set anyway, because its D2 counterpart errored.
- Nothing was truncated.

## Mechanism verification (Steps 1–5)

**Step 1 — causal chain.**
- Warm-state continuity lowers escalation latency only if a device's history can be extended in the prefix cache without recomputation (FORMULATION.md: warm state, refresh and reconstruction cost).
- That needs an append-only representation (Part 0).
- The controller can then trade warm capacity (RH2's footprint rule) against fidelity (FORMULATION.md: representation-dependent semantic loss) only if the warmable format's accuracy is known.
- RH3 found the one warmable format it tested to be 9 pp worse. RH4 asks whether that loss is intrinsic to appending (no format is both) or a property of RH3 A's resolution (an accurate warmable format exists).

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value | varies as expected? | evidence |
|---|---|---|---|---|
| append-only → cache reuse | SECOND cached ÷ FIRST prompt | 0.992–0.995 (cold FIRST) | yes; RH3 Part 0 had 0 for one video | Part 0 |
| representation → footprint | history tokens | D1 8.2k, D2 11.3k (max 22k / 31k) | yes | 1,680/1,680 answered requests: vLLM = HF prompt tokens |
| representation → accuracy | correctness | D1 36.8%, D2 39.6% | yes (D2 − D1 +2.74 [+0.84, +4.71]) | results |
| session length → footprint growth | history tokens vs qt | grows linearly, 45 tok/s (D2) | yes (unbounded; 6 over context) | over-context table |
| footprint → warm devices | floor(thr × KV / mean) | 3–9 (D2) | derived | warm columns |

No link is ABSENT or CONSTANT.

**Step 3 — trace.** Question 18C977EDB2 (qt 568 s, gold C):
- D2: 285 images at 352×256, t = 0, 2, … 568; header 31 tokens; HF expected = vLLM prompt = 25,824 tokens.
- In Part 0, the history to 538 s was 24,474 tokens. Re-sent with 15 more frames, 24,320 tokens came from cache and 1,504 were computed: 15 × 90 = 1,350 image tokens plus about 154 question/template tokens.
- No budget binds: 25,824 + 512 ≤ 32,768, and 285 ≤ 640 images.

**Step 4 — negative control.**
- RH3 Part 0 is the matched negative: the same server family, but a one-video history extended by 10 frames, reused 0 tokens despite 10–12k identical leading ids.
- Here the image history reuses 99%. The mechanism (unchanged per-item prefix) is what drives reuse.
- Within RH4, D1 vs D2 varies only resolution, and accuracy moves (+2.74 pp), so the fidelity link is live.

**Step 5 — alternative explanations.**
- **"D2 matches K1 only because of the extra header / sampling description."** The header changed by +4 tokens vs B and D2 ≈ B, so it is not distinguishable from, and not needed for, the result.
- **"D2 ≈ K1 because most questions are short sessions where stride and re-spacing coincide."**
  - Partly true: for qt ≤ 256 s, B and D2 hold similar frame sets (1 s vs 2 s stride).
  - The RECENT-miss contrasts (long-memory questions) show no loss, but they are underpowered (±9 pp).

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | this run | prior | source | ratio | agree? |
   |---|---|---|---|---|---|
   | K1 accuracy on the paired 839 | 39.81% | 39.53% (845) | R1 | 1.01 | agree (subset) |
   | B accuracy on the paired 839 | 40.52% | 40.24% (845) | RH3 | 1.01 | agree |
   | tokens per 288×224 / 352×256 image | 65 / 90 | 65 (RH3 B) / formula 90 | RH3 manifest | 1.00 | agree |
   | KV capacity, image server + prefix caching | 62,944 | 62,944 (RH3 image server) | RH3 meta | 1.00 | agree |
   | append reuse | 0.99 | 0.95 hit for warm escalations | RH2 mechanism check | 1.04 | agree |

2. **Physical plausibility.**
   - Sequential timing on the cache-off server, against RH2's calibration (0.341 s + 0.244 ms/token):

     | request | predicted | measured |
     |---|---|---|
     | D2, 25,824 tokens | 6.64 s | 6.57 s |
     | D1, 18,699 tokens | 4.90 s | 4.43 s |
     | D2, 10,845 tokens | 2.99 s | 2.23 s |

     All are within 2× and none is faster than 2×.
   - Monitoring shows SM clocks at a median of 915 MHz while busy (max 1,785) at about 410 W, the same in R1, R5, RH2 and RH4. The GPU runs power-limited at the same operating point in every run, so cross-study timings are comparable.

3. **Distribution sanity.**
   - D2 history 11,325 mean (max 30,541); D1 8,188 (max 22,066).
   - Completion is 1–2 tokens; there were 0 length finishes, 2 unparsed answers in D1 and 1 in D2 (scored wrong).
   - Answer agreement with K1 is 70–72%, with no identity.

4. **Definition audit.**
   - "History tokens", "RECENT-miss", "evidence_covered" and the warm-device rule are as in RH3.
   - The "over-context" flag (prompt + 512 > 32,768) is slightly stricter than vLLM's acceptance rule (see the D1 qt-1000 note).
   - The paired set is 839, not 845; K1/K3/A/B numbers here are on that subset.
   - "Append-only" means an unchanged per-image prefix, which Part 0 verified directly.

5. **Claim linkage.**
   - **C1** (fidelity is representation-dependent): supported. Resolution at a fixed stride moves accuracy by 2.7 pp, and frame density plus resolution by 9 pp.
   - **C5** (joint representation × placement × timing): supported in direction. An accurate warmable representation exists, so the warm/cold choice no longer forces a 9-pp quality loss within about 12 min. Its footprint (2× A's) halves warm capacity, which is a real joint trade-off.
   - **C4** (physical inertia grows with context): the fixed-stride history grows at 45 tokens/s (D2), which forces a rollover at about 12 min.

6. **Proxy validity.**
   - Warm-device counts are projections from RH2's rule applied to question-time mean history. They are not measured, and they understate the footprint of long sessions.
   - `evidence_covered` saturates (845/845 for both D cells) and does not explain any difference.

## H100 monitoring summary (no GPU)

`results/cost/h100_monitoring_summary.json`, built by `experiments/cost/h100_monitoring_summary.py` from the gitignored `logs/`, with per-run step windows, sha256 of every log used, and GPU-3 samples every 10 s:

| run | windows | foreign processes on GPU 3 | GPU util (median; busy-only median) | SM clock busy (min / median / max MHz) | memory clock | logs |
|---|---|---|---|---|---|---|
| R1 | 7 (incl. 3 failed parity attempts) | 0 (984 process samples) | 100%; 100% | 345 / 915 / 1,785 | 2,619 | 14 files |
| R5 | 5 (incl. 2 stopped sweeps) | 0 (2,221) | 0%; 100% (real-time replay idles) | 570 / 915 / 1,785 | 2,619 | 10 files |
| RH2 | 1 (plus the 23:07 restart; see RH2 report) | 0 (1,050) | 0%; 100% | 592 / 915 / 1,785 | 2,619 | 5 files |
| RH3 | 2 | **monitor and process logs MISSING**: the RH3 chain started no monitor. The watchdog ran and logged no foreign process. | — | — | — | 5 files (chain, steps, servers) |
| RH4 (added) | 2 | 0 (349) | 100%; 100% | 810 / 915 / 1,785 | 2,619 | 7 files |

"Foreign" means a GPU-3 process whose pid is not in the run's own vLLM server logs.

## Deviations and notes

- **Timestamp markers.** The spec's "[t=XXs] marker as in RH3 B" did not match RH3 B, which had no markers. Decision 1a (approved) kept B's layout without markers.
- **Header.** "One frame every 2 s from the session start", 31 tokens vs B's 27 (+4).
- **Stride and size.** These were chosen from input manifests only, before any accuracy was seen; the tables are in EXPERIMENTS.
- **Over-context questions.** Sent as built and recorded as HTTP 400 (decision 3a), never truncated.
- **Header shared across sessions.** The header is the same for every session, so different questions on one video share their cached history. This helped one Part 0 row and does not affect A–D accuracy (prefix caching OFF).

## Files

- `experiments/sember/study_rh4_inputs.py`: builder.
- `experiments/sember/study_rh4_fixed_stride.py`: Part 0, D1 and D2.
- `experiments/sember/study_rh4_analyse.py`: analysis.
- `experiments/cost/h100_monitoring_summary.py`: monitoring summary.
- `results/sember/study_rh4/`:
  - `study_rh4_inputs_manifest.jsonl.gz`
  - `study_rh4_part0_h100nvl.json`
  - `study_rh4_parity_h100nvl.json`
  - `study_rh4_requests_h100nvl.jsonl.gz`
  - `study_rh4_run_meta_h100nvl.json`
  - `study_rh4_results_h100nvl.json`
- `results/cost/h100_monitoring_summary.json`.
