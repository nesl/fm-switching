#!/usr/bin/env python3
"""StudyLIVE2-perf Option B: the fallback is built, and the DEFAULT PATH IS UNTOUCHED.

The fallback is OFF by default and enabled nowhere. These tests exist to make that checkable
rather than claimed, and to make shadow mode's silence meaningful:

  1. the default `sh_cost = "rollout"` takes the call it replaced, argument for argument, and a
     dry cell's decision log is byte-identical with the hook in place;
  2. piece release and recall candidates are NEVER scored by the closed form, in any mode;
  3. shadow mode cannot change a decision: it decides with the rollout;
  4. a NEGATIVE CONTROL: a closed form whose load factor is forced to 0 must show up as large
     divergence, so shadow mode has proven it can fire.
"""
from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parents[1]
ROOT = ORCH.parents[1]
for _p in (str(ORCH), str(ORCH / "live2"), str(ORCH / "live2" / "fleet"),
           str(ORCH / "live2" / "scorer"), str(ORCH / "live"), str(ORCH / "baselines"),
           str(ORCH / "sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from policy import closed_form as CF                                    # noqa: E402
from policy import coordinator as CO                                    # noqa: E402
from policy.state import PendingItem                                    # noqa: E402


def _cell(**kw):
    import fix_checks as FX
    base = dict(n_dashcam=4, n_robot=4, window_s=60.0, seed=1, h=1.0)
    base.update(kw)
    return FX._cell(**base)


def _cell_with(sh_cost, **kw):
    """Run a dry cell with `sh_cost` set on the arm's coordinator, returning (result, arm)."""
    import fix_checks as FX
    holder = {}
    real = FX._arm

    def arm(*a, **akw):
        m = real(*a, **akw)
        m.co.sh_cost = sh_cost
        holder["arm"] = m
        return m

    FX._arm = arm
    try:
        res = _cell(**kw)
    finally:
        FX._arm = real
    return res, holder["arm"]


class TestTheDefaultPathIsUntouched(unittest.TestCase):
    def test_the_default_mode_is_rollout_everywhere(self):
        self.assertEqual(CO.Coordinator.sh_cost, "rollout")
        import arms as A
        import arms_policy as AP
        self.assertEqual(AP.PolicyCoreArm.sh_cost, "rollout")
        a = A.make_arm("policy-core")
        self.assertEqual(a.sh_cost, "rollout")

    def test_the_hook_is_the_call_it_replaced(self):
        """With the default mode the hook must forward to `delta_j` with the same action."""
        import fix_checks as FX
        from policy.rollout import delta_j as real_delta_j
        seen = []

        def spy(ro, fleet, action, **kw):
            seen.append(dict(action))
            return real_delta_j(ro, fleet, action, **kw)

        CO.delta_j = spy
        try:
            _cell(window_s=30.0)
        finally:
            CO.delta_j = real_delta_j
        admits = [a for a in seen if a["kind"] == "admit"]
        self.assertGreater(len(admits), 0)
        for a in admits:
            self.assertEqual(sorted(a), ["items", "jobs", "kind"])

    def test_a_dry_cell_decides_identically_in_rollout_mode(self):
        """Two runs of the default path, byte-identical decision logs."""
        import fix_checks as FX
        from pathlib import Path as P
        import tempfile
        logs = []
        with tempfile.TemporaryDirectory() as d:
            for i in (0, 1):
                r = _cell(window_s=60.0, out=P(d) / ("r%d" % i))
                logs.append(FX._strip(P(r["decision_log"])))
        self.assertEqual(logs[0], logs[1])
        self.assertGreater(len(logs[0]), 100)

    def test_the_closed_form_is_never_called_in_rollout_mode(self):
        real = CF.sh_admit_delta_j
        calls = []

        def spy(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        CF.sh_admit_delta_j = spy
        try:
            res, arm = _cell_with("rollout", window_s=30.0)
        finally:
            CF.sh_admit_delta_j = real
        self.assertEqual(calls, [])
        self.assertEqual(arm.co.sh_closed_form_calls, 0)
        self.assertEqual(arm.co.sh_shadow, [])


class TestOnlyShCandidatesReachIt(unittest.TestCase):
    def test_a_piece_or_recall_candidate_is_refused_outright(self):
        for kind in ("rc_piece", "state_action", "summary"):
            item = PendingItem(item_id="x", kind=kind, device="d0", due_at=0.0,
                               deadline=10.0, tokens=1000)
            with self.assertRaises(CF.ClosedFormNotApplicable):
                CF.sh_admit_delta_j(None, None, [item], {})

    def test_more_than_one_candidate_is_refused(self):
        a = PendingItem(item_id="a", kind="episode_call", device="d0", due_at=0.0,
                        deadline=1.0, tokens=378)
        b = PendingItem(item_id="b", kind="episode_call", device="d0", due_at=0.0,
                        deadline=1.0, tokens=378)
        with self.assertRaises(CF.ClosedFormNotApplicable):
            CF.sh_admit_delta_j(None, None, [a, b], {})

    def test_in_closed_form_mode_only_sh_admissions_use_it(self):
        """Every closed-form call must be a lone episode call; the counter proves it ran."""
        real = CF.sh_admit_delta_j
        kinds = []

        def spy(ro, fleet, items, jobs=None):
            kinds.append(tuple(sorted(p.kind for p in items)))
            return real(ro, fleet, items, jobs)

        CF.sh_admit_delta_j = spy
        try:
            res, arm = _cell_with("closed_form", window_s=60.0, mu="ewma")
        finally:
            CF.sh_admit_delta_j = real
        self.assertGreater(len(kinds), 50, len(kinds))
        self.assertEqual(set(kinds), {("episode_call",)},
                         "something other than a lone SH call reached the closed form")
        self.assertEqual(arm.co.sh_closed_form_calls, len(kinds))


class TestShadowMode(unittest.TestCase):
    def test_shadow_decides_with_the_rollout_byte_for_byte(self):
        import fix_checks as FX
        from pathlib import Path as P
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            r_roll, _a = _cell_with("rollout", window_s=60.0, mu="ewma", out=P(d) / "roll")
            r_shadow, arm = _cell_with("shadow", window_s=60.0, mu="ewma", out=P(d) / "shadow")
            a = FX._strip(P(r_roll["decision_log"]))
            b = FX._strip(P(r_shadow["decision_log"]))
        self.assertEqual(a, b, "shadow mode changed a decision")
        self.assertGreater(len(arm.co.sh_shadow), 100, "shadow logged too little to mean much")
        for row in arm.co.sh_shadow:
            for k in ("delta_j_rollout", "delta_j_closed_form", "admit_rollout",
                      "admit_closed_form", "backlog_queued_tokens",
                      "backlog_running_requests", "n_devices", "load_factor"):
                self.assertIn(k, row)

    def test_the_closed_form_matches_the_rollout_exactly_on_an_idle_engine(self):
        """With nothing queued and nothing in flight there is no delay to approximate."""
        res, arm = _cell_with("shadow", n_dashcam=2, n_robot=2, window_s=30.0)
        idle = [r for r in arm.co.sh_shadow
                if r["backlog_running_requests"] == 0 and r["backlog_queued_requests"] == 0
                and r["terms"]["work_ahead_s"] == 0.0]
        self.assertGreater(len(idle), 0,
                           "the fixture produced no idle-engine candidate to compare on")
        for r in idle:
            self.assertEqual(r["delta_j_closed_form"], r["delta_j_rollout"],
                             "the two must agree exactly when there is no overlapping work")

    def test_the_negative_control_a_zero_load_factor_shows_up(self):
        """Force the load factor to 0 and shadow mode must report large divergence."""
        real_lf = CF.load_factor

        def zero_lf(ro, fleet, cand):
            d = real_lf(ro, fleet, cand)
            d["lf"] = 0.0
            d["note"] = "NEGATIVE CONTROL: load factor forced to 0"
            return d

        CF.load_factor = zero_lf
        try:
            res, arm = _cell_with("shadow", n_dashcam=8, n_robot=8, window_s=60.0, mu="ewma")
        finally:
            CF.load_factor = real_lf
        sh = arm.co.sh_shadow
        self.assertGreater(len(sh), 100)
        diffs = [r["delta_j_closed_form"] - r["delta_j_rollout"] for r in sh]
        nonzero = [d for d in diffs if abs(d) > 1e-12]
        self.assertGreater(len(nonzero), 0,
                           "a zero load factor produced NO divergence at all, so shadow mode "
                           "cannot be trusted to detect one")
        self.assertGreater(max(abs(d) for d in diffs), 1e-9)
        # and the control must be worse than the real load factor on the same fixture
        res2, arm2 = _cell_with("shadow", n_dashcam=8, n_robot=8, window_s=60.0, mu="ewma")
        real_diffs = [abs(r["delta_j_closed_form"] - r["delta_j_rollout"])
                      for r in arm2.co.sh_shadow]
        self.assertGreaterEqual(sum(abs(d) for d in diffs), sum(real_diffs),
                                "the forced-zero control is not worse than the real load "
                                "factor, so the control proves nothing")


class TestTheLoadFactor(unittest.TestCase):
    def test_it_is_the_frozen_step_model_ratio_with_no_clamp(self):
        res, arm = _cell_with("shadow", n_dashcam=8, n_robot=8, window_s=60.0, mu="ewma")
        lfs = [r["load_factor"] for r in arm.co.sh_shadow]
        self.assertGreater(len(lfs), 100)
        self.assertTrue(all(x > 0 for x in lfs))
        # the pre-registration states this can fall below 1 because the frozen
        # `per_decode_req_ms` is negative; it is recorded, not clamped
        self.assertLess(min(lfs), 1.0 + 1e-9)
        self.assertGreater(max(lfs), 1.0)

    def test_the_frozen_coefficients_that_make_it_so_are_still_negative(self):
        from policy.eng1_engine import StepModel
        c = StepModel.load().coef
        self.assertLess(c["per_decode_req_ms"], 0.0)
        self.assertLess(c["admission_per_image_ms"], 0.0)


class TestNothingFrozenMoved(unittest.TestCase):
    def test_the_frozen_engine_md5_is_unchanged(self):
        import hashlib
        import json
        freeze = ROOT / "results/orchestration/study_t0b/t0b_freeze.json"
        d = json.loads(freeze.read_text())
        files = next(v for v in d.values()
                     if isinstance(v, dict) and any(".py" in str(x) for x in list(v)[:5]))
        for rel, want in files.items():
            if not rel.endswith(".py"):
                continue
            exp = want if isinstance(want, str) else want.get("md5")
            got = hashlib.md5((ROOT / rel).read_bytes()).hexdigest()
            self.assertEqual(got, exp, "%s changed; a frozen file is never edited" % rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
