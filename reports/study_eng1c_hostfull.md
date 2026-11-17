# StudyENG1c-hostfull: the serving stack when the host KV tier is full

Measurement M6 for design decision D56. Pre-registered in `research/EXPERIMENTS.md` (row StudyENG1c-hostfull,
2026-11-16, before any run; design answers by the user 2026-11-16, points 1 to 5 plus the machine-monitor
requirement). Scripts: `experiments/cost/study_eng1c_hostfull.py` (runner), `experiments/cost/study_eng1c_analyse.py`
(analysis). Results: `results/cost/study_eng1c/`. Run: h100nvl GPU 2, 2026-11-16 15:36 to 2026-11-17 03:30
(11 h 54 min), 16 server starts, not VOID, every part finished.

## 1. Question and design

Under write-through offloading (every block computed on GPU is also stored on host), what does the host tier buy when
it is FULL, and how should a scheduler price GPU-warm, host-warm and cold histories for any capacity?

**Stack.** StudyENG1 KV-HOST exactly: Qwen3-VL-32B-Instruct @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags, native
offloading connector, `--enable-logging-iteration-details`, the fixed ENG1 stat-logger plugin, prefix caching on,
processor cache 128 GiB. Only `--kv-offloading-size` differs. At every start the flag list was diffed against ENG1
KV-HOST (diff = the size value only, or empty at 256) and the non-default args were checked exactly.

**Caps (user point 1).** One host chunk is one 16-token block (`blocks_per_chunk = 1`) at 256 KiB per token, so
C GiB holds C x 4,096 tokens. The GPU pool is 62,944 tokens (15.4 GiB). Caps were chosen by the host space BEYOND
the GPU pool:

| cap | host tokens | beyond GPU (tokens) | beyond GPU (11,184-token histories) | mmap in server log | enforced |
|---|---|---|---|---|---|
| 12 GiB (demonstration) | 49,152 | -13,792 | -1.23 | 12.88 GB | yes |
| 27 GiB | 110,592 | 47,648 | 4.26 | 28.99 GB | yes |
| 38 GiB | 155,648 | 92,704 | 8.29 | 40.80 GB | yes |
| 60 GiB | 245,760 | 182,816 | 16.35 | 64.42 GB | yes |
| 256 GiB (reference) | 1,048,576 | 985,632 | 88.1 | 274.88 GB | yes |

The mmap size equals the cap in bytes in every one of the 16 starts, and server RSS tracks it (17 / 32 / 44 / 65 /
261 GiB). The GPU pool was 62,944 tokens at every start.

**Harness simulator.** A chunk-level two-tier model (GPU and host, both LRU-ordered) replays every completed request
under four candidate host eviction rules: FIFO by store time, LRU by any access, LRU by host access only, and the
code reading (R4, below). It wrote per-rule predictions to `eng1c_pred_h100nvl.jsonl` BEFORE every Part A probe and
gives the write-order ground truth (tier at arrival) for Parts C and D.

**Code reading (pre-registered as Part A's prediction, from the vLLM 0.31.0 source).** Host eviction is LRU
(`cpu/policies/lru.py`, the default). A chunk's recency is set when it is stored and refreshed when a request that
used it finishes. A request served wholly from GPU re-offers its whole prompt to the store (the connector skips hits
only on the host-load path, `CHUNK_LEVEL`), so it refreshes, and re-stores, its host copies. A request with a host
load refreshes only the chunks it loaded and computed, not the GPU-hit chunks in front of them. Misses refresh
nothing. Within a history the tail is evicted first.

**Parts.** A: eviction rule and touch (6 patterns x 3 caps x 5 reps + 12 GiB x 5). B: P_host vs host occupancy
(ENG1b deferral trial; 310 trials). C: telemetry host vs cold at concurrency 1, 4, 8 (3 caps, 55 rounds each).
D: paired churn with / without (4 servers x 2 loads x 3 rebuild variants x 20 pairs; 120 HOLDOUT pairs recorded and
not analysed). E: host-full tax (20 identical P25 traces per server). Machine monitor: every 5 s, all four GPUs'
utilization, memory and power plus host MemAvailable (8,218 samples).

## 2. Smoke (2026-11-16 15:05 to 15:30, before the full run)

- Cap enforcement at 12 GiB and 27 GiB (new cap) and 256 GiB: mmap = cap; GPU pool 62,944; flags diff = size only.
- **256 GiB reproduction of ENG1b (stop condition): PASS.** P_host 0.999 (ENG1b 0.999); reload minus resident
  +0.109 s (ENG1b +0.12 s); rebuild (12 GiB, where the host cannot hold the prefix) minus resident +2.23 s
  (ENG1b +2.15 s).
- Parts C, D, E code paths exercised at 27 GiB; 0 cached-token mismatches in 138 paired comparisons.
- Implementation fixes before the full run (reported, not methodological): (1) Part B occupancy build passed the
  namespace twice (crash); (2) Part C setup passed the cap twice; (3) Part B's simulator prediction at resume ignored
  background requests that had already finished (it now feeds them first); (4) Part D's tier check summed cached
  tokens over a piece rebuild's chained requests (it now uses the first request).
- Process note: an analysis-script compile check was attempted once while a server was up during the full run; the
  permission layer denied it, so no Python of ours ran; the edit was made with the editor and compiled after the run.

## 2a. Mechanism verification (CLAUDE.md Steps 1 to 5)

**Step 1. Causal chain.** The policy prices a history by its storage tier (FORMULATION.md physical component of
context inertia: reconstruction cost grows with context length; host reload is cheap, rebuild is expensive). The
host tier can only supply a reload if the history's chunks are still on host when it is needed; under write-through
every computed block is written to host, so host residency is decided by the host's eviction rule and by how much
other work is written after the history. Therefore: eviction rule + write volume after the history + cap -> which
tier a history is in at arrival -> whether its next request is a 0.1 s reload or a 2.2 s rebuild -> how much delay it
imposes on everyone else.

**Step 2. Instantiation.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| host capacity | --kv-offloading-size, mmap bytes | 12 / 27 / 38 / 60 / 256 GiB | yes | section 1 table |
| write volume after the history | occupancy builds + filler + episodic tokens | 0 to 259k tokens | yes | B occ_tokens 0 to 258,930 |
| host residency at arrival | external (host) tokens of the probe / resume | 0 to 11,200 tokens | yes | A, B, C |
| restore cost | resume / job TTFT | 0.08 s (GPU) to 3.4 s (rebuild in pieces) | yes | B restore, D by tier |
| imposed delay | sum of background latency deltas, with minus without | -0.3 to 21 s | yes | D |

No link is ABSENT or CONSTANT.

**Step 3. Trace of one unit (Part B, 38 GiB, occupancy 0, rep 10, 2026-11-16 20:06).** Target: 5 prefix-chained
2,048-token pieces, prefix 10,394 tokens (written to host as computed). Occupancy: 0 tokens. Gap 30 s: P25 episodic
(about 46k tokens written) + filler 78,888 tokens (target 1.5 x (62,944 - 10,394) = 78,825). Written after the
target: about 125k + target 10.4k = 135k < 155,648 host tokens, so LRU keeps the target on host; 78.9k > the free GPU
pool, so the GPU has evicted it. Resume (6th piece): local 0, external 10,384, computed the new piece; TTFT 0.755 s.
Bound: GPU KV (evicted) but not host (kept). Outcome: reload. The simulator predicted host 10,352 tokens.

**Step 4. Negative control.** Two controls disable the mechanism. (a) Host smaller than the GPU pool (12 GiB): under
write-through + LRU the host keeps only what the GPU also keeps, so the host tier must add nothing. Observed: Part A
PF 5 / 5 cold (the same pattern gives a full host reload at 27 to 60 GiB), Part B 20 / 20 rebuilt, 0 tokens from
host. (b) Occupancy made OLDER than the target (38 GiB, occupancy 0.9 built before the target): if LRU ordering is the
mechanism, the same 90 % host occupancy must not hurt the target. Observed: 20 / 20 full reloads, against 0 / 20 when
the same occupancy is newer.

**Step 5. Alternative explanation.** "Recovery falls because the host is fuller" (occupancy as such) vs "recovery
falls because more is written after the history" (LRU age). They predict the same for newer occupancy and opposite
results for older occupancy; control (b) separates them: age, not fullness, decides. For Part A, "FIFO with some
noise" vs the code reading: PH (touch while host-only keeps the history) rules out FIFO 15 / 15; PM (mixed touch loses
it) rules out LRU-any 15 / 15; PG with a non-aligned prompt (touch while GPU-resident keeps it) rules out LRU host-only
12 / 12.

## 3. Part A: the host eviction rule and whether touching protects a history

Target T (fresh ~11k history), then filler; patterns (S = T's tokens, Hc = host tokens, margin 10k):
PF = GPU pool + 10k written after T; P0a = Hc - S - 10k; P0b = Hc + 10k; PG = 0.6 (GPU pool - S), touch T while
GPU-resident, then Hc - S - 10k; PH = GPU pool + 10k, touch T while host-only, then Hc - S - 10k; PM = GPU pool - S/2
(head on GPU, tail on host), touch, then Hc - S - 10k. The touch is T's full prompt sent with uuid references only
(a tiny body), max_tokens 1.

| cap | PF | P0a | P0b | PG | PH | PM |
|---|---|---|---|---|---|---|
| 12 GiB | cold 5 / 5 | | | | | |
| 27 GiB | host 5 / 5 | host 5 / 5 | cold 5 / 5 | host 4, cold 1 | host 5 / 5 | cold 5 / 5 |
| 38 GiB | host 5 / 5 | host 5 / 5 | cold 5 / 5 | host 3, cold 2 | host 5 / 5 | cold 5 / 5 |
| 60 GiB | host 5 / 5 | host 5 / 5 | cold 5 / 5 | host 5 / 5 | host 5 / 5 | cold 5 / 5 |

Matches with each rule's pre-written prediction (95 target probes): FIFO 68, LRU any access 77, LRU host access only
83, code reading 92. **The code reading conditioned on the observed touch path matches 95 / 95** (post hoc,
labelled): the three misses are all PG trials whose target prompt was 11,024 tokens, an exact multiple of the
16-token block. There the touch was served 11,008 tokens from GPU and 16 from host: vLLM must compute at least the
last token, so a block-aligned prompt cannot take its last block as a GPU hit; the connector loads that one block
from host, the request takes the host-load path, and the GPU-served head is not refreshed. Every PG trial with a
non-aligned prompt (12 / 12) was served wholly from GPU and stayed on host. The simulator did not model the forced
last-block recompute, which is why its pre-written prediction missed these three.

**Rule identified: LRU, refreshed by the code-reading rule.** A chunk becomes most recent when stored and when a
request that used it finishes; a request served WHOLLY from GPU refreshes all of its prefix on host; a request that
loads ANYTHING from host refreshes only what it loaded; within a history the tail goes first.

**Does touching keep a history host-resident?**

- Host-only history (PH): **yes, 15 / 15.** The touch reloads it and refreshes every chunk.
- GPU-resident history (PG): **yes if the touch is served wholly from GPU (12 / 12); no if even one chunk comes from
  host (0 / 3).** A block-aligned prompt always takes its last block from host when the history is on host as well;
  a touch that adds one token past the history avoids it.
- Partly GPU, partly host (PM): **no, 0 / 15.** The touch loads the tail from host and leaves the GPU-served head
  unrefreshed; the head then ages out first and the prefix lookup fails at chunk 0, so the WHOLE history is lost
  although its tail is still on host.

**Probe effect.** Witness histories (the first filler of the last segment) matched the simulator's prediction in
every trial, whether probed first or second; no probe changed another history's residency beyond what the
prediction already included.

## 4. Part B: P_host as a function of host occupancy

ENG1b trial (5 prefix-chained 2,048-token pieces, prefix about 10.4k), occupancy histories of occ x (Hc - prefix)
tokens built after the target (other devices served during the pause), then a 30-s gap with P25 episodic and filler
of 1.5 x the free GPU pool (about 78.8k tokens), resume at the gap end regardless. Recovered fraction = host-loaded /
evicted prefix tokens. Every one of the 300 loaded trials lost the prefix from GPU.

| cap | occupancy | n | full recovery (Wilson 95 % CI) | recovered token fraction (95 % CI) | resume TTFT median (filler done) |
|---|---|---|---|---|---|
| 12 | 0 | 20 | 0.00 (0.00, 0.16) | 0.000 | 2.79 s |
| 27 | 0 | 20 | 0.00 (0.00, 0.16) | 0.000 | 2.78 s |
| 27 | 0.5 / 0.9 / 1.1 | 20 each | 0.00 each | 0.000 each | 2.78 / 2.79 / 2.78 s |
| 38 | 0 | 20 | **1.00 (0.84, 1.00)** | 0.999 | 0.75 s |
| 38 | 0.5 / 0.9 / 1.1 | 20 each | 0.00 each | 0.000 each | 2.77 / 2.76 / 2.78 s |
| 38 | 0.9, occupancy OLDER (control) | 20 | **1.00 (0.84, 1.00)** | 0.999 | 0.75 s |
| 60 | 0 | 20 | **1.00 (0.84, 1.00)** | 0.999 | 0.75 s |
| 60 | 0.5 | 20 | 0.15 (0.05, 0.36) | **0.568 (0.40, 0.74)** | 1.45 s |
| 60 | 0.9 / 1.1 | 20 each | 0.00 each | 0.000 each | 2.80 / 2.79 s |
| 256 | 0 | 20 | **1.00 (0.84, 1.00)** | 0.999 | 0.82 s |

Restore times (filler finished or no load): resident 0.662 s (n 10), host reload 0.756 s (n 76), rebuild 2.781 s
(n 198); reload +0.094 s, rebuild +2.119 s over resident (ENG1b +0.12 / +2.15 s). At 60 GiB occupancy 0.5 the 20
trials span the boundary: 3 full reloads, 13 partial (tail lost, head kept), 4 rebuilds.

**Recovery is decided by how much is written after the history, not by how full the host is.** The simulator,
which counts every token written after the target (occupancy, filler and episodic), predicted the recovered tokens of
298 / 300 loaded trials within 1,024 tokens (median error 0, max 6,528). The 90 % older-occupancy control recovers
fully where the same newer occupancy recovers nothing.

**Pre-registered prediction corrected (disclosed).** The pre-registered hand calculation predicted full recovery at
27 GiB occupancy 0 and partial recovery (about 0.4) at 38 GiB occupancy 0.5. It omitted the P25 episodic traffic of
the gap (about 46k tokens in 32 s). With it, 27 GiB occupancy 0 writes about 135k tokens after the target, over the
110.6k cap, and 38 GiB occupancy 0.5 writes about 208k, over 155.6k. The observations match the corrected count
and the simulator (which was pre-registered and counts the episodic writes); the design was not changed.

## 5. Part C: can telemetry tell host-resident from cold when the host is full?

States by construction per slot: host (built, then a GPU-flush filler of GPU pool + 10k), gpu (built after the
flush), cold (built at least one round earlier, untouched, with >= Hc + 10k tokens written since and no residency
under any candidate rule; else a never-built history, cold_fresh: 10 of 590 probes). Probes issued concurrently.

| cap | concurrency | probes (host / cold / gpu) | API cached tokens: host vs cold correct | ENG1 metric-delta classifier, 3-way | round external counter: host count correct | simulator vs construction |
|---|---|---|---|---|---|---|
| 27 | 1 | 30 (11 / 12 / 9) | 100 % | 100 % | 100 % | 100 % |
| 27 | 4 | 60 (22 / 24 / 14) | 97.8 % | 46.7 % | 93.3 % | 98.3 % |
| 27 | 8 | 80 (16 / 38 / 26) | **75.9 %** | 27.5 % | 40.0 % | 87.5 % |
| 38 | 1 | 30 (9 / 13 / 11) | 100 % | 100 % | 100 % | 100 % |
| 38 | 4 | 60 (17 / 19 / 24) | 100 % | 41.7 % | 100 % | 100 % |
| 38 | 8 | 80 (27 / 24 / 29) | 94.1 % | 42.5 % | 40.0 % | 100 % |
| 60 | 1 | 30 (7 / 20 / 8) | 100 % | 100 % | 100 % | 100 % |
| 60 | 4 | 60 (21 / 17 / 22) | 100 % | 38.3 % | 100 % | 100 % |
| 60 | 8 | 80 (23 / 37 / 20) | 100 % | 33.8 % | 50.0 % | 100 % |

The per-request API cached tokens are the usable signal at every concurrency: they count local and host hits for
that request. ENG1's classifier (Prometheus deltas from the round start to each request's end) works only at
concurrency 1, because the deltas aggregate across concurrent requests. The round-aggregate external counter
recovers the host count at concurrency 1 and 4 but not 8.

**The errors at 27 GiB are not telemetry errors; the state changed between arrival and scheduling.**
Host-constructed histories fully recovered from host at scheduling (at least 90 % of the history's tokens):

| cap | concurrency 1 | concurrency 4 | concurrency 8 |
|---|---|---|---|
| 27 GiB | 11 / 11 | 16 / 22 (6 partial) | 3 / 16 (1 partial, 12 cold) |
| 38 GiB | 9 / 9 | 17 / 17 | 23 / 27 (4 partial) |
| 60 GiB | 7 / 7 | 21 / 21 | 23 / 23 |

(The API column above scores a probe "host" when at least 50 % of it hit, so partial loads count as host there.) A queued request pins nothing; the concurrent cold rebuilds (about 11k tokens each, eight requests
exceed the GPU pool) write through to host as they complete and evict the waiting host histories when the host
window beyond the GPU is small (27 GiB: 47.6k tokens). The cached-token count correctly reports the state at
scheduling; "host-warm at arrival" is not a stable state under concurrent cold work in a small window.

## 6. Part D: cost of churn (FIT trials; HOLDOUT recorded, not analysed)

Population 2 x cap in histories (27: 20, 38: 28, 60: 44; 256 uses 44). Per trial the injected job is the device's
next request on a uniformly drawn member: resident (by write order) -> one request; cold -> rebuild as one request
(mono) or as prefix-chained pieces of 23 / 11 frames. Imposed delay = sum over the trace's background requests of
(with - without) latency. 360 FIT pairs, 120 HOLDOUT pairs recorded and not analysed (split written before any run:
`results/cost/study_eng1c/eng1c_holdout_split.json`). **0 cached-token mismatches in 18,768 paired background
comparisons.** Tier at arrival (simulator) agreed with the job's first-request cached tokens in 354 / 360 pairs (5
predicted host but lost by scheduling, 1 predicted cold but warm).

Job TTFT, completion and imposed delay per cell (median [p10, p90]; noise = median |repeat - without| over 3
independent repeats per cell):

| cap | load | variant | job TTFT s | completion s | imposed delay s | noise s | tiers (gpu / host / partial / cold) |
|---|---|---|---|---|---|---|---|
| 27 | P25 | mono | 2.25 [0.10, 2.31] | 2.46 | 10.8 [-0.05, 19.2] | 0.15 | 4 / 1 / 1 / 9 |
| 27 | P25 | piece2048 | 2.85 [0.12, 3.01] | 2.88 | 4.50 [-0.03, 7.06] | 0.02 | 2 / 2 / 0 / 11 |
| 27 | P25 | piece1024 | 3.18 [0.22, 3.43] | 3.27 | 2.94 [0.12, 3.79] | 0.07 | 2 / 2 / 0 / 11 |
| 27 | S2 | mono | 2.26 [0.17, 2.31] | 2.57 | 14.2 [0.09, 16.3] | 0.10 | 2 / 1 / 0 / 12 |
| 27 | S2 | piece2048 | 2.96 [0.75, 3.00] | 3.00 | 6.03 [1.96, 6.75] | 0.02 | 1 / 2 / 0 / 12 |
| 27 | S2 | piece1024 | 3.38 [3.23, 3.54] | 3.45 | 3.20 [2.90, 3.44] | 0.07 | 0 / 1 / 1 / 13 |
| 38 | P25 | mono | 2.22 [0.13, 2.30] | 2.43 | 6.57 [0.02, 18.5] | 0.19 | 2 / 3 / 0 / 10 |
| 38 | P25 | piece2048 | 2.92 [2.79, 3.35] | 3.01 | 5.58 [3.69, 11.5] | 0.01 | 0 / 1 / 1 / 13 |
| 38 | P25 | piece1024 | 3.31 [3.04, 3.60] | 3.33 | 2.49 [1.56, 4.56] | 0.06 | 1 / 0 / 0 / 14 |
| 38 | S2 | mono | 2.23 [0.11, 2.26] | 2.55 | 13.5 [0.06, 14.8] | 0.05 | 3 / 1 / 2 / 9 |
| 38 | S2 | piece2048 | 2.89 [0.16, 3.00] | 2.93 | 5.15 [0.00, 6.29] | 0.08 | 2 / 2 / 1 / 10 |
| 38 | S2 | piece1024 | 3.35 [0.14, 3.51] | 3.37 | 3.05 [0.04, 3.22] | 0.02 | 3 / 0 / 0 / 12 |
| 60 | P25 | mono | 2.24 [0.97, 2.36] | 2.56 | 14.5 [1.91, 21.1] | 0.05 | 0 / 2 / 0 / 13 |
| 60 | P25 | piece2048 | 3.00 [2.65, 3.41] | 3.03 | 5.74 [2.82, 11.9] | 0.03 | 1 / 0 / 0 / 14 |
| 60 | P25 | piece1024 | 3.21 [0.13, 3.54] | 3.24 | 2.50 [-0.05, 3.66] | 0.06 | 2 / 2 / 0 / 11 |
| 60 | S2 | mono | 2.24 [1.01, 2.27] | 2.58 | 13.6 [4.87, 15.1] | 0.19 | 0 / 3 / 0 / 12 |
| 60 | S2 | piece2048 | 2.93 [0.99, 3.03] | 2.97 | 5.75 [1.98, 6.84] | 0.02 | 2 / 1 / 0 / 12 |
| 60 | S2 | piece1024 | 3.33 [0.18, 3.48] | 3.37 | 3.01 [0.06, 3.43] | 0.04 | 1 / 4 / 1 / 9 |
| 256 | P25 | mono | 0.23 [0.15, 2.27] | 0.26 | 0.05 [-0.01, 15.2] | 0.06 | 0 / 12 / 0 / 3 |
| 256 | P25 | piece2048 | 0.35 [0.14, 3.07] | 0.37 | 0.46 [-0.08, 6.50] | 0.03 | 2 / 6 / 0 / 7 |
| 256 | P25 | piece1024 | 0.22 [0.11, 3.30] | 0.25 | 0.07 [-0.10, 3.12] | 0.05 | 2 / 10 / 0 / 3 |
| 256 | S2 | mono | 0.24 [0.15, 2.26] | 0.27 | 0.02 [-0.04, 14.7] | 0.03 | 2 / 10 / 0 / 3 |
| 256 | S2 | piece2048 | 0.21 [0.15, 0.33] | 0.24 | 0.01 [-0.05, 0.11] | 0.04 | 1 / 13 / 0 / 1 |
| 256 | S2 | piece1024 | 0.19 [0.15, 3.31] | 0.23 | 0.04 [-0.04, 3.05] | 0.03 | 1 / 10 / 0 / 4 |

By tier at arrival (cell medians per tier): GPU-warm job TTFT 0.08 to 0.28 s, imposed -0.3 to 0.2 s; host-warm job
TTFT 0.13 to 0.25 s and imposed about 0 s, except four 27 / 60 GiB cells (n 1 to 2) whose predicted-host histories
were lost by scheduling (job TTFT 0.88 to 2.15 s, imposed 1.8 to 12 s; the tier mismatches above); cold job TTFT
2.24 to 2.32 s (mono), 2.8 to 3.0 s (2,048 pieces), 3.3 to 3.4 s (1,024 pieces); cold imposed delay 14.0 to 16.5 s
(mono), 3.8 to 6.2 s (2,048 pieces), 2.9 to 3.6 s (1,024 pieces). The capped servers see cold arrivals in 9 to 14 of 15 trials per cell; the 256 GiB reference holds
the whole population, so most arrivals are host-warm and the cell medians fall to about 0.2 s and about 0 s.

## 7. Part E: is there a host-full tax?

20 identical P25 traces (764 episodic requests) per server; "empty" = fresh 256 GiB server before its population;
"full" = after Part D at 27 / 38 / 60 GiB (host full with ongoing write-through evictions).

| condition | TTFT median (95 % CI) | TTFT p90 | step median (95 % CI) |
|---|---|---|---|
| 256 empty | 0.1623 (0.1593, 0.1664) | 0.2249 | 24.9 ms (24.8, 25.0) |
| 27 full | 0.1459 (0.1451, 0.1470) | 0.2074 | 25.0 ms (24.9, 25.1) |
| 38 full | 0.1464 (0.1455, 0.1474) | 0.2082 | 25.1 ms (25.0, 25.2) |
| 60 full | 0.1465 (0.1458, 0.1473) | 0.2074 | 25.1 ms (25.0, 25.1) |

Pre-registered comparison (full minus empty TTFT): -16.4 / -15.8 / -15.8 ms, CI excluding 0: the full host is
FASTER. This comparison is confounded by order: the empty traces were the first workload on a freshly started server,
and traces 2 to 8 ran slow (0.17 to 0.195 s median) before settling at 0.147 to 0.151 s; the full traces are flat
(0.143 to 0.154 s). Post hoc, labelled: on the last 10 traces only, full minus empty = -3.5 (-4.8, -1.8), -2.6
(-4.0, -1.2), -2.1 (-3.3, -0.6) ms, and step time 25.02 / 24.99 ms full vs 24.89 ms empty (+0.1 ms, +0.5 %).
**No host-full tax is detectable: TTFT is not slower when the host is full; step time is at most about 0.5 % longer.**

## 8. Machine monitor (user requirement)

GPU 3 (another user's vLLM) was at 100 % utilization and 79.9 GB in every one of 8,218 samples over the whole run,
so every trial overlapped GPU 3 activity and every trial is flagged; **no GPU 3 active vs idle comparison is
possible** for Parts D and E because GPU 3 was never idle. Host MemAvailable never fell below 1,148 GiB (median 1,365
GiB); every server start had at least cap + 192 GiB available. GPUs 0 and 1 stayed idle.

## 9. Results consistency check (CLAUDE.md, six checks)

1. **Cross-check against committed measurements.**

| quantity | this run | prior run | source | ratio | agree |
|---|---|---|---|---|---|
| P_host, roomy host | 0.999 (256 GiB) | 0.999 | StudyENG1b | 1.00 | yes |
| reload over resident (~10.4k) | +0.094 s | +0.12 s | StudyENG1b | 0.78 | yes |
| rebuild over resident (~10.4k) | +2.119 s | +2.15 s | StudyENG1b | 0.99 | yes |
| resident resume TTFT | 0.662 s | 0.621 s | StudyENG1b | 1.07 | yes |
| host-warm query TTFT, ~11k, conc 1 | 0.169 to 0.179 s | 0.167 s | StudyENG1 Part D | 1.04 | yes |
| cold query TTFT, ~11k, conc 1 | 2.19 to 2.23 s | 2.74 s | StudyENG1 Part D | 0.81 | yes (within 2x; ENG1 sent image bytes, here uuid references) |
| cold mono11k imposed delay | 10.8 to 14.7 s | 16 to 71 s (P25 / P40 / S2 / S4) | StudyENG1 Part C | about 0.3 to 0.9 | yes (within range at P25 / S2) |
| GPU pool | 62,944 tokens | 62,944 | StudyENG1 / ENG1b | 1.00 | yes |

2. **Physical plausibility.** Host reload of about 10.4k tokens (2.7 GB of KV) in about 0.094 s = about 29 GB/s,
   within PCIe Gen5 x16 (ENG1b: 22 GB/s). Cold rebuild of about 11k tokens in about 2.1 to 2.2 s = about 5k tokens/s,
   including vision encoding, consistent with ENG1 builds (about 4k tokens/s with byte upload). Nothing faster than
   the committed curves.
3. **Distribution sanity.** Every table reports p10 / p90 or CI; recovery fractions are 0 / 1 by construction except
   the 60 GiB occupancy 0.5 cell, which spans 0 to 1 (13 partial trials); TTFTs vary across trials (no constants).
4. **Definition audit.** "History" = a StudySLICE1 ~11k D2 session (10,843 to 11,205 tokens; nominal 11,184 in D56).
   "Prefix" (B) = 5 x 2,048-token pieces (10,392 to 10,394 tokens), as ENG1b. "Recovered fraction" = host-loaded /
   evicted-from-GPU prefix tokens, as ENG1b P_host. "Cold" = no residency on either tier. "Imposed delay" = sum of
   background latency deltas, as ENG1 Part C. "Occupancy" = occ x (Hc - prefix) tokens of other histories. Same names,
   same definitions as ENG1 / ENG1b.
5. **Claim linkage.** C4 (physical inertia): supported and sharpened: the reload / rebuild gap (+0.09 s vs +2.1 s;
   about 0 s vs 14 s imposed on others) holds at every cap, but whether a history is host-warm depends on the write
   volume after it relative to the cap, not on the host being "on". C5 (joint policy beats decomposed): not tested;
   supplies the tier-pricing inputs for D56.
6. **Proxy validity.** Tier at arrival in Part D is a simulator output (write order), validated against the first
   request's cached tokens (354 / 360). Part C ground truth is by construction, validated by the simulator (87.5 % at
   27 GiB concurrency 8 because of loss between arrival and scheduling, 98 to 100 % elsewhere). Part E's
   empty-vs-full comparison is a confounded proxy for "host-full tax" (order); reported as such.

**Result: PASS 6 / 6 with two labelled deviations** (the corrected B hand prediction; Part E order confound).

## 10. Verdicts

- **A (eviction rule): IDENTIFIED.** Host LRU with the code-reading refresh rule (95 / 95 with the observed touch
  path; 92 / 95 with the simulator's pre-written path, the 3 misses being block-aligned prompts). Touching keeps a
  host-only history (15 / 15) and a GPU-resident one only when the touch is served wholly from GPU (12 / 12 vs 0 / 3);
  a mixed touch loses the whole history (0 / 15).
- **B (P_host vs occupancy): A STEP IN WRITE VOLUME AFTER THE HISTORY.** Full recovery at 38 / 60 / 256 GiB when
  little is written after the history; zero when more than the cap is written after it; partial (tail lost) at the
  boundary (60 GiB occupancy 0.5: token fraction 0.57). Older occupancy is harmless (20 / 20). 12 GiB: zero.
- **C (telemetry): PER-REQUEST CACHED TOKENS REPORT THE STATE AT SCHEDULING CORRECTLY AT EVERY CONCURRENCY**
  (100 % against construction at 60 GiB; the 27 GiB errors, 75.9 % at concurrency 8, and 4 partial loads at 38 GiB
  are real loss of host state between arrival and scheduling, not telemetry errors). Aggregate Prometheus deltas fail
  above concurrency 1.
- **D (churn cost): COLD ARRIVALS DOMINATE.** Cold mono rebuild imposes about 14 s on others; pieces cut it to about
  6 s (2,048) and 3 s (1,024) at a cost of +0.7 to +1.1 s job TTFT; warm arrivals impose about 0 s.
- **E (host-full tax): NOT DETECTED.** At most +0.5 % step time; TTFT not slower.

## 11. Implications for the policy (interpretation, separate from the measurements above)

1. **Price host residency by write volume, not by host occupancy.** A history is host-warm iff the tokens written
   to host after its last refresh are below the cap; GPU-warm iff they are below the free GPU pool. Both are
   computable from the scheduler's own bookkeeping (StudyT0's pool bookkeeping extends to the host tier with the cap
   as a second threshold).
2. **A host tier smaller than the GPU pool is worth nothing** under write-through and shared LRU; only cap - GPU pool
   counts.
3. **Touch rule.** To keep a history host-warm, touch it with its full prompt plus one token while it is wholly on GPU
   or wholly on host; never touch a half-evicted history (that loses it entirely); avoid block-aligned touch prompts.
4. **Concurrency.** Host-warm is not stable while cold rebuilds run concurrently in a small window; a scheduler that
   admits a host-warm job behind several cold ones in a small host window should price it as possibly cold.
5. **Cold rebuild shape.** Under background load, rebuilding in 1,024-token pieces imposes about 4 to 5x less delay on
   others than a monolithic rebuild for about +1 s job TTFT.
6. **No host-full surcharge** is needed on ordinary requests.

## 12. Files

Created: `experiments/cost/study_eng1c_hostfull.py`, `experiments/cost/study_eng1c_analyse.py`,
`reports/study_eng1c_hostfull.md`, `results/cost/study_eng1c/` (holdout split, part A to E rows, predictions,
B trials, frontend rows, steps, machine and exclusivity monitors, run meta, results JSON, smoke files).
Changed: `research/EXPERIMENTS.md` (pre-registration row, then verdict), `results/INDEX.md`, `research/STATUS.md`.
