#!/usr/bin/env python3
"""ONE DRY CELL for F14, DECISION LATENCY vs FLEET SIZE. One cell per process (cf_pd_one_cell).

A WRAPPER, AND IT RESTATES NOTHING. `cf_pd_one_cell.main` is CALLED, so the posted workload knobs,
the seed allowlist, the planner wall-clock patch and above all THE COMMITTED DIGEST RECIPE are the
committed ones; there is no `sha256` and no `json.dumps` of a decision row in this file.
`d210_kv025_one_cell` already carries the two things F14 needs on top of that runner and both are
reused BY IMPORT rather than copied:

  the latency-keeping patch   `test_hybrid.dry` drops `decision_latency_ms` from every row it
                              returns (`test_hybrid.STRIP`), so the quantity the 20 ms budget is
                              judged against is not recoverable from a dry cell at all. The patch
                              keeps it INSIDE and strips it on the way OUT, so the rows that reach
                              the digest are the dict set the committed runner would have produced.
  the distribution report     `_lat_report` already emits min / p25 / median / p75 / IQR / p90 /
                              p99 / max, the budget comparison, `n_distinct` and
                              `constant_where_a_distribution_is_expected`, and a per-kind
                              breakdown. D214's "report the distribution, not just the quantiles"
                              is already this function's contract.

THE ONE THING THIS FILE ADDS is registration of the final rungs. `arms_final_ladder.register()` is
not called by any committed runner (its only other importer is `d208_ladder_name_proof`), so
`covex-v6-fair-final` and `covex-v6-final` do not resolve in `cf_pd_one_cell` without it. It goes
through `register()` itself, so D208's collision check against the committed names runs: those
names carry committed cell directories and `arms.ARMS` is a dict, so a second registration under
one of them would re-point every reader of those cells.

WHY A DRY CELL IS THE RIGHT INSTRUMENT HERE AND WHAT THAT COSTS. The decision latency is flash CPU
wall-clock inside the arm's `decide`, measured by `coordinator.py:2127`. It is a FLASH number. It
is NOT an H100 number and it is not an engine number, and D115 (1) measured the H100 host CPU at
about 2.2x slower than flash on the committed policy benchmark. D115 (3) permits a NORMALISED
latency to be REPORTED as a labelled derived quantity and forbids rescaling run OUTCOMES, so this
file emits the measured flash figure only and never a rescaled one. The factor belongs beside the
table, in the driver's report, not inside the number.

`--cutoff-off` IS PASSED BY THE DRIVER AND IT IS NOT A CONVENIENCE. With the planner wall-clock
cutoff ON, a decision that runs long is TRUNCATED, so the decisions themselves depend on how fast
the host was that minute and two runs of the same cell are not the same cell. The committed proof
recipe patches it off for exactly that reason, and a latency sweep that left it on would be
measuring a quantity that its own measurement had altered.

Flags: exactly `cf_pd_one_cell.py`'s, plus `--lat-out` and `--enforce-kv` (both as
`d210_kv025_one_cell.py`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_final_ladder as FL                                                 # noqa: E402
import cf_pd_one_cell as C                                                     # noqa: E402
import d210_kv025_one_cell as K                                                # noqa: E402

RUNG3 = FL.RUNG3
RUNG4 = FL.RUNG4


def register_final() -> Dict[str, Any]:
    """Register the three final rungs additively, and PROVE the names resolve afterwards."""
    import arms as A                                                       # noqa: PLC0415
    names = FL.register()                      # D208's collision check runs inside
    return {"registered": list(names),
            "resolves": {n: bool(n in A.ARMS) for n in (RUNG3, RUNG4)},
            "ladder_version": FL.LADDER_VERSION,
            "built_from": dict(FL.BUILT_FROM)}


if __name__ == "__main__":
    lat_out = None
    enforce = "--enforce-kv" in sys.argv
    if enforce:
        sys.argv.remove("--enforce-kv")
    if "--lat-out" in sys.argv:
        i = sys.argv.index("--lat-out")
        lat_out = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    reg = register_final()
    K._watch_coordinator(enforce)
    K._patch_dry()
    rc = C.main()
    if lat_out:
        rep = K._lat_report()
        rep["kv_capacity_enforced"] = bool(enforce)
        rep["enforcement_proof"] = K._enforcement_proof(enforce)
        rep["final_ladder_registration"] = reg
        rep["_d115"] = ("MEASURED ON FLASH. D115 (1): the H100 host CPU is about 2.2x slower on "
                        "the committed policy benchmark. D115 (3): a normalised latency may be "
                        "REPORTED as a labelled derived quantity; run OUTCOMES are never "
                        "rescaled. Nothing in this file is rescaled.")
        Path(lat_out).write_text(json.dumps(rep, default=float))
    raise SystemExit(rc)
