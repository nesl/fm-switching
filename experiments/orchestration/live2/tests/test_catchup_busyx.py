#!/usr/bin/env python3
"""Unit tests for the widened busy check of paced catch-up (live2_catchup_prefill_busyx). CPU only.
Run: python -I test_catchup_busyx.py
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
from test_catchup_pacing import _Arm  # noqa: E402


def _row(dev, qtype, kind, has_deadline=True):
    return NS(request_id="r", device_id=dev, qtype=qtype, kind=kind, uncached_tokens=100,
              slack_s=1.0, has_deadline=has_deadline)


def _arm(busyx):
    a = _Arm()
    if busyx:
        object.__setattr__(a, CU.BUSYX_SWITCH, True)
    CU.observe(a, _obs(10.1, [LINK]), _roster(3000, 1000))
    return a


def _cand(a, rows):
    return CU.candidates(a, _obs(10.2, [LINK], rows=rows), _roster(4000, 1000), set())


class T(unittest.TestCase):
    def test_none_in_flight(self):
        a = _arm(True)
        self.assertEqual(_cand(a, []), ["s1"])
        for k in ("ss", "dash", "cu_global"):
            self.assertEqual(a.stats["catchup_paced_skip_busy_" + k], 0)

    def test_ss_in_flight_blocks(self):
        a = _arm(True)
        self.assertEqual(_cand(a, [_row("asst003", "assistance", "recall")]), [])
        self.assertEqual(a.stats["catchup_paced_skip_busy_ss"], 1)

    def test_dash_in_flight_blocks_any_device(self):
        a = _arm(True)
        self.assertEqual(_cand(a, [_row("dash007", "alert", "monitor")]), [])
        self.assertEqual(a.stats["catchup_paced_skip_busy_dash"], 1)

    def test_background_rows_of_other_types_do_not_block_as_ss_or_dash(self):
        a = _arm(True)
        rows = [_row("dash007", "alert", "touch", False), _row("asst001", "assistance", "piece", False)]
        self.assertEqual(_cand(a, rows), ["s1"])

    def test_other_device_cu_piece_blocks_global(self):
        a = _arm(True)
        a._cu_state.win["s2"] = (0, 100, "d2")
        self.assertEqual(_cand(a, [_row("d2", "recall", "piece", False)]), [])
        self.assertEqual(a.stats["catchup_paced_skip_busy_cu_global"], 1)
        self.assertEqual(a.stats["catchup_epochs_paced_one_in_flight"], 0)

    def test_piece_of_device_without_window_does_not_block_global(self):
        a = _arm(True)
        self.assertEqual(_cand(a, [_row("d9", "recall", "piece", False)]), ["s1"])

    def test_same_device_piece_still_existing_counter(self):
        a = _arm(True)
        self.assertEqual(_cand(a, [_row("d1", "recall", "piece", False)]), [])
        self.assertEqual(a.stats["catchup_epochs_paced_one_in_flight"], 1)

    def test_off_unchanged(self):
        a = _arm(False)
        rows = [_row("asst003", "assistance", "recall"), _row("dash007", "alert", "monitor"),
                _row("d2", "recall", "piece", False)]
        a._cu_state.win["s2"] = (0, 100, "d2")
        a = _arm(False)
        self.assertEqual(_cand(a, rows), ["s1"])
        for k in ("ss", "dash", "cu_global"):
            self.assertEqual(a.stats["catchup_paced_skip_busy_" + k], 0)

    def test_switch_strict_and_requires_paced(self):
        class A: pass
        a = A()
        self.assertFalse(CU.arm_busyx(a))
        object.__setattr__(a, CU.BUSYX_SWITCH, 1)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_busyx(a)
        b = A()
        object.__setattr__(b, CU.BUSYX_SWITCH, True)
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_busyx(b)
        c = type("C", (), {CU.BUSYX_SWITCH: True})()
        with self.assertRaises(CU.CatchupSwitchError):
            CU.arm_busyx(c)

    def test_make_rung3(self):
        import arms_final_ladder as FL
        kw = dict(predictive_belief=True, book_belief=True, la_arrival=True)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=True, catchup_busyx=True, **kw)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_prefill=True, catchup_pace=True, catchup_busyx=1, **kw)
        with self.assertRaises(FL.LadderSwitchError):
            FL.make_rung3("x", catchup_busyx=True, **kw)
        arm = FL.make_rung3("x", catchup_prefill=True, catchup_pace=True, **kw)
        self.assertFalse(CU.arm_busyx(arm._rules))
        arm = FL.make_rung3("x", catchup_prefill=True, catchup_pace=True, catchup_busyx=True, **kw)
        self.assertTrue(CU.arm_busyx(arm._rules))


if __name__ == "__main__":
    unittest.main()
