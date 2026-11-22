#!/usr/bin/env python3
"""D172: every v6 ladder name resolves THROUGH THE HARNESS'S OWN ENTRY POINT.

WHY THIS FILE EXISTS, and it is a failure of mine and not of the names. When these names were
first released I checked that they resolved by importing `arm_names_v6` in my own process and
calling `arms.make_arm`. They did. But `run_live2_real.py` imports `hybrid` and nothing else, so
in the HARNESS'S process the names were never registered, and the first `covex-v6-state` cell
died 80 s in at `arms.py:627` with `KeyError: unknown arm 'covex-v6-state'`. All four cells were
skipped.

A NAME RESOLVES IN THE PROCESS THAT RESOLVES IT. A check run in a process the harness does not
use is not a check of the harness, however carefully it is run, and `make_arm` returning an object
proves only that whatever that caller imported was enough. So this proof spawns
`run_live2_real.py` ITSELF, as a subprocess, with the real command line, and reads what the
harness does with the name. The fix is in `arms.py`, beside the other arm families, so the name is
registered by importing `arms` at all and no caller has to know to import anything else.

THE NEGATIVE CONTROL IS NOT OPTIONAL HERE. A proof that "no KeyError appeared" passes trivially if
the subprocess never reached `make_arm`, if the arg parser rejected something first, or if the
grep is looking for the wrong string. So a deliberately unknown name MUST still produce the
KeyError. If it does not, this check is broken and the five results below mean nothing.
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

LADDER = ["covex-v6-base", "covex-v6-rules", "covex-v6-state", "covex-v6-fair", "covex-v6"]
UNKNOWN = "covex-v6-not-an-arm"
MARKER = "unknown arm"


def _probe(name: str) -> Dict[str, Any]:
    """Run the harness's own entry point on this arm name, tiny and server-free."""
    with tempfile.TemporaryDirectory(prefix="v6name_") as td:
        p = subprocess.run(
            [sys.executable, str(ENTRY), "--arm", name, "--out", str(Path(td) / "cell"),
             "--n-devices", "2", "--run-s", "5"],
            cwd=str(HERE), capture_output=True, text=True, timeout=900)
    blob = (p.stdout or "") + (p.stderr or "")
    unknown = MARKER in blob
    return {"arm": name, "returncode": p.returncode,
            "raised_unknown_arm": unknown,
            "reached_make_arm": ("make_arm" in blob) or not unknown,
            "tail": blob.strip().splitlines()[-1][:200] if blob.strip() else ""}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "every v6 ladder name resolves through run_live2_real.py itself",
        "_register": ("the harness's OWN entry point, spawned as a subprocess with the real "
                      "command line. NOT a bare make_arm in this process, which is the check "
                      "that passed while the harness was failing"),
        "entry_point": str(ENTRY.relative_to(REPO)),
        "registered_in": "experiments/orchestration/live2/arms.py, beside the other arm families",
    }

    neg = _probe(UNKNOWN)
    out["P0_negative_control"] = {
        "_claim": "a name that is NOT registered still raises through this same path",
        "probe": neg,
        "verdict": ("PASS: the check can see an unresolved name"
                    if neg["raised_unknown_arm"] else
                    "FAIL: THE CHECK IS BROKEN, not the arms. An unknown name did not produce "
                    "%r, so 'no KeyError' below would mean nothing" % MARKER),
    }
    if not out["P0_negative_control"]["verdict"].startswith("PASS"):
        print(json.dumps(out, indent=1))
        return 1

    rows: List[Dict[str, Any]] = [_probe(n) for n in LADDER]
    out["ladder"] = rows
    ok = [r for r in rows if not r["raised_unknown_arm"]]
    out["all_resolve"] = len(ok) == len(rows)
    out["verdict"] = ("PASS: all %d ladder names resolve through the harness's own entry point"
                      % len(rows) if out["all_resolve"] else
                      "FAIL: %s do not resolve"
                      % [r["arm"] for r in rows if r["raised_unknown_arm"]])
    dest = REPO / "results/orchestration/live2/frozen_test/v6_harness_name_proof.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(out["P0_negative_control"]["verdict"])
    for r in rows:
        print("  %-16s rc=%-3s unknown_arm=%s" % (r["arm"], r["returncode"],
                                                  r["raised_unknown_arm"]))
    print(out["verdict"])
    print("wrote", dest)
    return 0 if out["all_resolve"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
