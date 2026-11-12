<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Ekya (NSDI 2022) — case B

**Paper.** R. Bhardwaj, Z. Xia, G. Ananthanarayanan, J. Jiang, Y. Shu, N. Karianakis, K. Hsieh,
P. Bahl, I. Stoica, "Ekya: Continuous Learning of Video Analytics Models on Edge Compute
Servers", *NSDI 2022*.

**Code.** `https://github.com/edge-video-services/ekya` — Microsoft Research's own release
("Download the code"), so author-endorsed. Cloned to `~/baselines_src/ekya`, pinned at
`2a6c8201db95` (2022-03-10).

> **LICENSE FLAG.** The repository contains **no LICENSE or COPYING file anywhere**, and the
> README names no license, so no right to use or modify is granted. Consequences, applied:
> the clone is used for **citation and commit pinning only**; **no file in it was opened, run or
> copied**; its own CPU-runnable toy example (`simulator/tiny_sim.ipynb`, numpy + matplotlib
> only) was deliberately **left unrun**; and `ekya_adapted.py` was written from the **paper**.
> This is surfaced for the user rather than resolved silently.

**Files.** `ekya_adapted.py`. No reconstruction file: case B keeps the original, and the adapted
version is the deliverable.

## The paper's algorithm

Ekya shares one edge GPU between **inference** jobs (which must keep up with live streams) and
**retraining** jobs (which restore accuracy after data drift). Its **thief scheduler** starts
from a fair share and then iteratively *steals* a resource increment from one job and gives it to
another, keeping the reallocation only when a **micro-profiled** estimate says total accuracy
improves. Micro-profiling trains candidate configurations on a small data sample for a few epochs
to extrapolate the accuracy a full retraining would reach.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| inference jobs | episodic streams | ADAPTATION A1 |
| retraining jobs | recall warm maintenance and cold recall prefills | ADAPTATION A2 |
| fair-share initialisation | `share = total / (n_streams + 1)` | FAITHFUL in structure |
| thief loop (steal Δ, keep only if the score improves) | the `for victim ... for thief ...` loop in `EkyaAdapted.decide` | FAITHFUL in structure |
| micro-profiled accuracy estimate | `_stream_gain` (StudyE9b AP) and `_recall_gain` (StudyRH5 service times) | ADAPTATION A3 |
| total-accuracy objective | `score()` | ADAPTATION A4 |

## Adaptations, with reasons

- **A1/A2 job classes.** Ekya's two classes are "must keep up now" and "background work that pays
  off later". Ours are the same shape: episodic streams need cloud share now; recall warm
  maintenance and cold prefills are the background work competing for the same GPU.
- **A3 micro-profiles are replaced by measured curves.** Micro-profiling retrains a model, which
  needs a GPU. We substitute committed measurements. **Consequence: the part of Ekya that
  estimates the value of background work by sampling is not exercised** — the estimate is exact
  instead of sampled, which makes the thief scheduler's job easier than in the paper.
- **A4 the objective adds a background term.** Ekya maximises total accuracy over jobs. Recall
  "accuracy" and stream AP are not on one scale, so the background pool's contribution enters at
  weight 0 in `score()` and the background share is spent greedily by deadline afterwards. This
  is a deliberate, visible choice: weighting them would be inventing an exchange rate we have not
  measured. **Flagged as the weakest point of this adaptation.**
- **A5 the original is not called.** The release runs on Ray with NVIDIA MPS on a GPU; a CPU-only
  replay cannot call it. Combined with the licence flag, the adapted logic is written from the
  paper.

## Not reproduced, and why

Micro-profiling itself; the retraining-configuration search space (model architecture, number of
epochs, data subsampling); Ray/MPS execution; the accuracy-over-time integral Ekya optimises.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| thief iterations | 20 | our choice; the paper describes the loop as running to convergence, so this is a cap, stated |
| Δ (steal size) | `total / (pools × 20)` | derived from the iteration cap, not from the paper |
| horizon | 10 s | our scheduling epoch scale |
