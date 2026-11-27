#!/usr/bin/env python3
"""Unit tests for the D333 EXTENDED F1 / S2 netting claim: S2's claim on a robot's future is held
from its first executed release until the catch-up COMPLETES (window close / piece completion), F1 may
not credit that future while it is held; F1's admission holds the robot's future for its own window
and S2 may not release in it. CPU only, no engine. Run: python -I test_cf_claim.py"""
import sys
import types
import unittest
from collections import defaultdict
from pathlib import Path

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import cf_forfeit as CF  # noqa: E402
import catchup_prefill as CU  # noqa: E402
import arms_v6cfstep3 as S3  # noqa: E402


def _arm_with_state():
    arm = types.SimpleNamespace()
    arm._cu_state = CU.State()
    arm._roster = {"session_device": {"s001": "robo001", "s002": "robo002"}}
    arm.stats = defaultdict(int)
    return arm


class ClaimTests(unittest.TestCase):
    def test_pure_blocking_rule(self):
        self.assertTrue(CF.s2_claim_blocks(True, True, 9.0, 10.0))        # opened in an earlier epoch: bars F1
        self.assertFalse(CF.s2_claim_blocks(True, True, 10.0, 10.0))      # same epoch: joint evaluation instead
        self.assertFalse(CF.s2_claim_blocks(True, False, None, 10.0))     # not held
        self.assertFalse(CF.s2_claim_blocks(False, True, 9.0, 10.0))      # netting OFF: nothing blocks

    def test_window_scope_claim_held_from_release_until_window_closes(self):
        arm = _arm_with_state()
        cu = arm._cu_state
        cu.win["s001"] = (1000, 4000, "robo001")                         # a catch-up window is open
        self.assertEqual(CU.s2_claim(arm, None, "robo001", "window"), (False, None))   # nothing released yet
        cu.first_rel["s001"] = 7.0                                       # S2's first executed release
        self.assertEqual(CU.s2_claim(arm, None, "robo001", "window"), (True, 7.0))
        self.assertTrue(CF.s2_claim_blocks(True, True, 7.0, 7.1))        # F1 may not credit while held
        self.assertEqual(CU.s2_claim(arm, None, "robo002", "window"), (False, None))   # another robot: free
        del cu.win["s001"]                                               # the catch-up COMPLETES (window close)
        cu.first_rel.pop("s001", None)
        self.assertEqual(CU.s2_claim(arm, None, "robo001", "window"), (False, None))   # released at completion
        self.assertFalse(CF.s2_claim_blocks(True, False, None, 12.0))

    def test_piece_scope_claim_follows_the_in_flight_register(self):
        arm = _arm_with_state()
        cu = arm._cu_state
        cu.rel_dev["robo001"] = 7.0
        row = types.SimpleNamespace(device_id="robo001", kind="piece")
        obs = types.SimpleNamespace(cloud=types.SimpleNamespace(in_flight_work=(row,)))
        self.assertEqual(CU.s2_claim(arm, obs, "robo001", "piece"), (True, 7.0))
        obs2 = types.SimpleNamespace(cloud=types.SimpleNamespace(in_flight_work=()))   # the piece completed
        self.assertEqual(CU.s2_claim(arm, obs2, "robo001", "piece"), (False, None))

    def test_f1_claim_blocks_s2_for_its_window_only(self):
        arm = _arm_with_state()
        cu = arm._cu_state
        cu.f1_claim["robo001"] = (10.0, 13.5)                            # F1's admission window (est_loadaware)
        self.assertTrue(CU.f1_claim_active(cu, "robo001", 11.0))
        self.assertFalse(CU.f1_claim_active(cu, "robo001", 13.5))        # the claim ends with the window
        self.assertFalse(CU.f1_claim_active(cu, "robo002", 11.0))        # another robot: free

    def test_admission_win_cancels_the_s2_claim_opened_this_epoch(self):
        a = types.SimpleNamespace()
        a.stats = defaultdict(int)
        a.cf3_rows = []
        cu = CU.State()
        cu.rel_t, cu.rel = 10.0, {"s001": (0.05, "robo001")}
        cu.first_rel["s001"], cu.rel_dev["robo001"] = 10.0, 10.0
        a._rules = types.SimpleNamespace(_cu_state=cu)
        object.__setattr__(a, CF.NET_SWITCH, True)
        act = types.SimpleNamespace(sessions=[types.SimpleNamespace(session_id="s001", action="MATERIALIZE")])
        obs = types.SimpleNamespace(now_s=10.0)
        ra = types.SimpleNamespace(query_id="q1")
        d = {"own_gain": 0.6, "future_gain": 3.0, "bar": 0.2, "net": 3.6}
        supp = S3._Step3Mixin._cf3_net_claim(a, obs, act, ra, d, "robo001", "s001",
                                             {"harm_by_type": {}}, None)
        self.assertFalse(supp)
        self.assertEqual(act.sessions, [])                               # S2's release removed
        self.assertNotIn("s001", cu.first_rel)                           # and its claim never opened
        self.assertNotIn("robo001", cu.rel_dev)


if __name__ == "__main__":
    unittest.main()
