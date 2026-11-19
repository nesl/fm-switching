#!/usr/bin/env python3
"""Does mu track SCARCITY, or the price of the best use?

mu is an EWMA of the realised marginal utility per GPU-second of the last released item. That is a
price of the BEST USE, not of contention, so it may stay high while the engine is nearly idle.
This records mu beside an occupancy proxy at each decision period, so the two can be compared.

The occupancy proxy is the in-flight request count the arm itself sees, summed over
`obs.cloud.running_by_class`, which is the same quantity the release bound reads. It is NOT true
GPU utilisation and is labelled as a proxy throughout.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _harness as H                                                   # noqa: E402


def collect(n: int, run_s: float, switches: Dict[str, Any], tmp: Path) -> Dict[str, Any]:
    H.setup_paths()
    import arms_policy as AP

    samples: List[Dict[str, float]] = []
    _decide = AP.PolicyCoreArm.decide

    def decide(self, obs):
        try:
            mu = float(self.params.mu)
        except Exception:
            mu = float("nan")
        inflight = sum(int(v) for v in (obs.cloud.running_by_class or {}).values())
        queued = sum(int(v) for v in (obs.cloud.queued_by_class or {}).values())
        samples.append(dict(t=float(obs.now_s), mu=mu, inflight=inflight, queued=queued,
                            gpu_kv=float(obs.cloud.gpu_kv_fraction or 0.0)))
        return _decide(self, obs)

    AP.PolicyCoreArm.decide = decide
    try:
        H.run_fleet_cell(tmp / ("n%d" % n), n, run_s=run_s, seed=0, switches=switches)
    finally:
        AP.PolicyCoreArm.decide = _decide

    mus = [s["mu"] for s in samples]
    infl = [s["inflight"] for s in samples]
    kv = [s["gpu_kv"] for s in samples]
    busy_periods = sum(1 for x in infl if x >= 1)
    return dict(n_devices=n, periods=len(samples),
                mu=dict(p50=round(st.median(mus), 4), p90=round(sorted(mus)[int(0.9*len(mus))], 4),
                        min=round(min(mus), 4), max=round(max(mus), 4)),
                inflight=dict(mean=round(sum(infl)/len(infl), 4), max=max(infl),
                              periods_with_any=busy_periods,
                              fraction_of_periods_busy=round(busy_periods/len(infl), 4)),
                gpu_kv_fraction=dict(p50=round(st.median(kv), 4), max=round(max(kv), 4)),
                reading="mu is compared against an IN-FLIGHT OCCUPANCY PROXY, not true GPU "
                        "utilisation")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="4,8,16")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--switches", default="")
    a = ap.parse_args(argv)
    sw: Dict[str, Any] = {}
    for item in a.switches.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            sw[k] = float(v)
        else:
            sw[item] = True
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="covex_mu_"))
    cells = []
    for n in [int(x) for x in a.sizes.split(",") if x.strip()]:
        c = collect(n, a.run_s, sw, tmp)
        cells.append(c)
        print(json.dumps(c), flush=True)
    out = dict(check="covex_harden_mu_vs_occupancy", is_measurement=False,
               label="AUDIT of a dry run. mu beside an in-flight occupancy PROXY, to show whether "
                     "mu tracks scarcity. mu is untouched; this is a measurement, not a fix.",
               git_commit=head, switches_on={k: v for k, v in sw.items()}, cells=cells,
               _provenance=dict(git_commit=head, script="policy/audit/mu_vs_occupancy.py",
                                model="none (pol4 frozen)", device="flash CPU only",
                                n="seed 0 at %s devices for %.0f s" % (a.sizes, a.run_s),
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
