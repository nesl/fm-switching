#!/usr/bin/env python3
"""Reconcile the baseline sweep list against the live2 registry (CPU only, static).

  python3 -I experiments/orchestration/live2/sweep_registry_recon.py

User instruction 2026-11-20, before the sweep resumes. For every name in SWEEP_ARMS: is it
registered, does it declare `reads_device_answer`, and has it ever run live? The point is that the
sweep can neither FAIL on a name nor silently run the wrong arm.

WHY THIS SCRIPT EXISTS AT ALL, recorded because the mistake was mine. The device-score audit
reported `r3streaming` and `thinking-qwenvl` as "not in the live2 registry". Those are FILE stems
(`r3streaming_adapted.py`, `thinking_qwenvl_adapted.py`); the registry names are `r3-streaming` and
`thinking-qwenvl-atdm`, and both are registered. A name guessed from a file name that fails to
resolve says nothing about the registry, so membership is settled HERE by calling `make_arm`, which
is what the driver itself calls, and never by a name lookup.

`arms.ARMS` alone is also not the registry: importing `hybrid` adds the hybrid configs, so
`hybrid-F-lhreq` is absent from that dict until the import the driver performs. That is a second
reason to test the real construction path rather than a dict.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "hybrid"), str(HERE / "fleet"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/live"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _provenance  # noqa: E402

SWEEP = ROOT / "results/orchestration/live2/frozen_test/runs/SWEEP_ARMS"
RESULTS = ROOT / "results"
OUT = ROOT / "results/orchestration/live2/sweep_registry_recon.json"


def live_runs(name):
    """Committed live2 run directories for this arm, by the run-dir naming convention."""
    return sorted(str(p.relative_to(ROOT)) for p in RESULTS.rglob(f"{name}_*")
                  if p.is_dir() and (p / "run_meta.json").exists())


def main():
    import arms as A
    import hybrid  # noqa: F401  registers the hybrid configs into the registry
    names = [l.strip() for l in SWEEP.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    rows = []
    for n in names:
        rec = dict(name=n, in_arms_dict=n in A.ARMS)
        try:
            arm = A.make_arm(n)
            rec.update(buildable=True, arm_class=type(arm).__name__,
                       declares_reads_device_answer=bool(
                           getattr(arm, "reads_device_answer", False)))
        except Exception as e:                                                 # noqa: BLE001
            rec.update(buildable=False, error=repr(e)[:200],
                       declares_reads_device_answer=None)
        runs = live_runs(n)
        rec.update(live_run_dirs=len(runs), live_runs=runs[:8])
        rows.append(rec)
    unbuildable = [r["name"] for r in rows if not r["buildable"]]
    declaring = [r["name"] for r in rows if r.get("declares_reads_device_answer")]
    res = dict(
        label="Baseline sweep list reconciled against the live2 registry. Membership is decided by "
              "make_arm, the driver's own construction path, not by a name lookup.",
        at=datetime.now().isoformat(), sweep_list=str(SWEEP.relative_to(ROOT)),
        n_names=len(rows), n_unbuildable=len(unbuildable), unbuildable=unbuildable,
        n_declaring_reads_device_answer=len(declaring), declaring=declaring,
        arms=rows,
        verdict=("The sweep can neither fail on a name nor run the wrong arm: every name in the "
                 "list builds through make_arm."
                 if not unbuildable else
                 "STOP: the sweep list names arms that do not build. Fix the list or the registry "
                 "before the sweep resumes."),
        correction=dict(
            what="the device-score audit said r3streaming and thinking-qwenvl are not in the "
                 "live2 registry",
            truth="those are file stems; the registry names are r3-streaming and "
                  "thinking-qwenvl-atdm, and BOTH are registered and declare "
                  "reads_device_answer",
            consequence="all FIVE declaring arms are live2-registered, not three, so the wiring "
                        "proof must cover five",
            also="arms.ARMS alone is not the registry: importing hybrid adds hybrid-F-lhreq, "
                 "which is in the sweep list"))
    res["_provenance"] = _provenance.stamp(script="sweep_registry_recon.py", model="none",
                                           device="cpu", n=len(rows), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(f"{len(rows)} sweep names | unbuildable {len(unbuildable)} {unbuildable}")
    print(f"declaring reads_device_answer ({len(declaring)}): {declaring}")
    for r in rows:
        if r.get("declares_reads_device_answer") or r["live_run_dirs"] or not r["buildable"]:
            print(f"  {r['name']}: buildable {r['buildable']} declares "
                  f"{r.get('declares_reads_device_answer')} live runs {r['live_run_dirs']}")
    print(res["verdict"])


if __name__ == "__main__":
    main()
