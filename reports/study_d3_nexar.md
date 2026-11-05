# StudyD3-nexar: does the 32B − 4B ranking gap depend on how suddenly the event develops?

**E-id:** StudyD3-nexar (pre-registered 2026-11-04 ~19:15, before rendering or any GPU run).

**Status:** finished on 2026-11-04.
- Mechanism verification was recorded BEFORE the sweep.
- Primary: **not supported** (+0.009, 95 % CI [−0.036, +0.050]).
- Consistency check 1: the pilot's slow-gap disagreement (+0.006 vs +0.079) was followed up and remains unexplained (no further analysis, per the user's decision of 2026-11-05).
- **Classification (user decision, 2026-11-05):** the primary null is a **real negative** for a difference of about 0.05 AUROC or more. It does not rule out smaller differences.
- **Correction (2026-11-05):** secondary (f) "waiting vs upgrading" is **NOT VALID** for comparing models (see (f) below). Its numbers are kept.
- Per-request rows are gzipped (`d3_requests_h100nvl.jsonl.gz`); the analysis reads either form.

**Clips:** development clips only, excluding the D2 pilot clips. No validation or test frame was read.

## Primary hypothesis (pre-registered, from an exploratory pilot finding)

**Definitions:**

| term | definition |
|---|---|
| lead | `time_of_event − time_of_alert` |
| sudden / slow | lead < 1.5 s / lead ≥ 1.5 s |
| score | log P(Yes) (D2's normalised score), floored at 1e-12 |
| subgroup AUROC at an offset | the subgroup's positive clips vs all negative clips at that offset |
| gap(subgroup) | mean over offsets {−1.5, −1, −0.5, 0, +1, +2} of AUROC(32B) − AUROC(4B), at N = 9, SMALL |
| statistic | gap(sudden) − gap(slow), clip bootstrap resampling sudden, slow and negative clips separately, 2,000 resamples, seed 0 |
| supported iff | the 95 % CI excludes 0 and the estimate is > 0 |

**Departure from D2's unscored rule (deliberate):** positive clips are used at ALL offsets, including prefixes before `time_of_alert`, so the clip set stays fixed across offsets.

**Sanity gate (passed before the sweep):** the analysis code applied to the D2 pilot's SMALL results reproduces slow +0.0061, sudden +0.1066, difference +0.1004 on 36 slow / 39 sudden clips. Expected +0.006 / +0.107 / +0.100 within 0.002: **PASS**.

## Inputs (built 2026-11-04)

- **Clips:** 601 development clips not in the pilot: 301 positive (158 sudden, 143 slow) and 300 negative. 0 overlap with the pilot.
- **Negative reference times:** D2's rule over these clips. Within-bin KS p: 18–20 s 0.90, 38–42 s 0.92, other 0.46. 0 negatives needed clipping.
- **Offsets:** −3, −2.5, −2, −1.5, −1, −0.5, 0, +0.5, +1, +2 s.
- **Frames:** N = 9 / 3 / 1 by decode timestamp over the last 3 s before the offset. N = 3 takes the window's start, middle and end; N = 1 takes the last frame.
  - 6,010 requests per N (18,030 in total).
  - The last frame is at or before the offset in every request (asserted).
  - 33,078 unique SMALL PNG frames (12 GB) outside the repo, with a SHA-256 manifest.
  - Short spans: 21 (clip, offset) pairs, logged in `d3_sample.json`.
- **Header wording:**
  - N = 9: "The following are 9 consecutive dashcam frames covering 3 seconds, oldest first."
  - N = 3: "The following are 3 consecutive dashcam frames covering 3 seconds, oldest first."
  - N = 1: "The following is 1 dashcam frame."
  - For the 21 short spans, "3" is replaced by the actual span to 0.1 s (0.9 / 1.4 / 1.9 / 2.4 / 2.8 / 2.9 s) so the header stays correct.
- **Query:** D2's, unchanged.

## Mechanism verification (recorded BEFORE the sweep)

**Step 1: causal chain.**
- Following FORMULATION.md §Motivating scenario and §Regime uncertainty (which capability to provision when the requirement is uncertain), the chain is:
  - A sudden event shows little visible build-up before contact, so its cues are subtle and short-lived.
  - A higher-capability reader (32B) may pick up those subtle cues where 4B cannot.
  - A slow event shows a long, obvious approach that both models can read.
  - So the capability gain (32B − 4B AUROC) should be larger for sudden events.
- *Grounding caveat (as in D2):* the formulation concerns provisioning, not visual detection, so the link runs through the device-vs-cloud capability question.

**Step 2: instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| event suddenness | lead per positive clip | sudden 158, slow 143 | yes: two groups split at 1.5 s | `d3_sample.json` |
| evidence visible in the prefix | frames per (clip, offset, N) | 10 offsets × N ∈ {1, 3, 9} | yes: windows move with the offset | manifest |
| capability difference | 32B vs 4B score on identical input | measured by the run | — | per-request rows |
| gap varies with suddenness | gap(sudden) − gap(slow) | pilot: +0.100 (exploratory, n = 75) | to be tested | primary |

**Step 3: one traced request.**
- `prompt_trace_N{1,3,9}.txt` (written by the run) shows the complete prompt per N and checks that no time or name appears.
- Per-request frame pts and hashes are in `d3_requests_manifest.jsonl`.

**Step 4: negative controls.**
- Grey frames: 100 per model × N, expected to give one constant, near-zero score.
- Negatives contain no event, so their scores should not rise with offset.
- Questions where suddenness cannot matter: none built in. The gap is defined only on positives against shared negatives, so the negatives are common to both subgroups by construction.

**Step 5: alternative explanations.**
1. **Floor effect:** if 4B is near chance on sudden events, 32B has more room to gain. Checked by secondary (c): logit-AUROC, and the gap at offsets where 4B AUROC is similar between subgroups.
2. **Lead correlates with other properties** (scene, motion magnitude). Probed by the Urban / Highway split and the flow baseline per subgroup.
3. **Prefix-before-alert inclusion:** sudden clips spend fewer offsets after the alert, so the fixed-clip-set AUROC mixes in more pre-alert prefixes for them. Secondary (a) restricts to offsets 0, +1, +2, where both subgroups are past the alert.

## Results (sweep finished 2026-11-04 21:08; analysis 21:12)

Source: `results/dashcam/study_d3_nexar/d3_results_h100nvl.json` and `d3_summary.txt`.

**Comparison conditions:** 4B-I vs 32B-I on identical input (same frames, same prompt, and the same prompt-token count for every one of the 18,030 request pairs), the same stack (vLLM 0.31.0, h100nvl GPU 2, caches off) and the same decoding (greedy, max_tokens 8, top-20 logprobs).

### Observations

**Run health:**
- 36,660 OK rows (18,030 per model plus 300 grey per model).
- 0 error rows; every request succeeded on attempt 1.
- 0 responses with neither Yes nor No.
- Causality assertion held.

**Primary (N = 9, pre-registered statistic), n = 158 sudden / 143 slow / 300 negative:**

| quantity | estimate | 95 % CI |
|---|---|---|
| gap(sudden) | +0.089 | [+0.052, +0.124] |
| gap(slow) | +0.079 | [+0.041, +0.118] |
| **gap(sudden) − gap(slow)** | **+0.009** | **[−0.036, +0.050]** |

→ The CI includes 0. **Not supported** under the pre-registered rule.

**Secondaries:**

| id | measure | sudden | slow | diff [95 % CI] |
|---|---|---|---|---|
| a | N = 3 | +0.074 | +0.070 | +0.004 [−0.035, +0.040] |
| a | N = 1 | +0.058 | +0.059 | −0.001 [−0.039, +0.037] |
| a | post-alert offsets only (0, +1, +2), N = 9 | +0.108 | +0.088 | +0.020 [−0.025, +0.063] |
| b | regression of the gap on lead (continuous) | | | slope −0.095 [−0.52, +0.32], n = 301 |
| c | logit-AUROC | | | +0.049 [−0.17, +0.25] |
| c | offsets where the subgroups' 4B AUROC is similar (−2, −1.5, 0, +0.5, +1, +2) | +0.083 | +0.078 | |

- **(c) 4B AUROC per subgroup:**
  - Sudden ranges 0.568–0.738 and slow 0.601–0.719.
  - Neither subgroup is at chance at any offset.
  - Sudden is lower than slow before the alert and higher after it.
- **(d) Offset at which AUROC first reaches the threshold:**
  - At threshold 0.70, 32B reaches it earlier than 4B: sudden by 0.97 s [0.36, 1.53], slow by 1.05 s [0.27, 2.18].
  - At threshold 0.75, 4B never reaches it in either subgroup, so no shift is defined.
- **(e) Overall AUROC (all positives) per N:**
  - 32B is above 4B at every offset from −2 s onwards.
  - The model × offset interaction is:

    | N | scored positives | fixed slow cohort |
    |---|---|---|
    | 1 | −0.129 [−0.257, −0.004] | −0.062 [−0.199, +0.075] |
    | 3 | +0.095 [−0.025, +0.219] | +0.138 [+0.002, +0.273] |
    | 9 | +0.155 [+0.021, +0.297] | +0.120 [−0.031, +0.270] |
- **(f) Waiting vs upgrading — NOT VALID for comparing models (correction, 2026-11-05).** Numbers kept below for the record; do not cite them as a model comparison.
  - **Why not valid:** the measure is the per-clip log-odds of the correct answer. Log-odds are not comparable across models with different calibration, so a 4B → 32B difference in log-odds need not reflect a difference in ranking ability.
  - **Observation that exposed it:** the upgrade effect is largest (+3.31) at −3 s, where the N = 9 AUROC gap (32B − 4B) is about 0.01 (−0.007 on the 27 scored positives; +0.012 on the fixed slow cohort). The upgrade effect is smallest (+1.12) around the alert, where the AUROC gap is about 0.10.
  - A cause for this mismatch is not confirmed.
  - (The earlier label "change in mean log P(Yes)" was also inaccurate: `sec_waiting` in `d3_analyse.py` uses the log-odds of the correct answer, i.e. logit P(Yes) for positive clips and its negative for negative clips.)
  - Upgrading 4B → 32B at a fixed offset: +1.1 to +3.3 at every step, all CIs above 0.
  - Waiting one step: within ±0.6 for 4B and within ±1.04 for 32B, with mixed signs. It is positive only around the alert (−0.5 → 0 → +0.5) and negative after +0.5.
- **(g) Scene split:**
  - Urban (190 positive / 123 negative): 32B > 4B at every offset.
  - Highway (69 / 83): mixed before −1 s, and 32B > 4B from −1 s onwards.
- **(g) Out-of-fold-threshold recall** (sudden / slow):
  - 4B: ≤ 0.17 / ≤ 0.28.
  - 32B: ≤ 0.20 / ≤ 0.38.
  - Recall is low in both subgroups.

**Baselines (pooled AUROC):**
- Metadata LR: 0.628.
- Flow LR: 0.666. It reaches 0.73–0.77 at +0.5 to +2 s, which is comparable to 4B (0.70–0.73) and below 32B (0.80–0.82) at those offsets.
- Always-yes: 0.500.

**Exploratory observability:**
- Predicting sudden vs slow from frame features gives AUROC:
  - F1: 0.456 [0.39, 0.52].
  - F2: 0.555 [0.51, 0.60].
  - F3: 0.547 [0.50, 0.59].
- R² for the per-clip gap: F1 0.029, F2 0.045, F3 0.113 [0.071, 0.151].
- Increments:
  - F2 − F1 AUROC: +0.099 [0.025, 0.175].
  - F3 − F2 R²: +0.068 [0.036, 0.098].

### Mechanism-verification outcome

| link | status after the run |
|---|---|
| event suddenness | present: 158 / 143 |
| evidence in the prefix | present: scores rise toward and past the alert in both models (e) |
| capability difference | present and non-zero: gap ≈ +0.08 to +0.09 in each subgroup, both CIs above 0 |
| gap varies with suddenness | not observed |

- **Step 4 (grey frames):**
  - Yes rate 0 for both models at every N. One distinct score for every model and N except 32B at N = 9, which has 2 distinct scores.
  - Median P(Yes) is between 3e-9 and 1.3e-5.
  - Real-frame Yes rates are 2.9–11.8 %.
- **Step 4 (negatives not rising with offset):** not separately tabulated in this analysis (not checked).

### Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| N = 9 SMALL prompt tokens | 3,090 (3,092 for 21 short-span headers) | 3,090 | D2-nexar | 1.00 | agree |
| grey Yes rate | 0 | 0 | D2-nexar | — | agree |
| gap(sudden) | +0.089 | +0.107 (n = 39) | D2 pilot, exploratory | 0.83 | agree |
| gap(slow) | +0.079 | +0.006 (n = 36) | D2 pilot, exploratory | 13× | **DISAGREE** |
| diff | +0.009 | +0.100 | D2 pilot, exploratory | 0.09 | **DISAGREE** |

- The same analysis code reproduces the pilot values exactly (sanity gate), so the disagreement does not come from code or definitions.
- Clips differ (601 new development clips vs the 75 pilot clips).
- The pilot value is a point estimate on n = 36 slow clips with no CI computed, so whether +0.006 lies inside this run's sampling range is **not yet checked**.
- **Follow-up (2026-11-05 01:30, `d3_analyse.py --pilot-ci` → `d3_pilot_ci.json`; CPU, same code, 2,000 resamples, seed 0):**

  | quantity | estimate | 95 % CI |
  |---|---|---|
  | pilot gap(slow) | +0.006 | [−0.065, +0.078] |
  | pilot gap(sudden) | +0.107 | [+0.052, +0.165] |
  | pilot diff | +0.100 | [+0.020, +0.179] |
  | D3 gap(slow) at the pilot's size (36 slow / 75 negative clips drawn from D3 without replacement, 2,000 draws) | median +0.078 | [+0.015, +0.145] |

  - Only **0.9 %** of the D3 draws are ≤ the pilot's +0.006.
  - This run's gap(slow) (+0.079) lies just above the pilot's upper bound (+0.078).
- **Outcome of the follow-up: the discrepancy is NOT fully explained.** Sampling variation at the pilot's size makes a value as low as +0.006 unlikely (about 1 % of draws) though not impossible.
- **Status (user decision, 2026-11-05): kept as unexplained; no further analysis.**
  - The primary hypothesis was chosen after seeing the pilot data, so an extreme pilot value is expected under that selection.
  - Another possibility, not tested: the pilot's slow clips differ systematically from the other development clips.
- Following CLAUDE.md, I do not choose between the two values. Both are reported.

**2. Physical plausibility.** No latency or throughput was measured in this study; N/A.

**3. Distribution sanity.**
- Grey scores are constant, as expected for a control.
- Real-frame scores vary (per-offset AUROCs differ, and Yes rates are 2.9–11.8 %).
- No unexpected constants.

**4. Definition audit.**
- Score, AUROC, offsets, SMALL and the N = 9 header are as in D2.
- One deliberate difference: positives are included at pre-alert offsets (stated above).
- N = 3 / N = 1 headers and short-span headers state the actual N and span.

**5. Claim linkage.** FORMULATION.md §Regime uncertainty (which capability to provision):
- The result does not support the claim that the capability gain depends on event suddenness.
- The gain itself (32B over 4B) is present in both subgroups.

**6. Proxy validity.**
- Suddenness is proxied by `time_of_event − time_of_alert` from Nexar's annotations. It measures annotator-judged warning time, not visual build-up.
- F1 / F2 / F3 predict the sudden / slow label only weakly (AUROC ≤ 0.56), so the label is not strongly visible from frame features.
- This is a limitation of the proxy.

### Interpretation (consistency check 1 has an unexplained discrepancy, kept as such by user decision; see above)

- **The pre-registered verdict stands either way:** NOT SUPPORTED, by the mechanical decision rule applied to the pre-registered confirmatory sample.
- **Classification (user decision, 2026-11-05):** a **real negative** under CLAUDE.md Rule 2 for a difference of about 0.05 AUROC or more.
  - Every causal link was present, and the capability gap was non-zero in both subgroups.
  - The pilot's +0.100 lies outside this run's CI (upper bound +0.050).
- **What it does not rule out:** a difference smaller than about 0.05 AUROC. The same holds for N = 3 and N = 1.
- **What it suggests:** the pilot's large difference came mostly from its low slow-subgroup gap (+0.006), which this run did not reproduce (+0.079). That pilot value sits in the bottom ~1 % of what this run's data give at the pilot's sample size. Why is not established.
