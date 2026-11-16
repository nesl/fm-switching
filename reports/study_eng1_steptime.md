# StudyENG1-steptime: engine step time, admission, paired single-action ground truth and residency telemetry

Pre-registered in `research/EXPERIMENTS.md` (row StudyENG1-steptime, 2026-11-15, before any run; design decisions by the
user 2026-11-15: options 1a to 10 as recommended plus additions (i) overhead gate and (ii) the W25 warm condition).
Host h100nvl (sn4622120321) GPU 2, exclusive, serial, isolated. Scripts: `experiments/cost/study_eng1_steptime.py`
(runner), `experiments/cost/study_eng1_analyse.py` (analysis), `experiments/cost/eng1_statlog/` (stat-logger plugin).
Results: `results/cost/study_eng1/`.

## 1. Question and design

The scheduler scores each action by simulating the next 0.5 to 1 s of the engine with and without the action, so its
engine model must predict the delay that ONE action imposes on every other request. StudySIM1d's engine model (built
from TTFT-level data; summed compute per step, no sub-linear batching, no head-of-line hold behind a running slice)
failed out of sample on slice-vs-episodic interactions (`reports/study_sim1d_validate.md` sections 2.8 and 3.5). This
study measures the engine directly:

- **Part A (fit data):** step time vs batch composition. A1 episodic batches (N=1 378 tokens, N=3 about 1,062 tokens;
  k in {1, 2, 4, 8, 16}; 30 repetitions). A2 single prefill pieces (s in {256 ... 8192} tokens = 3 / 6 / 11 / 23 / 46 /
  91 frames) on a cached prefix c in {0, about 4k, about 11k, about 26k} (0 / 44 / 121 / 288 frames), alone or with
  j in {1, 4} episodic requests, plus a monolithic (c + s) control. A3 warm residents (append, escalation) on 4k / 11k /
  26k contexts with j in {0, 1, 4}.
- **Part B (fit data):** admission. A long request (monolithic about 11k cold history, or a 2,048 / 1,024-token piece
  on a cached 11k prefix) with an episodic N=1 injected at 0 / 25 / 50 / 75 % of its solo duration; E0 and T1.
- **Part C (ground truth for T0):** paired with / without single-action injection over 10-s traces of background
  episodic load (P25, P40 Poisson; S2, S4 periodic streams), six actions, 20 paired trials per (load, action), 30 %
  HOLDOUT fixed before any run. Addition (ii): W25 (P25 plus 8 warm sessions on KV-HOST), run last if the guard allows.
- **Part D (telemetry):** can counters attribute a request's prefix hits to GPU (local) vs host (external)?

### 1.1 Hypotheses (recorded before running)

- **H-step:** step duration is sub-linear in the number of small prefills batched together. SUB-LINEAR if median batch
  time(k 16) / (16 x median time(k 1)) < 0.8 with its 95 % bootstrap CI below 0.8 (per N); LINEAR otherwise.
- **H-admit:** while a long prefill runs, an arriving episodic request (a) waits for the long request's remaining work,
  (b) joins the next step and pays only longer steps, or (c) in between, chunk-size dependent. Per injected request:
  wait = TTFT minus the solo episodic TTFT (same engine); R = D_L x (1 - offset); rho = wait / R; (a) if rho >= 0.8;
  (b) if rho <= 0.2 or wait <= one step of that long request; else (c). Cell regime = regime of the median rho.
- **H-tier:** attribution is UNAMBIGUOUS at concurrency 1 if accuracy >= 95 %, and DEGRADES under concurrency if
  concurrency-4 accuracy is more than 10 points lower.

### 1.2 Servers, flags and caching (stated per CLAUDE.md)

All servers: 32B-I (Qwen3-VL-32B-Instruct @0cfaf481), vLLM 0.31.0, the StudySLICE1 base (max_model_len 32,768,
gpu_memory_utilization 0.9, bf16, chunked prefill with 8,192-token steps, fcfs, async scheduling on by default,
**prefix caching ON**, multimodal processor cache 128 GiB, `--enable-prompt-tokens-details`, `--enable-log-requests`
with the E10d millisecond logging config). KV pool 62,944 tokens. Added per server:

| server | added flags | used for |
|---|---|---|
| E0 instrumented | `--enable-logging-iteration-details` + ENG1 plugin | A, B (E0), C (E0 actions) |
| T1 instrumented | E0 instrumented + `--long-prefill-token-threshold 1024` | B (T1) |
| KV-HOST instrumented | + `--kv-offloading-size 256` (native backend) | C hostreload, W25 |
| KV-HOST + kv metrics | KV-HOST instrumented + `--kv-cache-metrics` | D |
| E0 plain (smoke only) | none (no iteration details, no plugin) | overhead gate (i) |

Every server's non-default-args line is parsed and must equal exactly the declared set (else STOP). The plugin is
loaded through PYTHONPATH (no venv change, no engine flag).

**Caching.** Every request in this study is cold for the prefix and processor caches except where a cached prefix is
the object of measurement: episodic images carry bytes plus a per-run uuid, so a reused clip hashes differently in
every run; D2 histories use fresh namespaces (new header tag, new uuids). Cached prefixes (A2 / A3 / B / C pieces,
appends, the Part D GPU state) are built immediately before use by a request in the same namespace and are checked
(gap between the prefix's prompt tokens and the next request's cached tokens <= 32). Host-resident histories are made
by natural eviction: about 78k tokens of fresh filler prefill (3 fresh ~26k histories) after the history is built,
more than the 62,944-token GPU pool.

(Sections 2 onward are written from the smoke run and the full run.)

## 2. Smoke run (2026-11-15 13:19 to 13:40, recorded before the full run)

Two invocations (the first stopped at the W25 pair on an implementation bug: the warm sessions' frames were not
pre-encoded; fixed by pre-encoding all 234 D2 sessions when W25 runs; the second invocation ran the W25 pair and Part
D). Five servers: SMK_plain, SMK_E0, SMK_KVHOST, SMK_KVHOST_2, SMK_KVHOSTm. **All five non-default-args lines equal the
declared sets** (extra keys: none; missing: none); the plugin loaded on every instrumented server; not VOID; GPU 2
exclusive throughout. Files: `results/cost/study_eng1/eng1_smoke_*`. Smoke data are never used for fitting.

### 2.1 Overhead gate (addition (i)): AMBIGUOUS AT k=8, reported for a decision

Ten repetitions each, same D14 requests on both servers (one cursor from the manifest start), every request cold
(cached 0).

| k | metric | plain | instrumented | ratio |
|---|---|---|---|---|
| 1 | median TTFT | 0.1369 s | 0.1301 s | **0.950** |
| 8 | median over all 80 requests | 0.4127 s | 0.5079 s | **1.231** |
| 8 | median over batches of the batch max | 0.5810 s | 0.5867 s | **1.010** |
| 8 | median over batches of the batch mean | 0.4485 s | 0.4536 s | **1.012** |

The k=8 per-request median is not a stable statistic: the 8 "simultaneous" requests reach the engine in three
admission tiers (1 request, then 3 or 4, then 3 or 4) because the API server preprocesses their images one after the
other (about 45 ms per N=1 request). Within each tier the two servers agree (tier 2: plain 0.36 to 0.45 s,
instrumented 0.29 to 0.51 s; tier 3: 0.565 to 0.601 s vs 0.556 to 0.658 s), but the pooled median lands in tier 2 or
tier 3 depending on how many batches split 4 / 4 vs 3 / 5 (plain: 5 of 10 batches 4 / 4; instrumented: 2 of 10). The
gate as pre-registered ("ratio of medians", > 1.03 at either k: STOP AND ASK) therefore fires on the per-request
median (1.231) and passes on both batch-level medians (1.010, 1.012) and at k=1 (0.950).

### 2.2 elapsed_ms under async scheduling (stated, as requested)

| lone request | iteration elapsed_ms | engine prefill time (plugin, scheduled -> first token) | client TTFT |
|---|---|---|---|
| N=1 episodic (378 tokens, 1 image) | 43.8 to 44.2 ms | 84.1 to 84.7 ms | 0.115 to 0.130 s |
| 91-frame piece at c=0 (8,231 tokens: steps of 8,192 + 39) | 964.7 to 969.4 + 27.7 to 28.2 ms | 1,488 to 1,555 ms | 2.00 to 2.12 s |

With vLLM 0.31.0's default async scheduling, elapsed_ms is the time the engine core blocks on the step's model output
after launching it, i.e. the residual GPU time not overlapped with the CPU-side launch (including the vision encoder);
it is about 50 to 65 % of the step. **It is a lower bound, not the step duration.** The analysis therefore uses (a)
the interval between consecutive engine output batches while the engine stays busy (a decode step after a prefill:
24 ms interval vs 22 ms elapsed) and (b) the engine's own per-request prefill time from the plugin. The client TTFT
also contains frontend preprocessing that is serial across requests (about 45 ms per N=1 image, about 0.5 s for 91
frames), which the scheduler's engine model must include.

### 2.3 Other smoke results

- **Cross-check (sanity):** N=1 single-request TTFT 0.124 s vs StudyD7b 0.134 s (ratio 0.92); N=3 0.241 s vs
  StudyD7 0.264 s (0.91); monolithic ~11k 2.755 s vs StudySLICE1 Part A 2.700 s (1.02); 2,048-token piece on 11k
  0.565 s vs SLICE1 chain slice 0.486 s (1.16). None > 1.25x.
- **Cold / prefix checks:** every build and monolithic request cached 0 tokens; every chained piece reused its prefix
  (gap 4 to 20 tokens <= 32).
- **H-step (A1, 2 repetitions, k 1 and 16 only):** batch time(16) / (16 x time(1)) = 0.56 (N=1) and 0.77 (N=3),
  both CIs below 0.8 (smoke size; not a verdict).
- **Part B (2 repetitions):** monolithic 11k (D_L 2.75 s): episodic TTFT 2.07 / 1.40 / 0.73 s at 25 / 50 / 75 %
  (rho 0.93 / 0.92 / 0.85, serial); at offset 0 the episodic request is served first (0.20 s) because the 11k
  request spends about 0.6 s in frontend preprocessing. 2,048-token piece (D_L 0.565 s): rho 0.88 at 25 %.
- **Part C pairs:** 6 pairs (P40 piece2048, P40 burst4, S2 mono11k, P25 hostreload, W25 append5) with 0 cached-token
  mismatches over 236 background requests; warm traffic in the W25 pair identical in all three runs (same 8 appends,
  same cached tokens, submit lag <= 5 ms); dispatch lateness <= 3.3 ms. Run-to-run noise (independent repeat of the
  without run): per-request median |d| 2.4 to 4.1 ms, sum over a trace 0.02 to 0.08 s. P40 piece2048: total imposed
  delay 5.04 s over 13 requests (max 0.66 s) for a 0.62 s piece; P40 burst4 0.09 s; P25 hostreload 0.03 s (the
  11,184-token history reloaded from host in 80 ms, 2.93 GB, TTFT 0.245 s).
- **Host residency by natural eviction works:** the reload request's window shows external hits 11,184 and
  prompt tokens by source external_kv_transfer 11,184, local hits 0. Each filler of 3 x 27,042 tokens takes about
  22.5 s (7.5 s per request), longer than the 12 s assumed in the estimate.
- **Part D (2 per state at concurrency 1, 1 round at 4):** concurrency 1: 6 / 6 correct (GPU: local hits = cached
  tokens, external 0; host: external hits = cached tokens, local 0; cold: neither). Concurrency 4: 1 / 4 correct, the
  windows overlap and each request's window absorbs the others' counter changes. Signals that exist:
  prefix_cache_{queries,hits}, external_prefix_cache_{queries,hits}, prompt_tokens_by_source {local_compute,
  local_cache_hit, external_kv_transfer}, prompt_tokens_cached, kv_offload_{store,load}_{bytes,time,size},
  kv_offload_cpu_cache_usage, num_requests_waiting_by_reason, request_num_preemptions, and with --kv-cache-metrics
  kv_block_{lifetime,idle_before_evict}_seconds (eviction samples). The per-request API usage reports cached tokens
  only as a total (no local / external split).

### 2.4 Gate re-run, interval validation and component isolation (amendments 1 and 2, before the full run)

**Gate re-run (30 repetitions per k, 2026-11-15 14:34 to 14:40; one earlier attempt at 14:33 was VOID before any
request because a short Python process of ours ran outside the job, and was discarded: files `eng1_gatevoid1_*`).**

| ratio instrumented / plain | value | rule (<= 1.03) |
|---|---|---|
| k=1 per-request median (0.1381 vs 0.1365 s) | 1.012 | pass |
| k=8 batch max / batch mean | 1.004 / 1.007 | pass |
| k=8 tier 1 / tier 2 / tier 3 (tier index) | 1.019 / **1.054** / 1.011 | tier 2 fails |
| k=8 pooled per-request median (reference) | 1.237 | n/a |

Tier composition differs: 6 of 30 instrumented batches split 1 / 7 against 0 of 30 plain. Size-matched tiers agree
within 2 % (tier 2 of 2 / 3 / 4 requests: 0.988 / 0.991 / 1.007; tier 3 of 3 / 4 / 5: 1.010 / 1.002 / 0.991) except
tier 2 of 6 requests (n 6 each, 1.056). Rule fired: STOP AND ASK (user decision: isolate the components).

**Interval validation (10 per kind, test requests behind a decode-only pacer).** First definition (sum of the
intervals of the steps carrying the request's prefill tokens): 0.49 / 0.82 / 0.90 of the engine prefill time for
N=1 / 23-frame / 91-frame requests, failing the 5 % rule. Cause: each image-bearing request is preceded by an
**admission step**, an output batch with 0 context tokens and elapsed 0.0 whose interval is long (median 50 ms for 1
image, 66 ms for 23, 158 ms for 91; the pacer's decode interval is 21.4 ms otherwise): the engine core prepares the
request's multimodal inputs on its critical path before the prefill step. With the admission step included, the
interval sum reproduces the engine prefill time: **ratio 1.001 (N=1, range 1.0005 to 1.0021), 1.000 (23 frames,
0.9991 to 1.0019), 0.999 (91 frames, 0.9985 to 0.9989), 30 / 30 within 0.3 %**. Accepted by the user as an
implementation fix; the admission step is modelled as its own term (section 6).

**Component isolation (k=8, 30 repetitions each, same requests; pre-registered decision rule in amendment 2).**

| server | 1 / 7 splits | Fisher p vs plain | tier-1 median TTFT | tier-1 ratio | batch max ratio | batch mean ratio |
|---|---|---|---|---|---|---|
| plain | 0 / 30 | 1.000 | 0.1792 s | 1.000 | 1.000 | 1.000 |
| full instrumentation | 6 / 30 | 0.024 | 0.1826 s | 1.019 | 1.004 | 1.007 |
| plugin only (repeat, primary) | 0 / 30 | 1.000 | 0.1599 s | 0.892 | 0.987 | 0.978 |
| plugin only (first run) | 0 / 30 | 1.000 | 0.1731 s | 0.966 | 0.997 | 0.997 |
| iteration details only | 0 / 30 | 1.000 | 0.1757 s | 0.981 | 1.003 | 0.998 |

The first plugin-only run may have overlapped a sub-second file-editing Python process of ours (not flagged by the
30-s monitor; timing could not exclude overlap with its repetitions), so a clean repeat was run and is primary; both
agree on the decision. **Decision (pre-registered rule): neither component alone reproduces the elevated split rate
(>= 4 of 30) or lengthens tier-1 time by more than 2 %; the full instrumentation is accepted** and the full run was
launched (14:50). The 1 / 7 excess appears only with both components together (6 / 30, p 0.024) and is reported as a
tier-size dependence: with both, slightly more requests can complete front-end preprocessing before the engine's
second step is scheduled, which moves requests from tier 3 into tier 2 without lengthening any size-matched tier by
more than 2 %. Variation in tier-1 time across plain-equivalent servers (0.160 to 0.183 s) is itself about 13 %, so
tier-1 differences of 2 % are within server-to-server variation.

**Process note.** During the smoke run (13:19 to 13:40) several short Python analysis commands of ours ran while
servers were serving; the monitor did not flag them and the smoke meta records not VOID. Smoke data are not used for
any result. From the gate re-run on, no Python process of ours runs while a server is up (attempt 1 of the gate re-run
was VOID for exactly this reason and was discarded).

## 3. Mechanism verification (CLAUDE.md Steps 1 to 5; recorded from the smoke run, before the full run)

**Step 1, causal chain.** Materialisation work (cold history prefill, prefix-chained slices, host reloads, warm
appends) runs on the same engine as episodic requests (FORMULATION.md section Constraints 2, serving feasibility:
"pay materialization + catch-up first", on the serving node). The engine executes work in steps of at most 8,192
tokens (chunked prefill); an episodic request that arrives while such a step runs cannot start before that step ends
and then shares the next step with whatever is scheduled (admission); its TTFT therefore rises by the remaining step
time plus the extra step time, and requests queued behind it inherit the delay (queue cascade). That delay lowers the
fraction of requests meeting the latency SLO (FORMULATION.md section Objective). The scheduler's counterfactual rollout
must predict this delay per action; this study measures each link: step time as a function of step content (Part A),
the admission rule (Part B), the end-to-end imposed delay per action (Part C), and whether the engine can tell where a
prefix was served from (Part D, the serving-feasibility input).

**Step 2, links instantiated (smoke values).**

| causal link | implementing quantity | value / range in smoke | varies as expected? | evidence |
|---|---|---|---|---|
| materialisation shares the engine | steps carrying a piece's tokens alongside episodic requests | piece step 2,081 tokens + 23 images, then a shared step of 3 episodic requests | yes | step log, section 3 Step 3 trace |
| step time grows with step content | busy-interval step duration vs new tokens | 22 to 25 ms (decode only) to about 1 s (8,192 tokens) | yes, monotone in tokens | plugin step rows, 677 steps with durations |
| sub-linear batching | batch time(16) / (16 x time(1)) | 0.56 (N=1), 0.77 (N=3) | yes, differs by N | A1 smoke |
| admission behind a running step | rho = wait / remaining long work | 0.85 to 0.93 (mono 11k), 0.88 (piece 2,048), about 0 at offset 0 | yes, varies with offset | Part B smoke |
| imposed delay on others | sum of TTFT(with) - TTFT(without) | 0.03 s (hostreload) to 5.04 s (piece2048 at P40) | yes, varies by action | Part C smoke pairs |
| noise floor | sum of repeat - without | 0.02 to 0.08 s | small vs the effect | Part C repeats |
| tier attribution | counter deltas per request window | 6 / 6 at concurrency 1, 1 / 4 at concurrency 4 | yes, varies with concurrency | Part D smoke |

No link is ABSENT or CONSTANT.

**Step 3, one traced unit (Part C, P40, piece2048, trial 12, background request 17; times from trace start).**

| run | event | t (s) | content |
|---|---|---|---|
| with | piece submitted | 3.744 | 12,913 prompt tokens, 10,832 cached (prefix gap 11): 2,081 new tokens, 23 images |
| with | request 17 submitted | 3.892 | 378 tokens, 0 cached, 1 image |
| with | step 311 ends | 4.363 | 1 prefill request, 2,081 tokens, 23 encoder inputs (the piece; it started after idle) |
| with | step 312 ends | 4.556 | 3 prefill requests, 1,134 tokens (request 17 + 2 others), 0.193 s |
| with | request 17 first token | 4.558 | TTFT 0.666 s |
| without | request 17 submitted | 3.892 | identical bytes, its own uuid namespace, 0 cached |
| without | step 415 ends | 4.056 | 1 prefill request, 378 tokens, 0.383 s interval since the previous output (idle gap) |
| without | request 17 first token | 4.057 | TTFT 0.165 s |

Imposed delay on request 17 = 0.666 - 0.165 = 0.501 s: it waited for the piece's step to end (4.363 s, about 0.42 s
after its frontend preprocessing finished) and then shared a 3-request step (0.193 s) instead of running alone. The
binding resource is GPU step time; KV is not binding (KV usage < 30 %, no preemptions). Requests 18 to 29 inherit
0.20 to 0.66 s each; total 5.04 s.

**Step 4, negative control.** Disable the mechanism (no injected action): the independent repeat of the without run
is exactly that control. It gives per-request |d| median 3.4 ms and a trace sum of -0.08 s for the same pair whose with
run gives +5.04 s; for burst4 the with-minus-without sum is 0.09 s against a repeat sum of 0.06 s, i.e. a 4-call burst
at P40 is near the noise floor. Collapse to the null when the action is absent: PASS.

**Step 5, alternative explanation.** The imposed delay could come from frontend contention (the piece's 23 images
being preprocessed in the API server, delaying the background requests' preprocessing) rather than from the engine
step. The two are distinguished by the step log: in the traced unit request 17 was admitted in the step that followed
the piece's step and its submit-to-admission time matches the piece step's end, while the frontend preprocessing of
23 images (about 0.15 s) ended before that. The full run quantifies both per action (client TTFT minus engine queue +
prefill time = frontend share). A second alternative, cache-state differences between paired runs, is excluded by
the per-request cached-token equality (0 mismatches).

## 4. Full run (2026-11-15 14:50 to 2026-11-16 01:05)

- **Attempt 1 (14:50):** stopped VOID at 15:17 by an unrelated `tar | split` job of the user's account (the D14b
  archive). By user decision A1 (300 batches) and A2 c0 (540 pieces), all finished by 15:08:38, are kept (server load
  `A_E0_part1`; rows tagged `kept_by_user`); the partial A2 c4k rows are discarded (kept as `eng1_void1_*`). The user
  declared their own non-GPU file activity an exception to the VOID rule (amendment 3); the ENG1 monitor's safe-command
  list was extended for archiving / transfer tools only (our python / vllm processes and any foreign GPU-2 process
  still void / stop).
- **Attempt 2 (16:03):** interrupted by us during server start to apply the exemption (no data).
- **Attempt 3 (16:05 to 01:05), the run reported here:** Part A resumed at A2 c4k (`--a-skip A1,c0`), then B (E0,
  T1), C (P25, P40, S2, S4 on E0; hostreload on KV-HOST), D, W25. **Not VOID; nothing remaining at the guard** (the
  10-h guard was not reached; W25 exempt); 14 server loads, every non-default-args line exactly as declared.
- **Plugin defect found after the run (implementation, reported):** on the KV-HOST servers the plugin wrote no rows.
  Each row carried the offloading connector's stats, whose label keys are tuples; `json.dumps` rejects non-string keys
  even with `default=`, and the plugin's protective `except` swallowed every row. E0 / T1 servers are unaffected.
  Lost on the six KV-HOST loads (C hostreload x 4, D, W25): per-step prompt tokens by source and per-request engine
  queue / prefill times. Recovered: step composition, timestamps (ms), elapsed_ms, KV usage and encoder inputs from
  the server logs' iteration-details lines (`eng1_steps/<label>_iterlog.jsonl.gz`, all 14 loads; on A_E0 the log
  and the plugin agree on all 7,594 steps, identical context tokens, timestamps within 1 ms). Unaffected: every
  client-side quantity (TTFTs, cached tokens, pairs), Prometheus counter deltas (Part D's pre-registered attribution
  rule), front-end log rows. The plugin is fixed (string keys, failures logged) for StudyENG1b.

## 5. Part A: step-time model

**A1 (batches of k simultaneous requests; median over 30 batches of the batch's last first token).**

| k | N=1 (378 tok) | N=3 (~1,062 tok) |
|---|---|---|
| 1 | 0.135 s | 0.252 s |
| 2 | 0.211 | 0.435 |
| 4 | 0.341 | 0.765 |
| 8 | 0.589 | 1.523 |
| 16 | 1.100 | 2.943 |

**H-step: SUB-LINEAR for both N.** time(16) / (16 x time(1)) = **0.510** (95 % CI 0.503 to 0.519) for N=1 and
**0.731** (0.717 to 0.742) for N=3. Part of the batch time is serial front-end preprocessing (section 7), so the
engine-side batching gain is larger than these ratios show.

**A2 (piece TTFT, s; median of 30; j = co-submitted episodic requests).**

| prefix c | s 256 (j 0 / 1 / 4) | s 1,024 | s 2,048 | s 4,096 | s 8,192 |
|---|---|---|---|---|---|
| 0 | 0.108 / 0.118 / 0.150 | 0.252 / 0.297 / 0.290 | 0.448 / 0.504 / 0.628 | 0.908 / 0.941 / 1.093 | 1.977 / 2.027 / 2.034 |
| ~4k | 0.123 / 0.129 / 0.159 | 0.268 / 0.299 / 0.315 | 0.498 / 0.548 / 0.659 | 0.958 / 0.997 / 1.176 | 2.126 / 2.183 / 2.184 |
| ~11k | 0.158 / 0.163 / 0.191 | 0.308 / 0.358 / 0.365 | 0.564 / 0.603 / 0.753 | 1.118 / 1.161 / 1.288 | 2.414 / 2.456 / 2.460 |
| ~26k | 0.228 / 0.238 / 0.267 | 0.423 / 0.460 / 0.486 | 0.757 / 0.787 / 0.834 | 1.476 / 1.520 / 1.622 | dropped (> max_model_len) |

Attended context adds cost: a 2,048-token piece costs 0.45 s at c 0 and 0.76 s at c ~26k. Every piece reused its
prefix (0 prefix failures, gap <= 32 on all 2,070 pieces); every cold request cached <= 16 tokens.

Episodic requests co-submitted with a piece (median TTFT, j=4): 0.50 to 0.70 s behind a 1,024-token piece and 0.69 to
0.99 s behind a 2,048-token piece, but only 0.35 to 0.39 s next to a 4,096 or 8,192-token piece, because those pieces
spend 0.3 to 0.5 s in front-end preprocessing (46 / 91 images) and the episodic requests reach the engine first.
Arrival order at the engine is set by the front end, not by submission order (section 7).

**Per-piece overhead (piece vs the same tokens inside one monolithic request; chain = prefix build + piece).**
Chain / monolithic 1.00 to 1.08 (median 1.03); extra time per piece 0.04 to 0.24 s over the marginal monolithic
cost, largest for small pieces on long prefixes (c ~26k, s 256: +0.24 s), smallest at s 2,048 (+0.04 s). The fixed
per-request cost (front end about 30 to 60 ms plus the admission step, section 8) dominates small pieces.

**A3 (warm residents, median TTFT, s).** Append (5 frames): 0.166 / 0.212 / 0.276 s alone on ~4k / ~11k / ~26k
contexts, rising to 0.212 / 0.242 / 0.281 s with 4 episodic requests. Escalation (question, 4 tokens): 0.064 / 0.093 /
0.130 s alone, 0.120 / 0.146 / 0.170 s with 4 episodic. Episodic requests co-submitted with them: 0.35 to 0.49 s at
j=4. The cloud requests produce 1 to 4 tokens (episodic 8), so no long-decode resident is studied.

**Fitted step model** (`results/cost/study_eng1/eng1_step_model.json`; fit data: Part A (A_E0_part1 up to 15:08:39,
A_E0) and Part B E0 steps; Part C and the HOLDOUT never used). Step duration = interval between consecutive output
batches while busy (validated, section 2.4). n = 5,974 steps, R^2 = 0.985.

| term | coefficient |
|---|---|
| intercept | 28.7 ms |
| per new prefill token (0 to 512) | 0.074 ms |
| extra per token above 512 / 2,048 / 4,096 | +0.019 / -0.008 / +0.092 ms |
| per image encoded in the step | 8.6 ms |
| per decode request / per prefill request | -0.6 / +3.9 ms |
| per (token x cached context) / 1e6 | 1.95 ms |
| admission: per image of the NEXT step / per 1k encoder tokens of the next step | -1.2 ms / 18.1 ms |

Residuals (median |res|): decode-only steps 2.9 ms (p90 21 ms); 1 to 512 tokens 5.7 ms; 512 to 2,048 10.6 ms (5.6 %);
2,048 to 4,096 25.6 ms (5.1 %); 4,096 to 8,192 111 ms (7.1 %); admission steps 27.9 ms. By server: A_E0 6.7 ms,
A_E0_part1 7.2 ms, B_E0 3.5 ms. The model is a lookup-free piecewise-linear form; it is the fit to be tested on the
Part C HOLDOUT later (T0); no HOLDOUT data entered it.

## 6. Part B: admission behaviour (H-admit)

Solo episodic TTFT 0.141 s (E0), 0.142 s (T1). Long-request solo duration D_L: monolithic ~11k 2.673 / 2.705 s,
2,048-token piece 0.564 / 0.574 s, 1,024-token piece 0.289 / 0.293 s (E0 / T1). "One step" for the one-step rule:
0.548 s (E0), 0.529 s (T1), the median busy interval of the Part B servers' steps carrying >= 1,024 prefill tokens.
30 injections per cell.

| long request | offset | E0 TTFT / rho (p10 to p90) / regime | T1 TTFT / rho / regime |
|---|---|---|---|
| mono ~11k | 0 % | 0.200 s / 0.02 / b | 0.198 / 0.02 / b |
| mono ~11k | 25 % | 2.110 / 0.98 (0.96 to 1.02) / **a** | 1.723 / 0.78 (0.76 to 0.80) / **c** |
| mono ~11k | 50 % | 1.474 / 1.00 / a | 1.475 / 0.99 / a |
| mono ~11k | 75 % | 0.792 / 0.97 / a | 0.799 / 0.97 / a |
| piece 2,048 | 0 % | 0.157 / 0.03 / b | 0.163 / 0.04 / b |
| piece 2,048 | 25 % | 0.507 / 0.87 / a | 0.507 / 0.85 / a |
| piece 2,048 | 50 % | 0.378 / 0.84 / a | 0.370 / 0.80 / b |
| piece 2,048 | 75 % | 0.239 / 0.69 / b | 0.234 / 0.64 / b |
| piece 1,024 | 0 % | 0.171 / 0.10 / b | 0.181 / 0.14 / b |
| piece 1,024 | 25 % | 0.323 / 0.84 / a | 0.315 / 0.79 / b |
| piece 1,024 | 50 % | 0.256 / 0.80 / a | 0.255 / 0.77 / b |
| piece 1,024 | 75 % | 0.186 / 0.63 / b | 0.187 / 0.61 / b |

**H-admit verdict: (a) serial blocking for a long prefill on E0.** An episodic request arriving while a monolithic
11k request runs waits for essentially all of its remaining work (rho 0.97 to 1.00 at 25 to 75 %); this is
head-of-line blocking behind the running request's remaining chunks, not fair sharing. At offset 0 the episodic request
is served first (rho 0.02) because the long request is still in front-end preprocessing (about 0.5 s for 122 images).
For single-step pieces (2,048 / 1,024 tokens) "serial" and "waits one step" are the same event: rho 0.80 to 0.87 at
25 to 50 % (regime a on E0), falling to 0.6 to 0.7 at 75 % (classified b by the one-step rule: the remaining work is
shorter than one step). **T1 (long-prefill threshold 1,024) changes the regime only at the 25 % offset of the
monolithic request (rho 0.78, regime c, TTFT 1.72 vs 2.11 s)**: with 1,024-token chunks the episodic request can
join earlier, but it still waits about 80 % of the remaining work; at 50 / 75 % it is serial as on E0. So the rollout
must model the running request's remaining work as a queue ahead of a newly arriving request, not as a shared step.

## 7. Front-end serialization (measured system property, user point 4)

Every request's API-server arrival (client submit), 'Received' (body parsed and rendered) and 'Added' (handed to the
engine core) times come from the server log (`eng1_frontend_requests_h100nvl.jsonl`, 81,980 requests incl. KV-HOST
loads); the engine queue after 'Added' is the plugin's queued time (E0 / T1 loads).

| quantity | value (58,918 requests of Parts A, B and C-FIT matched) |
|---|---|
| front-end service when the front end was idle (44,607 requests) | **29.6 ms + 20.2 ms per MB of body** (median abs residual 1.8 ms, p90 14.6 ms) |
| front-end service when queued behind another request (14,311) | **6.9 ms + 17.7 ms per MB** (median abs residual 4.8 ms, p90 16.3 ms) |
| idle front-end time by request type (median) | episodic N=1 38.6 ms (0.44 MB); piece 59.0 ms; 1,024 / 2,048 piece 61 / 104 ms; monolithic ~11k history 499 to 532 ms |
| share of front-end time before 'Received' | 95.5 % (parsing and rendering the body, incl. images) |
| engine queue after 'Added' | median 20 microseconds, p90 50 microseconds |

The per-MB part (image decoding and processing) is serial across requests; about 23 ms of the fixed per-request
cost overlaps with the previous request. A purely serial model (idle service applied back to back) over-predicts
queued requests' hand-off by 25 ms (median), which the busy fit removes. This is why "simultaneous" requests reach
the engine in tiers (section 2.4) and why an episodic request co-submitted with a 91-frame piece reaches the engine
first (section 5). Once handed over, a request is scheduled within microseconds; all waiting after that is inside the
engine's steps (sections 6 and 8).

## 8. Admission step: multimodal preparation stall on the engine's critical path (user point 2)

Each image-bearing request is preceded by an output batch with no context tokens whose interval is longer than the
step it contains: the engine core prepares the new request's multimodal inputs before scheduling its prefill, and the
step running at that time (for example other requests' decodes) is delayed by the stall.

| measurement | value |
|---|---|
| validation (pacer decode 21.4 ms) | admission interval 50 ms (1 image), 66 ms (23), 158 ms (91): stall about 29 / 45 / 137 ms |
| full-run decode-only admission steps (n 268) vs the decode baseline (24 to 25 ms at 1 to 15 decode requests) | stall = **12.7 ms + 1.15 ms per image** admitted in the next step (median abs residual 5.5 ms); bins: 1 image 22 ms (n 3), 2 to 4 images 33 ms, 5 to 15 images 32 ms, 16 to 40 images 33 ms, 41+ images 66 ms |
| in the step model (all steps) | +18.1 ms per 1k encoder tokens of the next step (the per-image term is absorbed by it: -1.2 ms) |

Effect on concurrently running requests: every request decoding while an admission step runs has its next token
delayed by the stall (all requests in a step share its output time). For a 91-frame piece the stall is about 0.14 s,
paid by every running request, separate from the piece's own prefill compute and from front-end serialization.

## 9. Part C: paired single-action ground truth (FIT trials only; HOLDOUT recorded, not analysed)

580 pairs (480 base + 100 W25) plus 87 independent repeats. **0 cached-token mismatches over 30,164 compared
background requests; warm traffic identical in all 100 W25 pairs.** HOLDOUT verification: 174 triples recorded, all
in the pre-registered split, 20,040 rows, not analysed. Per (load, action), 14 FIT pairs: total imposed delay on all
other requests (sum of TTFT with minus without), median (p10 to p90); noise = |sum| of the independent repeat.

| load | piece1024 | piece2048 | mono11k | append5 | hostreload | burst4 |
|---|---|---|---|---|---|---|
| P25 | 0.10 (-0.09 to 0.38) | 0.49 (0.12 to 1.23) | **16.2** (8.6 to 25.7) | 0.08 | 0.03 (noise 0.05) | 0.13 |
| P40 | 0.39 (0.10 to 2.35) | 0.91 (0.32 to 2.49) | **32.9** (22.5 to 64.4) | 0.03 (noise 0.15) | 0.19 (noise 0.22) | 0.33 |
| S2 | 0.08 | 0.62 (0.46 to 1.00) | **19.0** (17.6 to 22.2) | 0.06 | 0.01 (noise 0.04) | 0.13 |
| S4 | 0.40 (0.15 to 0.97) | 2.57 (2.10 to 3.19) | **71.2** (63.2 to 87.3) | 0.18 (noise 0.11) | 0.07 | 0.60 |
| W25 | 0.14 (noise 0.10) | 0.44 (0.09 to 1.38) | **16.9** (9.1 to 33.0) | 0.05 | not run | 0.06 (noise 0.06) |

Requests delayed by more than 50 ms per trial (median): mono11k 12 to 45; piece2048 1.5 to 9.5; piece1024 0.5 to 3;
the others 0.5 to 5. Maximum single-request delay (median over trials): mono11k 2.6 to 3.1 s; piece2048 0.34 to
0.52 s; piece1024 0.07 to 0.23 s; hostreload 0.06 to 0.11 s. Per-request run-to-run noise (median |d| of the
repeat): 0.7 to 8.1 ms. Cells whose imposed delay is within the repeat noise (flagged): hostreload at P25 / P40 / S2,
append5 at P40 / S4, piece1024 and burst4 at W25: for these the action's cost to others is not distinguishable from
noise at 14 pairs.

Ranking (robust across loads): a monolithic ~11k cold prefill imposes 16 to 71 s of total delay (it blocks every
arrival for its 2.7 s, section 6); a 2,048-token piece 0.4 to 2.6 s; a 1,024-token piece 0.1 to 0.4 s; a host reload
of the same 11k history about 0 to 0.2 s (it loads 2.9 GB in about 80 ms and computes only the question); a warm
append and a 4-call burst 0.03 to 0.6 s. Periodic streams with more streams (S4) amplify the cascade (2,048-token
piece: 2.57 s at S4 vs 0.62 s at S2). W25's warm traffic does not change the ranking (values close to P25).

## 10. Part D: residency telemetry (H-tier)

KV-HOST + --kv-cache-metrics; pre-registered rule over each request's [submit, completion] window: external-hit delta
>= 50 % of prompt -> host; else local-hit delta >= 50 % -> GPU; else cold.

| concurrency | true -> inferred | accuracy |
|---|---|---|
| 1 (90 requests) | gpu -> gpu 30; host -> host 30; cold -> cold 30 | **100 %** |
| 4 (120 requests, 30 rounds) | gpu -> gpu 12, gpu -> host 32; host -> host 36; cold -> host 28, cold -> gpu 12 | **40 %** |

**H-tier: UNAMBIGUOUS at concurrency 1 (100 % >= 95 %) and DEGRADES under concurrency (40 %, 60 points lower).** At
concurrency 4 a request's window absorbs the other requests' counter changes: every host-state request is inferred
host, but so are most GPU and cold requests that share a window with one. Per-request cached tokens (API usage) are
exact (median cached fraction 0.986 GPU, 0.987 host, 0.000 cold) but do not split local vs external. TTFT by state
(concurrency 1): GPU 0.100 s, host 0.167 s, cold 2.743 s; at concurrency 4: 0.242 / 0.386 / 3.200 s.

Signals that exist in vLLM 0.31.0: prefix_cache_{queries,hits} (local), external_prefix_cache_{queries,hits},
prompt_tokens_by_source {local_compute, local_cache_hit, external_kv_transfer}, prompt_tokens_cached,
kv_offload_{store,load}_{bytes,time,size}, kv_offload_cpu_cache_{usage,read_usage,write_usage}, kv_offload_lookup_sync_
delay, num_requests_waiting_by_reason, request_num_preemptions, and with --kv-cache-metrics
kv_block_{lifetime,idle_before_evict}_seconds (sampled eviction events). **Eviction counters exist only as sampled
lifetime / idle histograms; preemption counters exist; no counter reports cached-but-unreferenced blocks** (the
kv_cache_usage gauge counts referenced blocks only). Per request, the step-level prompt-tokens-by-source (plugin)
separates local from external exactly when no other request produces its first token in the same step; on the
KV-HOST loads those plugin rows were lost (section 4), so this per-step attribution is checked in StudyENG1b instead.

## 11. Results consistency check (CLAUDE.md, six checks)

1. **Cross-check vs committed measurements.**

| quantity | this run | prior | source | ratio | agree |
|---|---|---|---|---|---|
| N=1 single-request TTFT | 0.135 s | 0.134 s | StudyD7b | 1.01 | yes |
| N=3 single-request TTFT | 0.252 s | 0.264 s | StudyD7 | 0.95 | yes |
| monolithic ~11k TTFT | 2.673 s (Part B solo) | 2.700 s | StudySLICE1 Part A | 0.99 | yes |
| 2,048-token piece on ~11k | 0.564 s | 0.486 s | StudySLICE1 Part A chain slice | 1.16 | yes (< 2x; ENG1 pieces carry 23 frames = 2,070 tokens vs SLICE1's 22-frame slices of about 1,993) |
| GPU-resident vs cold ~11k TTFT | 0.100 / 2.743 s | 0.093 escalation (A3) / 2.700 s | this study A3 / SLICE1 | 1.08 / 1.02 | yes |

No disagreement > 2x; none > 1.25x for the pre-registered k=1 cross-check.

2. **Physical plausibility.** Prefill: a lone 91-frame (8,231-token) piece takes 1.56 s of engine prefill time
including its admission step (5.3k tok/s, section 2.4), equal to StudySLICE1's 5.3k tok/s engine-only monolithic
rate; a monolithic ~11k request 2.67 s client TTFT = 4.2k tok/s end to end including about 0.5 s of front end. Host reload: 2.93 GB loaded in about 80 ms by the offloading
counter (36 GB/s) and 0.067 s TTFT over the GPU-resident case (44 GB/s over 2.93 GB): **FLAG, 2.2 to 2.8x faster
than RH6's 10 to 16 GB/s best 30-s rolling rate.** Explanation: RH6's rate is a cell average including idle time
and contention; a single pinned-memory transfer on H100 NVL PCIe Gen5 x16 (64 GB/s nominal) at 36 to 44 GB/s is
within the link's capability, and the reload's TTFT is consistent with the counter (both independent). Reported as a
flagged, explained rate; not a caching artefact (the prefix was evicted from GPU, confirmed by local hits 0 and
external hits = cached tokens).
3. **Distribution sanity.** Spreads are reported with every median (p10 to p90 in Parts B and C; residual bands for
the step model; per-cell n). No constant appears where variation is expected; Part B rho distributions are narrow
(p10 to p90 within 0.1) where the mechanism is deterministic (serial blocking behind a known remaining work) and wide
at offset 0 and 75 % where front-end timing decides the order.
4. **Definition audit.** "piece" = a prefix-chained request adding round(s / 90) D2 frames (90 tokens / frame) to a
cached prefix (SLICE1 slice = floor(n / 90) frames: 22 vs our 23 frames at 2,048); "monolithic ~11k" = a StudySLICE1
~11k session (10,923 to 11,517 prompt tokens) in a fresh namespace, max_tokens 4 (= SLICE1 Part A); "cold" = cached
tokens <= 16 on a fresh namespace / fresh uuids (= SLICE1); "host reload" = the same history after natural eviction
from the 62,944-token GPU pool, served as external hits (new in this study); "step duration" = busy interval between
output batches including the admission step (validated, section 2.4); "front-end time" = Added minus client submit.
"tier" (section 2.4) is defined here only. No name is used with two definitions.
5. **Claim linkage.** C4 (physical inertia, warm vs cold): supported and extended to the serving engine: a GPU-resident
~11k prefix answers in 0.100 s, a host-resident one in 0.167 s, a cold one in 2.743 s (27x), and the cold path also
imposes 16 to 71 s of delay on other requests while a host reload imposes about 0. C5 (joint policy beats decomposed):
not tested here; this study supplies the engine, front-end and admission models and the T0 ground truth that the
scheduler's evaluation of C5 needs. FORMULATION.md section Constraints 2 (serving feasibility, materialization on the
serving node) is the mechanism measured; nothing measured is scoped out (no cross-model KV transfer: the host tier
holds the same model's KV).
6. **Proxy validity.** (i) iteration elapsed_ms as step duration: rejected (residual wait under async scheduling,
section 2.2); replaced by busy intervals, validated within 0.3 %. (ii) Counter deltas over a request window as that
request's residency: valid at concurrency 1 (100 %), not valid under concurrency (40 %), reported as such; not used
for any other headline. (iii) Client TTFT as the scheduler's latency: it includes front-end time, which is modelled
separately (section 7). (iv) The KV-HOST iteration-log rows as a substitute for the lost plugin rows: valid for step
composition and timing (identical to the plugin on A_E0), not for per-request engine times or hit sources.

## 12. Verdicts

- **H-step: SUB-LINEAR** (0.510 N=1, 0.731 N=3, CIs below 0.8).
- **H-admit: (a) serial blocking** behind a long prefill's remaining work on E0 at every offset once the long request
  is in the engine; single-step pieces block for the rest of their step; T1 moves only the monolithic 25 % cell to
  (c) (rho 0.78). Offset-0 requests are served first because of front-end preprocessing.
- **H-tier: UNAMBIGUOUS at concurrency 1 (100 %), DEGRADES under concurrency (40 %).**
- **Engine model for the rollout:** step model (R^2 0.985, section 5) + front-end serialization (section 7) + admission
  stall (section 8) + serial admission behind remaining work (section 6). Part C FIT ground truth is in place; the
  HOLDOUT (174 triples) is recorded for T0 and untouched.
- Mechanism verification: Steps 1 to 5 PASS (section 3; recorded before the full run). Consistency check: 6 / 6
  recorded, one flagged and explained rate (host reload bandwidth).
