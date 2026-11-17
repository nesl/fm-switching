"""StudyT0b-fidelity, the ONE-SHOT runs on both held-out sets, scoring the frozen pol4 model.

Registered in the amended StudyT0b row (disclosed amendment of 2026-11-17, frozen before either
holdout was read, md5 927813b86a3c9b618b915e232ce44671 at 2026-11-17T19:06:23Z):

  model      pol4 exactly as frozen, the 12 md5s of results/orchestration/study_t0b/t0b_freeze.json
  data       the 120 StudyENG1c Part D HOLDOUT pairs AND the 60 StudyENG1d HOLDOUT pairs,
             scored and reported SEPARATELY and never pooled
  primary    the LATENCY sum (both sources record latency per background request); the TTFT sum
             is the secondary and is what compares to StudyT0's 0.586 and to StudyENG1d's own
             published numbers
  ceilings   each source's own FIT repeats: StudyENG1c's 72 repeat pairs, StudyENG1d's 36
  criteria   (i-b), (ii) and (iii) unchanged; (iv) is not scorable on either holdout and
             StudyT0's registered 0.9718 stands

EACH RUN IS ONE SHOT. `t0_harness.T0Harness.run_holdout_once` re-verifies every frozen md5, writes
a log line beside the result, and REFUSES a second run once the result file exists.

ONE DISCLOSED DEVIATION IN THE FREEZE CHECK. `FrozenState.verify` compares the git HEAD as well as
the md5s, and the recorded HEAD (4a9facb) no longer exists because a rebase rewrote it; the md5s
are the binding record, as recorded in `results/orchestration/study_t0b/t0b_freeze_erratum.json`.
The frozen state is therefore rebuilt with the CURRENT git state and the RECORDED md5s, so every
md5 is still checked, the run records the real HEAD, and nothing about the model is taken on
trust.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import eng1d_replay as e1d
from . import score_t0b as st
from . import trace_replay as tr
from .eng1_engine import make_sim
from .t0_harness import FrozenState, T0Harness, git_state

OUT_DIR = "results/orchestration/study_t0b"
FREEZE = "results/orchestration/study_t0b/t0b_freeze.json"
AUTHORIZATION = (
    "user ruling of 2026-11-17: 'PART B (StudyT0b one-shot on pol4) ... Run the one-shot once "
    "per holdout with the existing refusal mechanism.' Amended row frozen before any holdout "
    "read at 2026-11-17T19:06:23Z, md5 927813b86a3c9b618b915e232ce44671.")
SOURCES = ("eng1c", "eng1d")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def frozen_state() -> FrozenState:
    raw = json.loads((_root() / FREEZE).read_text())
    return FrozenState(repo=str(_root()), git=git_state(_root()), files=dict(raw["files"]),
                       frozen_at=raw["frozen_at"],
                       note=("git.head rebuilt from the working tree because the recorded sha "
                             "4a9facb was rewritten by a rebase; the md5s are the binding record "
                             "(t0b_freeze_erratum.json) and every one of them is still checked"))


def _ceiling(trials: Sequence[tr.Trial], metric: str) -> Dict[str, Any]:
    return st.ceiling_for_metric(trials, metric)


def score_source(source: str, authorization: str) -> Dict[str, Any]:
    """Build the holdout trials for one source and score every registered criterion on them."""
    if source == "eng1c":
        hold, audit = st.load_part_d_trials(split="holdout", authorization=authorization)
        fit, _ = st.load_part_d_trials(split="fit")
        residency = st.tier_inputs(hold)
    elif source == "eng1d":
        hold, audit = e1d.load_trials(split="holdout", authorization=authorization)
        fit, _ = e1d.load_trials(split="fit")
        residency = dict(note="StudyENG1d ran with no host tier, so tier at arrival does not "
                              "arise", n=len(hold))
    else:
        raise ValueError("unknown source %r" % source)
    sim = make_sim("pol4")
    out: Dict[str, Any] = dict(source=source, n_holdout_trials=len(hold),
                               n_fit_trials_for_ceiling=len(fit), holdout_audit=audit,
                               residency=residency, engine_model="pol4",
                               engine=sim.step.describe(),
                               pol4_terms=sim.pol4.describe() if sim.pol4 else "OFF")
    for metric in ("latency", "ttft"):
        res = st.evaluate(hold, sim, metric)
        ceil = _ceiling(fit, metric)
        crit = st.criteria_table(res, ceil, dict(class_accuracy=None, measured_class_counts=None,
                                                 degenerate=None,
                                                 verdict="NOT APPLICABLE on this holdout: "
                                                         "neither held-out set is an ENG1b-style "
                                                         "prefix-loss collection, so StudyT0's "
                                                         "registered (iv) of 0.9718 stands"))
        out[metric] = dict(
            role=("PRIMARY" if metric == "latency" else "SECONDARY"),
            criteria=crit,
            ceiling={k: v for k, v in ceil.items() if k != "rows"},
            cuts=st.per_cut_tables(res) if source == "eng1c" else dict(
                per_action=st.error_direction(res, lambda r: r["action"]),
                per_load=st.error_direction(res, lambda r: r["load"]),
                per_cell=st.error_direction(res, lambda r: r["cell"]),
                pooled=st.pooled_direction(res)),
            per_trial=[dict(key=r["key"], cell=r["cell"], measured_delay_s=r["measured_delay_s"],
                            predicted_delay_s=r["predicted_delay_s"], passed=r["delay"]["passed"],
                            ratio=r["delay"]["ratio"], completion_are=r["completion_are"])
                       for r in res["trials"]],
            ranking=dict(pairs=res["criteria"]["ranking"]["pairs"],
                         cell_medians_measured=res["criteria"]["ranking"]["cell_medians_measured"],
                         cell_medians_predicted=res["criteria"]["ranking"]["cell_medians_predicted"]))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=list(SOURCES) + ["all"], default="all")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out_dir = Path(args.out_dir) if args.out_dir else (_root() / OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = SOURCES if args.source == "all" else (args.source,)

    harness = T0Harness()
    frozen = frozen_state()
    v = frozen.verify()
    changed = [c["path"] for c in v["changed"]]
    print("freeze: %d files, %d changed %s" % (len(frozen.files), len(changed), changed))
    if changed:
        print("REFUSING: the frozen model has changed, so this would not be a test of it")
        return 2

    results = {}
    for source in sources:
        result_path = out_dir / ("t0b_holdout_%s.json" % source)
        log_path = out_dir / "t0b_one_shot.log"
        try:
            out = harness.run_holdout_once(
                frozen, result_path, log_path,
                compute=lambda s=source: score_source(s, AUTHORIZATION),
                split_name="holdout:%s" % source, authorization=AUTHORIZATION)
        except PermissionError as e:
            print("REFUSED for %s: %s" % (source, e))
            continue
        results[source] = out
        for metric in ("latency", "ttft"):
            c = out[metric]["criteria"]
            ib = c["i_b_repeatability_scaled"]
            print("%-6s %-8s (%s) (i) %.4f  ceiling %.4f  (i-b) ratio %s -> %s | (ii) %.4f %s | "
                  "(iii) %.4f %s"
                  % (source, metric, out[metric]["role"], c["i_delay_absolute"]["fraction"],
                     ib.get("ceiling") or float("nan"),
                     ("%.4f" % ib["ratio"]) if ib.get("ratio") is not None else "n/a",
                     ib.get("verdict"), c["ii_ranking"]["fraction"], c["ii_ranking"]["verdict"],
                     c["iii_completion"]["median_abs_rel_error"],
                     c["iii_completion"]["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
