# Study O — Q4: does coverage-based escalation convert to end-to-end accuracy?

**Date:** 2026-10-15
**Plan:** `reports/study_o_plan.md` §7 (D1–D4 fixed 2026-10-14)
**Scripts:** `experiments/sember/study_o_q4.py` (inference), `study_o_q4_analyze.py` (analysis), `study_o_precheck.py` (§8 + D4)
**Trials:** `results/sember/study_o/study_o_q4_trials.jsonl` — **1,560** (3 cells × 520)
**Compute:** 4.83 h GPU inference, A6000 (flash, cuda:1). Within the 8 h cap; no sample reduction needed.

---

## Scope — Q4 only

Study O's full 9-cell factorial **halted** on 2026-10-14 at the §8 Q1 cell-balance check
(`reports/study_o_results.md`). Q4 was authorised separately because it does not depend on that
check and its own power check passed. **Only the 3 cells Q4 needs were run**, not the 9-cell
factorial. Q1, Q2 and Q3 are not addressed here.

Rationale recorded at authorisation: Q1 tests the evidence × capability interaction, which the
H100 StudyR run is closing independently — 32B-Thinking vs 32B-Instruct shows b=6, c=6 at n=53,
the same net-zero reshuffling measured at 4B (ERQA 59/49) and 8B (MV-RoboBench 71/67). If
capability heterogeneity does not exist at any runnable scale, Q1 has nothing to find. Q4 asks a
different question and is the live thread for the paper.

---

## VERDICT

> **Coverage-based escalation does NOT convert into end-to-end accuracy gain.**
>
> Primary test, remote = 8B-I × RICH, e = 0.2:
> **acc(d) − acc(c) = +0.50 pp, 95% CI [−1.18, +2.27]** (clustered bootstrap, 2,000 resamples,
> 150 video clusters). **CI includes 0.** gap_closed_accuracy = **4.4%**.
>
> ## **K4 FIRES** — reason (i): local and remote accuracy are too similar (33.85% vs 33.27%), so model routing does not matter.
>
> The Study N2 runtime-signal claim **stays at the coverage level only**.

---

## 1. Cells and defect fixes

All four defects were found **unfixed** on 2026-10-14 and fixed before launch
(`reports/study_o_results.md` §1). Fixes as applied in this run:

| defect | applied here |
|---|---|
| **D1** | 4B-T resolves to `Qwen/Qwen3-VL-4B-Thinking` snapshot `1de27d8c`, **distinct** from 4B-I `ebb281ec` and 8B-I `0c351dd0`. All three verified present. |
| **D2** | 4B-T: `temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True` (CFG-A). 4B-I / 8B-I: greedy. |
| **D3** | 4B-T `max_new_tokens=8192`; `think_closed` and `budget_hit` recorded per trial. |
| **D4** | `evidence_covered` computed per trial from the **timestamps actually sampled**. |

**D2 disclosed deviation:** the Qwen3-VL-Thinking model card recommends `temperature=1.0` for
vision-language tasks; CFG-A uses 0.6, on cross-study-consistency grounds with StudyK/P/Q/S1.
StudyS0 Audit 2 found the two indistinguishable on ERQA (41.0% vs 40.0%, CIs spanning ~19 pp).

| cell | role | n | accuracy | 95% CI | **D4 coverage** | frames (med) | input tok (med) | latency (med) |
|---|---|---|---|---|---|---|---|---|
| 4B-I × RECENT | local | 520 | **33.85%** | [29.9, 38.0] | **90.4%** | 121 | 12,439 | 2.4 s |
| 8B-I × RICH | remote (Instruct) | 520 | **33.27%** | [29.4, 37.4] | **100.0%** | 240 | 12,599 | 3.5 s |
| 4B-T × RICH | remote (Thinking) | 520 | **30.00%** | [26.2, 34.1] | **100.0%** | 240 | 12,601 | 13.2 s |

All three CIs overlap heavily. Chance on this 5-option MCQ is 20%.

### D4 — coverage rates per arm, from sampled timestamps

| arm | old (defective) coding | **measured from sampled timestamps** |
|---|---|---|
| RECENT | 68.8% | **90.4%** |
| RICH | 100.0% | **100.0%** |
| (UNIFORM — not run in Q4) | 100.0% | 85.4% |

The measured RECENT rate (90.4%) matches the pre-check estimate exactly. RICH measures 100%
rather than the pre-check's 99.6% because of the frame-selection deviation below — at 1 fps the
dense arm effectively never misses the evidence window.

The UNIFORM row is carried from `study_o_precheck.py` for completeness; UNIFORM is not one of
Q4's three cells and was not run. Its −14.6 pp correction is the finding that matters for **Q1**,
not for Q4.

### Stated deviation — RICH frame selection

The plan specifies RICH as "256 frames over [0, question_time]". As implemented, RICH is
**1 fps over [0, qt], capped at 256 by even subsampling** — identical to StudyI3's validated
TEMPORAL arm. Consequence: **56% of RICH trials carry fewer than 256 frames** (median 240
overall; median 146 for the qt < 256 s half).

Reason: sub-second sampling for short prefixes would require a finer decode than the 1 fps frame
cache and would diverge from prior S-EMBER work. This does not affect D4, which is computed from
whatever timestamps were actually sampled. Token economics confirm the configuration matches
StudyI3: **55 tok/frame**, inside its committed 44–56 range.

**Implementation note.** A first version passed frames as individual images rather than as a
video, bypassing the processor's per-frame pixel cap: **80,229 input tokens/question at 663
tok/frame, 36 s latency**. Caught by cross-checking against StudyI3's committed ~11,264-token
figure before the real run. Corrected to the video path with `VideoMetadata` and
`max_pixels=1280*28*28`: **12,451 tokens, 2.4 s**. The 10 affected trials were discarded.

---

## 2. Primary result — remote = 8B-I × RICH

**Paired n = 520.** Local 33.85%, remote 33.27% — **remote is 0.58 pp worse than local.**

Discordance is nonetheless substantial: remote rescues **b = 58** (11.2%), remote breaks
**c = 61** (11.7%), net **−0.58 pp**. 23% of questions get a different answer from the two arms.

**Predictor.** N2's P4 (all-MiniLM-L6-v2 + log(1+qt)) retrained on **8,928** S-EMBER rows with all
520 Study O questions on 150 videos **excluded**; no-leakage asserted in code. Base rate
P(needs_escalation) = 0.296. P(farthest > 120 s) in Study O = **31.2%** (H2 expectation ~29.7%).

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 33.85% | 33.27% | 33.79% | 35.00% | 34.42% | 43.85% | +1.21 pp | 12.0% |
| **0.2** | 33.85% | 33.27% | 33.73% | **34.23%** | 35.58% | 45.00% | **+0.50 pp** | **4.4%** |
| 0.3 | 33.85% | 33.27% | 33.67% | 33.65% | 35.77% | 45.00% | −0.02 pp | −0.2% |

**Pre-registered primary test (e = 0.2):**

```
acc(d) − acc(c) = +0.50 pp
95% CI [−1.18, +2.27] pp   (paired bootstrap, 2,000 resamples, clustered by video_id, 150 clusters)
CI excludes 0: NO
gap_closed_accuracy = 4.4%   (oracle headroom acc_f − acc_c = +11.27 pp)
```

**K4 FIRES** — the rule is (d)−(c) < 1 pp **and** CI includes 0; both hold. Reason **(i)**: local
and remote accuracy are too similar (33.85% vs 33.27%), so model routing does not matter.

---

## 3. Second remote configuration — 4B-T × RICH (plan §7 requires both)

**Paired n = 520.** Local 33.85%, remote **30.00%** — the thinking arm is **3.85 pp worse**.
Discordance: b = 58 (11.2%), c = 78 (15.0%), net **−3.85 pp**.

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 33.85% | 30.00% | 33.46% | 35.77% | 33.85% | 43.85% | +2.31 pp | 22.2% |
| **0.2** | 33.85% | 30.00% | 33.08% | **34.62%** | 33.65% | 45.00% | **+1.54 pp** | 12.9% |
| 0.3 | 33.85% | 30.00% | 32.69% | 33.85% | 33.85% | 45.00% | +1.15 pp | 9.4% |

```
acc(d) − acc(c) = +1.54 pp
95% CI [−0.32, +3.59] pp
CI excludes 0: NO
```

**K4 does not fire here — and that must not be read as a positive result.** K4 is a *conjunction*:
(d)−(c) < 1 pp **AND** CI includes 0. Here the first clause fails (1.54 pp > 1 pp) while the
second holds, so the kill condition is not triggered, **but the result is still null** — the
confidence interval includes zero.

There is also a mechanical reason the apparent gain is larger here: the random baseline (c) is
*dragged down* by mixing in a worse remote arm (30.00%), so beating it is easier. A larger d − c
against a weaker baseline is not evidence that escalation helps. Policy (a) never-escalate
(33.85%) beats policy (b) always-escalate (30.00%) by 3.85 pp.

---

## 4. The deeper finding: coverage has a low ceiling here, independent of predictor quality

The pre-registered test asks whether *this predictor* converts. The policy ladder answers a
stronger question: **could any coverage-based predictor convert?**

Policy (e) is the **evidence-distance oracle** — it ranks by the *true* farthest-evidence
distance, i.e. perfect knowledge of the very quantity N2's predictor estimates.

| remote config | (e) evidence oracle gain at e=0.2 | (f) accuracy oracle headroom | predictor (d) |
|---|---|---|---|
| 8B-I × RICH | **+1.85 pp** | +11.27 pp | +0.50 pp |
| 4B-T × RICH | **+0.57 pp** | +11.92 pp | +1.54 pp |

Real exploitable headroom exists — the accuracy oracle reaches ~45% against ~33% random, about
**+11–12 pp**. But a *perfect coverage signal* captures only **+0.57 to +1.85 pp** of it.

So coverage-based escalation on this workload is not limited by predictor quality. It is limited
because **coverage and "which arm answers correctly" are close to orthogonal**. Even a flawless
estimate of evidence distance would leave roughly 85–95% of the available headroom on the table.
Improving the predictor cannot fix this; the signal is close to the wrong one for the decision.

This is the result that bears on the paper. N2's SIGNAL verdict (OOF AUROC 0.766, 44.9% of the
**coverage** gap closed) is not contradicted — it is confined. The ranking is real at the coverage
level and does not transfer to accuracy.

---

## 5. Sanity checks

- **4B-T generation:** `think_closed` **516/520** (99.2%); `budget_hit` **4/520** (0.8%) at the
  8192 budget. Think tokens: median **188**, IQR [101, 406], max 4,922 — far below the cap, so
  D3's budget was not binding on this workload.
- **Parse failures reported separately, not silently scored wrong:** 4B-I **0**, 8B-I **0**,
  4B-T **4**. The 4 thinking-arm failures coincide with the 4 budget hits (truncated before an
  answer letter). Scoring all 4 as correct would move 4B-T from 30.00% to 30.77% — the verdict is
  unchanged.
- **No-leakage assertion:** P4's training set is asserted disjoint from the 150 Study O video_ids
  in code; the assertion passed on both runs.
- **Bootstrap clustering:** resampling is over the **150 videos**, not the 520 questions, so
  intra-video correlation is respected.
- **Chance baseline:** 20% (5-option MCQ). All three arms are well above chance, so this is a
  real-mechanism null, not a degenerate one — contrast StudyS1's 137-block, where both arms sat at
  chance and the comparison was uninterpretable.

---

## 6. Cost

| cell | median latency | relative |
|---|---|---|
| 4B-I × RECENT (local) | 2.4 s | 1× |
| 8B-I × RICH (remote) | 3.5 s | 1.5× |
| 4B-T × RICH (remote) | 13.2 s | **5.5×** |

Total 4.83 h of GPU inference for 1,560 trials. The thinking arm costs 5.5× the local arm and
returns **−3.85 pp**.

**ATTENTION-BACKEND DISCLOSURE (added 2026-10-15, after the run).** `study_o_q4.py` passes no
`attn_implementation`, so all three cells ran on the transformers default, **SDPA**, verified on
this box: `transformers 5.12.1`, `flash_attn 2.6.3` installed but not requested, and a no-arg load
of the 4B-I snapshot reports `_attn_implementation = sdpa` for both the text and vision towers.
The committed S-EMBER latency work used a different backend — `study_i2_budget.py:457` and
`study_i3_budget.py:557` pass `attn_implementation="flash_attention_2"` explicitly, and
`study_g_transfer_cost.py:251` / `study_g2_transfer_cost.py:219` assert it. Consequences:

- The three latencies above are **internally comparable** (one script, one backend, one GPU), so
  the 1× / 1.5× / 5.5× ratios and the cost-vs-accuracy conclusion stand as written.
- The **absolute** figures are SDPA numbers and must NOT be read against the committed flash-attn-2
  S-EMBER curves. This is the CLAUDE.md consistency-check-4 failure mode — one named quantity
  ("median latency", same model, same host) measured under two configurations — so the backend is
  recorded here rather than reconciled by picking one value.
- The **accuracy** results, and therefore the K4 verdict, are unaffected: the backend changes
  attention kernel numerics, not which option letter is selected, and all three cells share it.
- The token-budget cross-check in §4 is also unaffected — it compares input tokens per frame
  against StudyI3's committed ~11,264, and tokenisation is upstream of attention.

Not retrofitted: no timing-only rerun was performed, per the standing cross-hardware instruction.
A backend-matched rerun would be needed before any absolute Q4 latency enters `cost_matrix.csv`.

---

## 7. What this settles

**Settles:** on S-EMBER, routing between a local small-context arm and a remote large-context arm
produces no net accuracy gain, and a coverage-based escalation predictor does not convert to
end-to-end accuracy. K4 fires on the primary configuration. Per the plan, the Study N2
runtime-signal claim stays at the coverage level only.

**Does not settle:** Q1, Q2, Q3 — not run. The 9-cell factorial remains halted on the §8
cell-balance failure, which needs ~400 GB of absent video to repair (150 of 3,141 videos are
local). Nothing here speaks to the evidence × capability interaction.

**Caveat on scope:** this is one workload, one local/remote pair, and a post-hoc-authorised subset
of a larger design. The orthogonality finding in §4 is the generalisable part; the specific
accuracy numbers are not.
