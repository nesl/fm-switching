#!/usr/bin/env python3
"""ONE dry cell per process for the FINAL LADDER arms, plus each rung's own mechanism counters.

A WRAPPER, NOT A SECOND RUNNER, AND THE DIGEST IS NOT RECOMPUTED HERE. Everything that makes a
digest comparable (the posted knobs, the seed allowlist, the planner wall-clock patch, the
one-cell-per-process rule and above all the DIGEST RECIPE) lives in `cf_pd_one_cell.py` and is
reused by CALLING ITS `main()`. This file contains no `sha256` and no `json.dumps` of any row, for
the reason `cfr3_one_cell.py` records: a second copy of that recipe is how two digests of the same
rows stop matching.

WHY IT EXISTS AT ALL. `arms.py` does NOT import `arms_final_ladder`, so the three final names do
not resolve through a plain `import arms`. That is the same registration gap that made all eleven
`covex-v6-cf-pd` cells invisible to `run_live2_real.py`, and it is reported rather than patched
here, because `arms.py` is another session's file. This wrapper registers the ladder itself so a
DRY PROOF can run; A POSTED CELL STILL CANNOT, until that one additive line lands in `arms.py`.

WHAT IT ADDS, all outside the digest path: the ladder registration, and a per-rung mechanism dump
(the arm's own stats, the planner limb's weight source, and rung 4's request-deferral report) so
Step 2b can report COUNTS BY MECHANISM rather than only a digest that differs.
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

import arms_final_ladder as FL                                                 # noqa: E402
import cf_pd_one_cell as C                                                      # noqa: E402

_BUILT: List[Any] = []


def _register_capturing() -> None:
    """Register the final-rung names through the module's OWN guard, each factory wrapped."""
    import arms as A                                                        # noqa: PLC0415
    FL.register()                     # raises if it would shadow a committed name

    def wrap(fn: Any) -> Any:
        def _f(**kw: Any) -> Any:
            arm = fn(**kw)
            _BUILT.append(arm)
            return arm
        return _f
    A.ARMS.update({k: wrap(v) for k, v in FL.FINAL_LADDER_ARMS.items()})


def _dump() -> Dict[str, Any]:
    if not _BUILT:
        return {"arm_built": False, "note": "no final-ladder arm was built in this process"}
    arm = _BUILT[-1]
    st = dict(getattr(arm, "stats", {}) or {})
    out: Dict[str, Any] = {
        "arm": getattr(arm, "name", None), "arm_built": True,
        "class": type(arm).__name__,
        "n_arms_built_in_this_process": len(_BUILT),
        "all_stats_nonzero": {k: v for k, v in sorted(st.items()) if v},
        "pd_counters": {k: v for k, v in sorted(st.items()) if str(k).startswith("pd_")},
        "rd_counters": {k: v for k, v in sorted(st.items()) if str(k).startswith("rd_")},
        "deficit_counters": {k: v for k, v in sorted(st.items()) if "deficit" in str(k)},
    }
    for name, fn in (("planner_limb_w_source", "planner_weight_report"),
                     ("rd_report", "rd_report"),
                     ("deficit_feed_report", "deficit_feed_report")):
        if hasattr(arm, fn):
            try:
                out[name] = getattr(arm, fn)()
            except Exception as exc:                                        # noqa: BLE001
                out[name + "_error"] = repr(exc)
    out["W_WIRED_PROOF"] = getattr(arm, "W_WIRED_PROOF", None)
    import arms_v6state as VS                                              # noqa: PLC0415
    import release_recheck as RR                                           # noqa: PLC0415
    out["switches_read_back"] = {
        "qcache_key_fix_D188": VS.qcache_key_fix_enabled(arm),
        "release_recheck_D179_4": RR.arm_enables(arm),
        "release_recheck_types": (list(RR.types_for(arm)) if RR.arm_enables(arm) else None)}
    return out


if __name__ == "__main__":
    mech = None
    if "--mech-out" in sys.argv:
        i = sys.argv.index("--mech-out")
        mech = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    _register_capturing()
    rc = C.main()
    if mech:
        Path(mech).write_text(json.dumps(_dump(), indent=1, default=float))
    raise SystemExit(rc)
