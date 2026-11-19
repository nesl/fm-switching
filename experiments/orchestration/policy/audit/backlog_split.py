#!/usr/bin/env python3
"""The decisive question: what dominates the backlog charge on `sh_admit`, and does it CANCEL?

`Rollout._terminal` (rollout.py:712-713):
    a6_backlog = sum(extra_work_s over risk.values())
    mu_term    = -mu * (max(busy - H, 0.0) + a6_backlog)

So the charge has two parts, a QUEUE part from engine busy beyond the horizon and an A6 part from
expected restore work. `a6_expected_restore_backlog_s` is exposed in the terminal detail, so both
are read rather than re-derived, and their sum is checked against `mu_term` recovered as
`terminal - cont - sv`.

The question that matters: `a6_backlog` is a fleet-wide sum over at-risk JOBS from `_prefix_risk`,
so for an `sh_admit` candidate it may be identical in both branches and CANCEL in DeltaJ, in which
case the escalated a6 units defect cannot explain F-A8 and would not help the dashcam axis.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _harness as H                                                   # noqa: E402

EPS = 1e-12


def _parts(res: Any, mu: float, horizon: float) -> Dict[str, float]:
    det = (getattr(res, "detail", None) or {}).get("terminal") or {}
    cont = sum(float(x.get("value", 0.0)) for x in (det.get("continuation") or []))
    sv = sum(float(x.get("value", 0.0)) for x in (det.get("state_value") or []))
    a6 = float(det.get("a6_expected_restore_backlog_s") or 0.0)
    busy = float(res.engine_busy_s)
    queue_s = max(busy - horizon, 0.0)
    return dict(mu_term=float(res.terminal) - cont - sv,
                queue_part=-mu * queue_s, a6_part=-mu * a6,
                queue_s=queue_s, a6_s=a6, busy=busy)


def collect(n: int, run_s: float, switches: Dict[str, bool], tmp: Path) -> Dict[str, Any]:
    H.setup_paths()
    from policy import coordinator as PCO
    from policy import rollout as PRO

    runs: List[Any] = []
    rows: List[Dict[str, Any]] = []
    _run = PRO.Rollout.run

    def run(self, fleet, release_now=(), exclude=(), extra_pending=(), drop=(),
            extra_jobs=None):
        r = _run(self, fleet, release_now=release_now, exclude=exclude,
                 extra_pending=extra_pending, drop=drop, extra_jobs=extra_jobs)
        runs.append(r)
        return r

    _dj = PCO.delta_j

    def dj(ro, fleet, action):
        before = len(runs)
        res = _dj(ro, fleet, action)
        pair = runs[before:]
        items = list(action.get("items") or [])
        kinds = {getattr(it, "kind", None) for it in items}
        if action["kind"] == "admit" and kinds == {"episode_call"} and len(pair) >= 2:
            mu = float(ro.params.mu)
            hz = float(ro.params.H)
            a = _parts(pair[0], mu, hz)
            b = _parts(pair[1], mu, hz)
            rows.append(dict(
                mu=mu,
                queue_delta=a["queue_part"] - b["queue_part"],
                a6_delta=a["a6_part"] - b["a6_part"],
                mu_term_delta=a["mu_term"] - b["mu_term"],
                queue_s_action=a["queue_s"], queue_s_ref=b["queue_s"],
                a6_s_action=a["a6_s"], a6_s_ref=b["a6_s"],
                identity_err=abs((a["queue_part"] + a["a6_part"]) - a["mu_term"]),
                delta_j=float(res["delta_j"])))
        return res

    PRO.Rollout.run = run
    PCO.delta_j = dj
    PRO.delta_j = dj
    try:
        H.run_fleet_cell(tmp / ("n%d" % n), n, run_s=run_s, seed=0, switches=switches)
    finally:
        PRO.Rollout.run = _run
        PCO.delta_j = _dj
        PRO.delta_j = _dj

    def summ(key):
        v = [r[key] for r in rows]
        mag = [abs(x) for x in v]
        return dict(n=len(v), nonzero=sum(1 for x in mag if x > EPS),
                    nonzero_frac=(round(sum(1 for x in mag if x > EPS) / len(v), 4) if v else None),
                    p50_abs=(round(st.median(mag), 6) if v else None),
                    max_abs=(round(max(mag), 6) if v else None),
                    min=(round(min(v), 6) if v else None),
                    max=(round(max(v), 6) if v else None))
    return dict(n_devices=n, n_sh_admit=len(rows),
                queue_delta=summ("queue_delta"), a6_delta=summ("a6_delta"),
                mu_term_delta=summ("mu_term_delta"),
                a6_cancels_frac=(round(sum(1 for r in rows if abs(r["a6_delta"]) <= EPS)
                                       / len(rows), 4) if rows else None),
                a6_s_nonzero_frac=(round(sum(1 for r in rows if r["a6_s_action"] > EPS)
                                         / len(rows), 4) if rows else None),
                max_identity_err=(round(max(r["identity_err"] for r in rows), 12) if rows else None),
                mu_p50=(round(st.median([r["mu"] for r in rows]), 4) if rows else None))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="4,8,16")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--switches", default="")
    a = ap.parse_args(argv)
    sw = {s: True for s in a.switches.split(",") if s.strip()}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="covex_backlog_"))
    cells = []
    for n in [int(x) for x in a.sizes.split(",") if x.strip()]:
        c = collect(n, a.run_s, sw, tmp)
        cells.append(c)
        print(json.dumps(c), flush=True)
    out = dict(check="covex_harden_sh_admit_backlog_split", is_measurement=False,
               label="AUDIT of a dry run. Decomposes the sh_admit backlog charge into its queue "
                     "part, -mu * max(busy - H, 0), and its A6 part, -mu * a6_backlog, per branch "
                     "and as a delta.",
               git_commit=head, switches_on=sorted(sw), cells=cells,
               _provenance=dict(git_commit=head, script="policy/audit/backlog_split.py",
                                model="none (pol4 frozen)", device="flash CPU only",
                                n="seed 0 at %s devices for %.0f s" % (a.sizes, a.run_s),
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
