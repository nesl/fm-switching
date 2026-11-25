#!/usr/bin/env python3
"""Render reports/study_host_occupancy_addendum.md from host_occupancy_addendum.json. No plots."""
import json
from pathlib import Path
REPO = Path("/home/nesl/fm-switching")
J = json.load(open(REPO / "results/orchestration/live2/robot_idle/host_occupancy_addendum.json"))
PC, CO = J["per_cell"], J["conclusions"]
L = []
A = L.append
A("# Host-tier occupancy addendum (item 2 / D241): can an idle robot history be evicted from host?")
A("")
A("CPU only, read-only on committed logs, no images. **D240: 1x and kv0.5r reported separately.** "
  "Two host channels are reported side by side because they disagree and the disagreement is the "
  "finding.")
A("")
A("- ENGINE channel: host_counters_d211.log, the vLLM server's own automatic KV offload "
  "(vllm:kv_offload_store_bytes_total rate; vllm:kv_offload_cpu_cache_usage_perc occupancy).")
A("- POLICY channel: coordinator_result.json memory_pressure, the TRUSTED channel. "
  "(arm_stats.pd_free_kv_* and cloud.gpu_kv_fraction are UNTRUSTED when metrics_health is "
  "never_scraped, so they are not used.)")
A(f"- Host tier = 27 GiB = {J['constants']['host_capacity_tokens']} tokens = "
  f"{J['constants']['host_capacity_bytes']} bytes, at {J['constants']['bytes_per_token']} B/token.")
A("")
A("## Answers")
A("")
A("1. **Does the 27 GiB host tier ever FILL under rung 3?** NO, at neither memory level. The engine "
  f"occupancy peaks at {CO['1x']['engine_max_usage_perc']*100:.1f} percent at 1x and "
  f"{CO['kv0.5r']['engine_max_usage_perc']*100:.1f} percent at kv0.5r over the full 1,200 s; the "
  "policy host_peak_tokens is 0 at 1x and about 25,963 (23 percent) at kv0.5r. It never approaches "
  "full in a 1,200 s cell.")
A("2. **Can an idle robot history be EVICTED from host?** At **1x: effectively NO** - the policy "
  "offloads 0 and evicts 0, host_peak_tokens is 0, so there is nothing on the host tier to evict; "
  "an idle history stays resident (this is why the robot-idle survival shows P(cold) about 0.01). "
  "At **kv0.5r: lightly** - the policy evicts about 24 and host_peak_tokens is ~25,963, but the "
  "tier is far from full, so eviction is not capacity-driven and remains rare.")
A("3. **Do engine store bytes count RE-STORES?** YES at both levels: cumulative store bytes exceed "
  f"the host capacity by {CO['1x']['engine_max_store_over_capacity']}x (1x) and "
  f"{CO['kv0.5r']['engine_max_store_over_capacity']}x (kv0.5r) while occupancy peaks near 22 "
  "percent, so the same blocks are stored repeatedly. The item-2 turnover (110,592 / rate) therefore "
  "measures engine store CHURN, not unique-history eviction, and must be read that way.")
A("4. **Is the write rate steady or bursty?** BURSTY. At 1x rung3 s4 the per-60 s bin rate has "
  "mean ~324 and max ~710 tokens/s (max/mean 2.19); a lead-in sized to force a host-full state must "
  "cover the worst-case bin (~710 tok/s), not the 1,200 s mean (~343 tok/s from item 2).")
A("")
A("**Consequence for the outage probe:** since the host tier never fills at 1x (nor kv0.5r) in "
  "1,200 s and the policy evicts nothing at 1x, the probe's premise - evict from a full host, then "
  "measure HOST-warm vs cold recovery - is unreachable at 1x as designed. The mechanism cannot be "
  "exercised by waiting for the tier to fill; it needs rethinking rather than re-pricing. This is a "
  "model/log finding on committed data, no GPU time spent.")
A("")
A("## A6000 cross-check: identical kv0.5r policy values")
A("")
A("A6000 reported six kv0.5r cells with peak_tokens 32,470 and evicted 6 identically. Confirmed:")
A("")
A("| cell | policy peak_tokens | policy evicted |")
A("|---|---|---|")
for k in sorted(J["a6000_crosscheck_kv0.5r"]["policy_peak_tokens"]):
    A(f"| {k} | {J['a6000_crosscheck_kv0.5r']['policy_peak_tokens'][k]} | "
      f"{J['a6000_crosscheck_kv0.5r']['policy_evicted'][k]} |")
A("")
A("peak_tokens is identical (32,470) across covex-v6-fair-final s4, s5, s6 and evicted is identical "
  "(6) across s4 to s7. My ENGINE channel varies per cell (usage peak 22.3 vs 21.8 percent, distinct "
  "store bytes and burstiness per seed), so the per-cell host activity genuinely differs. That the "
  "POLICY peak_tokens and evicted are byte-identical across seeds where the engine channel varies "
  "supports A6000's read that these policy fields are short-circuited or trace-determined, not "
  "run-measured. My channel settles it independently: the real host activity is seed-dependent.")
A("")
for mem in ("1x", "kv0.5r"):
    A(f"## {mem}: per cell (engine and policy channels)")
    A("")
    A("| arm | seed | agreement | engine rate tok/s | engine usage max | store/cap | bursty (max/mean) "
      "| policy host_peak_tok | policy offloaded | policy evicted | policy resident |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in sorted(PC[mem]):
        r = PC[mem][k]
        b = r["engine_burstiness"] or {}
        A(f"| {r['arm']} | {r['seed']} | {r['agreement']} | {r['engine_store_rate_tokens_s']} | "
          f"{r['engine_usage_perc_max']} | {r['engine_store_max_over_capacity']} | "
          f"{b.get('bursty')} ({b.get('max_over_mean')}) | {r['policy_host_peak_tokens']} | "
          f"{r['policy_offloaded']} | {r['policy_evicted']} | {r['policy_resident']} |")
    A("")
A("Full data: results/orchestration/live2/robot_idle/host_occupancy_addendum.json")
(REPO / "reports/study_host_occupancy_addendum.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_host_occupancy_addendum.md")
