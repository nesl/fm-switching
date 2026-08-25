# Kill Conditions for the Fleet Capacity Claim (corrected)

Status: pre-registered 2026-08-24, before the next run. Supersedes the conditions
used in E36/E36b/E36c/E36d. Fixed now and applied as written.

---

## Why the previous conditions were wrong

The previous set — (a) always_window within 5 pp of maintenance_aware, (b)
always_full within 5 pp, (c) footprint_ranked within 5 pp, (d) accelerator never
binds, (e) advantage does not grow with fleet size — tests whether an adaptive
policy beats fixed policies. That is a different and weaker claim than the one
the paper makes, and two of the conditions are actively backwards:

**(b) punishes the policy for being correct.** The measurements say full history
is the cheapest representation to maintain (66 ms/turn vs 652 ms amortized for
win10 and 5,822 ms for sum200). If the claim is right, the correct choice under
contention usually *is* full. A policy that discovers this will be
indistinguishable from always_full, and (b) fires. The condition can only be
satisfied if the optimal choice is something other than full, which the
committed measurements say it usually is not.

**(c) fires on ties from a collapsed choice set.** footprint_ranked and
maintenance_aware agree whenever only one fidelity is admissible, which is the
case for LoCoMo at q>=0.30 (only full) and for EgoSchema (sum200 dominates on
every criterion). A tie produced by there being nothing to choose between is not
evidence about the mechanism in either direction.

**(e) presumes the wrong functional form.** The capacity claim is about *which
resource binds*, and the binding flip occurs at a turn-rate threshold, not
gradually with fleet size. E36d shows the gap largest at ti=5 s and flat
thereafter, which (e) reads as failure when it is the predicted shape.

Only (d) — does the accelerator ever bind — tests the story, and it is
necessary but not sufficient.

---

## The claim, stated so it can be tested

Representations differ in maintenance cost. Maintenance consumes accelerator
time. Accelerator time is finite and shared across the fleet. Therefore the
number of concurrent sessions a tier can support depends on the representation
held, and the ordering by memory footprint is inverted relative to the ordering
by maintenance cost. A selection rule that ranks by footprint lands on the wrong
side of this inversion whenever the accelerator is the binding resource.

This is a claim about a capacity relationship, not about a policy tournament.
Test it as a measurement first, and only then ask whether a policy exploits it.

---

## Primary conditions (the capacity relationship)

**P1 — Inverted orderings.** Sessions supported per representation must be
ordered differently under the memory constraint than under the accelerator
constraint. Specifically, sum200 must support the most under memory and the
fewest under accelerator, with full the reverse.
FAILS IF: the two orderings agree, or either ordering is not monotone.
Committed expectation: memory admits ~7 full / ~22 win10 / ~978 sum200;
accelerator at a 30 s turn interval admits ~454 full / ~46 win10 / ~5 sum200.

**P2 — The binding resource flips.** There must exist a turn-rate threshold at
which the binding constraint changes from memory to accelerator, and it must
occur at different turn rates for different representations. Report the
threshold per representation.
FAILS IF: one resource binds everywhere in the swept range, or the threshold is
identical across representations.

**P3 — Footprint-based selection lands on the wrong side.** In the regime where
the accelerator binds, a rule that ranks by value-per-byte must select a
representation that supports fewer concurrent sessions than the
maintenance-ranked choice. Report the sessions-supported difference, not an SLO
percentage.
FAILS IF: footprint-based selection picks the same representation as
maintenance-ranked selection wherever the accelerator binds.

**P4 — The mechanism is load-bearing.** With maintenance costs set to zero, P1
through P3 must collapse. Report the negative control for each.
FAILS IF: any of P1-P3 survives with maintenance disabled — the effect is then
driven by something else and must be identified.

---

## Secondary conditions (does a policy exploit it)

Only evaluated if P1-P4 pass. These ask whether the relationship translates into
outcomes, and they are scoped so a correct choice is not penalized.

**S1 — Best fixed representation is regime-dependent.** The representation
maximizing SLO attainment must differ across the swept conditions. If one fixed
representation is optimal everywhere, no selection policy is needed and the
contribution is the capacity characterization plus a recommendation.
This is a scoping outcome, not a failure.

**S2 — Selection matches the best fixed choice per regime.** maintenance_aware
must match or beat the best fixed policy in each cell, not differ from it.
Matching always_full where full is optimal is a PASS, not a failure. Report the
per-cell regret against the best fixed policy.
FAILS IF: maintenance_aware is worse than the best fixed policy by more than
5 pp in any cell where the choice set has more than one admissible option.

**S3 — Footprint ranking is measurably worse where the accelerator binds.**
Compare against a competent footprint_ranked with a device-fallback check, so
the incumbent is not artificially bad.
FAILS IF: competent footprint_ranked matches maintenance_aware in the
accelerator-bound regime.

**S4 — Activation region reported honestly.** State the number of cells in which
the mechanism activates, the conditions required for activation, and the
structural reason for every non-activating cell.
This is a reporting requirement, not a pass/fail.

---

## What each outcome means for the paper

- P1-P4 pass, S1-S3 pass: capacity characterization plus a selection policy.
  Full system contribution.
- P1-P4 pass, S1 shows one fixed representation optimal everywhere: capacity
  characterization plus a design recommendation. The policy is dropped; the
  measurement stands. This is a legitimate and reportable outcome.
- P1-P4 pass, S2 or S3 fail: the relationship is real but not exploitable by the
  proposed rule. Report the characterization and the failure of the rule,
  including why.
- Any of P1-P4 fails: the capacity claim itself is not supported. Report which
  link broke and stop.

---

## Modeling requirements carried into the next run

These are not kill conditions but the conditions under which the above are
meaningful:

1. Maintenance consumes accelerator capacity and delays other robots' queries
   through queueing, but is NOT charged to the querying robot's own TTFT unless
   its state was stale at query arrival. Per FORMULATION.md §5, prefill is a
   resource spent ahead of time, not a critical-path latency. Report how often
   the staleness case occurs.
2. Every edge policy includes a device-fallback check: a robot is assigned to
   the edge only if its expected outcome there is at least as good as on device.
   Without this the incumbent is artificially bad and every gap is inflated.
3. Edge KV capacity is fixed, swept independently of fleet size.
4. Window maintenance is modeled as growth (36 ms, prefix preserved) versus
   slide (~1,031 ms, prefix invalidated) with slide frequency driven by session
   structure, not as a flat amortized constant.
5. Robot session phases are desynchronized at initialization.
6. q_min is never lowered below 0.12 to make LoCoMo summaries admissible.
