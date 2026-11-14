#!/usr/bin/env python3
"""Run one short cell per ported arm against a server, and check the port. CPU only here.

StudyLIVE1-port, part 4. Against the fake stub (`--stub`) this runs on a machine with no GPU and
asserts, per arm:

  * every action it emitted was LEGAL (`interface.validate_action` runs inside `Policy.__call__`,
    so an illegal action raises and the arm is recorded as failed);
  * the per-cell arrival trace digest is IDENTICAL across arms (fairness rule 6);
  * no arm read the future: `interface.scrub` runs on every epoch, and any arm that declares
    `reads_future` is excluded from the live set by `classify.py`;
  * a decision trace exists.

**NOTHING FROM A STUB RUN IS A MEASUREMENT.** The stub's delays are drawn from committed
distributions so the loop is exercised at realistic ratios, and the cell is compressed in time
(`--speed`), which no measurement could be.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (HERE, ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/orchestration/baselines/smoke",
          ROOT / "experiments/orchestration/baselines/reconstructed",
          ROOT / "experiments/orchestration/sim", ROOT / "experiments/lib",
          ROOT / "experiments/dashcam"):
    sys.path.insert(0, str(p))

import adapter as A              # noqa: E402
import classify as CL            # noqa: E402
import fake_server as FS         # noqa: E402
import workload as W             # noqa: E402

OUT = ROOT / "results/orchestration/live1"
CELL = dict(mix="balanced", fleet=2, deadline_s=5.0, seed=0)


def live_arms() -> List[Any]:
    """Every orchestrator-level arm, built exactly as the simulator builds it."""
    import run_all
    cls = {r["arm"]: r for r in CL.classify()["arms"]}
    out = []
    for p in run_all.build():
        row = cls.get(p.name)
        if row is None:
            # a registry entry can carry more than one policy object (rh8's two readings), so
            # fall back to the longest registry name that prefixes this policy's name
            cand = [k for k in cls if p.name.startswith(k)]
            row = cls[max(cand, key=len)] if cand else None
        if row is None or not row["runs_live"]:
            continue
        if getattr(p, "reads_future", False):
            # rule 5: an oracle is never part of a deployable live comparison
            continue
        label = p.name + (f"/{getattr(p, 'objective', '')}"
                          if getattr(p, "objective", "") else "")
        out.append((label, p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stub", action="store_true", help="start the fake server in-process")
    ap.add_argument("--base-url", default=None, help="a real OpenAI-compatible endpoint")
    ap.add_argument("--window-s", type=float, default=300.0, help="trace seconds per cell")
    ap.add_argument("--speed", type=float, default=20.0, help="wall-clock compression")
    ap.add_argument("--tick-s", type=float, default=0.25)
    ap.add_argument("--arms", default=None, help="comma-separated subset")
    ap.add_argument("--out", default=str(OUT / "live1_stub_runs.json"))
    a = ap.parse_args()

    arms = live_arms()
    if a.arms:
        want = set(a.arms.split(","))
        arms = [(l, p) for l, p in arms if l in want]
    tr = W.build_trace(CELL["mix"], CELL["fleet"], CELL["deadline_s"], CELL["seed"])
    sha = A.trace_digest(tr, a.window_s)
    rows: List[Dict[str, Any]] = []

    def run_all_arms(url: str) -> None:
        for label, pol in arms:
            be = A.HttpBackend(url, time_scale=1.0 / a.speed)
            be.start_poller(0.2)
            t0 = time.time()
            try:
                orch = A.LiveOrchestrator(pol, be, tr, tick_s=a.tick_s, speed=a.speed,
                                          window_s=a.window_s, drain_s=30.0,
                                          seed=CELL["seed"])
                r = orch.run()
                r["failed"] = None
            except Exception as e:                                    # noqa: BLE001
                r = dict(arm=label, failed=f"{type(e).__name__}: {e}",
                         traceback=traceback.format_exc()[-800:], trace_sha256=sha)
            finally:
                be.close()
            r["arm"] = label
            r["wall_s"] = round(time.time() - t0, 2)
            r["digest_matches"] = bool(r.get("trace_sha256") == sha)
            rows.append(r)
            print("  %-30s %s on_time %s/%s  epochs over %s  %.1fs" % (
                label, "FAILED" if r.get("failed") else "ok",
                r.get("n_on_time"), r.get("n_answered"), r.get("epoch_overruns"),
                r["wall_s"]), flush=True)

    if a.stub or not a.base_url:
        with FS.serve() as url:
            print("stub on", url, flush=True)
            run_all_arms(url)
    else:
        run_all_arms(a.base_url)

    res = dict(
        label="StudyLIVE1-port: every orchestrator-level arm run for one short cell through the "
              "live adapter. NOTHING HERE IS A MEASUREMENT: the server is a fake stub whose "
              "delays are drawn from committed distributions, and the cell is time-compressed.",
        server="fake stub" if (a.stub or not a.base_url) else a.base_url,
        cell=dict(CELL, window_s=a.window_s, speed=a.speed, tick_s=a.tick_s,
                  trace_sha256=sha, trace_digest=tr.digest,
                  question_set=W.QUESTION_SET),
        n_arms=len(rows),
        n_failed=sum(1 for r in rows if r.get("failed")),
        all_digests_identical=all(r["digest_matches"] for r in rows),
        arms=rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print("wrote", a.out)
    print("arms %d, failed %d, digests identical %s" % (
        res["n_arms"], res["n_failed"], res["all_digests_identical"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
