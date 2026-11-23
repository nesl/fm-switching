# OVERNIGHT DECISIONS (D187), for the user's morning review

Every entry is PROVISIONAL and carries its evidence. A FINDING entry means something was measured
and NO ACTION was taken, with the reason. A DECISION entry means a new labelled version was built.

---

## 2026-11-22 18:20 FINDING, NO ACTION TAKEN: assistance is oversize because of an image grid that no D-row sets

WHAT WAS MEASURED (read-only, `results/orchestration/live2/frozen_test/image_settings_by_type.json`,
pushed at `c4db4122`). There is exactly ONE image-processor setting, server-wide, for all three
query types: `--mm-processor-kwargs {"size": {"shortest_edge": 4096, "longest_edge": 16777216}}`.
It binds NOTHING: the largest image any type sends is 9.4x below max_pixels and the smallest is 48x
above min_pixels, so no image of any type is rescaled by the processor. Our body builder performs
NO resize, crop or re-encode (`bodies.py:127-147`): it base64s the stored bytes verbatim.

THE DIFFERENCE IS UPSTREAM, IN STORAGE, AND IT IS PER TYPE:
  alert frames       768x432, downsized OFFLINE before storage   338 image tokens
  recall frames      352x256, downsized OFFLINE before storage     90 image tokens
  assistance images  NATIVE dataset resolution, NO pre-resize anywhere
                     p50 1448x938, p90 1448x1536, max 1536x1536  p50 1,307 image tokens

So one assistance image costs 3.9x an alert frame and 14.5x a recall frame.

WHY IT MATTERS TO D179, and it revises my own earlier account. I reported that assistance is
"routinely OVERSIZE against its own share" and used that to explain the W overrun with no recall
present. That is true as far as it goes, but the CAUSE is not the admission rule: as sent, the
median assistance request is 1.63x its own 843.7-token share and therefore takes an oversize
branch; on alert's 768x432 grid the same request would be a CONSTRUCTED 407 tokens, 0.48x its
share, comfortably inside it. Assistance's oversize status turns on an image grid, not on D179 (3).

A SECOND, INDEPENDENT CAUSE compounds it: assistance holds ZERO residency by construction
(`trace.py:567-574`), cached fraction exactly 0.0 on all 1,428 requests, so it pays its whole prompt
every time, while alert's append-only EP-G episode is 89.3 percent cached at p50.

NO D-ROW AUTHORISES THE PER-TYPE EFFECTIVE COST. D67, D70, D91, D111, D136, D143, D148, D153, D156
and D172 were searched. D70 and D91 fix the wire format and inherit the two grids from upstream
studies; D136 and D143 choose the SS datasets and the split only; D172 requires only that the
setting be STATED. The SETTING is uniform and authorised. The effective per-image cost is recorded
nowhere.

WHY NO ACTION WAS TAKEN, and this is the point of the entry. The obvious change, pre-resizing
assistance images to a comparable grid, would make assistance fit inside its share and would very
likely improve the shares arm's numbers. D187 (3) forbids it: "NEVER change targets, deadlines,
metrics, workload, seeds, baselines, pass bars or the margin". The image grid IS the workload. A
change that happens to help the arm under test, made overnight, on a quantity no decision governs,
is exactly the kind of thing the rule exists to prevent, so it is reported and left for the user.

REGISTER: 1,372 and 374 are MEASURED medians; 407 is a CONSTRUCTED bound, not a census.

POSITIVE CONTROLS ON THE READING, both exact before any table was trusted: the EP-G law
`prompt_tokens = 42 + 338 x n_frames` holds on 39,945 of 39,945 alert requests across the four base
cells, deviation histogram {0: 39945}; and `share_capacity.FACTORS` medians recompute from the four
cells that file names as its source at alert 374, recall 7,717, assistance 1,372, ratio 1.000000.

TWO SMALLER ITEMS FROM THE SAME READ:
1. A PROXY THAT FAILS, flagged by the code itself: assistance UPLINK BYTES substitute the S-EMBER D2
   median for every SS2 image (`fleet/data_sources.py:661`), understating them by 2.2x to 24x in
   area. It touches no token count, so nothing above depends on it, but any assistive uplink figure
   resting on it is unvalidated.
2. In the `b7-edf-feasibility` s4 cell, 74 of 8,058 alert requests deviate from the EP-G law, while
   the four base cells are 0 of 39,945. Not diagnosed and not used for any number here; flagged as a
   cheap check for whoever owns b7.
