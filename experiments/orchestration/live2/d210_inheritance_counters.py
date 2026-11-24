#!/usr/bin/env python3
"""ONE dry cell per process, and all it does is DUMP EVERY COUNTER THE ARM KEPT (Session D).

D200 (4) requires that each rung list the mechanisms the rung below adopted and show each one is
LIVE in the new rung, and D200 (4) as the brief restates it requires a file:line AND A NON-ZERO
DRY COUNTER for every one. `cf_pd_one_cell` reports a fixed 22-key subset plus the `pd_` prefix,
which is the right subset for the counterfactual and leaves most of rung 2's and rung 3's own
counters (`harm_warm_*`, `deficit_feed*`, `c5_attr_*`, `release_recheck*`, `state_skipped_*`)
unreported. This file exists only to make those visible.

IT MAKES NO DIGEST CLAIM AND COMPUTES NO DIGEST. The digest-bearing cells are the
`d210_kv025_driver` cells, which go through `cf_pd_one_cell`'s committed recipe. A counter census
and a digest claim are different registers and this file is deliberately only the first: it does
not import `hashlib`, and a reader must not compare any number here against a committed digest.

Same posted knobs and same seed allowlist as `cf_pd_one_cell`, read FROM that module rather than
restated, so the workload cannot drift between the two.
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

import cf_pd_one_cell as C                                                     # noqa: E402
import cfr3_one_cell as X                                                      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--kv-scale", type=float, default=1.0)
    ap.add_argument("--enforce-kv", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.seed not in C.ALLOWED_SEEDS:
        raise SystemExit("seed %d is not one of %s" % (a.seed, list(C.ALLOWED_SEEDS)))

    import arms as A                                                      # noqa: PLC0415
    import arms_v6c5 as VC                                                # noqa: PLC0415
    import arms_v6cf as VCF                                               # noqa: PLC0415
    import arms_v6shares as VSH                                           # noqa: PLC0415
    import arms_v6state as VS                                             # noqa: PLC0415
    VS.register(); VC.register(); VSH.register(); VCF.register()          # noqa: E702
    X._register_capturing()

    import cf_instrument as CI                                            # noqa: PLC0415
    for _n in dir(CI):
        _o = getattr(CI, _n)
        if isinstance(_o, type) and hasattr(_o, "over_budget"):
            _o.over_budget = lambda self, budget_ms=None: False

    kv_tokens = None
    if a.kv_scale != 1.0:
        import test_hybrid as _TH0                                        # noqa: F401,PLC0415
        import test_live2_coord as TLC                                    # noqa: PLC0415
        kv_tokens = int(round(float(TLC.GPU_KV) * float(a.kv_scale)))
        TLC.GPU_KV = kv_tokens
    # ON THE INSTANCE, NOT THE CLASS. `CoordState` is a dataclass, so its generated `__init__`
    # carries the default False and a class-attribute set does not reach the instance (measured).
    # This is the point the committed live runner sets it at (`run_live2_real.py:489`).
    coords: List[Any] = []
    import coordinator as CO                                              # noqa: PLC0415
    _orig_init = CO.Live2Coordinator.__init__

    def _init(self: Any, *aa: Any, **kk: Any) -> None:
        _orig_init(self, *aa, **kk)
        if a.enforce_kv:
            self.st.kv_capacity_enforced = True
        coords.append(self)
    CO.Live2Coordinator.__init__ = _init

    held = {}
    import test_hybrid as TH                                              # noqa: PLC0415
    kw = {k: v for k, v in C.POSTED.items()
          if k in ("dashcam_format", "robot_upload", "robot_reask_mean_s")}
    rows, st = TH.dry(a.arm, a.seed, a.n, run_s=a.run_s, ratio=C.POSTED["ratio"],
                      patch=lambda arm: held.setdefault("arm", arm),
                      robot_question_set=C.POSTED["robot_question_set"],
                      ss_question_set=C.POSTED["ss_question_set"], **kw)
    arm = held.get("arm")
    out = {
        "_what": "every counter the arm kept on one dry cell; NO DIGEST CLAIM",
        "_register": ("DRY, LOGICAL pool (--kv-scale scales test_live2_coord.GPU_KV), flash CPU. "
                      "No engine and no --num-gpu-blocks-override."),
        "arm": a.arm, "seed": a.seed, "n": a.n, "run_s": a.run_s,
        "kv_scale": a.kv_scale, "gpu_kv_tokens": kv_tokens,
        "kv_capacity_enforced": bool(a.enforce_kv),
        "n_decision_rows": len(rows or []),
        "stats_all": {k: v for k, v in sorted(dict(st or {}).items())},
    }
    if coords:
        _st = coords[-1].st
        out["enforcement_proof"] = {
            "asked_for": bool(a.enforce_kv),
            "read_back": bool(getattr(_st, "kv_capacity_enforced", False)),
            "gpu_kv_tokens_on_the_state": int(getattr(_st, "gpu_kv_tokens", 0) or 0),
            "pressure": {k: v for k, v in sorted(dict(getattr(_st, "pressure", {}) or {}).items())
                         if not k.startswith("_")},
        }
    if arm is not None:
        try:
            out["describe"] = arm.live2_describe()
        except Exception as exc:                                          # noqa: BLE001
            out["describe_error"] = repr(exc)
        out["w_wired_proof"] = getattr(arm, "W_WIRED_PROOF", None)
        out["w_source"] = getattr(arm, "_pd_w_source", None)
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({"arm": a.arm, "kv_scale": a.kv_scale,
                      "kv_capacity_enforced": bool(a.enforce_kv),
                      "rows": out["n_decision_rows"],
                      "n_counters": len(out["stats_all"])}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
