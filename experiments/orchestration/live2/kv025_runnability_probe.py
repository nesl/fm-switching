#!/usr/bin/env python3
"""ONE dry cell per process: can an arm RUN AT ALL at the 0.25x GPU KV pool?

Why this exists. The frozen-grid driver maps a *_kv0.25* tag to `--gpu-kv-tokens 15736`
(study_frozen_grid_driver_v28.sh:85), and every frozen-grid cell runs with
`--kv-capacity-enforced`. A single recall history on this workload is about 25,500 tokens, so ONE
history can exceed the WHOLE logical pool. Before a cell list is posted, each arm has to be shown
to decline gracefully rather than raise or spin.

It is `cf_pd_one_cell.py` adapted, with two differences, both deliberate:
  1. it replicates `test_hybrid.dry` inline so that `CoordState.kv_capacity_enforced` can be set
     to TRUE, which is what the live cells run and what `dry()` does not expose. Enforcement is
     the only consumer of `gpu_kv_tokens` that can evict (cstate.py:498), so a probe with it off
     would be measuring a different regime from the one posted.
  2. it catches and records any exception with its traceback, and records wall time, because
     "does it raise" and "does it spin" are the two failure modes under test.

ONE CELL PER PROCESS, for the reason cf_pd_one_cell.py documents: a second dry run inside one
process does not reproduce the first.

DIGEST RECIPE IS THE COMMITTED ONE:
sha256(json.dumps(rows without arm_version, sort_keys=True, separators=(',',':'),
default=float))[:16].

POSTED KNOBS, all of them: ratio 40:40:20, lh_req, ss2, dashcam_format epg, robot_upload
per-frame, robot_reask_mean_s 30.0, 16 devices, 1,200 s. Seeds 0, 4, 5, 6, 7 only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
ALLOWED_SEEDS = (0, 4, 5, 6, 7)
STRIP_EXTRA = ("arm_version",)

# counters that bear on "declined gracefully" versus "raised" versus "spun"
WATCH = ("budget_refusal", "release_infeasible_recall", "release_infeasible_alert",
         "over_limit_infeasible", "declined", "decline", "recall_CLOUD", "recall_DEVICE",
         "state_decisions", "decisions", "oversize", "no_capacity")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--kv-scale", type=float, default=0.25,
                    help="the GPU KV pool as a multiple of the committed 62,944 tokens: spec v6 "
                         "section 10's pre-registered memory sweep (1x, 0.5x, 0.25x).")
    ap.add_argument("--enforce", dest="enforce", action="store_true", default=True)
    ap.add_argument("--no-enforce", dest="enforce", action="store_false",
                    help="leave CoordState.kv_capacity_enforced at its default False. Used ONLY "
                         "for the positive control, where a committed dry digest has to be "
                         "reproduced and no committed dry digest was taken with enforcement on.")
    ap.add_argument("--cutoff-off", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.seed not in ALLOWED_SEEDS:
        raise SystemExit("seed %d is not allowed %s" % (a.seed, list(ALLOWED_SEEDS)))

    import arms as A
    import arms_v6c5 as VC
    import arms_v6shares as VSH
    import arms_v6state as VS
    VS.register(); VC.register(); VSH.register()
    # arms_v6cf (rung 4) is NOT registered. On origin/main `arms.py` reverted its registration
    # because `cf_protect_defer` calls `cf_objective.attainment_margin` at import time and that
    # function is in no commit; importing it here would make this probe die on a clean checkout
    # for every arm, which is the exact failure the revert note records. None of the six arms
    # probed here is a rung-4 arm.
    v6cf_registered = False
    if a.cutoff_off:
        import cf_instrument as CI
        for _n in dir(CI):
            _o = getattr(CI, _n)
            if isinstance(_o, type) and hasattr(_o, "over_budget"):
                _o.over_budget = lambda self, budget_ms=None: False

    import tempfile
    import cachekeys as CK
    import cstate as CS
    import emulator as EM
    import hybrid  # noqa: F401
    import trace as TR
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    import test_hybrid as TH
    import test_live2_coord as TLC

    kv_tokens = int(round(float(TLC.GPU_KV) * float(a.kv_scale)))
    out = {"arm": a.arm, "seed": a.seed, "n": a.n, "run_s": a.run_s, "workload": "posted",
           "kv_scale": a.kv_scale, "gpu_kv_tokens": kv_tokens,
           "gpu_kv_tokens_1x": int(TLC.GPU_KV),
           "kv_capacity_enforced": bool(a.enforce), "cutoff_off": bool(a.cutoff_off),
           "arms_v6cf_registered": v6cf_registered}
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _kw = dict(robot_question_set=POSTED["robot_question_set"],
                       ss_question_set=POSTED["ss_question_set"],
                       dashcam_format=POSTED["dashcam_format"],
                       robot_upload=POSTED["robot_upload"],
                       robot_reask_mean_s=POSTED["robot_reask_mean_s"])
            TR.write_trace(d / "t", TR.generate_trace(a.seed, a.n, POSTED["ratio"], a.run_s,
                                                      "A", **_kw))
            arm = A.make_arm(a.arm)
            arm.live2_configure(gpu_kv_tokens=kv_tokens, host_tier_gib=TLC.HOST_GIB,
                                host_tier_tokens=TLC.HOST_TOK, targets=CS.TARGETS)
            logs = Logs(d / "r").open()
            co = Live2Coordinator(arm, None, [], gpu_kv_tokens=kv_tokens,
                                  host_tier_gib=TLC.HOST_GIB, host_tier_tokens=TLC.HOST_TOK,
                                  upload_mode="A", window_s=a.run_s, drain_s=5.0, seed=a.seed,
                                  logs=logs, run_tag=CK.run_tag(a.seed, "x"), dry_run=True)
            co.st.kv_capacity_enforced = bool(a.enforce)
            out["kv_capacity_enforced_on_state"] = bool(co.st.kv_capacity_enforced)
            out["gpu_kv_tokens_on_state"] = int(co.st.gpu_kv_tokens)
            br = EmulatorBridge(co)
            br.kind = "stub"
            EM.FleetEmulator(d / "t", br, "A", realtime=False, drain_s=5.0).run(d / "r")
            logs.close()
            rows = [json.loads(l) for l in open(d / "r" / "decision.jsonl")]
            rows = [{k: v for k, v in r.items() if k not in TH.STRIP} for r in rows]
            sess = list(co.st.sessions.values())
            est = [int(getattr(x, "est_tokens", 0) or 0) for x in sess]
            built = [int(getattr(x, "built_tokens", 0) or 0) for x in sess]
            out["sessions"] = len(sess)
            out["est_tokens_max"] = max(est) if est else None
            out["built_tokens_max"] = max(built) if built else None
            out["n_sessions_est_over_pool"] = sum(1 for v in est if v > kv_tokens)
            out["n_sessions_built_over_pool"] = sum(1 for v in built if v > kv_tokens)
            out["pressure"] = dict(getattr(co.st, "pressure", None) or {})
            out["coord_counts"] = {k: v for k, v in sorted(
                (getattr(co.st, "counts", None) or {}).items())}
            st = dict(getattr(arm, "stats", None) or {})
            out["arm_stats_watch"] = {k: v for k, v in sorted(st.items())
                                      if any(w in str(k) for w in WATCH)}
            out["arm_stats_all_keys"] = sorted(st.keys())
            rr = [{k: v for k, v in r.items() if k not in STRIP_EXTRA} for r in rows]
            out["rows"] = len(rr)
            out["digest"] = hashlib.sha256(json.dumps(
                rr, sort_keys=True, separators=(",", ":"), default=float).encode()
            ).hexdigest()[:16]
            kinds = {}
            for r in rr:
                kinds[str(r.get("kind"))] = kinds.get(str(r.get("kind")), 0) + 1
            out["decision_kinds"] = dict(sorted(kinds.items()))
        out["raised"] = None
        out["ran"] = True
    except BaseException as e:                                    # noqa: BLE001
        out["ran"] = False
        out["raised"] = {"type": type(e).__name__, "msg": str(e)[:2000],
                         "traceback": traceback.format_exc()[-4000:]}
    out["wall_s"] = round(time.time() - t0, 2)
    s = json.dumps(out, default=float)
    if a.out:
        Path(a.out).write_text(s)
    print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
