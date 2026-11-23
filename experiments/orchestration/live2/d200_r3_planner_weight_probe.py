#!/usr/bin/env python3
"""D200 item 1c: HOW MANY RUNG-3 STATE DECISIONS WOULD CHANGE if rung 3's planner limb read the
live `deficit_feed` instead of the unfed counter. READ-ONLY on rung 3: nothing is committed to the
arm, and this probe is the only thing that changes.

WHY A PROBE AND NOT AN EDIT. The ruling is "DRY MEASUREMENT ONLY, NO CELLS, AND DO NOT CHANGE RUNG
3", so the second condition is produced by patching the planner's weight source inside THIS process
only, exactly as `cf_pd_one_cell.py --diag-epoch-cache-key` tests a hypothesis without editing a
file the session does not own. Rung 3's committed digest is reproduced on the BASELINE side of this
same probe, which is the control that says the instrument did not disturb the arm.

ONE CELL PER PROCESS, so this script runs ONE side and is invoked twice.

THE WEIGHT MAPPING IS THE ARM'S OWN. The adapter does not invent a device lookup: it calls the
arm's `_fairfeed_resolve_device` and then the arm's `_feed.weight_device`, so the planner weight and
rung 3's ordering weight cannot disagree about which device a decision is about.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ARM = "covex-v6-fair-c5attr"


class LivePlannerWeights:
    """The live rung-3 feed, adapted to the planner's weight interface. Counts every read."""

    def __init__(self, arm: Any) -> None:
        self._arm = arm
        self.reads = 0
        self.unresolved = 0
        self.above_floor = 0

    def _w(self, device_id: Any) -> float:
        self.reads += 1
        did = self._arm._fairfeed_resolve_device(device_id, None)
        if did is None:
            self.unresolved += 1
            return 1.0
        w = float(self._arm._feed.weight_device(did))
        if w > 1.0:
            self.above_floor += 1
        return w

    def weight(self, device_id: Any) -> float:
        return self._w(device_id)

    def shortfall(self, device_id: Any) -> float:
        did = self._arm._fairfeed_resolve_device(device_id, None)
        return 0.0 if did is None else float(self._arm._feed.shortfall_device(did))

    def starving(self, device_id: Any, threshold: float = 0.10) -> bool:
        return self.shortfall(device_id) >= float(threshold)

    def as_dict(self) -> Dict[str, Any]:
        return {"source": "deficit_feed.DeficitFeed.weight_device via the arm's own resolver",
                "reads": self.reads, "unresolved": self.unresolved,
                "reads_above_the_w1_floor": self.above_floor}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", required=True, choices=("baseline", "planner_fed"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sys.argv = ["x", "--arm", ARM, "--seed", "4", "--n", "16", "--run-s", "1200", "--cutoff-off"]
    import arms as A                                                       # noqa: PLC0415
    import arms_v6state as VS                                              # noqa: PLC0415
    import cf_pd_one_cell as C                                             # noqa: PLC0415

    held: Dict[str, Any] = {}
    orig_factory = A.ARMS[ARM]

    def _factory(**kw: Any) -> Any:
        arm = orig_factory(**kw)
        held["arm"] = arm
        return arm
    A.ARMS[ARM] = _factory

    adapters: List[LivePlannerWeights] = []
    if a.side == "planner_fed":
        orig_engine = VS.V6StateArm._cf_engine

        def _engine(self: Any) -> Any:
            cf = orig_engine(self)
            if not getattr(cf, "_d200_probe_wired", False) and hasattr(self, "_feed"):
                ad = LivePlannerWeights(self)
                cf.counters = ad
                cf._d200_probe_wired = True
                adapters.append(ad)
            return cf
        VS.V6StateArm._cf_engine = _engine

    C.main()

    arm = held.get("arm")
    cf = arm._cf_engine() if arm is not None else None
    log = []
    for d in (getattr(cf, "log", None) or []):
        log.append({"kind": d.kind, "decision_id": d.decision_id, "device_id": d.device_id,
                    "chosen": d.chosen, "base_choice": d.base_choice, "cf_choice": d.cf_choice,
                    "deviated": bool(d.deviated),
                    "value_cf": (None if d.value_cf is None else round(float(d.value_cf), 9)),
                    "delta": (None if d.delta is None else round(float(d.delta), 9)),
                    "margin": (None if d.margin is None else round(float(d.margin), 9))})
    out = {"side": a.side, "arm": ARM, "n_decisions_logged": len(log),
           "counts": dict(getattr(cf, "counts", {}) or {}),
           "weight_source": (adapters[0].as_dict() if adapters
                             else {"source": "committed unfed cf_objective.DeficitCounters",
                                   "every_weight": 1.0}),
           "log": log}
    Path(a.out).write_text(json.dumps(out, default=float))
    print(json.dumps({"side": a.side, "n_decisions_logged": len(log),
                      "weight_source": out["weight_source"]}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
