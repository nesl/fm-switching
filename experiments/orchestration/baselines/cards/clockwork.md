<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Clockwork (OSDI 2020) — case B

**Paper.** A. Gujarati, R. Karimi, S. Alzayat, W. Hao, A. Kaufmann, Y. Vigfusson, J. Mace,
"Serving DNNs like Clockwork: Performance Predictability from the Bottom Up", *OSDI 2020*
(arXiv:2006.02464). Distinguished Artifact Award.

**Code.** `https://gitlab.mpi-sws.org/cld/ml/clockwork` (Apache-2.0, MPI-SWS), ~26k lines of C++.
Cloned to `~/baselines_src/clockwork`, pinned at `6ce83e029051` (2022-02-02).

**Original smoke test.** Attempted: `cmake` configure fails at `find_package(Boost)` — Boost is
not installed on this host, and the build additionally needs CUDA and TVM per its docs. The
paper's **emulated-worker** mode would permit a GPU-free run, but building the toolchain is
outside this task. Recorded in `results/orchestration/study_b_baselines/b_originals_smoke.json`.

**Files.** `clockwork_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| admission | §4.1, Fig. 2 | the controller sums the predicted time to **LOAD** the model weights and to **INFER**, and "concludes that the request will complete within its specified SLO"; a request that cannot is dropped ("The controller is aware that `r4` will miss its deadline"). |
| consolidating choice | §4.2 | "no worker operation should have implicit performance side-effects on any future operation" — predictability comes from removing hidden state. |
| actions | §5.2 | only **LOAD** and **INFER** are exposed; INPUT/OUTPUT are orders of magnitude cheaper. |
| strategies | §5.3 | a **strategy** is (model, `latest` timestamp, batch size). Each INFER executor has a strategy queue ordered by `latest`; the scheduler "dequeues strategies until it finds one that is valid: `latest` has not elapsed, and the batch queue for the specified batch size has sufficient requests", then speculatively grows the batch. |
| LOAD choice | §5.3 | the highest-priority model that is not already loaded. |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| predicted LOAD + INFER | `ClockworkAdapted._predicted_s` = `costs.recall_ttft_s(tokens, readiness)` + queue estimate | ADAPTATION A1 |
| admission test | `pred <= q.slack_s(now)` | FAITHFUL |
| drop on miss | `REJECT` (or `DEVICE`) | ADAPTATION A3 |
| strategy order by `latest` | `sorted(recall, key=deadline − predicted)` | FAITHFUL in effect |
| LOAD choice | `session_action` KEEP_GPU_WARM for the first `keep_warm_slots` | ADAPTATION A2 |
| batch size | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1 LOAD is a KV load, not a weight load.** Clockwork's loadable unit is a DNN's weights; ours
  is a session's KV cache, whose COLD / HOST-WARM / GPU-WARM costs StudyRH5 measured directly
  (0.382 / 0.459 / 2.445 s at 11k tokens). This is the same decision — "is the thing I need
  resident, and can I still make the deadline if it is not" — on a different resident object.
- **A2 one replica, so LOAD priority becomes warm-slot choice.** Clockwork picks which model to
  load across many workers; we pick which sessions to hold GPU-warm.
- **A3 drop vs fall back.** Clockwork drops. Our interface also offers DEVICE, which is strictly
  more useful and is the primary setting (`reject_instead_of_local=False`); the paper's drop is
  available with `reject_instead_of_local=True` and both are reported.
- **A4 batching is absent from our action space.** Our interface has no batch size, so §5.3's
  batch-size dimension and its speculative growth are dropped. **This removes a real part of
  Clockwork's throughput story**, and is the main thing a reviewer should know about this card.

## Not reproduced, and why

Batching and speculative batch growth (no batch dimension in our action space); the worker-side
determinism machinery of §4.2 and §5.1 (a C++ runtime change); cold-start weight management;
Clockwork's own latency predictor (we use our measured curves instead).

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| safety margin | 0.0 s | the paper admits on the predicted value; a margin would be our invention |
| `keep_warm_slots` | 0 by default | set by the harness; the paper's LOAD choice depends on cluster state we do not model |
| latency predictions | StudyRH5 / E10b curves | committed measurements, not fitted here |
