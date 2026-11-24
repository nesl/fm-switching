# `covex-v6-final-nqd` — build record, four proofs, and the two consistency protocols

Base sha, resolved once: `1a092abd9009df90e4e0ce88b9af640369dd62be` (origin/main).
Pre-registration frozen at **12:58:57**, sha256 `58b24f24ea7f3fc0e14a649885824a1d`; the first cell
ran at **13:21:35**. Every cell is DRY and LOGICAL, on flash's CPU. No engine, no GPU, no
`--num-gpu-blocks-override`, no real KV allocator. Nothing in `/home/pragya/Desktop/FM-switching`
was modified: the whole build is a `git archive` of the base sha in this session's scratchpad.

## GUARD EXIT CODES — one beside every digest (D232 (6))

| phase | guard exit | fatal | advisory | what ran after it |
|---|---|---|---|---|
| `pristine` | **0** | 0 | 3 (the three declared files, not yet changed) | the patches |
| `built` | **0** | 0 | 0 | `nqd_abc.py` on the built tree → proof (a) |
| `before_proofs` | **0** | 0 | 0 | `nqd_proofs.py` 1x → proofs (b), (c), (d) |
| `before_kv05` | **0** | 0 | 0 | `nqd_proofs.py` kv0.5 enforced |
| `final` | **0** | 0 | 0 | — |
| `step2b` | **0** | 0 | 0 | `nqd_step2b.py` at both regimes |

The chain tests each with `if [ "$GUARD_RC" != "0" ]; then exit 1; fi` — never `&&`/`||`, because
`set -e` is suppressed inside an AND-OR list. It did hard-stop once, on run 1, on a different
assertion (see "the check was broken" below), and ran nothing after it.

## THE FOUR PROOFS

### (a) non-counterfactual arms byte-identical — **PASS, 0 of 7 moved**

One tree, measured pristine then built, same script and same import set.

| arm | pristine | built | rows | verdict |
|---|---|---|---|---|
| `hybrid-F-lhreq-noc3` | af8befb9420ad86a | af8befb9420ad86a | 12085/12085 | IDENTICAL |
| `covex-v6-state-final` | 9a4be873eb3c5fba | 9a4be873eb3c5fba | 14218/14218 | IDENTICAL |
| `covex-v6-fair-final` | 5a03c2807da3681a | 5a03c2807da3681a | 14539/14539 | IDENTICAL |
| `mooncake` | 7544b3aa16433c70 | 7544b3aa16433c70 | 12742/12742 | IDENTICAL |
| `simplestream` | e06add73698466bd | e06add73698466bd | 12253/12253 | IDENTICAL |
| `llf` | 961be8fe4942d86b | 961be8fe4942d86b | 14075/14075 | IDENTICAL |
| `covex-v6-final` (positive control) | 20393b11dd55e118 | 20393b11dd55e118 | 14539/14539 | IDENTICAL |

Six frozen files byte-identical before and after, `arms_final_ladder.py`
(`bdad5a2ce2ddd47d…`) and `coordinator.py` (`ab00eb2f31f0cc24…`) among them.

### (b) off-switch bar — **PASS**

`covex-v6-final-nqd-off` = `5a03c2807da3681a` = `covex-v6-fair-final`, byte-identical, both
measured in one process. So the two added channels do nothing on their own, AND deleting
`_Rung4Mixin` from the MRO changed nothing else: rung 3 is exactly what is left.

### (c) Step 2b — **the switch moves decisions. NOT an absent link.**

| regime | A `-nqd-daoff` | B `-nqd` | SETWISE | POSITIONAL | rows A/B |
|---|---|---|---|---|---|
| 1x | 5a03c2807da3681a | 1d2c6f5e03b409ea | **93** (46 only-A, 47 only-B) | 1,606 | 14,539 / 14,540 |
| kv0.5 enforced | 99e8a1203d244694 | e431e2f4edb5612d | **5,678** (3,115 / 2,563) | 8,124 | 14,298 / 13,746 |

**Both registers are reported because the positional number cannot carry the meaning its name
suggests.** At 1x the two logs differ by ONE row, and a positional walk counts every later row as
differing, so 1,606 is a true count of disagreeing POSITIONS and a false reading of "decisions the
switch changed". 93 is the setwise answer. This is the project's own convention
(`d184_r3_c5attr_proofs.json` reports "4512 / 12272 setwise / positional").

First decision that actually changed at 1x — found by multiset, so it is a changed decision and
not a displaced one: index 12,874 in B, `kind: "decline"`, `opp0010742`, t = 1052.8.

### (d) zero `rd_question_defers` BY CONSTRUCTION — **PASS**

The claim is about code, so it is made and checked in code. `covex-v6-final-nqd`'s MRO is
`covex-v6-final-da`'s **minus one entry**:

```
V6Final      : V6Final  _Rung4Mixin  _ProtectDeferMixin  V6FairFinalWired  _PlannerFeedMixin  …
V6FinalNQD   : V6FinalNQD            _ProtectDeferMixin  V6FairFinalWired  _PlannerFeedMixin  …
```

Four routes closed, each asserted at construction (`QuestionDeferralStillPresent` otherwise):

| route | observed |
|---|---|
| `_Rung4Mixin in MRO` | `False` — and `arms_v6cfr3.py:412` is the ONLY write to `rd_question_defers` outside `held/`, inside `_Rung4Mixin.decide`, so it has no call path |
| first `decide` owner | `_ProtectDeferMixin` (not `_Rung4Mixin`) |
| `rd_*` state attrs | `[]` — nothing allocated, so `coordinator.write_rd_decisions` returns `None` and no `rd_decisions.jsonl.gz` is written |
| `live2_cf_request_defer` declared on any decide-chain object | `[]` — the switch is **ABSENT**, not False, and no reader survives that could act on it |
| `rd_report` resolves | `False` |

Corroboration (not the claim): after a full dry cell the set of `rd_*` keys in the arm's stats is
`[]`, against `covex-v6-final`'s 15+ (`rd_decisions`, `rd_gate_*`, …).

### THE PORT RULE — the characteristic decision occurs

| regime | `pd_request_device_answers` | declined | `unexpressible` in `-daoff` | trades |
|---|---|---|---|---|
| 1x | **1** | 1 | 2 | 1 |
| kv0.5 enforced | **14** | 16 | 25 | 14 |

**At 1x the census reconciles exactly.** All three arms record identical decision populations —
`pd_decisions` 245, request 82, state 163, `pd_harm_n` 3, `pd_harm_over_bar` 2 — and the switch
converts the 2 `pd_request_crossed_bar_unexpressible` into 1 enacted deviation + 1 declined trade,
with the `wanted_to_act_but_a_request_has_no_slice_channel` gate count falling 2 → 0.
**At kv0.5 it does not and cannot:** 25 against 14 + 16 = 30, because once a deviation is enacted
the arm's trajectory diverges (14,298 vs 13,746 rows) and the two populations are no longer the
same. The reconciliation is claimed only where it holds.

## STEP 3 — ONE TRACED UNIT, HAND-CHECKABLE

The 1x firing, every term from `pd_device_trades`:

```
p_self (P(on time) if admitted now)        0.8803439204547071
w_self (live deficit weight, this device)  2.068100358422939
own lost = w_self x p_self                 1.8206395774278352
saved for others, by type   alert          5.3101941   (5 requests moved)
                            recall         0.0         (0)
                            assistance     0.0         (0)
saved_total                                5.310194100609862
net = saved - own                          3.4895545231820266
bar = w_d x MARGIN_CF = 2.0681 x 0.65824   1.3613063799283156
TEST  3.489555 > 1.361306                  crosses = True   -> ra.decision = "DEVICE"
by-type sum identity                       holds, residual -6.1e-10 (tol 5e-10 x n_rows + 1e-12)
```

Every line is reproducible by hand from the two inputs. The kv0.5 regime gives 14 such traces.

## THE CONSISTENCY PROTOCOL — seven checks

**1. Cross-check against committed measurements.** Every quantity previously measured.

| quantity | this run | prior | source of prior | ratio | agree |
|---|---|---|---|---|---|
| `covex-v6-final` dry digest / rows | 20393b11dd55e118 / 14,539 | 20393b11dd55e118 / 14,539 | rung-4 pass 1's pristine baseline (handoff), base sha `b8ce0873` | 1.00 | **agree** |
| `covex-v6-fair-final` dry digest | 5a03c2807da3681a | 5a03c2807da3681a | `results/.../d218_device_answers/d218_prereg.json`, `frozen_test/runs/FINAL_LADDER_CELLS` | 1.00 | **agree** |
| `covex-v6-state-final` / `covex-v6-state-uo` digest / rows | 9a4be873eb3c5fba / 14,218 | same | `frozen_test/c5attr_digest_proofs.json` | 1.00 | **agree** |
| `hybrid-F-lhreq-noc3` / `covex-v6-base` digest / rows | af8befb9420ad86a / 12,085 | same | `frozen_test/c5attr_digest_proofs.json` | 1.00 | **agree** |
| `MARGIN_CF_ON_TIME` | 0.65824 | 0.6582 (D177 (3)) | `cf_protect_defer.py`'s own assert | 1.00 | **agree** |
| `pd_request_crossed_bar_unexpressible` at 1x | 2 | 2 | `d216_final_kv025/d216_final_kv025_report.json` | 1.00 | **agree** |
| same, at 0.25x | — | 27 | same | — | mine is 25 at **0.5x**, between the committed 2 at 1x and 27 at 0.25x, monotone in memory pressure |

The cross-sha quote in row 1 is labelled: a digest is comparable only within one base sha, and
these two are quoted across `b8ce0873` and `1a092abd` only because
`git diff b8ce0873 1a092abd -- experiments` is **empty**. No disagreement anywhere, let alone >2x.

**2. Physical plausibility.** No latency, throughput or size is measured or claimed here. The
harm and bar numbers are in *counts of expected on-time cloud answers*, not seconds or bytes, so
there is no implied rate to compare against `cost_matrix.csv`. The one rate-like input, the D162
price, is imported from `d162_price` and drift-checked there against `per_queue_token`; it is not
retyped. **Nothing to flag.**

**3. Distribution sanity.** Spreads reported, not medians alone.

| quantity | n | min | median | max | distinct |
|---|---|---|---|---|---|
| `w_self` over the 14 kv0.5 firings | 14 | 1.095238 | 2.015532 | 2.555556 | **11** |
| `bar` over the same | 14 | 0.720930 | 1.326704 | 1.682169 | **11** |
| `p_self` | 14 | 0.650326 | ~0.900 | 0.911536 | 14 |
| `net` | 14 | 1.573753 | ~2.5 | 4.097221 | 14 |
| declined-trade `net` | 16 | −0.334047 | ~0.5 | 1.268641 | 16 |

A bar with ONE distinct value would be a bar at the w = 1 floor everywhere and CONSTANT in Rule
2's sense however the arm were wired. All 14 bars are above the w = 1 bar of 0.65824, with 11
distinct values, so the live deficit weight is moving. The declined nets straddle zero, so the
comparison is two-sided and not a formality.

*Flagged, under "an artefact spread":* the 1,606 / 8,124 positional counts. They are real counts
of a real thing and they are **not** counts of decisions the switch changed. Both registers are
printed side by side above rather than one being chosen.

*Flagged, under "a real effect averaged into undetectability":* the saving is **100 % on the alert
stratum** — all 14 firings and the 1x firing save alert deliveries only, 3 to 6 requests each, with
explicit zeros for recall and assistance. Reporting a bare "saved_total" would hide that the
mechanism acts entirely on the loss the ladder exists to reduce. The stratum is reported beside
every total.

**4. Definition audit.**

| object | definition used here | matches prior? |
|---|---|---|
| dry digest | `test_hybrid.dry(realtime=False)` rows, committed `test_hybrid.STRIP`, UNWIDENED, `arm_version` dropped, sha256 of canonical JSON, first 16 hex | yes — `cf_pd_one_cell.py`'s recipe, and it reproduces four committed digests |
| a "decision" | one `decision.jsonl` record | yes |
| `rd_question_defers` | incremented once per enacted question deferral at `arms_v6cfr3.py:412` | yes |
| `MARGIN_CF` | `MARGIN_CF_ON_TIME` = `cf_objective.attainment_margin(cf_margin.MARGIN_CF)` = 0.65824, asserted == 0.6582 at 4 dp | yes, unchanged |
| `w_d` | `deficit_feed.DeficitFeed.weight_device`, floored at 1 (D178 (2)), re-floored at the point of use | yes |
| kv0.5 | `test_live2_coord.GPU_KV` 62,944 → 31,472, with `kv_capacity_enforced` set **on the instance** | same knob as `d210`/`d216`; see check 6 |
| alert attainment | `per_episode_PRIMARY.mean_attainment`, 19-instant denominator | the governing scorer's, per `d222_1x_s4_verdict.json` |

No name is used with two definitions.

**5. Claim linkage.** The headline bears on **C5 — "joint representation × placement × timing
beats decomposed policies under a quality SLO"** (`research/CLAIMS.md`, status *untested*).
DEVICE_ANSWERS is a *placement* decision (cloud answer vs device answer) taken jointly with the
*timing* decision already in protect-and-defer (latest safe start) under a deadline SLO, and the
ladder's rungs are the decomposed comparator. These proofs **do not yet support or weaken C5**:
they establish that the mechanism is present, reaches decisions and is attributable. The bar cells
are what bear on it. Nothing measured here is scoped out by `FORMULATION.md §Scoping`: no KV moves
between tiers (the deviation withholds a *request*, so no KV transfer occurs — the branch
deliberately does not protect the victim), and one model per deployment is unaffected.

**6. Proxy validity.** Two proxies, both stated.

* **`kv_scale` 0.5 on the coordinator's LOGICAL pool, as a proxy for the live `kv0.5r` cell's
  memory pressure.** What it actually measures: the arm's own read of a halved pool plus the
  coordinator's eviction when enforcement is on. It is NOT an engine KV allocator. Valid for
  *reachability* of the mechanism, which is all it is used for here; it is **not** used for any
  headline and the kv0.5 figures are labelled DRY throughout. Enforcement was read back off the
  instance (`asked_for` True, `read_back` True, type `bool`) because `CoordState` is a dataclass
  and a class-attribute set does not reach the instance — and it bound: `epochs_over_cap` = 6.
* **`pd_request_crossed_bar_unexpressible` in `-daoff` as the denominator the switch converts.**
  Valid at 1x, where the decision populations are provably identical. **Not valid at kv0.5**, and
  not used as one there.

**7. Validate the control, not only the result.**

* The **positive control** is `covex-v6-final`, a known-good committed arm, and it reproduces its
  committed digest and row count exactly. If it had failed, the check would be broken, not the arm.
* Three further committed arms reproduce (`covex-v6-state-final`, `hybrid-F-lhreq-noc3`,
  `covex-v6-fair-final`), so the control side of proof (b) is checked **against a committed value,
  not against itself**.
* The **negative control** in the name proof: an unregistered name must NOT resolve, and does not.
  Without it, "every name resolved" would also pass on a harness that resolved anything.
* `-nqd-daoff` at 1x is byte-identical to rung 3, independently reproducing the committed finding
  that protect-and-defer is **UNEXERCISED at 1x** — so the A-side of proof (c) is a verified
  control and the 93 setwise differences are attributable to DEVICE_ANSWERS alone.
* **The check that broke, recorded because it is the whole point of check 7.** Run 1's
  enclosing-block checker reported 13 of 22 assertions FAILED on a tree whose edits were all
  correct. The checker was wrong three times over: it took the *innermost* enclosing scope, it
  treated a `def` header line as inside its own body, and it then refused to step through a `for`
  loop. **An impossible failure is as diagnostic as an impossible success**, and a broken check
  would otherwise have passed every edit, because the edits were fine. The checker now carries
  nine positive controls and one negative control on a synthetic module and refuses to render any
  verdict (`exit 2`) if its own controls fail.

## RULE 2 CLASSIFICATION

No null to classify. Proof (c) is non-zero in both registers at both regimes, the port rule's
characteristic decision fires 1 and 14 times, and the mechanism's quantities vary across the
conditions where the claim says they should. The one quantity that is deliberately **ABSENT** is
pass 1's five items, declared as such in the pre-registration before any cell.
