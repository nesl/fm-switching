# StudyPOL5-engine: the imposed-delay rebuild, STOPPED at the regression gate

Pre-registered in `research/EXPERIMENTS.md` (row StudyPOL5-engine, 2026-11-17, before any diagnosis or fit was
computed; the 13-field row was frozen to a timestamped scratchpad at **2026-11-17T18:30:29Z**, md5
**`e246e1c7d23364c837023ed5151fcba5`**). Scripts: `experiments/orchestration/policy/{diagnose_pol5,fit_pol5_terms,
eng1d_replay}.py`. Results: `results/orchestration/study_pol5/`. Machine: flash, CPU only, no GPU.

## 0. Outcome in one paragraph

**Part 1 (diagnosis) succeeded and Part 2 (model update) did not. The study is STOPPED before the freeze, as the
brief requires, and no holdout was read.** The diagnosis localized the over-prediction precisely: it is in the
arrivals that fall inside the action's engine span, it is the same under both imposed-delay definitions, it is
specific to StudyENG1c Part D's chained piece rebuilds, and it is NOT in the step model, which is accurate when it
is fed the engine's own step composition. Two structural rules derived from that diagnosis were implemented and
BOTH were rejected on FIT: a one-step asynchronous scheduling lag made the piece1024 ratio worse (1.74 to 2.42),
and one-prefill-per-step made it worse again (1.74 to 3.25). With both switched off, pol5's remaining changes (the
image-aware front end and the capped-host reload charge) are still worse than pol4 on StudyENG1c Part D FIT
(mono11k 1.12 to 1.51, piece1024 1.74 to 1.95, piece2048 1.66 to 1.88), so **the regression stop condition fires
and pol5 is not frozen.** pol4 remains the frozen model.

## 1. Part 1, the diagnosis: four findings, each with its evidence

**1.1 The error is in the in-window arrivals, under both definitions.** Per-arrival on StudyENG1c Part D FIT, with
the model's own phase assignment, predicted over measured:

| action | metric | pre_inj | pre_fe | in_window | post | total |
|---|---|---|---|---|---|---|
| mono11k | TTFT sum | 0.03 | 1.26 | **1.13** | 1.40 | 1.13 |
| mono11k | latency sum | 1.18 | 1.14 | **1.12** | 1.46 | 1.14 |
| piece2048 | TTFT sum | 0.42 | 2.10 | **1.62** | 2.44 | 1.59 |
| piece2048 | latency sum | 1.93 | 3.06 | **1.52** | 2.43 | 1.54 |
| piece1024 | TTFT sum | 0.62 | 2.45 | **1.83** | 1.44 | 1.82 |
| piece1024 | latency sum | 2.15 | 3.18 | **1.77** | 3.70 | 1.80 |

The in_window bin carries 96 to 98 % of the measured total in every row, so the other bins cannot move the verdict.
The two definitions agree to within 0.05, which rules out the metric as the cause (StudyT0b's definition finding
does not explain this).

**1.2 On StudyENG1d the same model is accurate per arrival.** Against StudyENG1d's OWN measured bins (its
per-arrival record, 9,912 arrivals over 180 FIT trials):

| action | pre_fe | 0-25 % | 25-50 % | 50-75 % | 75-100 % | post |
|---|---|---|---|---|---|---|
| mono11k | 1.23 | 1.04 | 1.00 | 0.93 | 1.08 | 0.80 |
| piece2048 | 1.13 | 0.92 | 0.83 | 0.79 | 1.13 | 0.75 |
| piece1024 | 1.07 | 1.12 | 0.95 | 1.17 | 1.17 | 1.48 |

So the defect is not "pieces" in general: it is StudyENG1c Part D's pieces, which are chained COLD rebuilds of 6 or
11 prefix-chained requests, where StudyENG1d's are a single 1 to 2k-token request on a warm prefix.

**1.3 The step model is not the cause.** Feeding the step model the ENGINE's own step composition inside the action
window (from StudyENG1c's committed step logs, cap 27 GiB, 30 trials per action), predicted engine time over
measured is **0.85 (mono11k), 0.97 (piece1024), 0.94 (piece2048)**. The cost of a step given its contents is right;
what is wrong is which requests the model puts in which step.

**1.4 The background-only arm is accurate.** Predicted over measured background TTFT with no action at all is 0.92
to 0.94 on every StudyENG1c cell and 0.93 to 0.98 on every StudyENG1d load, so base queueing is sound and the error
appears only in the presence of the action.

**1.5 The scheduling discrepancy, stated as measured.** pol4 merges background prefills into the action's own steps
in **54 % of piece1024 steps and 66 % of piece2048 steps** on StudyENG1c Part D FIT (4 % for mono11k), and **513 of
513** of those merged background prefills were handed over AFTER the previous step had started. StudyENG1d measured
the engine not doing that for its pieces: action token share 1.000 and 0 of 248 in-window arrivals admitted into a
piece's step.

**1.5a Provenance note added 2026-11-17 (StudyPOL6-chain Part A addendum). The three figures in 1.5 are CONFIRMED,
and their provenance is now closed.** StudyPOL6 Part A section 6 asserted the opposite of 1.5, that pol4 never
merges a background prefill into a piece's step; that assertion was an inference from reading `_schedulable` and was
WRONG, and the erratum is in StudyPOL6's report, not here. Re-measured from pol4's own deterministic step log
(`experiments/orchestration/policy/diagnose_pol6_merge.py`,
`results/orchestration/study_pol6/pol6_partA_merge_addendum.json`): on StudyENG1c Part D FIT, pol4 shares a piece's
step with a background prefill in **54.98 %** of chained piece1024 steps (497 of 904) and **69.31 %** of piece2048
steps (341 of 492), against **2.05 %** for mono11k (4 of 195). Pooling each variant's `n_parts == 1` trials gives
52.80 % and 65.35 %. 1.5's 54 % and 66 % lie inside the range those two denominators span and its 4 % for mono11k is
within two points, so the claim reproduces. The one weakness worth recording: these three figures were typed into
this report and are NOT present in the committed `pol5_diagnosis.json`, so the exact denominator 1.5 used cannot be
recovered; the measurement is now committed as a result file. StudyPOL6 also measured what 1.5 did not, the batch
WIDTH: pol4 admits up to 6, 8 and 21 prefills into a single step, against the engine's observed maximum `ctx_req`
of 2, which makes the discrepancy over-merging rather than a merge timing error alone.

## 2. Part 2, the model update, and why it was rejected

Three changes were implemented and measured behind a `pol5` flag, every coefficient loaded from
`results/orchestration/study_pol5/pol5_terms.json`. **Because the study stopped without adopting pol5, that flag is
NOT left in the serving model.** `experiments/orchestration/policy/eng1_engine.py` is named in the StudyT0b freeze
with its md5, and `T0Harness.run_holdout_once` refuses to run if that md5 moves, so the engine module was restored
byte-identical to the committed one and everything StudyPOL5 built now lives unwired in
`experiments/orchestration/policy/pol5_engine.py`. The two scheduler hooks are described there and deliberately NOT
implemented, since both were rejected. A test asserts the engine still offers exactly `eng1`, `pol4` and
`pol4_nobatch`, that `pol5` is refused, and that all 12 StudyT0b freeze md5s still verify.

**2.1 Front end, image-aware. KEPT in the terms file, not adopted.** Measured per-request front-end windows (client
submit to engine hand-off) on StudyENG1d FIT and StudyENG1 Part C FIT give
`24.10 ms + 4.16 ms per MB + 3.099 ms per image`, R^2 **0.985** on 58,085 idle windows, with a busy-regime factor of
**1.070** measured on 10,500 overlapping windows. pol4's body-size-only fit under-prices a many-image body: 489 ms
against a measured 554 ms for a 124-image 22.8 MB action. Residual: `inject` rows are still under-predicted (80.7
measured against 44.5 ms), which this study does not explain.

**2.2 Asynchronous scheduling lag. TESTED ON FIT AND REJECTED.** Rule: a request handed over during a step cannot
join it, because the engine prepared that step while the previous one ran (StudyENG1d section 6). Result on
StudyENG1c Part D FIT: piece1024 1.74 to **2.42**, piece2048 1.66 to **2.12**, mono11k 1.12 to **1.45**. It delayed
eligibility without preventing the merge, and it is kept in the terms file at 0 with the rejection recorded.

**2.3 One prefill per step. TESTED ON FIT AND REJECTED, and the inference behind it was unsound.** Rule: the engine
admits a single prefill per step. Result: piece1024 1.74 to **3.25**, piece2048 1.66 to **2.53**, mono11k 1.12 to
**1.68**. The rule was inferred from the step log field `it[1]`, whose median is 1.0 inside the action window; that
field is NOT a prefill count (it reads 1 on steps StudyENG1d shows carrying several prefills, and `pts` is a
five-element token breakdown rather than a per-request list), so the inference was wrong as well as the rule. Kept
at 0 with the attempt and its refutation recorded.

**2.4 Host transfer rate, reconciled.** StudyENG1c's committed counters give **44.69 GB/s** (96 non-holdout Part B
resumes) against StudyPOL4 term (a)'s **50.14 GB/s** fitted on StudyENG1 Part D, so the two counter-based rates
agree within 12 %. The 29 GB/s figure in StudyENG1c's report is an END-TO-END rate: a host-load resume costs
**0.1135 s** more than a resident one while the counter accounts for **0.0583 s**, leaving **53.3 ms** of
non-transfer overhead per reload (p10 to p90 spans -55 ms to +1,237 ms, because the host-load resumes include
partial loads at the capacity boundary). Conditions: the roomy-tier rate applies where the host tier is far from
full (StudyENG1 Part D, StudyENG1b); the capped rate plus the overhead applies where the tier is at its cap with
write-through eviction on every load (StudyENG1c, and any policy that manages placement under a cap).

**2.5 The regression gate.** With 2.2 and 2.3 switched off, pol5 is pol4 plus the image-aware front end and the
capped-host charge. On StudyENG1c Part D FIT it is still worse than pol4 (mono11k 1.12 to **1.51**, piece1024 1.74
to **1.95**, piece2048 1.66 to **1.88**); on StudyENG1d FIT the two are within 0.03 of each other (mono11k 1.04 to
1.07, piece1024 1.15 to 1.16, piece2048 0.96 to 0.97). The brief's regression stop condition therefore fires.
**pol5 is NOT frozen, the StudyT0b row is NOT amended, and pol4 remains the frozen model.**

## 3. What a next attempt needs

1. **The engine's per-step request membership.** Every remaining hypothesis is about which requests share a step,
   and no committed log carries that: `it[1]` is not a prefill count, `pts` is a token breakdown, and StudyENG1d's
   derived attribution recovers token mass per step but not membership. Either the plugin's field layout has to be
   decoded from the runner that wrote it, or a measurement has to record membership.
2. **A chained-rebuild measurement.** The defect lives in the chained cold rebuild (6 to 11 prefix-chained requests
   under load), which StudyENG1d did not exercise: it injected single pieces on a warm prefix. The gap between its
   accurate per-arrival numbers and StudyENG1c's 1.6 to 1.8 is exactly that difference.
3. The front-end fit (2.1) and the host reconciliation (2.4) stand on their own and can be adopted in a later row
   once something is known about 1 and 2, since neither explains the residual.

## 3A. Interpretation and the ruling of 2026-11-17 (separate from the measurements)

**The ruling: stop iterating the engine model for now. pol4 stays the frozen model and is the one the live policy
will use.** The rationale is in the shape of the residual rather than its size.

**What the residual's shape buys, and it resolves the D60 caveat.** The over-prediction is concentrated in CHAINED
piece rebuilds: in-window ratios of **1.62 for piece2048 and 1.83 for piece1024 against 1.13 for mono11k** on
StudyENG1c Part D FIT. pol4 therefore OVER-STATES the harm a piece-wise rebuild does to other requests more than it
over-states a monolithic one. The policy's choice between them is made on exactly that comparison, so the bias runs
AGAINST pieces: any live finding that the policy prefers pieces cannot be an artifact of the cost model, because the
model is charging pieces too much and the policy prefers them anyway. The D60 caveat, that the piece-versus-monolithic
preference might be a modelling artifact, is resolved in that direction. The converse does not hold: a live finding
that the policy prefers MONOLITHIC rebuilds would still be open to the artifact reading, and should be treated that
way until the residual is closed.

**An untested hypothesis, recorded as such and NOT a finding.** Between consecutive pieces of a chain the next piece
re-enters the front end (StudyPOL5 section 2.1 measures that window at about 78 ms for a piece1024 body and 140 ms
for piece2048), and during that gap the engine may serve queued background requests. A model that treats the chain as
a contiguous occupancy would then over-charge exactly the arrivals that the engine drains in those gaps, which is
where this study's residual sits. **Nothing here tests it.** It is consistent with the two facts in section 1 (the
step model is accurate given the engine's own composition, and the defect appears only for chains), but it was not
measured, and the measurement that would test it is the per-step request membership named in section 3.

## 3B. Part 3, residency integration (done 2026-11-17 on the ruling)

StudyRES1's measured model is now the controller's residency belief, in place of
`tiers.p_host_from_occupancy` and the assumption it carried (`tiers.EVICTION_RULE_ASSUMPTION`:
"the host tier's eviction order is modelled as LRU ... StudyENG1c is the measurement that replaces
this"). StudyENG1c measured it and StudyRES1 tested it at **0.9946** four-class accuracy with no
GPU-versus-host confusion, so the assumption is retired.

**Wired without touching anything frozen.** `params.py` and `tiers.py` are both named in the
StudyT0b freeze, so the belief is a new module, `policy/residency_belief.py`, exposing the same
`p_host_for(host_pool, evicted_tokens, prefix_id, t)` entry point the controller already calls. It
is reached through an optional `residency_belief` field on `Rollout` and `Coordinator`, which are
not frozen; **None keeps the old path**, so no existing result moves. All 12 StudyT0b freeze md5s
verify, and a test asserts both that fact and that the belief is not inside a frozen file.

**Which rule.** `residency.ResidencyModel(policy="rule")`, the RES1 rule as implemented, per the
ruling. RES1's R2 found LRU-by-any-access statistically indistinguishable from it (2 differing
predictions in 2,573), and that policy remains selectable behind the same flag.

**The boundary rule, and the margin's sources.** A history whose tokens written since its last
refresh are within a margin of the host cap is treated as POSSIBLY COLD: the belief returns a
SPLIT (`p_host` falling linearly from 1 to 0 across the margin) rather than a point prediction,
with `boundary: true`, `measured: false` and the reason in `basis`. The margin is
**(3,064 + 816) / 245,760 = 1.58 % of the cap**, which is **3,880 tokens at 60 GiB** and scales
with the cap rather than being a constant:

| component | tokens | source |
|---|---|---|
| RES1's median cumulative write-accounting error | 3,064 (1.37 % of the 245,760-token cap at 60 GiB) | `reports/study_res1_residency.md` section 3.2 |
| of which block rounding, kept in the margin because the fix is untested | 816 | same section |

RES1 measured that inside this band a 1.37 % accounting error becomes a **0.29** error in the
surviving fraction, which is exactly why a point prediction is the wrong output there.

**The block-rounding fix, disclosed.** The engine caches whole 16-token blocks and does not store
a trailing partial block; RES1's model charged the ceiling. `blocks_written` charges the floor.
**StudyRES1 was NOT re-scored on its TEST set with this fix**, which would be fitting on TEST; it
is recorded as pre-registerable for a later row, and until it is tested its 816 tokens stay inside
the margin.

## 4. What was NOT done, and why

- **Part 3 (residency integration) was not started when this report was first written**, because the regression
  stop fired in Part 2. It was then done on the user's ruling of 2026-11-17 and is section 3B.
- **Part 4's freeze and the StudyT0b row amendment were not done**, because freezing a model that regresses on FIT
  would put the regression into the next one-shot test.
- **The serving model was left untouched.** During Part 2 the flag lived in `eng1_engine.py`; when the gate fired
  that file was restored from the commit, and all 12 StudyT0b freeze md5s verify. The three md5s in T0's one-shot
  log that do not match (`eng1_engine.py`, `run_t0.py`, `trace_replay.py`) were already mismatched at HEAD before
  this study, from StudyPOL4's changes, and are unaffected by it.
- **No holdout was read.** StudyENG1 Part C HOLDOUT, StudyENG1c Part D HOLDOUT (120 pairs) and StudyENG1d HOLDOUT
  (60 pairs) are all untouched; the ENG1d loader refuses its holdout without an authorization string and a test
  proves it.

## 5. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/eng1d_replay.py` | NEW. StudyENG1d Part C trials, its per-arrival measured bins, its front-end windows, and the holdout fence |
| `experiments/orchestration/policy/diagnose_pol5.py` | NEW. Part 1: per-arrival predicted against measured inside StudyENG1d's bins, with the model's own phase assignment and the bin-count comparison |
| `experiments/orchestration/policy/fit_pol5_terms.py` | NEW. Part 2: the front-end fit, the host-rate reconciliation, and the two rejected structural rules with their rejections recorded |
| `experiments/orchestration/policy/pol5_engine.py` | NEW and UNWIRED. `Pol5Terms`, the image-aware front end, the capped-host reload charge, and the two rejected scheduler hooks described but not implemented |
| `experiments/orchestration/policy/eng1_engine.py` | UNCHANGED, byte-identical to the committed version, so the StudyT0b freeze still verifies. The pol5 work was developed in it, measured, and then taken back out when the regression gate fired |
| `results/orchestration/study_pol5/pol5_terms.json` | the fitted terms, both rejections, and the fit sets |
| `results/orchestration/study_pol5/pol5_diagnosis.json` | every number in section 1.2 and the bin counts |
| `experiments/orchestration/policy/residency_belief.py` | NEW, Part 3. The belief, the boundary rule and its margin, and the disclosed block-rounding fix |
| `experiments/orchestration/policy/{rollout,coordinator}.py` | the optional `residency_belief` field; None keeps the pre-POL5 path |
| `experiments/orchestration/policy/tests/test_residency_belief.py` | NEW, Part 3. 17 tests: the margin's sources, the boundary split, the rounding fix, the drop-in shape and the frozen-file check |
| `reports/study_pol4_engine.md` | the erratum in section 2A.6: StudyPOL4's rho values are biased low by its denominator, and its reading 2 is withdrawn |
