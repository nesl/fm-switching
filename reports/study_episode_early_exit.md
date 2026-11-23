# StudyEXIT: the EPISODE EARLY EXIT as a separate switch on rung 3 (D192 (3))

Pre-registration and mechanism verification. **NO CELL OF ANY EXIT ARM HAS RUN AND NO CELL LIST IS
POSTED.** Step 2 of CLAUDE.md's mechanism verification stopped this before the switch was built, and
this file records the stop with the measurement that establishes it.

**Two shas, kept distinct on purpose.** Every cell and every proof below ran on a clean `git archive`
export of the single literal sha **`be3dacde85587e03af938a35fa3d2e99dde86239`**, which was
origin/main when this task started, and **every `file:line` reference in this file is at that sha.**
Other sessions pushed four times while it ran, so this commit is parented on the re-resolved tip,
with `results/INDEX.md` rebuilt from that same tip and not from the older one, so nothing that
landed in between is reverted. Git records the parent; it is deliberately not hard-coded here,
because the tip moved again between two resolutions of it on this box, which is exactly the failure
the single-resolution rule exists to prevent.

**The re-resolution was checked rather than assumed, and one relevant file did change.** Between the
proof sha and this commit's parent, `coordinator.py` gained the D190 (5) release-recheck type
scoping (another session's `covex-v6-fair-c5attr-rr`), and `arms_v6rr.py`, `release_recheck.py` and
`rr_one_cell.py` are new. That change is gated behind `self._release_recheck`, an attribute only the
`-rr` arm sets, so it cannot move `covex-v6-fair-c5attr`; `reports/figures/d192_validation.json`,
`cstate.py`, `schema.py`, `baselines/interface.py`, `hybrid/hybrid_arm.py`, `arms_v6fairfeed.py`,
`fleet/trace.py`, `fleet/emulator.py`, `baselines/device_confidence.py` and `cf_pd_one_cell.py` are
all untouched. **Every quantity cited here is identical at the newer tip and only line numbers in
`coordinator.py` shift:** `:651` to `:656`, `:658` to `:663`, `:1843` to `:1853`, `:1846-1848` to
`:1856-1858`, `:1907` to `:1917`, `:1796-1821` to `:1806-1831` and `:1835` to `:1845`. The threshold
citation and the three rung-3-ladder bars hold unchanged.

---

## 1. The threshold, and where it came from

**EPISODE-LEVEL, COMMITTED, NOT SET HERE.** The D197 / D192 episode-level FAR-10 thresholds were
already on origin/main when this task started, so the instant-level placeholder was not needed and
is not used anywhere in this file.

| tier | theta | committed file | field |
|---|---|---|---|
| device (4BI) | **-0.20141326215572522** | `reports/figures/d192_validation.json` | `episode_level_thresholds_PRIMARY.device.theta` |
| cloud (32BI) | **-2.9298319411413662** | `reports/figures/d192_validation.json` | `episode_level_thresholds_PRIMARY.cloud.theta` |

Rule as committed, quoted from that file's `_rule`: "at most 10 percent of no-crash DEV EP-G
episodes cross when the tier alone serves every instant; DEV fold only, never EVAL". Both tiers
achieved DEV episode FAR 0.1111 over 45 negative DEV episodes (`k_allowed` 5). The derivation of
record is `experiments/analysis/episodic/dashcam_episodic.py:85 thresholds_episode()`; the prose
statement is `reports/figures/episodic_scores_README.md` under "Standing answer and thresholds".

Not derived here, not re-fitted here, never taken from EVAL. The instant-level thresholds
(device -2.578890, cloud -6.876021) are named in the same committed file as
`instant_level_thresholds_BESIDE` and are **not used**.

Caveat carried over rather than restated as new: that README records that the DEV calibration set
is 45 negative episodes, that 88 of the 90 DEV clips also appear in the workload, and that the
workload episode FAR therefore comes out near 0.08 rather than exactly 0.10.

---

## 2. Pre-registration, written before any cell and not to be reframed afterwards

Per seed 4 to 7 at 1x, scored against the committed rung-3 arm `covex-v6-fair-c5attr`:

1. **Robot on time AND robot correct by deadline ABOVE rung 3's.** The freed GPU must actually
   reach the robots. This is the point of the mechanism, not a side effect.
2. **Dashcam episode DETECTION and FALSE-ALARM RATE no worse than rung 3's**, scored by the D192
   episodic scorer at the EPISODE-LEVEL thresholds of section 1.
3. **Dashcam GPU SECONDS PER EPISODE below rung 3's.**

**FAILURE CONDITION, PRE-REGISTERED: IF THE FREED GPU DOES NOT RAISE ROBOT OR SINGLE-SHOT SERVICE,
THE EXIT IS REPORTED AS A COST SAVING ONLY, NEVER AS A SERVICE IMPROVEMENT.** This sentence is in
the file before any number exists so that it cannot be reframed after the numbers exist.

Rung-3 bars this would have been scored against, all three verified against the committed proofs at
the parent sha (`results/orchestration/live2/frozen_test/d184_r3_c5attr_proofs.json`) and all three
agreeing exactly with the values in the task statement:

| arm | committed dry s4 digest | rows |
|---|---|---|
| `covex-v6-fair-c5attr` (rung 3, the bar) | `12e4f73ce0ebd865` | 13,812 |
| `covex-v6-base` (positive control) | `af8befb9420ad86a` | 12,085 |
| `covex-v6-state-uo-c5attr` (positive control) | `9a4be873eb3c5fba` | 14,218 |

---

## 3. Step 0: what would make this run uninterpretable, asked before starting it

- *Is the comparator about to change?* No. Rung 3 is frozen under D188 and its digest is committed
  three times over (`d184_r3_c5attr_proofs.json`, `d185_fair_c5attr_gate.json`,
  `d190_rung4_r3_proofs.json`), all `12e4f73ce0ebd865` / 13,812.
- *Does this collide with rung 4?* No, by construction: independent of rung 4 per D194 (3). Nothing
  in `arms_v6cfr3.py`, `cf_request_defer.py`, `cf_protect_defer.py`, rung 4's registration,
  `v5/cf_objective.py` or `v5/cf_planner.py` was opened for writing, and nothing here builds on
  rung 4.
- *Does the mechanism have a reachable path in this regime?* **NO. This is the question that
  stopped the task, and it cost one reading pass instead of a sweep and a null.** Section 5.

---

## 4. Step 1: the causal chain

If an alert episode's STANDING calibrated answer (the cloud answer when it was delivered within the
1.0 s alert deadline, otherwise the device's own, spec v6 / D165 B) crosses its tier's episode-level
threshold (section 1), then the episode's detection decision is already made, so further cloud
service for that episode changes no outcome (D164: the episode rule is a cloud-context lifecycle
policy; D165 (C): an episode ends at the earlier of a served-instant crossing or the 21-frame cap).
A coordinator that stops sending that episode's remaining instants therefore gives up no detection
and returns the freed accelerator capacity to the pool, where the rung-3 ordering consumer spends it
on the queued recall and single-shot work that is missing its deadlines, raising robot
correct-by-deadline without lowering episode detection or raising the episode false-alarm rate.

Every link traces to a committed claim. The link that the simulation must implement, and the one the
whole chain hangs from, is the **first**: the standing calibrated answer must exist, per episode, as
a quantity the arm can read while the episode is still running.

---

## 5. Step 2: instantiating each link. THE FIRST LINK IS ABSENT. STOP.

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| the episode's standing calibrated answer | **none** | n/a | **ABSENT** | no score of any kind reaches the coordinator process; see A to D below |
| the per-instant cloud score | `cloud_answer.payload.cloud_score`, from `coordinator.py:1843 _score_of` | **None for every monitor instant of a dry cell** | **CONSTANT (None)** | `coordinator.py:1846-1848`: "A dry run sends no HTTP and so carries no logprobs and no text; the score is then None". Measured: see the probe, section 6 |
| the per-instant device score | `device_answers.jsonl` `device_score` (`fleet/trace.py:553`) | written by the trace generator, never on the wire | **ABSENT (written, never read in-process)** | its only readers in the tree are `scorer/score.py` and offline analysis; `schema.py` `FIELDS["monitor_frame"]` has no score field, so it cannot cross the wire |
| the only score-shaped field the arm can see | `EpisodicStream.delivered_scores` (`baselines/interface.py:100`, built at `cstate.py:592`) | **the literal 0.0, always** | **CONSTANT (0.0)** | its only two writers are `coordinator.py:658` and `coordinator.py:1907`, each appending a literal `0.0`; `coordinator.py:651` states it: "The SCORES here are placeholders: task value is scored offline from the recordings (D85, D87), never in this process" |
| episode identity for the exiting episode | `live2_completed` `episode_id` / `episode_index` (`coordinator.py:1819-1821`) | present and already read by rung 3 | yes | read at `arms_v6fairfeed.py:318-319` into the D178 deficit feed; this link is **PRESENT** |
| the act of stopping an episode's instants | `StreamAction(stream_id, "local")` | live channel | yes | emitted at `hybrid/hybrid_arm.py:513` and consumed by the coordinator; this link is **PRESENT** |
| freed accelerator returning to the pool | the engine's own capacity | n/a | not reached | unreachable while the trigger is absent |

**The two links the mechanism would need that it has are the last two: the episode key and the
action channel. The one it does not have is the trigger.** The exit would be a decision taken with
no access to the quantity it is defined by.

Four routes by which the trigger could have reached the arm were checked. Three are closed and the
fourth is forbidden:

- **A.** `EpisodicStream.delivered_scores` is the only score-shaped field in the arm-facing
  `Observation`. Both of its writers append a literal `0.0` and the docstring at
  `coordinator.py:651` says so deliberately. It is a **constant where a distribution is expected**,
  exactly the shape of CLAUDE.md's consistency check 3, and it already has readers that take its
  values rather than its length (`baselines/inarvl_adapted.py:65`,
  `baselines/hybrid_llm_adapted.py:37`), recorded here for whoever owns those baselines, and out
  of scope for this task.
- **B.** The cloud score exists only in the `cloud_answer` payload and the request log, is **not**
  fed into `delivered`, and is **None in every dry cell** because there are no logprobs without an
  engine. It is never passed to the arm at all: the completion record at `coordinator.py:1796-1821`
  carries `cloud_on_time`, `prompt_tokens`, `episode_id` and `episode_index`, and no score.
- **C.** There is no dashcam device-confidence supplier. `baselines/device_confidence.py` is keyed
  by `question_id` and covers the robot (StudyE7) and single-shot (SS2) tables only; the dashcam
  device score lives in the trace's offline answer table and is read only by the offline scorer.
- **D.** The one fabricated score in the tree is not a route and must not become one.
  `fleet/emulator.py:150 StubCoordinator._stub_score` returns a deterministic hash of the
  opportunity id, and that class is a stand-in for the whole coordinator used in fleet tests, not
  part of `test_hybrid.dry` (which builds a real `Live2Coordinator` with `dry_run=True` and
  `backend=None`). Its own docstring forbids it: "no stub score may enter a measured result"
  (D86 / D105). An exit arm made to fire dry by routing through it would be a mechanism driven by a
  hash of a string, which is the artefact-spread shape of CLAUDE.md's consistency check 3: a
  plausible per-episode spread that cannot mean what the column says.

**Per CLAUDE.md Step 2, an ABSENT or CONSTANT entry is a stopping condition: do not proceed to the
sweep. Per the port rule, the characteristic decision count would be ZERO, which is a stopping
condition and not a result.** Steps 2b, 3, 4 and 5 were not run, because running them would produce
exactly the artefact CLAUDE.md's precedent paragraph describes: E36, E36b and E36c each passed every
consistency check and produced nulls that were later traced to the mechanism under test being absent
from the simulation.

**Rule 2 classification, stated in advance of any null rather than after one:** an exit arm built
and scored on this base would be **INCONCLUSIVE, UNEXERCISED** (no condition in a dry run reaches
the mechanism, because the trigger quantity is identically absent), with the `delivered_scores`
route additionally **unexpressible** (the harness discards the channel the mechanism acts through by
overwriting every score with 0.0). It would **not** be a real negative, and it would not be evidence
about the policy.

---

## 6. The measurement, not the argument

One dry s4 cell of the committed rung-3 arm `covex-v6-fair-c5attr` was run through the committed
recipe with the planner wall-clock cutoff patched off and the posted knobs (16 devices, seed 4,
1200 s, ratio 40:40:20, lh_req, ss2, epg, per-frame, reask 30.0), with the arm-facing observation
and the monitor score extractor instrumented to census every value that could carry the trigger.
Instrument: `experiments/orchestration/live2/d192_exit_trigger_probe.py`. Output:
`results/orchestration/live2/episode_exit/d192_exit_trigger_probe.json`. **It claims no digest and
no result about any arm:** it is Step 2 instrumentation, and the digest claim is made only by the
committed `cf_pd_one_cell.py` in its own process.

| quantity | measured on the dry s4 rung-3 cell |
|---|---|
| decision rows | **13,812** |
| arm-facing observations built | 12,001 |
| `EpisodicStream`s handed to the arm | 72,000 |
| score values the arm saw inside `delivered_scores` | **2,821,940** |
| **distinct values among them** | **1, and it is `0.0`** |
| monitor score extractions (`_score_of`, kind `monitor`) | 10,886 |
| of which returned a `cloud_score` that was `None` | **10,886 (all of them)** |
| of which returned a number | **0** |
| any device score anywhere in the process | **no** |

So over one full cell the arm was handed nearly three million score values and every one of them was
the same literal zero, and the coordinator extracted a monitor score 10,886 times and got `None`
every time. The trigger is not merely unexercised at this fleet size or in this regime: it does not
exist.

**Register, marked here and not only where it was derived.** The probe's **13,812 rows agree exactly
with the committed rung-3 dry s4 row count**, which is a positive control on the probe's harness
(the instrumentation is transparent to the run) and is **a row count, not a digest**. The probe
computes no digest on purpose, so nothing here can be mistaken for a bar verdict. The load average
at the probe's start was 3.35 and 4.34 at its end, at concurrency 4: three other sessions' dry cells
were running throughout and the host could not be brought to concurrency 1. Under the measured
host-load hazard (at concurrency 3 `covex-v6-state-uo-c5attr` gave `639cd15ed38c9da0` / 14,207
against its committed `9a4be873eb3c5fba` / 14,218 alone) a digest taken here would not have been
comparable against a committed bar, which is the second reason the probe claims none. **A census of
distinct values is not load-sensitive: a constant 0.0 is 0.0 at any concurrency.**

**POSITIVE CONTROL ON THE INSTRUMENT, run in its own process by the committed runner and not by the
probe.** `experiments/orchestration/live2/cf_pd_one_cell.py --arm covex-v6-fair-c5attr --seed 4
--cutoff-off`, unmodified, on the same clean export:

| | digest | rows |
|---|---|---|
| this run | `12e4f73ce0ebd865` | 13,812 |
| committed (`d184_r3_c5attr_proofs.json`, `d185_fair_c5attr_gate.json`, `d190_rung4_r3_proofs.json`) | `12e4f73ce0ebd865` | 13,812 |

**PASS, byte-identical, and it passed despite the load** (4.60 at the cell's start, falling to 2.20
by its end, concurrency 2 to 4). So the instrument is sound and the rung-3 base is intact: what is
missing is the mechanism, not the harness. If a known-good committed arm had failed here, the
instrument would have been broken and not the arm, and nothing in this file could have been trusted.

A second, unplanned transparency check fell out of the pair: the probe's instrumented run and this
uninstrumented run both report `state_decisions = 60934` and 13,812 rows. The monkeypatched
observation wrapper therefore changed nothing about what the arm did, which is what licenses reading
the probe's census as the arm's own view.

**A second, independent structural gap, recorded while the instrument was open.** `delivered` is a
per-DEVICE `deque(maxlen=40)` (`cstate.py:81`) with no episode key: 70,190 of the 72,000 streams
were already at the 40-entry ceiling. Even with real scores in it, an *episode-level* standing
answer could not be read off it, because the arm is not told where one episode's entries end and the
next one's begin. The episode key exists on a different hook (`live2_completed`), one the score
would also have to travel on.

---

## 7. What the mechanism is worth, from committed numbers, before it is built

This is the early-exit headroom the D192 scorer already measures on the **committed rung-3 cells**
(`reports/figures/episodic_scores.csv`, arm `fair-c5attr`, at the EPISODE-LEVEL thresholds of
section 1). **Register, marked at the point of use: these are CEILINGS computed on an arm that does
NOT exit, not an observed exit arm's savings.** They are the GPU seconds the cloud spent on instants
*after* an episode's first standing crossing, which is what an exit would recover at most.

| seed | episodes | crash | no-crash | GPU s after crossing | as a fraction of dashcam cloud GPU | on CRASH episodes | on NO-CRASH episodes |
|---|---|---|---|---|---|---|---|
| 4 | 712 | 172 | 540 | 52.1661 | 6.49 % | 21.3320 | 30.8341 |
| 5 | 714 | 192 | 522 | 55.2635 | 6.90 % | 19.4311 | 35.8324 |
| 6 | 712 | 173 | 539 | 48.7799 | 6.11 % | 16.7410 | 32.0389 |
| 7 | 714 | 187 | 527 | 53.1921 | 6.60 % | 19.7117 | 33.4805 |

**The split that matters, by what triggered the crossing** (seed 4): of the 52.1661 GPU s,
30.8341 s (59.1 %) is on no-crash episodes that had already false-alarmed, where exiting is free;
16.7756 s is on crash episodes whose crossing was a true detection *before* the event, where
exiting is also free because the detection is already banked; and 4.5564 s is on crash episodes that
crossed only at or after the labelled event, which is the one stratum where an early exit could cost
a detection the episode exists for. The same ordering holds at every seed. So the risky fraction of
the prize is small, and the prize itself is **about 6 to 7 percent of dashcam cloud GPU, roughly 50
GPU-seconds over a 1200 s run at 16 devices**. That is the honest size of the service-improvement
leg of the pre-registration, and the reason the pre-registered failure condition (cost saving only,
never a service improvement) was written in advance.

Rung 3's committed episode-level dashcam numbers at the same thresholds, which the pre-registration
would have required proof 2 not to worsen: detection 0.1221 / 0.1250 / 0.1040 / 0.1123 and episode
false-alarm 0.0981 / 0.1054 / 0.1002 / 0.1063 at seeds 4 / 5 / 6 / 7, with
`dash_gpu_s_per_episode` 1.1298 / 1.1221 / 1.1207 / 1.1296.

---

## 8. What building it would require, and why none of it was done here

1. **A score on the completion record.** `coordinator.py` already computes the monitor score one
   line below the `live2_completed` call (`self._score_of(sub, r)` at `:1835`); passing it to the
   arm is additive and small. It does **not** rescue a dry cell, because a dry cell has no logprobs
   to score.
2. **The device half of the standing answer on the wire.** The device score exists only in the
   trace's offline answer table. Putting it where the coordinator can see it touches `schema.py`,
   `fleet/trace.py`, `fleet/events.py` and `fleet/emulator.py` and changes every trace's
   `device_answers_sha256` and record set, which invalidates every committed digest and bar. **That
   is a methodological change, not an implementation fix, and CLAUDE.md requires it to be flagged
   and discussed before being applied. It is flagged here and not applied.**
3. **A LIVE cell on the H100.** With (1) and (2) in place the mechanism still cannot fire in a dry
   cell, so none of the six proofs this task specifies (off-switch identity, Step 2b, the dry s4
   exit report, the port-rule count, the Step 4 negative control, byte identity of the other arms)
   is obtainable as specified. They are all dry proofs of a mechanism that can only fire live. The
   proof set would itself have to be redesigned, which is a user decision and not a build.

Nothing in rung 4's files and nothing in `v5/cf_objective.py` or `v5/cf_planner.py` was touched. No
arm was registered. No `research/*.md` was edited.

---

## 9. Consistency check

Five of the seven checks have something to bear on. Checks 2 and 6 do not apply, and no check can
bear on a result about an arm, because no such result is claimed.

1. **Cross-check against committed measurements.** The three rung-3-ladder bars quoted in section 2
   were read from `d184_r3_c5attr_proofs.json` at the parent sha and agree exactly with the task
   statement (ratio 1.000, no disagreement). The section 7 headroom figures are read from
   `reports/figures/episodic_scores.csv` unchanged and not recomputed.
3. **Distribution sanity.** The finding of this file *is* a constant where a distribution is
   expected: `delivered_scores` carries one value, `0.0`, across every observation of a 1200 s
   16-device cell. Reported as such rather than averaged.
4. **Definition audit.** "Episode" here is the workload's 21-frame EP-G episode keyed by
   `episode_id` from the committed per-seed trace table, which is the definition
   `reports/figures/episodic_scores_README.md` uses and the same one the episode-level thresholds
   were calibrated under. "Standing answer" is D165 B as that README states it. No name is used with
   two definitions.
5. **Claim linkage.** The mechanism bears on D164 (the episode rule is a policy mechanism) and
   D165 (C) (the episode rule is an ablation switch, claimed only if it measurably helps). This file
   does not weaken either: it reports that the switch's trigger is not instrumented, which is a fact
   about the harness and not about the policy.
7. **Validate the control, not only the result.** The three committed bars are the positive control
   on the instrument and were checked first; the probe deliberately claims no digest so that a
   load-sensitive digest cannot be mistaken for a finding.

Checks 2 and 6 do not apply: no latency, throughput or size is measured here and no proxy is used.

---

## 10. Verdict

**STOPPED AT STEP 2, BEFORE THE SWITCH WAS BUILT AND BEFORE ANY SCORED CELL. NO CELL LIST POSTED.**
The episode early exit is a well-posed mechanism with a committed episode-level threshold, a live
episode key, a live action channel and a measured ceiling of about 6 to 7 percent of dashcam cloud
GPU, of which the risky stratum is under a tenth. What it does not have is its trigger: the standing
calibrated answer does not exist inside the coordinator process in any cell, dry or live, and the
one score-shaped field the arm can see is a hard-coded 0.0. Three decisions are needed from the user
before this can be built, and they are listed in section 8.
