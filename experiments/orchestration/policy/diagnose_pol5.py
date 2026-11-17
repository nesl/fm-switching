"""StudyPOL5-engine Part 1: WHERE the frozen pol4 model's imposed-delay error sits, per arrival.

StudyT0b's FIT dry run showed the residual concentrated in piece rebuilds, but a trial-level sum
cannot say which part of the action's life the error comes from. StudyENG1d recorded, for every
background arrival, which phase of the action it arrived in, so this module compares predicted
against measured PER ARRIVAL inside those phases:

  pre_inj   the arrival came before the action was submitted (the within-trial control);
  pre_fe    between the action's submission and its scheduling, the front-end window;
  0-25 ... 75-100   inside the action's engine span, by offset;
  post      after the action's last prefill step.

It also compares the COUNT of arrivals the model places in each phase against the measured count,
because a model can get a phase's price right and still be wrong about who is in it.

NOTHING IS CHANGED HERE. This runs before any model edit, and its output is the evidence the
Part 2 changes have to be justified by.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import eng1d_replay as e1d
from . import trace_replay as tr
from .eng1_engine import EngineSim, make_sim

OUT_DIR = "results/orchestration/study_pol5"
MODEL_BINS = ("pre_inj", "pre_fe", "in_window", "post")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _q(xs: Sequence[float], p: float) -> Optional[float]:
    if not xs:
        return None
    ys = sorted(xs)
    pos = (len(ys) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] * (1 - (pos - lo)) + ys[hi] * (pos - lo)


def _dist(xs: Sequence[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    return dict(n=len(xs), sum=sum(xs), median=statistics.median(xs), p10=_q(xs, 0.1),
                p90=_q(xs, 0.9), min=min(xs), max=max(xs))


def model_bin(t_arrival: float, action_submit: float, action_added: float,
              action_first: Optional[float]) -> str:
    """Where the MODEL places an arrival relative to the action it is simulating."""
    if t_arrival < action_submit - 1e-9:
        return "pre_inj"
    if t_arrival < action_added - 1e-9:
        return "pre_fe"
    if action_first is None or t_arrival < action_first - 1e-9:
        return "in_window"
    return "post"


def per_arrival(trials: Sequence[tr.Trial], sim: EngineSim,
                measured: Dict[Tuple[str, str, int, int], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per compared background arrival: what the model predicted it would suffer, what it
    measured, which phase each of them puts it in, and the action's own timings in both."""
    rows: List[Dict[str, Any]] = []
    for t in trials:
        w, o = t.arms["with"], t.arms["without"]
        res_w = sim.run(tr._arm_requests(w, include_action=True))
        res_o = sim.run(tr._arm_requests(o, include_action=False))
        pw, po = res_w["per_request"], res_o["per_request"]
        acts = sorted(w.action, key=lambda r: float(r["t_submit"]))
        if not acts:
            continue
        a0 = acts[0]
        a_pred = pw.get(str(a0.get("rid")), {})
        a_submit = float(a0["t_submit"]) - w.t0_trace
        a_added = float(a_pred.get("t_added") or a_submit)
        a_first = a_pred.get("t_first")
        a_last_first = max((pw.get(str(r.get("rid")), {}).get("t_first") or 0.0) for r in acts)
        a_meas_ttft = float(a0.get("ttft_s") or 0.0)
        w_rows = {r.get("idx"): r for r in w.background if r.get("kind") in tr.COMPARED_KINDS}
        o_rows = {r.get("idx"): r for r in o.background if r.get("kind") in tr.COMPARED_KINDS}
        for idx in sorted(set(w_rows) & set(o_rows)):
            if idx is None:
                continue
            pa = pw.get(str(w_rows[idx].get("rid")), {}).get("ttft_s")
            pb = po.get(str(o_rows[idx].get("rid")), {}).get("ttft_s")
            if pa is None or pb is None:
                continue
            m = measured.get((t.load, t.action, t.trial, int(idx)))
            if m is None:
                continue
            arr = float(w_rows[idx]["t_submit"]) - w.t0_trace
            rows.append(dict(
                load=t.load, action=t.action, trial=t.trial, idx=int(idx),
                measured_delta_s=m["delta_s"], predicted_delta_s=float(pa) - float(pb),
                measured_bin=m["bin"], model_bin=model_bin(arr, a_submit, a_added, a_last_first),
                inflight=m["inflight"], offset=m["offset"],
                action_front_end_predicted_s=a_added - a_submit,
                action_ttft_predicted_s=(a_last_first - a_submit) if a_last_first else None,
                action_ttft_measured_s=a_meas_ttft))
    return rows


def by_bin(rows: Sequence[Dict[str, Any]], keyfn, binfield: str = "measured_bin") -> Dict[str, Any]:
    g: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        g[str(keyfn(r))][r[binfield]].append(r)
    out: Dict[str, Any] = {}
    for k, bins in sorted(g.items()):
        cell = {}
        for b, rs in sorted(bins.items()):
            meas = [r["measured_delta_s"] for r in rs]
            pred = [r["predicted_delta_s"] for r in rs]
            cell[b] = dict(n=len(rs), measured=_dist(meas), predicted=_dist(pred),
                           sum_ratio=(sum(pred) / sum(meas)) if abs(sum(meas)) > 1e-9 else None,
                           median_signed_s=statistics.median([p - m for p, m in
                                                              zip(pred, meas)]),
                           share_of_measured_total=None)
        total = sum(abs(r["measured_delta_s"]) for r in rows if str(keyfn(r)) == k)
        for b, c in cell.items():
            if total > 0:
                c["share_of_measured_total"] = sum(
                    abs(r["measured_delta_s"]) for r in bins[b]) / total
        out[k] = cell
    return out


def bin_counts(rows: Sequence[Dict[str, Any]], keyfn) -> Dict[str, Any]:
    """The model's phase against the measurement's phase for the same arrival. A model that
    prices a phase correctly but puts the wrong arrivals in it fails here and nowhere else."""
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    out = {}
    for k, rs in sorted(g.items()):
        conf: Dict[str, int] = defaultdict(int)
        for r in rs:
            mb = r["measured_bin"]
            mb_coarse = "in_window" if mb in e1d.IN_WINDOW_BINS else mb
            conf["%s->%s" % (mb_coarse, r["model_bin"])] += 1
        measured_counts: Dict[str, int] = defaultdict(int)
        model_counts: Dict[str, int] = defaultdict(int)
        for r in rs:
            mb = r["measured_bin"]
            measured_counts["in_window" if mb in e1d.IN_WINDOW_BINS else mb] += 1
            model_counts[r["model_bin"]] += 1
        out[k] = dict(n=len(rs), measured=dict(sorted(measured_counts.items())),
                      model=dict(sorted(model_counts.items())),
                      confusion=dict(sorted(conf.items())),
                      agreement=sum(v for kk, v in conf.items()
                                    if kk.split("->")[0] == kk.split("->")[1]) / max(len(rs), 1))
    return out


def action_timing(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The action's own front-end window and total TTFT, predicted against measured, per action
    and load. This is where a front-end mispricing shows up directly."""
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen = set()
    for r in rows:
        k = (r["load"], r["action"], r["trial"])
        if k in seen:
            continue
        seen.add(k)
        g["%s|%s" % (r["action"], r["load"])].append(r)
    out = {}
    for k, rs in sorted(g.items()):
        fe = [r["action_front_end_predicted_s"] for r in rs]
        pt = [r["action_ttft_predicted_s"] for r in rs if r["action_ttft_predicted_s"]]
        mt = [r["action_ttft_measured_s"] for r in rs if r["action_ttft_measured_s"]]
        out[k] = dict(n=len(rs), front_end_predicted=_dist(fe),
                      action_ttft_predicted=_dist(pt), action_ttft_measured=_dist(mt),
                      ttft_ratio=((statistics.median(pt) / statistics.median(mt))
                                  if pt and mt else None))
    return out


def measured_front_end(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """StudyENG1d's own front-end window for the action: its measured TTFT minus the engine
    prefill span the plugin recorded, which is the definition ENG1d used for the pre_fe bin."""
    mt = e1d.measured_trials()
    g: Dict[str, List[float]] = defaultdict(list)
    bodies: Dict[str, List[float]] = defaultdict(list)
    for t in trials:
        rec = mt.get((t.load, t.action, t.trial))
        if not rec:
            continue
        acts = sorted(t.arms["with"].action, key=lambda r: float(r["t_submit"]))
        if not acts:
            continue
        ttft = float(acts[0].get("ttft_s") or 0.0)
        pf = float(rec.get("action_pf_s") or 0.0)
        if ttft <= 0 or pf <= 0:
            continue
        g["%s|%s" % (t.action, t.load)].append(ttft - pf)
        bodies["%s|%s" % (t.action, t.load)].append(float(acts[0].get("body_mb") or 0.0))
    return {k: dict(window=_dist(v), body_mb_median=statistics.median(bodies[k]))
            for k, v in sorted(g.items())}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="pol4")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out_dir = Path(args.out_dir) if args.out_dir else (_root() / OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    trials, audit = e1d.load_trials("fit")
    measured = e1d.measured_arrivals(fence=True)
    sim = make_sim(args.model)
    rows = per_arrival(trials, sim, measured)
    print("ENG1d FIT: %d trials, %d compared arrivals joined to a measured bin"
          % (len(trials), len(rows)))

    out = dict(
        study="StudyPOL5-engine Part 1, diagnosis",
        model=args.model, holdout_audit=audit,
        n_arrivals=len(rows),
        by_action=by_bin(rows, lambda r: r["action"]),
        by_action_load=by_bin(rows, lambda r: "%s|%s" % (r["action"], r["load"])),
        by_measured_bin=by_bin(rows, lambda r: "ALL"),
        bin_counts_by_action=bin_counts(rows, lambda r: r["action"]),
        bin_counts_by_action_load=bin_counts(rows, lambda r: "%s|%s" % (r["action"], r["load"])),
        action_timing=action_timing(rows),
        measured_front_end=measured_front_end(trials),
        label="StudyENG1d FIT pairs, out of sample for pol4 (no pol4 coefficient saw an ENG1d "
              "datum); the measured bins are StudyENG1d's own per-arrival record")
    sys.path.insert(0, str(_root() / "experiments" / "lib"))
    from _provenance import stamp
    out["_provenance"] = stamp(script="policy/diagnose_pol5.py", model=None, device=None,
                               n=len(rows), args=vars(args))
    (out_dir / "pol5_diagnosis.json").write_text(json.dumps(out, indent=1, default=str))

    for action in ("mono11k", "piece2048", "piece1024"):
        cell = out["by_action"].get(action, {})
        print("== %s" % action)
        for b in ("pre_inj", "pre_fe", "0-25", "25-50", "50-75", "75-100", "post"):
            c = cell.get(b)
            if not c:
                continue
            print("   %-7s n%4d  measured sum %8.3f  predicted sum %8.3f  ratio %s  share %.2f"
                  % (b, c["n"], c["measured"]["sum"], c["predicted"]["sum"],
                     ("%.2f" % c["sum_ratio"]) if c["sum_ratio"] else "n/a",
                     c["share_of_measured_total"] or 0.0))
        bc = out["bin_counts_by_action"][action]
        print("   bin counts measured %s | model %s | agreement %.3f"
              % (bc["measured"], bc["model"], bc["agreement"]))
    print("wrote %s" % (out_dir / "pol5_diagnosis.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
