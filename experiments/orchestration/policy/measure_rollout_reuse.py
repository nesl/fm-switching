#!/usr/bin/env python3
"""StudyLIVE2-perf Option C, MEASUREMENT ONLY: how much do consecutive candidates share?

No implementation of incremental rollouts, and nothing here changes a decision. This script
WRAPS `Rollout.run` from outside, records what each call was given and what it returned, and
reports how much consecutive candidates within one decision period have in common. The design
note (`reports/study_live2_perf.md`, "Bounding decision cost: options", Option C) says to measure
the reuse before building anything, because a small number kills the option cheaply.

THREE QUANTITIES, because they answer different questions.

  1. CANDIDATES PER PERIOD. Reuse is worth nothing where there is only one rollout in a period.

  2. INPUT SHARING, component by component. Of the state a rollout reads, how much is identical
     to the previous candidate's: each device's belief (probabilities, size, staleness), the
     episode list, the pending list, the in-flight list, the jobs, the clock and the backlog.
     This is an upper bound on what any incremental scheme could reuse, and the per-device part
     is the quantity Option 0 already exploits.

  3. OUTPUT SHARING AND THE DIVERGENCE POINT. Of the trajectory a rollout produces (its
     deliveries and opportunities), what fraction of entries is identical to the previous
     candidate's, and at what simulated time does the first difference appear, as a fraction of
     the horizon H. THIS IS THE DECIDING NUMBER: an incremental rollout can only reuse the
     prefix of the trajectory before the first divergence, so if admitting one item perturbs the
     schedule immediately, there is nothing to carry forward however similar the inputs look.

Usage (dry-run fixtures only, CPU):
  measure_rollout_reuse.py --sizes 8,32,64 --window-s 120 --out results/.../rollout_reuse.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
ROOT = ORCH.parents[1]
# This file lives in `policy/`, which Python puts on sys.path[0] when it is run as a script.
# `policy/coordinator.py` would then shadow `live2/coordinator.py`, which is the one
# `live2/fix_checks.py` imports by bare name, and it cannot be imported outside its package.
# So the script's own directory comes off the path before anything else goes on.
sys.path = [q for q in sys.path if q and Path(q).resolve() != HERE]
for _p in (str(ORCH), str(ORCH / "live2"), str(ORCH / "live2" / "fleet"),
           str(ORCH / "live2" / "scorer"), str(ORCH / "live"), str(ORCH / "baselines"),
           str(ORCH / "sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------- fingerprints
def _belief(b) -> Tuple:
    return (tuple(sorted((str(t), round(float(p), 12)) for t, p in b.probs.items())),
            int(b.size_tokens), round(float(b.staleness_s), 9))


def _device(d) -> Tuple:
    return (tuple(sorted((rep, _belief(b)) for rep, b in d.history.items())),
            len(d.episodes), str(d.qtype),
            round(float(getattr(d.link, "rtt_s", 0.0)), 9))


def _item(p) -> Tuple:
    return (str(p.item_id), str(p.kind), str(p.device), round(float(getattr(p, "t", 0.0)), 9),
            int(getattr(p, "tokens", 0) or 0))


def _job(j) -> Tuple:
    return (str(j.device), str(getattr(j, "rep", "")), int(j.pieces_done), int(j.pieces_total),
            bool(getattr(j, "answered", False)), round(float(getattr(j, "deadline", 0.0)), 9))


def fleet_fingerprint(f) -> Dict[str, Any]:
    return dict(t=round(float(f.t), 9),
                gpu_backlog_s=round(float(getattr(f, "gpu_backlog_s", 0.0)), 9),
                devices={str(k): _device(v) for k, v in f.devices.items()},
                pending=[_item(p) for p in f.pending],
                in_flight=[_item(p) for p in getattr(f, "in_flight", ())],
                jobs={str(k): _job(v) for k, v in f.jobs.items()})


def result_fingerprint(r) -> Dict[str, Any]:
    def row(x):
        return tuple(sorted((str(k), (round(v, 9) if isinstance(v, float) else
                                      (str(v) if not isinstance(v, (int, bool)) else v)))
                            for k, v in x.items() if not isinstance(v, (dict, list))))
    return dict(deliveries=[row(x) for x in r.deliveries],
                opportunities=[row(x) for x in r.opportunities],
                u_hat=round(float(r.u_hat), 12), terminal=round(float(r.terminal), 12),
                total=round(float(r.total), 12))


def _first_time(rows, fp) -> Optional[float]:
    """The simulated time of the first row where two trajectories differ.

    Rows carry absolute run-clock times, so the caller turns this into a fraction of the horizon
    by subtracting the rollout's own start (`t0`).
    """
    a, b = rows, fp
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return _time_of(a[i])
    if len(a) != len(b):
        longer = a if len(a) > len(b) else b
        return _time_of(longer[min(len(a), len(b))])
    return None


def _time_of(row) -> Optional[float]:
    d = dict(row)
    for k in ("start", "delivered_at", "t", "capture_at", "deadline"):
        if k in d and isinstance(d[k], (int, float)):
            return float(d[k])
    return None


def _share(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Component-by-component identity between two consecutive candidates' INPUT states."""
    da, db = a["devices"], b["devices"]
    keys = set(da) | set(db)
    same_dev = sum(1 for k in keys if da.get(k) == db.get(k))
    ja, jb = a["jobs"], b["jobs"]
    jkeys = set(ja) | set(jb)
    same_job = sum(1 for k in jkeys if ja.get(k) == jb.get(k))
    pa, pb = a["pending"], b["pending"]
    common_pending = sum(1 for x, y in zip(pa, pb) if x == y)
    return dict(
        n_devices=len(keys),
        devices_identical=same_dev,
        device_fraction=(round(same_dev / len(keys), 6) if keys else None),
        n_jobs=len(jkeys), jobs_identical=same_job,
        job_fraction=(round(same_job / len(jkeys), 6) if jkeys else None),
        pending_len=(len(pa), len(pb)),
        pending_common_prefix=common_pending,
        pending_identical=(pa == pb),
        in_flight_identical=(a["in_flight"] == b["in_flight"]),
        clock_identical=(a["t"] == b["t"]),
        backlog_identical=(a["gpu_backlog_s"] == b["gpu_backlog_s"]))


def _out_share(a: Dict[str, Any], b: Dict[str, Any], horizon: float,
               t0: float = 0.0) -> Dict[str, Any]:
    out = {}
    for name in ("deliveries", "opportunities"):
        xa, xb = a[name], b[name]
        n = max(len(xa), len(xb))
        same = sum(1 for x, y in zip(xa, xb) if x == y)
        prefix = 0
        for x, y in zip(xa, xb):
            if x != y:
                break
            prefix += 1
        t_div = _first_time(xa, xb)
        out[name] = dict(n=(len(xa), len(xb)), identical_rows=same,
                         identical_fraction=(round(same / n, 6) if n else None),
                         identical_prefix=prefix,
                         prefix_fraction=(round(prefix / n, 6) if n else None),
                         first_divergence_t=t_div,
                         first_divergence_fraction_of_H=(
                             round(max(0.0, t_div - t0) / horizon, 6)
                             if (t_div is not None and horizon > 0) else None))
    out["totals_identical"] = (a["total"] == b["total"])
    return out


# ---------------------------------------------------------------- the measurement
def measure(n_devices: int, window_s: float, seed: int = 1, h: float = 1.0) -> Dict[str, Any]:
    import fix_checks as FX
    from policy.rollout import Rollout

    periods: List[List[Tuple[Dict[str, Any], Dict[str, Any]]]] = []
    current: Dict[str, Any] = dict(key=None, calls=[])
    real_run = Rollout.run
    horizon = {"h": float(h)}

    def run(self, fleet, *a, **kw):
        before = fleet_fingerprint(fleet)
        res = real_run(self, fleet, *a, **kw)
        after = result_fingerprint(res)
        horizon["h"] = float(self.params.H)
        key = before["t"]
        if current["key"] is None:
            current["key"] = key
        if key != current["key"]:
            if current["calls"]:
                periods.append(current["calls"])
            current["key"], current["calls"] = key, []
        current["calls"].append((before, after))
        return res

    Rollout.run = run
    try:
        r = FX._cell(n_dashcam=n_devices // 2, n_robot=n_devices - n_devices // 2,
                     window_s=window_s, seed=seed, h=h)
    finally:
        Rollout.run = real_run
    if current["calls"]:
        periods.append(current["calls"])

    per_period = [len(p) for p in periods]
    multi = [p for p in periods if len(p) > 1]
    in_rows: List[Dict[str, Any]] = []
    out_rows: List[Dict[str, Any]] = []
    for p in multi:
        for i in range(1, len(p)):
            in_rows.append(_share(p[i - 1][0], p[i][0]))
            out_rows.append(_out_share(p[i - 1][1], p[i][1], horizon["h"],
                                       t0=float(p[i][0]["t"])))

    def med(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.median(xs), 6) if xs else None

    def frac_true(xs):
        xs = list(xs)
        return round(sum(1 for x in xs if x) / len(xs), 6) if xs else None

    dv = [r_["first_divergence_fraction_of_H"] for r_ in
          (o["deliveries"] for o in out_rows)]
    return dict(
        n_devices=n_devices, window_s=window_s, seed=seed, H_s=h,
        is_measurement=False, label="DRY-RUN FIXTURE, not a measurement of the policy",
        n_rollouts=sum(per_period), n_periods=len(periods),
        n_periods_with_more_than_one_rollout=len(multi),
        rollouts_per_period=dict(
            min=(min(per_period) if per_period else None),
            median=med(per_period), p90=(sorted(per_period)[int(0.9 * len(per_period))]
                                         if per_period else None),
            max=(max(per_period) if per_period else None)),
        n_consecutive_pairs=len(in_rows),
        input_sharing=dict(
            device_fraction_median=med([x["device_fraction"] for x in in_rows]),
            device_fraction_min=(min([x["device_fraction"] for x in in_rows
                                      if x["device_fraction"] is not None], default=None)),
            job_fraction_median=med([x["job_fraction"] for x in in_rows]),
            pending_identical_fraction=frac_true(x["pending_identical"] for x in in_rows),
            in_flight_identical_fraction=frac_true(x["in_flight_identical"] for x in in_rows),
            clock_identical_fraction=frac_true(x["clock_identical"] for x in in_rows),
            backlog_identical_fraction=frac_true(x["backlog_identical"] for x in in_rows)),
        output_sharing=dict(
            deliveries_identical_fraction_median=med(
                [o["deliveries"]["identical_fraction"] for o in out_rows]),
            deliveries_prefix_fraction_median=med(
                [o["deliveries"]["prefix_fraction"] for o in out_rows]),
            opportunities_identical_fraction_median=med(
                [o["opportunities"]["identical_fraction"] for o in out_rows]),
            opportunities_prefix_fraction_median=med(
                [o["opportunities"]["prefix_fraction"] for o in out_rows]),
            first_divergence_fraction_of_H_median=med(dv),
            totals_identical_fraction=frac_true(o["totals_identical"] for o in out_rows)),
        decision_latency_ms=r.get("decision_latency_ms"),
        state_value_cache=(r.get("arm_stats") or {}).get("state_value_cache"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", default="8,32,64")
    ap.add_argument("--window-s", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--h", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rows = [measure(int(n), a.window_s, a.seed, a.h) for n in a.sizes.split(",")]
    res = dict(check="option_c_rollout_reuse", is_measurement=False, rows=rows)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
