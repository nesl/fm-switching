# StudyRES1-residency: can the scheduler's own bookkeeping predict where each history is?

Design decision D56. Pre-registered in `research/EXPERIMENTS.md` (row StudyRES1-residency, 2026-11-17, before any
prediction was scored; the 13-field row was frozen to a timestamped scratchpad at **2026-11-17T16:59:11Z**, md5
**`91f3c3fe2c72fb089e9fcb1aac43cbbd`**). Scripts: `experiments/orchestration/policy/residency.py`,
`experiments/orchestration/run_res1.py`. Results: `results/orchestration/study_res1/`. Scoring host: flash, CPU
only, no GPU. Every measurement read here was taken on h100nvl GPU 2 by StudyENG1c-hostfull and is only READ.

## 0. Pre-declaration, written before the TEST set was scored

**The question.** StudyT0b scored the delay model with the tier at arrival GIVEN. This study asks the question
that was excluded there: from the request stream alone, under bounded GPU and host capacity, can a scheduler's own
bookkeeping say where each device history is? The predictor implements StudyENG1c Part A's identified rule and
reads no measured cache-hit, load or compute counter.

**Criteria, exactly as frozen (unchanged by anything below).**

- **R1:** 4-class tier accuracy on TEST at least **0.90 pooled** and at least **0.85 in every cap**.
- **R2:** the rule beats **every** comparison predictor on TEST accuracy, with a paired bootstrap CI (resampling
  requests by TRIAL, 10,000 draws, 95 % percentile) excluding 0.
- **R3:** for PARTIAL cases, **MAE of the predicted fraction on host at most 0.10**.

**Scope, as frozen.** R1, R2 and R3 are scored on the TEST requests whose 4-class tier is MEASURED. vLLM reports
`local_cache_hit` and `external_kv_transfer` per run window, and a window isolates one request only where one
request could have loaded from host, so the GPU-versus-HOST split on a fully warm request is measurable only
there. COLD and PARTIAL are measurable from the request's own `cached_tokens` against its history length.

**Three secondary analyses, pre-declared on the user's instruction of 2026-11-17 and before scoring. They change
no criterion and no threshold.**

1. **The 2-class (warm versus cold) secondary is reported twice:** once over all TEST reuse requests, and once over
   the same set MINUS the Part B piece-chain requests (pieces 2 to 5), which are warm by construction, so any
   predictor that says warm is right about them for free.
2. **Selection check.** The measured subset is drawn mostly from isolated, low-concurrency windows, while the
   unmeasured warm requests concentrate in Part C at concurrency 4 and 8 and in Part D churn. Per part and per
   concurrency level, the PREDICTED tier distribution under the rule is reported on measured against unmeasured
   requests, so a reader can see whether the measured set under-represents the hard cases. **The verdict states
   plainly that R1 to R3 do not cover the GPU-versus-host split under concurrency 4 and 8.**
3. **Limitations name the measurement that would close that gap** (per-request attribution under concurrency),
   without designing it here.

**In-sample.** StudyENG1c Part A is IN-SAMPLE for the rule, because the rule was finalized after seeing it (its 95
of 95 is post hoc). Part A is reported separately and never pooled with TEST.

**Fenced.** The 120 StudyENG1c Part D HOLDOUT pairs: they are replayed as stream events, because they consumed
real capacity on the server and omitting them would corrupt every later prediction, but they are excluded from
every scored set and no measured outcome of theirs is ever read. A test proves both. The 174 StudyENG1 Part C
HOLDOUT triples and any T0b holdout are not read at all.

## 1. Ground truth: definition and thresholds

Each request's class is what the ENGINE reported for that request, with the reusable history
length taken from the scheduler side (Part A's build prompt, Part B's `prefix_tokens` and piece
chain, Part C's `hist_tokens`, Part D's population build). Block arithmetic throughout, because
the engine caches whole 16-token blocks and must recompute at least the last one, which is why
the tolerance is ONE BLOCK and not zero:

| class | measured condition |
|---|---|
| COLD | the request's cached tokens cover at most 1 block of its history |
| PARTIAL | more than 1 block of the history was recomputed (`history // 16 - cached // 16 > 1`) |
| HOST | at most 1 block recomputed AND more than 1 block transferred from host |
| GPU | at most 1 block recomputed AND at most 1 block from host |

COLD and PARTIAL need only the request's own `cached_tokens`. GPU versus HOST needs an
attributable host-transfer counter, by one of four routes, in this order: a per-request split
(Part A's `m_local` / `m_external` / `m_compute`); a per-resume counter window (Part B); a round
whose external total is zero, so no host load happened at all, or equals every warm request's
cached tokens, so each came from host (Part C); and a run whose external total is zero or equals
the run's cached tokens (Part D). A warm request with none of these is left UNDETERMINED and
scored only in the 2-class secondary.

**Measured TEST set: 4,135 reuse requests, of which 2,573 have a 4-class tier** (COLD 951,
GPU 1,316, HOST 262, PARTIAL 44), matching the pre-registered count exactly. Part A contributes
235 more, reported separately as in-sample.

**StudyENG1c's own harness simulator is not ground truth here.** Its agreement with the measured
class, as the brief requires as a separate check: **0.9539 over 347 Part D injections**, with its
errors being 7 PARTIAL called COLD, 5 HOST called PARTIAL, 2 GPU called HOST, 1 COLD called
PARTIAL and 1 HOST called COLD.

## 2. Mechanism verification (CLAUDE.md Steps 1 to 5)

Recorded in `results/orchestration/study_res1/res1_mechanism.json` before the TEST verdicts were
written; the driver stops without scoring if Step 2 finds an ABSENT or CONSTANT link.

**Step 1.** A history is reusable only while its blocks are still in a tier. Under write-through
every block computed on GPU is also stored on host, so the only thing that removes a history is
eviction, and eviction is least-recency-first on each tier independently. The tokens written to
each tier since a history's last refresh, with the refresh rule, therefore decide whether its next
request is served from GPU, from host, or recomputed; and every one of those inputs is something
the scheduler knows when it issues the requests.

**Step 2.** Four links, none ABSENT or CONSTANT: tokens written per server segment (the smallest
segment writes a 35-request stream, the largest 14,250 requests); host capacity minus the GPU pool
(**negative at 12 GiB, -13,792 tokens**, which is why ENG1c measured nothing from the host tier
there, through +985,632 at 256 GiB); evicted blocks per tier in the replay (non-zero on both tiers
in every segment); and the measured class mix, in which all four classes occur.

**Step 3.** One history followed through `C_c27` by hand, in the JSON: its build, every write that
displaced it with the running total, then the prediction as a lookup of contiguous chunks from
index 0 (first GPU, then host), its hit and recomputed tokens, the capacities at that moment, and
the measured class beside the predicted one.

**Step 4. Negative control: shuffle request order within each trial, keeping the same arrival
times.** Accuracy falls from **0.9946 to 0.6168**, against the occupancy-only baseline of
**0.4162**. The result moves, and it moves toward the baseline, so recency really is what the rule
exploits and not some artefact of the stream's token volumes, which the shuffle leaves untouched.

**Step 5.** The alternative is that something cruder agrees: tier fullness, FIFO, or LRU without
the host-path asymmetry. That is what R2 tests, and the four comparison predictors share every
line of the machinery except the policy switch. A second alternative, a lopsided class mix making
a constant answer look good, is why a constant-COLD baseline is scored and the class mix is
printed: COLD is only 37 % of the scored set.

## 3. R1 to R3, exactly as registered

| criterion | threshold | result | verdict |
|---|---|---|---|
| **R1** 4-class accuracy, pooled | 0.90 | **0.9946** (2,559 of 2,573) | **PASS** |
| **R1** 4-class accuracy, every cap | 0.85 | 12 GiB 1.0000, 27 GiB 0.9936, 38 GiB 0.9936, 60 GiB 0.9945, 256 GiB 1.0000 | **PASS** |
| **R2** rule beats every comparison predictor, paired bootstrap by trial excluding 0 | all | beats 4 of 5; **ties LRU-by-any-access** | **FAIL** |
| **R3** MAE of the predicted host fraction on PARTIAL cases | 0.10 | **0.2962** (n 32) | **FAIL** |

### 3.1 R2 in detail: the rule's distinguishing clause changes two predictions in 2,573

| comparison predictor | accuracy | difference (rule minus it) | 95 % CI by trial | excludes 0 |
|---|---|---|---|---|
| constant COLD | 0.3696 | +0.6250 | [+0.5428, +0.7045] | yes |
| occupancy only | 0.4162 | +0.5783 | [+0.5447, +0.6119] | yes |
| FIFO by store time | 0.9763 | +0.0183 | [+0.0121, +0.0252] | yes |
| LRU by host access only | 0.9899 | +0.0047 | [+0.0022, +0.0075] | yes |
| **LRU by any access** | **0.9942** | **+0.0004** | **[+0.0000, +0.0012]** | **no** |

R2 fails on the last row, and the reason is specific rather than statistical: **the rule and
LRU-by-any-access disagree on exactly 2 of the 2,573 scored requests**, both Part D at 38 GiB
(a churn arrival the rule calls PARTIAL and LRU-any calls COLD, measured PARTIAL; and an injected
job the rule calls COLD and LRU-any calls HOST, measured PARTIAL). The rule is right on one more
than LRU-any, which is a difference of 0.0004 and a confidence interval that touches zero.

The asymmetric clause (a request that loads anything from host refreshes only what it loaded, so
its GPU-served head is not refreshed) is the one thing that separates the rule from
LRU-by-any-access. It is what Part A's PM pattern demonstrated 15 out of 15 times. On this TEST
set it almost never binds, because a case has to be set up for it: a history must be half on each
tier, be touched, and then be asked for again after exactly enough other work. ENG1c Part A
constructs that situation deliberately; Parts B, C, D and E almost never produce it.

**Rule 2 classification.** This is a **real negative**, not an inconclusive. The mechanism was
present and exercised (Step 2 passed on every link, and the negative control moved accuracy by
0.38), so the finding is not an absent-mechanism artefact: on streams of this shape the rule's
asymmetry is not needed, and LRU-by-any-access is as good. What the rule's detail does buy,
measurably, is the difference against FIFO (+0.0183, CI excluding 0) and against LRU-by-host-only
(+0.0047, CI excluding 0), both of which are refresh-rule differences, and the enormous margin
over occupancy-only (+0.5783).

### 3.2 R3 in detail: the host fraction is a knife-edge where it is measurable

44 requests are measured PARTIAL and 32 carry a measured host fraction. The model UNDER-predicts
it: median measured 0.654 against median predicted 0.375, MAE 0.2962.

The cause is arithmetic, and it is worth stating precisely because it bears on how such a
predictor should be used. 29 of the 32 are Part B resumes at 60 GiB with occupancy 0.5, which is
ENG1c's own boundary cell (its section 4: 3 full reloads, 13 partial, 4 rebuilds in 20 trials).
There the surviving fraction is the difference of two nearly equal quantities: the host cap
(245,760 tokens) and the tokens written after the history (a median of 238,748 over 128 requests).
Converting each fraction error back into a token count, **the model's cumulative write accounting
is off by a median of 3,064 tokens, which is 1.37 % of the cap, and that 1.37 % becomes a 0.29
error in the fraction.** R3's 0.10 threshold on the fraction therefore demands about 0.4 %
accuracy in cumulative write accounting through a 240,000-token window.

One contributor is identified and quantified: the engine caches whole blocks and does not store
the trailing partial block, while the model charges the ceiling. Over the boundary window that is
a median **816 tokens, about a quarter of the 3,064-token gap**. The remaining three quarters are
not attributed by this study.

**No fix was applied.** Changing the model's rounding after seeing TEST results would be fitting
on TEST, which the brief forbids and which would make R1 meaningless. The fix is named in section
7 as a pre-registerable change for a follow-up.

### 3.3 Per cut

| cut | n | accuracy | measured mix |
|---|---|---|---|
| Part B (resumes) | 310 | 0.9935 | 204 COLD, 83 HOST, 13 PARTIAL, 10 GPU |
| Part C (queries) | 363 | 0.9862 | 196 COLD, 94 HOST, 55 GPU, 18 PARTIAL |
| Part D (injects, churn) | 1,900 | 0.9963 | 1,251 GPU, 551 COLD, 85 HOST, 13 PARTIAL |
| concurrency 1 | 80 | 1.0000 | 28 GPU, 27 HOST, 25 COLD |
| concurrency 4 | 124 | 0.9839 | 60 COLD, 35 HOST, 18 GPU, 11 PARTIAL |
| concurrency 8 | 159 | 0.9811 | 111 COLD, 32 HOST, 9 GPU, 7 PARTIAL |
| cap 12 GiB | 10 | 1.0000 | the host tier is smaller than the GPU pool, so nothing is host-warm |
| cap 27 GiB | 626 | 0.9936 | |
| cap 38 GiB | 783 | 0.9936 | |
| cap 60 GiB | 729 | 0.9945 | |
| cap 256 GiB | 425 | 1.0000 | |
| per role | churn 0.9969 (323), inject 0.9962 (1,577), query 0.9862 (363), resume 0.9935 (310) | | |

**Confusion matrix, the rule, all 2,573:** COLD to COLD 951, GPU to GPU 1,316, HOST to HOST 255,
PARTIAL to PARTIAL 37, **HOST called PARTIAL 7**, **PARTIAL called COLD 7**. There is no error
between GPU and HOST and no error involving COLD in either direction except the 7 PARTIAL called
COLD: every mistake is a boundary case where the model evicted slightly too much.

**All 14 errors, by part and cause:** Part D 7 (6 injects, 1 churn), Part C 5 (queries), Part B 2
(resumes). Each is the same cause in two directions: the model's cumulative write accounting is a
little heavy, so a history at the capacity boundary is predicted as having lost more than it did
(HOST called PARTIAL, 7 cases) or as having lost everything when a leading stretch survived
(PARTIAL called COLD, 7 cases). Per-row detail is in `res1_errors.json`.

## 4. The three pre-declared secondary analyses

### 4.1 The 2-class secondary, reported twice

| set | n | rule | FIFO | LRU any | LRU host only | occupancy only |
|---|---|---|---|---|---|---|
| all TEST reuse requests | 4,135 | **0.9959** | 0.9831 | 0.9959 | 0.9923 | 0.4048 |
| excluding Part B pieces 2 to 5 | 2,895 | **0.9941** | 0.9758 | 0.9941 | 0.9889 | 0.5333 |

Dropping the 1,240 piece-chain requests, which are warm by construction, costs the rule 0.0018
and costs occupancy-only nothing (it gains, because those requests were the ones it got wrong by
calling them cold). Warm versus cold is the easy question: every recency-based predictor is above
0.97, and only occupancy-only fails it badly.

### 4.2 Selection check: what the measured subset does and does not cover

Predicted tier distribution under the rule, measured against unmeasured requests:

| cut | measured n | measured predicted mix | unmeasured n | unmeasured predicted mix |
|---|---|---|---|---|
| pooled | 2,573 | 37 % COLD, 51 % GPU, 10 % HOST, 2 % PARTIAL | 1,562 | 1 % COLD, 86 % GPU, 13 % HOST, 0.2 % PARTIAL |
| B, piece chains | 310 | 66 % COLD, 27 % HOST, 4 % PARTIAL, 3 % GPU | 1,240 | 100 % GPU |
| C, concurrency 1 | 80 | 31 % COLD, 35 % GPU, 34 % HOST | 10 | 100 % COLD |
| C, concurrency 4 | 124 | 48 % COLD, 27 % HOST, 15 % GPU, 10 % PARTIAL | 56 | 75 % GPU, 25 % HOST |
| C, concurrency 8 | 159 | 70 % COLD, 18 % HOST, 6 % GPU, 6 % PARTIAL | 81 | **63 % HOST, 36 % GPU** |
| D | 1,900 | 66 % GPU, 29 % COLD, 4 % HOST, 0.5 % PARTIAL | 175 | **79 % HOST, 19 % GPU** |

The unmeasured requests are overwhelmingly ones the rule calls warm, and at Part C concurrency 8
and in Part D churn they are predominantly the ones it calls HOST, which is precisely the GPU
versus host distinction that needs an isolated counter window. **Stated plainly, as
pre-declared: R1, R2 and R3 do not cover the GPU-versus-host split under concurrency 4 and 8.**
Of the 1,562 unmeasured warm requests, 137 are Part C queries at concurrency 4 or 8 and 157 are
Part D churn arrivals; the remaining 1,268 are Part B piece-chain requests and 19 Part D injects.
What the measured subset does cover at those concurrencies is the 283 requests at concurrency 4
and 8 whose class came through a round-level or isolated route, where accuracy is 0.9839 and
0.9811.

### 4.3 Belief under ambiguous telemetry

Evaluated on the 88 Part C requests at concurrency 4 and 8 whose measured class came from a
ROUND-LEVEL route, so that reading the per-request window is not circular (on a request whose
truth came from its own isolated window, telemetry would be right by construction).

| what the scheduler believes | accuracy against the measured class |
|---|---|
| (a) telemetry alone: the request's own cached tokens plus the window's external increment | **0.8636** |
| (b) bookkeeping alone | **1.0000** |
| (c) bookkeeping, overridden by telemetry where the window is self-consistent | 0.9886 |

Only 10 of the 88 windows are self-consistent, and the one override among them is wrong, which is
why (c) sits just below (b). The reading is narrow but clean: under concurrency, the counters are
the thing that degrades, and the bookkeeping does not, so correcting bookkeeping with ambiguous
telemetry makes it worse rather than better. ENG1c's section 5 found the same about its own
metric-delta classifier, which works only at concurrency 1.

### 4.4 Concurrency, implication 4

Precision of host-warm predictions, by cap and concurrency, on the measured Part C subset: **1.000
in all nine cells** (11, 6, 9 predictions at 27 GiB for concurrency 1, 4, 8; 9, 12, 6 at 38 GiB;
7, 15, 14 at 60 GiB). ENG1c's implication 4 was that host-warm is not stable while cold rebuilds
run concurrently in a small host window; its evidence was that 12 of 16 host-constructed histories
at 27 GiB and concurrency 8 had become cold by scheduling. This study's bookkeeping PREDICTS that
loss rather than being surprised by it: at 27 GiB and concurrency 8 it issues only 9 host-warm
predictions out of 42 measured requests, calls 70 % of them COLD, and is right 0.9811 of the time.
The caveat of 4.2 applies: the 81 unmeasured requests in that cut are 63 % predicted HOST.

## 5. Part A, IN-SAMPLE and reported separately

Part A is where the rule was identified, so this is reproduction and not a test.

| predictor | accuracy on Part A (235 probes and touches) |
|---|---|
| rule | **0.9872** |
| LRU by host access only | 0.9362 |
| LRU by any access | 0.9106 |
| FIFO | 0.8723 |
| occupancy only | 0.1872 |

Confusion: COLD to COLD 38, GPU to GPU 12, HOST to HOST 162, PARTIAL to PARTIAL 20, GPU called
HOST 3. **The ordering is the reverse of the TEST set in one important way: on Part A the rule
beats LRU-by-any-access by 7.7 points, where on TEST it beats it by 0.04.** That is the clearest
statement of what 4.2 and 3.1 mean together: Part A was built to exercise the asymmetric refresh,
and the TEST streams do not exercise it.

Touch rules: of the 16 block-aligned Part A requests, the model marks 9 as taking the forced
last-block path and predicts HOST for those 9, against 6 measured HOST, so accuracy on the
block-aligned subset is 0.8125 and this is where the 3 GPU-called-HOST errors sit. The
half-evicted PM case is reproduced by construction in the unit tests: a history whose unrefreshed
head has aged out of host is predicted COLD even though its tail is still there, because the
prefix lookup fails at chunk 0.

## 6. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree |
|---|---|---|---|---|---|
| GPU pool | 62,944 tokens | 62,944 | ENG1c section 1, ENG1 | 1.00 | yes |
| host tokens per GiB | 4,096 | 4,096 (256 KiB per token, 16-token blocks) | ENG1c section 1 | 1.00 | yes |
| recovered fraction at 60 GiB, occupancy 0.5 | measured 0.654 median on the 29 scored partials | 0.568 (0.40 to 0.74) | ENG1c section 4 | 1.15 | yes, inside its CI |
| full recovery at 38 and 60 GiB, occupancy 0 | predicted HOST for 83 of 83 measured HOST resumes | 1.00 (0.84 to 1.00) | ENG1c section 4 | 1.00 | yes |
| 12 GiB buys nothing | 0 host-warm predictions, 0 measured | "12 GiB: zero" | ENG1c verdict B | 1.00 | yes |
| tier at arrival, Part D | measured class agrees with ENG1c's simulator on 0.9539 of 347 | 354 of 360 by its own check | ENG1c section 6 | 0.97 | yes |

No disagreement above 2x.

**2. Physical plausibility.** Nothing here is a latency or a rate; the quantities are token counts
and capacities, and each is checked against the server's own flags: the mmap size equalled the cap
in all 16 starts (ENG1c section 1), and the model's host capacity is computed from the same flag.
The largest single write in any stream is a 26,686-token filler, 1,668 blocks, which is 10.9 % of
the GPU pool, and the model's eviction of it is what produces the measured losses.

**3. Distribution sanity.** Accuracy is reported per cap, per part, per concurrency and per role
with its n, the class mix is given for every cut, and all 14 errors are listed individually in
`res1_errors.json`. The predicted host fraction on partials spans 0.000 to 0.667 and the measured
0.026 to 0.982, so no constant appears where a distribution is expected.

**4. Definition audit.** "History" is a StudySLICE1 D2 session of about 11k tokens in Parts A, C
and D and the 5-piece 10,394-token prefix in Part B, as ENG1c defines them. "Chunk" is one
16-token block, which is ENG1c's `blocks_per_chunk = 1`. "GPU-warm", "host-warm", "cold" and
"partial" are defined in section 1 here with explicit block thresholds, which ENG1c did not state
numerically; its own class labels were by construction, and the agreement between the two is
reported in section 1 rather than assumed. "Reuse request" is any request whose prompt contains a
previously built prefix, which excludes every episodic clip and filler.

**5. Claim linkage.** This bears on design decision D56 (where to store each history is a core
decision) and on FORMULATION.md's physical component of context inertia: it establishes that the
input a placement policy needs, namely which tier a history is in, is computable from the
scheduler's own bookkeeping at 0.9946 on 4-class accuracy where it can be measured, which is the
precondition for D56 being actionable at all. It does not speak to C5 (joint policy beats
decomposed), and nothing measured here falls outside FORMULATION.md's scope.

**6. Proxy validity.** Three proxies, all stated. (a) The reusable history length is a
scheduler-side quantity taken from the build or the recorded `hist_tokens`, not from a measured
hit count; where a piece chain grows, the previous part's prompt is used. (b) Untracked work is
held as one divisible bulk item per request rather than block by block: a bookkeeping economy that
leaves token accounting and every prediction unchanged, because only histories that some request
later reuses are ever queried by chunk. (c) The server segmentation uses the run_meta start times
with the epoch offset recovered from the frontend log, which carries both the server label and the
request's epoch time, so no timezone is assumed.

**Result: PASS 6 of 6.**

## 7. Limitations

1. **The GPU-versus-host split under concurrency 4 and 8 is not covered by R1 to R3.** 137 Part C
   requests at those concurrencies and 157 Part D churn arrivals are warm with no isolated counter
   window, and the rule calls most of them HOST. **The measurement that would close it is
   per-request attribution under concurrency**: a probe schedule in which each request's counter
   window can be isolated while other work is in flight, for example by serializing the probes
   within each window while the background load continues. Designing it is not in this study's
   scope.
2. **R3 is measured almost entirely in one boundary cell.** 29 of 32 scored partials are Part B
   resumes at 60 GiB with occupancy 0.5. The fraction there is the difference of two nearly equal
   quantities, so a 1.37 % error in cumulative write accounting becomes a 0.29 error in the
   fraction. A pre-registerable follow-up would charge whole blocks only (the engine does not store
   the trailing partial block, which is 816 of the 3,064-token median gap) and score the fraction
   on a cell designed to sit away from the capacity boundary. **That change was NOT applied here,
   because it would be fitting on TEST.**
3. **The rule's asymmetric refresh is not distinguishable from plain LRU on these streams** (2
   differing predictions in 2,573). It is distinguishable on Part A, which is in-sample. Whether
   the asymmetry matters in production depends on how often a half-evicted history is touched, and
   no TEST stream here answers that.
4. **The model has no pinning model beyond the running request.** Blocks of the request being
   served are protected during its own eviction pass, and nothing else is, so a long-running
   request's blocks could in principle be evicted under it in the model where the engine would not.
5. **Part E contributes write volume only.** It has no reuse request, so it tests nothing directly.
6. **All measurements are one H100 NVL and one model** (Qwen3-VL-32B-Instruct at vLLM 0.31.0 with
   the native offloading connector). The rule is a property of that stack's connector and eviction
   policy.

## 8. Interpretation, separate from the measurements

The bookkeeping question D56 depends on is answered in the affirmative, and more cleanly than the
delay question StudyT0b asked: from the request stream and the two capacities alone, with no
measured counter and no fitted parameter, the tier a history is in is predicted correctly on
0.9946 of the requests where the tier can be measured, with every single error a boundary case and
no confusion at all between GPU and host. A placement policy can therefore price host residency
from its own bookkeeping rather than from telemetry, which matters because section 4.3 shows the
telemetry is exactly what degrades under concurrency while the bookkeeping does not.

What the study does not support is the stronger claim that the rule's full detail is necessary.
Three of its clauses are load-bearing on this data: write-through, refresh on use, and tail-first
eviction, whose absence costs FIFO 1.8 points and occupancy-only 58 points. The fourth, the
asymmetric host refresh that Part A was built to demonstrate, changes two predictions in 2,573
here. The honest summary is that a scheduler needs recency bookkeeping on both tiers and does not
need the asymmetry to get 0.99 on streams of this shape, while a scheduler that deliberately
touches half-evicted histories, which is what the asymmetry governs, has no evidence from this
study to go on.

The practical consequence for the policy is the one ENG1c's implication 1 stated and this study
now tests: residency is decided by the tokens written since a history's last refresh, measured
against the free GPU pool and the host cap, and the scheduler can count those itself. The one
quantity it should not trust its own bookkeeping for is HOW MUCH of a history survives when the
write volume sits within a couple of percent of the cap, which is where R3 fails and where a
policy should treat a history as possibly cold rather than partially warm.

## 9. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/residency.py` | NEW. The chunk-level two-tier bookkeeping model, the four comparison predictors and the replay |
| `experiments/orchestration/run_res1.py` | NEW. Stream reconstruction from the committed rows, the measured ground truth, R1 to R3, the pre-declared analyses and the mechanism controls |
| `experiments/orchestration/policy/tests/test_residency.py` | NEW. 36 tests: the tier, the classes, the policy switch, the measured thresholds, the holdout fence and the stream counts |
| `results/orchestration/study_res1/res1_scores.json` | every number in sections 1, 3, 4 and 5 |
| `results/orchestration/study_res1/res1_mechanism.json` | Steps 1 to 5, the unit trace and both controls, written before the verdicts |
| `results/orchestration/study_res1/res1_errors.json` | all 14 errors, per row, with the class mix |
