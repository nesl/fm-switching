"""M4: how long a decision takes.

Spec 10.2 lists coordinator, rollout and continuation overhead as a remaining input, and spec 9
sets the continuation resolution from it. This measures the decision cost of THIS implementation
on this CPU, which is a lower bound on what a deployment would see and is not a claim about the
H100 host.
"""
from __future__ import annotations

import statistics
import time
from typing import Any, Dict, List, Sequence


def load_decision_latency_s(horizon_s: float = 0.75, pending_items: int = 4,
                            path=None) -> Dict[str, Any]:
    """This row's own M4 measurement, read back so the policy can CHARGE its decision latency on
    the question-first path (addendum A2 as revised).

    Returns the nearest measured cell rather than an interpolation, for the same reason the
    duration tables do: there is no evidence between the measured points."""
    import json
    from pathlib import Path as _P
    f = _P(path) if path else (_P(__file__).resolve().parents[3]
                               / "results/orchestration/pol2/pol2_m4_decision_time.json")
    if not f.exists():
        return dict(available=False, seconds=None, source=str(f),
                    reason="M4 has not been run on this machine")
    rows = json.loads(f.read_text())["rows"]
    best = min(rows, key=lambda r: (abs(r["horizon_s"] - horizon_s),
                                    abs(r["pending_items"] - pending_items)))
    return dict(available=True, seconds=float(best["p50_s"]), horizon_s=best["horizon_s"],
                pending_items=best["pending_items"], source=str(f),
                basis="M4 p50 of one DeltaJ_H at the nearest measured cell, flash CPU only")


def _timeit(fn, repeats: int) -> Dict[str, float]:
    xs: List[float] = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        xs.append(time.perf_counter() - t)
    xs.sort()
    return dict(n=repeats, mean_s=statistics.fmean(xs), p50_s=statistics.median(xs),
                p95_s=xs[min(len(xs) - 1, int(0.95 * len(xs)))], min_s=xs[0], max_s=xs[-1])


def measure_ghat_time(co, fleet, repeats: int = 200) -> Dict[str, Any]:
    """The v3.1 addendum puts a Ghat computation in front of EVERY request, so its cost belongs in
    M4 beside the rollout's."""
    from .escalation import EscalationRequest
    reqs = dict(
        sh=EscalationRequest("d0", "SH", 0.0, uncertainty=1.5),
        rc_known_type=EscalationRequest("d0", "RC", 0.0, qtype="counting_objects_events",
                                        temporal_reference_s=60.0, device_window_s=10.0),
        rc_unknown_type=EscalationRequest("d0", "RC", 0.0,
                                          text="how many cars did I pass earlier?",
                                          temporal_reference_s=60.0, device_window_s=10.0))
    rows = {}
    for name, req in reqs.items():
        rows[name] = _timeit(lambda req=req: co.ghat_of(fleet, req), repeats)
    return dict(rows=rows,
                note=("one Ghat per request, including the task-type posterior rules and the "
                      "predicted delivered delay on the device's link; the unknown-type row pays "
                      "for the expectation over the posterior"))


def measure_decision_time(ro, fleet, make_fleet, horizons: Sequence[float] = (0.5, 0.75, 1.0),
                          pending_sizes: Sequence[int] = (1, 4, 16, 64),
                          repeats: int = 20) -> Dict[str, Any]:
    """One DeltaJ_H evaluation, swept over the horizon and the pending-set size.

    `make_fleet(n)` must return a fleet carrying n pending items, so the sweep measures the policy
    and not the construction of its input."""
    from .rollout import delta_j
    rows = []
    for H in horizons:
        ro.params.H = float(H)
        for n in pending_sizes:
            f = make_fleet(n)
            item = f.pending[0].item_id
            r = _timeit(lambda: delta_j(ro, f, dict(kind="release", item_id=item)), repeats)
            rows.append(dict(horizon_s=H, pending_items=n, **r,
                             per_release_loop_s=r["p50_s"] * n))
    return dict(
        rows=rows,
        note=("each row is ONE DeltaJ_H, which is two rollouts. Spec 7.2's release loop scores "
              "every pending item per event, so the per-event cost is about pending_items times "
              "the row's p50; `per_release_loop_s` reports that product."),
        host="flash CPU only; no GPU, no model server",
        caveat=("a lower bound on deployment cost: this is pure Python on committed tables, and "
                "the real decision also pays for telemetry reads and the engine's own admission "
                "path"))
