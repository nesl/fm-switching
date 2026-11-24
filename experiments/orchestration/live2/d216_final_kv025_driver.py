#!/usr/bin/env python3
"""The FINAL-LADDER 0.25x dry cells (StudyD216-KV025 check 3), run under D216 (1)'s ALONE RULE.

WHAT TRANSFERS FROM SESSION D AND WHAT DOES NOT. The cell STRUCTURE is Session D's
(`d210_kv025_driver.py`): a positive control on the runner itself, each rung at 1x and at 0.25x,
the 0.25x pair with coordinator eviction OFF and ON so the ARM-OBSERVATION channel and the
COORDINATOR-EVICTION channel are never merged, each compound alone so a combined count can be
attributed, and the Step 4 controls as NAMED ARMS rather than code edits. Its COUNTS do not
transfer: `covex-v6-final` differs from `covex-v6-cf-c5attr` by the `id(obs)` cache-key fix, the
rung-3 planner limb on the deficit feed and the alert release re-check, each decision-changing.

THE ALONE RULE IS ENFORCED BY THE DRIVER, NOT BY TIMING A WINDOW BY HAND (D216 (1)). Before every
cell it polls until no OTHER live2 process is running, runs the cell, and then RE-CHECKS that
nothing started DURING it; a cell that was not alone end to end is recorded as `alone=False` and
its digest is not reported as a bar. The driver's own child is identified by an ENVIRONMENT MARKER
(`D216_CELL_MARKER`), never by a command-line pattern: a `pgrep -f` on a pattern that matches the
session's own shell kills it with exit 144, and a cmdline match cannot tell my own cell from
someone else's anyway.

loadavg IS RECORDED AS A MAGNITUDE, per cell, at start and at end, with the foreign-process census
beside it, because a digest measured under contention and one measured alone are different
measurements and the report has to be able to say which it has.

REGISTER: DRY and LOGICAL. `--kv-scale` scales `test_live2_coord.GPU_KV`, the coordinator's own
pool. No engine, no real KV allocator, no H100.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "d216_final_kv025_one_cell.py"
MARKER_ENV = "D216_CELL_MARKER"

# (tag, arm, kv_scale, want_rd, enforce). PRIORITY ORDER: if the run is cut short, the cells that
# have landed are the ones the report cannot be written without.
CELLS: List[Tuple[str, str, float, bool, bool]] = [
    # 1. POSITIVE CONTROL ON THE CHECK ITSELF (CLAUDE.md check 7). A COMMITTED arm, through THIS
    #    wrapper, must reproduce its COMMITTED digest. A failure here is the registration wrapper,
    #    not the arm.
    #
    #    TWO OF THEM, AND THE SECOND IS NOT A BAR. `covex-v6-base` (af8befb9420ad86a / 12,085) is
    #    a rung-0 arm, so D216 (1)'s rule about an unfixed rung-2 digest does not touch it and it
    #    is an ADMISSIBLE bar. `covex-v6-state-uo` (9a4be873eb3c5fba / 14,218) is a rung-2 arm
    #    with the `id(obs)` cache-key fix OFF, which D216 (1) disallows as a bar; it is kept as a
    #    REPRODUCTION DATUM on the wrapper and is labelled as one, never cited as a bar.
    ("F0a_base_1x",           "covex-v6-base",                 1.00, False, False),
    ("F0_state_uo_1x",        "covex-v6-state-uo",             1.00, False, False),
    # 2. THE TWO FINAL BARS AT 1x. Neither has a committed value: these cells CREATE them.
    ("F1_r3_final_1x",        "covex-v6-fair-final",           1.00, False, False),
    ("F2_r4_final_1x",        "covex-v6-final",                1.00, True,  False),
    # 3. THE OFF-SWITCH IDENTITY BAR at 1x. Both compounds off must collapse to F1 byte-identically.
    #    On the committed family the same cell was 711 rows off its declared rung-3 bar; this is
    #    where the final ladder either cures that or does not.
    ("F3_r4_off_1x",          "covex-v6-final-off",            1.00, False, False),
    # 4. 0.25x WITH COORDINATOR EVICTION OFF: the ARM-OBSERVATION channel alone.
    ("F4_r3_final_kv025",     "covex-v6-fair-final",           0.25, False, False),
    ("F5_r4_final_kv025",     "covex-v6-final",                0.25, True,  False),
    ("F6_r4_off_kv025",       "covex-v6-final-off",            0.25, False, False),
    # 5. 0.25x WITH EVICTION ON: the regime every posted `_kv0.25` cell runs in. The delta against
    #    4 is the coordinator-eviction channel, which is arm-independent.
    ("F7_r4_final_kv025_enf", "covex-v6-final",                0.25, True,  True),
    ("F8_r3_final_kv025_enf", "covex-v6-fair-final",           0.25, False, True),
    # 6. EACH COMPOUND ALONE at 0.25x, so the combined count can be attributed.
    ("F9_r4_pdonly_kv025",    "covex-v6-final-pdonly",         0.25, True,  False),
    ("F10_r4_rqonly_kv025",   "covex-v6-final-rqonly",         0.25, True,  False),
    # 7. CLAUDE.md STEP 4, as named arms, at the memory setting under test. Each must collapse to
    #    F6 (the off arm at the same setting).
    ("F11_harm0_kv025",       "covex-v6-final-harm0",          0.25, True,  False),
    ("F12_marginhuge_kv025",  "covex-v6-final-margin-huge",    0.25, True,  False),
]

# Every .py basename under live2 counts as a live2 process when it appears as a cmdline token. A
# NAME LIST, not a pattern: the rule has to catch a runner nobody thought to enumerate, and it must
# not catch this driver's own shell.
def _live2_basenames() -> frozenset:
    return frozenset(p.name for p in HERE.rglob("*.py"))


def _ancestors(pid: int) -> set:
    """This process and every parent of it, so the guard can never see itself as contention."""
    out = {pid}
    cur = pid
    for _ in range(64):
        try:
            with open("/proc/%d/stat" % cur, "rb") as fh:
                fields = fh.read().rsplit(b")", 1)[1].split()
            ppid = int(fields[1])
        except Exception:                                                  # noqa: BLE001
            break
        if ppid <= 1 or ppid in out:
            break
        out.add(ppid)
        cur = ppid
    return out


def _has_marker(pid: int, marker: str) -> bool:
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            env = fh.read()
    except Exception:                                                      # noqa: BLE001
        return False
    return ("%s=%s" % (MARKER_ENV, marker)).encode() in env


def foreign_live2(marker: str, names: frozenset, mine: set) -> List[Dict[str, Any]]:
    """Every live2 process that is not this driver, its ancestors, or a cell it launched."""
    out: List[Dict[str, Any]] = []
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
        if not parts:
            continue
        hit = [t for t in parts if os.path.basename(t) in names]
        if not hit:
            continue
        if _has_marker(pid, marker):
            continue
        out.append({"pid": pid, "script": os.path.basename(hit[0]),
                    "cmdline": " ".join(parts)[:400]})
    return out


def wait_until_alone(marker: str, names: frozenset, mine: set, timeout_s: float,
                     poll_s: float = 20.0) -> Tuple[bool, List[Dict[str, Any]], float]:
    t0 = time.time()
    while True:
        busy = foreign_live2(marker, names, mine)
        if not busy:
            return True, [], time.time() - t0
        if time.time() - t0 >= timeout_s:
            return False, busy, time.time() - t0
        time.sleep(poll_s)


def run_cell(tag: str, arm: str, kv: float, rd: bool, enforce: bool, out: Path, seed: int,
             n: int, run_s: float, marker: str) -> Dict[str, Any]:
    cell, err = out / ("%s.json" % tag), out / ("%s.err" % tag)
    lat = out / ("%s.lat.json" % tag)
    cmd = [sys.executable, str(RUNNER), "--arm", arm, "--seed", str(seed), "--n", str(n),
           "--run-s", str(run_s), "--cutoff-off", "--kv-scale", str(kv), "--lat-out", str(lat)]
    if enforce:
        cmd += ["--enforce-kv"]
    if rd:
        cmd += ["--rd-out", str(out / ("%s.rd.json" % tag)),
                "--pd-out", str(out / ("%s.pd.json" % tag))]
    env = dict(os.environ)
    env[MARKER_ENV] = marker
    l0 = os.getloadavg()
    t0 = time.time()
    with open(cell, "w") as fo, open(err, "w") as fe:
        rc = subprocess.call(cmd, cwd=str(HERE), stdout=fo, stderr=fe, env=env)
    rec: Dict[str, Any] = {
        "tag": tag, "arm": arm, "kv_scale": kv, "kv_capacity_enforced": bool(enforce),
        "returncode": rc, "wall_s": round(time.time() - t0, 1),
        "loadavg_at_start": [round(x, 2) for x in l0],
        "loadavg_at_end": [round(x, 2) for x in os.getloadavg()],
        "cmd": " ".join(cmd)}
    if rc == 0:
        try:
            d = json.loads(cell.read_text())
            rec.update(digest=d.get("digest"), rows=d.get("rows"),
                       gpu_kv_tokens=d.get("gpu_kv_tokens"))
        except Exception as exc:                                           # noqa: BLE001
            rec["parse_error"] = repr(exc)
    else:
        rec["stderr_tail"] = err.read_text()[-2000:]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--only", default=None, help="comma-separated tags")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--wait-s", type=float, default=3600.0,
                    help="how long to wait for an alone window before giving up and reporting")
    a = ap.parse_args()

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    marker = uuid.uuid4().hex
    names = _live2_basenames()
    mine = _ancestors(os.getpid())
    only = set(a.only.split(",")) if a.only else None

    man: List[Dict[str, Any]] = []
    mpath = out / "manifest.json"
    if mpath.exists():
        try:
            man = list(json.loads(mpath.read_text()).get("cells") or [])
        except Exception:                                                  # noqa: BLE001
            man = []
    done = {r["tag"] for r in man if r.get("returncode") == 0}

    def flush(note: Optional[str] = None) -> None:
        mpath.write_text(json.dumps({
            "_register": ("DRY and LOGICAL. --kv-scale scales test_live2_coord.GPU_KV, the "
                          "coordinator's own pool; no engine, no real KV allocator, flash CPU."),
            "_alone_rule": ("D216 (1): every cell polls until no other live2 process exists, runs, "
                            "then re-checks. The driver's own child is identified by the "
                            "D216_CELL_MARKER environment variable, never by a cmdline pattern."),
            "marker": marker, "seed": a.seed, "n": a.n, "run_s": a.run_s,
            "note": note, "cells": man}, indent=1))

    for tag, arm, kv, rd, enf in CELLS:
        if only is not None and tag not in only:
            continue
        if a.skip_existing and tag in done:
            continue
        ok, busy, waited = wait_until_alone(marker, names, mine, a.wait_s)
        if not ok:
            man.append({"tag": tag, "arm": arm, "kv_scale": kv, "SKIPPED": "NEVER ALONE",
                        "waited_s": round(waited, 1), "blockers": busy})
            flush("gave up waiting for an alone window; cells after %s were not run" % tag)
            print("GAVE UP: no alone window after %.0f s; blockers: %s"
                  % (waited, [b["script"] for b in busy]), file=sys.stderr)
            return 2
        rec = run_cell(tag, arm, kv, rd, enf, out, a.seed, a.n, a.run_s, marker)
        rec["waited_for_alone_s"] = round(waited, 1)
        after = foreign_live2(marker, names, mine)
        rec["started_during_the_cell"] = after
        rec["alone"] = not after
        man.append(rec)
        flush()
        print("%-24s rc=%s wall=%ss load0=%s alone=%s %s/%s"
              % (tag, rec["returncode"], rec["wall_s"], rec["loadavg_at_start"][0],
                 rec["alone"], rec.get("digest"), rec.get("rows")), flush=True)
    flush("complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
