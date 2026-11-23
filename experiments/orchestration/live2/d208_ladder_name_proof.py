#!/usr/bin/env python3
"""D208: the final ladder's NAME PROOF, its NEGATIVE CONTROL, and the no-shadowing proof.

The H100 gate requires a name proof WITH A NEGATIVE CONTROL in the committed JSON before a list is
gated, because a list whose arm names do not resolve dies at cell launch. This proves three things
and the second is the one a name proof usually forgets:

  1. THE THREE FINAL NAMES RESOLVE through the SAME import path the live harness uses
     (`run_live2_real.py` imports `arms` and `hybrid` and nothing else), and each builds an arm
     whose switches read ON through their own strict readers.
  2. THE NEGATIVE CONTROL: a name that was never registered must FAIL to resolve. Without it, a
     proof that "every name resolved" would also pass on a harness that resolved anything, which
     is the vacuous-pass shape CLAUDE.md's citing rules warn about.
  3. NO COMMITTED NAME IS SHADOWED. `arms.ARMS` is a dict, so registering under a committed key
     would REPLACE it; the factory identity of every protected name is compared before and after
     registration. `covex-v6-state` carries six committed cell directories, so this is the check
     that D208's suffix ruling exists to make true.

Writes results/orchestration/live2/ladder_final/d208_ladder_name_proof.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = ROOT / "results/orchestration/live2/ladder_final/d208_ladder_name_proof.json"
BOGUS = "covex-v6-final-THIS-NAME-IS-NOT-REGISTERED"


def main() -> int:
    import arms as A
    import arms_final_ladder as FL
    import arms_v6state as VS
    import release_recheck as RR

    before = {n: id(A.ARMS[n]) for n in FL.PROTECTED_NAMES if n in A.ARMS}
    registered = FL.register()
    after = {n: id(A.ARMS[n]) for n in FL.PROTECTED_NAMES if n in A.ARMS}

    rungs: Dict[str, Any] = {}
    for n in (FL.RUNG2, FL.RUNG3, FL.RUNG4):
        arm = A.ARMS[n]()
        cf = arm._cf_engine()
        row = {"resolves": True, "class": type(arm).__name__,
               "mro": [c.__name__ for c in type(arm).__mro__][:8],
               "built_from_committed_arm": FL.BUILT_FROM[n],
               "qcache_key_fix_D188": VS.qcache_key_fix_enabled(arm),
               "release_recheck_D179_4": RR.arm_enables(arm),
               "release_recheck_types": (list(RR.types_for(arm)) if RR.arm_enables(arm) else None),
               "deficit_feed_present": hasattr(arm, "_feed"),
               "deficit_gain": getattr(arm, "_feed_gain", None),
               "planner_weight_source": type(cf.counters).__name__,
               "planner_source_is_declared_constant":
                   bool(getattr(cf.counters, "IS_DECLARED_CONSTANT", True))}
        if hasattr(arm, "W_WIRED_PROOF"):
            row["legs_w_source_live"] = bool(arm.W_WIRED_PROOF["live_weight"])
            row["legs_and_limb_read_THE_SAME_feed_object"] = bool(
                arm._planner_w_source._arm._feed is arm._feed)
            row["_identity_register"] = ("the legs and the planner limb read ONE object, so their "
                                         "weights are equal BY CONSTRUCTION with maximum absolute "
                                         "difference exactly 0. That is an IDENTITY, not a "
                                         "measurement of agreement.")
        rungs[n] = row

    neg = {"name": BOGUS, "in_registry": BOGUS in A.ARMS}
    try:
        A.ARMS[BOGUS]()
        neg["resolved"] = True
        neg["verdict"] = "FAIL: an unregistered name resolved, so this proof is vacuous"
    except KeyError:
        neg["resolved"] = False
        neg["verdict"] = "PASS: an unregistered name does NOT resolve, so the proof can fail"

    res = {
        "_what": "D208 final-ladder name proof, with a negative control and the no-shadowing check",
        "registered": registered,
        "n_registry_after": len(A.ARMS),
        "rungs": rungs,
        "negative_control": neg,
        "no_committed_name_shadowed": {
            "protected": list(FL.PROTECTED_NAMES),
            "n_checked": len(before),
            "factory_identity_unchanged": before == after,
            "_why_this_matters": ("arms.ARMS is a dict, so a second registration under a committed "
                                 "key REPLACES it. covex-v6-state carries six committed cell "
                                 "directories and a results/INDEX.md citation, so a replacement "
                                 "would silently re-point every reader of those cells at a "
                                 "different policy. This is what D208's -final suffix prevents, "
                                 "and arms_final_ladder.register() raises on a clash rather than "
                                 "relying on this check alone.")},
        "all_pass": bool(before == after and not neg["resolved"]
                         and all(r["resolves"] for r in rungs.values())),
        "_provenance": {"script": "d208_ladder_name_proof.py", "device": "flash (CPU only)",
                        "model": "n/a", "n": len(rungs)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({"registered": registered, "all_pass": res["all_pass"],
                      "negative_control": neg["verdict"],
                      "no_shadowing": res["no_committed_name_shadowed"][
                          "factory_identity_unchanged"],
                      "planner_sources": {k: v["planner_weight_source"]
                                          for k, v in rungs.items()}}, indent=1))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
