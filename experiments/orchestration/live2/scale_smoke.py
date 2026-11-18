#!/usr/bin/env python3
"""StudyLIVE2-coord test (i): the scale smoke. CPU only, the existing CPU stub.

64 devices (32 dashcam + 32 robot), about 3 minutes, tight memory, mode A for `policy-core` and
`edf`, and mode B for `policy-core`. It reports decision latency p50 / p99, coordinator CPU use
and request rate.

WHAT THIS IS NOT. It is not a capacity result and not a latency result. The CPU stub is ONE FIFO
server drawing committed service times, so at 64 devices it saturates by construction and the
queue it builds is the fixture's, not an engine's. The numbers that mean anything here are the
COORDINATOR'S OWN: how long a decision takes, how much CPU the loop uses, and how many requests
it can put on the wire. Bodies are sent with uuid-only frame references (no image bytes), so the
request rate is not a bytes-on-the-wire figure either.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                      # noqa: E402
import cachekeys as CK                                                # noqa: E402
import calib as CALIB                                                 # noqa: E402
import cstate as CS                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from backend import Live2Backend                                      # noqa: E402
from coordinator import Live2Coordinator, Logs                        # noqa: E402
import fake_server as FS                                              # noqa: E402

GPU_KV = 62_944          # D76, the H100 KV pool round 1 runs at
HOST_TIGHT_GIB = 27.0    # D76 TIGHT
HOST_TIGHT_TOKENS = 48_000


def cell(arm_name: str, out: Path, *, mode: str = "A", window_s: float = 180.0,
         n_dashcam: int = 32, n_robot: int = 32, seed: int = 1,
         max_wall_s: float = 420.0) -> dict:
    kw = dict(h_s=1.0) if arm_name == "policy-core" else {}
    arm = A.make_arm(arm_name, **kw)
    cfg = dict(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_TIGHT_GIB,
               host_tier_tokens=HOST_TIGHT_TOKENS, targets=CS.TARGETS)
    if arm_name == "policy-core":
        out.mkdir(parents=True, exist_ok=True)
        cfg["calibration_knots_path"] = CALIB.write_knots(CALIB.load_map(),
                                                          out / "calibration_knots.json")
    arm.live2_configure(**cfg)
    tr = T.synthetic(n_dashcam=n_dashcam, n_robot=n_robot, duration_s=window_s, seed=seed,
                     upload_mode=mode, frames_dir=None)
    T.require_fake_server(tr, "fake")
    logs = Logs(out).open()
    with FS.serve(0) as url:
        be = Live2Backend(url, workers=64, record_bodies=False)
        resp = T.pull_responder(tr.get("frames_by_instant") or {}) if mode == "B" else None
        co = Live2Coordinator(arm, be, tr["events"], gpu_kv_tokens=GPU_KV,
                              host_tier_gib=HOST_TIGHT_GIB,
                              host_tier_tokens=HOST_TIGHT_TOKENS, upload_mode=mode,
                              window_s=window_s, drain_s=15.0, seed=seed, logs=logs,
                              run_tag=CK.run_tag(seed, arm_name), targets=CS.TARGETS,
                              on_pull=resp, max_wall_s=max_wall_s)
        res = co.run()
        be.close()
    logs.close()
    res.update(cell=f"{arm_name}/mode{mode}", n_dashcam=n_dashcam, n_robot=n_robot,
               fairness_digest=tr["fairness_digest"],
               live1_trace_digest=tr.get("live1_trace_digest"),
               trace_label=tr["label"], is_measurement=False)
    from _provenance import stamp
    res["_provenance"] = stamp(script="scale_smoke.py", model="none", device="flash_cpu",
                               n=res["n_requests"], seed=seed)
    (out / "result.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str)
                                     + "\n")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "results/orchestration/live2/coord/scale"))
    ap.add_argument("--window-s", type=float, default=180.0)
    ap.add_argument("--n-dashcam", type=int, default=32)
    ap.add_argument("--n-robot", type=int, default=32)
    ap.add_argument("--max-wall-s", type=float, default=420.0)
    a = ap.parse_args(argv)
    root = Path(a.out)
    rows = []
    for arm_name, mode in (("policy-core", "A"), ("edf", "A"), ("policy-core", "B")):
        out = root / f"{arm_name}_mode{mode}"
        r = cell(arm_name, out, mode=mode, window_s=a.window_s, n_dashcam=a.n_dashcam,
                 n_robot=a.n_robot, max_wall_s=a.max_wall_s)
        rows.append({k: r.get(k) for k in
                     ("cell", "n_devices", "n_opportunities", "n_requests", "n_decisions",
                      "decision_latency_ms", "cpu_s", "wall_s", "cpu_percent",
                      "request_rate_per_s", "epoch_overruns", "max_epoch_lag_s", "n_errors",
                      "decision_period_s", "n_pulls", "wall_guard_hit",
                      "virtual_t_reached_s")})
        print(json.dumps(rows[-1], default=str), flush=True)
    from _provenance import stamp
    (root / "scale_smoke.json").write_text(json.dumps(
        dict(is_measurement=False, cells=rows,
             _provenance=stamp(script="scale_smoke.py", model="none",
                               device="flash_cpu"),
             note="CPU stub, SYNTHETIC trace, uuid-only frame references. Coordinator-side "
                  "figures only; not a capacity or latency result."),
        indent=1, sort_keys=True, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
