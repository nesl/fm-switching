#!/usr/bin/env python3
"""The rung-3 deficit-feed names resolve THROUGH THE HARNESS'S OWN ENTRY POINT, and the switch is
on for them and off for every other arm in the registry.

Same shape and the same reasons as `v6shares_name_proof.py`, which records the failure both files
inherit: the v6 names were first checked by importing their own module and calling `arms.make_arm`
IN A PROCESS THAT HAD IMPORTED THAT MODULE. They resolved. `run_live2_real.py` imports `arms` and
`hybrid` and nothing else, so in the HARNESS'S process the names did not exist, the first
covex-v6-state cell died 80 s in with `KeyError: unknown arm`, and all four cells were skipped. A
name resolves in the process that resolves it. So P1 spawns `run_live2_real.py` itself.

P0 IS NOT OPTIONAL. "No KeyError appeared" passes trivially if the subprocess never reached
`make_arm`, if the arg parser rejected something first, or if the marker string is wrong. P0 gives
the same path a deliberately unknown name and REQUIRES that it still raise. If it does not, this
check is broken and P1 means nothing.

P2 is a switch-leak sweep: every arm in the registry is constructed and `live2_deficit_feed` is
read off the whole delegation chain. It proves the switch is SET on these arms and on no other. It
does NOT prove the switch moves a decision; that is `d178_deficit_feed_proofs.py`, and it needs the
one-line coordinator change the report names.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ENTRY = HERE / "run_live2_real.py"
OUT = REPO / "results/orchestration/live2/frozen_test/d178_fairfeed_name_proof.json"

ARMS_UNDER_TEST = ["covex-v6-fair-shares", "covex-v6-fair-shares-off",
                   "covex-v6-fair-shares-gain0", "covex-v6-fair-c5attr",
                   "covex-v6-fair-c5attr-off", "covex-v6-fair-c5attr-gain0"]
# the OFF names carry the switch set to False on purpose, which is not a leak
EXPECTED_SWITCH_ON = [a for a in ARMS_UNDER_TEST if not a.endswith("-off")]
UNKNOWN = "covex-v6-fair-shares-not-an-arm"
MARKER = "unknown arm"

POSTED = ["--ratio", "40:40:20", "--robot-question-set", "lh_req", "--ss-question-set", "ss2",
          "--dashcam-format", "epg", "--robot-upload", "per-frame",
          "--robot-reask-mean-s", "30.0"]


def _probe(name: str, seed: int = 0) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="d178name_") as td:
        p = subprocess.run(
            [sys.executable, str(ENTRY), "--arm", name, "--out", str(Path(td) / "cell"),
             "--n-devices", "2", "--run-s", "5", "--seed", str(seed)] + POSTED,
            cwd=str(HERE), capture_output=True, text=True, timeout=1800)
    blob = (p.stdout or "") + (p.stderr or "")
    return {"arm": name, "seed": seed, "returncode": p.returncode,
            "raised_unknown_arm": MARKER in blob,
            "tail": blob.strip().splitlines()[-1][:300] if blob.strip() else ""}


def _chain(obj: Any) -> List[Any]:
    out: List[Any] = []
    o: Any = obj
    seen = set()
    while o is not None and id(o) not in seen:
        seen.add(id(o))
        out.append(o)
        o = o.__dict__.get("_rules") or o.__dict__.get("_base")
    return out


def _switch_sweep() -> Dict[str, Any]:
    import arms as A
    import arms_v6fairfeed as FF

    on: Dict[str, List[bool]] = {}
    off: List[str] = []
    leaked: Dict[str, List[bool]] = {}
    unconstructible: Dict[str, str] = {}
    weights_exposed: Dict[str, Any] = {}
    for name in sorted(A.ARMS):
        try:
            arm = A.make_arm(name)
        except Exception as exc:                                        # noqa: BLE001
            unconstructible[name] = "%s: %s" % (type(exc).__name__, exc)
            continue
        reads = [bool(vars(o).get(FF.SWITCH_ATTR, False)) for o in _chain(arm)]
        getter = getattr(arm, "live2_share_weights", None)
        if name in ARMS_UNDER_TEST:
            on[name] = reads
            weights_exposed[name] = (getter() if callable(getter) else "no accessor")
        elif any(reads):
            leaked[name] = reads
        else:
            off.append(name)
            if callable(getter):
                leaked[name + " (accessor without the switch)"] = reads
    return {"switch_name": FF.SWITCH_ATTR,
            "arms_under_test": on, "weights_exposed": weights_exposed,
            "n_other_arms_all_off": len(off),
            "other_arms_with_the_switch_on": leaked,
            "unconstructible": unconstructible,
            "_what_a_chain_is": ("the wrapper and every object `_rules`/`_base` reaches; a single "
                                 "getattr on the wrapper is the check that passes while the "
                                 "inner object decides differently")}


def main() -> int:
    for p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
              str(HERE.parent / "baselines")):
        if p not in sys.path:
            sys.path.insert(0, p)
    out: Dict[str, Any] = {
        "_what": ("the rung-3 deficit-feed names resolve through run_live2_real.py itself, and "
                  "live2_deficit_feed is on for them and off for every other registered arm"),
        "_register": ("P0 and P1 are SUBPROCESS probes of the harness's own entry point with the "
                      "posted knobs; P2 is an in-process attribute read and is a statement about "
                      "REGISTRATION ONLY, never about the switch moving a decision"),
        "entry_point": str(ENTRY.relative_to(REPO)),
        "posted_knobs": POSTED,
    }
    p0 = _probe(UNKNOWN)
    out["P0_negative_control"] = dict(
        _claim="an unknown name on the SAME path still raises, so P1 is not vacuous",
        probe=p0, verdict=("PASS" if p0["raised_unknown_arm"] else "FAIL: the check is broken"))
    p1 = [_probe(a) for a in ARMS_UNDER_TEST]
    out["P1_names_resolve_in_the_harness"] = dict(
        _claim="each rung-3 name reaches make_arm in the harness's own process",
        probes=p1,
        verdict=("PASS" if not any(r["raised_unknown_arm"] for r in p1) else "FAIL"))
    sweep = _switch_sweep()
    out["P2_switch_is_arm_scoped"] = dict(
        _claim=("live2_deficit_feed reads ON for the rung-3 arms that declare it and OFF for "
                "every other arm in the registry, on every object of each chain"),
        sweep=sweep,
        verdict=("PASS" if not sweep["other_arms_with_the_switch_on"]
                 and all(any(v) for k, v in sweep["arms_under_test"].items()
                         if k in EXPECTED_SWITCH_ON)
                 and all(not any(v) for k, v in sweep["arms_under_test"].items()
                         if k.endswith("-off")) else "FAIL"),
        _note=("the -off names carry the switch set to False deliberately; that is the Step 4 "
               "control, not a leak"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    bad = [k for k, v in out.items()
           if isinstance(v, dict) and str(v.get("verdict", "")).startswith("FAIL")]
    print(json.dumps({k: (v.get("verdict") if isinstance(v, dict) else v)
                      for k, v in out.items()}, indent=1))
    print("wrote", OUT)
    print("FAILED:", bad if bad else "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
