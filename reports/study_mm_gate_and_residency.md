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

---

## RESOLVED 12:40 by oscillation counting: it is eviction pressure, my 80 percent was wrong, and the instrument I proposed is now much less needed

The H100 observed that v5-rules-2's **dashcam** requests are also costlier per request, 802 (s4) and
768 (s5) uncached tokens against noc3's 480 and 480, and argued this supports mutual eviction over
never-inserted. It does, and the decisive test is free: count **oscillation**, a
warm then cold then warm sequence on one stream, which **proves** insertion, loss and re-insertion
without any engine change.

| arm | dashcam streams | ever warm | oscillating | **warm to cold to warm events** |
|---|---|---|---|---|
| `noc3` (**no warming at all**) | 6 | 6 | 6 | **694** |
| `v5-rules-2` | 6 | 6 | 6 | **591** |
| `v5-rules` | 6 | 6 | 6 | **460** |

| arm | robot sessions | ever warm | oscillating | events |
|---|---|---|---|---|
| `noc3` | 12 | 10 | 5 | 5 |
| `v5-rules-2` | 22 | **15** | 10 | 25 |
| `v5-rules` | 22 | **22** | 19 | 104 |

**noc3, which issues no warm-ahead prefill at all, already oscillates 694 times on dashcam.** So
constant insertion and eviction is the **baseline state of this engine**, not something warming
introduced. That settles the direction: the cache is under continuous pressure regardless of arm.

### My 80 percent was three states conflated, and here they are separated

| of v5-rules-2's 139 COLD warm-ahead prefills | count | share |
|---|---|---|
| **EVICTED**: the session was observed warm EARLIER and this piece still missed | **28** | 20 percent |
| **PRE-FIRST-WARM**: the session DOES become warm later, so insertion demonstrably works for it | **77** | **55 percent** |
| in a session **never observed warm at all** | **34** | 24 percent |

I reported 111 as "never observed warm" and let that stand next to a discussion of "never
inserted". **Only 34 are even candidates for never-inserted.** For the 77, insertion is
demonstrably working in that very session, so they are pre-residency or evicted before the next
touch, not uninserted. Splitting at "was it ever warm before this request" was the wrong cut; the
right one also asks whether it was ever warm *after*.

### The mechanism, stated at the register the evidence supports

**Residency requires frequent touching, and the KV pool cannot hold a rarely-touched robot history
against constant dashcam churn.** The cleanest evidence is the contrast within the robot column:
under v5-rules' frequent pieces **22 of 22** sessions achieve warmth, under v5-rules-2's rare
pieces only **15 of 22**, and 7 never do. That is the same trade recorded in
`reports/study_v5rules2_live.md`: chunking removed the traffic that was keeping its own cache warm.

This is consistent with the user's framing, and now measured rather than assumed: at 16 devices
62,944 KV tokens cannot hold every robot history plus the dashcam episodes, so a history touched
once every 7.7 s loses its place to a dashcam stream touched several times a second.

### Consequence for item 3, against my own proposal

**The instrument I proposed an hour ago is now substantially less needed, and I am saying so rather
than leaving the recommendation where it was.** Offline analysis has narrowed the ambiguous set from
111 to **34 prefills in 7 sessions**, and the dominant mechanism is established by the oscillation
counts. One integer per request would still close those 34 exactly, and it remains the smallest
sufficient design, but it no longer answers a first-order question.

My recommendation changes to: **do not deploy it for this lead.** If it is deployed later it should
be for a different reason, such as pricing warms by predicted cache state in the counterfactual,
where knowing insertion per request would let the cost model condition on residency rather than
infer it. That is the use the user's own brief addition for session B points at, and it is a
stronger justification than the one I first offered.
