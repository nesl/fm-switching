#!/usr/bin/env python3
"""D129 item 4: calibrate the dry-run SCREEN against the LIVE H100 pilot.

The dry run prices the engine from the same committed curves COVEX's model uses, so it is
optimistic for COVEX. This measures BY HOW MUCH, per axis and per size, by applying the SAME
delivery definition to the live pilot's `outcomes.jsonl` as to the dry runs:

    delivered on time  <=>  t_delivered is set and t_delivered <= t_opportunity + deadline_s

Read-only over committed live results. Nothing here re-runs anything on a GPU.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[4]
RUNS = ROOT / "results/orchestration/live2/pilot/runs3"


def delivery(run_dir: Path) -> Optional[Dict[str, Any]]:
    p = run_dir / "outcomes.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(l) for l in open(p)]
    out: Dict[str, Any] = {}
    for kind in ("monitor", "recall"):
        k = [r for r in rows if r.get("kind") == kind]
        if not k:
            out[kind] = dict(offered=0)
            continue
        dv = [r for r in k if r.get("t_delivered") is not None]
        ot = [r for r in dv
              if float(r["t_delivered"]) <= float(r["t_opportunity"]) + float(r["deadline_s"])]
        out[kind] = dict(offered=len(k), delivered_any=len(dv), on_time=len(ot),
                         fraction=round(len(ot) / len(k), 4))
    return out


def parse_cell(name: str) -> Dict[str, Any]:
    m = re.match(r"^(?P<arm>.+?)_n(?P<n>\d+)_(?P<win>\d+)s", name)
    if not m:
        return dict(arm=None, n=None, window_s=None)
    return dict(arm=m.group("arm"), n=int(m.group("n")), window_s=int(m.group("win")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry", default="", help="JSON of dry-run fractions to compare against")
    a = ap.parse_args(argv)
    cells = []
    for d in sorted(glob.glob(str(RUNS / "*"))):
        if d.endswith(".stdout") or not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        info = parse_cell(name)
        dl = delivery(Path(d))
        if dl is None:
            continue
        meta_p = Path(d) / "run_meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        cells.append(dict(cell=name, **info, seed=meta.get("seed"),
                          memory=meta.get("memory") or meta.get("memory_setting"),
                          live=dl))
        print("%-40s arm=%-18s n=%-4s win=%-5s seed=%-4s | dashcam %-8s robot %-8s (%s of %s)" % (
            name, info["arm"], info["n"], info["window_s"], meta.get("seed"),
            dl["monitor"].get("fraction"), dl["recall"].get("fraction"),
            dl["recall"].get("on_time"), dl["recall"].get("offered")), flush=True)
    out = dict(check="covex_harden_live_calibration", is_measurement=False,
               label="READ-ONLY over the committed LIVE H100 pilot results. The SAME delivery "
                     "definition as the dry-run screen is applied, so the two are comparable. "
                     "Live pilot cells are labelled PILOT, not round-1 results, by their own "
                     "study; nothing here changes that.",
               definition="t_delivered is set and t_delivered <= t_opportunity + deadline_s",
               source=str(RUNS.relative_to(ROOT)), cells=cells,
               _provenance=dict(script="policy/audit/calibrate_live.py", model="live 32B on the "
                                "H100 for the LIVE side; none for the dry side",
                                device="read-only on flash", n="all committed runs3 cells",
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
