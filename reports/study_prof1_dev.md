# StudyPROF1-dev: the DEV-only profile tables the policy reads

Pre-registered in `research/EXPERIMENTS.md` (StudyPROF1-dev) before anything was computed. CPU only on flash: no GPU, no model server, no inference. One artifact: `results/orchestration/prof1/profiles_dev.json`.

**The evidence rule this row enforces.** spec D6: every table is fitted on DEV only. Nexar DEV = the 90-clip DEV side of the pre-registered StudyD14b split; S-EMBER DEV = the 70-video DEV side of StudyB-baselines amendment 2. No EVAL clip or question is read by this file.

**Every entry carries a provenance kind, and the policy must treat them differently.**

| kind | meaning | how many entries |
|---|---|---|
| MEASURED | a committed measurement, cited | u_SH curves, all five RC tables, 7 duration families, connectivity, RTT |
| DERIVED RULE | arithmetic over committed measurements, stated, not itself a measurement | episodic end-to-end latency, catch-up per frame, D2 tokens per frame |
| ASSUMPTION | no measurement exists; declared so the policy can run | bandwidth as a constant, jitter absent |
| PROPOSAL | computed by a stated DEV rule, NOT yet approved | omega_k, the question-type to representation map, the affine utility scale |

---

## 1. u_SH: utility against delivered delay and frames

**The AP to utility mapping, stated.** IDENTITY: u_SH = StudyE9c challenge mAP, which is already bounded [0, 1]

StudyE9c's challenge AP is already a bounded [0, 1] quantity, so the primary mapping invents nothing. An affine alternative is also computed and marked PROPOSAL: AFFINE PROPOSAL: u = clip((AP - base) / (AP_zero_delay_cloud - base), 0, 1), with base = the challenge base rate averaged over horizons and AP_zero_delay_cloud = 32B N=1 at zero delay on DEV (base rate 0.4287, zero-delay cloud 0.6032). the affine map changes the scale on which omega_k trades SH against RC; it is a PROPOSAL and must be approved before use

DEV clips: 90. Cadence 0.5 s (the primary); the 1.0-s cadence is in the JSON.

| delivered delay d (s) | u_SH(cloud, d, m=1) | u_SH affine (proposal) | u_SH(cloud, d, m=3) |
|---|---|---|---|
| 0.00 | 0.6032 | 1.0000 | 0.6975 |
| 0.25 | 0.5623 | 0.7652 | 0.6400 |
| 0.50 | 0.5481 | 0.6842 | 0.6153 |
| 0.75 | 0.5447 | 0.6645 | 0.5907 |
| 1.00 | 0.5344 | 0.6057 | 0.5532 |
| 1.50 | 0.5161 | 0.5008 | 0.4923 |
| 2.00 | 0.4995 | 0.4057 | 0.4716 |
| 2.50 | 0.4745 | 0.2624 | 0.4181 |
| 3.00 | 0.4750 | 0.2649 | 0.4101 |

| u_SH(device) | cadence | hold shift | latency |
|---|---|---|---|
| **0.4922** (affine 0.3638) | 0.75 s | 0.75 s | 0.567 s |

**The device is overtaken by a cloud answer that is about 1.0 s stale.** Reading down the m = 1 column, the cloud's delivered utility falls below the device's 0.4922 between d = 1.0 s (0.5344) and d = 1.25 s, which is this row's version of StudyE9d's d*: beyond roughly a second of delivered delay a cloud answer is worth less than the device's own current one.

**The m = 3 column is marked DEV-OPTIMISTIC.** StudyFRAMES1 found NO measurable benefit from m = 3 on held-out clips and a negative point estimate once m = 3 pays its own upload, while the DEV curves here show a positive m = 3 effect at short delay. The m = 3 entries are therefore marked DEV-OPTIMISTIC: do not enable merging on them (spec 7.9's enabling condition).

## 2. RC: accuracy by question type, DEV videos only

S-EMBER DEV videos from StudyB-baselines amendment 2 (sember_split.py): 70 videos, 243 questions

All five tables are restricted to the same 243 DEV questions, one row per question (these files carry retry rows; counting them all would weight a question by how often it was retried).

| table | tier | representation | DEV n | DEV accuracy | source |
|---|---|---|---|---|---|
| `32B-RICH` | cloud | RICH | 243 | 0.4033 | StudyR1 cell K1 (32BI, RICH video) |
| `32B-RECENT` | cloud | RECENT | 243 | 0.3868 | StudyR1 cell K3 (32BI, RECENT video) |
| `32B-D2` | cloud | D2 | 243 | 0.4198 | StudyRH4 cell D2 (32BI, 2-s stride 352x256) |
| `4B-D2` | device-proxy | D2 | 243 | 0.3128 | StudyE7 Job A (4BI on RH4's D2 input) - DEVICE PROXY, not an Orin measurement |
| `device-N1-orin` | device | RECENT-1frame | 243 | 0.1276 | StudyF4 Part A, 1-frame last-3-s window, Jetson Orin |

**4B-D2 is the H100 4B standing in for the device (StudyD15 Part A rejected it as an exact numerical stand-in); device-N1-orin is the only true device measurement and uses a different input (1 frame, last 3 s), so the two are not interchangeable.**

### 2.1 The question-type to representation map (PROPOSAL)

Fitted on DEV by taking, per question type, the cloud representation with the highest DEV accuracy. It is a PROPOSAL because several cells are thin: a type with 25 DEV questions separates 0.40 from 0.44 by one question.

| question type | chosen representation | cloud accuracy | RICH | RECENT | D2 | device 4B-D2 | device minus cloud | thin cell |
|---|---|---|---|---|---|---|---|---|
| counting_objects_events | **RICH** | 0.2500 | 0.2500 (n=36) | 0.2500 (n=36) | 0.2222 (n=36) | 0.1667 | -0.0833 | no |
| location_trace | **D2** | 0.4828 | 0.3103 (n=29) | 0.4483 (n=29) | 0.4828 (n=29) | 0.2759 | -0.2069 | no |
| object_comparison | **RICH** | 0.3750 | 0.3750 (n=16) | 0.3750 (n=16) | 0.3750 (n=16) | 0.2500 | -0.1250 | yes |
| sequential_action | **D2** | 0.5556 | 0.5185 (n=27) | 0.4074 (n=27) | 0.5556 (n=27) | 0.4815 | -0.0741 | no |
| spatial_aware_reasoning | **RECENT** | 0.2800 | 0.2000 (n=25) | 0.2800 (n=25) | 0.2400 (n=25) | 0.2400 | -0.0400 | no |
| temporal_ordering_recognition | **RICH** | 0.5152 | 0.5152 (n=33) | 0.4242 (n=33) | 0.4848 (n=33) | 0.3333 | -0.1818 | no |
| time_duration | **D2** | 0.4359 | 0.3846 (n=39) | 0.3846 (n=39) | 0.4359 (n=39) | 0.3333 | -0.1026 | no |
| visual_detail_recall | **RICH** | 0.6053 | 0.6053 (n=38) | 0.5000 (n=38) | 0.5263 (n=38) | 0.3947 | -0.2105 | no |

The cloud beats the device proxy on every question type, by -0.2105 to -0.0400, which is the quantity spec 4.3's u_RC trades against readiness delay.

## 3. Class weights omega_k: COMPUTED, AND A PROPOSAL AWAITING APPROVAL

**The rule, stated before the numbers.** equalize the mean utility gain per eligible opportunity across classes at the stated operating point; omega_k = 1 / gain_k normalized to omega_SH = 1

**The operating point.** SH: 32B N=1 at setting (ii), cadence 0.5 s, hold shift 0.50 s, against the device arm at its own 0.75-s cadence, on DEV clips. RC: the DEV-chosen representation per question type against the 4B-D2 device answer, averaged over question types weighted by DEV question counts. SS: EXCLUDED: no committed SS accuracy pair exists on this workload

| class | mean gain per eligible opportunity at the operating point | omega_k |
|---|---|---|
| SH | 0.0559 challenge mAP | 1.000 (normalizing class) |
| RC | 0.1317 accuracy | **0.4246** |
| SS | not measured | null, not invented |

one point of RC accuracy is worth 0.425 points of SH challenge mAP at this operating point, so an unweighted coordinator would spend almost everything on whichever class is measured on the wider scale.

| question type | representation | cloud | device | gain | DEV n |
|---|---|---|---|---|---|
| visual_detail_recall | RICH | 0.6053 | 0.3947 | +0.2105 | 38 |
| location_trace | D2 | 0.4828 | 0.2759 | +0.2069 | 29 |
| temporal_ordering_recognition | RICH | 0.5152 | 0.3333 | +0.1818 | 33 |
| object_comparison | RICH | 0.3750 | 0.2500 | +0.1250 | 16 |
| time_duration | D2 | 0.4359 | 0.3333 | +0.1026 | 39 |
| counting_objects_events | RICH | 0.2500 | 0.1667 | +0.0833 | 36 |
| sequential_action | D2 | 0.5556 | 0.4815 | +0.0741 | 27 |
| spatial_aware_reasoning | RECENT | 0.2800 | 0.2400 | +0.0400 | 25 |

**This is a proposal, not a decision.** Two things about it need the user's eye: it is computed at ONE operating point (a 0.50 s delivered delay for SH), and it uses the 4B-D2 device proxy rather than an Orin measurement for the RC side. Both move the ratio. SS has no weight at all because no committed measurement gives an SS accuracy pair on this workload.

## 4. Durations

| entry | kind | value | source | StudyENG1 replaces it |
|---|---|---|---|---|
| episodic TTFT by N | MEASURED | 32B N=1 0.1422 s, N=3 0.2643 s at 25 % load (and 75 % in the JSON) | StudyD7b (N=1) and StudyD7 (N=3, N=9), open-loop TTFT p50 at 25 % and 75 % of peak load | yes |
| episodic end-to-end by N | DERIVED RULE | 32B N=1 0.3950 s, N=3 0.9304 s, 4B N=1 0.3355 s | RTT + frame bytes / uplink + TTFT, unrounded (StudyE9b setting (ii)) | yes |
| recall TTFT by readiness | MEASURED | 11k: GPU-warm 0.382 s, host-warm 0.459 s, cold 2.445 s; 28k: 0.874 / 1.001 / 7.367 s | StudyRH5 Part A, isolated reload, D2 format, one request at a time, TTFT medians | yes |
| cold rebuild per token | MEASURED | 11k 4500 tok/s, 28k 3800 tok/s | StudyRH5 cold re-prefill rates | yes |
| host reload per token | MEASURED | 262144 B per token at 47.6 / 52.9 GB/s, that is 5.51e-06 s per token | StudyRH5: 64 layers x 8 KV heads x 128 x {K,V} x bf16 per token, and vLLM's own load-time ... | yes |
| catch-up per frame | **DERIVED RULE** | 91 tokens per D2 frame (median), so 0.0163 s per frame on the 32B and 0.0031 s on the 4B | appending s seconds of D2 history is an incremental prefill of its tokens: t_catchup = (frames x tokens_per_frame) / prefill_tok_s. NO committed video... | yes |
| answer time by context | MEASURED | K1 RICH 12645 tokens, LM prefill 2.17 s, frontend 1.47 s PNG / 0.75 s JPEG / 0.04 s text, vision encoder 0.2 s | StudyE10d | yes |
| prefix-chained piece overhead | MEASURED | chain / monolithic 1.093 at n=1,024 and 0.990 at n=2,048; median per-link overhead +0.015 s and -0.004 s | StudySLICE1 Part A, 40 chains over RH4 D2 sessions | no, Part A measured it |
| episodic capacity | MEASURED | 2.69 req/s with no warm sessions, 1.34 req/s at k=4 (GPU) or k=8 (host) | StudyE10b | yes |
| device answer latency | MEASURED | 0.567 s | StudyD8 arm A | no |

**Catch-up is the one duration with no committed measurement in the video domain.** appending s seconds of D2 history is an incremental prefill of its tokens: t_catchup = (frames x tokens_per_frame) / prefill_tok_s. NO committed video-domain measurement of catch-up exists; StudyE32 measured catch-up on LoCoMo text conversations and its numbers are flagged in CLAUDE.md, so they are NOT used here.

## 5. The link model

| component | kind | value |
|---|---|---|
| connectivity | MEASURED | 16 outdoor-driving traces, 28551 trace-seconds, connected 0.8562 of the time, 3829 outages, p50 1 s, p90 1 s, p99 2 s, max 3 s, 8.05 outages per minute |
| bandwidth | **ASSUMPTION (single committed value, no measured distribution)** | 13.6 Mbit/s as a CONSTANT; percentiles NOT AVAILABLE from committed data |
| RTT | MEASURED | 0.044 s, a ROUND trip (the answer's downlink is already inside it) |
| jitter | **ASSUMPTION** | none: the delivery model is deterministic given the payload and the server TTFT, and every committed study uses it that way. A jitter term would have to be invented, so it is declared absent rather th... |

**The brief asked for committed bandwidth percentiles and they do not exist.** the committed traces carry CONNECTIVITY (1 bit per second), NOT a bandwidth time series, so no percentiles can be computed from them. The policy must treat bandwidth as a constant with an outage process on top, and spec 4's t_up = payload / b_i uses this constant.

## 6. Demand, and the spec 6.4 conditional-rate test

| quantity | value |
|---|---|
| DEV videos | 70 |
| DEV questions | 243 |
| questions per video | mean 3.47, p50 3, min 2, max 6 |
| arrival rate per video | mean 0.596 per minute, p50 0.537, IQR 0.420 to 0.749 |
| inter-arrival time | mean 105.0 s, p50 89.0 s, IQR 48.0 to 146.0 s |
| lambda_rc default | 0.00993 questions per second per device |

### 6.1 The conditional recall rate: NOT COMPUTABLE, so NOT USED

The test the user specified: on DEV, do S-EMBER recall questions arrive more often within W seconds of a device escalation episode than elsewhere, for W in 10, 30 and 60 s, with a rate ratio and a CI; if the CI includes 1 at every W, the conditional rate is not used.

**Status: NOT COMPUTABLE FROM COMMITTED DATA.** escalation episodes exist only on the Nexar dashcam traces (SH) and recall questions only on S-EMBER videos (RC); no committed trace carries both on the same stream, and the simulator's pairing of the two is a harness construction, so a test on it would measure our own generator

**Decision applied: the conditional recall rate is NOT USED, which is the action the user's rule prescribes when the CI includes 1 at every W, and which spec 6.4 already requires absent DEV support**

This is flagged rather than buried because it is a judgement: the user's rule covers the case where the CI includes 1, and this is the different case where no CI can be formed at all. The ACTION is the same under either reading and under spec 6.4's own wording, so the mechanism is left off; if you want it treated differently, say so and nothing else in this row changes. What would make it computable: one stream that carries both: a continuous SH task and timestamped recall questions on the same video, which no current dataset in this project provides.

## 7. Results consistency check, 6 of 6

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS, exactly.** Recomputing each recall table over ALL questions from the per-question files reproduces the committed `b_recall_accuracy.json` accuracies to **+0.0e+00 or better** on all 5 configs (32B-RICH 0.395266, 32B-RECENT 0.383432, 32B-D2 0.395709, 4B-D2 0.308701, device-N1 0.153846). The u_SH pipeline reproduces StudyE9c's all-300 references to 1 ulp (`results/dashcam/ctrl1/ctrl1_consistency.json`: -1.11e-16 and +5.55e-17). Every duration is quoted from a committed study rather than recomputed. |
| 2 | physical plausibility | **PASS.** The derived rules are checked against their own inputs: host reload at 5.51e-06 s per token times 11,000 tokens is 0.061 s, which sits between StudyRH5's measured host-warm TTFT (0.459 s) and its GPU-warm TTFT (0.382 s) as it must; catch-up at 0.0163 s per D2 frame times 30 frames (one minute of 2-s stride) is 0.49 s, consistent with the 32B's committed 5.6k tok/s prefill. No rate here is faster than a committed curve. |
| 3 | distribution sanity | **PASS.** Spread is reported wherever a median is: D2 tokens per frame (p25 / p50 / p75), outage lengths (p50 / p90 / p99 / max), questions per video, inter-arrival times, and per-category n on every RC cell with a thin-cell flag. |
| 4 | definition audit | **PASS.** `challenge mAP`, `cloud_delivered`, `held_stream`, the 0.25-s grid and setting (ii) are imported from StudyE9b / E9d. RICH, RECENT and D2 keep their committed definitions (StudyR1 K1 / K3, StudyRH4 D2). One name is used in two senses across the project and is disambiguated here: `device` means the 4B-D2 PROXY in the RC tables and the Orin measurement in `device-N1-orin`; both are listed separately and never averaged. |
| 5 | claim linkage | **PASS.** These tables are the inputs to spec 4 (utility), 6.4 (demand), 7 (decision procedures) and 9 (parameters). Nothing here is itself a claim; two entries WEAKEN mechanisms the spec carries as conditional: m = 3 utility (spec 7.9's merge rule) and the conditional recall rate (spec 6.4). |
| 6 | proxy validity | **PASS with three proxies declared.** (a) 4B-D2 is the H100 4B standing in for the device; StudyD15 Part A rejected it as an exact stand-in, so it is valid for ordering and first-order value only, and the one true device table (StudyF4 Orin, accuracy 0.1276 against the proxy's 0.3128) is carried beside it rather than merged. (b) bandwidth as a constant with an outage process on top, because the committed traces carry connectivity bits and not a bandwidth series. (c) D2 tokens per frame is an upper bound because prompt tokens include the question text. None is load-bearing for a headline claim: this row produces inputs, not conclusions. |

## 8. What the policy should and should not switch on

1. **Use** the u_SH curves, the RC tables, the durations and the connectivity process. They are measured, cited, and DEV-only.
2. **Do not use** omega_k, the representation map or the affine utility scale without approval: all three are PROPOSALS, and omega_k in particular sets how the coordinator trades a point of RC accuracy against a point of SH challenge mAP (0.425 at the stated operating point).
3. **Leave off** spec 7.9's merge rule (no measured m > 1 benefit; StudyFRAMES1) and spec 6.4's conditional recall rate (not computable).
4. **Treat as absent** any jitter model and any bandwidth distribution, and carry the ASSUMPTION label wherever the constant uplink is used.
5. **Expect StudyENG1 to replace** every duration marked `replace_with_eng1`, which is 8 of the 10 duration families; the two it does not touch are StudySLICE1 Part A's piece overhead and StudyD8's device answer latency.

## 9. Files

| file | what |
|---|---|
| `experiments/orchestration/prof1_profiles.py` | the builder, with every provenance kind in code |
| `results/orchestration/prof1/profiles_dev.json` | the single artifact the policy reads |
| `results/orchestration/prof1/prof1_consistency.json` | the exact reproduction of the committed recall tables behind check 1 |

