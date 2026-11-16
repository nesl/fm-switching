# StudyENG1b-prefix-survival: how long an unreferenced, partly built history prefix survives on the GPU

Pre-registered in `research/EXPERIMENTS.md` (row StudyENG1b-prefix-survival, 2026-11-15, before any run; design answers
by the user 2026-11-15, points 1 to 4). Policy addendum section A6, measurement M5 (`policy_spec_v3_1_addendum.md`).
Host h100nvl GPU 2, exclusive, serial, isolated; run after StudyENG1-steptime had finished and its files were written.
Scripts: `experiments/cost/study_eng1b_survival.py` (runner; reuses StudyENG1's harness unchanged),
`experiments/cost/study_eng1b_analyse.py`. Results: `results/cost/study_eng1b/`.

## 1. Question and design

Between two reconstruction pieces no request holds the already-built prefix: its KV blocks are cached but
unreferenced. In vLLM 0.31.0 such blocks sit in the engine's free queue (freed blocks with a prefix hash are queued in
LRU order; blocks without a hash are reused first) and are the first candidates to be overwritten when other work
allocates KV. The scheduler must price the risk of deferring a piece: how likely is the prefix still resident after a
gap of G seconds under a given KV demand, and what happens to it when it is evicted (lost, or recoverable from the host
tier)?

**Trial.** Fresh D2 namespace; 5 prefix-chained pieces of 23 frames (~2,048 tokens) or 11 frames (~1,024) on a ~28k
StudySLICE1 session (piece 1 cold, cached <= 16; later pieces gap <= 32 tokens); a gap G with background KV demand
starting at the gap start; at the gap end the resume piece (6th piece) is issued regardless of background state.

**Loads (11).** (a) episodic N=1 Poisson at 25 % / 40 % of 15.1 req/s, arrivals over [gap start, gap end + 2 s];
(b) the same plus other devices' history builds (fresh ~26k / shorter D2 histories, one after another) totalling
f x (GPU KV capacity - prefix tokens), f in {0.25, 0.5, 1.0, 1.5}; new filler requests stop being issued once the
target is issued or the resume piece completes; (c) W25 (Poisson 25 % + 8 warm sessions, warm-up before the build,
unscored): ENG1's W25 unchanged on KV-HOST; the 'W25-E0 variant' on E0 runs the same warm sessions without a host tier
(configuration difference from ENG1's W25, which ran only on KV-HOST).

**Grid (trimmed by the user, point 1).** 2,048-token pieces: 11 loads x G {0.5, 2, 5, 10, 20} s x 2 servers x 6
repetitions = 660; 1,024-token pieces: load (b) only x G {2, 10} s x 2 servers x 6 = 192; 852 trials. Server loads:
E0 2,048 (W25 last), KV-HOST 2,048 (W25 last), E0 1,024, KV-HOST 1,024; trial order seeded (random.Random(20261116)).
6-h GPU guard. Rationale (user, stated as required): under the engine's free-block reuse, eviction is driven by how much
KV other work allocates during the gap, so pressure is the primary axis and gap length the secondary one; the analysis
uses the tokens actually allocated by other work before the resume (from the step rows) as the pressure variable.

**Servers.** StudyENG1's E0 (StudySLICE1 E0 + --enable-logging-iteration-details + ENG1 plugin) and KV-HOST (+ native
offloading 256 GiB, StudyE10c C2); non-default args checked exactly per server. The ENG1 plugin was fixed after
StudyENG1 (it dropped every row on KV-HOST servers because the connector's stats have tuple keys); the fix (string keys,
failures logged) is verified in the smoke below.

**Attribution.** The resume piece's prompt tokens are split into LOCAL hit, EXTERNAL (host) hit and computed from the
plugin row of its first-token step (prompt tokens by source); flagged AMBIGUOUS if another request with prefix hits
produced its first token in the same step; cross-checked with Prometheus counter deltas over the resume window.

**KV-pool metric (user point 2).** `kv_cache_usage` = 1 - free blocks / total blocks, and cached-unreferenced blocks are
in the free queue (vLLM 0.31.0 `block_pool.get_usage`), so the metric counts REFERENCED blocks only. No metric reports
the cached-unreferenced count; it is derived from our own bookkeeping (prefix tokens built minus tokens lost).

## 2. Smoke (2026-11-16 01:10 to 01:18, recorded before the full run)

Two servers (SMK_E0, SMK_KVHOST), both non-default-args lines exactly as declared, plugin loaded, not VOID.

| check | result |
|---|---|
| prefix chaining on build (all smoke trials) | every piece gap <= 32 tokens; piece 1 cached 0 |
| concurrency-1 attribution, E0, resume after a 2-s idle gap (2 trials) | step row [computed 2,076, local 10,384, external 0] = API cached 10,384 of a 10,390-token prefix: fully resident |
| concurrency-1 attribution, KV-HOST, forced eviction (filler 1.5 x free pool run to completion, then resume alone; 2 trials) | step row [2,077, 0, 10,384]; counters external_kv_transfer 10,384, local 0: fully evicted from GPU, fully recovered from host |
| plugin rows on KV-HOST after the fix | 370 rows, 0 serialisation errors, connector stats present |
| smoke cell E0, P40 + f 1.0, G 5 s (2 trials) | prefix fully resident (10,384 cached) but resume TTFT 6.12 / 5.59 s: the first filler build (~26k tokens, about 7.5 s) was still prefilling at the gap end, so it had allocated only part of the free pool and the resume piece queued behind its remaining chunks |
| W25 on KV-HOST, G 5 s | prefix fully resident, resume TTFT 0.63 s |
| kv_cache_usage right after the build | 0.0 (the 10.4k-token prefix is cached but unreferenced: confirms the metric counts referenced blocks only) |

**Telemetry distinguishes local from external hits for the prefix** (the pre-registered STOP condition does not
apply). One smoke-cell trial's first-token step row fell outside the first 60-ms matching window; the analysis matches
the step row nearest the client first token within 0.5 s whose step total covers the resume prompt.

(Full-run results follow.)

## 2a. Mechanism verification (CLAUDE.md Steps 1 to 5)

Process note: these steps rest on the smoke checks above, which ran and were recorded before the full run, but this
section was written up after the full run (the ENG1b pre-registration and smoke record stood in for it during the run).

**Step 1, causal chain.** A built prefix whose request has finished is cached but unreferenced (FORMULATION.md section
Constraints 1, ready-capacity: KV that is not held is not ready); other work that allocates KV during a deferral takes
free blocks in free-queue order; once allocation exceeds the blocks not holding the prefix, the prefix's blocks are
overwritten; the resume then either reloads them from the host tier (if one holds them) or recomputes them, and a
deferral decision that ignores this pays the restore cost (FORMULATION.md section Constraints 2, serving feasibility).

**Step 2, links instantiated.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| prefix unreferenced between pieces | kv_cache_usage right after the build | 0.0 (prefix 10.4k tokens cached) | constant by construction (that is the state under test) | smoke, section 6 |
| other work allocates KV | context tokens scheduled before the resume's scheduling | 0 to > 1.5 x the free pool | yes, with fill level and gap | step rows |
| allocation overwrites the prefix | lost prefix tokens | 0 to 10,392 | yes, step at 1.0 of the free pool | section 4 |
| host tier holds evicted KV | external hits of the resume | 0 (E0) / = lost tokens (KV-HOST) | yes, by server | sections 2, 5 |
| restore cost | resume TTFT resident / reload / rebuild | 0.61 / 0.74 / 2.76 s | yes | section 5 |

No link is ABSENT or CONSTANT where it should vary.

**Step 3, traced unit (smoke, KV-HOST forced eviction r0).** Build: 5 pieces, prefix 10,391 tokens, each piece gap
<= 32; filler 1.5 x (62,944 - 10,391) = 78.8k tokens run to completion with nothing else; resume (12,461 prompt tokens):
step row [computed 2,077, local 0, external 10,384]; counters external_kv_transfer 10,384, local_cache_hit 0; i.e. the
whole prefix was overwritten on GPU (allocation 1.5 x the free pool) and recovered from host; the computed 2,077 tokens
are the new piece. On E0 the same allocation makes the resume recompute the prefix (rebuild TTFT 2.76 s, section 5).

**Step 4, negative control.** No KV demand during the gap (smoke conc-1, E0, 2 trials; and load (a) at all gaps):
the prefix is always fully resident (62 / 62 on E0 incl. smoke). Removing the mechanism (allocation) removes the loss.

**Step 5, alternative explanation.** Loss could be driven by elapsed time (a TTL or idle eviction) rather than by
allocation. Distinguished by the data: at G 20 s with episodic load only the prefix always survives (60 / 60 per
server), while at G 10 s with f >= 1.0 it is lost; and with pressure measured at scheduling the outcome is a step
function of allocated tokens independent of gap. A second alternative, preemption of the resume, is excluded (no
preemptions recorded).

## 3. Full run (2026-11-16 01:18 to 05:55)

852 of 852 trials, four server loads (E0_2048, KVHOST_2048, E0_1024, KVHOST_1024), every non-default-args line
exactly as declared, plugin rows on all four loads (0 serialisation errors), KV capacity 62,944 tokens on both E0 and
KV-HOST, **not VOID, 6-h guard not reached** (4 h 37 min). Prefix chaining held on every build (gap <= 32 tokens;
piece 1 cold). Prefix sizes: 10,390 to 10,392 tokens (2,048-token pieces), 4,992 (1,024-token pieces).
Analysis: `experiments/cost/study_eng1b_analyse.py` -> `results/cost/study_eng1b/eng1b_results.json`.

**Attribution.** All 852 resume pieces were attributed from their first-token step row (no fallback); 1 flagged
AMBIGUOUS (an E0 W25 trial where a warm request produced its first token in the same step). The Prometheus counter
deltas over the resume window agree (within 64 tokens) in 840 trials; the 12 disagreements are all W25 trials, where the
warm requests' own prefix hits fall into the window (the concurrency ambiguity StudyENG1 Part D found).

## 4. Survival vs pressure (primary axis)

Pressure is the KV that other work allocated during the gap, as a fraction of the free pool (capacity - prefix
tokens). Two versions: (i) PRE-REGISTERED, allocated before the resume was ISSUED; (ii) allocated before the resume
was SCHEDULED (end of the step before its prefill step). The prefix lookup happens at scheduling, and when the resume
queues behind a still-running filler build the filler keeps allocating between issue and scheduling, so (ii) is the
quantity the eviction actually sees; (i) is reported as registered.

P(prefix fully resident) per pressure bin (n; p_full); 2,048-token pieces, all loads:

| allocated / free pool | E0, before issue (i) | E0, before scheduling (ii) | KV-HOST, (i) | KV-HOST, (ii) |
|---|---|---|---|---|
| 0 to 0.25 | 178; 1.00 | 57; 1.00 | 186; 0.99 | 64; 0.97 |
| 0.25 to 0.5 | 36; 0.92 | 98; 0.99 | 30; 0.83 | 99; 0.95 |
| 0.5 to 0.75 | 51; 0.47 | 72; 0.97 | 57; 0.44 | 74; 0.92 |
| 0.75 to 0.9 | 17; 0.76 | 24; 0.88 | 13; 1.00 | 22; 1.00 |
| 0.9 to 1.0 | 2; 1.00 | 5; 1.00 | 2; 1.00 | 3; 1.00 |
| 1.0 to 1.1 | 8; 0.00 | 9; 0.00 (lost 33 %) | 8; 0.00 | 7; 0.00 (lost 32 %) |
| 1.1 to 1.25 | 4; 0.00 | 0 | 4; 0.00 | 7; 0.00 (lost 60 %) |
| 1.25 to 1.5 | 8; 0.00 | 19; 0.00 (lost 100 %) | 9; 0.00 | 20; 0.00 (lost 100 %) |
| > 1.5 | 26; 0.00 | 46; 0.00 | 21; 0.00 | 34; 0.00 |

1,024-token pieces (load b only), version (ii): E0 0.25 to 0.9: 74; 1.00; 1.1 to 1.5: 22; 0.00. KV-HOST the same
(74; 1.00 and 22; 0.00).

**Result: survival is a step function of allocated KV, not of time.** With pressure measured at scheduling, every
prefix survives while other work has allocated less than the free pool (capacity minus the prefix) and none survives
beyond it: outside W25 the largest fully resident trial is at 0.9998 of the free pool and the smallest loss at 1.055.
Just past the threshold the loss is partial (about a third of the prefix at 1.0 to 1.1, 60 % at 1.1 to 1.25) and from
1.25 it is total. **Partial losses keep the LEADING tokens** (32 partial losses; local hits = the first 3,360 to 5,360
tokens of the prefix): the engine frees a request's blocks tail first, so the tail is overwritten first and a partly
evicted prefix can still be resumed from its surviving head. All 19 losses below 1.0 of the free pool are W25 trials:
the 8 warm sessions re-reference their own cached contexts during the gap (their appends hit cached prefixes), which
moves those blocks behind the prefix in the free queue without counting as new allocation, so for W25 the effective
free pool is smaller than capacity minus prefix.

**Gap length is secondary.** At a fixed gap, survival changes with the fill level; at a fixed fill level, a longer gap
only matters because more filler gets allocated. Episodic-only loads (a) never evicted the prefix (P25 and P40, all
gaps up to 20 s: 60 / 60 fully resident on each server), because episodic requests allocate at most 0.85 of the free
pool in 20 s at 40 % load and release their blocks quickly. Loss appears at G 10 s with f >= 1.0 (and G 20 s with
f >= 0.25 to 0.5), i.e. once enough filler has been allocated, and in W25 from G 5 s (p_full 0.67 at 5 s, 0.17 at
10 s, 0.00 at 20 s, on both servers).

## 5. What happens when the prefix is evicted: P_host and restore time

**P_host = 0.999** on KV-HOST: of 854,898 evicted prefix tokens over 103 trials with eviction, 853,936 came back as
external (host) hits. On E0 every evicted token was recomputed (P_host 0 by construction). The offloading connector
had written every built block to host as it was computed (write-through), so eviction from GPU never lost the KV.

Resume TTFT (median) by outcome; "filler done or none" = no filler build was still running at the resume:

| server, piece | prefix resident | evicted: reload from host | evicted: rebuild |
|---|---|---|---|
| E0, 2,048 | 0.610 s (n 116) | n/a | **2.758 s** (n 39) |
| KV-HOST, 2,048 | 0.621 s (n 117) | **0.738 s** (n 39) | n/a |
| E0 / KV-HOST, 1,024 | 0.322 / 0.326 s | (only with filler running) | (only with filler running) |

Restore cost of a fully evicted ~10.4k-token prefix: +0.12 s by host reload vs +2.15 s by rebuild (18x).

**Queueing behind still-running filler is separate from, and larger than, prefix loss.** When a filler build was
still prefilling at the gap end, the resume piece waited for its remaining chunks: median resume TTFT 6.9 to 7.1 s with
the prefix resident, 8.5 s with a host reload, 9.4 to 9.9 s with a rebuild (E0 / KV-HOST, both piece sizes). The
pre-registered "allocated before resume" version (i) undercounts pressure in exactly these trials.

## 6. KV-pool state at resume (T0 prefix-loss check)

| quantity | value |
|---|---|
| kv_cache_usage right after the build | 0.0 in every trial (median and max) |
| kv_cache_usage at resume | median 0.0 (non-zero only when other requests were running at that instant) |
| what the metric counts | referenced blocks only (`1 - free / total`; cached-unreferenced blocks are in the free queue) |
| cached-unreferenced prefix tokens at resume | not exposed by any metric; derived from our bookkeeping = prefix - lost tokens, recorded per trial (`trials[*].local`) |

So the engine's own usage metric cannot tell the rollout whether a deferred prefix is still there; the rollout's
KV-pool model must track it (capacity, unreferenced cached blocks in free-queue order, and the tokens other work
allocates, including re-referenced warm contexts). Per trial, `results/cost/study_eng1b/eng1b_results.json`
(`trials`) records prefix tokens, local / external / recomputed tokens, allocated tokens before issue and before
scheduling, filler state and resume TTFT: the ground truth for the T0 prefix-loss check.

## 7. Results consistency check (CLAUDE.md, six checks)

1. **Cross-check.** Resume of a resident 2,048-token piece on a ~10.4k prefix: 0.61 s vs StudyENG1 A2 c ~11k s 2,048
   piece 0.564 s (1.08) and SLICE1 chain slice 0.486 s (1.26; SLICE1 slices are 22 frames); host reload of a ~10.4k
   prefix: +0.12 s over resident vs ENG1 Part D +0.067 s for ~11k (both small; ENG1 Part D had no piece frames to
   preprocess); rebuild: 2.76 s vs ENG1 monolithic ~11k 2.67 s (1.03). KV capacity 62,944 tokens = ENG1 / SLICE1. No
   disagreement > 2x.
2. **Physical plausibility.** Host reload: about 10.4k tokens (about 2.7 GB of KV) in about 0.12 s = about 22 GB/s,
   inside PCIe Gen5 x16 and below ENG1's flagged 36 to 44 GB/s single-transfer rate; rebuild 10.4k tokens in about
   2.1 s = 4.9k tok/s (SLICE1 engine-only 5.3k tok/s).
3. **Distribution sanity.** Per-cell n 6 with Wilson intervals in the results file; survival bins report n; lost-token
   distributions are bimodal (0 or the whole prefix) with 32 partial losses, reported. Prefix sizes vary by 1 to 2
   tokens across sessions (10,390 to 10,392), as expected from header tags.
4. **Definition audit.** "fully resident" = local hits >= prefix - 32 tokens (the 32-token chaining tolerance); "lost"
   = prefix - local hits; "recovered from host" = external hits of the resume piece; "free pool" = KV capacity at server
   start - prefix tokens (user point 2); "allocated" = context tokens scheduled by all requests between the gap start
   and the resume's issue (i) or scheduling (ii), from the step rows; "piece", "cold", "host" as in StudyENG1.
5. **Claim linkage.** C4 (physical inertia): supported: losing a built 10.4k prefix costs 2.15 s to rebuild on E0 and
   0.12 s to reload on KV-HOST. C5 (joint policy beats decomposed): not tested; this supplies the A6 deferral-risk
   inputs (survival step function, P_host, restore times). FORMULATION.md section Constraints 1 (ready-capacity:
   KV that does not fit is not ready) is the mechanism measured. Nothing out of scope (same-model KV on host).
6. **Proxy validity.** (i) Allocated-before-issue as pressure: registered but invalid when the resume queues behind
   running filler (the filler keeps allocating); the before-scheduling version is the valid one and is labelled as a
   post-hoc refinement. (ii) Counter deltas as attribution: valid at concurrency 1 (smoke) and in 840 / 852 trials,
   invalid in W25 (12 disagreements); step rows are primary. (iii) kv_cache_usage as KV-pool state: NOT valid for
   unreferenced prefixes (always 0.0 after the build); reported as a limitation of the engine's telemetry.

## 8. Verdicts

- **Survival is a step function of the KV other work allocates before the resume is scheduled**: fully resident below
  1.0 of the free pool, partially lost (tail first) at 1.0 to 1.25, fully lost above 1.25; gap length matters only
  through allocation. Re-referenced warm contexts (W25) shrink the effective free pool (losses from 0.17 of it).
- **P_host = 0.999** (KV-HOST): eviction from GPU loses nothing; restore by reload +0.12 s vs rebuild +2.15 s (18x).
- **The larger deferral cost under filler pressure is queueing, not loss**: a resume issued while another history
  build is prefilling waits 6 to 10 s whether or not the prefix survived.
- **The engine's usage metric does not expose unreferenced prefixes**; the rollout must model the KV pool itself.
- Telemetry distinguishes local from external hits for the prefix (step rows, 852 / 852; 1 ambiguous).
