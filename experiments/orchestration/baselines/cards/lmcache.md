<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# LMCache — case B

**Paper / system.** LMCache, a KV offload-and-reuse layer for LLM serving (system paper
arXiv:2510.09665).

**Code.** `https://github.com/LMCache/LMCache` (Apache-2.0), pinned `6d8376b1248c` (2026-11-12),
in `~/baselines_src/lmcache`.

**Original smoke test.** Not run: the package targets CUDA (`CMakeLists.txt`, `csrc/`) and its
light tests import `lmcache`, which pulls torch. Recorded in `results/orchestration/study_b_baselines/b_originals_smoke.json`.

**Files.** `lmcache_adapted.py`.

## What it decides

LMCache is a storage LAYER, not a scheduler: it stores KV for reusable text across GPU, host DRAM
and disk and serves a request from the highest tier that holds it. As a POLICY its decision is
therefore the storage one — admit a session's KV, place it in a tier, and **evict by LRU** when a
tier is full.

## Mapping, step by step

| LMCache | our code | note |
|---|---|---|
| GPU / CPU / disk tiers | GPU / host | ADAPTATION A1 |
| admission | every session that asks | FAITHFUL (LMCache caches by default) |
| LRU eviction | `LMCacheAdapted` keeps the `gpu_slots` most recently used | FAITHFUL |
| request order | the documented FCFS default | ADAPTATION A2 |

## Adaptations, with reasons

- **A1 no disk tier** in our interface.
- **A2 it decides nothing about ordering or placement of compute**, so everything outside
  `session_action` takes the documented defaults. This is deliberate: LMCache is in the suite as
  the **LRU contrast** to AttentionStore's scheduler-aware eviction and Pensieve's value-ordered
  one, so that the three state-management baselines differ only in their eviction rule.

## Not reproduced, and why

Its chunked KV format and CUDA kernels; cross-request prefix sharing beyond whole sessions; its
disk tier; its vLLM connector.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `gpu_slots` | 4 | StudyE10b's measured warm-session operating point, as in the AttentionStore card |
