#!/usr/bin/env python3
"""PER-DECISION WALL-CLOCK INSTRUMENT, emitting the FULL DISTRIBUTION (D151 (5), spec v5 section
10). CPU only.

D151 (5) budgets the counterfactual at **p99 < 20 ms at 32 devices, MEASURED**, and spec v5
section 10 adds that the run report must carry the p99 AND THE DISTRIBUTION, because under
CLAUDE.md check 3 a p99 reported alone hides the shape that would show a short-circuit. A planner
that returned instantly on half its decisions because a switch was dead would have an excellent
p99. `reports/policy_v5_assessment.md` section E records that NO SUCH INSTRUMENT EXISTS, so the
budget could not be checked even in principle; this module is it.

WHAT IT EMITS, and why each part is there:

  * `samples_ms`   EVERY per-decision measurement, in order, not a summary. The distribution is
                   the artefact; the quantiles are a convenience.
  * quantiles      p0, p1, p5, p10, p25, p50, p75, p90, p95, p99, p99.9, p100.
  * histogram      declared fixed bin edges, so two runs' shapes can be compared directly.
  * `n_zero_like`  decisions faster than 1 microsecond. A short-circuit shows here first.
  * `by_kind`      the same distribution per decision kind, because the three kinds have different
                   candidate counts and mixing them hides which one is expensive.
  * `n_over_budget`, `p99_ms`, `within_budget`  the budget test itself, with the fleet size it
                   was measured at recorded beside it, since the budget is AT 32 DEVICES.

WHAT IT DOES NOT MEASURE. It measures the planner's own wall clock on the machine it runs on. It
is not a measurement of the live harness, it does not include the coordinator's state rebuild, and
it carries no GPU time. Every proof that uses it says so at the point of use.
"""
from __future__ import annotations

import json
import math
import platform
import statistics as st
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence

BUDGET_MS = 20.0                 # D151 (5)
BUDGET_AT_DEVICES = 32           # D151 (5): the budget is AT 32 devices
QUANTILES = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 0.999, 1.0)
HIST_EDGES_MS = (0.0, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0)
ZERO_LIKE_MS = 0.001             # 1 microsecond: faster than this is a short-circuit, not a plan


@dataclass
class Timing:
    kind: str
    meta: Dict[str, Any]
    elapsed_ms: float = 0.0
    _t0: int = 0

    def over_budget(self, budget_ms: float = BUDGET_MS) -> bool:
        """The live check the planner makes at candidate boundaries, so a slow plan can abandon to
        base (spec v5 section 10) rather than blow the budget and be reported after the fact."""
        return ((time.perf_counter_ns() - self._t0) / 1e6) > float(budget_ms)

    def elapsed_now_ms(self) -> float:
        return (time.perf_counter_ns() - self._t0) / 1e6


class DecisionClock:
    """Collects one wall-clock sample per decision, with its metadata, and emits the full shape."""

    def __init__(self, n_devices: Optional[int] = None, budget_ms: float = BUDGET_MS) -> None:
        self.n_devices = n_devices
        self.budget_ms = float(budget_ms)
        self.records: List[Dict[str, Any]] = []

    @contextmanager
    def time_decision(self, kind: str, **meta: Any) -> Iterator[Timing]:
        t = Timing(kind, dict(meta))
        t._t0 = time.perf_counter_ns()
        try:
            yield t
        finally:
            t.elapsed_ms = (time.perf_counter_ns() - t._t0) / 1e6
            rec = {"kind": kind, "elapsed_ms": t.elapsed_ms}
            rec.update(t.meta)
            self.records.append(rec)

    def note(self, key: str, value: Any) -> None:
        if self.records:
            self.records[-1][key] = value

    # ---- the distribution

    @staticmethod
    def _quantile(sorted_vals: Sequence[float], q: float) -> float:
        if not sorted_vals:
            return float("nan")
        if len(sorted_vals) == 1:
            return float(sorted_vals[0])
        pos = float(q) * (len(sorted_vals) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(sorted_vals) - 1)
        frac = pos - lo
        return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac)

    def _shape(self, vals: Sequence[float]) -> Dict[str, Any]:
        s = sorted(float(v) for v in vals)
        if not s:
            return {"n": 0}
        hist = []
        for i in range(len(HIST_EDGES_MS) - 1):
            lo, hi = HIST_EDGES_MS[i], HIST_EDGES_MS[i + 1]
            hist.append({"lo_ms": lo, "hi_ms": hi,
                         "n": sum(1 for v in s if lo <= v < hi)})
        hist.append({"lo_ms": HIST_EDGES_MS[-1], "hi_ms": None,
                     "n": sum(1 for v in s if v >= HIST_EDGES_MS[-1])})
        return {
            "n": len(s),
            "min_ms": round(s[0], 6), "max_ms": round(s[-1], 6),
            "mean_ms": round(st.fmean(s), 6),
            "stdev_ms": round(st.pstdev(s), 6) if len(s) > 1 else 0.0,
            "quantiles_ms": {("p%g" % (q * 100)): round(self._quantile(s, q), 6)
                             for q in QUANTILES},
            "histogram_ms": hist,
            "n_zero_like": sum(1 for v in s if v < ZERO_LIKE_MS),
            "zero_like_threshold_ms": ZERO_LIKE_MS,
        }

    def distribution(self, *, label: str = "", emit_samples: bool = True) -> Dict[str, Any]:
        vals = [r["elapsed_ms"] for r in self.records]
        out: Dict[str, Any] = {
            "_what": ("per-decision planner wall clock, FULL DISTRIBUTION (D151 (5), spec v5 "
                      "section 10): the p99 alone would hide a short-circuit"),
            "_register": ("the planner's own wall clock on this CPU. NOT the live harness, NOT "
                          "including the coordinator's state rebuild, NO GPU time"),
            "label": label,
            "n_devices": self.n_devices,
            "budget_ms": self.budget_ms,
            "budget_at_devices": BUDGET_AT_DEVICES,
            "overall": self._shape(vals),
            "by_kind": {},
            "machine": {"python": platform.python_version(), "machine": platform.machine(),
                        "processor": platform.processor(), "system": platform.system()},
        }
        kinds = sorted({str(r.get("kind")) for r in self.records})
        for k in kinds:
            out["by_kind"][k] = self._shape([r["elapsed_ms"] for r in self.records
                                             if r.get("kind") == k])
        p99 = out["overall"].get("quantiles_ms", {}).get("p99")
        out["p99_ms"] = p99
        out["n_over_budget"] = sum(1 for v in vals if v > self.budget_ms)
        out["frac_over_budget"] = (round(out["n_over_budget"] / len(vals), 6) if vals else None)
        out["within_budget"] = (bool(p99 is not None and p99 < self.budget_ms))
        out["budget_claim_valid_at_this_fleet_size"] = (self.n_devices == BUDGET_AT_DEVICES)
        if emit_samples:
            out["samples_ms"] = [round(v, 6) for v in vals]
            out["records"] = self.records
        return out


def main() -> int:
    c = DecisionClock(n_devices=32)
    for i in range(50):
        with c.time_decision("request", decision_id="d%03d" % i, n_candidates=4):
            sum(j * j for j in range(1000 + 50 * i))
    d = c.distribution(label="self test", emit_samples=False)
    print(json.dumps({k: d[k] for k in ("p99_ms", "within_budget", "n_over_budget", "overall")},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
