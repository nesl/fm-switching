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
