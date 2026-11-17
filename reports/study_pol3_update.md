# StudyPOL3-update: the policy library brought in line with D56, D57 and StudyENG1b

Pre-registered in `research/EXPERIMENTS.md` (row StudyPOL3-update). CPU only on flash: no GPU, no
model server, no inference. Extends `experiments/orchestration/policy/` (StudyPOL2-build) and
makes NO evaluation claim: this row fits nothing, tunes nothing and reports no policy comparison.

**Pre-registration order, stated because CLAUDE.md requires an E-id row before work starts and
the brief forbids editing `research/EXPERIMENTS.md` until the end.** A second session
(StudyCTRL1c) was editing the repository concurrently, so the registry could not be touched
mid-run without risking its edit. The full 13-field row text for this study and for
StudyT0-fidelity, including T0's pass criteria verbatim, was therefore written to a frozen
scratchpad file BEFORE any code was changed or any number computed, at 2026-11-16T22:34:26Z
(md5 44cbb9c82ea7cc540f0c90519c9271e2, one formatting-only correction at 22:34:46Z before any
computation: the registry's 13th cell is blank in every committed row, so a placeholder character
was removed). The rows were inserted into `research/EXPERIMENTS.md` verbatim from that frozen
text at the end of the session, after re-reading the file immediately beforehand so the other
session's edits were not clobbered.

**One sentence.** The KV pool now predicts prefix loss mechanistically with the tail-first rule
and the re-reference effect StudyENG1b measured, and the measured staircase is confined to the
long-gap fallback; the host tier is a bounded third tier with a pluggable eviction rule and
P_host is a function of its occupancy rather than the constant 0.0; a per-tier calibration
interface exists and refuses an uncalibrated cross-tier comparison; mu's estimator is now an
explicit parameter whose default holds mu at 0 and says why; the test suite goes from 120 to 184
tests, all passing.

---

## 1. What changed, mapped to the decisions

| # | change | code | decision |
|---|---|---|---|
| 1 | tail-first partial eviction inside one prefix, with the surviving HEAD and the lost tail both readable | `kvpool.PrefixEntry.head_tokens`, `lost_tail_tokens`, `built_tokens` | StudyENG1b section 4 |
| 2 | re-referencing a cached prefix moves it to the BACK of the free queue, which is the W25 mechanism | `kvpool.KVPool.reference` | StudyENG1b section 4 |
| 3 | one arrival's allocation as the single thing that evicts, routed through the tier store | `kvpool.KVPool.allocate` | StudyENG1b verdict 1 |
| 4 | the measured staircase, available ONLY as A6 point 2's long-gap fallback and in ALLOCATION, not seconds | `kvpool.eng1b_long_gap_curve`, `ENG1B_STAIRCASE` | StudyENG1b, ambiguity A34 |
| 5 | the cost of queueing behind work still running at resume, read off the rollout's own engine timeline | `rollout.Rollout._prefix_risk` -> `resume_queue_s` | StudyENG1b section 5 |
| 6 | a bounded host-warm tier with a pluggable eviction rule, default LRU, labelled ASSUMPTION | `tiers.HostPool`, `tiers.lru_rule`, `params.Params.host_eviction_callable` | D56 |
| 7 | three tiers as one object, with cold beneath both warm tiers and nothing ever deleted | `tiers.TieredStore`, `rollout.Rollout._build_store` | D56 |
| 8 | P_host as a function of host occupancy | `tiers.p_host_from_occupancy`, `params.Params.p_host_for` | D56 |
| 9 | tier assignment and the memory decision under bounded GPU AND host capacity, remainder demoted to COLD | `readiness.tier_assignment` | D56, spec 6.3, A6.3 |
| 10 | GPU and host sizes are INPUTS; the H100 values are named constants, never defaults | `params.H100NVL_KV_POOL_TOKENS`, `HOST_OFFLOAD_GIB_ENG1B` | D56 |
| 11 | a per-tier monotone raw-score-to-probability calibration, loaded from a file | `calibration.TierCalibration`, `MonotoneMap`, `calibration.load` | D57 |
| 12 | a LOUD failure on any uncalibrated cross-tier comparison, ranking, upgrade or gain estimate | `calibration.require_calibrated`, `rank_across_tiers`, `upgrade_decision`, `coordinator.Coordinator.upgrade_device_answer` | D57 |
| 13 | mu's estimator as an explicit parameter whose default does nothing and says so | `params.Params.mu_estimator`, `coordinator.Coordinator._update_mu` | brief item 4, spec 8 |
| 14 | the stale line in `reports/study_pol2_build.md` corrected, and ambiguity A20 marked resolved | that report; `spec_map.AMBIGUITIES` A20 | brief item 5 |

`spec_map.SPEC_MAP` goes from 58 to 72 entries and `spec_map.AMBIGUITIES` from 29 to 35, and
`spec_map.check()` is still a test, so none of the new entries can rot silently.

---

## 2. StudyENG1b in the KV pool, and the one line that keeps T0 honest

A6's mechanism is that between pieces no request holds a job's built prefix, so its blocks are
cached but UNREFERENCED and the engine frees those first. StudyENG1b measured the consequence
directly, and three parts of that measurement enter the pool.

**Tail first.** All 32 of StudyENG1b's partial losses kept the LEADING tokens (local hits were
the first 3,360 to 5,360 tokens of the prefix), because the engine frees a request's blocks tail
first. `PrefixEntry` now carries `built_tokens` alongside `tokens`, so `head_tokens()` is what
survives and `lost_tail_tokens()` is what went, and a partly evicted prefix is resumable from its
head rather than being written off.

**Re-reference, which is the W25 result.** StudyENG1b's only losses BELOW 1.0 of the free pool
were the W25 cells, where 8 warm sessions re-referenced their own cached contexts during the gap;
that moved those blocks behind the deferred prefix in the free queue WITHOUT allocating anything
new, so the effective free pool shrank. `reference()` now updates `last_used` on every reference,
held or released, which is that mechanism and not a correction factor. A test walks the free
order through a re-reference and asserts it reverses.

**The staircase stays out of the in-horizon path.** The measured curve is available as
`kvpool.eng1b_long_gap_curve`, is the LONG-GAP FALLBACK addendum A6 point 2 names, and defaults
to NOT BEING USED (`Params.survival_curve` is still None). Two reasons, both recorded as
ambiguity A34. First, StudyENG1b's own verdict is that survival is a step function of ALLOCATED
KV and that gap length matters only through allocation, so a curve in seconds would be a curve in
the wrong variable; `eng1b_long_gap_curve` therefore takes allocation as a fraction of the free
pool and a caller with a long gap must convert the gap itself. Second, T0's question is whether
the pool's bookkeeping reproduces the staircase, so feeding the staircase into `predict_loss`
would make the test vacuous. A test reads the source of `predict_loss` and asserts that neither
the curve nor the staircase constant appears in it.

**Queueing at resume is not a constant.** StudyENG1b's largest deferral cost under filler
pressure is not the loss but the QUEUE: a resume issued while another history build was still
prefilling waited 6 to 10 s whether or not the prefix survived. The brief asks for that through
the rollout rather than as a constant, and `_prefix_risk` now reports `resume_queue_s` read off
the rollout's own engine timeline, as the work pi_0 still has in flight at the instant the resume
would be issued.

---

## 3. D56: three tiers, both warm tiers bounded, and nothing deleted

The tier store is `tiers.TieredStore`: the GPU pool A6.2 already tracked, a BOUNDED `HostPool`
beneath it, and cold beneath that. "Drop" is a demotion: tokens the host tier cannot hold become
`cold_tokens`, the raw frames remain, and the history is rebuilt by prefill at the committed cold
rate. `Rollout._build_store` builds all three from the fleet's own beliefs on every rollout, and
the rollout's `kv` field keeps the GPU pool's keys AT THE TOP LEVEL so that no reader written
before D56 silently starts reading a different quantity, with the two tiers added beneath.

**Both sizes are inputs.** `Params.gpu_kv_capacity_tokens` and `host_kv_capacity_tokens` still
default to 0, which means NOT SUPPLIED, and `tier_assignment` still refuses a zero capacity. The
values StudyENG1 and StudyENG1b ran at are named constants (`H100NVL_KV_POOL_TOKENS = 62,944`,
`HOST_OFFLOAD_GIB_ENG1B = 256`) so a reproduction passes them explicitly. A host capacity of 0
means NO HOST TIER, which is StudyENG1b's E0 server.

**P_host.** The POL2 placeholder was the constant 0.0, the conservative extreme. It is now
derived:

| state of the host tier | P_host | measured? |
|---|---|---|
| no host tier configured | 0.0 | yes, StudyENG1b E0: every evicted token was recomputed |
| room for the evicted blocks | 0.999 | yes, StudyENG1b KV-HOST: 853,936 of 854,898 evicted prefix tokens returned as external hits |
| full, under the eviction rule | 0.999 x the fraction the rule keeps | NO, flagged `measured: false`, carries the rule's ASSUMPTION label |
| pinned by `Params.p_host` | that float | no, for a sweep or to reproduce POL2's 0.0 |

One consequence is stated rather than left to be discovered (ambiguity A30). Freshly evicted GPU
blocks are the MOST recently used, so under LRU a FULL host tier admits them and demotes its
incumbents to cold. P_host for the blocks being evicted therefore stays at 0.999 even at full
occupancy, the result is flagged unmeasured because the rule and not a measurement decided it,
and the cost of the full tier shows up as other prefixes' tokens in `TieredStore.cold_tokens`.
P_host falls below the measured value only when the evicted blocks do not fit the host tier at
all. A different eviction rule moves that cost somewhere else, which is exactly why the rule is
pluggable and why StudyENG1c matters.

**ASSUMPTION, named.** The host tier's eviction order was never observed: StudyENG1 Part D found
that vLLM 0.31.0 exposes eviction only as sampled lifetime and idle histograms and that no
counter reports cached-but-unreferenced blocks. The default is LRU, it is labelled
`tiers.EVICTION_RULE_ASSUMPTION` in code, it is reported in `HostPool.describe()` and in every
`p_host_from_occupancy` result that depends on it, and `Params.host_eviction_rule` is a
PLACEHOLDER whose note names StudyENG1c. `largest_first_rule` exists so the slot is demonstrably
pluggable, and is not a default.

---

## 4. D57: per-tier score calibration, with a loud failure

A calibration is a per-tier MONOTONE map from a raw score to a probability, fitted on DEV and
loaded from a file. `calibration.load` reads it, checks the knots are strictly increasing in raw
score, non-decreasing in probability and inside [0, 1], and refuses an EMPTY map rather than
reading it as identity. Outside the measured raw range the end value is held and the caller is
told, which is the rule `utility._interp` already applies to u_SH.

**Nothing is fitted here.** The brief is explicit that the maps come from StudyCTRL1c, so the
default is the identity map for every tier, which is the ABSENCE of a calibration.
`require_calibrated` therefore RAISES `CalibrationMissing` whenever scores from MORE THAN ONE
tier are about to be compared under identity maps. A comparison INSIDE one tier is always
allowed, because a monotone map preserves order and the calibration cannot change the answer. A
test opts in explicitly through `calibration.identity_for_tests()`, which is named so a grep
finds every place that relies on it, and whose `source_file` reads "NOT A CALIBRATION".

The guard is wired at the three places the brief names:

| place | call | behaviour today |
|---|---|---|
| ranking scores from different tiers | `calibration.rank_across_tiers` | raises without a calibration; maps first and can reverse the raw order |
| the cloud upgrading the device's answer | `calibration.upgrade_decision`, `Coordinator.upgrade_device_answer` | raises without a calibration |
| the memory decision when candidates carry a `score_tier` | `readiness.tier_assignment` | raises without a calibration; a candidate with no `score_tier` is a committed utility and is unaffected |

The reason the default is a refusal rather than a pass is measured, not stylistic: StudyCTRL1b's
oracle arm moved a rank metric by itself because the two tiers' scores live on different scales,
which is POL2 ambiguity A12 and is why spec 4.1's u_SH must be a CALIBRATED utility rather than a
raw tier score. Recorded as ambiguity A32.

---

## 5. mu: the options, their consequences, and why nothing was chosen

The brief asks for "the estimator the spec defines" and says that if the spec does not determine
it, the options and their consequences go in the report and mu stays at 0, labelled PLACEHOLDER,
with no silent choice. **The spec does not determine it**, and this was checked against the file
rather than from memory:

* spec 3.5 and 5.3 say what mu PRICES: residual GPU backlog at the horizon end that is not
  already in a job's continuation value, per GPU-second;
* spec 7.7 says what mu is MULTIPLIED BY: `pi = mu x (GPU-seconds of a typical first call)`;
* spec 8's main loop says only "update mu";
* spec 9's parameter table does not list mu at all.

So the quantity is defined and the estimator is not. POL2 recorded this as ambiguity A3 and
implemented an EWMA, which means mu would have drifted off its placeholder on the first event
without anyone choosing it. That is the silent choice the brief forbids, so the estimator is now
an explicit parameter.

`Params.mu_estimator` defaults to `"none"`: `_update_mu` returns immediately, mu stays at 0, and
it sets `Coordinator.mu_note` saying that the spec does not determine an estimator and naming the
consequence. An unknown value RAISES rather than falling back. Recorded as ambiguity A33.

| option | rule | consequence if selected |
|---|---|---|
| **`none` (DEFAULT, shipped)** | mu stays at the PLACEHOLDER 0 | spec 5.3's third terminal item is identically zero, so the GPU-backlog channel is SILENT. A6's expected restore work then reaches a decision only through the feasibility class (7.3) and the memory decision (6.3, A6.3), which is POL2 ambiguity A26 and is pinned by a test. Spec 7.7's price pi is also 0, so the escalation price is inert even if its flag were on. Nothing is invented; the cost of that is that one of A6's three channels is off |
| `ewma_marginal_utility` | EWMA of the realized marginal utility per GPU-second of the last released item, floored at zero, alpha a PLACEHOLDER | the analogy the spec's own style implies, since spec 6.3 defines nu_tier as the gain per byte of the last promotion into a full tier. It makes mu self-referential: mu is updated from realized DeltaJ, and DeltaJ contains mu, so the fixed point is unexamined and the smoothing constant has no evidence. Its numbers would enter every admission and release decision |
| a shadow-price estimator from the rollout | solve for the Lagrange multiplier on engine time inside each rollout | the textbook answer and the most expensive: it turns one DeltaJ into a small optimization, and M4 already shows the release loop (61.6 ms at 64 pending items) as the cost to watch, not the rollout |
| a measured opportunity cost from the engine | mu = utility lost per GPU-second from StudyENG1's measured imposed delays | the only option with a measurement behind it, and the one T0 makes thinkable, because T0 is the first evidence that the imposed delay can be predicted at all. It needs a utility-per-second conversion that no committed study supplies |
| a swept constant | treat mu as an application parameter and sweep it | honest and uninformative: it reports sensitivity rather than a value, and spec 9 does not list mu among the swept parameters |

**Nothing was chosen.** mu stays 0 and remains a declared PLACEHOLDER, `mu_estimator` is a
declared PLACEHOLDER, and T0 does not depend on either.

---

## 6. Tests

| | before | after |
|---|---|---|
| tests, all passing | 120 | 184 |
| `spec_map.SPEC_MAP` entries, all resolving | 58 | 72 |
| `spec_map.AMBIGUITIES` | 29 | 35 |
| `Params` fields | 36 | 39 |
| of which PLACEHOLDER | 22 | 24 |

Run with `cd experiments/orchestration && python3 -m unittest discover -s policy/tests -t .`

New modules: `policy/tests/test_pol3_update.py` (40 tests, one per change, each named after the
decision it pins) and `policy/tests/test_t0_fidelity.py` (24 tests, which belong to
StudyT0-fidelity and are reported there). The brief's six named additions are each covered:

| required test | where |
|---|---|
| bounded host | `TestD56BoundedHost`: capacity respected, LRU eviction, pluggable rule, assumption label |
| cold demotion | `TestD56BoundedHost.test_a_prefix_that_leaves_both_warm_tiers_is_cold_and_not_lost`, and `test_eviction_from_the_host_tier_is_a_demotion_not_a_deletion` |
| P_host by occupancy | `TestD56PHostByOccupancy`: the three measured states, the full-tier consequence, the pinning override, and that the rollout reads it |
| calibration guard | `TestD57Calibration`: raises with no calibration and with identity maps, allows one tier, allows a test opt-in, refuses a non-monotone or empty map, and guards both the upgrade and the memory decision |
| mechanistic prefix loss | `TestEng1bMechanisticPrefixLoss`: loss starts exactly at the free pool, partial loss keeps the head, a referenced prefix is never freed, the re-reference reverses the free order, `predict_loss` reads no fitted curve |
| all existing tests pass | 120 of 120, with no existing test rewritten |

---

## 7. Mechanism verification

**NOT APPLICABLE to this row**, for the reason StudyPOL2-build gives: it builds a mechanism and
makes no causal claim, tests no hypothesis and reports no comparison. The acceptance criterion
this row carries instead is the one POL2 carried, that every changed mechanism is instrumented
well enough for Steps 2 and 3 of a later verification to be possible at all. It is met: P_loss,
P_host with its basis string, the resume queue, the free order, the host tier's occupancy and
demotions, the cold tokens and the calibration's per-tier state are all on the rollout result or
on a `describe()`, and StudyT0-fidelity's own Step 2 and Step 3 were produced from them in the
same session, which is the strongest available evidence that the instrumentation suffices.

## 8. Results consistency check (CLAUDE.md, six checks)

1. **Cross-check against committed measurements. PASS.**

| quantity | this row | prior committed value | source | ratio | agree |
|---|---|---|---|---|---|
| P_host with room on the host tier | 0.999 | 0.999 | StudyENG1b section 5 | 1.00 | yes |
| P_host with no host tier | 0.0 | 0 by construction | StudyENG1b section 5, E0 | exact | yes |
| GPU KV pool, the H100 constant | 62,944 tokens | 62,944 | StudyENG1 section 1.2, StudyENG1b section 3, SLICE1 | 1.00 | yes |
| host offload size StudyENG1b ran at | 256 GiB | 256 | StudyENG1b section 1 | 1.00 | yes |
| staircase: loss onset | 1.00 of the free pool | 1.0 | StudyENG1b section 4 | 1.00 | yes |
| staircase: partial fractions | 0.33 at 1.1, 0.60 at 1.25 | about a third at 1.0 to 1.1, 60 % at 1.1 to 1.25 | StudyENG1b section 4 | 1.00 | yes |
| staircase: total loss | 1.0 from 1.5, reached by interpolation from 1.25 | total from 1.25 | StudyENG1b section 4 | conservative | yes, and the interpolation is stated |
| the committed profile constants POL2 asserted | unchanged | u_SH(device) 0.4922174586396322, omega_RC 0.42463109124188936, RTT 0.044 s, uplink 1,700,000 B/s | StudyPROF1-dev | exact | yes, the same tests still assert them |

No disagreement anywhere, and none possible by more than rounding: every number this row
introduces is read from a committed report or a committed JSON.

2. **Physical plausibility. PASS.** This row computes no latency, throughput or size of its own.
The two rates it carries are StudyENG1b's host reload (about 22 GB/s for a 10.4k-token prefix in
0.12 s) and cold rebuild (about 4.9k tok/s), both inside their committed curves and both read,
not recomputed. The eviction arithmetic is exact token bookkeeping against a pool size, so there
is no rate to be implausibly fast.

3. **Distribution sanity. PASS, with the limitation named.** The only distributions this row
produces are in the unit tests, and they are deterministic by construction. Where a committed
distribution was collapsed to a point, it is said: `ENG1B_STAIRCASE` holds StudyENG1b's bin MEANS
and not its spread, which is why it is a long-gap fallback and not a predictor, and the bins' own
n (2 to 46 per bin per server) is in StudyENG1b's table rather than restated here.

4. **Definition audit. PASS, with two definitions tightened and one name given a second
reading.** "Free pool" is StudyENG1b's own definition, KV capacity minus the prefix tokens, and
the pool reproduces it as `capacity - occupancy` with the prefix as the only unreferenced entry.
"Fully resident" is StudyENG1b's local hits at or above prefix minus the 32-token chaining
tolerance, and `trace_replay.loss_class` uses exactly that. "Lost" is prefix minus local hits.
Two definitions are now sharper than POL2's: P_HOST is a FUNCTION and not a constant, so a reader
of `Params.p_host` sees None rather than 0.0 and must call `p_host_for`, and the PROVENANCE note
says so; and a prefix's `tokens` now means the surviving HEAD, with `built_tokens` the original
size, where POL2 had only one number. One name is now used with two readings and both are
labelled: SURVIVAL CURVE in A6 point 2 reads as a function of GAP SECONDS, while StudyENG1b
measured a function of ALLOCATION; `eng1b_long_gap_curve` takes allocation, says so in its
docstring, in `ENG1B_STAIRCASE_SOURCE` and in `survival_p_loss`'s note, and ambiguity A34 records
why. No other name is used with two definitions.

5. **Claim linkage. PASS.** This row bears on spec D50's claimed contribution by making three of
its inputs executable, and on nothing else. It SUPPORTS no claim: a library is not evidence. It
does WEAKEN one thing and STRENGTHEN another. Weakened: any future cross-tier comparison that
would have run on raw scores now raises, so a result obtained that way cannot be produced by
accident. Strengthened, in the sense of made harder to overstate: P_host is no longer pinned at
the conservative 0.0, so deferral is no longer uniformly priced as a full rebuild and A6's cost
is now whatever the configured tiers imply. Nothing here touches a quantity
`research/FORMULATION.md` scopes out: the host tier holds the SAME model's KV, which is the
scoping line on KV portability.

6. **Proxy validity. PASS with both proxies declared.** (i) LRU as the host tier's eviction
order is a PROXY for StudyENG1c's unmeasured rule. It is valid for showing that a bounded host
tier changes the decision and NOT valid for any number that depends on which blocks survive a
full host tier; it is labelled in code and in every result that reads it, and it may not carry a
headline. (ii) `ENG1B_STAIRCASE` as a survival model is a PROXY for a curve in the variable A6
asks for; it is valid only beyond the rollout's reach, it is not the default, and T0 does not use
it. Both are the reason this row claims a mechanism and not a measurement.

---

## 9. What this row does NOT establish

* **No evaluation.** No baseline comparison, no capacity number, no claim that any of this
  improves a decision. T0 (`reports/study_t0_fidelity.md`) is the first fidelity evidence and is
  reported separately.
* **No calibration.** D57's interface exists and is empty. Until StudyCTRL1c delivers the maps,
  every cross-tier comparison raises, which is a working library with a missing input, not a
  working cross-tier comparison.
* **No host eviction measurement.** The rule is an ASSUMPTION and StudyENG1c is the measurement.
* **No mu.** mu is 0 and the estimator is unchosen, by instruction.
* **The conditional half of the spec is still unexercised**, unchanged from POL2: all eight
  conditional flags default off and their enabling conditions are still unmet.

## 10. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/tiers.py` | NEW. D56's bounded host tier, the pluggable eviction rule, P_host from occupancy, the three-tier store |
| `experiments/orchestration/policy/calibration.py` | NEW. D57's per-tier monotone maps, the file loader, and the loud failure |
| `experiments/orchestration/policy/kvpool.py` | tail-first eviction, the re-reference effect, `allocate`, the ENG1b long-gap curve |
| `experiments/orchestration/policy/params.py` | `p_host` now derived, `host_eviction_rule`, `tier_calibration`, `mu_estimator`, the H100 constants, provenance for each |
| `experiments/orchestration/policy/rollout.py` | the tier store on every rollout, P_host by occupancy, `resume_queue_s` |
| `experiments/orchestration/policy/readiness.py` | bounded host, cold demotion, the calibration guard in the memory decision |
| `experiments/orchestration/policy/coordinator.py` | the guarded upgrade, the explicit mu estimator, the tier store in piece sizing and resume verification |
| `experiments/orchestration/policy/spec_map.py` | 14 new spec entries, ambiguities A30 to A35, A20 resolved |
| `experiments/orchestration/policy/__init__.py` | exports for the new modules |
| `experiments/orchestration/policy/tests/test_pol3_update.py` | NEW. 40 tests, one per change |
| `reports/study_pol2_build.md` | the one stale line corrected in place, saying what it used to say |
