# D253's PRESSURE-PILOT PASS RULE: the three conditions DEFINED BEFORE ANY CELL IS SCORED

**Written 2026-11-25 while the P1 n20 cell was still running and before any of its figures were read.**
**These are flash's definitional calls, flagged as such, and the user may override any of them. The
reporting below is built so that an override needs NO re-run.**

## D253's rule, verbatim

> "Pass rule (workload really contests memory): host tier at capacity at least once, rung-3 idle robot
> P(cold) > 0.10 at 30-60 s gaps, evictions > 0. First passing direction becomes the regime for the touches
> and outage experiments, with baselines queued in it."

**All three must hold. P1 is therefore a DIAGNOSTIC, not an attainment comparison: it asks whether 20 or 24
devices put the memory system under real pressure.**

## (1) HOST TIER AT CAPACITY: the SERVER reading governs; both are reported

| reading | source | "at capacity" |
|---|---|---|
| **SERVER (governs)** | `vllm:kv_offload_cpu_cache_usage_perc` in `host_counters_d211.log`, sampled about every 10 s | the fraction reaching about **1.0** |
| PLANNER (reported beside) | `coordinator_result` `memory_pressure.pressure.host_peak_tokens`, `host_epochs_over_cap`, against header `host_tier_tokens` 110,630 | peak approaching the header value |

**Why the server reading: D253 asks whether the WORKLOAD contests memory, not whether the policy noticed.
The policy's noticing is a separate question and a known defect.**
*** AND THE DISCREPANCY IS ITSELF A RESULT, TO BE REPORTED WHATEVER THE CONDITION DOES: at 1x the planner
places NOTHING on the host tier (`host_peak_tokens` 0, `host_epochs_over_cap` 0, `evicted` 0 in the
committed 1x n16 `_rep2` reference) while the SERVER peaked at 0.221 over that run. If the server tier
fills while the planner still reads zero, the pressure exists and is INVISIBLE TO THE POLICY, which is
D211's unobservability result recurring in a new place. ***
**Register caution recorded in advance: an in-progress cell's partial peak is not comparable to a completed
run's peak. The n20 cell read 0.121 at about 14 of 20 minutes against n16's 0.221 over a full run; nothing
is read from that pair until n20 completes.**

## (2) IDLE-ROBOT P(cold): both halves declared

**(i) IDLE GAP = time since that robot's PREVIOUS QUESTION**, not since its previous request of any kind.
*** The alternative is vacuous: in per-frame mode a robot uploads a frame every 2 s, so measured by uploads
NO robot is ever idle for 30 s and the condition could never fire. A condition that cannot fire is not a
condition. *** **And the decision-relevant gap is exactly "this robot is not asking; do I keep its history
warm".**
**(ii) COLD = `cached_fraction` below 0.5**, measured on the question's prompt as the engine reports it.
**Declared at 0.5 BEFORE any number was seen.**
*** AND THE FULL DISTRIBUTION IS REPORTED BESIDE IT - deciles of `cached_fraction` over the idle-gap
questions, with n - SO THE THRESHOLD CAN BE MOVED LATER WITHOUT A RE-RUN AND WITHOUT ANYONE CHOOSING IT
AFTER SEEING THE ANSWER. *** **If 0.5 falls inside a cluster of points, that is to be said plainly: a
threshold inside a mass is a bad threshold.**
**Inputs, all present in `request.jsonl`: `device_id`, `t_submit`, `cached_fraction`, `cached_tokens`,
`prompt_tokens`, `opportunity_id`.**

## (3) EVICTIONS: planner-side governs; server-side is ABSENT, not substituted

**`memory_pressure.enact_placement_totals.evicted` is the condition** (0 in the committed 1x n16
reference). It is the quantity the policy acts on, and it is what D242's own option assessment used.
*** THE SERVER HAS NO EVICTION COUNTER. The `kv_offload_*` namespace carries usage, `load_bytes_total`,
`store_bytes_total` and time only - flow and occupancy, never events. The same namespace was checked for a
CAPACITY field when D250 came up and had none. So server-side evictions are reported as NOT RECORDABLE
from what a cell writes, and NO PROXY IS SUBSTITUTED. ***

## Why these were declared now

**D253's rule was relayed to the accelerator box WITHOUT its pass rule: the cell spec went out and the
three conditions did not, so the box was told "P2 runs only if P1 fails the rule" while never being told
what the rule was. That omission was flash's.** **It was found by reading the planner's full design log,
which runs to D256 while the repository copy had stopped at D236; the repository copy is now synced.**
**The box asked for all three definitions before computing any of them, which is why they are on record
here rather than inferred from a number.**
