# D159 (D): the StudySS2 single-shot confidences reach the harness query objects

Session D (flash / A6000), 2026-11-21. CPU only, dry runs on the committed stub. Instruments:
`experiments/orchestration/live2/v5/ss2_conf_wiring_proof.py` and
`.../ss2_conf_reaches_arm_proof.py`. Artefacts: `ss2_conf_wiring_proof.json`,
`ss2_conf_reaches_arm.json`.

## The gap was one call, and the data was already committed

`results/casestudy/study_ss2/ss2_device_confidence.json` exists, `device_confidence._load_ss2()`
loads it, and `device_confidence.confidence()` already consults the robot table then the
single-shot one. But `cstate._device_confidence` called **`DC._load_primary()` directly**, the
robot StudyE7 table alone. So nothing in the live path ever read the single-shot table and every
single-shot question was handed `None`.

That is the mechanical cause of the finding recorded overnight: **357 of the 377 recall decisions
per cell, 94.7 percent, were made by each cascade arm's MISSING-DATA DEFAULT rather than by its
published mechanism** (`reports/study_saturation_knee.md`, the cascade correction). The arms were
not broken and the table was not missing; the supplier consulted one of its two sources.

## W1 coverage: PASS

| | |
|---|---|
| SS2 table entries | 1,042 |
| robot table entries | separate key space, **disjoint** (64-hex digest against `<dataset>/<id>`) |
| harness single-shot questions, distinct | **357** |
| **covered** | **357, 100 percent** |
| missing | **0** |

## W2 the field reaches the arms and moves decisions: PASS

**This proof was asserted before it was measured, and that is recorded rather than tidied away.**
The first version captured the ARM's `stats`, but `device_conf_absent` is a **coordinator** counter
that `_dry` does not return, so the claim rested on evidence that did not exist. The replacement is
a direct A/B on the supplier: run each cascade arm with the committed table, then with
`_load_ss2` stubbed to `{}`, which is the pre-wiring state.

| arm | with SS2 | without SS2 | field reaches the arm |
|---|---|---|---|
| `confidence-cascade` | `b310a47eb8661b1c` | `7da4caa6dc441a84` | **yes** |
| `cascade-routing` | `d35c32b081e2f8b1` | `a2c7bfcd53c9f7a7` | **yes** |

Row counts are **equal** on both sides (13,564), so the confidences change the **content** of
decisions and not their number, which is what a threshold flipping DEVICE against CLOUD on the same
opportunities looks like. An UNCHANGED digest would have proved the wiring inert, which is the
write-only-field failure in a new place and is what this proof exists to exclude.

## W3 non-cascade arms byte-identical: PASS, as a real before and after

| | base label-ignored digest | rows |
|---|---|---|
| **before** the wiring, measured in the v5-rules-2 P2 run | `200f72359b035c3a` | 13,541 |
| **after** the wiring | `200f72359b035c3a` | 13,541 |

The earlier run happened before `cstate` was touched, so this is a genuine A/B and not two
measurements of one code path. Two independent reasons support it: `cstate.observation` hard-sets
the field to `None` unless the arm declares `reads_device_answer`, and **no arm in the driver's
current queue declares it** (checked arm by arm: v5-rules-2, noc3, b7, mooncake, llf, edf, eco-llm,
warm-all-lru, v5-rules, all False). So the change is unreachable for every cell now running, which
is why it was safe to commit mid-queue.

## Check 6, and it constrains what may be concluded

The field now carries **two different notions of confidence** under one name:

| rule | n of the 357 | the table's own `signal_strength` |
|---|---|---|
| `mcq_chosen_letter_mass` (mcq) | 144 | primary |
| `geometric_mean_token_prob` (free form) | 94 | primary |
| `geometric_mean_token_prob` (point) | **119** | **WEAK** |

A cascade arm compares **one threshold** against all three, so **119 of 357 decisions, 33.3
percent, rest on a signal the committed table itself declares weak.** Per check 6 that subset may
**not** carry a headline conclusion and the affected analysis is marked unvalidated. The remedy is
to report the three rules separately, or to restrict any cascade headline to the 238
primary-signal questions.

## W4, pre-registered before any cascade cell runs with the wiring live

**The claim: this will not by itself make four of the five cascade arms discriminate.** All five see
the identical robot range `[0.386991, 0.999972]`, and four have thresholds entirely outside it,
which is why `cascade-routing` read all 20 as DEVICE while `streamscout` read the same 20 as CLOUD.
The single-shot range is comparable: min **0.4045**, p10 0.7619, p50 **0.8734**, max 1.0.

| arm | predicted |
|---|---|
| `confidence-cascade` | **SPLITS** the 357; it discriminated 13 DEVICE / 7 CLOUD on the robot side |
| `cascade-routing` | saturates, reads nearly all 357 as HIGH |
| `streamscout` | saturates, reads nearly all 357 as LOW |
| `r3-streaming` | saturates |
| `thinking-qwenvl-atdm` | saturates |

**Refuted if** any of the four saturating arms splits the 357 by more than 10/90.

**Why it matters:** if it holds, the 94.7 percent missing-data problem is **replaced by a
threshold-placement problem rather than solved**, and the cascade family still cannot be scored on
its published mechanism. Worth knowing before GPU time is spent on those arms.

## Register

- Coverage, the rule split and the confidence percentiles are **MEASURED** from the committed table
  against a committed cell's own question list.
- W2 and W3 are **MEASURED** A/B comparisons, each with a stated counterfactual arm.
- W4 is a **PREDICTION**, committed before the cells run.
- Nothing is synthesized: absence of a committed value still returns `None`, and the robot table
  being empty still raises, while SS2 absence stays non-fatal for the reason the original docstring
  gives.
