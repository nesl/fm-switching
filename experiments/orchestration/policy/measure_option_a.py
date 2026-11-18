#!/usr/bin/env python3
"""StudyLIVE2-perf Option A: the OFFLINE divergence study. No arm changes, nothing enabled.

User decision 2026-11-18, design log D110. Option A would price a period's SH admissions as
deadline-order PREFIXES rather than candidate by candidate. That is an ACTION-SPACE RESTRICTION,
so this study measures what it would cost in decision quality before anyone builds it. The
pre-registration, written and committed before this file, is `reports/study_live2_perf.md`
section "Option A study" (A.1 to A.4) and is the authority on every definition here.

WHAT IT DOES. It runs an ordinary dry cell, unmodified, and WATCHES: a wrapper around
`Coordinator._admit_score` records each period's SH candidates in the order the arm raises them
(already deadline order), the admits the live policy makes, and a snapshot of the fleet taken
BEFORE that period's first SH admit. Afterwards it recomputes, from those snapshots, the DeltaJ
of the per-candidate set, of every deadline-order prefix, and of the doubling ladder, all through
the SAME rollout. Nothing in the decision path is touched: the wrapper forwards to the real
method and returns its result unchanged.

CPU only, committed fixtures, no GPU, no live run, and no result here is a measurement of policy
behaviour.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import sys

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
ROOT = ORCH.parents[1]
sys.path = [q for q in sys.path if q and Path(q).resolve() != HERE]
for _p in (str(ORCH), str(ORCH / "live2"), str(ORCH / "live2" / "fleet"),
           str(ORCH / "live2" / "scorer"), str(ORCH / "live"), str(ORCH / "baselines"),
           str(ORCH / "sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = ROOT / "results/orchestration/live2/coord/perf"


def _ladder(n: int) -> List[int]:
    """The doubling ladder: 0, 1, 2, 4, 8, ... capped at n, plus n itself."""
    ks, k = [0], 1
    while k < n:
        ks.append(k)
        k *= 2
    if n not in ks:
        ks.append(n)
    return sorted(set(k for k in ks if 0 <= k <= n))


def _dist(xs: Sequence[float]) -> Dict[str, Any]:
    v = sorted(float(x) for x in xs)
    if not v:
        return dict(n=0)

    def q(p):
        return round(v[min(int(p * len(v)), len(v) - 1)], 9)

    return dict(n=len(v), median=round(statistics.median(v), 9), p90=q(0.90),
                min=round(v[0], 9), max=round(v[-1], 9), sum=round(sum(v), 9))


def _is_prefix(taken: Sequence[bool]) -> bool:
    """True when the admitted indices are 1..m with no gap, which is what a prefix can express."""
    m = sum(1 for t in taken if t)
    return list(taken[:m]) == [True] * m and not any(taken[m:])


def collect(n_devices: int, window_s: float, seed: int, h: float,
            mu: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Any]:
    """Run one ordinary dry cell and record each period's SH candidates and the fleet before it."""
    import fix_checks as FX
    from policy import coordinator as CO
    from policy.rollout import clone_for_rollout

    periods: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {"key": None}
    real = CO.Coordinator._admit_score

    def spy(self, fleet, req, items, jobs):
        is_sh = getattr(req, "task", None) == "SH"
        if is_sh:
            key = round(float(fleet.t), 9)
            if cur["key"] != key:
                cur["key"] = key
                cur["entry"] = dict(
                    t=key,
                    # the snapshot is taken BEFORE this period's first SH admit: an admit only
                    # mutates `fleet.pending`, `fleet.jobs` and `dev.episodes`, and
                    # `clone_for_rollout` gives independent containers for all three
                    snapshot=clone_for_rollout(fleet),
                    backlog_queued_tokens=sum(max(int(p.tokens), 0) for p in fleet.pending),
                    backlog_running_requests=len(fleet.in_flight),
                    backlog_queued_requests=len(fleet.pending),
                    cands=[])
                periods.append(cur["entry"])
        res = real(self, fleet, req, items, jobs)
        if is_sh:
            cur["entry"]["cands"].append(dict(
                items=list(items), jobs=dict(jobs or {}),
                delta_j_live=float(res["delta_j"]), taken=bool(res["delta_j"] > 0),
                device=str(req.device),
                deadline=(float(req.deadline) if req.deadline is not None else None),
                capture_at=(float(getattr(req, "capture_at", 0.0) or 0.0))))
        return res

    holder: Dict[str, Any] = {}
    real_arm = FX._arm

    def arm(*a, **kw):
        m = real_arm(*a, **kw)
        holder["arm"] = m
        return m

    CO.Coordinator._admit_score = spy
    FX._arm = arm
    try:
        res = FX._cell(n_dashcam=n_devices // 2, n_robot=n_devices - n_devices // 2,
                       window_s=window_s, seed=seed, h=h, mu=mu)
    finally:
        CO.Coordinator._admit_score = real
        FX._arm = real_arm
    return periods, res, holder["arm"]


def score_periods(periods: Sequence[Dict[str, Any]], arm) -> List[Dict[str, Any]]:
    """Recompute DeltaJ for the per-candidate set, every prefix, and the doubling ladder."""
    ro = arm.co.rollout
    rows: List[Dict[str, Any]] = []
    for ent in periods:
        cands = ent["cands"]
        n = len(cands)
        if n == 0:
            continue
        snap = ent["snapshot"]
        if hasattr(ro, "state_value_cache"):
            ro.state_value_cache().clear()
        items_of = [c["items"] for c in cands]
        taken = [c["taken"] for c in cands]

        def dj(sets: Sequence[Sequence[Any]], ref_total: float) -> float:
            flat: List[Any] = []
            for s in sets:
                flat += list(s)
            if not flat:
                return 0.0
            return float(ro.run(snap, extra_pending=flat).total) - ref_total

        t0 = time.perf_counter()
        ref_total = float(ro.run(snap).total)
        t_ref = time.perf_counter() - t0

        # the per-candidate set, scored by the SAME whole-set function as the others
        t0 = time.perf_counter()
        dj_pc = dj([items_of[i] for i in range(n) if taken[i]], ref_total)
        t_pc_set = time.perf_counter() - t0

        # every deadline-order prefix
        t0 = time.perf_counter()
        pref = {0: 0.0}
        for k in range(1, n + 1):
            pref[k] = dj(items_of[:k], ref_total)
        t_exh = time.perf_counter() - t0
        k_star = max(pref, key=lambda k: pref[k])

        # the doubling ladder, reusing the prefixes already computed (the ladder is a subset)
        ladder = _ladder(n)
        k_dbl = max(ladder, key=lambda k: pref[k])

        rows.append(dict(
            t=ent["t"], n_candidates=n,
            n_admitted_per_candidate=sum(1 for x in taken if x),
            per_candidate_is_prefix=_is_prefix(taken),
            admitted_indices=[i + 1 for i, x in enumerate(taken) if x],
            delta_j_per_candidate=dj_pc,
            delta_j_best_prefix=pref[k_star], k_star=k_star,
            delta_j_doubling=pref[k_dbl], k_doubling=k_dbl,
            ladder=ladder,
            loss_best_prefix=dj_pc - pref[k_star],
            loss_doubling=dj_pc - pref[k_dbl],
            quantisation_cost=pref[k_star] - pref[k_dbl],
            best_prefix_differs_from_per_candidate=bool(
                sorted([i + 1 for i, x in enumerate(taken) if x]) != list(range(1, k_star + 1))),
            backlog_queued_tokens=ent["backlog_queued_tokens"],
            backlog_running_requests=ent["backlog_running_requests"],
            backlog_queued_requests=ent["backlog_queued_requests"],
            rollouts_per_candidate=2 * n, rollouts_exhaustive=n + 2,
            rollouts_doubling=len(ladder) + 1,
            wall_reference_s=t_ref, wall_per_candidate_set_s=t_pc_set,
            wall_exhaustive_s=t_exh,
            delta_j_live_sum=float(sum(c["delta_j_live"] for c in cands if c["taken"]))))
    return rows


def _terciles(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    vals = sorted(float(r[key]) for r in rows)
    if not vals:
        return {}
    lo, hi = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    out: Dict[str, List[Dict[str, Any]]] = {"T1_low": [], "T2_mid": [], "T3_high": []}
    for r in rows:
        v = float(r[key])
        out["T1_low" if v <= lo else ("T2_mid" if v <= hi else "T3_high")].append(r)
    return dict(edges=dict(lo=lo, hi=hi),
                buckets={k: summarise(v) for k, v in out.items()})


def summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return dict(n_periods=0)
    n = len(rows)
    not_prefix = [r for r in rows if not r["per_candidate_is_prefix"]]
    differs = [r for r in rows if r["best_prefix_differs_from_per_candidate"]]
    tot_pc = sum(r["delta_j_per_candidate"] for r in rows)
    return dict(
        n_periods=n,
        n_candidates=_dist([r["n_candidates"] for r in rows]),
        fraction_per_candidate_not_a_prefix=round(len(not_prefix) / n, 6),
        n_per_candidate_not_a_prefix=len(not_prefix),
        fraction_best_prefix_differs=round(len(differs) / n, 6),
        n_best_prefix_differs=len(differs),
        loss_best_prefix=_dist([r["loss_best_prefix"] for r in rows]),
        loss_doubling=_dist([r["loss_doubling"] for r in rows]),
        quantisation_cost=_dist([r["quantisation_cost"] for r in rows]),
        total_delta_j_per_candidate=round(tot_pc, 9),
        loss_sum_fraction_of_total=(
            round(sum(r["loss_best_prefix"] for r in rows) / tot_pc, 6)
            if tot_pc else None),
        loss_sum_fraction_of_total_doubling=(
            round(sum(r["loss_doubling"] for r in rows) / tot_pc, 6) if tot_pc else None),
        loss_where_already_a_prefix=_dist(
            [r["loss_best_prefix"] for r in rows if r["per_candidate_is_prefix"]]),
        loss_where_not_a_prefix=_dist(
            [r["loss_best_prefix"] for r in rows if not r["per_candidate_is_prefix"]]),
        rollouts=dict(per_candidate=_dist([r["rollouts_per_candidate"] for r in rows]),
                      exhaustive=_dist([r["rollouts_exhaustive"] for r in rows]),
                      doubling=_dist([r["rollouts_doubling"] for r in rows])))


def project(rows: Sequence[Dict[str, Any]], res: Dict[str, Any]) -> Dict[str, Any]:
    """A PROJECTION, not a measurement: decision time scaled by the rollout count.

    The measured per-rollout cost is this study's own: the exhaustive pass's wall time over the
    rollouts it used. The projected decision time of a method is the live decision latency times
    that method's rollout count over the per-candidate count, which assumes decision time is
    dominated by rollouts and proportional to their number. Both assumptions are stated because
    both are approximations: a period's non-rollout work does not shrink, so the projection is
    OPTIMISTIC for the cheaper methods.
    """
    lat = res.get("decision_latency_ms") or {}
    wall = sum(r["wall_exhaustive_s"] for r in rows)
    nroll = sum(r["rollouts_exhaustive"] - 1 for r in rows)
    per_rollout_ms = (1000.0 * wall / nroll) if nroll else None
    ratios = [r["rollouts_doubling"] / r["rollouts_per_candidate"] for r in rows
              if r["rollouts_per_candidate"]]
    med_ratio = statistics.median(ratios) if ratios else None
    return dict(
        is_projection=True,
        method="live decision latency scaled by (doubling rollouts / per-candidate rollouts); "
               "assumes decision time is rollout-dominated and linear in rollout count, so it "
               "is OPTIMISTIC for the cheaper method because non-rollout work does not shrink",
        measured_per_rollout_ms=(round(per_rollout_ms, 6) if per_rollout_ms else None),
        rollout_ratio_doubling_over_per_candidate=dict(
            median=(round(med_ratio, 6) if med_ratio else None),
            dist=_dist(ratios)),
        live_decision_latency_ms=lat,
        projected_doubling_p50_ms=(round(lat["p50"] * med_ratio, 4)
                                   if (lat.get("p50") and med_ratio) else None),
        projected_doubling_p99_ms=(round(lat["p99"] * med_ratio, 4)
                                   if (lat.get("p99") and med_ratio) else None))


def worked_example(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One period whose per-candidate set is not a prefix, with the loss it implies."""
    bad = [r for r in rows if not r["per_candidate_is_prefix"]]
    if not bad:
        return None
    r = max(bad, key=lambda x: abs(x["loss_best_prefix"]))
    return dict(
        t=r["t"], n_candidates=r["n_candidates"],
        admitted_indices_in_deadline_order=r["admitted_indices"],
        why_no_prefix_can_express_it=(
            "the admitted indices are %s, which is not 1..%d, so a later-deadline candidate was "
            "admitted while an earlier one was declined and no k reproduces the set"
            % (r["admitted_indices"], len(r["admitted_indices"]))),
        delta_j_per_candidate=r["delta_j_per_candidate"],
        delta_j_best_prefix=r["delta_j_best_prefix"], k_star=r["k_star"],
        loss_best_prefix=r["loss_best_prefix"],
        backlog_queued_tokens=r["backlog_queued_tokens"],
        backlog_running_requests=r["backlog_running_requests"])


def sanity_single_candidate(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Where a period has exactly ONE SH candidate, all three methods must agree exactly."""
    one = [r for r in rows if r["n_candidates"] == 1]
    bad = [r for r in one
           if not (r["delta_j_per_candidate"] == r["delta_j_best_prefix"]
                   == r["delta_j_doubling"])]
    return dict(n_periods_with_one_candidate=len(one), n_disagreeing=len(bad),
                agree=(len(bad) == 0),
                note="with n = 1 the prefixes are the empty set and the single candidate, so an "
                     "exhaustive search and a doubling ladder both contain the per-candidate "
                     "answer; a disagreement here would mean the three DeltaJ definitions are "
                     "not the same function of the admitted set",
                first_disagreement=(bad[0] if bad else None))


def run_size(n_devices: int, window_s: float, seed: int, h: float, mu: str) -> Dict[str, Any]:
    t0 = time.time()
    periods, res, arm = collect(n_devices, window_s, seed, h, mu)
    rows = score_periods(periods, arm)
    return dict(
        n_devices=n_devices, window_s=window_s, seed=seed, H_s=h, mu_mode=mu,
        n_periods_with_sh_candidates=len(rows),
        overall=summarise(rows),
        by_backlog_tercile_queued_tokens=_terciles(rows, "backlog_queued_tokens"),
        by_backlog_tercile_running_requests=_terciles(rows, "backlog_running_requests"),
        projection=project(rows, res),
        worked_example=worked_example(rows),
        sanity_single_candidate=sanity_single_candidate(rows),
        live_decision_latency_ms=res.get("decision_latency_ms"),
        study_wall_s=round(time.time() - t0, 2))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", default="8,32,64,128")
    ap.add_argument("--window-s", type=float, default=180.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--h", type=float, default=1.0)
    ap.add_argument("--mu", default="none")
    ap.add_argument("--out", default=str(OUT / "perf_optionA_divergence.json"))
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",")]
    rows = []
    for n in sizes:
        rows.append(run_size(n, a.window_s, a.seed, a.h, a.mu))
        print("done %d devices: %d periods" % (n, rows[-1]["n_periods_with_sh_candidates"]),
              flush=True)
    # THE SANITY FIXTURE, which the main sizes cannot provide: a single dashcam, so every period
    # raises exactly ONE SH candidate and all three methods must agree exactly. A size that
    # produces no one-candidate period leaves the check vacuous, which is why it gets its own run.
    sanity = run_size(2, a.window_s, a.seed, a.h, a.mu)
    print("done sanity fixture (2 devices, 1 dashcam): %d periods"
          % sanity["n_periods_with_sh_candidates"], flush=True)
    from _provenance import stamp
    res = dict(check="option_a_offline_divergence", is_measurement=False,
               label="offline divergence study on committed dry-run fixtures; no arm was "
                     "changed and Option A is not implemented",
               configuration=dict(window_s=a.window_s, seed=a.seed, H_s=a.h, mu_mode=a.mu,
                                  option_0="on", sh_cost="rollout"),
               rows=rows,
               sanity_fixture_one_candidate_per_period=dict(
                   n_devices=2, n_periods=sanity["n_periods_with_sh_candidates"],
                   candidates_per_period=sanity["overall"]["n_candidates"],
                   check=sanity["sanity_single_candidate"],
                   loss_best_prefix=sanity["overall"]["loss_best_prefix"],
                   loss_doubling=sanity["overall"]["loss_doubling"]),
               _provenance=stamp(script="measure_option_a.py", model="none",
                                 device="flash_cpu",
                                 n=sum(r["n_periods_with_sh_candidates"] for r in rows),
                                 args=a))
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print("wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
