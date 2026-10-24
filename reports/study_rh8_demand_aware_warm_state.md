# StudyRH8 — demand-aware partial warm state vs all-eager and all-lazy (H100, vLLM)

_Pre-registered 2026-10-23 (research/EXPERIMENTS.md, StudyRH8). Stack: vLLM 0.31.0 venv `~/.venvs/fm-switching-vllm`, FlashAttention 3, H100 NVL GPU 3, native OffloadingConnector 256 GiB + processor cache 128 GiB, Qwen3-VL-32B-Instruct bf16. vLLM numbers only._

## Decisions

Fleet 2026-10-23 12:08–15:22 (3.23 h vs 3.87 h estimate); smoke 11:55–12:07. All 10 cells completed; no STOP condition fired (host-hit verification passed in all 10 cells; fallbacks ≤ 1.41 %). One repetition per policy cell.

**Fraction of escalations with TTFT ≤ T** (denominator: in-window escalations minus over-context 400s — 4 at D64, 0 at D96, the same escalations in every policy):

| D | T | ALL-EAGER | ALL-LAZY | MIX-RANDOM | MIX-DEMAND | MIX-DEMAND − best rival (device-clustered 95 % CI) |
|---|---|---|---|---|---|---|
| 64 | 2 s | **0.821** | 0.578 | 0.624 | 0.729 | −9.2 pp vs ALL-EAGER [−19.3, −0.4] |
| 64 | **5 s** | **0.991** | 0.940 | 0.940 | 0.972 | **−1.8 pp** vs ALL-EAGER [−4.6, +0.5] |
| 64 | 15 s | 1.000 | 1.000 | 1.000 | 1.000 | 0 |
| 96 | 2 s | 0.007 | 0.423 | 0.423 | **0.573** | +15.0 pp vs ALL-LAZY [+9.5, +19.7] |
| 96 | **5 s** | 0.019 | 0.730 | 0.719 | **0.835** | **+10.5 pp** vs ALL-LAZY [+6.7, +14.6] |
| 96 | 15 s | 0.060 | 0.996 | 1.000 | 1.000 | 0 (tie with MIX-RANDOM) |

- **D = 64: COORDINATION NOT SHOWN.** The dominant pure policy is **ALL-EAGER** (99.1 % within 5 s). It is below its knee here (RH7: EAGER sustains D64 at 5 s), so warming every device makes every escalation cheap, including the low-demand ones that MIX-DEMAND leaves lazy (low-demand within 5 s: ALL-EAGER 0.988 vs MIX-DEMAND 0.939). Binding resource at ALL-EAGER D64 (RH7 rule): kv_running_set (GPU util 100 %, engine queue median 4, waiting max 35, KV max 1.00, PCIe 14.9 GB/s, 0 host misses) — busy but not saturated (drain 0.1 s).
- **D = 96: DEMAND-AWARE ALLOCATION WINS.** MIX-DEMAND beats the best rival (ALL-LAZY) by +10.5 pp at 5 s and +15.0 pp at 2 s; both CIs exclude 0 and the margins exceed the run-to-run noise measured by the repeats (≤ 0.5 pp at 5 s). ALL-EAGER collapses (median 131 s; append service saturated: engine queue 894, 653 requests in flight at window end), as in RH7. Binding at MIX-DEMAND D96: rule label kv_running_set (KV max 0.98, waiting max 30, GPU util median 61 %, no drain) — short queueing bursts, not saturation.
- **The win is demand matching, not load reduction (negative control).** MIX-RANDOM has the same eager count and append load (1,623 vs 1,627 appends at D96) but sits on ALL-LAZY (0.719 vs 0.730 at D96; 0.940 vs 0.940 at D64): warming the wrong quarter buys nothing. MIX-DEMAND's gain is concentrated on the high-demand devices (within 5 s 0.900 vs ALL-LAZY 0.765 at D96; median 0.41 vs 1.95 s), with computed tokens per escalation 323 (warm) vs 5,809 (lazy). Low-demand devices are not hurt (0.722 vs 0.670).
- **Run-to-run variance (repeats of RH7 D64):** EAGER median / p90 / p99 / max ratios 1.05 / 1.21 / 1.31 / 1.29, within-5 s 1.000 vs 1.000, within-2 s 0.826 vs 0.876; LAZYD 0.98 / 1.02 / 0.99 / 1.07, within-5 s 0.709 vs 0.704. Medians and the 5-s fraction reproduce; eager tails vary by up to ~30 % and the 2-s fraction by ~5 pp.

**Overall:** which policy is best depends on whether the all-eager fleet is below its knee. Below it (D64) warm everything; past it (D96) warm only the devices that escalate often — that beats both pure policies and a demand-blind partial allocation. The pre-registered rule therefore finds coordination at D96 and not at D64.

Caveats: single repetition per policy cell (repeats only for the RH7 configuration); the fallback rate was > 1 % (flag) in MIX-DEMAND D64 (1.30 %), MIX-DEMAND D96 (1.41 %) and REP-EAGER (1.33 %), all < 3 % stop; the binding-rule label kv_running_set fires in non-saturated cells (RH7 noted the flags cannot separate GPU KV capacity from offload-load throughput); D96 is ~1.2x D64's window load (RH7: devices exhaust their plans).

## Mechanism verification (Steps 1–5; recorded 2026-10-23 after the smoke (11:55–12:07) and before the fleet started at 12:08)

**Step 1 — causal chain.** Keeping a device's history warm (eager appends) makes its escalations cheap (the history is reused from GPU or host KV; only the question and the last frames are computed), but costs GPU/PCIe service for every append whether or not the device escalates (C4 / FORMULATION §context inertia: reconstruction cost grows with history; maintenance is charged continuously). RH7 measured both sides with equal demand: eager wins below its knee (~64 devices of appends) and loses past it, because append service, not escalations, saturates the warm path. If demand is heterogeneous, the value of warm state is concentrated on the devices that escalate often, while its cost is per device. Making exactly the high-demand quarter eager should therefore (i) give most escalations (63–64 % come from the high-demand devices) the warm-path TTFT, (ii) carry only ~25 % of ALL-EAGER's append load (below RH7's eager knee even at D96: 24 eager devices vs a knee between 64 and 96), and (iii) leave the remaining lazy escalations (20 % rate on 75 % of devices) to a GPU with spare compute. A demand-blind choice of the same number of eager devices (MIX-RANDOM) pays the same append cost but warms devices that rarely escalate, so its advantage over ALL-LAZY should be smaller.

**Step 2 — instantiate each link** (smoke values, D8, 60-s window; fleet values added after the run).

| causal link | implementing quantity | smoke value | varies as expected? | evidence |
|---|---|---|---|---|
| demand is heterogeneous | scheduled in-window escalations high / low | D64 140 / 82 (16 vs 48 devices); D96 170 / 97 | yes (8.75 vs 1.7 per device at D64) | `window_plan` (deterministic, same in all policies) |
| eager devices keep state warm | escalation cached / prompt tokens on eager devices | 2,912 / 3,278; 11,824 / 12,235 | yes | smoke records (MIX-DEMAND dev 6, 7) |
| lazy devices recompute | same on lazy devices | 16 / 3,277; 16 / 12,234 | yes — same device 7 escalation 3.09 s lazy vs 0.18 s eager | smoke records (MIX-RANDOM dev 6, 7) |
| append load ∝ eager devices | appends in window | D64: ALL-EAGER 5,471, MIX-DEMAND 1,379, MIX-RANDOM 1,394, ALL-LAZY 0 | yes | `window_plan` |
| demand-aware vs demand-blind | escalations landing on eager devices | D64 MIX-DEMAND 140 / 222 vs MIX-RANDOM 65 / 222 | yes | `window_plan` |
| host tier | load bytes / external hit token | no host hits at D8/60 s (fits GPU KV) | measured per fleet cell | kv_offload counters |
| fallbacks | cache-miss re-sends | 0 / 33 | per cell | records |

No link is ABSENT or CONSTANT.

**Step 3 — trace one unit** (smoke, real records). Device 7 (high-demand), escalation at 134 frames of history. MIX-DEMAND (device eager): warm-up sent 108 frames (16.4 MB, 9,766 tokens); appends every 10 s; the escalation body is 3 new frames (0.44 MB of a 20.35 MB full-bytes equivalent) + 131 uuid refs; prompt 12,235 tokens, cached 11,824, computed 411; TTFT 0.176 s. MIX-RANDOM (same device lazy-delta, first escalation of the session): 134 frames' bytes (20.37 MB), prompt 12,234, cached 16, computed 12,218; TTFT 3.087 s. Bound: neither (D8, engine idle) — the difference is pure recompute of the history (12.2k tokens at ~4k tok/s ≈ 3 s).

**Step 4 — negative control.** The mechanism is "matching warm state to demand". It is switched off at equal append cost by **MIX-RANDOM** (same number of eager devices, chosen independently of demand: 5/16 overlap at D64, 6/24 at D96; appends 1,394 vs 1,379). If demand matching drives a MIX-DEMAND win, MIX-RANDOM must sit near ALL-LAZY on the high-demand devices; if MIX-DEMAND wins merely because a quarter of the fleet is warm, MIX-RANDOM wins too. The two repeat cells (RH7 configuration, D64) measure run-to-run noise against which the 5-pp margin is read.

**Step 5 — alternative explanations.** (a) *MIX-DEMAND wins only because the GPU is less loaded* (fewer appends) — then MIX-RANDOM, with the same load, matches it; distinguished by Step 4. (b) *ALL-EAGER wins at D64 because RH7's knee moved* — the D64 repeat (rate 1.0) bounds RH7 variance; ALL-EAGER at RH8 demand offers the same appends but only 42 % of RH7's escalations. (c) *Window-start burst* (RH7: lazy first escalations bunch at window start) — reported per cell; it affects ALL-LAZY and the lazy part of the MIX cells, not the eager devices. (d) *Fraction-within-T moved by over-context 400s* — excluded from the denominator, identical across policies; counts reported.

## Per-cell metrics

Window 900 s; all TTFTs from submission; submit lag p99 ≤ 0.22 s in every cell (harness on time). "hi" / "lo" = high- / low-demand devices.

**Latency** (escalation TTFT s, p50 / p90 / p99 / max)

| cell | esc n (hi / lo) | all | high-demand | low-demand | eager devices within 5 s | lazy devices within 5 s |
|---|---|---|---|---|---|---|
| ALL-EAGER D64 | 218 (136 / 82) | 0.91 / 3.07 / 4.98 / 5.13 | 0.97 / 3.11 / 4.98 / 5.13 | 0.83 / 2.98 / 4.67 / 5.10 | 0.991 | — |
| ALL-LAZY D64 | 218 | 1.67 / 4.02 / 8.83 / 9.66 | 1.49 / 3.89 / 8.36 / 9.66 | 2.58 / 4.78 / 8.21 / 9.28 | — | 0.940 |
| MIX-RANDOM D64 | 218 | 1.39 / 4.27 / 8.84 / 9.32 | 1.09 / 3.77 / 8.87 / 9.32 | 2.49 / 4.96 / 8.43 / 8.84 | 0.969 (n 65) | 0.928 (n 153) |
| MIX-DEMAND D64 | 218 | 0.51 / 3.65 / 6.62 / 8.34 | 0.30 / 2.13 / 3.87 / 6.32 | 2.53 / 4.63 / 7.14 / 8.34 | 0.993 (n 136) | 0.939 (n 82) |
| ALL-EAGER D96 | 267 (170 / 97) | 131.2 / 179.7 / 183.0 / 183.6 | 133.7 / 179.3 / 182.7 / 183.6 | 127.4 / 180.4 / 183.0 / 183.1 | 0.019 | — |
| ALL-LAZY D96 | 267 | 2.66 / 8.19 / 13.63 / 15.26 | 1.95 / 7.69 / 12.66 / 14.36 | 3.49 / 9.52 / 13.59 / 15.26 | — | 0.730 |
| MIX-RANDOM D96 | 267 | 2.86 / 7.76 / 10.62 / 11.86 | 2.13 / 7.48 / 10.05 / 11.86 | 3.79 / 8.29 / 10.78 / 11.40 | 0.786 (n 70) | 0.695 (n 197) |
| MIX-DEMAND D96 | 267 | 1.21 / 6.53 / 12.34 / 13.50 | 0.41 / 4.78 / 9.93 / 12.37 | 3.32 / 8.24 / 13.24 / 13.50 | 0.900 (n 170) | 0.722 (n 97) |
| REP-EAGER D64 (rate 1.0) | 533 | 1.18 / 2.56 / 3.92 / 4.45 | = all | — | 1.000 | — |
| REP-LAZYD D64 (rate 1.0) | 533 | 2.86 / 15.84 / 26.04 / 30.32 | = all | — | — | 0.709 |

**Resources** (whole cell = window start → drain end)

| cell | appends | token hit | host share of hits | host reload TB | PCIe avg / best 30 s (GB/s) | computed tok/s achieved / demand | computed tok per esc (incl. appends; esc only hi / lo) | GPU util median % | engine q median / waiting max | in flight at end / drain s | KV median / max | live set (eager) / 256 GiB | fallbacks | binding (RH7 rule) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL-EAGER D64 | 5,430 | 0.953 | 0.99 | 13.46 | 14.9 / 17.7 | 2,857 / 2,841 | 11,731 (320 / 329) | 100 | 4 / 35 | 1 / 0.1 | 0.47 / 1.00 | 0.62 | 30 (0.52 %) | kv_running_set |
| ALL-LAZY D64 | 0 | 0.392 | 0.88 | 0.21 | 0.2 / 0.9 | 1,595 / 1,599 | 6,602 (5,155 / 9,001) | 0 | 0 / 2 | 0 / 0 | 0.00 / 0.74 | — | 0 | none flagged (engine unattributed) |
| MIX-RANDOM D64 | 1,394 | 0.884 | 0.96 | 3.36 | 3.7 / 6.0 | 1,956 / 1,939 | 8,004 (3,637 / 7,451) | 37 | 0 / 14 | 1 / 0.1 | 0.00 / 1.00 | 0.17 | 13 (0.80 %) | kv_running_set |
| MIX-DEMAND D64 | 1,338 | 0.909 | 0.93 | 3.37 | 3.7 / 5.5 | 1,537 / 1,541 | 6,362 (321 / 9,001) | 6 | 0 / 12 | 0 / 0 | 0.00 / 0.89 | 0.21 | 21 (1.30 %) | engine (unattributed) |
| ALL-EAGER D96 | 6,448 | 0.956 | 0.99 | 17.05 | 16.7 / 19.4 | 2,973 / 3,369 | 11,358 (322 / 326) | 100 | 894 / 1,186 | 653 / 118 | 0.59 / 0.98 | 0.88 | 40 (0.58 %) | kv_running_set |
| ALL-LAZY D96 | 0 | 0.350 | 0.97 | 0.27 | 0.3 / 0.8 | 2,218 / 2,221 | 7,488 (5,809 / 10,431) | 0 | 0 / 4 | 0 / 0 | 0.00 / 0.92 | — | 0 | none flagged (engine unattributed) |
| MIX-RANDOM D96 | 1,623 | 0.885 | 0.98 | 4.40 | 4.9 / 8.7 | 2,476 / 2,482 | 8,366 (4,465 / 7,554) | 85 | 1 / 28 | 0 / 0 | 0.12 / 0.98 | 0.23 | 8 (0.41 %) | kv_running_set |
| MIX-DEMAND D96 | 1,627 | 0.909 | 0.95 | 4.46 | 4.9 / 8.2 | 1,995 / 1,999 | 6,738 (323 / 10,431) | 61 | 0 / 30 | 0 / 0 | 0.00 / 0.98 | 0.24 | 27 (1.41 %) | kv_running_set |
| REP-EAGER D64 | 5,430 | 0.955 | 0.98 | 14.19 | 15.7 / 18.0 | 2,912 / 2,918 | 4,927 (319 / —) | 100 | 5 / 27 | 1 / 0.1 | 0.51 / 0.99 | 0.62 | 81 (1.33 %) | kv_running_set |
| REP-LAZYD D64 | 0 | 0.512 | 0.98 | 0.80 | 0.9 / 2.0 | 3,265 / 3,275 | 5,530 (5,530 / —) | 100 | 1 / 18 | 0 / 0 | 0.22 / 0.97 | — | 0 | kv_running_set |

GPU util medians of 0 in the ALL-LAZY cells are the 1-s sampler's median over a mostly idle window (escalations at 0.2–0.3 req/s); the cells are not idle during escalations.

**Host memory:** engine-core RSS peak 276–303 GiB (256 GiB offload buffer + processor cache + runtime), API RSS 3.6–17.8 GiB, MemAvailable ≥ 1,130 GiB in every cell.

**Errors:** over-context HTTP 400 (prompts > 32,768 tokens, one long session): escalations 4 per D64 cell (identical escalations in every policy; excluded from the denominator), appends 41–58 in cells where that session's device is eager (ALL-EAGER, MIX-DEMAND D64, MIX-RANDOM D96, REP-EAGER), and 2 ReadErrors on appends in ALL-EAGER D96. No escalation failed or was censored in any cell.

## Mechanism verification — fleet values

| causal link | fleet quantity | value | as expected? |
|---|---|---|---|
| demand heterogeneous | escalations hi / lo | 136 / 82 (D64), 170 / 97 (D96) — matches the plan (140 / 82, 170 / 97 scheduled, minus 4 over-context at D64) | yes |
| eager devices warm | computed tokens per escalation on eager devices | 319–329 (all eager cells) | yes |
| lazy devices recompute | same on lazy devices | 3,637–10,431 | yes |
| append load ∝ eager count | appends; host reload TB | 5,430 / 1,338–1,394 / 0 (D64); 13.5 / 3.4 / 0.2 TB | yes |
| demand matching | escalations on eager devices | MIX-DEMAND 136 / 218, 170 / 267 vs MIX-RANDOM 65 / 218, 70 / 267 | yes |
| host tier | whole-cell load bytes / external hit token | 262,171–264,335 B (pre-registered 262,144 ± 5 %) | verified in all 10 cells |

Step 4 outcome: the control (MIX-RANDOM) collapses onto ALL-LAZY at both D, so the D96 win is attributable to demand matching. Step 5: (a) excluded by Step 4; (b) the D64 repeat reproduces RH7 (5-s fraction 1.000 and 0.709 vs 0.704), so ALL-EAGER's D64 lead is not a shifted knee; (c) window-start burst: affects lazy escalations in every lazy/MIX cell alike and does not change the ordering; (d) over-context exclusions identical across policies.

**Trace (fleet, real records; the median non-fallback eager escalation of MIX-DEMAND D96).** High-demand device 36, session 2, escalation at 205 frames: body 0.62 MB (4 new frames + 201 uuid refs; full-bytes equivalent 30.2 MB), prompt 18,692 tokens, cached 18,128, computed 564; TTFT 0.391 s. The same escalation in ALL-LAZY (device lazy-delta): 125 frames not sent at the session's previous escalation (18.3 MB), prompt 18,691, cached 7,232 (the previous escalation's prefix still in GPU/host KV), computed 11,459; TTFT 3.219 s. Bound: recompute of the history the device had not sent since its last escalation. Note that a lazy high-demand device is *partly* warm through its own previous escalations (LAZY-DELTA + prefix cache), which narrows the gap at 15 s.

## Results consistency check

1. **Cross-check.** Repeats vs RH7 D64 — EAGER: median 1.18 vs 1.13 (1.05), p99 3.92 vs 2.98 (1.31), hit 0.9719 vs 0.9719, host TB 14.19 vs 14.2; LAZYD: median 2.86 vs 2.92 (0.98), p99 26.04 vs 26.35 (0.99), hit 0.512 vs 0.509. ALL-EAGER D96 at 40 % of RH7's escalations: collapse persists (median 131 vs 147 s; engine q 894 vs 1,090) — consistent with RH7's attribution to append service. All ratios within 2x. **AGREE.**
2. **Physical plausibility.** Achieved computed tok/s 1.5–3.3k (≤ RH7's 4.6k saturation / RH5's ~5k); PCIe ≤ 19.4 GB/s best 30 s (RH7 ≤ 20); warm escalation 320 computed tokens in 0.3–0.4 s median ≈ 1k tok/s plus scheduling — no rate faster than committed curves. **PASS.**
3. **Distribution sanity.** Spreads reported per cell and per group; no constant where a distribution is expected. The window-scoped load / hit-token ratio is exactly 262,144 in every cell (as in RH7) because loads are whole hit blocks — an identity; the pre-registered whole-cell check varies (262,171–264,335). **PASS.**
4. **Definition audit.** EAGER-DELTA, LAZY-DELTA, uuid refs, D2, window, drain cap, fallback, binding rule: identical to RH7 (imported code). New: per-device policy and demand subset (RH2's esc_subset convention; seed 0), and "fraction within T" (fixed before the fleet; over-context exclusion). "ALL-LAZY" here is LAZY-DELTA, not RH7's LAZY (full bytes). **PASS.**
5. **Claim linkage.** C4 / FORMULATION context inertia (warm state cost vs value) and the controller's placement action: supports the claim that warm-state allocation must be demand-aware past the eager knee and that per-device demand matters (D96); below the knee, uniform warmth dominates (D64). Does not speak to accuracy.
6. **Proxy validity.** TTFT with max_tokens 4 is the escalation latency proxy (as RH5–RH7). Demand is synthetic (fixed rates 1.0 / 0.2 on 25 % / 75 %), not a measured device-confidence trigger — the result says what a controller gains *if* it knows per-device demand; R9 / R4 address whether demand can be predicted. Stated as a limitation.

## H100 monitoring (this run)

`results/cost/h100_monitoring_summary.json` (StudyRH8, queue11): 2 windows (smoke, fleet), 1,156 monitor samples, SM clock busy median 1,170 MHz, 0 foreign processes on GPU 3, 0 watchdog lines.

## Deviations and notes

- After the smoke (before the fleet), the harness's STOP on host-hit verification was aligned with the pre-registration: it now stops only when a cell **with host hits** fails (the smoke had no host hits at D8/60 s and would otherwise have read as a failure). No fleet cell was affected (all had host hits and passed).
- Estimate basis: RH7's measured per-cell wall times (not a model); actual 3.23 h.

## Files

- `experiments/cost/study_rh8_demand_aware.py` (vLLM venv), `experiments/cost/study_rh8_analyse.py`
- `results/cost/study_rh8/`: `study_rh8_requests_h100nvl.jsonl.gz`, `study_rh8_metrics_h100nvl.jsonl.gz`, `study_rh8_cpu_h100nvl.jsonl.gz`, `study_rh8_run_meta_h100nvl.json`, `study_rh8_results_h100nvl.json`
- logs (not committed): `logs/queue11_*`
