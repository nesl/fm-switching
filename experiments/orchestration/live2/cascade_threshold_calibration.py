#!/usr/bin/env python3
"""DEV calibration of the cascade arms' decision thresholds, per card and per confidence type.

Pre-registered in `research/prereg_cascade_calibration.md`, committed BEFORE this script ran
(commit d8b88619). D164 / user ruling 2026-11-22 item 2.

WHAT THIS DOES AND DOES NOT DO. It applies the procedure each arm's OWN card specifies, on DEV
only, once per confidence type, and writes the fitted values to a COMMITTED FILE that the arm
then READS. It invents no threshold: where a card specifies no method, or where the quantity the
card's method calibrates against does not exist in live2, the arm is recorded as NOT CALIBRATABLE
with the reason and no number is written for it.

WHY A FILE RATHER THAN A RE-DERIVATION AT USE TIME. The LH-REQ work established the rule: two
independently written derivations of the same partition differ somewhere and nothing catches it.
A file can be diffed.

  fit     compute the per-type DEV thresholds and write the calibration JSON
  cell    run ONE dry cell in THIS process and print a JSON summary (the harness does not
          reproduce a dry cell twice inside one process, so a proof runs one cell per process)
  proofs  orchestrate the proof cells as subprocesses and write the proofs JSON

CPU only; no GPU, no model, no new measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

H = Path(__file__).resolve().parent
R = H.parents[2]
for p in (str(H), str(H / "fleet"), str(H / "scorer"), str(H / "hybrid"), str(H / "v5"),
          str(R / "experiments/orchestration/live"),
          str(R / "experiments/orchestration/baselines"),
          str(R / "experiments/orchestration/baselines/reconstructed"),
          str(R / "experiments/orchestration/sim"), str(R / "experiments/lib"),
          str(R / "experiments/orchestration")):
    if p not in sys.path:
        sys.path.insert(0, p)

OUTDIR = R / "results/orchestration/live2/cascade_calibration"
CALIB = OUTDIR / "cascade_thresholds.json"
PROOFS = OUTDIR / "cascade_calibration_proofs.json"
LH_REQ = R / "results/orchestration/live2/lh_req/lh_req_definition.json"
SS2_CONF = R / "results/casestudy/study_ss2/ss2_device_confidence.json"
SS2_SPLIT = R / "results/casestudy/study_ss2/ss2_dev_eval_split.json"

# The POSTED D164 workload (BASELINE_MATRIX _L3_epg_rq30), forwarded in full. A proof run on
# test_hybrid.dry's defaults would be a proof about a different workload.
WORK = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
            dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
CELL = dict(WORK, seed=4, n=16, run_s=600.0)

MIN_DEV_ITEMS = 10          # prereg section 5, fixed before fitting
TRIGGER_RATE = 0.20         # cards/cascade.md hyperparameter table, StudyE9's primary rate

TYPES = ("episodic", "robot", "ss_mcq", "ss_free_form", "ss_point")


# ---------------------------------------------------------------- the DEV populations
def lh_req_dev_ids() -> List[str]:
    """The LH-REQ DEV questions, case-folded on BOTH sides (D143 A; the folding trap).

    The committed definition carries 97 ids and `per_split` DEV 28 / EVAL 69. DEV is the ids that
    are NOT in the S-EMBER EVAL set, and the count is asserted against the committed number, which
    is the only thing that catches a one-sided fold.
    """
    import importlib.util
    d = json.loads(LH_REQ.read_text())
    allids = {q.lower() for q in d["lh_req_question_ids"]}
    spec = importlib.util.spec_from_file_location(
        "calib_sember_split", R / "experiments/orchestration/baselines/sember_split.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    s = mod.split()
    ev = {q.lower() for q in s["eval_questions"]}
    dv = {q.lower() for q in s["dev_questions"]}
    dev = sorted(allids & dv)
    if sorted(allids - ev) != dev:
        raise SystemExit("LH-REQ DEV by subtraction and by intersection disagree: the split is "
                         "not a partition of the LH-REQ ids under case folding")
    want = int(d["per_split"]["DEV"])
    if len(dev) != want:
        raise SystemExit("LH-REQ x DEV is %d but the committed definition says DEV = %d. Fold "
                         "both sides." % (len(dev), want))
    return dev


def ss2_dev_rows() -> List[Dict[str, Any]]:
    """The StudySS2 confidence rows restricted to the committed DEV part of the 30/70 split."""
    split = json.loads(SS2_SPLIT.read_text())
    dev = set()
    for name, part in split["per_dataset"].items():
        dev |= {str(q) for q in part["dev_qids"]}
    rows = json.loads(SS2_CONF.read_text())["rows"]
    return [r for r in rows if str(r["qid"]) in dev]


def ss_type_of_row(r: Dict[str, Any]) -> str:
    if r["rule"] == "mcq_chosen_letter_mass":
        return "ss_mcq"
    if r.get("signal_strength") == "weak":
        return "ss_point"
    return "ss_free_form"


# ---------------------------------------------------------------- the fits
def _quantile_report(vals: Sequence[float]) -> Dict[str, Any]:
    v = sorted(float(x) for x in vals)
    n = len(v)
    if not n:
        return dict(n=0)
    return dict(n=n, min=round(v[0], 6), p25=round(v[max(0, n // 4)], 6),
                median=round(statistics.median(v), 6), p75=round(v[min(n - 1, 3 * n // 4)], 6),
                max=round(v[-1], 6), n_distinct=len(set(v)))


def fit_episodic() -> Dict[str, Any]:
    """cards/cascade.md adaptation A2: the (1 - trigger_rate) quantile of the DEVICE arm's score
    on DEVELOPMENT-split negatives. Recomputed, not re-specified."""
    import numpy as np
    import devsplit as DS
    sc, lab = DS.load(arms=(("4BI", 1),))
    neg = [v for clip, per in sc[("4BI", 1)].items()
           if lab[clip] == "negative" for v in per.values()]
    tau = float(np.quantile(np.array(neg), 1.0 - TRIGGER_RATE))
    out = dict(type="episodic", method=("the (1 - trigger_rate) quantile of the DEVICE arm's "
                                        "score on StudyD3 DEVELOPMENT-split negatives"),
               card="cards/cascade.md adaptation A2", trigger_rate=TRIGGER_RATE,
               value=round(tau, 6), signal="log P(Yes) of the 4BI device arm at N = 1",
               dev_population="StudyD3 development clips, negatives, all offsets",
               distribution=_quantile_report(neg))
    return out


def fit_robot() -> Dict[str, Any]:
    """cards/cascade.md amendment 2: the MEDIAN committed device confidence over DEV questions,
    with the population narrowed to LH-REQ DEV per D143 A."""
    import device_confidence as DC
    prim = DC._load_primary()
    lower = {k.lower(): v for k, v in prim.items()}
    dev = lh_req_dev_ids()
    vals = [lower[q] for q in dev if q in lower]
    covered = len(vals)
    out = dict(type="robot", method="the median committed device confidence over DEV questions",
               card="cards/cascade.md amendment 2 (2026-11-13)",
               signal="StudyE7 Job A letter_probs mass on the emitted letter (4B-D2)",
               dev_population="LH-REQ DEV (D143 A), %d ids, %d with a committed value"
                              % (len(dev), covered),
               n_dev_ids=len(dev), n_with_value=covered,
               distribution=_quantile_report(vals))
    out["value"] = round(statistics.median(vals), 6) if covered else None
    return out


def fit_single_shot() -> List[Dict[str, Any]]:
    rows = ss2_dev_rows()
    by: Dict[str, List[float]] = {}
    for r in rows:
        by.setdefault(ss_type_of_row(r), []).append(float(r["confidence"]))
    out = []
    for t in ("ss_mcq", "ss_free_form", "ss_point"):
        vals = by.get(t, [])
        o = dict(type=t, method="the median committed device confidence over DEV questions",
                 card="cards/cascade.md amendment 2, applied per confidence type (D164)",
                 signal=("letter_probs mass on the emitted letter" if t == "ss_mcq"
                         else "geometric mean token probability"),
                 dev_population="StudySS2 committed 30/70 DEV part (D143 A)",
                 weak=(t == "ss_point"), n_with_value=len(vals),
                 distribution=_quantile_report(vals))
        o["value"] = round(statistics.median(vals), 6) if vals else None
        if t == "ss_point":
            o["weak_note"] = ("DECLARED WEAK by its own source: token confidence in the digits "
                              "of a coordinate is not confidence that the point is right. "
                              "Fitted and reported; may not carry a headline (CLAUDE.md check 6)")
        out.append(o)
    return out


def fail_conditions(fit: Dict[str, Any]) -> List[str]:
    """The prereg section 5 conditions, applied to one fitted type."""
    bad = []
    d = fit.get("distribution") or {}
    n = int(d.get("n", fit.get("n_with_value") or 0) or 0)
    if n < MIN_DEV_ITEMS:
        bad.append("too_little_dev_data(n=%d<%d)" % (n, MIN_DEV_ITEMS))
    v = fit.get("value")
    if v is None:
        bad.append("no_value")
    elif n:
        if v <= d["min"]:
            bad.append("degenerate_floor_at_or_below_dev_min")
        if v > d["max"]:
            bad.append("degenerate_floor_above_dev_max")
    if n and d.get("n_distinct", 0) <= 1:
        bad.append("constant_signal_on_dev")
    return bad


def cmd_fit(args) -> None:
    import _provenance
    fits = [fit_episodic(), fit_robot()] + fit_single_shot()
    for f in fits:
        f["prereg_fail_conditions_triggered"] = fail_conditions(f)
    doc: Dict[str, Any] = dict(
        _what=("DEV-fitted decision thresholds for the cascade arms, one per confidence type. "
               "Pre-registered in research/prereg_cascade_calibration.md (commit d8b88619) "
               "BEFORE this ran."),
        _rule=("fitted on DEV only (D6); the robot population is LH-REQ DEV and the single-shot "
               "populations are the committed seeded 30/70 DEV part (D143 A). EVAL is never "
               "fitted on and HOLDOUT is never read."),
        _consumers=("baselines/cascade_adapted.py reads `confidence_floors` from this file via "
                    "device_confidence.fitted_floors(); the type of a query is resolved from "
                    "device_confidence.kind_of(question_id)."),
        trigger_rate=TRIGGER_RATE, min_dev_items=MIN_DEV_ITEMS,
        confidence_floors={f["type"]: f["value"] for f in fits if f["type"] != "episodic"},
        tau_trigger=next(f["value"] for f in fits if f["type"] == "episodic"),
        per_type=fits,
        committed_comparators=dict(
            confidence_floor_card=0.7358, tau_trigger_card=-7.0009,
            source="cards/cascade.md hyperparameter table and amendment 2"),
        not_calibratable=NOT_CALIBRATABLE)
    doc["_provenance"] = _provenance.stamp(script="cascade_threshold_calibration.py",
                                           model="none", device="cpu",
                                           n=sum(int((f.get("distribution") or {}).get("n", 0) or 0)
                                                 for f in fits), args=args)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    CALIB.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in doc.items() if k != "per_type"}, indent=1, default=str))
    for f in fits:
        print("%-14s value=%-10s %s  FAIL=%s" % (f["type"], f["value"], f["distribution"],
                                                 f["prereg_fail_conditions_triggered"]))


# What is NOT calibratable, with the reason, written into the calibration file so a reader of the
# numbers meets the refusals in the same place. Checked in code by `cmd_fit`'s callers below.
NOT_CALIBRATABLE: Dict[str, Dict[str, str]] = {
    "cascade-routing": dict(
        quantity="lambda",
        card_method=("cards/cascade_routing.md and the paper: lambda is calibrated OFFLINE so "
                     "that expected cost meets a cost budget B. The card states this explicitly "
                     "and uses it to justify not adding B to the shared observation schema."),
        why_not=("live2 has no cost budget B. coordinator.py:321 sets gpu_budget_s = window_s x "
                 "1.0 GPU-second per second and its own comment says this is the PHYSICAL "
                 "CAPACITY, so it never binds artificially (D58: round 1 has no fixed budget). "
                 "D174 (1)'s census found budget refusals ZERO in every committed cell. The "
                 "quantity the paper's calibration targets does not exist here, so no lambda is "
                 "fitted and lambda_base stays at its committed 0.02, an UNFITTED CONSTANT."),
        also=("this arm has no fitted confidence threshold at all: its escalation test is "
              "q_cloud - (Q_DEVICE + (1 - Q_DEVICE) * conf) - lambda * c_cloud > 0, whose "
              "implied confidence threshold is a consequence of the committed quality priors "
              "and the cost curves, not a free parameter.")),
    "eco-llm": dict(
        quantity="none",
        card_method=("cards/ecollm.md specifies no threshold calibration. The arm does not "
                     "declare reads_device_answer, so it never receives a device confidence; its "
                     "rule is select = max(feasible, key=(quality, -cost)) under SLOs taken from "
                     "the observation (the query's own deadline, the remaining budget), with "
                     "min_quality left None."),
        why_not=("there is no thresholded confidence to set. The card further establishes (D137 "
                 "item 3, D138) that quality is consumed only as an ORDER, so no value in the "
                 "quality table can move a decision; price reaches a decision only through "
                 "feasibility. Nothing is invented here."),
        also=("BASELINE_MATRIX's 'these three escalate on a device-confidence threshold' is "
              "wrong for eco-llm: it escalates on nothing of the kind.")),
}


# ---------------------------------------------------------------- one dry cell, one process
def _decision_key(r: Dict[str, Any]) -> Tuple:
    """What was decided, independent of where it sits in the log (test_hybrid's own register)."""
    return (r.get("t"), r.get("kind"), r.get("action"), r.get("decision"),
            tuple(sorted(r.get("opportunity_ids") or ())) if isinstance(
                r.get("opportunity_ids"), (list, tuple)) else r.get("opportunity_id"),
            r.get("representation"))


def _digest(rows: Sequence[Dict[str, Any]], ignore: Sequence[str] = ("arm_version",)) -> str:
    rr = [{k: v for k, v in r.items() if k not in ignore} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _run_cell(arm: str, floors: Optional[Dict[str, float]], seed: int, run_s: float,
              lambda_base: Optional[float] = None) -> Dict[str, Any]:
    import hybrid  # noqa: F401
    import test_hybrid as TH
    import coordinator as CO

    def patch(a):
        if floors is not None and hasattr(a, "confidence_floors"):
            a.confidence_floors = dict(floors)
        if lambda_base is not None and hasattr(a, "lambda_base"):
            a.lambda_base = float(lambda_base)

    rows, stats = TH.dry(arm, seed, CELL["n"], run_s=run_s, ratio=CELL["ratio"], patch=patch,
                         robot_question_set=CELL["robot_question_set"],
                         ss_question_set=CELL["ss_question_set"],
                         dashcam_format=CELL["dashcam_format"],
                         robot_upload=CELL["robot_upload"],
                         robot_reask_mean_s=CELL["robot_reask_mean_s"])
    keys = [_decision_key(r) for r in rows]
    return dict(arm=arm, seed=seed, run_s=run_s, floors=floors, lambda_base=lambda_base,
                n_rows=len(rows), digest=_digest(rows),
                key_digest=hashlib.sha256(json.dumps(sorted(map(str, keys))).encode()
                                          ).hexdigest()[:16],
                keys=[str(k) for k in keys], stats=stats,
                device_wait_measured=bool(CO.DEVICE_WAIT_MEASURED))


def cmd_cell(args) -> None:
    out = _run_cell(args.arm, json.loads(args.floors) if args.floors else None,
                    args.seed, args.run_s,
                    lambda_base=(None if args.lambda_base is None else float(args.lambda_base)))
    # the per-cell counters the coordinator keeps are the device-wait and confidence-supply proofs
    Path(args.out).write_text(json.dumps(out, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "keys"}, default=str)[:2000])


def _sub(tag: str, arm: str, floors: Optional[Dict[str, float]], seed: int, run_s: float,
         lambda_base: Optional[float] = None) -> Dict[str, Any]:
    """One dry cell in its OWN process: a dry cell does not reproduce twice inside one process."""
    tmp = OUTDIR / ("_cell_%s.json" % tag)
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "cell", "--arm", arm,
           "--seed", str(seed), "--run-s", str(run_s), "--out", str(tmp)]
    if floors is not None:
        cmd += ["--floors", json.dumps(floors)]
    if lambda_base is not None:
        cmd += ["--lambda-base", str(lambda_base)]
    env = dict(os.environ)
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0 or not tmp.exists():
        return dict(error=(p.stderr or p.stdout or "")[-1500:], tag=tag, arm=arm)
    d = json.loads(tmp.read_text())
    tmp.unlink()
    d["tag"] = tag
    return d


def _cell_audit(arm: str, seed: int, run_s: float) -> Dict[str, Any]:
    """One cell, with the COORDINATOR's own counters captured and the decision mix tallied.

    Two prereg proofs need what `dry` does not return. Proof 3 (the device wait) lives on
    `coordinator.counts`, and an arm without a `stats` dict (eco-llm) needs its characteristic
    decision counted from the decision log instead. The coordinator instance is captured by
    subclassing it before `dry` imports it, so the cell is the SAME cell, not a reconstruction.
    """
    import collections
    import hybrid  # noqa: F401
    import test_hybrid as TH
    import coordinator as CO

    holder: Dict[str, Any] = {}
    base = CO.Live2Coordinator

    class _Capturing(base):                                   # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            base.__init__(self, *a, **k)
            holder["co"] = self

    CO.Live2Coordinator = _Capturing
    try:
        rows, stats = TH.dry(arm, seed, CELL["n"], run_s=run_s, ratio=CELL["ratio"],
                             robot_question_set=CELL["robot_question_set"],
                             ss_question_set=CELL["ss_question_set"],
                             dashcam_format=CELL["dashcam_format"],
                             robot_upload=CELL["robot_upload"],
                             robot_reask_mean_s=CELL["robot_reask_mean_s"])
    finally:
        CO.Live2Coordinator = base
    co = holder.get("co")
    counts = dict(getattr(co, "counts", {}) or {})
    dw = {k: int(v) for k, v in counts.items() if k.startswith("device_wait")}
    dc = {k: int(v) for k, v in counts.items() if k.startswith("device_conf")}
    mix = collections.Counter((r.get("kind"), r.get("representation")) for r in rows)
    return dict(arm=arm, seed=seed, run_s=run_s, n_rows=len(rows), digest=_digest(rows),
                arm_stats=stats, device_wait_counts=dw, device_confidence_counts=dc,
                decision_mix={("%s|%s" % (k[0], k[1])): v for k, v in sorted(
                    mix.items(), key=lambda x: str(x[0]))},
                device_wait_measured_switch=bool(CO.DEVICE_WAIT_MEASURED),
                proxy_s=float(CO.DEVICE_ANSWER_CHARGE_S))


def cmd_cellaudit(args) -> None:
    Path(args.out).write_text(json.dumps(_cell_audit(args.arm, args.seed, args.run_s),
                                         default=str))
    print("ok %s" % args.arm)


def cmd_audit(args) -> None:
    import _provenance
    res: Dict[str, Any] = dict(
        _what=("Prereg proof 3 (the device wait is MEASURED, fallback counters zero) and the "
               "characteristic-decision mix for each of the three cascade arms, read from the "
               "coordinator's own counters on one dry cell per arm, one cell per process."),
        cell=dict(CELL, run_s=args.run_s))
    for arm in ("confidence-cascade", "cascade-routing", "eco-llm"):
        tmp = OUTDIR / ("_audit_%s.json" % arm)
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "cellaudit",
               "--arm", arm, "--seed", str(CELL["seed"]), "--run-s", str(args.run_s),
               "--out", str(tmp)]
        pr = subprocess.run(cmd, capture_output=True, text=True)
        if pr.returncode != 0 or not tmp.exists():
            res[arm] = dict(error=(pr.stderr or pr.stdout or "")[-1200:])
            continue
        res[arm] = json.loads(tmp.read_text())
        tmp.unlink()
    res["_provenance"] = _provenance.stamp(script="cascade_threshold_calibration.py",
                                           model="none", device="cpu", n=CELL["n"], args=args)
    (OUTDIR / "cascade_calibration_audit.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str)[:5000])


def cmd_proofs(args) -> None:
    import _provenance
    res: Dict[str, Any] = dict(
        _what=("Proofs for the cascade threshold calibration: the characteristic decision occurs "
               "in BOTH directions, the switch reaches a decision (Step 2b), the identity "
               "control holds across processes, and the device wait is fully measured."),
        cell=dict(CELL, run_s=args.run_s), prereg="research/prereg_cascade_calibration.md")
    floors = json.loads(CALIB.read_text())["confidence_floors"]
    res["fitted_floors"] = floors

    # P0 IDENTITY CONTROL, across processes, before any A-versus-B is read (CLAUDE.md check 7).
    a = _sub("id_a", "confidence-cascade", floors, CELL["seed"], args.run_s)
    b = _sub("id_b", "confidence-cascade", floors, CELL["seed"], args.run_s)
    res["P0_identity_control"] = dict(
        digest_a=a.get("digest"), digest_b=b.get("digest"),
        rows_a=a.get("n_rows"), rows_b=b.get("n_rows"),
        identical=bool(a.get("digest") and a.get("digest") == b.get("digest")),
        error=a.get("error") or b.get("error"),
        meaning=("one dry cell per process. If this fails, no A-versus-B comparison from these "
                 "cells may be read."))
    res["P1_characteristic_decision"] = dict(fitted=a.get("stats"), cell_digest=a.get("digest"))

    # P2 STEP 2b, one type at a time: 0.0 can never escalate on confidence, 1.0 always does.
    step2b = {}
    for t in ("robot", "ss_mcq", "ss_free_form", "ss_point"):
        lo = dict(floors); lo[t] = 0.0
        hi = dict(floors); hi[t] = 1.0
        rl = _sub("lo_%s" % t, "confidence-cascade", lo, CELL["seed"], args.run_s)
        rh = _sub("hi_%s" % t, "confidence-cascade", hi, CELL["seed"], args.run_s)
        if rl.get("error") or rh.get("error"):
            step2b[t] = dict(error=rl.get("error") or rh.get("error"))
            continue
        kl, kh = list(rl["keys"]), list(rh["keys"])
        sl, sh = set(kl), set(kh)
        diff = sorted(sl ^ sh)
        first = diff[0] if diff else None
        step2b[t] = dict(floor_lo=0.0, floor_hi=1.0, rows_lo=rl["n_rows"], rows_hi=rh["n_rows"],
                         digest_lo=rl["digest"], digest_hi=rh["digest"],
                         n_differing_decisions_setwise=len(diff), first_difference=first,
                         moved=bool(diff), stats_lo=rl.get("stats"), stats_hi=rh.get("stats"))
    res["P2_step2b_per_type"] = step2b

    # P3 the other two arms: characteristic decision, and for cascade-routing a Step 2b on the
    # one constant its card names (lambda), so an unfitted constant is not also an inert one.
    cr_a = _sub("cr_base", "cascade-routing", None, CELL["seed"], args.run_s, lambda_base=0.02)
    cr_b = _sub("cr_hi", "cascade-routing", None, CELL["seed"], args.run_s, lambda_base=2.0)
    moved = (cr_a.get("digest") and cr_b.get("digest") and cr_a["digest"] != cr_b["digest"])
    res["P3_cascade_routing"] = dict(
        stats=cr_a.get("stats"), digest_lambda_002=cr_a.get("digest"),
        digest_lambda_200=cr_b.get("digest"), lambda_moves_decisions=bool(moved),
        n_differing_decisions_setwise=(len(set(cr_a.get("keys") or ()) ^ set(cr_b.get("keys") or ()))
                                      if cr_a.get("keys") and cr_b.get("keys") else None),
        error=cr_a.get("error") or cr_b.get("error"),
        note=("lambda is NOT fitted here, for the reason in the calibration file. This is a "
              "positive control on the constant, so that an unfitted constant is not reported "
              "without saying whether it is also inert."))
    ec = _sub("ecollm", "eco-llm", None, CELL["seed"], args.run_s)
    res["P4_ecollm"] = dict(stats=ec.get("stats"), digest=ec.get("digest"),
                            error=ec.get("error"),
                            note="no threshold to calibrate; characteristic decision only.")
    res["_provenance"] = _provenance.stamp(script="cascade_threshold_calibration.py",
                                           model="none", device="cpu", n=CELL["n"], args=args)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    PROOFS.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in res.items() if not k.startswith("_")},
                     indent=1, default=str)[:6000])


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fit").set_defaults(fn=cmd_fit)
    c = sub.add_parser("cell")
    c.add_argument("--arm", required=True)
    c.add_argument("--seed", type=int, default=CELL["seed"])
    c.add_argument("--run-s", dest="run_s", type=float, default=CELL["run_s"])
    c.add_argument("--floors", default=None)
    c.add_argument("--lambda-base", dest="lambda_base", default=None)
    c.add_argument("--out", required=True)
    c.set_defaults(fn=cmd_cell)
    ca = sub.add_parser("cellaudit")
    ca.add_argument("--arm", required=True)
    ca.add_argument("--seed", type=int, default=CELL["seed"])
    ca.add_argument("--run-s", dest="run_s", type=float, default=CELL["run_s"])
    ca.add_argument("--out", required=True)
    ca.set_defaults(fn=cmd_cellaudit)
    au = sub.add_parser("audit")
    au.add_argument("--run-s", dest="run_s", type=float, default=CELL["run_s"])
    au.set_defaults(fn=cmd_audit)
    p = sub.add_parser("proofs")
    p.add_argument("--run-s", dest="run_s", type=float, default=CELL["run_s"])
    p.set_defaults(fn=cmd_proofs)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
