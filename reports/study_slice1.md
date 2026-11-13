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
