# Study J6 — HALTED: required inputs are missing from this machine

**Date:** 2026-10-14
**Script:** `experiments/signs/study_j6_score.py` (exists, unmodified)
**Inference run:** **NOT STARTED** — three required inputs are absent.

---

## Verdict

> **HALTED. Not a result — a missing-input failure.**
>
> The scorer-validation pre-condition **cannot even be attempted**, and the ORIGINAL arm cannot be
> constructed. No model trials were run and nothing was scored.

StudyJ6 remains **open**: the question it was built to answer — whether the SIMPLIFIED prompt
costs accuracy — is still unanswered, exactly as it was after StudyJ5.

---

## What is missing

The script depends on an external working tree at `/tmp/sign-understanding`. `/tmp` has been
cleared since the script was last touched (2026-10-03). All five referenced paths are gone:

| path | role | status |
|---|---|---|
| `/tmp/sign-understanding/prompts/prompt.txt` | **ORIGINAL prompt template** | **MISSING — blocking** |
| `/tmp/sign-understanding/prompts/symbols.txt` | symbol vocabulary (`sym_str`, used by *both* arms) | **MISSING — blocking** |
| `/tmp/sign-understanding/recognition_results/gemini/recogntion_results.json` | Gemini-2.0-Flash baseline | **MISSING — blocking** |
| `/tmp/sign-understanding/gt/gt_annotation.json` | ground truth | missing, but **recoverable** (see below) |
| `/tmp/sign-understanding/gt/recognition-exclude-imgs.txt` | exclusion list | missing, not recoverable |

Searched and not found: `/tmp`, the whole of `/home/pragya` (depth 5), the repository working
tree, and git history (`--diff-filter=A` across all refs). `data/signs/dataset.zip` exists but is
**0 bytes**.

---

## Why each blocker is fatal rather than inconvenient

**1. The ORIGINAL prompt cannot be reconstructed, and J6 is a comparison against it.**

`make_prompts()` builds the two arms asymmetrically:

- **SIMPLIFIED** is a literal f-string **embedded in the script** — recoverable, except for the
  `sym_str` interpolation.
- **ORIGINAL** is `open(PROMPT_PATH).read()` with `GT_SYMBOL_LIST` and `REPLACE_DIRECTION_LIST`
  substituted — i.e. the upstream benchmark's own prompt text, which exists nowhere on this
  machine.

J6 is a **paired** ORIGINAL-vs-SIMPLIFIED test on matched (sign, seed) pairs. One arm cannot be
run against a reconstruction of the other: inventing the ORIGINAL prompt would be inventing the
experimental condition under test. That is a methodological change of the most serious kind, and
per `CLAUDE.md` it must be flagged rather than applied.

**2. `symbols.txt` affects both arms.** `sym_str = ", ".join(symbols[:10])` — the *first ten
lines in that file's order*. The HF `test.json` contains symbol-label keys, but not that file's
ordering, so `sym_str` cannot be reproduced faithfully even for the SIMPLIFIED arm.

**3. The scorer-validation pre-condition cannot be attempted.** The registry row states:

> SCORER VALIDATION (pre-condition): reproduce Gemini-2.0-Flash overall_acc ≈ 40.7% (J2
> reference) before scoring any model trials; **halt if validation fails**.

Without the Gemini predictions file there is no way to check the open_clip scorer
(ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip) is wired correctly. Scoring model trials
with an unvalidated scorer would breach an explicit pre-condition — and StudyJ5 already failed
once on a scoring-pipeline defect (`answer_text` not stored), which is the reason J6 exists.

---

## What *is* recoverable, for whoever restores this

- **Ground truth:** the HF dataset `NickyZimmerman/SiGNgapore2D` ships `test.json` (167 records)
  with `imagePath`, `objectID`, `boundingBox`, `text labels` and `symbol labels` — the same
  structure `gt_annotation.json` provided. Verified by download this session.
- **Images:** 167 files in the same HF repo; already cached locally at
  `~/.cache/huggingface/hub/datasets--NickyZimmerman--SiGNgapore2D`.
- **SIMPLIFIED prompt body:** embedded verbatim in `study_j6_score.py` lines 307–333.

**Still required from elsewhere:** `prompt.txt`, `symbols.txt`, the Gemini results JSON, and the
exclusion list. These came from a separate `sign-understanding` project tree, not from this
repository. They may survive on another machine (the H100 box, or wherever that project is
checked out) — that is the fastest route to unblocking J6.

**Recommendation:** once recovered, copy them **into this repository** under `data/signs/` rather
than `/tmp`, so the study is not lost to the next reboot. This is the second time a `/tmp`
dependency has cost a run.

---

## Pre-existing partial data

`results/signs/study_j6/study_j6_trials.jsonl` holds **12 trials** from 2026-10-03 (6 ORIGINAL,
6 SIMPLIFIED) against the planned 140. The schema is complete — it does include `answer_text`,
`score`, `think_closed` and `truncated`, so the J5 defect was genuinely fixed. The file was left
untouched this session. 12 of 140 is far too few to analyse, and the trials predate any scorer
validation.

---

## Verdict in the pre-registered form

The registry's rule is **FIX vs TRADE**. Neither can be returned:

> **Neither FIX nor TRADE. The experiment did not run.** No termination rates, no accuracy
> comparison, no paired test. StudyJ6 stays **PENDING**, blocked on inputs rather than on compute.
