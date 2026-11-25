# `covex-v6-final-kr` build estimate (read-only, nothing built)

Estimate produced 2026-11-24 on the user ruling that **the counterfactual's paper role is STATE management
under memory and network change**. Rung 4 re-conceived as a memory-aware state counterfactual on
`covex-v6-fair-final`, with the request-side legs off. **No code was written. No cell was run.**

**Headline: 25 to 44 hours (about 1.5 to 2.5 session-days), plus a 1 to 2 hour reachability gate that comes
first and may remove component (a) entirely.**

## The finding that decides the shape

**The analogous candidate loop does NOT exist in `v5/cf_planner.plan_state`.** It is at
`v5/cf_planner.py:617`, takes **one** `device_id`, builds six scalar candidates (WARM / TOUCH / KEEP /
RELOAD / HOLD_BACK / SLICE) and returns `max(scored, key=value)` for that session. **It holds no
cross-session state, no pool term and no budget argument at all.** The loop is in the caller,
`arms_v6state.py:398`, and carries nothing between iterations but `drop` and `extra` lists.

So (a) is **not** a top-k-instead-of-argmin edit. It is a **new set-selection layer** wrapping that caller.
The argmin that *is* the right shape, `arms_v6cf.py:265 _pd_victim`, sits on the request side the ruling
switches off, and so does the budget read it needs (`_pd_free_kv`), which must be **lifted into a shared
module rather than imported from the arm being disabled.**

## Reachability per component

**(a) KEEP-READY SET: reachable in principle, UNMEASURED in fact. Gate before building.** The pool binds at
0.5x (`rebuild_fits_without_evicting` 113 of 342 and 101 of 309) and the per-session planner deviates on
2,386 of 65,044 `state_decisions`. But a joint selection can differ from independent argmax **only on
epochs where the independently selected set's token cost exceeds free pool, and that quantity is committed
nowhere.** No counter exists. The cheap gate: recompute `occ_belief` as the sum of `built_tokens` over
`gpu_warm_sessions` per epoch from a committed rung-3 kv0.5r decision log and compare against the pool.
**If the independent set never exceeds free pool, (a) is UNEXERCISED and must not be run.**

**(b) PRE-WARM: the ruling names one blocker; there is a second and it is fatal as built.** Blocker 1 is
`arms_v6state.py:445` passing `warm_expressible=bool(warming)`. **Blocker 2: there is no enact branch for
`chosen == "WARM"`** - the enact handles only TOUCH, HOLD_BACK and SLICE. That is harmless today precisely
because WARM is only expressible when the rebuild is already going out, so choosing it is a no-op equal to
KEEP. **Lift the tie and WARM becomes a write-only choice**, logged in `state_chosen_WARM`, visible as a
`state_action` row, and causally inert. The read that must consume it is `coordinator.py:929-932`
(`MATERIALIZE` to `_advance_build`), so (b) requires **emitting a new `SessionAction(MATERIALIZE)` outside a
warming period**, not a flag flip.
Magnitude, which must be pre-registered or (b) delivers an unexercised null dressed as a negative: WARM's
harm is priced on the **full uncached `u`** while TOUCH uses the constant `TP_TOUCH_UNCACHED`, so **WARM is
dominated by TOUCH wherever `u > TP_TOUCH_UNCACHED` and both are expressible.** Lifting the tie plausibly
moves the **scored** candidate count by thousands and the **chosen** count by **single to low double
digits**.

**(c) SHADOW-PRICE HARM: the strongest of the three, with a guaranteed change and a built-in confound.**
The implementing quantity is hardcoded: `arms_v6state.py::_queued_behind` appends every pending request
with `"weight": 1.0`, so every displaced device is priced equally regardless of deficit - **a CONSTANT
today**. `v5/cf_objective.py:79` states in the code that this weighting "acts, and acts only, where devices
compete: the harm term of a request decision", which is exactly this field. Every link from the weight
through `harm_warm_from_queue_delay` to `plan_state`'s value comparison is a **read**.
**The confound, to be answered in Step 5:** new weights lie in [0,1) where old ones were 1.0, so (c) can
only lower harm and only increase deviations. **"Fairness pricing helped" and "the harm bar was loosened"
make the same prediction.** The distinguishing data is the deviation delta **stratified by at-or-above-
target victims (weight exactly 0) against below-target**, never the population figure.

## Hours by component

Anchored on **D222 pass 1** (910 insertions, 8 files, 5 items, about 1 day), the closest in shape because it
is also a pricing change inside an existing planner with a proofs script rather than a new action type. The
DEVICE_ANSWERS build (1,890 insertions, 9 files, about 2 session-days) anchors only (b)'s new emission path.

| component | hours | what drives the spread |
|---|---|---|
| shared: pool read, deficit weight, selection ledger (build once) | 4 to 7 | lifting `_pd_free_kv` out cleanly against duplicating it; the ledger schema is most of the work |
| (a) joint keep-ready selection | 8 to 14 | low if the gate shows the budget binds and ranking is a sort plus prefix cut; high if `plan_state` needs a set-mode signature, which puts `cf_planner.py` in the live path and re-runs every rung-3 identity proof |
| (b) pre-warm | 6 to 12 | low is lifting the tie and accepting a near-null; high includes the new MATERIALIZE emission and its expressibility proof |
| (c) shadow-price harm | 3 to 5 | the weight is one field; the cost is the stratified Step 5 analysis, not the code |
| pre-registration, three off-switch byte-identity proofs, switch-diff rows | 4 to 6 | three components means three independent off-switches |
| **total** | **25 to 44** | plus the 1 to 2 hour (a) gate, which comes first |

## Files, with the conflicts that must be sequenced

Live path: `arms_v6state.py` (the caller loop, `warm_expressible`, the `_queued_behind` weight, the enact
branches), `v5/cf_planner.py` (only if (a) needs a set-mode signature), `v5/cf_objective.py`. New:
`kr_pool.py`, `arms_v6cf_kr.py`, plus a proofs script and a one-cell runner.
**Conflicts with another session's held 19-path bundle, to be ordered rather than discovered:**
`arms_v6cfr3.py` (the arm registry), `arms_final_ladder.py`, `d225_switch_diff.py`.
**`coordinator.py` needs NO edit** - both read sites already exist (`:927-928` `_submit_touch` gated on
`_touch_requests`, and `:929-932` `MATERIALIZE` to `_advance_build`). `arms_v5rules2.py` and
`share_admission.py` stay read-only. `fleet/emulator.py` is H100-owned and untouched.

**The inertness trap, named:** the arm **must declare `live2_touch_requests = True`**. `desired_tier` is a
**write-only field and the code says so at `coordinator.py:944-945`**; the causal half is `_submit_touch`,
resolved by a plain `getattr(..., False)`. Every placement choice is logged as a `state_action` row at
`:911-918` **regardless**, so an arm missing that declaration produces a fully populated, fully differing
decision log while doing nothing to the engine, and a switch-diff pass reads green.

## Proving "the joint selection respects the pool budget"

Emit a **per-epoch selection ledger at the point of selection, before enact**: `pool_tokens`, `occ_metric`,
`occ_belief`, `occ_used`, `free`, and the ranked candidate list with each `cost_tokens`, the running
cumulative sum, the accept or reject flag and the reason. Then three checks offline over committed JSON.

1. **Arithmetic invariant.** Per epoch, the accepted costs sum to the cumulative at the last accept and that
   is at most `free`, and the first rejected candidate would have exceeded `free`. Recomputed from the
   ledger's own fields, so a selector bug cannot hide behind a selector-computed sum.
2. **The clipping defence, which the naive version misses.** A selector that over-asks and is clipped
   downstream satisfies check 1 when check 1 is read off the **enacted** set. So reconcile **three
   independently sourced counts per epoch**: selector accepts, emitted actions, and coordinator enacts,
   together with the engine's budget-refusal counter. **Committed precedent for exactly this shape:
   `covex-v6-state` s4 produced 1,438 touches with 12,824 budget refusals** - downstream refusal silently
   absorbing an over-ask.
3. **Both ends of the control (consistency check 7).** `pool` infinite: every positive-value candidate
   accepted and the arm must differ from rung 3. `pool` zero: no accepts and the arm must reproduce rung 3
   **byte-identically**. If the zero case does not reproduce rung 3, the selector is coupled to something
   other than the budget and the comparison is void.

**What a violation looks like in a committed artefact.** Directly, a ledger row whose accepted cost sum
exceeds free pool. Indirectly, and this is the one to watch: a row within budget **while**
`state_touch_emitted` exceeds `submitted_touch`, or emitted exceeds enacted, or a non-zero budget-refusal
delta concentrated on the epochs where the selector sat at its cap. **That pattern means the selector's
budget and the engine's budget are two different numbers.**

**One limitation to pre-register:** `obs.cloud.gpu_kv_fraction` is **identically 0.0** in both dry and live2
cells, so `occ_metric` is 0 and **the belief bound always binds**; the engine-metric half of the budget is
**UNEXERCISED** until the E1 split fix lands. Describe the budget as belief-bounded, not two-sourced.

## What should not be built

Nothing on the request side (per (d)); no new action type for WARM-ahead (reuse `MATERIALIZE`, which avoids
the `coordinator.py` edit and the bundle conflict); no `desired_tier` consumer, because it is write-only by
design and `submitted_touch` is the causal counter; no engine-metric scrape brought in as a side effect; no
margin or safety retuning and no new slice values (SLICE's half-harm model is declared and never measured);
and **no (a) at all until the gate pass shows the independently selected set ever exceeds free pool.**

**Build once, shared across (a), (b) and (c):** `kr_pool.py` holding the free-pool read lifted out of
`_pd_free_kv`, the deficit weight used by **both** (a)'s ranking and (c)'s harm so the two cannot drift
apart, and the per-epoch selection-ledger emitter, which is simultaneously (a)'s whole proof and half of
(b)'s.
