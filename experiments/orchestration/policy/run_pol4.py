"""StudyPOL4-engine: re-score StudyT0's four criteria on the Part C FIT trials under the OLD
model and the NEW one, side by side, and report what the three new terms do to the policy's
piece-versus-monolithic preference.

NOTHING HERE TOUCHES THE HOLDOUT. The 174 Part C HOLDOUT triples are SPENT: this driver loads
`eng1_holdout_split.json` only to EXCLUDE them, asserts that the scored set contains zero holdout
trials and that the excluded count is exactly the split's size, and writes both counts into every
output file.

IN-SAMPLE LABELLING. The three new terms were fitted on StudyENG1 Parts A, B and D and on
StudyENG1b, never on Part C. The Part C FIT re-score is therefore OUT OF SAMPLE for the terms'
coefficients, but it is NOT a held-out test of the revised model: these 406 trials were already
used by StudyT0-fidelity for two implementation fixes and for the error attribution that chose
which three terms to add, so the CHOICE of terms is informed by them. Every output file and every
table carries that label. The only test of the revision is StudyT0b on fresh data.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import trace_replay as tr
from .eng1_engine import ENGINE_MODELS, EngineSim, Pol4Terms, StepModel, make_sim
from .run_t0 import (CLASS_ACC, COMPLETION_MARE, MIN_FRACTION, _dist, _q, delay_pass,
                     evaluate_eng1b, evaluate_part_c, negative_control, noise_against_criteria,
                     noise_by_cell)

IN_SAMPLE_LABEL = (
    "FIT TRIALS, NOT HELD OUT. The three StudyPOL4 terms were fitted on StudyENG1 Parts A, B "
    "and D and on StudyENG1b, so no coefficient saw a Part C trial; but these 406 FIT trials "
    "informed the ATTRIBUTION that chose which terms to add (reports/study_t0_fidelity.md "
    "section 11) and carried two earlier implementation fixes, so this re-score is IN-SAMPLE FOR "
    "THE CHOICE OF TERMS and is not a test of the revised model. StudyT0b on fresh data is.")

OUT_DIR = "results/orchestration/study_pol4"
RANK_ACTIONS = ("mono11k", "piece2048", "piece1024")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def split_fit_trials() -> Tuple[List[tr.Trial], Dict[str, Any]]:
    """Every Part C FIT trial, with the holdout exclusion ASSERTED rather than assumed."""
    trials = tr.load_part_c_trials()
    raw = json.loads((_root() / tr.HOLDOUT_SPLIT_PATH).read_text())
    keys = set()
    for cell, idx in raw["holdout"].items():
        load, action = cell.split("|")
        for i in idx:
            keys.add((load, action, int(i)))
    fit = [t for t in trials if not t.holdout]
    hold = [t for t in trials if t.holdout]
    leaked = [t.key() for t in fit if (t.load, t.action, t.trial) in keys]
    assert not leaked, "HOLDOUT LEAK: %s" % leaked[:5]
    assert len(hold) == len(keys), ("the split lists %d triples, the record flags %d"
                                   % (len(keys), len(hold)))
    missing = [k for k in keys if k not in {(t.load, t.action, t.trial) for t in hold}]
    assert not missing, "split triples not found in the record: %s" % missing[:5]
    audit = dict(
        n_part_c_trials=len(trials), n_fit_scored=len(fit), n_holdout_excluded=len(hold),
        n_holdout_in_split_file=len(keys), holdout_trials_used=0,
        assertions=["every scored trial's (load, action, trial) is absent from the split file",
                    "the number of excluded trials equals the split file's size",
                    "every triple in the split file is present in the record and excluded"],
        split_file=tr.HOLDOUT_SPLIT_PATH)
    return fit, audit


def noise_ceilings() -> Dict[str, Any]:
    """StudyT0-fidelity section 11's `noise` column: criterion (i) applied to two independent
    measurements of the same trial, per action and per load. Every repeat is a FIT trial."""
    nac = noise_against_criteria()
    per_action: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    per_load: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in nac["rows"]:
        load, action = r["cell"].split("|")
        per_action[action].append(r)
        per_load[load].append(r)

    def _f(d):
        return {k: dict(n=len(v), n_passed=sum(1 for r in v if r["check"]["passed"]),
                        ceiling=sum(1 for r in v if r["check"]["passed"]) / len(v))
                for k, v in sorted(d.items())}
    return dict(pooled=dict(n=nac["n"], n_passed=nac["n_passed"], ceiling=nac["fraction"]),
                per_action=_f(per_action), per_load=_f(per_load),
                definition=nac["note"])


def error_direction(res: Dict[str, Any], keyfn) -> Dict[str, Any]:
    """StudyT0-fidelity section 11's own table: per cut, the model's pass fraction, the medians,
    the median SIGNED error (positive is over-prediction), the median ratio and the share of
    trials over-predicted."""
    usable = [r for r in res["trials"] if r["reconstructible"]]
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in usable:
        groups[keyfn(r)].append(r)
    out = {}
    for k, rs in sorted(groups.items()):
        ms = [r["measured_delay_s"] for r in rs]
        ps = [r["predicted_delay_s"] for r in rs]
        sg = [p - m for p, m in zip(ps, ms)]
        ratios = [p / m for p, m in zip(ps, ms) if m != 0]
        # StudyT0-fidelity section 11's `med_ratio` column is the median of the ratio of
        # MAGNITUDES, which is the only ratio defined when a per-trial sum changes sign; the
        # signed ratio is reported beside it because the two differ in exactly the cells where
        # the measurement crosses zero.
        ratios_abs = [abs(p) / abs(m) for p, m in zip(ps, ms) if m != 0]
        ar = [r["completion_are"] for r in rs if r["completion_are"] is not None]
        out[k] = dict(
            n=len(rs),
            model_pass_i=sum(1 for r in rs if r["delay"]["passed"]) / len(rs),
            measured_p50=statistics.median(ms), predicted_p50=statistics.median(ps),
            med_signed_s=statistics.median(sg),
            med_ratio_signed=(statistics.median(ratios) if ratios else None),
            med_ratio=(statistics.median(ratios_abs) if ratios_abs else None),
            frac_over_predicted=sum(1 for s in sg if s > 0) / len(rs),
            completion_median_are=(statistics.median(ar) if ar else None),
            measured=_dist(ms), predicted=_dist(ps))
    return out


def pooled_direction(res: Dict[str, Any]) -> Dict[str, Any]:
    usable = [r for r in res["trials"] if r["reconstructible"]]
    sg = [r["predicted_delay_s"] - r["measured_delay_s"] for r in usable]
    fails = [r for r in usable if not r["delay"]["passed"]]
    fsg = [r["predicted_delay_s"] - r["measured_delay_s"] for r in fails]
    return dict(n=len(usable), n_over=sum(1 for s in sg if s > 0),
                frac_over=sum(1 for s in sg if s > 0) / len(usable),
                med_signed_s=statistics.median(sg),
                n_failures=len(fails),
                failures_over=sum(1 for s in fsg if s > 0),
                failures_under=sum(1 for s in fsg if s <= 0),
                frac_failures_over=(sum(1 for s in fsg if s > 0) / len(fails)) if fails else None)


def ranking_piece_vs_mono(res_old: Dict[str, Any], res_new: Dict[str, Any]) -> Dict[str, Any]:
    """The policy's preference, as the predicted ordering of the three reconstruction actions
    within each background condition: cheapest imposed delay first."""
    def medians(res: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        acc: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for r in res["trials"]:
            if not r["reconstructible"] or r["action"] not in RANK_ACTIONS:
                continue
            acc[r["load"]][r["action"]].append(r["predicted_delay_s"])
        return {load: {a: statistics.median(v) for a, v in d.items()}
                for load, d in acc.items()}

    def measured(res: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        acc: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for r in res["trials"]:
            if not r["reconstructible"] or r["action"] not in RANK_ACTIONS:
                continue
            acc[r["load"]][r["action"]].append(r["measured_delay_s"])
        return {load: {a: statistics.median(v) for a, v in d.items()}
                for load, d in acc.items()}
    mo, mn, mm = medians(res_old), medians(res_new), measured(res_old)
    rows = []
    for load in sorted(set(mo) | set(mn)):
        def order(d: Dict[str, float]) -> List[str]:
            return [a for a, _ in sorted(d.get(load, {}).items(), key=lambda kv: kv[1])]
        o_old, o_new, o_meas = order(mo), order(mn), order(mm)
        rows.append(dict(
            load=load,
            predicted_order_old=o_old, predicted_order_new=o_new, measured_order=o_meas,
            old_matches_measured=(o_old == o_meas), new_matches_measured=(o_new == o_meas),
            order_changed=(o_old != o_new),
            predicted_medians_old={a: mo.get(load, {}).get(a) for a in RANK_ACTIONS},
            predicted_medians_new={a: mn.get(load, {}).get(a) for a in RANK_ACTIONS},
            measured_medians={a: mm.get(load, {}).get(a) for a in RANK_ACTIONS}))
    return dict(
        actions=list(RANK_ACTIONS), per_condition=rows,
        n_conditions=len(rows),
        n_order_changed=sum(1 for r in rows if r["order_changed"]),
        n_old_correct=sum(1 for r in rows if r["old_matches_measured"]),
        n_new_correct=sum(1 for r in rows if r["new_matches_measured"]),
        definition="the ordering is by PREDICTED total imposed delay on the episodic background "
                   "stream, cell median over the FIT trials of that condition, cheapest first; "
                   "the measured ordering is the same statistic on the measurement",
        in_sample=IN_SAMPLE_LABEL)


def term_ablation(trials: Sequence[tr.Trial], cell_actions: Sequence[str],
                  load: str = "P40") -> Dict[str, Any]:
    """CLAUDE.md mechanism verification Step 4, one control per new term.

    Each term is switched to its NEUTRAL value one at a time and the predicted imposed delay is
    compared against the old model's. A term that is really driving a cell's change must make
    that cell collapse back to the old prediction when it alone is disabled, and must be the only
    term that does. Run on one representative load; the cell is recorded."""
    full = Pol4Terms.load()
    terms = {
        "host_kv_transfer": dict(host_kv_bytes_per_token=0.0, host_kv_lookup_fixed_ms=0.0),
        "long_cold_prefill": dict(long_prefill_scale_intercept=1.0,
                                  long_prefill_scale_per_1k_tokens=0.0),
        "sub_linear_batching": dict(batch_prefill_gain_exponent=0.0),
    }
    sims = {"eng1": EngineSim(step=StepModel.load()),
            "pol4": EngineSim(step=StepModel.load(), pol4=full)}
    for name, neutral in terms.items():
        coef = dict(full.coef)
        coef.update(neutral)
        sims["pol4_without_" + name] = EngineSim(
            step=StepModel.load(),
            pol4=Pol4Terms(coef=coef, path="%s with %s neutralised" % (full.path, name),
                           raw=dict(ablation=name)))
        sims["only_" + name] = EngineSim(
            step=StepModel.load(),
            pol4=Pol4Terms.for_probe(**{k: v for k, v in full.coef.items()
                                        if k in _term_coefs(name)}))
    rows: Dict[str, Dict[str, Any]] = {}
    for action in cell_actions:
        sel = [t for t in trials if t.load == load and t.action == action]
        if not sel:
            continue
        per = {}
        for label, sim in sims.items():
            per[label] = statistics.median([tr.predict_trial(t, sim)["predicted_delay_s"]
                                            for t in sel])
        meas = statistics.median([tr.measured_imposed_delay_s(t)["total_s"] for t in sel])
        collapsed = {}
        for name in terms:
            d_full = per["pol4"] - per["eng1"]
            d_off = per["pol4_without_" + name] - per["eng1"]
            collapsed[name] = dict(
                change_with_all_terms_s=d_full, change_with_this_term_off_s=d_off,
                share_of_change_from_this_term=((d_full - d_off) / d_full) if d_full else None,
                only_this_term_s=per["only_" + name] - per["eng1"])
        rows[action] = dict(n=len(sel), measured_p50_s=meas, predicted_p50_s=per,
                            attribution=collapsed)
    return dict(control_cell="load %s, FIT trials only, actions %s"
                             % (load, list(cell_actions)),
                per_action=rows,
                rule="a term that drives a cell must account for essentially all of that "
                     "cell's change when it alone is disabled; if disabling it changes nothing, "
                     "it is not what moved the cell")


def _term_coefs(name: str) -> Sequence[str]:
    return {
        "host_kv_transfer": ("host_kv_bytes_per_token", "host_kv_transfer_gb_per_s",
                             "host_kv_lookup_fixed_ms"),
        "long_cold_prefill": ("long_prefill_scale_intercept",
                              "long_prefill_scale_per_1k_tokens"),
        "sub_linear_batching": ("batch_prefill_gain_exponent",),
    }[name]


def criteria_table(res: Dict[str, Any], eng1b: Dict[str, Any]) -> Dict[str, Any]:
    c = res["criteria"]
    return dict(
        i_delay=dict(fraction=c["delay_imposed_on_others"]["fraction"],
                     n_passed=c["delay_imposed_on_others"]["n_passed"],
                     n=c["delay_imposed_on_others"]["n"],
                     threshold=MIN_FRACTION,
                     verdict=c["delay_imposed_on_others"]["verdict"]),
        ii_ranking=dict(fraction=c["ranking"]["fraction"], n_agree=c["ranking"]["n_agree"],
                        n_pairs_included=c["ranking"]["n_pairs_included"],
                        threshold=MIN_FRACTION, verdict=c["ranking"]["verdict"]),
        iii_completion=dict(median_abs_rel_error=c["job_completion_time"]
                            ["median_abs_rel_error"],
                            n=c["job_completion_time"]["n"], threshold=COMPLETION_MARE,
                            verdict=c["job_completion_time"]["verdict"]),
        iv_prefix_loss=dict(class_accuracy=eng1b["class_accuracy"], n=eng1b["n"],
                            mae_fraction_lost=eng1b["mae_fraction_lost"],
                            threshold=CLASS_ACC, verdict=eng1b["verdict"]))


def regression_check(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """The brief's decisive STOP AND ASK: if (ii), (iii) or (iv) got WORSE on FIT data, stop."""
    rows = []
    rows.append(dict(criterion="ii_ranking", higher_is_better=True,
                     old=old["ii_ranking"]["fraction"], new=new["ii_ranking"]["fraction"]))
    rows.append(dict(criterion="iii_completion", higher_is_better=False,
                     old=old["iii_completion"]["median_abs_rel_error"],
                     new=new["iii_completion"]["median_abs_rel_error"]))
    rows.append(dict(criterion="iv_prefix_loss", higher_is_better=True,
                     old=old["iv_prefix_loss"]["class_accuracy"],
                     new=new["iv_prefix_loss"]["class_accuracy"]))
    for r in rows:
        d = r["new"] - r["old"]
        r["delta"] = d
        r["worse"] = bool(d < 0) if r["higher_is_better"] else bool(d > 0)
        r["verdict_changed"] = None
    worse = [r["criterion"] for r in rows if r["worse"]]
    return dict(rows=rows, any_worse=bool(worse), worse=worse,
                stop_and_ask_triggered=bool(worse),
                rule="the brief stops the row rather than trading a win on (i) for a regression "
                     "on (ii), (iii) or (iv) on FIT data")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--models", default="eng1,pol4,pol4_nobatch")
    ap.add_argument("--mode", default="rescore", choices=["rescore", "control"])
    args = ap.parse_args(list(argv) if argv is not None else None)
    root = _root()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in models:
        if m not in ENGINE_MODELS:
            raise SystemExit("unknown engine model %r" % m)
    fit, audit = split_fit_trials()
    sys.path.insert(0, str(root / "experiments/lib"))
    from _provenance import stamp
    if args.mode == "control":
        res = term_ablation(fit, ("hostreload", "mono11k", "burst4", "piece2048"))
        res["holdout_audit"] = audit
        res["in_sample"] = IN_SAMPLE_LABEL
        res["_provenance"] = stamp(script="policy/run_pol4.py --mode control", model=None,
                                   device="cpu", n=len(fit), args=args)
        (out_dir / "pol4_term_ablation.json").write_text(json.dumps(res, indent=1, default=str))
        for a, r in res["per_action"].items():
            print("%-11s measured %.4f | eng1 %.4f | pol4 %.4f"
                  % (a, r["measured_p50_s"], r["predicted_p50_s"]["eng1"],
                     r["predicted_p50_s"]["pol4"]))
            for name, d in r["attribution"].items():
                print("    %-20s off -> %.4f (share of change %s)"
                      % (name, r["predicted_p50_s"]["pol4_without_" + name],
                         ("%.3f" % d["share_of_change_from_this_term"])
                         if d["share_of_change_from_this_term"] is not None else "n/a"))
        return 0
    noise = noise_by_cell(fit)

    scored: Dict[str, Dict[str, Any]] = {}
    crit: Dict[str, Dict[str, Any]] = {}
    for m in models:
        sim = make_sim(m)
        res = evaluate_part_c(fit, sim, noise=noise)
        b = evaluate_eng1b()
        res["engine_model"] = m
        res["engine"] = sim.step.describe()
        res["pol4_terms"] = (sim.pol4.describe() if sim.pol4 is not None else "OFF")
        res["holdout_audit"] = audit
        res["split"] = "Part C FIT trials. %s" % IN_SAMPLE_LABEL
        res["per_action_direction"] = error_direction(res, lambda r: r["action"])
        res["per_load_direction"] = error_direction(res, lambda r: r["load"])
        res["pooled_direction"] = pooled_direction(res)
        res["eng1b"] = {k: v for k, v in b.items() if k != "trials"}
        res["_provenance"] = stamp(script="policy/run_pol4.py", model=None, device="cpu",
                                   n=res["n_usable"], args=args)
        (out_dir / ("pol4_fit_rescore_%s.json" % m)).write_text(
            json.dumps(res, indent=1, default=str))
        scored[m] = res
        crit[m] = criteria_table(res, b)
        print("%-5s (i) %.4f  (ii) %.4f  (iii) %.4f  (iv) %.4f"
              % (m, crit[m]["i_delay"]["fraction"], crit[m]["ii_ranking"]["fraction"],
                 crit[m]["iii_completion"]["median_abs_rel_error"],
                 crit[m]["iv_prefix_loss"]["class_accuracy"]))
    if "eng1" in scored and "pol4" in scored:
        comp = dict(
            in_sample=IN_SAMPLE_LABEL, holdout_audit=audit,
            criteria_old=crit["eng1"], criteria_new=crit["pol4"],
            criteria_all={m: crit[m] for m in crit},
            regression_check=regression_check(crit["eng1"], crit["pol4"]),
            regression_check_nobatch=(regression_check(crit["eng1"], crit["pol4_nobatch"])
                                      if "pol4_nobatch" in crit else None),
            per_action={m: scored[m]["per_action_direction"] for m in scored},
            per_load={m: scored[m]["per_load_direction"] for m in scored},
            pooled_direction={m: scored[m]["pooled_direction"] for m in scored},
            noise_ceilings=noise_ceilings(),
            piece_vs_monolithic=ranking_piece_vs_mono(scored["eng1"], scored["pol4"]),
            pol4_terms=Pol4Terms.load().describe())
        comp["_provenance"] = stamp(script="policy/run_pol4.py", model=None, device="cpu",
                                    n=scored["eng1"]["n_usable"], args=args)
        (out_dir / "pol4_old_vs_new.json").write_text(json.dumps(comp, indent=1, default=str))
        rc = comp["regression_check"]
        print("regression on (ii)-(iv): %s %s" % (rc["any_worse"], rc["worse"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
