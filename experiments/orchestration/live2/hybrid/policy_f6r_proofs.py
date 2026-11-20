"""Proofs required before hybrid-F6r joins the grid (D144 ruling 4).

hybrid-F6r = hybrid-F6 with C6 gated to non-single-shot recall, as D143 ruling C already stated the
design to be ("C6 is robot-only by design"). It is a NEW LABELLED ARM, not a change to hybrid-F6,
because the gate is NOT decision-preserving: measured on the three-type LH-REQ cell at 20 devices it
deletes one single-shot deviation. D108 / D121 byte-identity therefore cannot hold and D79 applies.

Three proofs, each answering a question the others do not:

  A. ROBOT-SIDE DECISIONS UNCHANGED. F6r against F6 on the same cells, with the setwise decision diff
     reported SEPARATELY for robot rows, single-shot rows and dashcam rows. The robot column is the
     claim; the single-shot column is the price, which the ruling asks to be reported rather than
     minimised; the dashcam column is reported because a deleted SS decision can propagate through
     C2's dashcam throttle and C1's ordering, so "unchanged on robots" is not by itself "unchanged
     everywhere" and must not be read that way.

  B. THE CHARACTERISTIC DECISION STILL OCCURS. A gate that silences C6 entirely would pass proof A
     perfectly, which is the port-side failure CLAUDE.md records: both required proofs passing while
     the arm made zero decisions of its own kind. So F6r must show c6_calls > 0, c6_scorer_error == 0,
     and every call landing on a period that holds non-SS recall.

  C. WHAT THE GATE BOUGHT. The wall time spent in the policy-core mirror (_c6_prepare) per cell, for
     F6 and F6r, with the period counts. This is the cost the gate exists to remove: 94 percent of
     C6's calls were on single-shot requests, and the SS-only periods paid p50 42.6 to 133.5 ms
     against the 100 ms decision period.

Everything here is a DRY run: no GPU, no server, stub bridge. These are decision-path proofs, not
timing or quality measurements of the live system, and nothing here may be read as a policy result.
The wall times in proof C are this box's dry-run cost of the mirror, not a live latency.
"""
import json
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "fleet"))
sys.path.insert(0, str(HERE.parent / "tests"))
sys.path.insert(0, str(HERE.parents[3] / "experiments/lib"))

import test_hybrid as TH   # noqa: E402

REPO = HERE.parents[3]
# The treatment arm is an argument because D144 ruling 4's proof is needed for BOTH robot-only
# variants: hybrid-F6r (mirror gated too, cheap) and hybrid-F6rm (mirror advanced every period,
# robot-exact). The baseline is hybrid-F6 in both cases.
TREAT = sys.argv[1] if len(sys.argv) > 1 else "hybrid-F6r-lhreq"
BASE = "hybrid-F6-lhreq"
OUT = REPO / ("results/orchestration/live2/hybrid/policy_%s_proofs.json"
              % TREAT.replace("hybrid-", "").replace("-lhreq", "").lower())

SEEDS = (0, 4)
SIZES = (16, 20, 32)
RUN_S = 1200.0
THREE = "40:40:20"
LH = dict(robot_question_set="lh_req", ss_question_set="ss2")


def _is_ss_row(r):
    """Single-shot rows name an assistive session; robot rows name a robot session. The note is the
    only per-row carrier of the device type in decision.jsonl, so it is what the split reads."""
    note = str(r.get("note") or "")
    return "session=asst" in note


def _is_robot_row(r):
    return "session=robo" in str(r.get("note") or "")


def _split(rows):
    robot = [r for r in rows if _is_robot_row(r)]
    ss = [r for r in rows if _is_ss_row(r)]
    dash = [r for r in rows if not _is_robot_row(r) and not _is_ss_row(r)]
    return robot, ss, dash


def _timed_prepare(arm):
    """Wrap the INSTANCE, not the class: make_arm resolves HybridArm through a differently named
    module instance, so a class-level monkeypatch silently does not take effect (it reported
    "NONE CAUGHT" while the counter still incremented)."""
    inner = arm._c6_prepare

    def wrapped(self, obs, _inner=inner):
        has_robot = any(getattr(q, "category", None) not in self._ss_types for q in (obs.recall or ()))
        t0 = time.perf_counter()
        try:
            return _inner(obs)
        finally:
            # Into stats, because TH.dry returns only arm.stats: a counter set on the arm itself
            # would be discarded with the arm when the temp dir closes.
            self.stats["t_prepare_ms"] = self.stats.get("t_prepare_ms", 0.0) + (
                time.perf_counter() - t0) * 1000.0
            self.stats["t_prepare_calls"] = self.stats.get("t_prepare_calls", 0) + 1
            if has_robot:
                self.stats["t_prepare_robot_calls"] = self.stats.get("t_prepare_robot_calls", 0) + 1

    arm._c6_prepare = types.MethodType(wrapped, arm)


def run():
    out = {"_note": __doc__.strip().splitlines()[0], "cells": []}
    for n in SIZES:
        for seed in SEEDS:
            cell = dict(n_devices=n, seed=seed, ratio=THREE, run_s=RUN_S, **LH)
            held = {}
            for arm in (BASE, TREAT):
                rows, st = TH.dry(arm, seed, n, run_s=RUN_S, ratio=THREE, patch=_timed_prepare, **LH)
                held[arm] = rows
                cell[arm] = dict(decisions=len(rows), stats=dict(st or {}))
            f6, f6r = held[BASE], held[TREAT]
            for label, pick in (("robot", _is_robot_row),
                               ("single_shot", _is_ss_row),
                               ("dashcam", lambda r: not _is_robot_row(r) and not _is_ss_row(r))):
                a = [r for r in f6 if pick(r)]
                b = [r for r in f6r if pick(r)]
                cell[f"moved_{label}"] = TH._differing_setwise(a, b)
                cell[f"rows_{label}"] = [len(a), len(b)]
            cell["moved_all"] = TH._differing_setwise(f6, f6r)
            print(f"  n={n:<3} seed={seed}  moved robot {cell['moved_robot']:<4} "
                  f"single-shot {cell['moved_single_shot']:<4} dashcam {cell['moved_dashcam']:<4} "
                  f"all {cell['moved_all']}", flush=True)
            out["cells"].append(cell)
    return out


if __name__ == "__main__":
    res = run()
    res["_treatment"], res["_baseline"] = TREAT, BASE
    import _provenance   # noqa: E402
    try:
        res["_provenance"] = _provenance.stamp(script="policy_f6r_proofs.py", model="none-dry",
                                               device="nvidia_rtx_a6000", n=len(res["cells"]))
    except Exception as e:                                                   # noqa: BLE001
        res["_provenance"] = {"git_commit": "unstamped", "script": "policy_f6r_proofs.py",
                              "note": f"stamp failed: {e!r}"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=float))
    print("wrote", OUT)
