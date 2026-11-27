#!/usr/bin/env python3
"""Unit tests for the PACED mode of catch-up prefill (live2_catchup_prefill_paced). CPU only.
Run: python -I test_catchup_pacing.py
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import catchup_prefill as CU  # noqa: E402
from test_catchup_prefill import LINK, _obs, _roster  # noqa: E402


class _Arm:
    chunk_tokens = 2048

    def __init__(self, cap=8, c2=(0.0, 0, 0), last=9.0, gap=5.0, horizon=lambda g: g):
        from collections import Counter
        self.stats = Counter()
        self._cu_state = CU.State()
        self._last_q_t = {} if last is None else {"d1": last, "d2": last}
        self._gap_ewma = {} if gap is None else {"d1": gap, "d2": gap}
        self._roster = {"session_device": {"s1": "d1", "s2": "d2"}}
        self._horizon_s = horizon
        self._base = NS(cap=cap, cap_ceiling=8, c2_epoch=c2)
        object.__setattr__(self, CU.SWITCH, True)
        object.__setattr__(self, CU.PACED_SWITCH, True)
        self._cup_w_of = lambda did: {"d1": 1.0, "d2": 2.5}.get(did, 1.0)


def _open(a):
    CU.observe(a, _obs(10.1, [LINK]), _roster(3000, 1000))


class T(unittest.TestCase):
    def test_switch_strict_and_requires_base(self):
        class A: pass
        a = A()
        self.assertFalse(CU.arm_paced(a))
        object.__setattr__(a, CU.PACED_SWITCH, 1)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_paced(a)
        b = A()
        object.__setattr__(b, CU.PACED_SWITCH, True)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_paced(b)
        c = type("C", (), {CU.PACED_SWITCH: True})()
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_paced(c)

    def test_make_rung3_requires_catchup(self):
        import arms_final_ladder as FL
        kw = dict(predictive_belief=True, book_belief=True, la_arrival=True)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_pace=True, **kw)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=True, catchup_pace=1, **kw)
        arm = FL.make_rung3("x", catchup_prefill=True, **kw)
        self.assertFalse(CU.arm_paced(arm._rules))
        arm = FL.make_rung3("x", catchup_prefill=True, catchup_pace=True, **kw)
        self.assertTrue(CU.arm_paced(arm._rules))

    def test_c5_reduced_blocks(self):
        a = _Arm(cap=4)
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), [])
        self.assertEqual(a.stats["catchup_paced_suppressed_c5"], 1)
        a = _Arm(cap=8)
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), ["s1"])

    def test_c2_at_risk_blocks_only_same_epoch(self):
        for risk in ((10.2, 1, 0), (10.2, 0, 1)):
            a = _Arm(c2=risk)
            _open(a)
            self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), [])
            self.assertEqual(a.stats["catchup_paced_suppressed_c2"], 1)
        a = _Arm(c2=(10.0, 1, 1))
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), ["s1"])
        self.assertEqual(a.stats["catchup_paced_c2_epoch_stale"], 1)

    def test_horizon_gate(self):
        a = _Arm(last=None, gap=None)
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), [])
        self.assertEqual(a.stats["catchup_paced_skip_no_prediction"], 1)
        a = _Arm(horizon=lambda g: 0.5 * g, last=9.9, gap=5.0)   # next at 14.9; window opens 12.4
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), [])
        self.assertEqual(a.stats["catchup_paced_skip_beyond_horizon"], 1)
        self.assertEqual(CU.candidates(a, _obs(12.5, [LINK]), _roster(4000, 1000), set()), ["s1"])

    def test_credit_bounds_asks(self):
        a = _Arm()
        _open(a)                                           # ceil(8460 / 2048) = 5
        self.assertEqual(a._cu_state.credit["s1"], 5)
        for _ in range(5):
            plan = NS(legal=["s1"])
            self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), ["s1"])
            CU.account(a, plan, ["s1"], 10.2)
        self.assertEqual(CU.candidates(a, _obs(10.3, [LINK]), _roster(4000, 1000), set()), [])
        self.assertEqual(a.stats["catchup_paced_skip_no_credit"], 1)

    def test_ordinary_ask_spends_credit(self):
        a = _Arm()
        _open(a)
        CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), {"s1"})
        self.assertEqual(a._cu_state.credit["s1"], 4)

    def test_weight_order(self):
        a = _Arm(last=100.0, gap=50.0)
        a._gap_ewma = {"d1": 1.0, "d2": 50.0}               # gap alone would put s1 first
        self.assertEqual(CU.order(a, ["s1", "s2"], 0.0), ["s2", "s1"])
        object.__setattr__(a, CU.PACED_SWITCH, False)
        self.assertEqual(CU.order(a, ["s1", "s2"], 0.0), ["s1", "s2"])

    def test_unpaced_unchanged(self):
        a = _Arm(cap=4, c2=(10.2, 1, 1), last=None, gap=None)
        object.__setattr__(a, CU.PACED_SWITCH, False)
        _open(a)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), _roster(4000, 1000), set()), ["s1"])
        self.assertEqual(a._cu_state.credit, {})


if __name__ == "__main__":
    unittest.main()
