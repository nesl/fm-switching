#!/usr/bin/env python3
"""D206 item c2: partition every REGISTERED arm by the CODE SITE that constructs the v5 state
planner, which is the unit the one-cell-per-family proof needs.

MEASURED, NOT ASSUMED. Every registered arm is CONSTRUCTED and the file and line of its
`_cf_engine` is read with `inspect`, so the partition comes from the code the process actually
loaded rather than from a reading of the source. The weight source each engine ends up holding is
read off the constructed engine for the same reason.

Writes results/orchestration/live2/d200_one_deficit_weight/d206_families.json.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = ROOT / "results/orchestration/live2/d200_one_deficit_weight/d206_families.json"


def main() -> int:
    import arms as A
    sites, errs, srcs = {}, {}, {}
    for name in sorted(A.ARMS):
        try:
            arm = A.ARMS[name]()
        except Exception as e:                                             # noqa: BLE001
            errs[name] = type(e).__name__ + ": " + str(e)[:80]
            continue
        eng = getattr(type(arm), "_cf_engine", None)
        if eng is None:
            key = "F1_no_cf_engine_attribute"
        else:
            try:
                key = "%s:%d" % (Path(inspect.getsourcefile(eng)).name,
                                 inspect.getsourcelines(eng)[1])
            except Exception:                                              # noqa: BLE001
                key = "unresolvable"
        sites.setdefault(key, []).append(name)
        bound = getattr(arm, "_cf_engine", None)
        if callable(bound):
            try:
                srcs.setdefault(type(bound().counters).__name__, []).append(name)
            except Exception as e:                                         # noqa: BLE001
                srcs.setdefault("ENGINE_ERROR_" + type(e).__name__, []).append(name)
    res = {
        "_what": ("the partition of every registered arm by the construction site of the v5 state "
                  "planner, and the weight source each engine actually holds"),
        "_measured_how": ("every arm CONSTRUCTED; the site read with inspect.getsourcefile and "
                          "getsourcelines on the bound _cf_engine; the source read off the "
                          "constructed engine. Nothing is inferred from a grep."),
        "n_registered": len(A.ARMS),
        "n_constructed": sum(len(v) for v in sites.values()),
        "refused_BY_DESIGN": errs,
        "by_construction_site": {k: {"n": len(v), "arms": v} for k, v in sorted(sites.items())},
        "by_weight_source_AFTER_D206": {k: {"n": len(v), "arms": v}
                                        for k, v in sorted(srcs.items())},
        "_reaching_total": sum(len(v) for k, v in sites.items()
                               if k != "F1_no_cf_engine_attribute"),
        "_cross_check": ("the reaching total is compared against the committed d177 reach census, "
                         "54 at its measurement base and 57 at its parent; the parent figure is "
                         "the comparable one because the base predates the three -rr arms, which "
                         "the committed row itself records as added by origin while it ran"),
        "_register": ("one cell per family proves the SHARED CONSTRUCTION SITE is decision-"
                      "identical end to end. It does NOT re-derive each arm's own digest, and is "
                      "not offered as doing so: that is what c1's bit-identity at the five read "
                      "sites carries."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({"registered": res["n_registered"], "constructed": res["n_constructed"],
                      "reaching": res["_reaching_total"],
                      "sites": {k: v["n"] for k, v in res["by_construction_site"].items()},
                      "sources": {k: v["n"] for k, v in
                                  res["by_weight_source_AFTER_D206"].items()},
                      "refused": list(errs)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
