# StudyRH6 — knee of the GPU+host-offload configuration and the controller's levers (H100, vLLM)

**Stack:** vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3 (FLASH_ATTN backend), CUDA graphs, gmu 0.90, max_model_len 32768, bf16 KV (62,944 tokens on GPU), prefix caching ON, Qwen3-VL-32B-Instruct @0cfaf481, h100nvl GPU 3 (PCIe Gen5 ×16). Every cell uses RH5's GPU+host server: vLLM native `OffloadingConnector` (`--kv-offloading-backend native --kv-offloading-size 256`; Part C 64). Harness = RH5's (RH2 plans, seed 0, per-device headers, 1× real time, 15-min window, warm-up upload, P-WARM, escalation rate 1.0, greedy, max_tokens 1 / 4). Watchdog (foreign process on GPU 3, host MemAvailable < 150 GiB) and GPU monitor ran for the whole chain; no foreign process on GPU 3, memory floor never reached. Analysis: original `.venv`, CPU.
Pre-registration: research/EXPERIMENTS.md StudyRH6 (2026-10-20, written before the chain started at 09:10 — before any GPU run, including the smoke). Chain 09:10–15:14 (6.07 h; model-predicted estimate 4.39 h, scenario range 4.39–7.27 h, cap 8 h — see Deviations).

## Decisions

### KNEE: **D\* = 48**; binding resource = **the vLLM API server (request ingestion before the engine)**

| cell | req/s offered | warm esc TTFT median | p99 | in flight at window end | drain | breach? |
|---|---|---|---|---|---|---|
| A D32 | 3.46 | **0.56 s** | **1.91 s** | 0 | 0 s | no |
| **A D48** | 5.18 | **654 s** | **881 s** | 3,054 | 882 s | **yes → D\*** |
| A D64 | 6.68 | 1,114 s | 1,528 s | 5,167 | 1,540 s | yes |
| A D96 | 7.97 | 1,722 s | 2,426 s | 6,733 | 2,152 s | yes |

Between D = 32 and 48 the configuration goes from RH5-like behaviour (sub-second median) to collapse. The collapse is **not** in any GPU-side resource: at D\* the GPU is idle (NVML SM util in-window median 0%; achieved computed tokens 1.15k tok/s vs ≥ 4k needed for the compute flag), the engine's own queue stays ≤ 8 requests (running + waiting) and its KV usage median in the window is 0, PCIe averages 6.2 GB/s (12% of the 48–53 GB/s reload rate), and the host tier never misses (0 of 1,787 checked warm requests; 0 allocation failures). The backlog sits **upstream of the engine**: harness in-flight minus engine running+waiting = median 1,301, max 3,054 requests during the D48 window, i.e. requests accepted by the API server but not yet handed to the engine core. The API server is the only process saturated (3.8 cores in-window median; `/metrics` stopped answering — 87% / 70% / 9% scrape coverage at D48 / D64 / D96).

**Pre-registered binding flags, stated honestly:** the pre-registered thresholds flag *api_cpu* (API process median ≥ 0.9 core) **and** *kv_running_set* (KV usage max ≥ 0.95 with waiting > 0) at D\* — but **both also fire at D32 and in B1, which do not breach**, so the thresholds alone do not discriminate. The attribution above rests on the queue-location and served-rate diagnostics (added after Part A, labelled not pre-registered): only the API server's backlog and served rate change between the non-breaching and breaching cells; KV usage reaches 0.9–1.0 only as short spikes (in-window median 0–0.07 in every 256-GiB cell, breaching or not).

**Congestion collapse, not a fixed ceiling:** the API server serves ~3.4 req/s of D2 bodies when arrivals stop (drain rate 3.45 / 3.35 / 2.78 req/s at D48 / D64 / D96) and 3.46 req/s at D32, but **under overload it serves less, not more**: 1.79 / 0.93 / 0.49 req/s in-window at D48 / D64 / D96 (served body volume 35 / 18 / 9 MB/s vs 72 MB/s at D32), while using *more* CPU (3.8–4.3 cores vs 1.9). Ingesting new 20-MB requests competes with preparing queued ones. Which API-server stage binds (HTTP/JSON ingestion and base64/PNG decoding on the event loop, or vLLM's single-worker multimodal-preprocessing executor, `renderers/base.py: ThreadPoolExecutor(max_workers=1)`) is **not resolved**: no profiler could attach (ptrace_scope = 1) and the busiest thread's in-window median is 0.58 core, so no single thread is pinned throughout.

### LEVERS MOVE THE KNEE: **all three effective at D\* = 48** (B1 within bounds; B2 and B3 only by the ≥ 50% p99-cut rule)

| cell (D = 48) | change | req/s | body MB/s offered | warm esc TTFT median | p99 | p99 cut vs A D48 | within ≤ 1.5 s / ≤ 10 s? | effective? |
|---|---|---|---|---|---|---|---|---|
| A D48 (baseline) | — | 5.18 | 107 | 654 s | 881 s | — | no | — |
| **B1** | append every 30 s | 1.98 | 42 | **1.33 s** | **3.92 s** | 99.6% | **yes** | **yes** |
| **B2** | D1 format (288×224, 65 tok/img) | 5.18 | 79 | **0.71 s** | 42.0 s | 95.2% | no (p99) | **yes** (p99 cut) |
| **B3** | lazy: no appends, full history per escalation | 0.45 | 10 | **2.29 s** (cold) | 13.9 s | 98.4% | no | **yes** (p99 cut) |

- **B1** cuts both the request rate and the ingested bytes 2.6× (to 42 MB/s, well under the ~72–76 MB/s the server sustains): no backlog, drain 2 s, GPU util back to 75%. Its median (1.33 s) is higher than D32's (0.56 s) because each append now carries 15 new frames (more compute per append; append hit 0.88 vs 0.95).
- **B2** keeps the request rate (5.18 req/s) but shrinks each body ~25% (13.7 vs 18.3 MB median): offered 79 MB/s sits at the edge of capacity — sub-second median, but a late backlog (185 in flight at window end, engine waiting max 69) gives p99 42 s. **The pair B2 vs A D48 (same request rate, ~25% fewer bytes → collapse avoided) indicates the binding quantity scales with request bytes/images, not request count.**
- **B3** removes appends: 0.45 req/s, API load negligible (0.05 cores), but every escalation is cold by design (token hit 0.51; ~11.7k-token histories prefilled at ~2.4k tok/s achieved): **median 2.29 s / p99 13.9 s** — far better than the collapsed D\* baseline (654 / 881 s) but **4× slower median than warm escalation below the knee** (D32 0.56 s; B1 1.33 s), and outside the bounds.
- **Binding resource vs levers:** the API server's ingestion load is proportional to (requests/s × images per request), which all three levers reduce — so the binding resource *is* one the controller's levers act on. The controller claim is narrowed in a different way: the lever that matters is **bytes re-sent per unit time**, which in this protocol (each append re-sends the whole history so the server can match the prefix) grows with history length × append rate even though the GPU computes only the new frames.

### PART C — host-capacity sensitivity (D\* = 48, 64 GiB host buffer)

| cell (D = 48, D2, 10 s) | host buffer | warm esc TTFT median | p99 | append hit | host hit tokens | warm misses | GPU util (window) | achieved / demand computed tok/s | in flight at end | drain |
|---|---|---|---|---|---|---|---|---|---|---|
| A D48 | 256 GiB | 654 s | 881 s | 0.954 | 42.5M | 0 / 1,787 | 0% | 1,153 / 2,260 | 3,054 | 882 s |
| **C D48** | **64 GiB** | **3,364 s** | **7,675 s** | **0.035** | **2.8M** | **999 / 1,136 (88%)** | **100%** | **4,827 / 46,312** | 4,069 | **7,736 s** |

With 64 GiB the D48 live set (peak ≈ 558k tokens, 1.72× the 325k-token GPU+host capacity) no longer fits: the host tier thrashes (88% of warm requests miss; append hit 0.95 → 0.035; host-hit tokens 42.5M → 2.8M while 10.9 TB are *stored* to host — LRU churn), every miss recomputes its ~10k-token history, and the GPU becomes the binding resource (SM util 100%, achieved 4.83k computed tok/s — RH5's GPU-only collapse rate — against 46k tok/s demanded). The pre-registered flags fire for **gpu_compute** and **host_capacity** (not kv_running_set, not PCIe: 0.09 GB/s load). The API-server backlog of A D48 is still present (upstream median 1,277), now *in addition to* an engine queue (median 644, waiting max 3,481): the cell is doubly bound and 5× worse than A D48 in median. **Host capacity is therefore a real second knee:** at 256 GiB it is not reached at any tested D (live-set peak ≤ 0.88× at D = 96; ≤ 1 warm miss per cell), at 64 GiB it is already exceeded at D\* — the host buffer must be sized to the live set (≈ D × mean history × 256 KiB), as RH5's footprint rule predicts for the GPU tier. Host-hit verification still passed (262,779 B per host-hit token, +0.24%).

## Per-cell metrics

| cell | req/s | n esc | esc TTFT med / p90 / p99 / max | append med / p99 | token hit | host share | KV med / max | PCIe load / store GB (avg GB/s) | computed tok/s achieved / demand | API cores med / max (busiest thread med) | GPU util med | waiting max | preempt | in flight at end | drain s | errors (ctx) | warm misses | pre-registered flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_D32 | 3.46 | 267 | 0.56 / 1.21 / 1.91 / 2.55 | 0.57 / 2.15 | 0.955 | 96% | 0.00 / 1.00 | 7,275 / 347 (8.1) | 1,522 / 1,499 | 1.86 / 5.55 (0.24) | 58 | 9 | 0 | 0 | 0 | 46 (46) | 0 / 2995 | kv_running_set, api_cpu |
| A_D48 | 5.18 | 397 | 654.45 / 843.63 / 881.40 / 881.96 | 660.08 / 881.40 | 0.955 | 98% | 0.28 / 0.98 | 11,131 / 523 (6.2) | 1,153 / 2,260 | 1.45 / 5.64 (0.83) | 8 | 183 | 0 | 3054 | 882 | 46 (46) | 0 / 1787 | kv_running_set, api_cpu |
| A_D64 | 6.68 | 533 | 1,114.08 / 1,469.59 / 1,528.17 / 1,546.64 | 1,120.23 / 1,531.44 | 0.955 | 98% | 0.00 / 0.99 | 14,197 / 674 (5.8) | 1,072 / 2,910 | 1.35 / 6.58 (0.84) | 0 | 45 | 0 | 5167 | 1,540 | 46 (46) | 0 / 1709 | kv_running_set, api_cpu |
| A_D96 | 7.97 | 658 | 1,722.41 / 2,311.23 / 2,425.95 / 2,442.36 | 1,709.99 / 2,421.45 | 0.945 | 98% | 0.18 / 1.00 | 17,741 / 1,032 (5.3) | 1,220 / 4,506 | 1.35 / 7.11 (0.82) | 0 | 50 | 0 | 6733 | 2,152 | 63 (63) | 1 / 2209 | kv_running_set, api_cpu |
| B1_D48 | 1.98 | 397 | 1.33 / 2.67 / 3.92 / 4.46 | 1.58 / 3.85 | 0.891 | 96% | 0.07 / 0.97 | 4,047 / 516 (4.5) | 2,213 / 2,202 | 1.55 / 5.17 (0.39) | 75 | 8 | 0 | 5 | 2 | 19 (19) | 0 / 1657 | kv_running_set, api_cpu |
| B2_D48 | 5.18 | 398 | 0.71 / 24.84 / 41.96 / 42.56 | 0.69 / 41.62 | 0.955 | 97% | 0.02 / 0.96 | 8,222 / 387 (8.7) | 1,624 / 1,680 | 2.64 / 5.08 (0.36) | 66 | 69 | 0 | 185 | 44 | 17 (17) | 0 / 4489 | kv_running_set, api_cpu |
| B3_D48 | 0.45 | 397 | 2.29 / 6.58 / 13.85 / 15.39 | — / — | 0.508 | 98% | 0.00 / 0.94 | 583 / 575 (0.6) | 2,434 / 2,440 | 0.05 / 3.00 (0.03) | 72 | 6 | 0 | 0 | 0 | 4 (4) | 0 / 251 | none |
| C_D48 | 5.18 | 397 | 3,363.97 / 6,842.19 / 7,674.62 / 7,710.58 | 3,625.93 / 7,636.16 | 0.085 | 73% | 0.27 / 0.92 | 740 / 10,911 (0.1) | 4,827 / 46,312 | 0.04 / 5.93 (0.03) | 100 | 3,481 | 0 | 4069 | 7,736 | 46 (46) | 999 / 1136 | gpu_compute, host_capacity |

**Diagnostics (window only; not pre-registered):**

| cell | scrape coverage | upstream of engine med / max | engine queue med / max | GPU util med | API cores med (busiest thread) | served req/s window / drain | body MB/s offered / served |
|---|---|---|---|---|---|---|---|
| A_D32 | 0.96 | 1 / 11 | 0 / 10 | 58 | 1.86 (0.24) | 3.46 / — | 72 / 72 |
| A_D48 | 0.87 | 1,301 / 3,054 | 0 / 8 | 0 | 3.83 (0.58) | 1.79 / 3.45 | 107 / 35 |
| A_D64 | 0.70 | 2,112 / 5,165 | 0 / 9 | 0 | 4.26 (0.56) | 0.93 / 3.35 | 136 / 18 |
| A_D96 | 0.09 | 440 / 6,143 | 0 / 2 | 0 | 4.12 (0.57) | 0.49 / 2.78 | 172 / 9 |
| B1_D48 | 0.96 | 2 / 9 | 1 / 8 | 75 | 1.55 (0.39) | 1.98 / — | 42 / 42 |
| B2_D48 | 0.96 | 3 / 183 | 1 / 71 | 66 | 2.68 (0.35) | 4.98 / 4.04 | 79 / 76 |
| B3_D48 | 0.96 | 0 / 7 | 0 / 8 | 72 | 0.05 (0.03) | 0.45 / — | 10 / 10 |
| C_D48 | 0.85 | 1,277 / 3,055 | 644 / 1,012 | 100 | 3.86 (0.57) | 0.66 / 0.53 | 107 / 14 |

Units: TTFT s; GB = 10⁹ B; PCIe = `kv_offload_load/store_bytes` deltas (window start → drain end) ÷ that elapsed time; "best 30 s" = highest 30-s rolling average load rate. Computed tok/s **achieved** = Σ(prompt − cached) of requests *completed* between window start and drain end ÷ that time; **demand** = Σ(prompt − cached) of requests *submitted* in the window ÷ 900 s. CPU cores from 1-s psutil samples over window + drain (API = the `vllm serve` process; engine = its child tree; harness = this client); GPU util = NVML SM utilisation, 1-s. Upstream = harness in-flight − (engine running + waiting), window only. Errors are all over-context HTTP 400s (sessions past D2's ~708-s limit; at D = 96 a second session reaches it), counted separately and excluded from TTFTs.

## Mechanism verification (Steps 1–5)

**Step 1 — causal chain** (pre-registered). With offload, a warm append costs (i) API-server receipt and decoding of the *whole* history's images (the protocol re-sends the full history every append so the server can match the cached prefix), (ii) host→GPU reload of the prefix not resident on GPU, (iii) GPU compute for the new frames, (iv) running-set GPU KV while the request runs. Per-device load ∝ (1 / cadence) × history size; the knee sits where one of (i)–(iv) or host capacity saturates (FORMULATION.md: physical inertia grows with context; warm-state capacity). B1 cuts the rate 3×, B2 the bytes per image (~25%) and KV bytes per frame (−28%), B3 removes appends.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| (i) API ingestion load ∝ D × history / cadence | offered body MB/s; API cores | 72 → 107 → 136 → 172 MB/s (A); 42 (B1), 79 (B2), 10 (B3); API 1.9 → 3.8–4.3 cores | yes | per-request `body_mb`, 1-s psutil |
| (i) saturates → backlog before the engine | upstream-of-engine queue (window) | median 1 (D32) → 1,301 / 2,113 (D48 / D64); B1 2, B2 3, B3 0 | yes | records × /metrics |
| (ii) host reload ∝ request rate × history | PCIe load GB; host share of hits | 7,275 → 17,741 GB; 96–98% | yes, but not binding (≤ 8.7 GB/s avg, ≤ 16 GB/s best 30 s) | kv_offload counters; 262,144 B/host-hit token in every cell |
| (iii) GPU compute | achieved computed tok/s; SM util | 1.07–2.43k tok/s; util 58% (D32) → 0% (D48+) | yes — *falls* at the knee (GPU starved) | records, NVML |
| (iv) running-set KV | KV usage median / max; engine waiting | in-window median 0–0.07 (256 GiB), max 0.26–1.0 in every cell; engine waiting ≤ 9 in window (B2 69 at the end) | spikes in all cells (non-discriminating) | /metrics |
| host capacity | warm misses; allocation failures; live-set peak | 0–1 misses of 1.7k–4.5k; 0 failures; peak 0.34–0.88× of 256 GiB | not reached at 256 GiB (Part C tests it) | records, counters |

No link is ABSENT. Links (ii)–(iv) and host capacity are present and vary, but are not binding at D\*.

**Step 3 — trace one unit** (a real record from `study_rh6_requests_h100nvl.jsonl.gz`). A D48, device 00, session 3 (video 9902221866524366), append at session time 100 s: 51 D2 frames, body 8.97 MB; scheduled at window +598.1 s, submitted 0.079 s later (harness on time); **1,898 earlier requests were in flight** at submission. Prompt 4,631 tokens, cached 4,176 (cell-level: 97.6% of hit tokens host-served, 262,144 B each → ≈ 1.09 GB reload ≈ 0.02 s at 48–53 GB/s), computed 455 tokens (5 new frames × 90 + 5) ≈ 0.1–0.2 s of prefill. **TTFT 730.5 s**, of which well under 1 s is engine work; the rest is waiting in the API server ahead of the engine (engine running + waiting ≤ 8 throughout the window). Bound: API ingestion — not KV, not compute, not PCIe, not host capacity (0 warm misses in the cell).

**Step 4 — negative control.** The ingestion mechanism is switched off *within the same cells* at window end: arrivals stop while the same queued work remains. The served rate then **doubles to quadruples** (D48 1.79 → 3.45 req/s; D64 0.93 → 3.35; D96 0.49 → 2.78) with no change in the engine, KV or PCIe configuration — the work per served request was not the limit, the concurrent ingestion was. Second control, B2: same request rate as A D48 with ~25% fewer bytes per request → no collapse (median 0.71 s). Third, RH5's committed GPU-only cells remain the offload-disabled control for the host tier (collapse from D = 8 at footprint 1.19×).

**Step 5 — alternative explanations.** (a) *The harness, not the server, is the bottleneck* (one Python process building and sending 20-MB bodies): excluded — submit lag p99 ≤ 0.31 s in every cell (median ≤ 0.03 s), harness ≤ 0.19 cores median, and requests are measured from submission. (b) *GPU running-set KV binds* (RH5's prediction): excluded at D\* — engine waiting ≤ 6 and KV median 0 in the D48 window while 1,300+ requests queue upstream; the GPU is idle. (c) *PCIe or host capacity*: PCIe ≤ 16 GB/s over any 30 s; zero host misses at 256 GiB. (d) *Request count rather than bytes*: B2 (same count, fewer bytes) does not collapse — bytes/images per second is the better descriptor; a pure test (fixed bytes, varied count) was not run.

## Results consistency check

1. **Cross-check vs committed measurements**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| GPU KV capacity | 62,944 | 62,944 | RH5 | 1.00 | agree |
| KV bytes per host-hit token | 262,144 (every cell, ±0.05%) | 262,144 | RH5 Part A | 1.00 | agree |
| D2 tokens per frame | 90 (+41 fixed) | 92 used in RH5/RH6 estimates | RH5 estimate | 0.98 | agree (estimate footprints 2% high) |
| D1 tokens per frame | 65 | 65 | RH4 | 1.00 | agree |
| warm esc TTFT below knee | D32 0.56 s | RH5 GPU+host D16 0.60 / D24 0.81 s | RH5 | 0.69–0.93 | agree (< 2×); RH6's lower value is consistent with RH5's harness serialising each ~20-MB body inside the timed span (httpx `json=` after `t_sub`) — RH6 pre-serialises |
| host share of hits | 96–98% | 92–95% (D16/24) | RH5 | ~1.04 | agree |
| PCIe average load | 5.3–8.7 GB/s | ~6 GB/s (D24) | RH5 | ~1 | agree |
| achieved computed tok/s under compute-bound load | Part C 4.83k | ~5.0k (GPU-only D24 collapse) | RH5 | 0.97 | agree |
| API capacity (req/s, D2) | ~3.4 (drain / D32) | 3.64 (estimate's M/M/1 fit to RH5 D24) | RH6 pre-registration | 0.93 | agree |

2. **Physical plausibility.** Reload rate not re-measured per request; fleet PCIe averages ≤ 8.7 GB/s and 1-s peaks ≤ 29.6 GB/s, below RH5's 48–53 GB/s link rate. Achieved compute ≤ 2.4k tok/s in offload cells (below cold-prefill 3.8–4.5k). API body throughput 72–76 MB/s sustained — no committed reference (new quantity); plausible for a Python HTTP server parsing JSON + base64 PNGs. Nothing exceeds a committed curve by 2×.
3. **Distribution sanity.** All TTFTs reported with median/p90/p99/max; collapsed cells' TTFTs span 0.3–2,443 s; byte-per-token ratio is a constant by architecture (expected). Escalation and append TTFT medians agree closely in collapsed cells (654 vs 660 s) — expected, both wait in the same upstream queue.
4. **Definition audit.** "Warm escalation TTFT", "token hit", "host share" as RH5. "Computed tok/s" now split: **achieved** (completed ÷ elapsed) vs **demand** (submitted ÷ 900 s) — RH5's reported value was demand. "Live-set peak" (new, pre-registered) = Σ current history of devices in a session, 5-s grid. "Warm miss" (new, pre-registered) = cached < 0.5× the previous completed request's prompt in the same device-session. "Upstream queue" (new, diagnostic, not pre-registered).
5. **Claim linkage.** **C4** (physical inertia grows with context): extended — with a host KV tier, the dominant per-append cost at scale is not recompute or reload but **re-transmitting and re-preprocessing the whole history** (bytes ∝ history length), which this serving protocol requires to hit the prefix cache. **C5** (joint representation × placement × timing): supported — the knee is moved by both timing (B1, cadence) and representation size (B2), and lazy placement (B3) trades knee relief for cold-escalation latency (2.3 s vs 0.56–1.33 s). Narrowing: the capacity in RH6 is an **API-server ingestion** limit of this vLLM build and request protocol, not a GPU/KV/PCIe limit; a protocol that sends only new frames (server-side session state) or caches media by id would remove it, so the knee location D\* = 48 is protocol-specific. FORMULATION §Scoping: same-GPU, same-model KV offload — in scope.
6. **Proxy validity.** `external_prefix_cache_hits` = host-served: validated (bytes = tokens × 256 KiB in every cell). `kv_offload_cpu_cache_usage_perc` = fraction of host chunks pinned by in-flight transfers (vLLM source), **not occupancy** — resolves RH5's open item; not used. Upstream queue uses harness in-flight minus engine counts from /metrics; at D96 the API server answered only 9% of in-window scrapes, so D96's upstream distribution is sampled sparsely (D48 87%, D64 70%). API "busiest thread" is a per-sample maximum over threads (not a fixed thread).

## H100 monitoring (this run)

`results/cost/h100_monitoring_summary.json` regenerated with StudyRH6 added: 5 step windows (smoke, Part A, B, C — the first smoke attempt's window is included), 2,090 GPU-3 samples, **0 foreign processes**, no watchdog FOREIGN or memory-floor line, SM clock busy min / median / max 592 / 975 / 1785 MHz (same power-limited operating point as R1–RH5), 12 log files hashed. GPU-3 utilisation (10-s samples) reads 100% median over the chain, dominated by Part C's 2.1-h recompute drain; the per-cell NVML 1-s readings in the tables are the ones used.

## Deviations and notes

- **Smoke run, restarted once:** the first smoke (D = 4, 60 s, scratchpad only) applied the host-hit STOP gate to itself and stopped — D = 4 fits in GPU KV, so it has no host hits by design (RH5 D4: 0.4%). The gate was exempted for the smoke stage only (all RH6 cells keep it) and the chain restarted at 09:15; the smoke then passed (TTFT 0.24 s warm, 0.89 s lazy). No RH6 cell was affected.
- **Waiting-by-reason scraper (observation only, not pre-registered):** a separate 1-s scrape of `vllm:num_requests_waiting_by_reason` (capacity vs deferred) ran from 09:31 (mid-D32) to the end (`logs/queue9_waiting_reason.csv`, not committed); it has the same gaps when the API server stops answering. It showed the post-window engine queue growing as "capacity" in A D48 and Part C; not used for any decision.
- **Diagnostics added after Part A** (queue location, window-only readings, served rates, scrape coverage) because the pre-registered binding thresholds fired in non-breaching cells; labelled as such in `study_rh6_results_h100nvl.json` (`diagnostics`).
- **Estimate:** the model predicted D\* = 32 (service capacity 3.64 req/s vs 3.46 offered — 95% utilisation); D32 held (capacity ≈ 3.4–3.5 req/s, sub-second median) and the knee was D48. Drain lengths were governed by the congestion-collapse served rate (≈ 3.4 req/s once arrivals stop) — close to the model's capacity; Part C's drain was set by recompute (7,736 s actual vs 8,755 s estimated (thrash model, miss 1.00; measured warm-miss fraction 0.88)).
- **Host memory:** with 6,733 requests queued (A D96), the API server's RSS reached 834 GiB (incl. the 256-GiB pinned region) and host MemAvailable fell to 431–456 GiB; the 150-GiB watchdog floor was never reached. On a shared host this is a practical hazard of the full-history protocol under overload.
- **Plan coverage:** no device is without sessions at any D; at D = 64 / 96, 10 / 68 devices run out of sessions before the window ends (2–3 sessions per device at D = 96) — kept in D, so D96's offered rate is 7.97 req/s, not 9.6.
- **Single repetition per cell**, one seed, as pre-registered.

## Files

`experiments/cost/study_rh6_offload_knee.py` (estimate, smoke, Part A/B/C), `experiments/cost/study_rh6_analyse.py`, `experiments/cost/h100_monitoring_summary.py` (RH6 added); `results/cost/study_rh6/`: `study_rh6_requests_h100nvl.jsonl.gz`, `study_rh6_metrics_h100nvl.jsonl.gz`, `study_rh6_cpu_h100nvl.jsonl.gz`, `study_rh6_run_meta_h100nvl.json` (server flags, offload lines, per-cell counters, host verification, D\*, estimate), `study_rh6_results_h100nvl.json`; `results/cost/h100_monitoring_summary.json`.
