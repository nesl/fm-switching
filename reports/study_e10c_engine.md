# StudyE10c-engine: do vLLM engine settings remove the recall interference?

E-id: StudyE10c-engine (`research/EXPERIMENTS.md`, pre-registered 2026-11-11; grid trimmed by the user before any run). Host: h100nvl **GPU 2**, exclusive.

## 0. Design (recorded before running)

**Harness.** `study_e10b_mixed.py` is imported unchanged by `study_e10c_engine.py`. It keeps:
- the same request builders, seeds, RH2 warm plans and 10-s append cadence;
- the 30-s discard, 240-s window and 300-s drain cap;
- the parity gate and the exclusivity monitor.

What changes:
- **Engine flags:**

  | config | flags |
  |---|---|
  | E0 | E10b's server (vLLM 0.31.0 defaults: chunked prefill ON, `max_num_batched_tokens` 8192, policy fcfs; confirmed from E10b's server log and `EngineArgs`; re-read from every E10c server log) |
  | E1 | `--scheduling-policy priority` |
  | E2 | `--max-num-batched-tokens 2048` |
  | E4 | E1 + E2 |
  | E3 | (`512`) **dropped** by the user's trim |

- **Priorities under E1 / E4** (vLLM: lower value first): episodic 0; warm warm-up, appends and escalations 1, including cache-miss fallbacks; cold recall 2. No priority field is sent under E0 / E2.
- **Fresh server for every cell**, including C0. E10b shared one server load across its baseline levels.
- **Levels, bottom-up:**
  - N = 1 at 10 / 20 / 25 / 30 / 40 / 50 % of 15.1 req/s;
  - N = 3 at 10 / 20 / 25 / 35 / 50 % of 5.38 req/s;
  - stop at the first failing level.
- **Poisson seeds:** 25 % and 50 % reuse E10b's level indices (0, 1), so those cells reproduce E10b's arrival sequences; new levels use indices 4–8.
- **Conditions:**

  | condition | load |
  |---|---|
  | C0 | none, KV-GPU |
  | C1 | cold only, r = 0.05, KV-GPU (as E10b) |
  | C2 | KV-HOST, k = 8 |
  | C3 | KV-HOST, k = 16 |
  | C4 | KV-HOST, k = 8 + r = 0.1 |

- **Grid (user trim):**
  - E0: C0 at both N, and C1–C4 at N = 1;
  - E1, E2, E4: C0–C4 at N = 1, plus C0 and C1 at N = 3;
  - no N = 3 for C2–C4.
  - About 95–100 cells, about 12 h.

## 1. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- E10b located the interference. A cold K1 prefill (12.6k tokens, about 4 s) or a warm recall step over an 8–10k-token context shares scheduler steps with the short episodic prefills. The episodic p99 then rises with the GPU under half busy: tail interference, not throughput.
- vLLM's scheduler admits work per step up to `max_num_batched_tokens`, chunking long prefills (chunked prefill on). It orders the waiting queue by policy.
- Two levers could act on that link:
  - **Priority** puts episodic requests ahead of recall in the waiting queue, and can preempt lower-priority running requests when KV is short. It should cut the episodic wait behind recall, at the cost of recall latency.
  - **A smaller chunk** (2048 vs 8192) bounds how many recall tokens ride in each step. That bounds each step's duration, so an episodic request waits at most one short step. The cost is more steps per long prefill (lower throughput, longer recall TTFT).
- If the interference is step-sharing, E1, E2 and E4 should restore episodic capacity under C1–C4 toward C0. If it is raw GPU work (as KV-GPU eviction was in E10b), they cannot.

**Step 2, instantiate each link.**

| link | quantity | planned range | varies? | evidence |
|---|---|---|---|---|
| recall work in the step | cold 12.6k-token prefills (C1, C4); warm 8–10k-context appends / escalations (C2–C4) | r 0 / 0.05 / 0.1; k 0 / 8 / 16 | yes, by design | E10b |
| scheduling order | `--scheduling-policy`, per-request priority | fcfs vs priority (0 / 1 / 2) | yes (E0 / E2 vs E1 / E4) | server log; request bodies |
| step token budget | `max_num_batched_tokens` | 8192 vs 2048 | yes (E0 / E1 vs E2 / E4) | server log per cell |
| episodic tail | p99 TTFT from scheduled arrival | measured per cell | to be measured | rows |
| recall cost | cold / escalation / append TTFT p50 / p99; unfinished at the drain cap | measured | to be measured | rows |

- No link is ABSENT or CONSTANT by design.
- **Feasibility gate.** E10b's token-parity gate (D14 N = 1 / 3, K1 video, D2 append) runs on a fresh server of EACH engine config before its first cell. It STOPs if a config cannot serve any of the three request types, for example a 12.6k-token video under a 2048-token step.

**Step 3, trace one unit.** One episodic request and one recall request from a loaded cell per lever: scheduled → sent → first token, with queue and KV state at that second.

**Step 4, negative control.**
- E0 is E10b's server. E0 C0 at N = 1 25 % and N = 3 50 % use E10b's seeds and must reproduce E10b's p99 (0.286 / 0.988 s) within 2×.
- C0 under each lever, where there is no recall load, shows each lever's own cost to episodic capacity.

**Step 5, alternative explanation.**
- A capacity change under a lever could come from the lever changing *episodic* throughput rather than interference: a smaller chunk lowers prefill efficiency. Each lever's own C0 ladder separates the two.
- Restoration under priority could come from recall starving rather than being scheduled around. Unfinished-at-drain-cap counts and recall p99 per class separate those.

## 2. Run (2026-11-11 22:50 → 2026-11-12 07:52)

- **Exclusive, not VOID.** The exclusivity monitor (every 30 s) found no other process of ours and no foreign process on GPU 2 for the whole run. No interruptions.
- **Parity / feasibility gate: PASSED for E0, E1, E2 and E4.** Each config served D14 N = 1 (378 tokens) and N = 3 (1,062), two K1 videos (11,801 / 12,645 tokens) and a D2 append (90 tokens per frame) with exact token parity. A 2,048-token step serves a 12.6k-token video.
- **Engine flags verified from all 87 server logs** (4 parity + 83 cells): E0 21 / E1 22 at `max_num_batched_tokens=8192`, E2 22 / E4 22 at `2048`; `'scheduling_policy': 'priority'` in all 44 E1 / E4 logs and in none of the E0 / E2 logs (fcfs default); chunked prefill ON everywhere. *Implementation note:* the run-time log parser in `study_e10c_engine.py` matched only `key=value` lines, so `log_scheduling_policy` (and `log_max_num_batched_tokens` for E2 / E4) is `None` in the run meta; the values above were re-read from the logs after the run. No cell is affected.
- 83 cells (bottom-up ladders stopped at first failure, so fewer than the ≈ 95–100 planned), 75,855 request rows, 58,971 in-window episodic requests, **0 episodic errors, 0 unfinished requests of any class**.
- Caching: prefix caching ON (needed for warm sessions); episodic prompts are distinct images, so their local hit fraction is 0.00–0.02; cold K1 recalls had 0 cached tokens; KV-HOST = 256 GiB CPU offload. Fresh server per cell, so nothing is cached across cells.

## 3. Capacity (report item 1)

Capacity = highest level of the bottom-up ladder whose episodic p99 TTFT meets the budget (0.45 s at N = 1, 1.21 s at N = 3). Percent of peak (15.1 req/s at N = 1; 5.38 at N = 3).

| condition | N | E0 (default) | E1 (priority) | E2 (2048) | E4 (priority + 2048) |
|---|---|---|---|---|---|
| C0 none | 1 | **40 %** (6.04 req/s) | 40 % | 40 % | 40 % |
| C0 none | 3 | **50 %**, ladder top | 50 %, top | 50 %, top | 50 %, top |
| C1 cold r = 0.05 | 1 | **< 10 %** | < 10 % | < 10 % | < 10 % |
| C1 cold r = 0.05 | 3 | — (trim) | < 10 % | < 10 % | < 10 % |
| C2 KV-HOST k = 8 | 1 | **30 %** | 30 % | 30 % | 30 % |
| C3 KV-HOST k = 16 | 1 | **10 %** | 10 % | 10 % | 10 % |
| C4 KV-HOST k = 8 + r = 0.1 | 1 | **< 10 %** | < 10 % | < 10 % | < 10 % |

Episodic p99 (s) at each level run:

| ladder | 10 % | 20 % | 25 % | 30 % / 35 %* | 40 % | 50 % |
|---|---|---|---|---|---|---|
| E0 / E1 / E2 / E4 C0 N1 | 0.23 / 0.22 / 0.21 / 0.21 | 0.29 / 0.28 / 0.27 / 0.27 | 0.28 / 0.27 / 0.31 / 0.27 | 0.29 / 0.30 / 0.29 / 0.30 | 0.39 / 0.39 / 0.37 / 0.37 | **0.452 / 0.462 / 0.470 / 0.459** ✗ |
| E0 / E1 / E2 / E4 C0 N3 | 0.36 / 0.36 / 0.36 / 0.35 | 0.60 / 0.60 / 0.65 / 0.59 | 0.51 / 0.47 / 0.51 / 0.51 | 0.71 / 0.70 / 0.67 / 0.67* | — | 1.06 / 1.01 / 0.92 / 0.96 ✓ |
| C1 N1 | **2.74 / 2.67 / 2.95 / 2.84** ✗ | | | | | |
| C1 N3 (E1 / E2 / E4) | **2.96 / 4.05 / 2.80** ✗ | | | | | |
| C2 N1 | 0.37 / 0.30 / 0.28 / 0.30 | 0.40 / 0.33 / 0.35 / 0.35 | 0.34 / 0.34 / 0.35 / 0.35 | 0.37 / 0.37 / 0.37 / 0.39 | **0.478 / 0.484 / 0.482 / 0.485** ✗ | |
| C3 N1 | 0.44 / 0.42 / 0.42 / 0.42 | **0.478 / 0.483 / 0.485 / 0.505** ✗ | | | | |
| C4 N1 | **4.82 / 4.36 / 4.20 / 3.29** ✗ | | | | | |

(* N = 3 ladder uses 35 % instead of 30 %.) Non-monotone p99 between neighbouring levels (e.g. 20 % vs 25 %) is cell-to-cell noise at 350–1,800 requests per window; it never changes a capacity.

**Control (E0 = E10b's server, E10b's seeds): PASS.** E0 C0 N1 25 % p99 0.279 s vs E10b 0.286 s (ratio 0.97); N3 50 % 1.058 vs 0.988 (1.07). E0 C0 N1 50 % fails by 2 ms (0.452 vs 0.45), as E10b's 50 % did (0.461); 40 % is a new level, so E0's N = 1 capacity is 40 %, not E10b's 25 % (E10b had no level between 25 % and 50 %).

## 4. Which configs restore C0 capacity? (report item 2)

**None.** Under every recall condition, every lever's capacity equals E0's at the same condition (`vs_E0_same_cond` = 0.000 req/s in all 12 ladders that have an E0 counterpart; the 3 C1 N = 3 ladders, which E0 did not run under the trim, are all < 10 %), and none reaches its own C0 or E0's C0. The levers also cost nothing at C0 (40 % / 50 % for all four configs), so this is not a lever trading episodic throughput for interference — the levers simply do not act on the interference.

Small, consistent latency effects below capacity, none of which moves a capacity:
- Priority (E1 / E4) and 2048 (E2 / E4) shave the C2 10 % p99 from 0.37 to 0.28–0.30 s.
- E4 lowers the C4 10 % p99 from 4.82 to 3.29 s — still 7× the budget.

## 5. Cost to each recall class (report item 3)

TTFT p50 / p99 (s), N = 1, at the lowest level run (10 %) and, for C2, at capacity (30 %):

| class | cell | E0 | E1 | E2 | E4 |
|---|---|---|---|---|---|
| cold K1 (11 per window) | C1 10 % | p99 5.93 | 5.86 | 6.05 | 6.00 |
| cold K1 (26) | C4 10 % | p99 6.79 | 6.83 | 7.09 | 6.90 |
| warm append (189) | C2 30 % | p99 0.67 | 0.61 | 0.63 | 0.64 |
| warm escalation (21) | C2 30 % | p99 0.60 | 0.61 | 0.61 | 0.61 |
| warm append (380) | C3 10 % | p99 0.66 | 0.65 | 0.67 | 0.68 |
| warm append (189) | C4 10 % | p99 5.00 | 4.83 | 5.04 | 4.92 |
| warm escalation (21) | C4 10 % | p99 3.56 | 3.69 | 3.77 | 3.30 |

- **No recall class has p99 > 10 s in any of the 83 cells, and no request of any class is unfinished at the drain cap: no starvation flag.** Priority did not starve the priority-2 cold recalls (their p99 moved ≤ 0.1 s).
- 2,048-token steps cost cold recall +0.07 to +0.30 s at p99 (more steps per 11–12.6k-token prefill).
- Warm misses: 0 of every warm follow-up in every cell (KV-HOST holds all sessions, as in E10b).

## 6. Binding resource per cell (report item 4), and Step 3 trace

| condition | binding resource | evidence |
|---|---|---|
| C0 | GPU step time from episodic load alone | p99 rises with load; at the failing 50 % level GPU busy 67–71 %, waiting queue ≈ 0, KV ≤ 4 %, API thread ≤ 0.21 core (not client- or API-bound, as E10b) |
| C2, C3 | GPU work added by warm appends / escalations | fail one (C2) or three (C3) levels below C0 with GPU busy 53–70 % at the failing level; warm misses 0, KV ≤ 64 %, preemptions 0 — the same total work under any order or chunk size, so no lever moves it |
| C1, C4 | **head-of-line blocking by each cold K1 recall's prefill, which neither lever splits** | GPU busy only 20–26 % (C1); see below |

**Step 3 trace (E4 C1 N1 10 %, priority + 2048).** One cold recall: 11,344 prompt tokens, 0 cached, 40.8 MB body, scheduled at t = 167.95 s, first token at +3.91 s. Episodic requests (378 tokens, priority 0) around it:

| submitted vs cold | TTFT | first token vs cold first token |
|---|---|---|
| −0.86 … +0.53 s (7 requests) | 0.14–0.21 s | before (unaffected) |
| +2.08 s | 1.829 s | +0.00 s |
| +2.90 / +2.93 / +3.03 s | 1.010 / 1.072 / 0.976 s | +0.00 / +0.09 / +0.10 s |
| +3.93 s onward | 0.14–0.15 s | after (unaffected) |

Across all 11 cold-recall cells (all four configs), **99 % of slow episodic requests (p99 > budget) were submitted inside a cold recall's prefill window (714 of 722), and their first token arrives a median 0.00–0.24 s after the cold request's first token** (p90 ≤ 0.49 s). The blocked window opens 0.2–1.0 s after the cold submit (the client-to-engine handling of the 40 MB body) and closes at the cold first token.

**Reading.** The episodic request is not queued behind the cold one (scheduler waiting queue mean ≈ 0.00–0.15 in C1), so a waiting-queue priority cannot help; and it is released only when the cold prefill completes, not after one 2,048-token chunk, so chunk size cannot help. The cold multimodal prefill behaves as one unsplittable unit. **Candidate explanation (not verified inside vLLM):** Qwen3-VL's video input — vision-encoder pass plus its ~11k placeholder tokens — is scheduled as a whole multimodal item rather than chunked; the step that carries it runs for seconds and every running request waits for it. Verifying this needs per-step scheduler instrumentation (not in this harness) or vLLM's multimodal chunking option; it is not claimed here.

## 7. Consistency protocol (6 checks)

1. **Cross-check against committed measurements.**

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | E0 C0 N1 25 % p99 | 0.279 s | 0.286 s | E10b | 0.97 | yes |
   | E0 C0 N3 50 % p99 | 1.058 s | 0.988 s | E10b | 1.07 | yes |
   | E0 C0 N1 50 % (fail) | 0.452 s | 0.461 s | E10b | 0.98 | yes |
   | cold K1 TTFT p50, C1 | 4.05 s (E0) | 4.15 s (N1 25 %) | E10b | 0.98 | yes |
   | C1 episodic p99 | 2.74 s @ 10 % | 2.94 s @ 25 % | E10b | 0.93 | yes |
   | C2 N1 25 % p99 | 0.339 s | 0.429 s | E10b KV-HOST k8 | 0.79 | yes |
   | C3 N1 25 % | fails at 20 % (0.478 s) | fails at 25 % (0.452 s) | E10b KV-HOST k16 | — | yes |
   | parity tokens | 378 / 1,062 / 11,801 / 12,645 / 90 per frame | same | E10b gate | 1.00 | yes |

2. **Physical plausibility.** Cold K1: 11.3–12.6k tokens to first token in about 4 s (≈ 3k tok/s including the 40 MB body handling), consistent with E10b and below committed H100 prefill rates. Episodic p50 0.14–0.15 s (N1) / 0.25–0.30 s (N3), as D7 / E10b. No faster-than-curve result.
3. **Distribution sanity.** p50 and p99 reported per cell; p99 varies 0.21–4.82 s across cells and is non-monotone only within noise between neighbouring levels; no constants where distributions are expected.
4. **Definition audit.** Conditions C0–C4 = E10b's (KV config, k, r) cells; capacity, budget (0.45 / 1.21 s), peak (15.1 / 5.38 req/s), window (30-s discard, 240 s), drain cap (300 s) are E10b's. New: N1 levels 10 / 20 / 30 / 40 % and N3 10 / 20 / 35 %, so E10c capacities are finer-grained than E10b's (E0 C0 N1 40 % vs E10b's 25 % is a grid difference, not a disagreement).
5. **Claim linkage.** FORMULATION's shared-replica cost: whether co-locating recall with episodic scoring needs separate capacity. Result: two standard vLLM engine levers do **not** remove the cold-recall interference, so it **strengthens** E10b's conclusion that cold recall needs isolation (its own replica or admission control), not scheduler tuning. Warm recall with host KV costs 1–3 levels of episodic capacity under every config.
6. **Proxy validity.** Episodic p99 TTFT from the scheduled arrival is the direct quantity (not a proxy). "Binding resource" uses server-side averages (GPU busy, queue, KV) plus the per-request timing above; the unsplittable-prefill explanation is an inference from timing and is labelled as such.

## 8. Verdict

**Real negative (Rule 2), with mechanism located.** Priority scheduling, a 2,048-token step budget and both together restore **no** episodic capacity under any recall condition (C1–C4: capacity identical to E0 in 12 / 12 comparable ladders; the 3 C1 N = 3 ladders without an E0 counterpart are all < 10 %), and cost none at C0. The mechanism was present and exercised — cold and warm recall ran in every intended cell, all levers were active (verified from 87 server logs), and the negative control (C0 / E10b reproduction) passed — so this is a settled finding for vLLM 0.31.0 + Qwen3-VL-32B. The per-request timing shows why: episodic requests are held until a cold recall's whole multimodal prefill completes, which is not a waiting-queue or chunk-size effect. No recall class starves (p99 ≤ 7.1 s everywhere, 0 unfinished).
