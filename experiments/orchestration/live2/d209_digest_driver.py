#!/usr/bin/env python3
"""D209 (2): before/after decision digests for the three placeholder fixes, one dry cell per
process, through the COMMITTED recipe (`cf_pd_one_cell.py --cutoff-off`, 16 devices, seed 4,
1,200 s, posted knobs 40:40:20 / lh_req / ss2 / epg / per-frame / reask 30.0).

The runner is the committed one and the digest is its digest: this file only spawns it in two
trees and pairs the results. POSITIVE CONTROL on the check itself: `covex-v6-base` must read
af8befb9420ad86a and `covex-v6-fair-c5attr` must read 12e4f73ce0ebd865 / 13,812 on the BEFORE
side; if a known-good committed arm fails there, the check is broken and not the arm.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = "/home/pragya/miniconda3/envs/fmtk/bin/python"
# The two (or three) code trees live in a session-unique scratchpad, never in the working
# tree: the local HEAD is over 1,200 commits behind origin and its live2/ tree is stale to
# the point that live2/hybrid/ is absent, so every side of every comparison here is a
# `git archive` of ONE literal origin sha. Set D209_SP to the directory holding the
# `before/`, `after/` and `after_no22/` trees.
SP = Path(os.environ.get("D209_SP", "/tmp/d209"))

RUNGS = ("covex-v6-base", "covex-v6-rules", "covex-v6-state-uo",
         "covex-v6-state-uo-c5attr", "covex-v6-fair-c5attr", "covex-v6-fair-c5attr-rr",
         # rung 4, the ONLY rung among our arms that reads gpu_kv_fraction (arms_v6cf.py:306)
         "covex-v6-cf-c5attr", "covex-v6-cf-pd-c5attr")
# the D179 (6a) reported-baseline set, which is the list the byte-identity gate is stated over,
# PLUS the three baselines the verified hit-6 read census names as live readers of
# gpu_kv_fraction: preble (preble_adapted.py:57), b9 (constructed.py:416) and uniscale
# (uniscale_adapted.py:63). They are here because they are the arms a hit-6 fix would move, so
# leaving them out would have made the identity table unable to fail where it matters.
BASELINES = ("v5-rules-2", "hybrid-F-lhreq-noc3", "b7-edf-feasibility", "always-cloud-fcfs",
             "edf", "llf", "mooncake", "attentionstore-prefetch", "simplestream",
             "querystream-proactive", "warm-all-lru", "confidence-cascade", "eco-llm",
             "preble", "b9", "uniscale")
COMMITTED = {"covex-v6-base": ("af8befb9420ad86a", None),
             "covex-v6-fair-c5attr": ("12e4f73ce0ebd865", 13812)}
ROWS_FOR = ("covex-v6-state-uo-c5attr", "covex-v6-fair-c5attr")


def cell(tree: str, arm: str, seed: int, rows_dir: Path) -> dict:
    d = SP / tree / "experiments/orchestration/live2"
    cmd = ["nice", "-n", "5", PY, "cf_pd_one_cell.py", "--arm", arm, "--seed", str(seed),
           "--n", "16", "--run-s", "1200", "--cutoff-off"]
    if arm in ROWS_FOR:
        cmd += ["--rows-out", str(rows_dir / f"{tree}_{arm}_s{seed}.rows.json")]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True, timeout=5400)
    lines = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not lines:
        tail = ((p.stderr or "").strip().splitlines() or ["no output"])[-1]
        return {"tree": tree, "arm": arm, "error": tail[:500], "wall_s": round(time.time() - t0, 1)}
    out = json.loads(lines[-1])
    out["tree"] = tree
    out["wall_s"] = round(time.time() - t0, 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--arms", default=None)
    ap.add_argument("--trees", default="before,after",
                    help="the two trees to pair, by scratchpad subdirectory name")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    arms = a.arms.split(",") if a.arms else list(RUNGS) + list(BASELINES)
    t_before, t_after = a.trees.split(",")
    rows_dir = SP / "rows"
    rows_dir.mkdir(exist_ok=True)
    jobs = [(t, arm) for arm in arms for t in (t_before, t_after)]
    res = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(cell, t, arm, a.seed, rows_dir) for t, arm in jobs]
        for f in futs:
            r = f.result()
            res.append(r)
            print(json.dumps({k: r.get(k) for k in ("tree", "arm", "digest", "rows", "error",
                                                    "wall_s")}), flush=True)
    by = {}
    for r in res:
        by.setdefault(r["arm"], {})[r["tree"]] = r
    table = []
    for arm in arms:
        b, af = by.get(arm, {}).get(t_before, {}), by.get(arm, {}).get(t_after, {})
        row = {"arm": arm, "before_digest": b.get("digest"), "after_digest": af.get("digest"),
               "before_rows": b.get("rows"), "after_rows": af.get("rows"),
               "identical": (b.get("digest") is not None
                             and b.get("digest") == af.get("digest")),
               "before_error": b.get("error"), "after_error": af.get("error"),
               "before_stats": b.get("stats"), "after_stats": af.get("stats")}
        if arm in COMMITTED:
            dg, nr = COMMITTED[arm]
            row["positive_control"] = {
                "committed_digest": dg, "committed_rows": nr,
                "before_matches_committed": b.get("digest") == dg,
                "before_rows_match": (nr is None or b.get("rows") == nr)}
        table.append(row)
    doc = {"recipe": ("cf_pd_one_cell.py --cutoff-off, n=16, seed=%d, run_s=1200, posted knobs "
                      "40:40:20 / lh_req / ss2 / epg / per-frame / reask 30.0" % a.seed),
           "before_tree": str(SP / t_before), "after_tree": str(SP / t_after),
           "fixes_in_after": ["live2/touch_policy.py (hit 22)",
                              "live2/engine_actions.py (hit 26)",
                              "live/adapter.py (hit 6)"],
           "n_distinct_before_digests": len({r["before_digest"] for r in table
                                             if r["before_digest"]}),
           "n_arms": len(table), "arms": table, "raw": res}
    Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
