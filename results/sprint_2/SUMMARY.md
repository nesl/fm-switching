# LH-variants verification — summary for the advisor deck

**Data source:** `simulator/results/comparison_lh_variants.json`, 312 rows = 13 policies × **24 cells** (3 workloads × 8 networks). (The prompt said 18; the actual data has 24. All centroids below are means across those 24 cells.)

## Headline answer

**The "four LH variants form a Pareto frontier" framing does not survive verification at full strength.** Two specific findings force a softening:

### Finding 1 — Speculative vs RoutedSync parity is a *tautology of the routing rule*, not a policy comparison.

Across all 24 cells, **SpeculativeLH and RoutedSyncLH return byte-exact identical latency and quality** (every `latency_delta = 0.000`, `quality_delta = 0.000` — see `quality_parity.csv`).

This is because the routing rule in `routed_sync_lh_policy.py:48` is:

```python
route_cloud = connected and (cloud_ms < edge_ms)
```

using the **ground-truth instantaneous network state** (`rtt_ms` from the trace), not an SSM forecast and not a learned estimator. So RoutedSync chooses the same tier that Speculative's post-hoc `min(edge, cloud)` would have selected, by construction. The "no information needed" claim for Speculative collapses: RoutedSync uses identical information (current connectivity + current RTT) to make the same choice without paying the loser's compute.

**Honest framing:** "A trivial threshold rule on instantaneous-RTT-aware expected cost recovers Speculative's latency at half the compute" — strong on the engineering side; weak as an SSM-driven-orchestration story. **The SSM-routing case must be re-run with the SSM forecast plumbed into the routing rule** before this can be claimed as the headline of the orchestrator thesis. Right now SSM is unused at routing time.

### Finding 2 — None of the four LH variants is in the per-network top-2 on any of the 8 networks. (`network_pareto_top2.csv`)

The per-network frontier is dominated by **Oracle, ProactiveMPC, ReactiveThreshold, SSM+MPC, and OverlapMigration**. SpeculativeLH, RoutedSyncLH, and HotStandbyLH never appear in any cell's top-2. The Pareto-frontier story from the last session held only at full-quality (q=1.0); once we admit quality-trading policies (Reactive at q=0.77, MPC family at q=0.94), they dominate on every network.

So the four-point latency-vs-compute Pareto plot is a within-LH-family-at-q=1.0 plot, not a global one.

## What the data DOES say cleanly

- **OverlapMigration is the cost-effective LH variant** when the user accepts the quality drop: centroid lat=10.87s, tok/cyc=2470, q=0.90. The quality hit (Section 5) is a binary OOM→stateless fallback in the simulator (`orchestrator_sim.py:178-186`), not a policy bug — it's how the edge tier handles KV pressure under any policy that lets it grow.
- **HotStandbyLH is dominated by RoutedSyncLH for a structural reason** (sticky promotion, not just bad networks). `network_breakdown_hotstandby.csv` shows HS = RS exactly on the 4 networks with effectively-zero disconnect (stable / degrading / urban / markov_campus). On the other 4, HS spends an estimated **~98% of cycles on edge-primary** post-failover (Section 4b, markov_urban: f_cloud ≈ 0.019). The cloud replica is RAM-resident the entire time but contributes zero to user-facing latency.
- **SpeculativeLH wastes exactly 50% of its compute, constant across all 24 cells** (413,100 tokens/cell = one tier's full prefill+decode per cycle × 100 cycles). RoutedSync wastes 0 by design. HS wastes only on failover cycles (0–2,731 tokens/cell). OM wastes only on warm-abort cycles (0–2,641 tokens/cell). Numbers and code citations in `hotstandby_diagnosis.md`.
- **Memory math checks out.** Peak `17,505 MB` = edge_VLM (7,163) + edge_LLM (3,264) + edge_KV at ~8,081 tokens (1,907) + cloud_LLM_weights (3,264) + cloud_KV (1,907). The user-suggested 12,334 + 7,163 = 19,497 double-counts the VLM (AlwaysEdge peak includes it; AlwaysCloud peak is VLM-only). **The 17,505 MB is correct, not an off-by-one.** Section 8 confirmed.
- **OverlapMigration's quality drop is mechanistically explainable.** It is the simulator's edge-OOM fallback into `stateless` mode (quality 0.70), triggered when `mem > memory_cap_mb`. OverlapMigration triggers it more than reactive because it doesn't migrate to cloud as eagerly as AlwaysCloud, so edge KV keeps growing until the cap. `overlap_quality_drop.txt` has the per-cell breakdown and code line references.

## Strongest single headline for the advisor pitch

Given the verification, the strongest defensible headline is **not** "we built a Pareto frontier of LH variants." It is:

> **"Under correlated network dynamics (Markov-modeled WiFi), instantaneous tier-cost routing with continuous KV sync (RoutedSyncLH) eliminates the cloud-migration tail latency that hurts AlwaysCloud (12.1s vs 11.9s mean, no migrations vs 4.5 migrations/episode), with no quality loss and only ~1.6% additional compute cost from edge-replica sync."**

This is true, defensible from `centroid_table.csv`, and avoids both (a) the Speculative-tautology trap and (b) the per-network-top-2 trap. The SSM angle on top of this — "if we replace instantaneous RTT with an SSM forecast, can routing get ahead of state transitions instead of reacting one tick late" — becomes the *next* experiment to run, not a claim from this data.

## Where the data forces softening

1. Drop "SpeculativeLH and RoutedSyncLH demonstrate the no-info vs info trade-off." They use identical information.
2. Drop "the LH variants form the Pareto frontier" as a global claim. They don't — they form a within-quality-1.0 sub-frontier.
3. Soften "HotStandby is dominated on bad networks" to "HotStandby with sticky promotion is dominated on bad networks; non-sticky HotStandby has not been measured."
4. The OverlapMigration q=0.90 number should NOT be cited without the mechanistic explanation, or it reads as "LH degrades quality" when it's actually "edge KV OOM forces stateless fallback regardless of LH."

## Files in this directory

| file | section |
|---|---|
| `centroid_table.csv` | 1 |
| `quality_parity.csv` | 2 |
| `network_breakdown_hotstandby.csv` | 4a |
| `network_pareto_top2.csv` | 7 |
| `compute_seconds_decomposition.txt` | 9 |
| `overlap_quality_drop.txt` | 5 |
| `hotstandby_diagnosis.md` | 4b + 6 |
| `SUMMARY.md` | this |
