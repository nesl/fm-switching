# A6000 night queue — summary

**Date:** 2026-10-14 → 2026-10-15 · **Host:** flash, GPU 1 only (GPU 0 and the H100 box untouched)
**GPU inference used:** 4.83 h (all of it StudyO Q4).

---

## Outcomes

| task | cap | outcome | GPU used |
|---|---|---|---|
| 0 — sync StudyS1 off flash | 15 min | **Done in ~4 min.** Nothing to copy; all artifacts already at the registry-named paths, untracked. | — |
| 1 — StudyO (9-cell) | 8 h | **HALTED at the §8 gate.** All four defects found unfixed and fixed. D4 recomputation inverts the arm ordering. | none |
| 1b — StudyO **Q4 only** (authorised after the halt) | 8 h | **COMPLETE. K4 FIRES** — coverage-based escalation does not convert to accuracy. 1,560 trials. | **4.83 h** |
| 2 — StudyJ6 | 5 h | **DROPPED.** Inputs exist only on the unreachable H100 box. | none |

The §8 halt and the J6 drop were both conditions you instructed me to halt on. After the halt you
authorised the Q4-only subset, which ran to completion inside its cap.

---

## Task 1b — StudyO Q4 (the night's substantive result)

Full report: `reports/study_o_q4_results.md`.

**Verdict: K4 FIRES.** Primary test, remote = 8B-I × RICH, e = 0.2:

```
acc(predictor top-e) − acc(random at rate e) = +0.50 pp
95% CI [−1.18, +2.27]   (paired bootstrap, 2,000 resamples, clustered by video, 150 clusters)
CI includes 0 · gap_closed_accuracy = 4.4%
```

Reason (i): local (33.85%) and remote (33.27%) are too similar — **remote is marginally worse**,
so model routing does not matter. The N2 runtime-signal claim stays at the coverage level only.

| cell | n | accuracy | D4 coverage | latency |
|---|---|---|---|---|
| 4B-I × RECENT (local) | 520 | 33.85% | 90.4% | 2.4 s |
| 8B-I × RICH (remote) | 520 | 33.27% | 100% | 3.5 s |
| 4B-T × RICH (remote) | 520 | 30.00% | 100% | 13.2 s |

**The finding that matters for the paper is not K4 itself.** The policy ladder shows the
*evidence-distance oracle* — perfect knowledge of the quantity N2's predictor estimates — gains
only **+1.85 pp** (8B-I) and **+0.57 pp** (4B-T), against an accuracy-oracle headroom of
**+11.27 / +11.92 pp**. Real exploitable headroom exists; a *perfect* coverage signal reaches
5–16% of it. So coverage-based escalation fails here because the signal is near-orthogonal to
which-arm-is-right, **not** because the predictor is weak. Improving the predictor cannot fix it.
N2's SIGNAL verdict is **confined, not contradicted**.

On the second remote configuration, K4 does *not* fire — but only because the rule is a
conjunction and (d)−(c) = 1.54 pp exceeds the 1 pp clause. The CI still includes 0, so the result
is null, and the larger apparent gain is partly mechanical: a worse remote drags the random
baseline down, making it easier to beat.

**An implementation defect worth recording.** My first version passed frames as individual images,
bypassing the processor's pixel cap: **80,229 input tokens/question, 36 s latency**. Caught before
the real run by cross-checking StudyI3's committed ~11,264-token figure. Corrected to the video
path: **12,451 tokens, 2.4 s** — a ~15× error that would have blown the cap and produced numbers
incomparable to prior S-EMBER work.

**Stated deviation:** RICH is implemented as 1 fps over [0, qt] capped at 256 (= StudyI3's
validated TEMPORAL arm), not the plan's literal "256 frames", so 56% of RICH trials carry fewer
than 256 frames. D4 is unaffected — coverage is computed from the timestamps actually sampled.

---

## Task 0 — StudyS1 sync

**No copying was required.** The premise that StudyS1 "exists only on this machine and is NOT in
the repo" is half right: the files are at exactly the paths the registry names, but **untracked**
— present in the working tree, absent from git history. "Not in the repo" meant uncommitted.

| path | size |
|---|---|
| `experiments/erqa/study_s1_mvrobobench.py` | 12 K |
| `experiments/erqa/study_s1_analyze.py` | 8 K |
| `experiments/erqa/study_s1_fetch_images.py` | 4 K |
| `results/mvrobobench/study_s1/study_s1_trials.jsonl` | 1.8 M |
| `reports/study_s1_competent_categories.md` | 12 K |

Integrity verified against the report: 2,169 trials (arm I 1,708, arm T 461), stratum n = 401,
b = 71, c = 67, **net_rescue +1.00 pp** — matching exactly.

**They need committing, which I cannot do.** Until then the H100 box has nothing to pull, and it
will keep re-deriving StudyS1. Paths are listed at the end of this file.

---

## Task 1 — StudyO: halted at §8, but the defect work is the real output

### All four defects were unfixed

| defect | found | fixed |
|---|---|---|
| D1 (critical) | 4B-T still listed as `Qwen/Qwen3-VL-4B-Instruct` "(thinking mode)" | → `Qwen/Qwen3-VL-4B-Thinking`, snapshots resolved |
| D2 | no decoding specified anywhere | → CFG-A, vendor deviation disclosed |
| D3 | no `max_new_tokens` for the thinking arm | → 8192, `think_closed`/`budget_hit` per trial |
| D4 | line 69 verbatim as flagged | → redefined and recomputed |

Resolved snapshots, all present and **distinct**: 4B-I `ebb281ec`, 8B-I `0c351dd0`,
4B-T `1de27d8c`. Left unfixed, D1 would have run the 4B-I checkpoint twice and reported one of
the runs as a thinking arm.

### D4 is the substantive finding — it inverts the arm ordering

`evidence_covered`, recomputed from each arm's **actual sampled frame timestamps** over the 520
locally-available questions:

| arm | OLD (defective) | NEW (sampled) | delta |
|---|---|---|---|
| RECENT | 68.8% | **90.4%** | **+21.5 pp** |
| UNIFORM | 100.0% | **85.4%** | **−14.6 pp** |
| RICH | 100.0% | **99.6%** | −0.4 pp |

Under the **old** coding RECENT was the only arm with any uncovered questions, so
`evidence_covered` was close to a relabelling of "is this the RECENT arm" — Q1's interaction would
largely have re-estimated the state-arm main effect under another name. Under the **corrected**
coding **UNIFORM is the worst-covered arm (85.4%), below RECENT (90.4%)**.

Mechanism: UNIFORM's inter-frame gap is 15.9 s median (up to 77 s) against an evidence window of
29 s median (10 s at p25), and **31.5% of questions have an evidence window narrower than their
own sampling gap**. RECENT beats the old estimate because it samples at 1 fps and the evidence
*window* often reaches into [qt−120, qt] even when its farthest point does not — the old rule
tested only the farthest point.

This confirms the predicted direction (RICH high, UNIFORM materially lower) and adds one that was
not predicted: RECENT outranks UNIFORM. Q1's primary test rests on this variable, so the
correction would have changed the study's headline result independently of the halt.

### Halt cause

| check | result |
|---|---|
| §8.1 Q4 power | **PASS** — 31.2% with farthest > 120 s (expected ~29.7%) |
| §8.2 Q1 cell balance | **FAIL** — 12 of 24 cells below 20 questions |

**Not repairable by resampling.** Only **150 of 3,141** referenced videos are on this machine
(19 GB), restricting StudyO to **520 of 9,448** questions. Full balance needs ~480 *evenly
spread*; the 520 available are uneven, so the check fails even using the entire local pool.
The root cause is data availability — roughly 400 GB of absent video — not sample size.

### One decision for you

The §8 halt is triggered by the **Q1** mixed-effects requirement. **Q4 — the one that matters for
the paper — does not depend on cell balance, and its own check passed.** A Q4-only run on the 520
local questions needs just 3 of the 9 cells (`4B-I × RECENT`, `8B-I × RICH`, `4B-T × RICH`), so
about a third of the compute.

I did **not** run it. You said halt if either check fails, and the plan says the same;
authorising a reduced variant is yours to decide.

---

## Task 2 — StudyJ6: DROPPED (H100 unreachable)

**Confirmed independently before the correction arrived:** the A6000 box has no path to the H100
box. No ssh config, no network mounts, no scp/rsync/ssh precedent in any script, no StudyT row,
and `known_hosts` is hashed so hosts cannot even be enumerated. Registry row set to **BLOCKED**,
recorded as a **scheduling gap, not a dead end** — re-cloning Sign-Understanding is a one-command
fix on any machine with network access. Ground truth was **not** reconstructed by hand.

Detail below from the earlier investigation.

---

## Task 2 (detail) — why J6's inputs are unrecoverable here

The script depends on `/tmp/sign-understanding`, cleared since 2026-10-03. **All five referenced
paths are gone.** Three blockers, each independently fatal:

1. **`prompt.txt` — the ORIGINAL prompt — is irrecoverable.** J6 is a *paired* ORIGINAL-vs-
   SIMPLIFIED test; one arm cannot be run against a reconstruction of the other. Writing a
   replacement prompt would invent the experimental condition under test. Note the asymmetry:
   **SIMPLIFIED is embedded verbatim in the script** (lines 307–333) and is recoverable; ORIGINAL
   is read from the missing file.
2. **`symbols.txt` is gone**, and `sym_str` = the first ten lines *in that file's order* feeds
   **both** arms. HF `test.json` has the symbol keys but not the ordering.
3. **The Gemini-2.0-Flash baseline is gone**, so the scorer-validation pre-condition cannot be
   *attempted* — not failed, attempted. J5 already failed once on a scoring-pipeline defect, which
   is the reason J6 exists; scoring with an unvalidated scorer would repeat that class of error.

Searched `/tmp`, all of `/home/pragya` to depth 5, the working tree, and git history across all
refs. `data/signs/dataset.zip` is **0 bytes**.

**Recoverable:** ground truth from HF `NickyZimmerman/SiGNgapore2D` `test.json` (167 records, same
structure as `gt_annotation.json` — verified by download), and the images (already HF-cached).

**Still needed from elsewhere:** `prompt.txt`, `symbols.txt`, the Gemini results JSON, the
exclusion list. They belong to a separate `sign-understanding` project tree and may survive on
another machine — the H100 box is the obvious place to look.

**Recommendation:** on recovery, copy them into this repo under `data/signs/` rather than `/tmp`.
This is the second run lost to a `/tmp` dependency.

12 of the planned 140 trials exist from 2026-10-03 and were left untouched. Their schema does
include `answer_text`, so the J5 defect was genuinely fixed — but 12 trials predate any scorer
validation and are too few to analyse.

**Verdict in the pre-registered form:** neither FIX nor TRADE. The experiment did not run.

---

## Cross-hardware note

No timing-only reruns were performed here, as instructed. A6000 latencies already exist in StudyQ
(ERQA) and StudyP (signs) for 4B-I, 4B-T, 8B-I and 8B-T.

For the eventual cross-hardware comparison: the H100 run's arm-A rerun yields **one measured
ratio, for 4B-Instruct only**. Applying that ratio to 4B-Thinking, 8B-Instruct or 8B-Thinking is a
**projection, not a measurement**, and must be labelled as such — decode is bandwidth-bound and
the A6000:H100 ratio is not constant across model sizes. StudyS1 is a concrete caution: arm T ran
226× slower than arm I on identical hardware and inputs, so per-arm cost does not scale by a
single hardware factor.

**Attention backend — a second axis, added 2026-10-15.** The incoming `research/HOST_H100.md`
notes the H100 venv lacks `flash_attn` and falls back to SDPA. Checking this box rather than
assuming the contrast: `flash_attn 2.6.3` IS installed here, but **none of tonight's three
scripts requested it** — `study_o_q4.py`, `study_s1_mvrobobench.py` and `study_s0_audit2.py` all
pass no `attn_implementation`, and the `transformers 5.12.1` default resolves to `sdpa` for both
the text and vision towers (verified by a no-arg load of the 4B-I snapshot).

So the backend split is NOT A6000-vs-H100; it runs through this repository:

| family | backend | evidence |
|---|---|---|
| `experiments/vision/`, `experiments/sember/` cost studies | `flash_attention_2`, explicit | `study_g_transfer_cost.py:251` and `study_g2_transfer_cost.py:219` assert it; `study_i2_budget.py:457`, `study_i3_budget.py:557` set it |
| all of `experiments/erqa/` | SDPA (default) | no `attn_implementation` anywhere in the directory |
| tonight's three scripts | SDPA (default) | no `attn_implementation`; default verified as `sdpa` |

Consequences, stated rather than repaired (no timing-only rerun, per instruction):

- **Accuracy results and every verdict are unaffected** — the backend changes attention numerics,
  not which option letter is chosen, and within each study all arms share it.
- **Within-study latency ratios hold** (Q4's 1.5×/5.5×, S1's 226×) — one script, one backend.
- **StudyS1 vs StudyQ is backend-matched**, since the whole `erqa/` family is SDPA.
- **StudyO Q4 is the one genuine mismatch:** it sits in `sember/`, whose cost studies use
  flash-attn-2, so its absolute latencies must not be read against StudyI2/I3 curves or enter
  `cost_matrix.csv` without a backend-matched rerun. Recorded in `reports/study_o_q4_results.md` §6.

This is a CLAUDE.md consistency-check-4 miss on my part — one named quantity, two configurations,
no reconciliation — caught on 2026-10-15 in response to a direct question, not by the checklist.

---

## Files changed tonight

**New:**
```
experiments/sember/study_o_precheck.py
experiments/sember/study_o_q4.py
experiments/sember/study_o_q4_analyze.py
results/sember/study_o/study_o_q4_trials.jsonl
reports/study_o_results.md
reports/study_o_q4_results.md
reports/study_j6_simplified_accuracy.md
reports/a6000_night_summary.md
```

**Modified:**
```
reports/study_o_plan.md          (D1–D4 fixed in place, each marked)
research/EXPERIMENTS.md          (StudyO and StudyJ6 rows updated)
results/INDEX.md                 (StudyO Q4 rows appended)
```

**Untouched:** `results/signs/study_j6/study_j6_trials.jsonl` (the 12 pre-existing trials).

---

## Still uncommitted from the previous session — this is why the H100 is duplicating work

```
experiments/erqa/study_s0_audit3b_auroc_power.py
experiments/erqa/study_s1_fetch_images.py
experiments/erqa/study_s1_mvrobobench.py
experiments/erqa/study_s1_analyze.py
results/erqa/study_s0/audit3b_auroc_power.json
results/mvrobobench/study_s1/study_s1_trials.jsonl
reports/study_s1_competent_categories.md
reports/study_s0_plan.md
reports/study_s0_audits.md
research/EXPERIMENTS.md
research/STATUS.md
results/INDEX.md
```

**Caution:** `results/erqa/study_s0/audit1_mvrobobench.json` is also untracked and holds the full
question text and options for all 1,708 MV-RoboBench questions. MV-RoboBench declares no license.
Reduce it to derived statistics, or leave it out of the commit.
