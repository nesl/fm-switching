#!/usr/bin/env python3
"""Unit tests for the D331 F1 / S2 netting (cf_forfeit.net_*, arms_v6cfstep3._Step3Mixin._cf3_net_claim).
CPU only, no engine. Run: python -I test_cf_net.py"""
import sys
import types
import unittest
from collections import defaultdict
from pathlib import Path

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import cf_forfeit as CF  # noqa: E402
import arms_v6cfstep3 as S3  # noqa: E402


def _SA(sid, action):
    return types.SimpleNamespace(session_id=sid, action=action)


def _arm(net_on, rel_t=10.0, rel=None):
    a = types.SimpleNamespace()
    a.stats = defaultdict(int)
    a.cf3_rows = []
    a._rules = types.SimpleNamespace(_cu_state=types.SimpleNamespace(rel_t=rel_t, rel=rel if rel is not None else {}, first_rel={}, rel_dev={}))
    object.__setattr__(a, CF.NET_SWITCH, bool(net_on))
    return a


def _d(own=0.6, fut=3.0, bar=0.2):
    return {"own_gain": own, "future_gain": fut, "bar": bar, "net": own + fut}


class NetTests(unittest.TestCase):
    def _call(self, arm, act, d, harm=None, harm_arr=None, now=10.0, did="robo001"):
        obs = types.SimpleNamespace(now_s=now)
        ra = types.SimpleNamespace(query_id="q1")
        return S3._Step3Mixin._cf3_net_claim(arm, obs, act, ra, d, did, "s001",
                                             harm or {"harm_by_type": {}}, harm_arr)

    def test_default_off_and_strict(self):
        a = types.SimpleNamespace()
        self.assertFalse(CF.net_enabled(a))
        object.__setattr__(a, CF.NET_SWITCH, 1)
        with self.assertRaises(CF.CfForfeitSwitchError):
            CF.net_enabled(a)

    def test_winner_and_tie(self):
        self.assertEqual(CF.net_winner(1.0, 0.5), "admit")
        self.assertEqual(CF.net_winner(0.5, 1.0), "s2")
        self.assertEqual(CF.net_winner(0.5, 0.5), "s2")          # a tie keeps the plan's S2 release

    def test_no_coincidence_without_s2_release_this_epoch(self):
        act = types.SimpleNamespace(sessions=[_SA("s001", "MATERIALIZE")])
        a = _arm(True, rel_t=9.0, rel={"s001": (0.5, "robo001")})       # a STALE epoch
        self.assertFalse(self._call(a, act, _d()))
        self.assertEqual(a.stats["cf3_net_coincide"], 0)
        a2 = _arm(True, rel={"s009": (0.5, "robo009")})                 # another robot
        self.assertFalse(self._call(a2, act, _d()))
        self.assertEqual(a2.stats["cf3_net_coincide"], 0)

    def test_admission_wins_removes_s2_and_logs(self):
        act = types.SimpleNamespace(sessions=[_SA("s001", "MATERIALIZE"), _SA("s002", "KEEP_GPU_WARM")])
        a = _arm(True, rel={"s001": (0.05, "robo001")})
        supp = self._call(a, act, _d(own=0.6, fut=3.0, bar=0.2))
        self.assertFalse(supp)                                          # the admission proceeds
        self.assertEqual([x.session_id for x in act.sessions], ["s002"])  # S2's release removed
        self.assertEqual(a.stats["cf3_net_s2_suppressed"], 1)
        r = a.cf3_rows[-1]
        self.assertEqual((r["event"], r["winner"], r["executed"], r["suppressed"]),
                         ("net_claim", "admit", "admit", "s2_release"))

    def test_s2_wins_suppresses_admission_and_logs(self):
        act = types.SimpleNamespace(sessions=[_SA("s001", "MATERIALIZE")])
        a = _arm(True, rel={"s001": (5.0, "robo001")})
        supp = self._call(a, act, _d(own=0.1, fut=0.1, bar=0.2))
        self.assertTrue(supp)                                           # the admission is suppressed
        self.assertEqual(len(act.sessions), 1)                          # S2's release stays
        self.assertEqual(a.stats["cf3_net_admission_suppressed"], 1)
        r = a.cf3_rows[-1]
        self.assertEqual((r["winner"], r["executed"], r["suppressed"]), ("s2", "s2", "admission"))

    def test_high_harm_makes_s2_win_even_with_big_future(self):
        act = types.SimpleNamespace(sessions=[_SA("s001", "MATERIALIZE")])
        a = _arm(True, rel={"s001": (0.3, "robo001")})
        supp = self._call(a, act, _d(own=0.6, fut=3.0, bar=0.2),
                          harm={"harm_by_type": {"recall": 50.0}})
        self.assertTrue(supp)

    def test_off_counts_and_logs_both_execute(self):
        act = types.SimpleNamespace(sessions=[_SA("s001", "MATERIALIZE")])
        a = _arm(False, rel={"s001": (0.05, "robo001")})
        self.assertFalse(self._call(a, act, _d()))
        self.assertEqual(len(act.sessions), 1)                          # nothing removed
        self.assertEqual(a.stats["cf3_net_coincide"], 1)
        self.assertEqual(a.stats["cf3_net_both_executed"], 1)
        self.assertEqual(a.cf3_rows[-1]["executed"], "both")


if __name__ == "__main__":
    unittest.main()
