# READ THIS BEFORE FILTERING D250 CELLS BY NAME: A CELL NAMED `h27` MAY BE RUNNING `h13.5`

**Written on 2026-11-25 BEFORE the first `_kv0.5r_h0.5` cell landed, as a condition of accepting the cell
name as it stands.**

## The fact

**Every live2 cell name is built as `..._1200s_h27_3t<tag>`, with `h27` HARD-CODED IN THE NAME BUILDER.**
The D250 memory condition halves the native host offload from 27 GiB to 13.5 GiB, and expresses that in the
TAG (`_h0.5`), not in the name stem.
*** SO A D250 CELL IS NAMED `..._1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30...` WHILE RUNNING A 13.5 GiB HOST
TIER. THE `h27` IN THE NAME IS WRONG FOR THESE CELLS. ***

## What is authoritative, in order

1. **`header.json`'s `host_tier_gib` and `host_tier_tokens`** - the true values, 13.5 and about 55,315.
2. **The tag token `_h0.5`** - authoritative over the name stem.
3. **The server's own startup log**, `shared_offload_region.py:142`, "Created mmap file ... (14.50 GB)" for
   a 13.5 GiB tier against 28.99 GB for 27 GiB. **This is the server reporting what it ALLOCATED, which is
   stronger than any argv read.**
**THE NAME STEM IS AUTHORITATIVE FOR NOTHING.**

## *** THE UNSAFE QUERY, STATED EXPLICITLY ***

**A bare grep for `_h27_` MATCHES D250 CELLS, which run a HALVED host tier.** Anyone selecting
"full-host-tier cells" that way will silently include halved ones.
**SAFE: require `_h0.5` ABSENT as well, or filter on `header.json`'s `host_tier_gib`, which is the only
field that cannot be wrong.**

## Why the name was not fixed instead

**Changing the name builder would alter EVERY committed cell name and break name-based pairing against the
entire committed corpus.** That is a far larger harm than one misleading token, so the trade was taken
deliberately. **It is recorded here rather than accepted silently, because "the same name meaning two
things" is a failure this project has hit repeatedly, and the mitigation is a reader who knows.**
**Conversion for reference: 27 GiB = 110,630 tokens as observed, so 262,054 bytes per token (255.9 KiB),
and 13.5 GiB = 55,315 tokens.**
