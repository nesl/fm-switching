# Cost ratio basis — canonical reference

**Date:** 2026-10-16
**Status:** reference table — **the canonical basis was ADOPTED 2026-10-16.** No committed headline is edited by this document: the switch is recorded as new registry rows (`StudyQ-median`, `StudyP-median`) and dated notes in the affected reports, with both bases labelled at every occurrence. Existing numbers stay as written.

Every latency cost ratio in the project is a ratio of two per-arm summary statistics, and the
project has been quoting two different summary statistics without saying which. StudyQ's 91× is
mean-of-means, StudyS1's 226× is median-of-medians, StudyP's 59× is mean-of-means. They are not
on the same basis and have been compared to each other as though they were — `reports/study_s1_competent_categories.md`
does so in one sentence, now annotated.

---

## Canonical basis: median-of-medians

The project adopts **median-of-medians** — the median of the numerator arm's per-trial latencies
divided by the median of the denominator arm's — as the canonical basis for every cost ratio.

**Rationale.** Thinking-arm latency distributions are long-tailed, and the tail is made of the
non-terminating traces: runs that hit the token cap and are analysed in their own right in
StudyJ2, StudyJ4 and StudyJ5 as a *termination* phenomenon. A mean cost ratio folds those same
traces into the *cost* number, so the project would be counting non-termination twice — once as
a termination rate and again as inflated latency. The median reports the cost of a typical
answered question, which is the quantity the bounded-path argument actually rests on.

The size of the problem is visible in the table: StudyS1's pooled ratio is 226× on medians and
452× on means. Same data, same arms, factor of two.

**This is a reporting convention, not a correction.** Both statistics are well-defined and
neither is wrong. Switching the committed headlines is a separate decision, to be taken from
this table.

---

## Every cost ratio in the project

`median` = median-of-medians · `mean` = mean-of-means. **Bold** marks the basis currently quoted
as that study's headline. A6000 rows are paired across backends; H100 rows are SDPA unless marked.

### StudyQ — ERQA, A6000 (`results/erqa/study_q/`)

| arms compared | backend | n | median | mean | headline quoted |
|---|---|---|---|---|---|
| A 4B-Thinking / D 8B-Instruct | SDPA | 400 / 400 | 46.7× | **89.5×** | **91×** (`study_q_retry_vs_scale_erqa.md`, registry, INDEX); **88×** (`study_q_fa2_backend.md`) |
| A 4B-Thinking / D 8B-Instruct | FA2 | 400 / 400 | 43.6× | **73.3×** | **72×** (`study_q_fa2_backend.md`) |
| A 4B-Thinking / E 4B-Instruct | SDPA | 400 / 400 | 70.7× | 138.3× | not quoted |
| A 4B-Thinking / E 4B-Instruct | FA2 | 400 / 400 | 66.5× | 114.0× | not quoted |
| C 8B-Thinking / D 8B-Instruct | SDPA | 400 / 400 | 53.9× | 106.5× | not quoted |
| C 8B-Thinking / D 8B-Instruct | FA2 | 400 / 400 | 56.5× | 100.5× | not quoted |

91× and 88× are the **same quantity** rounded differently (27.3/0.3 against 27.32/0.31); the
exact mean-of-means is 89.5×. They are not two measurements.

### StudyP — SiGNgapore2D, A6000 (`results/signs/study_p/`)

| arms compared | backend | n | median | mean | headline quoted |
|---|---|---|---|---|---|
| A 4B-Thinking / D 8B-Instruct | SDPA | 40 / 40 | 64.3× | **59.0×** | **59×** (`study_p_fa2_backend.md`) |
| A 4B-Thinking / D 8B-Instruct | FA2 | 40 / 40 | 50.0× | **42.0×** | **42×** (`study_p_fa2_backend.md`) |
| A 4B-Thinking / C 8B-Thinking | SDPA | 40 / 40 | 1.66× | **1.21×** | **1.21×** (registry StudyP row, labelled "mean") |
| A 4B-Thinking / C 8B-Thinking | FA2 | 40 / 40 | 1.11× | 0.97× | not quoted |

StudyP is the one family where the median ratio is **larger** than the mean, because arm D's
mean is pulled up by a few slow instruct trials while arm A's is not. The direction of the
mean/median gap is not constant across studies, so it cannot be corrected for by a blanket factor.

### StudyS1 — MV-RoboBench competent stratum, A6000 (`results/mvrobobench/study_s1/`)

| arms compared | backend | n | median | mean | headline quoted |
|---|---|---|---|---|---|
| T 4B-Thinking / I 4B-Instruct, POOLED | SDPA | 401 | **226.3×** | 451.9× | **226×** (`study_s1_competent_categories.md`, `a6000_night_summary.md`) |
| T / I, POOLED | FA2 | 401 | **201.8×** | 364.9× | **202×** (`study_s1_fa2_backend.md`) |
| T / I, robotic_trajectory_selection | SDPA | 200 | **143.6×** | 246.5× | **144×** |
| T / I, robotic_trajectory_selection | FA2 | 200 | **119.7×** | 203.2× | **120×** |
| T / I, spatial_distance_judgement | SDPA | 201 | **371.8×** | 648.9× | **372×** |
| T / I, spatial_distance_judgement | FA2 | 201 | **357.0×** | 520.9× | **357×** |

StudyS1 is already on the canonical basis throughout.

### H100 night summary — bases checked here for the first time

`reports/h100_night_summary.md` §"Latency cost of thinking at 32B" quotes three figures whose
basis had not been checked. **All three are median-of-medians** — the H100 family is already on
the canonical basis.

| source | arms compared | n | median | mean | headline quoted |
|---|---|---|---|---|---|
| StudyR, ERQA | D 32B-Thinking / A_h100 4B-Instruct (same hardware) | 400 / 400 | **198.8×** | 328.4× | **"≈190–200×"** — median; `study_r_device_vs_cloud.md` states "188× spatial, 200× overall" |
| StudyR, ERQA | D 32B-Thinking / A 4B-Instruct (reused, A6000) | 400 / 400 | **92.9×** | 163.0× | **"87× / 93×"** cross-hardware, labelled as such |
| StudyS2, MV-RoboBench | D 32B-Thinking / C 32B-Instruct | 401 / 401 | **91.6×** | 153.2× | **92×** |
| StudyT, signs | T32 @ budget 8192 / I32 | 40 / 40 | **76.1×** | 58.4× | quoted as medians **"210 s vs 2.8 s"**, ratio left implicit |

StudyT's figures reproduce exactly: T32 median 209.9 s, I32 median 2.76 s. Its mean ratio (58.4×)
is again *smaller* than its median ratio, as in StudyP.

StudyR's cross-hardware D/A row (92.9×) and StudyS2's D/C row (91.6×) are numerically almost
identical and measure entirely different things — one is 32B-vs-4B across two GPUs, the other is
thinking-vs-instruct at fixed size on one. They should not be cited near each other without the
distinction.

---

## What switching the headlines would mean

Recorded so the decision can be made from one place. Nothing below is applied.

| study | current headline | canonical (median) equivalent |
|---|---|---|
| StudyQ ERQA | 91× / 88× (SDPA), 72× (FA2) | 46.7× / 43.6× |
| StudyP signs | 59× (SDPA), 42× (FA2) | 64.3× / 50.0× |
| StudyP registry 4B-vs-8B | 1.21× | 1.66× |
| StudyS1 | 226× / 202× | unchanged — already canonical |
| H100 StudyR, StudyS2, StudyT | 198.8× / 91.6× / 76.1× | unchanged — already canonical |

Only StudyQ and StudyP would move. StudyQ's move is large (roughly halving) and would change the
stated size of the bounded-path advantage on ERQA, though not its direction or any verdict: 46.7×
and 89.5× both support "the instruct path is cheaper by one to two orders of magnitude at
indistinguishable accuracy". Per the registry rule, a switch should be a new row rather than an
edit to a committed verdict.
