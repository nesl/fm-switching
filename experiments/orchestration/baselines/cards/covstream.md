<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# CoVStream (arXiv:2606.22804) — case D, conditional P1

**Paper.** X. Liu, G. Chen, Z. Yan, K. Wu, W. Wang, "CoVStream: Edge-Cloud Collaboration for
Understanding of Long Video Streams", arXiv:2606.22804. **Verified (arXiv abstract page).**

**Code.** None found. **Case D.**

**Files.** `reconstructed/covstream.py`, `reconstructed/test_covstream_toy.py`,
`covstream_adapted.py`. **Experiment:** B-recall.

## WHY THIS IS NOW BUILT, HAVING BEEN REFUSED ONCE

The first pass of this suite listed CoVStream as **related work only**, on the grounds that its
edge tier produces captions and its cloud tier maintains an entity graph, and our evidence
inventory holds only representations we have measured — so expressing it would mean inventing an
uncosted representation. The addendum promotes it to conditional P1 **and requires that its
representation-construction compute be charged**, which is exactly what was unfair before: its
87.6 % bandwidth saving is paid for by *continuous* edge captioning and *continuous* cloud graph
maintenance, and a baseline that ignored those costs would violate fairness rule 3. With the cost
charged the baseline is comparable, and the remaining substitution is stated plainly below.

## The paper's algorithm

"The edge node converts raw streams into compact visual features and semantic captions. The cloud
server organizes this data into an entity graph and global visual context, and runs the heavy
reasoning model **only when a user query arrives**." Reported: 87.6 % bandwidth reduction while
retaining 99.2 % of the cloud baseline's accuracy on LVBench.

## Mapping

| paper | our code | note |
|---|---|---|
| edge features + captions | representation `D2` (a strided history) | **ADAPTATION A1 — the largest substitution in this suite** |
| cloud entity graph + global context | the session's GPU/host-warm D2 state, maintained continuously | ADAPTATION A2 |
| heavy model on query only, nothing uploaded then | serve from the warm state | FAITHFUL |
| bandwidth accounting | `bandwidth_ratio` against raw-frame upload | FAITHFUL |
| construction compute | **CHARGED** per frame (edge) and per packet (cloud) via `_charge_construction`, visible in the smoke results | FAITHFUL to fairness rule 3 |

## Adaptations, with reasons

- **A1 we do not caption and we do not build an entity graph.** Nothing in this project has ever
  measured either, so D2 — the nearest measured representation — stands in for both. **This
  baseline is therefore "CoVStream's edge-cloud SPLIT with our representations", not CoVStream**,
  and no accuracy number from the paper transfers.
- **A2 the graph becomes warm KV.** Our cloud's maintained structure is the session's KV state,
  which StudyRH5 costed.
- **A3 the construction costs are declared constants** (0.01 s per frame at the edge, 0.002 s per
  packet in the cloud), not measurements. They are the one place this card asks the reader to
  accept a number we did not measure, and they are deliberately conservative — a cheaper
  construction would only flatter this baseline.

## Not reproduced, and why

The captioner; the entity-graph builder; retrieval over the graph; the paper's LVBench numbers.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `edge_cost_s_per_frame` | 0.01 s | declared, not measured (A3) |
| `graph_cost_s_per_packet` | 0.002 s | declared, not measured (A3) |
| feature / caption bytes | 4,000 / 400 B | declared, not measured (A3) |
