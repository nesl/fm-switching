# StudyE6b-mobility — timely answers over a dropping network: rebuilt costs (Stage A) and when to keep a tier warm (Stage B)

**OFFLINE REPLAY OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no model server was started, and no inference was run. Every accuracy and every latency below is read from a committed result file of an earlier study.

**E-id:** `StudyE6b-mobility`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 **before any number in this report was computed** (user-authorized row). **Stage A** is §§1–17 below and is unchanged; **Stage B** is §§18–30, pre-registered separately on 2026-11-11 (later) once StudyE7-d2-4b and StudyE8-device-warm were committed.  
**Scripts:** `experiments/orchestration/study_e6b_traces.py`, `experiments/orchestration/study_e6b_mobility.py` (Stage A), `experiments/orchestration/study_e6b_stageb.py` (Stage B), `experiments/orchestration/study_e6b_report.py` (this file).  
**Results:** `results/orchestration/study_e6b/e6b_traces.npz`, `e6b_traces.json`, `e6b_results.json`, `e6b_mechanism_verification.md`, `e6b_stageb_results.json`, `e6b_stageb_mechanism_verification.md`.  
**Never used:** any result marked INVALID — E24/E24b/E24c, E31 Parts C and D, I2/I3 TEMPORAL/SPATIAL, D/D2 Thinking, K/J Thinking T0.6. Reachability comes from E31b's corrected `cell_id == -1` signal, never from E31 Part C's `State=D/I`.

## Prominent flags (read first)

1. **The deployment mode, not the policy, is the biggest single term in every timely-utility number StudyE4 and StudyE6(b) reported.** At 13.6 Mbit/s PNG, 5 s deadline, outdoor-driving, the oracle over twelve configurations is 0.5816 under STREAM and 0.2626 under ON-DEMAND, and the best static configuration is 0.3385 (cl-32B-RICH) against 0.1538 (dev-4B-SHORT-N1). StudyE4 charged one session both ways at once.
2. **StudyE6's own Part 0 fixed only half of error 1.** It moved the cloud-held arms to the session rule but left RECENT on a full per-question upload, so it is still a mixed mode. At 13.6 Mbit/s PNG 5 s the headroom over per-type is 0.0036 as StudyE4 reported it, 0.0793 after StudyE6 Part 0, and **0.1964 (STREAM) or 0.0012 (ON-DEMAND)** once one mode is applied to every cloud arm. Neither published number equals either self-consistent regime.
3. **The decomposed policy P1 beats the best static configuration at the 5 s and 10 s deadlines and collapses at 2 s.** Outdoor-driving at 13.6 Mbit/s: P1 − static is +0.0285 [+0.014, +0.043] at 5 s but -0.2349 [-0.270, -0.200] at 2 s. StudyE6 setting (a)'s rule maximises accuracy and knows nothing about deadlines, so it keeps choosing 32B cells that cannot be delivered in 2 s.
4. **P1's advantage is made almost entirely of the questions that arrive during an outage, not of the evidence rule.** On connected questions P1 scores 0.4018 against static's 0.3932; on outage questions 0.1520 against 0.0000 — the static cloud configuration scores exactly zero whenever the link is down, and P1 falls back to the device.
5. **That fallback is worth very little, because every device option is either near chance or undeliverable.** The device short windows score 0.1538 / 0.1373 / 0.1515 at N = 1/3/9, all at or below the 0.20 chance floor (StudyF1, StudyF4), and device RECENT 120 s costs about 17 s on the Orin, so it is delivered on 0.0012 of questions at a 5 s deadline.
6. **Irish outages are too short for the queue to matter; what matters is whether the link is up at the question instant.** Outage runs are p50 1 s, p95 2 s, max 3 s, so at 13.6 Mbit/s the backlog they leave clears in well under a second. The exception is arm U at 5 Mbit/s, where the offered stream rate is close to the link and 5.1 % of questions never get their backlog cleared.
7. **Stage A carries no keep-warm conclusion.** The device-warm link is ABSENT until StudyE7 and StudyE8 are committed, so per CLAUDE.md the keep-warm sweep (P2, P3, P3-noncausal, oracle keep-warm, negative control (b), the decision rule) is **not run**, and nothing here is offered as evidence for or against keeping a tier warm.
8. **Oracle caution.** The oracle picks the best of twelve single-draw greedy configurations per question. StudyE6 measured the near-identical-arm disagreement floor at 0.59 % (32B) and 1.47 % (4B) — about 0.15–0.44 pp of oracle headroom. The oracle margins here (0.2146 over P1 at 13.6 Mbit/s 5 s) are far above that floor, but the twelve-arm selection effect is larger than StudyE6's four-arm one and is not quantified.

## 1. The three costing errors, and what was done about them

| # | error | where it was | what it did | fix used here |
|---|---|---|---|---|
| 1 | mixed deployment modes | StudyE4 Part 1 and session analysis; StudyE6 setting (b) and Part 0 | RECENT paid a full on-demand upload every question while cloud-held history arms were charged as streamed, so the same session was billed two ways | one mode — STREAM or ON-DEMAND — applied to **all** cloud arms, never mixed; both reported |
| 2 | 4B cold curve stopped at 12,501 tokens | StudyE4, StudyE6 setting (b) | built from image-format device runs only, so 4B-RICH (p50 12,597 tokens) was UNKNOWN, i.e. unavailable, on 471 of 845 questions | StudyF3 `4BI/video/COLD`, token range 1,810–22,387; **0 of 845** cloud 4B RECENT or RICH questions are now UNKNOWN |
| 3 | 32B cold curve pooled formats | StudyE4, StudyE6 setting (b) | image-format and video-format runs were binned together in 100-token bins, so K3 got image pricing and K1 video pricing, with ≈0.8 s between the formats at equal tokens (StudyF3 §4) | StudyF3's separate `32BI/video/COLD`, `32BI/images/COLD` and `32BI/images/WARM` curves |

Dated correction blocks stating all three, and the reclassification below, have been prepended to `reports/study_e6_intervention.md` and `reports/study_e4_counterfactual.md`. **Their bodies are unchanged.**

**StudyE6's Rule 2 classification for the joint claim is withdrawn.** StudyE6 §13 called the combined-vs-independent null a REAL NEGATIVE. That rested partly on setting (b), which is built on these three costs; error 2 alone made 4B-RICH unavailable on 56 % of questions, removing one of the four arms the policy was meant to choose between. Under CLAUDE.md Rule 2 the joint claim is **INCONCLUSIVE (mechanism absent)**. **StudyE6 setting (a) — accuracy only, both models in the cloud, always reachable — stands exactly as reported**, including its own negative result, which uses no delivery cost.

## 2. Configurations, and what each comparison can identify

| configuration | model | location | representation | cache | accuracy source | latency source | accuracy if always delivered | n available |
|---|---|---|---|---|---|---|---|---|
| `cl-4B-RECENT` | 4B | cloud | RECENT | cold | StudyClean H1 | StudyF3 4BI/video/COLD | 0.3254 | 845 |
| `cl-4B-RICH` | 4B | cloud | RICH | cold | StudyClean H2 | StudyF3 4BI/video/COLD | 0.3018 | 845 |
| `cl-4B-U` | 4B | cloud | U | cold | StudyD11 arm U 4BI | StudyF3 4BI/video/COLD | 0.3361 | 845 |
| `cl-32B-RECENT` | 32B | cloud | RECENT | cold | StudyR1 K3 | StudyF3 32BI/video/COLD | 0.3834 | 845 |
| `cl-32B-RICH` | 32B | cloud | RICH | cold | StudyR1 K1 | StudyF3 32BI/video/COLD | 0.3953 | 845 |
| `cl-32B-U` | 32B | cloud | U | cold | StudyD11 arm U 32BI | StudyF3 32BI/video/COLD | 0.4142 | 845 |
| `cl-32B-D2-cold` | 32B | cloud | D2 | cold | StudyRH4 D2 | StudyF3 32BI/images/COLD | 0.3957 | 839 |
| `cl-32B-D2-warm` | 32B | cloud | D2 | **warm** | StudyRH4 D2 | StudyF3 32BI/images/WARM vs uncached tokens | 0.3736 | 605 |
| `dev-4B-SHORT-N1` | 4B | device Orin | last-3 s N=1 | cold | StudyF4 Part A N=1 | StudyF4 Part B p50 | 0.1538 | 845 |
| `dev-4B-SHORT-N3` | 4B | device Orin | last-3 s N=3 | cold | StudyF4 Part A N=3 | StudyF4 Part B p50 | 0.1373 | 845 |
| `dev-4B-SHORT-N9` | 4B | device Orin | last-3 s N=9 | cold | StudyF4 Part A N=9 | StudyF4 Part B p50 | 0.1515 | 845 |
| `dev-4B-RECENT` | 4B | device Orin | RECENT 120 s | cold | StudyClean H1 **as proxy (FLAG)** | StudyD4-orin / DevFast cold | 0.3254 | 845 |

**Match statements (CLAUDE.md: every comparison states whether input, stack and decoding match).**

- `cl-4B-RECENT` vs `cl-32B-RECENT`, and `cl-4B-RICH` vs `cl-32B-RICH`: **input identical**, stack identical (H100 vLLM 0.31.0), decoding identical (greedy, Instruct). Ledger class `IDENTICAL_INPUT`. These isolate capability.
- `*-RECENT` vs `*-RICH`: same model, same stack, same decoding; **input differs** — window, frame count and resolution all move together. Ledger class `REALLOCATED_BUDGET`; this is not history length alone.
- `cl-32B-D2-*` vs `cl-32B-RICH`: same model, stack and decoding; different construction and **different format** (separate images vs one video), which StudyF3 §4 measures at ≈0.8 s at equal token count. `REALLOCATED_BUDGET` + `FORMAT_DIFFERENT`.
- `cl-32B-D2-cold` vs `cl-32B-D2-warm`: identical input and identical answers; **only the cache state differs**, and the two are never pooled. Caching is stated as a methodological parameter: cold = prefix caching off (`cached_tokens = 0` on all 686 StudyF3 cold rows); warm = vLLM prefix cache holding the session's earlier D2 prefix, priced on StudyF3's *uncached-token* curve.
- device vs cloud 4B: **different stack** (llama.cpp F16 on Orin vs vLLM on H100) with the same decoding. StudyF4 measured 97.2 / 97.2 / 98.1 % per-question letter agreement on byte-identical frames, so the accuracy comparison is `IDENTICAL_INPUT` with a ~2–3 % stack-noise residual.
- `dev-4B-RECENT` accuracy is **a proxy**: StudyClean H1's cloud letters stand in for an Orin run that does not exist. StudyF4 justifies the substitution at the short windows; it has **not** been measured at 120 s on the device. Flagged, and it changes nothing here because the configuration is undeliverable at every deadline tested.

**PENDING — listed, never estimated.** These configurations are part of the pre-registered design and are left out of every table until the studies that measure them are committed:

| configuration | needs |
|---|---|
| `cl-4B-D2-cold` | StudyE7 (4B D2 letters) |
| `cl-4B-D2-warm` | StudyE7 (4B D2 letters) |
| `dev-4B-D2-warm` | StudyE7 letters + StudyE8 Part D parity, Part B warm-up curve |
| `dev-4B-D2-cold` | StudyE7 letters + StudyE8 Part D parity |
| `device keep-warm energy` | StudyE8 Parts A and C |

## 3. The rebuilt cost model

### 3.1 Latency: per-format, per-cache-state curves (StudyF3), UNKNOWN outside the measured range

| configuration | status counts |
|---|---|
| `cl-4B-RECENT` | measured 845 |
| `cl-4B-RICH` | measured 845 |
| `cl-4B-U` | UNKNOWN 25, measured 820 |
| `cl-32B-RECENT` | measured 845 |
| `cl-32B-RICH` | measured 845 |
| `cl-32B-U` | UNKNOWN 25, measured 820 |
| `cl-32B-D2-cold` | INFEASIBLE 6, measured 839 |
| `cl-32B-D2-warm` | COLD_FIRST_QUESTION 234, INFEASIBLE 6, UNKNOWN 24, measured 581 |
| `dev-4B-SHORT-N1` | measured 845 |
| `dev-4B-SHORT-N3` | measured 845 |
| `dev-4B-SHORT-N9` | measured 845 |
| `dev-4B-RECENT` | UNKNOWN 125, measured 720 |

`UNKNOWN` = the prompt falls outside the curve's measured token range; the primary analysis treats it as unavailable. `INFEASIBLE` = no committed answer for that question (the six D2 questions that exceeded the context limit). `COLD_FIRST_QUESTION` = the first question of a video, where no warm cloud session exists yet; those questions are served by `cl-32B-D2-cold`.

### 3.2 Upload: what each deployment mode charges

| representation | STREAM rate (B/s) | STREAM uplink MB/hour | ON-DEMAND bytes per question, p50 (MB) | ON-DEMAND max (MB) |
|---|---|---|---|---|
| RECENT | 276,307 | 994.7 | 34.26 | 34.47 |
| RICH | 139,845 | 503.4 | 35.70 | 36.79 |
| U | 416,152 | 1,498.1 | 50.76 | 66.28 |
| D2 | 69,922 | 251.7 | 16.22 | 80.83 |

PNG, median frame sizes from StudyE4's `e4_frame_bytes.json`. Stream rates are the arm's own frame rate at the arm's resolution: RECENT and U at 1 fps 512×384, RICH at 1 fps 352×256, D2 at 0.5 fps 352×256. **Stated assumption (StudyRH3, as StudyE6 Part 0):** RICH re-samples frames at each question, so a cloud holding all frames at 1 fps can build the RICH input without a fresh upload; the STREAM charge is the marginal cost of keeping that store current. Under STREAM the pending payload at a question is the queue backlog **plus the newest frame**, which is the frame captured at the question instant and not yet sent. The MB/hour figure is charged for the whole session, including hours in which no question arrives.

### 3.3 Upload delay actually incurred (13.6 Mbit/s, STREAM, outdoor-driving)

| representation | pending > 1 frame | upload s p50 | p95 | max | never uploaded | (5 Mbit/s) p95 | (5 Mbit/s) never uploaded |
|---|---|---|---|---|---|---|---|
| RECENT | 14.0 % | 0.163 | 0.325 | 0.488 | 0.0 % | 0.884 | 0.3 % |
| RICH | 14.0 % | 0.082 | 0.165 | 0.247 | 0.0 % | 0.448 | 0.0 % |
| U | 14.0 % | 0.163 | 0.407 | 0.652 | 0.0 % | 1.108 | 5.1 % |
| D2 | 14.0 % | 0.082 | 0.123 | 0.165 | 0.0 % | 0.336 | 0.0 % |

## 4. Network regimes

| regime | signal | sessions | total s | outage fraction | outage runs | run s p50 / p95 / max |
|---|---|---|---|---|---|---|
| `outdoor_driving` | Irish 5G cell_id == -1 (E31b corrected signal | 16 | 28,551 | 0.1438 | 3,829 | 1 / 2 / 3 |
| `indoor` | herolab C_level_a median per second < -75.0 dBm | 7 | 3,496 | 0.0074 | 1 | 26 / 26 / 26 |
| `synthetic_0pct` | SYNTHETIC two-state | 16 | 57,600 | 0.0000 | 0 | 0 / 0 / 0 |
| `synthetic_2pct` | SYNTHETIC two-state | 16 | 57,600 | 0.0197 | 1,068 | 1 / 2 / 3 |
| `synthetic_5pct` | SYNTHETIC two-state | 16 | 57,600 | 0.0494 | 2,637 | 1 / 2 / 3 |
| `synthetic_10pct` | SYNTHETIC two-state | 16 | 57,600 | 0.1013 | 5,432 | 1 / 2 / 3 |
| `synthetic_20pct` | SYNTHETIC two-state | 16 | 57,600 | 0.2012 | 10,819 | 1 / 2 / 3 |
| `synthetic_30pct` | SYNTHETIC two-state | 16 | 57,600 | 0.2998 | 16,054 | 1 / 2 / 3 |

- **outdoor-driving** reproduces E31b exactly: 14.38 % no-cell time in 3,829 runs of 1–3 s across 16 sessions and 28,551 s. Signal is `cell_id == -1`; `State=D/I` (E31 Part C, INVALID) is never used.
- **indoor** *is* available as a per-sample time series, so it is not skipped: the herolab datalogs carry `temp_sec` and `C_level_a`, and a second is an outage when the median RSSI in it is below −75 dBm. It yields **one** outage run of 26 s in 3,496 s. Two caveats: the seven sessions are 76, 76, 316, 344, 546, 650, 1488 s long, so only the longest can host the longest videos and the alignment is concentrated; and 27 seconds carry no sample at all and are treated as connected.
- **synthetic** is labelled synthetic throughout: a two-state process whose outage runs are resampled from the Irish empirical gap-duration distribution, with connected runs geometric at the mean that produces the target outage fraction. It therefore inherits Irish's short gaps; it varies *how often* the link drops, not *for how long*.

**Uplink is fixed at 5, 13.6 and 88 Mbit/s with RTT 60, 44 and 22 ms. Uplink variation is NOT modelled**, and the Irish traces are *download* traces — they are used here only for the reachability signal, never for a rate. Alignment: each video is mapped to a random window of a trace session long enough to hold it, 20 offsets per video (seeds 0–19), with questions replayed in time order within the video.

| regime | (video, offset) pairs | unmappable | videos never mappable |
|---|---|---|---|
| `outdoor_driving` | 4,680 | 0 | 0 |
| `indoor` | 4,680 | 0 | 0 |
| `synthetic_0pct` | 4,680 | 0 | 0 |
| `synthetic_2pct` | 4,680 | 0 | 0 |
| `synthetic_5pct` | 4,680 | 0 | 0 |
| `synthetic_10pct` | 4,680 | 0 | 0 |
| `synthetic_20pct` | 4,680 | 0 | 0 |
| `synthetic_30pct` | 4,680 | 0 | 0 |

## 5. Mechanism verification (CLAUDE.md Steps 1–5)

Recorded in `results/orchestration/study_e6b/e6b_mechanism_verification.md` **before the Stage A sweep ran**, and reproduced here in full.

> # StudyE6b-mobility — mechanism verification (CLAUDE.md Steps 1–5)
>
> **Recorded 2026-11-11, BEFORE the Stage A sweep ran.** The quantities below come from two
> single-regime probe runs (`indoor`, `outdoor_driving`, `synthetic_0pct`) made to instantiate the
> links, not from the sweep. Offline replay of committed results; CPU only; no GPU, no server, no
> inference.
>
> ## Step 1 — the causal chain (Stage A)
>
> If a mobile device must send evidence to a cloud model before that model can answer
> (FORMULATION §Constraints 2, *serving feasibility*: the serving node must hold an object fresh
> enough to serve within the latency SLO, or pay materialization first), and transfers are possible
> only while the device is attached to the network (§Constraints 3, *reachability*: transfers only
> along edges of G_i(t) at B(t)), then **how** the evidence is shipped decides what can be answered
> in time. Under ON-DEMAND the whole input is sent at question time, so the delivered latency is
> dominated by payload size. Under STREAM the device ships frames continuously, so at question time
> only the newest frame plus whatever an outage queued is pending — but an outage both (i) makes the
> cloud unanswerable at that instant and (ii) leaves a backlog that must clear before a later
> question is served, which is FORMULATION's §Objective statement that *handoff latency on a mobility
> event is the binding term*. Therefore: **outage seconds → queued bytes → upload delay at the next
> question → deadline missed → the cloud configuration scores zero, and only a device configuration
> can answer**; and because the two deployment modes charge the same session differently, the mode
> must be fixed for all cloud arms, which is exactly the error StudyE4 and StudyE6 setting (b) made.
>
> Stage A tests this chain and nothing else. It does **not** test the keep-warm claim; that chain
> needs the device-warm link, which is ABSENT until StudyE7 and StudyE8 are committed (see Step 2),
> and therefore no Stage A result is reported as evidence for or against keeping a tier warm.
>
> ## Step 2 — instantiate each link
>
> | causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
> |---|---|---|---|---|
> | the network drops out | outage fraction per regime | outdoor-driving **0.1438**; indoor **0.0074**; synthetic 0.0000 / 0.0197 / 0.0494 / 0.1013 / 0.2012 / 0.2998 | yes, by construction and by trace | `e6b_traces.json` |
> | outages have duration | outage run length | Irish p50 1 s, p95 2 s, max 3 s (3,829 runs); indoor one run of 26 s | yes | `e6b_traces.json` |
> | outage → queued bytes | pending bytes at question time vs one frame | fraction of questions with pending > 1 frame = **0.14** at 13.6 Mbit/s (= the outage fraction); RECENT pending p50 276,307 B, p95 552,614 B, max 828,921 B | yes, and only during/after outages | `cells[*].upload_diagnostics` |
> | queued bytes → upload delay | upload seconds at question time | RECENT p50 **0.025 / 0.163 / 0.442 s** at 88 / 13.6 / 5 Mbit/s; U p95 **0.063 / 0.407 / 1.108 s**; U never-uploaded **5.1 %** at 5 Mbit/s | yes, scales with uplink and with arm rate | same |
> | upload delay + compute → deadline met or missed | delivered total vs deadline | per-configuration utility moves from 0.395 (32B RICH, 13.6 Mbit/s STREAM, 5 s) to 0.005 (same arm, 5 Mbit/s, 2 s) | yes | `cells[*].per_config` |
> | unreachable at question time → only the device can answer | reachable fraction; P1 device-fallback fraction | reachable 0.861 (outdoor), 0.9938 (indoor), 1.0 (synthetic 0 %); fallback fraction equals 1 − reachable | yes | `cells[*]` |
> | the device fallback has value | device configuration accuracy | short windows **0.1538 / 0.1373 / 0.1515** (N = 1/3/9, StudyF4), all at or below the 0.20 chance floor; device RECENT 120 s cold = 0.3254 accuracy but ~17 s latency, delivered on **0.1 %** of questions at a 10 s deadline | **WEAK, and reported as such** — present and non-zero, but every device option is either near chance or undeliverable | StudyF4, StudyD4-orin/DevFast curve |
> | **device-warm history changes the fallback's value** | device D2 warm accuracy and warm/cold latency | **ABSENT** — needs StudyE7 (4B D2 letters) and StudyE8 (Part D parity, Part B warm-up curve, Parts A/C energy) | — | not committed |
>
> **No ABSENT link is on Stage A's chain.** The one ABSENT entry is the Stage B link, and it is the
> reason Stage B is not run here: per CLAUDE.md, the keep-warm sweep does not proceed until StudyE7
> and StudyE8 exist. The "device fallback has value" link is present but weak; it is flagged in the
> report and no Stage A conclusion depends on the fallback being good.
>
> ## Step 3 — trace one unit
>
> The runner writes one instrumented video-through-an-outage trace to
> `e6b_results.json → trace_example`: for every question of one (video, trace offset) pair it records
> the question time, the trace second, whether the link was up, the outage seconds in the preceding
> 60 s, and then per configuration the queue backlog in bytes, the newest-frame charge, total pending
> bytes, upload seconds, RTT, compute seconds, total seconds, whether it met the deadline, the
> committed correctness, and the resulting utility — plus the arm stream rates and the uplink MB per
> hour. The arithmetic is checkable by hand from those columns.
>
> ## Step 4 — negative control
>
> **Control (a), pre-registered:** set the outage fraction to 0 (`synthetic_0pct`). P1 must never
> fall back to the device, so its device-fallback fraction must be 0 and its utility must equal the
> always-cloud decomposed policy's. Probe outcome: reachable fraction **1.0**, device-fallback
> fraction **0.0**, P1 = **0.40355** at the 5 s and 10 s deadlines — identical to StudyE6 setting
> (a)'s evidence-only F1 accuracy (0.4036), which is the correct always-cloud value. **PASS.**
>
> A second control falls out of the design: at 88 Mbit/s the upload term is ~0.025 s, so utility must
> be set by compute and correctness alone; it is, and the per-configuration utilities there equal the
> committed accuracies of the arms that fit the deadline.
>
> Control (b) (device-warm accuracy set to device short-window accuracy) belongs to Stage B and is
> not run, because the quantity it would disable does not exist yet.
>
> ## Step 5 — alternative explanations
>
> 1. **"Cloud arms lose because of outages" vs "cloud arms lose because of compute."** Both predict
>    low utility at a short deadline. They are separated by the 88 Mbit/s column, where upload is
>    0.025 s: anything that still fails there fails on compute (32B video ≈ 3.7–3.8 s, 32B U ≈ 5.3 s,
>    device RECENT ≈ 17 s). The report attributes losses with that column and with the
>    connected-vs-outage utility split, not by assertion.
> 2. **"P1 beats static because placement helps" vs "P1 beats static because StudyE6's evidence rule
>    picks a better cell."** Separated by the outage-fraction-0 control: there P1 carries no placement
>    decision at all, so any P1 − static difference there is the evidence rule alone, and the
>    placement contribution is the change in that difference as the outage fraction rises.
> 3. **"The mode correction changes the answer" vs "the curve correction changes the answer."** The
>    two corrections are applied and reported separately: the E4 table 4.1 recompute is given under
>    both deployment modes with the same corrected curves, so the mode term and the curve term can be
>    read off independently.
> 4. **Alignment artefact.** A video mapped to an unusually bad or good stretch of trace could drive
>    a difference. Twenty offsets per video with a video-and-offset bootstrap is the control; the
>    indoor regime additionally reports how few sessions are long enough to host a video, because
>    there the alignment is concentrated.

## 6. Stage A results — static, P1 and the oracle, all regimes (STREAM, PNG)

P1 is the decomposed / no-pre-warm policy: model and evidence from StudyE6 setting (a)'s best rule (evidence-only, F1, logistic regression, 5-fold cross-fit by video, seed 0, unconstrained budget (StudyE6 setting (a)'s best realised policy, 0.4036)), the cloud over STREAM while connected, and the best no-pre-warm device configuration when the cloud is unreachable. The device configuration and the best static configuration are both chosen on training offsets (5 folds over the 20 trace offsets, seed 0); every number reported is from held-out offsets. The StudyE6 rule chose K3 on 253 questions and K1 on 592; the best static StudyE6 cell was K1 in all five folds.

**Uplink 5 Mbit/s, RTT 60 ms**

| regime | deadline | reachable | oracle | best static | (pick) | P1 | P1 − static [95 % CI] | oracle − P1 [95 % CI] | device fallback |
|---|---|---|---|---|---|---|---|---|---|
| `outdoor_driving` | 1 s | 0.861 | 0.1827 | 0.1538 | dev-4B-SHORT-N1 | 0.0227 | -0.1312 [-0.155, -0.110] | 0.1600 [+0.136, +0.185] | 0.139 |
| `outdoor_driving` | 2 s | 0.861 | 0.4463 | 0.2167 | cl-4B-RICH | 0.0248 | -0.1920 [-0.222, -0.160] | 0.4215 [+0.386, +0.456] | 0.139 |
| `outdoor_driving` | 5 s | 0.861 | 0.5815 | 0.3385 | cl-32B-RICH | 0.3664 | 0.0279 [+0.013, +0.043] | 0.2151 [+0.189, +0.241] | 0.139 |
| `outdoor_driving` | 10 s | 0.861 | 0.5858 | 0.3385 | cl-32B-RICH | 0.3666 | 0.0281 [+0.013, +0.043] | 0.2192 [+0.193, +0.244] | 0.139 |
| `indoor` | 1 s | 0.994 | 0.1891 | 0.1538 | dev-4B-SHORT-N1 | 0.0033 | -0.1506 [-0.175, -0.128] | 0.1858 [+0.160, +0.213] | 0.006 |
| `indoor` | 2 s | 0.994 | 0.5005 | 0.2896 | cl-4B-RICH | 0.0056 | -0.2840 [-0.317, -0.251] | 0.4949 [+0.459, +0.531] | 0.006 |
| `indoor` | 5 s | 0.994 | 0.6409 | 0.3919 | cl-32B-RICH | 0.4011 | 0.0092 [-0.004, +0.022] | 0.2399 [+0.214, +0.267] | 0.006 |
| `indoor` | 10 s | 0.994 | 0.6457 | 0.3983 | cl-32B-U | 0.4017 | 0.0034 [-0.017, +0.022] | 0.2440 [+0.218, +0.270] | 0.006 |
| `synthetic_0pct` | 1 s | 1.000 | 0.1893 | 0.1538 | dev-4B-SHORT-N1 | 0.0024 | -0.1515 [-0.176, -0.129] | 0.1870 [+0.161, +0.214] | 0.000 |
| `synthetic_0pct` | 2 s | 1.000 | 0.5030 | 0.2923 | cl-4B-RICH | 0.0047 | -0.2876 [-0.321, -0.254] | 0.4982 [+0.462, +0.533] | 0.000 |
| `synthetic_0pct` | 5 s | 1.000 | 0.6438 | 0.3953 | cl-32B-RICH | 0.4036 | 0.0083 [-0.005, +0.021] | 0.2402 [+0.214, +0.268] | 0.000 |
| `synthetic_0pct` | 10 s | 1.000 | 0.6485 | 0.4047 | cl-32B-U | 0.4036 | -0.0012 [-0.021, +0.017] | 0.2450 [+0.219, +0.272] | 0.000 |
| `synthetic_2pct` | 1 s | 0.980 | 0.1885 | 0.1538 | dev-4B-SHORT-N1 | 0.0049 | -0.1489 [-0.173, -0.126] | 0.1836 [+0.159, +0.211] | 0.020 |
| `synthetic_2pct` | 2 s | 0.980 | 0.4952 | 0.2817 | cl-4B-RICH | 0.0073 | -0.2744 [-0.309, -0.242] | 0.4879 [+0.453, +0.524] | 0.020 |
| `synthetic_2pct` | 5 s | 0.980 | 0.6348 | 0.3872 | cl-32B-RICH | 0.3979 | 0.0107 [-0.002, +0.024] | 0.2369 [+0.211, +0.264] | 0.020 |
| `synthetic_2pct` | 10 s | 0.980 | 0.6395 | 0.3940 | cl-32B-U | 0.3980 | 0.0040 [-0.015, +0.022] | 0.2415 [+0.215, +0.268] | 0.020 |
| `synthetic_5pct` | 1 s | 0.952 | 0.1870 | 0.1538 | dev-4B-SHORT-N1 | 0.0092 | -0.1447 [-0.168, -0.122] | 0.1779 [+0.153, +0.204] | 0.048 |
| `synthetic_5pct` | 2 s | 0.952 | 0.4834 | 0.2639 | cl-4B-RICH | 0.0114 | -0.2525 [-0.285, -0.220] | 0.4720 [+0.436, +0.506] | 0.048 |
| `synthetic_5pct` | 5 s | 0.952 | 0.6239 | 0.3758 | cl-32B-RICH | 0.3907 | 0.0149 [+0.001, +0.029] | 0.2333 [+0.208, +0.261] | 0.048 |
| `synthetic_5pct` | 10 s | 0.952 | 0.6282 | 0.3802 | cl-32B-U | 0.3908 | 0.0106 [-0.009, +0.030] | 0.2375 [+0.211, +0.264] | 0.048 |
| `synthetic_10pct` | 1 s | 0.897 | 0.1844 | 0.1538 | dev-4B-SHORT-N1 | 0.0173 | -0.1366 [-0.160, -0.114] | 0.1671 [+0.142, +0.192] | 0.103 |
| `synthetic_10pct` | 2 s | 0.897 | 0.4599 | 0.2341 | cl-4B-RICH | 0.0193 | -0.2148 [-0.249, -0.184] | 0.4405 [+0.404, +0.476] | 0.103 |
| `synthetic_10pct` | 5 s | 0.897 | 0.5982 | 0.3537 | cl-32B-RICH | 0.3747 | 0.0210 [+0.007, +0.037] | 0.2236 [+0.198, +0.249] | 0.103 |
| `synthetic_10pct` | 10 s | 0.897 | 0.6027 | 0.3537 | cl-32B-RICH | 0.3749 | 0.0212 [+0.007, +0.037] | 0.2278 [+0.202, +0.253] | 0.103 |
| `synthetic_20pct` | 1 s | 0.799 | 0.1799 | 0.1538 | dev-4B-SHORT-N1 | 0.0308 | -0.1231 [-0.146, -0.102] | 0.1492 [+0.126, +0.175] | 0.201 |
| `synthetic_20pct` | 2 s | 0.799 | 0.4218 | 0.1826 | cl-4B-RICH | 0.0324 | -0.1502 [-0.182, -0.121] | 0.3893 [+0.357, +0.424] | 0.201 |
| `synthetic_20pct` | 5 s | 0.799 | 0.5573 | 0.3145 | cl-32B-RICH | 0.3483 | 0.0338 [+0.018, +0.050] | 0.2090 [+0.184, +0.235] | 0.201 |
| `synthetic_20pct` | 10 s | 0.799 | 0.5609 | 0.3140 | cl-32B-RICH | 0.3491 | 0.0350 [+0.016, +0.052] | 0.2119 [+0.187, +0.237] | 0.201 |
| `synthetic_30pct` | 1 s | 0.705 | 0.1753 | 0.1538 | dev-4B-SHORT-N1 | 0.0464 | -0.1075 [-0.129, -0.087] | 0.1289 [+0.107, +0.152] | 0.295 |
| `synthetic_30pct` | 2 s | 0.705 | 0.3834 | 0.1538 | dev-4B-SHORT-N1 | 0.0479 | -0.1059 [-0.128, -0.085] | 0.3354 [+0.303, +0.368] | 0.295 |
| `synthetic_30pct` | 5 s | 0.705 | 0.5196 | 0.2799 | cl-32B-RICH | 0.3275 | 0.0475 [+0.030, +0.067] | 0.1922 [+0.169, +0.218] | 0.295 |
| `synthetic_30pct` | 10 s | 0.705 | 0.5230 | 0.2799 | cl-32B-RICH | 0.3293 | 0.0494 [+0.032, +0.069] | 0.1937 [+0.170, +0.220] | 0.295 |

**Uplink 13.6 Mbit/s, RTT 44 ms**

| regime | deadline | reachable | oracle | best static | (pick) | P1 | P1 − static [95 % CI] | oracle − P1 [95 % CI] | device fallback |
|---|---|---|---|---|---|---|---|---|---|
| `outdoor_driving` | 1 s | 0.861 | 0.1992 | 0.1538 | dev-4B-SHORT-N1 | 0.0230 | -0.1308 [-0.155, -0.109] | 0.1762 [+0.150, +0.203] | 0.139 |
| `outdoor_driving` | 2 s | 0.861 | 0.5018 | 0.2599 | cl-4B-RICH | 0.0251 | -0.2349 [-0.270, -0.200] | 0.4767 [+0.440, +0.511] | 0.139 |
| `outdoor_driving` | 5 s | 0.861 | 0.5816 | 0.3385 | cl-32B-RICH | 0.3670 | 0.0285 [+0.014, +0.043] | 0.2146 [+0.189, +0.241] | 0.139 |
| `outdoor_driving` | 10 s | 0.861 | 0.5865 | 0.3467 | cl-32B-U | 0.3670 | 0.0203 [+0.000, +0.039] | 0.2195 [+0.194, +0.245] | 0.139 |
| `indoor` | 1 s | 0.994 | 0.2068 | 0.1538 | dev-4B-SHORT-N1 | 0.0033 | -0.1505 [-0.175, -0.128] | 0.2035 [+0.177, +0.232] | 0.006 |
| `indoor` | 2 s | 0.994 | 0.5585 | 0.3233 | cl-4B-RECENT | 0.0057 | -0.3176 [-0.350, -0.285] | 0.5528 [+0.519, +0.586] | 0.006 |
| `indoor` | 5 s | 0.994 | 0.6411 | 0.3926 | cl-32B-RICH | 0.4020 | 0.0093 [-0.004, +0.023] | 0.2391 [+0.214, +0.266] | 0.006 |
| `indoor` | 10 s | 0.994 | 0.6459 | 0.4021 | cl-32B-U | 0.4022 | 0.0001 [-0.020, +0.019] | 0.2437 [+0.218, +0.270] | 0.006 |
| `synthetic_0pct` | 1 s | 1.000 | 0.2071 | 0.1538 | dev-4B-SHORT-N1 | 0.0024 | -0.1515 [-0.176, -0.129] | 0.2047 [+0.177, +0.233] | 0.000 |
| `synthetic_0pct` | 2 s | 1.000 | 0.5609 | 0.3254 | cl-4B-RECENT | 0.0047 | -0.3207 [-0.353, -0.289] | 0.5562 [+0.522, +0.589] | 0.000 |
| `synthetic_0pct` | 5 s | 1.000 | 0.6438 | 0.3953 | cl-32B-RICH | 0.4036 | 0.0083 [-0.005, +0.021] | 0.2402 [+0.214, +0.268] | 0.000 |
| `synthetic_0pct` | 10 s | 1.000 | 0.6485 | 0.4047 | cl-32B-U | 0.4036 | -0.0012 [-0.021, +0.017] | 0.2450 [+0.219, +0.272] | 0.000 |
| `synthetic_2pct` | 1 s | 0.980 | 0.2061 | 0.1538 | dev-4B-SHORT-N1 | 0.0050 | -0.1489 [-0.173, -0.126] | 0.2011 [+0.174, +0.229] | 0.020 |
| `synthetic_2pct` | 2 s | 0.980 | 0.5522 | 0.3144 | cl-4B-RECENT | 0.0073 | -0.3070 [-0.340, -0.276] | 0.5449 [+0.511, +0.579] | 0.020 |
| `synthetic_2pct` | 5 s | 0.980 | 0.6349 | 0.3872 | cl-32B-RICH | 0.3981 | 0.0109 [-0.002, +0.025] | 0.2368 [+0.211, +0.264] | 0.020 |
| `synthetic_2pct` | 10 s | 0.980 | 0.6396 | 0.3958 | cl-32B-U | 0.3981 | 0.0023 [-0.017, +0.021] | 0.2415 [+0.216, +0.268] | 0.020 |
| `synthetic_5pct` | 1 s | 0.952 | 0.2043 | 0.1538 | dev-4B-SHORT-N1 | 0.0092 | -0.1446 [-0.168, -0.122] | 0.1950 [+0.169, +0.222] | 0.048 |
| `synthetic_5pct` | 2 s | 0.952 | 0.5422 | 0.2974 | cl-4B-RECENT | 0.0114 | -0.2860 [-0.320, -0.255] | 0.5309 [+0.496, +0.564] | 0.048 |
| `synthetic_5pct` | 5 s | 0.952 | 0.6240 | 0.3758 | cl-32B-RICH | 0.3909 | 0.0151 [+0.002, +0.029] | 0.2331 [+0.208, +0.260] | 0.048 |
| `synthetic_5pct` | 10 s | 0.952 | 0.6286 | 0.3852 | cl-32B-U | 0.3909 | 0.0057 [-0.014, +0.024] | 0.2377 [+0.212, +0.264] | 0.048 |
| `synthetic_10pct` | 1 s | 0.897 | 0.2006 | 0.1538 | dev-4B-SHORT-N1 | 0.0174 | -0.1364 [-0.160, -0.114] | 0.1832 [+0.157, +0.210] | 0.103 |
| `synthetic_10pct` | 2 s | 0.897 | 0.5170 | 0.2692 | cl-4B-RICH | 0.0196 | -0.2496 [-0.284, -0.216] | 0.4974 [+0.463, +0.531] | 0.103 |
| `synthetic_10pct` | 5 s | 0.897 | 0.5985 | 0.3537 | cl-32B-RICH | 0.3754 | 0.0217 [+0.007, +0.037] | 0.2231 [+0.197, +0.249] | 0.103 |
| `synthetic_10pct` | 10 s | 0.897 | 0.6031 | 0.3618 | cl-32B-U | 0.3754 | 0.0136 [-0.007, +0.033] | 0.2278 [+0.202, +0.253] | 0.103 |
| `synthetic_20pct` | 1 s | 0.799 | 0.1947 | 0.1538 | dev-4B-SHORT-N1 | 0.0311 | -0.1228 [-0.146, -0.101] | 0.1636 [+0.140, +0.190] | 0.201 |
| `synthetic_20pct` | 2 s | 0.799 | 0.4775 | 0.2425 | cl-4B-RICH | 0.0328 | -0.2096 [-0.244, -0.177] | 0.4447 [+0.411, +0.481] | 0.201 |
| `synthetic_20pct` | 5 s | 0.799 | 0.5577 | 0.3145 | cl-32B-RICH | 0.3499 | 0.0354 [+0.020, +0.052] | 0.2078 [+0.182, +0.233] | 0.201 |
| `synthetic_20pct` | 10 s | 0.799 | 0.5624 | 0.3226 | cl-32B-U | 0.3499 | 0.0273 [+0.006, +0.047] | 0.2125 [+0.188, +0.238] | 0.201 |
| `synthetic_30pct` | 1 s | 0.705 | 0.1885 | 0.1538 | dev-4B-SHORT-N1 | 0.0469 | -0.1069 [-0.129, -0.086] | 0.1416 [+0.118, +0.165] | 0.295 |
| `synthetic_30pct` | 2 s | 0.705 | 0.4397 | 0.2120 | cl-4B-RICH | 0.0486 | -0.1634 [-0.198, -0.129] | 0.3911 [+0.357, +0.425] | 0.295 |
| `synthetic_30pct` | 5 s | 0.705 | 0.5204 | 0.2799 | cl-32B-RICH | 0.3307 | 0.0507 [+0.034, +0.069] | 0.1898 [+0.166, +0.216] | 0.295 |
| `synthetic_30pct` | 10 s | 0.705 | 0.5248 | 0.2863 | cl-32B-U | 0.3307 | 0.0444 [+0.024, +0.066] | 0.1941 [+0.171, +0.220] | 0.295 |

**Uplink 88 Mbit/s, RTT 22 ms**

| regime | deadline | reachable | oracle | best static | (pick) | P1 | P1 − static [95 % CI] | oracle − P1 [95 % CI] | device fallback |
|---|---|---|---|---|---|---|---|---|---|
| `outdoor_driving` | 1 s | 0.861 | 0.2207 | 0.1538 | dev-4B-SHORT-N1 | 0.0230 | -0.1308 [-0.155, -0.109] | 0.1976 [+0.170, +0.226] | 0.139 |
| `outdoor_driving` | 2 s | 0.861 | 0.5120 | 0.2811 | cl-4B-RECENT | 0.0251 | -0.2560 [-0.289, -0.222] | 0.4869 [+0.450, +0.522] | 0.139 |
| `outdoor_driving` | 5 s | 0.861 | 0.5816 | 0.3385 | cl-32B-RICH | 0.3670 | 0.0285 [+0.014, +0.043] | 0.2146 [+0.189, +0.241] | 0.139 |
| `outdoor_driving` | 10 s | 0.861 | 0.5865 | 0.3467 | cl-32B-U | 0.3670 | 0.0203 [+0.000, +0.039] | 0.2195 [+0.194, +0.245] | 0.139 |
| `indoor` | 1 s | 0.994 | 0.2304 | 0.1538 | dev-4B-SHORT-N1 | 0.0033 | -0.1505 [-0.175, -0.128] | 0.2271 [+0.199, +0.257] | 0.006 |
| `indoor` | 2 s | 0.994 | 0.5633 | 0.3236 | cl-4B-RECENT | 0.0057 | -0.3179 [-0.350, -0.286] | 0.5576 [+0.523, +0.591] | 0.006 |
| `indoor` | 5 s | 0.994 | 0.6412 | 0.3929 | cl-32B-RICH | 0.4022 | 0.0093 [-0.004, +0.023] | 0.2389 [+0.213, +0.266] | 0.006 |
| `indoor` | 10 s | 0.994 | 0.6460 | 0.4025 | cl-32B-U | 0.4022 | -0.0003 [-0.020, +0.019] | 0.2437 [+0.218, +0.270] | 0.006 |
| `synthetic_0pct` | 1 s | 1.000 | 0.2308 | 0.1538 | dev-4B-SHORT-N1 | 0.0024 | -0.1515 [-0.176, -0.129] | 0.2284 [+0.200, +0.259] | 0.000 |
| `synthetic_0pct` | 2 s | 1.000 | 0.5657 | 0.3254 | cl-4B-RECENT | 0.0047 | -0.3207 [-0.353, -0.289] | 0.5609 [+0.526, +0.594] | 0.000 |
| `synthetic_0pct` | 5 s | 1.000 | 0.6438 | 0.3953 | cl-32B-RICH | 0.4036 | 0.0083 [-0.005, +0.021] | 0.2402 [+0.214, +0.268] | 0.000 |
| `synthetic_0pct` | 10 s | 1.000 | 0.6485 | 0.4047 | cl-32B-U | 0.4036 | -0.0012 [-0.021, +0.017] | 0.2450 [+0.219, +0.272] | 0.000 |
| `synthetic_2pct` | 1 s | 0.980 | 0.2296 | 0.1538 | dev-4B-SHORT-N1 | 0.0050 | -0.1489 [-0.173, -0.126] | 0.2247 [+0.196, +0.255] | 0.020 |
| `synthetic_2pct` | 2 s | 0.980 | 0.5580 | 0.3191 | cl-4B-RECENT | 0.0073 | -0.3117 [-0.344, -0.280] | 0.5507 [+0.516, +0.585] | 0.020 |
| `synthetic_2pct` | 5 s | 0.980 | 0.6349 | 0.3872 | cl-32B-RICH | 0.3981 | 0.0109 [-0.002, +0.025] | 0.2368 [+0.211, +0.264] | 0.020 |
| `synthetic_2pct` | 10 s | 0.980 | 0.6396 | 0.3958 | cl-32B-U | 0.3981 | 0.0023 [-0.017, +0.021] | 0.2415 [+0.216, +0.268] | 0.020 |
| `synthetic_5pct` | 1 s | 0.952 | 0.2270 | 0.1538 | dev-4B-SHORT-N1 | 0.0092 | -0.1446 [-0.168, -0.122] | 0.2178 [+0.189, +0.247] | 0.048 |
| `synthetic_5pct` | 2 s | 0.952 | 0.5486 | 0.3109 | cl-4B-RECENT | 0.0114 | -0.2995 [-0.333, -0.267] | 0.5372 [+0.503, +0.571] | 0.048 |
| `synthetic_5pct` | 5 s | 0.952 | 0.6240 | 0.3758 | cl-32B-RICH | 0.3909 | 0.0151 [+0.002, +0.029] | 0.2331 [+0.208, +0.260] | 0.048 |
| `synthetic_5pct` | 10 s | 0.952 | 0.6286 | 0.3852 | cl-32B-U | 0.3909 | 0.0057 [-0.014, +0.024] | 0.2377 [+0.212, +0.264] | 0.048 |
| `synthetic_10pct` | 1 s | 0.897 | 0.2217 | 0.1538 | dev-4B-SHORT-N1 | 0.0174 | -0.1364 [-0.160, -0.114] | 0.2043 [+0.176, +0.233] | 0.103 |
| `synthetic_10pct` | 2 s | 0.897 | 0.5260 | 0.2908 | cl-4B-RECENT | 0.0196 | -0.2712 [-0.304, -0.239] | 0.5064 [+0.472, +0.540] | 0.103 |
| `synthetic_10pct` | 5 s | 0.897 | 0.5985 | 0.3537 | cl-32B-RICH | 0.3754 | 0.0217 [+0.007, +0.037] | 0.2231 [+0.197, +0.249] | 0.103 |
| `synthetic_10pct` | 10 s | 0.897 | 0.6031 | 0.3618 | cl-32B-U | 0.3754 | 0.0136 [-0.007, +0.033] | 0.2278 [+0.202, +0.253] | 0.103 |
| `synthetic_20pct` | 1 s | 0.799 | 0.2143 | 0.1538 | dev-4B-SHORT-N1 | 0.0311 | -0.1228 [-0.146, -0.101] | 0.1833 [+0.157, +0.211] | 0.201 |
| `synthetic_20pct` | 2 s | 0.799 | 0.4899 | 0.2614 | cl-4B-RECENT | 0.0328 | -0.2285 [-0.263, -0.196] | 0.4571 [+0.424, +0.491] | 0.201 |
| `synthetic_20pct` | 5 s | 0.799 | 0.5577 | 0.3145 | cl-32B-RICH | 0.3499 | 0.0354 [+0.020, +0.052] | 0.2078 [+0.182, +0.233] | 0.201 |
| `synthetic_20pct` | 10 s | 0.799 | 0.5624 | 0.3226 | cl-32B-U | 0.3499 | 0.0273 [+0.006, +0.047] | 0.2125 [+0.188, +0.238] | 0.201 |
| `synthetic_30pct` | 1 s | 0.705 | 0.2062 | 0.1538 | dev-4B-SHORT-N1 | 0.0470 | -0.1069 [-0.129, -0.086] | 0.1592 [+0.134, +0.185] | 0.295 |
| `synthetic_30pct` | 2 s | 0.705 | 0.4566 | 0.2302 | cl-4B-RECENT | 0.0486 | -0.1817 [-0.214, -0.148] | 0.4080 [+0.375, +0.442] | 0.295 |
| `synthetic_30pct` | 5 s | 0.705 | 0.5204 | 0.2799 | cl-32B-RICH | 0.3307 | 0.0507 [+0.034, +0.069] | 0.1898 [+0.166, +0.216] | 0.295 |
| `synthetic_30pct` | 10 s | 0.705 | 0.5248 | 0.2863 | cl-32B-U | 0.3307 | 0.0444 [+0.024, +0.066] | 0.1941 [+0.171, +0.220] | 0.295 |

CIs are video-and-offset bootstraps, 2,000 resamples, seed 0 (videos resampled with replacement, then one offset drawn per resampled video).

## 7. Where the P1 − static difference comes from: outage vs connected questions

| regime | uplink | deadline | total P1 − static | connected n | P1 | static | outage n | P1 | static | share of the difference from outage questions |
|---|---|---|---|---|---|---|---|---|---|---|
| `outdoor_driving` | 13.6 Mbit/s | 2 s | -0.2349 | 14,551 | 0.0046 | 0.3019 | 2,349 | 0.1520 | 0.0000 | -9 % |
| `outdoor_driving` | 13.6 Mbit/s | 5 s | +0.0285 | 14,551 | 0.4018 | 0.3932 | 2,349 | 0.1520 | 0.0000 | 74 % |
| `outdoor_driving` | 13.6 Mbit/s | 10 s | +0.0203 | 14,551 | 0.4018 | 0.4027 | 2,349 | 0.1520 | 0.0000 | 104 % |
| `indoor` | 13.6 Mbit/s | 2 s | -0.3176 | 16,795 | 0.0048 | 0.3253 | 105 | 0.1524 | 0.0000 | -0 % |
| `indoor` | 13.6 Mbit/s | 5 s | +0.0093 | 16,795 | 0.4035 | 0.3951 | 105 | 0.1524 | 0.0000 | 10 % |
| `indoor` | 13.6 Mbit/s | 10 s | +0.0001 | 16,795 | 0.4038 | 0.4046 | 105 | 0.1524 | 0.0000 | 1600 % |
| `synthetic_5pct` | 13.6 Mbit/s | 2 s | -0.2860 | 16,089 | 0.0045 | 0.3124 | 811 | 0.1480 | 0.0000 | -2 % |
| `synthetic_5pct` | 13.6 Mbit/s | 5 s | +0.0151 | 16,089 | 0.4031 | 0.3947 | 811 | 0.1480 | 0.0000 | 47 % |
| `synthetic_5pct` | 13.6 Mbit/s | 10 s | +0.0057 | 16,089 | 0.4031 | 0.4046 | 811 | 0.1480 | 0.0000 | 125 % |
| `synthetic_10pct` | 13.6 Mbit/s | 2 s | -0.2496 | 15,154 | 0.0049 | 0.3002 | 1,746 | 0.1472 | 0.0000 | -6 % |
| `synthetic_10pct` | 13.6 Mbit/s | 5 s | +0.0217 | 15,154 | 0.4017 | 0.3944 | 1,746 | 0.1472 | 0.0000 | 70 % |
| `synthetic_10pct` | 13.6 Mbit/s | 10 s | +0.0136 | 15,154 | 0.4017 | 0.4035 | 1,746 | 0.1472 | 0.0000 | 112 % |
| `synthetic_20pct` | 13.6 Mbit/s | 2 s | -0.2096 | 13,497 | 0.0042 | 0.3036 | 3,403 | 0.1463 | 0.0000 | -14 % |
| `synthetic_20pct` | 13.6 Mbit/s | 5 s | +0.0354 | 13,497 | 0.4013 | 0.3938 | 3,403 | 0.1463 | 0.0000 | 83 % |
| `synthetic_20pct` | 13.6 Mbit/s | 10 s | +0.0273 | 13,497 | 0.4013 | 0.4039 | 3,403 | 0.1463 | 0.0000 | 108 % |
| `synthetic_30pct` | 13.6 Mbit/s | 2 s | -0.1634 | 11,920 | 0.0044 | 0.3005 | 4,980 | 0.1542 | 0.0000 | -28 % |
| `synthetic_30pct` | 13.6 Mbit/s | 5 s | +0.0507 | 11,920 | 0.4044 | 0.3969 | 4,980 | 0.1542 | 0.0000 | 90 % |
| `synthetic_30pct` | 13.6 Mbit/s | 10 s | +0.0444 | 11,920 | 0.4044 | 0.4059 | 4,980 | 0.1542 | 0.0000 | 102 % |

The share column is the outage questions' contribution divided by the total difference. It is **74–104 % for outdoor-driving and 47–125 % for the synthetic regimes at 5 and 10 s** — i.e. the whole of the margin, and at 10 s slightly more than the whole, because on connected questions the static configuration is marginally ahead. The indoor 10 s cell reads 1600 % only because its total difference is +0.0001; the share is meaningless where the denominator is near zero, and it is left in rather than suppressed. At the 2 s deadline the share is negative: there the outage questions are the only ones where P1 is ahead, and they do not come close to covering the connected-question loss.

## 8. STREAM vs ON-DEMAND, same questions, same curves

| regime | uplink | deadline | STREAM oracle | STREAM static (pick) | ON-DEMAND oracle | ON-DEMAND static (pick) |
|---|---|---|---|---|---|---|
| `outdoor_driving` | 5 Mbit/s | 2 s | 0.4463 | 0.2167 (cl-4B-RICH) | 0.1904 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 5 Mbit/s | 5 s | 0.5815 | 0.3385 (cl-32B-RICH) | 0.2226 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 5 Mbit/s | 10 s | 0.5858 | 0.3385 (cl-32B-RICH) | 0.2554 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 13.6 Mbit/s | 2 s | 0.5018 | 0.2599 (cl-4B-RICH) | 0.1976 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 13.6 Mbit/s | 5 s | 0.5816 | 0.3385 (cl-32B-RICH) | 0.2626 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 13.6 Mbit/s | 10 s | 0.5865 | 0.3467 (cl-32B-U) | 0.3257 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 88 Mbit/s | 2 s | 0.5120 | 0.2811 (cl-4B-RECENT) | 0.2688 | 0.1538 (dev-4B-SHORT-N1) |
| `outdoor_driving` | 88 Mbit/s | 5 s | 0.5816 | 0.3385 (cl-32B-RICH) | 0.4222 | 0.2031 (cl-32B-D2-cold) |
| `outdoor_driving` | 88 Mbit/s | 10 s | 0.5865 | 0.3467 (cl-32B-U) | 0.4862 | 0.2552 (cl-32B-RICH) |
| `synthetic_10pct` | 5 Mbit/s | 2 s | 0.4599 | 0.2341 (cl-4B-RICH) | 0.1904 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 5 Mbit/s | 5 s | 0.5982 | 0.3537 (cl-32B-RICH) | 0.2245 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 5 Mbit/s | 10 s | 0.6027 | 0.3537 (cl-32B-RICH) | 0.2574 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 13.6 Mbit/s | 2 s | 0.5170 | 0.2692 (cl-4B-RICH) | 0.1988 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 13.6 Mbit/s | 5 s | 0.5985 | 0.3537 (cl-32B-RICH) | 0.2657 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 13.6 Mbit/s | 10 s | 0.6031 | 0.3618 (cl-32B-U) | 0.3315 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 88 Mbit/s | 2 s | 0.5260 | 0.2908 (cl-4B-RECENT) | 0.2695 | 0.1538 (dev-4B-SHORT-N1) |
| `synthetic_10pct` | 88 Mbit/s | 5 s | 0.5985 | 0.3537 (cl-32B-RICH) | 0.4433 | 0.2133 (cl-32B-D2-cold) |
| `synthetic_10pct` | 88 Mbit/s | 10 s | 0.6031 | 0.3618 (cl-32B-U) | 0.4962 | 0.2640 (cl-32B-RICH) |

P1 is defined as a STREAM policy ('cloud STREAM when connected') and is therefore not evaluated under ON-DEMAND.

**Uplink MB per hour charged, by mode** (outdoor-driving, PNG; STREAM is charged whether or not a question arrives):

| representation | STREAM | ON-DEMAND |
|---|---|---|
| RECENT | 994.7 | 1,113.4 |
| RICH | 503.4 | 1,138.8 |
| U | 1,498.1 | 1,594.0 |
| D2 | 251.7 | 600.4 |

The comparison is not a free lunch for STREAM: at these question densities STREAM and ON-DEMAND move comparable volumes, and STREAM moves more on the arms the policy does not end up using. What STREAM buys is *when* the bytes move.

## 9. StudyE4 table 4.1, recomputed

StudyE4 table 4.1 recomputed with StudyF3's per-format, per-cache-state latency curves and ONE deployment mode applied to all cloud arms. RTTs are StudyE6b's pre-registered values (60/44/22 ms); StudyE4 used 142 ms at 5 Mbit/s. No network outages, as in StudyE4.

| net / format / deadline | E4 as published | E6 Part 0 | **E6b STREAM** | **E6b ON-DEMAND** | E6b STREAM best static | E6b ON-DEMAND best static |
|---|---|---|---|---|---|---|
| 5 Mbit/s / png / 1 s | 0.0000 | 0.0000 | **0.0012** [+0.000, +0.004] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | dev-4B-RICH |
| 5 Mbit/s / png / 2 s | 0.0000 | 0.0580 | **0.0450** [+0.031, +0.060] | **0.0012** [+0.000, +0.004] | cl-4B-RICH | dev-4B-RICH |
| 5 Mbit/s / png / 5 s | 0.0000 | 0.0899 | **0.1964** [+0.171, +0.223] | **0.0000** [+0.000, +0.000] | cl-32B-RICH | cl-32B-D2 |
| 5 Mbit/s / png / 10 s | 0.0130 | 0.0781 | **0.2012** [+0.175, +0.227] | **0.0036** [+0.000, +0.008] | cl-32B-U | cl-32B-D2 |
| 5 Mbit/s / raw / 1 s | 0.0000 | 0.0000 | **0.0012** [+0.000, +0.004] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | dev-4B-RICH |
| 5 Mbit/s / raw / 2 s | 0.0000 | 0.0355 | **0.0047** [+0.001, +0.010] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | dev-4B-RICH |
| 5 Mbit/s / raw / 5 s | 0.0000 | 0.1254 | **0.1964** [+0.171, +0.223] | **0.0024** [+0.000, +0.006] | cl-32B-RICH | dev-4B-RICH |
| 5 Mbit/s / raw / 10 s | 0.0071 | 0.0781 | **0.2012** [+0.175, +0.227] | **0.0024** [+0.000, +0.006] | cl-32B-U | cl-32B-D2 |
| 13.6 Mbit/s / png / 1 s | 0.0000 | 0.0036 | **0.0036** [+0.000, +0.008] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | cl-32B-D2 |
| 13.6 Mbit/s / png / 2 s | 0.0000 | 0.0686 | **0.1195** [+0.099, +0.141] | **0.0000** [+0.000, +0.000] | cl-4B-RECENT | cl-32B-D2 |
| 13.6 Mbit/s / png / 5 s | 0.0036 | 0.0793 | **0.1964** [+0.171, +0.223] | **0.0012** [+0.000, +0.004] | cl-32B-RICH | cl-32B-D2 |
| 13.6 Mbit/s / png / 10 s | 0.0675 | 0.0781 | **0.2012** [+0.175, +0.227] | **0.0036** [+0.000, +0.008] | cl-32B-U | cl-32B-D2 |
| 13.6 Mbit/s / raw / 1 s | 0.0000 | 0.0000 | **0.0012** [+0.000, +0.004] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | dev-4B-RICH |
| 13.6 Mbit/s / raw / 2 s | 0.0000 | 0.0710 | **0.0462** [+0.033, +0.061] | **0.0000** [+0.000, +0.000] | cl-4B-RICH | cl-32B-D2 |
| 13.6 Mbit/s / raw / 5 s | 0.0000 | 0.0828 | **0.1964** [+0.171, +0.223] | **0.0000** [+0.000, +0.000] | cl-32B-RICH | cl-32B-D2 |
| 13.6 Mbit/s / raw / 10 s | 0.0237 | 0.0781 | **0.2012** [+0.175, +0.227] | **0.0036** [+0.000, +0.008] | cl-32B-U | cl-32B-D2 |
| 88 Mbit/s / png / 1 s | 0.0012 | 0.0154 | **0.0036** [+0.000, +0.008] | **0.0012** [+0.000, +0.004] | cl-32B-D2 | cl-32B-D2 |
| 88 Mbit/s / png / 2 s | 0.0249 | 0.0781 | **0.1219** [+0.101, +0.144] | **0.0012** [+0.000, +0.004] | cl-4B-RECENT | cl-32B-D2 |
| 88 Mbit/s / png / 5 s | 0.1432 | 0.1444 | **0.1964** [+0.171, +0.223] | **0.1586** [+0.135, +0.182] | cl-32B-RICH | cl-4B-RECENT |
| 88 Mbit/s / png / 10 s | 0.1692 | 0.1692 | **0.2012** [+0.175, +0.227] | **0.1953** [+0.170, +0.220] | cl-32B-U | cl-32B-RICH |
| 88 Mbit/s / raw / 1 s | 0.0000 | 0.0083 | **0.0036** [+0.000, +0.008] | **0.0000** [+0.000, +0.000] | cl-32B-D2 | cl-32B-D2 |
| 88 Mbit/s / raw / 2 s | 0.0059 | 0.0781 | **0.1219** [+0.101, +0.144] | **0.0012** [+0.000, +0.004] | cl-4B-RECENT | cl-32B-D2 |
| 88 Mbit/s / raw / 5 s | 0.0331 | 0.0781 | **0.1964** [+0.171, +0.223] | **0.0036** [+0.000, +0.008] | cl-32B-RICH | cl-32B-D2 |
| 88 Mbit/s / raw / 10 s | 0.2000 | 0.1716 | **0.2012** [+0.175, +0.227] | **0.1633** [+0.140, +0.185] | cl-32B-U | cl-32B-D2 |

Headroom is oracle − per-type cross-fit, StudyE4's own metric, over StudyE4's own nine configurations, two-fold cross-fitting by video and a 2,000-resample video bootstrap at seed 0, with no network outages — exactly StudyE4's design, with only the costs changed. The 5 Mbit/s row uses RTT 60 ms where StudyE4 used 142 ms.

## 10. One instrumented video through an outage

`1001141161985610_start_0.0_end_599.99`, offset 0, mapped to outdoor_driving session 6 starting at trace second 1084; video span 388 s, of which **66 s are outage**. Uplink 13.6Mbps_44ms, STREAM, png, deadline 5 s. Stream rates: D2 69,922 B/s (251.7 MB/h), RECENT 276,307 B/s (994.7 MB/h), RICH 139,845 B/s (503.4 MB/h), U 416,152 B/s (1,498.1 MB/h).

**Question at t = 236 s** (trace second 1320, link UP, 10 outage seconds in the preceding 60 s)

| configuration | backlog B | newest frame B | pending B | upload s | RTT s | compute s | total s | ≤ deadline | correct | utility |
|---|---|---|---|---|---|---|---|---|---|---|
| `cl-4B-RECENT` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 1.6745 | 1.8810 | yes | no | 0 |
| `cl-4B-RICH` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 1.5928 | 1.7191 | yes | yes | 1 |
| `cl-4B-U` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 2.1742 | 2.3808 | yes | yes | 1 |
| `cl-32B-RECENT` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 3.7284 | 3.9349 | yes | no | 0 |
| `cl-32B-RICH` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 3.5132 | 3.6395 | yes | yes | 1 |
| `cl-32B-U` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 5.3368 | 5.5434 | no | yes | 0 |
| `cl-32B-D2-cold` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 2.5782 | 2.7045 | yes | yes | 1 |
| `cl-32B-D2-warm` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | — | — | no | — | 0 |
| `dev-4B-SHORT-N1` | — | — | — | 0.0000 | — | 0.5525 | 0.5525 | yes | no | 0 |
| `dev-4B-SHORT-N3` | — | — | — | 0.0000 | — | 1.3635 | 1.3635 | yes | no | 0 |
| `dev-4B-SHORT-N9` | — | — | — | 0.0000 | — | 3.8560 | 3.8560 | yes | no | 0 |
| `dev-4B-RECENT` | — | — | — | 0.0000 | — | 17.0792 | 17.0792 | no | no | 0 |

**Question at t = 300 s** (trace second 1384, link UP, 8 outage seconds in the preceding 60 s)

| configuration | backlog B | newest frame B | pending B | upload s | RTT s | compute s | total s | ≤ deadline | correct | utility |
|---|---|---|---|---|---|---|---|---|---|---|
| `cl-4B-RECENT` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 1.6760 | 1.8825 | yes | no | 0 |
| `cl-4B-RICH` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 1.6953 | 1.8216 | yes | no | 0 |
| `cl-4B-U` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 2.2847 | 2.4913 | yes | no | 0 |
| `cl-32B-RECENT` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 3.7326 | 3.9391 | yes | yes | 1 |
| `cl-32B-RICH` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 3.7848 | 3.9111 | yes | yes | 1 |
| `cl-32B-U` | 0 | 276,307 | 276,307 | 0.1625 | 0.044 | 5.8409 | 6.0475 | no | yes | 0 |
| `cl-32B-D2-cold` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 3.3565 | 3.4828 | yes | yes | 1 |
| `cl-32B-D2-warm` | 0 | 139,845 | 139,845 | 0.0823 | 0.044 | 1.1624 | 1.2887 | yes | yes | 1 |
| `dev-4B-SHORT-N1` | — | — | — | 0.0000 | — | 0.5525 | 0.5525 | yes | no | 0 |
| `dev-4B-SHORT-N3` | — | — | — | 0.0000 | — | 1.3635 | 1.3635 | yes | no | 0 |
| `dev-4B-SHORT-N9` | — | — | — | 0.0000 | — | 3.8560 | 3.8560 | yes | no | 0 |
| `dev-4B-RECENT` | — | — | — | 0.0000 | — | 17.0909 | 17.0909 | no | no | 0 |

**Question at t = 387 s** (trace second 1471, link **DOWN**, 9 outage seconds in the preceding 60 s)

| configuration | backlog B | newest frame B | pending B | upload s | RTT s | compute s | total s | ≤ deadline | correct | utility |
|---|---|---|---|---|---|---|---|---|---|---|
| `cl-4B-RECENT` | 0 | 276,307 | 276,307 | — | 0.044 | 1.6721 | — | no | no | 0 |
| `cl-4B-RICH` | 0 | 139,845 | 139,845 | — | 0.044 | 1.6927 | — | no | yes | 0 |
| `cl-4B-U` | 0 | 276,307 | 276,307 | — | 0.044 | 2.3342 | — | no | yes | 0 |
| `cl-32B-RECENT` | 0 | 276,307 | 276,307 | — | 0.044 | 3.7221 | — | no | no | 0 |
| `cl-32B-RICH` | 0 | 139,845 | 139,845 | — | 0.044 | 3.7777 | — | no | yes | 0 |
| `cl-32B-U` | 0 | 276,307 | 276,307 | — | 0.044 | 6.1155 | — | no | yes | 0 |
| `cl-32B-D2-cold` | 0 | 139,845 | 139,845 | — | 0.044 | 4.4657 | — | no | yes | 0 |
| `cl-32B-D2-warm` | 0 | 139,845 | 139,845 | — | 0.044 | 1.3497 | — | no | yes | 0 |
| `dev-4B-SHORT-N1` | — | — | — | 0.0000 | — | 0.5525 | 0.5525 | yes | no | 0 |
| `dev-4B-SHORT-N3` | — | — | — | 0.0000 | — | 1.3635 | 1.3635 | yes | no | 0 |
| `dev-4B-SHORT-N9` | — | — | — | 0.0000 | — | 3.8560 | 3.8560 | yes | no | 0 |
| `dev-4B-RECENT` | — | — | — | 0.0000 | — | 17.0616 | 17.0616 | no | no | 0 |

Every row is checkable by hand: `total s = upload s + RTT + compute s` for a cloud configuration and `total s = compute s` for a device one; `upload s = pending B / (uplink bits per second / 8)` adjusted for any outage seconds crossed; `utility = 1` only when the configuration is both correct and delivered. Where the link is down at the question instant the cloud rows carry no total at all — by the pre-registered rule only device configurations can answer.

Two things are visible in this trace that the aggregate tables only imply. First, the backlog term is **zero** at all three questions even though 66 of the 388 trace seconds are outage: at 13.6 Mbit/s a 1–3 s Irish gap leaves at most a few hundred kilobytes, which clears long before the next question arrives, so under STREAM the binding quantity is reachability at the question instant, not the queue. Second, at t = 387 s the link is down, five of the eight cloud configurations hold the correct answer, and every one of them scores zero while the device — which can answer — is wrong.

## 11. Negative control (a) — outage fraction 0

Outage fraction 0 (synthetic_0pct). P1 must never fall back to the device, so its device-fallback fraction must be 0 and P1 must equal the always-cloud decomposed policy.

| cell | reachable | P1 device-fallback fraction | P1 | always-cloud decomposed | abs diff |
|---|---|---|---|---|---|
| `synthetic_0pct / 5Mbps_60ms / STREAM / 1s` | 1.000 | 0.000 | 0.0024 | 0.0024 | 0.000000 |
| `synthetic_0pct / 5Mbps_60ms / STREAM / 2s` | 1.000 | 0.000 | 0.0047 | 0.0047 | 0.000000 |
| `synthetic_0pct / 5Mbps_60ms / STREAM / 5s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |
| `synthetic_0pct / 5Mbps_60ms / STREAM / 10s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 1s` | 1.000 | 0.000 | 0.0024 | 0.0024 | 0.000000 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 2s` | 1.000 | 0.000 | 0.0047 | 0.0047 | 0.000000 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 5s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 10s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |
| `synthetic_0pct / 88Mbps_22ms / STREAM / 1s` | 1.000 | 0.000 | 0.0024 | 0.0024 | 0.000000 |
| `synthetic_0pct / 88Mbps_22ms / STREAM / 2s` | 1.000 | 0.000 | 0.0047 | 0.0047 | 0.000000 |
| `synthetic_0pct / 88Mbps_22ms / STREAM / 5s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |
| `synthetic_0pct / 88Mbps_22ms / STREAM / 10s` | 1.000 | 0.000 | 0.4036 | 0.4036 | 0.000000 |

**PASS.** Device-fallback fraction is 0.000 in every cell and P1 equals the always-cloud decomposed policy to 0.000000. At the 5 s and 10 s deadlines P1 = 0.4036, which is StudyE6 setting (a)'s evidence-only F1 accuracy (0.4036) — the mechanism switches off cleanly and the policy reduces to its cloud half.

Negative control (b) (device-warm accuracy set to device short-window accuracy) belongs to Stage B and is not run: the quantity it would disable does not exist until StudyE7 and StudyE8 are committed.

## 12. UNKNOWN sensitivity — linear extrapolation instead of unavailable

| cell | oracle, primary | oracle, extrapolated | configurations that move by > 0.002 |
|---|---|---|---|
| `indoor / 13.6Mbps_44ms / STREAM / 2s` | 0.5585 | 0.5585 | `cl-32B-D2-warm` 0.2021→0.2068 |
| `indoor / 13.6Mbps_44ms / STREAM / 5s` | 0.6411 | 0.6411 | `cl-4B-U` 0.3251→0.3334, `cl-32B-D2-warm` 0.2600→0.2659 |
| `outdoor_driving / 13.6Mbps_44ms / STREAM / 2s` | 0.5018 | 0.5018 | `cl-32B-D2-warm` 0.1720→0.1761 |
| `outdoor_driving / 13.6Mbps_44ms / STREAM / 5s` | 0.5816 | 0.5816 | `cl-4B-U` 0.2825→0.2896, `cl-32B-D2-warm` 0.2213→0.2264 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 2s` | 0.5609 | 0.5609 | `cl-32B-D2-warm` 0.2036→0.2083 |
| `synthetic_0pct / 13.6Mbps_44ms / STREAM / 5s` | 0.6438 | 0.6438 | `cl-4B-U` 0.3278→0.3361, `cl-32B-D2-warm` 0.2615→0.2675 |
| `synthetic_10pct / 13.6Mbps_44ms / STREAM / 2s` | 0.5170 | 0.5170 | `cl-32B-D2-warm` 0.1826→0.1865 |
| `synthetic_10pct / 13.6Mbps_44ms / STREAM / 5s` | 0.5985 | 0.5985 | `cl-4B-U` 0.2927→0.3004, `cl-32B-D2-warm` 0.2347→0.2397 |
| `synthetic_20pct / 13.6Mbps_44ms / STREAM / 2s` | 0.4775 | 0.4775 | `cl-32B-D2-warm` 0.1637→0.1673 |
| `synthetic_20pct / 13.6Mbps_44ms / STREAM / 5s` | 0.5577 | 0.5577 | `cl-4B-U` 0.2630→0.2698, `cl-32B-D2-warm` 0.2109→0.2154 |
| `synthetic_2pct / 13.6Mbps_44ms / STREAM / 2s` | 0.5522 | 0.5522 | `cl-32B-D2-warm` 0.1994→0.2041 |
| `synthetic_2pct / 13.6Mbps_44ms / STREAM / 5s` | 0.6349 | 0.6349 | `cl-4B-U` 0.3209→0.3291, `cl-32B-D2-warm` 0.2562→0.2621 |
| `synthetic_30pct / 13.6Mbps_44ms / STREAM / 2s` | 0.4397 | 0.4398 | `cl-32B-D2-warm` 0.1443→0.1475 |
| `synthetic_30pct / 13.6Mbps_44ms / STREAM / 5s` | 0.5204 | 0.5204 | `cl-4B-U` 0.2312→0.2373, `cl-32B-D2-warm` 0.1860→0.1902 |
| `synthetic_5pct / 13.6Mbps_44ms / STREAM / 2s` | 0.5422 | 0.5422 | `cl-32B-D2-warm` 0.1938→0.1985 |
| `synthetic_5pct / 13.6Mbps_44ms / STREAM / 5s` | 0.6240 | 0.6240 | `cl-4B-U` 0.3133→0.3213, `cl-32B-D2-warm` 0.2493→0.2551 |

The primary analysis treats an out-of-range prompt as unavailable. Replacing that with the curve's linear extrapolation (labelled, not measured) changes no oracle value and moves only `cl-4B-U` and `cl-32B-D2-warm`, by at most 0.008. The UNKNOWN rule is not load-bearing here — which is itself a consequence of fixing error 2.

## 13. Keep-warm costs that Stage A can report

The pre-registered cost set is device energy above loaded idle (StudyE8 Parts A and C), uplink MB, and cloud warm-session seconds. Stage A can report the second in full and the third structurally; the first is PENDING.

- **Uplink MB per hour** is in §3.2 and §8, charged for the whole session under STREAM.
- **Cloud warm-session seconds**: `cl-32B-D2-warm` holds a session open for the whole video. Over the 234 videos the warm configuration is usable on 605 of 845 questions — the 234 first-questions have no warm session yet and 24 fall outside StudyF3's measured uncached-token range. **No capacity limit is modelled**: this study assumes a warm session is always available on demand. StudyRH5 and StudyRH8 are the measurements that say when that assumption fails — StudyRH5 found GPU-only fleets collapse at 8 concurrent D2 sessions (median 96 s) while 256 GiB of host offload sustains 24 at a 0.81 s median, and StudyRH8 found that past the all-eager knee (D = 96) only demand-matched partial warming beats both pure policies. Nothing here contradicts or extends those; the single-session assumption is stated so that any warm number below is read as an upper bound on what a loaded fleet would deliver.
- **Device energy above loaded idle**: PENDING (StudyE8 Parts A and C). StudyF4 Part B gives per-request energy for the short windows (14.3 / 45.1 / 149.6 J at N = 1/3/9 over a 9.89 W loaded idle), but the *keep-warm* cost — holding a D2 history warm on the Orin between questions — is not measured anywhere, and it is not estimated here.

## 14. Results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior committed | source of prior | ratio | agree |
|---|---|---|---|---|---|
| H1 (4B RECENT) accuracy | 0.3254 | 0.3254 | StudyClean / StudyF1 §2 | 1.000 | agree |
| K3 (32B RECENT) accuracy | 0.3834 | 0.3834 | comparability ledger / StudyF1 §2 | 1.000 | agree |
| K1 (32B RICH) accuracy | 0.3953 | 0.3953 | StudyE6 §12 (best static cell) | 1.000 | agree |
| D2 (32B) accuracy | 0.3957 | 0.3957 | StudyRH4 results table | 1.000 | agree |
| U 32B accuracy | 0.4142 | 0.4142 | StudyD11 §table | 1.000 | agree |
| U 4B accuracy | 0.3361 | 0.3361 | StudyD11 §table | 1.000 | agree |
| device short-window N=1 accuracy | 0.1538 | 0.1538 | StudyF4 Part A | 1.000 | agree |
| device short-window N=3 accuracy | 0.1373 | 0.1373 | StudyF4 Part A | 1.000 | agree |
| device short-window N=9 accuracy | 0.1515 | 0.1515 | StudyF4 Part A | 1.000 | agree |
| device N=1 total latency p50 (s) | 0.5525 | 0.5525 | StudyF4 `study_f4_summary.json` parts.B.1 | 1.000 | agree |
| device N=9 total latency p50 (s) | 3.8560 | 3.8560 | StudyF4 `study_f4_summary.json` parts.B.9 | 1.000 | agree |
| Irish outage fraction | 0.1438 | 0.1438 | E31b §2a (4,105 / 28,551) | 1.000 | agree |

**PASS.** Every ratio is 1.000 and every accuracy reproduces its committed source exactly; no quantity is anywhere near the 2× investigation gate. Two notes, both reported rather than smoothed over:

- StudyF4's **report text** gives device total latency p50 as 0.563 / 1.374 / 3.862 s, while StudyF4's own committed `study_f4_summary.json` gives 0.5525 / 1.3635 / 3.856 s (the report's numbers look like a different percentile). This run uses the committed JSON, which it reproduces to the digit. The discrepancy is inside StudyF4 and is flagged here, not resolved.
- The herolab outage fraction here (0.0074 of seconds) is not the same object as E31b's 0.0091 of *samples* below −75 dBm: this study aggregates to a per-second median first, because outages must be intervals. Ratio 0.81, well inside the gate, and the definitional difference is the whole of it.

**2. Physical plausibility.** Every latency is a StudyF3 or StudyF4/StudyD4-orin measurement or an interpolation inside its measured range; nothing is faster than a committed curve because nothing is computed outside one. The upload rates are arithmetic: 276,307 B at 13.6 Mbit/s is 0.1625 s, which is what the trace shows. 32B cold prefill at ≈270–294 ms per 1k tokens (StudyF3) is ≈3.7k tok/s on an H100 NVL; the Orin at 812–940 tok/s sits in its committed 800–1,050 band (StudyF4 check 2). **PASS.**

**3. Distribution sanity.** Spreads are reported beside every median: upload p50/p95/max per representation and uplink (§3.3), outage run p50/p95/max per regime (§4), and bootstrap CIs on every headline difference. The one place constants legitimately appear is the device short windows, whose latency is a fixed per-N median by construction and whose accuracy is a fixed committed vector. **PASS.**

**4. Definition audit.**

| object | definition used here | matches prior? |
|---|---|---|
| RECENT | 121 frames at 1 fps over the last 120 s, 512×384 | StudyR1 / StudyClean manifest, unchanged |
| RICH | re-sampled whole history, ≤ 256 frames, 352×256 | StudyR1 manifest, unchanged |
| U | RICH frames older than the recent window plus the RECENT frames | StudyD11, as StudyE4/E6 |
| D2 | fixed 2 s stride from t = 0, 352×256, append-only | StudyRH4, unchanged |
| short window | last 3 s, N = 1/3/9 evenly spaced, 560×560 separate images | StudyF1/StudyF4; **not** DevFast's N = 9 over 120 s |
| outage | a second with `cell_id == -1` (Irish) or median RSSI < −75 dBm (herolab) | E31b corrected signals |
| delivered | upload + RTT + compute ≤ deadline, with the cloud unavailable if the link is down at the question instant | new to this study, stated |
| utility | correct AND delivered | StudyE4 / StudyE6 setting (b), unchanged |
| warm (cloud) | vLLM prefix cache holding the session's earlier D2 prefix; priced on uncached tokens | StudyF3 cell d |
| cold | prefix caching off | StudyF3, `cached_tokens = 0` on all 686 cold rows |

**PASS**, with one name used two ways across the literature and disambiguated here: StudyE4's 'continuous upload' meant *only the newest frame pending*, while its Part 1 meant *every frame since the previous question*. This study uses neither as a per-arm choice; it fixes a mode for the whole session.

**5. Claim linkage.** The headline results bear on FORMULATION §Constraints 2 (serving feasibility) and 3 (reachability) and on §Objective's statement that handoff latency on a mobility event is the binding term. They **support** the boundary-condition claim that the problem exists only when bandwidth and capacity are insufficient: at 88 Mbit/s under STREAM the upload term is 0.025 s and the whole decision reduces to compute and correctness. They **do not** speak to the coupling claim (§The coupling claim), which is about fidelity and placement not decomposing — that is Stage B's question. **Scope flag:** FORMULATION §Scoping assumes a single model per deployment, and this study compares a 4B device tier with a 32B cloud tier. That is the scoped-to-discussion case, and StudyF4's 97–98 % per-question agreement on byte-identical frames is the measurement that licenses it; no cross-tier KV transfer is modelled anywhere, so §Scoping's KV-portability exclusion is respected. **PASS with the flag.**

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| `dev-4B-RECENT` accuracy = StudyClean H1 letters | the *cloud* 4B's answers on the 120 s window, not the Orin's | **questionable, flagged**; not load-bearing, since the configuration is undeliverable at every deadline tested (≈17 s) |
| Irish 5G trace as a mobile uplink reachability signal | cell attachment of a driving handset in Ireland in 2019–20, on *download* sessions | valid for reachability (E31b's whole point); **invalid for rate**, which is why uplink is fixed and uplink variation is not modelled |
| herolab RSSI < −75 dBm as an outage | received signal strength at a robot in one room with a co-located AP | valid as a physical measure (E31b); the regime is near-continuous and its alignment is concentrated in 1–3 long-enough sessions |
| synthetic two-state process | nothing measured; a construction with Irish's gap durations | labelled synthetic throughout; it varies outage *frequency* only |
| 45 tokens per second of session time for D2 warm appends | StudyRH4's '5 images (450 tokens) per 10 s' | exact for D2 by construction |

**PASS**, with `dev-4B-RECENT` marked unvalidated and excluded from any headline claim.

## 15. Observations (data only, no interpretation)

1. Under STREAM at 13.6 Mbit/s and a 5 s deadline, outdoor-driving: oracle 0.5816, best static 0.3385 (`cl-32B-RICH`), P1 0.3670. P1 − static = +0.0285 [+0.014, +0.043].
2. The same cell at a 2 s deadline: P1 0.0251 against static 0.2599 (`cl-4B-RICH`), a difference of -0.2349 [-0.270, -0.200].
3. P1 − static is positive with a CI excluding zero at the 5 s deadline in every regime and at every uplink; at 10 s the CI contains zero in several cells; at 2 s it is negative with a CI excluding zero everywhere.
4. On connected questions P1 and the best static configuration are within 0.0086 of each other; on outage questions the static cloud configuration scores exactly 0 and P1 scores 0.1520.
5. The best static configuration changes with the deadline and the mode: 4B arms at 2 s, `cl-32B-RICH` at 5 s, `cl-32B-U` at 10 s under STREAM, and `cl-32B-D2` or a device short window under ON-DEMAND.
6. Deployment mode moves the oracle by more than any policy does: 0.5816 (STREAM) vs 0.2626 (ON-DEMAND) in the same cell.
7. Fixing error 2 removes every UNKNOWN from the cloud 4B arms (471 of 845 previously), and the linear-extrapolation sensitivity then changes no oracle value.
8. Negative control (a) passes exactly: 0.000 device fallback and a 0.000000 difference from the always-cloud policy at outage fraction 0.
9. Oracle − P1 is 0.2146 [+0.189, +0.241] at 13.6 Mbit/s 5 s and 0.2195 [+0.194, +0.245] at 10 s.

## 16. Interpretation (inference, labelled as such)

- **The reported corrections are not a rounding matter.** The three errors moved the low-bandwidth timely-utility results of StudyE4 and StudyE6(b) by more than any policy difference either study measured, and they moved them in the direction that favoured 32B-RICH. The right reading of those two reports is that their accuracy results stand and their delivered-in-time results do not.
- **StudyE6's joint claim should not have been called a real negative.** With 4B-RICH unavailable on 56 % of questions, the arm the policy was supposed to be able to choose was largely absent from setting (b). That is CLAUDE.md's definition of inconclusive, and the reclassification is made in the correction block rather than left implicit.
- **What P1 shows is narrow and worth stating plainly.** A decomposed policy beats the best static configuration at 5 s, and essentially all of the margin is the trivial observation that a device can answer when the network cannot and a fixed cloud configuration cannot. That is a placement effect, not an evidence-selection effect: on connected questions the two are indistinguishable. Whether a *better* placement decision — in particular keeping a tier warm — adds anything beyond this is exactly what Stage A cannot answer.
- **The deadline, not the network, is what breaks the decomposition.** P1 inherits StudyE6 setting (a)'s accuracy-only rule, which has no notion of delivery, so at a 2 s deadline it keeps choosing 32B cells whose compute alone is 3.7–3.8 s. A static policy that simply picks a 4B arm beats it by 23 pp. If a joint policy is ever going to pay here, the first thing it needs is not a better predictor but a deadline-aware action space.
- **On this workload the device fallback is close to worthless, and that caps everything Stage B can find.** Every no-pre-warm device option is at or below chance (StudyF1 and StudyF4 both measured the 3 s window as carrying no detectable information) or takes ~17 s. So the ceiling on any keep-warm policy's value is set by how good a *warm* device history turns out to be — StudyE7's and StudyE8's numbers — and not by the quality of the connectivity predictor.
- **Irish outages are the wrong shape for queueing to matter.** 1–3 s gaps at 13.6 Mbit/s leave backlogs that clear in under a second. The mechanism that actually bites is binary: was the link up when the question arrived. A trace with minute-scale gaps — which E31b looked for and could not obtain without an IEEE DataPort account — would exercise the queue; this one does not.

**CLAUDE.md Rule 2 classification for Stage A.** Stage A reports no null, so Rule 2 does not bind on a result of its own. It does bind on the claim it withdraws: StudyE6's joint-claim null moves from **real negative** to **INCONCLUSIVE (mechanism absent)**, because error 2 removed an arm from the action space the claim is about. Stage A's own chain (Step 2) has no ABSENT link; the one ABSENT entry is the device-warm link, which is why Stage B is not run.

## 17. What Stage A said Stage B would need (recorded before Stage B ran)

*Kept verbatim from the Stage A report. Point 2 is a prediction, and §29 checks it.*

Stage B runs when the user says StudyE7 and StudyE8 are committed. It adds the device-warm and 4B-D2 configurations, P2 (always-warm device), P3 (connectivity-aware keep-warm, predictor on past trace seconds only, θ and H fitted on training trace sessions, cross-fit by trace session, 5 folds, seed 0), P3-noncausal as a sanity bound, oracle keep-warm, negative control (b), and the pre-registered decision rule. Two things found in Stage A should be carried into it and are recorded now, before those results exist:

1. The pre-specified decision cell (uplink 13.6 Mbit/s, deadline 2 or 5 s, outdoor-driving or synthetic ≥ 5 %) behaves very differently at 2 s and at 5 s, because 32B compute alone exceeds 2 s. Both will be reported separately; neither will be dropped.
2. P3's predictor has little to predict on these traces: Irish gaps are 1–3 s and, per E31b §5, persistence accuracy at H = 10–60 s is 0.74–0.76 and is driven by the 85.6 % base rate. If P3 ≈ P2 at equal energy, the pre-registered reading is that the decision is a static rule — and the trace's gap structure, not the predictor, will be the reason.

---

# StudyE6b-mobility — STAGE B: when to keep which tier warm

**Gate cleared 2026-11-11 (later).** Stage A stopped before P2/P3 because the device-warm link was ABSENT. `StudyE7-d2-4b` (4B on the D2 history, plus 4B latency curves) and `StudyE8-device-warm` (the Jetson Orin keep-warm measurement) are now both committed, so the link is instantiated by direct measurement and the sweep proceeds. Stage B's mechanism verification was recorded in `results/orchestration/study_e6b/e6b_stageb_mechanism_verification.md` **before any Stage B number was computed**; the Stage B row amendment in `research/EXPERIMENTS.md` carries the same date.

**Still an offline replay of committed results.** CPU only on the flash host: no GPU, no model server, no inference. Script: `experiments/orchestration/study_e6b_stageb.py`. Results: `results/orchestration/study_e6b/e6b_stageb_results.json`. Stage A's `e6b_results.json` is **not rewritten**; every Stage A number above stands exactly as committed.

## 18. Stage B flags (read first)

1. **Device-warm D2 is the first device state on this workload that is both accurate and fast enough to matter.** It answers at 0.3087 accuracy — against 0.1538 for the best short window — in 1.3734 s at a 10 k-token history, where the same history answered **cold** costs 20.554 s. That ratio is the whole of Stage B.
2. **P2 (always-warm device) beats P1, and the entire margin is on outage questions.** Outdoor-driving, 13.6 Mbit/s, 5 s: P2 − P1 = **+0.0172** [+0.008, +0.028]; on connected questions the two policies are identical by construction, and on outage questions utility goes 0.1520 → 0.2754.
3. **The device cannot keep up with its own frame stream, and that caps the gain.** StudyE8 measured append latency crossing the 2 s D2 cadence at 15,069 tokens ≈ 334 s into a session. Replaying that exactly, the device's held history is current to within one frame on only **55.4 %** of questions (ingest lag p50 2 s, p90 21 s, max 321 s). The primary analysis lets the warm arm answer only when that lag ≤ 2 s.
4. **P3 (connectivity-aware) does not beat P2; it buys energy, not utility.** At the same cell P3 − P2 = -0.0072 [-0.014, -0.001] while keeping warm only 91 % of the time (4.76 Wh/h against P2's 5.21).
5. **The pre-registered θ grid was degenerate and had to be replaced — this is reported, not hidden.** On these traces an outage occurs *somewhere* in the next 30–120 s in 95.6–99.8 % of seconds, so the predicted risk sits at 0.95–1.00 and every absolute threshold in the pre-registered grid {0.05, 0.10, 0.20, 0.40} means *always warm*, making P3 identical to P2 by construction. θ is therefore taken at fixed quantile levels of the predictor's own risk distribution {0, 0.25, 0.50, 0.75, 0.90}. §23 gives the full grid.
6. **Predictability is not the binding constraint; the warm-up cost is.** P3-noncausal, which is handed the true future, scores 0.3840 against causal P3's 0.3770 — a gap of +0.0069. Irish outages have p50 **1 s** and max 3 s (Stage A §4), while turning the device warm mid-session costs a full cold prefill of the history it then holds — 20.554 s at 10 k tokens. No predictor can warm a device in time for a 1-second gap.
7. **Negative controls both pass.** (a) At outage fraction 0, P3's warm fraction is 0.000000 and P2 = P3 = P1 exactly. (b) Replacing the device-warm letters with the short-window letters collapses the P2 margin to +0.000000 — the gain is the warm state's **accuracy**, not its speed and not the scheduling.

## 19. The four configurations Stage A listed as PENDING

| configuration | accuracy source | n available | accuracy if always delivered | latency source |
|---|---|---|---|---|
| `cl-4B-D2-cold` | StudyE7 Job A letters (839) | 839 | 0.3087 | StudyE7 Job B 4B/images/COLD total curve |
| `cl-4B-D2-warm` | StudyE7 Job A letters | 605 | 0.2843 | StudyE7 Job B 4B/images/WARM ttft vs uncached tokens (R^2 0.325 - FLAGGED, weakest curve in the study) |
| `dev-4B-D2-cold` | StudyE7 Job A letters (parity StudyE8 Part D cold 27/27) | 839 | 0.3087 | StudyE8 Part B cold curve on the device |
| `dev-4B-D2-warm` | StudyE7 Job A letters (parity StudyE8 Part D warm 68/68) | 839 | 0.3087 | StudyE8 Part A warm-question curve at the history the device actually holds |

**Comparison match statements.** `cl-4B-D2-*` and `cl-32B-D2-*` read the **identical input** — StudyE7 Job A replayed StudyRH4's `body()` for cell D2 unchanged and its vLLM prompt tokens equal RH4's on 839/839 — on the same stack (vLLM 0.31.0) with the same greedy decoding, so 4B vs 32B on D2 is `IDENTICAL_INPUT`. The **device** D2 arms carry the same letters as the cloud 4B D2 arm; StudyE8 Part D measured the device's own letters against the H100's on byte-identical bodies (`body_sha256` matched 74/74) and found **68/68 agreement warm and 27/27 cold**, so this is a measured-parity proxy, not an assumed one. Its scope is the 74 archive questions, not all 845, and that is the proxy's limit (§26 check 6). Device *latency* is the Orin's own throughout; cloud latency is the H100's.

**Device cost curves actually used** (StudyE8 raw rows, binned-median interpolation, never pooled across cache state):

| history tokens | append (keep-warm) total | warm question total | cold question total |
|---|---|---|---|
| 1,000 | — | 0.467 s | 3.645 s |
| 5,000 | 0.784 s | 0.872 s | 9.761 s |
| 10,000 | 1.379 s | 1.373 s | 20.554 s |
| 15,000 | 1.946 s | 1.972 s | 32.834 s |
| 25,000 | 3.103 s | 3.053 s | 61.328 s |
| 45,000 | — | 5.484 s | 131.204 s |

Measured token ranges: append 534–52,059, warm question 2,539–52,048, cold question 761–52,127.

## 20. The keep-warm model, and the one methodological choice in it

A device holding a D2 history warm must ingest one 352×256 frame every 2 s. StudyE8 measured that each append evaluates a constant 95 tokens but still attends over the whole cached KV, so append latency grows with the history and crosses the 2 s cadence at 15,069 tokens. Stage B replays this exactly: appends are served FIFO at the measured cost, a device that turns warm mid-session first pays StudyE8 Part B's **cold prefill of the history it holds at that instant**, and the state it can answer from is whatever it has actually ingested.

**The choice.** Past the crossover the device falls behind, so its held history is older than the question — but the only letters available are StudyE7's, scored on the *full* history. Two readings are therefore reported, and the primary is the conservative one:

- **PRIMARY** — the warm arm may answer only when its ingest lag ≤ 2 s (one frame), i.e. when the state it holds is the state the letters describe.
- **OPTIMISTIC (labelled)** — the warm arm answers whenever it is warm, scoring the full-history letters against a stale history. This is an upper bound and is never used for a conclusion.

| regime | uplink | deadline | ready (lag ≤ 2 s) | warm at all | lag p50 | lag p90 | lag max | P2 primary | P2 optimistic |
|---|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 13.6 Mbit/s | 2 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.0422 | 0.0459 |
| outdoor_driving | 13.6 Mbit/s | 5 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.3842 | 0.3895 |
| synthetic_10pct | 13.6 Mbit/s | 2 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.0333 | 0.0359 |
| synthetic_10pct | 13.6 Mbit/s | 5 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.3891 | 0.3926 |
| synthetic_30pct | 13.6 Mbit/s | 2 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.0830 | 0.0908 |
| synthetic_30pct | 13.6 Mbit/s | 5 s | 0.554 | 0.993 | 2 s | 21 s | 321 s | 0.3651 | 0.3759 |

**A second choice, also reported both ways.** The pre-registration says P2 takes *"the faster-deliverable of cloud and device-warm"* when the cloud is unreachable. Read literally — lower latency wins even when both options meet the deadline — the policy prefers a 0.55 s short-window answer at 0.154 accuracy over a 1.4 s warm-D2 answer at 0.309, which is not a policy anyone would deploy and would make P2 ≈ P1 by construction. The primary rule is therefore: among device options that **meet the deadline**, take the one with the higher **training-fold** utility (cross-fitted over trace offsets, 5 folds, seed 0 — the same construction Stage A used to pick P1's device fallback, and causal: no per-question peeking). The literal reading is reported beside it in every results table as `P2 literal`.

## 21. Stage B results — all regimes, STREAM, PNG, uplink 13.6 Mbit/s

**Deadline 1 s**

| regime | reachable | best static | P1 | P2 | P2 literal | P3 | P3-noncausal | oracle (no keep-warm) | oracle keep-warm |
|---|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 0.8610 | 0.1538 | 0.0230 | **0.0230** | 0.0270 | 0.0230 | 0.0230 | 0.3382 | 0.3483 |
| indoor | 0.9938 | 0.1542 | 0.0033 | **0.0033** | 0.0035 | 0.0033 | 0.0033 | 0.3679 | 0.3684 |
| synthetic_0pct | 1.0000 | 0.1550 | 0.0024 | **0.0024** | 0.0024 | 0.0024 | 0.0024 | 0.3692 | 0.3692 |
| synthetic_2pct | 0.9801 | 0.1538 | 0.0050 | **0.0050** | 0.0054 | 0.0050 | 0.0050 | 0.3646 | 0.3662 |
| synthetic_5pct | 0.9520 | 0.1538 | 0.0092 | **0.0092** | 0.0104 | 0.0092 | 0.0092 | 0.3577 | 0.3617 |
| synthetic_10pct | 0.8967 | 0.1538 | 0.0174 | **0.0174** | 0.0209 | 0.0174 | 0.0174 | 0.3456 | 0.3553 |
| synthetic_20pct | 0.7986 | 0.1538 | 0.0311 | **0.0311** | 0.0370 | 0.0311 | 0.0311 | 0.3240 | 0.3408 |
| synthetic_30pct | 0.7053 | 0.1538 | 0.0469 | **0.0469** | 0.0550 | 0.0469 | 0.0469 | 0.3026 | 0.3267 |

**Deadline 2 s**

| regime | reachable | best static | P1 | P2 | P2 literal | P3 | P3-noncausal | oracle (no keep-warm) | oracle keep-warm |
|---|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 0.8610 | 0.2599 | 0.0251 | **0.0422** | 0.0291 | 0.0351 | 0.0420 | 0.5224 | 0.5414 |
| indoor | 0.9938 | 0.3233 | 0.0057 | **0.0062** | 0.0059 | 0.0057 | 0.0058 | 0.5798 | 0.5805 |
| synthetic_0pct | 1.0000 | 0.3254 | 0.0047 | **0.0047** | 0.0047 | 0.0047 | 0.0047 | 0.5822 | 0.5822 |
| synthetic_2pct | 0.9801 | 0.3144 | 0.0073 | **0.0104** | 0.0078 | 0.0073 | 0.0074 | 0.5733 | 0.5765 |
| synthetic_5pct | 0.9520 | 0.2974 | 0.0114 | **0.0175** | 0.0125 | 0.0114 | 0.0127 | 0.5631 | 0.5700 |
| synthetic_10pct | 0.8967 | 0.2692 | 0.0196 | **0.0333** | 0.0231 | 0.0267 | 0.0275 | 0.5375 | 0.5527 |
| synthetic_20pct | 0.7986 | 0.2425 | 0.0328 | **0.0544** | 0.0388 | 0.0544 | 0.0543 | 0.4970 | 0.5243 |
| synthetic_30pct | 0.7053 | 0.2120 | 0.0486 | **0.0830** | 0.0567 | 0.0830 | 0.0830 | 0.4595 | 0.4995 |

**Deadline 5 s**

| regime | reachable | best static | P1 | P2 | P2 literal | P3 | P3-noncausal | oracle (no keep-warm) | oracle keep-warm |
|---|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 0.8610 | 0.3385 | 0.3670 | **0.3842** | 0.3710 | 0.3770 | 0.3840 | 0.5932 | 0.6095 |
| indoor | 0.9938 | 0.3926 | 0.4020 | **0.4025** | 0.4021 | 0.4020 | 0.4021 | 0.6530 | 0.6537 |
| synthetic_0pct | 1.0000 | 0.3953 | 0.4036 | **0.4036** | 0.4036 | 0.4036 | 0.4036 | 0.6556 | 0.6556 |
| synthetic_2pct | 0.9801 | 0.3872 | 0.3981 | **0.4012** | 0.3985 | 0.3981 | 0.3982 | 0.6466 | 0.6496 |
| synthetic_5pct | 0.9520 | 0.3758 | 0.3909 | **0.3970** | 0.3921 | 0.3909 | 0.3922 | 0.6354 | 0.6415 |
| synthetic_10pct | 0.8967 | 0.3537 | 0.3754 | **0.3891** | 0.3789 | 0.3825 | 0.3833 | 0.6099 | 0.6236 |
| synthetic_20pct | 0.7986 | 0.3145 | 0.3499 | **0.3715** | 0.3559 | 0.3715 | 0.3714 | 0.5689 | 0.5925 |
| synthetic_30pct | 0.7053 | 0.2799 | 0.3307 | **0.3651** | 0.3388 | 0.3651 | 0.3651 | 0.5323 | 0.5667 |

**Deadline 10 s**

| regime | reachable | best static | P1 | P2 | P2 literal | P3 | P3-noncausal | oracle (no keep-warm) | oracle keep-warm |
|---|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 0.8610 | 0.3467 | 0.3670 | **0.3842** | 0.3710 | 0.3770 | 0.3840 | 0.6016 | 0.6137 |
| indoor | 0.9938 | 0.4021 | 0.4022 | **0.4027** | 0.4024 | 0.4022 | 0.4023 | 0.6580 | 0.6584 |
| synthetic_0pct | 1.0000 | 0.4047 | 0.4036 | **0.4036** | 0.4036 | 0.4036 | 0.4036 | 0.6604 | 0.6604 |
| synthetic_2pct | 0.9801 | 0.3958 | 0.3981 | **0.4012** | 0.3985 | 0.3981 | 0.3982 | 0.6522 | 0.6543 |
| synthetic_5pct | 0.9520 | 0.3852 | 0.3909 | **0.3970** | 0.3921 | 0.3909 | 0.3922 | 0.6417 | 0.6459 |
| synthetic_10pct | 0.8967 | 0.3618 | 0.3754 | **0.3891** | 0.3789 | 0.3825 | 0.3833 | 0.6192 | 0.6279 |
| synthetic_20pct | 0.7986 | 0.3226 | 0.3499 | **0.3715** | 0.3559 | 0.3715 | 0.3714 | 0.5809 | 0.5964 |
| synthetic_30pct | 0.7053 | 0.2863 | 0.3307 | **0.3651** | 0.3388 | 0.3651 | 0.3651 | 0.5467 | 0.5698 |

Paired contrasts (video-and-offset bootstrap, 2,000 resamples, seed 0), uplink 13.6 Mbit/s:

| regime | deadline | P2 − P1 | P3 − P1 | P3 − P2 | P2 − best static |
|---|---|---|---|---|---|
| outdoor_driving | 2 s | +0.0172 [+0.008, +0.028] | +0.0100 [+0.002, +0.018] | -0.0072 [-0.014, -0.001] | -0.2177 [-0.254, -0.183] |
| outdoor_driving | 5 s | +0.0172 [+0.008, +0.028] | +0.0100 [+0.002, +0.018] | -0.0072 [-0.014, -0.001] | +0.0457 [+0.029, +0.063] |
| indoor | 2 s | +0.0005 [-0.001, +0.003] | +0.0000 [+0.000, +0.000] | -0.0005 [-0.003, +0.001] | -0.3171 [-0.349, -0.285] |
| indoor | 5 s | +0.0005 [-0.001, +0.003] | +0.0000 [+0.000, +0.000] | -0.0005 [-0.003, +0.001] | +0.0099 [-0.003, +0.024] |
| synthetic_0pct | 2 s | +0.0000 [+0.000, +0.000] | +0.0000 [+0.000, +0.000] | +0.0000 [+0.000, +0.000] | -0.3207 [-0.353, -0.289] |
| synthetic_0pct | 5 s | +0.0000 [+0.000, +0.000] | +0.0000 [+0.000, +0.000] | +0.0000 [+0.000, +0.000] | +0.0083 [-0.005, +0.021] |
| synthetic_2pct | 2 s | +0.0031 [+0.000, +0.008] | +0.0000 [+0.000, +0.000] | -0.0031 [-0.008, +0.000] | -0.3040 [-0.337, -0.273] |
| synthetic_2pct | 5 s | +0.0031 [+0.000, +0.008] | +0.0000 [+0.000, +0.000] | -0.0031 [-0.008, +0.000] | +0.0140 [+0.001, +0.028] |
| synthetic_5pct | 2 s | +0.0061 [+0.000, +0.013] | +0.0000 [+0.000, +0.000] | -0.0061 [-0.013, +0.000] | -0.2799 [-0.314, -0.248] |
| synthetic_5pct | 5 s | +0.0061 [+0.000, +0.013] | +0.0000 [+0.000, +0.000] | -0.0061 [-0.013, +0.000] | +0.0212 [+0.007, +0.036] |
| synthetic_10pct | 2 s | +0.0137 [+0.005, +0.024] | +0.0071 [+0.000, +0.014] | -0.0066 [-0.014, -0.001] | -0.2359 [-0.271, -0.201] |
| synthetic_10pct | 5 s | +0.0137 [+0.005, +0.024] | +0.0071 [+0.000, +0.014] | -0.0066 [-0.014, -0.001] | +0.0354 [+0.019, +0.052] |
| synthetic_20pct | 2 s | +0.0215 [+0.009, +0.034] | +0.0215 [+0.009, +0.034] | +0.0000 [+0.000, +0.000] | -0.1881 [-0.224, -0.154] |
| synthetic_20pct | 5 s | +0.0215 [+0.009, +0.034] | +0.0215 [+0.009, +0.034] | +0.0000 [+0.000, +0.000] | +0.0570 [+0.039, +0.075] |
| synthetic_30pct | 2 s | +0.0344 [+0.019, +0.049] | +0.0344 [+0.019, +0.049] | +0.0000 [+0.000, +0.000] | -0.1289 [-0.166, -0.093] |
| synthetic_30pct | 5 s | +0.0344 [+0.019, +0.049] | +0.0344 [+0.019, +0.049] | +0.0000 [+0.000, +0.000] | +0.0851 [+0.064, +0.106] |

Per-configuration utility of the four new arms (uplink 13.6 Mbit/s, outdoor-driving):

| deadline | `cl-4B-D2-cold` | `cl-4B-D2-warm` | `dev-4B-D2-cold` | `dev-4B-D2-warm` | `dev-4B-SHORT-N1` | `dev-4B-RECENT` |
|---|---|---|---|---|---|---|
| 1 s | 0.1330 | 0.1291 | 0.0000 | 0.1053 | 0.1538 | 0.0000 |
| 2 s | 0.2290 | 0.1671 | 0.0000 | 0.1953 | 0.1538 | 0.0000 |
| 5 s | 0.2487 | 0.1673 | 0.0118 | 0.1953 | 0.1538 | 0.0012 |
| 10 s | 0.2487 | 0.1673 | 0.0698 | 0.1953 | 0.1538 | 0.0071 |

## 22. Where the P2 − P1 difference comes from

| regime | deadline | n connected | P1 | P2 | n outage | P1 | P2 | share of the margin from outage questions |
|---|---|---|---|---|---|---|---|---|
| outdoor_driving | 2 s | 14551 | 0.0046 | 0.0046 | 2349 | 0.1520 | 0.2754 | 100 % |
| outdoor_driving | 5 s | 14551 | 0.4018 | 0.4018 | 2349 | 0.1520 | 0.2754 | 100 % |
| indoor | 2 s | 16795 | 0.0048 | 0.0048 | 105 | 0.1524 | 0.2381 | 100 % |
| indoor | 5 s | 16795 | 0.4035 | 0.4035 | 105 | 0.1524 | 0.2381 | 100 % |
| synthetic_0pct | 2 s | 16900 | 0.0047 | 0.0047 | 0 | — | — | — |
| synthetic_0pct | 5 s | 16900 | 0.4036 | 0.4036 | 0 | — | — | — |
| synthetic_2pct | 2 s | 16563 | 0.0048 | 0.0048 | 337 | 0.1335 | 0.2878 | 100 % |
| synthetic_2pct | 5 s | 16563 | 0.4035 | 0.4035 | 337 | 0.1335 | 0.2878 | 100 % |
| synthetic_5pct | 2 s | 16089 | 0.0045 | 0.0045 | 811 | 0.1480 | 0.2750 | 100 % |
| synthetic_5pct | 5 s | 16089 | 0.4031 | 0.4031 | 811 | 0.1480 | 0.2750 | 100 % |
| synthetic_10pct | 2 s | 15154 | 0.0049 | 0.0049 | 1746 | 0.1472 | 0.2795 | 100 % |
| synthetic_10pct | 5 s | 15154 | 0.4017 | 0.4017 | 1746 | 0.1472 | 0.2795 | 100 % |
| synthetic_20pct | 2 s | 13497 | 0.0042 | 0.0042 | 3403 | 0.1463 | 0.2533 | 100 % |
| synthetic_20pct | 5 s | 13497 | 0.4013 | 0.4013 | 3403 | 0.1463 | 0.2533 | 100 % |
| synthetic_30pct | 2 s | 11920 | 0.0044 | 0.0044 | 4980 | 0.1542 | 0.2711 | 100 % |
| synthetic_30pct | 5 s | 11920 | 0.4044 | 0.4044 | 4980 | 0.1542 | 0.2711 | 100 % |

On connected questions P1 and P2 are **identical by construction** — both serve the cloud arm E6(a)'s rule picks — so every difference in the table is an outage-question difference, and the share column is 100 % wherever it is defined. Where the regime has no outage seconds the margin is exactly zero and the share is undefined.

## 23. The θ grid, and what P3 actually buys

The pre-registered absolute grid {0.05, 0.10, 0.20, 0.40} is below the predictor's entire support: the label it predicts — *is there an outage second anywhere in the next H seconds* — has a base rate of 0.956 (synthetic 10 %, H = 30 s) to 0.998, because outages are frequent and short. Every absolute θ in that grid therefore means *always warm*. θ is taken instead at fixed quantile levels of the predictor's own risk, so the grid spans warm fractions from ≈ 0.10 to 1.00. The levels are constants; only the level → threshold calibration uses the pooled predictions, and **which** level is used is cross-fitted by trace session (5 folds, seed 0).

Training grid, outdoor-driving, 13.6 Mbit/s, 5 s, fold 0:

| H | quantile level | training utility | warm fraction |
|---|---|---|---|
| 30 s | 0.00 | 0.3828 | 1.000 |
| 30 s | 0.25 | 0.3681 | 0.776 |
| 30 s | 0.50 | 0.3666 | 0.550 |
| 30 s | 0.75 | 0.3662 | 0.287 |
| 30 s | 0.90 | 0.3662 | 0.113 |
| 60 s | 0.00 | 0.3828 | 1.000 |
| 60 s | 0.25 | 0.3702 | 0.784 |
| 60 s | 0.50 | 0.3666 | 0.557 |
| 60 s | 0.75 | 0.3663 | 0.283 |
| 60 s | 0.90 | 0.3661 | 0.110 |
| 120 s | 0.00 | 0.3828 | 1.000 |
| 120 s | 0.25 | 0.3702 | 0.784 |
| 120 s | 0.50 | 0.3666 | 0.557 |
| 120 s | 0.75 | 0.3663 | 0.283 |
| 120 s | 0.90 | 0.3661 | 0.110 |

Fold 0 selects H = 30 s at quantile level 0.00 (θ = 0.9560), warm fraction 1.000. The selection criterion is the cheapest schedule whose **training** utility is within 1 pp of the best — the only criterion under which the pre-registered decision rule (*matches P2 within 1 pp at lower energy*) can discriminate at all; a utility-only fit always returns "always warm" and is recorded beside each pick as `utility_only_fit`.

| regime | deadline | P3 warm fraction | P3-noncausal warm fraction | P3 Wh/h | P2 Wh/h | P3 − P2 utility | P3-noncausal − P3 |
|---|---|---|---|---|---|---|---|
| outdoor_driving | 2 s | 0.914 | 1.000 | 4.762 | 5.209 | -0.0072 [-0.014, -0.001] | +0.0069 |
| outdoor_driving | 5 s | 0.914 | 1.000 | 4.762 | 5.209 | -0.0072 [-0.014, -0.001] | +0.0069 |
| indoor | 2 s | 0.055 | 0.017 | 0.284 | 5.209 | -0.0005 [-0.003, +0.001] | +0.0001 |
| indoor | 5 s | 0.055 | 0.017 | 0.284 | 5.209 | -0.0005 [-0.003, +0.001] | +0.0001 |
| synthetic_0pct | 2 s | 0.000 | 0.000 | 0.000 | 5.209 | +0.0000 [+0.000, +0.000] | +0.0000 |
| synthetic_0pct | 5 s | 0.000 | 0.000 | 0.000 | 5.209 | +0.0000 [+0.000, +0.000] | +0.0000 |
| synthetic_2pct | 2 s | 0.086 | 0.434 | 0.449 | 5.209 | -0.0031 [-0.008, +0.000] | +0.0001 |
| synthetic_2pct | 5 s | 0.086 | 0.434 | 0.449 | 5.209 | -0.0031 [-0.008, +0.000] | +0.0001 |
| synthetic_5pct | 2 s | 0.096 | 0.760 | 0.502 | 5.209 | -0.0061 [-0.013, +0.000] | +0.0013 |
| synthetic_5pct | 5 s | 0.096 | 0.760 | 0.502 | 5.209 | -0.0061 [-0.013, +0.000] | +0.0013 |
| synthetic_10pct | 2 s | 0.827 | 0.956 | 4.306 | 5.209 | -0.0066 [-0.014, -0.001] | +0.0008 |
| synthetic_10pct | 5 s | 0.827 | 0.956 | 4.306 | 5.209 | -0.0066 [-0.014, -0.001] | +0.0008 |
| synthetic_20pct | 2 s | 1.000 | 1.000 | 5.209 | 5.209 | +0.0000 [+0.000, +0.000] | -0.0001 |
| synthetic_20pct | 5 s | 1.000 | 1.000 | 5.209 | 5.209 | +0.0000 [+0.000, +0.000] | -0.0001 |
| synthetic_30pct | 2 s | 1.000 | 1.000 | 5.209 | 5.209 | +0.0000 [+0.000, +0.000] | +0.0000 |
| synthetic_30pct | 5 s | 1.000 | 1.000 | 5.209 | 5.209 | +0.0000 [+0.000, +0.000] | +0.0000 |

## 24. Keep-warm costs

**Device energy.** StudyE8 Part C measured a board power of 15.14 W while keeping a D2 history warm at the 2 s cadence against 9.94 W loaded-idle: a delta of **5.2087 W**, i.e. 5.21 Wh per warm-hour. P1 pays 0, P2 pays it continuously, P3 pays it for its warm fraction.

**Flagged, and it biases against the conclusion reached below:** StudyE8 did not measure power during a Part B *cold* prefill, so P3's warm-up is charged at the same 5.21 W delta. P3's energy is therefore a **lower bound**; warm-ups account for 9.6 % of its warm time in this cell.

**Uplink.** Unchanged from Stage A — the device streams the cloud arm's frames whether or not it also holds a local history, so keeping warm adds no uplink bytes:

| representation | MB per hour (PNG, STREAM) |
|---|---|
| D2 | 251.7 |
| RECENT | 994.7 |
| RICH | 503.4 |
| U | 1,498.1 |

**Cloud warm-session seconds.** The `cl-*-D2-warm` arms assume a session held on the server between questions. No capacity limit is modelled and none is implied: StudyRH5 and StudyRH8 are the capacity studies, and nothing here says how many such sessions a server can hold.

## 25. The pre-registered decision rule

> Pre-registered: the keep-warm decision is NON-TRIVIAL if P3 matches P2's utility (difference CI within +/-1 pp) at significantly lower device energy, or beats P1 with a CI excluding 0, in at least one pre-specified cell (outdoor-driving or synthetic >= 5%, uplink 13.6 Mbit/s, deadline 2 or 5 s). If P2 = P1 everywhere, device-warm has no value on this workload. If P3 = P2 at equal energy, the decision is a static rule.

| cell | P2 − P1 | P3 − P1 | P3 − P2 | P3 Wh/h vs P2 | matches P2 within ±1 pp? | strictly cheaper? | beats P1? | **non-trivial?** |
|---|---|---|---|---|---|---|---|---|
| outdoor_driving, 2s | +0.0172 [+0.008, +0.028] | +0.0100 [+0.002, +0.018] | -0.0072 [-0.014, -0.001] | 4.76 vs 5.21 | no | yes | yes | **YES** |
| outdoor_driving, 5s | +0.0172 [+0.008, +0.028] | +0.0100 [+0.002, +0.018] | -0.0072 [-0.014, -0.001] | 4.76 vs 5.21 | no | yes | yes | **YES** |
| synthetic_5pct, 2s | +0.0061 [+0.000, +0.013] | +0.0000 [+0.000, +0.000] | -0.0061 [-0.013, +0.000] | 0.50 vs 5.21 | no | yes | no | **no** |
| synthetic_5pct, 5s | +0.0061 [+0.000, +0.013] | +0.0000 [+0.000, +0.000] | -0.0061 [-0.013, +0.000] | 0.50 vs 5.21 | no | yes | no | **no** |
| synthetic_10pct, 2s | +0.0137 [+0.005, +0.024] | +0.0071 [+0.000, +0.014] | -0.0066 [-0.014, -0.001] | 4.31 vs 5.21 | no | yes | no | **no** |
| synthetic_10pct, 5s | +0.0137 [+0.005, +0.024] | +0.0071 [+0.000, +0.014] | -0.0066 [-0.014, -0.001] | 4.31 vs 5.21 | no | yes | no | **no** |
| synthetic_20pct, 2s | +0.0215 [+0.009, +0.034] | +0.0215 [+0.009, +0.034] | +0.0000 [+0.000, +0.000] | 5.21 vs 5.21 | yes | no | yes | **YES** |
| synthetic_20pct, 5s | +0.0215 [+0.009, +0.034] | +0.0215 [+0.009, +0.034] | +0.0000 [+0.000, +0.000] | 5.21 vs 5.21 | yes | no | yes | **YES** |
| synthetic_30pct, 2s | +0.0344 [+0.019, +0.049] | +0.0344 [+0.019, +0.049] | +0.0000 [+0.000, +0.000] | 5.21 vs 5.21 | yes | no | yes | **YES** |
| synthetic_30pct, 5s | +0.0344 [+0.019, +0.049] | +0.0344 [+0.019, +0.049] | +0.0000 [+0.000, +0.000] | 5.21 vs 5.21 | yes | no | yes | **YES** |

**Verdict as pre-registered: the keep-warm decision IS non-trivial**, in 6 of 10 pre-specified cells: `outdoor_driving|13.6Mbps_44ms|STREAM|2s`, `outdoor_driving|13.6Mbps_44ms|STREAM|5s`, `synthetic_20pct|13.6Mbps_44ms|STREAM|2s`, `synthetic_20pct|13.6Mbps_44ms|STREAM|5s`, `synthetic_30pct|13.6Mbps_44ms|STREAM|2s`, `synthetic_30pct|13.6Mbps_44ms|STREAM|5s`.

**And the qualification that matters more than the verdict.** The rule has two clauses, and all 6 cells fire on the second one — *P3 beats P1 with a CI excluding 0* (6 cells) — while the first clause, *P3 matches P2 within ±1 pp at strictly lower energy*, is satisfied in **0** cells. The second clause is satisfied by the keep-warm **action**, not by the **timing** of it: in every one of those cells P2 beats or equals P3 (P3 − P2 is -0.0072 to +0.0000), and where P3 does equal P2 it does so by choosing to stay warm all the time. Read against the question Stage B was posed — *does deciding **when** to keep which tier warm improve timely correct answers* — the answer on this workload is **no**; what improves them is keeping the device warm at all, which is P2.

**The two pre-registered readings.** P2 = P1 everywhere: **no** — so device-warm does have value, and the question is only when to pay for it. P3 = P2 at equal energy — the pre-registered trigger for "the decision is a static rule" — holds in **4 of 10** cells `synthetic_20pct 2s`, `synthetic_20pct 5s`, `synthetic_30pct 2s`, `synthetic_30pct 5s`. In the remaining cells the energy is not equal, and there P3 trades utility away for it (outdoor-driving: warm 91 % of the time for -0.0072 utility). Either way no cell shows scheduling skill: see §23's noncausal column, where perfect foresight also chooses to stay warm.

## 26. Negative controls

**(a) Outage fraction 0.** Outage fraction 0 (synthetic_0pct): P3's warm fraction must go to ~0 and P2/P3 must equal P1, because the device is never the only node that can answer.

| cell | reachable | P1 | P2 | P3 | P3 warm fraction | abs(P2 − P1) | abs(P3 − P1) |
|---|---|---|---|---|---|---|---|
| 5Mbps_60ms, 1s | 1.0000 | 0.0024 | 0.0024 | 0.0024 | 0.000000 | 0.000000 | 0.000000 |
| 5Mbps_60ms, 2s | 1.0000 | 0.0047 | 0.0047 | 0.0047 | 0.000000 | 0.000000 | 0.000000 |
| 5Mbps_60ms, 5s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |
| 5Mbps_60ms, 10s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |
| 13.6Mbps_44ms, 1s | 1.0000 | 0.0024 | 0.0024 | 0.0024 | 0.000000 | 0.000000 | 0.000000 |
| 13.6Mbps_44ms, 2s | 1.0000 | 0.0047 | 0.0047 | 0.0047 | 0.000000 | 0.000000 | 0.000000 |
| 13.6Mbps_44ms, 5s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |
| 13.6Mbps_44ms, 10s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |
| 88Mbps_22ms, 1s | 1.0000 | 0.0024 | 0.0024 | 0.0024 | 0.000000 | 0.000000 | 0.000000 |
| 88Mbps_22ms, 2s | 1.0000 | 0.0047 | 0.0047 | 0.0047 | 0.000000 | 0.000000 | 0.000000 |
| 88Mbps_22ms, 5s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |
| 88Mbps_22ms, 10s | 1.0000 | 0.4036 | 0.4036 | 0.4036 | 0.000000 | 0.000000 | 0.000000 |

**PASS** on both conditions: warm fraction → 0 in every cell (yes), and P2 = P3 = P1 exactly (yes).

**(b) Device-warm accuracy replaced by the device short-window accuracy.** The warm arm keeps its latency, its schedule and its energy; only its letters are swapped for StudyF4's N = 1 letters. If the P2 margin is a warm-*state* effect it must collapse.

| regime | deadline | P2 − P1 | P2(control b) − P1 | collapse | P3(control b) − P1 |
|---|---|---|---|---|---|
| outdoor_driving | 2 s | +0.0172 | +0.000000 | 100.0 % | +0.000000 |
| outdoor_driving | 5 s | +0.0172 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_5pct | 2 s | +0.0061 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_5pct | 5 s | +0.0061 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_10pct | 2 s | +0.0137 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_10pct | 5 s | +0.0137 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_20pct | 2 s | +0.0215 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_20pct | 5 s | +0.0215 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_30pct | 2 s | +0.0344 | +0.000000 | 100.0 % | +0.000000 |
| synthetic_30pct | 5 s | +0.0344 | +0.000000 | 100.0 % | +0.000000 |

**PASS.** The margin collapses to zero in every cell with a non-zero margin: with short-window letters the warm arm is no better than the fallback it replaces, so P2 reduces to P1 exactly. The Stage B gain is the warm state's **accuracy**, not its latency and not the scheduling.

## 27. One instrumented video, with the warm state charged

Regime outdoor_driving, uplink 13.6Mbps_44ms, STREAM, png, deadline 5 s. Video `1001141161985610_start_0.0_end_599.99`, offset 0, trace session `6` from second 1,084, span 388 s, 66 outage seconds in the window. Device policy: P2 (always-warm from session second 0).

| question | t (s) | connected | lag (s) | history held (tok) | full history (tok) | past 2 s crossover | usable | device J charged |
|---|---|---|---|---|---|---|---|---|
| `B058EEFB45` | 236 | yes | 2 | 10,530 | 10,620 | no | **yes** | 1,229 |
| `42CFFFAF13` | 300 | yes | 2 | 13,410 | 13,500 | no | **yes** | 1,563 |
| `4DF0872F25` | 387 | **no** | 5 | 17,190 | 17,415 | yes | no | 2,016 |

Every charge for the first question (`B058EEFB45`, t = 236 s, connected):

| configuration | status | correct | upload s | compute s | total s | delivered | utility |
|---|---|---|---|---|---|---|---|
| `cl-4B-RECENT` | measured | no | 0.163 | 1.675 | 1.881 | yes | 0 |
| `cl-4B-RICH` | measured | yes | 0.082 | 1.593 | 1.719 | yes | 1 |
| `cl-4B-U` | measured | yes | 0.163 | 2.174 | 2.381 | yes | 1 |
| `cl-32B-RECENT` | measured | no | 0.163 | 3.728 | 3.935 | yes | 0 |
| `cl-32B-RICH` | measured | yes | 0.082 | 3.513 | 3.639 | yes | 1 |
| `cl-32B-U` | measured | yes | 0.163 | 5.337 | 5.543 | no | 0 |
| `cl-32B-D2-cold` | measured | yes | 0.082 | 2.578 | 2.704 | yes | 1 |
| `cl-32B-D2-warm` | COLD_FIRST_QUESTION | — | 0.082 | — | — | no | 0 |
| `dev-4B-SHORT-N1` | measured | no | 0.000 | 0.552 | 0.552 | yes | 0 |
| `dev-4B-SHORT-N3` | measured | no | 0.000 | 1.363 | 1.363 | yes | 0 |
| `dev-4B-SHORT-N9` | measured | no | 0.000 | 3.856 | 3.856 | yes | 0 |
| `dev-4B-RECENT` | measured | no | 0.000 | 17.079 | 17.079 | no | 0 |
| `cl-4B-D2-cold` | measured | yes | 0.082 | 0.899 | 1.025 | yes | 1 |
| `cl-4B-D2-warm` | COLD_FIRST_QUESTION | — | 0.082 | — | — | no | 0 |
| `dev-4B-D2-cold` | measured | yes | 0.000 | 22.460 | 22.460 | no | 0 |
| `dev-4B-D2-warm` | state_dependent | yes | 0.000 | 1.426 | 1.426 | yes | 1 |

## 28. Stage B results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.** Stage B recomputes Stage A's P1 from the same code path, the same E6(a) rule, the same alignment seed and the same bootstrap seed, so every P1 must reproduce the committed Stage A value exactly. The device-warm arm's accuracy must equal StudyE7's committed 4B D2 figure.

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| P1, all 16 cells at 13.6 Mbit/s, deadlines 2 and 5 s | max abs difference 0.000000000 | — | `e6b_results.json` (Stage A, committed) | 1.000000 | agree |
| device-warm D2 accuracy (always delivered) | 0.308701 | 0.308701 | StudyE7 Job A, paired 839 | 1.000000 | agree |
| device keep-warm power above idle | 5.2087 W | 5.2087 W | StudyE8 Part C | 1.000000 | agree |
| 2 s cadence crossover | 15,069 tok | 15,069 tok | StudyE8 Part C | 1.000000 | agree |
| device warm-vs-cold speed-up at a 45 k-token history | 23.9× | 27.0× (at 52 k) | StudyE8 Part D | 0.89 | agree |

**PASS.** Stage B reproduces every committed Stage A P1 to the last bit, so the two stages' policy contrasts are on one scale, and no ratio is near the 2× investigation gate. Stage B's `best_static` and `oracle_no_keepwarm` are **not** expected to equal Stage A's and are not compared: the static pool and the oracle's action set both gained the four new configurations, which is the point of Stage B.

**2. Physical plausibility.** The device answers a 10 k-token warm history in 1.373 s having evaluated only the question tail (~160–207 tokens, StudyE8 Part A), i.e. roughly 120–150 tok/s of *new* work on a Jetson Orin at 1.3 GHz — far below the 647 tok/s cold prefill StudyE8 measured on the same stack, as it must be, because the warm path still attends over the whole cached KV. The cold arm at the same history costs 20.554 s, a 15.0× ratio, bracketed by StudyE8's own matched measurement (16.0× median, 27.0× at 52 k). No rate anywhere in Stage B is faster than a committed curve, because no curve was refitted: the three device curves are binned-median interpolations of StudyE8's raw per-request rows. **PASS.**

**3. Distribution sanity.** The ingest lag is reported as a distribution, not a median: p50 2 s, p90 21 s, max 321 s on outdoor-driving at 5 s, which is the spread the 2 s crossover predicts and not a constant. The θ grid spans warm fractions 0.110–1.000 with training utilities that differ in the third decimal, so neither is degenerate. The one place a constant legitimately appears is negative control (a), where P2 − P1 and P3 − P1 are exactly 0 across every cell — that is the control succeeding, and §26 shows it is zero because the device is never reached for, not because the arm is missing. **PASS.**

**4. Definition audit.**

| object | definition in this run | matches prior? |
|---|---|---|
| D2 | StudyRH4 cell D2: 352×256 separate images at a fixed 2 s stride from session start, append-only, RH4's header and R1 question text | yes — StudyE7 replayed RH4's `body()` unchanged and matched prompt tokens on 839/839 |
| warm (cloud) | prefix cache on, cost charged against **uncached** tokens since the previous question | yes — same as Stage A's 32B warm arm |
| warm (device) | llama.cpp `cache_prompt` true with the KV prefix resident; answering costs the question tail only | yes — StudyE8's own definition, Part 0 verified reuse |
| cold (device) | `cache_prompt` false, reused = 0 | yes — StudyE8 Part B |
| warm fraction | share of session seconds the device holds the history warm, warm-up included | new in Stage B; defined here |
| utility | answer correct **and** delivered within the deadline | yes — Stage A's definition, unchanged |
| keep-warm energy | (board power while keeping warm − loaded idle) × warm seconds | yes — StudyE8 Part C's delta |

One name is used with two definitions across the repository and is flagged here rather than reconciled: **"cold device latency"** means StudyF4/StudyD4-orin's 560×560 short-window curve (≈1,261 ms per 1k tokens) in Stage A's `dev-4B-RECENT` arm and StudyE8 Part B's D2 curve (≈3,022 ms per 1k) in Stage B's `dev-4B-D2-cold` arm. StudyE8 §Part B investigated the 2.4× gap and attributed it to format and token range, not to a stack regression; the two arms are never pooled and never compared to each other here. **PASS with the flag.**

**5. Claim linkage.** Stage B bears on FORMULATION §Constraints 2 (serving feasibility within the latency SLO, or pay materialization first), §Constraints 3 (reachability) and §refresh (the physical component of Context Inertia). It **supports** the claim that warm state is a placement decision with a real price: holding a D2 history warm on the device is what converts outage questions from unanswerable into answerable, and it costs a measured 5.21 W. It **weakens** the stronger claim that the *timing* of that decision is itself a lever on this workload — §25. It does **not** speak to the coupling claim across a fleet (single-stream; StudyRH5/RH8 are the capacity studies), and it measures no cross-tier KV transfer, so §Scoping's KV-portability exclusion is respected: the device builds its own KV from frames it already has. **PASS with the scope note.**

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| device D2 *accuracy* = the H100 4B's letters | the cloud 4B's answers on byte-identical bodies | **valid, and measured**: StudyE8 Part D found 68/68 warm and 27/27 cold agreement with the device's own letters on `body_sha256`-matched inputs. Scope: 74 archive questions of 845, so the parity is measured on 8.8 % of the question set and assumed on the rest |
| device-warm *answer* latency = StudyE8 Part A's warm-question curve | the Orin answering a warm D2 history, measured | valid; the history token count is StudyE7's own per-question prompt tokens, not an estimate |
| P3 warm-up *energy* = Part C's keep-warm power | power during a cold prefill was never measured | **flagged**. Same hardware, same clocked prefill work, but it is an assumption; it makes P3's energy a lower bound, i.e. it favours P3, and §25's verdict is against P3 anyway |
| full-history letters scored against a *stale* warm history | the device's answer on the history it actually holds was never measured | **flagged, and the reason the primary analysis gates on a ≤ 2 s ingest lag.** The ungated reading is reported as `P2 optimistic` and is never used for a conclusion |
| 4B cloud WARM latency vs uncached tokens | a fit with R² 0.325 (StudyE7 Job B) | **flagged before the sweep** (Stage B mechanism verification, point 1). `cl-4B-D2-warm` is the weakest curve in the study; no Stage B verdict rests on it |

## 29. Stage B observations and interpretation

**Observations (data only).**

1. P2 beats P1 in every regime that has outages, and the margin scales with the outage fraction: +0.0061 [+0.000, +0.013] at synthetic 5 %, +0.0172 [+0.008, +0.028] on outdoor-driving (14.4 % outage), +0.0344 [+0.019, +0.049] at synthetic 30 %. At outage fraction 0 it is exactly 0.
2. The P2 − P1 margin is **identical at the 2 s and the 5 s deadline** in every regime (outdoor-driving: +0.0172 and +0.0172). The questions the warm arm wins are outage questions it answers in about a second, so loosening the deadline from 2 s to 5 s adds nothing to the margin — it only raises both policies' connected-question utility (0.0046 → 0.4018).
3. On outage questions alone, utility goes 0.1520 → 0.2754 on outdoor-driving — the device-warm arm roughly doubles what a device can answer during an outage. On connected questions P1 and P2 are identical by construction.
4. The device holds a history current to within one frame on only 55.4 % of questions, although it is warm on 99.3 %. Ingest lag p90 is 21 s and max 321 s.
5. P3 never beats P2 in any cell. It equals P2 exactly where it chooses to stay warm all the time (synthetic 20 % and 30 %, warm fraction 1.000), and it loses utility wherever it de-warms: outdoor-driving -0.0072 [-0.014, -0.001] at warm fraction 0.914, synthetic 5 % -0.0061 [-0.013, +0.000] at warm fraction 0.096.
6. P3-noncausal, handed the true future, chooses to be warm 100 % of the time on outdoor-driving and scores 0.3840 against P2's 0.3842 — it reproduces always-warm rather than improving on it.
7. The oracle gains from adding the keep-warm action: oracle without keep-warm 0.5932 against oracle with it 0.6095 (+0.0163); P2 realises 7 % of the oracle's headroom over P1.
8. Both negative controls pass exactly: (a) warm fraction 0.000000 and P2 = P3 = P1 to 0 at outage fraction 0; (b) with short-window letters the P2 margin is +0.000000.
9. Device-warm costs 5.21 W above loaded idle continuously under P2; P3's best schedule on outdoor-driving costs 4.76 Wh/h, a 9 % saving, for the -0.0072 utility it gives up.

**Interpretation (inference, labelled as such).**

- **The answer to Stage B's question is: keep it warm, don't schedule it.** Holding a D2 history warm on the device is worth real utility — it is the only device state on this workload that is both accurate enough and fast enough to answer during an outage — and every cell where that helps is an outage cell. But *deciding when* to hold it warm buys nothing: the best connectivity-aware schedule either collapses to always-warm, or loses utility in exchange for energy. The pre-registered rule fires on its second clause (P3 beats P1 with a CI excluding 0) in six cells, and that clause is satisfied by the keep-warm *action*, not by the *timing* of it — P2 beats P3 in all six.
- **The reason is a cost asymmetry the trace makes unarguable.** Irish 5G outages have a median length of 1 s and a maximum of 3 s (Stage A §4), while turning a cold device warm mid-session costs a full reconstruction of the history it then holds — 20.6 s at 10 k tokens and 61.3 s at 25 k. A policy cannot warm up inside a gap that is over before the prefill finishes, so the only schedules that keep the utility are the ones that were already warm, which is P2. P3-noncausal confirms this is not a prediction failure: given the true future it also chooses to stay warm.
- **Stage A's own prediction is confirmed, and this is worth recording.** §17 point 2, written before any Stage B number existed, said that if P3 ≈ P2 the reading would be that the decision is static and the trace's gap structure, not the predictor, would be the reason. That is exactly what the data show — with the refinement that P3 ≈ P2 only when P3 chooses warm fractions near 1; where it economises, it loses utility.
- **The device's throughput ceiling, not its accuracy, is what caps the gain.** The warm arm's letters are worth 0.3087 against the fallback's 0.1538, but the arm is only usable on 55 % of questions because StudyE8's measured append cost overtakes the 2 s frame cadence 334 s into a session. A device that could ingest its own stream would roughly double the P2 margin — the `P2 optimistic` column in §20 is that bound. Making keep-warm pay off on long sessions is an ingest-throughput problem, not a model problem.
- **What this does not show.** It does not show that keep-warm scheduling is worthless in general: these outages are short and frequent, and a regime with long, rare, predictable outages — which this repository has no trace of — is exactly where P3 would have something to schedule, and §23's grid shows P3 does track the knob it is given. It does not establish the device arm's accuracy beyond StudyE8 Part D's 74-question parity. And it says nothing about how many warm cloud sessions a server can hold; no capacity limit is modelled.

**CLAUDE.md Rule 2.** The component that behaves like a null — P3 not beating P2 — is a **real negative**, not inconclusive. Step 2 of the Stage B mechanism verification instantiated every link with a non-zero, varying quantity before the sweep; the keep-warm mechanism is present and demonstrably drives P2's gain (negative control (b) collapses it to zero); the scheduling knob is present and varies (§23's grid spans warm fractions 0.11–1.00); and the policy was given a non-causal upper bound that it reaches. The mechanism operated as specified and did not produce the claimed effect. The one caveat is scope, not design: this is a negative about *these* outage statistics.

## 30. Files

- `experiments/orchestration/study_e6b_traces.py`
- `experiments/orchestration/study_e6b_mobility.py`
- `experiments/orchestration/study_e6b_stageb.py`
- `experiments/orchestration/study_e6b_report.py`
- `results/orchestration/study_e6b/e6b_traces.npz`
- `results/orchestration/study_e6b/e6b_traces.json`
- `results/orchestration/study_e6b/e6b_results.json`
- `results/orchestration/study_e6b/e6b_mechanism_verification.md`
- `results/orchestration/study_e6b/e6b_stageb_results.json`
- `results/orchestration/study_e6b/e6b_stageb_mechanism_verification.md`
- `reports/study_e6b_mobility.md (this file)`
- `reports/study_e6_intervention.md (correction block prepended; body unchanged)`
- `reports/study_e4_counterfactual.md (correction block prepended; body unchanged)`

