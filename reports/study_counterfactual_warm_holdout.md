# Session B's frozen `P_hat`: the zero warm held-out rows are STRUCTURAL

Session D (flash / A6000), 2026-11-21, overnight window. Analysis only, no run.

## Why this exists

`results/orchestration/live2/v5/cf_ontime_model_frozen.json` declares, in session B's own artefact:

```
residuals -> {'n_held_out': 101498, 'warm_rows_held_out': 0}
```

I reported that zero at 06:00 as the fourth and structural reason MARGIN_CF stays unset, but I had
only the declaration, not the cause. The cause is now measured, and it is worse than incidental.

## The cause

`cf_cost.py:63-66` sets `GATE_SPLIT = "by_arm"` and reads the committed
`results/orchestration/live2/frozen_test/cost_model_gate.json`. That split **fits on the non-hybrid
arms and holds out the hybrids**. Request-level warm share of every cell in the 26-cell gate set,
measured from `request.jsonl` with `cached_tokens > 0` as the warm test:

| arm | cells | warm share of requests |
|---|---|---|
| `hybrid-F-lhreq` | s0, s4, s5, s6 | **0.00 percent, all four** |
| `hybrid-F6-lhreq` | s0, s4, s5, s6 | **0.00 percent, all four** |
| `edf` | s4, s5, s6 | 2.65 to 2.68 percent |
| `llf` | s4, s5 | 2.66 to 2.70 percent |
| `eco-llm`, `mooncake`, `b7-edf-feasibility`, `always-cloud-fcfs` | 14 cells | **0.00 percent** |

Whole gate set: **1,797 warm requests of 345,072, or 0.52 percent.** The gate JSON states
`n_requests` 345066 and `warm_requests` 1797 independently, so the warm count matches exactly and
the total reconciles to within 6 requests (0.002 percent). The 6-request gap is expected and not a
discrepancy: `cost_model_gate.features()` keeps only rows with `t_submit`, `t_done` and
`t_first_token` all present and `prompt_tokens` truthy, while this count requires only `t_submit`.
Stated rather than rounded over, because an unexplained difference between two sources is the thing
check 1 exists to catch.

**The `by_arm` split holds out exactly the eight cells that contain no warm rows at all.** The zero
is therefore not a sampling accident that more data would fix. **That split cannot validate warm
first-token prediction even in principle**, because the held-out side has no warm row to validate
against. The gate's own `held_out` block says so in its structure: under `by_arm`, `all` and `cold`
both report n = 101,498 and there is no `warm` entry, whereas the `by_seed` split does carry one
(n = 1,077, ratio 0.9108).

## Why that matters for MARGIN_CF

MARGIN_CF (D157 (2)) is scored on the four EP-G WARM-ALL held-out cells, whose request-level warm
share is **83 to 91 percent**. So `P_hat` would be:

| | warm share |
|---|---|
| fitted on | 0.00 to 2.70 percent per cell, 0.52 percent pooled |
| **validated on** | **0.00 percent, structurally** |
| applied to | **83 to 91 percent** |

Two independent extrapolations, one of them unvalidatable by construction. **This is the same
confound the assessment already recorded as "warm is confounded with arm", in its sharpest possible
form: the arm that is held out is the arm that is never warm.** MARGIN_CF stays unset on this ground
regardless of how the other three resolve, and the remedy is specific rather than "more data": the
split must hold out an arm that produces warm rows, which among committed cells means the `by_seed`
split or a new split over the WARM-ALL arms.

## A second extrapolation, found while restricting the cell set

Pinning set B to the gate's exact 26 cells (its own `arms` field crossed with its `CELL` template at
seeds 0, 4, 5, 6) showed something the looser 29-cell glob had hidden, because the glob pulled in an
`_n20` cell that is not in the gate's set and is the only severe cell among the extras.

**Across all 26 cells the gate is fitted on, the worst first-token p50 in any 100 s window never
exceeds 2.781 s, and it is 0.915 s or below in 23 of them.** The EP-G WARM-ALL cells MARGIN_CF is
scored on reach worst windows of **31 to 478 s**.

So `P_hat` is fitted on a regime where the service is never more than about 2.8 s behind, and
applied to one where it is up to 478 s behind, a factor of about 170. That is a second extrapolation
independent of the warm one, and it is on the axis the model's own `overlap` term is supposed to
carry. Whether a linear `overlap` term extrapolates 170x is untested. REGISTER: this is a
**statement about the fit and test regimes**, measured; it is **not** a claim that the model is
wrong there.

The two extrapolations compound rather than overlap, because warmth and load are different axes:
the warm one has no held-out row at all under `by_arm`, while the load one has held-out rows but
only within a 2.8 s band.

## Register and consistency checks

- **MEASURED**, from `request.jsonl` over 29 extracted cells, cross-checked against the gate JSON's
  own `n_requests` and `warm_requests` totals.
- **Check 7, validate the control.** The `by_seed` split is the positive control and it **passes**:
  it has 1,077 warm held-out rows and a warm first-token ratio of 0.9108, so the estimator can be
  validated on warm data when a split provides any. The failure is the split, not the estimator.
  This is the same finding shape as the D156 (4) gate, where the positive control passed and the fit
  set was at fault.
- **Check 4, definition audit.** "Warm" here is `cached_tokens > 0` on the engine's own per-request
  telemetry, which is the definition `cost_model_gate.features()` uses (`warm=bool(ct > 0)`). It is
  **not** the coordinator's belief (`release_at_GPU-WARM`), which this report does not use and which
  is known to run conservative.
- **Rule 2.** Not a null and not classified as one. This is a design defect in a held-out split.

## What is NOT claimed

Nothing here says `P_hat` is wrong on warm requests. It says the committed `by_arm` validation
**cannot speak to** warm requests, so its held-out error is not evidence about the regime MARGIN_CF
is scored in. Whether `P_hat` transfers to 83 to 91 percent warm is untested, and testing it is a
decision for the user, not an analysis step.

## Session B's state, for the record

Session B's last push to origin was `023ce6f` at 2026-11-20 20:02, before the 21:00 window opened.
**Nothing from B landed during the overnight window.** The deficit weighting and the p99 instrument
remain UNKNOWN and are reported as unknown rather than inferred from the files, which is the same
position as the 06:00 summary and not a new one.
