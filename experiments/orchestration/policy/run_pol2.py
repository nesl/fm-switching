#!/usr/bin/env python3
"""StudyPOL2-build: build the v3 policy core, run its tests, measure M4 and exercise the T0
harness on a synthetic replay. CPU only; no GPU, no model server, no inference.

Nothing here tunes a parameter or evaluates a policy. The outputs are the spec-to-code map, the
ambiguity list, the decision-time measurement and the T0 dry run.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/orchestration"))
sys.path.insert(0, str(ROOT / "experiments/lib"))

from policy import (Coordinator, Demand, Device, Flags, HistoryBelief, Job, Link, Params,
                    PlaceholderEngine, Rollout, Fleet, PendingItem, load_profiles)
from policy import m4 as M4
from policy import spec_map as SM
from policy.t0_harness import T0Harness, synthetic_dataset

OUT = ROOT / "results/orchestration/pol2"


def build_fleet(pf, n_pending: int, n_devices: int = 4) -> Fleet:
    f = Fleet(t=0.0)
    for i in range(n_devices):
        link = Link(bandwidth_bytes_s=pf.uplink_bytes_per_s(), rtt_s=pf.rtt_s())
        d = Device(device_id="d%d" % i, link=link,
                   history={"RICH": HistoryBelief(rep="RICH", size_tokens=11_000)},
                   qtype="counting_objects_events")
        d.demand = Demand().prior_from_profiles(pf)
        f.add_device(d)
    for j in range(n_pending):
        did = "d%d" % (j % n_devices)
        if j % 2 == 0:
            f.pending.append(PendingItem(item_id="call%d" % j, kind="episode_call", device=did,
                                         due_at=0.0, frames=1))
        else:
            f.pending.append(PendingItem(item_id="piece%d" % j, kind="rc_piece", device=did,
                                         due_at=0.0, deadline=10.0, tokens=2048,
                                         job_id="j%d" % j))
    return f


def main() -> int:
    from _provenance import stamp
    OUT.mkdir(parents=True, exist_ok=True)
    pf = load_profiles()
    params = Params()
    params.gpu_kv_capacity_tokens = 200_000
    params.host_kv_capacity_tokens = 2_000_000
    flags = Flags()
    engine = PlaceholderEngine(profiles=pf, gpu_kv_tokens=200_000, host_kv_tokens=2_000_000)
    ro = Rollout(pf, params, flags, engine)
    co = Coordinator(pf, params, flags, engine, ro)

    # ---- the test suite
    loader = unittest.TestLoader()
    suite = loader.discover(str(HERE / "tests"), top_level_dir=str(ROOT / "experiments/"
                                                                   "orchestration"))
    res = unittest.TextTestRunner(verbosity=0, stream=open("/dev/null", "w")).run(suite)
    tests = dict(run=res.testsRun, failures=len(res.failures), errors=len(res.errors),
                 ok=res.wasSuccessful(),
                 command="cd experiments/orchestration && python3 -m unittest discover "
                         "-s policy/tests -t .")
    print("tests: %d run, %d failures, %d errors" % (tests["run"], tests["failures"],
                                                     tests["errors"]))
    if not tests["ok"]:
        print("the test suite must pass before the measurements are written")
        return 1

    # ---- the spec map, the ambiguities, the flag audit
    smap = dict(check=SM.check(), spec_map=SM.SPEC_MAP, ambiguities=SM.AMBIGUITIES,
                flags=dict(defaults=flags.as_dict(), conditional=Flags.ENABLING_CONDITION),
                parameters=dict(values=params.as_dict(),
                                provenance={k: v for k, v in
                                            __import__("policy").PROVENANCE.items()},
                                placeholders=params.placeholders()),
                engine=engine.describe(), tests=tests,
                decision_latency=co.decision_latency,
                query_paths=dict(
                    default="complete",
                    exception="question_first",
                    exception_conditions=["the request is an RC query",
                                          "its unsent history exceeds "
                                          "Params.question_first_history_bytes",
                                          "the device's uplink already carries higher-value "
                                          "traffic"],
                    delivered_delay=dict(
                        complete="up(question) + up(payload) + compute + down",
                        question_first="up(question) + decision latency (M4) + one control "
                                       "round trip + up(payload) + compute + down"),
                    on_decline="the query is DISCARDED: no pending item, no job, no in-flight "
                               "work, and the device's answer stands",
                    file_discrepancy=("research/POLICY_SPEC_v3_1_ADDENDUM.md still carries the "
                                      "superseded 'METADATA escalation request' wording in A2; "
                                      "the code follows the user's revision of 2026-11-15, "
                                      "recorded as ambiguity A20")),
                profiles=dict(path=pf.path, u_sh_device=pf.u_sh_device(),
                              omega=pf.raw["class_weights_omega"]["omega"],
                              frames_warning=pf.frames_warning()))
    smap["_provenance"] = stamp(script="policy/run_pol2.py", model=None, device="cpu",
                                n=len(SM.SPEC_MAP), args=None)
    (OUT / "pol2_spec_map.json").write_text(json.dumps(smap, indent=1, default=str))
    print("spec map: %d sections, %d ambiguities, all symbols resolve=%s"
          % (smap["check"]["n_sections"], smap["check"]["n_ambiguities"], smap["check"]["ok"]))

    # ---- M4
    m4 = M4.measure_decision_time(ro, build_fleet(pf, 1),
                                  lambda n: build_fleet(pf, n),
                                  horizons=(0.5, 0.75, 1.0),
                                  pending_sizes=(1, 4, 16, 64), repeats=15)
    m4["ghat"] = M4.measure_ghat_time(co, build_fleet(pf, 1))
    for k, v in m4["ghat"]["rows"].items():
        print("  M4 Ghat %-16s p50 %.3f ms" % (k, 1e3 * v["p50_s"]))
    m4["_provenance"] = stamp(script="policy/run_pol2.py --m4", model=None, device="cpu",
                              n=len(m4["rows"]), args=None)
    (OUT / "pol2_m4_decision_time.json").write_text(json.dumps(m4, indent=1, default=float))
    for r in m4["rows"]:
        if r["pending_items"] in (1, 64):
            print("  M4 H=%.2f s, %2d pending: one DeltaJ p50 %.2f ms, a full release loop "
                  "%.1f ms" % (r["horizon_s"], r["pending_items"], 1e3 * r["p50_s"],
                               1e3 * r["per_release_loop_s"]))

    # ---- A6 demonstration: what the KV-pool model does to a deferral decision
    from policy.kvpool import prefix_id_for
    from policy.rollout import delta_j
    from policy.state import Job, PendingItem as PI

    def a6_case(capacity, mu, rivals):
        pp = Params()
        pp.gpu_kv_capacity_tokens = capacity
        pp.host_kv_capacity_tokens = 2_000_000
        pp.H, pp.mu = 1.0, mu
        ro2 = Rollout(pf, pp, flags, engine)
        f = build_fleet(pf, 0, n_devices=1)
        j = Job(job_id="j0", device="d0", qtype="counting_objects_events", rep="RICH",
                deadline=10.0, admitted_at=0.0, pieces_total=6, pieces_done=3,
                tokens_per_piece=2048)
        f.jobs[j.job_id] = j
        f.pending.append(PI(item_id="next", kind="rc_piece", device="d0", due_at=0.0,
                            deadline=10.0, tokens=2048, job_id="j0"))
        for i in range(rivals):
            f.pending.append(PI(item_id="rival%d" % i, kind="rc_piece", device="d0", due_at=0.0,
                                deadline=9.0, tokens=4000, job_id="rival%d" % i))
        on = delta_j(ro2, f, dict(kind="defer", item_id="next"))["delta_j"]
        r_def = ro2.run(f, exclude=["next"])
        r_rel = ro2.run(f, release_now=["next"])
        pp.kv_pool_model = False
        off = delta_j(ro2, f, dict(kind="defer", item_id="next"))["delta_j"]
        pp.kv_pool_model = True
        return dict(capacity_tokens=capacity, mu=mu, n_rivals=rivals,
                    delta_j_defer_pool_on=on, delta_j_defer_pool_off=off,
                    p_loss_if_deferred=[v["p_loss"] for v in
                                        r_def.detail["prefix_risk"].values()],
                    p_loss_if_released=[v["p_loss"] for v in
                                        r_rel.detail["prefix_risk"].values()],
                    expected_restore_s=[v["extra_work_s"] for v in
                                        r_def.detail["prefix_risk"].values()],
                    kv=r_def.kv)

    sizer = Coordinator(pf, params, flags, engine, ro)
    fs = build_fleet(pf, 0, n_devices=1)
    jj = Job(job_id="sz", device="d0", qtype="counting_objects_events", rep="RICH",
             deadline=10.0, admitted_at=0.0, pieces_total=8, pieces_done=0,
             tokens_per_piece=1024)
    fs.jobs[jj.job_id] = jj
    params.gpu_kv_capacity_tokens = 200_000
    a6 = dict(
        high_pressure=a6_case(12_000, 1.0, 6),
        zero_pressure=a6_case(100_000_000, 1.0, 0),
        gpu_price_zero=a6_case(12_000, 0.0, 6),
        piece_sizing=sizer.choose_piece_size(fs, jj),
        p_host=dict(value=params.p_host, provenance=__import__("policy").PROVENANCE["p_host"]),
        survival_curve=dict(supplied=params.survival_curve is not None,
                            provenance=__import__("policy").PROVENANCE["survival_curve"]),
        reading=("A6's restore work reaches a release decision through spec 5.3's backlog "
                 "price. Under pressure the pool predicts the prefix is fully lost if the piece "
                 "is deferred and fully safe if it is released, which is the asymmetry A6 "
                 "exists to create. At zero pressure every A6 term is exactly zero and the "
                 "result equals the pre-A6 path. With mu at its PLACEHOLDER zero the channel is "
                 "silent and A6 acts only through feasibility and the memory decision."))
    a6["_provenance"] = stamp(script="policy/run_pol2.py --a6", model=None, device="cpu",
                              n=3, args=None)
    (OUT / "pol2_a6_prefix_survival.json").write_text(json.dumps(a6, indent=1, default=float))
    print("A6: deferring under pressure %+.4f with the pool, %+.4f without; at zero pressure "
          "%+.4f and %+.4f (identical)"
          % (a6["high_pressure"]["delta_j_defer_pool_on"],
             a6["high_pressure"]["delta_j_defer_pool_off"],
             a6["zero_pressure"]["delta_j_defer_pool_on"],
             a6["zero_pressure"]["delta_j_defer_pool_off"]))

    # ---- T0 dry run
    params.H = 0.75
    f = build_fleet(pf, 8)
    ds = synthetic_dataset(ro, f, list(f.pending), measured_overhead_s=0.0)
    t0 = T0Harness().run(ds)
    t0["dataset_note"] = ds["note"]
    t0["refusal_rule"] = ("T0Harness.run raises HoldoutRefused on any split named holdout, eval "
                          "or test, and on any unrecognized split name; the refusal is not "
                          "overridable")
    t0["_provenance"] = stamp(script="policy/run_pol2.py --t0", model=None, device="cpu",
                              n=t0.get("n", 0), args=None)
    (OUT / "pol2_t0_harness_dryrun.json").write_text(json.dumps(t0, indent=1, default=float))
    print("T0 dry run on the synthetic replay: %s over %d cases (the engine model is NOT "
          "validated by this)" % (t0["verdict"], t0["n"]))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
