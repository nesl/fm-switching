# QUEUED-AHEAD TOKENS AT ROBOT QUESTION ARRIVAL (2026-11-26T00:35Z). CPU, committed cells, nothing built. Question-time queue is a little larger than decision-time on the mean, much smaller at the median, and heavy-tailed.

**Definition: the D162 one** (`v5/cf_ontime_d162.py`, `d249_queue_visibility.py`): uncached tokens (prompt - cached) of OTHER requests with t_submit < t_arrival < t_first_token; arrival = the outcome's t_opportunity, so declined questions are included; seconds at 0.00015358 s per token. **Proxy caveat: reconstructed from first-token intervals, which is self-referential (a request delayed by queueing widens its own interval and later arrivals' apparent queue); it inflates congested cells and the tail and cannot create a queue where none existed. The queue includes the robot's own frame uploads.**
All cells s4; 7 robots / 132 questions except robot-heavy 11 / 229. Source agreement OK on 6; the 1x un-suffixed rung-3 cell has no `source_agreement` key in its header and was run unflagged.
| arm | zero | mean tok (s) | p10 / p50 / p90 / p99 tokens |
|---|---|---|---|
| 1x rung 3 | 2.3% | 2,289 (0.352) | 747 / 1,764 / 4,218 / 13,305 |
| 1x `-q` | 0.8% | 3,100 (0.476) | 734 / 1,842 / 3,917 / 29,534 |
| halved memory rung 3 | 3.0% | 6,664 (1.023) | 743 / 2,608 / 15,377 / 50,439 |
| halved memory `-q` | 4.5% | 4,641 (0.713) | 734 / 1,809 / 14,419 / 24,380 |
| robot-heavy P3 | 18.3% | 4,967 (0.763) | 0 / 831 / 20,070 / 47,993 |
| robot-heavy `-q` | 18.8% | 4,409 (0.677) | 0 / 746 / 14,185 / 43,270 |
**Cross-check against the live decision-time delay (`arm_stats`: milli_sum / priced), which averages all priced items and is capped at 2.781 s, so the two are different populations:** 1x 0.393 s against 0.476 s (1.21x); halved 0.522 against 0.713 (1.37x); robot-heavy 0.426 against 0.677 (1.59x). Question-time medians are 0.283, 0.278 and 0.115 s.
**Declined questions** sat in a larger queue than sent ones in 3 of 5 arms, but the declined groups are 3 to 34 questions: weak evidence.

## Reading
- **Pricing a future question at the CURRENT queue is roughly unbiased to mildly low on the mean (1.2x to 1.6x), overstates the typical question (median 0.1 to 0.3 s) and understates the tail (p90 0.6 to 2.4 s). A point estimate matches neither the median nor the tail; expected-queue pricing would need a distribution or quantile, not a number.**
- **An observation, not a cause (self-referential proxy, one seed each):** at 1x `-q` faces a LARGER question-time queue than rung 3 (mean 3,100 against 2,289 tokens, p99 29.5k against 13.3k), while under both pressures it faces a SMALLER one (4,641 against 6,664; 4,409 against 4,967). That is the same sign pattern as the three gate results (fail at 1x, pass under both pressures).
