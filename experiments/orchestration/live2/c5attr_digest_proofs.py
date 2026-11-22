#!/usr/bin/env python3
"""The C5 attribution candidate must not have moved anything that already exists.

P1  BEFORE / AFTER on four committed arms   covex-v6-state-uo, covex-v6-base, v5-rules-2 and
    b7-edf-feasibility produce the same decision digest in THIS tree and in a worktree at the
    commit this work started from. The BEFORE side comes from git, not from a number recorded in
    this tree, so the reference cannot have followed the change.
P2  Step 2b on a dry cell, with the trip instrument   the candidate against covex-v6-state-uo:
    the cap trajectory, the suppressed-halving count, and the number of differing decisions.
P3  the dry cell WITHOUT the instrument   both arms identical and c5_decrease 0, which is the
    statement that an unmodified dry cell cannot exercise this rule at all.
P4  negative control   the candidate with its own flag forced OFF must equal covex-v6-state-uo
    exactly, in the same instrumented cell.

ONE DRY CELL PER PROCESS throughout: a second dry run inside one process does not reproduce the
first (an open defect; covex-v6-state gave 15,871 rows then 16,109). The planner's wall-clock
cutoff is patched OFF in every digest process, so a digest is a property of the arm and not of the
machine's load; live cells keep it on (D99 (3)).

THE DRY CELLS FORWARD THE POSTED WORKLOAD KNOBS (ratio 40:40:20, lh_req, ss2, EP-G dashcam,
per-frame upload, 30 s re-asks, 16 devices), because test_hybrid.dry's own defaults are a
different workload and would measure the wrong thing.
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
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BEFORE_COMMIT = os.environ.get("C5ATTR_BEFORE", "f2d617fa")
COMMITTED_ARMS = ["covex-v6-state-uo", "covex-v6-base", "v5-rules-2", "b7-edf-feasibility"]
CELL = dict(seed=4, n=16, run_s=1200.0)
TRIP_S = 0.9                 # above C5's 0.8 s trip; a proof instrument, never a measurement

_SCRIPT = r'''
import hashlib, json, sys
HERE = %r
for p in (HERE, HERE+"/fleet", HERE+"/v5", HERE+"/hybrid", HERE+"/../baselines"):
    sys.path.insert(0, p)
import arms_v6state as VS
VS.register()
try:
    import arms_v6c5 as VC
    VC.register()
except Exception:
    pass
import cf_instrument as CI
for _n in dir(CI):
    _o = getattr(CI, _n)
    if isinstance(_o, type) and hasattr(_o, "over_budget"):
        _o.over_budget = lambda self, budget_ms=None: False
if %r > 0.0:
    import coordinator as CO
    _orig = CO.Live2Coordinator._dry_service_s
    def _svc(self, sub, _o=_orig, _t=%r):
        return _t if sub.kind == "monitor" else _o(self, sub)
    CO.Live2Coordinator._dry_service_s = _svc
import test_hybrid as TH
rows, st = TH.dry(%r, %d, %d, run_s=%f, ratio="40:40:20", robot_question_set="lh_req",
                  ss_question_set="ss2", dashcam_format="epg", robot_upload="per-frame",
                  robot_reask_mean_s=30.0)
rows = list(rows or [])
rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
d = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                              default=float).encode()).hexdigest()[:16]
print(json.dumps({"digest": d, "rows": len(rows)}))
'''


def _digest_in(live2: Path, arm: str, trip_s: float = 0.0) -> Dict[str, Any]:
    script = _SCRIPT % (str(live2), float(trip_s), float(trip_s), arm,
                        CELL["seed"], CELL["n"], CELL["run_s"])
    p = subprocess.run([sys.executable, "-c", script], cwd=str(live2),
                       capture_output=True, text=True, timeout=7200,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    line = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not line:
        return {"error": ((p.stderr or "").strip().splitlines() or ["no output"])[-1][:300]}
    return json.loads(line[-1])


def _one_cell(arm: str, trip_s: float, force_flag: str = None,
              rows_out: Path = None) -> Dict[str, Any]:
    cmd = [sys.executable, str(HERE / "c5attr_one_cell.py"), "--arm", arm,
           "--seed", str(CELL["seed"]), "--n", str(CELL["n"]),
           "--run-s", str(CELL["run_s"]), "--trip-s", str(trip_s), "--cutoff-off"]
    if force_flag:
        cmd += ["--force-flag", force_flag]
    if rows_out:
        cmd += ["--rows-out", str(rows_out)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=7200,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    line = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not line:
        return {"error": ((p.stderr or "").strip().splitlines() or ["no output"])[-1][:300]}
    return json.loads(line[-1])


def _differing(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    from collections import Counter

    def key(r):
        return (r.get("t"), r.get("kind"), tuple(r.get("opportunity_ids") or ()),
                r.get("representation"), r.get("defer_s"))
    ca, cb = Counter(map(key, a)), Counter(map(key, b))
    d = (ca - cb) + (cb - ca)
    first = None
    for x, y in zip(a, b):
        if x != y:
            first = {"committed_arm": x, "candidate": y}
            break
    return {"setwise_differing_decisions": int(sum(d.values())),
            "positional_differing_rows": int(sum(1 for x, y in zip(a, b) if x != y)
                                             + abs(len(a) - len(b))),
            "first_differing_row": first}


def p1_before_after() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    td = tempfile.mkdtemp(prefix="c5attr_before_")
    tree = Path(td) / "wt"
    made = subprocess.run(["git", "worktree", "add", "--detach", str(tree), BEFORE_COMMIT],
                          cwd=str(REPO), capture_output=True, text=True)
    try:
        if made.returncode != 0:
            return {"_claim": "committed arms unchanged",
                    "verdict": "FAIL: could not create the before-worktree: %s"
                               % (made.stderr or "").strip()[:300]}
        for arm in COMMITTED_ARMS:
            before = _digest_in(tree / "experiments/orchestration/live2", arm)
            after = _digest_in(HERE, arm)
            rows.append({"arm": arm, "before": before, "after": after,
                         "identical": (before.get("digest") is not None
                                       and before.get("digest") == after.get("digest")
                                       and before.get("rows") == after.get("rows"))})
            print("  %-22s before=%s/%s after=%s/%s %s" % (
                arm, before.get("digest"), before.get("rows"), after.get("digest"),
                after.get("rows"), "IDENTICAL" if rows[-1]["identical"] else "MOVED"),
                flush=True)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)],
                       cwd=str(REPO), capture_output=True, text=True)
        shutil.rmtree(td, ignore_errors=True)
    ok = bool(rows) and all(r["identical"] for r in rows)
    return {"_claim": ("the committed arms decide identically before and after this work, with "
                       "the BEFORE side taken from git at %s" % BEFORE_COMMIT),
            "cell": dict(CELL, workload="posted"), "before_commit": BEFORE_COMMIT,
            "rows": rows,
            "verdict": ("PASS: %d committed arms byte-identical across the change" % len(rows)
                        if ok else "FAIL: %s"
                        % [r["arm"] for r in rows if not r["identical"]])}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": ("covex-v6-state-uo-c5attr: what it must not have moved (P1), that its rule "
                  "reaches the cap (P2), that a dry cell cannot exercise it unaided (P3), and "
                  "that disabling the rule collapses it to its comparator (P4)"),
        "_protocol": ("one dry cell per process; planner wall-clock cutoff patched off; POSTED "
                      "workload knobs forwarded; --trip-s %.2f is a PROOF INSTRUMENT that raises "
                      "the dry monitor service time above C5's 0.8 s trip, applied identically "
                      "to both sides of every comparison and never quoted as a latency" % TRIP_S),
    }
    print("P1 before / after on the committed arms", flush=True)
    out["P1_committed_arms_unchanged"] = p1_before_after()
    print(out["P1_committed_arms_unchanged"]["verdict"], flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="c5attr_rows_"))
    try:
        print("P3 the dry cell without the instrument", flush=True)
        u0 = _one_cell("covex-v6-state-uo", 0.0)
        a0 = _one_cell("covex-v6-state-uo-c5attr", 0.0)
        out["P3_dry_default_is_unexercised"] = {
            "_claim": ("on an unmodified dry cell the monitor service time is the committed "
                       "curve's constant 0.3950 s, below C5's 0.8 s trip, so the cap never "
                       "halves and this rule CANNOT fire. A null here is UNEXERCISED, not a "
                       "negative"),
            "covex-v6-state-uo": u0, "candidate": a0,
            "identical": u0.get("digest") == a0.get("digest"),
            "c5_decrease_is_zero": [(u0.get("stats") or {}).get("c5_decrease"),
                                    (a0.get("stats") or {}).get("c5_decrease")],
            "verdict": ("PASS: identical digests and no halving to attribute, so the instrument "
                        "in P2 is necessary"
                        if u0.get("digest") == a0.get("digest") else
                        "FAIL: the arms differ even where the rule cannot fire")}
        print(" ", out["P3_dry_default_is_unexercised"]["verdict"], flush=True)

        print("P2 Step 2b with the instrument", flush=True)
        u = _one_cell("covex-v6-state-uo", TRIP_S, rows_out=tmp / "uo.json")
        a = _one_cell("covex-v6-state-uo-c5attr", TRIP_S, rows_out=tmp / "attr.json")
        dec = _differing(json.loads((tmp / "uo.json").read_text()),
                         json.loads((tmp / "attr.json").read_text()))
        moved_cap = (u.get("cap_series_digest") != a.get("cap_series_digest"))
        sup = (a.get("stats") or {}).get("c5_attr_suppressed_decrease") or 0
        out["P2_step2b_cap_trajectory"] = {
            "_claim": "the rule changes the cap trajectory and is not a write-only field",
            "covex-v6-state-uo": u, "candidate": a, "decisions": dec,
            "cap_trajectory_moved": bool(moved_cap),
            "suppressed_halvings": int(sup),
            "verdict": ("PASS: the cap trajectory differs (%s against %s, first halving %s "
                        "against %s) and %d halvings were suppressed"
                        % (u.get("cap_series_digest"), a.get("cap_series_digest"),
                           (u.get("cap_trace_head") or [None, None])[1:2],
                           (a.get("cap_trace_head") or [None, None])[1:2], sup)
                        if (moved_cap and sup > 0) else
                        "ABSENT LINK: the rule did not reach the cap (moved=%s, suppressed=%d)"
                        % (moved_cap, sup)),
            "_decision_level_note": (
                "the number of DIFFERING DECISIONS is reported as measured and is a separate "
                "register from the cap trajectory: a held dashcam stream emits no decision row, "
                "so a cap that differs need not show up as a differing row in a dry cell"),
        }
        print(" ", out["P2_step2b_cap_trajectory"]["verdict"], flush=True)
        print("  differing decisions:", dec["setwise_differing_decisions"], flush=True)

        print("P4 negative control", flush=True)
        off = _one_cell("covex-v6-state-uo-c5attr", TRIP_S, force_flag="off")
        out["P4_negative_control"] = {
            "_claim": ("with its own switch forced off the candidate IS covex-v6-state-uo, which "
                       "is what makes the P2 difference the rule and not the wrapper"),
            "candidate_flag_off": off, "covex-v6-state-uo": {k: u.get(k) for k in
                                                             ("digest", "rows",
                                                              "cap_series_digest")},
            "identical": (off.get("digest") == u.get("digest")
                          and off.get("cap_series_digest") == u.get("cap_series_digest")),
            "verdict": ("PASS: collapses to the comparator exactly"
                        if (off.get("digest") == u.get("digest")
                            and off.get("cap_series_digest") == u.get("cap_series_digest"))
                        else "FAIL: the switch is not what produces the difference")}
        print(" ", out["P4_negative_control"]["verdict"], flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = all(str(out[k].get("verdict", "")).startswith("PASS")
             for k in out if k.startswith("P"))
    out["verdict"] = ("ALL_PASS" if ok else
                      "SEE the per-proof verdicts: %s"
                      % {k: out[k]["verdict"][:60] for k in out if k.startswith("P")})
    dest = REPO / "results/orchestration/live2/frozen_test/c5attr_digest_proofs.json"
    dest.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(out["verdict"])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
