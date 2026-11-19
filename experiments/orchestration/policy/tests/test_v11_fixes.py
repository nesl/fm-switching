#!/usr/bin/env python3
"""D122 policy v1.1. Each fix behind its own flag, DEFAULT OFF (D38).

A3, honour_job_priority: spec 7.3's bounded-waiting check promotes a job to the PRIORITY class
and `coordinator._update_jobs` does set `job.feasibility = PRIORITY`, but the rollout valued
every job with `priority=False` hard coded, so the label could not reach the value it was
assigned for.

MEASURED AND REPORTED: with `competing_s = 0.0`, which is what the rollout passes, the `priority`
argument has NO effect, because `continuation_schedule` uses it only as
`cursor = t + (0.0 if priority else competing_s)`. So A3 is a no-op in today's build and becomes
live the moment competing work is modelled. The tests below therefore pin two things separately:
that the label is passed through (which is what v1.0 got wrong), and that it is inert at
`competing_s = 0` (which is what makes A3 safe to ship now).
"""
from __future__ import annotations

import unittest

from policy.continuation import FEASIBLE, INFEASIBLE, PRIORITY, classify, continuation_value
from policy.eng1_engine_fast import Eng1Engine
from policy.flags import Flags
from policy.profiles import load_profiles
from policy.state import Job

QTYPE = "counting_objects_events"


def _job(deadline: float, pieces_done: int = 0, feasibility: str = FEASIBLE) -> Job:
    j = Job(job_id="j", device="robo000", qtype=QTYPE, rep="RICH", deadline=deadline,
            admitted_at=0.0, pieces_total=4, pieces_done=pieces_done, tokens_per_piece=2048)
    j.feasibility = feasibility
    return j


class TestA3LabelIsPassedThrough(unittest.TestCase):
    """What v1.0 got wrong: the promotion label never reached `continuation_value`."""

    def setUp(self):
        self.e = Eng1Engine.load()
        self.pf = load_profiles()
        self.ac = self.pf.rc_accuracy(QTYPE, "RICH", "cloud")
        self.ad = self.pf.rc_accuracy(QTYPE, "D2", "device")
        self.om = self.pf.omega("RC")

    def _value(self, job, competing_s, priority):
        return continuation_value(job, 0.0, self.e, competing_s=competing_s, priority=priority,
                                  omega_rc=self.om, acc_cloud=self.ac, acc_device=self.ad,
                                  z=0.0, d_p_success=0.0, p_reachable=1.0, resolution_s=0.25,
                                  extra_work_s=0.0)

    def test_the_flag_defaults_off(self):
        self.assertFalse(Flags().honour_job_priority)

    def test_a_promoted_job_is_worth_more_when_competing_work_is_modelled(self):
        """The hand-built near-infeasible job the task asks for.

        At `competing_s = 3.0` a four-piece job with a 3.0 s deadline cannot finish behind the
        competing work, so it is worth 0 without priority and its full value with it. This is the
        case v1.0's hard-coded `priority=False` could never express.
        """
        job = _job(3.0, feasibility=PRIORITY)
        without = self._value(job, 3.0, False)
        with_prio = self._value(job, 3.0, True)
        self.assertEqual(without, 0.0, "without priority the job cannot finish, so it is worth 0")
        self.assertGreater(with_prio, 0.0, "with priority it fits and carries its full value")
        self.assertAlmostEqual(with_prio, self.om * (self.ac - self.ad), places=9)

    def test_the_rollout_now_reads_the_jobs_own_class(self):
        """v1.0 hard-coded `priority=False`; v1.1 derives it from the job and the flag."""
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout._terminal)
        self.assertIn("honour_job_priority", src,
                      "the rollout must consult the flag rather than hard-code priority")
        self.assertIn("j.feasibility == PRIORITY", src,
                      "the rollout must read the job's own class")
        self.assertNotIn("priority=False", src,
                         "the hard-coded priority=False is what v1.0 got wrong")

    def test_with_the_flag_off_the_job_class_is_ignored(self):
        """Default-off means a promoted job is valued exactly as v1.0 valued it."""
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout._terminal)
        self.assertIn("self.flags.honour_job_priority and", src)


class TestA3IsInertAtZeroCompetingWork(unittest.TestCase):
    """Why A3 is safe to ship now, and why it cannot be the robot fix on its own."""

    def setUp(self):
        self.e = Eng1Engine.load()
        self.pf = load_profiles()
        self.ac = self.pf.rc_accuracy(QTYPE, "RICH", "cloud")
        self.ad = self.pf.rc_accuracy(QTYPE, "D2", "device")
        self.om = self.pf.omega("RC")

    def _value(self, job, priority):
        return continuation_value(job, 0.0, self.e, competing_s=0.0, priority=priority,
                                  omega_rc=self.om, acc_cloud=self.ac, acc_device=self.ad,
                                  z=0.0, d_p_success=0.0, p_reachable=1.0, resolution_s=0.25,
                                  extra_work_s=0.0)

    def test_priority_changes_nothing_when_competing_work_is_zero(self):
        for deadline in (5.0, 2.0, 1.5, 1.0, 0.9):
            job = _job(deadline)
            self.assertEqual(self._value(job, False), self._value(job, True),
                             "at competing_s = 0 the priority flag must be inert, deadline %.1f"
                             % deadline)

    def test_classify_cannot_return_priority_at_zero_competing_work(self):
        """Both of `classify`'s branches use competing_s = 0 in production, so they agree."""
        seen = set()
        for i in range(1, 101):
            seen.add(classify(_job(round(i * 0.05, 2)), 0.0, self.e, 0.0, 0.5, 0.0, 0.25))
        self.assertEqual(seen, {FEASIBLE, INFEASIBLE},
                         "PRIORITY is unreachable from classify while competing_s is 0 on both "
                         "sides; got %r" % (sorted(seen),))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestB1DeficitUpdate(unittest.TestCase):
    """D122 fix B1: the deficit counter is updated from the REALISED on-time outcome.

    These fail on v1.0 for the plainest possible reason: on v1.0 nothing in production ever calls
    `bump_z`, so `z_of` stays 0.0 whatever happens.
    """

    def _device(self):
        from policy.state import Device, Link
        return Device(device_id="robo000", link=Link(bandwidth_bytes_s=1.7e6, rtt_s=0.05),
                      qtype=QTYPE)

    def test_a_realised_miss_raises_z_by_the_target(self):
        dev = self._device()
        self.assertEqual(dev.z_of("RC"), 0.0)
        dev.bump_z("RC", 0.9, 0.0)
        self.assertAlmostEqual(dev.z_of("RC"), 0.9, places=9)

    def test_a_realised_success_lowers_it_and_the_floor_holds(self):
        dev = self._device()
        dev.bump_z("RC", 0.9, 1.0)
        self.assertEqual(dev.z_of("RC"), 0.0, "the counter is floored at zero")
        dev.bump_z("RC", 0.9, 0.0)
        dev.bump_z("RC", 0.9, 1.0)
        self.assertAlmostEqual(dev.z_of("RC"), 0.8, places=9, msg="0.9 then 0.9 - 1.0")

    def test_sh_increments_are_unchanged_by_b1(self):
        """The constraint: SH keeps scale 1, so its increment is the committed rule exactly."""
        dev = self._device()
        dev.bump_z("SH", 0.9, 0.0)
        self.assertAlmostEqual(dev.z_of("SH"), 0.9, places=9)
        dev.bump_z("SH", 0.9, 1.0)
        self.assertAlmostEqual(dev.z_of("SH"), 0.8, places=9)

    def test_the_arm_switch_defaults_off(self):
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        for p in (str(live2), str(live2 / "fleet"), str(live2 / "scorer"),
                  str(live2.parents[0] / "baselines")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import arms_policy as AP
        self.assertFalse(AP.PolicyCoreArm().deficit_update,
                         "D122 requires every v1.1 fix to default OFF")

    def test_on_time_is_judged_at_the_first_token(self):
        """The application sees an answer at its first token, so that is the comparison."""
        import inspect
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        if str(live2) not in sys.path:
            sys.path.insert(0, str(live2))
        import arms_policy as AP
        src = inspect.getsource(AP.PolicyCoreArm._z_note_answer)
        self.assertIn("t_first_token", src)
        res = inspect.getsource(AP.PolicyCoreArm._z_resolve)
        self.assertIn('rec["deadline_abs"]', res)
        self.assertIn("bump_z", res)

    def test_a_declined_opportunity_still_resolves_as_a_miss(self):
        """Registering from the observation, not from admissions, is what makes this true."""
        import inspect
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        if str(live2) not in sys.path:
            sys.path.insert(0, str(live2))
        import arms_policy as AP
        src = inspect.getsource(AP.PolicyCoreArm._z_register)
        self.assertIn("obs.recall", src, "recall queries are registered from the observation")
        self.assertIn("sh_instant", src, "SH instants are registered from the D100 roster")
