#!/usr/bin/env python3
"""D179 (4) dry-cell proofs for the wire-time release re-check. Session B.

ONE DRY CELL PER PROCESS, in a subprocess. This is not fussiness: a second dry run inside one
process does not reproduce the first (covex-v6-state gave 15,871 rows then 16,109 in one process,
with `state_decisions` moving 44,300 to 45,337), and the planner wall-clock limit, PYTHONHASHSEED
and the registration context are all ruled out. The cause is an OPEN defect. So every digest
claim here is made across processes, one cell each, and `cf_instrument`'s wall-clock cutoff is
patched off, because a decision digest for a time-budgeted planner otherwise measures the load on
the box rather than the arm (d174_proofs._NoWallClockCutoff records that in full).

WHAT IS PROVED, on the POSTED workload (ratio 40:40:20, robot_question_set lh_req, ss_question_set
ss2, dashcam_format epg, robot_upload per-frame, robot_reask_mean_s 30.0, 16 devices, 1200 s):

  A  NEGATIVE CONTROL / REUSABILITY. With the switch OFF the committed arm's decision digest is
     byte-identical to the same arm with the switch absent, so no committed cell is invalidated.
     This is the D179 (4) stop condition "any committed arm's dry decisions change with the
     switch off".
  B  THE SWITCH REACHES A DECISION (Step 2b). With it ON, the number of decision rows that
     differ, and the first one. An identical log is an ABSENT LINK, never a negative.
  C  THE D179 STOP CONDITION on the alert path: the re-check must not fire on more than 50
     percent of alert requests. Denominator stated: released alerts plus skipped alerts, i.e.
     every alert request the coordinator reached release for.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEST = REPO / "results/orchestration/live2/frozen_test/d179_release_recheck_proofs.json"

# THE ARM MUST BE D162-PRICED, and the first run of this driver is why. On `covex-v6-base`, which
# is NOT D162-priced, the re-check fired on 12,166 of 12,168 alert requests (99.98 percent) and
# tripped the D179 STOP condition. The cause is a REGISTER fault in its input, not in the rule:
# `_uncached_in_flight` is incremented unconditionally at four release sites and decremented only
# inside `if self._d162_pricing` (coordinator.py:1508), so on a non-priced arm it is the
# cumulative sum of every uncached token the run has released rather than the queue ahead of this
# request. The coordinator now REFUSES the combination, so this driver must name a priced arm; the
# 99.98 percent row is kept in the result file as the record of the stop.
ARM = "covex-v6-rules-wo"                   # D162-priced (arms_v6state.py:447)
SEEDS = (4,)                                # dev seeds only; NEVER 1 to 3, never HOLDOUT
CELL = dict(n=16, run_s=1200.0, ratio="40:40:20", robot_question_set="lh_req",
            ss_question_set="ss2", dashcam_format="epg", robot_upload="per-frame",
            robot_reask_mean_s=30.0)
# THE CONTROL IS AUDITED, NOT ONLY THE TREATMENT (CLAUDE.md check 7). This arm's digest on THIS
# cell is already committed, so the switch-OFF side is checked against a committed value instead
# of being compared only against the switch-ON side. An impossible success here is as diagnostic
# as an impossible failure: if OFF does not reproduce it, the harness is broken and the ON/OFF
# comparison means nothing.
# keyed (arm, seed); covex-v6-base's row is the one the 99.98 percent stop was measured against
COMMITTED_OFF_BY_ARM = {
    ("covex-v6-base", 4): {"digest": "af8befb9420ad86a", "rows": 12085,
                           "source": ("results/orchestration/live2/frozen_test/"
                                      "c5attr_digest_proofs.json :: "
                                      "P1_committed_arms_unchanged")}}
COMMITTED_OFF = {s: v for (a, s), v in COMMITTED_OFF_BY_ARM.items() if a == ARM}

_CHILD = r'''
import hashlib, json, sys
HERE = %(here)r
for p in (HERE, HERE+"/fleet", HERE+"/v5", HERE+"/hybrid", HERE+"/../baselines"):
    sys.path.insert(0, p)
import cf_instrument as CI
for _n in dir(CI):                                    # the proofs-only wall-clock cutoff patch
    _o = getattr(CI, _n)
    if isinstance(_o, type) and hasattr(_o, "over_budget"):
        _o.over_budget = lambda self, budget_ms=None: False
import arms as A, arms_v6state as VS, arms_v6fair as VF, arm_names_v6 as N
VS.register(); VF.register(); N.register()
arm_name, mode = %(arm)r, %(mode)r
if mode == "on":
    _base = A.ARMS[arm_name]
    def _mk(_b=_base, **kw):
        a = _b(**kw)
        a.live2_release_recheck = True                # INSTANCE attribute, never the class
        return a
    A.ARMS[arm_name] = _mk
import test_hybrid as TH
CELL = %(cell)r
kw = {k: v for k, v in CELL.items()
      if k in ("dashcam_format", "robot_upload", "robot_reask_mean_s")}
rows, st = TH.dry(arm_name, %(seed)d, CELL["n"], run_s=CELL["run_s"], ratio=CELL["ratio"],
                  robot_question_set=CELL["robot_question_set"],
                  ss_question_set=CELL["ss_question_set"], **kw)
rows = list(rows or [])
rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
d = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                              default=float).encode()).hexdigest()[:16]
kinds = {}
for r in rr:
    kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
slim = [{"t": r.get("t"), "kind": r.get("kind"),
         "opportunity_ids": r.get("opportunity_ids")} for r in rr]
print("@@" + json.dumps({"arm": arm_name, "mode": mode, "seed": %(seed)d, "digest": d,
                         "rows": len(rr), "kinds": kinds, "slim": slim}))
'''


def _run(mode: str, seed: int) -> Dict[str, Any]:
    src = _CHILD % {"here": str(HERE), "arm": ARM, "mode": mode, "cell": CELL, "seed": seed}
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=10800)
    line = [l for l in (p.stdout or "").splitlines() if l.startswith("@@")]
    if not line:
        return {"error": ((p.stderr or "").strip().splitlines() or ["no output"])[-1][:400]}
    return json.loads(line[-1][2:])


def _first_difference(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return {"index": i, "off": x, "on": y}
    if len(a) != len(b):
        i = min(len(a), len(b))
        return {"index": i, "off": (a[i] if i < len(a) else None),
                "on": (b[i] if i < len(b) else None)}
    return None


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "D179 (4) release re-check: negative control, Step 2b, and the 50 percent "
                 "alert stop condition",
        "_protocol": ("one dry cell per process in a subprocess; cf_instrument's wall-clock "
                      "cutoff patched off for digest comparability"),
        "arm": ARM, "cell": CELL, "cases": []}
    ok = True
    for seed in SEEDS:
        off = _run("off", seed)
        on = _run("on", seed)
        if "error" in off or "error" in on:
            out["cases"].append({"seed": seed, "off": off, "on": on, "verdict": "ERROR"})
            ok = False
            continue
        off_slim, on_slim = off.pop("slim"), on.pop("slim")
        n_diff = sum(1 for x, y in zip(off_slim, on_slim) if x != y) \
            + abs(len(off_slim) - len(on_slim))
        skipped = on["kinds"].get("release_infeasible", 0)
        released_alerts = on["kinds"].get("release_monitor", 0)
        denom = skipped + released_alerts
        frac = (skipped / denom) if denom else None
        row = {"seed": seed, "off": off, "on": on,
               # A: the negative control. The switch-OFF digest is the number a reader compares
               # against this arm's committed digest for the same cell; it is reported, not
               # self-certified, because this process has no committed digest of its own to
               # compare against.
               "A_off_digest": off["digest"], "A_off_rows": off["rows"],
               "A_committed": COMMITTED_OFF.get(seed),
               "A_off_matches_committed": bool(
                   COMMITTED_OFF.get(seed) is not None
                   and off["digest"] == COMMITTED_OFF[seed]["digest"]
                   and off["rows"] == COMMITTED_OFF[seed]["rows"]),
               # B: Step 2b. The switch must MOVE decisions, or the comparison was not run.
               "B_decisions_differing": n_diff,
               "B_first_difference": _first_difference(off_slim, on_slim),
               "B_switch_reaches_a_decision": bool(n_diff > 0),
               # C: the D179 stop condition on the alert path.
               "C_alert_skips": skipped, "C_alert_released": released_alerts,
               "C_alert_denominator": denom,
               "C_alert_skip_fraction": (round(frac, 6) if frac is not None else None),
               "C_under_50_percent": (frac is not None and frac <= 0.50)}
        out["cases"].append(row)
        print("seed %d  off=%s/%s (committed %s) on=%s/%s  differing=%d  "
              "alert skips %s/%s = %s"
              % (seed, off["digest"], off["rows"],
                 "MATCH" if row["A_off_matches_committed"] else "MISMATCH",
                 on["digest"], on["rows"], n_diff, skipped, denom,
                 row["C_alert_skip_fraction"]), flush=True)
        if not row["A_off_matches_committed"]:
            ok = False
        if not row["B_switch_reaches_a_decision"] or not row["C_under_50_percent"]:
            ok = False
    out["verdict"] = ("PASS" if ok else "STOP: see A_off_matches_committed, "
                                       "B_switch_reaches_a_decision and C_under_50_percent")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(out, indent=1) + "\n")
    print(out["verdict"])
    print("wrote", DEST)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
