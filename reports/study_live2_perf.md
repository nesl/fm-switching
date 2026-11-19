# StudyLIVE2-perf: bounding the policy's per-period decision cost

This file carries the design work for StudyLIVE2-perf. The measured results of the row live in
`reports/study_live2_coord.md` section "StudyLIVE2-perf"; this is the forward-looking half.

**DESIGN NOTE ONLY. No code was written for anything in this file, nothing here was measured,
and nothing here is authorized. Every cost figure is an estimate derived from the measurements
cited, and each option is written so that its fidelity risk and its test are on the record before
anyone implements it.**

## Bounding decision cost: options

### What has to be bounded, and the shape of the problem

The decision period is 100 ms for every arm (D99). The measured decision latency of `policy-core`
on the committed 180 s dry fixture, after the 1.4 to 1.6x speed-up this row delivered:

| devices | decision p50 | decision p99 | over the 100 ms period |
|---|---|---|---|
| 32 | 20.2 ms | 100.6 ms | 1.01x |
| 64 | 50.7 ms | 252.5 ms | 2.5x |
| 128 | 121.6 ms | 994.8 ms | 9.9x |

(Updated after Option 0 was implemented; see `study_live2_coord.md` section P7.) The cost is
superlinear in fleet size: 100.6 to 252.5 is 2.51x for a doubling, and 252.5 to 994.8 is 3.94x,
so the empirical exponent runs from about 1.3 to 2.0. The reason is visible in
the profile and in the code, and it is a product of two factors:

* **candidates per period.** Every undecided SH instant is a candidate (D62), and each is priced
  by its own rollout. MEASURED (`policy/measure_rollout_reuse.py`, 120 s fixtures): the median
  period runs 14 rollouts at 8 devices, 40 at 32 and **60 at 64**, with a p90 of 172 and a worst
  period of 344 at 64 devices. An earlier draft of this note estimated "around 30" at 64 devices;
  the real number is twice that at the median and far worse in the tail.
* **devices per rollout.** `Rollout._terminal` sums a state value over every device and every
  representation it holds (`policy/rollout.py`, the loop over `f.devices` calling
  `readiness.state_value`), so one rollout is O(devices). It is 36.9 s of a 71.3 s profiled
  64-device cell.

32 devices now MEETS the period (1.01x, inside run-to-run variation). The gap left to close is
2.5x at 64 and 9.9x at 128.

So the per-period cost is roughly O(candidates x devices), which at a fixed ratio of candidates
to devices is O(devices^2). **Any option that does not attack one of those two factors cannot
change the exponent, only the constant.** The 1.9x this row delivered in total was entirely
constant-factor work, which is why it does not close the gap at 64 or 128.

One more constraint frames every option below. The candidates in a period are NOT independent:
on an admit the coordinator does `fleet.pending += items` (`policy/coordinator.py:299`) and
appends the episode (`:305-308`), and the next candidate's DeltaJ is a rollout over that same
fleet. Pricing candidate k therefore depends on what candidates 1..k-1 committed. That is why
parallel evaluation across workers was rejected in this row, and it is the thing each option
below either preserves or deliberately approximates.

---

### Option 0: memoise the terminal state-value sum across candidates (no decision changes)

**Not one of the three the brief lists, and it is put first because it is the only one with no
fidelity risk at all.**

*What it is.* `state_value(pf, device, rep, demand, h_s, qtype, link, deadline_s, omega_rc, ...)`
is a pure function of its arguments. Within one period the rollouts for successive candidates
differ only in the devices the earlier admits touched; every other device's beliefs, demand,
link and episode list are identical objects' values, cloned but unchanged. Today each candidate's
`_terminal` recomputes all of them.

*What changes in the decisions.* Nothing, if the cache key is complete. The returned value is the
value that would have been computed.

*Expected cost.* It attacks the devices-per-rollout factor directly. If a period admits k
candidates and each admit touches one device, the terminal sum goes from O(k x devices) to
O(devices + k). On the profile that is most of the 36.9 s `_terminal` share, so a 64-device cell
would plausibly land near or under 100 ms at p99. It does not help the first rollout of a period,
only the second onward, so it is worth least at k = 1 and most where the problem is worst.

**IMPLEMENTED 2026-11-18 and reported in `study_live2_coord.md` section P7.** The premise held:
the memo serves 98.9 % of calls at 64 devices. The gain was smaller than the hit rate suggests
(1.11 to 1.16x on the 180 s fixture, 1.52x on a 60 s one) because the terminal sum is a large
share of a rollout but not all of it. 32 devices now meets the period; 64 and 128 do not.

*Fidelity risk.* Zero in principle, and entirely concentrated in one engineering question: is the
key complete? A missing field means a stale value and a silently different decision. The
arguments include a mutable belief (`device.history[rep]`: probs, size, staleness), a demand
model, a link, the episode list (through `in_episode`), `exclude_job` and `credit_allowed`.

*How we would test it.* (1) The D99 equivalence grid, decision logs byte-identical, which is the
check this row already used three times. (2) A key-completeness test that is stronger than the
grid: run with the cache in SHADOW MODE, computing both the cached and the uncached value on
every call and asserting equality, over the full fixture set and both upload modes; that converts
a silent staleness bug into a loud one. (3) A mutation test: perturb each field of the key's
inputs in turn and assert the cached value changes, so a field absent from the key cannot pass.

---

### Option A: price a period's SH admissions as a batch, one rollout per admit count k

*What it is.* Instead of one rollout per candidate, sort the candidates once (by deadline, which
is already pi_0's order, D99 (4)) and run one rollout per PREFIX LENGTH k: admit the first k and
score the result. Choose the k with the best DeltaJ. That is at most (candidates + 1) rollouts
instead of candidates rollouts, which sounds like no saving, but it becomes one if the search
over k is coarse (for example doubling: k = 0, 1, 2, 4, 8, ...), giving O(log candidates)
rollouts per period.

*What changes in the decisions.* This is a real change and it has two parts. First, the policy
stops asking "is this instant worth admitting given what I have already admitted" and starts
asking "how many of this period's instants, in deadline order, are worth admitting". Those are
different questions: the per-candidate rule can admit a late-deadline instant and decline an
earlier one when the earlier one's value is lower, and a prefix rule cannot. Second, a coarse
search over k cannot return a k it did not try, so the admit count is quantised.

*Expected cost.* Per period, from O(candidates x devices) to O(log candidates x devices) with a
doubling search. At 64 devices with around 30 candidates that is roughly a 6x reduction against a
2.8x gap, which would put p99 under the period with margin.

*Fidelity risk.* Moderate and, importantly, ASYMMETRIC: it is a restriction of the action space,
not an approximation of a value. The policy can only choose prefixes of the deadline order, so
any period where the right answer is a non-prefix set is unreachable. That is the same class of
error as E24b in CLAUDE.md's precedent list (comparing policies whose action spaces did not
contain each other), so it must be reported as an action-space change and never described as a
speed-up alone. A policy that is cheaper because it can do less is not the same policy.

*How we would test it.* (1) Offline, on the committed fixtures: for every period, enumerate the
per-candidate decision set and the best prefix, and report the fraction of periods where they
differ and the DeltaJ lost when they do. That is a direct measurement of the fidelity cost and it
needs no new runs, only the existing decision logs plus a replay. (2) If the loss is small, run
both arms through the whole round-1 comparison and report them as two arms, not one: the batch
arm is a different arm and belongs in the table as such. (3) The quantisation of k is tested by
comparing the doubling search against the exhaustive prefix search on the same fixtures.

---

### Option B: a cheaper SH-admission estimate, full rollouts kept for pieces and recall jobs

*What it is.* Spec 6.5 already provides for this: "When a full rollout is too expensive (M4), the
closed-form channel approximation may be used (direct delay of overlapping requests from the step
model times a load factor), with the backlog term applied only outside channel 1 and continuation
value retained." Apply it to SH admission only, and keep the full rollout for piece release and
recall jobs, which are both far rarer per period and carry much more value each.

*What changes in the decisions.* SH admissions are scored by a closed-form delay estimate rather
than a simulated one. Pieces and recall jobs are unchanged. The direction of the error is
predictable and worth stating in advance: the closed form prices the delay this request imposes
on overlapping requests but applies the backlog term only outside channel 1, so it will tend to
UNDERSTATE the cost of admitting into an already-backlogged engine, which is exactly the
condition at 64 and 128 devices. That biases towards over-admission at the sizes where the
problem bites.

*Expected cost.* This is the cheapest of the three by a wide margin. SH admission is the dominant
candidate class (960 of the decisions in an 8-device 120 s cell), and a closed form is O(1) in
devices rather than O(devices), so it removes the dominant term of BOTH factors at once. Expected
well under the period at 128 devices.

*Fidelity risk.* The highest of the three, and the spec already names the mitigation: **"The
fallback must pass T0 itself."** That is not a formality. T0 is the fidelity gate the frozen model
passed, and a fallback that has not passed it is an unvalidated cost model being used to make
admission decisions, which is the E36 failure mode in a new costume: the quantity the experiment
exists to measure would be computed by something never checked against measurement.

*How we would test it.* (1) T0, on the fallback, as the spec requires: the same four criteria on
the same FIT trials, with the HOLDOUT untouched. (2) A head-to-head on the committed fixtures
comparing the closed-form DeltaJ against the full-rollout DeltaJ per SH candidate, reporting the
sign-disagreement rate (how often they disagree on admit versus decline) and the distribution of
the DeltaJ difference, split by engine backlog, because the bias is expected to depend on it.
(3) The over-admission prediction above is a falsifiable prediction and should be registered as
one before the run: if the closed form admits more at high load, that is the predicted failure
and not a surprise.

---

### Option C: incremental rollouts that reuse the previous candidate's state

*What it is.* Candidate k's rollout differs from candidate k-1's only by the one admit in
between. Rather than cloning the fleet and re-simulating from scratch, continue from the previous
rollout's state and apply the delta.

*What changes in the decisions.* Nothing, IF the rollout is a deterministic function of state and
the delta is applied exactly. This is the only one of the three the brief lists that is
decision-preserving in principle, which makes it the most attractive and the hardest.

*Expected cost.* It attacks the candidates factor without touching fidelity. The saving depends
on how much of a rollout is shared between successive candidates, which is not yet measured and
is the first thing to find out: if the admit perturbs the schedule early, little is reusable.

*MEASURED 2026-11-18, and the measurement closes the option: see `study_live2_coord.md` section
P8.* The inputs of consecutive candidates are nearly identical (the median pair shares every
device and every job), but the trajectory diverges at 7.6 % of the horizon at 8 devices and
22.1 % at 64, and only about a third of the opportunity rows form a reusable prefix. The ceiling
on what an incremental rollout could save is therefore roughly a fifth to a quarter of each
rollout body, about 1.3x, against a 2.5x gap at 64 devices. Option 0 already beat that ceiling by
exploiting the input sharing instead. **Not worth building.**

*Fidelity risk.* Low in principle and high in practice, for a specific reason: it replaces a
property that currently holds by construction with one that has to be maintained by hand. Today
each rollout starts from a fresh clone (`clone_for_rollout`), so cross-contamination between
candidates is impossible; `test_the_fast_clone_does_not_let_a_rollout_touch_the_callers_fleet`
exists precisely to keep that true. An incremental rollout deliberately shares state between
candidates, so the isolation guarantee has to be re-established for every field the rollout
writes. That is the same hazard class as the clone work in StudyLIVE2-fix, which is where the
`clone_impl = "reference"` escape hatch came from, and the same hatch would be needed here.

*How we would test it.* (1) Measure the reuse first, before building anything: instrument one
period's successive rollouts and report how much of the simulated timeline is identical between
candidate k-1 and k. If it is small, the option is dead and costs nothing to abandon. (2) If it
is large, implement it behind a flag with the full rollout as the reference, exactly as
`clone_impl` does, and require byte-identical decision logs on the equivalence grid. (3) An
isolation test per written field, in the shape of the existing clone test.

---

### Recommendation

In order: **Option 0 first**, because it is the only one that cannot change a decision and it
attacks the dominant factor in the profile; then **measure Option C's reuse**, because the
measurement is cheap and either kills the option or justifies it; then **Option A's offline
divergence study**, because it quantifies a fidelity cost from logs we already have. Option B
last, not because it is worst but because it is the only one whose precondition is a full T0 run,
and it should not be reached for before the two decision-preserving routes have been exhausted.

**STATUS 2026-11-18.** Option 0 is implemented and 32 devices now meets the period. Option C is
measured and closed: the reuse ceiling is about 1.3x, below what Option 0 already delivered.
Options A and B are NOT implemented and are not to be, pending what the H100 pilot shows about
what the policy's decision delay actually costs it; with the submission-stamp fix in place that
delay is paid as submit delay rather than as emulator lateness, so the pilot can now measure its
price instead of being invalidated by it. Both decision-preserving routes are now exhausted,
which is the condition this note set for reaching for Option B.

If none of them closes the gap, the honest outcome is the one this row already reported: the
uncapped policy does not keep up at 64 and 128 devices on flash CPU, that is a property of the
policy and the machine rather than of the harness, and the round-1 comparison should say so
rather than quietly capping the work the policy is allowed to do.

---

## Option B: the closed-form SH admission estimate (PRE-REGISTRATION, written before any code)

**User decision 2026-11-18: build Option B as schedule insurance, OFF BY DEFAULT.** Nothing in
the pilot, round 1 or any other run uses it until the user approves it after the pilot. This
entry is the pre-registration: the exact closed form, the load-factor definition, and the
falsifiable prediction, all recorded and committed BEFORE the implementation and before any
measurement. The planner logs the decision in the design log; this row records it.

Spec v4 section 6.5, which is what is being built: "When a full rollout is too expensive (M4),
the closed-form channel approximation may be used (direct delay of overlapping requests from the
step model times a load factor), with the backlog term applied only outside channel 1 and
continuation value retained. The fallback must pass T0 itself." It applies to SH (monitoring)
admission candidates ONLY; piece release and recall jobs keep the full rollout, unchanged.

### B.1 What the full rollout computes, so the closed form prices the same thing

For an admit, `delta_j` runs two rollouts and takes `a.total - b.total`, where
`total = u_hat + z_term + terminal` (`rollout.py:276-277`). The engine model in the rollout is a
SINGLE SERIAL SERVER in EDF order: `start_j = max(free_{j-1}, due_at_j)`,
`finish_j = start_j + predict(...).service_s`, `free_j = finish_j` (`rollout.py:203-219`). That
is why a closed form is possible at all: inserting one request shifts every later request in the
queue by exactly its service time, which is arithmetic rather than simulation.

The SH credit is PER INSTANT (D98, `rollout.py::_opportunity_utility`): each instant `c` of each
device is credited `omega_SH * (u_sh_cloud(delivered - c) - u_sh_device)` when the call captured
at `c` is delivered by `c + L_SH`, and exactly 0 otherwise, since a device-served instant
contributes `omega * (u_dev - u_dev)`.

### B.2 The closed form, term by term

At the decision instant: `t0 = f.t`, `H = params.H`, `end = t0 + H`. In-flight work frees the
engine at `free0 = max_p (t0 + predict(p, concurrent=|in_flight|-1).service_s)`. The EDF queue is
`Q = _edf(f.pending)`, served serially as above. Candidate `c` is an `episode_call` inserted at
its EDF position `k`, with `S_c = predict(c, concurrent=|in_flight|, load_pct).service_s`,
`start_c = max(free_{k-1}, due_at_c)`, `delivered_c = start_c + S_c + down_s(dev_c)`.

    DeltaJ_cf(admit c) = G - L + DeltaCV - mu * B + DeltaZ

| term | definition | frozen-engine quantity it comes from |
|---|---|---|
| **G** own gain | `omega_SH * (u_sh_cloud(delivered_c - capture_c) - u_sh_device)` if `delivered_c <= capture_c + L_SH`, else 0 | `Eng1Engine.predict().service_s` for the timing; `utility.u_sh_cloud` / `profiles.u_sh_device` for the value, both committed and unchanged |
| **L** imposed loss | `shift = LF * S_c`. For every queued `episode_call` at EDF position >= k that still starts inside the horizon, its credit recomputed at `delivered_j + shift`, dropping to 0 if that passes `capture_j + L_SH`. `L = sum(credit_before - credit_after) >= 0` | the same `service_s` arithmetic and the same committed `u_sh_cloud` |
| **DeltaCV** continuation value, RETAINED | for every job whose pieces are delayed, `continuation_value(job, t, engine, extra_work_s=shift) - continuation_value(job, t, engine, extra_work_s=0)` | the committed `continuation.continuation_value`, called exactly as the rollout calls it |
| **B** backlog, OUTSIDE CHANNEL 1 ONLY | `gpu_c` if `start_c > due_at_c` (the candidate had to queue, so its work sits behind the serving request and is outside channel 1), else 0. Charged as `-mu * B` | `predict().gpu_s`; `mu` from `params.mu`, the arm's own estimator |
| **DeltaZ** deficit term | for each device whose instant outcomes change, `z_of("SH") * (ok_after/n_after - ok_before/n_before)`, the same expression as `rollout.py::_z_term` | `Device.z_of`, committed |

**Channel 1** is the single serial server the frozen model describes (section 6: a request
arriving behind concurrent work waits for that work, it does not share a step). Work in channel 1
is the request being served; work outside it is queued. That is the reading of "the backlog term
applied only outside channel 1" this implements.

### B.3 The load factor: ONE definition, NO fitted parameter

    LF = step_ms(tok_c, img_c, decode_reqs = R_d, prefill_reqs = R_p, cached_ctx_tokens = C)
         / step_ms(tok_c, img_c, 0, 0, 0)

both sides evaluated on the frozen step model (`StepModel.step_ms`, read through
`eng1_engine_fast`), with `R_d` the in-flight requests, `R_p` the queued prefills ahead of the
candidate, and `C` the cached context tokens the policy believes the engine holds. It is a pure
ratio of the frozen model to itself, so **nothing is fitted, no HOLDOUT is touched, and no
cross-fitting is needed.** It uses exactly the step model's own per-request and
per-token-times-context terms, which is what the prompt's "using the step model's per-token /
per-request terms" asks for.

**One property of it is stated in advance because it is awkward.** The frozen step model's fitted
coefficients are not all positive: `per_decode_req_ms = -0.5711`, `admission_per_image_ms =
-1.2492` and `per_tok_above_2048_ms = -0.0078` (`results/cost/study_eng1/eng1_step_model.json`).
So LF is NOT guaranteed to be at or above 1, and on a decode-heavy engine the frozen model
predicts a SHORTER step. **No term is dropped and no clamp is applied**, because dropping a term
whose fitted sign is inconvenient would be choosing the answer, and clamping would substitute my
judgement for the frozen model's. The empirical distribution of LF is reported with the
measurements. If LF falls below 1 it DEFLATES the imposed delay, which adds to the
over-admission predicted below rather than cutting against it.

### B.4 What the closed form does NOT price, declared in advance

1. **Cascade effects.** The shift can push work out of the horizon entirely, change how much work
   is simulated, and change `busy`. The closed form prices only the FIRST-ORDER shift of the
   requests already queued.
2. **The KV pool and prefix-risk term.** The rollout allocates a transient prefix for an episode
   call and prices prefix-loss risk (A6.2); the closed form omits it.
3. **Cadence-calendar instants** other than those served by queued or in-flight calls.
4. **The terminal STATE-VALUE sum is omitted, and that omission is EXACT, not an
   approximation:** an `episode_call` builds no history, so no device belief changes and the term
   cancels identically in `a.total - b.total`.

Items 1 to 3 are approximations and all of them are omissions of COST, which is the mechanism
behind the prediction.

### B.5 PRE-REGISTERED PREDICTION, in the design note's own words

From Option B above, unchanged: "the closed form prices the delay this request imposes on
overlapping requests but applies the backlog term only outside channel 1, so it will tend to
UNDERSTATE the cost of admitting into an already-backlogged engine, which is exactly the
condition at 64 and 128 devices. That biases towards over-admission at the sizes where the
problem bites."

As falsifiable statements, to be answered with the numbers and not reworded:

- **P-B1 (sign).** `sign(closed-form admits - rollout admits) > 0` on the committed fixtures:
  over-admissions (closed form admits, rollout declines) exceed under-admissions (closed form
  declines, rollout admits).
- **P-B2 (trend with backlog).** The over-admission rate rises monotonically across backlog
  terciles, lowest in the first tercile and highest in the third.
- **P-B3 (trend with fleet size).** The over-admission rate rises with device count from 8 to
  128.
- **P-B4 (direction of the DeltaJ error).** The median of `DeltaJ_cf - DeltaJ_rollout` is
  positive, and rises with backlog tercile.

Each of P-B1 to P-B4 can come out held, not held, or mixed, and all four are reported that way.
A negative or zero sign on P-B1 falsifies the mechanism this fallback's risk assessment rests on,
which would be a more interesting result than confirmation.

### B.6 Acceptance is not decided here

M-B1 reports the spec's four T0 criteria for the fallback and for the full frozen model side by
side against the spec's pre-registered bars. **No pass or fail beyond the numbers against those
bars is declared, and the fallback is not enabled anywhere.** Acceptance is the user's call after
the H100 pilot shows what decision delay above 32 devices actually costs.

### B.7 Option B as built: the outcome

Built, tested, measured, **and left OFF**. `sh_cost` defaults to "rollout" everywhere and the
fallback is enabled in no run. Everything below is CPU only on committed dry-run fixtures, and
M-B2 / M-B3 / M-B4 run with mu ESTIMATED (`mu="ewma"`), not at its placeholder zero, because the
prediction is about the backlog term and at mu = 0 that term is silent in both models alike.

**Two errata to the pre-registration, both found by shadow mode and both recorded rather than
quietly corrected.** B.2 is the committed text; these are the corrections and the reasons.

1. *The channel-1 condition.* B.2 wrote it as `start_c > due_at_c`. That is not "outside
   channel 1": an instant CAPTURED BEFORE the decision instant satisfies it on a completely IDLE
   engine, so it fired with nothing ahead of the candidate. The condition used is the work ahead
   of the candidate when it could first run, `work_ahead_s = max(0, free_at_k - max(t0,
   due_at_c))`, which is 0 on an idle engine whatever the capture time.
2. *The backlog term's shape.* B.2 wrote `-mu * gpu_c` whenever the candidate queued. That is
   not the rollout's backlog term: the rollout charges `-mu * max(busy - H, 0)`, leftover work AT
   THE HORIZON, so an admission whose work still fits inside H costs nothing in backlog. The
   first shadow run showed the consequence immediately, and it is worth recording as a worked
   example of why shadow mode exists: on an 8 + 8 60 s fixture the error was a near-constant
   -0.055 on 949 of 952 candidates, it accounted for the ENTIRE difference from the rollout (the
   rollout's own `d_terminal` was 0 while this file's `own_gain` matched its `d_u_hat` exactly),
   and it inverted the measured direction so that the closed form appeared to UNDER-admit 411 to
   3. Reading that as a falsification of P-B1 would have been wrong. The term is now
   `max(busy_before + gpu_outside_channel_1 - H, 0) - max(busy_before - H, 0)`, which keeps the
   rollout's structure and applies the channel-1 restriction to which work enters it.

#### M-B1: T0 criteria on the fallback, FIT trials only

The scope is narrow and it is the first finding. The fallback is only ever applied to an SH
admission: one 378-token single-frame episode call. The committed trials inject actions of their
own size, and the distribution is nothing like that. Part C FIT runs 378 to 13,275 prompt tokens
with a median of 11,058; **ENG1d FIT runs 10,925 to 13,273 and contains not one trial at or below
600 tokens.** So only 70 of the 406 Part C FIT trials are the size this fallback ever prices, and
ENG1d cannot speak to it at all. All three groups are reported; the SH-sized subset is the one to
read.

| group | n | model | criterion (i) fraction | spec bar | ratio median | criterion (ii) |
|---|---|---|---|---|---|---|
| Part C FIT, **SH-sized actions only** | 70 | full frozen | 0.7143 | 0.90 | 1.401 | not computable |
| Part C FIT, **SH-sized actions only** | 70 | **closed form** | **0.2429** | 0.90 | **16.851** | not computable |
| Part C FIT, all actions (out of scope) | 406 | full frozen | 0.7562 | 0.90 | 1.275 | 0.9833 |
| Part C FIT, all actions (out of scope) | 406 | **closed form** | **0.0419** | 0.90 | **15.254** | **0.5333** |
| ENG1d FIT (no SH-sized trial exists) | 180 | full frozen | 0.9000 | 0.90 | 1.107 | 1.0000 |
| ENG1d FIT (no SH-sized trial exists) | 180 | **closed form** | **0.0000** | 0.90 | **9.380** | **0.3333** |

Criterion (ii) is NOT COMPUTABLE on the SH-sized subset: all 70 trials share one action size, so
no pair of actions within a condition differs by more than the 2x ranking rule requires.
Criteria (iii) and (iv) DO NOT APPLY, with the reasons recorded in the JSON: the closed form
predicts no completion time, and it omits the KV pool and the A6.2 prefix-risk term outright
(declared in advance at B.4), so it has no prefix-loss class.

**It is not the load factor.** The load factor's median is 1.000 on the SH-sized subset (max
1.127), and forcing it to exactly 1 leaves criterion (i) unchanged at 0.2429 with the ratio
median moving from 16.851 to 17.186. The over-prediction is the SERIAL-SHIFT ASSUMPTION
underneath it: the closed form charges every overlapping request the full residual of the
action's service time, and the real engine does not serialise that way.

**No pass or fail is declared.** The numbers are against the spec's pre-registered bars and
against the full frozen model, and the decision is the user's after the pilot. What the numbers
say plainly is that the spec's own precondition for this fallback, "the fallback must pass T0
itself", is not met as things stand on criterion (i), and that the trials needed to test it in
its own regime barely exist.

#### M-B2: shadow divergence, 13,808 SH candidates

| devices | candidates | exact match | over-admissions | under-admissions | DeltaJ difference median |
|---|---|---|---|---|---|
| 8 | 480 | 0.8792 | 2 | 0 | 0.000 |
| 32 | 1,904 | 0.9375 | 47 | 1 | 0.000 |
| 64 | 3,808 | 0.9270 | 118 | 0 | 0.000 |
| 128 | 7,616 | 0.9265 | 189 | 7 | 0.000 |
| **pooled** | **13,808** | **0.9265** | **356 (2.58 %)** | **8 (0.06 %)** | **0.000** (p10 0, p90 0, min -0.217, max +0.129) |

Over-admission rate by backlog tercile over queued tokens:

| devices | T1 low | T2 mid | T3 high |
|---|---|---|---|
| 8 | 0.000 | empty | 0.0588 |
| 32 | 0.000 | empty | 0.3310 |
| 64 | 0.000 | empty | 0.3894 |
| 128 | 0.000 | empty | 0.3129 |

DeltaJ difference median in the high tercile: 0.00277, 0.03562, 0.04718, 0.04718 at 8 / 32 / 64 /
128. **The middle tercile is empty at every size** because the backlog distribution is bimodal:
most candidates arrive at an idle engine, where the closed form is EXACT, and the rest arrive
behind work. That is reported rather than smoothed, and it makes P-B2 a two-point comparison.

**The pre-registered prediction, answered without rewording it:**

- **P-B1 (over-admissions exceed under-admissions): HELD.** 356 against 8, a ratio of 44 to 1.
- **P-B2 (the over-admission rate rises monotonically across backlog terciles): HELD in
  direction, on two points rather than three.** It is 0.000 in the low tercile at every size and
  0.313 to 0.389 in the high tercile. The middle tercile is empty, so "monotonic across three
  terciles" is not testable on this fixture.
- **P-B3 (the rate rises with device count from 8 to 128): NOT HELD.** It rises 8 to 64
  (0.0042, 0.0247, 0.0310 overall; 0.059, 0.331, 0.389 in the high tercile) and then FALLS at 128
  (0.0248 overall, 0.313 high). The prediction said "increasingly with fleet size" and it stops
  increasing at the largest size measured.
- **P-B4 (the DeltaJ difference median is positive and rises with backlog tercile): MIXED.** The
  pooled median is 0.000, not positive, because the closed form is exactly right on 92.65 % of
  candidates. Within the high-backlog tercile the median IS positive and does rise with size,
  0.00277 to 0.04718, flattening between 64 and 128.

So the MECHANISM is confirmed and its claimed TREND is not. Where the closed form differs it
over-admits, by a wide margin, and the divergence concentrates exactly where predicted, in the
high-backlog tercile. The "increasingly with fleet size" half of the prediction fails at 128.

#### M-B3: speed, closed_form against rollout, Option 0 on

Committed 180 s fixture, seed 1, mu estimated. (These p99 figures are not comparable to
`perf_speed_option0.json`, which ran at mu = 0; the comparison that matters here is mode against
mode on identical fixtures.)

| devices | p50 rollout | p50 closed form | p99 rollout | p99 closed form | wall rollout | wall closed form |
|---|---|---|---|---|---|---|
| 32 | 16.993 ms | 14.872 ms | 51.481 ms | 51.768 ms | 30.3 s | 27.7 s |
| 64 | 163.240 ms | 139.894 ms | 211.362 ms | **325.237 ms** | 206.5 s | 278.7 s |
| 128 | 345.655 ms | **122.552 ms** | 781.088 ms | **2,227.083 ms** | 476.6 s | 494.4 s |

**This is the decisive result for Option B, and it is a negative one.** The closed form does what
it was meant to do to the MEDIAN, cutting it 2.8x at 128 devices, and the opposite of what it was
meant to do to the TAIL: p99 is 1.54x WORSE at 64 devices and **2.85x worse at 128**. The
mechanism is the over-admission M-B2 measured: each extra admission creates downstream work that
the release loop then prices with a full rollout, so the period that was already worst becomes
worse. A fallback whose entire purpose is to bound the p99 inside the 100 ms period makes the p99
worse at the two sizes that need it. The 60 s fixture shows the same shape and is kept alongside
in `perf_optionB_m_b3_window60.json`.

#### M-B4: closed-loop effect, FIXTURE REPLAY, NOT A LIVE RESULT

| devices | SH admitted, rollout | SH admitted, closed form | delta | released delta | on-time delta |
|---|---|---|---|---|---|
| 8 | 476 | 476 | 0 | 0 | 0 |
| 32 | 1,033 | 1,034 | +1 | 0 | -1 |
| 64 | 1,063 | 1,069 | +6 | 0 | 0 |

The extra admissions are ABSORBED: `released` is identical at every size, so the release loop,
which still uses the full rollout, declines downstream what the closed form let in. At 8 devices
the two arms are identical in every counted quantity. **No fixture-level J is reported and the
reason is in the JSON rather than a zero being printed:** a dry-run fixture produces no scored J,
the decision log carries no per-decision J to sum, and inventing a proxy would be a number with
no definition behind it. The on-time fraction is the closest the fixture defines: 1.0000 against
0.9989 at 32 devices, 1.0000 against 1.0000 at 8 and 64.

#### B.8 Six-check consistency protocol

1. **Cross-check against committed measurements.** The full frozen model's criterion (i) is
   reproduced here at 0.7562 on Part C FIT and 0.9000 on ENG1d FIT with the committed
   `delay_pass` and the committed trials, which is the same scoring the T0b work reports; no
   quantity moved. The closed form has no prior committed value to disagree with, this being its
   first measurement.
2. **Physical plausibility.** The closed form's imposed delay is a sum of residuals of the frozen
   `predict().service_s`, so it cannot exceed the number of overlapping requests times that
   service time; the 16.9x ratio against measured is an OVER-prediction, which is the direction a
   serial model must err in against a batching engine, not a rate faster than the committed
   curves.
3. **Distribution sanity.** Every divergence figure is reported with its median, p10, p90, min
   and max, and the pooled median of exactly 0.000 is explained rather than left to look like a
   missing number: 92.65 % of candidates match bit for bit. The empty middle tercile is reported
   as empty.
4. **Definition audit.** "Imposed delay" keeps the committed TTFT-sum definition
   (`score_t0b.METRIC_FIELD["ttft"]`, StudyENG1 Part C's and StudyT0's own); criterion (i) uses
   the committed `run_t0.delay_pass` (1.5x or 0.1 s) and criterion (ii) the committed
   `run_t0.RANK_RATIO` of 2.0 and `MIN_FRACTION` bar of 0.90. Only the PREDICTOR differs.
5. **Claim linkage.** Nothing here bears on a claim in `research/CLAIMS.md`: this is an
   apparatus-cost study. It bears on spec 6.5's own precondition, which it does not meet.
6. **Proxy validity.** Two proxies are used and both are labelled. The SH-sized Part C subset is
   a proxy for SH-admission conditions, valid in action size and NOT in anything else: those
   trials' background load is ENG1c's, not a 64-device fleet's. The on-time fraction in M-B4 is a
   proxy for J and is not J; it is reported as a count, and no fixture-level J is claimed.

#### B.9 Limitations

1. The fallback does not meet the spec's criterion (i) bar in any scoping, and the trials that
   could test it in its own regime are 70 Part C trials with one action size, which cannot
   support criterion (ii) at all.
2. M-B2's backlog terciles are bimodal, so the trend across backlog rests on two points.
3. M-B3 and M-B4 are dry-run fixtures. The over-admission that drives the p99 blow-up depends on
   how much downstream work an admission really creates, which only a measured run settles.
4. The two errata above mean the committed pre-registration's B.2 is not the implemented form in
   two places. The errata are recorded here; the design log entry the planner writes should carry
   them.
5. Nothing here tests the fallback at 256 devices or above, or with the release loop also on a
   closed form, which is a different option and was not built.

---

## Option A study: definitions and expectations (PRE-REGISTRATION, written before any measurement)

**User decision 2026-11-18, design log D110. OFFLINE DIVERGENCE STUDY ONLY.** No arm changes, no
new switch, nothing enabled. Option B is closed (D109); Option 0 stays on. Option A is the
design note's "price a period's SH admissions as a batch, one rollout per admit count k", and the
whole point of measuring it first is that **it is an ACTION-SPACE RESTRICTION, not a speed-up**:
the policy could only ever admit the first k SH candidates in deadline order. If it is worth
building it becomes a separate arm in round 1 and is never described as a speed-up alone.

### A.1 The three methods, defined exactly

The candidates of a period are the SH (monitoring) admission candidates the arm raises, in the
order it raises them, which is already **deadline order**: `arms_policy._admit_monitoring` sorts
by `(deadline, stream_id)` (D99 (4), pi_0's order) and calls `Coordinator.escalate` once per
candidate. Write them `c_1 .. c_n` in that order, and `P_k = {c_1 .. c_k}` for the
deadline-order prefix of length k, with `P_0` the empty set.

**How a period's DeltaJ is compared across the three, which is the one modelling decision here
and is fixed now.** For ANY set S of candidates, the period's DeltaJ is defined by ONE rollout
pair from the period's STARTING fleet state, before any admit of that period:

    DeltaJ(S) = ro.run(start, extra_pending = items(S)).total - ro.run(start).total

That is `delta_j`'s own "admit" reference (spec 3.5: extra pending against nothing added),
evaluated once for the whole set rather than once per candidate. It is the SAME function of S for
all three methods, which is what makes them comparable, and it is computed by the CURRENT
rollout with Option 0 on and `sh_cost = "rollout"`, so no second model enters.

| method | the set it chooses | how |
|---|---|---|
| **per-candidate decision set** `S_pc` | the admits the current policy actually makes in that period | recorded from the real run: candidate `c_i` is admitted when the sequential rule's own `DeltaJ > 0`, each evaluated against the state left by the admits of `c_1 .. c_{i-1}` |
| **best prefix** `P_k*` | `argmax over k in 0..n of DeltaJ(P_k)` | exhaustive search over all n + 1 prefixes |
| **doubling search** `P_kd` | `argmax over k in {0, 1, 2, 4, 8, ...} union {n} of DeltaJ(P_k)`, the best k actually tried | the same, over the doubling ladder only |

**A consequence that is recorded in advance rather than discovered later.** `S_pc` is produced by
a GREEDY SEQUENTIAL rule and does not maximise `DeltaJ(S)`. So `DeltaJ(P_k*)` can come out ABOVE
`DeltaJ(S_pc)`, and the "DeltaJ lost" by the prefix rule can be NEGATIVE, meaning the restricted
method scores better on this measure than the policy does. That would not make Option A free: it
would mean the greedy rule is leaving value on the table within its own action space, which is a
separate finding about the current policy and must be reported as such rather than as a point in
Option A's favour.

**Rollout accounting**, so the speed projection has a stated basis. The reference rollout
`ro.run(start)` is the same for every k, so it is counted once per period:

| method | rollouts per period |
|---|---|
| per-candidate (what runs today) | `2n` (each candidate is its own action-and-reference pair) |
| exhaustive prefix | `n + 2` (one per prefix, plus the one shared reference) |
| doubling | `(number of k tried) + 1`, which is `floor(log2(n)) + 3` at most |

### A.2 What cannot be represented as a prefix, counted separately

A per-candidate set can contain an admit a prefix cannot express: a later-deadline candidate
admitted while an earlier-deadline one is declined. `S_pc` is a prefix exactly when the admitted
indices are `1 .. |S_pc|` with no gap. Periods where it is not are counted separately and one is
shown worked through, because they are the cases where Option A could not reproduce the current
policy's choice at any k.

### A.3 Written expectations, which are NOT constraints

Stated in advance so the outcome can contradict them:

- **E-A1.** Divergence between the per-candidate set and the best prefix rises with fleet size.
- **E-A2.** Divergence rises with backlog.
- **E-A3.** The DeltaJ lost is small where the per-candidate set already is a prefix.

Each is reported as held, not held, or mixed, in those words, and none of them gates anything.

### A.4 What this study does not do

It does not implement Option A, add a switch, or touch any arm's decision path. It reads the
periods a normal dry run produces and recomputes DeltaJ for the alternative sets offline. The
speed figure it produces is a PROJECTION from rollout counts and the measured per-rollout cost,
labelled as such, and is not a measured arm.

### A.5 Option A study: the outcome

Committed 180 s dry-run fixtures at 8 / 32 / 64 / 128 devices, seed 1, H = 1.0 s, Option 0 on,
`sh_cost = "rollout"`, the same configuration as `perf_speed_option0.json` as the prompt
specifies, which means `mu` is at its placeholder zero and the backlog term is silent. **No arm
was changed, no switch was added, and Option A is not implemented.** 6,122 periods with at least
one SH candidate were scored, plus 360 more on the sanity fixture.

#### The divergence

| devices | periods | candidates per period, median | per-candidate set is NOT a prefix | best prefix differs | DeltaJ lost, median | max | **lost as a fraction of the run's total SH DeltaJ** |
|---|---|---|---|---|---|---|---|
| 8 | 725 | 2 | 0.0000 | 0.0014 | 0 | 0 | **-0.000517** |
| 32 | 1,797 | 3 | 0.3673 | 0.3717 | 0 | 0.1339 | **0.2512** |
| 64 | 1,800 | 7 | 0.7372 | 0.7417 | 0.1013 | 0.1512 | **0.7921** |
| 128 | 1,800 | 12 | 0.7756 | 0.7794 | 0.0898 | 0.1554 | **0.8371** |

**That last column is the result.** Restricting SH admission to deadline-order prefixes costs
**79 % of the run's total SH DeltaJ at 64 devices and 84 % at 128.** It is not a small price for
a speed-up; it is most of the value the SH admission decision produces.

At 8 devices the fraction is slightly NEGATIVE (-0.000517), which is the case the
pre-registration recorded in advance: the per-candidate rule is greedy and sequential and does
not maximise `DeltaJ(S)`, so the best prefix can beat it. It does, by 0.05 % of one run's total,
on one period in 725. That is a note about the greedy rule having a little slack inside its own
action space, not a point in Option A's favour.

#### The quantisation cost of the doubling ladder is nearly nothing

| devices | loss, doubling, median | max | quantisation cost (exhaustive minus doubling), median | max |
|---|---|---|---|---|
| 8 | 0 | 0 | 0 | 0 |
| 32 | 0 | 0.1339 | 0 | 0.0354 |
| 64 | 0.1013 | 0.1512 | 0 | 0 |
| 128 | 0.0898 | 0.1554 | 0 | 0.0425 |

The doubling ladder is as good as the exhaustive prefix search in the median at every size, and
its worst case costs 0.035 to 0.043 extra. **If the prefix restriction were ever accepted, the
cheap search would be the right one;** the expensive part of Option A is the restriction, not the
search over k.

#### The expectations, answered without rewording them

- **E-A1, "divergence rises with fleet size": HELD, strongly.** The fraction of periods whose
  per-candidate set is not a prefix goes 0.0000, 0.3673, 0.7372, 0.7756 across 8, 32, 64 and 128
  devices, and the DeltaJ lost as a fraction of the total goes -0.0005, 0.2512, 0.7921, 0.8371.
- **E-A2, "divergence rises with backlog": NOT HELD, and mildly reversed.** By backlog tercile
  over queued tokens the not-a-prefix fraction is 0.3747 low against 0.2774 high at 32 devices,
  0.7375 against 0.7338 at 64, and 0.7815 against 0.7050 at 128; the median loss is likewise
  LOWER in the high tercile (0.1013 against 0.0549 at 64, 0.0898 against 0.0120 at 128). Two
  caveats on this one, both structural: the tercile edges are `lo = hi = 0` at every size, so the
  middle bucket is empty and the backlog distribution is bimodal exactly as it was for Option B;
  and this configuration runs at mu = 0, so the backlog term is silent and the only route by
  which backlog can act is through the queue's effect on delivery times.
- **E-A3, "the DeltaJ lost is small where the per-candidate set already is a prefix": HELD
  exactly.** On every already-a-prefix period at every size the loss is identically 0, median and
  maximum alike (725, 1,137, 473 and 404 such periods). That is not approximately small, it is
  zero by construction: when the per-candidate set is a prefix, it IS one of the prefixes the
  exhaustive search tries.

#### The worked example: what no prefix can express

64 devices, period t = 83.8, 6 SH candidates in deadline order, 7 requests running, queued tokens
0.

* The policy admits candidates **4, 5 and 6**, the three LATEST deadlines, and declines 1, 2
  and 3.
* No k reproduces that: the admitted indices are not `1..3`.
* The best prefix is **k\* = 0, admit nothing**, with DeltaJ 0.0 against the per-candidate set's
  0.15117. The whole of that period's SH value is lost.

The behaviour being destroyed is sensible, which is the point. The earliest-deadline instants
cannot be delivered inside their own `c_i + L_SH` given the work already running, so admitting
them buys nothing, while the later-deadline instants still can be. The policy declines the ones
it cannot serve and admits the ones it can. **A deadline-order prefix rule can only ever do the
opposite**, taking the most urgent first, and in this period the most urgent are precisely the
hopeless ones. This is not a corner case: it is 74 % of periods at 64 devices and 78 % at 128.

#### The speed it would buy, as a projection and labelled as one

Median rollouts per period, which is what the projection scales:

| devices | per-candidate (today) | exhaustive prefix | doubling |
|---|---|---|---|
| 8 | 4 | 4 | 4 |
| 32 | 6 | 5 | 5 |
| 64 | 14 | 9 | 6 |
| 128 | 24 | 14 | 7 |

**PROJECTION, NOT A MEASURED ARM.** Method: the live decision latency scaled by the median ratio
of doubling rollouts to per-candidate rollouts, which assumes decision time is rollout-dominated
and linear in rollout count. It is therefore OPTIMISTIC for the cheaper method, because a
period's non-rollout work does not shrink.

| devices | measured cost per rollout | rollout ratio | live p50 / p99 | **projected p50 / p99 under doubling** |
|---|---|---|---|---|
| 8 | 0.1020 ms | 1.000 | 1.87 / 8.46 ms | 1.87 / 8.46 ms |
| 32 | 0.3147 ms | 0.833 | 19.83 / 99.06 ms | 16.52 / 82.55 ms |
| 64 | 0.6271 ms | 0.429 | 49.73 / 247.45 ms | 21.31 / 106.05 ms |
| 128 | 1.2821 ms | 0.292 | 121.55 / 1,081.20 ms | 35.45 / 315.35 ms |

At 8 devices there is no saving at all, because a two-candidate period needs the same four
rollouts either way. At 128 devices the projection is a 3.4x cut, and **even then the projected
p99 of 315 ms is still 3.2x over the 100 ms decision period**, while 64 devices lands at 106 ms,
just over it.

#### The trade, stated plainly

Option A would buy an optimistically projected 3.4x on the decision-time tail at 128 devices,
still short of the period, in exchange for **84 % of the run's total SH DeltaJ**. At 64 devices it
buys 2.3x, lands at 106 ms, and costs 79 %. At 8 and 32 devices it buys nothing worth having. On
these fixtures Option A is not a good trade at any size measured, and the reason is structural
rather than a matter of tuning: in most periods at scale the policy's admit set is not a
deadline-order prefix, because the instants with the nearest deadlines are often the ones it
cannot serve.

The study does not decide. These are fixtures, not a live run, and the decision is the user's.

#### A.6 Sanity check

On a dedicated fixture with a single dashcam, every one of 360 periods raises **exactly one** SH
candidate, and the per-candidate set, the best prefix and the doubling search agree **exactly on
all 360** (0 disagreeing). With n = 1 the prefixes are the empty set and the single candidate, so
both searches contain the per-candidate answer; a disagreement would have meant the three DeltaJ
definitions were not the same function of the admitted set. The main fixtures could not provide
this check: at 8 devices and above no period has only one candidate, so it was run separately
rather than left vacuous.

#### A.7 Six-check consistency protocol

1. **Cross-check against committed measurements.** The live decision latencies this study
   observes (p99 99.06 / 247.45 / 1,081.20 ms at 32 / 64 / 128) sit against
   `perf_speed_option0.json`'s committed 100.59 / 252.54 / 994.79 ms on the same fixture and
   configuration: ratios 0.98, 0.98 and 1.09, all inside the 2x rule. The 9 % at 128 devices is
   the observation wrapper's own cost, which records a fleet clone once per period.
2. **Physical plausibility.** The measured per-rollout cost rises 0.102, 0.315, 0.627, 1.282 ms
   across the four sizes, close to linear in device count, which is what an O(devices) terminal
   sum predicts; nothing here is faster than the committed curves because nothing here is a
   latency measurement of the engine.
3. **Distribution sanity.** Every loss and cost figure carries median, p90, min, max and sum. The
   medians of exactly 0 at 8 and 32 devices are explained rather than left bare: the per-candidate
   set is already a prefix in 100 % and 63 % of those periods, where the loss is zero by
   construction. The empty middle tercile is reported as empty.
4. **Definition audit.** `DeltaJ(S)` is `delta_j`'s own admit reference (spec 3.5), one rollout
   pair per set from the period's starting state, identical for all three methods, as
   pre-registered in A.1. "Deadline order" is `arms_policy._admit_monitoring`'s own
   `(deadline, stream_id)` sort (D99 (4)), not a re-derived order. "Prefix" means the admitted
   indices are `1..m` with no gap.
5. **Claim linkage.** Nothing here bears on a claim in `research/CLAIMS.md`: it is an
   apparatus-cost study. It bears on whether Option A should become a round-1 arm.
6. **Proxy validity.** Two proxies, both labelled. The projected decision time is a proxy for a
   measured arm and is explicitly optimistic, since non-rollout work does not shrink with the
   rollout count. The fixture's total SH DeltaJ is a proxy for the value at stake in a live run
   and is not a scored J; it is a sum of the same `DeltaJ(S)` the policy itself optimises, which
   is the right denominator for a loss expressed as a fraction, and no fixture-level J is claimed.

#### A.8 Limitations

1. Fixtures, not live. The periods come from dry runs against the committed cost model, and what
   the policy would admit against a real engine may differ.
2. `mu = 0` in this configuration, chosen to match `perf_speed_option0.json` as instructed, so
   the backlog term is silent. E-A2's answer is therefore about backlog acting only through
   delivery times, and a run with mu estimated could give a different answer on that one
   expectation.
3. The backlog terciles are bimodal with an empty middle bucket, so the backlog trend rests on
   two points.
4. One seed (1) at each size.
5. The speed figure is a projection from rollout counts. A measured Option A arm could differ in
   either direction, and building one was explicitly out of scope.
6. The study measures the prefix restriction in DEADLINE order only, because that is what the
   design note's Option A proposes and what pi_0 already uses. A prefix in some other order, for
   example by DeltaJ or by predicted feasibility, is a different option and was not measured; the
   worked example suggests feasibility order would fare better, which is a hypothesis this study
   does not test.

## D110 (H100 host, 2026-11-18): the decision-speed benchmark on this host's CPU

User ruling D110 (2): run the committed benchmark on the H100 host's CPU, because the in-run decision latency of
policy-core at 64 devices in the harness addendum's acceptance cell (p99 138.2 ms) disagreed by more than 2x with this
report's fixture figures. Run exactly as committed: `experiments/orchestration/live2/fix_checks.py speed`, 180 s fixture
(the one behind `perf_speed_option0.json`), 32 / 64 / 128 devices, Option 0 on (built into `policy/readiness.py`),
`sh_cost = rollout` (default), same repetitions and percentile method; plus the 60 s fixture at 64 devices. No policy
code was modified. Host: AMD EPYC 9354, 2 x 32 cores, 128 logical CPUs, max 3.80 GHz; Python 3.10.12; no affinity
(single-threaded process). The host is SHARED: other users' processes ran throughout (at start two python processes at
about 100 % CPU each and a vLLM engine at 27 %, on other cores; snapshot `perf_speed_h100host_ps.txt`, user names
anonymised); GPU 2 idle, no server up. Output: `results/orchestration/live2/coord/perf/perf_speed_h100host.json`.

| devices | fixture | this host p50 / p99 | flash p50 / p99 | ratio p50 / p99 |
|---|---|---|---|---|
| 32 | 180 s | 43.8 / 222.1 ms | 20.2 / 100.6 ms | 2.17x / 2.21x |
| 64 | 180 s | 112.3 / 584.9 ms | 50.7 / 252.5 ms | 2.21x / 2.32x |
| 128 | 180 s | 278.4 / 2,220.4 ms | 121.6 / 994.8 ms | 2.29x / 2.23x |
| 64 | 60 s | 11.0 / 338.2 ms | p99 240.9 ms (section P5, before Option 0) | p99 1.40x |
| 64 | 180 s, DIAGNOSTIC H = 0.5 s | 102.8 / 575.9 ms | n/a | vs H = 1.0 on this host: 0.92x / 0.98x |
| 64 | in-run, acceptance cell `acc2_pc_n64` (real trace seed 0, 120 s, H = 0.5, mu EWMA, live 32B) | 47.3 / 138.2 ms | n/a | n/a |

**This host's CPU is about 2.2x SLOWER than flash's on identical work**, consistently at every size (single-thread
speed: a 3.8 GHz server core against a 5.4 GHz desktop core). So the in-run 138 ms is NOT explained by a faster CPU;
on this CPU the fixture costs 585 ms at the same size. The DIAGNOSTIC cell (approved, labelled, committed fixture
function unchanged except h = 0.5) rules out the H difference: 575.9 vs 584.9 ms. The two measurement points also
differ in trace (synthetic vs the real seed-0 trace), mu (0 vs EWMA), window (180 vs 120 s) and in what the live
coordinator tells the arm about history sizes: candidate, NOT tested, see the StudyMOT2 finding that the live
coordinator's per-session token estimate is not cumulative (`cstate.history_append` keeps the max of one batch and
the current value), which makes every live recall item look many times smaller than it is and could make its rollouts
cheaper. The live and fixture figures should not be compared until that is resolved. The live pilot measures decision
latency in-run on this CPU, which is the figure that bears on the 100 ms period.

### D110 / D115: the H100 host machine factor (2026-11-18)

Measured machine factor on the committed benchmark (`fix_checks.py speed`, 180 s fixture, Option 0 on, rollout):
**the H100 host's CPU takes about 2.2x as long as flash's** (p50 2.16x to 2.29x, p99 2.19x to 2.32x at 32, 64 and
128 devices). Pinned to an idle physical core (cpu 50, sibling idle) the result equals the unpinned run within 1 %
(`perf_speed_h100host_pinned.json`: 0.994 to 0.998 at p99), so the factor is the CPU, not contention from other
users. The shared-core cells could not hold contention (the other users' unpinned processes moved off the core) and
are not a contention measurement. Under D115, a NORMALISED DECISION LATENCY (H100 in-run latency divided by this
factor) may later be reported as a labelled derived quantity; RUN OUTCOMES are never rescaled. From the pilot on,
every run logs per decision the wall time, the deciding thread's CPU time (`time.thread_time()`) and the candidates
priced, plus a 1 s host-load sampler (`decision_time.jsonl.gz`, `host_load.jsonl.gz`, summaries in `run_meta.json`).
