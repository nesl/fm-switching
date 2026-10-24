# StudyR9 — can the cloud cheaply tell whether a question needs pruned history?

_Pre-registered 2026-10-23 (research/EXPERIMENTS.md, StudyR9). Stack: vLLM 0.31.0 venv `~/.venvs/fm-switching-vllm`, H100 NVL GPU 3, bf16, greedy, prefix caching off, processor cache off; Qwen3-VL-32B-Instruct (C0, C2) and Qwen3-VL-4B-Instruct (C1) served by vLLM. Device accuracy = committed llama.cpp C1 run (A6000) and cloud = committed R1 K1 (vLLM, H100); those are inputs, not new measurements._

## Decision

Ran 2026-10-23 15:22–16:11 on H100 GPU 3, after RH8 had finished and its server was stopped; requests strictly sequential, nothing else of ours on the host. All three pilot gates passed. 845 questions per detector, 0 errors.

**CLOUD-SIDE HISTORY CHECK: DOES NOT WORK** — two of the three pre-registered clauses fail:

| clause | required | C1 (4B-I localiser) | pass? |
|---|---|---|---|
| AUROC vs K3 uncovered (97 / 845) | ≥ 0.75 | **0.641** [0.570, 0.712] | **no** |
| escalation accuracy at e = 0.12 | ≥ 34.44 − 1 = 33.44 % | 33.85 % | yes |
| mean GPU-s / question vs C2 | ≤ 0.25x | **0.46x** (0.98 vs 2.11 s) | **no** |

| detector | AUROC [video-clustered 95 % CI] | GPU-s / question mean (median, p90) | accuracy at e = 0.05 / 0.10 / 0.12 / 0.20 (%) |
|---|---|---|---|
| C0 32B-I, question only | 0.430 [0.366, 0.493] | 0.053 (0.050, 0.059) | 31.48 / 32.54 / 32.43 / 33.37 |
| **C1 4B-I, low-res history** | **0.641** [0.570, 0.712] | 0.98 (0.80, 2.06) | 32.66 / 33.55 / 33.85 / 34.28 |
| C2 32B-I, low-res history | 0.755 [0.686, 0.819] | 2.11 (1.78, 4.29) | 32.19 / 33.14 / 33.85 / 35.15 |
| random (expectation) | 0.5 | — | 31.88 / 32.28 / 32.44 / 33.09 |
| question time qt alone (not pre-registered) | 0.685 [0.634, 0.735] | 0 | — |
| evidence oracle (the 97) | 1.0 | — | 32.76 / 34.04 / 34.47 / 34.93 (34.44 at e = 0.115) |
| perfect oracle | — | — | 36.45 / 41.42 / 43.43 / 51.01 |

Device alone (C1, 4B-I RECENT, llama.cpp): 31.48 %; cloud K1 (32B-I RICH): 39.53 %.

- **The cheap localiser does not separate the questions better than the question time alone.** C1's AUROC (0.641) is below the qt-only prior (0.685; questions late in long videos are more often uncovered). On the 678 questions where uncovered is possible (qt > 120 s), C1 0.638 vs qt 0.594 vs C2 0.738: C1 adds a little over the prior, C2 clearly more.
- **The expensive reference reaches the AUROC bar** (C2 0.755; binary "older than qt − 120" flag TPR 0.76 at FPR 0.17), so the signal exists in the low-res history — 4B cannot extract it reliably.
- **Accuracy at e = 0.12 passes for both C1 and C2 (33.85 %) — but this clause is weak**: the evidence oracle itself gains only +2.99 pp over the device (31.48 → 34.47 %), so a detector within 1 pp of it needs to capture only ~2/3 of that gain; random gets 32.44 %. The decision rests on the AUROC and cost clauses.
- **4B is not 4x cheaper end to end** (0.46x of 32B): both read the same 7.4k-token prompts (mean; max 19k; up to 640 images), and per-request latency includes API-server decoding and preprocessing of up to 640 PNG images with the processor cache off, which does not shrink with model size. The pre-registered metric is end-to-end latency; the GPU-only share was not instrumented.
- **C0 (question only) is anti-informative** (AUROC 0.43, CI excludes 0.5): 32B-I rates most questions 7–9 ("needs older observations") regardless, and slightly lower for those that do. History-ablation control: C1/C2's signal comes from the history, not from the question wording.

## Mechanism verification (Steps 1, 4, 5 recorded 2026-10-23 before any R9 GPU run; Steps 2–3 from the pilot gate)

**Step 1 — causal chain.** The device keeps only the last 120 s (DEV-RECENT); for 97/845 S-EMBER questions the annotated evidence lies before that window, and those are where escalating to the cloud with the full history pays (the evidence oracle: 31.48 % → 34.44 % at e = 0.115). The cloud already holds a cheap low-resolution copy of the history (RH3 A, 1 fps 160x128, ~22 tokens per frame). If a model reading that copy can locate *when* the evidence for a question appears, then "located time < qt − 120 s" identifies the questions whose evidence the device has pruned, and escalating those recovers the evidence oracle's gain without a per-question full-resolution pass. The chain needs: (i) the located time to carry information about the evidence interval (distance to the annotated interval), (ii) the score to rank the 97 above the rest (AUROC), (iii) a cost well below the expensive reference (4B vs 32B GPU-seconds).

**Step 2 — instantiate each link** (pilot = first 30 manifest questions per detector, gate before each sweep; full-run values in brackets).

| causal link | implementing quantity | pilot [full] value | varies as expected? |
|---|---|---|---|
| the model returns a usable time | parse rate | C1 1.00, C2 1.00, C0 1.00 [C1 1.000, C2 0.998, C0 1.000] | yes |
| located time carries content | distinct timestamps; located inside the annotated interval | C1 29 / 30, C2 27 / 30 distinct [inside interval C1 55.9 %, C2 62.0 %; median distance 0 s; p90 85.6 / 66.8 s] | yes |
| located time vs window boundary | flag "t < qt − 120" | [C1 flags 9.5 % (TPR 0.42, FPR 0.05); C2 23.7 % (TPR 0.76, FPR 0.17)] | yes |
| cost | end-to-end s / question | [C0 0.05, C1 0.98, C2 2.11] | yes (but see cost) |

No link is ABSENT or CONSTANT (no located time after qt; t = 0 in 1.2 % (C1) / 2.5 % (C2)).

**Step 3 — trace one unit** (real records, first manifest question; video 18C977…, qt 568 s, annotated evidence 541–568 s, K3 covered). C1: 569 frames + markers, prompt 16,569 tokens, answer "561", score (568 − 120) − 561 = −113 (inside the device window → not escalated; correct), distance to interval 0 s, 2.53 s. C2: "561", 5.25 s. C0: "3", digit-expectation 3.40, 201 tokens, 0.050 s.

**Step 4 — negative control.** C0 is the history-ablated control: the same question and options, no frames. If C1/C2's AUROC comes from locating the evidence in the history, it must exceed C0's; if it comes from question wording alone (some categories always need old history), C0 matches it. Category composition of the 97 is reported.

**Step 5 — alternative explanations.** (a) *Question-time prior*: questions asked late in long videos are more often uncovered; a localiser that outputs early times regardless of content would score well. Distinguished by distance to the annotated interval and by an AUROC of qt − 120 alone (reported). (b) *Score saturation*: if most located times are 0 or qt, AUROC is driven by a few values — score distribution reported. (c) *Marker leakage*: the `[t=XXs]` markers give the model the time axis; that is intended (it is how the cloud would ask), but it is an addition to RH3 A and is flagged.

## Results consistency check

1. **Cross-check.** Baselines reproduce committed values: device C1 31.48 % (accuracy_C1_meta), cloud K1 39.53 % (R1), evidence oracle 34.44 % at e = 97/845 (`figures/advisor_2026_10_23/numbers.md`), 97 positives (R1 K3). C1/C2 prompt tokens mean 7,416 vs RH3 A mean 5,736 + ~6 tokens per `[t=XXs]` marker x 253 images ≈ 7.3k — AGREE. **PASS.**
2. **Physical plausibility.** C2 (32B) 7.4k-token prompts in 1.78 s median ≈ 4.2k tok/s incl. image processing (RH5–RH7 32B prefill ~4.5–5k tok/s); C1 4B 0.80 s (~9k tok/s) — not faster than committed curves for a model 8x smaller. Prefix caching and the processor cache were off; each question has a distinct prompt. **PASS.**
3. **Distribution sanity.** Latency spread reported (p90, max); scores take 0–qt values (C1/C2) and 6 distinct text digits for C0 (0, 3, 5, 6, 7, 9); AUROCs with clustered CIs. **PASS.**
4. **Definition audit.** "Uncovered" = R1 K3 `evidence_covered == false` (RECENT = last 120 s at 1 fps; 97). The device C1 file's own flag (37 frames) gives 105 and is NOT used. RH3 A-format + `[t=XXs]` markers (flagged addition). e = 0.12 → 101 questions; the user's "34.4 %" is the oracle at e = 0.115. **PASS (with the flagged marker addition).**
5. **Claim linkage.** R4 / escalation trigger: the cheap cloud-side check of pruned-history need is not supported at 4B (AUROC 0.64, below a qt-only prior); a 32B check reaches 0.755 at 2.1 s per question. Weakens "the cloud can cheaply tell"; supports "the signal is in the low-res history".
6. **Proxy validity.** Ground truth is coverage of the annotated answer interval by the RECENT window (StudyO / R1 definition) — a proxy for "needs pruned history"; the accuracy gain it buys is small (+3 pp), so detecting it well has bounded value. GPU-seconds = end-to-end latency (includes API-server image processing) — stated.

## Deviations and notes

- `[t=XXs]` text markers added before each image (RH3 A has none) — pre-registered as a flagged methodological addition.
- e = 0.12 used as specified; the reference 34.44 % is at e = 0.115.
- Not pre-registered (reported, not decisive): qt-only AUROC; AUROC restricted to qt > 120 s; binary-flag TPR/FPR; category composition of the 97 (visual_detail_recall 29, location_trace 26, sequential_action 22, temporal_ordering 8, spatial 4, time_duration 4, object_comparison 2, counting 2).

## Files

- `experiments/escalation/study_r9_cloud_history_check.py` (vLLM venv), `experiments/escalation/study_r9_analyse.py`
- `results/escalation/study_r9/`: `study_r9_requests_h100nvl.jsonl.gz` (2,535 rows), `study_r9_run_meta_h100nvl.json` (servers, pilots), `study_r9_results_h100nvl.json`
- logs (not committed): `logs/queue11_r9.log`
