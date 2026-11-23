#!/usr/bin/env python3
"""ONE dry cell per process for the RUNG-4-ON-RUNG-3 arms (`covex-v6-cf-c5attr`).

A WRAPPER, NOT A SECOND RUNNER, AND THE DIGEST IS NOT RECOMPUTED HERE. Everything that makes a
digest comparable - the posted knobs, the seed allowlist, the planner wall-clock patch, the
one-cell-per-process rule and above all the DIGEST RECIPE - lives in `cf_pd_one_cell.py` and is
reused by CALLING ITS `main()`. A second copy of that recipe is how two digests of the same rows
stop matching, which already produced one phantom discrepancy in this project, so this file
contains no `sha256` and no `json.dumps` of any row.

TWO THINGS ARE ADDED, both outside the digest path.

  1. `arms_v6cfr3` is registered before `main()` runs, so the rung-4 names resolve. Every
     registration `cf_pd_one_cell.main` does itself is an additive `ARMS.update`, so it cannot
     displace them.
  2. The question-deferral leg's own counters and trace are written to a SECOND file, named by
     `--rd-out`. `cf_pd_one_cell` emits every `pd_*` counter by prefix and knows nothing about
     `rd_*`, and the arm instance it captures is private to its own `main`. So the factories are
     wrapped here to stash the instance they build, and the extra report is dumped after `main()`
     has returned. The arm is not touched before or during the run.

Accepts exactly the flags `cf_pd_one_cell.py` accepts, plus `--rd-out`.
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

import arms_v6cfr3 as R                                                        # noqa: E402
import cf_pd_one_cell as C                                                     # noqa: E402

_BUILT: List[Any] = []


def _register_capturing() -> None:
    """Register the rung-4 names, each factory wrapped so the instance it builds is kept."""
    import arms as A                                                       # noqa: PLC0415

    def wrap(fn: Any) -> Any:
        def _f(**kw: Any) -> Any:
            arm = fn(**kw)
            _BUILT.append(arm)
            return arm
        return _f
    A.ARMS.update({k: wrap(v) for k, v in R.V6CFR3_ARMS.items()})


def _rd_dump() -> Dict[str, Any]:
    if not _BUILT:
        return {"arm_built": False,
                "note": "no rung-4 arm was built in this process; the cell ran another family"}
    arm = _BUILT[-1]
    st = dict(getattr(arm, "stats", {}) or {})
    out: Dict[str, Any] = {
        "arm": getattr(arm, "name", None),
        "arm_built": True,
        "n_arms_built_in_this_process": len(_BUILT),
        "rd_counters": {k: v for k, v in sorted(st.items()) if str(k).startswith("rd_")},
        "pd_counters": {k: v for k, v in sorted(st.items()) if str(k).startswith("pd_")},
        "w_wired_proof": getattr(arm, "W_WIRED_PROOF", None),
        "w_source": getattr(arm, "_pd_w_source", None),
    }
    if hasattr(arm, "rd_report"):
        out["rd_report"] = arm.rd_report()
    if hasattr(arm, "live2_describe"):
        try:
            out["describe_rung4"] = arm.live2_describe().get("covex_v6_rung4")
        except Exception as exc:                                           # noqa: BLE001
            out["describe_rung4_error"] = repr(exc)
    out["rd_decisions"] = list(getattr(arm, "rd_decisions", []) or [])
    return out


if __name__ == "__main__":
    rd_out = None
    if "--rd-out" in sys.argv:
        i = sys.argv.index("--rd-out")
        rd_out = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    _register_capturing()
    rc = C.main()
    if rd_out:
        Path(rd_out).write_text(json.dumps(_rd_dump(), default=float))
    raise SystemExit(rc)
