"""Spec 5.2 and 11, test T0: does the rollout's prediction match live measurement?

THIS HARNESS MUST NOT BE RUN ON HOLDOUT DATA. T0 is a model-fidelity check, so running it on the
held-out evaluation traces would burn them: every residual it reports is information about those
traces, and a model corrected against them is fitted on them. `T0Harness.run` therefore REFUSES a
dataset whose `split` is not one of the permitted development splits, and the refusal is not
overridable by a keyword argument.

What it compares, per spec 5.2:
  1. the DELAY the candidate action imposes on other requests, predicted against measured;
  2. the predicted COMPLETION TIME of each historical job, predicted against measured;
and it reports the residual distribution per condition with a stated tolerance, plus the
in-sample flag the engine model attached to each prediction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

PERMITTED_SPLITS = ("dev", "DEV", "train", "TRAIN", "synthetic", "SYNTHETIC",
                    "crossfit-train")
REFUSED_SPLITS = ("holdout", "HOLDOUT", "eval", "EVAL", "test", "TEST")


class HoldoutRefused(PermissionError):
    """Raised when T0 is pointed at data it must not see."""


@dataclass
class T0Case:
    case_id: str
    condition: str
    predicted_delay_s: float
    measured_delay_s: float
    predicted_completion_s: Optional[float] = None
    measured_completion_s: Optional[float] = None
    in_sample: bool = True


@dataclass
class T0Harness:
    tolerance_delay_s: float = 0.05
    tolerance_completion_s: float = 0.25
    cases: List[T0Case] = field(default_factory=list)

    def add(self, case: T0Case) -> None:
        self.cases.append(case)

    def run(self, dataset: Dict[str, Any]) -> Dict[str, Any]:
        split = str(dataset.get("split", "")).strip()
        if split in REFUSED_SPLITS or split.lower() in ("holdout", "eval", "test"):
            raise HoldoutRefused(
                "T0 is a cost-model fidelity check and must not be run on %r: fitting the engine "
                "model against held-out traces makes every later comparison in-sample. Spec 5.2 "
                "and CLAUDE.md both forbid it." % split)
        if split not in PERMITTED_SPLITS:
            raise HoldoutRefused(
                "refusing an unrecognized split %r; name it explicitly as one of %s so the "
                "provenance of a T0 result is never in doubt" % (split, list(PERMITTED_SPLITS)))
        cases = [T0Case(**c) if isinstance(c, dict) else c for c in dataset.get("cases", [])]
        cases = list(self.cases) + cases
        if not cases:
            return dict(split=split, n=0, verdict="NO CASES", note="T0 has not been run")
        by_cond: Dict[str, List[T0Case]] = {}
        for c in cases:
            by_cond.setdefault(c.condition, []).append(c)
        rows = []
        for cond, cs in sorted(by_cond.items()):
            dres = [c.predicted_delay_s - c.measured_delay_s for c in cs]
            cres = [c.predicted_completion_s - c.measured_completion_s for c in cs
                    if c.predicted_completion_s is not None
                    and c.measured_completion_s is not None]
            rows.append(dict(
                condition=cond, n=len(cs),
                delay_residual=_dist(dres), completion_residual=_dist(cres),
                within_delay_tolerance=all(abs(x) <= self.tolerance_delay_s for x in dres),
                within_completion_tolerance=all(abs(x) <= self.tolerance_completion_s
                                                for x in cres) if cres else None,
                n_out_of_sample=sum(1 for c in cs if not c.in_sample)))
        passed = all(r["within_delay_tolerance"] and
                     (r["within_completion_tolerance"] in (True, None)) for r in rows)
        return dict(
            split=split, n=len(cases), per_condition=rows,
            tolerance_delay_s=self.tolerance_delay_s,
            tolerance_completion_s=self.tolerance_completion_s,
            verdict=("PASS" if passed else "FAIL"),
            note=("a PASS on a SYNTHETIC dataset establishes only that the harness computes what "
                  "it claims; T0 is established by live measurement on the H100 (spec 11)"))


def _dist(xs: Sequence[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    def q(p: float) -> float:
        pos = (n - 1) * p
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return ys[lo] * (1 - (pos - lo)) + ys[hi] * (pos - lo)
    return dict(n=n, mean=sum(ys) / n, p50=q(0.5), p05=q(0.05), p95=q(0.95), min=ys[0],
                max=ys[-1], max_abs=max(abs(ys[0]), abs(ys[-1])))


def synthetic_dataset(ro, fleet, items, measured_overhead_s: float = 0.0) -> Dict[str, Any]:
    """A replay the harness can be exercised on without any live run: the rollout predicts the
    delay each release imposes, and the 'measurement' is the same engine model plus a stated
    constant overhead. It proves the plumbing, not the engine model, and says so."""
    from .rollout import delta_j
    cases = []
    for it in items:
        res = delta_j(ro, fleet, dict(kind="release", item_id=it.item_id))
        pred = res["engine_busy_delta_s"]
        cases.append(dict(case_id=it.item_id, condition=it.kind,
                          predicted_delay_s=pred,
                          measured_delay_s=pred + measured_overhead_s,
                          in_sample=res["in_sample"]))
    return dict(split="synthetic", cases=cases,
                note="SYNTHETIC: the 'measurement' is the model itself plus %.3f s, so this "
                     "exercises the harness and NOT the engine model" % measured_overhead_s)
