#!/usr/bin/env python3
"""ONE dry cell per process for the FINAL-LADDER 0.25x re-run (StudyD216-KV025, check 3).

A WRAPPER OVER A WRAPPER, AND IT ADDS NOTHING TO THE DIGEST PATH. Session D's
`d210_kv025_one_cell.py` already carries everything that makes a digest comparable (the posted
knobs and seed allowlist and planner wall-clock patch of `cf_pd_one_cell.main`, the
latency-keeping patch, `--enforce-kv` applied on the coordinator INSTANCE and read back) and its
structure, channel split and classification scheme TRANSFER to this study. Session D's COUNTS do
not: `covex-v6-final` differs from `covex-v6-cf-c5attr` by the `id(obs)` cache-key fix, the state
planner reading the deficit feed at rung 3, and the alert release re-check, all decision-changing.
So this file re-points the arm NAMES and runs Session D's cell, rather than rebuilding either.

THE ONE THING IT ADDS is registration of the final rungs. `arms_final_ladder.register()` is NOT
called by any runner in the tree (its only other importer is `d208_ladder_name_proof`), so
`covex-v6-final` does not resolve in `cf_pd_one_cell` without this. Registration goes through
`arms_final_ladder.register()` itself, so D208's collision check against the committed names runs;
the three factories are then re-wrapped so the instance each builds is captured for the `--rd-out`
dump, exactly as `cfr3_one_cell._register_capturing` does for the committed rung-4 family.

THE ABLATION NAMES ARE REGISTERED HERE, NOT THERE. `arms_final_ladder.FINAL_LADDER_ARMS` has one
key per rung, so the off-switch identity bar and the Step 4 controls have no names to be run under.
They are added in THIS process only, each one a `make_rung4` call with exactly the keyword the
committed family uses for the same ablation (`arms_v6cfr3.V6CFR3_ARMS`), so the ablation is the
same ablation and no file the final ladder owns is touched.

  covex-v6-final-off          both compounds off; the OFF-SWITCH IDENTITY BAR. It must collapse to
                              `covex-v6-fair-final`. On the COMMITTED family it did not: Session D
                              section 3.0 pinned `covex-v6-cf-c5attr-off` 711 rows off its declared
                              rung-3 bar because `_Rung4Mixin._cf_engine` swaps the planner weight
                              source unconditionally while committed rung 3 does not read the feed.
                              In the final ladder rung 3 DOES read it (`_PlannerFeedMixin`), so this
                              cell is the test of whether that contamination is cured. It is a test,
                              not an assumption: the two modules use DIFFERENT wired-flags
                              (`_planner_deficit_wired` against `_rung4_planner_wired`), so rung 4
                              re-swaps a source that is already live.
  covex-v6-final-pdonly       protect-and-defer alone
  covex-v6-final-rqonly       question-deferral alone
  covex-v6-final-harm0        Step 4 mechanism control: harm zeroed at source on both legs
  covex-v6-final-margin-huge  Step 4 mechanism control: the BAR alone scaled

REGISTER. Every number from this file is DRY and LOGICAL, measured on flash's CPU. `--kv-scale`
scales `test_live2_coord.GPU_KV`, the coordinator's own pool; nothing here touches an engine, a
`--num-gpu-blocks-override` or a real KV allocator, and the decision latency is flash CPU
wall-clock inside the arm's `decide`, not an H100 number.

Flags: exactly `d216_final_kv025_one_cell.py` passes through to `d210_kv025_one_cell.py`, which is
`cf_pd_one_cell.py`'s plus `--rd-out`, `--pd-out`, `--lat-out` and `--enforce-kv`.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_final_ladder as FL                                                 # noqa: E402
import cfr3_one_cell as X                                                      # noqa: E402

RUNG4 = FL.RUNG4


def _ablations() -> Dict[str, Any]:
    """The rung-4 ablation names, each the same keyword the committed family uses."""
    return {
        RUNG4 + "-off": (lambda **kw: FL.make_rung4(RUNG4 + "-off", protect_defer=False,
                                                    request_defer=False, **kw)),
        RUNG4 + "-pdonly": (lambda **kw: FL.make_rung4(RUNG4 + "-pdonly", request_defer=False,
                                                       **kw)),
        RUNG4 + "-rqonly": (lambda **kw: FL.make_rung4(RUNG4 + "-rqonly", protect_defer=False,
                                                       **kw)),
        RUNG4 + "-harm0": (lambda **kw: FL.make_rung4(RUNG4 + "-harm0", control_harm_zero=True,
                                                      **kw)),
        RUNG4 + "-margin-huge": (lambda **kw: FL.make_rung4(RUNG4 + "-margin-huge",
                                                            control_margin_huge=True, **kw)),
    }


def _register_final_capturing() -> None:
    """Register the three final rungs plus the ablations, capturing every instance built.

    The capture list is `cfr3_one_cell._BUILT`, which is what `cfr3_one_cell._rd_dump` reads, so
    the `--rd-out` report Session D's runner writes needs no change to see a final-ladder arm.
    """
    import arms as A                                                       # noqa: PLC0415

    def wrap(fn: Any) -> Any:
        def _f(**kw: Any) -> Any:
            arm = fn(**kw)
            X._BUILT.append(arm)
            return arm
        return _f

    FL.register()                      # D208's collision check against the committed names
    names = dict(FL.FINAL_LADDER_ARMS)
    names.update(_ablations())
    A.ARMS.update({k: wrap(v) for k, v in names.items()})


if __name__ == "__main__":
    _orig = X._register_capturing

    def _both() -> None:
        _orig()                        # the committed rung-4 family, as Session D's runner expects
        _register_final_capturing()    # plus the final rungs, additively and last

    X._register_capturing = _both
    runpy.run_path(str(HERE / "d210_kv025_one_cell.py"), run_name="__main__")
