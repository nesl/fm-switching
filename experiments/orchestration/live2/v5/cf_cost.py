#!/usr/bin/env python3
"""PREDICTED SERVICE, DELIVERY PROBABILITY, THE LATEST SAFE START, AND TWO-LEVEL FIDELITY.

The cost side of the v5 counterfactual (spec v5 sections 5.2, 5.4; D151 (3), (4)). CPU only. No
GPU, no engine, no coordinator. Every number this module uses comes from a committed file.

WHAT IT PREDICTS, AND WHY DECODE IS NOT OPTIONAL.
The committed feasibility formula (`hybrid/feasible_on_time.py`, D133) is prefill only. Spec v5
section 5.2 is explicit that the predicted service which sets a latest safe start MUST INCLUDE
DECODE: at a 3 s deadline decode is up to 47 percent of the budget and was 1.086 s at the median
on the actual misses (frozen_test 19.5), and adding it moves the cold feasibility threshold by
about 1,700 tokens, which is the difference between 48 and 42 of 70 feasible. A planner that
forgets decode defers too late, every time, and the error is one-sided. So `predict()` returns
first token AND decode, `total_s` is their sum, and `latest_safe_start()` takes `total_s`. The
prefill-only number is still computed, as `total_prefill_only_s`, for one purpose: so the proofs
can show what omitting decode would have done. Nothing in the planner reads it.

WHERE THE MODEL COMES FROM. The committed `cost_model_gate.json`, the HELD-OUT-BY-ARM split:

    first_token = i0 + c1 * uncached_tokens + c2 * overlap_ft
    decode      = j0 + d1 * overlap_decode

By-arm and not by-seed, because v5 is a policy no fitted arm has produced and spec v5 section 12
names the by-arm split as the generalisation that matters. THE GATE FAILS: decode over-predicts
by 25 to 32 percent in every held-out class and warm is confounded with arm (G10). Every number
this module returns is therefore conditional on a failing gate and is labelled so. That is also
why the safety factor is derived from the gate's own held-out residuals rather than chosen.

WHERE P(ON TIME) COMES FROM. The objective needs a PROBABILITY, and a point prediction is 0 or 1.
`p_on_time()` reads the empirical distribution of (actual service / predicted service) over the
committed held-out requests and evaluates its CDF at `slack / predicted`. So the delivery
probability is a measured residual distribution, not a logistic shape anyone chose, and it moves
continuously with slack. Its limitations are its data's: the residuals are overwhelmingly COLD
(1,797 warm of 345,066) and every cell is `dashcam-1f` (D153, G17), so P(on time) is PROVISIONAL
in exactly the two regimes v5 cares about most. Stated here and carried into every report.

TWO-LEVEL FIDELITY (spec v5 section 5.4, D151 (4)). `plan_queue()` simulates the engine's actual
queue EXACTLY over the near-term window and carries a COARSE offered-load forecast beyond it. The
split point is declared per decision kind in `NEAR_EXACT_S` and is not fitted. Exactness
near-term is what lets the planner tell a 0.024 s decode from a 1.403 s one, which is 19.5's
58-fold range and decides a 3 s deadline on its own; the coarse level beyond is what keeps the
whole plan inside D151 (5)'s 20 ms.
"""
from __future__ import annotations

import bisect
import json
import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(REPO / "experiments/orchestration/live2"),
           str(REPO / "experiments/orchestration/live2/fleet"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.append(_p)

GATE_JSON = REPO / "results/orchestration/live2/frozen_test/cost_model_gate.json"
RESIDUALS_JSON = REPO / "results/orchestration/live2/v5/cf_service_residuals.json"

GATE_SPLIT = "by_arm"
GATE_STATUS = ("FAILS (spec v5 section 12): decode over-predicts by 25 to 32 percent in every "
               "held-out class, and warm is confounded with arm, so the warm regime is "
               "unidentified out of arm (G10). D154 (2) cannot set MARGIN_CF until it passes.")

# The link term, from the committed trace generator, so the planner and the harness agree.
try:
    import traces as _TRACES                                                   # noqa: E402
    LINK_RTT_S = float(_TRACES.RTT_MS) / 1000.0
    LINK_SOURCE = "live2/traces.py::RTT_MS"
except Exception:                                                              # noqa: BLE001
    LINK_RTT_S = 0.044
    LINK_SOURCE = "StudyE9 setting (ii) 0.044 s RTT (fallback: live2/traces.py not importable)"

# Two-level fidelity split points, DECLARED PER DECISION KIND (spec v5 section 5.4). These are
# declared constants, not fitted parameters, and no proof or cell varies them.
NEAR_EXACT_S: Dict[str, Optional[float]] = {
    # a request's exact window is its own horizon: its deadline and the deadlines it displaces,
    # which `plan_queue` is given directly. None means "the horizon the caller computed".
    "request": None,
    # a warm or keep decision looks out to the next likely question (capped, D151 (4)), but only
    # the first 3 s of that is simulated request by request; beyond it the queue is a forecast.
    "state": 3.0,
    # a backlog runs until caught up, which is far beyond any exact window.
    "sync": 3.0,
}

HORIZON_WARM_CAP_S = 120.0      # D151 (4): "capped about 60 to 120 s", declared, not fitted
HORIZON_WARM_CAP_RANGE = (60.0, 120.0)

FIXED_POINT_ITERATIONS = 3      # declared: the queue's overlap fixed point, bounded for the budget


# ---------------------------------------------------------------------------
# The committed cost model


def load_gate_model(path: Path = GATE_JSON, split: str = GATE_SPLIT) -> Dict[str, Any]:
    """The committed gate model. RAISES if absent: a silent fallback would let the planner price
    service from coefficients nobody fitted, which is the whole failure mode D151 (6) gates."""
    if not path.exists():
        raise FileNotFoundError("committed cost-model gate missing: %s" % path)
    d = json.loads(path.read_text())
    for sp in d["splits"]:
        if sp["name"] == split:
            m = dict(sp["model"])
            m["_split"] = split
            m["_fit_on"] = sp["fit_on"]
            m["_test_on"] = sp["test_on"]
            m["_n_fit"] = sp["n_fit"]
            m["_source"] = str(path.relative_to(REPO))
            m["_held_out_ratios"] = {
                k: {"first_token": v["first_token"]["ratio_p50"],
                    "decode": v["decode"]["ratio_p50"], "n": v["n"]}
                for k, v in sp["held_out"]["by_cache_state"].items()}
            m["_gate_status"] = GATE_STATUS
            return m
    raise KeyError("no split %r in %s" % (split, path))


@dataclass(frozen=True)
class ServicePrediction:
    first_token_s: float
    decode_s: float
    engine_s: float                 # first token + decode: what the request logs measure
    total_s: float                  # engine service + link, the quantity the planner budgets
    total_prefill_only_s: float     # what the committed D133 formula would have said
    decode_share: float
    uncached_tokens: int
    overlap_ft: int
    overlap_decode: int

    def as_dict(self) -> Dict[str, Any]:
        return {"first_token_s": round(self.first_token_s, 6),
                "decode_s": round(self.decode_s, 6),
                "engine_s": round(self.engine_s, 6),
                "total_s": round(self.total_s, 6),
                "total_prefill_only_s": round(self.total_prefill_only_s, 6),
                "decode_share": round(self.decode_share, 6),
                "uncached_tokens": self.uncached_tokens,
                "overlap_ft": self.overlap_ft, "overlap_decode": self.overlap_decode}


def predict(model: Dict[str, Any], tokens: int, cached_tokens: int = 0,
            overlap_ft: int = 0, overlap_decode: int = 0,
            link_s: float = LINK_RTT_S) -> ServicePrediction:
    """Predicted service for one cloud request, DECODE INCLUDED (spec v5 section 5.2)."""
    f, d = model["first_token"], model["decode"]
    unc = max(int(tokens) - int(cached_tokens), 0)
    ft = (float(f["intercept"]) + float(f["per_uncached_token"]) * unc
          + float(f["per_overlap"]) * max(int(overlap_ft), 0))
    dec = float(d["intercept"]) + float(d["per_overlap"]) * max(int(overlap_decode), 0)
    ft = max(ft, 0.0)
    dec = max(dec, 0.0)
    total = ft + dec + float(link_s)
    return ServicePrediction(ft, dec, ft + dec, total, ft + float(link_s),
                             dec / total if total > 0 else 0.0, unc,
                             max(int(overlap_ft), 0), max(int(overlap_decode), 0))


# ---------------------------------------------------------------------------
# The delivery-probability model: the gate's own held-out residuals


def load_residuals(path: Path = RESIDUALS_JSON) -> Dict[str, Any]:
    """The committed residual summary written by `cf_proofs.py --build-residuals`.

    RAISES if absent for the same reason `load_gate_model` does: a planner that invents a delivery
    probability is a planner whose every value is invented.
    """
    if not path.exists():
        raise FileNotFoundError(
            "residual summary missing: %s. Build it with "
            "`python3 -I experiments/orchestration/live2/v5/cf_proofs.py --build-residuals`, "
            "which reads committed request logs only." % path)
    return json.loads(path.read_text())


def ratio_quantile(residuals: Dict[str, Any], q: float) -> float:
    """Quantile of (actual service / predicted service) on the held-out split."""
    grid = residuals["ratio_quantiles"]["q"]
    vals = residuals["ratio_quantiles"]["value"]
    i = bisect.bisect_left(grid, float(q))
    i = min(max(i, 0), len(vals) - 1)
    return float(vals[i])


def p_on_time(residuals: Dict[str, Any], predicted_s: float, slack_s: float) -> float:
    """P(the answer is delivered within `slack_s`) = F_ratio(slack / predicted).

    `slack_s` is the time from the planned START to the deadline, so a deferral shortens it and a
    displacement that pushes a start later shortens it too. The CDF is the EMPIRICAL distribution
    of actual-over-predicted service on committed held-out requests.
    """
    if predicted_s <= 0:
        return 1.0 if slack_s >= 0 else 0.0
    if slack_s <= 0:
        return 0.0
    r = float(slack_s) / float(predicted_s)
    vals = residuals["ratio_quantiles"]["value"]
    grid = residuals["ratio_quantiles"]["q"]
    if r <= vals[0]:
        return 0.0
    if r >= vals[-1]:
        return 1.0
    i = bisect.bisect_right(vals, r) - 1
    i = min(max(i, 0), len(vals) - 2)
    v0, v1 = vals[i], vals[i + 1]
    q0, q1 = grid[i], grid[i + 1]
    if v1 <= v0:
        return float(q1)
    return float(q0 + (q1 - q0) * (r - v0) / (v1 - v0))


def service_error_to_objective_units(residuals: Dict[str, Any]) -> Dict[str, Any]:
    """D154 (2) wants the gate's held-out p90 ABSOLUTE error IN THE OBJECTIVE'S UNITS. REFUSES.

    The gate's error is in SECONDS of service; the objective is in expected correct answers
    delivered by the deadline. Pushing seconds through `p_on_time` and the committed accuracy
    table gives an answer that depends on which question you push it through: the same 0.4 s error
    is worth almost nothing on a question with 2 s of slack and almost the whole accuracy gap on
    one at the edge. So the conversion is a CHOICE OF POPULATION, which is exactly the kind of
    choice D151 (1) forbids making after seeing the data. Reported, not resolved.
    """
    return {
        "p90_abs_service_error_s": residuals.get("p90_abs_error_s"),
        "units_of_the_gate": "seconds of service time",
        "units_of_the_objective": "expected correct answers delivered by the deadline",
        "conversion_exists": False,
        "refused": True,
        "why": service_error_to_objective_units.__doc__.strip().splitlines()[2].strip()
        if service_error_to_objective_units.__doc__ else "",
        "what_would_settle_it": (
            "a user ruling that names the population the margin is expressed over (for example "
            "the p90 error evaluated at the median robot question's slack on the EP-G workload), "
            "recorded in the design log BEFORE the gate's ratios are looked at again"),
    }


# ---------------------------------------------------------------------------
# The latest safe start (spec v5 section 5.2, D151 (3))


@dataclass(frozen=True)
class LatestSafeStart:
    latest_start_s: float
    predicted_service_s: float
    safety_factor: float
    feasible: bool                  # can it still be started at or after `now` and land in time
    must_start_now: bool
    deferral_s: float               # how long the planner may wait, 0 if it must start now
    decode_included: bool
    latest_start_if_decode_omitted_s: float
    decode_omission_error_s: float

    def as_dict(self) -> Dict[str, Any]:
        d = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        return d


def latest_safe_start(now_s: float, deadline_abs_s: float, pred: ServicePrediction,
                      safety: float) -> LatestSafeStart:
    """`deadline minus predicted service times a measured safety factor` (D151 (3)).

    The safety factor comes from `cf_margin.safety_factor`, which derives it from the gate's own
    held-out residual quantile. It is not a knob and no proof or cell varies it.
    """
    need = float(safety) * pred.total_s
    lss = float(deadline_abs_s) - need
    need_po = float(safety) * pred.total_prefill_only_s
    lss_po = float(deadline_abs_s) - need_po
    return LatestSafeStart(
        latest_start_s=lss, predicted_service_s=pred.total_s, safety_factor=float(safety),
        feasible=bool(lss >= now_s - 1e-9),
        must_start_now=bool(lss <= now_s + 1e-9),
        deferral_s=max(lss - float(now_s), 0.0),
        decode_included=True,
        latest_start_if_decode_omitted_s=lss_po,
        decode_omission_error_s=lss_po - lss)


def replan_on_slip(lss: LatestSafeStart, now_s: float, pred: ServicePrediction,
                   safety: float, deadline_abs_s: float) -> Dict[str, Any]:
    """D151 (3)'s "re-plan on slip": recompute the latest safe start from the state as it now is.

    A slip is any reason the old plan no longer holds: the queue grew, the history grew, the start
    was missed. The re-plan is the same function on new inputs, and `slipped` records whether the
    deferral the planner was holding has been overtaken by the clock.
    """
    fresh = latest_safe_start(now_s, deadline_abs_s, pred, safety)
    return {"slipped": bool(now_s > lss.latest_start_s + 1e-9),
            "old_latest_start_s": round(lss.latest_start_s, 6),
            "new_latest_start_s": round(fresh.latest_start_s, 6),
            "now_s": round(float(now_s), 6),
            "still_feasible": fresh.feasible,
            "must_start_now": fresh.must_start_now,
            "replan": fresh.as_dict()}


# ---------------------------------------------------------------------------
# The queue: exact near-term, coarse beyond (two-level fidelity, spec v5 section 5.4)


@dataclass
class PendingRequest:
    """One cloud request the engine is serving or about to serve."""
    req_id: str
    device_id: str
    start_s: float                  # when it enters the engine (submitted, or planned start)
    tokens: int
    cached_tokens: int = 0
    deadline_abs_s: float = math.inf
    accuracy: float = 0.0           # accuracy of the representation it carries (committed table)
    weight: float = 1.0             # its device's deficit weight, read by cf_objective
    kind: str = "robot"
    # D171 (3): the identity the MEASURED device-latency tables are keyed on, so the harm term can
    # price each displaced request's own device fallback instead of a flat proxy.
    question_id: Optional[str] = None
    episode_frames: Optional[int] = None
    is_candidate: bool = False      # the request the current decision is about
    # filled by `plan_queue`
    pred: Optional[ServicePrediction] = None
    first_token_abs_s: float = 0.0
    done_abs_s: float = 0.0
    p_on_time: float = 0.0
    fidelity: str = "exact"


@dataclass(frozen=True)
class QueuePlan:
    requests: Tuple[PendingRequest, ...]
    exact_until_s: float
    n_exact: int
    n_coarse: int
    coarse_overlap_forecast: float
    iterations: int
    decision_kind: str

    def by_id(self) -> Dict[str, PendingRequest]:
        return {r.req_id: r for r in self.requests}

    def as_dict(self) -> Dict[str, Any]:
        return {"exact_until_s": round(self.exact_until_s, 6), "n_exact": self.n_exact,
                "n_coarse": self.n_coarse, "decision_kind": self.decision_kind,
                "coarse_overlap_forecast": round(self.coarse_overlap_forecast, 4),
                "iterations": self.iterations,
                "requests": [{"req_id": r.req_id, "device_id": r.device_id,
                              "fidelity": r.fidelity, "start_s": round(r.start_s, 6),
                              "tokens": r.tokens, "cached_tokens": r.cached_tokens,
                              "deadline_abs_s": (None if r.deadline_abs_s == math.inf
                                                 else round(r.deadline_abs_s, 6)),
                              "first_token_abs_s": round(r.first_token_abs_s, 6),
                              "done_abs_s": round(r.done_abs_s, 6),
                              "p_on_time": round(r.p_on_time, 6),
                              "is_candidate": r.is_candidate,
                              "pred": (r.pred.as_dict() if r.pred else None)}
                             for r in self.requests]}


def _count_overlaps(spans: Sequence[Tuple[float, float]], i: int) -> int:
    s0, e0 = spans[i]
    n = 0
    for j, (s1, e1) in enumerate(spans):
        if j == i:
            continue
        if s1 < e0 and s0 < e1:
            n += 1
    return n


def plan_queue(model: Dict[str, Any], residuals: Dict[str, Any],
               requests: Sequence[PendingRequest], *, now_s: float,
               exact_until_s: float, decision_kind: str,
               coarse_overlap_forecast: float,
               iterations: int = FIXED_POINT_ITERATIONS) -> QueuePlan:
    """Predict every request's completion, EXACTLY inside the near-term window and from a COARSE
    offered-load forecast beyond it.

    EXACT means the overlap counts each request actually experiences are COUNTED from the other
    requests' own predicted spans, which is a fixed point (a request's duration depends on who
    overlaps it and who overlaps it depends on durations). It is solved by `iterations` sweeps from
    zero overlap, which is deterministic and bounded; `iterations` is a declared constant.

    COARSE means the request is priced at `coarse_overlap_forecast` overlaps, the forecast of
    offered load, with no per-request simulation. That is the second level of D151 (4)'s two-level
    fidelity and it is what keeps the plan inside the 20 ms budget.
    """
    rs = [replace(r) for r in requests]
    for r in rs:
        r.fidelity = "exact" if r.start_s <= exact_until_s else "coarse"
    # initial pass at zero overlap for the exact set, forecast overlap for the coarse set
    for r in rs:
        ov = 0 if r.fidelity == "exact" else int(round(coarse_overlap_forecast))
        r.pred = predict(model, r.tokens, r.cached_tokens, ov, ov)
    for _ in range(max(int(iterations), 1)):
        ft_spans = [(r.start_s, r.start_s + (r.pred.first_token_s if r.pred else 0.0)) for r in rs]
        dec_spans = [(r.start_s + (r.pred.first_token_s if r.pred else 0.0),
                      r.start_s + (r.pred.total_s if r.pred else 0.0)) for r in rs]
        for i, r in enumerate(rs):
            if r.fidelity != "exact":
                continue
            r.pred = predict(model, r.tokens, r.cached_tokens,
                             _count_overlaps(ft_spans, i), _count_overlaps(dec_spans, i))
    for r in rs:
        r.first_token_abs_s = r.start_s + r.pred.first_token_s
        r.done_abs_s = r.start_s + r.pred.total_s
        # the residual distribution is fitted on ENGINE service (the request logs' first token plus
        # decode), so the probability is evaluated on engine service against the slack that
        # remains after the link is paid. Mixing the two scales would be a 44 ms error in the
        # planner's favour, which is the wrong direction.
        slack = r.deadline_abs_s - r.start_s - LINK_RTT_S
        r.p_on_time = (1.0 if r.deadline_abs_s == math.inf
                       else p_on_time(residuals, r.pred.engine_s, slack))
    return QueuePlan(tuple(rs), float(exact_until_s),
                     sum(1 for r in rs if r.fidelity == "exact"),
                     sum(1 for r in rs if r.fidelity == "coarse"),
                     float(coarse_overlap_forecast), int(iterations), decision_kind)


def coarse_forecast_overlap(arrival_rate_per_s: float, mean_service_s: float) -> float:
    """The coarse level: expected number of concurrent requests from offered load alone.

    Little's law on the offered stream, which is the cheapest forecast that still responds to
    fleet size, and is declared as a forecast rather than a simulation.
    """
    return max(float(arrival_rate_per_s) * float(mean_service_s), 0.0)


def main() -> int:
    m = load_gate_model()
    print(json.dumps({"split": m["_split"], "fit_on": m["_fit_on"], "test_on": m["_test_on"],
                      "first_token": m["first_token"], "decode": m["decode"],
                      "held_out_ratios": m["_held_out_ratios"],
                      "link_rtt_s": LINK_RTT_S, "link_source": LINK_SOURCE,
                      "gate_status": m["_gate_status"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
