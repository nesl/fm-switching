#!/usr/bin/env python3
"""DRIVER for the D209 (4) / D210 0.25x rung-4 dry report (Session D).

ONE CELL PER PROCESS AND ONE CELL AT A TIME. `cf_pd_one_cell` records that a second dry run inside
one process does not reproduce the first, and `d190_rung4_r3_proofs.host_load_hazard_measured`
records that a RUNG-2 arm's dry digest is sensitive to host load while the others' are not. So
every cell is a fresh subprocess, they run strictly sequentially, and the 1-minute load average at
each cell's start is recorded beside its digest so a reader can see the condition it was measured
under.

WHAT THE CELL LIST IS FOR. The 0.25x setting can only reach a decision through a read of the GPU
KV pool. The pairs at 1x and 0.25x of the SAME arm are therefore the binding test, per rung:
a rung whose digest does not move between them cannot have been testing memory pressure at all
(CLAUDE.md Rule 2, `unexercised`), and a rung whose digest does move was.

Writes one JSON per cell into --out-dir and a manifest. Recomputes no digest of its own.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "d210_kv025_one_cell.py"

# (tag, arm, kv_scale, want_rd, enforce). PRIORITY ORDER: if the run is cut short, the cells
# that have landed are the ones the report cannot be written without.
CELLS: List[Tuple[str, str, float, bool, bool]] = [
    # 1. POSITIVE CONTROL on the check itself (CLAUDE.md check 7): a COMMITTED arm must reproduce
    #    its COMMITTED digest through THIS runner, which is what proves the latency-keeping patch
    #    is digest-neutral. A failure here is the check, not the arm.
    ("P1_state_uo_1x",       "covex-v6-state-uo",            1.00, False, False),
    # 2. THE RUNG-3 BAR AND RUNG 4 AT 1x. `-off` is the rung-3 arm by construction, so R4off_1x is
    #    also the second positive control: it must equal the committed rung-3 digest.
    ("R4off_1x",             "covex-v6-cf-c5attr-off",       1.00, False, False),
    ("R4_full_1x",           "covex-v6-cf-c5attr",           1.00, True,  False),
    # 3. THE SAME PAIR AT 0.25x WITH ENFORCEMENT OFF: the ARM-OBSERVATION channel alone.
    ("R4off_kv025",          "covex-v6-cf-c5attr-off",       0.25, False, False),
    ("R4_full_kv025",        "covex-v6-cf-c5attr",           0.25, True,  False),
    # 4. THE SAME PAIR AT 0.25x WITH ENFORCEMENT ON: the regime every posted `_kv0.25` cell runs
    #    in. The delta against 3 is the COORDINATOR-EVICTION channel, which is arm-independent.
    ("R4off_kv025_enf",      "covex-v6-cf-c5attr-off",       0.25, False, True),
    ("R4_full_kv025_enf",    "covex-v6-cf-c5attr",           0.25, True,  True),
    # 5. THE COMMITTED RUNG-3 ARM BY ITS OWN NAME at 0.25x: the blindness measurement on the arm
    #    the paper names, not only on rung 4's off arm.
    ("R3_rung3_kv025",       "covex-v6-fair-c5attr",         0.25, False, False),
    # 6. EACH LEG ALONE at 0.25x, so a combined count can be attributed (addendum 12 item 5).
    ("R4_pdonly_kv025",      "covex-v6-cf-c5attr-pdonly",    0.25, True,  False),
    ("R4_rqonly_kv025",      "covex-v6-cf-c5attr-rqonly",    0.25, True,  False),
    # 7. CLAUDE.md STEP 4 negative control, as a NAMED ARM, at the memory setting under test.
    #    It must collapse to R4off_kv025.
    ("N1_harm0_kv025",       "covex-v6-cf-c5attr-harm0",     0.25, True,  False),
    # 8. ADDED MID-RUN, and the reason is in the report's section 3.0. `R4off_1x` came back 711
    #    rows away from the committed rung-3 bar, and the cause is that
    #    `arms_v6cfr3._Rung4Mixin._cf_engine` swaps the state planner's weight source
    #    UNCONDITIONALLY, so the off arm is rung 3 PLUS the D206 (2) planner weight and is not the
    #    rung-3 bar its own module declares it to be. Without rung 3 under its OWN NAME at 1x there
    #    is no uncontaminated bar on this commit, and the off-vs-rung-3 delta is the size of the
    #    contamination. Run with `--only R3_rung3_1x`.
    ("R3_rung3_1x",          "covex-v6-fair-c5attr",         1.00, False, False),
]


def load1() -> float:
    return float(os.getloadavg()[0])


def run_cell(tag: str, arm: str, kv: float, rd: bool, enforce: bool, out: Path,
             seed: int, n: int, run_s: float, env: str) -> Dict[str, Any]:
    cell = out / ("%s.json" % tag)
    err = out / ("%s.err" % tag)
    lat = out / ("%s.lat.json" % tag)
    cmd = (["conda", "run", "-n", env, "python"] if env else [sys.executable])
    cmd += [str(RUNNER), "--arm", arm, "--seed", str(seed), "--n", str(n),
            "--run-s", str(run_s), "--cutoff-off", "--kv-scale", str(kv),
            "--lat-out", str(lat)]
    if enforce:
        cmd += ["--enforce-kv"]
    if rd:
        cmd += ["--rd-out", str(out / ("%s.rd.json" % tag)),
                "--pd-out", str(out / ("%s.pd.json" % tag))]
    l0 = load1()
    t0 = time.time()
    with open(cell, "w") as fo, open(err, "w") as fe:
        rc = subprocess.call(cmd, cwd=str(HERE), stdout=fo, stderr=fe)
    rec: Dict[str, Any] = {"tag": tag, "arm": arm, "kv_scale": kv,
                           "kv_capacity_enforced": bool(enforce), "returncode": rc,
                           "wall_s": round(time.time() - t0, 1), "load1_at_start": l0,
                           "cmd": " ".join(cmd)}
    if rc == 0:
        try:
            d = json.loads(cell.read_text())
            rec.update(digest=d.get("digest"), rows=d.get("rows"),
                       gpu_kv_tokens=d.get("gpu_kv_tokens"))
        except Exception as exc:                                           # noqa: BLE001
            rec["parse_error"] = repr(exc)
    else:
        rec["stderr_tail"] = err.read_text()[-1500:]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    # EACH CELL IS RUN BY `sys.executable`, WHICH IS THIS DRIVER'S OWN INTERPRETER. Launch the
    # driver itself with `conda run -n fmtk python`, and every cell then runs in that same
    # environment without a second activation; `conda` is not on PATH inside `conda run`, which
    # is what a `conda` child failed on. `--env` re-enables the explicit form if ever needed.
    ap.add_argument("--env", default="")
    ap.add_argument("--only", default=None, help="comma-separated tags")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    man: List[Dict[str, Any]] = []
    mpath = out / "manifest.json"
    if mpath.exists():
        try:
            man = list(json.loads(mpath.read_text()).get("cells") or [])
        except Exception:                                                  # noqa: BLE001
            man = []
    done = {r["tag"] for r in man if r.get("returncode") == 0}
    for tag, arm, kv, rd, enf in CELLS:
        if only is not None and tag not in only:
            continue
        if a.skip_existing and tag in done:
            continue
        rec = run_cell(tag, arm, kv, rd, enf, out, a.seed, a.n, a.run_s, a.env)
        man = [r for r in man if r.get("tag") != tag] + [rec]
        mpath.write_text(json.dumps(
            {"_what": "D209 (4) / D210 0.25x rung-4 dry cells, one process each, sequential",
             "_register": ("DRY and LOGICAL: --kv-scale scales test_live2_coord.GPU_KV, the "
                           "logical coordinator pool. No engine, no --num-gpu-blocks-override."),
             "seed": a.seed, "n": a.n, "run_s": a.run_s, "cutoff_off": True,
             "cells": sorted(man, key=lambda r: r["tag"])}, indent=1, default=float))
        print(json.dumps({k: rec.get(k) for k in
                          ("tag", "arm", "kv_scale", "kv_capacity_enforced", "returncode",
                           "digest", "rows", "gpu_kv_tokens", "wall_s",
                           "load1_at_start")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
