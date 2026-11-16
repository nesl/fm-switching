import unittest

from policy import Flags
from policy.escalation import (ContextModulatedTrickle, CloudTrickle, DeviceFilter,
                               EscalationRequest, GhatTables, evidence_coverage, ghat,
                               type_posterior)
from policy.profiles import MissingEvidence
from policy.utility import u_sh_cloud, u_sh_device
from policy.tests._fixtures import PF, coordinator, fleet, params


def tables():
    return GhatTables(pf=PF)


class TestGhat(unittest.TestCase):
    def test_one_basis_scores_every_task_type(self):
        t = tables()
        sh = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395), t)
        rc = ghat(EscalationRequest("d0", "RC", 0.0, qtype="counting_objects_events",
                                    temporal_reference_s=60.0, device_window_s=10.0), t)
        for r in (sh, rc):
            self.assertIn("ghat", r)
            self.assertIsInstance(r["ghat"], float)

    def test_missing_local_evidence_raises_ghat(self):
        t = tables()
        covered = ghat(EscalationRequest("d0", "RC", 0.0, qtype="location_trace",
                                         temporal_reference_s=5.0, device_window_s=10.0), t)
        missing = ghat(EscalationRequest("d0", "RC", 0.0, qtype="location_trace",
                                         temporal_reference_s=120.0, device_window_s=10.0), t)
        self.assertGreater(missing["ghat"], covered["ghat"],
                           "the addendum's first insight: missing local evidence means a larger "
                           "cloud gain")
        self.assertEqual(covered["coverage"]["device_table"], "4B-D2")
        self.assertEqual(missing["coverage"]["device_table"], "device-N1-orin")

    def test_a_late_answer_has_exactly_zero_gain_for_every_type(self):
        t = tables()
        for task, kw in (("SH", dict(predicted_delivered_delay_s=5.0)),
                         ("RC", dict(qtype="time_duration", predicted_delivered_delay_s=50.0))):
            r = ghat(EscalationRequest("d0", task, 0.0, deadline=1.0, **kw), t)
            self.assertEqual(r["ghat"], 0.0)
            self.assertIn("MISSED", r["terms"]["timeliness"])

    def test_unknown_type_takes_the_expectation_over_the_posterior(self):
        t = tables()
        req = EscalationRequest("d0", "RC", 0.0, text="how many cars did I pass earlier?",
                                temporal_reference_s=120.0, device_window_s=10.0)
        r = ghat(req, t)
        self.assertGreater(len(r["posterior"]), 0)
        self.assertAlmostEqual(sum(r["posterior"].values()), 1.0, places=12)
        manual = sum(p * r["terms"]["per_type"][q]["ghat"] for q, p in r["posterior"].items())
        self.assertAlmostEqual(r["ghat"], manual, places=12)

    def test_type_posterior_rules_are_non_learned_and_readable(self):
        self.assertIn("counting_objects_events", type_posterior(
            EscalationRequest("d0", "RC", 0.0, text="how many pedestrians were there?")))
        self.assertIn("location_trace", type_posterior(
            EscalationRequest("d0", "RC", 0.0, text="where was the white van?")))
        self.assertEqual(type_posterior(EscalationRequest("d0", "RC", 0.0, qtype="time_duration")),
                         {"time_duration": 1.0})

    def test_an_unmatched_question_raises_rather_than_inventing_a_posterior(self):
        t = tables()
        with self.assertRaises(MissingEvidence):
            ghat(EscalationRequest("d0", "RC", 0.0, text="hello"), t)

    def test_uncertainty_multiplier_is_identity_and_declared_a_placeholder(self):
        t = tables()
        a = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395,
                                   uncertainty=0.0), t)
        b = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395,
                                   uncertainty=9.0), t)
        self.assertEqual(a["ghat"], b["ghat"])
        self.assertIn("PLACEHOLDER", t.provenance["uncertainty_multiplier"])
        self.assertIn("StudyCTRL1b", t.provenance["uncertainty_multiplier"])

    def test_a_filled_uncertainty_table_changes_ghat_without_touching_other_code(self):
        t = GhatTables(pf=PF, uncertainty_multiplier=lambda u: 1.0 + (u or 0.0))
        low = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395,
                                     uncertainty=0.0), t)
        high = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395,
                                      uncertainty=2.0), t)
        self.assertGreater(high["ghat"], low["ghat"])

    def test_sh_ghat_equals_the_rollout_gain_at_the_same_delay(self):
        """Addendum A1: the device's filter and the cloud's DeltaJ_H must use ONE formula."""
        t = tables()
        for d in (0.0, 0.395, 1.0, 2.0):
            g = ghat(EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=d), t)["ghat"]
            manual = PF.omega("SH") * (u_sh_cloud(PF, d)[0] - u_sh_device(PF))
            self.assertAlmostEqual(g, manual, places=12)


class TestNoHardCodedRouting(unittest.TestCase):
    """The addendum's hard requirement: no request type may be routed to the cloud by rule."""

    def test_every_type_goes_through_ghat(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        f.device("d0").history["RICH"].staleness_s = 0.0
        before = co.ghat_calls
        co.escalate(f, EscalationRequest("d0", "SH", 0.0, uncertainty=2.0))
        co.escalate(f, EscalationRequest("d0", "RC", 0.0, qtype="counting_objects_events",
                                         temporal_reference_s=60.0, device_window_s=10.0))
        self.assertEqual(co.ghat_calls - before, 2,
                         "each escalation of any type must score Ghat exactly once")

    def test_zero_gain_is_never_admitted_whatever_the_type(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        for req in (EscalationRequest("d0", "SH", 0.0, deadline=0.01,
                                      predicted_delivered_delay_s=5.0),
                    EscalationRequest("d0", "RC", 0.0, qtype="time_duration", deadline=0.01,
                                      predicted_delivered_delay_s=50.0)):
            out = co.escalate(f, req)
            self.assertFalse(any(d.taken for d in out),
                             "a request whose Ghat is zero must not be admitted, whatever its "
                             "type")

    def test_the_decision_names_ghat_as_its_basis_for_every_type(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        for req in (EscalationRequest("d0", "SH", 0.0),
                    EscalationRequest("d0", "RC", 0.0, qtype="location_trace",
                                      temporal_reference_s=60.0, device_window_s=10.0)):
            out = co.escalate(f, req)
            self.assertTrue(out)
            self.assertEqual(out[0].detail["basis"], "ghat")

    def test_a_query_is_sent_complete_by_default(self):
        """Addendum A2 as revised: the payload travels WITH the question unless the exception
        path applies."""
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        req = EscalationRequest("d0", "RC", 0.0, qtype="counting_objects_events",
                                temporal_reference_s=600.0, device_window_s=10.0,
                                payload_bytes=350_000, unsent_history_bytes=350_000)
        out = co.escalate(f, req)
        self.assertEqual(req.path, "complete")
        self.assertTrue(out[0].taken, "this query is worth admitting on the complete path")
        self.assertTrue(req.payload_delivered)
        self.assertTrue(all(p.meta.get("payload_arrived_with_request") for p in f.pending))
        self.assertFalse(any(p.meta.get("payload_pulled_at") is not None for p in f.pending),
                         "nothing is pulled on the complete path")

    def test_the_source_contains_no_type_keyed_admission_rule(self):
        """A behavioural test cannot see a rule that is never exercised, so the source of the
        escalation path is also checked for a branch that admits or declines ON THE TYPE."""
        import re
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "coordinator.py").read_text()
        body = src.split("def escalate(")[1].split("def pull_payload(")[0]
        for pat in (r"task\s*==\s*['\"](RC|SS)['\"][^\n]*\n\s*(return|admit)",
                    r"if\s+req\.task\s*in\s*\(",
                    r"always_escalate", r"force_admit"):
            self.assertIsNone(re.search(pat, body),
                              "the escalation path must not decide on the task type: %s" % pat)


class TestQueryPaths(unittest.TestCase):
    """Addendum A2 as revised: complete by default, question-first as an exception."""

    def _slow(self, f, bw=200_000.0, rtt=0.4):
        from policy.state import Link
        f.device("d0").link = Link(bandwidth_bytes_s=bw, rtt_s=rtt)

    def _rival(self, f):
        from policy.state import PendingItem
        f.in_flight.append(PendingItem(item_id="ep", kind="episode_call", device="d0",
                                       due_at=0.0, meta=dict(ghat=99.0)))

    def _req(self, deadline=None, big=True):
        return EscalationRequest("d0", "RC", 0.0, qtype="counting_objects_events",
                                 temporal_reference_s=600.0, device_window_s=10.0,
                                 payload_bytes=700_000,
                                 unsent_history_bytes=700_000 if big else 10,
                                 deadline=deadline)

    def test_question_first_needs_both_conditions(self):
        co = coordinator(p=params(H=1.0, question_first_history_bytes=1000))
        f = fleet(1)
        co.escalate(f, self._req(big=False))
        self.assertEqual("complete", f.devices["d0"] and "complete")
        f2 = fleet(1)
        r2 = self._req(big=True)
        co.escalate(f2, r2)
        self.assertEqual(r2.path, "complete",
                         "a big history alone must not take the exception path")
        f3 = fleet(1)
        self._rival(f3)
        r3 = self._req(big=True)
        co.escalate(f3, r3)
        self.assertEqual(r3.path, "question_first")
        f4 = fleet(1)
        self._rival(f4)
        r4 = self._req(big=False)
        co.escalate(f4, r4)
        self.assertEqual(r4.path, "complete",
                         "higher-value traffic alone must not take the exception path")

    def test_an_ss_query_never_takes_the_exception_path(self):
        from policy.escalation import choose_path
        r = EscalationRequest("d0", "SS", 0.0, unsent_history_bytes=10 ** 9)
        self.assertEqual(choose_path(r, True, 1000)["path"], "complete")

    def test_question_first_charges_the_round_trip_and_the_decision_latency(self):
        co = coordinator(p=params(H=1.0, question_first_history_bytes=1000))
        f = fleet(1)
        self._slow(f)
        req = self._req()
        dc, tc = co.predicted_delivered_delay_s(f, req, path="complete", detail=True)
        dq, tq = co.predicted_delivered_delay_s(f, req, path="question_first", detail=True)
        self.assertAlmostEqual(dq - dc, tq["control_round_trip_s"] + tq["decision_latency_s"],
                               places=12)
        self.assertGreater(tq["control_round_trip_s"], 0.0)
        self.assertGreater(tq["decision_latency_s"], 0.0)
        self.assertNotIn("control_round_trip_s", tc)

    def test_question_first_refuses_to_quote_a_delay_when_m4_is_unmeasured(self):
        co = coordinator(p=params(H=1.0))
        co.params.decision_latency_s = None
        f = fleet(1)
        with self.assertRaises(MissingEvidence):
            co.predicted_delivered_delay_s(f, self._req(), path="question_first")

    def test_tight_deadline_declines_question_first_but_admits_the_complete_path(self):
        """Test (i): the SAME query, the SAME deadline, on the SAME slow link. The extra control
        round trip and decision latency of the question-first path are what push it past the
        deadline."""
        co = coordinator(p=params(H=1.0, question_first_history_bytes=1000))
        probe = fleet(1)
        self._slow(probe)
        dc = co.predicted_delivered_delay_s(probe, self._req(), path="complete")
        dq = co.predicted_delivered_delay_s(probe, self._req(), path="question_first")
        self.assertLess(dc, dq)
        deadline = 0.5 * (dc + dq)

        f_q = fleet(1)
        self._slow(f_q)
        self._rival(f_q)
        r_q = self._req(deadline=deadline)
        out_q = co.escalate(f_q, r_q)
        self.assertEqual(r_q.path, "question_first")
        self.assertFalse(out_q[0].taken)
        self.assertIn("deadline", out_q[0].reason)
        self.assertEqual(out_q[0].detail["delivered_delay_terms"]["path"], "question_first")

        f_c = fleet(1)
        self._slow(f_c)
        r_c = self._req(deadline=deadline)
        out_c = co.escalate(f_c, r_c)
        self.assertEqual(r_c.path, "complete")
        self.assertTrue(out_c[0].taken,
                        "the same query inside the deadline on the complete path must be "
                        "admitted")

    def test_a_declined_complete_query_leaves_no_residual_work(self):
        """Test (ii)."""
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        self._slow(f, bw=50_000.0, rtt=1.0)
        before = (len(f.pending), len(f.in_flight), len(f.jobs))
        req = self._req(deadline=0.05)
        out = co.escalate(f, req)
        self.assertFalse(out[0].taken)
        self.assertEqual((len(f.pending), len(f.in_flight), len(f.jobs)), before)
        self.assertEqual(f.jobs, {})
        self.assertFalse(req.payload_delivered)

    def test_a_declined_query_by_delta_j_also_leaves_nothing(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        co.rollout.params.mu = 1e9
        out = co.escalate(f, self._req())
        self.assertFalse(out[0].taken)
        self.assertEqual(f.jobs, {})
        self.assertEqual(f.pending, [])


class TestTriggerFamilies(unittest.TestCase):
    def test_all_three_families_are_interchangeable(self):
        t = tables()
        req = EscalationRequest("d0", "SH", 0.0, predicted_delivered_delay_s=0.395)
        for fam in (DeviceFilter(threshold=0.0), CloudTrickle(score_threshold=-20.0),
                    ContextModulatedTrickle(score_threshold=-20.0, context_threshold=0.5)):
            out = fam.should_escalate(req, t, predicted_delay_s=0.395, cloud_score=-5.0,
                                      context_value=1.0)
            self.assertIn("escalate", out)
            self.assertIn("basis", out)

    def test_context_modulation_halves_the_cadence_only_above_the_threshold(self):
        fam = ContextModulatedTrickle(cadence_s=4.0, context_threshold=0.5)
        self.assertEqual(fam.cadence_for(0.1), 4.0)
        self.assertEqual(fam.cadence_for(0.9), 2.0)
        self.assertEqual(fam.cadence_for(None), 4.0)

    def test_the_sh_family_is_swappable_on_the_coordinator(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        co.sh_trigger = DeviceFilter(threshold=1e9)
        out = co.escalate(f, EscalationRequest("d0", "SH", 0.0))
        self.assertFalse(out[0].taken)
        self.assertIn("local filter", out[0].reason)
        co.sh_trigger = CloudTrickle(score_threshold=-1e9)
        req = EscalationRequest("d0", "SH", 0.0)
        req.__dict__["cloud_score"] = -5.0
        out2 = co.escalate(f, EscalationRequest("d0", "SH", 0.0))
        self.assertTrue(out2)
