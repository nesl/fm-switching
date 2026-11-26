# LINKSYNC s4 SCOPE A GATE: READOUT (H100, 2026-11-26 ~01:50 PST)

Scored against `research/study_linksync_s4_gate_prereg.md` (prereg 2026-11-26T01:38:13Z, amendments 01:49:35Z and 01:52:22Z, disclosure 01:56:39Z, all before any cell). A mechanism check, not a significance test: counts are descriptive. Nine cells, all POST-PUSH on live2 ed93608b434938204b49aded2a2cd93e9d7201ea, driver v43, run 2026-11-25 18:16 to 2026-11-26 01:30.

**What this file is NOT.** The H100 rule forbids host Python while cells run, so `experiments/analysis/robot_idle/link_sync_readout.py` was NOT run. Items 1, 2, 3 and the question part of item 4 below were computed with `jq` over `outcomes.jsonl`, `link_events.json` and `link_sync_log.json` (script: H100 scratchpad `linksync_items.sh`, definitions stated per item). NOT computed here: the dashcam part of item 4 and the per-question correctness and path of item 5 (needs the cloud letter and the controller question log). flash's script reads the same artefacts and should be run on CPU for those; this readout does not stand in for it.

## Per-cell validity (check 7 inputs)

| arm | k | valid | SA (header.json) | errors | ENOSPC | robot n | cbd | cloud on-time | acc served | device standing | SS | dashcam on-time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main q-sync | 1 | yes | OK | 0 | 0 | 229 | 136 | 179 | 0.620 | 50 | 214 | 4,656 |
| main q-sync | 3 | yes | OK | 1 | 0 | 229 | 135 | 175 | 0.623 | 54 | 219 | 4,649 |
| main q-sync | 5 | yes | OK | 0 | 0 | 229 | 138 | 167 | 0.635 | 62 | 219 | 4,718 |
| ablation q-sync-d177 | 1 | yes | OK | 0 | 0 | 229 | 130 | 177 | 0.605 | 52 | 223 | 4,827 |
| ablation q-sync-d177 | 3 | yes | OK | 0 | 0 | 229 | 130 | 174 | 0.609 | 55 | 223 | 4,726 |
| ablation q-sync-d177 | 5 | yes | OK | 0 | 0 | 229 | 134 | 172 | 0.628 | 57 | 219 | 4,777 |
| control q-sync-ctl | 1 | yes | OK | 0 | 0 | 229 | 134 | 172 | 0.610 | 57 | 217 | 4,611 |
| control q-sync-ctl | 3 | yes | OK | 0 | 0 | 229 | 130 | 174 | 0.603 | 55 | 216 | 4,665 |
| control q-sync-ctl | 5 | yes | OK | 1 | 0 | 229 | 135 | 167 | 0.623 | 62 | 216 | 4,610 |

Fleet figures are context only (a fleet cbd is not the verdict, per the prereg). Robot on-time is never quoted alone: each row carries cbd, accuracy on served and device standing. The two single errors are request errors that left the cells valid.

**Check 7 on the control.** `q-sync-ctl` is a new arm with no committed cell, so there are no committed control values to compare. What can be checked: SA OK in `header.json` for all three control cells; the control shows FIFO order (below); its fleet figures (cbd 130 to 135) sit with the main and ablation arms at the same k and near the committed same-mix references (P3 127, `-q` 136). No broken control found. This is a consistency check, not a comparison against committed values.

## Port-rule counters (prereg honesty condition)

| arm | k | link_sync_releases | holds_serial | holds_harm | questions_before_catchup | plan_calls | QUESTION_FIRST / WAIT / LEAVE_TO_DEVICE | release order vs reconnect order | release why |
|---|---|---|---|---|---|---|---|---|---|
| main | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | robo001 / robo001 | priority |
| main | 3 | 3 | 18 | 15 | 0 | 0 | 0 / 0 / 0 | 003,001,009 / 001,003,009 | priority |
| main | 5 | 5 | 34 | 2 | 0 | 0 | 0 / 0 / 0 | 010,001,004,003,009 / 001,003,004,009,010 | priority |
| ablation | 1 | **0** | 0 | 6,000 | 16 | 16 | 16 / 0 / 0 | none released | none |
| ablation | 3 | **0** | 0 | 6,000 | 47 | 47 | 47 / 0 / 0 | none released | none |
| ablation | 5 | **0** | 0 | 6,000 | 61 | 61 | 61 / 0 / 0 | none released | none |
| control | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | robo001 / robo001 | fifo |
| control | 3 | 3 | 18 | 0 | 0 | 0 | 0 / 0 / 0 | 001,003,009 / 001,003,009 | fifo |
| control | 5 | 5 | 34 | 0 | 0 | 0 | 0 / 0 / 0 | 001,003,004,009,010 / 001,003,004,009,010 | fifo |

Port rule: main shows a non-zero catch-up decision at every k (HELD). Control shows FIFO order at every k (HELD, order identical to reconnect order, why = fifo). Ablation: ZERO releases at every k (HELD, and stronger than "never release early": it never released at all within the run; the held backlog was never delivered, and `plan_sync` chose QUESTION_FIRST 100 percent of the time). Main's question-first / wait / device branch fired 0 times at every k (no question arrived before catch-up), as the disclosure predicted: that branch is UNEXERCISED.

## Items 1 and 2, per victim (reconnect = 600 s; seconds after reconnect)

Item 1 = reconnect to the first ON-TIME CLOUD answer to any of the victim's questions (a recall question asked at or after the reconnect, `within_L` true, cloud answer present), measured at delivery. CENSORED = none exists (count, never zero). Item 2 = reconnect to the victim's backlog fully uploaded (`pull_arrived` time in `link_events.json`; the plan's `history_arrived` field was not located in these artefacts, so arrival of the pulled backlog is used and labelled as a proxy); CENSORED where no backlog arrived. "first q" = seconds from reconnect to the victim's first post-reconnect question (trace ground truth, scoring only).

| k | victim | first q | item 1 main | item 1 ablation | item 1 control | item 2 main | item 2 ablation | item 2 control | on-time cloud q / asked (main, abl, ctl) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | robo001 | 123.9 | 126.8 | 125.6 | 131.2 | 0.1 | CENSORED | 0.1 | 14/16, 16/16, 14/16 |
| 3 | robo001 | 123.9 | 126.5 | 125.5 | 126.6 | 2.6 | CENSORED | 0.1 | 15/16, 16/16, 15/16 |
| 3 | robo003 | 38.3 | 40.2 | 39.1 | 40.2 | 0.1 | CENSORED | 1.1 | 12/14, 11/14, 10/14 |
| 3 | robo009 | 117.0 | 118.9 | 118.3 | 118.9 | 3.6 | CENSORED | 2.1 | 17/17, 16/17, 17/17 |
| 5 | robo001 | 123.9 | 131.2 | 125.5 | 131.1 | 1.0 | CENSORED | 0.1 | 14/16, 16/16, 14/16 |
| 5 | robo003 | 38.3 | 39.8 | 39.1 | 40.3 | 3.1 | CENSORED | 1.1 | 10/14, 11/14, 10/14 |
| 5 | robo004 | 262.7 | 393.5 | 325.7 | 343.7 | 2.1 | CENSORED | 2.1 | 6/11, 9/11, 7/11 |
| 5 | robo009 | 117.0 | 118.8 | 118.4 | 119.0 | 4.1 | CENSORED | 3.0 | 16/17, 16/17, 16/17 |
| 5 | robo010 | 539.3 | CENSORED (0/3) | 556.9 | 556.2 | 0.1 | CENSORED | 3.9 | 0/3, 1/3, 1/3 |

Reading (descriptive):
- **No victim is urgent at s4.** The earliest first post-reconnect question is robo003 at 38.3 s, above the 30 s definition, exactly as the 01:56 disclosure said. The pre-registered item-1 expectation (main beats control for urgent victims, no greater item-4 harm) is therefore VACUOUS, not held and not failed.
- Item 1 is dominated by when the question is asked (first q column), not by catch-up: main and control differ by 0 to 4.4 s for the five early victims, and by +49.8 s (robo004, 393.5 against 343.7) and CENSORED against 556.2 (robo010, 0 of 3 on-time against 1 of 3) at k=5, where main is the worse arm. With 4 matched questions no significance is claimed.
- Item 2: main and control drain within 4.1 s at every victim (main 0.1 to 4.1, control 0.1 to 3.9). The dry build's predicted slower main drain (about 17 s) is not seen live. The ablation never drains (CENSORED for all 9 victims).
- The ablation's item-1 times are earlier than main's and control's at several victims because it answers question-first, without the backlog; item 5's correctness (not computed here) is what that costs.

## Item 3: did catch-up order follow expected-question urgency

At reconnect the policy-side next-expected-question estimates are TIED across victims in every cell (all equal to the reconnect time plus 0.03 to 0.07 s, e.g. k=3: robo001, robo003, robo009 all 600.07; k=5: all 600.05), so the prereg's concordance (order agreeing with policy-side estimates) is UNDEFINED, not zero. As an extra descriptive, using the trace's first-question order (ground truth, scoring only; order robo003 38 s, robo009 117 s, robo001 124 s, robo004 263 s, robo010 539 s):
- k=3: main release order 003,001,009 agrees on 2 of 3 pairs; control FIFO 001,003,009 agrees on 1 of 3.
- k=5: main release order 010,001,004,003,009 agrees on 2 of 10 pairs (it releases the victim whose first question is LAST, robo010, first); control FIFO 001,003,004,009,010 agrees on 7 of 10.
So at k=5 the main arm's order is not urgency-ordered by the true question order, and worse than FIFO; main's order came from its priority term (all releases `why = priority`), not from question urgency, since the estimates it had were tied.

## Item 4: on-time loss to other devices inside the catch-up window

The catch-up window (reconnect to the last victim's backlog arrival) is 0.09 s (k=1), 3.6 s (k=3, main; 2.1 s control) and 4.1 s (k=5, main; 3.9 s control). Non-victim questions inside the window: 0 at k=1, 1 at k=3 and 1 at k=5, on time in both arms. The window is too short to contain more than one question; the dashcam-instant part was NOT computed here (flash's script). The ablation has no window (nothing released).

## Item 5: how each affected question was served, and correct

Not computed on H100 (needs the cloud letter and the question log). Beside it, from the cells' `robot_headline`: the validity table's cbd, accuracy on served and device standing (a fleet figure, not the item-5 readout). Device accuracy stays 0.257732 in the main currency as confirmed; the 0.37 live figure is not mixed in.

## Which pre-registered expectations held, failed or were vacuous

| expectation | status |
|---|---|
| Main beats control on item 1 for urgent victims, no greater item-4 harm | VACUOUS (no urgent victim at s4; earliest first question 38.3 s). Read descriptively: no consistent main advantage; main worse at k=5 for robo004 and robo010 |
| Main shows a non-zero catch-up decision (port rule) | HELD (releases 1/3/5, holds_serial 0/18/34, holds_harm 0/15/2) |
| Control shows FIFO order | HELD (all three k, why = fifo) |
| Ablation never releases early | HELD, and stronger: zero releases at any k, backlog never delivered |
| Main's question-first / wait / device branch | UNEXERCISED (0 plan calls at every k, as the disclosure said) |
| Main drains slower than control (dry: about 17 s against 1 to 4 s) | NOT SEEN live: both drain within 4.1 s |

## Rule 2 classification of the null

The gate returns no pre-registered win for the main arm, and the reasons are different per expectation, so one label does not fit:
- Item 1 expectation: **unexercised** (no urgent victim).
- Items 1 (descriptive), 2 and 4: **cancelled by geometry** in this reading: the backlog is small (about 60 frames, 5,400 tokens per victim) and drains in under 4.1 s in both main and control, so the catch-up window holds at most one non-victim question and the ordering has almost no room to change anything. H100 states this as its reading; flash should confirm or reclassify.
- Main's priority order at k=5 being worse than FIFO against the true question order: **fired and did not help** (the decision operated, its inputs were tied estimates, and the order it chose is not urgency-ordered). This is the only line here that is evidence about the policy, and it is n = 5 victims at one seed.
- The ablation's zero releases: the mechanism's expected behaviour, held.

No claim about the policy is made from this gate beyond those lines.

## Provenance

H100, jq only. Cell directories `results/orchestration/live2/frozen_test/runs/covex-v6-fair-final-{q-sync,q-sync-d177,q-sync-ctl}_n16_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k{1,3,5}-d120_evid-t4800_link_sync`. Counters from `link_sync_log.json` (`counts`, `sync_counters`, `sync_log`) and `link_events.json` (`link_log`: `pull_arrived`, `arrived`); questions from `outcomes.jsonl`.
