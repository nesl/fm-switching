# mm_gate FAIL is an artefact, D84 is intact, and the residency gap is 80 percent narrower than I thought

Session D (flash / A6000), 2026-11-21 ~12:20. Read-only analysis of committed request logs. No GPU,
no engine, no cell run, nothing deployed.

## Item 2: the mm_gate FAIL is (b), an artefact of the gate's premise. D84 is NOT breached.

The gate's message is "FAIL: multimodal hits in a run whose payloads should all be unique (SS timing
column not usable)". **Its premise is false for any workload that re-references frames**, which is
the committed StudyRH7 wire form: a frame the engine has already seen is sent as a uuid-only
reference. Robot history appends and piece chaining do this always; EP-G dashcam does it for every
episode frame.

### The hits are EXACTLY accounted for by legitimate within-device reuse

| cell | engine `mm_cache_hits` | within-device uuid reuse events | uuids shared ACROSS devices |
|---|---|---|---|
| `eco-llm_n16_s4_1200s_h27_3t` (oneframe, batch-30s) | **345** | **345, all robot** | **0** |
| `v5-rules-2 ... _L3_epg_rq30` | 67,336 | 67,690 (dashcam 43,664, robot 24,026) | **0** |

On the cleanest cell the match is **exact**: 345 hits, 345 reuse events, every one of them robot
history references. On the EP-G cell the two agree to 0.5 percent, and the residual is the gate's
own documented limitation that its 10 s snapshot window "can omit the first and last ~10 s".

**Hits never exceed within-device reuse.** That is the load-bearing observation, because it leaves
**no residual** for any cross-device or byte-level sharing to hide in.

### D84 specifically

| | |
|---|---|
| uuids used by more than one device | **0 of 14,706** (EP-G cell), **0 of 16,062** (oneframe cell) |
| single-shot requests / distinct single-shot uuids | **356 / 356** (`mm_uuid_check.json`) |
| wire image parts carrying a uuid | **82,541 of 82,541** |

Every image part carries a per-(run, device, session, frame) uuid, no uuid crosses a device, and
single-shot has one unique uuid per request. **D84 holds.** There is no STOP condition here and no
reason to withhold scoring.

### Which columns are unusable: fewer than the gate claims

The gate declares the single-shot timing column unusable on the argument that "total hits bound
single-shot hits". That bound is **correct but vacuous**: measured single-shot hits are **zero**,
since 356 requests carry 356 distinct uuids and contribute 0 of the 67,690 reuse events. So **the
single-shot timing column IS usable**, and the gate's conclusion does not follow once client-side
uuids are consulted instead of server-wide counters alone.

**The gate should be read as a reminder, not a verdict.** It is a server-wide counter check that
cannot attribute hits to a kind; the per-request `mm_uuids` can, and does.

**One assumption, stated because I did not verify it in engine source:** this rests on the engine
keying its multimodal cache by the client-supplied uuid, so two distinct uuids over identical bytes
would miss. The accounting rules out the alternative empirically (hits never exceed within-device
reuse, matching exactly on the oneframe cell), but the mechanism is inferred from that arithmetic
rather than read from vLLM.

## Item 3: 20 percent of the question needs no instrument at all, and my mechanism was wrong

The open lead was whether a COLD warm-ahead prefill means "prefix evicted by competing traffic" or
"prefix never inserted". Part of it is already decidable from committed logs, with **no engine
change, no added traffic and no cost**: for each robot session, walk its own requests in submit
order and ask whether any EARLIER request of that session was observed warm.

On `v5-rules-2 ... _L3_epg_rq30`, over its 139 COLD prefills:

| classification | count | share |
|---|---|---|
| **EVICTED** (the session was observed warm earlier, then lost it) | **28** | 20 percent |
| **NEVER OBSERVED WARM** (no earlier request of that session ever hit) | **111** | **80 percent** |

**My proposed mechanism was eviction by competing dashcam traffic, and it explains only 20
percent.** Four fifths of the cold prefills belong to sessions that were never observed warm at
all, which is a failure to ever achieve residency rather than a loss of it. That is consistent with
the user's own framing: at 16 devices the KV pool of 62,944 tokens cannot hold every robot history
plus the dashcam episodes, so a robot history may simply never win a place.

### What the offline method CANNOT do, which is what the instrument is for

Observed-hit absence conflates two states: **never inserted**, and **inserted then evicted before
any later request of that session could observe it**. My classifier cannot separate those, so the
111 are "never observed warm", not "never inserted". The 28 are sound, because an observed hit
proves prior residency.

### The smallest engine-side log that closes it

**One additional integer per request: the number of prefix-cache blocks INSERTED while serving it**,
reported in the response's usage block beside the existing `cached_tokens`.

That is sufficient and minimal. With insertion known per request, the two states separate directly:
insertion recorded and no later hit means **evicted**; no insertion ever recorded means **never
inserted**. Nothing else is needed, and in particular a full eviction trace is not: eviction is
inferable from insertion plus the absence of a later hit.

| | |
|---|---|
| cost on the wire | one integer per request, about 5,400 requests per cell, a few tens of KB per cell |
| cost in the engine | a counter already maintained by the block manager, read at response time |
| **can it run without changing any arm's decisions?** | **yes, if and only if no arm reads it.** It is output-only, like the `_instrument_placement` totals in `run_live2_real`. The field must be stripped before the observation is built, which `bodies.strip_internal` already does for `fm_*` hints, so the pattern exists. |
| what it does NOT require | no extra requests, no probe traffic, no change to any body, no change to the cache |

**Two alternatives rejected, with reasons.** A *probe request* after each piece, re-sending the same
prefix and reading its `cached_tokens`, would measure residency directly but **adds traffic**, which
changes load and therefore changes arm decisions indirectly, so it fails the user's condition. The
*server-wide* `prefix_cache_hits` and `prefix_cache_queries` counters differenced per 10 s snapshot
are free and already recorded, but they cannot attribute to a session, which is the whole question.

**DESIGN ONLY. Nothing deployed, and this needs a ruling**, both because it touches the engine's
response path and because it is an instrumentation change during a live measurement window.

## Register

- All counts are **MEASURED** from committed request logs, read-only.
- The exact 345/345 agreement is the strongest single piece of evidence and it is on the cell with
  the least re-referencing, which is where a residual would be most visible.
- The engine's multimodal-cache keying is **ASSUMED** from the accounting, not read from source.
- The 28/111 split is **MEASURED**; the interpretation of the 111 as "never observed warm" rather
  than "never inserted" is the limitation the instrument exists to remove.
