#!/usr/bin/env python3
"""ONE dry cell per process for `covex-v6-fair-c5attr-rr`, through the COMMITTED recipe.

THE DIGEST IS NOT RECOMPUTED HERE. The posted knobs, the seed allowlist, the planner wall-clock
patch, the one-cell-per-process rule and the digest recipe all live in `cf_pd_one_cell.py` and are
reused by CALLING ITS `main()`. This file contains no `sha256` and no `json.dumps` of any row,
because a second copy of that recipe is how two digests of the same rows stop matching.

TWO ADDITIONS, both outside the digest path.

  1. `cf_pd_one_cell.PD_STAT_KEYS` is EXTENDED with the four frozen `release_recheck` counter
     names. That tuple is a DATA constant listing which stats to echo, not part of the recipe, so
     extending it changes what is reported and nothing that is computed. The counters live in the
     COORDINATOR's `counts` (the re-check is a wire-time coordinator action, not the arm's
     statistic) and they do reach `test_hybrid.dry`'s returned stats, which is where the runner
     reads them.

  2. `release_recheck.decide` is WRAPPED to record every call, so the per-skip `est_first_token_s`
     and `remaining_s` are available for the WOULD-HAVE-MADE-IT check. The wrapper returns the
     committed function's own result unchanged and adds nothing to it, so no decision can move:
     it is a tap, not a filter. The coordinator also keeps `release_infeasible_events`, but that
     list lives on the coordinator object and `test_hybrid.dry` does not hand it back, so the tap
     is how the rows are obtained without editing a committed file.

Accepts exactly the flags `cf_pd_one_cell.py` accepts, plus `--rr-out`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_pd_one_cell as C                                                     # noqa: E402
import release_recheck as RR                                                   # noqa: E402

RR_KEYS = (RR.COUNTER_TOTAL,) + tuple(RR.COUNTER_BY_TYPE[t] for t in RR.TYPES) + (
    RR.COUNTER_UNCLASSIFIED,
    "release_recheck_out_of_scope_recall", "release_recheck_out_of_scope_assistance",
    "mon_sent", "mon_opportunities", "recall_CLOUD", "recall_DEVICE",
)

_CALLS: List[Dict[str, Any]] = []


def _tap() -> None:
    """Record every `RR.decide` call. Returns the committed result unchanged: a tap, not a filter."""
    orig = RR.decide

    def wrapped(**kw: Any) -> Dict[str, Any]:
        out = orig(**kw)
        if len(_CALLS) < 20000:
            _CALLS.append(dict(out))
        return out
    RR.decide = wrapped                                                    # type: ignore[assignment]


def _report() -> Dict[str, Any]:
    feas = [c for c in _CALLS if c.get("feasible")]
    skip = [c for c in _CALLS if not c.get("feasible")]
    by_type: Dict[str, Dict[str, int]] = {}
    for c in _CALLS:
        t = str(c.get("qtype"))
        d = by_type.setdefault(t, {"evaluated": 0, "feasible": 0, "skipped": 0})
        d["evaluated"] += 1
        d["feasible" if c.get("feasible") else "skipped"] += 1
    # THE WOULD-HAVE-MADE-IT CHECK. The ratio is the predictor's own overrun: est / remaining. A
    # skip at a ratio only just above 1 is one the predictor's error could account for.
    def ratio(c: Dict[str, Any]) -> float:
        rem = float(c.get("remaining_s") or 0.0)
        return (float(c["est_first_token_s"]) / rem) if rem > 0 else float("inf")
    rs = sorted(ratio(c) for c in skip)
    # THE ONLY FACTOR USED, and it is READ from the committed D162 gate rather than chosen:
    # the fit's own p50 actual over predicted, 0.2455 / 0.2519 = 0.974593... (the model
    # OVER-predicts slightly at the median). A skip would have made it if the true first token
    # fitted, i.e. if est x (actual/predicted) <= remaining, i.e. ratio <= predicted/actual.
    P50_ACTUAL = 0.2455
    P50_PRED = 0.2519
    k = P50_PRED / P50_ACTUAL
    return {
        "n_decide_calls": len(_CALLS),
        "n_feasible": len(feas), "n_skipped": len(skip),
        "by_type": by_type,
        "skip_overrun_ratio_est_over_remaining": {
            "n": len(rs),
            "min": (rs[0] if rs else None),
            "p10": (rs[max(0, len(rs) // 10)] if rs else None),
            "median": (rs[len(rs) // 2] if rs else None),
            "p90": (rs[min(len(rs) - 1, 9 * len(rs) // 10)] if rs else None),
            "max": (rs[-1] if rs else None),
            "n_distinct": len(set(round(x, 9) for x in rs)),
        },
        "WOULD_HAVE_MADE_IT": {
            "_what": ("a skip of an instant that WOULD have made its deadline is a SELF-INFLICTED "
                      "LOSS, the analogue of rung 4's deferred-and-would-have-missed count."),
            "_dry_limitation": ("a dry cell has no engine, so there is no observed first token to "
                               "compare against. What IS available is the predictor's own overrun "
                               "and the committed fit's measured bias, and both are reported."),
            "factor_used": k,
            "factor_source": ("cost_model_gate_d162.json, the committed fit's predicted_p50 %.4f "
                              "over actual_p50 %.4f = %.6f. The model OVER-predicts by 2.6 percent "
                              "at the median, and alert requests sit at the LOW-token end of that "
                              "fit, so this is the relevant direction for them. READ, not chosen."
                              % (P50_PRED, P50_ACTUAL, k)),
            "n_skips_that_would_have_made_it_at_the_fit_p50": sum(1 for x in rs if x <= k),
            "ratio_to_total_skips": (sum(1 for x in rs if x <= k) / len(rs)) if rs else None,
            "n_skips_within_10_percent_of_the_deadline": sum(1 for x in rs if x <= 1.10),
            "n_skips_within_50_percent": sum(1 for x in rs if x <= 1.50),
            "n_skips_over_2x_the_remaining_time": sum(1 for x in rs if x > 2.0),
            "the_tail_direction_is_FAVOURABLE_here": (
                "on the multi-thousand-uncached TAIL the same fit UNDER-predicts by 1.39x to "
                "1.87x (d190_recall_lag_diagnosis.json), so a large request's true first token is "
                "LARGER than est and a skip is MORE justified, not less. That is the opposite of "
                "rung 4's exposure, where under-prediction worked against the deferral."),
        },
        "first_10_skips": skip[:10],
        "first_10_feasible": feas[:10],
    }


if __name__ == "__main__":
    rr_out = None
    if "--rr-out" in sys.argv:
        i = sys.argv.index("--rr-out")
        rr_out = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    C.PD_STAT_KEYS = tuple(C.PD_STAT_KEYS) + RR_KEYS
    _tap()
    rc = C.main()
    if rr_out:
        Path(rr_out).write_text(json.dumps(_report(), default=float))
    raise SystemExit(rc)
