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
