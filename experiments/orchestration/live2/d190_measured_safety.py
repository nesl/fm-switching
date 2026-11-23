#!/usr/bin/env python3
"""THE SAFETY FACTOR FOR THE LATEST SAFE START, DERIVED FROM COMMITTED RUNG-3 DATA (D191, revised).

    "the latest safe start must carry the MEASURED D162 UNDER-PREDICTION as its safety factor,
     derived from committed rung-3 data, with THE QUANTILE AND SOURCE STATED, never assumed"

THIS FILE READS THE NUMBER. IT DOES NOT CHOOSE ONE. Every ratio below is parsed out of a committed
result file at import time, the quantile is named, the sample size is named, and both common
quantile conventions are computed so the choice is visible rather than buried in a library call.
Nothing here is fitted, swept or rounded to taste.

WHY THIS IS NOT TUNING, STATED SO IT CAN BE CHECKED RATHER THAN BELIEVED. The ratios come from
`covex-v6-fair-c5attr` cells at seeds 5 and 7 - THE RUNG-3 BASE rung 4 is built on, not rung 4's
own cells. A parameter derived from the committed behaviour of the base is the same practice D180
to D182 used to derive the D179 floors from committed `covex-v6-base` cells. A parameter derived
from the cells being diagnosed would be tuning; this is not that. The distinction is the provenance
of the data, so the provenance is recorded on the value and travels with it.

WHAT THE RATIOS ARE. `observed_ttft_s / predicted_first_token_s` on every recall question ACTUALLY
SENT in those two cells, where the prediction is the committed D162 model
(`first_token = 0.0678 + 0.000182 x uncached + 0.000154 x uncached_queued_ahead`) evaluated on the
ENGINE-REPORTED uncached and queued-ahead token counts, and the observation is the engine's own
first-token time. So both sides are measured, and the ratio is a model error and not a comparison
of two predictions.

THE SAMPLE IS n = 5 AND THAT IS SAID FIRST, not in a footnote. With five values the q90 by NEAREST
RANK **is the maximum**, and the linear-interpolation q90 sits between the fourth and fifth. Both
are computed and both are reported. The one IN FORCE is the nearest-rank q90, for two reasons
stated rather than assumed: it is the convention D125 already uses for kappa ("the q90 of measured
over predicted"), and it is the conservative direction - a LARGER factor puts the latest safe start
EARLIER, which costs slack and cannot cause the self-inflicted lateness this factor exists to
prevent. The small sample is a real limitation and is carried on the value as `sample_caveat`.

HOW THIS COMPARES WITH THE COMMITTED kappa IT REPLACES ON THIS PATH. `cf_margin.safety_factor` is
1.5775406165458339, the q90 of actual over predicted service on a held-out-by-arm split of
`cf_service_residuals.json`. The measured D162 under-prediction on the rung-3 sent rows runs 1.3856
to 1.8721, so the committed kappa COVERS 1.3856 AND DOES NOT COVER 1.8721. That is the gap this
file closes, in the one direction that is safe to close it.

SCOPE. This factor is used by `cf_request_defer` ONLY. `cf_protect_defer.KAPPA` is LEFT EXACTLY AS
COMMITTED, because that module's arms (`covex-v6-cf-pd-*`) have a posted cell list owned by another
session and changing their safety factor would silently change what those cells measure. So the
tree holds two safety factors on purpose, and each one says which it is: that is a recorded
divergence, not an oversight.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE_REL = "results/orchestration/live2/frozen_test/d190_recall_lag_diagnosis.json"
SOURCE = REPO / SOURCE_REL
RATIO_PATH = ("devices.<device>.D162_positive_control_on_sent_rows[].observed_over_predicted")

QUANTILE = 0.90
QUANTILE_METHOD = "nearest-rank"


class MeasuredSafetyUnavailable(RuntimeError):
    """The committed source could not be read. NOT silently replaced by a default.

    A missing file must not become a quiet 1.0: that would make every deferral look safe and the
    mechanism look as though it worked. D191 requires the factor to be MEASURED, so if it cannot
    be measured this raises and the arm does not run.
    """


def _ratios_from(doc: Dict[str, Any]) -> List[Tuple[str, str, float]]:
    out: List[Tuple[str, str, float]] = []
    for dev_key, dev in (doc.get("devices") or {}).items():
        for row in (dev.get("D162_positive_control_on_sent_rows") or []):
            r = row.get("observed_over_predicted")
            if r is None:
                continue
            out.append((str(dev_key), str(row.get("opportunity_id")), float(r)))
    return out


def _nearest_rank(values: List[float], q: float) -> float:
    """The q-quantile by NEAREST RANK: the smallest value at or above rank ceil(q * n)."""
    import math
    v = sorted(values)
    n = len(v)
    k = max(1, min(n, math.ceil(q * n)))
    return float(v[k - 1])


def _linear(values: List[float], q: float) -> float:
    """The q-quantile by linear interpolation, the numpy default, for comparison only."""
    v = sorted(values)
    if len(v) == 1:
        return float(v[0])
    pos = q * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return float(v[lo] + (pos - lo) * (v[hi] - v[lo]))


def load() -> Dict[str, Any]:
    if not SOURCE.exists():
        raise MeasuredSafetyUnavailable(
            "the committed source %s is not in this tree, so the safety factor cannot be MEASURED "
            "and will not be defaulted" % SOURCE_REL)
    doc = json.loads(SOURCE.read_text())
    rows = _ratios_from(doc)
    if not rows:
        raise MeasuredSafetyUnavailable(
            "%s holds no %s rows, so no ratio could be read" % (SOURCE_REL, RATIO_PATH))
    vals = [r[2] for r in rows]
    nr = _nearest_rank(vals, QUANTILE)
    li = _linear(vals, QUANTILE)
    return {
        "safety_factor": nr,
        "quantile": QUANTILE,
        "quantile_method": QUANTILE_METHOD,
        "quantile_nearest_rank": nr,
        "quantile_linear_interpolation": li,
        "n": len(vals),
        "min": min(vals), "max": max(vals),
        "all_values_sorted": sorted(vals),
        "rows": [{"device_key": d, "opportunity_id": o, "observed_over_predicted": r}
                 for d, o, r in rows],
        "source": SOURCE_REL,
        "source_path_within_file": RATIO_PATH,
        "source_cells": (doc.get("_cells_used") or {}),
        "what_the_ratio_is": (
            "observed engine first-token time divided by the committed D162 model's prediction on "
            "the ENGINE-REPORTED uncached and queued-ahead token counts, for every recall question "
            "actually SENT in the two committed covex-v6-fair-c5attr cells (seeds 5 and 7). Both "
            "sides measured; the ratio is a model error, not two predictions compared."),
        "why_not_tuning": (
            "the ratios come from the RUNG-3 BASE's own committed cells, not from rung 4's cells. "
            "Same practice as D180 to D182, which derived the D179 floors from committed "
            "covex-v6-base cells."),
        "sample_caveat": (
            "n = %d. At this n the nearest-rank q90 IS THE MAXIMUM, and the linear-interpolation "
            "q90 is %.5f. The nearest-rank value is the one in force: it is D125's own convention "
            "for kappa and it is the CONSERVATIVE direction, since a larger factor puts the "
            "latest safe start EARLIER and so cannot cause the lateness this factor exists to "
            "prevent. Five rows is a real limitation on how well the tail is characterised and it "
            "is not presented as more than it is." % (len(vals), li)),
        "committed_kappa_it_replaces_on_this_path": {
            "value": 1.5775406165458339,
            "source": "cf_margin.safety_factor(cf_cost.load_residuals()), q90 on a "
                      "held-out-BY-ARM split of cf_service_residuals.json",
            "coverage": ("it COVERS the 1.3856 low end of the measured range and DOES NOT COVER "
                         "the 1.8721 high end, which is the gap this factor closes"),
            "still_in_force_for": ("cf_protect_defer, unchanged: its arms have a posted cell list "
                                   "owned by another session and changing their safety factor "
                                   "would change what those cells measure"),
        },
    }


INFO: Dict[str, Any] = load()
SAFETY_FACTOR: float = float(INFO["safety_factor"])


def main() -> int:
    print(json.dumps(INFO, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
