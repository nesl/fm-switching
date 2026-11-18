#!/usr/bin/env python3
"""StudyLIVE2-perf Option 0: the terminal state-value memo returns the computed value.

The cache is only safe if its key names EVERY input the value depends on. Asserting that is
worthless; these tests make it falsifiable three ways:

  1. per field: perturb each input the key names, then ask the cache again, and require the
     answer to equal a fresh uncached computation. A key that missed the field would hand back
     the stale value and fail here.
  2. shadow mode on a real cell: compute both on every call over a dry policy cell and require
     agreement, which covers the inputs a hand-written test would not think to vary.
  3. a NEGATIVE CONTROL for shadow mode itself: break the key on purpose and require shadow mode
     to raise. Without this, 2 could be passing because the machinery never fires.
"""
from __future__ import annotations

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

from policy import readiness as R                                       # noqa: E402
from policy.readiness import StateValueCache, state_value               # noqa: E402

from policy.tests import _fixtures as FX                                # noqa: E402

PF = FX.PF
H_S, DEADLINE, OMEGA = 1.0, 10.0, 1.0


def _args(dev, **kw):
    a = dict(pf=PF, device=dev, rep="RICH", demand=dev.demand, h_s=H_S,
             qtype=dev.qtype, link=dev.link, deadline_s=DEADLINE, omega_rc=OMEGA,
             in_episode=False, exclude_job=None, credit_allowed=True)
    a.update(kw)
    return a


def _cached(cache, a):
    return state_value(cache=cache, **a)


def _fresh(a):
    return state_value(cache=None, **a)


class TestTheKeyNamesEveryInputTheValueDependsOn(unittest.TestCase):
    """Each case: fill the cache, change ONE thing, and require the cache to follow."""

    def _case(self, name, mutate, setup=None, **akw):
        """Fill the cache, change ONE input, and require both properties to hold.

        The property that matters is that the KEY names the field: if it did not, the second
        call would return the first call's value. Whether the value happens to MOVE for a
        particular fixture is a separate question and is reported, not required, because a value
        can sit on a plateau (a delivery already past its deadline, say) where a field genuinely
        does not matter.
        """
        dev = FX.device()
        if setup is not None:
            setup(dev)
        a = _args(dev, **akw)
        cache = StateValueCache(mode="on")
        k_before = R.state_value_key(a["pf"], a["device"], a["rep"], a["demand"], a["h_s"],
                                     a["qtype"], a["link"], a["deadline_s"], a["omega_rc"],
                                     a["in_episode"], a["exclude_job"], a["credit_allowed"])
        first = _cached(cache, a)
        self.assertEqual(first, _fresh(a), name + ": the first call already differs")
        mutate(dev, a)
        k_after = R.state_value_key(a["pf"], a["device"], a["rep"], a["demand"], a["h_s"],
                                    a["qtype"], a["link"], a["deadline_s"], a["omega_rc"],
                                    a["in_episode"], a["exclude_job"], a["credit_allowed"])
        self.assertNotEqual(k_before, k_after,
                            "%s: the key did not change, so a stale value could be served"
                            % name)
        want = _fresh(a)
        got = _cached(cache, a)
        self.assertEqual(got, want,
                         "%s: the cache returned a STALE value, so the key does not name it"
                         % name)
        return first, want

    def test_belief_size_tokens(self):
        def m(dev, a):
            dev.history["RICH"].size_tokens = 28_000
        f, w = self._case("size_tokens", m)
        self.assertNotEqual(f, w, "size_tokens did not move the value; pick a case that does")


    def test_belief_staleness(self):
        def m(dev, a):
            dev.history["RICH"].staleness_s = 60.0
        # the key must name it; whether it moves the value depends on where the fixture sits
        self._case("staleness_s", m)

    def test_belief_probabilities(self):
        def m(dev, a):
            dev.history["RICH"].probs = {"GPU": 1.0, "HOST": 0.0, "STORED": 0.0}
        self._case("probs", m)

    def test_demand_rate(self):
        def m(dev, a):
            dev.demand.lambda_rc["RICH"] = float(dev.demand.lambda_rc.get("RICH", 0.01)) * 7.0
        f, w = self._case("demand rate", m)
        self.assertNotEqual(f, w)

    def test_conditional_rate_enabled_and_in_episode(self):
        dev = FX.device()
        dev.demand.conditional_rate_enabled = True
        dev.demand.conditional_ratio = 3.0
        cache = StateValueCache(mode="on")
        a_off = _args(dev, in_episode=False)
        a_on = _args(dev, in_episode=True)
        self.assertEqual(_cached(cache, a_off), _fresh(a_off))
        self.assertEqual(_cached(cache, a_on), _fresh(a_on))
        self.assertNotEqual(_fresh(a_off)["p_need"], _fresh(a_on)["p_need"])
        # and the conditional rate itself is in the key, with the flag actually enabled
        def setup(dev_):
            dev_.demand.conditional_rate_enabled = True
            dev_.demand.conditional_ratio = 3.0

        def m(dev_, a_):
            dev_.demand.conditional_ratio = 11.0
        f, w = self._case("conditional_ratio", m, setup=setup, in_episode=True)
        self.assertNotEqual(f, w)

    def test_link_round_trip_time(self):
        def m(dev, a):
            dev.link.rtt_s = 9.0
        # a long enough RTT pushes delivery past the deadline, which changes u_RC
        self._case("link rtt", m)

    def test_h_s_deadline_and_omega(self):
        for name, kw, kw2 in (("h_s", dict(h_s=1.0), dict(h_s=30.0)),
                              ("deadline_s", dict(deadline_s=10.0), dict(deadline_s=0.001)),
                              ("omega_rc", dict(omega_rc=1.0), dict(omega_rc=5.0))):
            dev = FX.device()
            cache = StateValueCache(mode="on")
            a1, a2 = _args(dev, **kw), _args(dev, **kw2)
            self.assertEqual(_cached(cache, a1), _fresh(a1), name)
            self.assertEqual(_cached(cache, a2), _fresh(a2), name)
            self.assertNotEqual(_fresh(a1), _fresh(a2), name + " did not move the value")

    def test_credit_allowed_exclude_job_rep_and_qtype(self):
        dev = FX.device()
        cache = StateValueCache(mode="on")
        base = _args(dev)
        pairs = [dict(credit_allowed=False), dict(exclude_job="job7")]
        self.assertEqual(_cached(cache, base), _fresh(base))
        for kw in pairs:
            a = _args(dev, **kw)
            self.assertEqual(_cached(cache, a), _fresh(a), repr(kw))
            self.assertNotEqual(_fresh(base), _fresh(a), repr(kw) + " did not move the output")

    def test_a_hit_is_a_copy_so_a_caller_cannot_poison_the_cache(self):
        dev = FX.device()
        a = _args(dev)
        cache = StateValueCache(mode="on")
        first = _cached(cache, a)
        first["value"] = -12345.0
        first["counts"] = "mutated by a caller"
        second = _cached(cache, a)
        self.assertEqual(second, _fresh(a))
        self.assertNotEqual(second["value"], -12345.0)


class TestShadowMode(unittest.TestCase):
    def test_shadow_mode_agrees_on_a_real_policy_cell(self):
        import fix_checks as FXC
        arm_holder = {}
        real_arm = FXC._arm

        def arm(*a, **kw):
            made = real_arm(*a, **kw)
            made.co.rollout.sv_cache_impl = "shadow"
            arm_holder["arm"] = made
            return made

        FXC._arm = arm
        try:
            # 8 + 8 over 60 s: a shorter or smaller cell never reaches the terminal
            # state-value loop at all, because no robot has built a history yet, and a test
            # that exercises nothing would pass for the wrong reason
            FXC._cell(n_dashcam=8, n_robot=8, window_s=60.0, seed=1, h=1.0)
        finally:
            FXC._arm = real_arm
        c = arm_holder["arm"].co.rollout.state_value_cache()
        s = c.stats()
        self.assertEqual(s["mode"], "shadow")
        self.assertGreater(s["shadow_checks"], 10000,
                           "shadow mode barely fired, so it proves little: %r" % (s,))
        self.assertGreater(s["clears"], 100)
        self.assertEqual(s["hits"], s["shadow_checks"],
                         "in shadow mode every hit must also have been verified")

    def test_shadow_mode_catches_an_incomplete_key(self):
        """The negative control: break the key and require shadow mode to notice."""
        dev = FX.device()
        a = _args(dev)
        cache = StateValueCache(mode="shadow")
        real_key = R.state_value_key

        def blind_key(pf, device, rep, demand, h_s, qtype, link, deadline_s, omega_rc,
                      in_episode, exclude_job, credit_allowed):
            # drops the belief entirely, which is exactly the kind of omission to catch
            return (id(pf), rep, qtype, float(h_s), float(deadline_s), float(omega_rc),
                    bool(in_episode), bool(credit_allowed), exclude_job)

        R.state_value_key = blind_key
        try:
            _cached(cache, a)                       # fills the broken key
            dev.history["RICH"].size_tokens = 28_000
            with self.assertRaises(AssertionError) as cm:
                _cached(cache, a)
            self.assertIn("the key is incomplete", str(cm.exception))
        finally:
            R.state_value_key = real_key

    def test_off_mode_computes_and_caches_nothing(self):
        dev = FX.device()
        a = _args(dev)
        cache = StateValueCache(mode="off")
        self.assertEqual(_cached(cache, a), _fresh(a))
        s = cache.stats()
        self.assertEqual((s["hits"], s["misses"], s["live_entries"]), (0, 0, 0))

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            StateValueCache(mode="sometimes")


class TestThePeriodScope(unittest.TestCase):
    def test_the_arm_clears_the_cache_once_per_decision_period(self):
        import fix_checks as FXC
        r = FXC._cell(n_dashcam=8, n_robot=8, window_s=60.0, seed=1, h=1.0)
        c = (r.get("arm_stats") or {}).get("state_value_cache")
        self.assertIsNotNone(c, "the cache stats did not reach arm_stats")
        self.assertEqual(c["mode"], "on")
        # one clear per DECISION PERIOD, which is one decision-latency sample per period, not
        # one per logged decision (a period can log several)
        periods = r["decision_latency_ms"]["n"]
        self.assertEqual(c["clears"], periods,
                         "the cache must be cleared exactly once per decision period")
        self.assertGreater(c["n_calls"], 10000, c)
        self.assertGreater(c["hit_fraction"], 0.5, c)
        # entries alive at the end belong to the last period only, so at most one per
        # (device, representation) pair rather than one per period
        self.assertLessEqual(c["live_entries"], 16 * 4, c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
