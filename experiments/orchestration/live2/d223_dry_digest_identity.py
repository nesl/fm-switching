#!/usr/bin/env python3
"""D223 (2): THE 1x BYTE-IDENTITY PROOF, ON THE PROJECT'S OWN DETERMINISTIC DRY DIGEST.

WHY THIS INSTRUMENT AND NOT A REALTIME CELL, WHICH IS A FINDING IN ITS OWN RIGHT. The first
attempt at this proof ran paired dry-but-real-path cells through `run_live2_real.py`. Its control
caught that the instrument is unusable for a byte-identity claim: running the SAME tree twice, the
decision log differed in 169 rows on `t` and, more seriously, in real decision fields -
`traffic_mix` on 38 rows, `opportunity_ids` on 10, and `kind`, `note`, `representation` and
`representation_defaulted` on 4 each. `run_live2_real.py` drives the emulator with
`realtime=True`, so the cell races a wall clock and its decisions depend on how the box was
loaded. Of three runs of one arm, two agreed exactly and one diverged, so a two-run comparison on
that instrument would have returned "identical" or "moved" more or less at random, and either
answer would have looked clean. **A before/after agreement there is not evidence, and neither is a
disagreement.** That measurement is kept in `d223_byte_identity_realtime_probe.json` as the reason
this file exists, not as a proof of anything about the fix.

`hybrid/test_hybrid.dry` runs the SAME coordinator, arm and emulator with `realtime=False`: a
SIMULATED clock, no wall-clock race, deterministic. It is also the project's own instrument for
exactly this claim - `coordinator._belief_prefix_record` argues in its own docstring that a change
"moves no dry digest", with `test_hybrid.dry`'s stripped `decision.jsonl` rows as the digested
object and `STRIP = ("arm", "decision_latency_ms", "decision_id")` as the committed strip set. The
proof below is made on that object, with that strip set, unwidened.

WHAT IS COMPARED. For each arm, the full list of stripped decision rows, positionally, as
`test_hybrid._differing` compares them. Equal row counts and zero differing rows is the claim; the
first differing row is printed when there is one, so a failure is adjudicable and not just
reported.

WHAT THIS INSTRUMENT DOES AND DOES NOT REACH. It builds the coordinator IN-PROCESS, so it
exercises the four arm read sites (`hybrid/hybrid_arm.py`, `arms_v6cf.py`, `arms_v6cfr3.py`,
`arms_v6fair.py`) and NOT the `procsplit.py` hand-off, which only a split-mode run builds. The
hand-off is covered instead by the unit proofs and by the fail-loud it raises when a cfg declares a
server and carries no limit. Said here so the gap is read from the proof rather than discovered.
In a dry run no server is configured, so the limit comes from `configure_arch_default()` and is
32,768 - the same number the old constant held, which is why 1x identity is the right claim and
why only the 0.5x value moves.

THE CONTROL IS RUN FIRST AND IS NOT OPTIONAL (CLAUDE.md check 7). Each tree is run TWICE on the
first arm. If a tree disagrees with itself, this instrument is no better than the one it replaced
and the script says so and refuses the comparison. An instrument is not trusted here because it is
expected to be deterministic; it is trusted because it was observed to be.

Usage:
  python d223_dry_digest_identity.py --before LIVE2_DIR --after LIVE2_DIR --out FILE [--arm A ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent

# Every arm here, and WHY. Each module this ruling touched has a read site reached by at least one
# arm, plus committed baselines on paths the ruling does not touch as the positive control.
ARM_WHY = {
    "covex-v6-base": "the ladder base; the control inside the covex family",
    "covex-v6-state-uo-c5attr": "rung 2, the base the rung-4 compound is built on",
    "covex-v6-fair-c5attr": "RUNG 3, THE ARM THE H100 IS BLOCKED ON; reads arms_v6fair",
    "covex-v6-cf-pd-c5attr": "rung 4 on the rung-2 base; reads arms_v6cf's over-limit skip",
    "covex-v6-cf-c5attr": "rung 4 on the rung-3 base; reads arms_v6cfr3's VCF.CL.limit_tokens()",
    "hybrid-c1c2k2c5": "a hybrid arm: the canonical definition's own read site in hybrid_arm",
    "hybrid-base": "the hybrid identity baseline test_hybrid's own proofs are built on",
    "b7-edf-feasibility": "POSITIVE CONTROL: a committed baseline on a path this ruling does not "
                          "touch. If it moves, the harness moved and not the fix",
}
DEFAULT_ARMS = tuple(ARM_WHY)

# The workload the live cells run (D170's CELL_ARGS shape), so the proof sits on the real workload
# and not on test_hybrid's 50:50 oneframe defaults.
WORKLOAD = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
                dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)

_CHILD = r'''
import json, sys
tree = sys.argv[1]
arm = sys.argv[2]
seed = int(sys.argv[3]); n = int(sys.argv[4]); run_s = float(sys.argv[5])
wl = json.loads(sys.argv[6])
# THE TREE UNDER TEST SUPPLIES EVERY MODULE. The harness's own directory is removed from sys.path
# first, so a module of the same name in the tree that holds this script cannot shadow one in the
# tree being measured. Getting this backwards would measure one tree twice and call it identity.
drop = {%(selfdir)r, ""}
sys.path[:] = [p for p in sys.path if p not in drop]
for p in (tree + "/hybrid", tree, tree + "/fleet", tree + "/v5", tree + "/tests",
          tree + "/../baselines", tree + "/../sim", tree + "/../../lib"):
    sys.path.insert(0, p)
import test_hybrid as TH
rows, stats = TH.dry(arm, seed, n, run_s, **wl)
print("@@D223@@" + json.dumps({"rows": rows, "strip": list(TH.STRIP),
                               "test_hybrid_file": TH.__file__}))
'''


def collect(tree: Path, arm: str, a: Any) -> Dict[str, Any]:
    """One deterministic dry run of `arm`, with every module taken from `tree`."""
    src = _CHILD % {"selfdir": str(HERE)}
    cmd = [sys.executable, "-c", src, str(tree), arm, str(a.seed), str(a.n), str(a.run_s),
           json.dumps(WORKLOAD)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd="/")
    tail = (p.stderr or "")[-1500:]
    line = next((l for l in (p.stdout or "").splitlines() if l.startswith("@@D223@@")), None)
    if line is None:
        return {"tree": str(tree), "arm": arm, "ok": False, "returncode": p.returncode,
                "stderr_tail": tail}
    d = json.loads(line[len("@@D223@@"):])
    rows = d["rows"]
    return {"tree": str(tree), "arm": arm, "ok": True, "returncode": p.returncode,
            "n_rows": len(rows), "strip_set": d["strip"],
            "test_hybrid_file": d["test_hybrid_file"],
            "digest": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                                default=float).encode()).hexdigest()[:16],
            "_rows": rows}


def compare(a_rows: List[Dict[str, Any]], b_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_field: Dict[str, int] = {}
    n = 0
    first = None
    for i, (x, y) in enumerate(zip(a_rows, b_rows)):
        if x == y:
            continue
        n += 1
        if first is None:
            first = {"row_index": i, "before": x, "after": y}
        for k in set(x) | set(y):
            if x.get(k) != y.get(k):
                per_field[k] = per_field.get(k, 0) + 1
    return {"n_rows": [len(a_rows), len(b_rows)],
            "row_counts_equal": len(a_rows) == len(b_rows),
            "n_differing_rows": n + abs(len(a_rows) - len(b_rows)),
            "differing_fields": per_field, "first_difference": first}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True, help="live2 dir of a clean archive of the base sha")
    ap.add_argument("--after", required=True, help="live2 dir of the tree under test")
    ap.add_argument("--out", required=True)
    ap.add_argument("--arm", action="append", default=None)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=300.0)
    a = ap.parse_args(argv)

    before, after = Path(a.before).resolve(), Path(a.after).resolve()
    arms = tuple(a.arm) if a.arm else DEFAULT_ARMS

    # ---- THE CONTROL, FIRST: does each tree agree with ITSELF on this instrument?
    c_arm = arms[0]
    ctl: Dict[str, Any] = {
        "_what": ("THE INSTRUMENT'S OWN DETERMINISM, measured before any comparison is read. Each "
                  "tree is run twice on one arm. The realtime cell instrument this replaced FAILED "
                  "this check, which is why it was replaced."),
        "arm": c_arm}
    for tag, tree in (("before", before), ("after", after)):
        r1 = collect(tree, c_arm, a)
        r2 = collect(tree, c_arm, a)
        same = (r1.get("ok") and r2.get("ok") and r1["digest"] == r2["digest"])
        ctl[tag] = {"digests": [r1.get("digest"), r2.get("digest")],
                    "n_rows": [r1.get("n_rows"), r2.get("n_rows")],
                    "ok": [r1.get("ok"), r2.get("ok")],
                    "stderr_tail": [r1.get("stderr_tail"), r2.get("stderr_tail")],
                    "SELF_CONSISTENT": bool(same),
                    "diff": (None if same or not (r1.get("ok") and r2.get("ok"))
                             else compare(r1["_rows"], r2["_rows"]))}
    ctl["DETERMINISTIC"] = bool(ctl["before"]["SELF_CONSISTENT"] and ctl["after"]["SELF_CONSISTENT"])
    ctl["VERDICT"] = ("PASS: both trees reproduce their own digest exactly, so this instrument can "
                      "carry a byte-identity claim and an equal digest below means equal decisions."
                      if ctl["DETERMINISTIC"] else
                      "FAIL: THE INSTRUMENT IS NOT DETERMINISTIC. A tree disagrees with itself, so "
                      "nothing below is evidence about the fix and no byte-identity claim can be "
                      "made from it.")
    print(json.dumps({"CONTROL": ctl["VERDICT"],
                      "before": ctl["before"]["digests"],
                      "after": ctl["after"]["digests"]}, indent=1), flush=True)

    per_arm: Dict[str, Any] = {}
    for arm in arms:
        rb = collect(before, arm, a)
        rf = collect(after, arm, a)
        if not (rb.get("ok") and rf.get("ok")):
            per_arm[arm] = {"why_in_the_set": ARM_WHY.get(arm, "named on the command line"),
                            "RAN": False,
                            "before": {k: v for k, v in rb.items() if k != "_rows"},
                            "after": {k: v for k, v in rf.items() if k != "_rows"},
                            "IDENTICAL": False}
            print(json.dumps({"arm": arm, "RAN": False,
                              "stderr": (rb.get("stderr_tail") or rf.get("stderr_tail") or "")[-300:]}),
                  flush=True)
            continue
        cmp_ = compare(rb["_rows"], rf["_rows"])
        ident = (rb["digest"] == rf["digest"] and cmp_["n_differing_rows"] == 0)
        per_arm[arm] = {
            "why_in_the_set": ARM_WHY.get(arm, "named on the command line"),
            "RAN": True,
            "n_rows": [rb["n_rows"], rf["n_rows"]],
            "digest_before": rb["digest"], "digest_after": rf["digest"],
            "strip_set": rb["strip_set"],
            "modules_from": {"before": rb["test_hybrid_file"], "after": rf["test_hybrid_file"]},
            "comparison": cmp_,
            "IDENTICAL": bool(ident)}
        print(json.dumps({"arm": arm, "IDENTICAL": bool(ident),
                          "rows": [rb["n_rows"], rf["n_rows"]],
                          "digests": [rb["digest"], rf["digest"]]}), flush=True)

    ran = [k for k, v in per_arm.items() if v.get("RAN")]
    moved = sorted(k for k in ran if not per_arm[k]["IDENTICAL"])
    notrun = sorted(k for k in per_arm if k not in ran)
    all_ok = bool(ran) and not moved and not notrun and ctl["DETERMINISTIC"]
    out = {
        "_what": ("D223 (2) 1x byte-identity proof on the project's own deterministic dry digest "
                  "(hybrid/test_hybrid.dry, realtime=False), per arm"),
        "_claim": ("reading the context limit from the server's configured max-model-len at run "
                   "start changes no decision at 1x, for any arm"),
        "_instrument": ("hybrid/test_hybrid.dry with realtime=False and the committed STRIP set, "
                        "every module taken from the tree under test. See the module docstring for "
                        "why the realtime cell instrument was rejected and what this one does not "
                        "reach (the procsplit hand-off)."),
        "sha_before": os.environ.get("D223_SHA_BEFORE"),
        "workload": WORKLOAD,
        "cell": {"seed": a.seed, "n_devices": a.n, "run_s": a.run_s},
        "control_instrument_determinism": ctl,
        "arms": per_arm,
        "ARMS_WHOSE_DECISIONS_MOVED": moved,
        "ARMS_THAT_DID_NOT_RUN": notrun,
        "ALL_IDENTICAL": all_ok,
        "VERDICT": ("PASS: every arm's decisions are byte-identical at 1x on a deterministic "
                    "instrument whose determinism was measured first."
                    if all_ok else
                    ("STOP: the instrument failed its own determinism control; nothing here is "
                     "readable." if not ctl["DETERMINISTIC"] else
                     "STOP AND ESCALATE: moved=%s notrun=%s. Per D223 (2) a decision moving at 1x "
                     "is a stopping condition: do not proceed to any 0.5x cell."
                     % (moved, notrun))),
    }
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"VERDICT": out["VERDICT"], "ALL_IDENTICAL": all_ok,
                      "moved": moved, "notrun": notrun}, indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
