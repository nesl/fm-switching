# Superseded and invalid artifacts in this directory

Dated 2026-11-06. Nothing listed here is deleted or edited; this file records status only.

## INVALID — the grey-frame control of the 2026-11-05/06 run

| artifact | status |
|---|---|
| the 400 rows with `grey=true` in `model_4B/requests.part000.jsonl.gz` | **INVALID as a negative control.** Kept. |
| the 400 rows with `grey=true` in `model_8B/requests.part000.jsonl.gz` | **INVALID as a negative control.** Kept. |
| the `grey` block of `analysis.json` | **INVALID.** Computed from the rows above. |

**Reason.** `experiments/benchmarks/b1_run.py:428-431` hardcoded a single synthetic question
(`"What is shown?"`, options `one/two/three/four`, `gold` fixed to `"A"`) belonging to no
dataset, and `b1_run.py:433` submitted that same row object 100 times, varying only `gidx`,
which `b1_run.py:335` uses in the dedup key alone. Verified in the rows: **1 distinct
`prompt_sha256` per cell**, hence **1 distinct response per Instruct cell** under greedy
decoding (n=100 carried the information of n=1), and constant `gold`, so the statistic is
P(model emits "A") — an answer-position bias, not P(correct without visual information).

The real benchmark rows are **unaffected**: grey rows are separately keyed and excluded from
every real-arm statistic.

**Replaced by** `grey2/` (StudyB1-grey2), where each grey request carries a real question with
its option text verbatim and only the pixels are grey. See `reports/study_b1_flash.md` §7, §14.

## SUPERSEDED — analysis revision 1

| artifact | status |
|---|---|
| `analysis.json` | **SUPERSEDED by `analysis_rev2.json`.** Kept. |

Revision 1 (a) used the invalid grey control, (b) included HERBench, which the user removed
from StudyB1 on 2026-11-06, and (c) predates the RTV-Bench Instruct HISTORY remainder in
`grey2/`. Its §8 tables in the report are superseded by §15–§17.

## Note on the per-frame SHA-256 in every row

The recorded `frames.frame_sha256` is a hash of **PNG container bytes**, so it is sensitive to
the zlib compression level and is **not** a valid cross-host frame-identity key (this run used
PIL's default level 6; StudyB1-h100 uses level 1). It remains a valid within-host integrity
check. Cross-host frame identity was instead verified by re-encoding and is recorded in
`crosshost_frame_check.json`; see `reports/study_b1_flash.md` §18.
