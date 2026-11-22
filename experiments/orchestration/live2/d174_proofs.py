#!/usr/bin/env python3
"""D174 (1) proofs: the uncached-only budget charge, and what it must NOT have moved.

B1  committed digests reproduce   the four recorded dry digests at the posted cell shape are
                                  byte-identical after the charge change
B2  before / after on a baseline  b7-edf-feasibility and hybrid-F-lhreq-noc3 produce the same
                                  decision digest in THIS tree and in a worktree at HEAD
B3  Step 2b                       the repriced arm's decisions differ from the unrepriced rung's,
                                  with the first differing decision named
B4  arm-scoped, not global        every arm's charge mode comes from the arm; moving the module
                                  default does not move a priced arm's charge

WHY B2 EXISTS AND B1 IS NOT ENOUGH. B1 compares against digests I recorded myself earlier in this
session's work, in this same tree. If some shared edit had moved both, B1 would agree with a
moved reference. B2 runs the OTHER SIDE of the comparison from git, at the commit before the
charge changed, through a separate process, so the reference cannot have followed the change.

THE CHARGE IS ARM-SCOPED FROM HERE ON (B4), and that is the lesson of covex-v6-state s6: the
pricing switch defaulted ON through a helper, I checked the two MODE literals instead of the
attribute that gates behaviour, and the cell died at t = 264 s of 1,200 with 44,382 refusals. A
module global that any code path can move is not a declaration.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d162_price as DP                                                        # noqa: E402

CELL = dict(seed=4, n=16, run_s=1200.0, ratio="50:50",
            robot_question_set="lh_req", ss_question_set="ss2")
SMALL = dict(CELL, n=8, run_s=600.0)

# recorded at the posted cell shape in results/.../v6state_attribution.json
COMMITTED = {"v5-rules-2": "ae997d6af16a2ef4",
             "covex-v6-state": "6e8927b9f7f92040",
             "covex-v6-state-off": "ae997d6af16a2ef4",
             "covex-v6-state-noprice": "ae997d6af16a2ef4"}
BEFORE_COMMIT = "f15fa90f"        # the commit before the D174 charge change
BASELINES = ["b7-edf-feasibility", "hybrid-F-lhreq-noc3"]


def _digest(rows: Sequence[Dict[str, Any]], ignore: Sequence[str] = ("arm_version",)) -> str:
    rr = [{k: v for k, v in r.items() if k not in ignore} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _dry(arm: str, cell: Dict[str, Any]):
    import arms_v6state as VS
    import test_hybrid as TH
    VS.register()
    rows, st = TH.dry(arm, cell["seed"], cell["n"], run_s=cell["run_s"], ratio=cell["ratio"],
                      robot_question_set=cell["robot_question_set"],
                      ss_question_set=cell["ss_question_set"])
    return list(rows or []), dict(st or {})


def b1_committed_digests() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for arm, want in COMMITTED.items():
        dec, _st = _dry(arm, CELL)
        got = _digest(dec)
        rows.append({"arm": arm, "committed": want, "now": got, "rows": len(dec),
                     "identical": got == want})
    ok = all(r["identical"] for r in rows)
    return {"_claim": "the charge change moved no unpriced arm's decisions",
            "cell": CELL, "rows": rows,
            "verdict": ("PASS: all %d recorded digests reproduce byte-identically" % len(rows)
                        if ok else
                        "FAIL: %s moved" % [r["arm"] for r in rows if not r["identical"]])}


def _digest_in_tree(tree: Path, arm: str, cell: Dict[str, Any]) -> Dict[str, Any]:
    """Run one dry cell inside an arbitrary checkout and return its digest."""
    script = r'''
import hashlib, json, sys
from pathlib import Path
HERE = Path(%r)
for p in (str(HERE), str(HERE/"fleet"), str(HERE/"v5"), str(HERE/"hybrid"),
          str(HERE.parent/"baselines")):
    sys.path.insert(0, p)
import test_hybrid as TH
rows, st = TH.dry(%r, %d, %d, run_s=%f, ratio=%r, robot_question_set=%r, ss_question_set=%r)
rows = list(rows or [])
rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
d = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                              default=float).encode()).hexdigest()[:16]
print(json.dumps({"digest": d, "rows": len(rows)}))
''' % (str(tree / "experiments/orchestration/live2"), arm, cell["seed"], cell["n"],
       cell["run_s"], cell["ratio"], cell["robot_question_set"], cell["ss_question_set"])
    p = subprocess.run([sys.executable, "-c", script],
                       cwd=str(tree / "experiments/orchestration/live2"),
                       capture_output=True, text=True, timeout=3600,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    line = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not line:
        return {"error": ((p.stderr or "").strip().splitlines() or ["no output"])[-1][:300]}
    return json.loads(line[-1])


def b2_before_after_on_baselines() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    td = tempfile.mkdtemp(prefix="d174_before_")
    tree = Path(td) / "wt"
    made = subprocess.run(["git", "worktree", "add", "--detach", str(tree), BEFORE_COMMIT],
                          cwd=str(REPO), capture_output=True, text=True)
    try:
        if made.returncode != 0:
            return {"_claim": "a baseline's decisions are identical before and after the change",
                    "verdict": "FAIL: could not create the before-worktree: %s"
                               % (made.stderr or "").strip()[:200]}
        for arm in BASELINES:
            before = _digest_in_tree(tree, arm, SMALL)
            after_rows, _st = _dry(arm, SMALL)
            after = {"digest": _digest(after_rows), "rows": len(after_rows)}
            rows.append({"arm": arm, "before_commit": BEFORE_COMMIT,
                         "before": before, "after": after,
                         "identical": before.get("digest") == after["digest"]})
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)],
                       cwd=str(REPO), capture_output=True, text=True)
        shutil.rmtree(td, ignore_errors=True)
    ok = bool(rows) and all(r["identical"] for r in rows)
    return {"_claim": ("a baseline's decisions are identical before and after the change, with "
                       "the BEFORE side taken from git and not from a recorded number"),
            "cell": SMALL, "rows": rows,
            "verdict": ("PASS: %d baseline(s) byte-identical across the change" % len(rows)
                        if ok else
                        "FAIL: %s" % [r for r in rows if not r["identical"]])}


def b3_step2b() -> Dict[str, Any]:
    """The switch must REACH A DECISION. Identical logs would be an ABSENT LINK, not a null."""
    a, _ = _dry("covex-v6-state", SMALL)
    b, _ = _dry("covex-v6-state-uo", SMALL)
    da, db = _digest(a), _digest(b)
    first = None
    n = 0
    for i in range(max(len(a), len(b))):
        ra = {k: v for k, v in (a[i] if i < len(a) else {}).items() if k != "arm_version"}
        rb = {k: v for k, v in (b[i] if i < len(b) else {}).items() if k != "arm_version"}
        if ra != rb:
            n += 1
            if first is None:
                first = {"index": i, "unrepriced": ra, "repriced": rb}
    return {"_claim": "the charge reaches a decision (CLAUDE.md Step 2b)",
            "cell": SMALL,
            "covex_v6_state_digest": da, "covex_v6_state_uo_digest": db,
            "rows": {"covex-v6-state": len(a), "covex-v6-state-uo": len(b)},
            "differing_decisions": n, "first_difference": first,
            "verdict": ("PASS: %d differing decisions, first at index %s"
                        % (n, None if first is None else first["index"]) if n else
                        "FAIL: the logs are identical, so the charge is an ABSENT LINK at this "
                        "cell and the comparison has not been run")}


def b4_mode_is_arm_scoped() -> Dict[str, Any]:
    import arms as A
    import arms_v6state as VS
    VS.register()
    rows: List[Dict[str, Any]] = []
    saved = DP.CHARGE_MODE
    try:
        for name in ("covex-v6-state-uo", "covex-v6-state-wo", "covex-v6-rules-uo",
                     "covex-v6-rules-wo", "covex-v6-state-d162"):
            arm = A.make_arm(name)
            declared = DP.arm_charge_mode(arm)
            DP.CHARGE_MODE = "first-token"            # move the global out from under it
            still = DP.arm_charge_mode(arm)
            DP.CHARGE_MODE = saved
            rows.append({"arm": name, "declared_mode": declared,
                         "mode_after_moving_the_global": still,
                         "unaffected_by_the_global": declared == still})
    finally:
        DP.CHARGE_MODE = saved
    ok = all(r["unaffected_by_the_global"] for r in rows)
    expected = {"covex-v6-state-uo": "uncached-only", "covex-v6-state-wo": "work-only",
                "covex-v6-rules-uo": "uncached-only", "covex-v6-rules-wo": "work-only",
                "covex-v6-state-d162": DP.RULED_CHARGE_MODE}
    named = all(r["declared_mode"] == expected[r["arm"]] for r in rows)
    return {"_claim": ("each arm's charge mode is the ARM's and cannot be moved by the module "
                       "default, and each arm's mode is the one its name claims"),
            "ruled_mode": DP.RULED_CHARGE_MODE, "rows": rows,
            "modes_match_the_names": named,
            "verdict": ("PASS: %d arms, each pinned to its own mode and matching its name"
                        % len(rows) if (ok and named) else
                        "FAIL: the module default moves an arm's charge" if not ok else
                        "FAIL: an arm's mode does not match its name: %s"
                        % [r for r in rows if r["declared_mode"] != expected[r["arm"]]])}


def main() -> int:
    out: Dict[str, Any] = {"_what": "D174 (1) uncached-only budget charge proofs",
                           "price": DP.as_dict()}
    out["B4_mode_is_arm_scoped"] = b4_mode_is_arm_scoped()
    out["B3_step2b"] = b3_step2b()
    out["B2_before_after_on_baselines"] = b2_before_after_on_baselines()
    out["B1_committed_digests"] = b1_committed_digests()
    out["ALL_PASS"] = all(v["verdict"].startswith("PASS") for v in out.values()
                          if isinstance(v, dict) and "verdict" in v)
    dest = REPO / "results/orchestration/live2/frozen_test/d174_proofs.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out.items():
        if isinstance(v, dict) and "verdict" in v:
            print("%-30s %s" % (k, v["verdict"][:100]))
    print("ALL_PASS:", out["ALL_PASS"])
    print("wrote", dest)
    return 0 if out["ALL_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
