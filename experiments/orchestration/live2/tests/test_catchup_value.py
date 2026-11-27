#!/usr/bin/env python3
"""Unit tests for the VALUE GATE of catch-up prefill (live2_catchup_prefill_value). CPU only.
Run: python -I test_catchup_value.py
"""
import sys
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import arms_final_ladder as FL  # noqa: E402
import catchup_prefill as CU  # noqa: E402
import catchup_value as CV  # noqa: E402
import cf_cost as CC  # noqa: E402
import d162_price as DP  # noqa: E402
import future_horizon as FH  # noqa: E402
import link_sync as LS  # noqa: E402

KW = dict(predictive_belief=True, book_belief=True, la_arrival=True, engine_resync=True,
          pb_wire_tokens=True, pb_host_engine_model=True)


def _arm(w=2.0):
    arm = FL.make_rung3("t", catchup_prefill=True, catchup_value=True, **KW)
    r = arm._rules
    r._gap_ewma = {"d1": 10.0, "d2": 12.0, "d3": 30.0}
    r._last_q_t = {"d1": 100.0, "d2": 100.0, "d3": 100.0}
    r._cup_w_of = lambda did: {"d1": w}.get(did, 1.0)
    r._roster = {"session_device": {"s1": "d1", "s2": "d2", "s3": "d3"},
                 "devices": {"d1": {"type": "robot"}, "d2": {"type": "robot"}, "d3": {"type": "single_shot"}},
                 "est_tokens_by_session": {"s1": 12000}, "built_tokens_by_session": {"s1": 4000}}
    r._cu_state.lastq["d2"] = {"session_id": "s2", "tokens": 9000, "slack_s": 3.0, "qtype": "recall"}
    r._cu_state.lastq["d3"] = {"session_id": "s3", "tokens": 3000, "slack_s": 3.0, "qtype": "assistance"}
    return arm, r


def _row(i, dev, qt, unc, slack):
    return NS(request_id=i, device_id=dev, qtype=qt, kind="recall", uncached_tokens=unc, slack_s=slack,
              has_deadline=True)


def _obs(rows=()):
    return NS(now_s=110.0, epoch=1, recall=[], live_sessions=("s1", "s2", "s3"), device_links=(),
              cloud=NS(in_flight_work=tuple(rows)))


def _eval(r, rows=()):
    return CV.evaluate(r, _obs(rows), r._roster, "s1", "d1", 8000, (4000, 8000, "d1"), 12000)


class T(unittest.TestCase):
    def test_switch_strict_and_exclusive(self):
        class A: pass
        a = A()
        self.assertFalse(CU.arm_value(a))
        object.__setattr__(a, CU.VALUE_SWITCH, 1)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_value(a)
        b = A()
        object.__setattr__(b, CU.VALUE_SWITCH, True)
        with self.assertRaises(CU.CatchupSwitchError):               # requires the catch-up switch
            CU.arm_value(b)
        c = type("C", (), {CU.VALUE_SWITCH: True})()
        with self.assertRaises(CU.CatchupSwitchError):               # class attribute
            CU.arm_value(c)
        d = A()
        object.__setattr__(d, CU.SWITCH, True)
        object.__setattr__(d, CU.VALUE_SWITCH, True)
        object.__setattr__(d, CU.PACED_SWITCH, True)
        with self.assertRaises(CU.CatchupSwitchError):               # exclusive with paced
            CU.arm_value(d)

    def test_make_rung3_prerequisites(self):
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_value=True, **KW)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=True, catchup_value=1, **KW)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=True, catchup_pace=True, catchup_value=True, **KW)
        arm = FL.make_rung3("x", catchup_prefill=True, **KW)
        self.assertFalse(CU.arm_value(arm._rules))
        arm = FL.make_rung3("x", catchup_prefill=True, catchup_value=True, **KW)
        self.assertTrue(CU.arm_value(arm._rules))
        self.assertFalse(CU.arm_paced(arm._rules))
        self.assertIs(arm._rules._cu_outer, arm)

    def test_empty_queue_releases(self):
        _, r = _arm()
        d = _eval(r)
        self.assertTrue(d["release"])
        self.assertGreater(d["net_acc"], 0.0)
        self.assertEqual(d["queued_ahead"], 0)

    def test_high_deficit_full_queue_not_released_until_harm_falls(self):
        _, r = _arm(w=2.0)
        busy = [_row("a", "d2", "recall", 6000, 2.0)]
        d = _eval(r, busy)
        self.assertFalse(d["release"])                                # gain 0.161 against harm 0.317
        self.assertEqual(d["gate"], "held_net_not_positive")
        self.assertGreater(d["harm_acc"], d["gain_acc"])
        d2 = _eval(r, [])                                             # the queue drained: harm falls
        self.assertTrue(d2["release"])
        self.assertLess(d2["harm_acc"], d["harm_acc"])

    def test_window_is_est_loadaware_counted_once(self):
        _, r = _arm()
        busy = [_row("a", "d2", "recall", 6000, 2.0)]
        d = _eval(r, busy)
        est = float(DP.first_token_s(8000, 6000))
        self.assertAlmostEqual(d["est_loadaware_s"], est, places=9)
        self.assertAlmostEqual(d["window_s"], min(est, float(CC.HORIZON_WARM_CAP_S)), places=9)
        self.assertAlmostEqual(d["service_s"] + d["queue_wait_s"], est, places=9)   # wait counted ONCE
        e = _eval(r, [])
        self.assertLess(e["window_s"], d["window_s"])                 # a non-empty queue lengthens it

    def test_window_capped_at_horizon(self):
        self.assertEqual(FH.arrival_window(service_s=100.0, wait_s=500.0, cap_s=120.0), 120.0)
        self.assertEqual(FH.arrival_window(service_s=2.0, wait_s=1.0, cap_s=120.0), 3.0)

    def test_units_gaps_committed(self):
        g = CV._gaps()
        self.assertAlmostEqual(g["recall"], LS.ACC_QF - LS.ACC_DEVICE, places=12)
        self.assertAlmostEqual(g["recall"], 0.311067, places=6)
        self.assertAlmostEqual(g["assistance"], 0.621881 - 0.547985, places=6)
        self.assertNotIn("alert", g)                                  # no uncommitted 1.0 unit

    def test_dashcam_row_contributes_zero_harm(self):
        _, r = _arm(w=2.0)
        base = _eval(r, [])
        dash = _eval(r, [_row("x", "d9", "alert", 4000, 1.1)])
        self.assertEqual(dash["harm_pending_ot"], 0.0)               # no pending-row harm term
        self.assertEqual(dash["harm_pending_ot"], base["harm_pending_ot"])
        self.assertGreater(dash["queued_ahead"], base["queued_ahead"])  # its tokens stay in B's register
        self.assertNotIn("alert", dash["harm_by_type_ot"])
        self.assertEqual(dash["n_other_rows"], 0)
        mix = _eval(r, [_row("a", "d2", "recall", 6000, 2.0), _row("x", "d9", "alert", 4000, 1.1)])
        rec = _eval(r, [_row("a", "d2", "recall", 6000, 2.0)])
        self.assertNotIn("alert", mix["harm_by_type_ot"])
        self.assertEqual(set(mix["harm_by_type_ot"]) - {"recall", "assistance"}, set())
        self.assertEqual(mix["n_other_rows"], 1)

    def test_gain_is_cloud_over_device_gap(self):
        _, r = _arm(w=2.0)
        d = _eval(r)
        self.assertAlmostEqual(d["gain_acc"], d["gain_ot"] * (LS.ACC_QF - LS.ACC_DEVICE), places=9)
        self.assertAlmostEqual(d["n_expected"], 120.0 / 10.0, places=9)   # the SAME N_exp as step 3

    def test_no_question_estimate_holds(self):
        _, r = _arm()
        r._gap_ewma = {}
        d = _eval(r)
        self.assertFalse(d["release"])
        self.assertEqual(d["gate"], "no_question_estimate")

    def test_candidates_value_branch_and_order(self):
        arm, r = _arm(w=2.0)
        from test_catchup_prefill import LINK, _obs as _o, _roster as _ro
        CU.observe(r, _o(10.1, [LINK]), _ro(3000, 1000))
        self.assertIn("s1", r._cu_state.win)
        self.assertEqual(r._cu_state.link["s1"]["offline_s"], 9.0)
        self.assertTrue(CU.arm_value(r) and not CU.arm_paced(r))
        # ordering: -net, then next question, then id
        r._cu_state.val = {"a": 0.1, "b": 0.5, "c": 0.5}
        r._roster = {"session_device": {"a": "d1", "b": "d2", "c": "d3"}}
        r._last_q_t = {"d1": 1.0, "d2": 5.0, "d3": 2.0}
        r._gap_ewma = {"d1": 1.0, "d2": 1.0, "d3": 1.0}
        self.assertEqual(CU.order(r, ["a", "b", "c"]), ["c", "b", "a"])

    def test_candidates_release_and_hold_in_the_loop(self):
        arm, r = _arm(w=2.0)
        from test_catchup_prefill import LINK, _obs as _o, _roster as _ro
        ro = _ro(3000, 1000)
        ro["devices"] = {"d1": {"type": "robot"}, "d2": {"type": "robot"}}
        r._roster = ro
        r._gap_ewma = {"d1": 10.0, "d2": 12.0}
        r._last_q_t = {"d1": 100.0, "d2": 100.0}
        CU.observe(r, _o(110.0, [LINK]), ro)
        ro2 = _ro(4000, 1000)
        ro2["devices"] = ro["devices"]
        ro2["session_device"] = {"s1": "d1", "s2": "d2"}
        r._roster = ro2

        def ob(rows):
            o = _o(110.5, [LINK], rows=rows)
            o.epoch, o.recall = 2, []
            return o
        got = CU.candidates(r, ob([]), ro2, set())
        self.assertEqual(got, ["s1"])
        self.assertEqual(r.stats["catchup_value_released"], 1)
        self.assertEqual(len(r._cu_state.vlog), 1)
        self.assertGreater(r._cu_state.val["s1"], 0.0)
        r.stats.clear()
        got = CU.candidates(r, ob([_row("a", "d2", "recall", 6000, 2.0)]), ro2, set())
        self.assertEqual(got, [])
        self.assertEqual(r.stats["catchup_value_held_net_not_positive"], 1)


if __name__ == "__main__":
    unittest.main()
