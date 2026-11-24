#!/usr/bin/env python3
"""Hit 7 (user ruling 2026-11-23): Step 2b for SimpleStream's fitted window, ONE dry cell per process.

Runs `test_hybrid.dry`'s committed recipe (posted knobs: 16 devices, seed 4, 1,200 s, 40:40:20, lh_req,
ss2, EP-G, per-frame, re-ask 30, planner cutoff patched off as in cf_pd_one_cell.py) for one arm, but
keeps the run directory, so it can report what the decision digest cannot see: frames per robot RECENT
send (from the request log's mm_uuids / frame refs) and the coordinator's window counters. Run it in the
BEFORE and AFTER trees; it prints one JSON line.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"), str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)


def main() -> None:
    arm_name = sys.argv[1]
    import cf_instrument as CI                         # the committed cutoff patch (cf_pd_one_cell.py:95-100)
    for _n in dir(CI):
        _o = getattr(CI, _n)
        if isinstance(_o, type) and hasattr(_o, "over_budget"):
            _o.over_budget = lambda self, budget_ms=None: False
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import emulator as EM
    import hybrid  # noqa: F401
    import trace as TR
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK
    import test_hybrid as TH
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        kw = dict(robot_question_set=POSTED["robot_question_set"], ss_question_set=POSTED["ss_question_set"],
                  dashcam_format=POSTED["dashcam_format"], robot_upload=POSTED["robot_upload"],
                  robot_reask_mean_s=POSTED["robot_reask_mean_s"])
        TR.write_trace(d / "t", TR.generate_trace(4, 16, POSTED["ratio"], 1200.0, "A", **kw))
        arm = A.make_arm(arm_name)
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                            targets=CS.TARGETS)
        logs = Logs(d / "r").open()
        co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                              host_tier_tokens=HOST_TOK, upload_mode="A", window_s=1200.0, drain_s=5.0,
                              seed=4, logs=logs, run_tag=CK.run_tag(4, "x"), dry_run=True)
        br = EmulatorBridge(co)
        br.kind = "stub"
        EM.FleetEmulator(d / "t", br, "A", realtime=False, drain_s=5.0).run(d / "r")
        logs.close()
        rows = [json.loads(l) for l in open(d / "r" / "decision.jsonl")]
        rr = [{k: v for k, v in r.items() if k not in TH.STRIP and k != "arm_version"} for r in rows]
        digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                           default=float).encode()).hexdigest()[:16]
        frames = Counter()
        files = sorted(p.name for p in (d / "r").iterdir())
        req = d / "r" / "request.jsonl"
        if req.exists():
            for line in open(req):
                r = json.loads(line)
                if str(r.get("device_id", "")).startswith("robo"):
                    n = len(r.get("mm_uuids") or r.get("frame_refs") or [])
                    frames[n] += 1
    c = dict(co.counts)
    print(json.dumps(dict(arm=arm_name, digest=digest, rows=len(rows), run_files=files,
                          robot_request_frames=dict(sorted(frames.items())),
                          recent_window_sends=c.get("recent_window_sends", 0),
                          recent_window_s_sends=c.get("recent_window_s_sends", 0),
                          recent_window_s_frames=c.get("recent_window_s_frames", 0)), default=float))


if __name__ == "__main__":
    main()
