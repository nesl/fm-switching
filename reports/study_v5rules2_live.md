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
