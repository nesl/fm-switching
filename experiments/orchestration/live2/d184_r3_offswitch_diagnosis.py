#!/usr/bin/env python3
"""Why does covex-v6-fair-c5attr-off NOT collapse to covex-v6-state-uo-c5attr?

NO INSTRUMENTATION OF ANY KIND. The first proof run wrapped `_deficit_order_key` and `decide` on
every arm, and although the three committed baselines reproduced their committed digests under
those wrappers, the c5attr base is the one arm with no committed digest that this tree still
reproduces, so the wrappers are removed here rather than argued about.

What it reads: the C5 ATTRIBUTION COUNTERS the rule itself maintains, plus the cap trajectory. If
`covex-v6-state-uo-c5attr` shows suppressions and `covex-v6-fair-c5attr-off` shows none, the mixin
drops the rule; if both show the same and the digests still differ, the cause is elsewhere.

One dry cell per process, planner cutoff patched off, posted knobs, seed 4.
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
REPO = HERE.parents[2]
OUT = Path(os.environ.get("D184_DIAG_OUT", "/tmp/d184_r3_offswitch_diagnosis.json"))

CELL = dict(seed=4, n=16, run_s=1200.0, ratio="40:40:20", robot_question_set="lh_req",
            ss_question_set="ss2", dashcam_format="epg", robot_upload="per-frame",
            robot_reask_mean_s=30.0)
ARMS = ["covex-v6-state-uo", "covex-v6-state-uo-c5attr",
        "covex-v6-fair-c5attr-off", "covex-v6-fair-c5attr-gain0"]
KEEP_PREFIX = ("c5_attr", "c5_", "cap", "share_", "deficit", "c2_", "over_limit")


def _patch_planner_cutoff() -> None:
    import cf_instrument as CI
    for n in dir(CI):
        o = getattr(CI, n)
        if isinstance(o, type) and hasattr(o, "over_budget"):
            o.over_budget = lambda self, budget_ms=None: False


def _chain(obj: Any) -> List[Any]:
    out: List[Any] = []
    o: Any = obj
    seen = set()
    while o is not None and id(o) not in seen:
        seen.add(id(o))
        out.append(o)
        o = o.__dict__.get("_rules") or o.__dict__.get("_base")
    return out


def run_one(arm_name: str, rows_out: Optional[str]) -> Dict[str, Any]:
    for p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
              str(HERE.parent / "baselines")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import arms as A  # noqa: F401
    import arms_v6fairfeed as FF
    import arms_v6state as VS
    VS.register()
    FF.register()
    _patch_planner_cutoff()
    import test_hybrid as TH

    seen: Dict[str, Any] = {}

    def patch(arm: Any) -> None:
        """Records the object graph ONLY. It installs no wrapper and calls nothing."""
        seen["arm"] = arm

    rows, st = TH.dry(arm_name, CELL["seed"], CELL["n"], run_s=CELL["run_s"],
                      ratio=CELL["ratio"], robot_question_set=CELL["robot_question_set"],
                      ss_question_set=CELL["ss_question_set"],
                      dashcam_format=CELL["dashcam_format"], robot_upload=CELL["robot_upload"],
                      robot_reask_mean_s=CELL["robot_reask_mean_s"], patch=patch)
    rows = list(rows or [])
    rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
    digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                       default=float).encode()).hexdigest()[:16]
    st = dict(st or {})
    arm = seen.get("arm")
    chain = _chain(arm) if arm is not None else []
    core = chain[-1] if chain else None
    res = dict(
        arm=arm_name, digest=digest, rows=len(rows),
        chain=[type(o).__name__ for o in chain],
        c5_attr_flag_by_chain_object=[bool(vars(o).get("c5_attr_self_released", False))
                                      for o in chain],
        c5_attr_flag_on_core=bool(getattr(core, "c5_attr_self_released", False)),
        attr_mon_len_at_end=len(getattr(core, "_attr_mon", []) or []),
        attr_mon_tail=[[round(float(v), 6), bool(o)]
                       for v, o in (getattr(core, "_attr_mon", []) or [])[-5:]],
        cap_at_end=getattr(core, "cap", None),
        has_live2_completed=hasattr(arm, "live2_completed"),
        live2_completed_qualname=getattr(getattr(arm, "live2_completed", None),
                                         "__qualname__", None),
        counters={k: v for k, v in sorted(st.items())
                  if isinstance(v, (int, float)) and str(k).startswith(KEEP_PREFIX)})
    if rows_out:
        Path(rows_out).write_text(json.dumps(dict(arm=arm_name, rows=rr), default=float) + "\n")
    return res


def _cell(arm: str, keep: Optional[Path]) -> Dict[str, Any]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", arm]
    if keep is not None:
        cmd += ["--rows", str(keep)]
    env = dict(os.environ, PYTHONHASHSEED="0")
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=10800, env=env)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode or not line:
        return dict(arm=arm, error=(p.stderr or p.stdout)[-3000:])
    return json.loads(line[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--rows")
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one, a.rows), default=float))
        return 0

    tmp = Path(os.environ.get("D184_SCRATCH", "/tmp")) / "d184_diag"
    tmp.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=4)
    keep = {arm: tmp / ("rows_%s.json" % arm.replace("-", "_")) for arm in ARMS}
    futs = {arm: pool.submit(_cell, arm, keep[arm]) for arm in ARMS}
    cells = {}
    for arm in ARMS:
        cells[arm] = futs[arm].result()
        c = cells[arm]
        print("%-30s %s rows=%s attr_mon=%s cap=%s flags=%s" % (
            arm, c.get("digest"), c.get("rows"), c.get("attr_mon_len_at_end"),
            c.get("cap_at_end"), c.get("c5_attr_flag_by_chain_object")), flush=True)
        print("   counters:", json.dumps(c.get("counters")), flush=True)

    for p in (str(HERE), str(HERE / "hybrid")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_hybrid as TH

    def _rows(arm: str) -> List[Dict[str, Any]]:
        return json.loads(keep[arm].read_text())["rows"]

    pairs = [("covex-v6-state-uo", "covex-v6-state-uo-c5attr"),
             ("covex-v6-state-uo-c5attr", "covex-v6-fair-c5attr-off"),
             ("covex-v6-state-uo", "covex-v6-fair-c5attr-off"),
             ("covex-v6-fair-c5attr-off", "covex-v6-fair-c5attr-gain0")]
    diffs = {}
    for x, y in pairs:
        ra, rb = _rows(x), _rows(y)
        first = None
        for i, (p_, q_) in enumerate(zip(ra, rb)):
            if p_ != q_:
                first = dict(index=i, a=p_, b=q_)
                break
        diffs["%s__vs__%s" % (x, y)] = dict(
            positional=TH._differing(ra, rb), setwise=TH._differing_setwise(ra, rb),
            rows=(len(ra), len(rb)), first_differing=first)
        print("%-60s pos=%s set=%s" % ("%s vs %s" % (x, y),
                                       diffs[list(diffs)[-1]]["positional"],
                                       diffs[list(diffs)[-1]]["setwise"]), flush=True)

    out = dict(_what=("why covex-v6-fair-c5attr-off does not collapse to covex-v6-state-uo-c5attr;"
                      " NO instrumentation, one dry cell per process"),
               cell=dict(CELL), cells=cells, diffs=diffs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
