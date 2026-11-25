# Dashcam cloud-score arm-independence check (oracle stage 2-live gate)

CPU only, read-only. Before using simplestream's committed cloud scores as the DENSE per-instant
cloud (32BI) source for the dashcam oracle valuation, verify the per-instant 32BI score is
ARM-INDEPENDENT. For dashcam instants delivered to the cloud by BOTH simplestream and another arm in
the same seed x memory cell, compare the cloud scores. D197 cloud threshold theta = -2.9298319.

## Verdict: PASS. The cloud score is arm-independent; proceed with simplestream as the dense source.

| pair | n instants | fraction exactly equal | max abs diff | p99 abs diff | decision flips | flip fraction | repr diff | traffic_mix diff |
|---|---|---|---|---|---|---|---|---|
| simplestream ~ covex-v6-fair-final | 58,110 | 0.9999 | 0.2500 | 0.0000 | 0 | 0.00000 | 0 | 48,852 |
| simplestream ~ llf | 72,311 | 0.9998 | 0.3750 | 0.0000 | 0 | 0.00000 | 1 | 61,354 |
| simplestream ~ mooncake | 73,895 | 0.9985 | 0.3750 | 0.0000 | 0 | 0.00000 | 0 | 57,445 |
| simplestream ~ eco-llm | 74,293 | 0.9996 | 0.3750 | 0.0000 | 1 | 0.00001 | 5 | 59,871 |

**Overall decision-flip fraction across theta: 1 / 278,609 = 0.000004 (0.0004 percent), far below the
0.5 percent bar.** Pooled over seeds 4-7 and both memory levels (1x and kv0.5r reported together
only for this noise check; the bound itself keeps them separate per D240).

## Reading
- The per-instant 32BI score is equal across arms on at least 99.85 percent of shared instants, and
  the p99 absolute difference is 0.0000; the maximum difference is 0.375, consistent with
  batching/quantization noise (the 32BI score computed under different concurrent batch conditions).
- That noise NEVER flips the D197 cloud decision except on a single instant out of 278,609, so it
  cannot move an episode's max-over-subsets value.
- The request REPRESENTATION (prompt_tokens and mm_uuids count) is identical on all but 0 to 5
  shared instants, so the arms send the same frames for the same instant.
- traffic_mix DIFFERS between arms on most shared instants (expected: different arms create
  different concurrent load), yet the cloud score is invariant to it. That is the point of the
  check: the 32BI per-instant score is a property of the model and the frames, not of the arm.

## Consequence
simplestream (99.9 to 100 percent cloud-score coverage of dashcam instants across all 8 cells) is a
valid dense per-instant cloud-score source for the oracle dashcam valuation. The 5 to 8 instants per
cell with no simplestream cloud score are treated as device-only (not improvable), a conservative
choice that cannot raise the oracle above a valid upper bound. This source choice is recorded in the
oracle status doc and will be stated in every dashcam/pooled bound table.
