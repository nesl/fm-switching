#!/usr/bin/env python3
"""ONE dry cell per process for the D209 (4) / D210 0.25x RUNG-4 REPORT (Session D).

A WRAPPER, NOT A THIRD RUNNER, AND THE DIGEST RECIPE IS NOT RESTATED HERE. `cf_pd_one_cell.main`
is CALLED, so the posted knobs, the seed allowlist, the planner wall-clock patch, the
one-cell-per-process rule and above all the digest recipe are the committed ones. There is no
`sha256` and no `json.dumps` of a decision row in this file. `cfr3_one_cell` already wraps that
runner to register rung 4 and to dump the question-deferral leg's counters; this file reuses BOTH
of its helpers by import rather than copying them.

THE ONE THING IT ADDS IS THE DECISION LATENCY, AND IT ADDS IT WITHOUT MOVING THE DIGEST.
`test_hybrid.dry` drops `decision_latency_ms` from every row it returns (`test_hybrid.STRIP`), so
the quantity the 20 ms decision budget is judged against is not recoverable from a dry cell at
all. Rather than copy `dry`, this file patches `test_hybrid.dry` for the duration of the call:
the inner call runs with `decision_latency_ms` KEPT, the full rows are stashed for the latency
report, and the rows handed back to `cf_pd_one_cell` have `decision_latency_ms` removed again. So
the rows that reach the digest are the same dict set the committed runner would have produced, and
the claim is PROVED rather than asserted: the driver runs `covex-v6-state-uo` and `covex-v6-base`
through THIS file and requires their committed digests (9a4be873eb3c5fba / 14,218 rows and
af8befb9420ad86a). If a known-good committed arm fails under the patch, the patch is broken and
not the arm (CLAUDE.md check 7).

REGISTER. Every number this file produces is a DRY, LOGICAL-BUDGET number measured on flash's CPU:
`--kv-scale` scales `test_live2_coord.GPU_KV`, the LOGICAL coordinator pool, and nothing here
touches an engine, a `--num-gpu-blocks-override` or a real KV allocator. The decision latency is
flash CPU wall-clock inside the arm's `decide`, not an H100 number.

THE SECOND FLAG IS `--enforce-kv`, AND IT IS THERE BECAUSE THE DRY DEFAULT IS THE WRONG REGIME.
`CoordState.kv_capacity_enforced` defaults to False (`cstate.py:440`) and `test_hybrid.dry` never
sets it, so a plain dry cell at 0.25x records residency pressure and EVICTS NOTHING
(`cstate.py:520` is the only consumer that can evict). Every frozen-grid cell, including every
posted `_kv0.25` cell, runs with `--kv-capacity-enforced`. So the pool has TWO independent paths to
a decision and they must not be merged: the ARM'S OWN READ of the pool, which is visible with
enforcement off, and the COORDINATOR'S EVICTION, which is arm-independent and is the delta when
enforcement is on.

HOW `--enforce-kv` IS APPLIED, AND THE FAULT IT WAS ALMOST APPLIED THROUGH. The first version set
`cstate.CoordState.kv_capacity_enforced = True`. `CoordState` IS A DATACLASS, so its generated
`__init__` carries the default `False` in its own signature and a class-attribute set does NOT
reach the instance: measured, `CoordState(...).kv_capacity_enforced` stayed `False` after the set.
Two cells would have run UNENFORCED and been labelled enforced - the exact shape CLAUDE.md Step 2b
names, a switch that was passed and did not arrive. It is applied instead at the point the
COMMITTED live runner applies it, on the instance after the coordinator is built
(`run_live2_real.py:489`, `kv025_runnability_probe.py:129`), by wrapping
`Live2Coordinator.__init__`. And it is PROVED to have arrived rather than assumed: the coordinator
is stashed either way and the latency report records the flag READ BACK OFF THE INSTANCE together
with `st.pressure`, so a reader can see enforcement firing (`epochs_over_cap`) rather than take the
flag's word for it.

Flags: exactly `cf_pd_one_cell.py`'s, plus `--rd-out` (as `cfr3_one_cell.py`), `--lat-out` and
`--enforce-kv`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_pd_one_cell as C                                                     # noqa: E402
import cfr3_one_cell as X                                                      # noqa: E402

LAT_KEY = "decision_latency_ms"
_FULL: List[Dict[str, Any]] = []


def _patch_dry() -> None:
    """Keep `decision_latency_ms` inside, strip it on the way out."""
    import test_hybrid as TH                                              # noqa: PLC0415
    _orig = TH.dry

    def _dry(*a: Any, **kw: Any) -> Any:
        old = TH.STRIP
        TH.STRIP = tuple(x for x in old if x != LAT_KEY)
        try:
            rows, st = _orig(*a, **kw)
        finally:
            TH.STRIP = old
        _FULL.extend(rows)
        return [{k: v for k, v in r.items() if k != LAT_KEY} for r in rows], st
    TH.dry = _dry


def _q(v: List[float], p: float) -> float:
    """NEAREST-RANK, the rule `d190_measured_safety._nearest_rank` uses, so one quantile rule."""
    import d190_measured_safety as MS                                     # noqa: PLC0415
    return float(MS._nearest_rank(sorted(v), p))


def _lat_report() -> Dict[str, Any]:
    vals = [float(r[LAT_KEY]) for r in _FULL if r.get(LAT_KEY) is not None]
    miss = sum(1 for r in _FULL if r.get(LAT_KEY) is None)
    if not vals:
        return {"n": 0, "rows_seen": len(_FULL), "rows_without_the_field": miss,
                "VERDICT": "ABSENT: no decision row carried %s" % LAT_KEY}
    v = sorted(vals)
    n = len(v)
    by_kind: Dict[str, List[float]] = {}
    for r in _FULL:
        if r.get(LAT_KEY) is not None:
            by_kind.setdefault(str(r.get("kind")), []).append(float(r[LAT_KEY]))
    budget = 20.0
    return {
        "_register": ("DRY cell, flash CPU wall-clock inside the arm's decide, measured by "
                      "coordinator.py:2127. NOT an H100 number and not an engine number."),
        "budget_ms": budget,
        "n": n, "rows_seen": len(_FULL), "rows_without_the_field": miss,
        "min": v[0], "p25": _q(v, 0.25), "median": _q(v, 0.50), "p75": _q(v, 0.75),
        "iqr": round(_q(v, 0.75) - _q(v, 0.25), 6),
        "p90": _q(v, 0.90), "p99": _q(v, 0.99), "max": v[-1],
        "mean": round(sum(v) / n, 6),
        "n_distinct": len(set(v)),
        "constant_where_a_distribution_is_expected": bool(len(set(v)) <= 1),
        "n_over_budget": sum(1 for x in v if x > budget),
        "frac_over_budget": round(sum(1 for x in v if x > budget) / n, 6),
        "p99_within_budget": bool(_q(v, 0.99) <= budget),
        "max_within_budget": bool(v[-1] <= budget),
        "by_kind": {k: {"n": len(z), "min": min(z), "median": _q(z, 0.50),
                        "p99": _q(z, 0.99), "max": max(z), "n_distinct": len(set(z))}
                    for k, z in sorted(by_kind.items())},
    }


_COORDS: List[Any] = []


def _watch_coordinator(enforce: bool) -> None:
    """Stash every coordinator built, and set enforcement ON THE INSTANCE when asked."""
    import coordinator as CO                                              # noqa: PLC0415
    _orig = CO.Live2Coordinator.__init__

    def _init(self: Any, *a: Any, **kw: Any) -> None:
        _orig(self, *a, **kw)
        if enforce:
            self.st.kv_capacity_enforced = True
        _COORDS.append(self)
    CO.Live2Coordinator.__init__ = _init


def _enforcement_proof(enforce: bool) -> Dict[str, Any]:
    if not _COORDS:
        return {"VERDICT": "NO COORDINATOR SEEN: the switch cannot be proved to have arrived"}
    st = _COORDS[-1].st
    got = bool(getattr(st, "kv_capacity_enforced", False))
    return {
        "_what": "the switch READ BACK OFF THE OBJECT UNDER TEST, not merely passed",
        "n_coordinators_built": len(_COORDS),
        "asked_for": bool(enforce), "read_back": got,
        "type_read_back": type(getattr(st, "kv_capacity_enforced", None)).__name__,
        "ARRIVED": bool(got == enforce),
        "gpu_kv_tokens_on_the_state": int(getattr(st, "gpu_kv_tokens", 0) or 0),
        "pressure": {k: v for k, v in sorted(dict(getattr(st, "pressure", {}) or {}).items())
                     if not k.startswith("_")},
    }


if __name__ == "__main__":
    rd_out = lat_out = None
    enforce = "--enforce-kv" in sys.argv
    if enforce:
        sys.argv.remove("--enforce-kv")
    for flag in ("--rd-out", "--lat-out"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            val = sys.argv[i + 1]
            del sys.argv[i:i + 2]
            if flag == "--rd-out":
                rd_out = val
            else:
                lat_out = val
    X._register_capturing()
    _watch_coordinator(enforce)
    _patch_dry()
    rc = C.main()
    if rd_out:
        Path(rd_out).write_text(json.dumps(X._rd_dump(), default=float))
    if lat_out:
        rep = _lat_report()
        rep["kv_capacity_enforced"] = bool(enforce)
        rep["enforcement_proof"] = _enforcement_proof(enforce)
        Path(lat_out).write_text(json.dumps(rep, default=float))
        # THE ROWS, so a Step 2b count and a first difference can be computed between two cells
        # rather than only "the digests differ". Written AFTER the run from the rows already
        # stashed for the latency report, so it adds a file and touches nothing the run decided.
        # Strip `decision_latency_ms` from these before any comparison with a digest row set.
        Path(str(lat_out).replace(".lat.json", ".rows.json")).write_text(
            json.dumps(_FULL, default=float))
    raise SystemExit(rc)
