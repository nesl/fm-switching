# StudySLICE1: can an orchestrator slice a cold history prefill into short, prefix-chained engine units?

E-id: StudySLICE1 (`research/EXPERIMENTS.md`, pre-registered 2026-11-12). Host: h100nvl **GPU 2**, exclusive.

## 0. Question and Part A design (recorded before the Part A run)

**Question.** E10d–E10f showed that a cold history prefill is one engine unit no vLLM 0.31.0 scheduling control can split finely enough: the best setting, E10f Q1, still leaves a 0.9–1.3-s episodic tail. An append-only (D2) history has a property the engine does not use: every prefix of it is itself a valid prompt prefix. So an orchestrator above the engine can *materialize* the history as a chain of requests. Each request is the previous one's cached prefix plus the next n tokens of frames, and only the last carries the question. If each link reuses the previous prefix exactly and costs little beyond its own new tokens:
- no single engine unit is longer than about n tokens;
- the orchestrator can place the links in the gaps between episodic calls.

Part A tests whether such a chain is cheap and correct. Part B, run only if Part A passes, tests the live mixed workload.

**Server.**
- Qwen3-VL-32B-Instruct, vLLM 0.31.0 with E10c's E0 defaults: chunked prefill, 8,192-token steps, fcfs, async scheduling.
- Prefix caching ON.
- Multimodal processor cache 128 GiB.
- `--enable-log-requests` (`study_e10d_blocking.start_server("E0")`).

**Image-by-reference protocol: exactly RH7's DELTA mode, `study_rh7_eager_lazy.body7`.**
- Every image part carries a client `uuid` = `"{namespace}|{frame path}"`.
- The first request containing a frame sends its PNG bytes plus the uuid. Later requests send `{"type": "image_url", "image_url": null, "uuid": U}`, which vLLM takes from the processor cache (HTTP 400 on a miss, never a silent drop; RH7 §Path).
- Prefix-cache block keys use the uuid as the item's hash, so the KV of earlier links is reused (RH4 Part 0 / RH7 Step 0).
- vLLM 0.31.0 needed no change.

**Cache cleared.** Each monolithic repeat and each chain gets a fresh namespace: a new header tag, which changes the first text token, and new uuids. So neither the prefix cache nor the processor cache can serve anything. The run STOPs if a first request reports more than 16 cached tokens.

**Sessions.**
- RH4 / RH7 D2 histories: one 352×256 frame every 2 s (RH6 PNG fragments), ~90 tokens per frame, and a 31-token header, followed by the session's question (5 options, "Reply with only the letter").
- For each target, I took the 20 distinct sessions whose question history is closest to it:
  - 11,000 tokens → 10,831–11,191;
  - 28,000 tokens → 25,951–27,121. Only 7 sessions reach 27–29k (user decision 2A).

**Per session:**
- **Monolithic:** one cold request (header + all frames + question, temperature 0, max_tokens 4), × 5.
- **Sliced:** for n in {512, 1,024, 2,048, 4,096}, a chain.
  - Slice j = all frames so far, by reference, plus the next ⌊n / 90⌋ frames' bytes (5 / 11 / 22 / 45 frames), max_tokens 1.
  - The last slice carries the remaining frames and the question (max_tokens 4).
- Requests are strictly sequential, 0.2 s apart. Each is bracketed by `/metrics` scrapes, giving per-request deltas of vLLM's queue, prefill (scheduled → first token), engine TTFT and inference histograms.

**Per request:** client TTFT, engine queue and prefill time, prompt / cached / computed tokens, body bytes and answer letter.
- **Prefix check:** cached tokens must equal the previous link's prompt, up to the trailing reply template and 16-token block rounding. The run STOPs if the gap exceeds 32 tokens.

**Per chain:** wall time, total engine time (Σ queue + prefill), total computed tokens vs monolithic, and the final letter vs monolithic.

**Gate (pre-registered). All three must hold:**
1. Median per-slice overhead ≤ 0.10 s at n = 1,024 or 2,048. Overhead = slice engine time − slice computed tokens ÷ the session's monolithic prefill rate (computed tokens / engine time, median of 5).
2. Total chain engine time ≤ 1.25× monolithic at the same n.
3. Final letters identical to monolithic in ≥ 98 % of the 40 sessions × 4 n.

If the gate fails, the run stops after Part A and the report states which condition failed and why.

**Smoke test (2026-11-12 15:30, 1 session per target; `slice1_gate_smoke_*`, not part of the gate).**
- Letters matched monolithic in 8 / 8.
- Prefix gaps were 5–19 tokens (block rounding + reply template).
- Chain engine time vs monolithic:

  | session | monolithic | n 512 | n 1,024 | n 2,048 | n 4,096 |
  |---|---|---|---|---|---|
  | 11.2k | 2.09 s | 3.16 s | 2.32 s | 2.07 s | 1.97 s |
  | 27.2k | 6.14 s | 9.13 s | 6.74 s | 6.09 s | 5.88 s |

## 1. Mechanism verification for Part A (recorded BEFORE the Part A run)

**Step 1, causal chain.**
- FORMULATION's shared-replica cost and C4 (physical inertia grows with history): a cold recall must rebuild its history's KV, and E10d–E10f found that rebuild runs as one engine unit, blocking episodic calls for its whole ~2–6 s.
- The chain under test:
  - an append-only history can be rebuilt as k links, each a prefix-cache hit on all earlier links plus n new tokens;
  - each link's engine cost is then its n new tokens attending over the cached prefix, plus a fixed per-request cost (scheduling, API, processor-cache lookups for referenced images, the reply-template tokens recomputed each time);
  - the chain's total equals the monolithic cost plus k × that fixed cost;
  - if the fixed cost is small (≤ 0.10 s) and the total stays within 1.25× monolithic at n ≈ 1–2k, the cold rebuild becomes a sequence of short units (≈ 0.2–0.4 s each) an orchestrator can interleave with episodic calls (Part B);
  - correctness requires the final answer to be the same as monolithic.

**Step 2, instantiate each link.**

| link | implementing quantity | value / range | varies as needed? | evidence |
|---|---|---|---|---|
| prefix reuse per link | cached tokens vs the previous link's prompt | gap 5–19 tokens (smoke) | yes (cached grows with j) | usage `cached_tokens` |
| images not re-processed | body bytes per link ∝ new frames; processor-cache references | 5–45 new frames per link | yes, by n | `body_bytes` |
| new work per link | computed tokens = prompt − cached | ≈ n + template | yes, by n | usage |
| per-link fixed cost | engine time − computed / rate | smoke: chain excess 0.9–3.0 s at n 512 (25 / 61 links), ≤ 0.6 s at n ≥ 1,024 | yes, by n (number of links) | /metrics deltas |
| correctness | final letter vs monolithic | 8 / 8 equal (smoke) | — | outputs |

No link is ABSENT or CONSTANT.

**Step 3, trace one unit.** The report gives one 11k chain at n = 1,024, per link: frames sent / referenced, body bytes, prompt / cached / computed tokens, queue and prefill time, and the expected time from the rate.

**Step 4, negative control.** The monolithic request is the unsliced null. As a control for the prefix-reuse link, each chain's first link must show ≤ 16 cached tokens: cache cleared, nothing reused. A chain whose links did *not* reuse the prefix would compute about k / 2 × the history and fail the 1.25× bound.

**Step 5, alternative explanation.** A chain could match monolithic engine time while doing more work if per-link time were hidden in the API server rather than the engine, e.g. images re-decoded per link. Engine time alone would not show that, so the report also gives per-chain *wall* time and per-link body bytes. Images are re-sent only once by construction, and a re-processing cost would appear as wall − engine growing with the number of referenced frames.

## 2. Part A run (2026-11-12 15:35 → 16:23)

- **Size:** 40 sessions × (5 monolithic + 4 chains) = 200 monolithic requests and 3,062 chain links, 48 min.
- **Exclusivity:** 97 monitor samples; foreign process on GPU 2 in 0, our processes outside the job in 0. **Not VOID.** 0 request errors.
- **Prefix check:** 0 STOPs. Every first link had 0 cached tokens, and every later link reused the previous link's prompt to within **5–20 tokens**: 16-token block rounding plus the trailing reply template, which is recomputed in each link.
- **Sessions:**
  - 11k set: 10,923–11,517 prompt tokens, monolithic body 22.7 MB (median).
  - 28k set: 26,117–27,268 tokens, 55.7 MB.
  - One video appears in both sets (two different question times). The analysis keys sessions by (video, target).

**Analysis note (implementation fix).** The first analysis pass grouped by video alone, which merged that video's two sessions: 39 "sessions", spurious prefix gaps up to 4,092 and a 2.9× chain ratio. It was fixed to (video, target) before any conclusion was written. The numbers below are from the fixed pass.

## 3. Part A results

**Monolithic (median of 5 per session; median over sessions):**

| set | prompt tokens | engine (queue + prefill) | prefill rate | client TTFT |
|---|---|---|---|---|
| 11k | 10.9–11.5k | 2.06 s | 5,375 tok/s | 2.69 s |
| 28k | 26.1–27.3k | 6.11 s | 4,399 tok/s | 7.56 s |

Client TTFT includes the 23 / 56 MB body.

**Chains, medians over the 20 sessions of each set. Ratio = chain engine time ÷ monolithic engine time (range over sessions in brackets).**

| set | n | links | chain engine | ratio | longest single link (engine) | Σ link latency |
|---|---|---|---|---|---|---|
| 11k | 512 | 25 | 3.16 s | 1.51 [1.25–1.56] | 0.149 s | 4.51 s |
| 11k | 1,024 | 11 | 2.29 s | **1.11** [1.03–1.16] | **0.231 s** | 3.27 s |
| 11k | 2,048 | 6 | 2.07 s | **1.00** [0.98–1.01] | **0.394 s** | 2.78 s |
| 11k | 4,096 | 3 | 1.95 s | 0.94 [0.93–0.96] | 0.714 s | 2.63 s |
| 28k | 512 | 60 | 8.96 s | 1.47 [1.41–1.48] | 0.185 s | 13.08 s |
| 28k | 1,024 | 27 | 6.58 s | **1.09** [1.07–1.10] | **0.311 s** | 9.28 s |
| 28k | 2,048 | 14 | 6.02 s | **0.99** [0.98–1.00] | **0.553 s** | 7.80 s |
| 28k | 4,096 | 7 | 5.76 s | 0.94 [0.94–0.95] | 1.060 s | 7.35 s |

- "Σ link latency" is the client-side sum, excluding the harness's 0.2-s pauses and /metrics scrapes. It compares with monolithic client TTFT of 2.69 s (11k) and 7.56 s (28k).
- Computed tokens per chain vs monolithic (median): 1.027× (512), 1.012× (1,024), 1.005× (2,048), 1.003× (4,096). The extra is the reply template recomputed per link plus block rounding.

**Gate.**

| condition | n = 1,024 | n = 2,048 | threshold | pass? |
|---|---|---|---|---|
| median per-slice overhead (all links, both sets) | **0.015 s** (p10 −0.034, p90 0.068) | **−0.004 s** (p10 −0.101, p90 0.084) | ≤ 0.10 s | yes / yes |
| median chain / monolithic engine time | **1.093** (max 1.159; 40 / 40 ≤ 1.25) | **0.990** (max 1.008; 40 / 40 ≤ 1.25) | ≤ 1.25 | yes / yes |
| final letter = monolithic (all n) | — | — | ≥ 98 % | **158 / 160 = 98.75 %**, yes |

Other slice sizes, for reference:
- n = 512: overhead 0.044 s, ratio 1.48. That fails the cost bound, because 25–60 links × about 0.04 s add up.
- n = 4,096: ratio 0.94, but its longest link is 0.7–1.1 s.

**Letters.** Both mismatches are one 11k session (`762144796185953…`) whose *monolithic* answer is itself unstable across its 5 repeats (A, C, C, C, C). Its chains gave C / A / C / A against the reference (repeat 0) A. Measured against that session's majority letter C, the count would still be 158 / 160. All other 39 sessions: 5 / 5 monolithic repeats agree, and all 4 chains equal them.

**Why the overhead can be negative.** Overhead is measured against the session's *average* monolithic rate. Early links attend over a short prefix and so run faster than that average; late links run slower. The chain's total (the ratio) is the position-independent measure, and at n ≥ 2,048 it is at or below 1.0.

**Step 3 trace: one 11k chain, n = 1,024** (`1319837272968317…`, 11,159 tokens; monolithic engine 2.080 s, rate 5,364 tok/s).

| link | new frames | body MB | prompt | cached | computed | queue | prefill | expected (computed / rate) |
|---|---|---|---|---|---|---|---|---|
| 0 | 11 | 2.71 | 1,029 | 0 | 1,029 | 0.000 | 0.216 | 0.192 |
| 1 | 11 | 2.57 | 2,019 | 1,024 | 995 | 0.000 | 0.176 | 0.186 |
| 2 | 11 | 2.41 | 3,009 | 2,000 | 1,009 | 0.000 | 0.181 | 0.188 |
| 5 | 11 | 2.49 | 5,979 | 4,976 | 1,003 | 0.000 | 0.199 | 0.187 |
| 8 | 11 | 2.30 | 8,949 | 7,952 | 997 | 0.000 | 0.227 | 0.186 |
| 10 | 11 | 2.68 | 10,929 | 9,920 | 1,009 | 0.000 | 0.225 | 0.188 |
| 11 (question) | 1 | 0.24 | 11,159 | 10,912 | 247 | 0.000 | 0.104 | 0.046 |
| chain | 111 | 28.1 | — | — | 11,296 (1.012×) | — | **2.338 s (1.124×)** | — |

Links 3, 4, 6, 7 and 9 are similar and omitted.
- Bound: nothing (idle server, sequential).
- Each link costs about 1,000 new tokens attending over a growing cached prefix: 0.18 s near the start rising to 0.23 s at 10k, against a flat 0.19 s from the average rate.
- The final link carries the question: 247 tokens in 0.10 s, i.e. about 0.06 s fixed cost.
- Answer E = monolithic E.

**Part A verdict: GATE PASSED at both n = 1,024 and n = 2,048.**
- An append-only D2 history can be rebuilt as a prefix-chained sequence of requests through vLLM 0.31.0's ordinary API, with the RH7 uuid protocol and no engine change.
- Every link reuses the previous prefix exactly (up to block rounding).
- Engine work rises only 1–9 %, and per-link overhead is about 0.01–0.02 s.
- The answer is unchanged in 158 / 160 (both mismatches are a session whose monolithic answer is itself unstable).
- The longest engine unit falls from 2.1 / 6.1 s (monolithic) to 0.23–0.31 s (n = 1,024) or 0.39–0.55 s (n = 2,048).

Part B, the live mixed test, is designed in §0 of the EXPERIMENTS row. It waits for the user's decisions on the cold-recall history size and the scale, because its full grid exceeds the 5-h limit.

## 4. Part A consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | D2 cold prefill, ~10.9k tokens | 2.06 s engine (11k set) | 2.23 s (10,845 tok) | RH4 report (H100, vLLM) | 0.92 | yes |
   | D2 cold prefill, ~26k tokens | 6.11 s engine (26.1–27.3k) | 6.57 s (25,824 tok) | RH4 report | 0.93 | yes |
   | prefix reuse on an append | cached = previous prompt − 5..20 | 24,320 cached of 24,474 (−154 incl. question / template) | RH4 Part 0 | — | yes (same mechanism, finer here) |
   | tokens per D2 frame | 90 (≈ 990 per 11 frames + template) | 90 | RH4 / RH7 | 1.00 | yes |
   | uuid reference protocol | 0 cache misses, first-link cached 0 | 0 silent drops, HTTP 400 on a miss | RH7 Step 0 | — | yes |

2. **Physical plausibility.** PASS.
   - The monolithic rate is 5.4k tok/s at 11k and 4.4k tok/s at 27k (falling with context, as attention grows), consistent with E10d's 5.8k tok/s text-only 12.6k prefill.
   - Per-link rates are 4.5–5.8k tok/s.
   - No link is faster than the curve: its time is set by new tokens over a cached prefix, and computed tokens are counted from vLLM's own usage.
3. **Distribution sanity.** PASS.
   - Ratios are given with min–max per set.
   - Overhead is given with p10 / p90.
   - Monolithic repeats vary (e.g. 2.07–2.20 s).
   - No constants where distributions are expected. The prefix gap ranges over 5–20, not a constant.
4. **Definition audit.** PASS.
   - "Monolithic" = one cold request with a fresh namespace.
   - "Slice / link" = all frames so far by reference plus ⌊n / 90⌋ new frames.
   - "Engine time" = vLLM `request_queue_time` + `request_prefill_time` (scheduled → first token), per-request histogram deltas with requests strictly sequential.
   - "Overhead" and the gate are as pre-registered.
   - D2 representation = RH4 / RH7 (one 352×256 frame every 2 s, header, question text).
5. **Claim linkage.**
   - FORMULATION C4 (physical inertia grows with history) and the shared-replica cost.
   - Part A **supports** the premise that the inertia need not be paid as one unsplittable unit: rebuilding history can be broken into ≈ 0.2–0.5-s units at ≤ 9 % extra engine work, using only the API.
   - It does not yet speak to capacity; that is Part B.
6. **Proxy validity.**
   - Engine time from /metrics histogram deltas is valid only for sequential requests, which they are here (a single client, each request awaited).
   - Client latency is reported beside it.
   - Letter equality is a proxy for "same answer": valid for these 5-option, letter-only questions. Instability in the monolithic answer itself is reported separately.

**Result: PASS 6 / 6.**

## 5. Part B design (recorded before the Part B run)

**User decisions (2026-11-12):**
1. The cold recall is the ~11k D2 history, comparable to the 12.6k cold K1 recall in E10b–f.
2. The ~28k set is moot. Any future 28k cell would use the same 20 Part A sessions.
3. Default engine (E0) only, all six policies. Run order:
   1. C1 r = 0.05 (C1a), all policies;
   2. C4, all policies;
   3. C0 at 25 % and 40 % (controls);
   4. C1 r = 0.1 (C1b).
   P0 runs first within each condition. Once 5 h have elapsed, finish the current cell and stop to ask.

**Harness:** `experiments/cost/study_slice1_live.py`. It is the E10c / E10e `study_e10b_mixed.run_cell`, imported unchanged:
- episodic N = 1, open loop over distinct D14 requests, D7 Poisson arrivals, E10c's seed-index map;
- 30-s discard, 240-s scored window, 300-s drain cap;
- RH7 warm sessions for C4 (k = 8, KV-HOST 256 GiB);
- exclusivity monitor with VOID on overlap;
- a fresh server per cell. The server is vLLM 0.31.0 defaults (E0), prefix caching ON, processor cache 128 GiB. The server's "non-default args" line is checked to contain no scheduler flags.

Only the cold-recall path changes. Cold arrivals (Poisson at r, seed 1000 + level index) are handed to an orchestrator client instead of being posted directly.

**Cold recall:**
- One of the 20 Part A ~11k sessions (10,923–11,517 prompt tokens), taken in `random.Random(0)` order.
- Every recall uses a fresh namespace (new header tag and new frame uuids), so nothing is served from the prefix or processor cache. This is checked per cell: a recall's first request must have ≤ 16 cached tokens, and each later slice must leave a gap of ≤ 32 tokens to its prefix; otherwise STOP.
- Reference answer: the Part A monolithic letter (majority of 5).
- Time to answer is measured from the scheduled arrival to the first answer token. Deadlines are 5 s and 10 s.
- Predicted engine time = computed tokens ÷ the session's Part A monolithic prefill rate (5,307–5,419 tok/s).

**Policies.** Episodic calls are never delayed by any policy. The episodic arrival schedule is known to the orchestrator (devices declare their call times). Warm C4 traffic passes through.

| policy | cold request form | admission and dispatch rule |
|---|---|---|
| P0 | monolithic | posted at arrival (= E10c / E10e) |
| P1 | monolithic | EDF queue (deadline = arrival + 10 s), at most one cold request in the engine at a time |
| P2 | monolithic | P1, and the head request is held while any episodic call is due within its predicted engine time (~2.05 s). It is released anyway once its slack is exhausted (now + predicted ≥ deadline). |
| P3_1024 / P3_2048 | prefix-chained slices, n // 90 frames each (11–12 or 6 slices) | P1 queue. Each slice is sent after the previous slice finished. If an episodic call is due within the slice's predicted time (~0.19 / 0.38 s), the slice waits until 5 ms after that call's dispatch; otherwise it goes immediately. |
| P4 | P3_2048 (n = 2,048: Part A's best by cost, chain / monolithic 0.990, overhead −0.004 s) | Each slice is held while any episodic call is due within its predicted time. Once the recall's slack is exhausted (now + predicted remaining chain time ≥ deadline), the remaining slices go back-to-back. |

**Measured per cell:**
- Episodic p50 / p90 / p99 TTFT from the scheduled arrival. Capacity is the highest ladder level (10 / 20 / 25 / 30 / 40 % of 15.1 req/s) with p99 ≤ 0.45 s and no errors, found bottom-up and stopping at the first failure.
- Per cold recall: time to answer, meets 5 s / 10 s, letter vs reference, computed tokens (GPU work), slices, hold time and release reason.
- The 1-s /metrics timeline.

**Decision (pre-registered, unchanged):** slicing restores capacity if P3 or P4's C1 capacity is within one level of C0's and ≥ 90 % of their recalls meet the 10-s deadline. The rule is applied at C1a (primary) and at C1b. P2 is reported against the same rule. C0 is measured at 25 / 40 %; E10e found C0 capacity at the 40 % ladder top, so "within one level" means C1 capacity ≥ 30 %.

## 6. Mechanism verification for Part B (recorded BEFORE the Part B sweep)

**Step 1, the causal chain.** E10d–f established the chain:
1. A cold history prefill is one long engine unit (~2.05 s for ~11k tokens on E0).
2. Episodic calls arriving while it runs wait behind its steps.
3. Episodic p99 then exceeds 0.45 s at every load level, so C1 capacity falls below 10 % against 40 % at C0.

This bears on FORMULATION's reconstruction cost: the physical component of Context Inertia, the cost of rebuilding state on the serving tier, charged to a shared accelerator. Part A showed the unit can be cut into short prefix-chained pieces at ≤ 10 % extra cost. The claim under test is that if the orchestrator dispatches those short pieces only around the episodic calls, each episodic call waits at most one short slice step rather than the whole prefill, so p99 stays within budget at higher load. The recall still finishes, with an answer time set by the extra links and holds.

**Step 2, link instantiation.** These are planned quantities; observed values are filled in after the smoke run.

| causal link | implementing quantity | expected value / range | varies as expected? | evidence (to fill) |
|---|---|---|---|---|
| cold unit length | longest engine unit per recall | ~2.05 s (P0–P2) vs ~0.2 / ~0.4 s (P3 / P4) | must differ by policy | Part A per-link engine times; Part B slice rows |
| orchestrator acts | hold time and release reason per recall or slice | 0 for P0; > 0 for P2 / P3 / P4 | must be non-zero for P2–P4 | slice rows `held_s`, `released_by` |
| prefix reuse under load | cached tokens per slice vs previous prompt | gap ≤ 32 | constant small gap required | per-cell STOP check |
| episodic waiting | episodic p99 | > 0.45 s for P0 at C1 (E10e: 2.65 s) | must fall for P3 / P4 if the claim holds | cell summaries |
| recall cost | time to answer, computed tokens | ~2.5–4 s P0; longer for holds and chains | measured | cold rows |

**Step 3, trace.** One P4 recall from the smoke run will be traced slice by slice: send time, hold, release reason, prompt / cached / computed tokens, TTFT, and the episodic calls dispatched around it.

**Step 4, negative control.** P0 is the mechanism-off control within every condition: the same cold work arrives monolithic and unheld. In addition, C0 has no cold work at all. If P3 / P4 did not change episodic p99 relative to P0, the slicing mechanism would not be acting.

**Step 5, alternative explanation.** An improvement under P3 / P4 could come from serializing cold work and delaying it (also done by P1 / P2) rather than from slicing. P1 and P2 isolate that: each has the same queue and P2 the same gap-holding, but with a monolithic unit. A capacity gain over P2 is attributable to slicing. A second alternative is that cold recalls are simply postponed beyond the window. That is detected by the drain-time unanswered count and by the time-to-answer distribution.

### 6a. Part B smoke run (18:15 → 18:24; recorded before the sweep)

**Setup:** C1 r = 0.1, 10 % load (1.51 req/s), 60-s window (first 10 s discarded), one fresh E0 server per policy. Files: `results/cost/study_slice1/slice1_live_smoke_*`.

| policy | episodic p99 (s) | meets 0.45 s | recalls in window | met 10 s | met 5 s | letters = ref |
|---|---|---|---|---|---|---|
| P0 | 3.670 | no | 4 | 4 | 4 | 4 |
| P2 | 2.291 | no | 4 | 3 | 1 | 4 |
| P3_1024 | 0.396 | yes | 4 | 4 | 3 | 4 |
| P4 | 0.201 | yes | 4 | 4 | 3 | 4 |

Every link is instantiated and varies by policy as Step 2 requires:

- **Cold unit length:** P0 / P2 send one ~11k-token request. In P3 / P4, each slice is one ~1–2k-token request taking 0.35–0.56 s of client latency.
- **Orchestrator acts:**
  - P0 holds are 0.
  - P2 holds the request 0.6–7.9 s, and two recalls were released by `slack`.
  - P4 holds 0–0.58 s, every release by `gap`.
- **Prefix reuse under load:** first-request cached tokens were 0 in every recall. The largest gap between a link's cached tokens and the previous prompt was 20 tokens, below the 32-token STOP threshold.
- **Episodic waiting:** p99 falls from 3.67 s (P0) to 0.40 / 0.20 s (P3 / P4).

**Step 3 trace: P4 recall S1B24.**
- Session 115609519270, 11,028 prompt tokens, scheduled at t = 13.818 s, reference letter A.
- 6 slices, sent back-to-back because each one found a gap.

| slice | sent at (s after arrival) | held (s) | predicted engine (s) | prompt tokens | cached tokens | computed | client latency (s) |
|---|---|---|---|---|---|---|---|
| 0 | 0.001 | 0 | 0.375 | 2,021 | 0 | 2,021 | 0.454 |
| 1 | 0.455 | 0 | 0.369 | 4,001 | 2,016 | 1,985 | 0.460 |
| 2 | 0.916 | 0 | 0.369 | 5,981 | 3,984 | 1,997 | 0.487 |
| 3 | 1.403 | 0 | 0.369 | 7,961 | 5,968 | 1,993 | 0.522 |
| 4 | 1.925 | 0 | 0.369 | 9,941 | 7,952 | 1,989 | 0.565 |
| 5 (question) | 2.490 | 0 | 0.168 | 11,028 | 9,936 | 1,092 | 0.355 (answer A) |

- **Outcome:** answered at 2.844 s, meeting both deadlines; computed tokens 11,077 (1.004× the prompt).
- **Episodic calls during the recall:** scheduled at +1.88, +2.46 and +3.24 s, with TTFTs of 0.212, 0.137 and 0.134 s, all within budget.
- **Binding constraint:** none. The orchestrator never had to hold a slice.

**Implementation fix after the smoke run (before the sweep): slack guard.** P2 released its slack-exhausted recalls at deadline − predicted engine time. Client time to answer is longer than engine time (request transfer and image processing), so those recalls missed 10 s by ~0.8 s (10.82 / 10.92 s). The guard now predicts time to answer as predicted engine time × Part A's largest client-latency / engine-time ratio, plus 0.25 s for load. The ratios are 1.321 for monolithic (range 1.276–1.321) and 1.373 for the n = 2,048 chain (range 1.307–1.373). The window that checks for a blocking episodic call still uses predicted engine time. The smoke rows above predate the fix; the P2 / P4 hold rule is otherwise unchanged.

## 7. Part B run (2026-11-12 18:25 → 21:15)

- **Scale:** 28 cells on 28 fresh E0 servers, h100nvl GPU 2, 4 h 50 min (inside the 5-h guard).
- **Status:** not VOID; every server's "non-default args" line showed no scheduler flags; 0 cold-recall errors and 0 unfinished.
- **Cache checks:** every recall started cold (first-request cached tokens 0). The largest gap between a link's cached tokens and the previous prompt was 20 tokens; Part A saw 5–20.
- **Files:** `results/cost/study_slice1/slice1_live_{requests,slices,metrics,cpu,monitor}_h100nvl.jsonl`, `slice1_live_run_meta_h100nvl.json`, `slice1_live_results.json` (from `study_slice1_live_analyse.py`).

## 8. Part B results

### 8.1 Episodic capacity

Episodic N = 1, p99 TTFT ≤ 0.45 s from the scheduled arrival. Each cell shows episodic p99 in seconds; ✗ = over budget; – = not run because the ladder stops at the first failure.

| condition | policy | 10 % | 20 % | 25 % | 30 % | 40 % | capacity |
|---|---|---|---|---|---|---|---|
| C0 (no cold) | P0 | – | – | 0.272 | – | 0.391 | **40 %** (ladder top; E10e: 40 %) |
| C1 r 0.05 | P0 pass-through | 3.049 ✗ | | | | | < 10 % |
| | P1 EDF | 2.809 ✗ | | | | | < 10 % |
| | P2 blocking-aware | 2.501 ✗ | | | | | < 10 % |
| | P3_1024 | 0.397 | 0.460 ✗ | | | | 10 % |
| | P3_2048 | 0.555 ✗ | | | | | < 10 % |
| | **P4** | 0.244 | 0.397 | 0.341 | 0.357 | 0.516 ✗ | **30 %** |
| C1 r 0.1 | P0 | 4.328 ✗ | | | | | < 10 % |
| | P1 | 2.847 ✗ | | | | | < 10 % |
| | P2 | 2.772 ✗ | | | | | < 10 % |
| | P3_1024 | 0.424 | 0.473 ✗ | | | | 10 % |
| | P3_2048 | 0.583 ✗ | | | | | < 10 % |
| | **P4** | 0.263 | 0.355 | 0.619 ✗ | | | **20 %** |
| C4 (k 8 warm + r 0.1) | P0 | 4.458 ✗ | | | | | < 10 % |
| | P1 | 3.179 ✗ | | | | | < 10 % |
| | P2 | 3.021 ✗ | | | | | < 10 % |
| | P3_1024 | 0.488 ✗ | | | | | < 10 % |
| | P3_2048 | 0.645 ✗ | | | | | < 10 % |
| | P4 | 0.531 ✗ | | | | | < 10 % |

Episodic p50 is 0.145–0.17 s in every cell. Every policy leaves the median alone; only the tail differs.

### 8.2 Cold recalls

Time to answer is measured from the scheduled arrival, over all scored-window recalls of each ladder, failing cell included.

| condition | policy | recalls | answer time p50 / p90 (s) | meet 10 s | meet 5 s | 10 s within capacity cells | letters = Part A |
|---|---|---|---|---|---|---|---|
| C1 r 0.05 | P0 | 11 | 2.97 / 3.77 | 100 % | 100 % | – | 10 / 11 |
| | P1 | 11 | 2.92 / 4.59 | 100 % | 100 % | – | 10 / 11 |
| | P2 | 11 | 9.83 / 9.96 | 90.9 % | 36.4 % | – | 11 / 11 |
| | P3_1024 | 21 | 4.09 / 4.62 | 100 % | 90.5 % | 11 / 11 | 20 / 21 |
| | P3_2048 | 11 | 3.40 / 5.45 | 100 % | 81.8 % | – | 11 / 11 |
| | **P4** | 54 | 6.14 / 9.46 | **94.4 %** | 37.0 % | **41 / 41** | 54 / 54 |
| C1 r 0.1 | P0 | 26 | 2.89 / 3.93 | 100 % | 96.2 % | – | 26 / 26 |
| | P1 | 26 | 2.90 / 4.66 | 100 % | 88.5 % | – | 26 / 26 |
| | P2 | 26 | 9.95 / 10.84 | 73.1 % | 11.5 % | – | 26 / 26 |
| | P3_1024 | 48 | 4.27 / 7.14 | 100 % | 72.9 % | 26 / 26 | 48 / 48 |
| | P3_2048 | 26 | 3.58 / 5.75 | 100 % | 76.9 % | – | 26 / 26 |
| | **P4** | 76 | 5.72 / 10.39 | **84.2 %** | 42.1 % | 48 / 48 | 76 / 76 |
| C4 | P0 | 26 | 3.02 / 4.11 | 100 % | 92.3 % | – | 26 / 26 |
| | P1 | 26 | 3.03 / 4.93 | 100 % | 88.5 % | – | 26 / 26 |
| | P2 | 26 | 10.02 / 11.21 | 46.2 % | 11.5 % | – | 26 / 26 |
| | P3_1024 | 26 | 4.53 / 7.69 | 100 % | 61.5 % | – | 25 / 26 |
| | P3_2048 | 26 | 3.84 / 7.05 | 100 % | 73.1 % | – | 26 / 26 |
| | P4 | 26 | 4.42 / 7.73 | 100 % | 65.4 % | – | 26 / 26 |

**Answers.** 4 of 503 letters differ from the reference, all from session 762144796185, whose Part A monolithic answers were themselves A C C C C. Every other recall matches.

**GPU work.** Computed tokens per recall over prompt tokens, median: 1.000 for monolithic, 1.0048 for n = 2,048 chains and 1.0112 for n = 1,024, the same as Part A's 1.005 / 1.012. Slicing adds ≈ 0.5–1 % prefill work.

### 8.3 Why each policy behaves as it does

- **P0 / P1.** The ~11k monolithic prefill (one ~2-s engine unit) blocks every episodic call that arrives during it, exactly as in E10c–f. EDF admission (P1) only serializes cold requests, and at r ≤ 0.1 they rarely overlap. It changes nothing.
- **P2, blocking-aware but monolithic.** It holds the request (median 0.9–3.2 s) for a ~2.05-s gap in the episodic schedule. Even at 1.5 req/s such gaps are rare, so most recalls are released by `slack` (6 of 11, 18 of 26 and 19 of 26 at C1a, C1b and C4). The ~2-s unit then runs anyway. Episodic p99 only falls from 3.0–4.5 to 2.5–3.0 s, and recalls lose their deadline margin: 46–91 % meet 10 s. Blocking-aware admission without slicing cannot restore capacity: it can only move the long unit, not shorten it.
- **P3_1024 vs P3_2048, sliced and aligned but not held.** An episodic call that lands behind a slice waits up to one slice's engine time: ~0.2 s at 1,024, or ~0.4–0.55 s at 2,048. At 2,048 that alone exceeds the budget's headroom over the ~0.15-s episodic service time, so P3_2048 fails at 10 %. P3_1024 passes 10 % but not 20 %, where more arrivals land behind slices.
- **P4, n 2,048 slices plus the gap-hold guard.** Each slice waits until no episodic call is due within its predicted ~0.37 s.
  - Up to the capacity level, every release in every cell was by `gap` (66 / 60 / 60 / 60 at C1a 10–30 %; 156 / 132 at C1b 10–20 %). The orchestrator never had to force a slice, and episodic p99 stayed at 0.24–0.40 s.
  - Holding costs answer time: median 3.4 s at 10 % rising to 8.2 s at 30 % (C1a).
  - The failing levels coincide with the guard firing. At C1a 40 %, 14 slices were released by `slack`, and 19 of the 28 over-budget episodic calls overlapped a cold slice. At C1b 25 %, 62 slices were released by `slack`, all 54 over-budget calls overlapped a slice, and 12 of 28 recalls missed 10 s.
  - Capacity is reached where the gaps needed to fit a recall's slices before its deadline no longer exist.
- **C4.** Every policy is below 10 %, P4 included (0.531 s). Of the 8 over-budget episodic calls in the P4 cell, 7 overlapped both a cold slice and an in-flight warm request (computed tokens > 200). The other one overlapped a cold slice only. For P3_1024 the count is 10 of 10 overlapping both. The 8 warm sessions' appends and escalations pass through the orchestrator unmanaged by design. They are themselves multi-frame prefills, so they add the long units that slicing removes from the cold path. Combined with the sliced cold path, they push the tail just over budget (P4 0.531 vs P0 4.458 s).

## 9. Part B decision (pre-registered rule)

The rule: a policy restores capacity if its C1 capacity is within one ladder level of C0's (40 %, so ≥ 30 %) AND ≥ 90 % of its recalls meet 10 s.

| C1 | P2 | P3_1024 | P3_2048 | P4 | slicing restores capacity? |
|---|---|---|---|---|---|
| r 0.05 (C1a, primary) | < 10 %, 90.9 % → no | 10 %, 100 % → no | < 10 %, 100 % → no | **30 %, 94.4 % → YES** | **YES (P4)** |
| r 0.1 (C1b) | < 10 %, 73.1 % → no | 10 %, 100 % → no | < 10 %, 100 % → no | 20 %, 84.2 % → no | **NO** |

P4's 10-s fraction counts every recall of the ladder, including the failing top cell. Within its passing cells it is 41 / 41 at C1a and 48 / 48 at C1b.

**Verdict.**
- At the primary cold rate (r = 0.05 / s), slicing the cold D2 history and dispatching the slices in the gaps between episodic calls (P4) raises episodic capacity from < 10 % to 30 % of peak. That is within one level of the no-cold capacity of 40 %, while 94 % of recalls are answered within 10 s with the monolithic answer. **Slicing restores capacity under the pre-registered rule.**
- At double the cold rate (r = 0.1 / s), P4 reaches 20 %, two levels below C0. Restoration is partial and does not meet the rule.
- With 8 warm sessions passing through unmanaged (C4), no policy reaches 10 %.
- Both ingredients are needed:
  - Slicing without holding (P3) gives 10 % at best.
  - Holding without slicing (P2) gives < 10 % and does not meet the rule.
  - Only short units combined with gap-aware dispatch do.
- The price is recall latency: median time to answer rises from ~2.9 s (P0) to 3.4–8.2 s across P4's passing cells, and only 37–42 % of recalls meet 5 s.

**Mechanism classification.** All Step 2 links were present and varied as expected, and P0 acted as the negative control (§6a and §8.3):
- the longest cold unit falls from ~2 s to ≤ 0.55 s;
- holds and their release reasons are non-zero only for P2 / P4;
- prefix reuse holds under load;
- episodic p99 tracks the policy.

The C1a result is a positive finding. The C1b and C4 shortfalls are **real negatives at those loads**, not design failures: the mechanism operated (P4 released by `gap` until capacity), and it ran out of gaps (C1b) or met an unmanaged second source of long units (C4).

## 10. Part B consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | C0 N1 25 % episodic p99 | 0.272 s | 0.271 s | E10e P0 | 1.01 | yes |
   | C0 N1 40 % episodic p99 | 0.391 s | 0.383 s | E10e P0 | 1.02 | yes |
   | C1 r 0.05, 10 %, P0 episodic p99 | 3.049 s | 2.646 s | E10e P0 (K1 video 12.6k cold) | 1.15 | yes (different cold body) |
   | C4 10 %, P0 episodic p99 | 4.458 s | 4.710 s | E10e P0 | 0.95 | yes |
   | P0 cold time to answer under C1 load, p50 | 2.97 s | 2.69 s idle | Part A monolithic TTFT (11k) | 1.10 | yes (load adds queueing) |
   | chain computed / prompt | 1.0048 / 1.0112 | 1.005 / 1.012 | Part A | 1.00 | yes |
   | link prefix gap | ≤ 20 tokens | 5–20 | Part A | – | yes |

2. **Physical plausibility.** PASS.
   - The P0 cold recall implies ≈ 11.1k tokens / 2.97 s ≈ 3.8k tok/s client-side. The engine-side rate is 5.3–5.4k tok/s (Part A), and RH4 / E10d measured 5.4–5.8k.
   - No recall or slice is faster than the committed curve.
   - P4's longer answer times are holds, recorded per slice (`held_s`), not faster or slower compute.
3. **Distribution sanity.** PASS.
   - Answer time is given as p50 / p90 with per-cell medians and maxima (§8.3).
   - Episodic p99 differs in every cell (0.244–4.458 s).
   - Hold times and release counts vary by load.
   - No constants appear where distributions are expected.
4. **Definition audit.** PASS, with one flagged difference.
   - Capacity, the ladder, the 0.45-s budget, C0 / C1 / C4, seeds, the 30-s discard, the 240-s window and the drain cap are identical to E10c / E10e.
   - **Flagged:** the cold recall is the ~11k D2 history (RH7 image-by-reference PNG frames, 10,923–11,517 tokens), not E10b–f's K1 RICH video (12.6k). This was a user decision, made because D2 is append-only and therefore sliceable. P0 reproduces E10e's C1 / C4 failures with it (rows 3–4 above).
   - "Time to answer" runs from the scheduled arrival to the first answer token. For chains, that is the final link's first token.
5. **Claim linkage.**
   - FORMULATION's physical component of Context Inertia (reconstruction cost grows with history) and the timing dimension of the joint placement × timing policy.
   - Part B **supports** the claim that reconstruction timing is a lever. The same reconstruction work (+0.5 % tokens), cut into short units and timed into episodic gaps, recovers most of the shared replica's episodic capacity at r = 0.05.
   - It **weakens** any claim that this holds at higher cold rates or with unmanaged warm traffic (C1b, C4).
   - It does not speak to representation choice: every recall was full history.
6. **Proxy validity.**
   - **Known schedule:** the orchestrator knows the episodic arrival schedule. This stands in for devices declaring their call cadence. It is valid for periodic sensing, but optimistic for bursty or unannounced calls, and that is a limitation of the P2 / P4 result.
   - **Letters:** letter equality stands in for "same answer" (see Part A).
   - **Prediction:** predicted engine time comes from Part A's idle prefill rate per session. Under load slices run slower, which the slack guard absorbs with a margin. The hold rule's window does not, so P4's capacity is a lower bound for a load-aware predictor.

**Result: PASS 6 / 6** (check 4 records the flagged cold-body difference; check 6 records the known-schedule limitation).
