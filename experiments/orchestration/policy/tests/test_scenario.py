import unittest

from policy import Flags
from policy.telemetry import ResidencyBelief, TelemetrySnapshot
from policy.tests._fixtures import PF, call_item, coordinator, fleet, job, params, piece_item


class TestScenario(unittest.TestCase):
    """One run of spec 8's main loop over a sequence of events, start to finish."""

    def _run(self, flags=None):
        co = coordinator(flags=flags, p=params(H=0.75))
        f = fleet(2)
        trace = []
        trace += co.on_event(f, dict(kind="escalation", task="SH", device="d0"))
        f.t = 0.5
        trace += co.on_event(f, dict(kind="escalation", task="RC", device="d1",
                                     qtype="counting_objects_events"))
        f.t = 1.0
        trace += co.on_event(f, dict(kind="timer"))
        f.t = 1.5
        trace += co.on_outage(f, "d1", 0.3)
        f.t = 2.0
        trace += co.on_event(f, dict(kind="telemetry"))
        f.t = 2.5
        trace += co.on_reconnect(f, "d1")
        trace += co.on_event(f, dict(kind="timer"))
        return co, f, trace

    def test_the_loop_runs_and_every_decision_is_explained(self):
        co, f, trace = self._run()
        self.assertTrue(trace)
        for d in trace:
            self.assertTrue(d.reason, "every decision must carry a reason")
            self.assertIn(d.kind, ("admission", "release", "state_action", "feasibility",
                                   "outage", "reconnect", "tier_assignment"))

    def test_an_rc_escalation_registers_a_job_only_if_it_is_admitted(self):
        """Addendum A2 as revised: a declined query is DISCARDED, so the job must not be a side
        effect of merely planning one."""
        co, f, trace = self._run()
        adm = [d for d in trace if d.kind == "admission"]
        self.assertTrue(adm)
        if any(d.taken for d in adm):
            j = list(f.jobs.values())[0]
            self.assertEqual(j.qtype, "counting_objects_events")
            self.assertEqual(j.rep, "RICH")
            self.assertGreaterEqual(j.pieces_total, 1)
        else:
            self.assertEqual(f.jobs, {}, "a declined query leaves no job behind")
            self.assertFalse([p for p in f.pending if p.kind == "rc_piece"])

    def test_an_outage_pauses_only_that_device(self):
        co = coordinator(p=params(H=0.75))
        f = fleet(2)
        f.pending += [call_item("d0", 0.0, "a"), call_item("d1", 0.0, "b")]
        co.on_outage(f, "d1", 0.3)
        self.assertEqual([p.item_id for p in f.pending], ["a"])

    def test_the_scenario_is_reproducible(self):
        a = [(d.kind, d.target, d.taken, round(d.delta_j or 0.0, 12)) for d in self._run()[2]]
        b = [(d.kind, d.target, d.taken, round(d.delta_j or 0.0, 12)) for d in self._run()[2]]
        self.assertEqual(a, b)

    def test_turning_every_conditional_on_does_not_crash_the_loop(self):
        """The conditional half of the spec is OFF by default, but it must still be executable,
        or 'evaluated on and off' (spec header) would be impossible."""
        on = Flags().with_(escalation_price=True, phase_assignment=True, merging=True,
                           summaries=True, predictive_upload=True)
        co, f, trace = self._run(flags=on)
        self.assertTrue(trace)
        self.assertTrue(any(d.kind == "admission" for d in trace))

    def test_a_held_call_with_merging_off_is_a_device_outcome(self):
        """CHANGED FOR D98: a far-future call is now DISPATCHED, because its instant is credited
        at its own deadline rather than being worth zero for falling outside t0 + H; the
        hold-is-a-device-outcome branch is now reached by a call that cannot be delivered by
        c_i + L_SH, which is what spec 7.9 actually describes."""
        co = coordinator(p=params(H=0.75))
        f = fleet(1)
        it = call_item("d0", 10.0, "far_future")
        f.pending.append(it)
        self.assertEqual(co.hold_or_merge(f, it, next_due_at=10.5)["action"], "dispatch")

        co2 = coordinator(p=params(H=0.5))
        g = fleet(1)
        g.in_flight.append(piece_item("d0", 0.0, "big", deadline=100.0, tokens=7000,
                                      job_id="jbig"))
        g.jobs["jbig"] = job(pieces=1, done=0)
        late = call_item("d0", 0.0, "late")
        g.pending.append(late)
        r = co2.hold_or_merge(g, late, next_due_at=0.5)
        self.assertEqual(r["action"], "hold_then_device_outcome")
        self.assertIn("device-only outcome", r["note"])

    def test_scoring_calls_are_counted_for_m4(self):
        co, f, trace = self._run()
        self.assertGreater(co.scoring_calls, 0)

    def test_telemetry_confirms_a_requested_promotion_and_restores_credit(self):
        co = coordinator(p=params(H=0.75))
        f = fleet(1)
        b = f.device("d0").history["RICH"]
        r = ResidencyBelief(conservatism=co.params.belief_conservatism)
        r.request(b, "GPU", 0.0)
        self.assertFalse(r.credit_allowed(b))
        r.update(b, TelemetrySnapshot(local_hits=5), 1.0)
        self.assertTrue(r.credit_allowed(b))
        self.assertEqual(r.divergence(b)["believed"], "GPU")
        self.assertFalse(r.divergence(b)["diverged"])
