# Policy v2, item 3: the cost-model gate

**A6000, 2026-11-20. CPU only; committed request logs only, no GPU, no model server, no live run.**
Script `experiments/orchestration/live2/cost_model_gate.py`, output
`results/orchestration/live2/frozen_test/cost_model_gate.json`. No em dashes.

## 0. Verdict

**The gate does NOT pass, and it cannot pass on committed data.** Two separate failures, and the
first is the one that matters:

1. **The warm path cannot be held out at all.** Of 304,867 committed cloud requests across 23
   sixteen-device cells, **720 are warm, which is 0.236 percent**, and all 720 sit in exactly two
   cells, `llf_n16_s4` (362) and `edf_n16_s4` (358). Every held-out split therefore contains **zero**
   warm requests, whether held out by seed or by arm. v2's whole premise is warm state, so its cost
   model is being asked to price a regime for which no validation set exists.
2. **Cross-policy transfer on decode is 34 percent off.** Fitting on the non-hybrid arms and
   predicting the hybrids, the decode term over-predicts by a factor of **1.343**. v2 is a new
   policy whose request stream no fitted arm has produced, so the cross-arm split is the relevant
   test, and decode is the term that decides a 3 s deadline (frozen_test 19.5).

Both are fixable, and section 4 lists exactly what is needed to fix them.

## 1. What was fitted

Two linear terms, deliberately tiny, on committed live requests:

    first_token = a0 + a1 * uncached_tokens + a2 * overlap_at_submit
    decode      = b0 + b1 * overlap_at_decode

`uncached_tokens` is prompt tokens minus the engine's own per-request `cached_tokens`, so cache state
enters as a MEASURED quantity and not as a belief. `overlap` is the number of other requests whose
own submit-to-done interval overlaps the window in question, computed by two bisects per request
rather than by scanning, which is what makes 304,867 requests tractable.

The model is kept this small on purpose: **a model that needs per-arm terms cannot price a policy
that has not run**, and pricing an unrun policy is precisely what v2's latest-safe-start planner
asks of it.

Fitted coefficients, by-arm split: `first_token = -0.0234 + 1.647e-04 * uncached + 0.0381 * overlap`
and `decode = 0.0045 + 0.0151 * overlap`. So each additional overlapping request costs about **38 ms**
of first-token latency and **15 ms** of decode, and each uncached token about **0.16 ms**.

## 2. Held out by seed: fit on seeds 0 and 4, predict 5 and 6

| split | state | n | first token, predicted / actual p50 | ratio | decode, predicted / actual p50 | ratio |
|---|---|---|---|---|---|---|
| in sample | all | 172,564 | 0.322 / 0.286 | 1.126 | 0.067 / 0.064 | 1.044 |
| in sample | warm | 720 | 0.295 / 0.326 | 0.905 | 0.096 / 0.080 | 1.202 |
| **held out** | all | 132,303 | 0.322 / 0.304 | **1.057** | 0.081 / 0.073 | **1.118** |
| held out | warm | **0** | n/a | n/a | n/a | n/a |

Across workload draws the model transfers acceptably on the cold path: 5.7 percent over on first
token, 11.8 percent over on decode. **The held-out warm row is empty**, because both warm cells are
at seed 4, which is in the fit set.

## 3. Held out by arm: fit on the non-hybrids, predict the hybrids

This is the harder and more relevant test, and it is the one section 16's calibration failed.

| split | state | n | first token ratio | decode ratio |
|---|---|---|---|---|
| in sample | all | 203,369 | 1.020 | 1.065 |
| in sample | warm | 720 | 0.895 | 1.193 |
| **held out** | all | 101,498 | **0.918** | **1.343** |
| held out | warm | **0** | n/a | n/a |

The first-token term under-predicts the hybrids by 8.2 percent, which is tolerable. **The decode term
over-predicts them by 34.3 percent**, which is not, for the reason frozen_test 19.5 gives: on the
robot questions that missed a 3 s deadline, decode was 1.086 s at the median, over a third of the
whole budget. A planner that over-estimates decode by a third will defer work it could have released
and will decline work it could have served.

The direction is worth noting too. The model over-predicts hybrid decode because it was fitted on
arms whose robot requests decode in a crowd of 50 to 61 overlapping requests, while the hybrids'
decode at 9 (frozen_test 18.7.2). A linear term in overlap cannot carry that: the relation is
convex, 0.024 s at 0 to 3 overlaps rising to 1.403 s above 45, so a line fitted mostly on the busy
end over-prices the quiet end.

## 4. The calibration cells needed from the H100

The warm failure is a data gap, not a modelling one, and **no existing arm can close it**: warmth
occurs in committed data only as a side effect of edf and llf deferring until their own builds
complete, which is why it is 0.236 percent of requests and confined to one seed.

**So item 3 cannot pass before item 2(e) has run.** The WARM-ALL plus LRU baseline arm is the only
thing in the v2 plan that produces warm requests in quantity, so the gate's data has to come from
it. That is an ordering constraint the plan should carry: build 2(e), run it, then gate.

What I need, stated so it can be scheduled:

| cell | why |
|---|---|
| WARM-ALL + LRU at 16 devices, seeds 0, 4, 5 and 6, three-type | the warm fit set and, crucially, a warm HELD-OUT set. Four seeds means two can be held out |
| the same arm at 0.5x and 0.25x GPU pool, seeds 4 and 5 | warm requests under eviction pressure, where a warm prefix is partially resident. The current model has no term for a partial hit and no data to fit one |
| any one existing arm re-run at 16 devices with warm-ahead enabled, seed 4 | a WITHIN-ARM warm against cold comparison, so the warm term is not confounded with the policy that produced it |
| edf and llf at 16 devices, seeds 5 and 6 | the cheapest partial fix available today: it would move the existing 720 warm requests out of a single seed, making a by-seed warm hold-out possible without any new arm |

The last row is worth doing first because it is two existing arms at two existing seeds and needs no
new code. It does not fix the cross-policy problem, but it turns the warm hold-out from impossible
into thin.

## 5. What this means for the v2 build order

The brief's order is build then gate, and that is right, with one correction the gate itself
produces: **the gate's held-out warm set does not exist until 2(e) has run**, so the gate cannot be
the thing that unblocks the first live v2 run unless 2(e) runs before it. Either 2(e) is treated as
a calibration instrument as well as a baseline arm, which is the cheaper reading, or the gate is
explicitly split into a cold half that passes now and a warm half that waits.

The decode convexity is a modelling fix I can make without new data: a piecewise or log term in
overlap, fitted on the six measured overlap buckets rather than as one line. I have not made it yet,
because changing the model to improve a held-out ratio I have already seen is fitting to the test
set. It should be fitted on the cold data, held out by arm, and reported once rather than tuned.

---

# D149 / D152 value reader: Step 2b passes, the acceptance test does not discriminate

**A6000, 2026-11-20. Dry cells, CPU only.** Script
`experiments/orchestration/live2/hybrid/value_reader.py`, wired into `HybridArm` behind
`c3_value_reader`, DEFAULT OFF. Proofs in
`results/orchestration/live2/frozen_test/value_reader_proofs.json`. Cell: seed 4, 16 devices,
1,200 s, 40:40:20, LH-REQ robots, SS2 pool, dry engine.

## What the reader does

It replaces C3's feasibility-triggered RECENT fallback. The old branch sent RECENT whenever the full
history would not fit and RECENT would, a feasibility test with no reference to whether the answer
would be any good. The reader asks instead whether the answer beats the one the device already has:

    value(rep) = P(on time | rep) x accuracy(rep)   against   value(device) = accuracy(device)

On the committed DEV table (`lh_req_quality.json`, D6-compliant, fitted on the 28 DEV questions),
cloud D2 is 0.250, cloud RECENT is 0.107143 and the device is 0.107143. **RECENT never strictly
beats the device**, so the RECENT shortcut disappears without a rule of its own, which is what
D152 (2) ruled and predicted would fall out of the reader.

## The proofs

| arm | decision digest | representations released |
|---|---|---|
| hybrid-F-lhreq | `ec49e6d5a3b5454f` | D2 372, **RECENT 5** |
| hybrid-F-lhreq-noc3 | `5d3469549fead8ac` | D2 372, RECENT 0 |
| **hybrid-Fv-lhreq** (value reader) | `5d3469549fead8ac` | D2 372, RECENT 0 |
| hybrid-Fv-flat-lhreq | `5d3469549fead8ac` | D2 372, RECENT 0 |
| hybrid-Fv-invert-lhreq | `5d3469549fead8ac` | D2 372, RECENT 0 |
| hybrid-F6-lhreq (regression check) | `ec49e6d5a3b5454f` | D2 372, RECENT 5 |

**Step 2b PASSES.** The value reader moves decisions against hybrid-F, and it removes exactly the 5
RECENT releases C3 was making. The reader is behaviourally identical to turning C3 off on this cell,
which is the right answer: D152 (2) says the RECENT-only shortcut is not used for long-horizon
questions, and the reader reaches that conclusion from the value table rather than from a switch.

**D149 (4)'s ACCEPTANCE TEST DOES NOT DISCRIMINATE HERE, and that is a failure of the test, not a
pass.** Flattening and inverting the table leave the digest unchanged. The cause is scope, not
decoration: C3's slot consults the reader ONLY when the full history did not fit, so the only
candidate ever offered is RECENT, and under all three tables the reader withholds it. A control
whose every case lands the same way under every treatment cannot detect anything.

That the reader CAN express a preference is shown directly, outside the arm:

| table | only RECENT fits | both D2 and RECENT fit |
|---|---|---|
| committed | withhold | **send D2** |
| flattened | withhold | **withhold** |
| inverted | withhold | **withhold** |

So the transforms do change the decision when the reader is offered a real choice. **The acceptance
test will only be meaningful once the reader is consulted at ADMISSION**, choosing among D2, RECENT
and the device, rather than in a fallback slot that offers one candidate. That is where D151 (3)
puts the robot decision anyway, so this is an argument for moving the reader there in v5 and not a
reason to weaken the test.

Recorded as **unexercised** under CLAUDE.md Rule 2: the mechanism is present and reachable, and no
condition in this cell reaches the branch where it would differ.

---

# The D151 (6) cost-model gate: FAILS, and the reason is that warm is confounded with arm

**A6000, 2026-11-20, CPU only.** `experiments/orchestration/live2/cost_model_gate.py` over
345,066 committed requests in 26 cells. Output `results/orchestration/live2/frozen_test/cost_model_gate.json`.

## The fits

    first_token = a0 + a1 * uncached_tokens + a2 * overlap_ft
    decode      = b0 + b1 * overlap_decode

| split | class | n | first token pred/act | decode pred/act |
|---|---|---|---|---|
| by seed, held out | all | 172,502 | 1.072 | **1.298** |
| by seed, held out | warm | 1,077 | 0.911 | **1.245** |
| by seed, held out | cold | 171,425 | 1.072 | **1.309** |
| by arm, held out | all | 101,498 | 0.938 | **1.316** |
| by arm, held out | **warm** | **0** | n/a | n/a |

**First token predicts acceptably out of sample**, 0.94 to 1.07. **Decode over-predicts by 25 to 32
percent in every held-out class.** On that alone the gate does not pass.

## Why it cannot be fixed by collecting more of the same data

The warm class is 1,797 of 345,066 requests, 0.52 percent. That scarcity is the visible problem and
it is not the real one. Per cell:

| cell | believed tier counts | engine prefix_cache_hits |
|---|---|---|
| edf n16 s4 | gpu 358, cold 373 | 512,992 |
| llf n16 s4 | gpu 362, cold 373 | 424,224 |
| b7 n16 s4 | **cold 372, gpu 0** | **0** |
| hybrid-F-lhreq n16 s4 | **cold 372, gpu 0** | **0** |

**Warm is not a condition that varies within an arm. It is a property of which arm is running.** edf
and llf rebuild histories, so they reach a fully built state, take a GPU belief, and show hundreds
of thousands of engine prefix hits. b7 and the hybrids never rebuild, never take a GPU belief, and
show exactly zero engine prefix hits. The coordinator's belief and the engine's own counters agree
at cell level, which is a reassuring result in itself.

The consequence for the gate is fatal and is not about sample size: **the warm coefficient is fitted
entirely on edf and llf and would be applied to arms that never go warm.** That is why the by-arm
split has ZERO held-out warm requests, a figure that reads as a shortage and is actually a
statement that the warm regime is unidentified out of arm. Collecting more committed cells of the
same arms cannot fix it; only an arm that goes warm and cold under the SAME policy can, which is
exactly what WARM-ALL plus LRU is for.

**Verdict: the gate FAILS. v5 does not go live on this evidence.** The ordering constraint stands:
WARM-ALL must run before the gate is retried.

## The belief-versus-engine question, answered as posed and then corrected

The user asked for the prediction error reported separately for requests where the belief said cold
while the engine reported cache hits. **There are no such rows, and the reason is worth stating
because it is not the reassuring one.**

`telemetry_cached_tokens` appears in 18,738 residency rows over 45 cells: absent in 16,934, exactly
zero in 1,804, **positive in none**.

**CORRECTION, added 2026-11-20 after a wider audit (session C, 213 logs and 20,630 rows): "positive
in none" is true of THIS population and is not a property of the field.** Over the wider base the
field is positive in **95 rows**, 992 to 18,896 tokens, median 3,952. Every positive row sits in a
pilot or acceptance cell and none in the 45 frozen-grid and sweep cells counted above, so both
readings are correct on their own population and my error was generalising a population-specific
zero into a statement about the field. The conclusion below is unaffected, and one of its clauses is
now measured rather than inferred: **72 of those 95 positive rows are on PIECE-CHAINING arms and
none is on an arm that rebuilds whole.** So going warm and reporting reuse are DIFFERENT properties,
which is why edf and llf take 358 and 362 GPU beliefs while reporting reuse zero times. It is also
why the WARM-ALL instrument has to SLICE: a sliced build is the only committed shape that both goes
warm and reports reuse, so it is the only one that can identify the warm coefficient within a single
arm rather than across arms. I first read that as a broken write, because five cells report
424,000 to 513,000 engine prefix hits while every telemetry row in them reads zero. That reading was
wrong and I checked it before reporting it. The field is written at `coordinator.py:756` on the
history-build path ONLY, so it covers history pieces and not the dashcam monitor traffic that
produces most of those hits, and on the slice it does cover it is honestly zero. `cached_tokens_of`
in `backend.py` is careful in the same direction: absent returns None rather than 0, with a comment
that a zero "would be read as a confirmed cold path and D81's WARM / COLD tag would then be a
fabrication."

**But the phenomenon the question was aimed at is real, and the committed code already names it.**
`coordinator.py:745-752` says it outright: a partially built history keeps a COLD readiness, while
"the already-built prefix is still reused on the wire as uuid references, so the request is cheap
even while the readiness the arm sees says COLD; that gap is a limitation of the committed action
space and is reported." So an arm can be told COLD on a request the engine serves cheaply. That is
the user's PROVISIONAL note, and its anchor is that comment and the edf/llf prefix-hit counts,
not a telemetry disagreement that does not exist in the logs.

Recorded PROVISIONAL per the ruling: **the belief understates residency on partially built
histories, by construction rather than by fault.** Wiring `telemetry_cached_tokens` into the belief
as D150 directs will NOT by itself correct this, because the field does not observe the traffic
where the reuse happens. Session C should know that before it wires it.

## What this predicts for the 3 s handful

Section 22 of `study_frozen_test.md` predicted that edf and llf would move most between the offline
3 s re-score and a live 3 s run, as the upper bound on the planning-versus-scoring confound. That
prediction was made on their deferral behaviour. The table above gives it a mechanism: **edf and llf
are the only arms with real engine prefix reuse**, so they are the arms whose live cost differs most
from anything a re-score can reconstruct. The prediction stands and its reasoning is now stronger
than when it was written.

---

# D155 (4): the RECENT rule is now IMPOSED, and D149 (4) discriminates where value acts

## 1. Why the rule had to become a rule

Under D87's SUBSTITUTED device entry the device scored exactly what cloud RECENT scored, 0.107143,
and ties go to the device, so RECENT was never sent and D152 (2) appeared to **fall out** of the
reader's arithmetic. StudyORIN-REC part 1 measured the device at **2 of 28 = 0.071429** on the DEV
fit split, so the tie is gone, cloud RECENT strictly beats the device, and the unconstrained reader
sends RECENT whenever `P(on time) > 0.6667`. **7 of 20 cells of a declared grid flip.**

So D155 (4) imposes it. `choose(..., forbid_recent_for_lh=True, is_long_horizon=True)` removes RECENT
from the candidate set for a long-horizon question before any value is compared, and the decision
record carries `excluded_by_rule` and `rule_imposed` so the rule can never be read back as a result.
Measured effect at the four grid points where the unconstrained reader would have sent RECENT:

| p(D2) | p(RECENT) | rule ON | rule OFF |
|---|---|---|---|
| 0.0 | 0.7 | withhold | SEND RECENT |
| 0.0 | 1.0 | withhold | SEND RECENT |
| 0.3 | 0.7 | SEND D2 | SEND RECENT |
| 0.3 | 1.0 | SEND D2 | SEND RECENT |

A SHORT-horizon question is unaffected (`is_long_horizon=False` still sends RECENT), so the rule is
scoped to the questions D152 (2) is about rather than applied globally.

**Documented as IMPOSED, not derived.** The module docstring now says so, gives the superseded
figure, and records that it is not statistically settled: the DEV device interval
[0.019812, 0.226454] CONTAINS cloud RECENT's 0.107143, so on 28 questions "RECENT beats the device"
is one reading of a wide interval. D155 (4) revisits after the warm device latency and larger
samples. One stale figure in that docstring is also corrected: it claimed the device is right "about
25 percent", which was an EVAL number quoted beside a DEV comparison.

## 2. D149 (4)'s acceptance test, run where value acts

In C3's fallback slot the test could not discriminate, because that slot ever offers one candidate.
Warming is the decision value is supposed to drive, so the control was moved rather than weakened.
Eight candidate histories over both representations, with weight, question probability, delivery
gain and harm all varied so no single term dominates by construction. Artefact:
`results/orchestration/live2/v5/value_inversion_at_warmkeep.json`.

| slots | committed admitted | flat | inverted | full devalued 10,000x |
|---|---|---|---|---|
| 2 | h1, h4 | h1, h4 (order changed) | **h4, h1** | **h4, h2** |
| 3 | h1, h4, h3 | **h1, h4, h2** | **h4, h1, h2** | **h4, h2, h6** |
| 4 | h1, h4, h3, h2 | **h1, h4, h2, h6** | **h4, h1, h2, h6** | **h4, h2, h6, h8** |

**The test DISCRIMINATES: the ranking changes under all three transforms at every slot count, and
the admitted SET changes in 8 of the 9 cells.** So the earlier null was a property of the slot, not
of the mechanism, and G11's diagnosis is confirmed: the test is sound and C3's fallback was the
wrong place to run it.

**REGISTER, marked at the point of use: this is a CONSTRUCTED candidate set, not observed traffic.**
It establishes that value is load-bearing in the warm/keep reader as written. It is not a census and
it says nothing about how often such a set arises in a run, which only a live v5 cell with the
reader at admission can show.

---

# PATCH 2's owed proof is MET: the corrector is exercised on a live cell, without altering it

**Measured on the H100, `llf_n16_s4_1200s_h27_3t_L3`, post-patch, observe mode.** From that cell's
`coordinator_result.json` under `counts`:

| counter | value |
|---|---|
| `belief_corrections` | 724 |
| `belief_corrections_changed` | **15** |
| `belief_corrections_observed_only` | **15** |
| `belief_to_gpu` | 13 |
| `belief_to_cold` | 2 |

**The observe check PASSES**: `changed == observed_only`, so every correction's mutation was
withheld and no decision in that cell was altered. **So the proof I owed is discharged in the form I
wanted and could not guarantee: the corrector is EXERCISED on a live run, making 15 corrections it
would have applied, 13 of them promoting a belief to GPU-warm, while leaving the run that
demonstrates it untouched.**

Two things follow, and the second is the more useful.

1. **It is not `unexercised` under Rule 2.** Had `belief_corrections_changed` come back 0, the
   honest report would have been that the corrector never fires and the wiring proves nothing.
   15 of 724 is small but non-zero and the destinations are sensible: 13 promotions to GPU-warm are
   what a correction from engine telemetry should look like, since the engine reporting reuse means
   the history is resident when the coordinator thought otherwise.
2. **It quantifies the belief's error rate for the first time.** The coordinator's belief was wrong,
   in a direction the engine could detect, on **15 of 724 observations, about 2.1 percent**, and
   wrong CONSERVATIVELY in 13 of those 15: it said cold where the engine had the history. That is
   the direction `coordinator.py:745-752` already predicts in words, now with a number against it.

**What this does NOT establish**, stated because the gap is the one that matters for v5: a 2.1
percent correction rate on the history-build path is not evidence about the dashcam traffic, where
the wider audit found most reuse happens and where this field does not look. Wiring remains
necessary and not sufficient, and the outcome D151 asks for (the belief tracking residency on
partially built histories) is still unproved.

---

# Section 22's confound, complete at both ends and with no systematic direction

The H100 has now run all three arms section 22 named, so the bound is closed rather than bracketed.

| arm | offline 3 s re-score (decided at 5 s) | live 3 s | difference |
|---|---|---|---|
| b7 (predicted lower bound) | on time 0.3500, correct 0.4000 | 0.3500, 0.4000 | **0 questions** |
| edf (predicted upper bound) | 0.2500, 0.3500 | 0.2000, 0.3000 | **-1 question each** |
| llf (predicted upper bound) | 0.3500, 0.4000 | 0.4000, 0.4500 | **+1 question each** |

**The confound is plus or minus one question of 20, about 5 pp, and it has NO systematic
direction**: the two deferring arms moved by the same magnitude in OPPOSITE directions while the
declining arm did not move at all. That is the best available outcome for section 22.2's table. A
one-sided error of 5 pp would have been a bias to correct for; a two-sided one of the same size is
noise to state. So the offline table stands as a usable stand-in for a live 3 s run, with a plus or
minus 5 pp caveat on arms that defer, and prediction 2 and prediction 3 both hold: b7 moved least
(not at all), and edf and llf moved most (one question each).

**Register:** three arms at one seed is three paired comparisons, not a distribution. The bound is
an observed range over the cells that exist, not a constructed bound, and seeds 5 and 6 will widen
or confirm it rather than being needed to justify it.

---

# The gate's train/test split, and the confound that was checked rather than assumed

**The D151 (6) gate is now fitted and tested on different workloads by design** (user decision):

- **FIT:** `runs/WARMALL_CELLS_1F`, `warm-all-lru` and `warm-all-lru-reactive` at 16 devices, seed 4,
  3 s, on the dashcam-1f workload, cells tagged `_L3_cal1f`.
- **HELD-OUT TEST:** `runs/WARMALL_CELLS`, the same two arms plus a `-off` control and a `kv0.25`
  capacity cell, on the EP-G workload.

Nothing fitted on the 1F cells may be reported as a gate pass. MARGIN_CF is set once, from the
HELD-OUT p90 absolute prediction error, per D154 (2).

**The confound I raised and the H100 closed, recorded here because a train/test split is only as
good as the invariance between its halves.** `warm-all-lru` releases **412 times without a frame
store and 421 with one**, because `sent_bytes_for` only grows when a frame path resolves. Had the fit
cells run without a store and the held-out cells with one, the gate would have been fitted and tested
on arms that behaved differently for a reason unrelated to the workload, and the split would have
been void while looking fine.

**It does not apply, and the reason is structural rather than a coincidence of this run.** The H100's
driver has ONE `cell()` function and ONE command line: every cell, 1F and EP-G, fit and held-out,
gets the same `--frames-root $HOME/data/live2/frames_by_ref` and the same
`--frame-manifest $HOME/data/live2/jpeg/combined_manifest.jsonl`. Only the deadline, pool and
dashcam-format flags vary by tag. Mode is A for every cell.

**And the failure mode is caught rather than tolerated:** the harness's per-cell frames preflight
(`frames_preflight.json`) refuses a run whose frames do not resolve, so an EP-G cell that reaches a
frame the store lacks fails loud instead of quietly sending uuid-only references. That matters
because uuid-only references are exactly what produced a FALSE proof during development: with no
store, the authoring session's first version of proof (a) showed a perfect cached-token rise with
ZERO frames carrying bytes. An `n_unresolved` counter now makes a reference claimed for
never-uploaded bytes visible.

So the two halves of the split differ in the workload and in nothing else that is known to move
these arms. Recorded with the fit, as the H100 asked, so a later reader does not have to re-establish
it.

---

# Held-out cell 1 of 4 SATURATES, and MARGIN_CF's population is damaged in the one direction that matters

**H100, 20:10, `warm-all-lru_n16_s4_1200s_h27_3t_L3_epg` (EP-G plus per-frame).** 1,524 of 6,262
requests non-200 by 20:10, **24 percent**, so the cell is saturated under D144's 5 percent line and
is labelled so. Recorded as a FINDING and not retried, as agreed.

| | count |
|---|---|
| dashcam HTTP 400 | 1,113 |
| robot HTTP 400 | 397 |
| transport | 18 |

**The mechanism is the submission race again, now on EP-G dashcam episodes, and the trigger is
queue depth.** Dashcam was CLEAN for the first five minutes. Then, just before each dashcam
device's first failure, its previous request was still in flight with a **TTFT of 97 to 122 s
against a 1 s deadline**, so the engine queue was about 100 s deep and the next 0.5 s instant's
uuid-only references pointed at a frame the engine had not yet registered. Each device then
cascades, about 185 of about 280 later requests failing.

**This is not a general EP-G fault.** It is warm-everything plus per-frame upload at 16 devices:
per-frame makes the believed holding grow every 2 s instead of every 30 s (measured 3.27x the
prefill pieces for this arm), EP-G adds a persistent episode per dashcam, and warm-all-lru warms
every open session. The first five clean minutes are the evidence: the fault arrives with the
queue, not with the format.

**That is a capacity result worth having on its own.** It is the saturation point for
warm-everything that the offline P1 simulation could not give us, and it is why
`warm-all-lru-reactive`'s 33,103-token peak was never a substitute for it.

## Why this damages MARGIN_CF specifically, and not just this cell's score

D157 (2) sets MARGIN_CF as the p90 of `0.250 x |P_hat - 1[on time]|` over every robot question
released in these four cells. A question returned HTTP 400 has null `prompt_tokens`, so **it is in
the population, counts as missed, and cannot be priced.** On the 1F race cell that was 7 of 20. Here
it is about 400 robot 400s, so most of this cell's released robot questions are unpriceable, and the
H100 expects cell 4 (`_kv0.25`) to do the same. Cells 2 and 3, `-reactive` and `-off`, should be
clean.

**So the population is two damaged cells of four, and the damage is NOT RANDOM. It concentrates on
exactly the long warm-ahead requests whose prediction error the margin exists to capture.** A p90
computed over the survivors would therefore be **biased NARROW in the one direction that matters**:
it drops the hardest-to-predict cases and keeps the easy ones. D154 (2) sets the margin ONCE and
freezes it, so a margin set from this population locks that bias in permanently.

## Recommendation, and it is the user's call because D157 (2) named the population

**Do not set MARGIN_CF tonight.** Compute the p90 over the two clean cells and report it as a
DIAGNOSTIC, explicitly labelled not-the-margin, so the magnitude is known. Set the real margin once
the submission race is fixed and the four cells are re-run on a clean engine.

The reasoning, in one line: a margin whose job is to pay for the cost model's error must not be
measured on a population that systematically excludes the errors it would have been largest on.

Two things this does NOT block. **v5-rules needs no margin and no gate** (D156 (1)), so the night's
live v5 result is unaffected. And the gate's own held-out p90 can still be reported from the clean
cells with the damage stated, because that number is descriptive rather than frozen into the policy.

## The saturation and the race are ONE mechanism, and a prediction for the re-run

**Written BEFORE the `_rf` re-run exists, so it is a prediction and not a rationalisation.**

The H100's per-minute error curve on held-out cell 1:

| minute | 2 | 3 | 4 | 5 | **6** | **7** | 8 |
|---|---|---|---|---|---|---|---|
| errors | 17 | 31 | 73 | 57 | **654** | **596** | 101 |

**That is a cliff, not a gradual degradation**: an 11.5x jump between minutes 5 and 6 on unchanged
code. The dashcam TTFT just before each device's first failure was **97 to 122 s against a 1 s
deadline**, so the queue had crossed the depth at which a 0.5 s instant cadence outruns the engine.
From there each device's own uuid references begin pointing at frames the engine has not registered.

**So the race is the failure MODE and queue depth is the TRIGGER. They are one mechanism, not
two**, which is exactly why the first five minutes were clean under the same code and the same arm.

### The prediction

**The race fix will remove the 400s and will NOT remove the 100 s queue.** So the `_rf` re-run
should come back **valid and still slow**: few or no HTTP 400s, and dashcam TTFTs that still climb
far past the 1 s deadline once the queue builds, with the misses appearing as late deliveries
instead of errors.

**If the re-run comes back both clean AND fast, something other than the race was also at work**,
and that must be found before the cell is used as a capacity number. The most likely candidate
would be that the 400s were themselves relieving the queue, in which case removing them makes the
load strictly worse rather than better, and a faster clean run would mean the comparison is not
measuring what it appears to.

### Why this matters beyond one cell

If the prediction holds, **the capacity limit for warm-everything at 16 devices under EP-G plus
per-frame is a QUEUEING limit, not an error limit**, and the fix converts a visible failure (24
percent non-200) into an invisible one (deliveries past their deadline). That is a worse failure to
read, not a better one, and it is the reason this cell's saturation data was worth preserving under
its own name rather than being overwritten by the re-run.
