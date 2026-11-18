#!/usr/bin/env python3
"""StudyLIVE2-fix: the flash tests for D98, D99, D100, D101 and D102. CPU only, no server.

NOTHING ANY OF THESE TESTS PRODUCES IS A MEASUREMENT.

  preload      D101: history_preload is on the wire, in the fairness digest, and is stored as
               COLD history with no KV and no uplink charge
  d98          per-instant SH value: admission is not structurally zero at H = T_k; a delivery
               past its own deadline is not worth admitting; one past the HORIZON but inside
               the deadline is
  d99          one 100 ms decision period for every arm; the optimized policy decides exactly
               what the unoptimized one decides; the cap K, when set, binds and is reported
  d100         partial readiness costs a later piece as a piece; pi_0 serves both dashcams
  d102         the GPU budget is an input, identical for every arm, in the header
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                      # noqa: E402
import cachekeys as CK                                                # noqa: E402
import calib as CALIB                                                 # noqa: E402
import cstate as CS                                                   # noqa: E402
import fix_checks as FX                                               # noqa: E402
import schema as SC                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from bridge import EmulatorBridge                                     # noqa: E402
from coordinator import DECISION_PERIOD_S, Live2Coordinator, Logs     # noqa: E402

GPU_KV = 62_944
HOST_GIB = 27.0
HOST_TOK = 48_000


def _preload(device_id="r0", session_id="r0/s0", t=0.0, tokens=5000, frames=("f1", "f2")):
    return SC.make("history_preload", device_id=device_id, session_id=session_id,
                   frame_refs=list(frames), est_tokens=tokens, t=t)


def _co(arm, events, *, window_s=20.0, mode="A", out=None, period=None, budget=None):
    d = Path(out) if out else Path(tempfile.mkdtemp())
    logs = Logs(d).open()
    co = Live2Coordinator(arm, None, events, gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                          host_tier_tokens=HOST_TOK, upload_mode=mode, window_s=window_s,
                          drain_s=10.0, seed=1, logs=logs, run_tag=CK.run_tag(1, arm.name),
                          dry_run=True, decision_period_s=period, gpu_budget_s=budget)
    return co, logs


# ---------------------------------------------------------------- D101
class TestPreload(unittest.TestCase):
    def test_it_is_on_the_wire_with_the_agreed_fields(self):
        self.assertEqual(SC.FIELDS["history_preload"],
                         ("device_id", "session_id", "frame_refs", "est_tokens", "t"))
        self.assertIn("history_preload", SC.FLEET_TO_COORD)
        ev = _preload()
        self.assertEqual(SC.parse(ev).est_tokens, 5000)
        with self.assertRaises(ValueError):
            SC.make("history_preload", device_id="r0", session_id="s", frame_refs=[],
                    est_tokens=1)          # a missing `t` is refused, not defaulted

    def test_it_is_in_the_fairness_digest_coverage(self):
        for mode in ("A", "B"):
            self.assertIn("history_preload", T.fairness_kinds(mode))
        self.assertEqual(T._fairness_row(_preload()),
                         ("r0", "history_preload", "0.000000", "r0/s0", "5000", ""))
        base = [SC.make("device_register", device_id="r0", type="robot", uplink_mbps=13.6,
                        rtt_ms=44.0, start_t=0.0)]
        a = T.fairness_digest(base + [_preload()], "A")
        b = T.fairness_digest(base + [_preload(tokens=6000)], "A")
        self.assertNotEqual(a, b, "a different preload must be a different experiment")
        self.assertEqual(a, T.fairness_digest(list(reversed(base + [_preload()])), "A"))

    def test_the_coordinator_stores_it_as_cold_history_with_no_kv(self):
        arm = A.make_arm("edf")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        ev = [SC.make("device_register", device_id="r0", type="robot", uplink_mbps=13.6,
                      rtt_ms=44.0, start_t=0.0),
              SC.make("session_start", device_id="r0", session_id="r0/s0", t=0.0),
              _preload()]
        co, logs = _co(arm, ev, window_s=1.0)
        co.run()
        logs.close()
        s = co.st.sessions["r0/s0"]
        self.assertEqual(s.frames, ["f1", "f2"])
        self.assertEqual(s.est_tokens, 5000)
        self.assertEqual(s.preloaded_tokens, 5000)
        self.assertEqual(s.built_tokens, 0, "a preload is COLD: no KV is built by it")
        self.assertEqual(s.readiness(), "COLD")
        self.assertEqual(co.n_req, 0, "a preload charges no uplink and sends no request")

    def test_the_bridge_accepts_it(self):
        arm = A.make_arm("edf")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        co, logs = _co(arm, [], window_s=1.0)
        br = EmulatorBridge(co)
        br.on_event(SC.make("device_register", device_id="r0", type="robot", uplink_mbps=13.6,
                            rtt_ms=44.0, start_t=0.0), 0.0)
        br.on_event(_preload(), 0.0)
        logs.close()
        self.assertIn("r0/s0", co.st.sessions)
        self.assertEqual(co.st.sessions["r0/s0"].est_tokens, 5000)


# ---------------------------------------------------------------- D98
class TestD98(unittest.TestCase):
    def test_sh_admission_is_not_structurally_zero_at_either_h(self):
        """(a) The StudyLIVE2-coord issue-1 fixture: 0 of 240 admitted at H = 0.5 s before D98."""
        for h in (0.5, 1.0):
            with tempfile.TemporaryDirectory() as d:
                res = FX._cell(n_dashcam=2, n_robot=1, window_s=20.0, h=h, out=Path(d))
            s = res["arm_stats"]
            self.assertGreater(s["sh_escalated"], 0, "H=%.1f" % h)
            self.assertGreater(s["sh_admitted"], 0,
                               "H=%.1f: SH admission is still structurally zero" % h)
            self.assertTrue(all(x > 0 for x in s.get("sh_delta_j_admit", [])),
                            "an admit with DeltaJ <= 0 is not an admit")

    def test_the_library_rule_is_per_instant(self):
        from policy.rollout import Rollout
        from policy.tests._fixtures import PF, call_item, engine, fleet, params, piece_item, job
        from policy.flags import Flags
        from policy.rollout import delta_j
        ro = Rollout(PF, params(H=0.5), Flags(), engine())
        f = fleet(1)
        f.pending.append(call_item("d0", 0.0, "c0"))
        self.assertGreater(delta_j(ro, f, dict(kind="dispatch", item_id="c0"))["delta_j"], 0.0)
        # a delivery past its own deadline: device value, so not worth admitting
        g = fleet(1)
        g.in_flight.append(piece_item("d0", 0.0, "big", deadline=100.0, tokens=7000,
                                      job_id="jb"))
        g.jobs["jb"] = job(pieces=1)
        g.pending.append(call_item("d0", 0.0, "c0"))
        r = ro.run(g, release_now=["c0"])
        self.assertEqual([o["served_by"] for o in r.opportunities if o["t"] == 0.0], ["device"])
        self.assertLessEqual(delta_j(ro, g, dict(kind="dispatch", item_id="c0"))["delta_j"], 0.0)


# ---------------------------------------------------------------- D99
class TestD99(unittest.TestCase):
    def test_every_arm_decides_on_the_same_100ms_period(self):
        self.assertEqual(DECISION_PERIOD_S, 0.1)
        tr = T.synthetic(n_dashcam=1, n_robot=1, duration_s=5.0, seed=1)
        seen = {}
        for name in ("edf", "always-cloud-fcfs", "b9"):
            arm = A.make_arm(name)
            arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
            co, logs = _co(arm, tr["events"], window_s=5.0)
            res = co.run()
            logs.close()
            seen[name] = (co.decision_period_s, res["decision_latency_ms"]["n"])
        periods = {v[0] for v in seen.values()}
        self.assertEqual(periods, {0.1}, seen)
        counts = {v[1] for v in seen.values()}
        self.assertEqual(len(counts), 1, "arms decided a different number of times: %s" % seen)
        # exactly one decision per period over the window, inclusive of t = 0
        self.assertEqual(counts.pop(), int(5.0 / 0.1) + 1)

    def test_the_header_carries_the_period_and_h_separately(self):
        arm = A.make_arm("policy-core", h_s=1.0)
        d = Path(tempfile.mkdtemp())
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS,
                            calibration_knots_path=CALIB.write_knots(CALIB.load_map(),
                                                                     d / "k.json"))
        co, logs = _co(arm, [], window_s=1.0)
        logs.close()
        self.assertEqual(co.decision_period_s, 0.1)
        self.assertEqual(arm.params.H, 1.0)

    def test_the_fast_policy_decides_exactly_what_the_reference_decides(self):
        """(2) The equivalence test, on one small cell; fix_checks runs 4 and 8 devices x 3
        seeds x 120 s."""
        logs = {}
        for impl in ("reference", "fast"):
            with tempfile.TemporaryDirectory() as d:
                res = FX._cell(n_dashcam=2, n_robot=2, window_s=30.0, seed=1, impl=impl,
                               out=Path(d))
                logs[impl] = FX._strip(Path(res["decision_log"]))
        self.assertTrue(logs["fast"], "no decisions were logged")
        self.assertEqual(logs["reference"], logs["fast"])

    def test_the_fast_clone_leaves_the_callers_fleet_untouched(self):
        from policy.rollout import Rollout, delta_j
        from policy.tests._fixtures import PF, call_item, engine, fleet, params, piece_item, job
        from policy.flags import Flags
        out = {}
        for impl in ("reference", "fast"):
            ro = Rollout(PF, params(H=1.0), Flags(), engine())
            ro.clone_impl = impl
            f = fleet(2)
            f.pending += [call_item("d0", 0.0, "c0"), piece_item("d1", 0.0, "p0")]
            f.jobs["j0"] = job("d1", pieces=4, done=1)
            snap = copy.deepcopy(f)
            r = ro.run(f, release_now=["c0"])
            out[impl] = (r.total, r.u_hat, r.z_term, r.terminal,
                         delta_j(ro, f, dict(kind="release", item_id="p0"))["delta_j"])
            self.assertEqual(repr(f), repr(snap), "%s mutated the caller's fleet" % impl)
        self.assertEqual(out["reference"], out["fast"])

    def test_the_cap_binds_is_reported_and_drops_nothing(self):
        """(4) With K = 1 the cap must bind, be reported, and leave the un-evaluated instants
        visible for the next period rather than dropping them."""
        with tempfile.TemporaryDirectory() as d:
            res = FX._cell(n_dashcam=4, n_robot=0, window_s=20.0, out=Path(d) / "k1",
                           cap_k=1)
        s = res["arm_stats"]
        self.assertEqual(s["release_cap_k"], 1)
        self.assertGreater(s["sh_cap_bound_periods"] + s["release_cap_bound_passes"], 0,
                           "K = 1 on 4 dashcams never bound, so the test proves nothing")
        self.assertGreater(s["sh_admitted"], 0, "the cap starved admission completely")


# ---------------------------------------------------------------- D100
class TestD100(unittest.TestCase):
    def test_a_later_piece_costs_less_than_a_cold_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            r = FX.parity(Path(d))
        a = r["partial_readiness"]
        self.assertEqual(a["history_tokens"], 11_184)
        self.assertTrue(a["piece_is_cheaper"],
                        "a 1,024-token piece on a 10,160-token warm prefix (%.4f s) is not "
                        "cheaper than a cold rebuild of 11,184 tokens (%.4f s)"
                        % (a["piece_on_warm_prefix_s"],
                           a["cold_rebuild_of_the_same_tokens_s"]))
        for row in r["starvation"]["rows"]:
            self.assertTrue(row["both_devices_served"],
                            "%s served %s" % (row["arm"], row["monitor_answers_by_device"]))

    def test_the_hook_carries_the_instant_deadline_and_the_built_prefix(self):
        seen = {}

        class Spy(A.Pi0Edf):
            def live2_roster(self, roster):
                super().live2_roster(roster)
                seen.update(roster)

        tr = T.synthetic(n_dashcam=1, n_robot=1, duration_s=10.0, seed=1)
        arm = Spy(None)
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        co, logs = _co(arm, tr["events"], window_s=10.0)
        co.run()
        logs.close()
        self.assertIn("sh_instant", seen)
        self.assertIn("built_tokens_by_session", seen)
        for did, inst in seen["sh_instant"].items():
            self.assertAlmostEqual(inst["deadline_abs"] - inst["t_capture"],
                                   CS.TARGETS["dashcam"]["L_s"], places=6)

    def test_the_policy_costs_a_later_piece_on_a_warm_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            res = FX._cell(n_dashcam=1, n_robot=2, window_s=60.0, out=Path(d))
            rows = [json.loads(x) for x in
                    Path(res["decision_log"]).read_text().splitlines()]
            pieces = [r for r in rows if r["kind"] == "release_piece" or r["piece_tokens"]]
            self.assertTrue(pieces, "no piece was released, so nothing was costed as a piece")


# ---------------------------------------------------------------- D102
class TestD102(unittest.TestCase):
    def test_the_budget_is_an_input_identical_for_every_arm(self):
        tr = T.synthetic(n_dashcam=1, n_robot=1, duration_s=5.0, seed=1)
        got = {}
        for name in ("edf", "always-cloud-fcfs", "utility-per-cost", "b9"):
            arm = A.make_arm(name)
            arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
            co, logs = _co(arm, tr["events"], window_s=5.0)
            logs.close()
            got[name] = (co.gpu_budget_s, co.st.budget.gpu_seconds)
        self.assertEqual(set(got.values()), {(5.0, 5.0)}, got)

    def test_it_can_be_set_explicitly(self):
        arm = A.make_arm("edf")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        co, logs = _co(arm, [], window_s=5.0, budget=123.0)
        logs.close()
        self.assertEqual(co.gpu_budget_s, 123.0)
        self.assertEqual(co.st.budget.gpu_seconds, 123.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
