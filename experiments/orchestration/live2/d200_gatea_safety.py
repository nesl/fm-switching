#!/usr/bin/env python3
"""THE REPLACEMENT INPUT FOR THE RUNG-4 SAFETY FACTOR AND FOR D196 (1) GATE A (D200 user ruling 3).

Pre-registered in `results/orchestration/live2/frozen_test/d200_gatea_prereg.json` BEFORE this
script was run. Read that file first: it states the population, the healthy-window definition, the
n and the rank the quantile lands on, and it declares how a zero is to be read.

WHY THE OLD GATE WAS AN IDENTITY AND NOT A MEASUREMENT. `cf_request_defer` computes
`overrun = (b - SAFETY_FACTOR) * predicted_total_service_s` at `b = SAFETY_FACTOR_INFO["max"]`, and
`d190_measured_safety` takes the q90 of its input by nearest rank, `k = max(1, min(n, ceil(q*n)))`.
The committed input had n = 5, so k = 5 = n and the q90 IS the maximum: `b - SAFETY_FACTOR` is
identically 0 and `would_miss` is identically False, for every candidate and every arm. That is why
the input is replaced here and the threshold is not.

THE COUNT IS RETIRED (D206, user ruling, on this script's own reasoning). `overrun =
(b - SAFETY_FACTOR) * service` has the sign of `(b - SAFETY_FACTOR)` alone, because the service is
positive, so the would-have-missed COUNT can only be 0 or N and carries nothing about any
individual deferral. It was 0 of 6 because the old q90 EQUALLED the max, and it is N of N at any
bias strictly above the factor. THE GATE QUANTITIES ARE NOW THE EXPOSURE AND THE OVERRUN
MAGNITUDE. The count is KEPT as a column explicitly labelled an identity, so a reader can see WHY
it was retired rather than only that it went.

NOTHING IS REIMPLEMENTED. The rows come from the committed `cost_model_gate_d162.features`, the
zone from the committed `cost_model_gate_d162.classify`, the first-token coefficients from the
committed `cost_model_gate_d162.json`, and the quantile from the committed
`d190_measured_safety._nearest_rank`. One price source, one quantile rule.

D208 (1) ADDENDUM (Session D, 2026-11-23). `covex-v6-fair-c5attr-rr` joined rung 3, so the cells
the safety factor is derived FROM change when the final rung 3 is built. `--cell-template` and
`--out` make that re-derivation a flag and not an edit, and the DEFAULTS ARE THE COMMITTED ONES:
run with no flags this script writes the same file from the same four
`covex-v6-fair-c5attr_n16_s%d_...` cells as before. The factor itself is NOT re-pinned here; the
addendum run is reported BESIDE the committed one so a reader can see how much the input moved.
The final rungs (`covex-v6-state-final`, `covex-v6-fair-final`, `covex-v6-final`) have no cells
yet, so Gate A for the FINAL rung cannot be computed and is not reported as if it could be.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cost_model_gate_d162 as G                                               # noqa: E402
import d190_measured_safety as MS                                              # noqa: E402

RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
GATE = ROOT / "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"
R4 = ROOT / "results/orchestration/live2/frozen_test/d190_rung4_r3_proofs.json"
OUT = ROOT / "results/orchestration/live2/frozen_test/d200_gatea_safety.json"
CELL = "covex-v6-fair-c5attr_n16_s%d_1200s_h27_3t_L3_epg_rq30"
SEEDS = (4, 5, 6, 7)
Q = 0.90
KIND = "robot"


def coeffs() -> Dict[str, float]:
    """The committed D162 first-token coefficients, READ and never retyped."""
    m = json.loads(GATE.read_text())["model"]["first_token"]
    return {"intercept": float(m["intercept"]),
            "per_uncached_token": float(m["per_uncached_token"]),
            "per_queue_token": float(m["per_queue_token"])}


def ratios(cell_template: str = CELL) -> Dict[str, Any]:
    """Per-request observed-over-predicted first token, healthy windows, robot rows, seeds 4 to 7."""
    c = coeffs()
    rows: List[Dict[str, Any]] = []
    per_seed: Dict[str, int] = {}
    nonhealthy: Dict[str, int] = {}
    for s in SEEDS:
        run = RUNS / (cell_template % s)
        if not run.is_dir():
            raise SystemExit("MISSING committed rung-3 cell: %s" % (run,))
        rs = G.features(run)
        G.classify(rs)
        rob = [r for r in rs if r["kind"] == KIND]
        h = [r for r in rob if r["zone"] == "healthy"]
        per_seed[str(s)] = len(h)
        nonhealthy[str(s)] = len(rob) - len(h)
        for r in h:
            pred = (c["intercept"] + c["per_uncached_token"] * float(r["uncached_tokens"])
                    + c["per_queue_token"] * float(r["queue_uncached_ahead"]))
            if pred <= 0.0:
                continue
            rows.append({"seed": s, "i": r["i"], "warm": bool(r["warm"]),
                         "uncached_tokens": int(r["uncached_tokens"]),
                         "queue_uncached_ahead": round(float(r["queue_uncached_ahead"]), 3),
                         "predicted_first_token_s": round(pred, 6),
                         "observed_first_token_s": round(float(r["first_token_s"]), 6),
                         "observed_over_predicted": round(float(r["first_token_s"]) / pred, 6)})
    v = sorted(x["observed_over_predicted"] for x in rows)
    n = len(v)
    q90 = MS._nearest_rank(v, Q)
    dist = {"cell_template": cell_template, "n": n, "per_seed": per_seed, "robot_rows_NOT_healthy": nonhealthy,
            "min": v[0], "q10": MS._nearest_rank(v, 0.10), "median": st.median(v),
            "q90": q90, "max": v[-1], "n_distinct": len(set(v)),
            "n_strictly_above_q90": sum(1 for x in v if x > q90),
            "q90_rank_k": max(1, min(n, int(-(-Q * n // 1)))),
            "q90_is_strictly_below_max": bool(q90 < v[-1]),
            "frac_above_1": round(sum(1 for x in v if x > 1.0) / n, 6)}
    return {"distribution": dist, "rows": rows, "coefficients_read": c}


def deferrals() -> List[Dict[str, Any]]:
    """Rung 4's own s4 question deferrals, READ from the committed proof JSON."""
    d = json.loads(R4.read_text())
    out: List[Dict[str, Any]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if "would_miss_deadline_under_measured_bias" in o:
                m = o["would_miss_deadline_under_measured_bias"]
                out.append({"deferral_s": m.get("deferral_s"),
                            "predicted_total_service_s": m.get("predicted_total_service_s"),
                            "safety_factor_used": m.get("safety_factor_used")})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    seen, uniq = set(), []
    for r in out:
        k = (r["deferral_s"], r["predicted_total_service_s"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell-template", default=CELL,
                    help="run-directory name template taking the seed, e.g. the committed "
                         "covex-v6-fair-c5attr cells (the default) or the -rr cells")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    r = ratios(a.cell_template)
    dist = r["distribution"]
    sf = float(dist["q90"])
    defs_ = deferrals()
    cols: Dict[str, Any] = {}
    for tag, b in (("at_median_ratio", float(dist["median"])),
                   ("at_q90_ratio_THE_SAFETY_FACTOR_ITSELF", sf),
                   ("at_max_ratio", float(dist["max"]))):
        rowsout = []
        for d in defs_:
            total = float(d["predicted_total_service_s"] or 0.0)
            over = (float(b) - sf) * total
            rowsout.append({"predicted_total_service_s": total, "bias": float(b),
                            "overrun_s": round(over, 6), "would_miss": bool(over > 0.0)})
        nmiss = sum(1 for x in rowsout if x["would_miss"])
        cols[tag] = {"bias": float(b), "n_deferrals": len(rowsout),
                     "would_have_missed": nmiss,
                     "ratio_to_deferral_count": (round(nmiss / len(rowsout), 6)
                                                 if rowsout else None),
                     "is_an_identity": bool(abs(float(b) - sf) < 1e-12),
                     "per_deferral": rowsout}
    # THE COUNT IS STRUCTURALLY 0 OR N AND THAT IS THE SECOND HALF OF THE DEFECT.
    # overrun = (b - SAFETY_FACTOR) * predicted_total_service_s and the service is positive, so the
    # sign of the overrun is the sign of (b - SAFETY_FACTOR) and does not depend on the deferral at
    # all. The count can therefore only be 0 or N: it was 0 of 6 because the old q90 EQUALLED the
    # max, and it is N of N at any bias strictly above the factor. Replacing the input fixes the
    # degenerate quantile but it does NOT make the COUNT informative, so the quantity that carries
    # the information is reported beside it: the EXPOSURE, the measured fraction of sent recall
    # requests whose own observed-over-predicted ratio exceeded the safety factor. At a q90 factor
    # that fraction is about 10 percent BY CONSTRUCTION, and the value of measuring it is that it
    # is now 46 of 463 real requests instead of 0 of 5.
    v_sorted = sorted(x["observed_over_predicted"] for x in r["rows"])
    n_over = sum(1 for x in v_sorted if x > sf)
    exposure = {
        "_what": ("the quantity the would-have-missed COUNT cannot carry: how often a sent recall "
                  "request really did overrun the safety factor, measured on the committed cells"),
        "n_sent_requests": len(v_sorted),
        "n_above_the_safety_factor": n_over,
        "fraction_above_the_safety_factor": round(n_over / len(v_sorted), 6),
        "worst_ratio_seen": v_sorted[-1],
        "worst_overrun_multiple_of_predicted_service": round(float(v_sorted[-1]) - sf, 6),
        "_how_to_read_it": ("a deferral placed at the latest safe start carries about this "
                            "probability of overrunning, and the overrun magnitude is "
                            "(ratio - safety_factor) x predicted service seconds"),
        "_why_the_count_is_not_this": ("the count compares ONE bias against the factor, so it is "
                                       "0 or N by the sign of (b - factor); this fraction compares "
                                       "EVERY measured request against the factor")}
    old = {"n": 5, "source": MS.INFO.get("source"), "safety_factor": MS.SAFETY_FACTOR,
           "max": MS.INFO.get("max"), "min": MS.INFO.get("min"),
           "q90_equals_max": abs(float(MS.SAFETY_FACTOR) - float(MS.INFO["max"])) < 1e-12,
           "verdict": ("IDENTITY: q90 of 5 points by nearest rank IS the maximum, so "
                       "overrun = (max - q90) * predicted is identically 0 and the committed "
                       "would-have-missed 0 of 6 could not have been anything else")}
    gate = {"_status": "D206: THE GATE. Exposure and overrun magnitude, both measurements.",
            "safety_factor_q90": sf,
            "exposure_fraction_of_sent_recall_requests_over_the_safety_factor":
                exposure["fraction_above_the_safety_factor"],
            "exposure_n_over_n": "%d of %d" % (exposure["n_above_the_safety_factor"],
                                               exposure["n_sent_requests"]),
            "overrun_magnitude_worst_as_a_multiple_of_predicted_service":
                exposure["worst_overrun_multiple_of_predicted_service"],
            "quantile_is_non_degenerate": dist["q90_is_strictly_below_max"],
            "n_rows_strictly_above_the_factor": dist["n_strictly_above_q90"],
            "_how_to_read": ("a deferral placed at the latest safe start carries about the "
                             "exposure probability of overrunning, and the overrun costs "
                             "(ratio - safety_factor) x predicted service seconds; both are "
                             "measured on real sent requests, which the retired count was not")}
    res = {
        "_what": ("the rung-4 safety factor and the D196 (1) Gate A would-have-missed count, "
                  "re-derived from the PER-REQUEST observed-over-predicted first-token ratio of "
                  "the committed healthy-window robot rows of the rung-3 sent cells, seeds 4 to 7"),
        "_prereg": "results/orchestration/live2/frozen_test/d200_gatea_prereg.json",
        "_only_the_input_changed": ("q90 unchanged, nearest-rank rule unchanged (the committed "
                                    "d190_measured_safety._nearest_rank is CALLED, not copied), "
                                    "overrun formula unchanged, MARGIN_CF unchanged"),
        "new_input": dist,
        "new_safety_factor_q90": sf,
        "old_input_for_comparison": old,
        "THE_GATE": gate,
        "gate_a_would_have_missed_RETIRED": cols,
        "_why_the_count_is_retired": (
            "D206, on this script's own reasoning: overrun = (b - SAFETY_FACTOR) * service has the "
            "sign of (b - SAFETY_FACTOR) alone, so the count is 0 or N and never in between. The "
            "old 0 of 6 was an identity because q90 equalled max; N of N at the max bias is an "
            "identity of the opposite sign. Replacing the input made the QUANTILE real and did "
            "not make the COUNT informative. The column is kept and labelled so a reader can see "
            "why it was retired, not merely that it went."),
        "gate_a_count_is_structurally_0_or_N": {
            "why": ("overrun = (b - SAFETY_FACTOR) * predicted_total_service_s with a positive "
                    "service, so the sign is the sign of (b - SAFETY_FACTOR) and is the same for "
                    "every deferral. The count is 0 below the factor, 0 AT the factor and N above "
                    "it, for any N."),
            "consequence": ("the old 0 of 6 was an identity because q90 EQUALLED max; the new N of "
                            "N at the max bias is an identity of the opposite sign. Replacing the "
                            "input makes the QUANTILE real and does NOT make the COUNT "
                            "informative. Read `exposure_measured_on_sent_requests` instead."),
            "n_deferrals_on_the_s4_cell": 6,
            "n_deferrals_recoverable_from_the_committed_proof_json": 1,
            "register": ("the 6 is the committed and independently reproduced rd_question_defers "
                         "counter; only 1 of the 6 carries predicted_total_service_s in the "
                         "committed proof JSON, so the per-deferral overrun seconds are reported "
                         "for that one and the COUNTS are reported by the sign rule above, which "
                         "is exact for all 6")},
        "exposure_measured_on_sent_requests": exposure,
        "_register": {
            "at_q90_column": ("AN IDENTITY BY DESIGN and labelled as one: the bias equals the "
                              "safety factor, so the overrun is identically 0. It is reported so "
                              "the reader can see which column is an identity."),
            "at_median_and_at_max_columns": ("MEASUREMENTS, because the median and the max are "
                                             "strictly different from the q90 on an n of 463 "
                                             "with 46 rows strictly above the q90"),
            "rows_are_per_request_not_per_cell": ("the old 5 values were the sent rows of TWO "
                                                  "devices on TWO seeds; these are every sent "
                                                  "robot request on FOUR seeds")},
        "rows": r["rows"],
        "_provenance": {"script": "d200_gatea_safety.py", "model": "n/a (read-only)",
                        "device": "flash (CPU only)", "n": dist["n"]},
    }
    res["_cell_template"] = a.cell_template
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({"n": dist["n"], "min": dist["min"], "median": dist["median"],
                      "q90": dist["q90"], "max": dist["max"],
                      "n_distinct": dist["n_distinct"],
                      "n_strictly_above_q90": dist["n_strictly_above_q90"],
                      "q90_strictly_below_max": dist["q90_is_strictly_below_max"],
                      "old_safety_factor": MS.SAFETY_FACTOR,
                      "new_safety_factor": sf,
                      "deferrals": len(defs_),
                      "would_have_missed": {k: (v["would_have_missed"], v["is_an_identity"])
                                            for k, v in cols.items()},
                      "exposure_n_above_factor": exposure["n_above_the_safety_factor"],
                      "exposure_fraction": exposure["fraction_above_the_safety_factor"],
                      "worst_overrun_multiple": exposure[
                          "worst_overrun_multiple_of_predicted_service"]},
                     indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
