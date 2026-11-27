#!/usr/bin/env python3
"""Unit tests for the catch-up prefill switch (catchup_prefill.py, make_rung3). CPU only.
Run: python -I test_catchup_prefill.py
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import catchup_prefill as CU  # noqa: E402


class _Arm:
    chunk_tokens = 2048

    def __init__(self):
        from collections import Counter
        self.stats = Counter()
        self._cu_state = CU.State()
        self._last_q_t, self._gap_ewma = {}, {}
        self._roster = {"session_device": {}}


def _obs(now, links=(), rows=(), live=("s1",)):
    return NS(now_s=now, device_links=tuple(links), live_sessions=tuple(live),
              cloud=NS(in_flight_work=tuple(rows)))


def _roster(est, built, cached=None):
    return {"est_tokens_by_session": {"s1": est}, "built_tokens_by_session": {"s1": built},
            "session_device": {"s1": "d1"}, "devices": {"d1": {"type": "robot"}},
            "pb_cached_by_session": {"s1": {"tokens": est, "cached": built if cached is None else cached}}}


LINK = NS(device_id="d1", connected=True, offline_since=1.0, back_online_at=10.0,
          backlog_frames=94, backlog_tokens=8460)


class T(unittest.TestCase):
    def test_switch_strict(self):
        class A: pass
        a = A()
        self.assertFalse(CU.arm_enables(a))
        object.__setattr__(a, CU.SWITCH, 1)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_enables(a)
        b = type("B", (), {CU.SWITCH: True})()
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_enables(b)

    def test_make_rung3_prerequisites(self):
        import arms_final_ladder as FL
        for kw in (dict(), dict(predictive_belief=True), dict(predictive_belief=True, book_belief=True)):
            with self.assertRaises(FL.LadderSwitchError):
                FL.make_rung3("x", catchup_prefill=True, **kw)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=1, predictive_belief=True, book_belief=True, la_arrival=True)
        arm = FL.make_rung3("x", predictive_belief=True, book_belief=True, la_arrival=True)
        self.assertFalse(CU.arm_enables(arm._rules))
        arm = FL.make_rung3("x", predictive_belief=True, book_belief=True, la_arrival=True,
                            catchup_prefill=True)
        self.assertTrue(CU.arm_enables(arm._rules))

    def test_window_opens_once_and_closes(self):
        a = _Arm()
        CU.observe(a, _obs(10.1, [LINK]), _roster(3000, 1000))
        self.assertEqual(a.stats["catchup_windows_opened"], 1)
        CU.observe(a, _obs(10.2, [LINK]), _roster(3100, 1000))
        self.assertEqual(a.stats["catchup_windows_opened"], 1)
        r = _roster(3100, 1000)
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK]), r, set()), ["s1"])
        r = _roster(3000 + 8460, 3000 + 8460 - 100)
        self.assertEqual(CU.candidates(a, _obs(20.0, [LINK]), r, set()), [])
        self.assertEqual(a.stats["catchup_windows_closed_done"], 1)

    def test_pacing_ordinary_and_cold(self):
        a = _Arm()
        CU.observe(a, _obs(10.1, [LINK]), _roster(3000, 1000))
        row = NS(device_id="d1", kind="piece")
        self.assertEqual(CU.candidates(a, _obs(10.2, [LINK], [row]), _roster(4000, 1000), set()), [])
        self.assertEqual(CU.candidates(a, _obs(10.3, [LINK]), _roster(4000, 1000), {"s1"}), [])
        self.assertEqual(CU.candidates(a, _obs(10.4, [LINK]), _roster(4000, 1000, cached=0), set()), [])
        self.assertEqual(a.stats["catchup_epochs_paced_one_in_flight"], 1)
        self.assertEqual(a.stats["catchup_epochs_ordinary_ask_already"], 1)
        self.assertEqual(a.stats["catchup_epochs_prefix_not_resident"], 1)

    def test_no_backlog_no_window(self):
        a = _Arm()
        lk = NS(device_id="d1", connected=True, offline_since=1.0, back_online_at=10.0,
                backlog_frames=0, backlog_tokens=0)
        CU.observe(a, _obs(10.1, [lk]), _roster(3000, 1000))
        self.assertEqual(a.stats["catchup_windows_opened"], 0)

    def test_order(self):
        a = _Arm()
        a._roster = {"session_device": {"s1": "d1", "s2": "d2", "s3": "d3"}}
        a._last_q_t = {"d1": 100.0, "d2": 100.0}
        a._gap_ewma = {"d1": 50.0, "d2": 10.0}
        self.assertEqual(CU.order(a, ["s3", "s1", "s2"]), ["s2", "s1", "s3"])


if __name__ == "__main__":
    unittest.main()
