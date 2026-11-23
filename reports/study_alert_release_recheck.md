# StudyRR: the ALERT release re-check on rung 3 - PRE-REGISTRATION

Arm: **`covex-v6-fair-c5attr-rr`**, module `experiments/orchestration/live2/arms_v6rr.py`.
Written and **committed before any cell of this arm is posted**.

Every bar below was **supplied by the user** and is recorded verbatim. None of it is recomputed
here and none of it moves after a cell runs.

---

## 1. What the arm is

| rung | arm | what it adds |
|---|---|---|
| 3 | `covex-v6-fair-c5attr` | the c5attr base plus the D178 (2) deficit feed |
| this | **`covex-v6-fair-c5attr-rr`** | **`release_recheck` (D179 (4)) for the ALERT type only** |

An alert instant that can no longer make its 1 s deadline has its **question** skipped at wire
time; the device's answer stands. **The frame stays in the episode** and is carried by reference on
the next request: the coordinator's skip returns before `_mon_sent` is touched and the EP-G episode
context is append-only, so the next instant's `episode_frame_refs` still carries this frame and that
request's `n_new` rises by it. That property is asserted on the real request body in
`tests/test_release_recheck.py`; this arm reuses the proven component rather than restating it.

### Three things this arm deliberately does not do

* **No share admission.** The c5attr base carries none. `SA.arm_enables` is False on this arm and
  stays False.
* **No floors.** D188's floors are **PARKED**, and the reason is structural: they exist only inside
  share admission, so there is no way to have them here without pulling in shares, which would be a
  second change. They are not re-derived.
* **No recall or assistance re-check.** `live2_release_recheck_types = ("alert",)`. The recall path
  is the one that cost: r1 ran all three types and skipped 34 recall questions at s4, taking robot
  on time to **95** against rung 3's **122**.

### Why this mechanism, and it is a measured reason

From the committed rung-3 s4 cell, attributing each of 2,290 sent-and-late alert instants by what
was in front of it (`reports/study_rung4_margin_diagnosis.md`, committed at `a15a1792`):

| dominant blocker | share |
|---|---|
| **other alert frames** | **84.1 %** |
| single-shot | 4.8 % |
| recall questions | 6.9 % |
| recall warm or touch | 2.8 % |
| nothing ahead | 1.2 % |

Rung 4's question-deferral leg acts on the 6.9 percent and is reach-limited there. **This mechanism
acts on the 84.1 percent**, because an alert question that cannot make its own deadline is occupying
the engine in front of the next alert instant for no return at all.

### One factor, and it is checked rather than assumed

`coordinator.py` **refuses** `live2_release_recheck` on an arm that does not also declare
`live2_d162_pricing`, because `_uncached_in_flight` is decremented only under D162 pricing and is
otherwise a cumulative run total in the wrong register. **Rung 3 on the c5attr base already declares
`live2_d162_pricing = True`**, so this arm changes exactly one switch. The value is read off the
built instance and reported as `rr_prerequisite_proof`, not taken on trust.

### An independent switch, so the fourth arm is possible

Another session is building `covex-v6-fair-c5attr-exit` (the D192 (3) episode early exit) as a
separate switch on the same rung 3. Nothing here changes rung 3's behaviour or any shared decision
rule: this arm sets two arm-scoped **instance** attributes. An arm carrying both switches can
therefore be built later and the two contributions separated and stacked.

---

## 2. PRE-REGISTERED PASS AND FAILURE, per seed, at 1x

**1. PRIMARY: LATE alert instants FALL against rung 3.** Rung 3 s4 has **2,290 late of 8,356 sent**,
measured from the committed cell. This is the quantity the mechanism exists to reduce.

**2. Mean per-episode alert attainment ABOVE rung 3's:**

| seed | 4 | 5 | 6 | 7 |
|---|---|---|---|---|
| rung 3 | 0.441 | 0.427 | 0.436 | 0.475 |

**3. Robot on time at least 0.90 of rung 3's gain over base, AND single-shot at least 90 percent
within 2 s.** At s4, rung 3 is 122 against base 35, so the gain is 87, ninety percent of 87 is 78.3,
and the robot bar is **35 + 78.3 = 113.3, i.e. 114 or more** as an integer count. The raw count and
the computed retention are reported beside each other.

**FAILURE CONDITION, pre-registered: if late alerts do not fall, the mechanism is REPORTED AS NOT
WORKING.** It is never tuned. No threshold, no type set and no predictor in `release_recheck` is
changed in response to a result.

**PORT RULE, checked first and before any score is read.** The count of this arm's characteristic
decision, an **alert question skipped by the re-check**, must be non-zero. Zero is a stopping
condition and is reported as an **ABSENT LINK**, never as a negative about the policy.

**THE SELF-INFLICTED-LOSS GATE.** A skip of an instant that **would** have made its deadline is a
self-inflicted loss, exactly like rung 4's deferred-and-would-have-missed count. The dry s4 report
gives the raw count and its ratio to total skips, and **if it is material the run STOPS and reports**
rather than deciding materiality here.

*Dry limitation, stated in advance:* a dry cell has no engine, so there is no observed first token.
What is available is the predictor's own overrun, `est_first_token_s / remaining_s`, reported as a
full distribution, and the committed fit's measured bias. The factor used is **read** from
`cost_model_gate_d162.json`: predicted_p50 0.2519 over actual_p50 0.2455 = 1.026069, the fit's own
2.6 percent over-prediction at the median, which is the relevant direction because alert requests sit
at the low-token end of that fit. **The tail direction is favourable here**, which is the opposite of
rung 4's exposure: on the multi-thousand-uncached tail the same fit **under**-predicts by 1.39x to
1.87x, so a large request's true first token is larger than `est` and a skip is more justified, not
less.

---

## 3. FAIL-FAST: s4 is posted ALONE

s4 is posted by itself and scored against rung 3 s4 before any further seed is posted. s5, s6 and s7
follow only on that result.

---

## 4. Proofs required before any cell

* **Off-switch identity** against the committed rung-3 bar **`12e4f73ce0ebd865` / 13,812**, exactly.
  Not against rung 2.
* **Step 2b**: decisions differ, setwise and positionally, with the first difference named, and the
  first difference confirmed to be **the mechanism's own channel** (an alert question skipped)
  rather than a side effect.
* **A dry s4 report of re-check skips per type**, with the would-have-made-it check above.
* **The port rule** count, non-zero.
* **A Step 4 negative control** and the usual **positive controls**: `covex-v6-base`
  `af8befb9420ad86a` / 12,085 and `covex-v6-state-uo-c5attr` `9a4be873eb3c5fba` / 14,218 reproduce
  with this arm registered in the same processes.
* **The scope ablation** `covex-v6-fair-c5attr-rr-alltypes`, which is r1's type set on this base, so
  "alert only" is a measured cell and not a claim. It is **not** the headline arm.

All on a clean `git archive` checkout of one literal sha, one dry cell per process, concurrency 1
for anything compared against a committed bar, with the load average recorded. The digest recipe is
`cf_pd_one_cell.py --cutoff-off` with the posted knobs, and a digest is comparable only within one
recipe.

---

## 5. Caveats fixed in advance

* The re-check counters live in the **coordinator's** `counts`, not in `arm_stats`, because the
  re-check is a wire-time coordinator action taken after the arm's decision. The four names are
  frozen.
* `release_recheck.types_for` **defaults to all three types**, so no arm that does not declare the
  attribute can move. That is what makes the type gate additive rather than a change to a committed
  component, and the proof of it is the positive-control and off-switch digests, not the claim.
* D188 freezes stand: floors and `W_max` frozen, `live2_qcache_key_fix` NOT enabled, and the
  `id(obs)` cache-key fix stays **OFF**.
