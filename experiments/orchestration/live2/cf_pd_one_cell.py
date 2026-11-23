#!/usr/bin/env python3
"""ONE dry cell per process for the protect-and-defer proofs. Driven by `cf_pd_proofs.py`.

WHY ONE CELL PER PROCESS. A second dry run inside one process does not reproduce the first
(covex-v6-state gave 15,871 rows then 16,109, with state_decisions moving 44,300 to 45,337; cause
open, ruled out are the planner wall-clock limit, PYTHONHASHSEED and the registration context).
Separate processes with identical setup DO reproduce exactly, so every digest claim is made
across processes.

THE DIGEST RECIPE IS THE COMMITTED ONE AND IS NOT A NEW ONE. `sha256(json.dumps(rows without
arm_version, sort_keys=True, separators=(',',':'), default=float))[:16]`, over
`test_hybrid.dry`'s rows, with the POSTED workload knobs forwarded and the planner wall-clock
cutoff patched off - byte for byte what `c5attr_one_cell.py` does. A digest is comparable ONLY
within one recipe, and a different serialisation produced a phantom discrepancy in this project
today. PROVED rather than asserted: this runner reproduces the COMMITTED digests of
`covex-v6-state-uo` (9a4be873eb3c5fba, 14,218 rows) and `covex-v6-base` (af8befb9420ad86a) from
`results/orchestration/live2/frozen_test/c5attr_digest_proofs.json`, which is the POSITIVE
CONTROL on the check itself: if a known-good committed arm fails it, the check is broken and not
the arm.

POSTED KNOBS, all of them, because a dry run on the defaults is a run of a different workload:
ratio 40:40:20, lh_req, ss2, dashcam_format epg, robot_upload per-frame, robot_reask_mean_s 30.0,
16 devices, 1,200 s. Seeds 0, 4, 5, 6 and 7 only; never 1 to 3, never HOLDOUT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
ALLOWED_SEEDS = (0, 4, 5, 6, 7)

PD_STAT_KEYS = (
    "pd_decisions", "pd_decisions_state", "pd_decisions_request",
    "pd_state_defers", "pd_state_chunks", "pd_request_defers", "pd_protects",
    "pd_protect_unexpressible_session_busy", "pd_harm_n", "pd_harm_zero",
    "pd_harm_over_bar", "pd_harm_micro_sum", "pd_harm_micro_max",
    "pd_deferred_to_guard_epochs", "pd_other_skipped_over_limit",
    "pd_no_kv_pool_configured",
    "state_decisions", "state_touch_emitted", "decisions", "c5_dash_held",
    "recall_CLOUD", "over_limit_infeasible",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--cutoff-off", action="store_true")
    ap.add_argument("--kv-scale", type=float, default=1.0,
                    help="the GPU KV pool as a multiple of the committed 62,944 tokens. This is "
                         "spec v6 section 10's PRE-REGISTERED memory sweep (1x, 0.5x, 0.25x), "
                         "not an invented instrument, and it is applied identically to both "
                         "sides of every comparison it appears in.")
    ap.add_argument("--diag-epoch-cache-key", action="store_true",
                    help="DIAGNOSTIC INSTRUMENT, never a measurement and never on in a scorable "
                         "cell. `arms_v6state.V6StateArm._queued_behind` caches its pending-work "
                         "rows under `key = int(obs.epoch) if isinstance(obs.epoch, int) else "
                         "id(obs)`; `obs.epoch` is one of the EPOCH_KINDS STRINGS, so the key is "
                         "always `id(obs)`, a MEMORY ADDRESS. CPython reuses addresses, so when a "
                         "new Observation lands where the last one was, the cache is not "
                         "invalidated and the previous epoch's rows are reused - which makes a "
                         "rung-2 arm's decisions depend on allocation history. This flag forces "
                         "the cache to rebuild once per decision period, which is what the key "
                         "was meant to do, and is how the hypothesis is tested without editing "
                         "a file this session does not own.")
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--pd-out", default=None, help="where to write the per-decision pd records")
    a = ap.parse_args()
    if a.seed not in ALLOWED_SEEDS:
        raise SystemExit("seed %d is not one of the allowed seeds %s (never 1 to 3, never "
                         "HOLDOUT)" % (a.seed, list(ALLOWED_SEEDS)))

    import arms as A                                                   # noqa: PLC0415
    import arms_v6c5 as VC                                             # noqa: PLC0415
    import arms_v6cf as VCF                                            # noqa: PLC0415
    import arms_v6shares as VSH                                        # noqa: PLC0415
    import arms_v6state as VS                                          # noqa: PLC0415
    VS.register()
    VC.register()
    VSH.register()
    VCF.register()
    if a.cutoff_off:
        import cf_instrument as CI                                     # noqa: PLC0415
        for _n in dir(CI):
            _o = getattr(CI, _n)
            if isinstance(_o, type) and hasattr(_o, "over_budget"):
                _o.over_budget = lambda self, budget_ms=None: False

    if a.diag_epoch_cache_key:
        import arms_v6state as _VS2                                    # noqa: PLC0415
        _orig_qb = _VS2.V6StateArm._queued_behind

        def _qb(self, obs, session_id, _o=_orig_qb):
            if getattr(self, "_diag_last_now", None) != float(obs.now_s):
                self._diag_last_now = float(obs.now_s)
                self._q_cache_key = None          # rebuild once per decision period
            return _o(self, obs, session_id)
        _VS2.V6StateArm._queued_behind = _qb

    kv_tokens = None
    if a.kv_scale != 1.0:
        # `test_hybrid.dry` does `from test_live2_coord import GPU_KV` INSIDE the function, so
        # patching the source module is what reaches it; patching test_hybrid would not.
        # test_hybrid first, because it is what puts live2/tests on sys.path.
        import test_hybrid as _TH0                                     # noqa: F401,PLC0415
        import test_live2_coord as TLC                                 # noqa: PLC0415
        kv_tokens = int(round(float(TLC.GPU_KV) * float(a.kv_scale)))
        TLC.GPU_KV = kv_tokens

    held = {}

    def _patch(arm):
        held["arm"] = arm

    import test_hybrid as TH                                           # noqa: PLC0415
    kw = {k: v for k, v in POSTED.items()
          if k in ("dashcam_format", "robot_upload", "robot_reask_mean_s")}
    rows, st = TH.dry(a.arm, a.seed, a.n, run_s=a.run_s, ratio=POSTED["ratio"], patch=_patch,
                      robot_question_set=POSTED["robot_question_set"],
                      ss_question_set=POSTED["ss_question_set"], **kw)
    rows = list(rows or [])
    rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
    digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                       default=float).encode()).hexdigest()[:16]
    if a.rows_out:
        Path(a.rows_out).write_text(json.dumps(rr, default=float))
    st = dict(st or {})
    arm = held.get("arm")
    out = {
        "arm": a.arm, "seed": a.seed, "n": a.n, "run_s": a.run_s, "workload": "posted",
        "cutoff_off": bool(a.cutoff_off), "digest": digest, "rows": len(rows),
        "kv_scale": a.kv_scale, "gpu_kv_tokens": kv_tokens,
        "diag_epoch_cache_key": bool(a.diag_epoch_cache_key),
        "stats": {k: st.get(k) for k in PD_STAT_KEYS},
        # every pd_ counter, including the GATE counters, because which gate a decision stopped
        # at is the whole diagnosis when the harm is never reached
        "pd_counters": {k: v for k, v in sorted(st.items()) if str(k).startswith("pd_")},
    }
    if arm is not None and hasattr(arm, "pd_switch_report"):
        out["switch"] = arm.pd_switch_report()
        out["harm_distribution"] = arm.pd_harm_distribution()
        out["base_key"] = getattr(arm, "pd_base_key", None)
        out["controls"] = {"harm_zero": getattr(arm, "_pd_control_harm_zero", None),
                           "margin_huge": getattr(arm, "_pd_control_margin_huge", None)}
        out["bar_reading"] = getattr(arm, "_pd_bar_reading", None)
        out["w_source"] = getattr(arm, "_pd_w_source", None)
        import cf_protect_defer as PD                                  # noqa: PLC0415
        tr = getattr(arm, "pd_trace_kept", None)
        cr = getattr(arm, "pd_trace_crossed", None)
        out["traced_decision"] = (PD.trace_lines(tr) if tr else None)
        out["traced_decision_record"] = tr
        out["traced_bar_crossing"] = (PD.trace_lines(cr) if cr else None)
        out["traced_bar_crossing_record"] = cr
        if a.pd_out:
            Path(a.pd_out).write_text(json.dumps(
                {"harms": getattr(arm, "pd_harms", []),
                 "decisions": getattr(arm, "pd_decisions", []),
                 "traced_decision_record": tr,
                 "traced_bar_crossing_record": cr}, default=float))
    print(json.dumps(out, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
