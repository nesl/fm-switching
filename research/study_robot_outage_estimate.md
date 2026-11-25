# Robot-only outage: read-only estimate (ESTIMATE ONLY, nothing built)

**Provenance.** Read-only survey on flash, A6000 session, 2026-11-24. Pinned to `origin/main` once; every
path below was confirmed to exist at that sha before being named. **No code was written and nothing on the
run path was touched.** The network experiment is the user's to choose after the Orin's idle-survival and
eviction-headroom results; this note only prices two pieces of work.

## Summary

| piece | hours | blocked by |
|---|---|---|
| A. Trace-level robot outage | **9 to 14** | nothing |
| B. Minimal policy-side outage awareness | **12 to 17** | A, strictly |
| **combined** | **21 to 31** | |

**The order is forced, not preferred.** The arm cannot be exercised until outages exist in the trace.
Building B first produces a mechanism that is reachable but never reached, which is how E36, E36b and E36c
produced nulls that were not findings, and how the `-notouch` proof 2 came back owed rather than passed.

## A. Trace-level robot outage: 9 to 14 h

**Files touched:** `experiments/orchestration/live2/fleet/trace.py` (1,076 lines; `generate_trace()` at
:376, `write_trace()` at :1022, `fairness_digest()` at :1000, `_digest_tuple()` at :974);
`fleet/emulator.py` (device-only question handling, near :266); `run_live2_real.py` (CLI passthrough); one
new proof script; and regenerated frozen trace directories under
`results/orchestration/live2/frozen_test/traces/`.

**Two parts are much cheaper than they look, because the machinery already exists.**

*The burst on reconnect is close to free.* `fleet/links.py:104` already implements `UplinkQueue` as a FIFO
that computes `t_arrive` from `max(offer_time, uplink_free_at)` and **records `queue_s` rather than hiding
it**. So the right change is to move a frame's OFFER time to the reconnect instant and let the existing
queue produce the burst. The queueing delay is then measured by committed code rather than by something
written for this experiment, and `fleet/links.py` may need no edit at all.

*Device-only questions already have a channel.* `device_answers` has 339 references, is generated at
`fleet/trace.py:966` and read at `fleet/emulator.py:266`, carrying `device_score` per instant. Marking a
question device-only reuses that path instead of inventing one.

**The identity proof is strong and cheap, about 1 h.** The frozen trace directories already carry
`SHA256SUMS` beside `trace.jsonl.gz` and `trace_meta.json`, so "no outages scheduled gives a byte-identical
trace" is a checksum comparison plus `fairness_digest()` returning the committed value. Per the standing
rule the new arguments default OFF, so the identity proof is also the default-path test.

**The dominant cost, about 5 to 8 h of the total, is the schedule plus regeneration:** a deterministic
staggered round-robin over robots derived from the existing seed, so that only one robot is offline at a
time, threaded through `write_trace` and `trace_meta`, then regenerating and checking in the variants.

## B. Minimal policy-side outage awareness: 12 to 17 h

*** THE SIGNAL THE DESIGN ASSUMES DOES NOT EXIST. *** `last_frame`, `last_seen`, `t_last`, `idle_s` and
`since_last` all return **zero hits** across `schema.py`, `arms_v6state.py` and `coordinator.py`, and
`heartbeat` returns **zero hits anywhere in live2**. So "no frames or heartbeats for that device" is not an
observable an arm can read today. It must be built and plumbed: the coordinator maintains per-device last
arrival, the schema carries it, the observation exposes it.

**That plumbing is the largest risk in either estimate, and not because it is hard.** It is the exact shape
of this project's canonical failure: a field that is set, counted and dispatched but never read.
`desired_tier` had three references, one declaration and two writes, and no read, while every surface sign
said the mechanism was live. **So the estimate includes naming the READ SITE that changes a decision, with
file and line, as a deliverable rather than an afterthought.** Call it 4 to 6 h including that proof.

The protection branch itself is small, 2 to 3 h: `arms_v6state.py` already has the per-session loop at :398
and emits `KEEP_GPU_WARM` at :478. Pre-warm on reconnect is 3 to 4 h, and needs its own
characteristic-decision count, because the port rule requires that the decision an arm exists to make
occurs at least once. **Proofs add 3 to 4 h:** switch read-back with types, the one-factor assertion
against the other `_d` flags, byte-identity on the other 20 `arms_*.py`, a Step 2b decision-log diff, and a
negative control in which the schedule off collapses to rung 3 exactly.

## THE THING TO SETTLE BEFORE EITHER ESTIMATE IS SPENT

*** The headline robot metric cannot show this effect, by construction. *** `robot_value.n_cloud_standing`
counts rows whose `source == "cloud"`, so it is **blind to device answers**. An outage that forces questions
device-only will depress that number for **every arm identically**, whatever the policy does. The metric
that can show a policy difference is **correct-by-deadline**, which admits the device fallback.

*** And correct-by-deadline has NO measured noise floor: n = 0 pairs. *** The reason is structural rather
than a missing experiment: `standing_accuracy_by_deadline` **does not exist as a key in any of the floor
study's eight stratum-A cells**, so no historical pair can supply it. **As things stand, the one metric this
experiment would turn on is the one metric that cannot be distinguished from noise.**

**Two same-code replicates in our own condition would fix that, at a few hours of accelerator time and no
code.** D238's block A supplies exactly this for the comparator at seeds 5, 6 and 7, so after tonight the
position may be materially better. **That is the cheaper thing to do first, and it is a precondition for
reading the outage experiment rather than an alternative to it.**

## What this estimate does not cover

- Any choice of network regime. That is the user's after the Orin's results.
- Outage parameters beyond the shape described (one robot offline at a time, D in {30, 60} s).
- Any multi-device or correlated outage, which was priced separately and earlier at 14 to 21 h minimal
  against an 8 h gate.
- The hours assume no concurrent run-path freeze. D238 forbids `experiments/` pushes until block A ends, so
  no part of A or B can land before then.
