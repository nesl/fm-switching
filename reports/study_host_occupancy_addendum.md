# Host-tier occupancy addendum (item 2 / D241): can an idle robot history be evicted from host?

CPU only, read-only on committed logs, no images. **D240: 1x and kv0.5r reported separately.** Two host channels are reported side by side because they disagree and the disagreement is the finding.

- ENGINE channel: host_counters_d211.log, the vLLM server's own automatic KV offload (vllm:kv_offload_store_bytes_total rate; vllm:kv_offload_cpu_cache_usage_perc occupancy).
- POLICY channel: coordinator_result.json memory_pressure, the TRUSTED channel. (arm_stats.pd_free_kv_* and cloud.gpu_kv_fraction are UNTRUSTED when metrics_health is never_scraped, so they are not used.)
- Host tier = 27 GiB = 110592 tokens = 28991029248 bytes, at 262144 B/token.

## Answers

1. **Does the 27 GiB host tier ever FILL under rung 3?** NO, at neither memory level. The engine occupancy peaks at 22.3 percent at 1x and 21.8 percent at kv0.5r over the full 1,200 s; the policy host_peak_tokens is 0 at 1x and about 25,963 (23 percent) at kv0.5r. It never approaches full in a 1,200 s cell.
2. **Can an idle robot history be EVICTED from host?** At **1x: effectively NO** - the policy offloads 0 and evicts 0, host_peak_tokens is 0, so there is nothing on the host tier to evict; an idle history stays resident (this is why the robot-idle survival shows P(cold) about 0.01). At **kv0.5r: lightly** - the policy evicts about 24 and host_peak_tokens is ~25,963, but the tier is far from full, so eviction is not capacity-driven and remains rare.
3. **Do engine store bytes count RE-STORES?** YES at both levels: cumulative store bytes exceed the host capacity by 3.84x (1x) and 3.83x (kv0.5r) while occupancy peaks near 22 percent, so the same blocks are stored repeatedly. The item-2 turnover (110,592 / rate) therefore measures engine store CHURN, not unique-history eviction, and must be read that way.
4. **Is the write rate steady or bursty?** BURSTY. At 1x rung3 s4 the per-60 s bin rate has mean ~324 and max ~710 tokens/s (max/mean 2.19); a lead-in sized to force a host-full state must cover the worst-case bin (~710 tok/s), not the 1,200 s mean (~343 tok/s from item 2).

**Consequence for the outage probe:** since the host tier never fills at 1x (nor kv0.5r) in 1,200 s and the policy evicts nothing at 1x, the probe's premise - evict from a full host, then measure HOST-warm vs cold recovery - is unreachable at 1x as designed. The mechanism cannot be exercised by waiting for the tier to fill; it needs rethinking rather than re-pricing. This is a model/log finding on committed data, no GPU time spent.

## A6000 cross-check: identical kv0.5r policy values

A6000 reported six kv0.5r cells with peak_tokens 32,470 and evicted 6 identically. Confirmed:

| cell | policy peak_tokens | policy evicted |
|---|---|---|
| covex-v6-fair-final_s4 | 32470 | 6 |
| covex-v6-fair-final_s5 | 32470 | 6 |
| covex-v6-fair-final_s6 | 32470 | 6 |
| covex-v6-fair-final_s7 | 32768 | 6 |
| llf_s4 | 33784 | 2 |

peak_tokens is identical (32,470) across covex-v6-fair-final s4, s5, s6 and evicted is identical (6) across s4 to s7. My ENGINE channel varies per cell (usage peak 22.3 vs 21.8 percent, distinct store bytes and burstiness per seed), so the per-cell host activity genuinely differs. That the POLICY peak_tokens and evicted are byte-identical across seeds where the engine channel varies supports A6000's read that these policy fields are short-circuited or trace-determined, not run-measured. My channel settles it independently: the real host activity is seed-dependent.

## 1x: per cell (engine and policy channels)

| arm | seed | agreement | engine rate tok/s | engine usage max | store/cap | bursty (max/mean) | policy host_peak_tok | policy offloaded | policy evicted | policy resident |
|---|---|---|---|---|---|---|---|---|---|---|
| covex-v6-fair-final | 4 | ABSENT | 342.577 | 0.2229 | 3.64 | True (2.19) | 0 | 0 | 0 | 22 |
| covex-v6-fair-final | 5 | ABSENT | 348.601 | 0.0723 | 3.49 | True (2.25) | 0 | 0 | 0 | 21 |
| covex-v6-fair-final | 6 | ABSENT | 407.346 | 0.0942 | 3.84 | False (1.89) | 0 | 0 | 0 | 22 |
| covex-v6-fair-final | 7 | ABSENT | 240.796 | 0.1432 | 2.88 | True (4.1) | 0 | 0 | 0 | 20 |

## kv0.5r: per cell (engine and policy channels)

| arm | seed | agreement | engine rate tok/s | engine usage max | store/cap | bursty (max/mean) | policy host_peak_tok | policy offloaded | policy evicted | policy resident |
|---|---|---|---|---|---|---|---|---|---|---|
| covex-v6-fair-final | 4 | ABSENT | 343.362 | 0.1554 | 3.62 | False (1.94) | 25963 | 0 | 6 | 22 |
| covex-v6-fair-final | 5 | ABSENT | 357.316 | 0.218 | 3.54 | True (2.43) | 18674 | 0 | 6 | 21 |
| covex-v6-fair-final | 6 | WARNING moved_after_import | 405.988 | 0.0741 | 3.83 | True (2.26) | 21625 | 0 | 6 | 22 |
| covex-v6-fair-final | 7 | OK | 240.554 | 0.1832 | 2.88 | True (3.05) | 24697 | 0 | 6 | 20 |
| llf | 4 | ABSENT | 4510.179 | 0.1481 | 48.09 | False (1.09) | 8311 | 0 | 2 | 250 |

Full data: results/orchestration/live2/robot_idle/host_occupancy_addendum.json
