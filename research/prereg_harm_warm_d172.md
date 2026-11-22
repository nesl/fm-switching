# Pre-registration: `harm_warm` is computed, not declared (D172 follow-up)

**Written and committed BEFORE the predicted-gain grid is rerun**, per the ruling relayed by the
H100 on 2026-11-21. Nothing in this file may be changed after a grid is run under it; a change is
a new pre-registration with its own commit.

## Why this exists

`v5/cf_planner.plan_state` scores six candidates. `HOLD_BACK`'s value **is** `harm_warm` and
`SLICE`'s is half of it. Until now every caller passed `harm_warm` as a declared number, so those
two candidates reported a grid input back as if it were a model output. In the first
`covex-v6-state` build I passed `harm_warm = 0.0`, which scored both at zero and made them
unwinnable; in `v5/d171_proofs.py::P5` I passed a grid of 0, 0.05, 0.25 and 0.5, and 33 of 48
state deltas came back exactly equal to the input. Either way the number was never predicted.
That is consistency-check 3's **artefact spread**: a plausible spread that cannot carry the
meaning the column claims.

## The computation, fixed in advance

A warm of `u` **uncached** tokens occupies the engine ahead of every request already queued behind
it in the near-term simulation. For each such request `r`:

1. **Delay added.** `delta_t(r) = QUEUE_TOKEN_S * u`, with

   `QUEUE_TOKEN_S = 0.0001535807289338535`

   taken from the committed D162 model's `first_token.per_queue_token`
   (`results/orchestration/live2/frozen_test/cost_model_gate_d162.json`, gate commit `68a2b47`).
   **This is the queued-ahead coefficient and not `per_uncached_token` (0.0001824312597782467).**
   The two differ by 19 percent and only the first one answers "what does work placed AHEAD of a
   request cost that request", which is what a background warm does.

2. **Change in delivery probability.** `p_before = P(on time | slack)` and
   `p_after = P(on time | slack - delta_t(r))`, both through `cf_cost.p_on_time` against the same
   residual distribution every other v5 prediction uses. No new curve is introduced.

3. **Value.** The rows are valued by `cf_objective.harm_to_others` under D171 (2) replacement
   semantics, so each displaced request is charged
   `w_o * (p_before - p_after) * (acc_cloud_o - acc_dev_o * p_dev_on_time_o)`
   and never its full cloud accuracy. `harm_warm` is the sum over affected requests.

4. **Cap, and its counter.** If a warm's queued-ahead token count falls outside the range the
   D162 model was fitted on, the term is capped at the healthy-regime bound (first-token p50
   **2.781 s**, D160 (2)) and `harm_warm_capped` is incremented. A capped row is reported as
   capped; the cap is never silent. `harm_warm_capped == 0` is not assumed and is reported either
   way.

## What is reported

`HOLD_BACK`, `WARM` and `TOUCH` gains **separately** against `MARGIN_CF = 0.16456`, each with n,
mean, max and the count exceeding the margin, plus `harm_warm_capped`. `MARGIN_CF` is never
changed (D157, D172).

## Register

The D162 coefficient is a **fitted** value on healthy-regime rows, so every number derived here
is a prediction and not a measurement of a warm's realised cost. `StudySLICE1`, which would
measure it, has not run. A `HOLD_BACK` or `SLICE` result off this computation is a statement
about the cost model, and any report of one must say so.

## Provenance

The ruling reached this session relayed by the H100 session, quoted as the user's words, while the
user was away. The coefficient was checked against the committed gate file before this file was
written and matches `per_queue_token` to the precision quoted. Marked **PROVISIONAL** under
D106 / D116 until the user confirms directly.
