#!/usr/bin/env python3
"""ONE dry cell per process for the C5 attribution proofs. Driven by c5attr_proofs.py.

WHY ONE CELL PER PROCESS. A second dry run inside one process does not reproduce the first
(covex-v6-state gave 15,871 rows then 16,109, with state_decisions moving 44,300 to 45,337; cause
open, ruled out are the planner wall-clock limit, PYTHONHASHSEED and the registration context).
Separate processes with identical setup DO reproduce exactly, so every digest claim here is made
across processes.

WHY THERE IS A TRIP INSTRUMENT (`--trip-s`). C5's AIMD halves when the EWMA of monitor
first-token time exceeds 0.8 s. A dry cell's monitor service time is the committed curve's
CONSTANT 0.3950 s (costs.episodic_cloud_latency_s('32BI', 1, 25)), so the EWMA never crosses the
trip, `c5_decrease` is 0, and the cap never leaves 8. The attribution rule is therefore
UNEXERCISED on an unmodified dry cell BY CONSTRUCTION, and a null there would prove nothing about
it. `--trip-s X` replaces the dry monitor service time with X so the mechanism is reachable. It is
a PROOF INSTRUMENT, never a measurement: it is applied identically to both sides of every
comparison, and no latency from a run with it on may be quoted as a latency.

`--cutoff-off` patches cf_instrument's wall-clock abandonment off, so a digest is a property of
the arm and not of the machine's load. Live cells keep it ON (D99 (3)).
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--trip-s", type=float, default=0.0,
                    help="dry monitor service seconds; 0 keeps the committed curve")
    ap.add_argument("--lat-scale", type=float, default=1.0,
                    help="scale the EPISODIC ttft EWMA the arm reads; the SURGICAL trip "
                         "instrument, because it leaves the engine, the workload and the "
                         "episodic in-flight occupancy exactly as committed")
    ap.add_argument("--force-flag", choices=("on", "off"), default=None,
                    help="force c5_attr_self_released on the arm, for the negative control")
    ap.add_argument("--cutoff-off", action="store_true")
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--defaults", action="store_true",
                    help="test_hybrid.dry's own defaults instead of the POSTED workload knobs")
    a = ap.parse_args()

    import arms as A                                                   # noqa: PLC0415
    import arms_v6c5 as VC                                             # noqa: PLC0415
    import arms_v6state as VS                                          # noqa: PLC0415
    VS.register()
    VC.register()
    if a.cutoff_off:
        import cf_instrument as CI                                     # noqa: PLC0415
        for _n in dir(CI):
            _o = getattr(CI, _n)
            if isinstance(_o, type) and hasattr(_o, "over_budget"):
                _o.over_budget = lambda self, budget_ms=None: False
    if a.lat_scale != 1.0:
        # WHY THIS INSTRUMENT AND NOT --trip-s. Raising the dry monitor service time does make the
        # trip reachable, but it also keeps every monitor in flight for that long, so the episodic
        # in-flight count saturates the cap and a cap of 4 and a cap of 8 hold the SAME set: the
        # trajectory moves and no decision does. Scaling only the EWMA the arm READS leaves the
        # service times, the occupancy and the workload exactly as committed.
        import cstate as CS                                            # noqa: PLC0415
        _oe = CS.CoordState.ewma
        _sc = float(a.lat_scale)

        def _ew(self, cls, v, _o=_oe, _s=_sc):
            return _o(self, cls, (None if v is None else float(v) * _s) if cls == "episodic" else v)
        CS.CoordState.ewma = _ew
    if a.trip_s > 0.0:
        import coordinator as CO                                       # noqa: PLC0415
        _orig = CO.Live2Coordinator._dry_service_s
        _trip = float(a.trip_s)

        def _svc(self, sub, _o=_orig, _t=_trip):
            return _t if sub.kind == "monitor" else _o(self, sub)
        CO.Live2Coordinator._dry_service_s = _svc

    cap_trace = []
    # the episodic IN-FLIGHT count the cap is compared against (`budget = cap - epi`). Recorded
    # because it is what decides whether a cap difference can reach a decision at all: if epi
    # already exceeds the ceiling, a cap of 4 and a cap of 8 hold the same set.
    epi_seen: list = []

    def _patch(arm):
        core = arm
        seen = set()
        while core is not None and id(core) not in seen:
            seen.add(id(core))
            nxt = core.__dict__.get("_rules") or core.__dict__.get("_base")
            if nxt is None:
                break
            core = nxt
        if a.force_flag is not None:
            want = a.force_flag == "on"
            o = arm
            seen = set()
            while o is not None and id(o) not in seen:
                seen.add(id(o))
                o.c5_attr_self_released = want
                o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        _aimd = core._aimd

        def aimd(obs, _f=_aimd, _c=core):
            before = _c.cap
            epi_seen.append(int((getattr(obs.cloud, "running_by_class", None) or {}).get(
                "episodic", 0)))
            _f(obs)
            if _c.cap != before or not cap_trace or cap_trace[-1][1] != _c.cap:
                cap_trace.append((round(float(obs.now_s), 4), int(_c.cap)))
        core._aimd = aimd
        _patch.core = core

    import test_hybrid as TH                                           # noqa: PLC0415
    kw = dict() if a.defaults else {k: v for k, v in POSTED.items()
                                    if k in ("dashcam_format", "robot_upload",
                                             "robot_reask_mean_s")}
    cell = dict(ratio="50:50", robot_question_set="eval", ss_question_set="ss1") if a.defaults \
        else dict(ratio=POSTED["ratio"], robot_question_set=POSTED["robot_question_set"],
                  ss_question_set=POSTED["ss_question_set"])
    rows, st = TH.dry(a.arm, a.seed, a.n, run_s=a.run_s, ratio=cell["ratio"], patch=_patch,
                      robot_question_set=cell["robot_question_set"],
                      ss_question_set=cell["ss_question_set"], **kw)
    rows = list(rows or [])
    rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
    digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                       default=float).encode()).hexdigest()[:16]
    if a.rows_out:
        Path(a.rows_out).write_text(json.dumps(rr, default=float))
    st = dict(st or {})
    core = getattr(_patch, "core", None)
    # the C5 counters live on the HybridArm that owns `self.cap`, not on the outer wrapper whose
    # Counter `test_hybrid.dry` returns
    cst = dict(getattr(core, "stats", {}) or {})
    out = {
        "arm": a.arm, "seed": a.seed, "n": a.n, "run_s": a.run_s,
        "workload": "defaults" if a.defaults else "posted",
        "trip_s": a.trip_s, "lat_scale": a.lat_scale, "force_flag": a.force_flag, "cutoff_off": bool(a.cutoff_off),
        "digest": digest, "rows": len(rows),
        "flag_on_the_cap_owner": bool(getattr(core, "c5_attr_self_released", False)),
        "cap_adjustments": len(cap_trace),
        "episodic_in_flight": ({} if not epi_seen else {
            "p50": sorted(epi_seen)[len(epi_seen) // 2],
            "p90": sorted(epi_seen)[int(0.9 * len(epi_seen))],
            "max": max(epi_seen),
            "share_at_or_above_the_ceiling_8": round(
                sum(1 for v in epi_seen if v >= 8) / len(epi_seen), 4),
            "share_at_or_above_the_floor_4": round(
                sum(1 for v in epi_seen if v >= 4) / len(epi_seen), 4)}),
        "cap_trace_head": cap_trace[:20],
        "cap_series_digest": hashlib.sha256(
            json.dumps(cap_trace, default=float).encode()).hexdigest()[:16],
        "cap_final": (cap_trace[-1][1] if cap_trace else None),
        "cap_min": (min(c for _t, c in cap_trace) if cap_trace else None),
        "stats": {k: (cst.get(k) if k in cst else st.get(k)) for k in (
            "c5_decrease", "c5_increase", "c5_dash_held", "decisions", "state_decisions",
            "c5_attr_suppressed_decrease", "c5_attr_slow_all_self_released",
            "c5_attr_slow_mixed", "c5_attr_trip_without_slow_evidence")},
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
