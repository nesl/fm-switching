# LINKSYNC s4 SCOPE A GATE, PRE-REGISTERED BEFORE ANY CELL (2026-11-26T01:38:13Z). A MECHANISM CHECK, NOT A SIGNIFICANCE TEST. Nothing built has run; no cell exists.

**User ruling (D278 dev loop).** Cells at s4 only, no s5-s7: our sync arm against the naive-recovery control (FIFO catch-up, deficit gain 0, D226), rule A window (`t0 = 480 s`, 120 s, identical across k), ladder k in {1,3,5}, `_c3-11-2`, 1x, no memory token = **6 cells**. Baselines afterwards. Arm names and the exact cell lines are fixed by a timestamped amendment BEFORE any cell.
**Power, stated up front:** at s4 under rule A there are 4 matched questions (2 for k 1 to 3, 2 for k 3 to 5). Even if all 4 flip the same way the one-sided p is 0.5^4 = 0.0625, above 0.05. **So matched-question counts are DESCRIPTIVE and no significance is claimed.**

## Primary readout (ruled), per victim, our arm against the control, paired by victim and k
1. **Reconnect-to-first-on-time-cloud-answer:** seconds from the victim's reconnect to the first ON-TIME CLOUD answer to any of its questions; censored (no such answer) reported as a count, never as zero.
2. **Backlog drain time:** reconnect to the backlog fully uploaded AND in the cloud's history (`history_arrived`), per victim.
3. **Did catch-up order follow expected-question urgency:** the fraction of victim pairs (k>=3) whose catch-up completion order agrees with the order of their policy-side causal next-expected-question estimates at reconnect (D11/D48; never the trace's future). Undefined at k=1.
4. **On-time loss to other devices inside the catch-up window:** the catch-up window is reconnect to the last victim's backlog arrival in that arm; count questions and dashcam instants of NON-victim devices that miss their deadline inside the window, our arm minus the control, paired by (device, opportunity_id) since both arms see the identical trace.
5. **How each affected question was served** (cloud with full evidence / cloud question-first / device) **and whether it was correct** (correct-by-deadline and cloud accuracy on served beside it).
**Scoring definition proposed by flash and amendable before any cell:** an "URGENT victim" is a victim whose first post-reconnect question is asked within 30 s of its reconnect (trace ground truth, used for SCORING only, never by the policy).

## Expected (recorded now so it cannot be fitted afterwards)
**Our arm beats the naive-recovery control on item 1 for the urgent victims, with NO GREATER harm in item 4.** If that does not hold it is reported as not held, and under the dev loop it feeds the next iteration; it is not a freeze result.

## Invalidation and honesty conditions
A fleet robot cbd, or a matched-question count, quoted as the verdict is withdrawn. Robot on-time is never quoted alone. A result read from a cell whose `link_` counters are zero is an ABSENT LINK, not a result: our arm must show its catch-up decision (a non-zero `link_` sync counter) and the control must show FIFO order. The `plan_sync` question-first accuracy is the oracle FAIR value `recall|cloud|WITH_HISTORY` = 0.568799 (n 12,660, `oracle_fair_table.json`), **PROVISIONAL**; that table's device value 0.258 is a pooled population and is NOT mixed with the 0.37 robot device accuracy used in correct-by-deadline. Questions asked during the outage are device-only (D242). The full proof suite runs at the freeze, not per stage (D278 dev loop).
