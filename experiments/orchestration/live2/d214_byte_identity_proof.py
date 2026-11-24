#!/usr/bin/env python3
"""D214 FIGURE INSTRUMENTATION: THE BYTE-IDENTITY PROOF. Logging only, no decision moved.

THE CLAIM BEING PROVED. The D214 items 1 and 3 instrumentation (`f3_latency_stamps.py`,
`network_header.py` and the post-run block in `run_live2_real.py`) changes NO decision, for ANY
arm, ever. The user's constraint is "logging only; must be byte-identical in decisions for every
arm", and this file exists because that has to be PROVED and not asserted.

THREE PROOFS, IN INCREASING STRENGTH, AND THE WEAKEST IS NOT SKIPPED BECAUSE THE STRONGEST EXISTS.

  (a) STRUCTURAL, CONSTRUCTED. Every line of the new instrumentation runs AFTER `em.run()` has
      returned: the emulator's loop has ended, the coordinator is closed, every log file is
      written, and there is no decision left to make. Exactly TWO statements are added inside the
      run, and both are list appends of a reference to an object that already exists:
      `_EMU.append(em)` in `run_live2_real._emulator` and `_CO.append(co)` in
      `run_live2_real._inprocess`. Neither mutates any state a decision reads, and neither is read
      until after the run. This is reported as CONSTRUCTED, because an argument from reading code
      is not a measurement. It is also not a switch that happens to be off by default, which the
      brief asks us not to ship.

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
import difflib
import hashlib
import json
import os
import re
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


_POST_RUN_BEGIN = "D214 FIGURE INSTRUMENTATION (items 1 and 3). LOGGING ONLY. BEGIN"
_POST_RUN_END = "END D214 FIGURE INSTRUMENTATION"
_OUT_DICT = "out = dict(arm=a.arm"

# An added line inside the run is acceptable ONLY if it is one of these shapes. The point is not
# the list: it is that anything NOT matching is reported as UNCLASSIFIED and fails the check, so a
# future edit that slips a real statement into the run cannot pass by resembling the old one.
_SAFE_IN_RUN = (
    re.compile(r"^\s*_[A-Z]+\.append\([A-Za-z_][A-Za-z0-9_]*\)\s*(#.*)?$"),   # list append of a local
    re.compile(r"^\s*em = EM\.FleetEmulator\(.*\)\s*$"),                      # the pure rebinding
    re.compile(r"^\s*return em\s*$"),                                         # ...and its return
    re.compile(r"^\s*_EMU: list = \[\]\s*$"),                                 # module-level capture
    re.compile(r"^\s*_CO: list = \[\]\s*$"),
)


def in_run_additions(before_py: Path, after_py: Path) -> Dict[str, Any]:
    """PROOF (a), RECOMPUTED RATHER THAN RESTATED.

    A sentence saying "the only statement added inside the run is X" is invalidated silently by the
    next edit. So this enumerates, from the two files themselves, every executable line the AFTER
    file adds, classifies each as POST-RUN or IN-RUN by where it falls relative to the marked
    instrumentation block and the post-run `out = dict(...)`, and then requires every IN-RUN
    addition to match one of a few harmless shapes. Anything else is UNCLASSIFIED and the check
    FAILS.

    This is still CONSTRUCTED, not measured: it is a statement about the source text, not about a
    run. What it buys over the sentence it replaces is that it cannot go stale.
    """
    return classify_text(before_py.read_text(), after_py.read_text())


# The four injections the self-test uses. Each is a statement that WOULD change a decision, placed
# in a different region, so a check that passes them all is broken in a different way each time:
# inside `_inprocess`, inside `_emulator`, inside `run()` before the post-run block, and at module
# import. (anchor, harmful line to insert before it)
_INJECTIONS = (
    ("in _inprocess, mutating state a decision reads",
     "    _CO.append(co)", "    co.st.kv_capacity_enforced = True"),
    ("in _emulator, changing the emulator cadence",
     "    _EMU.append(em)", "    em.tick_s = 0.123"),
    ("in run(), before the post-run block, changing the seed",
     "    sends = bool(a.server)", "    a.seed = a.seed + 1"),
    ("at module import, reseeding the global RNG",
     "_CO: list = []", "import random; random.seed(7)"),
)


def check_self_test(before_py: Path, after_py: Path) -> Dict[str, Any]:
    """DOES THE CHECK FAIL WHEN IT SHOULD? A check that only ever passes proves nothing.

    The real tree passing is the POSITIVE control. This is the negative one: four statements that
    would genuinely change a decision are injected one at a time into four different regions, and
    the check must REJECT every one. A pass here means the verdict in `proof_a_structural` is
    load-bearing rather than decorative.

    This is not hypothetical rigour. The FIRST version of the classifier passed the real tree while
    sweeping `_emulator` and `_inprocess` into POST-RUN, because they are defined below `run` and
    the rule was a raw line number. It would have passed injections 1 and 2. The bug was found by
    reading what the check had classified, not from its verdict, so the self-test now runs every
    time and the same mistake cannot be made silently again.
    """
    before_text = before_py.read_text()
    after_text = after_py.read_text()
    cases: List[Dict[str, Any]] = []
    for where, anchor, harmful in _INJECTIONS:
        if anchor not in after_text:
            cases.append({"where": where, "RESULT": "SKIPPED: anchor %r is not in the after file, "
                                                    "so this region could not be tested" % anchor})
            continue
        mutated = after_text.replace(anchor, harmful + "   # INJECTED\n" + anchor, 1)
        r = classify_text(before_text, mutated)
        u = r.get("unclassified_in_run_additions") or []
        cases.append({"where": where, "injected": harmful,
                      "check_rejected_it": (r.get("PASS") is False),
                      "flagged": [{"line": x["line"], "in_function": x["in_function"],
                                   "text": x["text"]} for x in u[:2]]})
    tested = [c for c in cases if "check_rejected_it" in c]
    ok = bool(tested) and all(c["check_rejected_it"] for c in tested)
    return {
        "_what": ("NEGATIVE CONTROL ON THE CHECK ITSELF. Four decision-changing statements, one "
                  "per region, each injected alone; the classifier must reject all four."),
        "n_tested": len(tested), "n_skipped": len(cases) - len(tested),
        "cases": cases,
        "PASS": ok,
        "VERDICT": ("PASS: every injection was rejected, so proof (a)'s verdict is load-bearing."
                    if ok else
                    "FAIL: THE CHECK IS BROKEN, NOT THE TREE. At least one statement that would "
                    "change a decision was classified as harmless. proof_a_structural's PASS must "
                    "be disregarded until this is fixed."),
    }


def classify_text(before_text: str, after_text: str) -> Dict[str, Any]:
    """`in_run_additions` on two strings, so the self-test can mutate the after file in memory."""
    before = before_text.splitlines()
    after = after_text.splitlines()

    # the post-run region of the AFTER file, by its own markers
    b = e = o = None
    for i, ln in enumerate(after):
        if _POST_RUN_BEGIN in ln:
            b = i
        elif _POST_RUN_END in ln:
            e = i
        elif _OUT_DICT in ln:
            o = i
    markers = {"block_begin_line": (None if b is None else b + 1),
               "block_end_line": (None if e is None else e + 1),
               "out_dict_line": (None if o is None else o + 1)}
    if b is None or e is None or o is None:
        return {"VERDICT": "CANNOT CLASSIFY: the post-run block markers were not found in the "
                           "after file, so no line can be placed. Treat proof (a) as UNPROVED.",
                "markers": markers}

    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    added: List[tuple] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            for j in range(j1, j2):
                added.append((j + 1, after[j]))

    # WHICH FUNCTION EACH ADDED LINE IS IN, FROM THE AST. A raw line-number rule is WRONG here and
    # the first version of this check was wrong in the dangerous direction: `_emulator` and
    # `_inprocess` are defined BELOW `run`, so "after the post-run `out` dict" swept their bodies
    # into POST-RUN and the check PASSED while classifying the only two genuine in-run statements
    # as post-run. It would equally have passed a harmful statement added anywhere in those two
    # functions. An impossible success is as diagnostic as an impossible failure, and this one was
    # caught by reading what the check had classified rather than by its verdict.
    import ast
    try:
        tree = ast.parse("\n".join(after))
    except SyntaxError as exc:
        return {"VERDICT": "CANNOT CLASSIFY: the after file does not parse (%s). Treat proof (a) "
                           "as UNPROVED." % exc, "markers": markers}
    spans = [(n.lineno, n.end_lineno or n.lineno, n.name) for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def enclosing_fn(ln: int) -> Optional[str]:
        """The INNERMOST function containing this line, or None for module level."""
        best = None
        for lo, hi, name in spans:
            if lo <= ln <= hi and (best is None or (hi - lo) < best[0]):
                best = (hi - lo, name)
        return None if best is None else best[1]

    post_run, in_run, module_level, unclassified = [], [], [], []
    for lineno, text in added:
        s = text.strip()
        if not s or s.startswith("#"):
            continue                                   # comments and blanks execute nothing
        fn = enclosing_fn(lineno)
        rec = {"line": lineno, "text": s, "in_function": fn}
        if fn is None:
            # executed at IMPORT time, before any run exists. Still has to be harmless.
            if any(p.match(text) for p in _SAFE_IN_RUN):
                rec["shape"] = "module level, empty-list declaration, executed at import"
                module_level.append(rec)
            else:
                unclassified.append(rec)
        elif fn == "run" and (b <= lineno - 1 <= e or lineno - 1 >= o):
            post_run.append(rec)
        else:
            # inside `run` before the post-run block, or inside ANY other function: IN-RUN.
            if any(p.match(text) for p in _SAFE_IN_RUN):
                rec["shape"] = "harmless: a list append of an existing reference, or a rebinding"
                in_run.append(rec)
            else:
                unclassified.append(rec)

    ok = not unclassified
    return {
        "_what": ("PROOF (a), COMPUTED FROM THE TWO FILES. Every executable line the after file "
                  "adds, classified by whether it falls inside the marked post-run block (or the "
                  "post-run `out` dict) or inside the run. Comments and blank lines are dropped "
                  "because they execute nothing."),
        "register": "CONSTRUCTED: a statement about the source text, not about a run",
        "markers": markers,
        "n_executable_lines_added": len(post_run) + len(in_run) + len(unclassified),
        "n_post_run": len(post_run),
        "n_in_run": len(in_run),
        "n_module_level": len(module_level),
        "module_level_additions": module_level,
        "in_run_additions": in_run,
        "unclassified_in_run_additions": unclassified,
        "post_run_additions": post_run,
        "PASS": ok,
        "VERDICT": ("PASS: every executable addition is either in the post-run block or one of the "
                    "harmless in-run shapes (a list append of an existing reference, or a pure "
                    "rebinding). Nothing added inside the run can change a decision."
                    if ok else
                    "FAIL: %d executable line(s) were added INSIDE THE RUN in a shape this check "
                    "does not recognise as harmless. They are listed in "
                    "`unclassified_in_run_additions` and must be reviewed before the "
                    "instrumentation is called logging-only." % len(unclassified)),
    }


def free_gb(path: str = "/tmp") -> float:
    """Free gigabytes on the filesystem holding `path`. Decimal GB, as `df -BG` reports."""
    st = os.statvfs(path)
    return (st.f_bavail * st.f_frsize) / 1e9


def disk_stop(min_free_gb: float, path: str = "/tmp") -> Optional[Dict[str, Any]]:
    """None when there is room, else the record of WHY the run is stopping.

    A full disk has already silently skipped a commit on this project and it hits a `git push` as
    readily as a cell, so low disk is a TERMINAL condition here and not a warning: a cell that
    fills the box lands on another session's sweep or push and the failure looks like something
    else. Checked before EVERY cell, not only at the start, because the cells themselves write.
    """
    have = free_gb(path)
    if have >= float(min_free_gb):
        return None
    return {"STOP": "LOW DISK",
            "free_gb": round(have, 2), "min_free_gb": float(min_free_gb), "path": path,
            "why": ("halting rather than filling the disk. A disk-full here would land on another "
                    "session's push or sweep and would be misread as that session's fault.")}


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


def wait_alone(marker: str, mine: set, wait_s: float,
               min_free_gb: float = 5.0) -> Dict[str, Any]:
    """Bounded wait with THREE terminal conditions: a clear guard, the timeout, or low disk.

    The third exists because a waiter sitting for an hour on a filling disk looks exactly like a
    waiter that is working, from outside and from its own log.
    """
    t0 = time.time()
    while True:
        low = disk_stop(min_free_gb)
        if low is not None:
            return {"alone_at_start": False, "waited_s": round(time.time() - t0, 1),
                    "terminated_by": "LOW DISK", "disk": low}
        f = foreign(marker, mine)
        if not f:
            return {"alone_at_start": True, "waited_s": round(time.time() - t0, 1),
                    "terminated_by": "guard clear"}
        if time.time() - t0 >= wait_s:
            return {"alone_at_start": False, "waited_s": round(time.time() - t0, 1),
                    "terminated_by": "timeout", "foreign_at_give_up": f}
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
    min_free = float(getattr(a, "min_free_gb", 5.0))
    low = disk_stop(min_free)
    if low is not None:
        return {"tag": tag, "tree": str(tree), "NOT RUN": "LOW DISK", "disk": low}
    gate = wait_alone(marker, mine, wait_s, min_free_gb=min_free)
    if gate.get("terminated_by") == "LOW DISK":
        return {"tag": tag, "tree": str(tree), "NOT RUN": "LOW DISK",
                "disk": gate.get("disk"), "waited_for_alone_s": gate.get("waited_s")}
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
        "alone_by_guard": bool(gate.get("alone_at_start") and not after),
        "alone": ("GUARD-ASSERTED CLEAR" if (gate.get("alone_at_start") and not after)
                  else "FOREIGN LIVE2 PROCESS SEEN"),
        "alone_guard_bound": 'the guard enumerates foreign live2 processes by a hardcoded list of .py BASENAMES, so a process whose script name is not in that list is INVISIBLE to it. A cell can therefore record a clear guard truthfully and still not have been alone. THE BOOLEAN IS A SUMMARY OF THE CENSUS, NEVER THE FINDING: re-adjudicate from foreign_live2_at_start / _at_end and the loadavg magnitudes beside it. Direct evidence of determinism (two independent runs agreeing exactly) outranks any alone claim.',
        "waited_for_alone_s": gate.get("waited_s"),
        "wait_terminated_by": gate.get("terminated_by"),
        "free_gb_at_start": round(free_gb(), 2),
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
    ap.add_argument("--min-free-gb", type=float, default=5.0,
                    help="halt rather than fill the disk. Checked before every cell and as a "
                         "terminal condition of the alone-wait.")
    a = ap.parse_args(argv)
    before, after, work = Path(a.before), Path(a.after), Path(a.work)
    work.mkdir(parents=True, exist_ok=True)

    cells: List[Tuple[str, Path]] = [("A1_before", before), ("A2_before", before),
                                     ("B1_after", after), ("B2_after", after)]
    recs: Dict[str, Dict[str, Any]] = {}
    for tag, tree in cells:
        recs[tag] = run_one(tree, tag, work, a, a.wait_s)
        if recs[tag].get("NOT RUN") == "LOW DISK":
            Path(a.out).write_text(json.dumps(
                {"VERDICT": ("NOT RUN: LOW DISK. The proof halted before completing its cells "
                             "rather than filling the disk, so there is NO byte-identity result "
                             "here. This is not a pass and not a failure."),
                 "disk": recs[tag].get("disk"), "cells": recs}, indent=1, default=float) + "\n")
            print(json.dumps({"STOP": "LOW DISK", "tag": tag}), flush=True)
            return 9
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
    all_alone = all(bool(recs[t].get("alone_by_guard")) for t in recs)

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
        # PROOF (a) IS COMPUTED, NOT QUOTED. It used to be a sentence naming the one statement
        # added inside the run; that sentence went stale the moment a second one was added. This
        # recomputes the classification from the two files on every run, so the next edit cannot
        # quietly invalidate it: an unrecognised in-run addition FAILS the check instead of
        # resembling the old one.
        "proof_a_structural": in_run_additions(
            before / "run_live2_real.py", after / "run_live2_real.py"),
        # ...and the negative control ON THAT CHECK, read together with it. A classifier that
        # cannot fail says nothing when it passes.
        "proof_a_self_test": check_self_test(
            before / "run_live2_real.py", after / "run_live2_real.py"),
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
        "all_cells_guard_asserted_alone": all_alone,
        "alone_note": ("D216 (1). loadavg is recorded AS A MAGNITUDE at the start and end of every "
                       "cell; see cells[].loadavg_at_start / _at_end. THE FLAG IS GUARD-ASSERTED, "
                       "NOT A FINDING: read it as a summary of the foreign-process census beside "
                       "it (cells[].foreign_live2_at_start / _at_end) and re-adjudicate from that "
                       "census if it matters. See cells[].alone_guard_bound for why the guard can "
                       "be clear while the box was not."),
        "determinism_outranks_the_alone_flag": (
            "The A/A and B/B controls are TWO INDEPENDENT RUNS OF THE SAME CELL. If they agree "
            "exactly, that is DIRECT EVIDENCE that this cell is deterministic on this path, which "
            "is stronger than any argument that nothing disturbed it: a cell that reproduces under "
            "whatever contention it actually met does not need the box to have been empty. So the "
            "A-vs-B verdict rests on the agreement, and the alone flag is provenance beside it, "
            "not a precondition of it."),
        "VERDICT": verdict,
        "cells": recs,
    }
    Path(a.out).write_text(json.dumps(rep, indent=2, default=float) + "\n")
    print(json.dumps({"VERDICT": verdict, "digests": d, "all_alone": all_alone}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
