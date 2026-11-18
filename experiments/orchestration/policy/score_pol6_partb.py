"""StudyPOL6 Part B: score pol4 against pol6 on StudyENG1e FIT, all four T0b criteria.

REGRESSION STOP. The brief's gate is that pol6 must not be worse than pol4 on criterion (ii)
(action ranking) or (iii) (job completion). This module computes both for both models and sets
`regression_stop` if either worsens; the caller must not freeze pol6 when it fires.

NO HOLDOUT IS READ. `eng1e_replay.load_eng1e_trials("fit")` is the only loader used, criterion
(i-b)'s noise ceiling comes from StudyENG1e's own FIT repeat arms, and criterion (iv) has no
ENG1e measurement at all, so StudyT0's committed value stands and is reported unchanged.
"""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import eng1e_replay as er, score_t0b as s0, trace_replay as tr
from .eng1_engine import make_sim
from .pol6_engine import Pol6Terms, Pol6Sim

OUT_PATH = "results/orchestration/study_pol6/pol6_partB_fit_score.json"
METRICS = ("latency", "ttft")          # latency primary (T0b), ttft secondary


def _models(terms_path: Optional[Any] = None) -> Dict[str, Any]:
    base = make_sim("pol4")
    pol6 = Pol6Sim(sim=make_sim("pol4"),
                   terms=Pol6Terms.load(terms_path).with_config(measured_handover=True))
    return dict(pol4=base, pol6=pol6)


def per_cell_table(res: Dict[str, Any]) -> Dict[str, Any]:
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in res["trials"]:
        if r["reconstructible"]:
            by[r["cell"]].append(r)
    out = {}
    for cell, rows in sorted(by.items()):
        m = st.median([r["measured_delay_s"] for r in rows])
        p = st.median([r["predicted_delay_s"] for r in rows])
        over = sum(1 for r in rows if r["predicted_delay_s"] > r["measured_delay_s"])
        out[cell] = dict(n=len(rows), measured_median_s=round(m, 4),
                         predicted_median_s=round(p, 4),
                         ratio=(round(p / m, 4) if m else None),
                         n_over_predicted=over, n_under_predicted=len(rows) - over,
                         direction=("over" if p > m else "under"),
                         within_tolerance=sum(1 for r in rows if r["delay"]["passed"]))
    return out


def run(trials: Sequence[tr.Trial], terms_path: Optional[Any] = None) -> Dict[str, Any]:
    models = _models(terms_path)
    out: Dict[str, Any] = dict(
        study="StudyPOL6-chain Part B",
        is_measurement=False,
        fit_set="StudyENG1e FIT, %d trials over 24 cells (2 modes x 4 loads x 3 actions)"
                % len(trials),
        in_sample=("IN-SAMPLE for the choice of pol6's one term: the hand-over window was "
                   "fitted on these same FIT cells. The one-shot on the ENG1e HOLDOUT is the "
                   "out-of-sample test and is NOT run here."),
        models={}, ceiling={}, criteria_table={}, regression_stop=None)
    for metric in METRICS:
        out["ceiling"][metric] = s0.ceiling_for_metric(trials, metric)
    for name, sim in models.items():
        out["models"][name] = {}
        for metric in METRICS:
            res = s0.evaluate(trials, sim, metric)
            c = res["criteria"]
            out["models"][name][metric] = dict(
                criterion_i=dict(n=c["delay_imposed_on_others"]["n"],
                                 fraction=c["delay_imposed_on_others"]["fraction"],
                                 verdict=c["delay_imposed_on_others"]["verdict"]),
                criterion_i_b=s0.criterion_i_b(c["delay_imposed_on_others"]["fraction"],
                                               out["ceiling"][metric]["ceiling"]),
                criterion_ii=dict(n_pairs_included=c["ranking"]["n_pairs_included"],
                                  n_agree=c["ranking"]["n_agree"],
                                  fraction=c["ranking"]["fraction"],
                                  verdict=c["ranking"]["verdict"]),
                criterion_iii=dict(n=c["job_completion_time"]["n"],
                                   median_abs_rel_error=c["job_completion_time"][
                                       "median_abs_rel_error"],
                                   verdict=c["job_completion_time"]["verdict"]),
                per_cell=per_cell_table(res))
    # criterion (iv): no ENG1e measurement, so T0's committed value stands
    out["criterion_iv"] = dict(
        applicable=False, value_stands=0.9718, source="StudyT0-fidelity on StudyENG1b",
        note="StudyENG1e measures per-step membership under load, not prefix survival, so (iv) "
             "has no ENG1e evidence and is neither re-run nor re-scored here.")
    # the regression gate
    gate = {}
    for metric in METRICS:
        a, b = out["models"]["pol4"][metric], out["models"]["pol6"][metric]
        gate[metric] = dict(
            criterion_ii=dict(pol4=a["criterion_ii"]["fraction"], pol6=b["criterion_ii"]["fraction"],
                              worse=bool(b["criterion_ii"]["fraction"] < a["criterion_ii"]["fraction"])),
            criterion_iii=dict(pol4=a["criterion_iii"]["median_abs_rel_error"],
                               pol6=b["criterion_iii"]["median_abs_rel_error"],
                               worse=bool((b["criterion_iii"]["median_abs_rel_error"] or 0)
                                          > (a["criterion_iii"]["median_abs_rel_error"] or 0))))
    fired = any(gate[m][k]["worse"] for m in METRICS for k in ("criterion_ii", "criterion_iii"))
    out["regression_stop"] = dict(
        fired=fired, detail=gate,
        rule="the brief's gate: pol6 must not be worse than pol4 on (ii) or (iii) on FIT",
        consequence=("pol6 is NOT frozen and pol4 remains the frozen and default model"
                     if fired else "the gate does not fire; pol6 may be frozen"))
    return out


def main(argv: Any = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eng1e-root", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.eng1e_root:
        er.ENG1E_ROOT = Path(a.eng1e_root)
    trials, audit = er.load_eng1e_trials("fit")
    res = run(trials)
    res["loader_audit"] = audit
    root = Path(__file__).resolve().parents[3]
    p = Path(a.out) if a.out else (root / OUT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1) + "\n")
    for name in ("pol4", "pol6"):
        for m in METRICS:
            d = res["models"][name][m]
            print("%-5s %-8s (i) %.4f  (i-b) %.4f %s  (ii) %.4f %s  (iii) %.4f %s"
                  % (name, m, d["criterion_i"]["fraction"], d["criterion_i_b"]["ratio"] or 0,
                     d["criterion_i_b"]["verdict"], d["criterion_ii"]["fraction"],
                     d["criterion_ii"]["verdict"], d["criterion_iii"]["median_abs_rel_error"],
                     d["criterion_iii"]["verdict"]))
    print("ceiling latency %.4f  ttft %.4f" % (res["ceiling"]["latency"]["ceiling"],
                                               res["ceiling"]["ttft"]["ceiling"]))
    print("REGRESSION STOP:", res["regression_stop"]["fired"])
    print("written to", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
