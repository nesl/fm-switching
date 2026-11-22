#!/usr/bin/env python3
"""D175 (2): the over-limit rule is ON at every covex-v6 rung, and rung 0 to 2 cells stay reusable.

ONE DRY CELL PER PROCESS. This is not fussiness: a second dry run inside one process does not
reproduce the first (covex-v6-state gave 15,871 then 16,109 rows in one process, with
`state_decisions` itself moving 44,300 to 45,337), so a proof that runs several cells in one
process compares the first against a polluted second. Separate processes with identical setup DO
reproduce exactly. The time limit is NOT the cause: its own counter says 1 to 2 abandonments out
of 44,300 state decisions, 0.002 percent, and two fresh-process runs agree whether it is on or
off. The pollution is an OPEN defect, recorded as one; this driver is written so it cannot be
confused with the thing being proved.

WHAT IS PROVED. For each rung, the SAME arm with the rule off and with it on, on the cell where
over-limit questions exist (seed 7, posted workload, rq30 re-asks) and on one where they do not
(seed 4): the digests must be EQUAL, because no arm of ours sends an over-limit request. Equality
is what keeps the committed rung 0 to 2 cells reusable under D172 (2).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FRESH = Path("/tmp/claude-1001/fresh.py")
CASES = [
    # (arm, seed, posted?)  rung 0, 1, 2 on the cell where the mechanism EXISTS
    ("covex-v6-base", 7, True),
    ("covex-v6-rules", 7, True),
    ("covex-v6-state", 7, True),
    # and on a cell where it does not, so the rule must be invisible there too
    ("covex-v6-rules", 4, False),
]


def run(arm: str, rule: str, seed: int, posted: bool) -> Dict[str, Any]:
    cmd = [sys.executable, str(FRESH), arm, rule, str(seed)]
    if posted:
        cmd.append("posted")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
    line = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not line:
        return {"error": ((p.stderr or "").strip().splitlines() or ["no output"])[-1][:300]}
    return json.loads(line[-1])


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "D175 (2): the D170 over-limit rule changes no decision at rungs 0 to 2",
        "_protocol": ("one dry cell per process; a second run inside one process does not "
                      "reproduce the first, which is an OPEN defect recorded separately"),
        "_why_seed_7": ("the 18 over-limit recall questions exist only at seed 7 under rq30 "
                        "re-asks (34,051 to 52,861 tokens); seeds 4 to 6 top out near 26,900, so "
                        "a null there is UNEXERCISED and proves nothing about the rule"),
        "cases": [], }
    for arm, seed, posted in CASES:
        off = run(arm, "off", seed, posted)
        on = run(arm, "on", seed, posted)
        same = (off.get("digest") is not None and off.get("digest") == on.get("digest")
                and off.get("rows") == on.get("rows"))
        out["cases"].append({"arm": arm, "seed": seed, "posted_workload": posted,
                             "rule_off": off, "rule_on": on, "identical": bool(same)})
        print("%-18s seed %d %-8s off=%s/%s on=%s/%s  %s" % (
            arm, seed, "posted" if posted else "default",
            off.get("digest"), off.get("rows"), on.get("digest"), on.get("rows"),
            "IDENTICAL" if same else "MOVED"), flush=True)
    ok = bool(out["cases"]) and all(c["identical"] for c in out["cases"])
    out["verdict"] = ("PASS: the rule changes no decision on any of the %d cases, so the "
                      "committed rung 0 to 2 cells stay reusable under D172 (2)" % len(CASES)
                      if ok else
                      "FAIL: the rule moved decisions on %s; those committed cells are NOT "
                      "reusable under the rule and must be rerun"
                      % [(c["arm"], c["seed"]) for c in out["cases"] if not c["identical"]])
    dest = REPO / "results/orchestration/live2/frozen_test/d175_digest_proofs.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(out["verdict"])
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
