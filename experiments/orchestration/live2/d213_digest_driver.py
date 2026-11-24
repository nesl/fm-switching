#!/usr/bin/env python3
"""D213 items 2 and 3: before/after dry decision digests, through the COMMITTED recipe.

The runner is the committed one (`cf_pd_one_cell.py --cutoff-off`, 16 devices, seed 4, 1,200 s,
posted knobs) and the digest is its digest; this file only spawns it in two `git archive` trees of
ONE literal origin sha and pairs the results. Modelled on the committed
`d209_digest_driver.py` and differing from it in two ways that are deliberate:

  * THE ARM LIST IS D213's PAPER BASELINE SET, not D179 (6a)'s. D213 amends D212 (2): the paper's
    baselines are the BASELINE_MATRIX active arms plus kvflow-prefetch, cascade-routing and
    device-only, and fidelity work STOPS on pensieve, rh8, inar-vl, routellm, preble, b9 and
    uniscale. `preble`, `b9` and `uniscale` are therefore NOT here even though they read
    `gpu_kv_fraction`: they are out of the reported set, and on a dry cell they could not move
    anyway (a dry cell never calls `be.metrics()`).
  * ONE CELL AT A TIME (`--jobs 1` is the only supported setting). D213 item 1's ALONE RULE: a dry
    cell whose digest is used as a proof bar runs alone on its machine, and `/proc/loadavg` is
    recorded per cell as a MAGNITUDE, never a boolean.

POSITIVE CONTROL ON THE CHECK ITSELF, because an impossible success is as diagnostic as an
impossible failure: `covex-v6-base` must read af8befb9420ad86a and `covex-v6-fair-c5attr` must read
12e4f73ce0ebd865 / 13,812 rows on the BEFORE side. If a known-good committed arm fails there, the
check is broken and not the arm.

RUNG 2 IS MEASURED AND IS NOT A BAR. `covex-v6-state-uo-c5attr`'s dry digest is allocation
sensitive: the D209 (2) report records a COMMENT-ONLY edit to `engine_actions.py` moving it by 85
committed-key decisions and 11 rows, because `_queued_behind` keys on `id(obs)`. Item 3 edits
`coordinator.py`, which is in every arm's import graph, so a rung-2 move here cannot be attributed
to semantics by this comparison alone and is reported with that attribution stated.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PY = "/home/pragya/miniconda3/envs/fmtk/bin/python"
SP = Path(os.environ.get("D213_SP", "/tmp/d213"))

# our arms: rungs 1 to 4 of the spec v6 ladder as the ladder session has them committed
RUNGS = ("covex-v6-base", "covex-v6-rules", "covex-v6-state-uo", "covex-v6-state-uo-c5attr",
         "covex-v6-fair-c5attr", "covex-v6-cf-c5attr", "covex-v6-cf-pd-c5attr")
# D213's paper baseline set (BASELINE_MATRIX active arms + kvflow-prefetch + cascade-routing +
# device-only), plus v5-rules-2, the rung-1 predecessor the D174 census is stated over.
BASELINES = ("always-cloud-fcfs", "attentionstore-prefetch", "b7-edf-feasibility",
             "confidence-cascade", "eco-llm", "edf", "llf", "lmcache", "mooncake",
             "querystream-proactive", "simplestream", "streamscout", "warm-all-lru",
             "kvflow-prefetch", "cascade-routing", "device-only", "v5-rules-2")
COMMITTED = {"covex-v6-base": ("af8befb9420ad86a", None),
             "covex-v6-fair-c5attr": ("12e4f73ce0ebd865", 13812)}
# the digest of this arm is NOT used as a bar (see the module docstring)
NOT_A_BAR = ("covex-v6-state-uo-c5attr",)


def loadavg():
    return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]


def cell(tree: str, arm: str, seed: int, rows_dir: Path, env_extra=None) -> dict:
    d = SP / tree / "experiments/orchestration/live2"
    cmd = [PY, "-I", "cf_pd_one_cell.py", "--arm", arm, "--seed", str(seed),
           "--n", "16", "--run-s", "1200", "--cutoff-off",
           "--rows-out", str(rows_dir / f"{tree}_{arm}_s{seed}.rows.json")]
    env = dict(os.environ)
    env.update(env_extra or {})
    la0 = loadavg()
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True, timeout=7200, env=env)
    la1 = loadavg()
    lines = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not lines:
        tail = ((p.stderr or "").strip().splitlines() or ["no output"])[-1]
        return {"tree": tree, "arm": arm, "error": tail[:600],
                "wall_s": round(time.time() - t0, 1), "loadavg_start": la0, "loadavg_end": la1}
    out = json.loads(lines[-1])
    out["tree"] = tree
    out["wall_s"] = round(time.time() - t0, 1)
    out["loadavg_start"] = la0
    out["loadavg_end"] = la1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--arms", default=None)
    ap.add_argument("--trees", default="before,after")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    arms = a.arms.split(",") if a.arms else list(RUNGS) + list(BASELINES)
    t_before, t_after = a.trees.split(",")
    rows_dir = SP / "rows"
    rows_dir.mkdir(exist_ok=True)
    res = []
    for arm in arms:
        for t in (t_before, t_after):
            r = cell(t, arm, a.seed, rows_dir)
            res.append(r)
            print(json.dumps({k: r.get(k) for k in ("tree", "arm", "digest", "rows", "error",
                                                    "wall_s", "loadavg_start")}), flush=True)
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
               "used_as_bar": arm not in NOT_A_BAR,
               "loadavg_before": b.get("loadavg_start"), "loadavg_after": af.get("loadavg_start"),
               "wall_s": [b.get("wall_s"), af.get("wall_s")]}
        if not row["identical"] and b.get("digest") and af.get("digest"):
            row["moved_decisions"] = _rowdiff(rows_dir, t_before, t_after, arm, a.seed)
        if arm in COMMITTED:
            dg, nr = COMMITTED[arm]
            row["positive_control"] = {
                "committed_digest": dg, "committed_rows": nr,
                "before_matches_committed": b.get("digest") == dg,
                "before_rows_match": (nr is None or b.get("rows") == nr)}
        table.append(row)
    doc = {"recipe": ("cf_pd_one_cell.py --cutoff-off, n=16, seed=%d, run_s=1200, posted knobs "
                      "40:40:20 / lh_req / ss2 / epg / per-frame / reask 30.0" % a.seed),
           "alone_rule": "one cell at a time; loadavg recorded per cell as a magnitude",
           "before_tree": str(SP / t_before), "after_tree": str(SP / t_after),
           "fixes_in_after": ["live2/asyncbackend.py (D213 item 2, the /metrics scrape)",
                              "live2/coordinator.py (D213 item 3, the belief prefix record)"],
           "n_arms": len(table),
           "n_identical": sum(1 for r in table if r["identical"]),
           "n_moved": sum(1 for r in table if not r["identical"]),
           "arms": table, "raw": res}
    Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
    print("wrote", a.out)
    return 0


def _rowdiff(rows_dir: Path, tb: str, ta: str, arm: str, seed: int) -> dict:
    """Positional and setwise decision differences, in the committed `test_hybrid` registers."""
    try:
        A = json.loads((rows_dir / f"{tb}_{arm}_s{seed}.rows.json").read_text())
        B = json.loads((rows_dir / f"{ta}_{arm}_s{seed}.rows.json").read_text())
    except Exception as e:                                                # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}

    def key(r):
        return (r.get("t"), r.get("kind"), tuple(r.get("opportunity_ids") or ()),
                r.get("representation"), r.get("defer_s"))
    from collections import Counter
    ca, cb = Counter(key(r) for r in A), Counter(key(r) for r in B)
    pos = sum(1 for x, y in zip(A, B) if x != y) + abs(len(A) - len(B))
    first = next((i for i, (x, y) in enumerate(zip(A, B)) if x != y), None)
    fields = Counter()
    for x, y in zip(A, B):
        if x != y:
            for k in set(x) | set(y):
                if x.get(k) != y.get(k):
                    fields[k] += 1
    return {"positional": pos, "setwise": sum(((ca - cb) + (cb - ca)).values()),
            "n_rows": [len(A), len(B)], "first_differing_index": first,
            "first_differing_pair": ([A[first], B[first]] if first is not None else None),
            "fields_that_differ": dict(fields)}


if __name__ == "__main__":
    raise SystemExit(main())
