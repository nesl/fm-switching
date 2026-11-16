# Scheduling policy v3.1: addendum to v3 (escalation basis; prefix survival)

Status: 2026-11-15 (A2 revised and A6 added the same day). v3.1 = `claude/policy_spec.md` (v3) + this addendum. Where they conflict, this addendum wins. Decisions D51-D55 in `claude/policy_design_log.md`.

## A0. Three flows, kept distinct

| flow | what moves | mechanism |
|---|---|---|
| History sync (recall evidence) | the device's past frames into the cloud's stored history | predictor-driven BATCHED upload (D28, D32); not a continuous trickle |
| Monitoring trigger (SH) | the current state of a stream, to decide whether to open an episode | device-side gain filter and/or cloud-initiated low-rate sampling ("trickle"); family decided by StudyCTRL1b (Q11) |
| Query (SS, RC) | the question plus whatever the cloud needs that it does not already hold | sent complete by default (A2) |

## A1. Unified escalation basis (D51)

Every request of every type (SH instant, SS query, RC question) is escalated on ONE rule: its estimated cloud gain,

    Ghat(r) = E[ u_cloud(r) - u_device(r) | observable features of r ]

computed from DEV-fitted lookup tables (non-learned). No request type is routed to the cloud by rule. The insights enter only as determinants of Ghat:

| insight | observable feature | effect on Ghat |
|---|---|---|
| the cloud holds more evidence | evidence coverage: does the request reference time beyond what the device holds (temporal reference vs the device's window) | missing local evidence -> large gain |
| the cloud is a better model | task-type posterior P(type given observable) | base gain per type (DEV table) |
| the device may be wrong | the device's self-normalized uncertainty (instability, rise vs own history) | higher uncertainty -> more gain |
| timeliness | deadline vs predicted delivered delay on this device's link, INCLUDING the query path actually used (A2) | late cloud answer -> gain to zero |

When the type is unknown, Ghat is the expectation over types:

    Ghat(r) = sum over types tau of P(tau | observable) * Ghat(r | tau, context)

Cloud admission (v3 section 7.1) uses the same Ghat inside DeltaJ_H, so device-side triggering and cloud admission use one formula.

## A2. Query path (D52 revised, D54)

- DEFAULT, COMPLETE QUERY: the device sends the whole query immediately: the question, plus for SS the current frame(s), plus for RC any history frames the cloud does not yet hold (usually none, because history is uploaded in predictor-driven batches). The cloud runs admission (DeltaJ_H with Ghat) on arrival; a declined query is discarded and the device's own answer stands. No extra round trip.
- EXCEPTION, QUESTION FIRST: only when an RC query's unsent history is large AND the device's uplink is contended by its own higher-value traffic, the device sends the question first; the cloud decides and pulls the missing frames only if it admits. This path adds a control round trip plus the cloud's decision latency.
- Delivered delay for queries is computed for the path actually used:

      complete query:   d = t_up(question + payload) + t_queue + t_compute + t_down
      question first:   d = t_up(question) + t_decide + RTT/2 (pull request) + t_up(missing frames) + t_queue + t_compute + t_down

  where t_decide is the coordinator's measured decision latency (M4).
- The device keeps answering locally in all cases; the cloud answer upgrades it if it arrives in time.

## A3. Monitoring path (D52)

A local filter on the device computes Ghat for each SH instant, plus (pending StudyCTRL1b) a cloud-initiated low-rate sampling whose cloud-side score gives a better observation of gain. The trigger family is an OPEN QUESTION (Q11). v3 section 7.7's self-normalized signals become inputs to Ghat.

## A4. Task-type posterior (D53)

P(type | observable) comes first from simple non-learned keyword and temporal-reference rules; the device model labelling the question is a fallback only if the rules prove too coarse on DEV.

## A5. Test

The predictability-ceiling arm of StudyCTRL1b measures how well Ghat can be estimated from observable features (a cross-fitted flexible model as the ceiling); a simple rule built from its strongest features is the deployable version.

## A6. Partial-prefix survival: deferring a piece carries the risk of losing what is already built (D55)

Problem. A reconstruction job's pieces are released separately (v3 7.4). Between pieces no request holds the already-built prefix, so its KV blocks are cached but unreferenced, and the engine frees them first under memory pressure. It cannot be pinned (D44). Deferring the next piece is therefore not only a delay: it risks having to restore (reload from host, if the offload connector caught the evicted blocks) or rebuild (if they were dropped) work already done. "When to run the next piece" and "will the built prefix still be there" are one coupled decision.

Changes to v3:

1. Expected remaining work under deferral (replaces the fixed w_r in v3 5.4 for the defer branch):

       E[w_r | defer for gap g] = w_left + P_loss(g) * [ P_host * w_reload(prefix) + (1 - P_host) * w_rebuild(prefix) ]

   - w_left: the job's unreleased pieces;
   - P_loss(g): probability the built prefix is evicted before the next piece runs, for a deferral of length g;
   - P_host: probability that evicted blocks are recoverable from the host tier (from the offload connector's behaviour, measured, M5);
   - w_reload, w_rebuild: restore costs from the step model (M1) and committed reload/rebuild profiles.
   Both the continuation value (v3 5.4) and the feasibility class (v3 7.3) use this expected remaining work.

2. The rollout tracks the KV POOL (extends v3 5.1): GPU KV occupancy, referenced vs unreferenced cached blocks, and the engine's free-block order (recency), driven by the predicted arrivals and released work over the gap. P_loss(g) is read from the rollout's predicted eviction of the prefix's blocks, not set by hand. Where the rollout does not reach the resume time (a long gap), P_loss is extended with the measured survival curve (M5).

3. In-progress prefixes in the memory decision (extends v3 6.3): the KV of an in-progress job's built prefix is an item whose value is its job continuation value at risk (the drop in ContValue_r if it is lost) plus its state value for future questions, counted once each (v3 5.3 single-counting rule). Under memory pressure this makes deferral expensive, so the coordinator tends to finish the job, choose larger pieces (fewer gaps), or defer only when the memory outlook is safe. Because residency cannot be commanded, protection acts only through scheduling choices (finishing sooner, sizing, not releasing competing KV-heavy work), never through an assumed pin.

4. Verify on resume (extends v3 6.5): before releasing the next piece, check the prefix's believed residency from telemetry (local vs external hits on its blocks where attributable). If part of the prefix is lost, re-plan the job with its true remaining work (restore then continue), and record the event (requested continuation vs observed loss) for reporting.

5. Piece sizing (v3 7.4) evaluates candidate sizes with this deferral risk included, so exposure between pieces is part of the size choice.

Reporting: prefix-loss events per job, their cost, predicted vs observed P_loss, and how often deferral was chosen under pressure.
