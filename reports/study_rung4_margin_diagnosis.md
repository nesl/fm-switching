# StudyRUNG4-margin: is the margin the wrong yardstick, or are the gains simply not there?

Read-only diagnosis from logs already on disk. **Nothing was changed**: not MARGIN_CF, not the
safety factor, not the design, and no cell was posted. Gate A's STOP stands.

Sources: the dry s4 decision records of `covex-v6-cf-c5attr` at 1x and at 0.25x, produced on a clean
`git archive` checkout of `ec2d6a83` (`d190_rung4_r3_proofs.json`), and the **committed** rung-3 s4
cell `covex-v6-fair-c5attr_n16_s4_1200s_h27_3t_L3_epg_rq30`.

**Register, stated once and applying throughout.** The rung-4 figures are **DRY** decisions. The
0.25x rung-4 figures are **DRY AND LOGICAL-ONLY**: the harness pool was set to 15,736 tokens and no
engine was involved. The 0.25x **engine** pool of record is **15,760** (override 985 x 16, all usable,
no block reserved, fixed at `483ee585`); that figure is not used in any computation here and is given
so the two are not confused. The item 3 figures are **LIVE** and come from the committed cell.

Rung 3's committed digest never moved: `12e4f73ce0ebd865` / 13,812 under
`cf_pd_one_cell.py --cutoff-off`.

---

## 1. Every evaluated question-deferral candidate

88 candidates at 1x. **66 never reached the harm computation**, and that is the first finding:

| gate | n | share |
|---|---|---|
| `must_start_now_no_slack` | 47 | 53.4 % |
| `no_active_alert_episode` | 19 | 21.6 % |
| `saving_does_not_exceed_margin` | 16 | 18.2 % |
| fired (`defer_to_latest_safe_start`) | 6 | 6.8 % |

The 22 that reached the harm, each with weighted gain, weighted harm, their difference, the bar, and
the ratio to the bar:

| t_s | u | gain (w) | harm (w) | gain - harm | bar = w_d x MARGIN_CF | ratio | w_d | alerts | outcome |
|---|---|---|---|---|---|---|---|---|---|
| 95.0 | 7951 | 0.000000 | 0.027157 | -0.027157 | 1.974720 | -0.0138 | 3.0000 | 2 | margin |
| 126.8 | 6421 | 0.000000 | 0.045094 | -0.045094 | 1.974720 | -0.0228 | 3.0000 | 1 | margin |
| 156.8 | 7411 | 0.000000 | 0.032869 | -0.032869 | 1.974720 | -0.0166 | 3.0000 | 3 | margin |
| 158.7 | 7771 | 0.000000 | 0.015342 | -0.015342 | 0.999550 | -0.0153 | 1.5185 | 3 | margin |
| 443.3 | 6400 | 0.000000 | 0.022602 | -0.022602 | 0.999550 | -0.0226 | 1.5185 | 2 | margin |
| 542.9 | 5410 | 1.005309 | 0.017766 | 0.987543 | 0.755757 | **1.3067** | 1.1481 | 1 | **FIRED** |
| 621.3 | 7896 | 0.000000 | 0.013150 | -0.013150 | 0.929895 | -0.0141 | 1.4127 | 2 | margin |
| 643.6 | 4758 | 0.027820 | 0.042498 | -0.014678 | 1.609031 | -0.0091 | 2.4444 | 3 | margin |
| 677.4 | 6378 | 3.063852 | 0.044940 | 3.018912 | 1.974720 | **1.5288** | 3.0000 | 3 | **FIRED** |
| 688.5 | 6828 | 0.000000 | 0.031360 | -0.031360 | 1.487135 | -0.0211 | 2.2593 | 1 | margin |
| 694.5 | 7098 | 0.000000 | 0.035063 | -0.035063 | 1.682169 | -0.0208 | 2.5556 | 1 | margin |
| 714.4 | 7998 | 0.000000 | 0.015170 | -0.015170 | 1.487135 | -0.0102 | 2.2593 | 2 | margin |
| 743.5 | 7210 | 2.047327 | 0.026685 | 2.020643 | 1.389618 | **1.4541** | 2.1111 | 3 | **FIRED** |
| 747.1 | 7390 | 1.948614 | 0.025529 | 1.923085 | 1.442809 | **1.3329** | 2.1919 | 5 | **FIRED** |
| 792.2 | 5084 | 1.026910 | 0.034723 | 0.992187 | 1.402337 | 0.7075 | 2.1304 | 1 | margin |
| 865.9 | 4578 | 1.038061 | 0.031119 | 1.006942 | 1.162078 | 0.8665 | 1.7654 | 2 | margin |
| 935.0 | 6704 | 2.221573 | 0.023121 | 2.198451 | 1.043876 | **2.1060** | 1.5859 | 6 | **FIRED** |
| 935.5 | 6704 | 2.234112 | 0.024994 | 2.209118 | 1.121446 | **1.9699** | 1.7037 | 5 | **FIRED** |
| 988.0 | 8020 | 0.000000 | 0.012227 | -0.012227 | 1.138860 | -0.0107 | 1.7302 | 3 | margin |
| 988.3 | 8020 | 0.000000 | 0.010201 | -0.010201 | 1.194584 | -0.0085 | 1.8148 | 5 | margin |
| 1148.7 | 5208 | 0.170624 | 0.042069 | 0.128555 | 1.749681 | 0.0735 | 2.6581 | 1 | margin |
| 1153.3 | 5388 | 1.056968 | 0.040094 | 1.016874 | 1.661272 | 0.6121 | 2.5238 | 2 | margin |

### The distribution of (gain - harm) / (w_d x MARGIN_CF), and it is BIMODAL, not piled up below 1

n = 22, 22 distinct values. min -0.0228, p25 -0.0153, **median -0.0088**, p75 1.3067, max 2.1060.

| band | n of 22 |
|---|---|
| ratio <= 0 (gain below the decider's own loss) | **12** |
| 0 < ratio < 0.5 | 1 |
| **within 50 % of the margin (0.5 <= ratio < 1)** | **3** |
| **within 80 % of the margin (0.8 <= ratio < 1)** | **1** |
| ratio >= 1 (crossed, fired) | 6 |

**There is no cluster just below the margin.** One candidate of 22 sits within 80 percent of it and
three within 50 percent. The mass is at the two ends: 12 candidates have gain **exactly 0.000000**,
and 6 clear the bar by 1.3x to 2.1x.

At 0.25x (dry, logical-only) the same picture is sharper: 11 of 82 reach the harm, 7 of 11 have
gain exactly zero, the maximum ratio is 0.8632, and **nothing fires**, because protect-and-defer has
already deferred the candidates this leg would have taken.

---

## 2. Is the harm many small effects or few large ones? FEW LARGE ONES.

| quantity | value |
|---|---|
| added first-token delay per frame, D162 queue term `0.0001535807289338535 x u` | min 0.703 s, **median 1.039 s**, max 1.232 s |
| the alert deadline that delay is measured against | **1.0 s** |
| alert frames queued behind a candidate | 1 (x6), 2 (x6), 3 (x6), 5 (x3), 6 (x1) |
| per-frame weighted on-time answer avoided, over the 11 candidates that saved anything | 0.0093, 0.1706, 0.5190, 0.5285, 0.7405, 0.7447, 0.9743, **1.0053, 1.0213, 1.0237, 1.0269** |

**The added delay is comparable to the entire alert deadline**, so a frame left in front of the
prefill does not degrade, it is lost outright. The exact per-row record for the traced decision says
so in one line: `opp0005452`, qtype alert, slack 0.5561 s, `value_lost 1.005309` on a single row, out
of one row considered and one moved.

So the gain is **quantised in whole alert frames at roughly 1.0 on-time answer each**: the observed
gains are 0 (x11), 0.028, 0.171, then ~1.0 (x4), ~2.0 (x4), and 3.06. Against an unweighted MARGIN_CF
of 0.65824, **one saved frame already clears the unweighted bar.**

### What actually decides whether the gain is 0 or ~1: the deferral LENGTH

A frame is saved only if its own remaining slack is at or below the deferral. The deferral available
is the recall's own slack minus `1.8721 x predicted service`, and the two groups separate cleanly:

| group | n | deferral_s min | median | max |
|---|---|---|---|---|
| gain exactly zero | 11 | 0.1223 | **0.2745** | 0.7299 |
| gain non-zero | 11 | 0.3753 | **1.0067** | 1.3550 |

and 47 of 88 candidates got no deferral at all. **The binding constraint is how much slack the recall
question itself has, not the margin.**

The four candidates with a real gain that still did not fire (ratios 0.61 to 0.87) failed for the
ruled reason, not a mispricing: each had gain near 1.0 against a bar raised to 1.16 to 1.66 by its own
`w_d` of 1.77 to 2.52. That is D178 (5)'s sign direction working as specified, a lagging recall device
defers less.

---

## 3. What was actually in front of the LATE alerts, from the committed rung-3 s4 cell

11,764 alert instants, **8,356 sent** to the cloud, **2,290 sent and late** against the 1.0 s
deadline. For each late alert, every request occupying the engine when it arrived, classified, and
weighted by uncached tokens, which is what the D162 queue term charges:

| class in front | share with ANY of it ahead | **DOMINANT by uncached tokens** | requests ahead |
|---|---|---|---|
| **RECALL QUESTION** | 9.4 % | **6.9 %** | 229 |
| recall WARM or TOUCH | 27.9 % | 2.8 % | 2,247 |
| **OTHER ALERTS** | 96.1 % | **84.1 %** | 7,550 |
| single-shot | 18.4 % | 4.8 % | 427 |
| nothing ahead at all | | 1.2 % | |

**Alert lateness at rung 3 is overwhelmingly alert-on-alert self-congestion.** Only 132 recall
question requests exist in the whole cell, against 8,354 alert requests.

**Proxy declared.** "In front of it" is a proxy: the logs give submit and first-token times, not the
engine's internal batch order, so no definition here is the engine's own queue. The conclusion does
not depend on the choice:

| definition | RECALL QUESTION dominant | OTHER ALERT dominant |
|---|---|---|
| occupying the engine on arrival | 6.9 % | 84.1 % |
| overlaps my whole wait window | 6.3 % | 91.3 % |
| submitted before me, or overlapping | 6.3 % | 91.3 % |

---

## 4. Which branch the data supports

**Neither (i) nor (ii) as stated. The data separates them and rejects both, and it points at a third
reading.**

**(i) "candidates cluster just below the margin" is FALSIFIED.** One candidate of 22 is within 80
percent of the margin and three within 50 percent; the median ratio is -0.0088 and 12 of 22 have gain
exactly zero. Further, the premise behind (i) does not hold: the harm is **not** aggregate small-effect.
It is per-frame total loss of about 1.0 on-time answer, because the queue delay (median 1.039 s) is
larger than the whole 1 s alert deadline. So the margin's yardstick, a p90 error of a single
robot-question prediction, is **well matched** in magnitude to this harm, not mismatched: one saved
frame is about 1.5x the unweighted margin. **There is no evidence here that MARGIN_CF is the wrong
yardstick**, which removes the premise option (b) rested on.

**(ii) "gains are inherently small" is FALSIFIED AS WRITTEN.** When a deferral clears a frame the gain
is 1.0 to 3.1 on-time answers, 1.3x to 2.1x the bar, and 6 of 22 candidates cleared it.

**The reading the data does support, and it reaches (ii)'s conclusion by a different route:
question deferral cannot address alert lateness at 1x, because the traffic is not there.** Two
independent bounds, each measured, and they multiply:

1. **Reach.** A recall question is in front of only **9.4 percent** of late alerts and is the dominant
   term for **6.9 percent**. 84 percent are blocked by other alert frames, which no amount of
   question deferral can move. That is a ceiling on the mechanism from the workload, not from the
   policy.
2. **Yield within reach.** Where a recall question IS in front, the deferral available is bounded by
   the recall's own 3 s deadline minus `1.8721 x service`, and it is too short to clear any alert
   deadline in 11 of 22 cases. 47 of 88 candidates get no deferral at all.

Taken together, the dry s4 run's 6 deferrals save **14 alert-frame losses**, against **2,290** late
alerts in the live rung-3 s4 cell: about **0.6 percent**. That comparison crosses registers, dry
decisions against a live count, and is offered as an order of magnitude and not a prediction.

**What this says about the three options, without taking any of them.** Option (b), re-deriving the
safety factor from more committed rows, addressed the zero margin on the self-inflicted-loss column;
it does not touch either bound above, so it would buy confidence in the 6 deferrals rather than more
of them. Option (c), a retained-slack floor, acts on bound 2 and would reduce the deferral count
further, not raise it. Neither reaches bound 1, which is the larger of the two by an order of
magnitude.

**And the finding that is positive rather than negative:** alert lateness at this fleet size is an
alert-on-alert admission and capacity problem, which is the axis the D179 shares and floors work
occupies, not a recall-versus-alert timing problem. That is a statement about where the remaining
2,290 late frames live, and it is measured, not inferred.

**For the user's ruling.** Nothing was tuned, nothing was posted, and no parameter was moved.
