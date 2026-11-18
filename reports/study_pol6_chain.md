# StudyPOL6-chain Part A: the inter-piece gap is real, and it is not what pol4 gets wrong

Machine: flash, CPU only. Model under test: **pol4, the frozen model**, unchanged. Data:
**StudyENG1c Part D FIT pairs only** (240 pairs in the record, 360 trials built; 161 of them
chained). No HOLDOUT pair of StudyENG1 Part C, StudyENG1c Part D, StudyENG1d or StudyENG1e was
read. Nothing was fitted and nothing was frozen.

**ERRATUM INDEX.** One claim in this report was wrong and is corrected in **section 11**: that
pol4 never merges a background prefill into a piece's own step. It does, and more often than the
engine does. StudyPOL5 section 1.5 was right. Every place the claim appears is marked ERRATUM
inline. The gap findings (sections 3 to 5), the position decomposition and the granularity
findings are unaffected.

## 0. Outcome in one paragraph

The brief's hypothesis was **H-gap**: that between consecutive pieces of a chained rebuild the
next piece re-enters the front end, the engine serves queued background work in that window, and
a model treating the chain as contiguous over-charges for blocking that did not happen. The gaps
are real and the engine does serve work in them, but **pol4 is not treating the chain as
contiguous**: it prices a front-end window per request, so its own simulation already contains
inter-piece gaps and already schedules background requests inside them, covering 55 % to 70 % of
the measured gap time, and it reproduces a chain's total wall-clock span to within 1 %. Over the
161 chained FIT trials the gap position carries **31.3 s of the 303.9 s over-prediction (10 %)**,
while background requests whose first token lands **while the engine is actually prefilling a
piece** carry **270.5 s (89 %)**. So H-gap is **contradicted as an explanation** of the residual,
and the brief's STOP AND ASK condition fires. What the data points at instead is a step-structure
error, named here **H-granularity with H-merge**: pol4 gets each piece's prefill *duration* right
to within 5 % to 12 % but puts it in **one** step where the engine really uses about **1.8**
[ERRATUM, section 11: the clause that followed here, that pol4 never lets a background prefill
share a piece's step, was wrong; pol4 merges more often than the engine does, and the mechanism is
restated as H-overmerge].
That alternative cannot be turned into parameters from this data, because StudyENG1c does not
record which requests were in which step; Part A's per-step composition is derived by
subtraction. StudyENG1e-chain measures it.

## 1. What was pre-checked, and how

The measurement is **DERIVED and FIT**, labelled that way in every output. StudyENG1c records no
per-request step membership, so every per-piece engine time uses **StudyENG1d's own attribution
method**, applied unchanged (`experiments/cost/study_eng1d_analyse.py` docstring, "Action timing
(engine)"):

- a piece's **first scheduled time** `t_sched` = its client first-token time minus the stat-log
  plugin's `prefill_time` for that request id (`fin[...]["pf"]`, scheduled to first token);
- a piece's **prefill end** `t_end_eng` = the time of the last step row at or before the client
  first-token time, with StudyENG1d's own 2 ms slack;
- a step's **wall duration** = the difference of consecutive step-row times. The plugin's
  `elapsed_ms` is **not** the step's wall duration and is not used as one: on a monolithic 11k
  prefill its median is 0.03 ms. A first draft of this analysis used it and produced a 3e-05 s
  median step; a test now pins the definition.
- a step **carries other work** if its first-output computed tokens (`pts`[0]) are positive or it
  reports generation requests (`it`[3] > 0). The `it` layout is
  `[iteration_index, num_ctx_requests, num_ctx_tokens, num_generation_requests,
  num_generation_tokens, elapsed_ms, num_encoder_inputs, num_encoder_output_tokens, is_dummy]`
  (`experiments/cost/eng1_statlog/eng1_statlog.py`).

**Clocks.** StudyENG1c's client rows and the engine's step log carry the same wall clock. Checked
rather than assumed: for every chained piece, `t_first - pf` falls strictly between `t_submit` and
`t_first`. No calibration is applied.

**Gap definition.** The window in which the engine is free of the chain:
`gap_k = t_sched(piece k+1) - t_end_eng(piece k)`, decomposed into the previous piece's engine
tail, the client's own turnaround, and the next piece's front-end window.

**Metric.** Per-request attribution uses **TTFT**, because the mechanism acts on when a request
reaches its first token. Trial-level over-prediction is reported for **both** of T0b's
definitions (latency sum, the ENG1c primary; TTFT sum, the secondary).

## 2. Mechanism verification (recorded before any conclusion)

**Step 1, the causal chain.** If the physical component of context inertia is real
(FORMULATION.md: reconstruction cost grows with context length), a cost model must price what a
reconstruction costs *others*, not only itself. A chained rebuild is a sequence of separate
requests, so between pieces the engine holds no chain work; if the model instead treats the chain
as one contiguous occupancy, then a background request arriving in such a window is charged a
wait it never served, so the model's imposed delay exceeds the measured one, and the excess is
carried by exactly those requests that were served inside a gap. Each link is a quantity in the
record: the gap exists (step-log times), the engine serves work in it (step composition), the
model charges for it (the simulator's own step log), the excess appears (paired with-minus-without
sums).

**Step 2, instantiate each link.**

| causal link | implementing quantity | value / range on ENG1c Part D FIT | varies as expected? | evidence |
|---|---|---|---|---|
| a chain has inter-piece gaps | `gap_s` between consecutive pieces | 1,235 gaps, median 45.7 ms, IQR 32.7 to 73.7 ms, max 280 ms | yes, present for every chained trial and absent for mono (0.0) | section 3 |
| the gap is the next piece's front-end window | `frontend_window_s` / `client_turnaround_s` / `engine_tail_s` | 42.4 ms / 0.6 ms / 2.9 ms medians | yes, the front-end window dominates | section 3 |
| the engine serves others in the gap | steps in the gap carrying other work | 841 of 1,235 gaps contain a step boundary, and **all 841** carry other work; median 1 step, up to 1,512 other prefill tokens | yes | section 3 |
| the model charges the gap as occupancy | pol4's own simulated inter-piece gaps | **NOT ABSENT, and not zero**: 0.284 s per chain (piece1024) and 0.217 s (piece2048) against measured 0.513 s and 0.312 s | **LINK FAILS AS STATED**: pol4 is not contiguous | section 4 |
| the excess is carried by gap-served requests | over-prediction by position of the background first token | gap 31.3 s of 303.9 s (10 %); busy 270.5 s (89 %) | **LINK FAILS AS STATED** | section 5 |

Two links fail, and they are the two that H-gap needs. Under the protocol that is a stopping
condition for building on H-gap, and it is why no pol6 term was fitted. It is **not** a stopping
condition for reporting, because the links that failed failed by being *measured and found
false*, not by being absent: every quantity was instrumented, non-zero and varying.

**Step 3, one representative unit.** One chain, cell `27|P25|piece1024` trial 1, 12 pieces. The
first four pieces, all times in seconds on the shared wall clock:

| piece | t_submit | t_sched (derived) | t_end_eng (derived) | pf | queued | gap to next |
|---|---|---|---|---|---|---|
| 0 | 1794907086.4956 | 1794907086.5084 | 1794907086.7018 | 0.19508 | 0.00002 | 0.0179 |
| 1 | 1794907086.7046 | 1794907086.7197 | 1794907086.9104 | 0.19217 | 0.00001 | 0.0715 |
| 2 | 1794907086.9124 | 1794907086.9819 | 1794907087.1748 | 0.19428 | 0.00001 | 0.0460 |
| 3 | 1794907087.1771 | 1794907087.2208 | 1794907087.5801 | 0.36294 | 0.00001 | - |

Reading the arithmetic by hand: piece 0 is handed to the engine 12.8 ms after submission, prefills
for 193 ms, and returns; piece 1 is submitted 0.3 ms later and handed over 15.1 ms after that, so
the engine is free of the chain for 17.9 ms. The queued time is 10 to 20 microseconds throughout,
so **the gap is not engine queueing**, it is the front end. Nothing was bound by the KV or
accelerator budget in this unit; the binding quantity is front-end service time.

**Step 4, negative control.** The control is built into the design rather than simulated: the
**mono11k** action is the same 11k-token rebuild delivered as a single request, so the mechanism
under test is structurally absent. It behaves exactly as the absence predicts: measured gap total
**0.0 s**, zero other prefill tokens inside its own steps, `max ctx_req` 1 (it exceeds the step
budget and runs alone), pol4 gets its step count right (2.0 against 2.0), and its over-prediction
ratio is **1.13**, the smallest of the three actions, against 1.92 and 1.69 for the chained ones.
A second control is the degenerate arm of the piece variants themselves: 79 trials where the
history was already resident, so `n_parts` is 1 and there is no chain. Their over-prediction is
**0.018 s**, ratio 0.013 and 0.007, essentially exact. Both controls move the result, so the
chained structure, not the action label, is what carries the error.

**Step 5, alternative explanations.** Three produce an over-predicted imposed delay for chained
pieces and are distinguished as follows.

- **H-gap** (the brief's): the model misses the inter-piece windows. *Distinguished by* pol4's own
  simulated gap time and the position of the excess. Both say no: pol4 has 55 % to 70 % of the gap
  time and 89 % of the excess sits outside the gaps. **Rejected as the explanation.**
- **H-granularity**: the model puts a piece's prefill in one long step where the engine uses
  several short ones, so a mid-prefill arrival waits too long. *Distinguished by* steps per piece
  and per-step duration, with the piece's total prefill span held fixed. Supported: 1.75 and 1.92
  steps measured against pol4's 1.0, per-piece prefill span measured 0.242 s and 0.454 s against
  pol4's single steps of 0.271 s and 0.479 s, so the **total is right to 5 to 12 % and the
  granularity is wrong by about 1.8x**.
- **H-merge**: the engine admits a background prefill into a step a piece is already prefilling
  in, and the model never does. *Distinguished by* per-step composition. The engine's half is
  supported: of a piece1024 chain's 20 steps, 17 share with other work (8 with other prefill
  tokens, 12 with decodes), median 3,780 other prefill tokens inside the pieces' own steps,
  `max ctx_req` 2. **ERRATUM, section 11: the model's half is wrong.** pol4 was never measured
  here and does merge, on 54.98 % and 69.31 % of chained piece steps, more often than the engine.
  The surviving form of this alternative is **H-overmerge**: pol4 admits too many prefills into
  one over-long step and charges that step's duration to all of them.

H-granularity and H-merge are **not** distinguished from each other by this data, and they are
not independent: both would shorten a mid-prefill arrival's wait, and the derived composition
cannot say whether the extra step per piece is a token budget, an encoder budget, or the merge
itself. Saying which is the measurement StudyENG1e exists for, so Part A stops here rather than
choosing.

## 3. The gaps are real (brief item 1a, 1b)

1,235 inter-piece gaps over 161 chained FIT trials.

| quantity | median | IQR | min | max |
|---|---|---|---|---|
| gap (engine free of the chain) | 45.7 ms | 32.7 to 73.7 ms | 13.0 ms | 280.0 ms |
| next piece's front-end window | 42.4 ms | 29.3 to 70.1 ms | 10.9 ms | 275.9 ms |
| client turnaround | 0.6 ms | 0.4 to 0.8 ms | 0.1 ms | 1.5 ms |
| previous piece's engine tail | 2.9 ms | 2.4 to 3.4 ms | 1.1 ms | 11.9 ms |

Per action: piece1024 825 gaps, gap median 38.8 ms, front-end window 34.9 ms; piece2048 410 gaps,
48.2 ms and 44.1 ms. Per chain the gaps total a median **0.513 s** (piece1024, 11 to 12 pieces)
and **0.312 s** (piece2048, 6 pieces).

**The engine does serve background work in them.** 841 of the 1,235 gaps contain at least one
step boundary, and **every one of those 841 carries other work** (other prefill tokens or
decodes); median 1 step per gap, up to 3, median 0 and up to 1,512 other prefill tokens. The
remaining 394 gaps are shorter than one step and contain no boundary at all. Counting background
requests by where their first token lands, **374 of the 6,221 matched background requests** got
their first token inside a gap (median 3 per chain for piece1024, 2 for piece2048).

So brief items 1a and 1b are answered and the hypothesis's *premise* holds.

## 4. But pol4 is not treating the chain as contiguous (brief item 1c)

pol4's `EngineSim` prices a front-end window for **every** request from its body size, then hands
it to the engine at that instant. A chain's pieces are therefore handed over progressively in the
simulation too, and the simulator's own step log names which requests are prefilling in each
step, so its occupancy is read off rather than assumed.

| quantity (medians per chain) | piece1024 | piece2048 |
|---|---|---|
| measured gap total | 0.513 s | 0.312 s |
| **pol4's own simulated gap total** | **0.284 s** | **0.217 s** |
| fraction of the gap pol4 already has | 55 % | 70 % |
| background requests in a measured gap | 3 | 2 |
| background requests in a **pol4** gap | 3 | 3 |
| measured chain span (first t_sched to last prefill end) | 3.332 s | 2.925 s |
| **pol4's simulated chain span** | **3.318 s** | **2.946 s** |

pol4 therefore (a) has inter-piece gaps, (b) schedules at least as many background requests
inside them as the measurement does, and (c) reproduces the chain's total wall-clock span to
within 1 %. There is no contiguity error to remove.

**And closing the remaining gap difference would not be an improvement.** The gap is the next
piece's front-end window, and a chained piece is the awkward corner for both front-end models: a
tiny body carrying many images (median 0.011 MB and 11 derived images for piece1024, 0.0132 MB
and 23 for piece2048).

| front-end window per piece | piece1024 | piece2048 |
|---|---|---|
| pol4's body-size term | 29.8 ms | 29.9 ms |
| StudyPOL5's image-aware term | 58.2 ms | 95.4 ms |
| **measured median** | **34.9 ms** | **44.1 ms** |

pol4 is low by 5 ms and 14 ms; the image-aware term is high by 23 ms and 51 ms. Substituting it,
which is what `piece_gap_scheduling` does, would **overshoot** the measured gaps rather than
correct them. The flag is implemented because the brief asks for it, and is **off by default**
with this recorded as the reason.

## 5. Where the over-prediction actually is (the quantification)

Every matched background request of the 161 chained FIT trials, classified by where its first
token landed relative to the chain. Sums of TTFT-sum seconds over all trials.

| position of the background first token | n | measured delay | predicted delay | over-prediction | share | error in the with-arm | error in the without-arm |
|---|---|---|---|---|---|---|---|
| **busy** (engine prefilling a piece) | 1,468 | 288.5 s | 559.0 s | **+270.5 s** | **89.0 %** | +265.1 s | -5.4 s |
| **gap** (engine free of the chain) | 374 | 113.9 s | 145.2 s | +31.3 s | 10.3 % | +29.4 s | -1.9 s |
| post_chain | 2,306 | 31.4 s | 33.4 s | +2.0 s | 0.7 % | -5.8 s | -7.9 s |
| pre_chain | 2,073 | -0.1 s | 0.0 s | +0.1 s | 0.0 % | -6.4 s | -6.5 s |
| total | 6,221 | 433.7 s | 737.6 s | +303.9 s | 100 % | | |

Two readings, both load-bearing. First, **the gap position accounts for a tenth of the error**;
per trial the gap-attributable share of the over-prediction has median 0.077 (piece1024) and
0.037 (piece2048), IQR 0 to 0.20 in both. Second, **the error is in the with-arm prediction, not
the without-arm**: +265.1 s against -5.4 s on the busy position, so the model is not mis-pricing
the background load in general, it is mis-pricing what happens to a background request that
arrives while a piece is prefilling.

Trial-level, for completeness, in both of T0b's definitions:

| action (chained) | n | over-prediction (TTFT) | ratio (TTFT) | over-prediction (latency) | ratio (latency) |
|---|---|---|---|---|---|
| piece1024 | 79 | 1.628 s | 1.917 | 2.537 s | 1.827 |
| piece2048 | 82 | 2.185 s | 1.694 | 3.040 s | 1.593 |
| mono11k (control) | 120 | 1.120 s | 1.125 | - | - |
| piece variants, n_parts = 1 (control) | 79 | 0.018 s | 0.013 / 0.007 | - | - |

Medians. The chained ratios reproduce StudyPOL5's independently measured in-window ratios on a
different collection (see consistency check 1).

## 6. The leading alternative, with its FIT evidence

**pol4 gets a chain's total right and its step structure wrong.**

| quantity (medians) | piece1024 | piece2048 | mono11k (control) |
|---|---|---|---|
| steps per piece, measured | 1.75 | 1.92 | 2.0 |
| steps per piece, pol4 | 1.0 | 1.0 | 2.0 |
| per-piece prefill span, measured | 0.242 s | 0.454 s | 2.171 s |
| per-piece prefill wall time pol4 charges | 0.271 s | 0.479 s | - |
| median step duration, measured | 0.157 s | 0.170 s | 0.610 s |
| median step duration, pol4 | 0.271 s | 0.479 s | 1.103 s |
| steps a piece shares with other work, **engine** | 17 of 20 | 10.5 of 11.5 | 1 of 2 |
| steps a piece shares with a background prefill, **pol4** (ERRATUM, section 11) | 54.98 % | 69.31 % | 2.05 % |
| other prefill tokens inside the piece's own steps | 3,780 | 3,402 | **0** |
| max `ctx_req` in a piece's steps | 2 | 2 | **1** |
| implied prefill rate | 4,080 tok/s | 4,130 tok/s | 4,943 tok/s |

A background request arriving mid-prefill waits, in pol4, for the end of **one** step of 0.271 s
or 0.479 s; really it waits for the end of one of about 1.8 steps of 0.157 s or 0.170 s. The ratio
of expected waits under a uniform arrival is roughly 1.7 to 2.8, which brackets the observed
over-prediction ratios of 1.92 and 1.69. For mono the mechanism is absent, and the ratio is 1.13.

**ERRATUM, section 11.** An earlier version of this paragraph added "and may instead be merged
into the piece's own step", implying pol4 does not merge. It does, more often than the engine, and
that makes the granularity error worse rather than offsetting it: a merged background request is
charged the whole of pol4's over-long step. Corrected mechanism: **H-granularity with
H-overmerge**.

This is a **hypothesis with FIT evidence, not a finding**: the per-step composition is derived by
subtracting the action's own computed tokens from each step's first-output tokens, which cannot
attribute a step to a request. See consistency check 6.

## 7. Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run (ENG1c Part D FIT) | prior committed | source of prior | ratio | agree |
|---|---|---|---|---|---|
| imposed-delay over-prediction ratio, piece1024 | 1.917 (TTFT) | 1.83 in-window | StudyPOL5 section 1, ENG1d | 1.05 | agree |
| imposed-delay over-prediction ratio, piece2048 | 1.694 (TTFT) | 1.62 in-window | StudyPOL5 section 1, ENG1d | 1.05 | agree |
| imposed-delay over-prediction ratio, mono11k | 1.125 (TTFT) | 1.13 in-window | StudyPOL5 section 1, ENG1d | 1.00 | agree |
| imposed-delay ratio, piece1024, latency | 1.827 | 0.6188 pass fraction, residual "about 1.6x", piece-concentrated | StudyT0b Part 2 FIT dry run | n/a, same direction | agree |
| front-end window, small multi-image body | 34.9 to 44.1 ms | 39.2 ms for a 0.47 MB episodic body | StudyPOL5 section 2, ENG1d | 0.89 to 1.13 | agree |
| per-piece engine queued time | 0.00001 to 0.00002 s | queueing not the mechanism behind pieces | StudyPOL5 section 1 | n/a | agree |

Nothing disagrees by more than 1.13x. The two collections are independent (ENG1d is the H100
loaded-arrival study, ENG1c the host-full study), so the agreement on the three action ratios is a
genuine replication of StudyPOL5's localization, not a restatement.

**2. Physical plausibility.** Implied prefill rates: 4,080 tok/s for a chained piece1024 piece
(1,001 new tokens in 0.242 s), 4,130 tok/s for piece2048 (2,079 in 0.454 s), 4,943 tok/s for
mono11k (11,032 in 2.171 s), all on the H100 NVL with the multimodal encoder in the path. mono is
the fastest, which is the expected direction: a long prefill amortizes per-step and per-request
overhead over more tokens, so the pieces must be slower per token, and they are. No measurement
here implies a rate faster than the fastest committed one on this stack, so there is no caching
artifact to flag. The derived gap times are bounded below by one step boundary at each end; the
per-gap step count is reported (median 1) so a reader can bound that error, and it cannot exceed
the step duration, which is 0.157 to 0.170 s against gaps of 0.039 to 0.048 s. That is the
largest single uncertainty in section 3 and it is the reason StudyENG1e is needed.

**3. Distribution sanity.** Every median in this report is published with its IQR or its min and
max in `pol6_partA_gap.json`, and nothing agrees to more precision than the inputs vary: the
1,235 gap values span 13.0 to 280.0 ms, the 161 chained trials' TTFT over-predictions span -0.017
to 4.307 s. One ratio is unstable by construction and is reported as such: the per-trial
gap-attributable *share* has min -3.18 and max 0.52, because it divides by a per-trial
over-prediction that can approach zero; the IQR (0 to 0.20) and the pooled totals in section 5
are the summary, not the mean of the ratio.

**4. Definition audit.** "Imposed delay": both committed definitions are reported, the latency sum
(StudyENG1c Part D's own published quantity, T0b primary) and the TTFT sum (StudyENG1 section 9,
T0b secondary); per-request attribution uses TTFT, stated in section 1. "Step": the difference of
consecutive step-row times, which is StudyENG1d's definition; **not** the plugin's `elapsed_ms`,
which is a different quantity and whose misuse is pinned by a test. "Piece": one `inject` row with
its own `part_i`, so a chain of `n_parts` pieces is `n_parts` separate engine requests. "Gap":
defined in section 1, and decomposed so the front-end share is visible rather than assumed.
"Encoder unit" and "repeatability ceiling": unchanged from StudyPOL4 Part 1b and not used here.
"Chained": `n_parts > 1`; the 79 piece-variant trials with `n_parts == 1` are reported as a
separate control and never pooled with the chained ones.

**5. Claim linkage.** C4, the physical component of context inertia: this bears on it and
*narrows* it. The model's pricing of a reconstruction's own cost stands (it reproduces a chain's
span to 1 % and a piece's prefill duration to 5 to 12 %), so the physical component remains real
and largely priced; what is not trustworthy is the delay a chained reconstruction imposes on
others, and Part A localizes that to step structure rather than to chain structure. C5, joint
policy beats decomposed: not tested here. C6: not tested here. Nothing measured falls outside
FORMULATION.md's scope; no KV transfer between heterogeneous tiers is involved.

**6. Proxy validity.** One proxy, and it is the reason this is Part A and not Part B. Per-step
request membership is **not** recorded by StudyENG1c; the per-step composition in section 6 is a
**proxy** obtained by subtracting the action's own computed tokens from the step's first-output
computed tokens. It measures how many prefill tokens in a step were *not* the action's; it does
**not** measure which request they belonged to, nor which of a piece's tokens went in which step.
It is valid for the headline of sections 3 to 5, which need only whether a step carried other
work at all and where a background first token landed, both of which come from timestamps and
counters rather than from the subtraction. It is **not** valid for the headline of section 6, so
H-granularity and H-merge are marked a hypothesis with FIT evidence, the affected analysis is
**unvalidated**, and no pol6 parameter is fitted from it.

## 8. Rule 2 classification

The brief's hypothesis produced a negative. Classified: **real negative**, not inconclusive. Every
link of H-gap's chain was instrumented, non-zero and varying (Step 2); the gaps exist in the
measurement and in pol4's simulation; the negative controls moved the result in both directions
(mono and the `n_parts == 1` arms collapse to 1.13 and 0.013); and the hypothesis failed by being
measured and found not to carry the effect, at 10 % of it. H-gap is therefore a settled finding as
an *explanation of the residual*: it is not one. It remains true as a *description of the engine*,
which is a separate statement and is recorded as such in section 3.

## 9. What was built, and what is deliberately not built

**pol6 exists and is not the model.** `policy/pol6_engine.py`, selectable by flag, every flag off
by default, not wired into `eng1_engine.py` and not frozen. pol4 stays the frozen and default
model. `pol6_terms.json` carries **no coefficient of its own** (a test refuses a terms file that
does), because Part A fitted nothing; the one active number set, StudyPOL5's image-aware
front-end coefficients, is loaded from StudyPOL5's committed JSON **by reference** rather than
copied, and a test walks the module's AST to confirm no coefficient is typed into it.

- `piece_gap_scheduling`: **implemented**, off by default. It re-times a chain's hand-off instants
  by the difference between the image-aware and body-size front-end windows, which needs no
  change to the frozen module. Recorded as unable to explain the residual, and as overshooting
  the measured windows (section 4).
- `step_granularity`, `in_step_merge`: **not implemented**. Turning either on raises, rather than
  silently running an unparameterised rule.

**Parameters awaiting StudyENG1e** (`pol6_engine.AWAITING_ENG1E`): how many new tokens of a
multimodal piece the engine puts in one step; whether and under what admission condition a
background prefill joins a step a piece is already prefilling in; and whether the extra step per
piece is forced by an encoder or multimodal input budget rather than the token budget. Part A
cannot separate the last two.

**The StudyENG1e loader is a stub, by design.** `policy/eng1e_replay.py` declares the fields Part
B needs (`REQUIRED_STEP_FIELDS`, `REQUIRED_MEMBER_FIELDS`) **before** the schema is seen, so the
requirement cannot be quietly reshaped to whatever arrives; parses any row set carrying them;
refuses StudyENG1e HOLDOUT rows without an explicit authorization string, with no holdout object
constructed on a refused read; and refuses to guess a filename until ENG1e's report and split file
both exist. 34 tests, including a synthetic three-step example in which an action prefills over
two steps and shares the second, exercising `steps_per_request`, `merge_rate` and
`other_prefill_tokens` against hand-checkable values.

**Freeze intact.** All 12 StudyT0b freeze md5s verify; `results/cost/` is untouched. 350 tests
pass (316 before this study, 34 new, two of which caught my own errors: `elapsed_ms` used as a
step duration, and a structural `0.0` mistaken for a fitted coefficient).

## 10. Why Part A stops here

The brief's STOP AND ASK fires on its first clause: Part A found the gap hypothesis contradicted
by existing data, and section 5 reports what the data shows instead. Part B's diagnosis step
("which of H-gap, H-merge, H-other explains the over-prediction") is now partly answered on FIT
and should be re-scoped: H-gap is out at 10 %, and the question for ENG1e is whether granularity
or merge, or their interaction with the encoder budget, carries the 89 %. Fitting a pol6 term now
would mean choosing a structural parameter from a derived proxy, which is the second STOP AND ASK
clause. Nothing is frozen and the ENG1e HOLDOUT is untouched.

## 11. Addendum: who merges, and the erratum against this report

Asked before Part B, and settled by measurement rather than by reading either report. pol4 is
deterministic and its own step log names the requests prefilling in each step
(`EngineSim.run` -> `steps[i]["prefilling"]`), so the question is checkable.
`experiments/orchestration/policy/diagnose_pol6_merge.py` counts, on FIT pairs of both
collections, every simulated step in which an **action** request is prefilling and asks whether a
**background** request is prefilling in the same step. Decodes are counted separately and are not
a merge of prefills. Output: `results/orchestration/study_pol6/pol6_partA_merge_addendum.json`.

### 11.1 The verdict: StudyPOL5 section 1.5 is right, this report's section 6 was wrong

| input | action | action steps | shared with a background prefill | fraction | max prefills in one action step |
|---|---|---|---|---|---|
| ENG1c Part D FIT, **chained** | piece1024 | 904 | 497 | **0.5498** | 6 |
| ENG1c Part D FIT, **chained** | piece2048 | 492 | 341 | **0.6931** | 8 |
| ENG1c Part D FIT, n_parts = 1 | mono11k | 195 | 4 | 0.0205 | 2 |
| ENG1c Part D FIT, n_parts = 1 | piece1024 | 43 | 3 | 0.0698 | 2 |
| ENG1c Part D FIT, n_parts = 1 | piece2048 | 39 | 6 | 0.1538 | 2 |
| **ENG1d FIT** (bytes-carrying) | mono11k | 120 | 0 | **0.0000** | 1 (21 in any step) |
| **ENG1d FIT** (bytes-carrying) | piece1024 | 60 | 10 | 0.1667 | 4 |
| **ENG1d FIT** (bytes-carrying) | piece2048 | 60 | 7 | 0.1167 | 3 |

**StudyPOL5 section 1.5 reproduces.** It reported 54 % for piece1024 and 66 % for piece2048 on
ENG1c Part D FIT, with 4 % for mono11k. The chained measurement here is **54.98 %** and
**69.31 %**; pooling the `n_parts == 1` trials of the same variant gives 52.80 % and 65.35 %.
StudyPOL5's 54 % and 66 % therefore sit inside the range the two plausible denominators span, and
its mono figure (4 %) is within two points of the 2.05 % measured here. The exact denominator
cannot be recovered because those three figures were typed into StudyPOL5's report and are **not
present in its committed `pol5_diagnosis.json`**; that is a provenance weakness in StudyPOL5, now
closed by committing the measurement here. Its substantive claim stands, and no erratum is raised
against it.

**ERRATUM AGAINST THIS REPORT.** Section 6's clause that pol4 "never lets a background prefill
share a piece's step" is **false**. It was inferred from reading `EngineSim._schedulable`, which
admits strictly FCFS at step boundaries, and was never measured; I stated an inference as a
measurement. pol4 merges on 55 % and 69 % of chained piece steps, which is **more often** than
the engine does (a derived 8 of 20 and 5.5 of 11.5 piece steps carry other prefill tokens, 40 %
and 48 %), and it admits up to 6, 8 and 21 prefills into a single step against the engine's
observed maximum `ctx_req` of **2**. Every occurrence is marked inline; the corrected statement is
in `pol6_terms.json` under `partA_verdict.leading_alternative`, with the superseded wording kept
in `statement_erratum`.

### 11.2 Why this strengthens rather than weakens Part A's conclusion

The correction does not touch any measured quantity in sections 3 to 5: the gaps, pol4's own
simulated gap time, the chain-span agreement and the position decomposition (89 % busy, 10 % gap)
all stand. What changes is the *name* of the in-step mechanism.

A missing merge would have been a reason pol4 waits too long. The opposite is true, and it is
worse: pol4 pours many background prefills into a piece's single over-long step and then charges
**that step's duration to every one of them**. A request merged into pol4's 0.271 s or 0.479 s
step reaches its first token at the end of it; the same request in the engine joins one of about
1.8 steps of 0.157 s or 0.170 s, with at most one other request beside the piece. Over-merging
into an over-long step therefore *amplifies* the granularity error rather than offsetting it,
which is consistent with the direction of the residual (over-prediction, +265.1 s on the with-arm
of the busy position). The mechanism is restated as **H-granularity with H-overmerge**, and the
`in_step_merge` flag's description is corrected accordingly: what Part B must fit is not whether
to merge but **how many prefills a step may hold and how long that step then takes**.

### 11.3 The ENG1c versus ENG1d puzzle, stated and left open

The two collections disagree about the **engine**, not only about the model.

| | ENG1c Part D chains (uuid references) | ENG1d pieces (images as bytes) |
|---|---|---|
| engine merges background prefill into a piece's step | yes, a derived 40 % and 48 % of piece steps | **no: 0 of 248 in-window arrivals admitted** (StudyENG1d section 6) |
| pol4 merges, measured here | 54.98 % and 69.31 % | 16.67 % and 11.67 % |
| action shape | 6 to 12 chained requests, 1,024 or 2,048 new tokens each | one request |
| measured front-end window | 34.9 ms and 44.1 ms | 0.1 to 0.2 s for pieces, 0.7 s for mono11k under load |

So pol4 over-merges on **both** inputs, by a larger margin on the ENG1c chains. But the engine's
own behaviour differs between the two, and that difference is not explained by anything measured
in either study. Two candidate reasons, neither tested: the ENG1c pieces carry **uuid references**
to images already in the processor cache, so their front-end window is tens of milliseconds and
the encoder may be flushed, while the ENG1d pieces carry **image bytes**, so their window is
hundreds of milliseconds and the encoder is loaded on the critical path; and the ENG1c chain
presents a new request every ~45 ms, which keeps a queue standing at each step boundary in a way a
single ENG1d piece does not.

This is exactly the comparison **StudyENG1e-chain mode A against mode B** is collecting (mode B
ENG1c-exact with cached uuid references and the encoder flushed; mode A bytes, as in ENG1d), so
Part A does not choose between them. One caveat on the table's first row, which matters for how
much weight it can carry: ENG1c's figure is **DERIVED by subtraction** and ENG1d's is from its own
per-request analysis, so the two are a proxy and a measurement, not two measurements. ENG1e's
per-step membership makes both sides measured.

### 11.4 What Part B should fit, re-scoped

On ENG1e FIT, per injection mode, with the true membership:

1. **step granularity**: engine steps per piece, and what bounds them;
2. **in-step merging**: how many prefills a step holds and whose tokens they are, against pol4's
   up-to-6, 8 and 21;
3. **encoder budget**: encoder inputs per step, as the candidate that separates mode A from mode B.

The target is the **89 %** in-step residual, not H-gap. Nothing is fitted until ENG1e is
committed.

## 12. Files

New:

- `experiments/orchestration/policy/diagnose_pol6_gap.py`
- `experiments/orchestration/policy/pol6_engine.py`
- `experiments/orchestration/policy/eng1e_replay.py`
- `experiments/orchestration/policy/tests/test_pol6_chain.py`
- `results/orchestration/study_pol6/pol6_partA_gap.json`
- `results/orchestration/study_pol6/pol6_terms.json`
- `reports/study_pol6_chain.md`

Added by the section 11 addendum:

- `experiments/orchestration/policy/diagnose_pol6_merge.py`
- `results/orchestration/study_pol6/pol6_partA_merge_addendum.json`

Modified: `research/EXPERIMENTS.md`, `research/STATUS.md`, `results/INDEX.md` (one insertion each,
plus one amendment row for the addendum); `reports/study_pol6_chain.md`,
`experiments/orchestration/policy/pol6_engine.py` and
`results/orchestration/study_pol6/pol6_terms.json` carry the section 11 erratum.
