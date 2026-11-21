#!/usr/bin/env python3
"""D157 (2)'s MARGIN_CF population, keyed on CELL NAME, outside the frozen model.

WHY THIS IS A SEPARATE FILE, which is the point of it.

`cf_ontime_frozen.py` hashes BOTH its payload and its own source (`code_sha256`), so `load()`
refuses to predict if the module text changes. That is the right guard on `P_hat`'s ARITHMETIC: a
model edited after seeing a measurement is the fitting D157 (2) exists to prevent.

But that hash also covered the POPULATION BOOKKEEPING, which is not arithmetic and which had to be
corrected before any cell ran. Editing the population in place raised `FrozenModelTampered`, so a
legitimate correction was indistinguishable from tampering. Conflating "what P_hat computes" with
"which cells it is computed over" is the actual defect, and it is fixed by separation rather than by
re-freezing: `cf_ontime_frozen.py` is byte-identical to the frozen commit (1e021f5) and both its
hashes still verify, while the population lives here where it can be corrected and audited.

TWO ERRORS IN THE ORIGINAL GUARD, both found by the H100 BEFORE the cells ran, and the second is
why the cell NAME is now authoritative rather than the arm and label.

(a) The four held-out cells are four DIFFERENT arms: the full pool, `-reactive`, `-off`, and the
    full pool again at a 0.25x logical pool. A guard requiring `arm == "warm-all-lru"` on exactly
    four cells finds TWO and refuses the population outright. That failure is loud and merely
    costly.

(b) D156's v5-rules block ALSO runs `warm-all-lru` on EP-G with per-frame upload at SEED 5, from
    about 03:00. Its label contains "EP-G" and "upload-pf" and none of the forbidden strings, so a
    label-based guard ADMITS IT AS A FIFTH CELL and computes the margin over a population D157 (2)
    explicitly excludes, WITHOUT RAISING. A guard that silently widens its own population is worse
    than no guard, because the number it produces looks exactly like the right one.

So the population is an explicit list of four names. A fifth cell is refused by name whatever it
calls itself, and a renamed cell is refused rather than guessed at.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cf_ontime_frozen as F

# The H100's driver writes these exact directory names (confirmed 2026-11-20 before the run).
POPULATION_CELLS: Tuple[str, ...] = (
    "warm-all-lru_n16_s4_1200s_h27_3t_L3_epg",
    "warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg",
    "warm-all-lru-off_n16_s4_1200s_h27_3t_L3_epg",
    "warm-all-lru_n16_s4_1200s_h27_3t_kv0.25_L3_epg",
)

# Kept as a SECOND, independent check rather than the primary key: the label must still agree with
# the name. The H100's label is "FROZEN_TEST_THREE_TYPE dashcam-EP-G upload-pf <cell name>".
LABEL_REQUIRED: Tuple[str, ...] = ("EP-G", "upload-pf")
LABEL_FORBIDDEN: Tuple[str, ...] = ("dashcam-1f", "upload-30s", "v5-rules")


class PopulationRefused(RuntimeError):
    """The cells offered are not D157 (2)'s population. Never widened, never guessed."""


def check_cell(cell_dir: Path) -> Dict[str, Any]:
    """Is this ONE cell in the population? Reports every reason it is not."""
    d = Path(cell_dir)
    name, problems = d.name, []  # type: str, List[str]
    if name not in POPULATION_CELLS:
        problems.append("cell name %r is not one of D157 (2)'s four declared cells" % name)
    label = F.cell_label(d)
    if label is None:
        problems.append("run_meta.json::label is absent, so the cell does not declare its workload")
    else:
        for s in LABEL_REQUIRED:
            if s not in label:
                problems.append("label does not contain %r" % s)
        for s in LABEL_FORBIDDEN:
            if s in label:
                problems.append("label contains %r, which the population excludes" % s)
    return {"cell": name, "label": label, "arm": F.cell_arm(d),
            "in_population": not problems, "problems": problems}


def check_population(cell_dirs: Sequence[Path]) -> Dict[str, Any]:
    """All four, exactly, by name. Raises rather than returning a partial population."""
    rows = [check_cell(p) for p in cell_dirs]
    found = {r["cell"] for r in rows if r["in_population"]}
    missing = [c for c in POPULATION_CELLS if c not in found]
    extra = [r["cell"] for r in rows if not r["in_population"]]
    ok = not missing and not extra and len(rows) == len(POPULATION_CELLS)
    out = {"_rule": ("D157 (2): every robot question released in the 4 EP-G WARM-ALL held-out "
                     "cells (upload-pf) and NO other cells, keyed on cell name"),
           "declared": list(POPULATION_CELLS), "offered": [r["cell"] for r in rows],
           "per_cell": rows, "missing": missing, "not_in_population": extra, "complete": ok}
    if not ok:
        raise PopulationRefused(
            "the margin's population is not intact, so nothing is computed. missing=%r "
            "not_in_population=%r offered=%d of %d. D157 (2) names these four cells and no "
            "others; a fifth cell (notably warm-all-lru at SEED 5 from the v5-rules block, whose "
            "label also contains EP-G and upload-pf) must NOT be admitted."
            % (missing, extra, len(rows), len(POPULATION_CELLS)))
    return out


def census(cell_dirs: Sequence[Path]) -> Dict[str, Any]:
    """Counts only, no prediction: how much of the population is PRICEABLE.

    Run this the moment the cells land, BEFORE scoring anything. A question released but returned
    with null prompt_tokens (the submission-race 400s) is in D157 (2)'s population and counts as
    missed, and `P_hat` cannot price it. On the 1F race cell that was 7 of 20.
    """
    rows = [dict(check_cell(p), **F.census_one(Path(p))) if hasattr(F, "census_one")
            else check_cell(p) for p in cell_dirs]
    return {"_what": "priceable counts per cell; no model evaluated", "per_cell": rows}
