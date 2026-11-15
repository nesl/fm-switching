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

## 11. Part C design (recorded before the Part C run)

**Question.** Part B's P4 restored episodic capacity at C1a (30 % vs < 10 % for P0), but at C4 (KV-HOST k = 8 warm sessions + cold r = 0.1) every policy stayed below 10 % (P4 p99 at 10 %: 0.531 s). In that cell 7 of the 8 over-budget episodic calls overlapped both a cold slice and an in-flight warm request, and warm appends and escalations passed through unmanaged. Does managing warm traffic the way P4 manages cold slices (defer the deferrable, gap-align the latency-sensitive) restore episodic capacity when warm sessions and cold recall coexist, without breaking recall deadlines? Prior: StudyE10c measured warm-only C2 capacity at 30 % (N = 1, E0); StudySIM1b found KV-HOST adds about 0.04 s per request at N = 1, and that an episodic request overlapping any in-flight warm request pays about 0.05 to 0.07 s.

**Harness.** `experiments/cost/study_slice1_partc.py` on top of Part B's `study_slice1_live.py` (cold path, orchestrator, server start, sanity checks) and `study_e10b_mixed.run_cell`. Everything Part B fixed is unchanged: E0 server config (vLLM 0.31.0 defaults, prefix caching ON, processor cache 128 GiB, E10d logging flags, KV-HOST = native offloading 256 GiB), a fresh server per cell, episodic N = 1 open loop over distinct D14 requests, E10c's seed-index map, cold seeds 1000 + level index, 30-s discard, 240-s scored window, 300-s drain cap, ladder 10 / 20 / 25 / 30 / 40 % of 15.1 req/s bottom-up with stop at first failure, p99 budget 0.45 s, cold sessions and order, fresh cold namespaces, deadlines 5 / 10 s, exclusivity monitor with VOID on overlap, "non-default args" check. The warm plan is RH7's (H.plan(8, 0), eager delta bodies, appends every 10 s of session time, every question escalated, 1x real time), identical in every cell.

**Hook.** `study_e10b_mixed.py` gains one module variable `WARM_DEVICE = None`; `run_cell` calls `(WARM_DEVICE or R6.device)` where it called `R6.device`. With the default `None` the call is the same function with the same arguments, so E10b to E10f and Part B are unchanged (diff recorded in §12). Part C sets it only for P5 cells.

**Letters on warm requests.** Part C records each warm request's output text (needed for escalation letters) by running a copy of `R7.Cell.post` that additionally accumulates the streamed content and sets an optional "submitted" event just before the HTTP request. Request bodies, kinds and order are unchanged. It is used in every Part C cell (P0, P4, P5, P4_1024), so reference and treatment are measured the same way.

**Policies.**

| policy | cold path | warm path |
|---|---|---|
| P0 | monolithic, posted at arrival (Part B P0) | pass-through (hook off) |
| P4 | Part B P4 unchanged (2,048-token prefix-chained slices, EDF, one cold request at a time, each slice held while an episodic call is due within its predicted time, back-to-back once slack is exhausted; slack guard x 1.373 + 0.25 s) | pass-through (hook off) |
| P5 | identical to P4 | managed (below) |
| P4_1024 | P4 logic with 1,024-token slices (Part A chain); slack guard factor 1.467 = Part A's largest client-latency / engine-time ratio for n = 1,024 over the 20 ~11k sessions (range 1.387 to 1.467; same definition gives 1.373 for n = 2,048 and 1.321 monolithic) | pass-through (hook off) |

P5 warm management, per session (device, session index):
- **recall_warmup:** pass-through unchanged; it runs before the window (run_cell awaits all warm-ups before the window starts). The count of warm-ups still in flight inside the scored window is reported (expected 0 by construction).
- **recall_append (deferrable):** held while any episodic call is due within its predicted time; released on a gap ("gap"). Coalescing: if a later append of the same session becomes due while an earlier one is still held, the earlier one is dropped (the later append's delta body carries all frames not yet dispatched, because the dropped request never updates the session's dispatched state). Forced releases, back to back: (a) when an escalation for that session is dispatched, the session's pending append is flushed first, then the escalation ("flush_for_escalation"); (b) when the session's next scheduled append is due ("next_append_due"). With coalescing ON, (b) is superseded by the drop (the held append is replaced, not released); (b) acts only in the coalescing-OFF cell (Step 5), where the earlier append is released when the next one is due.
- **recall_escalation (latency-sensitive):** gap-aligned only, like P3: if an episodic call is due within its predicted time, dispatched 5 ms after that call's dispatch, otherwise immediately; never held longer.
- **Ordering:** within one session each warm request is submitted only after the previous one has been submitted (not completed), so a delta body never references frames that a still-unsent request carries. Episodic calls are never delayed.
- **Predicted warm time (committed data only, fitted before the run):** service TTFT from submit of StudyE10c's E0 C2 10 % appends (KV-HOST k = 8, no cold, in-window, n = 189): t = 0.1273 + 0.000390 x new tokens (OLS; R^2 0.12, residual p10 / p90 -0.093 / +0.106 s; most appends carry 5 frames). New tokens before dispatch: appends 10.6 + 90.3 x frames not yet dispatched; escalations 142.8 + 91.2 x frames not yet dispatched (includes the question; fitted on E10c E0 C2 10 % rows). A 5-frame append predicts 0.308 s; a 10-frame coalesced append 0.484 s. Nothing is fitted on Part C data.

**Conditions and order** (E0; fresh server per cell; reference first in each condition):
0. Smoke: C4a P5 at 10 %, 60-s window (first 10 s discarded), separate `slice1_partc_smoke_*` files, recorded with the mechanism verification (§12) before the sweep.
1. **C4a** = KV-HOST k = 8 + cold r = 0.05 [PRIMARY]: P0 at 10 % only (reference); P4 ladder; P5 ladder; then one REPLICATE cell of C4a P5 at P5's C4a capacity level (10 % if P5's capacity is below 10 %). **Relabelled 2026-11-13, after the smoke run and before the sweep (user decision; §12):** this cell was registered as the Step 5 coalescing-OFF cell. It runs with the coalescing flag OFF (tag `P5nc`), but under the registered release rule that flag can never change a decision (§12 hold table: no append is held until the next one is due, so neither a coalesce nor a `next_append_due` release can occur). It is therefore a same-configuration replicate of the C4a P5 cell at that level. It measures run-to-run noise: the episodic p99 difference between the two runs is reported and used when reading one-level capacity differences. The equivalence is checked in the results (0 coalesced in the P5 cell, 0 `next_append_due` releases in the replicate).
2. **C4** = KV-HOST k = 8 + cold r = 0.1: P4 at 10 % only (drift check against Part B's 0.531 s; must lie within 0.398 to 0.664 s, otherwise STOP AND ASK); P5 ladder.
3. **C2** = KV-HOST k = 8, no cold: P0 ladder (this run's warm-only ceiling); P5 ladder (warm management only).
4. **C1b** = KV-GPU, cold r = 0.1: P4_1024 ladder.
5-hour guard: once 5 h have elapsed since the first sweep cell, finish the current cell and STOP AND ASK.

**Measured per cell:** everything Part B measured (episodic p50 / p90 / p99, capacity, cold time to answer, 5 / 10 s, letters vs the Part A reference, computed tokens, holds, release reasons, slices, /metrics and CPU timelines, monitor), plus:
- per warm request (`slice1_partc_warm_h100nvl.jsonl`): kind, device, session, session time, scheduled time, dispatch time, hold time, release reason (gap / flush_for_escalation / next_append_due / passthrough), coalesced (dropped) yes / no, predicted time, computed tokens, TTFT;
- per escalation: time to answer from its scheduled time; fraction within 1 / 2 / 5 s; staleness = frames of the session with session time after the last dispatched warm request's session time, at the escalation's arrival (before any flush); answer letter vs the same question's letter under P0 in the same condition. C4 has no P0 cell in Part C and Part B recorded no warm letters, so C4's reference is C4a's P0 letters (same warm plan, same questions; the conditions differ only in cold rate);
- appends issued vs coalesced; total warm computed tokens vs P0 in the same condition (GPU work);
- for each over-budget episodic call (TTFT > 0.45 s): which requests were in flight during [scheduled arrival, first token]: cold slice or monolithic cold request, warm append, warm escalation, none.

**Sanity (as Part B):** every cold recall's first request <= 16 cached tokens and every slice's prefix gap <= 32 tokens (STOP otherwise); "non-default args" without scheduler flags; exclusivity monitor, VOID on overlap; C4 P4 10 % drift check.

**Pre-registered decision.**
- Warm management restores capacity at C4a if P5's C4a capacity is within one ladder level of THIS run's C2-P0 capacity AND >= 90 % of cold recalls meet 10 s AND >= 90 % of escalations meet 5 s. The same rule is applied at C4 (secondary).
- Warm management helps warm-only traffic if P5's C2 capacity exceeds C2-P0's by at least one level.
- P4_1024 at C1b is reported against Part B's rule (capacity >= 30 % and >= 90 % of recalls within 10 s).
- Escalation letters: at least 95 % must agree with P0's letters in the same condition; otherwise flagged.

**Stop and ask if:** GPU 2 is not idle; the hook cannot be default-off and byte-identical; predicted times would need Part C data; the drift check fails; the smoke run shows appends are never held; the 5-hour guard trips; anything would need a methodological change.

## 12. Mechanism verification for Part C (recorded BEFORE the Part C sweep)

**Hook (default off).** Diff of `experiments/cost/study_e10b_mixed.py` (the only change to shared code):

```
+WARM_DEVICE = None          # StudySLICE1 Part C hook: replaces R6.device for warm sessions when set; None = R6.device
...
-                         *(R6.device(cell, d, plans[d], offsets[d], window_end) for d in range(k)))
+                         *((WARM_DEVICE or R6.device)(cell, d, plans[d], offsets[d], window_end) for d in range(k)))
```

With the default `None` the expression evaluates to `R6.device`, called with the same arguments in the same place, so E10b to E10f and Part B execute the same code path. Part C sets the hook only for P5 cells and resets it to `None` after each cell.

**Offline unit test (before any GPU use).** The warm manager was driven with a fake engine and a synthetic episodic schedule. At 20 req/s an append was held for 1.0 s and then coalesced when the next one came due. The next append was flushed before an escalation, and the posts went out in the order append then escalation (10 ms apart). With coalescing OFF the held append was released as `next_append_due`. At 2 req/s appends were released on gaps after 0.02 to 0.05 s. The test also exposed one implementation bug, fixed before the smoke run: a session's dispatched state started at -1 instead of the warm-up's offset, which would have predicted the first append from the whole history (~9 s).

### 12a. Part C smoke run (07:58 to 08:03, 2026-11-13)

**Setup:** C4a (KV-HOST k = 8 + cold r = 0.05), P5, 10 % load (1.51 req/s), 60-s window (first 10 s discarded), one fresh E0 server. Files: `results/cost/study_slice1/slice1_partc_smoke_*`.

| quantity | value |
|---|---|
| episodic p50 / p99 (n 70) | 0.155 / 0.360 s (meets 0.45 s) |
| cold recalls in window | 2 / 2 within 10 s and 5 s, letters 2 / 2 equal |
| cold first-request cached / max prefix gap | 0 / 20 tokens |
| appends (all / in window) | 47 / 39, all dispatched, 0 coalesced |
| append hold | 32 of 47 under 5 ms; p50 0.0016 s, p90 0.130 s, max 0.671 s; every release `gap` |
| append predicted time | 0.202 to 0.308 s (2 to 5 new frames) |
| append computed tokens | 185 to 469 (median 459) |
| escalations (all / in window) | 8 / 6; 6 dispatched immediately, 2 aligned (held 0.130 and 0.287 s); 0 flushes |
| escalation time to answer | 0.15 to 0.56 s; all within 1 s |
| staleness at escalation | 1 to 4 frames |
| warm-ups ending inside the window | 0 |
| warm fallbacks (processor-cache miss) / errors / submission-order waits | 0 / 0 / 0 |

**Step 1, the causal chain.** Part B showed that each episodic call that overlaps an in-flight long request pays that request's engine steps. In C4, 7 of 8 over-budget calls overlapped both a cold slice and an in-flight warm request. StudySIM1b measured an overlap cost of 0.05 to 0.07 s per in-flight warm request, plus a 0.04-s KV-HOST mode cost. This bears on FORMULATION's physical component of Context Inertia (maintaining warm state is work charged to the shared accelerator) and on its timing dimension. The chain under test is:
1. Warm appends are deferrable and escalations are short, so dispatching them only in gaps between episodic calls reduces how often an episodic call overlaps warm work.
2. Together with P4's gap-timed cold slices, this keeps episodic p99 within 0.45 s at higher load.
3. Coalescing held appends reduces warm work further.
4. Escalations and cold recalls still meet their deadlines because escalations are aligned at most once and cold slices keep P4's slack guard.

**Step 2, link instantiation (from the smoke run).**

| causal link | implementing quantity | value in this run | varies as expected? | evidence |
|---|---|---|---|---|
| appends are deferred into gaps | append hold time, release reason | 0 to 0.671 s, 47 / 47 `gap` | yes: holds are non-zero exactly when an episodic call is due within the prediction | warm rows `held_s`, `release` |
| escalations are gap-aligned | escalation hold, release reason | 2 of 8 aligned (0.130, 0.287 s), 6 immediate | yes | warm rows |
| cold path behaves as P4 | slices, holds, release reasons, prefix reuse | 6 slices per recall, all `gap` releases, holds 0 to 0.087 s, first cached 0, gap <= 20 | yes (same as Part B P4) | cold and slice rows |
| episodic waiting falls | episodic p99 | 0.360 s at C4a 10 % (Part B C4 P4 10 %: 0.531 s, r 0.1) | to be tested by the sweep | cell summary |
| **coalescing reduces warm work** | appends coalesced | **0 of 47** | **UNEXERCISED** (not absent by error) | see below |
| flush before escalation | flushed appends | 0 of 8 | rare (load-dependent) | warm rows |

**Coalescing is UNEXERCISED at every ladder level (not absent by error).** The mechanism is implemented and was exercised in the offline unit test, but under the registered release rule a held append is always released at a gap long before the next append is due. An append can be coalesced only if it is still held when the session's next append comes due, 10 s later. The hold rule releases an append at the first moment no episodic call is due within its predicted time, which is 0.308 s for a normal 5-frame append. On this run's actual episodic schedules (E10c seed-index map, 240-s window, appends at every 0.1 s offset), the longest possible hold is:

| level | 5-frame append (0.308 s) hold p50 / p99 / max | 10-frame append (0.484 s) max |
|---|---|---|
| 10 % | 0.000 / 0.709 / 1.02 s | 2.37 s |
| 20 % | 0.117 / 1.113 / 1.69 s | 3.90 s |
| 25 % | 0.171 / 1.700 / 2.37 s | 8.40 s |
| 30 % | 0.264 / 2.388 / 3.38 s | 11.89 s |
| 40 % | 0.381 / 2.781 / 3.39 s | 14.94 s |

A 5-frame append is never held for 10 s at any level, so no append is ever coalesced. 10-frame appends only exist after a coalesce, so the last column cannot occur either. The coalescing link and the Step 5 coalescing-OFF cell (where `next_append_due` would likewise never fire) therefore cannot vary across the sweep. The sweep was held and the user was asked.

**User decision (2026-11-13, before the sweep):** proceed as registered. Coalescing is recorded as an UNEXERCISED link and Part C makes no claim about coalescing. The coalescing-OFF cell runs anyway, relabelled in §11 as a same-configuration replicate of C4a P5 at P5's capacity level, to measure run-to-run noise. The results confirm that P5's warm computed tokens are about 1.0x P0's. Everything else is unchanged, including the 5-hour guard and the stop conditions.

**Step 3, trace (smoke).**
- **Append:** device 0, session time 140 s. Scheduled at t = 70.656 s; an episodic call was due within 0.308 s, so it was held 0.671 s and released by `gap` at 71.327 s. It had 6,439 prompt tokens, 5,984 cached and 455 computed; TTFT was 0.230 s.
- **Aligned escalation:** device 4, session time 546 s, scheduled at 39.219 s with a 0.290-s prediction. It waited until 5 ms after the due episodic call and was dispatched at 39.505 s. It had 24,846 prompt tokens, 24,432 cached and 3 stale frames, and answered D in 0.564 s from its scheduled time.
- **Cold recall:** S1B3, 6 slices all released by `gap` (total hold 0.087 s), answered in 3.13 s with the reference letter.
- **Episodic calls:** 70 calls with p99 0.360 s, within budget.

**Step 4, negative control (planned).** P5 with warm management disabled is P4: the same cold code with the hook off. The control is this run's C4 P4 10 % cell (drift check against Part B's 0.531 s). Within C4a, P4's ladder is the warm-unmanaged control for P5.

**Step 5, alternative explanation.** A P5 capacity gain could come from coalescing (less warm work) rather than gap alignment. Coalescing is unexercised in this design (table above), so any gain cannot come from it. Warm computed tokens vs P0 (expected about 1.0x) confirm this in the results. A second alternative is run-to-run noise at a ladder boundary; the replicate cell measures it.

**Step 4 outcome (from the sweep).** The mechanism-off control is P4 (warm pass-through, same cold path). At C4 10 % P4's p99 was 0.544 s, which passes the drift check (1.03x Part B's 0.531 s, limit +/-25 %). P5's p99 was 0.453 s. Turning warm management on changed the result by -0.091 s, more than 10x the replicate noise (§14.4). The mechanism therefore acts; whether it helps depends on load (§14.3).

## 13. Part C run (2026-11-13 09:00 to 11:43)

- **Scale:** 22 cells on 22 fresh E0 servers, h100nvl GPU 2, 2 h 44 min (inside the 5-h guard); smoke 1 cell (§12a).
- **Status:** not VOID. Every server's "non-default args" line showed no scheduler flags (22 / 22). 0 episodic errors and 0 cold-recall errors. The drift check passed (C4 P4 10 %: 0.544 s, 1.03x Part B).
- **Cache checks:** every cold recall started cold (first-request cached tokens 0). The largest link prefix gap was 20 tokens.
- **Warm traffic:**
  - 0 warm-ups ended inside any scored window.
  - Every cell, P0 included, has 3 to 5 delta-body fallbacks (a processor-cache miss answered by a full resend, as in RH7 / E10c), so fallbacks are not caused by P5.
  - One warm request failed: an append in C2 P5 25 % at 11:00 got a client-side `httpx ReadError` (connection dropped mid-stream; the server log shows no error or abort).
  - The session recovered by the standard fallback on its next append (+460 computed tokens). All 902 episodic calls in that cell succeeded, so its capacity verdict stands.
  - The harness's own warm-error STOP (not a pre-registered stop condition) halted the sweep after that cell. It was resumed at 11:04 with the check unchanged; completed cells were skipped, and the 5-h clock kept counting from 09:00.
- **Files:** `results/cost/study_slice1/slice1_partc_{requests,slices,warm,metrics,cpu,monitor}_h100nvl.jsonl`, `slice1_partc_run_meta_h100nvl.json`, `slice1_partc_results.json` (from `study_slice1_partc_analyse.py`).

## 14. Part C results

### 14.1 Episodic capacity (p99 TTFT from the scheduled arrival, budget 0.45 s)

| condition | policy | capacity | p99 per level (s): 10 / 20 / 25 / 30 / 40 % |
|---|---|---|---|
| C4a (k 8 + cold r 0.05) | P0 (reference, 10 % only) | fails at 10 % | 3.399 |
| C4a | P4 | **10 %** | 0.387 / 0.640 |
| C4a | **P5** | **10 %** | 0.357 / 0.761 |
| C4a | P5 replicate (10 %) | meets at 10 % | 0.364 |
| C4 (k 8 + cold r 0.1) | P4 (drift check, 10 % only) | fails at 10 % | 0.544 |
| C4 | **P5** | **< 10 %** | 0.453 |
| C2 (k 8, no cold) | P0 | **30 %** | 0.279 / 0.352 / 0.350 / 0.375 / 0.497 |
| C2 | **P5** | **30 %** | 0.305 / 0.343 / 0.358 / 0.389 / 0.514 |
| C1b (KV-GPU, cold r 0.1) | **P4_1024** | **25 %** | 0.399 / 0.395 / 0.443 / 0.469 |

### 14.2 Cold recalls (scored window, all cells of the ladder)

| condition | policy | recalls | within 10 s | within 5 s | time to answer p50 / p90 / max (s) | letters = ref |
|---|---|---|---|---|---|---|
| C4a | P0 (10 %) | 11 | 100 % | 100 % | 3.12 / 4.50 / 4.57 | 10 / 11 |
| C4a | P4 | 21 | 100 % | 57 % | 4.79 / 7.11 / 8.89 | 20 / 21 |
| C4a | P5 | 21 | 100 % | 52 % | 4.92 / 7.28 / 8.94 | 19 / 21 |
| C4a | P5 replicate | 11 | 100 % | 82 % | 3.65 / 6.20 / 6.46 | 10 / 11 |
| C4 | P4 (10 %) | 26 | 100 % | 62 % | 4.38 / 7.71 / 8.40 | 25 / 26 |
| C4 | P5 | 26 | 100 % | 65 % | 4.34 / 7.75 / 8.47 | 26 / 26 |
| C1b | P4_1024 (all 4 levels) | 98 | 86.7 % | 49 % | 5.06 / 10.42 / 18.79 | 97 / 98 |
| C1b | P4_1024 within capacity (10 to 25 %) | 76 | 90.8 % (69) | 54 % | 4.80 p50 | |

P4_1024 met 10 s in 26 / 26 recalls at 10 % and 22 / 22 at 20 %, but only 21 / 28 at 25 %, where 82 slices were released on slack and the worst recall answered at 18.8 s. Letter mismatches are 1 per policy at most, with the reference letter as in Part B.

### 14.3 Warm traffic

**Appends (in window, per cell 189; all dispatched, 0 coalesced in every cell).**

| cell | hold p50 / p90 / max (s) | release reasons | append TTFT p50 / p90 (s) | P0 / P4 same cell | warm computed tokens vs P0 / P4 |
|---|---|---|---|---|---|
| C2 P5 10 % | 0.002 / 0.274 / 0.686 | gap 187-189, flush 0 | 0.283 / 0.406 | 0.257 / 0.350 | 1.000 |
| C2 P5 30 % | 0.305 / 1.047 / 2.707 | gap, flush 2 | 0.384 / 0.593 | 0.316 / 0.498 | 1.000 |
| C2 P5 40 % | 0.307 / 1.503 / 3.026 | gap, flush 3 | 0.425 / 0.700 | 0.351 / 0.564 | 1.000 |
| C4a P5 10 % | 0.002 / 0.269 / 0.674 | gap | | | 1.000 |
| C4a P5 20 % | 0.101 / 0.728 / 1.206 | gap, flush 2 | | | 1.000 (vs P4) |
| C4 P5 10 % | 0.002 / 0.278 / 0.785 | gap | | | 1.000 (vs P4) |

Warm computed tokens per cell were 91,111 to 91,321 under every policy (C2 P5 25 %: 0.9998x, the one failed append). **P5's warm GPU work is 1.00x P0's**, as expected with no coalescing. Every hold length agrees with the §12 hold table: no append was held anywhere near 10 s (maximum 3.03 s at C2 40 %).

**Escalations (time to answer from the scheduled time).**

| condition | policy | escalations | within 1 / 2 / 5 s | p50 / p90 (s) | staleness p50 / max (frames) | letters = P0 |
|---|---|---|---|---|---|---|
| C4a | P0 | 21 | 81 / 90 / 100 % | 0.293 / 1.902 | 3 / 4 | (reference) |
| C4a | P4 | 42 | 98 / 100 / 100 % | 0.276 / 0.761 | 3 / 4 | 42 / 42 |
| C4a | P5 | 42 | 95 / 100 / 100 % | 0.312 / 0.927 | 3 / 5 | 41 / 42 |
| C4a | P5 replicate | 21 | 95 / 100 / 100 % | 0.294 / 0.697 | 3 / 4 | 21 / 21 |
| C4 | P4 | 21 | 100 / 100 / 100 % | 0.346 / 0.595 | 3 / 4 | 20 / 21 (vs C4a P0) |
| C4 | P5 | 21 | 95 / 100 / 100 % | 0.319 / 0.727 | 3 / 4 | 20 / 21 (vs C4a P0) |
| C2 | P0 | 105 | 100 / 100 / 100 % | 0.287 / 0.497 | 3 / 4 | (reference) |
| C2 | P5 | 105 | 100 / 100 / 100 % | 0.345 / 0.674 | 3 / 5 | 105 / 105 |

- **Escalation holds:** P5 aligned 4 to 60 escalations per ladder (holds at most 0.32 s) and flushed a held append before 2 to 9 of them.
- **Letters:** 104 / 105 at C4a and 105 / 105 at C2 agree with P0. C4's 40 / 42 (95.2 %) is compared with C4a's P0 letters (§11); both C4 mismatches are the same question in P4 and in P5. No condition is below 95 %, so none is flagged.

### 14.4 Run-to-run noise (replicate)

The replicate of C4a P5 at 10 % (P5's C4a capacity level) had a p99 of 0.364 s against 0.357 s for the original. The difference is +0.007 s (1.02x), and both cells meet the budget. Equivalence of the two configurations held as predicted: 0 coalesced in either cell and 0 `next_append_due` releases in the replicate. Reading one-level differences with this noise in mind:
- **C4 P5 at 10 %:** it fails the budget by 0.003 s, inside run-to-run noise. Its capacity is formally < 10 % and could be 10 % on a rerun. Either value is two or more levels below C2-P0's 30 %, so the decision does not change.
- **P5 vs P0 at C2:** p99 differences per level are +0.026, -0.009, +0.008, +0.014, +0.017 s, all small. Both fail at 40 % by more than the noise (0.497 / 0.514 s).

### 14.5 What the over-budget episodic calls overlapped

Over-budget calls are classified by the requests in flight during [scheduled arrival, first token].

| cell | over budget | cold + append (+ escalation) | append only (+ escalation) | cold only (+ escalation) | none |
|---|---|---|---|---|---|
| C4a P0 10 % | 46 | 46 | 0 | 0 | 0 |
| C4a P4 20 % | 28 | 28 | 0 | 0 | 0 |
| C4a P5 20 % | 35 | 30 | 1 | 4 | 0 |
| C4 P4 10 % | 5 | 5 | 0 | 0 | 0 |
| C4 P5 10 % | 4 | 3 | 0 | 1 | 0 |
| C2 P0 40 % | 22 | 0 | 19 | 0 | 3 |
| C2 P5 40 % | 29 | 0 | 24 | 1 (escalation) | 4 |
| C1b P4_1024 30 % | 14 | 0 | 0 | 14 | 0 |

**Why P5 does not help (mechanism, measured).** Holding works as specified: holds grow with load (append hold p50 0.002 s at 10 %, 0.31 s at 30 to 40 %), and every release waits for a predicted gap. Two measured effects defeat it:
1. **Appends take longer than predicted under load.** The prediction (0.307 s for a 5-frame append) comes from E10c's 10 % cell. Under P5 at C2 40 % the appends' service TTFT was 0.425 s p50 and 0.700 s p90. An append released into a gap the predictor judged long enough is often still running when the next episodic call arrives: of the 62 append overlaps with over-budget calls in that cell, 38 involved an append submitted before the call arrived.
2. **Held work bunches.** Each held append (and each cold slice) checks for a gap independently, so requests held behind the same episodic call are all released into the same gap.
   - At C2 40 %, 49 of 189 P5 appends were submitted within 50 ms of another append, against 0 of 189 under P0; on average 1.57 appends were in flight at each submit, against 1.17.
   - At C4a 20 %, 20 P5 appends were submitted within 50 ms of a cold slice, against 7 under P4.
   - Bunched appends run longer (TTFT p50 0.425 vs 0.351 s for P0 at C2 40 %), which lengthens the very gaps they need.

At low load (10 %) gaps are long and P5 helps slightly: -0.030 s at C4a and -0.091 s at C4 vs P4. At 20 % and above, bunching dominates: +0.121 s at C4a 20 % vs P4.

**P4_1024 at C1b.**
- 1,024-token slices shorten the longest cold unit (Part A: ~0.19 vs ~0.38 s engine time), which lifts capacity from Part B's 20 % (P4, n 2,048) to 25 %.
- At 30 % every over-budget call overlapped a cold slice and nothing else.
- At 25 % the slack guard released 82 slices back-to-back, and 7 of 28 recalls missed 10 s (worst 18.8 s). The extra links (11 to 12 per recall, at the n = 1,024 latency factor of 1.467) make recalls slower to finish than at n = 2,048.

## 15. Part C decision (pre-registered rule)

| rule | measured | verdict |
|---|---|---|
| C4a [PRIMARY]: P5 capacity within one level of this run's C2-P0 (30 %, so >= 25 %), AND >= 90 % cold recalls within 10 s, AND >= 90 % escalations within 5 s | P5 10 %; cold 100 %; escalations 100 % | **NO** (capacity 10 % vs >= 25 % needed) |
| C4 (secondary): same rule | P5 < 10 % (0.453 s at 10 %, 0.003 s over); cold 100 %; escalations 100 % | **NO** |
| C2: P5 capacity exceeds C2-P0's by >= 1 level | P5 30 % = P0 30 % | **NO** |
| C1b: P4_1024 capacity >= 30 % and >= 90 % within 10 s | 25 %; 86.7 % (90.8 % within capacity) | **NO** (closer than Part B's P4: 20 %, 84.2 %) |
| escalation letters >= 95 % agree with P0 | C4a 99.0 %, C4 95.2 %, C2 100 % | not flagged |

**Classification (CLAUDE.md Rule 2).**
- **Warm management (P5) at C4a / C4 / C2 is a real negative for the registered P5 rule.** The mechanism was present and varied with load (Step 2, §14.3), and turning it off changed the result (Step 4: -0.091 s at C4 10 %, +0.121 s at C4a 20 %), but it did not restore capacity. The measured reasons are a low-load service-time prediction that underestimates append time under load, and independent per-request gap checks that bunch held work (§14.5). The negative is specific to this rule. A rule that accounts for other released work and uses a load-aware prediction is untested.
- **Coalescing is UNEXERCISED** (§12): under the registered release rule a held append is always released at a gap long before the next append is due. Part C makes no claim about coalescing, and P5's warm GPU work is 1.00x P0's.
- **P4_1024 at C1b is a real negative against Part B's rule,** with a one-level gain over n = 2,048.

## 16. Part C consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | C2 P0 capacity (E0, N 1) | 30 % | 30 % | StudyE10c | 1.0 | yes |
   | C2 P0 p99, 10 / 20 / 25 / 30 / 40 % | 0.279 / 0.352 / 0.350 / 0.375 / 0.497 s | 0.370 / 0.402 / 0.339 / 0.374 / 0.478 s | StudyE10c E0 C2 | 0.75 / 0.88 / 1.03 / 1.00 / 1.04 | yes |
   | C4 P4 10 % p99 | 0.544 s | 0.531 s | Part B | 1.03 | yes |
   | C4a P0 10 % p99 | 3.399 s | 3.049 s (C1a, no warm) / 4.458 s (C4, r 0.1) | Part B P0 | 1.11 / 0.76 | yes (between the two) |
   | escalation TTFT p50, C2 P0 | 0.287 s (from scheduled time) | 0.271 to 0.328 s (from submit) | StudyE10c E0 C2 | about 1.0 | yes |
   | warm computed tokens per cell | 91,111 to 91,321 (appends + escalations) | 83,285 (appends only) | StudyE10c E0 C2 | 1.09 (escalations add ~8k) | yes |
   | cold computed tokens per recall (median) | 11,094 to 11,257 | 11,077 to 11,586 | Part B | about 1.0 | yes |
   | C1b capacity, sliced | P4_1024 25 % | P4 20 %, P3_1024 10 % | Part B | | consistent (shorter slices + hold) |

2. **Physical plausibility.** PASS.
   - An append computes ~455 new tokens over 13 to 25k cached tokens in 0.26 to 0.43 s of client-side TTFT, about 1.1 to 1.8k tok/s, slower than the 5.3k tok/s prefill curve because of KV-HOST lookups and batching with other work. Nothing runs faster than the committed curves.
   - The cold P0 recall at C4a (3.12 s p50) matches Part B's 2.97 s at C1a.
3. **Distribution sanity.** PASS.
   - p99 differs in every cell (0.279 to 3.399 s).
   - Hold times and release counts vary by load.
   - Escalation answer times are spread (p50 0.28 to 0.35 s, p90 0.50 to 1.90 s).
   - Warm computed tokens are nearly constant across cells, as expected: the warm plan is identical in every cell (same sessions, same appends, same prefix cache state), and the small differences (91,111 to 91,321) come from fallbacks and the one failed append.
4. **Definition audit.** PASS, with flags.
   - Capacity, ladder, budget, seeds, window, discard, drain cap, cold sessions and deadlines are identical to Part B, and C2 / C4 are identical to E10c / Part B.
   - New definitions, stated in §11: C4a = C4 at cold r 0.05; escalation time to answer is from the scheduled time (E10c's escalation `ttft_s` is from submit); staleness counts frames not yet dispatched at the escalation's arrival.
   - **Flagged:** C4's escalation letter reference is C4a's P0 (§11).
   - **Flagged:** the coalescing-OFF cell is a same-configuration replicate (§11, §12).
5. **Claim linkage.**
   - FORMULATION's physical component of Context Inertia (warm-state maintenance and reconstruction are work on the shared accelerator) and the timing dimension of the joint placement x timing policy.
   - Part C **weakens** the claim that gap-timing warm maintenance per request recovers episodic capacity when warm sessions and cold recall share a replica. Under the registered rule it does not, because independently released deferrable work bunches.
   - It **supports** the claim that shorter cold units raise capacity (P4_1024 25 % vs P4 20 % at C1b), with a recall-latency cost.
   - It does not speak to representation choice or to coalescing.
6. **Proxy validity.**
   - **Known schedule:** the orchestrator knows the episodic arrival schedule, as in Part B; this is a limitation.
   - **Predicted append time:** it comes from a single low-load committed cell and stands in for in-flight time. It is accurate at 10 % (0.307 predicted vs 0.283 s measured p50) but underestimates at 30 to 40 % (0.384 to 0.425 s). This proxy failure is part of the measured mechanism (§14.5), so the P5 negative is scoped to this predictor.
   - **Letters:** letter equality stands in for "same answer", as before.

**Result: PASS 6 / 6** (check 4 records two flags; check 6 records the predictor limitation that bounds the P5 negative).

## 17. Part D design (recorded before the Part D run)

**Questions.**
- **D1.** Does a single coordinated background lane (P6) remove bunching and restore capacity where P4 / P5 fail?
- **D2.** How much of the gap-aware policies' benefit survives when the orchestrator knows only stream cadences, not the exact arrival times?
- **D3.** Live baseline numbers under the realistic arrival model, for the baselines that run on this harness today.

**Validity issue addressed.** In Parts B and C the orchestrator knew the exact future Poisson arrival times of the episodic calls. That is oracle knowledge for every gap-aware policy. Part D-a keeps that model, so it stays comparable to B and C. Part D-b replaces it with the target system's model: each device stream calls at a declared cadence, and only the phase and the network jitter are uncertain.

**Harness.** `experiments/cost/study_slice1_partd.py` on top of Part C's `study_slice1_partc.py` (warm post with letters, warm device loop, server and sanity checks), Part B's `study_slice1_live.py` (cold sessions, fresh namespaces, chain bodies) and `study_e10b_mixed.run_cell`, used through the existing default-off `WARM_DEVICE` hook and the modules' existing monkeypatch points: `E.dispatch`, `L.run_recall`, `L.next_ep_due`, `L.align_after_due` and `E.FRACS`. No shared file changes. If any change becomes necessary, it will be default-off, with the diff recorded in §18. Part B / C behaviour stays the default.

Everything fixed in Parts B and C is unchanged:
- E0 server (vLLM 0.31.0 defaults, prefix caching ON, processor cache 128 GiB, E10d logging flags), with KV-HOST adding native offloading of 256 GiB;
- a fresh server per cell;
- cold sessions, order, fresh namespaces and deadlines (5 / 10 s);
- the k = 8 RH7 warm plan;
- 30-s discard, 240-s scored window, 300-s drain cap;
- p99 budget 0.45 s;
- exclusivity monitor with VOID on overlap, and the "non-default args" check.

**Policy P6 (one background lane).**
- **Background units:** cold slices (2,048 tokens for P6; 1,024 for P6_1024), warm appends and warm escalations. Warm-ups pass through. Episodic calls are never delayed.
- **One unit at a time:** at most ONE background unit is in flight at any time (submitted and not yet finished). A cold recall's next slice is enqueued only when its previous slice has finished. There is no separate cold lock; the lane serializes.
- **Queue order:** escalations first (by arrival), then cold slices by recall deadline (EDF, deadline = arrival + 10 s), then appends by due time.
- **Release rule:** the head unit is released only when the lane is empty AND now + predicted service < next predicted episodic arrival - margin. The margin is 5 ms in D-a and the jitter p90 (0.044 s) in D-b. When the head cannot go, the lane waits until just after the blocking episodic call (+5 ms), until a higher-priority unit arrives, or until the head's slack trigger, then re-checks.
- **Predicted service:** an EWMA (alpha 0.3) of MEASURED service times (submit to finish) of completed units of the same kind and size bucket. It is updated online and reset to its committed initial value at the start of every cell. Non-learned.

  | bucket | initial value (s) | committed source |
  |---|---|---|
  | cold 2,048 non-final slice | 0.478 | Part A n 2,048 links, 11k sessions, latency p50 (n 100) |
  | cold 2,048 final slice (question) | 0.367 | Part A, n 20 |
  | cold 1,024 non-final slice | 0.285 | Part A n 1,024, n 209 |
  | cold 1,024 final slice | 0.346 | Part A, n 20 |
  | append, <= 5 new frames | 0.288 | StudyE10c E0 C2 10 % appends, latency p50 (n 189) |
  | append, 6 to 10 new frames | 0.484 | Part C fit (0.1273 + 0.000390 x tokens) at 10 frames |
  | append, > 10 new frames | 0.660 | Part C fit at 15 frames |
  | escalation, <= 5 new frames | 0.311 | StudyE10c E0 C2 10 % escalations, latency p50 (n 21) |
  | escalation, > 5 new frames | 0.539 | Part C escalation fit at 10 frames |

- **Slack guard (cold head only):** if the head slice's recall deadline - now < (predicted remaining chain time x 1.373 + 0.25 s) (Part B's rule, applied to the EWMA predictions), ONE unit is released regardless of the gap. It still waits for an empty lane. There is never a back-to-back chain; the next unit waits for the lane again. Escalations and appends have no slack release.
- **Coalescing:** if a session's append is still queued when its next append becomes due, the later one supersedes it (the Part C rule). Under a single lane this can now fire, and the count is reported.
- **Absorption (declared implementation choice):** when an escalation is released, any still-queued append of the same session with an earlier session time is dropped and counted as `absorbed`. The escalation's delta body already carries those frames, because a queued append has not advanced the session's dispatched state. Releasing the append afterwards would send a request with no new frames.
- **P6_nolane (Steps 4 / 5 only):** the same queue, EWMA and release rule, but without the one-in-flight constraint. Each head unit is released as soon as its own gap check passes, and the next head is checked immediately.

**Episodic arrival models.**
- **D-a, known schedule:** Part C's model (D7 Poisson at the ladder fraction, E10c seed-index map). The orchestrator knows the exact arrival times (oracle, as in B / C).
- **D-b, cadence-only schedule (the realistic model):**
  - S episodic N = 1 streams per replica. Each calls at a fixed 0.5-s cadence with a random phase, uniform in [0, 0.5) s and seeded per cell (`numpy default_rng(5000 + 100 x S + condition index)`).
  - Each call reaches the replica at nominal time + jitter. Jitter is independent per call, half-normal with p90 = 0.044 s (sigma = 0.0268 s, seeded per cell).
  - **The jitter is an ASSUMPTION, not a measurement.** It is one committed RTT of StudyE9b setting (ii) (RTT 0.044 s, PNG at 13.6 Mbit/s). E9b commits only point values, and StudyE31b commits only bandwidth percentiles (p10 / p50 / p90 = 0.90 / 9.58 / 102.9 Mbit/s) with an assumed 20-ms RTT, so no committed per-call latency distribution exists (user decision, 2026-11-13). A measured per-call latency trace (for example from the Orin / 5G setup) would replace this assumption later.
  - **TTFT clock:** episodic TTFT is measured from the call's arrival at the replica (nominal + jitter). Network delay is outside the replica's budget. The nominal scheduled time and the applied jitter are recorded per call for the mAP bridge.
  - **Episodic content:** each stream takes its own contiguous block of the D14 N = 1 manifest (10,660 requests in clip order; block length 545), so nothing repeats within a server load. `request_id`, clip (`file_name`) and time index `t` are recorded per request.
  - **Orchestrator knowledge:** it sees only past arrivals. Each stream's next call is predicted at its last observed arrival + 0.5 s. A call that is overdue counts as due now until it arrives or the margin (0.044 s) passes; after that the stream's next prediction moves on by 0.5 s. A stream not yet seen counts as due now (within the discarded first 30 s). It never reads the future schedule.
  - **Policies under D-b:**
    - P2 and P4 use the prediction minus the margin as the earliest arrival.
    - P3's "just after the call has been dispatched" waits for the predicted call to be observed (or for the margin to pass), then adds 5 ms.
    - P6 uses the rule above with margin 0.044 s.
  - **Ladder in streams per replica: 1, 2, 3, 4, 5** (2, 4, 6, 8, 10 req/s = 13.2 / 26.5 / 39.7 / 53.0 / 66.2 % of the 15.1 req/s peak). Capacity is the highest stream count with episodic p99 <= 0.45 s and no errors, found bottom-up and stopping at the first failure. Cold arrival seeds for D-b rungs use new seed indices (1009 to 1013), since the rungs are new levels.

**Conditions and order.**
0. **Smoke:** C4a P6 at 10 %, D-a, 60-s window. Then the **Step 4 cell:** C4a P6_nolane at 10 %, D-a, full window. Both are recorded with the mechanism verification (§18) before the sweep.
1. **D-a (known schedule; Part C's ladder 10 / 20 / 25 / 30 / 40 %):**
   - C4a P6 ladder;
   - Step 5 cell: C4a P6_nolane at P6's C4a capacity level, unless that level is 10 %, where the Step 4 cell already is that cell;
   - C1b P6_1024 ladder;
   - C1b P6 ladder;
   - C4 P4 at 10 % (drift check: within +/-25 % of Part C's 0.544 s, i.e. 0.408 to 0.680 s, otherwise STOP AND ASK);
   - C4 P6 ladder;
   - C2 P6 ladder.
2. **D-b (cadence only; ladder 1 to 5 streams):**
   1. C1a and C4a: P0, P2, P3_1024, P4, P6 (P0 first);
   2. C1b: P0, P4_1024, P6_1024;
   3. C2: P0, P6;
   4. **Tuned engine** (StudyE10e P1: `--long-prefill-token-threshold 1024`; non-default args must show exactly that and no other scheduler flag): P0 at C1a, C4a and C2;
   5. C0 (no recall): P0 at E0 and at the tuned engine (the ceiling).
3. **Sensitivity, only if the guard leaves time after D-b items 1 to 5:** P4 and P6 at C1a under (i) zero jitter (margin 5 ms) and (ii) half-normal p90 = 0.20 s with margin 0.20 s, to bracket the assumption.

**Guard.** 8 hours of GPU time in total, counted from the smoke run's start. Once exceeded, the current cell finishes and the run stops and reports what is done and what remains, in the priority order above. **Amended 2026-11-13 13:50 (user decision, during D-a): no time guard.** The running sweep keeps its 8-h check, but if it trips, the sweep resumes at once with `--no-guard` (completed cells are skipped), so the full plan, including the sensitivity cells, runs to completion.

**Measured per cell.** Everything Part C measured (episodic p50 / p90 / p99 and capacity; cold time to answer, 5 / 10 s, letters, computed tokens, slices, holds, release reasons; warm rows with hold, release, coalesced, staleness, escalation time to answer within 1 / 2 / 5 s and letters vs P0 in the same condition; warm computed tokens; over-budget overlap classes), plus:
- **Lane:** occupancy (fraction of the window with a unit in flight), maximum concurrent background units (live counter; P6 must be <= 1), queue length over time (event-driven), and per unit its kind, bucket, enqueue / release / finish times, hold, release reason (gap / slack), predicted vs measured service (prediction error by load), and the EWMA value after the update;
- **Bunching** in every cell, from the rows: background units submitted within 50 ms of another, and the maximum number concurrently in flight;
- coalesced and absorbed appends;
- **per episodic request:** stream, call index, nominal scheduled time, applied jitter, arrival, predicted arrival (D-b), `request_id`, clip and `t`.

**Pre-registered decisions.**
- **D1, C4a in D-a:** P6 restores capacity if its C4a capacity >= 20 % AND >= 90 % of cold recalls are within 10 s AND >= 90 % of escalations are within 5 s.
- **C1b in D-a:** P6_1024 >= 30 % with >= 90 % of recalls within 10 s (P6 at n 2,048 is reported against the same rule).
- **Mechanism check:** the maximum number of concurrent background units is 1 in every P6 cell. If it ever exceeds 1, it is a bug: STOP.
- **D2:** for each policy, capacity in streams under D-b vs the known-schedule capacity converted to streams (known capacity fraction x 15.1 / 2, floored: 10 % -> 0, 20 / 25 % -> 1, 30 % -> 2, 40 % -> 3). The loss per policy is reported, with no pass bar.
- **D3:** tabulated only, with no claim about which baseline is best.

**Sanity.**
- Every cold recall's first request has <= 16 cached tokens, and every slice's prefix gap is <= 32 tokens (STOP otherwise).
- Scheduler flags are as declared (none for E0; exactly E10e P1's flag for the tuned engine).
- Exclusivity monitor, VOID on overlap.
- The drift check above.

**Stop and ask if:** GPU 2 is not idle; a hook cannot be default-off and byte-identical; the drift check fails; P6 ever has more than 1 background unit in flight; anything needs a methodological change beyond this specification.

## 18. Mechanism verification for Part D (recorded BEFORE the Part D sweep)

**Shared code.** No shared file changed (`git diff` on `study_e10b_mixed.py`, `study_slice1_live.py`, `study_slice1_partc.py` is empty). Part D uses only the existing default-off `WARM_DEVICE` hook and module-level monkeypatches set per cell inside `study_slice1_partd.py`: `E.dispatch`, `L.run_recall`, `L.next_ep_due`, `L.align_after_due`, and `E.FRACS` extended with new D-b seed indices after the existing nine. Part B and C code paths are therefore byte-identical, and their defaults are untouched.

**Offline tests (before any GPU use).**
- **Lane with fake units** (a synthetic Poisson schedule at 2 and 8 req/s; 6 appends, 1 cold slice with a tight deadline, 1 escalation):
  - Single lane: at most 1 unit in flight, 0 violations, release order escalation, then cold, then appends; the cold slice released by `slack`; the EWMA moved from 0.288 to 0.211 s after 0.2-s units.
  - Without the lane: 5 to 7 of 8 units released within 50 ms of each other, with up to 8 in flight.
- **D-b plan and predictor** (3 streams):
  - 1,620 calls with unique request ids, and contiguous manifest blocks with clip and `t` recorded;
  - jitter p50 / p90 / max 0.018 / 0.044 / 0.092 s;
  - over a replay, true next arrival minus prediction was -0.036 / +0.001 / +0.036 s (p5 / p50 / p95), and 2.1 % of calls arrived earlier than prediction minus margin.

### 18a. Part D smoke run (13:01 to 13:06, 2026-11-13)

C4a P6 at 10 %, D-a, 60-s window (first 10 s discarded). Files: `slice1_partd_smoke_*`.

| quantity | value |
|---|---|
| episodic p50 / p99 (n 70) | 0.150 / 0.279 s (meets) |
| cold recalls in window | 2 / 2 within 10 s and 5 s, letters 2 / 2; first cached 0, max prefix gap 20 |
| escalations | 6 / 6 within 5 s (0.15 to 0.56 s) |
| lane units / max in flight / violations | 79 / **1** / 0 |
| lane occupancy (scored window) | 0.31 |
| queue length p50 / p90 / max | 1 / 2 / 4 |
| unit hold p50 / p90 | 0.0004 / 0.678 s |
| release reasons | gap 57, slack 0 |
| bunching (units within 50 ms of another; max concurrent) | 0 of 57; 1 |
| EWMA after the cell (initial) | cold 2,048 link 0.500 (0.478), final 0.414 (0.367), append <= 5 0.196 (0.288), escalation 0.249 (0.311) |
| measured - predicted service p50 / p90 | cold -0.009 / +0.052, append -0.008 / +0.063, escalation -0.040 / +0.097 s |
| coalesced / absorbed | 0 / 0 |

### 18b. Step 4 negative control (13:06 to 13:15)

C4a P6_nolane at 10 %, D-a, full 240-s window: the same queue, EWMA and release rule without the one-in-flight constraint.

| quantity | P6_nolane (this run) | P5, Part C, same cell | P4, Part C, same cell |
|---|---|---|---|
| episodic p99 | 0.378 s (meets) | 0.357 / 0.364 s (replicate) | 0.387 s |
| background units within 50 ms of another | **90 of 275** | 43 of 276 (replicate 36) | 20 of 276 |
| max concurrent background units | **6** | 4 | 4 |
| lane max in flight | 6 | | |
| releases | gap 274, slack 1; 1 append absorbed | | |
| EWMA after the cell | append 0.486, escalation 0.703, cold link 0.577 s | | |
| cold recalls / escalations | 11 / 11 within 10 s; 21 / 21 within 5 s | 11 / 11; 21 / 21 | |

Removing the single-lane constraint brings bunching back. Measured on the same metric, it is stronger than under P5, because the lane also releases cold slices and escalations on the same gap check. The p99 is in P5's range. The control behaves as required: the one-in-flight constraint is what removes bunching.

**Step 1, the causal chain.**
1. Part C found that independently gap-released background work bunches into the same gap, and that the low-load service prediction is too short under load. Both leave background work in flight when an episodic call arrives.
2. FORMULATION's physical component of Context Inertia (warm maintenance and cold reconstruction are work on the shared accelerator) and its timing dimension say the orchestrator can reduce interference by timing that work.
3. The claim under test is that if all background work passes through one lane, with at most one unit in flight and released only when its load-aware predicted service fits before the next predicted episodic arrival, then at most one short unit overlaps any episodic call and its predicted length tracks the current load.
4. Episodic p99 should then stay within budget at higher load than P4 / P5, while the slack guard keeps cold recalls within 10 s.
5. D2 asks whether this survives when the "next predicted arrival" comes from stream cadences and past arrivals instead of the exact schedule.

**Step 2, link instantiation (smoke and Step 4 cell).**

| causal link | implementing quantity | value in this run | varies as expected? | evidence |
|---|---|---|---|---|
| one unit in flight | lane max in flight / bunching | 1 (P6) vs 6 (no lane); within-50-ms 0 vs 90 | yes | §18a, §18b |
| units held for gaps | unit hold | p90 0.678 s (P6 smoke), 0.605 s (no lane) | yes (non-zero, load-dependent) | lane rows |
| lane occupancy | busy fraction of the window | 0.31 (P6) vs 0.54 (no lane, overlapping units) | yes | lane summary |
| load-aware prediction | EWMA per bucket | append 0.288 -> 0.196 (P6, quiet lane) / 0.486 (no lane, contended); escalation 0.311 -> 0.249 / 0.703 | yes: falls when units run alone, rises under contention | lane summary |
| slack release | units released by slack | 0 (smoke, 2 recalls), 1 (Step 4 cell) | non-zero, load-dependent; to be confirmed rising with load in the D-a ladders | lane rows |
| coalescing / absorption | dropped appends | 0 / 0 (smoke), 0 / 1 (Step 4) | load-dependent; coalescing needs a held append to wait 10 s, which a single lane can now cause at higher load | lane rows |
| episodic waiting | episodic p99 | 0.279 s (P6 smoke 10 %) | to be tested by the sweep | cell summary |

No link is ABSENT or CONSTANT. Slack and coalescing are load-dependent and are tracked per cell. If either stays at 0 in every D-a cell, it will be reported as UNEXERCISED, as coalescing was in Part C.

**Step 3, trace (smoke).** Cold recall S1B2 under P6 (session prompt 11,515 tokens, scheduled at 26.085 s, reference letter E):

| slice | sent (s after arrival) | held (s) | release | predicted service (s, EWMA) | prompt / cached tokens | measured latency (s) | queue length behind it |
|---|---|---|---|---|---|---|---|
| 0 | 0.001 | 0.000 | gap | 0.531 | 2,019 / 0 | 0.466 | 0 |
| 1 | 0.466 | 0.000 | gap | 0.511 | 3,999 / 2,000 | 0.456 | 1 |
| 2 | 0.923 | 0.000 | gap | 0.495 | 5,979 / 3,984 | 0.471 | 1 |
| 3 | 1.394 | 0.000 | gap | 0.488 | 7,959 / 5,968 | 0.490 | 1 |
| 4 | 1.884 | 0.000 | gap | 0.488 | 9,939 / 7,952 | 0.522 | 2 |
| 5 (question) | 2.407 | 0.000 | gap | 0.400 | 11,515 / 9,920 | 0.467 | 3 |

- **Outcome:** answered E (reference E) at 2.850 s; computed 11,586 tokens.
- **Lane behaviour:** each slice entered the lane as soon as its predecessor finished. Cold slices outrank the 1 to 3 appends that queued behind them, and each fit a predicted gap, so none was held.
- **Prediction:** the EWMA tracked the measured link latency within about 0.05 s.
- **Binding constraint:** none (the lane, not the episodic schedule, set the pace). The other in-window recall (S1B3) was held 0.088 s in total.

**Step 4, negative control.** §18b: without the single-lane constraint, bunching reappears (90 vs 0 units within 50 ms; 6 vs 1 in flight).

**Step 5, alternative explanation.** A P6 gain could come from the EWMA predictor alone rather than from the single lane. P6_nolane keeps the EWMA and drops the lane. At 10 % the Step 4 cell is that cell. The Step 5 cell at P6's C4a capacity level (run in the sweep if that level is above 10 %) separates the two: if P6_nolane matches P6 there, the lane is not what helps. A second alternative, run-to-run noise, is bounded by Part C's replicate (+0.007 s at C4a 10 %).

### 17a. Amendment (2026-11-13, about 17:00; recorded before any P6b run): P6 lane deadlock under D-b, and P6b

**Finding (D-b, C4a, P6).** The lane deadlocks when warm sessions are present.
- **How it starts:** once cold slices are released by slack ahead of a session's appends, that session's frames accumulate. Its next escalation then carries more than 5 new frames, which puts it in the `esc_gt5` bucket with a predicted service of 0.539 s.
- **Why it cannot clear:** with a strict 0.5-s cadence, the largest predicted gap is 0.456 s (0.5 s minus the 0.044-s margin). Escalations have no slack release (§17) and are first in the queue. So from about 20 s into the window no unit of any kind could be released: no cold slices (their slack trigger is never reached while an escalation is the head), no appends.
- **After the window:** the cadence predictor keeps predicting calls after the streams stop, so the deadlock persists through the drain. All cold recalls reached the 300-s drain cap unanswered.
- **Cells:** `SLICE1D_b_E0_P6_C4a_S1` (p99 0.190 s) and `_S2` (p99 0.251 s), each with 0 of 11 / 15 recalls answered within the window or the drain. Their low p99 only reflects that no background work ran.
- **Why D-a and C1a / C1b were unaffected:** in D-a, Poisson gaps are occasionally long enough. C1a / C1b have no escalations.

**Declared methodological change (user decision, 2026-11-13).**
- The D-b P6 cells at C4a are reported as **DEGENERATE**: lane deadlock (escalation predicted 0.539 s cannot fit the 0.456-s cadence gap; escalations have no slack; no background work ran after about 20 s). They carry starvation counts and **no capacity figure**.
- The D-b C4a P6 ladder stops after the cell that was in progress (S3).
- D-b C2 P6 is **not run: deadlocked by construction, demonstrated at 1 to 2 streams at C4a.** Same warm plan and escalation rule, with no cold slices needed to start the backlog: appends alone accumulate behind any long escalation.

**P6b (pre-registered here).** P6 (§17) plus three rules. The lane stays strictly single: at most one background unit in flight, always.
1. **Per-unit deadline guards.** A head unit whose guard has tripped is released regardless of the gap, one unit at a time (it still waits for the empty lane):
   - **escalation:** guard = escalation arrival + 5 s - (predicted remaining service of its chain x 1.373 + 0.25 s), where the chain is its catch-up units (rule 3) plus the escalation;
   - **append:** guard = the session's next append due time - (predicted service x 1.373 + 0.25 s), so a held append is released in time to finish before the next append would supersede it. If it is not at the head when the next append comes due, coalescing still applies (§17);
   - **cold:** unchanged (Part B's slack rule).
2. **Stream-ended rule (D-b predictor).** A stream that misses 2 consecutive predicted calls (each beyond the margin) is treated as ended and no longer predicted, until it is observed again.
3. **Catch-up slicing.** When an escalation arrives for a session with pending (not yet dispatched) frames:
   - those frames are first sent as append units (`catchup`), queued at escalation priority ahead of their escalation;
   - each unit carries as many frames as fit the current gap estimate (at least 1 frame per unit): its predicted service, from the append fit 0.1273 + 0.000390 x (10.6 + 90.3 x frames) scaled by the current append EWMA / 0.288, must fit the gap estimate;
   - **gap estimate** = the median predicted inter-arrival gap over the next 2 s, minus the margin (D-a: from the exact schedule; D-b: from the stream predictions);
   - any still-queued append of that session is dropped as `absorbed_catchup`, since its frames are part of the catch-up;
   - the escalation then carries only its question (no new frames, `esc_le5` bucket);
   - in the lane each catch-up unit is predicted with the same value it was sized by (the scaled fit), not with the coarse 6-to-10-frame bucket EWMA, so a unit sized to fit a gap is also judged to fit it; its measured service still updates its bucket's EWMA. (Offline test: 1 stream at 0.5 s, 20 pending frames: catch-up units of 9 + 9 + 2 frames, each released on a gap one cadence period apart, then the escalation; at most 1 unit in flight. P6 on the same input never released the escalation.)
   - catch-up units fall under their escalation's deadline guard (rule 1);
   - escalation answer time is measured from the escalation's arrival, so it includes the catch-up.

**P6b runs, in the priority order.**
- D-b C4a P6b ladder: in item 1, in place of the stopped P6 ladder.
- D-b C2 P6b ladder: in item 3, in place of C2 P6.
- Then D-a C4a P6b ladder, for comparison with D-a P6 (10 %).

All other items keep their order.

**P6b checks and reporting.**
- **Mechanism check:** maximum concurrent background units = 1 in every P6b cell, otherwise STOP.
- **Reported:** deadline-guard releases by kind (escalation, catch-up, append, cold slack); catch-up units per escalation; and escalation predicted service before (the bucket it would have had without catch-up) and after catch-up.
- **Decision:** P6b is read against the same D1 rule at D-a C4a (capacity >= 20 % AND >= 90 % of recalls within 10 s AND >= 90 % of escalations within 5 s). Its D-b capacities enter the D2 / D3 tables.

**Guard.** Per the user's latest instruction ("keep the 8-h guard"), the 8-h GPU-time guard is re-instated: it trips at about 21:01 and is no longer auto-resumed. The current cell then finishes and the run stops and reports what is done and what remains. **Amended again 2026-11-13 about 20:46 (user decision): no time bound.** If the guard trips, the sweep resumes at once with `--no-guard` (completed cells skipped), so C0 on the tuned engine and all sensitivity cells run.

## 19. Part D run (2026-11-13 13:01 to 21:41)

- **Timeline:**
  - smoke 13:01 to 13:06; Step 4 cell 13:06 to 13:15;
  - sweep 13:15 to 17:03, stopped by user decision after D-b C4a P6 S3 (§17a);
  - `sweep3` 17:04 to 21:06 (P6b added; stopped by the 8-h guard at 8.08 h);
  - `sweep4` 21:06 to 21:41, resumed with `--no-guard` (user decision: no time bound).
- **Total GPU time:** 8 h 40 min on h100nvl GPU 2.
- **Scale:** 74 cells on 74 fresh servers: 62 E0 and 12 tuned (E10e P1).
- **Status:** not VOID. Every server's "non-default args" matched its engine: none of the scheduler flags for E0, and exactly `'long_prefill_token_threshold': 1024` for the tuned engine.
- **Cache checks:** every cold recall started cold (first-request cached tokens 0). The largest link prefix gap was 20 tokens.
- **Drift check:** C4 P4 at 10 % in D-a had p99 0.527 s, 0.97x Part C's 0.544 s (limit +/-25 %). PASS.
- **Errors:**
  - 1 episodic request failed with a client-side `httpx ReadError` (connection dropped mid-stream; no server error), in D-a C4a P6b 20 %, a cell that already fails on p99 (0.549 s).
  - 0 warm request errors.
- **Mechanism check:** at most 1 background unit was in flight in every one of the 27 P6 / P6_1024 / P6b cells, with 0 violations.
- **D-b jitter:** observed per-call jitter p90 was 0.044 to 0.048 s in every 0.044-s cell, 0.218 s at 0.20 s, and 0 at zero jitter. Arrival minus prediction was -0.047 / +0.000 / +0.046 s (p5 / p50 / p95) across cells. Values include a constant rounding offset of up to 5 ms from the recorded window start.
- **mAP bridge:** every D-b episodic row records stream, call index, nominal time, applied jitter, arrival, predicted arrival, `request_id`, clip and `t`.
- **Files:** `results/cost/study_slice1/slice1_partd_{requests,slices,warm,lane,metrics,cpu,monitor}_h100nvl.jsonl`, `slice1_partd_run_meta_h100nvl.json`, `slice1_partd_results.json` (from `study_slice1_partd_analyse.py`); smoke `slice1_partd_smoke_*`.

## 20. Part D results

### 20.1 D-a (known Poisson schedule): capacity, cold recalls, escalations

| condition | policy | capacity | p99 per level (s): 10 / 20 / 25 / 30 / 40 % | recalls <= 10 s / <= 5 s; answer p50 (s) | escalations <= 5 s; p50 (s) |
|---|---|---|---|---|---|
| C4a | P6 | **10 %** | 0.287 / 0.515 | 21 / 21, 29 %; 7.99 | 42 / 42; 0.47 |
| C4a | P6b | **10 %** | 0.317 / 0.549 | 20 / 21, 24 %; 8.00 | 42 / 42; 0.58 |
| C4a | P6_nolane (Step 4) | meets at 10 % | 0.378 | 11 / 11, 36 %; 5.79 | 21 / 21; 0.50 |
| C4a | Part C P4 / P5 (reference) | 10 % / 10 % | 0.387 / 0.640 and 0.357 / 0.761 | 100 % | 100 % |
| C1b | P6_1024 | **20 %** | 0.413 / 0.411 / 0.485 | 66 / 76 (86.8 %), 16 %; 7.88 | |
| C1b | P6 | **10 %** | 0.363 / 0.569 | 46 / 48 (95.8 %), 23 %; 7.72 | |
| C1b | Part C P4_1024 (reference) | 25 % | 0.399 / 0.395 / 0.443 / 0.469 | 86.7 % | |
| C4 | P4 (drift check) | fails at 10 % | 0.527 | 26 / 26 | 21 / 21 |
| C4 | P6 | **< 10 %** | 0.549 | 26 / 26, 38 %; 5.52 | 21 / 21; 0.55 |
| C2 | P6 | **40 % (ladder top)** | 0.293 / 0.315 / 0.315 / 0.332 / 0.401 | | 95 / 105 (90.5 %); 0.56 |
| C2 | Part C P0 / P5 (reference) | 30 % / 30 % | ... / 0.375 / 0.497 and ... / 0.389 / 0.514 | | 100 % |

At C2 40 %, P6's escalations pay for the capacity: only 12 / 21 (57 %) were within 5 s (p90 11.2 s, staleness up to 42 frames). At 30 % it was 20 / 21 (95 %). With escalations held to >= 90 % within 5 s, P6's C2 capacity is 30 %, equal to P0's.

### 20.2 D-b (cadence-only streams, jitter p90 0.044 s ASSUMED): capacity in streams

One stream = 2 req/s = 13.2 % of peak; 5 streams = 66.2 %.

| condition | engine | policy | capacity | p99 per rung (s): 1 / 2 / 3 / 4 / 5 streams | recalls <= 10 s | escalations <= 5 s; p50 (s) |
|---|---|---|---|---|---|---|
| C1a | E0 | P0 | < 1 | 4.355 | 11 / 11 | |
| C1a | E0 | P2 | < 1 | 2.673 | 4 / 11 | |
| C1a | E0 | P3_1024 | **3** | 0.352 / 0.422 / 0.447 / 0.519 | 47 / 58 (81 %) | |
| C1a | E0 | P4 | < 1 | 0.517 | 11 / 11 | |
| C1a | E0 | P6 | < 1 | 0.504 | 9 / 11 | |
| C4a | E0 | P0 | < 1 | 4.788 | 11 / 11 | 21 / 21; 0.22 |
| C4a | E0 | P2 | < 1 | 2.938 | 2 / 11 | 21 / 21; 0.36 |
| C4a | E0 | P3_1024 | **1** | 0.430 / 0.535 | 21 / 26 (81 %) | 42 / 42; 0.34 |
| C4a | E0 | P4 | **1** | 0.433 / 0.541 | 25 / 26 (96 %) | 42 / 42; 0.34 |
| C4a | E0 | P6 | **DEGENERATE** (no capacity figure) | 0.190 / 0.251 / 0.210 | 0 / 46 | 0 / 63 |
| C4a | E0 | P6b | < 1 | 0.567 | 8 / 11 | 21 / 21; 0.87 |
| C1b | E0 | P0 | < 1 | 4.891 | 25 / 25 | |
| C1b | E0 | P4_1024 | **2** | 0.410 / 0.420 / 0.459 | 46 / 79 (58 %) | |
| C1b | E0 | P6_1024 | **2** | 0.405 / 0.410 / 0.471 | 42 / 79 (53 %) | |
| C2 | E0 | P0 | **4** | 0.249 / 0.258 / 0.287 / 0.425 / 0.522 | | 105 / 105; 0.34 |
| C2 | E0 | P6b | **3** | 0.266 / 0.290 / 0.361 / 0.462 | | 82 / 84 (97.6 %); 2.21 |
| C1a | tuned | P0 | < 1 | 2.288 | 11 / 11 | |
| C4a | tuned | P0 | < 1 | 2.629 | 11 / 11 | 21 / 21; 0.25 |
| C2 | tuned | P0 | **4** | 0.234 / 0.262 / 0.291 / 0.416 / 0.516 | | 105 / 105; 0.34 |
| C0 | E0 | P0 | **5 (ladder top)** | 0.187 / 0.194 / 0.233 / 0.252 / 0.316 | | |
| C0 | tuned | P0 | **5 (ladder top)** | 0.192 / 0.195 / 0.237 / 0.256 / 0.319 | | |

**DEGENERATE (D-b C4a P6, §17a):** lane deadlock. The lane's last release came at 19.9 / 28.0 / 74.9 s into the window (S1 / S2 / S3), with 151 units never released. 0 of 46 recalls and 0 of 63 escalations were answered, and 537 appends coalesced. D-b C2 P6 was not run (deadlocked by construction).

**Escalation cost of P6b under cadence (C2):** within 5 s, 21 / 21, 21 / 21, 20 / 21 and 20 / 21 at 1 to 4 streams, but answer p50 rose from 0.58 s (1 stream) to 2.03 / 4.53 / 3.96 s (2 / 3 / 4 streams). Catch-up units per escalation had a median of 1 at 1 stream and 4 to 8 at 3 to 4 streams.

### 20.3 Jitter sensitivity (C1a, D-b)

| policy | zero jitter (margin 5 ms) | p90 0.044 s (primary) | p90 0.20 s (margin 0.20 s) |
|---|---|---|---|
| P4 | **2 streams** (0.221 / 0.337 / 0.721 s) | < 1 (0.517 s) | < 1 (0.510 s) |
| P6 | < 1 (0.497 s; 63 of 66 units by slack) | < 1 (0.504 s) | < 1 (0.529 s; 66 of 66 by slack) |

### 20.4 Lane (P6 / P6_1024 / P6b) and bunching

| cell | occupancy | queue p50 / p90 / max | unit hold p50 / p90 (s) | releases | coalesced / absorbed | measured - predicted service p50 / p90 (s) | background units within 50 ms of another; max in flight |
|---|---|---|---|---|---|---|---|
| D-a C4a P6 10 % | 0.37 | 1 / 6 / 8 | 0.08 / 4.66 | gap 273, slack 1 | 0 / 2 | append +0.005 / +0.088, cold +0.014 / +0.057 | 0 of 274; 1 |
| D-a C4a P6 20 % | 0.39 | 4 / 8 / 10 | 1.06 / 7.77 | gap 234, slack 17 | 17 / 9 | append +0.009 / +0.105, cold -0.006 / +0.085 | 0 of 252; 1 |
| D-a C4a P6_nolane 10 % (Step 4) | 0.54 | 0 / 1 / 5 | 0.00 / 0.60 | gap 274, slack 1 | 0 / 1 | append -0.009 / **+0.276** | **90 of 275; 6** |
| D-a C2 P6 40 % | 0.18 | 6 / 9 / 11 | 3.36 / 9.51 | gap 116 | 86 / 8 | append -0.000 / +0.111 | 0 of 119; 1 |
| D-a C1b P6_1024 25 % | 0.44 | 1 / 3 / 6 | 0.04 / 0.88 | gap 194, slack 118 | | cold +0.001 / +0.085 | 0 of 322; 1 |
| D-b C1a P6 1 stream | 0.14 | 1 / 2 / 3 | 0.18 / 5.56 | gap 2, slack 64 | | cold +0.002 / +0.038 | 0 of 66; 1 |
| D-b C2 P6b 3 streams | 0.32 | 8 / 16 / 23 | 4.50 / 9.34 | gap 147, deadline 142 | 49 / 21 (catch-up) | append +0.041 / +0.143 | 0 of 299; 1 |
| D-b C4a P6b 1 stream | 0.39 | 5 / 9 / 12 | 0.50 / 7.89 | gap 199, slack 62, deadline 10 | 25 / 15 (catch-up) | append +0.013 / +0.084 | 0 of 277; 1 |

For comparison, the non-lane policies under D-b C4a bunch: P4 had 12 of 276 units within 50 ms and up to 4 in flight; P0 had 10 of 221 and up to 10.

- **P6b deadline releases** (D-b): C2 at 1 / 2 / 3 / 4 streams: 1 / 100 / 156 / 107 (appends 1 / 94 / 109 / 91, catch-up 0 / 2 / 33 / 11, escalations 0 / 4 / 14 / 5); C4a 1 stream: 13 (appends 11, catch-up 2). D-a C4a: 0.
- **P6b catch-up:** 95 units at D-a C4a and 386 at D-b C2. Escalation predicted service before / after catch-up (median): D-b C2 0.290 / 0.172 s; D-b C4a 0.177 / 0.169 s; D-a C4a 0.146 / 0.136 s.
- **Warm GPU work** under the lane: 89,977 to 95,944 computed tokens per cell vs 91,301 under P0 (0.99x to 1.05x). Coalescing saves little because the superseding append carries the dropped frames.

### 20.5 What over-budget episodic calls overlapped

| cell | over budget | classes |
|---|---|---|
| D-a C4a P6 20 % | 16 | cold 16 (no warm) |
| D-a C4a P6b 20 % | 21 | cold 21 |
| D-a C4 P6 10 % | 8 | cold 8 |
| D-a C4 P4 10 % (no lane) | 6 | append + cold 5, append + cold + escalation 1 |
| D-a C1b P6 20 % | 25 | cold 25 |
| D-b C1a P4 1 stream | 6 | cold 6 |
| D-b C1a P3_1024 4 streams | 99 | cold 99 |
| D-b C4a P4 2 streams | 18 | append + cold 11, cold 7 |
| D-b C4a P6b 1 stream | 18 | cold 15, append + cold 3 |
| D-b C2 P0 5 streams | 107 | append 90, append + escalation 16, escalation 1 |
| D-b C2 P6b 4 streams | 21 | append 21 |

Under the single lane, warm work no longer overlaps over-budget episodic calls whenever cold slices are present: every over-budget call in a P6 / P6b cell with cold recall overlapped a cold slice, and in D-a none overlapped warm work. **The remaining binding unit is the 2,048-token cold slice** (measured 0.47 to 0.58 s at the lane's EWMA), which no gap rule can make shorter.

### 20.6 D2: known schedule vs cadence only (capacity in streams)

Known-schedule capacity is converted as fraction x 15.1 / 2, floored. The column "benefit over P0" is the policy's capacity minus P0's in the same arrival model.

| condition | policy | known schedule (source) | known, streams | benefit over P0 (known) | cadence only | benefit over P0 (cadence) | loss of benefit |
|---|---|---|---|---|---|---|---|
| C0 | P0 (E0 / tuned) | 40 %, ladder top (Part B / E10e P1) | >= 3 | | >= 5 (ladder top) | | (arrival process alone: >= +2) |
| C2 | P0 | 30 % (Part C) | 2 | | 4 | | (arrival process: +2) |
| C2 | P6 / P6b | P6 40 %, ladder top (D-a); 30 % with escalations >= 90 % | 3 | +1 (0 with escalations) | P6b 3 | -1 | 1 to 2 |
| C1a | P0 / P2 | < 10 % (Part B) | 0 | | 0 | | |
| C1a | P3_1024 | 10 % (Part B) | 0 | 0 | **3** | **+3** | gain of 3 |
| C1a | P4 | 30 % (Part B) | 2 | +2 | 0 (2 at zero jitter) | 0 (+2 at zero jitter) | **2** (0 at zero jitter) |
| C1a | P6 | not run under D-a | | | 0 | 0 | |
| C4a | P4 | 10 % (Part C) | 0 | 0 | 1 | +1 | gain of 1 |
| C4a | P3_1024 | not run under D-a | | | 1 | +1 | |
| C4a | P6 / P6b | 10 % / 10 % (D-a) | 0 / 0 | 0 / 0 | DEGENERATE / 0 | / 0 | 0 |
| C1b | P4_1024 | 25 % (Part C) | 1 | +1 | 2 | +2 | gain of 1 |
| C1b | P6_1024 | 20 % (D-a) | 1 | +1 | 2 | +2 | gain of 1 |
| C1a | tuned P0 | < 10 % (E10e P1 C1, K1 video cold body) | 0 | | 0 | | |

Reading D2:
- **Cadence arrivals are much smoother than Poisson.** With no background work they alone raise pass-through capacity: C0 holds >= 5 streams (66 %) against 3, and C2 P0 holds 4 against 2. Losses are therefore read on the benefit over P0, not on raw capacity.
- **What survives depends on whether the background unit fits a cadence gap.** The cadence gap is 0.5 s; minus the 0.044-s margin it is 0.456 s.
  - 1,024-token slices (about 0.29 s) fit. P3_1024 gains 3 streams at C1a, and P4_1024 / P6_1024 gain 1 at C1b.
  - 2,048-token slices (0.47 to 0.52 s measured) do not. P4 loses all of its known-schedule benefit at C1a (2 streams -> 0), and keeps it only at zero jitter (2 streams).
  - P6 uses its measured service time (EWMA about 0.5 s) instead of the 0.38-s engine-time prediction, so even at zero jitter it never fits and falls back to slack releases (< 1 stream).
- **Warm sessions under cadence:** the plain lane deadlocks (§17a). The P6b fixes remove the deadlock but add no capacity at C4a, and cost one stream at C2 against pass-through, while slowing escalations (p50 2 to 4.5 s at 2 to 4 streams).

### 20.7 D3: live baselines under the cadence model (tabulated; no claim about which is best)

| condition | E0 P0 | tuned P0 (E10e P1) | best sliced policy measured (streams) |
|---|---|---|---|
| C0 | >= 5 (p99 0.316 s at 5) | >= 5 (0.319 s at 5) | |
| C1a | < 1 (4.355 s at 1) | < 1 (2.288 s) | P3_1024 3 |
| C4a | < 1 (4.788 s) | < 1 (2.629 s) | P3_1024 1, P4 1 |
| C1b | < 1 (4.891 s) | not run | P4_1024 2, P6_1024 2 |
| C2 | 4 (0.425 s at 4) | 4 (0.416 s at 4) | P6b 3 |

The tuned engine roughly halves pass-through p99 under cold recall (2.29 vs 4.36 s at C1a, 2.63 vs 4.79 s at C4a), but that is not enough to reach the budget at 1 stream.

## 21. Part D decisions (pre-registered rules)

| rule | measured | verdict |
|---|---|---|
| D1, C4a in D-a: P6 >= 20 % AND >= 90 % recalls <= 10 s AND >= 90 % escalations <= 5 s | P6 10 %; 100 %; 100 % | **NO** |
| D1 applied to P6b (§17a) | P6b 10 %; 95.2 %; 100 % | **NO** |
| C1b in D-a: P6_1024 >= 30 % and >= 90 % <= 10 s | 20 %; 86.8 % | **NO** |
| C1b P6 (n 2,048), same rule | 10 %; 95.8 % | **NO** |
| Mechanism: max concurrent background units = 1 in every P6 cell | 1 in all 27 P6 / P6_1024 / P6b cells, 0 violations | **PASS** |
| D2 (no bar) | §20.6 | reported |
| D3 (tabulate only) | §20.7 | reported |

**Classification (CLAUDE.md Rule 2).**
- **D1 (P6 and P6b at C4a): real negative.** The mechanism was present and acted:
  - the single lane held 1 unit in flight;
  - bunching fell from 90 of 275 units (no-lane control) to 0;
  - over-budget episodic calls no longer overlapped any warm work.

  Capacity stayed at 10 % because the 2,048-token cold slice remains the binding unit.
- **Positive result (D-a, warm only):** the lane raised C2 capacity to 40 % (ladder top) against 30 % for P0 and P5. This was not a pre-registered decision, and it holds only if escalations may slow: at 40 %, 57 % of escalations were within 5 s. With escalations held to 90 % it is 30 %, equal to P0.
- **C1b P6_1024: real negative** against Part B's rule (20 %; Part C's P4_1024 reached 25 %).
- **D-b C4a P6: DEGENERATE**, a design defect of the registered P6 under cadence, not a finding about capacity. D-b C2 P6 was not run.
- **Step 5 (EWMA alone vs lane): INCONCLUSIVE at C4a.** P6's capacity level is 10 %, where both P6 and P6_nolane meet the budget (0.287 vs 0.378 s), so capacity cannot separate them. Bunching (0 vs 90) and p99 favour the lane. Whether the EWMA alone helps is not separable at this level.
- **D2 is assumption-dependent for 2,048-token policies.** P4 at C1a keeps its benefit at zero jitter (2 streams) and loses it at the assumed 0.044 s. A measured per-call latency trace is needed before this is a headline.

## 22. Part D consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | C4 P4 10 % p99 (D-a) | 0.527 s | 0.544 s | Part C | 0.97 | yes |
   | C4a P6 10 % p99 (D-a) | 0.287 s | 0.279 s (smoke) / 0.387 s (P4) / 0.357 s (P5) | §18a / Part C | 1.03 / 0.74 / 0.80 | yes (lane lower, as designed) |
   | C1b sliced capacity (D-a) | P6_1024 20 %, P6 10 % | P4_1024 25 %, P4 20 % | Part C / Part B | | consistent within one level |
   | C0 P0 p99 near 25 % load | 0.194 s (2 streams = 26.5 %, cadence) | 0.272 s (25 %, Poisson) | Part B | 0.71 | yes, explained by the arrival process |
   | C2 P0 p99 near 25 % | 0.258 s (2 streams, cadence) | 0.350 s (25 %, Poisson) | Part C | 0.74 | yes, same explanation |
   | tuned C1a P0 p99 | 2.288 s at 2 req/s | 2.124 s at 1.51 req/s | StudyE10e P1 C1 | 1.08 | yes (different cold body: K1 video) |
   | lane EWMA, 2,048-token link (final) | 0.50 to 0.58 s | 0.478 s initial (idle) | Part A | 1.05 to 1.21 | yes (load) |
   | warm computed tokens per cell | 89,977 to 95,944 | 91,301 | Part C P0 | 0.99 to 1.05 | yes |

2. **Physical plausibility.** PASS.
   - A 2,048-token link measured 0.47 to 0.58 s end to end, about 3.5 to 4.4k tok/s, below the 5.3k tok/s engine prefill curve (Part A).
   - A 1,024-token link measured about 0.29 s (about 3.5k tok/s).
   - An append measured about 0.2 to 0.3 s for about 460 new tokens over a 13 to 25k cached prefix (KV-HOST lookups).
   - Nothing is faster than the committed curves.
3. **Distribution sanity.** PASS.
   - p99 differs in every cell (0.187 to 4.891 s), and holds, queue lengths and release mixes vary with load.
   - Observed jitter matches the assumption (p90 0.044 to 0.048 s), with spread across calls.
   - Warm computed tokens are nearly constant across cells, as expected: the same warm plan runs in every cell.
   - The DEGENERATE cells' low p99 is explained (no background work ran) and is not reported as capacity.
4. **Definition audit.** PASS, with flags.
   - The ladder, budget, window, seeds and conditions are identical to Parts B / C for D-a.
   - D-b defines capacity in streams (1 stream = 2 req/s). Its TTFT runs from the arrival at the replica, the same reference point as D-a's scheduled arrival.
   - **Flagged:**
     - the jitter is an assumption, not a measurement;
     - D-b C4a P6 is DEGENERATE and D-b C2 P6 was not run (declared change, §17a);
     - P6b was added after the deadlock (pre-registered in §17a before running);
     - the tuned-engine known-schedule reference (E10e) used the K1 video cold body, not the 11k D2 history;
     - the time guard was lifted, re-instated, then lifted (user decisions, §17 / §17a).
5. **Claim linkage.**
   - FORMULATION's physical component of Context Inertia (reconstruction and maintenance work on the shared accelerator) and the timing dimension of the joint placement x timing policy.
   - Part D **weakens** the claim that gap-timing background work recovers capacity under realistic knowledge:
     - with exact schedules, one coordinated lane removes bunching and warm interference but not the cold-slice bottleneck;
     - with cadence-only knowledge, 2,048-token slices no longer fit the gaps under the assumed jitter.
   - It **supports** a narrower claim: background units shorter than the cadence gap minus the jitter margin (1,024-token slices) keep and even extend their benefit under cadence (P3_1024 3 streams at C1a).
   - It does not speak to representation choice.
6. **Proxy validity.**
   - **Jitter:** the half-normal jitter (p90 0.044 s, one E9b RTT) is an assumption. The sensitivity cells show it is decisive for 2,048-token policies (P4: 2 streams at zero jitter, < 1 at 0.044 and 0.20 s). The D-b P4 / P6 results are therefore **unvalidated for a headline** until a measured per-call latency trace replaces the assumption.
   - **Cadence:** the strict 0.5-s cadence stands in for "devices declare their call cadence". Real streams may drift or batch.
   - **D-a oracle:** the D-a results keep Part B / C's oracle schedule and are an upper bound for gap-aware policies.
   - **Letters:** escalation letters agree with P0 in 95 to 100 % of comparisons per policy (lowest 20 / 21 = 95.2 % for D-b C4a P6b), so no condition is flagged.

**Result: PASS 6 / 6** (check 4 records five flags; check 6 marks the D-b 2,048-token results as assumption-dependent).
