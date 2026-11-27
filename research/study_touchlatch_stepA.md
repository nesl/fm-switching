# D319 STEP A: facts (CPU, read-only, origin tip 5a28f4ac; cells committed on origin; scripts preplay.py, stepa2..5.py in this dir)

Scope: three halved cells (candidate cell (2), pwire halved, committed -la-er halved). Register: OBSERVED from committed logs, except P predictions, which are an OFFLINE REPLAY of the shadow (candidate flags engine_resync + host_engine_model fed with the cell's own request log); the replay reproduces the live counters (cand: 7,602 sends and 6,450 resyncs against live 7,607 and 6,488).

## 1. Is live2_d261_cold_unlatch on in the candidate? NO.
`make_rung3(..., cold_unlatch=None)` follows `d249_queue_visibility` (arms_final_ladder.py:550); the candidate (arms_v6cfr3.py `r3cand`) passes neither, so `d249_queue_visibility=False` and the unlatch is OFF. Only `covex-v6-fair-final-q` and `-unlatch` turn it on (arms_v6cfr3.py:789, 793). The header switch record has no d261 key (run_live2_real.py:229-250 does not list it); the counters `d261_*` are absent in all five cells, as expected for an OFF switch.

## 2. Cell (2): how many sessions latched?  TWO sessions (not many).
| session | TOUCH chosen | issued | refused | refusal window | what started it |
|---|---|---|---|---|---|
| robo006 s001 | 1,284 | 0 | 1,284 | 780.7 to 914.4 s (134 s) | piece pt=9,011 at t=778.5 read cached_tokens 0; completed 780.664; first refusal 780.69 |
| robo005 s002 | 1,062 | 0 | 1,062 | 910.3 to 1,033.5 s (123 s) | piece pt=9,011 at t=905.7 read cached_tokens 0; completed 908.94; first refusal 910.29 |
| robo000 s002 | 20 | 20 | 0 | 1,136.9 to 1,138.8 s | warm, no latch |
All 2,346 refusals are in these two sessions, issued at about 10 per second per session (every state epoch). Each latch lasted until the end of the run window for that session's pieces: the cold read repeated at EVERY following piece (robo006: pieces at 824.5 and 870.5 both read 0; robo005: 951.7 and 997.7 both read 0) and ended only when the session's next RECALL (robo006, t=914.5, cached 10,976 of 10,991) or a late piece read non-zero.

## 3. KEY TABLE: P belief at each refused epoch against the NEXT real request (cell (2); refusals grouped by the interval before the session's next request)
Truth column: next request cached_tokens / built prefix. In this cell NO touch was sent in the window, so a cold next read is partly CAUSED by the refusal: it is an upper bound on how often a touch would have reached a cold session.
| session | refused epochs | window | P frac (min/med/max) | P pure-GPU at the FIRST epoch | first epoch P drops under 0.95 | P allows (pure tier, >= 0.95) | next request cached/built |
|---|---|---|---|---|---|---|---|
| robo005 | 288 | 910 to 952 | 0.00/1.00/1.00 | 1.00 | +25.1 s | 60% | 0.00 (cold) |
| robo005 | 459 | 952 to 998 | 0.00/1.00/1.00 | 1.00 | +36.6 s | 79% | 0.00 (cold) |
| robo005 | 315 | 998 to 1,033 | 0.00/1.00/1.00 | 1.00 | +20.9 s | 52% | 0.00 (cold) |
| robo006 | 425 | 781 to 824 | 0.00/1.00/1.00 | 1.00 | +31.6 s | 71% | 0.00 (cold) |
| robo006 | 442 | 825 to 870 | 0.01/1.00/1.00 | 1.00 | +35.2 s | 76% | 0.00 (cold) |
| robo006 | 417 | 871 to 914 | 1.00/1.00/1.00 | 1.00 | never | 100% | 1.10 (warm) |
(P allows = P cached fraction >= 0.95 AND wholly GPU or wholly host; the same two rules as the existing guard: PURE_TIER_MIN_BELIEF 0.95 and M6.)
READING: (a) **At the first refused epoch of EVERY interval P says wholly GPU-resident (6 of 6)** and the D150 flag says cold: the cold flag describes the state BEFORE the request that carried the zero, and that request then rebuilt the prompt in the engine (the refusal comes 0.03 s to 1.4 s after the completion). (b) **P predicts an eviction inside the interval in 5 of 6 intervals (first drop +21 to +37 s) and none in the sixth; the engine's next read is cold in exactly those 5 and warm in the sixth: P agrees with the outcome at interval level 6 of 6.** (c) At epoch level, in the touch-free cell, P-allowed epochs 1,668 of 2,346 (pure GPU 266, pure host 1,402; mixed resident 92 refused by M6): next warm 380, next cold or partial 1,288 (the host-containing epochs are the weak part: pure_host 339 warm against 1,063 cold). (d) So P knows what the one-hot flag gets wrong at the moment the latch forms (fresh rebuild) and it also times the eviction; it does NOT validate its host-resident predictions later in a window.

## 4. The same table in the two comparison cells
| cell | refusal rate | latched sessions | outcome |
|---|---|---|---|
| pwire halved | 1,191 of 2,468 (48%) | robo006 only (781 to 914 s: next reads 0, 0, 1.1, the same three intervals as the candidate cell) | robo005 (pieces read non-zero) was NOT latched: 1,263 touches issued over 908 to 1,037 s and every next request read warm (1.0, 1.1, 1.11) |
| committed -la-er halved | 446 of 1,477 (30%) | robo006 only, 781 to 825 s | the prefix SURVIVED the 45 s without a touch (piece at 824.6: cached/built 1.0), the non-zero read re-promoted the belief, 800 touches were issued from 826 s, next reads warm |
SAME MECHANISM AT LOWER INTENSITY: a session's first piece zero latches it; the latch breaks only if the UNTOUCHED prefix happens to survive until the next piece (-la-er, 825 s) and persists when it does not (pwire and candidate, robo006; candidate, robo005): refusal removes the touch that would have protected the prefix and the eviction it permits then confirms the cold flag (feedback loop). Where touches were issued the next request was warm (pwire robo005 1,263 of 1,263 epochs; -la-er 1,026 of 1,029 allowed epochs).

## 5. Engine-side signal (vLLM 0.31.0 source, scratchpad vllm_src; read, nothing scraped)
* Per-request: `cached_tokens` = local hit + external (connector/host) hit, folded: `v1/metrics/stats.py:288` (`num_cached_tokens = num_local_cached_tokens + num_external_cached_tokens`) and the response schema carries only cached_tokens, created_cache_tokens, multimodal_tokens (D209 (4) note, engine_actions.py). The offloading connector's `request_finished` returns no kv_transfer params (`kv_connector/v1/offloading/scheduler.py:1936-1958`). So NO per-request field separates a host hit from a GPU hit.
* CONSEQUENCE FOR THE PREMISE: because host hits are folded INTO cached_tokens, `cached_tokens == 0` means no local AND no external hit: a TRUE MISS at that request's admission. The D150 flag is therefore not wrong because it confuses a host hit with a miss (a host hit reads > 0); it is stale after the zero-reading request itself COMPLETES, because that request leaves its prompt resident. The docstring of `belief_update_from_cached_tokens` ("a host hit reads cold") contradicts stats.py:288 and the D209 (4) note in the same file; flagged, not edited.
* Aggregate only: `vllm:prompt_tokens_by_source_total{source=local_cache_hit|external_kv_transfer}` (stats.py:386-421). Not attributable per request under concurrency. The planned GPU 2 engine probe (E-engine-hosttier) does not add a per-request signal, but its single-request-in-flight steps DO confirm the fold (a host read after a GPU flush must report cached_tokens > 0 and the aggregate external counter must rise by the same amount): that is the check to read in its P2 output.
