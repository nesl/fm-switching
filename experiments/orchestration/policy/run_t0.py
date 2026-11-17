"""StudyT0-fidelity: the driver for approval test T0.

Modes:
  dryrun     StudyENG1 Part C FIT trials. Out of sample for the step model (fitted on Part A and
             Part B E0 only) and NOT the held-out split, so it may be run as often as needed and
             implementation bugs found here may be fixed.
  control    the negative control of CLAUDE.md's mechanism verification Step 4.
  eng1b      all 852 StudyENG1b trials, mechanistic prediction only.
  holdout    the ONE authorized run on the 174 held-out Part C triples, through
             `t0_harness.T0Harness.run_holdout_once`, which requires the frozen hashes, logs the
             run and refuses a second one.

The PRE-REGISTERED pass criteria are in `CRITERIA` and are evaluated exactly as written. The
criteria were fixed before any result was computed; the frozen pre-registration text is recorded
in the session scratchpad and reproduced in reports/study_t0_fidelity.md.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import trace_replay as tr
from .eng1_engine import EngineSim, StepModel, KV_POOL_TOKENS_H100NVL
from .t0_harness import FrozenState, T0Harness

CRITERIA = {
    "delay_imposed_on_others": (
        "prediction within 1.5x of measured, or within 0.1 s absolute for small values, for at "
        "least 90 % of HOLDOUT triples"),
    "ranking": (
        "within each background condition, the predicted ordering of actions matches the "
        "measured ordering for at least 90 % of action pairs whose measured values differ by "
        "more than 2x"),
    "job_completion_time": "median absolute relative error at most 20 %",
    "eng1b_prefix_loss": (
        "none/partial/total class correct for at least 90 % of trials; also report MAE of "
        "fraction lost"),
}

DELAY_RATIO = 1.5
DELAY_ABS_S = 0.1
RANK_RATIO = 2.0
COMPLETION_MARE = 0.20
CLASS_ACC = 0.90
MIN_FRACTION = 0.90

# Files whose exact bytes decide the prediction. Frozen before the holdout run.
FROZEN_FILES = [
    "results/cost/study_eng1/eng1_step_model.json",
    "experiments/orchestration/policy/eng1_engine.py",
    "experiments/orchestration/policy/trace_replay.py",
    "experiments/orchestration/policy/kvpool.py",
    "experiments/orchestration/policy/tiers.py",
    "experiments/orchestration/policy/params.py",
    "experiments/orchestration/policy/t0_harness.py",
    "experiments/orchestration/policy/run_t0.py",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _q(xs: Sequence[float], p: float) -> float:
    ys = sorted(xs)
    if not ys:
        return float("nan")
    pos = (len(ys) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] * (1 - (pos - lo)) + ys[hi] * (pos - lo)


def _dist(xs: Sequence[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    return dict(n=len(xs), min=min(xs), p10=_q(xs, 0.10), p50=_q(xs, 0.50), p90=_q(xs, 0.90),
                max=max(xs), mean=statistics.fmean(xs))


def delay_pass(pred: float, meas: float) -> Dict[str, Any]:
    """Criterion (i), exactly as pre-registered: within 1.5x of measured, OR within 0.1 s
    absolute for small values."""
    abs_ok = abs(pred - meas) <= DELAY_ABS_S
    ratio = None
    ratio_ok = False
    if pred * meas > 0:
        hi, lo = max(abs(pred), abs(meas)), min(abs(pred), abs(meas))
        ratio = hi / lo if lo > 0 else float("inf")
        ratio_ok = ratio <= DELAY_RATIO
    return dict(passed=bool(abs_ok or ratio_ok), within_abs=bool(abs_ok),
                within_ratio=bool(ratio_ok), ratio=ratio,
                abs_error_s=abs(pred - meas))


def noise_by_cell(trials: Sequence[tr.Trial], path: Any = None) -> Dict[str, Any]:
    """StudyENG1's own measurement noise: the INDEPENDENT REPEAT of the without-run.

    For each repeat the same quantity the experiment reports is computed between the repeat and
    the original without-run, so the number is directly comparable to an imposed delay. Every
    repeat is a FIT trial, so reading them does not touch the holdout."""
    p = Path(path) if path is not None else (_repo_root() / tr.PART_C_PATH)
    rep: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    base: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    with open(p) as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("kind") not in tr.COMPARED_KINDS:
                continue
            k = (row["load"], row["action"], int(row["trial"]))
            if row.get("mode") == "repeat":
                rep[k].append(row)
            elif row.get("mode") == "without":
                base[k].append(row)
    per_cell: Dict[str, List[float]] = defaultdict(list)
    for k, rows in sorted(rep.items()):
        if k not in base:
            continue
        a = {tr._bg_key(r): r for r in rows}
        b = {tr._bg_key(r): r for r in base[k]}
        tot = 0.0
        n = 0
        for key in set(a) & set(b):
            x, y = a[key].get("ttft_s"), b[key].get("ttft_s")
            if x is None or y is None:
                continue
            tot += float(x) - float(y)
            n += 1
        if n:
            per_cell["%s|%s" % (k[0], k[1])].append(abs(tot))
    return dict(per_cell={c: _dist(v) for c, v in sorted(per_cell.items())},
                pooled=_dist([x for v in per_cell.values() for x in v]),
                definition="|sum over matched background requests of TTFT(independent repeat of "
                           "the without-run) - TTFT(without)|, the same quantity the experiment "
                           "reports as the imposed delay",
                n_repeats=sum(len(v) for v in per_cell.values()))


def noise_against_criteria(path: Any = None) -> Dict[str, Any]:
    """What the PRE-REGISTERED criteria would score on the MEASUREMENT ITSELF.

    StudyENG1 ran an independent repeat of the without-run for 87 FIT trials. For each of those
    the imposed delay can be computed two ways that differ only by measurement noise:
    sum(with - without) and sum(with - repeat). Applying criterion (i) to that pair gives the
    fraction the criterion could reach from measurement reproducibility alone, which is the
    ceiling any prediction can hit. The same pair gives the ceiling for criterion (iii) through
    the action's own completion time, which was measured once per arm and has no repeat, so that
    one is reported as NOT AVAILABLE rather than estimated.

    Every trial used here is FIT; no holdout datum is touched."""
    p = Path(path) if path is not None else (_repo_root() / tr.PART_C_PATH)
    buckets: Dict[Tuple[str, str, int], Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list))
    with open(p) as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("kind") not in tr.COMPARED_KINDS:
                continue
            m = row.get("mode")
            if m not in ("with", "without", "repeat"):
                continue
            buckets[(row["load"], row["action"], int(row["trial"]))][m].append(row)
    rows = []
    for k, arms in sorted(buckets.items()):
        if not (arms.get("repeat") and arms.get("without") and arms.get("with")):
            continue
        def _sum(a: str, b: str) -> Optional[float]:
            x = {tr._bg_key(r): r for r in arms[a]}
            y = {tr._bg_key(r): r for r in arms[b]}
            tot, n = 0.0, 0
            for key in set(x) & set(y):
                u, v = x[key].get("ttft_s"), y[key].get("ttft_s")
                if u is None or v is None:
                    continue
                tot += float(u) - float(v)
                n += 1
            return tot if n else None
        a = _sum("with", "without")
        b = _sum("with", "repeat")
        if a is None or b is None:
            continue
        rows.append(dict(cell="%s|%s" % (k[0], k[1]), trial=k[2], measured_a_s=a,
                         measured_b_s=b, check=delay_pass(b, a)))
    passed = [r for r in rows if r["check"]["passed"]]
    frac = len(passed) / len(rows) if rows else 0.0
    per_cell: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_cell[r["cell"]].append(r)
    return dict(
        n=len(rows), n_passed=len(passed), fraction=frac, threshold=MIN_FRACTION,
        criterion_i_noise_ceiling_verdict=("PASS" if frac >= MIN_FRACTION else "FAIL"),
        would_noise_alone_fail_criterion_i=bool(frac < MIN_FRACTION),
        criterion_iii_noise="NOT AVAILABLE: the action's own completion time was measured once "
                            "per arm and StudyENG1 ran no repeat of the with-arm, so there is no "
                            "repeat-based noise estimate for criterion (iii)",
        criterion_ii_noise="the ranking criterion is evaluated on per-cell MEDIANS over trials, "
                           "so the relevant noise is the median's, not a single trial's; the "
                           "per-cell repeat spread is reported in `noise`",
        per_cell={c: dict(n=len(v), n_passed=sum(1 for r in v if r["check"]["passed"]),
                          fraction=sum(1 for r in v if r["check"]["passed"]) / len(v))
                  for c, v in sorted(per_cell.items())},
        rows=rows,
        note="the two measurements differ ONLY by run-to-run noise, so a pair that fails "
             "criterion (i) is a pair the criterion would reject even from a perfect prediction")


def evaluate_part_c(trials: Sequence[tr.Trial], sim: EngineSim,
                    noise: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for t in trials:
        setup = tr.setup_overlap_report(t)
        m = tr.measured_imposed_delay_s(t)
        pr = tr.predict_trial(t, sim)
        mc = tr.measured_action_completion_s(t)
        pc = pr["predicted_action_completion_s"]
        rows.append(dict(
            key=t.key(), load=t.load, action=t.action, trial=t.trial, cell=t.cell(),
            reconstructible=bool(setup["ok"] and m["n_matched"] > 0),
            setup=setup, n_matched_measured=m["n_matched"], n_matched_predicted=pr["n_matched"],
            measured_delay_s=m["total_s"], predicted_delay_s=pr["predicted_delay_s"],
            measured_completion_s=mc, predicted_completion_s=pc,
            delay=delay_pass(pr["predicted_delay_s"], m["total_s"]),
            completion_are=(abs(pc - mc) / mc if (mc and pc is not None and mc > 0) else None),
            unfinished=pr["unfinished"]))
    usable = [r for r in rows if r["reconstructible"]]
    # ---- criterion (i)
    dp = [r for r in usable if r["delay"]["passed"]]
    frac = len(dp) / len(usable) if usable else 0.0
    crit_i = dict(criterion=CRITERIA["delay_imposed_on_others"], n=len(usable),
                  n_passed=len(dp), fraction=frac, threshold=MIN_FRACTION,
                  verdict=("PASS" if frac >= MIN_FRACTION else "FAIL"))
    # ---- criterion (ii): per background condition, action pairs differing by more than 2x
    by_cell_m: Dict[str, List[float]] = defaultdict(list)
    by_cell_p: Dict[str, List[float]] = defaultdict(list)
    for r in usable:
        by_cell_m[r["cell"]].append(r["measured_delay_s"])
        by_cell_p[r["cell"]].append(r["predicted_delay_s"])
    med_m = {c: statistics.median(v) for c, v in by_cell_m.items()}
    med_p = {c: statistics.median(v) for c, v in by_cell_p.items()}
    loads = sorted({c.split("|")[0] for c in med_m})
    pairs: List[Dict[str, Any]] = []
    for load in loads:
        acts = sorted(c.split("|")[1] for c in med_m if c.startswith(load + "|"))
        for i in range(len(acts)):
            for j in range(i + 1, len(acts)):
                a, b = acts[i], acts[j]
                ma, mb = med_m["%s|%s" % (load, a)], med_m["%s|%s" % (load, b)]
                pa, pb = med_p["%s|%s" % (load, a)], med_p["%s|%s" % (load, b)]
                lo, hi = min(abs(ma), abs(mb)), max(abs(ma), abs(mb))
                if lo <= 0 or hi / lo <= RANK_RATIO:
                    pairs.append(dict(load=load, a=a, b=b, measured_ratio=(hi / lo if lo > 0
                                                                           else None),
                                      included=False))
                    continue
                agree = (ma > mb) == (pa > pb)
                pairs.append(dict(load=load, a=a, b=b, measured_ratio=hi / lo, included=True,
                                  measured=[ma, mb], predicted=[pa, pb], agree=bool(agree)))
    inc = [p for p in pairs if p["included"]]
    agree_frac = (sum(1 for p in inc if p["agree"]) / len(inc)) if inc else 0.0
    crit_ii = dict(criterion=CRITERIA["ranking"], n_pairs_total=len(pairs),
                   n_pairs_included=len(inc),
                   n_agree=sum(1 for p in inc if p["agree"]), fraction=agree_frac,
                   threshold=MIN_FRACTION,
                   verdict=("PASS" if inc and agree_frac >= MIN_FRACTION else
                            ("FAIL" if inc else "NOT COMPUTABLE: no action pair differs by more "
                                               "than 2x")),
                   pairs=pairs, cell_medians_measured=med_m, cell_medians_predicted=med_p)
    # ---- criterion (iii)
    ares = [r["completion_are"] for r in usable if r["completion_are"] is not None]
    mare = statistics.median(ares) if ares else float("nan")
    crit_iii = dict(criterion=CRITERIA["job_completion_time"], n=len(ares),
                    median_abs_rel_error=mare, threshold=COMPLETION_MARE,
                    verdict=("PASS" if ares and mare <= COMPLETION_MARE else "FAIL"))
    # ---- per load and per action, as the brief requires
    def _tab(keyfn):
        out = {}
        for r in usable:
            out.setdefault(keyfn(r), []).append(r)
        tab = {}
        for k, rs in sorted(out.items()):
            ms = [x["measured_delay_s"] for x in rs]
            ps = [x["predicted_delay_s"] for x in rs]
            ar = [x["completion_are"] for x in rs if x["completion_are"] is not None]
            tab[k] = dict(n=len(rs), measured=_dist(ms), predicted=_dist(ps),
                          n_delay_passed=sum(1 for x in rs if x["delay"]["passed"]),
                          fraction_delay_passed=sum(1 for x in rs if x["delay"]["passed"])
                          / len(rs),
                          completion_median_are=(statistics.median(ar) if ar else None))
        return tab
    worst = sorted(usable, key=lambda r: -r["delay"]["abs_error_s"])[:12]
    return dict(n_trials=len(rows), n_usable=len(usable),
                not_reconstructible=[r["key"] for r in rows if not r["reconstructible"]],
                criteria=dict(delay_imposed_on_others=crit_i, ranking=crit_ii,
                              job_completion_time=crit_iii),
                per_load=_tab(lambda r: r["load"]), per_action=_tab(lambda r: r["action"]),
                per_cell=_tab(lambda r: r["cell"]),
                noise=noise, noise_against_criteria=noise_against_criteria(),
                worst_predicted=[dict(key=w["key"], measured_delay_s=w["measured_delay_s"],
                                      predicted_delay_s=w["predicted_delay_s"],
                                      abs_error_s=w["delay"]["abs_error_s"],
                                      ratio=w["delay"]["ratio"],
                                      measured_completion_s=w["measured_completion_s"],
                                      predicted_completion_s=w["predicted_completion_s"])
                                 for w in worst],
                trials=[{k: v for k, v in r.items() if k != "setup"} for r in rows])


def evaluate_eng1b(pressure_field: str = "alloc_before_sched",
                   path: Any = None) -> Dict[str, Any]:
    raw = tr.load_eng1b_trials(path)
    caps = raw.get("kv_capacity")
    if not isinstance(caps, dict):
        caps = {}
    rows = []
    for t in raw["trials"]:
        cap = int(caps.get(t.get("tag"), KV_POOL_TOKENS_H100NVL))
        pred = tr.predict_eng1b_trial(t, cap, pressure_field=pressure_field)
        meas_lost = int(t.get("lost_tokens") or 0)
        pref = int(t["prefix"])
        rows.append(dict(server=t["server"], size=t["size"], load=t["load"], gap=t["gap"],
                         rep=t["rep"], prefix=pref,
                         measured_lost_tokens=meas_lost,
                         measured_fraction_lost=meas_lost / max(pref, 1),
                         measured_class=tr.loss_class(meas_lost, pref),
                         predicted_lost_tokens=pred["predicted_lost_tokens"],
                         predicted_fraction_lost=pred["predicted_fraction_lost"],
                         predicted_class=pred["predicted_class"],
                         allocated_tokens=pred["allocated_tokens"],
                         free_pool_tokens=pred["free_pool_tokens"]))
    correct = sum(1 for r in rows if r["measured_class"] == r["predicted_class"])
    acc = correct / len(rows) if rows else 0.0
    mae = (statistics.fmean([abs(r["predicted_fraction_lost"] - r["measured_fraction_lost"])
                            for r in rows]) if rows else float("nan"))
    conf: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        conf[r["measured_class"]][r["predicted_class"]] += 1
    def _tab(keyfn):
        out: Dict[Any, List[Dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(keyfn(r), []).append(r)
        return {str(k): dict(
            n=len(rs),
            class_accuracy=sum(1 for x in rs if x["measured_class"] == x["predicted_class"])
            / len(rs),
            mae_fraction=statistics.fmean([abs(x["predicted_fraction_lost"]
                                               - x["measured_fraction_lost"]) for x in rs]))
                for k, rs in sorted(out.items(), key=lambda kv: str(kv[0]))}
    return dict(n=len(rows), pressure_field=pressure_field, kv_capacity_tokens=dict(caps),
                criterion=CRITERIA["eng1b_prefix_loss"],
                class_accuracy=acc, n_correct=correct, threshold=CLASS_ACC,
                verdict=("PASS" if acc >= CLASS_ACC else "FAIL"),
                mae_fraction_lost=mae,
                confusion={k: dict(v) for k, v in sorted(conf.items())},
                per_server=_tab(lambda r: r["server"]), per_size=_tab(lambda r: r["size"]),
                per_load=_tab(lambda r: r["load"]), per_gap=_tab(lambda r: r["gap"]),
                worst=[dict(r) for r in sorted(
                    rows, key=lambda r: -abs(r["predicted_fraction_lost"]
                                             - r["measured_fraction_lost"]))[:12]],
                evidence_strength="WEAKER THAN THE HOLDOUT TEST: StudyENG1b has no held-out "
                                  "split, so these 852 trials are the whole study. No parameter "
                                  "used here was fitted on ENG1b and its measured staircase was "
                                  "not called, but the trials are not a held-out sample",
                trials=rows)


def negative_control(trials: Sequence[tr.Trial], sim: EngineSim) -> Dict[str, Any]:
    """Mechanism verification Step 4. The mechanism under test is that the ACTION's own work
    displaces other requests' work inside the engine. Disable it by replaying the with-arm
    WITHOUT the action, which is the same timeline as the without-arm, and confirm the predicted
    imposed delay collapses to zero. If it does not, the prediction is being driven by something
    other than the action."""
    rows = []
    for t in trials:
        full = tr.predict_trial(t, sim)["predicted_delay_s"]
        res_w = sim.run(tr._arm_requests(t.arms["with"], include_action=False))
        res_o = sim.run(tr._arm_requests(t.arms["without"], include_action=False))
        pw, po = res_w["per_request"], res_o["per_request"]
        w_rows = {tr._bg_key(r): r for r in t.arms["with"].background
                  if r.get("kind") in tr.COMPARED_KINDS}
        o_rows = {tr._bg_key(r): r for r in t.arms["without"].background
                  if r.get("kind") in tr.COMPARED_KINDS}
        tot = 0.0
        for k in set(w_rows) & set(o_rows):
            a = pw.get(str(w_rows[k].get("rid")), {}).get("ttft_s")
            b = po.get(str(o_rows[k].get("rid")), {}).get("ttft_s")
            if a is None or b is None:
                continue
            tot += float(a) - float(b)
        rows.append(dict(key=t.key(), with_action_s=full, action_removed_s=tot))
    full = [abs(r["with_action_s"]) for r in rows]
    resid = [abs(r["action_removed_s"]) for r in rows]
    med_full = statistics.median(full) if full else float("nan")
    med_resid = statistics.median(resid) if resid else float("nan")
    return dict(n=len(rows),
                control_cell=[r["key"] for r in rows],
                predicted_with_action=_dist([r["with_action_s"] for r in rows]),
                predicted_action_removed=_dist([r["action_removed_s"] for r in rows]),
                median_abs_with_action_s=med_full, median_abs_residual_s=med_resid,
                ratio_median_residual_to_median_effect=(med_resid / med_full if med_full
                                                        else None),
                collapsed=bool(med_full > 0 and med_resid / med_full < 0.05),
                exactly_zero=all(abs(r["action_removed_s"]) <= 1e-9 for r in rows),
                note="the action is the only thing the two arms differ in by DESIGN, but the two "
                     "arms are separate live runs, so their recorded submit instants differ by "
                     "the dispatch jitter StudyENG1 measured (<= 3.3 ms). With the action "
                     "removed the replay therefore leaves that jitter floor rather than exactly "
                     "zero, and the control asks whether the floor is negligible against the "
                     "effect, not whether it is bit-zero",
                rows=rows)


def holdout_secondary_criterion_ii(trials: Sequence[tr.Trial], sim: EngineSim,
                                   registered_path: Any) -> Dict[str, Any]:
    """Q1 (user ruling, 2026-11-16): a clearly labelled SECONDARY re-score of criterion (ii)
    under the CORRECTED compared-request definition, from the SAME FROZEN PREDICTIONS.

    WHAT THIS IS AND IS NOT. The registered T0 verdict and `t0_holdout_partc.json` and
    `t0_one_shot.log` are NOT touched and NOT superseded. The bug being corrected is a
    SCORING-DEFINITION ERROR, not a model change: StudyENG1 section 9's published per-cell table
    sums the imposed delay over the EPISODIC background stream only, while the registered run
    also summed the 8 warm sessions' appends and escalations that exist in the W25 cells. The
    engine model, the pool, the parameters and the step model are byte-identical to the freeze;
    the only files that changed are the two that decide WHICH REQUESTS ENTER THE SUM.

    HOW "the same frozen predictions" is enforced rather than asserted. The per-request simulated
    TTFTs are recomputed by the identical frozen model, and this function FIRST reproduces the
    registered superset-summed `predicted_delay_s` for every trial and refuses to continue unless
    every one matches the registered file to 1e-9. Only then is the corrected episodic-only sum
    taken. So the secondary score is a different SUMMATION of predictions already made, and the
    check proves it.
    """
    reg = json.loads(Path(registered_path).read_text())
    reg_by_key = {r["key"]: r for r in reg["trials"]}
    rows = []
    mismatches = []
    for t in trials:
        superset = tr.predict_trial(t, sim, kinds=tr.BACKGROUND_KINDS)
        corrected = tr.predict_trial(t, sim, kinds=tr.COMPARED_KINDS)
        m_sup = tr.measured_imposed_delay_s(t, kinds=tr.BACKGROUND_KINDS)
        m_cor = tr.measured_imposed_delay_s(t, kinds=tr.COMPARED_KINDS)
        r = reg_by_key.get(t.key())
        if r is None:
            mismatches.append(dict(key=t.key(), reason="absent from the registered file"))
            continue
        d_pred = abs(superset["predicted_delay_s"] - r["predicted_delay_s"])
        d_meas = abs(m_sup["total_s"] - r["measured_delay_s"])
        if d_pred > 1e-9 or d_meas > 1e-9:
            mismatches.append(dict(key=t.key(), predicted_delta=d_pred, measured_delta=d_meas))
        rows.append(dict(key=t.key(), load=t.load, action=t.action, cell=t.cell(),
                         registered_predicted_s=r["predicted_delay_s"],
                         registered_measured_s=r["measured_delay_s"],
                         reproduced_predicted_s=superset["predicted_delay_s"],
                         reproduced_measured_s=m_sup["total_s"],
                         corrected_predicted_s=corrected["predicted_delay_s"],
                         corrected_measured_s=m_cor["total_s"]))
    if mismatches:
        raise RuntimeError(
            "the secondary re-score refuses to run: it could not reproduce the registered "
            "superset-summed values bit for bit, so it would not be a re-score of the same "
            "frozen predictions: %s" % json.dumps(mismatches[:5]))

    def _rank(key_pred: str, key_meas: str) -> Dict[str, Any]:
        bym: Dict[str, List[float]] = defaultdict(list)
        byp: Dict[str, List[float]] = defaultdict(list)
        for r in rows:
            bym[r["cell"]].append(r[key_meas])
            byp[r["cell"]].append(r[key_pred])
        med_m = {c: statistics.median(v) for c, v in bym.items()}
        med_p = {c: statistics.median(v) for c, v in byp.items()}
        pairs = []
        for load in sorted({c.split("|")[0] for c in med_m}):
            acts = sorted(c.split("|")[1] for c in med_m if c.startswith(load + "|"))
            for i in range(len(acts)):
                for j in range(i + 1, len(acts)):
                    a, b = acts[i], acts[j]
                    ma, mb = med_m["%s|%s" % (load, a)], med_m["%s|%s" % (load, b)]
                    pa, pb = med_p["%s|%s" % (load, a)], med_p["%s|%s" % (load, b)]
                    lo, hi = min(abs(ma), abs(mb)), max(abs(ma), abs(mb))
                    if lo <= 0 or hi / lo <= RANK_RATIO:
                        pairs.append(dict(load=load, a=a, b=b, included=False))
                        continue
                    pairs.append(dict(load=load, a=a, b=b, included=True,
                                      measured_ratio=hi / lo, measured=[ma, mb],
                                      predicted=[pa, pb], agree=bool((ma > mb) == (pa > pb))))
        inc = [p for p in pairs if p["included"]]
        frac = (sum(1 for p in inc if p["agree"]) / len(inc)) if inc else 0.0
        return dict(n_pairs_total=len(pairs), n_pairs_included=len(inc),
                    n_agree=sum(1 for p in inc if p["agree"]), fraction=frac,
                    threshold=MIN_FRACTION,
                    verdict=("PASS" if inc and frac >= MIN_FRACTION else "FAIL"),
                    pairs=pairs, cell_medians_measured=med_m, cell_medians_predicted=med_p)

    registered = _rank("registered_predicted_s", "registered_measured_s")
    corrected = _rank("corrected_predicted_s", "corrected_measured_s")
    affected = sorted({r["cell"] for r in rows
                       if abs(r["corrected_measured_s"] - r["registered_measured_s"]) > 1e-9})
    cell_shift = {}
    for c in affected:
        rs = [r for r in rows if r["cell"] == c]
        a = statistics.median([r["registered_measured_s"] for r in rs])
        b = statistics.median([r["corrected_measured_s"] for r in rs])
        cell_shift[c] = dict(registered_median_s=a, corrected_median_s=b,
                             ratio=(a / b if b else None),
                             moved_more_than_2x=bool(b and abs(a / b) > 2.0))
    return dict(
        what="SECONDARY, LABELLED re-score of criterion (ii) only, under the corrected "
             "compared-request definition, from the same frozen predictions",
        status="SECONDARY. It does NOT replace the registered T0 verdict and nothing in "
               "t0_holdout_partc.json or t0_one_shot.log was read for anything but the "
               "bit-equality check or modified in any way",
        error_class="SCORING-DEFINITION ERROR, not a model change: the engine model, the KV "
                    "pool, the parameters and the step model JSON are byte-identical to the "
                    "freeze; only which requests enter the SUM changed",
        reproduced_registered_bit_for_bit=True,
        n_trials=len(rows), criterion=CRITERIA["ranking"],
        registered_scoring=registered, corrected_scoring=corrected,
        cells_affected=affected, cells_affected_detail=cell_shift,
        cells_moved_more_than_2x=[c for c, v in cell_shift.items()
                                  if v["moved_more_than_2x"]],
        trials=rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", required=True,
                    choices=["dryrun", "control", "eng1b", "holdout",
                             "holdout-secondary-ii"])
    ap.add_argument("--out-dir", default="results/orchestration/study_t0")
    ap.add_argument("--authorization", default="")
    ap.add_argument("--pressure-field", default="alloc_before_sched",
                    choices=["alloc_before_sched", "alloc_before_resume"])
    args = ap.parse_args(list(argv) if argv is not None else None)
    root = _repo_root()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    sm = StepModel.load()
    sim = EngineSim(step=sm)
    import sys
    sys.path.insert(0, str(root / "experiments/lib"))
    from _provenance import stamp

    def stamp_or_none(script: str, n: int) -> Dict[str, Any]:
        return stamp(script="policy/run_t0.py --mode %s" % args.mode, model=None, device="cpu",
                     n=n, args=args)
    if args.mode == "eng1b":
        res = evaluate_eng1b(args.pressure_field)
        res["engine"] = sm.describe()
        res["_provenance"] = stamp_or_none(script="run_t0.py", n=res["n"])
        (out_dir / "t0_eng1b_prefix_loss.json").write_text(json.dumps(res, indent=1,
                                                                      default=str))
        print("eng1b: class accuracy %.4f (n=%d) verdict %s, MAE fraction %.4f"
              % (res["class_accuracy"], res["n"], res["verdict"], res["mae_fraction_lost"]))
        return 0
    trials = tr.load_part_c_trials()
    fit = [t for t in trials if not t.holdout]
    hold = [t for t in trials if t.holdout]
    if args.mode == "control":
        cell = [t for t in fit if t.load == "P40" and t.action == "piece2048"]
        res = negative_control(cell, sim)
        res["cell"] = "P40 | piece2048, FIT trials only"
        res["_provenance"] = stamp_or_none(script="run_t0.py", n=res["n"])
        (out_dir / "t0_negative_control.json").write_text(json.dumps(res, indent=1, default=str))
        print("control: collapsed=%s n=%d" % (res["collapsed"], res["n"]))
        return 0
    if args.mode == "holdout-secondary-ii":
        res = holdout_secondary_criterion_ii(
            hold, sim, out_dir / "t0_holdout_partc.json")
        res["_provenance"] = stamp_or_none(script="run_t0.py", n=res["n_trials"])
        (out_dir / "t0_holdout_secondary_criterion_ii.json").write_text(
            json.dumps(res, indent=1, default=str))
        print("secondary (ii): registered %s %.4f (%d of %d) | corrected %s %.4f (%d of %d)"
              % (res["registered_scoring"]["verdict"], res["registered_scoring"]["fraction"],
                 res["registered_scoring"]["n_agree"],
                 res["registered_scoring"]["n_pairs_included"],
                 res["corrected_scoring"]["verdict"], res["corrected_scoring"]["fraction"],
                 res["corrected_scoring"]["n_agree"],
                 res["corrected_scoring"]["n_pairs_included"]))
        print("cells affected:", res["cells_affected"])
        print("cells moved more than 2x:", res["cells_moved_more_than_2x"])
        return 0
    if args.mode == "dryrun":
        res = evaluate_part_c(fit, sim, noise=noise_by_cell(fit))
        res["split"] = "FIT (dry run; out of sample for the step model, not the holdout)"
        res["engine"] = sm.describe()
        res["_provenance"] = stamp_or_none(script="run_t0.py", n=res["n_usable"])
        (out_dir / "t0_dryrun_partc_fit.json").write_text(json.dumps(res, indent=1, default=str))
        for k, v in res["criteria"].items():
            print("dryrun %-26s %s" % (k, v["verdict"]))
        return 0
    # --- holdout, one shot
    if not args.authorization:
        raise SystemExit("the holdout mode needs --authorization recording who authorized the "
                         "one-shot run")
    frozen = FrozenState.freeze(root, FROZEN_FILES,
                                note="StudyT0-fidelity one-shot holdout run")
    (out_dir / "t0_freeze.json").write_text(json.dumps(frozen.as_dict(), indent=1, default=str))
    harness = T0Harness()

    def _compute() -> Dict[str, Any]:
        r = evaluate_part_c(hold, sim, noise=noise_by_cell(fit))
        r["split"] = "HOLDOUT (174 triples, one shot)"
        r["engine"] = sm.describe()
        r["frozen"] = frozen.as_dict()
        r["_provenance"] = stamp_or_none(script="run_t0.py", n=r["n_usable"])
        return r

    res = harness.run_holdout_once(frozen, out_dir / "t0_holdout_partc.json",
                                   out_dir / "t0_one_shot.log", _compute,
                                   authorization=args.authorization)
    for k, v in res["criteria"].items():
        print("holdout %-26s %s" % (k, v["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
