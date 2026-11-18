import copy
import unittest

from policy import Flags
from policy.profiles import MissingEvidence
from policy.rollout import delta_j
from policy.t0_harness import HoldoutRefused, T0Harness, synthetic_dataset
from policy.spec_map import AMBIGUITIES, SPEC_MAP, check
from policy.tests._fixtures import (PF, call_item, coordinator, device, engine, fleet, job,
                                    params, piece_item, rollout)


class TestRollout(unittest.TestCase):
    def test_an_empty_fleet_scores_exactly_zero(self):
        ro = rollout()
        f = fleet(1)
        r = ro.run(f)
        self.assertAlmostEqual(r.u_hat, 0.0, places=12)
        self.assertAlmostEqual(r.z_term, 0.0, places=12)
        self.assertEqual(r.deliveries, [])

    def test_device_only_is_the_zero_of_the_gain_scale(self):
        ro = rollout()
        f = fleet(1)
        self.assertTrue(all(abs(o["utility"] - o["device_utility"]) < 1e-12
                            for o in ro.run(f).opportunities))

    def test_eligible_opportunities_are_counted_whether_escalated_or_not(self):
        ro = rollout(p=params(H=1.0))
        f = fleet(2)
        r = ro.run(f)
        self.assertEqual(len(r.opportunities), 2 * int(1.0 / ro.params.T_k["SH"]))

    def test_releasing_a_cloud_call_is_positive_wherever_its_instant_falls(self):
        """CHANGED FOR D98: per-instant SH value makes a call worth its OWN instant's value, so a
        late-in-the-horizon capture is no longer worth less than an early one (the old assertion
        `late < good` tested the retired display-freshness rule, not the claim)."""
        ro = rollout(p=params(H=1.0))
        f = fleet(1)
        f.pending.append(call_item("d0", 0.0))
        good = delta_j(ro, f, dict(kind="dispatch", item_id="call0"))
        self.assertGreater(good["delta_j"], 0.0)
        far = copy.deepcopy(f)
        far.pending = [call_item("d0", 0.95, "late")]
        late = delta_j(ro, far, dict(kind="dispatch", item_id="late"))
        self.assertGreater(late["delta_j"], 0.0)
        self.assertAlmostEqual(late["delta_j"], good["delta_j"], places=12)


class TestD98PerInstantSH(unittest.TestCase):
    """D98: each SH instant is credited at its own deadline c_i + L_SH, even past t0 + H.

    Spec 5.1 and 6.3 as amended. The retired rule credited only the cadence points inside
    [t0, t0 + H), which made a monitoring call's marginal value structurally zero whenever
    H <= T_k (StudyLIVE2-coord open issue 1).
    """

    def _busy_fleet(self, tokens: int):
        """One device, one SH instant captured at t0, and an in-flight RC piece that keeps the
        engine busy for about `tokens` / 4,500 s, so the call's delivery is pushed past the
        horizon by a controllable amount."""
        f = fleet(1)
        f.in_flight.append(piece_item("d0", 0.0, "big", deadline=100.0, tokens=tokens,
                                      job_id="jbig"))
        f.jobs["jbig"] = job(pieces=1, done=0)
        f.pending.append(call_item("d0", 0.0, "c0"))
        return f

    def test_sh_admission_is_not_structurally_zero_at_h_equal_to_the_cadence(self):
        ro = rollout(p=params(H=0.5))
        self.assertEqual(ro.params.H, ro.params.T_k["SH"])
        f = fleet(1)
        f.pending.append(call_item("d0", 0.0, "c0"))
        self.assertGreater(delta_j(ro, f, dict(kind="dispatch", item_id="c0"))["delta_j"], 0.0)

    def test_a_delivery_after_its_own_deadline_is_not_worth_admitting(self):
        """b: predicted delivery 1.770 s against a deadline of 0.0 + 1.5 s, so the instant takes
        the DEVICE value and DeltaJ(admit) <= 0."""
        ro = rollout(p=params(H=0.5))
        f = self._busy_fleet(7000)
        r = ro.run(f, release_now=["c0"])
        self.assertEqual(r.detail["sh_tail_simulated"], 1)
        o = [x for x in r.opportunities if x["t"] == 0.0][0]
        self.assertEqual(o["served_by"], "device")
        self.assertGreater(r.deliveries[0]["delivered_at"], o["deadline"])
        self.assertLessEqual(delta_j(ro, f, dict(kind="dispatch", item_id="c0"))["delta_j"], 0.0)

    def test_a_delivery_in_time_but_past_the_horizon_is_worth_admitting(self):
        """c: predicted delivery 0.881 s, past t0 + H = 0.5 s but inside the deadline 1.5 s, so
        the instant takes the CLOUD value and DeltaJ(admit) > 0 (spec 6.3: never worth zero
        merely because it lands after the horizon)."""
        ro = rollout(p=params(H=0.5))
        f = self._busy_fleet(3000)
        r = ro.run(f, release_now=["c0"])
        o = [x for x in r.opportunities if x["t"] == 0.0][0]
        self.assertEqual(o["served_by"], "cloud")
        self.assertGreater(r.deliveries[0]["delivered_at"], 0.5)
        self.assertLessEqual(r.deliveries[0]["delivered_at"], o["deadline"])
        self.assertTrue(o["beyond_horizon"])
        self.assertGreater(delta_j(ro, f, dict(kind="dispatch", item_id="c0"))["delta_j"], 0.0)

    def test_an_sh_call_in_flight_at_t0_is_credited_at_its_own_deadline(self):
        ro = rollout(p=params(H=0.5))
        f = fleet(1)
        f.in_flight.append(call_item("d0", 0.0, "inflight"))
        r = ro.run(f)
        self.assertTrue(any(d["item_id"] == "inflight" and d.get("in_flight_at_t0")
                            for d in r.deliveries))
        self.assertEqual([x["served_by"] for x in r.opportunities if x["t"] == 0.0], ["cloud"])

    def test_the_opportunity_list_keeps_one_entry_per_credited_instant(self):
        ro = rollout(p=params(H=1.0))
        f = fleet(2)
        f.pending.append(call_item("d0", 0.25, "off_grid"))
        r = ro.run(f)
        self.assertEqual(len(r.opportunities), 2 * int(1.0 / ro.params.T_k["SH"]) + 1)
        self.assertEqual(len({(o["device"], o["t"]) for o in r.opportunities}),
                         len(r.opportunities))

    def test_a_device_served_instant_contributes_exactly_zero_to_u_hat(self):
        """Why the instant SET may differ between the two branches of an admit without biasing
        DeltaJ: spec 3.2's scale is a GAIN against the device answer (ambiguity A2)."""
        ro = rollout(p=params(H=1.0))
        a = ro.run(fleet(1))
        f = fleet(1)
        f.pending.append(call_item("d0", 0.25, "off_grid"))
        b = ro.run(f, exclude=["off_grid"])
        self.assertEqual(len(b.opportunities), len(a.opportunities) + 1)
        self.assertAlmostEqual(a.u_hat, b.u_hat, places=12)

    def test_the_tail_pass_charges_nothing_to_the_horizons_own_accounting(self):
        ro = rollout(p=params(H=0.5))
        f = self._busy_fleet(3000)
        with_call = ro.run(f, release_now=["c0"])
        without = ro.run(f, exclude=["c0"])
        self.assertEqual(with_call.detail["sh_tail_simulated"], 1)
        self.assertAlmostEqual(with_call.engine_busy_s, without.engine_busy_s, places=12)
        self.assertAlmostEqual(with_call.residual_backlog_s, without.residual_backlog_s,
                               places=12)

    def test_delta_j_is_deterministic(self):
        ro = rollout()
        f = fleet(1)
        f.pending.append(call_item())
        a = delta_j(ro, f, dict(kind="dispatch", item_id="call0"))["delta_j"]
        b = delta_j(ro, f, dict(kind="dispatch", item_id="call0"))["delta_j"]
        self.assertEqual(a, b)

    def test_delta_j_does_not_mutate_the_fleet(self):
        ro = rollout()
        f = fleet(1)
        f.pending.append(call_item())
        before = (len(f.pending), len(f.in_flight), f.t)
        delta_j(ro, f, dict(kind="dispatch", item_id="call0"))
        self.assertEqual((len(f.pending), len(f.in_flight), f.t), before)

    def test_only_the_four_reference_actions_are_accepted(self):
        ro = rollout()
        f = fleet(1)
        with self.assertRaises(ValueError):
            delta_j(ro, f, dict(kind="whatever"))

    def test_terminal_value_counts_each_question_once(self):
        """Addendum A6.3 with v3 5.3: a prefix may be valued BOTH as the job's own question at
        risk AND as readiness for future questions, but never twice for the same question."""
        ro = rollout()
        f = fleet(1)
        j = job(done=1)
        f.jobs[j.job_id] = j
        r = ro.run(f)
        cont = r.detail["terminal"]["continuation"]
        sv = r.detail["terminal"]["state_value"]
        self.assertTrue(cont)
        self.assertTrue(sv, "A6.3: the prefix still earns state value for FUTURE questions")
        ckeys = {tuple(x["counts_question"]) for x in cont}
        skeys = {tuple(x["counts_question"]) for x in sv}
        self.assertFalse(ckeys & skeys)
        self.assertEqual([x["excluded_job"] for x in sv], [j.job_id],
                         "the state-value row must record which in-progress job it excludes")

    def test_mu_prices_only_backlog_beyond_the_horizon(self):
        ro = rollout(p=params(H=0.5, mu=1.0))
        f = fleet(1)
        for i in range(6):
            f.pending.append(piece_item(iid="p%d" % i, tokens=28_000, job_id=None))
        r = ro.run(f)
        self.assertLess(r.detail["terminal"]["mu_term"], 0.0,
                        "mu is a price: backlog must SUBTRACT from terminal value (A19)")
        self.assertGreater(r.detail["terminal"]["residual_backlog_s"], 0.0)

    def test_out_of_sample_is_propagated(self):
        ro = rollout()
        f = fleet(1)
        f.pending.append(piece_item())
        f.in_flight.append(call_item(iid="inflight"))
        self.assertFalse(ro.run(f).in_sample)

    def test_closed_form_fallback_is_refused_while_its_flag_is_off(self):
        ro = rollout()
        f = fleet(1)
        it = piece_item()
        with self.assertRaises(MissingEvidence):
            ro.closed_form(f, it)
        ro2 = rollout(flags=Flags().with_(closed_form_fallback=True), p=params(mu=1.0))
        self.assertLessEqual(ro2.closed_form(f, it), 0.0)


class TestCoordinator(unittest.TestCase):
    def test_admission_admits_a_useful_escalation_and_opens_an_episode(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        out = co.on_event(f, dict(kind="escalation", task="SH", device="d0"))
        adm = [d for d in out if d.kind == "admission"]
        self.assertTrue(adm and adm[0].taken)
        self.assertEqual(len(f.device("d0").episodes), 1)

    def test_release_is_one_unit_at_a_time_and_stops_when_no_delta_j_is_positive(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        for i in range(3):
            f.pending.append(call_item("d0", 0.0, "c%d" % i))
        out = co._release_loop(f)
        taken = [d for d in out if d.taken]
        self.assertEqual(len(f.in_flight), len(taken))
        self.assertLessEqual(len(taken), 3)
        self.assertFalse(out[-1].taken, "the loop must end on a non-positive score")

    def test_single_shot_is_refused_rather_than_guessed(self):
        co = coordinator()
        f = fleet(1)
        with self.assertRaises(MissingEvidence):
            co._plan(f, dict(kind="escalation", task="SS", device="d0"))

    def test_infeasible_job_stops_spending_gpu_time(self):
        co = coordinator()
        f = fleet(1)
        j = job(deadline=0.01, pieces=4)
        f.jobs[j.job_id] = j
        f.pending += [piece_item(iid="p%d" % i) for i in range(4)]
        out = []
        co._update_jobs(f, out)
        self.assertEqual(j.feasibility, "INFEASIBLE")
        self.assertEqual([p for p in f.pending if p.job_id == j.job_id], [])

    def test_hold_or_merge_says_device_outcome_while_merging_is_off(self):
        co = coordinator(p=params(H=1.0))
        f = fleet(1)
        it = call_item("d0", 5.0, "future")
        f.pending.append(it)
        r = co.hold_or_merge(f, it, next_due_at=5.5)
        self.assertIn(r["action"], ("hold_then_device_outcome", "dispatch"))
        if r["action"] == "hold_then_device_outcome":
            self.assertIn("device-only outcome", r["note"])

    def test_outage_pauses_and_reconnect_restores(self):
        co = coordinator()
        f = fleet(1)
        f.pending.append(call_item())
        co.on_outage(f, "d0", 0.4)
        self.assertEqual(f.pending, [])
        self.assertFalse(f.device("d0").link.reachable)
        self.assertEqual(f.device("d0").link.p_reachable_within_hs, 0.4)
        co.on_reconnect(f, "d0")
        self.assertEqual(len(f.pending), 1)
        self.assertTrue(f.device("d0").link.reachable)

    def test_deficit_counter_rises_on_a_miss_and_floors_at_zero(self):
        co = coordinator()
        f = fleet(1)
        z1 = co.update_deficit(f, "d0", "SH", success_hat=0.0)
        self.assertAlmostEqual(z1, co.params.p_k["SH"], places=12)
        z2 = co.update_deficit(f, "d0", "SH", success_hat=1.0)
        self.assertGreaterEqual(z2, 0.0)
        for _ in range(10):
            z2 = co.update_deficit(f, "d0", "SH", success_hat=1.0)
        self.assertEqual(z2, 0.0)

    def test_price_is_zero_while_its_flag_is_off(self):
        co = coordinator(p=params(mu=5.0))
        f = fleet(1)
        self.assertEqual(co.price(f, 0.14), 0.0)
        co2 = coordinator(flags=Flags().with_(escalation_price=True), p=params(mu=5.0))
        self.assertAlmostEqual(co2.price(f, 0.14), 0.7, places=12)

    def test_conditional_mechanisms_off_changes_nothing_in_the_release_decision(self):
        f1, f2 = fleet(1), fleet(1)
        f1.pending.append(call_item())
        f2.pending.append(call_item())
        a = coordinator(p=params(H=1.0))._release_loop(f1)
        b = coordinator(flags=Flags(), p=params(H=1.0))._release_loop(f2)
        self.assertEqual([(d.kind, d.taken, round(d.delta_j or 0.0, 12)) for d in a],
                         [(d.kind, d.taken, round(d.delta_j or 0.0, 12)) for d in b])


class TestT0AndSpecMap(unittest.TestCase):
    def test_t0_refuses_holdout_and_unknown_splits(self):
        h = T0Harness()
        for split in ("HOLDOUT", "holdout", "eval", "EVAL", "test", "mystery"):
            with self.assertRaises(HoldoutRefused):
                h.run(dict(split=split, cases=[]))

    def test_t0_runs_on_a_synthetic_replay_and_labels_it(self):
        ro = rollout(p=params(H=1.0))
        f = fleet(1)
        items = [call_item("d0", 0.0, "c0"), piece_item("d0", 0.0, "p0")]
        f.pending += items
        ds = synthetic_dataset(ro, f, items, measured_overhead_s=0.01)
        out = T0Harness(tolerance_delay_s=0.05).run(ds)
        self.assertEqual(out["split"], "synthetic")
        self.assertEqual(out["verdict"], "PASS")
        self.assertIn("SYNTHETIC", ds["note"])

    def test_spec_map_resolves_and_lists_every_section(self):
        c = check()
        self.assertTrue(c["ok"], c["missing"])
        self.assertGreaterEqual(c["n_sections"], 30)
        self.assertGreaterEqual(c["n_ambiguities"], 10)

    def test_every_ambiguity_names_a_reversible_place(self):
        for a in AMBIGUITIES:
            for key in ("id", "where", "question", "choice", "why", "reversible_at"):
                self.assertTrue(a.get(key), "%s lacks %s" % (a.get("id"), key))
