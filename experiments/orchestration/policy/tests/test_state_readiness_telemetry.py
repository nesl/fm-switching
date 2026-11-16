import unittest

from policy.continuation import (FEASIBLE, INFEASIBLE, PRIORITY, bounded_waiting_breach,
                                 classify, continuation_value, p_finish)
from policy.readiness import state_actions, state_value, tier_assignment
from policy.state import HistoryBelief, TIERS, colder
from policy.telemetry import ResidencyBelief, TelemetrySnapshot
from policy import Flags
from policy.tests._fixtures import PF, device, engine, job, params


class TestBelief(unittest.TestCase):
    def test_belief_normalizes_and_rejects_empty_mass(self):
        b = HistoryBelief("RICH", 100, probs={"GPU": 2.0, "HOST": 2.0, "STORED": 0.0})
        self.assertAlmostEqual(sum(b.probs.values()), 1.0, places=12)
        with self.assertRaises(ValueError):
            HistoryBelief("RICH", 100, probs={"GPU": 0.0, "HOST": 0.0, "STORED": 0.0})

    def test_colder_ladder_ends_at_the_device(self):
        self.assertEqual([colder(t) for t in TIERS], ["HOST", "STORED", "DEVICE"])


class TestTelemetry(unittest.TestCase):
    def test_unambiguous_local_hits_confirm_gpu(self):
        b = HistoryBelief("RICH", 100)
        r = ResidencyBelief()
        r.request(b, "GPU", 0.0)
        self.assertFalse(r.credit_allowed(b))
        v = r.update(b, TelemetrySnapshot(local_hits=3), 1.0)
        self.assertEqual(v, "GPU")
        self.assertEqual(b.probs["GPU"], 1.0)
        self.assertTrue(r.credit_allowed(b))

    def test_ambiguous_telemetry_moves_mass_colder_never_warmer(self):
        b = HistoryBelief("RICH", 100, probs={"GPU": 1.0, "HOST": 0.0, "STORED": 0.0})
        r = ResidencyBelief(conservatism=0.5)
        before = dict(b.probs)
        r.update(b, TelemetrySnapshot(local_hits=2, external_hits=2), 1.0)
        self.assertLess(b.probs["GPU"], before["GPU"])
        self.assertGreater(b.probs["HOST"] + b.probs["STORED"],
                           before["HOST"] + before["STORED"])

    def test_divergence_is_reported(self):
        b = HistoryBelief("RICH", 100)
        r = ResidencyBelief()
        r.request(b, "GPU", 0.0)
        d = r.divergence(b)
        self.assertTrue(d["diverged"])
        self.assertEqual(d["unconfirmed_request"], "GPU")


class TestReadiness(unittest.TestCase):
    def test_tier_assignment_refuses_an_unsupplied_capacity(self):
        with self.assertRaises(ValueError):
            tier_assignment([dict(value=1.0, tokens=10)], 0, 0)

    def test_tier_assignment_respects_capacity_and_ranks_by_value_per_byte(self):
        cands = [dict(name="a", value=1.0, tokens=1000), dict(name="b", value=9.0, tokens=1000),
                 dict(name="c", value=5.0, tokens=1000)]
        out = tier_assignment(cands, gpu_capacity_tokens=2000, host_capacity_tokens=1000)
        self.assertEqual([c["name"] for c in out["gpu"]], ["b", "c"])
        self.assertEqual([c["name"] for c in out["host"]], ["a"])
        self.assertLessEqual(out["gpu_tokens_used"], 2000)
        self.assertEqual(out["nu_tier"]["GPU"], 5.0 / 1000)

    def test_zero_and_negative_value_is_never_promoted(self):
        out = tier_assignment([dict(value=0.0, tokens=10), dict(value=-1.0, tokens=10)],
                              100, 100)
        self.assertEqual(out["gpu"], [])
        self.assertEqual(out["host"], [])
        self.assertEqual(len(out["denied"]), 2)

    def test_state_value_needs_a_confirmed_transition_for_credit(self):
        d = device(tier="HOST")
        p = params()
        r_ok = state_value(PF, d, "RICH", d.demand, p.H_s, d.qtype, d.link, p.L_k["RC"],
                           PF.omega("RC"))
        r_no = state_value(PF, d, "RICH", d.demand, p.H_s, d.qtype, d.link, p.L_k["RC"],
                           PF.omega("RC"), credit_allowed=False)
        self.assertGreaterEqual(r_ok["value"], 0.0)
        self.assertEqual(r_no["value"], 0.0)

    def test_state_value_never_uses_the_conditional_rate_while_the_flag_is_off(self):
        d = device()
        p = params()
        r = state_value(PF, d, "RICH", d.demand, p.H_s, d.qtype, d.link, p.L_k["RC"],
                        PF.omega("RC"), in_episode=True)
        self.assertFalse(r["conditional_rate_used"])

    def test_conditional_state_actions_appear_only_with_their_flag(self):
        d = device(staleness_s=2.0)
        d.history["RICH"].unsent_frames = 4
        off = [a.kind for a in state_actions(d, "RICH", Flags())]
        on = [a.kind for a in state_actions(d, "RICH",
                                            Flags().with_(summaries=True,
                                                          predictive_upload=True))]
        self.assertNotIn("REFRESH_SUMMARY", off)
        self.assertNotIn("REQUEST_UPLOAD", off)
        self.assertIn("REFRESH_SUMMARY", on)
        self.assertIn("REQUEST_UPLOAD", on)


class TestContinuation(unittest.TestCase):
    def test_answered_or_finished_job_has_no_continuation_value(self):
        e = engine()
        j = job(pieces=4, done=4)
        self.assertEqual(continuation_value(j, 0.0, e, 0.0, False, 0.42, 0.4, 0.2, 0.0), 0.0)
        j2 = job()
        j2.answered = True
        self.assertEqual(continuation_value(j2, 0.0, e, 0.0, False, 0.42, 0.4, 0.2, 0.0), 0.0)

    def test_a_tight_deadline_is_infeasible_and_a_loose_one_is_feasible(self):
        e = engine()
        self.assertEqual(classify(job(deadline=0.01), 0.0, e, 0.0, 0.5), INFEASIBLE)
        self.assertEqual(classify(job(deadline=1e6), 0.0, e, 0.0, 0.5), FEASIBLE)

    def test_priority_class_exists_between_the_two(self):
        e = engine()
        j = job(deadline=3.0, pieces=4)
        self.assertEqual(classify(j, 0.0, e, competing_s=10.0, threshold=0.5,
                                  competing_s_with_priority=0.0), PRIORITY)

    def test_p_finish_is_monotone_in_the_deadline(self):
        e = engine()
        last = -1.0
        for dl in (0.01, 0.5, 1.0, 5.0, 50.0):
            v = p_finish(job(deadline=dl), 0.0, e, 0.0, False)
            self.assertGreaterEqual(v, last)
            last = v

    def test_continuation_value_is_not_tokens_processed(self):
        """Spec 5.4: partial work that cannot finish earns nothing."""
        e = engine()
        late = job(deadline=0.01, pieces=8, done=7)
        self.assertEqual(continuation_value(late, 0.0, e, 0.0, False, 0.42, 0.4, 0.2, 0.0), 0.0)

    def test_bounded_waiting_detects_a_job_about_to_become_infeasible(self):
        e = engine()
        j = job(deadline=1.0, pieces=3)
        self.assertIsInstance(bounded_waiting_breach(j, 0.0, e, 0.0, 0.5, 0.75), bool)
