# v5-rules-2, first live cell: the prefill COUNT fell 19x and the load barely moved

Session D (flash / A6000), 2026-11-21 11:30. Cell:
`v5-rules-2_n16_s4_1200s_h27_3t_L3_epg_rq30`, run by the H100, VALID, 5,432 requests, 0 errors.
Comparators on the same rq30 trace: `hybrid-F-lhreq-noc3` (the base) and `v5-rules`.
Instrument: `experiments/orchestration/live2/v5/rq30_load_attribution.py`.

## What held

The warming cut is real and it reproduces the dry proof. Prefill pieces **156 live against 183
dry**, and v5-rules on the same trace issues **3,027**. So the 19x reduction in prefill COUNT holds
live, and P5's declared criterion is met on a live cell as well as a dry one.

Headline scores also move the right way: by-deadline **0.485** for v5-rules-2 against **0.470** for
noc3 and **0.439** for v5-rules, and single-shot recovers from v5-rules' **170 of 357** to **245**.

## What did not hold, and it is my own P5 criterion that is at fault

Splitting the robot side into warm-ahead prefills and recall requests, by whether the request
carries a scored `opportunity_id`:

| arm | prefills | prefill uncached tokens | tokens per prefill | recalls | recall uncached tokens |
|---|---|---|---|---|---|
| `noc3` | 0 | 0 | n/a | 54 | 341,355 |
| **`v5-rules-2`** | **156** | **854,840** | **5,480** | 93 | 589,367 |
| `v5-rules` | 3,007 | 1,415,444 | **471** | 131 | 604,604 |

| | v5-rules to v5-rules-2 |
|---|---|
| prefill **count** | 3,007 to 156, **19.3x fewer** |
| prefill **uncached tokens** | 1,415,444 to 854,840, **only 40 percent less** |
| **tokens per prefill** | 471 to 5,480, **11.6x BIGGER each** |

**The chunking traded many small prefills for a few large ones, and the quantity that actually
drives the engine fell by 40 percent while the quantity I proved fell by 95 percent.** D160 (1)
asked for the prefill request count and that is what P5 measured, so the proof is not wrong about
what it claims. But **count is not what loads the engine, tokens are**, and my report of P5 invited
the reading that the load problem was solved by a factor of 20. It was not.

The total is roughly conserved for a reason that is obvious in hindsight: the tokens being prefilled
are the session's history, and chunking changes **when** they are sent, not **how many** there are.

## A second finding: the declared slice is not binding

`engine_actions.WARM_AHEAD_SLICE_TOKENS = 1024`, documented as "small pieces: one piece per session
per epoch". Measured uncached tokens per prefill under v5-rules-2: **5,480**, which is **5.4x the
declared cap**. Under v5-rules it is 471, inside it. So the cap holds when asks are frequent and
does not hold once the tail is allowed to accumulate. Whether `slice_tokens` is not enforced by
`coordinator._advance_build` or whether a piece carries uncached tokens beyond the slice (header,
frames) is **not yet established** and is the next thing to check. REGISTER: the 5,480 is MEASURED;
the cause is not.

## Why dashcam still fails, which answers the H100's question

v5-rules-2 against noc3, uncached tok/s by kind:

| kind | request delta | tok/s delta |
|---|---|---|
| dashcam | **-4,916** | **-669.2** |
| robot | **+195** | **+919.0** |
| single shot | 0 | 0.0 |
| **total** | | **+249.9** |

So the robot side costs **+919 tok/s** and the dashcam side gives back only **-669**, for a net
**+250 tok/s**. That moves the arm from noc3's **4,479 tok/s to 4,729**, which crosses the
transition zone (roughly 4,500 to 4,750) that noc3 sits below. Hence the guard active in **4,027 of
11,999 epochs**, a third of the run, and dashcam FAIL where noc3 meets.

**Is this v5-rules-2 working as designed? Yes on warming, and the chain is intended end to end.**
Chunked warming makes robot histories warm, the base's own feasibility test then declines less (38
declines against noc3's 77), so more robot recalls are released (451 against 412) on long histories,
and that is the new load source. Every link is the mechanism doing what it was built to do.

**But the guard is now partly aimed at the wrong thing.** D160 (2) sheds background warming first
and changes nothing else. Warming is 854,840 of the robot side's 1,444,207 uncached tokens, so in
token terms shedding it is still the largest single lever. What the guard cannot touch is the
**extra releases** its own warming enabled, and those are 589,367 tokens on 93 requests that noc3
served as 54. A guard that sheds warming while the releases it created keep arriving is treating a
symptom one step upstream of itself.

## What this changes for full v5

The counterfactual decides **robot request** decisions, which is exactly the release side the guard
cannot reach. So full v5 is the right place to fix this, and two requirements follow that were not
obvious before this cell:

1. **The counterfactual must price warming in TOKENS, not in asks.** An objective that counts
   prefills will conclude that 156 is cheap. It is 854,840 uncached tokens.
2. **The healthy-regime restriction in D160 (2) has to bind on the release side too.** v5-rules-2
   crosses the transition zone by +250 tok/s, and 919 of that arrives as robot work the guard does
   not shed. A counterfactual that chooses only among healthy-regime actions must therefore be able
   to decline a release, not only defer a warm.

## Register

- All token and request figures are **MEASURED** from the three cells' own `request.jsonl`.
- The prefill / recall split uses the presence of a scored `opportunity_id` as the discriminator,
  which is exact: a warm-ahead piece has no scored opportunity.
- The causal chain from warming to fewer declines to more releases is **ARGUED** from the decision
  counts, not traced per decision. The counts are the H100's and are consistent, but a per-decision
  trace would be needed to call it proved.

---

## CORRECTION: the slice IS binding. Chunking defeats its own prefix cache.

I reported that `WARM_AHEAD_SLICE_TOKENS = 1024` "is not binding" because measured uncached tokens
per prefill were 5,480. That was wrong, and the real mechanism is more interesting and more
actionable.

`coordinator._advance_build:700` reads
`piece = left if slice_tokens is None else min(int(slice_tokens), left)`, so the slice **is**
enforced. With `D2_TOK_PER_IMG = 90`, a 1,024-token slice is about 11 new frames. The excess is not
the slice overrunning; it is the **prefix being re-sent uncached**.

Engine-observed `cache_path` on the warm-ahead prefills themselves:

| arm | prefills | cache_path | uncached per request | prompt per request | cached per request |
|---|---|---|---|---|---|
| `v5-rules` | 3,007 | **WARM 2,902, COLD 104** (96.5 percent warm) | **471** | 10,127 | 9,656 |
| **`v5-rules-2`** | 156 | **COLD 139, WARM 17** (**89.1 percent COLD**) | **5,480** | 6,968 | 1,488 |

**v5-rules' prefills hit the prefix cache 96.5 percent of the time and send only the new slice.
v5-rules-2's miss it 89.1 percent of the time and re-send most of the history.** Of its 5,480
uncached tokens per piece, roughly 1,024 are genuinely new and about **4,456 are prefix that should
have been cached and was not**. Over 156 pieces that is about **695,000 tokens, or 579 uncached
tok/s of pure cache-miss waste**, which is **2.3x the entire +250 tok/s by which the arm exceeds
noc3**.

### Why, and it is a trap in the design rather than a bug

Warming works by sending uuid references for frames the engine has already seen, so it depends on
the session's prefix still being resident. What keeps a prefix resident is being touched often.
v5-rules issued a piece about every 0.4 s per the run's 3,007 over 1,200 s, comfortably inside
retention. v5-rules-2 issues one about every 7.7 s, and with roughly four dashcam requests per
second competing for the same cache the session is evicted in between.

**So the mechanism that makes chunking cheap in request count is the same mechanism that makes each
request expensive in tokens.** Chunking removed the very traffic that was keeping its own cache
warm. That is why the total barely moved: 19.3x fewer pieces at 11.6x the cost each.

### What it changes for full v5, replacing my earlier requirement 1

My earlier statement, that the counterfactual must price warming in tokens rather than asks, is
right but insufficient. **The token cost of a warm is not a property of the warm; it depends on
whether the prefix survived since the last one.** A cost model that prices a 1,024-token slice at
1,024 tokens will be wrong by about 5x on 89 percent of this arm's warms.

Three consequences, in order of how much they change the build:

1. **The cost model must take cache state as an input, not infer it.** The engine reports
   `cache_path` and `cached_tokens` per request; the D162 refit already carries `cached_tokens` in
   its `uncached_tokens` feature, so a refit on healthy-regime data will learn the right
   coefficient. What it cannot do is predict WHICH state a future warm will land in.
2. **The chunk interval is now a cache-residency decision, not only a volume decision.** There may
   be no good fixed value: frequent warms are cheap per warm and numerous, rare warms are few and
   expensive, and the product is roughly conserved. If that holds, D160 (1)'s chunk size is a
   knob with a flat objective, which is worth knowing before it is swept.
3. **This is a candidate explanation for the dashcam hold-back that does not require the release
   chain.** 579 tok/s of cache-miss waste is enough on its own to cross the transition zone.

### Register, and what is NOT established

- The `cache_path` counts, token figures and the 579 tok/s are **MEASURED** from the cells' own
  request logs.
- The 1,024-new-plus-4,456-prefix split is **DERIVED** from the slice rule and `D2_TOK_PER_IMG`,
  not measured per request.
- **Eviction by competing dashcam traffic is the PROPOSED mechanism and is not proved.** The
  alternative is that the prefix was never inserted for these sessions at all. Distinguishing them
  needs the residency or eviction trace, which is the same instrument gap recorded in
  `reports/study_saturation_knee.md` for the cache-tail lead. Both leads now want the same missing
  measurement, which raises its priority.
