# StudyOUTAGE-CORR build status, 2026-11-24 22:30: ALL FOUR BUILD ITEMS DONE, AND THE EXPERIMENT IS BLOCKED ON TWO INDEPENDENT GROUNDS

**Nothing is applied and nothing is pushed to `experiments/`.** The D242 freeze on
`experiments/orchestration` and `experiments/lib` is intact. **No cell has run and none can be queued
without a user ruling.**

## What is built, with proof status

| item | built | proofs |
|---|---|---|
| **A** trace-level correlated outage, default OFF | YES, 3 files | **OFF-path byte-identity PASSES** on all three trace files in two configurations, and the committed `fairness_digest 96c1a048...` reproduces exactly. Probe shown non-vacuous three ways. **`fleet/links.py` needed NO edit**: the burst and `queue_s` come from committed code. |
| **B** the per-device last-arrival observable | YES, 3 files | **READ SITE NAMED AND FIRING**, below. Not write-only. |
| **C** `-outage` and `-outage-fifo` | YES, 2 files, 710 new lines | switch read-back PASSES typed; one-factor **40 of 42 attributes identical**, differing only in `name` and the ordering flag; **every other `arms*.py` byte-identical**; outages-OFF decision log **identical to rung 3**, digest `edb7e94867917ac0b845f0e0432f05b9`, with `llf` as a positive control proving the check can fail. |
| **D** proofs | PARTLY | the 1,200 s identity proof is **OWED**: a 1,200 s cell did not finish, so the identity rests on 300 s and the outage proof on 700 s. |

**The named read site, item B's gate:** `arms_v6outage.py:392` puts a device into the catch-up set only when
its arrival gap exceeds the threshold, and `:423` drops a still-dark device from the epoch's candidates. The
chain to the enacted action runs through the **unedited** coordinator: ordered asks are spliced to the front
of `act.sessions`, `coordinator.py:945` walks that list **in order with no sort**, `:968` dispatches
MATERIALIZE, and `_advance_build` accumulates `_uncached_in_flight` at `:1399` so an earlier ask consumes
what a later one is refused from. **Evidence it fires: 2,996 reads with outages off and 6,996 with them on,
detecting exactly the 5 dark devices.**
**A design decision measured before it was written: a REORDER-ONLY branch would have been unexercised in
3,000 of 3,001 epochs**, because rung 3 emits zero session actions in 2,968 of them. **That is why the
branch issues rather than only reorders**, and it is the kind of check that turns an absent link into a
design.

## *** BLOCKER 1: THE ORDERING IS A PURE PERMUTATION. THE TWO ARMS' FULL DECISION-ROW MULTISETS ARE IDENTICAL. ***

The ordering **fires**: 22 of 22 orderable epochs differ from FIFO, digests differ, 61 positional row
differences. **But the multiset difference over the FULL ROW is 0**, and also 0 over `(t, kind,
piece_tokens)` and over the harness's own `_decision_key`. **The two arms build the identical set of
pieces, permuted within the same decision periods.**
*** RULE 2 CLASSIFICATION: INCONCLUSIVE, "CANCELLED BY GEOMETRY". The quantity is alive and cancels between
the compared branches because NO GATE REFUSED ANYTHING. It is NOT "fired and did not help" and it is NOT a
negative about the ranking. ***
**Three separable causes, two of which are defects:**
1. *** `obs.cloud.gpu_kv_fraction` IS A STRUCTURAL ZERO IN A DRY RUN. *** `cstate.observation` reads it from
   `metrics["vllm:gpu_cache_usage_perc"]` with a 0.0 default, and a dry cell has no vLLM. **So the pressure
   test is a CONSTANT link in every dry cell** - the `desired_tier` and E36 shape exactly, and the reason
   the qualified count is 0 rather than low.
2. **The demand term is not the pre-registration's quantity**: 38,009, the unbuilt remainder of the five
   victims, against the prereg's resident history plus backlog across all sessions.
3. *** NO GATE ACTUALLY REFUSED. The binding gates in `_advance_build` are `budget.can_spend` on GPU
   SECONDS and the D179 share gate, NOT a KV-TOKEN CAP. *** So "within the GPU pool", the constraint the
   ruling asks the ordering to respect, **may not be enforced by any decision-refusing gate at all.**

**Options, none chosen:** (a) derive occupancy from the arm's own belief, fixing cause 1 only and
substituting a belief proxy for a physical quantity; (b) redefine demand as the prereg's quantity, fixing
cause 2 and still blocked by cause 1; (c) ship the unqualified count of 22 and leave the qualifier at 0,
which is what is built; (d) **run below 1x so a gate refuses, which is the ONLY option addressing cause 3
and which D240 FORBIDS.**

## *** BLOCKER 2, INDEPENDENT: AMENDMENT 1. THE GRID'S PREMISE IS UNSUPPORTED. ***

The 55,000-token history figure matches no measured quantity: per-robot resident history is **4,217** at
p50 and the whole resident fleet peaks at **48,975**, below the figure used for one history. **On an empty
pool all three k values FIT and the grid has no positive condition.** See
`research/study_outage_corr_AMENDMENT_1.md`.

## *** THE TWO BLOCKERS MEET, AND THE MEETING POINT IS A RULING ONLY THE USER CAN MAKE ***

**Blocker 2 says the pool may never be exceeded at 1x. Blocker 3's cause 3 says that even when it is, no
gate refuses on KV tokens. And the one regime where a gate demonstrably refuses is below 1x, which D240
excludes for all outage work.** **So as specified, the experiment cannot distinguish the planner's ranking
from FIFO, and a k-grid run tonight would produce a null that says nothing about the ranking.** That is
the same structural tension already recorded against freeze-gate row 10.13, now concrete and blocking.

## Integration between items A and B, resolved

Item C reads **`Observation.last_arrival_s` and nothing else** - no `queue_s`, no `t_offer`, no
`trace_meta` - and `switch_report()` publishes `"does_not_read": ["queue_s", "arrival lateness",
"trace_meta outage schedule"]` so it cannot drift. **Item B's open question is answered by item A's
design:** the in-window `recall_question` keeps its ask time but gains a `t_offer` set to the reconnect, and
the emulator passes that offer into `UplinkQueue.send`, so **arrival at the coordinator occurs at or after
the reconnect and never during the window.** The detector's event-kind set is therefore correct as built and
needs no narrowing.

## Still owed

**The 1,200 s outages-OFF identity proof**, the only proof not delivered. And four methodological stops
from item A plus four from item B and C, all declared beside the code as PROVISIONAL and pre-ruling, none
chosen silently. **The threshold that detects a reconnect was measured rather than guessed: 20.0 s, twice
the largest natural arrival gap of 10.000 s observed with outages off.**
