#!/usr/bin/env python3
"""D214 FIGURE INSTRUMENTATION: THE BYTE-IDENTITY PROOF. Logging only, no decision moved.

THE CLAIM BEING PROVED. The D214 items 1 and 3 instrumentation (`f3_latency_stamps.py`,
`network_header.py` and the post-run block in `run_live2_real.py`) changes NO decision, for ANY
arm, ever. The user's constraint is "logging only; must be byte-identical in decisions for every
arm", and this file exists because that has to be PROVED and not asserted.

THREE PROOFS, IN INCREASING STRENGTH, AND THE WEAKEST IS NOT SKIPPED BECAUSE THE STRONGEST EXISTS.

  (a) STRUCTURAL, CONSTRUCTED. Every line of the new instrumentation runs AFTER `em.run()` has
      returned: the emulator's loop has ended, the coordinator is closed, every log file is
      written, and there is no decision left to make. The ONLY statement added inside the run is
      `_EMU.append(em)` in `run_live2_real._emulator`, a list append of a reference to an object
      that already exists; it mutates no state any decision reads. This is reported as CONSTRUCTED,
      because an argument from reading code is not a measurement. It is also not a switch that
      happens to be off by default, which the brief asks us not to ship.

  (b) IMPORT-CLOSURE, OBSERVED. A decision path that never imports a module cannot be changed by
      it. This proof runs one dry cell and then reports whether `network_header`,
      `f3_latency_stamps`, `f14_one_cell` or `run_live2_real` appear in `sys.modules` afterwards.
      An absence claim here is made with the exact census printed beside it, never from a
      truncated view.

  (c) PAIRED CELLS, OBSERVED, AND THIS IS THE ONE THE BRIEF ASKS FOR. The same cell is run on a
      clean BEFORE tree (a `git archive` of the origin sha, untouched) and on the AFTER tree, and
      the two `decision.jsonl` files are compared. Decisions are compared with the TIMING fields
      removed (`arm`, `decision_latency_ms`, `decision_id`: exactly `test_hybrid.STRIP`), because
      a wall-clock latency is not a decision and differs between any two runs of the same cell.
      The raw byte comparison is reported beside it so a reader can see which register each
      statement is in.

  (c) HAS ITS OWN CONTROL, AND WITHOUT IT THE COMPARISON IS UNREADABLE. `run_live2_real.py` runs
      the emulator in REAL TIME and ticks the coordinator on the wall clock while it waits, so two
      runs of the same cell on the same tree are not guaranteed to produce the same decision log.
      SO EACH TREE IS RUN TWICE. A/A and B/B establish the harness's own reproducibility floor
      FIRST; only if both are identical does A-vs-B mean anything, and if they are not, this file
      says so and refuses to report the A-vs-B result as a byte-identity proof. A comparison whose
      control is never audited is the blindness CLAUDE.md check 7 is about, and here the control is
      the harness's own repeatability.

ALONE, AND loadavg AS A MAGNITUDE (D216 (1)). Every cell waits for a window with no other live2
process, re-checks that none started during it, and records `/proc/loadavg` at the start and the
end as the number. A digest or a row count measured under contention and one measured alone are
different measurements.

THE CELL IS DRY-BUT-REAL-PATH. There is no server on flash, so the cell runs `run_live2_real.py`
with no `--server`: the real `Live2Coordinator`, the real `EmulatorBridge`, the real emulator and
the real post-run block, with `dry_run=True` inside the coordinator. That is the path the
instrumentation sits on. It is NOT a measurement of anything: `is_measurement` is false in its own
header and no latency from it is reportable.

Usage:
    python d214_byte_identity_proof.py --before DIR --after DIR --out FILE [--arm ...] [--n 8]
where DIR is an `experiments/orchestration/live2` directory in each tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
MARKER_ENV = "D214_PROOF_MARKER"
STRIP = ("arm", "decision_latency_ms", "decision_id")   # test_hybrid.STRIP, the committed set

LIVE2_HINTS = ("cf_pd_one_cell.py", "cfr3_one_cell.py", "c5attr_one_cell.py", "rr_one_cell.py",
               "d210_kv025_one_cell.py", "d216_final_kv025_one_cell.py", "f14_one_cell.py",
               "d213_digest_driver.py", "d209_digest_driver.py", "d216_final_kv025_driver.py",
               "d210_kv025_driver.py", "f14_decision_latency_driver.py", "run_live2_real.py",
               "run_live2_cell.py", "test_hybrid.py", "d214_byte_identity_proof.py")


def _ancestors(pid: int) -> set:
    out, cur = {pid}, pid
    for _ in range(64):
        try:
            with open("/proc/%d/stat" % cur, "rb") as fh:
                cur = int(fh.read().rsplit(b")", 1)[1].split()[1])
        except Exception:                                                  # noqa: BLE001
            break
        if not cur or cur in out:
            break
        out.add(cur)
    return out


def _marked(pid: int, marker: str) -> bool:
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            return ("%s=%s" % (MARKER_ENV, marker)).encode() in fh.read()
    except Exception:                                                      # noqa: BLE001
        return False


def foreign(marker: str, mine: set) -> List[Dict[str, Any]]:
    out = []
    for ent in os.listdir("/proc"):
        if not ent.isdigit():
            continue
        pid = int(ent)
        if pid in mine:
            continue
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                parts = [x.decode("utf-8", "replace") for x in fh.read().split(b"\0") if x]
        except Exception:                                                  # noqa: BLE001
            continue
        if not parts or not [t for t in parts if os.path.basename(t) in LIVE2_HINTS]:
            continue
        if _marked(pid, marker):
            continue
        cwd = None
        try:
            cwd = os.readlink("/proc/%d/cwd" % pid)
        except Exception:                                                  # noqa: BLE001
            pass
        out.append({"pid": pid, "cwd": cwd, "cmd": " ".join(parts)[:400]})
    return out


def wait_alone(marker: str, mine: set, wait_s: float) -> Dict[str, Any]:
    t0 = time.time()
    while True:
        f = foreign(marker, mine)
        if not f:
            return {"alone_at_start": True, "waited_s": round(time.time() - t0, 1)}
        if time.time() - t0 >= wait_s:
            return {"alone_at_start": False, "waited_s": round(time.time() - t0, 1),
                    "foreign_at_give_up": f}
        time.sleep(20.0)


def _rows(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def _digest(rows: List[Dict[str, Any]]) -> str:
    rr = [{k: v for k, v in r.items() if k not in STRIP} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _raw_sha(p: Path) -> Optional[str]:
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def run_one(tree: Path, tag: str, work: Path, a: Any, wait_s: float) -> Dict[str, Any]:
    rdir = work / tag
    rdir.mkdir(parents=True, exist_ok=True)
    marker = uuid.uuid4().hex
    mine = _ancestors(os.getpid())
    gate = wait_alone(marker, mine, wait_s)
    cmd = [sys.executable, str(tree / "run_live2_real.py"),
           "--arm", a.arm, "--seed", str(a.seed), "--n-devices", str(a.n),
           "--run-s", str(a.run_s), "--mode", "A", "--out", str(rdir),
           "--work", str(work / (tag + "_work")), "--server-kind", "none",
           # THE POSTED WORKLOAD KNOBS, all of them, because a cell on the defaults is a cell of a
           # different workload and the proof is meant to sit on the path the real cells take.
           "--ratio", "40:40:20", "--robot-question-set", "lh_req", "--ss-question-set", "ss2",
           "--dashcam-format", "epg", "--robot-upload", "per-frame",
           "--robot-reask-mean-s", "30.0", "--no-score",
           "--label", "D214 byte-identity proof cell (NOT a measurement)"]
    env = dict(os.environ)
    env[MARKER_ENV] = marker
    l0 = os.getloadavg()
    t0 = time.time()
    log = work / (tag + ".log")
    with open(log, "w") as fh:
        rc = subprocess.call(cmd, cwd=str(tree), stdout=fh, stderr=subprocess.STDOUT, env=env)
    l1 = os.getloadavg()
    after = foreign(marker, mine)
    rows = _rows(rdir / "decision.jsonl")
    rec = {
        "tag": tag, "tree": str(tree), "returncode": rc,
        "wall_s": round(time.time() - t0, 1),
        "loadavg_at_start": [round(x, 2) for x in l0],
        "loadavg_at_end": [round(x, 2) for x in l1],
        "alone": bool(gate.get("alone_at_start") and not after),
        "waited_for_alone_s": gate.get("waited_s"),
        "foreign_at_start": gate.get("foreign_at_give_up") or [],
        "foreign_at_end": after,
        "n_decision_rows": len(rows),
        "decision_digest_timing_stripped": _digest(rows) if rows else None,
        "decision_jsonl_raw_sha16": _raw_sha(rdir / "decision.jsonl"),
        "request_jsonl_raw_sha16": _raw_sha(rdir / "request.jsonl"),
        "log_tail": log.read_text()[-1500:] if log.exists() else None,
        "run_dir": str(rdir),
        "cmd": " ".join(cmd),
    }
    rm = rdir / "run_meta.json"
    if rm.exists():
        m = json.loads(rm.read_text())
        rec["fairness_digest"] = m.get("fairness_digest")
        rec["digests_equal"] = m.get("digests_equal")
        rec["network_header_present"] = bool(m.get("network"))
        rec["network_link_model_applied"] = (m.get("network") or {}).get("link_model_applied")
        rec["figure_instrumentation"] = m.get("figure_instrumentation")
    return rec


def import_closure_census(tree: Path, work: Path) -> Dict[str, Any]:
    """OBSERVED: does the DRY decision path import any of the new modules? Census printed."""
    script = work / "_closure.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "H = Path(%r)\n"
        "for p in (H, H/'fleet', H/'v5', H/'hybrid', H.parent/'baselines'):\n"
        "    sys.path.insert(0, str(p))\n"
        "import arms as A, arms_v6state as VS, arms_v6c5 as VC, arms_v6shares as VSH, "
        "arms_v6cf as VCF\n"
        "VS.register(); VC.register(); VSH.register(); VCF.register()\n"
        "import test_hybrid as TH\n"
        "rows, st = TH.dry('covex-v6-base', 4, 4, run_s=30.0, ratio='40:40:20',\n"
        "                  robot_question_set='lh_req', ss_question_set='ss2',\n"
        "                  dashcam_format='epg', robot_upload='per-frame',\n"
        "                  robot_reask_mean_s=30.0)\n"
        "watch = ('network_header', 'f3_latency_stamps', 'f14_one_cell',\n"
        "         'f14_decision_latency_driver', 'run_live2_real', 'd214_byte_identity_proof')\n"
        "print(json.dumps({'n_rows': len(rows),\n"
        "                  'present': {w: (w in sys.modules) for w in watch},\n"
        "                  'n_modules': len(sys.modules)}))\n" % str(tree))
    p = subprocess.run([sys.executable, "-I", str(script)], cwd=str(tree),
                       capture_output=True, text=True)
    out: Dict[str, Any] = {"returncode": p.returncode, "stderr_tail": p.stderr[-1500:]}
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            out.update(json.loads(line))
            break
        except Exception:                                                  # noqa: BLE001
            continue
    out["_what"] = ("OBSERVED. One dry cell on the AFTER tree, then the census of sys.modules. A "
                    "module absent from the dry decision path cannot change a dry decision. The "
                    "exact census is in `present`; this is not an absence claimed from a "
                    "truncated grep.")
    return out


def first_difference(a_rows: List[Dict[str, Any]], b_rows: List[Dict[str, Any]]) -> Any:
    for i, (x, y) in enumerate(zip(a_rows, b_rows)):
        xs = {k: v for k, v in x.items() if k not in STRIP}
        ys = {k: v for k, v in y.items() if k not in STRIP}
        if xs != ys:
            return {"index": i, "before": xs, "after": ys}
    if len(a_rows) != len(b_rows):
        return {"index": min(len(a_rows), len(b_rows)),
                "note": "logs differ in LENGTH: %d before, %d after" % (len(a_rows), len(b_rows))}
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True, help="live2 dir of a clean archive of the base sha")
    ap.add_argument("--after", required=True, help="live2 dir of the tree with the instrumentation")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--arm", default="covex-v6-base")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--run-s", type=float, default=120.0)
    ap.add_argument("--wait-s", type=float, default=14400.0)
    a = ap.parse_args(argv)
    before, after, work = Path(a.before), Path(a.after), Path(a.work)
    work.mkdir(parents=True, exist_ok=True)

    cells: List[Tuple[str, Path]] = [("A1_before", before), ("A2_before", before),
                                     ("B1_after", after), ("B2_after", after)]
    recs: Dict[str, Dict[str, Any]] = {}
    for tag, tree in cells:
        recs[tag] = run_one(tree, tag, work, a, a.wait_s)
        print(json.dumps({k: recs[tag].get(k) for k in
                          ("tag", "returncode", "alone", "n_decision_rows",
                           "decision_digest_timing_stripped", "loadavg_at_start",
                           "loadavg_at_end")}), flush=True)
        Path(a.out).write_text(json.dumps({"partial": True, "cells": recs}, indent=1,
                                          default=float) + "\n")

    d = {t: recs[t].get("decision_digest_timing_stripped") for t in recs}
    aa = bool(d["A1_before"] is not None and d["A1_before"] == d["A2_before"])
    bb = bool(d["B1_after"] is not None and d["B1_after"] == d["B2_after"])
    ab = bool(d["A1_before"] is not None and d["A1_before"] == d["B1_after"])
    all_alone = all(bool(recs[t].get("alone")) for t in recs)

    if not (aa and bb):
        verdict = ("INCONCLUSIVE -- THE CONTROL FAILED, NOT THE TREATMENT. Two runs of the same "
                   "cell on the SAME tree did not reproduce each other (A/A %s, B/B %s), so the "
                   "harness's own repeatability on this real-time path is below the resolution the "
                   "A-vs-B comparison needs. The A-vs-B result below is NOT a byte-identity proof "
                   "and must not be read as one; proofs (a) and (b) stand on their own."
                   % (aa, bb))
    elif ab:
        verdict = ("PASS. The control reproduced on both trees (A/A and B/B identical) and BEFORE "
                   "and AFTER produced the SAME decisions on this cell. Combined with proof (a), "
                   "structural, and proof (b), the import closure, the instrumentation is "
                   "logging only on this path.")
    else:
        verdict = ("FAIL -- THE INSTRUMENTATION MOVED A DECISION. The control reproduced on both "
                   "trees and BEFORE differs from AFTER. Per the brief this must be REPORTED and "
                   "the instrumentation must NOT be shipped behind a switch.")

    rep = {
        "_claim": ("the D214 items 1 and 3 instrumentation changes no decision, for any arm, "
                   "ever. Logging only."),
        "_register": ("DRY cell on the REAL runner path (run_live2_real.py with no server). NOT a "
                      "measurement of anything; is_measurement is false in its own header."),
        "cell": {"arm": a.arm, "seed": a.seed, "n_devices": a.n, "run_s": a.run_s, "mode": "A"},
        "proof_a_structural": {
            "register": "CONSTRUCTED",
            "statement": ("every added line runs after em.run() returned; the only statement added "
                          "inside the run is `_EMU.append(em)` in run_live2_real._emulator, a list "
                          "append of a reference to an already-existing object."),
        },
        "proof_b_import_closure": import_closure_census(after, work),
        "proof_c_paired_cells": {
            "register": "OBSERVED",
            "digests_timing_stripped": d,
            "control_A_over_A_identical": aa,
            "control_B_over_B_identical": bb,
            "control_note": ("THE CONTROL IS READ FIRST. run_live2_real.py runs the emulator in "
                             "real time and ticks the coordinator on the wall clock, so same-tree "
                             "repeatability is not free and is measured here rather than assumed."),
            "before_equals_after": ab,
            "raw_sha16": {t: recs[t].get("decision_jsonl_raw_sha16") for t in recs},
            "raw_sha_note": ("the RAW file sha includes decision_latency_ms, a wall-clock "
                             "measurement that differs between any two runs. It is reported for "
                             "the register, never as the identity criterion."),
            "first_difference": first_difference(
                _rows(Path(recs["A1_before"]["run_dir"]) / "decision.jsonl"),
                _rows(Path(recs["B1_after"]["run_dir"]) / "decision.jsonl")),
            "strip_set": list(STRIP),
        },
        "all_cells_ran_alone": all_alone,
        "alone_note": ("D216 (1). loadavg is recorded AS A MAGNITUDE at the start and end of every "
                       "cell; see cells[].loadavg_at_start / _at_end. A cell with alone=false is "
                       "reported as such and its digest is not a bar."),
        "VERDICT": verdict,
        "cells": recs,
    }
    Path(a.out).write_text(json.dumps(rep, indent=2, default=float) + "\n")
    print(json.dumps({"VERDICT": verdict, "digests": d, "all_alone": all_alone}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
