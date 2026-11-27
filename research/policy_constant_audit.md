# Policy constant audit: COVEX rung 3 and the step-1 stack (portability and deployability)

Scope: `covex-v6-fair-final` (rung 3) and the step-1 stack (`-la` load-aware arrival admission, `-la-er` with the release re-check; layer P = predictive belief; layer 0b = book belief). Read-only code reading at origin/main. No cells were run. Line numbers are from this checkout; "not traced" means the reader was not followed to a decision site.

Source-type key: MEASURED PROFILE, CALIBRATED FROM ERROR (formula given), DECLARED, READ LIVE FROM ENGINE/LINK, WITHIN-RUN ESTIMATOR, IMPOSED RULE.

Deployment axes: DS = dataset, TT = task type, DM = device model, CM = cloud model, GPU = GPU and memory, EN = serving engine, NW = network.

## Section 1: constant table

Decision-relevant rows (each has a read site in a decision). "Dev seeds" records what the code shows; "not verified" means the code does not say.

| name | value | defined at | read by (decision) | source type | evidence | axes | derivation rule in a new deployment | set on dev seeds |
|---|---|---|---|---|---|---|---|---|
| d162 INTERCEPT_S | 0.0677976 s | `live2/d162_price.py:46` | `live2/la_arrival_admission.py` (b7 arrival gate `est <= slack`, via `DP.first_token_s`); release re-check (`live2/release_recheck.py`, `coordinator.py:310-317`) | CALIBRATED FROM ERROR (gate fit) | `results/orchestration/live2/frozen_test/cost_model_gate_d162.json`, gate commit 68a2b47 | GPU, EN, CM, token length | refit the first-token gate on cells from the new stack, then re-pin the constant | not verified |
| d162 PER_UNCACHED_S | 1.8243e-4 s/token | `live2/d162_price.py:47` | same as INTERCEPT_S | CALIBRATED FROM ERROR | as above | GPU, EN, CM | as above | not verified |
| d162 PER_QUEUE_S | 1.5358e-4 s/token | `live2/d162_price.py:48` | la queue term (`la_arrival_admission.py` header; `d249_queue_visibility.py:41`); release re-check reads `self._w.total()` (`coordinator.py:310`) | CALIBRATED FROM ERROR | as above | GPU, EN, CM, load | as above | not verified |
| d162 CHARGE_MODE | "uncached-only" | `live2/d162_price.py:149-150` | decides what is charged to the accelerator budget (D174 (1)) | IMPOSED RULE | D174 (1), 2026-11-22 | EN (prefix cache) | none; it is a ruling | n/a |
| DEV_LAT_S (device answer charge) | 0.567 s | `baselines/costs.py:37` | `live2/coordinator.py:89` `DEVICE_ANSWER_CHARGE_S = C.DEV_LAT_S`, the charge for every device answer | MEASURED PROFILE | StudyD8 arm A total p50 (D87 rule) | DM, TT | re-profile the device (`results/device/study_devlat/orin_device_latency_tables.json`), then take the per-type value | not verified |
| RECALL_TTFT_S | GPU-WARM 0.382 / 0.874; HOST-WARM 0.459 / 1.001; COLD 2.445 / 7.367 s (11k / 28k tokens) | `baselines/costs.py:71-76` | `costs.recall_ttft_s`; the isolated estimate the b7 gate used before la (`la_arrival_admission.py` header) | MEASURED PROFILE | cited to the RH5 run (`costs.py` SOURCES block, lines 144-160) | GPU, EN, CM, context size | re-profile at the deployment's GPU and engine; interpolate by `_nearest_size` | not verified |
| COLD_PREFILL_TOK_S | {11k: 4500, 28k: 3800} tok/s | `baselines/costs.py:81` | cold-recall estimate (`costs.py`; reader not traced) | MEASURED PROFILE | StudyRH5 Part A (`experiments/cost/study_rh6_offload_knee.py:391`) | GPU, CM | re-profile cold prefill | not verified |
| PREFILL_TOK_S (duplicate) | {11k: 4500, 28k: 3800} | `policy/engine.py:26` | not traced | MEASURED PROFILE (copy) | same as above | GPU, CM | two definitions; keep one | not verified |
| HOST_RELOAD_GB_S | {11k: 47.6, 28k: 52.9} GB/s | `baselines/costs.py:91` | host reload branch of the recall cost (reader not traced) | MEASURED PROFILE | StudyRH5 vLLM load-time metric | GPU, EN, host memory | re-measure reload at the deployment's host link | not verified |
| HOST_BYTES_PER_TOKEN | 262144 | `baselines/costs.py:90` | host-tier sizing (reader not traced) | MEASURED PROFILE | model KV geometry | CM (KV layout) | recompute from model config | not verified |
| EPISODIC_CAPACITY_REQ_S | {(GPU,0,0):2.69, (GPU,4,0):1.34, ...} s | `baselines/costs.py:94-100` | episodic capacity model (reader not traced) | MEASURED PROFILE | StudyD7 / D7b cost profiling | GPU, CM | re-profile | not verified |
| EPG_TOK_PER_FRAME | 338 tokens | `live2/bodies.py:94` (copies at `deficit_feed.py:112`, `image_settings_by_type.py:50`) | per-frame charge in trace and dashcam body (`d179_share_tests.py:803`; `deficit_feed.py:129`) | MEASURED PROFILE | `live2/epg_bodies_proof.py:105-112` (proof agrees with trace) | DS (frame size), CM (tokenizer, vision encoder) | re-measure per model and frame size with `epg_bodies_proof.py` | not verified |
| EPG_TEXT_TOKENS | 42 | `live2/bodies.py:93` | per-request text overhead, same readers | MEASURED PROFILE | `epg_bodies_proof.py:540-543` | CM | as above | not verified |
| frame bytes, trace default | 60,000 B | `live2/traces.py:37` (default at `:164`) | uplink upload time for monitor frames | MEASURED PROFILE | StudyE10a | DS, NW | re-measure the JPEG size on the deployment dataset | not verified |
| frame bytes, fleet | 63,897.5 B | `live2/fleet/data_sources.py:66` | fleet `monitor_offer.frame_bytes` (`fleet/events.py:21`) | MEASURED PROFILE | `results/cost/study_e10/e10a_sizes.json` | DS, NW | as above | not verified |
| UPLINK_MBPS | 13.6 Mbit/s | `live2/traces.py:41`, `live2/fleet/links.py:38`, `live2/network_header.py:48` | upload time (`upload_s`, `links.py:45`) | DECLARED (D75 committed) | D75 | NW | read live from the link: `READ LIVE FROM ENGINE/LINK` (`link_model`) | not verified |
| RTT_MS | 44.0 ms | `live2/traces.py:42`, `live2/n4_question_delta_audit.py:81` | delivery time, one-way = RTT/2 (`oracle_lp_run.py:31`) | DECLARED (D75) | D75 | NW | read live from the link | not verified |
| LINK_RTT_S | 0.044 s | `live2/v5/cf_ontime_d162.py:53` | the v5 on-time model (duplicate of RTT_MS) | DECLARED | D75 | NW | as above | not verified |
| u_SH (profile) | measured curves, 90 DEV clips, grid 0.25 s | `results/orchestration/prof1/profiles_dev.json` key `u_SH`, read by `policy/profiles.py` | SH utility in `policy/escalation.py:108,205` | MEASURED PROFILE | StudyE9d on DEV only (profile `evidence_rule`) | DS, TT, DM, CM | re-profile on the deployment's DEV split | yes (DEV only) |
| RC tables (profile) | measured, 70 S-EMBER DEV videos, 243 questions | `profiles_dev.json` key `RC` | per-type base gain (`escalation.py:107`) | MEASURED PROFILE | S-EMBER DEV split | DS, TT, DM, CM | re-profile on the deployment's DEV split | yes (DEV only) |
| omega (class weights) | omega_SH = 1.0, omega_RC = 0.42463, omega_SS = null | `profiles_dev.json` key `class_weights_omega`; read `policy/profiles.py:121-124`, `policy/utility.py:85-89`, `policy/escalation.py:205` | per-class weight in the utility g_r(x) (`utility.py:86`) | CALIBRATED FROM ERROR (equalise mean gain; omega_k = 1/gain_k normalised to omega_SH) | `research/STATUS.md:1050` | TT, DS, CM | re-derive omega from the rule on the deployment's DEV gains; omega_SS needs a committed SS accuracy pair | yes (DEV), BUT SEE NOTE |
| durations.episodic_ttft_by_n | MEASURED, marked `replace_with_eng1: true` | `profiles_dev.json` key `durations` | episodic duration model (reader not traced) | MEASURED PROFILE | StudyD7b (N=1), StudyD7 (N=3, N=9) | GPU, EN | replace with the ENG1 measurement (flagged in the file) | not verified |
| link_model | connectivity, bandwidth, rtt, jitter | `profiles_dev.json` key `link_model` | network model (reader not traced) | MEASURED PROFILE | StudyE31b outdoor traces (E6b) | NW | read live from the link | not verified |
| demand (arrival rate) | lambda_rc_default_per_s, inter-arrival | `profiles_dev.json` key `demand` | arrival process (reader not traced) | MEASURED PROFILE | 70 S-EMBER DEV videos | TT, DS | re-profile from the deployment's question stream | yes (DEV only) |
| MARGIN_CF (unweighted) | 0.16456 | `live2/v5/cf_margin.py:67` | deviation margin in the planner (`cf_margin.py` D171 note; `v5/cf_planner.py` effective margin) | CALIBRATED FROM ERROR: p90 over the D157 population of `a_D2_DEV x |P_hat(on time) - 1[on time]|` | `cf_ontime_frozen.py` header (D157 (2)); n_overall 476, p90 0.164560 (warm 0.150341, cold 0.173231); set at D169 step 3, commit 2cb2d5c1 | TT, CM, EN (warm/cold split) | recompute the p90 on the deployment's held-out warm-all cells with `cf_ontime_frozen.py --freeze` | NO: held-out EP-G WARM-ALL cells, not dev. See conflict note |
| MARGIN_CF_ON_TIME | 0.65824 (= 0.16456 / 0.250) | `live2/cf_protect_defer.py:264-277` (asserted to 4 dp at `:277`) | the bar in the on-time planner (`cf_protect_defer.py:47`; `cf_request_defer.py:434`) | CALIBRATED FROM ERROR (formula) | `cf_margin.py` comment (D177 (3)) | TT, CM | margin_on_time = p90 / a_D2_DEV, with a_D2_DEV re-measured | NO (held-out) |
| a_D2_DEV | 0.250 | `live2/v5/cf_margin.py:62` (named in comments) | converts the margin to on-time units; also the device-vs-cloud accuracy delta | MEASURED PROFILE (committed DEV table) | `cf_ontime_frozen.py:158` | TT, DM, CM | re-measure the DEV accuracy delta for the deployment | DEV |
| D259 margin candidate | 0.0828915 (on-time 0.331566) | `live2/d261_margin_scope.py:37-38` | not read by the policy (competing derivation) | CALIBRATED FROM ERROR (method A) | D259 (A) | as above | listed to show a second derivation exists | not decision-relevant (candidate) |
| HORIZON_WARM_CAP_S | 120.0 s | `live2/v5/cf_cost.py:126` | warm horizon, `min(next_question - now, cap)` (`v5/cf_planner.py:672`) | DECLARED | D151 (4) ("capped about 60 to 120 s") | EN (cache retention), TT | none: declared, not fitted; re-derive from the cache's measured retention | n/a |
| DEFICIT_GAIN | 1.0 | `live2/v5/cf_objective.py:225` (default at `:342`) | deficit weight `w = 1 + gain * shortfall` (`cf_objective.py:322`) | DECLARED | D206 fix (`apply_d206_patches.py:150-169`) | TT | none | n/a |
| C5 cap: CAP_FLOOR, CAP_CEIL | 4, 8 | `live2/c5attr_trip_attribution.py:40` | AIMD cap on in-flight work; halves when the EWMA of monitor overload trips (`:140`) | DECLARED | `rung1_submission_gap.py:24` | EN (engine overload), NW | none; the trip threshold is also declared | not verified |
| K_R (at-risk slack) | 0.3 x the type's own deadline | `live2/rung1_submission_gap.py:56` (old 0.9 s value); policy text `live2/hybrid/policy_f_proofs.py:6` | C2 at-risk flag: slack < k_r (`live2/hybrid/hybrid_arm.py:252`) | DECLARED (D143 B) | `hybrid/policy_f_proofs.py:6` | TT, DM | none; the factor 0.3 is declared | n/a |
| C2 dashcam threshold | not located | `live2/hybrid/hybrid_arm.py:14` (text) | dashcam trailing on-time fraction (reader not traced) | DECLARED | not located | TT | none | n/a |
| per-type deadlines | alert 1.0 s, recall 3.0 s, single-shot 2.0 s | `live2/d179_rung2_verdict.py:217` (scoring); `analysis/outage/outage_headroom.py:39` | answer deadline the policy reads from the trace (`monitor_offer.deadline_s`, `fleet/events.py:21`) | DECLARED (D71 as amended by D82, cell `target_defaults`) | D71 / D82 | TT | none (task spec); must be re-declared per task | n/a |
| release re-check | enabled per arm | `live2/release_recheck.py` via `RR.arm_enables(arm)` (`coordinator.py:304-317`) | release decision; reads the D162 predictor (constants above) | IMPOSED RULE, with a read of the D162 constants | `coordinator.py:311-317` | EN, CM | none beyond the d162 refit | n/a |
| P engine block size | 16 tokens, full blocks only | `live2/predictive_belief.py:13` | prefix-cache block hashing (layer P) | DECLARED (engine config) | the serving engine's prefix cache | EN | read from the engine config (READ LIVE FROM ENGINE) | n/a |
| offload RULE | assistive: NO_RETENTION, dashcam: NO_RETENTION, robot: None | `live2/offload_policy.py:49-53` | per-type host retention (`offload_policy.py`; `coordinator.py:55`) | IMPOSED RULE (D167) | D167; `NO_RETENTION` definition not located by grep | TT, EN (host store) | none; a ruling | n/a |

Not decision-relevant (written or reported, not read in a decision): `n5_queued_by_class_census.py:50` THRESH, `dashcam_deadline_release_estimate.py:137` USER_THRESHOLD_S (analysis); `deadline_sweep.py:38,46-48` DEADLINES and DECODE_BY_OVERLAP (sweep grid); `scorer/score.py:358-370` DEVICE_WAIT_S (scoring charge, cell-side); the dashcam scoring thresholds in `analysis/episodic/dashcam_episodic.py` (scoring, not policy); E.ARMS names.

Conflicts that must be resolved before a redeployment:
1. **omega is read but unapproved.** `profiles_dev.json` labels omega as "PROPOSAL, requires user approval before the policy uses it", and `research/STATUS.md:1050` says the same. The policy still reads omega_RC = 0.42463 (`profiles.py:121-124`). omega_SS is null, so a single-shot utility call raises `MissingEvidence`. The rung 3 gate therefore depends on an unapproved weight.
2. **MARGIN_CF is set while its own docstring says the gate does not pass.** `cf_margin.py:67` sets 0.16456 (D169 step 3), but the docstring block states the constant stays `None` and that no v5 cell may run (spec v5 section 12.1). The margin was also set from held-out cells, not dev (D157 (2)).
3. **Two margin derivations.** The committed 0.16456 (on-time 0.65824) and the D259 method A (0.0828915, on-time 0.331566, `d261_margin_scope.py:37-38`) disagree by a factor of about 2. The policy reads only the first.
4. **Two frame-size constants** (traces 60,000 B, fleet 63,897.5 B) and **two prefill tables** (`costs.py:81`, `policy/engine.py:26`). Each pair should be reduced to one source.
5. **Device latency is one number for all tasks.** DEV_LAT_S = 0.567 s is charged to every device answer (`coordinator.py:89`). The Orin measurements differ by task: recall 0.15 to 0.22 s, dashcam append 0.24 to 0.37 s, single-shot 0.28 to 3.4 s (`results/device/study_devlat/orin_device_latency_tables.json`).

## Section 2: structural assumptions

| assumption | what the policy relies on | measurement it rests on | what breaks if it fails |
|---|---|---|---|
| cloud is more accurate than device per type (D177) | sending a question to cloud is a gain, so the planner escalates | `results/orchestration/live2/oracle/oracle_fair_table.json`: recall cloud WITH_HISTORY 0.569 vs device 0.258; single-shot cloud 0.622 vs device 0.548 | escalation loses value. Stateless recall (WITHOUT_HISTORY, 0.212) is below device (0.258), so serving stateless is a negative gain |
| history helps recall | a recall answered with history beats one without | `oracle_fair_table.json`: prompt split at 2,000 tokens (bimodal, empty valley 1,000 to 5,000), 0.569 with history vs 0.212 without | the cold-start path loses value. The cold body was checked (`8d19ad8d`): no mid-episode truncation, so the policy's history assumption holds on the live path |
| dashcam cloud gain per instant | serving the dashcam to cloud raises episode correctness | episode correctness under the committed thresholds: cloud-only 495 and rung 3 496 against device-only 523 (D197 thresholds, `reports/study_dashcam_diagnosis.md`); challenge mAP is above device for most arms (`reports/figures/dsmap_results.json`) | the dashcam routing is a net loss on the episode measure. The challenge metric and the episode measure disagree, so the assumption is not established |
| recent-frames ban (D152) | a recent-frames request is not sent | cited ruling D152; the code path was not located in this audit | not verified here |
| warm horizon 120 s | the cache survives up to 120 s between questions | declared (D151 (4)) | warm credit overstates when the cache evicts earlier (memory pressure, idle robots) |
| 16-token full-block prefix cache (layer P) | the engine caches full 16-token blocks | engine configuration | a different block size or eviction policy changes the cached-token count, so layer P's pricing shifts |
| device latency 0.567 s for every device answer | one charge fits all device answers | StudyD8 arm A p50 | the device charge is wrong for any task whose measured latency differs (see conflict 5) |
| margin p90 transfers | the p90 error on held-out warm-all cells bounds the deviation error | `cf_ontime_frozen.py` population | a shift in the cold fraction or the model changes the margin (warm 0.150, cold 0.173) |
| frame size 338 tokens per frame, 60 to 64 KB per frame | per-frame token cost and upload time | `epg_bodies_proof.py`; `E10A` | a different vision encoder, resolution or JPEG quality changes both the token charge and the upload time |
| uplink 13.6 Mbit/s, RTT 44 ms | upload and delivery time | D75 | a different network changes every delivery time; the policy reads these as constants, not from the link |
| per-type deadlines 1 / 2 / 3 s | the task requires these answer times | D71 as amended by D82 | any task with other deadlines changes every slack computation |
| omega ratio (RC/SH = 0.42) | the robot class counts 0.42 of the shared-host class in the utility | `profiles_dev.json` omega rule | an unapproved weight; a change in the task mix changes the ratio |
| C5 cap 4 to 8 halves only on engine overload | a slow monitor is not overload | `arms_v6c5.py:10-15` and the trip instrument | a slow monitor that is not overloaded halves the cap and throttles recall |

## Section 3: redeployment recipe

**Re-profiled by an existing study (run the study on the new device, engine, or dataset):**
- d162 INTERCEPT_S, PER_UNCACHED_S, PER_QUEUE_S: refit the first-token gate (`cost_model_gate_d162.json`).
- DEV_LAT_S and the per-task device latency: `study_devlat` (Orin tables).
- RECALL_TTFT_S, COLD_PREFILL_TOK_S, HOST_RELOAD_GB_S, EPISODIC_CAPACITY_REQ_S: StudyRH5 and StudyD7 / D7b cost profiling.
- EPG_TOK_PER_FRAME, EPG_TEXT_TOKENS: `live2/epg_bodies_proof.py`.
- frame bytes, uplink and RTT: StudyE10a and the link measurement.
- u_SH, RC, demand, link_model, durations: the PROF1 pipeline (`prof1_profiles.py`) on the deployment's DEV split.

**Re-derived by formula from one calibration run:**
- MARGIN_CF and MARGIN_CF_ON_TIME: `margin = p90(a_D2_DEV x |P_hat - 1[on time]|)` on the deployment's held-out warm-all cells, with `cf_ontime_frozen.py --freeze`, then `margin_on_time = margin / a_D2_DEV`.
- omega_k: `omega_k = 1 / gain_k`, normalised to omega_SH = 1, once the approval ruling exists (`profiles_dev.json`).
- K_R: 0.3 times each type's deadline (the factor 0.3 itself is declared).
- Per-type cloud and device accuracy (the FAIR table): re-estimate by `oracle_fair_table.py` on the new cells.

**No derivation rule (candidates for a sensitivity test):**
- HORIZON_WARM_CAP_S (120 s), DEFICIT_GAIN (1.0), C5 cap (4 and 8) and its trip threshold, the K_R factor (0.3), the per-type deadlines, the offload RULE, and the block size (set by the engine).

**Proposed sensitivity sweep (each declared constant at -30%, nominal, +30%):**

| constant | nominal | -30% | +30% | cells |
|---|---|---|---|---|
| HORIZON_WARM_CAP_S | 120 s | 84 s | 156 s | rung 3 and `-la-er`, 1x s4 to s7 |
| DEFICIT_GAIN | 1.0 | 0.7 | 1.3 | rung 3 and `-la-er`, 1x s4 to s7 |
| K_R factor | 0.3 | 0.21 | 0.39 | rung 3 and `-la-er`, 1x s4 to s7 |
| MARGIN_CF_ON_TIME | 0.65824 | 0.461 | 0.855 | rung 3 and `-la-er`, 1x s4 to s7 |
| DEV_LAT_S | 0.567 s | 0.397 s | 0.737 s | rung 3 and `-la-er`, 1x s4 to s7 |
| C5 CAP_CEIL / CAP_FLOOR | 8 / 4 | 5.6 / 2.8 | 10.4 / 5.2 | rung 3, 1x s4 to s7 |
| omega_RC | 0.4246 | 0.297 | 0.552 | rung 3, 1x s4 to s7 (after the approval ruling) |

The sweep is a sensitivity test only. It does not change any committed constant. Results are reported beside the nominal row, and no constant is tuned on the sweep.
