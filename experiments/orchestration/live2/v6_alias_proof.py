#!/usr/bin/env python3
"""D172 (2): every ready v6 ladder name is the SAME ARM as the committed name it maps to, proved
by DECISION DIGEST on a dry cell, so its committed cells are reused and never rerun for the name.

WHAT THE DIGEST DOES AND DOES NOT COVER, because this is the whole register of the claim. It is
taken over the coordinator's own decision rows, which is where an arm's behaviour shows up. The
committed digest convention INCLUDES `arm_version` and EXCLUDES the arm's name (five differently
named hybrids share one committed digest), so a matching digest says the DECISIONS are identical
and says nothing by itself about whether the name travels into the outputs. That is the right
split for D172 (2): cell reuse is a claim about decisions.

THE POSITIVE CONTROL RUNS FIRST (consistency check 7). Two arms that MUST differ are digested and
must differ. Without it a digest function that returned a constant, or a dry runner that ignored
its arm argument, would make every identity below pass and mean nothing.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arm_names_v6 as V6                                                      # noqa: E402

# seeds 4 to 7 only, per the standing rule; one dry cell is enough for an identity claim.
CELL = dict(seed=4, n=8, run_s=600.0, ratio="50:50",
            robot_question_set="lh_req", ss_question_set="ss2")


def _digest(rows: Sequence[Dict[str, Any]], ignore: Sequence[str] = ()) -> str:
    rr = [{k: v for k, v in r.items() if k not in ignore} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _dry(arm_name: str) -> List[Dict[str, Any]]:
    import test_hybrid as TH
    rows, _st = TH.dry(arm_name, CELL["seed"], CELL["n"], run_s=CELL["run_s"],
                       ratio=CELL["ratio"], robot_question_set=CELL["robot_question_set"],
                       ss_question_set=CELL["ss_question_set"])
    return list(rows or [])


def _committed_cells(arm: str) -> int:
    """How many COMMITTED cells this arm actually has, counted off the frozen-test tree.

    D172 (2) says an identical arm's cell is REUSED and never rerun. That sentence is only worth
    anything where cells exist, so the count is reported beside every identity: "reused" over
    zero cells is vacuous and must not read as if the rung were covered.
    """
    root = REPO / "results/orchestration/live2/frozen_test/runs"
    if not root.exists():
        return 0
    n = 0
    for p in root.rglob("*"):
        if p.is_dir() and p.name.startswith(arm + "_"):
            n += 1
    return n


def _kinds(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        k = str(r.get("kind"))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    V6.register()
    out: Dict[str, Any] = {
        "_what": "D172 (2) identity of every ready v6 ladder name with its committed arm",
        "_register": ("DRY cell, no GPU and no engine: the claim is that the two names produce "
                      "the same DECISIONS, which is what cell reuse rests on"),
        "cell": dict(CELL, dry=True),
        "digest_convention": ("sha256 over the decision rows, 16 hex; the committed convention "
                              "includes arm_version and does not key on the arm's name"),
    }

    # ---- positive control FIRST
    a = _dry("hybrid-F-lhreq-noc3")
    b = _dry("b7-edf-feasibility")
    out["P0_positive_control"] = {
        "_claim": "two arms that must differ do differ, so the digest and the runner are live",
        "hybrid-F-lhreq-noc3": {"digest": _digest(a), "rows": len(a), "kinds": _kinds(a)},
        "b7-edf-feasibility": {"digest": _digest(b), "rows": len(b), "kinds": _kinds(b)},
        "differ": _digest(a) != _digest(b),
        "verdict": ("PASS: the check is live" if _digest(a) != _digest(b) else
                    "FAIL: THE CHECK IS BROKEN, not the arms; nothing below may be read"),
    }
    if not out["P0_positive_control"]["verdict"].startswith("PASS"):
        print(json.dumps(out, indent=1))
        return 1

    # ---- identity, rung by rung
    rows: List[Dict[str, Any]] = []
    for r in V6.V6_LADDER:
        if not r["ready"]:
            rows.append({"rung": r["rung"], "name": r["name"], "ready": False,
                         "missing": r["missing"],
                         "verdict": ("NOT BUILT: the name raises rather than resolving to the "
                                     "rung below, so no cell can run it by mistake")})
            continue
        old = r["implemented_by"]
        ro = _dry(old)
        rn = _dry(r["name"])
        same = _digest(ro) == _digest(rn)
        rows.append({
            "rung": r["rung"], "name": r["name"], "ready": True, "committed_as": old,
            "digest_committed_name": _digest(ro), "digest_v6_name": _digest(rn),
            "rows_committed_name": len(ro), "rows_v6_name": len(rn),
            "kinds": _kinds(rn),
            "identical": same,
            "committed_cells_of_the_old_name": _committed_cells(old),
            "verdict": ((("PASS: identical decisions, so %s's %d committed cells ARE %s's cells "
                          "and are reused, never rerun for the name"
                          % (old, _committed_cells(old), r["name"]))
                         if _committed_cells(old) else
                         ("PASS: identical decisions, but %s has ZERO committed cells, so there "
                          "is nothing to reuse and this rung is NOT covered by existing runs"
                          % old)) if same else
                        "FAIL: the v6 name changes decisions, so it is not an alias and its "
                        "cells may NOT be reused"),
        })
    out["identity"] = rows
    ready = [r for r in rows if r.get("ready")]
    out["all_ready_rungs_identical"] = all(r["identical"] for r in ready)
    out["ALL_PASS"] = (out["all_ready_rungs_identical"]
                       and out["P0_positive_control"]["verdict"].startswith("PASS"))
    dest = REPO / "results/orchestration/live2/frozen_test/v6_alias_proof.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(out["P0_positive_control"]["verdict"])
    for r in rows:
        print("  rung %d %-16s %s" % (r["rung"], r["name"], r["verdict"][:90]))
    print("ALL_PASS:", out["ALL_PASS"])
    print("wrote", dest)
    return 0 if out["ALL_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
