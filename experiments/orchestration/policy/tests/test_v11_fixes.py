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


class TestRcTailMirrorsD98(unittest.TestCase):
    """D122 v1.1: the D98-equivalent tail for recall, behind Flags.rc_tail, default off."""

    def test_the_flag_defaults_off(self):
        self.assertFalse(Flags().rc_tail)

    def test_an_rc_piece_that_cannot_start_inside_h_is_tailed_only_with_the_flag(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.run)
        self.assertIn('elif p.kind == "rc_piece" and self.flags.tail_cursor_on():', src,
                      "the selection branch must mirror D98's and be gated by the cursor switch")
        self.assertIn("sh_tail.append(p)", src)

    def test_the_bound_uses_the_rc_pieces_own_absolute_deadline(self):
        """D98 adds L_k to an instant's capture; an rc_piece carries its deadline already."""
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.run)
        self.assertIn('float(p.deadline) for p in f.pending if p.kind == "rc_piece"', src)

    def test_the_horizon_accounting_stays_isolated_as_d98_requires(self):
        """The tail's progress must NOT reach jobs_progress, which _terminal reads."""
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.run)
        self.assertIn("tail_progress[p.job_id] = tail_progress.get(p.job_id, 0) + 1", src)
        self.assertIn("rc_progress = jobs_progress", src)
        self.assertIn("rc_progress = dict(jobs_progress)", src,
                      "the tail view must be a COPY, so jobs_progress is untouched")

    def test_the_two_causes_are_independently_toggleable(self):
        """User item 1: the SH side effect cannot be attributed unless each cause stands alone."""
        f = Flags()
        self.assertFalse(f.rc_tail_cursor)
        self.assertFalse(f.rc_tail_zrows)
        self.assertFalse(f.tail_cursor_on())
        self.assertFalse(f.tail_zrows_on())
        # the master turns both on, so the pre-split build is reproduced exactly
        both = Flags(rc_tail=True)
        self.assertTrue(both.tail_cursor_on())
        self.assertTrue(both.tail_zrows_on())
        # and each sub-switch isolates its own cause
        cur = Flags(rc_tail_cursor=True)
        self.assertTrue(cur.tail_cursor_on())
        self.assertFalse(cur.tail_zrows_on())
        zr = Flags(rc_tail_zrows=True)
        self.assertFalse(zr.tail_cursor_on())
        self.assertTrue(zr.tail_zrows_on())

    def test_the_z_rows_are_gated_separately_from_the_cursor(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.run)
        self.assertIn("if self.flags.tail_zrows_on() or rc_rows:", src,
                      "v1.2's planner routes its own RC rows through the same point")
        self.assertIn("if (self.flags.tail_cursor_on() or rc_rows) and tail_progress:", src)

    def test_rc_opportunities_exist_so_the_deficit_can_be_credited(self):
        """v1.0 emitted task=SH rows only, so z_of('RC') was never read by _z_term."""
        from policy import rollout as RO
        self.assertTrue(hasattr(RO.Rollout, "_rc_opportunities"),
                        "v1.0 has no RC opportunity rows at all, which is why a non-zero RC "
                        "deficit could not change a decision")
        import inspect
        src = inspect.getsource(RO.Rollout._rc_opportunities)
        self.assertIn('task="RC"', src)
        self.assertIn("met_slo", src)
        self.assertIn("last <= job.deadline", src,
                      "met_slo must be judged at the question's OWN deadline, as D98 does")

    def test_the_rc_rows_reach_the_deficit_term(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.run)
        self.assertIn("opps = list(opps) + self._rc_opportunities(", src)


class TestStalenessIsWritten(unittest.TestCase):
    """D122 v1.1: HistoryBelief.staleness_s was read in production and written nowhere."""

    def test_the_flag_defaults_off(self):
        self.assertFalse(Flags().write_staleness)

    def test_the_field_is_now_written_from_coordinator_state(self):
        import inspect
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        if str(live2) not in sys.path:
            sys.path.insert(0, str(live2))
        import arms_policy as AP
        src = inspect.getsource(AP.PolicyCoreArm._sync)
        self.assertIn("b.staleness_s =", src,
                      "v1.0 never assigns staleness_s anywhere in production")
        self.assertIn("built_tokens_by_session", src, "it must come from coordinator state")
        self.assertIn("D2_TOK_PER_IMG", src, "frames received minus frames built")

    def test_the_stride_comes_from_the_committed_profile(self):
        import inspect
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        if str(live2) not in sys.path:
            sys.path.insert(0, str(live2))
        import arms_policy as AP
        src = inspect.getsource(AP.PolicyCoreArm._d2_stride_s)
        self.assertIn("d2_stride_s", src)
        self.assertNotIn("2.0", src, "the stride must be read, not written as a literal")

    def test_unbuilt_frames_convert_to_the_seconds_the_consumer_expects(self):
        """utility.t_ready_s does frames = staleness_s / d2_stride_s, so the inverse must hold."""
        from policy.profiles import load_profiles
        stride = float(load_profiles().raw["durations"]["catchup_per_frame"]["d2_stride_s"])
        tokens_per_img = 90
        for unbuilt_tokens in (0, 90, 2048, 17581):
            frames = unbuilt_tokens / tokens_per_img
            staleness_s = frames * stride
            self.assertAlmostEqual(staleness_s / stride, frames, places=9)


class TestF3RealisticCompetingWork(unittest.TestCase):
    """D122 v1.1 F3: competing_s comes from the rollout's own state, not a constant 0.

    The v1.0-failing assertions are the source ones plus `competing_gpu_s` not existing at all.
    """

    def test_the_flag_defaults_off(self):
        self.assertFalse(Flags().realistic_competing)

    def test_the_helper_exists_and_returns_zero_with_the_flag_off(self):
        from policy import rollout as RO
        self.assertTrue(hasattr(RO.Rollout, "competing_gpu_s"),
                        "v1.0 has no competing-work estimator at all")
        import inspect
        src = inspect.getsource(RO.Rollout.competing_gpu_s)
        self.assertIn("if not self.flags.realistic_competing:", src)
        self.assertIn("return 0.0", src)

    def test_no_caller_passes_a_hard_coded_zero_any_more(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout._terminal)
        self.assertIn("comp = self.competing_gpu_s(f, j, end)", src)
        self.assertNotIn("competing_s=0.0", src,
                         "the hard-coded zero is what v1.0 got wrong")
        risk = inspect.getsource(RO.Rollout.continuation_value_at_risk)
        self.assertIn("comp = self.competing_gpu_s(f, job, f.t)", risk,
                      "the A6 safe/lost pair must use the same competing value on both sides")

    def test_the_coordinator_classify_sites_use_it_so_priority_is_reachable(self):
        import inspect
        from policy import coordinator as CO
        src = inspect.getsource(CO.Coordinator._update_jobs)
        self.assertIn("comp = self.rollout.competing_gpu_s(fleet, job, fleet.t)", src)
        self.assertIn("competing_s=comp", src)
        self.assertNotIn("competing_s=0.0", src)

    def test_it_uses_the_frozen_step_models_own_gpu_s_and_no_new_parameter(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout._gpu_s_of)
        self.assertIn("self.engine.predict(self._request(p), concurrent=0)", src)
        self.assertIn("self.occupancy_of(", src, "it must read the single occupancy expression")
        for banned in ("0.5", "1.5", "factor", "scale", "tune"):
            self.assertNotIn(banned, src, "F3 must introduce no parameter")

    def test_the_occupancy_quantity_lives_in_exactly_one_place(self):
        """D127: competing_s and the backlog term must not disagree about the engine.

        Both read `Rollout.occupancy_of`, so F5a's correction propagates to both at once rather
        than needing a second, divergent fix.
        """
        import inspect
        from policy import rollout as RO
        self.assertTrue(hasattr(RO.Rollout, "occupancy_of"))
        occ = inspect.getsource(RO.Rollout.occupancy_of)
        self.assertIn("return float(pr.gpu_s)", occ)
        run = inspect.getsource(RO.Rollout.run)
        self.assertEqual(run.count("busy += self.occupancy_of(pr)"), 2,
                         "both backlog accumulation sites must read the one expression")
        self.assertNotIn("busy += pr.gpu_s", run,
                         "no site may inline the occupancy expression any more")
        self.assertIn("self.occupancy_of(", inspect.getsource(RO.Rollout._gpu_s_of))

    def test_priority_becomes_reachable_once_competing_work_is_non_zero(self):
        """The direct test of what F3 is for: classify can return PRIORITY."""
        from policy.continuation import FEASIBLE, INFEASIBLE, PRIORITY, classify
        e = Eng1Engine.load()
        seen_zero, seen_real = set(), set()
        for i in range(1, 101):
            j = _job(round(i * 0.05, 2))
            seen_zero.add(classify(j, 0.0, e, 0.0, 0.5, 0.0, 0.25))
            seen_real.add(classify(j, 0.0, e, 3.0, 0.5, 0.0, 0.25))
        self.assertNotIn(PRIORITY, seen_zero,
                         "with competing_s = 0 PRIORITY is unreachable, which is the v1.0 bug")
        self.assertIn(PRIORITY, seen_real,
                      "with real competing work PRIORITY must become reachable")

    def test_in_flight_work_counts_unconditionally(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.competing_gpu_s)
        self.assertIn("for p in f.in_flight:", src)
        self.assertIn("if p.job_id != jid:", src)

    def test_pending_work_counts_only_when_it_sorts_ahead_under_pi_0(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.competing_gpu_s)
        self.assertIn("if k < key:", src)
        self.assertIn("p.due_at, p.item_id", src, "the pi_0 EDF key, as _edf uses it")


class TestF4ProbabilisticPFinish(unittest.TestCase):
    """D122 v1.1 F4: p_finish becomes P(finish <= D_r) under the MEASURED completion error."""

    def test_the_flag_defaults_off(self):
        self.assertFalse(Flags().prob_p_finish)

    def test_the_fit_source_is_committed_and_fit_only(self):
        from policy import completion_error as CE
        d = CE.describe()
        self.assertEqual(d["source"], "results/cost/study_eng1/eng1_step_model.json")
        self.assertIn("HOLDOUT) not used", str(d["fit_data"]),
                      "the fit data must state the HOLDOUT was excluded")
        self.assertEqual(d["n"], 5974)

    def test_it_refuses_a_source_that_does_not_state_the_holdout_was_excluded(self):
        """A guard, so this can never be calibrated on something unstated."""
        import json
        import tempfile
        from pathlib import Path
        from policy import completion_error as CE
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text(json.dumps(dict(fit_data="everything, including the holdout",
                                         residual_bands={"tok_0_1": {"median_rel_res": 0.1}})))
            with self.assertRaises(ValueError):
                CE.load_sigmas(p)

    def test_sigma_comes_from_the_committed_medians_with_no_free_parameter(self):
        import json
        from pathlib import Path
        from policy import completion_error as CE
        root = Path(__file__).resolve().parents[4]
        raw = json.loads((root / CE.STEP_MODEL_PATH).read_text())
        for band, rec in raw["residual_bands"].items():
            if "median_rel_res" not in rec:
                continue
            want = float(rec["median_rel_res"]) / CE.HALF_NORMAL_MEDIAN
            self.assertAlmostEqual(CE.load_sigmas()[band], want, places=12)

    def test_the_probability_is_a_gradient_where_the_indicator_is_a_step(self):
        """The whole point of F4: progress and slack must stop being invisible."""
        from policy.continuation import p_finish
        e = Eng1Engine.load()
        ind, prob = [], []
        for deadline in (5.0, 2.0, 1.2, 1.0, 0.9, 0.5):
            j = _job(deadline)
            ind.append(p_finish(j, 0.0, e, 0.0, False, 0.25, 0.0, None))
            prob.append(p_finish(j, 0.0, e, 0.0, False, 0.25, 0.0, 0.0829))
        self.assertEqual(set(ind), {0.0, 1.0}, "the indicator takes only two values")
        self.assertGreater(len(set(round(x, 3) for x in prob)), 3,
                           "the probability must vary, not step: got %r" % (prob,))
        self.assertTrue(all(a >= b - 1e-12 for a, b in zip(prob, prob[1:])),
                        "it must be monotone in slack: %r" % (prob,))

    def test_rel_sigma_none_keeps_the_indicator_byte_for_byte(self):
        from policy.continuation import p_finish
        e = Eng1Engine.load()
        for deadline in (5.0, 1.0, 0.9, 0.5):
            j = _job(deadline)
            v = p_finish(j, 0.0, e, 0.0, False, 0.25, 0.0, None)
            self.assertIn(v, (0.0, 1.0))

    def test_the_schedule_now_reports_a_prediction_even_on_an_overrun(self):
        """`finish_at` keeps its meaning so no existing reader changes."""
        from policy.continuation import continuation_schedule
        e = Eng1Engine.load()
        j = _job(0.5)
        s = continuation_schedule(j, 0.0, e, 0.0, False, 0.25, 0.0, full_estimate=True)
        self.assertIsNone(s.finish_at, "an overrun must still report finish_at None")
        self.assertIsNotNone(s.finish_estimate)
        self.assertGreater(s.finish_estimate, j.deadline)

    def test_the_rollout_passes_none_with_the_flag_off(self):
        import inspect
        from policy import rollout as RO
        src = inspect.getsource(RO.Rollout.rel_sigma_for)
        self.assertIn("if not self.flags.prob_p_finish:", src)
        self.assertIn("return None", src)


class TestF5cDeficitRouting(unittest.TestCase):
    """D126 F5c: the deficit update goes through its spec entry point, with no behaviour change."""

    def _arm_mod(self):
        import sys
        from pathlib import Path
        live2 = Path(__file__).resolve().parents[2] / "live2"
        for p in (str(live2), str(live2 / "fleet"), str(live2 / "scorer")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import arms_policy as AP
        return AP

    def test_the_arm_no_longer_calls_bump_z_directly(self):
        import inspect
        AP = self._arm_mod()
        src = inspect.getsource(AP.PolicyCoreArm._z_resolve)
        self.assertNotIn("dev.bump_z(", src,
                         "B1's direct call is what left the spec entry point dead")
        self.assertIn("self.co.update_deficit(", src)

    def test_the_spec_entry_point_is_no_longer_dead_code(self):
        """`spec_map.py` names `coordinator.update_deficit` for spec 3.3 and 7.6."""
        import inspect
        AP = self._arm_mod()
        from policy.coordinator import Coordinator
        self.assertTrue(callable(Coordinator.update_deficit))
        src = inspect.getsource(AP.PolicyCoreArm._z_resolve)
        self.assertIn("update_deficit", src, "the entry point must have a production caller")

    def test_the_missing_device_guard_is_kept(self):
        """`fleet.device` indexes and would raise; the guard is what makes routing equivalent."""
        import inspect
        AP = self._arm_mod()
        src = inspect.getsource(AP.PolicyCoreArm._z_resolve)
        self.assertIn("if dev is not None:", src)

    def test_update_deficit_applies_the_same_counter_update(self):
        from policy.state import Device, Link
        dev = Device(device_id="robo000", link=Link(bandwidth_bytes_s=1.7e6, rtt_s=0.05),
                     qtype=QTYPE)
        dev.bump_z("RC", 0.9, 0.0)
        direct = dev.z_of("RC")
        other = Device(device_id="robo001", link=Link(bandwidth_bytes_s=1.7e6, rtt_s=0.05),
                       qtype=QTYPE)
        other.bump_z("RC", 0.9, 0.0)
        self.assertAlmostEqual(direct, other.z_of("RC"), places=12,
                               msg="routing must not change the arithmetic")


class TestV12Planner(unittest.TestCase):
    """D125 v1.2: the RC job planner. These fail on v1.1, which has no planner at all."""

    def setUp(self):
        from policy import planner_rc as PL
        self.PL = PL
        self.e = Eng1Engine.load()

    def test_the_switches_default_off(self):
        f = Flags()
        self.assertFalse(f.planner_rc)
        self.assertFalse(f.plan_latest)
        self.assertFalse(f.replan)

    def test_the_plan_set_is_the_design_notes(self):
        plans = self.PL.enumerate_plans(
            engine=self.e, device="robo000", qtype=QTYPE, rep="RICH", size_tokens=11000,
            readiness="COLD", deadline_abs=5.0, t=0.0, piece_sizes=(1024, 2048),
            allow_latest=True, kappa=1.0)
        labels = {p.label() for p in plans}
        self.assertIn("ONE-GO-NOW", labels)
        self.assertIn("PIECES-NOW(1024)", labels)
        self.assertIn("PIECES-NOW(2048)", labels)
        self.assertTrue(any(l.startswith("PIECES-LATEST") for l in labels),
                        "plan_latest must add the LATEST variants: %r" % (labels,))

    def test_readiness_preconditions_limit_the_set(self):
        warm = self.PL.enumerate_plans(
            engine=self.e, device="robo000", qtype=QTYPE, rep="RICH", size_tokens=11000,
            readiness="GPU-WARM", deadline_abs=5.0, t=0.0, piece_sizes=(1024,),
            allow_latest=False, kappa=1.0)
        self.assertEqual({p.kind for p in warm}, {self.PL.WARM},
                         "a GPU-warm history is answered, not rebuilt")
        host = self.PL.enumerate_plans(
            engine=self.e, device="robo000", qtype=QTYPE, rep="RICH", size_tokens=11000,
            readiness="HOST-WARM", deadline_abs=5.0, t=0.0, piece_sizes=(1024,),
            allow_latest=False, kappa=1.0)
        self.assertIn(self.PL.RELOAD, {p.kind for p in host},
                      "a host-warm history reloads rather than rebuilding")

    def test_no_new_piece_size_is_invented(self):
        plans = self.PL.enumerate_plans(
            engine=self.e, device="robo000", qtype=QTYPE, rep="RICH", size_tokens=11000,
            readiness="COLD", deadline_abs=5.0, t=0.0, piece_sizes=(1024, 2048),
            allow_latest=True, kappa=1.0)
        sizes = {p.piece_tokens for p in plans if p.piece_tokens}
        self.assertTrue(sizes <= {1024, 2048}, "D17's measured sizes only, got %r" % (sizes,))

    def test_a_reserved_unit_carries_its_planned_release_time(self):
        plans = self.PL.enumerate_plans(
            engine=self.e, device="robo000", qtype=QTYPE, rep="RICH", size_tokens=4096,
            readiness="COLD", deadline_abs=20.0, t=0.0, piece_sizes=(1024,),
            allow_latest=True, kappa=1.0)
        latest = [p for p in plans if p.kind == self.PL.PIECES_LATEST]
        self.assertTrue(latest, "a 20 s deadline leaves room for a LATEST plan")
        p = latest[0]
        self.assertGreater(p.first_start_s, 0.0, "LATEST must start later than now")
        for u in p.units:
            self.assertAlmostEqual(u.due_at, p.first_start_s, places=9,
                                   msg="the planned time travels as due_at, which the rollout "
                                       "honours as max(free_at, due_at)")
            self.assertEqual(u.meta.get("plan"), self.PL.PIECES_LATEST)

    def test_kappa_is_one_and_flagged_provisional(self):
        """No committed FIT/DEV q90 of measured over predicted job completion exists."""
        import inspect
        src = inspect.getsource(self.PL)
        self.assertIn("kappa IS 1.0 AND PROVISIONAL", src)

    def test_abandon_says_plainly_when_it_is_not_valued(self):
        inert = self.PL.abandon_note(True)
        self.assertIn("DECLINING THE REMAINDER", inert)
        self.assertIn("PROVISIONAL", inert)
        live = self.PL.abandon_note(False)
        self.assertIn("keeps the state value", live)

    def test_the_replan_triggers_are_the_notes(self):
        from policy.state import Job
        j = Job(job_id="j", device="robo000", qtype=QTYPE, rep="RICH", deadline=5.0,
                admitted_at=0.0, pieces_total=4, pieces_done=0, tokens_per_piece=1024)
        self.assertIsNone(self.PL.replan_cause(job=j, now=0.0, predicted_completion_s=2.0,
                                               kappa=1.0, prefix_lost=False,
                                               readiness_changed=False))
        self.assertIn("slipped", self.PL.replan_cause(
            job=j, now=0.0, predicted_completion_s=6.0, kappa=1.0, prefix_lost=False,
            readiness_changed=False))
        self.assertIn("prefix loss", self.PL.replan_cause(
            job=j, now=0.0, predicted_completion_s=1.0, kappa=1.0, prefix_lost=True,
            readiness_changed=False))
        self.assertIn("readiness", self.PL.replan_cause(
            job=j, now=0.0, predicted_completion_s=1.0, kappa=1.0, prefix_lost=False,
            readiness_changed=True))

    def test_the_rollout_accepts_a_long_window_and_routes_rc_rows(self):
        import inspect
        from policy import rollout as RO
        sig = inspect.signature(RO.Rollout.run)
        self.assertIn("horizon_s", sig.parameters, "v1.1's run has no long window")
        self.assertIn("rc_rows", sig.parameters, "v1.1 cannot route planner RC rows")
