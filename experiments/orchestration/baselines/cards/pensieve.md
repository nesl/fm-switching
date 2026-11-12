<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Pensieve (EuroSys 2025) — case D

**Paper.** L. Yu, J. Lin, J. Li, "Stateful Large Language Model Serving with Pensieve",
*EuroSys 2025* (arXiv:2312.05516).

**Code.** None found. **Case D.**

**Files.** `reconstructed/pensieve.py`, `reconstructed/test_pensieve_toy.py`,
`pensieve_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| multi-tier cache | §1, §4 | a GPU-CPU two-tier cache holding conversation history, swapped as capacity requires. |
| eviction value | §4 | eviction is at the granularity of **a chunk of tokens**, and a chunk is kept when it is "attractive for longer and/or ... cheaper to recompute" — so DROP what is cheap to recompute. |
| token granularity | §4 | "we decide to swap at the granularity of individual tokens", so a session may be PARTIALLY resident and the missing segment is recomputed. |
| ahead-of-time swapping | §4 | pipelined transfer overlapping computation. |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| chunk value ordering | `chunk_value = reuse_horizon × recompute_cost` | FAITHFUL to the paper's stated preference |
| evict until the tier fits | `evict_to_fit` | FAITHFUL |
| ahead-of-time pipelined swap | `aot_swap_s` | FAITHFUL |
| partial residency cost | `serve_cost_s` = pipelined transfer of the CPU part + full recompute of the dropped part | FAITHFUL |
| recompute rate | StudyRH5's measured cold prefill rate for that size (4,500 / 3,800 tok/s) | ADAPTATION A2 |
| chunk granularity | one chunk per session | ADAPTATION A1 |

## Adaptations, with reasons

- **A1 whole-session granularity.** Pensieve's point is sub-session granularity; our
  `session_action` is whole-session, so a partial residency is expressed as
  `OFFLOAD_TO_HOST` for the whole session and the chunk-value ordering decides WHICH sessions go
  first. **The reconstruction keeps token/chunk granularity and the toy test exercises it; the
  policy cannot.** This is the main limitation of this card.
- **A2 recompute cost is measured.** "Cheaper to recompute" needs a rate; StudyRH5 measured it
  for exactly the D2 sizes we use.
- **A3 the reuse horizon is a parameter, not a prediction.** The paper's "attractive for longer"
  implies a reuse estimate; we expose one constant (`reuse_horizon_s`, 30 s) rather than predict
  it, because predicting reuse from our observation would be a new policy, not Pensieve's.
  FLAGGED.

## Not reproduced, and why

The attention-kernel change that lets Pensieve attend over a non-contiguous KV layout (a CUDA
change); the pipelining implementation; its vLLM block-manager integration; its throughput
results.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `gpu_capacity_tokens` | 60,000 | StudyRH5's measured GPU KV capacity (62,944 tokens at bf16), rounded down |
| `reuse_horizon_s` | 30 s | our own constant; see A3 |
| recompute rates | 4,500 / 3,800 tok/s | StudyRH5 Part A |
