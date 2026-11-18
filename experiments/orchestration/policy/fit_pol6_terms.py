"""Fit StudyPOL6's one Part B term on StudyENG1e FIT: the piece hand-over window.

WHAT IS FITTED AND WHY ONLY THIS. StudyENG1e-chain settles the three candidates StudyPOL6 Part A
could only separate by subtraction:

  (a) STEP GRANULARITY: not an error. The engine runs every piece in exactly ONE step (median
      and max 1.0 steps per piece in all 16 chain cells) and pol4 already models one step. Part
      A's derived 1.75 and 1.92 steps per piece were an artifact of deriving step composition by
      subtracting the action's own tokens on StudyENG1c, which StudyENG1e can do directly.
  (b) IN-STEP MERGING: real but not the error, and forbidding it makes FIT WORSE. The engine's
      median other-prefill share inside a piece step is 0.000 in 13 of 16 cells; pol4 merges
      somewhat more in the typical step. A structural rule that refuses to batch a piece with
      background prefill was implemented and REJECTED on FIT (chain ratio 1.636 to 1.897),
      because refusing to batch lengthens the chain and delays everything behind it.
  (c) ENCODER BUDGET: not an error. StudyENG1e's own encoder check passed in every cell (every
      piece's encoder inputs equal its new frames after the setup flush), so there is no
      mismatch for a term to correct.

What is left, and what this module fits, is the HAND-OVER WINDOW: the time from a piece
completing to the NEXT piece's first engine step. StudyENG1e measures it as `gaps.fe_next_s`
and pol4 charges only its body-size front end, which for a chained piece of uuid references is
29.9 ms against a measured 99 to 231 ms. pol4 therefore hands the next piece to the engine far
too early, and the background work the engine would have served in that gap is instead charged
the piece's step. One coefficient, two injection modes by body size, two measured piece sizes.

FIT SET. StudyENG1e FIT only (15 of 20 trials per cell; the 5 HOLDOUT trials per (load, action)
are never read, which `eng1e_replay` enforces). Every number here is IN-SAMPLE for the choice of
this term and is labelled so wherever it is reported.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path
from typing import Any, Dict, Optional

from . import eng1e_replay as er

TERMS_PATH = "results/orchestration/study_pol6/pol6_terms.json"
# StudyENG1e injection modes, by what a piece's body actually carries (decision-time computable)
MODE_KIND = {"B": "refs", "A": "bytes"}
ACTION_TOKENS = {"chain1024": 1024, "chain2048": 2048}


def fit(results_path: Optional[Any] = None) -> Dict[str, Any]:
    """The measured hand-over window per (body kind, piece size), median over loads."""
    p = Path(results_path) if results_path else er.eng1e_path(er.ENG1E_RESULTS)
    R = json.loads(Path(p).read_text())
    cells = R["cells_cpu_ok"]
    acc: Dict[str, Dict[str, list]] = {}
    detail = []
    for key, c in sorted(cells.items()):
        mode, load, action = key.split("|")
        if action not in ACTION_TOKENS:
            continue
        kind = MODE_KIND[mode]
        tok = str(ACTION_TOKENS[action])
        fe = c["gaps"]["fe_next_s"]["median"]
        acc.setdefault(kind, {}).setdefault(tok, []).append(fe)
        detail.append(dict(cell=key, kind=kind, piece_tokens=int(tok), load=load,
                           fe_next_s_median=fe, n_gaps=c["gaps"]["n"],
                           turnaround_s_median=c["gaps"]["turnaround_s"]["median"],
                           gap_s_median=c["gaps"]["dur_s"]["median"]))
    coef = {k: {t: round(st.median(v), 6) for t, v in sorted(d.items())}
            for k, d in sorted(acc.items())}
    spread = {"%s|%s" % (k, t): dict(min=round(min(v), 6), max=round(max(v), 6),
                                     median=round(st.median(v), 6), n_loads=len(v))
              for k, d in sorted(acc.items()) for t, v in sorted(d.items())}
    return dict(piece_handover_s=coef, per_cell=detail, spread_over_loads=spread,
                source=str(p), provenance=er.file_provenance([p]))


def write_terms(fitted: Dict[str, Any], terms_path: Optional[Any] = None,
                root: Optional[Path] = None) -> Dict[str, Any]:
    """Add the fitted coefficient to the committed terms file, keeping Part A's record intact."""
    r = Path(root) if root else Path(__file__).resolve().parents[3]
    p = Path(terms_path) if terms_path else (r / TERMS_PATH)
    raw = json.loads(p.read_text())
    if int(raw.get("holdout_trials_used", -1)) != 0:
        raise ValueError("%s does not state that it used zero HOLDOUT trials" % p)
    raw["coef"] = dict(piece_handover_s=fitted["piece_handover_s"])
    raw["coef_note"] = (
        "ONE fitted coefficient, StudyPOL6 Part B: the measured piece hand-over window "
        "(StudyENG1e `gaps.fe_next_s`), per body kind (bytes or uuid references, decided by the "
        "piece's own body size) and per measured piece size. IN-SAMPLE for the choice of this "
        "term. The window is LOAD-DEPENDENT in the measurement and a load-independent median is "
        "fitted on purpose: the load-varying part is the endogenous wait for dispatch behind "
        "background steps, which a step-level simulator must produce itself, and a per-load "
        "coefficient would encode a background arrival rate the policy does not know when it "
        "decides. The spread over loads is recorded in partB.fit.spread_over_loads.")
    raw["partB"] = dict(
        study="StudyPOL6-chain Part B",
        fit_set="StudyENG1e FIT only, 15 of 20 trials per cell, both injection modes",
        holdout_trials_used=0,
        rejected_on_fit=[
            dict(rule="step_granularity",
                 reason="not an error: the engine runs every piece in ONE step, median and max "
                        "1.0 in all 16 chain cells, which is what pol4 already does"),
            dict(rule="in_step_merge",
                 reason="implemented and rejected: forbidding a piece to share its step with "
                        "background prefill moved the chain ratio from 1.636 to 1.897 on FIT"),
            dict(rule="encoder_budget",
                 reason="not an error: StudyENG1e's encoder check passed in every cell"),
        ],
        fit=fitted)
    p.write_text(json.dumps(raw, indent=1) + "\n")
    return raw


def main(argv: Any = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eng1e-root", default=None,
                    help="read StudyENG1e from this root instead of the repo")
    ap.add_argument("--write", action="store_true", help="write the terms file")
    a = ap.parse_args(argv)
    if a.eng1e_root:
        er.ENG1E_ROOT = Path(a.eng1e_root)
    f = fit()
    print(json.dumps(dict(piece_handover_s=f["piece_handover_s"],
                          spread_over_loads=f["spread_over_loads"]), indent=1))
    if a.write:
        write_terms(f)
        print("written to %s" % TERMS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
