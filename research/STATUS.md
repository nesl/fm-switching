# FM-switching — Project Status

Last updated: 2026-09-03 (Study I3 re-analysis (CPU only): paired McNemar's test replaces independent-sample CI-overlap. Three defects fixed. VERDICT: INCONCLUSIVE for both models — no category survives BH correction. 4B overall p=0.246 (b=39,c=51); 8B overall p=0.047 (b=45,c=67) — 8B overall nominally significant but no category survives multiple-comparison correction. Corrected latency: 8B SPARSE inference 1,228ms matches I2 (prior 5,295ms included 4,374ms video-seek decode). Bias-only baseline lift +0.067–0.123 across all cells — models are doing real work, not letter guessing. Report: reports/study_i3_reanalysis.md.)

Last updated: 2026-09-03 (Study I3: S-EMBER SPARSE vs TEMPORAL at full power — COMPLETE. 1,836 valid trials: 4B and 8B × SPARSE/TEMPORAL, n=459 each. SPATIAL arm dropped (settled by I2). VERDICT: UNDERPOWERED — no category passes CI-overlap test for either model. Consistent direction: TEMPORAL ≥ SPARSE in 10/14 category×model cells; overall 4B +2.6pp, 8B +4.8pp. Strongest trends: 8B sequential_action +11.5pp, 4B/8B location_trace +9.6pp, 8B temporal_ordering +8.5pp — all within combined CI. SPARSE wins: visual_detail_recall (both models), object_comparison (4B). Latency: 4B TEMPORAL 7.2× SPARSE (5,871 vs 810ms); 8B TEMPORAL 1.3× SPARSE (7,029 vs 5,295ms). Position bias flagged in all 4 cells. Key method: sequential video decode eliminates PyAV backward seeks, reducing 8B TEMPORAL from ~95s/trial to ~7s. Report: reports/study_i3_budget.md.)

Last updated: 2026-09-03 (Study I2: S-EMBER frame-budget experiment — COMPLETE. Three arms: SPARSE (16f, ~270 tok/f, budget never binds), SPATIAL (42f at 1fps, verified no spatial reduction, ~270–284 tok/f), TEMPORAL (256f at 1fps, budget binds, ~44 tok/f). 1,318 valid trials, 0 errors. Overall: TEMPORAL wins (4B 0.340, 8B 0.340); SPARSE second (4B 0.266, 8B 0.250); SPATIAL lowest (4B 0.218, 8B 0.250). TEMPORAL wins: time_duration and sequential_action (both models). SPARSE wins: spatial_aware_reasoning and object_comparison (both). 8B−4B gap negligible across all arms (≤0.032) — confirms no tier-placement benefit from model routing on S-EMBER. Two bugs fixed from StudyI: (a) vision_tokens now from VIDEO_TOKEN_ID count in input_ids (not video_grid_thw product, which overstates ~4.2×); (b) SPATIAL capped at 42 frames. KV bytes per token: 147,456 B/tok for both Qwen3-VL-4B/8B (differs from committed 57,344 for Qwen2.5-VL-7B — different model family, no contradiction). Report: reports/study_i2_budget.md.)

Last updated: 2026-09-02 (Study I diagnostic — S-EMBER tier gap pre-rerun checks. Bug 1 CONFIRMED: Qwen3VLVideoProcessor 3D budget (T×H×W ≤ 25,165,824) silently reduces DENSE (256 f) spatial resolution 5.8× to 48 tok/frame vs SPARSE 270 tok/frame; crossover at 43 f; fix = cap DENSE ≤ 42 f (≈0.18fps at median qt). Bug 2 NOT a scoring bug: 8B E-position bias in spatial_aware_reasoning; 4B genuinely weak on location_trace. Vision LOAD-BEARING: text-only 21.6% vs SPARSE-4B 26.6% (+5.0pp > 3pp gate). SPARSE arms are valid; DENSE rerun pending (both models). Preliminary SPARSE-only result: 8B−4B gap = +0.7pp NEGLIGIBLE — no tier-placement benefit from model routing on S-EMBER. Report: reports/study_i_diagnostic.md. Next: rerun DENSE arms with ≤42-frame cap, run analyse.py, update study_i_tier_gap.md.)

Last updated: 2026-09-01 (Study H2: S-EMBER annotation analysis — HF access granted, annotation-level analysis complete. PRIMARY FINDING: E2 retracted. All 3,141 videos are multi-question (2–6 Q/video); 99.97% have distinct question_time values; median spread 204 s (IQR 167 s, p90 429 s). A growing prefix exists. S-EMBER ACCEPTED as session workload. Evidence distance (nearest = qt−answer_end): median 21 s, IQR 56 s, p90 117 s — wide, not clustered near zero. Category differences: object_comparison and spatial_aware_reasoning have nearest=0 s (evidence ends at query time but starts far back; farthest median 68–90 s); location_trace nearest median 44 s. After excluding counting_objects_events (1,627/9,448 = 17.2%): 7,821 QA / 3,126 videos / 2,755 multi-Q videos. Session feasibility at 1fps: max KV 22.3 GB, 0% exceed 32 GB usable vRAM — fits trivially; retention trade-off is driven by latency and transfer cost, not memory exhaustion. 10 annotation artifacts (aet = floor(qt)+1, 1.0 s exactly) excluded from evidence distance. SC5 corrects Study H: memory_recency = qt − answer_start_time (not answer_end_time). Report: reports/study_h2_sember_annotations.md.)

Last updated: 2026-09-01 (Study H: S-EMBER benchmark structure audit — STOPPED, two escalation conditions met. E1: HF dataset gated (403); psharma05 not approved, request access at huggingface.co/datasets/facebook/S-EMBER. E2 (the decisive one): S-EMBER's GSER evaluation protocol makes each question a fresh forward pass over video[0, question_time] — no shared accumulating stream exists. S-EMBER REJECTED as workload for runtime state retention study. Offline findings from HF filename metadata: 3,141 videos, 387.9 h, median 367 s, bimodal at 300 s/600 s. Scoring: MCQ = exact letter match; grounding = temporal IoU (no LLM judge required); optional Gemini judge for answer text. Feasibility: median video at 1fps fits 48 GB A6000 (6.8 GB KV); max video at 2fps OOM. Report: reports/study_h_sember_structure.md.)

Last updated: 2026-08-31 (Study G2: Transfer Cost clean rerun — A6000. Fixes three Study G defects: D1 maintenance omitted, D2 synthetic frames (stereotyped 33-token summaries), D3 fidelity claims forbidden. Under accounting A (transfer+reconstruction only, StudyG replication): R7 dominates 24/24 cells at p50 both families — same conclusion as StudyG, confirming D1 caused the error. Under accounting B (maintenance_cumulative + f×p50_routing): R3 dominates all cells at f∈{1,2,5}; R3 wins 16/24 at f=10; R3 and R7 split 12/12 at f=25 (R7 wins only N≤6). R7 never dominates a majority of cells at any tested routing frequency. R7 maintenance at N=48 = 76s (LOW) / 94s (HIGH) vs R3 ≈ 29ms; crossover f >> 25 for N≥12. Q2: R7 payload content-dependence masked by 128-token cap for N≥6. Q3: R6 KV 40× larger than R1 at N=48 (1,050 MB), not competitive. Report: reports/study_g2_transfer_cost.md.)

Last updated: 2026-08-31 (Study G: Transfer Cost — A6000. Measured payload size, reconstruction latency, and end-to-end transfer+reconstruction distribution for 7 representations (R1 PNG, R2a/b JPEG, R3 window-k3, R4 pixel tensors, R5 vision embeddings, R6 KV analytical, R7 text summary) at N∈{1,3,6,12,24,48}, 4 network profiles (campus/urban/indoor/harsh), 200 samples/cell. Dominance verdict: R7 wins p50 in 24/24 cells. R3 is the best non-summary representation for N≥6 (constant payload 697 KB, reconstruction 365 ms). R6 KV extraction not possible (DynamicCache.key_cache absent in transformers 5.12.1); size analytical only (1.1 GB at N=48), reconstruction not measured. R4/R5 same-model-only and dominated on end-to-end latency. Dominance does not trivialize the decision: R7 wins on transfer cost, loses on fidelity for dense workloads (LoCoMo −24 pp). Report: reports/study_g_transfer_cost.md.)

Last updated: 2026-08-31 (Study F — **Jetson AGX Orin arm** (Jetson-only; companion to the A6000 arm below and to Study E). Diagnosed BOTH suspect Study E Orin numbers as Jetson software-stack artifacts. (a) decode 9.40/9.09 tok/s (4B/8B) = ~106–110 ms/token FIXED overhead floor in HF generate()+dynamic cache; 4B at only 40.7% of its 23.1 tok/s bandwidth roofline (204.8 GB/s); 4B≈8B parity across a 2× weight gap is the overhead signature — contrast the A6000 arm where 4B (48.5) separates from 8B (32.0). C2 static-cache / C3 compile UNAVAILABLE (triton absent on aarch64; not installed, per scope). (b) 53.4 GB is a **torch.no_grad() OMISSION** in Study E's Orin measure_full (Study B/A6000 wrapped the identical forward in no_grad): reproduced exactly — 53.39 GB with-grad vs 17.64 GB with no_grad @ N=6; N=12 feasible at 18.7 GB, NO OOM (matches A6000 N=6 17.4 GB + the ~16.7 GB arithmetic). torch mem counters over-report ~2× vs /proc/meminfo RAM under unified memory. **Retract Study E's N=6 memory ceiling / N=12 OOM / O(L²)-SDPA-attention claim, and its "9.4 tok/s = device decode rate / parameter-independent" claim.** Report: reports/study_f_orin_diagnostic.md.)

Last updated: 2026-08-31 (Study F: A6000 diagnostic arm — reference-machine companion to Study E. Part 1 (Qwen3-VL 4B-I vs 8B-I decode rate, C1/C2, 5 reps, 256 fixed tokens): 4B separates clearly from 8B on A6000 — 48.5 vs 32.0 tok/s (C1), 54.8 vs 35.0 tok/s (C2 static cache). Rooflines: 86.5 vs 43.8 tok/s. 4B at 56% RL; 8B at 73% RL — 8B closer to ceiling, consistent with a fixed per-token overhead floor. C3 (torch.compile fullgraph) FAILED for both models (flash-attn not traceable). Contrast with Study E Orin: 4B=8B=9.4 tok/s. Part 2 (Qwen2.5-VL-7B phase memory N=3–12): weights 16.8 GB, vision encoding delta <0.3% of peak, KV matches Study B (1.000 ratio), unaccounted activation 0.2–0.7 GB grows with N. A6000 N=6 peak 17.4 GB vs Orin 53.4 GB (cross-machine attribution deferred). N=1 GC artifact flagged. All sanity checks passed. Report: reports/study_f_a6000_diagnostic.md.)

Last updated: 2026-08-31 (Study E: device-side cost on Jetson AGX Orin, 64 GB, MAXN — the device half of the cost model. Part 1 (360 trials, Qwen3-VL 4B/8B Instruct+Thinking): on-device decode ~9.4 tok/s for ALL models (overhead/bandwidth-bound, not param-bound — 4B=8B); 8B cost is in TTFT (434 vs 280 ms) and memory (17.7 vs 9.0 GB). Orin ~4× slower than A6000 on Instruct, ~3–5× slower decode on Thinking. Part 2 (Qwen2.5-VL-7B state cost): full-retention ceiling **N=6** (peak 53.4 GB; OOM at N=12) vs A6000 N≥48 — O(L²) SDPA attention memory, no flash-attn, despite 64 GB unified. Part 3: **no throttling** over 14.5 h (max tj 65 °C, GPU pinned 1.3005 GHz, 0/10,345 throttle samples), throughput flat. Ran 5.10.2/torch2.8/SDPA-no-flash-attn vs A6000 flash-attn → gaps carry a software-stack component. Report: reports/study_e_orin_cost.md.)

Last updated: 2026-08-30 (Study D2: full 4-model run — L1–L3 main matrix (1,260 trials) + L4 probe (20 trials). Key finding: 4B-Thinking = 8B-Thinking at L3 within-1 (0.767 each); 4B-T beats 8B-I by +0.034 within-1 at 62× latency cost; think-token IQR/median=1.84 at L3 (not predictable). L4 probe: non_termination=20–30% at 8192 tokens; verbose_bounded=0 — budget failure is reasoning non-convergence, not verbosity.)

Last updated: 2026-08-30 (Study D: reasoning compute vs parameters — 4B-Instruct vs 4B-Thinking on COCO person counting, 720 trials. Stop condition fired at qwen3vl4b_t/L4 (30% budget hit > 5%). Reliable finding: 4B-Thinking beats 4B-Instruct at L3 by +0.233 pp exact-match (0.400 vs 0.167); think tokens scale 54→1626 L1→L4. 8B models pending rerun with max_new_tokens=8192.)

Last updated: 2026-08-30 (Study C: difficulty scaling — 1,440 trials, COCO val2017, 2 models × 2 modes × 4 difficulty levels. RQ1: stepwise token count scales monotonically with difficulty (7B: 69→140 tok, 3B: 75→126 tok). RQ2: 3B vs 7B accuracy gap is non-monotone; reverses at high difficulty in stepwise mode. RQ3: chain-of-thought does not close the gap and collapses 7B accuracy to 0.000 at L4 (8+ people). Exact-match accuracy is near-floor for both models at L3–L4 in both modes.)

(Study A + Study B: vision cost characterization. Study A: vision token count, KV bytes, and output token count are content-independent at fixed 560×560 px — all 12 images → 400 tokens, KV=24.9 MB, ratio=1.000; prefill 145–148 ms with 2.83 ms cross-image spread that is run-order confounded. Study B: per-token KV byte cost is identical for vision and text tokens (57,344 B/tok, ratio=1.000 all cells); operational cost ordering differs from text — vision window (377 ms constant) << full (6,332 ms at N=48) << summary construction (27,854 ms); text ordering is full (66 ms warm-append) < window < summary; H3 confirmed for KV cost only, H4 confirmed for ordering/magnitudes.) (E38: three slide figures from committed data. Fig 1: maintenance cost by state form — full=66ms, win10_amortized=653ms, sum200=5822ms (horizontal bar, log scale). Fig 2: the inversion — KV footprint vs maintenance cost (ascending footprint = descending maintenance). Fig 3: N_eff=min(N_mem,N_accel) vs turn interval at kv=9GiB — full=8 always mem-bound; win10 rises 6→23 (crossover ti≈17.2s); sum200 rises 0→10. Plotting only; all values from committed sources. Two discrepancies flagged: win10 amortized 653ms (E34) vs 689.7ms (E35/E36e sim); sum200 KV 9.2MB (160 tok×57344B) vs task-spec 11.5MB (200 tok). Both documented; direction of claims unaffected.)

E36h: two-part rule ablation. Mean admission_gain=+9.62 pp; mean representation_gain=+0.48 pp across 16 cells (20× ratio). rep_gain positive in 2/16 cells (kv=4.5 ti=5s: +2.09pp; kv=18 ti=15s: +5.64pp), zero in 14/16. S3 corrected vs footprint_ranked_mb (like-for-like representation comparison with MB admission held constant): +0.006 to +0.303 pp at ti=5s — N_eff criterion beats footprint density most clearly at large kv. Greedy_upper (renamed from oracle) beats neff_marginal at kv=4.5 ti=5s by 1.33pp (KV-ASC tiebreaker more space-efficient in mixed-fidelity regime). 10 fidelity-mix violations explained: mixed fleet + zero rep_gain occurs when always_window_mb already achieves the optimum.

E36g: marginal-benefit admission ordering. neff_marginal (two-part rule: argmax N_eff for fidelity + marginal benefit of edge residency for admission) passes S2 in all 16 cells (0/16 fail; vs neff_ranked 3/16 fail) and S3 (+0.159–0.360 pp vs fp_ranked at ti=5s). Distinguishable from every fixed policy in 13/16 cells. E36f mixed-fidelity diagnosis superseded: actual cause = N_eff ordering admits small-L zero-MB robots first; neff_marginal fixes this by ordering by marginal benefit (binary: device fails?). Oracle beaten in 1 cell (kv=18,ti=15: +0.007 pp artifact).

E36f: neff_ranked policy S2 re-verification. S2 FAIL in 3 cells at ti=5s (kv=4.5/9/36 GiB; diagnosed in E36g as admission ordering defect, not mixed-fidelity effect); E36e's kv=18GiB ti≥30s cells PASS. S3 PASS (+0.2–16.4pp vs fp_ranked). 0/16 cells selection-distinguishable; 11/16 outcome-distinguishable.

E36e: fleet capacity relationship with proactive maintenance model. Part A analytic P1–P4 all PASS: memory ordering fully inverted vs accelerator ordering; win10 crossover at ti≈17s; footprint_ranked selects 2 fewer sessions than maintenance_ranked at ti=5s kv=9GiB; gap collapses with maint=0. Part A2: win10 is N_eff-maximizing at ti≥15s (non-monotone P1b PASS); 3-way non-monotone collapses at B=4/periodic-5; 2-way LoCoMo claim immune to batching. Part B: S1 PASS (regime-dependent optimum), S2 FAIL (structural: maintenance_aware uses N_accel score, correct only in accel-bound regime; fails at kv=18GiB ti≥30s, regret +12.8–13.5pp; N_eff-ranked policy would pass by construction), S3 PASS (+7–26pp gap at ti=5s all kv_caps), S4 reported (40/288 activating). Prior E36d FIFO queue model was incorrect: win10 slide maintenance blocked robot TTFT; correct proactive model charges maintenance to epoch budget only. E36d superseded.)

## Framing

Mobile FM agents operating at the edge must maintain session state between turns.
That state can be held in one of four representations — full-replay, window-10,
summary-80, or summary-200 — which differ in reconstruction cost (transfer + re-prefill
latency) and in fidelity (how much task-relevant information survives compression).
**Context Inertia** is the joint cost of holding that state: it has a *physical* component
(transfer and reconstruction time, which grows with context length and degrades with
network conditions) and a *semantic* component (cheaper representations discard
information the future turn needs, in a workload-dependent way).

## Two measurement instruments

| Instrument | What it measures | Status |
|---|---|---|
| **Fidelity audit** | QA accuracy of blind / summary-80 / summary-200 / window-10 / full across EgoSchema, Infini-THOR, LoCoMo | Complete: three-regime taxonomy established under Qwen2.5-7B and Mistral-7B (Phase 0a gate passed) |
| **Cost profiling** | Restore, update, and state-size as a function of context length per representation per tier | **Complete on all three tiers** — A6000, RTX 3090 Ti, and Jetson AGX Orin (2026-08-19); summary-update full-context rerun done per tier |

## Current stage

1. **Regime taxonomy** (fidelity, Phase 0a) — *complete*.
   EgoSchema = gist-compressible; Infini-THOR = structured-compressible; LoCoMo = dense-incompressible.
   Held under a second model (Mistral-7B); gate passed.

2. **Physical inertia cost** (Phase 1) — *complete on all three tiers* (A6000, RTX 3090 Ti, Jetson AGX Orin).
   Key crossovers: xB (summary pipeline beats full re-prefill) = L≈65K on A6000, never in range on
   3090Ti (update OOMs above 32K). xC (window ≥10× cheaper) = L≈8K on A6000, L≈4K on 3090Ti.
   Jetson Orin: full_restore feasible ≤16K (75 s), infeasible ≥24K by the 120 s time budget (never OOMs,
   65.9 GB unified); ran the 5.10.2/torch2.8/SDPA-no-flash-attn stack (vs 4.46.3/flash-attn on flash), so
   Jetson-vs-flash gaps include a software-stack component. Jetson crossover rows not yet computed.

3. **Simulator** — *E24, E24b, and E24c complete (2026-08-19)*.
   E24 (1,260 runs, single-edge): placement-aware policies +12pp vs reactive; joint ≤3pp over cache_value.
   E24b (9,720 runs, 3-edge, stressed): fidelity_only outperforms joint by 6–14pp across all regime mixes;
   L-scaling and drift-scaling predictions both falsified.
   E24c (1,440 runs, shared solver, 10 policies): COUPLING FALSIFIED (final). Median gap joint − best-decomposed
   = −1.3pp. New fidelity_first_lifecycle policy (lifecycle-cost-aware fidelity selection) beats joint in 38/48
   cells by up to 17.2pp. Root cause: joint's density metric (V/S_ready) over-selects sum200 (tiny, high density)
   over win (lower density, 100× cheaper refresh at large L). Value function incomplete — does not capture lifecycle
   refresh cost. Thesis position: lifecycle-cost-aware fidelity selection at current serving node is sufficient;
   explicit joint placement×fidelity optimization provides no value.
   Prior SSM+MPC+RL code in `simulator/` is kept for lineage.

## Next gate

Narrow the thesis to: "lifecycle-cost-aware fidelity selection at the current serving node is sufficient;
joint placement×fidelity optimization does not add value." Prepare submission with E24+E24b+E24c as the
simulator evidence. Recommend incorporating lifecycle cost into the value function as a future-work note.
E26 (vLLM calibration) and E23 (Jetson cost) are supporting evidence; proceed when ready but not blocking.

## Target venue

SenSys 2027 (second round) or MobiSys 2027. MLSys fallback if simulator results are strong but
framing needs adjustment.

## What is running where

| Host | Role | Current activity |
|---|---|---|
| **flash / A6000** | Fidelity experiments, server-tier cost profiling | Idle (Phase 1 fix-up committed) |
| **flash / RTX 3090 Ti** | Edge-tier cost profiling (GPU 0) | Idle (Phase 1 fix-up committed) |
| **Jetson AGX Orin** | Device-tier cost profiling (separate SSH host) | Idle — E37 done (qwen3b vs qwen7b device-tier time ratio, 2026-08-24); E23 done (qwen7b cost profile, 2026-08-19) |

Flash hosts both A6000 (GPU 1) and RTX 3090 Ti (GPU 0) in the same machine.
Jetson is a separate SSH host; pull before running so it writes to `results/cost/profiles/jetson_orin/`.
