# D249 DEV BUILD 2 (D256): THE CAP IS IN, IT CHANGES NOTHING, AND TOUCH IS STILL UNREACHABLE

*** D256 (c)'s STOP CONDITION IS REACHED. No second code change was attempted. THE DECISION IS THE USER'S. ***
**Nothing is committed to `experiments/`. No live gate cell was run, per D256. KV is not enforced in this
harness, so no kv0.5r claim is made from any of it.**

## (a) THE CAP: applied, counted, and it moves NO decision

**One file, mirroring `cf_objective.py:838-839` rather than inventing a form: in `arms_v6state.py::_p_warm_cold`,
at the single place the D249 path turns tokens into seconds.** `diff -rq` shows exactly one source file changed.
```
d249_pwc_queue_capped = 5,740 of 61,678 decisions (9.31 pct)      0 on the OFF arm, 0 on the uncapped tree
max applied delay  15,705 ms -> 2,781 ms
aggregate predicted delay  43,152.250 s -> 31,988.427 s  (-25.9 pct)
```
*** AND THE ON LOG IS BYTE-IDENTICAL CAPPED AND UNCAPPED: 11,386 rows, digest `b7bb6e018b6e1d27`, 0
positional, 0 setwise. A 25.9 PERCENT REDUCTION IN PRICED DELAY CHANGES NOT ONE DECISION. ***

## (b) MARGIN PROVENANCE: RECOVERABLE, with TWO CITATIONS CORRECTED BY THIS SESSION

| field | value |
|---|---|
| statistic | nearest-rank **p90** of `A_D2_DEV x abs(P_hat - 1[on time])` |
| code | `experiments/orchestration/live2/v5/margin_cf_d169.py` *(the agent omitted the `v5/` prefix)* |
| population | **476 robot questions** in healthy-regime windows over 8 committed rq30 cells (n16, seeds 4 to 7), committed BEFORE scoring in `margin_cf_population_d169.json`; n_warm 271, n_cold 205, minima 40/40 |
| model | `P_hat` = `cf-ontime-d162-1.0`, hash-frozen before scoring |
| result | **p90 overall 0.16456**, warm 0.150341, cold 0.173231, **p50 0.01156** |
| pre-registration | units at D157 (2) before the gate ran; procedure and n >= 40 at D168; population replacement and the "freeze, commit, compute" order at D169 |
| `A_D2_DEV` | **0.250 = 7 of 28**, Wilson CI **[0.1268, 0.4336]**, declared at `cf_protect_defer.py:258` |

*** TWO ATTRIBUTION CORRECTIONS, BOTH MADE BY CHECKING RATHER THAN RELAYING. Dev build 1 cited `2cb2d5c1`
for the code constant; build 2 corrected that to `478e6cc5`; BOTH ARE WRONG. At `2cb2d5c1` and at
`478e6cc5` the committed `cf_margin.py` still reads `MARGIN_CF = 0.05` (and `= None` at the latter). THE
FIRST COMMIT WHOSE TREE CARRIES `MARGIN_CF = 0.16456` IS `96655fd0`. ***
**The right reading, which reconciles it with the ledger: D171 attributes the VALUE to `2cb2d5c1`, where it
was derived and accepted, and the ledger's own n = 476 and warm = 271 match this population exactly. The
CODE CONSTANT landed later, at `96655fd0`. Two events, two commits, and build 2 was right that they differ
and wrong about which.**
**Two record defects carried forward, neither affecting arithmetic: `cf_margin.py:62` calls `A_D2_DEV` a
"delta" when it is an absolute accuracy, and that module's docstring still reads as if the constant were
unset. The 476 per-question errors are NOT committed, only the summary.**

## *** THE LEVER: THE MARGIN IS AN OUTCOME-NOISE QUANTILE COMPARED AGAINST A DETERMINISTIC SIGNAL ***

**The error is measured against the REALISED BERNOULLI OUTCOME of a single question. For any
well-calibrated forecast that distribution has mass near `p` and near `1 - p`, so its UPPER DECILE is
dominated by outcome randomness that NO model can remove.** The committed numbers show exactly that:
```
on-time units:  p50 error 0.04624     p90 error 0.65824     ratio 14.2x
```
*** AND THE QUANTITY THE BAR IS COMPARED AGAINST, `p_question x (p_warm - p_cold)`, CONTAINS NO SUCH TERM.
SO THE BAR IS NOT MIS-SET; IT IS MEASURING A DIFFERENT KIND OF QUANTITY. ***

## PROPOSED RECALIBRATION. REPORTED ONLY, NOT APPLIED, NOT COMPUTED, per D256 (b)

**Keep D154 (2), the population, the frozen `P_hat`, the healthy-window filter, the minima, the pre-commit
order and the p90 quantile EXACTLY as committed. Change only WHAT THE ERROR IS MEASURED AGAINST.**
- **METHOD A (primary): CALIBRATION error.** Bin the same 476 questions by predicted `P_hat` (pre-registered
  equal-count deciles, min 40 or merge); per-bin error `abs(mean(P_hat|bin) - freq(on time|bin))`; margin =
  p90 of that over questions; warm and cold reported separately as today.
- **METHOD B (secondary): the error of the DIFFERENCE the planner actually reads**, p90 of
  `abs((P_hat_warm - P_hat_cold) - (freq_warm - freq_cold))` within matched bins. Secondary because the
  pairing is across questions and needs its own ruling.
**WHY THIS IS NOT TUNING TO ARM OUTCOMES: it reads only `(P_hat, realised on-time, warm flag)` for a frozen
model on a pre-committed population at a quantile fixed in advance. No arm action, no TOUCH or HOLD_BACK
count, no policy metric, no arm comparison. IT WOULD RETURN THE SAME NUMBER IF D249 DID NOT EXIST.**
*** AND THE FORBIDDEN SHORTCUT IS NAMED SO IT IS EXCLUDED: taking the margin from the observed Z
distribution in (c) WOULD be tuning to arm outcomes by the back door, because that distribution is an
OUTPUT OF THE ARM UNDER TEST. ***

## (c) REACHABILITY, STRUCTURAL, WITH AND WITHOUT THE CAP: THE STOP CONDITION

`Z = p_question x (p_warm - p_cold) - harm_touch / w_d`, over 61,678 decisions with TOUCH scored at every one.
| | ON, no cap | ON, capped |
|---|---|---|
| Z p10 / p50 / p90 / p99 / **max** | 0.0000866 / 0.005459 / 0.16754 / 0.38009 / **0.555588** | 0.000146 / 0.006822 / 0.16754 / 0.38009 / **0.555588** |
| **decisions where TOUCH COULD clear the bar** | **0 of 61,678** | **0 of 61,678** |
| **TOUCH chosen** | **0** | **0** |
| max `p_warm - p_cold` | 0.593995773 | 0.593995773 |

**THE CAP RAISES Z IN THE MIDDLE AND NOT AT THE TOP: median +25 pct, p25 +33 pct, while p90, p99 and the
MAXIMUM do not move to nine decimals.** **Because the decision with the widest warm-cold gap ALREADY had a
queue inside the bound, so capping cannot widen it.**
*** Z max 0.555588 IS 84.4 PERCENT OF THE 0.65824 BAR, SHORT BY 0.102652. And the largest warm-cold gap
anywhere, 0.593995773, IS ITSELF BELOW THE BAR, so TOUCH is unreachable even at `p_question = 1`. ***
**From the logs ONLY, as a statement about this cell and not a proposal: a bar above 0.5556 is unreachable
everywhere here; 0.38009 would be clearable at 1 pct of decisions and 0.16754 at 10 pct.** **THESE ARE NOT
CANDIDATE MARGINS. Choosing one from this list is the forbidden shortcut named above.**
**THIS CONTRADICTS D246.**

## (d) LIGHT PROOFS, with (a) only

| | OFF | ON uncapped | ON capped |
|---|---|---|---|
| KEEP | 57,960 | 61,610 | **61,610** |
| **TOUCH** | **2,954** | **0** | **0** |
| HOLD_BACK | 0 | 68 | **68** |
| WARM | 6 | 0 | **0** |
| deviations | 2,960 | 68 | **68** |
**Decisions changed vs rung 3: positional 12,344, setwise 3,977**, first differing decision quoted.
**Switch-OFF identity HOLDS on the committed bar: 14,539 rows, `5a03c2807da3681a`, 0 positional, 0 setwise.**
**Positive control NOT vacuous: `llf` identical before/after at 14,075 / `961be8fe4942d86b`, and `llf`
against rung 3 differs at ROW INDEX 0.** **New instrument control: the ON arm run plain and under the
reachability probe are BYTE-IDENTICAL, so the probe does not perturb what it measures.**
**Hazards re-checked: 4 of 4 `CC.predict(` sites still carry literal `0, 0`; unit suite 20 of 20 PASS.**

## TWO ARTEFACT TRAPS, recorded so nobody repeats them

1. *** BUILD 1's `cell_r3q_after.json.gz` IS ITS SUPERSEDED PRE-SLACK-ALIGNMENT ON CELL: `d249_queued_ahead_reads` EXACTLY DOUBLED (122,506 against 61,678). ANYONE COMPARING AGAINST BUILD 1 MUST USE
   `cell_r3q2_after`. The digest is the SAME either way, so a digest check would NOT have caught it. ***
2. **`reach_uncap.json`'s `queue_delay_s_as_applied` column is MISLABELLED: it is `min(delay, 2.781)`
   regardless of tree, so in the UNCAPPED file it is not what that tree applied.** The authoritative
   uncapped maximum is the arm's own `d249_pwc_queue_max_milli` = 15,705 ms.

## OWED BEFORE ANY OF THIS IS CITED

**NO E-id exists for D249 or D256 in `research/EXPERIMENTS.md` (verified: zero occurrences of either), and
there is no `results/INDEX.md` row for the margin artefacts.** CLAUDE.md requires one before the work is
cited.

---
---

# THE AGENT'S FULL RECORD FOLLOWS, UNEDITED

# D249 DEV BUILD 2, under user ruling D256: THE CAP, THE MARGIN PROVENANCE, AND REACHABILITY

**BUILT IN SCRATCH. NOTHING APPLIED TO THE REPOSITORY, NOTHING COMMITTED, NOTHING PUSHED.**
Build 1's trees were REUSED, not rebuilt. `before/` and `after/` are build 1's trees (archive of
`origin/main` at `d7aa473e99c886f2c27f3e95523ed8256d604152`); `after_cap/` is a copy of `after/`
plus the single change in (a). Read-only git at `a6c6eb4ffcf1f04e8e7fdf689d6159aebe02164e`, which
is today's `origin/main` and is AHEAD of the sha build 1 pinned; the code read for (b) was read at
`a6c6eb4f`, the cells ran on build 1's tree, and the two are named separately wherever it matters.

Disk at start: 24 GB free (floor 15 GB).

---

## (a) THE CAP. The only code change in this build.

`after_cap/experiments/orchestration/live2/arms_v6state.py`, inside `_p_warm_cold`, at the one
place in the D249 path where a token count has become seconds. It mirrors `cf_objective.py:838-839`
line for line, on the same constant, read by name from the same module.

```diff
         try:
             import cf_cost as CC
+            import cf_objective as CO
             cf = self._cf_engine()
             warm = CC.predict(cf.model, int(est_tokens), int(built_tokens), 0, 0)
             cold = CC.predict(cf.model, int(est_tokens), 0, 0, 0)
             q_s = QV.queue_delay_s(int(queued_ahead_tokens), cf.model) \
                 if int(queued_ahead_tokens) > 0 else 0.0
+            # D256 (a): THE CAP, mirroring `cf_objective.py:838-839` exactly, on the same bound
+            # and for the same reason (D160 (2) does not trust the D162 model across the
+            # saturation transition). The harm path has capped its added delay since it was
+            # written; the D249 (b) pricing path did not, and added up to 15.705 s of predicted
+            # first token in the posted cell, 9.31 pct of its prices landing outside the bound.
+            # Counted, never silent, as `harm_warm_capped` is.
+            capped = False
+            if q_s > CO.HEALTHY_FIRST_TOKEN_BOUND_S:
+                q_s = CO.HEALTHY_FIRST_TOKEN_BOUND_S
+                capped = True
+            if capped:
+                self.stats["d249_pwc_queue_capped"] += 1
             if q_s > 0.0:
```

The mirrored original, for the record:

```
cf_objective.py:792   HEALTHY_FIRST_TOKEN_BOUND_S = 2.781          # D160 (2); the cap, never silent
cf_objective.py:837       capped = False
cf_objective.py:838       if dt > HEALTHY_FIRST_TOKEN_BOUND_S:
cf_objective.py:839           dt = HEALTHY_FIRST_TOKEN_BOUND_S
cf_objective.py:840           capped = True
```

`diff -rq after after_cap` reports exactly ONE source file changed (plus its `.pyc`). The margin
is untouched; nothing else is touched.

**THE CAP COUNT, per cell, in `arm_stats`:** `d249_pwc_queue_capped` = **5,740** of 61,678 state
decisions (60,723 of them priced a non-zero queue), i.e. **9.31 pct**, and
`d249_pwc_queue_max_milli` falls from **15,705 ms to 2,781 ms**. Aggregate predicted queue delay
falls from 43,152.250 s to 31,988.427 s, a reduction of 11,163.823 s (25.9 pct). The counter is 0
on the OFF arm and 0 on the uncapped tree, so it is not a constant.

---

## (b) MARGIN PROVENANCE: RECOVERABLE, and it is a derivation with data and method

Traced through `a6c6eb4f`. **Verdict: a derivation stated with data and method**, not an assertion
and not a bare literal. Build 1's attribution needed one correction.

| item | finding |
|---|---|
| derived and accepted at | `2cb2d5c1` (2026-11-21 17:13:05 -0800), "MARGIN_CF = 0.16456, SET once from the D169 population"; an ancestor of `a6c6eb4f` |
| **written into the code at** | **`478e6cc5`**, not `2cb2d5c1`: at `2cb2d5c1` `cf_margin.py` still read `MARGIN_CF: Optional[float] = None`, and `478e6cc5` says so itself ("It was computed, committed to JSON and marked IMPLEMENTED in the spec at 2cb2d5c1, but cf_margin.MARGIN_CF was still None") |
| ever changed since | NO commit changes the value |
| the statistic | nearest-rank p90 of `A_D2_DEV * abs(P_hat - 1[on time])`, `margin_cf_d169.py:92` and `:117`, `A_D2_DEV = 0.250` at `:22` |
| the population | 476 robot questions RELEASED in HEALTHY-regime windows (D162 window rule: observed first-token p50 of the question's own 100 s submit window <= 2.781 s) over 8 committed rq30 cells: `v5-rules-2` and `hybrid-F-lhreq-noc3`, n16, seeds 4 to 7, 1200 s, epg. Committed BEFORE scoring in `margin_cf_population_d169.json` |
| the model | `P_hat` = `cf-ontime-d162-1.0`, hash-frozen before scoring (payload `8fa0c7fe`, code `df6863b0`) |
| the result | `error_p90_overall` 0.16456 (warm 0.150341, cold 0.173231), `error_p50_overall` 0.01156, n_warm 271, n_cold 205, thresholds min_n 40 and min_n_warm 40, verdict SET |
| pre-registration | the UNITS were named at D157 (2) before the gate ran; the setting procedure and the n >= 40 minimum at D168; the population replacement at D169, with the order "freeze P_hat, commit the cell list, then compute" |
| the bar the planner applies | `attainment_margin(0.16456)` = 0.16456 / 0.250 = **0.65824**, confirmed by D255 as `MARGIN_CF_ON_TIME` |
| `A_D2_DEV = 0.250` | the LH-REQ DEV-split cloud-with-D2-history accuracy, **7 of 28**, Wilson CI [0.1268, 0.4336], from `lh_req_quality.json`; traceable and measured, on a very small n |

Two defects in the record, neither changing the arithmetic. (i) `cf_margin.py:62` calls `A_D2_DEV`
"the committed device-vs-cloud accuracy delta"; it is not a delta (the committed delta on that
split is 0.178571), it is the cloud's absolute DEV accuracy, and the rest of the code names it
correctly. (ii) `cf_margin.py`'s module docstring, `MARGIN_CF_RULE` and `UNIT_CONVERSION_GAP` still
read as if the constant were unset; `478e6cc5` kept them deliberately as the record of why the gap
was open, and they contradict lines 49-69 of the same file.

**The per-question error array is NOT committed** - only the p90/p50/n summary - so 0.16456 cannot
be recomputed from committed artefacts without re-running `margin_cf_d169.py` over the eight cell
directories.

### WHAT THE PROVENANCE SHOWS ABOUT THE BAR, which is the input to any recalibration

The statistic is the p90 of `|P_hat - 1[on time]|` against the **realised Bernoulli outcome of a
single question**. For ANY well-calibrated probability forecast, that distribution has mass near
`1 - p` and near `p`, so its upper decile is dominated by **outcome randomness, which no model can
predict away**, and not by the model's own error. The committed numbers show exactly that shape:
in on-time units the p50 absolute error is **0.04624** and the p90 is **0.65824**, a factor of
14.2. A bar of 0.65824 on-time answers is therefore mostly the irreducible variance of a coin whose
bias the model already predicts well, charged as if it were prediction uncertainty.

The quantity the bar is compared against is a DIFFERENCE of two predictions for the SAME session,
`p_question x (p_warm - p_cold)`, in which that Bernoulli term does not appear.

### THE PROPOSED RECALIBRATION. REPORT ONLY. NOT APPLIED, NOT COMPUTED.

**Keep D154 (2) intact** - the margin is the frozen cost model's held-out p90 absolute prediction
error, in the objective's units, set once, frozen, never swept - and keep the population, the
frozen `P_hat`, the healthy-window filter, the n >= 40 minima, the pre-commit order and the p90
quantile EXACTLY as D157 (2) / D168 / D169 fixed them. **Change only what the error is measured
against**, from the single realisation to the frequency the model's own prediction implies:

> **Method A (primary), the calibration-error p90.** Bin the 476 held-out questions by predicted
> `P_hat` (pre-registered bin edges, equal-count deciles, minimum 40 per bin or merge upward).
> Within each bin compute the realised on-time frequency. The per-bin error is
> `|mean(P_hat | bin) - freq(on time | bin)|`. `MARGIN_CF_ON_TIME` is the p90 of that error over
> questions (each question carrying its own bin's error), and `MARGIN_CF` is that times `A_D2_DEV`
> for continuity with the committed symbol. Report warm and cold separately as today, report the
> bin table, and require the same minima.
>
> **Method B (secondary, if the pairing is judged sound), the error of the DIFFERENCE.** The
> planner never reads a single `P_hat`; it reads `p_warm - p_cold`. Stratify the same population
> by warm and cold (n 271 / 205) within matched `P_hat` bins and take the p90 of
> `|(P_hat_warm - P_hat_cold) - (freq_warm - freq_cold)|`. This is the error on the quantity
> actually compared, which is what a deviation margin is for. It is secondary because the pairing
> is across questions rather than within one, and that approximation must be ruled on.

**Why this is NOT tuning to arm outcomes, which the ruling forbids absolutely.** The computation
reads only `(P_hat, realised on-time, warm flag)` triples for a FROZEN model on a population
committed before scoring, at a quantile fixed in advance. It does not read any arm's chosen
actions, any TOUCH or HOLD_BACK count, any policy metric, any arm-versus-arm comparison, or any
`covex-v6-fair-final-q` output; it would return the same number if D249 did not exist and if the
state planner had never been written. The change is justified by a units-and-semantics argument
about what the bar is supposed to measure - model uncertainty on the compared quantity - stated
before any value is computed, and NOT by what it does to any arm. **A method chosen because it
makes TOUCH fire would be forbidden, and so would be reading the observed `z` distribution of
section (c) and setting the margin beneath it: that distribution is an output of the arm under
test, so a margin taken from it is a margin tuned to arm outcomes by the back door.** It is named
here precisely so that it is excluded.

**The honest limitation, stated before the method is ruled on:** nobody, including this build,
knows what value Method A or Method B returns until it is run, and the ruling forbids running it.
Section (c) says what range of bars leaves TOUCH reachable on this cell; whether the recalibrated
value lands in that range is UNKNOWN and must not be guessed.

---

## (c) REACHABILITY, MEASURED STRUCTURALLY ON THE DECISION LOGS, WITH AND WITHOUT THE CAP

Same posted cell throughout (seed 4, n16, 1200 s, 40:40:20, lh_req, ss2, epg, per-frame, rq30, 1x,
`--cutoff-off`), ONE CELL PER PROCESS. The quantity is
`Z = p_question x (p_warm - p_cold) - harm_touch / w_d`, recovered per decision as
`TOUCH.value / w_d` with `w_d = margin_effective / 0.65824`, so it is read off the planner's own
candidate values and not recomputed from a model. 61,678 decisions, TOUCH scored at every one
(`no_touch_value` = 0).

| quantity | ON, WITHOUT the cap | ON, WITH the cap |
|---|---|---|
| **(1) Z distribution** p0 / p1 / p10 / p25 / p50 | -0.1511 / -0.00097 / 0.0000866 / 0.000620 / 0.005459 | -0.1511 / -0.00096 / 0.000146 / 0.000824 / 0.006822 |
| p75 / p90 / p99 / **max** | 0.05556 / 0.16754 / 0.38009 / **0.555588** | 0.05781 / 0.16754 / 0.38009 / **0.555588** |
| **(2) decisions where TOUCH COULD clear the bar** | **0 of 61,678** | **0 of 61,678** |
| **(3) TOUCH CHOSEN** | **0** | **0** |
| max `p_warm - p_cold` | 0.593995773 | **0.593995773** |
| applied queue delay, max | 15.705 s | 2.781 s |
| prices above the 2.781 s bound | 5,740 (9.31 pct) | 5,740 capped (9.31 pct) |
| the bar | 0.65824 x `w_d` | 0.65824 x `w_d` |

**THE CAP RAISES Z IN THE MIDDLE OF THE DISTRIBUTION AND NOT AT THE TOP.** Z's median rises 25 pct
(0.005459 to 0.006822) and its p25 rises 33 pct, while p90, p99 and the maximum do not move at all,
to nine decimal places. The reason is structural: the decision with the largest warm-cold gap is
one whose queue was ALREADY INSIDE the bound, so capping cannot widen it. The cap removes 25.9 pct
of the aggregate predicted delay and **changes no decision**: the ON log is byte-identical capped
and uncapped (11,386 rows, digest `b7bb6e018b6e1d27`, 0 positional and 0 setwise differences).

**So the bar at 0.65824 leaves TOUCH unreachable on this cell with the cap exactly as it did
without it, and the gap is not marginal: the most favourable decision in 61,678 reaches 0.5556,
which is 84.4 pct of the bar.** For the record, and as a statement about the logs rather than a
proposed value: a bar above 0.5556 is unreachable at every decision here; at 0.38009 it would be
clearable at 1 pct of decisions, at 0.16754 at 10 pct.

*** THIS IS THE D246 CONTRADICTION, AND IT IS A FINDING FOR THE USER, NOT SOMETHING TO ENGINEER
AROUND. *** D246 and D256 require touches to stay in the policy AND to remain reachable in
`covex-v6-fair-final-q`. Under the committed bar they are not reachable, the cap does not change
that, and no second code change was attempted. Whether an outcome-free recalibration can leave
them reachable cannot be answered without computing the (b) statistic, which (b) forbids. The
decision is the user's.

---

## (d) THE LIGHT PROOFS, RE-RUN WITH (a) ONLY

| leg | arm | tree | rows | digest (wide strip) |
|---|---|---|---|---|
| A | `covex-v6-fair-final` (OFF) | after_cap | **14,539** | **`5a03c2807da3681a`** |
| B | `llf` (positive control) | after_cap | **14,075** | **`961be8fe4942d86b`** |
| C | `covex-v6-fair-final-q` (ON) | after_cap | 11,386 | `b7bb6e018b6e1d27` |
| D | `covex-v6-fair-final-q` (ON) under the reach probe | after_cap | 11,386 | `b7bb6e018b6e1d27` |
| E | `covex-v6-fair-final-q` (ON) under the reach probe | after (uncapped) | 11,386 | `b7bb6e018b6e1d27` |

- **PROOF 1, the OFF-switch identity: PASS, on the committed bar.** `covex-v6-fair-final` on the
  BEFORE tree against the CAPPED tree: 14,539 rows both sides, wide digest `5a03c2807da3681a` both
  sides, positional 0, setwise 0, IDENTICAL true. The cap is unreachable with the switch off.
- **PROOF 4, the positive control, twice.** `llf` BEFORE against CAPPED: 14,075 rows,
  `961be8fe4942d86b`, positional 0, setwise 0. And `llf` against rung 3 on the SAME capped tree:
  14,075 against 14,539 rows, digests differ, positional 14,539, setwise 12,362, **first differing
  row index 0**. So IDENTICAL is not vacuous.
- **PROOF 5, the instrument control (new in this build).** The ON arm run plain and the ON arm run
  under the reachability probe are byte-identical (0 positional, 0 setwise, same digest), so the
  probe does not perturb the cell it measures.

**Decisions changed vs rung 3, with the cap (Step 2b):** **positional 12,344, setwise 3,977** -
the same counts build 1 recorded without the cap.
**First differing decision**, setwise register: the key `(233.3, "release_piece", [], None, None)`,
present only in the OFF log - at t = 233.3 s the OFF arm releases a build piece the ON arm does
not. Positionally the first differing row is index **2,195**: OFF `release_piece` at t = 233.3 s
(`session=robo005|s001|...`) against ON `release_recall` (`opp0002253`,
`session=robo000|s000|...`), differing in `kind`, `note`, `opportunity_ids`, `piece_tokens`,
`representation`, `representation_defaulted` and `t`.
Differing fields over the whole log: `opportunity_ids` 9,167, `t` 9,151, `traffic_mix` 7,654,
`kind` 4,053, `note` 2,587, `desired_tier` 1,911, `representation` 633,
`representation_defaulted` 633, `piece_tokens` 159, `defer_s` 2.

**CHOSEN-ACTION COUNTS, before and after.**

| counter | OFF rung 3 | ON uncapped | **ON capped** |
|---|---|---|---|
| `state_decisions` | 60,920 | 61,678 | 61,678 |
| `state_chosen_KEEP` | 57,960 | 61,610 | **61,610** |
| `state_chosen_TOUCH` / `state_touch_emitted` | 2,954 / 2,954 | 0 / 0 | **0 / 0** |
| `state_chosen_HOLD_BACK` / enacted | 0 / 0 | 68 / 68 | **68 / 68** |
| `state_chosen_WARM` | 6 | 0 | **0** |
| `state_deviations` | 2,960 | 68 | **68** |
| `gain_TOUCH_over_margin` | 2,960 | 0 | **0** |
| `gain_TOUCH_max_milli` | 1,873 | 1,165 | 1,165 |
| `gain_HOLD_BACK_over_margin` | 0 | 68 | 68 |
| `harm_warm_priced` / `nonzero` / `max_milli` | 2,314 / 1,607 / 998 | 59,314 / 24,336 / 5,442 | 59,314 / 24,336 / 5,442 |
| `harm_warm_capped` | 1 | 105 | 105 |
| **`d249_pwc_queue_capped`** | **0** | **0** | **5,740** |
| `d249_pwc_queue_max_milli` | 0 | 15,705 | **2,781** |
| `d249_pwc_queue_milli_sum` | 0 | 43,152,250 | **31,988,427** |
| `submitted_piece` | 163 | 94 | 94 |
| `state_skipped_unpriced`, `timeout_fallback`, abandons | 0 | 0 | 0 |

No other chosen action occurs: RELOAD and SLICE are never chosen in any of the three (RELOAD is
offered only at host-warm, which no cell has reached - UNEXERCISED, per build 1).

**THE LARGEST `p_warm - p_cold` UNDER THE CAP: 0.593995773**, against the bar of 0.65824. It is
unchanged from the uncapped run to nine decimal places, which is the whole of the (c) finding.

**HAZARD RE-CHECKS.** The 247.5x unit guard: the static scan over `arms_v6state.py` re-ran on the
capped tree and found **4 of 4** `CC.predict(` call sites still carrying literal `0, 0` in
`overlap_ft` and `overlap_decode`; the queue is still added in SECONDS. The unit suite is **20 of
20 PASS, 0 FAIL** on the capped tree, including "at zero queued-ahead tokens the pair is EXACTLY
the committed rung-3 pair" (warm 0.9918012103166088, cold 0.9774000781058854 both sides). Numbers
re-read at the point of use: `per_queue_token` = 0.0001535807289338535 seconds **per TOKEN**;
`per_overlap` = 0.038004811772727576 seconds **per REQUEST**; the cap bound 2.781 is **seconds of
first token**, and `d249_pwc_queue_max_milli` is **milliseconds**, which is why 2,781 and 2.781 are
the same quantity. **KV capacity is NOT enforced in this harness** (`kv_capacity_enforced` False in
`test_hybrid.dry`), so NO kv0.5r claim is made.

---

## WHAT TO DISTRUST, AND TWO THINGS THIS BUILD CAUGHT

1. **Build 1's `cell_r3q_after.json.gz` is its SUPERSEDED pre-slack-alignment ON cell** and its
   `d249_queued_ahead_reads` is exactly doubled (122,506 against 61,678) with
   `harm_warm_nonzero` 21,955 against 24,336. `cell_r3q2_after.json.gz` is the aligned run and
   matches this build's uncapped run exactly on every counter. Anyone comparing against build 1
   must use `cell_r3q2_after`. The decision log and digest are the same in both, so this is an
   instrumentation difference and not a decision difference - which is also why it would have
   survived a digest check.
2. **`reach_uncap.json` carries a mislabelled column.** `queue_delay_s_as_applied` is computed by
   the probe as `min(delay, 2.781)` regardless of the tree, so in the UNCAPPED file that column is
   NOT what the tree applied. The authoritative uncapped applied maximum is the arm's own counter,
   `d249_pwc_queue_max_milli` = 15,705 ms. The percentiles of the uncapped arithmetic are in
   `queue_delay_s_uncapped_arith`, which is correct in both files.
3. **Every number here is a DRY cell** (`realtime=False`, simulated clock, no engine). NO LIVE GATE
   CELL WAS RUN, per the ruling. The d188 precedent warns a dry replay bounds nothing about live.
4. **No E-id exists** for D249 or D256: `research/EXPERIMENTS.md` at `a6c6eb4f` has no row for
   either, and no `results/INDEX.md` row for the margin artefacts. Required before any of this is
   cited.
5. **No score, no quality or on-time metric, no per-device dashcam reading** is reported, and none
   may be taken from a dry cell.

## FILES (session scratchpad; nothing in the repository)

```
.../scratchpad/d249/after_cap/                               build 1's after tree plus (a)
.../scratchpad/d249/out/d256_cap.diff                        the cap, as a diff
.../scratchpad/d249/out/reach_cap.json                       (c) with the cap
.../scratchpad/d249/out/reach_uncap.json                     (c) without the cap
.../scratchpad/d249/out/unit_proofs_cap.json                 20 checks, 20 PASS
.../scratchpad/d249/out/d256_p1_offidentity.json             PROOF 1
.../scratchpad/d249/out/d256_p4_llf_identity.json            PROOF 4a
.../scratchpad/d249/out/d256_p4_llf_vs_r3.json               PROOF 4b
.../scratchpad/d249/out/d256_p2_step2b.json                  Step 2b with the cap
.../scratchpad/d249/out/d256_p5_probe_is_transparent.json    instrument control
.../scratchpad/d249/out/d256_p6_cap_effect.json              cap effect on the log: none
.../scratchpad/d249/out/cell_{r3_cap,llf_cap,r3q_cap_plain,r3q_cap_probe,r3q_uncap_probe}.json.gz
.../scratchpad/d249/drv/{reach_probe.py,chain_d256.sh,chain_d256_diffs.sh}
```
