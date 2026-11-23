#!/usr/bin/env python3
"""Score proof (a): every reported baseline's DRY digest against its committed bar.

Reads results/orchestration/live2/ladder_final/d208_proof_a_bars.json for the bars and
ladder_final/cells/*.json for the measurements, so it can be re-run as cells land and always
reports the SAME verdict from the committed table rather than a remembered number.

ESCALATION RULE, from D208: if any arm MOVES, stop the sweep and report. A moved baseline would
invalidate the comparison set the whole ladder is judged against.

LOAD: each cell's loadavg at start is recorded as a MAGNITUDE in ladder_final/d208_proof_a_loadavg.json
and echoed here. The boundary that matters: for --cutoff-off DIGEST cells load is not a
comparability threat, because the planner wall-clock cutoff is patched off and the time-dependent
quantity is out of play; for anything TIMING-dependent it is. That is carried by the mechanism plus
the bit-exact matches recorded here, NOT by precedent, and the correction field in the bars file
records why an earlier precedent claim was withdrawn.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LF = ROOT / "results/orchestration/live2/ladder_final"


def main() -> int:
    bars = json.loads((LF / "d208_proof_a_bars.json").read_text())["bars"]
    loads = {}
    lp = LF / "d208_proof_a_loadavg.json"
    if lp.exists():
        loads = {k: v.get("loadavg_1min_at_start")
                 for k, v in json.loads(lp.read_text()).get("per_cell", {}).items()}
    got = {}
    for p in sorted(glob.glob(str(LF / "cells" / "*.json"))):
        if ".rows." in p:
            continue
        try:
            d = json.load(open(p))
        except Exception:                                                  # noqa: BLE001
            continue
        a = d.get("arm")
        if a in bars and isinstance(d.get("digest"), str):
            got[a] = (d["digest"], d.get("rows"), os.path.basename(p))
    moved, matched = [], []
    print("%-26s %-17s %-7s %-17s %-7s %-6s %s" % ("arm", "measured", "rows", "bar", "rows",
                                                   "load", "verdict"))
    for a in sorted(bars):
        b = bars[a]
        exp = (b["digest"], b["rows"])
        if a not in got:
            print("%-26s %-17s %-7s %-17s %-7s %-6s PENDING" % (a, "-", "-", exp[0], exp[1], "-"))
            continue
        g = got[a]
        ok = (g[0], g[1]) == exp
        (matched if ok else moved).append(a)
        print("%-26s %-17s %-7s %-17s %-7s %-6s %s"
              % (a, g[0], g[1], exp[0], exp[1],
                 (("%.2f" % loads[a]) if loads.get(a) is not None else "?"),
                 "MATCH" if ok else "*** MOVED ***"))
    n = len(bars)
    print("\n%d of %d measured, %d match, %d MOVED" % (len(got), n, len(matched), len(moved)))
    if moved:
        print("\nESCALATE AND STOP: %s" % (", ".join(moved),))
        print("A moved baseline invalidates the comparison set the final ladder is judged against.")
        return 1
    if len(got) < n:
        print("sweep incomplete; nothing has moved so far")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
